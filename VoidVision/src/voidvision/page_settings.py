"""Settings page."""

import tkinter as tk

from . import __version__, explain, matcher, theme
from . import widgets as w


class SettingsPage(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=theme.BG)
        self.app = app
        self.pickers = {}
        self._build()

    def _card(self, parent, title, subtitle):
        card = w.Card(parent, padding=18, parent_bg=theme.BG)
        card.pack(fill="x", pady=(0, 12))
        w.label(card.body, title, bold=True, size=11, bg=theme.BG_CARD).pack(anchor="w")
        w.label(card.body, subtitle, muted=True, size=9, bg=theme.BG_CARD).pack(anchor="w",
                                                                              pady=(2, 12))
        return card.body

    def _row(self, body, text, hint=""):
        row = tk.Frame(body, bg=theme.BG_CARD)
        row.pack(fill="x", pady=4)
        left = tk.Frame(row, bg=theme.BG_CARD)
        left.pack(side="left", fill="x", expand=True)
        w.label(left, text, bg=theme.BG_CARD).pack(anchor="w")
        if hint:
            w.label(left, hint, muted=True, size=9, bg=theme.BG_CARD).pack(anchor="w")
        return row

    def _build(self):
        cfg = self.app.cfg
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=24, pady=(20, 16))
        w.label(head, "Settings", size=18, bold=True).pack(anchor="w")
        w.label(head, "Saved automatically.", muted=True).pack(anchor="w")

        scroll = w.ScrollFrame(self)
        scroll.pack(fill="both", expand=True, padx=24, pady=(0, 18))
        inner = scroll.interior

        hk = self._card(inner, "Hotkeys", "Global - they work while another window has focus. "
                                         "Esc while recording clears one.")
        for key, text, hint in (("run_hotkey", "Run / stop flow", ""),
                                ("capture_hotkey", "Capture image", "Adds it to the library"),
                                ("panic_hotkey", "Emergency stop", "Stops everything immediately")):
            row = self._row(hk, text, hint)
            p = w.HotkeyPicker(row, self.app.hotkeys, cfg[key],
                               lambda c, k=key: self._set_hotkey(k, c), parent_bg=theme.BG_CARD,
                               width=160)
            p.pack(side="right")
            self.pickers[key] = p

        be = self._card(inner, "Behaviour", "How the window gets out of the way.")
        for key, text, hint in (
                ("hide_while_running", "Minimise while running",
                 "So the window never covers what the flow is looking for"),
                ("highlight_tests", "Highlight test matches", "Flash a frame around what was found"),
                ("always_on_top", "Keep window on top", "")):
            row = self._row(be, text, hint)
            var = tk.BooleanVar(value=cfg[key])
            w.Toggle(row, "", var, command=lambda k=key, v=var: self._set(k, bool(v.get())),
                     parent_bg=theme.BG_CARD).pack(side="right")

        ma = self._card(inner, "Matching", "Defaults for new steps.")
        row = self._row(ma, "Default match", "Lower finds more, but may find the wrong thing")
        conf = tk.DoubleVar(value=cfg["default_confidence"])
        w.Slider(row, conf, 0.5, 1.0, parent_bg=theme.BG_CARD, width=240,
                 fmt=lambda v: f"{v:.0%} {explain.strictness(v)}",
                 on_change=lambda v: self._set("default_confidence", round(float(conf.get()), 2))
                 ).pack(side="right")
        row = self._row(ma, "Re-check every (ms)", "How often a waiting step looks again")
        poll = tk.StringVar(value=str(cfg["poll_ms"]))

        def set_poll():
            try:
                v = min(max(int(float(poll.get())), 20), 5000)
            except ValueError:
                v = cfg["poll_ms"]
            poll.set(str(v))
            self._set("poll_ms", v)

        w.Entry(row, poll, width=6, on_commit=set_poll, parent_bg=theme.BG_CARD,
                justify="center").pack(side="right")

        kb = self._card(inner, "Keyboard", "On the Flow page, when you're not typing in a field.")
        for keys, what in (("\u2191 / \u2193", "Select the previous / next step"),
                           ("Ctrl + \u2191 / \u2193", "Move the selected step up / down"),
                           ("Space", "Turn the selected step on or off"),
                           ("T", "Test the selected image or colour step"),
                           ("Ctrl + D", "Duplicate the selected step"),
                           ("Delete", "Delete the selected step"),
                           ("Ctrl + S  /  Ctrl + O", "Save / open a flow")):
            row = tk.Frame(kb, bg=theme.BG_CARD)
            row.pack(fill="x", pady=2)
            w.label(row, keys, bg=theme.BG_CARD, width=20, font=theme.mono(10)).pack(side="left")
            w.label(row, what, muted=True, bg=theme.BG_CARD).pack(side="left")

        ab = self._card(inner, "About", f"Void Vision {__version__}")
        accel = "OpenCV (fast)" if matcher.cv2 is not None else "NumPy  ·  pip install opencv-python for faster matching"
        row = self._row(ab, "Matching engine", accel)

    def _set(self, key, value):
        self.app.cfg[key] = value
        self.app.apply_settings()

    def _set_hotkey(self, key, combo):
        cfg = self.app.cfg
        for other in ("run_hotkey", "capture_hotkey", "panic_hotkey"):
            if other != key and combo and cfg[other] == combo:
                self.pickers[key].set_combo(cfg[key])
                self.app.toast("That key is already used by another hotkey", "warn")
                return
        self._set(key, combo)

    def refresh(self):
        for key, p in self.pickers.items():
            p.set_combo(self.app.cfg[key])
