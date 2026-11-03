"""The visual macro: an image library plus an ordered list of steps.

A flow file (.vflow) is one self-contained JSON document - the captured images
are embedded as base64 PNG, so a flow can be shared as a single file.
"""

import base64
import copy
import io
import json
import uuid
from dataclasses import dataclass, field

from PIL import Image

FORMAT = "voidvision.flow"
VERSION = 1

ON_FAIL = ["stop", "skip", "restart"]
ON_FAIL_LABELS = {"stop": "Stop the flow", "skip": "Skip this step", "restart": "Restart flow"}
ACTIONS = ["click", "double", "right", "move"]
ACTION_LABELS = {"click": "Click", "double": "Double", "right": "Right", "move": "Hover"}

# Field spec per step kind: (key, label, type, default, options)
# Types: template, color, region, float, int, choice, text, key, bool
_IMAGE_COMMON = [
    ("confidence", "Match", "percent", 0.85, (0.5, 1.0)),
    ("timeout", "Timeout (s)", "float", 5.0, None),
    ("region", "Search area", "region", None, None),
    ("color", "Strict colour", "bool", False, None),
]

KINDS = {
    "click_image": {
        "label": "Find & click",
        "group": "vision",
        "fields": [("template", "Image", "template", None, None)] + _IMAGE_COMMON + [
            ("action", "Then", "choice", "click", ACTIONS),
            ("offset_x", "Offset X", "int", 0, None),
            ("offset_y", "Offset Y", "int", 0, None),
            ("on_fail", "If not found", "choice", "stop", ON_FAIL),
        ],
    },
    "wait_image": {
        "label": "Wait for image",
        "group": "vision",
        "fields": [("template", "Image", "template", None, None),
                   ("mode", "Wait until it", "choice", "appear", ["appear", "vanish"])]
                  + _IMAGE_COMMON + [
            ("on_fail", "If it times out", "choice", "stop", ON_FAIL),
        ],
    },
    "if_image": {
        "label": "If visible",
        "group": "vision",
        "fields": [("template", "Image", "template", None, None),
                   ("confidence", "Match", "percent", 0.85, (0.5, 1.0)),
                   ("timeout", "Timeout (s)", "float", 0.0, None),
                   ("region", "Search area", "region", None, None),
                   ("color", "Strict colour", "bool", False, None),
                   ("negate", "If NOT visible", "bool", False, None),
                   ("skip", "Else skip next", "int", 1, None)],
    },
    "click_color": {
        "label": "Find colour",
        "group": "vision",
        "fields": [("rgb", "Colour", "color", [61, 220, 132], None),
                   ("tolerance", "Tolerance", "int", 12, None),
                   ("timeout", "Timeout (s)", "float", 5.0, None),
                   ("region", "Search area", "region", None, None),
                   ("action", "Then", "choice", "click", ACTIONS),
                   ("on_fail", "If not found", "choice", "stop", ON_FAIL)],
    },
    "click": {
        "label": "Click",
        "group": "input",
        "fields": [("button", "Button", "choice", "left", ["left", "right", "middle"]),
                   ("count", "Times", "int", 1, None),
                   ("interval", "Gap (ms)", "int", 60, None)],
    },
    "key": {
        "label": "Key",
        "group": "input",
        "fields": [("combo", "Key or combo", "key", "enter", None),
                   ("hold_ms", "Hold (ms)", "int", 0, None)],
    },
    "type": {
        "label": "Type text",
        "group": "input",
        "fields": [("text", "Text", "text", "hello", None)],
    },
    "scroll": {
        "label": "Scroll",
        "group": "input",
        "fields": [("amount", "Notches (+up)", "int", -3, None)],
    },
    "wait": {
        "label": "Wait",
        "group": "flow",
        "fields": [("seconds", "Seconds", "float", 1.0, None)],
    },
    "timing": {
        "label": "Hit the spot",
        "group": "vision",
        "fields": [("region", "Bar area", "region", None, None),
                   # Defaults match the common meter: a black line sweeping
                   # over a bar, pressed when it's on a red block.
                   ("marker_rgb", "Marker colour", "color", [0, 0, 0], None),
                   ("zone_mode", "The spot is", "choice", "color", ["fixed", "color"]),
                   ("zone", "Spot", "zone", [0.45, 0.55], None),
                   ("zone_rgb", "Spot colour", "color", [215, 7, 7], None),
                   ("tolerance", "Colour range", "int", 40, None),
                   ("combo", "Then press", "key", "space", None),
                   ("lead_ms", "Press early (ms)", "int", 25, None),
                   ("timeout", "Timeout (s)", "float", 10.0, None),
                   ("on_fail", "If it never lines up", "choice", "stop", ON_FAIL)],
    },
}

ZONE_MODE_LABELS = {"fixed": "Fixed place", "color": "A colour"}

IMAGE_KINDS = {"click_image", "wait_image", "if_image"}
SEARCH_KINDS = IMAGE_KINDS | {"click_color"}
TIMING_KINDS = {"timing"}


def new_id():
    return uuid.uuid4().hex[:10]


def normalize_image(image):
    """RGBA when the image is a cut-out (has transparent pixels), else RGB."""
    from .matcher import mask_of

    if mask_of(image) is not None:
        rgba = image.convert("RGBA")
        # Snap alpha to fully kept / fully ignored, which is how matching sees it.
        a = rgba.getchannel("A").point(lambda v: 255 if v >= 128 else 0)
        rgba.putalpha(a)
        return rgba
    return image.convert("RGB")


@dataclass
class Template:
    id: str
    name: str
    image: Image.Image

    @property
    def size(self):
        return self.image.size

    @property
    def is_cutout(self):
        return self.image.mode == "RGBA"

    def to_dict(self):
        buf = io.BytesIO()
        # Cut-outs keep their transparency; everything else is stored as RGB.
        normalize_image(self.image).save(buf, format="PNG", optimize=True)
        return {"id": self.id, "name": self.name,
                "png": base64.b64encode(buf.getvalue()).decode("ascii")}

    @classmethod
    def from_dict(cls, d):
        image = Image.open(io.BytesIO(base64.b64decode(d["png"])))
        image.load()
        return cls(str(d["id"]), str(d.get("name") or "Image"), normalize_image(image))


@dataclass
class Step:
    kind: str
    params: dict = field(default_factory=dict)
    enabled: bool = True
    note: str = ""
    id: str = field(default_factory=new_id)

    @classmethod
    def create(cls, kind, **overrides):
        if kind not in KINDS:
            raise ValueError(f"unknown step kind: {kind}")
        params = {key: copy.deepcopy(default) for key, _, _, default, _ in KINDS[kind]["fields"]}
        params.update(overrides)
        return cls(kind, params)

    def get(self, key):
        if key in self.params:
            return self.params[key]
        for k, _, _, default, _ in KINDS[self.kind]["fields"]:
            if k == key:
                return default
        return None

    def clone(self):
        return Step(self.kind, copy.deepcopy(self.params), self.enabled, self.note)

    def to_dict(self):
        return {"kind": self.kind, "params": self.params, "enabled": self.enabled,
                "note": self.note}

    @classmethod
    def from_dict(cls, d):
        kind = d.get("kind")
        if kind not in KINDS:
            raise ValueError(f"unknown step kind: {kind!r}")
        step = cls.create(kind)
        known = {k for k, *_ in KINDS[kind]["fields"]}
        step.params.update({k: v for k, v in (d.get("params") or {}).items() if k in known})
        step.enabled = bool(d.get("enabled", True))
        step.note = str(d.get("note", ""))
        return step


@dataclass
class Flow:
    name: str = "Untitled flow"
    steps: list = field(default_factory=list)
    templates: dict = field(default_factory=dict)   # id -> Template
    loop: bool = False
    loop_count: int = 1                              # 0 = until stopped

    # -------------------------------------------------------------- library

    def add_template(self, image, name=None):
        tid = new_id()
        if not name:
            n = len(self.templates) + 1
            existing = {t.name for t in self.templates.values()}
            while f"Image {n}" in existing:
                n += 1
            name = f"Image {n}"
        self.templates[tid] = Template(tid, name, normalize_image(image))
        return self.templates[tid]

    def remove_template(self, tid):
        self.templates.pop(tid, None)
        for step in self.steps:
            if step.params.get("template") == tid:
                step.params["template"] = None

    def usage(self, tid):
        return sum(1 for s in self.steps if s.params.get("template") == tid)

    def template_for(self, step):
        tid = step.params.get("template")
        return self.templates.get(tid) if tid else None

    # -------------------------------------------------------------- problems

    def problems(self):
        """Human-readable reasons the flow can't run as-is (empty if fine)."""
        out = []
        for i, step in enumerate(self.steps, 1):
            if not step.enabled:
                continue
            if step.kind in IMAGE_KINDS and self.template_for(step) is None:
                out.append(f"Step {i} ({KINDS[step.kind]['label']}) has no image")
            if step.kind == "timing" and not step.get("region"):
                out.append(f"Step {i} (Hit the spot) needs its Bar area set")
        return out

    # -------------------------------------------------------------- io

    def to_dict(self):
        return {
            "format": FORMAT, "version": VERSION, "name": self.name,
            "loop": self.loop, "loop_count": self.loop_count,
            "templates": [t.to_dict() for t in self.templates.values()],
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, d):
        if not isinstance(d, dict) or d.get("format") != FORMAT:
            raise ValueError("not a Void Vision flow file")
        flow = cls(name=str(d.get("name") or "Untitled flow"),
                   loop=bool(d.get("loop", False)),
                   loop_count=int(d.get("loop_count", 1)))
        for td in d.get("templates", []):
            t = Template.from_dict(td)
            flow.templates[t.id] = t
        flow.steps = [Step.from_dict(sd) for sd in d.get("steps", [])]
        return flow


def save_flow(flow, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(flow.to_dict(), f, indent=1)


def load_flow(path):
    with open(path, "r", encoding="utf-8") as f:
        return Flow.from_dict(json.load(f))


# ------------------------------------------------------------------ display

def _region_text(region):
    if not region:
        return "whole screen"
    x, y, w, h = region
    return f"{w}x{h} area"


def summary(step, flow):
    """One-line description of a step for the list view."""
    p = step.get
    k = step.kind
    if k in IMAGE_KINDS:
        t = flow.template_for(step)
        name = t.name if t else "no image yet"
    if k == "click_image":
        act = ACTION_LABELS.get(p("action"), "Click")
        off = ""
        if p("offset_x") or p("offset_y"):
            off = f" {p('offset_x'):+d},{p('offset_y'):+d}"
        return f"{act}{off} on '{name}' · {int(round(p('confidence') * 100))}% · {p('timeout'):g}s"
    if k == "wait_image":
        return f"Until '{name}' {'appears' if p('mode') == 'appear' else 'disappears'} · {p('timeout'):g}s"
    if k == "if_image":
        verb = "not visible" if p("negate") else "visible"
        n = int(p("skip"))
        return f"If '{name}' is {verb}, else skip {n} step{'s' if n != 1 else ''}"
    if k == "click_color":
        r, g, b = p("rgb")
        act = ACTION_LABELS.get(p("action"), "Click")
        return f"{act} on #{r:02x}{g:02x}{b:02x} ±{p('tolerance')} · {_region_text(p('region'))}"
    if k == "click":
        n = int(p("count"))
        return f"{p('button').title()} click{' x%d' % n if n != 1 else ''} where the cursor is"
    if k == "key":
        hold = f" · hold {p('hold_ms')}ms" if p("hold_ms") else ""
        return f"Press {format_combo(p('combo'))}{hold}"
    if k == "type":
        text = str(p("text"))
        short = text[:34] + ("…" if len(text) > 34 else "")
        return "“" + short + "”"
    if k == "scroll":
        a = int(p("amount"))
        return f"Scroll {'up' if a > 0 else 'down'} {abs(a)}"
    if k == "wait":
        return f"Pause {p('seconds'):g}s"
    if k == "timing":
        if p("zone_mode") == "color":
            r, g, b = p("zone_rgb")
            spot = f"the #{r:02x}{g:02x}{b:02x} spot"
        else:
            z0, z1 = p("zone")
            spot = f"{z0:.0%}\u2013{z1:.0%}"
        where = "" if p("region") else " \u00b7 set the bar area"
        return f"Press {format_combo(p('combo'))} when the marker hits {spot}{where}"
    return k


def format_combo(combo):
    if not combo:
        return "(none)"
    return " + ".join(part.upper() if len(part) <= 1 else part.title()
                      for part in str(combo).split("+"))
