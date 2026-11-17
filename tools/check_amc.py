"""校验《先进材料研究进展C》分章题库草稿。

用法：
    python tools/check_amc.py            # 检查 papers_amc/ch*.json 全部
    python tools/check_amc.py ch02       # 只检查一个

每条题目的 evidence 必须能在对应章节的课件转录稿（corpus_amc/chXX.md）
里逐字找到，找不到就报错并指出是哪一题。这里不做静默丢弃：草稿阶段宁可
吵一点，也不要让没依据的题混进成品。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pdfquiz.verify import Report, check_structure, evidence_ok, squash  # noqa: E402

PAPERS = ROOT / "papers_amc"
CORPUS = ROOT / "corpus_amc"

KINDS = ("single", "multiple", "truefalse", "fill", "short", "term")
MINIMUM = {"single": 6, "multiple": 3, "truefalse": 4, "fill": 4, "short": 3, "term": 5}
MAXIMUM = {"single": 12, "multiple": 5, "truefalse": 7, "fill": 7, "short": 5, "term": 10}

TYPE_OF = {
    "single": "single",
    "multiple": "multiple",
    "truefalse": "truefalse",
    "fill": "fill",
    "short": "short",
    "term": "term",
}


def load(chapter_file: Path) -> tuple[dict, str]:
    data = json.loads(chapter_file.read_text(encoding="utf-8"))
    stem = chapter_file.stem  # ch02
    corpus = (CORPUS / f"{stem}.md").read_text(encoding="utf-8")
    return data, corpus


def flatten(data: dict) -> list[dict]:
    out: list[dict] = []
    chapter = data.get("chapter", "")
    for kind in KINDS:
        for q in data.get(kind) or []:
            item = dict(q)
            item["type"] = TYPE_OF[kind]
            item.setdefault("chunk_path", f"{chapter} > {item.get('ref', '')}")
            item["_kind"] = kind
            out.append(item)
    return out


def check(chapter_file: Path) -> Report:
    data, corpus = load(chapter_file)
    questions = flatten(data)
    report = Report()
    seen: set[str] = set()

    for q in questions:
        kind = q["_kind"]
        why = ""
        ok, why = check_structure(q)
        if ok:
            ok, why = evidence_ok(q.get("evidence", ""), corpus)
        if ok and not str(q.get("explanation", "")).strip():
            ok, why = False, "缺 explanation（错在哪、依据哪句）"
        if ok:
            key = squash(q.get("question", ""))
            if key in seen:
                ok, why = False, "同一章内题干重复"
        if ok:
            seen.add(key)
            report.accepted.append(q)
        else:
            report.rejected.append({"question": q.get("question", ""), "reason": why, "kind": kind})
    return report


def main(argv: list[str]) -> int:
    picks = argv[1:] or [f"ch0{i}" for i in range(1, 5)]
    bad = 0
    for stem in picks:
        f = PAPERS / f"{stem}.json"
        if not f.exists():
            print(f"缺文件：{f}")
            bad += 1
            continue
        data, _ = load(f)
        report = check(f)
        counts = {k: len(data.get(k) or []) for k in KINDS}
        short = [f"{k} {counts[k]}/{MINIMUM[k]}" for k in KINDS if counts[k] < MINIMUM[k]]
        long = [f"{k} {counts[k]}>{MAXIMUM[k]}" for k in KINDS if counts[k] > MAXIMUM[k]]
        print(f"== {stem} {data.get('chapter','')}")
        print(f"   题量 {counts} 通过 {len(report.accepted)} 退回 {len(report.rejected)}")
        if short:
            print(f"   数量不足：{'、'.join(short)}")
            bad += 1
        if long:
            print(f"   超出上限：{'、'.join(long)}")
            bad += 1
        if report.rejected:
            bad += 1
        for r in report.rejected:
            print(f"   ✗ [{r['kind']}] {r['question'][:40]} —— {r['reason']}")
    print("\n全部合格。" if not bad else f"\n需要修：{bad} 处")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
