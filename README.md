# Quantum Chess

A hotseat (2 local players, no clock) chess variant: standard chess rules plus
a **superposition / collapse** layer. Pieces can split into probabilistic
"ghosts" instead of just moving, and contact between pieces triggers a random
**collapse** that reveals where a piece really was.

You still win the classic way — **capture the enemy king** — there's no
check/checkmate concept; the quantum layer sits on top of ordinary chess
movement, not instead of it.

## Features

- Full standard-chess movement (via [`python-chess`](https://python-chess.readthedocs.io/)
  as the movement oracle), plus:
  - **Split** a piece into two probabilistic ghosts instead of moving it.
  - **Path collapse** — sliding through a ghost measures it on the way.
  - Two collapse modes (**Partial** / **Full**) controlling what happens to a
    piece's other ghosts when one is ruled out.
  - **Castling**, en passant, and promotion, adapted to work with ghosts.
  - Optional **mass movement** dial: move every ghost of a superposed piece in
    one planned turn, resolved by a single dice roll.
  - An advisory **check-probability overlay** — shows how likely a king is to
    be captured next turn (purely informational, doesn't restrict moves).
- A pygame UI with two switchable visual themes/skins, click-to-select
  move/split, a promotion picker, an animated collapse reveal (slide → flash →
  fade/shatter), save/load, and an in-game settings screen.
- A **headless engine** (`quantumchess/`, no `pygame` import) that is fully
  unit-tested independent of the UI.

## Install & run

```bash
pip install -r requirements.txt
python main.py
```

The pre-game menu lets you pick the collapse mode, whether splitting/mass
moves are enabled, board theme, team names/colours, and RNG seed.

See **[HOW_TO_PLAY.md](HOW_TO_PLAY.md)** for the full player-facing rules and
controls.

## Tests

```bash
python -m pytest -q
```

UI tests drive the pygame app headlessly and need a dummy video driver (set
automatically by `tests/test_m4_ui.py`, but harmless to also export yourself):

```bash
SDL_VIDEODRIVER=dummy python -m pytest -q
```

## Project layout

```
quantumchess/        # headless engine — model, rules, collapse, check, persistence
quantumchess/ui/      # pygame layer (the only place pygame is imported)
quantumchess/ui/skins/# the two switchable visual themes (HUD, Clarity)
tests/                # pytest suite for engine + UI
main.py               # entry point: python main.py
demo_m1.py..demo_m3.py# headless milestone demos (no pygame needed)
```

See **[ARCHITECTURE.md](ARCHITECTURE.md)** for how the pieces fit together,
and **[PLAN.md](PLAN.md)** for the full ruleset and design rationale.

## Documentation map

| File | Purpose |
|---|---|
| [PLAN.md](PLAN.md) | Living design spec — locked rules, dials, milestones |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Module-by-module technical map |
| [CLAUDE.md](CLAUDE.md) | Detailed engineering log for AI-assisted development (Claude Code) |
| [HOW_TO_PLAY.md](HOW_TO_PLAY.md) | Player-facing rules and controls |
| [UI_REDESIGN.md](UI_REDESIGN.md) | History of the UI skin redesign playtest |
| [ONLINE_PLAY.md](ONLINE_PLAY.md) | Design notes for two-player online play (not yet built) |
| [options.md](options.md) | Original design-dial brainstorm |

## Status

All milestones through M4 (playable pygame UI) are complete; see
[PLAN.md](PLAN.md) for the milestone checklist and known deferred edge cases.

## License

No license has been chosen yet — all rights reserved by default until one is
added.
