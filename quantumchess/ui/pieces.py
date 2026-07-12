"""Piece-set rendering -- pluggable board-token art.

The board used to draw pieces as tinted Unicode glyphs only. This module adds
selectable art sets and is the single place that knows how to turn a
``(ptype, color)`` into a picture:

* ``"unicode"`` -- the original glyph look (drawn by ``render.draw_token``'s
  own font path; this module reports it as available but produces no raster,
  since it needs the skin's font).
* ``"cburnett"`` / ``"merida"`` -- real vector piece sets, rasterized on demand
  from the bundled SVGs (``assets/pieces/<set>/<code>.svg``) via pygame-ce's
  native ``pygame.image.load_sized_svg`` -- no external dependency, and crisp
  at any size because the SVG is rendered at the exact pixel size requested.
* ``"neon"`` -- generated at runtime, not bundled: each cburnett silhouette is
  recoloured to the side's neon colour (``theme.WHITE_NEON`` / ``BLACK_NEON``)
  and given a glow. The natural fit for the cyberpunk board.

Adding a future thematic set = drop ``assets/pieces/<name>/{wP..bK}.svg`` in and
add one ``(key, label)`` line to ``PIECE_SETS``.

Two caches: raw SVG rasters keyed by ``(set, code, size)`` (theme-independent,
never invalidated), and composited tokens (with recolour/shadow/glow) keyed by
a revision counter that ``set_active`` bumps -- so a mid-match theme/colour or
set change repaints without stale neon colours, while the expensive SVG raster
survives.
"""

from __future__ import annotations

import io
from pathlib import Path

import chess
import pygame

from . import theme

_ASSET_ROOT = Path(__file__).parent / "assets" / "pieces"

# Ordered (key, label) -- drives the menu picker and the persisted dial value.
PIECE_SETS = [
    ("cburnett", "Classic"),
    ("merida", "Merida"),
    ("neon", "Neon"),
    ("unicode", "Unicode"),
]
_SET_KEYS = {k for k, _ in PIECE_SETS}

_CODE = {
    chess.PAWN: "P", chess.KNIGHT: "N", chess.BISHOP: "B",
    chess.ROOK: "R", chess.QUEEN: "Q", chess.KING: "K",
}

# The neon set has no art of its own; it recolours this base set's silhouettes.
_NEON_BASE = "cburnett"

_active = {chess.WHITE: "cburnett", chess.BLACK: "cburnett"}
_rev = 0                       # bumped on set/theme change; keys _token_cache
_svg_bytes: dict = {}          # (set, code) -> raw svg bytes
_raster_cache: dict = {}       # (set, code, size) -> Surface  (theme-independent)
_token_cache: dict = {}        # (rev, set, ptype, color, size, glow) -> Surface


def available():
    """Ordered list of ``(key, label)`` piece sets for the menu."""
    return list(PIECE_SETS)


def is_set(name: str) -> bool:
    return name in _SET_KEYS


def active(color: bool = chess.WHITE) -> str:
    """The active set for a side (each team can pick its own -- see
    ``set_active``). ``color`` is a python-chess colour bool (True == white)."""
    return _active.get(color, "cburnett")


def set_active(white_name: str, black_name: str = None):
    """Select the active set **per side** (and mark theme-dependent caches
    stale). ``black_name`` defaults to ``white_name`` (both sides the same).
    Safe to call on every config/theme change -- it always bumps the revision
    so a recoloured/glowing set picks up new team colours, while cached SVG
    rasters (theme-independent) survive."""
    global _rev
    if black_name is None:
        black_name = white_name
    _active[chess.WHITE] = white_name if white_name in _SET_KEYS else "cburnett"
    _active[chess.BLACK] = black_name if black_name in _SET_KEYS else "cburnett"
    _rev += 1
    _token_cache.clear()


# --------------------------------------------------------------- rasterization
def _load_bytes(set_name: str, code: str) -> bytes:
    key = (set_name, code)
    data = _svg_bytes.get(key)
    if data is None:
        with open(_ASSET_ROOT / set_name / f"{code}.svg", "rb") as fh:
            data = fh.read()
        _svg_bytes[key] = data
    return data


def _raster(set_name: str, ptype: int, color: bool, size: int) -> pygame.Surface:
    """SVG rasterized to ``size`` x ``size`` (RGBA), cached theme-independently."""
    code = ("w" if color == chess.WHITE else "b") + _CODE[ptype]
    key = (set_name, code, size)
    surf = _raster_cache.get(key)
    if surf is None:
        data = _load_bytes(set_name, code)
        surf = pygame.image.load_sized_svg(io.BytesIO(data), (size, size)).convert_alpha()
        _raster_cache[key] = surf
    return surf


# ------------------------------------------------------------------ recolouring
def _recolor(art: pygame.Surface, color) -> pygame.Surface:
    """Return ``art`` as a solid-``color`` silhouette, preserving its
    anti-aliased alpha. Trick: BLEND_RGBA_MAX floods rgb to white while keeping
    each pixel's own alpha, then BLEND_RGBA_MULT stamps that alpha shape onto a
    flat colour fill -- no numpy needed."""
    aa = art.copy()
    aa.fill((255, 255, 255, 0), special_flags=pygame.BLEND_RGBA_MAX)
    out = pygame.Surface(art.get_size(), pygame.SRCALPHA)
    out.fill((*color, 255))
    out.blit(aa, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return out


def render_art(set_name: str, ptype: int, color: bool, size: int) -> pygame.Surface:
    """The piece picture alone (no shadow/glow), ``size`` x ``size`` RGBA."""
    if set_name == "neon":
        base = _raster(_NEON_BASE, ptype, color, size)
        neon = theme.WHITE_NEON if color == chess.WHITE else theme.BLACK_NEON
        return _recolor(base, neon)
    return _raster(set_name, ptype, color, size)


# -------------------------------------------------------------------- compositor
def render_token(set_name: str, ptype: int, color: bool, size: int, *, glow=None):
    """A ready-to-blit token: the piece art with a soft drop shadow (classic
    sets) or a coloured glow (``glow`` given, used by the neon set). Returned
    surface is larger than ``size`` (padded for the shadow/glow spread) and is
    cached; callers apply per-ghost opacity with ``set_alpha`` on a copy."""
    key = (_rev, set_name, ptype, color, size, glow)
    tok = _token_cache.get(key)
    if tok is not None:
        return tok

    art = render_art(set_name, ptype, color, size)
    pad = max(2, size // 6)
    canvas = pygame.Surface((size + 2 * pad, size + 2 * pad), pygame.SRCALPHA)
    blur = max(1, size // 18)

    if glow is not None:
        halo = _recolor(art, glow)
        halo = pygame.transform.gaussian_blur(halo, blur * 2)
        # Two passes deepen the neon bloom without a separate bright core.
        canvas.blit(halo, (pad, pad))
        canvas.blit(halo, (pad, pad))
    else:
        shadow = _recolor(art, (0, 0, 0))
        shadow.set_alpha(120)
        shadow = pygame.transform.gaussian_blur(shadow, blur)
        off = max(1, size // 22)
        canvas.blit(shadow, (pad + off, pad + off))

    canvas.blit(art, (pad, pad))
    _token_cache[key] = canvas
    return canvas
