"""文档 -> 结构化 Markdown。

两条判然不同的路径，先探测再决定：

1. 有文字层（原生 PDF）——按质量降序尝试解析器：
       pymupdf4llm  (快，CPU 可跑，保留标题/表格)
       docling      (IBM，MIT，结构化最好，支持 CJK)
       pypdf        (零 ML 兜底，只有纯文本，丢失版式)

2. 无文字层（扫描件）——pymupdf4llm/docling/pypdf 全部无能为力，
   必须走 OCR。见 ocr.py 与 ocr_md.py。

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


def extract(
    path: str | Path,
    *,
    ocr: str = "auto",
    pages: list[int] | None = None,
    dpi: int = 200,
    progress=None,
) -> Extracted:
    """ocr: auto（扫描件自动 OCR）/ off（禁止 OCR）/ force（强制 OCR）。"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"找不到文件：{path}")
    suffix = path.suffix.lower()

    if suffix in PASS_SUFFIX:
        text = path.read_text(encoding="utf-8", errors="ignore")
        return Extracted(text, "passthrough", 0)

    if suffix != ".pdf":
        raise ValueError(f"不支持的格式 {suffix}；支持 .pdf / .md / .txt")

    # 先判断有没有文字层：这决定后面整条路怎么走
    probe = None
    try:
        from .ocr import probe_text_layer

        probe = probe_text_layer(path)
    except Exception:
        probe = None

    scanned = bool(probe and probe["is_scanned"])
    if ocr == "force" or (scanned and ocr != "off"):
        return _via_ocr(path, probe, pages, dpi, progress)

    tried: list[str] = []
    for name, fn in (
        ("pymupdf4llm", _via_pymupdf4llm),
        ("docling", _via_docling),
        ("pypdf", _via_pypdf),
    ):
        try:
            md, npages, warns = fn(path)
        except _EngineMissing:
            tried.append(name)
            continue
        if scanned:
            warns = warns + [
                "检测到这份 PDF 没有文字层（扫描件），但 OCR 被关闭，"
                "抽取结果将为空或不完整。"
            ]
        return Extracted(md, name, npages, warns)

    raise RuntimeError(
        "没有可用的 PDF 解析器。请任选其一安装：\n"
        "  pip install pymupdf4llm      # 推荐，快且保留结构\n"
        "  pip install docling          # 质量最高，需下载模型\n"
        "  pip install pypdf            # 最轻，仅纯文本"
    )


def _via_ocr(
    path: Path,
    probe: dict | None,
    pages: list[int] | None,
    dpi: int,
    progress,
) -> Extracted:
    from .ocr import ocr_pdf
    from .ocr_md import pages_to_markdown

    try:
        page_ocrs = ocr_pdf(path, pages=pages, dpi=dpi, progress=progress)
    except RuntimeError as exc:
        raise RuntimeError(
            f"{exc}\n\n这份 PDF 是扫描件（无文字层），必须 OCR 才能转成文字。"
        ) from exc

    md = pages_to_markdown(page_ocrs, title=path.stem)
    chars = sum(len(p.text) for p in page_ocrs)
    blank = [p.page for p in page_ocrs if len(p.text.strip()) < 20]

    warns = [
        f"扫描件，已走 OCR（{page_ocrs[0].engine if page_ocrs else 'n/a'}）。"
        "识别结果可能有个别错字，尤其是音标与公式。",
    ]
    if blank:
        warns.append(f"有 {len(blank)} 页几乎没识别出文字：{blank[:10]}")
    if chars == 0:
        warns.append("OCR 未识别出任何文字，请检查页图质量或换引擎。")

    return Extracted(md, f"ocr:{page_ocrs[0].engine if page_ocrs else 'n/a'}", len(page_ocrs), warns)


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
