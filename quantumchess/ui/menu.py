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
            self._load_teams(startup=True)

        self.font_title = pygame.font.SysFont("segoeui", 36, bold=True)
        self.font = pygame.font.SysFont("segoeui", 22)
        self.font_small = pygame.font.SysFont("segoeui", 17)
        # Small symbol font for the "unicode" piece-set preview swatch.
        self.font_glyph = pygame.font.SysFont("segoeuisymbol", 30)

        w, h = self.screen.get_size()
        cx = w // 2
        self.collapse_full_rect = pygame.Rect(cx - 220, 112, 200, 40)
        self.collapse_partial_rect = pygame.Rect(cx + 20, 112, 200, 40)
        # Three action-dial toggles on one row. "Mass split" is only meaningful
        # with "Mass moves" on, so it's shown disabled (and ignores clicks)
        # until then.
        self.split_toggle_rect = pygame.Rect(cx - 235, 164, 150, 40)
        self.mass_toggle_rect = pygame.Rect(cx - 75, 164, 150, 40)
        self.mass_split_toggle_rect = pygame.Rect(cx + 85, 164, 150, 40)

        self.theme_rects = {
            "origin": pygame.Rect(cx - 220, 232, 200, 40),
            "cyberpunk": pygame.Rect(cx + 20, 232, 200, 40),
        }

        # Piece-set picker, one row per team (each side chooses its own art):
        # a team label on the left, then one button per set with a small king
        # preview drawn in that team's colour.
        self._piece_label_w = 64
        self.white_piece_rects = self._piece_row_rects(cx, 300)
        self.black_piece_rects = self._piece_row_rects(cx, 346)

        self.white_name_rect = pygame.Rect(cx - 320, 412, 300, 34)
        self.black_name_rect = pygame.Rect(cx + 20, 412, 300, 34)
        self.swap_rect = pygame.Rect(cx - 20, 412, 40, 34)

        self.white_swatch_rects = self._swatch_rects(cx - 320)
        self.black_swatch_rects = self._swatch_rects(cx + 20)

        # One row: Save Teams | Reroll seed | Load Teams
        self.team_save_rect = pygame.Rect(cx - 330, 556, 200, 38)
        self.reroll_rect = pygame.Rect(cx - 100, 556, 200, 38)
        self.team_load_rect = pygame.Rect(cx + 130, 556, 200, 38)
        self.team_status = ""       # transient feedback for the last save/load

        # Mid-game, Start doubles as "New Game" (same rect, relabeled) and
        # gains a Resume neighbour so a match's own settings screen can back
        # out without resetting the board. Pre-game there's nothing to resume
        # to, so Start alone stays centered as it always has.
        if self.in_game:
            self.resume_rect = pygame.Rect(cx - 210, 632, 200, 50)
            self.start_rect = pygame.Rect(cx + 10, 632, 200, 50)
        else:
            self.resume_rect = None
            self.start_rect = pygame.Rect(cx - 100, 632, 200, 50)

    def _piece_row_rects(self, cx, y):
        """One team's piece-set buttons: {set_key -> Rect}, laid out to the
        right of a fixed-width team label."""
        pw, pgap = 148, 8
        n = len(pieces.PIECE_SETS)
        grp_w = self._piece_label_w + 12 + n * pw + (n - 1) * pgap
        bx = cx - grp_w // 2 + self._piece_label_w + 12
        return {key: pygame.Rect(bx + i * (pw + pgap), y, pw, 40)
                for i, (key, _label) in enumerate(pieces.PIECE_SETS)}

    @staticmethod
    def _swatch_rects(x0):
        size, gap = 26, 5
        rects = []
        for i, _ in enumerate(theme.SWATCHES):
            col = i % 4
            row = i // 4
            x = x0 + col * (size + gap)
            y = 474 + row * (size + gap)
            rects.append(pygame.Rect(x, y, size, size))
        return rects

    def _build_config(self):
        return GameConfig(collapse_mode=self.collapse_mode,
                          splitting_enabled=self.splitting_enabled,
                          mass_movement=self.mass_movement,
                          # mass split only makes sense with mass movement on.
                          mass_split=self.mass_split and self.mass_movement,
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
        if self.white_name_rect.collidepoint(pos):
            self.active_field = "white_name"
            return None
        if self.black_name_rect.collidepoint(pos):
            self.active_field = "black_name"
            return None
        self.active_field = None

        if self.collapse_full_rect.collidepoint(pos):
            self.collapse_mode = CollapseMode.FULL
        elif self.collapse_partial_rect.collidepoint(pos):
            self.collapse_mode = CollapseMode.PARTIAL
        elif self.split_toggle_rect.collidepoint(pos):
            self.splitting_enabled = not self.splitting_enabled
        elif self.mass_toggle_rect.collidepoint(pos):
            self.mass_movement = not self.mass_movement
            if not self.mass_movement:
                self.mass_split = False   # can't mass-split without mass movement
        elif self.mass_split_toggle_rect.collidepoint(pos):
            if self.mass_movement:        # ignored while disabled
                self.mass_split = not self.mass_split
        elif self.theme_rects["origin"].collidepoint(pos):
            self.theme_name = "origin"
        elif self.theme_rects["cyberpunk"].collidepoint(pos):
            self.theme_name = "cyberpunk"
        elif any(r.collidepoint(pos) for r in self.white_piece_rects.values()):
            for key, r in self.white_piece_rects.items():
                if r.collidepoint(pos):
                    self.white_piece_set = key
                    break
        elif any(r.collidepoint(pos) for r in self.black_piece_rects.values()):
            for key, r in self.black_piece_rects.items():
                if r.collidepoint(pos):
                    self.black_piece_set = key
                    break
        elif self.swap_rect.collidepoint(pos):
            self._swap_teams()
        elif self.reroll_rect.collidepoint(pos):
            self.seed = random.SystemRandom().randrange(1_000_000)
        elif self.team_save_rect.collidepoint(pos):
            self._save_teams()
        elif self.team_load_rect.collidepoint(pos):
            self._load_teams()
        elif self.in_game and self.resume_rect.collidepoint(pos):
            return ("resume", self._build_config())
        elif self.start_rect.collidepoint(pos):
            return ("new_game" if self.in_game else "start", self._build_config())
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

    def _draw_piece_row(self, rects, selected, name, color):
        """Draw one team's piece-set row: the team name label on the left, then
        a button per set (preview drawn in that team's colour)."""
        first = next(iter(rects.values()))
        lab = self.font_small.render(name[:9], True, theme.team_label(color))
        self.screen.blit(lab, (first.x - self._piece_label_w - 12,
                               first.centery - lab.get_height() // 2))
        for key, label in pieces.PIECE_SETS:
            self._piece_set_button(rects[key], key, label, selected == key, color)

    def _piece_set_button(self, rect, key, label, active, color):
        """A piece-set option for one team: a small king preview of the set
        (drawn in ``color``'s art) on the left, the set's name on the right,
        highlighted when selected."""
        bg = theme.ACCENT if active else theme.PANEL_BG
        pygame.draw.rect(self.screen, bg, rect, border_radius=8)
        border = theme.ACCENT if active else theme.TEXT_DIM
        pygame.draw.rect(self.screen, border, rect, width=2 if not active else 3, border_radius=8)

        icon_center = (rect.x + 26, rect.centery)
        if key == "unicode":
            ink = (20, 20, 20) if active else theme.TEXT
            glyph = self.font_glyph.render(theme.GLYPH[chess.KING], True, ink)
            self.screen.blit(glyph, glyph.get_rect(center=icon_center))
        else:
            glow = theme.team_neon(color) if key == "neon" else None
            tok = pieces.render_token(key, chess.KING, color, 36, glow=glow)
            self.screen.blit(tok, tok.get_rect(center=icon_center))

        text_color = (20, 20, 20) if active else theme.TEXT
        s = self.font_small.render(label, True, text_color)
        self.screen.blit(s, (rect.x + 50, rect.centery - s.get_height() // 2))

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

        self._button(self.split_toggle_rect,
                    f"Splitting: {'On' if self.splitting_enabled else 'Off'}",
                    self.splitting_enabled, font=self.font_small)
        self._button(self.mass_toggle_rect,
                    f"Mass moves: {'On' if self.mass_movement else 'Off'}",
                    self.mass_movement, font=self.font_small)
        self._button(self.mass_split_toggle_rect,
                    f"Mass split: {'On' if (self.mass_split and self.mass_movement) else 'Off'}",
                    self.mass_split and self.mass_movement,
                    enabled=self.mass_movement, font=self.font_small)

        theme_caption = self.font_small.render("Board theme:", True, theme.TEXT_DIM)
        self.screen.blit(theme_caption, theme_caption.get_rect(center=(w // 2, self.theme_rects["origin"].y - 18)))
        self._button(self.theme_rects["origin"], "Origin", self.theme_name == "origin")
        self._button(self.theme_rects["cyberpunk"], "Cyberpunk", self.theme_name == "cyberpunk")

        pieces_caption = self.font_small.render("Piece sets (each team picks its own):",
                                                True, theme.TEXT_DIM)
        white_first = next(iter(self.white_piece_rects.values()))
        self.screen.blit(pieces_caption, pieces_caption.get_rect(center=(w // 2, white_first.y - 14)))
        self._draw_piece_row(self.white_piece_rects, self.white_piece_set,
                             self.white_name.strip() or "White", chess.WHITE)
        self._draw_piece_row(self.black_piece_rects, self.black_piece_set,
                             self.black_name.strip() or "Black", chess.BLACK)

        names_caption = self.font_small.render("Team names:", True, theme.TEXT_DIM)
        self.screen.blit(names_caption, names_caption.get_rect(center=(w // 2, self.white_name_rect.y - 16)))
        self._name_field(self.white_name_rect, self.white_name, self.active_field == "white_name")
        self._name_field(self.black_name_rect, self.black_name, self.active_field == "black_name")
        self._button(self.swap_rect, "⇄", False)

        if self.theme_name == "cyberpunk":
            colors_caption = self.font_small.render(
                "Team colours (used as accents against dark grays):", True, theme.TEXT_DIM)
            self.screen.blit(colors_caption, colors_caption.get_rect(
                center=(w // 2, self.white_swatch_rects[0].y - 16)))
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
