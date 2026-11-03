"""Entry point."""

from . import config
from .screen import enable_dpi_awareness


def main():
    # Must happen before any window or screenshot exists (Windows only).
    enable_dpi_awareness()
    from .app import MainWindow
    from .hotkeys import HotkeyManager

    cfg = config.load()
    manager = HotkeyManager()
    app = MainWindow(cfg, manager)
    manager.start()
    app.mainloop()
    return 0
