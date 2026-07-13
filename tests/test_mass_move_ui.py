"""UI-level tests for mass-move planning (the 'mass movement' dial), driven
headlessly like test_m4_ui.py."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from fractions import Fraction

import chess
import pygame

from quantumchess.config import CollapseMode, GameConfig
from quantumchess.model import Ghost, QuantumBoard
from quantumchess.ui import render, theme
from quantumchess.ui.app import App

from tests.test_m3_collapse import ScriptedRng

pygame.init()
_SCREEN = pygame.display.set_mode((theme.WINDOW_W, theme.WINDOW_H))


def _click(app, square):
    app.handle_mouse_down(render.square_rect(square).center)


def _click_rect(app, rect):
    app.handle_mouse_down(rect.center)


def _mass_app(mass=True):
    """App whose board is a White rook superposed a1 (1/2) / h1 (1/2)."""
    app = App(_SCREEN, GameConfig(collapse_mode=CollapseMode.FULL,
                                  mass_movement=mass, seed=0))
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    rook = qb._add_piece(chess.WHITE, chess.ROOK, chess.A1)
    qb.ghosts_of(rook.id)[0].prob = Fraction(1, 2)
    qb.ghosts.append(Ghost(rook.id, chess.H1, Fraction(1, 2)))
    qb._add_piece(chess.WHITE, chess.KING, chess.E4)
    qb._add_piece(chess.BLACK, chess.KING, chess.E8)
    app.qb = qb
    app._ply += 1
    return app, rook


def test_dial_off_selects_superposed_piece_normally():
    app, rook = _mass_app(mass=False)
    _click(app, chess.A1)
    assert not app.is_planning()
    assert app.selected == chess.A1


def test_dial_on_enters_planning_for_superposed_piece():
    app, rook = _mass_app(mass=True)
    _click(app, chess.A1)
    assert app.is_planning()
    assert app.plan_piece == rook.id
    assert app.plan == {chess.A1: (chess.A1,), chess.H1: (chess.H1,)}  # all default to "stay"
    assert app.selected is None


def test_dial_on_enters_planning_even_while_in_split_mode():
    """Regression: selecting a superposed piece must open mass-move planning
    regardless of the top-level Move/Split toggle -- previously it only
    triggered while `mode == "move"`, so a player who switched to Split mode
    (a natural thing to try when they want to split ghosts) got dropped into
    an ordinary one-ghost split instead of planning, and the turn ended after
    touching only one ghost."""
    app, rook = _mass_app(mass=True)
    app.toggle_mode()
    assert app.mode == "split"
    _click(app, chess.A1)
    assert app.is_planning()
    assert app.plan_piece == rook.id
    assert app.selected is None
    assert app.mode == "move"   # the toggle is meaningless during planning; normalized back


def test_solid_piece_not_planned_even_with_dial_on():
    app, rook = _mass_app(mass=True)
    _click(app, chess.E4)          # the (solid) king
    assert not app.is_planning()
    assert app.selected == chess.E4


def test_assign_legs_and_confirm_no_conflict():
    app, rook = _mass_app(mass=True)
    _click(app, chess.A1)          # enter planning
    _click(app, chess.A1)          # make a1 the active ghost
    assert app.plan_active == chess.A1
    _click(app, chess.A4)          # aim it at a4
    assert app.plan[chess.A1] == (chess.A4,)
    assert app.plan_active is None
    _click(app, chess.H1)          # active h1
    _click(app, chess.H4)          # aim it at h4
    assert app.plan[chess.H1] == (chess.H4,)

    _click_rect(app, render.mass_controls_rects()["confirm"])
    assert not app.is_planning()
    assert app.qb.turn == chess.BLACK
    squares = {g.square: g.prob for g in app.qb.ghosts_of(rook.id)}
    assert squares == {chess.A4: Fraction(1, 2), chess.H4: Fraction(1, 2)}


def test_confirm_with_conflict_uses_rng_and_captures():
    app, rook = _mass_app(mass=True)
    bishop = app.qb._add_piece(chess.BLACK, chess.BISHOP, chess.A4)
    app.rng = ScriptedRng(draws=[0.1])   # the a1->a4 capture leg (prob 1/2) wins

    _click(app, chess.A1)          # enter planning
    _click(app, chess.A1)
    _click(app, chess.A4)          # a1 -> a4 (captures the bishop)
    _click(app, chess.H1)
    _click(app, chess.H4)          # h1 -> h4 (safe)
    _click_rect(app, render.mass_controls_rects()["confirm"])

    assert not app.is_planning()
    assert not bishop.alive
    remaining = app.qb.ghosts_of(rook.id)
    assert len(remaining) == 1
    assert remaining[0].square == chess.A4 and remaining[0].prob == Fraction(1)


def test_escape_cancels_plan():
    app, rook = _mass_app(mass=True)
    _click(app, chess.A1)
    assert app.is_planning()
    app.cancel_selection()
    assert not app.is_planning()
    assert app.qb.turn == chess.WHITE   # nothing was played


def test_switching_to_split_mode_cancels_plan():
    app, rook = _mass_app(mass=True)
    _click(app, chess.A1)
    assert app.is_planning()
    app.toggle_mode()               # move -> split
    assert not app.is_planning()
    assert app.mode == "split"


def test_promotion_leg_prompts_and_uses_chosen_piece():
    app = App(_SCREEN, GameConfig(collapse_mode=CollapseMode.FULL,
                                  mass_movement=True, seed=0))
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    pawn = qb._add_piece(chess.WHITE, chess.PAWN, chess.A7)
    qb.ghosts_of(pawn.id)[0].prob = Fraction(1, 2)
    qb.ghosts.append(Ghost(pawn.id, chess.H2, Fraction(1, 2)))
    qb._add_piece(chess.WHITE, chess.KING, chess.E1)
    qb._add_piece(chess.BLACK, chess.KING, chess.E8)
    app.qb = qb
    app._ply += 1
    app.rng = ScriptedRng(draws=[0.1])   # a7 leg wins

    _click(app, chess.A7)          # enter planning
    _click(app, chess.A7)          # active a7
    _click(app, chess.A8)          # aim at a8 -> should prompt for promotion
    assert app._pending_plan_promo == (chess.A7, chess.A8)
    assert app.plan[chess.A7] == (chess.A7,)   # not committed until a piece is picked

    _click_rect(app, render.promotion_rects()[chess.ROOK])
    assert app._pending_plan_promo is None
    assert app.plan[chess.A7] == (chess.A8,)
    assert app.plan_promo[(chess.A7, chess.A8)] == chess.ROOK

    _click(app, chess.H2)
    _click(app, chess.H3)          # h2 -> h3 (safe)
    _click_rect(app, render.mass_controls_rects()["confirm"])
    assert app.qb.pieces[pawn.id].ptype == chess.ROOK


def test_reaiming_a_promo_leg_elsewhere_drops_the_promotion():
    app = App(_SCREEN, GameConfig(mass_movement=True, seed=0))
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    pawn = qb._add_piece(chess.WHITE, chess.PAWN, chess.A7)
    qb.ghosts_of(pawn.id)[0].prob = Fraction(1, 2)
    qb.ghosts.append(Ghost(pawn.id, chess.H2, Fraction(1, 2)))
    qb._add_piece(chess.WHITE, chess.KING, chess.E1)
    qb._add_piece(chess.BLACK, chess.KING, chess.E8)
    app.qb = qb
    app._ply += 1

    _click(app, chess.A7)
    _click(app, chess.A7)
    _click(app, chess.A8)
    _click_rect(app, render.promotion_rects()[chess.QUEEN])
    assert app.plan_promo.get((chess.A7, chess.A8)) == chess.QUEEN
    # re-aim the same ghost back to holding -> the stale promotion is cleared
    _click(app, chess.A7)          # select it again
    _click(app, chess.A7)          # click itself -> hold
    assert app.plan[chess.A7] == (chess.A7,)
    assert (chess.A7, chess.A8) not in app.plan_promo


def test_cancel_button_aborts_plan():
    app, rook = _mass_app(mass=True)
    _click(app, chess.A1)
    _click(app, chess.A1)
    _click(app, chess.A4)           # a real assignment in progress
    _click_rect(app, render.mass_controls_rects()["cancel"])
    assert not app.is_planning()
    assert app.qb.turn == chess.WHITE
