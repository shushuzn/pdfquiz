"""存储格式 v2 的单元测试：迁移、ID 保留与拒绝非法结构。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pdfquiz import amcbank  # noqa: E402


def question(**over: object) -> dict:
    base = {
        "question": "这道题的题干足够长，可以用于存储格式测试",
        "options": ["甲", "乙", "丙", "丁"],
        "answer": "A",
        "explanation": "解析写明依据与错项原因",
        "evidence": "课件里的原句足够长，可以逐字回查",
        "ref": "S1",
        "difficulty": "easy",
        "bloom": "记忆",
    }
    base.update(over)
    return base


class TestNormalize(unittest.TestCase):
    def test_v1_is_flattened_with_ids(self):
        data = {
            "chapter": "第一章 测试",
            "single": [question(), question()],
            "term": [
                {
                    "question": "术语",
                    "answer": "释义",
                    "explanation": "解析",
                    "evidence": "课件原句足够长，可以回查",
                    "ref": "S2",
                    "difficulty": "easy",
                    "bloom": "识记",
                }
            ],
        }
        out = amcbank.normalize(data, "ch01")
        self.assertEqual(out["schema"], 2)
        self.assertNotIn("single", out)
        self.assertEqual([q["type"] for q in out["questions"]], ["single", "single", "term"])
        self.assertEqual(
            [q["id"] for q in out["questions"]],
            ["ch01-single-001", "ch01-single-002", "ch01-term-001"],
        )
        self.assertEqual(out["questions"][2]["bloom"], "记忆")
        self.assertNotIn("options", out["questions"][2])

    def test_existing_ids_are_kept_and_gaps_get_next_number(self):
        data = {
            "schema": 2,
            "chapter": "第一章 测试",
            "questions": [
                question(id="ch01-single-001", type="single"),
                question(id="ch01-single-003", type="single"),
                question(type="single"),
            ],
        }
        out = amcbank.normalize(data, "ch01")
        self.assertEqual(
            [q["id"] for q in out["questions"]],
            ["ch01-single-001", "ch01-single-003", "ch01-single-004"],
        )

    def test_duplicate_id_is_rejected(self):
        data = {
            "schema": 2,
            "chapter": "第一章 测试",
            "questions": [
                question(id="ch01-single-001", type="single"),
                question(id="ch01-single-001", type="single"),
            ],
        }
        with self.assertRaises(amcbank.BankError):
            amcbank.normalize(data, "ch01")

    def test_unknown_field_is_rejected(self):
        data = {
            "schema": 2,
            "chapter": "第一章 测试",
            "questions": [question(id="ch01-single-001", type="single", difficulty2="easy")],
        }
        with self.assertRaises(amcbank.BankError):
            amcbank.normalize(data, "ch01")

    def test_bad_enum_is_rejected(self):
        data = {
            "chapter": "第一章 测试",
            "single": [question(id="ch01-single-001", difficulty="中等")],
        }
        with self.assertRaises(amcbank.BankError):
            amcbank.normalize(data, "ch01")

    def test_term_mode_is_validated(self):
        term = {k: v for k, v in question().items() if k != "options"}
        term.update(type="term", id="ch01-term-001", mode="explain")
        data = {"schema": 2, "chapter": "第一章 测试", "questions": [term]}
        out = amcbank.normalize(data, "ch01")
        self.assertEqual(out["questions"][0]["mode"], "explain")

        for bad in (
            {**term, "mode": "lookup"},
            {**question(id="ch01-single-001", type="single"), "mode": "explain"},
        ):
            with self.subTest(mode=bad.get("mode")):
                with self.assertRaises(amcbank.BankError):
                    amcbank.normalize(
                        {"schema": 2, "chapter": "第一章 测试", "questions": [bad]}, "ch01"
                    )


if __name__ == "__main__":
    unittest.main()
