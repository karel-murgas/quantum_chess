"""Pre-game match-setup menu -- the v1 dials (see docs/ENGINE.md)."""

from __future__ import annotations

import random
from pathlib import Path

import chess
import pygame

from ..config import CollapseMode, GameConfig
from .. import persistence
from . import theme, pieces, present, render

MAX_NAME_LEN = 16
TEAMS_SAVE_PATH = Path("saves/teams.json")
LAST_SETTINGS_PATH = Path("saves/last_settings.json")

# The dial toggle row is drawn as a small dependency tree, not a flat row --
# each entry here maps a dial to the one it needs (see _dial_rows/_dial_rects).
# "split" (Splitting) is the implicit root: everything else needs it directly
# or indirectly.
_DIAL_PARENT = {
    "split_stay": "split",
    "mass": "split",
    "mass_split": "mass",
    "mass_all_must_act": "mass",
}

# Mouseover copy for each dial toggle and collapse-mode button (see
# _draw_hover_tooltips). Kept as flat data, separate from the labels in
# _dial_specs, since it doesn't depend on on/off state.
_DIAL_TOOLTIPS = {
    "split": "Allow a ghost to split into two branches (probability halved each) "
             "instead of only moving. Off restricts every turn to a plain move.",
    "split_stay": "When a ghost splits, allow one of the two branches to be the "
                  "source square itself (\"stay + move\"). Off requires both "
                  "branches to land on a new square.",
    "mass": "Move every ghost of a superposed piece in one planned turn -- each "
            "ghost aimed independently -- settled by a single roll, instead of "
            "acting on one ghost per turn.",
    "mass_split": "Inside a mass-move turn, let each ghost split as well as "
                  "relocate, not just move.",
    "mass_all_must_act": "Require every ghost in a mass turn to move or split -- "
                        "none may simply stay behind untouched.",
}
_COLLAPSE_TOOLTIPS = {
    CollapseMode.FULL: "A 'not here' result resolves the whole piece to one "
                       "location at once, dropping every other ghost.",
    CollapseMode.PARTIAL: "A 'not here' result only removes the contacted ghost; "
                          "the piece's remaining ghosts renormalize and stay "
                          "superposed.",
}


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
        self.split_stay_enabled = True
        self.mass_movement = False
        self.mass_split = False
        self.mass_all_must_act = False
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
            self.split_stay_enabled = initial_config.split_stay_enabled
            self.mass_movement = initial_config.mass_movement
            self.mass_split = initial_config.mass_split
            self.mass_all_must_act = initial_config.mass_all_must_act
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
        # The dial toggles below Collapse mode are laid out dynamically as a
        # tree, not a fixed row (see _dial_rows/_dial_rects) -- which ones are
        # visible, and how many levels deep the tree goes, depends on the
        # current state. Everything below reserves room for the tree's tallest
        # possible shape (3 levels: Splitting -> Split stay/Mass moves -> Mass
        # split/All must act) so lower sections never have to move.
        y_after_tree = 296

        self.theme_rects = {
            "origin": pygame.Rect(cx - 220, y_after_tree, 200, 40),
            "cyberpunk": pygame.Rect(cx + 20, y_after_tree, 200, 40),
        }

        self.white_name_rect = pygame.Rect(cx - 320, y_after_tree + 68, 300, 34)
        self.black_name_rect = pygame.Rect(cx + 20, y_after_tree + 68, 300, 34)
        self.swap_rect = pygame.Rect(cx - 20, y_after_tree + 68, 40, 34)

        # Piece-set picker, one dropdown per team (each side chooses its own
        # art), sitting directly under Teams next to that team's colour
        # swatches -- closed it's just a button showing the current set with
        # a small king preview; open it drops a same-width option list below
        # (see _piece_option_rects/_draw_piece_options).
        dd_w, dd_h = 140, 38
        piece_row_y = y_after_tree + 132
        self.white_piece_dropdown_rect = pygame.Rect(cx - 320, piece_row_y, dd_w, dd_h)
        self.black_piece_dropdown_rect = pygame.Rect(cx + 20, piece_row_y, dd_w, dd_h)

        self.white_swatch_rects = self._swatch_rects(cx - 320 + dd_w + 20, piece_row_y)
        self.black_swatch_rects = self._swatch_rects(cx + 20 + dd_w + 20, piece_row_y)

        # One row: Save Teams | Reroll seed | Load Teams
        self.team_save_rect = pygame.Rect(cx - 330, y_after_tree + 238, 200, 38)
        self.reroll_rect = pygame.Rect(cx - 100, y_after_tree + 238, 200, 38)
        self.team_load_rect = pygame.Rect(cx + 130, y_after_tree + 238, 200, 38)
        self.team_status = ""       # transient feedback for the last save/load

        # Mid-game, Start doubles as "New Game" (same rect, relabeled) and
        # gains a Resume neighbour so a match's own settings screen can back
        # out without resetting the board. Pre-game there's nothing to resume
        # to, so Start alone stays centered as it always has.
        start_y = y_after_tree + 348
        if self.in_game:
            self.resume_rect = pygame.Rect(cx - 210, start_y, 200, 50)
            self.start_rect = pygame.Rect(cx + 10, start_y, 200, 50)
        else:
            self.resume_rect = None
            self.start_rect = pygame.Rect(cx - 100, start_y, 200, 50)

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
        """(key, label, active) for each dial toggle currently visible. Each is
        **hidden entirely** (not merely disabled) once its prerequisite dial is
        off -- split stay and mass moves both need splitting on; mass split and
        all-must-act both need mass moves on -- so there's nothing to show a
        player that couldn't apply. See ``_DIAL_PARENT`` for the dependency
        chain this mirrors."""
        specs = [("split", f"Splitting: {'On' if self.splitting_enabled else 'Off'}",
                 self.splitting_enabled)]
        if self.splitting_enabled:
            specs.append(("split_stay", f"Split stay: {'On' if self.split_stay_enabled else 'Off'}",
                         self.split_stay_enabled))
            specs.append(("mass", f"Mass moves: {'On' if self.mass_movement else 'Off'}",
                         self.mass_movement))
            if self.mass_movement:
                specs.append(("mass_split", f"Mass split: {'On' if self.mass_split else 'Off'}",
                             self.mass_split))
                specs.append(("mass_all_must_act", f"All must act: {'On' if self.mass_all_must_act else 'Off'}",
                             self.mass_all_must_act))
        return specs

    def _dial_rows(self):
        """Visible dial keys grouped into tree levels, root first -- each level
        is exactly the children (per ``_DIAL_PARENT``) of the previous level's
        nodes, mirroring the dependency chain (Splitting -> Split stay/Mass
        moves -> Mass split/All must act). Feeds both ``_dial_rects`` (layout)
        and ``draw`` (the connecting lines) so the tree's shape is described
        once."""
        keys = [key for key, _label, _active in self._dial_specs()]
        keyset = set(keys)
        rows = []
        placed = set()
        current = [k for k in keys if _DIAL_PARENT.get(k) not in keyset]
        while current:
            rows.append(current)
            placed.update(current)
            current = [k for k in keys if k not in placed and _DIAL_PARENT.get(k) in placed]
        return rows

    def _dial_rects(self):
        """{key -> Rect} for the currently-visible dial toggles, laid out as a
        tree (see ``_dial_rows``): the root is centered on the menu, and each
        further level's siblings are centered directly under their shared
        parent -- so the layout visually branches exactly where the dial
        dependency chain does. Recomputed live rather than cached in
        ``__init__`` -- both which toggles are visible and the tree's shape
        change as the player clicks."""
        rows = self._dial_rows()
        w, h, gap_x, gap_y = 150, 30, 10, 10
        cx = self.screen.get_width() // 2
        y0 = 158
        rects = {}
        centers = {}
        for depth, row in enumerate(rows):
            y = y0 + depth * (h + gap_y)
            group_cx = cx if depth == 0 else centers[_DIAL_PARENT[row[0]]]
            total = len(row) * w + (len(row) - 1) * gap_x
            x0 = group_cx - total // 2
            for i, key in enumerate(row):
                rect = pygame.Rect(x0 + i * (w + gap_x), y, w, h)
                rects[key] = rect
                centers[key] = rect.centerx
        return rects

    def _draw_dial_tree(self, rects):
        """Elbowed connector lines from each visible dial to its parent (see
        ``_DIAL_PARENT``) -- drawn before the buttons so the boxes sit on top
        of the line ends, giving the toggle row a genuine dependency-tree look
        instead of a flat, unrelated row of buttons."""
        for key, rect in rects.items():
            parent_key = _DIAL_PARENT.get(key)
            if parent_key is None or parent_key not in rects:
                continue
            prect = rects[parent_key]
            mid_y = (prect.bottom + rect.top) // 2
            pygame.draw.line(self.screen, theme.TEXT_DIM,
                             (prect.centerx, prect.bottom), (prect.centerx, mid_y), 2)
            pygame.draw.line(self.screen, theme.TEXT_DIM,
                             (prect.centerx, mid_y), (rect.centerx, mid_y), 2)
            pygame.draw.line(self.screen, theme.TEXT_DIM,
                             (rect.centerx, mid_y), (rect.centerx, rect.top), 2)

    def _build_config(self):
        # Defensive AND-gating of the dial dependency chain (splitting ->
        # mass movement -> mass split), in case a loaded config had them out
        # of sync (e.g. a hand-edited save) -- normal UI clicks already keep
        # them consistent via the cascading resets in handle_click.
        mass_movement = self.mass_movement and self.splitting_enabled
        return GameConfig(collapse_mode=self.collapse_mode,
                          splitting_enabled=self.splitting_enabled,
                          split_stay_enabled=self.split_stay_enabled,
                          mass_movement=mass_movement,
                          mass_split=self.mass_split and mass_movement,
                          mass_all_must_act=self.mass_all_must_act and mass_movement,
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
                # split stay, mass movement (and mass split/all-must-act with
                # it) only make sense with splitting on -- turning splitting
                # off hides and clears all of them.
                self.split_stay_enabled = True
                self.mass_movement = False
                self.mass_split = False
                self.mass_all_must_act = False
        elif "split_stay" in dial_rects and dial_rects["split_stay"].collidepoint(pos):
            self.split_stay_enabled = not self.split_stay_enabled
        elif "mass" in dial_rects and dial_rects["mass"].collidepoint(pos):
            self.mass_movement = not self.mass_movement
            if not self.mass_movement:
                # mass split and all-must-act only make sense with mass
                # movement on -- turning it off hides and clears both.
                self.mass_split = False
                self.mass_all_must_act = False
        elif "mass_split" in dial_rects and dial_rects["mass_split"].collidepoint(pos):
            self.mass_split = not self.mass_split
        elif "mass_all_must_act" in dial_rects and dial_rects["mass_all_must_act"].collidepoint(pos):
            self.mass_all_must_act = not self.mass_all_must_act
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
        self.split_stay_enabled = data["split_stay_enabled"]
        self.mass_movement = data["mass_movement"]
        self.mass_split = data["mass_split"]
        self.mass_all_must_act = data["mass_all_must_act"]
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
        self._draw_dial_tree(dial_rects)
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

        # A mouseover tooltip explaining whatever's under the cursor, drawn
        # dead last so it floats over everything else.
        self._draw_hover_tooltips(dial_rects)

    # ------------------------------------------------------------- tooltips
    def _wrap_text(self, text, font, max_width):
        words = text.split(" ")
        lines = []
        current = ""
        for word in words:
            trial = f"{current} {word}".strip()
            if current and font.size(trial)[0] > max_width:
                lines.append(current)
                current = word
            else:
                current = trial
        if current:
            lines.append(current)
        return lines

    def _draw_tooltip(self, text, anchor_rect):
        """A small floating info box explaining ``anchor_rect``'s control,
        word-wrapped and placed just below it (above it if that would run off
        the bottom of the screen; clamped horizontally so it never runs off
        either side)."""
        font = self.font_small
        max_text_w = 320
        lines = self._wrap_text(text, font, max_text_w)
        pad = 10
        line_h = font.get_height() + 2
        box_w = max_text_w + pad * 2
        box_h = line_h * len(lines) + pad * 2

        screen_w, screen_h = self.screen.get_size()
        x = min(max(anchor_rect.centerx - box_w // 2, 8), screen_w - box_w - 8)
        y = anchor_rect.bottom + 10
        if y + box_h > screen_h - 8:
            y = anchor_rect.top - box_h - 10

        box = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        pygame.draw.rect(box, (18, 18, 22, 235), box.get_rect(), border_radius=8)
        pygame.draw.rect(box, theme.ACCENT, box.get_rect(), width=1, border_radius=8)
        for i, line in enumerate(lines):
            surf = font.render(line, True, (232, 232, 232))
            box.blit(surf, (pad, pad + i * line_h))
        self.screen.blit(box, (x, y))

    def _draw_hover_tooltips(self, dial_rects):
        """Show one info tooltip for whichever collapse-mode or dial button
        the mouse currently sits over, if any. Uses ``present.to_logical`` to
        map the real cursor position onto this menu's own (base-resolution)
        coordinate space, same as a click would be -- one frame stale at
        worst, since ``present`` records the mapping from the previous
        ``present()`` call."""
        pos = present.to_logical(pygame.mouse.get_pos())
        targets = [
            (self.collapse_full_rect, _COLLAPSE_TOOLTIPS[CollapseMode.FULL]),
            (self.collapse_partial_rect, _COLLAPSE_TOOLTIPS[CollapseMode.PARTIAL]),
        ]
        for key, rect in dial_rects.items():
            if key in _DIAL_TOOLTIPS:
                targets.append((rect, _DIAL_TOOLTIPS[key]))
        for rect, text in targets:
            if rect.collidepoint(pos):
                self._draw_tooltip(text, rect)
                return
