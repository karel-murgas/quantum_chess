# UI reference (`quantumchess/ui/`)

**The only place that imports pygame.** Never import it from the engine modules.
For the one-page map see [ARCHITECTURE.md](../ARCHITECTURE.md); for the visual-design
history of the skins see [HISTORY.md](HISTORY.md).

---

## Rendering pipeline

### `present.py` — physical-window presentation

Everything draws onto offscreen **logical** surfaces (the game at
`WINDOW_W×WINDOW_H`, the menu at `MENU_W×MENU_H`). `present(window, source)`
smooth-scales the source to fit the OS window, letterboxed; `to_logical(pos)` maps a
physical click back onto whichever surface was last presented.

The window is resizable and fullscreen-toggleable (F11). `main.py` / `App.run`
translate every `MOUSEBUTTONDOWN` through `to_logical` before dispatch and recreate the
window on `VIDEORESIZE`.

⚠️ **Any live mouse read must translate too** — `BaseSkin.hover_square` maps
`pygame.mouse.get_pos()` through `to_logical` before `square_at_pixel`, or the hover
highlight lands on the wrong square.

⚠️ **F11 goes through `present.toggle_fullscreen(window)`** (explicit
`set_mode((0,0), FULLSCREEN)` / restore), *not* `pygame.display.toggle_fullscreen()` —
the latter misbehaves with a manually presented window. `VIDEORESIZE` is ignored while
`present.is_fullscreen()`.

Tests are unaffected: they drive `handle_mouse_down` directly in scaled logical space
(clicking `render.square_rect(...).center`), never touching the physical translation.

### `theme.SCALE` — supersampling

The whole game frame is drawn at `SCALE`× (=2) the base layout resolution onto an
offscreen surface, then smooth-scaled to the window. Downscaling a 2× render is free
SSAA, and an upscale to a big monitor stays smooth.

- **All game geometry constants in `theme.py` are `× SCALE`.** Because `SCALE` is a
  *static* constant (fixed at import), the module-level copies the skins capture at
  import time already see the scaled values — no runtime plumbing.
- **Every stray pixel-literal** (font sizes, panel Y-flows, stroke widths, chip
  padding, radii) is wrapped in `theme.px(n)` = `round(n * SCALE)`, since the skins'
  panels are authored in absolute pixels.
- `theme.MENU_W`/`MENU_H` are the **base (unscaled)** window size: the menu is authored
  at that resolution on its own surface and scaled the same way, so `menu.py`'s many
  absolute literals stay untouched.

---

## `theme.py`

Layout/colour constants and the glyph map (`♔♕♖♗♘♙`, tinted per side rather than using
separate black/white codepoints).

Two presets: **origin** (the original wood-board look) and **cyberpunk** (neon-on-dark).
`apply_theme(name, white_color, black_color)` rebuilds the whole palette dict and does
`globals().update()` — **every other UI module reads palette values as `theme.X`
(attribute lookup, never `from theme import X`)**, so one call after the menu closes (or
after `App.load_from`) repaints everything with no plumbing.

Cyberpunk's palette is *generated*, not hardcoded: `_cyberpunk_palette` mixes each
player's chosen colour with fixed dark/light grays (`_mix`/`_clamp`) to build the board
squares, each side's token fill/border, and an ink colour picked for contrast
(`ink_for`, luminance-based) — so an arbitrary neon still reads against its token.

Other per-theme tables:

- **`TERMS`** — reskins the *narration* in the side log: "captures" → "deletes",
  the fizzle clause, "vanished" branches, the win line, `castle_verb`
  ("castles"/"reroutes"), `check_word`/`safe_word` ("CHECK"/"LOCKED ON"),
  `mass_verb`/`mass_split_verb`/`mass_collapse_clause`, and the on-board collapse
  captions (`reveal_present`/`reveal_absent`/`reveal_capture`).
- **`LOG_KEYWORD_COLORS`** — maps each `TERMS` key to a colour already in the palette
  (captures reuse `EVENT_ABSENT_COLOR`, splits reuse `SPLIT_PICK_RING`, a win reuses
  `SELECTED_RING`, `vanished_word` reuses `LEGAL_CONTACT_DOT`), via a shared
  `_keyword_colors(palette)` helper both palettes call — a new keyword needs one
  mapping, not per-theme duplication.
- **`WHITE_LABEL`/`BLACK_LABEL`** + `team_label(color)` — each side's *name text*
  colour (origin: cream / lightened wood-brown, legible on the dark panel; cyberpunk:
  each side's own neon). Used for the turn title, tray headers, win banner, and inline
  in the side log.
- **`SWATCHES`** — the curated 8-colour list the menu's colour pickers offer.
- **`EVENT_PRESENT_COLOR`/`EVENT_ABSENT_COLOR`** — the green/red collapse-flash hues.

---

## `pieces.py` — the piece-set registry/renderer

The single place that turns a `(ptype, color)` into board art.

| Set | Source |
|---|---|
| `cburnett`, `merida` | Real Lichess SVGs under `ui/assets/pieces/<set>/{wP..bK}.svg`, rasterized at the exact pixel size via `pygame.image.load_sized_svg` — no Cairo/`cairosvg` dep, crisp at any size |
| `neon` | Generated at runtime: cburnett silhouettes recoloured to the side's colour |
| `tiger` | Vector-traced tiger figures (see below) |
| `cthulhu` | Vector-traced Lovecraftian figures, same recipe as tiger (see below) |
| `dragon` | Vector-traced dragon figures, mixed from two sheets (see below) |
| `unicode` | The original glyph look, drawn by the font path |

A set is either **literal** (SVGs drawn as-is: cburnett/merida) or **tinted**
(`_TINTED`, a `{set -> base set supplying the shapes}` map: neon borrows cburnett's
silhouettes, tiger/cthulhu/dragon have their own) — `render_art` recolours a tinted set to
`theme.team_neon(color)`. Recolouring is numpy-free (`_recolor`): `BLEND_RGBA_MAX`
floods rgb to white keeping each pixel's alpha, then `BLEND_RGBA_MULT` stamps that
alpha onto a flat colour fill.

`render_token` composites a soft drop shadow (classic sets), a coloured glow (neon), or
a **contrast rim** (tiger, cthulhu, dragon) via `gaussian_blur`, cached.

Two caches: raw SVG rasters keyed `(set, code, size)` (theme-independent, never
invalidated) and composited tokens keyed by a **revision counter** that `set_active`
bumps — so a mid-match theme/colour/set change repaints without stale colours while the
expensive raster survives.

**The active set is per side.** `_active` is a `{colour -> set}` map; `pieces.active(color)`
reads it and `pieces.set_active(white, black)` sets it — called next to *every*
`theme.apply_theme(...)` (main.py, `App.load_from`, `App._handle_settings_click`) as
`set_active(config.white_piece_set, config.black_piece_set)`. Every renderer that branches
on the set passes the piece's `color`, so White can be `cburnett` while Black is `neon`.

**Adding a set** = drop its SVGs in a folder + one `(key, label)` line in `PIECE_SETS`.
Both menu piece-set dropdowns are built from `pieces.available()`, so it shows up automatically.

### The `tiger` set

Traced from the user's raster sheet `assets/tiger_set.png` by
**`tools/trace_tiger.py`** — a *build-time only* script (needs `potracer`+`pillow`+`numpy`;
the game itself never imports them, it just loads the committed SVGs). The tracer splits
the sheet into figures by ink-projection row/column gaps, traces each into Béziers, and
writes all six into **one shared square canvas** so the sheet's own relative piece sizes
survive the rasterizer's fit-to-token-box — except the paw, scaled ×1.6 (at the sheet's
0.39-of-a-king it read as a speck).

⚠️ `potrace.Bitmap` inverts internally, so it must be handed the **negated** ink mask,
else it traces the background.

The art has **no light/dark pair** — one silhouette per piece — so tiger is a *tinted*
set: `w*.svg` and `b*.svg` hold the same shape and the colour comes from each team's
own colour at runtime. Because a team colour can land anywhere on the light/dark range
(a pale tiger would vanish on a light square), `render_token` gives it a contrast rim:
the silhouette recoloured to `theme.ink_for(tint)`, blurred and blitted 3× so it's
near-opaque at the edge and fades out softly. On cyberpunk that rim reads as a glow for
free.

### The `cthulhu` set

Same recipe as tiger, off a different sheet: traced from `assets/cthulhu_set.png` by
**`tools/trace_cthulhu.py`**. That sheet is simpler than tiger's — two rows (green,
light-blue) of the same six figures, no separate pawn row — so the tracer skips the
pawn-rescale step entirely and just reads six boxes from one row band. Also a *tinted*
set (`_TINTED["cthulhu"] = "cthulhu"`) with the same contrast-rim treatment in
`render_token`.

### The `dragon` set

Same recipe again, but off **two** sheets instead of one: `assets/dragon_set_a.png`
supplies the bishop, rook and pawn; `assets/dragon_set_b.png` supplies the king, queen
and knight (the user's own pick of the better figure from each sheet). Traced by
**`tools/trace_dragon.py`**, which reads six boxes from each sheet's white-figure row,
picks the three per sheet it needs, and lays all six onto one shared canvas sized off
the largest figure across *both* sheets — so a piece from sheet A sits at the same
relative scale as one from sheet B. Also a *tinted* set (`_TINTED["dragon"] = "dragon"`)
with the same contrast-rim treatment in `render_token`.

---

## `animation.py` — collapse-animation model

**Pygame-free**, like the engine. `Token`/`Beat` dataclasses +
`build_animation(before, movers, events)`, which turns a resolved move/split into a beat
script: one TRAVEL beat (the mover, or every moving branch, slides out from its source)
then one FLASH beat per `CollapseEvent`.

It reconstructs each beat's static `rest` layer from the *pre-resolve* snapshot plus the
movers, evolving it event by event — that's what keeps a split branch that will vanish
**visible until its own flash fades it** (the engine already dropped it instantly). Fades
come from `CollapseEvent.removed`, shatters from `captured_square`; a confirmed mover goes
solid in `rest` on its own flash. Durations vary by slide distance and whether the beat
also removes something.

---

## `render.py`

Pure drawing primitives — nothing here mutates state. Board, ghost tokens (alpha ∝
probability + fraction label), same-piece aura outlines, legal-destination dots
(colour-coded safe/merge/risky-contact), promotion picker, `draw_beat` (one animation
beat at progress `t`: rest tokens, smoothstep-eased travel, fading `removed` ghosts, a
capture `shatter`, the green/red flash, a floating caption chip), the plan rings/arrows/
controls, the vignette.

`draw_token` is the shared token renderer (live board *and* animation); `blit_piece_art`
is its art branch, reused by the skins' own `draw_token`.

`draw_log_line(surface, text, pos, font, default_color, name_colors=None)` renders one
side-log line with its theme keywords in colour: `_log_keyword_spans(text, extra_specs=())`
searches for every `theme.TERMS` value *plus* any extra `(text, color)` pairs (longest
first, so a multi-word phrase like `win_suffix` isn't shadowed by a shorter keyword inside
it, nor a team name by a keyword inside it), keeps non-overlapping matches, and blits the
line as alternating default/keyword segments. Team names are passed as `name_colors`
(`{name: theme.team_label(color)}`) so a name reads in its team colour inline too. A
keyword split across a word-wrap boundary just isn't coloured on that render — the panel is
wide enough that this hasn't come up.

`_draw_danger_marker` overlays a red warning ring + a `frac_str` chip (the mover's own
resulting check probability) on top of a normal legal-move dot.

---

## `skins/` — one drawing language per view

Two views a player can switch between **live mid-match**: **Quantum HUD** (`hud.py`) and
**Clarity / Data-viz** (`clarity.py`). There is no "no skin" classic render path —
`App.draw()` is just `self.skin.draw(self)`.

`base.py`'s `BaseSkin` supplies the shared contract (hit-testing/geometry, fonts, the
`_check_values` cache, `_hbar`/`_caps_label` helpers, the planning overlay). Each skin owns
its own `panel_rects()` — so drawn and clickable positions stay in lock-step;
`App.handle_mouse_down` always hit-tests against `self.skin.panel_rects()` — and a
from-scratch `draw_panel`.

---

## `app.py` — `App`

Click-driven interaction: select → move or split → collapse animation. Promotion picker,
side log. Both players see the **entire** board including all ghosts/probabilities at all
times (hotseat, no hidden information) — only the collapse dice roll is unknown until
resolved.

Every side-log line reads team names/verbs off `self.config.team_name(color)` /
`theme.TERMS[...]`, never hardcoded "White"/"Black"/"captures".

### Surrender

Instead of moving or splitting, the side to move can give up on the spot
(`App.surrender`): it sets `QuantumBoard.winner`/`game_over` directly — the other
side wins immediately, same end-state as a king capture but with no move played, so
it bypasses the move/collapse machinery entirely (there's no `Move`/`Split`
involved). Gated behind a **click-to-arm / click-again-to-confirm** side-panel
button — any other click, or Escape, cancels the armed confirm — so a stray misclick
can't end the game.

### Animation driving

Right before resolving, `_execute_move` / `_handle_split_click` snapshot the board
(`_snapshot_tokens`); after, they build a beat script via `animation.build_animation`
(`self._beats`, current = `[0]`). `update(dt)` advances `_beat_elapsed` and drains finished
beats (a single long frame can drain several short ones); `draw` renders the current beat
*instead of* the live pieces while `is_animating()`, then hands back to the normal board
once `_beats` empties (`qb` is already the final state throughout).

Any click / New Game / Escape flushes via `_flush_animation` (skip to end) — but a **winning
move's animation always takes priority** and can't be skipped past into New Game.

**Quiet relocate/merge moves (zero events) resolve instantly, no beats**, so ordinary play
stays snappy. Only a move that actually measured something animates — plus two exceptions:
*every* split (both branches always slide out), and a **completed castle** (`_execute_move`
snapshots the rook's pre-move `Token` too and, if `move.castle_rook` completed — checked by
whether the rook ghost actually landed on `rook_to`, not by the `has_moved` flag — passes
*both* the king's and rook's `(dest_token, from_square)` pairs into `build_animation`).

### Check overlay wiring

`show_check` (default on; panel button / `K`). `_check_readout()` builds the two per-king
readout lines from `check.check_probability`. `_selfcheck_by_square()` returns
`{to_square -> Fraction}` for the *move-mode* selection's destinations that would **raise**
the mover's own king danger above its current baseline (via `check.move_self_check`).

Both are cached, keyed on a `self._ply` counter bumped on every board change (move/split
resolve, `new_game`, `load_from`) — the per-destination board deep-copies are far too
expensive to recompute per frame. Split mode shows the readout but no per-branch warnings (a
split leaves half the mass on the source, so it barely opens a line — deliberately out of
scope).

### Piece info popover (right-click pin)

A read-only way to identify a token — useful for any reskinned set (tiger/cthulhu) whose art
doesn't obviously map to a standard piece name, and for reading a piece's quantum state without
selecting it (selection only ever works for **your own** piece on **your** turn; this works for
either side, any time, since it touches no selection/move state).

`App.handle_right_click` (wired in `run()` for `MOUSEBUTTONDOWN` button 3, routed through
`present.to_logical` like a left click) toggles `self.pinned_square` — right-click a piece to pin
it, again to unpin, elsewhere to repoint. Two things then draw for it, both in `BaseSkin.draw`:

- `draw_pinned_highlight` rings every ghost of the pinned piece in its aura colour (the same
  "ring the square in the piece's aura colour" idiom `render.draw_plan_rings` uses for a piece
  being planned), drawn in the ordinary board phase, under the tokens — so the whole superposed
  cloud is obvious on the board itself, not just listed in the card.
- `draw_pinned_inspector` renders the piece's identity plus every ghost's square and a probability
  bar (reusing `_hbar`, the same primitive Clarity's selected-piece inspector uses), drawn last —
  on top of everything except the promotion picker, so every skin gets it with no bespoke panel
  work, the same pattern the mass-planning overlay uses. Placement comes from a shared
  `BaseSkin._popover_rect`: anchored just outside the piece's square (below it if the square is in
  the board's top half, above otherwise, so the card never covers the piece it describes) and
  clamped (`pygame.Rect.clamp_ip`) to the logical surface so an a/h-file or rank-1/8 token's card
  can't spill off-screen.

The pin is deliberately transient, not real state: `handle_mouse_down` clears it on **any** left
click, and so do `cancel_selection` (Escape), `new_game`, and `load_from` — dismissal follows the
standard click-triggered-popover convention (click away / Escape / toggle), not a hover tooltip's
mouse-leave, so it can't vanish out from under you while you're still moving the mouse toward your
next move.

### Mass-move / mass-split planning

When the `mass_movement` dial is on, clicking a **superposed** own piece opens planning
instead of an ordinary one-click move/split. (A *solid* piece still moves/splits the ordinary
way — planning only makes sense for >1 ghost.)

**Entry is mode-independent** (clicking a superposed piece always opens planning, whichever
of Move/Split is active). **Inside** a plan, the Move/Split toggle keeps its ordinary meaning:
it says whether the ghost you're currently aiming **moves** (one click, commits immediately)
or **splits** (the two-pick gesture). `App.plan_splitting()` = `can_mass_split() and
mode == "split"`; `_plan_cap()` is the resulting destination cap (1 or 2). The toggle stays
switchable mid-plan (`toggle_mode` drops any half-made assignment but keeps the plan). With
`mass_split` *off* the toggle can't mean anything inside a plan, so it abandons the plan and
`_begin_plan` forces `mode = "move"` so the panel can't show a stale "SPLIT" label.

*(Both halves of this were real playtest bugs — see [HISTORY.md](HISTORY.md).)*

State: `self.plan` maps every ghost's source square → a **tuple** of its chosen
destination(s) (all default to `(source,)` = "stay"; one square = relocate, two distinct
squares = that ghost splits in half). `self.plan_active` is the ghost being aimed,
`self.plan_piece` the piece, `self.plan_pick_a` the first branch chosen for the active ghost
(mirroring top-level `split_pick_a`).

`_handle_plan_click` cycles select-ghost → pick-target (click the ghost again to hold);
`_commit_plan_branch` centralizes "record this branch" for both first/second pick and cap
1/2. `plan_legal()` gives the active ghost's targets in the skin's highlight style (a
`CAPTURE_SOLID` is tagged **risky**, like a split, since a mass leg's mover isn't guaranteed
present). With `split_stay_enabled` off, `plan_legal()` withholds the active ghost's own square
while `plan_splitting()` is true, so a split leg's *second* branch can't land back on the
source — the "hold in place" click in `_handle_plan_click` (a plain move-only leg, not a split)
is a separate code path and stays unaffected. Aiming a ghost pawn at the promotion rank pops the
ordinary promotion picker (`_pending_plan_promo` holds the leg; `plan_promo[(from, to)]` records
the choice per branch,
pruned via `_prune_promos` if that ghost is re-aimed) — no auto-queening.

Escape backs out the in-progress ghost assignment first, then the whole plan. Confirm (a
floating `render.mass_controls_rects()` button over the board, or `Enter`) → `_confirm_plan`
builds a `MassMove` (every leg single) or a `MassSplit` (when the dial is on), logs it, and
animates every moving branch sliding out — the winning branch is matched by
`result.chosen_from` **+** `chosen_to` (so a split's *sibling* isn't mistaken for it), lands
solid, and the losers fade.

With `mass_all_must_act` on, `_confirm_plan` first checks `App._plan_fully_acted()` (every leg's
destinations differ from a bare "stay") and simply returns without resolving anything if some
ghost hasn't acted — the plan stays open, both for the mouse Confirm click and the `Enter` key
(they funnel through the same method). `BaseSkin.draw_plan` reflects this back at the player:
`render.draw_mass_controls`'s `confirm_enabled` dims the Confirm button, and the status hint swaps
to say every ghost must move or split first.

The plan is **transient UI state** — not persisted; cleared by `new_game`/`load_from`.
Planning is skin-agnostic: drawn centrally in `BaseSkin.draw`'s `is_planning()` branch, so
both skins get it without touching their bespoke panels.

*Known quirk: the floating Confirm/Cancel controls overlap the board's bottom-rank squares.*

### Save / load

`App.save_to`/`load_from` wrap `persistence.save_game`/`load_game` against a single quicksave
slot (`DEFAULT_SAVE_PATH = saves/quicksave.json`); wired to both panel buttons and `F5`/`F9`.
`load_from` catches `OSError`/`ValueError`/`KeyError` (missing file, unknown version, malformed
JSON) and logs a message instead of crashing.

### Skin switching & in-game Settings

`self.skins` / `self.skin_index` / `self.skin` are built in `__init__`; `cycle_skin()` advances
to the next — wired to **Tab** and to a `"view"` key in the panel rect dict. Like
`show_captured`/`show_check`, it's a **display preference**: hit-tested ahead of the "whose
turn / game over" gates, and untouched by `new_game`/`load_from`.

`open_settings()` reopens `ui/menu.py`'s `Menu` as a full-screen overlay, constructed with
`in_game=True, initial_config=self.config` so it opens pre-filled with the *match's current*
dials rather than the last saved setup. `self.in_settings`/`self.settings_menu` gate everything:
`draw()` renders the menu instead of the skin entirely, and `run()` routes `MOUSEBUTTONDOWN` to
`_handle_settings_click`. `handle_keydown` special-cases `in_settings` up front — Escape closes
and **discards every edit** (`self.config` is untouched until a button is actually clicked), F11
still toggles fullscreen, anything else forwards to `settings_menu.handle_keydown` (so the
team-name fields keep working); normal game hotkeys don't fire while it's open.

Reachable via a "Settings (O)" panel button or the **O** key; both go through `open_settings()`,
which is a **no-op mid-animation** (same guard as Save/Load) so a collapse reveal can't be
interrupted.

`_handle_settings_click` reads the `(action, config)` tuple `Menu.handle_click` returns, always
calls `theme.apply_theme(...)`, then branches:

- `"resume"` — swap in `self.config` and log "Settings updated." `qb`/turn/log/mode are left
  completely alone, so changing a colour mid-game costs neither player their position.
- `"new_game"` — `new_game(config)` resets the board with the edited dials. (`App.new_game`'s
  `config` param is optional: no-arg — the post-win "New Game (N)" button/key — reseeds the rng
  randomly and keeps the current config; passed a config, it adopts it and seeds from
  `config.seed`, deterministic like a menu-driven start.)

---

## `menu.py`

Pre-game dial picker: collapse mode, splitting, split stay, mass moves, mass split, all-must-act,
seed, board theme, team names, team colours, per-team piece sets.

**The dial toggles are laid out as a small dependency tree, not a flat row.** `_DIAL_PARENT` maps
each non-root dial to the one it needs (`split_stay`/`mass` → `split`; `mass_split`/
`mass_all_must_act` → `mass`). `_dial_rows` groups the currently-visible keys into levels (root
first, each level exactly the children of the previous one — see `_DIAL_PARENT`); `_dial_rects`
lays each level out centered under its own parent's x-position (not the whole screen), so the tree
visually branches exactly where the dial dependencies do — e.g. the mass-split/all-must-act pair
sits centered under "Mass moves", offset from the page center, not under "Splitting". `_draw_dial_tree`
draws elbowed connector lines (parent bottom → midpoint → child top) *before* the buttons so the
boxes sit on top of the line ends. A dial whose prerequisite is off simply **isn't drawn or
clickable**, not merely dimmed. Everything below the tree reserves fixed vertical space for its
tallest possible shape (3 levels) so lower sections never have to move as dials toggle. Toggling a
dial off **cascades** the reset onto anything depending on it, and `_build_config` re-applies the
same AND-gating defensively.

**Split stay** (`split_stay_enabled`, default on) governs whether a split may offer the ghost's
own square as one of its two destinations — the "stay + move" split (see `app.py` below and
`ENGINE.md::legal_split_targets`). It's a child of `split`, not of `mass` — it only depends on
splitting being on, and applies equally to an ordinary one-ghost split and to a split leg inside a
mass-split plan. It has no bearing on a *plain move* (single-ghost or a mass-move leg that isn't
splitting) — holding a ghost in place there was never part of "splitting" and stays available
regardless of this dial.

**All must act** (`mass_all_must_act`, default off, a child of `mass`) requires every ghost in a
mass-move/mass-split plan to be assigned a real move or split — none may be left at its default
"stay" (`(from_square,)`) assignment. Enforced entirely on the confirm path: `App._plan_fully_acted`
checks every leg, and `_confirm_plan` is simply a no-op while it's violated (same for the Enter-key
shortcut, since both call the same method) — the plan just stays open so the player can go assign
the remaining ghost(s). The skin dims the Confirm button (`render.draw_mass_controls`'s
`confirm_enabled`) and swaps the status hint to say so while blocked. Composes with split stay
exactly as it reads: a ghost that splits with one branch staying still counts as having acted (a
split's two destinations can never both equal the source — see `_commit_plan_branch`), so the two
dials don't conflict.

**Mouseover tooltips.** `_draw_hover_tooltips` (called last in `draw`) maps the real cursor position
onto the menu's own coordinate space via `present.to_logical(pygame.mouse.get_pos())` — one frame
stale at worst, since `present` records the mapping from the *previous* `present()` call — and,
if it lands on the collapse-mode buttons or any visible dial, renders a word-wrapped info box
(`_draw_tooltip`/`_wrap_text`) explaining that control, placed just below it (above if that would
run off the bottom of the screen). Copy lives in flat `_DIAL_TOOLTIPS`/`_COLLAPSE_TOOLTIPS` dicts,
independent of the on/off-state label text in `_dial_specs`.

**Team fields.** Names are click-to-focus text inputs (`active_field` + `handle_keydown`, wired
from the caller's event loop). Below the names, each side gets a **piece-set dropdown**
(`white_piece_open`/`black_piece_open`) sitting next to that team's colour swatches — closed it's
a button with a preview icon, the current set's name and a caret; opening it lays out
`pieces.PIECE_SETS` as a same-width option list directly beneath (`_piece_option_rects`). An open
dropdown is **modal**: `handle_click` checks it first and any click — hit or miss — selects (if it
landed on an option) and closes it, consuming the click rather than falling through to whatever
the option list is currently drawn over. Colour swatches (`theme.SWATCHES`) are shown only once
Cyberpunk is selected. A **"⇄" swap** button between the two name fields trades the white/black
name + colour + piece-set assignments in one click — since white always moves first, this is how
players pick who starts.

**Save/Load Teams** (flanking "Reroll seed") persists the cosmetic setup via
`persistence.save_teams`/`load_teams`; Load writes the values straight back into the menu fields
and a transient `team_status` line reports the result.

**Startup defaults.** `_load_startup_defaults()` tries `load_last_settings` first (every dial +
cosmetic field) and falls back to `_load_teams` (the older cosmetics-only path) if no
last-settings file exists yet — so a fresh launch reopens the menu exactly as it was last left,
with no save button to remember. A missing/corrupt file is silently ignored at startup, whereas an
explicit Load click still surfaces "No saved teams to load."

**Remembering.** `_finalize(action)` — what `handle_click` calls for the Start/New-Game/Resume
buttons — builds the config, calls `save_last_settings` (best-effort; an `OSError` is swallowed so
a failed remember can't block starting the game), then returns `(action, config)`.

**Reused mid-game as the Settings screen.** `in_game: bool = False` and
`initial_config: Optional[GameConfig] = None`. `initial_config`, when given, seeds every field from
it instead of calling `_load_startup_defaults()`. `in_game` titles it "Settings" instead of "Match
Setup" and adds a `resume_rect` ("Resume Game") beside Start (relabeled "New Game"); pre-game,
`resume_rect` is `None` and Start stays the single centered button. `handle_click` returns
`(action, GameConfig)` — `"start"` pre-game, `"new_game"`/`"resume"` mid-game — so a caller can tell
"reset the board" from "just apply these settings". All three build via the shared `_build_config()`.

---

## `main.py` (repo root)

Entry point. Calls `theme.apply_theme(config.theme, config.white_color, config.black_color)` and
`pieces.set_active(...)` once the menu's Start button returns a `GameConfig`, before constructing
`App` — this is the one call site that actually activates a chosen theme.
