"""出题：把一块正文交给模型，强制它同时给出原文锚句。"""

from __future__ import annotations

import re

from .chunk import Chunk
from .llm import parse_json

SYSTEM = """你是出题人，为大学生期末复习命题。

铁律：
1. 只依据给定正文出题。正文没写的内容，一个字都不要加。
2. 每道题必须带 evidence 字段，填入正文中**逐字连续出现**的一句原文，
   作为该题所考知识点的依据。改写过、拼接过的句子无效。
3. 若正文信息不足以支撑某题，宁可少出一题，也不要猜。
4. 禁止出现"以上都对/都不对"这类无信息选项；四个选项必须互不相同。
5. answer 必须是选项字母（单选）或字母数组（多选）；判断题用 true/false。
"""

USER_TMPL = """{lang_line}

题型配比：{types}
本次需要 {n} 道题。

{extra}

请输出 JSON：
{{
  "questions": [
    {{
      "type": "single | multiple | truefalse | short",
      "bloom": "记忆 | 理解 | 应用 | 分析",
      "difficulty": "easy | medium | hard",
      "question": "题干",
      "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
      "answer": "A",
      "explanation": "为什么是这个答案，一两句话",
      "evidence": "正文中逐字连续出现的原句"
    }}
  ]
}}

短文/简答题不需要 options，answer 直接写参考答案要点。

正文（章节：{path}）：
<<<
{text}
>>>
"""

LANG = {
    "zh": "用简体中文命题，术语保留原文英文。",
    "en": "Write the questions in English.",
}

BLOOM_HINT = (
    "认知层次分布请接近：记忆 30%、理解 40%、应用 20%、分析 10%。"
    "不要全部出成背诵题。"
)


def build_prompts(chunk: Chunk, n: int, types: list[str], lang: str) -> tuple[str, str]:
    user = USER_TMPL.format(
        lang_line=LANG.get(lang, LANG["zh"]),
        types="、".join(types),
        n=n,
        extra=BLOOM_HINT,
        path=chunk.path,
        text=chunk.text,
    )
    return SYSTEM, user


def generate_for_chunk(
    chunk: Chunk,
    n: int,
    types: list[str],
    lang: str,
    chat_fn,
) -> list[dict]:
    system, user = build_prompts(chunk, n, types, lang)
    raw = chat_fn(system, user)
    return parse_questions(raw, chunk)


def parse_questions(raw: str, chunk: Chunk) -> list[dict]:
    data = parse_json(raw)
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("questions") or data.get("items") or []
    else:
        items = []
    if not isinstance(items, list):
        items = []
    out: list[dict] = []
    for q in items:
        if not isinstance(q, dict):
            continue
        q.setdefault("type", "single")
        q.setdefault("options", [])
        q.setdefault("explanation", "")
        q.setdefault("bloom", "理解")
        q.setdefault("difficulty", "medium")
        q["chunk_path"] = chunk.path
        out.append(q)
    return out


# ---------------------------------------------------------------- 离线模式

DEF_RE = re.compile(r"^(?P<term>[^，。；：、]{2,26}?)(?:是指|指的是|定义为)(?P<body>.{6,})$")
BLANK_RES = [
    re.compile(r"(?P<v>记为|称为|叫做)(?P<obj>[^，。；、\s]{1,20})"),
    re.compile(r"(?P<v>分解为|分为|包括)(?P<obj>[^。；：、]{4,24})"),
    re.compile(r"(?P<v>取值范围是|通常为|通常是|一般取)(?P<obj>[^。；，]{2,20})"),
]
META_RE = re.compile(r"^(本章|本节|上文|综上|因此|所以|但是|然而|其|这|该|二者|上述|此外|同时)")
SENT_RE = re.compile(r"(?<=[。！？.!?])")


def offline_questions(chunk: Chunk, n: int) -> list[dict]:
    """无 API 时的确定性兜底：从定义句生成定义题与填空题。

    这不是"出题"，只是让整条流水线可跑通、可校验。
    evidence 一律取原句，因此必然通过溯源校验——正好用来测校验器本身。
    只认带定义/计量锚点的句子，宁可少出，不出噪音题。
    """
    body = chunk.text.replace("\n", "")
    sentences = [s.strip() for s in SENT_RE.split(body) if s.strip()]

    picked: list[dict] = []
    for sent in sentences:
        if len(picked) >= n:
            break
        if META_RE.match(sent) or not (20 <= len(sent) <= 160):
            continue
        item = _make_item(sent, chunk.path)
        if item:
            picked.append(item)
    return picked


def _make_item(sent: str, path: str) -> dict | None:
    base = {
        "type": "short",
        "bloom": "记忆",
        "difficulty": "easy",
        "options": [],
        "explanation": "（离线模式：由原文定义句直接改写，未经模型加工）",
        "evidence": sent,
        "chunk_path": path,
        "mock": True,
    }

    m = DEF_RE.match(sent)
    if m:
        body = m.group("body").strip().rstrip("。.")
        if len(body) >= 6:
            return {
                **base,
                "question": f"{m.group('term').strip()}是指什么？",
                "answer": body + "。",
            }

    for pat in BLANK_RES:
        m = pat.search(sent)
        if not m:
            continue
        obj = m.group("obj").strip()
        if not (1 <= len(obj) <= 24):
            continue
        blanked = sent[: m.start("obj")] + "＿＿＿＿" + sent[m.end("obj") :]
        return {
            **base,
            "type": "fill",
            "question": blanked.strip(),
            "answer": obj,
        }
    return None
