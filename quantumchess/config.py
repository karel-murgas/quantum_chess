"""Match-setup configuration — the v1 dials (see PLAN.md).

Kept in its own module (not game.py) so both game.py and collapse.py can import
it without a circular dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CollapseMode(Enum):
    """What happens to a piece's remaining ghosts on a *negative* measurement."""
    PARTIAL = "partial"   # only the contacted ghost vanishes; the rest renormalize
    FULL = "full"         # resolve the whole piece to one location; drop the rest


@dataclass
class GameConfig:
    collapse_mode: CollapseMode = CollapseMode.FULL
    splitting_enabled: bool = True
    mass_movement: bool = False        # allow moving *all* of a piece's ghosts in one planned turn
    seed: Optional[int] = None
    theme: str = "origin"              # "origin" | "cyberpunk"
    white_name: str = "White"
    black_name: str = "Black"
    white_color: tuple[int, int, int] = (240, 200, 90)
    black_color: tuple[int, int, int] = (90, 150, 230)

    def team_name(self, color: bool) -> str:
        """`color` is a python-chess colour bool (True == white)."""
        return self.white_name if color else self.black_name

    def team_color(self, color: bool) -> tuple[int, int, int]:
        return self.white_color if color else self.black_color
