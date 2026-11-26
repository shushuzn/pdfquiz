"""裁一张教材插图并压成 WebP。

    python tools/crop_figure.py --page /tmp/p-022.png --box 560,60,815,380 \
        --out papers_hgyl/examples/figures/ch01-fig1-08.webp --page-ref P13

box 是页面渲染图上的像素框 (x0,y0,x1,y1)，先粗裁再自动去掉四周空白。
输出一行 JSON，可直接填进 figures/chNN.json。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def trim(image: Image.Image, threshold: int = 200, margin: int = 12) -> Image.Image:
    """按深色像素去掉四周白边，再留一点白边。"""
    gray = image.convert("L")
    mask = gray.point(lambda p: 255 if p < threshold else 0)
    box = mask.getbbox()
    if box:
        image = image.crop(box)
    canvas = Image.new("RGB", (image.width + margin * 2, image.height + margin * 2), "white")
    canvas.paste(image, (margin, margin))
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", required=True, help="整页渲染图")
    parser.add_argument("--box", required=True, help="x0,y0,x1,y1")
    parser.add_argument("--out", required=True, help="输出 .webp")
    parser.add_argument("--page-ref", default="", help="印刷页码，如 P13")
    parser.add_argument("--max-width", type=int, default=720)
    parser.add_argument("--quality", type=int, default=82)
    args = parser.parse_args()

    box = tuple(int(v) for v in args.box.split(","))
    if len(box) != 4:
        raise SystemExit("--box 要四个整数")
    image = Image.open(args.page).convert("RGB")
    image = image.crop(box)
    image = trim(image)
    if image.width > args.max_width:
        height = round(image.height * args.max_width / image.width)
        image = image.resize((args.max_width, height), Image.LANCZOS)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, "WEBP", quality=args.quality, method=6)
    print(json.dumps({
        "file": out.name,
        "page": args.page_ref,
        "width": image.width,
        "height": image.height,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())