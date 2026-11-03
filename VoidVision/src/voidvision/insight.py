"""Panels that explain images and test results in words and pictures.

Status is never shown by colour alone: every verdict carries an icon (check,
warning, cross) and a written title, so it reads the same for colour-blind
users and in a screenshot pasted into a chat.
"""

import tkinter as tk

from PIL import Image, ImageTk

from . import draw, explain, icons, theme
from . import widgets as w

LEVEL_STYLE = {
    explain.GOOD: (theme.GREEN, theme.GREEN_DIM, "check"),
    explain.OK: (theme.ORANGE, theme.ORANGE_DIM, "warn"),
    explain.WEAK: (theme.RED, theme.RED_DIM, "close"),
}


def preview(image, max_w, max_h):
    """Scale a capture to fit a box; small captures grow with hard pixels."""
    from .cutout import on_checkerboard

    pic = on_checkerboard(image) if image.mode == "RGBA" else image.convert("RGB")
    k = min(max_w / pic.width, max_h / pic.height)
    if k >= 2:
        k = int(k)
        return pic.resize((pic.width * k, pic.height * k), Image.NEAREST)
    if k < 1:
        return pic.resize((max(1, int(pic.width * k)), max(1, int(pic.height * k))), Image.LANCZOS)
    return pic


class VerdictBox(tk.Frame):
    """Icon badge + bold title + one wrapped sentence."""

    def __init__(self, master, verdict, bg=theme.BG_CARD, wrap=280, compact=False):
        super().__init__(master, bg=bg)
        fg, tint, icon = LEVEL_STYLE[verdict.level]
        badge = tk.Canvas(self, width=22, height=22, bg=bg, highlightthickness=0)
        badge.pack(side="left", anchor="n", pady=(1, 0))
        draw.circle(badge, 11, 11, 22, tint, None)
        badge.create_image(11, 11, image=icons.get(icon, 14, fg, stroke=2.6))
        text = tk.Frame(self, bg=bg)
        text.pack(side="left", fill="x", expand=True, padx=(8, 0))
        w.label(text, verdict.title, bold=True, size=10, bg=bg, fg=fg).pack(anchor="w")
        if not compact:
            w.label(text, verdict.detail, size=9, bg=bg, fg=theme.FG_SOFT, wraplength=wrap,
                    justify="left").pack(anchor="w", pady=(1, 0))


class ScoreBar(tk.Canvas):
    """0-100% bar: the fill is the score, the tick is what the step needs."""

    def __init__(self, master, score, need=None, width=280, bg=theme.BG_CARD):
        super().__init__(master, width=width, height=34, bg=bg, highlightthickness=0, bd=0)
        x0, x1, y = 0, width, 8
        draw.rrect(self, x0, y, x1 - x0, 8, 4, theme.BG_FIELD_HOVER, None, bg)
        ok = need is None or score >= need
        color = theme.GREEN if ok else (theme.ORANGE if score >= (need or 0) - 0.12 else theme.RED)
        fill_w = max(0.0, min(score, 1.0)) * (x1 - x0)
        if fill_w > 2:
            draw.rrect(self, x0, y, fill_w, 8, 4, color, None, theme.BG_FIELD_HOVER)
        self.create_text(x0, 27, text=f"Similarity {score:.0%}", anchor="w", fill=theme.FG,
                         font=theme.font(9, "bold"))
        if need is not None:
            nx = x0 + need * (x1 - x0)
            self.create_line(nx, y - 3, nx, y + 11, fill=theme.FG, width=2)
            self.create_text(x1, 27, text=f"needs {need:.0%}", anchor="e", fill=theme.FG_MUTED,
                             font=theme.font(9))


class ComparePanel(tk.Frame):
    """'Your image' beside 'Closest on screen', plus the score and verdict."""

    def __init__(self, master, template_image, result, bg=theme.BG_CARD, width=300):
        super().__init__(master, bg=bg)
        self._imgs = []
        p = result.probe
        w.section(self, "Last test", bg=bg).pack(anchor="w", pady=(0, 6))
        # The answer first, then the evidence.
        VerdictBox(self, result.verdict, bg=bg, wrap=width - 34).pack(fill="x", pady=(0, 10))
        pics = tk.Frame(self, bg=bg)
        pics.pack(fill="x")
        half = (width - 12) // 2
        self._pic(pics, "Your image", template_image, half, bg).pack(side="left")
        if p.closest is not None:
            label = "Found on screen" if p.hit is not None else "Closest on screen"
            self._pic(pics, label, p.closest, half, bg).pack(side="right")
        else:
            self._pic(pics, "On screen", None, half, bg).pack(side="right")
        if result.confidence is not None:
            ScoreBar(self, p.score, result.confidence, width=width, bg=bg).pack(anchor="w",
                                                                              pady=(8, 0))

    def _pic(self, parent, caption, image, width, bg):
        f = tk.Frame(parent, bg=bg)
        c = tk.Canvas(f, width=width, height=64, bg=bg, highlightthickness=0)
        c.pack()
        draw.rrect(c, 0, 0, width, 64, 6, theme.BG_FIELD, theme.BORDER_STRONG, bg)
        if image is not None:
            img = ImageTk.PhotoImage(preview(image, width - 12, 54))
            self._imgs.append(img)
            c.create_image(width / 2, 32, image=img)
        else:
            c.create_text(width / 2, 32, text="nothing", fill=theme.FG_MUTED, font=theme.font(9))
        w.label(f, caption, muted=True, size=8, bg=bg).pack(anchor="w", pady=(3, 0))
        return f


class QualityLine(tk.Frame):
    """Compact 'is this a good image?' line shown under a capture."""

    def __init__(self, master, image, bg=theme.BG_CARD, wrap=280):
        super().__init__(master, bg=bg)
        verdict = explain.image_quality(image)
        VerdictBox(self, verdict, bg=bg, wrap=wrap,
                   compact=verdict.level == explain.GOOD).pack(fill="x")
