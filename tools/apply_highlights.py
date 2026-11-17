"""把课堂划重点并入现有题库，而不是另建一套卷子。

- 词汇 / 短语 → docs/terms.html（术语默写总表）
- 重点句     → docs/notes.html（教材重点句对照）

已在题库里的词条只补一条「课堂划重点」说明，不重复出题；脚本可重复运行。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HIGHLIGHTS = ROOT / "papers" / "highlights.json"
DOCS = ROOT / "docs"

PAYLOAD = re.compile(r"(window\.__QUIZ__\s*=\s*)(\{.*?\})(;?\s*</script>)", re.S)
PREFIX = "课堂划重点："


def load_deck(path: Path) -> tuple[str, dict, re.Match]:
    text = path.read_text(encoding="utf-8")
    match = PAYLOAD.search(text)
    if not match:
        raise RuntimeError(f"找不到内联题库数据：{path}")
    return text, json.loads(match.group(2)), match


def save_deck(path: Path, text: str, payload: dict, match: re.Match) -> None:
    payload["meta"]["accepted"] = len(payload["questions"])
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    path.write_text(text[: match.start(2)] + data + text[match.end(2) :], encoding="utf-8")


def strip_prompt(question: str) -> str:
    return re.sub(r"^写出英文[：:]\s*", "", question.strip())


def marked(exp: str) -> str:
    exp = exp.strip()
    return exp if exp.startswith(PREFIX) else PREFIX + exp


def term_entry(item: dict, index: int) -> dict:
    section = "Words and Expressions" if item["type"] == "term" else "Phrases"
    return {
        "i": index,
        "n": index + 1,
        "ch": "老师划重点",
        "sec": section,
        "code": "",
        "t": "term",
        "bloom": item.get("bloom", "记忆"),
        "diff": item.get("difficulty", "easy"),
        "q": strip_prompt(item["question"]),
        "o": [],
        "a": [str(item["answer"]).strip()],
        "exp": marked(item.get("explanation", "")),
        "ev": item.get("evidence", ""),
        "keys": item.get("keys", []),
        "ref": item.get("ref", ""),
        "hint": "",
        "score": 1,
    }


def sentence_entry(item: dict, index: int) -> dict:
    return {
        "i": index,
        "n": index + 1,
        "ch": "老师划重点",
        "sec": "重点句",
        "code": "",
        "t": "trans_en_cn",
        "bloom": item.get("bloom", "理解"),
        "diff": item.get("difficulty", "medium"),
        "q": item["question"].strip(),
        "o": [],
        "a": [str(item["answer"]).strip()],
        "exp": marked(item.get("explanation", "")),
        "ev": item.get("evidence", ""),
        "keys": item.get("keys", []),
        "ref": item.get("ref", ""),
        "hint": "",
        "score": item.get("score", 2),
    }


def merge_terms(items: list[dict]) -> tuple[int, int]:
    path = DOCS / "terms.html"
    text, payload, match = load_deck(path)
    by_answer = {
        str(q["a"][0]).strip().casefold(): q
        for q in payload["questions"]
        if q.get("a")
    }

    added = marked_existing = 0
    for item in items:
        if item.get("type") not in {"term", "fill"}:
            continue
        key = str(item["answer"]).strip().casefold()
        if key in by_answer:
            q = by_answer[key]
            new_exp = marked(q.get("exp", ""))
            if new_exp != q.get("exp", ""):
                q["exp"] = new_exp
                marked_existing += 1
            continue
        entry = term_entry(item, len(payload["questions"]))
        payload["questions"].append(entry)
        by_answer[key] = entry
        added += 1

    save_deck(path, text, payload, match)
    return added, marked_existing


def merge_sentences(items: list[dict]) -> tuple[int, int]:
    path = DOCS / "notes.html"
    text, payload, match = load_deck(path)
    added = marked_existing = 0
    for item in items:
        if item.get("type") != "trans_en_cn":
            continue
        key = re.sub(r"\s+", " ", item["question"]).strip().casefold()
        existing = next(
            (q for q in payload["questions"]
             if re.sub(r"\s+", " ", str(q.get("q", ""))).strip().casefold() == key),
            None,
        )
        if existing:
            new_exp = marked(existing.get("exp", ""))
            if new_exp != existing.get("exp", ""):
                existing["exp"] = new_exp
                marked_existing += 1
            continue
        payload["questions"].append(sentence_entry(item, len(payload["questions"])))
        added += 1

    save_deck(path, text, payload, match)
    return added, marked_existing


def main() -> int:
    data = json.loads(HIGHLIGHTS.read_text(encoding="utf-8"))
    items = data.get("questions", data)
    if not isinstance(items, list):
        raise SystemExit("papers/highlights.json 里没有 questions 列表")

    t_add, t_mark = merge_terms(items)
    n_add, n_mark = merge_sentences(items)
    print(f"术语总表：新增 {t_add} 题，标注已有 {t_mark} 题")
    print(f"重点句对照：新增 {n_add} 题，标注已有 {n_mark} 题")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
