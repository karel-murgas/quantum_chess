"""Variant B -- Quantum HUD.

A sci-fi command console. Neon grid board inside an angular bezel with corner
brackets; holographic tokens (glowing ring, translucent core); each ghost wears
an *orbiting probability ring* (arc sweep proportional to probability) instead of
a corner fraction; a piece's superposed ghosts are always joined by faint
*entanglement lines* so you read the cloud without selecting; collapses glitch,
dim and bloom the board. Monospace, bracketed HUD panel modules. Leans all the
way into "theme is a world."
"""

from __future__ import annotations

import math
import random

import chess
import pygame

from .. import render, theme, pieces
from .base import (BaseSkin, BOARD_MARGIN, BOARD_PIXELS, PANEL_X, PANEL_W,
                   WINDOW_H, WINDOW_W, SQUARE)


class HudSkin(BaseSkin):
    name = "Quantum HUD"
    blurb = "neon console: orbiting probability rings, entanglement webs, glitch collapse"
    FAMILY = "consolas"
    MONO = "consolas"

    def _accent(self):
        return theme.ACCENT

    def draw_background(self, surf, app):
        surf.fill(self._mix(theme.BG, (0, 0, 0), 0.4))
        # faint full-screen grid
        step = 40
        col = self._tint(self._accent(), 16)
        grid = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        for gx in range(0, WINDOW_W, step):
            pygame.draw.line(grid, col, (gx, 0), (gx, WINDOW_H))
        for gy in range(0, WINDOW_H, step):
            pygame.draw.line(grid, col, (0, gy), (WINDOW_W, gy))
        surf.blit(grid, (0, 0))

    def square_color(self, square, light):
        base = theme.LIGHT_SQUARE if light else theme.DARK_SQUARE
        return self._mix(base, (6, 10, 18), 0.62 if not light else 0.5)

    def draw_board(self, surf, app):
        super().draw_board(surf, app)
        br = self.board_rect()
        # neon grid overlay on square boundaries
        neon = pygame.Surface((br.w + 1, br.h + 1), pygame.SRCALPHA)
        for i in range(9):
            a = self._tint(self._accent(), 40)
            pygame.draw.line(neon, a, (i * SQUARE, 0), (i * SQUARE, br.h))
            pygame.draw.line(neon, a, (0, i * SQUARE), (br.w, i * SQUARE))
        surf.blit(neon, br.topleft)
        self._corner_brackets(surf, br.inflate(theme.px(16), theme.px(16)), self._accent(),
                              theme.px(26), theme.px(3))

    def _corner_brackets(self, surf, rect, color, size, w):
        pts = [
            ((rect.left, rect.top), (1, 0), (0, 1)),
            ((rect.right, rect.top), (-1, 0), (0, 1)),
            ((rect.left, rect.bottom), (1, 0), (0, -1)),
            ((rect.right, rect.bottom), (-1, 0), (0, -1)),
        ]
        for (px, py), (dx1, dy1), (dx2, dy2) in pts:
            pygame.draw.line(surf, color, (px, py), (px + dx1 * size, py + dy1 * size), w)
            pygame.draw.line(surf, color, (px, py), (px + dx2 * size, py + dy2 * size), w)

    def draw_sibling_web(self, surf, app):
        qb = app.qb
        seen = set()
        web = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        for ghost in qb.ghosts:
            pid = ghost.piece_id
            if pid in seen or qb.is_solid(pid):
                continue
            seen.add(pid)
            centers = [render.square_rect(g.square).center for g in qb.ghosts_of(pid)]
            if len(centers) < 2:
                continue
            cx = sum(c[0] for c in centers) / len(centers)
            cy = sum(c[1] for c in centers) / len(centers)
            col = self._tint(self._aura_color(pid), 70)
            for c in centers:
                pygame.draw.line(web, col, (cx, cy), c, theme.px(2))
            pygame.draw.circle(web, self._tint(self._aura_color(pid), 120), (int(cx), int(cy)),
                               theme.px(3))
        surf.blit(web, (0, 0))

    # A hologram's identity comes from its projector colour (the ring/glow --
    # each side's own accent), not its body: the body itself stays a bright,
    # legible white-hot core for every piece so the glyph never gets lost
    # (the old per-team dark-mixed fill made low-probability ghosts read as
    # featureless smudges). Ink is a fixed dark tone so it reads against that
    # bright core regardless of side.
    HOLO_BODY = (232, 244, 248)
    HOLO_INK = (14, 18, 24)

    #: floor under the ring/glow alpha -- team identity (which side a ghost
    #: belongs to) must stay legible even at low probability; only the body
    #: and glyph (the "how likely is it really here" signal) fade with prob.
    RING_ALPHA_FLOOR = 220

    def _team_wash(self, surf, color, center, r):
        """A faint team-coloured backdrop behind every token, bigger than the
        ring itself -- a third, square-scale cue for "whose square is this"
        that reads even before the eye resolves the ring or glyph."""
        _, border, _ = self._token_colors(color)
        size = int(r * 2.35)
        wash = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.rect(wash, (*border, 32), wash.get_rect(), border_radius=int(size * 0.22))
        surf.blit(wash, wash.get_rect(center=center))

    def draw_token(self, surf, color, ptype, center, *, alpha=255, radius=None, solid=True):
        r = radius if radius is not None else int(SQUARE * 0.40)
        # Non-unicode sets show real piece art instead of the holographic
        # glyph-in-a-disc; keep the subtle team wash so the HUD still frames
        # each piece with its side colour, then blit the art on top.
        if pieces.active(color) != "unicode":
            self._team_wash(surf, color, center, r)
            render.blit_piece_art(surf, color, ptype, center, int(SQUARE * 0.36), alpha)
            return
        _, border, _ = self._token_colors(color)
        self._team_wash(surf, color, center, r)
        tok = pygame.Surface((r * 2 + 8, r * 2 + 8), pygame.SRCALPHA)
        c = (r + 4, r + 4)
        ring_alpha = max(alpha, self.RING_ALPHA_FLOOR)
        # glow, in the piece's own team accent colour -- not scaled down by
        # probability, so a faint ghost never reads as "the other team's colour"
        for gr, ga in ((r + 3, 55), (r + 1, 85)):
            pygame.draw.circle(tok, (*border, ga), c, gr)
        core_a = int((150 if not solid else 210) * alpha / 255)
        pygame.draw.circle(tok, (*self.HOLO_BODY, core_a), c, r)
        # a bolder ring than before -- team colour should read at a glance,
        # not just on close inspection
        pygame.draw.circle(tok, (*border, ring_alpha), c, r,
                           width=theme.px(3) if not solid else theme.px(4))
        glyph = self.fonts["piece"].render(theme.GLYPH[ptype], True, (*self.HOLO_INK, alpha))
        tok.blit(glyph, glyph.get_rect(center=c))
        surf.blit(tok, tok.get_rect(center=center))

    def draw_ghost_prob(self, surf, ghost, center, color, alpha=255):
        rect = render.square_rect(ghost.square)
        # Snug against the token's own border ring (drawn at core radius
        # SQUARE*0.40 in draw_token) so the probability meter reads as one
        # continuous ring hugging the piece, not a separate floating halo
        # with a gap -- and thick enough (like Clarity's donut) to read as
        # a meter rather than a stray hairline.
        core_r = int(SQUARE * 0.40)
        ring_w = theme.px(6)
        r = core_r + ring_w // 2 + theme.px(1)
        arc = pygame.Rect(0, 0, r * 2, r * 2)
        arc.center = rect.center
        frac = float(ghost.prob)
        _, border, _ = self._token_colors(color)
        # Background "track" is a neutral dim tone, NOT the team colour at
        # lower alpha -- the old version tinted the *same* hue for the empty
        # portion, so against a coloured board square the whole ring just
        # read as one solid circle regardless of the actual fraction. Only
        # the foreground arc (the real "how much is filled") uses the team
        # colour, so partial fractions are visibly partial.
        pygame.draw.arc(surf, self._tint(theme.TEXT_DIM, 140), arc, 0, 2 * math.pi, ring_w)
        start = math.pi / 2
        pygame.draw.arc(surf, border, arc, start - 2 * math.pi * frac, start, ring_w)
        # The fraction text itself sits on a small HOLO_BODY chip and reads in
        # HOLO_INK -- the token's own body/ink pair, not the neon team colour
        # -- since drawing it bare in `border` directly on the neon ring/grid
        # made it blend in and become illegible (the original bug report).
        # Reuses BaseSkin._chip (same helper Clarity uses) rather than a
        # bespoke alpha-surface build, so the text centring is identical to
        # Clarity's already-correct behaviour.
        self._chip(surf, render.frac_str(ghost.prob), (rect.centerx, rect.bottom - theme.px(12)),
                   self.HOLO_BODY, self.HOLO_INK)

    def draw_legal(self, surf, app, legal, warnings):
        r = int(SQUARE * 0.30)
        colmap = {"merge": theme.LEGAL_MERGE_DOT, "contact": theme.LEGAL_CONTACT_DOT}
        for sq, kind in legal.items():
            c = render.square_rect(sq).center
            color = colmap.get(kind, theme.LEGAL_MOVE_DOT)
            # target reticle: diamond + center dot
            pts = [(c[0], c[1] - r), (c[0] + r, c[1]), (c[0], c[1] + r), (c[0] - r, c[1])]
            pygame.draw.lines(surf, color, True, pts, theme.px(2))
            pygame.draw.circle(surf, color, c, theme.px(4))
        if warnings:
            for sq, prob in warnings.items():
                render._draw_danger_marker(surf, sq, prob, self.fonts)

    def draw_selection(self, surf, app):
        qb, sel = app.qb, app.selected
        inf = theme.px(8)
        if sel is not None:
            ghost = qb.ghost_at(sel)
            if ghost is not None:
                for g in qb.ghosts_of(ghost.piece_id):
                    self._corner_brackets(surf, render.square_rect(g.square).inflate(-inf, -inf),
                                          self._aura_color(ghost.piece_id), theme.px(14), theme.px(2))
            pl = self.pulse()
            self._corner_brackets(surf, render.square_rect(sel).inflate(-theme.px(4), -theme.px(4)),
                                  self._mix(theme.SELECTED_RING, (255, 255, 255), 0.3 * pl),
                                  theme.px(20), theme.px(3))
        if app.split_pick_a is not None:
            self._corner_brackets(surf, render.square_rect(app.split_pick_a).inflate(-theme.px(4), -theme.px(4)),
                                  theme.SPLIT_PICK_RING, theme.px(20), theme.px(3))

    def collapse_overlay(self, surf, app, beat, t):
        br = self.board_rect()
        # dim the field
        dim = pygame.Surface((br.w, br.h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, int(70 * math.sin(math.pi * t))))
        surf.blit(dim, br.topleft)
        if beat.flash_square is None or beat.flash_present:
            return  # a positive ("really there") reveal is clean -- no glitch
        if beat.flash_role in ("mover", "split", "promotion"):
            # the acting piece's own wave function fizzled -- the dramatic
            # moment of the turn, so glitch the whole board.
            self._glitch_region(surf, br, t, n=4, max_dx=14, slice_h=(6, 18))
        else:
            # a blocker/target measured along the way wasn't there -- a minor
            # aside, not the main event, so only that square glitches.
            sq_rect = render.square_rect(beat.flash_square).inflate(4, 4).clip(br)
            self._glitch_region(surf, sq_rect, t, n=2, max_dx=5, slice_h=(4, 9))

    def _glitch_region(self, surf, region, t, *, n, max_dx, slice_h):
        """A few offset horizontal slices with a chromatic tint, confined to
        ``region`` -- the whole board for a big glitch, one square for a small
        local one."""
        if region.w <= 0 or region.h <= 0:
            return
        snap = surf.subsurface(region).copy()
        intensity = math.sin(math.pi * t)
        min_h, max_h = slice_h
        for _ in range(n):
            sh = min(random.randint(min_h, max_h), region.h)
            sy = random.randint(0, max(0, region.h - sh))
            dxo = random.randint(-max_dx, max_dx)
            slice_rect = pygame.Rect(0, sy, region.w, sh)
            piece = snap.subsurface(slice_rect).copy()
            tint = pygame.Surface(piece.get_size(), pygame.SRCALPHA)
            tint.fill((*self._accent(), int(60 * intensity)))
            piece.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
            surf.blit(piece, (region.x + dxo, region.y + sy))

    # ------------------------------------------------------------- HUD panel
    def panel_rects(self):
        p = theme.px
        x = PANEL_X + p(16)
        right = PANEL_X + PANEL_W - p(16)
        w = right - x
        half = (w - p(8)) // 2
        return {
            "mode": pygame.Rect(x, p(86), w, p(30)),
            "captured": pygame.Rect(x, p(120), w, p(30)),
            "check": pygame.Rect(x, p(154), w, p(30)),
            "save": pygame.Rect(x, p(192), half, p(30)),
            "load": pygame.Rect(x + half + p(8), p(192), half, p(30)),
            "surrender": pygame.Rect(x, p(226), w, p(30)),
            "view": pygame.Rect(x, p(260), half, p(30)),
            "quit": pygame.Rect(x + half + p(8), p(260), half, p(30)),
            "settings": pygame.Rect(x, p(294), w, p(30)),
            "new_game": pygame.Rect(x, WINDOW_H - p(92), w, p(44)),
        }

    def panel_backdrop(self, surf, app):
        panel = pygame.Rect(PANEL_X, 0, PANEL_W, WINDOW_H)
        pygame.draw.rect(surf, self._mix(theme.PANEL_BG, (0, 0, 0), 0.35), panel)
        # scanlines
        scan = pygame.Surface((PANEL_W, WINDOW_H), pygame.SRCALPHA)
        for y in range(0, WINDOW_H, 4):
            pygame.draw.line(scan, (0, 0, 0, 40), (0, y), (PANEL_W, y))
        surf.blit(scan, panel.topleft)
        pygame.draw.line(surf, self._accent(), (PANEL_X + 1, 0), (PANEL_X + 1, WINDOW_H), 2)

    def draw_button(self, surf, rect, label, *, active=True, enabled=True,
                    color=None, text_color=None):
        if color is not None:
            base, txt = color, text_color or (10, 10, 10)
        elif not enabled:
            base, txt = self._mix(theme.PANEL_BG, (0, 0, 0), 0.2), theme.TEXT_DIM
        elif active:
            base, txt = self._accent(), (10, 12, 16)
        else:
            base, txt = self._mix(theme.PANEL_BG, (0, 0, 0), 0.1), theme.TEXT
        pygame.draw.rect(surf, base, rect)
        pygame.draw.rect(surf, self._accent() if enabled else theme.TEXT_DIM, rect, width=theme.px(1))
        self._corner_brackets(surf, rect, self._accent() if enabled else theme.TEXT_DIM,
                              theme.px(8), theme.px(2))
        s = self.fonts["small"].render(label, True, txt)
        surf.blit(s, s.get_rect(center=rect.center))

    def _module(self, surf, rect, title):
        """A bracketed console module box with a title tab; returns inner top y."""
        p = theme.px
        pygame.draw.rect(surf, self._mix(theme.PANEL_BG, (0, 0, 0), 0.2), rect)
        self._corner_brackets(surf, rect, self._accent(), p(12), p(2))
        if title:
            t = self.fonts["tiny"].render(title, True, self._accent())
            tab = pygame.Rect(rect.x + p(10), rect.y - t.get_height() // 2 - p(1),
                              t.get_width() + p(10), t.get_height() + p(2))
            pygame.draw.rect(surf, self._mix(theme.PANEL_BG, (0, 0, 0), 0.35), tab)
            surf.blit(t, (tab.x + p(5), tab.y + p(1)))
        return rect.y + p(8)

    def _toggle_row(self, surf, rect, key, label, value, lit):
        """A terminal toggle line: ``[K] LABEL ... VALUE`` with a state LED."""
        p = theme.px
        base = self._mix(theme.PANEL_BG, (0, 0, 0), 0.1)
        pygame.draw.rect(surf, base, rect)
        edge = self._accent() if lit else theme.TEXT_DIM
        pygame.draw.rect(surf, edge, rect, width=p(1))
        pygame.draw.circle(surf, edge, (rect.x + p(12), rect.centery), p(4))
        lab = self.fonts["small"].render(f"[{key}] {label}", True,
                                         theme.TEXT if lit else theme.TEXT_DIM)
        surf.blit(lab, (rect.x + p(24), rect.centery - lab.get_height() // 2))
        val = self.fonts["small"].render(value, True, self._accent() if lit else theme.TEXT_DIM)
        surf.blit(val, (rect.right - val.get_width() - p(10),
                        rect.centery - val.get_height() // 2))

    def _mode_row(self, surf, rect, key, mode_value, enabled=True):
        """MOVE/SPLIT are two equally-active states, not an on/off pair --
        unlike `_toggle_row`'s lit/dim-grey pattern (which reads as
        enabled/disabled), both modes render fully lit here, just in a
        different accent: green for MOVE, blue for SPLIT (reusing the same
        hues the board already uses for legal-move dots / the split-pick
        ring). Only "splitting disabled" for the match actually dims to grey."""
        if not enabled:
            col, value = theme.TEXT_DIM, "LOCKED"
        else:
            col = theme.SPLIT_PICK_RING if mode_value == "split" else theme.LEGAL_MOVE_DOT
            value = mode_value.upper()
        p = theme.px
        tint = pygame.Surface(rect.size, pygame.SRCALPHA)
        tint.fill(self._tint(col, 26) if enabled else self._mix(theme.PANEL_BG, (0, 0, 0), 0.2))
        surf.blit(tint, rect.topleft)
        pygame.draw.rect(surf, col, rect, width=p(1))
        pygame.draw.circle(surf, col, (rect.x + p(12), rect.centery), p(4))
        lab = self.fonts["small"].render(f"[{key}] MODE", True, theme.TEXT if enabled else theme.TEXT_DIM)
        surf.blit(lab, (rect.x + p(24), rect.centery - lab.get_height() // 2))
        val = self.fonts["small"].render(value, True, col)
        surf.blit(val, (rect.right - val.get_width() - p(10),
                        rect.centery - val.get_height() // 2))

    def _view_row(self, surf, rect, key, value):
        """Which UI this is -- like `_mode_row`'s MOVE/SPLIT, two equally
        valid choices rather than an on/off toggle, so it's always fully lit
        (never dims to the `_toggle_row` disabled grey)."""
        p = theme.px
        col = self._accent()
        tint = pygame.Surface(rect.size, pygame.SRCALPHA)
        tint.fill(self._tint(col, 26))
        surf.blit(tint, rect.topleft)
        pygame.draw.rect(surf, col, rect, width=p(1))
        pygame.draw.circle(surf, col, (rect.x + p(12), rect.centery), p(4))
        lab = self.fonts["small"].render(f"[{key}] VIEW", True, theme.TEXT)
        surf.blit(lab, (rect.x + p(24), rect.centery - lab.get_height() // 2))
        val = self.fonts["small"].render(value, True, col)
        surf.blit(val, (rect.right - val.get_width() - p(10),
                        rect.centery - val.get_height() // 2))

    def _threat_gauge(self, surf, x, y, w, name, prob, cbool):
        head = self.fonts["small"].render(name, True, theme.team_label(cbool))
        surf.blit(head, (x, y))
        danger = prob > 0
        col = self._accent() if not danger else theme.EVENT_ABSENT_COLOR
        info = render.frac_str(prob) if danger else "SECURE"
        info_s = self.fonts["small"].render(info, True, col)
        surf.blit(info_s, (x + w - info_s.get_width(), y))
        segs, gap = 12, theme.px(3)
        seg_w = (w - gap * (segs - 1)) / segs
        filled = round(float(prob) * segs)
        top = y + theme.px(20)
        for i in range(segs):
            r = pygame.Rect(int(x + i * (seg_w + gap)), top, int(seg_w), theme.px(8))
            pygame.draw.rect(surf, col if i < filled else self._tint(theme.TEXT_DIM, 60), r)

    def draw_panel(self, surf, app, status, check_lines):
        p = theme.px
        self.panel_backdrop(surf, app)
        qb, config = app.qb, app.config
        rects = self.panel_rects()
        x = PANEL_X + p(16)
        right = PANEL_X + PANEL_W - p(16)
        w = right - x

        # --- ACTIVE UNIT header module ---------------------------------------
        hdr = pygame.Rect(x, p(12), w, p(56))
        self._module(surf, hdr, "ACTIVE UNIT")
        cur = "_" if int(self.now() * 2) % 2 == 0 else " "
        name_s = self.fonts["title"].render(config.team_name(qb.turn).upper() + cur, True,
                                            theme.team_label(qb.turn))
        surf.blit(name_s, (hdr.x + p(12), hdr.y + p(10)))
        mode_txt = "STANDBY" if not config.splitting_enabled else f"MODE: {app.mode.upper()}"
        surf.blit(self.fonts["tiny"].render("> " + mode_txt, True, self._accent()),
                  (hdr.x + p(12), hdr.y + p(38)))

        # --- control rows -----------------------------------------------------
        self._mode_row(surf, rects["mode"], "M", app.mode, enabled=config.splitting_enabled)
        self._toggle_row(surf, rects["captured"], "C", "LOST UNITS",
                         "ON" if app.show_captured else "OFF", app.show_captured)
        self._toggle_row(surf, rects["check"], "K", "THREAT VIS",
                         "ON" if app.show_check else "OFF", app.show_check)
        self.draw_button(surf, rects["save"], "[F5] SAVE", active=False)
        self.draw_button(surf, rects["load"], "[F9] LOAD", active=False)
        if not qb.game_over:
            if app._confirm_surrender:
                self.draw_button(surf, rects["surrender"], "!! CONFIRM ABORT !!",
                                 color=theme.EVENT_ABSENT_COLOR, text_color=(10, 10, 10))
            else:
                self.draw_button(surf, rects["surrender"], "[!] ABORT MATCH", active=False)
        self._view_row(surf, rects["view"], "TAB", ["CLARITY", "HUD"][app.skin_index])
        if app._confirm_quit:
            self.draw_button(surf, rects["quit"], "!! CONFIRM QUIT !!",
                             color=theme.EVENT_ABSENT_COLOR, text_color=(10, 10, 10))
        else:
            self.draw_button(surf, rects["quit"], "[!] QUIT", active=False)
        self.draw_button(surf, rects["settings"], "[O] SETTINGS", active=False)

        # --- THREAT ASSESSMENT module ----------------------------------------
        y = rects["settings"].bottom + p(12)
        if app.show_check:
            mod = pygame.Rect(x, y, w, p(84))
            inner = self._module(surf, mod, "THREAT ASSESSMENT")
            gy = inner + p(6)
            for name, prob, cbool in self._check_values(app):
                self._threat_gauge(surf, mod.x + p(12), gy, w - p(24), name, prob, cbool)
                gy += p(36)
            y = mod.bottom + p(12)
        else:
            y += p(8)

        if status:
            surf.blit(self.fonts["small"].render("> " + status, True, self._accent()), (x, y))
        y += p(26)

        # --- SYSTEM LOG module ------------------------------------------------
        self._caps_label(surf, "SYSTEM LOG", (x, y), color=self._accent(), rule_to=right)
        y += p(18)
        footer_y = WINDOW_H - p(40)
        self._draw_log_and_tray(surf, app, x, y,
                                bottom=(footer_y - p(8) if not qb.game_over else None))

        # --- footer telemetry -------------------------------------------------
        tele = f"SEED {config.seed} | COLLAPSE {config.collapse_mode.value.upper()}"
        surf.blit(self.fonts["tiny"].render(tele, True, theme.TEXT_DIM), (x, footer_y))
        surf.blit(self.fonts["tiny"].render("F11 FULLSCREEN | TAB SWITCH UI", True,
                                            theme.TEXT_DIM), (x, footer_y + p(16)))

        # --- game over --------------------------------------------------------
        if qb.game_over and qb.winner is not None:
            banner = f">> {config.team_name(qb.winner).upper()} WINS <<"
            bs = self.fonts["title"].render(banner, True, theme.team_label(qb.winner))
            surf.blit(bs, (x, rects["new_game"].y - p(42)))
            self.draw_button(surf, rects["new_game"], "[N] NEW MATCH")
