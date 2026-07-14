# Architecture

A quick technical map of the codebase — the short version, for getting oriented.
For the mechanics in depth see [docs/ENGINE.md](docs/ENGINE.md) and
[docs/UI.md](docs/UI.md); for why each piece was built the way it was, see
[docs/HISTORY.md](docs/HISTORY.md).

## The hard rule

**`quantumchess/` (the engine) never imports `pygame`.** `quantumchess/ui/` is
the only place that does. This keeps the quantum logic fully unit-testable
headless and leaves the door open to a non-pygame frontend later.

## Engine (`quantumchess/`)

| Module | Responsibility |
|---|---|
| `model.py` | `Piece`, `Ghost`, `QuantumBoard`. Probabilities are exact `Fraction`s. `to_classical_board()` projects a *solid* position onto a `python-chess` board — used as the movement oracle and for ASCII rendering. |
| `rules.py` | `Move`/`MoveKind`/`Split`/`MassMove`/`MassSplit`, `generate_moves` (pseudo-legal, via `python-chess` attack tables over solids), `apply_move`, `apply_split`, `legal_split_targets`, castling. Occupancy invariant: **≤1 ghost per square**; a different piece's ghost on the same square is a `CONTACT` that needs a collapse. |
| `collapse.py` | The measurement/collapse engine. `resolve_move` / `resolve_split` / `resolve_mass_move` / `resolve_mass_split`. Measurement only happens on collision (relocating to an empty square is instant, no dice). Returns a `CollapseEvent` log the UI animates from. |
| `config.py` | `GameConfig` — the match dials (collapse mode, splitting, mass movement, mass split, seed) plus the cosmetic match identity (theme, team names/colours, per-team piece sets). Split out from `game.py` so `collapse.py` can import it without a circular dependency. |
| `check.py` | Advisory (non-rule-changing) check-probability overlay: `check_probability`, `move_self_check`. Exact `Fraction` math, no RNG — the *expected* danger, not a rolled outcome. |
| `game.py` | `random_selfplay` — the classical-only M1 driver used by early tests/demos. |
| `persistence.py` | JSON save/load (`save_game`/`load_game`), including RNG state so a resumed game's future collapses continue the same sequence. Separate `save_teams`/`load_teams` for cosmetic team identity. |
| `textview.py` | Headless ASCII board renderer (used by the `demo_*.py` scripts). |

## UI (`quantumchess/ui/`)

| Module | Responsibility |
|---|---|
| `app.py` | `App` — the click-driven interaction loop: select → move/split/mass-move plan → collapse animation. Owns save/load, settings, skin switching. |
| `animation.py` | Pygame-free animation *model* — turns a resolved move/collapse into a `Beat` script (travel, then one flash per measurement). Unit-tested headlessly. |
| `render.py` | Pure drawing primitives — board, tokens, highlights, animation beats, plan overlay. Nothing here mutates state. |
| `pieces.py` | The piece-set registry/renderer (`cburnett`/`merida` SVGs, the generated `neon` set, the traced `tiger` set, `unicode` glyphs). The set is chosen **per team**. |
| `present.py` | Physical-window presentation — everything draws onto an offscreen logical surface at `theme.SCALE`× and is smooth-scaled to a resizable/fullscreen window (free SSAA). Maps clicks back with `to_logical`. |
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

- **How a mechanism actually works** → [docs/ENGINE.md](docs/ENGINE.md) /
  [docs/UI.md](docs/UI.md).
- **Why it works that way, and when it landed** → [docs/HISTORY.md](docs/HISTORY.md).
- **The invariants you must not break** → [CLAUDE.md](CLAUDE.md).
- **The ruleset itself, dials, and milestone plan** → [PLAN.md](PLAN.md).
- **Player-facing controls** → [HOW_TO_PLAY.md](HOW_TO_PLAY.md).
