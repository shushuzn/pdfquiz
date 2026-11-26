"""校验教材例题数据。

    python tools/check_examples.py          # 全部章
    python tools/check_examples.py ch01     # 只查一章
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
        expected = examples.EXPECTED[stem]
        if not examples.path_of(stem).exists():
            if expected:
                print(f"== {stem}\n   缺文件：{examples.path_of(stem).name}")
                bad += 1
            else:
                print(f"== {stem} 0 例（本章无例题）")
            continue
        try:
            data = examples.load(stem)
        except Exception as exc:  # noqa: BLE001 - 把解析错误原样报出来
            print(f"== {stem}\n   JSON 解析失败：{exc}")
            bad += 1
            continue
        errs = examples.validate(stem, data)
        n = len(data.get("examples") or [])
        total += n
        print(f"== {stem} {data.get('chapter', '')} · {n} 例")
        if errs:
            for e in errs:
                print(f"   ✗ {e}")
            bad += len(errs)
        else:
            print("   结构、编号、页码、上下标写法通过")
    if not bad:
        print(f"共 {total} 例，全部通过")
    else:
        print(f"共 {total} 例，发现 {bad} 处问题")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))