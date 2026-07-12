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
    assert set(keys) == {"cburnett", "merida", "neon", "unicode"}


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


@pytest.mark.parametrize("set_name", ["cburnett", "merida"])
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
