"""Milestone 3 demo: collapse resolution -- the quantum core.

Run:  python demo_m3.py [seed]

Hand-built position: a White rook on a1 slides to a8. Along that file sit a
split black bishop (a3 = 1/2, off-file = 1/2), a split black knight (a5... here
a6 = 1/2, off-file = 1/2), and a split *White* (friendly) pawn (a5 = 1/2,
off-file = 1/2). Sliding through them can capture an enemy ghost, sail past one
that "wasn't really there", or get stopped early by a friendly ghost that turns
out to be real -- all rolled live with a seeded RNG, several possibly resolving
in the very same move.
"""

import random
import sys
from fractions import Fraction

import chess

from quantumchess.collapse import resolve_move
from quantumchess.config import CollapseMode, GameConfig
from quantumchess.model import Ghost, QuantumBoard
from quantumchess.rules import generate_moves
from quantumchess.textview import render


def build_position():
    qb = QuantumBoard()
    qb.turn = chess.WHITE
    qb._add_piece(chess.WHITE, chess.ROOK, chess.A1)
    qb._add_piece(chess.WHITE, chess.KING, chess.E1)
    qb._add_piece(chess.BLACK, chess.KING, chess.E8)

    bishop = qb._add_piece(chess.BLACK, chess.BISHOP, chess.A3)
    qb.ghosts_of(bishop.id)[0].prob = Fraction(1, 2)
    qb.ghosts.append(Ghost(bishop.id, chess.C1, Fraction(1, 2)))

    knight = qb._add_piece(chess.BLACK, chess.KNIGHT, chess.A5)
    qb.ghosts_of(knight.id)[0].prob = Fraction(1, 2)
    qb.ghosts.append(Ghost(knight.id, chess.F5, Fraction(1, 2)))

    pawn = qb._add_piece(chess.WHITE, chess.PAWN, chess.A6)
    qb.ghosts_of(pawn.id)[0].prob = Fraction(1, 2)
    qb.ghosts.append(Ghost(pawn.id, chess.H2, Fraction(1, 2)))
    return qb


def describe(ev):
    verb = "IS" if ev.present else "is NOT"
    return (f"    measure {ev.role:<11} piece#{ev.piece_id} @ "
            f"{chess.square_name(ev.square)} (p={ev.prob_before}) -> {verb} there")


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    config = GameConfig(collapse_mode=CollapseMode.FULL, seed=seed)
    rng = random.Random(seed)

    qb = build_position()
    print(render(qb))
    print(f"\nRook a1-a8, through bishop(a3), knight(a5), own pawn(a6). "
          f"seed={seed}, mode={config.collapse_mode.value}\n")

    rook_move = next(
        m for m in generate_moves(qb, include_contact=True)
        if chess.square_name(m.from_square) == "a1" and chess.square_name(m.to_square) == "a8"
    )
    result = resolve_move(qb, rook_move, config, rng)

    for ev in result.events:
        print(describe(ev))
    print()
    if result.fizzled:
        print("Rook was not really on a1 after all -- the move fizzles.")
    else:
        landed = "reached a8" if result.final_square == chess.A8 else "stopped early"
        print(f"Rook ends up on {chess.square_name(result.final_square)} ({landed}).")
        if result.captured_piece_ids:
            print(f"Captured piece id(s): {result.captured_piece_ids}")

    print("\nFinal position:")
    print(render(qb))


if __name__ == "__main__":
    main()
