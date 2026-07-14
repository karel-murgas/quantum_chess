# UI reference (`quantumchess/ui/`)

**The only place that imports pygame.** Never import it from the engine modules.
For the one-page map see [ARCHITECTURE.md](../ARCHITECTURE.md); for the visual-design
history of the skins see [UI_REDESIGN.md](../UI_REDESIGN.md).

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
| `unicode` | The original glyph look, drawn by the font path |

A set is either **literal** (SVGs drawn as-is: cburnett/merida) or **tinted**
(`_TINTED`, a `{set -> base set supplying the shapes}` map: neon borrows cburnett's
silhouettes, tiger has its own) — `render_art` recolours a tinted set to
`theme.team_neon(color)`. Recolouring is numpy-free (`_recolor`): `BLEND_RGBA_MAX`
floods rgb to white keeping each pixel's alpha, then `BLEND_RGBA_MULT` stamps that
alpha onto a flat colour fill.

`render_token` composites a soft drop shadow (classic sets), a coloured glow (neon), or
a **contrast rim** (tiger) via `gaussian_blur`, cached.

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
present). Aiming a ghost pawn at the promotion rank pops the ordinary promotion picker
(`_pending_plan_promo` holds the leg; `plan_promo[(from, to)]` records the choice per branch,
pruned via `_prune_promos` if that ghost is re-aimed) — no auto-queening.

Escape backs out the in-progress ghost assignment first, then the whole plan. Confirm (a
floating `render.mass_controls_rects()` button over the board, or `Enter`) → `_confirm_plan`
builds a `MassMove` (every leg single) or a `MassSplit` (when the dial is on), logs it, and
animates every moving branch sliding out — the winning branch is matched by
`result.chosen_from` **+** `chosen_to` (so a split's *sibling* isn't mistaken for it), lands
solid, and the losers fade.

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

Pre-game dial picker: collapse mode, splitting, mass moves, mass split, seed, board theme, team
names, team colours, per-team piece sets.

**Dial row is laid out dynamically.** `_dial_specs`/`_dial_rects` include a toggle only once its
prerequisite dial is on (mass moves needs splitting; mass split needs mass moves) — a dial whose
prerequisite is off simply **isn't drawn or clickable**, not merely dimmed. The rects (and the
row's centering) are recomputed on every `handle_click`/`draw` rather than fixed in `__init__`,
since how many buttons exist depends on current state. Toggling a dial off **cascades** the reset
onto anything depending on it, and `_build_config` re-applies the same AND-gating defensively.

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
