"""Castling tests.

Castling only ever applies to a king/rook that has *never* moved or split
(tracked via ``Piece.has_moved``), which by construction means it's still
solid on its home square. The king's 2-square hop is generated like any other
slide and, when its path holds a foreign ghost, resolved with the exact same
path-collapse machinery used elsewhere (``collapse._walk_contact``) -- the
rook only follows if the king's walk reaches the full destination
uncollapsed. See CLAUDE.md for the full design writeup.
"""

import random
from fractions import Fraction

import chess
import pytest

from quantumchess.collapse import resolve_move, resolve_split
from quantumchess.config import CollapseMode, GameConfig
from quantumchess.model import Ghost, QuantumBoard
from quantumchess.rules import (
    MoveKind, Split, apply_move, apply_split, generate_moves, ghost_destinations,
    legal_split_targets, split_destination_castle_rook, split_destination_kind,
)


class _Scripted:
    """A stand-in RNG returning a prescribed sequence, for deterministic tests."""

    def __init__(self, draws):
        self.draws = list(draws)

    def random(self):
        return self.draws.pop(0)

    def choices(self, population, weights=None, k=1):
        return [population[0]]


def _back_rank_setup(color=chess.WHITE):
    """A lone king (e-file) + both rooks (a/h-file) on their home rank, plus
    an enemy king far away so the game can't already be "over"."""
    qb = QuantumBoard()
    qb.turn = color
    rank = 0 if color == chess.WHITE else 7
    other_rank = 7 if color == chess.WHITE else 0
    king = qb._add_piece(color, chess.KING, chess.square(4, rank))
    rook_a = qb._add_piece(color, chess.ROOK, chess.square(0, rank))
    rook_h = qb._add_piece(color, chess.ROOK, chess.square(7, rank))
    qb._add_piece(not color, chess.KING, chess.square(4, other_rank))
    return qb, king, rook_a, rook_h


def _castle_move(qb, side="K", include_contact=True):
    king = next(p for p in qb.living_pieces(qb.turn) if p.ptype == chess.KING)
    for m in ghost_destinations(qb, qb.solid_square(king.id)):
        if m.castle_rook is None:
            continue
        rook_from = m.castle_rook[1]
        file = chess.square_file(rook_from)
        if (side == "K") == (file == 7):
            return m
    return None


# ------------------------------------------------------------- generation
def test_kingside_castle_offered_with_clear_path():
    qb, king, rook_a, rook_h = _back_rank_setup()
    move = _castle_move(qb, "K")
    assert move is not None
    assert move.kind == MoveKind.RELOCATE
    assert chess.square_name(move.to_square) == "g1"
    assert move.castle_rook == (rook_h.id, chess.H1, chess.F1)


def test_queenside_castle_offered_with_clear_path():
    qb, king, rook_a, rook_h = _back_rank_setup()
    move = _castle_move(qb, "Q")
    assert move is not None
    assert chess.square_name(move.to_square) == "c1"
    assert move.castle_rook == (rook_a.id, chess.A1, chess.D1)


def test_not_offered_once_king_has_moved():
    qb, king, rook_a, rook_h = _back_rank_setup()
    king.has_moved = True
    assert _castle_move(qb, "K") is None
    assert _castle_move(qb, "Q") is None


def test_not_offered_once_that_rook_has_moved():
    qb, king, rook_a, rook_h = _back_rank_setup()
    rook_h.has_moved = True
    assert _castle_move(qb, "K") is None
    assert _castle_move(qb, "Q") is not None  # queenside untouched


def test_blocked_by_own_solid_piece_between():
    qb, king, rook_a, rook_h = _back_rank_setup()
    qb._add_piece(chess.WHITE, chess.BISHOP, chess.F1)
    assert _castle_move(qb, "K") is None


def test_queenside_blocked_by_rook_only_square():
    qb, king, rook_a, rook_h = _back_rank_setup()
    # b1 is only on the rook's path, never the king's -- must be empty too.
    qb._add_piece(chess.WHITE, chess.KNIGHT, chess.B1)
    assert _castle_move(qb, "Q") is None


def test_opening_position_offers_no_castle():
    qb = QuantumBoard.standard_setup()
    moves = generate_moves(qb)
    assert not any(m.castle_rook is not None for m in moves)


def test_castle_included_in_split_targets():
    qb, king, rook_a, rook_h = _back_rank_setup()
    king_sq = qb.solid_square(king.id)
    targets = legal_split_targets(qb, king_sq)
    assert chess.G1 in targets and chess.C1 in targets
    assert split_destination_kind(qb, king_sq, chess.G1) == (MoveKind.RELOCATE, None)
    assert split_destination_castle_rook(qb, king_sq, chess.G1) == (rook_h.id, chess.H1, chess.F1)
    assert split_destination_castle_rook(qb, king_sq, chess.D1) is None  # ordinary square


# ------------------------------------------------------- split-based castling
# A king split toward a castle square drags the rook along too -- but the
# rook is never superposed by it, it always makes one plain, deterministic
# relocation (see rules.split_destination_castle_rook / apply_split /
# collapse.resolve_split).
def test_apply_split_toward_clear_castle_moves_rook_unconditionally():
    qb, king, rook_a, rook_h = _back_rank_setup()
    king_sq = qb.solid_square(king.id)
    apply_split(qb, Split(king.id, king_sq, chess.G1, chess.D1))

    king_ghosts = {g.square: g.prob for g in qb.ghosts_of(king.id)}
    assert king_ghosts == {chess.G1: Fraction(1, 2), chess.D1: Fraction(1, 2)}
    assert qb.solid_square(rook_h.id) == chess.F1
    assert rook_h.has_moved
    assert not rook_a.has_moved  # the other rook is untouched


def test_split_branch_captures_solid_enemy_on_castle_square_moves_rook():
    qb, king, rook_a, rook_h = _back_rank_setup()
    king_sq = qb.solid_square(king.id)
    enemy = qb._add_piece(chess.BLACK, chess.KNIGHT, chess.G1)
    split = Split(king.id, king_sq, chess.G1, chess.D1)
    kind, cap_id = split_destination_kind(qb, king_sq, chess.G1)
    assert kind == MoveKind.CAPTURE_SOLID and cap_id == enemy.id

    rng = _Scripted([0.0])   # the g1 branch measures present
    result = resolve_split(qb, split, GameConfig(collapse_mode=CollapseMode.FULL), rng)

    assert result.captured_piece_ids == [enemy.id]
    assert not enemy.alive
    assert qb.solid_square(king.id) == chess.G1
    assert qb.solid_square(rook_h.id) == chess.F1
    assert rook_h.has_moved


def test_split_branch_fizzles_against_solid_enemy_on_castle_square_no_rook_move():
    qb, king, rook_a, rook_h = _back_rank_setup()
    king_sq = qb.solid_square(king.id)
    enemy = qb._add_piece(chess.BLACK, chess.KNIGHT, chess.G1)
    split = Split(king.id, king_sq, chess.G1, chess.D1)

    rng = _Scripted([0.9])   # the g1 branch measures NOT present
    result = resolve_split(qb, split, GameConfig(collapse_mode=CollapseMode.PARTIAL), rng)

    assert result.captured_piece_ids == []
    assert enemy.alive
    assert qb.solid_square(king.id) == chess.D1   # only the other branch survives
    assert qb.solid_square(rook_h.id) == chess.H1  # rook never moved
    assert not rook_h.has_moved


def test_split_branch_negative_path_collapse_completes_castle():
    """A foreign ghost sits on f1; the g1 branch measures present, then the
    path ghost measures 'not there' -> vanishes, and the branch's walk
    continues to g1, dragging the rook along."""
    qb, king, rook_a, rook_h = _back_rank_setup()
    king_sq = qb.solid_square(king.id)
    ghost_piece = qb._add_piece(chess.BLACK, chess.BISHOP, chess.F1)
    qb.ghosts_of(ghost_piece.id)[0].prob = Fraction(1, 2)
    qb.ghosts.append(Ghost(ghost_piece.id, chess.H6, Fraction(1, 2)))

    split = Split(king.id, king_sq, chess.G1, chess.D1)
    kind, _ = split_destination_kind(qb, king_sq, chess.G1)
    assert kind == MoveKind.CONTACT

    rng = _Scripted([0.0, 0.9])   # g1 branch present; f1 ghost measures NOT there
    resolve_split(qb, split, GameConfig(collapse_mode=CollapseMode.PARTIAL), rng)

    assert qb.solid_square(king.id) == chess.G1
    assert qb.solid_square(rook_h.id) == chess.F1
    assert rook_h.has_moved


def test_split_branch_positive_path_collapse_stops_short_no_rook_move():
    """Force the (superposed) f1 ghost to measure 'really there': the g1
    branch's walk stops before g1, so the rook never moves."""
    qb, king, rook_a, rook_h = _back_rank_setup()
    king_sq = qb.solid_square(king.id)
    ghost_piece = qb._add_piece(chess.BLACK, chess.BISHOP, chess.F1)
    qb.ghosts_of(ghost_piece.id)[0].prob = Fraction(1, 2)
    qb.ghosts.append(Ghost(ghost_piece.id, chess.H6, Fraction(1, 2)))

    split = Split(king.id, king_sq, chess.G1, chess.D1)
    rng = _Scripted([0.0, 0.0])   # g1 branch present; f1 ghost measures really there

    result = resolve_split(qb, split, GameConfig(collapse_mode=CollapseMode.FULL), rng)

    assert result.captured_piece_ids == [ghost_piece.id]
    assert not ghost_piece.alive
    assert qb.solid_square(king.id) == chess.F1   # captured the bishop, stopped short
    assert qb.solid_square(rook_h.id) == chess.H1  # rook never moved
    assert not rook_h.has_moved


# --------------------------------------------------------------- execution
def test_apply_move_castles_kingside_and_marks_moved():
    qb, king, rook_a, rook_h = _back_rank_setup()
    move = _castle_move(qb, "K")
    apply_move(qb, move)
    assert qb.solid_square(king.id) == chess.G1
    assert qb.solid_square(rook_h.id) == chess.F1
    assert king.has_moved and rook_h.has_moved
    assert not rook_a.has_moved  # the other rook is untouched


def test_apply_move_castles_queenside():
    qb, king, rook_a, rook_h = _back_rank_setup()
    move = _castle_move(qb, "Q")
    apply_move(qb, move)
    assert qb.solid_square(king.id) == chess.C1
    assert qb.solid_square(rook_a.id) == chess.D1


def test_castle_can_capture_a_solid_enemy_at_destination():
    qb, king, rook_a, rook_h = _back_rank_setup()
    enemy = qb._add_piece(chess.BLACK, chess.KNIGHT, chess.G1)
    move = _castle_move(qb, "K")
    assert move.kind == MoveKind.CAPTURE_SOLID
    apply_move(qb, move)
    assert qb.solid_square(king.id) == chess.G1
    assert qb.solid_square(rook_h.id) == chess.F1
    assert not enemy.alive


# -------------------------------------------------------- quantum interaction
def test_negative_collapse_on_path_lets_castle_complete():
    """A foreign ghost sits on f1; it measures 'not there' -> vanishes, and the
    king's walk continues on to g1, dragging the rook along."""
    qb, king, rook_a, rook_h = _back_rank_setup()
    ghost_piece = qb._add_piece(chess.BLACK, chess.BISHOP, chess.F1)
    qb.ghosts_of(ghost_piece.id)[0].prob = Fraction(1, 2)
    qb.ghosts.append(Ghost(ghost_piece.id, chess.H6, Fraction(1, 2)))

    move = _castle_move(qb, "K", include_contact=True)
    assert move.kind == MoveKind.CONTACT

    result = resolve_move(qb, move, GameConfig(collapse_mode=CollapseMode.PARTIAL),
                          random.Random(0))
    # With Random(0) the first draw is well below 0.5 -> "not there".
    assert result.final_square == chess.G1
    assert qb.solid_square(king.id) == chess.G1
    assert qb.solid_square(rook_h.id) == chess.F1
    assert rook_h.has_moved


def test_positive_collapse_on_path_stops_king_short_no_rook_move():
    """Force the (superposed) f1 ghost to measure 'really there': the king's
    walk stops before g1, so the rook never moves."""
    class AlwaysLow:
        def random(self):
            return 0.0

    qb, king, rook_a, rook_h = _back_rank_setup()
    ghost_piece = qb._add_piece(chess.BLACK, chess.BISHOP, chess.F1)
    qb.ghosts_of(ghost_piece.id)[0].prob = Fraction(1, 2)
    qb.ghosts.append(Ghost(ghost_piece.id, chess.H6, Fraction(1, 2)))

    move = _castle_move(qb, "K", include_contact=True)
    assert move.kind == MoveKind.CONTACT

    result = resolve_move(qb, move, GameConfig(collapse_mode=CollapseMode.FULL), AlwaysLow())
    assert result.final_square == chess.F1  # captured the bishop, stopped short
    assert qb.solid_square(king.id) == chess.F1
    assert qb.solid_square(rook_h.id) == chess.H1  # rook never moved
    assert not rook_h.has_moved
    assert not ghost_piece.alive
