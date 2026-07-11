"""Core headless data model for Quantum Chess.

This module is deliberately free of any UI / pygame imports so the engine can be
unit-tested in isolation and later reused by any frontend (see PLAN.md).

Milestone 1 scope: every living piece is *solid* — it owns exactly one ghost
with probability 1, so the position is equivalent to a classical chess board.
The types below (Piece / Ghost / probabilities as ``Fraction``) already carry
the structure the quantum layer will need in later milestones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Optional

import chess

# We reuse python-chess constants throughout for zero-friction interop:
#   colours : chess.WHITE (True) / chess.BLACK (False)
#   types   : chess.PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING
#   squares : ints 0..63 (a1=0 .. h8=63); chess.square_name() to display


@dataclass
class Piece:
    """A single chess piece with a stable identity.

    The identity matters once the piece splits: every ghost points back to the
    same ``id``, and a piece is only ever in superposition *with its own ghosts*
    (there is no cross-piece entanglement — see PLAN.md).
    """

    id: int
    color: bool          # chess.WHITE / chess.BLACK
    ptype: int           # chess.PAWN .. chess.KING (mutable: promotion)
    alive: bool = True
    has_moved: bool = False   # any move or split, ever -- disqualifies future castling


@dataclass
class Ghost:
    """One possible location of a piece, carrying its probability mass."""

    piece_id: int
    square: int                       # 0..63
    prob: Fraction = field(default_factory=lambda: Fraction(1))


class QuantumBoard:
    """Mutable game state: pieces, their ghosts, and turn bookkeeping.

    Invariant (per living piece): the probabilities of its ghosts sum to 1.
    In Milestone 1 that trivially holds because each piece has a single p=1 ghost.
    """

    def __init__(self) -> None:
        self.pieces: dict[int, Piece] = {}
        self.ghosts: list[Ghost] = []
        self.turn: bool = chess.WHITE
        self.ep_square: Optional[int] = None   # en-passant target square, if any
        self.winner: Optional[bool] = None     # set when a king is captured
        self.game_over: bool = False
        self._next_id: int = 0

    # ------------------------------------------------------------------ setup
    @classmethod
    def standard_setup(cls) -> "QuantumBoard":
        """Build the standard chess opening position, all pieces solid."""
        qb = cls()
        start = chess.Board()  # standard start position
        for square, piece in start.piece_map().items():
            qb._add_piece(piece.color, piece.piece_type, square)
        qb.turn = chess.WHITE
        return qb

    def _add_piece(self, color: bool, ptype: int, square: int) -> Piece:
        piece = Piece(id=self._next_id, color=color, ptype=ptype)
        self._next_id += 1
        self.pieces[piece.id] = piece
        self.ghosts.append(Ghost(piece_id=piece.id, square=square, prob=Fraction(1)))
        return piece

    # -------------------------------------------------------------- accessors
    def ghosts_of(self, piece_id: int) -> list[Ghost]:
        return [g for g in self.ghosts if g.piece_id == piece_id]

    def is_solid(self, piece_id: int) -> bool:
        gs = self.ghosts_of(piece_id)
        return len(gs) == 1 and gs[0].prob == 1

    def ghost_at(self, square: int) -> Optional[Ghost]:
        """Return a ghost occupying ``square`` (unique while all pieces solid)."""
        for g in self.ghosts:
            if g.square == square:
                return g
        return None

    def piece_id_at(self, square: int) -> Optional[int]:
        g = self.ghost_at(square)
        return g.piece_id if g is not None else None

    def solid_square(self, piece_id: int) -> int:
        gs = self.ghosts_of(piece_id)
        assert len(gs) == 1, "solid_square() called on a superposed piece"
        return gs[0].square

    def living_pieces(self, color: Optional[bool] = None) -> list[Piece]:
        return [
            p for p in self.pieces.values()
            if p.alive and (color is None or p.color == color)
        ]

    # ----------------------------------------------------------- classical view
    def to_classical_board(self) -> chess.Board:
        """Project the current (all-solid) position onto a python-chess board.

        Used as a movement oracle and for ASCII rendering in Milestone 1. Asserts
        that every living piece is solid; the quantum layer will replace callers
        of this with occupancy that understands ghosts.
        """
        board = chess.Board.empty()
        for piece in self.living_pieces():
            assert self.is_solid(piece.id), "to_classical_board() needs solid pieces"
            board.set_piece_at(
                self.solid_square(piece.id),
                chess.Piece(piece.ptype, piece.color),
            )
        board.turn = self.turn
        board.ep_square = self.ep_square
        # Castling rights are intentionally cleared: Milestone 1 omits castling
        # (variant has no check, so castling is added as a simple special-case
        # in a later milestone — see PLAN.md).
        board.castling_rights = chess.BB_EMPTY
        return board

    def ascii(self) -> str:
        """Human-readable board (uppercase = White). Solid position only."""
        return str(self.to_classical_board())
