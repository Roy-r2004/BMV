"""The Figure model (Step 2, Task 1).

A Figure is one number with a kind (theirs, derived, ours, reference), a source
that matches the kind, and a precision that says how it is printed. These tests
pin the model itself: construction, display, the mapping from the pipeline's
claim dicts, JSON, the set and its matching, and the label vocabulary.

The claims below come from the pipeline's own producers wherever one can be
called without a model, so a change to a producer that the mapping cannot read
shows up here and not in a client's document.
"""
from __future__ import annotations

import ast
import json
import os
import sys
from decimal import Decimal

import pytest

from app.figures import labels
from app.figures import model as M
from app.figures.model import (
    Figure, FigureSet, Proposal, Reference, TheirsSource, Working,
    as_json, display, display_number, from_claim, from_json, tag_word, to_claim,
)
from app.pipeline import capacity, registry as R

D = Decimal
PROPOSED = "consultant_proposed \u2014 client approval required"
FIGURES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           "app", "figures")


# -- builders ---------------------------------------------------------------

def theirs(id_="CF-01", value="22", unit="USD", precision=0, period=None, quote="I charge $22 a class"):
    return Figure(id_, D(value), unit, period, "theirs",
                  TheirsSource(turn=1, field="What do you charge a class?", quote=quote, file=None, cell=None),
                  precision)


def derived(id_="DV-01", value="44928", unit="USD", precision=0, period="year"):
    return Figure(id_, D(value), unit, period, "derived",
                  Working(inputs=("CF-01",), op="mul", text="24 x 36 x 52"), precision)


def ours(id_="PL-01", value="6", unit="weeks", precision=0):
    return Figure(id_, D(value), unit, None, "ours", Proposal(note="six weeks for the pilot"), precision)


def reference(id_="RF-01", value="38.7", unit="percent", precision=1):
    return Figure(id_, D(value), unit, "year", "reference",
                  Reference(publication="Industry survey", year=2024, population="studios, US",
                            url="https://example.org/survey"), precision)


def claims_from_producers():
    """CF, DV, TB, SA, SI from registry's own producers; CAP from capacity;
    CE as evidence.extract builds it (a cell citation in a file)."""
    cf = R.client_fact_claims(
        [{"question": "What do you charge a class?",
          "answer": "I charge $22 a class, about 25% are no-shows, 12 reformers"}],
        ["We run six classes a day for 8 hrs a week"])
    dv = R.derived_claims({
        "lines": [{"arithmetic_verified": True, "annual": "$44,928 a year",
                   "arithmetic": "24 classes x $36 x 52", "item": "cost of no-shows"}],
        "scenarios": [{"name": "conservative", "assumption": "recovers 25% of no-shows",
                       "impact": "$11,232 a year", "impact_verified": True}]})
    cap = capacity.as_claims({"shape": "weekly_grid", "unit_plural": "classes",
                              "derived": [{"key": "CAP-01", "value": 144, "label": "classes a week",
                                           "working": "6 x 4 x 6"}]})
    ce = [{"id": "CE-01", "type": "client_fact", "value": 38, "unit": "", "time_basis": "week",
           "population": "n/a", "scope": "engagement", "phase": "all",
           "provenance": "client_input", "approval_status": "client_stated",
           "source": "bookings.xlsx \u00b7 Sheet1 \u00b7 B7", "allowed_sections": ["*"],
           "text": "classes taught last week", "origin": "file", "cell": "B7", "file": "bookings.xlsx"}]
    return {c["id"]: c for c in cf + dv + cap + ce}


def claim(**over):
    base = {"id": "X-01", "type": "client_fact", "value": 5.0, "unit": "count", "time_basis": "n/a",
            "population": "n/a", "scope": "engagement", "phase": "all", "provenance": "client_input",
            "approval_status": "client_stated", "source": "client brief", "allowed_sections": ["*"],
            "text": "five"}
    base.update(over)
    return base


def registry_errors(c):
    return R.validate_registry({"claims": [c], "monthly_identity": R.MONTHLY_IDENTITY})


# -- construction ------------------------------------------------------------

@pytest.mark.parametrize("bad", [22.0, 22, "22", None])
def test_value_must_be_a_decimal(bad):
    with pytest.raises(TypeError):
        Figure("X", bad, "USD", None, "theirs",
               TheirsSource(None, None, "q", None, None), 0)


def test_float_is_refused_even_when_it_would_be_exact():
    with pytest.raises(TypeError):
        Figure("X", 0.5, "USD", None, "theirs", TheirsSource(None, None, "q", None, None), 1)


def test_non_finite_value_is_refused():
    for bad in ("NaN", "Infinity"):
        with pytest.raises(ValueError):
            Figure("X", D(bad), "count", None, "derived", Working((), "mul", "t"), 0)


def test_precision_must_be_an_int():
    for bad in (1.0, True, "1", None):
        with pytest.raises(TypeError):
            Figure("X", D("1"), "count", None, "derived", Working((), "mul", "t"), bad)


def test_kind_and_source_must_agree():
    t = TheirsSource(None, None, "q", None, None)
    w = Working((), "mul", "t")
    p = Proposal("n")
    r = Reference("p", 2024, "pop", "u")
    for kind, src in (("theirs", w), ("derived", t), ("ours", r), ("reference", p)):
        with pytest.raises(ValueError):
            Figure("X", D("1"), "count", None, kind, src, 0)
    with pytest.raises(ValueError):
        Figure("X", D("1"), "count", None, "estimated", p, 0)


def test_a_theirs_or_reference_figure_cannot_hold_digits_it_would_not_print():
    # theirs prints at its precision with no "~", so it may not hide digits
    with pytest.raises(ValueError):
        theirs(value="22.5", precision=0)
    with pytest.raises(ValueError):
        reference(value="38.74", precision=1)
    # derived and ours may: they print with "~"
    assert display(derived(value="22.5", unit="count", precision=0)) == "~23"


def test_figure_is_frozen_and_hashable():
    f = theirs()
    with pytest.raises(Exception):
        f.value = D("23")
    assert hash(f) == hash(theirs())


# -- display -----------------------------------------------------------------

def test_theirs_prints_at_its_precision_with_the_dollar_sign():
    assert display(theirs(value="22")) == "$22"
    assert display(theirs(value="1250.5", precision=2)) == "$1,250.50"
    assert display(theirs(value="25", unit="percent")) == "25%"
    assert display(theirs(value="12", unit="count")) == "12"
    assert display(theirs(value="1250", unit="count")) == "1,250"
    assert display(theirs(value="4700", unit="count", precision=-2)) == "4,700"


def test_derived_that_rounding_changed_shows_a_tilde():
    assert display(derived(value="44928", unit="count", precision=-3)) == "~45,000"
    assert display(derived(value="44928", unit="USD", precision=-3)) == "~$45,000"
    assert display(derived(value="33.333", unit="percent", precision=0)) == "~33%"
    assert display(derived(value="2.5", unit="count", precision=0)) == "~3"      # half rounds up
    assert display(derived(value="-0.4", unit="count", precision=0)) == "~0"     # no minus on zero


def test_derived_that_rounding_left_alone_shows_no_tilde():
    assert display(derived(value="864", unit="count", precision=0)) == "864"
    assert display(derived(value="44928", unit="USD", precision=0)) == "$44,928"
    assert display(derived(value="45000", unit="count", precision=-3)) == "45,000"
    assert display(derived(value="3692.71", unit="USD", precision=2)) == "$3,692.71"
    assert display(derived(value="25", unit="percent", precision=0)) == "25%"


def test_ours_follows_the_same_tilde_rule_as_derived():
    assert display(ours(value="6", unit="weeks")) == "6 weeks"
    assert display(ours(value="6.4", unit="weeks")) == "~6 weeks"
    assert display(ours(value="1", unit="weeks")) == "1 week"


def test_reference_prints_exactly_and_never_gets_a_tilde():
    assert display(reference()) == "38.7%"
    assert display(reference(value="1200000", unit="USD", precision=-3)) == "$1,200,000"


def test_negative_numbers_put_the_sign_before_the_symbol():
    assert display(derived(value="-5", unit="USD")) == "-$5"
    assert display(derived(value="-5.4", unit="USD", precision=0)) == "~-$5"


def test_unknown_unit_prints_the_number_then_the_unit_word():
    assert display(theirs(value="12", unit="reformers")) == "12 reformers"
    assert display(theirs(value="1250", unit="deliveries")) == "1,250 deliveries"
    assert display(theirs(value="3", unit="EUR")) == "3 EUR"


# -- display_number: the number alone, for replacing a number inside a sentence --

def test_display_number_keeps_symbols_and_drops_unit_words():
    assert display_number(theirs(value="22")) == "$22"
    assert display_number(theirs(value="25", unit="percent")) == "25%"
    assert display_number(derived(value="44928", unit="USD", precision=-3)) == "~$45,000"
    assert display_number(derived(value="33.333", unit="percent", precision=0)) == "~33%"
    assert display_number(derived(value="-5", unit="USD")) == "-$5"
    assert display_number(derived(value="-5.4", unit="USD", precision=0)) == "~-$5"
    assert display_number(theirs(value="1250.5", precision=2)) == "$1,250.50"
    # "6 weeks" is the number 6 and a word the sentence already holds
    assert display_number(ours(value="6", unit="weeks")) == "6"
    assert display_number(ours(value="1", unit="weeks")) == "1"
    assert display_number(ours(value="6.4", unit="weeks")) == "~6"
    assert display_number(theirs(value="12", unit="reformers")) == "12"
    assert display_number(theirs(value="3", unit="EUR")) == "3"
    assert display_number(theirs(value="1250", unit="count")) == "1,250"
    assert display_number(theirs(value="1.5", unit="weeks", precision=1)) == "1.5"


def test_display_number_without_symbols_is_the_digits_the_sign_and_the_tilde():
    assert display_number(derived(value="44928", unit="USD", precision=-3), symbols=False) == "~45,000"
    assert display_number(theirs(value="22"), symbols=False) == "22"
    assert display_number(theirs(value="1250.5", precision=2), symbols=False) == "1,250.50"
    assert display_number(theirs(value="25", unit="percent"), symbols=False) == "25"
    assert display_number(derived(value="-5.4", unit="USD", precision=0), symbols=False) == "~-5"


def test_display_number_agrees_with_display_on_every_number():
    # whatever display prints, display_number prints the same digits, sign and tilde
    import re
    for f in (theirs(), theirs(value="25", unit="percent"), derived(), derived(value="3692.71", unit="USD", precision=2),
              ours(value="6.4"), ours(value="1"), reference(), reference(value="1200000", unit="USD", precision=-3),
              derived(value="-5.4", unit="USD", precision=0), theirs(value="12", unit="reformers")):
        words = re.sub(r"[ A-Za-z]+$", "", display(f))
        assert display_number(f) == words, f


@pytest.mark.parametrize("unit", sorted(set(R._CAPACITY_CANON.values())))
def test_every_hardware_unit_the_registry_emits_prints_with_its_unit(unit):
    assert display(theirs(value="24", unit=unit)) == f"24 {unit}"
    c = claim(value=24.0, unit=unit)
    assert to_claim(from_claim(c))["unit"] == unit


@pytest.mark.parametrize("one, many", [("ms", "ms"), ("second", "seconds"), ("minute", "minutes"),
                                       ("hour", "hours"), ("day", "days"), ("week", "weeks"),
                                       ("month", "months"), ("year", "years"),
                                       ("millisecond", "milliseconds")])
def test_every_time_unit_the_registry_grammar_emits(one, many):
    assert display(theirs(value="8", unit=many)) == f"8 {many}"
    assert display(theirs(value="1", unit=one)) == f"1 {one}"
    assert display(theirs(value="1", unit=many)) == f"1 {one}"
    c = claim(value=8.0, unit=many)
    assert to_claim(from_claim(c))["unit"] == many


def test_the_time_words_match_the_registry_grammar():
    # the registry's number grammar is the source of these unit words
    for word in ("seconds", "minutes", "hours", "days", "weeks", "months", "years", "ms", "milliseconds"):
        assert R._numbers(f"it takes 8 {word}")[0][2] == word


def test_tag_words():
    assert [tag_word(k) for k in ("theirs", "derived", "ours", "reference")] == \
        ["yours", "worked out", "our estimate", "reference"]
    with pytest.raises(ValueError):
        tag_word("guessed")


# -- from_claim / to_claim ---------------------------------------------------

CORE = ("id", "value", "unit", "time_basis", "provenance", "approval_status")


@pytest.mark.parametrize("cid", ["CF-01", "CF-02", "CF-03", "CF-04", "CE-01", "DV-01", "TB-01-day",
                                 "TB-01-month", "SA-01-1", "SI-01-1", "SI-01-month", "CAP-01"])
def test_every_producer_claim_round_trips_its_core_fields(cid):
    c = claims_from_producers()[cid]
    f = from_claim(c)
    back = to_claim(f)
    for key in CORE:
        if key not in c:
            assert back[key]                  # CAP claims have no approval_status; the claim we build does
            continue
        if key == "unit" and c["unit"] == "ratio":
            assert back["unit"] == "%"        # a ratio is a fraction shown as a percent
            continue
        assert back[key] == c[key], (cid, key)
    assert registry_errors(back) == []


def test_the_value_is_a_decimal_built_from_the_floats_repr():
    f = from_claim(claim(value=0.1, unit="count"))
    assert isinstance(f.value, Decimal) and not isinstance(f.value, float)
    assert f.value == D("0.1")
    assert f.precision == 1
    # 0.1 + 0.2 in a float is 0.30000000000000004: arithmetic noise past the 15 digits
    # a float reliably holds. It is cleaned to 0.3, not shown to a client as 17 digits.
    assert from_claim(claim(value=0.30000000000000004, unit="count")).value == D("0.3")
    assert from_claim(claim(value=1.1000000000000001, unit="count")).value == D("1.1")
    assert from_claim(claim(value=61.55, unit="USD")).value == D("61.55")
    assert from_claim(claim(value=44928.0, unit="USD")).precision == 0
    assert from_claim(claim(value=1200000.0, unit="count")).precision == 0
    assert from_claim(claim(value=12, unit="count")).value == D("12")      # an int claim value


def test_a_number_with_fifteen_digits_or_fewer_survives_exactly():
    for text in ("0.123456789012345", "123456789012345", "12345.6789012345", "0.07", "61.55", "1e-07", "1e+22"):
        assert from_claim(claim(value=float(text), unit="count")).value == D(text), text
    big = from_claim(claim(value=1e22, unit="count"))
    assert big.value == D(10 ** 22) and big.precision == 0
    assert from_claim(claim(value=12, unit="count")).value == D("12")      # an int is taken as it is


@pytest.mark.parametrize("answer, shown, as_float", [("33.3%", "33.3%", 0.333), ("1.1%", "1.1%", 0.011),
                                                     ("7.7%", "7.7%", 0.077), ("64.2 percent", "64.2%", 0.642)])
def test_registry_division_noise_does_not_reach_the_display(answer, shown, as_float):
    # registry._numbers divides the typed number by 100.0, which leaves
    # 0.33299999999999996 for 33.3 and 0.011000000000000001 for 1.1
    [c] = R.client_fact_claims([{"question": "What share of orders arrive late?", "answer": answer}], [])
    if answer in ("33.3%", "1.1%"):
        assert c["value"] != as_float                    # the noise really is in the claim
    f = from_claim(c)
    assert display(f) == shown
    assert f.unit == "percent" and f.precision == 1
    assert to_claim(f)["value"] == as_float


def test_cf_maps_to_theirs_with_the_question_and_the_text():
    f = from_claim(claims_from_producers()["CF-01"])
    assert f.kind == "theirs" and f.unit == "USD" and f.value == D("22")
    assert f.source == TheirsSource(turn=None, field="What do you charge a class?",
                                    quote="I charge $22 a class, about 25% are no-shows, 12 reformers",
                                    file=None, cell=None)
    assert display(f) == "$22"
    brief = from_claim(claims_from_producers()["CF-04"])
    assert brief.source.field is None and brief.source.file is None


def test_ce_maps_to_theirs_with_file_sheet_and_cell():
    c = claims_from_producers()["CE-01"]
    f = from_claim(c)
    assert f.kind == "theirs" and f.source.file == "bookings.xlsx" and f.source.cell == "B7"
    assert f.source.field == "Sheet1"
    assert f.period == "week" and f.unit == ""
    back = to_claim(f)
    assert back["source"] == c["source"] and back["file"] == "bookings.xlsx" and back["cell"] == "B7"
    assert back["origin"] == "file" and back["text"] == c["text"]


def test_dv_maps_to_derived_with_the_claims_source_as_its_working():
    c = claims_from_producers()["DV-01"]
    f = from_claim(c)
    assert f.kind == "derived" and f.unit == "USD" and f.period == "year"
    assert f.source.text == "financial_model.lines[0]: 24 classes x $36 x 52"
    assert f.source.op == "derived_value"
    assert display(f) == "$44,928"
    back = to_claim(f)
    assert back["type"] == "derived_value" and back["source"] == c["source"]
    tb = from_claim(claims_from_producers()["TB-01-month"])
    assert tb.period == R.MONTHLY_IDENTITY and display(tb) == "$3,692.71"
    assert to_claim(tb)["type"] == "time_basis_conversion"
    assert to_claim(from_claim(claims_from_producers()["SI-01-1"]))["type"] == "scenario_impact"


def test_sa_maps_to_ours_as_a_percent():
    c = claims_from_producers()["SA-01-1"]
    f = from_claim(c)
    assert f.kind == "ours" and f.unit == "percent" and f.value == D("25") and f.precision == 0
    assert display(f) == "25%"
    assert f.source == Proposal(note="25% (conservative scenario assumption)")
    back = to_claim(f)
    assert back["value"] == 0.25 and back["provenance"] == "consultant_proposed"
    assert back["approval_status"] == PROPOSED


def test_cap_claim_has_no_type_or_scope_and_still_maps():
    f = from_claim(claims_from_producers()["CAP-01"])
    assert f.kind == "derived" and f.unit == "classes" and f.period == "week"
    assert f.value == D("144") and display(f) == "144 classes"
    back = to_claim(f)
    assert back["type"] == "derived_value" and back["scope"] == "engagement" and back["phase"] == "all"
    assert registry_errors(back) == []


def test_percent_in_and_out():
    f = from_claim(claim(value=0.25, unit="%"))
    assert f.value == D("25") and f.unit == "percent" and f.precision == 0
    assert from_claim(claim(value=0.07, unit="%")).value == D("7")          # not 7.000000000000001
    g = from_claim(claim(value=0.255, unit="%"))
    assert g.value == D("25.5") and g.precision == 1 and display(g) == "25.5%"
    assert to_claim(f)["value"] == 0.25 and to_claim(f)["unit"] == "%"
    assert to_claim(g)["value"] == 0.255
    assert from_claim(claim(value=1.5, unit="%")).value == D("150")
    # percentage points and pp are not fractions: the number stays as written
    assert from_claim(claim(value=5.0, unit="pp")).value == D("5")


def test_canonical_gate_takes_its_kind_from_its_approval():
    gate = dict(provenance="canonical_gate", type="pilot_gate")
    assert from_claim(claim(approval_status="client_stated", **gate)).kind == "theirs"
    assert from_claim(claim(approval_status="machine_verified", **gate)).kind == "derived"
    assert from_claim(claim(approval_status=PROPOSED, **gate)).kind == "ours"
    # nothing said, or something unrecognised, is the least trusted kind: ours
    assert from_claim(claim(approval_status="pending", **gate)).kind == "ours"
    no_approval = claim(**gate)
    del no_approval["approval_status"]
    assert from_claim(no_approval).kind == "ours"


def test_a_rejected_claim_is_not_a_figure():
    with pytest.raises(ValueError, match="rejected"):
        from_claim(claim(provenance="canonical_gate", approval_status="rejected"))
    with pytest.raises(ValueError, match="rejected"):
        from_claim(claim(approval_status="rejected"))


def test_provenance_maps_to_kind_and_back():
    for prov, appr, kind in (("client_input", "client_stated", "theirs"),
                             ("machine_computed", "machine_verified", "derived"),
                             ("consultant_proposed", PROPOSED, "ours")):
        f = from_claim(claim(provenance=prov, approval_status=appr))
        assert f.kind == kind
        back = to_claim(f)
        assert (back["provenance"], back["approval_status"]) == (prov, appr)
        assert registry_errors(back) == []


def test_a_claim_the_mapping_cannot_read_is_refused_plainly():
    for bad in (claim(provenance="made_up"), claim(provenance=None), claim(value=None),
                claim(value="5"), claim(value=True), claim(value=float("nan")),
                claim(value=float("inf")), claim(id="")):
        with pytest.raises(ValueError):
            from_claim(bad)


def test_a_reference_figure_is_not_a_registry_claim():
    with pytest.raises(ValueError):
        to_claim(reference())


# -- JSON ----------------------------------------------------------------------

@pytest.mark.parametrize("f", [theirs(), derived(), ours(), reference(),
                               derived(value="0.1", unit="count", precision=1),
                               derived(value="1200000", unit="count", precision=-3)])
def test_json_round_trip(f):
    d = as_json(f)
    assert isinstance(d["value"], str)
    assert from_json(json.loads(json.dumps(d))) == f
    assert as_json(from_json(d)) == d


def test_json_shape():
    d = as_json(derived())
    assert d == {"id": "DV-01", "value": "44928", "unit": "USD", "period": "year", "kind": "derived",
                 "source": {"inputs": ["CF-01"], "op": "mul", "text": "24 x 36 x 52"}, "precision": 0}
    assert as_json(theirs())["source"] == {"turn": 1, "field": "What do you charge a class?",
                                           "quote": "I charge $22 a class", "file": None, "cell": None}
    assert as_json(ours())["source"] == {"note": "six weeks for the pilot"}
    assert as_json(reference())["source"] == {"publication": "Industry survey", "year": 2024,
                                              "population": "studios, US", "url": "https://example.org/survey"}
    assert as_json(derived(value="1200000", unit="count", precision=-3))["value"] == "1200000"


def test_from_json_refuses_a_malformed_figure_plainly():
    good = as_json(theirs())
    for bad in ("nope", {}, {**good, "value": 22.0}, {**good, "value": "abc"}, {**good, "kind": "guessed"},
                {**good, "source": {"note": "x"}}):
        with pytest.raises(ValueError):
            from_json(bad)


# -- FigureSet -----------------------------------------------------------------

def test_set_keeps_insertion_order_and_looks_up_by_id():
    a, b, c = theirs("A"), derived("B"), ours("C")
    fs = FigureSet([a, b])
    fs.add(c)
    assert [f.id for f in fs] == ["A", "B", "C"] and len(fs) == 3
    assert fs.get("B") is b and fs.get("nope") is None
    assert "A" in fs and "nope" not in fs


def test_set_refuses_two_different_figures_with_one_id_but_accepts_a_repeat():
    fs = FigureSet([theirs("A")])
    fs.add(theirs("A"))                    # the same figure again changes nothing
    assert len(fs) == 1
    with pytest.raises(ValueError):
        fs.add(theirs("A", value="23"))


def test_by_kind_and_counts():
    fs = FigureSet([theirs("A"), theirs("B"), derived("C"), ours("D")])
    assert [f.id for f in fs.by_kind("theirs")] == ["A", "B"]
    assert fs.by_kind("reference") == []
    assert fs.counts() == {"theirs": 2, "derived": 1, "ours": 1, "reference": 0}
    assert list(fs.counts()) == ["theirs", "derived", "ours", "reference"]


def test_match_returns_every_figure_within_half_a_percent_in_order():
    fs = FigureSet([derived("A", value="1000", unit="count"), derived("B", value="1004", unit="count"),
                    derived("C", value="1020", unit="count")])
    assert [f.id for f in fs.match(D("1002"))] == ["A", "B"]
    assert [f.id for f in fs.match(D("1000"))] == ["A", "B"]
    assert fs.match(D("1010")) == []


def test_match_tolerance_boundary_is_half_a_percent_of_the_larger():
    fs = FigureSet([derived("A", value="1000", unit="count")])
    assert fs.match(D("1005"))                    # 5 / 1005 is under half a percent
    assert fs.match(D("995"))
    assert not fs.match(D("1006"))
    assert not fs.match(D("994"))


def test_a_rounding_between_two_figures_of_different_values_matches_both():
    # match reports every candidate; refusing to pick one is the binder's job
    fs = FigureSet([derived("A", value="4720", unit="USD"), derived("B", value="4680", unit="USD")])
    assert [f.id for f in fs.match(D("4700"))] == ["A", "B"]
    assert [f.id for f in fs.match(D("4720"))] == ["A"]


def test_the_tolerance_is_relative_to_the_numbers_not_to_a_rounding_step():
    # 4,730 is 0.64% from 4,700 (outside), 4,690 is 0.21% (inside)
    fs = FigureSet([derived("A", value="4730", unit="USD"), derived("B", value="4690", unit="USD")])
    assert [f.id for f in fs.match(D("4700"))] == ["B"]


def test_match_by_the_value_as_the_figure_displays_it():
    f = derived("A", value="44928", unit="count", precision=-3)       # shows ~45,000
    fs = FigureSet([f])
    assert fs.match(D("45000")) == [f]
    assert fs.match(D("44928")) == [f]
    assert fs.match(D("44700")) == []
    # a displayed value can sit outside the tolerance and still match
    g = derived("B", value="1.4", unit="count", precision=0)           # shows ~1
    assert FigureSet([g]).match(D("1")) == [g]


def test_match_with_two_figures_in_tolerance_returns_both():
    fs = FigureSet([theirs("A", value="22"), derived("B", value="22", unit="USD"), ours("C", value="9")])
    assert [f.id for f in fs.match(D("22"))] == ["A", "B"]


def test_match_filters_by_unit_when_given():
    fs = FigureSet([theirs("A", value="25", unit="percent"), theirs("B", value="25", unit="count")])
    assert [f.id for f in fs.match(D("25"))] == ["A", "B"]
    assert [f.id for f in fs.match(D("25"), "percent")] == ["A"]
    assert fs.match(D("25"), "weeks") == []


def test_match_handles_zero_and_refuses_non_decimals():
    fs = FigureSet([derived("A", value="0", unit="count")])
    assert [f.id for f in fs.match(D("0"))] == ["A"]
    assert fs.match(D("NaN")) == []
    with pytest.raises(TypeError):
        fs.match(0.5)


# -- labels and the package boundary -----------------------------------------

def test_label_words_are_the_closed_list():
    assert labels.LABEL_WORDS == ("phase", "step", "section", "exhibit", "volume", "page", "module",
                                  "screen", "part", "appendix", "table", "slide", "footnote", "option")
    assert isinstance(labels.LABEL_WORDS, tuple)
    assert len(set(labels.LABEL_WORDS)) == len(labels.LABEL_WORDS)
    assert all(w == w.lower() and w.isalpha() for w in labels.LABEL_WORDS)


def _imports(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append(("." * node.level) + (node.module or ""))
    return names


@pytest.mark.parametrize("module", ["__init__.py", "model.py", "labels.py"])
def test_the_model_package_imports_only_the_standard_library(module):
    for name in _imports(os.path.join(FIGURES_DIR, module)):
        top = name.split(".")[0]
        assert top in sys.stdlib_module_names, f"{module} imports {name}"


def test_the_package_never_imports_the_engine():
    for fname in os.listdir(FIGURES_DIR):
        if fname.endswith(".py"):
            for name in _imports(os.path.join(FIGURES_DIR, fname)):
                assert not name.startswith("app.engine"), f"{fname} imports {name}"


def test_the_approval_and_provenance_words_match_the_registry():
    assert M._APPROVAL_PROPOSED in R.APPROVAL
    for word in ("client_input", "machine_computed", "canonical_gate", "consultant_proposed"):
        assert word in R.PROVENANCE
    assert set(M._DERIVED_CLAIM_TYPES) <= R.CLAIM_TYPES
    assert M._PROPOSED_CLAIM_TYPE in R.CLAIM_TYPES


def test_the_model_files_are_ascii():
    for module in ("__init__.py", "model.py", "labels.py"):
        text = open(os.path.join(FIGURES_DIR, module), encoding="utf-8").read()
        assert all(ord(ch) < 128 for ch in text), module


# -- money, singular words, ids, JSON depth, decimal context -------------------------

def test_money_with_a_fractional_part_shows_cents():
    assert display(theirs(value="22.5", precision=1)) == "$22.50"
    assert display(theirs(value="22.50", precision=2)) == "$22.50"
    assert display(theirs(value="22.125", precision=3)) == "$22.125"
    assert display(theirs(value="1250.5", precision=1)) == "$1,250.50"
    assert display(theirs(value="22", precision=1)) == "$22.00"
    assert display(theirs(value="22", precision=0)) == "$22"
    assert display(derived(value="-22.5", unit="USD", precision=1)) == "-$22.50"
    assert display(derived(value="22.54", unit="USD", precision=1)) == "~$22.50"
    assert display(derived(value="3692.71", unit="USD", precision=2)) == "$3,692.71"
    # only money has cents: other units show exactly the digits of their precision
    assert display(theirs(value="22.5", unit="count", precision=1)) == "22.5"
    assert display(theirs(value="33.3", unit="percent", precision=1)) == "33.3%"
    assert display(theirs(value="1.5", unit="weeks", precision=1)) == "1.5 weeks"


def test_a_unit_word_is_singular_exactly_when_the_number_shown_is_one():
    assert display(theirs(value="1", unit="weeks")) == "1 week"
    assert display(theirs(value="1", unit="week")) == "1 week"
    assert display(theirs(value="1.0", unit="weeks", precision=1)) == "1.0 week"      # any precision
    assert display(derived(value="1.04", unit="weeks", precision=0)) == "~1 week"     # the number shown is 1
    assert display(theirs(value="-1", unit="days")) == "-1 day"
    for plural in ("0", "0.5", "1.5", "2", "12"):
        assert display(theirs(value=plural, unit="weeks", precision=len(plural.partition(".")[2]))) \
            == f"{plural} weeks"


def test_a_figure_id_must_be_a_string_and_not_empty():
    w = Working((), "mul", "t")
    with pytest.raises(ValueError):
        Figure("", D("1"), "count", None, "derived", w, 0)
    with pytest.raises(TypeError):
        Figure(7, D("1"), "count", None, "derived", w, 0)


def test_a_two_decimal_quantity_is_not_refused_as_theirs():
    # the engine's Quantity defaults to two decimals; a client's cents must go through
    from app.engine.types import Quantity, UnitFamily

    q = Quantity(value=D("1250.5"), unit="USD", unit_family=UnitFamily.MONEY)
    f = Figure("CF-01", q.value, q.unit, None, "theirs",
               TheirsSource(None, "price", "$1,250.50", None, None), q.precision)
    assert display(f) == "$1,250.50"
    whole = Quantity(value=D("22"), unit="USD", unit_family=UnitFamily.MONEY)
    g = Figure("CF-02", whole.value, whole.unit, None, "theirs",
               TheirsSource(None, "price", "$22", None, None), whole.precision)
    assert display(g) == "$22.00"
    # what is refused is a value with digits the precision would drop
    with pytest.raises(ValueError):
        Figure("CF-03", D("1250.555"), "USD", None, "theirs", TheirsSource(None, None, "q", None, None), q.precision)


def _bad(figure, path, value):
    """as_json(figure) with one nested entry replaced."""
    d = json.loads(json.dumps(as_json(figure)))
    node = d
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return d


@pytest.mark.parametrize("figure, path, value", [
    (derived(), ("source", "inputs"), "CF-01"),
    (derived(), ("source", "inputs"), [1]),
    (derived(), ("source", "inputs"), None),
    (derived(), ("source", "op"), 5),
    (derived(), ("source", "text"), None),
    (reference(), ("source", "year"), "2024"),
    (reference(), ("source", "year"), 2024.5),
    (reference(), ("source", "year"), True),
    (reference(), ("source", "year"), None),
    (reference(), ("source", "url"), 5),
    (theirs(), ("source", "turn"), "1"),
    (theirs(), ("source", "turn"), True),
    (theirs(), ("source", "turn"), 1.5),
    (theirs(), ("source", "quote"), None),
    (theirs(), ("source", "field"), 3),
    (theirs(), ("source", "file"), ["a.xlsx"]),
    (ours(), ("source", "note"), 5),
    (theirs(), ("source",), None),
    (theirs(), ("source",), "from a client"),
    (theirs(), ("id",), 5),
    (theirs(), ("id",), ""),
    (theirs(), ("unit",), 5),
    (theirs(), ("period",), 5),
    (theirs(), ("kind",), 5),
    (theirs(), ("precision",), "0"),
    (theirs(), ("precision",), 0.0),
    (theirs(), ("precision",), True),
])
def test_from_json_checks_every_nested_type(figure, path, value):
    with pytest.raises(ValueError):
        from_json(_bad(figure, path, value))


def test_from_json_accepts_the_nulls_the_model_allows():
    assert from_json(_bad(theirs(), ("source", "turn"), None)).source.turn is None
    assert from_json(_bad(theirs(), ("period",), None)).period is None
    for key in ("source", "unit", "value", "kind", "id", "precision", "period"):
        missing = json.loads(json.dumps(as_json(theirs())))
        del missing[key]
        with pytest.raises(ValueError):
            from_json(missing)


def test_match_does_not_depend_on_the_callers_decimal_context():
    import decimal

    fs = FigureSet([derived("A", value="1000", unit="count")])
    with decimal.localcontext() as ctx:
        ctx.prec = 1
        # at one digit, a gap of 5.1 would round to 5 and the figure would match
        assert fs.match(D("1005.1")) == []
        assert [f.id for f in fs.match(D("1005"))] == ["A"]
    with decimal.localcontext() as ctx:
        ctx.prec = 2
        # and the bound 5.0251 must not be cut to 5.0, which would refuse a gap of 5.02
        assert [f.id for f in fs.match(D("1005.02"))] == ["A"]
