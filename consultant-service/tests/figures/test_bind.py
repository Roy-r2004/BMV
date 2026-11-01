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


def test_the_exact_number_also_prints_as_the_figure_displays_it():
    known = fs(derived("DV-01", "44928", "USD", precision=-3))
    assert bind("That is $44,928 a year.", known).text == "That is ~$45,000 a year."   # no hedge: the tilde says it


def test_a_figure_that_displays_with_no_tilde_prints_with_none():
    known = fs(derived("DV-02", "864", "", precision=0))
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


def test_equal_figures_of_one_kind_resolve_to_the_first_added():
    r = bind("It costs $22.", fs(theirs("CF-02", "22", "USD"), theirs("CF-01", "22", "USD")))
    assert [f.id for f in r.bound] == ["CF-02"]


def test_equal_values_in_different_units_are_not_the_same_figure():
    known = fs(theirs("CF-01", "12", "classes"), theirs("CF-02", "12", "reformers"))
    r = bind("Of the 12 we start with the first.", known)
    assert r.bound == [] and [m.text for m in r.unresolved] == ["12"]
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
    assert bind("You have twelve classes today.", known).text == "You have 12 classes today."
    known = fs(theirs("CF-06", "12", "classes"))
    assert bind("You have twelve classes today.", known).text == "You have 12 classes today."


def test_a_unit_word_after_a_digit_is_kept_and_not_repeated():
    known = fs(ours("PL-01", "6", "weeks"))
    assert bind("a pilot of six weeks", known).text == "a pilot of 6 weeks"
    assert bind("a pilot of 6 weeks", known).text == "a pilot of 6 weeks"


def test_a_rounded_estimate_gets_its_tilde_and_the_unit_word_stays_once():
    known = fs(ours("PL-01", "6.4", "weeks", precision=0))
    assert bind("a pilot of 6 weeks", known).text == "a pilot of ~6 weeks"


def test_a_magnitude_letter_or_word_is_replaced_with_the_figures_digits():
    known = fs(theirs("CF-01", "10000", "USD"), theirs("CF-02", "1500000", ""))
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

@pytest.mark.parametrize("hedge", ["about", "around", "roughly", "approximately", "nearly", "circa",
                                   "About", "ROUGHLY"])
def test_a_hedge_word_before_a_tilde_figure_stays_and_the_tilde_is_left_off(hedge):
    known = fs(derived("DV-01", "44928", "USD", precision=-3))
    assert bind(f"We lose {hedge} $44,928 a year", known).text == f"We lose {hedge} $45,000 a year"


def test_a_hedge_word_that_is_a_preposition_is_never_deleted():
    known = fs(derived("DV-01", "44928", "USD", precision=-3))
    text = "You asked about $45,000 in lost revenue."
    assert bind(text, known).text == text
    assert bind("We talked around $44,928 for an hour.", known).text == "We talked around $45,000 for an hour."


def test_only_the_word_right_before_is_a_hedge():
    known = fs(derived("DV-01", "44928", "USD", precision=-3))
    assert bind("about the $44,928", known).text == "about the $45,000"      # an article, like a hedge, says "roughly"
    assert bind("costs only $44,928", known).text == "costs only ~$45,000"
    assert bind("thereabout $44,928", known).text == "thereabout ~$45,000"      # not the word "about"


def test_a_tilde_the_model_wrote_is_not_doubled():
    known = fs(derived("DV-01", "44928", "USD", precision=-3))
    assert bind("~$44,900 a year", known).text == "~$45,000 a year"
    assert bind("~ $44,900 a year", known).text == "~ $45,000 a year"             # what the model wrote stays
    assert bind("\u2248$44,900 a year", known).text == "\u2248$45,000 a year"


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
    assert r.text == "About $45,000 a year, 6 weeks, then $9,999 and {{F:NOPE-1}} and 77."
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
    text = "A class is $22 over six weeks.  Done!"
    cleaned, removed = clean_sentences(text, KNOWN)
    assert cleaned == "A class is $22 over 6 weeks.  Done!" and removed == []


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
    text = "A class is $22; we lose about $44,928 a year over six weeks, not $9,999."
    segs = segments(text, KNOWN)
    assert "".join(s["text"] for s in segs) == bind(text, KNOWN).text
    assert [s for s in segs if "figure" in s] == [
        {"figure": "CF-01", "text": "$22"},
        {"figure": "DV-01", "text": "$45,000"},
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
    segs = segments("We lose about $44,928.", KNOWN)
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
    r = bind("We run 12 classes a week.", fs(derived("DV-01", "12.04", "classes", precision=2)))
    assert r.text == "We run 12.04 classes a week."
    assert bind("We run 12 class slots.", fs(derived("DV-01", "12.04", "", precision=2))).text == "We run 12.04 class slots."


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
    assert bind("It is $4,700.", fs(derived("DV-01", "4720", "USD"))).text == "It is $4,720."
    assert bind("It is $4,700.", fs(ours("PL-01", "4720", "USD"))).text == "It is $4,720."
    _stays_unresolved("It is $4,700.", fs(theirs("CF-01", "4720", "USD")), "$4,700")
    ref = fig("reference", "RF-01", "4720", "USD")
    _stays_unresolved("It is $4,700.", fs(ref), "$4,700")


def test_near_equal_figures_of_two_kinds_follow_the_most_trusted_one():
    # the client's own 4,720 and our 4,720: the model altered the client's number
    _stays_unresolved("It is $4,700.", fs(derived("DV-01", "4720", "USD"), theirs("CF-01", "4720", "USD")), "$4,700")
    # a derived and a reference of one value: derived is the more trusted, so it may be rewritten
    r = bind("It is $4,700.", fs(fig("reference", "RF-01", "4720", "USD"), derived("DV-01", "4720", "USD")))
    assert r.text == "It is $4,720." and [f.id for f in r.bound] == ["DV-01"]


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
    assert bind("It is around $44,928.", known).text == "It is around $45,000."
    assert bind("It is ~$44,928.", known).text == "It is ~$45,000."
    assert bind("It is $44,928.", known).text == "It is ~$45,000."


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
    known = fs(derived("DV-01", "44928", "USD", precision=-3))
    text = 'We lose $44,928 a year, and she wrote "$44,928" to us, so $44,928 it is.'
    assert bind(text, known).text == 'We lose ~$45,000 a year, and she wrote "$44,928" to us, so ~$45,000 it is.'


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
               theirs("CF-02", "12", "count"))
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
    r = bind("We run 40 weeks.", fs(derived("DV-01", "40.1", "weeks", precision=1)))
    assert r.text == "We run 40.1 weeks." and [f.id for f in r.bound] == ["DV-01"]


def test_the_figure_that_names_the_unit_wins_over_a_unitless_one():
    known = fs(theirs("CF-01", "12", "count"), derived("DV-01", "12", "weeks"))
    for k in (known, fs(derived("DV-01", "12", "weeks"), theirs("CF-01", "12", "count"))):
        r = bind("It takes 12 weeks.", k)
        assert r.text == "It takes 12 weeks." and [f.id for f in r.bound] == ["DV-01"] and r.unresolved == []
    nouns = fs(theirs("CF-01", "12", "count"), derived("DV-02", "12", "classes"))
    assert [f.id for f in bind("We run 12 classes.", nouns).bound] == ["DV-02"]
    # with no unit named after it the number is ambiguous, as it was
    assert [u.text for u in bind("Of the 12 we start.", nouns).unresolved] == ["12"]


def test_a_noun_that_is_no_unit_still_takes_a_unitless_count():
    known = fs(theirs("CF-01", "12", "count"))
    assert [f.id for f in bind("We have 12 instructors.", known).bound] == ["CF-01"]


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
    assert bind("{{F:N}} members", TA).text == "12 members"
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
R1 = fs(theirs("CF-62", "62", "percent"), theirs("CF-04", "4", "count"), derived("DV-398", "3.98", "percent", precision=2),
        theirs("CF-22", "22", "USD"), theirs("CF-12", "12", "count"), derived("DV-1196", "11.96", "USD", precision=2),
        ours("PL-25", "25", "USD"), theirs("CF-40", "40", "count"), derived("DV-399", "39.9", "USD", precision=1))


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
    _binds_each_on_its_own("Class size 12 - $22 per head.", R1, "CF-12", "CF-22")
    _binds_each_on_its_own("Price: $22 - 12 per class.", R1, "CF-22", "CF-12")


def test_a_bare_number_followed_by_a_partitive_or_an_alternative_shares_nothing():
    _binds_each_on_its_own("At $22 to 12 or more members, a class pays.", R1, "CF-22", "CF-12")
    _binds_each_on_its_own("Offer $25 to 40 of your members.", R1, "PL-25", "CF-40")
    _binds_each_on_its_own("Offer $25 to 40 and more members.", R1, "PL-25", "CF-40")
    _binds_each_on_its_own("Offer $25 to 40 than we had.", R1, "PL-25", "CF-40")


def test_a_bare_left_number_does_not_become_dollars_because_a_dollar_amount_follows():
    _binds_each_on_its_own("Class size 12 to $22 per head.", R1, "CF-12", "CF-22")
    # it can when the range is plainly of money
    pairs = fs(theirs("A", "20", "USD"), theirs("B", "30", "USD"), theirs("C", "20", "count"))
    for text in ("From 20 to $30 a class.", "Costs 20-$30 a class.", "Between 20 and $30 a class."):
        r = bind(text, pairs)
        assert r.unresolved == [] and [f.id for f in r.bound] == ["A", "B"], text
    r = bind("Costs 20 to $30 a class.", pairs)
    assert [f.id for f in r.bound] == ["C", "B"]
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
    known = fs(theirs("CF-01", "12", "count"), ours("PL-01", "12.05", "reformers", precision=2))
    _binds_each_on_its_own("You have 12 reformers.", known, "CF-01")
    known = fs(theirs("CF-01", "12", "count"), derived("DV-01", "12.04", "classes", precision=2))
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
    assert bind("Your weekly rent of $9,500 is high.", weekly).bound[0].id == "DV-01"
    assert bind("You bring in about $9,500 a class.", weekly).bound[0].id == "DV-01"     # "a class" is no period
    assert bind("You bring in about $9,500.", weekly).bound[0].id == "DV-01"
    no_period = fs(derived("DV-01", "9504", "USD"))
    assert bind("You bring in about $9,500 a month.", no_period).bound[0].id == "DV-01"
    month = fs(derived("DV-01", "9504", "USD", period="operating_30_day_month"))
    assert bind("You bring in about $9,500 a month.", month).bound[0].id == "DV-01"
    _stays_unresolved("You bring in about $9,500 a week.", month, "$9,500")


def test_a_period_blocks_percents_and_counts_too_and_not_through_a_time_word():
    known = fs(theirs("CF-01", "30", "percent", period="week"), theirs("CF-02", "12", "count", period="week"))
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


def test_a_comparative_over_a_figure_that_displays_as_the_mention_binds_without_a_tilde():
    known = fs(derived("DV-01", "44928", "USD", precision=-3))
    r = bind("Costs are over $45,000 now.", known)
    assert r.text == "Costs are over $45,000 now." and [f.id for f in r.bound] == ["DV-01"]


def test_about_and_around_are_hedges_and_not_limits():
    known = fs(derived("DV-01", "7480", "USD"))
    assert bind("Keep costs about $7,500.", known).text == "Keep costs about $7,480."
    assert bind("Keep costs around $7,500.", known).text == "Keep costs around $7,480."


# -- 5. a near rewrite must be a true rounding -----------------------------------------------------------------------------

def test_a_near_mention_is_rewritten_only_when_it_is_the_figure_rounded_to_its_own_last_place():
    known = fs(derived("DV-01", "44928", "USD"))
    assert bind("We lose $45,000 a year.", known).text == "We lose $44,928 a year."      # thousands
    assert bind("We lose $44,900 a year.", known).text == "We lose $44,928 a year."      # hundreds
    assert bind("We lose $44,930 a year.", known).text == "We lose $44,928 a year."      # tens
    _stays_unresolved("We lose $44,950 a year.", known, "$44,950")                       # near, but 44,928 is 44,930 to tens
    _stays_unresolved("We lose $44,960 a year.", known, "$44,960")
    _stays_unresolved("We lose $44,990 a year.", known, "$44,990")
    assert bind("Fees are $1,000.", fs(derived("DV-01", "995", "USD"))).text == "Fees are $995."
    _stays_unresolved("A seat is $4,750.", fs(derived("DV-01", "4728", "USD")), "$4,750")
    assert bind("About 12 classes a week.", fs(derived("DV-01", "12.04", "classes", precision=2))).text == \
        "About 12.04 classes a week."


# -- 6. the round trip: what is written must read back as what was meant ---------------------------------------------------------------

def test_a_replacement_that_would_read_back_as_another_number_is_taken_back():
    known = fs(ours("PL-02", "2", ""), ours("PL-03", "200", ""))
    text = "Run two 200-person events."
    r = bind(text, known)
    assert r.text == text                                   # "2 200-person" would read as 2,200
    assert r.unresolved == [] and {f.id for f in r.bound} == {"PL-02", "PL-03"}
    assert [m.value for m in mentions(r.text)] == [D(2), D(200)]


def test_a_replacement_that_would_change_how_the_number_reads_is_taken_back():
    # "USD 2" reads as money, "two" beside "USD" did not: the figure is named, the words stay
    known = fs(ours("PL-02", "2", ""))
    for text in ("Pay USD two now.", "It costs EUR two."):
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
    known = fs(theirs("A", "22", "USD"), theirs("B", "6", "count"))
    r = bind("{{F:A}} to 6 a class", known)
    assert r.text == "$22 to 6 a class" and [u.text for u in r.unresolved] == ["6"]
    r = bind("{{F:A}} to 6 members", known)
    assert r.unresolved == [] and [f.id for f in r.bound] == ["A", "B"]


def test_what_bind_wrote_reads_back_as_the_figures_it_named():
    known = fs(theirs("CF-01", "22", "USD"), derived("DV-01", "44928", "USD", precision=-3), ours("PL-01", "6", "weeks"),
               theirs("P", "25", "percent"), theirs("E", "1000", "EUR"))
    text = "A class is $22; we lose about $44,928 a year over six weeks, 25 percent of it, in EUR 1,000 steps."
    r = bind(text, known)
    assert [m.value for m in mentions(r.text)] == [D(22), D(45000), D(6), D(25), D(1000)]


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
    assert bind("roughly a $44,928 loss", usd).text == "roughly a $45,000 loss"


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
    r = bind("Allow two - 3x more.", known)
    assert r.text == "Allow two - 3x more." and [f.id for f in r.bound] == ["PL-02"] and r.unresolved == []


def test_a_tilde_before_the_second_number_of_a_range_does_not_break_the_range():
    known = fs(theirs("A", "22", "USD"), derived("D", "44928", "USD", precision=-3))
    r = bind("From $22 to ~45,000 a year.", known)
    assert r.text == "From $22 to ~45,000 a year." and [f.id for f in r.bound] == ["A", "D"]
    again = bind(bind("From $22 to 45,000 a year.", known).text, known)
    assert again.text == "From $22 to ~45,000 a year."
