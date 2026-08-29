"""A percentage written as a word, and whose units the gate randomises.

Two defects the worldwide AI-datacentre engagement (production run 20) exposed
in the one canonical gate.

ONE -- the brief said "rise to at least 90 percent". The gate stored
target_value 0.9 with unit "% relative" and rendered "must be at least 0.9%":
a HUNDREDFOLD error in the number the pilot is decided on. _PP already read the
word form ("percentage points", "pp"); _PCT read only the symbol, so the word
form fell through to the model's own numeric field -- which holds the ratio --
and was then printed with a percent sign. Nothing caught it, because the
conflict check compares the parsed value against that same field, and after a
failed parse they are one object.

TWO -- the assignment sentence randomised "comparable eligible ORDERS" and the
denominator counted "eligible DELIVERIES". Both were hardcoded, so a delivery
client's vocabulary went into every engagement that followed; the datacentre
gate inherited both though that estate has neither. It survived review because
the hardcoded default matched the one client it was written for.
"""
import pytest

from app.pipeline.pilot_gate import (
    _plural, assignment_sentence, assignment_unit, gate_errors, normalize_gate,
)

ICARRY_POP = ("All delivery orders placed for individuals via the iCARRY mobile app "
              "in the pilot geography, excluding business clients")
COUNCIL_POP = "Every council question the Masar team asks during the pilot"


def gate(**over):
    raw = {"target": "rise to at least 90 percent (proposed — client approval required)",
           "target_value": 0.9, "change_kind": "relative", "duration": "3 weeks",
           "primary_metric": "Share of verdicts rated at least as good as control",
           "population": COUNCIL_POP, "numerator": "verdicts rated at least as good",
           "geography": "not applicable",
           "control_method_stated": "Each question is randomly assigned 50/50 to treatment or control",
           "guardrails": ["latency"]}
    raw.update(over)
    return normalize_gate(raw)


# ── ONE: a percentage may be written as a word ───────────────────────────────

@pytest.mark.parametrize("text", [
    "rise to at least 90 percent", "rise to at least 90 per cent",
    "rise to at least 90percent", "rise to at least 90 pct", "rise to at least 90%",
])
def test_the_word_and_the_symbol_are_the_same_quantity(text):
    assert gate(target=text)["target_value"] == 90.0


def test_the_rendered_formula_is_not_a_hundredth_of_the_target():
    g = gate()
    assert "90%" in g["target_formula"]
    assert "0.9%" not in g["target_formula"], "the ratio was printed as a percentage"


def test_the_model_ratio_is_reconciled_against_the_text_not_preferred_over_it():
    """0.9 and "90 percent" are the same number written two ways. That is a
    reconciliation, not a contradiction -- and the TEXT governs."""
    g = gate()
    assert g["target_value"] == 90.0
    assert g["target_value_field"] == 0.9
    assert g["target_value_reconciled"] is True
    assert g["target_value_conflict"] is False


def test_percentage_points_still_belong_to_the_other_rule():
    """"percent" must not swallow "percentage points" -- \\b already fails
    inside "percentage", and _PP is tested first."""
    g = gate(target="a 5 percentage-point rise", change_kind="percentage_point")
    assert g["target_value"] == 5.0
    assert g["target_unit"] == "percentage points"


def test_a_genuine_contradiction_is_still_a_conflict():
    """Run 47: text "5 percentage-point rise", field 0.93 = the resulting rate."""
    g = gate(target="a 5 percentage-point rise", target_value=0.93, change_kind="percentage_point")
    assert g["target_value_conflict"] is True


# ── ONE(b): a failed parse must announce itself ──────────────────────────────

def test_a_number_in_the_text_that_cannot_be_parsed_is_recorded():
    g = gate(target="rise to at least 90 basis widgets", change_kind="relative", target_value=0.9)
    assert g["target_value_from_text"] is False
    assert any("could not parse" in e for e in gate_errors(g))


def test_a_parsed_target_raises_nothing():
    assert not any("could not parse" in e for e in gate_errors(gate()))


def test_a_gate_stored_before_this_check_is_not_condemned_by_it():
    """The flag is written by normalize_gate, so a gate already on disk has no
    opinion about it. Reading its ABSENCE as a failed parse took request 53 --
    a delivered package -- from clean to two findings. No evidence is not
    evidence of a defect."""
    old = dict(gate())
    del old["target_value_from_text"]
    assert not any("could not parse" in e for e in gate_errors(old))


def test_a_target_with_no_number_at_all_raises_nothing():
    g = gate(target="baseline and target to be established during week-one measurement",
             target_value=None)
    assert not any("could not parse" in e for e in gate_errors(g))


# ── TWO: the unit belongs to the engagement ──────────────────────────────────

@pytest.mark.parametrize("population,expected", [
    (ICARRY_POP, "orders"),
    (COUNCIL_POP, "questions"),
    ("All first-attempt deliveries to new customers", "deliveries"),
    ("Every support ticket raised during the pilot", "tickets"),
    ("All patient enquiries received in the window", "enquiries"),
])
def test_the_unit_comes_from_the_population(population, expected):
    assert assignment_unit({"population": population}) == expected


def test_the_fallback_names_no_client_s_business():
    """A default that says "orders" puts a delivery company's vocabulary into a
    hospital's pilot. The neutral word is the only safe one."""
    for pop in ("", None, "   "):
        assert assignment_unit({"population": pop}) == "units"
    assert assignment_unit(None) == "units"
    assert assignment_unit({}) == "units"


def test_the_delivery_engagement_is_word_for_word_unchanged():
    """Request 53 is a delivered package. Deriving the unit must reproduce its
    sentence exactly, not merely something equivalent."""
    assert assignment_sentence({"population": ICARRY_POP}) == (
        "Comparable eligible orders are randomized 50/50 between treatment and control — "
        "the control group keeps today's process and is never drawn from another client, "
        "zone or period.")


def test_the_datacentre_engagement_stops_randomising_deliveries():
    g = gate()
    assert "questions" in g["assignment"]
    for wrong in ("orders", "deliveries"):
        assert wrong not in g["assignment"], "another engagement's vocabulary"
        assert wrong not in g["denominator"], "another engagement's vocabulary"


def test_the_denominator_counts_what_the_assignment_randomises():
    """These were two different hardcoded nouns describing one population."""
    g = gate()
    assert g["denominator"] == "eligible questions assigned to each group"
    assert assignment_unit(g) in g["assignment"]


@pytest.mark.parametrize("word,expected", [
    ("order", "orders"), ("orders", "orders"), ("enquiry", "enquiries"),
    ("batch", "batches"), ("box", "boxes"), ("class", "classes"), ("day", "days"),
])
def test_pluralisation(word, expected):
    assert _plural(word) == expected
