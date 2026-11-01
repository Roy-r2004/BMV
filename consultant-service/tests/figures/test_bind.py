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

from decimal import Decimal

import pytest

from app.figures import bind as B
from app.figures.bind import BindResult, UnresolvedToken, bind, clean_sentences, segments
from app.figures.model import (
    Figure, FigureSet, Proposal, Reference, TheirsSource, Working, display_number, from_claim,
)
from app.figures.read import Mention, mentions

D = Decimal


# -- builders ------------------------------------------------------------------

def _digits_after_point(value: str) -> int:
    return max(0, -D(value).as_tuple().exponent)


def fig(kind: str, fid: str, value: str, unit: str = "", precision: int | None = None) -> Figure:
    p = _digits_after_point(value) if precision is None else precision
    source = {
        "theirs": TheirsSource(turn=1, field=None, quote=f"{value} {unit}", file=None, cell=None),
        "derived": Working(inputs=(), op="mul", text="worked out"),
        "ours": Proposal(note="we propose it"),
        "reference": Reference(publication="Survey", year=2024, population="studios", url="https://example.org"),
    }[kind]
    return Figure(id=fid, value=D(value), unit=unit, period=None, kind=kind, source=source, precision=p)


def theirs(fid, value, unit="", precision=None):
    return fig("theirs", fid, value, unit, precision)


def derived(fid, value, unit="", precision=None):
    return fig("derived", fid, value, unit, precision)


def ours(fid, value, unit="", precision=None):
    return fig("ours", fid, value, unit, precision)


def fs(*figures: Figure) -> FigureSet:
    return FigureSet(figures)


def assert_spans_hold(result: BindResult) -> None:
    """Every unresolved record points at its own text inside the bound text."""
    for u in result.unresolved:
        assert result.text[u.start:u.end] == u.text, u


# -- a rounded number prints the figure's own value (Task 3 brief) -------------------

def test_a_rounded_mention_prints_the_figures_own_display():
    known = fs(derived("DV-01", "44928", "USD", precision=-3))
    r = bind("We lose about $45,000 a year.", known)
    assert r.text == "We lose ~$45,000 a year."          # the figure's display; "about" would double the hedge
    assert [f.id for f in r.bound] == ["DV-01"]
    assert r.unresolved == []


def test_the_exact_number_also_prints_as_the_figure_displays_it():
    known = fs(derived("DV-01", "44928", "USD", precision=-3))
    assert bind("That is $44,928 a year.", known).text == "That is ~$45,000 a year."


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


def test_the_same_rounding_near_only_one_figure_binds_to_it():
    known = fs(theirs("CF-01", "4720", "USD"))
    r = bind("About $4,700 a month goes missing.", known)
    assert r.text == "About $4,720 a month goes missing."   # theirs is exact: no tilde, no re-rounding
    assert [f.id for f in r.bound] == ["CF-01"]


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
    known = fs(ours("PL-01", "12", "weeks"), theirs("CF-02", "12", "reformers"))
    r = bind("Of the 12 we start with the first.", known)
    assert r.bound == [] and [m.text for m in r.unresolved] == ["12"]


# -- a theirs figure is never re-rounded -------------------------------------------------

def test_a_theirs_figure_prints_exactly_as_the_client_gave_it():
    known = fs(theirs("CF-01", "22.50", "USD"), theirs("CF-02", "1250", "USD"))
    assert bind("a class is $22.5", known).text == "a class is $22.50"
    assert bind("a class is $22.50", known).text == "a class is $22.50"


def test_a_theirs_figure_within_tolerance_replaces_the_models_rounding_without_a_tilde():
    r = bind("Roughly $1,247 a month.", fs(theirs("CF-02", "1250", "USD")))
    assert r.text == "Roughly $1,250 a month."


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


def test_a_money_mention_may_bind_to_a_figure_with_no_unit_and_keeps_its_dollar_sign():
    r = bind("a $25 fee", fs(theirs("CF-03", "25", "")))
    assert r.text == "a $25 fee" and [f.id for f in r.bound] == ["CF-03"]


def test_a_percent_mention_does_not_bind_to_a_money_figure():
    r = bind("a 25% fee", fs(theirs("CF-03", "25", "USD")))
    assert r.bound == [] and [m.text for m in r.unresolved] == ["25%"]


# -- only the number is replaced -----------------------------------------------------------

def test_a_number_word_becomes_digits_and_the_unit_word_after_it_is_kept():
    known = fs(theirs("CF-06", "12", "reformers"))
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
def test_a_hedge_word_before_a_tilde_figure_is_dropped(hedge):
    known = fs(derived("DV-01", "44928", "USD", precision=-3))
    assert bind(f"We lose {hedge} $44,928 a year", known).text == "We lose ~$45,000 a year"


def test_only_the_word_right_before_is_a_hedge():
    known = fs(derived("DV-01", "44928", "USD", precision=-3))
    assert bind("about the $44,928", known).text == "about the ~$45,000"
    assert bind("costs only $44,928", known).text == "costs only ~$45,000"
    assert bind("thereabout $44,928", known).text == "thereabout ~$45,000"      # not the word "about"


def test_a_tilde_the_model_wrote_is_not_doubled():
    known = fs(derived("DV-01", "44928", "USD", precision=-3))
    assert bind("~$44,900 a year", known).text == "~$45,000 a year"
    assert bind("~ $44,900 a year", known).text == "~$45,000 a year"
    assert bind("\u2248$44,900 a year", known).text == "~$45,000 a year"


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
    assert bind("about {{F:DV-01}} a year", known).text == "~$45,000 a year"


def test_a_token_with_spaces_inside_is_still_a_token():
    known = fs(theirs("CF-01", "22", "USD"))
    assert bind("{{ F: CF-01 }} a class", known).text == "$22 a class"


# -- times, dates, labels, and the kinds that are never rewritten -----------------------------------

def test_dates_labels_and_times_are_left_alone():
    text = "We open at 9am on 31 Oct 2025 for Phase 2 (page 7, Exhibit 2.1) in Q3."
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
    "See Phase two of the plan, Q3 and CF-04.",
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
    assert r.text == "~$45,000 a year, 6 weeks, then $9,999 and {{F:NOPE-1}} and 77."
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
    assert cleaned == "We lose ~$45,000 a year. We start in March."
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
    cleaned, removed = clean_sentences("We start in week 4. Then $777 follows. End.", KNOWN)
    assert removed == ["We start in week 4.", "Then $777 follows."] and cleaned == "End."


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
        {"figure": "DV-01", "text": "~$45,000"},
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


def test_segments_after_a_hedge_drop_still_join_exactly():
    segs = segments("We lose about $44,928.", KNOWN)
    assert "".join(s["text"] for s in segs) == "We lose ~$45,000."
    assert segs[0] == {"text": "We lose "}


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
