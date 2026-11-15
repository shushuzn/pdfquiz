"""通过 MCP（stdio / JSON-RPC 2.0）调用 LLM 工具。

协议要点（MCP 2024-11-05）：
    initialize -> notifications/initialized -> tools/list -> tools/call

为什么自己写而不用 SDK：只需要一个 tools/call，不到 200 行，
省掉一层依赖，也方便你换成任何自建的 MCP 服务器。

配置（任一方式）：
    CLI:  --mcp-cmd npx --mcp-args "-y,@model/xxx-server" --mcp-tool chat
    ENV:  PDFQUIZ_MCP_CMD / PDFQUIZ_MCP_ARGS / PDFQUIZ_MCP_TOOL
"""

from __future__ import annotations

import json
import queue
import subprocess
import threading

PROTOCOL_VERSION = "2024-11-05"


class MCPError(RuntimeError):
    pass


class StdioMCPClient:
    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        *,
        timeout: float = 180.0,
        env: dict | None = None,
    ) -> None:
        self.timeout = timeout
        self._queue: queue.Queue = queue.Queue()
        self._stderr_tail: list[str] = []
        self._next_id = 0
        self._tools: list[str] = []

        try:
            self.proc = subprocess.Popen(
                [command, *(args or [])],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
            )
        except FileNotFoundError as exc:
            raise MCPError(f"找不到 MCP 服务器命令：{command}") from exc

        threading.Thread(target=self._pump_stdout, daemon=True).start()
        threading.Thread(target=self._pump_stderr, daemon=True).start()
        self._handshake()

    # ------------------------------------------------------------ 生命周期

    def _pump_stdout(self) -> None:
        assert self.proc.stdout
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self._queue.put(json.loads(line))
            except json.JSONDecodeError:
                continue

    def _pump_stderr(self) -> None:
        assert self.proc.stderr
        for line in self.proc.stderr:
            self._stderr_tail.append(line.rstrip())
            del self._stderr_tail[:-20]

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass

    def __enter__(self) -> "StdioMCPClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------ 调用

    def _request(self, method: str, params: dict | None = None) -> dict:
        self._next_id += 1
        rid = self._next_id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})

        while True:
            try:
                msg = self._queue.get(timeout=self.timeout)
            except queue.Empty:
                tail = "\n".join(self._stderr_tail[-5:])
                raise MCPError(
                    f"等待 {method} 响应超时（{self.timeout:.0f}s）。"
                    + (f"\n服务器 stderr：\n{tail}" if tail else "")
                ) from None

            if msg.get("id") != rid:
                continue  # 服务器主动通知/日志帧，跳过
            if "error" in msg:
                err = msg["error"]
                raise MCPError(f"{method} 失败：{err.get('message', err)}")
            return msg.get("result", {})

    def _send(self, payload: dict) -> None:
        if not self.proc.stdin:
            raise MCPError("MCP 进程已关闭")
        try:
            self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, ValueError) as exc:
            tail = "\n".join(self._stderr_tail[-5:])
            raise MCPError(f"写入 MCP 进程失败：{exc}\n{tail}") from exc

    def _notify(self, method: str) -> None:
        self._send({"jsonrpc": "2.0", "method": method})

    def _handshake(self) -> None:
        self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "pdfquiz", "version": "0.1.0"},
            },
        )
        self._notify("notifications/initialized")
        try:
            result = self._request("tools/list")
            self._tools = [t.get("name", "") for t in result.get("tools", [])]
        except MCPError:
            self._tools = []

    @property
    def tools(self) -> list[str]:
        return self._tools

    def call_tool(self, name: str, arguments: dict) -> str:
        if self._tools and name not in self._tools:
            raise MCPError(
                f"服务器没有工具 {name!r}。可用：{', '.join(self._tools) or '(无)'}"
            )
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise MCPError(f"工具 {name} 返回错误：{_content_text(result)[:400]}")
        text = _content_text(result)
        if not text:
            raise MCPError(f"工具 {name} 返回空内容")
        return text


def _content_text(result: dict) -> str:
    parts = []
    for item in result.get("content", []) or []:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text", "")))
    return "\n".join(parts).strip()


class MCPChat:
    """把 MCP 工具包装成 chat(system, user) -> str。"""

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        tool: str = "chat",
        prompt_key: str = "prompt",
        system_key: str | None = "system",
        timeout: float = 180.0,
    ) -> None:
        self.tool = tool
        self.prompt_key = prompt_key
        self.system_key = system_key
        self.client = StdioMCPClient(command, args, timeout=timeout)

    def __call__(self, system: str, user: str) -> str:
        args: dict = {self.prompt_key: user}
        if self.system_key:
            args[self.system_key] = system
        return self.client.call_tool(self.tool, args)

    def close(self) -> None:
        self.client.close()
