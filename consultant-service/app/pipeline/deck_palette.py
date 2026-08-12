"""The deck's palette, read from the screens the pipeline actually rendered.

The deck used to be coloured from `visual_theme.primary_color` — a hex the
plan stage picked before a single pixel existed. The images then went and
looked however they looked, and the slide furniture around them was tinted
by a number that had never seen them. On a cinematic dark screenshot with a
warm brass accent, a slide framed in the plan's indigo reads as two
different documents stapled together.

So the palette is sampled from the bytes instead: the ink on the slide comes
out of the same picture it frames. Deterministic PIL, no model call, no cost
— the same screenshots produce the same deck every time.

How, and why each step is there:

  - Quantize each screen to a small adaptive palette and weight every colour
    by how much of the image it covers. Sampling single pixels finds
    whatever happened to be under the sampler; coverage finds what the
    screen is actually made of.
  - The BACKGROUND is the darkest heavily-covered colour. Cinematic UI is
    dark and mostly ground, so the most-covered dark tone is the room the
    interface lives in.
  - The ACCENT is the most colourful thing on screen, scored by saturation
    times coverage — not saturation alone, which finds a stray four-pixel
    error badge and paints the whole deck with it.
  - Everything is then FORCED to be legible. A palette read from an image
    has no obligation to be usable, and an unreadable slide is worse than a
    generic one: the accent is lightened or darkened until it clears 4.5:1
    against the surface it sits on, and if it cannot get there it is
    dropped for the brand colour.

Nothing here can fail the export. Every entry point returns a complete
palette; an unreadable file, a missing file, a greyscale screenshot and an
empty image list all fall back to the brand-derived palette, which is what
the deck used before this module existed.
"""

import colorsys
import logging
import os

from PIL import Image

logger = logging.getLogger("consultant.deck_palette")

# Sampled small. The palette is about broad areas of colour, and a 240px
# read is both faster and less distracted by single-pixel detail.
_SAMPLE_EDGE = 240
_QUANTIZE_COLORS = 16
# A colour has to cover this much of a screen before it can be the ground.
_MIN_GROUND_COVERAGE = 0.06
# Below this saturation nothing counts as an accent — a grey "accent" makes
# every rule and kicker on the deck invisible.
_MIN_ACCENT_SATURATION = 0.22
_MIN_ACCENT_CONTRAST = 4.5
# The deck's own fallback, used when the images cannot supply a palette.
_FALLBACK = {
    "bg": "#0B1020",
    "surface": "#141B2E",
    "line": "#2A334A",
    "accent": "#22D3EE",
    "accent_soft": "#67E8F9",
    "text": "#F8FAFC",
    "muted": "#94A3B8",
    "source": "fallback",
}


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _rgb(hex_color: str) -> tuple[int, int, int]:
    v = hex_color.lstrip("#")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    channels = []
    for c in rgb:
        s = c / 255
        channels.append(s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = _relative_luminance(a), _relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def _shift(rgb: tuple[int, int, int], *, lightness: float | None = None,
           saturation: float | None = None) -> tuple[int, int, int]:
    r, g, b = (c / 255 for c in rgb)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if lightness is not None:
        l = max(0.0, min(1.0, lightness))
    if saturation is not None:
        s = max(0.0, min(1.0, saturation))
    out = colorsys.hls_to_rgb(h, l, s)
    return tuple(int(round(c * 255)) for c in out)


def _weighted_colors(path: str) -> list[tuple[tuple[int, int, int], float]]:
    """[(rgb, coverage)] for one image, most-covered first. [] if unreadable."""
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((_SAMPLE_EDGE, _SAMPLE_EDGE))
            quantized = im.quantize(colors=_QUANTIZE_COLORS, method=Image.MEDIANCUT)
            palette = quantized.getpalette() or []
            counts = quantized.getcolors() or []
    except Exception as exc:
        logger.warning("deck palette: could not read %s (%s)", os.path.basename(path), exc)
        return []

    total = sum(count for count, _ in counts) or 1
    out = []
    for count, index in counts:
        base = index * 3
        if base + 2 >= len(palette):
            continue
        out.append(((palette[base], palette[base + 1], palette[base + 2]), count / total))
    out.sort(key=lambda item: -item[1])
    return out


def _saturation(rgb: tuple[int, int, int]) -> float:
    _, _, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    return s


def from_images(image_paths: list[str], brand_hex: str | None = None) -> dict[str, str]:
    """The deck palette for one request. Never raises; always complete."""
    weighted: list[tuple[tuple[int, int, int], float]] = []
    used = 0
    for path in image_paths:
        colors = _weighted_colors(path)
        if colors:
            used += 1
            weighted.extend(colors)
    if not weighted:
        return _from_brand(brand_hex)

    # Ground: darkest colour that still covers a real share of the screens.
    grounds = [(rgb, w) for rgb, w in weighted if w >= _MIN_GROUND_COVERAGE]
    if not grounds:
        grounds = weighted
    bg = min(grounds, key=lambda item: _relative_luminance(item[0]))[0]

    # Accent: colourful AND present. Saturation alone finds a stray badge.
    candidates = [
        (rgb, _saturation(rgb) * (w ** 0.5))
        for rgb, w in weighted
        if _saturation(rgb) >= _MIN_ACCENT_SATURATION
    ]
    if not candidates:
        # A greyscale set of screens genuinely has no accent to borrow.
        return _from_brand(brand_hex, bg=bg)
    accent = max(candidates, key=lambda item: item[1])[0]

    return _assemble(bg, accent, brand_hex, source=f"images({used})")


def _from_brand(brand_hex: str | None, bg: tuple[int, int, int] | None = None) -> dict[str, str]:
    """The pre-image behaviour, kept whole as the floor under everything.

    Everything goes through `_assemble`, including the no-brand case. An
    earlier version pasted a sampled ground into the fixed dark fallback and
    left its text colour alone — a pale greyscale screenshot then produced
    #F8FAFC body text on an #F0F0F5 ground, a contrast ratio of 1.09. The
    fallback exists to be the safe floor; it cannot have a path that skips
    the checks.
    """
    try:
        accent = _rgb(brand_hex) if brand_hex else _rgb(_FALLBACK["accent"])
    except (ValueError, IndexError):
        accent = _rgb(_FALLBACK["accent"])
        brand_hex = None
    ground = bg if bg is not None else _rgb(_FALLBACK["bg"])
    return _assemble(ground, accent, brand_hex, source="brand" if brand_hex else "fallback")


def _assemble(bg: tuple[int, int, int], accent: tuple[int, int, int],
              brand_hex: str | None, *, source: str) -> dict[str, str]:
    """Turns a ground and an accent into a full, legible palette."""
    # The ground is pushed dark enough to be a ground. A screenshot whose
    # most-covered tone is mid-grey would otherwise produce slides that are
    # neither light nor dark and read as a rendering fault.
    if _relative_luminance(bg) > 0.18:
        bg = _shift(bg, lightness=0.07, saturation=min(0.35, _saturation(bg)))

    # Surfaces are built on the ACCENT's hue, not the ground's. A cinematic
    # screenshot's darkest region is usually all but black, and neutral greys
    # lifted off it give the deck no relationship to the picture it frames —
    # correct, and characterless. Carrying the accent hue at low saturation
    # makes a panel read as the same material as the screen above it, which
    # is the whole point of sampling the image in the first place.
    accent_hue = colorsys.rgb_to_hls(*(c / 255 for c in accent))[0]

    def _tinted(lightness: float, saturation: float) -> tuple[int, int, int]:
        r, g, b = colorsys.hls_to_rgb(accent_hue, lightness, saturation)
        return tuple(int(round(c * 255)) for c in (r, g, b))

    bg = _tinted(max(0.035, min(0.09, _relative_luminance(bg) + 0.03)), 0.30)
    surface = _tinted(0.13, 0.24)
    line = _tinted(0.26, 0.20)

    # Legibility is not negotiable — walk the accent lighter until it clears
    # 4.5:1 on the surface, and abandon it for the brand if it never does.
    lit = accent
    lightness = colorsys.rgb_to_hls(*(c / 255 for c in accent))[1]
    while contrast(lit, surface) < _MIN_ACCENT_CONTRAST and lightness < 0.92:
        lightness += 0.04
        lit = _shift(accent, lightness=lightness)
    if contrast(lit, surface) < _MIN_ACCENT_CONTRAST:
        try:
            lit = _rgb(brand_hex) if brand_hex else _rgb(_FALLBACK["accent"])
        except (ValueError, IndexError):
            lit = _rgb(_FALLBACK["accent"])
        if contrast(lit, surface) < _MIN_ACCENT_CONTRAST:
            lit = _rgb(_FALLBACK["accent"])
            source = f"{source}->fallback-accent"

    text = (0xF8, 0xFA, 0xFC) if contrast((0xF8, 0xFA, 0xFC), bg) >= 7 else (0x0F, 0x17, 0x2A)
    muted = _shift(text, lightness=0.62, saturation=0.12)

    return {
        "bg": _hex(bg),
        "surface": _hex(surface),
        "line": _hex(line),
        "accent": _hex(lit),
        "accent_soft": _hex(_shift(lit, lightness=min(0.82, colorsys.rgb_to_hls(*(c / 255 for c in lit))[1] + 0.18))),
        "text": _hex(text),
        "muted": _hex(muted),
        "source": source,
    }
