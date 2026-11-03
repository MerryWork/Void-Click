VOID CLICK

An autoclicker, macro recorder and macro scripting tool for Windows and macOS.
Pure Python - a tkinter GUI with pynput for input control, and no other
dependencies.

One window with a dark glass theme and an icon rail for Clicker, Macro, Script
and Settings.

Looking for macros that see the screen? VoidVision/ in this repository is the
separate visual-macro app: flows that find an image or colour on screen and
click it wherever it is. See VoidVision/README.md.


INSTALL AND RUN

If you have Python 3.8+:

    pip install .
    voidclick

"voidclick" is registered as a GUI script, so on Windows it launches with no
console window behind it.

Without installing - double-click VoidClick.pyw in this folder (Windows), or
run:

    python -m voidclick

from the src directory. Either way you need pynput (pip install pynput).

Without Python at all - build a standalone executable, see "Building a
standalone build" below.

Settings are stored per user, not next to the program:

    Windows    %APPDATA%\VoidClick\config.json
    macOS      ~/Library/Application Support/VoidClick/config.json
    Linux      $XDG_CONFIG_HOME/VoidClick/config.json

Delete that file to restore defaults.


FEATURES

Clicker
- Click rate in milliseconds or clicks-per-second - switch units, the other is
  shown live
- Duty cycle - the share of each cycle the button is held down
- Speed randomization - jitters the interval so clicks aren't perfectly uniform
- Position jitter - scatters each click by +/- N pixels instead of hammering one
  point
- Click limit, and a choice of mouse button

Macro - records what you do
- Mouse movement, clicks, scroll and keyboard input, with real timing
- Fixed loop count or continuous looping
- Its own playback speed control (0.25x - 4x), adjustable mid-run
- Convert to Script - rebuilds a recording as editable, position-free steps
- Save and load as .json

Script - position-independent sequences
Recorded macros replay absolute coordinates, so they break when a window moves.
A script is an ordered list of logical steps with no positions in it:

    Autoclick    Click at N cps for N seconds
    Clicks       Click exactly N times
    Key          Press a key, optionally held for N ms
    Wait         Pause N seconds

Click steps take duty cycle and randomization too. So "autoclick at 34 cps,
every 3 seconds press 3, wait, press 1, then carry on" is four steps with
"Repeat until stopped" enabled. Steps can be reordered, duplicated, edited
inline and saved to .json. The page has its own run-speed control, separate
from the macro one.

Converting a recording into a script

The Macro page's "Convert to Script" button analyses a recording and rebuilds
it as steps: click bursts become autoclick or click steps with the rate, duty
cycle and randomization recovered from the original timings, pauses become wait
steps, and keypresses become key steps.

Because scripts carry no coordinates, the conversion is only faithful when every
click landed in roughly the same place. Before replacing anything it reports what
can't come across - clicks in several positions, scroll events, mouse movement,
and held modifiers such as Ctrl+C, which sequential key steps can't express.

Settings
- Panic hotkey, and whether panic also closes the app
- A swap hotkey that trades two actions' start hotkeys with each other - pick
  which pair it applies to, press it, and they exchange keys
- Keep window always on top
- Record mouse movement - off gives much smaller, clicks-and-keys-only macros
- Export / import settings, so a working setup can be shared
- Reset all settings to defaults


HOTKEYS

Click a hotkey button, then press what you want to bind. Keyboard keys and
mouse buttons both work - side buttons (Mouse 4/5), middle click, right click,
alone or with modifiers. Hotkeys are global; the window doesn't need focus.

- Toggle - press once to start, again to stop.
- Hold - runs only while the key or button is held down.

Holding unrelated keys does not block a hotkey, so bindings still fire while
you're holding movement keys in a game.

All six hotkeys - clicker, macro record, macro play, script run, panic and swap -
are forced to be different. Assigning a key another one already owns clears the
field and shows a warning instead.

Bare left click is deliberately refused as a binding: it would fire on every
click. Left click with a modifier is fine.

Void Click ignores input it generated itself, so binding the same mouse button
the clicker is clicking won't make it switch itself off.


EMERGENCY STOP

The panic hotkey (default F12) halts the clicker, macro playback, recording
and any running script at once, from anywhere. It can also close the app
outright - see Settings.


TESTS

    py tests/test_core.py

196 assertions covering click timing, limits and jitter, macro round-trips,
playback order/speed/interrupt, script execution and looping, macro-to-script
conversion, hotkey matching, hold mode, capture rules, conflict detection,
hotkey swapping, recovery from mid-run errors, and config merging. Input
controllers are stubbed, so the tests never move the real mouse or send real
keystrokes.


BUILDING A STANDALONE BUILD

For sharing with people who don't have Python:

    pip install pyinstaller
    pyinstaller voidclick.spec

The result lands in dist/. The spec names pynput's platform backend as a
hidden import, which PyInstaller's static analysis cannot find on its own, and
adds a proper .app bundle on macOS.


PLATFORM NOTES

macOS: pynput needs Accessibility permission (to control the mouse and
keyboard) and Input Monitoring permission (to see global input). macOS should
prompt on first run; if not, add your terminal or the python binary under
System Settings > Privacy & Security > Accessibility and > Input Monitoring,
then restart.

Windows: the title bar is switched to dark automatically on Windows 10
2004+/11. Some antivirus tools flag autoclicker-style software (global input
hooks plus synthetic clicks) as a false positive - expected for this category of
tool.

Games and anti-cheat: many games detect and block synthetic input, and input
automation may violate a game's terms of service. Use responsibly.


KNOWN LIMITATIONS

- Keys bound as record/play hotkeys are filtered out of recordings to avoid
  feedback loops, so a key can't be both a hotkey and part of a macro.
- Timing is bounded by OS scheduling; very high click rates drift from the
  requested figure.
- A recorded macro can be played, saved and cleared, but not edited step by
  step - convert it to a script to edit it.
- macOS is untested. The code paths are there and documented, but the app has
  only ever been run on Windows.
