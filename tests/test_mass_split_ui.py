"""UI-level tests for mass-split planning (the 'mass split' dial layered on
'mass movement'), driven headlessly like test_mass_move_ui.py.

Focus: the per-ghost two-pick gesture (first branch -> optionally a second
branch = split, or the first square again = plain single move), and that a
confirmed plan reaches ``collapse.resolve_mass_split``. The top-level
Move/Split toggle picks which gesture the ghost you're aiming uses -- in Move
mode a planned ghost only relocates (one click), so these tests toggle into
Split mode before splitting one.
"""

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


def _split_app(mass_split=True):
    """App (mass movement + mass split on) with a White rook superposed
    a1 (1/2) / h1 (1/2); kings off the a/h files."""
    app = App(_SCREEN, GameConfig(collapse_mode=CollapseMode.FULL,
                                  mass_movement=True, mass_split=mass_split, seed=0))
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


def test_can_mass_split_gate():
    on, _ = _split_app(mass_split=True)
    off, _ = _split_app(mass_split=False)
    assert on.can_mass_split() and not off.can_mass_split()
    # the toggle is what arms the split gesture, and only when the dial is on
    assert on._plan_cap() == 1 and not on.plan_splitting()   # move mode
    on.toggle_mode()
    assert on._plan_cap() == 2 and on.plan_splitting()       # split mode
    off.toggle_mode()
    assert off._plan_cap() == 1 and not off.plan_splitting()


def test_move_mode_ghost_click_commits_a_single_move_not_a_split():
    """Regression for a user report: in Move mode, aiming one ghost and then
    clicking the *other* ghost split the first one into two branches instead of
    selecting the second -- the two-pick split gesture was always armed, even
    though the toggle said MOVE. Move mode must commit the first pick outright."""
    app, rook = _split_app()
    _click(app, chess.A1)          # enter planning (mode is "move")
    _click(app, chess.A1)          # arm the a1 ghost
    _click(app, chess.A4)          # its target -> committed, ghost deselected
    assert app.plan[chess.A1] == (chess.A4,)
    assert app.plan_pick_a is None and app.plan_active is None

    _click(app, chess.H1)          # selects the other ghost -- does NOT split a1
    assert app.plan_active == chess.H1
    assert app.plan[chess.A1] == (chess.A4,)


def test_toggling_mode_mid_plan_switches_the_gesture():
    app, rook = _split_app()
    _click(app, chess.A1)          # enter planning
    _click(app, chess.A1)          # arm a1
    app.toggle_mode()              # -> split mode; drops the half-made assignment
    assert app.plan_active is None and app.is_planning()
    _click(app, chess.A1)
    _click(app, chess.A4)          # now the first pick of a split
    assert app.plan_pick_a == chess.A4
    _click(app, chess.A8)
    assert app.plan[chess.A1] == (chess.A4, chess.A8)

    app.toggle_mode()              # back to move mode
    _click(app, chess.H1)
    _click(app, chess.H4)          # single click commits again
    assert app.plan[chess.H1] == (chess.H4,)
    assert app.plan_active is None


def test_reported_bug_toggling_split_mode_first_still_reaches_both_ghosts():
    """Regression for a user report: with Mass split on, toggling the
    top-level Move/Split control to "Split" before selecting the superposed
    piece used to fall through to an ordinary one-ghost split -- ending the
    turn after touching only one ghost, with no chance to act on the second.
    Selecting the piece must open planning (and let both ghosts be assigned)
    no matter which mode was active when it was clicked."""
    app, rook = _split_app()
    app.toggle_mode()
    assert app.mode == "split"
    _click(app, chess.A1)          # select the superposed rook
    assert app.is_planning()       # not an ordinary single-ghost split

    _click(app, chess.A1)          # arm the a1 ghost
    _click(app, chess.A4)          # first branch
    _click(app, chess.A8)          # second branch -> a1 splits a4/a8
    assert app.plan[chess.A1] == (chess.A4, chess.A8)

    app.toggle_mode()              # move mode for the second ghost
    _click(app, chess.H1)          # arm the h1 ghost too
    _click(app, chess.H4)          # move it
    assert app.plan[chess.H1] == (chess.H4,)

    _click_rect(app, render.mass_controls_rects()["confirm"])
    assert not app.is_planning()
    assert app.qb.turn == chess.BLACK
    squares = {g.square: g.prob for g in app.qb.ghosts_of(rook.id)}
    assert squares == {chess.A4: Fraction(1, 4), chess.A8: Fraction(1, 4),
                       chess.H4: Fraction(1, 2)}


def test_two_picks_split_a_ghost_into_two_branches():
    app, rook = _split_app()
    _click(app, chess.A1)          # enter planning
    app.toggle_mode()              # split mode: aiming a ghost fans it out
    _click(app, chess.A1)          # active a1
    _click(app, chess.A4)          # first branch
    assert app.plan_pick_a == chess.A4
    assert app.plan[chess.A1] == (chess.A4,)     # provisional single so far
    assert app.plan_active == chess.A1           # still aiming
    _click(app, chess.A8)          # second branch -> split
    assert app.plan[chess.A1] == (chess.A4, chess.A8)
    assert app.plan_pick_a is None
    assert app.plan_active is None


def test_click_first_branch_again_makes_a_plain_move():
    app, rook = _split_app()
    _click(app, chess.A1)
    app.toggle_mode()              # split mode
    _click(app, chess.A1)
    _click(app, chess.A4)          # first branch
    _click(app, chess.A4)          # same square again -> commit single move
    assert app.plan[chess.A1] == (chess.A4,)
    assert app.plan_pick_a is None
    assert app.plan_active is None


def test_split_with_a_staying_branch():
    app, rook = _split_app()
    _click(app, chess.A1)
    app.toggle_mode()              # split mode
    _click(app, chess.A1)
    _click(app, chess.A4)          # first branch: move
    _click(app, chess.A1)          # second branch: the source square (stay)
    assert app.plan[chess.A1] == (chess.A4, chess.A1)


def test_split_stay_disabled_withholds_source_square_as_second_branch():
    app, rook = _split_app()
    app.config.split_stay_enabled = False
    _click(app, chess.A1)
    app.toggle_mode()              # split mode
    _click(app, chess.A1)
    assert chess.A1 not in app.plan_legal()         # own square no longer offered
    _click(app, chess.A4)          # first branch: move
    assert app.plan_pick_a == chess.A4
    assert chess.A1 not in app.plan_legal()         # nor as the second branch
    _click(app, chess.A1)          # not a legal target, but a1 is itself a planned
                                    # ghost -> re-selects it for editing instead
    assert app.plan_active == chess.A1
    assert app.plan_pick_a is None
    assert app.plan[chess.A1] == (chess.A4,)        # branch A's provisional single move stands


def test_split_stay_disabled_does_not_affect_move_only_leg():
    """A ghost that's simply held in place (not splitting) is unaffected by the
    dial -- that's a plain move leg, not a split, per CLAUDE.md's clarification
    that split stay only governs actual splits."""
    app, rook = _split_app(mass_split=True)
    app.config.split_stay_enabled = False
    _click(app, chess.A1)          # enter planning in move mode
    _click(app, chess.A1)          # arm a1
    _click(app, chess.A1)          # hold in place -- a move-only leg, not a split
    assert app.plan[chess.A1] == (chess.A1,)
    assert app.plan_active is None


def test_confirm_split_resolves_without_conflict():
    app, rook = _split_app()
    _click(app, chess.A1)
    app.toggle_mode()              # split mode: a1 fans out
    _click(app, chess.A1)
    _click(app, chess.A4)
    _click(app, chess.A8)          # a1 splits a4 + a8
    app.toggle_mode()              # back to move mode for the other ghost
    _click(app, chess.H1)
    _click(app, chess.H4)          # h1 relocates (single move)
    assert app.plan[chess.H1] == (chess.H4,)
    _click_rect(app, render.mass_controls_rects()["confirm"])
    assert not app.is_planning()
    assert app.qb.turn == chess.BLACK
    squares = {g.square: g.prob for g in app.qb.ghosts_of(rook.id)}
    assert squares == {chess.A4: Fraction(1, 4), chess.A8: Fraction(1, 4),
                       chess.H4: Fraction(1, 2)}


def test_confirm_split_branch_capture_uses_rng():
    app, rook = _split_app()
    bishop = app.qb._add_piece(chess.BLACK, chess.BISHOP, chess.A4)
    app.rng = ScriptedRng(draws=[0.1])   # the a4 capture half (1/4) wins the roll
    _click(app, chess.A1)
    app.toggle_mode()              # split mode
    _click(app, chess.A1)
    _click(app, chess.A4)          # branch 1: capture bishop
    _click(app, chess.B1)          # branch 2: safe
    _click(app, chess.H1)
    _click(app, chess.H1)          # h1 holds
    _click_rect(app, render.mass_controls_rects()["confirm"])
    assert not app.is_planning()
    assert not bishop.alive
    remaining = app.qb.ghosts_of(rook.id)
    assert len(remaining) == 1
    assert remaining[0].square == chess.A4 and remaining[0].prob == Fraction(1)


def test_escape_backs_out_of_in_progress_split_then_cancels_plan():
    app, rook = _split_app()
    _click(app, chess.A1)
    app.toggle_mode()              # split mode
    _click(app, chess.A1)
    _click(app, chess.A4)          # branch A chosen
    assert app.plan_pick_a == chess.A4
    app.cancel_selection()         # first Escape: drop the in-progress pick
    assert app.is_planning()
    assert app.plan_pick_a is None and app.plan_active is None
    app.cancel_selection()         # second Escape: cancel the whole plan
    assert not app.is_planning()
    assert app.qb.turn == chess.WHITE


def test_split_promotion_branch_prompts_per_branch():
    app = App(_SCREEN, GameConfig(collapse_mode=CollapseMode.FULL,
                                  mass_movement=True, mass_split=True, seed=0))
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    pawn = qb._add_piece(chess.WHITE, chess.PAWN, chess.A7)
    qb.ghosts_of(pawn.id)[0].prob = Fraction(1, 2)
    qb.ghosts.append(Ghost(pawn.id, chess.H2, Fraction(1, 2)))
    qb._add_piece(chess.WHITE, chess.KING, chess.E1)
    qb._add_piece(chess.BLACK, chess.KING, chess.E8)
    app.qb = qb
    app._ply += 1
    app.rng = ScriptedRng(draws=[0.1])   # a8 branch (1/4) wins

    _click(app, chess.A7)          # enter planning
    app.toggle_mode()              # split mode
    _click(app, chess.A7)          # active a7
    _click(app, chess.A8)          # branch 1 -> promotes, prompt
    assert app._pending_plan_promo == (chess.A7, chess.A8)
    _click_rect(app, render.promotion_rects()[chess.ROOK])
    assert app.plan_promo[(chess.A7, chess.A8)] == chess.ROOK
    assert app.plan_pick_a == chess.A8            # first branch committed, still aiming
    _click(app, chess.A7)          # branch 2: stay -> split (a8, a7)
    assert app.plan[chess.A7] == (chess.A8, chess.A7)
    _click(app, chess.H2)
    _click(app, chess.H2)          # h2 holds
    _click_rect(app, render.mass_controls_rects()["confirm"])
    assert app.qb.pieces[pawn.id].ptype == chess.ROOK


# --------------------------------------------------- "all ghosts must act"
def test_plan_fully_acted_is_false_while_a_ghost_still_defaults_to_stay():
    app, rook = _split_app()
    _click(app, chess.A1)          # enter planning; both legs default to "stay"
    assert app._plan_fully_acted() is False
    _click(app, chess.A1)          # arm a1
    _click(app, chess.A4)          # a1 moves
    assert app.plan[chess.A1] == (chess.A4,)
    assert app._plan_fully_acted() is False   # h1 still untouched
    _click(app, chess.H1)
    _click(app, chess.H4)          # h1 moves too
    assert app._plan_fully_acted() is True


def test_confirm_blocked_while_a_ghost_has_not_acted():
    app, rook = _split_app()
    app.config.mass_all_must_act = True
    _click(app, chess.A1)          # enter planning
    _click(app, chess.A1)
    _click(app, chess.A4)          # a1 acts; h1 is still left at its default stay
    _click_rect(app, render.mass_controls_rects()["confirm"])
    assert app.is_planning()                 # confirm was refused
    assert app.qb.turn == chess.WHITE
    assert app.plan[chess.A1] == (chess.A4,)  # the in-progress plan survives untouched


def test_confirm_succeeds_once_every_ghost_has_acted():
    app, rook = _split_app()
    app.config.mass_all_must_act = True
    _click(app, chess.A1)
    _click(app, chess.A1)
    _click(app, chess.A4)          # a1 acts
    _click(app, chess.H1)
    _click(app, chess.H4)          # h1 acts too -- every ghost has now moved
    _click_rect(app, render.mass_controls_rects()["confirm"])
    assert not app.is_planning()
    assert app.qb.turn == chess.BLACK


def test_enter_key_confirm_is_also_blocked_while_a_ghost_has_not_acted():
    app, rook = _split_app()
    app.config.mass_all_must_act = True
    _click(app, chess.A1)
    _click(app, chess.A1)
    _click(app, chess.A4)          # only a1 acts
    app.handle_keydown(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert app.is_planning()
    assert app.qb.turn == chess.WHITE
