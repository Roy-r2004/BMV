"""Pins for the deck's PROPORTIONS — the class of defect this artifact keeps
producing and no test has ever caught.

The pptx has a documented history of distortion and overlap bugs (dd181b8,
d6e8959), and the reason they shipped is that "the picture is squashed" and
"the box is four times taller than its text" are things you see rather than
things that raise. These tests do not replace looking at it — session 33
rebuilt the deck, exported all seven slides through Keynote and read them —
but they hold the two specific proportions that looking found wrong, so the
next regression is a red test rather than a slide.

Deliberately NOT pinned here: anything about how the deck looks that a
number cannot express. That still requires
`python scripts/deck_sample.py` and a pair of eyes.
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from PIL import Image
from pptx.util import Inches

from app.config import settings
from app.pipeline import export_pptx


class _Row:
    def __init__(self, role_id, role_label, file_path):
        self.role_id, self.role_label, self.variant, self.file_path = role_id, role_label, 0, file_path


class _Req:
    business_name = "Northgate Coffee Roasters"
    business_description = "A coffee roastery."
    industry = "Coffee Roastery"


def _png(path, size):
    Image.new("RGB", size, "white").save(path, format="PNG")


@pytest.fixture
def run_dir(tmp_path, monkeypatch):
    """A screen with its two W4 composites, at the aspect ratios the
    compositor really produces: a wide thin top band and a squarer content
    block."""
    images = tmp_path / "images" / "1"
    images.mkdir(parents=True)
    _png(images / "analytics_0.png", (1408, 814))
    _png(images / "analytics_hero.png", (1548, 957))
    _png(images / "analytics_detail_1.png", (1317, 358))   # 3.68:1
    _png(images / "analytics_detail_2.png", (1007, 522))   # 1.93:1
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path))
    return tmp_path


def _build(employees):
    return export_pptx.build_presentation(
        _Req(),
        {"pain_points": ["a", "b"], "growth_opportunity": "c"},
        {"consulting_summary": "s", "recommended_features": ["f"], "recommended_ai_employees": employees},
        {"concept_name": "Northgate Roast Intelligence", "roles": [], "visual_theme": {"primary_color": "#7c3f21"}},
        [_Row("analytics", "Analytics", "/uploads/images/1/analytics_0.png")],
    )


def _pictures(slide):
    return [s for s in slide.shapes if s.shape_type == 13]  # MSO_SHAPE_TYPE.PICTURE


def _employee_cards(slide):
    """The rounded cards, not the full-width accent bar — both are autoshapes."""
    return [s for s in slide.shapes if s.name.startswith("Rounded Rectangle")]


def test_a_detail_crop_is_given_the_height_its_shape_needs(run_dir):
    """The slots were a fixed 2.45" tall. A detail crop is a wide, thin band,
    so at 3.5" wide it rendered under an inch and left 1.5" of its slot
    empty — twice per slide, in a column labelled IN DETAIL containing two
    thumbnails too small to show any detail."""
    prs = _build([{"title": "AI Ops", "why": "short"}])
    screen_slide = prs.slides[1]
    details = sorted(_pictures(screen_slide), key=lambda p: p.top)[1:]
    assert len(details) == 2

    for picture, source_aspect in zip(details, (1317 / 358, 1007 / 522)):
        assert picture.width == pytest.approx(Inches(3.5), rel=0.02)
        assert picture.height == pytest.approx(picture.width / source_aspect, rel=0.02), (
            "the placed crop does not have its own aspect ratio"
        )


def test_the_detail_column_is_not_mostly_empty(run_dir):
    """The measure that actually failed: how much of the column the crops
    use. Two 2.45" slots holding 0.95" and 1.81" of image is 44% used."""
    prs = _build([{"title": "AI Ops", "why": "short"}])
    details = sorted(_pictures(prs.slides[1]), key=lambda p: p.top)[1:]

    span = max(p.top + p.height for p in details) - min(p.top for p in details)
    used = sum(p.height for p in details)
    assert used / span > 0.85, "the crops are stacked with more gap than image"


def test_the_hero_is_still_the_dominant_image_on_the_slide(run_dir):
    """Fixing the crops must not turn the detail column into the subject."""
    pictures = sorted(
        _pictures(_build([{"title": "A", "why": "b"}]).slides[1]),
        key=lambda p: p.width * p.height, reverse=True,
    )
    hero, *details = pictures
    assert all(hero.width * hero.height > 3 * d.width * d.height for d in details)


def test_a_closing_card_is_sized_from_its_own_text(run_dir):
    """Fixed at 2.9", two employees with one-line reasons produced two boxes
    four times taller than their content — which reads as content that
    failed to load."""
    short = _build([{"title": "AI Ops", "why": "Short."}])
    long = _build([{"title": "AI Ops", "why": "A much longer sentence about what this employee does all day, " * 3}])

    def _card_height(prs):
        closing = prs.slides[len(prs.slides._sldIdLst) - 1]
        cards = _employee_cards(closing)
        assert cards, "the closing slide has no employee cards"
        return cards[0].height

    assert _card_height(long) > _card_height(short)
    assert _card_height(short) < Inches(2.0), "a one-line reason does not need a two-inch box"


def test_the_card_never_grows_without_bound(run_dir):
    """A pathological `why` must not push the card off the slide."""
    prs = _build([{"title": "AI Ops", "why": "x" * 4000}])
    closing = prs.slides[len(prs.slides._sldIdLst) - 1]
    cards = _employee_cards(closing)
    assert cards[0].top + cards[0].height < export_pptx.SLIDE_H
