# Playtest transcript — 2026-07-11

Found during interactive play: the side-log line for a split always printed
`(1/2), (1/2)` regardless of the ghost's actual probability before the split.
Splitting an already-partial ghost (e.g. the White King's f4 ghost, itself
1/2) should show 1/4 for each new ghost, not 1/2. Root cause and fix: see
`quantumchess/ui/app.py::_handle_split_click` (was a hardcoded string instead
of reading back `qb.ghost_at(...).prob`) — bug fixed same day, engine math in
`rules.py::apply_split` was already correct.

## Game log

```
Black Pawn splits f7 -> f5 (1/2), f6 (1/2)
White Knight splits g1 -> f3 (1/2), e2 (1/2)
Black Pawn e7->e5.
White Knight f3: wasn't really there -- move fizzles.
Black Pawn f5->f4.
White King e1->d2.
Black Bishop splits c8 -> f5 (1/2), g4 (1/2)
White Pawn splits h2 -> h3 (1/2), h4 (1/2)
Black Pawn f4->e3: captures White Pawn.
White King d2->e3: captures Black Pawn.
Black Bishop g4: wasn't really there -- move fizzles.
White King splits e3 -> f4 (1/2), e4 (1/2)
Black Queen splits d8 -> e7 (1/2), f6 (1/2)
White King splits f4 -> g5 (1/2), g4 (1/2)
Black Bishop f5->h3: captures White Pawn.
White King g5->g4.
```

Note: the `(1/2)` shown for the second King split (`f4 -> g5, g4`) is the
buggy display; the actual resulting probabilities were 1/4 each (verified by
re-deriving with `apply_split` directly — see fix commit).
