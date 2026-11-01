"""Exact derived arithmetic (Step 2, Task 4).

`derive` turns Figures into a new Figure by one of four operations (product,
total, difference, ratio), in Decimal, and keeps the working. These tests pin
the arithmetic (12 x 6 x 6 is 432, and 0.07 x 100 is 7 and not
7.000000000000001), the kind rule (ours in, ours out), the refusals in plain
words, and that the result is the same number the engine's DecimalCalculator
gives wherever the engine accepts the operation.

The engine is imported inside the differential tests only: the figures package
must not load it at import time (the engine imports the pipeline, and the
pipeline will import this package).
"""
from __future__ import annotations

import ast
import os
import re
from decimal import Decimal

import pytest

from app.figures import calc
from app.figures.calc import decimal_of, derive, places_of, round_half_up, unit_key
from app.figures.model import (
    Figure, Proposal, Reference, TheirsSource, Working, as_json, decimal_from_float, display, displayed_value,
    from_claim, from_json,
)

D = Decimal
TIMES, MINUS, DIVIDE = "×", "−", "÷"
CALC_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       "app", "figures", "calc.py")


# -- builders ---------------------------------------------------------------

def theirs(id_, value, unit="", period=None, precision=0):
    return Figure(id_, D(value), unit, period, "theirs",
                  TheirsSource(turn=1, field=None, quote="as they said it", file=None, cell=None), precision)


def worked(id_, value, unit="", period=None, precision=0):
    return Figure(id_, D(value), unit, period, "derived",
                  Working(inputs=(), op="product", text="from their figures"), precision)


def ours(id_, value, unit="", period=None, precision=0):
    return Figure(id_, D(value), unit, period, "ours", Proposal(note="what we propose"), precision)


def cited(id_, value, unit="", precision=1):
    return Figure(id_, D(value), unit, "year", "reference",
                  Reference(publication="Industry survey", year=2024, population="studios", url="https://example.org"),
                  precision)


# -- the arithmetic -----------------------------------------------------------

def test_twelve_times_six_times_six_is_432_exactly_and_the_working_is_kept():
    f = derive("product", [theirs("A", "12", "reformers"), theirs("B", "6", "classes a day"),
                           theirs("C", "6", "days a week")], id="CAP-01", unit="spots", period="week")
    assert f.value == D(432) and str(f.value) == "432" and isinstance(f.value, Decimal)
    assert (f.id, f.unit, f.period, f.kind) == ("CAP-01", "spots", "week", "derived")
    assert isinstance(f.source, Working)
    assert (f.source.inputs, f.source.op) == (("A", "B", "C"), "product")
    assert f.source.text == f"12 reformers {TIMES} 6 classes a day {TIMES} 6 days a week = 432 spots a week"


def test_the_working_reads_like_the_move_in_the_brief():
    f = derive("product", [theirs("P", "6", "USD"), theirs("N", "144")], id="M-1", unit="USD", period="week")
    assert f.value == D(864)
    assert f.source.text == f"$6 {TIMES} 144 = $864 a week"
    assert display(f) == "$864"


def test_factors_are_calendar_constants_and_appear_in_the_working():
    f = derive("product", [theirs("W", "864", "USD", period="week")], id="M-2", unit="USD", period="year",
               factors=[(D(52), "weeks a year")])
    assert f.value == D(44928)
    assert f.source.text == f"$864 {TIMES} 52 weeks a year = $44,928 a year"
    assert f.source.inputs == ("W",)          # a constant is not a figure, so it is not an input
    g = derive("product", [theirs("A", "144", "spots"), theirs("B", "6", "USD")], id="M-3", unit="USD",
               period="year", factors=[(D(52), "weeks a year")])
    assert g.value == D(44928) and g.source.text == f"144 spots {TIMES} $6 {TIMES} 52 weeks a year = $44,928 a year"


def test_a_factor_may_be_a_whole_number_but_never_a_float():
    f = derive("product", [theirs("W", "864", "USD")], id="M", unit="USD", factors=[(52, "weeks a year")])
    assert f.value == D(44928)
    with pytest.raises(ValueError, match="float"):
        derive("product", [theirs("W", "864", "USD")], id="M", unit="USD", factors=[(52.0, "weeks a year")])


def test_a_difference_takes_the_rest_from_the_first():
    f = derive("difference", [theirs("A", "28", "USD"), theirs("B", "22", "USD")], id="D-1", unit="USD")
    assert f.value == D(6) and f.kind == "derived"
    assert f.source.op == "difference" and f.source.inputs == ("A", "B")
    assert f.source.text == f"$28 {MINUS} $22 = $6"
    g = derive("difference", [theirs("A", "100", "USD"), theirs("B", "22", "USD"), theirs("C", "8", "USD")],
               id="D-2", unit="USD")
    assert g.value == D(70) and g.source.text == f"$100 {MINUS} $22 {MINUS} $8 = $70"


def test_a_difference_may_come_out_below_zero():
    f = derive("difference", [theirs("A", "22", "USD"), theirs("B", "28", "USD")], id="D-3", unit="USD")
    assert f.value == D(-6) and f.source.text == f"$22 {MINUS} $28 = -$6"


def test_a_total_adds_and_keeps_the_digits_a_float_would_lose():
    f = derive("total", [theirs("A", "0.1", precision=1), theirs("B", "0.2", precision=1)], id="T-1", unit="",
               precision=1)
    assert f.value == D("0.3") and str(f.value) == "0.3"
    assert f.source.text == "0.1 + 0.2 = 0.3"
    big = derive("product", [theirs("A", "12345678901234567"), theirs("B", "3")], id="T-2", unit="")
    assert big.value == D("37037036703703701")


def test_no_float_noise_reaches_the_result():
    f = derive("product", [theirs("A", "0.07", precision=2), theirs("B", "100")], id="N-1", unit="percent")
    assert f.value == D(7) and str(f.value) == "7"      # not 7.000000000000001, and not 7.00
    assert f.unit == "percent" and display(f) == "7%"


def test_a_ratio_divides_and_a_percent_is_a_ratio_with_a_factor():
    f = derive("ratio", [theirs("A", "432"), theirs("B", "48")], id="R-1", unit="")
    assert f.value == D(9) and f.source.text == f"432 {DIVIDE} 48 = 9"
    pct = derive("ratio", [theirs("A", "12"), theirs("B", "48")], id="R-2", unit="percent",
                 factors=[(D(100), "percent")])
    assert pct.value == D(25) and display(pct) == "25%"
    assert pct.source.text == f"12 {DIVIDE} 48 {TIMES} 100 percent = 25%"


def test_a_ratio_that_does_not_end_is_cut_at_a_fixed_width_and_shown_as_rounded():
    f = derive("ratio", [theirs("A", "1"), theirs("B", "3")], id="R-3", unit="", precision=2)
    assert D("0.3333333333") < f.value < D("0.3333333334")
    assert abs(f.value - D("0.3333333333333333333333333333333333333333333333333333")) < D("1e-49")
    assert display(f) == "~0.33"                                   # shown to 2 places, so it says so
    assert f.source.text.startswith(f"1 {DIVIDE} 3 = ~0.333")      # the working never claims exactness


def test_precision_is_how_it_prints_not_what_it_holds():
    f = derive("product", [theirs("A", "24", "USD"), theirs("B", "36")], id="P-1", unit="USD", period="year",
               precision=-3, factors=[(D(52), "weeks a year")])
    assert f.value == D(44928) and display(f) == "~$45,000"
    assert f.source.text.endswith("= $44,928 a year")              # the working keeps the exact figure


# -- whose it is -----------------------------------------------------------------------

def test_theirs_derived_and_reference_inputs_give_a_derived_figure():
    f = derive("product", [theirs("A", "12"), worked("B", "6"), cited("C", "3")], id="K-1", unit="")
    assert f.kind == "derived" and isinstance(f.source, Working)
    assert f.source.inputs == ("A", "B", "C")


def test_one_figure_of_ours_makes_the_result_ours_and_the_working_is_its_note():
    f = derive("difference", [ours("P", "28", "USD"), theirs("CF-04", "22", "USD")], id="K-2", unit="USD")
    assert f.kind == "ours" and f.value == D(6)
    assert isinstance(f.source, Proposal)
    assert f.source.note == f"$28 {MINUS} $22 = $6"


def test_a_figure_of_ours_far_from_the_end_still_makes_the_result_ours():
    f = derive("product", [theirs("A", "144"), theirs("B", "6", "USD"), ours("C", "2")], id="K-3", unit="USD")
    assert f.kind == "ours" and f.value == D(1728)


# -- refusals, in plain words --------------------------------------------------------

def test_a_total_refuses_figures_in_different_units():
    with pytest.raises(ValueError) as e:
        derive("total", [theirs("A", "22", "USD"), theirs("B", "12", "reformers")], id="X", unit="USD")
    assert "$22" in str(e.value) and "12 reformers" in str(e.value) and "same kind of number" in str(e.value)


def test_a_difference_refuses_figures_in_different_units():
    with pytest.raises(ValueError, match="same kind of number"):
        derive("difference", [theirs("A", "22", "USD"), theirs("B", "6", "classes")], id="X", unit="USD")


def test_a_total_refuses_figures_on_different_periods():
    with pytest.raises(ValueError, match="same period"):
        derive("total", [theirs("A", "22", "USD", period="week"), theirs("B", "5", "USD", period="year")],
               id="X", unit="USD")


def test_a_ratio_by_zero_is_refused():
    with pytest.raises(ValueError, match="zero"):
        derive("ratio", [theirs("A", "12"), theirs("B", "0")], id="X", unit="")


def test_a_float_input_is_refused_in_plain_words():
    with pytest.raises(ValueError, match="float"):
        derive("product", [theirs("A", "12"), 6.0], id="X", unit="")
    with pytest.raises(ValueError, match="Figure"):
        derive("product", [theirs("A", "12"), 6], id="X", unit="")
    with pytest.raises(ValueError, match="Figure"):
        derive("product", [theirs("A", "12"), D(6)], id="X", unit="")


def test_the_shape_of_the_request_is_checked():
    two = [theirs("A", "12"), theirs("B", "6")]
    with pytest.raises(ValueError, match="operation"):
        derive("mean", two, id="X", unit="")
    with pytest.raises(ValueError, match="at least two"):
        derive("total", two[:1], id="X", unit="")
    with pytest.raises(ValueError, match="at least two"):
        derive("product", two[:1], id="X", unit="")
    with pytest.raises(ValueError, match="exactly two"):
        derive("ratio", two + [theirs("C", "2")], id="X", unit="")
    with pytest.raises(ValueError, match="factor"):
        derive("total", two, id="X", unit="", factors=[(D(52), "weeks a year")])
    with pytest.raises(ValueError):
        derive("product", two, id="", unit="")


def test_a_working_too_wide_to_be_exact_is_refused_not_rounded():
    wide = D("9" * 60)
    with pytest.raises(ValueError, match="digits"):
        derive("product", [theirs("A", "1"), theirs("B", "1")], id="X", unit="",
               factors=[(wide, "a"), (wide, "b")])


def test_the_result_round_trips_through_json_for_every_kind():
    a = derive("product", [theirs("A", "12"), theirs("B", "6")], id="J-1", unit="spots", period="week")
    b = derive("product", [theirs("A", "12"), ours("B", "6")], id="J-2", unit="spots", period="week")
    for f in (a, b):
        assert from_json(as_json(f)) == f
    assert as_json(a)["value"] == "72"


def test_decimal_of_takes_a_number_from_json_at_fifteen_digits_and_nothing_else():
    assert decimal_of(0.07) == D("0.07") and str(decimal_of(0.07)) == "0.07"
    assert str(decimal_of(144.0)) == "144" and str(decimal_of(144)) == "144"
    assert str(decimal_of(0.33299999999999996)) == "0.333"
    assert str(decimal_of("22.50")) == "22.50" and decimal_of(D("1.5")) == D("1.5")
    for bad in (True, None, "twelve", float("nan"), float("inf"), [1], D("NaN")):
        with pytest.raises(ValueError):
            decimal_of(bad)


def test_calc_does_not_import_the_engine():
    """The engine imports the pipeline at module level; this package is imported by the pipeline."""
    with open(CALC_PY, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in ast.walk(tree):
        names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                 else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
        assert not any(n == "app.engine" or n.startswith("app.engine.") for n in names), ast.dump(node)


# -- the same number as the engine's calculator ---------------------------------------------
#
# The engine's DecimalCalculator is the other exact calculator in this repo. It
# cannot be used from the pipeline (it refuses subtraction, our proposals, the
# pipeline's claim ids, and importing it closes an import cycle), so derive() is
# a second implementation, and these tests keep the two honest: the same
# operation over the same numbers must give the same Decimal wherever the
# engine accepts it. The engine quantises to the widest input precision; derive
# keeps every digit (it is cut when shown), so "exact" cases are compared as they
# are and the others after the engine's own rounding.

AS_OF = "2025-12-31"


def _engine():
    """The engine's types and calculator. Imported here, lazily, on purpose."""
    from app.engine import types as T
    from app.engine.calc import DecimalCalculator
    return T, DecimalCalculator()


def _entity(T, entity_id, value, unit, family, *, precision, currency=None, basis="year"):
    dims = T.Dimensions(currency=currency, period="FY25", period_basis=basis, scope="group", as_of=AS_OF,
                        definition=None)
    quantity = T.Quantity(D(value), unit, family, dims, precision)
    payload = T.FactPayload(statement=f"stated {entity_id}", basis=T.FactBasis.CLIENT_STATED,
                            measure_id="MEA-1", quantity=quantity, formula=None, inputs=())
    return T.make_entity(kind=T.Kind.FACT, engagement_id="E-1", payload=payload,
                         provenance=T.Provenance(T.Actor.PARTNER, "turn:1", derived_from=("EVI-1",)),
                         confidence=T.Confidence(None), relevance=T.Relevance("DEC-1", 0.5),
                         relation=T.RelationToCentralDecision.INFORMS, status=T.Status.PROPOSED,
                         entity_id=entity_id)


def _quantised(value: Decimal, precision: int) -> Decimal:
    return value.quantize(D(1).scaleb(-precision), rounding="ROUND_HALF_UP")


# Each case: name, op, inputs as (value, precision, unit family, unit), the result's (family, unit),
# the engine's period step with derive's matching factors, the period basis the inputs share, and
# whether the engine's result needs no rounding (so the two must be equal as they stand).
CASES = [
    ("product of three counts", "product",
     [("12", 0, "COUNT", "count"), ("6", 0, "COUNT", "count"), ("6", 0, "COUNT", "count")],
     ("COUNT", "count"), 1, [], "year", True),
    ("product with decimals", "product",
     [("0.25", 2, "COUNT", "count"), ("12", 0, "COUNT", "count")],
     ("COUNT", "count"), 1, [], "year", True),
    ("a week's takings for a year", "product",
     [("6", 0, "MONEY", "USD"), ("144", 0, "COUNT", "count")],
     ("MONEY", "USD"), 52, [(D(52), "weeks a year")], "week", True),
    ("a week's hours for a year", "product",
     [("8", 0, "TIME", "hours"), ("5", 0, "COUNT", "count")],
     ("TIME", "hours"), 52, [(D(52), "weeks a year")], "week", True),
    ("total of money with cents", "total",
     [("22", 2, "MONEY", "USD"), ("28", 2, "MONEY", "USD"), ("5.5", 2, "MONEY", "USD")],
     ("MONEY", "USD"), 1, [], "year", True),
    ("total of counts with decimals", "total",
     [("12.5", 2, "COUNT", "count"), ("7.25", 2, "COUNT", "count"), ("0.25", 2, "COUNT", "count")],
     ("COUNT", "count"), 1, [], "year", True),
    ("ratio that divides exactly", "ratio",
     [("432", 0, "COUNT", "count"), ("48", 0, "COUNT", "count")],
     ("RATE", "%"), 1, [], "year", True),
    ("ratio the engine rounds", "ratio",
     [("10", 4, "COUNT", "count"), ("3", 4, "COUNT", "count")],
     ("RATE", "%"), 1, [], "year", False),
    ("difference, which the engine does as a total with a negative", "difference",
     [("28", 2, "MONEY", "USD"), ("22", 2, "MONEY", "USD")],
     ("MONEY", "USD"), 1, [], "year", True),
]


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_derive_gives_the_same_number_as_the_engine_calculator(case):
    name, op, inputs, (family_name, unit), step, factors, basis, exact = case
    T, engine = _engine()
    # the engine has no subtraction: it adds the later figures as negatives
    entities = []
    for i, (value, precision, fam, u) in enumerate(inputs):
        signed = f"-{value}" if op == "difference" and i > 0 else value
        entities.append(_entity(T, f"FCT-{i + 1}", signed, u, getattr(T.UnitFamily, fam), precision=precision,
                                currency="USD" if fam == "MONEY" else None, basis=basis))
    family = getattr(T.UnitFamily, family_name)
    if op == "product":
        got = engine.product(entities, unit=unit, unit_family=family, period_step=step)
    elif op in ("total", "difference"):
        got = engine.total(entities)
    else:
        got = engine.ratio(*entities)

    figures = [theirs(f"FCT-{i + 1}", value, "" if op == "ratio" else u, precision=precision)
               for i, (value, precision, fam, u) in enumerate(inputs)]
    mine = derive(op, figures, id="CAP-01", unit="" if op == "ratio" else unit, factors=factors)

    assert isinstance(mine.value, Decimal) and isinstance(got.quantity.value, Decimal)
    if exact:
        assert mine.value == got.quantity.value, name
    # the engine rounds to its widest input precision; derive keeps every digit and rounds only to show
    assert _quantised(mine.value, got.quantity.precision) == got.quantity.value, name


# -- the two stages that call derive -----------------------------------------------------
#
# capacity.shape and answer.compute_move used to multiply and subtract floats. They
# now work through derive, and keep every client-visible string as it was
# (tests/test_consultation_flow.py pins those). What changes is only the digits
# float arithmetic got wrong, and a few terms no sane answer holds.

OWNER = ["12 reformers. Six classes a day, six days a week.", "A typical class is about 10.7 of 12 full."]
WEEK = {"shape": "weekly_grid", "unit": "reformer spot", "unit_plural": "reformer spots", "per_slot": 12,
        "slots_per_day": 6, "days_per_week": 6, "typical_taken": 10.7, "full_slots": []}
CLAIMS = [{"id": "CF-01", "value": 144, "unit": "spots", "text": "144 spots", "provenance": "client_input"},
          {"id": "CF-02", "value": 100, "unit": "members", "text": "100 members", "provenance": "client_input"},
          {"id": "CF-04", "value": 22, "unit": "USD", "text": "$22 a class", "provenance": "client_input"},
          {"id": "CF-08", "value": 8, "unit": "hours", "text": "8 hours", "provenance": "client_input"}]


def _move(parts):
    return {"label": "x", "unit": "USD", "period": "year",
            "terms": [{"label": "spots a week", "value": 144, "from": "CF-01"},
                      {"label": "rise", "parts": parts},
                      {"label": "weeks a year", "value": 52, "from": "constant"}]}


def test_the_week_has_no_float_noise_in_what_it_stores():
    from app.pipeline import capacity
    pic = capacity.shape(WEEK, OWNER)
    taken = {d["key"]: d["value"] for d in pic["derived"]}
    # 10.7 * 6 * 6 is 385.19999999999993 and 432 less that is 46.80000000000007 in floats
    assert taken["CAP-03"] == 385.2 and repr(taken["CAP-03"]) == "385.2"
    assert taken["CAP-04"] == 46.8 and repr(taken["CAP-04"]) == "46.8"
    assert pic["taken"] == 385.2 and pic["capacity"] == 432 and isinstance(pic["capacity"], int)


def test_the_total_picture_takes_the_used_from_the_capacity_exactly():
    from app.pipeline import capacity
    pic = capacity.shape({"shape": "total", "unit": "van", "total_capacity": 40.3, "total_taken": 31.1,
                          "period": "day"}, ["We have 40.3 vans and 31.1 are on the road."])
    # 40.3 - 31.1 is 9.199999999999996 in floats
    assert {d["key"]: d["value"] for d in pic["derived"]}["CAP-03"] == 9.2


def test_the_move_is_exact_where_floats_are_not():
    from app.pipeline import answer
    raw = {"unit": "members", "period": "year", "label": "x",
           "terms": [{"label": "members", "value": 100, "from": "CF-02"},
                     {"label": "share who stay", "value": 0.07, "from": "proposed"}]}
    move = answer.compute_move(raw, CLAIMS)
    assert move["value"] == 7.0 and repr(move["value"]) == "7.0"     # 100 * 0.07 is 7.000000000000001 in floats
    assert move["working"] == "100 members × 0.07 proposed share who stay = 7"


def test_a_proposed_number_takes_the_unit_of_what_it_is_taken_from():
    from app.pipeline import answer
    # no "$" and no "price" in the label: the proposal is still dollars beside a dollar figure
    parts = [{"value": 28, "from": "proposed", "label": "proposed uplift"}, {"value": 22, "from": "CF-04", "sign": -1}]
    assert answer.compute_move(_move(parts), CLAIMS)["value"] == 144 * 6 * 52


def test_parts_in_two_units_are_refused_not_subtracted():
    from app.pipeline import answer
    parts = [{"value": 22, "from": "CF-04"}, {"value": 8, "from": "CF-08", "sign": -1}]
    assert answer.compute_move(_move(parts), CLAIMS) is None


def test_parts_with_nothing_to_take_away_from_or_with_a_constant_in_them_are_refused():
    from app.pipeline import answer
    assert answer.compute_move(_move([{"value": 22, "from": "CF-04", "sign": -1}]), CLAIMS) is None
    assert answer.compute_move(_move([{"value": 22, "from": "CF-04"}, {"value": 12, "from": "constant"}]),
                               CLAIMS) is None


# -- precision left to the working, ties, and very small results ---------------------------------

def test_a_result_with_no_precision_shows_the_places_it_needs():
    three = [theirs("A", "10.7", "spots", precision=1), theirs("B", "6"), theirs("C", "6")]
    f = derive("product", three, id="P-1", unit="spots", period="week")
    assert f.precision == 1 and display(f) == "385.2 spots"
    assert f.source.text.endswith("= 385.2 spots a week")
    whole = derive("product", [theirs("A", "12"), theirs("B", "6"), theirs("C", "6")], id="P-2", unit="spots")
    assert whole.precision == 0 and display(whole) == "432 spots"
    cut = derive("product", three, id="P-3", unit="spots", precision=0)     # an int still rounds, and says so
    assert display(cut) == "~385 spots" and cut.value == D("385.2")


def test_a_chain_of_steps_reads_exactly_at_every_step():
    taken = derive("product", [theirs("T", "10.7", "spots a slot", precision=1), theirs("S", "6", "slots a day"),
                               theirs("D", "6", "days a week")], id="CAP-03", unit="spots", period="week")
    empty = derive("difference", [theirs("C", "432", "spots", period="week"), taken], id="CAP-04", unit="spots",
                   period="week")
    assert taken.source.text == f"10.7 spots a slot {TIMES} 6 slots a day {TIMES} 6 days a week = 385.2 spots a week"
    assert empty.source.text == f"432 spots {MINUS} 385.2 spots = 46.8 spots a week"
    assert "~" not in taken.source.text + empty.source.text


def test_a_ratio_that_does_not_end_shows_the_places_it_is_cut_to_and_says_so():
    f = derive("ratio", [theirs("A", "1"), theirs("B", "3")], id="R-4", unit="")
    assert f.precision == calc.SHOWN_PLACES == 12
    assert display(f) == "~0.333333333333"


def test_a_tiny_result_is_zero_only_when_it_is_zero():
    # 4E-13 is under half a unit of the 12th place but is not zero: it keeps its digits
    f = derive("product", [worked("A", "2E-7", precision=7), worked("B", "2E-6", precision=6)], id="T-1", unit="")
    assert display(f) == "0." + "0" * 12 + "4" and "~" not in f.source.text
    # 6E-13 rounds to a figure at the 12th place, so it is shown there, as rounded
    g = derive("product", [worked("A", "2E-7", precision=7), worked("B", "3E-6", precision=6)], id="T-2", unit="")
    assert display(g) == "~0." + "0" * 11 + "1"
    # three digits are kept of a value far smaller than that, and the working agrees
    h = derive("product", [worked("A", "1.234567E-20", precision=26), worked("B", "1")], id="T-3", unit="")
    assert display(h) == "~0." + "0" * 19 + "123" and "~0.0000000000000000000123" in h.source.text
    z = derive("product", [worked("A", "0"), worked("B", "5")], id="T-4", unit="")
    assert display(z) == "0" and z.source.text == f"0 {TIMES} 5 = 0"
    for text in (f.source.text, g.source.text, h.source.text, z.source.text):
        assert not re.search(r"~0(\.0+)?(?![\d.])", text), text      # never "~0.000000": a value shown as zero


def test_a_working_that_underflows_says_it_is_too_small_not_too_wide():
    with pytest.raises(ValueError, match="too small"):
        derive("product", [worked("A", "1E-9999"), worked("B", "1E-9999")], id="U", unit="")


def test_a_tie_rounds_away_from_zero_in_display_and_in_round_half_up():
    half = derive("product", [theirs("A", "1813"), theirs("B", "0.5", precision=1)], id="H-1", unit="USD", precision=0)
    assert half.value == D("906.5") and display(half) == "~$907"
    assert half.source.text.endswith("= $906.50")               # the working keeps the exact figure
    below = derive("difference", [theirs("A", "22", "USD"), theirs("B", "28.5", "USD", precision=1)], id="H-2",
                   unit="USD", precision=0)
    assert display(below) == "~-$7"                              # -6.5 goes to -7, not to -6
    cents = derive("product", [theirs("A", "3031"), theirs("B", "0.025", precision=3)], id="H-3", unit="USD",
                   precision=2)
    assert cents.value == D("75.775") and display(cents) == "~$75.78"
    # the figure, its working and the stage formatters all use the same rule
    for value, places in (("906.5", 0), ("75.775", 2), ("-6.5", 0), ("0.5", 0), ("2.675", 2), ("44500", -3)):
        f = Figure("x", D(value), "", None, "derived", Working((), "product", ""), places)
        assert displayed_value(f) == round_half_up(value, places), (value, places)
    assert (round_half_up(2.5), round_half_up(-2.5), round_half_up(0.285, 2), round_half_up(1.005, 2)) == (
        D(3), D(-3), D("0.29"), D("1.01"))       # Python's round() gives 2, -2, 0.28 and 1.0


def test_places_of_counts_what_is_needed_not_what_was_written():
    assert [places_of(D(v)) for v in ("22.50", "450", "1E+3", "0.0010", "7", "0")] == [1, 0, 0, 3, 0, 0]


def test_units_are_compared_ignoring_case_and_the_singular_or_plural_of_a_time_or_count_word():
    for a, b in (("hour", "hours"), ("USD", "usd"), ("Week", "weeks"), ("count", "counts"), (" day ", "Days")):
        assert unit_key(a) == unit_key(b), (a, b)
        f = derive("total", [theirs("A", "3", a), theirs("B", "2", b)], id="Q", unit=a)
        assert f.value == D(5)
    for a, b in (("hours", "minutes"), ("USD", "EUR"), ("class", "classes"), ("USD", "")):
        with pytest.raises(ValueError, match="same kind of number"):
            derive("difference", [theirs("A", "3", a), theirs("B", "2", b)], id="Q", unit=a)


def test_decimal_of_and_the_claim_mapping_read_a_float_the_same_way():
    assert [str(decimal_from_float(x)) for x in (0.07, 144.0, 0.33299999999999996)] == ["0.07", "144", "0.333"]
    for x in (0.07, 144.0, 0.33299999999999996, 1e-7, 123456789.123456789, 2.5e20, 22.5, -3.1000000000000005):
        claim = {"id": "CF-01", "type": "client_fact", "value": x, "unit": "count", "provenance": "client_input",
                 "text": "t", "source": "client brief"}
        assert decimal_of(x) == decimal_from_float(x) == from_claim(claim).value, x
        assert str(decimal_of(x)) == str(from_claim(claim).value), x
    with pytest.raises(ValueError):
        decimal_from_float(float("nan"))


# -- the stages: what their working reads like, ties, non-finite numbers, claims --------------------

def _spy(monkeypatch, module):
    """Record every Figure `module.derive` returns, by id."""
    seen, real = {}, module.derive

    def spy(op, inputs, **kw):
        figure = real(op, inputs, **kw)
        seen[kw["id"]] = figure
        return figure
    monkeypatch.setattr(module, "derive", spy)
    return seen


def test_the_weeks_chained_working_shows_exact_figures_at_every_step(monkeypatch):
    from app.pipeline import capacity
    seen = _spy(monkeypatch, capacity)
    capacity.shape(WEEK, OWNER)
    assert seen["CAP-03"].source.text == (f"10.7 reformer spots a slot {TIMES} 6 slots a day {TIMES} "
                                          "6 days a week = 385.2 reformer spots a week")
    assert seen["CAP-04"].source.text == f"432 reformer spots {MINUS} 385.2 reformer spots = 46.8 reformer spots a week"
    assert "CAP-03a" not in seen and "CAP-05" not in seen        # no slot sells out: nothing is added on


def test_a_week_with_a_slot_that_sells_out_chains_without_rounding(monkeypatch):
    from app.pipeline import capacity
    seen = _spy(monkeypatch, capacity)
    raw = dict(WEEK, slot_times=[None] * 5 + ["18:00"], full_slots=["18:00"])
    capacity.shape(raw, OWNER + ["The 6pm class sells out."])
    assert seen["CAP-03"].source.text == "321 reformer spots + 72 reformer spots = 393 reformer spots a week"
    assert seen["CAP-04"].source.text == f"432 reformer spots {MINUS} 393 reformer spots = 39 reformer spots a week"
    steps = [f for f in seen.values() if f.id.startswith("CAP")]
    assert steps and all("~" not in f.source.text and " 0 " not in f.source.text for f in steps)


def test_the_moves_chained_working_shows_exact_figures_at_every_step(monkeypatch):
    from app.pipeline import answer
    seen = _spy(monkeypatch, answer)
    parts = [{"value": 28, "from": "proposed", "label": "proposed evening price"},
             {"value": 22, "from": "CF-04", "sign": -1}]
    move = answer.compute_move(_move(parts), CLAIMS)
    assert seen["rise"].source.note == f"$28 {MINUS} $22 = $6"
    assert seen["move"].source.note == f"144 spots {TIMES} $6 {TIMES} 52 weeks a year = $44,928 a year"
    assert move["value"] == 44928.0 and "~" not in seen["move"].source.note


def test_a_tie_prints_away_from_zero_in_what_the_stages_say():
    from app.pipeline import answer, capacity
    assert (capacity._fmt(385.25), capacity._fmt(0.05), capacity._fmt(7), capacity._fmt(385.2)) == (
        "385.3", "0.1", "7", "385.2")
    assert (answer._money(906.5), answer._money(75.775), answer._money(44928.0), answer._money(-906.5)) == (
        "$907", "$76", "$44,928", "$-907")
    assert (answer._plain(0.125), answer._plain(2.5), answer._plain(1000.0), answer._plain(7.000000000000001)) == (
        "0.13", "2.5", "1,000", "7")
    assert [answer._said(v) for v in (4.5, 44500.0, 450.0, 4450.0, -4.5, 44928.0, 0.4)] == [
        5, 45000, 450, 4500, -5, 45000, 0]
    assert answer._plain(float("inf")) == "inf" and answer._money(float("nan")) == "nan"


def test_a_share_that_lands_on_a_half_percent_rounds_up():
    from app.pipeline import capacity
    # 1.5 of 12 in 36 slots is 54 of 432, which is exactly 12.5 percent
    pic = capacity.shape(dict(WEEK, typical_taken=1.5), ["12 reformers. Six classes a day, six days a week.",
                                                          "A typical class is about 1.5 of 12 full."])
    assert pic["taken"] == 54.0 and pic["pct"] == 13
    van = capacity.shape({"shape": "total", "unit": "van", "total_capacity": 8, "total_taken": 1, "period": "day"},
                         ["We have 8 vans and 1 is on the road."])
    assert van["pct"] == 13                                      # 1 of 8 is 12.5 percent


NOT_A_NUMBER = [float("nan"), float("inf"), float("-inf"), 1e999, 10 ** 400, "NaN", "Infinity"]


@pytest.mark.parametrize("bad", NOT_A_NUMBER, ids=repr)
def test_a_number_that_is_not_one_in_a_move_is_refused_never_raised(bad):
    from app.pipeline import answer
    spots = {"label": "spots a week", "value": 144, "from": "CF-01"}
    cases = [
        [spots, {"label": "new", "value": bad, "from": "proposed"}],
        [dict(spots, value=bad), {"label": "price", "value": 22, "from": "CF-04"}],
        [spots, {"label": "weeks a year", "value": bad, "from": "constant"}],
        [spots, {"label": "rise", "parts": [{"value": bad, "from": "proposed", "label": "p"},
                                            {"value": 22, "from": "CF-04", "sign": -1}]}],
    ]
    for terms in cases:
        assert answer.compute_move({"unit": "USD", "terms": terms}, CLAIMS) is None
    assert answer.compute_move({"unit": "USD", "terms": [spots, {"label": "x", "value": 2, "from": "proposed"}]},
                               CLAIMS) is not None


@pytest.mark.parametrize("bad", NOT_A_NUMBER, ids=repr)
def test_the_answer_does_not_raise_on_a_number_that_is_not_one(bad):
    from app.pipeline import answer
    raw = {"headline": "You are full.", "action": {"weeks": bad, "name": "plan"},
           "move": {"unit": "USD", "terms": [{"label": "a", "value": bad, "from": "CF-04"},
                                              {"label": "b", "value": 2, "from": "proposed"}]},
           "figures": [{"value": "$22", "label": "price", "cites": ["CF-04"]}]}
    got, problems = answer.shape(raw, CLAIMS, ["I charge $22 a class."])
    assert got["action"]["weeks"] == 6 and got["move"] is None and problems


def test_parts_are_compared_by_kind_of_number_not_by_spelling():
    from app.pipeline import answer
    claims = CLAIMS + [{"id": "H-1", "value": 8, "unit": "Hours", "text": "8 hours", "provenance": "client_input"},
                       {"id": "H-2", "value": 2, "unit": "hour", "text": "2 hours", "provenance": "client_input"},
                       {"id": "U-1", "value": 22, "unit": "usd", "text": "$22", "provenance": "client_input"},
                       {"id": "U-2", "value": 5, "unit": "USD", "text": "$5", "provenance": "client_input"}]
    hours = answer.compute_move(_move([{"value": 8, "from": "H-1"}, {"value": 2, "from": "H-2", "sign": -1}]), claims)
    assert hours["value"] == 144 * 6 * 52
    money = answer.compute_move(_move([{"value": 22, "from": "U-1"}, {"value": 5, "from": "U-2", "sign": -1}]), claims)
    assert money["value"] == 144 * 17 * 52
    # different kinds still do not mix, and a part that is only taken away has nothing to be taken from
    assert answer.compute_move(_move([{"value": 22, "from": "U-1"}, {"value": 2, "from": "H-2", "sign": -1}]),
                               claims) is None
    assert answer.compute_move(_move([{"value": 8, "from": "H-1", "sign": -1},
                                      {"value": 2, "from": "H-2", "sign": -1}]), claims) is None


def test_a_cited_claim_is_a_figure_by_the_claim_mapping_or_not_at_all():
    from app.pipeline import answer
    gate = {"id": "PG-1", "value": 22, "unit": "USD", "text": "$22", "provenance": "canonical_gate",
            "approval_status": "machine_verified", "source": "pilot gate"}
    assert answer._claim_figure(gate, 22.0).kind == "derived"
    assert answer._claim_figure(dict(gate, approval_status="client_stated"), 22.0).kind == "theirs"
    quoted = answer._claim_figure(CLAIMS[2], 22.05)                   # the value the term quotes, not the claim's
    assert quoted.kind == "theirs" and quoted.value == D("22.05") and quoted.precision == 2
    assert quoted.id == "CF-04" and quoted.source.quote == "$22 a class"
    for unmappable in (dict(CLAIMS[2], provenance=None), dict(CLAIMS[2], provenance="hearsay"),
                       dict(CLAIMS[2], provenance="consultant_proposed", approval_status="rejected")):
        assert answer._claim_figure(unmappable, 22.0) is None
    terms = [{"label": "spots a week", "value": 144, "from": "CF-01"},
             {"label": "price", "value": 22, "from": "CF-04"}]
    claims = [dict(CLAIMS[0]), dict(CLAIMS[2], provenance="hearsay")]
    assert answer.compute_move({"unit": "USD", "terms": terms}, claims) is None
    assert answer.compute_move({"unit": "USD", "terms": terms}, [dict(CLAIMS[0]), dict(CLAIMS[2])]) is not None
