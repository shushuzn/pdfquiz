"""文档 -> 结构化 Markdown。

解析器按质量降序尝试，谁装了用谁：
    pymupdf4llm  (快，CPU 可跑，保留标题/表格)
    docling      (IBM，MIT，结构化最好，支持 CJK)
    pypdf        (零 ML 兜底，只有纯文本，丢失版式)

设计取舍：不把 Docling 写成硬依赖。它的模型缓存约 1-2GB，
不该成为"只是想转换一份 PDF"的前置条件。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

PASS_SUFFIX = {".md", ".markdown", ".txt"}


class _EngineMissing(Exception):
    """该解析器未安装，跳到下一个。"""


@dataclass
class Extracted:
    markdown: str
    engine: str
    pages: int = 0
    warnings: list[str] = field(default_factory=list)


def extract(path: str | Path) -> Extracted:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"找不到文件：{path}")
    suffix = path.suffix.lower()

    if suffix in PASS_SUFFIX:
        text = path.read_text(encoding="utf-8", errors="ignore")
        return Extracted(text, "passthrough", 0)

    if suffix != ".pdf":
        raise ValueError(f"不支持的格式 {suffix}；支持 .pdf / .md / .txt")

    tried: list[str] = []
    for name, fn in (
        ("pymupdf4llm", _via_pymupdf4llm),
        ("docling", _via_docling),
        ("pypdf", _via_pypdf),
    ):
        try:
            md, pages, warns = fn(path)
        except _EngineMissing:
            tried.append(name)
            continue
        return Extracted(md, name, pages, warns)

    raise RuntimeError(
        "没有可用的 PDF 解析器。请任选其一安装：\n"
        "  pip install pymupdf4llm      # 推荐，快且保留结构\n"
        "  pip install docling          # 质量最高，需下载模型\n"
        "  pip install pypdf            # 最轻，仅纯文本"
    )


def _via_pymupdf4llm(path: Path) -> tuple[str, int, list[str]]:
    try:
        import pymupdf4llm
    except ImportError as exc:
        raise _EngineMissing from exc

    md = pymupdf4llm.to_markdown(str(path), show_progress=False)
    pages = 0
    try:
        import fitz

        with fitz.open(str(path)) as doc:
            pages = doc.page_count
    except Exception:
        pass
    return md, pages, []


def _via_docling(path: Path) -> tuple[str, int, list[str]]:
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as exc:
        raise _EngineMissing from exc

    result = DocumentConverter().convert(str(path))
    doc = result.document
    md = doc.export_to_markdown()
    pages = len(getattr(doc, "pages", {}) or {})
    return md, pages, []


def _via_pypdf(path: Path) -> tuple[str, int, list[str]]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise _EngineMissing from exc

    reader = PdfReader(str(path))
    blocks: list[str] = []
    for i, page in enumerate(reader.pages, 1):
        raw = page.extract_text() or ""
        raw = re.sub(r"[ \t]+\n", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw).strip()
        blocks.append(f"## Page {i}\n\n{raw}" if raw else f"## Page {i}\n\n(无文本层)")

    warnings = [
        "使用 pypdf 兜底：仅抽取纯文本，标题层级、表格、公式全部丢失。",
        "扫描件（无文本层）需要先 OCR，或改用 docling / pymupdf4llm。",
    ]
    return "\n\n".join(blocks), len(reader.pages), warnings
