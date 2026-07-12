"""Tests for the optional 'mass movement' dial -- moving every ghost of one
superposed piece in a single planned turn, settled by one measurement.

See ``quantumchess.collapse.resolve_mass_move`` and CLAUDE.md.
"""

from fractions import Fraction

import chess
import pytest

from quantumchess.collapse import resolve_mass_move
from quantumchess.config import CollapseMode, GameConfig
from quantumchess.model import Ghost, QuantumBoard
from quantumchess.rules import MassMove

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


def _rook_three_ghosts():
    """White rook split a1 (1/2) / h1 (1/4) / h8 (1/4)."""
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    rook = qb._add_piece(chess.WHITE, chess.ROOK, chess.A1)
    qb.ghosts_of(rook.id)[0].prob = Fraction(1, 2)
    qb.ghosts.append(Ghost(rook.id, chess.H1, Fraction(1, 4)))
    qb.ghosts.append(Ghost(rook.id, chess.H8, Fraction(1, 4)))
    qb._add_piece(chess.WHITE, chess.KING, chess.E4)
    qb._add_piece(chess.BLACK, chess.KING, chess.E8)
    return qb, rook


# ------------------------------------------------------------- no conflict
def test_no_conflict_relocates_all_ghosts_without_dice():
    qb, rook = _rook_two_ghosts()
    mass = MassMove(rook.id, ((chess.A1, chess.A4), (chess.H1, chess.H4)))
    res = resolve_mass_move(qb, mass, GameConfig(), ScriptedRng(draws=[]))  # no draws
    assert res.events == []
    assert res.final_square is None
    squares = {g.square: g.prob for g in qb.ghosts_of(rook.id)}
    assert squares == {chess.A4: Fraction(1, 2), chess.H4: Fraction(1, 2)}
    assert qb.turn == chess.BLACK


def test_no_conflict_staying_ghost_is_allowed():
    qb, rook = _rook_two_ghosts()
    mass = MassMove(rook.id, ((chess.A1, chess.A1), (chess.H1, chess.H4)))  # a1 stays
    resolve_mass_move(qb, mass, GameConfig(), ScriptedRng(draws=[]))
    squares = {g.square: g.prob for g in qb.ghosts_of(rook.id)}
    assert squares == {chess.A1: Fraction(1, 2), chess.H4: Fraction(1, 2)}


def test_two_ghosts_merging_onto_one_square_sums_probability():
    qb, rook = _rook_three_ghosts()   # a1 1/2, h1 1/4, h8 1/4
    mass = MassMove(rook.id, ((chess.A1, chess.A5),
                              (chess.H1, chess.H4), (chess.H8, chess.H4)))
    resolve_mass_move(qb, mass, GameConfig(), ScriptedRng(draws=[]))
    squares = {g.square: g.prob for g in qb.ghosts_of(rook.id)}
    assert squares == {chess.A5: Fraction(1, 2), chess.H4: Fraction(1, 2)}   # 1/4 + 1/4


# ---------------------------------------- conflict -> roll lands on a safe square
def _rook_with_one_capture_leg():
    """3-ghost rook where the a1 leg captures a solid bishop on a4; the two
    h-file legs are conflict-free relocations."""
    qb, rook = _rook_three_ghosts()
    bishop = qb._add_piece(chess.BLACK, chess.BISHOP, chess.A4)
    mass = MassMove(rook.id, ((chess.A1, chess.A4),      # CAPTURE_SOLID, prob 1/2
                              (chess.H1, chess.H4),      # safe, prob 1/4
                              (chess.H8, chess.H5)))     # safe, prob 1/4
    return qb, rook, bishop, mass


def test_dodge_partial_keeps_safe_ghosts_drops_conflict():
    qb, rook, bishop, mass = _rook_with_one_capture_leg()
    # roll 0.8 -> lands in [3/4, 1): the h8->h5 safe leg wins.
    res = resolve_mass_move(qb, mass, GameConfig(collapse_mode=CollapseMode.PARTIAL),
                            ScriptedRng(draws=[0.8]))
    assert res.final_square is None            # stayed superposed
    assert res.captured_piece_ids == []
    assert bishop.alive                        # never measured
    squares = {g.square: g.prob for g in qb.ghosts_of(rook.id)}
    assert squares == {chess.H4: Fraction(1, 2), chess.H5: Fraction(1, 2)}  # renormalized
    assert qb.turn == chess.BLACK


def test_dodge_full_collapses_whole_piece_to_rolled_square():
    qb, rook, bishop, mass = _rook_with_one_capture_leg()
    res = resolve_mass_move(qb, mass, GameConfig(collapse_mode=CollapseMode.FULL),
                            ScriptedRng(draws=[0.8]))   # h8->h5 wins
    assert res.final_square == chess.H5
    assert res.chosen_from == chess.H8
    assert bishop.alive
    remaining = qb.ghosts_of(rook.id)
    assert len(remaining) == 1
    assert remaining[0].square == chess.H5 and remaining[0].prob == Fraction(1)
    assert qb.turn == chess.BLACK


# ------------------------------------ conflict -> roll lands ON the conflict square
def test_conflict_leg_wins_captures_solid_and_drops_the_rest():
    qb, rook, bishop, mass = _rook_with_one_capture_leg()
    # roll 0.1 -> lands in [0, 1/2): the a1->a4 capture leg wins. No second draw:
    # the categorical roll already confirmed the piece is on that leg.
    res = resolve_mass_move(qb, mass, GameConfig(collapse_mode=CollapseMode.FULL),
                            ScriptedRng(draws=[0.1]))
    assert res.final_square == chess.A4
    assert res.chosen_from == chess.A1
    assert res.captured_piece_ids == [bishop.id]
    assert not bishop.alive
    remaining = qb.ghosts_of(rook.id)
    assert len(remaining) == 1
    assert remaining[0].square == chess.A4 and remaining[0].prob == Fraction(1)
    assert qb.turn == chess.BLACK


def test_conflict_contact_leg_measures_the_enemy_ghost():
    """A conflicting leg that CONTACTs a *superposed* enemy still measures that
    enemy (the 'measure the enemy too' rule): one roll to pick the leg, a second
    to resolve the contacted ghost."""
    qb, rook = _rook_two_ghosts()
    target = qb._add_piece(chess.BLACK, chess.BISHOP, chess.A4)   # superposed enemy
    qb.ghosts_of(target.id)[0].prob = Fraction(1, 2)
    qb.ghosts.append(Ghost(target.id, chess.D4, Fraction(1, 2)))
    mass = MassMove(rook.id, ((chess.A1, chess.A4),      # CONTACT, prob 1/2
                              (chess.H1, chess.H4)))     # safe, prob 1/2
    # roll 0.1 -> a1 leg wins; second draw 0.1 -> the a4 enemy ghost is really there.
    res = resolve_mass_move(qb, mass, GameConfig(collapse_mode=CollapseMode.FULL),
                            ScriptedRng(draws=[0.1, 0.1]))
    assert res.final_square == chess.A4
    assert res.captured_piece_ids == [target.id]
    assert not target.alive
    remaining = qb.ghosts_of(rook.id)
    assert len(remaining) == 1 and remaining[0].square == chess.A4


def test_conflict_contact_leg_enemy_absent_rook_slides_through():
    qb, rook = _rook_two_ghosts()
    target = qb._add_piece(chess.BLACK, chess.BISHOP, chess.A4)
    qb.ghosts_of(target.id)[0].prob = Fraction(1, 2)
    qb.ghosts.append(Ghost(target.id, chess.D4, Fraction(1, 2)))
    mass = MassMove(rook.id, ((chess.A1, chess.A4), (chess.H1, chess.H4)))
    # a1 leg wins; enemy on a4 NOT present -> rook reaches the (now empty) a4.
    res = resolve_mass_move(qb, mass, GameConfig(collapse_mode=CollapseMode.FULL),
                            ScriptedRng(draws=[0.1, 0.9]))
    assert res.final_square == chess.A4
    assert res.captured_piece_ids == []
    assert target.alive
    assert qb.ghosts_of(target.id)[0].square == chess.D4   # renormalized survivor


def test_capturing_king_via_mass_move_wins_game():
    qb, rook = _rook_two_ghosts()
    king = qb._add_piece(chess.BLACK, chess.KING, chess.A4)   # solid enemy king on the file
    mass = MassMove(rook.id, ((chess.A1, chess.A4), (chess.H1, chess.H4)))
    res = resolve_mass_move(qb, mass, GameConfig(), ScriptedRng(draws=[0.1]))  # a1 leg wins
    assert res.captured_piece_ids == [king.id]
    assert qb.game_over and qb.winner == chess.WHITE
    assert qb.turn == chess.WHITE   # turn does NOT flip after a game-ending capture


# --------------------------------------------------------------- promotion
def _superposed_pawn():
    """A White pawn split a7 (1/2) / h2 (1/2), one push from promoting on a8."""
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    pawn = qb._add_piece(chess.WHITE, chess.PAWN, chess.A7)
    qb.ghosts_of(pawn.id)[0].prob = Fraction(1, 2)
    qb.ghosts.append(Ghost(pawn.id, chess.H2, Fraction(1, 2)))
    qb._add_piece(chess.WHITE, chess.KING, chess.E1)
    qb._add_piece(chess.BLACK, chess.KING, chess.E8)
    return qb, pawn


def test_mass_promotion_uses_chosen_piece_when_leg_wins():
    qb, pawn = _superposed_pawn()
    mass = MassMove(pawn.id, ((chess.A7, chess.A8), (chess.H2, chess.H3)),
                    promotions=((chess.A7, chess.ROOK),))
    # a7 leg (prob 1/2) wins the roll -> the pawn really was there, promotes.
    res = resolve_mass_move(qb, mass, GameConfig(collapse_mode=CollapseMode.FULL),
                            ScriptedRng(draws=[0.1]))
    assert res.final_square == chess.A8
    assert qb.pieces[pawn.id].ptype == chess.ROOK        # not a queen
    remaining = qb.ghosts_of(pawn.id)
    assert len(remaining) == 1 and remaining[0].square == chess.A8


def test_mass_promotion_does_not_happen_when_leg_loses():
    qb, pawn = _superposed_pawn()
    mass = MassMove(pawn.id, ((chess.A7, chess.A8), (chess.H2, chess.H3)),
                    promotions=((chess.A7, chess.ROOK),))
    # h2 leg wins -> the pawn wasn't on a8, no promotion ("its problem").
    res = resolve_mass_move(qb, mass, GameConfig(collapse_mode=CollapseMode.FULL),
                            ScriptedRng(draws=[0.9]))
    assert qb.pieces[pawn.id].ptype == chess.PAWN
    remaining = qb.ghosts_of(pawn.id)
    assert len(remaining) == 1 and remaining[0].square == chess.H3


# --------------------------------------------------------------- validation
def test_mass_move_requires_every_ghost_assigned():
    qb, rook = _rook_three_ghosts()
    mass = MassMove(rook.id, ((chess.A1, chess.A4), (chess.H1, chess.H4)))  # h8 missing
    with pytest.raises(ValueError):
        resolve_mass_move(qb, mass, GameConfig(), ScriptedRng(draws=[]))


def test_mass_move_rejects_illegal_leg():
    qb, rook = _rook_two_ghosts()
    mass = MassMove(rook.id, ((chess.A1, chess.B3), (chess.H1, chess.H4)))  # rook can't reach b3
    with pytest.raises(ValueError):
        resolve_mass_move(qb, mass, GameConfig(), ScriptedRng(draws=[0.1]))


def test_blocks_after_game_over():
    qb, rook = _rook_two_ghosts()
    qb.game_over = True
    mass = MassMove(rook.id, ((chess.A1, chess.A4), (chess.H1, chess.H4)))
    with pytest.raises(RuntimeError):
        resolve_mass_move(qb, mass, GameConfig(), ScriptedRng(draws=[]))
