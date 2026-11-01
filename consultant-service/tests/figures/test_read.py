"""The number reader and checker (Step 2, Task 2).

`mentions` reads every number a sentence holds, by the grammar of plan ruling 8:
digits, money, percents, k/M suffixes, ranges (both ends), multipliers, digit
ordinals, number words from two up and word ordinals from third up. It does not
count "one", "a", "an", "first" or "second", a digit right after a label word
(ruling 4), an identifier such as Q3 or CF-04, or page furniture. Clock times
and dates are read with their own forms, so the checker can treat them apart.

`unsupported` returns every mention no known figure supports. There is no
leniency: a small number is a number.

Every non-ASCII character below is written as an escape so the file stays ASCII.
"""
from __future__ import annotations

import ast
import inspect
import os
from decimal import Decimal

import pytest

from app.figures import read as R
from app.figures.model import Figure, FigureSet, TheirsSource, Working, from_claim
from app.figures.read import Mention, mentions, supported, unsupported

D = Decimal
NOTHING = FigureSet()


def theirs(fid: str, value: str, unit: str = "") -> Figure:
    v = D(value)
    return Figure(id=fid, value=v, unit=unit, period=None, kind="theirs",
                  source=TheirsSource(turn=1, field=None, quote=f"{value} {unit}", file=None, cell=None),
                  precision=max(0, -v.as_tuple().exponent))


def derived(fid: str, value: str, unit: str = "", precision: int = 0) -> Figure:
    return Figure(id=fid, value=D(value), unit=unit, period=None, kind="derived",
                  source=Working(inputs=(), op="mul", text="worked"), precision=precision)


def values(ms: list[Mention]) -> list[Decimal]:
    return [m.value for m in ms]


# -- must flag: every row of recon 1.3 that passes today, and more -------------------

MUST_FLAG = [
    # (text, values, forms)
    ("twelve classes", ["12"], ["word"]),
    ("a dozen spots", ["12"], ["word"]),
    ("half a dozen", ["6"], ["word"]),
    ("twenty-two", ["22"], ["word"]),
    ("twenty two", ["22"], ["word"]),
    ("3x more bookings", ["3"], ["multiplier"]),
    ("3\u00d7 more bookings", ["3"], ["multiplier"]),
    ("threefold", ["3"], ["multiplier"]),
    ("twice", ["2"], ["multiplier"]),
    ("the 3rd phase", ["3"], ["ordinal"]),
    ("1st week", ["1"], ["ordinal"]),
    ("8 hrs a week", ["8"], ["digit"]),
    ("12 reformers", ["12"], ["digit"]),
    ("2-3 weeks", ["2", "3"], ["range", "range"]),
    ("six-week pilot", ["6"], ["word"]),
    ("1.5 hours", ["1.5"], ["digit"]),
    ("0.5", ["0.5"], ["digit"]),
    ("one in 20", ["20"], ["digit"]),
    ("$35", ["35"], ["money"]),
    ("50%", ["50"], ["percent"]),
    ("10k", ["10000"], ["digit"]),
    ("$1.2M", ["1200000"], ["money"]),
    # more of the same grammar
    ("bookings doubled", ["2"], ["multiplier"]),
    ("triple the members", ["3"], ["multiplier"]),
    ("a tenfold rise", ["10"], ["multiplier"]),
    ("a three-fold rise", ["3"], ["multiplier"]),
    ("a 3-fold rise", ["3"], ["multiplier"]),
    ("3 \u00d7 more", ["3"], ["multiplier"]),
    ("the third week", ["3"], ["ordinal"]),
    ("the twenty-first booking", ["21"], ["ordinal"]),
    ("the 22nd member", ["22"], ["ordinal"]),
    ("a hundred and twenty members", ["120"], ["word"]),
    ("one hundred members", ["100"], ["word"]),
    ("thirty-five thousand a year", ["35000"], ["word"]),
    ("two dozen mats", ["24"], ["word"]),
    ("two and a half weeks", ["2.5"], ["word"]),
    ("fifty percent", ["50"], ["percent"]),
    ("35,000 a year", ["35000"], ["digit"]),
    ("1,000 members", ["1000"], ["digit"]),
    ("1,234,567 views", ["1234567"], ["digit"]),
    ("3.5 stars", ["3.5"], ["digit"]),
    ("$4,700", ["4700"], ["money"]),
    ("$22.50 a class", ["22.50"], ["money"]),
    ("\u20ac50 a class", ["50"], ["money"]),
    ("\u00a350 a class", ["50"], ["money"]),
    ("US$35", ["35"], ["money"]),
    ("35 USD", ["35"], ["money"]),
    ("forty dollars", ["40"], ["money"]),
    ("$35k", ["35000"], ["money"]),
    ("$2bn", ["2000000000"], ["money"]),
    ("1.5 million views", ["1500000"], ["digit"]),
    ("5M users", ["5000000"], ["digit"]),
    ("25 percent", ["25"], ["percent"]),
    ("25 per cent", ["25"], ["percent"]),
    ("25 %", ["25"], ["percent"]),
    ("down -5% on last year", ["-5"], ["percent"]),
    ("a change of \u22125", ["-5"], ["digit"]),
    ("(12 reformers)", ["12"], ["digit"]),
    ("24GB of memory", ["24"], ["digit"]),
    ("5m away", ["5"], ["digit"]),
    ("2 to 3 weeks", ["2", "3"], ["range", "range"]),
    ("2\u20133 weeks", ["2", "3"], ["range", "range"]),
    ("10-15% more", ["10", "15"], ["percent", "percent"]),
    ("$20-$30 a class", ["20", "30"], ["money", "money"]),
    ("10-15k a month", ["10000", "15000"], ["range", "range"]),
    ("weeks 1-2", ["1", "2"], ["range", "range"]),   # lower case, no reference lead: not a plan position
    ("2000-3000 members", ["2000", "3000"], ["range", "range"]),
    ("2,025 members", ["2025"], ["digit"]),
    ("$2025", ["2025"], ["money"]),
    ("1 of 5 explanations", ["1", "5"], ["digit", "digit"]),
    ("zero and 0", ["0", "0"], ["word", "digit"]),
    ("covers .5 of it", ["0.5"], ["digit"]),
    ("12 reformers and twelve mats", ["12", "12"], ["digit", "word"]),
    ("6 classes a day, six days a week", ["6", "6"], ["digit", "word"]),
    ("the 3 Decisions", ["3"], ["digit"]),   # "Dec" is a month only as a whole word
    ("may 3 times", ["3"], ["digit"]),       # a month name is a proper noun, capitalised
]


@pytest.mark.parametrize("text,want,forms", MUST_FLAG, ids=[t for t, _, _ in MUST_FLAG])
def test_must_flag(text, want, forms):
    found = unsupported(text, NOTHING)
    assert values(found) == [D(v) for v in want]
    assert [m.form for m in found] == forms


# -- must not flag --------------------------------------------------------------------

MUST_NOT_FLAG = [
    "one of the explanations",
    "no one",
    "the first week",
    "a second",
    "a week",
    "an hour",
    "Phase 2",
    "Step 3",
    "Exhibit 2.1",
    "in 2025",
    "31 Oct",
    "6pm",
    # more of the same grammar
    "Phases 1-2",
    "work starts in phase 2",
    "Phase two",
    "see Table 4",
    "Option 3",
    "Appendix 2",
    "Section 3.2.1",
    "Q3",
    "Q3 2025",
    "M3-A",
    "CF-04",
    "B2B",
    "v2.1 ships. Q3.",
    "on Oct 31, 2025",
    "the 3rd of March",
    "31st October",
    "March 3rd",
    "18:00",
    "6:30 pm",
    "6 p.m.",
    "the 6-7pm slot",
    "9am to 5pm",
    "the 1990s",
    "2025-03-01",
    "31/10/2025",
    "in 2025-2026",
    "seconds count",
    "hundreds of people",
    "dozens of people",
    "double-check it",
    "first and second",
    "one",
    "Marketing",
    "a minute",
]


@pytest.mark.parametrize("text", MUST_NOT_FLAG)
def test_must_not_flag(text):
    assert unsupported(text, NOTHING) == []


def test_a_clock_time_is_checked_against_the_hours_they_gave():
    assert unsupported("6pm", NOTHING, hours=None) == []
    assert unsupported("6pm", NOTHING, hours={18}) == []
    late = unsupported("6pm", NOTHING, hours={9})
    assert [(m.form, m.value) for m in late] == [("time", D(18))]
    assert values(unsupported("at 6:30 pm and 18:00", NOTHING, hours={9})) == [D(18), D(18)]
    assert values(unsupported("12am", NOTHING, hours={9})) == [D(0)]
    assert values(unsupported("12pm", NOTHING, hours={9})) == [D(12)]
    assert values(unsupported("11-1pm", NOTHING, hours={2})) == [D(11), D(13)]


def test_times_and_dates_have_their_own_forms():
    forms = [(m.text, m.form) for m in mentions("On 31 Oct 2025 at 6pm, then 18:00.")]
    assert forms == [("31 Oct", "date"), ("2025", "date"), ("6pm", "time"), ("18:00", "time")]


# -- the mentions themselves ------------------------------------------------------------

def test_mentions_are_in_text_order_with_exact_spans():
    text = ("We run twelve classes, 8 hrs a week, at $35 (50% full); Phase 2 adds 2-3 weeks "
            "and a 3x lift, the 3rd in 2025, one in 20.")
    ms = mentions(text)
    assert [m.text for m in ms] == ["twelve", "8", "$35", "50%", "2", "3", "3x", "3rd", "2025", "20"]
    for m in ms:
        assert text[m.start:m.end] == m.text
        assert isinstance(m.value, Decimal)
    assert [m.start for m in ms] == sorted(m.start for m in ms)


def test_a_range_gives_one_mention_per_end():
    ms = mentions("2-3 weeks")
    assert [(m.text, m.start, m.end, m.value, m.form) for m in ms] == [
        ("2", 0, 1, D(2), "range"), ("3", 2, 3, D(3), "range")]


def test_a_number_at_the_end_of_a_sentence_keeps_its_period_out():
    text = "We have 12. Then 3.5. Then $35."
    ms = mentions(text)
    assert [m.text for m in ms] == ["12", "3.5", "$35"]
    assert [m.value for m in ms] == [D(12), D("3.5"), D(35)]


def test_mention_is_frozen():
    m = mentions("12")[0]
    with pytest.raises(Exception):
        m.value = D(13)  # type: ignore[misc]


def test_words_spans_cover_the_whole_phrase():
    text = "half a dozen and a hundred and twenty"
    assert [(m.text, m.value) for m in mentions(text)] == [("half a dozen", D(6)), ("a hundred and twenty", D(120))]


def test_a_percent_mention_reads_the_percent_number():
    assert [(m.text, m.value) for m in mentions("25 percent of 50%")] == [("25 percent", D(25)), ("50%", D(50))]


# -- supported ----------------------------------------------------------------------------

def test_a_rounding_of_a_derived_figure_is_supported():
    known = FigureSet([derived("rev", "44928", "USD", precision=-3)])
    assert unsupported("about 45,000", known) == []


def test_a_percent_is_compared_as_the_percent_number():
    known = FigureSet([theirs("share", "25", "percent")])
    assert unsupported("25%", known) == []
    assert unsupported("25 percent", known) == []
    assert values(unsupported("26%", known)) == [D(26)]


def test_a_percent_binds_to_a_claim_stored_as_a_fraction():
    claim = {"id": "CF1", "type": "client_fact", "value": 0.25, "unit": "%", "provenance": "client_input",
             "approval_status": "client_stated", "source": "client brief", "text": "a quarter come back"}
    known = FigureSet([from_claim(claim)])
    assert unsupported("25%", known) == []
    assert unsupported("25 per cent", known) == []


def test_a_number_word_is_supported_by_their_figure():
    known = FigureSet([theirs("reformers", "12", "reformers")])
    assert unsupported("twelve", known) == []
    assert unsupported("you have twelve reformers", known) == []


def test_a_rounding_near_two_figures_is_supported_here_and_left_to_bind():
    # $4,700 sits within half a percent of both 4,720 and 4,680. The reader says
    # it is supported (some figure matches); refusing to pick one of two
    # different values is bind's job (Task 3), not the reader's.
    known = FigureSet([theirs("a", "4720", "USD"), theirs("b", "4680", "USD")])
    ms = mentions("$4,700")
    assert [(m.value, m.form) for m in ms] == [(D(4700), "money")]
    assert [f.id for f in known.match(ms[0].value)] == ["a", "b"]
    assert supported(ms[0], known) is True
    assert unsupported("$4,700", known) == []


def test_money_needs_a_money_figure_when_the_figure_has_a_unit():
    m = mentions("$35")[0]
    assert supported(m, FigureSet([theirs("price", "35", "USD")])) is True
    assert supported(m, FigureSet([theirs("price", "35", "")])) is True
    assert supported(m, FigureSet([theirs("mats", "35", "reformers")])) is False
    assert supported(m, FigureSet([theirs("share", "35", "percent")])) is False


def test_a_percent_needs_a_percent_figure_when_the_figure_has_a_unit():
    m = mentions("35%")[0]
    assert supported(m, FigureSet([theirs("share", "35", "percent")])) is True
    assert supported(m, FigureSet([theirs("share", "35", "")])) is True
    assert supported(m, FigureSet([theirs("price", "35", "USD")])) is False


def test_other_forms_need_a_figure_of_their_value():
    known = FigureSet([theirs("r", "12", "reformers"), theirs("w", "3", "weeks")])
    assert unsupported("12 reformers for 2-3 weeks and a 3x lift, the 3rd", known) == [
        mentions("12 reformers for 2-3 weeks")[1]]


def test_a_time_is_supported_by_hours_and_a_date_by_its_form():
    t = mentions("6pm")[0]
    assert (t.form, t.value) == ("time", D(18))
    assert supported(t, NOTHING) is True
    assert supported(t, NOTHING, hours={18}) is True
    assert supported(t, NOTHING, hours={9}) is False
    for text in ("in 2025", "31 Oct"):
        d = mentions(text)[0]
        assert d.form == "date" and supported(d, NOTHING) is True


def test_unsupported_has_no_leniency_parameter():
    params = inspect.signature(unsupported).parameters
    assert list(params) == ["text", "known", "hours"]
    assert params["hours"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["hours"].default is None
    # the old checker skipped anything below 2; this one does not
    assert values(unsupported("one of 1 explanations", NOTHING)) == [D(1)]


def test_empty_and_numberless_text():
    assert mentions("") == []
    assert mentions("No numbers here at all.") == []
    assert unsupported("", NOTHING) == []


# -- controller rulings after review --------------------------------------------------------

# 1. a numbered list marker first on its line is structure, not a number

def test_a_list_marker_is_not_a_mention():
    assert mentions("1. Book the studio") == []
    text = "The plan:\n1. Book the studio\n  2) Call 12 members\n\t3. Open in 2 weeks\n10. Review"
    assert [m.text for m in mentions(text)] == ["12", "2"]


@pytest.mark.parametrize("text,want", [
    ("We have 1. Then more", ["1"]),        # mid-line, not a marker
    ("1.5 hours a day", ["1.5"]),           # a decimal, not a marker
    ("12 reformers", ["12"]),               # no point after it
    ("Plan:\n3 classes a day", ["3"]),      # first on its line, but no point
    ("1.Book the studio", ["1"]),           # no space after the point
])
def test_a_number_that_is_not_a_list_marker_still_counts(text, want):
    assert [m.text for m in mentions(text)] == want


# 2. double and triple are factors only before what they multiply

@pytest.mark.parametrize("text,want", [
    ("double the revenue", ["2"]),
    ("triple your bookings", ["3"]),
    ("quadruple our reach", ["4"]),
    ("double what you make", ["2"]),
    ("double that", ["2"]),
    ("double as many", ["2"]),
    ("doubling their spend", ["2"]),
    ("double 3 classes", ["2", "3"]),
    ("double twelve", ["2", "12"]),
    ("bookings doubled", ["2"]),
    ("revenue tripled", ["3"]),
    ("reach quadrupled", ["4"]),
    ("twice", ["2"]),
    ("threefold", ["3"]),
    ("a tenfold rise", ["10"]),
])
def test_a_multiplier_word_before_what_it_multiplies_counts(text, want):
    found = mentions(text)
    assert [m.value for m in found] == [D(v) for v in want]
    assert found[0].form == "multiplier"


@pytest.mark.parametrize("text", [
    "no double booking", "a triple room", "double-check it",
    "triple-booked", "Double booking is gone",
])
def test_a_multiplier_word_as_a_modifier_is_not_a_mention(text):
    assert mentions(text) == []


# 3. fractions read as the percent number

@pytest.mark.parametrize("text,value,span", [
    ("a third of members", "33.3333", "a third"),
    ("a third of no-shows", "33.3333", "a third"),
    ("one third of sales", "33.3333", "one third"),
    ("two thirds of the week", "66.6667", "two thirds"),
    ("two-thirds of them", "66.6667", "two-thirds"),
    ("half of members", "50", "half"),
    ("Half of members", "50", "Half"),
    ("half the clients", "50", "half"),
    ("an hour and a half", "50", "a half"),
    ("a quarter of sales", "25", "a quarter"),
    ("three quarters of members", "75", "three quarters"),
    ("two quarters of the year", "50", "two quarters"),
    ("a fifth of revenue", "20", "a fifth"),
    ("an eighth of it", "12.5", "an eighth"),
])
def test_a_fraction_in_a_quantity_use_reads_as_the_percent_number(text, value, span):
    found = mentions(text)
    assert [(m.text, m.value, m.form) for m in found] == [(span, D(value), "fraction")]


@pytest.mark.parametrize("text,want", [
    ("the first half", []),
    ("in the second half", []),
    ("half-price classes", []),
    ("half price classes", []),
    ("every quarter", []),
    ("per quarter", []),
    ("last quarter", []),
    ("next quarter", []),
    ("this quarter", []),
])
def test_a_fraction_word_outside_a_quantity_use_is_not_a_fraction(text, want):
    assert [(m.text, str(m.value), m.form) for m in mentions(text)] == want


def test_a_number_word_or_ordinal_is_not_taken_for_a_fraction():
    assert [(m.value, m.form) for m in mentions("half a dozen")] == [(D(6), "word")]
    assert [(m.value, m.form) for m in mentions("half a million")] == [(D(500000), "word")]
    assert [(m.value, m.form) for m in mentions("the third week")] == [(D(3), "ordinal")]
    assert [(m.value, m.form) for m in mentions("two and a half weeks")] == [(D("2.5"), "word")]
    assert [(m.value, m.form) for m in mentions("two classes")] == [(D(2), "word")]


def test_a_fraction_is_supported_by_a_percent_figure():
    m = mentions("a third of members")[0]
    assert supported(m, FigureSet([theirs("share", "33.3", "percent")])) is True
    assert supported(m, FigureSet([theirs("share", "33.3", "")])) is True
    assert supported(m, FigureSet([theirs("share", "33", "percent")])) is False
    assert supported(m, FigureSet([theirs("price", "33.3333", "USD")])) is False
    claim = {"id": "CF2", "type": "client_fact", "value": 0.5, "unit": "%", "provenance": "client_input",
             "approval_status": "client_stated", "source": "client brief", "text": "half come back"}
    assert unsupported("half of them come back", FigureSet([from_claim(claim)])) == []


# 4. a 1900-2100 number is a year only after a word that makes it one

@pytest.mark.parametrize("text", [
    "in 2025", "In 2025 we grew", "since 2019", "from 2020 to 2024", "until 2027", "till 2027",
    "during 2024", "before 2020", "after 2021", "the year 2025", "FY 2025",
    "May 2026", "October 2025", "Q3 2025", "on Oct 31, 2025", "31 Oct 2025", "from 2020 to 2025",
    "in 2025-2026", "the 1990s",
])
def test_a_year_after_its_word_is_a_date(text):
    found = mentions(text)
    assert found and all(m.form == "date" for m in found)


@pytest.mark.parametrize("text,want,forms", [
    ("2000 members", ["2000"], ["digit"]),
    ("2025 was good", ["2025"], ["digit"]),
    ("we sold 1950 mats", ["1950"], ["digit"]),
    ("2025-2026", ["2025", "2026"], ["range", "range"]),
    ("may 2026", ["2026"], ["digit"]),   # a month name is capitalised
])
def test_a_year_shaped_count_is_a_digit(text, want, forms):
    found = mentions(text)
    assert [m.value for m in found] == [D(v) for v in want]
    assert [m.form for m in found] == forms


# 5. a label's list of numbers are labels

@pytest.mark.parametrize("text", [
    "Phases 2 and 3", "Steps 1-3", "Phases 1, 2 and 3", "Phases 1, 2, and 3", "Steps 1 & 2",
    "Phases 2 to 4", "Phase 2\u20133", "Steps 1-3 and 5", "Phase two",
    "Steps 1, 2", "Phases 1, 2, 3 and 4", "Phase 2-3, and Steps 4, 5",
])
def test_a_list_after_a_label_word_is_labels(text):
    assert mentions(text) == []


@pytest.mark.parametrize("text,want", [
    ("Phase 2, 12 weeks long", ["12"]),        # a comma joins only after a plural label
    ("Phase 2, 3 and 4", ["3", "4"]),
    ("Step 1, then 2 calls", ["2"]),
    ("Phase 2 costs $35", ["$35"]),
    ("Step 3 takes 12 weeks", ["12"]),
    ("Phase 2. 3 weeks later", ["3"]),
    ("Phases 1-2 run for 6 weeks", ["6"]),        # a verb after the list ends it
    ("Phase 2 adds 2-3 weeks", ["2", "3"]),
])
def test_a_number_after_a_label_that_is_not_in_its_list_still_counts(text, want):
    assert [m.text for m in mentions(text)] == want


# -- review fixes: a hidden number is the one failure this reader must not have ------------

def readings(text: str) -> list[tuple[str, str, str]]:
    return [(m.text, str(m.value), m.form) for m in mentions(text)]


# A1. only a bare number joins a label; anything carrying a unit is read

@pytest.mark.parametrize("text,want", [
    ("Phase 2 - $50", [("$50", "50", "money")]),
    ("Phase 2 to $50k", [("$50k", "50000", "money")]),
    ("Step 3 - 40% of members", [("40%", "40", "percent")]),
    ("Section 4 - 2,000 members", [("2,000", "2000", "digit")]),
    ("Step 1 - 3x faster", [("3x", "3", "multiplier")]),
    ("Phase 2,000 members", [("2,000", "2000", "digit")]),
    ("Step 3 40% of members", [("40%", "40", "percent")]),
    ("Phase 2 percent", [("2 percent", "2", "percent")]),
    ("Phase 2k", [("2k", "2000", "digit")]),
])
def test_a_label_does_not_hide_a_number_with_a_unit(text, want):
    assert readings(text) == want


# A2. a dash joins a label list only unspaced

@pytest.mark.parametrize("text,want", [
    ("Phase 1 - 6 weeks", ["6"]),
    ("Phase 1 \u2013 6 weeks", ["6"]),
    ("Appendix 1 - 12 interviews", ["12"]),
    ("Page 3 - 12 reformers", ["12"]),
    ("Steps 1-3", []),
    ("Phases 1-3", []),
    ("Phase 2\u20133.", []),
])
def test_only_an_unspaced_dash_joins_a_label_list(text, want):
    assert [m.text for m in mentions(text)] == want


# A3. and/to/comma join only after a plural label, and only bare items that end the phrase

@pytest.mark.parametrize("text,want", [
    ("Phase 2 and 12 weeks", ["12"]),
    ("Phase 2 to 12 weeks", ["12"]),
    ("Step 1 to 3 members", ["3"]),
    ("Part 2 and 15 more classes", ["15"]),
    ("Phase 2 and 3", ["3"]),
    ("Phase 2 and 3,000 members", ["3,000"]),
    ("Phases 2 and 3,000 members", ["3,000"]),
    ("Phases 2 and 3 run", []),                    # a verb after the list ends it
    ("Phases 2 and 3 weeks", ["3"]),
    ("Steps 1, 2 percent", ["2 percent"]),
    ("Phases 2 and 3", []),
    ("Steps 1, 2 and 3", []),
    ("Steps 1, 2 and 3.", []),
    ("(Phases 2 and 3)", []),
    ("Phases 2 and 3; then", []),
    ("Phases 2 and 3\nNext", []),
    ("Phases 1-2, 4 & 6", []),
])
def test_a_label_list_needs_a_plural_label_and_bare_items(text, want):
    assert [m.text for m in mentions(text)] == want


# A4. a lower-case label word is a label only after a reference word

@pytest.mark.parametrize("text,want", [
    ("book a table 4 times a week", ["4"]),
    ("the option 3 times", ["3"]),
    ("a page 2 people read", ["2"]),
    ("Phase 2", []),
    ("in phase 2", []),
    ("see section 4", []),
    ("during step 3", []),
    ("per phase 2", []),
    ("as set out in table 4", []),
])
def test_a_lower_case_label_word_needs_a_reference_lead(text, want):
    assert [m.text for m in mentions(text)] == want


# B5. markdown emphasis does not hide a number

@pytest.mark.parametrize("text,want", [
    ("__5__ studios", [("5", "5", "digit")]),
    ("_50%_ growth", [("50%", "50", "percent")]),
    ("**5**", [("5", "5", "digit")]),
    ("*12* reformers", [("12", "12", "digit")]),
    ("model_5 and snake_case_5", []),
])
def test_markdown_emphasis_does_not_hide_a_number(text, want):
    assert readings(text) == want


# B6. the tail of a token that starts with a digit is read

@pytest.mark.parametrize("text,want", [
    ("10x12", ["10", "12"]),
    ("1h30", ["1", "30"]),
    ("10x24", ["10", "24"]),
    ("2x2", ["2", "2"]),
    ("M3-A, CF-04 and v2", []),
])
def test_the_tail_of_a_digit_led_token_is_read(text, want):
    assert [m.text for m in mentions(text)] == want


# C7. more scale letters, with a currency

@pytest.mark.parametrize("text,value", [
    ("$5MM", "5000000"), ("$5mn", "5000000"), ("$2bn", "2000000000"), ("$2B", "2000000000"),
])
def test_scale_letters_with_a_currency(text, value):
    assert readings(text) == [(text, value, "money")]


def test_scale_letters_without_a_currency_do_not_scale():
    assert readings("5MM rows and 2B params") == [("5", "5", "digit"), ("2", "2", "digit")]


# C8. range ends keep their unit

@pytest.mark.parametrize("text,forms", [
    ("$30-$35", ["money", "money"]),
    ("$30-35", ["money", "money"]),
    ("30-35%", ["percent", "percent"]),
    ("30-35 reformers", ["range", "range"]),
])
def test_range_ends_keep_their_unit(text, forms):
    found = mentions(text)
    assert [m.value for m in found] == [D(30), D(35)]
    assert [m.form for m in found] == forms


def test_a_range_end_is_unit_checked():
    known = FigureSet([theirs("mats", "30", "reformers"), theirs("rooms", "35", "rooms")])
    assert [m.text for m in unsupported("$30-35", known)] == ["$30", "35"]
    assert unsupported("30-35 reformers", known) == []


# C9. currency codes, glued or spaced

@pytest.mark.parametrize("text,value", [
    ("AUD50", "50"), ("SGD100", "100"), ("INR500", "500"), ("CAD 5", "5"), ("Rs500", "500"),
    ("Rs. 500", "500"), ("50 NZD", "50"), ("JPY 1,200", "1200"),
])
def test_a_currency_code_makes_money(text, value):
    assert readings(text) == [(text, value, "money")]


def test_the_currency_codes_are_one_tuple_and_the_money_units():
    assert isinstance(R._CURRENCY_CODES, tuple)
    assert R._MONEY_UNITS == frozenset(R._CURRENCY_CODES)
    m = mentions("AUD50")[0]
    assert supported(m, FigureSet([theirs("fee", "50", "AUD")])) is True
    assert supported(m, FigureSet([theirs("fee", "50", "reformers")])) is False


# D10. "of" and "by" no longer make a year

@pytest.mark.parametrize("text,want", [
    ("growth of 2000 members", [("2000", "2000", "digit")]),
    ("a team of 1950 people", [("1950", "1950", "digit")]),
    ("by 2000 members", [("2000", "2000", "digit")]),
    ("by 2026", [("2026", "2026", "digit")]),        # by and of lead amounts too (fifth review, item 1)
    ("the end of 2025", [("2025", "2025", "digit")]),
    ("in 2025", [("2025", "2025", "date")]),
    ("until 2027", [("2027", "2027", "date")]),
])
def test_of_and_by_do_not_make_a_year(text, want):
    assert readings(text) == want


# D11. fractions after a lead word, and cardinal fractions always

@pytest.mark.parametrize("text,span,value", [
    ("cut costs in half", "half", "50"),
    ("down by half", "half", "50"),
    ("down by a quarter", "a quarter", "25"),
    ("over half", "half", "50"),
    ("split into thirds", "thirds", "33.3333"),
    ("nearly a third", "a third", "33.3333"),
    ("more than half", "half", "50"),
    ("one third", "one third", "33.3333"),
    ("two thirds", "two thirds", "66.6667"),
    ("three quarters", "three quarters", "75"),
    ("two quarters", "two quarters", "50"),
    ("one half", "one half", "50"),
])
def test_a_fraction_after_a_lead_word_or_with_a_cardinal(text, span, value):
    assert readings(text) == [(span, value, "fraction")]


@pytest.mark.parametrize("text", [
    "the first half", "second half", "half-price", "at half-price", "half price", "every quarter",
    "per quarter", "last quarter", "next quarter", "this quarter",
])
def test_fraction_words_that_are_not_quantities(text):
    assert [m for m in mentions(text) if m.form == "fraction"] == []
    assert mentions(text) == []


def test_a_fraction_word_with_no_exception_is_read_as_a_fraction():
    # the rule is inverted (re-review item 2): read unless a known exception applies
    assert readings("a third time") == [("third", "3", "ordinal")]     # before a noun: an order
    assert readings("a half") == [("a half", "50", "fraction")]
    assert readings("thirds") == [("thirds", "33.3333", "fraction")]


# D12. a word ordinal opening a sentence before a comma is an enumerator

@pytest.mark.parametrize("text,want", [
    ("Third, we book the studio.", []),
    ("Fourth, the price.", []),
    ("We start. Third, we book.", []),
    ("Plan:\nFifth, review.", []),
    ("3rd, we book.", [("3rd", "3", "ordinal")]),
    ("the third, and last", [("third", "3", "ordinal")]),
    ("Third week we book.", [("Third", "3", "ordinal")]),
])
def test_a_sentence_opening_word_ordinal_is_an_enumerator(text, want):
    assert readings(text) == want


# E13-15. ordinals at scale, space-grouped thousands, 2X

@pytest.mark.parametrize("text,want", [
    ("the hundredth member", [("hundredth", "100", "ordinal")]),
    ("the thousandth visit", [("thousandth", "1000", "ordinal")]),
    ("one hundredth", [("one hundredth", "100", "ordinal")]),
    ("45 000 a year", [("45 000", "45000", "digit")]),
    ("1 250 000 views", [("1 250 000", "1250000", "digit")]),
    ("45\u2009000", [("45\u2009000", "45000", "digit")]),
    ("45\u00a0000", [("45\u00a0000", "45000", "digit")]),
    ("12 34 56", [("12", "12", "digit"), ("34", "34", "digit"), ("56", "56", "digit")]),
    ("2X more", [("2X", "2", "multiplier")]),
])
def test_scale_ordinals_grouped_thousands_and_capital_x(text, want):
    assert readings(text) == want


# F17. the span invariant over a seeded random mix, and speed

_TOKENS = [
    "12", "1,000", "45 000", "3.5", ".5", "$35", "\u20ac50", "\u00a37", "AUD50", "Rs500", "50%", "25 percent",
    "10k", "$1.2M", "$5MM", "2-3", "2 to 3", "$30-35", "3x", "2X", "3\u00d7", "10x12", "1h30", "3rd", "1st",
    "twelve", "twenty-two", "a dozen", "half a dozen", "half", "a third", "two thirds", "third", "Third,",
    "twice", "double", "the", "of", "in", "by", "and", "to", ",", ".", "-", " - ", "\u2013", "(", ")", "**",
    "__", "_", "Phase", "phase", "Phases", "Steps", "Exhibit 2.1", "Q3", "CF-04", "model_5", "2025", "2000",
    "31 Oct", "Oct 31", "6pm", "18:00", "6-7pm", "1990s", "2025-03-01", "\n", "\n1. ", "  2) ", "members",
    "weeks", "-5", "\u22125", "0", "1.2.3", "v2.1",
]
_SEPARATORS = ["", " ", " ", " ", "\t", "-", ",", "\u00a0"]


def test_spans_are_exact_ordered_and_never_overlap_over_a_seeded_random_mix():
    import random
    rng = random.Random(20261101)
    for _ in range(20000):
        parts = []
        for _ in range(rng.randint(1, 8)):
            parts.append(rng.choice(_TOKENS))
            parts.append(rng.choice(_SEPARATORS))
        text = "".join(parts)
        last_end = 0
        for m in mentions(text):
            assert text[m.start:m.end] == m.text, (text, m)
            assert m.start < m.end and m.start >= last_end, (text, m)
            assert isinstance(m.value, Decimal), (text, m)
            last_end = m.end


def test_a_long_text_reads_quickly():
    import time
    digits = "1234567890" * 3000                                    # 30k characters
    chain = ", ".join(str(i % 1000) for i in range(6000))          # about 23k
    labels = "Phases " + ", ".join(str(i) for i in range(1, 5000)) + " and 5000."   # about 24k
    prose = "Phase 2 - $50, 30-35% of 1,200 members in 2025; a third of no-shows. " * 330   # about 23k
    text = "\n".join((digits, chain, labels, prose))
    assert len(text) >= 100_000
    started = time.perf_counter()
    found = unsupported(text, NOTHING)
    elapsed = time.perf_counter() - started
    assert elapsed < 5, elapsed
    assert len(found) > 6000


# -- re-review: prefer a false flag to a hidden number ----------------------------------------

# 1. no quadratic walk: long underscore, asterisk and emphasis runs read quickly

_LONG_RUNS = [   # (id, text, want); ids keep pytest's environment variable short
    ("underscores-20k", "_" * 20000, []),
    ("stars-underscores-20k-5", "**" + "_" * 20000 + "5", ["5"]),
    ("letter-underscores-20k-5", "a" + "_" * 20000 + "5", []),
    ("underscores-100k", "_" * 100000, []),
    ("stars-100k", "*" * 100000, []),
    ("stars-100k-5", "**" + "*" * 100000 + "5", ["5"]),
    ("emphasis-100k", "__5__ " * 16700, ["5"] * 16700),
    ("underscores-5-underscores", "_" * 50000 + "5" + "_" * 50000, ["5"]),
]


@pytest.mark.parametrize("text,want", [(t, w) for _, t, w in _LONG_RUNS], ids=[i for i, _, _ in _LONG_RUNS])
def test_long_emphasis_runs_read_in_linear_time(text, want):
    import time
    started = time.perf_counter()
    found = mentions(text)
    elapsed = time.perf_counter() - started
    assert elapsed < 3, elapsed
    assert [m.text for m in found] == want


# 2. a fraction word is read unless a known exception applies

@pytest.mark.parametrize("text", [
    "roughly half will return", "up to half could churn", "at least half renew",
    "approximately half renew", "Half renew each month", "close to half", "half or more",
    "half as many", "cut costs in half", "half an hour",
])
def test_half_is_read_unless_an_exception_applies(text):
    found = mentions(text)
    assert [(m.text.lower(), m.value, m.form) for m in found] == [("half", D(50), "fraction")]


@pytest.mark.parametrize("text", [
    "the first half", "second half", "the last half", "the other half", "this half", "half-price",
    "half-hour", "half price", "every quarter", "per quarter", "last quarter", "next quarter",
    "this quarter", "each quarter",
])
def test_half_and_quarter_after_a_position_or_period_word_or_in_a_compound_are_not_read(text):
    assert mentions(text) == []


def test_half_a_dozen_and_cardinal_fractions_are_unchanged():
    assert [(m.text, m.value, m.form) for m in mentions("half a dozen")] == [("half a dozen", D(6), "word")]
    assert readings("one third") == [("one third", "33.3333", "fraction")]
    assert readings("two thirds") == [("two thirds", "66.6667", "fraction")]
    assert readings("three quarters") == [("three quarters", "75", "fraction")]


# 3. "<Month> <day>" is a date only before the end, punctuation, a function word,
#    a suffix, a time or a dash and another day; otherwise the number is a count

@pytest.mark.parametrize("text,want", [
    ("In May 12 members joined", [("12", "12", "digit")]),
    ("In April 20 new clients signed up", [("20", "20", "digit")]),
    ("By June 15 instructors had left", [("15", "15", "digit")]),
])
def test_a_month_followed_by_a_count_reads_the_count(text, want):
    assert readings(text) == want


@pytest.mark.parametrize("text,want", [
    ("It opens May 12.", [("May 12", "12", "date")]),
    ("on May 12", [("May 12", "12", "date")]),
    ("May 12, 2025", [("May 12", "12", "date"), ("2025", "2025", "date")]),
    ("May 12, we opened", [("May 12", "12", "date")]),
    ("May 12th members", [("May 12th", "12", "date")]),
    ("May 12 at 6pm", [("May 12", "12", "date"), ("6pm", "18", "time")]),
    ("May 12 6pm", [("May 12", "12", "date"), ("6pm", "18", "time")]),
    ("May 12-14", [("May 12", "12", "date"), ("14", "14", "date")]),
    ("May 12 - June 3", [("May 12", "12", "date"), ("June 3", "3", "date")]),
    ("May 12 the studio opens", [("May 12", "12", "date")]),
    ("31 Oct", [("31 Oct", "31", "date")]),
    ("the 3rd of March", [("3rd of March", "3", "date")]),
])
def test_a_month_and_day_in_date_position_is_a_date(text, want):
    assert readings(text) == want


# 4. a year needs its lead word and a date continuation

@pytest.mark.parametrize("text,want", [
    ("available in 2000 studios", [("2000", "2000", "digit")]),
    ("after 2000 sessions", [("2000", "2000", "digit")]),
    ("until 2000 members sign up", [("2000", "2000", "digit")]),
    ("from 2000 to 2050 members", [("2000", "2000", "range"), ("2050", "2050", "range")]),
    ("In 2025 revenue grew", [("2025", "2025", "date")]),         # revenue is a noun a year qualifies
])
def test_a_year_shaped_number_before_a_noun_is_a_count(text, want):
    assert readings(text) == want


@pytest.mark.parametrize("text", [
    "in 2025.", "in 2025, revenue grew", "In 2025 we grew", "since 2019 we have",
    "from 2020 to 2025", "in 2025-2026", "during 2024, and in 2025", "Q3 2025", "FY 2025 May",
    "until 2027 as planned",
])
def test_a_year_in_date_position_is_a_date(text):
    found = mentions(text)
    assert found and all(m.form == "date" for m in found), found


# 5. after a label word, only one bare number word that ends the phrase is a label

@pytest.mark.parametrize("text,want", [
    ("Phase two thousand members", [("two thousand", "2000", "word")]),
    ("Option three hundred dollars", [("three hundred dollars", "300", "money")]),
    ("Phase two percent", [("two percent", "2", "percent")]),
    ("Phase twelve weeks", [("twelve", "12", "word")]),
    ("Step two and a half hours", [("two and a half", "2.5", "word")]),
])
def test_a_number_word_quantity_after_a_label_is_read(text, want):
    assert readings(text) == want


@pytest.mark.parametrize("text", ["Phase two", "Step three", "Phase two.", "(Step three)", "Phase two, then"])
def test_a_bare_number_word_after_a_label_is_a_label(text):
    assert mentions(text) == []


# 6. a clock time after a label word is still a time

def test_a_time_after_a_label_word_is_a_time():
    assert readings("Step 6pm") == [("6pm", "18", "time")]
    assert [m.text for m in unsupported("Step 6pm", NOTHING, hours={9})] == ["6pm"]
    assert readings("Step 6") == []


# 7. currency signs after the number, and the yen and rupee signs

@pytest.mark.parametrize("text,span,value", [
    ("40$", "40$", "40"),
    ("40\u20ac", "40\u20ac", "40"),
    ("40 \u20ac", "40 \u20ac", "40"),
    ("\u00a5500", "\u00a5500", "500"),
    ("500\u00a5", "500\u00a5", "500"),
    ("\u20b9500", "\u20b9500", "500"),
    ("\u20b91,200", "\u20b91,200", "1200"),
])
def test_a_currency_sign_after_the_number_or_yen_and_rupee_make_money(text, span, value):
    assert readings(text) == [(span, value, "money")]


def test_a_sign_that_opens_the_next_amount_is_not_a_suffix():
    assert readings("40 $50") == [("40", "40", "digit"), ("$50", "50", "money")]


# 8. more reference leads for lower-case label words

@pytest.mark.parametrize("text", ["on page 7", "open page 7", "go to page 7", "turn to page 7", "Page 7 shows it"])
def test_a_lower_case_label_after_on_open_or_to_is_a_label(text):
    assert mentions(text) == []


def test_a_lower_case_label_word_opening_a_sentence_is_read():
    # no reference lead and no capital: "page 7" is read (a false flag, never a hidden number)
    assert readings("page 7 shows the plan") == [("7", "7", "digit")]


# addendum: a range needs agreeing shapes, and a bare end that takes a shape has no noun of its own

@pytest.mark.parametrize("text,want", [
    ("We pay $45 to 12 instructors each week.", [("$45", "45", "money"), ("12", "12", "digit")]),
    ("We cut churn 5% to 40 members.", [("5%", "5", "percent"), ("40", "40", "digit")]),
    ("Raise the price by 10% to $22.", [("10%", "10", "percent"), ("$22", "22", "money")]),
    ("$20-30 a class", [("$20", "20", "money"), ("30", "30", "money")]),
    ("10-15% a year", [("10", "10", "percent"), ("15%", "15", "percent")]),
    ("30-35 reformers", [("30", "30", "range"), ("35", "35", "range")]),
    ("$30-35 per class", [("$30", "30", "money"), ("35", "35", "money")]),
    ("$30-35.", [("$30", "30", "money"), ("35", "35", "money")]),
    ("$30-$35 a class", [("$30", "30", "money"), ("$35", "35", "money")]),
])
def test_a_range_hands_a_shape_only_to_a_bare_end_with_no_noun(text, want):
    assert readings(text) == want


def test_a_label_word_number_before_a_function_word_is_a_label():
    assert mentions("See Phase two of the plan, Q3 and CF-04.") == []


# -- third review ---------------------------------------------------------------------------

# 1. a colon pattern is a time only with am/pm, a time word before it, or an hour 13-23

@pytest.mark.parametrize("text,want", [
    ("an instructor-to-client ratio of 1:10", [("1", "1", "digit"), ("10", "10", "digit")]),
    ("1:12", [("1", "1", "digit"), ("12", "12", "digit")]),
    ("1:20", [("1", "1", "digit"), ("20", "20", "digit")]),
    ("a 10:30 split", [("10", "10", "digit"), ("30", "30", "digit")]),
    ("at 10:30", [("10:30", "10", "time")]),
    ("18:00", [("18:00", "18", "time")]),
    ("6:30pm", [("6:30pm", "18", "time")]),
    ("from 9:00 to 17:00", [("9:00", "9", "time"), ("17:00", "17", "time")]),
    ("doors open 09:00", [("09:00", "9", "time")]),
    ("1:1 coaching", []),
])
def test_a_colon_pattern_is_a_ratio_unless_it_is_clearly_a_time(text, want):
    assert readings(text) == want


# 2. multiplier words are read in every use but compounds and the nouns they describe

@pytest.mark.parametrize("text", [
    "could double by next summer", "Bookings will double.", "Aim to triple bookings",
    "Doubling membership is realistic.", "a double", "bookings double.", "revenue doubles",
    "tripling the classes", "will double bookings",
])
def test_a_multiplier_word_is_read_as_a_verb_too(text):
    found = mentions(text)
    assert len(found) == 1 and found[0].form == "multiplier", found


@pytest.mark.parametrize("text", [
    "no double booking", "a double room", "double shifts", "double beds", "double-check",
    "triple-booked", "double glazing", "a double major", "double standard", "double agent",
    "double take", "double vision", "double space", "double entry", "double clicks", "double checks",
])
def test_a_multiplier_word_as_a_compound_or_before_its_noun_is_not_read(text):
    assert mentions(text) == []


# 3. slash and hyphen dates need a four-digit year

@pytest.mark.parametrize("text,want", [
    ("10/31/2025", [("10/31/2025", "10", "date")]),
    ("31/10/2025", [("31/10/2025", "31", "date")]),
    ("2025-10-31", [("2025-10-31", "2025", "date")]),
    ("31-10-2025", [("31-10-2025", "31", "date")]),
    ("2025/10/31", [("2025/10/31", "2025", "date")]),
    ("5/10/20 class packs", [("5", "5", "digit"), ("10", "10", "digit"), ("20", "20", "digit")]),
    ("5/10/15% apply", [("5", "5", "digit"), ("10", "10", "digit"), ("15%", "15", "percent")]),
    ("5/10", [("5", "5", "digit"), ("10", "10", "digit")]),
    ("31/10/25", [("31", "31", "digit"), ("10", "10", "digit"), ("25", "25", "digit")]),
])
def test_a_numeric_date_needs_a_four_digit_year(text, want):
    assert readings(text) == want


# 4. words that also follow counts do not make a month and day a date

@pytest.mark.parametrize("text,want", [
    ("In May 12 to 15 new members", [("12", "12", "range"), ("15", "15", "range")]),
    ("In June 10 or 12 members cancelled", [("10", "10", "digit"), ("12", "12", "digit")]),
    ("In March 12 of our 40 members renewed", [("12", "12", "digit"), ("40", "40", "digit")]),
    ("In March 12 were lost", [("12", "12", "digit")]),
    ("May 10-15 new members", [("10", "10", "range"), ("15", "15", "range")]),
    ("We lost 5 of April's new members", [("5", "5", "digit")]),
])
def test_a_month_before_a_count_word_reads_the_count(text, want):
    assert readings(text) == want


@pytest.mark.parametrize("text,want", [
    ("May 10-15 we close", [("May 10", "10", "date"), ("15", "15", "date")]),
    ("May 10-15.", [("May 10", "10", "date"), ("15", "15", "date")]),
    ("On May 12 the studio opens", [("May 12", "12", "date")]),
    ("May 12 is the date", [("May 12", "12", "date")]),
    ("By June 15, instructors had left", [("June 15", "15", "date")]),
])
def test_a_month_and_day_before_a_date_word_is_a_date(text, want):
    assert readings(text) == want


# 5. a lone x glued before a number is a multiplier

def test_x_before_a_number_is_a_multiplier():
    assert ("x3", "3", "multiplier") in readings("Grow revenue x3 in two years")
    assert readings("Grow revenue x3 in two years") == [("x3", "3", "multiplier"), ("two", "2", "word")]
    assert readings("X2 the bookings") == [("X2", "2", "multiplier")]
    assert readings("x86-64 servers and v2") == []


# 6. decade words read like "30s"

@pytest.mark.parametrize("text,value", [
    ("in their thirties", "30"), ("the twenties", "20"), ("mid-forties", "40"), ("the nineties", "90"),
])
def test_a_decade_word_reads_its_decade(text, value):
    found = mentions(text)
    assert [(m.value, m.form) for m in found] == [(D(value), "digit")]


# 7. more currency prefixes, in the one tuple

@pytest.mark.parametrize("text,span", [
    ("Prices start at R500 a month", "R500"), ("RM500", "RM500"), ("Dh500", "Dh500"),
    ("kr500", "kr500"), ("Kr 500", "Kr 500"), ("MXN500", "MXN500"), ("BRL 120", "BRL 120"),
    ("500 PLN", "500 PLN"),
])
def test_more_currency_prefixes_make_money(text, span):
    found = [m for m in mentions(text) if m.form == "money"]
    assert [m.text for m in found] == [span]
    for code in ("R", "RM", "Dh", "kr", "Kr", "MXN", "OMR"):
        assert code in R._CURRENCY_CODES


# 8. idioms hold no quantity; working hours are times

@pytest.mark.parametrize("text", ["24/7", "open 24x7", "1-on-1", "one-on-one", "1:1 coaching", "one to one"])
def test_an_idiom_is_not_a_quantity(text):
    assert mentions(text) == []


def test_nine_to_five_is_working_hours():
    # only after open, opens, hours, shift or daily (fourth review, item 4)
    assert readings("open 9-5") == [("9", "9", "time"), ("5", "17", "time")]
    assert readings("Hours: 9 to 5") == [("9", "9", "time"), ("5", "17", "time")]
    assert unsupported("open 9-5", NOTHING) == []
    assert unsupported("open 9-5", NOTHING, hours={9, 17}) == []
    assert [m.value for m in unsupported("open 9-5", NOTHING, hours={9})] == [D(17)]


@pytest.mark.parametrize("text,want", [
    ("a 5-star review", ["5"]), ("the 80/20 rule", ["80", "20"]), ("4K video", ["4K"]), ("3 D-rings", ["3"]),
])
def test_things_that_look_like_idioms_but_hold_numbers_are_read(text, want):
    assert [m.text for m in mentions(text)] == want


# 9. positions on the plan's own time axis are dates

@pytest.mark.parametrize("text,want", [
    ("Week 6", [("6", "6", "date")]),
    ("Weeks 1-4", [("1", "1", "date"), ("4", "4", "date")]),
    ("Month 1-3", [("1", "1", "date"), ("3", "3", "date")]),
    ("Day 30", [("30", "30", "date")]),
    ("Year 1", [("1", "1", "date")]),
    ("by Week 6", [("6", "6", "date")]),
    ("in week 6", [("6", "6", "date")]),
    ("Quarter 2.", [("2", "2", "date")]),
    ("Week 6 costs $50", [("6", "6", "date"), ("$50", "50", "money")]),
    ("Week 6 - 12 members", [("6", "6", "date"), ("12", "12", "digit")]),
    ("week 6 starts", [("6", "6", "digit")]),
    ("Week 12 members", [("12", "12", "digit")]),
])
def test_a_plan_position_is_a_date_and_a_quantity_after_it_is_read(text, want):
    assert readings(text) == want


# 9b. the roadmap's structure words are label words

@pytest.mark.parametrize("text,want", [
    ("Stage 2", []), ("Tier 3", []), ("Level 4.", []), ("Gate 1", []), ("Wave 2", []), ("Sprints 1-3", []),
    ("in round 2", []), ("Milestone 3", []),
    ("Tier 3 costs $50", ["$50"]), ("Milestone 12 members", ["12"]), ("round 2 numbers", ["2"]),
])
def test_the_roadmap_structure_words_are_labels(text, want):
    assert [m.text for m in mentions(text)] == want


# 10. minor

def test_a_half_dozen_and_a_half_million_read_the_quantity():
    assert [(m.text, m.value, m.form) for m in mentions("A half dozen instructors")] == [
        ("A half dozen", D(6), "word")]
    assert [(m.text, m.value, m.form) for m in mentions("a half million dollars")] == [
        ("a half million dollars", D(500000), "money")]


def test_vulgar_half_zero_noon_and_midnight():
    assert readings("1\u00bd hours") == [("1", "1", "digit"), ("\u00bd", "50", "fraction")]
    assert readings("zero churn") == [("zero", "0", "word")]
    assert readings("at noon") == [("noon", "12", "time")]
    assert readings("by midnight") == [("midnight", "0", "time")]
    assert readings("12 noon") == [("12 noon", "12", "time")]
    assert readings("afternoon") == []


@pytest.mark.parametrize("text,want", [
    ("Phase 12 weeks is enough", ["12"]),
    ("Phase 2 starts", []),
    ("Phase 12 is next", []),
    ("Phase 12.", []),
    ("Exhibit 2.1 shows it", []),
])
def test_a_label_number_of_two_digits_must_end_the_phrase(text, want):
    assert [m.text for m in mentions(text)] == want


# -- fourth review ---------------------------------------------------------------------------

def values_of(text: str) -> list[Decimal]:
    return [m.value for m in mentions(text)]


# 1. day-month follows the same continuation rule, and the day must exist in the month

@pytest.mark.parametrize("text,want", [
    ("4 December parties", [("4", "4", "digit")]),
    ("12 December cake orders", [("12", "12", "digit")]),
    ("Run 2 June workshops", [("2", "2", "digit")]),
    ("Book 6 January intro sessions", [("6", "6", "digit")]),
    ("Only 4 of March trials converted", [("4", "4", "digit")]),
    ("31 Oct", [("31 Oct", "31", "date")]),
    ("12 December.", [("12 December", "12", "date")]),
    ("on 12 December we opened", [("12 December", "12", "date")]),
    ("12 December 2025", [("12 December", "12", "date"), ("2025", "2025", "date")]),
    ("30 Feb.", [("30", "30", "digit")]),
    ("31 April", [("31", "31", "digit")]),
    ("Feb 30.", [("30", "30", "digit")]),
    ("Apr 31", [("31", "31", "digit")]),
    ("Feb 29.", [("Feb 29", "29", "date")]),
])
def test_day_month_needs_a_date_continuation_and_a_real_day(text, want):
    assert readings(text) == want


# 2. a list of month-day pairs is a monthly series of counts; a pair or span is a date range

@pytest.mark.parametrize("text,want", [
    ("New members: Jan 12, Feb 14, Mar 18.", ["12", "14", "18"]),
    ("Bookings: May 15; June 18; July 21.", ["15", "18", "21"]),
    ("Churned members: April 7, May 5, June 4.", ["7", "5", "4"]),
    ("Sign-ups: 12 Jan, 14 Feb, 18 Mar.", ["12", "14", "18"]),
])
def test_a_monthly_series_is_read_as_counts(text, want):
    found = mentions(text)
    assert [m.text for m in found] == want and all(m.form != "date" for m in found)


@pytest.mark.parametrize("text,want", [
    ("Closed Dec 24 and 25.", [("Dec 24", "24", "date"), ("25", "25", "date")]),
    ("from Nov 1 to Nov 30", [("Nov 1", "1", "date"), ("Nov 30", "30", "date")]),
    ("Closed Dec 24 to Jan 2.", [("Dec 24", "24", "date"), ("Jan 2", "2", "date")]),
    ("On May 12 and 13 we are closed.", [("May 12", "12", "date"), ("13", "13", "date")]),
    ("Workshops on June 3 or 10.", [("June 3", "3", "date"), ("10", "10", "date")]),
    ("The audit runs Mar 3-7.", [("Mar 3", "3", "date"), ("7", "7", "date")]),
    ("Dec 24 - Jan 2, 2026", [("Dec 24", "24", "date"), ("Jan 2", "2", "date"), ("2026", "2026", "date")]),
])
def test_a_month_day_pair_that_ends_as_a_date_is_a_date_range(text, want):
    assert readings(text) == want


# 3. rank words make a share; "a third" before a noun is an order

@pytest.mark.parametrize("text,want", [
    ("The top quarter of members book 60% of classes",
     [("quarter", "25", "fraction"), ("60%", "60", "percent")]),
    ("the bottom fifth", [("fifth", "20", "fraction")]),
    ("our weakest quarter", [("quarter", "25", "fraction")]),
    ("the best third", [("third", "33.3333", "fraction")]),
    ("the lowest tenth", [("tenth", "10", "fraction")]),
    ("the upper half", [("half", "50", "fraction")]),
    ("the lower half", [("half", "50", "fraction")]),
    ("A fourth van", [("fourth", "4", "ordinal")]),
    ("a third hygienist", [("third", "3", "ordinal")]),
    ("the third class", [("third", "3", "ordinal")]),
    ("a third of members", [("a third", "33.3333", "fraction")]),
    ("cut costs by a third", [("a third", "33.3333", "fraction")]),
    ("nearly a fifth.", [("a fifth", "20", "fraction")]),
    ("a quarter van", [("a quarter", "25", "fraction")]),
])
def test_rank_words_make_a_share_and_a_third_before_a_noun_is_an_order(text, want):
    assert readings(text) == want


# 4. nine to five is working hours only with am/pm or after open, hours, shift, daily

@pytest.mark.parametrize("text", [
    "Reduce the team from 9 to 5 people.", "Drop from 9 to 5 vans", "A 9-5 member split", "We work 9-5.",
])
def test_nine_to_five_without_a_lead_is_two_numbers(text):
    found = mentions(text)
    assert [m.value for m in found] == [D(9), D(5)] and all(m.form != "time" for m in found)


@pytest.mark.parametrize("text", ["open 9-5", "Opens 9 to 5", "Hours: 9-5", "shift 9-5", "daily 9-5", "9am-5pm"])
def test_nine_to_five_after_a_lead_or_with_am_pm_is_working_hours(text):
    found = mentions(text)
    assert [(m.value, m.form) for m in found] == [(D(9), "time"), (D(17), "time")]


# 5. a ratio cue makes a colon pair a ratio; otherwise quarter minutes and ranges make a time

@pytest.mark.parametrize("text,want", [
    ("Keep the ratio at 1:10", ["1", "10"]),
    ("Move the ratio from 1:12 to 1:8", ["1", "12", "1", "8"]),
    ("Staffing 1:10.", ["1", "10"]),
    ("after 1:12 became standard", ["1", "12"]),
    ("a staff-to-client 1:6", ["1", "6"]),
    ("a 1:15 mix", ["1", "15"]),
])
def test_a_colon_pair_with_a_ratio_cue_or_odd_minutes_is_a_ratio(text, want):
    found = mentions(text)
    assert [str(m.value) for m in found] == want and all(m.form != "time" for m in found)


@pytest.mark.parametrize("text,want", [
    ("The 7:15 class", [("7:15", "7", "time")]),
    ("opens 7:30 and closes 8:15", [("7:30", "7", "time"), ("8:15", "8", "time")]),
    ("8:00-18:00", [("8:00", "8", "time"), ("18:00", "18", "time")]),
    ("9:00 to 17:00", [("9:00", "9", "time"), ("17:00", "17", "time")]),
    ("8:30 - 17:30", [("8:30", "8", "time"), ("17:30", "17", "time")]),
    ("9:05 to 17:00", [("9:05", "9", "time"), ("17:00", "17", "time")]),
    ("at 9:10", [("9:10", "9", "time")]),
])
def test_a_colon_pair_with_quarter_minutes_or_a_time_at_the_other_end_is_a_time(text, want):
    assert readings(text) == want
    assert all(m.value != 0 or m.form == "time" for m in mentions(text))   # never a stray 0


# 6. more year leads, a noun a year qualifies, and "from" needs its other end

@pytest.mark.parametrize("text", [
    "FY 2025 revenue", "In late 2025", "Q3 2025 revenue", "mid-2025", "from 2020 until 2024",
    "In 2025 revenue grew",
])
def test_a_year_after_a_lead_and_before_a_date_continuation_is_a_date(text):
    found = mentions(text)
    assert found and all(m.form == "date" for m in found), found


@pytest.mark.parametrize("text,want", [
    ("Followers rose to 2100 from 1950 in May.", [("2100", "2100", "digit"), ("1950", "1950", "digit")]),
    ("Up from 1980 in 2024.", [("1980", "1980", "digit"), ("2024", "2024", "date")]),
    ("growth of 2000 members", [("2000", "2000", "digit")]),
    ("the 2000 members", [("2000", "2000", "digit")]),
    ("for 1999 people", [("1999", "1999", "digit")]),
])
def test_a_year_shaped_count_stays_a_count(text, want):
    assert readings(text) == want


# 7. twice and thrice keep their factor in compounds

@pytest.mark.parametrize("text,value", [
    ("Twice-weekly classes", "2"), ("twice-daily", "2"), ("twice-yearly reviews", "2"), ("thrice weekly", "3"),
    ("Twice a week", "2"),
])
def test_twice_and_thrice_compounds_are_multipliers(text, value):
    found = mentions(text)
    assert [(m.value, m.form) for m in found] == [(D(value), "multiplier")]


def test_double_compounds_stay_modifiers():
    assert mentions("double-check") == []


# 8. every vulgar fraction sign reads as a fraction

@pytest.mark.parametrize("text,value", [
    ("\u2153 of members", "33.3333"), ("\u2154 renew", "66.6667"), ("\u215b of a share", "12.5"),
    ("\u2155 of revenue", "20"), ("\u2159 of it", "16.6667"), ("\u215e", "87.5"),
])
def test_a_vulgar_fraction_sign_is_a_fraction(text, value):
    assert [(m.value, m.form) for m in mentions(text)] == [(D(value), "fraction")]


def test_a_number_and_a_vulgar_fraction():
    assert readings("2\u2154 hours") == [("2", "2", "digit"), ("\u2154", "66.6667", "fraction")]


# 9. a short local prefix or a glued code needs an amount

@pytest.mark.parametrize("text", ["R1", "R2", "Risks R1-R5", "See risk R3", "Room R2", "PHP8"])
def test_a_prefix_before_a_short_number_is_an_identifier(text):
    assert mentions(text) == []


@pytest.mark.parametrize("text,value", [("R500", "500"), ("R1,200", "1200"), ("R2.5k", "2500"), ("AUD50", "50")])
def test_a_prefix_before_an_amount_is_money(text, value):
    assert [(m.value, m.form) for m in mentions(text)] == [(D(value), "money")]


def test_a_code_before_a_number_glued_to_a_letter_is_not_money():
    assert readings("CAD 3D") == []                          # 3D is an idiom (fifth review, item 5)
    assert readings("CAD 3kg tiles") == [("3", "3", "digit")]  # a glued unit: not an amount, still read


# 10. a label list may be followed by a function word or a verb

@pytest.mark.parametrize("text,want", [
    ("Weeks 1-4 are setup", [("1", "1", "date"), ("4", "4", "date")]),
    ("Month 1-3 is the pilot", [("1", "1", "date"), ("3", "3", "date")]),
    ("Phases 2-3 take 10 weeks", [("10", "10", "digit")]),
    ("Options 1 and 2 cost the same", []),
    ("### Week 1-2 - Setup", [("1", "1", "date"), ("2", "2", "date")]),
    ("Phases 2 and 3 weeks", [("3", "3", "digit")]),
    ("Weeks 1-4 members", [("1", "1", "date"), ("4", "4", "digit")]),
])
def test_a_label_list_followed_by_a_verb_or_function_word_holds(text, want):
    assert readings(text) == want


# 11. value bugs

def test_a_dozen_and_a_half_is_eighteen():
    assert values_of("a dozen and a half") == [D(18)]
    assert values_of("A dozen and a half pastries.") == [D(18)]
    assert values_of("two and a half") == [D("2.5")]
    assert values_of("a million and a half") == [D(1500000)]


@pytest.mark.parametrize("text,want", [
    ("Our top-10 clients pay late.", [("10", "10", "digit")]),
    ("Covid-19 cut revenue.", [("19", "19", "digit")]),
    ("COVID-19", []),
])
def test_a_hyphen_after_a_word_is_not_a_minus(text, want):
    assert readings(text) == want


# 12. am applies to a range ending at 12

def test_ten_to_twelve_am():
    assert readings("10-12am") == [("10", "10", "time"), ("12am", "12", "time")]


# -- fifth review -----------------------------------------------------------------------------

# 1. by, of, for, over, the, through lead amounts: a year-shaped number after them is a count

@pytest.mark.parametrize("text,want", [
    ("Grow the email list by 2000.", [("2000", "2000", "digit")]),
    ("A budget of 2000 for the fit-out", [("2000", "2000", "digit")]),
    ("We made over 2000 sales last year.", [("2000", "2000", "digit")]),
    ("For 2000 a month you can rent...", [("2000", "2000", "digit")]),
    ("Revenue for 2050 is the stretch case.", [("2050", "2050", "digit")]),
    ("That is a saving of 1950.", [("1950", "1950", "digit")]),
    ("By 2027 the studio will", [("2027", "2027", "digit")]),        # accepted cost
    ("Revenue for 2024 was", [("2024", "2024", "digit")]),           # accepted cost
    ("in 2000 sales", [("2000", "2000", "digit")]),                  # a count noun after it
    ("in 2025 the studio", [("2025", "2025", "digit")]),             # a generic word after it
])
def test_an_amount_shaped_like_a_year_is_read(text, want):
    assert readings(text) == want


@pytest.mark.parametrize("text", ["in 2025.", "since 2019 we", "In late 2025", "FY 2025 revenue", "mid-2025",
                                  "Q3 2025", "until 2027, then", "from 2020 to 2024"])
def test_a_year_after_a_year_lead_is_still_a_date(text):
    found = mentions(text)
    assert found and all(m.form == "date" for m in found), found


# 2. a local prefix before two or more digits, or an ISO code before any digits, is money

@pytest.mark.parametrize("text,want", [
    ("A drop-in class costs R80.", [("R80", "80", "money")]),
    ("Classes at RM45 each.", [("RM45", "45", "money")]),
    ("A latte is Dh18.", [("Dh18", "18", "money")]),
    ("Rs99 per month.", [("Rs99", "99", "money")]),
    ("Entry kr90.", [("kr90", "90", "money")]),
    ("R80-R120 a class", [("R80", "80", "money"), ("R120", "120", "money")]),
    ("GBP5 delivery", [("GBP5", "5", "money")]),
    ("EUR5 per bag", [("EUR5", "5", "money")]),
    ("USD8 per item", [("USD8", "8", "money")]),
    ("AUD9 per box", [("AUD9", "9", "money")]),
])
def test_a_glued_currency_prefix_before_an_amount_is_money(text, want):
    assert readings(text) == want


@pytest.mark.parametrize("text", ["R1", "Room R2", "Risks R1-R5", "PHP8"])
def test_a_local_prefix_before_one_digit_is_an_identifier(text):
    assert mentions(text) == []
    assert "PHP" not in R._CURRENCY_CODES


# 3. a monthly series joined by "and", a bar, a slash or a spaced dash is counts

@pytest.mark.parametrize("text,want", [
    ("New members: Jan 12, Feb 14 and Mar 18.", ["12", "14", "18"]),
    ("Monthly churn: Oct 9, Nov 11 and Dec 6.", ["9", "11", "6"]),
    ("Members by month: 12 Jan, 14 Feb and 18 Mar.", ["12", "14", "18"]),
    ("Sign-ups: Jan 12 / Feb 14 / Mar 18.", ["12", "14", "18"]),
    ("Jan 12 | Feb 14 | Mar 18", ["12", "14", "18"]),
    ("Jan 12 - Feb 14 - Mar 18", ["12", "14", "18"]),
    ("New members: Jan 12 and Feb 14", ["12", "14"]),
])
def test_a_monthly_series_with_and_or_other_separators_is_counts(text, want):
    found = mentions(text)
    assert [m.text for m in found] == want and all(m.form != "date" for m in found), found


@pytest.mark.parametrize("text,want", [
    ("Closed Dec 24 and 25.", [("Dec 24", "24", "date"), ("25", "25", "date")]),
    ("Jan 12 and Feb 14", [("Jan 12", "12", "date"), ("Feb 14", "14", "date")]),
    ("Closed Dec 24 - Jan 2.", [("Dec 24", "24", "date"), ("Jan 2", "2", "date")]),
])
def test_a_two_item_pair_without_a_list_intro_stays_dates(text, want):
    assert readings(text) == want


# 4. halve reads as a multiplier of one half

@pytest.mark.parametrize("text,span", [
    ("Churn halved after the welcome call.", "halved"), ("halve the churn", "halve"),
    ("halving costs", "halving"), ("Revenue halves", "halves"),
])
def test_halve_is_a_multiplier_of_a_half(text, span):
    assert [(m.text, m.value, m.form) for m in mentions(text)] == [(span, D("0.5"), "multiplier")]


# 5. the technical register: a name's number is part of the name

@pytest.mark.parametrize("text", [
    "ISO 27001", "SOC 2", "GDPR Article 5", "TLS 1.3", "OAuth 2.0", "WCAG 2.1", "Python 3.12", "PostgreSQL 16",
    "React 19", "HTTP 429", "Port 5432", "PHP 8.2", "(Python 3.12)", "Wi-Fi 6", "Next.js 14", "iso 9001",
    "2FA", "3D", "B2B", "B2C", "Use 2FA and B2B billing",
])
def test_a_technical_name_and_its_number_are_not_a_quantity(text):
    assert mentions(text) == []


def test_a_quantity_after_a_technical_name_is_read():
    assert readings("ISO 27001 costs $5,000") == [("$5,000", "5000", "money")]
    assert readings("React 19 cut load time by 40%") == [("40%", "40", "percent")]


# 6. a markdown heading's own number is structure

@pytest.mark.parametrize("text,want", [
    ("## 2. Diagnosis", []), ("### 3.1 Plan", []), ("# 1 Intro", []), ("Text\n## 3. Plan", []),
    ("## 2. Diagnosis: 12 members", ["12"]), ("#1 rule", ["1"]), ("We are #2", ["2"]),
])
def test_a_heading_number_is_structure(text, want):
    assert [m.text for m in mentions(text)] == want


# 7. more verbs may follow a label list

@pytest.mark.parametrize("text,want", [
    ("Phases 2 and 3 cover onboarding", []), ("Steps 1-3 include setup", []),
    ("Phases 1, 2 and 3 focus on sales", []), ("Steps 4 and 5 handle billing", []),
    ("Phases 2-3 need 10 weeks", ["10"]), ("Phases 2 and 3 deliver results", []),
    ("Steps 1-2 build the base", []), ("Phases 2 and 3 classes", ["3"]),
])
def test_more_verbs_may_follow_a_label_list(text, want):
    assert [m.text for m in mentions(text)] == want


# 8. a day and month followed by a year is a date, even before a comma

@pytest.mark.parametrize("text", ["On 3 March 2026, we start.", "3 March 2026", "12 December 2025, then"])
def test_a_day_month_and_year_is_a_date(text):
    found = mentions(text)
    assert len(found) == 2 and all(m.form == "date" for m in found), found


# fifth review, probe comparison: readings the round-6 rules had started to hide

@pytest.mark.parametrize("text,want", [
    ("## 3 quick wins", ["3"]), ("### 5 things to fix this month", ["5"]),
])
def test_a_heading_number_before_a_lower_case_word_is_a_count(text, want):
    assert [m.text for m in mentions(text)] == want


@pytest.mark.parametrize("text,want", [
    ("| Teacher:student | 1:15 | 1:30 | Owner |", ["1", "15", "1", "30"]),
    ("| Capacity | 1:30 per class | | |", ["1", "30"]),
    ("Mat classes are 1:15, reformer 1:6.", ["1", "15", "1", "6"]),
    ("4:30 average session length.", ["4", "30"]),
    ("Average call: 4:30.", ["4", "30"]),
    ("Wait time 3:45 on average.", ["3", "45"]),
    ("Score of 3:15 on the audit.", ["3", "15"]),
    ("Lap time 1:45.", ["1", "45"]),
    ("Run 10:15 splits.", ["10", "15"]),
])
def test_ratios_durations_and_scores_are_not_clock_times(text, want):
    found = mentions(text)
    assert [str(m.value) for m in found] == want and all(m.form != "time" for m in found), found


def test_quarter_minutes_from_six_on_are_still_times():
    assert readings("Classes at 6:30, 7:45, 12:15, 17:30 and 19:00.") == [
        ("6:30", "6", "time"), ("7:45", "7", "time"), ("12:15", "12", "time"),
        ("17:30", "17", "time"), ("19:00", "19", "time")]
    assert readings("Mon 7:00-19:00") == [("7:00", "7", "time"), ("19:00", "19", "time")]
    assert readings("at 1:30") == [("1:30", "1", "time")]


def test_a_technical_name_before_a_range_does_not_hide_it():
    assert [m.value for m in mentions("Office 9 to 5, Monday to Friday.")] == [D(9), D(5)]


def test_juxtaposed_month_day_pairs_are_a_series():
    found = mentions("Sales: Jan 12 Feb 14 Mar 18")
    assert [m.text for m in found] == ["12", "14", "18"] and all(m.form != "date" for m in found)


# -- the module stays its own grammar -----------------------------------------------------

def test_the_reader_is_its_own_grammar_and_imports_no_engine():
    path = os.path.join(os.path.dirname(R.__file__), "read.py")
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
