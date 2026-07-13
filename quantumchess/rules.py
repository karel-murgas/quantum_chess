"""Movement + superposition rules for Quantum Chess.

Milestone 1: classical movement, capture-the-king.
Milestone 2 (this): a piece may be *superposed* into several ghosts. A turn is one
action on one ghost — **move** it, or **split** it into two (``p -> p/2, p/2``).
Ghosts of the same piece **merge** (probabilities add) when they land together.

python-chess is used only as a geometric movement oracle (``Board.attacks``) over
the **solid** pieces; ghosts are handled by us. Occupancy invariant: **at most one
ghost per square** — same-piece ghosts merge, and landing on a *different* piece's
ghost is a "contact" (collapse), which is deferred to Milestone 3.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from fractions import Fraction
from typing import Optional

import chess

from .model import Ghost, QuantumBoard


class MoveKind(Enum):
    RELOCATE = auto()        # onto an empty square
    MERGE = auto()           # onto another ghost of the *same* piece (probs add)
    CAPTURE_SOLID = auto()   # onto an enemy *solid* piece (deterministic, p=1)
    CONTACT = auto()         # onto/through a *different* piece's ghost -> collapse (M3)


@dataclass(frozen=True)
class Move:
    piece_id: int
    from_square: int
    to_square: int
    is_capture: bool = False
    captured_piece_id: Optional[int] = None
    promotion: Optional[int] = None
    is_en_passant: bool = False
    is_double_push: bool = False
    kind: MoveKind = MoveKind.RELOCATE
    castle_rook: Optional[tuple[int, int, int]] = None  # (rook_piece_id, rook_from, rook_to)

    def uci(self) -> str:
        s = chess.square_name(self.from_square) + chess.square_name(self.to_square)
        if self.promotion is not None:
            s += chess.piece_symbol(self.promotion)
        return s


@dataclass(frozen=True)
class Split:
    """Split the ghost on ``from_square`` into two ghosts at ``to_a`` / ``to_b``."""
    piece_id: int
    from_square: int
    to_a: int
    to_b: int


@dataclass(frozen=True)
class MassMove:
    """Move *every* ghost of one superposed piece in a single planned turn (the
    optional "mass movement" dial -- see ``collapse.resolve_mass_move``).

    ``assignments`` is one ``(from_square, to_square)`` per current ghost of the
    piece; ``to_square == from_square`` means that ghost stays put. Resolution
    measures the whole piece *once* to settle any conflicts (a destination that
    contacts another piece), rather than collapsing every ghost.

    ``promotions`` (``(from_square, promotion_ptype)`` pairs) records the piece
    a promoting pawn leg should become -- the player picks it per leg in the UI,
    exactly like a single move, rather than defaulting to a queen."""
    piece_id: int
    assignments: tuple[tuple[int, int], ...]
    promotions: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class MassSplit:
    """Move *or split* every ghost of one superposed piece in a single planned
    turn -- the optional "mass split" dial (requires ``mass_movement``; see
    ``collapse.resolve_mass_split`` and CLAUDE.md).

    ``legs`` is one ``(from_square, destinations)`` per current ghost of the
    piece, where ``destinations`` is a tuple of **one** square (that ghost just
    relocates, exactly like a ``MassMove`` leg -- ``to == from`` means "stay")
    or **two distinct** squares (that ghost *splits* into two ``p/2`` halves).
    This is the strict generalization of ``MassMove``: a plan whose every leg
    has a single destination resolves identically.

    Like a mass move, the whole piece's conflicts are settled by *one*
    measurement over the resulting halves (which sum to 1), rather than
    collapsing each ghost. ``promotions`` (``(from_square, to_square,
    promotion_ptype)`` triples) records the piece a promoting pawn *branch*
    becomes -- keyed by both squares since a single ghost can split into two
    promoting destinations that each need their own choice."""
    piece_id: int
    legs: tuple[tuple[int, tuple[int, ...]], ...]
    promotions: tuple[tuple[int, int, int], ...] = ()


# --------------------------------------------------------------------- oracle
def _solids_board(qb: QuantumBoard) -> chess.Board:
    """A python-chess board holding only the solid (certain) pieces."""
    board = chess.Board.empty()
    for piece in qb.living_pieces():
        if qb.is_solid(piece.id):
            board.set_piece_at(qb.solid_square(piece.id),
                               chess.Piece(piece.ptype, piece.color))
    return board


def _classify(qb: QuantumBoard, target: int, moving_pid: int, color: bool):
    """Return (MoveKind|None, captured_pid|None) for landing on ``target``.

    None kind means the square is blocked by our own solid piece (illegal).
    Ghost occupancy (not on the oracle board) is resolved here against ``qb``.
    """
    occ = qb.ghost_at(target)
    if occ is None:
        return MoveKind.RELOCATE, None
    if occ.piece_id == moving_pid:
        return MoveKind.MERGE, None
    if qb.is_solid(occ.piece_id):
        if qb.pieces[occ.piece_id].color == color:
            return None, None                      # own solid blocks
        return MoveKind.CAPTURE_SOLID, occ.piece_id
    return MoveKind.CONTACT, None                   # different piece's ghost


def _path_has_foreign_ghost(qb: QuantumBoard, frm: int, to: int, moving_pid: int) -> bool:
    for s in chess.SquareSet(chess.between(frm, to)):
        g = qb.ghost_at(s)
        if g is not None and g.piece_id != moving_pid:
            return True
    return False


# ----------------------------------------------------------- move generation
def ghost_destinations(qb: QuantumBoard, square: int,
                       solids_board: Optional[chess.Board] = None,
                       include_castle: bool = True) -> list[Move]:
    """Pseudo-legal moves for the single ghost currently on ``square``."""
    g = qb.ghost_at(square)
    assert g is not None, "no ghost on that square"
    piece = qb.pieces[g.piece_id]
    board = solids_board if solids_board is not None else _solids_board(qb)

    previously = board.piece_at(square)
    board.set_piece_at(square, chess.Piece(piece.ptype, piece.color))
    try:
        if piece.ptype == chess.PAWN:
            moves = _pawn_dest(qb, board, g, piece.color)
        else:
            moves = _piece_dest(qb, board, g, piece.color)
    finally:
        if previously is None:
            board.remove_piece_at(square)
        else:
            board.set_piece_at(square, previously)
    if include_castle and piece.ptype == chess.KING:
        moves.extend(_castle_moves(qb, g, piece.color))
    return moves


# ------------------------------------------------------------------ castling
# Castling only ever applies to a king/rook that has *never* moved or split
# (see CLAUDE.md) -- which by construction means it's still solid on its
# original square, so there's nothing to measure about the mover itself. The
# king's 2-square hop is generated like any other slide (`_classify` +
# `_path_has_foreign_ghost`), which lets `collapse.resolve_move` walk it with
# the exact same path-collapse machinery used for sliding CONTACT moves --
# "start evaluation by moving the king first". The rook only ever follows if
# the king's walk reaches the full destination uncollapsed; a king that stops
# short (captures or fizzles partway) leaves the rook untouched. The one
# square that's the rook's alone to cross (b-file, queenside) isn't on the
# king's path at all, so it isn't resolved by any walk -- it must be
# completely empty (no ghost, friendly or foreign) for queenside castling to
# be offered.
_CASTLE_SIDES = (
    # side, rook_file, king_to_file, rook_to_file, rook-only transit files
    ("K", 7, 6, 5, ()),
    ("Q", 0, 2, 3, (1,)),
)


def _castle_moves(qb: QuantumBoard, king_ghost: Ghost, color: bool) -> list[Move]:
    king_pid = king_ghost.piece_id
    if qb.pieces[king_pid].has_moved:
        return []
    rank = chess.square_rank(king_ghost.square)
    king_sq = king_ghost.square
    if king_sq != chess.square(4, rank):
        return []  # not on its home square (shouldn't happen if never moved)

    moves: list[Move] = []
    for _side, rook_file, king_to_file, rook_to_file, rook_only_files in _CASTLE_SIDES:
        rook_sq = chess.square(rook_file, rank)
        rook_ghost = qb.ghost_at(rook_sq)
        if rook_ghost is None:
            continue
        rook = qb.pieces[rook_ghost.piece_id]
        if rook.ptype != chess.ROOK or rook.color != color or rook.has_moved:
            continue
        if any(qb.ghost_at(chess.square(f, rank)) is not None for f in rook_only_files):
            continue  # rook-only transit square must be fully empty

        king_to = chess.square(king_to_file, rank)
        rook_to = chess.square(rook_to_file, rank)

        path_squares = list(chess.SquareSet(chess.between(king_sq, king_to))) + [king_to]
        blocked = False
        for sq in path_squares:
            occ = qb.ghost_at(sq)
            if occ is not None and qb.is_solid(occ.piece_id):
                # A solid piece always blocks unless it's an enemy sitting
                # exactly on the king's final square (a deterministic capture).
                if qb.pieces[occ.piece_id].color == color or sq != king_to:
                    blocked = True
                    break
        if blocked:
            continue

        kind, cap_id = _classify(qb, king_to, king_pid, color)
        if kind is None:
            continue
        if kind != MoveKind.CONTACT and _path_has_foreign_ghost(qb, king_sq, king_to, king_pid):
            kind, cap_id = MoveKind.CONTACT, None

        moves.append(Move(
            king_pid, king_sq, king_to,
            is_capture=kind == MoveKind.CAPTURE_SOLID,
            captured_piece_id=cap_id,
            kind=kind,
            castle_rook=(rook_ghost.piece_id, rook_sq, rook_to),
        ))
    return moves


def _piece_dest(qb, board, g: Ghost, color: bool) -> list[Move]:
    moves: list[Move] = []
    for target in board.attacks(g.square):
        kind, cap_id = _classify(qb, target, g.piece_id, color)
        if kind is None:
            continue
        if kind != MoveKind.CONTACT and _path_has_foreign_ghost(
                qb, g.square, target, g.piece_id):
            kind, cap_id = MoveKind.CONTACT, None
        moves.append(Move(
            g.piece_id, g.square, target,
            is_capture=kind == MoveKind.CAPTURE_SOLID,
            captured_piece_id=cap_id,
            kind=kind,
        ))
    return moves


def _pawn_dest(qb, board, g: Ghost, color: bool) -> list[Move]:
    moves: list[Move] = []
    sq, pid = g.square, g.piece_id
    forward = 8 if color == chess.WHITE else -8
    start_rank = 1 if color == chess.WHITE else 6
    promo_rank = 7 if color == chess.WHITE else 0

    def emit(to_sq, kind, *, cap_id=None, ep=False, double=False):
        if kind in (MoveKind.RELOCATE, MoveKind.CAPTURE_SOLID) and \
                chess.square_rank(to_sq) == promo_rank:
            for promo in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT):
                moves.append(Move(pid, sq, to_sq, kind == MoveKind.CAPTURE_SOLID,
                                  cap_id, promotion=promo, is_en_passant=ep, kind=kind))
        else:
            moves.append(Move(pid, sq, to_sq, kind == MoveKind.CAPTURE_SOLID,
                              cap_id, is_en_passant=ep, is_double_push=double, kind=kind))

    # forward push(es): a *solid* piece (own or enemy) directly ahead blocks
    # outright -- pawns never push into occupancy and can't jump a certain
    # blocker. A *ghost* in the way (own or foreign) doesn't block the
    # attempt: the pawn may still try to push through it, and every foreign
    # ghost anywhere on the path (not just the destination) makes this a
    # CONTACT move so ``collapse.resolve_move`` measures it square-by-square.
    one = sq + forward
    one_clear_of_solid = 0 <= one < 64 and board.piece_at(one) is None
    if one_clear_of_solid:
        ghost_one = qb.ghost_at(one)
        if ghost_one is None:
            emit(one, MoveKind.RELOCATE)
        elif ghost_one.piece_id == pid:
            emit(one, MoveKind.MERGE)          # push-merge onto own ghost
        else:
            emit(one, MoveKind.CONTACT)        # foreign ghost ahead -> collapse resolves it

        # two-square push from the starting rank: can't jump a solid blocker
        # on "one" (already guaranteed by one_clear_of_solid), but a ghost on
        # "one" is just another square to measure along the way.
        two = sq + 2 * forward
        if chess.square_rank(sq) == start_rank and 0 <= two < 64 and board.piece_at(two) is None:
            ghost_two = qb.ghost_at(two)
            if ghost_one is None and ghost_two is None:
                emit(two, MoveKind.RELOCATE, double=True)
            elif (ghost_one is None or ghost_one.piece_id == pid) and \
                    ghost_two is not None and ghost_two.piece_id == pid:
                emit(two, MoveKind.MERGE, double=True)  # path clear/own-ghost, destination merges
            else:
                emit(two, MoveKind.CONTACT, double=True)  # foreign ghost somewhere on the path

    # diagonal captures
    for target in board.attacks(sq):
        solid = board.piece_at(target)
        if solid is not None:
            if solid.color != color:
                emit(target, MoveKind.CAPTURE_SOLID, cap_id=qb.piece_id_at(target))
            continue
        occ = qb.ghost_at(target)
        if occ is not None and occ.piece_id != pid:
            # A pawn's diagonal move is a *capture* -- only legal against an
            # enemy. A friendly ghost on the diagonal square is not a capturable
            # target (mirrors the friendly-solid `continue` just above), so the
            # pawn simply can't go there.
            if qb.pieces[occ.piece_id].color != color:
                emit(target, MoveKind.CONTACT)
        elif occ is None and target == qb.ep_square:
            victim = qb.ghost_at(target - forward)
            # En passant against a superposed victim pawn is a deferred edge case
            # (see PLAN.md); only offer it while the victim is solid/certain.
            if victim is not None and qb.is_solid(victim.piece_id):
                emit(target, MoveKind.CAPTURE_SOLID, cap_id=victim.piece_id, ep=True)

    return moves


def generate_moves(qb: QuantumBoard, include_contact: bool = False) -> list[Move]:
    """All pseudo-legal moves for the side to move, across every ghost.

    ``CONTACT`` moves need collapse (Milestone 3); by default they're excluded so
    callers only ever get moves that ``apply_move`` can execute today.
    """
    board = _solids_board(qb)
    moves: list[Move] = []
    for piece in qb.living_pieces(qb.turn):
        for ghost in qb.ghosts_of(piece.id):
            moves.extend(ghost_destinations(qb, ghost.square, board))
    if not include_contact:
        moves = [m for m in moves if m.kind != MoveKind.CONTACT]
    return moves


# --------------------------------------------------------------- apply layer
def apply_move(qb: QuantumBoard, move: Move) -> None:
    if qb.game_over:
        raise RuntimeError("game is already over")
    if move.kind == MoveKind.CONTACT:
        raise NotImplementedError("collapse resolution lands in Milestone 3")

    moving = qb.ghost_at(move.from_square)
    assert moving is not None and moving.piece_id == move.piece_id
    mover = qb.pieces[move.piece_id]
    mover.has_moved = True

    if move.kind == MoveKind.MERGE:
        target = qb.ghost_at(move.to_square)
        target.prob += moving.prob
        qb.ghosts.remove(moving)
        qb.ep_square = None
        qb.turn = not qb.turn
        return

    if move.is_capture and move.captured_piece_id is not None:
        remove_piece(qb, move.captured_piece_id)
        if qb.pieces[move.captured_piece_id].ptype == chess.KING:
            qb.winner = mover.color
            qb.game_over = True

    moving.square = move.to_square
    if move.promotion is not None:
        mover.ptype = move.promotion
    qb.ep_square = (move.from_square + move.to_square) // 2 if move.is_double_push else None
    if move.castle_rook is not None:
        rook_pid, rook_from, rook_to = move.castle_rook
        qb.ghost_at(rook_from).square = rook_to
        qb.pieces[rook_pid].has_moved = True
    if not qb.game_over:
        qb.turn = not qb.turn


def legal_split_targets(qb: QuantumBoard, square: int) -> list[int]:
    """Squares the ghost on ``square`` may split toward -- anywhere it could
    otherwise move, including onto an enemy (solid or ghost), plus ``square``
    itself (one branch stays put while the other moves). Landing on an enemy
    is legal but must go through ``collapse.resolve_split``, which measures
    that branch on contact exactly like a CONTACT/CAPTURE_SOLID move;
    ``apply_split`` below only handles the measurement-free case itself.
    A king may split one branch toward a castle square too -- the rook is
    never superposed by this, it just makes its own plain relocation
    alongside whichever branch reaches the castle square (see
    ``split_destination_castle_rook`` / ``apply_split`` / ``collapse.resolve_split``)."""
    return [square] + [m.to_square for m in ghost_destinations(qb, square)]


def split_destination_kind(qb: QuantumBoard, square: int, to_square: int):
    """(MoveKind, captured_piece_id) for a candidate split destination, or
    (None, None) if it isn't reachable at all. Staying at ``square`` is always
    a measurement-free ``RELOCATE`` -- nothing else can be occupying it."""
    if to_square == square:
        return MoveKind.RELOCATE, None
    for m in ghost_destinations(qb, square):
        if m.to_square == to_square:
            return m.kind, m.captured_piece_id
    return None, None


def split_destination_castle_rook(qb: QuantumBoard, square: int, to_square: int
                                  ) -> Optional[tuple[int, int, int]]:
    """(rook_piece_id, rook_from, rook_to) if splitting the ghost on ``square``
    toward ``to_square`` is a castling branch, else ``None``. The rook itself
    is never split/superposed -- whoever applies the split (``apply_split`` for
    a clear path, ``collapse.resolve_split`` once a branch's own measurement
    confirms it reached the castle square) relocates it with one plain,
    deterministic move alongside that branch."""
    for m in ghost_destinations(qb, square):
        if m.to_square == to_square:
            return m.castle_rook
    return None


def mass_assignment_move(qb: QuantumBoard, piece_id: int, from_square: int,
                         to_square: int, promotion: Optional[int] = None) -> Optional[Move]:
    """The classified ``Move`` for one ghost of a mass move, or ``None`` if the
    ghost on ``from_square`` can't legally reach ``to_square``.

    ``to_square == from_square`` is a "stay" -- a measurement-free ``RELOCATE``
    onto its own square (nothing else can be there). Otherwise it's whichever
    ``ghost_destinations`` move lands on ``to_square``. When that square is a
    promotion rank the destination yields one candidate per promotion piece;
    ``promotion`` selects which (as picked in the UI), defaulting to the first
    candidate (a queen) if unspecified."""
    if to_square == from_square:
        return Move(piece_id, from_square, from_square, kind=MoveKind.RELOCATE)
    for m in ghost_destinations(qb, from_square):
        if m.to_square != to_square:
            continue
        if promotion is None or m.promotion == promotion:
            return m       # first match (queen for a promo square when unspecified)
    return None


def apply_split(qb: QuantumBoard, split: Split) -> None:
    """Split one ghost (prob p) into two ghosts of p/2 at two distinct,
    measurement-free squares (empty or same-piece merge). Raises if either
    destination would contact an enemy -- use ``collapse.resolve_split`` for
    those instead."""
    if qb.game_over:
        raise RuntimeError("game is already over")
    if split.to_a == split.to_b:
        raise ValueError("a split needs two distinct destination squares")

    source = qb.ghost_at(split.from_square)
    if source is None or source.piece_id != split.piece_id:
        raise ValueError("no such ghost to split")

    # Classify both destinations (a castle destination needs has_moved still
    # False to be recognized) *before* marking the piece moved.
    ok = {MoveKind.RELOCATE, MoveKind.MERGE}
    kind_a, _ = split_destination_kind(qb, split.from_square, split.to_a)
    kind_b, _ = split_destination_kind(qb, split.from_square, split.to_b)
    if kind_a not in ok or kind_b not in ok:
        raise ValueError("both split destinations must be legal (empty or same-piece merge); "
                         "use collapse.resolve_split for a destination that contacts an enemy")

    castle_a = split_destination_castle_rook(qb, split.from_square, split.to_a)
    castle_b = split_destination_castle_rook(qb, split.from_square, split.to_b)
    qb.pieces[split.piece_id].has_moved = True

    half = source.prob / 2
    qb.ghosts.remove(source)
    for dest in (split.to_a, split.to_b):
        existing = qb.ghost_at(dest)
        if existing is not None and existing.piece_id == split.piece_id:
            existing.prob += half                       # merge into own ghost
        else:
            qb.ghosts.append(Ghost(split.piece_id, dest, half))

    # A castle branch's rook is never superposed -- with a clear path there's
    # nothing to measure, so it just makes its own plain move right here.
    for castle_rook in (castle_a, castle_b):
        if castle_rook is not None:
            rook_pid, rook_from, rook_to = castle_rook
            qb.ghost_at(rook_from).square = rook_to
            qb.pieces[rook_pid].has_moved = True

    qb.ep_square = None
    qb.turn = not qb.turn


def remove_piece(qb: QuantumBoard, piece_id: int) -> None:
    qb.pieces[piece_id].alive = False
    qb.ghosts = [g for g in qb.ghosts if g.piece_id != piece_id]
