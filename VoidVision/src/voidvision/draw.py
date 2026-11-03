"""Anti-aliased shapes for Tk canvases, rendered with Pillow.

Tk's canvas draws everything without anti-aliasing, which is what made rounded
corners look soft and stair-stepped. Here each shape is rendered by Pillow at
4x and downsampled, then shown as an image, so corners and hairline borders
come out crisp. Rendered images are cached by their parameters - hover states
flip between a handful of looks, so the cache stays tiny.
"""

from collections import OrderedDict

from PIL import Image, ImageDraw

SUPERSAMPLE = 4
_CACHE_LIMIT = 600
_cache = OrderedDict()


def hex_to_rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c)))) for c in rgb[:3])


def mix(a, b, t):
    ra, rb = hex_to_rgb(a), hex_to_rgb(b)
    return rgb_to_hex([ra[i] + (rb[i] - ra[i]) * t for i in range(3)])


def lighten(color, amount=0.1):
    return mix(color, "#ffffff", amount)


def darken(color, amount=0.1):
    return mix(color, "#000000", amount)


def _cached(key, build):
    image = _cache.get(key)
    if image is not None:
        _cache.move_to_end(key)
        return image
    from PIL import ImageTk

    image = ImageTk.PhotoImage(build())
    _cache[key] = image
    while len(_cache) > _CACHE_LIMIT:
        _cache.popitem(last=False)
    return image


def render_rrect(w, h, radius, fill, outline=None, bg=None, sheen=0.0, width=1):
    """Pillow image of a rounded rectangle, at 1x after supersampled drawing.

    `sheen` adds the Void Click glass cue: a faint lighter top half and a 1px
    specular line on the top edge. 0 gives a flat surface.
    """
    s = SUPERSAMPLE
    w, h = max(int(w), 1), max(int(h), 1)
    big = Image.new("RGBA", (w * s, h * s), hex_to_rgb(bg) + (255,) if bg else (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    r = max(0, min(radius, w / 2, h / 2)) * s
    box = [0, 0, w * s - 1, h * s - 1]
    if outline and min(w, h) <= 2 * width + 1:
        # Too small for a border (a widget before its first layout pass).
        fill, outline = outline, None
    if outline:
        d.rounded_rectangle(box, radius=r, fill=hex_to_rgb(outline))
        inset = width * s
        d.rounded_rectangle([inset, inset, w * s - 1 - inset, h * s - 1 - inset],
                            radius=max(r - inset, 0), fill=hex_to_rgb(fill))
        inner_top = inset
    else:
        d.rounded_rectangle(box, radius=r, fill=hex_to_rgb(fill))
        inner_top = 0

    if sheen > 0:
        # Lighter top half, clipped to the shape by drawing through a mask.
        mask = Image.new("L", big.size, 0)
        md = ImageDraw.Draw(mask)
        inset = width * s if outline else 0
        md.rounded_rectangle([inset, inset, w * s - 1 - inset, h * s - 1 - inset],
                             radius=max(r - inset, 0), fill=255)
        md.rectangle([0, h * s // 2, w * s, h * s], fill=0)
        top = Image.new("RGBA", big.size, hex_to_rgb(lighten(fill, 0.05 * sheen)) + (255,))
        big.paste(top, (0, 0), mask)
        hl = hex_to_rgb(lighten(fill, 0.16 * sheen))
        y = inner_top + s // 2
        d.line([(r * 0.8, y), (w * s - r * 0.8, y)], fill=hl, width=s)

    return big.resize((w, h), Image.LANCZOS)


def rrect(canvas, x, y, w, h, radius, fill, outline=None, bg=None, sheen=0.0,
          width=1, tags=(), anchor="nw"):
    """Draw a cached anti-aliased rounded rectangle on `canvas`."""
    key = ("rrect", int(w), int(h), radius, fill, outline, bg, sheen, width)
    image = _cached(key, lambda: render_rrect(w, h, radius, fill, outline, bg, sheen, width))
    return canvas.create_image(x, y, image=image, anchor=anchor, tags=tags)


def render_circle(d, fill, bg=None, outline=None, width=1):
    s = SUPERSAMPLE
    big = Image.new("RGBA", (d * s, d * s), hex_to_rgb(bg) + (255,) if bg else (0, 0, 0, 0))
    dr = ImageDraw.Draw(big)
    if outline:
        dr.ellipse([0, 0, d * s - 1, d * s - 1], fill=hex_to_rgb(outline))
        i = width * s
        dr.ellipse([i, i, d * s - 1 - i, d * s - 1 - i], fill=hex_to_rgb(fill))
    else:
        dr.ellipse([0, 0, d * s - 1, d * s - 1], fill=hex_to_rgb(fill))
    return big.resize((d, d), Image.LANCZOS)


def circle(canvas, cx, cy, d, fill, bg=None, outline=None, width=1, tags=()):
    key = ("circle", int(d), fill, bg, outline, width)
    image = _cached(key, lambda: render_circle(int(d), fill, bg, outline, width))
    return canvas.create_image(cx, cy, image=image, anchor="center", tags=tags)


def thumbnail(image, size, bg="#1d222c", radius=5):
    """Fit `image` inside a size x size rounded tile (returns a PIL image)."""
    tile = Image.new("RGBA", (size, size), hex_to_rgb(bg) + (255,))
    pic = image.convert("RGB").copy()
    pic.thumbnail((size - 6, size - 6), Image.NEAREST if max(pic.size) < size // 2 else Image.LANCZOS)
    if max(pic.size) < size // 2:
        # Tiny captures (an icon, a digit) are enlarged with hard pixels so
        # they stay legible instead of blurring.
        k = max(1, (size - 6) // max(pic.size))
        pic = pic.resize((pic.width * k, pic.height * k), Image.NEAREST)
    tile.paste(pic, ((size - pic.width) // 2, (size - pic.height) // 2))
    s = SUPERSAMPLE
    mask = Image.new("L", (size * s, size * s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size * s - 1, size * s - 1], radius=radius * s,
                                           fill=255)
    mask = mask.resize((size, size), Image.LANCZOS)
    tile.putalpha(mask)
    return tile
