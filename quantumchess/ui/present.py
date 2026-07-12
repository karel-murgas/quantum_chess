"""Physical-window presentation for the supersampled UI.

The game (and the menu) draw onto their own offscreen *logical* surfaces --
the game at the supersampled resolution ``theme.WINDOW_W x WINDOW_H`` (see
``theme.SCALE``), the menu at the base ``theme.MENU_W x MENU_H``. Each frame,
``present`` smooth-scales that surface to fit the actual OS window, letterboxed
to preserve aspect ratio. This is what replaced the old ``pygame.SCALED``
nearest-neighbour upscale: downscaling a 2x render is free anti-aliasing, and an
upscale to a big monitor stays smooth instead of blocky.

Mouse events arrive in physical-window pixels, so ``to_logical`` maps a click
back onto whichever surface was last presented (menu vs. game -- they differ in
size, and ``present`` records the mapping for the one it just drew).
"""

from __future__ import annotations

import pygame

# (destination Rect within the window, (source_w, source_h)) from the last
# present() -- what to_logical() inverts. None until the first frame.
_fit = None

# Fullscreen state, so toggle_fullscreen() can restore the previous windowed
# size when leaving fullscreen.
_fullscreen = False
_windowed_size = None


def toggle_fullscreen(window):
    """Toggle real fullscreen and return the new display surface. Explicit
    ``set_mode`` (rather than ``pygame.display.toggle_fullscreen()``) because
    we present manually: fullscreen just becomes a bigger window, and
    ``present`` letterboxes the same source into it. Entering fullscreen uses
    the desktop resolution; leaving restores the last windowed size."""
    global _fullscreen, _windowed_size
    if _fullscreen:
        size = _windowed_size or window.get_size()
        _fullscreen = False
        return pygame.display.set_mode(size, pygame.RESIZABLE)
    _windowed_size = window.get_size()
    _fullscreen = True
    # (0, 0) tells SDL to use the current desktop resolution.
    return pygame.display.set_mode((0, 0), pygame.FULLSCREEN)


def is_fullscreen() -> bool:
    return _fullscreen


def present(window: pygame.Surface, source: pygame.Surface) -> None:
    """Smooth-scale ``source`` to fit ``window`` (letterboxed) and blit it,
    recording the placement so ``to_logical`` can invert a later click."""
    global _fit
    ww, wh = window.get_size()
    sw, sh = source.get_size()
    scale = min(ww / sw, wh / sh)
    w, h = max(1, round(sw * scale)), max(1, round(sh * scale))
    x, y = (ww - w) // 2, (wh - h) // 2

    scaled = source if (w, h) == (sw, sh) else pygame.transform.smoothscale(source, (w, h))
    if (x, y) != (0, 0) or (w, h) != (ww, wh):
        window.fill((0, 0, 0))          # letterbox bars
    window.blit(scaled, (x, y))
    _fit = (pygame.Rect(x, y, w, h), (sw, sh))


def to_logical(pos):
    """Map a physical-window position to coordinates on the last-presented
    source surface. Clamped to the surface so a click in a letterbox bar maps
    to the nearest edge rather than off-surface."""
    if _fit is None:
        return pos
    rect, (sw, sh) = _fit
    x = (pos[0] - rect.x) / rect.w * sw
    y = (pos[1] - rect.y) / rect.h * sh
    x = min(max(x, 0.0), sw - 1)
    y = min(max(y, 0.0), sh - 1)
    return (int(x), int(y))
