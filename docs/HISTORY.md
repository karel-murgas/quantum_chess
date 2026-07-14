# Build history

Milestone status and a dated log of what shipped, why, and which playtest prompted it.
Mechanism detail lives in [ENGINE.md](ENGINE.md) / [UI.md](UI.md); this file is the
"when and why".

## Milestones

- [x] **M1** — headless board model + classical movement (capture-the-king), ASCII demo,
      tests.
- [x] **M2** — superposition: split, merge, ghost/probability bookkeeping (exact
      `Fraction`s), ghost-aware move generation, ASCII ghost view. Contact with a foreign
      ghost detected and deferred to M3.
- [x] **M3** — collapse: contact + path collapse (several pieces can collapse in one
      move), both modes, seedable RNG (`random.Random` passed in explicitly — trivially
      mockable), win-by-king-capture through collapse. Deterministic mechanism tests via a
      `ScriptedRng` test double, plus a statistical test (3000 trials, a 50% ghost captures
      ~50% of the time).
- [x] **M4** — pygame UI. See the log below; it grew far past the original scope.
- [x] **M5** — folded into M4 (`ui/menu.py` covers the v1 dials).
- [x] **M6** — polish pass; v1 playable end to end.

Test count: **214 passing** (2026-07-14).

---

## 2026-07-10

- **Collapse bug**: a superposed mover capturing a *certain/solid* piece wasn't measured
  — it was treated as a guaranteed capture. Fixed after the user asked "is movement
  measured only in case of collision?". Now `CAPTURE_SOLID` measures the mover too.

## 2026-07-11 — M4 lands, then a long polish run

**First interactive playtest** ("looks like it works"), then a self-review found three
real UX gaps, all fixed: Escape quit the whole app instead of cancelling the selection
(`App.cancel_selection`); no way to start a new game after a win (`App.new_game`, "New
Game (N)"); the Move/Split toggle was keyboard-only (now also a panel button). Also: a
winning move's collapse animation could be skipped past via New Game — animation now
takes priority over both New Game and Escape.

**Second playtest** turned up two bugs:

- *Display*: the side log always printed `(1/2), (1/2)` for a split even when splitting an
  already-partial ghost. The engine math was correct; the log line hardcoded the string.
  Fixed by reading the actual post-split `Ghost.prob` back off the board via the new public
  `render.frac_str()`. Transcript: `games/2026-07-11_split-fraction-log-bug.md`.
- *Interaction*: `App.mode` was never reset after a turn, so once either player used split
  mode it silently stayed in split mode for the **other** player's next turn — clicking an
  opponent's piece then read as "pick an illegal split target", which fails closed by
  clearing the selection (looks like the click did nothing). Fixed by resetting
  `mode = "move"` at the end of `_execute_move`/`_handle_split_click`.

**Save/load** (`persistence.py`, `F5`/`F9`) — motivated by wanting to resume that same game
after the app was closed. Round-trips board state, dials, and RNG state.

**Cyberpunk theme + team customization** — a second board theme alongside **origin**, with
per-match team names and accent colours picked in the menu. The cyberpunk palette is
*generated* from the two chosen colours, not hardcoded. A per-theme `TERMS` dict reskins the
side-log narration too ("captures" → "deletes") — added after the user specifically asked
for terminology to be part of the theme, not just colours.

**Collapse animation** — movement-first, then per-measurement reveals (slide → green/red
flash → fading ghosts → capture shatter → floating caption). Choreography and "variable by
complexity" pacing chosen with the user via `AskUserQuestion`. Engine `CollapseEvent`
enriched with `removed`/`captured_square` (still headless); new pygame-free `ui/animation.py`
builds the beat script. Quiet moves stay instant.

**Menu defaults from the last team save** so returning players don't re-pick their setup.

**Split can leave a branch on its own square** (user: "add current position to one of the
target possibilities"). Fixed at the rules layer (`legal_split_targets` prepends `square`
itself). UI-side, the "click the selected square to deselect" shortcut is suppressed in split
mode so that click reaches `_handle_split_click` as a "stay here" pick.

**Castling** — added after the user reached a real playtest position where it should have been
legal. Locked beforehand: only a king/rook that has *never* moved or split; ghosts between
them are resolved by walking the king's own path; the queenside b-file square must be empty;
the rook only follows if the king's walk reaches the full castle distance.

**Removed-pieces tray** — a "Removed pieces: ON/OFF (C)" toggle. Sourced straight from
`qb.pieces` filtered to `not p.alive` (a captured `Piece` already just sits there forever), so
no new engine state. Initially rows above the log; changed the same day (user asked for it
*beside* the log) to a second column with a thin vertical rule.

**Advisory check-probability overlay** (`check.py`) — user asked for an interface to "signal
check and partial check, like 3/8 to be a check" plus a warning before a move exposes their
own king. Does **not** reintroduce a check rule.

**Pawn move-gen bug** (playtest): a pawn's diagonal was offered as a `CONTACT` onto *any*
foreign ghost, including a **friendly** one (a7 "capturing" its own forked b7-pawn ghost on
b6). `_pawn_dest` checked the occupant's colour for a *solid* blocker but not a *ghost* one.

**UI redesign** (`UI_REDESIGN.md`) — explored 3 alternate visual languages live-switchable in a
standalone `demo_ui.py`. Concluded the same day: Polished Evolution **dropped**, **Quantum HUD**
and **Clarity kept** as the two real views, the whole thing merged into the main game and
`demo_ui.py` deleted. `App` itself now owns skin switching. A "Quit" button (previously only in
the now-deleted classic path) was ported to both skins so the merge didn't silently drop it.

**Split-based castling** — a playtest *crashed* the app: splitting a king toward a castle square
raised `ValueError("both split destinations must be legal")`, because the UI's split-mode
highlight dict offered the square while the rules layer excluded castling from splits. Asked, the
user wanted the opposite of a re-exclusion — castling should be reachable by splitting, with the
rook making one ordinary non-superposed move alongside whichever branch lands there. A second real
bug was caught while building it (classify *before* setting `has_moved`).

**Ghost-pawn promotion tightened** — a quiet push onto the promotion rank used to promote a mere
*ghost* pawn unconditionally (per the original PLAN.md spec). The user asked for that ghost to be
measured on the spot instead: really there ⇒ promote; not there ⇒ "his problem".

**In-game Settings** — the pre-game `Menu` reused mid-match (user asked to change colours/team
name/etc. or start over without quitting), via `Menu(in_game=True, initial_config=...)` and
`handle_click` returning `(action, config)`.

**Check metric v2 — condition on the king's location.** A playtest showed a superposed king
cornered on *every* square it could occupy still reading `7/9`: the flat `1 − ∏(1 − p_i)` treated
the king's presence on different squares as independent Bernoullis. Danger now partitions by
king-ghost square (mutually exclusive, weights sum to 1). The cornered king correctly reads `1`.

**Mass movement dial** (user: "move all ghosts in [a piece's] superposition in one move … resolve
any potential conflicts without the need to collapse all ghosts"). Locked beforehand: it walks each
ghost's full path; it **does** measure the contacted enemy on the winning leg; it **replaces** the
single-ghost move for a superposed piece; and — after the user asked — it **obeys the Full/Partial
collapse-mode dial** in the "dodged onto a safe square" branch. A promoting pawn leg still prompts
for the piece (no auto-queening), also at the user's request.

**Check metric v3 — the enemy's strongest single move.** The readout kept over-counting; the user:
"it should represent the probability that the king will be captured if opponent plays his strongest
move." v2 still compounded *independent* threats within a king square, so two enemy pieces each
half-threatening the same king read 3/4 when the opponent can only play one (best = 1/2). Now:
**max** over every enemy move, walking each slide's path (so one move sweeping several king ghosts
reads as certain), plus a mass-move term when that dial is on, and a `describe()` label so the
readout names the strongest move ("CHECK 2/3 (R a4->e7)").

## 2026-07-12

**Graphics overhaul** (user: "how to make the game more pretty … can you do better resolution? it
is quite pixelated"). Five pillars: supersampling (2× + smooth-scale to a resizable/fullscreen
window, `ui/present.py`); selectable **piece sets** (real cburnett/merida SVGs, a runtime neon set,
the original unicode — `ui/pieces.py`); anti-aliased/scaled shapes; crisper text; effects (drop
shadows, neon glow, cyberpunk vignette). Scaling the skins' absolute-pixel panels via `theme.px()`
was the bulk of the work.

A follow-up pass the same day made piece sets **per-team**, and fixed two present-layer bugs from
the first cut: the **hover highlight** now translates through `present.to_logical` (it was
hit-testing physical pixels against the 2× logical board), and **F11** goes through
`present.toggle_fullscreen` instead of the flaky `pygame.display.toggle_fullscreen()`.

**Online play speced** (`ONLINE_PLAY.md`) — design only, nothing implemented.

## 2026-07-13

**Mass split dial** (user: "if mass move is on, I would like a toggle to turn on/off mass split too
— when on, I can split multiple ghosts, each ghost has an option to move or split"). The strict
generalization of mass movement: a mass-split turn with no actual splits resolves byte-for-byte
like a mass move. `resolve_mass_move`'s internals were refactored into a shared
`_resolve_mass_entries` core.

**Menu polish**, two requests together: dial toggles are **hidden when unavailable** (user: "when
some option is not available, it should be hidden (like mass split without mass move)"), and the
game **remembers the last settings** across launches (user: "make the game remember last settings
and load them when app starts") via `saves/last_settings.json`, written on every Start/New-Game/
Resume and read when a fresh menu opens.

**Planning-entry bug** ("I turn on split, move one ghost and the turn ends, I didn't get a chance to
split the second ghost"): entering planning required `mode == "move"`, so a player who toggled to
Split *first* — a natural thing to try when you want to split multiple ghosts — fell through to an
ordinary one-ghost split, which per "a turn = one action on one ghost" ends the turn immediately.
Fixed by dropping the mode check: selecting a superposed piece always opens planning.

## 2026-07-14

**The flip side of that fix** ("I'm in move mode, but after queen ghost h6→h4 I wanted to move the
other queen ghost (f6) and it made the first ghost split instead"): inside planning the two-pick
split gesture was armed purely by the `mass_split` **dial**, ignoring the Move/Split **mode**, so
the click that aimed a ghost never committed — it sat waiting for a second branch, and the next
click (on the other ghost, if that square happened to be a legal target of the first — which is why
it looked side-dependent; it's geometry, not colour) was swallowed as branch B. Fixed by making the
toggle govern the gesture *inside* a plan exactly as it does outside one.

**Tiger piece set** — the user dropped `assets/tiger_set.png` (a sheet of tiger-themed figures) and
asked for SVGs of them as a new set. The sheet is a raster, so the SVGs are **vector-traced** by
`tools/trace_tiger.py` (build-time only, committed so the art is regenerable). One silhouette per
piece (no light/dark pair) ⇒ a **team-tinted** set like neon, with a contrast rim so a pale team
colour still reads on a light square.

**Piece-set picker → dropdown, moved under Teams next to colours** — the growing `PIECE_SETS` list
(now 5, more planned) had outgrown the old fixed 5-button row per team, and the user asked for it to
become a dropdown, relocated next to the team-colour swatches. Each team's picker collapsed into one
`_draw_piece_dropdown` button (preview icon + current set name + caret); opening it lays the full
`pieces.PIECE_SETS` list out as `_piece_option_rects`, a same-width column directly beneath. The open
list is modal in `handle_click` — checked before anything else, any click either selects an option or
just closes it, so it can't fall through to whatever it's drawn over. Freed vertical space let Team
names/colours move up in the menu layout.
