"""题目校验：溯源回查、结构检查、去重。

这是整条流水线里唯一能挡住幻觉的环节，所以宁可错杀：

  1. evidence 必须能在原文里找到（规范化后逐字包含）。
     模型最爱改一两个字、合并两句、把"不"字悄悄去掉——都能被抓到。
  2. 选项/答案结构必须自洽。
  3. 题干高度相似的去重。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

MIN_EVIDENCE = 10
DUP_THRESHOLD = 0.72

_PUNCT = re.compile(r"[\s，。、；：！？,.;:!?\"'“”‘’（）()\[\]【】《》<>—\-–…·`*_|/\\]+")
_MD = re.compile(r"[*_`#>]+")
_LABEL = re.compile(r"^\s*[A-Ha-h]\s*[\.\、\)．:：]\s*")


def _strip_label(option: str) -> str:
    return _LABEL.sub("", option)


@dataclass
class Report:
    accepted: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.accepted) + len(self.rejected)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = _MD.sub("", text)
    text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def squash(text: str) -> str:
    return _PUNCT.sub("", normalize(text))


def evidence_ok(evidence: str, source: str) -> tuple[bool, str]:
    ev = normalize(evidence)
    if len(ev) < MIN_EVIDENCE:
        return False, f"evidence 过短（{len(ev)} 字）"
    if ev in normalize(source):
        return True, ""
    if squash(ev) and squash(ev) in squash(source):
        return True, "evidence 仅标点/空白有差异"
    return False, "evidence 在原文中找不到"


def check_structure(q: dict) -> tuple[bool, str]:
    qtype = str(q.get("type", "single")).lower()
    question = normalize(q.get("question", ""))
    if len(question) < 6:
        return False, "题干为空或过短"

    if qtype in {"single", "multiple"}:
        options = [normalize(o) for o in q.get("options") or [] if normalize(o)]
        if len(options) < 3:
            return False, f"选项不足（{len(options)} 个）"
        if len({squash(_strip_label(o)) for o in options}) != len(options):
            return False, "存在重复选项"
        ans = q.get("answer")
        letters = {str(a).strip().upper()[:1] for a in (ans if isinstance(ans, list) else [ans])}
        valid = {chr(ord("A") + i) for i in range(len(options))}
        if not letters or not letters <= valid:
            return False, f"答案 {ans!r} 不在选项范围内"
        if qtype == "single" and len(letters) != 1:
            return False, "单选题答案多于一个"
        if qtype == "multiple" and len(letters) < 2:
            return False, "多选题答案只有一个"

    elif qtype == "truefalse":
        if str(q.get("answer")).strip().lower() not in {"true", "false", "对", "错", "t", "f"}:
            return False, "判断题答案非布尔"

    elif qtype in {"short", "fill"}:
        if len(normalize(q.get("answer", ""))) < 2:
            return False, "参考答案为空"

    return True, ""


def _grams(text: str, n: int = 3) -> set[str]:
    s = squash(text)
    return {s[i : i + n] for i in range(max(0, len(s) - n + 1))}


def is_duplicate(question: str, seen: list[set[str]]) -> bool:
    g = _grams(question)
    if not g:
        return True
    return any(len(g & o) / len(g | o) >= DUP_THRESHOLD for o in seen if o)


def verify(questions: list[dict], source_text: str) -> Report:
    report = Report()
    seen: list[set[str]] = []

    for q in questions:
        ok, why = check_structure(q)
        if ok:
            ok, why = evidence_ok(q.get("evidence", ""), source_text)
        if ok and is_duplicate(q.get("question", ""), seen):
            ok, why = False, "与已有题目高度重复"
        if ok:
            seen.append(_grams(q.get("question", "")))
            report.accepted.append(q)
        else:
            report.rejected.append({"question": q.get("question", ""), "reason": why})
    return report


def stats(questions: list[dict]) -> dict:
    def tally(key: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for q in questions:
            k = str(q.get(key, "未标注"))
            out[k] = out.get(k, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    return {
        "type": tally("type"),
        "bloom": tally("bloom"),
        "difficulty": tally("difficulty"),
    }
