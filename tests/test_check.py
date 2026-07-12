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


def test_two_half_threats_do_not_compound():
    # Two half-present rooks both able to reach the solid king (one down the
    # e-file, one along rank 1). The opponent gets ONE move, so the danger is
    # the *strongest single move*, 1/2 -- NOT the old compounded
    # 1 - (1 - 1/2)(1 - 1/2) = 3/4. Two separate threats never add up.
    qb, ids = make_board((chess.WHITE, chess.KING, chess.E1),
                         (chess.BLACK, chess.ROOK, chess.E8),
                         (chess.BLACK, chess.ROOK, chess.A1),
                         (chess.BLACK, chess.KING, chess.H8))
    superpose(qb, ids[1], (chess.E8, Fraction(1, 2)), (chess.H5, Fraction(1, 2)))
    superpose(qb, ids[2], (chess.A1, Fraction(1, 2)), (chess.A5, Fraction(1, 2)))
    assert check.check_probability(qb, chess.WHITE) == Fraction(1, 2)


def test_superposed_king_only_exposed_ghost_counts():
    # King 3/4 on the attacked square, 1/4 tucked away safe.
    qb, ids = make_board((chess.WHITE, chess.KING, chess.E1),
                         (chess.BLACK, chess.ROOK, chess.E8),
                         (chess.BLACK, chess.KING, chess.H8))
    superpose(qb, ids[0], (chess.E1, Fraction(3, 4)), (chess.A1, Fraction(1, 4)))
    assert check.check_probability(qb, chess.WHITE) == Fraction(3, 4)


def test_one_slide_sweeps_two_king_ghosts_is_certain():
    # King split 1/2 on e5, 1/2 on e2 -- BOTH on the e-file. A single rook slide
    # e8->e1 sweeps the whole file: path collapse measures e5 first (capture if
    # the king is there), else continues and measures e2. Wherever the king is,
    # this one move catches it, so danger is a certain 1.
    qb, ids = make_board((chess.WHITE, chess.KING, chess.E1),
                         (chess.BLACK, chess.ROOK, chess.E8),
                         (chess.BLACK, chess.KING, chess.H1))
    superpose(qb, ids[0], (chess.E5, Fraction(1, 2)), (chess.E2, Fraction(1, 2)))
    assert check.check_probability(qb, chess.WHITE) == 1


def test_two_king_ghosts_needing_two_moves_take_the_max():
    # King 2/3 on e7 (only the e1 rook reaches it, up the file) and 1/3 on a4
    # (only the h4 rook reaches it, along the rank). No single move hits both --
    # e7 and a4 share no line -- so the danger is the strongest single move
    # (2/3), NOT the sum 2/3 + 1/3 and NOT a compounded 1.
    qb, ids = make_board((chess.WHITE, chess.KING, chess.E7),
                         (chess.BLACK, chess.ROOK, chess.E1),
                         (chess.BLACK, chess.ROOK, chess.H4),
                         (chess.BLACK, chess.KING, chess.H8))
    superpose(qb, ids[0], (chess.E7, Fraction(2, 3)), (chess.A4, Fraction(1, 3)))
    assert check.check_probability(qb, chess.WHITE) == Fraction(2, 3)


def test_mass_move_threat_beats_single_move():
    # A rook superposed 1/2 on e8 and 1/2 on e1, a SOLID king on e4 between them.
    # Any single move captures only if that ghost is real (1/2). But with the
    # mass-movement dial on, the categorical roll picks whichever ghost is real
    # and it slides onto e4 with certainty -- e8->e4 or e1->e4 -- so the piece
    # captures for sure: 1/2 * 1 + 1/2 * 1 = 1. Off, it's just 1/2.
    qb, ids = make_board((chess.WHITE, chess.KING, chess.E4),
                         (chess.BLACK, chess.ROOK, chess.E8),
                         (chess.BLACK, chess.KING, chess.H1))
    superpose(qb, ids[1], (chess.E8, Fraction(1, 2)), (chess.E1, Fraction(1, 2)))
    assert check.check_probability(qb, chess.WHITE) == Fraction(1, 2)
    assert check.check_probability(qb, chess.WHITE, mass_movement=True) == 1


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


def test_strongest_threat_names_the_move():
    # The readout labels the actual strongest move: a rook down the e-file.
    qb, _ = make_board((chess.WHITE, chess.KING, chess.E1),
                       (chess.BLACK, chess.ROOK, chess.E8),
                       (chess.BLACK, chess.KING, chess.A8))
    threat = check.strongest_threat(qb, chess.WHITE)
    assert threat is not None
    assert threat.prob == 1
    assert threat.from_square == chess.E8 and threat.to_square == chess.E1
    assert threat.describe() == "R e8->e1"
    # The lone white king can't reach the black king -> nothing threatens it.
    assert check.strongest_threat(qb, chess.BLACK) is None


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
