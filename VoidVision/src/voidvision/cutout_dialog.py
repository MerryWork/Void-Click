"""The cut-out editor: click the colour to keep, see live what is ignored."""

import tkinter as tk

from PIL import Image, ImageTk

from . import cutout, explain, theme
from . import widgets as w
from .insight import VerdictBox

VIEW_W, VIEW_H = 560, 260


class CutoutDialog(tk.Toplevel):
    """`on_done(new_image)` gets the cut-out (RGBA) or plain RGB image."""

    def __init__(self, root, image, name, on_done):
        super().__init__(root)
        self.on_done = on_done
        self.base = image.convert("RGB")          # original pixels, always
        self.keep, self.remove = [], []
        self.title(f"Cut out — {name}")
        self.configure(bg=theme.BG)
        self.resizable(False, False)
        self.transient(root)

        k = min(VIEW_W / self.base.width, VIEW_H / self.base.height)
        self.scale = max(1, int(k)) if k >= 1 else k
        self.view_size = (max(1, int(self.base.width * self.scale)),
                          max(1, int(self.base.height * self.scale)))
        self._img = None
        self.result = image if image.mode == "RGBA" else self.base

        body = tk.Frame(self, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=20, pady=18)
        w.label(body, "Cut out the background", size=14, bold=True).pack(anchor="w")
        w.label(body, "Click the part you want Void Vision to look for - for a meter or bar, "
                      "click its colour. Everything greyed out with squares is ignored when "
                      "matching, so it can change freely.", muted=True, wraplength=VIEW_W,
                justify="left").pack(anchor="w", pady=(2, 12))

        mode_row = tk.Frame(body, bg=theme.BG)
        mode_row.pack(fill="x", pady=(0, 10))
        self.mode = tk.StringVar(value="keep")
        w.label(mode_row, "Clicking will", muted=True, size=9).pack(side="left", padx=(0, 10))
        w.Segmented(mode_row, [("keep", "Keep this colour"), ("remove", "Remove this colour")],
                    self.mode).pack(side="left")

        frame = w.Card(body, padding=10, parent_bg=theme.BG)
        frame.pack(fill="x")
        self.canvas = tk.Canvas(frame.body, width=self.view_size[0], height=self.view_size[1],
                                bg=theme.BG_CARD, highlightthickness=0, cursor="crosshair")
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self._click)

        tol_row = tk.Frame(body, bg=theme.BG)
        tol_row.pack(fill="x", pady=(12, 0))
        w.label(tol_row, "Colour range", muted=True, size=9, width=13).pack(side="left")
        self.tol = tk.DoubleVar(value=30)
        w.Slider(tol_row, self.tol, 5, 120, step=1, width=260,
                 fmt=lambda v: f"±{v:.0f}",
                 on_change=lambda v: self._apply()).pack(side="left")
        w.label(tol_row, "wider keeps shades and edges too", muted=True, size=9).pack(side="left",
                                                                                padx=8)

        self.picks_row = tk.Frame(body, bg=theme.BG)
        self.picks_row.pack(fill="x", pady=(10, 0))
        self.verdict_holder = tk.Frame(body, bg=theme.BG)
        self.verdict_holder.pack(fill="x", pady=(12, 0))

        foot = tk.Frame(body, bg=theme.BG)
        foot.pack(fill="x", pady=(16, 0))
        w.Button(foot, text="Start over", icon="close", variant="ghost",
                 command=self._reset).pack(side="left")
        w.Button(foot, text="Apply", icon="check", variant="primary",
                 command=self._finish).pack(side="right")
        w.Button(foot, text="Cancel", variant="secondary",
                 command=self.destroy).pack(side="right", padx=8)
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Return>", lambda e: self._finish())

        self._render()
        self.update_idletasks()
        x = root.winfo_rootx() + (root.winfo_width() - self.winfo_width()) // 2
        y = root.winfo_rooty() + 60
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.grab_set()
        self.focus_set()

    # ------------------------------------------------------------- editing

    def _click(self, e):
        px = min(max(int(e.x / self.scale), 0), self.base.width - 1)
        py = min(max(int(e.y / self.scale), 0), self.base.height - 1)
        rgb = self.base.getpixel((px, py))[:3]
        (self.keep if self.mode.get() == "keep" else self.remove).append(rgb)
        self._apply()

    def _reset(self):
        self.keep, self.remove = [], []
        self._apply()

    def _apply(self):
        self.result = cutout.build(self.base, self.keep, self.remove, int(self.tol.get()))
        self._render()

    def _render(self):
        shown = cutout.on_checkerboard(self.result, cell=max(3, int(self.scale * 2)))
        resample = Image.NEAREST if self.scale >= 1 else Image.LANCZOS
        self._img = ImageTk.PhotoImage(shown.resize(self.view_size, resample))
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self._img, anchor="nw")

        for child in self.picks_row.winfo_children():
            child.destroy()
        if self.keep or self.remove:
            for label, colors in (("Keeping", self.keep), ("Removing", self.remove)):
                if not colors:
                    continue
                w.label(self.picks_row, label, muted=True, size=9).pack(side="left", padx=(0, 6))
                for c in colors[-8:]:
                    w.Swatch(self.picks_row, c, size=20, parent_bg=theme.BG).pack(side="left",
                                                                              padx=(0, 4))
                tk.Frame(self.picks_row, bg=theme.BG, width=12).pack(side="left")
        else:
            w.label(self.picks_row, "Nothing picked yet - click the image above.",
                    muted=True, size=9).pack(side="left")

        for child in self.verdict_holder.winfo_children():
            child.destroy()
        VerdictBox(self.verdict_holder, explain.image_quality(self.result), bg=theme.BG,
                   wrap=VIEW_W - 40).pack(fill="x")

    def _finish(self):
        result = self.result
        self.destroy()
        self.on_done(result)


def open_cutout(app, template, after=None):
    """Open the editor for a library image and save the result into it."""
    def done(image):
        template.image = image
        app.test_results.pop("tpl:" + template.id, None)
        for step in app.flow.steps:
            if step.params.get("template") == template.id:
                app.test_results.pop(step.id, None)
        app.mark_dirty()
        app.on_library_changed()
        kept = cutout.kept_fraction(image)
        app.toast("Cut-out removed" if kept >= 1.0 else f"Cut-out saved — {kept:.0%} kept",
                  "ok")
        if after:
            after()
    CutoutDialog(app, template.image, template.name, done)

