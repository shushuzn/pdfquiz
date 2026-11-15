"""用最新的网页模板重渲染已经生成的题库，不必重跑解析与出题。

改了模板（换配色、调移动端布局）之后，旧产物里的题目 JSON 还是好的，
只是外壳过时了。这个脚本把 HTML 内联的 window.__QUIZ__ 取出来，塞回当前
模板重新拼一遍，题目内容一个字都不动。

用法：
    python tools/restyle.py examples/*.quiz.html          就地重写
    python tools/restyle.py in.html -o out.html           另存
"""

from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "pdfquiz" / "templates" / "quiz.html"

PAYLOAD = re.compile(r"window\.__QUIZ__\s*=\s*(\{.*?\});\s*</script>", re.S)
HUB_LINK = re.compile(r'<a class="hub-link" href="[^"]*">.*?</a>', re.S)


def _hub_link(href: str) -> str:
    return (
        '<a class="hub-link" href="' + html.escape(href) + '">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
        '<path d="M19 12H5M12 19l-7-7 7-7"/></svg>'
        "全部试卷</a>"
    )


def restyle(src: Path, tpl: str, hub: str | None = None) -> str:
    raw = src.read_text(encoding="utf-8")
    m = PAYLOAD.search(raw)
    if not m:
        raise SystemExit(f"{src}：找不到内联题库数据，可能不是本工具生成的页面")

    payload = json.loads(m.group(1))
    meta = payload.get("meta") or {}
    title = meta.get("title") or meta.get("id") or src.stem
    generated = meta.get("generated") or f"{datetime.now():%Y-%m-%d %H:%M}"
    n = len(payload.get("questions") or [])

    bits = [f"解析器 {meta.get('engine', '—')}", f"{n} 题", f"生成于 {generated}"]
    if meta.get("mock"):
        bits.insert(0, "离线模式产物")

    # 重渲染不能丢掉「全部试卷」入口：优先用显式参数，否则沿用旧页面里的链接
    if hub:
        hublink = _hub_link(hub)
    else:
        old = HUB_LINK.search(raw)
        hublink = old.group(0) if old else ""

    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return (
        tpl.replace("{{TITLE}}", html.escape(str(title)))
        .replace("{{SUBTITLE}}", html.escape(" · ".join(bits)))
        .replace("{{SOURCE}}", html.escape(str(meta.get("source", ""))))
        .replace("{{HUPLINK}}", hublink)
        .replace("{{DATA}}", data)
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="用最新模板重渲染已有题库")
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("-o", "--out", type=Path, help="只处理一个文件时另存到此处")
    ap.add_argument("--hub", help="侧栏「全部试卷」链接地址；默认沿用旧页面里的设置")
    args = ap.parse_args()

    if args.out and len(args.files) > 1:
        raise SystemExit("-o 只能在处理单个文件时使用")

    tpl = TEMPLATE.read_text(encoding="utf-8")
    for src in args.files:
        out = restyle(src, tpl, hub=args.hub)
        dst = args.out or src
        dst.write_text(out, encoding="utf-8")
        print(f"✓ {src} → {dst}（{len(out) / 1024:.0f} KB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
