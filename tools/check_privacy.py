"""发布前隐私检查。

只做规则匹配：教师联系方式、课程内部字段、带追踪参数的链接。
命中即失败，避免把不该公开的信息再次提交到公开仓库。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "__pycache__", "out_amc", "out_exam", ".venv", "venv", "env"}
TEXT_SUFFIXES = {
    ".md", ".json", ".py", ".html", ".txt", ".yml", ".yaml",
    ".tsv", ".mjs", ".js", ".css", ".toml",
}

PATTERNS = [
    (re.compile(r"主讲教师\s*[:：]"), "教师姓名栏"),
    (re.compile(r"(?:授课教师|任课教师|主讲)\s*[:：]\s*[\u4e00-\u9fa5]{2,4}"), "教师姓名"),
    (re.compile(r"课程负责人\s*[:：]"), "课程负责人栏"),
    (re.compile(r"办公室\s*[:：]"), "办公室门牌"),
    (re.compile(r"QQ\s*[:：]?\s*\d{5,12}"), "QQ 号"),
    (re.compile(r"(?:微信|WeChat)\s*(?:号)?\s*[:：]\s*[A-Za-z0-9_-]{5,}", re.I), "微信号"),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "手机号"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "邮箱"),
    # 括号里的「姓名，单位」：课件封面与致谢里最常见的泄露形式
    (re.compile(r"[（(][\u4e00-\u9fa5]{2,4}[，,][^）)]{0,30}(?:学院|大学|研究所|学系|系)[^）)]*[）)]"),
     "姓名与单位"),
    (re.compile(r"seid\s*=|spm_id_from\s*=|vd_source\s*=|utm_source\s*="), "追踪参数"),
]


def iter_files(root: Path = ROOT):
    root = Path(root)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        yield path


def scan(root: Path = ROOT) -> list[tuple[Path, int, str]]:
    root = Path(root)
    hits: list[tuple[Path, int, str]] = []
    for path in iter_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for pattern, label in PATTERNS:
                if pattern.search(line):
                    hits.append((path.relative_to(root), lineno, label))
                    break
    return hits


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    root = Path(args[0]) if args else ROOT
    hits = scan(root)
    if hits:
        print("隐私检查未通过：")
        for path, lineno, label in hits:
            print(f"  {path}:{lineno}  {label}")
        return 1
    print("隐私检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())