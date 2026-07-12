# Quantum Chess — Implementation Plan (v1)

Hotseat, 2 local human players, no time limit. Standard chess + a superposition/collapse layer.

## Stack
- **Python 3.11+**
- **`python-chess`** — standard-chess move rules (per-piece legality, sliding, castling, en passant, promotion, FEN).
- **`pygame`** — rendering + input.
- **`pytest`** — tests.
- Pieces rendered as **Unicode chess glyphs** (♔♕♖♗♘♙ …) via a font — no image assets/licensing needed. Alpha = probability; tint = color.

**Hard rule: the game engine is headless** (no `pygame` import). The UI is a thin layer on top. This keeps the quantum logic fully unit-testable and leaves a clean door open to a future web frontend.

## Locked v1 ruleset

### Win condition — *capture the king, no check*
- No check / checkmate / stalemate. You win by **capturing the enemy king**.
- The king is an ordinary piece: it can split, and capturing a king-ghost triggers a normal collapse. Real king there → win; not there → play continues (you've just revealed where it isn't).
- Consequence: no "moving into check" rules to enforce — a big simplification.
- **Surrender** (added 2026-07-11): instead of moving/splitting, the side to move
  can give up on the spot — the other side wins immediately, same as a king
  capture, just without a move played. UI-only (`ui/app.py::App.surrender`,
  `QuantumBoard.winner`/`game_over` set directly, bypassing move/collapse
  machinery entirely since there's no `Move`/`Split` involved). Gated behind a
  click-to-arm/click-again-to-confirm side-panel button (any other click, or
  Escape, cancels the armed confirm) so a stray misclick can't end the game.

### A turn = one action on one ghost
1. **Move** a ghost to one legal square (standard movement for its type), or
2. **Split** a ghost: send it to **two** legal squares at once. The source ghost (probability *p*) becomes two ghosts of *p/2* each. One of the two destinations may be the source square itself, letting a branch stay put while the other moves — otherwise the source square is vacated.

Only the acted-on ghost moves/splits; a piece's other ghosts stay put. (This is `options.md`: "only currently moved figure", "half the probability of its parent".)

**A piece is only ever in superposition with its own ghosts — there is no cross-piece entanglement, ever.**

**Split-scope dial** (`options.md` lines 6–7, a *within-piece* choice):
- *Single-ghost split* (v1 default): only the acted ghost splits (`p → p/2, p/2`).
- *All-ghosts split*: splitting makes **every** ghost of that piece split at once (e.g. bishop at [a ½, b ½] → four ¼-ghosts). Deferred to a later milestone because destination-picking for the other ghosts ties into the movement-symmetry dials (`options.md` lines 16–19). Flagged in code.

**Move-scope dial** (`options.md` lines 12–19, parallel to split-scope):
- *Single-ghost move* (v1 default): only the acted ghost moves.
- *All-ghosts move*: every ghost of the piece moves at once, either **dependently/symmetrically** (mirrored by the middle line or middle point — `options.md` lines 17–19) or **independently** (each ghost takes its own legal move). The **independent** variant shipped 2026-07-11 as the optional `mass_movement` dial: the player plans a destination per ghost (any may hold), and a **single measurement** settles all conflicts at once — if the roll lands the piece on a conflict-free square the conflicting ghosts just vanish (per the collapse-mode dial: Partial keeps the rest superposed, Full collapses to that square), and if it lands on a conflicting square the piece goes solid there and that contact resolves normally. See `collapse.resolve_mass_move` / CLAUDE.md. The symmetric variant is still deferred.

### Probability bookkeeping
- A live piece's ghosts always sum to **1** (it's definitely *somewhere* among them).
- Split: `p → p/2, p/2`. Merge (below): probabilities add.
- **No split limit.** Probabilities may go arbitrarily small (1/2ⁿ); collapses naturally thin the ghost count over the game. (Display note: enforce a *minimum render alpha* so tiny ghosts stay visible and clickable, and label probabilities as `1/2ⁿ`.)

### Merging
- Moving/splitting a ghost onto **another ghost of the same piece** merges them; probabilities add (`options.md` line 30).

### Occupancy, blocking & path collapse
Ghosts on a mover's path are **measured as it passes** — passing *is* a contact.

- A slider (Q/R/B), a pawn's two-square step, etc. walk their path square by square from source toward destination.
- **Solid** pieces block normally (enemy = capture & stop; own = stop before).
- Each **ghost** on an intermediate square is measured the moment the mover reaches it:
  - **Really there** → contact: enemy ⇒ capture it and **movement ends** here; own ⇒ **movement ends** on the square before it. (If the mover is itself a ghost, its own measurement fires here too — see Collapse.)
  - **Not there** → the square was really empty, **movement continues** past it.
- So one move can **collapse several pieces** in a row, and may stop short of its intended destination if a passed ghost turns out to be real. Choosing to route a slider through ghosts is a deliberate, risky measurement — "you may *want* to pass."
- Knights jump (no path → only the landing square is a contact).
- A move that lands on an empty destination with no path contact does **not** self-collapse the mover; its ghost simply relocates.

### Collapse / measurement (the core) — **implemented in `collapse.py`**
When ghost `g` of mover **A** (probability `p_g`) attempts a move whose path (see Occupancy above) touches one or more different-piece ghosts:

1. **Measure A** — "is A really at `g`?" true with prob `p_g`.
   - **Yes** (`p_g`): A is confirmed → collapses solid; all other A-ghosts vanish. Proceed to step 2.
   - **No** (`1 - p_g`): the move **fizzles** entirely (A was elsewhere), nothing on the path is touched, turn ends. Apply collapse **mode** to A's own remaining ghosts:
     - *Partial*: delete ghost `g`, renormalize A's remaining ghosts.
     - *Full*: roll A's true location among remaining ghosts, make solid, delete the rest.
2. **Walk the path**, measuring each different-piece ghost `B` (prob `p_h`) in travel order as A reaches it — "is B really here?":
   - **Yes, enemy**: B is captured (removed entirely). A's movement **ends here** (may be short of the original destination).
   - **Yes, friendly (same color, different piece)**: B is confirmed → collapses solid (its own other ghosts vanish), but isn't captured. A's movement **ends on the square before** B.
   - **No**: B wasn't really there — apply collapse **mode** to B's remaining ghosts, and **A's path continues** to the next square.
   - Either "yes" branch stops the walk; a run of "no"s lets a single move resolve several pieces' superpositions in a row (exactly as many as the path holds).

Capturing a **solid** piece still runs **step 1** (measure the mover) if the mover itself is superposed — only step 2 (measuring the target) is trivial (`p_h = 1`, always "yes"). A superposed piece capturing a certain enemy is *not* a guaranteed capture. Solids block path generation already, so an enemy solid can only ever be the final destination, never a mid-path square. Landing on the **king** and confirming it = win.

### Standard-chess edges (v1 scope)
- **Castling** (implemented 2026-07-11): only for a king/rook that has never moved *or split* — tracked via `Piece.has_moved`, which by construction means both are still solid on their home squares. Squares between king and rook may hold ghosts; the king's 2-square hop is walked with the same path-collapse machinery as any sliding `CONTACT` move, and the rook only follows if that walk reaches the full castle destination uncollapsed. The one square that's the rook's alone to cross (queenside b-file) isn't on the king's path, so it must be completely empty up front rather than being resolved by a walk. No check concept exists in this variant, so there's no "can't castle through/into check" restriction. See `rules.py`/`collapse.py` in `CLAUDE.md` for the full writeup.
- En passant applies only to a **solid** victim pawn (no check concept simplifies castling, above, but doesn't affect this) — if the victim is superposed, that en passant capture isn't offered (deferred edge case, flagged in `rules.py`).
- Promotion (revised 2026-07-11): a pawn reaching the last rank via a quiet push promotes outright only if it's already **solid**. A still-**superposed** ghost reaching the rank is measured on the spot instead — really there confirms it solid (siblings elsewhere vanish) and it promotes (player picks the piece); not there means no promotion, and the collapse mode applies to whatever siblings remain. If a contact move stops short of the promotion square, no promotion happens (unchanged).
- Fancier quantum interactions with these are deferred and flagged in code.

## Match-setup dials exposed in v1
1. **Collapse mode**: Partial ↔ Full.
2. **Splitting**: on/off (no probability cap).
3. **RNG seed** (optional) — for reproducible/testable matches.

Other `options.md` dials (split-scope all-ghosts, who-moves, symmetry variants, equal-`1/n` probabilities) are fixed at the clean defaults above in v1 and added incrementally later. There is **no** cross-piece entanglement dial — a piece only superposes with itself.

## Display
- Solid piece (p=1): opaque glyph. Ghost: alpha ∝ probability.
- Fraction label (½, ¼, ⅛) in the square corner.
- Ghosts of the same piece share a colored **aura/outline** so scattered ghosts read as one piece.
- Click a piece → highlight all its ghosts + legal destinations. Split UI: pick two destinations (the source square itself is offered as one of them, for a "stay + move" split).
- **Side log**: `White bishop split → e3 (½), g5 (½)`, `COLLAPSE: bishop not on e3 — move fizzles`, etc.
- Short **collapse animation** so both hotseat players trust the RNG.

## Architecture
```
quantumchess/
  model.py      # Piece, Ghost, QuantumBoard, GameState, GameConfig
  rules.py      # legal moves per piece (via python-chess), split & merge
  collapse.py   # measurement/collapse (partial & full), seedable RNG
  game.py       # apply action, trigger collapse, win detection, turn switch
  ui/
    render.py   # board, ghosts, labels, auras, highlights, log
    menu.py     # match-setup dials
    app.py      # pygame loop, input handling, animations
  main.py       # entry point
tests/          # rules, splitting, probability sums, collapse stats, win
assets/         # (none needed — Unicode glyphs)
```

## Milestones
1. ✅ **Headless standard chess** over our board model (wrap `python-chess`); play a legal normal game via ASCII debug renderer. *(foundation)* — `model.py`, `rules.py` (M1 subset), `game.py`, `demo_m1.py`, `tests/test_m1_movement.py`.
2. ✅ **Superposition**: split, ghost/probability bookkeeping, merge; ASCII renderer shows ghosts. — `rules.py` (`Split`/`apply_split`/`MoveKind`), `textview.py`, `demo_m2.py`, `tests/test_m2_superposition.py`.
3. ✅ **Collapse**: contact detection + path collapse, both modes, seedable RNG, win-by-king-capture. — `collapse.py` (`resolve_move`), `config.py`, `demo_m3.py`, `tests/test_m3_collapse.py`.
4. ✅ **Pygame UI**: board, ghosts (alpha/labels/auras), selection, legal-move highlighting (safe/merge/risky-contact), split picker, promotion picker, side log, collapse animation, pre-game dial menu, game-over banner. — `ui/theme.py`, `ui/render.py`, `ui/app.py`, `ui/menu.py`, `main.py`, `tests/test_m4_ui.py`. Verified with headless PNG screenshots + simulated-click tests; **still needs a real human playtest** via `python main.py`.
5. ~~Match-setup menu~~ — folded into M4 (`ui/menu.py` already covers the v1 dials). Remaining: richer in-menu explanations if needed.
6. ✅ Polish pass (2026-07-11): user's first interactive playtest passed ("looks like it works"), followed by a self-review that found and fixed three real UX bugs — Escape quit the whole app instead of cancelling a selection, no way to start a new game after a win, and the Move/Split toggle was keyboard-only. Also fixed: a winning move's own collapse animation could be skipped past via New Game. Wrote `HOW_TO_PLAY.md`. 58 tests passing. v1 is playable end to end.

## Testing approach
- Engine is headless → pure `pytest`: legal-move parity with standard chess, probabilities always sum to 1, merge math, and **statistical** collapse tests (a ½ ghost captures ≈50% over N seeded trials — see `test_statistical_capture_rate_near_probability`, 3000 trials).
- Deterministic collapse-mechanism tests use a small `ScriptedRng` test double (fixed `.random()`/`.choices()` sequence) rather than reverse-engineering real seeds — robust across Python versions and not flaky.
- Regression-worthy edge case: a superposed piece capturing a *certain* (solid) enemy must still measure the mover — it is not a guaranteed capture just because the target isn't in question. Covered by `test_capture_of_solid_piece_still_measures_a_superposed_mover_success` / `..._fizzles_if_mover_not_really_there`.
- Manual playtest pass in the UI at the end of each UI milestone.
