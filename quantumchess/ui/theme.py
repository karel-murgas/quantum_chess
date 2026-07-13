"""Visual constants for the Quantum Chess UI (Milestone 4+).

Two selectable presets -- "origin" (the original wood-board look) and
"cyberpunk" (neon-on-dark, tinted by each player's chosen team colour).
`apply_theme()` is called once after the menu closes and mutates this
module's globals in place; every other UI module reads palette values as
``theme.X`` (an attribute lookup, never ``from theme import X``), so the
swap is picked up everywhere without touching render.py/app.py/menu.py.
"""

import chess

# --- supersampling -----------------------------------------------------------
# The whole game frame is drawn at SCALE x the base layout resolution onto an
# offscreen surface, then smooth-scaled to fit the window (see ui/present.py).
# Downscaling a 2x render = free anti-aliasing (SSAA); upscaling for a big
# monitor stays smooth instead of the old nearest-neighbour blockiness. Because
# SCALE is a *static* constant (fixed at import, never changed at runtime), the
# module-level copies skins capture at import time already see the scaled
# values -- no runtime plumbing needed. All game geometry below is in scaled
# pixels; the menu is authored at the base resolution (MENU_W/H) instead and
# smooth-scaled the same way.
SCALE = 2

SQUARE = 84 * SCALE
BOARD_MARGIN = 24 * SCALE
BOARD_PIXELS = SQUARE * 8
PANEL_WIDTH = 400 * SCALE
WINDOW_W = BOARD_MARGIN * 2 + BOARD_PIXELS + PANEL_WIDTH
WINDOW_H = BOARD_MARGIN * 2 + BOARD_PIXELS

# Base (unscaled) window size -- the pre-game / settings menu draws at this
# resolution onto its own surface, presented the same way as the game frame.
MENU_W = WINDOW_W // SCALE
MENU_H = WINDOW_H // SCALE


def px(n) -> int:
    """Scale a base-resolution pixel literal (border widths, small offsets,
    chip padding) into the supersampled render space. Geometry derived from
    SQUARE already scales automatically; use this for the stray literals."""
    return round(n * SCALE)

GLYPH = {
    chess.PAWN: "♙",
    chess.KNIGHT: "♘",
    chess.BISHOP: "♗",
    chess.ROOK: "♖",
    chess.QUEEN: "♕",
    chess.KING: "♔",
}

DEFAULT_WHITE_COLOR = (240, 200, 90)
DEFAULT_BLACK_COLOR = (90, 150, 230)

# Curated neon swatches offered in the menu's team-colour picker.
SWATCHES = [
    (255, 46, 199),   # magenta
    (0, 224, 255),    # cyan
    (57, 255, 168),   # neon green
    (255, 209, 0),    # neon yellow
    (189, 0, 255),    # violet
    (255, 111, 0),    # neon orange
    (255, 64, 90),    # hot red
    (110, 255, 255),  # ice blue
]


def _mix(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _clamp(c):
    return tuple(max(0, min(255, int(v))) for v in c)


def _ink_for(color):
    """Near-black or near-white text, whichever contrasts against `color`."""
    r, g, b = color
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return (25, 22, 18) if luminance > 140 else (235, 232, 225)


_ORIGIN_TERMS = dict(
    capture_verb="captures",
    vanished_word="vanished",
    fizzle_clause="wasn't really there -- move fizzles",
    win_suffix="wins by capturing the king!",
    split_verb="splits",
    measuring_verb="measuring",
    present_word="IS",
    absent_word="is NOT",
    reveal_present="REAL!",
    reveal_absent="EMPTY",
    reveal_capture="CAPTURED!",
    castle_verb="castles",
    mass_verb="mass move",
    mass_split_verb="mass split",
    mass_collapse_clause="collapses onto",
    surrender_verb="resigns",
    surrender_suffix="wins by resignation!",
    check_word="CHECK",
    safe_word="safe",
)

_CYBERPUNK_TERMS = dict(
    capture_verb="deletes",
    vanished_word="glitched out",
    fizzle_clause="ghost signal -- no lock, move glitches out",
    win_suffix="wins by deleting the king's process!",
    split_verb="forks",
    measuring_verb="pinging",
    present_word="ONLINE",
    absent_word="OFFLINE",
    reveal_present="ONLINE",
    reveal_absent="OFFLINE",
    reveal_capture="DELETED!",
    castle_verb="reroutes",
    mass_verb="swarm",
    mass_split_verb="fork swarm",
    mass_collapse_clause="resolves onto",
    surrender_verb="disconnects",
    surrender_suffix="wins -- the opponent disconnected!",
    check_word="LOCKED ON",
    safe_word="clear",
)


def _keyword_colors(palette):
    """Map each narration keyword (see TERMS) to a colour already in the
    palette, so the side-log highlight reuses the same visual language as
    the rest of the board (captures/deletes read in the "danger" red used
    for a negative collapse flash, a split/fork in the split-picker blue,
    a win in the same gold used for the win banner, etc.). `vanished_word`
    ("vanished"/"glitched out") uses the risky-contact orange rather than a
    dim tone -- a branch that didn't survive its split is worth noticing,
    not fading into the log."""
    return dict(
        capture_verb=palette["EVENT_ABSENT_COLOR"],
        split_verb=palette["SPLIT_PICK_RING"],
        mass_verb=palette["SPLIT_PICK_RING"],
        mass_split_verb=palette["SPLIT_PICK_RING"],
        castle_verb=palette["ACCENT"],
        win_suffix=palette["SELECTED_RING"],
        surrender_suffix=palette["SELECTED_RING"],
        surrender_verb=palette["EVENT_ABSENT_COLOR"],
        fizzle_clause=palette["TEXT_DIM"],
        vanished_word=palette["LEGAL_CONTACT_DOT"],
    )


def _origin_palette(white_color, black_color):
    palette = dict(
        TERMS=_ORIGIN_TERMS,
        LIGHT_SQUARE=(240, 217, 181),
        DARK_SQUARE=(181, 136, 99),
        BOARD_BORDER=(60, 45, 35),
        BG=(18, 18, 20),
        PANEL_BG=(30, 30, 34),
        TEXT=(230, 230, 230),
        TEXT_DIM=(160, 160, 165),
        ACCENT=(240, 200, 90),
        SELECTED_RING=(255, 215, 0),
        LEGAL_MOVE_DOT=(70, 190, 110),
        LEGAL_MERGE_DOT=(90, 150, 230),
        LEGAL_CONTACT_DOT=(235, 150, 40),
        SPLIT_PICK_RING=(80, 160, 235),
        WHITE_TOKEN=(248, 246, 238),
        WHITE_TOKEN_BORDER=(70, 60, 40),
        WHITE_INK=(35, 30, 20),
        BLACK_TOKEN=(40, 37, 34),
        BLACK_TOKEN_BORDER=(200, 195, 180),
        BLACK_INK=(235, 230, 215),
        # Team-name text colours (legible on the dark panel): a warm cream for
        # the light side, a lightened wood-brown for the dark side.
        WHITE_LABEL=(245, 238, 220),
        BLACK_LABEL=(198, 150, 105),
        # Vivid per-side colours the "neon" piece set tints its silhouettes
        # with. On origin these are the (default gold / blue) team colours; on
        # cyberpunk they're each player's chosen neon.
        WHITE_NEON=_clamp(white_color),
        BLACK_NEON=_clamp(black_color),
        AURA_PALETTE=[
            (231, 76, 60), (52, 152, 219), (46, 204, 113), (241, 196, 15),
            (155, 89, 182), (26, 188, 156), (230, 126, 34), (149, 165, 166),
        ],
        EVENT_PRESENT_COLOR=(70, 200, 110),
        EVENT_ABSENT_COLOR=(220, 90, 90),
    )
    palette["LOG_KEYWORD_COLORS"] = _keyword_colors(palette)
    return palette


def _cyberpunk_palette(white_color, black_color):
    """Neon-on-dark grid, tinted by each side's chosen team colour blended
    with its own grayscale ramp -- the board grays lean toward a blend of
    both teams' hues, and each side's token/border/aura draw straight from
    its own colour against a matching gray."""
    gray_dark = (16, 16, 22)
    gray_mid = (46, 46, 58)
    gray_light = (205, 205, 215)
    blend = _mix(white_color, black_color, 0.5)

    light_square = _clamp(_mix(gray_mid, blend, 0.22))
    dark_square = _clamp(_mix(gray_dark, blend, 0.18))
    board_border = _clamp(blend)

    white_token = _clamp(_mix(gray_light, white_color, 0.55))
    black_token = _clamp(_mix(gray_dark, black_color, 0.6))

    accent = _clamp(_mix(white_color, black_color, 0.35))

    palette = dict(
        TERMS=_CYBERPUNK_TERMS,
        LIGHT_SQUARE=light_square,
        DARK_SQUARE=dark_square,
        BOARD_BORDER=board_border,
        BG=(8, 8, 14),
        PANEL_BG=(14, 14, 22),
        TEXT=(225, 240, 245),
        TEXT_DIM=(110, 120, 140),
        ACCENT=accent,
        SELECTED_RING=(255, 46, 199),
        LEGAL_MOVE_DOT=(57, 255, 168),
        LEGAL_MERGE_DOT=(60, 190, 255),
        LEGAL_CONTACT_DOT=(255, 140, 30),
        SPLIT_PICK_RING=(0, 224, 255),
        WHITE_TOKEN=white_token,
        WHITE_TOKEN_BORDER=_clamp(white_color),
        WHITE_INK=_ink_for(white_token),
        BLACK_TOKEN=black_token,
        BLACK_TOKEN_BORDER=_clamp(black_color),
        BLACK_INK=_ink_for(black_token),
        # Team-name text colours = each side's own vivid neon accent.
        WHITE_LABEL=_clamp(white_color),
        BLACK_LABEL=_clamp(black_color),
        WHITE_NEON=_clamp(white_color),
        BLACK_NEON=_clamp(black_color),
        AURA_PALETTE=[
            (255, 46, 199), (0, 224, 255), (57, 255, 168), (255, 209, 0),
            (189, 0, 255), (0, 255, 209), (255, 111, 0), (150, 160, 190),
        ],
        EVENT_PRESENT_COLOR=(57, 255, 168),
        EVENT_ABSENT_COLOR=(255, 64, 90),
    )
    palette["LOG_KEYWORD_COLORS"] = _keyword_colors(palette)
    return palette


_BUILDERS = {
    "origin": _origin_palette,
    "cyberpunk": _cyberpunk_palette,
}


def team_label(color: bool):
    """Text colour for a side's team name (see WHITE_LABEL/BLACK_LABEL in the
    active palette). `color` is a python-chess colour bool (True == white)."""
    return WHITE_LABEL if color else BLACK_LABEL


def team_neon(color: bool):
    """The vivid per-side colour the neon piece set tints its silhouettes with
    (see WHITE_NEON/BLACK_NEON). `color` is a python-chess colour bool."""
    return WHITE_NEON if color else BLACK_NEON


def apply_theme(name: str, white_color=None, black_color=None):
    """Swap the active palette in place. Call once after the menu closes
    (and again after loading a save, in case its theme/colours differ)."""
    builder = _BUILDERS.get(name, _origin_palette)
    palette = builder(white_color or DEFAULT_WHITE_COLOR, black_color or DEFAULT_BLACK_COLOR)
    globals().update(palette)
    # Active theme name, read by render.draw_token to decide token styling.
    globals()["THEME_NAME"] = name if name in _BUILDERS else "origin"


apply_theme("origin")
