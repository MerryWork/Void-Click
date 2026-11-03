"""Screen capture and synthetic input - the only module that touches the OS.

Coordinates: everything outside this module works in *screen coordinates*,
the space the mouse moves in. Screenshots can be in a different pixel space
(Retina displays capture at 2x), so every grab returns a Shot that knows how
to map its own pixels back to screen coordinates.
"""

import sys
import time
from dataclasses import dataclass

from PIL import Image


def enable_dpi_awareness():
    """On Windows, make screenshots, Tk and pynput all use physical pixels.

    Without this, a scaled display (125%, 150%) captures at one size and moves
    the mouse at another, so every click would land off target.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def virtual_screen(root=None):
    """(left, top, width, height) of the whole desktop in screen coordinates."""
    if sys.platform == "win32":
        try:
            import ctypes

            m = ctypes.windll.user32.GetSystemMetrics
            # SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN
            return m(76), m(77), m(78), m(79)
        except Exception:
            pass
    if root is not None:
        return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()
    return 0, 0, 1920, 1080


@dataclass
class Shot:
    image: Image.Image
    left: float     # screen coordinate of the image's top-left pixel
    top: float
    scale: float    # image pixels per screen unit

    def to_screen(self, px, py):
        return self.left + px / self.scale, self.top + py / self.scale

    def size_on_screen(self, pw, ph):
        return pw / self.scale, ph / self.scale


class ScreenBackend:
    """Real screen and input. `screen_rect` is the desktop in screen units."""

    def __init__(self, screen_rect):
        self.screen_rect = screen_rect
        self._mouse = None
        self._keyboard = None

    # ---------------------------------------------------------------- capture

    def grab(self, region=None):
        from PIL import ImageGrab

        sl, st, sw, sh = self.screen_rect
        kwargs = {"all_screens": True} if sys.platform == "win32" else {}
        # Always grab the whole desktop, then crop. Asking for a bbox is not
        # consistent across platforms - on macOS it comes back at 1x while a
        # full grab is Retina 2x, and captured images would stop matching
        # as soon as a search area was set.
        image = ImageGrab.grab(**kwargs).convert("RGB")
        scale = (image.width / float(sw)) if sw else 1.0
        scale = scale or 1.0
        if region is None:
            return Shot(image, sl, st, scale)
        x, y, w, h = region
        box = (int(round((x - sl) * scale)), int(round((y - st) * scale)),
               int(round((x - sl + w) * scale)), int(round((y - st + h) * scale)))
        box = (max(box[0], 0), max(box[1], 0), min(box[2], image.width), min(box[3], image.height))
        if box[2] <= box[0] or box[3] <= box[1]:
            box = (0, 0, 1, 1)  # area is off-screen: an empty search, not a crash
        return Shot(image.crop(box), sl + box[0] / scale, st + box[1] / scale, scale)

    def grab_fast(self, region):
        """Grab just `region`, as quickly as the platform allows.

        Timing steps look at a small bar many times a second; grabbing the
        whole desktop each time would be far too slow. Windows and X11 copy
        just the area (in physical pixels, thanks to DPI awareness). macOS
        returns bbox grabs at a different scale than full grabs, so there
        the consistent full-grab-and-crop path is used instead.
        """
        if sys.platform == "darwin":
            return self.grab(region)
        from PIL import ImageGrab

        x, y, w, h = (int(round(v)) for v in region)
        kwargs = {"all_screens": True} if sys.platform == "win32" else {}
        image = ImageGrab.grab(bbox=(x, y, x + w, y + h), **kwargs).convert("RGB")
        return Shot(image, x, y, image.width / float(w) if w else 1.0)

    # ---------------------------------------------------------------- input

    def _ctl(self):
        if self._mouse is None:
            from pynput import keyboard, mouse

            self._mouse = mouse.Controller()
            self._keyboard = keyboard.Controller()
        return self._mouse, self._keyboard

    def prepare(self):
        """Connect the mouse and keyboard now, not on the first press.

        Creating pynput's controllers opens a connection to the input system,
        which can take tens of milliseconds - enough to make the first key
        press of a timing step late.
        """
        self._ctl()

    def move(self, x, y):
        m, _ = self._ctl()
        m.position = (int(round(x)), int(round(y)))

    def click(self, button="left", count=1):
        from pynput.mouse import Button

        m, _ = self._ctl()
        m.click(getattr(Button, button, Button.left), count)

    def scroll(self, amount):
        m, _ = self._ctl()
        m.scroll(0, amount)

    def press_combo(self, combo, hold_ms=0):
        """Press a key, a mouse button, or either with modifiers held.

        e.g. "space", "ctrl+s", "mouse_left", "shift+mouse_right".
        """
        m, kb = self._ctl()
        parts = [p for p in str(combo).split("+") if p]
        buttons = [_to_button(p) for p in parts if p.strip().lower().startswith("mouse_")]
        keys = [_to_key(p) for p in parts if not p.strip().lower().startswith("mouse_")]
        for k in keys:
            kb.press(k)
        for b in buttons:
            m.press(b)
        if hold_ms:
            time.sleep(hold_ms / 1000.0)
        for b in reversed(buttons):
            m.release(b)
        for k in reversed(keys):
            kb.release(k)

    def type_text(self, text):
        _, kb = self._ctl()
        kb.type(text)


_ALIASES = {"control": "ctrl", "option": "alt", "win": "cmd", "super": "cmd", "command": "cmd",
            "return": "enter", "escape": "esc", "del": "delete", "pgup": "page_up",
            "pgdn": "page_down", "spacebar": "space"}


def _to_button(name):
    from pynput.mouse import Button

    token = name.strip().lower()[len("mouse_"):]
    for attr in {"left": ["left"], "right": ["right"], "middle": ["middle"],
                 "x1": ["x1", "button8"], "x2": ["x2", "button9"]}.get(token, [token]):
        button = getattr(Button, attr, None)
        if button is not None:
            return button
    raise ValueError(f"unknown mouse button: {name!r}")


def _to_key(name):
    from pynput.keyboard import Key, KeyCode

    name = name.strip().lower()
    name = _ALIASES.get(name, name)
    if len(name) == 1:
        return KeyCode.from_char(name)
    key = getattr(Key, name, None)
    if key is None:
        raise ValueError(f"unknown key: {name!r}")
    return key
