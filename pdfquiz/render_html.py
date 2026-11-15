"""导出单文件网页题库。

产物是一个自包含 HTML：无外链、无 CDN、无服务端，双击即可作答。
所有题目以 JSON 内联注入，样式与脚本都在同一文件里，方便丢到任意
静态托管（GitHub Pages / 内网共享盘）直接打开。
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from .verify import Report

LETTERS = "ABCDEFGH"
_LABEL = re.compile(r"^\s*[A-Ha-h]\s*[\.\、\)．:：]\s*")
TEMPLATE = Path(__file__).parent / "templates" / "quiz.html"


def _strip_label(option: object) -> str:
    """去掉选项自带的 "A." 前缀，字母由渲染层统一分配。"""
    return _LABEL.sub("", str(option).strip()).strip()


def _letters(answer: object, count: int) -> list[str]:
    """把各种写法的答案归一成选项字母列表。"""
    raw = answer if isinstance(answer, list) else [answer]
    valid = LETTERS[:count]
    out: list[str] = []
    for item in raw:
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            idx = item if 0 <= item < count else item - 1
            if 0 <= idx < count and valid[idx] not in out:
                out.append(valid[idx])
            continue
        for ch in str(item).strip().upper():
            if ch in valid and ch not in out:
                out.append(ch)
    return out


def _bool(answer: object) -> str:
    s = str(answer).strip().lower()
    return "T" if s in {"true", "t", "对", "正确", "是", "√"} else "F"


def _split_path(path: str) -> tuple[str, str]:
    parts = [p.strip() for p in str(path or "").split(">") if p.strip()]
    if not parts:
        return "未分章", "未分节"
    if len(parts) == 1:
        return parts[0], parts[0]
    return parts[0], parts[-1]


def _section_of(sec: str) -> str:
    """从 "3.2 偏差与方差的权衡" 里取出编号 "3.2"。"""
    m = re.match(r"^\s*(\d+(?:\.\d+)*)", sec)
    return m.group(1) if m else ""


def build_payload(
    *,
    title: str,
    engine: str,
    source: str,
    chunks: int,
    reports: list[Report],
    mock: bool,
    generated: str,
) -> dict:
    accepted = [q for r in reports for q in r.accepted]
    rejected = [q for r in reports for q in r.rejected]

    questions: list[dict] = []
    for i, q in enumerate(accepted):
        qtype = str(q.get("type", "single")).lower()
        chapter, section = _split_path(q.get("chunk_path", ""))
        options = [_strip_label(o) for o in (q.get("options") or []) if str(o).strip()]

        if qtype == "truefalse":
            answer = [_bool(q.get("answer"))]
            if len(options) < 2:
                options = ["正确", "错误"]
        elif qtype in {"single", "multiple"}:
            answer = _letters(q.get("answer"), len(options)) or ["A"]
        else:
            answer = [str(q.get("answer", "")).strip()]

        questions.append(
            {
                "i": i,
                "n": i + 1,
                "ch": chapter,
                "sec": section,
                "code": _section_of(section),
                "t": qtype,
                "bloom": str(q.get("bloom", "") or ""),
                "diff": str(q.get("difficulty", "") or ""),
                "q": str(q.get("question", "")).strip(),
                "o": options,
                "a": answer,
                "exp": str(q.get("explanation", "") or "").strip(),
                "ev": str(q.get("evidence", "") or "").strip(),
            }
        )

    return {
        "meta": {
            "id": _slug(title),
            "title": title,
            "engine": engine,
            "source": source,
            "generated": generated,
            "chunks": chunks,
            "accepted": len(accepted),
            "rejected": [
                {"q": str(r.get("question", ""))[:120], "why": str(r.get("reason", ""))}
                for r in rejected
            ],
            "mock": bool(mock),
        },
        "questions": questions,
    }


def _slug(text: str) -> str:
    keep = [c for c in text if c.isalnum() or c in "-_"]
    return "".join(keep)[:60] or "deck"


def render_html(
    *,
    title: str,
    engine: str,
    source: str,
    chunks: int,
    reports: list[Report],
    mock: bool,
    template: Path | None = None,
) -> str:
    from datetime import datetime

    generated = f"{datetime.now():%Y-%m-%d %H:%M}"
    payload = build_payload(
        title=title,
        engine=engine,
        source=source,
        chunks=chunks,
        reports=reports,
        mock=mock,
        generated=generated,
    )

    tpl = (template or TEMPLATE).read_text(encoding="utf-8")
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    subtitle_bits = [f"解析器 {engine}", f"{len(payload['questions'])} 题", f"生成于 {generated}"]
    if mock:
        subtitle_bits.insert(0, "离线模式产物")

    return (
        tpl.replace("{{TITLE}}", html.escape(title))
        .replace("{{SUBTITLE}}", html.escape(" · ".join(subtitle_bits)))
        .replace("{{SOURCE}}", html.escape(source))
        .replace("{{DATA}}", data)
    )
