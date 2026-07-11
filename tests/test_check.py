"""Tests for the advisory check-probability overlay (quantumchess/check.py).

Fully headless -- no pygame. Builds small hand-made positions and asserts the
exact ``Fraction`` danger, plus the "would this move expose my king?" warning.
"""

from fractions import Fraction

import chess

from quantumchess import check, rules
from quantumchess.model import Ghost, QuantumBoard


def make_board(*pieces):
    """pieces: (color, ptype, square) tuples. Returns a QuantumBoard with each
    piece solid on its square."""
    qb = QuantumBoard()
    ids = []
    for color, ptype, square in pieces:
        ids.append(qb._add_piece(color, ptype, square).id)
    return qb, ids


def superpose(qb, piece_id, *placements):
    """Replace ``piece_id``'s ghosts with the given ``(square, Fraction)`` list."""
    qb.ghosts = [g for g in qb.ghosts if g.piece_id != piece_id]
    for square, prob in placements:
        qb.ghosts.append(Ghost(piece_id, square, prob))


def test_no_threat_is_safe():
    qb, _ = make_board((chess.WHITE, chess.KING, chess.E1),
                       (chess.BLACK, chess.KING, chess.E8))
    assert check.check_probability(qb, chess.WHITE) == 0
    assert check.check_probability(qb, chess.BLACK) == 0


def test_solid_rook_is_full_check():
    # Black rook down a clear e-file onto a solid white king == certain capture.
    qb, _ = make_board((chess.WHITE, chess.KING, chess.E1),
                       (chess.BLACK, chess.ROOK, chess.E8),
                       (chess.BLACK, chess.KING, chess.A8))
    assert check.check_probability(qb, chess.WHITE) == 1


def test_superposed_attacker_scales_the_check():
    # Queen only half-present on the attacking square -> half a check.
    qb, ids = make_board((chess.WHITE, chess.KING, chess.E1),
                         (chess.BLACK, chess.QUEEN, chess.E8),
                         (chess.BLACK, chess.KING, chess.H8))
    superpose(qb, ids[1], (chess.E8, Fraction(1, 2)), (chess.A4, Fraction(1, 2)))
    assert check.check_probability(qb, chess.WHITE) == Fraction(1, 2)


def test_two_independent_half_threats_aggregate():
    # Two half-present rooks, one on the file, one on the rank:
    # 1 - (1 - 1/2)(1 - 1/2) = 3/4.
    qb, ids = make_board((chess.WHITE, chess.KING, chess.E1),
                         (chess.BLACK, chess.ROOK, chess.E8),
                         (chess.BLACK, chess.ROOK, chess.A1),
                         (chess.BLACK, chess.KING, chess.H8))
    superpose(qb, ids[1], (chess.E8, Fraction(1, 2)), (chess.H5, Fraction(1, 2)))
    superpose(qb, ids[2], (chess.A1, Fraction(1, 2)), (chess.A5, Fraction(1, 2)))
    assert check.check_probability(qb, chess.WHITE) == Fraction(3, 4)


def test_superposed_king_only_exposed_ghost_counts():
    # King 3/4 on the attacked square, 1/4 tucked away safe.
    qb, ids = make_board((chess.WHITE, chess.KING, chess.E1),
                         (chess.BLACK, chess.ROOK, chess.E8),
                         (chess.BLACK, chess.KING, chess.H8))
    superpose(qb, ids[0], (chess.E1, Fraction(3, 4)), (chess.A1, Fraction(1, 4)))
    assert check.check_probability(qb, chess.WHITE) == Fraction(3, 4)


def test_cornered_superposed_king_is_certain_check():
    # King split 2/3 on e7, 1/3 on g8 -- and BOTH squares are under a certain
    # capture (a rook down the e-file, a rook along the 8th rank). Wherever the
    # king collapses it dies, so danger must read a full 1, not the old
    # independent-Bernoulli 1 - (1/3)(2/3) = 7/9.
    qb, ids = make_board((chess.WHITE, chess.KING, chess.E1),
                         (chess.BLACK, chess.ROOK, chess.E8),
                         (chess.BLACK, chess.ROOK, chess.A8),
                         (chess.BLACK, chess.KING, chess.H1))
    superpose(qb, ids[0], (chess.E7, Fraction(2, 3)), (chess.G8, Fraction(1, 3)))
    assert check.check_probability(qb, chess.WHITE) == 1


def test_superposed_king_partially_cornered_weights_by_location():
    # King 2/3 e7 (certainly attacked by the e-file rook) + 1/3 g6 (safe -- the
    # rook reaches neither the e-file square below e7 nor g6's rank/file).
    # Danger = 2/3 * 1 + 1/3 * 0 = 2/3.
    qb, ids = make_board((chess.WHITE, chess.KING, chess.E1),
                         (chess.BLACK, chess.ROOK, chess.E8),
                         (chess.BLACK, chess.KING, chess.H1))
    superpose(qb, ids[0], (chess.E7, Fraction(2, 3)), (chess.G6, Fraction(1, 3)))
    assert check.check_probability(qb, chess.WHITE) == Fraction(2, 3)


def test_partial_blocker_thins_the_threat():
    # A half-present friendly pawn on e4 has a 1/2 chance of blocking the rook.
    qb, ids = make_board((chess.WHITE, chess.KING, chess.E1),
                         (chess.BLACK, chess.ROOK, chess.E8),
                         (chess.WHITE, chess.PAWN, chess.E4),
                         (chess.BLACK, chess.KING, chess.H8))
    superpose(qb, ids[2], (chess.E4, Fraction(1, 2)), (chess.D5, Fraction(1, 2)))
    assert check.check_probability(qb, chess.WHITE) == Fraction(1, 2)


def test_move_self_check_discovers_exposure():
    # A knight on e2 blocks the rook; moving it off the file exposes the king.
    qb, ids = make_board((chess.WHITE, chess.KING, chess.E1),
                         (chess.WHITE, chess.KNIGHT, chess.E2),
                         (chess.BLACK, chess.ROOK, chess.E8),
                         (chess.BLACK, chess.KING, chess.H8))
    assert check.check_probability(qb, chess.WHITE) == 0     # knight shields it
    knight_move = next(m for m in rules.ghost_destinations(qb, chess.E2)
                       if m.to_square == chess.C3)
    assert check.move_self_check(qb, knight_move) == 1        # line opens -> full check


def test_move_self_check_king_to_safety_vs_into_fire():
    qb, _ = make_board((chess.WHITE, chess.KING, chess.E1),
                       (chess.BLACK, chess.ROOK, chess.E8),
                       (chess.BLACK, chess.KING, chess.H8))
    assert check.check_probability(qb, chess.WHITE) == 1
    to_safe = next(m for m in rules.ghost_destinations(qb, chess.E1)
                   if m.to_square == chess.D1)
    to_fire = next(m for m in rules.ghost_destinations(qb, chess.E1)
                   if m.to_square == chess.E2)
    assert check.move_self_check(qb, to_safe) == 0            # steps off the file
    assert check.move_self_check(qb, to_fire) == 1            # still on the file
