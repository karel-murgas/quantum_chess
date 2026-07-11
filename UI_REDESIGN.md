# Quantum Chess — UI redesign brief

Living design doc for the UI overhaul (started 2026-07-11). Goal: make the game
**more comfortable, clearer, and sexier** — improving both UX (how it plays) and
visuals (how it feels) — and make the *theme drive real design elements*, not
just a recolor. Deliverable: a **playable demo that switches between several UI
variants live during play**, so we can feel each one and pick.

---

## 1. How players actually interact (and what that demands)

Context: **hotseat, 2 local humans, one screen, mouse-driven, no timer, no hidden
information.** Both players see every ghost and probability at all times — the
*only* unknown is the collapse dice roll.

A single turn is this loop:

1. **Read the board** — who's superposed, where, how likely.
2. **Pick a piece** — and understand its *ghost cloud* (which ghosts are the same
   piece) and each ghost's probability.
3. **Decide move vs split** — the signature quantum choice.
4. **Pick destination(s)** — and gauge the *risk* of each (safe / merge / contact),
   plus whether it exposes my own king.
5. **Watch the collapse resolve** — the dramatic reveal.

Because there is no hidden information, **all the tension lives in the collapse
roll.** That is the moment to maximize. Everything else is a *decision-support*
problem: show the quantum state clearly enough that a good decision is easy.

Two humans sharing a screen also means: they **point at squares and talk about
them** (coordinates matter), and they read the board **from a slight distance**
(contrast and size matter).

### What must catch the eye, in priority order
1. **Whose turn + current mode** — persistent, glanceable, impossible to mistake.
2. **The collapse reveal** — the payoff moment; deserves the most drama.
3. **A selected piece's ghost cloud + per-ghost probability** — the core decision.
4. **Legal destinations and their risk** — safe / merge / risky-contact, legibly.
5. **Danger to your own king** — the advisory check overlay.

### Emphasis techniques available to us
Motion (hover feedback, selection pulse, eased transitions), depth (drop shadow,
glow, bloom), size & contrast for the *active* element, **dimming everything else**
during a key moment (e.g. the board darkens around a collapse), and thematic
framing (a bezel/HUD/frame that tells you which world you're in).

---

## 2. What's weak today (honest audit)

**UX**
- **No board coordinates.** The log says `e2->e4` but the board has no rank/file
  labels — players can't map notation to squares, and can't easily name a square
  to each other.
- **Mode is an invisible global toggle.** Move vs split is a persistent state
  that already caused a real bug (stuck in split mode into the next turn). It's a
  footgun and not discoverable at the moment of acting.
- **Legal-destination dots are tiny (~10px) and their colour code is unlabeled.**
  Green/blue/orange is meaningful but nothing on the board says what they mean.
- **Probability is hard to compare at a glance** — alpha + a small corner
  fraction. The alpha floor (70) means a 1/8 and a 1/2 ghost look similar.
- **Sibling identity only shows on selection.** With several superposed pieces
  you can't tell which ghosts belong together until you click one.
- **Turn indicator is just a small text line** — not a strong signal.
- **The side panel is a text-heavy stack of toggle buttons** — six buttons, a
  config line, a wall of log text. Functional, not comfortable.

**Visual**
- **Flat and functional.** No depth, no shadow, no glow, no texture. Tokens are
  Unicode glyphs in plain circles.
- **Theme = colours + narration words only.** "Origin" is wood colours, "cyberpunk"
  is tinted grays. Neither has a *structural / typographic / decorative* identity.
  The brief explicitly wants theme to drive **design elements**, not hue.
- **No hover / no idle motion** — the board feels inert until something resolves.

**What's already good (keep it):** the collapse animation choreography
(slide → flash → fade → shatter → caption) is genuinely nice; the exact-`Fraction`
probability model; the headless-engine / thin-UI split; per-theme narration terms.

---

## 3. Design principles for the redesign

- **The quantum state is the hero.** Superposition and collapse should be the most
  beautiful, most legible things on screen.
- **Theme is a world, not a palette.** Each theme changes frame, typography,
  token style, motion, and decorative motif — you should know which theme you're
  in from a black-and-white screenshot.
- **Emphasise the active, dim the rest.** Whatever the player is deciding on gets
  depth/glow/size; everything else recedes.
- **Comfort = feedback.** Hover states, selection pulse, eased transitions, and
  labels so nothing is a guess.
- **Don't break the engine boundary.** All of this lives in the `ui/` layer; the
  headless engine (`quantumchess/`) is untouched.

---

## 4. Proposed variants (to build into the switchable demo)

Each is a cohesive *design language*. Within each, the two content themes
(origin / cyberpunk) still differ **structurally**, not just in colour.

### A — Polished Evolution *(low-risk baseline)*
Same layout, production-quality finish. Beveled board frame with **engraved
rank/file coordinates**, soft **drop shadows** under tokens, **hover highlight**
on squares, a **selection pulse**, larger *labeled* legal indicators (solid ring =
move, double ring = merge, dashed = risky contact), a slim **probability bar**
under each ghost in addition to the fraction, and a **card-based side panel** with
grouped, icon-led controls and a big turn banner. Origin = wood + parchment +
serif; cyberpunk = the same skeleton in neon/glass.
*Purpose: the "just make it nice" option and the comparison anchor.*

### B — Quantum HUD *(cyberpunk-native, maximum drama)*
A sci-fi command console. Board inside an **angular HUD bezel** with corner
brackets and a faint grid glow. Ghosts drawn as **holographic tokens with an
orbiting probability ring** (ring arc ∝ probability) — no corner fractions needed.
**Entanglement webs**: a piece's ghosts are always joined by faint lines, so you
read the cloud without selecting. Collapse = **screen-dim + glitch + bloom + a
shockwave**. Side panel is a stack of "modules" with monospace readouts and
animated scanlines. Origin version = a warmer "astral observatory" reskin.
*Purpose: lean all the way into the theme-as-world idea.*

### C — Clarity / Data-viz *(readability-native)*
Optimise for reading the quantum state. Each ghost wears a **probability donut**
(filled arc, fraction centered) — instantly comparable across the whole board.
Sibling ghosts always share a coloured halo + a thin connecting web. A dedicated
**inspector panel** shows the selected piece's full distribution as horizontal
bars, and legal destinations become **labeled chips** (`↳ e4 · safe`,
`⚠ d5 · 3/8 risk`). Flat, high-contrast, accessible.
*Purpose: the "I can always tell exactly what's going on" option.*

### D — Tactile / Material *(origin-native, cozy)*
A physical board-game feel. Beveled wooden squares with grain and **carved
coordinates**, a **felt-textured panel**, pieces as engraved discs with real drop
shadows that **lift on hover/selection**. Ghosts are translucent "spirit" pieces
with a soft shimmer. Collapse = a satisfying **snap** with dust. Cyberpunk version
= brushed-metal + glass tiles.
*Purpose: warmth and physicality; the anti-sci-fi pole.*

---

## 5. Cross-cutting UX fixes (apply to whichever variant wins)
- **Rank/file coordinates** on the board.
- **Mode as a contextual choice**, not a sticky global: e.g. selecting a piece
  offers both "move here" and "split here" affordances, and mode always resets
  per turn (already fixed) — or a hold-to-split modifier. To be decided per variant.
- **Legend / labels** for destination risk colours.
- **Hover feedback** on squares and buttons.
- **Stronger turn + mode banner.**

---

## 6. Demo architecture (how live-switching works)
Introduce a `Skin` abstraction in `ui/` — an object exposing the drawing hooks the
board and panel need (`draw_background`, `draw_board`, `draw_token`,
`draw_ghost_prob`, `draw_selection`, `draw_legal`, `draw_panel`, collapse effects,
`fonts`). Each variant above is one `Skin` implementation. A thin
`demo_ui.py` runs the real `App`/engine but lets a hotkey (e.g. **Tab**, or number
keys) **cycle the active skin live mid-game**, and an on-screen chip names the
current variant. The engine, `app.py` interaction logic, and `menu.py` stay as-is;
only the drawing is swapped. Skins layer *on top of* the existing palette/`TERMS`
system so origin/cyberpunk keep working inside each variant.

Once we pick a winner, it graduates from the demo into the real render path.

---

## 7. Status — built (2026-07-11), narrowed to 3 variants after first playtest

Three variants are implemented and playable in the switchable demo. **Variant D
(Tactile/Material) was cut** after the first playtest — dropped by the user in
favour of focusing on the other three.

- **Run:** `python demo_ui.py` (menu → game, same as `main.py`).
- **Switch live:** **Tab** / **→** next, **Shift+Tab** / **←** previous,
  **1, 2, 3** jump to a variant (numbers auto-scale to however many are
  registered). A badge top-left of the board names the active variant.
- Everything else plays as normal (click to move, **M** split, **F5/F9** save/load,
  the collapse animation, etc.). Both content themes (origin / cyberpunk) work
  inside every variant — pick them in the menu as usual.

**Architecture as built**
- `quantumchess/ui/skins/base.py` — `BaseSkin`: orchestrates a frame from small
  overridable hooks; defaults reproduce the original look. **Hit-testing and
  geometry are shared** (`render.square_rect` / `render.panel_rects`), so clicks
  work identically under every skin. Also holds `_dotted_ring` (the "risky
  contact" ring cue), shared by any skin that wants Polished's ring language.
- `skins/polished.py` (A), `skins/hud.py` (B), `skins/clarity.py` (C) — one
  `Skin` each.
- `demo_ui.py` — `DemoApp(App)` sets `self.skin` and adds the cycle hotkeys +
  variant badge. Nothing else in `App` changed except a tiny, opt-in
  `self.skin` delegation in `draw()` and extracting `handle_keydown()`.
- The engine and normal `main.py` game are untouched; all 117 tests still pass.

**Round-2 feedback (first playtest) and fixes**
- **Dropped variant D** (Tactile/Material) entirely — removed from
  `SKIN_CLASSES`/`build_skins()`, file deleted.
- **Clarity's legal-move markers** were dot + text chip ("move"/"merge"/"risk")
  — replaced with Polished's ring language (solid ring = move, double ring =
  merge, dotted ring = risky contact), shared via `BaseSkin._dotted_ring`. Reads
  more consistently with the probability donuts already on the board and is
  less visually busy. Danger warnings still use the shared
  `render._draw_danger_marker`.
- **HUD ghosts read as featureless** — the old per-team dark-mixed translucent
  fill (`_mix(fill, black, 0.2)` at low alpha) made low-probability ghosts look
  like dim smudges. Fixed: every HUD token now has a bright, fixed
  "holographic" white-ish body (`HudSkin.HOLO_BODY`) with a fixed dark ink
  (`HOLO_INK`) for the glyph — legible regardless of side or probability —
  while **team identity moves entirely to the ring/glow colour** (each side's
  own accent, e.g. a player's chosen green), matching the "faction colour on a
  monochrome hologram" sci-fi trope and directly addressing "use white figures
  with my current green."

**Round-3: bespoke side panels (2026-07-11)**
Each tested variant now has a *from-scratch* side panel — not one shared layout
recoloured per skin. Panel geometry is **skin-owned** via a new
`BaseSkin.panel_rects()` (defaults to the canonical `render.panel_rects()`);
`App.handle_mouse_down` hit-tests against the *active skin's* rects, so drawn and
clickable positions stay in lock-step — the real game and all 117 tests use
`skin=None` and are byte-for-byte unchanged.
- **Polished** — a *control deck*: rounded cards w/ drop-shadow, a turn "hero"
  card (team-colour accent bar + king token + name + a MOVE/SPLIT status pill),
  grouped buttons, `● ON`/`○ off` toggle buttons, a KING SAFETY mini-bar
  readout, footer. Mirrors the domed-token / beveled-frame board.
- **Quantum HUD** — *console modules* (monospace): a bracketed `ACTIVE UNIT`
  header w/ blinking cursor, terminal toggle rows w/ state LEDs
  (`[M] MODE ··· SPLIT`), bracketed `[F5] SAVE` / `[!] ABORT MATCH` keys, a
  segmented **THREAT ASSESSMENT** gauge per king, a `SYSTEM LOG` feed, and a
  telemetry footer.
- **Clarity** — a *data panel*: flat, high-contrast, everything small-caps
  labeled with hairline rules; a flat turn header, a segmented **Move/Split**
  control, pill **switches**, labeled KING SAFETY bars, the selected-piece
  **inspector** promoted into a "SELECTED" section, and a "GAME LOG".

Shared helpers added to `BaseSkin`: `_check_values` (per-ply-cached king-danger
`Fraction`s for the gauges/bars), `_hbar`, `_caps_label`, `_round_card`;
`_draw_log_and_tray` gained an optional `bottom` so a panel can reserve a footer.

**Not yet done (deliberately, pending the pick)**
- The mode-as-sticky-global UX fix (section 5) is not changed yet — it affects
  interaction logic in `app.py`, so it waits until we're not A/B-testing looks.
- During a collapse, tokens use each skin's style but the flash/shatter/caption
  come from the shared `render` helpers; per-skin collapse flair is limited to
  the overlay (HUD glitch) for now.

---

## 8. Resolution — picked, merged into the real game (2026-07-11)

The playtest ended with two winners kept and one variant retired:

- **Polished Evolution (A) dropped entirely** — `skins/polished.py` deleted,
  removed from the skin registry. Its one surviving idea is a lineage note,
  not code: its glossy "hero card" turn header (accent bar + king token +
  name + a mode pill) is *why* Clarity's header got upgraded below, even
  though the header actually reused is styled after HUD's, not Polished's
  (see next point).
- **Clarity's turn header rebuilt**, borrowing the *structure* of HUD's
  "ACTIVE UNIT" module (a framed block that names whose turn it is and
  carries a live mode readout, judged nicer than Polished's plain card) but
  reskinned flat/hairline-bordered/no-glow to match Clarity's own
  data-panel language — no console brackets, no blinking cursor, no gloss.
  It's now a full-width bordered block: team-colour accent bar, king token,
  team name, a "to move" caption, and a MOVE/SPLIT chip in the corner
  (`skins/clarity.py::draw_panel`, the "turn header" block).
- **Quantum HUD and Clarity are now the only two views**, and the player can
  switch between them **live, any time during a match** — not just at the
  pre-game menu — via **Tab** or a **"view" control in the side panel**
  (a `CLARITY`/`HUD` segmented control in Clarity, a `[TAB] VIEW` row in
  HUD). This is a display preference like the removed-pieces tray or the
  check overlay: it survives `new_game`/`load_from` untouched.
- **The demo is gone.** `demo_ui.py` (the standalone playtest harness) is
  deleted; skin-cycling now lives directly in `App` (`ui/app.py`):
  `self.skins`/`self.skin_index`/`self.skin` are built in `__init__` (there
  is no more "skin is `None`" classic/legacy render path), and
  `App.cycle_skin()` is called from both the Tab key and the panel's "view"
  hit-test. `python main.py` *is* the redesigned UI now — there's no
  separate command to run it.
- **The panel-based "Quit" button** (confirm-then-fire, previously only
  reachable via the classic render path's `render.panel_rects()["quit"]`,
  which no skin actually implemented) was ported to both surviving skins
  so retiring the classic path didn't silently remove it.
- Test fallout: `test_m4_ui.py` used to build click coordinates from the
  canonical `render.panel_rects()`; since every skin now owns its own panel
  geometry, tests hit-test through `app.skin.panel_rects()` instead. 119
  tests passing (unchanged count — this was a like-for-like swap, not new
  coverage; the view-toggle behaviour itself was checked by hand, see
  below).
- Verified visually via headless PNG screenshots (`SDL_VIDEODRIVER=dummy`)
  of both skins mid-match (a split knight selected, a captured pawn in the
  tray, king-safety gauges live) to confirm the new header and the added
  panel rows fit without overlap, plus a scripted click-through of the
  view toggle, Tab hotkey, and the quit confirm-arm-fire dance.
