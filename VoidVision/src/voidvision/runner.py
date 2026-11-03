"""Runs a Flow on a background thread.

The runner never touches the OS directly - it drives a backend (screen.py's
ScreenBackend in the app, a fake in the tests) so every rule here is testable
without a display.
"""

import threading
import time
import traceback
from dataclasses import dataclass

from . import matcher
from .model import KINDS


@dataclass
class Hit:
    """A match translated into screen coordinates."""
    x: float
    y: float
    w: float
    h: float
    score: float
    elapsed_ms: float

    @property
    def center(self):
        return self.x + self.w / 2.0, self.y + self.h / 2.0


def _safe(cb, *args):
    if cb is None:
        return
    try:
        cb(*args)
    except Exception:
        traceback.print_exc()


@dataclass
class Probe:
    """Everything one look at the screen found - used to explain Test results."""
    hit: object            # Hit when it counts as found, else None
    score: float           # best similarity anywhere (0..1)
    closest: object        # PIL crop of the best-scoring spot, even if too weak
    elapsed_ms: float


def probe(backend, flow, step):
    """One search for an image/colour step, keeping the closest spot."""
    region = step.get("region")
    shot = backend.grab(tuple(region) if region else None)
    if step.kind == "click_color":
        m = matcher.find_color(shot.image, step.get("rgb"), int(step.get("tolerance")))
        score = 1.0 if m else 0.0
        found = m is not None
    else:
        template = flow.template_for(step)
        if template is None:
            return Probe(None, 0.0, None, 0.0)
        m = matcher.best(shot.image, template.image, color=bool(step.get("color")))
        score = m.score if m else 0.0
        found = m is not None and m.score >= float(step.get("confidence"))
    if m is None:
        return Probe(None, score, None, 0.0)
    closest = shot.image.crop((m.x, m.y, m.x + m.w, m.y + m.h))
    hit = None
    if found:
        x, y = shot.to_screen(m.x, m.y)
        w, h = shot.size_on_screen(m.w, m.h)
        hit = Hit(x, y, w, h, m.score, m.elapsed_ms)
    return Probe(hit, max(score, 0.0), closest, m.elapsed_ms)


def look_once(backend, flow, step):
    """One search for an image/colour step. Returns (Hit or None, best score)."""
    p = probe(backend, flow, step)
    return p.hit, p.score


STILL_AFTER = 0.25   # seconds of identical pictures before a marker counts as stopped


def timing_decision(x, v, zone, lead, horizon, confirmed=True):
    """When to press for a marker at `x` (0..1 along the bar).

    v          speed in bar-widths per second (None = not known yet)
    zone       (start, end) of the spot
    lead       seconds to press early (input lag)
    horizon    seconds until the next chance to decide (a picture's age plus
               the time to the next new picture)
    confirmed  whether the speed is trustworthy yet

    Returns ("press", delay_seconds) or ("wait", 0).
    """
    if x is None:
        return "wait", 0.0
    lo, hi = zone
    inside = lo <= x <= hi
    centre = (lo + hi) / 2.0
    if v is None or not confirmed:
        return "wait", 0.0                      # don't guess - look again
    if abs(v) < 1e-4:
        # Standing still: press only once it's sitting on the spot.
        return ("press", 0.0) if inside else ("wait", 0.0)
    to_centre = (centre - x) / v               # seconds until it reaches the centre
    if to_centre < 0:
        # Already past the centre, moving away. Still inside? Press now -
        # late but on the spot beats a miss.
        return ("press", 0.0) if inside else ("wait", 0.0)
    when = to_centre - lead
    if when <= horizon:
        # It gets there before the next chance to look again: time the press
        # here rather than risk skipping a narrow spot.
        return "press", max(when, 0.0)
    return "wait", 0.0


def fit_motion(samples):
    """Position and speed from recent (x, t) pictures, by least squares.

    Returns (x_now, speed, confirmed). Confirmed needs at least three
    pictures all moving the same way - one noisy pixel step can't fool it.
    """
    if not samples:
        return None, None, False
    x_last, t_last = samples[-1]
    if len(samples) < 3:
        return x_last, None, False
    ts = [t for _, t in samples]
    xs = [x for x, _ in samples]
    mt, mx = sum(ts) / len(ts), sum(xs) / len(xs)
    var = sum((t - mt) ** 2 for t in ts)
    if var <= 0:
        return x_last, None, False
    v = sum((t - mt) * (x - mx) for x, t in samples) / var
    steps = [b - a for a, b in zip(xs, xs[1:])]
    same_way = all(d > 0 for d in steps) or all(d < 0 for d in steps)
    x_now = mx + v * (t_last - mt)              # smoothed position at the last picture
    return x_now, v, same_way


class Runner:
    def __init__(self, backend, on_state=None, on_step=None, on_log=None, poll=0.12):
        self.backend = backend
        self.on_state = on_state      # (running: bool, message: str)
        self.on_step = on_step        # (index, status) status: active|ok|fail|skip
        self.on_log = on_log          # (message)
        self.poll = poll
        self._stop = threading.Event()
        self._thread = None
        self.last_error = None

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, flow, loop=None, loop_count=None, start_at=0):
        if self.running:
            return False
        self._stop.clear()
        self.last_error = None
        loop = flow.loop if loop is None else loop
        loop_count = flow.loop_count if loop_count is None else loop_count
        self._thread = threading.Thread(target=self._run, args=(flow, loop, loop_count, start_at),
                                        daemon=True, name="voidvision-runner")
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()

    def join(self, timeout=None):
        if self._thread is not None:
            self._thread.join(timeout)

    # ---------------------------------------------------------------- loop

    def _log(self, msg):
        _safe(self.on_log, msg)

    def _sleep(self, seconds):
        """Interruptible sleep. Returns False if stopped meanwhile."""
        if seconds <= 0:
            return not self._stop.is_set()
        return not self._stop.wait(seconds)

    def _run(self, flow, loop, loop_count, start_at):
        prepare = getattr(self.backend, "prepare", None)
        if prepare is not None:
            _safe(prepare)          # connect input up front (see ScreenBackend.prepare)
        _safe(self.on_state, True, "Running")
        message = "Finished"
        try:
            passes = 0
            while not self._stop.is_set():
                outcome = self._run_pass(flow, start_at)
                start_at = 0
                passes += 1
                if outcome == "stopped":
                    message = "Stopped"
                    break
                if outcome == "failed":
                    message = self.last_error or "Step failed"
                    break
                if not loop or (loop_count and passes >= loop_count):
                    break
            if self._stop.is_set() and message == "Finished":
                message = "Stopped"
        except Exception as exc:  # never leave the UI stuck in 'running'
            traceback.print_exc()
            message = f"Error: {exc}"
            self.last_error = message
        finally:
            _safe(self.on_state, False, message)

    def _run_pass(self, flow, index=0):
        steps = flow.steps
        while index < len(steps):
            if self._stop.is_set():
                return "stopped"
            step = steps[index]
            if not step.enabled:
                _safe(self.on_step, index, "skip")
                index += 1
                continue
            _safe(self.on_step, index, "active")
            result = self._run_step(flow, step, index)
            if self._stop.is_set():
                return "stopped"

            if result == "ok":
                _safe(self.on_step, index, "ok")
                index += 1
            elif isinstance(result, tuple) and result[0] == "jump":
                _safe(self.on_step, index, "ok")
                for skipped in range(index + 1, min(index + 1 + result[1], len(steps))):
                    _safe(self.on_step, skipped, "skip")
                index += 1 + result[1]
            else:  # failure
                _safe(self.on_step, index, "fail")
                policy = step.get("on_fail") or "stop"
                if policy == "skip":
                    index += 1
                elif policy == "restart":
                    # A restart with nothing in between to wait on would spin
                    # flat out; the poll pause keeps it a polite retry loop.
                    if not self._sleep(self.poll):
                        return "stopped"
                    index = 0
                else:
                    label = KINDS[step.kind]["label"]
                    self.last_error = f"Step {index + 1} ({label}) failed"
                    return "failed"
        return "done"

    # ---------------------------------------------------------------- steps

    def _search(self, flow, step, want_present=True):
        """Poll until the target is (or is no longer) visible, or timeout."""
        timeout = max(0.0, float(step.get("timeout") or 0))
        deadline = time.monotonic() + timeout
        best = 0.0
        while True:
            hit, score = look_once(self.backend, flow, step)
            best = max(best, score)
            if (hit is not None) == want_present:
                return hit if want_present else True, best
            if time.monotonic() >= deadline or self._stop.is_set():
                return None, best
            if not self._sleep(self.poll):
                return None, best

    def _run_timing(self, step, index):
        """Watch a bar; press the key when the marker reaches the spot.

        Each look measures the marker's position (0..1 along the bar) and,
        from the previous look, its speed. If the marker will reach the
        spot's centre before the next look would arrive, the press is timed
        for that moment - so a narrow spot isn't skipped between frames - and
        `lead_ms` presses that much earlier to absorb game input lag.
        """
        region = tuple(step.get("region"))
        grab = getattr(self.backend, "grab_fast", self.backend.grab)
        clock = getattr(self.backend, "clock", time.monotonic)
        sleep = getattr(self.backend, "sleep", None)
        rgb, tol = step.get("marker_rgb"), int(step.get("tolerance") or 40)
        lead = max(0, int(step.get("lead_ms") or 0)) / 1000.0
        deadline = clock() + max(0.0, float(step.get("timeout") or 0))
        zone = tuple(step.get("zone"))
        # The first grab of a run can be slow (connecting to the display,
        # warming up); take it once and throw it away so it can't skew the
        # first speed reading.
        grab(region)
        samples = []           # recent new pictures: (position, time)
        frame = 0.03           # typical time between new pictures, refined as we go
        last_change = None

        def press(where):
            self.backend.press_combo(step.get("combo"), 0)
            self._log(f"#{index + 1} pressed at {where:.0%} (spot {zone[0]:.0%}\u2013{zone[1]:.0%})")
            return "ok"

        while not self._stop.is_set():
            if clock() > deadline:
                self._log(f"#{index + 1} the marker never reached the spot")
                return "fail"
            # The picture shows the screen as it was when the grab began, so
            # that is the moment the marker was where we're about to measure.
            seen_at = clock()
            image = grab(region).image
            if step.get("zone_mode") == "color":
                span = matcher.zone_span(image, step.get("zone_rgb"), tol, bridge_rgb=rgb)
                if span is not None:
                    zone = span    # keep the last place it was seen if hidden
            x = matcher.marker_position(image, rgb, tol)
            if x is not None:
                if not samples or abs(x - samples[-1][0]) > 1e-6:
                    # A new picture. Looks often outpace the screen redrawing;
                    # a repeated picture says nothing about speed, so only
                    # pictures that changed are used to measure it.
                    if len(samples) >= 2:
                        d_old = samples[-1][0] - samples[-2][0]
                        if d_old * (x - samples[-1][0]) < 0:
                            samples = samples[-1:]      # it bounced: start fresh
                    if samples:
                        frame = min(0.7 * frame + 0.3 * max(seen_at - samples[-1][1], 0.001),
                                    0.1)
                    samples.append((x, seen_at))
                    samples = [p for p in samples if seen_at - p[1] <= 0.15][-8:]
                    last_change = seen_at
                x_now, v, confirmed = fit_motion(samples)
                if last_change is not None and seen_at - last_change > STILL_AFTER:
                    v, confirmed = 0.0, True            # genuinely not moving
                # Next chance to decide: this picture's age (grab + work so
                # far) plus the wait for another new picture.
                horizon = (clock() - samples[-1][1]) + 1.5 * frame
                action, delay = timing_decision(x_now, v, zone, lead, horizon, confirmed)
                if action == "press":
                    delay -= clock() - samples[-1][1]   # time since that picture
                    if delay > 0:
                        if sleep:
                            sleep(delay)
                        elif not self._sleep(delay):
                            return "fail"
                    return press(x_now)
            # Yield briefly; the grab itself paces the loop.
            if sleep:
                sleep(0.001)
            elif not self._sleep(0.001):
                return "fail"
        return "fail"

    def _act(self, action, x, y):
        b = self.backend
        b.move(x, y)
        if action == "click":
            b.click("left", 1)
        elif action == "double":
            b.click("left", 2)
        elif action == "right":
            b.click("right", 1)

    def _run_step(self, flow, step, index):
        k = step.kind
        b = self.backend

        if k in ("click_image", "click_color"):
            hit, best = self._search(flow, step)
            if hit is None:
                self._log(f"#{index + 1} not found (best {best:.0%})" if k == "click_image"
                          else f"#{index + 1} colour not found")
                return "fail"
            cx, cy = hit.center
            cx += int(step.get("offset_x") or 0)
            cy += int(step.get("offset_y") or 0)
            self._act(step.get("action"), cx, cy)
            self._log(f"#{index + 1} found {hit.score:.0%} at {int(cx)},{int(cy)}")
            return "ok"

        if k == "wait_image":
            appear = step.get("mode") == "appear"
            result, best = self._search(flow, step, want_present=appear)
            if not result:
                self._log(f"#{index + 1} timed out")
                return "fail"
            return "ok"

        if k == "if_image":
            hit, _ = self._search(flow, step)
            visible = hit is not None
            if visible != bool(step.get("negate")):
                return "ok"
            n = max(0, int(step.get("skip") or 0))
            self._log(f"#{index + 1} condition false, skipping {n}")
            return ("jump", n)

        if k == "click":
            count = max(1, int(step.get("count") or 1))
            gap = max(0, int(step.get("interval") or 0)) / 1000.0
            for i in range(count):
                if self._stop.is_set():
                    break
                b.click(step.get("button") or "left", 1)
                if i < count - 1 and not self._sleep(gap):
                    break
            return "ok"

        if k == "key":
            b.press_combo(step.get("combo"), int(step.get("hold_ms") or 0))
            return "ok"

        if k == "type":
            b.type_text(str(step.get("text") or ""))
            return "ok"

        if k == "scroll":
            b.scroll(int(step.get("amount") or 0))
            return "ok"

        if k == "wait":
            self._sleep(float(step.get("seconds") or 0))
            return "ok"

        if k == "timing":
            return self._run_timing(step, index)

        raise ValueError(f"unknown step kind {k}")
