"""教材 Markdown 的文本处理：页标记、切句、词汇表还原、章节路径。

这些函数原本散在 `tools/build_exam.py` 里，被 build_objective / build_materials
反过来 import —— 脚本之间互相 import 很脆（改个工作目录就断）。抽成模块后：

  - 谁都能 import，不再依赖 sys.path 注入；
  - 页标记的处理只有一处实现，`verify` 也用同一套规则；
  - 纯函数，好测（见 tests/test_booktext.py）。

约定：教材转录稿的页边界写成 `### p151` 这样的三级标题，正文在 `## 正文` 与
`## Words and Expressions` 之间。
"""

from __future__ import annotations

import re

# `### p151` / `### 151` 这类页标记
PAGE_MARK = re.compile(r"^#{1,6}\s*p?\.?\s*\d{1,4}\s*$", re.M)

# 页眉里重复的「170 **UNIT 3 Step Growth Polymerization**」
_RUNNING_HEAD = re.compile(r"^\d{1,3}\s+\*\*.{0,80}?\*\*\s*$", re.M)
# 插图说明 / 脚注
_CAPTION = re.compile(r"^>.*$", re.M)
_BODY = re.compile(r"^##\s*正文(.*?)^##\s*Words", re.M | re.S)
_VOCAB = re.compile(r"^##\s*Words and Expressions(.*?)(?:\n##\s|\Z)", re.M | re.S)


def strip_page_marks(text: str) -> str:
    """去掉页标记，留下正文。

    `verify` 做逐字回查时必须先走这一步：书上一句话被翻页切开时，中间会插一行
    `### p151`，不摘掉就永远匹配不上，只能把好好的句子当幻觉丢掉。
    """
    return PAGE_MARK.sub("", text)


def split_body(md: str) -> str:
    """只要正文，不要词汇表与注释——术语题的高频统计必须基于正文。

    保留 `### pN` 页标记：句子切分要以页为界。跨页拼接出来的「句子」在原文里
    并不连续，拿它当 evidence 会过不了逐字回查。
    """
    m = _BODY.search(md)
    if m:
        body = m.group(1)
    else:
        # 有的转录稿没有 `## 正文` 这个小标题，退一步：词汇表之前都算正文。
        # 不这么兜底的话，词汇表会漏进正文，句子依据和词频统计全被污染。
        cut = re.search(r"^##\s*Words", md, re.M)
        body = md[: cut.start()] if cut else md
    body = _CAPTION.sub("", body)
    body = _RUNNING_HEAD.sub("", body)
    return body


def clean_md(md: str) -> str:
    """抹掉 Markdown 记号，用于「整篇文本里搜句子」这类粗粒度匹配。"""
    t = re.sub(r"^\|.*$", "", md, flags=re.M)          # 表格行
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.M)        # 标题
    t = re.sub(r"\*{1,2}|_{1,2}", "", t)                # 强调符
    t = re.sub(r"\$\$?.*?\$\$?", "", t, flags=re.S)      # 公式
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def unit_title(md: str, stem: str) -> str:
    """一级标题去掉尾部括号注释，取不到就退回 `UNIT n`。"""
    m = re.search(r"^#\s+(.+)$", md, re.M)
    if m:
        title = re.sub(r"[（(][^）)]*[）)]\s*$", "", m.group(1)).strip()
        if title:
            return title
    return f"UNIT {int(stem[4:])}"


def part_of_unit(num: int) -> str:
    if num <= 10:
        return "PART A 高分子化学与物理"
    if num <= 20:
        return "PART B 高分子材料工程"
    return "PART C 高分子材料与应用"


def canonical_path(num: int, titles: dict[int, str], fallback: str = "") -> str:
    """统一成「PART A … > UNIT 3 …」，避免同一单元在不同卷里被写成两种路径。"""
    part = part_of_unit(num)
    title = titles.get(num, "")
    if part and title:
        return f"{part} > {title}"
    return title or fallback


def parse_vocab(md: str) -> list[dict]:
    """从 `## Words and Expressions` 的表格还原词条。"""
    m = _VOCAB.search(md)
    if not m:
        return []
    rows = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        term, _, pos, meaning = cells[0], cells[1], cells[2], cells[3]
        if term.lower() in {"term", ""} or set(term) <= {"-", ":"}:
            continue
        if not re.match(r"^[A-Za-z][A-Za-z\s\-']*$", term):
            continue
        rows.append({"term": term, "pos": pos, "meaning": meaning})
    return rows


def sentences(body: str) -> list[str]:
    """按页切句。跨页拼出来的句子在原文中并不连续，不能当依据。"""
    out: list[str] = []
    for chunk in re.split(r"^###.*$", body, flags=re.M):
        flat = re.sub(r"\s+", " ", chunk)
        parts = re.split(r"(?<=[.;!?])\s+", flat)
        out += [p.strip() for p in parts if len(p.strip()) > 30]
    return out


def first_meaning(raw: str) -> str:
    """教材释义常写成「性能,行为」「溶解[度];溶液」，只取第一个义项。"""
    meaning = re.sub(r"\[[^\]]*\]", "", raw)
    meaning = re.split(r"[;；]", meaning)[0]
    meaning = re.split(r"[,，]", meaning)[0].strip()
    return meaning
