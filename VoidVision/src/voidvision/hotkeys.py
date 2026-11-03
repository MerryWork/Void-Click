"""Global hotkeys (keyboard keys, modifier combos and mouse side buttons).

A hotkey fires when all of its keys are held and the key just pressed belongs
to it - extra unrelated keys being held don't block it, so hotkeys still work
mid-game while movement keys are down.
"""

import threading
import traceback

MODIFIERS = ("ctrl", "alt", "shift", "cmd")
_ORDER = {m: i for i, m in enumerate(MODIFIERS)}
_FRIENDLY = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "cmd": "Cmd",
             "mouse_x1": "Mouse 4", "mouse_x2": "Mouse 5", "mouse_middle": "Middle Click",
             "space": "Space", "esc": "Esc", "enter": "Enter", "tab": "Tab"}


def normalize(tokens):
    return "+".join(sorted(set(tokens), key=lambda t: (_ORDER.get(t, 99), t)))


def parse(combo):
    return frozenset(t for t in (combo or "").split("+") if t)


def label(combo):
    if not combo:
        return "Not set"
    parts = sorted(parse(combo), key=lambda t: (_ORDER.get(t, 99), t))
    return " + ".join(_FRIENDLY.get(t, t.upper() if len(t) <= 3 else t.title()) for t in parts)


def matches(combo, held, just_pressed):
    c = parse(combo)
    return bool(c) and just_pressed in c and c <= held


class HotkeyManager:
    def __init__(self):
        self._hotkeys = {}           # name -> (frozenset, callback)
        self._held = set()
        self._by_vk = {}
        self._capture = None
        self._lock = threading.Lock()
        self._listeners = []

    def start(self):
        try:
            from pynput import keyboard, mouse
        except Exception:  # no display / no permission - hotkeys simply off
            traceback.print_exc()
            return False
        self._kb = keyboard
        self._ms = mouse
        self._listeners = [
            keyboard.Listener(on_press=self._on_press, on_release=self._on_release),
            mouse.Listener(on_click=self._on_click),
        ]
        for listener in self._listeners:
            listener.daemon = True
            listener.start()
        return True

    def stop(self):
        for listener in self._listeners:
            try:
                listener.stop()
            except Exception:
                pass
        self._listeners = []

    def register(self, name, combo, callback):
        with self._lock:
            if combo:
                self._hotkeys[name] = (parse(combo), callback)
            else:
                self._hotkeys.pop(name, None)

    def capture_next(self, callback):
        """callback(combo) on the next non-modifier key or side button."""
        self._capture = callback

    def cancel_capture(self):
        self._capture = None

    # ---------------------------------------------------------------- tokens

    def _key_token(self, key):
        kb = self._kb
        for mod in MODIFIERS:
            for suffix in ("", "_l", "_r", "_gr"):
                k = getattr(kb.Key, mod + suffix, None)
                if k is not None and key == k:
                    return mod
        if isinstance(key, kb.KeyCode):
            if key.char:
                return key.char.lower()
            return f"vk{key.vk}"
        return getattr(key, "name", str(key))

    def _press(self, token):
        cap = self._capture
        if cap is not None:
            if token in MODIFIERS:
                self._held.add(token)
                return
            if token == "mouse_left":
                return
            self._capture = None
            combo = normalize((self._held & set(MODIFIERS)) | {token})
            try:
                cap(combo)
            except Exception:
                traceback.print_exc()
            return
        self._held.add(token)
        held = frozenset(self._held)
        with self._lock:
            hits = [(c, cb) for c, cb in self._hotkeys.values() if token in c and c <= held]
        if not hits:
            return
        top = max(len(c) for c, _ in hits)
        for c, cb in hits:
            if len(c) == top:
                try:
                    cb()
                except Exception:
                    traceback.print_exc()

    def _on_press(self, key, injected=False):
        if injected:
            return
        token = self._key_token(key)
        vk = getattr(key, "vk", None)
        if vk is not None:
            self._by_vk[vk] = token
        self._press(token)

    def _on_release(self, key, injected=False):
        vk = getattr(key, "vk", None)
        token = self._by_vk.pop(vk, None) if vk is not None else None
        self._held.discard(token or self._key_token(key))

    def _on_click(self, x, y, button, pressed, injected=False):
        if injected:
            return
        name = getattr(button, "name", "")
        token = {"x1": "mouse_x1", "button8": "mouse_x1", "x2": "mouse_x2",
                 "button9": "mouse_x2", "middle": "mouse_middle"}.get(name, f"mouse_{name}")
        if pressed:
            self._press(token)
        else:
            self._held.discard(token)
