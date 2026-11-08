"""Draw the original MTS to DNxHR icon.

Each size is rendered on its own 4× canvas so the 16 px and 24 px glyphs can
drop the sprocket holes and keep a 2 px stroke. Output is deterministic.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw

SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]
_TOP = (0x2B, 0x3A, 0x55)
_BOTTOM = (0x16, 0x20, 0x2F)
_WHITE = (255, 255, 255, 255)
_AMBER = (0xF5, 0xA5, 0x24, 255)
_RESAMPLE = getattr(Image, "Resampling", Image).LANCZOS


def _blend(top: tuple[int, int, int], bottom: tuple[int, int, int], t: float) -> tuple[int, int, int, int]:
    return (
        int(top[0] + (bottom[0] - top[0]) * t),
        int(top[1] + (bottom[1] - top[1]) * t),
        int(top[2] + (bottom[2] - top[2]) * t),
        255,
    )


def _chevron(size: int, thickness: float) -> list[tuple[float, float]]:
    """Right-pointing chevron whose back overlaps the film frame."""
    back = 0.46 * size
    tip = 0.84 * size
    mid = 0.50 * size
    wing = 0.20 * size
    inset = thickness
    return [
        (back, mid - wing),
        (tip, mid),
        (back, mid + wing),
        (back + inset * 0.15, mid + wing - inset),
        (tip - inset * 1.35, mid),
        (back + inset * 0.15, mid - wing + inset),
    ]


def render(size: int) -> Image.Image:
    scale = 4
    canvas = size * scale
    simple = size in (16, 24)
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    gradient = ImageDraw.Draw(image)
    for y in range(canvas):
        gradient.line(
            [(0, y), (canvas - 1, y)],
            fill=_blend(_TOP, _BOTTOM, y / float(canvas - 1)),
        )
    mask = Image.new("L", (canvas, canvas), 0)
    radius = int(round(canvas * 0.18))
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, canvas - 1, canvas - 1),
        radius=radius,
        fill=255,
    )
    image.putalpha(mask)

    draw = ImageDraw.Draw(image)
    min_stroke = 2 * scale if simple else scale
    stroke = max(min_stroke, int(round(canvas * (0.075 if simple else 0.04))))
    left = int(round(canvas * 0.14))
    right = int(round(canvas * 0.55))
    top = int(round(canvas * 0.24))
    bottom = int(round(canvas * 0.76))
    draw.rectangle((left, top, right, bottom), outline=_WHITE, width=stroke)
    if not simple:
        hole = max(stroke, int(round(canvas * 0.035)))
        span = right - left
        for slot in range(1, 4):
            center = left + span * slot / 4.0
            for edge in (top, bottom):
                draw.ellipse(
                    (center - hole, edge - hole, center + hole, edge + hole),
                    fill=_WHITE,
                )
    thickness = max(float(stroke) * 1.15, canvas * 0.09)
    draw.polygon(_chevron(canvas, thickness), fill=_AMBER)
    return image.resize((size, size), _RESAMPLE)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Draw assets/app.ico")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Icon path (default: <repo>/assets/app.ico)",
    )
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    out = args.out if args.out is not None else root / "assets" / "app.ico"
    out.parent.mkdir(parents=True, exist_ok=True)
    images = [render(size) for size in SIZES]
    images[-1].save(
        out,
        format="ICO",
        sizes=[(size, size) for size in SIZES],
        append_images=images[:-1],
    )
    png_path = out.parent / "app-256.png"
    images[-1].save(png_path, format="PNG")
    with Image.open(out) as icon:
        found = set(icon.info.get("sizes") or [])
    expected = {(size, size) for size in SIZES}
    missing = expected - found
    if missing:
        print("error: icon is missing sizes {0}".format(sorted(missing)), file=sys.stderr)
        return 1
    print(out)
    print(" ".join(str(size) for size in SIZES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
