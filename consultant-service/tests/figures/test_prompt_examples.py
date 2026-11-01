"""Every number a prompt shows as an example is plainly an example.

A model copies what it is shown. If a prompt's example reads like a client's real
figure ("$22 vs $32", "144 reformer spots"), the copy lands in a client's answer
looking like fact. Two things keep that from happening, and this file holds both.

1. The checker catches a copy. Every quoted example that holds a digit or a number
   word is read with the real reader, against an EMPTY known set
   (`read.unsupported(example, FigureSet())`), and must be flagged: a copied
   example then drops its sentence or rejects its part, as any number nobody owns
   does. The only numbers allowed to go unflagged are the ones the reader passes
   by form: dates, clock times, labels ("Phase 2"), identifiers ("M3-A", "CF-04"),
   and a list marker. A digit that the reader passes over for any other reason
   ("24/7") is a number that could hide in a copy, and fails here.

2. The example looks invented. A value an example shows is round (one significant
   digit: 100, 50%, 20, 5) or a calendar constant (52 weeks, 12 months). A
   realistic-looking value would be mistaken for a figure about the business, and
   it can coincide with a real one.

What this file cannot do: it cannot catch a coincidence between an example and a
client's real figure. If a client's price really is $100 and the prompt's example
says "$100 a class", a copied example passes the checker as theirs. The round
values make that unlikely, never impossible; the only full cure is a prompt that
shows no number at all, which is what an example should do whenever it can.

Both checks cover every template under app/prompts and the screen block guide that
two of them carry in a variable. They also cover the prose of
app/screens/example.json, the worked screen the model is shown when it draws the
first screen of a system: its captions and its story, which are written for the
client and bound like the model's own. The rest of that file (the headings, rows
and cells of the drawn screens) is SAMPLE DATA, a region the law exempts, and it
must look real to teach the density; only the reader check applies to it (a number
in it would be caught if it were copied into prose).
"""
from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from app.figures import read
from app.figures.labels import LABEL_WORDS
from app.figures.model import FigureSet
from app.screens import generate, render

PROMPTS = Path(__file__).resolve().parents[2] / "app" / "prompts"
BLOCK_GUIDE = "screens/generate.py BLOCK_GUIDE"

EXAMPLE_JSON = "screens/example.json"
_ROOT = object()
# what the model writes as prose in the worked screen: a caption under each screen, and the story
_EXAMPLE_PROSE = re.compile(r"^/(?:screens/\d+/caption|story/.*)$")
# an example said in a clause rather than in quotes: "like C4=1240", "e.g. 40 seats", "such as 3 cards"
_LOOSE = re.compile(r"(?:\blike|\be\.g\.|\bfor example|\bsuch as)[ \t:]+(?![\"'<])([^,;)\"'\n]{1,60}?)(?=[,;)]|\.(?:\s|$)|$)", re.I | re.M)

#: Values that are not round and are not invented: the calendar, when the word
#: after the number is its unit ("52 weeks", "12 months", "365 days"). A bare 12 is
#: a number about the business.
CALENDAR = {Decimal(7): "days", Decimal(12): "months", Decimal(24): "hours", Decimal(30): "days",
            Decimal(52): "weeks", Decimal(60): "minutes", Decimal(365): "days"}
_WORD_AFTER = re.compile(r"[ 	]*([A-Za-z]+)")

_JINJA = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", re.S)
_DOUBLE = re.compile(r'"([^"\n]*)"')
_SINGLE = re.compile(r"(?<![\w'])'([^'\n]+?)'(?![\w'])")
_DIGITS = re.compile(r"\d+")
# identifiers: letters then a digit (M3-A, R8, Q3, v2.1); capitals, a hyphen, digits (CF-04);
# words joined by underscores (measure_in_week_1)
_TOKEN = re.compile(r"[A-Za-z]+\d[A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)*|[A-Z]{1,6}-\d[A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)*"
                    r"|[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+")
_LIST_MARKER = re.compile(r"^\s*\d+[.)]\s")
_WORD_BEFORE = re.compile(r"([A-Za-z]+)[ \t]*$")
_BY_FORM = frozenset({"time", "date"})


def examples_in(text: str) -> list[str]:
    """Every double- or single-quoted string in the template text, on one line,
    and every unquoted clause that follows "like", "e.g.", "for example" or "such as",
    that holds a digit or a number the reader counts. Jinja is cut out first, so a
    variable inside a quoted example does not count as part of it."""
    found: list[str] = []
    for line in _JINJA.sub(" ", text).splitlines():
        for rx in (_DOUBLE, _SINGLE, _LOOSE):
            for m in rx.finditer(line):
                s = m.group(1).strip()
                if any(ch.isdigit() for ch in s) or read.mentions(s):
                    found.append(s)
    return found


def hidden_digits(example: str) -> list[str]:
    """Digit runs the reader does not count that are not an identifier, a label or
    a list marker: numbers that would hide in a copy."""
    counted = [(m.start, m.end) for m in read.mentions(example)]
    idents = [(m.start(), m.end()) for m in _TOKEN.finditer(example)]
    hidden = []
    for d in _DIGITS.finditer(example):
        if any(a <= d.start() and d.end() <= b for a, b in counted + idents):
            continue
        if _LIST_MARKER.match(example) and d.start() < 4:
            continue
        word = _WORD_BEFORE.search(example[:d.start()])
        if word and word.group(1).lower() in LABEL_WORDS:
            continue
        hidden.append(d.group())
    return hidden


def uncaught(example: str) -> str | None:
    """Why a copy of `example` would get through the checker, or None.

    Every number the reader counts is either flagged against an empty known set or
    a date or a time, which it passes by form. What can hide is a digit the reader
    does not count at all; ALL of them are collected, so an example with a flagged
    number and a hidden one ("$100, open 24/7") is not let through by the first."""
    hidden = hidden_digits(example)
    if hidden:
        return f"the reader passes over {', '.join(hidden)}, and it is no identifier, label or date"
    assert all(read.supported(m, FigureSet()) == (m.form in _BY_FORM) for m in read.mentions(example))
    return None


def looks_real(example: str) -> list[str]:
    """The numbers in `example` that are neither round (one significant digit) nor
    a calendar constant. A date or a clock time is what it is and is not judged."""
    out = []
    for m in read.mentions(example):
        v = abs(m.value)
        if m.form in _BY_FORM or v == 0:
            continue
        after = _WORD_AFTER.match(example, m.end)
        if v in CALENDAR and after and after.group(1).lower() == CALENDAR[v]:
            continue
        if len(v.normalize().as_tuple().digits) > 1:
            out.append(m.text.strip())
    return out


def _templates() -> list[Path]:
    return sorted(PROMPTS.glob("*.j2"))


def _sources() -> dict[str, str]:
    """name -> text of every template, and of the block guide the screen prompts
    carry in a variable."""
    out = {p.name: p.read_text(encoding="utf-8") for p in _templates()}
    out[BLOCK_GUIDE] = generate.BLOCK_GUIDE
    return out


def _scanned() -> list[tuple[str, str]]:
    return [(name, e) for name, text in _sources().items() for e in examples_in(text)]


def example_json_leaves(node=_ROOT, path="") -> list[tuple[str, object]]:
    """Every string and every number in the worked screen example, with its path.
    A string is an example as a whole; a number is judged by its value. Booleans and
    nulls hold no figure."""
    node = render.load_example() if node is _ROOT else node
    if isinstance(node, dict):
        return [x for k, v in node.items() for x in example_json_leaves(v, f"{path}/{k}")]
    if isinstance(node, list):
        return [x for i, v in enumerate(node) for x in example_json_leaves(v, f"{path}/{i}")]
    if isinstance(node, bool) or node is None:
        return []
    return [(path, node)]


def example_prose() -> list[tuple[str, str]]:
    """The strings of the worked screen that are prose the model writes for the client."""
    return [(path, v) for path, v in example_json_leaves() if isinstance(v, str) and _EXAMPLE_PROSE.match(path)]


# -- the scanner itself ---------------------------------------------------------------

def test_the_scanner_finds_the_examples_and_judges_them():
    text = ('say "about $100 a class" or "Phase 2" or "M3-A" or "Example only" '
            'or "six-week pilot" or "$22 vs $32" or "at 6pm" or \'1 in 10\'')
    assert examples_in(text) == ["about $100 a class", "Phase 2", "M3-A", "six-week pilot", "$22 vs $32", "at 6pm",
                                 "1 in 10"]
    assert uncaught("about $100 a class") is None and looks_real("about $100 a class") == []
    assert looks_real("$22 vs $32") == ["$22", "$32"]
    assert looks_real("fifteen weeks") == ["fifteen"] and looks_real("52 weeks a year") == []
    assert looks_real("12 reformers") == ["12"] and looks_real("12 months") == []
    assert looks_real("25%") == ["25%"] and looks_real("50%") == []


def test_what_the_reader_passes_by_form_is_allowed_and_any_other_hidden_digit_is_not():
    for fine in ("Phase 2", "Step 4", "M3-A", "R8", "CF-04", "at 6pm", "09:00", "in 2025", "Example only"):
        assert uncaught(fine) is None, fine
    assert "24" in uncaught("open 24/7")                      # an idiom the reader skips hides its digits
    assert uncaught("$22 vs $32") is None and uncaught("six-week pilot") is None   # the reader flags these


def test_every_template_the_block_guide_and_the_worked_examples_prose_are_scanned():
    names = set(_sources())
    assert len(names) == len(_templates()) + 1 and BLOCK_GUIDE in names
    assert {"answer.j2", "decide.j2", "diagnose.j2", "capacity.j2", "journey.j2", "qa_numbers.j2"} <= names
    assert generate.BLOCK_GUIDE.strip()
    assert len(example_json_leaves()) > 500
    paths = [path for path, _ in example_prose()]
    assert "/story/intro" in paths and any(p.endswith("/caption") for p in paths) and len(paths) > 30
    assert not any(re.match(r"/screens/\d+/(rows|heading|subheading)", p) for p in paths)   # sample data is not prose


def test_a_hidden_digit_is_found_beside_a_flagged_number():
    assert uncaught("$100 a month, open 24/7") is not None and "24" in uncaught("$100 a month, open 24/7")
    assert uncaught("$100 a month, in 2025, for M3-A") is None


def test_an_example_said_in_a_clause_is_found_too():
    text = "Every cell is shown with its address, like C4=1240. Ask for a unit, e.g. USD, hours. Use 3 to 6 stages."
    assert examples_in(text) == ["C4=1240"]
    assert looks_real("C4=1240") == ["1240"]


# -- the two checks --------------------------------------------------------------------

def test_a_copied_example_would_be_caught_by_the_checker():
    """Every example with a number: the reader flags it against an empty known set,
    unless its only numbers are dates, times, labels or identifiers."""
    failing = [f"{name}: {e!r} -> {why}" for name, e in _scanned() if (why := uncaught(e))]
    assert not failing, "examples a copy of which would pass as a figure:\n" + "\n".join(failing)


def test_every_example_number_is_plainly_invented():
    """Every example number in every prompt is round (one significant digit) or a
    calendar constant."""
    failing = [f"{name}: {e!r} -> {', '.join(bad)}" for name, e in _scanned() if (bad := looks_real(e))]
    assert not failing, "examples that read like a client's own figures:\n" + "\n".join(failing)


def test_the_worked_screens_prose_holds_only_numbers_a_copy_of_which_is_caught_and_none_that_reads_like_a_figure():
    """A caption or a line of the story in the worked screen is prose the model may
    copy into the client's own, where it is bound like any other. It passes the same
    two checks as a prompt's example. The sample rows and cells are not held to the
    second: they are sample data, and look real on purpose."""
    caught = [f"{EXAMPLE_JSON}{p}: {v!r} -> {why}" for p, v in example_prose() if (why := uncaught(v))]
    invented = [f"{EXAMPLE_JSON}{p}: {v!r} -> {', '.join(bad)}" for p, v in example_prose() if (bad := looks_real(v))]
    assert not caught, "prose of the worked screen that would pass as a figure:\n" + "\n".join(caught)
    assert not invented, "prose of the worked screen that reads like a client's own figures:\n" + "\n".join(invented)


def test_every_number_of_the_worked_screens_sample_data_would_be_caught_if_copied():
    """The reader check, for the sample data: no digit hides from the reader."""
    hidden = [f"{EXAMPLE_JSON}{p}: {v!r} -> {why}" for p, v in example_json_leaves()
              if isinstance(v, str) and (why := uncaught(v))]
    assert not hidden, "\n".join(hidden)
