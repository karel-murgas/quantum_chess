# Architecture

A quick technical map of the codebase. For the full rationale behind every
design decision (and a detailed history of how each piece was built), see
[CLAUDE.md](CLAUDE.md) — this file is the short version for getting oriented.

## The hard rule

**`quantumchess/` (the engine) never imports `pygame`.** `quantumchess/ui/` is
the only place that does. This keeps the quantum logic fully unit-testable
headless and leaves the door open to a non-pygame frontend later.

## Engine (`quantumchess/`)

| Module | Responsibility |
|---|---|
| `model.py` | `Piece`, `Ghost`, `QuantumBoard`. Probabilities are exact `Fraction`s. `to_classical_board()` projects a *solid* position onto a `python-chess` board — used as the movement oracle and for ASCII rendering. |
| `rules.py` | `Move`/`MoveKind`/`Split`/`MassMove`, `generate_moves` (pseudo-legal, via `python-chess` attack tables over solids), `apply_move`, `apply_split`, `legal_split_targets`. Occupancy invariant: **≤1 ghost per square** per piece; a different piece's ghost on the same square is a `CONTACT` that needs a collapse. |
| `collapse.py` | The measurement/collapse engine. `resolve_move` / `resolve_split` / `resolve_mass_move`. Measurement only happens on collision (relocating to an empty square is instant, no dice). Returns a `CollapseEvent` log the UI animates from. |
| `config.py` | `GameConfig` — the match dials (collapse mode, splitting on/off, mass movement on/off, seed, theme, team names/colours). Split out from `game.py` so `collapse.py` can import it without a circular dependency. |
| `check.py` | Advisory (non-rule-changing) check-probability overlay: `check_probability`, `move_self_check`. Exact `Fraction` math, no RNG — the *expected* danger, not a rolled outcome. |
| `game.py` | `random_selfplay` — the classical-only M1 driver used by early tests/demos. |
| `persistence.py` | JSON save/load (`save_game`/`load_game`), including RNG state so a resumed game's future collapses continue the same sequence. Separate `save_teams`/`load_teams` for cosmetic team identity. |
| `textview.py` | Headless ASCII board renderer (used by the `demo_*.py` scripts). |

## UI (`quantumchess/ui/`)

| Module | Responsibility |
|---|---|
| `app.py` | `App` — the click-driven interaction loop: select → move/split/mass-move plan → collapse animation. Owns save/load, settings, skin switching. |
| `animation.py` | Pygame-free animation *model* — turns a resolved move/collapse into a `Beat` script (travel, then one flash per measurement). Unit-tested headlessly. |
| `render.py` | Pure drawing functions — board, tokens, highlights, side panel, animation beats. Nothing here mutates state. |
| `menu.py` | Pre-game dial picker; reused mid-game as the in-game **Settings** screen (`in_game=True`). |
| `theme.py` | Palette + glyph constants for the two board themes (origin/cyberpunk) and their narration terminology (`TERMS`). |
| `skins/` | Two swappable full-UI visual languages — **Quantum HUD** (`hud.py`) and **Clarity** (`clarity.py`) — sharing a common contract in `base.py`. Switch live mid-match (Tab). |

## Entry points

- `python main.py` — menu, then the real game.
- `python demo_m1.py` / `demo_m2.py` / `demo_m3.py [seed]` — headless ASCII
  demos of each milestone's mechanics, no pygame required.

## Tests (`tests/`)

Plain `pytest` against the headless engine, plus UI tests that drive `App`
headlessly under `SDL_VIDEODRIVER=dummy` with simulated clicks. Run:

```bash
python -m pytest -q
```

## Where to look for more detail

- **Why a rule works the way it does, and its full history** → [CLAUDE.md](CLAUDE.md)
  (maintained as a running engineering log across sessions).
- **The ruleset itself, dials, and milestone plan** → [PLAN.md](PLAN.md).
- **Player-facing controls** → [HOW_TO_PLAY.md](HOW_TO_PLAY.md).
