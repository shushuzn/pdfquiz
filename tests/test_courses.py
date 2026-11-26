"""课程注册表与两层页面生成测试。

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import contextlib
import io
import json
import re
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

    def test_course_can_override_deck_role(self):
        course = {**COURSE, "roles": {"terms": ["释义", "写释义"]}}
        html = build_hub.render_course(course, DECKS)
        self.assertIn('<span class="tag">释义</span>', html)
        self.assertIn("写释义", html)
        self.assertNotIn("刷术语", html)

    def test_hublink_retargeted(self):
        page = ('<a class="crumb hub-link" href="index.html">'
                '<svg viewBox="0 0 24 24"></svg>全部试卷</a>')
        out = build_hub.retarget_hublink(page, "demo-course.html")
        self.assertIn('href="demo-course.html"', out)
        self.assertIn('class="crumb hub-link"', out)
        self.assertIn("返回课程", out)
        self.assertNotIn("全部试卷", out)
        self.assertIn("<svg", out)


class TestCli(unittest.TestCase):
    def test_unknown_course_reports_error(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = build_hub.main(["--course", "no-such-course"])
        self.assertEqual(code, 2)
        self.assertIn("没有课程", out.getvalue())

    def test_missing_course_argument(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = build_hub.main(["--course"])
        self.assertEqual(code, 2)
        self.assertIn("--course", out.getvalue())


class TestDeckFallback(unittest.TestCase):
    """decks.json 缺失时，从既有课程页反推卷子清单。"""

    LEGACY_CARD = """<a class="card" href="terms.html">
        <div class="card-top"><span class="tag">默写</span><span class="nums"><b>20</b> 题 · <b>20</b> 分</span></div>
        <h2>术语默写总表</h2>
        <p>课程全部术语。</p>
        <div class="chips"><span class="chip">术语 <b>20</b></span></div>
        <span class="go">刷术语</span>
      </a>"""

    def make_root(self) -> Path:
        tmp = Path(tempfile.mkdtemp())
        (tmp / "docs").mkdir()
        return tmp

    def test_bank_total_dedupes_shared_questions(self):
        root = self.make_root()

        def page(*stems: str) -> str:
            qs = [{"t": "single", "q": s, "o": ["A", "B"], "a": ["A"]} for s in stems]
            return ("<script>window.__QUIZ__ = "
                    + json.dumps({"questions": qs}, ensure_ascii=False)
                    + ";</script>")

        (root / "docs" / "exam_a.html").write_text(page("q1", "q2"), encoding="utf-8")
        (root / "docs" / "terms.html").write_text(page("q2", "q3"), encoding="utf-8")
        self.assertEqual(build_hub.bank_total(COURSE, DECKS, root / "docs"), 3)
        # 卷子页面缺失时不能瞎猜，返回 None 让调用方退回旧口径
        self.assertIsNone(build_hub.bank_total(COURSE, DECKS, root / "docs" / "nope"))

    def test_course_page_roundtrip(self):
        page = build_hub.render_course(COURSE, DECKS)
        parsed = build_hub.parse_decks(page, COURSE)
        self.assertEqual([d["id"] for d in parsed], ["exam_a", "terms"])
        self.assertEqual(parsed[0]["count"], 10)
        self.assertEqual(parsed[0]["score"], 100)
        self.assertEqual(parsed[0]["types"], {"term": 10})
        self.assertEqual(parsed[1]["desc"], "")
        # 卡片上已去掉课程前缀，重新渲染不会再叠加
        self.assertIn("<h2>期末模拟卷 A</h2>", build_hub.render_course(COURSE, parsed))

    def test_legacy_page_without_data_attrs(self):
        parsed = build_hub.parse_decks(self.LEGACY_CARD, COURSE)
        self.assertEqual(len(parsed), 1)
        deck = parsed[0]
        self.assertEqual(deck["id"], "terms")
        self.assertEqual(deck["title"], "术语默写总表")
        self.assertEqual(deck["count"], 20)
        self.assertEqual(deck["score"], 20)
        self.assertEqual(deck["types"], {"term": 20})

    def test_missing_decks_json_uses_course_page(self):
        root = self.make_root()
        (root / "docs" / "demo-course.html").write_text(
            build_hub.render_course(COURSE, DECKS), encoding="utf-8")
        decks = build_hub.load_decks(COURSE, root / "docs", root)
        self.assertEqual([d["id"] for d in decks], ["exam_a", "terms"])
        html = build_hub.render_home([COURSE], {COURSE["id"]: decks})
        self.assertIn('href="demo-course.html"', html)
        self.assertIn("共 30 题", html)

    def test_no_source_at_all(self):
        root = self.make_root()
        self.assertEqual(build_hub.load_decks(COURSE, root / "docs", root), [])

    def test_decks_json_wins_over_page(self):
        root = self.make_root()
        out = root / "out_demo"
        out.mkdir()
        (out / "decks.json").write_text(json.dumps(DECKS, ensure_ascii=False), encoding="utf-8")
        (root / "docs" / "demo-course.html").write_text(self.LEGACY_CARD, encoding="utf-8")
        decks = build_hub.load_decks(COURSE, root / "docs", root)
        self.assertEqual([d["id"] for d in decks], ["exam_a", "terms"])
        self.assertEqual(decks[0]["title"], "某课程 · 期末模拟卷 A")


class TestExamplesDeck(unittest.TestCase):
    EXAMPLES = {
        "id": "examples", "title": "某课程 · 教材例题精解", "short": "例题",
        "desc": "教材例题。", "count": 93, "score": 0, "types": {},
        "quiz": False, "unit": "例",
    }

    def test_examples_are_shown_but_not_counted_as_questions(self):
        decks = DECKS + [self.EXAMPLES]
        html = build_hub.render_course(COURSE, decks)
        self.assertIn("题库 30 题", html)
        self.assertIn("教材例题 93 例", html)
        self.assertIn("<b>93</b> 例", html)
        self.assertIn("例题按教材原题单独成册", html)
        self.assertNotIn("3 套合计", html)

    def test_home_deck_count_excludes_examples(self):
        html = build_hub.render_home(
            [COURSE], {COURSE["id"]: DECKS + [self.EXAMPLES]})
        self.assertIn("共 2 套题库", html)
        self.assertIn("教材例题 93 例", html)

    def test_card_roundtrip_keeps_unit_and_quiz_flag(self):
        course = {**COURSE, "decks": ["exam_a", "terms", "examples"]}
        html = build_hub.render_course(course, DECKS + [self.EXAMPLES])
        parsed = build_hub.parse_decks(html, course)
        self.assertEqual([d["id"] for d in parsed], ["exam_a", "terms", "examples"])
        self.assertTrue(parsed[0]["quiz"])
        self.assertFalse(parsed[-1]["quiz"])
        self.assertEqual(parsed[-1]["unit"], "例")

    def test_bank_total_skips_examples_page(self):
        root = Path(tempfile.mkdtemp())
        docs = root / "docs"
        docs.mkdir()

        def page(stem: str) -> str:
            return ("<script>window.__QUIZ__ = "
                    + json.dumps({"questions": [
                        {"t": "single", "q": stem, "o": ["A", "B"], "a": ["A"]}
                    ]}, ensure_ascii=False)
                    + ";</script>")

        (docs / "exam_a.html").write_text(page("q1"), encoding="utf-8")
        (docs / "terms.html").write_text(page("q2"), encoding="utf-8")
        # 例题页没有 __QUIZ__，不应把去重统计逼回旧口径
        (docs / "examples.html").write_text("<html>例题</html>", encoding="utf-8")
        self.assertEqual(
            build_hub.bank_total(COURSE, DECKS + [self.EXAMPLES], docs), 2)


class TestCommittedSite(unittest.TestCase):
    """回归：首页必须列出所有已有课程页的课程。"""

    def test_index_lists_every_built_course(self):
        index = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        for course in load_courses(ROOT):
            page_name = course_page(course)
            page = ROOT / "docs" / page_name
            if not page.exists():
                continue
            decks = build_hub.parse_decks(page.read_text(encoding="utf-8"), course)
            if not decks:
                continue
            with self.subTest(course=course["id"]):
                card = re.search(
                    rf'<a class="card" href="{re.escape(page_name)}">(.*?)</a>',
                    index, re.S)
                self.assertIsNotNone(card, f"{course['id']} 未出现在首页")
                quiz = [d for d in decks if d.get("quiz", True)]
                total = sum(d["count"] for d in quiz)
                unique = build_hub.bank_total(course, decks)
                count = total if unique is None else unique
                self.assertIn(f"<b>{len(quiz)}</b> 套", card.group(1))
                self.assertIn(f"<b>{count}</b> 题", card.group(1))

    def test_course_page_reports_unique_bank(self):
        """课程页的「题库 N 题」必须是去重后的题数，不是各套简单相加。"""
        for course in load_courses(ROOT):
            page_name = course_page(course)
            page = ROOT / "docs" / page_name
            if not page.exists():
                continue
            decks = build_hub.parse_decks(page.read_text(encoding="utf-8"), course)
            unique = build_hub.bank_total(course, decks)
            if unique is None:
                continue
            with self.subTest(course=course["id"]):
                self.assertIn(f"题库 {unique} 题", page.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
