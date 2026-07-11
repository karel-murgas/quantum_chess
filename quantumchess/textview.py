"""Headless text rendering of a QuantumBoard (no pygame).

Solid pieces show as plain letters (uppercase = White). A ghost square shows the
piece letter wrapped in ``*`` (e.g. ``*B*``). Because at most one ghost occupies a
square, the grid stays unambiguous; exact probabilities are listed in a legend
below the board (fractions can be non-1/2ⁿ after merges, e.g. 3/4).
"""

from __future__ import annotations

from fractions import Fraction

import chess

from .model import QuantumBoard

_FILES = "a b c d e f g h"


def _letter(qb: QuantumBoard, piece_id: int) -> str:
    p = qb.pieces[piece_id]
    sym = chess.piece_symbol(p.ptype)
    return sym.upper() if p.color == chess.WHITE else sym


def _cell(qb: QuantumBoard, square: int) -> str:
    g = qb.ghost_at(square)
    if g is None:
        return " . "
    letter = _letter(qb, g.piece_id)
    return f" {letter} " if qb.is_solid(g.piece_id) else f"*{letter}*"


def board_ascii(qb: QuantumBoard) -> str:
    lines = []
    for rank in range(7, -1, -1):
        row = "".join(_cell(qb, rank * 8 + file) for file in range(8))
        lines.append(f"{rank + 1} {row}")
    lines.append("   " + "  ".join(_FILES.split()))
    return "\n".join(lines)


def _frac(f: Fraction) -> str:
    return str(f.numerator) if f.denominator == 1 else f"{f.numerator}/{f.denominator}"


def superposition_legend(qb: QuantumBoard) -> str:
    rows = []
    for piece in sorted(qb.living_pieces(), key=lambda p: p.id):
        ghosts = qb.ghosts_of(piece.id)
        if len(ghosts) <= 1:
            continue
        color = "White" if piece.color == chess.WHITE else "Black"
        name = chess.piece_name(piece.ptype).capitalize()
        spots = "  ".join(
            f"{chess.square_name(g.square)}={_frac(g.prob)}"
            for g in sorted(ghosts, key=lambda g: g.square)
        )
        total = sum((g.prob for g in ghosts), Fraction(0))
        rows.append(f"  {color} {name} #{piece.id}: {spots}   (sum={_frac(total)})")
    if not rows:
        return "  (no pieces in superposition)"
    return "\n".join(rows)


def render(qb: QuantumBoard) -> str:
    turn = "White" if qb.turn == chess.WHITE else "Black"
    out = [board_ascii(qb), "", f"Turn: {turn}", "Superpositions:", superposition_legend(qb)]
    if qb.game_over and qb.winner is not None:
        win = "White" if qb.winner == chess.WHITE else "Black"
        out.append(f"** {win} wins (king captured) **")
    return "\n".join(out)
