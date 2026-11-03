"""Design tokens for Void Vision.

The palette keeps Void Click's identity - near-black glass surfaces, a green
"go" accent and an orange "running" accent - but the surfaces are flatter and
every edge is a crisp 1px line, so the whole thing reads sharper.
"""

import sys

# Surfaces, darkest to lightest.
BG_RAIL = "#08090d"        # icon rail
BG = "#0d0f14"             # window / page background
BG_CARD = "#13161d"        # cards and panels
BG_RAISED = "#191d26"      # hovered card, inspector header
BG_FIELD = "#1d222c"       # inputs, chips, tracks
BG_FIELD_HOVER = "#242a36"

BORDER = "#232835"         # hairlines on cards
BORDER_STRONG = "#2f3644"  # hairlines on inputs

FG = "#f1f3f7"
FG_SOFT = "#c3c8d2"
FG_MUTED = "#8f97a8"     # ~6:1 on cards (WCAG AA for body text)
FG_FAINT = "#6b7385"     # ~3.6:1 - only for disabled / decorative text

GREEN = "#3ddc84"
GREEN_HOVER = "#5ae597"
GREEN_DIM = "#173a29"      # tinted background behind green text
ORANGE = "#ff9d45"
ORANGE_HOVER = "#ffb06a"
ORANGE_DIM = "#3d2814"
RED = "#ff5c6c"
RED_HOVER = "#ff7a87"
RED_DIM = "#3d171d"
BLUE = "#5aa9ff"           # informational: found-match highlights, links

TEXT_ON_ACCENT = "#06120b"

RADIUS = 6        # controls
RADIUS_CARD = 9   # cards and panels

_FONT_CANDIDATES = {
    "win32": ["Segoe UI Variable Text", "Segoe UI"],
    "darwin": ["SF Pro Text", "Helvetica Neue", "Helvetica"],
}
_FONT_FALLBACKS = ["Inter", "Cantarell", "Noto Sans", "DejaVu Sans", "Arial"]
_MONO_CANDIDATES = ["Cascadia Mono", "Consolas", "SF Mono", "Menlo",
                    "JetBrains Mono", "DejaVu Sans Mono", "Courier New"]

FAMILY = "TkDefaultFont"
MONO = "TkFixedFont"


def init(root):
    """Pick the best installed font family and set app-wide widget defaults."""
    global FAMILY, MONO
    from tkinter import font as tkfont

    installed = set(tkfont.families(root))
    candidates = _FONT_CANDIDATES.get(sys.platform, []) + _FONT_FALLBACKS
    FAMILY = next((f for f in candidates if f in installed), "TkDefaultFont")
    MONO = next((f for f in _MONO_CANDIDATES if f in installed), "TkFixedFont")

    root.configure(bg=BG)
    root.option_add("*Font", font(10))
    root.option_add("*Menu.background", BG_RAISED)
    root.option_add("*Menu.foreground", FG)
    root.option_add("*Menu.activeBackground", GREEN)
    root.option_add("*Menu.activeForeground", TEXT_ON_ACCENT)
    root.option_add("*Menu.borderWidth", 0)
    root.option_add("*Menu.activeBorderWidth", 0)
    root.option_add("*Menu.relief", "flat")


def font(size=10, weight="normal"):
    return (FAMILY, size, weight)


def mono(size=9):
    return (MONO, size)
