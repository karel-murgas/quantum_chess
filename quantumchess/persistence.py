"""Save/load game state to/from JSON.

Headless (no pygame import) so it stays unit-testable like the rest of the
engine. Captures everything needed to resume a game byte-exact: the board
(pieces + ghosts, probabilities as exact Fractions), the match config dials,
and the RNG's internal state -- so future collapses continue the same random
sequence as if the game had never been closed.

UI-transient state (current selection, in-progress split picker, the collapse
animation reveal queue) is deliberately *not* part of the save format: `qb` is
already fully resolved the instant a move is applied, so none of that is
needed to correctly resume play.
"""

from __future__ import annotations

import json
import random
from fractions import Fraction
from pathlib import Path
from typing import Any

from .config import CollapseMode, GameConfig
from .model import Ghost, Piece, QuantumBoard

SAVE_FORMAT_VERSION = 1


def _frac_to_list(f: Fraction) -> list[int]:
    return [f.numerator, f.denominator]


def _frac_from_list(pair: list[int]) -> Fraction:
    return Fraction(pair[0], pair[1])


def to_dict(qb: QuantumBoard, config: GameConfig, rng: random.Random,
           mode: str, log: list[str]) -> dict[str, Any]:
    """Snapshot everything needed to resume the game, as plain JSON-safe data."""
    return {
        "version": SAVE_FORMAT_VERSION,
        "board": {
            "pieces": [
                {"id": p.id, "color": p.color, "ptype": p.ptype, "alive": p.alive,
                 "has_moved": p.has_moved}
                for p in qb.pieces.values()
            ],
            "ghosts": [
                {"piece_id": g.piece_id, "square": g.square, "prob": _frac_to_list(g.prob)}
                for g in qb.ghosts
            ],
            "turn": qb.turn,
            "ep_square": qb.ep_square,
            "winner": qb.winner,
            "game_over": qb.game_over,
            "next_id": qb._next_id,
        },
        "config": {
            "collapse_mode": config.collapse_mode.value,
            "splitting_enabled": config.splitting_enabled,
            "mass_movement": config.mass_movement,
            "seed": config.seed,
            "theme": config.theme,
            "white_piece_set": config.white_piece_set,
            "black_piece_set": config.black_piece_set,
            "white_name": config.white_name,
            "black_name": config.black_name,
            "white_color": list(config.white_color),
            "black_color": list(config.black_color),
        },
        "rng_state": rng.getstate(),
        "mode": mode,
        "log": list(log),
    }


def from_dict(data: dict[str, Any]) -> tuple[QuantumBoard, GameConfig, random.Random, str, list[str]]:
    """Inverse of ``to_dict``: rebuild (board, config, rng, mode, log)."""
    version = data.get("version")
    if version != SAVE_FORMAT_VERSION:
        raise ValueError(f"unsupported save format version: {version!r}")

    board_data = data["board"]
    qb = QuantumBoard()
    for pd in board_data["pieces"]:
        qb.pieces[pd["id"]] = Piece(id=pd["id"], color=pd["color"],
                                    ptype=pd["ptype"], alive=pd["alive"],
                                    has_moved=pd.get("has_moved", False))
    qb.ghosts = [
        Ghost(piece_id=gd["piece_id"], square=gd["square"], prob=_frac_from_list(gd["prob"]))
        for gd in board_data["ghosts"]
    ]
    qb.turn = board_data["turn"]
    qb.ep_square = board_data["ep_square"]
    qb.winner = board_data["winner"]
    qb.game_over = board_data["game_over"]
    qb._next_id = board_data["next_id"]

    cfg_data = data["config"]
    default_config = GameConfig()
    config = GameConfig(
        collapse_mode=CollapseMode(cfg_data["collapse_mode"]),
        splitting_enabled=cfg_data["splitting_enabled"],
        mass_movement=cfg_data.get("mass_movement", default_config.mass_movement),
        seed=cfg_data["seed"],
        theme=cfg_data.get("theme", default_config.theme),
        # Migrate the old single "piece_set" key: use it for both sides if the
        # per-team keys are absent (a save from before per-team sets existed).
        white_piece_set=cfg_data.get("white_piece_set",
                                     cfg_data.get("piece_set", default_config.white_piece_set)),
        black_piece_set=cfg_data.get("black_piece_set",
                                     cfg_data.get("piece_set", default_config.black_piece_set)),
        white_name=cfg_data.get("white_name", default_config.white_name),
        black_name=cfg_data.get("black_name", default_config.black_name),
        white_color=tuple(cfg_data.get("white_color", default_config.white_color)),
        black_color=tuple(cfg_data.get("black_color", default_config.black_color)),
    )

    rng = random.Random()
    rng_version, internal_state, gauss_next = data["rng_state"]
    rng.setstate((rng_version, tuple(internal_state), gauss_next))

    return qb, config, rng, data["mode"], list(data["log"])


def save_game(path, qb: QuantumBoard, config: GameConfig, rng: random.Random,
             mode: str, log: list[str]) -> None:
    data = to_dict(qb, config, rng, mode, log)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_game(path) -> tuple[QuantumBoard, GameConfig, random.Random, str, list[str]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return from_dict(data)


# --- Team setup (menu-layer cosmetic identity) -----------------------------
#
# A "team setup" is just the match's cosmetic identity -- the board theme plus
# each side's name and accent colour. Persisted on its own (separate from a
# full game save) so players can reuse a favourite team look across matches
# without retyping names / repicking colours in the menu each time. Headless
# and pygame-free like the rest of this module; the menu drives it directly
# from its own fields rather than round-tripping a GameConfig.

TEAMS_FORMAT_VERSION = 1


def save_teams(path, *, theme: str, white_name: str, black_name: str,
               white_color, black_color,
               white_piece_set: str = "cburnett", black_piece_set: str = "cburnett") -> None:
    data = {
        "version": TEAMS_FORMAT_VERSION,
        "theme": theme,
        "white_piece_set": white_piece_set,
        "black_piece_set": black_piece_set,
        "white_name": white_name,
        "black_name": black_name,
        "white_color": list(white_color),
        "black_color": list(black_color),
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_teams(path) -> dict[str, Any]:
    """Return {theme, white_piece_set, black_piece_set, white_name, black_name,
    white_color, black_color}.

    Colours come back as plain (r, g, b) tuples. Raises ``ValueError`` on an
    unrecognized format version, like ``load_game``. The per-team piece sets
    fall back to the old single "piece_set" key (or "cburnett") for team files
    written before per-team sets existed -- a grow-only schema change, so no
    version bump, same precedent as the theme fields.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    version = data.get("version")
    if version != TEAMS_FORMAT_VERSION:
        raise ValueError(f"unsupported teams format version: {version!r}")
    old_set = data.get("piece_set", "cburnett")
    return {
        "theme": data["theme"],
        "white_piece_set": data.get("white_piece_set", old_set),
        "black_piece_set": data.get("black_piece_set", old_set),
        "white_name": data["white_name"],
        "black_name": data["black_name"],
        "white_color": tuple(data["white_color"]),
        "black_color": tuple(data["black_color"]),
    }
