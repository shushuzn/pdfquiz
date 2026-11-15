"""生成一个真实可解析的示例 PDF（纯标准库，不依赖 reportlab）。

用途：在没有真实讲义时，验证 PDF 解析路径确实能跑通。
注意：Helvetica 只能编码 Latin-1，所以示例正文是英文；
中文 PDF 请用 docling / pymupdf4llm（它们带 CJK 字体处理）。
"""

from __future__ import annotations

from pathlib import Path

PAGES: list[list[tuple[str, int]]] = [
    [
        ("Chapter 3  Overfitting and Regularization", 16),
        ("", 10),
        ("3.1 Definition of overfitting", 12),
        ("Overfitting refers to the phenomenon where the training error keeps", 10),
        ("decreasing while the validation error starts to rise after a certain", 10),
        ("epoch. The model is fitting noise in the training samples as if it", 10),
        ("were signal. A reliable symptom is not the absolute value of the", 10),
        ("training loss, but the widening gap between training and validation", 10),
        ("loss.", 10),
        ("", 10),
        ("3.2 Bias and variance trade-off", 12),
        ("Generalization error decomposes into bias, variance and irreducible", 10),
        ("noise. Bias measures the systematic deviation between the hypothesis", 10),
        ("space and the true function. Variance measures sensitivity to", 10),
        ("perturbations of the training set. High bias corresponds to", 10),
        ("underfitting, high variance corresponds to overfitting.", 10),
    ],
    [
        ("3.3 L2 regularization", 12),
        ("L2 regularization adds the sum of squared weights to the loss,", 10),
        ("scaled by a coefficient lambda. Its effect is to shrink weights", 10),
        ("toward zero without setting them exactly to zero, which is why it is", 10),
        ("also called weight decay. When lambda approaches zero the penalty", 10),
        ("vanishes and the model reduces to ordinary least squares.", 10),
        ("", 10),
        ("3.4 L1 regularization and sparsity", 12),
        ("L1 regularization adds the sum of absolute weights. Unlike L2 it", 10),
        ("tends to drive a subset of weights exactly to zero, producing a", 10),
        ("sparse solution that can serve as feature selection. Geometrically", 10),
        ("the constraint region of L1 is a diamond whose vertices lie on the", 10),
        ("axes, so the optimum often lands on a vertex where some weights", 10),
        ("are exactly zero.", 10),
    ],
    [
        ("3.5 Dropout", 12),
        ("Dropout randomly zeroes the output of a fraction p of neurons at", 10),
        ("each training iteration. At inference no neuron is dropped, but", 10),
        ("weights must be rescaled by the keep probability to preserve the", 10),
        ("expected output. Dropout can be read as an implicit ensemble of", 10),
        ("many weight-sharing subnetworks, so it reduces variance.", 10),
        ("", 10),
        ("3.6 Early stopping", 12),
        ("Early stopping halts training when validation loss stops improving", 10),
        ("for a number of consecutive epochs and rolls back to the best", 10),
        ("checkpoint. It requires no change to the loss function and is the", 10),
        ("cheapest regularizer, at the cost of holding out a validation set.", 10),
    ],
]


def build(pages: list[list[tuple[str, int]]], path: Path) -> None:
    objects: list[bytes] = []

    def add(body: str) -> int:
        objects.append(body.encode("latin-1"))
        return len(objects)

    catalog_id = add("<< /Type /Catalog /Pages 2 0 R >>")
    pages_id = 2
    objects.append(b"")  # 占位，稍后回填
    font_id = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                  "/Encoding /WinAnsiEncoding >>")

    page_ids: list[int] = []
    for lines in pages:
        stream = ["BT"]
        y = 780
        for text, size in lines:
            if text:
                esc = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
                stream.append(f"/F1 {size} Tf 1 0 0 1 72 {y} Tm ({esc}) Tj")
            y -= (size + 8)
        stream.append("ET")
        raw = "\n".join(stream).encode("latin-1")
        content_id = add(f"<< /Length {len(raw)} >>\nstream\n" + raw.decode("latin-1")
                         + "\nendstream")
        page_ids.append(add(
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        ))

    kids = " ".join(f"{i} 0 R" for i in page_ids)
    objects[pages_id - 1] = (
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("latin-1")
    )

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode("latin-1") + body + b"\nendobj\n"

    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode("latin-1")
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n").encode("latin-1")

    path.write_bytes(bytes(out))


if __name__ == "__main__":
    target = Path(__file__).resolve().parent.parent / "samples" / "overfitting_lecture.pdf"
    build(PAGES, target)
    print(f"已生成 {target} ({target.stat().st_size} bytes, {len(PAGES)} 页)")
