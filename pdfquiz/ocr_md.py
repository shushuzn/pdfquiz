"""扫描件 OCR 文本 → 结构化 Markdown。

面对于「专业英语教材」这类排版，难点不在正文（单栏段落，好办），
而在每单元末尾的 Words and Expressions 词汇表：OCR 出来是散行，
必须按列位置还原成 词条 / 音标 / 词性 / 释义 四列，否则术语题没有可靠依据。
"""

from __future__ import annotations

import re

from .ocr import Line, PageOCR

# 词性标记：n. v. a. ad. adj. adv. prep. conj. pron. num. vt. vi.
_POS = re.compile(
    r"^(n|v|a|ad|adj|adv|prep|conj|pron|num|vt|vi|art|int|aux)\s*\.$", re.I
)
_HEADING_VOCAB = re.compile(r"words?\s*(and|&)\s*expressions?", re.I)
_PAGE_NO = re.compile(r"^\s*[\-—–]?\s*\d{1,3}\s*[\-—–]?\s*$")
_PHONETIC = re.compile(r"^[\[/\(（【].*[\]/\)）】]$")
_UNIT_HEAD = re.compile(r"^\s*UNIT\s+(\d{1,2})\b[\.\s:]*(.*)$", re.I)
_PART_HEAD = re.compile(r"^\s*PART\s+([A-C])\b[\.\s:]*(.*)$", re.I)

# 行尾连字符断词：polym-\ner → polymer
_HYPHEN_BREAK = re.compile(r"(\w)-\s*$")


def clean_line(s: str) -> str:
    s = s.replace("\u00ad", "")
    return s.strip()


def is_page_number(s: str) -> bool:
    return bool(_PAGE_NO.match(s))


def is_vocab_heading(s: str) -> bool:
    return bool(_HEADING_VOCAB.search(s))


def looks_vocab_row(cells: list[str]) -> bool:
    """至少有一个 cell 是词性或音标，才认为这是词汇表的一行。"""
    if len(cells) < 2:
        return False
    for c in cells:
        c = c.strip()
        if _POS.match(c) or _PHONETIC.match(c):
            return True
    return False


def parse_vocab_row(cells: list[str]) -> dict | None:
    """把一行 cell 归到 词条/音标/词性/释义。缺列时容忍。"""
    cells = [c.strip() for c in cells if c.strip()]
    if not cells:
        return None

    term = cells[0]
    phonetic = ""
    pos = ""
    meaning = ""

    rest = cells[1:]
    i = 0
    if i < len(rest) and _PHONETIC.match(rest[i]):
        phonetic = rest[i]
        i += 1
    if i < len(rest) and _POS.match(rest[i]):
        pos = rest[i]
        i += 1
    if i < len(rest):
        meaning = " ".join(rest[i:])

    # 音标有时会和词条粘在一起
    if not phonetic:
        m = re.search(r"[\[/]([^\]/]{2,30})[\]/]", term)
        if m:
            phonetic = "[" + m.group(1) + "]"
            term = (term[: m.start()] + term[m.end() :]).strip()

    if not term or len(term) > 80:
        return None
    return {"term": term, "phonetic": phonetic, "pos": pos, "meaning": meaning}


# ---------------------------------------------------------------- 页 → 段落


def page_to_blocks(page: PageOCR) -> list[dict]:
    """把一页的 OCR 行转成 block 列表：heading / para / vocab / table。

    正文按行首缩进判断段落起止：扫描件里段首通常有缩进，
    OCR 的 x0 能反映出来，但这里简化为「行尾标点 + 行首大写」的启发式。
    """
    blocks: list[dict] = []
    vocab_mode = False
    para: list[str] = []

    def flush():
        nonlocal para
        if para:
            blocks.append({"type": "para", "text": " ".join(para).strip()})
            para = []

    for ln in page.lines:
        text = clean_line(ln.text.replace("\t", " "))
        if not text:
            continue
        if is_page_number(text):
            continue

        if is_vocab_heading(text):
            flush()
            vocab_mode = True
            blocks.append({"type": "vocab_heading", "text": text})
            continue

        m_unit = _UNIT_HEAD.match(text)
        if m_unit and len(text) < 90:
            flush()
            vocab_mode = False
            blocks.append(
                {
                    "type": "unit",
                    "num": int(m_unit.group(1)),
                    "title": m_unit.group(2).strip(" .:："),
                }
            )
            continue

        m_part = _PART_HEAD.match(text)
        if m_part and len(text) < 90:
            flush()
            vocab_mode = False
            blocks.append(
                {
                    "type": "part",
                    "letter": m_part.group(1).upper(),
                    "title": m_part.group(2).strip(" .:："),
                }
            )
            continue

        if vocab_mode:
            cells = [c for c in ln.cells if c.strip()]
            if looks_vocab_row(cells):
                row = parse_vocab_row(cells)
                if row:
                    blocks.append({"type": "vocab", **row})
                    continue
            # 词汇表里的续行（释义换行）并到上一条
            if blocks and blocks[-1]["type"] == "vocab" and len(text) < 60:
                blocks[-1]["meaning"] = (blocks[-1]["meaning"] + " " + text).strip()
                continue
            # 不是词条行也不是续行 → 退出词汇表模式
            vocab_mode = False

        # 正文
        if para and _HYPHEN_BREAK.search(para[-1]):
            para[-1] = _HYPHEN_BREAK.sub("", para[-1]) + text
        else:
            para.append(text)

    flush()
    return blocks


def pages_to_markdown(
    pages: list[PageOCR],
    title: str = "",
    unit_offset: int = 0,
) -> str:
    """把 OCR 结果拼成带层级的 Markdown。"""
    out: list[str] = []
    if title:
        out.append(f"# {title}\n")

    part_name = {"A": "Part A", "B": "Part B", "C": "Part C"}
    cur_unit = 0

    for page in pages:
        blocks = page_to_blocks(page)
        for b in blocks:
            t = b["type"]
            if t == "part":
                out.append(
                    f"\n## PART {b['letter']} {b['title']}\n".replace("  ", " ")
                )
                out.append(f"<!-- pdf-page {page.page} -->\n")
            elif t == "unit":
                cur_unit = b["num"]
                bare = b["title"]
                # 有些单元标题跨行，OCR 会把标题和副标题并在一行
                out.append(f"\n### UNIT {b['num']} {bare}\n")
                out.append(f"<!-- pdf-page {page.page} -->\n")
            elif t == "vocab_heading":
                out.append("\n#### Words and Expressions\n")
                out.append("| Term | Phonetic | POS | Meaning |")
                out.append("|---|---|---|---|")
            elif t == "vocab":
                out.append(
                    "| {term} | {phonetic} | {pos} | {meaning} |".format(
                        term=_cell(b["term"]),
                        phonetic=_cell(b["phonetic"]),
                        pos=_cell(b["pos"]),
                        meaning=_cell(b["meaning"]),
                    )
                )
            elif t == "para":
                txt = b["text"]
                if len(txt) < 3:
                    continue
                out.append("\n" + txt + "\n")

    md = "\n".join(out)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip() + "\n"


def _cell(s: str) -> str:
    return (s or "").replace("|", "\\|").strip()
