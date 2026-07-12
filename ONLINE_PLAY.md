# Online Play — design notes (not yet built)

Status: **design only**, discussed 2026-07-12. Nothing here is implemented yet.
This is the living spec for turning the current hotseat game into a two-player
online game (one match, one friend — no matchmaking hub, no accounts, no login).

## Why this is easy for *this* game

Three properties of the existing design collapse the hard parts of networked
play:

1. **No hidden information.** The game is hotseat — both players already see the
   *entire* board: all ghosts, all probabilities, everything. So there is
   nothing to hide from the opponent's client, and we can ship full game state
   across the wire with zero secrecy concerns. This removes the single biggest
   reason online games *need* an authoritative server (to keep hidden state
   away from clients).

2. **No timer, turns are discrete.** Latency is irrelevant. A turn is one atomic
   action (`Move` / `Split` / `MassMove`), so it's one message per turn. It can
   even be played correspondence-style (async, hours apart) — the game is
   naturally turn-based, not realtime.

3. **The RNG problem is sidestepped, not solved.** The only source of
   nondeterminism is the collapse dice roll. The clean trick: **the side whose
   turn it is resolves its own action locally (rolls its own dice) and ships the
   *outcome*, not the intent.** The receiving client never rolls — it just
   applies what happened. This means the two machines' RNG streams don't need to
   be synchronized at all; only the active side ever draws. `persistence.py`
   already snapshots `rng.getstate()`, so even a mid-game resync is cheap, but
   for live turn-by-turn play we don't even need that.

## Core protocol (independent of transport)

Per turn, the **active** client (the side whose `qb.turn` it is):

1. Resolves the action locally exactly as today
   (`App._execute_move` / `_confirm_plan` / `_handle_split_click` →
   `collapse.resolve_*`), producing the ordered `CollapseEvent` list.
2. Sends **one message**:
   ```
   { action, events, resulting_snapshot }
   ```
   - `action` — the `Move` / `Split` / `MassMove` (small frozen dataclasses of
     ints; need a `to_dict`/`from_dict`).
   - `events` — the ordered `CollapseEvent`s (dataclasses of ints / `Fraction`s
     / enums).
   - `resulting_snapshot` — `persistence.to_dict(qb, config, rng, ...)`, the
     authoritative post-turn state.

The **passive** client (the side waiting):

1. Already holds the correct *before* board (its own current `qb`).
2. Runs the same `animation.build_animation(before, movers, events)` it would
   run locally → plays the **identical** collapse animation the mover saw.
3. Then hard-sets `qb` from `resulting_snapshot`, guaranteeing zero divergence.

So the receiver gets the full reveal animation *and* provably-consistent state.
This fits the existing headless animation model perfectly: the animation is
rebuildable from `(before_snapshot, movers, events)`, all of which are on the
wire or already local.

**Turn gating** is trivial: a client only accepts board input when
`self.qb.turn == my_color`; otherwise it sits in a "waiting for opponent" state,
rendering and animating incoming turns.

### New code needed (all outside the engine)

The engine (`quantumchess/`) must **never** learn about networking — same
discipline as the pygame rule. The additions are small:

- **Serialization** for `Move`, `Split`, `MassMove`, `CollapseEvent`
  (`to_dict`/`from_dict`). Mechanical — they're frozen dataclasses of
  ints/`Fraction`s/enums; mirror the patterns already in `persistence.py`
  (see `_frac_to_list`/`_frac_from_list`).
- A transport-agnostic **`NetSession`** abstraction (send/recv one message,
  `my_color`, connection state) that `App` talks to. Swapping transports later
  never touches `App` or the engine.
- **Host / Join UI** — one or two screens (reuse the menu layer).
- `App` gains a "this turn arrived from the network" path that replays
  `action + events` and applies `resulting_snapshot` instead of reading local
  clicks.

### MVP shortcut

v1 can skip receiver-side animation: ship just `resulting_snapshot` + the log
line and snap to the new state (maybe a generic flash). Ships in an afternoon;
add synced animation (above) later. Because the animation is already headless
and event-driven, doing it "properly" isn't much more work.

## Transport options (the real decision)

| Option | How | NAT / internet reach | Infra to run | Effort |
|---|---|---|---|---|
| **A. Direct TCP socket** | One player hosts a port, the other connects by IP | LAN: trivial. Internet: needs port-forwarding **or** Tailscale/ZeroTier (both install it, use the tailnet IP — no port-forward, no server) | None | Lowest |
| **B. Hosted WebSocket relay** | ~50-line `websockets`/FastAPI app on a free tier (Render/Fly/Railway); two clients join a **room code**; the server just relays messages | Works anywhere behind NAT, no fiddling | One tiny always-on service | Medium |
| **C. Correspondence via shared storage** | Exchange the JSON payload through a shared Dropbox/Drive folder / gist / Firebase; poll for the opponent's turn file | Works anywhere, fully async | None (or free cloud) | Low, but clunky UX |

They are **not mutually exclusive** — because everything goes through one
`NetSession` interface, we can start with A and add B later without touching
`App` or the engine.

## Recommendation

**Build the `NetSession` seam + the action/event serialization first, then ship
transport A (direct socket), with Tailscale as the "over the internet" story.**

Rationale: zero infrastructure, zero cost, lowest latency, and Tailscale removes
the only real pain (NAT) for a two-person game with a two-minute install on each
side. A "Host game" / "Join game (enter IP)" pair of buttons on the existing
menu is all the UX needed. If we later want click-a-room-code-from-anywhere with
no Tailscale, the hosted relay (B) drops in behind the same interface.

## Deliberately out of scope / known caveats

- **Trust model.** Because the active side rolls its own dice, a *malicious*
  client could fake a favorable collapse. For playing with a friend this is a
  non-issue. If it ever mattered, move the roll to a relay/host that is
  authoritative — the `NetSession` seam makes that a transport swap, not an
  engine change.
- **Reconnection / resume.** `persistence.py` already round-trips full state
  (board + config + RNG state), so a reconnecting client can be resynced by
  sending it a fresh `to_dict` snapshot. Not needed for v1.
- **Simultaneous input is impossible** — turns strictly alternate and are gated
  on `qb.turn`, so there's no concurrent-edit / conflict-resolution problem.
- **No matchmaking, accounts, or lobby** — one match, two known players, by
  explicit design.
