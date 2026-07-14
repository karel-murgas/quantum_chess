"""BaseSkin -- the drawing contract every UI-redesign variant implements.

A *skin* owns the entire frame: given the running ``App`` (its ``qb``,
selection, mode, log, animation beats, toggles) it paints board + pieces +
panel + collapse animation + promotion picker.

Design constraints that keep this safe to swap live mid-game:

* **Hit-testing is shared, never overridden.** Board squares use
  ``render.square_rect`` / ``render.square_at_pixel`` and panel buttons use
  ``render.panel_rects`` -- so ``App.handle_mouse_down`` keeps working no matter
  which skin is active. A skin changes how things *look*, drawn at the same
  clickable positions.
* **Content theme still applies.** Skins read ``theme.X`` for the origin /
  cyberpunk palette + narration ``TERMS``; the skin adds the *structural* design
  language (frame, typography, token style, probability display, motion,
  collapse flair) on top. So theme drives more than colour.

``draw(app)`` is the orchestrator; subclasses override the small visual hooks
(``draw_background``, ``draw_board``, ``draw_token``, ``draw_ghost_prob``,
``draw_selection``, ``draw_legal``, ``draw_sibling_web``, ``panel_backdrop``,
``draw_button``, ``collapse_overlay`` ...). The BaseSkin defaults reproduce the
original look, so a variant only writes what makes it distinct.
"""

from __future__ import annotations

import math
from fractions import Fraction

import chess
import pygame

from ... import check
from .. import render, theme, present

SQUARE = theme.SQUARE
BOARD_MARGIN = theme.BOARD_MARGIN
BOARD_PIXELS = theme.BOARD_PIXELS
PANEL_X = BOARD_MARGIN * 2 + BOARD_PIXELS
PANEL_W = theme.PANEL_WIDTH
WINDOW_W = theme.WINDOW_W
WINDOW_H = theme.WINDOW_H

FILES = "abcdefgh"
RANKS = "12345678"


class BaseSkin:
    #: short display name, shown in the demo's variant chip
    name = "Base"
    #: one-line description
    blurb = "the original look, routed through the skin system"
    #: font families -- override for a different typographic personality
    FAMILY = "segoeui"
    MONO = "consolas"
    SYMBOL = "segoeuisymbol"

    def __init__(self):
        self.fonts = self._build_fonts()
        self._cv_key = None       # app._ply the cached check values are for
        self._cv = []             # [(name, Fraction, color_bool)] per king

    # ---------------------------------------------------------------- fonts
    def _build_fonts(self):
        # Point sizes are authored at the base resolution, then scaled into the
        # supersampled render space (theme.px) so text is drawn at 2x and
        # downscaled crisp -- the same SSAA that de-pixelates the board. The
        # piece glyph size derives from SQUARE, which is already scaled.
        f = self.FAMILY
        px = theme.px
        return {
            "hero": pygame.font.SysFont(f, px(30), bold=True),
            "title": pygame.font.SysFont(f, px(26), bold=True),
            "body": pygame.font.SysFont(f, px(20)),
            "small": pygame.font.SysFont(f, px(16)),
            "tiny": pygame.font.SysFont(f, px(12), bold=True),
            "banner": pygame.font.SysFont(f, px(44), bold=True),
            "piece": pygame.font.SysFont(self.SYMBOL, int(SQUARE * 0.62)),
            "label": pygame.font.SysFont(f, px(15), bold=True),
            "coord": pygame.font.SysFont(f, px(13), bold=True),
            "icon": pygame.font.SysFont(self.SYMBOL, px(18)),
            # Ghost-probability chip label (see _chip below): always the base
            # family, never a skin's own typographic personality (e.g. HUD's
            # Consolas) -- a monospace "/" glyph's own bearing threw the
            # visual centre off even though the bounding box was centred, so
            # every skin now renders this one label identically to Clarity's.
            "chip": pygame.font.SysFont(BaseSkin.FAMILY, px(12), bold=True),
        }

    # ----------------------------------------------------------- utilities
    @staticmethod
    def _aura_color(piece_id: int):
        return theme.AURA_PALETTE[piece_id % len(theme.AURA_PALETTE)]

    @staticmethod
    def _tint(color, alpha: int):
        return (*color, max(0, min(255, alpha)))

    @staticmethod
    def _mix(a, b, t):
        return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))

    @staticmethod
    def _dotted_ring(surf, center, r, color, n=14):
        """A ring of small dots -- the shared "risky contact" legal-move cue
        (Polished's own destination rings, reused by Clarity's)."""
        for i in range(n):
            a = 2 * math.pi * i / n
            pt = (center[0] + int(r * math.cos(a)), center[1] + int(r * math.sin(a)))
            pygame.draw.circle(surf, color, pt, theme.px(3))

    def _chip(self, surf, text, center, bg, fg, font=None):
        """A small rounded pill: opaque ``bg`` behind ``fg``-coloured text,
        centred exactly on ``center``. Shared by every skin's ghost-probability
        label so they all get the same (verified-correct) text centring --
        drawn straight onto ``surf`` with plain opaque fills, no intermediate
        alpha-blended surface, which is what keeps the centring exact."""
        s = (font or self.fonts["chip"]).render(text, True, fg)
        pad = theme.px(4)
        w, h = s.get_width() + pad * 2, s.get_height() + pad
        chip = pygame.Rect(0, 0, w, h)
        chip.center = center
        pygame.draw.rect(surf, bg, chip, border_radius=h // 2)
        surf.blit(s, s.get_rect(center=chip.center))

    @staticmethod
    def now():
        return pygame.time.get_ticks() / 1000.0

    def pulse(self, period=1.1):
        """0..1 triangle-ish pulse for selection/idle glow."""
        return 0.5 + 0.5 * math.sin(2 * math.pi * self.now() / period)

    def hover_square(self):
        # The mouse position is in physical-window pixels; map it back onto the
        # supersampled logical surface (letterbox-aware) before hit-testing, or
        # the hover highlight lands on the wrong square.
        return render.square_at_pixel(present.to_logical(pygame.mouse.get_pos()))

    @staticmethod
    def _token_colors(color: bool):
        if color == chess.WHITE:
            return theme.WHITE_TOKEN, theme.WHITE_TOKEN_BORDER, theme.WHITE_INK
        return theme.BLACK_TOKEN, theme.BLACK_TOKEN_BORDER, theme.BLACK_INK

    # -------------------------------------------------- shared panel helpers
    def _check_values(self, app):
        """``[(team_name, Fraction danger, color_bool)]`` per king, cached per
        board change so a threat gauge can be drawn every frame cheaply. The
        Fraction is the same aggregate danger ``App._check_readout`` reports as
        text -- here the skins want the number, to size a bar/gauge."""
        if self._cv_key == app._ply:
            return self._cv
        mass = app.config.mass_movement
        vals = [(app.config.team_name(c), check.check_probability(app.qb, c, mass), c)
                for c in (chess.WHITE, chess.BLACK)]
        self._cv_key, self._cv = app._ply, vals
        return vals

    def _hbar(self, surf, rect, frac, fg, bg, radius=4):
        """A horizontal fill bar (threat gauges, inspector distribution)."""
        pygame.draw.rect(surf, bg, rect, border_radius=radius)
        if frac > 0:
            w = max(theme.px(3), int(rect.w * min(1.0, float(frac))))
            pygame.draw.rect(surf, fg, (rect.x, rect.y, w, rect.h), border_radius=radius)

    def _caps_label(self, surf, text, pos, font=None, color=None, rule_to=None):
        """A dim small-caps section label; optional hairline rule to ``rule_to`` x.
        Returns the y just below the label."""
        font = font or self.fonts["tiny"]
        color = color or theme.TEXT_DIM
        s = font.render(text.upper(), True, color)
        surf.blit(s, pos)
        if rule_to is not None:
            ly = pos[1] + s.get_height() // 2
            pygame.draw.line(surf, self._tint(theme.TEXT_DIM, 90),
                             (pos[0] + s.get_width() + theme.px(10), ly), (rule_to, ly), theme.px(1))
        return pos[1] + s.get_height()

    # ------------------------------------------------------------- orchestr.
    def draw(self, app):
        surf = app.screen
        self.draw_background(surf, app)
        self.draw_board(surf, app)

        status = ""
        if app.is_animating():
            status = self.draw_collapse(surf, app)
        elif app.is_planning():
            status = self.draw_plan(surf, app)
        else:
            legal = app._legal_by_square()
            warnings = app._selfcheck_by_square() if app.show_check else {}
            self.draw_sibling_web(surf, app)
            self.draw_selection(surf, app)
            self.draw_pinned_highlight(surf, app)
            self.draw_legal(surf, app, legal, warnings)
            self.draw_pieces(surf, app)
            if app._pending_promotion is not None:
                status = "Choose promotion: click a piece"

        check_lines = app._check_readout() if app.show_check else None
        self.draw_panel(surf, app, status, check_lines)

        if app._pending_promotion is not None or app._pending_plan_promo is not None:
            self.draw_promotion(surf, app)
        elif not app.is_animating():
            self.draw_pinned_inspector(surf, app)

    # ------------------------------------------------------------ background
    def draw_background(self, surf, app):
        surf.fill(theme.BG)

    # ----------------------------------------------------------------- board
    def board_rect(self):
        return pygame.Rect(BOARD_MARGIN, BOARD_MARGIN, BOARD_PIXELS, BOARD_PIXELS)

    def square_color(self, square, light: bool):
        return theme.LIGHT_SQUARE if light else theme.DARK_SQUARE

    def draw_board(self, surf, app):
        for square in chess.SQUARES:
            rect = render.square_rect(square)
            light = (chess.square_file(square) + chess.square_rank(square)) % 2 == 1
            pygame.draw.rect(surf, self.square_color(square, light), rect)
        self.draw_hover(surf, app)
        pygame.draw.rect(surf, theme.BOARD_BORDER, self.board_rect(), width=theme.px(3))
        self.draw_coordinates(surf)

    def draw_hover(self, surf, app):
        if app.is_over() or app.is_animating():
            return
        sq = self.hover_square()
        if sq is None:
            return
        rect = render.square_rect(sq)
        glow = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        glow.fill(self._tint(theme.TEXT, 26))
        surf.blit(glow, rect.topleft)

    def draw_coordinates(self, surf):
        font = self.fonts["coord"]
        for f in range(8):
            rect = render.square_rect(chess.square(f, 0))
            light = (f + 0) % 2 == 1
            col = self.square_color(chess.square(f, 0), not light)
            lab = font.render(FILES[f], True, col)
            surf.blit(lab, (rect.right - lab.get_width() - 3, rect.bottom - lab.get_height() - 2))
        for r in range(8):
            rect = render.square_rect(chess.square(0, r))
            light = (0 + r) % 2 == 1
            col = self.square_color(chess.square(0, r), not light)
            lab = font.render(RANKS[r], True, col)
            surf.blit(lab, (rect.left + 3, rect.top + 2))

    # ---------------------------------------------------------------- pieces
    def draw_pieces(self, surf, app):
        qb = app.qb
        for ghost in qb.ghosts:
            piece = qb.pieces[ghost.piece_id]
            center = render.square_rect(ghost.square).center
            solid = qb.is_solid(ghost.piece_id)
            alpha = render._prob_alpha(ghost.prob, solid)
            self.draw_token(surf, piece.color, piece.ptype, center, alpha=alpha, solid=solid)
            if not solid:
                self.draw_ghost_prob(surf, ghost, center, piece.color)

    def draw_token(self, surf, color, ptype, center, *, alpha=255, radius=None, solid=True):
        render.draw_token(surf, self.fonts["piece"], color, ptype, center,
                          alpha=alpha, radius=radius)

    def draw_ghost_prob(self, surf, ghost, center, color, alpha=255):
        render._draw_prob_label(surf, self.fonts["label"], ghost.prob, center, alpha=alpha, color=color)

    # ------------------------------------------------------- entanglement web
    def draw_sibling_web(self, surf, app):
        """How a piece's superposed ghosts are visually linked. Off by default;
        HUD / Clarity turn it on for the whole board."""
        return

    # ------------------------------------------------------------- selection
    def draw_selection(self, surf, app):
        qb, sel = app.qb, app.selected
        if sel is not None:
            ghost = qb.ghost_at(sel)
            if ghost is not None:
                for g in qb.ghosts_of(ghost.piece_id):
                    pygame.draw.rect(surf, self._aura_color(ghost.piece_id),
                                     render.square_rect(g.square), width=4)
            ring = self._mix(theme.SELECTED_RING, (255, 255, 255), 0.25 * self.pulse())
            pygame.draw.rect(surf, ring, render.square_rect(sel), width=5)
        if app.split_pick_a is not None:
            pygame.draw.rect(surf, theme.SPLIT_PICK_RING,
                             render.square_rect(app.split_pick_a), width=5)

    # --------------------------------------------------------------- legal
    def draw_legal(self, surf, app, legal, warnings):
        dot_colors = {"merge": theme.LEGAL_MERGE_DOT, "contact": theme.LEGAL_CONTACT_DOT}
        for sq, kind in legal.items():
            rect = render.square_rect(sq)
            color = dot_colors.get(kind, theme.LEGAL_MOVE_DOT)
            pygame.draw.circle(surf, color, rect.center, SQUARE // 8)
        if warnings:
            for sq, prob in warnings.items():
                render._draw_danger_marker(surf, sq, prob, self.fonts)

    # -------------------------------------------------------- mass-move plan
    def draw_plan(self, surf, app):
        """Draw the in-progress mass-move / mass-split plan: sibling web +
        aura/active rings under the pieces, the active ghost's legal targets in
        this skin's own dot/ring language, then the assignment arrows over the
        pieces and the floating Confirm/Cancel controls. Returns a status
        prompt."""
        self.draw_sibling_web(surf, app)
        render.draw_plan_rings(surf, app.plan, app.plan_active, app.plan_piece)
        self.draw_legal(surf, app, app.plan_legal(), {})
        self.draw_pieces(surf, app)
        render.draw_plan_arrows(surf, app.plan, app.plan_piece, app.plan_pick_a)
        all_acted = app._plan_fully_acted()
        confirm_enabled = not (app.config.mass_all_must_act and not all_acted)
        render.draw_mass_controls(surf, self.fonts, confirm_enabled=confirm_enabled)
        split = app.plan_splitting()
        noun = "Mass split" if app.can_mass_split() else "Mass move"
        if app._pending_plan_promo is not None:
            return "Choose promotion for this branch: click a piece"
        if app.plan_active is None:
            if not confirm_enabled:
                return "Every ghost must move or split before you can Confirm"
            hint = " ([M] to split a ghost)" if app.can_mass_split() and not split else ""
            return f"{noun}: click a ghost to aim it, then Confirm{hint}"
        if split and app.plan_pick_a is not None:
            return "2nd square = split; the 1st square again = single move"
        if split:
            return "Split this ghost: click its two branches"
        return "Move this ghost: click its target (or itself to hold)"

    # ------------------------------------------------------------- collapse
    def _draw_anim_token(self, surf, tok, center, alpha_mult=1.0):
        base = render._prob_alpha(tok.prob, tok.solid)
        alpha = int(base * alpha_mult)
        self.draw_token(surf, tok.color, tok.ptype, center, alpha=alpha, solid=tok.solid)
        if not tok.solid and alpha_mult > 0.15:
            # a lightweight ghost prob during motion (fraction), for all skins
            render._draw_prob_label(surf, self.fonts["label"], tok.prob, center,
                                    alpha=int(255 * alpha_mult), color=tok.color)

    def draw_collapse(self, surf, app):
        beat = app._beats[0]
        t = app._beat_t()
        te = render._ease(t)

        if beat.flash_square is not None:
            render._draw_flash(surf, beat.flash_square, bool(beat.flash_present), t)
        for tok in beat.rest:
            self._draw_anim_token(surf, tok, render.square_rect(tok.square).center)
        for tok, frm in beat.travel:
            center = render._lerp(render.square_rect(frm).center,
                                  render.square_rect(tok.square).center, te)
            self._draw_anim_token(surf, tok, center)
        for tok in beat.fades:
            self._draw_anim_token(surf, tok, render.square_rect(tok.square).center,
                                  alpha_mult=max(0.0, 1 - t))
        if beat.shatter is not None:
            render._draw_shatter(surf, self.fonts["piece"], beat.shatter, t)
        if beat.caption:
            render._draw_caption(surf, self.fonts["label"], beat.caption,
                                 beat.caption_square, t)
        self.collapse_overlay(surf, app, beat, t)

        if beat.flash_square is not None:
            verb = theme.TERMS["present_word"] if beat.flash_present else theme.TERMS["absent_word"]
            return (f"{theme.TERMS['measuring_verb']} @ "
                    f"{chess.square_name(beat.flash_square)}: {verb} there")
        return ""

    def collapse_overlay(self, surf, app, beat, t):
        """Extra full-screen flair during a collapse (glitch, dust, ...)."""
        return

    # --------------------------------------------------------------- panel
    def panel_rects(self):
        """Clickable panel button rects for THIS skin. Must contain the keys
        ``App.handle_mouse_down`` hit-tests (mode/save/load/surrender/captured/
        check/new_game). Defaults to the canonical layout; a skin with a bespoke
        panel overrides this and ``App`` routes hit-testing through it, so the
        drawn positions and the clickable positions stay in lock-step."""
        return render.panel_rects()

    def panel_backdrop(self, surf, app):
        panel = pygame.Rect(PANEL_X, 0, PANEL_W, WINDOW_H)
        pygame.draw.rect(surf, theme.PANEL_BG, panel)

    def draw_button(self, surf, rect, label, *, active=True, enabled=True,
                    color=None, text_color=None):
        render._draw_button(surf, rect, label, self.fonts["small"],
                            active=active, enabled=enabled, color=color, text_color=text_color)

    def draw_panel(self, surf, app, status, check_lines):
        """Shared, fully-functional panel. Draws a skin-styled backdrop then the
        standard widgets at their canonical (clickable) positions. Subclasses
        usually override ``panel_backdrop`` / ``draw_button`` rather than this."""
        self.panel_backdrop(surf, app)
        qb, config = app.qb, app.config
        rects = self.panel_rects()
        x = PANEL_X + 20
        y = 20

        turn = config.team_name(qb.turn)
        name_surf = self.fonts["title"].render(turn, True, theme.team_label(qb.turn))
        surf.blit(name_surf, (x, y))
        rest = self.fonts["title"].render(" to move", True, theme.TEXT)
        surf.blit(rest, (x + name_surf.get_width(), y))

        if config.splitting_enabled:
            self.draw_button(surf, rects["mode"], f"Mode: {app.mode.upper()}  (M)",
                             active=(app.mode == "split"))
        else:
            self.draw_button(surf, rects["mode"], "Splitting disabled", enabled=False)
        self.draw_button(surf, rects["save"], "Save (F5)", active=False)
        self.draw_button(surf, rects["load"], "Load (F9)", active=False)
        if not qb.game_over:
            if app._confirm_surrender:
                self.draw_button(surf, rects["surrender"], "Confirm surrender? (click again)",
                                 color=theme.EVENT_ABSENT_COLOR, text_color=(20, 20, 20))
            else:
                self.draw_button(surf, rects["surrender"], "Surrender", active=False)
        self.draw_button(surf, rects["captured"],
                         f"Removed pieces: {'ON' if app.show_captured else 'OFF'} (C)",
                         active=app.show_captured)
        self.draw_button(surf, rects["check"],
                         f"Check warnings: {'ON' if app.show_check else 'OFF'} (K)",
                         active=app.show_check)
        y = rects["check"].bottom + 10

        if app.show_check and check_lines:
            for text, color in check_lines:
                surf.blit(self.fonts["body"].render(text, True, color), (x, y))
                y += 26
            y += 4

        cfg = self.fonts["small"].render(
            f"Collapse: {config.collapse_mode.value}   "
            f"Splitting: {'on' if config.splitting_enabled else 'off'}", True, theme.TEXT_DIM)
        surf.blit(cfg, (x, y)); y += 22
        surf.blit(self.fonts["small"].render("F11: Fullscreen   Tab: switch UI", True,
                                             theme.TEXT_DIM), (x, y)); y += 24
        if status:
            surf.blit(self.fonts["body"].render(status, True, theme.ACCENT), (x, y)); y += 30

        y = self.panel_extra(surf, app, x, y)
        y += 8
        pygame.draw.line(surf, theme.TEXT_DIM, (x, y), (PANEL_X + PANEL_W - 20, y), 1)
        y += 14
        self._draw_log_and_tray(surf, app, x, y)

        if qb.game_over and qb.winner is not None:
            banner = f"{config.team_name(qb.winner).upper()} WINS"
            bs = self.fonts["title"].render(banner, True, theme.team_label(qb.winner))
            surf.blit(bs, (x, rects["new_game"].y - 50))
            self.draw_button(surf, rects["new_game"], "New Game (N)")

    def panel_extra(self, surf, app, x, y):
        """Hook for extra panel content (e.g. Clarity's inspector) between the
        readout and the log divider. Returns the new y cursor."""
        return y

    # --------------------------------------------------------- info popovers
    def _popover_rect(self, anchor_rect, size):
        """Placement shared by the hover tooltip and the pinned inspector
        card: just outside ``anchor_rect`` (below it if the anchor sits in
        the board's top half, above otherwise, so the popover never covers
        the piece it's describing), clamped to stay fully inside the logical
        surface so an edge-file/rank token doesn't spill off-screen."""
        w, h = size
        board = self.board_rect()
        below = anchor_rect.centery < board.centery
        box = pygame.Rect(0, 0, w, h)
        box.centerx = anchor_rect.centerx
        if below:
            box.top = anchor_rect.bottom + theme.px(6)
        else:
            box.bottom = anchor_rect.top - theme.px(6)
        box.clamp_ip(pygame.Rect(0, 0, WINDOW_W, WINDOW_H))
        return box

    def _popover_bg(self, surf, box):
        bg = pygame.Surface(box.size, pygame.SRCALPHA)
        bg.fill((*theme.PANEL_BG, 235))
        surf.blit(bg, box.topleft)
        pygame.draw.rect(surf, self._tint(theme.TEXT_DIM, 140), box,
                         width=theme.px(1), border_radius=theme.px(6))

    def draw_pinned_highlight(self, surf, app):
        """Ring every ghost of the pinned piece (see draw_pinned_inspector) in
        its aura colour -- the visual half of the right-click pin, showing the
        whole superposed cloud at a glance rather than making you read the
        card's square list. Same "ring the square, aura colour, under the
        tokens" idiom `render.draw_plan_rings` already uses for a piece being
        planned."""
        sq = app.pinned_square
        if sq is None:
            return
        ghost = app.qb.ghost_at(sq)
        if ghost is None:
            return
        color = self._aura_color(ghost.piece_id)
        for g in app.qb.ghosts_of(ghost.piece_id):
            pygame.draw.rect(surf, color, render.square_rect(g.square), width=theme.px(4))

    def draw_pinned_inspector(self, surf, app):
        """The card half of the right-click pin (see
        ``App.handle_right_click`` / ``draw_pinned_highlight``): the piece's
        identity plus every ghost's square and probability as a bar, so a
        whole superposed cloud can be read at a glance without selecting it
        (selecting only works for your own piece on your own turn; this
        works for either side, any time)."""
        sq = app.pinned_square
        if sq is None:
            return
        ghost = app.qb.ghost_at(sq)
        if ghost is None:
            app.pinned_square = None
            return
        p = theme.px
        pid = ghost.piece_id
        gs = sorted(app.qb.ghosts_of(pid), key=lambda g: -float(g.prob))
        header_s = self.fonts["small"].render(app._piece_label(pid), True, self._aura_color(pid))
        hint_s = self.fonts["tiny"].render("right-click or Esc to close", True, theme.TEXT_DIM)
        pad = p(10)
        anchor = render.square_rect(sq)

        if len(gs) == 1:
            body_s = self.fonts["tiny"].render("solid -- probability 1", True, theme.TEXT_DIM)
            w = max(header_s.get_width(), body_s.get_width(), hint_s.get_width()) + pad * 2
            h = (header_s.get_height() + p(6) + body_s.get_height() + p(10)
                 + hint_s.get_height() + pad * 2)
            box = self._popover_rect(anchor, (w, h))
            self._popover_bg(surf, box)
            x, y = box.left + pad, box.top + pad
            surf.blit(header_s, (x, y)); y += header_s.get_height() + p(6)
            surf.blit(body_s, (x, y)); y += body_s.get_height() + p(10)
            surf.blit(hint_s, (x, y))
            return

        row_h, bar_w = p(20), p(90)
        rows = [(self.fonts["tiny"].render(chess.square_name(g.square), True, theme.TEXT),
                self.fonts["tiny"].render(render.frac_str(g.prob), True, theme.TEXT), float(g.prob))
                for g in gs]
        name_w = max(s.get_width() for s, _, _ in rows)
        frac_w = max(s.get_width() for _, s, _ in rows)
        w = max(header_s.get_width(), name_w + p(8) + bar_w + p(8) + frac_w,
                hint_s.get_width()) + pad * 2
        h = header_s.get_height() + p(6) + len(rows) * row_h + p(6) + hint_s.get_height() + pad * 2
        box = self._popover_rect(anchor, (w, h))
        self._popover_bg(surf, box)

        x, y = box.left + pad, box.top + pad
        surf.blit(header_s, (x, y))
        y += header_s.get_height() + p(6)
        for name_s, frac_s, frac in rows:
            surf.blit(name_s, (x, y + row_h // 2 - name_s.get_height() // 2))
            track = pygame.Rect(x + name_w + p(8), y + row_h // 2 - p(5), bar_w, p(10))
            self._hbar(surf, track, frac, self._aura_color(pid), self._tint(theme.TEXT_DIM, 90),
                      radius=p(4))
            surf.blit(frac_s, (track.right + p(8), y + row_h // 2 - frac_s.get_height() // 2))
            y += row_h
        y += p(6)
        surf.blit(hint_s, (x, y))

    def _draw_log_and_tray(self, surf, app, x, log_top, bottom=None):
        p = theme.px
        qb, config = app.qb, app.config
        rects = self.panel_rects()
        panel_right = PANEL_X + PANEL_W - p(20)
        default_bottom = (rects["new_game"].y - p(60)) if qb.game_over else (WINDOW_H - p(16))
        bottom_limit = min(default_bottom, bottom) if bottom is not None else default_bottom

        if app.show_captured:
            tray_width, col_gap = p(130), p(18)
            tray_x = panel_right - tray_width
            log_right = tray_x - col_gap
            pygame.draw.line(surf, theme.TEXT_DIM, (tray_x - col_gap // 2, log_top),
                             (tray_x - col_gap // 2, bottom_limit), p(1))
        else:
            log_right = panel_right

        line_h = p(20)
        max_width = log_right - x
        max_lines = max(0, (bottom_limit - log_top) // line_h)
        name_colors = {
            config.team_name(chess.WHITE): theme.team_label(chess.WHITE),
            config.team_name(chess.BLACK): theme.team_label(chess.BLACK),
        }
        wrapped = []
        for line in app.log:
            wrapped.extend(render.wrap_line(line, self.fonts["small"], max_width))
        y = log_top
        for line in (wrapped[-max_lines:] if max_lines else []):
            render.draw_log_line(surf, line, (x, y), self.fonts["small"], theme.TEXT, name_colors)
            y += line_h

        if app.show_captured:
            removed = [p for p in qb.pieces.values() if not p.alive]
            removed.sort(key=lambda p: render._CAPTURED_ORDER.index(p.ptype)
                         if p.ptype in render._CAPTURED_ORDER else len(render._CAPTURED_ORDER))
            white = [p for p in removed if p.color == chess.WHITE]
            black = [p for p in removed if p.color == chess.BLACK]
            icon_r = render.fit_captured_icon_radius(tray_width, bottom_limit - log_top,
                                                      len(white), len(black))
            ty = render._draw_captured_column(surf, self.fonts["small"], self.fonts["icon"],
                                              config.team_name(chess.WHITE), white,
                                              chess.WHITE, tray_x, log_top, panel_right, icon_r=icon_r)
            ty += p(10)
            render._draw_captured_column(surf, self.fonts["small"], self.fonts["icon"],
                                         config.team_name(chess.BLACK), black,
                                         chess.BLACK, tray_x, ty, panel_right, icon_r=icon_r)

    # ------------------------------------------------------------ promotion
    def draw_promotion(self, surf, app):
        render.draw_promotion_picker(surf, app.qb.turn, self.fonts)
