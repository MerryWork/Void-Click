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

        raise ValueError(f"unknown step kind {k}")
