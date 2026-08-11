"""Pins for the floating-backdrop crop (JOB 2, session 34).

The prompt forbids the interface-as-a-card-on-a-backdrop in two places and
the model drew it anyway on 5 of 15 session-33 screens; session 32 "fixed"
it twice at the prompt layer. The fix is deterministic PIL instead — and
because a false positive here crops REAL UI out of a customer's screenshot,
the pins run in both directions:

  - a full-bleed screenshot comes through BYTE-IDENTICAL, including the
    hard case: a full-bleed screen whose content sits inside generous
    padding on its own surface;
  - a floating one loses its margin, including the case where a card hangs
    outside the app's own edge.

Validated against the real session-33 set (validate_backdrop_crop.py in
docs/evidence/session34/): fires on all three salon screens (the pink-
backdrop run), refuses the other fifteen — including the two tone-on-tone
retail floats, where the contrast box lands inside the card and a crop
would shave card padding (the ring-vs-inner guard is what refuses), and
hedgefund's clipped-cards screen, where content touches the canvas edge so
no backdrop ring exists. Those three stay defects for the JOB 3 checker;
this module only ever fixes the ones it can fix losslessly.
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch

from PIL import Image, ImageDraw

from app.config import settings
from app.pipeline import images as images_mod

W, H = 1376, 768
CARD_BOX = (80, 50, 1296, 718)  # left, top, right, bottom
PINK = (231, 180, 172)
CARD = (26, 18, 24)


def _png(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _texture(draw: ImageDraw.ImageDraw, box, step=24, color=(240, 236, 232)):
    """Hairlines and text-like ticks — the local contrast a real UI has."""
    left, top, right, bottom = box
    for x in range(left, right, step):
        draw.line([(x, top), (x, bottom)], fill=color, width=1)
    for y in range(top, bottom, step):
        draw.line([(left, y), (right, y)], fill=color, width=1)


def _gradient_backdrop() -> Image.Image:
    """A smooth vertical gradient — the session-33 salon backdrop was a
    gradient, and a detector that only handles flat color would have
    missed the only three screens it exists for."""
    ramp = Image.linear_gradient("L").resize((W, H))
    top, bottom = PINK, (204, 140, 150)
    return Image.merge("RGB", [
        ramp.point(lambda p, a=a, b=b: round(a + (b - a) * p / 255))
        for a, b in zip(top, bottom)
    ])


def _floating() -> bytes:
    im = _gradient_backdrop()
    draw = ImageDraw.Draw(im)
    draw.rectangle(CARD_BOX, fill=CARD)
    _texture(draw, (CARD_BOX[0] + 24, CARD_BOX[1] + 24, CARD_BOX[2] - 24, CARD_BOX[3] - 24))
    return _png(im)


def _full_bleed() -> bytes:
    im = Image.new("RGB", (W, H), CARD)
    _texture(ImageDraw.Draw(im), (0, 0, W, H))
    return _png(im)


def _full_bleed_with_padding() -> bytes:
    """Content inset 60px into its OWN surface, which runs to every edge.
    The cinematic register does exactly this, and cropping its padding
    would be the false positive this module must never produce."""
    im = Image.new("RGB", (W, H), CARD)
    _texture(ImageDraw.Draw(im), (60, 60, W - 60, H - 60))
    return _png(im)


# ── full-bleed comes through untouched, bit for bit ──────────────────────

def test_full_bleed_is_byte_identical():
    data = _full_bleed()
    assert images_mod._crop_floating_backdrop(data) is data


def test_full_bleed_with_interior_padding_is_byte_identical():
    data = _full_bleed_with_padding()
    assert images_mod._crop_floating_backdrop(data) is data


def test_content_touching_one_edge_is_byte_identical():
    """A card cut off by the canvas (hedgefund analytics_overview) has no
    backdrop ring — cropping cannot fix it and must not try."""
    im = _gradient_backdrop()
    draw = ImageDraw.Draw(im)
    draw.rectangle((0, 50, 1296, 718), fill=CARD)  # reaches the left edge
    _texture(draw, (24, 74, 1272, 694))
    data = _png(im)
    assert images_mod._crop_floating_backdrop(data) is data


def test_a_high_sitting_content_box_is_layout_not_backdrop():
    """The session-33 law screens: content 18px from the top (the nav bar
    hugs it) and ~60px from the bottom, on the app's own ground. Even with
    a color step present, lopsided margins mean layout — a floating card
    is drawn centered. This exact shape false-positived twice while the
    detector was being built."""
    im = _gradient_backdrop()
    draw = ImageDraw.Draw(im)
    draw.rectangle((80, 14, 1296, 707), fill=CARD)  # 14 top vs 61 bottom
    _texture(draw, (104, 38, 1272, 683))
    data = _png(im)
    assert images_mod._crop_floating_backdrop(data) is data


def test_a_small_panel_on_a_poster_is_not_cropped_to():
    """Interior must fill most of the frame — this is a screenshot
    pipeline, not a thumbnail extractor."""
    im = _gradient_backdrop()
    draw = ImageDraw.Draw(im)
    draw.rectangle((488, 234, 888, 534), fill=CARD)
    _texture(draw, (512, 258, 864, 510))
    data = _png(im)
    assert images_mod._crop_floating_backdrop(data) is data


def test_the_kill_switch_is_one_env_var():
    data = _floating()
    with patch.object(settings, "ENABLE_BACKDROP_CROP", False):
        assert images_mod._crop_floating_backdrop(data) is data


# ── floating loses its margin ────────────────────────────────────────────

def test_floating_card_is_cropped_to_the_card():
    cropped = Image.open(io.BytesIO(images_mod._crop_floating_backdrop(_floating())))
    card_w = CARD_BOX[2] - CARD_BOX[0]
    card_h = CARD_BOX[3] - CARD_BOX[1]
    assert abs(cropped.width - card_w) <= 10 and abs(cropped.height - card_h) <= 10
    # and none of the backdrop survives: every remaining pixel is card-dark,
    # not backdrop-pink
    extrema = cropped.convert("RGB").getextrema()
    assert extrema[0][1] < 250 and extrema[1][0] < PINK[1] - 20


def test_a_card_hanging_outside_the_frame_is_kept():
    """Session 33's hedgefund screens drew cards hanging off the app's own
    edge. The brief: cropping to the bounding box of card PLUS hanger is
    still right — the hanger must not be amputated."""
    im = _gradient_backdrop()
    draw = ImageDraw.Draw(im)
    draw.rectangle((80, 50, 1200, 718), fill=CARD)
    _texture(draw, (104, 74, 1176, 694))
    draw.rectangle((1240, 200, 1340, 400), fill=CARD)  # hangs beyond the card
    _texture(draw, (1248, 208, 1332, 392), step=12)
    cropped = Image.open(io.BytesIO(images_mod._crop_floating_backdrop(_png(im))))
    assert cropped.width >= 1340 - 80 - 6, "the hanging card was amputated"


def test_junk_bytes_fail_safe_to_the_original():
    data = b"not a png"
    assert images_mod._crop_floating_backdrop(data) is data


# ── the pipeline applies it before the judge looks ───────────────────────

def test_candidates_are_cropped_before_qa_sees_them(dental_spec):
    floating = _floating()
    qa_saw = []

    def fake_review(db, request_id, image_bytes, spec):
        qa_saw.append(Image.open(io.BytesIO(image_bytes)).size)
        return {"score": 9.0, "issues": [], "approved": True}

    class _Db:
        def add(self, *_): ...
        def commit(self): ...

    with patch.object(images_mod.provider, "generate_image", return_value={"image_bytes": floating, "usage": None}), \
         patch.object(images_mod.qa, "review_image", side_effect=fake_review), \
         patch.object(images_mod, "log_usage"):
        selected, _ = images_mod._render_screen(
            _Db(), 1, dental_spec, [{"prompt": "p", "variant_id": None, "model": "m"}],
            "v", reference_images=None,
        )

    assert qa_saw and qa_saw[0][0] < W, "QA scored the uncropped image"
    assert Image.open(io.BytesIO(selected["image_bytes"])).size == qa_saw[0]
