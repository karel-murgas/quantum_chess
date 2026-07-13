"""Main interactive loop for Quantum Chess (Milestone 4).

Click-driven, hotseat (no networking, no AI): both players share this window
and see the same board, including every ghost and its probability -- nothing is
hidden. The only thing genuinely unknown is the outcome of a collapse, which is
rolled live and narrated in the side log / a short on-board caption.
"""

from __future__ import annotations

import random
from pathlib import Path

import chess
import pygame

from .. import check, rules
from ..collapse import resolve_mass_move, resolve_mass_split, resolve_move, resolve_split
from ..config import GameConfig
from ..model import QuantumBoard
from ..persistence import load_game, save_game
from ..rules import MassMove, MassSplit, MoveKind, Split
from . import render, theme, present, pieces
from .animation import Token, build_animation
from .menu import Menu
from .skins import build_skins

DEFAULT_SAVE_PATH = Path("saves/quicksave.json")


class App:
    def __init__(self, window: pygame.Surface, config: GameConfig):
        # `window` is the physical OS surface; the game is drawn onto an
        # offscreen supersampled surface (`self.screen`) and smooth-scaled to
        # fit the window each frame (see ui/present.py). The in-game Settings
        # menu draws onto its own base-resolution surface, made in open_settings.
        self.window = window
        self.screen = pygame.Surface((theme.WINDOW_W, theme.WINDOW_H))
        self._menu_surf = None
        self.config = config
        self.rng = random.Random(config.seed)
        self.qb = QuantumBoard.standard_setup()

        self.mode = "move"            # "move" | "split"
        self.selected = None          # square with a selected ghost
        self.split_pick_a = None      # first chosen split destination
        # Mass-move / mass-split planning (the "mass movement" dial, and the
        # "mass split" dial layered on it): while planning, `plan` maps every
        # ghost's source square -> a tuple of its chosen destination(s) --
        # one square (relocate; `(from,)` means "stay") or, only when mass
        # split is enabled, two distinct squares (that ghost splits in half).
        # `plan_active` is the ghost currently being assigned, `plan_piece` the
        # piece being planned, and `plan_pick_a` (mass split only) is the first
        # branch chosen while a split is being built for `plan_active` -- the
        # same two-pick gesture as the top-level split mode's `split_pick_a`.
        # See collapse.resolve_mass_move / resolve_mass_split.
        self.plan = None              # dict[from_sq -> tuple[to_sq, ...]] | None
        self.plan_active = None       # from_sq of the ghost being assigned
        self.plan_piece = None        # piece_id being planned
        self.plan_pick_a = None       # first split branch chosen for plan_active
        self.plan_promo = {}          # {(from_sq, to_sq) -> promotion ptype} per promoting branch
        self._pending_plan_promo = None  # (from_sq, to_sq) awaiting a promotion pick
        self._pending_promotion = None  # (from_sq, to_sq, [candidate Moves]) | None
        self._confirm_surrender = False  # armed by one Surrender click, fired by the next
        self._confirm_quit = False    # armed by one Quit click, fired by the next
        self.should_quit = False      # set once Quit is confirmed; run() exits on it
        self.show_captured = True     # side-panel removed-pieces tray, toggled by (C)
        self.show_check = True        # check-probability readout + move warnings, toggled by (K)
        self.in_settings = False      # mid-game Settings screen open? (see open_settings)
        self.settings_menu = None     # the Menu instance driving it while open

        # Drawing skin: the whole frame (board + panel) is delegated to one of
        # these (see ui/skins/ and UI_REDESIGN.md). Started as a 3-variant demo
        # for playtesting; Clarity and Quantum HUD are the two that survived,
        # and a player can switch between them live, mid-match (Tab / the
        # "view" panel control), rather than picking once at the menu.
        self.skins = build_skins()
        self.skin_index = 0
        self.skin = self.skins[self.skin_index]

        self._ply = 0                 # bumps whenever the board changes; keys the check cache
        self._sc_cache_key = None     # (selected, _ply) the cached self-check overlay is for
        self._sc_cache = {}           # {to_square -> resulting Fraction} for the selection
        self._readout_ply = None      # _ply the cached side-panel readout is for
        self._readout = []            # [(text, color)] per-king check lines

        self._beats = []              # remaining collapse-animation beats (current = [0])
        self._beat_elapsed = 0.0      # ms elapsed into the current beat

        self.log = []

    def _piece_label(self, piece_id: int) -> str:
        piece = self.qb.pieces[piece_id]
        side = self.config.team_name(piece.color)
        name = chess.piece_name(piece.ptype).capitalize()
        return f"{side} {name}"

    # ------------------------------------------------------------- selection
    def _own_ghost_at(self, square):
        g = self.qb.ghost_at(square)
        if g is None or self.qb.pieces[g.piece_id].color != self.qb.turn:
            return None
        return g

    def _legal_by_square(self):
        """dict[to_square -> 'move'|'merge'|'contact'] for the current selection.

        In split mode, a branch landing on a *solid* enemy is also tagged
        "contact": the new half-ghost still has to measure itself against
        that enemy (a p/2 branch capturing a certain piece isn't guaranteed),
        unlike a plain move where the mover's own presence is usually certain.
        Split mode also offers the source square itself as a destination --
        one branch can stay put while the other moves.
        """
        if self.selected is None:
            return {}
        risky = (MoveKind.CONTACT, MoveKind.CAPTURE_SOLID) if self.mode == "split" \
            else (MoveKind.CONTACT,)
        by_square = {}
        if self.mode == "split":
            by_square[self.selected] = "move"
        for m in rules.ghost_destinations(self.qb, self.selected):
            tag = "merge" if m.kind == MoveKind.MERGE else (
                "contact" if m.kind in risky else "move")
            by_square[m.to_square] = tag
        return by_square

    def _moves_to_square(self, square):
        return [m for m in rules.ghost_destinations(self.qb, self.selected)
                if m.to_square == square]

    # ------------------------------------------------------- mass-move planning
    def can_mass(self) -> bool:
        return self.config.mass_movement

    def can_mass_split(self) -> bool:
        """Mass split is the mass-movement dial with per-ghost splitting turned
        on -- each planned ghost may fan out into two branches, not just move."""
        return self.config.mass_movement and self.config.mass_split

    def plan_splitting(self) -> bool:
        """Whether the *active* ghost in a plan splits (two picks) or just moves
        (one pick). The top-level Move/Split toggle decides, exactly like it does
        for an ordinary single-ghost turn: in Move mode a planned ghost relocates
        and the click commits immediately; in Split mode it fans into two
        branches. (Only meaningful with the mass-split dial on.)"""
        return self.can_mass_split() and self.mode == "split"

    def _plan_cap(self) -> int:
        """How many destinations the active ghost may be assigned: 2 in Split
        mode with mass split on, else 1 (move only)."""
        return 2 if self.plan_splitting() else 1

    def is_planning(self) -> bool:
        return self.plan is not None

    def _begin_plan(self, piece_id):
        """Enter mass-move/split planning for ``piece_id`` -- every ghost starts
        assigned to 'stay' (a one-element tuple of its own square); the player
        then reassigns any of them and confirms. Planning can be entered from
        either Move or Split mode (see ``handle_mouse_down``); the toggle keeps
        its ordinary meaning *inside* the plan -- it says whether the ghost
        you're aiming moves or splits (see ``plan_splitting``) -- and stays
        switchable mid-plan. With mass split off it has no meaning here at all,
        so reset it to "move" rather than show a stale "SPLIT" label."""
        self.plan = {g.square: (g.square,) for g in self.qb.ghosts_of(piece_id)}
        self.plan_active = None
        self.plan_piece = piece_id
        self.plan_pick_a = None
        self.plan_promo = {}
        self._pending_plan_promo = None
        self.selected = None
        self.split_pick_a = None
        if not self.can_mass_split():
            self.mode = "move"

    def cancel_plan(self):
        self.plan = None
        self.plan_active = None
        self.plan_piece = None
        self.plan_pick_a = None
        self.plan_promo = {}
        self._pending_plan_promo = None

    def _is_promo_leg(self, from_sq, to_sq) -> bool:
        """True if aiming the ghost on ``from_sq`` at ``to_sq`` is a promoting
        pawn push (so the player must pick a promotion piece for this branch)."""
        return any(m.to_square == to_sq and m.promotion is not None
                   for m in rules.ghost_destinations(self.qb, from_sq))

    def _prune_promos(self, from_sq):
        """Drop any recorded promotion for ``from_sq`` whose target is no longer
        one of that ghost's planned destinations (e.g. after re-aiming it)."""
        dests = self.plan.get(from_sq, ())
        self.plan_promo = {k: v for k, v in self.plan_promo.items()
                           if k[0] != from_sq or k[1] in dests}

    def _commit_plan_branch(self, from_sq, to_sq):
        """Record ``to_sq`` as a destination for the active ghost. With mass
        split on this is the first branch (stay active so a second may be added,
        turning the leg into a split) or the second (completing the split);
        without it, it's the single move and the ghost is deselected."""
        if self._plan_cap() == 1 or self.plan_pick_a is None:
            self.plan[from_sq] = (to_sq,)            # single move / first branch
            self._prune_promos(from_sq)
            if self._plan_cap() == 1:
                self.plan_active = None
            else:
                self.plan_pick_a = to_sq             # keep aiming for a 2nd branch
        else:
            self.plan[from_sq] = (self.plan_pick_a, to_sq)   # split into both
            self._prune_promos(from_sq)
            self.plan_pick_a = None
            self.plan_active = None

    def plan_legal(self):
        """dict[to_square -> 'move'|'merge'|'contact'] for the ghost currently
        being assigned (``plan_active``), including its own square (stay). A
        CAPTURE_SOLID is tagged risky ('contact') like in split mode -- a mass
        leg's mover isn't guaranteed present, so even a solid capture is a
        gamble settled by the single roll."""
        if self.plan is None or self.plan_active is None:
            return {}
        by_square = {self.plan_active: "move"}
        for m in rules.ghost_destinations(self.qb, self.plan_active):
            by_square[m.to_square] = "merge" if m.kind == MoveKind.MERGE else (
                "contact" if m.kind in (MoveKind.CONTACT, MoveKind.CAPTURE_SOLID) else "move")
        return by_square

    def _handle_plan_click(self, square):
        if self.plan_active is None:
            if square in self.plan:
                self.plan_active = square            # start assigning this ghost
                self.plan_pick_a = None
                return
            # clicking a *different* superposed own piece switches to planning it
            g = self._own_ghost_at(square)
            if g is not None and self.can_mass() and len(self.qb.ghosts_of(g.piece_id)) > 1:
                self._begin_plan(g.piece_id)
            return

        active = self.plan_active
        split = self._plan_cap() == 2

        # (mass split) clicking the already-chosen first branch again confirms a
        # plain single move there rather than splitting.
        if split and self.plan_pick_a is not None and square == self.plan_pick_a:
            self.plan_pick_a = None
            self.plan_active = None
            return

        # clicking the ghost's own square (when it isn't already branch A) holds
        # it in place.
        if square == active and (not split or self.plan_pick_a is None):
            self.plan[active] = (active,)
            self._prune_promos(active)
            self.plan_pick_a = None
            self.plan_active = None
            return

        if square in self.plan_legal():
            if self._is_promo_leg(active, square):
                # defer the branch commit until the player picks a promotion
                self._pending_plan_promo = (active, square)
            else:
                self._commit_plan_branch(active, square)
            return

        # clicking a *different* planned ghost switches to editing it.
        if square in self.plan:
            self.plan_pick_a = None
            self.plan_active = square
            return

        self.plan_pick_a = None                      # clicked nothing useful
        self.plan_active = None

    # ------------------------------------------------------------- check odds
    def _check_readout(self):
        """One ``(text, color)`` line per side for the side panel, reporting the
        enemy's strongest single move against each king (see
        ``quantumchess.check``) plus a short label naming that move. Danger red
        when a capture is threatened, dim when safe. Cached per board change
        (``_ply``) so it isn't recomputed every frame."""
        if self._readout_ply == self._ply:
            return self._readout
        lines = []
        mass = self.config.mass_movement
        for color in (chess.WHITE, chess.BLACK):
            name = self.config.team_name(color)
            threat = check.strongest_threat(self.qb, color, mass)
            if threat is None or threat.prob == 0:
                lines.append((f"{name}: {theme.TERMS['safe_word']}", theme.TEXT_DIM))
            else:
                lines.append((f"{name}: {theme.TERMS['check_word']} "
                              f"{render.frac_str(threat.prob)} ({threat.describe()})",
                              theme.EVENT_ABSENT_COLOR))
        self._readout_ply, self._readout = self._ply, lines
        return lines

    def _selfcheck_by_square(self):
        """{to_square -> resulting check Fraction} for destinations of the
        current (move-mode) selection that would *raise* the mover's own king
        danger -- the pre-move warning set (feature 2). Cached per selection so
        the per-destination board copies aren't rebuilt every frame."""
        if self.selected is None or self.mode != "move":
            return {}
        key = (self.selected, self._ply)
        if self._sc_cache_key == key:
            return self._sc_cache
        mass = self.config.mass_movement
        baseline = check.check_probability(self.qb, self.qb.turn, mass)
        warnings = {}
        for m in rules.ghost_destinations(self.qb, self.selected):
            resulting = check.move_self_check(self.qb, m, mass)
            if resulting > baseline:
                warnings[m.to_square] = resulting
        self._sc_cache_key, self._sc_cache = key, warnings
        return warnings

    # ----------------------------------------------------------- animation
    def _snapshot_tokens(self):
        """Freeze the board's ghosts into plain animation Tokens (piece meta +
        square + prob + solidity) -- taken *before* a move resolves so the
        animation has the 'before' picture to slide/fade from."""
        toks = []
        for g in self.qb.ghosts:
            p = self.qb.pieces[g.piece_id]
            toks.append(Token(g.piece_id, p.color, p.ptype, g.square, g.prob,
                              self.qb.is_solid(g.piece_id)))
        return toks

    def _begin_animation(self, before, movers, events):
        self._beats = build_animation(before, movers, events)
        self._beat_elapsed = 0.0

    def _beat_t(self) -> float:
        """Progress [0, 1] through the current beat."""
        if not self._beats:
            return 0.0
        dur = self._beats[0].duration_ms
        return min(1.0, self._beat_elapsed / dur) if dur else 1.0

    # --------------------------------------------------------------- input
    def is_animating(self) -> bool:
        return bool(self._beats)

    def is_over(self) -> bool:
        return self.qb.game_over

    def can_split(self) -> bool:
        return self.config.splitting_enabled

    def toggle_mode(self):
        if not self.can_split():
            return
        if self.is_planning():
            if not self.can_mass_split():
                self.cancel_plan()    # the toggle can't mean anything inside a
                                      # move-only plan -- abandon it and go split
                                      # a single ghost the ordinary way
            else:
                # inside a mass-split plan the toggle switches how the *next*
                # ghost is aimed (move or split); drop any half-made assignment.
                self.plan_pick_a = None
                self.plan_active = None
        self.mode = "split" if self.mode == "move" else "move"
        self.split_pick_a = None

    def toggle_captured(self):
        self.show_captured = not self.show_captured

    def toggle_check(self):
        self.show_check = not self.show_check

    def cycle_skin(self):
        """Switch to the next registered view (Tab / the panel's "view"
        control). A display preference, not game state -- untouched by
        new_game/load_from, same as show_captured/show_check."""
        self.skin_index = (self.skin_index + 1) % len(self.skins)
        self.skin = self.skins[self.skin_index]

    def cancel_selection(self):
        """Escape: back out of whatever's in progress -- never quits the app."""
        if self._confirm_quit:
            self._confirm_quit = False
        elif self._confirm_surrender:
            self._confirm_surrender = False
        elif self._pending_promotion is not None:
            self._pending_promotion = None
        elif self._pending_plan_promo is not None:
            self._pending_plan_promo = None   # back out of the promo pick, keep the plan
        elif self.plan is not None and (self.plan_pick_a is not None
                                        or self.plan_active is not None):
            # back out of the in-progress ghost assignment first; a second
            # Escape then cancels the whole plan.
            self.plan_pick_a = None
            self.plan_active = None
        elif self.plan is not None:
            self.cancel_plan()
        elif self.split_pick_a is not None:
            self.split_pick_a = None
        elif self.selected is not None:
            self.selected = None

    def surrender(self):
        """The side to move gives up their turn entirely -- the other side
        wins on the spot, same as a king capture, but with no move played."""
        if self.qb.game_over:
            return
        surrendering = self.config.team_name(self.qb.turn)
        self.qb.winner = not self.qb.turn
        self.qb.game_over = True
        winner = self.config.team_name(self.qb.winner)
        self.log.append(f"{surrendering} {theme.TERMS['surrender_verb']}.")
        self.log.append(f"** {winner} {theme.TERMS['surrender_suffix']} **")

    def new_game(self, config=None):
        """Reset the board. ``config`` (passed by ``_handle_settings_click``
        when the in-game Settings screen's New Game is used instead of the
        post-win button) replaces the match's dials/cosmetics and seeds the
        rng deterministically from it, matching a menu-driven start; the
        no-arg post-win path keeps the existing config and reseeds randomly,
        unchanged from before."""
        if config is not None:
            self.config = config
            self.rng = random.Random(config.seed)
        else:
            self.rng = random.Random()
        self.qb = QuantumBoard.standard_setup()
        self.mode = "move"
        self.selected = None
        self.split_pick_a = None
        self.cancel_plan()
        self._pending_promotion = None
        self._confirm_surrender = False
        self._confirm_quit = False
        self._ply += 1
        self._beats = []
        self._beat_elapsed = 0.0
        self.log = []

    def save_to(self, path=DEFAULT_SAVE_PATH):
        """Snapshot the game to ``path``. Safe to call mid-animation -- ``qb`` is
        already fully resolved the instant a move is applied; only the visual
        reveal queue is transient, and that's not part of the save format."""
        save_game(path, self.qb, self.config, self.rng, self.mode, self.log)
        self.log.append(f"Game saved to {path}.")

    def load_from(self, path=DEFAULT_SAVE_PATH):
        try:
            qb, config, rng, mode, log = load_game(path)
        except (OSError, ValueError, KeyError) as exc:
            self.log.append(f"Couldn't load {path}: {exc}")
            return
        self.qb = qb
        self.config = config
        self.rng = rng
        self.mode = mode
        self.log = log
        theme.apply_theme(config.theme, config.white_color, config.black_color)
        pieces.set_active(config.white_piece_set, config.black_piece_set)
        self.selected = None
        self.split_pick_a = None
        self.cancel_plan()
        self._pending_promotion = None
        self._confirm_surrender = False
        self._confirm_quit = False
        self._ply += 1
        self._beats = []
        self._beat_elapsed = 0.0
        self.log.append(f"Game loaded from {path}.")

    def open_settings(self):
        """Enter the in-game Settings screen (panel button / (O)) -- the same
        ``Menu`` widget the pre-game flow uses, reopened over the current
        match's own dials so a player can tweak theme/colours/names (or the
        collapse/splitting dials) and either resume this game unchanged or
        start a fresh one. Blocked mid-animation, like Save/Load, so a
        collapse reveal can't be interrupted."""
        if self.is_animating():
            return
        # The settings menu is authored at the base resolution, like the
        # pre-game menu -- give it its own surface (present() scales it up).
        self._menu_surf = pygame.Surface((theme.MENU_W, theme.MENU_H))
        self.settings_menu = Menu(self._menu_surf, in_game=True, initial_config=self.config)
        self.in_settings = True

    def _handle_settings_click(self, pos):
        """Routes clicks while ``in_settings`` to the settings ``Menu`` instead
        of the board (see ``run()``). Resume just swaps in the edited config
        (cosmetics/dials only -- the board, log and turn are untouched); New
        Game additionally resets the board via ``new_game(config)``."""
        result = self.settings_menu.handle_click(pos)
        if result is None:
            return
        action, config = result
        theme.apply_theme(config.theme, config.white_color, config.black_color)
        pieces.set_active(config.white_piece_set, config.black_piece_set)
        if action == "resume":
            self.config = config
            self.log.append("Settings updated.")
        elif action == "new_game":
            self.new_game(config)
            self.log.append(f"New game started "
                            f"({config.team_name(chess.WHITE)} vs {config.team_name(chess.BLACK)}).")
        self.in_settings = False
        self.settings_menu = None
        self._menu_surf = None

    def handle_mouse_down(self, pos):
        # Each skin lays its panel out differently; hit-test against the
        # active skin's own rects so clicks track whatever it drew.
        rects = self.skin.panel_rects()
        # A pending collapse reveal always takes priority -- even on the move
        # that just won the game -- so it can never be skipped past via New Game.
        if self.is_animating():
            self._flush_animation()
            return
        if rects["save"].collidepoint(pos):
            self.save_to()
            return
        if rects["load"].collidepoint(pos):
            self.load_from()
            return
        if rects["captured"].collidepoint(pos):
            self.toggle_captured()
            return
        if rects["check"].collidepoint(pos):
            self.toggle_check()
            return
        if rects.get("view") is not None and rects["view"].collidepoint(pos):
            self.cycle_skin()
            return
        if rects.get("settings") is not None and rects["settings"].collidepoint(pos):
            self.open_settings()
            return
        if rects.get("quit") is not None and rects["quit"].collidepoint(pos):
            if self._confirm_quit:
                self.should_quit = True
            else:
                self._confirm_quit = True
                self._confirm_surrender = False
            return
        if self._confirm_quit:
            # Any other click backs out of the armed quit instead of firing it --
            # a stray click elsewhere must never close the app.
            self._confirm_quit = False
            return
        if self.is_over():
            if rects["new_game"].collidepoint(pos):
                self.new_game()
            return
        if rects["surrender"].collidepoint(pos):
            if self._confirm_surrender:
                self.surrender()
                self._confirm_surrender = False
            else:
                self._confirm_surrender = True
            return
        if self._confirm_surrender:
            # Any other click backs out of the armed surrender instead of
            # acting on it -- a stray click elsewhere must never end the game.
            self._confirm_surrender = False
            return
        if self._pending_promotion is not None:
            choice = render.promotion_choice_at(pos)
            if choice is not None:
                self.choose_promotion(choice)
            return
        if rects["mode"].collidepoint(pos):
            self.toggle_mode()
            return

        # Mass-move planning takes over the board until the player confirms or
        # cancels (the confirm/cancel buttons float over the board, so they're
        # hit-tested before board squares).
        if self.is_planning():
            if self._pending_plan_promo is not None:
                choice = render.promotion_choice_at(pos)
                if choice is not None:
                    frm, to = self._pending_plan_promo
                    self.plan_promo[(frm, to)] = choice
                    self._pending_plan_promo = None
                    self._commit_plan_branch(frm, to)   # now finish the branch
                return
            controls = render.mass_controls_rects()
            if controls["confirm"].collidepoint(pos):
                self._confirm_plan()
                return
            if controls["cancel"].collidepoint(pos):
                self.cancel_plan()
                return
            square = render.square_at_pixel(pos)
            if square is not None:
                self._handle_plan_click(square)
            return

        square = render.square_at_pixel(pos)
        if square is None:
            return

        if self.selected is None:
            g = self._own_ghost_at(square)
            if g is not None:
                # With the mass-movement dial on, selecting a *superposed*
                # piece always opens planning instead of an ordinary
                # single-ghost move/split -- regardless of the Move/Split mode
                # toggle. Planning itself lets you choose move *or* (with mass
                # split on) split per ghost, so the top-level mode toggle would
                # otherwise just steal the click into an ordinary one-ghost
                # split and end the turn before the other ghosts are ever
                # touched. A solid piece (one ghost) is unaffected -- it still
                # moves/splits the ordinary one-click/two-click way, honoring
                # whichever mode is active.
                if self.can_mass() and len(self.qb.ghosts_of(g.piece_id)) > 1:
                    self._begin_plan(g.piece_id)
                else:
                    self.selected = square
                    self.split_pick_a = None
            return

        if square == self.selected and self.mode != "split":
            self.selected = None
            self.split_pick_a = None
            return

        legal = self._legal_by_square()
        if square not in legal:
            if self._own_ghost_at(square) is not None:
                self.selected = square
                self.split_pick_a = None
            else:
                self.selected = None
                self.split_pick_a = None
            return

        if self.mode == "split":
            self._handle_split_click(square)
        else:
            self._handle_move_click(square)

    def _handle_move_click(self, square):
        candidates = self._moves_to_square(square)
        if len(candidates) > 1:
            self._pending_promotion = (self.selected, square, candidates)
            return
        self._execute_move(candidates[0])

    def _handle_split_click(self, square):
        if self.split_pick_a is None:
            self.split_pick_a = square
            return
        if square == self.split_pick_a:
            self.split_pick_a = None
            return

        from_sq = self.selected
        piece_id = self.qb.ghost_at(from_sq).piece_id
        label = self._piece_label(piece_id)
        a_sq, b_sq = self.split_pick_a, square
        a_name, b_name = chess.square_name(a_sq), chess.square_name(b_sq)

        # A split branch toward a castle square drags the rook along too --
        # never superposed, it makes one plain move alongside that branch (see
        # rules.split_destination_castle_rook / collapse.resolve_split).
        # Snapshot its "before" so it can slide even though resolve_split only
        # ever measures the king's own branches.
        castle_rooks = [cr for cr in (
            rules.split_destination_castle_rook(self.qb, from_sq, a_sq),
            rules.split_destination_castle_rook(self.qb, from_sq, b_sq),
        ) if cr is not None]
        rook_befores = {}
        for rook_pid, rook_from, _rook_to in castle_rooks:
            rg = self.qb.ghost_at(rook_from)
            rook_befores[rook_pid] = Token(rook_pid, self.qb.pieces[rook_pid].color,
                                           self.qb.pieces[rook_pid].ptype, rook_from,
                                           rg.prob, True)

        before = self._snapshot_tokens()
        color = self.qb.pieces[piece_id].color
        ptype = self.qb.pieces[piece_id].ptype
        half = self.qb.ghost_at(from_sq).prob / 2

        split = Split(piece_id, from_sq, a_sq, b_sq)
        result = resolve_split(self.qb, split, self.config, self.rng)
        self._ply += 1

        def branch_desc(name, sq):
            g = self.qb.ghost_at(sq)
            if g is not None and g.piece_id == piece_id:
                return f"{name} ({render.frac_str(g.prob)})"
            return f"{name} ({theme.TERMS['vanished_word']})"

        self.log.append(f"{label} {theme.TERMS['split_verb']} {chess.square_name(from_sq)} -> "
                        f"{branch_desc(a_name, a_sq)}, {branch_desc(b_name, b_sq)}")

        castled_rooks = []
        for rook_pid, rook_from, rook_to in castle_rooks:
            landed = self.qb.ghost_at(rook_to)
            if landed is not None and landed.piece_id == rook_pid:
                castled_rooks.append((rook_pid, rook_from, rook_to))
        if castled_rooks:
            names = ", ".join(f"{chess.square_name(f)}->{chess.square_name(t)}"
                              for _pid, f, t in castled_rooks)
            self.log.append(f"{label} {theme.TERMS['castle_verb']} (rook {names}).")

        if result.captured_piece_ids:
            names = ", ".join(self._piece_label(i) for i in result.captured_piece_ids)
            self.log.append(f"{label} {theme.TERMS['capture_verb']} {names}.")
        if self.qb.game_over and self.qb.winner is not None:
            winner = self.config.team_name(self.qb.winner)
            self.log.append(f"** {winner} {theme.TERMS['win_suffix']} **")

        # Both branches slide out from the source; each measured branch then
        # flashes. A branch that vanishes still travels first, then fades.
        movers = [(Token(piece_id, color, ptype, a_sq, half, False), from_sq),
                  (Token(piece_id, color, ptype, b_sq, half, False), from_sq)]
        for rook_pid, rook_from, rook_to in castled_rooks:
            rook_before = rook_befores[rook_pid]
            dest_rook_tok = Token(rook_pid, rook_before.color, rook_before.ptype,
                                  rook_to, rook_before.prob, True)
            movers.append((dest_rook_tok, rook_from))
        self._begin_animation(before, movers, result.events)

        self.selected = None
        self.split_pick_a = None
        self.mode = "move"          # each new turn defaults back to move mode

    def _confirm_plan(self):
        """Resolve the planned mass move/split: build the ``MassMove`` (every
        leg a single move) or ``MassSplit`` (some ghost fans out into two
        branches), roll it out via ``resolve_mass_move``/``resolve_mass_split``
        (one measurement settles every conflict), log it, and animate every
        moving branch sliding out (the winning branch lands solid; the losers
        travel as ghosts and are faded by the collapse events)."""
        piece_id = self.plan_piece
        label = self._piece_label(piece_id)
        color = self.qb.pieces[piece_id].color
        ptype = self.qb.pieces[piece_id].ptype
        src_prob = {g.square: g.prob for g in self.qb.ghosts_of(piece_id)}

        before = self._snapshot_tokens()
        if self.can_mass_split():
            legs = tuple((frm, tuple(dests)) for frm, dests in self.plan.items())
            promotions = tuple((frm, to, promo)
                               for (frm, to), promo in self.plan_promo.items()
                               if to in self.plan.get(frm, ()) and to != frm)
            result = resolve_mass_split(self.qb, MassSplit(piece_id, legs, promotions),
                                        self.config, self.rng)
            verb = theme.TERMS['mass_split_verb']
        else:
            assignments = tuple((frm, dests[0]) for frm, dests in self.plan.items())
            promotions = tuple((frm, promo)
                               for (frm, to), promo in self.plan_promo.items()
                               if self.plan.get(frm) == (to,) and to != frm)
            result = resolve_mass_move(self.qb, MassMove(piece_id, assignments, promotions),
                                       self.config, self.rng)
            verb = theme.TERMS['mass_verb']
        self._ply += 1

        parts = []
        for frm, dests in self.plan.items():
            moving = [d for d in dests if d != frm]
            if not moving and len(dests) == 1:
                continue                                  # a plain hold
            targets = "/".join(chess.square_name(d) for d in dests)
            parts.append(f"{chess.square_name(frm)}->{targets}")
        legs_desc = ", ".join(parts) or "all ghosts hold"
        self.log.append(f"{label} {verb}: {legs_desc}.")
        if result.captured_piece_ids:
            names = ", ".join(self._piece_label(i) for i in result.captured_piece_ids)
            self.log.append(f"{label} {theme.TERMS['capture_verb']} {names}.")
        if result.final_square is not None:
            self.log.append(f"{label} {theme.TERMS['mass_collapse_clause']} "
                            f"{chess.square_name(result.final_square)}.")
        if self.qb.game_over and self.qb.winner is not None:
            winner = self.config.team_name(self.qb.winner)
            self.log.append(f"** {winner} {theme.TERMS['win_suffix']} **")

        # Every moving branch slides out from its source (like a split's
        # branches); the winning branch (if the piece collapsed) lands solid on
        # its real square, the rest travel as ghosts and are faded by the
        # collapse events. `chosen_to` disambiguates the winning branch from a
        # *sibling* branch of the same source when a ghost split into two.
        movers = []
        winner_used = False
        for frm, dests in self.plan.items():
            branch_prob = src_prob[frm] / len(dests)
            for to in dests:
                if frm == to:
                    continue
                if (not winner_used and result.final_square is not None
                        and result.chosen_from == frm and result.chosen_to == to):
                    dest_tok = Token(piece_id, color, ptype, result.final_square,
                                     branch_prob, True)
                    winner_used = True
                else:
                    dest_tok = Token(piece_id, color, ptype, to, branch_prob, False)
                movers.append((dest_tok, frm))
        self._begin_animation(before, movers, result.events)

        self.cancel_plan()
        self.selected = None
        self.mode = "move"

    def choose_promotion(self, promo_piece):
        _from_sq, _to_sq, candidates = self._pending_promotion
        move = next(m for m in candidates if m.promotion == promo_piece)
        self._pending_promotion = None
        self._execute_move(move)

    def _execute_move(self, move):
        piece_id = move.piece_id
        label = self._piece_label(piece_id)
        frm = chess.square_name(move.from_square)

        # A castle is a king move that -- only if it fully arrives -- drags the
        # rook along too; snapshot the rook's "before" so it can slide even
        # though `resolve_move` only ever measures the king.
        rook_before = None
        if move.castle_rook is not None:
            rook_pid, rook_from, rook_to = move.castle_rook
            rg = self.qb.ghost_at(rook_from)
            rook_before = Token(rook_pid, self.qb.pieces[rook_pid].color,
                                self.qb.pieces[rook_pid].ptype, rook_from, rg.prob, True)

        before = self._snapshot_tokens()
        src = self.qb.ghost_at(move.from_square)
        mover_tok = Token(piece_id, self.qb.pieces[piece_id].color,
                          self.qb.pieces[piece_id].ptype, move.from_square,
                          src.prob, self.qb.is_solid(piece_id))

        result = resolve_move(self.qb, move, self.config, self.rng)
        self._ply += 1
        self.selected = None
        self.mode = "move"          # each new turn defaults back to move mode

        castled = False
        if move.castle_rook is not None:
            rook_pid, _rook_from, rook_to = move.castle_rook
            landed = self.qb.ghost_at(rook_to)
            castled = landed is not None and landed.piece_id == rook_pid

        if result.fizzled:
            self.log.append(f"{label} {frm}: {theme.TERMS['fizzle_clause']}.")
        else:
            to = chess.square_name(result.final_square)
            if castled:
                rook_to_name = chess.square_name(move.castle_rook[2])
                rook_from_name = chess.square_name(move.castle_rook[1])
                self.log.append(f"{label} {theme.TERMS['castle_verb']} {frm}->{to} "
                                f"(rook {rook_from_name}->{rook_to_name}).")
            elif result.captured_piece_ids:
                names = ", ".join(self._piece_label(i) for i in result.captured_piece_ids)
                self.log.append(f"{label} {frm}->{to}: {theme.TERMS['capture_verb']} {names}.")
            else:
                self.log.append(f"{label} {frm}->{to}.")
            if self.qb.game_over and self.qb.winner is not None:
                winner = self.config.team_name(self.qb.winner)
                self.log.append(f"** {winner} {theme.TERMS['win_suffix']} **")

        # Only a move that actually measured something (a collapse) gets the
        # slide+flash treatment; a quiet relocate/merge resolves instantly so
        # ordinary play stays snappy. The mover slides source -> final square; a
        # fizzle doesn't move (its source ghost just fades in its flash beat).
        # A completed castle always slides both pieces, like a split's two
        # branches, even when the path was clear and nothing was measured.
        if result.events or castled:
            movers = []
            if not result.fizzled and result.final_square is not None:
                dest_tok = Token(mover_tok.piece_id, mover_tok.color, mover_tok.ptype,
                                 result.final_square, mover_tok.prob, mover_tok.solid)
                movers = [(dest_tok, move.from_square)]
            if castled:
                rook_pid, rook_from, rook_to = move.castle_rook
                dest_rook_tok = Token(rook_pid, rook_before.color, rook_before.ptype,
                                      rook_to, rook_before.prob, True)
                movers.append((dest_rook_tok, rook_from))
            self._begin_animation(before, movers, result.events)

    def _flush_animation(self):
        """Skip to the end -- ``qb`` is already at the final state, so just drop
        the remaining beats and let the live board draw."""
        self._beats = []
        self._beat_elapsed = 0.0

    # -------------------------------------------------------------- update
    def update(self, dt_ms):
        if not self._beats:
            return
        self._beat_elapsed += dt_ms
        # A single frame can span more than one short beat -- drain them all.
        while self._beats and self._beat_elapsed >= self._beats[0].duration_ms:
            self._beat_elapsed -= self._beats[0].duration_ms
            self._beats.pop(0)
        if not self._beats:
            self._beat_elapsed = 0.0

    # ---------------------------------------------------------------- draw
    def draw(self):
        # The Settings screen is a full-screen overlay, like the pre-game
        # menu -- it takes over the whole window rather than living inside
        # the skin's own panel, so board/panel drawing is skipped entirely
        # while it's open.
        if self.in_settings:
            self.settings_menu.draw()
            present.present(self.window, self._menu_surf)
            return
        # The active skin owns the entire frame -- board, pieces, panel,
        # collapse animation. See ui/skins/. It draws onto the offscreen
        # supersampled surface, which is then smooth-scaled to the window.
        self.skin.draw(self)
        if getattr(theme, "THEME_NAME", "origin") == "cyberpunk":
            render.draw_vignette(self.screen)   # moodier, screen-lit look
        present.present(self.window, self.screen)

    # ----------------------------------------------------------------- run
    def handle_keydown(self, event):
        """Keyboard shortcuts."""
        if self.in_settings:
            # Escape backs out of Settings without applying anything -- same
            # "cancel, never destroy state" contract as cancel_selection.
            # F11 still works so a player isn't stuck out of fullscreen.
            if event.key == pygame.K_ESCAPE:
                self.in_settings = False
                self.settings_menu = None
            elif event.key == pygame.K_F11:
                self.window = present.toggle_fullscreen(self.window)
            else:
                self.settings_menu.handle_keydown(event)
            return
        if event.key == pygame.K_F11:
            self.window = present.toggle_fullscreen(self.window)
        if event.key == pygame.K_TAB:
            self.cycle_skin()
        if event.key == pygame.K_ESCAPE:
            self.cancel_selection()
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.is_planning() \
                and self._pending_plan_promo is None:
            self._confirm_plan()
        if event.key == pygame.K_m:
            self.toggle_mode()
        if event.key == pygame.K_c:
            self.toggle_captured()
        if event.key == pygame.K_k:
            self.toggle_check()
        if event.key == pygame.K_o:
            self.open_settings()
        if event.key == pygame.K_n and self.is_over() and not self.is_animating():
            self.new_game()
        if event.key == pygame.K_F5 and not self.is_animating():
            self.save_to()
        if event.key == pygame.K_F9 and not self.is_animating():
            self.load_from()

    def run(self):
        clock = pygame.time.Clock()
        while True:
            dt = clock.tick(60)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                elif event.type == pygame.VIDEORESIZE and not present.is_fullscreen():
                    self.window = pygame.display.set_mode(event.size, pygame.RESIZABLE)
                elif event.type == pygame.KEYDOWN:
                    self.handle_keydown(event)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    # Map the physical-window click onto the logical surface
                    # that was last presented (game or settings menu).
                    pos = present.to_logical(event.pos)
                    if self.in_settings:
                        self._handle_settings_click(pos)
                    else:
                        self.handle_mouse_down(pos)

            if self.should_quit:
                return

            self.update(dt)
            self.draw()
            pygame.display.flip()
