"""The register is checked in code. Shares are whole numbers that add to 100,
each row's range is that share of the headline, and a cost is a figure we
have or a named gap. Nothing is priced by the model.
"""
from __future__ import annotations

import json
from decimal import Decimal

import pytest

from app.config import settings
from app.figures import known as K
from app.figures.bind import bind
from app.figures.model import Figure, TheirsSource, as_json
from app.models import Request
from app.storyline.flex import flexed
from app.storyline.register import RegisterInvalid, assemble, displays, extra_figures

TERMS = [
    {"kind": "claim", "id": "CF-04", "value": "22", "sign": 1, "label": "her price"},
    {"kind": "constant", "value": "5", "sign": 1, "label": "days"},
    {"kind": "proposed", "value": "0.75", "sign": 1, "label": "who stay"},
]
THEIRS = Figure("CF-04", Decimal("22"), "USD", None, "theirs",
                TheirsSource(1, "price", "We charge $22 a class.", None, None), 0)


def _req(**columns) -> Request:
    phases = [{"when": "Week 1", "do": "Tell them.", "you": "You send it."},
              {"when": "Weeks 2 to 6", "do": "Watch.", "you": "You look."}]
    answer = {"headline": "You are full.", "move": {"value": 82.5, "unit": "USD", "period": "year",
                                                     "terms": TERMS, "display": "the prize"}}
    base = dict(
        business_name="Halo", business_description="A studio.", email="a@b.c",
        case_file_json=json.dumps([as_json(THEIRS)]),
        action_plan_json=json.dumps({"phases": phases}),
        answer_json=json.dumps(answer),
    )
    base.update(columns)
    return Request(**base)


def _row(n, share, **over) -> dict:
    row = {"phase": 1 if n == 1 else 2, "recommendation": f"Do the {n} thing.",
           "changes": "The evening class.", "owner": "the owner", "depends_on": [],
           "share_pct": share, "cost_figure": "CF-04", "cost_needs": None}
    row.update(over)
    return row


def _drafted(shares=(60, 40)) -> list[dict]:
    rows = []
    for n, share in enumerate(shares, 1):
        rows.append(_row(n, share, depends_on=[1] if n > 1 else []))
    return rows


def test_shares_must_sum_to_one_hundred():
    for shares, total in (((50, 49), 99), ((50, 51), 101)):
        with pytest.raises(RegisterInvalid) as caught:
            assemble(_req(), _drafted(shares))
        assert any(str(total) in reason for reason in caught.value.reasons)


def test_row_ranges_add_up_to_the_headline_exactly():
    reg = assemble(_req(), _drafted())
    low, mid, high = flexed(TERMS, settings.VALUE_FLEX_PCT)
    assert sum((row.value.low for row in reg.rows), Decimal(0)) == low
    assert sum((row.value.mid for row in reg.rows), Decimal(0)) == mid
    assert sum((row.value.high for row in reg.rows), Decimal(0)) == high
    assert reg.rows[0].value.mid == mid * Decimal(60) / Decimal(100)
    assert reg.rows[0].when == "Week 1" and reg.rows[1].when == "Weeks 2 to 6"
    assert "Shares are our estimate of where the gain comes from." in reg.footnotes
    assert any("75%" in note for note in reg.footnotes)


def test_a_missing_move_leaves_values_empty_and_says_why():
    bare = _req(answer_json=json.dumps({"headline": "You are full."}))
    reg = assemble(bare, _drafted())
    assert all(row.value is None for row in reg.rows) and reg.total is None
    assert "There is no range to show, because this answer has no value to share out." in reg.footnotes
    legacy = _req(answer_json=json.dumps({"headline": "You are full.", "move": {"value": 100}}))
    old = assemble(legacy, _drafted())
    assert all(row.value is None for row in old.rows)
    assert any("workings" in note for note in old.footnotes)


def test_cost_is_a_known_figure_or_a_named_gap():
    rows = [_row(1, 60, cost_figure="NO-SUCH", cost_needs=None),
            _row(2, 40, cost_figure=None, cost_needs="the evening wage", depends_on=[1])]
    with pytest.raises(RegisterInvalid) as caught:
        assemble(_req(), rows)
    assert caught.value.reasons
    priced = [_row(1, 60), _row(2, 40, cost_figure=None, cost_needs="the evening wage", depends_on=[1])]
    reg = assemble(_req(), priced)
    assert reg.rows[0].cost.figure_id == "CF-04" and reg.rows[0].cost.needs is None
    assert reg.rows[1].cost.figure_id is None and reg.rows[1].cost.needs == "the evening wage"
    assert any("the evening wage" in note for note in reg.footnotes)


def test_dependency_on_a_later_row_is_rejected():
    rows = [_row(1, 60, depends_on=[2]), _row(2, 40, depends_on=[])]
    with pytest.raises(RegisterInvalid):
        assemble(_req(), rows)
    ok = assemble(_req(), [_row(1, 60, depends_on=[]), _row(2, 40, depends_on=[1])])
    assert ok.rows[1].depends_on == (1,)


def test_row_count_outside_the_bounds_is_rejected_with_both_bounds_named(monkeypatch):
    monkeypatch.setattr(settings, "REGISTER_ROWS_MIN", 2)
    monkeypatch.setattr(settings, "REGISTER_ROWS_MAX", 8)
    for count in (1, 9):
        shares = [100] if count == 1 else [12] + [11] * 8
        with pytest.raises(RegisterInvalid) as caught:
            assemble(_req(), [_row(n, share, phase=1, depends_on=[]) for n, share in enumerate(shares, 1)])
        text = " ".join(caught.value.reasons)
        assert "2" in text and "8" in text


def test_the_register_numbers_pass_the_number_law():
    req = _req()
    drafted = _drafted()
    reg = assemble(req, drafted)
    extra = extra_figures(reg)
    assert extra and {f.kind for f in extra} == {"ours"}
    known = K.with_extra(K.known_for(req, leave_out={"register"}), extra)
    for line in displays(reg):
        bound = bind(line, known)
        assert bound.unresolved == [], (line, [u.text for u in bound.unresolved])
    req.storyline_json = json.dumps({"register": drafted})
    held = {f.id for f in K.known_for(req)}
    assert {f.id for f in extra} <= held
