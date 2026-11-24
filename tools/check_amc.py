"""校验《先进材料研究进展C》分章题库草稿。

用法：
    python tools/check_amc.py            # 检查 papers_amc/ch*.json 全部
    python tools/check_amc.py ch02       # 只检查一个

每条题目的 evidence 必须能在对应章节的课件转录稿（corpus_amc/chXX.md）
里逐字找到，找不到就报错并指出是哪一题。这里不做静默丢弃：草稿阶段宁可
吵一点，也不要让没依据的题混进成品。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pdfquiz import amcbank  # noqa: E402
from pdfquiz.verify import Report, check_structure, evidence_ok, squash  # noqa: E402

PAPERS = ROOT / "papers_amc"
CORPUS = ROOT / "corpus_amc"

KINDS = amcbank.KINDS
MINIMUM = {"single": 6, "multiple": 3, "truefalse": 4, "fill": 4, "short": 3, "term": 5}
MAXIMUM = {"single": 12, "multiple": 5, "truefalse": 7, "fill": 7, "short": 5, "term": 10}
BAD_PUNCT = ("，，", "。。", "；；", "、、")


def explanation_ok(explanation: str, evidence: str) -> tuple[bool, str]:
    """解析是给学生看的，不能是空话、病句或 evidence 的复印件。"""
    text = str(explanation or "").strip()
    if len(text) < 30:
        return False, "explanation 太短，没讲清错在哪、依据哪句"
    for mark in BAD_PUNCT:
        if mark in text:
            return False, f"explanation 有重复标点「{mark}」"
    if "课件" in text:
        return False, "explanation 不要用「课件」指代来源"
    if squash(text) == squash(evidence):
        return False, "explanation 不能照抄 evidence"
    return True, ""


def load(chapter_file: Path) -> tuple[dict, str]:
    data = amcbank.load(chapter_file)
    stem = chapter_file.stem  # ch02
    corpus = (CORPUS / f"{stem}.md").read_text(encoding="utf-8")
    return data, corpus


def flatten(data: dict) -> list[dict]:
    out: list[dict] = []
    chapter = data.get("chapter", "")
    for q in data["questions"]:
        item = dict(q)
        item.setdefault("chunk_path", f"{chapter} > {item.get('ref', '')}")
        item["_kind"] = item["type"]
        out.append(item)
    return out


def check(data: dict, corpus: str) -> Report:
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
            ok, why = explanation_ok(q.get("explanation", ""), q.get("evidence", ""))
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
    picks = argv[1:] or ["ch01", "ch02", "ch03", "ch04", "ch05", "ch06", "ch07", "ch08", "ch09", "ch10"]
    bad = 0
    seen_ids: set[str] = set()
    for stem in picks:
        f = PAPERS / f"{stem}.json"
        if not f.exists():
            print(f"缺文件：{f}")
            bad += 1
            continue
        try:
            data, corpus = load(f)
        except amcbank.BankError as exc:
            print(f"== {stem}\n   存储格式错误：{exc}")
            bad += 1
            continue
        report = check(data, corpus)
        counts = amcbank.counts(data)
        for q in data["questions"]:
            if q["id"] in seen_ids:
                print(f"   ✗ 全局重复 id：{q['id']}")
                bad += 1
            seen_ids.add(q["id"])
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
