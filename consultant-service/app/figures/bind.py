"""Binding: print a figure's own value where the model wrote a number it names,
and drop the sentences whose numbers nobody owns.

`bind(text, known)` reads every number the text holds (`read.mentions`) and every
`{{F:<id>}}` token, and decides each one.

A number binds to a figure only if the units fit, and only on a value it can
stand for:

    units       a money mention binds only to a figure in the SAME currency (a euro
                is not a dollar); a percent mention only to a percent figure; a
                bare number (no currency sign, no percent) only to a figure that is
                neither money nor percent, so "1,000 square feet" can never be read
                from a dollar amount. When the word after a bare number is a unit of
                time ("10 days") it must agree with a figure in time ("10.03 weeks"
                is not it), and a count noun ("6 members") is not a figure in weeks.
                Any other unit (classes, GB) needs a noun after the number, if there
                is one, to be that unit. A range takes its shape from the whole range:
                "$20-30" is two money ends, "10-15%" two percent ends.
    value       a mention equal to the figure's value, or to the value as it displays
                (44928 shown as ~45,000), is exact; any other mention within half a
                percent is near. Exact beats near. A near mention is rewritten only
                to a derived or ours figure (the model rounded a number we worked
                out); against a theirs or reference figure it is unresolved, since
                we never silently correct a client's own number. Figures of
                different values at the same distance make the mention ambiguous, so
                "about $4,700" between 4,720 and 4,680 names neither.
    equal       figures of one value and unit: the most trusted kind wins (theirs,
                derived, reference, ours), then the first added.

An unresolved mention is left as written and reported.

Only the number is replaced, never what the sentence says around it. "twelve
classes" becomes "12 classes". The currency sign, percent sign, and the words
percent, USD or dollars that the model put on its number are kept; a symbol it did
not write is not added; a magnitude it wrote ("10k", "1.5 million") is spelled out
as the figure's digits. A figure that rounding changed gets a "~" in front, except
after a hedge word ("about", "around", "roughly", "approximately", "nearly",
"circa") or a "~" the model wrote, which stay exactly as written: they may be
prepositions, and the sentence already hedges.

Never rewritten: times and dates, and the kinds whose words carry the meaning,
multipliers ("3x", "twice"), ordinals ("3rd") and fractions ("half"). They stay as
written when a figure supports them (`read.supported`) and are reported unresolved
when none does. A number inside a client's quotation (between double quotes) is
checked against the figures and bound only on an exact match, never rewritten.

A token `{{F:<id>}}` is replaced by that figure's number. A currency sign before
it, or a percent sign or a unit word after it, is not doubled: the number prints
without its own symbol, and the neighbour must fit the figure (a "%" after a dollar
figure is unresolved). Where nothing next to it names the unit, the figure prints
whole ("$22", "25%", "6 weeks", "24 GB"). A token with an unknown id, one stuck to
digits ("12{{F:A}}"), and any "{{F:" still in the output (nested or unclosed
braces) are unresolved and reported, never left silently.

`BindResult.unresolved` holds `Mention` records for numbers and `UnresolvedToken`
records for tokens. Both have `.text`, `.start` and `.end`, and the positions are
in `BindResult.text` (the bound text), so `result.text[u.start:u.end] == u.text`
always holds. `BindResult.bound` lists each figure used once, in the order of first
use. A figure that supports a quoted number is listed, and the number stays.

`clean_sentences` binds, then removes each sentence that still holds an unresolved
record. `segments` returns the bound text in pieces, each bound number carrying its
figure's id, for the web.

The module imports the reader and the model only. It has no top-level import of
`app.engine` or `app.pipeline`.
"""
from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, replace
from typing import NamedTuple

from app.figures.model import _TIME_UNITS, Figure, FigureSet, display, display_number, displayed_value
from app.figures.read import _CURRENCY_CODES, _MONEY_UNITS, Mention, mentions, supported


@dataclass(frozen=True)
class UnresolvedToken:
    """A `{{F:<id>}}` token that could not be bound: its id is not a known figure,
    or what stands beside it contradicts the figure, or it is stuck to digits. A
    `{{F:` left in the output by nested or unclosed braces is reported with
    `text="{{F:"` and an empty `figure_id`. `start` and `end` are positions in the
    bound text; `text` is the token as written."""
    text: str
    start: int
    end: int
    figure_id: str


Unresolved = Mention | UnresolvedToken


@dataclass(frozen=True)
class BindResult:
    """`text` is the bound text. `bound` lists each figure used once, in the order
    it was first used. `unresolved` lists, in text order, every number or token
    that was left as written, with positions in `text`."""
    text: str
    bound: list[Figure]
    unresolved: list[Unresolved]


# -- units ------------------------------------------------------------------------------------

# Most trusted first: what the client said, what we worked out from it, what a
# publication says, and last what we only propose.
_TRUST = {"theirs": 0, "derived": 1, "reference": 2, "ours": 3}

# Forms whose words carry the meaning. A figure may support them; they are not
# rewritten, because "3" is not "3x", "3rd" or "a third".
_KEPT_AS_WRITTEN = frozenset({"time", "date", "multiplier", "ordinal", "fraction"})

_SP = r"[ \t\u00a0]"

# the currency a sign or a word stands for; a sign not listed names no currency
_SIGN_CURRENCY = {"$": "USD", "US$": "USD", "\u20ac": "EUR", "\u00a3": "GBP", "A$": "AUD", "AU$": "AUD",
                  "C$": "CAD", "CA$": "CAD", "NZ$": "NZD", "HK$": "HKD", "S$": "SGD"}
_WORD_CURRENCY = {"dollar": "USD", "dollars": "USD", "euro": "EUR", "euros": "EUR"}
_CODES = "|".join(map(re.escape, _CURRENCY_CODES))

# what a mention carries around its digits, which a replacement keeps: a currency
# sign or code before it, and "%", "percent", "percentage points", a code or
# "dollars" after it
_LEAD = re.compile(rf"[-\u2212]?(?P<cur>(?:[A-Z]{{1,3}}\$|\$|\u20ac|\u00a3|(?:{_CODES})\.?){_SP}?)?")
_TRAIL_BODY = (rf"(?:{_SP}*%|(?i:{_SP}*per{_SP}?cent|{_SP}*percentage{_SP}+points?)(?![A-Za-z])"
               rf"|{_SP}?(?:{_CODES})\.?(?![A-Za-z])|{_SP}+(?i:dollars?|euros?)(?![A-Za-z]))")
_TRAIL = re.compile(_TRAIL_BODY + r"\Z")
_TRAIL_HEAD = re.compile(_TRAIL_BODY)
_LEAD_BEFORE = re.compile(rf"(?:[A-Z]{{1,3}}\$|\$|\u20ac|\u00a3|(?:{_CODES})\.?){_SP}?\Z")


class _Shape(NamedTuple):
    lead: str                # the currency written before the number, "" if none
    trail: str               # the percent or currency words written after it, "" if none
    kind: str                # "percent", "money" or "bare": how the mention presents its number
    currency: str | None     # for money: the currency it names, None if it names none we know


def _currency_of(lead: str, trail: str) -> str | None:
    cur = lead.strip().rstrip(".")
    if cur:
        return _SIGN_CURRENCY.get(cur) or (cur if cur in _MONEY_UNITS else None)
    word = trail.strip().rstrip(".")
    return _WORD_CURRENCY.get(word.lower()) or (word if word in _MONEY_UNITS else None)


def _shape(text: str, form: str) -> _Shape:
    lead = _LEAD.match(text)
    cur = lead.group("cur") or ""
    t = _TRAIL.search(text, lead.end())
    trail = t.group() if t else ""
    if "%" in trail or "per" in trail.lower() or form == "percent":
        return _Shape(cur, trail, "percent", None)
    if cur or trail or form == "money":
        return _Shape(cur, trail, "money", _currency_of(cur, trail))
    return _Shape(cur, trail, "bare", None)


def _share_range(a: _Shape, b: _Shape) -> tuple[_Shape, _Shape]:
    """The two ends of a range take their shape from the whole range: a percent
    anywhere makes both ends percents, a currency anywhere makes both ends money.
    An end that names its own currency keeps it ("$1,000 to EUR 900")."""
    kinds = {a.kind, b.kind}
    kind = "percent" if "percent" in kinds else "money" if "money" in kinds else "bare"

    def end(own: _Shape, other: _Shape) -> _Shape:
        named = own.currency if (own.lead or own.trail) else None
        return own._replace(kind=kind, currency=None if kind != "money" else named or other.currency)

    return end(a, b), end(b, a)


# Ends of a range are numbers read as plain quantities.
_NOT_A_RANGE_END = frozenset({"time", "date", "multiplier", "ordinal", "fraction"})
_RANGE_JOIN = re.compile(rf"{_SP}*[-\u2013\u2014]{_SP}*|{_SP}+to{_SP}+")

# time words, by what they stand for ("hrs" is "hour"); the model's own table is the
# source for the words, the abbreviations are the ones clients type
_TIME_CANON = {word: one for one, many in _TIME_UNITS for word in (one, many)}
_TIME_CANON.update({"sec": "second", "secs": "second", "min": "minute", "mins": "minute", "hr": "hour",
                    "hrs": "hour", "wk": "week", "wks": "week", "yr": "year", "yrs": "year"})

# words that follow a number without naming what it counts
_FUNCTION_WORDS = frozenset(
    "a an the of to or and in on at by for from with without per than as is are was were be been being will "
    "would can could may might should must shall has have had do does did it its we you they he she i us them "
    "this that these those then but so if when while which who whom what not no nor yet up out off over into "
    "onto about around roughly approximately nearly circa each every both either".split())

_NEXT_WORD = re.compile(rf"(?:-|{_SP}+)([A-Za-z]+)")


def _stem(word: str) -> str:
    """A word without its plural: classes -> class, reformers -> reformer."""
    w = word.lower()
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith(("sses", "xes", "ches", "shes", "zzes")):
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _unit_fits(word: str | None, unit: str) -> bool:
    """Whether the word after a bare number can be the unit of a figure in `unit`.
    No word, a word that names nothing ("of", "and"), and a figure with no unit of
    its own contradict nothing. A time word needs a figure in the same time unit; a
    figure in time needs the word, when there is a noun, to be that time word; any
    other unit (classes, GB) needs a noun after the number to be that unit."""
    if word is None or unit in ("", "count"):
        return True
    figure_time, word_time = _TIME_CANON.get(unit.lower()), _TIME_CANON.get(word)
    if figure_time:
        return word_time == figure_time or (word_time is None and word in _FUNCTION_WORDS)
    if word_time:
        return False
    if word in _FUNCTION_WORDS:
        return True
    return _stem(word) in {_stem(w) for w in re.findall(r"[A-Za-z]+", unit)}


def _admissible(f: Figure, shape: _Shape, word: str | None) -> bool:
    if shape.kind == "percent":
        return f.unit == "percent"
    if shape.kind == "money":
        return shape.currency is not None and f.unit == shape.currency
    return f.unit not in _MONEY_UNITS and f.unit != "percent" and _unit_fits(word, f.unit)


def _pick(m: Mention, shape: _Shape, word: str | None, known: FigureSet, quoted: bool) -> Figure | None:
    """The one figure `m` names, or None when it names none or cannot choose."""
    cands = [f for f in known.match(m.value) if _admissible(f, shape, word)]
    equal = [f for f in cands if f.value == m.value]
    shown = [f for f in cands if f.value != m.value and displayed_value(f) == m.value]
    near = [f for f in cands if f.value != m.value and displayed_value(f) != m.value]
    pool, is_near = equal or shown, not (equal or shown)
    if is_near:
        pool = near
    if not pool or (is_near and quoted):
        return None
    if len({f.value for f in pool}) > 1:
        return None   # figures of different values: a rounding that names none of them
    if len({f.unit for f in pool}) > 1:
        return None   # the same value in two units: 12 weeks or 12 reformers?
    winner = min(pool, key=lambda f: _TRUST[f.kind])   # min keeps the first of equals
    if is_near and winner.kind in ("theirs", "reference"):
        return None   # the model altered the client's own number
    return winner


# -- hedges and quotations ---------------------------------------------------------------------

# a hedge word right before a number, or a "~" / approximately-equal sign: the
# sentence already says "about", so the figure's own "~" would say it twice
_HEDGE = re.compile(
    rf"(?:(?<![A-Za-z])(?:about|around|roughly|approximately|nearly|circa){_SP}+|[~\u2248]{_SP}*)\Z", re.I)

# a client's quotation: text between straight or curly double quotes
_QUOTE = re.compile(r'"[^"]{0,400}"|\u201c[^\u201d]{0,400}\u201d')

_TOKEN = re.compile(r"\{\{\s*F\s*:\s*([^{}]*?)\s*\}\}")
_OPENER = re.compile(r"\{\{\s*F\s*:")


class _Decision(NamedTuple):
    leave: bool            # supported, and kept exactly as written
    figure: Figure | None  # set: the span is replaced
    text: str              # what replaces it, when `figure` is set


_LEAVE = _Decision(True, None, "")
_UNRESOLVED = _Decision(False, None, "")


def _contradicts(word: str, unit: str) -> bool:
    """A time word right after a token that is not the figure's own time unit
    ("{{F:PL-01}}-day" for a figure in weeks): the token's figure is not that."""
    word_time = _TIME_CANON.get(word.lower())
    return bool(word_time) and unit not in ("", "count") and _TIME_CANON.get(unit.lower()) != word_time


def _same_unit_word(word: str, unit_word: str) -> bool:
    a, b = _TIME_CANON.get(word.lower()), _TIME_CANON.get(unit_word.lower())
    if a or b:
        return a == b
    return _stem(word) in {_stem(w) for w in re.findall(r"[A-Za-z]+", unit_word)}


def _decide_token(figure_id: str, text: str, start: int, end: int, known: FigureSet, hedged: bool) -> _Decision:
    f = known.get(figure_id)
    if f is None or text[start - 1:start].isdigit() or text[end:end + 1].isdigit():
        return _UNRESOLVED
    after = _NEXT_WORD.match(text, end)
    if after and _contradicts(after.group(1), f.unit):
        return _UNRESOLVED
    lead = _LEAD_BEFORE.search(text[max(0, start - 8):start])
    trail = _TRAIL_HEAD.match(text, end)
    if trail and ("%" in trail.group() or "per" in trail.group().lower()):
        fits = f.unit == "percent"
    elif lead or trail:
        currency = _currency_of(lead.group() if lead else "", trail.group() if trail else "")
        fits = currency is not None and f.unit == currency
    else:
        # nothing beside it names the unit: the figure prints whole, but a unit word
        # the sentence already has right after it is not said twice
        shown = display_number(f, tilde=not hedged)
        unit_word = display(f)[len(display_number(f)):].strip()
        if unit_word and not (after and _same_unit_word(after.group(1), unit_word)):
            shown += " " + unit_word
        return _Decision(False, f, shown)
    if not fits:
        return _UNRESOLVED
    return _Decision(False, f, display_number(f, symbols=False, tilde=not hedged))


def _decide_mention(m: Mention, shape: _Shape, word: str | None, known: FigureSet, quoted: bool,
                    hedged: bool, hours: set[int] | None) -> _Decision:
    if m.form in _KEPT_AS_WRITTEN:
        return _LEAVE if supported(m, known, hours) else _UNRESOLVED
    f = _pick(m, shape, word, known, quoted)
    if f is None:
        return _UNRESOLVED
    if quoted:
        return _Decision(False, f, m.text)   # checked, bound, never rewritten
    body = re.fullmatch(r"(~?-?)(.*)", display_number(f, symbols=False, tilde=not hedged), re.S)
    return _Decision(False, f, f"{body.group(1)}{shape.lead}{body.group(2)}{shape.trail}")


# -- one pass over the text -----------------------------------------------------------------------

@dataclass
class _Run:
    text: str
    bound: list[Figure]
    unresolved: list[Unresolved]
    spans: list[tuple[int, int, str]]   # (start, end, figure id) of each replacement, in `text`


def _run(text: str, known: FigureSet, hours: set[int] | None) -> _Run:
    text = text or ""
    tokens = list(_TOKEN.finditer(text))
    token_starts = [t.start() for t in tokens]
    token_ends = [t.end() for t in tokens]
    ms: list[Mention] = []
    for m in mentions(text):
        # the digits inside a token's id are the id's, not a number the model wrote
        i = bisect_right(token_ends, m.start)
        if i < len(tokens) and token_starts[i] < m.end:
            continue
        ms.append(m)
    if not ms and not tokens and not _OPENER.search(text):
        return _Run(text, [], [], [])

    shapes = [_shape(m.text, m.form) for m in ms]
    partner: dict[int, int] = {}   # the other end of a range, by index
    for i in range(len(ms) - 1):
        a, b = ms[i], ms[i + 1]
        if i in partner or a.form in _NOT_A_RANGE_END or b.form in _NOT_A_RANGE_END:
            continue
        gap = text[a.end:b.start]
        if len(gap) <= 6 and _RANGE_JOIN.fullmatch(gap):
            partner[i], partner[i + 1] = i + 1, i
    for i, j in partner.items():
        if i < j:
            shapes[i], shapes[j] = _share_range(shapes[i], shapes[j])

    quotes = [(q.start(), q.end()) for q in _QUOTE.finditer(text)]
    quote_starts = [q[0] for q in quotes]

    items: list[tuple[int, int, int, bool]] = [(t.start(), t.end(), i, True) for i, t in enumerate(tokens)]
    items += [(m.start, m.end, i, False) for i, m in enumerate(ms)]
    items.sort(key=lambda it: (it[0], it[1]))

    pieces: list[str] = []
    length = 0                  # length of the bound text so far
    cursor = 0                  # how much of `text` has been copied or replaced
    bound: dict[str, Figure] = {}
    unresolved: list[Unresolved] = []
    spans: list[tuple[int, int, str]] = []
    for start, end, index, is_token in items:
        hedged = bool(_HEDGE.search(text[max(0, start - 40):start]))
        if is_token:
            fid = tokens[index].group(1).strip()
            d = _decide_token(fid, text, start, end, known, hedged)
        else:
            m = ms[index]
            word = None
            if shapes[index].kind == "bare":
                last = max(index, partner.get(index, index))
                nxt = _NEXT_WORD.match(text, ms[last].end)
                word = nxt.group(1).lower() if nxt else None
            q = bisect_right(quote_starts, m.start) - 1
            quoted = q >= 0 and m.end <= quotes[q][1]
            d = _decide_mention(m, shapes[index], word, known, quoted, hedged, hours)
        if d.leave:
            continue
        gap = text[cursor:start]
        pieces.append(gap)
        at = length + len(gap)
        if d.figure is not None:
            pieces.append(d.text)
            spans.append((at, at + len(d.text), d.figure.id))
            length = at + len(d.text)
            bound.setdefault(d.figure.id, d.figure)
        else:
            written = text[start:end]
            pieces.append(written)
            if is_token:
                unresolved.append(UnresolvedToken(written, at, at + len(written), fid))
            else:
                unresolved.append(replace(ms[index], start=at, end=at + len(written)))
            length = at + len(written)
        cursor = end
    pieces.append(text[cursor:])
    out = "".join(pieces)

    # a "{{F:" still in the output (nested or unclosed braces) is a token nobody resolved
    reported = [(u.start, u.end) for u in unresolved if isinstance(u, UnresolvedToken)]
    starts = [r[0] for r in reported]
    extra = []
    for o in _OPENER.finditer(out):
        k = bisect_right(starts, o.start()) - 1
        if k < 0 or o.start() >= reported[k][1]:
            extra.append(UnresolvedToken(o.group(), o.start(), o.end(), ""))
    if extra:
        unresolved = sorted(unresolved + extra, key=lambda u: u.start)
    return _Run(out, list(bound.values()), unresolved, spans)


def bind(text: str, known: FigureSet, *, hours: set[int] | None = None) -> BindResult:
    """`text` with each number that names a known figure printed as that figure's
    value, and the numbers and tokens that name none listed in `unresolved`. See
    the module docstring for the rules."""
    r = _run(text, known, hours)
    return BindResult(r.text, r.bound, r.unresolved)


def segments(text: str, known: FigureSet) -> list[dict]:
    """The bound text in order as `{"text": str}` and `{"figure": id, "text": str}`
    pieces. Joined, the pieces are exactly `bind(text, known).text`. A number left
    unresolved is plain text. An empty text gives no pieces."""
    r = _run(text, known, None)
    out: list[dict] = []
    pos = 0
    for start, end, figure_id in r.spans:
        if start > pos:
            out.append({"text": r.text[pos:start]})
        out.append({"figure": figure_id, "text": r.text[start:end]})
        pos = end
    if pos < len(r.text):
        out.append({"text": r.text[pos:]})
    return out


# -- sentences ----------------------------------------------------------------------------------------

_TERMINATORS = ".!?\u2026"
_CLOSERS = "\"')]}\u201d\u2019\u00bb"
_OPENERS = "(['\"\u201c\u2018"
# words whose full stop does not end a sentence ("Dr. Smith", "vs. the rest")
_ABBREVIATIONS = frozenset({"dr.", "mr.", "mrs.", "ms.", "prof.", "sr.", "jr.", "st.", "vs.", "cf.", "approx.",
                            "inc.", "ltd.", "corp.", "fig.", "vol.", "ca.", "viz.", "al."})
_DOTTED = re.compile(r"(?:[A-Za-z]{1,2}\.){2,}")        # e.g.  i.e.  U.S.  a.m.  Ph.D.
_CLOCK = frozenset({"a.m.", "p.m."})                    # these may end a sentence
_INITIAL = re.compile(r"[A-Z]\.")                        # J. Smith
_SPACE = re.compile(r"\s+")

# A line that is its own unit: a bullet or quote mark, a numbered item, a heading, a
# table row, a bold lead ("**Rent:** $999", "**Costs**"), or a short "Label: value"
# line. Such a line is never split into sentences, and never joined to its neighbours.
_STRUCTURE = re.compile(
    r"[ \t]*(?:[-*+\u2022\u2013>][ \t]+|\d{1,3}[.)][ \t]+|#{1,6}[ \t]+|\|"
    r"|(?:\*\*|__)[^\n]{1,80}?(?:\*\*|__)"
    r"|[A-Z][\w&/()'-]*(?:[ \t]+[\w&/()'-]+){0,2}:[ \t]+\S)")


def _stop_before(text: str, i: int) -> int:
    """The index just after the sentence's last mark before position `i`,
    stepping back over closing quotes and brackets."""
    while i > 0 and text[i - 1] in _CLOSERS:
        i -= 1
    return i


def _ends_sentence_inline(text: str, a: int, b: int) -> bool:
    """Whether the spaces text[a:b] (no line break) end a sentence."""
    j = _stop_before(text, a)
    if j == 0 or text[j - 1] not in _TERMINATORS:
        return False
    if text[j - 1] != ".":
        return True                      # "?" "!" and the ellipsis end it
    k = j - 1
    while k > 0 and not text[k - 1].isspace():
        k -= 1
    word = text[k:j].lstrip(_OPENERS)
    low = word.lower()
    next_char = text[b] if b < len(text) else ""
    if low in _CLOCK:
        return next_char.isupper()
    if low in _ABBREVIATIONS or _DOTTED.fullmatch(word) or _INITIAL.fullmatch(word):
        return False
    return not next_char.islower()       # "5. and then ..." is not a new sentence


def _units(text: str) -> list[tuple[int, int, int]]:
    """Split into sentence-like units as (start, body end, end): the body, then the
    white space that separates it from the next unit. Leading white space belongs
    to the first body. Nothing is lost: the units cover the text.

    A blank line, a line that ends a sentence (or a colon), and each structure line
    end a unit. A line that merely wraps does not, so a sentence broken over two
    lines stays whole, never a dangling half."""
    line_starts = [0] + [m.end() for m in re.finditer("\n", text)]
    is_structure = [bool(_STRUCTURE.match(text, s)) for s in line_starts]
    cuts: list[tuple[int, int]] = []
    for m in _SPACE.finditer(text):
        a, b = m.span()
        if a == 0 or b == len(text):
            continue
        before = bisect_right(line_starts, a - 1) - 1
        if "\n" in m.group():
            j = _stop_before(text, a)
            ends = (m.group().count("\n") >= 2 or is_structure[before]
                    or is_structure[bisect_right(line_starts, b) - 1]
                    or (j > 0 and (text[j - 1] in _TERMINATORS or text[j - 1] in ":;")))
        else:
            ends = not is_structure[before] and _ends_sentence_inline(text, a, b)
        if ends:
            cuts.append((a, b))
    units: list[tuple[int, int, int]] = []
    start = 0
    for a, b in cuts:
        units.append((start, a, b))
        start = b
    units.append((start, max(start, len(text.rstrip())), len(text)))
    return units


def clean_sentences(text: str, known: FigureSet, *, hours: set[int] | None = None) -> tuple[str, list[str]]:
    """Bind `text`, then remove each sentence that still holds an unresolved
    number or token. Returns the cleaned text and the removed sentences (as
    bound, without their trailing space).

    A sentence ends at ".", "!" or "?" followed by space, except after "e.g.",
    "i.e.", a title such as "Dr.", an initial, or before a lowercase word; a
    decimal point is never followed by space. A blank line, a line that ends a
    sentence, and every list item, table row, heading and label line are units of
    their own, so one bad cell drops only its row and one bad label line only that
    line. Dropping a unit never removes a blank line between paragraphs, nor merges
    a paragraph into a list. Nothing is added: the kept sentences are the bound
    text's own characters."""
    r = _run(text, known, hours)
    if not r.unresolved:
        return r.text, []
    t = r.text
    units = _units(t)
    starts = [u[0] for u in units]
    bad = {bisect_right(starts, u.start) - 1 for u in r.unresolved}

    kept: list[list[str]] = []          # [body, separator]
    removed: list[str] = []
    for i, (s, body_end, e) in enumerate(units):
        body, sep = t[s:body_end], t[body_end:e]
        if i not in bad:
            kept.append([body, sep])
            continue
        removed.append(body.strip())
        if sep and "\n" not in sep:
            continue                    # more follows on this line: the space goes with it
        if kept:
            before = kept[-1][1]
            if (before and "\n" not in before) or sep.count("\n") > before.count("\n"):
                kept[-1][1] = sep       # the line ends where the dropped one did; a blank line is never lost
    joined = "".join(body + sep for body, sep in kept)
    if not joined.strip():
        return "", removed
    return joined.rstrip() + t[len(t.rstrip()):], removed
