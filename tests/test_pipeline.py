"""核心逻辑测试：切块、溯源校验、去重。

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdfquiz.chunk import chunk_markdown  # noqa: E402
from pdfquiz.generate import offline_questions  # noqa: E402
from pdfquiz.render import render  # noqa: E402
from pdfquiz.verify import Report, check_structure, evidence_ok, verify  # noqa: E402

SRC = (
    "过拟合是指模型在训练数据上的误差持续下降，而在验证数据上的误差在某一轮之后"
    "转而上升的现象。其本质是模型把训练样本中的噪声也当成了规律来学习。"
)


class TestChunk(unittest.TestCase):
    def test_split_by_heading(self):
        md = "# 章\n\n导语一句。\n\n## 第一节\n\n" + SRC + "\n\n## 第二节\n\n" + SRC
        chunks = chunk_markdown(md, min_chars=1)
        self.assertEqual(len(chunks), 3)
        self.assertIn("第一节", chunks[1].path)
        self.assertEqual(chunks[1].idx, 2)

    def test_long_section_split(self):
        md = "## 长节\n\n" + ("这是一句用来填充长度的话。" * 120)
        chunks = chunk_markdown(md, max_chars=500, min_chars=10)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(c.chars <= 700 for c in chunks))

    def test_short_fragment_merges_forward(self):
        md = "## A\n\n标题下的引导句。\n\n## B\n\n" + SRC
        chunks = chunk_markdown(md, min_chars=60)
        self.assertEqual(len(chunks), 1)
        self.assertIn("B", chunks[0].path)
        self.assertIn("引导句", chunks[0].text)


class TestEvidence(unittest.TestCase):
    def test_verbatim_passes(self):
        ok, _ = evidence_ok(SRC.split("。")[0] + "。", SRC)
        self.assertTrue(ok)

    def test_whitespace_and_punct_tolerated(self):
        ok, _ = evidence_ok("过拟合是指模型在训练数据上的误差持续下降", SRC)
        self.assertTrue(ok)

    def test_fabricated_rejected(self):
        ok, why = evidence_ok("这段话在原始文档中并不存在纯属模型编造。", SRC)
        self.assertFalse(ok)
        self.assertIn("找不到", why)

    def test_negation_flip_rejected(self):
        ok, _ = evidence_ok("过拟合不是指模型在训练数据上的误差持续下降", SRC)
        self.assertFalse(ok)

    def test_too_short_rejected(self):
        ok, why = evidence_ok("过拟合", SRC)
        self.assertFalse(ok)
        self.assertIn("过短", why)


class TestStructure(unittest.TestCase):
    def _q(self, **kw):
        base = {
            "type": "single",
            "question": "过拟合的可靠判别信号是什么？",
            "options": ["A. 训练损失", "B. 差距扩大", "C. 验证损失", "D. 参数量"],
            "answer": "B",
        }
        base.update(kw)
        return base

    def test_valid(self):
        self.assertTrue(check_structure(self._q())[0])

    def test_duplicate_options(self):
        ok, why = check_structure(self._q(options=["A. 甲", "B. 甲", "C. 丙"]))
        self.assertFalse(ok)
        self.assertIn("重复选项", why)

    def test_answer_out_of_range(self):
        ok, why = check_structure(self._q(answer="E"))
        self.assertFalse(ok)
        self.assertIn("不在选项范围", why)

    def test_multiple_with_single_answer(self):
        ok, why = check_structure(self._q(type="multiple", answer=["B"]))
        self.assertFalse(ok)
        self.assertIn("只有一个", why)

    def test_multiple_answer_as_string(self):
        for ans in ("AB", "A、B", "A,B"):
            ok, why = check_structure(self._q(type="multiple", answer=ans))
            self.assertTrue(ok, f"{ans!r}: {why}")

    def test_truefalse_bad_answer(self):
        ok, _ = check_structure({"type": "truefalse", "question": "这是对的吗？", "answer": "yes"})
        self.assertFalse(ok)


class TestRender(unittest.TestCase):
    def test_option_labels_are_normalized(self):
        q = {
            "type": "single",
            "question": "过拟合的可靠判别信号是什么？",
            "options": ["A、训练损失", "B、差距扩大", "C、验证损失", "D、参数量"],
            "answer": "B",
            "evidence": SRC.split("。")[0] + "。",
        }
        md = render(
            title="测试", engine="passthrough", source="x.md",
            chunks=1, reports=[Report(accepted=[q])], mock=False,
        )
        self.assertIn("- A. 训练损失", md)
        self.assertNotIn("A. A、训练损失", md)


class TestVerify(unittest.TestCase):
    def test_dedupe_and_reject_mix(self):
        good = {
            "type": "single",
            "question": "过拟合的可靠判别信号是什么？",
            "options": ["A. 训练损失", "B. 差距扩大", "C. 验证损失", "D. 参数量"],
            "answer": "B",
            "evidence": SRC.split("。")[0] + "。",
        }
        dup = dict(good, question="过拟合的可靠判别信号是什么??")
        fake = dict(good, question="另一个完全不同的问题表述方式是什么？",
                    evidence="这句话在原文中并不存在纯属编造内容。")

        rep = verify([good, dup, fake], SRC)
        self.assertEqual(len(rep.accepted), 1)
        self.assertEqual(len(rep.rejected), 2)
        reasons = " ".join(r["reason"] for r in rep.rejected)
        self.assertIn("重复", reasons)
        self.assertIn("找不到", reasons)

    def test_offline_items_always_grounded(self):
        """离线兜底题的 evidence 取自原句，必须 100% 通过。"""
        md = "## 定义\n\n" + SRC
        chunk = chunk_markdown(md, min_chars=10)[0]
        items = offline_questions(chunk, 5)
        self.assertTrue(items)
        rep = verify(items, chunk.text)
        self.assertEqual(len(rep.rejected), 0)
        self.assertEqual(len(rep.accepted), len(items))


if __name__ == "__main__":
    unittest.main(verbosity=2)
