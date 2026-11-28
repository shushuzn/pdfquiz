"""线性公式文本 → LaTeX 转换器的回归测试。

除了逐条规则，最后还有一组「全量体检」：把 93 道例题里所有会送进 KaTeX 的
串都跑一遍结构校验。转换器的底线是宁可退回线性文本，也不要生成一条渲染失败的公式。
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import examples  # noqa: E402
import texmath  # noqa: E402


def tex(line: str) -> str | None:
    return texmath.to_tex(line)


class TestSymbols(unittest.TestCase):
    def test_operators_and_relations(self):
        self.assertEqual(tex("a × b − c · d ≈ e"), r"a \times  b - c \cdot  d \approx  e")

    def test_greek_gets_a_trailing_space(self):
        # \mu 后面紧跟字母会被 TeX 读成 \muu，必须留空格
        self.assertEqual(tex("18μu_{t}"), r"18\mu u_{t}")
        self.assertEqual(tex("ρ_{s} − ρ"), r"\rho _{s} - \rho ")
        self.assertEqual(tex("Σh_{f}"), r"\sum h_{f}")

    def test_degree(self):
        self.assertEqual(tex("95.8°C"), r"95.8\,{}^{\circ}\mathrm{C}")
        self.assertEqual(tex("p^{°}_{A} = 179.2"), r"p^{\circ}_{A} = 179.2")

    def test_primes(self):
        self.assertEqual(tex("H′ = 18"), "H' = 18")
        self.assertEqual(tex("Δ″_{2}"), r"\Delta ''_{2}")

    def test_percent_is_escaped(self):
        self.assertEqual(tex("η = 98%"), r"\eta  = 98\%")

    def test_functions(self):
        self.assertEqual(tex("ln(25/20)"), r"\ln (25/20)")
        self.assertEqual(tex("lgα"), r"\lg \alpha ")


class TestSqrt(unittest.TestCase):
    def test_paren_and_bracket_and_word(self):
        for src in ("√((a − b)/c)", "√[18/(3000 × 9.81)]", "sqrt(2 × 0.53)"):
            out = tex(src)
            self.assertIsNotNone(out, src)
            self.assertIn(r"\sqrt{", out)
            self.assertNotIn("√", out)
        self.assertEqual(tex("√(a − b)/c"), r"\sqrt{a - b}/c")
        self.assertEqual(tex("√[18/(3000 × 9.81)]"), r"\sqrt{18/(3000 \times  9.81)}")

    def test_nested(self):
        self.assertEqual(tex("√(a + √(b))"), r"\sqrt{a + \sqrt{b}}")


class TestUnits(unittest.TestCase):
    def test_unit_after_number_is_upright(self):
        self.assertEqual(tex("u = 1.75 m/s"), r"u = 1.75\,\mathrm{m}/\mathrm{s}")
        self.assertEqual(tex("q = 3.08×10^{-3} m^{3}/h"),
                         r"q = 3.08\times 10^{-3}\,\mathrm{m}^{3}/\mathrm{h}")

    def test_variables_are_not_units(self):
        # 这些位置上的字母是变量，包成直立体就变成单位了
        for src in ("Q=q_{m1}r", "F = V + W", "S = mV/L", "D = Wr'/(0.95r)",
                    "z_{2} - z_{1} = h_{0}", "t = q^{2}/K"):
            self.assertNotIn(r"\mathrm", tex(src), src)


class TestChemicals(unittest.TestCase):
    def test_common_formulas_are_upright(self):
        self.assertEqual(tex("NH_{3}"), r"\mathrm{NH}_{3}")
        self.assertEqual(tex("CO_{2}"), r"\mathrm{CO}_{2}")

    def test_subscripted_variables_stay_italic(self):
        self.assertEqual(tex("X_{1}"), "X_{1}")
        self.assertEqual(tex("Y_{2}"), "Y_{2}")


class TestChinese(unittest.TestCase):
    def test_cjk_subscript_wrapped_in_text(self):
        self.assertEqual(tex("H_{g允} = 4.74"), r"H_{\text{g允}} = 4.74")

    def test_cjk_outside_formula_aborts(self):
        # 整行里还夹着中文说明（90° 弯头），放弃转换，退回线性文本
        self.assertIsNone(tex("90° 弯头"))

    def test_prose_is_not_math(self):
        self.assertFalse(texmath.is_formula_line("试求该条件下气、液两相的组成。"))
        self.assertTrue(texmath.is_formula_line("p_{A} = 179.2 kPa"))
        self.assertTrue(texmath.is_formula_line("z_{2} - z_{1} = h_{0}"))

    def test_line_with_cjk_is_not_a_pure_formula(self):
        self.assertFalse(texmath.is_formula_line("解得 D = 7.35 kmol/h"))


class TestSafety(unittest.TestCase):
    def test_unknown_character_aborts(self):
        self.assertIsNone(tex("a ⊕ b = c"))

    def test_orphan_script_aborts(self):
        self.assertIsNone(tex("^{2} = 4"))
        self.assertIsNone(tex("_0 = 1"))

    def test_unbalanced_group_aborts(self):
        self.assertIsNone(tex("q_{V}/((π/4)d^{2}"))

    def test_empty_line(self):
        self.assertIsNone(tex("   "))


class TestSplitChain(unittest.TestCase):
    def test_splits_from_second_equals(self):
        self.assertEqual(
            texmath.split_chain("Y_{2} = Y_{1}(1 − η) = 0.0134 × 0.005 = 0.0000669"),
            ["Y_{2} = Y_{1}(1 − η)", "= 0.0134 × 0.005", "= 0.0000669"],
        )

    def test_keeps_leading_equals_with_first_operator(self):
        segs = texmath.split_chain("= 2 × 3.14 × 250 = 0.0132")
        self.assertEqual(segs, ["= 2 × 3.14 × 250", "= 0.0132"])

    def test_does_not_split_inside_brackets(self):
        self.assertEqual(texmath.split_chain("f = (a = b) + c"), ["f = (a = b) + c"])


class TestLineBreaks(unittest.TestCase):
    """手机上放不下就折行：等号 → 加减号 → 连乘号，逐级放宽。"""

    def test_short_line_not_broken(self):
        self.assertEqual(texmath._breaks("z_{2} - z_{1} = h_{0}"), ["z_{2} - z_{1} = h_{0}"])

    def test_splits_terms_at_top_level(self):
        src = "= 1/1200 + 2.5×10^{-4} + 0.0025 × 0.025/(45 × 0.0225) + 4.5×10^{-4} × 0.025/0.020"
        self.assertGreater(len(src), texmath.TERM_MAX)
        segs = texmath.split_terms(src)
        self.assertEqual(segs[:2], ["= 1/1200", "+ 2.5×10^{-4}"])
        self.assertTrue(all(s.startswith(("+", "-", "−", "=")) for s in segs), segs)

    def test_unary_and_bracketed_operators_are_not_break_points(self):
        src = "= " + "(0.5 - 1) + " * 10 + "9"
        segs = texmath.split_terms(src)
        self.assertGreater(len(segs), 1)
        # 括号里那一组必须整段待在一起，不能从 0.5 - 1 中间劈开
        self.assertEqual(sum(s.count("(0.5 - 1)") for s in segs), src.count("(0.5 - 1)"))
        for seg in segs:
            self.assertFalse(seg.endswith("("), seg)
            self.assertFalse(seg.startswith("- 1)"), seg)
        # = 后面紧跟的负号是一元的，不该成为折行点
        for seg in texmath.split_terms("y = -5 + " + "1.0 × 2.0 + " * 9 + "9"):
            self.assertFalse(seg.startswith("-5"), seg)

    def test_splits_long_product_chain(self):
        chain = ("q_{V} = 0.648×0.785×0.075^{2}×sqrt(2×0.08×9.81×(13600 − 880)/880)")
        segs = texmath._breaks(chain)
        self.assertGreater(len(segs), 1)
        self.assertTrue(all(len(s) <= texmath.FACTOR_MAX or "×" not in s[1:] for s in segs), segs)

    def test_breaks_keep_braces_balanced(self):
        for s in ("K_{计} = 1/[1/α_{1} + R_{s1} + R_{s2}(d_{1}/d_{2}) + d_{1}/(α_{2}d_{2})]",
                  "= 2156 × 1.027 × (45 - 20) + 28.03 × (2492 + 1.86 × 45 - 4.187 × 20) + 3"):
            for seg in texmath._breaks(s):
                for a, b in (("{", "}"), ("(", ")"), ("[", "]")):
                    self.assertEqual(seg.count(a), seg.count(b), f"{a}{b} 被拆开了：{seg}")


class TestConvertLine(unittest.TestCase):
    def test_pure_formula_becomes_block(self):
        kinds = [k for k, _, _ in texmath.convert_line("p_{1} = p_{2}")]
        self.assertEqual(kinds, ["math-block"])

    def test_long_inline_formula_gets_its_own_line(self):
        line = "式中 N_{OG2} = " + "x_{1} + " * 12 + "= 2.364，故"
        kinds = [k for k, _, _ in texmath.convert_line(line)]
        self.assertIn("math-block", kinds)
        self.assertIn("break", kinds)

    def test_short_inline_formula_stays_inline(self):
        kinds = [k for k, _, _ in texmath.convert_line("解得 D = 7.35kmol/h，W = 7.65kmol/h")]
        self.assertEqual(kinds.count("math"), 2)
        self.assertNotIn("break", kinds)

    def test_plain_prose_untouched(self):
        line = "试求该条件下气、液两相的组成。"
        self.assertEqual([k for k, _, _ in texmath.convert_line(line)], ["text"])


class TestWholeCorpus(unittest.TestCase):
    """全量体检：例题数据里每一条要送进 KaTeX 的串都得过结构校验。"""

    ORPHAN = re.compile(r"\\[,;:!](?=[ \t]*[\^_])")
    # 这些字符没有任何映射规则，出现在产出里就说明漏了规则
    LEFTOVER = re.compile("[⊕⊗∮∈∉⊆⊇∅∧∨∴∵≡≅⊥∥]|\U0001d400-\U0001d7ff")

    def lines(self):
        for stem in examples.hgyl.ORDER:
            if not examples.EXPECTED[stem]:
                continue
            for item in examples.load(stem)["examples"]:
                for key in ("problem", "solution", "answer", "note"):
                    for line in str(item.get(key) or "").split("\n"):
                        yield line

    def test_converted_pieces_are_structurally_sound(self):
        pieces = 0
        for line in self.lines():
            for kind, payload, _ in texmath.convert_line(line):
                if kind not in ("math", "math-block"):
                    continue
                pieces += 1
                stripped = texmath.TEXT_GROUP.sub("", payload)
                with self.subTest(tex=payload[:70]):
                    self.assertTrue(re.fullmatch(r"[\x00-\x7f]*", stripped), "留下未映射字符")
                    self.assertIsNone(self.ORPHAN.search(payload), "空白命令后紧跟上下标")
                    self.assertIsNone(self.LEFTOVER.search(payload), "残留未映射符号")
                    self.assertNotIn("√", payload, "根号没有改写")
                    for a, b in (("{", "}"), ("(", ")"), ("[", "]")):
                        self.assertEqual(payload.count(a), payload.count(b), f"{a}{b} 不配对")
        self.assertGreater(pieces, 2000, "公式片段数量骤减，转换规则可能被改坏")

    def test_every_math_piece_round_trips_to_readable_text(self):
        # 线性回退文本必须原样保留，禁用脚本时靠它读题
        for line in self.lines():
            for kind, _, fallback in texmath.convert_line(line):
                if kind in ("math", "math-block"):
                    with self.subTest(line=line[:60]):
                        self.assertIn(fallback, line)


if __name__ == "__main__":
    unittest.main()
