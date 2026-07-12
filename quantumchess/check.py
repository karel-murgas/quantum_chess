"""Advisory *check* probability for Quantum Chess.

This variant deliberately has **no** classical check / checkmate -- the king is
an ordinary, capturable, splittable piece (locked design decision, see
PLAN.md / CLAUDE.md). Nothing here changes that: this module is a purely
*informational* overlay answering one question --

    "If it were the enemy's turn and they played their **single strongest
     move**, how likely is it that this king gets captured?"

Metric (chosen with the user): **the strongest single enemy move**::

    check_probability(qb, color) = max over every enemy move m of  P(m captures the king)

Not a sum, not a compounded product over independent threats -- the opponent
gets **one** move, so two separate attackers aiming at the king do *not* add up;
the danger is whatever their best move alone achieves. Conversely, a single
sliding move can sweep **several** king ghosts at once (path collapse measures
every ghost it passes), and that *does* raise the number, because that one move
really can catch the king wherever it turns out to be along the line.

Per-move capture probability (exact, no independence fudge *within* a move --
the engine's own collapse rules give it directly). For an enemy ghost of
presence ``p`` sliding ``from -> to`` along path squares ``s1..sn``::

    P(m captures king) = p * SUM over king ghosts on square s_k of
                                q(s_k) * PROD over each OTHER piece X with
                                          ghosts strictly before s_k on the path:
                                              ( 1 - (total of X's ghost mass there) )

* ``q(s_k)`` is the king ghost's probability of *being* on ``s_k``. King
  locations are **mutually exclusive** (the king is in exactly one place, weights
  sum to 1), so conditioned on "king is on ``s_k``" every *earlier* king ghost on
  the path is empty and drops out of the blocker product -- only non-king,
  non-attacker pieces can block the walk. Summing the ``q(s_k)`` terms is exact
  (mutually-exclusive events), which is what lets one slide that covers two king
  ghosts read as a certain capture.
* A blocking piece ``X`` with several ghosts on the path blocks with probability
  equal to the *sum* of those ghost masses (its locations are mutually exclusive
  too -- the sequential path-collapse renormalization works out to exactly this),
  while *distinct* pieces really are independent, hence the product over ``X``.
* The attacker's own other ghosts never block (the walk passes through them), so
  ``X`` ranges over non-king, non-attacker pieces only.

Solid blockers never appear as "between" ghosts: python-chess ``attacks`` over
the solid board already refuses to generate a ray through a solid piece, so
``rules.ghost_destinations`` (reused here) only yields reachable targets.

**Mass movement** (optional dial): when it's on, a *superposed* enemy piece may
mass-move -- one categorical roll picks which ghost is real, and the winning
ghost's chosen slide resolves with the mover *certain*. So its strongest king
threat is ``SUM over its ghosts g of  p_g * (best single leg of g, assuming g is
certainly present)`` -- a *sum* (the roll outcomes are mutually exclusive), each
term taking that ghost's best-capturing destination. This can strictly beat any
single move (two ghosts covering the king from opposite sides guarantee a
capture). Included in the max only when ``mass_movement=True`` is passed.

Headless like the rest of the engine -- no pygame, exact ``Fraction`` math, and
**no RNG**: this is the *expected* danger, not a rolled outcome.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

import chess

from . import rules
from .model import Ghost, QuantumBoard
from .rules import Move


@dataclass(frozen=True)
class KingThreat:
    """The enemy's strongest capturing move against one king, for display.

    ``prob`` is that move's capture probability (the reported check number).
    ``from_square``/``to_square`` name the slide (both ``None`` for a mass-move
    threat, which has no single origin/target)."""
    prob: Fraction
    attacker_id: int
    ptype: int
    from_square: Optional[int] = None
    to_square: Optional[int] = None
    is_mass: bool = False

    def describe(self) -> str:
        """Short human label, e.g. ``"R a4->f4"`` or ``"R mass"``."""
        letter = chess.piece_symbol(self.ptype).upper()
        if self.is_mass:
            return f"{letter} mass"
        return (f"{letter} {chess.square_name(self.from_square)}"
                f"->{chess.square_name(self.to_square)}")


def king_ghosts(qb: QuantumBoard, color: bool) -> list[Ghost]:
    """Every ghost of ``color``'s (living) king -- one square if solid, several
    if the king is itself superposed."""
    ghosts: list[Ghost] = []
    for piece in qb.living_pieces(color):
        if piece.ptype == chess.KING:
            ghosts.extend(qb.ghosts_of(piece.id))
    return ghosts


def _ordered_path(frm: int, to: int) -> list[int]:
    """The squares a slide crosses, in travel order: the squares strictly
    between ``frm`` and ``to`` (nearest first) then ``to`` itself. Empty
    ``between`` for a knight jump collapses this to just ``[to]``."""
    middle = sorted(chess.SquareSet(chess.between(frm, to)),
                    key=lambda s: chess.square_distance(frm, s))
    return middle + [to]


def _path_capture_part(qb: QuantumBoard, frm: int, to: int,
                       king_prob_by_sq: dict[int, Fraction],
                       attacker_id: int) -> Fraction:
    """Capture probability of a slide ``frm -> to`` **given the attacker is
    certainly present** -- the ``SUM_k q(s_k) * PROD_X (1 - blocker mass)`` term.

    Multiply by the attacker ghost's own ``prob`` for a single-move threat; use
    it as-is (weighted by the categorical roll) for a mass-move leg. Walks the
    path in travel order, accumulating each non-king / non-attacker piece's ghost
    mass as a blocker; king ghosts are mutually exclusive so they're summed as
    the ``q(s_k)`` terms and never counted as blockers of a *later* king ghost."""
    if not king_prob_by_sq:
        return Fraction(0)
    total = Fraction(0)
    blocker_mass: dict[int, Fraction] = {}   # piece_id -> ghost mass seen so far
    for sq in _ordered_path(frm, to):
        if sq in king_prob_by_sq:
            survival = Fraction(1)
            for mass in blocker_mass.values():
                survival *= 1 - mass
            total += king_prob_by_sq[sq] * survival
            continue                      # a king ghost never blocks a later one
        occ = qb.ghost_at(sq)
        if occ is None or occ.piece_id == attacker_id:
            continue                      # empty, or the attacker's own ghost (passes through)
        blocker_mass[occ.piece_id] = blocker_mass.get(occ.piece_id, Fraction(0)) + occ.prob
    return total


def strongest_threat(qb: QuantumBoard, color: bool,
                     mass_movement: bool = False) -> Optional[KingThreat]:
    """The enemy's single most dangerous move against ``color``'s king, or
    ``None`` if there is no king (or nothing threatens it -- ``prob == 0``).

    Considers every enemy ghost's pseudo-legal moves and, when ``mass_movement``
    is on, each superposed enemy piece's best mass move too. Independent of whose
    turn it actually is: "if it were the enemy's move, what's the worst they
    could do right now."""
    kg = king_ghosts(qb, color)
    if not kg:
        return None
    king_prob_by_sq = {g.square: g.prob for g in kg}
    board = rules._solids_board(qb)

    best: Optional[KingThreat] = None
    for enemy in qb.living_pieces(not color):
        ghosts = qb.ghosts_of(enemy.id)

        # Single-move threats: one ghost slides, capturing if it reaches the king.
        for eg in ghosts:
            for move in rules.ghost_destinations(qb, eg.square, board):
                part = _path_capture_part(qb, eg.square, move.to_square,
                                          king_prob_by_sq, enemy.id)
                if part == 0:
                    continue
                p = eg.prob * part
                if best is None or p > best.prob:
                    best = KingThreat(p, enemy.id, enemy.ptype,
                                      eg.square, move.to_square, is_mass=False)

        # Mass-move threat: the categorical roll picks the real ghost; each
        # ghost independently takes its best-capturing leg (assuming it's real).
        if mass_movement and len(ghosts) > 1:
            total = Fraction(0)
            for eg in ghosts:
                best_leg = Fraction(0)
                for move in rules.ghost_destinations(qb, eg.square, board):
                    part = _path_capture_part(qb, eg.square, move.to_square,
                                              king_prob_by_sq, enemy.id)
                    if part > best_leg:
                        best_leg = part
                total += eg.prob * best_leg
            if total > 0 and (best is None or total > best.prob):
                best = KingThreat(total, enemy.id, enemy.ptype, is_mass=True)

    return best


def check_probability(qb: QuantumBoard, color: bool,
                      mass_movement: bool = False) -> Fraction:
    """Danger to ``color``'s king = the enemy's strongest single move's capture
    probability (see the module docstring). ``0`` means completely safe; ``1``
    means some one move captures for certain. Exact ``Fraction``."""
    threat = strongest_threat(qb, color, mass_movement)
    return threat.prob if threat is not None else Fraction(0)


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


def move_self_check(qb: QuantumBoard, move: Move,
                    mass_movement: bool = False) -> Fraction:
    """Danger to the *mover's own* king after ``move`` is played -- the
    warning-before-you-move number. Detects both moving into an attack (the king
    itself, or a piece landing on an attacked square) and discovered exposure (a
    blocker leaving a line to the king)."""
    mover_color = qb.pieces[move.piece_id].color
    return check_probability(_hypothetical_after(qb, move), mover_color, mass_movement)
