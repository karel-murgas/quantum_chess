"""Tests for the optional 'mass split' dial -- moving *or splitting* every
ghost of one superposed piece in a single planned turn, settled by one
measurement.

See ``quantumchess.collapse.resolve_mass_split`` and CLAUDE.md. A mass split
whose every leg has a single destination must resolve identically to the
corresponding mass move; the split-specific behaviour is that a ghost may fan
out into two half-probability halves.
"""

from fractions import Fraction

import chess
import pytest

from quantumchess.collapse import resolve_mass_move, resolve_mass_split
from quantumchess.config import CollapseMode, GameConfig
from quantumchess.model import Ghost, QuantumBoard
from quantumchess.rules import MassMove, MassSplit

from tests.test_m3_collapse import ScriptedRng


def _rook_two_ghosts():
    """White rook split a1 (1/2) / h1 (1/2); both kings out of the a/h files."""
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    rook = qb._add_piece(chess.WHITE, chess.ROOK, chess.A1)
    qb.ghosts_of(rook.id)[0].prob = Fraction(1, 2)
    qb.ghosts.append(Ghost(rook.id, chess.H1, Fraction(1, 2)))
    qb._add_piece(chess.WHITE, chess.KING, chess.E4)
    qb._add_piece(chess.BLACK, chess.KING, chess.E8)
    return qb, rook


# ------------------------------ single-destination legs == a mass move
def test_all_single_legs_matches_mass_move():
    qb, rook = _rook_two_ghosts()
    mass = MassSplit(rook.id, ((chess.A1, (chess.A4,)), (chess.H1, (chess.H4,))))
    res = resolve_mass_split(qb, mass, GameConfig(), ScriptedRng(draws=[]))
    assert res.events == []
    assert {g.square: g.prob for g in qb.ghosts_of(rook.id)} == \
        {chess.A4: Fraction(1, 2), chess.H4: Fraction(1, 2)}
    assert qb.turn == chess.BLACK


# ------------------------------------------ a ghost splits into two halves
def test_one_ghost_splits_into_two_halves_no_conflict():
    qb, rook = _rook_two_ghosts()
    # a1 (1/2) splits into a4 + a8; h1 (1/2) just relocates to h4.
    mass = MassSplit(rook.id, ((chess.A1, (chess.A4, chess.A8)),
                               (chess.H1, (chess.H4,))))
    res = resolve_mass_split(qb, mass, GameConfig(), ScriptedRng(draws=[]))
    assert res.events == []
    squares = {g.square: g.prob for g in qb.ghosts_of(rook.id)}
    assert squares == {chess.A4: Fraction(1, 4), chess.A8: Fraction(1, 4),
                       chess.H4: Fraction(1, 2)}
    total = sum(g.prob for g in qb.ghosts_of(rook.id))
    assert total == 1


def test_split_branches_merging_onto_one_square_sum_probability():
    qb, rook = _rook_two_ghosts()
    # a1 splits a4 (1/4) + e1 (1/4); h1 splits h4 (1/4) + e1 (1/4) -- e1 merges
    # (both rooks reach e1 along rank 1).
    mass = MassSplit(rook.id, ((chess.A1, (chess.A4, chess.E1)),
                               (chess.H1, (chess.H4, chess.E1))))
    resolve_mass_split(qb, mass, GameConfig(), ScriptedRng(draws=[]))
    squares = {g.square: g.prob for g in qb.ghosts_of(rook.id)}
    assert squares == {chess.A4: Fraction(1, 4), chess.H4: Fraction(1, 4),
                       chess.E1: Fraction(1, 2)}   # 1/4 + 1/4


def test_split_branch_can_stay_on_source_square():
    qb, rook = _rook_two_ghosts()
    # a1 splits into "stay a1" + move a4; h1 relocates.
    mass = MassSplit(rook.id, ((chess.A1, (chess.A1, chess.A4)),
                               (chess.H1, (chess.H4,))))
    resolve_mass_split(qb, mass, GameConfig(), ScriptedRng(draws=[]))
    squares = {g.square: g.prob for g in qb.ghosts_of(rook.id)}
    assert squares == {chess.A1: Fraction(1, 4), chess.A4: Fraction(1, 4),
                       chess.H4: Fraction(1, 2)}


# ------------------------------------ a split branch conflicts (captures)
def test_split_branch_captures_when_that_half_wins_roll():
    qb, rook = _rook_two_ghosts()
    bishop = qb._add_piece(chess.BLACK, chess.BISHOP, chess.A4)
    # a1 (1/2) splits into a4 (capture, 1/4) + b1 (safe, 1/4); h1 stays.
    mass = MassSplit(rook.id, ((chess.A1, (chess.A4, chess.B1)),
                               (chess.H1, (chess.H1,))))
    # roll 0.1 -> lands in the first quarter [0, 1/4): the a4 capture half wins.
    res = resolve_mass_split(qb, mass, GameConfig(collapse_mode=CollapseMode.FULL),
                             ScriptedRng(draws=[0.1]))
    assert res.final_square == chess.A4
    assert res.chosen_from == chess.A1
    assert res.chosen_to == chess.A4
    assert res.captured_piece_ids == [bishop.id]
    assert not bishop.alive
    remaining = qb.ghosts_of(rook.id)
    assert len(remaining) == 1
    assert remaining[0].square == chess.A4 and remaining[0].prob == Fraction(1)


def test_split_conflict_partial_dodge_keeps_safe_halves():
    qb, rook = _rook_two_ghosts()
    bishop = qb._add_piece(chess.BLACK, chess.BISHOP, chess.A4)
    # a1 splits a4 (capture 1/4) + b1 (safe 1/4); h1 stays (safe 1/2).
    mass = MassSplit(rook.id, ((chess.A1, (chess.A4, chess.B1)),
                               (chess.H1, (chess.H1,))))
    # roll 0.9 -> beyond 1/2: the safe h1 leg wins; PARTIAL keeps the safe halves.
    res = resolve_mass_split(qb, mass, GameConfig(collapse_mode=CollapseMode.PARTIAL),
                             ScriptedRng(draws=[0.9]))
    assert res.final_square is None                # stayed superposed
    assert bishop.alive                            # the a4 half never measured
    squares = {g.square: g.prob for g in qb.ghosts_of(rook.id)}
    # dropped the a4 (1/4) conflict half; renormalize b1 (1/4) + h1 (1/2) -> /(3/4)
    assert squares == {chess.B1: Fraction(1, 3), chess.H1: Fraction(2, 3)}


def test_capturing_king_via_split_branch_wins_game():
    qb, rook = _rook_two_ghosts()
    king = qb._add_piece(chess.BLACK, chess.KING, chess.A4)
    mass = MassSplit(rook.id, ((chess.A1, (chess.A4, chess.B1)),
                               (chess.H1, (chess.H1,))))
    res = resolve_mass_split(qb, mass, GameConfig(), ScriptedRng(draws=[0.1]))  # a4 half wins
    assert res.captured_piece_ids == [king.id]
    assert qb.game_over and qb.winner == chess.WHITE
    assert qb.turn == chess.WHITE


# --------------------------------------------------------------- promotion
def _superposed_pawn():
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    pawn = qb._add_piece(chess.WHITE, chess.PAWN, chess.A7)
    qb.ghosts_of(pawn.id)[0].prob = Fraction(1, 2)
    qb.ghosts.append(Ghost(pawn.id, chess.H2, Fraction(1, 2)))
    qb._add_piece(chess.WHITE, chess.KING, chess.E1)
    qb._add_piece(chess.BLACK, chess.KING, chess.E8)
    return qb, pawn


def test_split_promotion_branch_uses_its_chosen_piece():
    qb, pawn = _superposed_pawn()
    # a7 splits into a8 (promote, 1/4) + a7 stay (1/4); h2 pushes to h3.
    mass = MassSplit(pawn.id, ((chess.A7, (chess.A8, chess.A7)),
                               (chess.H2, (chess.H3,))),
                     promotions=((chess.A7, chess.A8, chess.ROOK),))
    # roll 0.1 -> the a8 promotion half (prob 1/4) wins.
    res = resolve_mass_split(qb, mass, GameConfig(collapse_mode=CollapseMode.FULL),
                             ScriptedRng(draws=[0.1]))
    assert res.final_square == chess.A8
    assert qb.pieces[pawn.id].ptype == chess.ROOK
    remaining = qb.ghosts_of(pawn.id)
    assert len(remaining) == 1 and remaining[0].square == chess.A8


# --------------------------------------------------------------- validation
def test_requires_every_ghost_assigned():
    qb, rook = _rook_two_ghosts()
    mass = MassSplit(rook.id, ((chess.A1, (chess.A4,)),))   # h1 missing
    with pytest.raises(ValueError):
        resolve_mass_split(qb, mass, GameConfig(), ScriptedRng(draws=[]))


def test_rejects_split_leg_with_duplicate_destinations():
    qb, rook = _rook_two_ghosts()
    mass = MassSplit(rook.id, ((chess.A1, (chess.A4, chess.A4)),
                               (chess.H1, (chess.H1,))))
    with pytest.raises(ValueError):
        resolve_mass_split(qb, mass, GameConfig(), ScriptedRng(draws=[]))


def test_rejects_illegal_leg():
    qb, rook = _rook_two_ghosts()
    mass = MassSplit(rook.id, ((chess.A1, (chess.B3,)), (chess.H1, (chess.H4,))))
    with pytest.raises(ValueError):
        resolve_mass_split(qb, mass, GameConfig(), ScriptedRng(draws=[0.1]))


def test_blocks_after_game_over():
    qb, rook = _rook_two_ghosts()
    qb.game_over = True
    mass = MassSplit(rook.id, ((chess.A1, (chess.A4,)), (chess.H1, (chess.H4,))))
    with pytest.raises(RuntimeError):
        resolve_mass_split(qb, mass, GameConfig(), ScriptedRng(draws=[]))


def test_equivalent_to_mass_move_for_single_legs():
    """A mass split of all-single legs and the equivalent mass move produce the
    same board and RNG consumption."""
    qb_a, rook_a = _rook_two_ghosts()
    qb_a._add_piece(chess.BLACK, chess.BISHOP, chess.A4)
    split = MassSplit(rook_a.id, ((chess.A1, (chess.A4,)), (chess.H1, (chess.H4,))))
    res_split = resolve_mass_split(qb_a, split, GameConfig(), ScriptedRng(draws=[0.1]))

    qb_b, rook_b = _rook_two_ghosts()
    qb_b._add_piece(chess.BLACK, chess.BISHOP, chess.A4)
    move = MassMove(rook_b.id, ((chess.A1, chess.A4), (chess.H1, chess.H4)))
    res_move = resolve_mass_move(qb_b, move, GameConfig(), ScriptedRng(draws=[0.1]))

    assert res_split.final_square == res_move.final_square
    assert {g.square: g.prob for g in qb_a.ghosts_of(rook_a.id)} == \
        {g.square: g.prob for g in qb_b.ghosts_of(rook_b.id)}
