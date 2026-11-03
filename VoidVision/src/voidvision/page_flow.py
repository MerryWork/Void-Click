"""Flow page: the step list on the left, the selected step's inspector on the right."""

import tkinter as tk

from PIL import Image, ImageTk

from . import draw, explain, icons, model, theme
from .cutout_dialog import open_cutout
from .insight import ComparePanel, QualityLine, preview
from . import widgets as w
from .model import KINDS, Step

ROW_H = 60
ROW_GAP = 6

QUICK_ADD = [("click_image", "Find & click"), ("wait_image", "Wait for image"),
             ("if_image", "If visible"), ("click_color", "Find colour"), ("wait", "Wait")]
MORE_ADD = ["click", "key", "type", "scroll"]

STATUS_COLORS = {"active": theme.ORANGE, "ok": theme.GREEN, "fail": theme.RED,
                 "skip": theme.FG_FAINT}


class StepRow(tk.Canvas):
    def __init__(self, master, page, step):
        super().__init__(master, height=ROW_H, bg=theme.BG, highlightthickness=0, bd=0)
        self.page, self.step = page, step
        self.index = 0
        self.selected = self.hover = False
        self.status = None
        self._thumb = None
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonPress-1>", lambda e: page.on_row_press(self, e))
        self.bind("<B1-Motion>", lambda e: page.on_row_drag(self, e))
        self.bind("<ButtonRelease-1>", lambda e: page.on_row_release(self, e))
        self.bind("<Double-Button-1>", lambda e: page.toggle_enabled(self.step))

    def _set_hover(self, h):
        self.hover = h
        self.redraw()

    def redraw(self):
        self.delete("all")
        width = max(self.winfo_width(), 200)
        s = self.step
        fill = theme.BG_RAISED if (self.selected or self.hover) else theme.BG_CARD
        outline = theme.GREEN if self.selected else theme.BORDER
        draw.rrect(self, 0, 0, width, ROW_H, theme.RADIUS_CARD, fill, outline, theme.BG)
        dim = not s.enabled

        # index
        self.create_text(22, ROW_H / 2, text=str(self.index + 1), fill=theme.FG_FAINT,
                         font=theme.font(10, "bold"))
        # thumbnail / icon tile
        tile_x = 42
        template = self.page.app.flow.template_for(s) if s.kind in model.IMAGE_KINDS else None
        if template is not None:
            key = ("thumb", template.id, 40, id(template.image))
            self._thumb = draw._cached(key, lambda: draw.thumbnail(template.image, 40, theme.BG_FIELD))
            self.create_image(tile_x, 10, image=self._thumb, anchor="nw")
        elif s.kind == "click_color":
            draw.rrect(self, tile_x, 10, 40, 40, 6, draw.rgb_to_hex(s.get("rgb")),
                       theme.BORDER_STRONG, fill)
        else:
            draw.rrect(self, tile_x, 10, 40, 40, 6, theme.BG_FIELD, None, fill)
            color = theme.GREEN if s.kind in model.SEARCH_KINDS else theme.FG_SOFT
            self.create_image(tile_x + 20, 30, image=icons.get(icons.KIND_ICONS[s.kind], 18,
                                                               theme.FG_FAINT if dim else color))

        tx = tile_x + 54
        title = KINDS[s.kind]["label"]
        self.create_text(tx, 21, text=title, anchor="w",
                         fill=theme.FG_MUTED if dim else theme.FG, font=theme.font(10, "bold"))
        summary = model.summary(s, self.page.app.flow)
        self.create_text(tx, 40, text=summary, anchor="w",
                         fill=theme.FG_FAINT if dim else theme.FG_MUTED, font=theme.font(9),
                         width=max(width - tx - 70, 50))
        if dim:
            self._pill(width - 16, "OFF", theme.FG_MUTED, theme.BG_FIELD, fill)
        if self.status:
            # Icon + colour, so the state reads without telling colours apart.
            cx = width - 24 - (44 if dim else 0)
            color = STATUS_COLORS[self.status]
            tint = {"ok": theme.GREEN_DIM, "fail": theme.RED_DIM, "active": theme.ORANGE_DIM,
                    "skip": theme.BG_FIELD}[self.status]
            draw.circle(self, cx, ROW_H / 2, 22, tint, None)
            glyph = {"ok": "check", "fail": "close", "active": "play", "skip": "down"}[self.status]
            self.create_image(cx, ROW_H / 2, image=icons.get(glyph, 13, color, stroke=2.6))

    def _pill(self, right, text, fg, bg, behind):
        draw.rrect(self, right - 34, ROW_H / 2 - 10, 34, 20, 10, bg, None, behind)
        self.create_text(right - 17, ROW_H / 2, text=text, fill=fg, font=theme.font(8, "bold"))


class FlowPage(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=theme.BG)
        self.app = app
        self.rows = []
        self.selected = None          # Step
        self._drag = None
        self._build()

    # ------------------------------------------------------------- layout

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        head = tk.Frame(self, bg=theme.BG)
        head.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 0))
        head.columnconfigure(0, weight=1)
        titles = tk.Frame(head, bg=theme.BG)
        titles.grid(row=0, column=0, sticky="w")
        w.label(titles, "Flow", size=18, bold=True).pack(anchor="w")
        self.subtitle = w.label(titles, "", muted=True)
        self.subtitle.pack(anchor="w")

        actions = tk.Frame(head, bg=theme.BG)
        actions.grid(row=0, column=1, sticky="e")
        w.Button(actions, icon="new", variant="ghost", command=self.app.new_flow,
                 tooltip="New flow").pack(side="left", padx=2)
        w.Button(actions, icon="folder", variant="ghost", command=self.app.open_flow,
                 tooltip="Open…").pack(side="left", padx=2)
        w.Button(actions, icon="save", variant="ghost", command=self.app.save_flow,
                 tooltip="Save").pack(side="left", padx=(2, 12))
        self.run_btn = w.Button(actions, text="Run", icon="play", variant="primary", height=36,
                                width=128, command=self.app.toggle_run)
        self.run_btn.pack(side="left")

        # add-step chips
        bar = tk.Frame(self, bg=theme.BG)
        bar.grid(row=1, column=0, sticky="ew", padx=24, pady=(16, 12))
        for kind, text in QUICK_ADD:
            w.Button(bar, text=text, icon=icons.KIND_ICONS[kind], variant="chip", height=30,
                     icon_size=14, font=theme.font(9),
                     command=lambda k=kind: self.add_step(k)).pack(side="left", padx=(0, 6))
        self._more = w.Button(bar, text="More", icon="chevron", variant="chip", height=30,
                              icon_size=14, font=theme.font(9), command=self._more_menu)
        self._more.pack(side="left")

        body = tk.Frame(self, bg=theme.BG)
        body.grid(row=2, column=0, sticky="nsew", padx=24)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.scroll = w.ScrollFrame(body)
        self.scroll.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        self.list_frame = self.scroll.interior
        self.empty = tk.Frame(self.scroll.interior, bg=theme.BG)

        self.inspector = Inspector(body, self)
        self.inspector.grid(row=0, column=1, sticky="nsew")

        # footer
        foot = w.Card(self, padding=10, parent_bg=theme.BG)
        foot.grid(row=3, column=0, sticky="ew", padx=24, pady=(12, 18))
        fb = foot.body
        self.loop_var = tk.BooleanVar(value=self.app.flow.loop)
        w.Toggle(fb, "Loop", self.loop_var, command=self._loop_changed).pack(side="left")
        self.count_var = tk.StringVar(value=str(self.app.flow.loop_count))
        w.label(fb, "times", muted=True).pack(side="left", padx=(12, 6))
        self.count_entry = w.Entry(fb, self.count_var, width=4, on_commit=self._loop_changed,
                                   justify="center", height=28)
        self.count_entry.pack(side="left")
        w.label(fb, "0 = until stopped", muted=True, size=9).pack(side="left", padx=(8, 0))
        self.log_label = w.label(fb, "", muted=True, size=9)
        self.log_label.pack(side="right")
        self.status_canvas = tk.Canvas(fb, width=96, height=24, bg=theme.BG_CARD,
                                       highlightthickness=0, bd=0)
        self.status_canvas.pack(side="right", padx=(0, 12))
        self.set_status("Ready", "idle")

    def _more_menu(self):
        m = tk.Menu(self, tearoff=False)
        for kind in MORE_ADD:
            m.add_command(label="  " + KINDS[kind]["label"] + "  ",
                          command=lambda k=kind: self.add_step(k))
        b = self._more
        m.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height() + 2)

    # ------------------------------------------------------------- list

    def refresh(self, keep_selection=True):
        flow = self.app.flow
        if not keep_selection or self.selected not in flow.steps:
            self.selected = flow.steps[0] if flow.steps else None
        existing = {id(r.step): r for r in self.rows}
        new_rows = []
        for step in flow.steps:
            row = existing.pop(id(step), None) or StepRow(self.list_frame, self, step)
            new_rows.append(row)
        for row in existing.values():
            row.destroy()
        for row in new_rows:
            row.pack_forget()
        self.rows = new_rows
        for i, row in enumerate(self.rows):
            row.index = i
            row.selected = row.step is self.selected
            row.pack(fill="x", pady=(0, ROW_GAP))
            row.redraw()
        self._empty_state(not self.rows)
        self.inspector.show(self.selected)
        n = len(flow.steps)
        imgs = len(flow.templates)
        self.subtitle.configure(text=f"{flow.name}  ·  {n} step{'s' if n != 1 else ''}  ·  "
                                     f"{imgs} image{'s' if imgs != 1 else ''}")
        self.loop_var.set(flow.loop)
        self.count_var.set(str(flow.loop_count))

    def _empty_state(self, show):
        e = self.empty
        for child in e.winfo_children():
            child.destroy()
        if not show:
            e.pack_forget()
            return
        e.pack(fill="both", expand=True, pady=40)
        c = tk.Canvas(e, width=64, height=64, bg=theme.BG, highlightthickness=0)
        c.pack()
        draw.rrect(c, 0, 0, 64, 64, 16, theme.BG_CARD, theme.BORDER, theme.BG)
        c.create_image(32, 32, image=icons.get("crosshair", 30, theme.GREEN))
        w.label(e, "Build a flow that sees the screen", size=12, bold=True,
                anchor="center").pack(pady=(14, 2))
        w.label(e, "Add Find & click, then drag a box around the button it should press.\n"
                   "Steps run top to bottom, and keep working when windows move.",
                muted=True, justify="center", anchor="center").pack()
        w.Button(e, text="Add Find & click", icon="plus", variant="primary",
                 command=lambda: self.add_step("click_image", capture=True)).pack(pady=16)

    def update_row(self, step):
        for row in self.rows:
            if row.step is step:
                row.redraw()
        self.app.mark_dirty()

    def select(self, step):
        self.selected = step
        for row in self.rows:
            sel = row.step is step
            if row.selected != sel:
                row.selected = sel
                row.redraw()
            if sel:
                self.scroll.scroll_to_widget(row)
        self.inspector.show(step)

    def add_step(self, kind, capture=None):
        step = Step.create(kind)
        if "confidence" in step.params:
            step.params["confidence"] = float(self.app.cfg["default_confidence"])
        steps = self.app.flow.steps
        at = steps.index(self.selected) + 1 if self.selected in steps else len(steps)
        steps.insert(at, step)
        self.selected = step
        self.app.mark_dirty()
        self.refresh()
        self.select(step)
        if capture is None:
            capture = kind in model.IMAGE_KINDS and self.app.cfg.get("capture_on_add", True)
        if capture:
            self.inspector.capture_template()

    def toggle_enabled(self, step):
        step.enabled = not step.enabled
        self.update_row(step)
        self.inspector.show(step)

    def move_selected(self, delta):
        steps = self.app.flow.steps
        if self.selected not in steps:
            return
        i = steps.index(self.selected)
        j = min(max(i + delta, 0), len(steps) - 1)
        if i != j:
            steps.insert(j, steps.pop(i))
            self.app.mark_dirty()
            self.refresh()
            self.select(self.selected)

    def duplicate_selected(self):
        steps = self.app.flow.steps
        if self.selected in steps:
            i = steps.index(self.selected)
            copy = self.selected.clone()
            steps.insert(i + 1, copy)
            self.app.mark_dirty()
            self.selected = copy
            self.refresh()
            self.select(copy)

    def delete_selected(self):
        steps = self.app.flow.steps
        if self.selected in steps:
            i = steps.index(self.selected)
            steps.pop(i)
            self.selected = steps[min(i, len(steps) - 1)] if steps else None
            self.app.mark_dirty()
            self.refresh()

    # drag to reorder ------------------------------------------------------

    def on_row_press(self, row, e):
        self.select(row.step)
        self._drag = {"row": row, "y": e.y_root, "moved": False}

    def on_row_drag(self, row, e):
        d = self._drag
        if not d or self.app.runner.running:
            return
        if not d["moved"] and abs(e.y_root - d["y"]) < 6:
            return
        d["moved"] = True
        self.configure(cursor="fleur")
        y = e.y_root - self.list_frame.winfo_rooty()
        target = min(max(int(y // (ROW_H + ROW_GAP)), 0), len(self.rows) - 1)
        steps = self.app.flow.steps
        i = steps.index(row.step)
        if target != i:
            steps.insert(target, steps.pop(i))
            self.app.mark_dirty()
            self.refresh()

    def on_row_release(self, row, e):
        self.configure(cursor="")
        self._drag = None

    # ------------------------------------------------------------- run state

    def _loop_changed(self):
        flow = self.app.flow
        flow.loop = bool(self.loop_var.get())
        try:
            flow.loop_count = max(0, int(float(self.count_var.get())))
        except ValueError:
            pass
        self.count_var.set(str(flow.loop_count))
        self.app.mark_dirty()

    def set_running(self, running):
        if running:
            self.run_btn.configure_button(text="Stop", icon="stop", variant="running")
        else:
            self.run_btn.configure_button(text="Run", icon="play", variant="primary")
        if running:
            for row in self.rows:
                row.status = None
                row.redraw()

    def set_step_status(self, index, status):
        if 0 <= index < len(self.rows):
            row = self.rows[index]
            row.status = status
            row.redraw()

    def set_status(self, text, kind="idle"):
        c = self.status_canvas
        c.delete("all")
        fg, bg = {"idle": (theme.FG_SOFT, theme.BG_FIELD), "run": (theme.ORANGE, theme.ORANGE_DIM),
                  "ok": (theme.GREEN, theme.GREEN_DIM), "fail": (theme.RED, theme.RED_DIM)}[kind]
        draw.rrect(c, 0, 0, 96, 24, 12, bg, None, theme.BG_CARD)
        draw.circle(c, 14, 12, 8, fg, None)
        c.create_text(26, 12, text=text, anchor="w", fill=fg, font=theme.font(9, "bold"))

    def on_test_result(self, key):
        if self.inspector.step is not None and self.inspector.step.id == key:
            self.inspector.show(self.inspector.step)

    def handle_key(self, e):
        """Keyboard control of the step list (focus must not be in a text field).

        Up/Down select, Ctrl+Up/Down move, Space enables/disables,
        Ctrl+D duplicates, T tests the selected step, Delete removes it.
        """
        steps = self.app.flow.steps
        if not steps:
            return
        ctrl = bool(e.state & 0x4)
        i = steps.index(self.selected) if self.selected in steps else 0
        key = e.keysym
        if key in ("Up", "Down"):
            delta = -1 if key == "Up" else 1
            if ctrl:
                self.move_selected(delta)
            else:
                self.select(steps[min(max(i + delta, 0), len(steps) - 1)])
            return "break"
        if key == "Home":
            self.select(steps[0])
        elif key == "End":
            self.select(steps[-1])
        elif key == "space":
            self.toggle_enabled(steps[i])
        elif key.lower() == "d" and ctrl:
            self.duplicate_selected()
        elif key.lower() == "t" and not ctrl and steps[i].kind in model.SEARCH_KINDS:
            self.app.test_step(steps[i])
        else:
            return None
        return "break"

    def set_log(self, text):
        self.log_label.configure(text=text)


class Inspector(w.Card):
    WIDTH = 372

    def __init__(self, master, page):
        super().__init__(master, padding=16, parent_bg=theme.BG, width=self.WIDTH)
        self.fixed()
        self.page = page
        self.app = page.app
        self.step = None
        self._vars = {}
        self._images = []

    def show(self, step):
        self.step = step
        b = self.body
        for child in b.winfo_children():
            child.destroy()
        self._vars.clear()
        self._images.clear()
        b.columnconfigure(0, weight=1)
        if step is None:
            w.label(b, "Nothing selected", bold=True, bg=theme.BG_CARD).pack(anchor="w")
            w.label(b, "Add a step from the bar above.", muted=True,
                    bg=theme.BG_CARD).pack(anchor="w", pady=(4, 0))
            return

        head = tk.Frame(b, bg=theme.BG_CARD)
        head.pack(fill="x")
        ic = tk.Canvas(head, width=34, height=34, bg=theme.BG_CARD, highlightthickness=0)
        ic.pack(side="left")
        draw.rrect(ic, 0, 0, 34, 34, 8, theme.GREEN_DIM if step.kind in model.SEARCH_KINDS
                   else theme.BG_FIELD, None, theme.BG_CARD)
        ic.create_image(17, 17, image=icons.get(icons.KIND_ICONS[step.kind], 18,
                                               theme.GREEN if step.kind in model.SEARCH_KINDS
                                               else theme.FG_SOFT))
        t = tk.Frame(head, bg=theme.BG_CARD)
        t.pack(side="left", padx=10)
        index = self.app.flow.steps.index(step) + 1
        w.label(t, KINDS[step.kind]["label"], bold=True, size=12, bg=theme.BG_CARD).pack(anchor="w")
        w.label(t, f"Step {index}", muted=True, size=9, bg=theme.BG_CARD).pack(anchor="w")
        en = tk.BooleanVar(value=step.enabled)
        w.Toggle(head, "", en, command=lambda: self.page.toggle_enabled(step),
                 parent_bg=theme.BG_CARD).pack(side="right")

        tk.Frame(b, bg=theme.BORDER, height=1).pack(fill="x", pady=12)

        # Footer first, anchored to the bottom, so it stays put whatever the
        # number of fields above it.
        foot = tk.Frame(b, bg=theme.BG_CARD)
        foot.pack(fill="x", side="bottom")
        tk.Frame(b, bg=theme.BORDER, height=1).pack(fill="x", pady=(10, 10), side="bottom")

        scroller = w.ScrollFrame(b, bg=theme.BG_CARD)
        scroller.pack(fill="both", expand=True)
        fields = scroller.interior
        for key, lbl, ftype, default, opts in KINDS[step.kind]["fields"]:
            self._field(fields, key, lbl, ftype, opts)
            if ftype in ("template", "color"):
                self._result_panel(fields)

        for icon, tip, cmd in (("up", "Move up", lambda: self.page.move_selected(-1)),
                               ("down", "Move down", lambda: self.page.move_selected(1)),
                               ("copy", "Duplicate", self.page.duplicate_selected),
                               ("trash", "Delete", self.page.delete_selected)):
            w.Button(foot, icon=icon, variant="ghost", tooltip=tip, command=cmd,
                     parent_bg=theme.BG_CARD).pack(side="left", padx=(0, 2))
        w.Button(foot, icon="play", variant="ghost", tooltip="Run from this step",
                 parent_bg=theme.BG_CARD,
                 command=lambda: self.app.start_run(start_at=self.app.flow.steps.index(step))
                 ).pack(side="right")
        if step.kind in model.SEARCH_KINDS:
            w.Button(foot, text="Test", icon="eye", variant="secondary", parent_bg=theme.BG_CARD,
                     command=lambda: self.app.test_step(step)).pack(side="right", padx=(0, 6))

    # ------------------------------------------------------------- fields

    def _row(self, parent, text):
        row = tk.Frame(parent, bg=theme.BG_CARD)
        row.pack(fill="x", pady=5)
        w.label(row, text, muted=True, size=9, bg=theme.BG_CARD, width=13).pack(side="left")
        return row

    def _commit(self, key, value):
        if key in ("template", "region", "color", "rgb", "tolerance"):
            self.app.test_results.pop(self.step.id, None)
        self.step.params[key] = value
        self.page.update_row(self.step)

    def _field(self, parent, key, lbl, ftype, opts):
        step = self.step
        value = step.get(key)
        bg = theme.BG_CARD

        if ftype == "template":
            self._template_field(parent)
            return

        row = self._row(parent, lbl)
        if ftype == "percent":
            var = tk.DoubleVar(value=float(value))
            def changed(v, var=var, key=key):
                self._commit(key, float(var.get()))
                if self.app.test_results.get(step.id):
                    self.show(step)   # re-judge the last test against the new setting

            w.Slider(row, var, opts[0], opts[1], parent_bg=bg, width=200,
                     fmt=lambda v: f"{v:.0%} {explain.strictness(v)}",
                     on_change=changed).pack(side="left")
        elif ftype in ("float", "int"):
            var = tk.StringVar(value=f"{value:g}" if ftype == "float" else str(value))

            def commit(var=var, key=key, ftype=ftype):
                try:
                    v = float(var.get()) if ftype == "float" else int(float(var.get()))
                except ValueError:
                    v = step.get(key)
                if key in ("timeout", "seconds", "tolerance", "count", "hold_ms", "interval", "skip"):
                    v = max(0, v)
                var.set(f"{v:g}" if ftype == "float" else str(v))
                if v != step.get(key):
                    self._commit(key, v)

            w.Entry(row, var, width=7, on_commit=commit, parent_bg=bg).pack(side="left")
        elif ftype == "choice":
            var = tk.StringVar(value=value)
            if key == "on_fail":
                w.Select(row, [(o, model.ON_FAIL_LABELS[o]) for o in opts], var,
                         on_change=lambda v, key=key: self._commit(key, v), width=170,
                         parent_bg=bg).pack(side="left")
            else:
                labels = model.ACTION_LABELS if key == "action" else {}
                w.Segmented(row, [(o, labels.get(o, o.title())) for o in opts], var,
                            on_change=lambda v, key=key: self._commit(key, v),
                            parent_bg=bg, width=1).pack(side="left", fill="x", expand=True,
                                                        padx=(0, 4))
        elif ftype == "bool":
            var = tk.BooleanVar(value=bool(value))
            w.Toggle(row, "", var, command=lambda: self._commit(key, bool(var.get())),
                     parent_bg=bg).pack(side="left")
        elif ftype == "text":
            var = tk.StringVar(value=value)
            w.Entry(row, var, width=18, on_commit=lambda: self._commit(key, var.get()),
                    parent_bg=bg).pack(side="left", fill="x", expand=True)
        elif ftype == "key":
            var = tk.StringVar(value=value)
            w.Entry(row, var, width=10,
                    on_commit=lambda: self._commit(key, var.get().strip().lower()),
                    parent_bg=bg).pack(side="left")

            def record(var=var):
                rec.configure_button(text="Press…", variant="running")

                def got(combo):
                    var.set(combo)
                    self._commit(key, combo)
                    rec.configure_button(text="Record", variant="secondary")
                self.app.hotkeys.capture_next(lambda c: self.after(0, got, c))

            rec = w.Button(row, text="Record", variant="secondary", parent_bg=bg, height=30,
                           font=theme.font(9), command=record)
            rec.pack(side="left", padx=(6, 0))
        elif ftype == "region":
            self._region_field(row, key)
        elif ftype == "color":
            self._color_field(row, key)

    def _template_field(self, parent):
        step, flow = self.step, self.app.flow
        bg = theme.BG_CARD
        box = tk.Frame(parent, bg=bg)
        box.pack(fill="x", pady=(0, 8))
        t = flow.template_for(step)
        pic = tk.Canvas(box, width=96, height=72, bg=bg, highlightthickness=0, cursor="hand2")
        pic.pack(side="left")
        if t is not None:
            draw.rrect(pic, 0, 0, 96, 72, 8, theme.BG_FIELD, theme.BORDER_STRONG, bg)
            img = ImageTk.PhotoImage(preview(t.image, 88, 64))
            self._images.append(img)
            pic.create_image(48, 36, image=img)
        else:
            draw.rrect(pic, 0, 0, 96, 72, 8, theme.BG_FIELD, theme.BORDER_STRONG, bg)
            pic.create_image(48, 30, image=icons.get("crosshair", 22, theme.FG_MUTED))
            pic.create_text(48, 56, text="No image", fill=theme.FG_MUTED, font=theme.font(8))
        pic.bind("<Button-1>", lambda e: self.capture_template())

        side = tk.Frame(box, bg=bg)
        side.pack(side="left", fill="x", expand=True, padx=(12, 0))
        var = tk.StringVar(value=t.id if t else "")
        opts = [(tid, tpl.name) for tid, tpl in flow.templates.items()]
        sel = w.Select(side, opts or [("", "Library is empty")], var, width=180, parent_bg=bg,
                       on_change=lambda v: (self._commit("template", v or None), self.show(step)))
        sel.pack(anchor="w")
        btns = tk.Frame(side, bg=bg)
        btns.pack(anchor="w", pady=(8, 0))
        w.Button(btns, text="Capture", icon="crosshair", variant="primary", parent_bg=bg,
                 height=28, font=theme.font(9, "bold"), icon_size=14,
                 command=self.capture_template).pack(side="left")
        if t:
            w.Button(btns, icon="scissors", variant="secondary", parent_bg=bg, height=28,
                     icon_size=14, tooltip="Cut out the background (ignore what's behind it)",
                     command=lambda: open_cutout(self.app, t,
                                                 after=lambda: self.show(step))
                     ).pack(side="left", padx=(6, 0))
            w.label(btns, f"{t.size[0]}×{t.size[1]}px", muted=True, size=9,
                    bg=bg).pack(side="left", padx=8)
            QualityLine(parent, t.image, bg=bg, wrap=290).pack(fill="x", pady=(0, 8))
        else:
            w.label(parent, "Click Capture, then drag a box around the thing to find. "
                            "Include its text or outline - that's what makes it recognisable.",
                    muted=True, size=9, bg=bg, wraplength=300,
                    justify="left").pack(anchor="w", pady=(0, 8))

    def _result_panel(self, parent):
        """The last Test of this step, re-judged against the current settings."""
        step = self.step
        result = self.app.test_results.get(step.id)
        if result is None:
            return
        p = result.probe
        if step.kind == "click_color":
            target = Image.new("RGB", (24, 24), tuple(step.get("rgb")))
            verdict = explain.color_result(p.hit is not None)
            need = None
        else:
            t = self.app.flow.template_for(step)
            if t is None:
                return
            target = t.image
            need = float(step.get("confidence"))
            verdict = explain.test_result(p.score, need, p.score >= need, p.elapsed_ms)
        shown = type(result)(p, verdict, need)
        ComparePanel(parent, target, shown, bg=theme.BG_CARD, width=300).pack(fill="x",
                                                                             pady=(2, 10))

    def capture_template(self):
        step = self.step
        if step is None or step.kind not in model.IMAGE_KINDS:
            return

        def done(image):
            if image is None:
                return
            t = self.app.flow.add_template(image)
            step.params["template"] = t.id
            self.page.update_row(step)
            self.app.on_library_changed()
            if self.step is step:
                self.show(step)
        self.app.capture("image", done)

    def _region_field(self, row, key):
        step, bg = self.step, theme.BG_CARD
        region = step.get(key)
        text = "Whole screen" if not region else f"{region[2]}×{region[3]} at {region[0]},{region[1]}"
        w.label(row, text, size=9, bg=bg).pack(side="left")

        def set_region():
            def done(r):
                if r:
                    self._commit(key, list(r))
                    self.show(step)
            self.app.capture("region", done)

        def clear():
            self._commit(key, None)
            self.show(step)

        if region:
            w.Button(row, icon="close", variant="ghost", parent_bg=bg, height=26, icon_size=14,
                     tooltip="Search the whole screen", command=clear).pack(side="right")
        w.Button(row, icon="region", variant="ghost", parent_bg=bg, height=26, icon_size=14,
                 tooltip="Limit to an area (faster)", command=set_region).pack(side="right")

    def _color_field(self, row, key):
        step, bg = self.step, theme.BG_CARD
        rgb = step.get(key)
        sw = w.Swatch(row, rgb, size=28, parent_bg=bg)
        sw.pack(side="left")
        var = tk.StringVar(value=draw.rgb_to_hex(rgb).upper())

        def commit():
            v = var.get().strip().lstrip("#")
            try:
                new = list(draw.hex_to_rgb(v)) if len(v) == 6 else step.get(key)
            except ValueError:
                new = step.get(key)
            var.set(draw.rgb_to_hex(new).upper())
            sw.set(new)
            if new != step.get(key):
                self._commit(key, new)

        w.Entry(row, var, width=8, on_commit=commit, parent_bg=bg,
                font=theme.mono(10)).pack(side="left", padx=(8, 6))

        def pick():
            def done(c):
                if c:
                    self._commit(key, list(c))
                    self.show(step)
            self.app.capture("color", done)

        w.Button(row, icon="dropper", variant="secondary", parent_bg=bg, height=28, icon_size=14,
                 tooltip="Pick from screen", command=pick).pack(side="left")
