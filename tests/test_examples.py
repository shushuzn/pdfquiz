"""教材例题数据与「例题精解」页的回归测试。"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import build_examples  # noqa: E402
import examples  # noqa: E402
import hgyl  # noqa: E402


class TestExampleData(unittest.TestCase):
    def test_all_chapters_present_with_expected_counts(self):
        for stem, expected in examples.EXPECTED.items():
            with self.subTest(stem=stem):
                path = examples.path_of(stem)
                if expected:
                    self.assertTrue(path.exists(), f"{stem} 缺文件")
                    self.assertEqual(len(examples.load(stem)["examples"]), expected)
                else:
                    self.assertFalse(path.exists(), f"{stem} 没有例题，不该有文件")

    def test_total_is_93(self):
        self.assertEqual(examples.total(), 93)

    def test_every_record_valid(self):
        self.assertEqual(examples.validate_all(), [])

    def test_labels_are_sequential_and_refs_in_chapter(self):
        for stem in hgyl.ORDER:
            if not examples.EXPECTED[stem]:
                continue
            start, end = examples.page_range(stem)
            data = examples.load(stem)
            chapter_no = int(stem[2:])
            for i, item in enumerate(data["examples"], 1):
                with self.subTest(stem=stem, i=i):
                    self.assertEqual(item["label"], f"例{chapter_no}-{i}")
                    self.assertEqual(item["id"], f"{stem}-ex-{i:03d}")
                    page = int(re.match(r"P(\d+)", item["ref"]).group(1))
                    self.assertGreaterEqual(page, start)
                    self.assertLessEqual(page, end)

    def test_solutions_are_more_than_answers(self):
        for stem in hgyl.ORDER:
            if not examples.EXPECTED[stem]:
                continue
            for item in examples.load(stem)["examples"]:
                with self.subTest(stem=stem, label=item["label"]):
                    self.assertGreaterEqual(len(item["solution"]), 40)
                    self.assertGreaterEqual(len(item["problem"]), 20)
                    self.assertLessEqual(len(item["answer"]), 400)


class TestRender(unittest.TestCase):
    def chapters(self):
        return [(stem, examples.load(stem)) for stem in hgyl.ORDER if examples.EXPECTED[stem]]

    def test_page_contains_every_example(self):
        html = build_examples.render(self.chapters())
        self.assertEqual(html.count('<article class="ex"'), 93)
        self.assertIn("例0-1", html)
        self.assertIn("例1-27", html)
        self.assertIn("例7-8", html)
        self.assertIn("教材 P4", html)
        self.assertIn("93 例", html)

    def test_page_is_self_contained(self):
        html = build_examples.render(self.chapters())
        self.assertNotIn("<link", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)

    def test_rich_escapes_and_formats(self):
        self.assertEqual(build_examples.rich("x_{F}"), "x<sub>F</sub>")
        self.assertEqual(build_examples.rich("m^{3}"), "m<sup>3</sup>")
        self.assertEqual(build_examples.rich("**粗**"), "<b>粗</b>")
        self.assertIn("&lt;script&gt;", build_examples.rich("<script>"))

    def test_output_is_deterministic(self):
        html = build_examples.render(self.chapters())
        self.assertEqual(html, build_examples.render(self.chapters()))

    def test_build_main_writes_file(self):
        code = build_examples.main([])
        self.assertEqual(code, 0)
        target = build_examples.OUT / "examples.quiz.html"
        self.assertTrue(target.exists())
        self.assertGreater(target.stat().st_size, 50_000)


class TestNoAsciiSuperscripts(unittest.TestCase):
    def test_raw_units_are_flagged(self):
        errs = examples.validate("ch00", {
            "schema": 1,
            "chapter": "绪论",
            "examples": [{
                "id": "ch00-ex-001", "label": "例0-1", "ref": "P4", "topic": "测试",
                "problem": "流量 3m3/h", "solution": "x" * 50, "answer": "1",
                "figure": "", "note": "",
            }],
        })
        self.assertTrue(any("上标" in e for e in errs), errs)

    def test_subscripted_symbols_are_not_flagged(self):
        errs = examples.validate("ch00", {
            "schema": 1,
            "chapter": "绪论",
            "examples": [{
                "id": "ch00-ex-001", "label": "例0-1", "ref": "P4", "topic": "测试",
                "problem": "冷却水 q_{m2}=5.75kg/s", "solution": "R_{s2}=4.5×10^{-4}m^{2}·°C/W" * 3,
                "answer": "1", "figure": "", "note": "",
            }],
        })
        self.assertFalse(any("上标" in e for e in errs), errs)

    def test_normalizer_fixes_common_forms(self):
        self.assertEqual(examples.normalize_text("3m3/h"), "3m^{3}/h")
        self.assertEqual(examples.normalize_text("2X10-3"), "2×10^{-3}")
        self.assertEqual(examples.normalize_text("H2O"), "H_{2}O")


if __name__ == "__main__":
    unittest.main()