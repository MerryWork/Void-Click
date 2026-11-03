"""Core tests - matcher, model, file format, runner rules, hotkey helpers.

Run with either of:

    python tests/test_core.py
    python -m unittest discover tests

No display is needed: the runner is driven through a fake backend, so nothing
here moves the real mouse or presses real keys.
"""

import os
import sys
import tempfile
import threading
import time
import unittest

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from voidvision import config, hotkeys, matcher, model  # noqa: E402
from voidvision.model import Flow, Step  # noqa: E402
from voidvision.runner import Runner, look_once  # noqa: E402
from voidvision.screen import Shot  # noqa: E402


# ---------------------------------------------------------------- helpers

def noise(h, w, seed=0):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, (h, w, 3), dtype=np.uint8)


def desktop(w=640, h=400):
    """A UI-ish screen: flat panels, some text-like noise, a few buttons."""
    img = Image.new("RGB", (w, h), (24, 26, 32))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w, 30], fill=(40, 44, 52))
    for i in range(8):
        d.text((10 + i * 70, 8), f"Menu{i}", fill=(200, 200, 200))
    d.rectangle([40, 60, 600, 360], fill=(32, 35, 42))
    for row in range(10):
        d.text((60, 80 + row * 22), "lorem ipsum dolor sit amet " * 2, fill=(150, 150, 160))
    return img


def button(text, fill, size=(90, 30)):
    img = Image.new("RGB", size, fill)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, size[0] - 1, size[1] - 1], outline=(255, 255, 255))
    d.text((10, 9), text, fill=(255, 255, 255))
    return img


class FakeBackend:
    """Screen is a PIL image that steps can change; input is recorded."""

    def __init__(self, screen, scale=1.0, left=0, top=0):
        self.screen = screen
        self.scale, self.left, self.top = scale, left, top
        self.events = []
        self.grabs = 0
        self.on_grab = None

    def grab(self, region=None):
        self.grabs += 1
        if self.on_grab:
            self.on_grab(self)
        img = self.screen
        if region:
            x, y, w, h = region
            s = self.scale
            box = (int((x - self.left) * s), int((y - self.top) * s),
                   int((x - self.left + w) * s), int((y - self.top + h) * s))
            return Shot(img.crop(box), x, y, self.scale)
        return Shot(img.copy(), self.left, self.top, self.scale)

    def move(self, x, y):
        self.events.append(("move", round(x), round(y)))

    def click(self, button="left", count=1):
        self.events.append(("click", button, count))

    def scroll(self, amount):
        self.events.append(("scroll", amount))

    def press_combo(self, combo, hold_ms=0):
        self.events.append(("key", combo, hold_ms))

    def type_text(self, text):
        self.events.append(("type", text))


def run_sync(runner, flow, timeout=10, **kw):
    states = []
    done = threading.Event()

    def on_state(running, message):
        states.append((running, message))
        if not running:
            done.set()

    runner.on_state = on_state
    runner.start(flow, **kw)
    assert done.wait(timeout), "runner did not finish"
    runner.join(1)
    return states[-1][1]


# ---------------------------------------------------------------- matcher

class MatcherTests(unittest.TestCase):
    def test_exact_match_on_noise(self):
        hay = noise(300, 500, 1)
        for (y, x, h, w) in ((10, 20, 12, 30), (150, 300, 40, 90), (200, 380, 80, 110)):
            m = matcher.find(hay, hay[y:y + h, x:x + w].copy(), 0.9)
            self.assertIsNotNone(m)
            self.assertEqual((m.x, m.y, m.w, m.h), (x, y, w, h))
            self.assertGreater(m.score, 0.99)

    def test_downscaled_path_on_big_screen(self):
        # Large haystack + large template triggers the coarse-to-fine search.
        hay = noise(900, 1400, 2)
        t = hay[500:580, 900:1020].copy()
        m = matcher.find(hay, t, 0.9)
        self.assertEqual((m.x, m.y), (900, 500))

    def test_button_on_desktop(self):
        screen = desktop()
        b = button("Claim", (45, 108, 223))
        screen.paste(b, (300, 200))
        m = matcher.find(screen, b, 0.9)
        self.assertEqual((m.x, m.y), (300, 200))
        cx, cy = m.center
        self.assertEqual((cx, cy), (345.0, 215.0))

    def test_tolerates_brightness_change(self):
        screen = desktop()
        b = button("OK", (31, 143, 78))
        screen.paste(b, (100, 120))
        arr = np.asarray(screen).astype(float) * 0.8 + 25
        dimmed = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        m = matcher.find(dimmed, b, 0.9)
        self.assertEqual((m.x, m.y), (100, 120))

    def test_absent_returns_none_and_best_reports_score(self):
        screen = desktop()
        b = button("Missing", (200, 40, 40))
        self.assertIsNone(matcher.find(screen, b, 0.9))
        best = matcher.best(screen, b)
        self.assertIsNotNone(best)
        self.assertLess(best.score, 0.9)

    def test_color_mode_rejects_same_shape_different_colour(self):
        screen = desktop()
        red = button("Go", (200, 50, 50))
        # Same luminance, different hue.
        lum_red = 0.299 * 200 + 0.587 * 50 + 0.114 * 50
        g = int(round((lum_red - 0.299 * 50 - 0.114 * 50) / 0.587))
        green = button("Go", (50, g, 50))
        screen.paste(green, (60, 100))
        self.assertIsNotNone(matcher.find(screen, red, 0.9, color=False))
        self.assertIsNone(matcher.find(screen, red, 0.9, color=True))
        screen.paste(red, (400, 250))
        m = matcher.find(screen, red, 0.9, color=True)
        self.assertEqual((m.x, m.y), (400, 250))

    def test_flat_template(self):
        screen = desktop()
        ImageDraw.Draw(screen).rectangle([500, 300, 539, 329], fill=(255, 157, 69))
        swatch = Image.new("RGB", (20, 15), (255, 157, 69))
        m = matcher.find(screen, swatch, 0.9)
        self.assertIsNotNone(m)
        self.assertTrue(500 <= m.x <= 520 and 300 <= m.y <= 315)

    def test_find_all(self):
        screen = desktop()
        b = button("X", (90, 90, 200), (40, 26))
        spots = [(60, 100), (200, 100), (340, 260)]
        for p in spots:
            screen.paste(b, p)
        found = matcher.find_all(screen, b, 0.95)
        self.assertEqual(sorted((m.x, m.y) for m in found), sorted(spots))

    def test_template_bigger_than_haystack(self):
        self.assertIsNone(matcher.find(noise(20, 20), noise(40, 40), 0.5))

    def test_find_color(self):
        screen = desktop()
        ImageDraw.Draw(screen).rectangle([200, 150, 229, 169], fill=(255, 157, 69))
        m = matcher.find_color(screen, (250, 160, 70), tolerance=12)
        self.assertEqual((m.x, m.y, m.w, m.h), (200, 150, 30, 20))
        self.assertIsNone(matcher.find_color(screen, (0, 255, 255), tolerance=5))

    def test_fast_len(self):
        for n in (1, 7, 17, 1000, 1091, 1949):
            f = matcher._fast_len(n)
            self.assertGreaterEqual(f, n)
            r = f
            for p in (2, 3, 5):
                while r % p == 0:
                    r //= p
            self.assertEqual(r, 1)


# ---------------------------------------------------------------- model

class ModelTests(unittest.TestCase):
    def test_defaults_for_every_kind(self):
        flow = Flow()
        for kind in model.KINDS:
            step = Step.create(kind)
            for key, *_ in model.KINDS[kind]["fields"]:
                self.assertIn(key, step.params)
            self.assertIsInstance(model.summary(step, flow), str)

    def test_unknown_kind_rejected(self):
        with self.assertRaises(ValueError):
            Step.create("teleport")

    def test_round_trip(self):
        flow = Flow(name="Test", loop=True, loop_count=3)
        t = flow.add_template(button("Hi", (10, 20, 30)))
        flow.steps = [Step.create("click_image", template=t.id, offset_x=5),
                      Step.create("key", combo="ctrl+s"), Step.create("wait", seconds=0.5)]
        flow.steps[1].enabled = False
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.vflow")
            model.save_flow(flow, path)
            back = model.load_flow(path)
        self.assertEqual(back.name, "Test")
        self.assertTrue(back.loop)
        self.assertEqual(back.loop_count, 3)
        self.assertEqual([s.kind for s in back.steps], ["click_image", "key", "wait"])
        self.assertFalse(back.steps[1].enabled)
        self.assertEqual(back.steps[0].params["offset_x"], 5)
        bt = back.templates[t.id]
        self.assertEqual(bt.size, t.size)
        self.assertEqual(bt.image.tobytes(), t.image.tobytes())

    def test_load_ignores_unknown_params_and_fills_missing(self):
        d = {"format": model.FORMAT, "steps": [{"kind": "wait", "params": {"bogus": 1}}],
             "templates": []}
        flow = Flow.from_dict(d)
        self.assertNotIn("bogus", flow.steps[0].params)
        self.assertEqual(flow.steps[0].params["seconds"], 1.0)

    def test_rejects_foreign_json(self):
        with self.assertRaises(ValueError):
            Flow.from_dict({"steps": []})

    def test_remove_template_clears_references(self):
        flow = Flow()
        t = flow.add_template(button("A", (1, 2, 3)))
        flow.steps = [Step.create("click_image", template=t.id)]
        self.assertEqual(flow.usage(t.id), 1)
        flow.remove_template(t.id)
        self.assertIsNone(flow.steps[0].params["template"])
        self.assertEqual(len(flow.problems()), 1)

    def test_template_names_are_unique(self):
        flow = Flow()
        a = flow.add_template(button("A", (1, 2, 3)))
        b = flow.add_template(button("B", (1, 2, 3)))
        self.assertNotEqual(a.name, b.name)

    def test_clone_is_independent(self):
        s = Step.create("click_color", rgb=[1, 2, 3])
        c = s.clone()
        c.params["rgb"][0] = 99
        self.assertEqual(s.params["rgb"][0], 1)
        self.assertNotEqual(s.id, c.id)


# ---------------------------------------------------------------- runner

class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.screen = desktop()
        self.claim = button("Claim", (45, 108, 223))
        self.flow = Flow()
        self.tid = self.flow.add_template(self.claim).id

    def _runner(self, backend):
        return Runner(backend, poll=0.01)

    def test_click_image_clicks_centre_plus_offset(self):
        self.screen.paste(self.claim, (300, 200))
        b = FakeBackend(self.screen)
        self.flow.steps = [Step.create("click_image", template=self.tid, offset_x=10, offset_y=-5)]
        self.assertEqual(run_sync(self._runner(b), self.flow), "Finished")
        self.assertEqual(b.events, [("move", 355, 210), ("click", "left", 1)])

    def test_actions(self):
        self.screen.paste(self.claim, (300, 200))
        for action, expect in (("double", [("click", "left", 2)]), ("right", [("click", "right", 1)]),
                               ("move", [])):
            b = FakeBackend(self.screen)
            self.flow.steps = [Step.create("click_image", template=self.tid, action=action)]
            run_sync(self._runner(b), self.flow)
            self.assertEqual(b.events[1:], expect, action)

    def test_retina_scale_and_origin(self):
        # Screenshot at 2x, desktop origin at (-100, 50): clicks must come out
        # in screen coordinates, not image pixels.
        big = self.screen.resize((self.screen.width * 2, self.screen.height * 2))
        claim2 = self.claim.resize((self.claim.width * 2, self.claim.height * 2))
        big.paste(claim2, (600, 400))
        flow = Flow()
        t = flow.add_template(claim2)
        flow.steps = [Step.create("click_image", template=t.id)]
        b = FakeBackend(big, scale=2.0, left=-100, top=50)
        run_sync(self._runner(b), flow)
        self.assertEqual(b.events[0], ("move", -100 + 345, 50 + 215))

    def test_region_search(self):
        self.screen.paste(self.claim, (300, 200))
        b = FakeBackend(self.screen)
        self.flow.steps = [Step.create("click_image", template=self.tid, region=[250, 150, 200, 120])]
        run_sync(self._runner(b), self.flow)
        self.assertEqual(b.events[0], ("move", 345, 215))
        # Same target outside the region is not found.
        self.flow.steps = [Step.create("click_image", template=self.tid, region=[0, 0, 200, 120],
                                       timeout=0)]
        b2 = FakeBackend(self.screen)
        self.assertIn("failed", run_sync(self._runner(b2), self.flow))

    def test_not_found_stops_with_message(self):
        b = FakeBackend(self.screen)
        self.flow.steps = [Step.create("click_image", template=self.tid, timeout=0),
                           Step.create("key", combo="a")]
        msg = run_sync(self._runner(b), self.flow)
        self.assertEqual(msg, "Step 1 (Find & click) failed")
        self.assertEqual(b.events, [])

    def test_on_fail_skip(self):
        b = FakeBackend(self.screen)
        self.flow.steps = [Step.create("click_image", template=self.tid, timeout=0, on_fail="skip"),
                           Step.create("key", combo="a")]
        self.assertEqual(run_sync(self._runner(b), self.flow), "Finished")
        self.assertEqual(b.events, [("key", "a", 0)])

    def test_on_fail_restart_until_found(self):
        b = FakeBackend(self.screen)
        claim = self.claim

        def appear_late(backend):
            if backend.grabs == 4:
                backend.screen = backend.screen.copy()
                backend.screen.paste(claim, (100, 100))
        b.on_grab = appear_late
        self.flow.steps = [Step.create("key", combo="r"),
                           Step.create("click_image", template=self.tid, timeout=0,
                                       on_fail="restart")]
        self.assertEqual(run_sync(self._runner(b), self.flow), "Finished")
        self.assertEqual([e for e in b.events if e[0] == "key"], [("key", "r", 0)] * 4)
        self.assertEqual(b.events[-1], ("click", "left", 1))

    def test_waits_until_image_appears(self):
        b = FakeBackend(self.screen)
        claim = self.claim

        def appear(backend):
            if backend.grabs == 3:
                backend.screen = backend.screen.copy()
                backend.screen.paste(claim, (50, 300))
        b.on_grab = appear
        self.flow.steps = [Step.create("wait_image", template=self.tid, timeout=5)]
        self.assertEqual(run_sync(self._runner(b), self.flow), "Finished")
        self.assertEqual(b.grabs, 3)

    def test_wait_vanish_and_timeout(self):
        self.screen.paste(self.claim, (50, 300))
        b = FakeBackend(self.screen)
        self.flow.steps = [Step.create("wait_image", template=self.tid, mode="vanish", timeout=0.05)]
        self.assertIn("failed", run_sync(self._runner(b), self.flow))
        clean = desktop()

        def vanish(backend):
            if backend.grabs == 2:
                backend.screen = clean
        b2 = FakeBackend(self.screen)
        b2.on_grab = vanish
        self.assertEqual(run_sync(self._runner(b2), self.flow), "Finished")

    def test_if_visible_skips_when_absent(self):
        b = FakeBackend(self.screen)
        self.flow.steps = [Step.create("if_image", template=self.tid, skip=2),
                           Step.create("key", combo="a"), Step.create("key", combo="b"),
                           Step.create("key", combo="c")]
        statuses = []
        r = self._runner(b)
        r.on_step = lambda i, s: statuses.append((i, s))
        run_sync(r, self.flow)
        self.assertEqual(b.events, [("key", "c", 0)])
        self.assertIn((1, "skip"), statuses)
        self.assertIn((2, "skip"), statuses)

    def test_if_visible_runs_when_present_and_negate(self):
        self.screen.paste(self.claim, (10, 40))
        b = FakeBackend(self.screen)
        self.flow.steps = [Step.create("if_image", template=self.tid, skip=1),
                           Step.create("key", combo="a"), Step.create("key", combo="b")]
        run_sync(self._runner(b), self.flow)
        self.assertEqual([e[1] for e in b.events], ["a", "b"])
        b2 = FakeBackend(self.screen)
        self.flow.steps[0].params["negate"] = True
        run_sync(self._runner(b2), self.flow)
        self.assertEqual([e[1] for e in b2.events], ["b"])

    def test_click_color(self):
        ImageDraw.Draw(self.screen).rectangle([200, 150, 229, 169], fill=(255, 157, 69))
        b = FakeBackend(self.screen)
        self.flow.steps = [Step.create("click_color", rgb=[255, 157, 69], tolerance=5)]
        run_sync(self._runner(b), self.flow)
        self.assertEqual(b.events, [("move", 215, 160), ("click", "left", 1)])

    def test_input_steps(self):
        b = FakeBackend(self.screen)
        self.flow.steps = [Step.create("click", button="right", count=3, interval=0),
                           Step.create("key", combo="ctrl+c", hold_ms=0),
                           Step.create("type", text="hey"), Step.create("scroll", amount=-2),
                           Step.create("wait", seconds=0.01)]
        run_sync(self._runner(b), self.flow)
        self.assertEqual(b.events, [("click", "right", 1)] * 3 + [
            ("key", "ctrl+c", 0), ("type", "hey"), ("scroll", -2)])

    def test_disabled_steps_are_skipped(self):
        b = FakeBackend(self.screen)
        self.flow.steps = [Step.create("key", combo="a"), Step.create("key", combo="b")]
        self.flow.steps[0].enabled = False
        run_sync(self._runner(b), self.flow)
        self.assertEqual(b.events, [("key", "b", 0)])

    def test_loop_count(self):
        b = FakeBackend(self.screen)
        self.flow.steps = [Step.create("key", combo="a")]
        run_sync(self._runner(b), self.flow, loop=True, loop_count=4)
        self.assertEqual(len(b.events), 4)

    def test_loop_forever_until_stopped(self):
        b = FakeBackend(self.screen)
        self.flow.steps = [Step.create("wait", seconds=0.005)]
        r = self._runner(b)
        states = []
        r.on_state = lambda run, msg: states.append(msg)
        r.start(self.flow, loop=True, loop_count=0)
        time.sleep(0.15)
        self.assertTrue(r.running)
        r.stop()
        r.join(2)
        self.assertFalse(r.running)
        self.assertEqual(states[-1], "Stopped")

    def test_stop_interrupts_long_wait(self):
        b = FakeBackend(self.screen)
        self.flow.steps = [Step.create("wait", seconds=30), Step.create("key", combo="a")]
        r = self._runner(b)
        r.start(self.flow)
        time.sleep(0.05)
        t0 = time.monotonic()
        r.stop()
        r.join(2)
        self.assertLess(time.monotonic() - t0, 1.0)
        self.assertEqual(b.events, [])

    def test_start_at(self):
        b = FakeBackend(self.screen)
        self.flow.steps = [Step.create("key", combo="a"), Step.create("key", combo="b")]
        run_sync(self._runner(b), self.flow, start_at=1)
        self.assertEqual(b.events, [("key", "b", 0)])

    def test_backend_error_does_not_wedge_runner(self):
        class Broken(FakeBackend):
            def press_combo(self, combo, hold_ms=0):
                raise RuntimeError("boom")
        b = Broken(self.screen)
        self.flow.steps = [Step.create("key", combo="a")]
        r = self._runner(b)
        msg = run_sync(r, self.flow)
        self.assertIn("boom", msg)
        self.assertFalse(r.running)
        self.assertTrue(r.start(self.flow))  # can start again
        r.stop()
        r.join(2)

    def test_look_once_reports_best_score_when_missing(self):
        b = FakeBackend(self.screen)
        step = Step.create("click_image", template=self.tid)
        hit, best = look_once(b, self.flow, step)
        self.assertIsNone(hit)
        self.assertLess(best, 0.85)


class ExplainTests(unittest.TestCase):
    """The plain-language wording people see about images and test results."""

    def test_strictness_words(self):
        from voidvision import explain
        self.assertEqual(explain.strictness(0.6), "Loose")
        self.assertEqual(explain.strictness(0.85), "Balanced")
        self.assertEqual(explain.strictness(0.92), "Strict")
        self.assertEqual(explain.strictness(1.0), "Exact")

    def test_image_quality_levels(self):
        from voidvision import explain
        self.assertEqual(explain.image_quality(button("Claim", (45, 108, 223))).level, explain.GOOD)
        flat = explain.image_quality(Image.new("RGB", (60, 30), (255, 157, 69)))
        self.assertEqual((flat.level, flat.title), (explain.WEAK, "One flat colour"))
        self.assertIn("Find colour", flat.detail)
        tiny = explain.image_quality(button("", (9, 9, 9), (5, 5)))
        self.assertEqual(tiny.title, "Very small")
        # A soft gradient: has variation but no edges or text.
        grad = Image.linear_gradient("L").resize((80, 40)).convert("RGB")
        self.assertEqual(explain.image_quality(grad).title, "Low detail")
        big = Image.fromarray(noise(400, 600))
        self.assertEqual(explain.image_quality(big).title, "Large")

    def test_test_result_wording(self):
        from voidvision import explain
        v = explain.test_result(0.99, 0.85, True, 120)
        self.assertEqual(v.level, explain.GOOD)
        self.assertIn("120 ms", v.detail)
        self.assertEqual(explain.test_result(0.9, 0.85, True).title, "Found")
        almost = explain.test_result(0.79, 0.85, False)
        self.assertEqual(almost.level, explain.OK)
        self.assertIn("lower Match to 77%", almost.detail)   # a concrete, working number
        self.assertLess(0.77, 0.79)
        gone = explain.test_result(0.3, 0.85, False)
        self.assertEqual((gone.level, gone.title), (explain.WEAK, "Not on screen"))
        self.assertEqual(explain.color_result(False).level, explain.WEAK)

    def test_probe_keeps_closest_spot_when_too_weak(self):
        from voidvision.runner import probe
        screen = desktop()
        claim = button("Claim", (45, 108, 223))
        screen.paste(claim, (300, 200))
        flow = Flow()
        t = flow.add_template(claim)
        step = Step.create("click_image", template=t.id, confidence=0.85)
        p = probe(FakeBackend(screen), flow, step)
        self.assertIsNotNone(p.hit)
        self.assertEqual(p.closest.size, claim.size)
        # Demand more than is possible: not "found", but we still see where it looked.
        step.params["confidence"] = 1.01
        p = probe(FakeBackend(screen), flow, step)
        self.assertIsNone(p.hit)
        self.assertGreater(p.score, 0.99)
        self.assertEqual(p.closest.tobytes(), claim.tobytes())


def timing_bar(behind=(230, 200, 40)):
    """A white tick bar with a red marker, drawn over something coloured -
    the shape of a game's timing meter."""
    img = Image.new("RGB", (200, 40), (209, 216, 229))
    d = ImageDraw.Draw(img)
    d.rectangle([80, 5, 120, 38], fill=behind)            # a character behind the bar
    d.rectangle([10, 18, 190, 21], fill=(255, 255, 255))
    for x in range(10, 191, 20):
        d.rectangle([x, 12, x + 1, 27], fill=(255, 255, 255))
    d.rectangle([150, 8, 154, 31], fill=(230, 20, 20))      # moving marker
    return img


class CutoutTests(unittest.TestCase):
    def test_keep_colour_makes_a_mask(self):
        from voidvision import cutout
        bar = timing_bar()
        cut = cutout.keep_colors(bar, [(255, 255, 255)], 30)
        self.assertTrue(cutout.is_cutout(cut))
        mask = matcher.mask_of(cut)
        self.assertTrue(mask[19, 50])           # the white bar is kept
        self.assertFalse(mask[8, 100])          # the character behind it is not
        self.assertFalse(mask[20, 152])         # nor the red marker
        self.assertLess(cutout.kept_fraction(cut), 0.25)
        self.assertFalse(cutout.is_cutout(cutout.clear(cut)))

    def test_build_keep_then_remove(self):
        from voidvision import cutout
        bar = timing_bar()
        everything_but_red = cutout.build(bar, remove=[(230, 20, 20)], tolerance=20)
        m = matcher.mask_of(everything_but_red)
        self.assertFalse(m[20, 152])
        self.assertTrue(m[19, 50])
        self.assertFalse(cutout.is_cutout(cutout.build(bar)))   # nothing picked = no cut-out

    def test_cutout_matches_on_a_different_background(self):
        from voidvision import cutout
        cut = cutout.keep_colors(timing_bar(), [(255, 255, 255)], 30)
        screen = desktop(800, 500)
        # The same bar, but the character behind it changed colour and the
        # marker moved: a plain capture no longer matches, the cut-out does.
        moved = timing_bar(behind=(40, 90, 200))
        d = ImageDraw.Draw(moved)
        d.rectangle([150, 8, 154, 31], fill=(209, 216, 229))
        d.rectangle([30, 8, 34, 31], fill=(230, 20, 20))
        screen.paste(moved, (420, 300))
        m = matcher.find(screen, cut, 0.9)
        self.assertIsNotNone(m)
        self.assertEqual((m.x, m.y), (420, 300))
        plain = matcher.best(screen, timing_bar())
        self.assertLess(plain.score, m.score)

    def test_cutout_is_not_fooled_by_a_plain_patch_of_its_colour(self):
        from voidvision import cutout
        cut = cutout.keep_colors(timing_bar(), [(255, 255, 255)], 30)
        screen = Image.new("RGB", (700, 400), (120, 170, 220))
        ImageDraw.Draw(screen).rectangle([0, 0, 320, 220], fill=(255, 255, 255))
        best = matcher.best(screen, cut)
        self.assertLess(best.score, 0.85)        # a white wall is not a tick bar
        screen.paste(timing_bar(behind=(90, 90, 90)), (400, 300))
        m = matcher.find(screen, cut, 0.85)
        self.assertEqual((m.x, m.y), (400, 300))

    def test_cutout_found_on_many_backgrounds_at_full_size(self):
        # Thin shapes vanish when downscaled; big screens must still find them.
        from voidvision import cutout
        cut = cutout.keep_colors(timing_bar(), [(255, 255, 255)], 30)
        mask = matcher.mask_of(cut)
        bar = np.asarray(timing_bar())
        for bg in ((120, 170, 220), (200, 200, 200), (235, 238, 245), (30, 30, 40)):
            arr = np.zeros((700, 1000, 3), np.uint8)
            arr[:] = bg
            spot = arr[500:540, 600:800]
            spot[mask] = bar[mask]
            spot[8:31, 40:45] = (230, 20, 20)             # marker over the bar
            m = matcher.find(arr, cut, 0.85)
            self.assertIsNotNone(m, bg)
            self.assertEqual((m.x, m.y), (600, 500), bg)

    def test_masked_ncc_with_detail(self):
        # A cut-out that keeps varied pixels uses true masked NCC.
        hay = noise(300, 400, 5)
        t = hay[100:150, 200:280].copy()
        rgba = np.dstack([t, np.full(t.shape[:2], 255, np.uint8)])
        rgba[:20, :30, 3] = 0                                 # ignore a corner
        hay2 = hay.copy()
        hay2[100:120, 200:230] = 0                            # which changed on screen
        m = matcher.find(hay2, Image.fromarray(rgba, "RGBA"), 0.95)
        self.assertEqual((m.x, m.y), (200, 100))

    def test_cutout_survives_save_and_load(self):
        from voidvision import cutout
        flow = Flow()
        t = flow.add_template(cutout.keep_colors(timing_bar(), [(255, 255, 255)], 30))
        self.assertTrue(t.is_cutout)
        back = Flow.from_dict(flow.to_dict())
        bt = back.templates[t.id]
        self.assertTrue(bt.is_cutout)
        np.testing.assert_array_equal(matcher.mask_of(bt.image), matcher.mask_of(t.image))
        plain = flow.add_template(timing_bar())
        self.assertFalse(plain.is_cutout)

    def test_quality_explains_cutouts(self):
        from voidvision import cutout, explain
        cut = cutout.keep_colors(timing_bar(), [(255, 255, 255)], 30)
        v = explain.image_quality(cut)
        self.assertEqual(v.title, "Cut-out — shape only")
        self.assertIn("ignored", v.detail)
        tiny = cutout.keep_colors(timing_bar(), [(230, 20, 20)], 5)
        self.assertEqual(explain.image_quality(tiny).level, explain.WEAK)


class ScreenBackendTests(unittest.TestCase):
    def test_region_crop_keeps_retina_scale(self):
        from unittest import mock

        from voidvision.screen import ScreenBackend

        full = Image.new("RGB", (2000, 1200), (0, 0, 0))
        ImageDraw.Draw(full).rectangle([600, 400, 619, 409], fill=(255, 0, 0))
        backend = ScreenBackend((0, 0, 1000, 600))      # screen in points, image at 2x
        with mock.patch("PIL.ImageGrab.grab", return_value=full):
            shot = backend.grab((250, 150, 200, 100))
            whole = backend.grab()
        self.assertEqual(shot.scale, 2.0)
        self.assertEqual(shot.image.size, (400, 200))
        self.assertEqual(shot.to_screen(100, 100), (300.0, 200.0))   # the red box, in points
        self.assertEqual(whole.to_screen(600, 400), (300.0, 200.0))
        with mock.patch("PIL.ImageGrab.grab", return_value=full):
            off = backend.grab((5000, 5000, 10, 10))
        self.assertEqual(off.image.size, (1, 1))


# ---------------------------------------------------------------- misc

class HotkeyAndConfigTests(unittest.TestCase):
    def test_normalize_and_label(self):
        self.assertEqual(hotkeys.normalize(["f9", "shift", "ctrl"]), "ctrl+shift+f9")
        self.assertEqual(hotkeys.label("ctrl+f9"), "Ctrl + F9")
        self.assertEqual(hotkeys.label("mouse_x1"), "Mouse 4")
        self.assertEqual(hotkeys.label(""), "Not set")

    def test_matches(self):
        held = frozenset({"w", "ctrl", "f9"})
        self.assertTrue(hotkeys.matches("ctrl+f9", held, "f9"))
        self.assertFalse(hotkeys.matches("ctrl+f9", held, "w"))
        self.assertFalse(hotkeys.matches("alt+f9", held, "f9"))
        self.assertFalse(hotkeys.matches("", held, "f9"))

    def test_manager_fires_most_specific(self):
        m = hotkeys.HotkeyManager()
        fired = []
        m.register("a", "f9", lambda: fired.append("a"))
        m.register("b", "ctrl+f9", lambda: fired.append("b"))
        m._press("ctrl")
        m._press("f9")
        self.assertEqual(fired, ["b"])
        m._held.clear()
        m._press("f9")
        self.assertEqual(fired, ["b", "a"])

    def test_manager_capture(self):
        m = hotkeys.HotkeyManager()
        got = []
        m.capture_next(got.append)
        m._press("shift")
        m._press("mouse_left")    # ignored
        m._press("g")
        self.assertEqual(got, ["shift+g"])

    def test_config_merge(self):
        cfg = config.merge({"poll_ms": 50, "always_on_top": "yes", "default_confidence": 1,
                            "junk": 1})
        self.assertEqual(cfg["poll_ms"], 50)
        self.assertFalse(cfg["always_on_top"])      # wrong type ignored
        self.assertEqual(cfg["default_confidence"], 1.0)
        self.assertNotIn("junk", cfg)
        self.assertEqual(config.merge(None), config.DEFAULTS)

    def test_config_save_load(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "sub", "c.json")
            cfg = dict(config.DEFAULTS, run_hotkey="f6")
            config.save(cfg, p)
            self.assertEqual(config.load(p)["run_hotkey"], "f6")
            self.assertEqual(config.load(os.path.join(d, "none.json")), config.DEFAULTS)


if __name__ == "__main__":
    unittest.main(verbosity=1)
