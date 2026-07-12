"""Quantum Chess entry point (Milestone 4: pygame hotseat UI).

Run:  python main.py            # normal: pre-game menu, then play
      python main.py --load     # skip the menu, boot straight into the quicksave
      python main.py --load PATH # ...from a specific save file

The --load shortcut exists to automate the "test a new feature in an in-progress
game" round-trip: instead of Save -> quit -> relaunch -> pick dials in the menu ->
Load, you just Save (F5) and relaunch with --load. It jumps directly into the
saved position (board, dials, RNG state, theme all restored) so a code change can
be exercised against the exact same game with a single command.
"""

import argparse
import sys

import pygame

from quantumchess.config import GameConfig
from quantumchess.ui import theme, present, pieces
from quantumchess.ui.app import App, DEFAULT_SAVE_PATH
from quantumchess.ui.menu import Menu


def _run_loaded(window, save_path):
    """Skip the menu and boot straight into ``save_path``.

    App.load_from replaces the board/config/rng/log/mode wholesale and re-applies
    the saved theme + piece set, so we just construct App with a throwaway default
    config and immediately load over it. Missing/corrupt saves are reported by
    load_from (into the side log); to fail loudly at the command line instead we
    check the file exists up front.
    """
    if not save_path.exists():
        print(f"No save file at {save_path} -- nothing to load. "
              f"Run 'python main.py' to start a new game.", file=sys.stderr)
        return
    app = App(window, GameConfig())
    app.load_from(save_path)
    app.run()


def main():
    parser = argparse.ArgumentParser(description="Quantum Chess (hotseat pygame UI).")
    parser.add_argument(
        "-l", "--load", nargs="?", const=str(DEFAULT_SAVE_PATH), default=None,
        metavar="PATH",
        help="Skip the menu and load a saved game directly "
             f"(default: {DEFAULT_SAVE_PATH}).",
    )
    args = parser.parse_args()

    pygame.init()
    pygame.display.set_caption("Quantum Chess")
    # The window starts at the base (unscaled) layout size and is resizable /
    # fullscreen-toggleable. Everything is drawn onto offscreen logical surfaces
    # and smooth-scaled to fit this window each frame (see ui/present.py) -- so
    # the pixels stay crisp at any window size instead of the old nearest-
    # neighbour SCALED upscale.
    window = pygame.display.set_mode((theme.MENU_W, theme.MENU_H), pygame.RESIZABLE)

    if args.load is not None:
        from pathlib import Path
        _run_loaded(window, Path(args.load))
        pygame.quit()
        return

    # The menu is authored at the base resolution; it draws to its own surface,
    # which present() scales into the window.
    menu_surf = pygame.Surface((theme.MENU_W, theme.MENU_H))
    menu = Menu(menu_surf)
    clock = pygame.time.Clock()
    config = None
    while config is None:
        clock.tick(60)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
            if event.type == pygame.VIDEORESIZE and not present.is_fullscreen():
                window = pygame.display.set_mode(event.size, pygame.RESIZABLE)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                result = menu.handle_click(present.to_logical(event.pos))
                if result is not None:
                    _action, config = result
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F11:
                    window = present.toggle_fullscreen(window)
                else:
                    menu.handle_keydown(event)
        menu.draw()
        present.present(window, menu_surf)
        pygame.display.flip()

    theme.apply_theme(config.theme, config.white_color, config.black_color)
    pieces.set_active(config.white_piece_set, config.black_piece_set)
    App(window, config).run()
    pygame.quit()


if __name__ == "__main__":
    main()
