"""把《化工原理》分章题库草稿汇编成四套题库网页。

    python tools/build_hgyl.py            # 生成四套，写到 out_hgyl/
    python tools/build_hgyl.py --list     # 只看会出哪几套、各多少题

草稿在 papers_hgyl/ch0N.json，证据回到 corpus_hgyl/ch0N.md 逐字核对；
页码引用写成 P123，侧栏与出处显示成「第 123 页」。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pdfquiz import amcbank  # noqa: E402
from pdfquiz.render_html import render_html  # noqa: E402
from pdfquiz.verify import Report, verify  # noqa: E402

import examples  # noqa: E402
import hgyl  # noqa: E402

PAPERS = ROOT / "papers_hgyl"
CORPUS = ROOT / "corpus_hgyl"
OUT = ROOT / "out_hgyl"

DECKS = [
    {
        "id": "objective",
        "title": "化工原理 · 客观题专练",
        "desc": "单选、多选、判断按章排，覆盖流体流动、分离、传热、吸收、蒸馏、干燥与蒸发。每题都能翻回教材页码核对原句。",
        "kinds": ("single", "multiple", "truefalse"),
    },
    {
        "id": "practice",
        "title": "化工原理 · 分章精练",
        "desc": "填空加简答：先填公式里的关键量，再用人话把机理、设备与操作要点讲一遍。",
        "kinds": ("fill", "short"),
    },
    {
        "id": "terms",
        "title": "化工原理 · 术语与概念",
        "desc": "把沉降、过滤、传热、吸收、精馏、干燥的核心名词逐个过：先自己写释义，再对照教材原句自评。",
        "kinds": ("term",),
    },
    {
        "id": "exam",
        "title": "化工原理 · 期末模拟卷",
        "desc": "单选 20、多选 4、判断 8、填空 4、简答 3 题，满分 100，限时 120 分钟，按章轮转抽题。",
        "kinds": (),
        "scores": {"single": 2, "multiple": 3, "truefalse": 2, "fill": 2, "short": 8},
        "pick": {"single": 20, "multiple": 4, "truefalse": 8, "fill": 4, "short": 3},
    },
]


def section_of(stem: str, ref: str) -> str:
    m = re.search(r"(\d+)", str(ref))
    return hgyl.section_of(stem, int(m.group(1))) if m else "未分节"


def load_chapters(skip_missing: bool = False) -> tuple[list[dict], dict[str, str]]:
    chapters, corpora = [], {}
    for stem in hgyl.ORDER:
        f = PAPERS / f"{stem}.json"
        if not f.exists():
            if skip_missing:
                print(f"跳过 {stem}：还没有草稿")
                continue
            raise SystemExit(f"缺草稿：{f}")
        data = amcbank.load(f)
        data["_stem"] = stem
        chapters.append(data)
        corpora[stem] = (CORPUS / f"{stem}.md").read_text(encoding="utf-8")
    return chapters, corpora


def questions_of(data: dict) -> list[dict]:
    out = []
    chapter = data.get("chapter", "")
    stem = data["_stem"]
    for q in data["questions"]:
        item = dict(q)
        kind = item["type"]
        ref = str(item.get("ref", ""))
        item["chunk_path"] = f"{chapter} > {section_of(stem, ref)}"
        num = re.search(r"(\d+)", ref)
        item["ref"] = f"第 {num.group(1)} 页" if num else ref
        item.setdefault("score", hgyl.SCORE[kind])
        item["_kind"] = kind
        item["_chapter"] = chapter
        item["_stem"] = stem
        out.append(item)
    return out


def verified(chapters: list[dict], corpora: dict[str, str]) -> tuple[list[dict], list[dict]]:
    accepted, rejected = [], []
    for data in chapters:
        stem = data["_stem"]
        report: Report = verify(questions_of(data), corpora[stem])
        for q in report.accepted:
            if not str(q.get("explanation", "")).strip():
                rejected.append({"question": q["question"], "reason": f"{stem} 缺 explanation"})
                continue
            accepted.append(q)
        for r in report.rejected:
            rejected.append({"question": r["question"], "reason": f"{stem} {r['reason']}"})
    return accepted, rejected


def balanced(items: list[dict], take: int, offset: int) -> list[dict]:
    """同一章内优先挑答案字母不同的题，避免整卷答案扎堆。"""
    groups: dict[str, list[dict]] = {}
    for q in items:
        groups.setdefault(str(q.get("answer", "")), []).append(q)
    keys = sorted(groups)
    picked: list[dict] = []
    j = 0
    while len(picked) < take and any(groups[x] for x in keys):
        x = keys[(offset + j) % len(keys)]
        if groups[x]:
            picked.append(groups[x].pop(0))
        j += 1
    return picked


def spread(pool: list[dict], n: int) -> list[dict]:
    """按章均匀抽题：题少时隔章取，题多时每章先保底再摊余数。"""
    buckets: dict[str, list[dict]] = {}
    for q in pool:
        buckets.setdefault(q["_stem"], []).append(q)
    order = [k for k in hgyl.ORDER if k in buckets]
    if not order or n <= 0:
        return []
    if n < len(order):
        quotas = {order[int((i + 0.5) * len(order) / n)]: 1 for i in range(n)}
    else:
        base, extra = divmod(n, len(order))
        quotas = {k: base for k in order}
        for i in range(extra):
            quotas[order[int((i + 0.5) * len(order) / extra)]] += 1
    out: list[dict] = []
    for ci, k in enumerate(order):
        take = min(quotas.get(k, 0), len(buckets[k]))
        if take:
            out.extend(balanced(buckets[k], take, ci))
    if len(out) < n:
        chosen = {id(q) for q in out}
        for k in order:
            for q in buckets[k]:
                if len(out) >= n:
                    break
                if id(q) not in chosen:
                    out.append(q)
                    chosen.add(id(q))
    return out[:n]


def sort_key(q: dict) -> tuple:
    stem = q["_stem"]
    sec = q["chunk_path"].split(">")[-1].strip()
    names = [name for _, name in hgyl.SECTIONS.get(stem, [])]
    si = names.index(sec) if sec in names else 99
    m = re.search(r"(\d+)", str(q.get("ref", "")))
    return (hgyl.ORDER.index(stem), si, int(m.group(1)) if m else 0, q["_kind"])


def deck_questions(deck: dict, pool: list[dict]) -> list[dict]:
    if deck.get("pick"):
        picked = []
        for kind, n in deck["pick"].items():
            got = spread([q for q in pool if q["_kind"] == kind], n)
            if len(got) < n:
                print(f"  提醒：{deck['id']} 的 {kind} 只凑到 {len(got)}/{n} 题")
            for q in got:
                q = dict(q)
                q["score"] = deck["scores"][kind]
                picked.append(q)
        return picked
    return sorted([q for q in pool if q["_kind"] in deck["kinds"]], key=sort_key)


def tally(qs: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for q in qs:
        out[q["type"]] = out.get(q["type"], 0) + 1
    return out


def main(argv: list[str]) -> int:
    if not CORPUS.exists():
        print("缺 corpus_hgyl/（教材语料不入库），跳过重建，沿用 docs/ 里已发布的页面")
        return 0
    chapters, corpora = load_chapters("--skip-missing" in argv)
    pool, rejected = verified(chapters, corpora)

    if rejected:
        print(f"证据核对退回 {len(rejected)} 题：")
        for r in rejected:
            print(f"  ✗ {r['question'][:40]} —— {r['reason']}")
        return 1

    OUT.mkdir(exist_ok=True)
    meta = []
    for deck in DECKS:
        qs = deck_questions(deck, pool)
        if not qs:
            print(f"跳过 {deck['id']}：没有可用题目")
            continue
        score = sum(int(q.get("score") or 0) for q in qs)
        if "--list" in argv:
            print(f"{deck['id']:10s} {len(qs):3d} 题 {score:4d} 分  {deck['title']}")
            continue
        html = render_html(
            title=deck["title"],
            engine="教材 OCR 全文 + 逐字回查",
            source=hgyl.SOURCE,
            chunks=len(corpora),
            reports=[Report(accepted=qs)],
            mock=False,
            hub="hgyl.html",
            hub_label="返回课程",
            generated="",
        )
        (OUT / f"{deck['id']}.quiz.html").write_text(html, encoding="utf-8")
        meta.append({
            "id": deck["id"],
            "title": deck["title"],
            "desc": deck["desc"],
            "count": len(qs),
            "score": score if deck["id"] == "exam" else 0,
            "types": tally(qs),
        })
        print(f"{deck['id']:10s} {len(qs):3d} 题 {score:4d} 分 → out_hgyl/{deck['id']}.quiz.html")

    if "--list" in argv:
        print(f"总题池 {len(pool)} 题")
        return 0

    ex_total = examples.total()
    if ex_total:
        meta.append({
            "id": "examples",
            "title": "化工原理 · 教材例题精解",
            "short": "例题",
            "desc": f"教材正文 {ex_total} 道例题按章收在一起：先自己做一遍，再展开解答对照步骤；每题标印刷页码，可翻回原书核对。",
            "count": ex_total,
            "score": 0,
            "types": {},
            "quiz": False,
            "unit": "例",
        })
        print(f"examples   {ex_total:3d} 例         → out_hgyl/examples.quiz.html")

    (OUT / "decks.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"题池 {len(pool)} 题，四套共 {sum(m['count'] for m in meta if m.get('quiz', True))} 题")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))