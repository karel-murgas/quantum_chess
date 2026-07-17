"""Tests for the piece-set registry / renderer (ui/pieces.py).

Headless, but needs a pygame video context for surface ops -- so it forces the
dummy SDL driver like the other UI tests.
"""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import chess
import pygame
import pytest

pygame.init()
pygame.display.set_mode((64, 64))

from quantumchess.ui import theme, pieces  # noqa: E402


def setup_function(_fn):
    theme.apply_theme("cyberpunk", (255, 46, 199), (0, 224, 255))
    pieces.set_active("cburnett")


def test_available_lists_all_sets_including_unicode():
    keys = [k for k, _label in pieces.available()]
    assert set(keys) == {
        "cburnett", "merida", "tiger", "cthulhu", "dragon", "neon", "unicode",
    }


def test_set_active_falls_back_on_unknown():
    pieces.set_active("does-not-exist")
    assert pieces.active() == "cburnett"


def test_set_active_is_per_side():
    pieces.set_active("merida", "neon")
    assert pieces.active(chess.WHITE) == "merida"
    assert pieces.active(chess.BLACK) == "neon"
    # a single argument applies to both sides
    pieces.set_active("cburnett")
    assert pieces.active(chess.WHITE) == "cburnett"
    assert pieces.active(chess.BLACK) == "cburnett"


@pytest.mark.parametrize("set_name", ["cburnett", "merida", "tiger", "cthulhu", "dragon"])
def test_svg_sets_rasterize_with_content(set_name):
    art = pieces.render_art(set_name, chess.KNIGHT, chess.WHITE, 120)
    assert art.get_size() == (120, 120)
    # a rasterized piece actually draws something (non-empty alpha bbox)
    assert art.get_bounding_rect().width > 0


def test_neon_silhouette_uses_side_neon_colour():
    # neon recolours the base silhouette to theme.WHITE_NEON for the white side
    art = pieces.render_art("neon", chess.ROOK, chess.WHITE, 120)
    bb = art.get_bounding_rect()
    r, g, b, a = art.get_at(bb.center)
    assert (r, g, b) == theme.WHITE_NEON
    assert a > 0


def _an_inked_pixel(art):
    """A fully-opaque pixel of the silhouette (its bbox centre may fall in one
    of the art's cutouts, e.g. the tiger's stripes or cthulhu's eyes, which are
    holes)."""
    bb = art.get_bounding_rect()
    for y in range(bb.top, bb.bottom):
        for x in range(bb.left, bb.right):
            if art.get_at((x, y))[3] == 255:
                return x, y
    raise AssertionError("silhouette has no opaque pixel")


@pytest.mark.parametrize("set_name", ["tiger", "cthulhu", "dragon"])
def test_tinted_own_set_silhouette_uses_side_team_colour(set_name):
    # tiger/cthulhu are tinted sets too, but off their own bundled shapes
    for color, tint in ((chess.WHITE, theme.WHITE_NEON), (chess.BLACK, theme.BLACK_NEON)):
        art = pieces.render_art(set_name, chess.KING, color, 120)
        r, g, b, _a = art.get_at(_an_inked_pixel(art))
        assert (r, g, b) == tint


@pytest.mark.parametrize("set_name", ["tiger", "cthulhu", "dragon"])
def test_tinted_own_set_shapes_are_the_same_for_both_sides(set_name):
    # the source art has no light/dark pair -- the colour comes from the tint
    white = pieces._raster(set_name, chess.QUEEN, chess.WHITE, 96)
    black = pieces._raster(set_name, chess.QUEEN, chess.BLACK, 96)
    assert white.get_bounding_rect() == black.get_bounding_rect()


@pytest.mark.parametrize("set_name", ["tiger", "cthulhu", "dragon"])
def test_tinted_own_set_token_draws_a_contrast_rim(set_name):
    # a token whose tint is pale gets a dark rim outside the art's own alpha,
    # so it still reads on a light square
    theme.apply_theme("cyberpunk", (245, 245, 245), (0, 224, 255))
    pieces.set_active(set_name)
    size = 120
    art = pieces.render_art(set_name, chess.ROOK, chess.WHITE, size)
    tok = pieces.render_token(set_name, chess.ROOK, chess.WHITE, size)
    pad = (tok.get_width() - size) // 2

    # find a pixel just outside the silhouette's left edge, on its centre row
    bb = art.get_bounding_rect()
    y = bb.centery
    x = next(x for x in range(bb.left, bb.right) if art.get_at((x, y))[3] > 0)
    assert art.get_at((x - 2, y))[3] == 0            # empty in the bare art
    rim = tok.get_at((pad + x - 2, pad + y))
    assert rim[3] > 0                                 # ...but inked in the token
    assert sum(rim[:3]) < sum(theme.WHITE_NEON)       # and darker than the tint


def test_render_token_pads_for_shadow_or_glow():
    # composited token is larger than the bare art (room for shadow/glow spread)
    tok = pieces.render_token("cburnett", chess.QUEEN, chess.BLACK, 100)
    assert tok.get_width() > 100 and tok.get_height() > 100


def test_render_token_cached_by_revision():
    a = pieces.render_token("cburnett", chess.PAWN, chess.WHITE, 80)
    b = pieces.render_token("cburnett", chess.PAWN, chess.WHITE, 80)
    assert a is b                      # same revision -> cached identity
    pieces.set_active("merida")        # bumps revision, clears token cache
    pieces.set_active("cburnett")
    c = pieces.render_token("cburnett", chess.PAWN, chess.WHITE, 80)
    assert c is not a                  # recomputed after the revision bump
