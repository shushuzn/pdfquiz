"""分章题库的存储格式（v2）：扁平题目列表 + 显式题型 + 稳定 ID。

v1 把题型当顶层键（`single`/`multiple`/...），题目本身不带 `type`，一道题
是哪一类完全由它所在的数组决定。这样存有三个问题：题目离开数组就失去题型；
数组下标是唯一身份，插一道题后面全部错位；校验与构建各写一套“按题型遍历”
的代码，容易漏题。

v2 统一成：

    {
      "schema": 2,
      "chapter": "第一章 先进材料研究进展概论",
      "questions": [
        {"id": "ch01-single-001", "type": "single", "question": "...", ...}
      ]
    }

`id` 由章、题型与三位序号组成，写入后不再随排序变化；新增题只追加序号。
`normalize()` 可以把 v1、缺 ID 或顺序混乱的草稿规范回 v2，`validate()` 是
工具与测试共用的存储层校验。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SCHEMA_VERSION = 2

KINDS = ("single", "multiple", "truefalse", "fill", "short", "term")
TERM_MODES = ("translate", "explain")
DIFFICULTIES = ("easy", "medium", "hard")
BLOOMS = ("记忆", "理解", "应用", "分析", "评价", "创造")
BLOOM_ALIASES = {"识记": "记忆"}

ID_RE = re.compile(
    r"^(?P<stem>ch\d{2})-(?P<kind>single|multiple|truefalse|fill|short|term)-(?P<num>\d{3})$"
)
REF_RE = re.compile(r"^S\d+$")

COMMON_FIELDS = ("id", "type", "question", "answer", "explanation", "evidence", "ref")
OPTION_KINDS = ("single", "multiple")
QUESTION_FIELDS = ("id", "type", "mode", "question", "options", "answer", "explanation", "evidence", "ref", "difficulty", "bloom")
ALLOWED_FIELDS = frozenset(QUESTION_FIELDS)


class BankError(ValueError):
    """存储格式不合法。消息里带章与题号，方便直接定位。"""


def read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BankError(f"{path.name} 不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise BankError(f"{path.name} 顶层必须是对象")
    return data


def load(path: Path) -> dict:
    """读取并校验 v2 草稿；v1 请先用 normalize() 迁移。"""
    data = read(path)
    errors = validate(data, path.stem)
    if errors:
        raise BankError("\n".join(errors))
    return data


def by_kind(data: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {kind: [] for kind in KINDS}
    for q in data.get("questions") or []:
        out[q["type"]].append(q)
    return out


def counts(data: dict) -> dict[str, int]:
    return {kind: len(items) for kind, items in by_kind(data).items()}


def validate(data: dict, stem: str) -> list[str]:
    """只查存储层：顶层结构、ID、题型、枚举与字段有无。

    选项与答案是否自洽仍交给 `verify.check_structure`，避免两套规则分叉。
    """
    errors: list[str] = []
    extra = set(data) - {"schema", "chapter", "questions"}
    if extra:
        errors.append(f"{stem} 顶层有未知字段：{', '.join(sorted(extra))}")
    if data.get("schema") != SCHEMA_VERSION:
        errors.append(f"{stem} schema 应为 {SCHEMA_VERSION}，实际为 {data.get('schema')!r}")
    if not str(data.get("chapter", "")).strip():
        errors.append(f"{stem} 缺 chapter")
    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        errors.append(f"{stem} 的 questions 必须是非空数组")
        return errors

    seen: set[str] = set()
    for i, q in enumerate(questions):
        where = f"{stem} questions[{i}]"
        if not isinstance(q, dict):
            errors.append(f"{where} 不是对象")
            continue
        unknown = set(q) - ALLOWED_FIELDS
        if unknown:
            errors.append(f"{where} 有未知字段：{', '.join(sorted(unknown))}")
        missing = [f for f in COMMON_FIELDS if f not in q]
        if missing:
            errors.append(f"{where} 缺字段：{', '.join(missing)}")
            continue
        kind = q.get("type")
        if kind not in KINDS:
            errors.append(f"{where} type 非法：{kind!r}")
            continue
        mode = q.get("mode")
        if mode is not None:
            if kind != "term":
                errors.append(f"{where} 只有 term 题可以带 mode")
            elif mode not in TERM_MODES:
                errors.append(f"{where} mode 非法：{mode!r}，应为 {'/'.join(TERM_MODES)}")
        m = ID_RE.fullmatch(str(q.get("id", "")))
        if not m:
            errors.append(f"{where} id 应形如 {stem}-{kind}-001")
        else:
            if m["stem"] != stem:
                errors.append(f"{where} id 的章前缀是 {m['stem']}，应为 {stem}")
            if m["kind"] != kind:
                errors.append(f"{where} id 的题型是 {m['kind']}，与 type={kind} 不一致")
        qid = str(q.get("id", ""))
        if qid in seen:
            errors.append(f"{where} id 重复：{qid}")
        seen.add(qid)
        for field in COMMON_FIELDS:
            if not str(q.get(field, "")).strip():
                errors.append(f"{where} {field} 为空")
        if not REF_RE.fullmatch(str(q.get("ref", ""))):
            errors.append(f"{where} ref 应为 S12 这样的幻灯片号")
        if q.get("difficulty") not in DIFFICULTIES:
            errors.append(f"{where} difficulty 非法：{q.get('difficulty')!r}")
        if q.get("bloom") not in BLOOMS:
            errors.append(f"{where} bloom 非法：{q.get('bloom')!r}")
        options = q.get("options")
        if kind in OPTION_KINDS:
            if not isinstance(options, list) or len(options) < 3:
                errors.append(f"{where} {kind} 至少需要 3 个选项")
        elif options:
            errors.append(f"{where} {kind} 不应带 options")
    return errors


def normalize(data: dict, stem: str) -> dict:
    """把 v1 / 残缺 v2 规范成 v2，保留已有 ID 与题内顺序。

    - v1 按 KINDS 顺序展开，题型写进每道题；
    - 题目按题型分组排列，组内保持原顺序；
    - 缺 ID 的题追加该题型当前最大序号 +1，已有 ID 不改；
    - `识记` 统一为 `记忆`。
    """
    raw = data.get("questions")
    if raw is None:
        raw = []
        for kind in KINDS:
            for q in data.get(kind) or []:
                item = dict(q)
                item["type"] = kind
                raw.append(item)
    if not isinstance(raw, list):
        raise BankError(f"{stem} 的 questions 必须是数组")

    groups: dict[str, list[dict]] = {kind: [] for kind in KINDS}
    for i, q in enumerate(raw):
        if not isinstance(q, dict):
            raise BankError(f"{stem} 第 {i} 题不是对象")
        kind = q.get("type")
        if kind not in KINDS:
            raise BankError(f"{stem} 第 {i} 题 type 非法：{kind!r}")
        unknown = set(q) - ALLOWED_FIELDS
        if unknown:
            raise BankError(f"{stem} 第 {i} 题有未知字段：{', '.join(sorted(unknown))}")
        item = {k: q[k] for k in QUESTION_FIELDS if k in q}
        bloom = item.get("bloom")
        item["bloom"] = BLOOM_ALIASES.get(bloom, bloom)
        groups[kind].append(item)

    used: set[str] = set()
    for kind, items in groups.items():
        prefix = f"{stem}-{kind}-"
        for item in items:
            qid = str(item.get("id", ""))
            if not qid:
                continue
            m = ID_RE.fullmatch(qid)
            if not m or not qid.startswith(prefix):
                raise BankError(f"{stem} {kind} 的 id 与题型不匹配：{qid}")
            if qid in used:
                raise BankError(f"{stem} id 重复：{qid}")
            used.add(qid)
    for kind, items in groups.items():
        prefix = f"{stem}-{kind}-"
        seq = [
            int(m["num"])
            for item in items
            if (m := ID_RE.fullmatch(str(item.get("id", ""))))
        ]
        nxt = max(seq, default=0) + 1
        for item in items:
            if not item.get("id"):
                item["id"] = f"{prefix}{nxt:03d}"
                nxt += 1

    ordered: list[dict] = []
    for kind in KINDS:
        for item in groups[kind]:
            item["type"] = kind
            ordered.append({k: item[k] for k in QUESTION_FIELDS if k in item})

    out = {"schema": SCHEMA_VERSION, "chapter": data.get("chapter", ""), "questions": ordered}
    errors = validate(out, stem)
    if errors:
        raise BankError("\n".join(errors))
    return out


def dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def dump(path: Path, data: dict) -> None:
    path.write_text(dumps(data), encoding="utf-8")
