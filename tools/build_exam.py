"""把手工出的试卷 + 教材词汇表汇编成题库（Markdown + 网页）。

用法：
    python tools/build_exam.py

做的事：
1. 合并 .units/*.md 作为语料，用于校验每道题的 evidence 是否真出自教材；
2. 读 papers/exam_a.json（人工出题，含译文与采分点）；
3. 从词汇表自动生成「中译英 · 术语速记」题，只取正文中真实出现过的词；
4. 走一遍 verify，被拒的题连同原因一并输出，不静默丢弃；
5. 产出 Markdown 题库、HTML 题库、教材整理稿。
"""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pdfquiz.render import render as render_markdown  # noqa: E402
from pdfquiz.render_html import render_html  # noqa: E402
from pdfquiz.verify import verify  # noqa: E402

UNITS_DIR = ROOT / ".units"
PAPER = ROOT / "papers" / "exam_a.json"
OUT = ROOT / "out_exam"

UNIT_ORDER = [
    "unit01", "unit02", "unit03", "unit06", "unit07",
    "unit10", "unit16", "unit17", "unit22", "unit29",
]
TERMS_PER_UNIT = 5


# ---------------------------------------------------------------- 语料


def load_units() -> dict[str, str]:
    out = {}
    for stem in UNIT_ORDER:
        f = UNITS_DIR / f"{stem}.md"
        if f.exists():
            out[stem] = f.read_text(encoding="utf-8")
    return out


def split_body(md: str) -> str:
    m = re.search(r"^## 正文(.*?)^## Words", md, re.M | re.S)
    body = m.group(1) if m else md
    body = re.sub(r"^>.*$", "", body, flags=re.M)
    body = re.sub(r"^###.*$", "", body, flags=re.M)
    return body


def clean_md(md: str) -> str:
    """去掉 Markdown 标记，保留可读正文，供 evidence 比对与展示。"""
    t = re.sub(r"^\|.*$", "", md, flags=re.M)          # 表格行
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.M)        # 标题
    t = re.sub(r"\*{1,2}|_{1,2}", "", t)                # 强调符
    t = re.sub(r"\$\$?.*?\$\$?", "", t, flags=re.S)      # 公式
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def unit_title(md: str, stem: str) -> str:
    """取单元标题，去掉“（书页 1-6）”这类页码括注。"""
    m = re.search(r"^#\s+(.+)$", md, re.M)
    if m:
        title = re.sub(r"[（(][^）)]*[）)]\s*$", "", m.group(1)).strip()
        if title:
            return title
    return f"UNIT {int(stem[4:])}"


# 目录页的权威划分：PART A = UNIT 1-10，PART B = 11-20，PART C = 21-30
PART_RANGES = (("A", 1, 10), ("B", 11, 20), ("C", 21, 30))
PART_CN = {
    "A": "PART A 高分子化学与物理",
    "B": "PART B 聚合工程",
    "C": "PART C 加工·性能·应用",
}


def part_of_unit(num: int) -> str:
    for key, lo, hi in PART_RANGES:
        if lo <= num <= hi:
            return PART_CN[key]
    return ""


def canonical_path(num: int, titles: dict[int, str], fallback: str = "") -> str:
    """用单元号重建章节路径，消除试卷里 UNIT 3/10/16 的简写差异。"""
    title = titles.get(num) or fallback
    part = part_of_unit(num)
    if part and title:
        return f"{part} > {title}"
    return title or fallback


def parse_vocab(md: str) -> list[dict]:
    """从词汇表还原词条。"""
    m = re.search(r"## Words and Expressions(.*?)(?:\n## |\Z)", md, re.S)
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
    flat = re.sub(r"\s+", " ", body)
    parts = re.split(r"(?<=[.;!?])\s+", flat)
    return [p.strip() for p in parts if len(p.strip()) > 30]


def make_term_questions(units: dict[str, str], titles: dict[int, str] | None = None) -> list[dict]:
    """每单元挑正文高频词做中译英。高频≈核心术语，也贴近“上课强调的词”。

    全局去重：同一个英文词只出一次，否则 dissolve 会在 U1 和 U6 各出一遍。
    """
    out: list[dict] = []
    used: set[str] = set()
    for stem, md in units.items():
        body = split_body(md)
        sents = sentences(body)
        low = " " + re.sub(r"\s+", " ", body).lower() + " "

        scored = []
        for row in parse_vocab(md):
            term = row["term"].strip()
            if len(term) < 4 or " " in term:
                continue  # 只取单词，短语另有机会
            if term.lower() in used:
                continue
            n = low.count(" " + term.lower() + " ")
            if n <= 0:
                continue
            ev = next((s for s in sents if term.lower() in s.lower()), "")
            if not ev:
                continue
            scored.append((n, term, row, ev))

        scored.sort(key=lambda x: (-x[0], x[1]))
        picked = 0
        for n, term, row, ev in scored:
            if term.lower() in used:
                continue
            meaning = re.sub(r"\[[^\]]*\]", "", row["meaning"])
            # 取第一个义项：教材常写成“性能,行为”“溶解[度];溶液”，全塞进题干会看不懂
            meaning = re.split(r"[;；]", meaning)[0]
            meaning = re.split(r"[,，]", meaning)[0].strip()
            if len(meaning) < 2:
                continue
            used.add(term.lower())
            picked += 1
            num = int(stem[4:])
            title = (titles or {}).get(num) or unit_title(md, stem)
            out.append(
                {
                    "type": "term",
                    # 与人工题共用同一套章节路径，结果页与侧栏才不会把
                    # 同一个单元拆成“UNIT 1 …”和“第 01 单元”两行
                    "chunk_path": canonical_path(num, {num: title}),
                    "score": 1,
                    "question": meaning,
                    "answer": term,
                    "keys": [{"en": term, "cn": meaning}],
                    "ref": f"{title} · 词汇表",
                    "evidence": ev,
                    "explanation": f"词性 {row['pos']}；教材原释义：{row['meaning']}",
                }
            )
            if picked >= TERMS_PER_UNIT:
                break
    return out


# ---------------------------------------------------------------- 教材整理稿


def build_textbook(units: dict[str, str]) -> str:
    heads = {
        "unit01": "UNIT 1 What are Polymers?（书页 1-6）",
        "unit02": "UNIT 2 Chain Polymerization（书页 7-10）",
        "unit03": "UNIT 3 Step-Growth Polymerization（书页 11-20）",
        "unit06": "UNIT 6 Polymer Solution（书页 34-40）",
        "unit07": "UNIT 7 Morphology of Solid Polymers（书页 41-47）",
        "unit10": "UNIT 10 Preparations of Amino Resins in Laboratory（书页 61-68）",
        "unit16": "UNIT 16 Copolymer Composition Distributions Affected by Micromixing（书页 102-108）",
        "unit17": "UNIT 17 Introduction to Modelling of Polymerization Kinetics（书页 109-115）",
        "unit22": "UNIT 22 Mechanical Properties of Polymers（书页 143-147）",
        "unit29": "UNIT 29 Synthetic Plastics（书页 182-188）",
    }
    out = [
        "# 高分子材料工程专业英语 · 复习范围整理稿",
        "",
        "> 由原书扫描页逐页识读整理，仅收录期末复习范围内的 10 个单元。",
        "> 页码为书内印刷页码；原书 PDF 页码 = 书内页码 + 5（前 5 页为封面、版权、前言与目录）。",
        "> 识读过程中无法辨认的个别字符以 `[?]` 标注，未作臆测补全。",
        "",
        "## 目录",
        "",
    ]
    for stem in UNIT_ORDER:
        if stem in units:
            t = heads.get(stem, stem)
            out.append(f"- [{t}](#{t.lower().replace(' ', '-')})")
    out.append("")

    for stem in UNIT_ORDER:
        if stem not in units:
            continue
        md = units[stem]
        # 去掉原文件的一级标题，统一用二级
        md = re.sub(r"^# .*$", "", md, count=1, flags=re.M)
        out.append(f"## {heads.get(stem, stem)}")
        out.append(md.strip())
        out.append("")

    return "\n".join(out)


# ---------------------------------------------------------------- main


def main() -> int:
    units = load_units()
    if not units:
        print("找不到 .units/*.md，先完成转录。")
        return 1

    print(f"语料：{len(units)} 个单元，共 {sum(len(v) for v in units.values()):,} 字符")

    paper = json.loads(PAPER.read_text(encoding="utf-8"))
    manual = paper["questions"]
    # 认知层次与难度：按题型给默认值，缺失时才填，不覆盖人工标注
    DEFAULTS = {
        "trans_en_cn": ("理解", "medium"),
        "trans_cn_en": ("记忆", "easy"),
        "describe": ("应用", "medium"),
        "qa": ("分析", "hard"),
    }
    for q in manual:
        bloom, diff = DEFAULTS.get(q["type"], ("理解", "medium"))
        q.setdefault("bloom", bloom)
        q.setdefault("difficulty", diff)

    # 单元 → 标题以教材目录为准；试卷里的简写（如 Step-Growth / 缺 “in Laboratory”）
    # 统一按单元号重建，避免同一单元被拆成两个分组
    titles: dict[int, str] = {}
    for stem, md in units.items():
        titles[int(stem[4:])] = unit_title(md, stem)

    for q in manual:
        m = re.search(r"UNIT\s*(\d+)", str(q.get("chunk_path", "")), re.I)
        if m:
            q["chunk_path"] = canonical_path(int(m.group(1)), titles, str(q.get("chunk_path", "")).split(">")[-1].strip())

    terms = make_term_questions(units, titles)
    for q in terms:
        q.setdefault("bloom", "记忆")
        q.setdefault("difficulty", "easy")
    print(f"人工题 {len(manual)} 道 · 术语题 {len(terms)} 道")

    source = "\n".join(clean_md(v) for v in units.values())
    # 词汇表单独并入语料，术语题的 evidence 才能落在这里
    source += "\n" + "\n".join(v for v in units.values())

    all_q = manual + terms
    report = verify(all_q, source)
    print(f"校验通过 {len(report.accepted)} / {len(all_q)}")
    for r in report.rejected[:12]:
        print(f"  丢弃：{r['reason']} ← {r['question'][:40]}")

    OUT.mkdir(exist_ok=True)
    title = paper["meta"]["title"]

    # Markdown 版按单元顺序重排：题库按题型分两批追加，不排会把同一单元打散成两段，
    # 打印出来像两套目录。网页版保持试卷的题型顺序，两者编号因此不同。
    md_report = copy.copy(report)
    order = {t: i for i, t in enumerate(["trans_en_cn", "trans_cn_en", "describe", "qa", "term"])}
    md_report.accepted = sorted(
        report.accepted,
        key=lambda q: (
            int(re.search(r"UNIT\s*(\d+)", str(q.get("chunk_path", "")), re.I).group(1))
            if re.search(r"UNIT\s*(\d+)", str(q.get("chunk_path", "")), re.I)
            else 999,
            order.get(str(q.get("type")), 99),
        ),
    )

    md = render_markdown(
        title=title,
        source=paper["meta"]["source"],
        reports=[md_report],
        engine="逐页识读",
        chunks=len(units),
        mock=False,
    )
    (OUT / "exam_a.quiz.md").write_text(md, encoding="utf-8")

    html = render_html(
        title=title,
        engine="逐页识读",
        source=paper["meta"]["source"],
        chunks=len(units),
        reports=[report],
        mock=False,
    )
    (OUT / "exam_a.quiz.html").write_text(html, encoding="utf-8")

    tb = build_textbook(units)
    (OUT / "教材整理稿.md").write_text(tb, encoding="utf-8")

    acc = report.accepted
    by_type: dict[str, int] = {}
    for q in acc:
        by_type[q["type"]] = by_type.get(q["type"], 0) + 1
    score = sum(int(q.get("score", 0)) for q in acc)
    print("题型分布：", by_type)
    print(f"总分：{score}")
    print(f"产物：{OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
