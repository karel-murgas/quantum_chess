"""Trace the `dragon` SVG piece set from two source sheets.

Build-time only -- the game never imports potrace. Regenerate the art with:

    pip install potracer pillow numpy
    python tools/trace_dragon.py

Two sheets were supplied, each with the usual four bands (gold figures, gold
pawns, white figures, white pawns) and six figures per row in K, Q, B, N, R, P
order. The final `dragon` set is a mix: bishop, rook and pawn come from
`assets/dragon_set_a.png`; king, queen and knight come from
`assets/dragon_set_b.png`. Only the shapes matter: the game tints the dragon
set to each team's own colour at runtime (see `ui/pieces.py`), so one
silhouette per piece is written to both `w<code>.svg` and `b<code>.svg`.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from potrace import Bitmap

ROOT = Path(__file__).resolve().parent.parent
SRC_A = ROOT / "assets" / "dragon_set_a.png"   # bishop, rook, pawn
SRC_B = ROOT / "assets" / "dragon_set_b.png"   # king, queen, knight
OUT = ROOT / "quantumchess" / "ui" / "assets" / "pieces" / "dragon"

# Left-to-right order of the figures on each sheet.
ORDER = ["K", "Q", "B", "N", "R", "P"]

# Which sheet supplies each piece.
SOURCE = {"K": "b", "Q": "b", "N": "b", "B": "a", "R": "a", "P": "a"}

SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {c} {c}" '
    'width="{c}" height="{c}">\n'
    '  <path fill="{fill}" fill-rule="evenodd" d="{d}"/>\n'
    "</svg>\n"
)


def load_mask(path: Path) -> np.ndarray:
    """Ink (gold or white figures) on the sheet's black background."""
    img = Image.open(path).convert("L")
    return np.asarray(img, dtype=np.uint8) > 60


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


def sheet_boxes(path: Path) -> dict[str, tuple[int, int, int, int]]:
    """Code -> bounding box for the six figures on the white (row 3) band --
    the cleanest to threshold, same convention as the tiger/cthulhu sheets."""
    mask = load_mask(path)
    bands = _runs(mask.any(axis=1), min_gap=20)
    if len(bands) < 3:
        print(f"{path.name}: expected >= 3 row bands, got {len(bands)}", file=sys.stderr)
        raise SystemExit(1)
    boxes = figures(mask, bands[2])
    if len(boxes) != 6:
        print(f"{path.name}: expected 6 figures in the row, got {len(boxes)}", file=sys.stderr)
        raise SystemExit(1)
    return mask, dict(zip(ORDER, boxes))


def main() -> int:
    mask_a, boxes_a = sheet_boxes(SRC_A)
    mask_b, boxes_b = sheet_boxes(SRC_B)
    masks = {"a": mask_a, "b": mask_b}
    boxes = {"a": boxes_a, "b": boxes_b}

    chosen = {code: (SOURCE[code], boxes[SOURCE[code]][code]) for code in ORDER}
    span = max(max(x1 - x0, y1 - y0) for _src, (x0, y0, x1, y1) in chosen.values())
    # A canvas that's a multiple of 32 sidesteps a pygame-ce `load_sized_svg`
    # rounding quirk where some viewBox/target-size ratios rasterize one pixel
    # off (e.g. a 304 canvas at a requested size of 120 returns 121x121).
    canvas = math.ceil(span * 1.10 / 32) * 32

    OUT.mkdir(parents=True, exist_ok=True)
    for code in ORDER:
        src, (x0, y0, x1, y1) = chosen[code]
        mask = masks[src]
        # Bitmap inverts internally, so hand it the negated ink mask -- passing
        # it as-is traces the *background* (a frame rect with the figure as a
        # hole) instead of the figure.
        sub = mask[y0:y1, x0:x1]
        traced = Bitmap(~sub).trace(turdsize=6, alphamax=1.0, opticurve=True,
                                    opttolerance=0.2)

        w, h = x1 - x0, y1 - y0
        d = curves_to_path(traced, 1.0, (canvas - w) / 2.0, (canvas - h) / 2.0)
        # Fills are only a fallback: the game recolours the dragon set per team.
        for side, fill in (("w", "#e0a020"), ("b", "#2a1a0a")):
            (OUT / f"{side}{code}.svg").write_text(
                SVG.format(c=canvas, fill=fill, d=d), encoding="utf-8"
            )
        print(f"{code}: sheet {src}, {w}x{h} px -> {canvas} canvas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
