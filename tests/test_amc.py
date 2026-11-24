"""《先进材料研究进展C》题库的回归测试。

    python -m unittest discover -s tests -v

盯三件事：分章草稿还在不在、每道题的 evidence 还能不能在课件转录稿里逐字找到、
四套题库的题量与模拟卷满分有没有被改坏。
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import build_amc  # noqa: E402
from pdfquiz import amcbank  # noqa: E402
from pdfquiz.courses import find_course, load_courses  # noqa: E402
from pdfquiz.verify import evidence_ok  # noqa: E402

KINDS = amcbank.KINDS


def load_data(stem: str) -> dict:
    return json.loads((build_amc.PAPERS / f"{stem}.json").read_text(encoding="utf-8"))


class TestDrafts(unittest.TestCase):
    def test_all_chapters_present(self):
        for stem in build_amc.CHAPTERS:
            with self.subTest(stem=stem):
                data = load_data(stem)
                self.assertTrue(data.get("chapter", "").startswith("第"))
                counts = amcbank.counts(data)
                for kind in KINDS:
                    self.assertGreaterEqual(counts[kind], 3, f"{stem} 的 {kind} 太少")

    def test_every_evidence_is_verbatim(self):
        for stem in build_amc.CHAPTERS:
            corpus = (build_amc.CORPUS / f"{stem}.md").read_text(encoding="utf-8")
            data = load_data(stem)
            for q in data["questions"]:
                with self.subTest(stem=stem, q=q["question"][:20]):
                    ok, why = evidence_ok(q.get("evidence", ""), corpus)
                    self.assertTrue(ok, f"{q['question'][:20]} —— {why}")

    def test_explanations_written(self):
        for stem in build_amc.CHAPTERS:
            data = load_data(stem)
            for q in data["questions"]:
                self.assertTrue(str(q.get("explanation", "")).strip(), q["question"][:20])
                self.assertNotIn("evidence", q["explanation"])


class TestStorage(unittest.TestCase):
    def test_flat_schema(self):
        total = 0
        for stem in build_amc.CHAPTERS:
            with self.subTest(stem=stem):
                data = load_data(stem)
                self.assertEqual(data.get("schema"), amcbank.SCHEMA_VERSION)
                self.assertNotIn("single", data)
                self.assertNotIn("term", data)
                self.assertEqual(len(data["questions"]), 46)
                total += len(data["questions"])
        self.assertEqual(total, 460)

    def test_ids_are_unique_and_typed(self):
        seen: set[str] = set()
        for stem in build_amc.CHAPTERS:
            for q in load_data(stem)["questions"]:
                with self.subTest(stem=stem, qid=q["id"]):
                    m = amcbank.ID_RE.fullmatch(q["id"])
                    self.assertIsNotNone(m, q["id"])
                    self.assertEqual(m["stem"], stem)
                    self.assertEqual(m["kind"], q["type"])
                    self.assertNotIn(q["id"], seen)
                    seen.add(q["id"])

    def test_metadata_enums(self):
        for stem in build_amc.CHAPTERS:
            for q in load_data(stem)["questions"]:
                with self.subTest(stem=stem, q=q["id"]):
                    self.assertIn(q["difficulty"], amcbank.DIFFICULTIES)
                    self.assertIn(q["bloom"], amcbank.BLOOMS)
                    if q["type"] == "term":
                        self.assertEqual(q.get("mode"), "explain")
                    else:
                        self.assertNotIn("mode", q)

    def test_questions_grouped_by_type(self):
        for stem in build_amc.CHAPTERS:
            order = [amcbank.KINDS.index(q["type"]) for q in load_data(stem)["questions"]]
            self.assertEqual(order, sorted(order), f"{stem} 的题型分组被打乱")

    def test_files_are_canonical(self):
        for stem in build_amc.CHAPTERS:
            path = build_amc.PAPERS / f"{stem}.json"
            self.assertEqual(
                amcbank.dumps(load_data(stem)), path.read_text(encoding="utf-8"), stem
            )


class TestSections(unittest.TestCase):
    def test_slide_numbers_map_to_sections(self):
        self.assertEqual(build_amc.section_of("ch02", "S9"), "第二节 仿生的诞生")
        self.assertEqual(build_amc.section_of("ch02", "S39"), "第五节 仿生材料的设计及举例")
        self.assertEqual(build_amc.section_of("ch03", "S55"), "5 木材科学与创新发展")
        self.assertEqual(build_amc.section_of("ch04", "S11"), "评价指标与测试基础")
        self.assertEqual(build_amc.section_of("ch03", "S28"), "4 生物质能源材料")
        self.assertEqual(build_amc.section_of("ch04", "S98"), "拓展资源")
        self.assertEqual(build_amc.section_of("ch01", "S1"), "课程导入")
        self.assertEqual(build_amc.section_of("ch09", "S3"), "课程导入")
        self.assertEqual(build_amc.section_of("ch10", "S45"), "碳/碳复合材料")
        self.assertEqual(build_amc.section_of("ch08", "S5"), "1.1 什么是活性炭")
        self.assertEqual(build_amc.section_of("ch08", "S60"), "2 炭黑的生产和应用")

    def test_unknown_slide_falls_back(self):
        self.assertEqual(build_amc.section_of("ch99", "S3"), "未分节")


class TestDecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        chapters, corpora = build_amc.load_chapters()
        cls.pool, cls.rejected = build_amc.verified(chapters, corpora)

    def test_nothing_rejected(self):
        self.assertEqual(self.rejected, [])

    def test_exam_sums_to_100(self):
        deck = next(d for d in build_amc.DECKS if d["id"] == "exam")
        qs = build_amc.deck_questions(deck, [dict(q) for q in self.pool])
        self.assertEqual(sum(int(q["score"]) for q in qs), 100)
        kinds = [q["_kind"] for q in qs]
        self.assertEqual(kinds.count("single"), 20)
        self.assertEqual(kinds.count("short"), 4)
        # 每章都要有题，否则模拟卷只考了半本书
        self.assertEqual(len({q["_stem"] for q in qs}), len(build_amc.CHAPTERS))

    def test_practice_sorted_by_chapter(self):
        deck = next(d for d in build_amc.DECKS if d["id"] == "practice")
        qs = build_amc.deck_questions(deck, [dict(q) for q in self.pool])
        order = [q["_stem"] for q in qs]
        self.assertEqual(order, sorted(order, key=build_amc.CHAPTERS.index))


class TestRegistry(unittest.TestCase):
    def test_amc_registered_with_prefix(self):
        course = find_course(load_courses(ROOT), "amc")
        self.assertEqual(course["out"], "out_amc")
        self.assertEqual(course["prefix"], "amc-")
        self.assertEqual(course["decks"], ["exam", "objective", "practice", "terms"])
        self.assertEqual(course["page"], "amc.html")

    def test_deck_pages_do_not_collide(self):
        courses = load_courses(ROOT)
        amc = find_course(courses, "amc")
        poly = find_course(courses, "polymer-en")
        amc_pages = {build_amc_deck_page(amc, d) for d in amc["decks"]}
        poly_pages = {build_amc_deck_page(poly, d) for d in poly["decks"]}
        self.assertFalse(amc_pages & poly_pages)


def build_amc_deck_page(course: dict, deck_id: str) -> str:
    from pdfquiz.courses import deck_page

    return deck_page(course, deck_id)


if __name__ == "__main__":
    unittest.main()
