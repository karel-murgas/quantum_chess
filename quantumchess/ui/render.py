"""Pure drawing functions for the Quantum Chess board (Milestone 4).

Nothing here mutates game state; functions take a Surface plus read-only state
and draw onto it. Kept separate from app.py (event handling / game loop).
"""

from __future__ import annotations

import math
from fractions import Fraction
from typing import Optional

import chess
import pygame

from ..model import QuantumBoard
from . import theme, pieces
from .animation import Token


def square_rect(square: int) -> pygame.Rect:
    file = chess.square_file(square)
    rank = chess.square_rank(square)
    x = theme.BOARD_MARGIN + file * theme.SQUARE
    y = theme.BOARD_MARGIN + (7 - rank) * theme.SQUARE
    return pygame.Rect(x, y, theme.SQUARE, theme.SQUARE)


def square_at_pixel(pos) -> Optional[int]:
    x, y = pos
    bx, by = x - theme.BOARD_MARGIN, y - theme.BOARD_MARGIN
    if not (0 <= bx < theme.BOARD_PIXELS and 0 <= by < theme.BOARD_PIXELS):
        return None
    file = bx // theme.SQUARE
    rank = 7 - (by // theme.SQUARE)
    return chess.square(file, rank)


def _aura_color(piece_id: int):
    return theme.AURA_PALETTE[piece_id % len(theme.AURA_PALETTE)]


def _draw_danger_marker(surface, square: int, prob: Fraction, fonts=None):
    """Red warning ring on a self-exposing destination, with the resulting
    check fraction chipped into its top-left corner."""
    rect = square_rect(square)
    pygame.draw.rect(surface, theme.EVENT_ABSENT_COLOR, rect, width=theme.px(4))
    if fonts is None:
        return
    label = fonts["label"].render(frac_str(prob), True, theme.EVENT_ABSENT_COLOR)
    pad = theme.px(3)
    chip = pygame.Surface((label.get_width() + pad * 2, label.get_height() + pad * 2),
                          pygame.SRCALPHA)
    chip.fill((8, 8, 12, 190))
    chip.blit(label, (pad, pad))
    surface.blit(chip, (rect.x + theme.px(2), rect.y + theme.px(2)))


def frac_str(f: Fraction) -> str:
    return str(f.numerator) if f.denominator == 1 else f"{f.numerator}/{f.denominator}"


def wrap_line(text, font, max_width):
    """Greedily wrap `text` to fit `max_width` px, returning a list of lines.

    Splits on spaces; a single word wider than `max_width` is left on its own
    line (it will still overflow, but that's rare -- log lines are prose)."""
    words = text.split(" ")
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}" if current else word
        if font.size(candidate)[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def _log_keyword_spans(text, extra_specs=()):
    """Find non-overlapping occurrences of the theme's narration keywords
    (`theme.TERMS` values, coloured via `theme.LOG_KEYWORD_COLORS`) plus any
    `extra_specs` (`(text, color)` pairs, e.g. team names) in `text`, longest
    first so e.g. a whole win_suffix phrase isn't shadowed by a shorter one, or
    a team name by a keyword sitting inside it. Returns (start, end, color)
    tuples sorted by position."""
    specs = [(theme.TERMS[key], color) for key, color in theme.LOG_KEYWORD_COLORS.items()
             if key in theme.TERMS]
    specs.extend((kw, color) for kw, color in extra_specs if kw)
    specs.sort(key=lambda kv: -len(kv[0]))
    claimed = []
    for keyword, color in specs:
        start = 0
        while True:
            idx = text.find(keyword, start)
            if idx == -1:
                break
            end = idx + len(keyword)
            if not any(idx < c_end and end > c_start for c_start, c_end, _ in claimed):
                claimed.append((idx, end, color))
            start = idx + 1
    claimed.sort(key=lambda span: span[0])
    return claimed


def draw_log_line(surface, text, pos, font, default_color, name_colors=None):
    """Render one log line, colouring theme keywords (captures/splits/
    castles/fizzles/wins/vanished) and team names (`name_colors`, a
    ``{name: color}`` dict) inline while leaving the rest in `default_color`."""
    x, y = pos
    cursor = 0
    for start, end, color in _log_keyword_spans(text, tuple((name_colors or {}).items())):
        if start > cursor:
            seg_surf = font.render(text[cursor:start], True, default_color)
            surface.blit(seg_surf, (x, y))
            x += seg_surf.get_width()
        seg_surf = font.render(text[start:end], True, color)
        surface.blit(seg_surf, (x, y))
        x += seg_surf.get_width()
        cursor = end
    if cursor < len(text):
        surface.blit(font.render(text[cursor:], True, default_color), (x, y))


def _prob_alpha(prob: Fraction, solid: bool) -> int:
    """A ghost's opacity tracks its probability (solids are fully opaque);
    a floor keeps a faint 1/2^n ghost from disappearing entirely."""
    return 255 if solid else max(70, int(255 * float(prob)))


def draw_token(surface, piece_font, color: bool, ptype: int, center, *, alpha: int = 255,
               radius: Optional[int] = None):
    """Draw a single piece token centred at ``center`` with the given opacity.
    Shared by the live board, the collapse animation, and the side panel's
    removed-pieces tray (which passes a smaller ``radius``/``piece_font``).

    The look depends on the active piece set (see ``ui/pieces.py``): the
    ``"unicode"`` set keeps the original filled-circle-plus-glyph token (and
    uses ``piece_font``); every other set blits real piece art (SVG-rasterized
    or the recoloured neon silhouette) with a soft shadow or neon glow, so no
    circle -- the art itself carries the side's colour and shape."""
    alpha = max(0, min(255, alpha))
    if alpha == 0:
        return
    token_r = radius if radius is not None else int(theme.SQUARE * 0.40)

    if pieces.active(color) == "unicode":
        token_surf = pygame.Surface((token_r * 2, token_r * 2), pygame.SRCALPHA)
        if color == chess.WHITE:
            fill, border, ink = theme.WHITE_TOKEN, theme.WHITE_TOKEN_BORDER, theme.WHITE_INK
        else:
            fill, border, ink = theme.BLACK_TOKEN, theme.BLACK_TOKEN_BORDER, theme.BLACK_INK
        pygame.draw.circle(token_surf, (*fill, alpha), (token_r, token_r), token_r)
        pygame.draw.circle(token_surf, (*border, alpha), (token_r, token_r), token_r,
                           width=theme.px(3))
        glyph = piece_font.render(theme.GLYPH[ptype], True, (*ink, alpha))
        token_surf.blit(glyph, glyph.get_rect(center=(token_r, token_r)))
        surface.blit(token_surf, token_surf.get_rect(center=center))
        return

    blit_piece_art(surface, color, ptype, center, token_r, alpha)


def blit_piece_art(surface, color: bool, ptype: int, center, token_r: int, alpha: int = 255):
    """Blit real piece art (an SVG-rasterized or neon-silhouette token) centred
    at ``center``. Shared by ``draw_token`` and the HUD/Clarity skins, which use
    it for every set except ``"unicode"`` -- so all three views render the same
    art, on top of whatever board/backdrop the skin drew. The piece fills ~the
    whole square (``token_r*2`` is 0.8*SQUARE, so 2.4x gives a natural piece
    height with a small margin); the neon set gets a side-keyed glow."""
    set_name = pieces.active(color)
    glow = None
    if set_name == "neon":
        glow = theme.WHITE_NEON if color == chess.WHITE else theme.BLACK_NEON
    art_size = max(1, round(token_r * 2.4))
    tok = pieces.render_token(set_name, ptype, color, art_size, glow=glow)
    if alpha < 255:
        tok = tok.copy()
        tok.set_alpha(alpha)
    surface.blit(tok, tok.get_rect(center=center))


def _draw_prob_label(surface, label_font, prob: Fraction, center, alpha: int = 255, color: bool = chess.WHITE):
    # Use the piece's ink color (white for black pieces, black for white pieces)
    # so fractions contrast well against the token circle
    ink = theme.WHITE_INK if color == chess.BLACK else theme.BLACK_INK
    label = label_font.render(frac_str(prob), True, ink)
    if alpha < 255:
        label.set_alpha(alpha)
    x = center[0] + theme.SQUARE // 2 - label.get_width() - 4
    y = center[1] + theme.SQUARE // 2 - label.get_height() - 2
    surface.blit(label, (x, y))


# --------------------------------------------------------------- collapse anim
def _ease(t: float) -> float:
    """Smoothstep -- eases a linear 0..1 into an accelerate/decelerate curve."""
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _draw_flash(surface, square: int, present: bool, t: float):
    """A green (really there) / red (not there) pulse on the measured square,
    brightest mid-beat so the eye catches the reveal."""
    color = theme.EVENT_PRESENT_COLOR if present else theme.EVENT_ABSENT_COLOR
    pulse = math.sin(math.pi * max(0.0, min(1.0, t)))
    rect = square_rect(square)
    overlay = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    overlay.fill((*color, int(150 * pulse)))
    surface.blit(overlay, rect.topleft)
    pygame.draw.rect(surface, color, rect, width=max(theme.px(2), int(theme.px(7) * pulse)))


def _draw_shatter(surface, piece_font, token: Token, t: float):
    """A captured piece bursting: the token fades as a ring expands outward."""
    center = square_rect(token.square).center
    draw_token(surface, piece_font, token.color, token.ptype, center, alpha=int(220 * (1 - t)))
    radius = int(theme.SQUARE * (0.18 + 0.4 * t))
    width = max(theme.px(1), int(theme.px(6) * (1 - t)))
    if 1 - t > 0.03:
        pygame.draw.circle(surface, theme.EVENT_ABSENT_COLOR, center, radius, width=width)


def _draw_caption(surface, font, text: str, square: int, t: float):
    """A short floating caption above the action -- fades in/out, drifts up."""
    alpha = int(255 * math.sin(math.pi * max(0.0, min(1.0, t))))
    if alpha <= 0:
        return
    rect = square_rect(square)
    surf = font.render(text, True, theme.ACCENT)
    surf.set_alpha(alpha)
    pad = theme.px(5)
    chip = pygame.Surface((surf.get_width() + pad * 2, surf.get_height() + pad * 2),
                          pygame.SRCALPHA)
    chip.fill((8, 8, 12, int(160 * alpha / 255)))
    cx, top = rect.centerx, rect.top - theme.px(6) - int(theme.px(18) * t)
    surface.blit(chip, chip.get_rect(center=(cx, top)))
    surface.blit(surf, surf.get_rect(center=(cx, top)))


# ------------------------------------------------------------------- vignette
_vignette_src = None      # small radial mask, built once
_vignette_scaled = {}     # size -> mask scaled to that surface


def _vignette_source():
    """A small radial darkening mask (transparent centre, dark corners), built
    once at low resolution and smooth-scaled up per surface size -- an
    inexpensive way to get a soft elliptical vignette with no per-pixel work
    at draw time."""
    global _vignette_src
    if _vignette_src is None:
        n = 96
        s = pygame.Surface((n, n), pygame.SRCALPHA)
        c = (n - 1) / 2
        maxd = (c * c + c * c) ** 0.5
        for y in range(n):
            for x in range(n):
                d = ((x - c) ** 2 + (y - c) ** 2) ** 0.5 / maxd
                a = 0 if d < 0.5 else min(160, int(160 * ((d - 0.5) / 0.5) ** 1.8))
                s.set_at((x, y), (0, 0, 0, a))
        _vignette_src = s
    return _vignette_src


def draw_vignette(surface):
    """Blit a soft dark vignette over the whole frame (used on the cyberpunk
    theme for a moodier, more 'screen-lit' look)."""
    size = surface.get_size()
    mask = _vignette_scaled.get(size)
    if mask is None:
        mask = pygame.transform.smoothscale(_vignette_source(), size)
        _vignette_scaled[size] = mask
    surface.blit(mask, (0, 0))


# ------------------------------------------------------ mass-move planning
def mass_controls_rects():
    """The two floating Confirm / Cancel buttons shown over the board while a
    mass move is being planned. Overlaid on the board (like the promotion
    picker) so a mouse-only player never needs the keyboard; hit-tested before
    board squares in ``App.handle_mouse_down``."""
    bw, bh, gap = theme.px(156), theme.px(40), theme.px(16)
    total = bw * 2 + gap
    cx = theme.BOARD_MARGIN + (theme.BOARD_PIXELS - total) // 2
    cy = theme.BOARD_MARGIN + theme.BOARD_PIXELS - bh - theme.px(12)
    return {
        "confirm": pygame.Rect(cx, cy, bw, bh),
        "cancel": pygame.Rect(cx + bw + gap, cy, bw, bh),
    }


def _draw_arrow(surface, a, b, color, width=None):
    """A directed line a -> b with a little arrowhead at b."""
    width = width if width is not None else theme.px(4)
    pygame.draw.line(surface, color, a, b, width)
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    size = theme.px(14)
    for da in (math.radians(150), math.radians(-150)):
        tip = (b[0] + size * math.cos(ang + da), b[1] + size * math.sin(ang + da))
        pygame.draw.line(surface, color, b, tip, width)


def draw_plan_rings(surface, plan, plan_active, plan_piece):
    """Aura ring around every ghost of the piece being planned, plus a bright
    'active' ring on the ghost currently being assigned. Drawn *under* the
    pieces (like the normal selection highlight)."""
    color = _aura_color(plan_piece)
    for frm in plan:
        pygame.draw.rect(surface, color, square_rect(frm), width=theme.px(4))
    if plan_active is not None:
        pygame.draw.rect(surface, theme.SELECTED_RING, square_rect(plan_active), width=theme.px(5))


def draw_plan_arrows(surface, plan, plan_piece):
    """One arrow per reassigned ghost (source -> chosen destination) with a ring
    on the destination; a small 'hold' dot marks a ghost left in place. Drawn
    *over* the pieces so the plan stays legible."""
    color = _aura_color(plan_piece)
    for frm, to in plan.items():
        if frm == to:
            pygame.draw.circle(surface, color, square_rect(frm).center,
                               theme.SQUARE // 10, width=theme.px(3))
            continue
        a, b = square_rect(frm).center, square_rect(to).center
        _draw_arrow(surface, a, b, color)
        pygame.draw.circle(surface, color, b, theme.SQUARE // 6, width=theme.px(3))


def draw_mass_controls(surface, fonts):
    rects = mass_controls_rects()
    _draw_button(surface, rects["confirm"], "Confirm (Enter)", fonts["small"], active=True)
    _draw_button(surface, rects["cancel"], "Cancel (Esc)", fonts["small"], active=False)


def panel_rects():
    """Clickable button rects in the side panel, shared by draw and hit-testing."""
    panel_x = theme.BOARD_MARGIN * 2 + theme.BOARD_PIXELS
    return {
        "mode": pygame.Rect(panel_x + 20, 64, 240, 36),
        "save": pygame.Rect(panel_x + 20, 112, 110, 32),
        "load": pygame.Rect(panel_x + 150, 112, 110, 32),
        "surrender": pygame.Rect(panel_x + 20, 152, 240, 36),
        "captured": pygame.Rect(panel_x + 20, 200, 240, 32),
        "check": pygame.Rect(panel_x + 20, 236, 240, 32),
        "quit": pygame.Rect(panel_x + 20, 272, 240, 32),
        "settings": pygame.Rect(panel_x + 20, 308, 240, 32),
        "new_game": pygame.Rect(panel_x + 20, theme.WINDOW_H - 100, 220, 48),
    }


# Rough material order (highest first) so the removed-pieces tray reads like
# a captured-material strip rather than capture order.
_CAPTURED_ORDER = (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN, chess.KING)


def fit_captured_icon_radius(tray_width, available_height, white_n, black_n,
                             default_r=None, min_r=None):
    """Shrink the removed-pieces tray's icon size until both team columns
    (header + wrapped icon grid, stacked with a gap between them) fit inside
    `available_height` -- otherwise a long game with many captures grows the
    tray past whatever's laid out below it (win banner, New Game button,
    footer text)."""
    default_r = default_r if default_r is not None else theme.px(12)
    min_r = min_r if min_r is not None else theme.px(5)
    header_h, col_gap = theme.px(20), theme.px(10)
    for r in range(default_r, min_r - 1, -1):
        step = r * 2 + theme.px(4)
        per_row = max(1, tray_width // step)
        white_rows = -(-white_n // per_row) if white_n else 1
        black_rows = -(-black_n // per_row) if black_n else 1
        needed = 2 * header_h + white_rows * step + black_rows * step + col_gap
        if needed <= available_height:
            return r
    return min_r


def _draw_captured_column(surface, small_font, icon_font, label, pieces, color,
                          x, y, col_right, icon_r=None):
    """Draw one team's removed-pieces list as a narrow vertical block: a
    coloured name header, then small piece-glyph tokens wrapping to as many
    rows as the ``col_right`` width forces. Returns the y just below it,
    for the next group (or caller) to continue from."""
    icon_r = icon_r if icon_r is not None else theme.px(12)
    label_surf = small_font.render(label, True, theme.team_label(color))
    surface.blit(label_surf, (x, y))
    y += label_surf.get_height() + theme.px(6)

    if not pieces:
        none_surf = small_font.render("none", True, theme.TEXT_DIM)
        surface.blit(none_surf, (x, y))
        return y + none_surf.get_height() + theme.px(4)

    step = icon_r * 2 + theme.px(4)
    icon_x, icon_y = x + icon_r, y + icon_r
    for piece in pieces:
        if icon_x + icon_r > col_right:
            icon_x = x + icon_r
            icon_y += step
        draw_token(surface, icon_font, color, piece.ptype, (icon_x, icon_y), radius=icon_r)
        icon_x += step
    return icon_y + icon_r + 4


def _draw_button(surface, rect, label, font, *, active=True, enabled=True,
                  color=None, text_color=None):
    if color is not None:
        pass
    elif not enabled:
        color, text_color = theme.PANEL_BG, theme.TEXT_DIM
    elif active:
        color, text_color = theme.ACCENT, (20, 20, 20)
    else:
        color, text_color = theme.PANEL_BG, theme.TEXT
    pygame.draw.rect(surface, color, rect, border_radius=theme.px(6))
    pygame.draw.rect(surface, theme.TEXT_DIM, rect, width=theme.px(2), border_radius=theme.px(6))
    surf = font.render(label, True, text_color)
    surface.blit(surf, surf.get_rect(center=rect.center))


def promotion_rects():
    order = (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT)
    box, gap = theme.px(70), theme.px(14)
    total_w = box * 4 + gap * 3
    start_x = theme.BOARD_MARGIN + (theme.BOARD_PIXELS - total_w) // 2
    y = theme.BOARD_MARGIN + (theme.BOARD_PIXELS - box) // 2
    rects = {}
    x = start_x
    for ptype in order:
        rects[ptype] = pygame.Rect(x, y, box, box)
        x += box + gap
    return rects


def draw_promotion_picker(surface, color, fonts):
    overlay = pygame.Surface((theme.BOARD_PIXELS, theme.BOARD_PIXELS), pygame.SRCALPHA)
    overlay.fill((10, 10, 10, 190))
    surface.blit(overlay, (theme.BOARD_MARGIN, theme.BOARD_MARGIN))

    fill = theme.WHITE_TOKEN if color == chess.WHITE else theme.BLACK_TOKEN
    ink = theme.WHITE_INK if color == chess.WHITE else theme.BLACK_INK
    for ptype, rect in promotion_rects().items():
        pygame.draw.rect(surface, fill, rect, border_radius=theme.px(8))
        pygame.draw.rect(surface, theme.ACCENT, rect, width=theme.px(2), border_radius=theme.px(8))
        if pieces.active(color) == "unicode":
            glyph = fonts["piece"].render(theme.GLYPH[ptype], True, ink)
            surface.blit(glyph, glyph.get_rect(center=rect.center))
        else:
            # Show the active piece set's own art so the picker matches the board.
            blit_piece_art(surface, color, ptype, rect.center, int(rect.w * 0.42))


def promotion_choice_at(pos):
    for ptype, rect in promotion_rects().items():
        if rect.collidepoint(pos):
            return ptype
    return None
