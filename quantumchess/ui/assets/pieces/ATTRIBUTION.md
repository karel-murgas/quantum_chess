# Piece set attributions

SVG piece artwork bundled here is sourced from the Lichess project
(https://github.com/lichess-org/lila, `public/piece/<set>/`).

- **cburnett** — by Colin M.L. Burnett. Licensed GPLv2+ / BSD / GFDL
  (multi-licensed; effectively free for reuse). Lichess's default set.
- **merida** — by Armando Hernandez Marroquin. Distributed by Lichess under
  the GPL.

The **neon** set in the game is not bundled art: it is generated at runtime by
tinting the cburnett silhouettes with each team's colour and adding a glow (see
`quantumchess/ui/pieces.py`).

The **unicode** set uses the system font's chess glyphs (♔♕♖♗♘♙), no assets.
