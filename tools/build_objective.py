"""从教材正文生成客观题（填空 + 单选），补上「40% 客观题」这一块空白。

思路是「不造题，只搬」：
- 填空题：直接拿教材原句，把其中一个真词挖成空，答案就是那个词，依据句就是原句。
- 单选题：题干是词汇表里的中文释义，正确项是它对应的英文，干扰项从同一本书的
  其它术语里取（长度相近、首字母不同），四个选项都真实存在于教材词汇表。

用法：
    python tools/build_objective.py            # 只统计
    python tools/build_objective.py --write    # 写出 papers/objective.json
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UNITS = ROOT / ".units"
OUT = ROOT / "papers" / "objective.json"

sys.path.insert(0, str(ROOT / "tools"))
from build_exam import (  # noqa: E402
    _first_meaning,
    canonical_path,
    parse_vocab,
    sentences,
    split_body,
    unit_title,
)

FILL_TARGET = 34
SINGLE_TARGET = 40
BLANK = "＿＿＿＿"


def load_units() -> dict[str, str]:
    if not UNITS.is_dir():
        return {}
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted(UNITS.glob("unit*.md"))}


def _pos_key(pos: str) -> str:
    """把词性归一成 n / v / adj / adv，用来挑同类干扰项。"""
    p = (pos or "").lower()
    if p.startswith("n"):
        return "n"
    if p.startswith("v"):
        return "v"
    if p.startswith("a") or p.startswith("adj"):
        return "adj"
    if p.startswith("ad") or p.startswith("adv"):
        return "adv"
    return "other"


def vocab_all(units: dict[str, str]):
    """[(term, meaning, unit_no, pos_key)]，同词只留第一次出现。"""
    out, seen = [], set()
    for stem, md in units.items():
        num = int(stem[4:])
        for row in parse_vocab(md):
            term = row["term"].strip()
            key = re.sub(r"[^a-z]", "", term.lower())
            if len(key) < 4 or key in seen or " " in term:
                continue
            meaning = _first_meaning(row["meaning"])
            if len(meaning) < 2:
                continue
            seen.add(key)
            out.append((term, meaning, num, _pos_key(row.get("pos", ""))))
    return out


def make_fill(units: dict[str, str], titles: dict[int, str], vocab) -> list[dict]:
    """挖空填词：原句里恰好出现一次的术语才挖，避免歧义。"""
    by_unit: dict[int, list[str]] = {}
    for term, _meaning, num, _pos in vocab:
        by_unit.setdefault(num, []).append(term)

    out, used_sent, per_term = [], set(), {}
    # 按单元轮转、术语从长到短：长词更像考点，也避免同一个词被反复挖
    plans = []
    for stem, md in units.items():
        num = int(stem[4:])
        terms = sorted(set(by_unit.get(num, [])), key=len, reverse=True)
        if terms:
            plans.append((num, terms, sentences(split_body(md))))

    quota = max(1, FILL_TARGET // max(1, sum(1 for p in plans for _ in p[1][:6])))
    for num, terms, sents in plans:
        for term in terms:
            if len(out) >= FILL_TARGET:
                break
            if per_term.get(term, 0) >= 2:
                continue
            if not (5 <= len(term) <= 13):
                continue
            for sent in sents:
                if not (32 <= len(sent) <= 190):
                    continue
                key = re.sub(r"\W+", "", sent).lower()[:60]
                if key in used_sent:
                    continue
                hits = re.findall(r"\b" + re.escape(term) + r"\b", sent, re.I)
                if len(hits) != 1:
                    continue
                hit = re.search(r"\b" + re.escape(term) + r"\b", sent, re.I)
                stem_text = sent[: hit.start()] + BLANK + sent[hit.end():]
                if len(stem_text) < 34:
                    continue
                out.append({
                    "type": "fill",
                    "chunk_path": canonical_path(num, titles),
                    "score": 2,
                    "question": stem_text,
                    "answer": term,
                    "keys": [{"en": term, "cn": ""}],
                    "ref": f"{titles.get(num, '')} · 原文填空",
                    "evidence": sent,
                    "difficulty": "easy" if len(term) <= 8 else ("medium" if len(term) <= 11 else "hard"),
                    "explanation": f"原句用 {term}；注意拼写与单复数。",
                })
                used_sent.add(key)
                per_term[term] = per_term.get(term, 0) + 1
                break
    return out


def make_single(units, titles, vocab, seed: int = 20261115) -> list[dict]:
    """中文释义 → 选英文术语，干扰项取自同一本书的其它术语。"""
    rnd = random.Random(seed)
    pool = [(t, m, n, p) for t, m, n, p in vocab if 4 <= len(t) <= 28]

    # 每题都必须挂一句教材原句做依据，否则「这个词在书里哪儿出现过」说不清
    sents_by_unit: dict[int, list[str]] = {}
    for stem, md in units.items():
        sents_by_unit[int(stem[4:])] = sentences(split_body(md))

    def evidence_for(term: str, num: int) -> str:
        pat = re.compile(r"\b" + re.escape(term) + r"\b", re.I)
        for scope in ([num], sorted(sents_by_unit)):
            for n in scope:
                for sent in sents_by_unit.get(n, []):
                    if pat.search(sent) and len(sent) >= 30:
                        return sent
        return ""

    out = []
    for term, meaning, num, pos in pool:
        if len(out) >= SINGLE_TARGET:
            break
        want = len(term)
        # 干扰项优先同词性：名词题不该混进 imperfect / amorphous 这类形容词
        same = [
            t for t, m, _n, p in pool
            if p == pos and t.lower() != term.lower() and m != meaning and abs(len(t) - want) <= 6
        ]
        cands = same if len(same) >= 12 else [
            t for t, m, _n, p in pool
            if t.lower() != term.lower() and m != meaning and abs(len(t) - want) <= 6
        ]
        if len(cands) < 12:
            continue
        rnd.shuffle(cands)
        picks, firsts = [], {term[0].lower()}
        for c in cands:
            if c[0].lower() in firsts:
                continue
            if re.sub(r"[^a-z]", "", c.lower()) == re.sub(r"[^a-z]", "", term.lower()):
                continue
            picks.append(c)
            firsts.add(c[0].lower())
            if len(picks) == 3:
                break
        if len(picks) < 3:
            continue
        ev = evidence_for(term, num)
        if not ev:
            continue
        options = picks + [term]
        rnd.shuffle(options)
        letter = "ABCD"[options.index(term)]
        out.append({
            "type": "single",
            "chunk_path": canonical_path(num, titles),
            "score": 2,
            "question": f"「{meaning}」对应的英文术语是：",
            "options": options,
            "answer": letter,
            "keys": [{"en": term, "cn": meaning}],
            "ref": f"{titles.get(num, '')} · 词汇表",
            "evidence": ev,
            "difficulty": "easy",
            "explanation": f"{meaning} → {term}",
        })
    return out


def main(argv: list[str]) -> int:
    units = load_units()
    if not units:
        print("找不到 .units/*.md")
        return 1
    titles = {int(s[4:]): unit_title(md, s) for s, md in units.items()}
    vocab = vocab_all(units)
    print(f"词汇表可用 {len(vocab)} 条")

    fills = make_fill(units, titles, vocab)
    singles = make_single(units, titles, vocab)
    print(f"填空 {len(fills)} 题 · 单选 {len(singles)} 题 · 合计 {len(fills) + len(singles)}")

    if "--write" not in argv:
        for q in fills[:4]:
            print("  填 " + q["question"][:70] + "  →  " + q["answer"])
        for q in singles[:4]:
            print("  选 " + q["question"] + "  →  " + q["answer"] + " " + q["options"][ord(q["answer"]) - 65])
        return 0

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "meta": {
            "title": "客观题专练 · 填空与选择",
            "source": "《高分子材料工程专业英语》曹同玉、冯连芳主编（化学工业出版社）",
            "note": "填空挖自教材原句，选项全部取自本教材词汇表，不另造题。",
        },
        "questions": fills + singles,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"写出 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
