"""教材例题数据与「例题精解」页的回归测试。"""

from __future__ import annotations

import contextlib
import io
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
        self.assertNotIn('src="http', html)
        self.assertNotIn('href="http', html)
        self.assertNotIn("url(http", html)
        self.assertNotIn("@import", html)
        # KaTeX 必须整包内嵌，字体也不能留外部引用
        self.assertIn("katex.renderToString", html)
        self.assertIn("KaTeX_Main", html)
        self.assertNotIn("url(fonts/", html)

    def test_rich_escapes_and_formats(self):
        self.assertEqual(build_examples.rich("**粗**"), "<b>粗</b>")
        self.assertIn("&lt;script&gt;", build_examples.rich("<script>"))
        # 公式行交给 KaTeX，但标签里仍留线性写法，禁用脚本也能读
        out = build_examples.rich("x_{F} = 0.4")
        self.assertIn('data-tex="x_{F} = 0.4"', out)
        self.assertIn("x<sub>F</sub> = 0.4", out)

    def test_output_is_deterministic(self):
        html = build_examples.render(self.chapters())
        self.assertEqual(html, build_examples.render(self.chapters()))

    def test_build_main_writes_file(self):
        with contextlib.redirect_stdout(io.StringIO()):
            code = build_examples.main([])
        self.assertEqual(code, 0)
        target = build_examples.OUT / "examples.quiz.html"
        self.assertTrue(target.exists())
        self.assertGreater(target.stat().st_size, 50_000)


class TestFigures(unittest.TestCase):
    def chapters(self):
        return [(stem, examples.load(stem)) for stem in hgyl.ORDER if examples.EXPECTED[stem]]

    @staticmethod
    def refs(stem):
        return {
            str(item.get("figure", "")).strip()
            for item in examples.load(stem)["examples"]
            if str(item.get("figure", "")).strip()
        }

    def test_every_figure_is_indexed_and_stored(self):
        total = 0
        for stem in hgyl.ORDER:
            if not examples.EXPECTED[stem]:
                continue
            refs = self.refs(stem)
            if not refs:
                continue
            with self.subTest(stem=stem):
                index = examples.load_figures(stem)
                self.assertEqual(index.get("schema"), 1)
                self.assertEqual(index.get("chapter"), examples.chapter_name(stem))
                self.assertEqual(set(index.get("figures") or {}), refs)
                used = set()
                for key, meta in index["figures"].items():
                    path = examples.FIGDIR / meta["file"]
                    self.assertTrue(path.exists(), f"{stem} {key} 缺 {meta['file']}")
                    self.assertGreaterEqual(path.stat().st_size, 2000, key)
                    self.assertNotIn(meta["file"], used, f"{key} 与别图共用文件")
                    used.add(meta["file"])
                    self.assertRegex(meta["page"], r"^P\d+$")
                    self.assertGreaterEqual(meta["width"], 100)
                    self.assertLessEqual(meta["width"], 720)
                    self.assertGreater(meta["height"], 100)
                    total += 1
        self.assertEqual(total, 36)

    def test_render_embeds_every_figure(self):
        html = build_examples.render(self.chapters())
        self.assertEqual(html.count('<figure class="figbox">'), 36)
        self.assertEqual(html.count('data:image/webp;base64,'), 36)
        self.assertNotIn("附图 图", html)
        self.assertIn('id="lightbox"', html)
        self.assertIn('class="lb-close"', html)

    def test_figure_markup_keeps_intrinsic_size(self):
        html = build_examples.render(self.chapters())
        for block in re.findall(r'<figure class="figbox">.*?</figure>', html):
            self.assertRegex(block, r'<img src="data:image/webp;base64,[A-Za-z0-9+/=]+"')
            self.assertRegex(block, r'width="\d{3,4}" height="\d{3,4}"')
            self.assertIn("点击放大", block)


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