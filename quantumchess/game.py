"""Game orchestration.

Milestone 1 provides a seeded random self-play driver (classical rules only,
used by the ASCII demo and the M1 tests). ``GameConfig``/``CollapseMode`` now
live in config.py; re-exported here for convenience.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

import chess

from .config import CollapseMode, GameConfig  # noqa: F401  (re-exported)
from .model import QuantumBoard
from .rules import Move, apply_move, generate_moves


@dataclass
class PlyRecord:
    ply: int
    mover_color: bool
    move: Move
    note: str = ""


def random_selfplay(seed: int = 0, max_plies: int = 1000):
    """Play a random legal game (capture-the-king) and return (board, log)."""
    rng = random.Random(seed)
    qb = QuantumBoard.standard_setup()
    log: list[PlyRecord] = []

    for ply in range(1, max_plies + 1):
        if qb.game_over:
            break
        moves = generate_moves(qb)
        if not moves:
            break  # no legal move for the side to move -> treat as a draw
        move = rng.choice(moves)
        mover_color = qb.turn
        note = ""
        if move.is_capture and move.captured_piece_id is not None:
            victim = qb.pieces[move.captured_piece_id]
            note = f"x{chess.piece_symbol(victim.ptype).upper()}"
            if victim.ptype == chess.KING:
                note += "  <-- KING CAPTURED"
        log.append(PlyRecord(ply, mover_color, move, note))
        apply_move(qb, move)

    return qb, log
