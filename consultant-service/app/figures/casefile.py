"""The case file: what the client told us, as figures that say where each came from.

Every number in the client's own words becomes a `theirs` Figure with its source:
the interview answer it was in (`turn`, and `field` = the question id when the
client's page sent one), the free-text column it was typed into (`field`), or the
cell of a file they uploaded (`file`, `cell`, and the sheet in `field`). The
`quote` is the sentence the number sits in, cut to `QUOTE_MAX` characters.

Figure ids are stable and unique for a request:

    T<turn>-<n>      the n-th number in the interview answer at position <turn>
                     (1-based, in `ops_numbers_json`): T2-1, T2-2
    F-<field>-<n>    the n-th number in a free-text column: F-main_problem-1
    E<claim>-<n>     the n-th number in the evidence claim CE-<claim>, whose id
                     the client's files keep when another claim is removed:
                     E3-1 is CE-03. If two claims ever share a claim id (see
                     evidence.extract's start_index), the later figure takes
                     `.2` after its id: E3-1.2

The same row and the same reader give the same ids on every build.

The case file is stored in `Request.case_file_json` as a JSON list of figures.
A row made before the column existed has none: `load` builds the set from the
row's columns and does not write it. `save` rebuilds the whole case file from the
row's columns and stages it on the row, leaving the commit to the caller, so the
case file reaches the database in the commit that writes whatever it describes. It
is rebuilt, not patched, when the client's files change (`evidence.save` calls it),
so there is one way in and the case file cannot drift from the claims.

How many figures one text and one request may hold is bounded in `app/config.py`
(`CASE_FILE_FIGURES_PER_TEXT`, `CASE_FILE_FIGURES_PER_REQUEST`); a build stops at
the bound, in the order the texts are read.

Only the client's words are read: the interview answers (never the questions,
which we wrote), the free-text columns, and the values of the claims read out of
their files. A brief fact's value (`brief_json`) is the interview's summary and is
never read. Text the intake adds to the description (the facts they did not know,
the question the engagement answers) is ours and is cut out before reading.

A clock time and a date are not stored. `read.supported` passes them by their
form (a time against the hours the client gave), and a figure made from "6pm"
would hold the value 18 and vouch for "18 reformers".

This module imports no model and no pipeline code, so `app.pipeline.evidence` can
call it. A request is anything with the columns named here.
"""
from __future__ import annotations

import json
import math
import re
from bisect import bisect_right
from dataclasses import replace
from decimal import Decimal
from typing import Iterable

from app.config import settings
from app.figures.model import Figure, FigureSet, TheirsSource, as_json, from_json
from app.figures.read import Mention, mentions

#: Characters of one text that are read for numbers. A bound on work, far above
#: anything a form takes; text past it is not read.
MAX_TEXT_CHARS = 50_000
#: Characters of a figure's quote.
QUOTE_MAX = 240

#: What `create_request` appends to the description. Ours, not their words.
UNKNOWNS_NOTE = "Figures the client did not know"
QUESTION_NOTE = "The question this engagement answers:"

#: The columns the client typed into, in the order they are read.
FREE_TEXT_COLUMNS = ("business_description", "main_problem", "desired_outcome", "revenue_today")

_NOT_STORED_FORMS = frozenset({"time", "date"})
_OUR_NOTES = re.compile(
    r"\n\n(?:%s|%s).*?(?=\n\n|\Z)" % (re.escape(UNKNOWNS_NOTE), re.escape(QUESTION_NOTE)), re.S)
# "<file> . <sheet> . <CELL>", the source evidence.extract writes (a middle dot)
_FILE_SEP = " \u00b7 "
_ELLIPSIS = "\u2026"
# A sentence ends at ., ! or ? when what follows (after a space) does not start in
# lower case ("6 p.m. on Fridays" runs on; "22.50" has no space), and at a line break.
# The lookbehind starts a match only at the first mark of a run: without it a long run of
# dots is retried from every position and takes quadratic time (50,000 dots took a minute).
_SENTENCE_END = re.compile(r"(?<![.!?])[.!?]+[\"')\u201d\u2019]*(?=\s+[^a-z\s])|\n+")
_TRAILING_NUMBER = re.compile(r"(\d+)\s*$")
# A currency code the amount is written with ("$50 AUD", "CAD 100"): the reader keeps it in
# the mention's text.
_CODE_IN = re.compile(r"(?<![A-Za-z])[A-Z]{3}(?![A-Za-z])")


# -- reading the row -------------------------------------------------------------------

def _loads_list(raw: object) -> list:
    try:
        data = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _scope_question(req) -> str:
    """The question the interview agreed, which the intake copies into the
    description and, when they left it blank, into the desired outcome."""
    try:
        brief = json.loads(req.brief_json) if getattr(req, "brief_json", None) else None
    except (TypeError, ValueError):
        return ""
    question = brief.get("question") if isinstance(brief, dict) else None
    return " ".join(question.split()) if isinstance(question, str) else ""


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans, start = [], 0
    for m in _SENTENCE_END.finditer(text):
        spans.append((start, m.end()))
        start = m.end()
    spans.append((start, len(text)))
    return spans


def _quote(text: str, spans: list[tuple[int, int]], starts: list[int], m: Mention) -> str:
    """The sentence `m` sits in; past QUOTE_MAX, the stretch of it around the number."""
    lo, hi = spans[max(0, bisect_right(starts, m.start) - 1)]
    sentence = text[lo:hi]
    lo += len(sentence) - len(sentence.lstrip())
    sentence = sentence.strip()
    if len(sentence) <= QUOTE_MAX:
        return sentence
    first = m.start - lo
    last = min(m.end - lo, len(sentence))
    begin = max(0, first - (QUOTE_MAX - (last - first)) // 2)
    end = min(len(sentence), begin + QUOTE_MAX)
    begin = max(0, end - QUOTE_MAX)
    return (_ELLIPSIS if begin else "") + sentence[begin:end].strip() + (_ELLIPSIS if end < len(sentence) else "")


def _precision(value: Decimal) -> int:
    """Digits after the point, without the zeros a magnitude word adds
    (1.5k is 1500.0 and shows as 1,500); 22.50 keeps its one."""
    if value == 0:
        return 0
    _, digits, exponent = value.as_tuple()
    shown, digits = -exponent, list(digits)
    while shown > 0 and digits and digits[-1] == 0:
        digits.pop()
        shown -= 1
    return max(0, shown)


def _currency(text: str) -> str:
    """The unit of a money mention, from how it was written. Only a currency it
    names is returned: a code written with the amount ("$50 AUD", "CAD 100") is
    that currency whatever sign is beside it, and A$ and NZ$ are not US dollars. A
    bare figure is not given a currency it does not carry."""
    named = _CODE_IN.search(text)
    if named:
        return named.group()
    upper = text.upper()
    if "\u20ac" in text or "EUR" in upper:
        return "EUR"
    if "\u00a3" in text or "GBP" in upper:
        return "GBP"
    if "$" in text:
        return "USD" if text[:text.index("$")].lstrip("-\u2212").strip() in ("", "US") else ""
    return "USD" if "USD" in upper or "DOLLAR" in upper else ""


def _unit(m: Mention) -> str:
    # a fraction is read as the percent number ("a third" is 33.3333), so it prints with its sign
    if m.form in ("percent", "fraction"):
        return "percent"
    return _currency(m.text) if m.form == "money" else ""


def _figure(id: str, m: Mention, source: TheirsSource) -> Figure | None:
    try:
        return Figure(id=id, value=m.value, unit=_unit(m), period=None, kind="theirs", source=source,
                      precision=_precision(m.value))
    except ValueError:   # a number too long for the figure to hold
        return None


def _text_figures(text: str, prefix: str, *, turn: int | None, field: str | None,
                  limit: int) -> list[Figure]:
    """One figure per stored number in `text`, named `<prefix>-<n>`, the first
    `limit` of them in text order."""
    text = text[:MAX_TEXT_CHARS]
    spans = _sentence_spans(text)
    starts = [s for s, _ in spans]
    out: list[Figure] = []
    n = 0
    for m in mentions(text):
        if len(out) >= limit:
            break
        if m.form in _NOT_STORED_FORMS:
            continue
        n += 1
        figure = _figure(f"{prefix}-{n}", m, TheirsSource(
            turn=turn, field=field, quote=_quote(text, spans, starts, m), file=None, cell=None))
        if figure:
            out.append(figure)
    return out


# -- the client's files ----------------------------------------------------------------

def _value_text(value: object) -> str:
    """A claim's value as the cell shows it, for the reader. The model gives a
    string ("$1,240.00") or a number; a float is taken to the 15 digits it holds."""
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, str):
        return value.strip()[:100]
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and math.isfinite(value):
        d = Decimal(repr(float(format(value, ".15g"))))
        return format(Decimal(int(d)) if d == d.to_integral_value() else d, "f")
    return ""


def _sheet(source: object, file: str | None, cell: str | None) -> str | None:
    """The sheet in '<file> . <sheet> . <CELL>' (evidence.extract), or None."""
    if not (isinstance(source, str) and file):
        return None
    prefix, suffix = f"{file}{_FILE_SEP}", f"{_FILE_SEP}{cell}" if cell else ""
    if source.startswith(prefix) and source.endswith(suffix) and len(source) > len(prefix) + len(suffix):
        return source[len(prefix):len(source) - len(suffix)]
    return None


def _claim_figures(claims: Iterable, limit: int) -> list[Figure]:
    """The first `limit` figures in evidence claims (the CE- claims
    `evidence.extract` writes). A claim holds one number, the one verified against
    its cell; `text` is the extraction's own description of the cell, kept as the
    quote."""
    out: list[Figure] = []
    for position, claim in enumerate(claims, 1):
        if len(out) >= limit:
            break
        if not isinstance(claim, dict):
            continue
        value = _value_text(claim.get("value"))
        file = claim["file"] if isinstance(claim.get("file"), str) and claim["file"] else None
        cell = claim["cell"] if isinstance(claim.get("cell"), str) and claim["cell"] else None
        described = " ".join(str(claim.get("text") or "").split())
        source = TheirsSource(turn=None, field=_sheet(claim.get("source"), file, cell),
                              quote=(described or value)[:QUOTE_MAX], file=file, cell=cell)
        tail = _TRAILING_NUMBER.search(str(claim.get("id") or ""))
        number = str(int(tail.group(1))) if tail else str(position)
        n = 0
        for m in mentions(value):
            if m.form in _NOT_STORED_FORMS:
                continue
            n += 1
            figure = _figure(f"E{number}-{n}", m, source)
            if figure:
                out.append(figure)
    return out


def _place(known: dict[str, Figure], figure: Figure) -> None:
    """Add `figure` under its id, or under a free one if a different figure holds
    it. The same figure again changes nothing."""
    k = 1
    while True:
        candidate = figure if k == 1 else replace(figure, id=f"{figure.id}.{k}")
        held = known.get(candidate.id)
        if held is None:
            known[candidate.id] = candidate
            return
        if held == candidate:
            return
        k += 1


# -- the case file -----------------------------------------------------------------------

def build(req) -> list[Figure]:
    """Every theirs figure in the row's interview answers, free-text columns and
    evidence claims, in that order. Reads only; never touches the column. It stops
    at the bounds in `settings`: so many figures from one text, so many in all."""
    figures: dict[str, Figure] = {}
    per_text, per_request = settings.CASE_FILE_FIGURES_PER_TEXT, settings.CASE_FILE_FIGURES_PER_REQUEST

    for turn, pair in enumerate(_loads_list(getattr(req, "ops_numbers_json", None)), 1):
        answer = pair.get("answer") if isinstance(pair, dict) else None
        if not isinstance(answer, str) or not answer.strip():
            continue
        qid = pair.get("id")
        field = qid.strip() if isinstance(qid, str) and qid.strip() else None
        for figure in _text_figures(answer, f"T{turn}", turn=turn, field=field,
                                    limit=min(per_text, per_request - len(figures))):
            _place(figures, figure)

    question, seen = _scope_question(req), set()
    for field in FREE_TEXT_COLUMNS:
        text = getattr(req, field, None)
        if not isinstance(text, str):
            continue
        if field == "business_description":
            text = _OUR_NOTES.sub("", text)
        words = " ".join(text.split())
        if not words or words in seen or (field == "desired_outcome" and words == question):
            continue   # empty, the same words again, or the question we wrote
        seen.add(words)
        for figure in _text_figures(text.strip(), f"F-{field}", turn=None, field=field,
                                    limit=min(per_text, per_request - len(figures))):
            _place(figures, figure)

    for figure in _claim_figures(_loads_list(getattr(req, "evidence_json", None)),
                                 limit=per_request - len(figures)):
        _place(figures, figure)
    return list(figures.values())


def _stored(req) -> FigureSet | None:
    """The stored case file, or None when the row has none or it cannot be read."""
    raw = getattr(req, "case_file_json", None)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return FigureSet(from_json(d) for d in data) if isinstance(data, list) else None
    except (TypeError, ValueError):
        return None


def load(req) -> FigureSet:
    """The request's case file. A row with none stored (made before this step) or
    with one that cannot be read is built from its columns; nothing is written."""
    stored = _stored(req)
    return stored if stored is not None else FigureSet(build(req))


def save(db, req) -> None:
    """Stage the case file, built from the row's columns, on `req`. The caller
    commits. An empty case file is stored as "[]", so it is not mistaken for a row
    from before this step."""
    req.case_file_json = json.dumps([as_json(f) for f in build(req)])
    db.add(req)
