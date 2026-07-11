"""Advisory *check* probability for Quantum Chess.

This variant deliberately has **no** classical check / checkmate -- the king is
an ordinary, capturable, splittable piece (locked design decision, see
PLAN.md / CLAUDE.md). Nothing here changes that: this module is a purely
*informational* overlay answering one question --

    "How likely is it that the enemy could capture this king on their very
     next move, given that both the king and any attacker may be superposed?"

Metric (chosen with the user): **aggregate danger**. Every distinct enemy
capturing attempt against the king is one *threat* with a success probability
``p_i``; the reported check probability is::

    1 - prod(1 - p_i)   over all threats

i.e. the chance that *at least one* threat lands, treating threats as
independent. The true danger is a little lower (the enemy actually gets only
one move, and some threats are mutually exclusive), but independence is the
agreed, simple, explainable model.

A single threat's probability is the product of the pieces that must "line up"
for that capture to happen:

* the attacker ghost must materialise on its square  (its ``prob``),
* every *other* piece's ghost sitting between it and the king must be **absent**
  (``1 - prob`` each -- if present it would block or be captured first), and
* the king ghost must materialise on the targeted square  (its ``prob``).

Solid blockers never appear as "between" ghosts: python-chess ``attacks`` over
the solid board already refuses to generate a ray through a solid piece, so
``rules.ghost_destinations`` (reused here) only yields reachable targets.

Headless like the rest of the engine -- no pygame, exact ``Fraction`` math, and
**no RNG**: this is the *expected* danger, not a rolled outcome.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from fractions import Fraction

import chess

from . import rules
from .model import Ghost, QuantumBoard
from .rules import Move


@dataclass(frozen=True)
class Threat:
    """One enemy capturing attempt against a single king ghost."""
    attacker_id: int
    from_square: int
    king_square: int          # the king-ghost square that would be captured
    prob: Fraction            # P(this one move captures the king)


def king_ghosts(qb: QuantumBoard, color: bool) -> list[Ghost]:
    """Every ghost of ``color``'s (living) king -- one square if solid, several
    if the king is itself superposed."""
    ghosts: list[Ghost] = []
    for piece in qb.living_pieces(color):
        if piece.ptype == chess.KING:
            ghosts.extend(qb.ghosts_of(piece.id))
    return ghosts


def threats_against(qb: QuantumBoard, color: bool) -> list[Threat]:
    """All enemy (``not color``) capturing attempts against ``color``'s king.

    One threat per (attacker ghost -> reachable king-ghost square) alignment.
    Independent of whose turn it is: it answers "if it were the enemy's move,
    what could they do to this king right now."
    """
    king_sq = {g.square: g for g in king_ghosts(qb, color)}
    if not king_sq:
        return []

    board = rules._solids_board(qb)
    threats: list[Threat] = []
    for enemy in qb.living_pieces(not color):
        for eg in qb.ghosts_of(enemy.id):
            for move in rules.ghost_destinations(qb, eg.square, board):
                target = king_sq.get(move.to_square)
                if target is None:
                    continue
                p = eg.prob
                for mid in chess.SquareSet(chess.between(eg.square, move.to_square)):
                    blocker = qb.ghost_at(mid)
                    if blocker is not None and blocker.piece_id != enemy.id:
                        p *= 1 - blocker.prob
                p *= target.prob
                if p > 0:
                    threats.append(Threat(enemy.id, eg.square, move.to_square, p))
    return threats


def check_probability(qb: QuantumBoard, color: bool) -> Fraction:
    """Aggregate danger to ``color``'s king: ``1 - prod(1 - p_i)`` over every
    threat. ``0`` means completely safe; ``1`` means a certain capture is
    available. Exact ``Fraction`` (e.g. ``Fraction(3, 8)``)."""
    survive = Fraction(1)
    for threat in threats_against(qb, color):
        survive *= 1 - threat.prob
    return 1 - survive


def _hypothetical_after(qb: QuantumBoard, move: Move) -> QuantumBoard:
    """A copy of ``qb`` with ``move`` applied as a plain *relocation* of the
    mover to its destination (plus removal of a solid piece captured outright,
    and the castling rook dragged along). The random collapse a CONTACT/CAPTURE
    move might trigger is **not** rolled -- for a "would this expose my king?"
    warning we assume the move simply completes as intended."""
    hypo = copy.deepcopy(qb)
    src = hypo.ghost_at(move.from_square)
    if src is None or src.piece_id != move.piece_id:
        return hypo

    if move.is_capture and move.captured_piece_id is not None:
        rules.remove_piece(hypo, move.captured_piece_id)

    prob = src.prob
    if src in hypo.ghosts:
        hypo.ghosts.remove(src)
    dest = hypo.ghost_at(move.to_square)
    if dest is not None and dest.piece_id == move.piece_id:
        dest.prob += prob                       # merge onto own ghost
    else:
        if dest is not None:
            hypo.ghosts.remove(dest)            # mover displaces a foreign ghost
        hypo.ghosts.append(Ghost(move.piece_id, move.to_square, prob))

    if move.castle_rook is not None:
        _rook_pid, rook_from, rook_to = move.castle_rook
        rook = hypo.ghost_at(rook_from)
        if rook is not None:
            rook.square = rook_to

    return hypo


def move_self_check(qb: QuantumBoard, move: Move) -> Fraction:
    """Aggregate danger to the *mover's own* king after ``move`` is played --
    the warning-before-you-move number. Detects both moving into an attack
    (the king itself, or a piece landing on an attacked square) and discovered
    exposure (a blocker leaving a line to the king)."""
    mover_color = qb.pieces[move.piece_id].color
    return check_probability(_hypothetical_after(qb, move), mover_color)
