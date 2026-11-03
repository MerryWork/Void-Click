"""Cut-outs: removing the parts of a capture that shouldn't be matched.

A capture of a meter, a crosshair or a health bar usually drags along
whatever was behind it - a character, a map, the sky. When that background
changes, the capture stops matching. Cutting it out marks those pixels as
transparent, and the matcher then ignores them (see matcher.mask_of).
"""

import numpy as np
from PIL import Image

from . import matcher


def _rgb(image):
    return np.asarray(image.convert("RGB"), dtype=np.int16)


def _near(arr, colors, tolerance):
    hit = np.zeros(arr.shape[:2], dtype=bool)
    for c in colors:
        target = np.array(c[:3], dtype=np.int16)
        hit |= (np.abs(arr - target) <= tolerance).all(axis=2)
    return hit


def _with_mask(image, keep):
    rgba = image.convert("RGB").convert("RGBA")
    rgba.putalpha(Image.fromarray(np.where(keep, 255, 0).astype(np.uint8)))
    return rgba


def keep_colors(image, colors, tolerance=40):
    """Keep only pixels near one of `colors`; everything else is ignored."""
    return _with_mask(image, _near(_rgb(image), colors, tolerance))


def remove_colors(image, colors, tolerance=40):
    """Ignore pixels near `colors`, on top of anything already removed."""
    keep = _near(_rgb(image), colors, tolerance) == False  # noqa: E712
    existing = matcher.mask_of(image)
    if existing is not None:
        keep &= existing
    return _with_mask(image, keep)


def build(image, keep=(), remove=(), tolerance=40):
    """Cut-out from scratch: keep pixels near `keep` colours (all, if none
    are given), minus pixels near `remove` colours. Works from the image's
    original pixels, so it can be redone any number of times."""
    arr = _rgb(image)
    mask = _near(arr, keep, tolerance) if keep else np.ones(arr.shape[:2], dtype=bool)
    if remove:
        mask &= ~_near(arr, remove, tolerance)
    if mask.all():
        return image.convert("RGB")
    return _with_mask(image, mask)


def clear(image):
    """Undo a cut-out: every pixel counts again."""
    return image.convert("RGB")


def is_cutout(image):
    return matcher.mask_of(image) is not None


def kept_fraction(image):
    mask = matcher.mask_of(image)
    return 1.0 if mask is None else float(mask.mean())


def on_checkerboard(image, cell=4):
    """Show removed pixels as a grey checkerboard, the usual 'transparent' cue."""
    rgba = image.convert("RGBA")
    w, h = rgba.size
    yy, xx = np.mgrid[0:h, 0:w]
    board = np.where(((xx // cell + yy // cell) % 2)[..., None] == 0, 58, 42).astype(np.uint8)
    bg = Image.fromarray(np.repeat(board, 3, axis=2), "RGB").convert("RGBA")
    return Image.alpha_composite(bg, rgba).convert("RGB")
