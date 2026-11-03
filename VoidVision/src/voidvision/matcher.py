"""Finding a captured image on the screen.

Matching is normalised cross-correlation (NCC) on greyscale, which tolerates
brightness and contrast shifts such as hover glows or a dimmed window. A score
of 1.0 is a pixel-perfect match; around 0.8 and up is usually the same thing.

NCC over a whole screen is computed with FFTs (numpy only). Large templates are
searched first on a 2x/4x downscaled copy, and the best few candidates are then
re-scored at full resolution, which keeps a 1080p search well under a second.
If OpenCV happens to be installed it is used for the score map instead - it is
much faster, but never required.

Cut-out templates (RGBA with transparent pixels) are matched on their kept
pixels only - masked NCC - so a background showing through them is ignored.

Greyscale matching cannot tell a red button from a green one of the same
brightness, so `color=True` additionally compares the colours of each
candidate and rejects ones that differ.
"""

import time
from dataclasses import dataclass

import numpy as np

try:  # optional accelerator
    import cv2  # type: ignore
except Exception:  # pragma: no cover - depends on the machine
    cv2 = None

FLAT_STD = 2.0        # templates flatter than this use a difference metric
CANDIDATES = 6        # coarse-search candidates refined at full resolution
COLOR_TOLERANCE = 0.12
FLAT_PIXEL_TOLERANCE = 12   # grey levels a kept cut-out pixel may differ by
AGREE_BIN = 12              # shades closer than this count as one level
AGREE_MAX_LEVELS = 6        # cut-outs with this few shades use pixel agreement
UNIFORM_FROM = 0.3          # surrounding spots this alike to the kept colour start a penalty
RING_RADIUS = 3             # how far around kept pixels counts as "surrounding"
RING_TOLERANCE = 8          # grey levels for "the same colour" in that check


@dataclass
class Match:
    x: int        # top-left, in haystack pixels
    y: int
    w: int
    h: int
    score: float
    elapsed_ms: float = 0.0

    @property
    def center(self):
        return self.x + self.w / 2.0, self.y + self.h / 2.0


# ---------------------------------------------------------------- conversions

def as_rgb(image):
    """PIL image or array -> HxWx3 uint8 array."""
    if isinstance(image, np.ndarray):
        arr = image
        if arr.ndim == 2:
            return np.repeat(arr[:, :, None], 3, axis=2).astype(np.uint8)
        return arr[:, :, :3].astype(np.uint8)
    return np.asarray(image.convert("RGB"), dtype=np.uint8)


_LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float32)


def mask_of(image):
    """Which template pixels count (bool HxW), or None when all of them do.

    A cut-out image is an RGBA image whose removed pixels are transparent;
    those pixels are left out of matching entirely, so whatever shows through
    behind them (a moving character, a changing background) doesn't matter.
    """
    if isinstance(image, np.ndarray):
        if image.ndim == 3 and image.shape[2] == 4:
            alpha = image[:, :, 3]
        else:
            return None
    else:
        if image.mode not in ("RGBA", "LA", "PA") and "transparency" not in image.info:
            return None
        alpha = np.asarray(image.convert("RGBA"))[:, :, 3]
    keep = alpha >= 128
    return None if keep.all() else keep


def to_gray(rgb):
    return rgb[:, :, :3].astype(np.float32) @ _LUMA


def _fast_len(n):
    """Smallest 2^a * 3^b * 5^c >= n - FFTs of these sizes are several times faster."""
    best = 1 << (n - 1).bit_length()
    p5 = 1
    while p5 < best:
        p35 = p5
        while p35 < best:
            q = p35
            while q < n:
                q *= 2
            best = min(best, q)
            p35 *= 3
        p5 *= 5
    return best


def _downscale(gray, factor):
    if factor == 1:
        return gray
    h = gray.shape[0] // factor * factor
    w = gray.shape[1] // factor * factor
    g = gray[:h, :w]
    return g.reshape(h // factor, factor, w // factor, factor).mean(axis=(1, 3))


# ---------------------------------------------------------------- score maps

def _window_sums(a, h, w):
    """Sum of every h x w window of `a` (valid positions only)."""
    ii = np.zeros((a.shape[0] + 1, a.shape[1] + 1), dtype=np.float64)
    ii[1:, 1:] = a.cumsum(0).cumsum(1)
    return ii[h:, w:] - ii[:-h, w:] - ii[h:, :-w] + ii[:-h, :-w]


def _correlate_sum(pairs):
    """sum(correlate(image_i, kernel_i)) with a single inverse FFT."""
    H, W = pairs[0][0].shape
    h, w = pairs[0][1].shape
    shape = (_fast_len(H + h - 1), _fast_len(W + w - 1))
    acc = None
    for image, kernel in pairs:
        prod = np.fft.rfft2(image, shape) * np.fft.rfft2(kernel[::-1, ::-1], shape)
        acc = prod if acc is None else acc + prod
    return np.fft.irfft2(acc, shape)[h - 1:H, w - 1:W]


def _uses_agreement(templ, mask):
    """True for cut-outs with only a few shades kept (scored pixel by pixel)."""
    if mask is None:
        return False
    return len(np.unique(np.round(templ[mask] / AGREE_BIN))) <= AGREE_MAX_LEVELS


def _correlate(image, kernel):
    """Valid-mode cross-correlation via FFT."""
    H, W = image.shape
    h, w = kernel.shape
    shape = (_fast_len(H + h - 1), _fast_len(W + w - 1))
    f = np.fft.rfft2(image, shape)
    k = np.fft.rfft2(kernel[::-1, ::-1], shape)
    full = np.fft.irfft2(f * k, shape)
    return full[h - 1:H, w - 1:W]


def _dilate(mask, radius):
    """Grow a boolean mask by `radius` pixels (square neighbourhood)."""
    out = mask.copy()
    h, w = mask.shape
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dy == 0 and dx == 0:
                continue
            ys, yd = (slice(0, h - dy), slice(dy, h)) if dy >= 0 else (slice(-dy, h), slice(0, h + dy))
            xs, xd = (slice(0, w - dx), slice(dx, w)) if dx >= 0 else (slice(-dx, w), slice(0, w + dx))
            out[yd, xd] |= mask[ys, xs]
    return out


def _masked_score_map(hay, templ, mask):
    """NCC computed over the kept pixels only (masked NCC, all via FFT)."""
    m = mask.astype(np.float64)
    n = m.sum()
    if n < 4:
        return np.zeros((hay.shape[0] - templ.shape[0] + 1, hay.shape[1] - templ.shape[1] + 1))
    kept = templ[mask]
    t_mean = kept.mean()
    levels = np.unique(np.round(kept / AGREE_BIN))
    if len(levels) <= AGREE_MAX_LEVELS:
        # Few distinct shades kept (e.g. just the white of a bar, with some
        # anti-aliased edge pixels): the shape is in *where* they are, and NCC
        # has too little variation to work with. Score = share of kept spots
        # that still show their own shade. Something crossing the bar (a
        # moving marker) then costs only the pixels it covers.
        quant = np.round(templ / AGREE_BIN)
        counts, pairs = [], []
        for level in levels:
            spots = (mask & (quant == level)).astype(np.float64)
            counts.append(spots.sum())
            close = (np.abs(hay - level * AGREE_BIN) <= FLAT_PIXEL_TOLERANCE).astype(np.float64)
            pairs.append((close, spots))
        agree = _correlate_sum(pairs)
        score = np.clip(agree / n, 0.0, 1.0)
        # The shape only means something if the removed spots *differ* from
        # it: a plain wall of the kept colour would otherwise pass for a
        # white tick bar. Where most removed spots also show the main kept
        # shade, mark the score down - by up to 60% for a fully uniform area.
        # Only the removed spots right next to kept ones matter (the gaps
        # between ticks, the rows just above and below a bar's line) - those
        # are what make it a shape rather than a patch of colour.
        ring = _dilate(mask, RING_RADIUS) & ~mask
        n_ring = ring.sum()
        if n_ring >= 4:
            main = levels[int(np.argmax(counts))] * AGREE_BIN
            same = (np.abs(hay - main) <= RING_TOLERANCE).astype(np.float64)
            r = np.clip(_correlate(same, ring.astype(np.float64)) / n_ring, 0.0, 1.0)
            score *= 1.0 - 0.6 * np.clip((r - UNIFORM_FROM) / (1.0 - UNIFORM_FROM), 0.0, 1.0)
        return score
    s1 = _correlate(hay, m)           # sum of image pixels under the kept spots
    s2 = _correlate(hay * hay, m)
    t = (templ - t_mean) * m
    t_norm = np.sqrt((t * t).sum())
    corr = _correlate(hay, t)
    var = np.maximum(s2 - s1 * s1 / n, 0)
    denom = np.sqrt(var) * t_norm
    out = np.zeros_like(corr)
    ok = denom > 1e-6 * max(t_norm, 1.0) * np.sqrt(n)
    out[ok] = corr[ok] / denom[ok]
    return np.clip(out, -1.0, 1.0)


def score_map(hay, templ, mask=None):
    """Similarity of `templ` at every position of `hay` (both greyscale).

    `mask` (bool, template-sized) limits the comparison to the True pixels.
    """
    h, w = templ.shape
    if hay.shape[0] < h or hay.shape[1] < w:
        return np.zeros((0, 0))
    # float64 throughout: the variance below is a difference of two large
    # sums, which float32 cancels into noise on a full screen.
    hay = np.asarray(hay, dtype=np.float64)
    templ = np.asarray(templ, dtype=np.float64)
    if mask is not None:
        return _masked_score_map(hay, templ, mask)
    n = float(h * w)
    t_std = templ.std()

    if t_std < FLAT_STD:
        # A flat patch (a solid colour swatch) has no shape for NCC to latch
        # onto - score by mean absolute closeness instead.
        mean = _window_sums(hay, h, w) / n
        sq = _window_sums(hay * hay, h, w) / n
        spread = np.sqrt(np.maximum(sq - mean * mean, 0))
        diff = np.abs(mean - templ.mean()) + spread
        return 1.0 - np.clip(diff / 64.0, 0, 1)

    if cv2 is not None:
        res = cv2.matchTemplate(hay.astype(np.float32), templ.astype(np.float32),
                                cv2.TM_CCOEFF_NORMED)
        return np.nan_to_num(res.astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)

    t = templ - templ.mean()
    t_norm = np.sqrt((t * t).sum())
    corr = _correlate(hay, t)
    s1 = _window_sums(hay, h, w)
    s2 = _window_sums(hay * hay, h, w)
    var = np.maximum(s2 - s1 * s1 / n, 0)
    denom = np.sqrt(var) * t_norm
    out = np.zeros_like(corr)
    ok = denom > 1e-6 * max(t_norm, 1.0) * np.sqrt(n)
    out[ok] = corr[ok] / denom[ok]
    return np.clip(out, -1.0, 1.0)


def _peaks(scores, count, min_dist_y, min_dist_x, floor=-1.0):
    """Top `count` positions, suppressing neighbours of each pick."""
    s = scores.copy()
    found = []
    for _ in range(count):
        if s.size == 0:
            break
        idx = int(np.argmax(s))
        y, x = divmod(idx, s.shape[1])
        val = float(s[y, x])
        if val <= floor:
            break
        found.append((y, x, val))
        s[max(0, y - min_dist_y):y + min_dist_y + 1,
          max(0, x - min_dist_x):x + min_dist_x + 1] = -2.0
    return found


def _color_similarity(hay_rgb, templ_rgb, x, y, mask=None):
    h, w = templ_rgb.shape[:2]
    patch = hay_rgb[y:y + h, x:x + w].astype(np.float64)
    if patch.shape[:2] != (h, w):
        return 0.0
    t = templ_rgb.astype(np.float64)
    if mask is not None:
        patch, t = patch[mask], t[mask]
    else:
        patch, t = patch.reshape(-1, 3), t.reshape(-1, 3)
    # Compare average colour per channel - robust to small misalignment but
    # catches a red-vs-green swap that greyscale cannot see.
    diff = np.abs(patch.mean(axis=0) - t.mean(axis=0)).max() / 255.0
    return 1.0 - diff


# ---------------------------------------------------------------- public API

def _downscale_mask(mask, factor):
    if mask is None or factor == 1:
        return mask
    small = _downscale(mask.astype(np.float64), factor) >= 0.5
    return None if small.all() else small


def _search(hay_rgb, templ_rgb, count, color, mask=None):
    hay = to_gray(hay_rgb)
    templ = to_gray(templ_rgb)
    h, w = templ.shape
    if hay.shape[0] < h or hay.shape[1] < w:
        return []

    kept = templ[mask] if mask is not None else templ
    factor = 1
    # Shape-only cut-outs (thin lines, ticks) blur away when downscaled, so
    # they are always searched at full resolution.
    if (cv2 is None or mask is not None) and kept.std() >= FLAT_STD \
            and not _uses_agreement(templ, mask):
        smallest = min(h, w)
        if smallest >= 64 and hay.size > 400_000:
            factor = 4
        elif smallest >= 24 and hay.size > 200_000:
            factor = 2

    if factor == 1:
        scores = score_map(hay, templ, mask)
        picks = _peaks(scores, count, max(1, h // 2), max(1, w // 2))
        results = [(x, y, v) for y, x, v in picks]
    else:
        small_mask = _downscale_mask(mask, factor)
        if mask is not None and small_mask is not None and small_mask.sum() < 4:
            small_mask = None
        coarse = score_map(_downscale(hay, factor), _downscale(templ, factor), small_mask)
        picks = _peaks(coarse, max(count, CANDIDATES),
                       max(1, h // (2 * factor)), max(1, w // (2 * factor)))
        results = []
        margin = factor * 2
        for cy, cx, _ in picks:
            x0 = max(0, cx * factor - margin)
            y0 = max(0, cy * factor - margin)
            x1 = min(hay.shape[1], cx * factor + w + margin)
            y1 = min(hay.shape[0], cy * factor + h + margin)
            local = score_map(hay[y0:y1, x0:x1], templ, mask)
            if local.size == 0:
                continue
            ly, lx = divmod(int(np.argmax(local)), local.shape[1])
            results.append((x0 + lx, y0 + ly, float(local[ly, lx])))
        # Refinement can land two coarse picks on the same spot.
        results.sort(key=lambda r: -r[2])
        unique = []
        for r in results:
            if all(abs(r[0] - u[0]) > w // 2 or abs(r[1] - u[1]) > h // 2 for u in unique):
                unique.append(r)
        results = unique

    if color:
        rescored = []
        for x, y, v in results:
            sim = _color_similarity(hay_rgb, templ_rgb, x, y, mask)
            if sim < 1.0 - COLOR_TOLERANCE:
                v = min(v, sim - COLOR_TOLERANCE)
            rescored.append((x, y, v))
        results = sorted(rescored, key=lambda r: -r[2])
    return [Match(int(x), int(y), w, h, float(v)) for x, y, v in results]


def find(haystack, template, confidence=0.85, color=False):
    """Best match of `template` in `haystack`, or None if below `confidence`."""
    start = time.perf_counter()
    hay_rgb, templ_rgb = as_rgb(haystack), as_rgb(template)
    results = _search(hay_rgb, templ_rgb, CANDIDATES if color else 1, color, mask_of(template))
    elapsed = (time.perf_counter() - start) * 1000
    if not results:
        return None
    best = results[0]
    best.elapsed_ms = elapsed
    return best if best.score >= confidence else None


def best(haystack, template, color=False):
    """Best match regardless of confidence - for 'how close was it?' feedback."""
    start = time.perf_counter()
    results = _search(as_rgb(haystack), as_rgb(template), CANDIDATES if color else 1, color,
                      mask_of(template))
    if not results:
        return None
    results[0].elapsed_ms = (time.perf_counter() - start) * 1000
    return results[0]


def find_all(haystack, template, confidence=0.85, color=False, limit=50):
    """Every non-overlapping match at or above `confidence`, best first."""
    results = _search(as_rgb(haystack), as_rgb(template), limit, color, mask_of(template))
    return [m for m in results if m.score >= confidence]


def find_color(haystack, rgb, tolerance=12):
    """Centre of the first patch of `rgb` (+/- tolerance per channel), or None.

    Returns a Match whose box spans the connected run of matching pixels near
    the first hit, so clicking its centre lands inside the coloured area.
    """
    start = time.perf_counter()
    arr = as_rgb(haystack).astype(np.int16)
    target = np.array(rgb[:3], dtype=np.int16)
    mask = (np.abs(arr - target) <= tolerance).all(axis=2)
    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        return None
    y0, x0 = int(ys[0]), int(xs[0])
    # Grow a box around the first hit within a local neighbourhood.
    r = 40
    sub = mask[y0:y0 + r * 2, max(0, x0 - r):x0 + r]
    sy, sx = np.nonzero(sub)
    left = max(0, x0 - r) + int(sx.min())
    right = max(0, x0 - r) + int(sx.max())
    bottom = y0 + int(sy.max())
    m = Match(left, y0, right - left + 1, bottom - y0 + 1, 1.0)
    m.elapsed_ms = (time.perf_counter() - start) * 1000
    return m


# ---------------------------------------------------------------- timing bars

def color_runs(haystack, rgb, tolerance=40, min_pixels=2):
    """Horizontal spans [(x0, x1, pixels)] where `rgb` appears, widest first.

    Used on a bar's screen area: each column counts as a hit when at least
    `min_pixels` of its pixels are the colour, and neighbouring hit columns
    (allowing 1px gaps) form one run.
    """
    arr = as_rgb(haystack).astype(np.int16)
    target = np.array(rgb[:3], dtype=np.int16)
    mask = (np.abs(arr - target) <= tolerance).all(axis=2)
    counts = mask.sum(axis=0)
    cols = counts >= min_pixels
    runs, start, gap = [], None, 0
    for x, hit in enumerate(cols):
        if hit:
            if start is None:
                start = x
            gap, end = 0, x
        elif start is not None:
            gap += 1
            if gap > 1:
                runs.append((start, end, int(counts[start:end + 1].sum())))
                start = None
    if start is not None:
        runs.append((start, end, int(counts[start:end + 1].sum())))
    runs.sort(key=lambda r: -r[2])
    return runs


def marker_position(haystack, rgb, tolerance=40):
    """Centre of the marker along the bar, as a fraction 0..1, or None."""
    width = as_rgb(haystack).shape[1]
    runs = color_runs(haystack, rgb, tolerance)
    if not runs or width < 2:
        return None
    x0, x1, _ = runs[0]
    return ((x0 + x1) / 2.0) / (width - 1)


def _color_columns(arr, rgb, tolerance, min_pixels=2):
    target = np.array(rgb[:3], dtype=np.int16)
    mask = (np.abs(arr - target) <= tolerance).all(axis=2)
    counts = mask.sum(axis=0)
    return counts >= min_pixels, counts


def zone_span(haystack, rgb, tolerance=40, bridge_rgb=None):
    """The spot's extent along the bar, (start, end) fractions, or None.

    `bridge_rgb` is the marker's colour: where the marker sits on the spot it
    hides part of it, splitting the spot's colour in two. Marker columns that
    touch the spot are treated as spot, so it is still seen whole.
    """
    arr = as_rgb(haystack).astype(np.int16)
    width = arr.shape[1]
    if width < 2:
        return None
    spot_cols, counts = _color_columns(arr, rgb, tolerance)
    if not spot_cols.any():
        return None
    joined = spot_cols.copy()
    if bridge_rgb is not None:
        joined |= _color_columns(arr, bridge_rgb, tolerance)[0]
    best, best_pixels, start = None, 0, None
    for x in range(width + 1):
        on = x < width and (joined[x] or (x + 1 < width and joined[x - 1] and joined[x + 1]
                                          if 0 < x else False))
        if on and start is None:
            start = x
        elif not on and start is not None:
            pixels = int(counts[start:x][spot_cols[start:x]].sum())
            if pixels > best_pixels:
                inside = np.nonzero(spot_cols[start:x])[0]
                best, best_pixels = (start + inside[0], start + inside[-1]), pixels
            start = None
    if best is None:
        return None
    return best[0] / (width - 1), best[1] / (width - 1)
