"""让 `python -m pdfquiz` 等价于 `pdfquiz` 命令。"""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
