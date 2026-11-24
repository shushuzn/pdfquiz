"""发布前隐私检查的规则测试。

    python -m unittest discover -s tests -v

PII 样本在运行时拼接，避免测试文件自身命中规则。
"""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import check_privacy  # noqa: E402


def make_root() -> Path:
    return Path(tempfile.mkdtemp())


def write(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class TestPrivacyRules(unittest.TestCase):
    def test_clean_tree_passes(self):
        root = make_root()
        write(root, "notes.md", "# 课件整理\n\n只保留课程内容。\n")
        self.assertEqual(check_privacy.scan(root), [])

    def test_each_pattern_is_detected(self):
        cases = {
            "教师姓名栏": "主讲" + "教师：" + "某老师",
            "教师姓名": "主讲" + "：某老师",
            "课程负责人栏": "课程" + "负责人：" + "某老师",
            "办公室门牌": "办公" + "室：A312",
            "QQ 号": "Q" + "Q:12345678",
            "微信号": "微信" + "号：abcde12345",
            "手机号": "联系电话 138" + "0013" + "8000",
            "邮箱": "mail: user" + "@" + "example.com",
            "姓名与单位": "（" + "某某" + "，" + "某大学" + "）",
            "追踪参数": "https://example.com/v?utm" + "_source=feed",
        }
        for label, text in cases.items():
            with self.subTest(label=label):
                root = make_root()
                write(root, "hit.md", text + "\n")
                hits = check_privacy.scan(root)
                self.assertEqual([h[2] for h in hits], [label])

    def test_qq_without_colon(self):
        root = make_root()
        write(root, "hit.md", "联系 Q" + "Q532714599\n")
        self.assertEqual([h[2] for h in check_privacy.scan(root)], ["QQ 号"])

    def test_cover_author_affiliation_is_detected(self):
        root = make_root()
        write(root, "corpus_amc/ch01.md",
              "《某课程》课件（" + "某某" + "，" + "某学院" + "）与课程教学大纲\n")
        self.assertEqual([h[2] for h in check_privacy.scan(root)], ["姓名与单位"])

    def test_location_is_reported(self):
        root = make_root()
        write(root, "corpus/ch01.md", "第一行\n第二行 " + "Q" + "Q:12345678\n")
        hits = check_privacy.scan(root)
        self.assertEqual(len(hits), 1)
        path, lineno, label = hits[0]
        self.assertEqual(path, Path("corpus/ch01.md"))
        self.assertEqual(lineno, 2)
        self.assertEqual(label, "QQ 号")

    def test_skip_dirs_and_binary_suffixes(self):
        root = make_root()
        write(root, "out_amc/draft.md", "Q" + "Q:12345678\n")
        write(root, "docs/scan.bin", "Q" + "Q:12345678\n")
        self.assertEqual(check_privacy.scan(root), [])

    def test_main_exit_codes(self):
        root = make_root()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(check_privacy.main([str(root)]), 0)
        self.assertIn("隐私检查通过", out.getvalue())

        write(root, "hit.md", "Q" + "Q:12345678\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(check_privacy.main([str(root)]), 1)
        self.assertIn("hit.md:1", out.getvalue())

    def test_repo_is_clean(self):
        self.assertEqual(check_privacy.scan(ROOT), [])


if __name__ == "__main__":
    unittest.main()