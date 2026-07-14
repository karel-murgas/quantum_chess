# Quantum Chess — project guide

A hotseat (2 local humans, no timer) chess variant: standard chess plus a
**superposition / collapse** layer. Pieces can *split* into ghosts with
probabilities; contact triggers a random **collapse** that reveals where a piece
really was.

## Where to look

| Doc | What's in it |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | One-page map of every module. **Start here.** |
| [docs/ENGINE.md](docs/ENGINE.md) | Deep mechanics: the ruleset as a spec, dials, collapse, mass move/split, castling, check, persistence. |
| [docs/UI.md](docs/UI.md) | Deep mechanics: rendering pipeline, skins, planning UI, menu. |
| [docs/HISTORY.md](docs/HISTORY.md) | Dated log — what shipped, why, which playtest prompted it (includes the skin-redesign history). |
| [HOW_TO_PLAY.md](HOW_TO_PLAY.md) | Player-facing rules/controls. |
| [ONLINE_PLAY.md](ONLINE_PLAY.md) | Online play — **design only, not built.** |

**Keep docs current.** A new feature updates `docs/ENGINE.md` or `docs/UI.md` (the
mechanism) and `docs/HISTORY.md` (the dated why) — *not* this file. Only edit CLAUDE.md
when something below actually changes.

## Stack

Python 3.13 · **`python-chess`** (movement oracle only) · **`pygame-ce`** (UI) ·
`pytest`. Install: `pip install -r requirements.txt`.

## Run / test

```bash
python main.py                    # play (needs a real display)
python -m pytest -q               # 231 passing
```

UI tests need `SDL_VIDEODRIVER=dummy` (set automatically at the top of `test_m4_ui.py`).

## Hard rules

1. **The engine is headless.** `quantumchess/` must never import `pygame`; `quantumchess/ui/`
   is the only place that does. Keeps the quantum logic unit-testable and a web frontend
   possible.
2. **Probabilities are exact `Fraction`s.** Never floats. Tests assert per-piece sums == 1.
3. **A piece only ever superposes with its own ghosts — no cross-piece entanglement, ever.**
4. **Occupancy invariant: ≤1 ghost per square.** Same-piece ghosts merge (probabilities add);
   a different piece's ghost is a `CONTACT` that needs a collapse.
5. **Dials are gated in the UI, not the engine.** `resolve_*` functions are dial-agnostic by
   design; `App`/`Menu` enforce `splitting_enabled` / `mass_movement` / `mass_split`.
6. **UI modules read the palette as `theme.X`** (attribute lookup, never
   `from theme import X`) — `theme.apply_theme()` does `globals().update()`, so one call
   repaints everything with no plumbing.
7. Reuse **python-chess constants** everywhere (`chess.WHITE`/`BLACK`, piece types, square
   ints 0..63) for zero-friction interop.

## Locked v1 design decisions

Don't silently change these — they were decided with the user.

- **Win = capture the king.** No check / checkmate / stalemate. The king is an ordinary,
  capturable, splittable piece. The **check-probability overlay** (`check.py`) is *purely
  advisory*: it never restricts a move, it only displays how likely a king is to be
  capturable next turn.
- **A turn = one action on one ghost**: move it, or *split* it (`p → p/2, p/2`). One split
  branch may stay on the source square — gated by the **`split_stay_enabled`** dial (needs
  `splitting_enabled`; on by default).
  - The optional **`mass_movement`** dial relaxes this: a *superposed* piece may instead move
    **all** its ghosts in one planned turn, settled by a **single** categorical roll.
  - The optional **`mass_split`** dial (needs `mass_movement`) lets each ghost in such a turn
    *split* as well as move. Both are off by default and provably reduce to the single move.
  - The optional **`mass_all_must_act`** dial (needs `mass_movement`) forbids leaving any
    ghost at its default "stay" assignment — every ghost in the plan must move or split.
    Off by default (a mass turn may leave some ghosts untouched).
- **Collapse modes (match dial)** — on a *negative* measurement ("not here"):
  *Partial* only the contacted ghost vanishes and the rest renormalize; *Full* resolves the
  whole piece to one location. A *positive* measurement always collapses to solid, both modes.
- **Path collapse**: a mover measures every ghost it passes. Real ⇒ movement stops there
  (capture if enemy); not-there ⇒ it continues. One move can collapse a chain and stop short
  of its target.
- **Measurement only happens on collision.** Relocating to an empty square (or merging onto
  your own ghost) is instant — no dice. The one exception is a *ghost* pawn landing on the
  promotion rank, which is measured on the spot.
- **A superposed mover capturing a *certain* piece is still measured** — it is not a
  guaranteed capture just because the target isn't in question. (This was a real bug.)
- **No split cap** — probabilities may shrink to 1/2ⁿ; collapses thin them out.
- **Castling** requires a king/rook that has *never* moved or split (`Piece.has_moved`), which
  guarantees both are still solid on their home squares. No check concept exists, so there's no
  "can't castle through check" — only occupancy matters. A king may also *split* one branch
  toward the castle square; the rook is never superposed by this.
- **Deferred dials** (documented, not built): symmetric all-ghosts move, equal-`1/n`
  probabilities, exotic promotion/en-passant interactions.

## Known deferred edge cases

- **En passant** against a *superposed* victim pawn isn't offered (only while the victim is
  solid). Flagged in `rules.py::_pawn_dest`.
- A pawn reaching the back rank via a **CONTACT** move (through a collapse, not a plain push)
  does not promote — only the deterministic `RELOCATE`/`CAPTURE_SOLID` cases are wired.
- The seed is chosen by a "reroll" button, not free-text entry.
- Aura colours cycle by `piece_id % 8`, so with many superposed pieces two could coincidentally
  share a colour (cosmetic).
- The mass-plan floating Confirm/Cancel controls overlap the board's bottom-rank squares.

## Working style

Design as **configurable dials** rather than hardcoded choices; **discuss the design before
coding** anything with a rules impact. Playtest findings drive the roadmap — when the user
reports a bug from a real game, capture *what they saw* in `docs/HISTORY.md`, not just the fix.
