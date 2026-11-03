"""Canvas-drawn controls in the Void Vision style.

Plain tk/ttk widgets can't do rounded corners, hairline borders or hover
states that match, so the visible controls are drawn here. Shapes come from
draw.py (Pillow, anti-aliased); text stays native Tk text so it renders with
the platform's own font smoothing.
"""

import sys
import tkinter as tk

from . import draw, hotkeys, icons, theme

_VARIANTS = {
    #           fill               hover                  fg                    outline              sheen
    "primary": (theme.GREEN, theme.GREEN_HOVER, theme.TEXT_ON_ACCENT, None, 1.0),
    "running": (theme.ORANGE, theme.ORANGE_HOVER, theme.TEXT_ON_ACCENT, None, 1.0),
    "secondary": (theme.BG_FIELD, theme.BG_FIELD_HOVER, theme.FG, theme.BORDER_STRONG, 0.0),
    "ghost": (None, theme.BG_FIELD, theme.FG_SOFT, None, 0.0),
    "danger": (theme.RED_DIM, "#4d1d24", theme.RED, None, 0.0),
    "chip": (theme.BG_FIELD, theme.GREEN_DIM, theme.FG_SOFT, theme.BORDER, 0.0),
}


def _parent_bg(master, default=theme.BG):
    try:
        return master.cget("bg")
    except tk.TclError:
        return default


class Button(tk.Canvas):
    def __init__(self, master, text="", command=None, variant="secondary", icon=None,
                 width=None, height=32, font=None, parent_bg=None, icon_size=16,
                 tooltip=None, **kw):
        self.parent_bg = parent_bg or _parent_bg(master)
        self.text = text
        self.command = command
        self.variant = variant
        self.icon_name = icon
        self.icon_size = icon_size
        self.font = font or theme.font(10, "bold" if variant in ("primary", "running") else "normal")
        self._fixed_width = width
        self._hover = self._pressed = False
        self._enabled = True
        super().__init__(master, width=width or self._natural_width(), height=height,
                         bg=self.parent_bg, highlightthickness=0, bd=0, **kw)
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._down)
        self.bind("<ButtonRelease-1>", self._up)
        if tooltip:
            Tooltip(self, tooltip)
        self._draw()

    def _natural_width(self):
        from tkinter import font as tkfont

        w = 0
        if self.text:
            w += tkfont.Font(font=self.font).measure(self.text) + 24
        if self.icon_name:
            w += self.icon_size + (8 if self.text else 16)
        return max(w, 32)

    def _colors(self):
        fill, hover, fg, outline, sheen = _VARIANTS[self.variant]
        fill = fill or self.parent_bg
        if not self._enabled:
            return fill, theme.FG_FAINT, outline, sheen
        if self._pressed:
            return draw.darken(hover, 0.08), fg, outline, sheen
        if self._hover:
            return hover, fg, outline, sheen
        return fill, fg, outline, sheen

    def _draw(self):
        self.delete("all")
        w, h = max(self.winfo_width(), 2), max(self.winfo_height(), 2)
        if w <= 2:
            w = int(self["width"])
        fill, fg, outline, sheen = self._colors()
        draw.rrect(self, 0, 0, w, h, theme.RADIUS, fill, outline, self.parent_bg, sheen)
        content_w = 0
        from tkinter import font as tkfont

        tw = tkfont.Font(font=self.font).measure(self.text) if self.text else 0
        if self.icon_name:
            content_w += self.icon_size + (8 if self.text else 0)
        content_w += tw
        x = (w - content_w) / 2
        if self.icon_name:
            img = icons.get(self.icon_name, self.icon_size, fg)
            self.create_image(x, h / 2, image=img, anchor="w")
            x += self.icon_size + 8
        if self.text:
            self.create_text(x, h / 2, text=self.text, fill=fg, font=self.font, anchor="w")

    def _enter(self, _e):
        self._hover = True
        if self._enabled:
            self.configure(cursor="hand2")
        self._draw()

    def _leave(self, _e):
        self._hover = self._pressed = False
        self.configure(cursor="")
        self._draw()

    def _down(self, _e):
        if self._enabled:
            self._pressed = True
            self._draw()

    def _up(self, e):
        was = self._pressed
        self._pressed = False
        self._draw()
        inside = 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height()
        if was and inside and self._enabled and self.command:
            self.command()

    def configure_button(self, text=None, variant=None, icon=None, enabled=None):
        if text is not None:
            self.text = text
        if variant is not None:
            self.variant = variant
            self.font = theme.font(10, "bold" if variant in ("primary", "running") else "normal")
        if icon is not None:
            self.icon_name = icon or None
        if enabled is not None:
            self._enabled = enabled
        if self._fixed_width is None:
            self.configure(width=self._natural_width())
        self._draw()


class Toggle(tk.Frame):
    """Pill switch with a label to its right."""

    def __init__(self, master, text, variable, command=None, parent_bg=None):
        bg = parent_bg or _parent_bg(master)
        super().__init__(master, bg=bg)
        self.var, self.command, self.bg = variable, command, bg
        self.canvas = tk.Canvas(self, width=34, height=20, bg=bg, highlightthickness=0, bd=0,
                                cursor="hand2")
        self.canvas.pack(side="left")
        self.label = tk.Label(self, text=text, bg=bg, fg=theme.FG_SOFT, font=theme.font(10),
                              cursor="hand2")
        if text:
            self.label.pack(side="left", padx=(10, 0))
        for w in (self.canvas, self.label):
            w.bind("<Button-1>", self._flip)
        self.var.trace_add("write", lambda *a: self.refresh())
        self.refresh()

    def _flip(self, _e=None):
        self.var.set(not self.var.get())
        if self.command:
            self.command()

    def refresh(self):
        c = self.canvas
        c.delete("all")
        on = bool(self.var.get())
        draw.rrect(c, 0, 0, 34, 20, 10, theme.GREEN if on else theme.BG_FIELD,
                   None if on else theme.BORDER_STRONG, self.bg, 0.8 if on else 0)
        knob = theme.TEXT_ON_ACCENT if on else theme.FG_MUTED
        draw.circle(c, 24 if on else 10, 10, 14, knob, None)


class Entry(tk.Frame):
    """Rounded single-line field. `on_commit` runs on Return and focus-out."""

    def __init__(self, master, variable, width=10, on_commit=None, parent_bg=None, height=30,
                 font=None, justify="left"):
        bg = parent_bg or _parent_bg(master)
        super().__init__(master, bg=bg)
        self.bg, self.height, self._focus = bg, height, False
        self.canvas = tk.Canvas(self, height=height, bg=bg, highlightthickness=0, bd=0)
        self.canvas.pack(fill="x", expand=True)
        self.entry = tk.Entry(self.canvas, textvariable=variable, width=width, bd=0,
                              relief="flat", highlightthickness=0, bg=theme.BG_FIELD, fg=theme.FG,
                              insertbackground=theme.GREEN, font=font or theme.font(10),
                              selectbackground=theme.GREEN, selectforeground=theme.TEXT_ON_ACCENT,
                              disabledbackground=theme.BG_FIELD, disabledforeground=theme.FG_FAINT,
                              justify=justify)
        self.entry.update_idletasks()
        self.canvas.configure(width=self.entry.winfo_reqwidth() + 20)
        self._win = self.canvas.create_window(10, height // 2, window=self.entry, anchor="w")
        self.canvas.bind("<Configure>", self._resize)
        self.canvas.bind("<Button-1>", lambda e: self.entry.focus_set())
        self.entry.bind("<FocusIn>", lambda e: self._set_focus(True))
        self.entry.bind("<FocusOut>", lambda e: (self._set_focus(False), self._commit()))
        self.entry.bind("<Return>", lambda e: (self._commit(), self.winfo_toplevel().focus_set()))
        self.on_commit = on_commit
        self._draw()

    def _commit(self):
        if self.on_commit:
            self.on_commit()

    def _resize(self, e):
        self.canvas.itemconfigure(self._win, width=max(e.width - 20, 10))
        self._draw()

    def _set_focus(self, f):
        self._focus = f
        self._draw()

    def _draw(self):
        c = self.canvas
        c.delete("bgshape")
        w = max(c.winfo_width(), int(c["width"]))
        draw.rrect(c, 0, 0, w, self.height, theme.RADIUS, theme.BG_FIELD,
                   theme.GREEN if self._focus else theme.BORDER_STRONG, self.bg, tags="bgshape")
        c.tag_lower("bgshape")


class Select(tk.Canvas):
    """Dropdown: a field showing the current label; click opens a menu."""

    def __init__(self, master, options, variable, on_change=None, width=160, height=30,
                 parent_bg=None):
        self.bg = parent_bg or _parent_bg(master)
        super().__init__(master, width=width, height=height, bg=self.bg, highlightthickness=0,
                         bd=0, cursor="hand2")
        self.options = list(options)   # [(value, label)]
        self.var, self.on_change, self._hover = variable, on_change, False
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", self._open)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.var.trace_add("write", lambda *a: self._draw())
        self._draw()

    def set_options(self, options):
        self.options = list(options)
        self._draw()

    def _set_hover(self, h):
        self._hover = h
        self._draw()

    def _label(self):
        v = self.var.get()
        for value, label in self.options:
            if str(value) == str(v):
                return label
        return "Choose…"

    def _draw(self):
        self.delete("all")
        w, h = max(self.winfo_width(), int(self["width"])), max(self.winfo_height(), int(self["height"]))
        draw.rrect(self, 0, 0, w, h, theme.RADIUS,
                   theme.BG_FIELD_HOVER if self._hover else theme.BG_FIELD, theme.BORDER_STRONG,
                   self.bg)
        self.create_text(10, h / 2, text=self._label(), fill=theme.FG, font=theme.font(10),
                         anchor="w")
        self.create_image(w - 10, h / 2, image=icons.get("chevron", 14, theme.FG_MUTED), anchor="e")

    def _open(self, _e):
        menu = tk.Menu(self, tearoff=False)
        for value, label in self.options:
            menu.add_command(label="  " + label + "  ", command=lambda v=value: self._pick(v))
        menu.tk_popup(self.winfo_rootx(), self.winfo_rooty() + self.winfo_height() + 2)

    def _pick(self, value):
        self.var.set(value)
        if self.on_change:
            self.on_change(value)


class Segmented(tk.Canvas):
    """A row of mutually exclusive options in one track."""

    def __init__(self, master, options, variable, on_change=None, height=30, parent_bg=None,
                 width=None):
        self.bg = parent_bg or _parent_bg(master)
        from tkinter import font as tkfont

        self._font = theme.font(9, "bold")
        f = tkfont.Font(font=self._font)
        self.options = list(options)
        natural = sum(f.measure(lbl) + 22 for _, lbl in self.options) + 6
        super().__init__(master, width=width or natural, height=height, bg=self.bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.var, self.on_change = variable, on_change
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", self._click)
        self.var.trace_add("write", lambda *a: self._draw())
        self._draw()

    def _bounds(self):
        w = max(self.winfo_width(), int(self["width"]))
        seg = (w - 6) / max(len(self.options), 1)
        return w, seg

    def _draw(self):
        self.delete("all")
        w, seg = self._bounds()
        h = max(self.winfo_height(), int(self["height"]))
        draw.rrect(self, 0, 0, w, h, theme.RADIUS, theme.BG_FIELD, theme.BORDER, self.bg)
        current = str(self.var.get())
        for i, (value, label) in enumerate(self.options):
            x = 3 + i * seg
            active = str(value) == current
            if active:
                draw.rrect(self, x, 3, seg, h - 6, theme.RADIUS - 2, theme.GREEN, None,
                           theme.BG_FIELD, 0.8)
            self.create_text(x + seg / 2, h / 2, text=label, font=self._font,
                             fill=theme.TEXT_ON_ACCENT if active else theme.FG_MUTED)

    def _click(self, e):
        w, seg = self._bounds()
        i = int((e.x - 3) // seg)
        if 0 <= i < len(self.options):
            value = self.options[i][0]
            self.var.set(value)
            if self.on_change:
                self.on_change(value)


class Slider(tk.Canvas):
    """Horizontal slider with the value printed at the right."""

    def __init__(self, master, variable, lo, hi, fmt="{:.0%}", on_change=None, width=200,
                 parent_bg=None, step=0.01):
        self.bg = parent_bg or _parent_bg(master)
        super().__init__(master, width=width, height=26, bg=self.bg, highlightthickness=0, bd=0,
                         cursor="hand2")
        self.var, self.lo, self.hi, self.fmt = variable, lo, hi, fmt
        self.on_change, self.step = on_change, step
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", self._drag)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", lambda e: self.on_change and self.on_change(self.var.get()))
        self.var.trace_add("write", lambda *a: self._draw())
        self._draw()

    def _track(self):
        w = max(self.winfo_width(), int(self["width"]))
        return 8, w - 56

    def _draw(self):
        self.delete("all")
        x0, x1 = self._track()
        try:
            v = float(self.var.get())
        except (tk.TclError, ValueError):
            v = self.lo
        t = (min(max(v, self.lo), self.hi) - self.lo) / ((self.hi - self.lo) or 1)
        draw.rrect(self, x0, 11, x1 - x0, 4, 2, theme.BG_FIELD_HOVER, None, self.bg)
        kx = x0 + t * (x1 - x0)
        if kx - x0 > 1:
            draw.rrect(self, x0, 11, kx - x0, 4, 2, theme.GREEN, None, self.bg)
        draw.circle(self, kx, 13, 14, theme.FG, None)
        self.create_text(x1 + 12, 13, text=self.fmt.format(v), anchor="w", fill=theme.FG,
                         font=theme.font(10, "bold"))

    def _drag(self, e):
        x0, x1 = self._track()
        t = min(max((e.x - x0) / max(x1 - x0, 1), 0), 1)
        v = self.lo + t * (self.hi - self.lo)
        v = round(v / self.step) * self.step
        self.var.set(round(v, 4))


class Card(tk.Canvas):
    """Rounded panel; put children in `.body` (a Frame)."""

    def __init__(self, master, padding=14, fill=theme.BG_CARD, outline=theme.BORDER,
                 parent_bg=None, **kw):
        self.bg = parent_bg or _parent_bg(master)
        super().__init__(master, bg=self.bg, highlightthickness=0, bd=0, **kw)
        self.fill, self.outline, self.padding = fill, outline, padding
        self.body = tk.Frame(self, bg=fill)
        self._win = self.create_window(padding, padding, window=self.body, anchor="nw")
        self.bind("<Configure>", self._resize)
        self.body.bind("<Configure>", self._body_resized)

    def _body_resized(self, e):
        # Let the card grow to its content when it isn't being stretched.
        need_h = e.height + 2 * self.padding
        if int(self["height"]) != need_h and not getattr(self, "_fixed", False):
            self.configure(height=need_h)

    def _resize(self, e):
        p = self.padding
        self.itemconfigure(self._win, width=max(e.width - 2 * p, 1))
        if getattr(self, "_fixed", False):
            self.itemconfigure(self._win, height=max(e.height - 2 * p, 1))
        self.delete("cardbg")
        draw.rrect(self, 0, 0, e.width, e.height, theme.RADIUS_CARD, self.fill, self.outline,
                   self.bg, tags="cardbg")
        self.tag_lower("cardbg")

    def fixed(self):
        """Fill whatever space the layout gives instead of hugging content."""
        self._fixed = True
        return self


class ScrollFrame(tk.Frame):
    """Vertically scrolling area; content goes in `.interior`."""

    def __init__(self, master, bg=theme.BG, **kw):
        super().__init__(master, bg=bg, **kw)
        # The bar is packed first and the canvas asks for no size of its own,
        # otherwise a narrow container squeezes the bar out to nothing.
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, width=1, height=1)
        self.bar = tk.Canvas(self, width=6, bg=bg, highlightthickness=0, bd=0)
        self.bar.pack(side="right", fill="y", padx=(4, 0))
        self.canvas.pack(side="left", fill="both", expand=True)
        self.interior = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window(0, 0, window=self.interior, anchor="nw")
        self.interior.bind("<Configure>", self._update)
        self.canvas.bind("<Configure>", self._fit)
        self.canvas.configure(yscrollcommand=self._bar_set)
        for w in (self.canvas, self.interior):
            w.bind("<Enter>", self._bind_wheel)
            w.bind("<Leave>", self._unbind_wheel)
        self.bar.bind("<Configure>", lambda e: self._bar_set(self._first, self._last))
        self.bar.bind("<B1-Motion>", self._bar_drag)
        self.bar.bind("<Button-1>", self._bar_drag)
        self._first = self._last = None

    def _update(self, _e=None):
        self.canvas.configure(scrollregion=(0, 0, self.interior.winfo_reqwidth(),
                                            self.interior.winfo_reqheight()))

    def _fit(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)
        self._update()

    def _bar_set(self, first, last):
        if first is None:
            return
        self._first, self._last = float(first), float(last)
        b = self.bar
        b.delete("all")
        if self._last - self._first >= 0.999:
            return
        h = max(b.winfo_height(), 1)
        y0, y1 = self._first * h, self._last * h
        draw.rrect(b, 0, y0, 6, max(y1 - y0, 12), 3, theme.BORDER_STRONG, None, None)

    def _bar_drag(self, e):
        if self._first is None:
            return
        h = max(self.bar.winfo_height(), 1)
        span = self._last - self._first
        self.canvas.yview_moveto(max(0.0, e.y / h - span / 2))

    def _bind_wheel(self, _e):
        if sys.platform.startswith("linux"):
            self.bind_all("<Button-4>", lambda e: self._scroll(-1))
            self.bind_all("<Button-5>", lambda e: self._scroll(1))
        else:
            self.bind_all("<MouseWheel>", self._wheel)

    def _unbind_wheel(self, e):
        # Moving onto a child row also sends <Leave>; only let go of the wheel
        # once the pointer has really left this scroll area.
        try:
            under = self.winfo_containing(e.x_root, e.y_root)
        except (tk.TclError, KeyError):
            under = None
        while under is not None:
            if under is self:
                return
            under = under.master
        for seq in ("<Button-4>", "<Button-5>", "<MouseWheel>"):
            self.unbind_all(seq)

    def _wheel(self, e):
        delta = e.delta if sys.platform == "darwin" else e.delta / 120
        self._scroll(-int(delta) or (-1 if e.delta > 0 else 1))

    def _scroll(self, units):
        if self._first is not None and self._last - self._first < 0.999:
            self.canvas.yview_scroll(units, "units")

    def scroll_to_widget(self, widget):
        self.update_idletasks()
        if self._first is None:
            return
        total = max(self.interior.winfo_height(), 1)
        y = widget.winfo_y()
        h = widget.winfo_height()
        top = self._first * total
        view = (self._last - self._first) * total
        if y < top:
            self.canvas.yview_moveto(y / total)
        elif y + h > top + view:
            self.canvas.yview_moveto((y + h - view) / total)


class Toast(tk.Canvas):
    """Short message floated at the bottom centre of the window."""

    def __init__(self, root):
        super().__init__(root, height=34, bg=theme.BG, highlightthickness=0, bd=0)
        self.root, self._job = root, None

    def show(self, message, kind="info", ms=1800):
        from tkinter import font as tkfont

        color = {"info": theme.BG_RAISED, "ok": theme.GREEN_DIM, "warn": theme.ORANGE_DIM,
                 "error": theme.RED_DIM}[kind]
        accent = {"info": theme.FG_SOFT, "ok": theme.GREEN, "warn": theme.ORANGE,
                  "error": theme.RED}[kind]
        f = theme.font(10)
        w = tkfont.Font(font=f).measure(message) + 44
        self.configure(width=w)
        self.delete("all")
        draw.rrect(self, 0, 0, w, 34, 17, color, theme.BORDER_STRONG, theme.BG)
        draw.circle(self, 18, 17, 8, accent, None)
        self.create_text(30, 17, text=message, anchor="w", fill=theme.FG, font=f)
        # Above the Flow page footer, centred on the content area (not the rail).
        self.place(relx=0.5, rely=1.0, y=-84, anchor="s", x=34)
        tk.Misc.lift(self)
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(ms, self.place_forget)


class Tooltip:
    def __init__(self, widget, text):
        self.widget, self.text, self.tip, self._job = widget, text, None, None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _e):
        self._job = self.widget.after(500, self._show)

    def _show(self):
        if self.tip:
            return
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.configure(bg=theme.BORDER_STRONG)
        tk.Label(self.tip, text=self.text, bg=theme.BG_RAISED, fg=theme.FG_SOFT,
                 font=theme.font(9), padx=8, pady=4).pack(padx=1, pady=1)
        self.tip.update_idletasks()
        self.tip.wm_geometry(f"+{x - self.tip.winfo_width() // 2}+{y}")

    def _hide(self, _e=None):
        if self._job:
            self.widget.after_cancel(self._job)
            self._job = None
        if self.tip:
            self.tip.destroy()
            self.tip = None


class HotkeyPicker(Button):
    """Shows a hotkey; click, then press the new key (Esc clears it)."""

    def __init__(self, master, manager, combo, on_change, width=150, **kw):
        self.manager, self.combo, self.on_change = manager, combo, on_change
        super().__init__(master, text=hotkeys.label(combo), command=self._capture,
                         variant="secondary", width=width, icon="keyboard", **kw)

    def set_combo(self, combo):
        self.combo = combo
        self.configure_button(text=hotkeys.label(combo), variant="secondary")

    def _capture(self):
        self.configure_button(text="Press a key…", variant="running")
        self.manager.capture_next(lambda c: self.after(0, self._got, c))

    def _got(self, combo):
        if combo == "esc":
            combo = ""
        self.set_combo(combo)
        self.on_change(combo)


def section(master, text, bg=None):
    return tk.Label(master, text=text.upper(), bg=bg or _parent_bg(master), fg=theme.FG_MUTED,
                    font=theme.font(8, "bold"), anchor="w")


def label(master, text, muted=False, size=10, bold=False, bg=None, **kw):
    kw.setdefault("anchor", "w")
    return tk.Label(master, text=text, bg=bg or _parent_bg(master),
                    fg=theme.FG_MUTED if muted else theme.FG,
                    font=theme.font(size, "bold" if bold else "normal"), **kw)


class Swatch(tk.Canvas):
    def __init__(self, master, rgb, size=30, parent_bg=None, command=None):
        self.bg = parent_bg or _parent_bg(master)
        super().__init__(master, width=size, height=size, bg=self.bg, highlightthickness=0, bd=0,
                         cursor="hand2" if command else "")
        self.size = size
        if command:
            self.bind("<Button-1>", lambda e: command())
        self.set(rgb)

    def set(self, rgb):
        self.delete("all")
        color = draw.rgb_to_hex(rgb)
        draw.rrect(self, 0, 0, self.size, self.size, theme.RADIUS, color, theme.BORDER_STRONG,
                   self.bg)
