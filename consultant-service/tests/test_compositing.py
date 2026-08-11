"""Pins for W4 — deterministic presentation compositing and the deck.

Two failure modes this guards, both of which have actually shipped in this
repo before (dd181b8, d6e8959): an image stretched or cropped to fit a box
it does not fit, and a picture floating in dead space because the box was
the wrong shape. Unit tests cannot tell you a slide is ugly, but they can
tell you the geometry is honest.
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch

from PIL import Image

from app.pipeline import compositing, export_pptx


def _screenshot(width: int = 640, height: int = 360) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "#FFFFFF").save(buf, format="PNG")
    return buf.getvalue()


def _size(png: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(png)) as im:
        return im.size


# ── the compositor ───────────────────────────────────────────────────────

def test_produces_a_hero_and_two_detail_crops():
    out = compositing.compose_presentation(_screenshot(), primary_color="#0e9594")
    assert set(out) == {"hero", "detail_1", "detail_2"}
    assert all(png.startswith(b"\x89PNG") for png in out.values())


def test_the_hero_frames_the_screenshot_rather_than_replacing_it():
    source = _screenshot(640, 360)
    hero_w, hero_h = _size(compositing.compose_presentation(source, primary_color="#0e9594")["hero"])
    assert hero_w > 640 and hero_h > 360, "chrome and backdrop margins must add room"
    # ...but not so much that the screenshot becomes a stamp on a poster.
    assert hero_w < 640 * 1.35 and hero_h < 360 * 1.7


def test_compositing_is_deterministic():
    """No model call, no randomness — the same screenshot must composite to
    the same bytes, or nothing downstream can be compared across runs."""
    source = _screenshot()
    first = compositing.compose_presentation(source, primary_color="#0e9594")
    second = compositing.compose_presentation(source, primary_color="#0e9594")
    assert first == second


def test_detail_crops_get_no_browser_chrome():
    """A title bar on top of a crop taken from the middle of a screen
    claims something untrue about what is being shown."""
    source = _screenshot(1000, 600)
    out = compositing.compose_presentation(source, primary_color="#0e9594")
    margin = round(1000 * compositing._MARGIN_RATIO)

    hero_h = _size(out["hero"])[1]
    assert hero_h > 600 + margin * 2, "the hero's extra height is its chrome bar"

    for name, box in compositing._crop_regions((1000, 600)):
        crop_w, crop_h = box[2] - box[0], box[3] - box[1]
        detail_w, detail_h = _size(out[name])
        assert detail_h == crop_h + round(crop_w * compositing._MARGIN_RATIO) * 2
        assert detail_w == crop_w + round(crop_w * compositing._MARGIN_RATIO) * 2


def test_detail_crops_exclude_the_sidebar():
    """A detail that includes the nav is just a smaller copy of the hero."""
    for _, box in compositing._crop_regions((1000, 600)):
        assert box[0] >= 100, "crops start to the right of the sidebar"


def test_crops_can_be_turned_off():
    out = compositing.compose_presentation(_screenshot(), primary_color="#0e9594", detail_crops=0)
    assert set(out) == {"hero"}


def test_a_missing_logo_file_is_not_an_error():
    out = compositing.compose_presentation(
        _screenshot(), primary_color="#0e9594", logo_path="/nope/logo.png",
    )
    assert "hero" in out


def test_the_logo_goes_on_the_backdrop_not_over_the_interface(tmp_path):
    """The corner mark painted onto the screenshot itself is what clipped
    card content in the W1 and W2 runs. Presentation branding sits on the
    backdrop, where it cannot cover a card."""
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (64, 64), (255, 0, 0, 255)).save(logo)

    source = _screenshot(600, 400)
    without = compositing.compose_presentation(source, primary_color="#0e9594")["hero"]
    with_logo = compositing.compose_presentation(source, primary_color="#0e9594", logo_path=str(logo))["hero"]
    assert with_logo != without

    marked = Image.open(io.BytesIO(with_logo)).convert("RGB")
    margin = round(600 * compositing._MARGIN_RATIO)
    chrome = max(18, round(600 * compositing._CHROME_HEIGHT_RATIO))
    # Every red pixel must sit outside the window's own rectangle.
    for x in range(marked.width):
        for y in range(marked.height):
            if marked.getpixel((x, y))[0] > 200 and marked.getpixel((x, y))[1] < 80:
                inside_window = (
                    margin <= x < margin + 600 and margin <= y < margin + 400 + chrome
                )
                assert not inside_window, f"logo pixel at {(x, y)} covers the interface"


def test_a_tiny_image_does_not_produce_degenerate_crops():
    out = compositing.compose_presentation(_screenshot(60, 40), primary_color="#0e9594")
    assert "hero" in out  # crops below the minimum are skipped, not shipped broken


# ── the deck ─────────────────────────────────────────────────────────────

def test_presentation_variant_finds_the_composite_beside_the_screenshot(tmp_path):
    images = tmp_path / "images" / "7"
    images.mkdir(parents=True)
    (images / "dashboard_0.png").write_bytes(_screenshot())
    (images / "dashboard_hero.png").write_bytes(_screenshot())

    with patch.object(export_pptx.settings, "UPLOADS_DIR", str(tmp_path)):
        hero = export_pptx._presentation_variant("/uploads/images/7/dashboard_0.png", "hero")
        missing = export_pptx._presentation_variant("/uploads/images/7/dashboard_0.png", "detail_2")

    assert hero and hero.endswith("dashboard_hero.png")
    assert missing is None, "a deck must fall back to the screenshot, not lose the slide"


def test_contain_preserves_aspect_ratio_and_centers(tmp_path):
    """The distortion bug this repo has shipped twice: an image forced to
    both dimensions of a box it does not match."""
    path = tmp_path / "wide.png"
    Image.new("RGB", (1000, 500), "#FFFFFF").save(path)

    placed: dict = {}

    class _Shapes:
        def add_picture(self, img, left, top, width=None, height=None):
            placed.update(left=left, top=top, width=width, height=height)
            return object()

    class _Slide:
        shapes = _Shapes()

    export_pptx._place_image_contain(_Slide(), str(path), 0, 0, 600, 600)

    assert placed["width"] / placed["height"] == 2.0
    assert placed["width"] <= 600 and placed["height"] <= 600
    assert placed["top"] > 0 and placed["left"] == 0, "centered on the constrained axis"
