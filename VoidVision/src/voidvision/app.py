"""Main window: icon rail + pages, and the glue between UI, runner and screen."""

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

from . import config, draw, explain, icons, matcher, model, practice, theme
from . import widgets as w
from .overlay import CaptureOverlay, Highlight
from .page_flow import FlowPage
from .page_images import ImagesPage
from .page_settings import SettingsPage
from .runner import Runner, probe
from .screen import ScreenBackend, virtual_screen

APP_NAME = "Void Vision"
FILE_TYPES = [("Void Vision flow", "*.vflow"), ("All files", "*.*")]

class TimingResult:
    """Where the marker (and a coloured spot) were on the last Test."""
    kind = "timing"

    def __init__(self, marker, zone):
        self.marker, self.zone = marker, zone


class TestResult:
    """The last Test of a step or library image, kept so panels can show it."""

    def __init__(self, probe, verdict, confidence):
        self.probe, self.verdict, self.confidence = probe, verdict, confidence


NAV = [("flow", "flow", "Flow"), ("images", "images", "Images"), ("settings", "gear", "Settings")]


class RailButton(tk.Canvas):
    def __init__(self, master, icon, text, command):
        super().__init__(master, width=60, height=58, bg=theme.BG_RAIL, highlightthickness=0, bd=0,
                         cursor="hand2")
        self.icon, self.text, self.command = icon, text, command
        self.active = self.hover = False
        self.bind("<Enter>", lambda e: self._h(True))
        self.bind("<Leave>", lambda e: self._h(False))
        self.bind("<Button-1>", lambda e: command())
        self.redraw()

    def _h(self, v):
        self.hover = v
        self.redraw()

    def redraw(self):
        self.delete("all")
        if self.active or self.hover:
            draw.rrect(self, 4, 2, 52, 54, 10, theme.BG_FIELD if self.active else theme.BG_CARD,
                       None, theme.BG_RAIL)
        if self.active:
            draw.rrect(self, 0, 16, 3, 26, 1.5, theme.GREEN, None, theme.BG_RAIL)
        color = theme.GREEN if self.active else (theme.FG_SOFT if self.hover else theme.FG_MUTED)
        self.create_image(30, 22, image=icons.get(self.icon, 20, color))
        self.create_text(30, 44, text=self.text, fill=theme.FG if self.active else theme.FG_MUTED,
                         font=theme.font(8, "bold" if self.active else "normal"))


class MainWindow(tk.Tk):
    def __init__(self, cfg, hotkey_manager):
        super().__init__(className="VoidVision")
        theme.init(self)
        self.cfg = cfg
        self.hotkeys = hotkey_manager
        self.title(APP_NAME)
        self.geometry("1000x680")
        self.minsize(900, 600)
        self._icon = draw._cached(("winicon",), lambda: icons.render_logo(64))
        self.iconphoto(True, self._icon)
        _dark_titlebar(self)

        self.backend = ScreenBackend(virtual_screen(self))
        self.runner = Runner(self.backend,
                             on_state=lambda r, m: self.after(0, self._on_run_state, r, m),
                             on_step=lambda i, s: self.after(0, self.flow_page.set_step_status, i, s),
                             on_log=lambda m: self.after(0, self.flow_page.set_log, m))
        self.flow = model.Flow()
        self.path = None
        self.dirty = False
        self._busy = False   # a capture/test is in progress
        self.test_results = {}   # step id / "tpl:<id>" -> TestResult
        self.bar_snapshots = {}  # timing step id -> PIL image of its bar area
        self._practice = None
        self._load_initial()

        self._build()
        self.apply_settings()
        self.show("flow")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind_all("<Control-s>", lambda e: self._owns_shortcut(e) and self.save_flow())
        self.bind_all("<Control-o>", lambda e: self._owns_shortcut(e) and self.open_flow())
        self.bind_all("<Delete>", self._delete_key)
        for seq in ("<Up>", "<Down>", "<Control-Up>", "<Control-Down>", "<Home>", "<End>",
                    "<space>", "<Control-d>", "<t>"):
            self.bind_all(seq, self._list_key)

    # ------------------------------------------------------------------ build

    def _build(self):
        rail = tk.Frame(self, bg=theme.BG_RAIL, width=68)
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)
        logo = tk.Canvas(rail, width=68, height=64, bg=theme.BG_RAIL, highlightthickness=0)
        logo.pack(pady=(10, 8))
        logo.create_image(34, 32, image=icons.logo(36))
        self.nav = {}
        for key, icon, text in NAV:
            b = RailButton(rail, icon, text, lambda k=key: self.show(k))
            b.pack(pady=2)
            self.nav[key] = b
        self.live = tk.Canvas(rail, width=68, height=44, bg=theme.BG_RAIL, highlightthickness=0)
        self.live.pack(side="bottom", pady=10)
        tk.Frame(self, bg=theme.BORDER, width=1).pack(side="left", fill="y")

        self.container = tk.Frame(self, bg=theme.BG)
        self.container.pack(side="left", fill="both", expand=True)
        self.container.rowconfigure(0, weight=1)
        self.container.columnconfigure(0, weight=1)
        self.flow_page = FlowPage(self.container, self)
        self.images_page = ImagesPage(self.container, self)
        self.settings_page = SettingsPage(self.container, self)
        self.pages = {"flow": self.flow_page, "images": self.images_page,
                      "settings": self.settings_page}
        for p in self.pages.values():
            p.grid(row=0, column=0, sticky="nsew")
        self.toaster = w.Toast(self)
        self._draw_live(False)
        self.flow_page.refresh(keep_selection=False)
        self.images_page.refresh()
        self._update_title()

    def _draw_live(self, running):
        c = self.live
        c.delete("all")
        color = theme.ORANGE if running else theme.GREEN
        draw.circle(c, 34, 12, 10, color, None)
        if running:
            draw.circle(c, 34, 12, 18, theme.ORANGE_DIM, None)
            draw.circle(c, 34, 12, 10, color, None)
        c.create_text(34, 32, text="Running" if running else "Idle", fill=theme.FG_MUTED,
                      font=theme.font(8))

    def show(self, key):
        for k, b in self.nav.items():
            b.active = k == key
            b.redraw()
        self.pages[key].tkraise()
        self.current = key

    def toast(self, message, kind="info"):
        self.toaster.show(message, kind)

    def confirm(self, title, message):
        return messagebox.askyesno(title, message, parent=self)

    # ------------------------------------------------------------------ state

    def mark_dirty(self):
        if not self.dirty:
            self.dirty = True
            self._update_title()

    def _update_title(self):
        name = os.path.basename(self.path) if self.path else self.flow.name
        self.title(name + (" •" if self.dirty else "") + " — " + APP_NAME)

    def on_library_changed(self):
        self.images_page.refresh()
        self.flow_page.refresh()

    def apply_settings(self):
        cfg = self.cfg
        self.attributes("-topmost", bool(cfg["always_on_top"]))
        self.runner.poll = max(0.02, cfg["poll_ms"] / 1000.0)
        self.hotkeys.register("run", cfg["run_hotkey"], lambda: self.after(0, self.toggle_run))
        self.hotkeys.register("capture", cfg["capture_hotkey"],
                              lambda: self.after(0, self._hotkey_capture))
        self.hotkeys.register("panic", cfg["panic_hotkey"], lambda: self.after(0, self.panic))
        config.save(cfg)
        from . import hotkeys

        hk = hotkeys.label(cfg["run_hotkey"]) if cfg["run_hotkey"] else ""
        if not self.runner.running:
            self.flow_page.run_btn.configure_button(text=f"Run  {hk}".strip())

    # ------------------------------------------------------------------ files

    def _load_initial(self):
        for path in (self.cfg.get("last_flow"), str(config.autosave_path())):
            if path and os.path.exists(path):
                try:
                    self.flow = model.load_flow(path)
                    self.path = path if path == self.cfg.get("last_flow") else None
                    return
                except Exception:
                    continue

    def _discard_ok(self):
        if not self.dirty or not self.flow.steps:
            return True
        ans = messagebox.askyesnocancel("Unsaved changes", "Save changes to this flow first?",
                                        parent=self)
        if ans is None:
            return False
        if ans:
            return self.save_flow()
        return True

    def new_flow(self):
        if self.runner.running or not self._discard_ok():
            return
        self.flow, self.path, self.dirty = model.Flow(), None, False
        self.cfg["last_flow"] = ""
        self._after_load()

    def open_flow(self):
        if self.runner.running or not self._discard_ok():
            return
        path = filedialog.askopenfilename(parent=self, filetypes=FILE_TYPES, title="Open flow")
        if not path:
            return
        try:
            self.flow = model.load_flow(path)
        except Exception as exc:
            self.toast(f"Couldn't open: {exc}", "error")
            return
        self.path, self.dirty = path, False
        self.cfg["last_flow"] = path
        config.save(self.cfg)
        self._after_load()
        self.toast(f"Opened {os.path.basename(path)}", "ok")

    def save_flow(self, as_new=False):
        path = self.path
        if as_new or not path:
            path = filedialog.asksaveasfilename(parent=self, filetypes=FILE_TYPES,
                                                defaultextension=".vflow", title="Save flow",
                                                initialfile=self.flow.name + ".vflow")
            if not path:
                return False
            self.flow.name = os.path.splitext(os.path.basename(path))[0]
        try:
            model.save_flow(self.flow, path)
        except OSError as exc:
            self.toast(f"Couldn't save: {exc}", "error")
            return False
        self.path, self.dirty = path, False
        self.cfg["last_flow"] = path
        config.save(self.cfg)
        self._update_title()
        self.flow_page.refresh()
        self.toast("Saved", "ok")
        return True

    def _after_load(self):
        self.flow_page.refresh(keep_selection=False)
        self.images_page.refresh()
        self._update_title()

    def _autosave(self):
        try:
            config.data_dir().mkdir(parents=True, exist_ok=True)
            model.save_flow(self.flow, str(config.autosave_path()))
        except OSError:
            pass

    # ------------------------------------------------------------------ run

    def toggle_run(self):
        if self.runner.running:
            self.runner.stop()
        else:
            self.start_run()

    def start_run(self, start_at=0):
        if self.runner.running or self._busy:
            return
        if not self.flow.steps:
            self.toast("Add a step first", "warn")
            return
        problems = self.flow.problems()
        if problems:
            self.toast(problems[0], "error")
            self.show("flow")
            return
        self._autosave()
        if self.cfg["hide_while_running"]:
            self.iconify()
        # Give the window manager a moment to actually get the window out of
        # the way before the first screenshot.
        delay = 350 if self.cfg["hide_while_running"] else 0
        self.after(delay, lambda: self.runner.start(self.flow, start_at=start_at))

    def panic(self):
        self.runner.stop()

    def _on_run_state(self, running, message):
        self.flow_page.set_running(running)
        self._draw_live(running)
        if running:
            self.flow_page.set_status("Running", "run")
            return
        self.apply_settings()
        failed = message not in ("Finished", "Stopped")
        self.flow_page.set_status("Failed" if failed else message,
                                  "fail" if failed else ("ok" if message == "Finished" else "idle"))
        if self.state() == "iconic":
            self.deiconify()
        self.toast(message, "error" if failed else ("ok" if message == "Finished" else "info"))

    # ------------------------------------------------------------------ capture & test

    def _hotkey_capture(self):
        def done(image):
            if image is not None:
                t = self.flow.add_template(image)
                self.mark_dirty()
                self.on_library_changed()
                self.images_page.select(t)
                self.toast(f"Captured {t.name}", "ok")
        self.capture("image", done)

    def check_capture(self, image):
        """Reject unusable captures and warn, in words, about weak ones."""
        if image is None:
            return False
        if min(image.size) < 6:
            self.toast("Too small \u2014 drag a box at least 6 px each way", "warn")
            return False
        verdict = explain.image_quality(image)
        if verdict.level != explain.GOOD:
            self.toast(f"{verdict.title} \u2014 see the tips under the image", "warn")
        return True

    def capture(self, mode, on_done):
        """Hide, screenshot, let the user select, come back. mode: image|region|color."""
        if self._busy or self.runner.running:
            return
        self._busy = True
        was_iconic = self.state() == "iconic"
        self.withdraw()

        def grab():
            try:
                shot = self.backend.grab()
            except Exception as exc:
                self._busy = False
                self.deiconify()
                self.toast(f"Screen capture failed: {exc}", "error")
                return

            def finished(result):
                self._busy = False
                if not was_iconic:
                    self.deiconify()
                    self.lift()
                if mode == "image" and not self.check_capture(result):
                    result = None
                on_done(result)
            CaptureOverlay(self, shot, mode, finished)
        self.after(300, grab)

    # ------------------------------------------------------------------ timing bars

    def snapshot_bar(self, step):
        """Grab the step's bar area so the editor can draw the real bar."""
        region = step.get("region")
        if not region:
            return
        try:
            self.bar_snapshots[step.id] = self.backend.grab_fast(tuple(region)).image
        except Exception:
            self.bar_snapshots.pop(step.id, None)

    def _test_timing(self, step):
        region = step.get("region")
        if not region:
            self.toast("Set the Bar area first \u2014 drag around the bar", "warn")
            return
        image = self.backend.grab_fast(tuple(region)).image
        self.bar_snapshots[step.id] = image
        tol = int(step.get("tolerance") or 40)
        marker = matcher.marker_position(image, step.get("marker_rgb"), tol)
        zone = None
        if step.get("zone_mode") == "color":
            zone = matcher.zone_span(image, step.get("zone_rgb"), tol)
        self.test_results[step.id] = TimingResult(marker, zone)
        if marker is None:
            self.toast("Marker not seen \u2014 pick its colour with the dropper", "warn")
        elif step.get("zone_mode") == "color" and zone is None:
            self.toast("Spot colour not seen \u2014 pick it with the dropper", "warn")
        else:
            self.toast(f"Marker seen at {marker:.0%} along the bar", "ok")
        self.flow_page.on_test_result(step.id)

    def open_practice(self, step=None):
        """Open the redrawn practice bar; 'Use for my step' wires it up."""
        if self._practice is not None and self._practice.winfo_exists():
            self._practice.lift()
            return

        def use(bar):
            if step is None:
                return
            step.params["region"] = bar.bar_area()
            step.params["zone"] = [round(v, 4) for v in bar.zone_fraction()]
            step.params["marker_rgb"] = list(practice.MARKER)
            step.params["zone_rgb"] = list(practice.SPOT)
            step.params["zone_mode"] = "color" if bar.moving.get() else "fixed"
            self.test_results.pop(step.id, None)
            self.snapshot_bar(step)
            self.mark_dirty()
            self.flow_page.update_row(step)
            self.flow_page.inspector.show(step)
            self.toast("Step set up for the practice bar \u2014 press Run, then click the bar",
                       "ok")
        self._practice = practice.PracticeBar(self, on_use=use if step is not None else None)

    def test_step(self, step):
        if step.kind == "timing":
            self._test_timing(step)
            return
        if step.kind in model.IMAGE_KINDS and self.flow.template_for(step) is None:
            self.toast("Capture an image for this step first", "warn")
            return
        self._probe(step, step.id)

    def test_template(self, template):
        step = model.Step.create("click_image", template=template.id,
                                 confidence=float(self.cfg["default_confidence"]))
        self._probe(step, "tpl:" + template.id)

    def _probe(self, step, key):
        """Look once, then explain the result in the panel that asked."""
        if self._busy or self.runner.running:
            return
        self._busy = True
        hide = self.cfg["hide_while_running"]
        if hide:
            self.withdraw()
        flow = self.flow
        is_color = step.kind == "click_color"
        confidence = None if is_color else float(step.get("confidence"))

        def work():
            try:
                result, error = probe(self.backend, flow, step), None
            except Exception as exc:
                result, error = None, exc
            self.after(0, finish, result, error)

        def finish(result, error):
            self._busy = False
            if hide:
                self.deiconify()
            if error is not None:
                self.toast(f"Test failed: {error}", "error")
                return
            if is_color:
                verdict = explain.color_result(result.hit is not None)
            else:
                verdict = explain.test_result(result.score, confidence, result.hit is not None,
                                              result.elapsed_ms)
            self.test_results[key] = TestResult(result, verdict, confidence)
            kind = {"good": "ok", "ok": "warn", "weak": "error"}[verdict.level]
            self.toast(verdict.title, kind)
            hit = result.hit
            if hit is not None and self.cfg["highlight_tests"]:
                Highlight(self, hit.x, hit.y, hit.w, hit.h, f"{hit.score:.0%}")
            self.flow_page.on_test_result(key)
            self.images_page.on_test_result(key)

        self.after(300 if hide else 0, lambda: threading.Thread(target=work, daemon=True).start())

    # ------------------------------------------------------------------ misc

    def _owns_shortcut(self, e):
        """Shortcuts belong to the main window only, and never during a run.

        Bindings made with bind_all fire for every window of the app - the
        practice bar and dialogs included - so a flow pressing Space into the
        practice bar used to toggle its own step off mid-run.
        """
        if self.runner.running or self._busy:
            return False
        try:
            if e.widget.winfo_toplevel() is not self:
                return False
        except (AttributeError, tk.TclError, KeyError):
            return False
        # Typing in a field (or using a dropdown) keeps its normal keys.
        return not isinstance(e.widget, (tk.Entry, tk.Menu))

    def _list_key(self, e):
        if not self._owns_shortcut(e) or self.current != "flow":
            return None
        return self.flow_page.handle_key(e)

    def _delete_key(self, e):
        if not self._owns_shortcut(e):
            return
        if self.current == "flow":
            self.flow_page.delete_selected()

    def close(self):
        self.runner.stop()
        self.hotkeys.stop()
        self._autosave()
        config.save(self.cfg)
        self.destroy()


def _dark_titlebar(root):
    if sys.platform != "win32":
        return
    try:
        import ctypes

        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        value = ctypes.c_int(1)
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value),
                                                          ctypes.sizeof(value)) == 0:
                break
    except Exception:
        pass
