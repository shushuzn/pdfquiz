"""把例题里常见的 OCR 上下标写法统一成网页写法。

    python tools/normalize_examples.py --check   # 只报告
    python tools/normalize_examples.py --write   # 就地修正
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import examples  # noqa: E402
import hgyl  # noqa: E402

TEXT_FIELDS = ("topic", "problem", "solution", "answer", "note")


def main(argv: list[str]) -> int:
    write = "--write" in argv
    changed = 0
    for stem in hgyl.ORDER:
        path = examples.path_of(stem)
        if not path.exists():
            continue
        data = examples.load(stem)
        dirty = False
        for item in data.get("examples") or []:
            for key in TEXT_FIELDS:
                old = str(item.get(key, ""))
                new = examples.normalize_text(old)
                if new != old:
                    item[key] = new
                    dirty = True
        if dirty:
            changed += 1
            print(f"{stem}: 需要修正")
            if write:
                path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
        else:
            print(f"{stem}: 无需修正")
    print(f"{changed} 个文件{'已修正' if write else '需要修正'}")
    if changed and not write:
        print("运行 python tools/normalize_examples.py --write 统一上下标写法")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))