"""Exhibits are drawn from figures. The model never chooses a chart or a number.

A section with nothing to draw has no exhibit. Rows past the bound are grouped,
and the group is a figure whose value is their exact sum.
"""
from __future__ import annotations

import json
from decimal import Decimal

import pytest

from app.config import settings
from app.figures import known as K
from app.figures.bind import bind
from app.figures.model import Figure, TheirsSource, as_json, tag_word
from app.models import Request
from app.storyline.exhibits import draw_pdf, for_section

TERMS = [
    {"kind": "claim", "id": "CF-01", "value": "10", "sign": 1, "label": "classes"},
    {"kind": "proposed", "value": "6", "sign": 1, "label": "the rise"},
    {"kind": "constant", "value": "52", "sign": 1, "label": "weeks a year"},
]


def _grid(taken: list[int]) -> dict:
    return {"shape": "weekly_grid", "unit": "spot", "unit_plural": "spots",
            "grid": [{"day": "Day 1", "slots": [
                {"time": f"{9 + i:02d}:00", "taken": n, "capacity": 12} for i, n in enumerate(taken)]}]}


CLASSES = Figure("CF-01", Decimal("10"), "classes", None, "theirs",
                 TheirsSource(1, "classes", "We run ten classes.", None, None), 0)

#: A stored storyline whose proof draws every exhibit: an exhibit's figures
#: join the known set only when a section draws it.
DRAWN = json.dumps({"register": [], "sections": [
    {"id": sid, "title": sid, "takeaway": ""} for sid in ("week", "prize", "grid", "plan", "scoreboard")]})


def _req(**columns) -> Request:
    base = dict(business_name="Halo", business_description="A studio.", email="a@b.c",
                capacity_json=json.dumps(_grid([4, 8, 6])),
                case_file_json=json.dumps([as_json(CLASSES)]),
                storyline_json=DRAWN,
                answer_json=json.dumps({"headline": "You are full.",
                                        "move": {"value": 3120, "unit": "USD", "period": "year",
                                                 "terms": TERMS}}))
    base.update(columns)
    return Request(**base)


def test_bar_labels_are_figures_with_their_tags():
    exhibit = for_section(_req(), "week")
    known = K.known_for(_req())
    assert exhibit is not None and exhibit.kind == "bar"
    assert exhibit.data["rows"]
    for row in exhibit.data["rows"]:
        figure = known.get(row["figure_id"])
        assert figure is not None
        assert row["tag"] == tag_word(figure.kind)
        assert row["display"]


def test_waterfall_steps_sum_to_the_headline():
    exhibit = for_section(_req(), "prize")
    amounts = [Decimal(step["amount"]) for step in exhibit.data["steps"]]
    assert sum(amounts, Decimal(0)) == Decimal(3120)
    ours = [step for step in exhibit.data["steps"] if step["tag"] == "our estimate"]
    assert ours


def test_rows_over_the_bound_are_grouped_and_the_group_sum_is_exact(monkeypatch):
    monkeypatch.setattr(settings, "EXHIBIT_ROWS_MAX", 3)
    taken = [4, 5, 6, 7, 8]
    exhibit = for_section(_req(capacity_json=json.dumps(_grid(taken))), "week")
    labels = [row["label"] for row in exhibit.data["rows"]]
    assert labels[-1] == "Other classes (3)"
    assert len(exhibit.data["rows"]) == 3
    known = K.known_for(_req(capacity_json=json.dumps(_grid(taken))))
    group = known.get(exhibit.data["rows"][-1]["figure_id"])
    assert group.value == Decimal(6 + 7 + 8)


def test_no_data_gives_no_exhibit_not_an_empty_chart():
    empty = _req(capacity_json=None, answer_json=json.dumps({"headline": "You are full."}))
    assert for_section(empty, "week") is None
    assert for_section(empty, "prize") is None
    assert for_section(_req(), "scoreboard") is None


def test_drawing_fits_its_box_at_min_and_max_rows(monkeypatch):
    monkeypatch.setattr(settings, "EXHIBIT_ROWS_MAX", 4)
    small = draw_pdf(for_section(_req(capacity_json=json.dumps(_grid([4]))), "week"), 360, 200)
    wide = draw_pdf(for_section(_req(capacity_json=json.dumps(_grid([4, 5, 6, 7]))), "week"), 360, 280)
    for drawing, width, height in ((small, 360, 200), (wide, 360, 280)):
        for shape in _shapes(drawing):
            assert 0 <= shape["x"] and shape["x"] + shape["w"] <= width + 0.5
            assert 0 <= shape["y"] and shape["y"] + shape["h"] <= height + 0.5


def test_every_drawn_string_passes_the_number_law(monkeypatch):
    monkeypatch.setattr(settings, "EXHIBIT_ROWS_MAX", 3)
    req = _req(capacity_json=json.dumps(_grid([4, 5, 6, 7, 8])))
    known = K.known_for(req)
    for section in ("week", "prize"):
        drawing = draw_pdf(for_section(req, section), 400, 280)
        for text in _strings(drawing):
            if any(ch.isdigit() for ch in text):
                bound = bind(text, known)
                assert bound.unresolved == [], (text, [item.text for item in bound.unresolved])


SPOTS = Figure("CF-09", Decimal("12"), "spots", None, "theirs",
               TheirsSource(1, "empty", "Twelve spots go empty.", None, None), 0)
PRICE = Figure("CF-04", Decimal("22"), "USD", None, "theirs",
               TheirsSource(2, "price", "We charge twenty-two a class.", None, None), 0)


def _prize_req(terms, value, **columns) -> Request:
    return _req(case_file_json=json.dumps([as_json(SPOTS), as_json(PRICE)]),
                answer_json=json.dumps({"headline": "x", "move": {"value": value, "unit": "USD",
                                                                  "period": "week", "terms": terms}}),
                **columns)


def test_a_waterfall_step_keeps_its_unit_and_is_tagged_as_what_it_is():
    # Review C3: 12 empty spots printed as "$12", and 12 x $22 was tagged "yours".
    terms = [
        {"kind": "claim", "id": "CF-09", "value": "12", "sign": 1, "label": "empty spots a week"},
        {"kind": "claim", "id": "CF-04", "value": "22", "sign": 1, "label": "her price"},
        {"kind": "proposed", "value": "0.75", "sign": 1, "label": "who stay"},
    ]
    req = _prize_req(terms, 198)
    rows = for_section(req, "prize").data["rows"]
    known = K.known_for(req)
    assert rows[0]["figure_id"] == "CF-09" and rows[0]["tag"] == "yours"
    assert not rows[0]["display"].startswith("$")
    second = known.get(rows[1]["figure_id"])
    assert second.kind == "derived" and second.unit == "USD" and second.value == Decimal(264)
    assert rows[1]["tag"] == "worked out"
    assert rows[2]["tag"] == "our estimate"
    assert all(f.kind != "theirs" for f in known if f.id.startswith("EX-"))


def test_an_exhibit_no_section_draws_vouches_for_nothing():
    # Review C3: EX-PRIZE-2 = $484 "theirs" joined every run's known set, so an
    # invented "$484" passed the law as the client's own figure.
    terms = [
        {"kind": "claim", "id": "CF-04", "value": "22", "sign": 1, "label": "her price"},
        {"kind": "claim", "id": "CF-04", "value": "22", "sign": 1, "label": "her price again"},
        {"kind": "proposed", "value": "0.75", "sign": 1, "label": "who stay"},
    ]
    text = "Her studio already makes $484 a week."
    undrawn = _prize_req(terms, 363, storyline_json=None)
    assert not [f for f in K.known_for(undrawn) if f.id.startswith("EX-")]
    assert [u.text for u in bind(text, K.known_for(undrawn)).unresolved] == ["$484"]
    drawn = _prize_req(terms, 363)
    step = K.known_for(drawn).get("EX-PRIZE-2")
    assert step.kind == "derived" and not isinstance(step.source, TheirsSource)


def test_a_step_whose_unit_cannot_be_said_has_no_figure():
    terms = [
        {"kind": "constant", "value": "5", "sign": 1, "label": "days"},
        {"kind": "claim", "id": "CF-04", "value": "22", "sign": 1, "label": "her price"},
    ]
    rows = for_section(_prize_req(terms, 110), "prize").data["rows"]
    assert rows[0]["figure_id"] == "" and rows[0]["display"] == ""
    assert rows[1]["display"]


def _shapes(drawing) -> list[dict]:
    found = []

    def walk(node):
        contents = getattr(node, "contents", None)
        if contents:
            for child in contents:
                walk(child)
            return
        x = float(getattr(node, "x", 0) or 0)
        y = float(getattr(node, "y", 0) or 0)
        width = float(getattr(node, "width", 0) or 0)
        height = float(getattr(node, "height", 0) or 0)
        text = getattr(node, "text", None)
        if isinstance(text, str):
            from reportlab.pdfbase.pdfmetrics import stringWidth
            size = float(getattr(node, "fontSize", 8) or 8)
            width = stringWidth(text, getattr(node, "fontName", "Helvetica"), size)
            height = size
        found.append({"x": x, "y": y, "w": width, "h": height})

    walk(drawing)
    return found


def _strings(drawing) -> list[str]:
    found = []

    def walk(node):
        text = getattr(node, "text", None)
        if isinstance(text, str):
            found.append(text)
        for child in getattr(node, "contents", None) or []:
            walk(child)

    walk(drawing)
    return found
