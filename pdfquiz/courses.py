"""课程注册表。

题库按课程分组：站点首页只列课程，进课程页才看到具体卷子。
课程信息写在仓库根目录的 courses.json 里，新增课程只要加一条，
不用改代码。

字段：
    id       课程标识，只允许小写字母、数字和连字符，同时作为默认页面名
    name     课程全名，页面标题用
    tagline  一句副标题，例如「期末复习 · 6 套题库」
    desc     课程说明
    coverage 覆盖范围（可省略）
    out      构建产物目录，里面要有 decks.json 和 <卷>.quiz.html
    prefix   卷子页面在 docs/ 下的文件名前缀，默认空（保持旧链接不变）
    decks    要收录的卷子 id，顺序即展示顺序
    page     课程页文件名，默认 <id>.html
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REGISTRY = "courses.json"
_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def load_courses(root: str | Path) -> list[dict]:
    path = Path(root) / REGISTRY
    if not path.exists():
        raise FileNotFoundError(f"找不到 {path}，无法确定有哪些课程")
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw.get("courses") if isinstance(raw, dict) else raw
    if not isinstance(items, list) or not items:
        raise ValueError(f"{path} 里没有课程")

    courses: list[dict] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{path} 的课程条目必须是对象")
        cid = str(item.get("id") or "").strip()
        if not _ID.match(cid):
            raise ValueError(f"课程 id 不合法：{cid!r}（只允许小写字母、数字、连字符）")
        if cid in seen:
            raise ValueError(f"课程 id 重复：{cid}")
        seen.add(cid)
        course = dict(item)
        course["id"] = cid
        course.setdefault("name", cid)
        course.setdefault("tagline", "")
        course.setdefault("desc", "")
        course.setdefault("coverage", "")
        course.setdefault("out", f"out_{cid}")
        course.setdefault("prefix", "")
        course.setdefault("page", f"{cid}.html")
        course["decks"] = [str(d) for d in (course.get("decks") or [])]
        courses.append(course)
    return courses


def course_page(course: dict) -> str:
    return course["page"]


def deck_page(course: dict, deck_id: str) -> str:
    return f"{course['prefix']}{deck_id}.html"


def find_course(courses: list[dict], cid: str) -> dict:
    for course in courses:
        if course["id"] == cid:
            return course
    raise KeyError(f"courses.json 里没有课程 {cid!r}")
