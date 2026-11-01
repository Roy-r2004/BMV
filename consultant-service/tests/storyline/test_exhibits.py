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
from app.figures.model import tag_word
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


def _req(**columns) -> Request:
    base = dict(business_name="Halo", business_description="A studio.", email="a@b.c",
                capacity_json=json.dumps(_grid([4, 8, 6])),
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
