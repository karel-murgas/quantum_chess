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
from . import theme
from .animation import Beat, Token


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


def draw_board(surface):
    for square in chess.SQUARES:
        rect = square_rect(square)
        light = (chess.square_file(square) + chess.square_rank(square)) % 2 == 1
        color = theme.LIGHT_SQUARE if light else theme.DARK_SQUARE
        pygame.draw.rect(surface, color, rect)
    board_rect = pygame.Rect(theme.BOARD_MARGIN, theme.BOARD_MARGIN,
                             theme.BOARD_PIXELS, theme.BOARD_PIXELS)
    pygame.draw.rect(surface, theme.BOARD_BORDER, board_rect, width=3)


def _aura_color(piece_id: int):
    return theme.AURA_PALETTE[piece_id % len(theme.AURA_PALETTE)]


def draw_highlights(surface, qb: QuantumBoard, selected_square, legal_by_square,
                    split_pick_a, check_by_square=None, fonts=None):
    if selected_square is not None:
        ghost = qb.ghost_at(selected_square)
        if ghost is not None:
            for g in qb.ghosts_of(ghost.piece_id):
                pygame.draw.rect(surface, _aura_color(ghost.piece_id),
                                 square_rect(g.square), width=4)
        pygame.draw.rect(surface, theme.SELECTED_RING, square_rect(selected_square), width=5)

    dot_colors = {"merge": theme.LEGAL_MERGE_DOT, "contact": theme.LEGAL_CONTACT_DOT}
    for sq, kind in legal_by_square.items():
        rect = square_rect(sq)
        color = dot_colors.get(kind, theme.LEGAL_MOVE_DOT)
        pygame.draw.circle(surface, color, rect.center, theme.SQUARE // 8)

    # A move that would raise the mover's OWN king danger is flagged in danger
    # red -- a warning ring plus the resulting check fraction (feature 2).
    if check_by_square:
        for sq, prob in check_by_square.items():
            _draw_danger_marker(surface, sq, prob, fonts)

    if split_pick_a is not None:
        pygame.draw.rect(surface, theme.SPLIT_PICK_RING, square_rect(split_pick_a), width=5)


def _draw_danger_marker(surface, square: int, prob: Fraction, fonts=None):
    """Red warning ring on a self-exposing destination, with the resulting
    check fraction chipped into its top-left corner."""
    rect = square_rect(square)
    pygame.draw.rect(surface, theme.EVENT_ABSENT_COLOR, rect, width=4)
    if fonts is None:
        return
    label = fonts["label"].render(frac_str(prob), True, theme.EVENT_ABSENT_COLOR)
    pad = 3
    chip = pygame.Surface((label.get_width() + pad * 2, label.get_height() + pad * 2),
                          pygame.SRCALPHA)
    chip.fill((8, 8, 12, 190))
    chip.blit(label, (pad, pad))
    surface.blit(chip, (rect.x + 2, rect.y + 2))


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
    """Draw a single piece token (filled circle + border + glyph) centred at
    ``center`` with the given opacity. Shared by the live board, the
    collapse animation, and the side panel's removed-pieces tray (which
    passes a smaller ``radius`` and a smaller ``piece_font`` to match)."""
    alpha = max(0, min(255, alpha))
    if alpha == 0:
        return
    token_r = radius if radius is not None else int(theme.SQUARE * 0.40)
    token_surf = pygame.Surface((token_r * 2, token_r * 2), pygame.SRCALPHA)
    if color == chess.WHITE:
        fill, border, ink = theme.WHITE_TOKEN, theme.WHITE_TOKEN_BORDER, theme.WHITE_INK
    else:
        fill, border, ink = theme.BLACK_TOKEN, theme.BLACK_TOKEN_BORDER, theme.BLACK_INK

    pygame.draw.circle(token_surf, (*fill, alpha), (token_r, token_r), token_r)
    pygame.draw.circle(token_surf, (*border, alpha), (token_r, token_r), token_r, width=3)
    glyph = piece_font.render(theme.GLYPH[ptype], True, (*ink, alpha))
    token_surf.blit(glyph, glyph.get_rect(center=(token_r, token_r)))
    surface.blit(token_surf, token_surf.get_rect(center=center))


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


def draw_pieces(surface, qb: QuantumBoard, piece_font, label_font):
    for ghost in qb.ghosts:
        piece = qb.pieces[ghost.piece_id]
        center = square_rect(ghost.square).center
        solid = qb.is_solid(ghost.piece_id)
        draw_token(surface, piece_font, piece.color, piece.ptype, center,
                   alpha=_prob_alpha(ghost.prob, solid))
        if not solid:
            _draw_prob_label(surface, label_font, ghost.prob, center, color=piece.color)


# --------------------------------------------------------------- collapse anim
def _ease(t: float) -> float:
    """Smoothstep -- eases a linear 0..1 into an accelerate/decelerate curve."""
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _draw_anim_token(surface, piece_font, label_font, token: Token, center, alpha_mult=1.0):
    base = _prob_alpha(token.prob, token.solid)
    alpha = int(base * alpha_mult)
    draw_token(surface, piece_font, token.color, token.ptype, center, alpha=alpha)
    if not token.solid and alpha_mult > 0.15:
        _draw_prob_label(surface, label_font, token.prob, center, alpha=int(255 * alpha_mult), color=token.color)


def _draw_flash(surface, square: int, present: bool, t: float):
    """A green (really there) / red (not there) pulse on the measured square,
    brightest mid-beat so the eye catches the reveal."""
    color = theme.EVENT_PRESENT_COLOR if present else theme.EVENT_ABSENT_COLOR
    pulse = math.sin(math.pi * max(0.0, min(1.0, t)))
    rect = square_rect(square)
    overlay = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    overlay.fill((*color, int(150 * pulse)))
    surface.blit(overlay, rect.topleft)
    pygame.draw.rect(surface, color, rect, width=max(2, int(7 * pulse)))


def _draw_shatter(surface, piece_font, token: Token, t: float):
    """A captured piece bursting: the token fades as a ring expands outward."""
    center = square_rect(token.square).center
    draw_token(surface, piece_font, token.color, token.ptype, center, alpha=int(220 * (1 - t)))
    radius = int(theme.SQUARE * (0.18 + 0.4 * t))
    width = max(1, int(6 * (1 - t)))
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
    pad = 5
    chip = pygame.Surface((surf.get_width() + pad * 2, surf.get_height() + pad * 2),
                          pygame.SRCALPHA)
    chip.fill((8, 8, 12, int(160 * alpha / 255)))
    cx, top = rect.centerx, rect.top - 6 - int(18 * t)
    surface.blit(chip, chip.get_rect(center=(cx, top)))
    surface.blit(surf, surf.get_rect(center=(cx, top)))


def draw_beat(surface, beat: Beat, t: float, fonts):
    """Render one collapse-animation beat at local progress ``t`` in [0, 1]."""
    piece_font, label_font = fonts["piece"], fonts["label"]
    te = _ease(t)

    if beat.flash_square is not None:                       # behind the tokens
        _draw_flash(surface, beat.flash_square, bool(beat.flash_present), t)

    for tok in beat.rest:
        _draw_anim_token(surface, piece_font, label_font, tok, square_rect(tok.square).center)

    for tok, frm in beat.travel:
        center = _lerp(square_rect(frm).center, square_rect(tok.square).center, te)
        _draw_anim_token(surface, piece_font, label_font, tok, center)

    for tok in beat.fades:
        _draw_anim_token(surface, piece_font, label_font, tok,
                         square_rect(tok.square).center, alpha_mult=max(0.0, 1 - t))

    if beat.shatter is not None:
        _draw_shatter(surface, piece_font, beat.shatter, t)

    if beat.caption:
        _draw_caption(surface, fonts["label"], beat.caption, beat.caption_square, t)


# ------------------------------------------------------ mass-move planning
def mass_controls_rects():
    """The two floating Confirm / Cancel buttons shown over the board while a
    mass move is being planned. Overlaid on the board (like the promotion
    picker) so a mouse-only player never needs the keyboard; hit-tested before
    board squares in ``App.handle_mouse_down``."""
    bw, bh, gap = 156, 40, 16
    total = bw * 2 + gap
    cx = theme.BOARD_MARGIN + (theme.BOARD_PIXELS - total) // 2
    cy = theme.BOARD_MARGIN + theme.BOARD_PIXELS - bh - 12
    return {
        "confirm": pygame.Rect(cx, cy, bw, bh),
        "cancel": pygame.Rect(cx + bw + gap, cy, bw, bh),
    }


def _draw_arrow(surface, a, b, color, width=4):
    """A directed line a -> b with a little arrowhead at b."""
    pygame.draw.line(surface, color, a, b, width)
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    size = 14
    for da in (math.radians(150), math.radians(-150)):
        tip = (b[0] + size * math.cos(ang + da), b[1] + size * math.sin(ang + da))
        pygame.draw.line(surface, color, b, tip, width)


def draw_plan_rings(surface, plan, plan_active, plan_piece):
    """Aura ring around every ghost of the piece being planned, plus a bright
    'active' ring on the ghost currently being assigned. Drawn *under* the
    pieces (like the normal selection highlight)."""
    color = _aura_color(plan_piece)
    for frm in plan:
        pygame.draw.rect(surface, color, square_rect(frm), width=4)
    if plan_active is not None:
        pygame.draw.rect(surface, theme.SELECTED_RING, square_rect(plan_active), width=5)


def draw_plan_arrows(surface, plan, plan_piece):
    """One arrow per reassigned ghost (source -> chosen destination) with a ring
    on the destination; a small 'hold' dot marks a ghost left in place. Drawn
    *over* the pieces so the plan stays legible."""
    color = _aura_color(plan_piece)
    for frm, to in plan.items():
        if frm == to:
            pygame.draw.circle(surface, color, square_rect(frm).center,
                               theme.SQUARE // 10, width=3)
            continue
        a, b = square_rect(frm).center, square_rect(to).center
        _draw_arrow(surface, a, b, color)
        pygame.draw.circle(surface, color, b, theme.SQUARE // 6, width=3)


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
                             default_r=12, min_r=5):
    """Shrink the removed-pieces tray's icon size until both team columns
    (header + wrapped icon grid, stacked with a gap between them) fit inside
    `available_height` -- otherwise a long game with many captures grows the
    tray past whatever's laid out below it (win banner, New Game button,
    footer text)."""
    header_h, col_gap = 20, 10
    for r in range(default_r, min_r - 1, -1):
        step = r * 2 + 4
        per_row = max(1, tray_width // step)
        white_rows = -(-white_n // per_row) if white_n else 1
        black_rows = -(-black_n // per_row) if black_n else 1
        needed = 2 * header_h + white_rows * step + black_rows * step + col_gap
        if needed <= available_height:
            return r
    return min_r


def _draw_captured_column(surface, small_font, icon_font, label, pieces, color,
                          x, y, col_right, icon_r=12):
    """Draw one team's removed-pieces list as a narrow vertical block: a
    coloured name header, then small piece-glyph tokens wrapping to as many
    rows as the ``col_right`` width forces. Returns the y just below it,
    for the next group (or caller) to continue from."""
    label_surf = small_font.render(label, True, theme.team_label(color))
    surface.blit(label_surf, (x, y))
    y += label_surf.get_height() + 6

    if not pieces:
        none_surf = small_font.render("none", True, theme.TEXT_DIM)
        surface.blit(none_surf, (x, y))
        return y + none_surf.get_height() + 4

    step = icon_r * 2 + 4
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
    pygame.draw.rect(surface, color, rect, border_radius=6)
    pygame.draw.rect(surface, theme.TEXT_DIM, rect, width=2, border_radius=6)
    surf = font.render(label, True, text_color)
    surface.blit(surf, surf.get_rect(center=rect.center))


def draw_side_panel(surface, qb: QuantumBoard, config, mode, log_lines, status_text, fonts,
                     confirm_surrender=False, show_captured=True, show_check=True,
                     check_lines=None, confirm_quit=False):
    panel_rect = pygame.Rect(theme.BOARD_MARGIN * 2 + theme.BOARD_PIXELS, 0,
                             theme.PANEL_WIDTH, theme.WINDOW_H)
    pygame.draw.rect(surface, theme.PANEL_BG, panel_rect)
    rects = panel_rects()

    x = panel_rect.x + 20
    y = 20
    turn = config.team_name(qb.turn)
    name_surf = fonts["title"].render(turn, True, theme.team_label(qb.turn))
    surface.blit(name_surf, (x, y))
    rest_surf = fonts["title"].render(" to move", True, theme.TEXT)
    surface.blit(rest_surf, (x + name_surf.get_width(), y))

    if config.splitting_enabled:
        _draw_button(surface, rects["mode"], f"Mode: {mode.upper()}  (M)",
                    fonts["small"], active=(mode == "split"))
    else:
        _draw_button(surface, rects["mode"], "Splitting disabled", fonts["small"],
                    enabled=False)

    _draw_button(surface, rects["save"], "Save (F5)", fonts["small"], active=False)
    _draw_button(surface, rects["load"], "Load (F9)", fonts["small"], active=False)

    if not qb.game_over:
        if confirm_surrender:
            _draw_button(surface, rects["surrender"], "Confirm surrender? (click again)",
                        fonts["small"], color=theme.EVENT_ABSENT_COLOR, text_color=(20, 20, 20))
        else:
            _draw_button(surface, rects["surrender"], "Surrender", fonts["small"], active=False)

    _draw_button(surface, rects["captured"],
                f"Removed pieces: {'ON' if show_captured else 'OFF'} (C)",
                fonts["small"], active=show_captured)
    _draw_button(surface, rects["check"],
                f"Check warnings: {'ON' if show_check else 'OFF'} (K)",
                fonts["small"], active=show_check)

    if confirm_quit:
        _draw_button(surface, rects["quit"], "Confirm quit? (click again)",
                    fonts["small"], color=theme.EVENT_ABSENT_COLOR, text_color=(20, 20, 20))
    else:
        _draw_button(surface, rects["quit"], "Quit", fonts["small"], active=False)
    y = rects["quit"].bottom + 10

    if show_check and check_lines:
        for text, color in check_lines:
            surface.blit(fonts["body"].render(text, True, color), (x, y))
            y += 26
        y += 4

    cfg_surf = fonts["small"].render(
        f"Collapse: {config.collapse_mode.value}   Splitting: "
        f"{'on' if config.splitting_enabled else 'off'}",
        True, theme.TEXT_DIM)
    surface.blit(cfg_surf, (x, y))
    y += 22
    hint_surf = fonts["small"].render("F11: Fullscreen", True, theme.TEXT_DIM)
    surface.blit(hint_surf, (x, y))
    y += 24

    if status_text:
        status_surf = fonts["body"].render(status_text, True, theme.ACCENT)
        surface.blit(status_surf, (x, y))
        y += 30

    y += 8
    pygame.draw.line(surface, theme.TEXT_DIM, (x, y), (panel_rect.right - 20, y), 1)
    y += 14

    # Below the divider the panel splits into two columns: the log on the
    # left, and -- when toggled on -- a narrower removed-pieces column on the
    # right where each side's lost pieces wrap into their own little grid.
    log_top = y
    bottom_limit = (rects["new_game"].y - 60) if qb.game_over else (theme.WINDOW_H - 16)
    panel_right = panel_rect.right - 20

    if show_captured:
        tray_width = 130
        col_gap = 18
        tray_x = panel_right - tray_width
        log_right = tray_x - col_gap
        pygame.draw.line(surface, theme.TEXT_DIM,
                         (tray_x - col_gap // 2, log_top), (tray_x - col_gap // 2, bottom_limit), 1)
    else:
        log_right = panel_right

    # Word-wrap each log line to the log column's width, then show only as
    # many visual lines as fit above the New Game area / window bottom.
    line_h = 20
    max_width = log_right - x
    max_lines = max(0, (bottom_limit - log_top) // line_h)

    name_colors = {
        config.team_name(chess.WHITE): theme.team_label(chess.WHITE),
        config.team_name(chess.BLACK): theme.team_label(chess.BLACK),
    }
    wrapped = []
    for line in log_lines:
        wrapped.extend(wrap_line(line, fonts["small"], max_width))
    y = log_top
    for line in wrapped[-max_lines:] if max_lines else []:
        draw_log_line(surface, line, (x, y), fonts["small"], theme.TEXT, name_colors)
        y += line_h

    if show_captured:
        removed = [p for p in qb.pieces.values() if not p.alive]
        removed.sort(key=lambda p: _CAPTURED_ORDER.index(p.ptype)
                     if p.ptype in _CAPTURED_ORDER else len(_CAPTURED_ORDER))
        white_removed = [p for p in removed if p.color == chess.WHITE]
        black_removed = [p for p in removed if p.color == chess.BLACK]
        icon_r = fit_captured_icon_radius(tray_width, bottom_limit - log_top,
                                          len(white_removed), len(black_removed))
        ty = _draw_captured_column(surface, fonts["small"], fonts["icon"],
                                   config.team_name(chess.WHITE), white_removed,
                                   chess.WHITE, tray_x, log_top, panel_right, icon_r=icon_r)
        ty += 10
        _draw_captured_column(surface, fonts["small"], fonts["icon"],
                              config.team_name(chess.BLACK), black_removed,
                              chess.BLACK, tray_x, ty, panel_right, icon_r=icon_r)

    if qb.game_over and qb.winner is not None:
        banner = f"{config.team_name(qb.winner).upper()} WINS"
        banner_surf = fonts["title"].render(banner, True, theme.team_label(qb.winner))
        surface.blit(banner_surf, (x, rects["new_game"].y - 50))
        _draw_button(surface, rects["new_game"], "New Game (N)", fonts["body"])


def promotion_rects():
    order = (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT)
    box, gap = 70, 14
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
        pygame.draw.rect(surface, fill, rect, border_radius=8)
        pygame.draw.rect(surface, theme.ACCENT, rect, width=2, border_radius=8)
        glyph = fonts["piece"].render(theme.GLYPH[ptype], True, ink)
        surface.blit(glyph, glyph.get_rect(center=rect.center))


def promotion_choice_at(pos):
    for ptype, rect in promotion_rects().items():
        if rect.collidepoint(pos):
            return ptype
    return None
