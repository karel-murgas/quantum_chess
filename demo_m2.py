"""Milestone 2 demo: superposition (split / merge), no collapse yet.

Run:  python demo_m2.py

Walks a short scripted game where a white bishop splits, one ghost splits again,
and then two ghosts merge into a 3/4-probability ghost — printing the ghost-aware
ASCII board and the exact-fraction legend after each action.
"""

import chess

from quantumchess.model import QuantumBoard
from quantumchess.rules import Split, apply_move, apply_split, generate_moves
from quantumchess.textview import render


def mv(qb, uci):
    frm, to = chess.parse_square(uci[:2]), chess.parse_square(uci[2:4])
    for m in generate_moves(qb, include_contact=True):
        if m.from_square == frm and m.to_square == to and m.promotion is None:
            return m
    raise AssertionError(f"no move {uci} available")


def show(title, qb):
    print(f"\n=== {title} ===")
    print(render(qb))


def main():
    qb = QuantumBoard.standard_setup()
    show("Start", qb)

    apply_move(qb, mv(qb, "e2e4"));  # open the f1-bishop's diagonal
    apply_move(qb, mv(qb, "e7e5"))
    show("After 1. e4 e5", qb)

    apply_split(qb, Split(qb.piece_id_at(chess.F1), chess.F1, chess.B5, chess.D3))
    show("White SPLITS the f1 bishop -> b5 (1/2) and d3 (1/2)", qb)

    apply_move(qb, mv(qb, "b8c6"))
    apply_split(qb, Split(qb.piece_id_at(chess.D3), chess.D3, chess.C4, chess.A6))
    show("White SPLITS the d3 ghost -> c4 (1/4) and a6 (1/4)", qb)

    apply_move(qb, mv(qb, "g8f6"))
    apply_move(qb, mv(qb, "c4b5"))   # ghost c4 merges into ghost b5
    show("White MERGES c4 into b5 -> b5 becomes 3/4, a6 stays 1/4", qb)

    print("\nThe bishop is now spread across b5 (3/4) and a6 (1/4); probabilities "
          "still sum to 1. No collapse has happened yet — that's Milestone 3.")


if __name__ == "__main__":
    main()
