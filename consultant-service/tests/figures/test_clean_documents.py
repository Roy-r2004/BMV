"""What a client reads holds no internal ids, and a labelled proposal is not an orphan."""
from decimal import Decimal

import pytest

from app.figures import law
from app.figures.model import Figure, FigureSet, Proposal, TheirsSource


def theirs(id_, value, unit):
    return Figure(id_, Decimal(value), unit, None, "theirs", TheirsSource(None, None, "q", None, None), 0)


KNOWN = FigureSet([theirs("T4-1", "20", "percent"), theirs("T8-3", "2000", "hours"),
                   Figure("TH-pool-38", Decimal("30"), "minutes", None, "ours", Proposal(note="a proposal"), 0)])


def check(text):
    with law.scope(KNOWN, where="Volume I", request_id=None) as s:
        out = law.check(text)
        found = list(s._found)
    return out, found


@pytest.mark.parametrize("before,after", [
    ("taking a 20% (T4-1) commission", "taking a 20% commission"),
    ("hours (T8-3), a clear benchmark", "hours, a clear benchmark"),
    ("a cut [CF-07, CE-02] of it", "a cut of it"),
    ("exceeds the limit (TH-daily-pilot-review-and-escalat-15) today", "exceeds the limit today"),
    ("the price (F-main_problem-1)", "the price"),
])
def test_internal_ids_never_print(before, after):
    assert check(before)[0] == after


def test_a_threshold_written_as_its_id_prints_its_value():
    assert "30" in check("within TH-pool-38 minutes")[0] and "TH-" not in check("within TH-pool-38 minutes")[0]


def test_a_threshold_id_before_its_value_is_dropped():
    assert check("the price at TH-pool-38: 20% today")[0] == "the price at 20% today"


def test_ordinary_words_with_hyphens_and_numbers_are_left_alone():
    text = "the Covid-19 rules and a B2B-only pilot"
    assert check(text)[0] == text


@pytest.mark.parametrize("text", [
    "within 3 working days (proposed — client approval required)",
    "a maximum of 7 times (proposed — client approval required)",
    "target: 95% within (proposed — client approval required) 5 minutes",
])
def test_a_number_marked_as_proposed_is_not_an_orphan(text):
    assert check(text)[1] == []


@pytest.mark.parametrize("text", ["we will earn 19,800 AED (proposed \u2014 client approval required)",
                                  "a saving of $900 (proposed \u2014 client approval required)",
                                  "worth 40 dirhams (proposed \u2014 client approval required)"])
def test_the_label_never_excuses_money(text):
    assert len(check(text)[1]) == 1


def test_half_a_label_excuses_nothing():
    assert [f.number for f in check("within 37 calls (proposed)")[1]] == ["37"]


def test_a_number_with_no_label_is_still_a_finding():
    assert [f.number for f in check("losing 37 calls a day")[1]] == ["37"]


def test_a_label_further_along_the_sentence_does_not_excuse_a_number():
    found = check("we lost 37 calls last week and the new response time target is agreed separately (proposed — client approval required)")[1]
    assert [f.number for f in found] == ["37"]
