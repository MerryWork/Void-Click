"""Full-screen capture overlay and on-screen match highlights.

The overlay freezes a screenshot, dims it, and lets you drag out a rectangle
(to capture an image or a search area) or click a pixel (to pick a colour).
Because the selection is made on the frozen screenshot, hover effects and
menus that would vanish when the mouse moves can still be captured.
"""

import tkinter as tk

from PIL import Image, ImageEnhance, ImageTk

from . import theme

MODE_IMAGE = "image"
MODE_REGION = "region"
MODE_COLOR = "color"

_HINTS = {
    MODE_IMAGE: "Drag around what to find  ·  Esc to cancel",
    MODE_REGION: "Drag out the area to search in  ·  Esc to cancel",
    MODE_COLOR: "Click the colour to look for  ·  Esc to cancel",
}


class CaptureOverlay(tk.Toplevel):
    """`on_done(result)` gets a PIL image, a region tuple, an (r,g,b) or None."""

    def __init__(self, root, shot, mode, on_done):
        super().__init__(root)
        self.shot, self.mode, self.on_done = shot, mode, on_done
        self._finished = False
        left, top = int(shot.left), int(shot.top)
        sw, sh = shot.size_on_screen(shot.image.width, shot.image.height)
        self.sw, self.sh = int(round(sw)), int(round(sh))

        self.overrideredirect(True)
        self.geometry(f"{self.sw}x{self.sh}+{left}+{top}")
        self.attributes("-topmost", True)
        self.configure(bg="black", cursor="crosshair")

        display = shot.image
        if display.size != (self.sw, self.sh):
            display = display.resize((self.sw, self.sh), Image.LANCZOS)
        self._bright = display
        self._dim_img = ImageTk.PhotoImage(ImageEnhance.Brightness(display).enhance(0.45))
        self._crop_img = None

        c = self.canvas = tk.Canvas(self, width=self.sw, height=self.sh, highlightthickness=0,
                                    bd=0, bg="black")
        c.pack()
        c.create_image(0, 0, image=self._dim_img, anchor="nw")
        self._hint()
        self._start = None
        c.bind("<ButtonPress-1>", self._press)
        c.bind("<B1-Motion>", self._drag)
        c.bind("<ButtonRelease-1>", self._release)
        c.bind("<Motion>", self._motion)
        self.bind("<Escape>", lambda e: self._finish(None))
        self.bind("<Button-3>", lambda e: self._finish(None))
        self.after(30, self._focus)

    def _focus(self):
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _hint(self):
        c = self.canvas
        text = _HINTS[self.mode]
        x = self.sw / 2
        c.create_rectangle(x - 230, 18, x + 230, 52, fill=theme.BG_RAISED, outline=theme.GREEN,
                           tags="hint")
        c.create_text(x, 35, text=text, fill=theme.FG, font=theme.font(11, "bold"), tags="hint")

    # ------------------------------------------------------------- selection

    def _press(self, e):
        if self.mode == MODE_COLOR:
            self._finish(self._pixel(e.x, e.y))
            return
        self._start = (e.x, e.y)

    def _drag(self, e):
        if not self._start:
            return
        c = self.canvas
        c.delete("sel")
        x0, y0 = self._start
        x1, y1 = e.x, e.y
        l, t, r, b = min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)
        if r - l >= 2 and b - t >= 2:
            self._crop_img = ImageTk.PhotoImage(self._bright.crop((l, t, r, b)))
            c.create_image(l, t, image=self._crop_img, anchor="nw", tags="sel")
        color = theme.GREEN if self.mode == MODE_IMAGE else theme.BLUE
        c.create_rectangle(l, t, r, b, outline=color, width=2, tags="sel")
        px_w, px_h = self._to_pixels(r - l, b - t)
        c.create_text(l, b + 8, anchor="nw", text=f"{px_w} × {px_h}", fill=color,
                      font=theme.font(10, "bold"), tags="sel")
        c.tag_raise("hint")

    def _release(self, e):
        if not self._start:
            return
        x0, y0 = self._start
        l, t, r, b = min(x0, e.x), min(y0, e.y), max(x0, e.x), max(y0, e.y)
        self._start = None
        if r - l < 4 or b - t < 4:
            self.canvas.delete("sel")
            return
        if self.mode == MODE_REGION:
            self._finish((int(self.shot.left + l), int(self.shot.top + t), int(r - l), int(b - t)))
        else:
            s = self.shot.scale
            box = (int(l * s), int(t * s), int(r * s), int(b * s))
            self._finish(self.shot.image.crop(box))

    def _motion(self, e):
        if self.mode != MODE_COLOR:
            return
        c = self.canvas
        c.delete("loupe")
        rgb = self._pixel(e.x, e.y)
        hexc = "#%02x%02x%02x" % rgb
        x, y = e.x + 18, e.y + 18
        c.create_rectangle(x, y, x + 132, y + 34, fill=theme.BG_RAISED, outline=theme.BORDER_STRONG,
                           tags="loupe")
        c.create_rectangle(x + 6, y + 6, x + 28, y + 28, fill=hexc, outline=theme.FG, tags="loupe")
        c.create_text(x + 36, y + 17, text=hexc.upper(), anchor="w", fill=theme.FG,
                      font=theme.mono(10), tags="loupe")

    def _pixel(self, x, y):
        s = self.shot.scale
        px = min(max(int(x * s), 0), self.shot.image.width - 1)
        py = min(max(int(y * s), 0), self.shot.image.height - 1)
        return tuple(self.shot.image.getpixel((px, py))[:3])

    def _to_pixels(self, w, h):
        s = self.shot.scale
        return int(w * s), int(h * s)

    def _finish(self, result):
        if self._finished:
            return
        self._finished = True
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
        self.on_done(result)


class Highlight:
    """A bright frame around a screen rectangle that fades out on its own."""

    def __init__(self, root, x, y, w, h, text="", color=theme.GREEN, ms=1400):
        self.parts = []
        pad, t = 4, 3
        x, y, w, h = int(x) - pad, int(y) - pad, int(w) + 2 * pad, int(h) + 2 * pad
        for gx, gy, gw, gh in ((x, y, w, t), (x, y + h - t, w, t), (x, y, t, h), (x + w - t, y, t, h)):
            self.parts.append(self._strip(root, gx, gy, gw, gh, color))
        if text:
            tag = tk.Toplevel(root)
            tag.overrideredirect(True)
            tag.attributes("-topmost", True)
            tk.Label(tag, text=text, bg=color, fg=theme.TEXT_ON_ACCENT, font=theme.font(9, "bold"),
                     padx=6, pady=2).pack()
            tag.geometry(f"+{x}+{max(0, y - 24)}")
            self.parts.append(tag)
        root.after(ms, self.close)

    @staticmethod
    def _strip(root, x, y, w, h, color):
        win = tk.Toplevel(root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=color)
        win.geometry(f"{max(w, 1)}x{max(h, 1)}+{x}+{y}")
        return win

    def close(self):
        for p in self.parts:
            try:
                p.destroy()
            except tk.TclError:
                pass
        self.parts = []
