"""命令行入口。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .chunk import Chunk, chunk_markdown
from .extract import extract
from .generate import build_prompts, generate_for_chunk, offline_questions, parse_questions
from .llm import LLMError, chat
from .render import render
from .verify import Report, verify

DEFAULT_TYPES = ["single", "multiple", "truefalse", "short"]


def _argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pdfquiz",
        description="PDF/讲义 → Markdown → 带原文溯源的复习题",
    )
    p.add_argument("source", help="PDF / Markdown / TXT 路径")
    p.add_argument("-o", "--out", default="out", help="输出目录（默认 out/）")
    p.add_argument("-n", "--num", type=int, default=4, help="每块题量（默认 4）")
    p.add_argument("--types", default=",".join(DEFAULT_TYPES), help="题型，逗号分隔")
    p.add_argument("--lang", default="zh", choices=["zh", "en"], help="出题语言")
    p.add_argument("--max-chars", type=int, default=2000, help="单块上限字数")
    p.add_argument("--min-chars", type=int, default=60, help="碎片合并阈值")
    p.add_argument("--extract-only", action="store_true", help="只做解析，导出 Markdown 就停")
    p.add_argument("--keep-md", action="store_true", help="保留中间 Markdown")
    p.add_argument("--no-html", action="store_true", help="不生成网页版题库")
    p.add_argument("-V", "--version", action="version", version=f"pdfquiz {__version__}")

    g = p.add_argument_group("模型来源（四选一，默认自动探测）")
    g.add_argument(
        "--provider",
        choices=["auto", "openai", "mcp", "bridge", "offline"],
        default="auto",
        help="auto=有 API Key 走 openai，否则走 bridge（由当前会话的智能体出题）",
    )
    g.add_argument("--model", default=None)
    g.add_argument("--base-url", default=None)
    g.add_argument("--api-key", default=None)

    m = p.add_argument_group("MCP 模式")
    m.add_argument("--mcp-cmd", default=os.getenv("PDFQUIZ_MCP_CMD"), help="MCP 服务器启动命令")
    m.add_argument(
        "--mcp-args",
        default=os.getenv("PDFQUIZ_MCP_ARGS"),
        help="MCP 启动参数，逗号分隔（如 -y,@scope/server）",
    )
    m.add_argument("--mcp-tool", default=os.getenv("PDFQUIZ_MCP_TOOL", "chat"), help="工具名")
    m.add_argument("--mcp-prompt-key", default="prompt", help="提示词参数名")
    m.add_argument("--mcp-system-key", default="system", help="系统提示参数名，留空则不传")

    b = p.add_argument_group("桥接模式（两段式，由外部智能体充当 LLM）")
    b.add_argument("--emit-prompts", metavar="PATH", help="只导出提示词到 JSON，然后退出")
    b.add_argument("--answers", metavar="PATH", help="读入外部生成的答案 JSON，继续校验与导出")

    p.add_argument("--offline", action="store_true", help="[兼容旧用法] 等价于 --provider offline")
    return p


def _build_chat(args) -> tuple[object | None, str]:
    """返回 (chat_fn, 描述)。"""
    if args.mcp_cmd:
        from .mcp_llm import MCPChat

        mcp = MCPChat(
            args.mcp_cmd,
            [a for a in (args.mcp_args or "").split(",") if a],
            tool=args.mcp_tool,
            prompt_key=args.mcp_prompt_key,
            system_key=args.mcp_system_key or None,
        )
        return mcp, f"mcp · {args.mcp_cmd} · {args.mcp_tool}"

    def openai_chat(system: str, user: str) -> str:
        return chat(
            system, user,
            model=args.model, base_url=args.base_url, api_key=args.api_key,
        )

    return openai_chat, f"openai · {args.model or os.getenv('PDFQUIZ_MODEL') or 'gpt-4o-mini'}"


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # Windows 控制台默认 GBK
        except Exception:
            pass

    args = _argparser().parse_args(argv)
    if args.offline:
        args.provider = "offline"
    src = Path(args.source)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = src.stem

    print(f"[1/4] 解析 {src.name} …")
    try:
        doc = extract(src)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"[!] {exc}")
        return 2
    print(f"      解析器 {doc.engine} · {doc.pages or '?'} 页 · {len(doc.markdown)} 字符")
    for w in doc.warnings:
        print(f"      ⚠ {w}")

    if args.keep_md or args.extract_only:
        md_path = out_dir / f"{stem}.extracted.md"
        md_path.write_text(doc.markdown, encoding="utf-8")
        print(f"      已写出 {md_path}")
    if args.extract_only:
        return 0

    print("[2/4] 切块 …")
    chunks = chunk_markdown(doc.markdown, args.max_chars, args.min_chars)
    print(f"      {len(chunks)} 块，最长 {max((c.chars for c in chunks), default=0)} 字符")
    if not chunks:
        print("      正文为空，可能是扫描件。先 OCR，或改用 docling / pymupdf4llm。")
        return 2

    types = [t.strip() for t in args.types.split(",") if t.strip()]

    if args.emit_prompts:
        return _emit_prompts(chunks, args, types, Path(args.emit_prompts))

    provider = args.provider
    if provider == "auto":
        if args.mcp_cmd:
            provider = "mcp"
        elif args.api_key or os.getenv("OPENAI_API_KEY"):
            provider = "openai"
        else:
            provider = "bridge"
    if provider == "bridge" and not args.answers:
        print(
            "[!] 未配置 API Key，且未提供 --answers。\n"
            "    桥接模式下请先导出提示词，由会话中的智能体作答：\n"
            f"      python run.py {args.source} --emit-prompts prompts.json\n"
            "    然后再执行：\n"
            f"      python run.py {args.source} --answers answers.json"
        )
        return 4

    chat_fn = None
    label = "offline"
    bridge_items: list | None = None
    if provider in {"openai", "mcp"}:
        chat_fn, label = _build_chat(args)
    elif provider == "bridge":
        label = "bridge · 外部答案文件"
        try:
            bridge_items = _load_answers(args.answers)
        except RuntimeError as exc:
            print(f"[!] {exc}")
            return 4
    print(f"[3/4] 出题 + 溯源校验 · 来源 {label} …")

    reports: list[Report] = []
    try:
        for pos, c in enumerate(chunks):
            try:
                if provider == "offline":
                    raw_qs = offline_questions(c, args.num)
                elif provider == "bridge":
                    raw_qs = parse_questions(_bridge_answer(bridge_items, pos), c)
                else:
                    raw_qs = generate_for_chunk(c, args.num, types, args.lang, chat_fn)
            except (LLMError, RuntimeError) as exc:
                print(f"      ✗ 第 {c.idx} 块失败：{exc}")
                continue

            rep = verify(raw_qs, c.text)
            reports.append(rep)
            if provider == "offline" and not rep.accepted:
                mark = "（本节无定义句，跳过）"
            elif rep.rejected:
                mark = f"（弃 {len(rep.rejected)}）"
            else:
                mark = ""
            print(f"      块 {c.idx:>2} {c.title[:24]:<26} 过 {len(rep.accepted)} {mark}")
    finally:
        if provider == "mcp" and chat_fn is not None:
            chat_fn.close()

    accepted = [q for r in reports for q in r.accepted]
    if not accepted:
        print("      没有题目通过校验。检查模型输出、API Key，或放宽 --min-chars。")
        return 3

    print("[4/4] 导出 …")
    quiz_md = render(
        title=stem,
        engine=doc.engine,
        source=str(src),
        chunks=len(chunks),
        reports=reports,
        mock=(provider == "offline"),
    )
    quiz_path = out_dir / f"{stem}.quiz.md"
    quiz_path.write_text(quiz_md, encoding="utf-8")

    print(f"      题库 {quiz_path}")
    if not args.no_html:
        from .render_html import render_html

        web = render_html(
            title=stem,
            engine=doc.engine,
            source=str(src),
            chunks=len(chunks),
            reports=reports,
            mock=(provider == "offline"),
        )
        web_path = out_dir / f"{stem}.quiz.html"
        web_path.write_text(web, encoding="utf-8")
        print(f"      网页版 {web_path}")

    rejected = [q for r in reports for q in r.rejected]
    if rejected:
        (out_dir / f"{stem}.rejected.json").write_text(
            json.dumps(rejected, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    total = len(accepted) + len(rejected)
    print(f"      通过 {len(accepted)}/{total} 题，淘汰率 {len(rejected) / max(1, total):.0%}")
    return 0


def _emit_prompts(chunks: list[Chunk], args, types: list[str], path: Path) -> int:
    payload = []
    for c in chunks:
        system, user = build_prompts(c, args.num, types, args.lang)
        payload.append(
            {"chunk": c.idx, "path": c.path, "system": system, "user": user}
        )
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"      已导出 {len(payload)} 条提示词 → {path}")
    print("      下一步：由智能体按提示词作答，写入 answers.json 后用 --answers 传入。")
    return 0


def _load_answers(path: str) -> list:
    """读入外部答案文件，一次解析后复用；错误转成可读提示。"""
    p = Path(path)
    if not p.exists():
        raise RuntimeError(f"找不到答案文件：{p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"答案文件不是合法 JSON：{p}（{exc}）") from exc
    items = data.get("answers", data) if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise RuntimeError(
            f"答案文件格式不正确：{p}；应为数组，或包含 answers 数组的对象"
        )
    return items


def _bridge_answer(items: list, pos: int) -> str:
    if pos >= len(items):
        raise RuntimeError(f"answers 只有 {len(items)} 条，缺少第 {pos + 1} 块")
    item = items[pos]
    if isinstance(item, dict):
        item = item.get("text") or item.get("content") or json.dumps(item, ensure_ascii=False)
    return str(item)
