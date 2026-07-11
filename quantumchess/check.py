"""Advisory *check* probability for Quantum Chess.

This variant deliberately has **no** classical check / checkmate -- the king is
an ordinary, capturable, splittable piece (locked design decision, see
PLAN.md / CLAUDE.md). Nothing here changes that: this module is a purely
*informational* overlay answering one question --

    "How likely is it that the enemy could capture this king on their very
     next move, given that both the king and any attacker may be superposed?"

Metric (chosen with the user): **aggregate danger**, computed by *conditioning
on where the king actually is*. The king occupies exactly **one** of its ghost
squares -- those locations are mutually exclusive, with weights (the ghost
``prob`` values) that sum to 1. So the reported check probability is::

    sum over king squares s of  q_s * ( 1 - prod(1 - a_i)  over threats on s )

where ``q_s`` is the king ghost's probability of *being* on ``s`` and ``a_i`` is
the *attacker-side* success probability of one threat aimed at ``s`` (does **not**
include the king's own presence -- that is already accounted for by ``q_s``).
``1 - prod(1 - a_i)`` is the chance at least one attacker lands *given the king
is on ``s``*, treating the distinct enemy attackers as independent (a mild
overestimate, the agreed simple model). Averaging over ``s`` with the true,
mutually-exclusive weights ``q_s`` is what makes a fully-covered king read as a
certain (``1``) check rather than being spuriously discounted -- the old
``1 - prod(1 - p_i)`` over *all* threats treated the king's own location on
different squares as independent Bernoullis and under-reported when several of
its ghosts were simultaneously threatened (a superposed king cornered on every
square it could be on is dead for certain, and now shows it).

An attacker-side threat probability ``a_i`` is the product of the pieces that
must "line up" for that capture to happen, *excluding* the king:

* the attacker ghost must materialise on its square  (its ``prob``), and
* every *other* piece's ghost sitting between it and the king must be **absent**
  (``1 - prob`` each -- if present it would block or be captured first).

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
    """One enemy capturing attempt against a single king ghost.

    ``prob`` is the *attacker-side* success probability -- P(this attacker
    materialises on ``king_square`` with a clear path), which does **not**
    include the king's own presence there. That factor is carried separately as
    ``king_prob`` so ``check_probability`` can weight it as the mutually-exclusive
    "king is actually on this square" probability instead of folding it into an
    independent product (see the module docstring)."""
    attacker_id: int
    from_square: int
    king_square: int          # the king-ghost square that would be captured
    prob: Fraction            # P(attacker reaches king_square) -- excludes king prob
    king_prob: Fraction       # P(the king is actually on king_square)


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
                if p > 0:
                    threats.append(
                        Threat(enemy.id, eg.square, move.to_square, p, target.prob))
    return threats


def check_probability(qb: QuantumBoard, color: bool) -> Fraction:
    """Aggregate danger to ``color``'s king, conditioned on the king's location.

    Partition the threats by the king-ghost square they aim at (mutually
    exclusive locations, weights ``q_s`` summing to 1), aggregate the
    attacker-side threats *within* each square as ``1 - prod(1 - a_i)``, then
    take the ``q_s``-weighted average::

        sum_s  q_s * (1 - prod(1 - a_i) over threats on s)

    ``0`` means completely safe; ``1`` means capture is certain wherever the king
    turns out to be. Exact ``Fraction`` (e.g. ``Fraction(3, 8)``)."""
    # king_square -> (q_s, running product of attacker survival on that square)
    by_square: dict[int, list[Fraction]] = {}
    for threat in threats_against(qb, color):
        entry = by_square.get(threat.king_square)
        if entry is None:
            by_square[threat.king_square] = [threat.king_prob, 1 - threat.prob]
        else:
            entry[1] *= 1 - threat.prob
    danger = Fraction(0)
    for king_prob, survive in by_square.values():
        danger += king_prob * (1 - survive)
    return danger


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
