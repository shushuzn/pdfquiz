"""扫描件支持：无文字层 PDF 的页图提取与 OCR。

设计取舍：
- 页图优先取 PDF 内嵌图（多数扫描件是整页一张图，原图信息最完整），
  取不到再退化为 pymupdf 渲染。渲染只是插值放大，不会增加真实信息量。
- OCR 引擎可插拔：rapidocr（中英混排、CPU 可跑）优先，tesseract 兜底。
- 逐页结果落盘缓存。233 页的 OCR 要几分钟，重跑不能从头再来。
"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

# ---------------------------------------------------------------- 数据结构


@dataclass
class Line:
    """版面重组后的一行。cells 是按 x 切出的列块，词汇表靠它还原四列。"""

    y: float
    text: str
    cells: list[str] = field(default_factory=list)
    cols: list[int] = field(default_factory=list)  # 每个 cell 归属的列号

    @property
    def x0(self) -> float:
        return 0.0


@dataclass
class PageOCR:
    page: int  # 1-based PDF 页码
    lines: list[Line]
    engine: str = ""
    width: int = 0
    height: int = 0

    @property
    def text(self) -> str:
        return "\n".join(ln.text for ln in self.lines)

    def to_dict(self) -> dict:
        return {
            "page": self.page,
            "engine": self.engine,
            "width": self.width,
            "height": self.height,
            "lines": [asdict(ln) for ln in self.lines],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PageOCR":
        return cls(
            page=d["page"],
            engine=d.get("engine", ""),
            width=d.get("width", 0),
            height=d.get("height", 0),
            lines=[
                Line(
                    y=ln["y"],
                    text=ln["text"],
                    cells=ln.get("cells", []),
                    cols=ln.get("cols", []),
                )
                for ln in d.get("lines", [])
            ],
        )


# ---------------------------------------------------------------- 文字层探测


def probe_text_layer(pdf_path: str | Path, sample: int = 24) -> dict:
    """判断是否扫描件。返回每页字符数摘要，供上层决策。"""
    import pymupdf

    doc = pymupdf.open(str(pdf_path))
    n = doc.page_count
    # 均匀采样，避免只看到封面或纯图页
    idxs = (
        list(range(n))
        if n <= sample
        else sorted({int(i * (n - 1) / (sample - 1)) for i in range(sample)})
    )
    counts = []
    for i in idxs:
        t = doc[i].get_text().strip()
        counts.append(len(t))
    doc.close()

    nonempty = sum(1 for c in counts if c >= 40)
    return {
        "pages": n,
        "sampled": len(counts),
        "nonempty": nonempty,
        "median_chars": sorted(counts)[len(counts) // 2] if counts else 0,
        "is_scanned": nonempty == 0,
    }


# ---------------------------------------------------------------- 页图提取


def page_images(pdf_path: str | Path, pages: list[int] | None = None, dpi: int = 200):
    """逐页产出 (页码, PIL.Image)。页码 1-based。"""
    import pymupdf
    from PIL import Image

    doc = pymupdf.open(str(pdf_path))
    targets = pages or list(range(1, doc.page_count + 1))

    for pno in targets:
        page = doc[pno - 1]
        img = None

        # 先试内嵌图：整页扫描件通常就是一张图，原分辨率优于任何渲染
        try:
            infos = page.get_images(full=True)
            if len(infos) == 1:
                info = infos[0]
                data = doc.extract_image(info[0])
                cand = Image.open(io.BytesIO(data["image"]))
                # 图基本铺满页面才算整页扫描图，否则（页内插图）改用渲染
                if _covers_page(cand, page):
                    img = cand
        except Exception:
            img = None

        if img is None:
            pix = page.get_pixmap(dpi=dpi)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

        if img.mode != "RGB":
            img = img.convert("RGB")
        yield pno, img

    doc.close()


def _covers_page(img, page) -> bool:
    """内嵌图宽高比接近 A4 且像素量足够，判定为整页扫描图。"""
    w, h = img.size
    if w * h < 500 * 700:
        return False
    page_ratio = page.rect.width / page.rect.height
    img_ratio = w / h
    return abs(page_ratio - img_ratio) < 0.12


# ---------------------------------------------------------------- 版面重组


def group_lines(boxes: list[tuple], tol_ratio: float = 0.55) -> list[Line]:
    """把 OCR 的散框按 y 聚成行，行内按 x 排序并切出列块。

    boxes 元素: (x0, y0, x1, y1, text, score)
    """
    items = []
    for b in boxes:
        x0, y0, x1, y1, txt = b[0], b[1], b[2], b[3], b[4]
        if not str(txt).strip():
            continue
        items.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "text": str(txt)})

    items.sort(key=lambda it: (it["y0"], it["x0"]))

    rows: list[dict] = []
    for it in items:
        cy = (it["y0"] + it["y1"]) / 2
        h = max(1.0, it["y1"] - it["y0"])
        target = None
        for r in rows:
            if abs(r["cy"] - cy) <= max(h, r["h"]) * tol_ratio:
                target = r
                break
        if target is None:
            rows.append({"cy": cy, "h": h, "items": [it], "n": 1})
        else:
            target["cy"] = (target["cy"] * target["n"] + cy) / (target["n"] + 1)
            target["n"] += 1
            target["h"] = max(target["h"], h)
            target["items"].append(it)

    rows.sort(key=lambda r: r["cy"])

    lines: list[Line] = []
    for r in rows:
        cells = sorted(r["items"], key=lambda it: it["x0"])
        cells.sort(key=lambda it: it["x0"])
        texts = [c["text"] for c in cells]
        # 列块间距：相邻块间隔超过行高中位数 1.6 倍，视为换列
        gaps = []
        for a, b in zip(cells, cells[1:]):
            gaps.append(b["x0"] - a["x1"])
        med_h = r["h"]

        pieces: list[str] = []
        split_cells: list[str] = []
        cur = [texts[0]] if texts else []
        for i, g in enumerate(gaps):
            if g > med_h * 1.6:
                split_cells.append(" ".join(cur).strip())
                pieces.append("  ")
                cur = [texts[i + 1]]
            else:
                sep = "" if _touching(pieces, texts, i) else " "
                cur.append(texts[i + 1])
        if cur:
            split_cells.append(" ".join(cur).strip())

        joined = ""
        for i, c in enumerate(split_cells):
            if i:
                joined += "\t"
            joined += c

        lines.append(Line(y=r["cy"], text=joined, cells=split_cells))

    return lines


def _touching(pieces, texts, i) -> bool:
    """中日文之间不加空格。"""
    if i + 1 >= len(texts):
        return False
    if not texts[i] or not texts[i + 1]:
        return True
    a, b = texts[i][-1], texts[i + 1][0]
    return _is_cjk(a) and _is_cjk(b)


def _is_cjk(ch: str) -> bool:
    o = ord(ch)
    return 0x3000 <= o <= 0x9FFF or 0xFF00 <= o <= 0xFFEF


# ---------------------------------------------------------------- OCR 引擎


class OcrEngine:
    """统一封装：返回 (boxes) 供版面重组。"""

    name = "base"

    def recognize(self, img) -> list[tuple]:  # pragma: no cover
        raise NotImplementedError


class RapidOcrEngine(OcrEngine):
    name = "rapidocr"

    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR

        self._cli = RapidOCR()

    def recognize(self, img) -> list[tuple]:
        import numpy as np

        arr = np.array(img)
        res, _ = self._cli(arr)
        out = []
        for item in res or []:
            box, txt, score = item[0], item[1], item[2]
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            out.append((min(xs), min(ys), max(xs), max(ys), txt, score))
        return out


class TesseractEngine(OcrEngine):
    name = "tesseract"

    def __init__(self, lang: str = "eng+chi_sim"):
        import pytesseract

        self._t = pytesseract
        self.lang = lang

    def recognize(self, img) -> list[tuple]:
        data = self._t.image_to_data(
            img, lang=self.lang, output_type=self._t.Output.DICT
        )
        out = []
        n = len(data["text"])
        for i in range(n):
            txt = (data["text"][i] or "").strip()
            if not txt:
                continue
            w, h = data["width"][i], data["height"][i]
            if w <= 1 or h <= 1:
                continue
            x, y = data["left"][i], data["top"][i]
            out.append((x, y, x + w, y + h, txt, float(data["conf"][i]) / 100.0))
        return out


def get_engine(name: str = "auto") -> OcrEngine:
    if name in ("auto", "rapidocr"):
        try:
            return RapidOcrEngine()
        except Exception:
            if name == "rapidocr":
                raise
    try:
        return TesseractEngine()
    except Exception as exc:
        raise RuntimeError(
            "没有可用的 OCR 引擎。请安装 rapidocr-onnxruntime"
            "（pip install rapidocr-onnxruntime）或系统安装 tesseract。"
        ) from exc


# ---------------------------------------------------------------- 缓存与主流程


def _cache_path(cache_dir: Path, pdf_path: Path, page: int, tag: str) -> Path:
    key = hashlib.sha1(
        f"{pdf_path.resolve()}:{pdf_path.stat().st_size}:{page}:{tag}".encode()
    ).hexdigest()[:16]
    return cache_dir / f"{key}.json"


def ocr_pdf(
    pdf_path: str | Path,
    pages: list[int] | None = None,
    engine_name: str = "auto",
    cache_dir: str | Path | None = None,
    dpi: int = 200,
    progress=None,
) -> list[PageOCR]:
    """OCR 指定页（默认全本），带磁盘缓存。"""
    pdf_path = Path(pdf_path)
    cache = Path(cache_dir) if cache_dir else pdf_path.parent / ".ocr_cache"
    cache.mkdir(parents=True, exist_ok=True)

    engine = None
    results: list[PageOCR] = []

    for pno, img in page_images(pdf_path, pages, dpi=dpi):
        tag = f"{engine_name}-{dpi}"
        cp = _cache_path(cache, pdf_path, pno, tag)
        if cp.exists():
            try:
                results.append(PageOCR.from_dict(json.loads(cp.read_text("utf-8"))))
                if progress:
                    progress(pno, "cached")
                continue
            except Exception:
                pass

        if engine is None:
            engine = get_engine(engine_name)

        boxes = engine.recognize(img)
        lines = group_lines(boxes)
        page = PageOCR(
            page=pno,
            lines=lines,
            engine=engine.name,
            width=img.size[0],
            height=img.size[1],
        )
        cp.write_text(json.dumps(page.to_dict(), ensure_ascii=False), "utf-8")
        results.append(page)
        if progress:
            progress(pno, "ocr")

    return results
