"""A redrawn timing bar to practise against and to test Hit the spot steps.

A clean white track with ticks, a red block marking the spot and a thin
black marker sweeping back and forth across it. Press any key while it has focus and it reports how close the
press was - exactly what a "Hit the spot" step should achieve in a game.
"""

import random
import time
import tkinter as tk

from . import theme
from . import widgets as w

BAR_W, BAR_H = 520, 72
TRACK_Y = 36
MARKER = (0, 0, 0)        # the moving line
SPOT = (215, 7, 7)        # the block to hit
SPEEDS = {"slow": 0.35, "medium": 0.7, "fast": 1.3}    # bar widths per second


def _hex(rgb):
    return "#%02x%02x%02x" % rgb


class PracticeBar(tk.Toplevel):
    def __init__(self, app, on_use=None):
        super().__init__(app)
        self.app, self.on_use = app, on_use
        self.title("Practice bar — Void Vision")
        self.configure(bg=theme.BG)
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.pos, self.dir = 0.0, 1
        self.shown, self.shown_dir = 0.0, 1    # the marker as last drawn on screen
        self.stutter = 0.0                     # longest gap between redraws lately
        self.zone = [0.62, 0.67]
        self.hits = self.tries = 0
        self._last = time.perf_counter()

        body = tk.Frame(self, bg=theme.BG)
        body.pack(padx=18, pady=16)
        w.label(body, "Practice bar", size=13, bold=True).pack(anchor="w")
        w.label(body, "Press any key when the black line is on the red block - or let a "
                      "Hit the spot step do it. Keep this window focused so it hears the key.",
                muted=True, size=9, wraplength=BAR_W, justify="left").pack(anchor="w",
                                                                         pady=(2, 10))
        # The bar sits on its own plain background, like a game HUD would.
        self.canvas = tk.Canvas(body, width=BAR_W, height=BAR_H, bg="#d1d8e5",
                                highlightthickness=0, bd=0)
        self.canvas.pack()
        self.result = w.label(body, "Waiting for a press…", bold=True, size=11)
        self.result.pack(anchor="w", pady=(10, 0))
        self.score = w.label(body, "", muted=True, size=9)
        self.score.pack(anchor="w")

        row = tk.Frame(body, bg=theme.BG)
        row.pack(fill="x", pady=(12, 0))
        self.speed = tk.StringVar(value="medium")
        w.Segmented(row, [("slow", "Slow"), ("medium", "Medium"), ("fast", "Fast")],
                    self.speed).pack(side="left")
        self.moving = tk.BooleanVar(value=False)
        w.Toggle(row, "Spot moves each round", self.moving).pack(side="left", padx=14)
        if on_use:
            w.Button(row, text="Use for my step", icon="check", variant="primary",
                     command=self._use).pack(side="right")

        self.bind("<KeyPress>", self._key)
        self.after(16, self._tick)
        self.focus_force()

    # ------------------------------------------------------------- drawing

    def _draw(self):
        c = self.canvas
        c.delete("all")
        x0, x1 = 16, BAR_W - 16
        span = x1 - x0
        # White track with ticks: tall ones at the ends, short ones between.
        c.create_rectangle(x0, TRACK_Y - 2, x1, TRACK_Y + 2, fill="white", outline="")
        for i in range(11):
            tx = x0 + span * i / 10
            tall = 20 if i in (0, 10) else 12
            c.create_rectangle(tx - 2, TRACK_Y - tall, tx + 2, TRACK_Y + tall, fill="white",
                               outline="")
        # The spot: a red block sitting on the track.
        zx0, zx1 = x0 + self.zone[0] * span, x0 + self.zone[1] * span
        c.create_rectangle(zx0, TRACK_Y - 14, zx1, TRACK_Y + 14, fill=_hex(SPOT), outline="")
        # The marker: a thin black line, taller than everything else.
        self.shown, self.shown_dir = self.pos, self.dir
        mx = x0 + self.pos * span
        c.create_rectangle(mx - 2, TRACK_Y - 28, mx + 2, TRACK_Y + 28, fill=_hex(MARKER),
                           outline="")

    def _tick(self):
        if not self.winfo_exists():
            return
        now = time.perf_counter()
        dt, self._last = now - self._last, now
        self.stutter = max(self.stutter * 0.9, dt)
        self.pos += self.dir * SPEEDS[self.speed.get()] * dt
        if self.pos >= 1.0:
            self.pos, self.dir = 1.0, -1
        elif self.pos <= 0.0:
            self.pos, self.dir = 0.0, 1
        self._draw()
        self.after(8, self._tick)

    # ------------------------------------------------------------- input

    def _key(self, _e):
        # Judged on the marker as it was last drawn - what anyone pressing
        # the key could actually see - not on where it would be by now.
        self.tries += 1
        lo, hi = self.zone
        centre = (lo + hi) / 2.0
        speed = SPEEDS[self.speed.get()]
        pos, direction = self.shown, self.shown_dir
        off_ms = (pos - centre) / speed * 1000 * direction   # + late, - early
        if lo <= pos <= hi:
            self.hits += 1
            self.result.configure(text=f"Hit — {abs(off_ms):.0f} ms from the centre",
                                  fg=theme.GREEN)
        else:
            when = "late" if off_ms > 0 else "early"
            self.result.configure(text=f"Miss — {abs(off_ms):.0f} ms {when}", fg=theme.RED)
        note = ("  \u00b7  this window stuttered (%d ms between frames)" % (self.stutter * 1000)
                if self.stutter > 0.05 else "")
        self.score.configure(text=f"{self.hits} of {self.tries} on the spot{note}")
        if self.moving.get():
            width = self.zone[1] - self.zone[0]
            start = random.uniform(0.1, 0.9 - width)
            self.zone = [start, start + width]

    def bar_area(self):
        """The bar's screen rectangle, for a step's Bar area."""
        c = self.canvas
        return [c.winfo_rootx(), c.winfo_rooty(), BAR_W, BAR_H]

    def zone_fraction(self):
        """The spot as fractions of the whole bar area (not just the track)."""
        x0, span = 16, BAR_W - 32
        return [(x0 + self.zone[0] * span) / (BAR_W - 1), (x0 + self.zone[1] * span) / (BAR_W - 1)]

    def _use(self):
        if self.on_use:
            self.on_use(self)
