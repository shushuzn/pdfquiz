"""从教材正文抽取「高分子材料名称」中英对照，生成名称默写卷。

只保留在 `.units/*.md` 正文里真正出现过的名称，且每题都挂一句原文依据，
这样每道题都能点开看「教材哪里这么写的」。数据源：
`tools/materials.tsv`（英文名<TAB>缩写<TAB>中文名）。

用法：
    python tools/build_materials.py            # 只扫描，打印命中情况
    python tools/build_materials.py --write    # 写出 papers/materials.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UNITS = ROOT / ".units"
OUT = ROOT / "papers" / "materials.json"
TABLE = ROOT / "tools" / "materials.tsv"

sys.path.insert(0, str(ROOT / "tools"))
from pdfquiz.booktext import sentences, split_body, unit_title  # noqa: E402


def load_units() -> dict[str, str]:
    if not UNITS.is_dir():
        return {}
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted(UNITS.glob("unit*.md"))}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def load_table() -> list[tuple[str, str, str]]:
    rows = []
    for line in TABLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        en, abbr, cn = (x.strip() for x in parts[:3])
        if en:
            rows.append((en, abbr, cn))
    return rows


def _good_use(sent: str, en: str) -> bool:
    """判断这处出现是不是「材料名本身」，而不是 polypropylene ethers 这类派生词。"""
    m = re.search(r"\b" + re.escape(en).replace(r"\ ", r"[\s\-]+") + r"s?\b", sent, re.I)
    if not m:
        return False
    before = sent[: m.start()].rstrip()
    after = sent[m.end():].lstrip()
    prev_word = re.search(r"([A-Za-z]+)$", before)
    prev = prev_word.group(1).lower() if prev_word else ""
    nxt = (re.match(r"([A-Za-z]+)", after) or [None, ""])[1].lower() if after else ""
    # 后面紧跟的实词不是系动词/连词，说明它只是个定语（polypropylene ethers）
    ok_after = nxt in {"", "is", "are", "was", "were", "has", "have", "had", "and", "or", "can", "may", "gives", "give"}
    if after[:1] in ",.;:)":
        ok_after = True
    # 前面是 the/a/these/those 之类冠词时，必须是「these polyethylene」这种直接修饰，
    # 若中间还有别的实词（these polypropylene ethers），after 已经把它挡住了
    ok_before = True
    if prev in {"of", "than", "like", "such"}:
        ok_before = True
    return ok_after and ok_before


def find(units: dict[str, str], rows):
    """返回 [(en, abbr, cn, unit_no, sentence)]，同一名称取第一次出现的单元。"""
    hits = []
    for en, abbr, cn in rows:
        pat = re.compile(r"\b" + re.escape(en).replace(r"\ ", r"[\s\-]+") + r"s?\b", re.I)
        found = None
        for stem, md in units.items():
            body = split_body(md)
            for s in sentences(body):
                if pat.search(s) and _good_use(s, en):
                    found = (int(stem[4:]), norm(s))
                    break
            if found:
                break
        if found:
            hits.append((en, abbr, cn, found[0], found[1]))
    return hits


def make_questions(units, titles, hits) -> list[dict]:
    out = []
    for en, abbr, cn, num, sent in hits:
        title = titles.get(num, f"UNIT {num}")
        ans = f"{en} / {abbr}" if abbr else en
        out.append({
            "type": "term",
            "chunk_path": f"PART A 高分子化学与物理 > {title}",
            "score": 2,
            "question": cn,
            "answer": ans,
            "keys": [{"en": en, "cn": cn}] + ([{"en": abbr, "cn": cn + "（缩写）"}] if abbr else []),
            "ref": f"{title} · 材料名称",
            "evidence": sent,
            "explanation": f"常见高分子材料名称：{cn} → {en}" + (f"，缩写 {abbr}" if abbr else ""),
        })
    return out


def main(argv: list[str]) -> int:
    units = load_units()
    if not units:
        print("找不到 .units/*.md")
        return 1
    titles = {int(s[4:]): unit_title(md, s) for s, md in units.items()}
    rows = load_table()
    hits = find(units, rows)
    print(f"对照表 {len(rows)} 条 · 正文命中 {len(hits)} 条 · 未命中 {len(rows) - len(hits)} 条")
    if not hits:
        return 1
    miss = [r[0] for r in rows if r[0] not in {h[0] for h in hits}]
    if miss:
        print("未命中：" + "、".join(miss))
    by_unit: dict[int, int] = {}
    for h in hits:
        by_unit[h[3]] = by_unit.get(h[3], 0) + 1
    print("按单元：" + " ".join(f"U{k}×{v}" for k, v in sorted(by_unit.items())))

    if "--write" not in argv:
        for en, abbr, cn, num, sent in hits[:8]:
            print(f"  U{num:<3} {cn:<14} → {en:<38} | {sent[:52]}")
        return 0

    qs = make_questions(units, titles, hits)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "meta": {
            "title": "高分子材料名称 · 中译英默写",
            "source": "《高分子材料工程专业英语》曹同玉、冯连芳主编（化学工业出版社）",
            "note": "PPT「2.1 考前复习」指定：常见高分子材料名称与性质的英文翻译是重点",
        },
        "questions": qs,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"写出 {OUT}（{len(qs)} 题 · 满分 {sum(q['score'] for q in qs)}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
