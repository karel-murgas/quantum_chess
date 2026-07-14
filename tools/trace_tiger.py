"""Trace `assets/tiger_set.png` into the `tiger` SVG piece set.

Build-time only -- the game never imports potrace. Regenerate the art with:

    pip install potracer pillow numpy
    python tools/trace_tiger.py

The sheet holds two copies of the same six figures (an orange row and a white
row, each followed by a row of pawns). Only the shapes matter: the game tints
the tiger set to each team's own colour at runtime (see `ui/pieces.py`), so one
silhouette per piece is written to both `w<code>.svg` and `b<code>.svg`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image
from potrace import Bitmap

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "tiger_set.png"
OUT = ROOT / "quantumchess" / "ui" / "assets" / "pieces" / "tiger"

# Left-to-right order of the figures on the sheet.
ORDER = ["K", "Q", "B", "N", "R", "P"]

# The sheet's own relative sizes are kept (all six share one canvas), except the
# paw: drawn at 0.39 of the king's height it reads as a speck in a board square,
# so it's scaled to roughly the 0.62 a normal set's pawn gets.
PIECE_SCALE = {"P": 1.6}

SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {c} {c}" '
    'width="{c}" height="{c}">\n'
    '  <path fill="{fill}" fill-rule="evenodd" d="{d}"/>\n'
    "</svg>\n"
)


def load_mask() -> np.ndarray:
    """Ink (orange or white figures) on the sheet's black background."""
    img = Image.open(SRC).convert("L")
    return np.asarray(img, dtype=np.uint8) > 110


def _runs(flags: np.ndarray, min_gap: int) -> list[tuple[int, int]]:
    """Index ranges of True runs, merging any blank gap shorter than min_gap."""
    runs, start, gap = [], None, 0
    for i, on in enumerate(flags):
        if on:
            if start is None:
                start = i - gap if gap and runs and gap < min_gap else i
            gap = 0
        elif start is not None:
            gap += 1
            if gap >= min_gap:
                runs.append((start, i - gap + 1))
                start, gap = None, 0
    if start is not None:
        runs.append((start, len(flags)))
    return runs


def figures(mask: np.ndarray, band: tuple[int, int]) -> list[tuple[int, int, int, int]]:
    """Bounding boxes of the figures in one row band, left to right."""
    top, bot = band
    strip = mask[top:bot]
    boxes = []
    for x0, x1 in _runs(strip.any(axis=0), min_gap=18):
        ys = np.where(strip[:, x0:x1].any(axis=1))[0]
        boxes.append((x0, top + int(ys[0]), x1, top + int(ys[-1]) + 1))
    return boxes


def curves_to_path(traced, scale: float, dx: float, dy: float) -> str:
    """potrace curves -> one SVG path 'd', placed on the shared canvas."""
    def pt(p):
        return f"{p.x * scale + dx:.2f} {p.y * scale + dy:.2f}"

    parts = []
    for curve in traced:
        parts.append(f"M {pt(curve.start_point)}")
        for seg in curve:
            if seg.is_corner:
                parts.append(f"L {pt(seg.c)} L {pt(seg.end_point)}")
            else:
                parts.append(f"C {pt(seg.c1)} {pt(seg.c2)} {pt(seg.end_point)}")
        parts.append("Z")
    return " ".join(parts)


def main() -> int:
    mask = load_mask()
    bands = _runs(mask.any(axis=1), min_gap=20)
    if len(bands) < 4:
        print(f"expected 4 row bands on the sheet, got {len(bands)}", file=sys.stderr)
        return 1

    # Row 3 is the white figure row (cleanest to threshold); row 4 its pawns.
    boxes = figures(mask, bands[2])
    if len(boxes) != 6:
        print(f"expected 6 figures in the row, got {len(boxes)}", file=sys.stderr)
        return 1
    # That row's own last figure is a paw too, but the pawn row draws it at the
    # pawn's true scale relative to the figures -- take it from there.
    boxes[5] = figures(mask, bands[3])[0]

    span = max(max(x1 - x0, y1 - y0) for x0, y0, x1, y1 in boxes)
    canvas = round(span * 1.10)

    OUT.mkdir(parents=True, exist_ok=True)
    for code, (x0, y0, x1, y1) in zip(ORDER, boxes):
        # Bitmap inverts internally, so hand it the negated ink mask -- passing
        # it as-is traces the *background* (a frame rect with the figure as a
        # hole) instead of the figure.
        sub = mask[y0:y1, x0:x1]
        traced = Bitmap(~sub).trace(turdsize=6, alphamax=1.0, opticurve=True,
                                    opttolerance=0.2)

        scale = PIECE_SCALE.get(code, 1.0)
        w, h = (x1 - x0) * scale, (y1 - y0) * scale
        d = curves_to_path(traced, scale, (canvas - w) / 2.0, (canvas - h) / 2.0)
        # Fills are only a fallback: the game recolours the tiger set per team.
        for side, fill in (("w", "#e9a33d"), ("b", "#2a2320")):
            (OUT / f"{side}{code}.svg").write_text(
                SVG.format(c=canvas, fill=fill, d=d), encoding="utf-8"
            )
        print(f"{code}: {x1 - x0}x{y1 - y0} px -> {canvas} canvas (scale {scale})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
