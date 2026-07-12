"""Variant C -- Clarity / Data-viz.

Optimised for *reading the quantum state at a glance*. Every ghost wears a
**probability donut** (a filled arc, thickness constant, sweep proportional to
probability) so two ghosts' odds are comparable across the whole board without
mental math. A piece's superposed ghosts always share a coloured **halo** and a
thin connecting **web** -- no need to select to see the cloud. Legal destinations
are **labeled chips** (move / merge / risk n/n) instead of bare dots, and the
side panel gains an **inspector** showing the selected piece's full distribution
as horizontal bars. Flat, high-contrast, accessible.
"""

from __future__ import annotations

import math

import chess
import pygame

from .. import render, theme
from .base import (BaseSkin, PANEL_X, PANEL_W, WINDOW_H, SQUARE)


class ClaritySkin(BaseSkin):
    name = "Clarity / Data-viz"
    blurb = "probability donuts, always-on sibling halos, labeled chips, inspector panel"

    def square_color(self, square, light):
        base = theme.LIGHT_SQUARE if light else theme.DARK_SQUARE
        # push contrast up so tokens + donuts pop
        return self._mix(base, (255, 255, 255), 0.10) if light else self._mix(base, (0, 0, 0), 0.12)

    def draw_sibling_web(self, surf, app):
        qb = app.qb
        seen = set()
        for ghost in qb.ghosts:
            pid = ghost.piece_id
            if pid in seen or qb.is_solid(pid):
                continue
            seen.add(pid)
            gs = qb.ghosts_of(pid)
            if len(gs) < 2:
                continue
            centers = [render.square_rect(g.square).center for g in gs]
            col = self._aura_color(pid)
            for i in range(len(centers)):
                for j in range(i + 1, len(centers)):
                    pygame.draw.line(surf, self._tint(col, 55), centers[i], centers[j], 2)
            for c in centers:
                pygame.draw.circle(surf, col, c, int(SQUARE * 0.44), width=2)

    def draw_token(self, surf, color, ptype, center, *, alpha=255, radius=None, solid=True):
        r = radius if radius is not None else int(SQUARE * 0.34)
        fill, border, ink = self._token_colors(color)
        tok = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(tok, (*fill, alpha), (r, r), r)
        pygame.draw.circle(tok, (*border, alpha), (r, r), r, width=3)
        glyph = self.fonts["piece"].render(theme.GLYPH[ptype], True, (*ink, alpha))
        tok.blit(glyph, glyph.get_rect(center=(r, r)))
        surf.blit(tok, tok.get_rect(center=center))

    def draw_ghost_prob(self, surf, ghost, center, color, alpha=255):
        rect = render.square_rect(ghost.square)
        r = int(SQUARE * 0.44)
        arc = pygame.Rect(0, 0, r * 2, r * 2)
        arc.center = rect.center
        frac = float(ghost.prob)
        pygame.draw.arc(surf, self._tint(theme.TEXT_DIM, 120), arc, 0, 2 * math.pi, 7)
        start = math.pi / 2
        pygame.draw.arc(surf, theme.ACCENT, arc, start - 2 * math.pi * frac, start, 7)
        # Chip uses the piece's OWN body/ink pair (not the neutral accent) so
        # the fraction reads as "this piece's number", and keeps solid
        # contrast against the board regardless of which team it belongs to.
        fill, _, ink = self._token_colors(color)
        self._chip(surf, render.frac_str(ghost.prob), (rect.centerx, rect.bottom - 12),
                   fill, ink)

    def draw_legal(self, surf, app, legal, warnings):
        # Same ring language as Polished: solid ring = move, double ring =
        # merge, dotted ring = risky contact -- cleaner than dot+text chips
        # and reads consistently with the donuts already used for probability.
        r = int(SQUARE * 0.40)
        for sq, kind in legal.items():
            c = render.square_rect(sq).center
            if kind == "merge":
                pygame.draw.circle(surf, theme.LEGAL_MERGE_DOT, c, r, width=3)
                pygame.draw.circle(surf, theme.LEGAL_MERGE_DOT, c, r - 7, width=2)
            elif kind == "contact":
                self._dotted_ring(surf, c, r, theme.LEGAL_CONTACT_DOT)
            else:
                pygame.draw.circle(surf, theme.LEGAL_MOVE_DOT, c, r, width=4)
        if warnings:
            for sq, prob in warnings.items():
                render._draw_danger_marker(surf, sq, prob, self.fonts)

    def draw_selection(self, surf, app):
        qb, sel = app.qb, app.selected
        if sel is not None:
            p = self.pulse()
            pygame.draw.rect(surf, self._mix(theme.SELECTED_RING, (255, 255, 255), 0.3 * p),
                             render.square_rect(sel), width=5)
        if app.split_pick_a is not None:
            pygame.draw.rect(surf, theme.SPLIT_PICK_RING,
                             render.square_rect(app.split_pick_a), width=5)

    # ------------------------------------------------------------- data panel
    #: fixed geometry shared between ``panel_rects`` (hit-testing) and
    #: ``draw_panel`` (drawing) -- keep these two in lock-step by hand rather
    #: than deriving one from the other, since ``panel_rects`` must stay a
    #: pure function of nothing (``App.handle_mouse_down`` calls it without a
    #: board to draw against).
    _HERO_Y, _HERO_H = 14, 68

    def panel_rects(self):
        x = PANEL_X + 18
        right = PANEL_X + PANEL_W - 18
        w = right - x
        half = (w - 10) // 2
        return {
            "mode": pygame.Rect(x, 108, w, 36),
            "save": pygame.Rect(x, 150, half, 30),
            "load": pygame.Rect(x + half + 10, 150, half, 30),
            "surrender": pygame.Rect(x, 186, w, 30),
            "captured": pygame.Rect(x, 222, half, 30),
            "check": pygame.Rect(x + half + 10, 222, half, 30),
            "view": pygame.Rect(x, 258, half, 30),
            "quit": pygame.Rect(x + half + 10, 258, half, 30),
            "settings": pygame.Rect(x, 294, w, 30),
            "new_game": pygame.Rect(x, WINDOW_H - 92, w, 44),
        }

    def panel_backdrop(self, surf, app):
        panel = pygame.Rect(PANEL_X, 0, PANEL_W, WINDOW_H)
        pygame.draw.rect(surf, theme.PANEL_BG, panel)
        pygame.draw.line(surf, self._tint(theme.TEXT_DIM, 120),
                         (PANEL_X, 0), (PANEL_X, WINDOW_H), 1)

    def _flat_button(self, surf, rect, label, *, active=False, danger=False, enabled=True):
        if danger:
            bg, fg = theme.EVENT_ABSENT_COLOR, (16, 16, 18)
        elif not enabled:
            bg, fg = self._mix(theme.PANEL_BG, (0, 0, 0), 0.15), theme.TEXT_DIM
        elif active:
            bg, fg = theme.ACCENT, (16, 16, 18)
        else:
            bg, fg = self._mix(theme.PANEL_BG, (255, 255, 255), 0.08), theme.TEXT
        pygame.draw.rect(surf, bg, rect)
        pygame.draw.rect(surf, self._tint(theme.TEXT_DIM, 110), rect, width=1)
        s = self.fonts["small"].render(label, True, fg)
        surf.blit(s, s.get_rect(center=rect.center))

    def _segmented(self, surf, rect, labels, active_i, enabled=True):
        n = len(labels)
        pygame.draw.rect(surf, self._mix(theme.PANEL_BG, (255, 255, 255), 0.06), rect)
        for i, lab in enumerate(labels):
            seg = pygame.Rect(rect.x + i * rect.w // n, rect.y,
                              rect.w // n if i < n - 1 else rect.w - i * rect.w // n, rect.h)
            on = enabled and i == active_i
            if on:
                pygame.draw.rect(surf, theme.ACCENT, seg)
            fg = (16, 16, 18) if on else (theme.TEXT if enabled else theme.TEXT_DIM)
            s = self.fonts["small"].render(lab, True, fg)
            surf.blit(s, s.get_rect(center=seg.center))
        pygame.draw.rect(surf, self._tint(theme.TEXT_DIM, 110), rect, width=1)
        pygame.draw.line(surf, self._tint(theme.TEXT_DIM, 110),
                         (rect.centerx, rect.y), (rect.centerx, rect.bottom), 1)

    def _switch(self, surf, rect, label, on):
        s = self.fonts["small"].render(label, True, theme.TEXT if on else theme.TEXT_DIM)
        surf.blit(s, (rect.x + 4, rect.centery - s.get_height() // 2))
        track = pygame.Rect(0, 0, 34, 16)
        track.midright = (rect.right - 4, rect.centery)
        col = theme.LEGAL_MOVE_DOT if on else self._tint(theme.TEXT_DIM, 120)
        pygame.draw.rect(surf, col, track, border_radius=8)
        knob = track.right - 8 if on else track.left + 8
        pygame.draw.circle(surf, (245, 245, 245), (knob, track.centery), 6)

    def _safety_bar(self, surf, x, y, w, name, prob, cbool):
        surf.blit(self.fonts["small"].render(name, True, theme.team_label(cbool)), (x, y))
        danger = prob > 0
        col = theme.EVENT_ABSENT_COLOR if danger else theme.LEGAL_MOVE_DOT
        word = render.frac_str(prob) if danger else theme.TERMS["safe_word"]
        ws = self.fonts["small"].render(word, True, col)
        surf.blit(ws, (x + w - ws.get_width(), y))
        self._hbar(surf, pygame.Rect(x, y + 20, w, 6), float(prob), col,
                   self._tint(theme.TEXT_DIM, 90), radius=3)

    def draw_panel(self, surf, app, status, check_lines):
        self.panel_backdrop(surf, app)
        qb, config = app.qb, app.config
        rects = self.panel_rects()
        x = PANEL_X + 18
        right = PANEL_X + PANEL_W - 18
        w = right - x

        # --- turn header --------------------------------------------------
        # Structurally this is HUD's "ACTIVE UNIT" idea (a framed block that
        # names whose turn it is *and* carries a live mode readout) rather
        # than a bare colour swatch -- reskinned flat and hairline-bordered,
        # no glow/shadow, to match the rest of Clarity's data-panel language.
        hero = pygame.Rect(x, self._HERO_Y, w, self._HERO_H)
        pygame.draw.rect(surf, self._mix(theme.PANEL_BG, (255, 255, 255), 0.05), hero)
        pygame.draw.rect(surf, self._tint(theme.TEXT_DIM, 110), hero, width=1)
        pygame.draw.rect(surf, theme.team_label(qb.turn), (hero.x, hero.y, 6, hero.h))
        self.draw_token(surf, qb.turn, chess.KING, (hero.x + 42, hero.centery), radius=24)
        surf.blit(self.fonts["hero"].render(config.team_name(qb.turn), True, theme.TEXT),
                  (hero.x + 74, hero.y + 10))
        self._caps_label(surf, "to move", (hero.x + 76, hero.y + 42))
        if config.splitting_enabled:
            mode_col = theme.SPLIT_PICK_RING if app.mode == "split" else theme.LEGAL_MOVE_DOT
            self._chip(surf, app.mode.upper(), (hero.right - 34, hero.y + 18),
                       mode_col, (16, 16, 18))

        # --- controls ---------------------------------------------------------
        self._caps_label(surf, "controls", (x, hero.bottom + 8), rule_to=right)
        if config.splitting_enabled:
            self._segmented(surf, rects["mode"], ["MOVE", "SPLIT"],
                            1 if app.mode == "split" else 0)
        else:
            self._segmented(surf, rects["mode"], ["MOVE", "SPLIT"], 0, enabled=False)
        self._flat_button(surf, rects["save"], "Save  F5")
        self._flat_button(surf, rects["load"], "Load  F9")
        if not qb.game_over:
            self._flat_button(surf, rects["surrender"],
                              "Confirm surrender?" if app._confirm_surrender else "Surrender",
                              danger=app._confirm_surrender)
        self._switch(surf, rects["captured"], "Removed", app.show_captured)
        self._switch(surf, rects["check"], "Threats", app.show_check)
        self._segmented(surf, rects["view"], ["CLARITY", "HUD"], app.skin_index)
        self._flat_button(surf, rects["quit"],
                          "Confirm quit?" if app._confirm_quit else "Quit",
                          danger=app._confirm_quit)
        self._flat_button(surf, rects["settings"], "Settings  (O)")

        # --- king safety ------------------------------------------------------
        y = rects["settings"].bottom + 16
        if app.show_check:
            self._caps_label(surf, "king safety", (x, y), rule_to=right)
            y += 20
            for name, prob, cbool in self._check_values(app):
                self._safety_bar(surf, x, y, w, name, prob, cbool)
                y += 34
        else:
            y += 4

        # --- selected-piece inspector ----------------------------------------
        if app.selected is not None and qb.ghost_at(app.selected) is not None:
            self._caps_label(surf, "selected", (x, y), rule_to=right)
            y = self.panel_extra(surf, app, x, y + 20)
        y += 6

        if status:
            surf.blit(self.fonts["body"].render(status, True, theme.ACCENT), (x, y))
            y += 28

        # --- log --------------------------------------------------------------
        self._caps_label(surf, "game log", (x, y), rule_to=right)
        y += 18
        footer_y = WINDOW_H - 40
        self._draw_log_and_tray(surf, app, x, y,
                                bottom=(footer_y - 8 if not qb.game_over else None))

        # --- footer -----------------------------------------------------------
        cfg = (f"Collapse {config.collapse_mode.value} · "
               f"Split {'on' if config.splitting_enabled else 'off'}")
        surf.blit(self.fonts["tiny"].render(cfg.upper(), True, theme.TEXT_DIM), (x, footer_y))
        surf.blit(self.fonts["tiny"].render("F11 FULLSCREEN · TAB SWITCH UI", True,
                                            theme.TEXT_DIM), (x, footer_y + 16))

        # --- game over --------------------------------------------------------
        if qb.game_over and qb.winner is not None:
            banner = f"{config.team_name(qb.winner).upper()} WINS"
            bs = self.fonts["title"].render(banner, True, theme.team_label(qb.winner))
            surf.blit(bs, (x, rects["new_game"].y - 42))
            self._flat_button(surf, rects["new_game"], "New Game  (N)", active=True)

    # -------------------------------------------------------- inspector panel
    def panel_extra(self, surf, app, x, y):
        qb = app.qb
        sel = app.selected
        if sel is None:
            return y
        ghost = qb.ghost_at(sel)
        if ghost is None:
            return y
        pid = ghost.piece_id
        gs = sorted(qb.ghosts_of(pid), key=lambda g: -float(g.prob))
        piece = qb.pieces[pid]
        head = f"{app.config.team_name(piece.color)} {chess.piece_name(piece.ptype).capitalize()}"
        surf.blit(self.fonts["small"].render(head, True, self._aura_color(pid)), (x, y))
        y += 22
        bar_w = PANEL_X + theme.PANEL_WIDTH - 18 - (x + 44) - 40
        for g in gs:
            frac = float(g.prob)
            surf.blit(self.fonts["small"].render(chess.square_name(g.square), True, theme.TEXT),
                      (x, y))
            track = pygame.Rect(x + 44, y + 2, bar_w, 14)
            pygame.draw.rect(surf, self._tint(theme.TEXT_DIM, 90), track, border_radius=4)
            pygame.draw.rect(surf, theme.ACCENT,
                             (track.x, track.y, max(3, int(bar_w * frac)), 14), border_radius=4)
            fs = self.fonts["tiny"].render(render.frac_str(g.prob), True, theme.TEXT)
            surf.blit(fs, (track.right + 6, y))
            y += 22
        return y + 4
