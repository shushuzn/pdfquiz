"""《化工原理》题库的回归测试。

教材语料属于版权文本，不入库；本机没有 corpus_hgyl/ 时只跑存储与配置检查，
逐字回查那部分自动跳过。CI 上就是这样跑的。
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import build_hgyl  # noqa: E402
import hgyl  # noqa: E402
from check_hgyl import notation_ok  # noqa: E402
from pdfquiz import amcbank  # noqa: E402
from pdfquiz.courses import find_course, load_courses  # noqa: E402
from pdfquiz.verify import evidence_ok  # noqa: E402

KINDS = amcbank.KINDS
HAS_CORPUS = build_hgyl.CORPUS.exists()


def load(stem: str) -> dict:
    return json.loads((build_hgyl.PAPERS / f"{stem}.json").read_text(encoding="utf-8"))


class TestConfig(unittest.TestCase):
    def test_chapters_cover_the_book(self):
        starts = [page for _, page in hgyl.CHAPTERS.values()]
        self.assertEqual(starts, sorted(starts))
        self.assertEqual(starts[0], 1)

    def test_sections_reach_chapter_end(self):
        pages = [page for _, page in hgyl.CHAPTERS.values()]
        for i, stem in enumerate(hgyl.ORDER):
            end = (pages[i + 1] - 1) if i + 1 < len(pages) else 425
            with self.subTest(stem=stem):
                limits = [limit for limit, _ in hgyl.SECTIONS[stem]]
                self.assertEqual(limits, sorted(limits))
                self.assertEqual(limits[-1], end)

    def test_course_registered(self):
        course = find_course(load_courses(ROOT), "hgyl")
        self.assertEqual(course["out"], "out_hgyl")
        self.assertEqual(course["decks"], ["exam", "objective", "practice", "terms"])

    def test_exam_totals_100(self):
        exam = next(d for d in build_hgyl.DECKS if d["id"] == "exam")
        total = sum(exam["pick"][k] * exam["scores"][k] for k in exam["pick"])
        self.assertEqual(total, 100)


class TestNotation(unittest.TestCase):
    def test_rejects_ascii_units(self):
        for text in ("密度 998 kg/m3", "面积 3.5 m2", "10-3 Pa·s", "比热 4.18 kJ/(kg"):
            with self.subTest(text=text):
                ok, why = notation_ok({"question": text})
                self.assertFalse(ok, text)
                self.assertIn("上下标", why)

    def test_accepts_unicode(self):
        for text in ("密度 998 kg·m⁻³", "面积 3.5 m²", "10⁻³ Pa·s", "热流 5 kW·m⁻²·K⁻¹"):
            with self.subTest(text=text):
                ok, why = notation_ok({"question": text})
                self.assertTrue(ok, why)

    def test_ignores_evidence(self):
        ok, _ = notation_ok({"question": "黏度 10⁻³ Pa·s", "evidence": "原文写 10-3 Pa·s 与 m3"})
        self.assertTrue(ok)


class TestDrafts(unittest.TestCase):
    def test_every_chapter_has_a_draft(self):
        for stem in hgyl.ORDER:
            with self.subTest(stem=stem):
                data = load(stem)
                self.assertEqual(data["schema"], amcbank.SCHEMA_VERSION)
                self.assertEqual(data["chapter"], hgyl.CHAPTERS[stem][0])
                counts = amcbank.counts(data)
                floor = hgyl.minimum(stem)
                for kind in KINDS:
                    self.assertGreaterEqual(counts[kind], floor[kind], f"{stem} 的 {kind} 太少")

    @unittest.skipUnless(HAS_CORPUS, "教材语料不入库")
    def test_evidence_is_verbatim(self):
        for stem in hgyl.ORDER:
            corpus = (build_hgyl.CORPUS / f"{stem}.md").read_text(encoding="utf-8")
            for q in load(stem)["questions"]:
                with self.subTest(stem=stem, q=q["question"][:18]):
                    ok, why = evidence_ok(q["evidence"], corpus)
                    self.assertTrue(ok, f"{stem} {q['id']} —— {why}")

    @unittest.skipUnless(HAS_CORPUS, "教材语料不入库")
    def test_build_outputs_four_decks(self):
        chapters, corpora = build_hgyl.load_chapters()
        pool, rejected = build_hgyl.verified(chapters, corpora)
        self.assertFalse(rejected, rejected[:3])
        for deck in build_hgyl.DECKS:
            with self.subTest(deck=deck["id"]):
                self.assertTrue(build_hgyl.deck_questions(deck, [dict(q) for q in pool]))


if __name__ == "__main__":
    unittest.main()