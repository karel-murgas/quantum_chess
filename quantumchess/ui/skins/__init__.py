"""UI skins -- swappable drawing languages for the board + panel (design
history in docs/HISTORY.md).

**Quantum HUD** and **Clarity / Data-viz** are the two views a player can switch
between during a real match. ``App`` (see ``ui/app.py``) owns one instance of
each permanently -- there is no "skin is None" classic fallback; the game always
renders through one of these two.

``build_skins()`` constructs one instance of each (fonts are built in
``__init__``, so call it only after ``pygame.font`` is ready). ``SKIN_CLASSES``
fixes the cycle order (index 0 is the default view a new game boots into).
"""

from .base import BaseSkin
from .hud import HudSkin
from .clarity import ClaritySkin

SKIN_CLASSES = [ClaritySkin, HudSkin]


def build_skins():
    return [cls() for cls in SKIN_CLASSES]


__all__ = ["BaseSkin", "HudSkin", "ClaritySkin", "SKIN_CLASSES", "build_skins"]
