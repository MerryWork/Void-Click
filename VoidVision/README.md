VOID VISION

The visual-macro member of the Void Click family. Instead of replaying fixed
mouse coordinates, a Void Vision flow looks at the screen: it finds a captured
image (a button, an icon, a word) or a colour and clicks wherever it is right
now. Flows keep working when windows move, resize or open somewhere new.

Same dark-glass look as Void Click, rebuilt sharper: anti-aliased shapes,
hairline borders and crisp line icons, all drawn by Pillow. Screenshots:
docs/flow.png, docs/test-result.png and docs/images.png.


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


UNDERSTANDING IMAGES

Void Vision explains what it sees in plain words, so you don't have to guess
what a number like 0.81 means.

- Every captured image gets a rating under it: "Good image", "Low detail",
  "Large", "Very small" or "One flat colour". Each comes with a sentence
  saying why and what to do about it. A weak capture also gets a warning
  the moment you make it.
- Test shows the result in words first ("Found", "Almost - just under your
  setting", "Not on screen"), then the evidence: your image beside what it
  found on screen. If it found nothing good enough, you see the closest
  spot instead. A similarity bar shows the score, with a tick marking what
  the step needs. When a match is close, it gives a working number, e.g.
  "lower Match to 77%".
- The Match slider reads as a word as well as a percentage: Loose,
  Balanced, Strict or Exact.
- Changing the Match setting re-judges the last test straight away, so you
  can see whether the step would now succeed without testing again.


CUT-OUTS: IGNORING WHAT'S BEHIND IT

A capture of a meter, a timing bar, a crosshair or a health bar drags along
whatever was behind it - a character, the map, the sky. When that changes,
the capture stops matching. Cut the background out:

1. Images page (or the scissors button next to Capture in a step) >
   Cut out background.
2. Click the colour to look for - e.g. the white of a timing bar. Only
   pixels of that colour (+/- Colour range) are kept; everything shown as a
   grey checkerboard is ignored when matching. "Remove this colour" takes
   a colour out instead, e.g. a marker that moves along the bar.
3. Apply. The image's rating tells you what was kept.

Cut-outs that keep just a few shades (a white bar and its ticks) are matched
by shape: each kept spot must still show its own shade, and the spots
around it must not - so a plain white wall can't pass for a white bar, and a
marker sliding over part of the bar only costs the pixels it covers. These
are searched at full detail, so give such steps a Search area around the bar
(about 40 ms instead of around a second for a whole screen). On a white
background a white bar genuinely can't be told apart.

Importing a PNG with transparency also gives you a cut-out: transparent
pixels are ignored. Edit cut-out / Undo bring every pixel back at any time -
the original pixels are kept in the flow file.


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


ACCESSIBILITY

- Status is never shown by colour alone. Run results in the step list carry
  a check, a cross or an arrow, and every verdict has an icon and a title.
- Secondary text meets WCAG AA contrast (about 6:1) on the dark surfaces.
- Icon-only buttons have tooltips.
- The step list works from the keyboard: Up/Down select, Ctrl+Up/Down move,
  Space turns a step on or off, T tests it, Ctrl+D duplicates, Delete
  removes. Settings > Keyboard lists them all.
- Known limit: Tk, the toolkit the app is built on, exposes little to
  screen readers. Labels are real text, but a screen reader won't announce
  the custom-drawn controls.


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

Or run every suite in the repository, Void Click included, from the root
with `python run_tests.py` (see ../TESTING.md).

Covers cut-outs (masks, shape matching through a moving marker, not
mistaking a plain patch for the shape), the plain-language image and test
explanations, the matcher (exact, downscaled, brightness-shifted, colour-strict,
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
