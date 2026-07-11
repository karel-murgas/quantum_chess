"""Collapse resolution — the quantum core of Quantum Chess (Milestone 3).

A ``CONTACT`` move (see ``rules.MoveKind``) means the mover's path touches at
least one ghost belonging to a *different* piece. This module resolves that with
a seeded RNG, per PLAN.md:

  1. Measure the mover: is it really at its source square (prob ``p``)?
     - No: the move fizzles. The mover's *other* ghosts are unaffected by this
       move, but the measured ghost is gone -- apply the configured collapse
       mode to what's left of the mover's own superposition.
     - Yes: the mover is confirmed -- it collapses solid, dropping every other
       ghost of that piece.
  2. Walk the path (source -> destination) one square at a time. Each square
     holding a *different* piece's ghost is measured in turn:
     - Really there, enemy: captured; the mover's movement ends *there* (it may
       stop short of its intended destination).
     - Really there, friendly: the blocker is confirmed solid; the mover's
       movement ends on the square *before* it (never captures its own side).
     - Not there: that piece's ghost is gone -- apply the collapse mode to its
       remaining ghosts, and the mover's path continues.
  A single move can therefore resolve several pieces' superpositions in a row.

Non-CONTACT moves (RELOCATE / MERGE / CAPTURE_SOLID) are deterministic and are
simply delegated to ``rules.apply_move`` -- there is nothing to measure.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from fractions import Fraction
from typing import Optional

import chess

from .config import CollapseMode, GameConfig
from .model import Ghost, QuantumBoard
from .rules import (
    Move, MoveKind, Split, apply_move, remove_piece,
    split_destination_castle_rook, split_destination_kind,
)


@dataclass
class CollapseEvent:
    """One measurement performed while resolving a move (for logging/UI).

    ``removed`` / ``captured_square`` describe the *visual* consequence of this
    single measurement so the UI can animate it without re-deriving the engine
    math: ``removed`` is every ghost this measurement wiped off the board --
    ``(square, prob)`` pairs (siblings dropped on a positive collapse; the
    measured ghost plus, in FULL mode, its siblings on a negative one; a
    captured piece's *other* ghosts). ``captured_square`` is where an enemy was
    actually taken (its token shatters there). Not frozen so the resolver can
    fill these in right after the mutating collapse helpers report back.
    """
    role: str            # "mover" | "path" | "destination" | "split" | "promotion"
    piece_id: int
    square: int
    prob_before: Fraction
    present: bool
    removed: tuple[tuple[int, Fraction], ...] = ()   # (square, prob) ghosts wiped here
    captured_square: Optional[int] = None            # enemy taken here (shatter point)


@dataclass
class MoveResolution:
    events: list[CollapseEvent] = field(default_factory=list)
    fizzled: bool = False               # True: the mover ghost wasn't really there
    final_square: Optional[int] = None  # where the mover ended up (None if fizzled)
    captured_piece_ids: list[int] = field(default_factory=list)


@dataclass
class SplitResolution:
    """Result of ``resolve_split``. Unlike a move, a split can't "fizzle" as a
    whole -- at least the measurement-free branch (if any) always lands; only
    an individual enemy-contacting branch can come up empty."""
    events: list[CollapseEvent] = field(default_factory=list)
    captured_piece_ids: list[int] = field(default_factory=list)


def _flip(rng: random.Random, prob: Fraction) -> bool:
    """True with probability ``prob``."""
    return rng.random() < prob


def _path_order(qb: QuantumBoard, piece_id: int, frm: int, to: int) -> list[int]:
    """Squares from (excluding) ``frm`` to (including) ``to``, in travel order.

    Knights jump -- only the landing square is a contact point.
    """
    if qb.pieces[piece_id].ptype == chess.KNIGHT:
        return [to]
    ff, fr = chess.square_file(frm), chess.square_rank(frm)
    tf, tr = chess.square_file(to), chess.square_rank(to)
    df = (tf > ff) - (tf < ff)
    dr = (tr > fr) - (tr < fr)
    squares = []
    f, r = ff + df, fr + dr
    while (f, r) != (tf, tr):
        squares.append(chess.square(f, r))
        f, r = f + df, r + dr
    squares.append(to)
    return squares


def _collapse_negative(qb: QuantumBoard, piece_id: int, removed: Ghost,
                       config: GameConfig, rng: random.Random
                       ) -> list[tuple[int, Fraction]]:
    """Apply the configured collapse mode after a ghost measures "not here".

    Returns the ``(square, prob)`` of every ghost this wiped -- always the
    measured ghost itself, plus (FULL mode) the non-chosen siblings -- so the
    UI can fade exactly those tokens out.
    """
    wiped = [(removed.square, removed.prob)]
    qb.ghosts.remove(removed)
    remaining = qb.ghosts_of(piece_id)
    if config.collapse_mode == CollapseMode.PARTIAL:
        scale = Fraction(1) / (Fraction(1) - removed.prob)
        for g in remaining:
            g.prob *= scale
    else:  # FULL: roll the real location among the remaining ghosts, drop the rest
        if remaining:
            weights = [float(g.prob) for g in remaining]
            chosen = rng.choices(remaining, weights=weights, k=1)[0]
            chosen.prob = Fraction(1)
            wiped.extend((g.square, g.prob) for g in remaining if g is not chosen)
            qb.ghosts = [g for g in qb.ghosts if g.piece_id != piece_id or g is chosen]
    return wiped


def _collapse_positive(qb: QuantumBoard, piece_id: int, keep: Ghost
                       ) -> list[tuple[int, Fraction]]:
    """The measured ghost really was there: it goes solid, its siblings vanish.

    Returns the ``(square, prob)`` of the wiped siblings (for fade-out visuals).
    """
    wiped = [(g.square, g.prob) for g in qb.ghosts
             if g.piece_id == piece_id and g is not keep]
    keep.prob = Fraction(1)
    qb.ghosts = [g for g in qb.ghosts if g.piece_id != piece_id or g is keep]
    return wiped


def _capture(qb: QuantumBoard, victim_id: int, winner_color: bool) -> None:
    victim = qb.pieces[victim_id]
    remove_piece(qb, victim_id)
    if victim.ptype == chess.KING:
        qb.winner = winner_color
        qb.game_over = True


def _walk_contact(qb: QuantumBoard, pid: int, mover_color: bool, frm: int, to: int,
                  config: GameConfig, rng: random.Random,
                  events: list[CollapseEvent], captured_ids: list[int]) -> int:
    """Walk ``frm`` -> ``to`` measuring every foreign ghost in turn (used once
    the mover/branch at ``frm`` is already confirmed real). Returns the square
    the mover actually stops on -- may be short of ``to`` if a blocker turns
    out to be really there."""
    stop_square = to
    path = _path_order(qb, pid, frm, to)
    for i, sq in enumerate(path):
        occ = qb.ghost_at(sq)
        if occ is None or occ.piece_id == pid:
            continue
        target_color = qb.pieces[occ.piece_id].color
        p_target = occ.prob
        really_there = _flip(rng, p_target)
        ev = CollapseEvent(
            "destination" if sq == to else "path",
            occ.piece_id, sq, p_target, really_there,
        )
        events.append(ev)
        if really_there:
            if target_color == mover_color:
                ev.removed = tuple(_collapse_positive(qb, occ.piece_id, occ))  # confirm blocker
                stop_square = path[i - 1] if i > 0 else frm
            else:
                # capture: the victim's token at ``sq`` shatters; any other ghosts
                # of that same piece (superposed victim) fade out alongside it.
                ev.removed = tuple((g.square, g.prob) for g in qb.ghosts
                                   if g.piece_id == occ.piece_id and g.square != sq)
                ev.captured_square = sq
                _capture(qb, occ.piece_id, mover_color)
                captured_ids.append(occ.piece_id)
                stop_square = sq
            break
        else:
            ev.removed = tuple(_collapse_negative(qb, occ.piece_id, occ, config, rng))
            # not there -> movement continues past this square
    return stop_square


def _resolve_promotion_relocate(qb: QuantumBoard, move: Move, config: GameConfig,
                                rng: random.Random) -> MoveResolution:
    """A quiet (RELOCATE/MERGE) pawn push lands on the promotion rank while the
    pawn is still just a ghost (prob < 1). Reaching the back rank forces an
    immediate self-measurement before it's allowed to promote: really there ->
    confirm solid, drop siblings, promote; not there -> that ghost is gone (the
    collapse mode applies to whatever's left), no promotion -- its problem."""
    apply_move(qb, replace(move, promotion=None))  # relocate only; hold the promotion back
    pid = move.piece_id
    ghost = qb.ghost_at(move.to_square)
    present = _flip(rng, ghost.prob)
    ev = CollapseEvent("promotion", pid, move.to_square, ghost.prob, present)
    if present:
        ev.removed = tuple(_collapse_positive(qb, pid, ghost))
        qb.pieces[pid].ptype = move.promotion
    else:
        ev.removed = tuple(_collapse_negative(qb, pid, ghost, config, rng))
    return MoveResolution(events=[ev], fizzled=False, final_square=move.to_square,
                          captured_piece_ids=[])


def resolve_move(qb: QuantumBoard, move: Move, config: GameConfig,
                 rng: random.Random) -> MoveResolution:
    """Execute ``move``, resolving any quantum contact along the way."""
    if qb.game_over:
        raise RuntimeError("game is already over")

    if move.kind in (MoveKind.RELOCATE, MoveKind.MERGE):
        # No interaction with another piece at all (empty square, or the mover's
        # own ghost) -- nothing to measure, no collapse... unless this is a pawn
        # reaching the promotion rank while still just a ghost (prob < 1): the
        # back rank forces an immediate self-measurement before it can promote
        # (see _resolve_promotion_relocate). A solid pawn (prob == 1) has
        # nothing left to measure and promotes exactly as before.
        if move.promotion is not None:
            source_ghost = qb.ghost_at(move.from_square)
            if source_ghost.prob < 1:
                return _resolve_promotion_relocate(qb, move, config, rng)
        apply_move(qb, move)
        return MoveResolution(events=[], fizzled=False, final_square=move.to_square,
                              captured_piece_ids=[])

    # CAPTURE_SOLID or CONTACT: the move touches another piece, so the mover's own
    # presence is measured first -- capturing even a *certain* piece only succeeds
    # if the (possibly superposed) mover is confirmed to really be here.
    pid = move.piece_id
    mover_color = qb.pieces[pid].color
    qb.pieces[pid].has_moved = True
    source_ghost = qb.ghost_at(move.from_square)
    p_mover = source_ghost.prob

    present = _flip(rng, p_mover)
    mover_ev = CollapseEvent("mover", pid, move.from_square, p_mover, present)
    events = [mover_ev]

    if not present:
        mover_ev.removed = tuple(_collapse_negative(qb, pid, source_ghost, config, rng))
        qb.ep_square = None
        qb.turn = not qb.turn
        return MoveResolution(events=events, fizzled=True, final_square=None,
                              captured_piece_ids=[])

    mover_ev.removed = tuple(_collapse_positive(qb, pid, source_ghost))  # solid @ from

    if move.kind == MoveKind.CAPTURE_SOLID:
        # By construction (see rules.ghost_destinations) this path holds no
        # foreign ghosts and the target is certain -- capture proceeds outright.
        # The take is at the destination, so the mover event carries the shatter
        # point even though its own flash is back at ``from_square``.
        captured_ids = [move.captured_piece_id] if move.captured_piece_id is not None else []
        if move.captured_piece_id is not None:
            mover_ev.captured_square = move.to_square
            _capture(qb, move.captured_piece_id, mover_color)
        source_ghost.square = move.to_square
        if move.promotion is not None:
            qb.pieces[pid].ptype = move.promotion
        qb.ep_square = (move.from_square + move.to_square) // 2 if move.is_double_push else None
        if move.castle_rook is not None:
            rook_pid, rook_from, rook_to = move.castle_rook
            qb.ghost_at(rook_from).square = rook_to
            qb.pieces[rook_pid].has_moved = True
        if not qb.game_over:
            qb.turn = not qb.turn
        return MoveResolution(events=events, fizzled=False, final_square=move.to_square,
                              captured_piece_ids=captured_ids)

    captured_ids: list[int] = []
    stop_square = _walk_contact(qb, pid, mover_color, move.from_square, move.to_square,
                                config, rng, events, captured_ids)

    source_ghost.square = stop_square
    if move.promotion is not None and stop_square == move.to_square:
        qb.pieces[pid].ptype = move.promotion
    qb.ep_square = None
    if move.castle_rook is not None and stop_square == move.to_square:
        # The rook only follows if the king's walk reached the full castle
        # distance uncollapsed -- rook_to is always one of the squares that
        # walk already measured, so this relocation itself needs no roll.
        rook_pid, rook_from, rook_to = move.castle_rook
        qb.ghost_at(rook_from).square = rook_to
        qb.pieces[rook_pid].has_moved = True
    if not qb.game_over:
        qb.turn = not qb.turn

    return MoveResolution(events=events, fizzled=False, final_square=stop_square,
                          captured_piece_ids=captured_ids)


def _resolve_split_branch(qb: QuantumBoard, pid: int, mover_color: bool, frm: int, to: int,
                          kind: MoveKind, cap_id: Optional[int], ghost: Ghost,
                          config: GameConfig, rng: random.Random,
                          events: list[CollapseEvent], captured_ids: list[int],
                          castle_rook: Optional[tuple[int, int, int]] = None) -> None:
    """Measure ``ghost`` (already placed at ``to``, at whatever probability it
    currently holds) against the enemy there, exactly like a mover in
    ``resolve_move`` -- a superposed branch capturing a *certain* enemy still
    isn't a guaranteed capture. ``ghost.prob`` may have been renormalized up
    (e.g. to 1) by a sibling split branch fizzling first -- conservation of
    probability, not a fresh independent coin flip, is what keeps a split from
    ever vanishing both branches at once.

    ``castle_rook``, when this branch targets a castle square, is the rook to
    drag along -- never superposed, it follows with one plain relocation only
    once this branch is confirmed to have actually reached ``to`` (mirroring
    ``resolve_move``'s "rook follows only if the king's walk completes")."""
    present = _flip(rng, ghost.prob)
    ev = CollapseEvent("split", pid, to, ghost.prob, present)
    events.append(ev)

    if not present:
        ev.removed = tuple(_collapse_negative(qb, pid, ghost, config, rng))
        return

    ev.removed = tuple(_collapse_positive(qb, pid, ghost))  # confirmed real; siblings vanish

    if kind == MoveKind.CAPTURE_SOLID:
        # No foreign ghosts on the path by construction (see rules.ghost_destinations).
        # The enemy is taken right where this branch landed -- shatter it at ``to``.
        if cap_id is not None:
            ev.captured_square = to
            _capture(qb, cap_id, mover_color)
            captured_ids.append(cap_id)
        if castle_rook is not None:
            rook_pid, rook_from, rook_to = castle_rook
            qb.ghost_at(rook_from).square = rook_to
            qb.pieces[rook_pid].has_moved = True
        return

    stop_square = _walk_contact(qb, pid, mover_color, frm, to, config, rng, events, captured_ids)
    ghost.square = stop_square
    if castle_rook is not None and stop_square == to:
        rook_pid, rook_from, rook_to = castle_rook
        qb.ghost_at(rook_from).square = rook_to
        qb.pieces[rook_pid].has_moved = True


def resolve_split(qb: QuantumBoard, split: Split, config: GameConfig,
                  rng: random.Random) -> SplitResolution:
    """Execute ``split``. A destination that's empty or a same-piece merge
    just places the p/2 ghost (no measurement, per ``rules.apply_split``). A
    destination that contacts an enemy is measured immediately -- both
    branches settle in the same instant the split is made, the same way a
    CONTACT/CAPTURE_SOLID move measures on contact.

    Both branches are placed *before* either is measured (mirroring the
    measurement-free split, which always creates both halves up front). That
    matters when both destinations are enemy-contacting: if the first
    measures negative, ``_collapse_negative`` renormalizes the *other*
    branch's already-existing ghost up to absorb the lost probability --
    conservation, not an independent coin flip -- so the piece can never
    measure "not here" on every branch and vanish outright.
    """
    if qb.game_over:
        raise RuntimeError("game is already over")
    if split.to_a == split.to_b:
        raise ValueError("a split needs two distinct destination squares")

    pid = split.piece_id
    mover_color = qb.pieces[pid].color
    source = qb.ghost_at(split.from_square)
    if source is None or source.piece_id != pid:
        raise ValueError("no such ghost to split")

    # Classify both destinations (a castle destination needs has_moved still
    # False to be recognized) *before* marking the piece moved.
    dest_info = {}
    castle_info = {}
    for dest in (split.to_a, split.to_b):
        kind, cap_id = split_destination_kind(qb, split.from_square, dest)
        if kind is None:
            raise ValueError("both split destinations must be legal")
        dest_info[dest] = (kind, cap_id)
        castle_info[dest] = split_destination_castle_rook(qb, split.from_square, dest)
    qb.pieces[pid].has_moved = True

    half = source.prob / 2
    qb.ghosts.remove(source)

    events: list[CollapseEvent] = []
    captured_ids: list[int] = []
    simple_kinds = (MoveKind.RELOCATE, MoveKind.MERGE)

    contact_ghosts: dict[int, Ghost] = {}
    for dest in (split.to_a, split.to_b):
        kind, _cap_id = dest_info[dest]
        if kind in simple_kinds:
            existing = qb.ghost_at(dest)
            if existing is not None and existing.piece_id == pid:
                existing.prob += half
            else:
                qb.ghosts.append(Ghost(pid, dest, half))
            # Clear-path castle branch: no measurement, so the rook (never
            # superposed) just makes its own plain move right here.
            castle_rook = castle_info[dest]
            if castle_rook is not None:
                rook_pid, rook_from, rook_to = castle_rook
                qb.ghost_at(rook_from).square = rook_to
                qb.pieces[rook_pid].has_moved = True
        else:
            g = Ghost(pid, dest, half)
            qb.ghosts.append(g)
            contact_ghosts[dest] = g

    for dest in (split.to_a, split.to_b):
        kind, cap_id = dest_info[dest]
        if kind in simple_kinds:
            continue
        if qb.game_over:
            continue
        ghost = contact_ghosts[dest]
        if not any(g is ghost for g in qb.ghosts):
            # An earlier branch already confirmed the piece solid elsewhere,
            # wiping this one -- it never happened, so it's never measured.
            continue
        _resolve_split_branch(qb, pid, mover_color, split.from_square, dest,
                              kind, cap_id, ghost, config, rng, events, captured_ids,
                              castle_rook=castle_info[dest])

    qb.ep_square = None
    if not qb.game_over:
        qb.turn = not qb.turn

    return SplitResolution(events=events, captured_piece_ids=captured_ids)
