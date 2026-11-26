"""教材例题数据的加载与校验。

例题与题库是两套数据：题库（papers_hgyl/chNN.json）用来组卷考试，例题
（papers_hgyl/examples/chNN.json）只用于「教材例题精解」阅读页，不计入题数。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import hgyl

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "papers_hgyl" / "examples"
FIGDIR = EXAMPLES / "figures"

# 教材正文里的例题数，按章固定；ch08 没有例题
EXPECTED = {
    "ch00": 1,
    "ch01": 27,
    "ch02": 5,
    "ch03": 18,
    "ch04": 2,
    "ch05": 16,
    "ch06": 16,
    "ch07": 8,
    "ch08": 0,
}

FIELDS = ("id", "label", "ref", "topic", "problem", "solution", "answer")
REF = re.compile(r"^P(\d+)$")
# 网页端用 ^{} / _{} 表示上下标；这些 OCR 常见的 ASCII 写法会读错量纲
ASCII_UNITS = re.compile(
    r"(?<![A-Za-z])("
    r"(?:m|cm|mm|dm|km|kg|g|mol|kmol|Pa|W|J|N|s|h|L)[23](?![0-9A-Za-z])"
    r"|(?<!\d)10-\d"
    r"|kg/m3|m3/h|m3/s|m2/s|W/\(m2"
    r"|H2O|CO2|SO2|O2|N2|NH3|H2SO4|CaCO3|NaCl"
    r")"
)
TAG = re.compile(r"</?(?:sup|sub|br|b|i|span|div|p)\b", re.I)
SCRIPT = re.compile(r"[\^_]\{[^{}]*\}")


def strip_scripts(text: str) -> str:
    """去掉已经写成 ^{} / _{} 的上下标，避免把 q_{m2} 里的 m2 误判成裸单位。"""
    return SCRIPT.sub("", text)


def chapter_name(stem: str) -> str:
    return hgyl.CHAPTERS[stem][0]


def page_range(stem: str) -> tuple[int, int]:
    i = hgyl.ORDER.index(stem)
    start = hgyl.CHAPTERS[stem][1]
    end = hgyl.CHAPTERS[hgyl.ORDER[i + 1]][1] - 1 if i + 1 < len(hgyl.ORDER) else hgyl.BOOK_LAST_PAGE
    return start, end


def path_of(stem: str) -> Path:
    return EXAMPLES / f"{stem}.json"


def figures_path(stem: str) -> Path:
    return FIGDIR / f"{stem}.json"


def load_figures(stem: str) -> dict:
    path = figures_path(stem)
    if not path.exists():
        return {"schema": 1, "chapter": chapter_name(stem), "figures": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def load(stem: str) -> dict:
    return json.loads(path_of(stem).read_text(encoding="utf-8"))


def load_all() -> list[tuple[str, dict]]:
    return [(stem, load(stem)) for stem in hgyl.ORDER if path_of(stem).exists()]


def counts() -> dict[str, int]:
    out = {}
    for stem in hgyl.ORDER:
        if path_of(stem).exists():
            out[stem] = len(load(stem).get("examples") or [])
        else:
            out[stem] = 0
    return out


def total() -> int:
    return sum(counts().values())


def validate(stem: str, data: dict) -> list[str]:
    """返回该章的问题清单；空列表表示合格。"""
    errs: list[str] = []
    expected = EXPECTED.get(stem, 0)
    if not isinstance(data, dict):
        return [f"{stem}: 顶层必须是对象"]
    if data.get("schema") != 1:
        errs.append(f"{stem}: schema 应为 1")
    if data.get("chapter") != chapter_name(stem):
        errs.append(f"{stem}: chapter 应为「{chapter_name(stem)}」")
    items = data.get("examples")
    if not isinstance(items, list):
        return errs + [f"{stem}: examples 必须是数组"]
    if len(items) != expected:
        errs.append(f"{stem}: 例题数 {len(items)}，应为 {expected}")
    start, end = page_range(stem)
    chapter_no = int(stem[2:])
    for i, item in enumerate(items, 1):
        tag = f"{stem} 第{i}条"
        if not isinstance(item, dict):
            errs.append(f"{tag}: 必须是对象")
            continue
        for key in FIELDS:
            if not str(item.get(key, "")).strip():
                errs.append(f"{tag}: 缺 {key}")
        if item.get("id") != f"{stem}-ex-{i:03d}":
            errs.append(f"{tag}: id 应为 {stem}-ex-{i:03d}")
        if item.get("label") != f"例{chapter_no}-{i}":
            errs.append(f"{tag}: label 应为 例{chapter_no}-{i}")
        ref = str(item.get("ref", ""))
        m = REF.match(ref)
        if not m:
            errs.append(f"{tag}: ref 应写成 P123，实际 {ref!r}")
        else:
            page = int(m.group(1))
            if not start <= page <= end:
                errs.append(f"{tag}: P{page} 不在本章 {start}–{end} 页范围内")
        topic = str(item.get("topic", ""))
        if len(topic) > 24 or "\n" in topic:
            errs.append(f"{tag}: topic 应是不超过 24 字的单行")
        if "\n" in str(item.get("answer", "")):
            errs.append(f"{tag}: answer 应只占一行")
        for key in ("problem", "solution", "answer", "note"):
            text = str(item.get(key, ""))
            hit = ASCII_UNITS.search(strip_scripts(text))
            if hit:
                errs.append(f"{tag}: {key} 的「{hit.group(0)}」缺少上标，请改成 ^{{}}")
            tag_hit = TAG.search(text)
            if tag_hit:
                errs.append(f"{tag}: {key} 不要写 HTML 标签「{tag_hit.group(0)}」")
        if "[?]" in json.dumps(item, ensure_ascii=False) and not str(item.get("note", "")).strip():
            errs.append(f"{tag}: 有 [?] 但 note 为空，需说明哪里看不清")
    return errs


def validate_all() -> list[str]:
    errs: list[str] = []
    for stem in hgyl.ORDER:
        expected = EXPECTED.get(stem, 0)
        if not path_of(stem).exists():
            if expected:
                errs.append(f"{stem}: 缺文件 {path_of(stem).name}")
            continue
        try:
            data = load(stem)
        except json.JSONDecodeError as exc:
            errs.append(f"{stem}: JSON 解析失败：{exc}")
            continue
        errs.extend(validate(stem, data))
        errs.extend(validate_figures(stem, data))
    return errs


def validate_figures(stem: str, data: dict) -> list[str]:
    """检查例题引用的插图是否都有索引、文件和尺寸。"""
    errs: list[str] = []
    items = data.get("examples") or []
    refs = {
        str(item.get("figure", "")).strip()
        for item in items
        if str(item.get("figure", "")).strip()
    }
    if not refs:
        return errs
    path = figures_path(stem)
    if not path.exists():
        return [f"{stem}: 缺图片索引 figures/{stem}.json（{len(refs)} 张图）"]
    try:
        index = load_figures(stem)
    except json.JSONDecodeError as exc:
        return [f"{stem}: 图片索引 JSON 解析失败：{exc}"]
    if index.get("schema") != 1:
        errs.append(f"{stem}: 图片索引 schema 应为 1")
    if index.get("chapter") != chapter_name(stem):
        errs.append(f"{stem}: 图片索引 chapter 应为「{chapter_name(stem)}」")
    entries = index.get("figures")
    if not isinstance(entries, dict):
        return errs + [f"{stem}: 图片索引 figures 必须是对象"]
    start, end = page_range(stem)
    used: dict[str, str] = {}
    for key in sorted(refs):
        meta = entries.get(key)
        if not isinstance(meta, dict):
            errs.append(f"{stem}: 缺「{key}」的插图")
            continue
        name = str(meta.get("file", ""))
        if not name.endswith(".webp"):
            errs.append(f"{stem}「{key}」: file 应为 .webp 文件")
            continue
        if name in used:
            errs.append(f"{stem}「{key}」: 与「{used[name]}」共用同一文件")
        used[name] = key
        image = FIGDIR / name
        if not image.exists():
            errs.append(f"{stem}「{key}」: 文件不存在 figures/{name}")
        elif image.stat().st_size < 2000:
            errs.append(f"{stem}「{key}」: 图片过小，可能裁错了")
        page = str(meta.get("page", ""))
        m = REF.match(page)
        if not m:
            errs.append(f"{stem}「{key}」: page 应写成 P123，实际 {page!r}")
        elif not start <= int(m.group(1)) <= end:
            errs.append(f"{stem}「{key}」: P{m.group(1)} 不在本章 {start}–{end} 页范围内")
        for dim in ("width", "height"):
            value = meta.get(dim)
            if not isinstance(value, int) or not 100 <= value <= 2000:
                errs.append(f"{stem}「{key}」: {dim} 应是 100–2000 的整数")
    return errs


def normalize_text(text: str) -> str:
    """把 OCR 常见的 ASCII 上下标改成网页写法；只做低风险的机械替换。"""
    s = str(text).replace("℃", "°C")
    s = re.sub(r"(?<=\d)\s*[Xx]\s*(?=\d)", "×", s)
    s = re.sub(r"(?<=\d)\s*oC\b", "°C", s)
    for formula, fixed in (
        ("H2SO4", "H_{2}SO_{4}"),
        ("CaCO3", "CaCO_{3}"),
        ("H2O", "H_{2}O"),
        ("NH3", "NH_{3}"),
        ("CO2", "CO_{2}"),
        ("SO2", "SO_{2}"),
        ("O2", "O_{2}"),
        ("N2", "N_{2}"),
    ):
        s = re.sub(rf"(?<![A-Za-z]){formula}(?![0-9A-Za-z])", fixed, s)
    s = re.sub(r"(?<![A-Za-z])m3(?![0-9A-Za-z])", "m^{3}", s)
    s = re.sub(r"(?<![A-Za-z])m2(?![0-9A-Za-z])", "m^{2}", s)
    s = re.sub(r"(?<![A-Za-z])m-(\d)(?![0-9A-Za-z])", r"m^{-\1}", s)
    s = re.sub(r"(?<!\d)10-(\d)", r"10^{-\1}", s)
    return s