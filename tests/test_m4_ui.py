"""Milestone 4 tests: UI interaction logic, driven headlessly (SDL dummy driver).

These simulate clicks by calling App.handle_mouse_down() directly with pixel
coordinates computed from render.square_rect() -- no real window or display
needed, but real pygame Surface/font machinery runs underneath.
"""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from fractions import Fraction

import chess
import pygame
import pytest

from quantumchess.config import CollapseMode, GameConfig
from quantumchess.model import Ghost
from quantumchess.ui import render, theme
from quantumchess.ui.animation import Beat
from quantumchess.ui.app import App
from quantumchess.ui.menu import Menu

pygame.init()
_SCREEN = pygame.display.set_mode((theme.WINDOW_W, theme.WINDOW_H))


def _click(app, square):
    app.handle_mouse_down(render.square_rect(square).center)


def _new_app(**overrides):
    kwargs = dict(collapse_mode=CollapseMode.FULL, splitting_enabled=True, seed=0)
    kwargs.update(overrides)
    return App(_SCREEN, GameConfig(**kwargs))


# ------------------------------------------------------------------- moves
def test_select_then_move_executes_and_advances_turn():
    app = _new_app()
    _click(app, chess.E2)
    assert app.selected == chess.E2

    _click(app, chess.E4)
    assert app.selected is None
    assert app.qb.turn == chess.BLACK
    assert app.qb.piece_id_at(chess.E4) is not None
    assert app.qb.piece_id_at(chess.E2) is None
    assert len(app.log) == 1


def test_clicking_selected_square_again_deselects():
    app = _new_app()
    _click(app, chess.E2)
    assert app.selected == chess.E2
    _click(app, chess.E2)
    assert app.selected is None


def test_clicking_illegal_square_reselects_or_clears():
    app = _new_app()
    _click(app, chess.E2)
    _click(app, chess.D2)          # another own pawn, not a legal e2 destination
    assert app.selected == chess.D2

    _click(app, chess.D4)          # legal move for the newly selected pawn
    assert app.qb.piece_id_at(chess.D4) is not None
    assert app.selected is None


def test_clicking_empty_irrelevant_square_clears_selection():
    app = _new_app()
    _click(app, chess.E2)
    _click(app, chess.H5)          # not a legal destination, not an own ghost
    assert app.selected is None


# ------------------------------------------------------------------- split
def test_split_two_clicks_creates_two_ghosts():
    app = _new_app()
    app.toggle_mode()               # toggling clears selection, so do it first
    assert app.mode == "split"
    _click(app, chess.B1)          # knight

    _click(app, chess.A3)
    assert app.split_pick_a == chess.A3

    _click(app, chess.C3)
    assert app.split_pick_a is None
    assert app.selected is None

    knight_id = None
    for pid, piece in app.qb.pieces.items():
        if piece.ptype == chess.KNIGHT and piece.color == chess.WHITE and app.qb.ghosts_of(pid):
            squares = {g.square for g in app.qb.ghosts_of(pid)}
            if squares == {chess.A3, chess.C3}:
                knight_id = pid
    assert knight_id is not None
    ghosts = app.qb.ghosts_of(knight_id)
    assert {g.prob for g in ghosts} == {Fraction(1, 2)}
    assert app.qb.turn == chess.BLACK


def test_split_pick_a_reclick_cancels():
    app = _new_app()
    app.toggle_mode()
    _click(app, chess.B1)
    _click(app, chess.A3)
    assert app.split_pick_a == chess.A3
    _click(app, chess.A3)          # re-click cancels the pick
    assert app.split_pick_a is None
    assert app.qb.turn == chess.WHITE   # nothing was consumed


def test_split_can_pick_source_square_as_one_branch():
    app = _new_app()
    app.toggle_mode()
    _click(app, chess.B1)          # knight
    assert chess.B1 in app._legal_by_square()   # own square offered as a target

    _click(app, chess.B1)          # first branch: stay put
    assert app.split_pick_a == chess.B1

    _click(app, chess.A3)          # second branch: move
    assert app.split_pick_a is None
    assert app.selected is None

    knight_id = None
    for pid, piece in app.qb.pieces.items():
        if piece.ptype == chess.KNIGHT and piece.color == chess.WHITE and app.qb.ghosts_of(pid):
            squares = {g.square for g in app.qb.ghosts_of(pid)}
            if squares == {chess.B1, chess.A3}:
                knight_id = pid
    assert knight_id is not None
    ghosts = app.qb.ghosts_of(knight_id)
    assert {g.prob for g in ghosts} == {Fraction(1, 2)}
    assert app.qb.turn == chess.BLACK


def test_toggle_mode_respects_splitting_disabled():
    app = _new_app(splitting_enabled=False)
    app.toggle_mode()
    assert app.mode == "move"


def test_split_stay_disabled_withholds_source_square():
    app = _new_app(split_stay_enabled=False)
    app.toggle_mode()
    _click(app, chess.B1)          # knight
    assert chess.B1 not in app._legal_by_square()   # own square no longer offered

    _click(app, chess.A3)          # first branch: move
    assert app.split_pick_a == chess.A3
    _click(app, chess.B1)          # not a legal second branch -- re-selects the ghost instead
    assert app.selected == chess.B1
    assert app.split_pick_a is None
    assert app.qb.turn == chess.WHITE               # nothing was consumed


# -------------------------------------------------------------- promotion
def test_promotion_picker_then_choice_executes():
    app = _new_app()
    black_pawn_id = app.qb.piece_id_at(chess.E7)
    app.qb.pieces[black_pawn_id].alive = False
    app.qb.ghosts = [g for g in app.qb.ghosts if g.piece_id != black_pawn_id]
    black_king_id = app.qb.piece_id_at(chess.E8)
    app.qb.ghosts_of(black_king_id)[0].square = chess.E5   # vacate e8 for the promotion

    pawn_id = app.qb.piece_id_at(chess.E2)
    app.qb.ghosts_of(pawn_id)[0].square = chess.E7

    _click(app, chess.E7)
    assert app.selected == chess.E7
    _click(app, chess.E8)
    assert app._pending_promotion is not None
    assert app.qb.turn == chess.WHITE          # not yet resolved

    rook_rect_center = render.promotion_rects()[chess.ROOK].center
    app.handle_mouse_down(rook_rect_center)

    assert app._pending_promotion is None
    assert app.qb.turn == chess.BLACK
    assert app.qb.pieces[pawn_id].ptype == chess.ROOK
    assert app.qb.ghosts_of(pawn_id)[0].square == chess.E8


# ------------------------------------------------------------------ animation
def test_animation_drains_beats_over_time_and_blocks_input():
    app = _new_app()
    app._beats = [Beat(duration_ms=500), Beat(duration_ms=500)]
    assert app.is_animating()

    app.update(499)
    assert len(app._beats) == 2      # not yet time to advance

    app.update(2)                    # first beat done
    assert len(app._beats) == 1

    app.update(500)                  # second beat done
    assert len(app._beats) == 0
    assert not app.is_animating()

    _click(app, chess.E2)            # normal input resumes
    assert app.selected == chess.E2


def test_one_frame_can_drain_several_short_beats():
    app = _new_app()
    app._beats = [Beat(duration_ms=120), Beat(duration_ms=120), Beat(duration_ms=120)]
    app.update(1000)                 # a long frame flushes them all
    assert not app.is_animating()


def test_winning_animation_cannot_be_skipped_via_new_game_click():
    app = _new_app()
    app.qb.game_over = True
    app.qb.winner = chess.WHITE
    app._beats = [Beat(duration_ms=500), Beat(duration_ms=500)]

    # First click on the New Game button lands on the reveal, not the button:
    # it flushes the animation rather than starting a new game.
    app.handle_mouse_down(app.skin.panel_rects()["new_game"].center)
    assert not app.is_animating()
    assert app.qb.game_over            # New Game was NOT triggered by that click

    # Only once the reveal is done does the same click actually start a new game.
    app.handle_mouse_down(app.skin.panel_rects()["new_game"].center)
    assert not app.qb.game_over


def test_click_during_animation_skips_it():
    app = _new_app()
    app._beats = [Beat(duration_ms=500), Beat(duration_ms=500)]
    _click(app, chess.A1)          # any click flushes the whole animation
    assert not app.is_animating()


# ------------------------------------------------------------------ game over
def test_game_over_blocks_all_input():
    app = _new_app()
    app.qb.game_over = True
    app.qb.winner = chess.WHITE
    _click(app, chess.E2)
    assert app.selected is None
    assert app.qb.turn == chess.WHITE


def test_new_game_button_resets_after_game_over():
    app = _new_app()
    _click(app, chess.E2)
    app.qb.game_over = True
    app.qb.winner = chess.WHITE
    app.log.append("** White wins by capturing the king! **")

    app.handle_mouse_down(app.skin.panel_rects()["new_game"].center)

    assert not app.qb.game_over
    assert app.qb.winner is None
    assert app.log == []
    assert app.selected is None
    assert app.qb.turn == chess.WHITE
    assert len(app.qb.pieces) == 32


def test_surrender_requires_a_second_confirm_click():
    app = _new_app()
    surrender_center = app.skin.panel_rects()["surrender"].center

    app.handle_mouse_down(surrender_center)   # arms the confirm, doesn't act yet
    assert not app.qb.game_over
    assert app._confirm_surrender

    app.handle_mouse_down(surrender_center)   # second click actually surrenders
    assert app.qb.game_over
    assert app.qb.winner == chess.BLACK       # White was to move and gave up
    assert not app._confirm_surrender
    assert any("resign" in line.lower() for line in app.log)
    assert any("wins" in line.lower() for line in app.log)


def test_surrender_confirm_is_cancelled_by_any_other_click():
    app = _new_app()
    app.handle_mouse_down(app.skin.panel_rects()["surrender"].center)
    assert app._confirm_surrender

    _click(app, chess.E2)   # an unrelated click backs out instead of surrendering
    assert not app._confirm_surrender
    assert not app.qb.game_over
    assert app.selected is None   # the click that cancelled confirm wasn't itself acted on


def test_surrender_confirm_is_cancelled_by_escape():
    app = _new_app()
    app.handle_mouse_down(app.skin.panel_rects()["surrender"].center)
    assert app._confirm_surrender

    app.cancel_selection()
    assert not app._confirm_surrender
    assert not app.qb.game_over


def test_surrender_button_does_nothing_once_game_is_over():
    app = _new_app()
    app.qb.game_over = True
    app.qb.winner = chess.WHITE

    app.handle_mouse_down(app.skin.panel_rects()["surrender"].center)

    assert not app._confirm_surrender
    assert app.qb.winner == chess.WHITE   # untouched


def test_cancel_selection_backs_out_without_acting():
    app = _new_app()
    _click(app, chess.E2)
    assert app.selected == chess.E2
    app.cancel_selection()
    assert app.selected is None
    assert app.qb.turn == chess.WHITE   # nothing was played

    app.toggle_mode()
    _click(app, chess.B1)
    _click(app, chess.A3)
    assert app.split_pick_a == chess.A3
    app.cancel_selection()
    assert app.split_pick_a is None
    assert app.selected == chess.B1     # cancel unwinds one step at a time


# -------------------------------------------------------------- mode button
def test_mode_button_click_toggles_and_is_disabled_when_splitting_off():
    app = _new_app()
    app.handle_mouse_down(app.skin.panel_rects()["mode"].center)
    assert app.mode == "split"
    app.handle_mouse_down(app.skin.panel_rects()["mode"].center)
    assert app.mode == "move"

    app2 = _new_app(splitting_enabled=False)
    app2.handle_mouse_down(app2.skin.panel_rects()["mode"].center)
    assert app2.mode == "move"


# -------------------------------------------------------- removed-pieces tray
def test_captured_button_toggles_show_captured():
    app = _new_app()
    assert app.show_captured is True
    app.handle_mouse_down(app.skin.panel_rects()["captured"].center)
    assert app.show_captured is False
    app.handle_mouse_down(app.skin.panel_rects()["captured"].center)
    assert app.show_captured is True


def test_captured_button_works_even_after_game_over():
    app = _new_app()
    app.qb.game_over = True
    app.qb.winner = chess.WHITE
    app.handle_mouse_down(app.skin.panel_rects()["captured"].center)
    assert app.show_captured is False


def test_draw_with_removed_pieces_does_not_crash():
    app = _new_app()
    pawn_id = app.qb.piece_id_at(chess.E7)
    app.qb.pieces[pawn_id].alive = False
    app.qb.ghosts = [g for g in app.qb.ghosts if g.piece_id != pawn_id]
    app.draw()          # tray shown, with one removed piece to render
    app.toggle_captured()
    app.draw()          # tray hidden


# ------------------------------------------------------------ contact via UI
def test_contact_move_through_ui_updates_log_and_board():
    app = _new_app()
    rook_id = app.qb.piece_id_at(chess.A1)
    app.qb.ghosts_of(rook_id)[0].square = chess.A1  # keep rook solid at a1
    # remove the a-file pawn so the rook's path up the file is open, then
    # place a superposed black bishop ghost on that file to force CONTACT.
    a_pawn_id = app.qb.piece_id_at(chess.A2)
    app.qb.pieces[a_pawn_id].alive = False
    app.qb.ghosts = [g for g in app.qb.ghosts if g.piece_id != a_pawn_id]

    bishop_id = app.qb.piece_id_at(chess.C8)
    app.qb.ghosts_of(bishop_id)[0].square = chess.A4
    app.qb.ghosts_of(bishop_id)[0].prob = Fraction(1, 2)
    app.qb.ghosts.append(Ghost(bishop_id, chess.H4, Fraction(1, 2)))

    _click(app, chess.A1)
    legal = app._legal_by_square()
    assert legal.get(chess.A4) == "contact"

    _click(app, chess.A4)
    assert len(app.log) == 1
    # The rook is solid (prob=1) so it can't fizzle; the only randomness is
    # whether the bishop ghost was really on a4 -- either way the turn advances.
    assert app.qb.turn == chess.BLACK


# --------------------------------------------------------------- save / load
def test_save_to_then_load_from_round_trips_state(tmp_path):
    app = _new_app()
    save_path = tmp_path / "quicksave.json"

    _click(app, chess.E2)
    _click(app, chess.E4)          # some actual history to distinguish from fresh
    saved_log = list(app.log)      # the log *before* the "saved to" note gets appended
    saved_turn = app.qb.turn
    app.save_to(save_path)
    assert save_path.exists()

    app.new_game()                 # blow away in-memory state
    assert app.qb.turn == chess.WHITE
    assert app.log == []

    app.load_from(save_path)
    assert app.qb.turn == saved_turn
    assert app.qb.piece_id_at(chess.E4) is not None
    assert app.log[:-1] == saved_log   # last entry is the "loaded from" note
    assert app.selected is None and app.split_pick_a is None


def test_save_and_load_panel_buttons_are_clickable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)    # DEFAULT_SAVE_PATH is relative -- keep it out of the repo
    app = _new_app()
    _click(app, chess.E2)
    _click(app, chess.E4)

    app.handle_mouse_down(app.skin.panel_rects()["save"].center)
    assert any("saved" in line.lower() for line in app.log)

    app.new_game()
    app.handle_mouse_down(app.skin.panel_rects()["load"].center)
    assert app.qb.piece_id_at(chess.E4) is not None


def test_load_from_missing_file_logs_error_without_crashing(tmp_path):
    app = _new_app()
    app.load_from(tmp_path / "does-not-exist.json")
    assert any("couldn't load" in line.lower() for line in app.log)
    assert app.qb.turn == chess.WHITE   # untouched -- load failed cleanly


# ------------------------------------------------------------------- menu
def test_menu_defaults_from_last_saved_teams(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)    # Menu.TEAMS_SAVE_PATH is relative -- keep it out of the repo
    saver = Menu(_SCREEN)
    saver.theme_name = "cyberpunk"
    saver.white_name = "Alpha"
    saver.black_name = "Beta"
    saver.white_color = theme.SWATCHES[1]
    saver.black_color = theme.SWATCHES[2]
    saver._save_teams()

    fresh = Menu(_SCREEN)
    assert fresh.theme_name == "cyberpunk"
    assert fresh.white_name == "Alpha"
    assert fresh.black_name == "Beta"
    assert fresh.white_color == theme.SWATCHES[1]
    assert fresh.black_color == theme.SWATCHES[2]
    assert fresh.team_status == ""   # silent on startup, unlike an explicit Load click


def test_menu_defaults_stay_hardcoded_without_a_saved_teams_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fresh = Menu(_SCREEN)
    assert fresh.theme_name == "origin"
    assert fresh.white_name == "White"
    assert fresh.black_name == "Black"


# ---------------------------------------------------- dial toggle visibility
def test_mass_toggle_hidden_when_splitting_off():
    m = Menu(_SCREEN)
    m.splitting_enabled = False
    keys = {key for key, _label, _active in m._dial_specs()}
    assert keys == {"split"}
    assert "mass" not in m._dial_rects()
    assert "mass_split" not in m._dial_rects()


def test_mass_split_toggle_hidden_when_mass_moves_off():
    m = Menu(_SCREEN)
    m.splitting_enabled = True
    m.mass_movement = False
    keys = {key for key, _label, _active in m._dial_specs()}
    assert keys == {"split", "split_stay", "mass"}
    assert "mass_split" not in m._dial_rects()


def test_all_toggles_visible_when_everything_on():
    m = Menu(_SCREEN)
    m.splitting_enabled = True
    m.mass_movement = True
    m.mass_split = True
    m.mass_all_must_act = True
    keys = {key for key, _label, _active in m._dial_specs()}
    assert keys == {"split", "split_stay", "mass", "mass_split", "mass_all_must_act"}


def test_all_must_act_toggle_hidden_when_mass_moves_off():
    m = Menu(_SCREEN)
    m.splitting_enabled = True
    m.mass_movement = False
    keys = {key for key, _label, _active in m._dial_specs()}
    assert "mass_all_must_act" not in keys
    assert "mass_all_must_act" not in m._dial_rects()


def test_turning_off_splitting_cascades_off_mass_and_mass_split():
    m = Menu(_SCREEN)
    m.splitting_enabled = True
    m.mass_movement = True
    m.mass_split = True
    m.mass_all_must_act = True
    rects = m._dial_rects()
    m.handle_click(rects["split"].center)   # toggle Splitting off
    assert m.splitting_enabled is False
    assert m.mass_movement is False
    assert m.mass_split is False
    assert m.mass_all_must_act is False


def test_turning_off_mass_moves_cascades_off_mass_split_and_all_must_act():
    m = Menu(_SCREEN)
    m.splitting_enabled = True
    m.mass_movement = True
    m.mass_split = True
    m.mass_all_must_act = True
    rects = m._dial_rects()
    m.handle_click(rects["mass"].center)   # toggle Mass moves off
    assert m.mass_movement is False
    assert m.mass_split is False
    assert m.mass_all_must_act is False


def test_mass_all_must_act_toggle_flips_and_reaches_build_config():
    m = Menu(_SCREEN)
    m.splitting_enabled = True
    m.mass_movement = True
    rects = m._dial_rects()
    m.handle_click(rects["mass_all_must_act"].center)
    assert m.mass_all_must_act is True
    assert m._build_config().mass_all_must_act is True


def test_dial_tree_positions_children_under_their_parent():
    """The mass-split/all-must-act pair should be centered under the Mass
    moves box, not under the whole screen -- confirming the tree layout
    actually branches per-parent instead of just centering every row."""
    m = Menu(_SCREEN)
    m.splitting_enabled = True
    m.mass_movement = True
    m.mass_split = True
    m.mass_all_must_act = True
    rects = m._dial_rects()
    mass_cx = rects["mass"].centerx
    children_cx = (rects["mass_split"].centerx + rects["mass_all_must_act"].centerx) / 2
    assert abs(children_cx - mass_cx) <= 1
    assert rects["mass_split"].top > rects["mass"].bottom
    assert rects["split_stay"].top > rects["split"].bottom


def test_split_stay_toggle_hidden_when_splitting_off():
    m = Menu(_SCREEN)
    m.splitting_enabled = False
    keys = {key for key, _label, _active in m._dial_specs()}
    assert keys == {"split"}
    assert "split_stay" not in m._dial_rects()


def test_split_stay_toggle_flips_independent_of_mass_dials():
    m = Menu(_SCREEN)
    m.splitting_enabled = True
    m.mass_movement = False
    rects = m._dial_rects()
    m.handle_click(rects["split_stay"].center)
    assert m.split_stay_enabled is False
    assert m.mass_movement is False   # unaffected -- split stay has no cascade


def test_turning_off_mass_moves_cascades_off_mass_split():
    m = Menu(_SCREEN)
    m.splitting_enabled = True
    m.mass_movement = True
    m.mass_split = True
    rects = m._dial_rects()
    m.handle_click(rects["mass"].center)    # toggle Mass moves off
    assert m.mass_movement is False
    assert m.mass_split is False
    assert m.splitting_enabled is True      # untouched


def test_clicking_where_a_hidden_toggle_used_to_be_does_nothing_bad():
    """With mass split hidden (mass moves off), a click at the position the
    3rd button would have occupied must not raise or silently flip an
    unrelated dial -- it should just fall through to no-op."""
    m = Menu(_SCREEN)
    m.splitting_enabled = True
    m.mass_movement = False
    rects_three = None
    # compute where "mass_split" *would* be if all three were visible, by
    # temporarily enabling mass_movement
    m.mass_movement = True
    would_be = m._dial_rects()["mass_split"].center
    m.mass_movement = False
    before = (m.splitting_enabled, m.mass_movement, m.mass_split)
    m.handle_click(would_be)
    assert (m.splitting_enabled, m.mass_movement, m.mass_split) == before


# --------------------------------------------------- remembering last settings
def test_start_game_remembers_dials_and_cosmetics_for_next_startup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    m = Menu(_SCREEN)
    m.splitting_enabled = True
    m.mass_movement = True
    m.mass_split = True
    m.collapse_mode = CollapseMode.PARTIAL
    m.theme_name = "cyberpunk"
    m.white_name = "Alice"
    m.black_name = "Bob"
    action, config = m.handle_click(m.start_rect.center)
    assert action == "start"
    assert config.mass_split is True

    fresh = Menu(_SCREEN)
    assert fresh.collapse_mode == CollapseMode.PARTIAL
    assert fresh.splitting_enabled is True
    assert fresh.mass_movement is True
    assert fresh.mass_split is True
    assert fresh.theme_name == "cyberpunk"
    assert fresh.white_name == "Alice"
    assert fresh.black_name == "Bob"


def test_resume_from_in_game_settings_also_remembers_settings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    m = Menu(_SCREEN, in_game=True, initial_config=GameConfig())
    m.mass_movement = True
    action, config = m.handle_click(m.resume_rect.center)
    assert action == "resume"
    assert config.mass_movement is True

    fresh = Menu(_SCREEN)
    assert fresh.mass_movement is True


def test_fresh_menu_falls_back_to_team_save_when_no_last_settings_exist(tmp_path, monkeypatch):
    """Backward compatible with a pre-existing teams.json (cosmetics only, no
    dials) from before this feature existed."""
    monkeypatch.chdir(tmp_path)
    saver = Menu(_SCREEN)
    saver.theme_name = "cyberpunk"
    saver.white_name = "Alpha"
    saver._save_teams()

    fresh = Menu(_SCREEN)
    assert fresh.theme_name == "cyberpunk"
    assert fresh.white_name == "Alpha"
    assert fresh.mass_movement is False   # no last-settings file -- dials stay hardcoded


# --------------------------------------------------------------- in-game settings
def test_open_settings_via_panel_button_and_via_o_key():
    app = _new_app()
    app.handle_mouse_down(app.skin.panel_rects()["settings"].center)
    assert app.in_settings
    assert app.settings_menu is not None
    assert app.settings_menu.in_game

    app.in_settings = False
    app.settings_menu = None
    app.handle_keydown(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_o, unicode="o"))
    assert app.in_settings


def test_settings_blocked_during_animation():
    app = _new_app()
    app._beats = [Beat(duration_ms=500)]
    app.handle_mouse_down(app.skin.panel_rects()["settings"].center)
    assert not app.in_settings   # the click flushed the reveal instead


def test_settings_opens_prefilled_from_the_current_match_config():
    app = _new_app(white_name="Alpha", black_name="Beta")
    app.open_settings()
    assert app.settings_menu.white_name == "Alpha"
    assert app.settings_menu.black_name == "Beta"
    assert app.settings_menu.collapse_mode == app.config.collapse_mode


def test_settings_escape_cancels_without_applying_changes():
    app = _new_app()
    app.open_settings()
    app.settings_menu.white_name = "Changed"
    app.handle_keydown(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, unicode=""))
    assert not app.in_settings
    assert app.settings_menu is None
    assert app.config.white_name == "White"     # untouched


def test_settings_keydown_routes_text_entry_to_the_menu_not_game_hotkeys():
    app = _new_app()
    app.open_settings()
    app.settings_menu.active_field = "white_name"
    app.handle_keydown(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_m, unicode="m"))
    assert app.settings_menu.white_name == "Whitem"   # typed into the field
    assert app.mode == "move"                          # not treated as the (M) hotkey


def test_settings_resume_applies_changes_without_resetting_the_board(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)   # Resume now also auto-saves last-settings -- keep it out of the repo
    app = _new_app()
    _click(app, chess.E2)
    _click(app, chess.E4)
    turn_before = app.qb.turn
    log_before = list(app.log)

    app.open_settings()
    app.settings_menu.white_name = "Alpha"
    app.settings_menu.theme_name = "cyberpunk"
    app._handle_settings_click(app.settings_menu.resume_rect.center)

    assert not app.in_settings
    assert app.settings_menu is None
    assert app.config.white_name == "Alpha"
    assert app.config.theme == "cyberpunk"
    assert app.qb.turn == turn_before
    assert app.qb.piece_id_at(chess.E4) is not None    # board untouched
    assert app.log[:-1] == log_before                  # only the "updated" note appended


def test_settings_new_game_resets_the_board_with_the_edited_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)   # New Game now also auto-saves last-settings -- keep it out of the repo
    app = _new_app()
    _click(app, chess.E2)
    _click(app, chess.E4)

    app.open_settings()
    app.settings_menu.black_name = "Beta"
    app._handle_settings_click(app.settings_menu.start_rect.center)

    assert not app.in_settings
    assert app.config.black_name == "Beta"
    assert app.qb.turn == chess.WHITE
    assert app.qb.piece_id_at(chess.E4) is None
    assert len(app.qb.pieces) == 32
