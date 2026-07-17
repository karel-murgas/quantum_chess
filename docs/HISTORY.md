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

Test count: **235 passing** (2026-07-17).

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

**UI redesign** — explored 3 alternate visual languages live-switchable in a
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
*ghost* pawn unconditionally (per the original spec). The user asked for that ghost to be
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

**Cthulhu piece set** — same request pattern as tiger: the user dropped `assets/cthulhu_set.png` (a
sheet of Lovecraftian figures, green row + light-blue row) and asked for an SVG set. Traced by the new
`tools/trace_cthulhu.py`, a trimmed copy of `trace_tiger.py` — this sheet has no separate
tiny-pawn row to rescale from, so that step drops out entirely. Team-tinted like tiger, same contrast
rim in `render_token`.

**"Split stay" dial** — a "stay + move" split (one branch left on the source square, the other
moved) was always allowed; the user asked for it to become a match-setup toggle instead of a fixed
behavior. Added `GameConfig.split_stay_enabled` (default on, so existing behavior/saves are
unchanged) and gated it purely in the UI per the usual rule: `rules.legal_split_targets` still
always includes the source square, and `App._legal_by_square`/`plan_legal` withhold it as a pickable
destination when the dial is off — for both an ordinary one-ghost split and a split leg inside a
mass-split plan. Deliberately does **not** touch plain moves or a mass-move leg that isn't
splitting — holding a ghost in place there isn't "splitting" and was never in scope for this dial.

**"All ghosts must act" dial** — a follow-up to split stay: the user pointed out a mass-move/
mass-split turn can leave some ghosts sitting untouched at their default "stay" assignment, and
asked for an option requiring every ghost to move or split instead. Clarified via
`AskUserQuestion` that Confirm should simply be *blocked* while any ghost hasn't acted (plan stays
open) and that the dial should nest under Mass moves (meaningless without it), like Mass split.
Added `GameConfig.mass_all_must_act` (default off); `App._plan_fully_acted` checks every leg and
`_confirm_plan` no-ops while it's violated (covers both the mouse Confirm button and the `Enter`
shortcut, since both call it); the skin dims Confirm (`render.draw_mass_controls`'s new
`confirm_enabled`) and swaps the status hint to explain why. Composes cleanly with split stay: a
split that leaves one branch on the source still counts as "acted" — only a bare single-destination
"stay" leg fails the check.

**Settings menu — dial tree + mouseover tooltips.** Same request: make the toggle row "visually
nice, not just random buttons," with connecting lines showing how dials unfold, plus hover infotext.
The flat row became a small dependency tree (`_DIAL_PARENT`, `_dial_rows`/`_dial_rects` in
`menu.py`): each level's siblings are centered under their *own* parent's position rather than the
whole screen, so e.g. Mass split/All must act visibly branch out from Mass moves specifically.
`_draw_dial_tree` draws elbowed parent→child connectors before the buttons. Every section below the
tree now reserves fixed vertical space for its tallest possible shape (3 levels) so the rest of the
menu never jumps as dials are toggled. `_draw_hover_tooltips` maps the cursor via
`present.to_logical(pygame.mouse.get_pos())` and shows a word-wrapped info box for whichever
collapse-mode button or dial the mouse is over, copy pulled from flat `_DIAL_TOOLTIPS`/
`_COLLAPSE_TOOLTIPS` dicts. Verified visually via headless PNG screenshots (`pygame.image.save` on
the menu's offscreen surface under `SDL_VIDEODRIVER=dummy`) rather than a real display.

**Piece info popover (right-click pin).** With reskinned sets (tiger, cthulhu) in play, a token's
art no longer obviously maps to a standard piece name — the user asked for on-board infotext,
"intuitive, decent, not cluttering," and to think through the UX before coding. First cut shipped
two tiers (a dwell-triggered hover tooltip alongside a right-click pin), but the user asked to drop
the hover tier and keep only the pin, plus have the pin visually ring the rest of a superposed
piece's ghosts, not just list them in the card. Landed on: `App.handle_right_click` (wired in
`run()` for `MOUSEBUTTONDOWN` button 3) toggles `self.pinned_square`; `BaseSkin.draw_pinned_highlight`
rings every ghost of the pinned piece in its aura colour (`render.draw_plan_rings`'s own idiom for a
piece being planned), drawn under the tokens in the ordinary board phase; `draw_pinned_inspector`
then renders the fuller card — identity plus every ghost's square/probability as a bar (reusing
`_hbar`, the same primitive Clarity's selected-piece inspector uses) — drawn last, on top of
everything except the promotion picker. Works on **either side's** pieces at any time, unlike
Clarity's inspector (which only ever shows your own selected piece), since right-click never
touches selection/move state. Also asked, before building it, whether dismissing the pin on mouse
movement would be more or less convenient: recommended against it — that's the hover-tooltip
convention (dismiss on mouse-leave), while click-triggered popovers everywhere (GitHub hovercards,
Figma comments, any dropdown) dismiss via click-away/Escape/toggle instead, and tying it to mouse
movement would undo the whole point of switching from hover to click (the card would vanish while
the mouse crosses the board toward the next move). Kept the existing dismissal set: any left click,
Escape, new game, or load — a transient "let me peek," never persisted state.

## 2026-07-17

**Dragon piece set.** Same request pattern as tiger/cthulhu, but from **two** sheets: the
user supplied two dragon-themed icon sheets and asked for a set that mixes them — bishop,
rook and pawn off the first, king, queen and knight off the second (their own pick of the
better figure per piece). `tools/trace_dragon.py` generalizes `trace_tiger.py`/
`trace_cthulhu.py` to read six boxes from each sheet's white-figure row, take the three
pieces it needs from each, and lay all six onto one shared canvas sized off the largest
figure across *both* sheets, so a sheet-A piece and a sheet-B piece land at the same
relative scale. Team-tinted like tiger/cthulhu, same contrast rim in `render_token`.

**Collapse mode nested under Splitting.** User feedback on the settings menu: Collapse
mode (Full/Partial) was drawn as its own standalone section above the dial-dependency
tree, when a piece can only ever end up superposed via a split in the first place — so
the choice is meaningless with Splitting off. Folded it into the same tree as a child of
`split` (`_DIAL_PARENT["collapse"] = "split"`), alongside split stay/mass moves: hidden
entirely (not dimmed) when Splitting is off, shown with a connector line otherwise. Changed
from a two-button Full/Partial picker to a single toggle button (`"Collapse: Full/Partial"`,
click to flip) to match every other dial's look; reclaimed the vertical space the old
standalone section used so nothing below shifted.

**Team-swap/colour-picker bug + Origin colour lock.** User report: "switching the team
doesn't correctly switch colors, and then the color picker stops working." The swap
button and swatch clicks were mutating `self.white_color`/`black_color` correctly all
along — confirmed headless, screenshot diffing before/after each click. The actual bug
was the piece-set dropdown's preview icon: for a tinted set (neon/tiger/cthulhu/dragon)
it recoloured via `theme.team_neon(color)`, a **module global set only by
`apply_theme()`** (i.e. whatever the last *started* game used) — completely disconnected
from the colour the menu is live-editing. A swatch pick or a team swap updated the data
and moved the swatch's own highlight ring, but the one piece of visual feedback a player
actually watches (the icon) never moved, reading as "broken." Fixed by threading an
optional `tint` override through `pieces.render_art`/`render_token`, which the menu now
passes as the live `self.white_color`/`black_color` (Cyberpunk only). Also actioned the
user's related ask — "in origin mode there should only be black and white" — by locking
Origin's `WHITE_NEON`/`BLACK_NEON` to its own token colours instead of deriving them from
`white_color`/`black_color` (which defaulted to gold/blue): Origin has no colour picker,
so a tinted set now always renders plain black-vs-white there, never a stale custom tint.
