"""W4 — deterministic presentation compositing.

The split this module exists to enforce: the image model renders UI TRUTH
(flat, straight-on, edge to edge, which is what it is good at), and Python
renders the PRESENTATION around it — browser chrome, a soft shadow, a
brand-tinted backdrop, detail crops. Asking the model for a laptop mockup
or a perspective shot garbles the interface text it just got right, and
that text is the entire product.

Everything here is PIL arithmetic: no model call, no cost, no variance.
The same screenshot composites to the same bytes every time.

Outputs per screen:
  <slug>_0.png          the raw screenshot (unchanged, still watermarked)
  <slug>_hero.png       chrome + shadow + backdrop, the deck/hero artifact
  <slug>_detail_1.png   a crop of the screen's top band, framed the same way
  <slug>_detail_2.png   a crop of its main content area

Crops are geometric, not semantic — a fixed top band and a fixed centre
region. Nothing here knows which pixels hold the chart, and pretending
otherwise (by asking a model where to crop) would spend money to make a
deterministic step unreliable.
"""

import io
import os

from PIL import Image, ImageDraw, ImageFilter

from app.pipeline.art_packs import derive_palette

COMPOSITE_VERSION = "composite-v1"

# Presentation geometry, all relative to the screenshot's width so a 1024px
# square and a 1408px widescreen render at the same visual weight.
_CHROME_HEIGHT_RATIO = 0.035
_CORNER_RADIUS_RATIO = 0.012
# Tight on purpose. The composite is placed inside a slide that already
# has its own margins, so generous padding here reads as a small picture
# floating in white — seen in the first rendered deck.
_MARGIN_RATIO = 0.05
_SHADOW_BLUR_RATIO = 0.022
_SHADOW_OFFSET_RATIO = 0.012


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (size[0] - 1, size[1] - 1)], radius=radius, fill=255)
    return mask


def _gradient_backdrop(size: tuple[int, int], top: str, bottom: str) -> Image.Image:
    """A vertical two-stop gradient, built one row at a time.

    Drawn at 1/8 scale and resized up: a 1600px-tall gradient costs 1600
    draw calls at full size and 200 this way, and the result is identical
    once it has been resampled — a linear ramp has nothing to lose.
    """
    width, height = size
    small = Image.new("RGB", (1, max(2, height // 8)))
    top_rgb = tuple(int(top.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    bottom_rgb = tuple(int(bottom.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    pixels = small.load()
    for y in range(small.height):
        t = y / max(1, small.height - 1)
        pixels[0, y] = tuple(round(top_rgb[i] + (bottom_rgb[i] - top_rgb[i]) * t) for i in range(3))
    return small.resize((width, height), Image.BILINEAR)


def _browser_chrome(width: int, height: int, radius: int, accent: str) -> Image.Image:
    """A restrained chrome bar: three dots and an address pill.

    Deliberately unbranded and slightly generic. A convincing replica of a
    specific browser invites the eye to check it against the real thing;
    the job here is only to say "this is a web application".
    """
    bar = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(bar)
    draw.rounded_rectangle([(0, 0), (width - 1, height + radius)], radius=radius, fill="#EDEFF3")
    draw.line([(0, height - 1), (width, height - 1)], fill="#DDE1E8", width=1)

    dot_r = max(3, height // 7)
    for i, color in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
        cx = int(height * 0.9) + i * dot_r * 3
        cy = height // 2
        draw.ellipse([(cx - dot_r, cy - dot_r), (cx + dot_r, cy + dot_r)], fill=color)

    pill_left = int(width * 0.22)
    pill_right = int(width * 0.78)
    pill_h = int(height * 0.52)
    pill_top = (height - pill_h) // 2
    draw.rounded_rectangle(
        [(pill_left, pill_top), (pill_right, pill_top + pill_h)],
        radius=pill_h // 2, fill="#FFFFFF", outline="#DDE1E8", width=1,
    )
    lock_r = max(2, pill_h // 6)
    lock_cx = pill_left + pill_h
    draw.ellipse(
        [(lock_cx - lock_r, height // 2 - lock_r), (lock_cx + lock_r, height // 2 + lock_r)],
        fill=accent,
    )
    return bar


def _framed(
    screenshot: Image.Image, palette: dict[str, str], logo: Image.Image | None,
    *, chrome: bool = True,
) -> Image.Image:
    """One screenshot -> rounded corners + shadow on a backdrop, with
    browser chrome when the image is a whole screen.

    Detail crops get `chrome=False`: a browser title bar sitting on top of a
    crop taken from the MIDDLE of a screen claims something untrue about
    what is being shown, and the eye catches it immediately.
    """
    shot = screenshot.convert("RGB")
    width, height = shot.size

    chrome_h = max(18, round(width * _CHROME_HEIGHT_RATIO)) if chrome else 0
    radius = max(6, round(width * _CORNER_RADIUS_RATIO))
    margin = round(width * _MARGIN_RATIO)
    blur = max(6, round(width * _SHADOW_BLUR_RATIO))
    offset = round(width * _SHADOW_OFFSET_RATIO)

    window = Image.new("RGB", (width, height + chrome_h), "#FFFFFF")
    if chrome_h:
        bar = _browser_chrome(width, chrome_h, radius, palette["primary"])
        window.paste(bar, (0, 0), bar)
    window.paste(shot, (0, chrome_h))
    window.putalpha(_rounded_mask(window.size, radius))

    canvas_size = (width + margin * 2, height + chrome_h + margin * 2)
    backdrop = _gradient_backdrop(canvas_size, palette["primary_tint"], palette["surface"])
    canvas = backdrop.convert("RGBA")

    # The shadow is the window's own silhouette, blurred — a rectangle
    # would show its corners through the window's rounded ones.
    shadow = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    silhouette = Image.new("RGBA", window.size, (17, 24, 39, 90))
    silhouette.putalpha(Image.eval(window.getchannel("A"), lambda a: min(90, a)))
    shadow.paste(silhouette, (margin, margin + offset), silhouette)
    canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(blur)))
    canvas.paste(window, (margin, margin), window)

    if logo is not None:
        # On the BACKDROP, clear of the interface. The corner mark painted
        # onto the screenshot itself is what clipped card content in the W1
        # and W2 runs; presentation branding does not have to sit on top of
        # the product to be seen.
        #
        # Sized from the margin band rather than from the image width, so
        # tightening the margin can never push the mark back over a card —
        # which is exactly what happened when the margin went from 9% to 5%.
        pad = max(2, margin // 8)
        mark = max(12, margin - pad)
        placed = logo.resize((mark, mark), Image.LANCZOS)
        x = max(margin + width, canvas.width - mark - pad)
        y = max(margin + height + chrome_h, canvas.height - mark - pad)
        canvas.paste(placed, (x, y), placed)

    return canvas.convert("RGB")


def _crop_regions(size: tuple[int, int]) -> list[tuple[str, tuple[int, int, int, int]]]:
    """Fixed geometric crops, both taken to the RIGHT of the sidebar.

    `detail_1` is the metric band under the header — the KPI row on every
    archetype. `detail_2` is the main content block below it, where the hero
    chart or primary panel sits. Both deliberately exclude the sidebar: a
    "detail" that includes the nav is just a smaller copy of the hero, which
    is exactly how the first rendered deck looked.
    """
    width, height = size
    return [
        ("detail_1", (round(width * 0.15), round(height * 0.05), width, round(height * 0.36))),
        ("detail_2", (round(width * 0.15), round(height * 0.30), round(width * 0.80), round(height * 0.86))),
    ]


def compose_presentation(
    screenshot_bytes: bytes,
    *,
    primary_color: str | None,
    secondary_color: str | None = None,
    logo_path: str | None = None,
    detail_crops: int = 2,
) -> dict[str, bytes]:
    """Returns {"hero": png, "detail_1": png, "detail_2": png} — PNG bytes.

    `screenshot_bytes` should be the UNWATERMARKED screenshot: the logo is
    composited onto the backdrop here instead, so it never covers UI. The
    raw screenshot saved beside these is watermarked separately, which is
    what keeps the "no unbranded bytes under /uploads" policy true for
    every file.
    """
    shot = Image.open(io.BytesIO(screenshot_bytes))
    shot.load()
    palette = derive_palette(primary_color, secondary_color)

    logo = None
    if logo_path and os.path.isfile(logo_path):
        logo = Image.open(logo_path).convert("RGBA")

    out: dict[str, bytes] = {}

    def _encode(image: Image.Image) -> bytes:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    out["hero"] = _encode(_framed(shot, palette, logo))

    for name, box in _crop_regions(shot.size)[: max(0, detail_crops)]:
        crop = shot.convert("RGB").crop(box)
        if crop.width < 40 or crop.height < 40:
            continue
        out[name] = _encode(_framed(crop, palette, logo, chrome=False))

    return out
