"""站点静态检查：本地链接必须能打开，卷子必须能返回所属课程。

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pdfquiz.courses import course_page, deck_page, load_courses  # noqa: E402

DOCS = ROOT / "docs"
LINK = re.compile(r'href="([^"]+)"')
EXTERNAL = ("http://", "https://", "#", "mailto:", "javascript:", "data:")


class TestSiteLinks(unittest.TestCase):
    def test_all_local_links_resolve(self):
        pages = sorted(DOCS.glob("*.html"))
        self.assertTrue(pages, "docs/ 里没有页面")
        for page in pages:
            for href in LINK.findall(page.read_text(encoding="utf-8")):
                if href.startswith(EXTERNAL):
                    continue
                target = urlsplit(href).path
                if not target:
                    continue
                with self.subTest(page=page.name, href=href):
                    resolved = (page.parent / unquote(target)).resolve()
                    self.assertTrue(resolved.is_file(), f"{page.name} -> {href} 不存在")

    def test_every_deck_returns_to_its_course(self):
        courses = load_courses(ROOT)
        checked = 0
        for course in courses:
            href = course_page(course)
            for deck_id in course["decks"]:
                page = DOCS / deck_page(course, deck_id)
                if not page.exists():
                    continue
                text = page.read_text(encoding="utf-8")
                with self.subTest(course=course["id"], deck=deck_id):
                    self.assertRegex(
                        text,
                        rf'<a class="[^"]*\bhub-link\b[^"]*" href="{re.escape(href)}"',
                    )
                    self.assertIn("返回课程", text)
                checked += 1
        self.assertGreater(checked, 0, "没有检查到任何卷子页")


if __name__ == "__main__":
    unittest.main()