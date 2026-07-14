# Engine reference (`quantumchess/`)

Deep mechanics for the headless engine. For the one-page map see
[ARCHITECTURE.md](../ARCHITECTURE.md); for the locked design decisions and
invariants see [CLAUDE.md](../CLAUDE.md); for when/why each feature landed see
[HISTORY.md](HISTORY.md).

**Hard rule: nothing here may import `pygame`.**

---

## `model.py`

`Piece`, `Ghost`, `QuantumBoard`. Probabilities are exact `Fraction`s; a live
piece's ghosts always sum to 1.

`to_classical_board()` projects the *solid* position onto a python-chess board —
used for ASCII rendering and as the movement oracle.

`Piece.has_moved` is set the instant a piece is moved *or* split, ever. Even if it
later re-merges onto its home square it stays permanently disqualified from
castling. This is what makes "has never moved or split" equivalent to "is
guaranteed solid on its home square", so castling needs no separate solidity check.

## `rules.py`

`Move` / `MoveKind` / `Split` / `MassMove` / `MassSplit`, `generate_moves`
(pseudo-legal, via `Board.attacks` over solids so it extends to quantum blockers),
`apply_move`, `apply_split`, `legal_split_targets`, `split_destination_kind`,
`remove_piece`.

**Occupancy invariant: ≤1 ghost per square.** Same-piece ghosts merge (probabilities
add); a *different* piece's ghost is a `CONTACT` needing a collapse. `CONTACT` moves
are only generated on request (`include_contact=True`), and `apply_move` raises
`NotImplementedError` on them — resolution lives in `collapse.py`.

`legal_split_targets` includes the piece's **own square** (a "stay + move" split) and
squares that would capture/contact an enemy (splitting into an enemy square is legal
— see `resolve_split`). `apply_split` itself stays the measurement-free fast path and
raises if either destination needs a collapse. This function stays dial-agnostic by
design (rule 5): the `split_stay_enabled` dial that lets a player turn "stay + move"
off is enforced in `ui/app.py` (`_legal_by_square`/`plan_legal`), not here.

### Mass movement

`MassMove(piece_id, assignments)` — one `(from_square, to_square)` per current ghost
(`to == from` means "stay"). `mass_assignment_move(qb, pid, from, to)` classifies one
leg (a "stay" is a measurement-free `RELOCATE` on its own square; otherwise it's
whichever `ghost_destinations` move lands on `to`). A promoting pawn leg carries its
chosen piece via `MassMove.promotions` (`(from_square, ptype)` pairs) — the player
picks per leg in the UI, defaulting to queen only if unspecified.

### Mass split

`MassSplit(piece_id, legs, promotions)` is the strict generalization: `legs` is one
`(from_square, destinations)` per ghost, where `destinations` is **one** square (that
ghost relocates — exactly a `MassMove` leg) or **two distinct** squares (that ghost
splits into two `p/2` halves). `promotions` is keyed by both squares
(`(from_square, to_square, ptype)` triples) since one ghost can split into two
promoting destinations. Legs still classify through `mass_assignment_move`.

Neither `MassMove` nor `MassSplit` cares whether a leg is a "stay" (`destinations ==
(from_square,)`) or a real move/split — that's a UI-only constraint too. The
`mass_all_must_act` dial (every ghost must act; none may just stay) is enforced by
`App._plan_fully_acted`/`_confirm_plan` refusing to resolve the plan at all while it's
violated, same dial-agnostic-engine principle as `split_stay_enabled` above.

### Castling

`Move.castle_rook: Optional[tuple[rook_piece_id, rook_from, rook_to]]`, set only on
the king's own move. `_castle_moves` offers it when the king and that rook both have
`has_moved == False`.

The king's 2-square hop is classified with the same `_classify` /
`_path_has_foreign_ghost` helpers as any other slide, so it comes out as:

- `RELOCATE` — clear path (resolved in `apply_move`),
- `CAPTURE_SOLID` — a solid enemy on the final square (castling-into-a-capture is
  *allowed* here, unlike real chess, to keep "a king slide is a king slide"),
- `CONTACT` — a ghost (friendly or foreign) anywhere on the path → deferred to
  `collapse.resolve_move`.

The queenside b-file square is crossed only by the rook, never by the king, so no
walk ever resolves it: it must be **completely empty** (no ghost at all) for
queenside castling to be offered. Deliberate simplification — no rook-side collapse
mechanic was designed.

**The rook follows only if the king's move/walk actually reaches the full castle
destination.** A king that stops short (captures a path ghost, or is blocked by a
confirmed friendly one) leaves the rook untouched — mirroring "path collapse can stop
a move short of its target".

### Split-based castling

Castling is also reachable by **splitting** one king branch toward the castle square.
`legal_split_targets` / `split_destination_kind` call `ghost_destinations` with the
default `include_castle=True`, so a castle destination is an ordinary split target
reported as whatever `MoveKind` it actually is.
`split_destination_castle_rook(qb, square, to_square) -> Optional[tuple[rook_id, rook_from, rook_to]]`
is how `apply_split` / `collapse.resolve_split` learn a branch is a castling one.

**The rook is never superposed** — it always makes one plain, deterministic
relocation:

- clear-path (`RELOCATE`) branch → nothing to measure, `apply_split` moves the rook
  unconditionally the instant the branch is placed;
- `CAPTURE_SOLID` / `CONTACT` branch → `resolve_split` moves it only once *that
  branch* is confirmed to have reached the castle square (capture branches always
  complete once confirmed; contact branches only if `_walk_contact`'s `stop_square`
  equals the full destination).

⚠️ Both `apply_split` and `resolve_split` must classify the destinations (and look up
`castle_rook`) **before** marking `has_moved = True` — marking first makes the king
look already-moved to that same classification call, silently turning every castle
branch into "not a castle".

### Known deferred edge cases

- **En passant** against a *superposed* victim pawn isn't offered (only while the
  victim is solid). Flagged in `_pawn_dest`.
- A pawn reaching the back rank via a **CONTACT** move (i.e. through a collapse, not
  a plain push) does **not** promote — promotion is only wired for the deterministic
  `RELOCATE`/`CAPTURE_SOLID` cases (see `_pawn_dest`'s `emit`).

---

## `collapse.py`

The measurement engine. Returns a `MoveResolution` (fizzled?, `final_square`,
`captured_piece_ids`) plus an ordered `CollapseEvent` log the UI animates from.

Each `CollapseEvent` carries the measurement (role / piece / square / `prob_before` /
`present`) **and its visual consequence**: `removed` (the `(square, prob)` of every
ghost that measurement wiped) and `captured_square`. Populated by having
`_collapse_positive` / `_collapse_negative` *return* what they drop — this is what
lets the UI animate a collapse without re-deriving the engine math.

### `resolve_move`

**Measurement only happens on collision.** `RELOCATE` / `MERGE` (empty square, or the
mover's own ghost) skip straight to a plain `apply_move` — no dice.

**Exception: a pawn landing on the promotion rank while still a ghost.**
`_resolve_promotion_relocate` relocates the ghost first (via `apply_move` with
`promotion` stripped), then measures that ghost against its own probability: really
there ⇒ `_collapse_positive` (confirm solid, drop siblings) then promote; not there ⇒
`_collapse_negative`, no promotion — it just stays a pawn wherever it ends up. Logged
with role `"promotion"`. A fully solid pawn (`prob == 1`, no siblings) has nothing to
measure and promotes as before.

Any move that touches another piece (`CAPTURE_SOLID` or `CONTACT`) **measures the
mover first** — this applies *even when capturing a certain/solid piece*: a superposed
mover isn't guaranteed to land the capture just because the target is certain.

- positive ⇒ mover goes solid, siblings dropped;
- negative ⇒ move fizzles, collapse mode applies to the remaining siblings.

For `CONTACT`, once the mover is confirmed, `_walk_contact` walks the path square by
square measuring every foreign ghost in travel order: enemy real ⇒ capture & stop
there; friendly real ⇒ confirm it solid & stop one square before; not-there ⇒ apply
collapse mode and keep walking. One move can resolve several pieces' superpositions in
a row. Ends the game via king capture, same as `apply_move`.

### `resolve_split`

Both branches settle in the same instant the split is made. Measurement-free branches
(empty / same-piece merge) are placed unconditionally first; then each
enemy-contacting branch is measured exactly like a move's mover (a `p/2` branch
capturing even a certain piece isn't guaranteed):

- positive ⇒ confirm solid there, wipe every other ghost of the piece
  (`_collapse_positive`, shared with `resolve_move`);
- negative ⇒ remove just that branch and renormalize the rest (`_collapse_negative`).

A `CONTACT` branch additionally walks the path via `_walk_contact`, so a sliding split
branch can capture or stop short partway. If splitting into *two* enemy-occupied
squares at once, the first branch that confirms real skips measuring the second
entirely (the piece is settled; that square is never touched).

### `resolve_mass_move`

Each leg of a `MassMove` is classified against the pre-move board (via
`rules.mass_assignment_move`) as **safe** (`RELOCATE`/`MERGE`) or a **conflict**
(`CONTACT`/`CAPTURE_SOLID`, or a still-superposed pawn promoting — promotions need a
measurement, so they count as conflicts).

- **No conflicts** ⇒ every ghost just relocates. Probabilities merge by destination,
  no dice, ep cleared — the same "a quiet move is instant" rule as elsewhere.
- **≥1 conflict** ⇒ **one categorical roll** (`_roll_entry`, weighted by each ghost's
  `prob`, which sum to 1 — the generalization of a single mover's Bernoulli `_flip`)
  picks where the piece *really* is.
  - Winning leg **safe** ⇒ the conflicting ghosts vanish, and the **collapse-mode dial
    applies**: PARTIAL keeps the safe ghosts renormalized (piece stays superposed),
    FULL collapses the whole piece onto the rolled square. Enemies on the *dropped*
    legs are never measured (the piece dodged).
  - Winning leg a **conflict** ⇒ the piece goes solid on that slide
    (`_collapse_positive` drops every other ghost) and the slide resolves exactly like
    a `resolve_move` `CONTACT`/`CAPTURE_SOLID`, reusing `_walk_contact` to measure the
    enemy on its path (so it can capture or stop short).

Returns a `MassMoveResolution` (events, `captured_piece_ids`, plus `final_square` /
`chosen_from` / `chosen_to` — the solid landing, the winning ghost's source, and the
winning leg's *intended* destination, which differ when a CONTACT slide stopped
short). `chosen_to` is what lets the UI tell the winning branch from a *sibling*
branch of the same source ghost.

**Provably reduces to today's single move** (move one ghost, hold the rest) in both
collapse modes: `P(solid at s) = p_s` either way.

### `resolve_mass_split`

The generalization of the above. Shared internals: `_classify_mass_entry` (one leg →
a classified `_MassEntry`) + `_resolve_mass_entries` (the roll and the three branches
above). `resolve_mass_move` builds one entry per assignment; `resolve_mass_split`
builds **one or two** (half-prob each) per leg — so a mass split whose every leg is
single is byte-for-byte a mass move (asserted in `tests/test_mass_split.py`). Same
single-measurement guarantee: `P(solid at s) = mass at s`.

---

## `check.py` — advisory check overlay

**Purely informational. It never restricts a move** — the king stays freely
capturable (see the locked decisions in [CLAUDE.md](../CLAUDE.md)). Headless, exact
`Fraction`s, **no RNG** (it's the *expected* danger, not a rolled outcome).

**Metric: the single strongest enemy move.**
`check_probability(qb, color) = max over every enemy move m of P(m captures the king)`.
The opponent only gets **one** move, so two separate attackers aiming at the king do
**not** compound.

Each move's capture probability is computed exactly from the engine's own
path-collapse rules (`strongest_threat` / `_path_capture_part`). For an enemy ghost of
presence `p` sliding `from→to`, walk the path in travel order and take:

```
p · Σ over king ghosts on square s_k of  q(s_k) · ∏ over each *other* piece X
                                          with ghosts strictly before s_k
                                          of (1 − X's total ghost mass there)
```

King locations are **mutually exclusive** (the `q(s_k)` sum to 1), so conditioned on
"king is on `s_k`", every *earlier* king ghost on the path is empty and drops out of
the blocker product — only non-king, non-attacker pieces block. Consequences: a single
slide that **sweeps several king ghosts** (a rook down a file the king is superposed
along) reads as a certain capture, while two king ghosts needing two *different* moves
take the **max**, not a sum. A blocking piece with several ghosts on the path blocks
with probability = the **sum** of those masses (its locations are mutually exclusive
too); distinct pieces are independent, hence the ∏ over X.

Moves are enumerated by reusing `rules.ghost_destinations` (solid blockers already
prune each ray via the oracle board). The metric ignores `move.kind` entirely — it
only needs `from`/`to` and the path — so it automatically covers a solid-king
`CAPTURE_SOLID`, a superposed-king `CONTACT`, a pawn's diagonal, etc.

**With `mass_movement=True`**, a superposed enemy piece's strongest king threat is
`Σ over its ghosts g of p_g · (best single leg of g, assuming g is certainly present)`
— a *sum* over the mutually-exclusive categorical-roll outcomes. This can strictly
beat any single move (two ghosts covering the king from opposite sides guarantee a
capture) and is folded into the same max.

`strongest_threat` returns a `KingThreat` (prob + attacker + `from`/`to`, or
`is_mass`) with a `describe()` label (`"R a4->e1"` / `"R mass"`) so the readout can
**name** the strongest move.

`move_self_check(qb, move, mass_movement=False)` answers "does this move expose *my*
king?" — it builds a hypothetical board via `_hypothetical_after` (deep-copy, relocate
the mover, drop an outright-captured solid, drag a castling rook) and re-runs
`check_probability` for the mover's colour, catching both moving into fire and
discovered exposure. It approximates the move as simply completing; the random collapse
a CONTACT move might itself trigger is not rolled.

---

## `config.py`

`GameConfig` (the match dials) and `CollapseMode`. Split out of `game.py` so
`collapse.py` can import it without a circular dependency; re-exported from `game.py`.

| Field | Notes |
|---|---|
| `collapse_mode` | PARTIAL / FULL |
| `splitting_enabled` | Enforced at the **UI** layer (`App.toggle_mode`) |
| `split_stay_enabled` | Needs `splitting_enabled`; whether a split may leave one branch on the source square ("stay + move" as well as "move + move"). Default on. UI-enforced (`app.py` `_legal_by_square`/`plan_legal`) |
| `mass_movement` | Enforced at the UI layer (`App.can_mass`) |
| `mass_split` | Only meaningful with `mass_movement` on; UI-enforced (`App.can_mass_split`) |
| `mass_all_must_act` | Needs `mass_movement`; every ghost must move/split (none may just stay). UI-enforced (`App._plan_fully_acted`/`_confirm_plan`) |
| `seed` | |
| `theme`, `white_name`/`black_name`, `white_color`/`black_color` | Cosmetic; `team_name(color)` / `team_color(color)` helpers |
| `white_piece_set`/`black_piece_set` | Per-team piece art; `piece_set(color)` accessor |

The engine's `resolve_*` functions are **dial-agnostic** by design — dials are gated in
the UI. The cosmetic fields live here (not in `ui/`) so `persistence.py` can round-trip
them without importing pygame.

---

## `persistence.py`

JSON save/load, headless like the rest. Three independent round-trips:

**Game** — `to_dict`/`from_dict` + `save_game`/`load_game` (default slot
`saves/quicksave.json`). Snapshots the board (pieces + ghosts, exact `Fraction`s,
`has_moved`), the `GameConfig`, and the RNG's internal state
(`random.Random.getstate()`/`setstate()`) so a resumed game's future collapses draw the
same sequence they would have. Deliberately excludes UI-transient state (click
selection, in-progress split picker, animation queue) — `qb` is fully resolved the
instant a move applies. `load_game` raises on an unrecognized `version`.

**Teams** — `save_teams`/`load_teams` (own `TEAMS_FORMAT_VERSION`, slot
`saves/teams.json`). Just the cosmetic identity (theme + names + colours + piece sets),
independent of any game, so players can reuse a favourite look. Driven straight from the
menu's fields (plain kwargs, not a `GameConfig`) so it stays pygame-free.

**Last settings** — `save_last_settings`/`load_last_settings` (own
`LAST_SETTINGS_FORMAT_VERSION`, slot `saves/last_settings.json`). A superset of the
teams round-trip that also carries **every dial**. Written automatically by
`Menu._finalize` on every Start/New Game/Resume, read by `Menu._load_startup_defaults`
when a fresh pre-game menu opens. **The seed is deliberately excluded** — every match
gets a fresh random one.

**Schema policy: grow-only.** New fields are read with `.get(..., default)`, not a hard
key lookup, so older files still load instead of raising — no `version` bump when the
schema only *grows* optional fields. Precedents: `has_moved` (absent ⇒ "never moved",
which is never wrong for a piece still on its home square), the theme fields (absent ⇒
origin/White/Black), and the piece sets (an old single `piece_set` key loads for *both*
sides).

---

## `game.py`

`random_selfplay` — a classical-only self-play driver (no quantum layer) used by
the standard-chess movement tests.
