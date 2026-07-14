"""Pre-game match-setup menu -- the v1 dials (see PLAN.md)."""

from __future__ import annotations

import random
from pathlib import Path

import chess
import pygame

from ..config import CollapseMode, GameConfig
from .. import persistence
from . import theme, pieces, render

MAX_NAME_LEN = 16
TEAMS_SAVE_PATH = Path("saves/teams.json")
LAST_SETTINGS_PATH = Path("saves/last_settings.json")


class Menu:
    def __init__(self, screen: pygame.Surface, in_game: bool = False, initial_config=None):
        """``in_game=True`` is how ``App`` reopens this same dial picker mid-match
        (see ``ui/app.py::open_settings``) instead of only pre-game from
        ``main.py``: it shows a Resume button alongside Start (relabeled "New
        Game"), and ``initial_config`` seeds every field from the match's
        *current* ``GameConfig`` instead of the last saved team file, so the
        screen opens showing what's actually in play, not stale defaults.
        """
        self.screen = screen
        self.in_game = in_game
        self.collapse_mode = CollapseMode.FULL
        self.splitting_enabled = True
        self.mass_movement = False
        self.mass_split = False
        self.seed = random.SystemRandom().randrange(1_000_000)

        self.theme_name = "origin"
        self.white_piece_set = "cburnett"
        self.black_piece_set = "cburnett"
        self.white_name = "White"
        self.black_name = "Black"
        self.white_color = theme.DEFAULT_WHITE_COLOR
        self.black_color = theme.DEFAULT_BLACK_COLOR
        self.active_field = None      # "white_name" | "black_name" | None
        self.white_piece_open = False  # is the white piece-set dropdown expanded?
        self.black_piece_open = False

        if initial_config is not None:
            self.collapse_mode = initial_config.collapse_mode
            self.splitting_enabled = initial_config.splitting_enabled
            self.mass_movement = initial_config.mass_movement
            self.mass_split = initial_config.mass_split
            self.seed = initial_config.seed
            self.theme_name = initial_config.theme
            self.white_piece_set = initial_config.white_piece_set
            self.black_piece_set = initial_config.black_piece_set
            self.white_name = initial_config.white_name
            self.black_name = initial_config.black_name
            self.white_color = initial_config.white_color
            self.black_color = initial_config.black_color
        else:
            self._load_startup_defaults()

        self.font_title = pygame.font.SysFont("segoeui", 36, bold=True)
        self.font = pygame.font.SysFont("segoeui", 22)
        self.font_small = pygame.font.SysFont("segoeui", 17)
        # Small symbol font for the "unicode" piece-set preview swatch.
        self.font_glyph = pygame.font.SysFont("segoeuisymbol", 30)

        w, h = self.screen.get_size()
        cx = w // 2
        self.collapse_full_rect = pygame.Rect(cx - 220, 112, 200, 40)
        self.collapse_partial_rect = pygame.Rect(cx + 20, 112, 200, 40)
        # The "Splitting"/"Mass moves"/"Mass split" toggle row is laid out
        # dynamically (see _dial_specs/_dial_rects) -- each toggle is only
        # shown once its prerequisite dial is on, so the row's width (and
        # therefore each button's rect) depends on the current state and can't
        # be fixed up front.

        self.theme_rects = {
            "origin": pygame.Rect(cx - 220, 232, 200, 40),
            "cyberpunk": pygame.Rect(cx + 20, 232, 200, 40),
        }

        self.white_name_rect = pygame.Rect(cx - 320, 300, 300, 34)
        self.black_name_rect = pygame.Rect(cx + 20, 300, 300, 34)
        self.swap_rect = pygame.Rect(cx - 20, 300, 40, 34)

        # Piece-set picker, one dropdown per team (each side chooses its own
        # art), sitting directly under Teams next to that team's colour
        # swatches -- closed it's just a button showing the current set with
        # a small king preview; open it drops a same-width option list below
        # (see _piece_option_rects/_draw_piece_options).
        dd_w, dd_h = 140, 38
        piece_row_y = 364
        self.white_piece_dropdown_rect = pygame.Rect(cx - 320, piece_row_y, dd_w, dd_h)
        self.black_piece_dropdown_rect = pygame.Rect(cx + 20, piece_row_y, dd_w, dd_h)

        self.white_swatch_rects = self._swatch_rects(cx - 320 + dd_w + 20, piece_row_y)
        self.black_swatch_rects = self._swatch_rects(cx + 20 + dd_w + 20, piece_row_y)

        # One row: Save Teams | Reroll seed | Load Teams
        self.team_save_rect = pygame.Rect(cx - 330, 470, 200, 38)
        self.reroll_rect = pygame.Rect(cx - 100, 470, 200, 38)
        self.team_load_rect = pygame.Rect(cx + 130, 470, 200, 38)
        self.team_status = ""       # transient feedback for the last save/load

        # Mid-game, Start doubles as "New Game" (same rect, relabeled) and
        # gains a Resume neighbour so a match's own settings screen can back
        # out without resetting the board. Pre-game there's nothing to resume
        # to, so Start alone stays centered as it always has.
        if self.in_game:
            self.resume_rect = pygame.Rect(cx - 210, 580, 200, 50)
            self.start_rect = pygame.Rect(cx + 10, 580, 200, 50)
        else:
            self.resume_rect = None
            self.start_rect = pygame.Rect(cx - 100, 580, 200, 50)

    def _piece_option_rects(self, dropdown_rect):
        """{set_key -> Rect} for a dropdown's open option list, one row per
        set stacked directly below the button, same width as it."""
        h = 34
        return {key: pygame.Rect(dropdown_rect.x, dropdown_rect.bottom + i * h, dropdown_rect.width, h)
                for i, (key, _label) in enumerate(pieces.PIECE_SETS)}

    @staticmethod
    def _swatch_rects(x0, y0):
        size, gap = 26, 5
        rects = []
        for i, _ in enumerate(theme.SWATCHES):
            col = i % 4
            row = i // 4
            x = x0 + col * (size + gap)
            y = y0 + row * (size + gap)
            rects.append(pygame.Rect(x, y, size, size))
        return rects

    def _dial_specs(self):
        """(key, label, active) for each "Splitting"/"Mass moves"/"Mass split"
        toggle currently visible. Each is **hidden entirely** (not merely
        disabled) once its prerequisite dial is off -- mass movement only
        makes sense with splitting on, and mass split only with mass movement
        on -- so there's nothing to show a player that couldn't apply."""
        specs = [("split", f"Splitting: {'On' if self.splitting_enabled else 'Off'}",
                 self.splitting_enabled)]
        if self.splitting_enabled:
            specs.append(("mass", f"Mass moves: {'On' if self.mass_movement else 'Off'}",
                         self.mass_movement))
            if self.mass_movement:
                specs.append(("mass_split", f"Mass split: {'On' if self.mass_split else 'Off'}",
                             self.mass_split))
        return specs

    def _dial_rects(self):
        """{key -> Rect} for the currently-visible dial toggles (see
        ``_dial_specs``), laid out as a row centered on the same span the
        fixed 3-button row used to occupy. Recomputed live rather than cached
        in ``__init__`` -- which toggles are visible depends on the current
        dial state, so the row's width can change as the player clicks."""
        specs = self._dial_specs()
        w, h, gap = 150, 40, 10
        total = len(specs) * w + (len(specs) - 1) * gap
        cx = self.screen.get_width() // 2
        x0 = cx - total // 2
        y = 164
        return {key: pygame.Rect(x0 + i * (w + gap), y, w, h)
                for i, (key, _label, _active) in enumerate(specs)}

    def _build_config(self):
        # Defensive AND-gating of the dial dependency chain (splitting ->
        # mass movement -> mass split), in case a loaded config had them out
        # of sync (e.g. a hand-edited save) -- normal UI clicks already keep
        # them consistent via the cascading resets in handle_click.
        mass_movement = self.mass_movement and self.splitting_enabled
        return GameConfig(collapse_mode=self.collapse_mode,
                          splitting_enabled=self.splitting_enabled,
                          mass_movement=mass_movement,
                          mass_split=self.mass_split and mass_movement,
                          seed=self.seed,
                          theme=self.theme_name,
                          white_piece_set=self.white_piece_set,
                          black_piece_set=self.black_piece_set,
                          white_name=self.white_name.strip() or "White",
                          black_name=self.black_name.strip() or "Black",
                          white_color=self.white_color,
                          black_color=self.black_color)

    def handle_click(self, pos):
        """Returns ``(action, GameConfig)`` once Start/Resume is clicked, else
        None. ``action`` is ``"start"`` pre-game, or (mid-game, ``in_game``)
        ``"new_game"`` for the relabeled Start button / ``"resume"`` for the
        Resume button -- ``App`` (see ``open_settings``/``_handle_settings_click``)
        tells those apart to decide whether to reset the board or just apply
        the dial/cosmetic changes to the match in progress."""
        # An open piece-set dropdown is modal: the click either lands on one
        # of its options (select + close) or anywhere else (just close it,
        # same as clicking away from any dropdown) -- either way it doesn't
        # fall through to whatever the option list is currently overlapping.
        if self.white_piece_open:
            for key, r in self._piece_option_rects(self.white_piece_dropdown_rect).items():
                if r.collidepoint(pos):
                    self.white_piece_set = key
                    break
            self.white_piece_open = False
            return None
        if self.black_piece_open:
            for key, r in self._piece_option_rects(self.black_piece_dropdown_rect).items():
                if r.collidepoint(pos):
                    self.black_piece_set = key
                    break
            self.black_piece_open = False
            return None

        if self.white_name_rect.collidepoint(pos):
            self.active_field = "white_name"
            return None
        if self.black_name_rect.collidepoint(pos):
            self.active_field = "black_name"
            return None
        self.active_field = None

        dial_rects = self._dial_rects()   # only the currently-visible toggles
        if self.collapse_full_rect.collidepoint(pos):
            self.collapse_mode = CollapseMode.FULL
        elif self.collapse_partial_rect.collidepoint(pos):
            self.collapse_mode = CollapseMode.PARTIAL
        elif dial_rects["split"].collidepoint(pos):
            self.splitting_enabled = not self.splitting_enabled
            if not self.splitting_enabled:
                # mass movement (and mass split with it) only make sense with
                # splitting on -- turning splitting off hides and clears both.
                self.mass_movement = False
                self.mass_split = False
        elif "mass" in dial_rects and dial_rects["mass"].collidepoint(pos):
            self.mass_movement = not self.mass_movement
            if not self.mass_movement:
                self.mass_split = False   # can't mass-split without mass movement
        elif "mass_split" in dial_rects and dial_rects["mass_split"].collidepoint(pos):
            self.mass_split = not self.mass_split
        elif self.theme_rects["origin"].collidepoint(pos):
            self.theme_name = "origin"
        elif self.theme_rects["cyberpunk"].collidepoint(pos):
            self.theme_name = "cyberpunk"
        elif self.white_piece_dropdown_rect.collidepoint(pos):
            self.white_piece_open = True
            self.black_piece_open = False
        elif self.black_piece_dropdown_rect.collidepoint(pos):
            self.black_piece_open = True
            self.white_piece_open = False
        elif self.swap_rect.collidepoint(pos):
            self._swap_teams()
        elif self.reroll_rect.collidepoint(pos):
            self.seed = random.SystemRandom().randrange(1_000_000)
        elif self.team_save_rect.collidepoint(pos):
            self._save_teams()
        elif self.team_load_rect.collidepoint(pos):
            self._load_teams()
        elif self.in_game and self.resume_rect.collidepoint(pos):
            return self._finalize("resume")
        elif self.start_rect.collidepoint(pos):
            return self._finalize("new_game" if self.in_game else "start")
        elif self.theme_name == "cyberpunk":
            for rect, color in zip(self.white_swatch_rects, theme.SWATCHES):
                if rect.collidepoint(pos):
                    self.white_color = color
                    return None
            for rect, color in zip(self.black_swatch_rects, theme.SWATCHES):
                if rect.collidepoint(pos):
                    self.black_color = color
                    return None
        return None

    def _finalize(self, action):
        """Build the edited config, remember it (every dial + cosmetic field)
        for the next app start via ``persistence.save_last_settings``, and
        return ``(action, config)`` for the caller to apply. Runs on every
        Start/New Game/Resume click -- the moment settings are actually
        confirmed -- so the last-used setup persists across app restarts with
        no separate save step (see ``_load_startup_defaults``)."""
        config = self._build_config()
        try:
            persistence.save_last_settings(LAST_SETTINGS_PATH, config)
        except OSError:
            pass   # best-effort; a failed remember shouldn't block starting the game
        return (action, config)

    def handle_keydown(self, event):
        if self.active_field is None:
            return
        if event.key in (pygame.K_RETURN, pygame.K_TAB, pygame.K_ESCAPE):
            self.active_field = None
            return
        if event.key == pygame.K_BACKSPACE:
            current = getattr(self, self.active_field)
            setattr(self, self.active_field, current[:-1])
            return
        ch = event.unicode
        current = getattr(self, self.active_field)
        if ch and ch.isprintable() and len(current) < MAX_NAME_LEN:
            setattr(self, self.active_field, current + ch)

    def _save_teams(self):
        """Persist the current team setup (theme + names + colours) to disk."""
        try:
            persistence.save_teams(
                TEAMS_SAVE_PATH,
                theme=self.theme_name,
                white_piece_set=self.white_piece_set,
                black_piece_set=self.black_piece_set,
                white_name=self.white_name.strip() or "White",
                black_name=self.black_name.strip() or "Black",
                white_color=self.white_color,
                black_color=self.black_color,
            )
            self.team_status = "Teams saved."
        except OSError as exc:
            self.team_status = f"Save failed: {exc}"

    def _load_startup_defaults(self):
        """Prefill every field -- dials *and* cosmetics -- from the settings
        last used to start/resume/restart a game (``saves/last_settings.json``,
        written automatically by ``_finalize``), so a fresh app launch reopens
        the menu exactly as it was last left. Falls back to a saved team
        profile (cosmetics only, no dials -- see ``_load_teams``) for a first
        run before anything's been auto-saved yet, then to the hardcoded
        defaults. Silent either way: there's nothing to report on startup."""
        try:
            data = persistence.load_last_settings(LAST_SETTINGS_PATH)
        except (OSError, ValueError, KeyError):
            self._load_teams(startup=True)
            return
        self.collapse_mode = data["collapse_mode"]
        self.splitting_enabled = data["splitting_enabled"]
        self.mass_movement = data["mass_movement"]
        self.mass_split = data["mass_split"]
        self.theme_name = data["theme"]
        self.white_piece_set = data["white_piece_set"]
        self.black_piece_set = data["black_piece_set"]
        self.white_name = data["white_name"]
        self.black_name = data["black_name"]
        self.white_color = data["white_color"]
        self.black_color = data["black_color"]

    def _load_teams(self, startup: bool = False):
        """Load a saved team setup back into the menu fields.

        Also called once at startup (``startup=True``) so a match reopens with
        whatever team setup was last saved, instead of the hardcoded defaults.
        A missing/corrupt save is silent on startup (there's nothing to
        report yet) but still surfaces as a status line on an explicit click.
        """
        try:
            data = persistence.load_teams(TEAMS_SAVE_PATH)
        except (OSError, ValueError, KeyError):
            if not startup:
                self.team_status = "No saved teams to load."
            return
        self.theme_name = data["theme"]
        self.white_piece_set = data["white_piece_set"]
        self.black_piece_set = data["black_piece_set"]
        self.white_name = data["white_name"]
        self.black_name = data["black_name"]
        self.white_color = data["white_color"]
        self.black_color = data["black_color"]
        self.active_field = None
        if not startup:
            self.team_status = "Teams loaded."

    def _swap_teams(self):
        """Swap the white/black name and colour assignments.

        White always moves first, so swapping which team is "white" is how
        players pick who starts.
        """
        self.white_name, self.black_name = self.black_name, self.white_name
        self.white_color, self.black_color = self.black_color, self.white_color
        self.white_piece_set, self.black_piece_set = self.black_piece_set, self.white_piece_set
        self.active_field = None

    def _button(self, rect, label, active, enabled=True, font=None):
        font = font or self.font
        if not enabled:
            color, text_color = theme.PANEL_BG, theme.TEXT_DIM
        elif active:
            color, text_color = theme.ACCENT, (20, 20, 20)
        else:
            color, text_color = theme.PANEL_BG, theme.TEXT
        pygame.draw.rect(self.screen, color, rect, border_radius=8)
        pygame.draw.rect(self.screen, theme.TEXT_DIM, rect, width=2, border_radius=8)
        surf = font.render(label, True, text_color)
        self.screen.blit(surf, surf.get_rect(center=rect.center))

    def _piece_icon(self, center, key, color, active):
        """Small king preview of piece-set ``key`` drawn in ``color``'s art,
        shared by the closed dropdown button and its option rows."""
        if key == "unicode":
            ink = (20, 20, 20) if active else theme.TEXT
            glyph = self.font_glyph.render(theme.GLYPH[chess.KING], True, ink)
            self.screen.blit(glyph, glyph.get_rect(center=center))
        else:
            glow = theme.team_neon(color) if key == "neon" else None
            tok = pieces.render_token(key, chess.KING, color, 26, glow=glow)
            self.screen.blit(tok, tok.get_rect(center=center))

    def _draw_piece_dropdown(self, rect, selected, color, open_):
        """The closed-state button for one team's piece-set picker: a preview
        icon, the current set's name, and a caret. Click toggles the option
        list open (``_draw_piece_options`` draws it, directly below)."""
        pygame.draw.rect(self.screen, theme.PANEL_BG, rect, border_radius=8)
        border = theme.ACCENT if open_ else theme.TEXT_DIM
        pygame.draw.rect(self.screen, border, rect, width=2, border_radius=8)
        self._piece_icon((rect.x + 22, rect.centery), selected, color, False)
        label = dict(pieces.PIECE_SETS)[selected]
        s = self.font_small.render(label, True, theme.TEXT)
        self.screen.blit(s, (rect.x + 42, rect.centery - s.get_height() // 2))
        caret = self.font_small.render("▴" if open_ else "▾", True, theme.TEXT_DIM)
        self.screen.blit(caret, caret.get_rect(midright=(rect.right - 8, rect.centery)))

    def _draw_piece_options(self, dropdown_rect, selected, color):
        """The open option list under a piece-set dropdown -- one row per
        available set, highlighted when it's the current selection."""
        for key, label in pieces.PIECE_SETS:
            rect = self._piece_option_rects(dropdown_rect)[key]
            active = key == selected
            bg = theme.ACCENT if active else theme.PANEL_BG
            pygame.draw.rect(self.screen, bg, rect)
            pygame.draw.rect(self.screen, theme.TEXT_DIM, rect, width=1)
            self._piece_icon((rect.x + 22, rect.centery), key, color, active)
            text_color = (20, 20, 20) if active else theme.TEXT
            s = self.font_small.render(label, True, text_color)
            self.screen.blit(s, (rect.x + 42, rect.centery - s.get_height() // 2))

    def _name_field(self, rect, text, active):
        pygame.draw.rect(self.screen, theme.PANEL_BG, rect, border_radius=6)
        border = theme.ACCENT if active else theme.TEXT_DIM
        pygame.draw.rect(self.screen, border, rect, width=2, border_radius=6)
        shown = text + ("|" if active else "")
        surf = self.font.render(shown, True, theme.TEXT)
        self.screen.blit(surf, (rect.x + 10, rect.y + rect.height // 2 - surf.get_height() // 2))

    def _swatches(self, rects, chosen):
        for rect, color in zip(rects, theme.SWATCHES):
            pygame.draw.rect(self.screen, color, rect, border_radius=6)
            if color == chosen:
                pygame.draw.rect(self.screen, theme.TEXT, rect, width=3, border_radius=6)
            else:
                pygame.draw.rect(self.screen, theme.TEXT_DIM, rect, width=1, border_radius=6)

    def draw(self):
        self.screen.fill(theme.BG)
        w, _ = self.screen.get_size()

        title_text = "Quantum Chess -- Settings" if self.in_game else "Quantum Chess -- Match Setup"
        title = self.font_title.render(title_text, True, theme.TEXT)
        self.screen.blit(title, title.get_rect(center=(w // 2, 70)))

        caption = self.font_small.render(
            "Collapse mode -- what happens to the rest of a piece's ghosts on a 'not here' result:",
            True, theme.TEXT_DIM)
        self.screen.blit(caption, caption.get_rect(center=(w // 2, self.collapse_full_rect.y - 18)))
        self._button(self.collapse_full_rect, "Full", self.collapse_mode == CollapseMode.FULL)
        self._button(self.collapse_partial_rect, "Partial", self.collapse_mode == CollapseMode.PARTIAL)

        dial_rects = self._dial_rects()
        for key, label, active in self._dial_specs():
            self._button(dial_rects[key], label, active, font=self.font_small)

        theme_caption = self.font_small.render("Board theme:", True, theme.TEXT_DIM)
        self.screen.blit(theme_caption, theme_caption.get_rect(center=(w // 2, self.theme_rects["origin"].y - 18)))
        self._button(self.theme_rects["origin"], "Origin", self.theme_name == "origin")
        self._button(self.theme_rects["cyberpunk"], "Cyberpunk", self.theme_name == "cyberpunk")

        names_caption = self.font_small.render("Team names:", True, theme.TEXT_DIM)
        self.screen.blit(names_caption, names_caption.get_rect(center=(w // 2, self.white_name_rect.y - 16)))
        self._name_field(self.white_name_rect, self.white_name, self.active_field == "white_name")
        self._name_field(self.black_name_rect, self.black_name, self.active_field == "black_name")
        self._button(self.swap_rect, "⇄", False)

        teams_caption_text = ("Piece set & team colours:" if self.theme_name == "cyberpunk"
                              else "Piece set (each team picks its own):")
        teams_caption = self.font_small.render(teams_caption_text, True, theme.TEXT_DIM)
        self.screen.blit(teams_caption, teams_caption.get_rect(
            center=(w // 2, self.white_piece_dropdown_rect.y - 16)))
        self._draw_piece_dropdown(self.white_piece_dropdown_rect, self.white_piece_set,
                                  chess.WHITE, self.white_piece_open)
        self._draw_piece_dropdown(self.black_piece_dropdown_rect, self.black_piece_set,
                                  chess.BLACK, self.black_piece_open)
        if self.theme_name == "cyberpunk":
            self._swatches(self.white_swatch_rects, self.white_color)
            self._swatches(self.black_swatch_rects, self.black_color)

        seed_label = self.font_small.render(f"Seed: {self.seed}", True, theme.TEXT_DIM)
        self.screen.blit(seed_label, seed_label.get_rect(center=(w // 2, self.reroll_rect.y - 16)))
        self._button(self.team_save_rect, "Save Teams", False)
        self._button(self.reroll_rect, "Reroll seed", False)
        self._button(self.team_load_rect, "Load Teams", False)

        if self.team_status:
            status = self.font_small.render(self.team_status, True, theme.TEXT_DIM)
            self.screen.blit(status, status.get_rect(center=(w // 2, self.reroll_rect.bottom + 14)))

        if self.in_game:
            self._button(self.resume_rect, "Resume Game", True)
            self._button(self.start_rect, "New Game", False)
        else:
            self._button(self.start_rect, "Start Game", True)

        # Open piece-set option lists are drawn last so they overlay whatever
        # they happen to span (they're modal -- see handle_click).
        if self.white_piece_open:
            self._draw_piece_options(self.white_piece_dropdown_rect, self.white_piece_set, chess.WHITE)
        if self.black_piece_open:
            self._draw_piece_options(self.black_piece_dropdown_rect, self.black_piece_set, chess.BLACK)
