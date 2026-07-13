"""Save/load round-trip tests (headless, no pygame)."""

from fractions import Fraction

import chess
import pytest

from quantumchess.config import CollapseMode, GameConfig
from quantumchess.model import Ghost, QuantumBoard
from quantumchess.persistence import (
    from_dict, load_game, load_last_settings, load_teams, save_game,
    save_last_settings, save_teams, to_dict,
)
from quantumchess.rules import Split, apply_split


def _superposed_board():
    qb = QuantumBoard.standard_setup()
    bishop_id = qb.piece_id_at(chess.F1)
    qb.ghosts_of(bishop_id)[0].square = chess.D3   # pretend the diagonal's open
    apply_split(qb, Split(bishop_id, chess.D3, chess.C4, chess.A6))
    qb.ep_square = chess.E3
    return qb


def test_round_trip_preserves_has_moved():
    qb = QuantumBoard.standard_setup()
    king_id = qb.piece_id_at(chess.E1)
    qb.pieces[king_id].has_moved = True
    config = GameConfig()
    rng = __import__("random").Random(1)

    data = to_dict(qb, config, rng, "move", [])
    qb2, *_ = from_dict(data)

    assert qb2.pieces[king_id].has_moved is True
    rook_id = qb2.piece_id_at(chess.A1)
    assert qb2.pieces[rook_id].has_moved is False


def test_from_dict_defaults_has_moved_false_for_old_saves():
    qb = QuantumBoard.standard_setup()
    config = GameConfig()
    rng = __import__("random").Random(1)
    data = to_dict(qb, config, rng, "move", [])
    for pd in data["board"]["pieces"]:
        del pd["has_moved"]   # simulate a save written before this field existed

    qb2, *_ = from_dict(data)
    assert all(not p.has_moved for p in qb2.pieces.values())


def test_to_dict_from_dict_round_trips_board_state():
    qb = _superposed_board()
    config = GameConfig(collapse_mode=CollapseMode.PARTIAL, splitting_enabled=True, seed=7,
                        mass_movement=True, mass_split=True,
                        white_piece_set="merida", black_piece_set="neon")
    rng = __import__("random").Random(7)
    rng.random()   # advance state so we can check it's actually preserved, not just re-seeded
    log = ["Black Pawn e7->e5.", "White Bishop splits d3 -> c4 (1/4), a6 (1/4)"]

    data = to_dict(qb, config, rng, "split", log)
    qb2, config2, rng2, mode2, log2 = from_dict(data)

    assert {(g.piece_id, g.square, g.prob) for g in qb2.ghosts} == \
           {(g.piece_id, g.square, g.prob) for g in qb.ghosts}
    assert all(isinstance(g.prob, Fraction) for g in qb2.ghosts)
    assert qb2.turn == qb.turn
    assert qb2.ep_square == qb.ep_square
    assert qb2.game_over == qb.game_over
    assert qb2.winner == qb.winner
    assert {p.id: (p.color, p.ptype, p.alive) for p in qb2.pieces.values()} == \
           {p.id: (p.color, p.ptype, p.alive) for p in qb.pieces.values()}

    assert config2.collapse_mode == config.collapse_mode
    assert config2.splitting_enabled == config.splitting_enabled
    assert config2.mass_movement == config.mass_movement
    assert config2.mass_split == config.mass_split
    assert config2.seed == config.seed
    assert config2.white_piece_set == "merida"
    assert config2.black_piece_set == "neon"

    assert rng2.getstate() == rng.getstate()
    assert mode2 == "split"
    assert log2 == log


def test_save_game_then_load_game_round_trips_via_disk(tmp_path):
    qb = _superposed_board()
    config = GameConfig(collapse_mode=CollapseMode.FULL, splitting_enabled=True, seed=1)
    rng = __import__("random").Random(1)
    log = ["White Pawn e2->e4."]

    path = tmp_path / "nested" / "quicksave.json"   # parent dir doesn't exist yet
    save_game(path, qb, config, rng, "move", log)
    assert path.exists()

    qb2, config2, rng2, mode2, log2 = load_game(path)
    assert {(g.piece_id, g.square, g.prob) for g in qb2.ghosts} == \
           {(g.piece_id, g.square, g.prob) for g in qb.ghosts}
    assert config2.seed == 1
    assert mode2 == "move"
    assert log2 == log


def test_load_game_rejects_unknown_version(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"version": 999}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_game(path)


def test_resumed_rng_continues_same_sequence_as_original():
    """The whole point of persisting rng state: future collapses must draw the
    same sequence they would have if the game were never closed."""
    import random
    rng = random.Random(42)
    rng.random(); rng.random()   # simulate a couple of collapses already resolved

    qb = QuantumBoard.standard_setup()
    config = GameConfig()
    data = to_dict(qb, config, rng, "move", [])
    _, _, resumed_rng, _, _ = from_dict(data)

    expected_next = [rng.random() for _ in range(5)]
    actual_next = [resumed_rng.random() for _ in range(5)]
    assert actual_next == expected_next


def test_save_teams_then_load_teams_round_trips_via_disk(tmp_path):
    path = tmp_path / "nested" / "teams.json"   # parent dir doesn't exist yet
    save_teams(path, theme="cyberpunk", white_piece_set="neon", black_piece_set="merida",
               white_name="Alice", black_name="Bob",
               white_color=(255, 46, 199), black_color=(0, 224, 255))
    assert path.exists()

    data = load_teams(path)
    assert data == {
        "theme": "cyberpunk",
        "white_piece_set": "neon",
        "black_piece_set": "merida",
        "white_name": "Alice",
        "black_name": "Bob",
        "white_color": (255, 46, 199),
        "black_color": (0, 224, 255),
    }
    # colours come back as tuples, not the JSON lists they were stored as
    assert isinstance(data["white_color"], tuple)


def test_load_teams_migrates_old_single_piece_set(tmp_path):
    """A teams file with the old single "piece_set" key applies it to both
    sides; one with neither falls back to cburnett (grow-only schema, no
    version bump)."""
    migrate = tmp_path / "migrate.json"
    migrate.write_text(
        '{"version": 1, "theme": "origin", "piece_set": "merida",'
        ' "white_name": "W", "black_name": "B",'
        ' "white_color": [1, 2, 3], "black_color": [4, 5, 6]}',
        encoding="utf-8")
    data = load_teams(migrate)
    assert data["white_piece_set"] == "merida"
    assert data["black_piece_set"] == "merida"

    ancient = tmp_path / "ancient.json"
    ancient.write_text(
        '{"version": 1, "theme": "origin", "white_name": "W", "black_name": "B",'
        ' "white_color": [1, 2, 3], "black_color": [4, 5, 6]}',
        encoding="utf-8")
    data2 = load_teams(ancient)
    assert data2["white_piece_set"] == "cburnett"
    assert data2["black_piece_set"] == "cburnett"


def test_load_teams_rejects_unknown_version(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"version": 999}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_teams(path)


# ----------------------------------------------------- last-used settings
def test_save_last_settings_then_load_round_trips_via_disk(tmp_path):
    path = tmp_path / "nested" / "last_settings.json"   # parent dir doesn't exist yet
    config = GameConfig(collapse_mode=CollapseMode.PARTIAL, splitting_enabled=True,
                        mass_movement=True, mass_split=True, seed=99,
                        theme="cyberpunk", white_piece_set="neon", black_piece_set="merida",
                        white_name="Alice", black_name="Bob",
                        white_color=(255, 46, 199), black_color=(0, 224, 255))
    save_last_settings(path, config)
    assert path.exists()

    data = load_last_settings(path)
    assert data == {
        "collapse_mode": CollapseMode.PARTIAL,
        "splitting_enabled": True,
        "mass_movement": True,
        "mass_split": True,
        "theme": "cyberpunk",
        "white_piece_set": "neon",
        "black_piece_set": "merida",
        "white_name": "Alice",
        "black_name": "Bob",
        "white_color": (255, 46, 199),
        "black_color": (0, 224, 255),
    }
    # note: seed is deliberately NOT part of last-used settings -- every match
    # still gets a fresh random seed at the menu, so it doesn't round-trip.


def test_load_last_settings_falls_back_to_defaults_for_missing_fields(tmp_path):
    """A grow-only schema: a last-settings file predating a newer dial (e.g.
    mass_split) still loads, just defaulting that field."""
    path = tmp_path / "old.json"
    path.write_text(
        '{"version": 1, "collapse_mode": "full", "splitting_enabled": true,'
        ' "theme": "origin", "white_name": "W", "black_name": "B",'
        ' "white_color": [1, 2, 3], "black_color": [4, 5, 6]}',
        encoding="utf-8")
    data = load_last_settings(path)
    assert data["mass_movement"] is False
    assert data["mass_split"] is False
    assert data["white_piece_set"] == "cburnett"


def test_load_last_settings_rejects_unknown_version(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"version": 999}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_last_settings(path)
