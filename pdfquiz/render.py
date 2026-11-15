"""导出 Markdown 题库。"""

from __future__ import annotations

from datetime import datetime

from .verify import Report, stats

LETTERS = "ABCDEFGH"

TYPE_CN = {
    "single": "单选题",
    "multiple": "多选题",
    "truefalse": "判断题",
    "short": "简答题",
    "fill": "填空题",
}


def _answer_text(q: dict) -> str:
    ans = q.get("answer")
    if isinstance(ans, list):
        return "".join(str(a).upper()[:1] for a in ans)
    if str(q.get("type")) == "truefalse":
        return "正确" if str(ans).lower() in {"true", "对", "t"} else "错误"
    return str(ans)


def render(
    *,
    title: str,
    engine: str,
    source: str,
    chunks: int,
    reports: list[Report],
    mock: bool,
) -> str:
    accepted = [q for r in reports for q in r.accepted]
    rejected = [q for r in reports for q in r.rejected]
    st = stats(accepted)

    lines: list[str] = [f"# {title} · 复习题库", ""]
    if mock:
        lines += [
            "> **离线模式产物**：题目由陈述句改写而来，用于验证流水线，不是真正的出题结果。",
            "> 配置 `OPENAI_API_KEY` 后去掉 `--offline` 重跑，才会得到有干扰项的选择题。",
            "",
        ]

    lines += [
        f"- 源文件：`{source}`",
        f"- 解析器：`{engine}` · 切块：{chunks} 段",
        f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M}",
        f"- 通过校验：**{len(accepted)}** 题 · 丢弃：{len(rejected)} 题"
        + (f"（淘汰率 {len(rejected) / max(1, len(accepted) + len(rejected)):.0%}）" if rejected else ""),
        "",
    ]

    if accepted:
        lines += [
            "| 维度 | 分布 |",
            "|---|---|",
            "| 题型 | "
            + " · ".join(f"{TYPE_CN.get(k, k)} {v}" for k, v in st["type"].items())
            + " |",
            "| 认知层次 | " + " · ".join(f"{k} {v}" for k, v in st["bloom"].items()) + " |",
            "| 难度 | " + " · ".join(f"{k} {v}" for k, v in st["difficulty"].items()) + " |",
            "",
        ]

    current_path = None
    for i, q in enumerate(accepted, 1):
        path = q.get("chunk_path", "")
        if path != current_path:
            lines += ["", f"## {path}", ""]
            current_path = path
        lines += _render_question(i, q)

    if accepted:
        lines += ["", "---", "", "## 答案与解析", ""]
        for i, q in enumerate(accepted, 1):
            lines.append(
                f"**{i}. {_answer_text(q)}**　"
                f"*{TYPE_CN.get(str(q.get('type')), q.get('type'))} · "
                f"{q.get('bloom', '')} · {q.get('difficulty', '')}*"
            )
            expl = str(q.get("explanation", "")).strip()
            if expl:
                lines.append(f"　　{expl}")
            ev = str(q.get("evidence", "")).strip()
            if ev:
                lines.append(f"　　> 原文依据：{ev}")
            lines.append("")

    if rejected:
        lines += ["", "---", "", "## 被丢弃的题（溯源失败或结构不合法）", ""]
        for r in rejected:
            lines.append(f"- `{r['reason']}` — {r['question'][:80]}")
        lines.append("")

    return "\n".join(lines)


def _render_question(i: int, q: dict) -> list[str]:
    qtype = str(q.get("type", "single"))
    out = [f"**{i}.** {q.get('question', '').strip()}", ""]
    options = q.get("options") or []
    if not options and qtype == "truefalse":
        options = ["正确", "错误"]
    for j, opt in enumerate(options):
        text = str(opt).strip()
        prefix = f"{LETTERS[j]}."
        if not text.startswith(prefix):
            text = f"{prefix} {text}"
        out.append(f"- {text}")
    if options:
        out.append("")
    if qtype == "short":
        out.append("　　_答：_")
        out.append("")
    return out
