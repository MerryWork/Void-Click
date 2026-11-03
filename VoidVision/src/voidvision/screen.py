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

    # ---------------------------------------------------------------- input

    def _ctl(self):
        if self._mouse is None:
            from pynput import keyboard, mouse

            self._mouse = mouse.Controller()
            self._keyboard = keyboard.Controller()
        return self._mouse, self._keyboard

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
        _, kb = self._ctl()
        keys = [_to_key(part) for part in str(combo).split("+") if part]
        for k in keys:
            kb.press(k)
        if hold_ms:
            time.sleep(hold_ms / 1000.0)
        for k in reversed(keys):
            kb.release(k)

    def type_text(self, text):
        _, kb = self._ctl()
        kb.type(text)


_ALIASES = {"control": "ctrl", "option": "alt", "win": "cmd", "super": "cmd", "command": "cmd",
            "return": "enter", "escape": "esc", "del": "delete", "pgup": "page_up",
            "pgdn": "page_down", "spacebar": "space"}


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
