# Piece set attributions

SVG piece artwork bundled here is sourced from the Lichess project
(https://github.com/lichess-org/lila, `public/piece/<set>/`).

- **cburnett** — by Colin M.L. Burnett. Licensed GPLv2+ / BSD / GFDL
  (multi-licensed; effectively free for reuse). Lichess's default set.
- **merida** — by Armando Hernandez Marroquin. Distributed by Lichess under
  the GPL.

The **tiger** set (`tiger/`) is the project's own: vector-traced from the
tiger-themed artwork the user supplied as `assets/tiger_set.png` (crowned tiger
faces for king/queen, a tiger profile for the knight, a paw for the pawn). The
SVGs are one silhouette per piece — the game tints them per team at runtime, so
`w*.svg` and `b*.svg` hold the same shape (see `quantumchess/ui/pieces.py`).
Traced with `tools/trace_tiger.py` (build-time only; needs `potracer`, which the
game itself never imports).

The **neon** set in the game is not bundled art: it is generated at runtime by
tinting the cburnett silhouettes with each team's colour and adding a glow (see
`quantumchess/ui/pieces.py`).

The **unicode** set uses the system font's chess glyphs (♔♕♖♗♘♙), no assets.
