"""Line icons rendered with Pillow at 4x and downsampled (crisp, anti-aliased).

Every icon is drawn on a unit grid of 24 with a 2px stroke, the common modern
icon convention, then scaled to the requested size.
"""

import math

from PIL import Image, ImageDraw

from .draw import SUPERSAMPLE, _cached, hex_to_rgb

_GRID = 24.0


class _Pen:
    def __init__(self, size, color, stroke=2.0):
        self.s = size * SUPERSAMPLE / _GRID
        self.img = Image.new("RGBA", (size * SUPERSAMPLE, size * SUPERSAMPLE), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)
        self.c = hex_to_rgb(color) + (255,)
        self.w = max(1, int(round(stroke * self.s)))

    def p(self, x, y):
        return (x * self.s, y * self.s)

    def line(self, *pts, closed=False):
        pts = [self.p(x, y) for x, y in pts]
        if closed:
            pts = pts + [pts[0]]
        self.d.line(pts, fill=self.c, width=self.w, joint="curve")
        r = self.w / 2
        for x, y in (pts[0], pts[-1]):  # round caps
            self.d.ellipse([x - r, y - r, x + r, y + r], fill=self.c)

    def rect(self, x1, y1, x2, y2, r=2, fill=False):
        box = [x1 * self.s, y1 * self.s, x2 * self.s, y2 * self.s]
        if fill:
            self.d.rounded_rectangle(box, radius=r * self.s, fill=self.c)
        else:
            self.d.rounded_rectangle(box, radius=r * self.s, outline=self.c, width=self.w)

    def circle(self, cx, cy, r, fill=False):
        box = [(cx - r) * self.s, (cy - r) * self.s, (cx + r) * self.s, (cy + r) * self.s]
        if fill:
            self.d.ellipse(box, fill=self.c)
        else:
            self.d.ellipse(box, outline=self.c, width=self.w)

    def poly(self, *pts):
        self.d.polygon([self.p(x, y) for x, y in pts], fill=self.c)

    def done(self, size):
        return self.img.resize((size, size), Image.LANCZOS)


def _flow(p):
    p.rect(3, 3, 10, 9, 2)
    p.rect(14, 15, 21, 21, 2)
    p.line((6.5, 9), (6.5, 18), (14, 18))
    p.circle(18, 6, 2.6)
    p.line((10, 6), (15.4, 6))


def _images(p):
    p.rect(3, 4, 21, 20, 3)
    p.circle(9, 9.5, 1.8, fill=True)
    p.line((4, 18), (10, 12.5), (14, 16), (16.5, 13.5), (20.5, 17.5))


def _gear(p):
    pts = []
    for i in range(48):
        a = 2 * math.pi * i / 48
        r = 9.6 if (i % 6) in (0, 1, 2) else 7.4
        pts.append((12 + r * math.cos(a + 0.2), 12 + r * math.sin(a + 0.2)))
    p.d.polygon([p.p(x, y) for x, y in pts], outline=p.c, width=p.w)
    p.circle(12, 12, 3)


def _play(p):
    p.poly((7, 4.5), (19.5, 12), (7, 19.5))


def _stop(p):
    p.rect(6, 6, 18, 18, 2.5, fill=True)


def _plus(p):
    p.line((12, 5), (12, 19))
    p.line((5, 12), (19, 12))


def _up(p):
    p.line((6, 14.5), (12, 8.5), (18, 14.5))


def _down(p):
    p.line((6, 9.5), (12, 15.5), (18, 9.5))


def _copy(p):
    p.rect(8, 8, 20, 20, 2.5)
    p.line((16, 4.5), (6.5, 4.5))
    p.line((4.5, 6.5), (4.5, 16))


def _trash(p):
    p.line((4, 6.5), (20, 6.5))
    p.line((9, 6.5), (9.5, 3.5), (14.5, 3.5), (15, 6.5))
    p.line((6, 6.5), (7, 20), (17, 20), (18, 6.5))
    p.line((10.5, 10.5), (10.5, 16))
    p.line((13.5, 10.5), (13.5, 16))


def _crosshair(p):
    p.circle(12, 12, 7)
    for a, b in (((12, 2), (12, 7)), ((12, 17), (12, 22)), ((2, 12), (7, 12)), ((17, 12), (22, 12))):
        p.line(a, b)
    p.circle(12, 12, 1.2, fill=True)


def _dropper(p):
    p.line((14, 5), (19, 10))
    p.line((16.5, 7.5), (6.5, 17.5), (5, 21), (8.5, 19.5), (18.5, 9.5))
    p.circle(18.5, 5.5, 2.4, fill=True)


def _eye(p):
    pts_top = [(2.5 + i * 0.95, 12 - 6.5 * math.sin(math.pi * i / 20)) for i in range(21)]
    pts_bot = [(2.5 + i * 0.95, 12 + 6.5 * math.sin(math.pi * i / 20)) for i in range(21)]
    p.line(*pts_top)
    p.line(*pts_bot)
    p.circle(12, 12, 3)


def _folder(p):
    p.line((3, 18.5), (3, 6), (9, 6), (11, 8.5), (21, 8.5), (21, 18.5), (3, 18.5))


def _save(p):
    p.line((5, 4), (16, 4), (20, 8), (20, 20), (4, 20), (4, 4), (5, 4))
    p.rect(8, 13, 16, 20, 1)
    p.line((8, 4), (8, 8.5), (14, 8.5))


def _new(p):
    p.line((14, 3.5), (6, 3.5), (6, 20.5), (18, 20.5), (18, 7.5), (14, 3.5))
    p.line((12, 10.5), (12, 16.5))
    p.line((9, 13.5), (15, 13.5))


def _chevron(p):
    p.line((7, 10), (12, 15), (17, 10))


def _check(p):
    p.line((5, 12.5), (10, 17.5), (19.5, 7))


def _close(p):
    p.line((6, 6), (18, 18))
    p.line((18, 6), (6, 18))


def _warn(p):
    p.line((12, 6), (12, 13.5))
    p.circle(12, 18, 1.4, fill=True)


def _scissors(p):
    p.circle(6.5, 17.5, 3)
    p.circle(17.5, 17.5, 3)
    p.line((8.6, 15.4), (16.5, 4))
    p.line((15.4, 15.4), (7.5, 4))


def _region(p):
    for x1, y1, x2, y2 in ((3, 3, 7, 3), (3, 3, 3, 7), (17, 3, 21, 3), (21, 3, 21, 7),
                           (3, 21, 7, 21), (3, 17, 3, 21), (17, 21, 21, 21), (21, 17, 21, 21)):
        p.line((x1, y1), (x2, y2))
    p.rect(8, 8, 16, 16, 1.5)


def _cursor(p):
    p.line((6, 3.5), (6, 19), (10, 15), (13, 21), (15.5, 20), (12.5, 14), (18, 14), (6, 3.5))


def _keyboard(p):
    p.rect(2.5, 6, 21.5, 18, 2.5)
    for x in (6.5, 10, 13.5, 17):
        p.circle(x, 10, 0.9, fill=True)
    p.line((7.5, 14.2), (16.5, 14.2))


def _text(p):
    p.line((5, 6), (19, 6))
    p.line((12, 6), (12, 19))


def _clock(p):
    p.circle(12, 12, 8.5)
    p.line((12, 7.5), (12, 12), (15.5, 14))


def _scroll(p):
    p.rect(7, 3, 17, 21, 5)
    p.line((12, 7), (12, 10.5))


def _branch(p):
    p.line((7, 4), (7, 20))
    p.circle(17, 8, 2.6)
    p.line((17, 10.6), (17, 12), (7, 16))


def _bolt(p):
    p.poly((13.5, 2.5), (5, 13.5), (11, 13.5), (10, 21.5), (19, 10), (13, 10))


def _palette(p):
    p.circle(12, 12, 8.5)
    p.circle(8.5, 10, 1.3, fill=True)
    p.circle(12, 7.5, 1.3, fill=True)
    p.circle(15.5, 10, 1.3, fill=True)


def _loop(p):
    pts = [(12 + 7 * math.cos(a / 10.0), 12 + 7 * math.sin(a / 10.0)) for a in range(-12, 48)]
    p.line(*pts)
    p.poly((19.4, 6.5), (20.5, 11.5), (15.5, 10.0))


_DRAWERS = {
    "flow": _flow, "images": _images, "gear": _gear, "play": _play, "stop": _stop,
    "plus": _plus, "up": _up, "down": _down, "copy": _copy, "trash": _trash,
    "crosshair": _crosshair, "dropper": _dropper, "eye": _eye, "folder": _folder,
    "save": _save, "new": _new, "chevron": _chevron, "check": _check, "close": _close, "warn": _warn, "scissors": _scissors,
    "region": _region, "cursor": _cursor, "keyboard": _keyboard, "text": _text,
    "clock": _clock, "scroll": _scroll, "branch": _branch, "bolt": _bolt,
    "palette": _palette, "loop": _loop,
}

KIND_ICONS = {
    "click_image": "crosshair", "wait_image": "eye", "if_image": "branch",
    "click_color": "dropper", "click": "cursor", "key": "keyboard", "type": "text",
    "scroll": "scroll", "wait": "clock",
}


def render(name, size, color, stroke=2.0):
    p = _Pen(size, color, stroke)
    _DRAWERS[name](p)
    return p.done(size)


def get(name, size, color, stroke=2.0):
    """Cached Tk image of icon `name`."""
    return _cached(("icon", name, size, color, stroke), lambda: render(name, size, color, stroke))


def render_logo(size, badge="#3ddc84", mark="#06120b"):
    """App mark: a rounded green badge holding a target/aperture."""
    s = SUPERSAMPLE
    big = Image.new("RGBA", (size * s, size * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    d.rounded_rectangle([0, 0, size * s - 1, size * s - 1], radius=size * s * 0.28,
                        fill=hex_to_rgb(badge))
    # Top sheen, Void Click's glass cue.
    sheen = Image.new("RGBA", big.size, (255, 255, 255, 0))
    sd = ImageDraw.Draw(sheen)
    sd.rounded_rectangle([0, 0, size * s - 1, size * s - 1], radius=size * s * 0.28,
                         fill=(255, 255, 255, 38))
    sd.rectangle([0, size * s // 2, size * s, size * s], fill=(0, 0, 0, 0))
    big = Image.alpha_composite(big, sheen)
    d = ImageDraw.Draw(big)
    c = hex_to_rgb(mark)
    cx = cy = size * s / 2
    w = max(1, int(size * s * 0.075))
    r1 = size * s * 0.27
    d.ellipse([cx - r1, cy - r1, cx + r1, cy + r1], outline=c, width=w)
    r2 = size * s * 0.095
    d.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], fill=c)
    tick = size * s * 0.13
    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        x0, y0 = cx + dx * (r1 - tick * 0.2), cy + dy * (r1 - tick * 0.2)
        x1, y1 = cx + dx * (r1 + tick), cy + dy * (r1 + tick)
        d.line([(x0, y0), (x1, y1)], fill=c, width=w)
    return big.resize((size, size), Image.LANCZOS)


def logo(size):
    return _cached(("logo", size), lambda: render_logo(size))
