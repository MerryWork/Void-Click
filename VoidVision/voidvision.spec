# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec - a standalone Void Vision executable.

    pip install pyinstaller
    pyinstaller voidvision.spec
"""

import sys

# pynput chooses its backend at runtime, invisible to static analysis.
if sys.platform == "win32":
    backends = ["pynput.keyboard._win32", "pynput.mouse._win32"]
elif sys.platform == "darwin":
    backends = ["pynput.keyboard._darwin", "pynput.mouse._darwin"]
else:
    backends = ["pynput.keyboard._xorg", "pynput.mouse._xorg"]

a = Analysis(
    ["launch.py"],
    pathex=["src"],
    binaries=[],
    datas=[],
    hiddenimports=backends + ["PIL.ImageTk", "PIL.ImageGrab"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="VoidVision",
    debug=False,
    strip=False,
    upx=True,
    console=False,
)

if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="Void Vision.app",
        bundle_identifier="com.voidclick.vision",
        info_plist={
            "NSHighResolutionCapable": True,
            "NSAppleEventsUsageDescription": "Void Vision sends keyboard and mouse input on your behalf.",
        },
    )
