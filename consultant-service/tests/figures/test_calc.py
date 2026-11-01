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
from decimal import Decimal

import pytest

from app.figures import calc
from app.figures.calc import decimal_of, derive
from app.figures.model import (
    Figure, Proposal, Reference, TheirsSource, Working, as_json, display, from_json,
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
    assert "$22" in str(e.value) and "12 reformers" in str(e.value) and "same unit" in str(e.value)


def test_a_difference_refuses_figures_in_different_units():
    with pytest.raises(ValueError, match="same unit"):
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
    wide = D("9" * 40)
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
    assert calc.derive is derive


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


def test_at_least_five_operations_are_checked_against_the_engine():
    """The parametrised test above errors if the engine ever refuses a case; this pins that the
    table itself still holds five or more cases and every operation."""
    assert len(CASES) >= 5
    assert {c[1] for c in CASES} == {"product", "total", "difference", "ratio"}
