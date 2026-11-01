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
    ("bookings double", ["2"], ["multiplier"]),
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
    ("10-15% more", ["10", "15"], ["range", "range"]),
    ("$20-$30 a class", ["20", "30"], ["range", "range"]),
    ("10-15k a month", ["10000", "15000"], ["range", "range"]),
    ("Weeks 1-2", ["1", "2"], ["range", "range"]),
    ("2000-3000 members", ["2000", "3000"], ["range", "range"]),
    ("2,025 members", ["2025"], ["digit"]),
    ("$2025", ["2025"], ["money"]),
    ("1 of 5 explanations", ["1", "5"], ["digit", "digit"]),
    ("zero and 0", ["0"], ["digit"]),
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
    "phase 2 starts",
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
    "2025-2026",
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
