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
- **Mass moves: On/Off.** *(Only shown when Splitting is on — it has nothing to
  do without superposition.)* When on, a piece that's already in superposition
  can move *all* of its ghosts at once in a single planned turn (see
  [Mass moves](#mass-moves-moving-a-whole-superposition-at-once) below), instead
  of only moving/splitting one ghost. Off by default.
- **Mass split: On/Off.** *(Only shown when Mass moves is on.)* Extends a
  mass-move turn so each ghost may either **move** to one square or **split**
  into two. Off by default. See
  [Mass moves](#mass-moves-moving-a-whole-superposition-at-once) below.

  Turning a dial off also turns off (and hides) anything that depends on it —
  e.g. turning Splitting off hides *and* clears Mass moves and Mass split.
- **Seed.** Controls the random number generator behind every collapse. Click
  "Reroll seed" for a different one; write down a seed if you want to replay
  the exact same sequence of dice rolls later. (The seed always starts fresh —
  it's the one setting that's deliberately *not* remembered between sessions.)
- **Board theme — Origin / Cyberpunk.** Origin is the classic wood board;
  Cyberpunk is a neon-on-dark look you can tint with each team's colour (and it
  reskins the side-log wording). Cyberpunk also gets a subtle vignette.
- **Piece sets — Classic / Merida / Neon / Unicode, chosen per team.** Each
  side picks its *own* figures (there's a row for each team), so White can play
  Classic pieces while Black plays Neon on the same board. *Classic* and
  *Merida* are proper chess piece artwork; *Neon* renders that side as a glowing
  silhouette in its team colour (great with the Cyberpunk theme); *Unicode* is
  the original simple glyph tokens. Each option shows a little king preview, in
  that team's colour, so you can see the look before you pick.
- **Team names & colours.** Name each side and (Cyberpunk) pick an accent
  colour; the "⇄" swaps who plays White (White always moves first). "Save
  Teams" / "Load Teams" lets you name and reuse a favourite
  theme + set + names + colours on demand.

Click **Start Game**. The window is resizable, and **F11** toggles fullscreen —
the board scales smoothly to fit, staying crisp.

**The menu remembers itself automatically**, too: every dial and cosmetic
choice (collapse mode, splitting/mass moves/mass split, theme, piece sets,
names, colours) is saved the moment you click Start Game (or, mid-match,
New Game / Resume in Settings) and reloaded the next time you open the menu —
no button to click, nothing to lose by forgetting to save. This is separate
from the explicit "Save Teams" / "Load Teams" profile above: that one is a
named look you return to on purpose; this one just keeps whatever you last
actually played with. The seed is the one exception — it always rerolls fresh.

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

### Mass moves: moving a whole superposition at once

*(Only available if you turned **Mass moves** on in the menu.)*

When you select a piece that's **already in superposition** (has more than one
ghost), you enter **planning mode** instead of a normal single-ghost move:

1. Every ghost starts out "holding" its square (a small dot marks it).
2. Click a ghost to pick it, then click where you want *that* ghost to go — an
   arrow shows the plan. Click the ghost again to make it hold instead.
3. Repeat for as many ghosts as you like (leave any of them holding). If you
   aim a **pawn** at the back rank, the promotion picker pops up so you choose
   what that ghost would become (just like a normal promotion).
4. Click **Confirm (Enter)** to play it, or **Cancel (Esc)** to back out.

Then the game settles the whole thing with **one** dice roll. If none of your
ghosts' destinations run into another piece, they all just relocate — no
randomness. If some *do* (an enemy in the way, a risky contact), the roll
decides where your piece really was:

- If it turns out to have been on a **safe** destination, the ghosts that were
  heading into trouble simply vanish (the ones threatened enemies aren't even
  measured) — in **Partial** mode the rest of your piece stays spread out; in
  **Full** mode it collapses solid onto that one square.
- If it turns out to have been on a **conflict** destination, your piece
  becomes solid there and that contact resolves like a normal collapse (capture
  and all), while its other ghosts vanish.

The point: one measurement can clear up *every* potential collision your piece
faced this turn, instead of forcing you to collapse it one contact at a time.

#### Mass split: splitting ghosts during a mass turn

*(Only available if you also turned **Mass split** on in the menu.)*

With **Mass split** on, each ghost in a planning turn can not only move but
**split into two**. The gesture mirrors ordinary split mode, one ghost at a
time:

1. Click a ghost to pick it, then click its **first** target — a pick-ring
   marks it.
2. Now click a **second** target to **split** that ghost in half between the
   two (each branch gets half of that ghost's probability). One of the two
   branches may be the ghost's **own square**, if you want a branch to stay put.
3. Or, to make it a plain single move instead, just click that **first target
   again** (or click another ghost / Confirm) — no split.
4. Clicking a ghost's **own square first** holds it in place, as before.

Everything else is identical to a mass move: all the resulting halves add up to
1, and a single dice roll settles any conflicts across the whole (now larger)
spread of ghosts. A mass-split turn where you never actually split anything is
exactly a mass move.
(A single ghost moving while the rest hold is just an ordinary move — mass moves
are a superset.)

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

## Changing settings mid-game

Click **Settings (O)** (or press `O`) at any time to reopen the same setup
screen you saw before the match started, pre-filled with the game's current
dials, theme, team names, and colours. From there you can:

- **Resume Game** — apply whatever you changed (colours, names, theme, or
  even the collapse-mode/splitting dials) and go straight back to this exact
  position, same board, same turn, same log.
- **New Game** — apply your changes and start a fresh game with them, same as
  starting over from the pre-game menu.

Press `Escape` to back out of Settings without changing anything.

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
| Mass move (if enabled) | Select a superposed piece → aim each ghost → Confirm (or `Enter`) |
| Mass split (if enabled) | In a mass turn, click a ghost → two targets to split it (or one target = move) |
| Skip a collapse animation | Click anywhere |
| Surrender | Click "Surrender" twice (arm, then confirm) |
| New game after a win | Click "New Game", or press `N` |
| Save game | Click "Save", or press `F5` |
| Load game | Click "Load", or press `F9` |
| Toggle removed-pieces tray | Click "Removed pieces", or press `C` |
| Open Settings (change theme/piece set/names/colours/dials) | Click "Settings", or press `O` |
| Resume from Settings without changing anything | Press `Escape` |
| Switch UI view (Clarity / HUD) | Click the view button, or press `Tab` |
| Toggle fullscreen | Press `F11` |
