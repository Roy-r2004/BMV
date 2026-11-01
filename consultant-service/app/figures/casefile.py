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
the bound, in the order the texts are read. The files' figures are counted first,
up to half the request bound, so a long interview cannot starve them.

Only the client's words are read: the interview answers (never the questions,
which we wrote), the free-text columns, and the values of the claims read out of
their files. A brief fact's value (`brief_json`) is the interview's summary and is
never read. Text the intake adds to the description (the facts they did not know,
the question the engagement answers) is ours and is cut out before reading.

Units, from how the number was written: money in its currency (a code the reader
knows written with it, else the sign as the binder reads it: $ and US$ are USD, A$
AUD, NZ$ NZD, the euro and pound signs EUR and GBP), a percent or a fraction as "percent", a count followed by a
time word in that time unit (12 weeks, 8 hrs a week: "week", "hour"), and any other
plain count in the noun after it, as typed in lower case ("twelve reformers" is
12 "reformers"). A count with no noun straight after it ("12 of 40 members" is 12
with none, and 40 "members") has no unit.

A clock time and a date are not stored. `read.supported` passes them by their
form (a time against the hours the client gave), and a figure made from "6pm"
would hold the value 18 and vouch for "18 reformers".

This module imports the figure model, the reader and the binder's word tables (so a
currency sign or a time word means here what it means to the binder), and no stage or
pipeline code, so `app.pipeline.evidence` can call it. A request is anything with the
columns named here.
"""
from __future__ import annotations

import json
import math
import re
from bisect import bisect_right
from dataclasses import replace
from decimal import Decimal
from typing import Iterable, Iterator, NamedTuple

from app.config import settings
from app.figures.bind import _NUMBER_WORDS, _PHRASE_STOP, _SIGN_CURRENCY, _SKIP_WORDS, _WORD_CURRENCY
from app.figures.model import Figure, FigureSet, TheirsSource, as_json, from_json
from app.figures.read import _CURRENCY_CODES, Mention, mentions
from app.figures.words import TIME_CANON as _TIME_CANON

#: Characters of one text that are read for numbers. A bound on work, far above
#: anything a form takes; text past it is not read.
MAX_TEXT_CHARS = 50_000
#: Characters of a figure's quote.
QUOTE_MAX = 240

#: What `create_request` appends to the description. Ours, not their words.
UNKNOWNS_NOTE = "Figures the client did not know"
QUESTION_NOTE = "The question this engagement answers:"

#: The columns the client typed into, in the order they are read: every intake text
#: field a prompt shows the model (analyze, diagnose, playbook, the roadmap, the bridge
#: read target_customers, what_you_like, industry, timeline and budget_range), so a
#: number the model is shown in their words is theirs. New columns go at the end, so
#: the ids of the columns read before them do not move. The business name is a name,
#: not a statement of figures, and is not read.
FREE_TEXT_COLUMNS = ("business_description", "main_problem", "desired_outcome", "revenue_today",
                     "target_customers", "what_you_like", "industry", "timeline", "budget_range")

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
# A currency code the amount is written with ("CAD 100", "AUD50", "$50 AUD"): only the
# codes the reader knows (read._CURRENCY_CODES), so "$50 FOR a class" is dollars, not a
# currency called FOR. Whether the reader keeps a code after the amount in the mention's
# text has changed before, so the few characters after the mention are looked at too.
_CODES = "|".join(sorted(map(re.escape, _CURRENCY_CODES), key=len, reverse=True))
_CODE_IN = re.compile(rf"(?<![A-Za-z])(?:{_CODES})(?![A-Za-z])")
_CODE_AFTER = re.compile(rf"[ \t]{{0,2}}({_CODES})(?![A-Za-z])")
# a sign before the amount, with the letters that say which dollar it is (A$, NZ$, US$);
# what each stands for is the binder's one table (bind._SIGN_CURRENCY)
_SIGN = re.compile(r"[A-Z]{0,3}\$|[€£]")
_WORD = re.compile(r"[A-Za-z]+")
_AFTER_CHARS = 80   # room for a time word or a noun (NOUN_MAX) behind a few skipped words
# The time word a number is directly followed by ("12 weeks", "3-month", "8hrs"). The words
# are the model's closed table, said by what they stand for (hrs is hour); the extra
# spellings are the ones clients type. "8 hrs a week" is hours: the rate phrase after the
# word does not change what was counted.
# The time words are the shared table (words.TIME_CANON), the one the binder is to read
# with too, so a time word the case file reads is one the binder reads the same way.
_TIME_WORD_AFTER = re.compile(r"(?:-|[^\S\r\n]*)([A-Za-z]+)")
#: The longest noun kept as a count's unit.
NOUN_MAX = 30
# What the binder skips between a count and its noun ("12 new members", "8 more classes") and
# where it stops reading a noun phrase (function words, adverbs): the case file reads the noun
# the same way, so a figure's unit is a word the binder finds in the sentence too. "of" is a
# stop, not a word passed over: "12 of 40 members" counts nothing the 12 can name.
# The word after a count, after a space or a hyphen: letters and digits with hyphens and
# apostrophes inside. A word cut short by another kind of letter ("caf" of a word with an
# accent) is not read.
_NEXT_TOKEN = re.compile(r"(?:-|[^\S\r\n]+)([A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*)(?![^\W\d_])")
_NOUN = re.compile(r"[a-z]+(?:['-][a-z]+)*")
_DIGITS = re.compile(r"\d[\d.,]*")
_NUMBER_LEAD = _NUMBER_WORDS | {"quarter"}


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


class ClientText(NamedTuple):
    """One text in the client's own words: the text as it is read, the id prefix
    its figures take (T<turn>, F-<field>), and where it came from."""
    text: str
    prefix: str
    turn: int | None
    field: str | None


def _answer_texts(pairs: list) -> Iterator[ClientText]:
    for turn, pair in enumerate(pairs, 1):
        answer = pair.get("answer") if isinstance(pair, dict) else None
        if not isinstance(answer, str) or not answer.strip():
            continue
        qid = pair.get("id")
        field = qid.strip() if isinstance(qid, str) and qid.strip() else None
        yield ClientText(answer, f"T{turn}", turn, field)


def client_words(req) -> Iterator[ClientText]:
    """The one place that says which of the row's words are the client's: each
    interview answer (never the question we asked), then each free-text column with
    the notes the intake adds cut out, skipping a column that repeats words already
    read or holds only the scope question we wrote. A file's figures are not words
    and are read from its claims (`build`)."""
    yield from _answer_texts(_loads_list(getattr(req, "ops_numbers_json", None)))
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
        yield ClientText(text.strip(), f"F-{field}", None, field)


def client_texts(req) -> list[str]:
    """The client's own words on the row (`client_words`), as plain texts."""
    return [w.text.strip() for w in client_words(req)]


def answers(ops_numbers: object) -> list[str]:
    """The answers alone in interview pairs as the page sends them (a JSON list of
    {question, answer}), never the questions we asked."""
    return [w.text.strip() for w in _answer_texts(_loads_list(ops_numbers))]


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


def _currency(text: str, after: str = "") -> str:
    """The unit of a money mention, from how it was written (`after` is the few
    characters that follow it). Only a currency it names is returned: a code
    written with the amount ("$50 AUD", "CAD 100") is that currency whatever sign
    is beside it, and A$ and NZ$ are not US dollars. A bare figure is not given a
    currency it does not carry."""
    named = _CODE_IN.search(text) or _CODE_AFTER.match(after)
    if named:
        return named.group(named.lastindex or 0)
    sign = _SIGN.search(text)
    if sign:
        # the binder's table: $ and US$ are USD, A$ and AU$ AUD, NZ$ NZD...; a sign it does not list names none
        return _SIGN_CURRENCY.get(sign.group(), "")
    return next((_WORD_CURRENCY[w.lower()] for w in _WORD.findall(text) if w.lower() in _WORD_CURRENCY), "")


def _time_unit(after: str) -> str:
    """The time unit of the number just before `after` ("week" for "12 weeks"), or ""."""
    word = _TIME_WORD_AFTER.match(after)
    return _TIME_CANON.get(word.group(1).lower(), "") if word else ""


def _number_led(token: str) -> bool:
    """A hyphen compound that starts with a number or a number word ("50-minute",
    "half-hour", "two-bedroom"): a measure of the noun that follows, not the noun."""
    head, hyphen, _ = token.partition("-")
    return bool(hyphen) and (_DIGITS.fullmatch(head) is not None or head in _NUMBER_LEAD)


def _counted_unit(after: str) -> str:
    """What a plain count counts, from the words after it: a time unit ("week" for
    "12 weeks", "8 hrs a week"), else the noun as typed in lower case ("reformers" for
    "twelve reformers", "classes" for "8 classes a day"), else "". A noun is the first
    word after the count once "more", "new", "total" and the like (the binder's skip
    words) and a number-led compound ("six 50-minute classes": classes) are passed over.
    A function word or an adverb, punctuation, the end, or a word longer than NOUN_MAX
    leaves it without a unit ("12 of 40 members" is 12 with none and 40 members). A
    generic noun ("2 others nearby", "6 things") is the unit like any other, so the binder
    can tell a count whose noun says nothing (words.GENERIC_NOUNS, a wildcard there) from
    one with no noun at all."""
    unit = _time_unit(after)
    if unit:
        return unit
    pos = 0
    while True:
        found = _NEXT_TOKEN.match(after, pos)
        if not found:
            return ""
        word, pos = found.group(1).lower(), found.end()
        if word in _SKIP_WORDS or _number_led(word):
            continue
        if word in _TIME_CANON:
            return _TIME_CANON[word]
        if not _NOUN.fullmatch(word) or not 2 <= len(word) <= NOUN_MAX:
            return ""
        return "" if word in _PHRASE_STOP else word


def _unit(m: Mention, after: str) -> str:
    # a fraction is read as the percent number ("a third" is 33.3333), so it prints with its sign
    if m.form in ("percent", "fraction"):
        return "percent"
    if m.form == "money":
        return _currency(m.text, after)
    # a position ("the 3rd week") or a multiplier ("3x") counts nothing
    return _counted_unit(after) if m.form in ("digit", "word", "range") else ""


def unit_of(m: Mention, text: str) -> str:
    """The unit the case file gives mention `m` of `text`, from how it was written:
    a currency, "percent", a time unit, the noun it counts, or ""."""
    return _unit(m, text[m.end:m.end + _AFTER_CHARS])


def _figure(id: str, m: Mention, source: TheirsSource, text: str) -> Figure | None:
    """The figure for mention `m` of `text`."""
    try:
        return Figure(id=id, value=m.value, unit=unit_of(m, text), period=None,
                      kind="theirs", source=source,
                      precision=_precision(m.value))
    except ValueError:   # a number too long for the figure to hold
        return None


def read_text(text: str, prefix: str, *, turn: int | None = None, field: str | None = None,
              limit: int) -> list[tuple[Mention, Figure]]:
    """One figure per stored number in `text`, named `<prefix>-<n>`, the first
    `limit` of them in text order, each with the mention it was read from (whose
    form says how it was written: a count, money, a percent...)."""
    text = text[:MAX_TEXT_CHARS]
    spans = _sentence_spans(text)
    starts = [s for s, _ in spans]
    out: list[tuple[Mention, Figure]] = []
    n = 0
    for m in mentions(text):
        if len(out) >= limit:
            break
        if m.form in _NOT_STORED_FORMS:
            continue
        n += 1
        figure = _figure(f"{prefix}-{n}", m, TheirsSource(
            turn=turn, field=field, quote=_quote(text, spans, starts, m), file=None, cell=None), text)
        if figure:
            out.append((m, figure))
    return out


def _text_figures(text: str, prefix: str, *, turn: int | None, field: str | None,
                  limit: int) -> list[Figure]:
    return [f for _, f in read_text(text, prefix, turn=turn, field=field, limit=limit)]


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
            if len(out) >= limit:   # a hard bound: a claim with several numbers stops mid-claim
                break
            if m.form in _NOT_STORED_FORMS:
                continue
            n += 1
            figure = _figure(f"E{number}-{n}", m, source, value)
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
    at the bounds in `settings`: so many figures from one text, so many in all.

    The files' figures are counted against the bound first, up to half of it, so a
    long interview cannot starve them; they are still listed last. What the files
    do not use is left to the client's typed words, so neither side can take more
    than its share from the other."""
    figures: dict[str, Figure] = {}
    per_text, per_request = settings.CASE_FILE_FIGURES_PER_TEXT, settings.CASE_FILE_FIGURES_PER_REQUEST
    from_files = _claim_figures(_loads_list(getattr(req, "evidence_json", None)), limit=per_request // 2)
    per_request -= len(from_files)

    for words in client_words(req):
        for figure in _text_figures(words.text, words.prefix, turn=words.turn, field=words.field,
                                    limit=min(per_text, per_request - len(figures))):
            _place(figures, figure)

    for figure in from_files:
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
