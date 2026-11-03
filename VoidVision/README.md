VOID VISION

The visual-macro member of the Void Click family. Instead of replaying fixed
mouse coordinates, a Void Vision flow looks at the screen: it finds a captured
image (a button, an icon, a word) or a colour and clicks wherever it is right
now. Flows keep working when windows move, resize or open somewhere new.

Same dark-glass look as Void Click, rebuilt sharper: anti-aliased shapes,
hairline borders and crisp line icons, all drawn by Pillow. Screenshots:
docs/flow.png and docs/images.png.


INSTALL AND RUN

Python 3.8+:

    pip install .
    voidvision

Or without installing - double-click VoidVision.pyw (Windows), or from this
folder:

    pip install pynput pillow numpy
    python VoidVision.pyw

Optional, for much faster matching on big screens:

    pip install opencv-python        (or: pip install .[fast])

Void Vision uses OpenCV automatically when it is installed and falls back to
pure NumPy when it isn't. Settings > About shows which one is active.

Settings and an autosave of the open flow live per user:

    Windows    %APPDATA%\VoidVision\
    macOS      ~/Library/Application Support/VoidVision/
    Linux      $XDG_CONFIG_HOME/VoidVision/


HOW IT WORKS

1. Add a "Find & click" step. The window steps aside and the screen freezes
   under a dimmed overlay - drag a box around what to click.
2. Press Test (eye icon) to check it is found. It reports the match score and
   time, and flashes a frame around the match on screen.
3. Add more steps and press Run (F9). Press F9 again or F12 to stop.

Because you select on a frozen screenshot, you can capture hover states,
tooltips and menus that would vanish the moment the mouse moved.


STEPS

Vision
  Find & click     Look for an image, then Click / Double / Right / Hover on
                   its centre, plus an optional X/Y offset (e.g. click the
                   text box to the right of a label)
  Wait for image   Wait until an image appears - or until it disappears
  If visible       If an image is (or with "If NOT visible", isn't) on screen,
                   carry on; otherwise skip the next N steps
  Find colour      Look for a pixel colour (+/- tolerance) and click it.
                   Pick the colour straight off the screen with the dropper

Input
  Click            Click where the cursor already is, N times
  Key              A key or combo - ctrl+s, alt+tab, enter, f5... or press
                   Record and hit the keys
  Type text        Type a string
  Scroll           Scroll up (+) or down (-)
  Wait             Pause N seconds

Every vision step has:
  Match            How close a match must be (85% default). Lower finds more
                   but may find the wrong thing; Test shows the best score so
                   you can tune it
  Timeout          Keep looking for up to N seconds (0 = look once)
  Search area      Limit the search to part of the screen. Faster, and stops
                   look-alikes elsewhere from matching
  Strict colour    Greyscale matching can't tell a red button from a green one
                   of the same brightness; this checks colour too
  If not found     Stop the flow / Skip this step / Restart the flow from the
                   top. Restart turns "wait for X, then click it" into a retry
                   loop

Steps can be dragged to reorder, duplicated, disabled (double-click a row,
or the switch in the inspector) and run from any point ("Run from this
step"). Loop a flow N times, or 0 for until stopped.


IMAGES

The Images page is the flow's library. Every capture lands here; rename,
recapture, test or delete them, or import PNG/JPG files. A flow file
(.vflow) is a single JSON document with the images embedded, so one file is
all you need to share a flow.


HOTKEYS

Global, configurable in Settings:

    F9     Run / stop the flow
    F10    Capture a new image into the library
    F12    Emergency stop

Keyboard keys, modifier combos and mouse side buttons all work.


TIPS

- Capture tight around something distinctive - a whole button with its
  label, not just its background. A single flat colour matches anywhere
  (Void Vision warns you); use Find colour for those.
- Leave "Minimise while running" on so the window never hides the target.
- Give a slow app time: raise Timeout rather than adding Wait steps - the
  step continues the moment the image appears.
- Matching runs at the screen's native scale. Captures made at one display
  scaling (100%, 150%, Retina) won't match the same UI drawn at another.


PLATFORM NOTES

Windows: the app runs DPI-aware, so screenshots, the overlay and the mouse
all use the same physical pixels on scaled displays. Multi-monitor desktops
are captured whole.

macOS: needs Screen Recording (to see the screen), Accessibility (to click
and type) and Input Monitoring (for hotkeys) under System Settings > Privacy
& Security. Retina screenshots are mapped back to screen points
automatically. Only the main display is searched.

Linux (X11): works with an X server; Wayland sessions generally block
screenshots and synthetic input.

Games and anti-cheat: many games detect synthetic input, and automation may
break a game's terms of service. Use responsibly.


TESTS

    python tests/test_core.py

Covers the matcher (exact, downscaled, brightness-shifted, colour-strict,
flat, multi-match, colour search), the flow file round trip, every runner
rule (offsets, actions, Retina scale and desktop origin, search areas, the
three failure policies, wait-appear/vanish, if-visible skipping, loops, stop,
start-from-step, recovery from backend errors) and the hotkey and settings
helpers. The runner is driven through a fake screen, so the tests never
move the real mouse.


BUILDING A STANDALONE BUILD

    pip install pyinstaller
    pyinstaller voidvision.spec

Output lands in dist/.
