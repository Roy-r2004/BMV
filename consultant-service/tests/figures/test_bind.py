"""Binding and sentence cleaning (Step 2, Task 3).

`bind` puts a figure's own value where the model wrote a number it matches, and
leaves a number it cannot place exactly alone, reporting it. `clean_sentences`
drops each sentence that still holds such a number. `segments` hands the web the
bound text in pieces, each bound number carrying its figure's id.

Review Focus 1 (a rounding near two figures of different values binds to
neither) and Review Focus 4 (25% binds to a percent figure stored as 0.25) are
pinned here.

Every non-ASCII character below is written as an escape so the file stays ASCII.
"""
from __future__ import annotations

import time
from decimal import Decimal

import pytest

from app.figures import bind as B
from app.figures import read
from app.figures.bind import BindResult, UnresolvedToken, bind, clean_sentences, segments
from app.figures.model import (
    Figure, FigureSet, Proposal, Reference, TheirsSource, Working, display_number, from_claim,
)
from app.figures.read import Mention, mentions

D = Decimal


# -- builders ------------------------------------------------------------------

def _digits_after_point(value: str) -> int:
    return max(0, -D(value).as_tuple().exponent)


def fig(kind: str, fid: str, value: str, unit: str = "", precision: int | None = None,
        period: str | None = None) -> Figure:
    p = _digits_after_point(value) if precision is None else precision
    source = {
        "theirs": TheirsSource(turn=1, field=None, quote=f"{value} {unit}", file=None, cell=None),
        "derived": Working(inputs=(), op="mul", text="worked out"),
        "ours": Proposal(note="we propose it"),
        "reference": Reference(publication="Survey", year=2024, population="studios", url="https://example.org"),
    }[kind]
    return Figure(id=fid, value=D(value), unit=unit, period=period, kind=kind, source=source, precision=p)


def theirs(fid, value, unit="", precision=None, period=None):
    return fig("theirs", fid, value, unit, precision, period)


def derived(fid, value, unit="", precision=None, period=None):
    return fig("derived", fid, value, unit, precision, period)


def ours(fid, value, unit="", precision=None, period=None):
    return fig("ours", fid, value, unit, precision, period)


def fs(*figures: Figure) -> FigureSet:
    return FigureSet(figures)


def assert_spans_hold(result: BindResult) -> None:
    """Every unresolved record points at its own text inside the bound text."""
    for u in result.unresolved:
        assert result.text[u.start:u.end] == u.text, u


# -- a rounded number prints the figure's own value (Task 3 brief) -------------------

def test_a_rounded_mention_prints_the_figures_own_display_and_keeps_the_hedge_word():
    known = fs(derived("DV-01", "44928", "USD", precision=-3))
    r = bind("We lose about $45,000 a year.", known)
    assert r.text == "We lose about $45,000 a year."     # "about" says it is rounded; no second "~"
    assert [f.id for f in r.bound] == ["DV-01"]
    assert r.unresolved == []


def test_the_exact_value_of_a_rounded_figure_is_kept_as_written_and_a_rounding_needs_a_cue():
    known = fs(derived("DV-01", "44928", "USD", precision=-3))
    r = bind("That is $44,928 a year.", known)
    assert r.text == "That is $44,928 a year." and [f.id for f in r.bound] == ["DV-01"]    # never less than was said
    assert bind("That is about $45,000 a year.", known).text == "That is about $45,000 a year."
    assert bind("That is ~$45,000 a year.", known).text == "That is ~$45,000 a year."
    _stays_unresolved("That is $45,000 a year.", known, "$45,000")                    # a rounding, with nothing to say so


def test_a_figure_that_displays_with_no_tilde_prints_with_none():
    known = fs(derived("DV-02", "864", "classes", precision=0))
    r = bind("about 864 classes", known)
    assert r.text == "about 864 classes"                  # nothing to double: the hedge stays
    assert [f.id for f in r.bound] == ["DV-02"]


# -- Review Focus 1: two figures of different values within tolerance -----------------

def test_a_rounding_near_two_figures_of_different_values_binds_to_neither():
    known = fs(theirs("CF-01", "4720", "USD"), derived("DV-01", "4680", "USD"))
    text = "About $4,700 a month goes missing."
    r = bind(text, known)
    assert r.text == text                                 # byte for byte, hedge included
    assert r.bound == []
    assert [m.text for m in r.unresolved] == ["$4,700"]
    assert isinstance(r.unresolved[0], Mention)
    assert_spans_hold(r)


def test_the_same_rounding_near_only_one_derived_figure_binds_to_it():
    known = fs(derived("DV-01", "4720", "USD"))
    r = bind("About $4,700 a month goes missing.", known)
    assert r.text == "About $4,720 a month goes missing."   # the model rounded a number we worked out
    assert [f.id for f in r.bound] == ["DV-01"]


def test_the_same_rounding_near_only_one_theirs_figure_is_unresolved():
    known = fs(theirs("CF-01", "4720", "USD"))
    text = "About $4,700 a month goes missing."
    r = bind(text, known)
    assert r.text == text and r.bound == []               # the model altered the client's own number
    assert [m.text for m in r.unresolved] == ["$4,700"]


def test_two_figures_of_different_values_do_not_bind_in_either_order():
    a, b = theirs("CF-01", "4720", "USD"), derived("DV-01", "4680", "USD")
    for known in (fs(a, b), fs(b, a)):
        assert bind("$4,700", known).bound == []


def test_a_mention_that_matches_nothing_is_unresolved_and_left_alone():
    r = bind("We expect $9,999 next year.", fs(theirs("CF-01", "22", "USD")))
    assert r.text == "We expect $9,999 next year."
    assert [m.text for m in r.unresolved] == ["$9,999"]
    assert r.bound == []


# -- equal figures: the most trusted kind wins ------------------------------------------

_ORDER = ("theirs", "derived", "reference", "ours")


@pytest.mark.parametrize("better, worse", [(_ORDER[i], _ORDER[j]) for i in range(4) for j in range(i + 1, 4)])
def test_equal_figures_resolve_to_the_most_trusted_kind(better, worse):
    a, b = fig(better, "A-1", "22", "USD"), fig(worse, "B-1", "22", "USD")
    for known in (fs(a, b), fs(b, a)):                    # the order they were added makes no difference
        r = bind("It costs $22.", known)
        assert [f.id for f in r.bound] == ["A-1"], (better, worse)
        assert r.unresolved == []


def test_equal_figures_of_one_kind_resolve_to_the_lowest_id_whatever_the_order_added():
    for known in (fs(theirs("CF-02", "22", "USD"), theirs("CF-01", "22", "USD")),
                  fs(theirs("CF-01", "22", "USD"), theirs("CF-02", "22", "USD"))):
        assert [f.id for f in bind("It costs $22.", known).bound] == ["CF-01"]


def test_one_value_in_two_units_is_one_answer_when_no_noun_tells_them_apart():
    # both print "12": nothing the page shows would differ, so the number binds, to the lowest id
    known = fs(theirs("CF-02", "12", "reformers"), theirs("CF-01", "12", "classes"))
    r = bind("Of the 12 we start with the first.", known)
    assert r.text == "Of the 12 we start with the first." and [f.id for f in r.bound] == ["CF-01"] and r.unresolved == []
    # a noun after the number does tell them apart
    assert [f.id for f in bind("We have 12 reformers.", known).bound] == ["CF-02"]
    assert [f.id for f in bind("We run 12 classes.", known).bound] == ["CF-01"]
    # and a figure that prints the value another way is a real choice
    odd = fs(theirs("CF-01", "12", "classes"), theirs("CF-02", "12.0", "reformers"))
    _stays_unresolved("Of the 12 we start.", odd, "12")
    mixed = fs(theirs("CF-02", "12", ""), derived("DV-01", "12", "classes"))
    assert [f.id for f in bind("Of the 12 we start.", mixed).bound] == ["CF-02"]     # the more trusted kind wins
    # a time figure never takes a bare number with no time word after it
    r = bind("Of the 12 we start with the first.", fs(ours("PL-01", "12", "weeks"), theirs("CF-02", "12", "reformers")))
    assert [f.id for f in r.bound] == ["CF-02"]


# -- a theirs figure is never re-rounded -------------------------------------------------

def test_a_theirs_figure_prints_exactly_as_the_client_gave_it():
    known = fs(theirs("CF-01", "22.50", "USD"), theirs("CF-02", "1250", "USD"))
    assert bind("a class is $22.5", known).text == "a class is $22.50"
    assert bind("a class is $22.50", known).text == "a class is $22.50"


def test_a_theirs_figure_is_never_silently_corrected_to_a_near_number():
    known = fs(theirs("CF-02", "1250", "USD"))
    r = bind("Roughly $1,247 a month.", known)
    assert r.text == "Roughly $1,247 a month." and r.bound == []
    assert [m.text for m in r.unresolved] == ["$1,247"]
    assert bind("Roughly $1,250 a month.", known).bound[0].id == "CF-02"


# -- Review Focus 4: percent -----------------------------------------------------------

def _percent_claim():
    return {"id": "CF-05", "type": "client_fact", "value": 0.25, "unit": "%", "time_basis": "n/a",
            "population": "n/a", "scope": "engagement", "phase": "all", "provenance": "client_input",
            "approval_status": "client_stated", "source": "discovery: no-shows", "allowed_sections": ["*"],
            "text": "about 25% are no-shows"}


def test_25_percent_binds_to_a_claim_stored_as_a_fraction():
    known = fs(from_claim(_percent_claim()))
    r = bind("Around 25% of seats go empty.", known)
    assert r.text == "Around 25% of seats go empty."
    assert [f.id for f in r.bound] == ["CF-05"] and r.unresolved == []
    r2 = bind("Around 25 percent of seats go empty.", known)
    assert [f.id for f in r2.bound] == ["CF-05"] and r2.unresolved == []
    assert r2.text == "Around 25 percent of seats go empty."   # the unit word the model used is not touched


def test_a_percent_does_not_bind_to_the_fraction_of_the_same_digits():
    known = fs(from_claim(_percent_claim()))
    r = bind("The rate is 0.25%.", known)
    assert r.bound == [] and [m.text for m in r.unresolved] == ["0.25%"]


def test_a_percent_mention_prefers_a_percent_figure_over_a_plain_one_of_the_same_value():
    known = fs(theirs("CF-03", "25", "classes"), theirs("CF-04", "25", "percent"))
    r = bind("25% of the 25 classes", known)
    assert r.text == "25% of the 25 classes"
    assert [f.id for f in r.bound] == ["CF-04", "CF-03"]
    assert r.unresolved == []


def test_a_money_mention_prefers_a_money_figure_over_a_plain_one():
    known = fs(theirs("CF-03", "25", "classes"), theirs("CF-04", "25", "USD"))
    r = bind("$25 a class", known)
    assert [f.id for f in r.bound] == ["CF-04"]


def test_a_money_mention_does_not_bind_to_a_figure_with_no_unit():
    r = bind("a $25 fee", fs(theirs("CF-03", "25", "")))
    assert r.text == "a $25 fee" and r.bound == [] and [m.text for m in r.unresolved] == ["$25"]


def test_a_percent_mention_does_not_bind_to_a_money_figure():
    r = bind("a 25% fee", fs(theirs("CF-03", "25", "USD")))
    assert r.bound == [] and [m.text for m in r.unresolved] == ["25%"]


# -- only the number is replaced -----------------------------------------------------------

def test_a_number_word_becomes_digits_and_the_unit_word_after_it_is_kept():
    known = fs(theirs("CF-06", "12", "count"))
    _stays_unresolved("You have twelve classes today.", known, "twelve")      # a count names no noun
    known = fs(theirs("CF-06", "12", "classes"))
    assert bind("You have twelve classes today.", known).text == "You have 12 classes today."


def test_a_unit_word_after_a_digit_is_kept_and_not_repeated():
    known = fs(ours("PL-01", "6", "weeks"))
    assert bind("a pilot of six weeks", known).text == "a pilot of 6 weeks"
    assert bind("a pilot of 6 weeks", known).text == "a pilot of 6 weeks"


def test_a_rounded_estimate_gets_its_tilde_and_the_unit_word_stays_once():
    known = fs(ours("PL-01", "6.4", "weeks", precision=0))
    assert bind("a pilot of about 6 weeks", known).text == "a pilot of about 6 weeks"
    assert bind("a pilot of ~6 weeks", known).text == "a pilot of ~6 weeks"
    _stays_unresolved("a pilot of 6 weeks", known, "6")
    assert bind("a pilot of {{F:PL-01}} weeks", known).text == "a pilot of ~6 weeks"


def test_a_magnitude_letter_or_word_is_replaced_with_the_figures_digits():
    known = fs(theirs("CF-01", "10000", "USD"), theirs("CF-02", "1500000", "visits"))
    assert bind("a $10k budget", known).text == "a $10,000 budget"
    assert bind("1.5 million visits", known).text == "1,500,000 visits"


def test_the_currency_and_percent_words_the_model_used_are_kept():
    known = fs(theirs("CF-01", "35", "USD"), theirs("CF-02", "5", "percent"))
    assert bind("35 USD each", known).text == "35 USD each"
    assert bind("a 5 percentage points rise", known).text == "a 5 percentage points rise"


def test_a_negative_number_keeps_the_sign_before_the_symbol():
    known = fs(derived("DV-09", "-5", "USD"))
    assert bind("a loss of -$5", known).text == "a loss of -$5"


def test_a_range_binds_each_end_on_its_own():
    known = fs(ours("PL-01", "6", "weeks"), ours("PL-02", "8", "weeks"))
    assert bind("6-8 weeks", known).text == "6-8 weeks"
    r = bind("six to eight weeks", known)
    assert r.text == "6 to 8 weeks" and [f.id for f in r.bound] == ["PL-01", "PL-02"]
    half = bind("6-9 weeks", known)
    assert half.text == "6-9 weeks" and [m.text for m in half.unresolved] == ["9"]
    assert [f.id for f in half.bound] == ["PL-01"]


def test_a_percent_range_keeps_the_percent_sign_it_had():
    known = fs(theirs("CF-01", "10", "percent"), theirs("CF-02", "15", "percent"))
    assert bind("10-15% growth", known).text == "10-15% growth"


# -- the hedge word before a figure that carries its own tilde --------------------------------

@pytest.mark.parametrize("hedge", ["about", "around", "roughly", "approximately", "circa", "About", "ROUGHLY"])
def test_a_hedge_word_before_a_tilde_figure_stays_and_the_tilde_is_left_off(hedge):
    known = fs(derived("DV-01", "44928", "USD", precision=-3))
    assert bind(f"We lose {hedge} $45,000 a year", known).text == f"We lose {hedge} $45,000 a year"
    assert bind(f"We lose {hedge} $44,928 a year", known).text == f"We lose {hedge} $44,928 a year"   # exact: as written


def test_a_hedge_word_that_is_a_preposition_is_never_deleted():
    known = fs(derived("DV-01", "44928", "USD", precision=-3))
    text = "You asked about $45,000 in lost revenue."
    assert bind(text, known).text == text
    assert bind("We talked around $44,928 for an hour.", known).text == "We talked around $44,928 for an hour."


def test_only_the_word_right_before_is_a_hedge():
    known = fs(derived("DV-01", "44928", "USD", precision=-3))
    assert bind("about the $45,000", known).text == "about the $45,000"      # an article after a cue is still the cue
    _stays_unresolved("costs only $45,000", known, "$45,000")                  # "only" is no cue
    _stays_unresolved("thereabout $45,000", known, "$45,000")                  # not the word "about"
    assert bind("costs only $44,928", known).text == "costs only $44,928"


def test_a_tilde_the_model_wrote_is_not_doubled():
    known = fs(derived("DV-01", "44928", "USD", precision=-3))
    # a true rounding of a figure we show rounded stays as the model wrote it: the display could only say less
    assert bind("~$44,900 a year", known).text == "~$44,900 a year"
    assert bind("~ $44,900 a year", known).text == "~ $44,900 a year"
    assert bind("\u2248$44,900 a year", known).text == "\u2248$44,900 a year"
    assert bind("~$45,000 a year", known).text == "~$45,000 a year"
    assert bind("~$44,928 a year", known).text == "~$44,928 a year"


def test_a_hedge_is_kept_when_the_figure_prints_exact():
    known = fs(theirs("CF-01", "22", "USD"))
    assert bind("about $22 a class", known).text == "about $22 a class"
    assert bind("~$22 a class", known).text == "~$22 a class"


def test_a_hedge_word_before_an_unresolved_number_stays():
    r = bind("about $9,999 a year", fs(theirs("CF-01", "22", "USD")))
    assert r.text == "about $9,999 a year"


# -- tokens --------------------------------------------------------------------------------------

def test_a_token_is_replaced_by_the_figures_number():
    known = fs(theirs("CF-01", "22", "USD"), derived("DV-01", "44928", "USD", precision=-3),
               ours("PL-01", "6", "weeks"), theirs("CF-05", "25", "percent"))
    r = bind("A class is {{F:CF-01}}; that is {{F:DV-01}} a year over {{F:PL-01}} weeks at {{F:CF-05}}.", known)
    assert r.text == "A class is $22; that is ~$45,000 a year over 6 weeks at 25%."
    assert [f.id for f in r.bound] == ["CF-01", "DV-01", "PL-01", "CF-05"]
    assert r.unresolved == []


def test_a_token_matches_display_number_of_its_figure():
    f = derived("DV-01", "44928", "USD", precision=-3)
    assert bind("{{F:DV-01}}", fs(f)).text == display_number(f)


def test_an_unknown_token_is_unresolved_and_says_which_id():
    r = bind("It costs {{F:NOPE-9}} a year.", fs(theirs("CF-01", "22", "USD")))
    assert r.text == "It costs {{F:NOPE-9}} a year."
    assert r.bound == []
    assert len(r.unresolved) == 1
    u = r.unresolved[0]
    assert isinstance(u, UnresolvedToken)
    assert (u.text, u.figure_id) == ("{{F:NOPE-9}}", "NOPE-9")
    assert_spans_hold(r)


def test_the_digits_inside_a_token_are_not_a_second_mention():
    r = bind("{{F:CF-01}} and {{F:CAP-12}} and {{F:Q3-2}}", fs(theirs("CF-01", "22", "USD")))
    assert [type(u) for u in r.unresolved] == [UnresolvedToken, UnresolvedToken]
    assert [u.figure_id for u in r.unresolved] == ["CAP-12", "Q3-2"]


def test_a_numeric_id_inside_a_token_is_not_read_as_a_number():
    r = bind("see {{F:7}} and {{F:12}}", fs(theirs("12", "22", "USD")))
    assert r.text == "see {{F:7}} and $22"
    assert [type(u) for u in r.unresolved] == [UnresolvedToken] and r.unresolved[0].figure_id == "7"
    assert_spans_hold(r)


def test_a_token_takes_the_hedge_rule_too():
    known = fs(derived("DV-01", "44928", "USD", precision=-3))
    assert bind("about {{F:DV-01}} a year", known).text == "about $45,000 a year"


def test_a_token_with_spaces_inside_is_still_a_token():
    known = fs(theirs("CF-01", "22", "USD"))
    assert bind("{{ F: CF-01 }} a class", known).text == "$22 a class"


# -- times, dates, labels, and the kinds that are never rewritten -----------------------------------

def test_dates_labels_and_times_are_left_alone():
    text = "We open at 9am on 31 Oct 2025 for Phase 2 and Exhibit 2.1 in Q3."
    r = bind(text, FigureSet())
    assert r.text == text and r.bound == [] and r.unresolved == []


def test_a_time_the_client_did_not_give_is_unresolved_when_hours_are_known():
    text = "Open from 9am to 5pm."
    r = bind(text, FigureSet(), hours={9, 10, 11, 12, 13, 14, 15, 16})
    assert r.text == text
    assert [m.text for m in r.unresolved] == ["5pm"]
    assert bind(text, FigureSet(), hours={9, 17}).unresolved == []


def test_a_fraction_is_never_rewritten(monkeypatch):
    half = Mention(text="half", start=0, end=4, value=D("50"), form="fraction")
    monkeypatch.setattr(B, "mentions", lambda text: [half])
    r = bind("half of them", fs(theirs("CF-01", "50", "percent")))
    assert r.text == "half of them" and r.unresolved == []
    r = bind("half of them", FigureSet())
    assert r.text == "half of them" and r.unresolved == [half]


def test_a_real_fraction_from_the_reader_is_never_rewritten():
    if not any(m.form == "fraction" for m in mentions("a third of them")):
        pytest.skip("the reader in this checkout does not read fractions yet")
    r = bind("half of them", fs(theirs("CF-01", "50", "percent")))
    assert r.text == "half of them"
    r = bind("half of them", FigureSet())
    assert r.text == "half of them" and [m.text for m in r.unresolved] == ["half"]


def test_a_multiplier_or_an_ordinal_is_kept_as_written_when_supported_and_reported_when_not():
    known = fs(ours("PL-01", "3", ""))
    assert bind("a 3x return", known).text == "a 3x return"
    assert bind("a 3x return", known).unresolved == []
    assert bind("the 3rd phase", known).unresolved == []
    other = bind("a 7x return and the 9th time", known)
    assert other.text == "a 7x return and the 9th time"
    assert [m.text for m in other.unresolved] == ["7x", "9th"]


# -- text with nothing to bind --------------------------------------------------------------------------

_NO_NUMBERS = [
    "",
    "Hello.",
    "  spaced \t out\r\nand unicode \u00e9\u2014 text \u201cquoted\u201d  \n\n",
    "See Phase two, Q3 and CF-04.",
    "a sentence without any digits at all, e.g. this one",
]


@pytest.mark.parametrize("text", _NO_NUMBERS)
def test_a_text_without_numbers_comes_back_byte_for_byte(text):
    known = fs(theirs("CF-01", "22", "USD"))
    r = bind(text, known)
    assert r.text == text and r.bound == [] and r.unresolved == []
    assert clean_sentences(text, known) == (text, [])
    assert segments(text, known) == ([{"text": text}] if text else [])


def test_bind_result_is_frozen():
    r = bind("x", FigureSet())
    with pytest.raises(Exception):
        r.text = "y"   # type: ignore[misc]


# -- the unresolved records point into the bound text -------------------------------------------------------

def test_unresolved_positions_are_in_the_bound_text_even_after_earlier_replacements():
    known = fs(derived("DV-01", "44928", "USD", precision=-3), ours("PL-01", "6", "weeks"))
    text = "About $44,928 a year, six weeks, then $9,999 and {{F:NOPE-1}} and 77."
    r = bind(text, known)
    assert r.text == "About $44,928 a year, 6 weeks, then $9,999 and {{F:NOPE-1}} and 77."
    assert [u.text for u in r.unresolved] == ["$9,999", "{{F:NOPE-1}}", "77"]
    assert_spans_hold(r)


@pytest.mark.parametrize("text", [
    "About $44,928 a year, six weeks, then $9,999 and 77.",
    "Roughly $44,900, and {{F:DV-01}}, and {{F:XX-1}}.",
    "6-8 weeks, 9-10 weeks.",
    "No numbers here, but half of it.",
])
def test_binding_twice_changes_nothing_more(text):
    known = fs(derived("DV-01", "44928", "USD", precision=-3), ours("PL-01", "6", "weeks"),
               ours("PL-02", "8", "weeks"))
    once = bind(text, known)
    twice = bind(once.text, known)
    assert twice.text == once.text


def test_bound_lists_each_figure_once_in_order_of_first_use():
    known = fs(theirs("CF-01", "22", "USD"), ours("PL-01", "6", "weeks"))
    r = bind("$22, then six weeks, then $22 and 6 weeks.", known)
    assert [f.id for f in r.bound] == ["CF-01", "PL-01"]


# -- clean_sentences ------------------------------------------------------------------------------------------

KNOWN = fs(derived("DV-01", "44928", "USD", precision=-3), theirs("CF-01", "22", "USD"),
           theirs("CF-07", "1.5", ""), ours("PL-01", "6", "weeks"))


def test_only_the_offending_sentence_is_dropped():
    text = "We lose about $45,000 a year. The fix costs $9,999. We start in March."
    cleaned, removed = clean_sentences(text, KNOWN)
    assert cleaned == "We lose about $45,000 a year. We start in March."
    assert removed == ["The fix costs $9,999."]


def test_a_text_with_nothing_unresolved_is_just_bound():
    text = "A class is $22 for six weeks.  Done!"
    cleaned, removed = clean_sentences(text, KNOWN)
    assert cleaned == "A class is $22 for 6 weeks.  Done!" and removed == []


def test_the_first_and_the_last_sentence_can_go():
    cleaned, removed = clean_sentences("It costs $9,999. Middle one. It saves 77%.", KNOWN)
    assert cleaned == "Middle one." and removed == ["It costs $9,999.", "It saves 77%."]


def test_when_every_sentence_goes_nothing_is_left():
    cleaned, removed = clean_sentences("It costs $9,999. It saves 77%.", KNOWN)
    assert cleaned == "" and removed == ["It costs $9,999.", "It saves 77%."]


def test_a_decimal_does_not_end_a_sentence():
    cleaned, removed = clean_sentences("The ratio is 1.5 here. Then $777 appears. The end.", KNOWN)
    assert cleaned == "The ratio is 1.5 here. The end." and removed == ["Then $777 appears."]
    cleaned, removed = clean_sentences("It rose 3.5 points then fell $777. Fine.", KNOWN)
    assert cleaned == "Fine." and removed == ["It rose 3.5 points then fell $777."]


def test_e_g_and_i_e_do_not_end_a_sentence():
    cleaned, removed = clean_sentences("Costs vary, e.g. $777 for a trial. Next is fine.", KNOWN)
    assert cleaned == "Next is fine." and removed == ["Costs vary, e.g. $777 for a trial."]
    cleaned, removed = clean_sentences("Plans differ, i.e. they cost $777 each. Next is fine.", KNOWN)
    assert cleaned == "Next is fine." and removed == ["Plans differ, i.e. they cost $777 each."]


def test_a_title_abbreviation_does_not_end_a_sentence():
    cleaned, removed = clean_sentences("Dr. Smith charges $777 an hour. We agree.", KNOWN)
    assert cleaned == "We agree." and removed == ["Dr. Smith charges $777 an hour."]
    cleaned, removed = clean_sentences("Dr. Smith agrees. It costs $777.", KNOWN)
    assert cleaned == "Dr. Smith agrees." and removed == ["It costs $777."]
    cleaned, removed = clean_sentences("Ask Mrs. Jones and Prof. Lee about the 77% rate. Fine.", KNOWN)
    assert cleaned == "Fine." and len(removed) == 1


def test_a_question_and_an_exclamation_end_a_sentence():
    cleaned, removed = clean_sentences("Why pay $777? Because we say so! Fine.", KNOWN)
    assert cleaned == "Because we say so! Fine." and removed == ["Why pay $777?"]


def test_a_closing_quote_or_bracket_after_the_full_stop_stays_with_its_sentence():
    cleaned, removed = clean_sentences('He said "it costs $777." Then left. (Fine.) End.', KNOWN)
    assert cleaned == "Then left. (Fine.) End." and removed == ['He said "it costs $777."']


def test_a_sentence_ending_in_a_number_still_ends():
    cleaned, removed = clean_sentences("Each class has 12. Then $777 follows. End.", KNOWN)
    assert removed == ["Each class has 12.", "Then $777 follows."] and cleaned == "End."


def test_paragraphs_survive_a_dropped_sentence():
    text = "First paragraph, $22 a class.\n\nSecond one costs $9,999.\n\nClosing paragraph is fine."
    cleaned, removed = clean_sentences(text, KNOWN)
    assert cleaned == "First paragraph, $22 a class.\n\nClosing paragraph is fine."
    assert removed == ["Second one costs $9,999."]


def test_the_rest_of_a_paragraph_stays_when_one_of_its_sentences_goes():
    text = "Keep this. Drop $9,999 this. Keep that.\nNext line stays."
    cleaned, removed = clean_sentences(text, KNOWN)
    assert cleaned == "Keep this. Keep that.\nNext line stays."
    text = "Keep this. Drop $9,999 this.\nNext line stays."
    cleaned, removed = clean_sentences(text, KNOWN)
    assert cleaned == "Keep this.\nNext line stays."


def test_list_items_without_full_stops_are_separate_units():
    text = "- item a costs $9,999\n- item b is fine\n- item c saves 77%\n- item d is fine\n"
    cleaned, removed = clean_sentences(text, KNOWN)
    assert cleaned == "- item b is fine\n- item d is fine\n"
    assert removed == ["- item a costs $9,999", "- item c saves 77%"]


def test_a_sentence_wrapped_over_two_lines_goes_whole():
    text = "The cost is\n$9,999 a year, which hurts. Fine."
    cleaned, removed = clean_sentences(text, KNOWN)
    assert cleaned == "Fine." and removed == ["The cost is\n$9,999 a year, which hurts."]


def test_the_trailing_whitespace_of_the_text_is_kept():
    cleaned, removed = clean_sentences("Keep. Drop $9,999. \n", KNOWN)
    assert cleaned == "Keep. \n"
    assert removed == ["Drop $9,999."]


def test_an_unresolved_token_drops_its_sentence():
    cleaned, removed = clean_sentences("It is {{F:NOPE-9}} a year. Fine.", KNOWN)
    assert cleaned == "Fine." and removed == ["It is {{F:NOPE-9}} a year."]


def test_a_sentence_with_two_unresolved_numbers_is_reported_once():
    cleaned, removed = clean_sentences("It costs $9,999 or $8,888. Fine.", KNOWN)
    assert cleaned == "Fine." and removed == ["It costs $9,999 or $8,888."]


def test_the_removed_sentence_is_shown_as_bound():
    cleaned, removed = clean_sentences("A class is $22 and the fix costs $9,999. Fine.", KNOWN)
    assert removed == ["A class is $22 and the fix costs $9,999."]


def test_clean_sentences_takes_the_clients_hours():
    cleaned, removed = clean_sentences("We open at 9am. We close at 5pm.", FigureSet(), hours={9})
    assert cleaned == "We open at 9am." and removed == ["We close at 5pm."]


def test_a_cleaned_text_binds_to_itself():
    text = "We lose about $44,928 a year. The fix costs $9,999. Six weeks."
    cleaned, _ = clean_sentences(text, KNOWN)
    assert bind(cleaned, KNOWN).text == cleaned
    assert clean_sentences(cleaned, KNOWN) == (cleaned, [])


# -- segments --------------------------------------------------------------------------------------------------------

def test_segments_join_back_to_the_bound_text_exactly():
    text = "A class is $22; we lose about $44,928 a year for six weeks, not $9,999."
    segs = segments(text, KNOWN)
    assert "".join(s["text"] for s in segs) == bind(text, KNOWN).text
    assert [s for s in segs if "figure" in s] == [
        {"figure": "CF-01", "text": "$22"},
        {"figure": "DV-01", "text": "$44,928"},
        {"figure": "PL-01", "text": "6"},
    ]
    assert all(set(s) <= {"text", "figure"} and s["text"] for s in segs)


def test_segments_for_a_token():
    assert segments("{{F:CF-01}} a class", KNOWN) == [{"figure": "CF-01", "text": "$22"}, {"text": " a class"}]
    assert segments("a class: {{F:CF-01}}", KNOWN) == [{"text": "a class: "}, {"figure": "CF-01", "text": "$22"}]


def test_segments_leave_unresolved_numbers_in_plain_text():
    segs = segments("It costs $9,999 or $22.", KNOWN)
    assert segs == [{"text": "It costs $9,999 or "}, {"figure": "CF-01", "text": "$22"}, {"text": "."}]


def test_segments_for_a_range_split_between_the_ends():
    known = fs(ours("PL-01", "6", "weeks"), ours("PL-02", "8", "weeks"))
    assert segments("6-8 weeks", known) == [
        {"figure": "PL-01", "text": "6"}, {"text": "-"}, {"figure": "PL-02", "text": "8"}, {"text": " weeks"}]


def test_segments_after_a_hedge_still_join_exactly():
    segs = segments("We lose about $45,000.", KNOWN)
    assert "".join(s["text"] for s in segs) == "We lose about $45,000."
    assert segs[0] == {"text": "We lose about "}


def test_segments_of_a_text_with_one_bound_number_only():
    assert segments("$22", KNOWN) == [{"figure": "CF-01", "text": "$22"}]


# -- the module stays inside the package ------------------------------------------------------------------------------

def test_the_binder_imports_no_engine_or_pipeline_and_makes_no_float():
    import ast
    import os
    path = os.path.join(os.path.dirname(B.__file__), "bind.py")
    with open(path, encoding="utf-8") as fh:
        source = fh.read()
    assert source.isascii()
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert not any(n.startswith(("app.engine", "app.pipeline")) for n in imported)
    called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "float" not in called


# ==============================================================================================
# Controller rulings after review (units fit, value rule, ranges, hedges, structure, tokens,
# quotations, speed). Each test uses the reviewer's own input where there is one.
# ==============================================================================================

def _stays_unresolved(text, known, *texts):
    r = bind(text, known)
    assert r.text == text, r.text
    assert r.bound == []
    assert [u.text for u in r.unresolved] == list(texts)
    assert_spans_hold(r)
    return r


# -- 1. a number binds only to a figure whose unit fits it ---------------------------------------

def test_a_bare_number_is_never_rewritten_from_a_money_figure():
    _stays_unresolved("The studio is 1,000 square feet.", fs(theirs("CF-01", "1004", "USD")), "1,000")


def test_a_bare_number_binds_to_a_figure_with_no_unit_or_a_plain_unit():
    assert bind("The studio is 1,000 square feet.", fs(theirs("CF-01", "1000", ""))).text == \
        "The studio is 1,000 square feet."
    assert [f.id for f in bind("The studio is 1,000 square feet.",
                               fs(theirs("CF-01", "1000", "square feet"))).bound] == ["CF-01"]


def test_a_noun_after_a_bare_number_must_be_the_figures_unit():
    # 12.04 reformers is not 12 classes, and the module must not turn one into the other
    _stays_unresolved("We run 12 classes a week.", fs(derived("DV-01", "12.04", "reformers", precision=2)), "12")
    _stays_unresolved("We run 12 classes a week.", fs(derived("DV-01", "12.04", "GB", precision=2)), "12")
    r = bind("We run about 12 classes a week.", fs(derived("DV-01", "12.04", "classes", precision=2)))
    assert r.text == "We run about 12.04 classes a week."
    _stays_unresolved("We run 12 class slots.", fs(derived("DV-01", "12.04", "", precision=2)), "12")   # no unit: no noun


def test_days_do_not_bind_to_a_figure_in_weeks():
    _stays_unresolved("Onboarding takes 10 days.", fs(derived("DV-01", "10.03", "weeks", precision=2)), "10")


def test_days_bind_to_a_figure_in_days_and_a_time_word_may_be_a_hyphenated_adjective():
    known = fs(derived("DV-01", "10", "days"))
    assert [f.id for f in bind("Onboarding takes 10 days.", known).bound] == ["DV-01"]
    assert [f.id for f in bind("A 10-day onboarding.", known).bound] == ["DV-01"]
    _stays_unresolved("A 10-week onboarding.", known, "10")


def test_hours_do_not_bind_to_a_percent_figure():
    _stays_unresolved("We need 40 hours of cover.", fs(derived("DV-01", "39.9", "percent", precision=1)), "40")


def test_classes_do_not_bind_to_a_money_figure():
    _stays_unresolved("We run 12 classes a week.", fs(theirs("CF-01", "12.05", "USD", precision=2)), "12")


def test_units_do_not_bind_to_a_percent_figure():
    _stays_unresolved("We sold 10 units.", fs(theirs("CF-01", "10", "percent")), "10")


def test_a_count_noun_does_not_bind_to_a_figure_in_time():
    known = fs(ours("PL-01", "6", "weeks"))
    _stays_unresolved("We have 6 members.", known, "6")
    # a filler word is not agreement: only the time word itself is
    _stays_unresolved("Allow 6 or 8 weeks.", known, "6", "8")
    _stays_unresolved("The pilot lasts 6.", known, "6")


def test_a_euro_mention_binds_only_to_a_euro_figure():
    _stays_unresolved("Rent is EUR 1,000 a month", fs(theirs("CF-01", "1004", "USD")), "EUR 1,000")
    _stays_unresolved("Rent is EUR 1,000 a month", fs(theirs("CF-01", "1000", "USD")), "EUR 1,000")
    _stays_unresolved("Rent is $1,000 a month", fs(theirs("CF-01", "1000", "EUR")), "$1,000")
    _stays_unresolved("Rent is \u20ac1,000 a month", fs(theirs("CF-01", "1000", "GBP")), "\u20ac1,000")
    r = bind("Rent is EUR 1,000 a month", fs(theirs("CF-01", "1000", "EUR")))
    assert r.text == "Rent is EUR 1,000 a month" and [f.id for f in r.bound] == ["CF-01"]
    r = bind("Rent is \u20ac1,000.00 a month", fs(theirs("CF-01", "1000", "EUR")))
    assert r.text == "Rent is \u20ac1,000 a month"
    assert bind("Rent is $1,000 a month", fs(theirs("CF-01", "1000", "USD"))).bound[0].id == "CF-01"


def test_a_money_mention_with_a_sign_the_binder_does_not_know_is_unresolved():
    _stays_unresolved("Rent is XY$1,000 a month", fs(theirs("CF-01", "1000", "USD")), "XY$1,000")


def test_a_percent_figure_never_fills_a_bare_or_money_mention_and_the_reverse():
    known = fs(theirs("CF-01", "25", "percent"))
    _stays_unresolved("It is 25 now.", known, "25")
    _stays_unresolved("It is $25 now.", known, "$25")
    _stays_unresolved("It is 25% now.", fs(theirs("CF-01", "25", "USD")), "25%")


# -- 2. the value rule ---------------------------------------------------------------------------------

def test_an_exact_figure_wins_over_a_near_figure_of_a_different_value():
    for known in (fs(theirs("CF-01", "4700", "USD"), derived("DV-01", "4720", "USD")),
                  fs(derived("DV-01", "4720", "USD"), theirs("CF-01", "4700", "USD"))):
        r = bind("It is $4,700 a month.", known)
        assert r.text == "It is $4,700 a month." and [f.id for f in r.bound] == ["CF-01"]
        assert r.unresolved == []


def test_a_figure_equal_to_the_mention_beats_a_figure_that_only_displays_as_it():
    known = fs(derived("DV-01", "44928", "USD", precision=-3), theirs("CF-01", "45000", "USD"))
    r = bind("It is $45,000 a year.", known)
    assert r.text == "It is $45,000 a year." and [f.id for f in r.bound] == ["CF-01"]


def test_two_figures_that_display_alike_but_differ_stay_unresolved():
    known = fs(derived("DV-01", "44928", "USD", precision=-3), derived("DV-02", "45010", "USD", precision=-3))
    _stays_unresolved("It is $45,000 a year.", known, "$45,000")


def test_a_near_mention_is_rewritten_only_to_a_derived_or_ours_figure():
    assert bind("It is about $4,700.", fs(derived("DV-01", "4720", "USD"))).text == "It is about $4,720."
    assert bind("It is about $4,700.", fs(ours("PL-01", "4720", "USD"))).text == "It is about $4,720."
    _stays_unresolved("It is about $4,700.", fs(theirs("CF-01", "4720", "USD")), "$4,700")
    ref = fig("reference", "RF-01", "4720", "USD")
    _stays_unresolved("It is about $4,700.", fs(ref), "$4,700")
    _stays_unresolved("It is $4,700.", fs(derived("DV-01", "4720", "USD")), "$4,700")      # a rounding needs its cue


def test_near_equal_figures_of_two_kinds_follow_the_most_trusted_one():
    # the client's own 4,720 and our 4,720: the model altered the client's number
    _stays_unresolved("It is about $4,700.", fs(derived("DV-01", "4720", "USD"), theirs("CF-01", "4720", "USD")), "$4,700")
    # a derived and a reference of one value: derived is the more trusted, so it may be rewritten
    r = bind("It is about $4,700.", fs(fig("reference", "RF-01", "4720", "USD"), derived("DV-01", "4720", "USD")))
    assert r.text == "It is about $4,720." and [f.id for f in r.bound] == ["DV-01"]


# -- 3. a range's ends take their shape from the whole range ------------------------------------------------

def test_a_percent_range_has_two_percent_ends():
    known = fs(theirs("CF-01", "10", "USD"), theirs("CF-02", "15", "percent"))
    r = bind("Churn 10-15% a year.", known)
    assert r.text == "Churn 10-15% a year."
    assert [f.id for f in r.bound] == ["CF-02"] and [u.text for u in r.unresolved] == ["10"]
    known = fs(theirs("CF-01", "10", "classes"), theirs("CF-02", "15", "percent"))
    assert [u.text for u in bind("Churn 10-15% a year.", known).unresolved] == ["10"]
    both = fs(theirs("CF-01", "10", "percent"), theirs("CF-02", "15", "percent"))
    assert bind("Churn 10-15% a year.", both).unresolved == []


def test_a_money_range_has_two_money_ends():
    known = fs(theirs("CF-01", "20", "USD"), theirs("CF-02", "30", "classes"))
    r = bind("Costs $20-30 a class.", known)
    assert r.text == "Costs $20-30 a class."
    assert [f.id for f in r.bound] == ["CF-01"] and [u.text for u in r.unresolved] == ["30"]
    known = fs(theirs("CF-01", "20", "USD"), theirs("CF-02", "30", "percent"))
    assert [u.text for u in bind("Costs $20-30 a class.", known).unresolved] == ["30"]
    both = fs(theirs("CF-01", "20", "USD"), theirs("CF-02", "30", "USD"))
    assert bind("Costs $20-30 a class.", both).unresolved == []
    euros = fs(theirs("CF-01", "20", "EUR"), theirs("CF-02", "30", "USD"))
    assert [u.text for u in bind("Costs \u20ac20-30 a class.", euros).unresolved] == ["30"]


def test_a_range_in_words_takes_the_unit_word_after_its_last_end():
    known = fs(ours("PL-01", "6", "weeks"), ours("PL-02", "8", "weeks"))
    assert bind("Allow 6 to 8 weeks.", known).unresolved == []
    r = bind("Allow 6 to 8 days.", known)
    assert [u.text for u in r.unresolved] == ["6", "8"]


# -- 4. hedge words are never deleted -------------------------------------------------------------------------

def test_the_reviewers_hedge_sentence_comes_back_unchanged():
    known = fs(derived("DV-01", "44928", "USD", precision=-3))
    assert bind("You asked about $45,000 in lost revenue.", known).text == "You asked about $45,000 in lost revenue."


def test_a_hedged_figure_prints_without_a_tilde_and_an_unhedged_one_with():
    known = fs(derived("DV-01", "44928", "USD", precision=-3))
    assert bind("It is around $45,000.", known).text == "It is around $45,000."
    assert bind("It is ~$45,000.", known).text == "It is ~$45,000."
    assert bind("It is around $44,928.", known).text == "It is around $44,928."     # exact: as written
    _stays_unresolved("It is $45,000.", known, "$45,000")
    assert bind("It is {{F:DV-01}}.", known).text == "It is ~$45,000."


# -- 5. paragraphs and structure --------------------------------------------------------------------------------

K5 = fs(theirs("CF-01", "40", "USD"), theirs("CF-02", "12", "reformers"))


def test_a_dropped_list_item_never_merges_the_paragraph_after_it_into_the_list():
    text = "- Classes cost $40.\n- Rent is $999.\n\nYou have 12 reformers."
    cleaned, removed = clean_sentences(text, K5)
    assert cleaned == "- Classes cost $40.\n\nYou have 12 reformers."
    assert removed == ["- Rent is $999."]


def test_a_dropped_item_after_a_paragraph_keeps_the_blank_line_before_the_list():
    cleaned, removed = clean_sentences("You have 12 reformers.\n\n- Rent is $999.\n- Classes cost $40.\n", K5)
    assert cleaned == "You have 12 reformers.\n\n- Classes cost $40.\n"
    assert removed == ["- Rent is $999."]


def test_a_dropped_paragraph_between_two_paragraphs_leaves_one_break():
    cleaned, removed = clean_sentences("You have 12 reformers.\n\nRent is $999.\n\nClasses cost $40.", K5)
    assert cleaned == "You have 12 reformers.\n\nClasses cost $40." and removed == ["Rent is $999."]


def test_one_bad_cell_drops_only_its_row_and_the_header_and_separator_stay():
    table = "| Item | Cost |\n| --- | --- |\n| Classes | $40 |\n| Rent | $999 |\n| Reformers | 12 |\n"
    cleaned, removed = clean_sentences(table, K5)
    assert cleaned == "| Item | Cost |\n| --- | --- |\n| Classes | $40 |\n| Reformers | 12 |\n"
    assert removed == ["| Rent | $999 |"]


def test_a_table_row_is_one_unit_even_with_a_full_stop_in_a_cell():
    table = "| Item | Note |\n| --- | --- |\n| Rent | Ouch. It is $999. |\n| Classes | $40 |"
    cleaned, removed = clean_sentences(table, K5)
    assert cleaned == "| Item | Note |\n| --- | --- |\n| Classes | $40 |"
    assert removed == ["| Rent | Ouch. It is $999. |"]


def test_a_bad_label_line_drops_only_that_line():
    cleaned, removed = clean_sentences("**Rent:** $999\n**Classes:** $40", K5)
    assert cleaned == "**Classes:** $40" and removed == ["**Rent:** $999"]
    cleaned, removed = clean_sentences("Rent: $999\nClasses: $40\nReformers: 12", K5)
    assert cleaned == "Classes: $40\nReformers: 12" and removed == ["Rent: $999"]
    cleaned, removed = clean_sentences("**Rent**: $999\n**Classes**: $40", K5)
    assert cleaned == "**Classes**: $40"


def test_a_heading_is_its_own_unit_and_a_bad_sentence_under_it_goes_alone():
    cleaned, removed = clean_sentences("## Costs\nThe fix costs $999.\nA class costs $40.", K5)
    assert cleaned == "## Costs\nA class costs $40." and removed == ["The fix costs $999."]
    cleaned, removed = clean_sentences("**Costs**\nThe fix costs $999.", K5)
    assert cleaned == "**Costs**" and removed == ["The fix costs $999."]


def test_a_list_item_is_one_unit_even_with_two_sentences_in_it():
    cleaned, removed = clean_sentences("- Rent is $999. Pay early.\n- Classes cost $40.", K5)
    assert cleaned == "- Classes cost $40." and removed == ["- Rent is $999. Pay early."]


def test_a_prose_sentence_with_an_early_colon_is_not_a_label_line():
    cleaned, removed = clean_sentences("Here is the key point: you pay $40. We also add $999 more. Done.", K5)
    assert cleaned == "Here is the key point: you pay $40. Done." and removed == ["We also add $999 more."]


def test_wrapped_prose_still_joins_until_a_sentence_end():
    cleaned, removed = clean_sentences("The cost is\n$999 a year, which hurts. Classes cost $40.", K5)
    assert cleaned == "Classes cost $40." and removed == ["The cost is\n$999 a year, which hurts."]


# -- 6. tokens ----------------------------------------------------------------------------------------------------

TK = fs(theirs("CF-05", "22", "USD"), theirs("P", "25", "percent"), theirs("E1", "1000", "EUR"),
        theirs("G1", "24", "GB"), theirs("A1", "1000", "AUD"), ours("PL-01", "6", "weeks"))


def test_a_token_next_to_a_symbol_or_unit_word_does_not_double_it():
    assert bind("{{F:P}}%", TK).text == "25%"
    assert bind("{{F:P}} percent", TK).text == "25 percent"
    assert bind("{{F:CF-05}} dollars", TK).text == "22 dollars"
    assert bind("$ {{F:CF-05}}", TK).text == "$ 22"
    assert bind("${{F:CF-05}}", TK).text == "$22"
    assert bind("{{F:CF-05}} USD", TK).text == "22 USD"
    assert bind("{{F:CF-05}} a class", TK).text == "$22 a class"
    assert bind("{{F:P}} of seats", TK).text == "25% of seats"


def test_a_token_whose_neighbour_says_another_unit_is_unresolved():
    for text, shown in (("{{F:CF-05}}%", "{{F:CF-05}}"), ("${{F:P}}", "{{F:P}}"), ("{{F:P}} dollars", "{{F:P}}"),
                        ("\u20ac{{F:CF-05}}", "{{F:CF-05}}")):
        r = bind(text, TK)
        assert r.text == text and r.bound == [], text
        assert [u.text for u in r.unresolved] == [shown], text


def test_a_token_stuck_to_digits_is_unresolved():
    for text in ("12{{F:CF-05}}", "{{F:CF-05}}12", "$12{{F:CF-05}}"):
        r = bind(text, TK)
        assert r.text == text and r.bound == [] and any(isinstance(u, UnresolvedToken) for u in r.unresolved)


def test_stray_or_nested_braces_are_reported_and_never_left_silently():
    for text in ("{{F:{{F:CF-05}}}}", "see {{F:CF-05", "see {{F:CF-05} here", "{{F: {{F:P}} }}", "oops {{F:"):
        r = bind(text, TK)
        assert "{{F:" in r.text, text
        assert r.unresolved, text
        assert all(u.text and r.text[u.start:u.end] == u.text for u in r.unresolved), text
        cleaned, removed = clean_sentences(f"Fine. {text} Also fine.", TK)
        assert "{{F:" not in cleaned and len(removed) == 1, text


def test_a_figure_in_euros_pounds_or_an_unlisted_unit_prints_its_unit_through_a_token():
    assert bind("{{F:E1}}", TK).text == "\u20ac1,000"
    assert bind("Rent {{F:E1}} a month", TK).text == "Rent \u20ac1,000 a month"
    assert bind("{{F:A1}}", TK).text == "1,000 AUD"
    assert bind("{{F:A1}} AUD", TK).text == "1,000 AUD"
    assert bind("{{F:G1}}", TK).text == "24 GB"
    assert bind("{{F:G1}} GB", TK).text == "24 GB"
    sq = fs(theirs("S1", "1000", "square feet"))
    assert bind("{{F:S1}} square feet", sq).text == "1,000 square feet"
    assert bind("{{F:S1}}", sq).text == "1,000 square feet"
    assert bind("{{F:PL-01}}", TK).text == "6 weeks"
    assert bind("over {{F:PL-01}} weeks", TK).text == "over 6 weeks"
    assert bind("over {{F:PL-01}} week", TK).text == "over 6 week"


# -- 7. a client's quotation is checked, never rewritten ----------------------------------------------------------

def test_a_number_in_a_quotation_binds_only_on_an_exact_match_and_is_not_rewritten():
    known = fs(derived("DV-01", "44928", "USD", precision=-3))
    exact = 'The client wrote "we lose about $44,928 a year" and we agree.'
    r = bind(exact, known)
    assert r.text == exact and [f.id for f in r.bound] == ["DV-01"] and r.unresolved == []
    shown = 'The client wrote "we lose $45,000 a year" and we agree.'
    r = bind(shown, known)
    assert r.text == shown and [f.id for f in r.bound] == ["DV-01"]
    near = 'The client wrote "we lose $44,900 a year" and we agree.'
    r = bind(near, known)
    assert r.text == near and r.bound == [] and [u.text for u in r.unresolved] == ["$44,900"]
    curly = 'The client wrote \u201cwe lose $44,900 a year\u201d and we agree.'
    r = bind(curly, known)
    assert r.text == curly and [u.text for u in r.unresolved] == ["$44,900"]
    curly_exact = 'She wrote \u201c$44,928\u201d.'
    assert bind(curly_exact, known).text == curly_exact


def test_outside_the_quotation_the_same_number_is_still_rewritten():
    known = fs(theirs("CF", "12", "classes"))
    text = 'We run twelve classes, she wrote "twelve classes" to us, so twelve classes it is.'
    assert bind(text, known).text == 'We run 12 classes, she wrote "twelve classes" to us, so 12 classes it is.'


def test_a_quoted_number_that_matches_nothing_drops_its_sentence():
    cleaned, removed = clean_sentences('She wrote "we lose $9,999". Fine.', KNOWN)
    assert cleaned == "Fine." and len(removed) == 1


def test_segments_tag_a_quoted_figure_with_the_text_as_written():
    known = fs(derived("DV-01", "44928", "USD", precision=-3))
    assert segments('She wrote "$44,928" here', known) == [
        {"text": 'She wrote "'}, {"figure": "DV-01", "text": "$44,928"}, {"text": '" here'}]


# -- 8. speed ----------------------------------------------------------------------------------------------------------

def test_a_hundred_thousand_characters_of_tokens_and_numbers_bind_in_about_a_second():
    known = fs(theirs("A", "22", "USD"))
    text = "{{F:A}} 12 " * (100_000 // 11)
    t0 = time.perf_counter()
    r = bind(text, known)
    took = time.perf_counter() - t0
    assert r.text.startswith("$22 12 $22 12 ") and len(r.unresolved) == text.count("12")
    assert took < 5, took
    t0 = time.perf_counter()
    cleaned, removed = clean_sentences("Costs $9,999 a lot. Fine here. " * 3000, known)
    assert time.perf_counter() - t0 < 5
    assert cleaned.count("Fine here.") == 3000 and len(removed) == 3000


# -- 9. one list of money units -------------------------------------------------------------------------------------------

def test_the_money_units_are_the_readers_own_set():
    assert B._MONEY_UNITS is read._MONEY_UNITS


# -- two more edges found while reviewing the rulings ----------------------------------------------------------------

def test_a_range_end_that_names_its_own_currency_keeps_it():
    known = fs(theirs("US", "1000", "USD"), theirs("EU", "900", "EUR"))
    r = bind("From $1,000 to EUR 900 a month.", known)
    assert r.unresolved == [] and [f.id for f in r.bound] == ["US", "EU"]
    wrong = fs(theirs("US", "1000", "USD"), theirs("EU", "900", "USD"))
    assert [u.text for u in bind("From $1,000 to EUR 900 a month.", wrong).unresolved] == ["EUR 900"]


def test_a_token_followed_by_a_time_word_that_is_not_its_unit_is_unresolved():
    known = fs(ours("PL-01", "6", "weeks"), theirs("CF-05", "22", "USD"), theirs("N", "12", "count"))
    for text in ("{{F:PL-01}}-day pilot", "{{F:PL-01}} days", "{{F:CF-05}} days"):
        r = bind(text, known)
        assert r.text == text and r.bound == [] and len(r.unresolved) == 1, text
    assert bind("{{F:PL-01}}-week pilot", known).text == "6-week pilot"
    r = bind("{{F:N}} days", known)                          # a count is not a figure in days either
    assert r.text == "{{F:N}} days" and r.bound == [] and len(r.unresolved) == 1


def test_a_time_word_after_a_number_does_not_bind_to_a_figure_in_a_noun_unit():
    _stays_unresolved("The pilot runs 12 days.", fs(derived("DV-01", "12.04", "classes", precision=2)), "12")
    _stays_unresolved("The pilot runs 12 days.", fs(derived("DV-01", "12.04", "GB", precision=2)), "12")
    # nor to a figure with no unit: the case file has to say "days" before prose may
    _stays_unresolved("The pilot runs 12 days.", fs(theirs("CF-01", "12", "")), "12")
    _stays_unresolved("The pilot runs 12 days.", fs(theirs("CF-01", "12", "count")), "12")


# ==============================================================================================
# Second review round: ranges are not "whatever sits between two numbers", a time word is
# evidence, clean_sentences keeps items and indents whole, tokens do not glue.
# The range logic reads each mention's own text, so these hold whatever forms the reader gives
# the ends of a range.
# ==============================================================================================

# -- 1. "to" and "-" between two numbers are not automatically a range -------------------------------------

def test_a_percent_then_a_dollar_amount_is_two_quantities_not_a_range():
    known = fs(theirs("CF-01", "10", "percent"), derived("DV-01", "22.1", "percent", precision=1),
               theirs("CF-02", "22", "USD"))
    r = bind("Raise the price by 10% to $22.", known)
    assert r.text == "Raise the price by 10% to $22."
    assert [f.id for f in r.bound] == ["CF-01", "CF-02"] and r.unresolved == []


def test_a_dollar_amount_then_a_count_of_people_is_two_quantities_not_a_range():
    known = fs(theirs("CF-01", "45", "USD"), derived("DV-01", "12.05", "USD", precision=2),
               theirs("CF-02", "12", "instructors"))
    r = bind("We pay $45 to 12 instructors each week.", known)
    assert r.text == "We pay $45 to 12 instructors each week."
    assert [f.id for f in r.bound] == ["CF-01", "CF-02"] and r.unresolved == []


def test_a_percent_then_a_count_of_members_is_two_quantities_not_a_range():
    known = fs(theirs("CF-01", "5", "percent"), derived("DV-01", "39.9", "percent", precision=1))
    r = bind("We cut churn 5% to 40 members.", known)
    assert r.text == "We cut churn 5% to 40 members."
    assert [f.id for f in r.bound] == ["CF-01"] and [u.text for u in r.unresolved] == ["40"]


def test_a_bare_end_with_no_noun_of_its_own_takes_the_shape_of_the_range():
    known = fs(theirs("CF-01", "20", "USD"), theirs("CF-02", "30", "count"))
    for text in ("Costs $20 to 30 a class.", "Costs $20-30 per class.", "Costs $20-30.", "Costs $20-30 each, ok."):
        assert [u.text for u in bind(text, known).unresolved] == ["30"], text
    known = fs(theirs("CF-01", "20", "USD"), theirs("CF-02", "30", "members"))
    r = bind("Costs $20 to 30 members.", known)       # "members" is 30's own noun: two quantities
    assert r.unresolved == [] and [f.id for f in r.bound] == ["CF-01", "CF-02"]
    pct = fs(theirs("CF-01", "10", "count"), theirs("CF-02", "15", "percent"))
    for text in ("Churn 10-15% a year.", "from 10 to 15%", "Churn 10-15%."):
        assert [u.text for u in bind(text, pct).unresolved] == ["10"], text


def test_a_range_end_with_its_own_shape_is_never_overridden_by_the_other():
    both = fs(theirs("CF-01", "5", "USD"), theirs("CF-02", "10", "percent"))
    assert bind("Fees run from $5 to 10%.", both).unresolved == []        # a dollar and a percent: two quantities
    pct_only = fs(theirs("CF-01", "5", "percent"), theirs("CF-02", "10", "percent"))
    r = bind("Fees run from $5 to 10%.", pct_only)
    assert [u.text for u in r.unresolved] == ["$5"]                       # the percent did not turn $5 into 5%
    usd_only = fs(theirs("CF-01", "5", "USD"), theirs("CF-02", "10", "USD"))
    r = bind("Fees run from $5 to 10%.", usd_only)
    assert [u.text for u in r.unresolved] == ["10%"]                      # nor the dollar turn 10% into $10


# -- 2. a time word is evidence ---------------------------------------------------------------------------------

def test_a_unitless_count_never_takes_a_number_before_a_time_word():
    _stays_unresolved("Staff need 12 hours of cover.", fs(derived("DV-01", "11.96", "count", precision=2)), "12")
    _stays_unresolved("Staff need 12 hours of cover.", fs(derived("DV-01", "11.96", "", precision=2)), "12")


def test_a_filler_word_is_not_agreement_with_a_figure_in_time():
    _stays_unresolved("We run 40 per week.", fs(derived("DV-01", "40.1", "weeks", precision=1)), "40")
    _stays_unresolved("We run 40 a week.", fs(derived("DV-01", "40.1", "weeks", precision=1)), "40")
    r = bind("We run about 40 weeks.", fs(derived("DV-01", "40.1", "weeks", precision=1)))
    assert r.text == "We run about 40.1 weeks." and [f.id for f in r.bound] == ["DV-01"]


def test_the_figure_that_names_the_unit_wins_over_a_unitless_one():
    known = fs(theirs("CF-01", "12", "count"), derived("DV-01", "12", "weeks"))
    for k in (known, fs(derived("DV-01", "12", "weeks"), theirs("CF-01", "12", "count"))):
        r = bind("It takes 12 weeks.", k)
        assert r.text == "It takes 12 weeks." and [f.id for f in r.bound] == ["DV-01"] and r.unresolved == []
    nouns = fs(theirs("CF-01", "12", "count"), derived("DV-02", "12", "classes"))
    assert [f.id for f in bind("We run 12 classes.", nouns).bound] == ["DV-02"]
    # with no noun after it both print "12": the more trusted kind answers
    assert [f.id for f in bind("Of the 12 we start.", nouns).bound] == ["CF-01"]


def test_a_unitless_count_takes_a_number_only_when_no_noun_follows_it():
    known = fs(theirs("CF-01", "12", "count"))
    _stays_unresolved("We have 12 instructors.", known, "12")
    for text in ("We have 12.", "We have 12, then more.", "We have 12 of them.", "Only 12 of them."):
        assert [f.id for f in bind(text, known).bound] == ["CF-01"], text
    for text in ("We have 12 per class.", "We have 12 each week."):         # a rate does not contradict a figure with no period
        assert [f.id for f in bind(text, known).bound] == ["CF-01"], text
    for text in ("Hire 12 now.", "Dial 12"):                                   # a number that is not a quantity
        _stays_unresolved(text, known, "12")
    named = fs(theirs("CF-01", "12", "instructors"))
    assert [f.id for f in bind("We have 12 instructors.", named).bound] == ["CF-01"]


# -- 3. clean_sentences keeps items, indents and blank lines whole ---------------------------------------------------

KS = fs(theirs("CF-01", "22", "USD"), theirs("CF-02", "12", "reformers"))


def test_a_wrapped_list_item_goes_whole_when_a_number_in_it_is_bad():
    cleaned, removed = clean_sentences("- Rent is $22 and\n  we lose $9 each week.\n- Fine item.", KS)
    assert cleaned == "- Fine item."
    assert removed == ["- Rent is $22 and\n  we lose $9 each week."]


def test_a_bad_first_line_takes_the_continuation_lines_of_its_item_with_it():
    cleaned, removed = clean_sentences("- We lose $9 each week and\n  that adds up over time.\n- Rent is $22.", KS)
    assert cleaned == "- Rent is $22."
    assert removed == ["- We lose $9 each week and\n  that adds up over time."]


def test_an_item_that_wraps_without_an_indent_keeps_its_unfinished_line_together():
    cleaned, removed = clean_sentences("- We lose $9 each week and\nthat adds up over time.\n- Rent is $22.", KS)
    assert cleaned == "- Rent is $22." and len(removed) == 1


def test_a_numbered_item_and_the_indented_line_under_it_are_one_unit():
    cleaned, removed = clean_sentences("1. Rent is $22.\n   We lose $9 a week.\n2. Next.", KS)
    assert cleaned == "2. Next."
    assert removed == ["1. Rent is $22.\n   We lose $9 a week."]


def test_a_dropped_child_item_leaves_its_parent_and_its_siblings():
    cleaned, removed = clean_sentences("- a\n  - b costs $9\n- c", KS)
    assert cleaned == "- a\n- c" and removed == ["- b costs $9"]
    cleaned, removed = clean_sentences("- a\n  - b\n  - c costs $9\n  - d\n- e", KS)
    assert cleaned == "- a\n  - b\n  - d\n- e" and removed == ["- c costs $9"]


def test_a_dropped_indented_paragraph_leaves_the_next_one_with_its_own_indent():
    cleaned, removed = clean_sentences("Ok sentence.\n\n  Indented para $9.\n\nNext.", KS)
    assert cleaned == "Ok sentence.\n\nNext." and removed == ["Indented para $9."]
    cleaned, removed = clean_sentences("- a\n  - b costs $9\n  - d\n- e", KS)
    assert cleaned == "- a\n  - d\n- e"


def test_a_drop_never_turns_the_next_line_into_an_indented_code_block():
    cleaned, removed = clean_sentences("A.\n\nBad $9.\n    Keep this line.\n\nEnd.", KS)
    assert cleaned == "A.\n\nKeep this line.\n\nEnd." and removed == ["Bad $9."]


def test_the_separator_after_a_drop_is_the_longer_break_and_the_next_units_indent():
    assert B._rejoin("\n  ", "\n") == "\n"
    assert B._rejoin("\n", "\n\n") == "\n\n"
    assert B._rejoin("\n\n", "\n") == "\n\n"
    assert B._rejoin("\n\n  ", "\n\n") == "\n\n"
    assert B._rejoin("\n", "\n  ") == "\n  "
    assert B._rejoin(" ", "\n") == "\n"
    assert B._rejoin("\n", "") == ""
    assert B._rejoin("\n\n", "\n    ") == "\n\n"        # a blank line and then four columns is a code block
    assert B._rejoin("\n", "\n    ") == "\n    "         # the text already had it


def test_a_plain_lead_in_with_a_colon_splits_into_sentences():
    cleaned, removed = clean_sentences("Why it matters: rent is $22. You lose $9 too. Fine end.", KS)
    assert cleaned == "Why it matters: rent is $22. Fine end." and removed == ["You lose $9 too."]


def test_unfinished_label_lines_are_separate_units_but_a_wrapped_sentence_is_not():
    cleaned, removed = clean_sentences("Rent: $999\nClasses: $22\nReformers: 12", KS)
    assert cleaned == "Classes: $22\nReformers: 12" and removed == ["Rent: $999"]
    cleaned, removed = clean_sentences("The cost is\n$999 a year, which hurts. Fine.", KS)
    assert cleaned == "Fine."


# -- 4. tokens do not glue ---------------------------------------------------------------------------------------------

TA = fs(theirs("A", "22", "USD"), theirs("N", "12", "count"), ours("PL-01", "6", "weeks"),
        theirs("CF-05", "22", "USD"), theirs("G1", "24", "GB"), theirs("P", "25", "percent"))


def test_a_token_stuck_to_a_scale_letter_or_a_word_is_unresolved():
    for text in ("{{F:A}}k", "{{F:A}}M", "{{F:A}}m", "{{F:A}}bn", "{{F:A}}th", "x{{F:A}}", "{{F:A}}x"):
        r = bind(text, TA)
        assert r.text == text and r.bound == [] and len(r.unresolved) == 1, text
    assert bind("USD{{F:A}}", TA).text == "USD22"      # a currency code in front is a currency


def test_a_token_before_a_noun_prints_the_number_only_and_only_where_the_noun_can_stand():
    _stays_unresolved("{{F:N}} members", TA, "{{F:N}}")                      # a count names no noun
    assert bind("{{F:M}} members", fs(theirs("M", "12", "members"))).text == "12 members"
    assert bind("{{F:M}} members", fs(theirs("M", "12", "member"))).text == "12 members"
    _stays_unresolved("{{F:M}} reformers", fs(theirs("M", "12", "members")), "{{F:M}}")
    assert bind("{{F:PL-01}} weeks", TA).text == "6 weeks"            # the unit is said once
    for text in ("{{F:PL-01}} members", "{{F:CF-05}} members", "{{F:G1}} apples"):
        r = bind(text, TA)
        assert r.text == text and r.bound == [] and len(r.unresolved) == 1, text
    assert bind("{{F:CF-05}} extra", TA).text == "$22 extra"
    assert bind("{{F:CF-05}} a class", TA).text == "$22 a class"
    assert bind("{{F:PL-01}} in total", TA).text == "6 weeks in total"


def test_a_lowercase_or_odd_case_token_is_a_token():
    assert bind("{{f:CF-05}} a class", TA).text == "$22 a class"
    assert bind("{{ f : CF-05 }} a class", TA).text == "$22 a class"
    r = bind("see {{f:NOPE}} here", TA)
    assert r.text == "see {{f:NOPE}} here" and isinstance(r.unresolved[0], UnresolvedToken)
    r = bind("see {{f:CF-05", TA)
    assert r.unresolved and r.text == "see {{f:CF-05"


def test_when_the_text_starts_with_a_drop_the_first_kept_line_keeps_its_own_indent():
    assert clean_sentences("\tTabbed $9.\n\tTabbed $22.", KS) == ("\tTabbed $22.", ["Tabbed $9."])
    assert clean_sentences("  Bad $9. Good $22.", KS) == ("  Good $22.", ["Bad $9."])
    assert clean_sentences("- Bad $9\n  - Child $22\n- Last", KS) == ("  - Child $22\n- Last", ["- Bad $9"])


# ==============================================================================================
# Third review round: what joins two numbers, tier before specificity, periods, comparatives,
# true roundings only, the round-trip net, glued tokens, bold-led paragraphs, no code blocks.
# Judged against the reader as committed.
# ==============================================================================================

# the review's figures
R1 = fs(theirs("CF-62", "62", "percent"), theirs("CF-04", "4", "instructors"), derived("DV-398", "3.98", "percent", precision=2),
        theirs("CF-22", "22", "USD"), theirs("CF-12", "12", "count"), derived("DV-1196", "11.96", "USD", precision=2),
        ours("PL-25", "25", "USD"), theirs("CF-40", "40", "members"), derived("DV-399", "39.9", "USD", precision=1))


def _binds_each_on_its_own(text, known, *ids):
    r = bind(text, known)
    assert r.text == text, r.text
    assert [f.id for f in r.bound] == list(ids), [f.id for f in r.bound]
    assert r.unresolved == [], r.unresolved
    return r


# -- 1. what can join two numbers ----------------------------------------------------------------------

def test_a_spaced_dash_or_an_em_dash_never_joins_two_numbers():
    _binds_each_on_its_own("Occupancy is 62% - 4 of your instructors are idle at noon.", R1, "CF-62", "CF-04")
    _binds_each_on_its_own("Occupancy is 62% \u2014 4 of your instructors are idle at noon.", R1, "CF-62", "CF-04")
    _binds_each_on_its_own("Occupancy is 62% \u2013 4 of your instructors are idle at noon.", R1, "CF-62", "CF-04")
    _binds_each_on_its_own("Occupancy is 62%\u20144 of your instructors are idle at noon.", R1, "CF-62", "CF-04")
    _binds_each_on_its_own("Each class costs $22 - 12 of them sell out.", R1, "CF-22", "CF-12")
    r = bind("Class size 12 - $22 per head.", R1)         # a unitless 12 after "size" and beside "per head" is no quantity
    assert r.text == "Class size 12 - $22 per head." and [f.id for f in r.bound] == ["CF-22"]
    assert [u.text for u in r.unresolved] == ["12"]
    _binds_each_on_its_own("Price: $22 - 12 per class.", R1, "CF-22", "CF-12")      # "per class" does not hold a figure with no period


def test_a_bare_number_followed_by_a_partitive_or_an_alternative_shares_nothing():
    _binds_each_on_its_own("At $22 to 12 or more members, a class pays.", R1, "CF-22", "CF-12")
    _binds_each_on_its_own("Offer $25 to 40 of your members.", R1, "PL-25", "CF-40")
    _binds_each_on_its_own("Offer $25 to 40 and more members.", R1, "PL-25", "CF-40")
    _binds_each_on_its_own("Offer $25 to 40 than we had.", R1, "PL-25", "CF-40")


def test_a_bare_left_number_does_not_become_dollars_because_a_dollar_amount_follows():
    r = bind("Class size 12 to $22 per head.", R1)
    assert [f.id for f in r.bound] == ["CF-22"] and [u.text for u in r.unresolved] == ["12"]    # 12 stays its own number
    # it can when the range is plainly of money
    pairs = fs(theirs("A", "20", "USD"), theirs("B", "30", "USD"), theirs("C", "20", "count"))
    for text in ("From 20 to $30 a class.", "Costs 20-$30 a class.", "Between 20 and $30 a class."):
        r = bind(text, pairs)
        assert r.unresolved == [] and [f.id for f in r.bound] == ["A", "B"], text
    r = bind("Costs 20 to $30 a class.", pairs)         # a bare 20 after a verb is no quantity for a figure with no unit
    assert [f.id for f in r.bound] == ["B"] and [u.text for u in r.unresolved] == ["20"]
    # a bare left end that is the tail of a partitive keeps to itself
    pct = fs(theirs("A", "12", "percent"), theirs("B", "15", "percent"))
    assert [u.text for u in bind("4 of 12 to 15% came.", pct).unresolved] == ["4", "12"]


def test_the_joiners_that_remain_still_join():
    pct = fs(theirs("A", "10", "count"), theirs("B", "15", "percent"))
    for text in ("Churn 10-15% a year.", "Churn 10\u201315% a year.", "Churn of 10 to 15% a year.",
                 "Churn between 10 and 15% a year.", "Churn from 10 to 15% a year."):
        assert [u.text for u in bind(text, pct).unresolved] == ["10"], text
    usd = fs(theirs("A", "20", "USD"), theirs("B", "30", "count"))
    for text in ("Costs $20-30 a class.", "Costs $20 to 30 a class.", "Costs between $20 and 30 a class."):
        assert [u.text for u in bind(text, usd).unresolved] == ["30"], text
    assert [u.text for u in bind("Costs $20 and 30 a class.", usd).unresolved] == []   # "and" alone is not "between"


# -- 2. the tier decides first, specificity only within it ------------------------------------------------

def test_the_clients_exact_number_beats_a_more_specific_near_figure():
    known = fs(theirs("CF-01", "12", "reformers"), ours("PL-01", "12.05", "reformers", precision=2))
    _binds_each_on_its_own("You have 12 reformers.", known, "CF-01")
    known = fs(theirs("CF-01", "12", "classes"), derived("DV-01", "12.04", "classes", precision=2))
    _binds_each_on_its_own("You run 12 classes a week.", known, "CF-01")


def test_within_a_tier_the_figure_that_names_the_unit_still_wins():
    known = fs(theirs("CF-01", "12", "count"), derived("DV-01", "12", "classes"))
    _binds_each_on_its_own("You run 12 classes a week.", known, "DV-01")


# -- 3. a period the sentence names must be the figure's ---------------------------------------------------------

def test_a_weekly_figure_never_binds_to_a_monthly_or_yearly_amount():
    known = fs(derived("DV-01", "9504", "USD", period="week"), derived("DV-02", "1953.6", "USD", precision=1, period="week"))
    _stays_unresolved("You bring in about $9,500 a month.", known, "$9,500")
    _stays_unresolved("Empty seats cost you $1,950 a year.", known, "$1,950")
    _stays_unresolved("Empty seats cost you $1,950 per year.", known, "$1,950")
    _stays_unresolved("Empty seats cost you $1,950 yearly.", known, "$1,950")
    _stays_unresolved("Your monthly rent of $9,500 is high.", known, "$9,500")


def test_the_same_amount_binds_when_the_period_agrees_or_is_absent():
    weekly = fs(derived("DV-01", "9504", "USD", period="week"))
    assert bind("You bring in about $9,500 a week.", weekly).text == "You bring in about $9,504 a week."
    assert bind("You bring in about $9,500 each week.", weekly).bound[0].id == "DV-01"
    assert bind("Your weekly rent of about $9,500 is high.", weekly).bound[0].id == "DV-01"
    assert bind("You bring in about $9,500 a class.", weekly).bound[0].id == "DV-01"     # "a class" is no period
    assert bind("You bring in about $9,500.", weekly).bound[0].id == "DV-01"
    no_period = fs(derived("DV-01", "9504", "USD"))
    assert bind("You bring in about $9,500 a month.", no_period).bound[0].id == "DV-01"
    month = fs(derived("DV-01", "9504", "USD", period="operating_30_day_month"))
    assert bind("You bring in about $9,500 a month.", month).bound[0].id == "DV-01"
    _stays_unresolved("You bring in about $9,500 a week.", month, "$9,500")


def test_a_period_blocks_percents_and_counts_too_and_not_through_a_time_word():
    known = fs(theirs("CF-01", "30", "percent", period="week"), theirs("CF-02", "12", "classes", period="week"))
    _stays_unresolved("Churn is 30% a month.", known, "30%")
    _stays_unresolved("We run 12 classes a month.", known, "12")
    assert bind("We run 12 classes a week.", known).bound[0].id == "CF-02"
    days = fs(theirs("CF-03", "10", "days", period="week"))
    assert bind("It takes 10 days a week.", days).bound[0].id == "CF-03"      # "days" is the unit; the period is the week's


def test_a_token_is_held_to_the_period_too():
    weekly = fs(derived("DV-01", "9504", "USD", period="week"))
    r = bind("You bring in {{F:DV-01}} a month.", weekly)
    assert r.text == "You bring in {{F:DV-01}} a month." and len(r.unresolved) == 1
    assert bind("You bring in {{F:DV-01}} a week.", weekly).text == "You bring in $9,504 a week."


# -- 4. a comparative is a claim, not a rounding ------------------------------------------------------------------------

def test_a_limit_is_never_rewritten_to_a_near_figure():
    _stays_unresolved("Keep costs under $7,500.", fs(derived("DV-01", "7480", "USD")), "$7,500")
    _stays_unresolved("Costs are over $45,000.", fs(derived("DV-01", "44928", "USD")), "$45,000")


@pytest.mark.parametrize("lead", ["over", "under", "above", "below", "at least", "at most", "up to", "more than",
                                  "less than", "fewer than", "exceeds", "no more than", "no less than", "nearly",
                                  "almost", "exactly", "Over", "AT LEAST"])
def test_every_comparative_binds_only_on_an_exact_match(lead):
    known = fs(derived("DV-01", "44928", "USD"))
    _stays_unresolved(f"Costs are {lead} $45,000 now.", known, "$45,000")
    r = bind(f"Costs are {lead} $44,928 now.", known)
    assert r.text == f"Costs are {lead} $44,928 now." and [f.id for f in r.bound] == ["DV-01"]


def test_a_comparative_over_a_figure_that_only_displays_as_the_mention_is_unresolved():
    # 44,928 shown as ~45,000 does not certify "over $45,000": the limit needs the exact value
    known = fs(derived("DV-01", "44928", "USD", precision=-3))
    _stays_unresolved("Costs are over $45,000 now.", known, "$45,000")


def test_about_and_around_are_hedges_and_not_limits():
    known = fs(derived("DV-01", "7480", "USD"))
    assert bind("Keep costs about $7,500.", known).text == "Keep costs about $7,480."
    assert bind("Keep costs around $7,500.", known).text == "Keep costs around $7,480."


# -- 5. a near rewrite must be a true rounding -----------------------------------------------------------------------------

def test_a_near_mention_is_rewritten_only_when_it_is_the_figure_rounded_to_its_own_last_place():
    known = fs(derived("DV-01", "44928", "USD"))
    assert bind("We lose about $45,000 a year.", known).text == "We lose about $44,928 a year."      # thousands
    assert bind("We lose about $44,900 a year.", known).text == "We lose about $44,928 a year."      # hundreds
    assert bind("We lose about $44,930 a year.", known).text == "We lose about $44,928 a year."      # tens
    _stays_unresolved("We lose about $44,950 a year.", known, "$44,950")                   # near, but 44,928 is 44,930 to tens
    _stays_unresolved("We lose about $44,960 a year.", known, "$44,960")
    _stays_unresolved("We lose about $44,990 a year.", known, "$44,990")
    _stays_unresolved("We lose $45,000 a year.", known, "$45,000")                          # a true rounding with no cue
    assert bind("Fees are about $1,000.", fs(derived("DV-01", "995", "USD"))).text == "Fees are about $995."
    _stays_unresolved("A seat is about $4,750.", fs(derived("DV-01", "4728", "USD")), "$4,750")
    assert bind("About 12 classes a week.", fs(derived("DV-01", "12.04", "classes", precision=2))).text == \
        "About 12.04 classes a week."


# -- 6. the round trip: what is written must read back as what was meant ---------------------------------------------------------------

def test_a_replacement_that_would_read_back_as_another_number_is_taken_back():
    known = fs(ours("PL-02", "2", ""), ours("PL-03", "200", "person"))
    text = "Plan on two 200-person events."
    r = bind(text, known)
    assert r.text == text                                   # "2 200-person" would read as 2,200
    assert r.unresolved == [] and {f.id for f in r.bound} == {"PL-02", "PL-03"}
    assert [m.value for m in mentions(r.text)] == [D(2), D(200)]


def test_a_replacement_that_would_change_how_the_number_reads_is_taken_back():
    # "USD 2" reads as money, "two" beside "USD" did not: the figure is named, the words stay
    known = fs(ours("PL-02", "2", "tickets"))
    for text in ("Pay USD two tickets.", "It costs EUR two tickets."):
        r = bind(text, known)
        assert r.text == text and [f.id for f in r.bound] == ["PL-02"] and r.unresolved == [], text


def test_braces_around_a_replaced_number_that_now_read_as_a_token_take_it_back():
    r = bind("{{F: {{F:C}} 3x }}", fs(theirs("C", "12", "count")))
    assert "{{F:" in r.text and r.bound == [] and r.unresolved
    r = bind("{{F:{{F:A}}}}", fs(theirs("A", "22", "USD")))
    assert r.bound == [] and r.unresolved


def test_a_currency_sign_after_a_number_is_kept_with_it():
    known = fs(ours("W", "6", ""))
    _stays_unresolved("Rent is 6 $ a week", known, "6 $")        # it was dollars; a bare figure does not name them
    r = bind("Rent is 6 $ a week", fs(ours("W", "6", "USD")))
    assert r.text == "Rent is 6 $ a week" and [f.id for f in r.bound] == ["W"]


def test_a_currency_code_that_belongs_to_the_number_before_is_not_the_lead_of_a_token():
    known = fs(theirs("A", "22", "USD"))
    r = bind("We pay 22 USD {{F:A}} more.", known)
    assert r.text == "We pay 22 USD $22 more."


def test_a_number_a_token_becomes_can_be_an_end_of_a_range():
    # "{{F:A}} to 6": once A prints as $22 this reads "$22 to 6", so the 6 shares the dollars
    known = fs(theirs("A", "22", "USD"), theirs("B", "6", "members"))
    r = bind("{{F:A}} to 6 a class", known)
    assert r.text == "$22 to 6 a class" and [u.text for u in r.unresolved] == ["6"]
    r = bind("{{F:A}} to 6 members", known)
    assert r.unresolved == [] and [f.id for f in r.bound] == ["A", "B"]


def test_what_bind_wrote_reads_back_as_the_figures_it_named():
    known = fs(theirs("CF-01", "22", "USD"), derived("DV-01", "44928", "USD", precision=-3), ours("PL-01", "6", "weeks"),
               theirs("P", "25", "percent"), theirs("E", "1000", "EUR"))
    text = "A class is $22; we lose about $44,928 a year over six weeks, 25 percent of it, in EUR 1,000 steps."
    r = bind(text, known)
    assert [m.value for m in mentions(r.text)] == [D(22), D(44928), D(6), D(25), D(1000)]


_FRAGMENTS = ["about", "roughly a", "over", "$22", "22", "12", "$ 12", "{{F:A}}", "{{F:C}}", "{{F:A}}{{F:C}}", "two",
              "200-person", "2 200", "weeks", "per week", "a month", "-", " - ", "to", "of", "or", "%", "10-15%", "and",
              "x", "k", ".", ",", "\n", "- ", "(", ")", "\"", "$", "USD", "twice", "half", "3x", "45,000", "6", "44,928",
              "12.04", "classes", "members", "hours", "{{F:Z}}", "{{F:", "}}", "~", "EUR 5", "5 percent", "1,000"]


def test_binding_what_was_bound_changes_nothing_more():
    """Property: for random texts, bind(bind(x).text) names the same figures, has no
    unresolved number the first pass did not have, and leaves the text as it is."""
    import random
    known = fs(theirs("A", "22", "USD"), theirs("C", "12", "count"), derived("D", "44928", "USD", precision=-3),
               ours("W", "6", "weeks"), theirs("N2", "2", ""), theirs("N200", "200", ""),
               theirs("P", "25", "percent"), derived("Q", "12.04", "classes", precision=2), theirs("E", "5", "EUR"),
               derived("R", "6", "", period="week"))
    rng = random.Random(20261101)
    for _ in range(1500):
        text = "".join(rng.choice(_FRAGMENTS) + rng.choice([" ", " ", "  "]) for _ in range(rng.randint(1, 9)))
        first = bind(text, known)
        again = bind(first.text, known)
        assert {f.id for f in again.bound} == {f.id for f in first.bound}, (text, first.text, again.text)
        old = sorted(u.text for u in first.unresolved)
        new = sorted(u.text for u in again.unresolved)
        for t in new:
            assert t in old, (text, first.text, again.text, old, new)
        assert again.text == first.text, (text, first.text, again.text)
        for u in first.unresolved:
            assert first.text[u.start:u.end] == u.text, (text, u)


# -- 7. tokens ------------------------------------------------------------------------------------------------------------------------------

def test_a_count_or_unitless_token_before_a_time_word_is_unresolved():
    known = fs(theirs("CLS", "12", "count"), theirs("U", "6", ""), ours("PL-01", "6", "weeks"))
    for text in ("{{F:CLS}} hours", "{{F:U}} weeks", "{{F:CLS}}-day pilot", "{{F:U}} days"):
        r = bind(text, known)
        assert r.text == text and r.bound == [] and len(r.unresolved) == 1, text
    assert bind("{{F:PL-01}} weeks", known).text == "6 weeks"


def test_two_adjacent_tokens_are_unresolved_and_two_apart_are_not():
    known = fs(theirs("A", "22", "USD"), theirs("C", "12", "count"))
    r = bind("{{F:A}}{{F:C}}", known)
    assert r.text == "{{F:A}}{{F:C}}" and r.bound == [] and len(r.unresolved) == 2
    assert bind("{{F:A}} {{F:C}}", known).text == "$22 12"
    assert bind("{{F:A}}, {{F:C}}", known).text == "$22, 12"


def test_a_token_after_a_dollar_sign_reads_as_one_amount_and_never_doubles_a_tilde():
    rounded = fs(derived("M", "44928", "USD", precision=-3), theirs("E", "22", "USD"))
    assert bind("$ {{F:M}}", rounded).text == "~$45,000"
    assert bind("Rent is $ {{F:M}} a year.", rounded).text == "Rent is ~$45,000 a year."
    assert bind("$ {{F:E}}", rounded).text == "$ 22"                      # nothing was rounded: the sign stays as written
    assert bind("about $ {{F:M}}", rounded).text == "about $ 45,000"       # the hedge already says it
    assert bind("about {{F:M}}", rounded).text == "about $45,000"


def test_a_token_after_a_hedge_and_an_article_or_an_article_alone_drops_the_tilde():
    known = fs(derived("P", "33.333", "percent", precision=0))
    assert bind("roughly a {{F:P}}", known).text == "roughly a 33%"
    assert bind("about a {{F:P}} drop", known).text == "about a 33% drop"
    assert bind("a {{F:P}} drop", known).text == "a 33% drop"
    assert bind("the {{F:P}} drop", known).text == "the 33% drop"
    assert bind("{{F:P}} of seats", known).text == "~33% of seats"
    usd = fs(derived("M", "44928", "USD", precision=-3))
    assert bind("roughly a $45,000 loss", usd).text == "roughly a $45,000 loss"
    assert bind("roughly a $44,928 loss", usd).text == "roughly a $44,928 loss"      # exact: never a less exact number


# -- 8. clean_sentences --------------------------------------------------------------------------------------------------------------------------

def test_a_bold_led_paragraph_of_several_sentences_splits_into_sentences():
    text = "**Bottom line:** Your price is $22. You lose $9. Raise it to $22."
    cleaned, removed = clean_sentences(text, KS)
    assert cleaned == "**Bottom line:** Your price is $22. Raise it to $22." and removed == ["You lose $9."]
    cleaned, removed = clean_sentences("**Bottom line:** Your price is $9. You pay $22.", KS)
    assert cleaned == "You pay $22." and removed == ["**Bottom line:** Your price is $9."]


def test_a_bold_lead_with_no_sentence_end_in_the_middle_is_still_one_unit():
    cleaned, removed = clean_sentences("**Rent:** $999.\n**Classes:** $22.", KS)
    assert cleaned == "**Classes:** $22." and removed == ["**Rent:** $999."]
    cleaned, removed = clean_sentences("**Rent:** about $999 a month, give or take\n**Classes:** $22", KS)
    assert cleaned == "**Classes:** $22"


def test_an_unindented_line_after_an_item_that_ended_a_sentence_is_a_new_paragraph():
    cleaned, removed = clean_sentences("- Rent is $22.\nThis is a new paragraph $9.", KS)
    assert cleaned == "- Rent is $22." and removed == ["This is a new paragraph $9."]
    cleaned, removed = clean_sentences("- Rent is $9.\nKeep this paragraph.", KS)
    assert cleaned == "Keep this paragraph." and removed == ["- Rent is $9."]
    cleaned, removed = clean_sentences("- **Rent is $22.**\nNew paragraph $9.", KS)
    assert cleaned == "- **Rent is $22.**"
    cleaned, removed = clean_sentences('- He said "rent is $22."\nNew paragraph $9.', KS)
    assert cleaned == '- He said "rent is $22."'
    cleaned, removed = clean_sentences("1. Rent is $9.\nKeep this paragraph.", KS)
    assert cleaned == "Keep this paragraph."


def test_a_drop_never_leaves_a_line_with_four_spaces_that_the_text_did_not_have():
    cleaned, removed = clean_sentences("Rent is high at $9.\n    Indented wrap continues here.", KS)
    assert cleaned == "Indented wrap continues here." and removed == ["Rent is high at $9."]
    cleaned, removed = clean_sentences("Fine.\n- item $9\n\n    para in item\n\nEnd.", KS)
    assert cleaned == "Fine.\n\nEnd." and removed == ["- item $9\n\n    para in item"]
    # the text already had it: left alone
    assert clean_sentences("    code line $22\n\nBad $9.", KS) == ("    code line $22", ["Bad $9."])


def test_a_loose_list_item_with_an_indented_second_paragraph_goes_whole():
    cleaned, removed = clean_sentences("- Rent is $22.\n\n  And that is fine.\n\n- Bad item $9.\n\n  More on it.\n\nEnd.", KS)
    assert cleaned == "- Rent is $22.\n\n  And that is fine.\n\nEnd."


# -- 9. idioms -------------------------------------------------------------------------------------------------------------------------------------------

def test_24_7_and_24x7_are_not_quantities():
    for text in ("We are open 24/7.", "Support runs 24x7 for you."):
        if mentions(text):
            pytest.skip("the reader in this checkout reads this idiom")
        r = bind(text, FigureSet())
        assert r.text == text and r.unresolved == []


def test_a_number_word_made_a_digit_must_not_become_a_multiplier():
    # "2 - 3x" reads the 2 as a multiplier, "two - 3x" did not: the words stay
    known = fs(ours("PL-02", "2", ""), ours("PL-03", "3", ""))
    r = bind("Plan on two - 3x more.", known)
    assert r.text == "Plan on two - 3x more." and [f.id for f in r.bound] == ["PL-02"] and r.unresolved == []


def test_a_tilde_before_the_second_number_of_a_range_does_not_break_the_range():
    known = fs(theirs("A", "22", "USD"), derived("D", "44928", "USD", precision=-3))
    r = bind("From $22 to ~45,000 a year.", known)
    assert r.text == "From $22 to ~45,000 a year." and [f.id for f in r.bound] == ["A", "D"]
    r = bind("From $22 to 45,000 a year.", known)           # a rounded figure needs its cue; the 22 still binds
    assert r.text == "From $22 to 45,000 a year." and [f.id for f in r.bound] == ["A"] and [u.text for u in r.unresolved] == ["45,000"]
    assert bind(bind("From $22 to about 45,000 a year.", known).text, known).text == "From $22 to about 45,000 a year."


# ==============================================================================================
# Fourth review round: a limit certifies only what it can, the whole clause names the period,
# links and code are not prose, a count noun must match, and one value printed one way is one answer.
# The figures are the reviewer's studio, with the nouns the case file now stores.
# ==============================================================================================

STUDIO = fs(
    theirs("PRICE", "22", "USD"), theirs("CAP", "12", "reformers"), theirs("MEM", "180", "members"),
    theirs("CLS", "40", "classes", period="week"), theirs("RENT", "4000", "USD", period="month"),
    theirs("OCC", "62", "percent"), theirs("INS", "4", "instructors"), theirs("OPEN", "6", "days"),
    derived("REVW", "6547.2", "USD", precision=-2, period="week"), derived("EMPTY", "182.4", "seats", precision=0, period="week"),
    derived("LOSTW", "1953.6", "USD", precision=-1, period="week"),
    derived("LOSTY", "101587.2", "USD", precision=-3, period="year"),
    derived("LEAVE", "9", "members", precision=0, period="month"),
    ours("NEWP", "25", "USD"), ours("PILOT", "6", "weeks"), ours("INTRO", "3", "intro classes"),
)


# -- 1. a limit certifies only what it can ---------------------------------------------------------------------

def test_a_limit_over_a_figure_that_is_only_shown_that_way_is_unresolved():
    _stays_unresolved("Costs are over $45,000.", fs(derived("DV-01", "44928", "USD", precision=-3)), "$45,000")
    _stays_unresolved("Empty seats: fewer than 182 a week.", STUDIO, "182")
    _stays_unresolved("Keep costs within $7,500.", fs(derived("DV-01", "7480", "USD")), "$7,500")


def test_a_limit_binds_on_the_exact_value_and_prints_exactly_as_written():
    r = bind("You lose more than $101,587.20 a year.", STUDIO)
    assert r.text == "You lose more than $101,587.20 a year." and [f.id for f in r.bound] == ["LOSTY"]
    assert r.unresolved == []
    r = bind("Empty seats cost about $1,950 a week ($1,953.60 exactly).", STUDIO)
    assert r.text == "Empty seats cost about $1,950 a week ($1,953.60 exactly)." and r.unresolved == []
    assert [f.id for f in r.bound] == ["LOSTW"]
    r = bind("It is exactly $1,953.60 a week.", STUDIO)
    assert r.text == "It is exactly $1,953.60 a week." and [f.id for f in r.bound] == ["LOSTW"]
    _stays_unresolved("It is exactly $1,950 a week.", STUDIO, "$1,950")        # the rounded display is not the value


@pytest.mark.parametrize("lead", ["within", "maximum of", "minimum of", "max", "min", "cap", "capped at", "limit of",
                                  "top", "north of", "upwards of", "in excess of", "not more than", "no less than",
                                  "Within", "UPWARDS OF"])
def test_a_limit_word_before_the_number_makes_it_exact_only(lead):
    near = fs(derived("DV-01", "7480", "USD"))
    exact = fs(derived("DV-01", "7500", "USD"))
    _stays_unresolved(f"Keep costs {lead} $7,500 now.", near, "$7,500")
    r = bind(f"Keep costs {lead} $7,500 now.", exact)
    assert r.text == f"Keep costs {lead} $7,500 now." and [f.id for f in r.bound] == ["DV-01"]


@pytest.mark.parametrize("tail", ["max", "min", "maximum", "at most", "at least", "or more", "or less", "and up", "+", "exactly"])
def test_a_limit_word_after_the_number_makes_it_exact_only(tail):
    near = fs(derived("DV-01", "7480", "USD"))
    exact = fs(derived("DV-01", "7500", "USD"))
    text = f"Keep costs to $7,500 {tail} now." if tail != "+" else "Keep costs to $7,500+ now."
    _stays_unresolved(text, near, "$7,500")
    r = bind(text, exact)
    assert r.text == text and [f.id for f in r.bound] == ["DV-01"]


def test_a_hedge_between_the_limit_and_the_number_does_not_loosen_it():
    near = fs(derived("DV-01", "7480", "USD"))
    exact = fs(derived("DV-01", "7500", "USD"))
    for text in ("Keep costs under about $7,500.", "Keep costs at most roughly $7,500.", "Keep costs over around $7,500."):
        _stays_unresolved(text, near, "$7,500")
        assert bind(text, exact).text == text, text


def test_a_token_after_a_limit_is_unresolved_when_the_figure_is_shown_rounded():
    rounded = fs(derived("M", "44928", "USD", precision=-3))
    exact = fs(theirs("M", "22", "USD"))
    for text in ("Costs are over {{F:M}}.", "Costs are exactly {{F:M}}.", "Costs are {{F:M}} or more.", "Keep it within {{F:M}}."):
        r = bind(text, rounded)
        assert r.text == text and r.bound == [] and len(r.unresolved) == 1, text
    assert bind("Costs are over {{F:M}}.", exact).text == "Costs are over $22."
    assert bind("Costs are {{F:M}} or more.", exact).text == "Costs are $22 or more."
    # a plain hedge still lets the figure print without a second "~"
    assert bind("Costs are about {{F:M}}.", rounded).text == "Costs are about $45,000."


# -- 2. the whole clause names the period -----------------------------------------------------------------------------

def test_a_period_named_anywhere_in_the_clause_must_be_the_figures():
    _stays_unresolved("That's about $1,950 in lost revenue a month.", STUDIO, "$1,950")
    _stays_unresolved("Each month, you lose about $1,950.", STUDIO, "$1,950")
    _stays_unresolved("You lose about $102,000 in lost revenue a month.", STUDIO, "$102,000")
    _stays_unresolved("About 182 seats sit empty a month.", STUDIO, "182")
    _stays_unresolved("9 members leave every week.", STUDIO, "9")
    _stays_unresolved("In a typical year you lose about $1,950.", STUDIO, "$1,950")
    _stays_unresolved("Weekly rent: $4,000.", STUDIO, "$4,000")
    _stays_unresolved("| Loss | $1,950 | monthly |", STUDIO, "$1,950")


def test_a_token_is_held_to_the_period_of_its_whole_clause():
    r = bind("Each month you lose {{F:LOSTW}}.", STUDIO)
    assert r.text == "Each month you lose {{F:LOSTW}}." and r.bound == [] and len(r.unresolved) == 1
    assert bind("Each week you lose {{F:LOSTW}}.", STUDIO).text == "Each week you lose ~$1,950."
    assert bind("You lose {{F:LOSTW}} in lost revenue a week.", STUDIO).text == "You lose ~$1,950 in lost revenue a week."


def test_a_period_that_agrees_or_is_not_named_does_not_block():
    assert [f.id for f in bind("Each week, you lose about $1,950.", STUDIO).bound] == ["LOSTW"]
    assert [f.id for f in bind("9 members leave each month.", STUDIO).bound] == ["LEAVE"]
    assert [f.id for f in bind("About 182 seats sit empty.", STUDIO).bound] == ["EMPTY"]
    assert [f.id for f in bind("Your annual loss is about $102,000.", STUDIO).bound] == ["LOSTY"]
    # each number is held to the phrase next to it: two periods in one clause bind the figure of each
    r = bind("Empty seats cost you about $1,950 a week, or about $102,000 a year.", STUDIO)
    assert [f.id for f in r.bound] == ["LOSTW", "LOSTY"] and r.unresolved == []
    r = bind("Rent is $4,000 a month and you lose about $1,950 a week.", STUDIO)
    assert [f.id for f in r.bound] == ["RENT", "LOSTW"] and r.unresolved == []
    r = bind("Empty seats cost you about $1,950 a week. That is about $102,000 a year.", STUDIO)
    assert [f.id for f in r.bound] == ["LOSTW", "LOSTY"] and r.unresolved == []


def test_a_swapped_period_is_still_refused_when_the_phrase_stands_by_the_number():
    # the clause names both; the phrase right by each number decides
    _stays_unresolved("Rent is $1,950 a month and you lose $4,000 a week.", STUDIO, "$1,950", "$4,000")


# -- 3. links, code and paths are not prose ------------------------------------------------------------------------------

def test_a_url_is_neither_read_nor_touched():
    for text in ("See https://example.com/p/1200 for more.", "See http://example.com/p/1200.", "Go to www.example.com/p/1200 now.",
                 "See (https://example.com/p/1200).", "Docs: https://example.com/a/1200?x=22&y=9#top, then stop."):
        r = bind(text, STUDIO)
        assert r.text == text and r.unresolved == [] and r.bound == [], text
        assert clean_sentences(text, STUDIO) == (text, []), text


def test_a_link_target_is_masked_and_the_link_text_is_still_read():
    for text in ("See [plan](https://x.com/1200).", "See [plan](guides/1200).", "See ![chart](img/1200.png) here.",
                 'See [plan](https://x.com/1200 "the 1200 plan").'):
        r = bind(text, STUDIO)
        assert r.text == text and r.unresolved == [], text
    r = bind("See [we lose $9 a week](https://x.com/22) now.", STUDIO)
    assert [u.text for u in r.unresolved] == ["$9"]
    r = bind("See [we charge $22](https://x.com/9) now.", STUDIO)
    assert [f.id for f in r.bound] == ["PRICE"] and r.unresolved == []


def test_code_spans_and_fenced_blocks_are_left_alone():
    for text in ("Run `seats=1200` now.", "Run ``seats = 1200`` now.", "Use `{{F:NOPE}}` as written.",
                 "Code:\n```\nseats = 1200\nprice = 9\n```\nDone.", "Code:\n~~~python\nseats = 1200\n~~~\nDone."):
        r = bind(text, STUDIO)
        assert r.text == text and r.unresolved == [], text
        assert clean_sentences(text, STUDIO) == (text, []), text
    r = bind("Run `seats=1200` and pay $9.", STUDIO)
    assert [u.text for u in r.unresolved] == ["$9"]
    r = bind("Run `seats=1200` and pay $22.", STUDIO)
    assert r.text == "Run `seats=1200` and pay $22." and [f.id for f in r.bound] == ["PRICE"]


def test_a_path_like_token_is_left_alone_and_a_rate_is_still_read():
    for text in ("Read .../guides/22 first.", "Open /api/plans/1200/edit please.", "See docs/plan/1200 for more.",
                 "Try example.com/p/1200 today."):
        r = bind(text, STUDIO)
        assert r.text == text and r.unresolved == [], text
    r = bind("You lose about $1,950/week.", STUDIO)
    assert [f.id for f in r.bound] == ["LOSTW"]                  # "$1,950/week" is a rate: read, with its period
    _stays_unresolved("You lose about $1,950/month.", STUDIO, "$1,950")


def test_a_bound_number_next_to_a_url_leaves_the_url_byte_identical():
    text = "See https://x.com/p/44928 then lose $44,928 a year, `seats=1200`, [plan](u/9/9)."
    known = fs(derived("DV-01", "44928", "USD", precision=-3))
    r = bind(text, known)
    assert r.text == "See https://x.com/p/44928 then lose $44,928 a year, `seats=1200`, [plan](u/9/9)."
    assert [f.id for f in r.bound] == ["DV-01"] and r.unresolved == []
    assert "".join(s["text"] for s in segments(text, known)) == r.text


# -- 4. the noun after a count ---------------------------------------------------------------------------------------------------

def test_a_count_binds_only_to_a_figure_whose_unit_is_that_noun():
    _stays_unresolved("Hire 4 more instructors.", fs(theirs("CAP", "4", "reformers")), "4")
    _stays_unresolved("About 180 empty seats a week.", STUDIO, "180")
    _stays_unresolved("Add 3 classes on Saturday.", STUDIO, "3")
    assert [f.id for f in bind("Hire 4 more reformers.", fs(theirs("CAP", "4", "reformers"))).bound] == ["CAP"]
    assert [f.id for f in bind("You have 180 members.", STUDIO).bound] == ["MEM"]
    assert [f.id for f in bind("Add 3 intro classes on Saturday.", STUDIO).bound] == ["INTRO"]
    assert [f.id for f in bind("Add 3 new intro classes.", STUDIO).bound] == ["INTRO"]
    assert [f.id for f in bind("Add 3 additional intro classes.", STUDIO).bound] == ["INTRO"]
    assert [f.id for f in bind("You have 4 total instructors.", STUDIO).bound] == ["INS"]


def test_the_noun_is_compared_without_its_plural_and_the_adjectives_in_front_of_it():
    reformers = fs(theirs("CAP", "1", "reformers"))
    assert [f.id for f in bind("You have 1 reformer.", reformers).bound] == ["CAP"]
    assert [f.id for f in bind("You have 1 extra reformer.", reformers).bound] == ["CAP"]
    assert [f.id for f in bind("You have 1 big reformer.", reformers).bound] == ["CAP"]    # more words in front are fine
    assert [f.id for f in bind("A 12-reformer room.", fs(theirs("CAP", "12", "reformers"))).bound] == ["CAP"]
    studies = fs(theirs("S", "3", "studies"))
    assert [f.id for f in bind("You run 3 studies.", studies).bound] == ["S"]
    assert [f.id for f in bind("You run 3 boxes.", fs(theirs("B", "3", "box"))).bound] == ["B"]


def test_a_figure_with_no_noun_takes_a_number_only_when_no_noun_follows_it():
    bare = fs(theirs("A", "4", ""))
    for text in ("You have 4.", "You have 4, ok.", "You have 4 of them."):
        assert [f.id for f in bind(text, bare).bound] == ["A"], text
    for text in ("You have 4 a week.", "You have 4 per class."):   # a rate: nothing for it to contradict
        assert [f.id for f in bind(text, bare).bound] == ["A"], text
    assert bind("Hire 4 more.", bare).bound == []                  # a number that follows a verb
    _stays_unresolved("You have 4 instructors.", bare, "4")
    _stays_unresolved("Hire 4 more instructors.", bare, "4")
    # a figure that names a noun takes a number that names none
    named = fs(theirs("A", "4", "instructors"))
    for text in ("You have 4.", "You have 4 of them.", "Hire 4 more."):
        assert [f.id for f in bind(text, named).bound] == ["A"], text         # a noun unit needs no cue from the verb


def test_derived_capacity_figures_keep_their_own_noun():
    known = fs(derived("CAP-01", "144", "classes", period="week"), derived("CAP-02", "48", "seats", period="week"))
    assert [f.id for f in bind("We run 144 classes a week.", known).bound] == ["CAP-01"]
    _stays_unresolved("We run 144 seats a week.", known, "144")
    _stays_unresolved("We run 144 members.", known, "144")


# -- the addendum: ambiguity is a different printed result, not a different unit ----------------------------------------------------------

HALO = fs(theirs("CF-01", "12", "reformers"), theirs("CF-02", "12", ""), theirs("CF-03", "10", ""))


def test_the_same_value_in_two_units_is_one_answer_when_nothing_tells_them_apart():
    r = bind("10 of 12 are full.", HALO)
    assert r.text == "10 of 12 are full." and r.unresolved == [] and {f.id for f in r.bound} == {"CF-03", "CF-01"}
    r = bind("You have 12 reformers.", HALO)
    assert [f.id for f in r.bound] == ["CF-01"]
    r = bind("You have 12.", HALO)
    assert [f.id for f in r.bound] == ["CF-01"]                  # the same literal either way: lowest id
    r = bind("You have 12 reformers and 10 of 12 are full.", HALO)
    assert r.unresolved == [] and r.text == "You have 12 reformers and 10 of 12 are full."


def test_the_most_trusted_kind_answers_then_the_lowest_id():
    for known in (fs(ours("A", "12", "x"), theirs("Z", "12", "reformers"), derived("M", "12", "y")),
                  fs(theirs("Z", "12", "reformers"), derived("M", "12", "y"), ours("A", "12", "x"))):
        assert [f.id for f in bind("Of the 12 we start.", known).bound] == ["Z"]
    known = fs(derived("B", "12", "x"), derived("A", "12", "y"), ours("C", "12", "z"))
    assert [f.id for f in bind("Of the 12 we start.", known).bound] == ["A"]


def test_figures_that_print_differently_stay_ambiguous():
    _stays_unresolved("Of the 12 we start.", fs(theirs("A", "12", "x"), theirs("B", "12.0", "y")), "12")
    _stays_unresolved("It is $4,700.", fs(theirs("A", "4720", "USD"), derived("B", "4680", "USD")), "$4,700")


# -- 5. speed -----------------------------------------------------------------------------------------------------------------------------

def test_a_hundred_thousand_characters_of_small_numbers_bind_in_seconds():
    known = fs(*[theirs(f"F{i}", str(i + 1), "") for i in range(24)])
    text = "12 " * 33000
    t0 = time.perf_counter()
    r = bind(text, known)
    assert time.perf_counter() - t0 < 8
    assert len(r.bound) == 1 and r.unresolved == []


def test_twenty_thousand_numbers_against_four_hundred_figures_bind_in_seconds():
    known = fs(*[derived(f"F{i}", str(i * 7 + 3), "") for i in range(400)])
    text = " ".join(str(n % 3000) for n in range(20000))
    t0 = time.perf_counter()
    bind(text, known)
    assert time.perf_counter() - t0 < 12


def test_a_figure_in_a_stand_in_noun_takes_whatever_noun_the_number_is_given():
    others = fs(theirs("A", "2", "others"))
    assert [f.id for f in bind("You and two studios nearby.", others).bound] == ["A"]
    assert [f.id for f in bind("Two others nearby.", others).bound] == ["A"]
    _stays_unresolved("It takes 2 days.", others, "2")                       # a time word still needs a time figure


# ==============================================================================================
# Fifth review round, three mechanisms instead of word lists:
#   M1 a rounded figure needs positive approximation evidence (a cue) and nothing that qualifies it
#   M2 every rate or period phrase in the clause must name the figure's own period
#   M3 the noun a partitive counts, and a figure with no unit binds only where a quantity stands
# ==============================================================================================

REV = fs(
    derived("M", "44928", "USD", precision=-3), derived("COST", "7480", "USD", precision=-2),
    derived("REVC", "19950", "USD", precision=-3, period="week"),
    derived("LOSTW", "1953.6", "USD", precision=-1, period="week"),
    derived("LOSTY", "101587.2", "USD", precision=-3, period="year"),
    derived("EMPTY", "182.4", "seats", precision=0, period="week"),
    derived("LEAVE", "9", "members", precision=0, period="month"),
    theirs("CLS", "40", "classes", period="week"), theirs("RENT", "4000", "USD", period="month"),
    theirs("PRICE", "22", "USD"), theirs("OCC", "62", "percent"),
)


# -- M1: a rounded figure binds an exact statement, or a rounding that says it is one ---------------------------

@pytest.mark.parametrize("text, shown", [
    ("Cap spend at $7,500.", "$7,500"),
    ("Spend $7,500.", "$7,500"),                         # a plain rounding, no cue at all
    ("Costs are over ~$45,000.", "$45,000"),
    ("Costs are over about $45,000.", "$45,000"),
    ("Costs have grown past $45,000.", "$45,000"),
    ("Costs are >$45,000.", "$45,000"),
    ("Costs are < $45,000.", "$45,000"),
    ("Costs are $45,000-plus.", "$45,000"),
    ("Costs are $45,000+.", "$45,000"),
    ("Costs are greater than or equal to $45,000.", "$45,000"),
    ("Costs are no less than ~$45,000.", "$45,000"),
    ("Costs of at least about $45,000.", "$45,000"),
    ("Costs top $45,000.", "$45,000"),
    ("Costs pass $45,000.", "$45,000"),
    ("Costs surpass $45,000.", "$45,000"),
    ("Costs are a ceiling of $45,000 now.", "$45,000"),
    ("Costs are $45,000 or more.", "$45,000"),
    ("Costs are $45,000 at most.", "$45,000"),
    ("Costs are $45,000 to the dollar.", "$45,000"),
    ("Costs are south of $45,000.", "$45,000"),
])
def test_a_rounded_figure_is_not_certified_by_a_limit_a_comparison_or_a_bare_rounding(text, shown):
    r = bind(text, REV)
    assert r.text == text and r.bound == [] and [u.text for u in r.unresolved] == [shown], r.text


def test_a_limit_anywhere_before_the_number_takes_away_the_cue():
    for text in ("At the very least, $20,000 a week.", "The clinic brings in, at the very least, about $20,000 a week.",
                 "At worst, about $20,000 a week.", "Spend, at a minimum, around $20,000 a week.",
                 "Revenue tops, say, about $20,000 a week."):
        r = bind(text, REV)
        assert r.text == text and r.bound == [] and [u.text for u in r.unresolved] == ["$20,000"], text
    # with nothing in the way the same cue binds
    r = bind("Revenue is about $20,000 a week.", REV)
    assert [f.id for f in r.bound] == ["REVC"] and r.unresolved == []


def test_an_exactness_word_binds_only_the_exact_value_and_prints_it_as_written():
    for text in ("The clinic brings in precisely $19,950 a week.", "It brings in an exact $19,950 a week.",
                 "It brings in a precise $19,950 a week.", "It brings in $19,950 a week, exactly.",
                 "It brings in $19,950 a week to the dollar."):
        r = bind(text, REV)
        assert r.text == text and [f.id for f in r.bound] == ["REVC"] and r.unresolved == [], text
    for text in ("It brings in precisely $20,000 a week.", "It brings in an exact $20,000 a week."):
        r = bind(text, REV)
        assert r.text == text and r.bound == [] and [u.text for u in r.unresolved] == ["$20,000"], text


def test_the_exact_value_of_a_rounded_figure_is_never_printed_less_exactly():
    for text in ("Costs are $44,928.", "Costs are about $44,928.", "Costs are ~$44,928.", "A $44,928 loss."):
        r = bind(text, REV)
        assert r.text == text and [f.id for f in r.bound] == ["M"], text
    # a true rounding the model wrote stays too: the display would be the coarser number
    r = bind("Revenue is roughly $6,550 a week.", fs(derived("REVW", "6547.2", "USD", precision=-2, period="week")))
    assert r.text == "Revenue is roughly $6,550 a week." and [f.id for f in r.bound] == ["REVW"]


def test_a_rounded_figure_binds_its_own_display_after_a_cue_without_doubling_the_hedge():
    for text in ("Costs are about $45,000.", "Costs are around $45,000.", "Costs are roughly $45,000.",
                 "Costs are approximately $45,000.", "Costs are approx. $45,000.", "Costs are c. $45,000.",
                 "Costs are circa $45,000.", "Costs are an estimated $45,000.", "Costs are some $45,000.",
                 "Costs are ~$45,000.", "Costs are \u2248$45,000.", "Costs are approx. ~$45,000.",
                 "Costs are about ~$45,000.", "Costs are about a $45,000 loss."):
        r = bind(text, REV)
        assert r.text == text and [f.id for f in r.bound] == ["M"] and r.unresolved == [], text


def test_a_token_for_a_rounded_figure_still_prints_its_tilde_unless_a_cue_precedes_it():
    assert bind("Costs are {{F:M}}.", REV).text == "Costs are ~$45,000."
    assert bind("Costs are about {{F:M}}.", REV).text == "Costs are about $45,000."
    assert bind("Costs are approx. {{F:M}}.", REV).text == "Costs are approx. $45,000."


def test_a_limit_word_before_a_token_still_refuses_a_rounded_figure_and_prints_an_exact_one():
    assert bind("Spend at most {{F:PRICE}}.", REV).text == "Spend at most $22."
    for text in ("Costs are over {{F:M}}.", "Cap spend at {{F:COST}}.", "Costs top {{F:M}}."):
        r = bind(text, REV)
        assert r.text == text and r.bound == [], text


# -- M2: every rate or period phrase in the clause names the figure's own period ------------------------------------

@pytest.mark.parametrize("phrase", [
    "$1,950 an hour", "$1,950 per hour", "$1,950 hourly", "$1,950 quarterly", "$1,950 per quarter",
    "$1,950 each quarter", "$1,950 a fortnight", "$1,950 biweekly", "$1,950 per session", "$1,950 per class",
    "$1,950 per member", "$1,950 per diem", "$1,950 a month", "$1,950 a year", "$1,950 daily",
    "$1,950 every other week", "$1,950/mo", "$1,950/class", "$1,950 per term",
])
def test_a_weekly_figure_is_not_bound_by_another_rate_or_period(phrase):
    text = f"You lose about {phrase}."
    r = bind(text, REV)
    assert r.text == text and r.bound == [] and [u.text for u in r.unresolved] == ["$1,950"], text


@pytest.mark.parametrize("text, shown", [
    ("This month, losses are about $1,950.", "$1,950"),
    ("Last month you lost about $1,950.", "$1,950"),
    ("MTD losses are about $1,950.", "$1,950"),
    ("Year to date you lost about $1,950.", "$1,950"),
    ("Losses to date are about $1,950.", "$1,950"),
    ("| Month | about $1,950 |", "$1,950"),
    ("| Per month | about $1,950 |", "$1,950"),
    ("| Monthly | about $1,950 |", "$1,950"),
    ("You run 40 classes per fortnight.", "40"),
    ("You run 40 classes each quarter.", "40"),
    ("You run 40 classes per term.", "40"),
    ("You run 40 classes a month.", "40"),
    ("You run 40 classes per session.", "40"),
    ("You lose about $102,000 per decade.", "$102,000"),
    ("You lose about $102,000 over 5 years.", "$102,000"),
    ("You lose about $102,000 over the lease.", "$102,000"),
    ("You lose about $102,000 over the next three years.", "$102,000"),
    ("You lose about $102,000 a week.", "$102,000"),
    ("You lose about $102,000 per month.", "$102,000"),
])
def test_a_period_figure_is_refused_when_any_phrase_in_the_clause_names_another(text, shown):
    r = bind(text, REV)
    assert r.text == text and r.bound == [] and [u.text for u in r.unresolved][0] == shown, text     # "5 years" is a number too


def test_a_period_figure_binds_when_every_phrase_names_its_own_period():
    for text, ids in (("You lose about $1,950 a week.", ["LOSTW"]), ("You lose about $1,950 each week.", ["LOSTW"]),
                      ("Weekly, you lose about $1,950.", ["LOSTW"]), ("You lose about $1,950/week.", ["LOSTW"]),
                      ("This week you lose about $1,950.", ["LOSTW"]), ("Last week you lost about $1,950.", ["LOSTW"]),
                      ("In a typical week you lose about $1,950.", ["LOSTW"]),
                      ("You lose about $102,000 a year.", ["LOSTY"]), ("Your annual loss is about $102,000.", ["LOSTY"]),
                      ("You run 40 classes a week.", ["CLS"]), ("You run 40 classes per week.", ["CLS"]),
                      ("About 182 seats sit empty a week.", ["EMPTY"]), ("9 members leave every month.", ["LEAVE"]),
                      ("Rent is $4,000 per month.", ["RENT"]), ("| Month | $4,000 |", ["RENT"])):
        r = bind(text, REV)
        assert r.text == text and [f.id for f in r.bound] == ids and r.unresolved == [], text


def test_a_figure_with_no_period_is_never_blocked_by_a_phrase():
    for text in ("The class costs $22 per session.", "The class costs $22 a month.", "Pay $22 each quarter, MTD.",
                 "Occupancy is 62% over the lease."):
        r = bind(text, REV)
        assert r.text == text and r.unresolved == [] and len(r.bound) == 1, text


def test_a_token_is_held_to_every_period_phrase_too():
    for text in ("This month you lose {{F:LOSTW}}.", "You lose {{F:LOSTW}} per session.", "MTD you lost {{F:LOSTW}}.",
                 "You lose {{F:LOSTW}} per decade.", "| Month | {{F:LOSTW}} |"):
        r = bind(text, REV)
        assert r.text == text and r.bound == [] and len(r.unresolved) == 1, text
    assert bind("This week you lose {{F:LOSTW}}.", REV).text == "This week you lose ~$1,950."


# -- M3: the noun a partitive counts, and the figure with no unit ------------------------------------------------------------

REFS = fs(theirs("REF", "12", "reformers"), theirs("EMP", "3", "reformers"), theirs("BOOKED", "4", "reformers"),
          theirs("STAFF", "7", "staff"), theirs("BAKERS", "2", "staff"))
BARE = fs(theirs("U12", "12", ""), theirs("U3", "3", ""), theirs("U4", "4", ""), theirs("U7", "7", ""),
          theirs("U2", "2", ""))


def test_after_of_the_counted_noun_is_the_same_for_both_numbers():
    for text, ids in (("3 of 12 reformers sit empty.", ["EMP", "REF"]),
                      ("Only 4 of your 12 reformers are booked.", ["BOOKED", "REF"]),
                      ("2 of your 7 staff are bakers.", ["BAKERS", "STAFF"]),
                      ("3 of the 12 reformers sit empty.", ["EMP", "REF"]),
                      ("3 of those reformers sit empty.", ["EMP"])):
        r = bind(text, REFS)
        assert r.text == text and [f.id for f in r.bound] == ids and r.unresolved == [], text
    # the noun is the one after "of": a figure in another noun does not bind either number
    r = bind("3 of 12 reformers sit empty.", fs(theirs("A", "3", "staff"), theirs("B", "12", "staff")))
    assert r.bound == [] and [u.text for u in r.unresolved] == ["3", "12"]
    # and a figure with no unit does not bind a number that counts a noun through "of"
    for text in ("3 of 12 reformers sit empty.", "Only 4 of your 12 reformers are booked.", "2 of your 7 staff are bakers."):
        r = bind(text, BARE)
        assert r.bound == [] and r.unresolved, text


def test_a_ratio_or_a_fraction_is_not_two_quantities():
    for text in ("The ratio is 1:10 here.", "Split 3/12 now.", "On 4/12 we start.", "Mix at 4:12 please."):
        for known in (BARE, REFS, REV):
            r = bind(text, known)
            assert r.text == text and r.bound == [] and len(r.unresolved) == 2, (text, [u.text for u in r.unresolved])
    assert bind("The ratio is {{F:U12}}.", BARE).text == "The ratio is 12."       # the whole text as a token is fine


def test_a_figure_with_no_unit_does_not_bind_a_label_a_cell_or_a_name():
    for text in ("**4.** Review pricing.", "| 4 | Review pricing |", "Dial 4", "Room 4", "Hire 4.", "Hire 4 now."):
        r = bind(text, BARE)
        assert r.text == text and r.bound == [] and [u.text for u in r.unresolved] == ["4"], text
    for text in ("- 4. Review pricing", "| Task | 4 |"):
        r = bind(text, BARE)
        assert r.bound == [], text


def test_a_figure_with_no_unit_binds_an_exact_number_where_a_quantity_stands():
    for text in ("You have 4.", "You have 4, then more.", "About 4 of them came.", "There are 4 of them.",
                 "Members: 4", "Only 4.", "It is 4 or more."):
        r = bind(text, BARE)
        assert r.text == text and [f.id for f in r.bound] == ["U4"] and r.unresolved == [], text


def test_a_figure_with_no_unit_does_not_bind_near_a_rate_a_period_or_a_noun_or_a_rounding():
    for text in ("You have 4 instructors.", "You have 4 more instructors.", "You have 4 of your instructors."):
        r = bind(text, BARE)
        assert r.bound == [] and [u.text for u in r.unresolved] == ["4"], text
    known = fs(derived("D4", "4.02", "", precision=2))
    r = bind("You have about 4.", known)                      # a rounding of a figure with no unit
    assert r.bound == [] and [u.text for u in r.unresolved] == ["4"]
    assert [f.id for f in bind("You have 4.02.", known).bound] == ["D4"]


def test_a_mention_with_a_noun_binds_only_a_figure_that_carries_that_noun():
    mixed = fs(theirs("A", "4", ""), theirs("B", "4", "reformers"))
    assert [f.id for f in bind("You have 4 reformers.", mixed).bound] == ["B"]
    assert [f.id for f in bind("You have 4.", mixed).bound] == ["A"]
    assert [f.id for f in bind("You have 4 reformers.", fs(theirs("A", "4", "instructors"))).bound] == []
    assert [f.id for f in bind("You have 4 reformer.", mixed).bound] == ["B"]                 # plural folded


# -- the positive cases and the property ----------------------------------------------------------------------------------------

def test_the_ordinary_statements_still_bind():
    for text, ids in (("A class is $22.", ["PRICE"]), ("Occupancy is 62%.", ["OCC"]), ("You lose about $1,950 a week.", ["LOSTW"]),
                      ("You lose about $102,000 a year.", ["LOSTY"]), ("You have 12 reformers.", None),
                      ("Costs are about $45,000.", ["M"]), ("Costs are ~$45,000.", ["M"])):
        r = bind(text, REV if ids else REFS)
        assert r.text == text and r.unresolved == [], text
        if ids:
            assert [f.id for f in r.bound] == ids, text
    r = bind("You have 12 reformers.", REFS)
    assert [f.id for f in r.bound] == ["REF"]


_FRAGMENTS5 = ["approx.", "c.", "an estimated", "per session", "MTD", "last month", "weekly", "4/12", "1:10", "cap",
               "tops", "of your", "| 4 |", "per fortnight", "each quarter", "at the very least,", "precisely",
               "> ", "3 of 12 reformers", "Dial 4", "**4.**", "$20,000", "$1,950", "$102,000", "182", "40 classes",
               "9 members", "a week", "a year", "over 5 years", "to date"]


def test_binding_twice_is_stable_with_cues_limits_periods_and_ratios():
    import random
    known = fs(*list(REV), *list(REFS), *list(BARE))
    rng = random.Random(51)
    for _ in range(1200):
        text = "".join(rng.choice(_FRAGMENTS + _FRAGMENTS5) + rng.choice([" ", " ", "  "]) for _ in range(rng.randint(1, 8)))
        first = bind(text, known)
        again = bind(first.text, known)
        assert again.text == first.text, (text, first.text, again.text)
        assert {f.id for f in again.bound} == {f.id for f in first.bound}, (text, first.text)
        assert sorted(u.text for u in again.unresolved) == sorted(u.text for u in first.unresolved), (text, first.text)
        for u in first.unresolved:
            assert first.text[u.start:u.end] == u.text, (text, u)


def test_a_comparison_sign_takes_the_cue_away_but_an_arrow_does_not():
    for text in ("Costs are > about $45,000.", "Costs are >= ~$45,000.", "Costs are < about $45,000.",
                 "Costs are \u2265 about $45,000.", "Costs are \u2264 ~$45,000.", "Costs are >~$45,000."):
        r = bind(text, REV)
        assert r.text == text and r.bound == [] and [u.text for u in r.unresolved] == ["$45,000"], text
    for text in ("Costs -> about $45,000.", "Costs => ~$45,000."):
        r = bind(text, REV)
        assert r.text == text and [f.id for f in r.bound] == ["M"], text


# -- the correction: a rate does not hold a figure with no period; each number is held to the phrase next to it -------------

def test_a_figure_with_no_unit_and_no_period_binds_beside_a_rate_or_a_period():
    for text in ("You have 4 a week.", "You have 4 per class.", "You have 4 each month.", "Each week you have 4."):
        r = bind(text, BARE)
        assert r.text == text and [f.id for f in r.bound] == ["U4"] and r.unresolved == [], text


def test_a_figure_with_no_unit_but_a_period_is_held_to_it_like_any_figure():
    weekly = fs(theirs("W4", "4", "", period="week"))
    assert [f.id for f in bind("You have 4 a week.", weekly).bound] == ["W4"]
    assert [f.id for f in bind("You have 4.", weekly).bound] == ["W4"]
    for text in ("You have 4 a month.", "You have 4 per class.", "Each month you have 4."):
        r = bind(text, weekly)
        assert r.text == text and r.bound == [] and [u.text for u in r.unresolved] == ["4"], text


def test_the_partitive_with_a_rate_binds_the_clients_figures_when_no_noun_follows_the_pair():
    halo = fs(theirs("A1-1", "12", "reformers"), theirs("A2-1", "10", ""), theirs("A2-2", "12", ""))
    text = "We track evening fill against 10 of 12 each week."
    r = bind(text, halo)
    assert r.text == text and r.unresolved == [] and [f.id for f in r.bound] == ["A2-1", "A1-1"]
    # a noun after the pair does count, for both numbers
    r = bind("We track evening fill against 10 of 12 reformers each week.", halo)
    assert [f.id for f in r.bound] == ["A1-1"] and [u.text for u in r.unresolved] == ["10"]
    r = bind("We track evening fill against 10 of 12 reformers each week.", fs(theirs("A", "12", "reformers")))
    assert [f.id for f in r.bound] == ["A"] and [u.text for u in r.unresolved] == ["10"]


def test_each_number_is_held_only_to_the_period_phrase_next_to_it():
    both = bind("Empty seats cost you about $1,950 a week, or about $102,000 a year.", REV)
    assert both.text == "Empty seats cost you about $1,950 a week, or about $102,000 a year."
    assert [f.id for f in both.bound] == ["LOSTW", "LOSTY"] and both.unresolved == []
    assert [f.id for f in bind("This month, losses are about $1,950 a week.", REV).bound] == ["LOSTW"]
    assert [f.id for f in bind("Each week, losses are about $1,950 a week.", REV).bound] == ["LOSTW"]
    # no phrase after the number: the nearest one before it speaks
    for text in ("Each month, you lose about $1,950.", "This month, losses are about $1,950.", "MTD losses are about $1,950."):
        r = bind(text, REV)
        assert r.text == text and r.bound == [] and [u.text for u in r.unresolved] == ["$1,950"], text
    # the phrase after a number belongs to that number, not to the one before it
    r = bind("Rent is $1,950 a month and you lose $4,000 a week.", REV)
    assert r.bound == [] and [u.text for u in r.unresolved] == ["$1,950", "$4,000"]
    r = bind("You lose about $1,950 a week and about $102,000 a month.", REV)
    assert [f.id for f in r.bound] == ["LOSTW"] and [u.text for u in r.unresolved] == ["$102,000"]
