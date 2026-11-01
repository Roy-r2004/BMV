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

The first check covers every template. The second covers the prompts that write
for a client or read the client's own words (`IN_SCOPE`) and the screen block
guide; the other templates (the decision, analysis and diagnosis prompts, the
auditors, the extras) still hold some realistic-looking examples and are brought
to it by the tasks that own them.
"""
from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from app.figures import read
from app.figures.labels import LABEL_WORDS
from app.figures.model import FigureSet
from app.screens import generate

PROMPTS = Path(__file__).resolve().parents[2] / "app" / "prompts"
BLOCK_GUIDE = "screens/generate.py BLOCK_GUIDE"

#: The prompts that write prose a client reads, or read the client's own words:
#: both checks apply to them, and to the block guide the screen prompts carry.
IN_SCOPE = (
    "answer.j2", "roadmap.j2", "decompose.j2", "blueprint.j2", "technical_plan.j2", "playbook.j2",
    "screens_plan.j2", "screen.j2", "casefile.j2", "interview.j2", BLOCK_GUIDE,
)

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
    that holds a digit or a number the reader counts. Jinja is cut out first, so a
    variable inside a quoted example does not count as part of it."""
    found: list[str] = []
    for line in _JINJA.sub(" ", text).splitlines():
        for rx in (_DOUBLE, _SINGLE):
            for m in rx.finditer(line):
                s = m.group(1)
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
    """Why a copy of `example` would get through the checker, or None."""
    if read.unsupported(example, FigureSet()):
        return None
    hidden = hidden_digits(example)
    if hidden:
        return f"the reader passes over {', '.join(hidden)}, and it is no identifier, label or date"
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


def _scanned(only: tuple[str, ...] | None = None) -> list[tuple[str, str]]:
    return [(name, e) for name, text in _sources().items() if only is None or name in only
            for e in examples_in(text)]


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


def test_the_templates_and_the_block_guide_are_there():
    assert set(_sources()) >= set(IN_SCOPE)
    assert generate.BLOCK_GUIDE.strip()


# -- the two checks --------------------------------------------------------------------

def test_a_copied_example_would_be_caught_by_the_checker():
    """Every example with a number: the reader flags it against an empty known set,
    unless its only numbers are dates, times, labels or identifiers."""
    failing = [f"{name}: {e!r} -> {why}" for name, e in _scanned() if (why := uncaught(e))]
    assert not failing, "examples a copy of which would pass as a figure:\n" + "\n".join(failing)


def test_every_example_number_is_plainly_invented():
    """Every example number in the prompts that write for a client is round (one
    significant digit) or a calendar constant."""
    failing = [f"{name}: {e!r} -> {', '.join(bad)}" for name, e in _scanned(IN_SCOPE) if (bad := looks_real(e))]
    assert not failing, "examples that read like a client's own figures:\n" + "\n".join(failing)
