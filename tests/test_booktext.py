"""`pdfquiz.booktext` 与跨页 evidence 的单测。

这些规则以前埋在 tools/build_exam.py 里，只能靠「跑一遍看题数对不对」来验证，
现在抽成模块，直接锁行为。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdfquiz.booktext import (  # noqa: E402
    canonical_path,
    clean_md,
    first_meaning,
    parse_vocab,
    part_of_unit,
    sentences,
    split_body,
    strip_page_marks,
    unit_title,
)
from pdfquiz.verify import evidence_ok  # noqa: E402

MD = """# UNIT 3 Step Growth Polymerization（缩聚）

### p78

In step growth polymerization, monomers combine to form dimers, trimers and longer chains.

### p79

No initiator is required because any two monomers can react with each other directly.

## Words and Expressions

| Term | 音标 | 词性 | 释义 |
| --- | --- | --- | --- |
| monomer | /ˈmɒnəmə/ | n. | 单体 |
| step growth | /step/ | n. | 逐步增长 |
| | | | |
"""


class TestSplitBody(unittest.TestCase):
    def test_body_stops_at_vocab(self):
        body = split_body(MD)
        self.assertIn("step growth polymerization", body.lower())
        self.assertNotIn("monomer |", body)

    def test_page_marks_are_kept(self):
        self.assertIn("### p78", split_body(MD))

    def test_caption_and_running_head_dropped(self):
        md = "## 正文\n> 图 3-1 反应示意\n\n120 **UNIT 3 Step Growth**\n\n正文一句。\n\n## Words"
        body = split_body(md)
        self.assertNotIn("反应示意", body)
        self.assertNotIn("120 **UNIT 3", body)
        self.assertIn("正文一句", body)


class TestSentences(unittest.TestCase):
    def test_no_cross_page_sentence(self):
        """翻页处不能拼句：拼出来的句子原文里并不连续。"""
        got = sentences(split_body(MD))
        joined = " ".join(got)
        self.assertNotIn("directly. No initiator", joined)
        self.assertTrue(any("dimers" in s for s in got))
        self.assertTrue(any("initiator" in s for s in got))

    def test_short_fragments_dropped(self):
        self.assertEqual(sentences("### p1\nToo short."), [])


class TestVocab(unittest.TestCase):
    def test_rows_parsed(self):
        rows = parse_vocab(MD)
        self.assertEqual([r["term"] for r in rows], ["monomer", "step growth"])
        self.assertEqual(rows[0]["pos"], "n.")

    def test_header_and_empty_rows_skipped(self):
        terms = [r["term"].lower() for r in parse_vocab(MD)]
        self.assertNotIn("term", terms)
        self.assertEqual(len(terms), 2)


class TestPathAndTitle(unittest.TestCase):
    def test_title_drops_parenthesis(self):
        self.assertEqual(unit_title(MD, "unit03"), "UNIT 3 Step Growth Polymerization")

    def test_title_falls_back(self):
        self.assertEqual(unit_title("没有一级标题", "unit22"), "UNIT 22")

    def test_part_boundaries(self):
        self.assertIn("PART A", part_of_unit(10))
        self.assertIn("PART B", part_of_unit(11))
        self.assertIn("PART B", part_of_unit(20))
        self.assertIn("PART C", part_of_unit(21))

    def test_canonical_path(self):
        self.assertEqual(
            canonical_path(3, {3: "UNIT 3 X"}),
            "PART A 高分子化学与物理 > UNIT 3 X",
        )
        self.assertEqual(canonical_path(3, {}, "回退路径"), "回退路径")


class TestCleanAndMeaning(unittest.TestCase):
    def test_clean_md_strips_marks(self):
        self.assertEqual(clean_md("## 标题\n\n**粗**体"), "标题\n\n粗体")

    def test_first_meaning(self):
        self.assertEqual(first_meaning("性能,行为"), "性能")
        self.assertEqual(first_meaning("溶解[度];溶液"), "溶解")
        self.assertEqual(first_meaning("粘度"), "粘度")


class TestPageMarkEvidence(unittest.TestCase):
    SRC = """In amorphous polymers this is simply a rearrangement of the coiled chains.
In crystalline polymers the phenomenon is more complex; crystallites may be reoriented or even completely rear-

### p151

ranged; oriented recrystallization may be induced by the stress applied.
"""

    def test_page_mark_stripped(self):
        self.assertNotIn("### p151", strip_page_marks(self.SRC))

    def test_sentence_across_page_accepted(self):
        """这句话在书上横跨 150/151 两页，中间有页标记和断词，仍然算原文。"""
        ev = ("In crystalline polymers the phenomenon is more complex; crystallites may be "
              "reoriented or even completely rearranged; oriented recrystallization may be "
              "induced by the stress applied.")
        ok, why = evidence_ok(ev, self.SRC)
        self.assertTrue(ok, why)

    def test_fabricated_still_rejected(self):
        ev = ("In crystalline polymers the phenomenon is simpler; crystallites never move "
              "and no recrystallization can be induced by stress.")
        ok, why = evidence_ok(ev, self.SRC)
        self.assertFalse(ok)
        self.assertIn("找不到", why)


if __name__ == "__main__":
    unittest.main()
