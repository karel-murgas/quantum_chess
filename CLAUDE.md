# Quantum Chess — project guide (for Claude)

A hotseat (2 local humans, no timer) chess variant: standard chess plus a
**superposition / collapse** layer. Pieces can *split* into ghosts with
probabilities; contact triggers a random **collapse** that reveals where a piece
really was.

**Read `PLAN.md` first** — it is the living spec (full ruleset, dials, milestones).
`options.md` is the user's original design-dial brainstorm.

## Stack
- Python 3.13, **`python-chess`** (movement oracle only), **`pygame-ce`** (UI), `pytest`.
- Pieces drawn as **Unicode glyphs** (no image assets); alpha = probability.
- Install: `pip install -r requirements.txt`.

## Locked v1 design decisions (don't silently change these)
- **Win = capture the king.** No check / checkmate / stalemate. The king is an
  ordinary, capturable, splittable piece. (The **check-probability overlay**
  added 2026-07-11 — `quantumchess/check.py`, see below — is *purely advisory*
  and does **not** reintroduce a check rule: it never restricts a move, it only
  displays how likely a king is to be capturable next turn.)
- **A piece superposes only with its own ghosts — no cross-piece entanglement, ever.**
- **A turn = one action on one ghost:** move it, or *split* it into two (`p → p/2, p/2`).
- **Collapse modes (match dial)** — behaviour on a *negative* measurement ("not here"):
  - *Partial*: only the contacted ghost vanishes; the rest renormalize.
  - *Full*: resolve the whole piece to one location; drop the others.
  (A *positive* measurement always collapses the piece to solid, both modes.)
- **Path collapse:** a mover measures every ghost it passes. Real ⇒ movement stops
  there (capture if enemy); not-there ⇒ it continues. One move can collapse a chain
  and stop short of its target.
- **No split cap** — probabilities may shrink to 1/2ⁿ; collapses thin them out.
- **Castling** (added 2026-07-11, see `rules.py`/`collapse.py` below): only for a
  king/rook that has *never* moved or split (tracked via `Piece.has_moved`),
  which means it's guaranteed solid on its home square. No check concept
  exists in this variant, so there's no "can't castle through/into check"
  restriction — only occupancy matters. A king may also *split* one branch
  toward the castle square (added 2026-07-11, per user request) — the rook is
  never superposed by this: it always makes one plain, deterministic
  relocation alongside whichever branch reaches the castle square, exactly
  mirroring a full-move castle's "rook follows only if the walk completes."
- Deferred dials (documented, not yet built): all-ghosts move/split (symmetric or
  independent), equal-`1/n` probabilities, exotic promotion/en-passant
  interactions.

## Architecture
- **Engine is headless** — `quantumchess/` must not import `pygame`. UI is a thin
  layer so the quantum logic stays unit-testable (and a web frontend stays possible).
- `model.py` — `Piece`, `Ghost`, `QuantumBoard` (probabilities are exact `Fraction`s).
  `to_classical_board()` projects a *solid* position onto a python-chess board and is
  used both for ASCII rendering and as the movement oracle. `Piece.has_moved`
  (added 2026-07-11 for castling, see `rules.py` below) is set the instant a
  piece is moved *or* split, ever — even if it later re-merges back onto its
  home square, it stays permanently disqualified from castling.
- `rules.py` — `Move`/`MoveKind`/`Split`, `generate_moves` (pseudo-legal via
  `Board.attacks` over solids, so it extends to quantum blockers), `apply_move`,
  `apply_split`, `legal_split_targets`, `split_destination_kind`, `remove_piece`.
  Occupancy invariant: **≤1 ghost per square** (same-piece ghosts merge; a
  different piece's ghost is a `CONTACT` = needs collapse). `CONTACT` moves are
  generated only on request (`include_contact=True`) and `apply_move` raises
  `NotImplementedError` on them — resolution lives in `collapse.py`.
  `legal_split_targets` includes squares that would capture/contact an enemy
  (splitting into an enemy-occupied square is legal — see `resolve_split`
  below); `apply_split` itself stays the measurement-free fast path and raises
  if either destination needs a collapse.
  **Castling** (added 2026-07-11, user asked "should I be able to castle here?"
  after a playtest reached a position where it should be legal): `Move` gained
  `castle_rook: Optional[tuple[rook_piece_id, rook_from, rook_to]]`, set only on
  the king's own move. `_castle_moves` offers it when the king and that side's
  rook both have `has_moved == False` (which — since nothing ever touched them —
  guarantees both are still solid on their home squares, no separate "is it
  solid" check needed). The king's 2-square hop is classified with the exact
  same `_classify`/`_path_has_foreign_ghost` helpers used for any other slide,
  so it comes out as `RELOCATE` (clear path), `CAPTURE_SOLID` (a solid enemy
  sitting on the final square — castling-into-a-capture is allowed, unlike real
  chess, to stay consistent with "a king slide is a king slide"), or `CONTACT`
  (a ghost, friendly or foreign, anywhere on the path) — resolution of the
  first two happens right here in `apply_move`; `CONTACT` defers to
  `collapse.resolve_move` like any other sliding contact. The one square that
  belongs to the rook alone (b-file, queenside) is never on the king's path, so
  it isn't resolved by any walk — it's required to be completely empty (no
  ghost at all) as a precondition for offering queenside castling, a
  deliberate simplification (no "rook-side collapse" mechanic was designed).
  `apply_move`/`collapse.resolve_move` both relocate the rook **only if the
  king's move/walk actually reaches the full castle destination** — a king that
  stops short (captures a path ghost, or gets blocked short by a confirmed
  friendly one) leaves the rook untouched, mirroring "path collapse can stop a
  move short of its target."
  **Split-based castling** (added 2026-07-11, user asked for it explicitly
  after a UI crash — splitting a king toward the castle square used to be
  excluded from `legal_split_targets`/`split_destination_kind` via
  `include_castle=False`, but the UI's split-mode highlight dict still offered
  the square by mistake, so picking it raised `ValueError` in
  `resolve_split`). Rather than re-excluding it, castling was extended to
  splits: both functions now call `ghost_destinations` with the default
  `include_castle=True`, so a castle destination is a normal split target
  reported as whatever `MoveKind` it actually is (`RELOCATE`/`CAPTURE_SOLID`/
  `CONTACT`). A new `split_destination_castle_rook(qb, square, to_square) ->
  Optional[tuple[rook_id, rook_from, rook_to]]` (same `ghost_destinations`
  lookup, just returning `.castle_rook` instead of `.kind`) is how
  `apply_split`/`collapse.resolve_split` find out a branch is a castling one.
  **The rook itself is never superposed/split** — it always makes one plain,
  deterministic relocation: for a clear-path (`RELOCATE`) branch there's
  nothing to measure, so `apply_split` moves it unconditionally the instant
  the branch is placed; for a `CAPTURE_SOLID`/`CONTACT` branch (enemy on the
  destination or path), `collapse.resolve_split`/`_resolve_split_branch` move
  it only once *that specific branch* is confirmed to have actually reached
  the castle square — capture branches always complete once confirmed present
  (no foreign ghosts on the path by construction), contact branches only if
  `_walk_contact`'s `stop_square` equals the full destination — the exact same
  "rook follows only if the king's own walk completes" rule `resolve_move`
  already used, just applied per-branch instead of per-move. Both `apply_split`
  and `resolve_split` classify the destinations (and look up `castle_rook`)
  **before** marking the piece's `has_moved = True` — marking it first (the
  original order) made the king look already-moved to that same classification
  call, which silently turned every castle branch into "not a castle" (a
  second real bug caught while building this, before it shipped). UI:
  `app.py::_handle_split_click` snapshots the rook's pre-split `Token`,
  executes the split, then checks (same pattern as `_execute_move`) whether
  the rook actually landed on `rook_to` before adding it to the slide
  animation and logging a `castle_verb` line alongside the split's own log
  line. 124 tests passing (`tests/test_castling.py` covers the clear-path,
  solid-capture, and both collapse-branch cases; `_legal_by_square` no longer
  needs a split-mode-only `include_castle` override).
- `textview.py` — headless ASCII board (`*B*` = ghost) + exact-fraction legend.
- `config.py` — `GameConfig` (dials), `CollapseMode`. Split out from `game.py` so
  `collapse.py` can import it without a circular dependency; re-exported from
  `game.py` for convenience. Also carries the cosmetic (non-logic) match-setup
  fields: `theme` ("origin"/"cyberpunk"), `white_name`/`black_name`,
  `white_color`/`black_color` (RGB tuples, only meaningful for cyberpunk), plus
  `team_name(color)`/`team_color(color)` helpers keyed off the python-chess
  colour bool. Kept here (not in `ui/`) so `persistence.py` can round-trip them
  without importing pygame, and so the engine-level `GameConfig` stays the
  single source of truth for a match's identity. Added 2026-07-11 alongside the
  cyberpunk theme, per the user's ask to let players pick a team name + colour.
- `collapse.py` — `resolve_move`: the collapse engine. **Measurement only happens
  on collision** — `RELOCATE`/`MERGE` (empty square, or the mover's own ghost)
  skip straight to a plain `apply_move`, no dice involved. Any move that touches
  another piece (`CAPTURE_SOLID` or `CONTACT`) measures the mover first (positive
  ⇒ solid, drop siblings; negative ⇒ fizzle + apply collapse mode) — **this
  applies even when capturing a certain/solid piece**: a superposed mover isn't
  guaranteed to land the capture just because the target is certain (was a real
  bug, fixed 2026-07-10 after the user asked "is movement measured only in case
  of collision?"). For `CONTACT`, after the mover is confirmed, walk the path
  square-by-square measuring every foreign ghost in turn (enemy real ⇒ capture &
  stop there; friendly real ⇒ confirm it solid & stop one square before it;
  not-there ⇒ apply collapse mode, keep walking) — one move can resolve several
  pieces' superpositions in a row. Returns a `MoveResolution` (fizzled?,
  final_square, captured_piece_ids) plus an ordered `CollapseEvent` log for the
  UI animation. Ends the game via king capture same as `apply_move`.
  Each `CollapseEvent` carries not just the measurement (role/piece/square/
  prob_before/present) but its *visual consequence* — `removed` (the
  `(square, prob)` of every ghost that measurement wiped: siblings on a positive
  collapse, the measured ghost + FULL-mode siblings on a negative one, a captured
  piece's other ghosts) and `captured_square` (where an enemy was taken, for a
  shatter effect). Populated by having `_collapse_positive`/`_collapse_negative`
  *return* what they drop; the dataclass is no longer frozen so the resolver can
  fill these in after the mutating helper reports back. This is what lets the UI
  animate a collapse without re-deriving the engine math. Kept fully headless.
  `resolve_split`: splitting into an enemy-occupied square used to be silently
  illegal (`legal_split_targets` excluded `CAPTURE_SOLID`/`CONTACT` outright,
  so the UI just deselected the click) — fixed 2026-07-11 after the user asked
  for one split branch to be able to capture. Both branches settle in the same
  instant the split is made: measurement-free branches (empty/same-piece
  merge) are placed unconditionally first, then each enemy-contacting branch
  is measured exactly like a move's mover (a p/2 branch capturing even a
  certain piece isn't guaranteed) — positive confirms it solid there and wipes
  every other ghost of that piece (siblings included, via `_collapse_positive`,
  reused from `resolve_move`); negative removes just that branch and
  renormalizes the rest via `_collapse_negative`. A `CONTACT`-kind branch
  additionally walks the path via the same `_walk_contact` helper `resolve_move`
  uses (extracted during this fix), so a sliding split-branch can still capture
  or stop short partway there. If splitting into *two* enemy-occupied squares
  at once, the first branch resolved that confirms real skips measuring the
  second entirely (the piece is settled; that square is never touched).
  `resolve_move`'s `CAPTURE_SOLID`/`CONTACT` branches also carry the castling
  rook-follow logic (see `rules.py` above) — for `CONTACT` specifically, the
  rook only relocates if `_walk_contact`'s `stop_square` equals the king's
  full destination, and needs no measurement of its own since `rook_to` is
  always one of the squares the king's own walk already resolved.
- `check.py` — **advisory** check-probability overlay (added 2026-07-11, user
  asked for an interface to "signal check and partial check, like 3/8 to be a
  check" plus a warning before a move exposes their own king). Purely
  informational — no rule impact (see locked decision above). Headless, exact
  `Fraction`s, **no RNG** (it's the *expected* danger, not a rolled outcome).
  Metric = **aggregate danger** (chosen with the user via `AskUserQuestion`):
  every enemy capturing attempt against a king is one *threat* with success
  probability `p_i`, and `check_probability(qb, color) = 1 − ∏(1 − p_i)` (chance
  at least one lands, threats treated as independent — a mild overestimate since
  the enemy really gets one move, but the agreed simple model). A single
  threat's `p` = (attacker ghost `prob`) × ∏(each *other* piece's ghost on the
  path is absent, `1 − prob`) × (king ghost `prob` on the targeted square).
  Threats are enumerated by **reusing `rules.ghost_destinations`** for every
  enemy ghost and keeping the moves whose `to_square` holds a king ghost — so it
  automatically tracks whatever the engine can actually capture (incl. quirks
  like a pawn's forward-push CONTACT capture onto a *superposed* king; solid
  blockers already prune the ray via the oracle board, so only partial ghosts
  enter the absent-product). `move_self_check(qb, move)` answers "does this move
  expose *my* king?": it builds a hypothetical board via `_hypothetical_after`
  (deep-copy, relocate the mover to its destination, drop a solid piece it
  captures outright, drag a castling rook) and re-runs `check_probability` for
  the mover's colour — catching both moving into fire and discovered exposure
  (a blocker leaving a line). It approximates the move as simply completing;
  the random collapse a CONTACT move might itself trigger is not rolled.
- `game.py` — `random_selfplay` (M1, classical-only driver used by M1 tests/demo).
- `persistence.py` — save/load a game to/from JSON. Headless like the rest of
  the engine; `to_dict`/`from_dict` snapshot the board (pieces + ghosts, exact
  `Fraction` probabilities), the `GameConfig` dials, and the RNG's internal
  state (`random.Random.getstate()`/`setstate()`) so a resumed game's future
  collapses draw the same sequence they would have if it had never been
  closed. Deliberately excludes UI-transient state (current click selection,
  in-progress split picker, the collapse-animation reveal queue) — `qb` is
  already fully resolved the instant a move applies, so none of that is needed
  to correctly resume play. `save_game`/`load_game` wrap `to_dict`/`from_dict`
  with file I/O (`save_game` creates parent dirs; `load_game` raises on an
  unrecognized `version` field, checked so old/corrupt saves fail loudly
  rather than silently misloading). Each piece dict also carries `has_moved`
  (added 2026-07-11 for castling); `from_dict` reads it with `.get(..., False)`
  rather than a hard key lookup, same reasoning as the theme fields below — a
  save from before this field existed just loads as "never moved," which is
  never *wrong* for a piece that's still on its home square (the only case
  that matters for castling eligibility) and merely conservative-safe
  otherwise. No `version` bump, same precedent as the theme fields. The
  `config` sub-dict also carries
  `theme`/`white_name`/`black_name`/`white_color`/`black_color`; `from_dict`
  reads these with `.get(..., default)` (not a hard key lookup) so old saves
  written before 2026-07-11 still load — they just fall back to
  origin/"White"/"Black" instead of raising, deliberately not a `version` bump
  since the schema only grew optional fields. Separately, `save_teams`/
  `load_teams` (own `TEAMS_FORMAT_VERSION`, single slot `saves/teams.json`)
  round-trip just the *cosmetic team identity* — theme + both names + both
  colours — independent of any game in progress, so players can reuse a
  favourite team look across matches without retyping it in the menu. Driven
  straight from the menu's own fields (plain kwargs, not a `GameConfig`) so it
  stays pygame-free; colours come back as `(r,g,b)` tuples. Added 2026-07-11
  per the user's ask for a save/load-teams button.
- `ui/` — pygame layer (Milestone 4). **The only place that imports pygame** —
  never import it from the engine modules above.
  - `theme.py` — layout/color constants, the glyph map (`♔♕♖♗♘♙`, tinted per
    side rather than relying on separate black/white codepoints — see font note
    below). Two swappable presets, **origin** (the original wood-board look)
    and **cyberpunk** (neon-on-dark). `apply_theme(name, white_color,
    black_color)` rebuilds the whole palette dict and does `globals().update()`
    — every other UI module reads palette values as `theme.X` (attribute
    lookup, never `from theme import X`), so one call after the menu closes
    (or after `App.load_from`, in case a save carries a different theme) repaints
    everything with no plumbing through render.py/app.py/menu.py. Cyberpunk's
    palette is generated, not hardcoded per colour: `_cyberpunk_palette` mixes
    each player's chosen `white_color`/`black_color` with fixed dark/light grays
    (`_mix`/`_clamp`) to build the board squares (blend of both teams' hues into
    the grid), each side's token fill/border, and an ink colour picked for
    contrast (`_ink_for`, luminance-based) — so an arbitrarily-picked neon still
    reads against its token. `TERMS` is a second per-theme dict, swapped the
    same way, that reskins the *narration* players see in the side log —
    "captures" → "deletes", a fizzled move's clause, "vanished" branches, the
    win line, and the collapse status line's "IS"/"is NOT" → "ONLINE"/"OFFLINE"
    — added because a reused colour palette alone didn't feel "cyberpunk enough"
    once the boards were side by side. `castle_verb` ("castles"/"reroutes",
    added 2026-07-11) follows the same pattern for the new castling log line.
    `check_word`/`safe_word` ("CHECK"/"safe" vs "LOCKED ON"/"clear", added
    2026-07-11) reskin the advisory check-probability readout the same way.
    `TERMS` also carries the on-board
    collapse-caption words (`reveal_present`/`reveal_absent`/`reveal_capture` —
    "REAL!"/"EMPTY"/"CAPTURED!" vs "ONLINE"/"OFFLINE"/"DELETED!"). `SWATCHES` is
    the curated 8-colour list the menu's colour pickers offer (free-text hex was
    considered and skipped as unnecessary polish for a 2-player hotseat game).
    `EVENT_PRESENT_COLOR`/`EVENT_ABSENT_COLOR` are the green/red collapse-flash
    hues (per theme). `LOG_KEYWORD_COLORS` (added 2026-07-11, user asked for
    the side-log's narration keywords to be colorized) maps each `TERMS` key
    (`capture_verb`, `split_verb`, `castle_verb`, `win_suffix`,
    `fizzle_clause`, `vanished_word`, ...) to a colour already in the
    palette — captures/deletes reuse `EVENT_ABSENT_COLOR` (the same red as a
    negative collapse flash), a split/fork reuses `SPLIT_PICK_RING`, a win
    reuses `SELECTED_RING` (same gold as the win banner), and `vanished_word`
    ("vanished"/"glitched out") reuses `LEGAL_CONTACT_DOT` (the risky-contact
    orange, not a dim tone — user asked for it to stand out too, since a
    split branch that didn't survive is worth noticing) — via a shared
    `_keyword_colors(palette)` helper both `_origin_palette`/
    `_cyberpunk_palette` call, so a new keyword only needs one new mapping,
    not per-theme duplication. `WHITE_LABEL`/`BLACK_LABEL` + the
    `theme.team_label(color)` helper (added 2026-07-11, user asked for team
    names to render in their team colour) give each side's *name text* a
    per-theme colour: origin uses a warm cream / lightened wood-brown pair
    (legible on the dark panel, since the raw black token is unreadable there);
    cyberpunk uses each side's own vivid neon accent (`white_color`/
    `black_color`). Applied by render.py to the turn title, the removed-pieces
    tray headers, the win banner, and inline in the side-log (team names are
    fed to `draw_log_line` as extra colour spans alongside the `TERMS`
    keywords).
  - `animation.py` — **pygame-free** collapse-animation *model* (like the
    engine). `Token`/`Beat` dataclasses + `build_animation(before, movers,
    events)`, which turns a resolved move/split into a beat script: one TRAVEL
    beat (the mover, or both split branches, slides out from the source) then one
    FLASH beat per `CollapseEvent`. It reconstructs each beat's static `rest`
    layer from the *pre-resolve* snapshot plus the movers, evolving it event by
    event — that's what keeps a split branch that will vanish visible until its
    own flash fades it (the engine already dropped it instantly). Fades come
    from `CollapseEvent.removed`, shatters from `captured_square`; a confirmed
    mover goes solid in `rest` on its own flash. Durations vary by slide
    distance / whether the beat also removes something ("variable by
    complexity"). Unit-tested headlessly in `tests/test_animation.py`.
  - `render.py` — pure drawing functions (board, ghost tokens with alpha ∝
    probability + fraction label, same-piece aura outlines, legal-destination
    dots colour-coded safe/merge/**risky-contact**, side panel, promotion
    picker). Nothing here mutates state. `draw_token` is the shared token
    renderer (used by both the live board and the animation); `draw_beat(surface,
    beat, t, fonts)` draws one animation beat at progress `t` — rest tokens,
    sliding travel tokens (smoothstep-eased), fading `removed` ghosts, a capture
    `shatter` (fading token + expanding ring), the green/red square flash, and a
    floating caption chip. `draw_log_line(surface, text, pos, font,
    default_color, name_colors=None)` (added 2026-07-11, alongside
    `LOG_KEYWORD_COLORS` above) renders one side-log line with its theme
    keywords in colour: helper `_log_keyword_spans(text, extra_specs=())`
    searches `text` for every `theme.TERMS` value *plus* any `extra_specs`
    `(text, color)` pairs (longest first, so a multi-word phrase like
    `win_suffix` isn't shadowed by a shorter keyword sitting inside it, nor a
    team name by a keyword inside it), keeps only non-overlapping matches, and
    `draw_log_line` blits the line as alternating default-colour/keyword-colour
    segments instead of one `font.render` call. `draw_side_panel` passes the
    two team names as `name_colors` (`{name: theme.team_label(color)}`) so a
    name reads in its team colour inline in the log too (see `theme.py`'s
    `WHITE_LABEL`/`BLACK_LABEL` above). `draw_side_panel`'s log
    loop (was a single `fonts["small"].render(line, ...)` per wrapped line)
    calls this instead. A keyword split across a word-wrap boundary just
    doesn't get coloured on that render — the panel is wide enough that this
    hasn't come up in practice, not worth solving. **Check overlay** (added
    2026-07-11): `draw_side_panel` takes `show_check`/`check_lines` and draws a
    "Check warnings: ON/OFF (K)" toggle (`panel_rects()["check"]`) plus, above
    the config line, one `(text, color)` readout line per king (danger-red when
    threatened, dim when safe). `draw_highlights` takes an optional
    `check_by_square`/`fonts`: for each destination in it, `_draw_danger_marker`
    overlays a red warning ring + a `frac_str` chip (the mover's own resulting
    check probability) on top of the normal legal-move dot.
  - `app.py` — `App`: click-driven interaction (select → move or split → collapse
    animation), promotion picker, side log. Both players see the *entire* board
    including all ghosts/probabilities at all times (hotseat, no hidden
    information) — only the collapse dice roll is unknown until resolved.
    Collapse animation: right before resolving, `_execute_move`/`_handle_split_click`
    snapshot the board (`_snapshot_tokens`) and, after, build a beat script via
    `animation.build_animation` (`self._beats`, current = `[0]`). `update(dt)`
    advances `_beat_elapsed` and drains finished beats (a single long frame can
    drain several short beats); `draw` renders the current beat via
    `render.draw_beat` *instead of* the live pieces while `is_animating()`, then
    hands back to the normal board once `_beats` empties (`qb` is already the
    final state throughout). Any click / the New Game / Escape paths flush via
    `_flush_animation` (skip to end) — a winning move's animation still can't be
    skipped past into New Game. **Quiet relocate/merge moves (zero events)
    resolve instantly (no beats), so ordinary play stays snappy; only a move that
    actually measured something — and *every* split (both branches always slide
    out) — animates.** A completed castle is a third exception to the "quiet
    moves are instant" rule (added 2026-07-11): `_execute_move` snapshots the
    rook's pre-move `Token` too and, if `move.castle_rook` completed (checked
    by whether the rook ghost actually landed on `rook_to`, not just
    `has_moved`, to stay independent of the flag's exact semantics), passes
    *both* the king's and rook's `(dest_token, from_square)` pairs into
    `build_animation` — same mechanism `_handle_split_click` already uses for
    a split's two branches — so both pieces always slide even when the path
    was completely clear and there's nothing to flash. The side-log line for a
    completed castle uses the new `theme.TERMS['castle_verb']`
    ("castles"/"reroutes") and names the rook's own move too.
    `App.save_to`/`App.load_from` wrap `persistence.save_game`/`load_game`
    against a single quicksave slot (`DEFAULT_SAVE_PATH = saves/quicksave.json`);
    wired to both panel buttons (`self.skin.panel_rects()["save"/"load"]` —
    see `skins/` below) and `F5`/`F9`. `load_from` catches
    `OSError`/`ValueError`/`KeyError` (missing file, unknown version,
    malformed JSON) and logs a message instead of crashing the app.
    `App._piece_label` and every side-log line read team names/verbs off
    `self.config.team_name(color)` / `theme.TERMS[...]` rather than
    hardcoding "White"/"Black"/"captures" — see `theme.py` above.
    **Check overlay wiring** (added 2026-07-11): `show_check` (default on,
    toggled by the panel button / `K`). `_check_readout()` builds the two
    per-king readout lines from `check.check_probability`; `_selfcheck_by_square()`
    returns `{to_square -> Fraction}` for the current *move-mode* selection's
    destinations that would *raise* the mover's own king danger above its
    current baseline (via `check.move_self_check`) — the feature-2 warning set.
    Both are cached and keyed on a `self._ply` counter bumped on every board
    change (move/split resolve, new_game, load_from), so the per-destination
    board deep-copies and the readout aren't recomputed each frame. Split mode
    shows the readout but no per-branch warnings (a split leaves half the mass
    on the source, so it barely opens a line — deliberately out of scope).
    **Skin switching** (added 2026-07-11, see `skins/` below): `self.skins`
    (all registered skins), `self.skin_index`, `self.skin` (the active one)
    are built in `__init__` — there is no more "no skin" classic render
    path; `draw()` is just `self.skin.draw(self)`. `App.cycle_skin()`
    advances to the next skin; wired to the **Tab** key and to a `"view"`
    key in `handle_mouse_down`'s rect dict, hit-tested like
    save/load/captured/check (reachable any time, not gated on whose turn it
    is or game-over). A display preference, like `show_captured`/
    `show_check` — untouched by `new_game`/`load_from`.
  - `skins/` — one drawing language per view (board + panel), see
    `UI_REDESIGN.md` for the full design history. Started 2026-07-11 as a
    3-variant live-switching demo (`demo_ui.py`, a separate script) to
    playtest looks side by side; after playtesting, **Quantum HUD**
    (`hud.py`) and **Clarity / Data-viz** (`clarity.py`) were kept as the
    two views a player can switch between *during a real match* (see
    `App`'s skin switching above), **Polished Evolution** was dropped, and
    the demo script was deleted — the redesigned UI *is* the main game now;
    `python main.py` runs it directly. `base.py`'s `BaseSkin` still supplies
    the shared contract (hit-testing/geometry, fonts, `_check_values`
    cache, `_hbar`/`_caps_label`/`_round_card` helpers) both skins build on;
    each skin owns its own `panel_rects()` (so drawn and clickable
    positions stay in lock-step — `App.handle_mouse_down` always hit-tests
    against `self.skin.panel_rects()`) and a from-scratch `draw_panel`.
    Clarity's turn header (added 2026-07-11) borrows the *structure* of
    HUD's "ACTIVE UNIT" module — a framed block naming whose turn it is
    plus a live mode readout, judged nicer in playtesting than Polished's
    header — but reskinned flat/hairline-bordered/no-glow to match
    Clarity's own data-panel language instead of HUD's console brackets.
    Both skins also gained a `"view"` control (a `CLARITY`/`HUD` segmented
    switch in Clarity, a `[TAB] VIEW` row in HUD) and a `"quit"` button
    (confirm-then-fire, ported from the retired classic path so removing it
    didn't silently drop the feature) in the same pass.
  - `menu.py` — pre-game dial picker (collapse mode, splitting on/off, seed,
    board theme, team names, team colours). `splitting_enabled` is enforced at
    this UI layer (`App.toggle_mode`), not inside the engine — the engine's
    split functions are dial-agnostic by design. Team-name fields are simple
    click-to-focus text inputs (`Menu.active_field` + `handle_keydown`, wired
    from `main.py`'s menu loop since the mouse-only loop never forwarded
    `KEYDOWN` before); team-colour pickers are `theme.SWATCHES` swatches,
    shown only once "Cyberpunk" is the selected theme (origin doesn't use
    custom colours). Both team-colour swatch rows and the theme toggle read
    back into the `GameConfig` the Start button returns. A "Save Teams" /
    "Load Teams" button pair (flanking "Reroll seed" on one row) persists the
    current team setup (theme + names + colours) via `persistence.save_teams`/
    `load_teams`; Load writes the saved values straight back into the menu
    fields and a transient `team_status` line reports the result. `Menu.__init__`
    also calls `_load_teams(startup=True)` right after setting the hardcoded
    defaults, so a fresh menu opens pre-filled with whatever team setup was
    last saved instead of always resetting to origin/White/Black — a missing
    or corrupt save is silently ignored at startup (falls back to the
    hardcoded defaults) since `team_status` has nothing worth reporting yet,
    whereas an explicit Load click still surfaces "No saved teams to load."
    Added 2026-07-11 per the user's ask to default menu settings from the last
    team save. A "⇄" swap button (`Menu.swap_rect`, between the two name
    fields) trades the white/black name+colour assignments in one click
    (`Menu._swap_teams`) — since white always moves first, this is how
    players pick who starts without retyping both names. Added 2026-07-11
    per the user's ask for a way to switch who starts.
  - Collapse animation plays on the board (see `animation.py`/`render.draw_beat`
    above): movement slides out first, then each measurement flashes green/red
    with fading ghosts, capture shatters and a floating caption. Per-beat
    durations are set in `animation.py` (travel scales with distance; a flash
    that also removes something gets extra time). Any click mid-animation
    flushes the rest instantly (skip).
- `main.py` (repo root) — entry point: `python main.py` (menu → game). Calls
  `theme.apply_theme(config.theme, config.white_color, config.black_color)`
  once the menu's Start button returns a `GameConfig`, before constructing
  `App` — this is the one call site that actually activates a chosen theme.
- `tests/` — plain pytest against the headless engine, plus `test_m4_ui.py`
  which drives `App` headlessly via `SDL_VIDEODRIVER=dummy` and simulated clicks
  (`handle_mouse_down` with pixel coords from `render.square_rect(...).center`)
  — real interaction-logic coverage, not just visual inspection. `test_persistence.py`
  covers `persistence.py` directly (no pygame needed): dict round-trip, disk
  round-trip (`tmp_path`), rejecting an unrecognized save-format version, and
  that a resumed RNG continues the *same* future random sequence it would have
  pre-save (the whole point of persisting `rng.getstate()`). `test_animation.py`
  covers the collapse-animation beat builder headlessly (no pygame): travel
  beat + one flash per event, vanished branches routed to fades, captures to a
  shatter, confirmed movers going solid. `test_check.py` covers the advisory
  check-probability overlay headlessly: full check from a solid attacker,
  superposed-attacker scaling, aggregate `1−∏(1−p)` over two threats,
  superposed-king exposure, a partial blocker thinning a threat, and
  `move_self_check` for both discovered exposure and moving into/out of fire.

## Run / test
- **Play the game**: `python main.py` (needs a real display — pick dials in the menu, then click to play)
- Demo (M1 random game): `python demo_m1.py [seed]`
- Demo (M2 superposition): `python demo_m2.py`
- Demo (M3 collapse): `python demo_m3.py [seed]` — try seeds 1-5, each gives a different outcome
- Tests: `python -m pytest -q`  (119 passing). UI tests need `SDL_VIDEODRIVER=dummy` in
  the environment (set automatically at the top of `test_m4_ui.py`, but harmless to
  also export it yourself: `SDL_VIDEODRIVER=dummy python -m pytest -q`).
- `HOW_TO_PLAY.md` (repo root) — player-facing rules/controls guide for the user and their friend.

## Milestone status
- [x] **M1** — headless board model + classical movement (capture-the-king), ASCII
      demo, tests. All green.
- [x] **M2** — superposition: split, merge, ghost/probability bookkeeping (exact
      `Fraction`s), ghost-aware move generation, ASCII ghost view. Contact with a
      foreign ghost is detected and deferred to M3. All green.
- [x] **M3** — collapse: contact + path collapse (multiple pieces can collapse in
      one move), both modes (partial/full), seedable RNG (`random.Random` passed
      in explicitly — trivially mockable in tests), win-by-king-capture through
      collapse. Deterministic mechanism tests (via a `ScriptedRng` test double)
      plus a statistical test (3000 trials, 50% ghost captures ~50% of the time).
      All green.
- [x] **M4** — pygame UI: board, ghost tokens (alpha ∝ probability, fraction
      labels, same-piece aura outlines), click-to-select with legal-destination
      highlighting (safe/merge/risky-contact colour-coded), split mode
      (two-click destination picker), promotion picker, side log, on-board
      collapse animation (movement-then-reveal: slide → green/red flash → fading
      ghosts → capture shatter → floating caption; click-to-skip), game-over
      banner, pre-game dial menu. Verified via headless PNG screenshots (visual)
      and `test_m4_ui.py` (functional, simulated clicks under `SDL_VIDEODRIVER=dummy`).
      All green. User did a first interactive playtest 2026-07-11 ("looks like
      it works"); a follow-up self-review pass then found and fixed three real
      UX gaps: Escape used to quit the whole app instead of cancelling the
      current selection (`App.cancel_selection`), there was no way to start a
      new game after a win (`App.new_game`, "New Game (N)" button), and the
      Move/Split toggle was keyboard-only (now also a clickable panel button,
      `render.panel_rects()["mode"]`). Also fixed: a winning move's own collapse
      animation could be skipped past via the New Game button — animation now
      always takes priority over both New Game and Escape. A second playtest
      2026-07-11 turned up a display-only bug: the side-log always printed
      `(1/2), (1/2)` for a split, even when splitting an already-partial ghost
      (should show 1/4 for a ghost that was already at 1/2). The engine math in
      `rules.py::apply_split` was correct throughout (`half = source.prob / 2`);
      the log line in `app.py::_handle_split_click` just hardcoded the string
      instead of reading the resulting `Ghost.prob` back off the board. Fixed
      by reading the actual post-split probabilities via the new public
      `render.frac_str()` (renamed from `_frac_str`). Transcript saved at
      `games/2026-07-11_split-fraction-log-bug.md`. That same playtest also
      surfaced a real interaction bug: `App.mode` ("move"/"split") was never
      reset after a turn completed, so once either player used split mode it
      silently stayed in split mode for the *other* player's next turn too —
      clicking an opponent's piece to capture then read as "pick an illegal
      split target," which fails closed by clearing the whole selection
      (looks like the click just did nothing / "reverted"). Fixed by resetting
      `self.mode = "move"` at the end of `_execute_move` and
      `_handle_split_click` in `app.py`, so every new turn starts in move mode
      by default and split must be re-chosen each time it's wanted. That same
      day, added a save/load mechanism (`quantumchess/persistence.py` +
      `App.save_to`/`App.load_from`, "Save (F5)"/"Load (F9)" panel buttons) —
      motivated by wanting to resume that same game after the app was closed
      before it could be reconstructed by hand. Single quicksave slot at
      `saves/quicksave.json`; round-trips board state (exact `Fraction`
      probabilities), config dials, and RNG state so a resumed game's future
      collapses are exactly as random as an uninterrupted one. 65 tests passing.
      Later the same day, added a second board theme, **cyberpunk** (neon-on-dark),
      alongside the original look (now called **origin**) — user-requested, with
      per-match team customization: players pick a team name and an accent
      colour each in the pre-game menu (`ui/menu.py`), and the cyberpunk palette
      is generated from those two colours blended with grays rather than being
      a second hardcoded palette (`ui/theme.py::_cyberpunk_palette`). Team names
      replace the hardcoded "White"/"Black" everywhere they're displayed
      (`GameConfig.team_name`), and a per-theme `TERMS` dict reskins the side-log
      narration too (e.g. "captures" → "deletes" in cyberpunk) — added after the
      user specifically asked for terminology to be part of the theme, not just
      colours. `GameConfig` gained `theme`/`white_name`/`black_name`/
      `white_color`/`black_color`, persisted via `persistence.py` with
      `.get(..., default)` fallbacks so pre-existing saves still load. 75 tests
      passing. Later 2026-07-11, the collapse resolution got a proper **on-board
      animation** (user asked to make collapses readable): movement-first, then
      per-measurement reveals — both split branches (or the mover) slide out,
      then each measured square flashes green (really there) / red (not there),
      wiped ghosts fade, a captured piece shatters, and a short caption floats
      over the action. Chosen choreography = full slide+flash+fade+caption,
      pacing = variable by complexity (`AskUserQuestion`). Architecture: engine
      `CollapseEvent` enriched with `removed`/`captured_square` (still headless);
      new pygame-free `ui/animation.py` builds a beat script from a before-snapshot
      + the events; `render.draw_beat` draws it; `app.py` drives it beat by beat.
      Quiet moves (no measurement) stay instant. 83 tests passing. Later the
      same day, the menu was changed to default its team fields from the last
      `saves/teams.json` save (see `ui/menu.py` above) instead of always
      resetting to origin/White/Black, so a returning pair of players don't
      have to re-pick their theme/names/colours every session. 85 tests
      passing. Later 2026-07-11, split gained the option to leave one branch
      at the piece's own square (user asked to be able to "add current
      position to one of the target possibilities") — previously
      `legal_split_targets`/`ghost_destinations` never offered a piece's own
      square since a normal move can't target where it already is. Fixed at
      the rules layer: `legal_split_targets` (`rules.py`) now prepends
      `square` itself to the candidate list, and `split_destination_kind`
      special-cases `to_square == square` as a measurement-free `RELOCATE`
      (nothing else can occupy a square the piece's own ghost is already on,
      so it's always safe) — `apply_split`/`collapse.resolve_split` needed no
      changes beyond that, since both already re-check occupancy at each
      destination *after* removing the source ghost first. UI-side,
      `app.py::_legal_by_square` adds the source square to the split-mode
      destination dict, and `handle_mouse_down`'s "click the selected square
      to deselect" shortcut is now suppressed in split mode (`square ==
      self.selected and self.mode != "split"`) so that click reaches
      `_handle_split_click` as a "stay here" pick instead of clearing the
      selection — Escape still cancels normally. 87 tests passing. Later
      2026-07-11, **castling** was added (previously a deferred, unbuilt dial —
      see `rules.py`/`collapse.py`/`model.py`/`app.py`/`theme.py` above for the
      full writeup) after the user reached a real playtest position where it
      should have been legal and asked whether it should be possible. Locked
      with the user beforehand: castling only for a king/rook that has *never*
      moved or split, ever (`Piece.has_moved`); squares between king and rook
      may hold ghosts (resolved by walking the king's own path with the same
      machinery as any sliding `CONTACT` move — "start evaluation by moving
      the king first"), except the queenside b-file square, which only the
      rook ever crosses and so must be completely empty up front. The rook
      only follows if the king's move/walk reaches the full castle distance
      uncollapsed. 102 tests passing. Later 2026-07-11, the side panel gained a
      **removed pieces** tray (user asked to show captured figures with a show/
      hide toggle): a "Removed pieces: ON/OFF (C)" button
      (`render.panel_rects()["captured"]`, also bound to the `C` key) drawn
      right below Surrender. Sourced straight from `qb.pieces` filtered to
      `not p.alive` — no new engine state needed, since a captured `Piece`
      already just sits `alive=False` in that dict forever, sorted
      queen-to-pawn (`render._CAPTURED_ORDER`) rather than by capture order.
      `App.show_captured` defaults to `True` and isn't reset by
      `new_game`/`load_from` (a display preference, not game state); the
      button is checked in `handle_mouse_down` ahead of the `is_over()` gate
      so it still works after a win, unlike Mode/Surrender. Initially laid out
      as rows above the log; changed same day (user asked for it beside the
      log instead) to a **second column**: below the divider, the panel splits
      into the log (left, narrowed) and a fixed-width tray (right,
      `render._draw_captured_column`, 12px-radius tokens via `draw_token`'s
      new optional `radius` param, default unchanged for the board/animation
      call sites) listing each `config.team_name(color)`'s dead pieces as a
      little icon grid that wraps to further rows on its own, with a thin
      vertical rule between the two columns. Hiding the tray just widens the
      log back to the panel's full width — both columns share the same
      `log_top`/`bottom_limit` vertical extent so there's no separate height
      bookkeeping. 109 tests passing. Later 2026-07-11, an **advisory
      check-probability overlay** was added (`quantumchess/check.py` + UI
      wiring — see the module/`render.py`/`app.py`/`theme.py` notes above)
      after the user asked for "an interface to signal check and partial
      check, like 3/8 to be a check" plus a warning before a move exposes
      their own king. It does **not** reintroduce a check *rule* (the king
      stays freely capturable): it only displays each king's aggregate danger
      (`1−∏(1−p)` over every enemy capturing attempt, metric chosen with the
      user) in the side panel and flags, on the selected piece, every
      destination that would raise the mover's own king danger with a red ring
      + resulting fraction. Toggle: panel button / `K`. 117 tests passing.
      Later 2026-07-11, a playtest found a **pawn move-generation bug**: a pawn's
      diagonal move was offered as a `CONTACT` onto *any* foreign ghost,
      including a **friendly** one (e.g. a7 "capturing" its own forked b7-pawn
      ghost on b6 — an illegal move that the UI accepted). `_pawn_dest`
      (`rules.py`) checked the occupant's colour for a *solid* diagonal blocker
      but not for a *ghost* one; fixed by only emitting the diagonal `CONTACT`
      when `qb.pieces[occ.piece_id].color != color` (an enemy), mirroring the
      friendly-solid `continue` right above it. Fixes both plain moves and split
      targets (both route through `ghost_destinations`). 119 tests passing.
      Later 2026-07-11, a separate **UI redesign playtest** (`UI_REDESIGN.md`,
      `quantumchess/ui/skins/`, run via a standalone `demo_ui.py`) explored
      3 alternate visual languages (Polished Evolution, Quantum HUD,
      Clarity/Data-viz) live-switchable mid-game, plus bespoke side panels
      for each. It concluded the same day: **Polished Evolution dropped**,
      **Quantum HUD and Clarity kept as the two real views**, and the whole
      thing **merged into the main game** — `demo_ui.py` deleted, `App`
      itself now owns skin-switching (`self.skins`/`cycle_skin()`, **Tab** or
      a panel "view" control, live mid-match, see `ui/app.py`/`ui/skins/`
      above). Clarity's turn header was rebuilt around HUD's "ACTIVE UNIT"
      structure (judged nicer than Polished's) reskinned to Clarity's own
      flat language; a "Quit" button (previously only reachable through the
      now-deleted classic render path) was ported to both surviving skins
      so the merge didn't silently drop it. `test_m4_ui.py` now hit-tests
      through `app.skin.panel_rects()` instead of the old canonical
      `render.panel_rects()`. 119 tests passing (unchanged count — a
      like-for-like swap of which panel geometry the clicks target, not new
      coverage). Later 2026-07-11, a playtest crashed the app: splitting a
      king toward a castle square raised `ValueError("both split destinations
      must be legal")` from `collapse.resolve_split`, because the UI's
      split-mode highlight dict (`app.py::_legal_by_square`) offered the
      square (a leftover default-argument gap) while the rules layer still
      excluded castling from splits outright. Asked, the user wanted the
      opposite of a re-exclusion: castling should be **reachable by splitting
      the king**, with the rook making one ordinary, non-superposed move
      alongside whichever branch lands on the castle square — see
      `rules.py`/`collapse.py`'s **Split-based castling** writeup above for
      the full mechanism (`split_destination_castle_rook`, the
      classify-before-`has_moved` ordering fix, and the `resolve_move`-mirroring
      "rook follows only if that branch's walk completes" rule). 124 tests
      passing.
- [ ] **M5** — (menu dials already landed in M4; this milestone folds into it —
      remaining polish items only, e.g. richer dial explanations in-menu).
- [ ] **M6** — polish pass (see below for what's left).

## Known deferred edge cases
- En passant against a **superposed** victim pawn is not offered as a move (only
  offered while the would-be-captured pawn is solid). Flagged in `rules.py`
  (`_pawn_dest`). Rare combination; revisit if it matters in play.
- A pawn that reaches the back rank via a **CONTACT** move (i.e. through a
  collapse, not a plain push) does not promote — promotion is only wired for the
  deterministic RELOCATE/CAPTURE_SOLID cases (see `rules.py::_pawn_dest`'s
  `emit`). Rare; revisit if it comes up in play.
- UI: seed is chosen by a "reroll" button (random each click), not free-text
  entry — good enough for reproducing a match by writing the number down, not
  for typing an exact known seed. Aura colours cycle through an 8-colour
  palette by `piece_id % 8`, so with many simultaneously-superposed pieces two
  could coincidentally share a colour (cosmetic only, not a correctness issue).

## Conventions
- Reuse python-chess constants everywhere (colours `chess.WHITE/BLACK`, piece types,
  square ints 0..63) for zero-friction interop.
- Keep probabilities as `Fraction` (exact; tests assert per-piece sums == 1).
- When you build the quantum layer, replace `to_classical_board()` callers with
  ghost-aware occupancy rather than extending that solid-only helper.
