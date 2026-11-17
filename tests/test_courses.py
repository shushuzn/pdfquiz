"""课程注册表与两层页面生成测试。

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from pdfquiz.courses import course_page, deck_page, find_course, load_courses  # noqa: E402
import build_hub  # noqa: E402


DECKS = [
    {"id": "exam_a", "title": "某课程 · 期末模拟卷 A", "short": "模拟 A", "desc": "",
     "count": 10, "score": 100, "types": {"term": 10}},
    {"id": "terms", "title": "某课程 · 术语默写总表", "short": "默写", "desc": "",
     "count": 20, "score": 20, "types": {"term": 20}},
]

COURSE = {
    "id": "demo-course",
    "name": "某课程",
    "tagline": "期末复习 · 2 套题库",
    "desc": "示例课程。",
    "coverage": "UNIT 1、2",
    "out": "out_demo",
    "prefix": "",
    "decks": ["exam_a", "terms"],
    "page": "demo-course.html",
}


class TestRegistry(unittest.TestCase):
    def write(self, payload: object) -> Path:
        tmp = Path(tempfile.mkdtemp())
        (tmp / "courses.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return tmp

    def test_defaults_fill_in(self):
        root = self.write({"courses": [{"id": "chem", "name": "化学"}]})
        (course,) = load_courses(root)
        self.assertEqual(course["page"], "chem.html")
        self.assertEqual(course["prefix"], "")
        self.assertEqual(course["out"], "out_chem")
        self.assertEqual(course["decks"], [])

    def test_duplicate_id_rejected(self):
        root = self.write({"courses": [{"id": "a"}, {"id": "a"}]})
        with self.assertRaises(ValueError):
            load_courses(root)

    def test_bad_id_rejected(self):
        root = self.write({"courses": [{"id": "../etc"}]})
        with self.assertRaises(ValueError):
            load_courses(root)

    def test_missing_registry(self):
        with self.assertRaises(FileNotFoundError):
            load_courses(tempfile.mkdtemp())

    def test_repo_registry_is_valid(self):
        courses = load_courses(ROOT)
        self.assertTrue(courses)
        find_course(courses, courses[0]["id"])
        with self.assertRaises(KeyError):
            find_course(courses, "no-such-course")


class TestPages(unittest.TestCase):
    def test_deck_page_prefix(self):
        self.assertEqual(deck_page(COURSE, "exam_a"), "exam_a.html")
        self.assertEqual(deck_page({**COURSE, "prefix": "demo-"}, "exam_a"), "demo-exam_a.html")

    def test_home_lists_courses_not_decks(self):
        course = {k: COURSE[k] for k in COURSE}
        html = build_hub.render_home([course], {course["id"]: DECKS})
        self.assertIn('href="demo-course.html"', html)
        self.assertIn("进入课程", html)
        # 首页不能直接链到卷子，否则又会「一进来就是某张卷」
        self.assertNotIn('href="exam_a.html"', html)
        self.assertNotIn('href="terms.html"', html)
        self.assertIn("共 30 题", html)

    def test_course_page_lists_decks_without_course_prefix(self):
        html = build_hub.render_course(COURSE, DECKS)
        self.assertIn('href="exam_a.html"', html)
        self.assertIn('href="index.html"', html)
        self.assertIn("全部课程", html)
        self.assertIn("<h2>期末模拟卷 A</h2>", html)
        self.assertNotIn("某课程 · 期末模拟卷 A", html)

    def test_hublink_retargeted(self):
        page = ('<a class="hub-link" href="index.html">'
                '<svg viewBox="0 0 24 24"></svg>全部试卷</a>')
        out = build_hub.retarget_hublink(page, "demo-course.html")
        self.assertIn('href="demo-course.html"', out)
        self.assertIn("返回课程", out)
        self.assertNotIn("全部试卷", out)
        self.assertIn("<svg", out)


if __name__ == "__main__":
    unittest.main()
