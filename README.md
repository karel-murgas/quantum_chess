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
```

See **[ARCHITECTURE.md](ARCHITECTURE.md)** for how the pieces fit together,
and **[docs/ENGINE.md](docs/ENGINE.md)** for the full ruleset and design rationale.

## Documentation map

| File | Purpose |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Module-by-module technical map |
| [docs/ENGINE.md](docs/ENGINE.md) | Engine mechanics in depth — ruleset, dials, collapse, mass move/split, castling, check |
| [docs/UI.md](docs/UI.md) | UI mechanics in depth — rendering pipeline, skins, planning, menu |
| [docs/HISTORY.md](docs/HISTORY.md) | Dated build log — what shipped, why, which playtest prompted it |
| [CLAUDE.md](CLAUDE.md) | Working agreement + invariants for AI-assisted development (Claude Code) |
| [HOW_TO_PLAY.md](HOW_TO_PLAY.md) | Player-facing rules and controls |
| [ONLINE_PLAY.md](ONLINE_PLAY.md) | Design notes for two-player online play (not yet built) |

## Status

The game is playable end to end (pygame UI, save/load, two skins). See
[docs/ENGINE.md](docs/ENGINE.md) for the ruleset and known deferred edge cases.

## License

No license has been chosen yet — all rights reserved by default until one is
added.
