"""Per-user settings (not stored next to the program - see README)."""

import json
import os
import sys
from pathlib import Path

APP_DIR_NAME = "VoidVision"

DEFAULTS = {
    "run_hotkey": "f9",
    "capture_hotkey": "f10",
    "panic_hotkey": "f12",
    "hide_while_running": True,
    "highlight_tests": True,
    "always_on_top": False,
    "poll_ms": 120,
    "default_confidence": 0.85,
    "last_flow": "",
}


def data_dir():
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / APP_DIR_NAME


def config_path():
    return data_dir() / "config.json"


def merge(data):
    """Defaults overlaid with known keys from `data`, type-checked loosely."""
    cfg = dict(DEFAULTS)
    if isinstance(data, dict):
        for key, default in DEFAULTS.items():
            if key in data and isinstance(data[key], type(default)):
                cfg[key] = data[key]
            elif key in data and isinstance(default, float) and isinstance(data[key], int):
                cfg[key] = float(data[key])
    return cfg


def load(path=None):
    path = Path(path or config_path())
    try:
        with open(path, "r", encoding="utf-8") as f:
            return merge(json.load(f))
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save(cfg, path=None):
    path = Path(path or config_path())
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except OSError:
        pass


def autosave_path():
    """Where the open flow is kept between sessions when it was never saved."""
    return data_dir() / "autosave.vflow"
