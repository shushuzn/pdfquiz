"""从 .units/*.md 的 Notes 板块抽取「重点句 + 教材原译」。

教材每个单元的 Notes 是逐句语法分析，末尾给出全句译文——这正是老师上课
会讲、考试会考的句子，而且译文是教材自己的，不需要模型再翻一遍。

输出 papers/notes.json：
    {"questions": [{type: trans_en_cn, question: 英文原句, answer: 教材译文, ...}]}

抽不出来译文的条目会单独列出，由人工补译后写进 papers/notes_extra.json，
不在脚本里瞎猜。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UNITS = ROOT / ".units"
OUT = ROOT / "papers" / "notes.json"

UNIT_ORDER = ["unit01", "unit02", "unit03", "unit06", "unit07",
              "unit10", "unit16", "unit17", "unit22", "unit29"]
PART_OF = {n: ("PART A 高分子化学与物理" if n <= 10 else
               "PART B 高分子材料工程" if n <= 20 else
               "PART C 高分子材料与应用") for n in range(1, 31)}

# 译文标记的写法各单元不一致：全句译文为：/ 该句译为：/ 此句可译为：/ 译为：
PATTERNS = [
    r"全句(?:的)?译文(?:为|是)?\s*[：:]\s*[“\"]([^”\"]+)[”\"]",
    r"(?:该|此|本)句(?:可)?译(?:为|成)\s*[：:]\s*[“\"]([^”\"]+)[”\"]",
    r"(?:可)?译为\s*[：:]\s*[“\"]([^”\"]+)[”\"]",
    r"译文(?:为|是)?\s*[：:]\s*[“\"]([^”\"]+)[”\"]",
]


def clean_quote(s: str) -> str:
    s = s.strip()
    s = re.sub(r'^["“”]+|["“”]+$', "", s).strip()
    return s


def unit_title(md: str, stem: str) -> str:
    m = re.search(r"^#\s+(.+)$", md, re.M)
    if m:
        t = re.sub(r"[（(][^）)]*[）)]\s*$", "", m.group(1)).strip()
        if t:
            return t
    return f"UNIT {int(stem[4:])}"


def notes_block(md: str) -> str:
    m = re.search(r"^## Notes(.*?)(?=^## )", md, re.M | re.S)
    return m.group(1) if m else ""


def extract() -> tuple[list[dict], list[dict]]:
    ok: list[dict] = []
    miss: list[dict] = []
    for stem in UNIT_ORDER:
        f = UNITS / f"{stem}.md"
        if not f.exists():
            continue
        md = f.read_text(encoding="utf-8")
        num = int(stem[4:])
        title = unit_title(md, stem)
        path = f"{PART_OF[num]} > {title}"
        for block in re.split(r"\n(?=\d+\.\s)", notes_block(md)):
            block = block.strip()
            m = re.match(r"(\d+)\.\s*(.+?)\s*——", block, re.S)
            if not m:
                continue
            en = clean_quote(m.group(2))
            rest = block[m.end():]
            cn = ""
            for p in PATTERNS:
                hits = [clean_quote(h) for h in re.findall(p, rest)]
                hits = [h for h in hits if len(h) >= 8]
                if hits:
                    cn = max(hits, key=len)
                    break
            item = {
                "type": "trans_en_cn",
                "chunk_path": path,
                "score": 5,
                "question": en,
                "answer": cn,
                "ref": f"{title} · Notes {m.group(1)}",
                "evidence": en,
                "bloom": "理解",
                "difficulty": "medium",
                "note_no": int(m.group(1)),
            }
            (ok if cn else miss).append(item)
    return ok, miss


def main() -> int:
    ok, miss = extract()
    # 与 A 卷重复的句子去掉：同一句在两张卷子里出现没有意义
    used = set()
    pa = ROOT / "papers" / "exam_a.json"
    if pa.exists():
        for q in json.loads(pa.read_text(encoding="utf-8"))["questions"]:
            if q.get("type") == "trans_en_cn":
                used.add(re.sub(r"\W+", "", q.get("evidence", ""))[:60])
    kept, dup = [], []
    for q in ok:
        key = re.sub(r"\W+", "", q["question"])[:60]
        (dup if key in used else kept).append(q)

    OUT.write_text(json.dumps({"questions": kept}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"抽出 {len(ok)} 条，去重后保留 {len(kept)} 条（与 A 卷重复 {len(dup)} 条）")
    for q in dup:
        print("  跳过（A 卷已用）：", q["question"][:60])
    print(f"缺译文 {len(miss)} 条，需人工补译：")
    for q in miss:
        print(f"  {q['ref']}：{q['question'][:80]}")
    print(f"写出 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
