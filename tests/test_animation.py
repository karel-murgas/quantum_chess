"""Unit tests for the collapse-animation beat builder (pygame-free).

``build_animation`` turns a pre-resolve board snapshot + the resolver's
``CollapseEvent`` list into a sequence of drawable beats. These tests pin the
choreography rules directly, without any display: one travel beat up front, one
flash beat per measurement, vanished ghosts routed to fades, captures to a
shatter, and confirmed movers going solid in the rest layer.
"""

from fractions import Fraction

import chess

from quantumchess.collapse import CollapseEvent
from quantumchess.ui.animation import Token, build_animation


def _tok(pid, sq, prob=Fraction(1), solid=True, color=chess.WHITE, ptype=chess.KNIGHT):
    return Token(pid, color, ptype, sq, prob, solid)


def test_split_into_empty_squares_is_one_travel_beat():
    before = [_tok(5, chess.B1)]                       # solid knight at b1
    a = _tok(5, chess.A3, Fraction(1, 2), solid=False)
    b = _tok(5, chess.C3, Fraction(1, 2), solid=False)
    beats = build_animation(before, [(a, chess.B1), (b, chess.B1)], [])

    assert len(beats) == 1                             # no measurement -> just movement
    (beat,) = beats
    assert len(beat.travel) == 2                       # both branches slide out
    assert beat.flash_square is None
    assert {frm for _tok_, frm in beat.travel} == {chess.B1}


def test_split_fizzle_fades_the_lost_branch_and_keeps_the_other():
    before = [_tok(5, chess.B1)]
    a = _tok(5, chess.A3, Fraction(1, 2), solid=False)
    b = _tok(5, chess.C3, Fraction(1, 2), solid=False)
    # branch A measured "not there": the A-ghost is wiped.
    ev = CollapseEvent("split", 5, chess.A3, Fraction(1, 2), present=False,
                       removed=((chess.A3, Fraction(1, 2)),))
    beats = build_animation(before, [(a, chess.B1), (b, chess.B1)], [ev])

    assert len(beats) == 2                             # travel + one flash
    flash = beats[1]
    assert flash.flash_present is False
    assert {t.square for t in flash.fades} == {chess.A3}
    assert chess.C3 in {t.square for t in flash.rest}  # surviving branch still shown
    assert chess.A3 not in {t.square for t in flash.rest}


def test_capture_routes_the_victim_to_a_shatter():
    mover = _tok(1, chess.A1, ptype=chess.ROOK)
    victim = _tok(2, chess.A2, color=chess.BLACK, ptype=chess.PAWN)
    dest = _tok(1, chess.A2, ptype=chess.ROOK)         # mover ends on the victim's square
    ev = CollapseEvent("mover", 1, chess.A1, Fraction(1), present=True,
                       captured_square=chess.A2)
    beats = build_animation([mover, victim], [(dest, chess.A1)], [ev])

    flash = beats[-1]
    assert flash.shatter is not None
    assert flash.shatter.piece_id == 2 and flash.shatter.square == chess.A2
    # the surviving mover rests on a2; the victim is gone from the rest layer.
    assert chess.A2 in {t.square for t in flash.rest if t.piece_id == 1}
    assert all(t.piece_id != 2 for t in flash.rest)


def test_positive_mover_fades_its_siblings_then_rests_solid():
    m_src = _tok(1, chess.C1, Fraction(1, 2), solid=False, ptype=chess.BISHOP)
    m_sib = _tok(1, chess.F4, Fraction(1, 2), solid=False, ptype=chess.BISHOP)
    enemy = _tok(2, chess.A3, color=chess.BLACK, ptype=chess.PAWN)
    dest = _tok(1, chess.A3, Fraction(1, 2), solid=False, ptype=chess.BISHOP)

    mover_ev = CollapseEvent("mover", 1, chess.C1, Fraction(1, 2), present=True,
                             removed=((chess.F4, Fraction(1, 2)),))
    dest_ev = CollapseEvent("destination", 2, chess.A3, Fraction(1), present=True,
                            captured_square=chess.A3)
    beats = build_animation([m_src, m_sib, enemy], [(dest, chess.C1)], [mover_ev, dest_ev])

    assert len(beats) == 3                             # travel + two flashes
    mover_flash = beats[1]
    assert {t.square for t in mover_flash.fades} == {chess.F4}
    # once confirmed, the mover token in the rest layer is solid.
    resting_mover = next(t for t in mover_flash.rest if t.piece_id == 1)
    assert resting_mover.solid and resting_mover.prob == Fraction(1)


def test_fizzled_move_fades_the_stationary_mover():
    m_src = _tok(1, chess.C1, Fraction(1, 2), solid=False, ptype=chess.BISHOP)
    enemy = _tok(2, chess.A3, color=chess.BLACK, ptype=chess.PAWN)
    # no movers (a fizzle doesn't move); the mover ghost is wiped in its flash.
    ev = CollapseEvent("mover", 1, chess.C1, Fraction(1, 2), present=False,
                       removed=((chess.C1, Fraction(1, 2)),))
    beats = build_animation([m_src, enemy], [], [ev])

    assert len(beats) == 1                             # no travel, just the flash
    assert {t.square for t in beats[0].fades} == {chess.C1}
    assert beats[0].flash_present is False
