"""把分章题库草稿汇编成《先进材料研究进展C》的四套题库网页。

    python tools/build_amc.py            # 生成全部四套，写到 out_amc/
    python tools/build_amc.py --list     # 只看会出哪几套、各多少题

草稿在 papers_amc/ch0N.json，按题型分组；证据一律回到 corpus_amc/ch0N.md
逐字核对（和 build_exam 同一套 verify），对不上就退回并打印原因。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pdfquiz.render_html import render_html  # noqa: E402
from pdfquiz.verify import Report, verify  # noqa: E402

COURSE_NAME = "先进材料研究进展C"
PAPERS = ROOT / "papers_amc"
CORPUS = ROOT / "corpus_amc"
OUT = ROOT / "out_amc"

CHAPTERS = ["ch01", "ch02", "ch03", "ch04", "ch05", "ch06", "ch07", "ch08", "ch09", "ch10"]

SCORE = {"single": 2, "multiple": 3, "truefalse": 2, "fill": 2, "short": 10, "term": 2}

DECKS = [
    {
        "id": "objective",
        "title": f"{COURSE_NAME} · 客观题专练",
        "desc": "单选、多选、判断全覆盖，考点按章节顺序排。题干里的每个说法都能在课件原句里找到出处。",
        "kinds": ("single", "multiple", "truefalse"),
    },
    {
        "id": "practice",
        "title": f"{COURSE_NAME} · 分章精练",
        "desc": "填空加简答，按章分组：先填关键参数，再用自己的话把机理讲一遍。",
        "kinds": ("fill", "short"),
    },
    {
        "id": "terms",
        "title": f"{COURSE_NAME} · 术语与概念",
        "desc": "概论、仿生、木材、电催化、储能与碳材料的名词逐个过，答完对着课件原句核一遍。",
        "kinds": ("term",),
    },
    {
        "id": "exam",
        "title": f"{COURSE_NAME} · 期末模拟卷",
        "desc": "单选 20、多选 4、判断 8、填空 6、简答 4 题，满分 100。选择与判断按章轮转抽取，限时 90 分钟。",
        "kinds": (),
        "scores": {"single": 2, "multiple": 3, "truefalse": 2, "fill": 2, "short": 5},
        "pick": {"single": 20, "multiple": 4, "truefalse": 8, "fill": 6, "short": 4},
    },
]

SOURCE = "《先进材料研究进展C》课件（课程组）与课程教学大纲"

# 每章按课件目录切成几段，题库侧栏按段分组；页码是幻灯片序号的上界。
SECTIONS = {
    "ch01": [
        (5, "课程导入"),
        (10, "第一节 先进材料的概念与分类"),
        (17, "第二节 先进能源材料发展的必要性"),
        (31, "第三节 发展历程与趋势"),
        (44, "第四节 生物质资源与先进能源材料"),
        (55, "第五节 研究进展的调研方法"),
    ],
    "ch02": [
        (2, "课程导入"),
        (7, "第一节 仿生的起源"),
        (11, "第二节 仿生的诞生"),
        (18, "第三节 仿生与科技创新"),
        (38, "第四节 仿生学基本要素"),
        (48, "第五节 仿生材料的设计及举例"),
        (55, "第六节 天然生物及其仿生材料"),
    ],
    "ch03": [
        (4, "1 木材科技创新势在必行"),
        (17, "2 功能性实体木材"),
        (26, "3 新型木质复合材料"),
        (31, "4 生物质能源材料"),
        (57, "5 木材科学与创新发展"),
    ],
    "ch04": [
        (10, "背景与析氢机理"),
        (17, "评价指标与测试基础"),
        (49, "析氢催化剂"),
        (53, "测试方法与参比电极"),
        (65, "CO₂还原的热力学与路径"),
        (69, "CO₂还原装置与传质"),
        (94, "铜基与掺杂催化剂"),
        (98, "拓展资源"),
    ],
    "ch05": [
        (2, "课程导入"),
        (13, "1 生产与发展"),
        (20, "2 结构与工作原理"),
        (29, "3.1 正极材料"),
        (40, "3.2 负极材料"),
        (44, "4.1 隔膜"),
        (50, "4.2 电解液"),
        (60, "5 电池结构与制作"),
        (83, "Li–O₂ 电池"),
        (102, "Li–S 电池"),
        (114, "锂金属负极"),
    ],
    "ch06": [
        (2, "课程导入"),
        (18, "1.1 概述与分类"),
        (21, "结构与电极材料"),
        (34, "碳电极与赝电容材料"),
        (42, "导电剂、电解液与隔膜"),
        (47, "性能指标与对比"),
        (64, "研究进展"),
        (82, "应用"),
    ],
    "ch07": [
        (2, "课程导入"),
        (24, "一、碳与生活 / 二、碳元素"),
        (47, "碳的杂化与同素异形体"),
        (53, "碳材料的分类"),
        (61, "工业化碳制品"),
        (74, "碳材料的发展"),
    ],
    "ch08": [
        (2, "课程导入"),
        (5, "1.1 什么是活性炭"),
        (35, "1.2 活性炭的发展与应用"),
        (41, "1.3 活性炭的孔结构"),
        (56, "1.4 活性炭的制备与分类"),
        (57, "1.5 思考题"),
        (76, "2 炭黑的生产和应用"),
    ],
    "ch09": [
        (3, "课程导入"),
        (13, "一、碳纤维的结构与设计理念"),
        (37, "三、聚丙烯腈基碳纤维制备"),
        (45, "粘胶基碳纤维"),
        (63, "沥青基碳纤维"),
        (79, "复合材料基本概念"),
        (91, "表面处理与复合工艺"),
    ],
    "ch10": [
        (2, "课程导入"),
        (13, "富勒烯"),
        (45, "碳纳米管"),
        (61, "碳/碳复合材料"),
    ],
}


def section_of(stem: str, ref: str) -> str:
    m = re.search(r"(\d+)", str(ref))
    if not m:
        return "未分节"
    n = int(m.group(1))
    for limit, name in SECTIONS.get(stem, []):
        if n <= limit:
            return name
    return "未分节"


def load_chapters() -> tuple[list[dict], dict[str, str]]:
    chapters, corpora = [], {}
    for stem in CHAPTERS:
        f = PAPERS / f"{stem}.json"
        if not f.exists():
            raise SystemExit(f"缺草稿：{f}")
        data = json.loads(f.read_text(encoding="utf-8"))
        data["_stem"] = stem
        chapters.append(data)
        corpora[stem] = (CORPUS / f"{stem}.md").read_text(encoding="utf-8")
    return chapters, corpora


def questions_of(data: dict) -> list[dict]:
    out = []
    chapter = data.get("chapter", "")
    stem = data["_stem"]
    for kind in ("single", "multiple", "truefalse", "fill", "short", "term"):
        for q in data.get(kind) or []:
            item = dict(q)
            item["type"] = kind
            slide = str(item.get("ref", ""))
            item["chunk_path"] = f"{chapter} > {section_of(stem, slide)}"
            # 侧栏与出处都显示「第 N 页」，比 S12 这种内部编号好读
            num = re.search(r"(\d+)", slide)
            item["ref"] = f"第 {num.group(1)} 页" if num else slide
            item.setdefault("score", SCORE[kind])
            item["_kind"] = kind
            item["_chapter"] = chapter
            item["_stem"] = stem
            out.append(item)
    return out


def verified(chapters: list[dict], corpora: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """按章分别过 verify：证据只在本科课的转录稿里找。"""
    accepted, rejected = [], []
    for data in chapters:
        stem = data["_stem"]
        qs = questions_of(data)
        report: Report = verify(qs, corpora[stem])
        for q in report.accepted:
            if not str(q.get("explanation", "")).strip():
                rejected.append({"question": q["question"], "reason": f"{stem} 缺 explanation"})
                continue
            accepted.append(q)
        for r in report.rejected:
            rejected.append({"question": r["question"], "reason": f"{stem} {r['reason']}"})
    return accepted, rejected


def round_robin(pool: list[dict], n: int) -> list[dict]:
    """按章轮流抽，保证模拟卷每章都有份。"""
    buckets: dict[str, list[dict]] = {}
    for q in pool:
        buckets.setdefault(q["_stem"], []).append(q)
    out: list[dict] = []
    i = 0
    order = [k for k in CHAPTERS if k in buckets]
    while len(out) < n and any(buckets[k] for k in order):
        k = order[i % len(order)]
        if buckets[k]:
            out.append(buckets[k].pop(0))
        i += 1
    return out


def sort_key(q: dict) -> tuple:
    """按章、按节、按页码排，侧栏分组顺序才和课件顺序一致。"""
    stem = q["_stem"]
    sec = q["chunk_path"].split(">")[-1].strip()
    names = [name for _, name in SECTIONS.get(stem, [])]
    si = names.index(sec) if sec in names else 99
    m = re.search(r"(\d+)", str(q.get("ref", "")))
    return (CHAPTERS.index(stem), si, int(m.group(1)) if m else 0, q["_kind"])


def deck_questions(deck: dict, pool: list[dict]) -> list[dict]:
    if deck.get("pick"):
        picked = []
        for kind, n in deck["pick"].items():
            got = round_robin([q for q in pool if q["_kind"] == kind], n)
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
    chapters, corpora = load_chapters()
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
        report = Report(accepted=qs)
        html = render_html(
            title=deck["title"],
            engine="课件转录稿 + 逐字回查",
            source=SOURCE,
            chunks=len(corpora),
            reports=[report],
            mock=False,
            hub="amc.html",
            hub_label="返回课程",
        )
        (OUT / f"{deck['id']}.quiz.html").write_text(html, encoding="utf-8")
        meta.append({
            "id": deck["id"],
            "title": deck["title"],
            "desc": deck["desc"],
            "count": len(qs),
            # 只有模拟卷标满分；其余几套是练习，写「169 分」反而误导
            "score": score if deck["id"] == "exam" else 0,
            "types": tally(qs),
        })
        print(f"{deck['id']:10s} {len(qs):3d} 题 {score:4d} 分 → out_amc/{deck['id']}.quiz.html")

    if "--list" in argv:
        print(f"总题池 {len(pool)} 题")
        return 0

    (OUT / "decks.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"题池 {len(pool)} 题，四套共 {sum(m['count'] for m in meta)} 题")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
