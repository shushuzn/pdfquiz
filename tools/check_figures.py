"""校验教材例题的插图索引与图片文件。

    python tools/check_figures.py          # 全部章
    python tools/check_figures.py ch01     # 只查一章
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import examples  # noqa: E402
import hgyl  # noqa: E402


def main(argv: list[str]) -> int:
    picks = argv[1:] or hgyl.ORDER
    bad = 0
    total = 0
    for stem in picks:
        if stem not in examples.EXPECTED:
            print(f"未知章节：{stem}")
            bad += 1
            continue
        if not examples.path_of(stem).exists():
            if examples.EXPECTED[stem] == 0:
                print(f"== {stem} 0 张（本章无例题）")
                continue
            print(f"== {stem}\n   缺例题文件 {examples.path_of(stem).name}")
            bad += 1
            continue
        data = examples.load(stem)
        refs = [
            str(item.get("figure", "")).strip()
            for item in data.get("examples") or []
            if str(item.get("figure", "")).strip()
        ]
        if not refs:
            print(f"== {stem} 0 张（本章例题无附图）")
            continue
        errs = examples.validate_figures(stem, data)
        total += len(set(refs))
        print(f"== {stem} {examples.chapter_name(stem)} · {len(set(refs))} 张")
        if errs:
            for err in errs:
                print(f"   ✗ {err}")
            bad += len(errs)
        else:
            print("   索引、文件、页码、尺寸通过")
    if not bad:
        print(f"共 {total} 张，全部通过")
    else:
        print(f"共 {total} 张，发现 {bad} 处问题")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))