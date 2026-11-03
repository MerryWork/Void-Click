"""Images page: the flow's library of captured images."""

import tkinter as tk
from tkinter import filedialog

from PIL import Image, ImageTk

from . import draw, icons, theme
from . import widgets as w
from .page_flow import preview

TILE_W, TILE_H = 150, 150
COLS = 3


class Tile(tk.Canvas):
    def __init__(self, master, page, template):
        super().__init__(master, width=TILE_W, height=TILE_H, bg=theme.BG, highlightthickness=0,
                         bd=0, cursor="hand2")
        self.page, self.template = page, template
        self.selected = self.hover = False
        self._img = None
        self.bind("<Enter>", lambda e: self._h(True))
        self.bind("<Leave>", lambda e: self._h(False))
        self.bind("<Button-1>", lambda e: page.select(template))
        self.redraw()

    def _h(self, v):
        self.hover = v
        self.redraw()

    def redraw(self):
        self.delete("all")
        t = self.template
        fill = theme.BG_RAISED if (self.hover or self.selected) else theme.BG_CARD
        draw.rrect(self, 0, 0, TILE_W, TILE_H, theme.RADIUS_CARD, fill,
                   theme.GREEN if self.selected else theme.BORDER, theme.BG)
        draw.rrect(self, 8, 8, TILE_W - 16, 96, 6, theme.BG_FIELD, None, fill)
        self._img = ImageTk.PhotoImage(preview(t.image, TILE_W - 28, 84))
        self.create_image(TILE_W / 2, 56, image=self._img)
        self.create_text(12, 118, text=t.name, anchor="w", fill=theme.FG,
                         font=theme.font(10, "bold"), width=TILE_W - 20)
        uses = self.page.app.flow.usage(t.id)
        meta = f"{t.size[0]}×{t.size[1]}  ·  " + (f"used {uses}×" if uses else "unused")
        self.create_text(12, 136, text=meta, anchor="w", fill=theme.FG_MUTED, font=theme.font(8))


class ImagesPage(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=theme.BG)
        self.app = app
        self.selected = None
        self.tiles = []
        self._preview = None
        self._build()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        head = tk.Frame(self, bg=theme.BG)
        head.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 16))
        head.columnconfigure(0, weight=1)
        t = tk.Frame(head, bg=theme.BG)
        t.grid(row=0, column=0, sticky="w")
        w.label(t, "Images", size=18, bold=True).pack(anchor="w")
        self.subtitle = w.label(t, "", muted=True)
        self.subtitle.pack(anchor="w")
        a = tk.Frame(head, bg=theme.BG)
        a.grid(row=0, column=1, sticky="e")
        w.Button(a, text="Import", icon="folder", variant="secondary", height=36,
                 command=self._import).pack(side="left", padx=(0, 8))
        w.Button(a, text="Capture", icon="crosshair", variant="primary", height=36,
                 command=self._capture).pack(side="left")

        body = tk.Frame(self, bg=theme.BG)
        body.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 18))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.scroll = w.ScrollFrame(body)
        self.scroll.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        self.grid_frame = self.scroll.interior
        self.detail = w.Card(body, padding=16, parent_bg=theme.BG, width=300).fixed()
        self.detail.grid(row=0, column=1, sticky="nsew")

    def refresh(self):
        flow = self.app.flow
        for tile in self.tiles:
            tile.destroy()
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self.tiles = []
        if self.selected is not None and self.selected.id not in flow.templates:
            self.selected = None
        templates = list(flow.templates.values())
        if self.selected is None and templates:
            self.selected = templates[0]
        if not templates:
            e = tk.Frame(self.grid_frame, bg=theme.BG)
            e.pack(fill="both", expand=True, pady=50)
            c = tk.Canvas(e, width=64, height=64, bg=theme.BG, highlightthickness=0)
            c.pack()
            draw.rrect(c, 0, 0, 64, 64, 16, theme.BG_CARD, theme.BORDER, theme.BG)
            c.create_image(32, 32, image=icons.get("images", 30, theme.GREEN))
            w.label(e, "No images yet", size=12, bold=True, anchor="center").pack(pady=(14, 2))
            w.label(e, "Capture a button, icon or word from the screen, then use it in\n"
                       "Find & click, Wait for image or If visible steps.", muted=True,
                    justify="center", anchor="center").pack()
        for i, t in enumerate(templates):
            tile = Tile(self.grid_frame, self, t)
            tile.selected = t is self.selected
            tile.redraw()
            tile.grid(row=i // COLS, column=i % COLS, padx=(0, 10), pady=(0, 10), sticky="nw")
            self.tiles.append(tile)
        n = len(templates)
        self.subtitle.configure(text=f"{n} image{'s' if n != 1 else ''} in {flow.name}"
                                     "  ·  saved inside the flow file")
        self._show_detail()

    def select(self, template):
        self.selected = template
        for tile in self.tiles:
            tile.selected = tile.template is template
            tile.redraw()
        self._show_detail()

    def _show_detail(self):
        b = self.detail.body
        for child in b.winfo_children():
            child.destroy()
        t = self.selected
        bg = theme.BG_CARD
        if t is None:
            w.label(b, "Nothing selected", bold=True, bg=bg).pack(anchor="w")
            return
        pv = tk.Canvas(b, width=268, height=170, bg=bg, highlightthickness=0)
        pv.pack()
        draw.rrect(pv, 0, 0, 268, 170, 8, theme.BG_FIELD, theme.BORDER_STRONG, bg)
        self._preview = ImageTk.PhotoImage(preview(t.image, 250, 150))
        pv.create_image(134, 85, image=self._preview)

        w.section(b, "Name", bg=bg).pack(anchor="w", pady=(16, 4))
        name = tk.StringVar(value=t.name)

        def rename():
            v = name.get().strip() or t.name
            name.set(v)
            if v != t.name:
                t.name = v
                self.app.mark_dirty()
                self.app.on_library_changed()

        w.Entry(b, name, width=24, on_commit=rename, parent_bg=bg).pack(fill="x")
        uses = self.app.flow.usage(t.id)
        w.label(b, f"{t.size[0]} × {t.size[1]} px  ·  used by {uses} step"
                   f"{'s' if uses != 1 else ''}", muted=True, size=9, bg=bg).pack(anchor="w",
                                                                                  pady=(10, 0))
        btns = tk.Frame(b, bg=bg)
        btns.pack(fill="x", pady=(16, 0))
        w.Button(btns, text="Find on screen", icon="eye", variant="secondary", parent_bg=bg,
                 command=lambda: self.app.test_template(t)).pack(side="left")
        w.Button(btns, text="Recapture", icon="crosshair", variant="ghost", parent_bg=bg,
                 command=lambda: self._recapture(t)).pack(side="left", padx=6)
        w.Button(b, text="Delete image", icon="trash", variant="danger", parent_bg=bg,
                 command=lambda: self._delete(t)).pack(anchor="w", pady=(10, 0))

    def _capture(self):
        def done(image):
            if image is not None:
                self.selected = self.app.flow.add_template(image)
                self.app.mark_dirty()
                self.app.on_library_changed()
        self.app.capture("image", done)

    def _recapture(self, t):
        def done(image):
            if image is not None:
                t.image = image.convert("RGB")
                self.app.mark_dirty()
                self.app.on_library_changed()
        self.app.capture("image", done)

    def _delete(self, t):
        uses = self.app.flow.usage(t.id)
        if uses and not self.app.confirm(
                "Delete image", f"'{t.name}' is used by {uses} step(s). Delete it anyway?"):
            return
        self.app.flow.remove_template(t.id)
        self.selected = None
        self.app.mark_dirty()
        self.app.on_library_changed()

    def _import(self):
        paths = filedialog.askopenfilenames(
            title="Import images", parent=self,
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif"), ("All files", "*.*")])
        added = 0
        for path in paths:
            try:
                img = Image.open(path)
                img.load()
            except Exception:
                self.app.toast(f"Couldn't read {path}", "error")
                continue
            import os

            self.selected = self.app.flow.add_template(img, os.path.splitext(os.path.basename(path))[0])
            added += 1
        if added:
            self.app.mark_dirty()
            self.app.on_library_changed()
            self.app.toast(f"Imported {added} image{'s' if added != 1 else ''}", "ok")
