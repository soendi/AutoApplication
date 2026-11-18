"""Erzeugt ``autoapplication.ico`` und ``autoapplication.png``.

Das Symbol ist derselbe Briefumschlag mit Haken wie in der Kopfzeile.
Aufruf: ``python packaging/make_icon.py`` (benoetigt Pillow).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 512
BASE = Path(__file__).resolve().parent


def draw() -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    painter = ImageDraw.Draw(image)

    painter.rounded_rectangle((0, 0, SIZE, SIZE), radius=int(SIZE * 0.22), fill=(77, 141, 255, 255))
    painter.rounded_rectangle((0, SIZE * 0.55, SIZE, SIZE), radius=int(SIZE * 0.22), fill=(28, 58, 122, 255))
    painter.rounded_rectangle(
        (SIZE * 0.16, SIZE * 0.28, SIZE * 0.84, SIZE * 0.74),
        radius=int(SIZE * 0.05),
        fill=(246, 247, 249, 255),
    )
    painter.line(
        [
            (SIZE * 0.18, SIZE * 0.30),
            (SIZE * 0.50, SIZE * 0.53),
            (SIZE * 0.82, SIZE * 0.30),
        ],
        fill=(43, 74, 133, 255),
        width=int(SIZE * 0.035),
        joint="curve",
    )
    painter.ellipse(
        (SIZE * 0.58, SIZE * 0.52, SIZE * 0.92, SIZE * 0.86),
        fill=(62, 207, 142, 255),
    )
    painter.line(
        [
            (SIZE * 0.655, SIZE * 0.685),
            (SIZE * 0.705, SIZE * 0.745),
            (SIZE * 0.795, SIZE * 0.600),
        ],
        fill=(11, 36, 25, 255),
        width=int(SIZE * 0.055),
        joint="curve",
    )
    return image


def main() -> int:
    image = draw()
    png = BASE / "autoapplication.png"
    image.resize((256, 256), Image.LANCZOS).save(png)
    image.save(
        BASE / "autoapplication.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"Symbol geschrieben: {png.name}, autoapplication.ico")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
