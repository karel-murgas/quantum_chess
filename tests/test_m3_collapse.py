"""Milestone 3 tests: collapse resolution (contact, path collapse, both modes)."""

import random
from fractions import Fraction

import chess
import pytest

from quantumchess.collapse import _collapse_negative, resolve_move, resolve_split
from quantumchess.config import CollapseMode, GameConfig
from quantumchess.model import Ghost, QuantumBoard
from quantumchess.rules import MoveKind, Split, generate_moves, split_destination_kind


class ScriptedRng:
    """A stand-in RNG returning a prescribed sequence, for deterministic tests."""

    def __init__(self, draws, choice_indices=None):
        self.draws = list(draws)
        self.choice_indices = list(choice_indices) if choice_indices else []

    def random(self):
        assert self.draws, "ScriptedRng ran out of scripted draws"
        return self.draws.pop(0)

    def choices(self, population, weights=None, k=1):
        idx = self.choice_indices.pop(0) if self.choice_indices else 0
        return [population[idx]]


def _rook_vs_ghost_position(target_prob=Fraction(1, 2), other_square=chess.H2,
                            target_color=chess.BLACK, target_ptype=chess.BISHOP):
    """White rook a1, White king e1, Black king e8, and a superposed piece on a2."""
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    qb._add_piece(chess.WHITE, chess.ROOK, chess.A1)
    qb._add_piece(chess.WHITE, chess.KING, chess.E1)
    qb._add_piece(chess.BLACK, chess.KING, chess.E8)
    target = qb._add_piece(target_color, target_ptype, chess.A2)
    qb.ghosts_of(target.id)[0].prob = target_prob
    qb.ghosts.append(Ghost(target.id, other_square, Fraction(1) - target_prob))
    return qb, target


def _rook_a2_move(qb):
    return next(m for m in generate_moves(qb, include_contact=True)
                if chess.square_name(m.from_square) == "a1"
                and chess.square_name(m.to_square) == "a2")


# ------------------------------------------------------------- unit: negative collapse
def _piece_with_three_ghosts():
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    piece = qb._add_piece(chess.BLACK, chess.BISHOP, chess.A3)
    g0 = qb.ghosts_of(piece.id)[0]
    g0.prob = Fraction(1, 2)
    g1 = Ghost(piece.id, chess.C1, Fraction(1, 4))
    g2 = Ghost(piece.id, chess.H8, Fraction(1, 4))
    qb.ghosts.extend([g1, g2])
    return qb, piece, g0


def test_negative_collapse_partial_renormalizes():
    qb, piece, g0 = _piece_with_three_ghosts()
    _collapse_negative(qb, piece.id, g0, GameConfig(collapse_mode=CollapseMode.PARTIAL),
                       random.Random(0))
    remaining = {g.square: g.prob for g in qb.ghosts_of(piece.id)}
    assert remaining == {chess.C1: Fraction(1, 2), chess.H8: Fraction(1, 2)}


def test_negative_collapse_full_picks_one_solid():
    qb, piece, g0 = _piece_with_three_ghosts()
    _collapse_negative(qb, piece.id, g0, GameConfig(collapse_mode=CollapseMode.FULL),
                       random.Random(0))
    remaining = qb.ghosts_of(piece.id)
    assert len(remaining) == 1
    assert remaining[0].prob == Fraction(1)
    assert remaining[0].square in (chess.C1, chess.H8)


# --------------------------------------------------------- resolve_move: single contact
def test_resolve_move_delegates_plain_moves():
    qb = QuantumBoard.standard_setup()
    move = next(m for m in generate_moves(qb) if m.uci() == "e2e4")
    res = resolve_move(qb, move, GameConfig(), random.Random(0))
    assert res.events == []
    assert not res.fizzled
    assert qb.piece_id_at(chess.E4) is not None
    assert qb.turn == chess.BLACK


def test_contact_capture_when_target_present():
    qb, target = _rook_vs_ghost_position()
    move = _rook_a2_move(qb)
    assert move.kind == MoveKind.CONTACT
    rng = ScriptedRng(draws=[0.0, 0.0])   # mover present, target present
    res = resolve_move(qb, move, GameConfig(collapse_mode=CollapseMode.FULL), rng)
    assert not res.fizzled
    assert res.final_square == chess.A2
    assert res.captured_piece_ids == [target.id]
    assert not qb.pieces[target.id].alive
    assert qb.piece_id_at(chess.A2) is not None


def test_contact_no_capture_when_target_absent_partial_mode():
    qb, target = _rook_vs_ghost_position()
    move = _rook_a2_move(qb)
    rng = ScriptedRng(draws=[0.0, 0.99])   # mover present, target NOT present
    res = resolve_move(qb, move, GameConfig(collapse_mode=CollapseMode.PARTIAL), rng)
    assert not res.fizzled
    assert res.final_square == chess.A2      # rook reaches the (really empty) square
    assert res.captured_piece_ids == []
    assert qb.pieces[target.id].alive
    remaining = qb.ghosts_of(target.id)
    assert len(remaining) == 1
    assert remaining[0].square == chess.H2
    assert remaining[0].prob == Fraction(1)   # only ghost left -> renormalizes to solid


def test_mover_fizzle_leaves_target_untouched():
    qb, target = _rook_vs_ghost_position()
    rook_id = qb.piece_id_at(chess.A1)
    qb.ghosts_of(rook_id)[0].prob = Fraction(1, 2)
    qb.ghosts.append(Ghost(rook_id, chess.A8, Fraction(1, 2)))
    move = _rook_a2_move(qb)
    rng = ScriptedRng(draws=[0.99])   # mover NOT present -> fizzle, nothing else drawn
    res = resolve_move(qb, move, GameConfig(collapse_mode=CollapseMode.FULL), rng)
    assert res.fizzled
    assert res.captured_piece_ids == []
    assert qb.pieces[target.id].alive
    assert len(qb.ghosts_of(target.id)) == 2   # untouched
    assert qb.turn == chess.BLACK              # the attempt still consumed the turn


def test_friendly_ghost_blocks_before_contact_square():
    qb, target = _rook_vs_ghost_position(target_color=chess.WHITE, target_ptype=chess.PAWN)
    move = _rook_a2_move(qb)
    rng = ScriptedRng(draws=[0.0, 0.0])   # mover present, friendly ghost present
    res = resolve_move(qb, move, GameConfig(collapse_mode=CollapseMode.FULL), rng)
    assert not res.fizzled
    assert res.final_square == chess.A1     # a2 is the first path square -> stop at source
    assert res.captured_piece_ids == []
    assert qb.pieces[target.id].alive       # own piece, never captured
    remaining = qb.ghosts_of(target.id)
    assert len(remaining) == 1               # measurement confirmed it solid
    assert remaining[0].square == chess.A2
    assert remaining[0].prob == Fraction(1)


def _superposed_rook_vs_solid_bishop():
    """A rook split across a1 (1/2) / h1 (1/2); a certain (solid) bishop on a2."""
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    rook = qb._add_piece(chess.WHITE, chess.ROOK, chess.A1)
    qb.ghosts_of(rook.id)[0].prob = Fraction(1, 2)
    qb.ghosts.append(Ghost(rook.id, chess.H1, Fraction(1, 2)))
    qb._add_piece(chess.WHITE, chess.KING, chess.E1)
    qb._add_piece(chess.BLACK, chess.KING, chess.E8)
    bishop = qb._add_piece(chess.BLACK, chess.BISHOP, chess.A2)
    move = next(m for m in generate_moves(qb, include_contact=True)
                if chess.square_name(m.from_square) == "a1"
                and chess.square_name(m.to_square) == "a2")
    assert move.kind == MoveKind.CAPTURE_SOLID
    return qb, rook, bishop, move


def test_capture_of_solid_piece_still_measures_a_superposed_mover_success():
    qb, rook, bishop, move = _superposed_rook_vs_solid_bishop()
    rng = ScriptedRng(draws=[0.1])   # mover present (0.1 < 1/2)
    res = resolve_move(qb, move, GameConfig(collapse_mode=CollapseMode.FULL), rng)
    assert not res.fizzled
    assert res.captured_piece_ids == [bishop.id]
    assert not qb.pieces[bishop.id].alive
    assert qb.piece_id_at(chess.A2) is not None
    remaining = qb.ghosts_of(rook.id)
    assert len(remaining) == 1 and remaining[0].square == chess.A2 and remaining[0].prob == Fraction(1)


def test_capture_of_solid_piece_fizzles_if_mover_not_really_there():
    qb, rook, bishop, move = _superposed_rook_vs_solid_bishop()
    rng = ScriptedRng(draws=[0.99])   # mover NOT present (0.99 >= 1/2)
    res = resolve_move(qb, move, GameConfig(collapse_mode=CollapseMode.FULL), rng)
    assert res.fizzled
    assert res.captured_piece_ids == []
    assert qb.pieces[bishop.id].alive   # bishop untouched -- capture never happened
    assert qb.piece_id_at(chess.A2) is not None and qb.piece_id_at(chess.A2) == bishop.id
    remaining = qb.ghosts_of(rook.id)
    assert len(remaining) == 1 and remaining[0].square == chess.H1 and remaining[0].prob == Fraction(1)


def test_contact_capture_of_king_wins_game():
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    qb._add_piece(chess.WHITE, chess.ROOK, chess.A1)
    qb._add_piece(chess.WHITE, chess.KING, chess.E1)
    king = qb._add_piece(chess.BLACK, chess.KING, chess.A2)
    qb.ghosts_of(king.id)[0].prob = Fraction(1, 2)
    qb.ghosts.append(Ghost(king.id, chess.H2, Fraction(1, 2)))
    move = _rook_a2_move(qb)
    rng = ScriptedRng(draws=[0.0, 0.0])
    res = resolve_move(qb, move, GameConfig(collapse_mode=CollapseMode.FULL), rng)
    assert res.captured_piece_ids == [king.id]
    assert qb.game_over and qb.winner == chess.WHITE


def test_resolve_move_blocks_after_game_over():
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    qb._add_piece(chess.WHITE, chess.QUEEN, chess.A1)
    qb._add_piece(chess.WHITE, chess.KING, chess.E1)
    qb._add_piece(chess.BLACK, chess.KING, chess.A2)
    move = next(m for m in generate_moves(qb) if m.uci() == "a1a2")
    resolve_move(qb, move, GameConfig(), random.Random(0))
    assert qb.game_over
    with pytest.raises(RuntimeError):
        resolve_move(qb, move, GameConfig(), random.Random(0))


# ------------------------------------------------------- resolve_move: chained path
def test_path_collapse_through_multiple_ghosts():
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    qb._add_piece(chess.WHITE, chess.ROOK, chess.A1)
    qb._add_piece(chess.WHITE, chess.KING, chess.E1)
    qb._add_piece(chess.BLACK, chess.KING, chess.E8)
    near = qb._add_piece(chess.BLACK, chess.PAWN, chess.A3)
    qb.ghosts_of(near.id)[0].prob = Fraction(1, 2)
    qb.ghosts.append(Ghost(near.id, chess.H3, Fraction(1, 2)))
    far = qb._add_piece(chess.BLACK, chess.KNIGHT, chess.A6)
    qb.ghosts_of(far.id)[0].prob = Fraction(1, 2)
    qb.ghosts.append(Ghost(far.id, chess.H6, Fraction(1, 2)))

    move = next(m for m in generate_moves(qb, include_contact=True)
                if chess.square_name(m.from_square) == "a1"
                and chess.square_name(m.to_square) == "a8")
    assert move.kind == MoveKind.CONTACT

    # mover present; near-square ghost NOT present (continue); far-square ghost present (capture, stop)
    rng = ScriptedRng(draws=[0.0, 0.99, 0.0])
    res = resolve_move(qb, move, GameConfig(collapse_mode=CollapseMode.FULL), rng)

    assert res.final_square == chess.A6
    assert res.captured_piece_ids == [far.id]
    assert not qb.pieces[far.id].alive
    assert qb.pieces[near.id].alive
    assert qb.ghosts_of(near.id)[0].square == chess.H3   # only ghost left, renormalized
    assert len(res.events) == 3


# -------------------------------------------------- resolve_move: ghost pawn promotion
def _ghost_pawn_position(pawn_prob=Fraction(1, 2), other_square=chess.H2):
    """A White pawn split across a7 (``pawn_prob``) / ``other_square``, one
    push away from promotion, plus both kings."""
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    qb._add_piece(chess.WHITE, chess.KING, chess.E1)
    qb._add_piece(chess.BLACK, chess.KING, chess.E8)
    pawn = qb._add_piece(chess.WHITE, chess.PAWN, chess.A7)
    qb.ghosts_of(pawn.id)[0].prob = pawn_prob
    qb.ghosts.append(Ghost(pawn.id, other_square, Fraction(1) - pawn_prob))
    return qb, pawn


def _a7a8_queen_move(qb):
    return next(m for m in generate_moves(qb)
                if chess.square_name(m.from_square) == "a7"
                and chess.square_name(m.to_square) == "a8"
                and m.promotion == chess.QUEEN)


def test_solid_pawn_promotion_relocate_is_still_unmeasured():
    """A fully solid pawn (no siblings) has nothing left to measure -- it
    promotes exactly as before, no dice drawn."""
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    qb._add_piece(chess.WHITE, chess.KING, chess.E1)
    qb._add_piece(chess.BLACK, chess.KING, chess.E8)
    qb._add_piece(chess.WHITE, chess.PAWN, chess.A7)
    move = _a7a8_queen_move(qb)
    res = resolve_move(qb, move, GameConfig(), random.Random(0))  # no draws needed
    assert res.events == []
    assert not res.fizzled
    assert qb.piece_id_at(chess.A8) is not None
    piece_id = qb.piece_id_at(chess.A8)
    assert qb.pieces[piece_id].ptype == chess.QUEEN


def test_ghost_pawn_promotion_confirms_and_promotes_when_present():
    qb, pawn = _ghost_pawn_position()
    move = _a7a8_queen_move(qb)
    rng = ScriptedRng(draws=[0.1])   # 0.1 < 1/2 -> really there
    res = resolve_move(qb, move, GameConfig(collapse_mode=CollapseMode.FULL), rng)
    assert not res.fizzled
    assert res.final_square == chess.A8
    assert len(res.events) == 1
    ev = res.events[0]
    assert ev.role == "promotion" and ev.present
    assert qb.pieces[pawn.id].ptype == chess.QUEEN
    remaining = qb.ghosts_of(pawn.id)
    assert len(remaining) == 1 and remaining[0].square == chess.A8
    assert remaining[0].prob == Fraction(1)   # sibling on h2 wiped
    assert qb.turn == chess.BLACK


def test_ghost_pawn_promotion_no_promotion_when_absent_partial_mode():
    qb, pawn = _ghost_pawn_position()
    move = _a7a8_queen_move(qb)
    rng = ScriptedRng(draws=[0.9])   # 0.9 >= 1/2 -> not really there
    res = resolve_move(qb, move, GameConfig(collapse_mode=CollapseMode.PARTIAL), rng)
    assert not res.fizzled           # the move itself still executed -- just no promotion
    assert len(res.events) == 1
    ev = res.events[0]
    assert ev.role == "promotion" and not ev.present
    assert qb.pieces[pawn.id].ptype == chess.PAWN   # never promoted -- its problem
    assert qb.piece_id_at(chess.A8) is None
    remaining = qb.ghosts_of(pawn.id)
    assert len(remaining) == 1 and remaining[0].square == chess.H2
    assert remaining[0].prob == Fraction(1)   # only ghost left -> renormalizes to solid
    assert qb.turn == chess.BLACK


def test_ghost_pawn_promotion_no_promotion_when_absent_full_mode():
    qb, pawn = _ghost_pawn_position()
    move = _a7a8_queen_move(qb)
    rng = ScriptedRng(draws=[0.9])   # not really there; only one sibling left to pick
    res = resolve_move(qb, move, GameConfig(collapse_mode=CollapseMode.FULL), rng)
    assert qb.pieces[pawn.id].ptype == chess.PAWN
    assert qb.piece_id_at(chess.A8) is None
    remaining = qb.ghosts_of(pawn.id)
    assert len(remaining) == 1 and remaining[0].square == chess.H2
    assert remaining[0].prob == Fraction(1)


# --------------------------------------------------------- resolve_split: split onto enemy
def _bishop_split_position():
    """White bishop a1, White king e1, Black king e8, a solid Black pawn on c3
    (reachable via a1-b2-c3, b2 empty so the pawn is a CAPTURE_SOLID target)."""
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    bishop = qb._add_piece(chess.WHITE, chess.BISHOP, chess.A1)
    qb._add_piece(chess.WHITE, chess.KING, chess.E1)
    qb._add_piece(chess.BLACK, chess.KING, chess.E8)
    pawn = qb._add_piece(chess.BLACK, chess.PAWN, chess.C3)
    return qb, bishop, pawn


def _bishop_vs_ghost_position(target_prob=Fraction(1, 2), other_square=chess.H8):
    """Same as above but c3 holds a superposed (not solid) Black bishop instead."""
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    bishop = qb._add_piece(chess.WHITE, chess.BISHOP, chess.A1)
    qb._add_piece(chess.WHITE, chess.KING, chess.E1)
    qb._add_piece(chess.BLACK, chess.KING, chess.E8)
    target = qb._add_piece(chess.BLACK, chess.BISHOP, chess.C3)
    qb.ghosts_of(target.id)[0].prob = target_prob
    qb.ghosts.append(Ghost(target.id, other_square, Fraction(1) - target_prob))
    return qb, bishop, target


def test_split_destination_kind_reports_capture_solid():
    qb, bishop, pawn = _bishop_split_position()
    kind, cap_id = split_destination_kind(qb, chess.A1, chess.C3)
    assert kind == MoveKind.CAPTURE_SOLID
    assert cap_id == pawn.id


def test_split_branch_captures_solid_enemy_when_present():
    qb, bishop, pawn = _bishop_split_position()
    split = Split(bishop.id, chess.A1, chess.B2, chess.C3)
    rng = ScriptedRng(draws=[0.1])   # the c3 branch (prob 1/2) measures present
    res = resolve_split(qb, split, GameConfig(collapse_mode=CollapseMode.FULL), rng)
    assert res.captured_piece_ids == [pawn.id]
    assert not qb.pieces[pawn.id].alive
    remaining = qb.ghosts_of(bishop.id)
    assert len(remaining) == 1                       # confirming c3 wiped the b2 sibling
    assert remaining[0].square == chess.C3
    assert remaining[0].prob == Fraction(1)
    assert qb.turn == chess.BLACK


def test_split_branch_fizzles_against_solid_enemy_when_absent():
    qb, bishop, pawn = _bishop_split_position()
    split = Split(bishop.id, chess.A1, chess.B2, chess.C3)
    rng = ScriptedRng(draws=[0.9])   # the c3 branch measures NOT present
    res = resolve_split(qb, split, GameConfig(collapse_mode=CollapseMode.PARTIAL), rng)
    assert res.captured_piece_ids == []
    assert qb.pieces[pawn.id].alive              # capture never happened
    remaining = qb.ghosts_of(bishop.id)
    assert len(remaining) == 1                    # b2 renormalizes to solid
    assert remaining[0].square == chess.B2
    assert remaining[0].prob == Fraction(1)
    assert qb.turn == chess.BLACK


def test_split_branch_contact_capture_when_target_present():
    qb, bishop, target = _bishop_vs_ghost_position()
    split = Split(bishop.id, chess.A1, chess.B2, chess.C3)
    rng = ScriptedRng(draws=[0.1, 0.1])   # branch present, target present
    res = resolve_split(qb, split, GameConfig(collapse_mode=CollapseMode.FULL), rng)
    assert res.captured_piece_ids == [target.id]
    assert not qb.pieces[target.id].alive
    remaining = qb.ghosts_of(bishop.id)
    assert len(remaining) == 1 and remaining[0].square == chess.C3
    assert remaining[0].prob == Fraction(1)


def test_split_branch_contact_target_absent_branch_still_lands():
    qb, bishop, target = _bishop_vs_ghost_position()
    split = Split(bishop.id, chess.A1, chess.B2, chess.C3)
    rng = ScriptedRng(draws=[0.1, 0.9])   # branch present, target NOT present
    res = resolve_split(qb, split, GameConfig(collapse_mode=CollapseMode.FULL), rng)
    assert res.captured_piece_ids == []
    assert qb.pieces[target.id].alive
    remaining_target = qb.ghosts_of(target.id)
    assert len(remaining_target) == 1 and remaining_target[0].square == chess.H8
    remaining_bishop = qb.ghosts_of(bishop.id)
    assert len(remaining_bishop) == 1 and remaining_bishop[0].square == chess.C3


def test_split_branch_own_measurement_negative_skips_target_entirely():
    qb, bishop, target = _bishop_vs_ghost_position()
    split = Split(bishop.id, chess.A1, chess.B2, chess.C3)
    rng = ScriptedRng(draws=[0.9])   # branch NOT present -- target is never even measured
    res = resolve_split(qb, split, GameConfig(collapse_mode=CollapseMode.PARTIAL), rng)
    assert res.captured_piece_ids == []
    assert len(qb.ghosts_of(target.id)) == 2   # completely untouched
    remaining_bishop = qb.ghosts_of(bishop.id)
    assert len(remaining_bishop) == 1 and remaining_bishop[0].square == chess.B2
    assert remaining_bishop[0].prob == Fraction(1)


def test_split_branch_capture_of_king_wins_game():
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    bishop = qb._add_piece(chess.WHITE, chess.BISHOP, chess.A1)
    qb._add_piece(chess.WHITE, chess.KING, chess.E1)
    king = qb._add_piece(chess.BLACK, chess.KING, chess.C3)
    split = Split(bishop.id, chess.A1, chess.B2, chess.C3)
    rng = ScriptedRng(draws=[0.1])
    res = resolve_split(qb, split, GameConfig(collapse_mode=CollapseMode.FULL), rng)
    assert res.captured_piece_ids == [king.id]
    assert qb.game_over and qb.winner == chess.WHITE


def test_resolve_split_blocks_after_game_over():
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    bishop = qb._add_piece(chess.WHITE, chess.BISHOP, chess.A1)
    qb._add_piece(chess.WHITE, chess.KING, chess.E1)
    qb._add_piece(chess.BLACK, chess.KING, chess.C3)
    split = Split(bishop.id, chess.A1, chess.B2, chess.C3)
    resolve_split(qb, split, GameConfig(), ScriptedRng(draws=[0.1]))
    assert qb.game_over
    with pytest.raises(RuntimeError):
        resolve_split(qb, split, GameConfig(), ScriptedRng(draws=[0.1]))


def test_split_both_branches_contact_first_confirmed_second_never_touched():
    """Splitting into two enemy-occupied squares at once: once one branch is
    confirmed real, the piece is settled there and the other branch's target
    is never measured at all."""
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    queen = qb._add_piece(chess.WHITE, chess.QUEEN, chess.A1)
    qb._add_piece(chess.WHITE, chess.KING, chess.E1)
    qb._add_piece(chess.BLACK, chess.KING, chess.E8)
    pawn_c3 = qb._add_piece(chess.BLACK, chess.PAWN, chess.C3)   # a1-c3 diagonal
    pawn_a3 = qb._add_piece(chess.BLACK, chess.PAWN, chess.A3)   # a1-a3 file
    kind_c3, _ = split_destination_kind(qb, chess.A1, chess.C3)
    kind_a3, _ = split_destination_kind(qb, chess.A1, chess.A3)
    assert kind_c3 == MoveKind.CAPTURE_SOLID and kind_a3 == MoveKind.CAPTURE_SOLID

    split = Split(queen.id, chess.A1, chess.C3, chess.A3)
    rng = ScriptedRng(draws=[0.1])   # only ONE draw scripted: c3 confirmed, a3 must not be measured
    res = resolve_split(qb, split, GameConfig(collapse_mode=CollapseMode.FULL), rng)
    assert res.captured_piece_ids == [pawn_c3.id]
    assert not pawn_c3.alive
    assert pawn_a3.alive                     # never contacted
    remaining = qb.ghosts_of(queen.id)
    assert len(remaining) == 1 and remaining[0].square == chess.C3


def test_split_both_branches_contact_first_fizzles_second_absorbs_probability():
    """Regression: splitting into two enemy-occupied squares must never leave
    the piece with zero ghosts. If the first branch measures negative, the
    second branch's probability is renormalized up (to 1, since it's the only
    ghost left) *before* it's measured -- conservation, not two independent
    coin flips that could both come up empty."""
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    queen = qb._add_piece(chess.WHITE, chess.QUEEN, chess.A1)
    qb._add_piece(chess.WHITE, chess.KING, chess.E1)
    qb._add_piece(chess.BLACK, chess.KING, chess.E8)
    pawn_c3 = qb._add_piece(chess.BLACK, chess.PAWN, chess.C3)   # a1-c3 diagonal
    pawn_a3 = qb._add_piece(chess.BLACK, chess.PAWN, chess.A3)   # a1-a3 file

    split = Split(queen.id, chess.A1, chess.C3, chess.A3)
    # c3 branch measures NOT present; a3 branch's prob is then renormalized to
    # 1, so it's guaranteed present regardless of the second scripted draw.
    rng = ScriptedRng(draws=[0.9, 0.5])
    res = resolve_split(qb, split, GameConfig(collapse_mode=CollapseMode.FULL), rng)

    assert pawn_c3.alive                        # c3 was never really there
    assert res.captured_piece_ids == [pawn_a3.id]
    assert not pawn_a3.alive
    remaining = qb.ghosts_of(queen.id)
    assert len(remaining) == 1                  # never zero ghosts
    assert remaining[0].square == chess.A3
    assert remaining[0].prob == Fraction(1)


# ------------------------------------------------------------------ statistical check
def test_statistical_capture_rate_near_probability():
    """Over many independent 50/50 contacts, capture happens roughly half the time."""
    trials = 3000
    hits = 0
    for i in range(trials):
        qb, target = _rook_vs_ghost_position()
        move = _rook_a2_move(qb)
        res = resolve_move(qb, move, GameConfig(collapse_mode=CollapseMode.FULL),
                           random.Random(i))
        if res.captured_piece_ids:
            hits += 1
    rate = hits / trials
    assert 0.45 < rate < 0.55
