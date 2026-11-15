"""端到端冒烟：离线跑一遍 CLI，断言产出的题库结构正常且没有题被淘汰。

CI 里跑这个是为了守住一条底线——**改坏流水线要能被发现**。单元测试都过、
但 CLI 拼不起来的情况以前真发生过（模板重复声明那次就是网页整页失效）。
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pdfquiz.cli import main  # noqa: E402


def check() -> int:
    out = Path(tempfile.mkdtemp(prefix="pdfquiz-smoke-"))
    rc = main([str(ROOT / "samples" / "过拟合与正则化.md"), "--provider", "offline", "-o", str(out)])
    assert rc == 0, f"CLI 返回 {rc}"

    md = out / "过拟合与正则化.quiz.md"
    html = out / "过拟合与正则化.quiz.html"
    assert md.exists() and md.stat().st_size > 500, "Markdown 题库没生成"
    assert html.exists() and html.stat().st_size > 5000, "网页题库没生成"

    raw = html.read_text(encoding="utf-8")
    m = re.search(r"window\.__QUIZ__ = (\{.*?\});\s*</script>", raw, re.S)
    assert m, "网页里找不到 __QUIZ__ 数据"
    data = json.loads(m.group(1))
    meta = data.get("meta", {})
    accepted = meta.get("accepted", 0)
    rejected = meta.get("rejected", [])
    assert accepted > 0, "一道题都没通过校验"
    assert not rejected, f"有题被淘汰：{rejected[:2]}"
    assert len(data.get("questions", [])) == accepted, "题数与 meta 不一致"
    for q in data["questions"]:
        assert q.get("ev"), f"第 {q.get('n')} 题没有原文依据"

    print(f"冒烟通过：{accepted} 题，淘汰 0，网页 {html.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(check())
