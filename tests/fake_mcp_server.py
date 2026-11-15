"""一个最小的 MCP 服务器，用于测试 pdfquiz 的 MCP 客户端。

行为：把提示词里 <<< >>> 之间的正文首句当作"真实依据"，
另外返回一道**伪造依据**的题（原文里压根没有这句话），
用来验证下游校验器确实能拦住幻觉。
"""

from __future__ import annotations

import json
import re
import sys

TOOLS = [
    {
        "name": "chat",
        "description": "fake chat tool for tests",
        "inputSchema": {
            "type": "object",
            "properties": {"prompt": {"type": "string"}, "system": {"type": "string"}},
            "required": ["prompt"],
        },
    }
]


def body_of(prompt: str) -> str:
    m = re.search(r"<<<\s*(.+?)\s*>>>", prompt, re.S)
    return m.group(1) if m else prompt


def reply(prompt: str) -> str:
    text = body_of(prompt)
    # 只在"标点 + 空白"处断句，避免把 3.3 这类小数当句末
    parts = [s for s in re.split(r"(?<=[。！？])\s*|(?<=[.!?])\s+", text) if s.strip()]
    first = (parts[0] if parts else text).strip()
    questions = {
        "questions": [
            {
                "type": "single",
                "bloom": "理解",
                "difficulty": "medium",
                "question": "根据本节内容，下列说法正确的是？",
                "options": [
                    "A. 与原文一致的说法",
                    "B. 原文未提及的说法",
                    "C. 与原文相反的说法",
                    "D. 以上都不对",
                ],
                "answer": "A",
                "explanation": "A 与原文首句一致。",
                "evidence": first,
            },
            {
                "type": "single",
                "bloom": "记忆",
                "difficulty": "easy",
                "question": "这是一道依据被编造的题？",
                "options": ["A. 甲", "B. 乙", "C. 丙", "D. 丁"],
                "answer": "A",
                "explanation": "模型幻觉。",
                "evidence": "这段话在原始文档中并不存在纯属模型编造。",
            },
        ]
    }
    return json.dumps(questions, ensure_ascii=False)


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = msg.get("method")
        if method == "initialize":
            out = {
                "jsonrpc": "2.0",
                "id": msg["id"],
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fake-mcp", "version": "0.0.1"},
                },
            }
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            out = {"jsonrpc": "2.0", "id": msg["id"], "result": {"tools": TOOLS}}
        elif method == "tools/call":
            args = msg.get("params", {}).get("arguments", {})
            out = {
                "jsonrpc": "2.0",
                "id": msg["id"],
                "result": {
                    "content": [{"type": "text", "text": reply(args.get("prompt", ""))}],
                    "isError": False,
                },
            }
        else:
            out = {
                "jsonrpc": "2.0",
                "id": msg.get("id"),
                "error": {"code": -32601, "message": f"unknown method {method}"},
            }
        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
