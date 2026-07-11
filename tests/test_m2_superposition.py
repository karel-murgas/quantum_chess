"""Milestone 2 tests: superposition — split, merge, probability bookkeeping."""

from fractions import Fraction

import chess
import pytest

from quantumchess.model import Ghost, QuantumBoard
from quantumchess.rules import (
    MoveKind,
    Split,
    apply_move,
    apply_split,
    generate_moves,
    ghost_destinations,
    legal_split_targets,
)


def _open_bishop_position():
    """Standard start, then 1.e4 e5 so the f1 bishop's diagonal is open."""
    qb = QuantumBoard.standard_setup()
    apply_move(qb, _mv(qb, "e2e4"))
    apply_move(qb, _mv(qb, "e7e5"))
    return qb, qb.piece_id_at(chess.F1)


def _mv(qb, uci):
    frm, to = chess.parse_square(uci[:2]), chess.parse_square(uci[2:4])
    for m in generate_moves(qb, include_contact=True):
        if m.from_square == frm and m.to_square == to and m.promotion is None:
            return m
    raise AssertionError(f"no move {uci}")


def _sum(qb, pid):
    return sum((g.prob for g in qb.ghosts_of(pid)), Fraction(0))


def _no_shared_squares(qb):
    squares = [g.square for g in qb.ghosts]
    assert len(squares) == len(set(squares)), "two ghosts share a square"


def test_split_halves_probability_and_vacates_source():
    qb, pid = _open_bishop_position()
    apply_split(qb, Split(pid, chess.F1, chess.B5, chess.D3))
    gs = qb.ghosts_of(pid)
    assert len(gs) == 2
    assert {g.square for g in gs} == {chess.B5, chess.D3}
    assert all(g.prob == Fraction(1, 2) for g in gs)
    assert _sum(qb, pid) == 1
    assert not qb.is_solid(pid)
    assert qb.ghost_at(chess.F1) is None
    assert qb.turn == chess.BLACK           # split consumes the turn
    _no_shared_squares(qb)


def test_chained_split_produces_correct_fractions():
    qb, pid = _open_bishop_position()
    apply_split(qb, Split(pid, chess.F1, chess.B5, chess.D3))
    apply_split(qb, Split(pid, chess.D3, chess.C4, chess.A6))
    probs = {chess.square_name(g.square): g.prob for g in qb.ghosts_of(pid)}
    assert probs == {"b5": Fraction(1, 2), "c4": Fraction(1, 4), "a6": Fraction(1, 4)}
    assert _sum(qb, pid) == 1
    _no_shared_squares(qb)


def test_move_merge_adds_probabilities():
    qb, pid = _open_bishop_position()
    apply_split(qb, Split(pid, chess.F1, chess.B5, chess.D3))
    apply_split(qb, Split(pid, chess.D3, chess.C4, chess.A6))
    merge = next(m for m in ghost_destinations(qb, chess.C4)
                 if m.to_square == chess.B5)
    assert merge.kind == MoveKind.MERGE
    apply_move(qb, merge)
    probs = {chess.square_name(g.square): g.prob for g in qb.ghosts_of(pid)}
    assert probs == {"b5": Fraction(3, 4), "a6": Fraction(1, 4)}
    assert _sum(qb, pid) == 1
    _no_shared_squares(qb)


def test_split_onto_own_ghost_merges():
    qb, pid = _open_bishop_position()
    apply_split(qb, Split(pid, chess.F1, chess.B5, chess.D3))
    # Split d3 toward b5 (own ghost -> merge) and c4 (empty).
    apply_split(qb, Split(pid, chess.D3, chess.B5, chess.C4))
    probs = {chess.square_name(g.square): g.prob for g in qb.ghosts_of(pid)}
    assert probs == {"b5": Fraction(3, 4), "c4": Fraction(1, 4)}
    assert _sum(qb, pid) == 1


def test_split_requires_distinct_legal_targets():
    qb, pid = _open_bishop_position()
    with pytest.raises(ValueError):
        apply_split(qb, Split(pid, chess.F1, chess.B5, chess.B5))   # same square
    with pytest.raises(ValueError):
        apply_split(qb, Split(pid, chess.F1, chess.B5, chess.H6))   # h6 not reachable


def test_split_can_leave_a_branch_at_the_source_square():
    qb, pid = _open_bishop_position()
    assert chess.F1 in legal_split_targets(qb, chess.F1)
    apply_split(qb, Split(pid, chess.F1, chess.F1, chess.D3))
    probs = {chess.square_name(g.square): g.prob for g in qb.ghosts_of(pid)}
    assert probs == {"f1": Fraction(1, 2), "d3": Fraction(1, 2)}
    assert _sum(qb, pid) == 1
    assert qb.turn == chess.BLACK           # split consumes the turn
    _no_shared_squares(qb)


def test_legal_split_targets_includes_captures_but_apply_split_rejects_them():
    qb, pid = _open_bishop_position()
    # Drop a black pawn on c4 so f1-bishop could *capture* there.
    qb._add_piece(chess.BLACK, chess.PAWN, chess.C4)
    targets = set(legal_split_targets(qb, chess.F1))
    assert chess.C4 in targets                     # legal -- collapse.resolve_split handles it
    assert {chess.E2, chess.D3} <= targets         # reachable before the blocker
    assert chess.B5 not in targets                 # the c4 pawn still blocks anything beyond

    # apply_split itself is the measurement-free fast path only -- it must
    # reject a destination that needs a collapse.resolve_split measurement.
    with pytest.raises(ValueError):
        apply_split(qb, Split(pid, chess.F1, chess.E2, chess.C4))


def _black_ghost_position():
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    qb._add_piece(chess.WHITE, chess.ROOK, chess.A1)
    qb._add_piece(chess.WHITE, chess.KING, chess.E1)
    qb._add_piece(chess.BLACK, chess.KING, chess.E8)
    bb = qb._add_piece(chess.BLACK, chess.BISHOP, chess.A4)  # will be superposed
    g = qb.ghosts_of(bb.id)[0]
    g.prob = Fraction(1, 2)
    qb.ghosts.append(Ghost(bb.id, chess.H4, Fraction(1, 2)))
    return qb, bb


def test_contact_with_enemy_ghost_is_deferred():
    qb, bb = _black_ghost_position()
    # Default generation hides CONTACT moves...
    assert all(m.kind != MoveKind.CONTACT for m in generate_moves(qb))
    assert not any(m.to_square == chess.A4 for m in generate_moves(qb))
    # ...but they exist when asked for, and applying one is a Milestone-3 seam.
    contact = next(m for m in generate_moves(qb, include_contact=True)
                   if m.to_square == chess.A4)
    assert contact.kind == MoveKind.CONTACT
    with pytest.raises(NotImplementedError):
        apply_move(qb, contact)


def test_slider_through_enemy_ghost_is_contact():
    qb, bb = _black_ghost_position()
    # Rook a1 sliding to a8 passes the enemy ghost on a4 -> the whole move is CONTACT.
    thru = next(m for m in generate_moves(qb, include_contact=True)
                if m.from_square == chess.A1 and m.to_square == chess.A8)
    assert thru.kind == MoveKind.CONTACT


def test_opening_move_count_still_20():
    # Superposition machinery must not disturb the classical baseline.
    qb = QuantumBoard.standard_setup()
    assert len(generate_moves(qb)) == 20


def test_pawn_cannot_diagonally_capture_a_friendly_ghost():
    """Regression: a pawn's diagonal move is a *capture*, only legal against an
    enemy. A friendly ghost of another piece sitting on the diagonal square used
    to be offered as a CONTACT move (a7xb6 onto our own forked pawn); it must not
    be a legal target at all -- same as a friendly *solid* diagonal blocker."""
    qb = QuantumBoard()
    qb.turn = chess.BLACK
    a7_pawn = qb._add_piece(chess.BLACK, chess.PAWN, chess.A7)
    b7_pawn = qb._add_piece(chess.BLACK, chess.PAWN, chess.B7)
    # Fork the b7 pawn into b6/b5 so a friendly ghost now sits on a7's diagonal.
    apply_split(qb, Split(b7_pawn.id, chess.B7, chess.B6, chess.B5))
    qb.turn = chess.BLACK

    dests = [m.to_square for m in ghost_destinations(qb, chess.A7)]
    assert chess.B6 not in dests
    # The straight-ahead push is unaffected.
    assert chess.A6 in dests


def test_pawn_can_still_diagonally_contact_an_enemy_ghost():
    """The color check must not disable legitimate diagonal captures: an *enemy*
    ghost on the diagonal is still offered as a CONTACT."""
    qb = QuantumBoard()
    qb.turn = chess.BLACK
    qb._add_piece(chess.BLACK, chess.PAWN, chess.A7)
    enemy = qb._add_piece(chess.WHITE, chess.KNIGHT, chess.D4)
    # Split the enemy knight so a ghost lands on b6 (a7's diagonal capture square).
    apply_split(qb, Split(enemy.id, chess.D4, chess.B5, chess.C6))
    qb.ghosts_of(enemy.id)[0].square = chess.B6   # place a ghost squarely on b6
    qb.turn = chess.BLACK

    diag = next(m for m in ghost_destinations(qb, chess.A7) if m.to_square == chess.B6)
    assert diag.kind == MoveKind.CONTACT
