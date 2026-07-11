"""Collapse-animation model (Milestone 4+) -- turns a resolved move/split into a
sequence of drawable *beats* so the board can narrate the collapse instead of
snapping straight to the outcome.

Deliberately **pygame-free** (like the engine): it works in square ints, exact
``Fraction`` probabilities and a normalized progress ``t`` in [0, 1]; render.py
turns that into pixels. That keeps the beat logic unit-testable headlessly, the
same way the engine is.

Choreography (user-chosen 2026-07-11): *movement first, then reveals.* One
TRAVEL beat slides the mover -- or both split branches -- out from the source;
then one FLASH beat per ``CollapseEvent`` pulses the measured square green
(really there) or red (not there), fades out every ghost that measurement wiped,
shatters a captured piece, and floats a short caption. Durations vary by
distance / whether the beat also removes something ("variable by complexity").

The board is already fully resolved by the time we build this (the engine
resolves instantly), so a beat's ``rest`` layer is reconstructed here from the
*pre-resolve* snapshot plus the movers, evolving event by event -- that's what
keeps a split branch that will vanish visible until its own flash fades it,
rather than popping out the instant the engine dropped it.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from fractions import Fraction
from typing import Optional

import chess

from . import theme

# Pacing (ms). Travel scales with the longest slide; a flash that also removes
# something gets extra room so the fade/shatter is followable.
TRAVEL_MS_BASE = 150
TRAVEL_MS_PER_STEP = 55
TRAVEL_MS_MAX = 560
FLASH_MS = 500
FLASH_EXTRA_MS = 320


@dataclass(frozen=True)
class Token:
    """A drawable piece instance at a square, at a given probability/solidity."""
    piece_id: int
    color: bool          # chess.WHITE / chess.BLACK
    ptype: int
    square: int
    prob: Fraction
    solid: bool


@dataclass
class Beat:
    """One animation step. ``rest`` tokens draw statically; ``travel`` tokens
    slide from a source square to their own ``square``; ``fades`` dissolve;
    ``shatter`` is a captured piece bursting; ``flash_*`` pulses a square."""
    duration_ms: int
    rest: tuple[Token, ...] = ()
    travel: tuple[tuple[Token, int], ...] = ()      # (token, from_square)
    flash_square: Optional[int] = None
    flash_present: Optional[bool] = None
    flash_role: Optional[str] = None                # CollapseEvent.role: "mover"/"split"/"promotion"/"path"/"destination"
    fades: tuple[Token, ...] = ()
    shatter: Optional[Token] = None
    caption: Optional[str] = None
    caption_square: Optional[int] = None


def _cheby(a: int, b: int) -> int:
    return max(abs(chess.square_file(a) - chess.square_file(b)),
               abs(chess.square_rank(a) - chess.square_rank(b)))


def _pop_at(tokens: list[Token], square: int, piece_id: int) -> Optional[Token]:
    for i, t in enumerate(tokens):
        if t.square == square and t.piece_id == piece_id:
            return tokens.pop(i)
    return None


def _pop_foreign_at(tokens: list[Token], square: int, own_pids: set[int]) -> Optional[Token]:
    for i, t in enumerate(tokens):
        if t.square == square and t.piece_id not in own_pids:
            return tokens.pop(i)
    return None


def _solidify(tokens: list[Token], piece_id: int, square: int, by_piece: bool) -> None:
    """Replace a ghost with its solid self in-place. ``by_piece`` matches on the
    piece anywhere (used for a confirmed *mover*, which has already slid to its
    destination); otherwise match the token sitting on ``square`` (a confirmed
    blocker)."""
    for i, t in enumerate(tokens):
        hit = (t.piece_id == piece_id) if by_piece else \
              (t.square == square and t.piece_id == piece_id)
        if hit:
            tokens[i] = replace(t, prob=Fraction(1), solid=True)
            return


def _caption(ev) -> tuple[str, int]:
    terms = theme.TERMS
    if ev.captured_square is not None:
        return terms["reveal_capture"], ev.captured_square
    word = terms["reveal_present"] if ev.present else terms["reveal_absent"]
    return word, ev.square


def build_animation(before: list[Token],
                    movers: list[tuple[Token, int]],
                    events) -> list[Beat]:
    """Build the beat script.

    ``before``  -- every token on the board *before* the move resolved.
    ``movers``  -- ``(token_at_destination, from_square)`` for each thing that
                   slides out (one for a move, two for a split; empty on a
                   fizzle where nothing moves). ``token.prob`` is the
                   pre-measurement look (ghost alpha) while it travels.
    ``events``  -- the resolver's ordered ``CollapseEvent`` list.
    """
    beats: list[Beat] = []

    mover_pids = {tok.piece_id for tok, _ in movers}
    consumed = {(frm, tok.piece_id) for tok, frm in movers}
    current: list[Token] = [t for t in before if (t.square, t.piece_id) not in consumed]
    mover_tokens = [tok for tok, _ in movers]
    current.extend(mover_tokens)

    # --- TRAVEL: slide everything that actually changes square.
    real_movers = [(tok, frm) for tok, frm in movers if frm != tok.square]
    if real_movers:
        maxd = max(_cheby(frm, tok.square) for tok, frm in real_movers)
        dur = min(TRAVEL_MS_MAX, TRAVEL_MS_BASE + TRAVEL_MS_PER_STEP * maxd)
        moving = set(mover_tokens)
        rest = tuple(t for t in current if t not in moving)
        beats.append(Beat(duration_ms=dur, rest=rest,
                          travel=tuple((tok, frm) for tok, frm in real_movers)))

    # --- FLASH: one beat per measurement, evolving ``current`` as we go.
    for ev in events:
        fades = [t for t in (_pop_at(current, sq, ev.piece_id) for sq, _ in ev.removed)
                 if t is not None]
        shatter = None
        if ev.captured_square is not None:
            shatter = _pop_foreign_at(current, ev.captured_square, mover_pids)

        if ev.present and ev.captured_square is None:
            by_piece = ev.role in ("mover", "split", "promotion")
            _solidify(current, ev.piece_id, ev.square, by_piece)

        caption, caption_sq = _caption(ev)
        extra = FLASH_EXTRA_MS if (fades or shatter is not None) else 0
        beats.append(Beat(
            duration_ms=FLASH_MS + extra,
            rest=tuple(current),
            flash_square=ev.square,
            flash_present=ev.present,
            flash_role=ev.role,
            fades=tuple(fades),
            shatter=shatter,
            caption=caption,
            caption_square=caption_sq,
        ))

    return beats


def total_duration(beats: list[Beat]) -> int:
    return sum(b.duration_ms for b in beats)
