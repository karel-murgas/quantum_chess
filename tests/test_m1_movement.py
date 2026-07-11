"""Milestone 1 tests: classical movement + capture-the-king, over our own model.

The engine is headless, so these are plain pytest with no UI involved.
"""

from fractions import Fraction

import chess
import pytest

from quantumchess.game import random_selfplay
from quantumchess.model import QuantumBoard
from quantumchess.rules import Move, apply_move, generate_moves


def _find_move(moves, uci, promotion=None):
    for m in moves:
        if (chess.square_name(m.from_square) + chess.square_name(m.to_square) == uci
                and m.promotion == promotion):
            return m
    raise AssertionError(f"move {uci} (promo={promotion}) not generated")


def test_standard_setup_counts():
    qb = QuantumBoard.standard_setup()
    assert len(qb.pieces) == 32
    assert len(qb.ghosts) == 32
    assert all(qb.is_solid(p.id) for p in qb.pieces.values())
    assert qb.turn == chess.WHITE


def test_opening_move_count_is_20():
    # 16 pawn moves + 4 knight moves, no castling relevant at the start.
    qb = QuantumBoard.standard_setup()
    assert len(generate_moves(qb)) == 20


def test_probabilities_sum_to_one_per_piece():
    qb = QuantumBoard.standard_setup()
    for piece in qb.living_pieces():
        total = sum((g.prob for g in qb.ghosts_of(piece.id)), Fraction(0))
        assert total == 1


def test_no_move_lands_on_own_piece():
    qb = QuantumBoard.standard_setup()
    for m in generate_moves(qb):
        occ = qb.piece_id_at(m.to_square)
        if occ is not None:
            assert qb.pieces[occ].color != qb.turn


def test_double_push_sets_en_passant_and_capture_works():
    qb = QuantumBoard.standard_setup()
    apply_move(qb, _find_move(generate_moves(qb), "e2e4"))   # White double push
    assert qb.ep_square == chess.E3
    apply_move(qb, _find_move(generate_moves(qb), "d7d5"))   # Black double push
    assert qb.ep_square == chess.D6
    apply_move(qb, _find_move(generate_moves(qb), "e4e5"))   # White pawn advances
    apply_move(qb, _find_move(generate_moves(qb), "f7f5"))   # Black double push -> ep at f6
    assert qb.ep_square == chess.F6
    ep = _find_move(generate_moves(qb), "e5f6")              # en passant capture
    assert ep.is_en_passant and ep.is_capture
    black_pawns_before = len([p for p in qb.living_pieces(chess.BLACK)
                              if p.ptype == chess.PAWN])
    apply_move(qb, ep)
    black_pawns_after = len([p for p in qb.living_pieces(chess.BLACK)
                             if p.ptype == chess.PAWN])
    assert black_pawns_after == black_pawns_before - 1  # f5 pawn removed
    assert qb.piece_id_at(chess.F6) is not None          # capturer sits on f6
    assert qb.piece_id_at(chess.F5) is None


def test_promotion_generates_all_four_pieces():
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    # Lone white pawn on a7, black king out of the way; white king present so it's a legal-ish board.
    qb._add_piece(chess.WHITE, chess.PAWN, chess.A7)
    qb._add_piece(chess.WHITE, chess.KING, chess.E1)
    qb._add_piece(chess.BLACK, chess.KING, chess.H8)
    promos = {m.promotion for m in generate_moves(qb)
              if chess.square_name(m.from_square) == "a7"}
    assert promos == {chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT}


def test_capturing_king_ends_game():
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    qb._add_piece(chess.WHITE, chess.ROOK, chess.A1)
    qb._add_piece(chess.WHITE, chess.KING, chess.E1)
    bk = qb._add_piece(chess.BLACK, chess.KING, chess.A8)
    rook_take_king = _find_move(generate_moves(qb), "a1a8")
    assert rook_take_king.is_capture and rook_take_king.captured_piece_id == bk.id
    apply_move(qb, rook_take_king)
    assert qb.game_over
    assert qb.winner == chess.WHITE
    assert not qb.pieces[bk.id].alive


def test_game_over_blocks_further_moves():
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    qb._add_piece(chess.WHITE, chess.QUEEN, chess.A1)
    qb._add_piece(chess.WHITE, chess.KING, chess.E1)
    qb._add_piece(chess.BLACK, chess.KING, chess.A2)
    apply_move(qb, _find_move(generate_moves(qb), "a1a2"))
    assert qb.game_over
    with pytest.raises(RuntimeError):
        apply_move(qb, Move(0, chess.E1, chess.E2))


@pytest.mark.parametrize("seed", range(12))
def test_random_selfplay_is_legal_and_terminates(seed):
    """Fuzz: every ply is a generated move; per-piece probabilities stay at 1."""
    qb, log = random_selfplay(seed=seed, max_plies=1000)
    # Someone should have captured a king within the ply budget under random play.
    assert qb.game_over and qb.winner is not None
    for piece in qb.living_pieces():
        total = sum((g.prob for g in qb.ghosts_of(piece.id)), Fraction(0))
        assert total == 1
    # Exactly one king remains alive.
    kings = [p for p in qb.living_pieces() if p.ptype == chess.KING]
    assert len(kings) == 1
