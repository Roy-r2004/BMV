"""A brand palette derived from the business itself, not from an industry string.

Why this exists
---------------
Measured over the 62 archived workspaces that shipped a ``mock.ts``: **three**
distinct ``primary_color`` values — ``#0f766e`` x58, ``#0f172a`` x3, ``#be185d``
x1. Every site looked the same because two industry->palette keyword tables
disagreed and the worse one ran first (``visual_demo_enrichment.THEME_PALETTES``,
whose ``generic`` and ``wellness`` buckets are the *same colour*), after which
``brand_locked=True`` sealed it for the rest of the run.

Replacing one keyword table with a better keyword table does not fix this, and
that is measured too, not assumed. Simulated over the same 62 workspaces,
letting ``brand_brief._industry_bucket`` decide alone yields **three** distinct
colours — the identical count, merely redistributed. It also puts 28 of the 62
in ``wellness``, because the art-gallery briefs contain the sentence *"not a
booking SaaS or clinic front desk"* and the table matches the word ``clinic``
inside a negation.

So the palette is derived from the brand's own identity:

* deterministic — same business, same palette, on every run and every machine;
* stable — it does not move when a description is edited or a model is swapped;
* distinct — different businesses land on different palettes;
* legible by construction — every colour's lightness is *solved* against its
  own background to hit a contrast ratio, so no hue can ship an unreadable
  button. There is no hand-checked colour list to keep in contrast repair.

No industry string is read anywhere in this module. That is the point of it.
"""
from __future__ import annotations

import hashlib
import re
from typing import Iterator

#: Hues are a ring rather than a continuum: two businesses 3 degrees apart would
#: look identical and read as the monoculture this module exists to remove.
#: 24 stops at 15 degrees are individually nameable.
_HUE_STOPS = 24

#: A second axis, so the identity space is wider than the hue ring without
#: adding hues so close together they stop being distinguishable. A vivid teal
#: and a slate teal are different brands; teal and teal-3-degrees-over are not.
_TONES: tuple[tuple[str, float, float], ...] = (
    # label, primary saturation, background saturation
    ("vivid", 0.62, 0.34),
    ("slate", 0.34, 0.20),
)

#: Contrast targets, each against the surface the colour is actually used on.
#: 4.5 is the WCAG AA floor for normal text; the primary target sits above it so
#: that white-on-brand survives the antialiasing the floor does not model.
_PRIMARY_ON_WHITE = 5.2
_SECONDARY_ON_WHITE = 10.0
_TEXT_ON_BACKGROUND = 13.0
_MUTED_ON_BACKGROUND = 4.8

_BACKGROUND_LIGHTNESS = 0.965
_WHITE = (255, 255, 255)

_PUNCT_RE = re.compile(r"[^a-z0-9]+")

#: How many distinct palettes exist. Declared before the functions that use it
#: so ``palette_for_index`` can wrap on it.
IDENTITY_COUNT = _HUE_STOPS * len(_TONES)


def _hsl_to_rgb(hue_deg: float, sat: float, light: float) -> tuple[int, int, int]:
    """Standard HSL->sRGB. ``hue_deg`` in degrees, ``sat``/``light`` in [0, 1]."""

    c = (1.0 - abs(2.0 * light - 1.0)) * sat
    h = (hue_deg % 360.0) / 60.0
    x = c * (1.0 - abs(h % 2.0 - 1.0))
    m = light - c / 2.0
    if h < 1:
        rgb = (c, x, 0.0)
    elif h < 2:
        rgb = (x, c, 0.0)
    elif h < 3:
        rgb = (0.0, c, x)
    elif h < 4:
        rgb = (0.0, x, c)
    elif h < 5:
        rgb = (x, 0.0, c)
    else:
        rgb = (c, 0.0, x)
    return tuple(int(round((v + m) * 255)) for v in rgb)  # type: ignore[return-value]


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def channel(value: int) -> float:
        v = value / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    """WCAG 2.x contrast ratio between two sRGB colours."""

    la, lb = _relative_luminance(a), _relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _solve_lightness(
    hue: float, sat: float, against: tuple[int, int, int], target: float
) -> float:
    """Darkest-to-lightest bisection for the lightness that hits ``target``.

    Luminance rises monotonically with HSL lightness at a fixed hue and
    saturation, so contrast against a light surface falls monotonically and a
    bisection is exact to the step count. 32 steps resolve lightness far below
    one 8-bit level, which is why the result is reproducible across machines.
    """

    lo, hi = 0.0, 1.0
    for _ in range(32):
        mid = (lo + hi) / 2.0
        if contrast_ratio(_hsl_to_rgb(hue, sat, mid), against) >= target:
            lo = mid
        else:
            hi = mid
    return lo


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def brand_identity_key(business_name: str | None, business_description: str | None = None) -> str:
    """The string a palette is derived from.

    The **name** is the brand, so the palette must not move when a description
    is reworded — requests 92, 95 and 97 are the same restaurant and must be the
    same colour. The description is a fallback only for nameless briefs.
    """

    name = _PUNCT_RE.sub(" ", str(business_name or "").casefold()).strip()
    if name:
        return name
    return _PUNCT_RE.sub(" ", str(business_description or "").casefold()).strip()


def palette_index(business_name: str | None, business_description: str | None = None) -> int:
    """Stable index into the identity space. ``blake2s`` so it is not seeded."""

    key = brand_identity_key(business_name, business_description)
    digest = hashlib.blake2s(key.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % (_HUE_STOPS * len(_TONES))


def palette_for_index(index: int) -> dict[str, str]:
    """The palette at one point in the identity space.

    One body, so a mutation to the derivation is visible from both entry points
    below. Session 8's rule: a test that drives its own copy of the producer is
    green with the producer deleted.
    """

    index %= IDENTITY_COUNT
    hue = (index % _HUE_STOPS) * (360.0 / _HUE_STOPS)
    _, primary_sat, background_sat = _TONES[index // _HUE_STOPS]
    secondary_hue = (hue + 12.0) % 360.0
    background = _hsl_to_rgb(hue, background_sat, _BACKGROUND_LIGHTNESS)
    text_sat = min(primary_sat, 0.30)
    muted_sat = min(primary_sat, 0.14)
    return {
        "primary": _hex(
            _hsl_to_rgb(hue, primary_sat, _solve_lightness(hue, primary_sat, _WHITE, _PRIMARY_ON_WHITE))
        ),
        "secondary": _hex(
            _hsl_to_rgb(
                secondary_hue,
                primary_sat,
                _solve_lightness(secondary_hue, primary_sat, _WHITE, _SECONDARY_ON_WHITE),
            )
        ),
        "background": _hex(background),
        "surface": _hex(_WHITE),
        "text": _hex(
            _hsl_to_rgb(hue, text_sat, _solve_lightness(hue, text_sat, background, _TEXT_ON_BACKGROUND))
        ),
        "muted": _hex(
            _hsl_to_rgb(hue, muted_sat, _solve_lightness(hue, muted_sat, background, _MUTED_ON_BACKGROUND))
        ),
    }


def derive_palette(
    business_name: str | None, business_description: str | None = None
) -> dict[str, str]:
    """Six brand colours for one business. Deterministic and contrast-solved."""

    return palette_for_index(palette_index(business_name, business_description))


def every_identity() -> Iterator[tuple[int, dict[str, str]]]:
    """Every palette the derivation can produce — the contrast test's corpus."""

    for index in range(IDENTITY_COUNT):
        yield index, palette_for_index(index)


__all__ = [
    "IDENTITY_COUNT",
    "brand_identity_key",
    "contrast_ratio",
    "derive_palette",
    "every_identity",
    "palette_for_index",
    "palette_index",
]
