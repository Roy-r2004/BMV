"""Pins for app/engine/calc: exact arithmetic, refusals, reconciliation.

Each test names the law it pins and the mutation that must break it
(work_breakdown C4-calc): a mean over conflicting inputs, a dropped currency
check, a falsy dimension test, a recompute tolerance.
"""
from __future__ import annotations

import ast
import os
from decimal import Decimal

import pytest

from app.engine import types as T
from app.engine.calc import (
    COMPARABLE, INCOMPARABLE, UNKNOWN_DIMENSION, DecimalCalculator, IncomparableInputs, PERIOD_STEPS,
    Reconciliation, comparable, family_of, format_quantity, parse_quantity, reconcile,
)
from app.engine.calc.arith import evaluate

AS_OF = "2025-12-31"


def test_calc_boundary_types_are_the_registry_definitions_not_private_copies():
    """The refusal the calculator raises must be the class consumers catch.
    A private copy of IncomparableInputs (or of the result/reconciliation
    dataclasses) would let a refusal escape every `except` in methods/ and
    turn a CONFLICT into a crash. Identity, not just equal names."""
    import app.engine.calc as calc
    from app.engine import registry as R

    for name in ("CalcResult", "Calculator", "IncomparableInputs", "Reconciliation", "RegistryView"):
        assert getattr(calc, name) is getattr(R, name), name
    # the exception arith.py actually raises is catchable via the registry's name
    q = T.Quantity(Decimal("1"), "EUR", T.UnitFamily.MONEY, dims(currency="EUR"), 0)
    r = T.Quantity(Decimal("1"), "USD", T.UnitFamily.MONEY, dims(currency="USD"), 0)
    with pytest.raises(R.IncomparableInputs):
        DecimalCalculator().total([fact("F1", q), fact("F2", r)])


def dims(**over) -> T.Dimensions:
    base = dict(currency=None, period="FY25", period_basis="year", scope="group", as_of=AS_OF, definition=None)
    base.update(over)
    return T.Dimensions(**base)


def qty(value: str, unit: str, family: T.UnitFamily, d: T.Dimensions | None = None, precision: int = 2) -> T.Quantity:
    return T.Quantity(Decimal(value), unit, family, d or dims(), precision)


def fact(entity_id: str, quantity: T.Quantity | None, *, basis: T.FactBasis = T.FactBasis.CLIENT_STATED,
         measure_id: str = "MEA-1", formula: str | None = None, inputs: tuple[str, ...] = ()) -> T.Entity:
    payload = T.FactPayload(statement=f"stated {entity_id}", basis=basis, measure_id=measure_id, quantity=quantity,
                            formula=formula, inputs=inputs)
    return T.make_entity(kind=T.Kind.FACT, engagement_id="E-1", payload=payload,
                         provenance=T.Provenance(T.Actor.PARTNER, "turn:1", derived_from=("EVI-1",)),
                         confidence=T.Confidence(None), relevance=T.Relevance("DEC-1", 0.5),
                         relation=T.RelationToCentralDecision.INFORMS, status=T.Status.PROPOSED, entity_id=entity_id)


def assumption(entity_id: str, quantity: T.Quantity, approval: T.ApprovalState) -> T.Entity:
    payload = T.AssumptionPayload(statement="share", quantity=quantity, approval=approval)
    return T.make_entity(kind=T.Kind.ASSUMPTION, engagement_id="E-1", payload=payload,
                         provenance=T.Provenance(T.Actor.METHOD, "method:scenario@1"),
                         confidence=T.Confidence(None), relevance=T.Relevance("DEC-1", 0.5),
                         relation=T.RelationToCentralDecision.INFORMS, status=T.Status.PROPOSED, entity_id=entity_id)


class View:
    """The slice of RegistryView the calculator reads: get() and query(kind)."""
    engagement_id = "E-1"

    def __init__(self, *entities: T.Entity):
        self.rows = {e.id: e for e in entities}

    def get(self, entity_id):
        return self.rows.get(entity_id)

    def query(self, kind=None, *, status=None, where=None):
        return [e for e in self.rows.values() if kind is None or e.kind is kind]


def money(entity_id: str, value: str, currency: str = "EUR", **over) -> T.Entity:
    return fact(entity_id, qty(value, currency, T.UnitFamily.MONEY, dims(currency=currency, **over)))


# -- exact arithmetic and recompute (L7) ---------------------------------------

def test_product_recompute_is_exact_428_not_430():
    hours = fact("FCT-1", qty("214", "hours", T.UnitFamily.TIME))
    rate = fact("FCT-2", qty("2", "count", T.UnitFamily.COUNT))
    calc = DecimalCalculator()
    res = calc.product([hours, rate], unit="hours", unit_family=T.UnitFamily.TIME)
    assert res.quantity.value == Decimal("428.00")
    assert res.formula == "FCT-1 * FCT-2" and res.inputs == ("FCT-1", "FCT-2")
    stored_ok = fact("FCT-3", res.quantity, basis=T.FactBasis.CALCULATED, formula=res.formula, inputs=res.inputs)
    drifted = fact("FCT-4", qty("430", "hours", T.UnitFamily.TIME), basis=T.FactBasis.CALCULATED,
                   formula=res.formula, inputs=res.inputs)
    view = View(hours, rate, stored_ok, drifted)
    assert calc.recompute(stored_ok, view) is True
    # 430 is 0.47% off 428: inside every "close enough" tolerance r30 ever
    # used, and still an invented number. Mutation: widen recompute to 0.5%.
    assert calc.recompute(drifted, view) is False


def test_recompute_refuses_missing_inputs_and_non_calculated():
    a = fact("FCT-1", qty("10", "hours", T.UnitFamily.TIME))
    calc = DecimalCalculator()
    stored = fact("FCT-9", qty("20", "hours", T.UnitFamily.TIME), basis=T.FactBasis.CALCULATED,
                  formula="FCT-1 * FCT-2", inputs=("FCT-1", "FCT-2"))
    assert calc.recompute(stored, View(a, stored)) is False
    assert calc.recompute(a, View(a)) is False


def test_formula_grammar_is_exact_and_has_no_eval():
    v = {"FCT-1": Decimal("214"), "FCT-2": Decimal("2")}
    assert evaluate("FCT-1 * FCT-2 * 12", v) == Decimal("5136")
    assert evaluate("(FCT-1 + FCT-2) / 2", v) == Decimal("108")
    with pytest.raises(ValueError):
        evaluate("__import__('os')", v)
    with pytest.raises(ValueError):
        evaluate("FCT-7 * 2", v)


def test_period_conversion_month_to_year_is_x12_and_recomputes():
    monthly = money("FCT-1", "1250.50", period_basis="month")
    calc = DecimalCalculator()
    res = calc.convert_period(monthly, "year")
    assert res.quantity.value == Decimal("15006.00")
    assert res.quantity.dimensions.period_basis == "year"
    assert res.formula == "FCT-1 * 12 / 1"
    assert PERIOD_STEPS == {"year": 1, "month": 12, "fortnight": 26, "week": 52, "day": 365}
    stored = fact("FCT-2", res.quantity, basis=T.FactBasis.CALCULATED, formula=res.formula, inputs=res.inputs)
    assert calc.recompute(stored, View(monthly, stored)) is True
    weekly = calc.convert_period(stored, "week")
    assert weekly.quantity.value == Decimal("288.58") and weekly.inputs == ("FCT-2",)


def test_period_conversion_needs_a_pinned_basis():
    unpinned = money("FCT-1", "100", period_basis=None)
    with pytest.raises(IncomparableInputs) as err:
        DecimalCalculator().convert_period(unpinned, "year")
    assert err.value.reason == "unknown_dimension" and "period_basis" in err.value.unpinned
    with pytest.raises(ValueError):
        DecimalCalculator().convert_period(money("FCT-2", "100"), "quarter")


def test_product_with_period_step_annualises():
    weekly = fact("FCT-1", qty("45", "hours", T.UnitFamily.TIME, dims(period_basis="week")))
    calc = DecimalCalculator()
    res = calc.product([weekly], unit="hours", unit_family=T.UnitFamily.TIME, period_step=52)
    assert res.quantity.value == Decimal("2340.00") and res.formula == "FCT-1 * 52"
    assert res.quantity.dimensions.period_basis == "year"
    with pytest.raises(ValueError):
        calc.product([weekly], unit="hours", unit_family=T.UnitFamily.TIME, period_step=13)


# -- refusals: never a guessed number ----------------------------------------

def test_cross_currency_without_conversion_fact_is_a_refusal_not_a_number():
    eur, usd = money("FCT-1", "100", "EUR"), money("FCT-2", "100", "USD")
    calc = DecimalCalculator(View(eur, usd))
    with pytest.raises(IncomparableInputs) as err:
        calc.total([eur, usd])
    assert err.value.reason == "incomparable" and "currency" in err.value.unpinned
    with pytest.raises(IncomparableInputs):
        calc.product([eur, usd], unit="EUR", unit_family=T.UnitFamily.MONEY)
    assert comparable(eur.payload.quantity, usd.payload.quantity) == INCOMPARABLE


def test_cross_currency_with_a_registered_conversion_fact_converts_and_cites_it():
    eur, usd = money("FCT-1", "100", "EUR"), money("FCT-2", "100", "USD")
    rate = fact("FCT-3", qty("0.9", "EUR/USD", T.UnitFamily.RATE, dims(as_of=AS_OF)), basis=T.FactBasis.EXTERNAL_SOURCED,
                measure_id="MEA-9")
    calc = DecimalCalculator(View(eur, usd, rate))
    res = calc.total([eur, usd])
    assert res.quantity.value == Decimal("190.00") and res.quantity.unit == "EUR"
    assert "FCT-3" in res.inputs and res.formula == "FCT-1 + FCT-2 * FCT-3"
    stored = fact("FCT-4", res.quantity, basis=T.FactBasis.CALCULATED, formula=res.formula, inputs=res.inputs)
    assert calc.recompute(stored, View(eur, usd, rate, stored)) is True


def test_money_without_a_pinned_currency_is_an_unknown_dimension():
    a = fact("FCT-1", qty("100", "EUR", T.UnitFamily.MONEY, dims(currency=None)))
    b = money("FCT-2", "100", "EUR")
    with pytest.raises(IncomparableInputs) as err:
        DecimalCalculator().product([a, b], unit="EUR", unit_family=T.UnitFamily.MONEY)
    assert err.value.reason == "unknown_dimension" and err.value.unpinned == ("currency",)
    assert comparable(a.payload.quantity, b.payload.quantity) == UNKNOWN_DIMENSION


def test_hours_times_a_share_the_client_never_gave_is_refused():
    hours = fact("FCT-1", qty("2000", "hours", T.UnitFamily.TIME))
    guessed = fact("FCT-2", qty("0.4", "%", T.UnitFamily.RATE), basis=T.FactBasis.INFERRED, measure_id="MEA-2")
    unapproved = assumption("ASM-1", qty("0.4", "%", T.UnitFamily.RATE), T.ApprovalState.UNAPPROVED)
    calc = DecimalCalculator()
    for share in (guessed, unapproved):
        with pytest.raises(ValueError, match="share"):
            calc.product([hours, share], unit="hours", unit_family=T.UnitFamily.TIME)
    given = fact("FCT-3", qty("0.4", "%", T.UnitFamily.RATE), measure_id="MEA-2")
    approved = assumption("ASM-2", qty("0.4", "%", T.UnitFamily.RATE), T.ApprovalState.APPROVED)
    for share in (given, approved):
        assert calc.product([hours, share], unit="hours", unit_family=T.UnitFamily.TIME).quantity.value == Decimal("800.00")


def test_capacity_to_money_needs_a_price_fact():
    volume = fact("FCT-1", qty("500", "requests/sec", T.UnitFamily.CAPACITY))
    calc = DecimalCalculator()
    with pytest.raises(IncomparableInputs) as err:
        calc.product([volume], unit="EUR", unit_family=T.UnitFamily.MONEY)
    assert err.value.reason == "capacity_to_money"
    price = money("FCT-2", "0.10")
    assert calc.product([volume, price], unit="EUR", unit_family=T.UnitFamily.MONEY).quantity.value == Decimal("50.00")


def test_total_and_ratio_refuse_incomparable_and_unknown_dimensions():
    a = fact("FCT-1", qty("40", "heads", T.UnitFamily.COUNT))
    b = fact("FCT-2", qty("5", "FTE", T.UnitFamily.COUNT))
    c = fact("FCT-3", qty("10", "heads", T.UnitFamily.COUNT, dims(as_of=None)))
    calc = DecimalCalculator()
    with pytest.raises(IncomparableInputs) as err:
        calc.total([a, b])
    assert err.value.reason == "incomparable"
    with pytest.raises(IncomparableInputs) as err:
        calc.total([a, c])
    assert err.value.reason == "unknown_dimension" and err.value.unpinned == ("as_of",)
    d = fact("FCT-4", qty("10", "heads", T.UnitFamily.COUNT))
    assert calc.total([a, d]).quantity.value == Decimal("50.00")
    r = calc.ratio(d, a)
    assert r.quantity.value == Decimal("0.25") and r.quantity.unit_family is T.UnitFamily.RATE
    with pytest.raises(IncomparableInputs):
        calc.ratio(a, b)
    with pytest.raises(ValueError):
        calc.ratio(a, fact("FCT-5", qty("0", "heads", T.UnitFamily.COUNT)))


def test_comparable_on_incompatible_families_is_incomparable():
    hours = qty("10", "hours", T.UnitFamily.TIME)
    eur = qty("10", "EUR", T.UnitFamily.MONEY, dims(currency="EUR"))
    assert comparable(hours, eur) == INCOMPARABLE
    assert comparable(hours, qty("10", "hours", T.UnitFamily.TIME)) == COMPARABLE
    assert comparable(hours, qty("10", "hours", T.UnitFamily.TIME, dims(scope=None))) == UNKNOWN_DIMENSION
    assert comparable(hours, qty("10", "hours", T.UnitFamily.TIME, dims(scope="NL"))) == INCOMPARABLE


# -- reconciliation: never averaged --------------------------------------------

def test_same_measure_same_dimensions_different_value_is_a_value_conflict():
    a = fact("FCT-1", qty("40", "heads", T.UnitFamily.COUNT))
    b = fact("FCT-2", qty("45", "heads", T.UnitFamily.COUNT))
    r = reconcile(a, b)
    # Mutation: a mean over the two (42.5 reported as agreement) makes this fail.
    assert r.outcome == "conflict" and r.conflict_kind is T.ConflictKind.VALUE
    assert reconcile(a, fact("FCT-3", qty("40", "heads", T.UnitFamily.COUNT))).outcome == "same"


def test_client_stated_versus_document_verified_is_client_vs_record():
    a = fact("FCT-1", qty("40", "heads", T.UnitFamily.COUNT), basis=T.FactBasis.CLIENT_STATED)
    b = fact("FCT-2", qty("45", "heads", T.UnitFamily.COUNT), basis=T.FactBasis.DOCUMENT_VERIFIED)
    assert reconcile(a, b).conflict_kind is T.ConflictKind.CLIENT_VS_RECORD
    assert reconcile(b, a).conflict_kind is T.ConflictKind.CLIENT_VS_RECORD


def test_different_as_of_is_distinct_not_a_conflict():
    a = fact("FCT-1", qty("40", "heads", T.UnitFamily.COUNT, dims(as_of="2024-12-31")))
    b = fact("FCT-2", qty("45", "heads", T.UnitFamily.COUNT, dims(as_of="2025-12-31")))
    assert reconcile(a, b) == Reconciliation("distinct")
    c = fact("FCT-3", qty("45", "heads", T.UnitFamily.COUNT, dims(scope="NL")))
    assert reconcile(b, c).outcome == "distinct"


def test_differing_definition_or_unit_is_a_definition_conflict():
    a = fact("FCT-1", qty("40", "heads", T.UnitFamily.COUNT, dims(definition="heads incl. agency")))
    b = fact("FCT-2", qty("45", "heads", T.UnitFamily.COUNT, dims(definition="permanent heads")))
    assert reconcile(a, b).conflict_kind is T.ConflictKind.DEFINITION
    c = fact("FCT-3", qty("45", "FTE", T.UnitFamily.COUNT))
    assert reconcile(fact("FCT-4", qty("40", "heads", T.UnitFamily.COUNT)), c).conflict_kind is T.ConflictKind.DEFINITION


def test_unpinned_dimension_is_a_question_and_absence_is_tested_with_is_none():
    pinned = fact("FCT-1", qty("40", "heads", T.UnitFamily.COUNT))
    no_as_of = fact("FCT-2", qty("45", "heads", T.UnitFamily.COUNT, dims(as_of=None)))
    r = reconcile(pinned, no_as_of)
    assert r.outcome == "question" and r.unpinned == ("as_of",) and r.conflict_kind is None
    # pinned on one side only is a question too
    r = reconcile(pinned, fact("FCT-3", qty("40", "heads", T.UnitFamily.COUNT, dims(definition="heads"))))
    assert r.outcome == "question" and r.unpinned == ("definition",)
    # A present-but-empty value written by a newer normaliser is PINNED, not
    # absent: `is None` keeps it; a falsy test would condemn both facts as
    # unpinned and open a question about nothing. Mutation: `is None` -> falsy.
    # as_of is a dimension a COUNT NEEDS, so it is the one a falsy test
    # would misread; scope pinned empty on one side and named on the other
    # is two populations (distinct), not a missing pin.
    empty_as_of = dims(as_of="")
    a = fact("FCT-4", qty("40", "heads", T.UnitFamily.COUNT, empty_as_of))
    b = fact("FCT-5", qty("40", "heads", T.UnitFamily.COUNT, empty_as_of))
    assert reconcile(a, b).outcome == "same"
    assert comparable(a.payload.quantity, b.payload.quantity) == COMPARABLE
    c = fact("FCT-6", qty("40", "heads", T.UnitFamily.COUNT, dims(scope="")))
    d = fact("FCT-7", qty("40", "heads", T.UnitFamily.COUNT, dims(scope="NL")))
    assert reconcile(c, d).outcome == "distinct"
    assert comparable(c.payload.quantity, d.payload.quantity) == INCOMPARABLE


def test_fact_without_a_quantity_asks_for_one():
    a = fact("FCT-1", qty("40", "heads", T.UnitFamily.COUNT))
    b = fact("FCT-2", None)
    assert reconcile(a, b).outcome == "question" and reconcile(a, b).unpinned == ("quantity",)


def test_reconcile_joins_on_measure_id_only_never_on_text():
    a = fact("FCT-1", qty("40", "heads", T.UnitFamily.COUNT), measure_id="MEA-1")
    b = fact("FCT-2", qty("40", "heads", T.UnitFamily.COUNT), measure_id="MEA-2")
    with pytest.raises(ValueError):
        reconcile(a, b)
    with pytest.raises(ValueError):
        reconcile(fact("FCT-3", None, measure_id=None), fact("FCT-4", None, measure_id=None))
    with pytest.raises(ValueError):
        reconcile(a, assumption("ASM-1", qty("0.1", "%", T.UnitFamily.RATE), T.ApprovalState.APPROVED))


def test_calc_package_has_no_mean_blend_or_similarity():
    """The law behind every reconciliation test: the package cannot compute
    a midpoint because nothing in it names one."""
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "app", "engine", "calc")
    forbidden_modules = {"statistics", "difflib", "rapidfuzz"}
    forbidden_names = {"mean", "fmean", "median", "average", "blend", "midpoint"}
    for name in sorted(os.listdir(root)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(root, name), encoding="utf-8") as fh:
            src = fh.read()
        assert src.isascii(), f"{name}: non-ASCII in source"
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                assert not (set(m.split(".")[0] for m in mods) & forbidden_modules), f"{name}: forbidden import"
            if isinstance(node, (ast.Name, ast.Attribute, ast.FunctionDef)):
                ident = getattr(node, "id", None) or getattr(node, "attr", None) or getattr(node, "name", None)
                assert ident not in forbidden_names, f"{name}: {ident} at line {node.lineno}"
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "eval", f"{name}: eval()"


# -- units ----------------------------------------------------------------------

def test_parse_quantity_is_exact_from_the_token_and_pins_currency():
    q = parse_quantity("we pay $1,250.50 per month for hosting")
    assert q is not None and q.value == Decimal("1250.50") and q.unit == "USD"
    assert q.unit_family is T.UnitFamily.MONEY and q.dimensions.currency == "USD" and q.precision == 2
    pct = parse_quantity("about 12% of inquiries")
    assert pct.value == Decimal("0.12") and pct.unit == "%" and pct.unit_family is T.UnitFamily.RATE
    hrs = parse_quantity("45 hours a week on order entry")
    assert hrs.value == Decimal("45") and hrs.unit == "hours" and hrs.unit_family is T.UnitFamily.TIME
    assert parse_quantity("since 2019 we have grown") is None
    assert parse_quantity("no numbers here") is None
    assert parse_quantity("40 people") .unit_family is T.UnitFamily.COUNT
    cap = parse_quantity("needs 24 GB VRAM")
    assert cap.unit == "GB" and cap.unit_family is T.UnitFamily.CAPACITY
    assert family_of("tonnes") is T.UnitFamily.DISTANCE_AREA_MASS and family_of("EUR") is T.UnitFamily.MONEY
    assert family_of("gb / s") is T.UnitFamily.CAPACITY and family_of("widgetry") is T.UnitFamily.OTHER


def test_format_quantity_is_deterministic_and_exact():
    assert format_quantity(qty("1250.5", "EUR", T.UnitFamily.MONEY, dims(currency="EUR", period_basis="month"))) == "EUR 1,250.50 per month"
    assert format_quantity(qty("0.125", "%", T.UnitFamily.RATE, dims(period_basis=None), precision=3)) == "12.5%"
    assert format_quantity(qty("40", "heads", T.UnitFamily.COUNT, dims(period_basis="point_in_time"), precision=0)) == "40 heads"


def test_quantity_refuses_float():
    with pytest.raises(TypeError):
        T.Quantity(0.1, "EUR", T.UnitFamily.MONEY)
