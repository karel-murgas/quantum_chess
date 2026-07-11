"""Milestone 1 demo: a legal random game under the capture-the-king ruleset.

Run:  python demo_m1.py [seed]

Prints the opening position, a compact move log, the final position, and the
result. Proves the headless board model + movement engine work end-to-end before
any quantum layer is added.
"""

import sys

import chess

from quantumchess.game import random_selfplay


def color_name(c: bool) -> str:
    return "White" if c == chess.WHITE else "Black"


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    qb, log = random_selfplay(seed=seed, max_plies=1000)

    print(f"Quantum Chess — Milestone 1 random self-play (seed={seed})\n")
    print("Opening position:")
    print(qb.__class__.standard_setup().ascii())
    print()

    for rec in log:
        num = f"{(rec.ply + 1)//2}."
        side = color_name(rec.mover_color)[0]
        print(f"  {rec.ply:>3}  {num:<4} {side} {rec.move.uci():<6} {rec.note}")

    print("\nFinal position:")
    print(qb.ascii())
    print()
    if qb.winner is not None:
        print(f"Result: {color_name(qb.winner)} wins by capturing the king "
              f"(after {len(log)} plies).")
    else:
        print(f"Result: no king captured within {len(log)} plies (draw/aborted).")


if __name__ == "__main__":
    main()
