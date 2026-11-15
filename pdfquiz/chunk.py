"""Markdown -> 章节感知的切块。

切块的边界决定出题质量：模型只能看到眼前这一块，
所以切块必须贴着文档自身的章节结构，而不是按固定字数硬切。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

HEAD_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
SENT_SPLIT = re.compile(r"(?<=[。！？；.!?;])\s*")


@dataclass
class Chunk:
    idx: int
    title: str
    path: str
    text: str

    @property
    def chars(self) -> int:
        return len(self.text)


def chunk_markdown(
    markdown: str,
    max_chars: int = 2000,
    min_chars: int = 60,
) -> list[Chunk]:
    """按标题切分，过长的段落再按句切，极短的碎片并入后一节。

    一节 100-200 字在教材里是正常粒度，足够支撑 2-4 道题，
    所以默认只在正文短于 60 字（纯过渡句、空节）时才做合并。
    合并方向朝后：碎片作为下一节的引子，章节标签才不会失真。
    """
    sections = _split_sections(markdown)
    pieces: list[tuple[str, str, str]] = []  # (title, path, body)

    for title, path, body in sections:
        if len(body) <= max_chars:
            pieces.append((title, path, body))
            continue
        for i, part in enumerate(_split_long(body, max_chars)):
            pieces.append((f"{title} ({i + 1})" if i else title, path, part))

    merged: list[tuple[str, str, str]] = []
    carry = ""
    last = len(pieces) - 1
    for i, (title, path, body) in enumerate(pieces):
        if len(body) < min_chars and i < last:
            carry = f"{carry}\n\n{body}".strip() if carry else body
            continue
        merged.append((title, path, f"{carry}\n\n{body}".strip() if carry else body))
        carry = ""

    return [
        Chunk(idx=i, title=t, path=p, text=b)
        for i, (t, p, b) in enumerate(merged, 1)
        if b.strip()
    ]


def _split_sections(markdown: str) -> list[tuple[str, str, str]]:
    lines = markdown.splitlines()
    stack: list[tuple[int, str]] = []
    sections: list[tuple[str, str, str]] = []
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if not body:
            buf.clear()
            return
        title = stack[-1][1] if stack else "(文档开头)"
        path = " > ".join(t for _, t in stack) or title
        sections.append((title, path, body))
        buf.clear()

    for line in lines:
        m = HEAD_RE.match(line)
        if m:
            flush()
            level = len(m.group(1))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, m.group(2).strip()))
        else:
            buf.append(line)
    flush()
    return sections


def _split_long(body: str, max_chars: int) -> list[str]:
    out: list[str] = []
    cur: list[str] = []
    size = 0
    for para in [p for p in body.split("\n\n") if p.strip()]:
        if len(para) > max_chars:
            for sent in SENT_SPLIT.split(para):
                sent = sent.strip()
                if not sent:
                    continue
                if size + len(sent) > max_chars and cur:
                    out.append("\n\n".join(cur))
                    cur, size = [], 0
                cur.append(sent)
                size += len(sent)
            continue
        if size + len(para) > max_chars and cur:
            out.append("\n\n".join(cur))
            cur, size = [], 0
        cur.append(para)
        size += len(para) + 2
    if cur:
        out.append("\n\n".join(cur))
    return out
