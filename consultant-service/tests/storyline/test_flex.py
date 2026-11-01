"""The headline move, flexed. Only a number we proposed moves; the client's
figures and the calendar constants stay exact, and a range is never upside down.

The arithmetic is exact (`Decimal`). A move stored before it kept its terms has
no range: the caller is told, and nothing is invented in its place.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest
from decimal import Decimal

from app.figures.calc import decimal_of
from app.figures.model import FigureSet
from app.pipeline import answer
from app.storyline.flex import NoTerms, flexed, note


def _settings(*pairs: tuple[str, str]) -> list[str]:
    """The storyline bounds as a fresh interpreter reads them from the environment."""
    env = dict(os.environ, **dict(pairs))
    out = subprocess.run(
        [sys.executable, "-c",
         "from app.config import settings as s; "
         "print(s.VALUE_FLEX_PCT, s.REGISTER_ROWS_MIN, s.REGISTER_ROWS_MAX, "
         "s.STORYLINE_SECTIONS_MAX, s.EXHIBIT_ROWS_MAX)"],
        env=env, capture_output=True, text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        timeout=60)
    assert out.returncode == 0
    return out.stdout.split()


def test_config_bounds_clamp_and_min_never_exceeds_max(caplog):
    from app import config

    high = _settings(("VALUE_FLEX_PCT", "99"))
    low = _settings(("VALUE_FLEX_PCT", "1"))
    assert high[0] == "50" and low[0] == "5"
    # a shortest register above the longest is moved down to it
    with caplog.at_level("WARNING", logger="consultant.config"):
        assert config._at_most("REGISTER_ROWS_MIN", 9, "REGISTER_ROWS_MAX", 3) == 3
    assert "REGISTER_ROWS_MIN=9 is above REGISTER_ROWS_MAX=3" in caplog.text
    rows = _settings(("REGISTER_ROWS_MIN", "9"), ("REGISTER_ROWS_MAX", "3"))
    assert int(rows[1]) <= int(rows[2])
    sections = _settings(("STORYLINE_SECTIONS_MAX", "99"), ("EXHIBIT_ROWS_MAX", "1"))
    assert sections[3] == "12" and sections[4] == "4"


def test_flexed_scales_only_our_terms():
    terms = [
        {"kind": "claim", "id": "CF-04", "value": "22", "sign": 1, "label": "her price"},
        {"kind": "constant", "value": "5", "sign": 1, "label": "days"},
        {"kind": "proposed", "value": "0.75", "sign": 1, "label": "who stay"},
    ]
    low, mid, high = flexed(terms, 20)
    assert mid == Decimal("22") * Decimal("5") * Decimal("0.75")
    assert low == Decimal("22") * Decimal("5") * Decimal("0.6")
    assert high == Decimal("22") * Decimal("5") * Decimal("0.9")
    assert note(terms, 20) == "Flexes our assumption of 75% by 20% either way."


def test_flexed_with_no_proposed_term_collapses():
    terms = [
        {"kind": "claim", "id": "CF-04", "value": "22", "sign": 1, "label": "her price"},
        {"kind": "constant", "value": "52", "sign": 1, "label": "weeks a year"},
    ]
    low, mid, high = flexed(terms, 20)
    assert low == mid == high == Decimal("22") * Decimal("52")
    assert note(terms, 20) is None


def test_flexed_keeps_low_below_high_with_a_subtracted_term():
    """A number we propose that is taken away: flexing it up makes the result
    smaller, and the low end is still the low end."""
    terms = [{
        "sign": 1, "label": "price after the change",
        "parts": [
            {"kind": "claim", "id": "CF-04", "value": "100", "sign": 1, "label": "her price"},
            {"kind": "proposed", "value": "40", "sign": -1, "label": "taken off"},
        ],
    }]
    low, mid, high = flexed(terms, 20)
    assert mid == Decimal("60")
    assert low == Decimal("52") and high == Decimal("68")
    assert low < mid < high


CLAIMS = [
    {"id": "CF-01", "value": 10, "unit": "class", "text": "10 classes", "provenance": "client_input"},
    {"id": "CF-04", "value": 22, "unit": "USD", "text": "$22 a class", "provenance": "client_input"},
]
MOVE = {"label": "the prize", "unit": "USD", "period": "year",
        "terms": [{"label": "classes", "value": 10, "from": "CF-01"},
                  {"label": "price rise",
                   "parts": [{"value": 28, "from": "proposed", "label": "proposed evening price"},
                             {"value": 22, "from": "CF-04", "sign": -1}]},
                  {"label": "weeks a year", "value": 52, "from": "constant"}]}


def test_move_stores_its_terms():
    move = answer.compute_move(MOVE, CLAIMS)
    low, mid, high = flexed(move["terms"], 0)
    assert mid == decimal_of(move["value"])
    assert low == high == mid
    # the proposed price is still its own term, so only it moves
    widened, same, _ = flexed(move["terms"], 20)
    assert same == mid and widened < mid
    got, _ = answer.shape({"headline": "You are full.", "move": MOVE}, CLAIMS, FigureSet())
    assert flexed(got["move"]["terms"], 0)[1] == decimal_of(got["move"]["value"])


def test_a_move_without_terms_has_no_range():
    with pytest.raises(NoTerms):
        flexed(None, 20)
