"""校验《化工原理》分章题库草稿。

用法：
    python tools/check_hgyl.py            # 检查 papers_hgyl/ch*.json 全部
    python tools/check_hgyl.py ch01 ch02  # 只检查指定章

和 check_amc 同一套规则（结构、逐字回查、解析质量、上下标写法），只有两处
不同：章节清单来自 tools/hgyl.py，页码引用写成 P123。

顺序、选项、答案、解析都查；任何一条不过就整章不合格，不做静默丢弃。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pdfquiz import amcbank  # noqa: E402
from pdfquiz.verify import Report, check_structure, evidence_ok, squash  # noqa: E402

import hgyl  # noqa: E402
from check_amc import explanation_ok  # noqa: E402

PAPERS = ROOT / "papers_hgyl"
CORPUS = ROOT / "corpus_hgyl"

KINDS = amcbank.KINDS

# 面积/体积/摩尔量/传热系数的常见写法，缺上下标会读错量纲
ASCII_UNITS = re.compile(
    r"(?<![A-Za-z])("
    r"(?:m|cm|mm|dm|km|kg|g|mol|kmol|Pa|W|J|N|s|h|L)[23](?![0-9A-Za-z])"
    r"|10-\d"
    r"|kg/m3|m3/h|m3/s|m2/s|W/\(m2|J/\(kg|kJ/\(kg"
    r"|H2O|CO2|SO2|O2|N2|NH3|H2SO4|CaCO3|NaCl"
    r")"
)


def notation_ok(question: dict) -> tuple[bool, str]:
    """化工原理全靠量纲说话，m³ 写成 m3 会直接改变题意。"""
    texts = [question.get("question", ""), question.get("explanation", "")]
    texts += question.get("options") or []
    answer = question.get("answer")
    if isinstance(answer, str):
        texts.append(answer)
    elif isinstance(answer, list):
        texts += [str(x) for x in answer]
    for text in texts:
        hit = ASCII_UNITS.search(str(text))
        if hit:
            return False, f"「{hit.group(0)}」请写成 Unicode 上下标或 <sub>/<sup>"
    return True, ""


def page_texts(corpus: str) -> dict[int, str]:
    parts = re.split(r"^### p(\d+)\s*$", corpus, flags=re.M)
    return {int(parts[i]): squash(parts[i + 1]) for i in range(1, len(parts), 2)}


def page_ok(question: dict, pages: dict[int, str]) -> tuple[bool, str]:
    """ref 必须与 evidence 所在页一致：站点上写着「第 123 页」，翻过去就得有这句。"""
    m = re.search(r"(\d+)", str(question.get("ref", "")))
    if not m:
        return False, "ref 缺页码"
    page = int(m.group(1))
    if page not in pages:
        return False, f"ref 指向 P{page}，语料里没有这一页"
    if squash(question.get("evidence", "")) not in pages[page]:
        return False, f"evidence 不在 P{page} 上（ref 与原文页不一致）"
    return True, ""


def flatten(data: dict) -> list[dict]:
    out = []
    chapter = data.get("chapter", "")
    for q in data["questions"]:
        item = dict(q)
        item.setdefault("chunk_path", f"{chapter} > {item.get('ref', '')}")
        item["_kind"] = item["type"]
        out.append(item)
    return out


def check(data: dict, corpus: str) -> Report:
    report = Report()
    seen: set[str] = set()
    pages = page_texts(corpus)

    for q in flatten(data):
        kind = q["_kind"]
        ok, why = check_structure(q)
        if ok:
            ok, why = evidence_ok(q.get("evidence", ""), corpus)
        if ok:
            ok, why = page_ok(q, pages)
        if ok and not str(q.get("explanation", "")).strip():
            ok, why = False, "缺 explanation（错在哪、依据哪句）"
        if ok:
            ok, why = explanation_ok(q.get("explanation", ""), q.get("evidence", ""))
        if ok:
            ok, why = notation_ok(q)
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
    if not CORPUS.exists():
        print("缺 corpus_hgyl/（教材语料不入库），跳过逐字核对")
        return 0
    picks = argv[1:] or hgyl.ORDER
    bad = 0
    seen_ids: set[str] = set()

    for stem in picks:
        f = PAPERS / f"{stem}.json"
        if not f.exists():
            print(f"缺文件：{f}")
            bad += 1
            continue
        try:
            data = amcbank.load(f)
        except amcbank.BankError as exc:
            print(f"== {stem}\n   存储格式错误：{exc}")
            bad += 1
            continue
        corpus_file = CORPUS / f"{stem}.md"
        if not corpus_file.exists():
            print(f"== {stem}\n   缺语料：{corpus_file}")
            bad += 1
            continue
        corpus = corpus_file.read_text(encoding="utf-8")
        report = check(data, corpus)
        counts = amcbank.counts(data)
        for q in data["questions"]:
            if q["id"] in seen_ids:
                print(f"   ✗ 全局重复 id：{q['id']}")
                bad += 1
            seen_ids.add(q["id"])

        floor = hgyl.minimum(stem)
        short = [f"{k} {counts[k]}/{floor[k]}" for k in KINDS if counts[k] < floor[k]]
        long = [f"{k} {counts[k]}>{hgyl.MAXIMUM[k]}" for k in KINDS if counts[k] > hgyl.MAXIMUM[k]]
        print(f"== {stem} {data.get('chapter', '')}")
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