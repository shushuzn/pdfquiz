"""把 KaTeX 的 CSS 打成「字体内联」的单文件，供离线页面直接嵌入。

    python tools/make_katex_css.py <katex dist 目录>

KaTeX 默认从 fonts/ 目录按文件名加载 woff2/woff/ttf 三种格式。我们的站点是
一个 HTML 文件走天下（题库页、例题页都要求离线可用），所以把每个 woff2 读出来
做 base64，塞进 @font-face 的 data URI，顺手丢掉 woff/ttf 兜底——现代浏览器
全都支持 woff2，留着只会让文件翻倍。

产物 vendor/katex/katex.inline.css 与 vendor/katex/katex.min.js 一起提交，
构建页面时不需要联网，也不需要 node/npm。
"""

from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "vendor" / "katex" / "katex.inline.css"

# url(fonts/KaTeX_Main-Regular.woff2) format("woff2"),url(...) format("woff"),url(...) format("truetype")
SRC_RE = re.compile(r"""src:url\(([^)]*?\.woff2)\)\s*format\("woff2"\)(?:,url\([^)]*\)\s*format\("[^"]*"\))*""")


def build(dist: Path) -> str:
    css = (dist / "katex.min.css").read_text(encoding="utf-8")

    def inline(m: re.Match) -> str:
        rel = m.group(1)
        font = dist / rel
        if not font.exists():
            raise SystemExit(f"缺字体文件：{font}")
        b64 = base64.b64encode(font.read_bytes()).decode("ascii")
        return f'src:url(data:font/woff2;base64,{b64}) format("woff2")'

    out = SRC_RE.sub(inline, css)
    left = re.findall(r"url\((?!data:)[^)]*\)", out)
    if left:
        raise SystemExit(f"仍有外部引用没内联：{left[:5]}")
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    dist = Path(argv[0])
    css = build(dist)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(css, encoding="utf-8")
    print(f"{TARGET.relative_to(ROOT)} {len(css):,} 字节")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
