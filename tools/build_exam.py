"""把讲义语料汇编成多套题库（网页 + Markdown）。

用法：
    python tools/build_exam.py              # 全部卷子
    python tools/build_exam.py exam_a       # 只构建指定的几套
    python tools/build_exam.py --list       # 看有哪些卷子

卷子：
    exam_a    期末模拟卷 A（人工出题，分值与题型对齐考试）
    exam_b    期末模拟卷 B（平行卷：题型分值同 A，题目不同）
    practice  分单元精练（每单元 4 句翻译 + 2 问答 + 1 描述 + 8 个术语）
    notes     教材重点句对照（Notes 里的重点句 + 教材原译）
    terms     术语默写总表（词汇表里在正文出现过的全部单词与短语）

所有题都要过 verify：evidence 必须能在教材原文里逐字找到，找不到就丢，
并打印原因，不静默忽略。
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
PAPERS = ROOT / "papers"
OUT = ROOT / "out_exam"

UNIT_ORDER = ["unit01", "unit02", "unit03", "unit06", "unit07",
              "unit10", "unit16", "unit17", "unit22", "unit29"]

TYPE_ORDER = ["trans_en_cn", "trans_cn_en", "describe", "qa", "term",
              "single", "multiple", "truefalse", "fill", "short"]

DEFAULTS = {
    "trans_en_cn": ("理解", "medium"),
    "trans_cn_en": ("记忆", "easy"),
    "describe": ("应用", "medium"),
    "qa": ("分析", "hard"),
    "term": ("记忆", "easy"),
}


# ---------------------------------------------------------------- 语料


def load_units() -> dict[str, str]:
    out = {}
    for stem in UNIT_ORDER:
        f = UNITS_DIR / f"{stem}.md"
        if f.exists():
            out[stem] = f.read_text(encoding="utf-8")
    return out


def split_body(md: str) -> str:
    """只要正文，不要词汇表与注释——术语题的高频统计必须基于正文。

    保留 `### pN` 页标记：句子切分要以页为界。跨页拼接出来的“句子”在原文里
    并不连续，拿它当 evidence 会过不了逐字回查（旧版本的坑）。
    """
    m = re.search(r"^## 正文(.*?)^## Words", md, re.M | re.S)
    body = m.group(1) if m else md
    body = re.sub(r"^>.*$", "", body, flags=re.M)                       # 插图说明/脚注
    body = re.sub(r"^\d{1,3}\s+\*\*.{0,80}?\*\*\s*$", "", body, flags=re.M)  # 页眉「170 **UNIT 3 …**」
    return body


def clean_md(md: str) -> str:
    t = re.sub(r"^\|.*$", "", md, flags=re.M)          # 表格行
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.M)        # 标题
    t = re.sub(r"\*{1,2}|_{1,2}", "", t)                # 强调符
    t = re.sub(r"\$\$?.*?\$\$?", "", t, flags=re.S)      # 公式
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def unit_title(md: str, stem: str) -> str:
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
    part = part_of_unit(num)
    title = titles.get(num, "")
    if part and title:
        return f"{part} > {title}"
    return title or fallback


# ---------------------------------------------------------------- 术语题


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
    """按页切句。跨页拼出来的句子在原文中并不连续，不能当依据。"""
    out: list[str] = []
    for chunk in re.split(r"^###.*$", body, flags=re.M):
        flat = re.sub(r"\s+", " ", chunk)
        parts = re.split(r"(?<=[.;!?])\s+", flat)
        out += [p.strip() for p in parts if len(p.strip()) > 30]
    return out


def _first_meaning(raw: str) -> str:
    """教材释义常写成“性能,行为”“溶解[度];溶液”，只取第一个义项。"""
    meaning = re.sub(r"\[[^\]]*\]", "", raw)
    meaning = re.split(r"[;；]", meaning)[0]
    meaning = re.split(r"[,，]", meaning)[0].strip()
    return meaning


def make_term_questions(
    units: dict[str, str],
    titles: dict[int, str] | None = None,
    per_unit: int | None = 5,
    phrases: str | None = None,
) -> list[dict]:
    """从词汇表生成「中译英 · 术语」。

    per_unit=None 表示不设上限。短语（phrases="hit"）只取正文里出现过的，
    这样 evidence 能落在正文句子上，而不是词汇表行。
    """
    out: list[dict] = []
    used: set[str] = set()
    for stem, md in units.items():
        body = split_body(md)
        sents = sentences(body)
        low = " " + re.sub(r"\s+", " ", body).lower() + " "
        num = int(stem[4:])
        title = (titles or {}).get(num) or unit_title(md, stem)
        path = canonical_path(num, {num: title})

        rows = parse_vocab(md)
        scored = []
        for row in rows:
            term = row["term"].strip()
            if " " in term or len(term) < 4 or term.lower() in used:
                continue
            n = low.count(" " + term.lower() + " ")
            if n <= 0:
                continue
            ev = next((s for s in sents if term.lower() in s.lower()), "")
            if ev:
                scored.append((n, term, row, ev))
        scored.sort(key=lambda x: (-x[0], x[1]))
        picked = scored if per_unit is None else scored[:per_unit]

        for _, term, row, ev in picked:
            meaning = _first_meaning(row["meaning"])
            if len(meaning) < 2 or term.lower() in used:
                continue
            used.add(term.lower())
            out.append({
                "type": "term",
                "chunk_path": path,
                "score": 1,
                "question": meaning,
                "answer": term,
                "keys": [{"en": term, "cn": meaning}],
                "ref": f"{title} · 词汇表",
                "evidence": ev,
                "explanation": f"词性 {row['pos']}；教材原释义：{row['meaning']}",
            })

        if phrases:
            for row in rows:
                term = row["term"].strip()
                if " " not in term or len(term) < 6 or term.lower() in used:
                    continue
                if low.count(term.lower()) <= 0:
                    continue
                ev = next((s for s in sents if term.lower() in s.lower()), "")
                if not ev:
                    continue
                meaning = _first_meaning(row["meaning"])
                if len(meaning) < 2:
                    continue
                used.add(term.lower())
                out.append({
                    "type": "term",
                    "chunk_path": path,
                    "score": 1,
                    "question": meaning,
                    "answer": term,
                    "keys": [{"en": term, "cn": meaning}],
                    "ref": f"{title} · 词汇表（短语）",
                    "evidence": ev,
                    "explanation": f"短语；教材原释义：{row['meaning']}",
                })
    return out


# ---------------------------------------------------------------- 卷子组装


def load_paper(name: str) -> dict | None:
    f = PAPERS / f"{name}.json"
    if not f.exists():
        print(f"  ! 找不到 {f.name}，跳过")
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def norm_sentence(s: str) -> str:
    return re.sub(r"\W+", "", str(s or "")).lower()[:70]


def fill_defaults(qs: list[dict]) -> list[dict]:
    for q in qs:
        bloom, diff = DEFAULTS.get(q.get("type", ""), ("理解", "medium"))
        q.setdefault("bloom", bloom)
        q.setdefault("difficulty", diff)
    return qs


def unit_items(units_dir: Path) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for f in sorted(units_dir.glob("unit*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        out[int(data["unit"])] = data
    return out


def q_from_trans(item: dict, unit: dict, path: str) -> dict:
    return {
        "type": "trans_en_cn",
        "chunk_path": path,
        "score": 5,
        "question": item["en"].strip(),
        "answer": item["cn"].strip(),
        "keys": item.get("keys") or [],
        "ref": f"{unit.get('title', '')} · 精练",
        "evidence": item["en"].strip(),
    }


def q_from_pair(item: dict, unit: dict, path: str, qtype: str, score: int) -> dict:
    return {
        "type": qtype,
        "chunk_path": path,
        "score": score,
        "question": item["q"].strip(),
        "answer": item["a"].strip(),
        "keys": item.get("keys") or [],
        "ref": f"{unit.get('title', '')} · 精练",
        "evidence": item.get("ev", "").strip(),
    }


def build_practice_and_b(
    units: dict[str, str],
    titles: dict[int, str],
    units_dir: Path,
    seen: set[str],
) -> tuple[list[dict], list[dict]]:
    """把每单元 6 翻译 / 3 问答 / 2 描述 拆两批：
    前 4+2+1 进精练卷，其余进 B 卷候选池。同一句不会同时出现在两张卷子里。
    """
    data = unit_items(units_dir)
    practice: list[dict] = []
    pool_trans: list[tuple[int, dict]] = []
    pool_qa: list[tuple[int, dict]] = []
    pool_desc: list[tuple[int, dict]] = []

    for num in sorted(data):
        u = data[num]
        path = canonical_path(num, titles)
        trans = [t for t in u.get("trans", []) if norm_sentence(t.get("en")) not in seen]
        qa = [x for x in u.get("qa", []) if norm_sentence(x.get("ev")) not in seen]
        desc = [x for x in u.get("describe", []) if norm_sentence(x.get("ev")) not in seen]

        for t in trans[:4]:
            practice.append(q_from_trans(t, u, path))
            seen.add(norm_sentence(t["en"]))
        pool_trans += [(num, t) for t in trans[4:]]

        for x in qa[:2]:
            practice.append(q_from_pair(x, u, path, "qa", 5))
            seen.add(norm_sentence(x["ev"]))
        pool_qa += [(num, x) for x in qa[2:]]

        for x in desc[:1]:
            practice.append(q_from_pair(x, u, path, "describe", 5))
            seen.add(norm_sentence(x["ev"]))
        pool_desc += [(num, x) for x in desc[1:]]

    def pick(pool: list[tuple[int, dict]], k: int, prefer: list[int]) -> list[tuple[int, dict]]:
        """每个单元先取一条，取不满再回头补，保证覆盖面。"""
        order = [n for n in prefer if any(n == p[0] for p in pool)]
        order += [n for n, _ in pool if n not in order]
        got: list[tuple[int, dict]] = []
        for rnd in range(3):
            for num in order:
                if len(got) >= k:
                    return got
                cands = [item for n, item in pool if n == num]
                if rnd < len(cands):
                    got.append((num, cands[rnd]))
        return got[:k]

    b_trans = pick(pool_trans, 12, [3, 10, 1, 2, 6, 7, 16, 17, 22, 29])
    b_desc = pick(pool_desc, 3, [1, 10, 16, 22, 29, 3, 6, 7, 2, 17])
    b_qa = pick(pool_qa, 3, [3, 7, 22, 2, 17, 6, 1, 10, 16, 29])

    b: list[dict] = []
    for num, t in b_trans:
        b.append(q_from_trans(t, data[num], canonical_path(num, titles)))
    for num, x in b_desc:
        b.append(q_from_pair(x, data[num], canonical_path(num, titles), "describe", 5))
    for num, x in b_qa:
        b.append(q_from_pair(x, data[num], canonical_path(num, titles), "qa", 5))
    return practice, b


def order_questions(qs: list[dict]) -> list[dict]:
    def key(q):
        t = TYPE_ORDER.index(q["type"]) if q["type"] in TYPE_ORDER else 99
        m = re.search(r"UNIT\s*(\d+)", str(q.get("chunk_path", "")), re.I)
        return (t, int(m.group(1)) if m else 999)
    return sorted(qs, key=key)


# ---------------------------------------------------------------- 教材整理稿


def build_textbook(units: dict[str, str]) -> str:
    heads = {
        "unit01": "UNIT 1 What are Polymers?（书页 1-6）",
        "unit02": "UNIT 2 Chain Polymerization（书页 7-10）",
        "unit03": "UNIT 3 Step Growth Polymerization（书页 11-20）",
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
        md = re.sub(r"^# .*$", "", md, count=1, flags=re.M)
        out.append(f"## {heads.get(stem, stem)}")
        out.append(md.strip())
        out.append("")

    return "\n".join(out)


# ---------------------------------------------------------------- 主流程


DECKS = [
    ("exam_key", "考前重点卷", "按老师「2.1 考前复习」：每单元重点句 + 强调词汇 + Notes，分值 60/10/15/15"),
    ("objective", "客观题专练", "填空挖自教材原句、选项全取词汇表，对齐考试的客观题部分"),
    ("materials", "高分子材料名称默写", "PPT 指定重中之重：常见材料名称中译英"),
    ("exam_a", "期末模拟卷 A", "人工出题，分值与题型对齐考试；附核心术语"),
    ("exam_b", "期末模拟卷 B", "平行卷：题型分值同 A，题目全部不同"),
    ("practice", "分单元精练", "每单元 4 句翻译 + 2 问答 + 1 描述 + 8 个术语"),
    ("notes", "教材重点句对照", "Notes 里的重点句，配教材给出的原译"),
    ("terms", "术语默写总表", "词汇表里在正文出现过的全部单词与短语"),
]


def main(argv: list[str]) -> int:
    if "--list" in argv:
        for name, title, desc in DECKS:
            print(f"{name:9s} {title:12s} {desc}")
        return 0

    want = [a for a in argv if not a.startswith("-")]
    units = load_units()
    if not units:
        print("找不到 .units/*.md，先完成转录。")
        return 1
    titles = {int(s[4:]): unit_title(md, s) for s, md in units.items()}
    print(f"语料：{len(units)} 个单元，共 {sum(len(v) for v in units.values()):,} 字符")

    source = "\n".join(clean_md(v) for v in units.values()) + "\n" + "\n".join(units.values())

    # 全局去重：同一句原文不出现在两张卷子里
    seen: set[str] = set()
    paper_a = load_paper("exam_a")
    paper_b = load_paper("exam_b")
    notes = load_paper("notes")
    for src in (notes, paper_a):
        for q in (src or {}).get("questions", []):
            seen.add(norm_sentence(q.get("evidence") or q.get("question")))

    practice_items, b_items = build_practice_and_b(units, titles, PAPERS / "units", seen)
    print(f"精练题 {len(practice_items)} 道 · B 卷从单元稿抽到 {len(b_items)} 道")

    decks: dict[str, tuple[str, list[dict]]] = {}

    if paper_a:
        qs = fill_defaults(copy.deepcopy(paper_a["questions"]))
        for q in qs:
            m = re.search(r"UNIT\s*(\d+)", str(q.get("chunk_path", "")), re.I)
            if m:
                q["chunk_path"] = canonical_path(
                    int(m.group(1)), titles, str(q.get("chunk_path", "")).split(">")[-1].strip()
                )
        qs += make_term_questions(units, titles, per_unit=5)
        decks["exam_a"] = (paper_a["meta"]["title"], qs)

    if paper_b:
        qs = fill_defaults(copy.deepcopy(paper_b["questions"])) + fill_defaults(b_items)
        qs += make_term_questions(units, titles, per_unit=5)
        decks["exam_b"] = (paper_b["meta"]["title"], qs)

    decks["practice"] = ("高分子材料工程专业英语 · 分单元精练",
                         fill_defaults(practice_items) + make_term_questions(units, titles, per_unit=8))

    if notes:
        decks["notes"] = ("高分子材料工程专业英语 · 教材重点句对照",
                          fill_defaults(copy.deepcopy(notes["questions"])))

    paper_key = load_paper("exam_key")
    if paper_key:
        qs = fill_defaults(copy.deepcopy(paper_key["questions"]))
        for q in qs:
            m = re.search(r"UNIT\s*(\d+)", str(q.get("chunk_path", "")), re.I)
            if m:
                q["chunk_path"] = canonical_path(
                    int(m.group(1)), titles, str(q.get("chunk_path", "")).split(">")[-1].strip()
                )
        decks["exam_key"] = (paper_key["meta"]["title"], qs)

    for name in ("objective", "materials"):
        paper = load_paper(name)
        if paper:
            decks[name] = (paper["meta"]["title"], fill_defaults(copy.deepcopy(paper["questions"])))

    decks["terms"] = ("高分子材料工程专业英语 · 术语默写总表",
                      make_term_questions(units, titles, per_unit=None, phrases="hit"))

    OUT.mkdir(exist_ok=True)
    summary = []
    for name, title, desc in DECKS:
        if name not in decks or (want and name not in want):
            continue
        deck_title, qs = decks[name]
        qs = order_questions(qs)
        report = verify(qs, source)
        print(f"\n[{name}] {deck_title}")
        print(f"  校验通过 {len(report.accepted)} / {len(qs)}")
        for r in report.rejected[:8]:
            print(f"    丢弃：{r['reason']} ← {r['question'][:48]}")

        md_report = copy.copy(report)
        md_report.accepted = sorted(
            report.accepted,
            key=lambda q: (
                int(m.group(1)) if (m := re.search(r"UNIT\s*(\d+)", str(q.get("chunk_path", "")), re.I)) else 999,
                TYPE_ORDER.index(q["type"]) if q["type"] in TYPE_ORDER else 99,
            ),
        )
        (OUT / f"{name}.quiz.md").write_text(
            render_markdown(title=deck_title, source=paper_a["meta"]["source"], reports=[md_report],
                            engine="逐页识读", chunks=len(units), mock=False),
            encoding="utf-8",
        )
        (OUT / f"{name}.quiz.html").write_text(
            render_html(title=deck_title, engine="逐页识读", source=paper_a["meta"]["source"],
                        chunks=len(units), reports=[report], mock=False, hub="index.html"),
            encoding="utf-8",
        )
        by_type: dict[str, int] = {}
        for q in report.accepted:
            by_type[q["type"]] = by_type.get(q["type"], 0) + 1
        score = sum(int(q.get("score", 0)) for q in report.accepted)
        print(f"  题型 {by_type} · 满分 {score}")
        summary.append({"id": name, "title": deck_title, "desc": desc,
                        "count": len(report.accepted), "score": score, "types": by_type})

    (OUT / "教材整理稿.md").write_text(build_textbook(units), encoding="utf-8")
    (OUT / "decks.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n产物：{OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
