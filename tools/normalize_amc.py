"""把 papers_amc 的分章草稿规范成存储格式 v2。

    python tools/normalize_amc.py            # 就地重写全部章节
    python tools/normalize_amc.py ch02 ch05  # 只处理指定章节
    python tools/normalize_amc.py --check    # 只检查是否已是规范形式

v1（按题型分组的顶层键）会展开成扁平 questions 数组，补上显式 type 与稳定
id；顺序、字段顺序、bloom 取值也一并归一。`--check` 不写文件，规范化后如果
与磁盘内容不同就返回非零，供 CI 拦住手改或不规范的提交。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pdfquiz import amcbank  # noqa: E402

PAPERS = ROOT / "papers_amc"
CHAPTERS = [f"ch{i:02d}" for i in range(1, 11)]


def main(argv: list[str]) -> int:
    check = "--check" in argv
    picks = [a for a in argv if not a.startswith("--")] or CHAPTERS
    changed = 0
    total = 0

    for stem in picks:
        path = PAPERS / f"{stem}.json"
        if not path.exists():
            print(f"缺文件：{path}")
            return 1
        before = path.read_text(encoding="utf-8")
        try:
            data = amcbank.normalize(json.loads(before), stem)
        except (json.JSONDecodeError, amcbank.BankError) as exc:
            print(f"{stem} 无法规范化：{exc}")
            return 1
        after = amcbank.dumps(data)
        counts = amcbank.counts(data)
        total += len(data["questions"])
        mark = "=" if after == before else ("!" if check else "→")
        print(
            f"{mark} {stem} {len(data['questions']):3d} 题 "
            + " ".join(f"{k} {v}" for k, v in counts.items())
        )
        if after != before:
            changed += 1
            if not check:
                path.write_text(after, encoding="utf-8")

    if check:
        if changed:
            print(f"\n{changed} 个文件不是规范 v2，运行 python tools/normalize_amc.py")
            return 1
        print(f"\n全部为规范 v2，共 {total} 题。")
        return 0

    print(f"\n{changed} 个文件已重写，共 {total} 题。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
