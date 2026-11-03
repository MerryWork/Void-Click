"""Plain-language explanations of images and match scores.

Raw numbers like "0.81" mean little to most people. Everything the UI says
about how good an image is, or how a test went, comes from here, so the
wording is consistent and testable.
"""

from dataclasses import dataclass

import numpy as np

from . import matcher

GOOD, OK, WEAK = "good", "ok", "weak"


@dataclass
class Verdict:
    level: str        # good | ok | weak
    title: str        # a few words
    detail: str       # one sentence: why, and what to do


def strictness(confidence):
    """Word for a Match setting."""
    if confidence >= 0.98:
        return "Exact"
    if confidence >= 0.9:
        return "Strict"
    if confidence >= 0.75:
        return "Balanced"
    return "Loose"


def image_quality(image):
    """How well this capture is likely to be found, and why."""
    rgb = matcher.as_rgb(image)
    h, w = rgb.shape[:2]
    gray = matcher.to_gray(rgb)
    mask = matcher.mask_of(image)
    if mask is not None:
        return _cutout_quality(gray, mask)
    if min(w, h) < 8 or w * h < 120:
        return Verdict(WEAK, "Very small",
                       f"At {w}×{h} px it can match in many places. Capture a bit more "
                       "around it, like the whole button.")
    if gray.std() < matcher.FLAT_STD:
        return Verdict(WEAK, "One flat colour",
                       "There is no shape to recognise, so it may match the wrong place. "
                       "Use a Find colour step, or capture something with an edge or text.")
    # Share of pixels sitting on an edge - text, borders, icon outlines.
    gy = np.abs(np.diff(gray, axis=0))
    gx = np.abs(np.diff(gray, axis=1))
    edges = (np.count_nonzero(gy > 24) + np.count_nonzero(gx > 24)) / float(w * h * 2)
    if edges < 0.015:
        return Verdict(OK, "Low detail",
                       "Mostly smooth colour with little shape. It may work - press Test to "
                       "check - but text or an outline makes it far more reliable.")
    if w * h > 400 * 300:
        return Verdict(OK, "Large",
                       "Big captures are slower to find and break if any part changes. "
                       "Capture just the part you want to click.")
    return Verdict(GOOD, "Good image", "Clear detail and a sensible size - easy to find.")


def _cutout_quality(gray, mask):
    kept = int(mask.sum())
    share = mask.mean()
    if kept < 30 or share < 0.02:
        return Verdict(WEAK, "Almost nothing kept",
                       f"Only {kept} pixels ({share:.0%}) are left to compare, so it can match almost "
                       "anywhere. Edit the cut-out and keep a wider colour range.")
    if matcher._uses_agreement(gray, mask):
        return Verdict(OK, "Cut-out \u2014 shape only",
                       f"{share:.0%} of the image is kept, in just a few shades, so mainly its shape "
                       "is compared - the background behind it is ignored. Set a Search area "
                       "around it: shapes like this are searched at full detail, which is "
                       "slow across a whole screen.")
    return Verdict(GOOD, "Cut-out",
                   f"{share:.0%} of the image is kept; the rest is ignored, so changes behind "
                   "it don't matter.")


def test_result(score, confidence, found, elapsed_ms=None):
    """What a Test result means, in words, with a next step."""
    pct = f"{score:.0%}"
    need = f"{confidence:.0%}"
    speed = f" in {elapsed_ms:.0f} ms" if elapsed_ms is not None else ""
    if found and score >= 0.97:
        return Verdict(GOOD, "Found — near-identical",
                       f"{pct} similar{speed}. This step will work as it is.")
    if found:
        return Verdict(GOOD, "Found",
                       f"{pct} similar (needs {need}){speed}. Small differences such as a hover "
                       "glow are fine.")
    if score >= confidence - 0.12 and score > 0.4:
        lower = max(0.5, int(score * 100 - 2) / 100.0)
        return Verdict(OK, "Almost — just under your setting",
                       f"The closest spot was {pct} similar but this step needs {need}. "
                       f"If the picture on the right is the right thing, lower Match to "
                       f"{lower:.0%}; otherwise recapture it.")
    return Verdict(WEAK, "Not on screen",
                   f"Nothing was more than {pct} similar. Make sure it is visible and not "
                   "covered, or recapture it the way it looks now.")


def color_result(found):
    if found:
        return Verdict(GOOD, "Colour found", "The highlighted spot is where it will click.")
    return Verdict(WEAK, "Colour not on screen",
                   "No pixel was within the tolerance. Pick the colour again, or raise "
                   "Tolerance a little.")
