# Quantum Chess — How to Play

A hotseat (2 players, one keyboard/mouse, no clock) chess variant. Same board,
same pieces, same moves as standard chess — plus one twist: pieces can enter
**superposition** (exist in more than one place at once, each with a
probability), and reality gets pinned down by **collapse** when something
interacts with something else.

## Starting a game

```
python main.py
```

You'll see a setup menu first:

- **Collapse mode — Full / Partial.** This only matters when a piece is measured
  and turns out *not* to be where you tried to interact with it. Say a bishop
  has three possible locations and one of them just got ruled out:
  - **Full**: the bishop's whole superposition resolves immediately — one of
    its remaining locations is chosen at random as "the real one," and it
    becomes solid there. The other locations vanish.
  - **Partial**: only the ruled-out spot disappears. The bishop stays spread
    across its remaining locations, with their probabilities rebalanced to
    still add up to 1.
- **Splitting: On/Off.** Turns the whole superposition mechanic on or off. Off
  gives you ordinary chess.
- **Seed.** Controls the random number generator behind every collapse. Click
  "Reroll seed" for a different one; write down a seed if you want to replay
  the exact same sequence of dice rolls later.

Click **Start Game**.

## The board

Both players can see everything — there's no hidden information except the
outcome of a collapse (which is genuinely random, decided live).

- A **solid** piece (fully opaque token) definitely exists there.
- A **ghost** (faded token, with a fraction like `1/2` in the corner) is one
  *possible* location of a piece. A piece's ghosts always add up to a total
  probability of 1 — it's definitely somewhere among them.
- All of a piece's ghosts share the same colored **outline** so you can tell at
  a glance which faded pieces scattered across the board are really the same
  piece.

## Winning

**Capture the enemy king.** That's it — there's no check or checkmate in this
variant. The king is a normal piece: it can even be superposed like anything
else. If you capture a king-ghost, you might discover the king wasn't really
there — the game keeps going.

## Taking a turn

Click one of your own pieces (any ghost of it) to select it. Legal destinations
light up with a colored dot:

- 🟢 **Green** — a safe move or capture. The outcome is certain.
- 🔵 **Blue** — a merge. You're moving onto another ghost of the *same* piece;
  their probabilities add together (no randomness involved).
- 🟠 **Orange** — a **risky contact**. Something else (an enemy or a friendly
  ghost) is in the way or on that square, and its reality is uncertain. Taking
  this move triggers a **collapse**.

Click a destination to move there. Click the same piece again (or press
**Escape**) to deselect without doing anything.

### Splitting a piece

Click the **Mode: MOVE (M)** button (or press `M`) to switch to **Split**
mode. Select a piece, then click **two** different legal destinations in a
row — the piece splits into two ghosts there, each with half its previous
probability. Click your first pick again to cancel it and choose differently.
One of your two picks can be the piece's own square, so one ghost stays put
while the other moves. (This button is disabled if splitting was turned off
in the menu.)

### Collapses

When you attempt a risky (orange) move, the game measures — in order — whether
your piece was really where you thought, and then whether whatever it touched
was really there. Each measurement is shown briefly at the top of the side
panel ("measuring White Bishop @ b5: IS there") before the final result lands
in the log. A single move can chain through **several** collapses in a row if
your piece slides through more than one uncertain square — so sliding through
a cluster of ghosts is a real gamble, and you might end up stopping short of
where you were aiming.

Click anywhere to skip straight to the result if you don't want to wait for the
reveal.

### Promotion

If a pawn move reaches the back rank via a normal (green) move, a small
picker pops up — click Queen, Rook, Bishop, or Knight.

## Surrendering

If the position's hopeless, click **Surrender** in the panel instead of making
a move. It arms a confirmation — the button turns red and asks you to click it
again. Click it a second time to actually give up (the other side wins on the
spot); clicking anywhere else, or pressing `Escape`, backs out without ending
the game.

## After the game

When a king is captured (or a side surrenders), a **New Game** button appears
in the panel (or press `N`). It starts a fresh game with the same dial
settings you picked in the menu.

## Removed pieces

The side panel keeps a **removed pieces** tray showing every piece each side
has lost so far (small glyphs, sorted queen-to-pawn). Click **Removed pieces
(C)** (or press `C`) to hide it and reclaim the panel space for the log, or
show it again.

## Saving and loading

Click **Save (F5)** (or press `F5`) at any time to snapshot the game to
`saves/quicksave.json` — board position, every ghost's exact probability, the
dial settings, and even the random-number state, so a resumed game's collapses
are exactly as random as if you'd never closed the app. Click **Load (F9)**
(or press `F9`) to resume from that file. There's a single quicksave slot: a
new save overwrites the last one.

## Quick reference

| Action | How |
|---|---|
| Select a piece | Click it |
| Deselect / cancel | Click it again, or press `Escape` |
| Move | Click a legal (dot-highlighted) destination |
| Toggle Move/Split mode | Click the mode button, or press `M` |
| Split | In Split mode, click two destinations |
| Skip a collapse animation | Click anywhere |
| Surrender | Click "Surrender" twice (arm, then confirm) |
| New game after a win | Click "New Game", or press `N` |
| Save game | Click "Save", or press `F5` |
| Load game | Click "Load", or press `F9` |
| Toggle removed-pieces tray | Click "Removed pieces", or press `C` |
