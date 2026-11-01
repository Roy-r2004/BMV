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
                from a dollar amount. A time word right after a bare number
                ("10 days") is evidence: the figure must be in that very unit
                ("10.03 weeks" is not it), a figure with no unit never matches, and
                a filler word ("40 per week") is not agreement with a figure in
                time. Any other unit (classes, GB) needs the noun after the number,
                if there is one, to be that unit, and a figure that names the unit
                beats a unitless one. Only an unspaced hyphen or en dash, " to ", and "and"
                after "between" or "from" join two numbers into a range; a spaced
                dash, an em dash or a clause break never does. Two numbers so joined
                share a shape only when one is bare and the other carries it
                ("10-15%", "$20-30 a class"), the right end if bare has no noun,
                "of", "or", "and" or "than" after it ("4 of your instructors"), and the
                left end if bare is not the tail of a partitive and takes dollars
                only when the range is plainly of money. "10% to $22" and "$45 to 12
                instructors" are two quantities, each with its own shape; a shape
                an end carries is never overridden by the other. The numbers tokens
                become are ends of ranges too, so binding twice changes nothing.
    period      a period the sentence names around a money, percent or count
                ("a month", "per week", "weekly") must be the figure's own period if it
                has one: a weekly figure never binds to "$9,500 a month".
    value       a mention equal to the figure's value, or to the value as it displays
                (44928 shown as ~45,000), is exact; any other mention within half a
                percent is near. The tier decides first (exact beats near); the figure
                that names the unit the next word gives beats a unitless one only
                within a tier. A near mention is rewritten only to a derived or ours
                figure, and only if it is a true rounding of it: the figure rounded to
                the mention's own last significant place (45,000 for 44,928, 1,000
                for 995); against a theirs or reference figure it is unresolved,
                since we never silently correct a client's own number. After a
                comparative or a bound ("over", "under", "at least", "up to", "more
                than", "nearly", "exactly" ...) only an exact match binds: it is a
                claim about a limit, not a rounding. Figures of
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
"circa", with or without an article after it), an article, or a "~" the model wrote,
which stay exactly as written: they may be prepositions, and the sentence already
hedges.

Never rewritten: times and dates, and the kinds whose words carry the meaning,
multipliers ("3x", "twice"), ordinals ("3rd") and fractions ("half"). They stay as
written when a figure supports them (`read.supported`) and are reported unresolved
when none does. A number inside a client's quotation (between double quotes) is
checked against the figures and bound only on an exact match, never rewritten.

A token `{{F:<id>}}` is replaced by that figure's number. A currency sign before
it, or a percent sign or a unit word after it, is not doubled: the number prints
without its own symbol, and the neighbour must fit the figure (a "%" after a dollar
figure is unresolved). Where nothing next to it names the unit, the figure prints
whole ("$22", "25%", "6 weeks", "24 GB"). A noun after it names what is counted: a
unitless or percent figure stands before it ("12 members"), a figure in time, money
or another unit does not (it would say "6 members" for weeks). A token with an
unknown id, one stuck to digits or letters ("12{{F:A}}", "{{F:A}}k"), and any "{{F:"
still in the output (nested or unclosed braces) are unresolved and reported, never
left silently. "{{f:id}}" in any case is a token.

Round trip: after binding, the output is read again with the reader. Each number
must read back as the value, the sort (money, percent, bare) and the form it was
given, and no two may have fused. A replacement that would fuse with a neighbour
("{{F:A}}{{F:C}}" into "$2212", "two 200-person" into "2 200-person" read as
2,200) or change how the number reads ("USD two" into "USD 2") is taken back: a
number that equals its figure stays as written and is still named, anything else is
reported unresolved.

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
from decimal import ROUND_HALF_UP, Context, Decimal
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
_NUMBER_WORDS = frozenset(
    "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen "
    "nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million billion dozen half".split())
_NUMBER_WORD = "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True))
_TRAIL_BODY = (rf"(?:{_SP}*%|(?i:{_SP}*per{_SP}?cent|{_SP}*percentage{_SP}+points?)(?![A-Za-z])"
               rf"|{_SP}?(?:{_CODES})\.?(?![A-Za-z])|{_SP}+(?i:dollars?|euros?)(?![A-Za-z])"
               rf"|{_SP}?[$\u20ac\u00a3](?!{_SP}*(?:[\d.]|(?i:{_NUMBER_WORD})(?![A-Za-z]))))")
_TRAIL = re.compile(_TRAIL_BODY + r"\Z")
_TRAIL_HEAD = re.compile(_TRAIL_BODY)
_LEAD_BEFORE = re.compile(rf"(?:[A-Z]{{1,3}}\$|\$|\u20ac|\u00a3|(?:{_CODES})\.?){_SP}?\Z")


class _Shape(NamedTuple):
    lead: str                # the currency written before the number, "" if none
    trail: str               # the percent or currency words written after it, "" if none
    kind: str                # "percent", "money" or "bare": how the mention presents its number
    currency: str | None     # for money: the currency it names, None if it names none we know
    plain: bool = True       # False when the text holds a symbol that is neither lead nor trail


def _currency_of(lead: str, trail: str) -> str | None:
    cur = lead.strip().rstrip(".")
    if cur:
        return _SIGN_CURRENCY.get(cur) or (cur if cur in _MONEY_UNITS else None)
    word = trail.strip().rstrip(".")
    return _SIGN_CURRENCY.get(word) or _WORD_CURRENCY.get(word.lower()) or (word if word in _MONEY_UNITS else None)


def _shape(text: str) -> _Shape:
    """How the mention presents its number, read from its own text only: the
    reader's form is not trusted here, because a range end carries a shape it was
    handed by its neighbour."""
    lead = _LEAD.match(text)
    cur = lead.group("cur") or ""
    t = _TRAIL.search(text, lead.end())
    trail = t.group() if t else ""
    core = text[lead.end():len(text) - len(trail)]
    plain = not any(c in core for c in "$%\u20ac\u00a3")   # a symbol we cannot keep apart from the digits
    if "%" in trail or "per" in trail.lower():
        return _Shape(cur, trail, "percent", None, plain)
    if cur or trail:
        return _Shape(cur, trail, "money", _currency_of(cur, trail), plain)
    return _Shape(cur, trail, "bare", None, plain)


def _share_range(a: _Shape, b: _Shape, *, joiner: str, from_between: bool, noun_after: bool,
                 partitive_before: bool) -> tuple[_Shape, _Shape]:
    """Two numbers joined as a range share a shape only when one of them is bare
    and the other carries a shape ("10-15%", "$20-30 a class"). The right end, if
    bare, must have no noun of its own after it (a function word like "a" or
    "per" is fine, "of", "or", "and" and "than" are not: "4 of your
    instructors"). The left end, if bare, must not be the tail of a partitive or an
    alternative, and takes a money shape only when the range is plainly of money
    ("20-$30", "from 20 to $30"; "12 to $22" is not). Otherwise each keeps its own:
    "10% to $22" and "$45 to 12 instructors" are two quantities. A shape an end
    carries is never overridden by the other."""
    bare_a, bare_b = a.kind == "bare", b.kind == "bare"
    if bare_a == bare_b:
        return a, b
    if bare_a:
        if partitive_before or (b.kind == "money" and joiner == "to" and not from_between):
            return a, b
        return a._replace(kind=b.kind, currency=b.currency), b
    if noun_after:
        return a, b
    return a, b._replace(kind=a.kind, currency=a.currency)


# Ends of a range are numbers read as plain quantities.
_NOT_A_RANGE_END = frozenset({"time", "date", "multiplier", "ordinal", "fraction"})

# What can join two numbers into a range: an UNSPACED hyphen or en dash ("10-15%"),
# " to " ("10 to 15%"), and "and" after "between" or "from" ("between 10 and 15%").
# A spaced hyphen or en dash, an em dash, or a clause break never joins: in
# "62% - 4 of your instructors are idle" the dash only starts a new statement.
_JOIN_DASH = re.compile(r"[-\u2013]")
_JOIN_TO = re.compile(rf"{_SP}+to{_SP}+")
_JOIN_AND = re.compile(rf"{_SP}+and{_SP}+")
_FROM_BETWEEN = re.compile(rf"(?<![A-Za-z])(?:from|between){_SP}+\Z", re.I)
# a partitive or an alternative follows a bare number: "4 of your instructors", "12 or more members"
_OWN_NOUN_WORDS = frozenset({"of", "or", "and", "than"})
_BEFORE_PARTITIVE = re.compile(rf"[\d%]{_SP}*(?:of|or|and){_SP}+\Z", re.I)    # "4 of 12 to 15%", "12 or 15 to 20%"


def _joiner(text: str, a: Mention, b: Mention) -> str | None:
    """"dash", "to" or "and" when what stands between the two mentions joins them
    into a range, else None."""
    gap = text[a.end:b.start].rstrip("~\u2248")   # a "~" in front of the second number is a hedge, not a gap
    if len(gap) > 6:
        return None
    if _JOIN_DASH.fullmatch(gap):
        return "dash"
    if _JOIN_TO.fullmatch(gap):
        return "to"
    if _JOIN_AND.fullmatch(gap) and _FROM_BETWEEN.search(text[max(0, a.start - 12):a.start]):
        return "and"
    return None


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

_FUNCTION_WORDS = _FUNCTION_WORDS | _NUMBER_WORDS

_NEXT_WORD = re.compile(rf"(?:-|{_SP}+)[~\u2248]?([A-Za-z]+)")


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


def _unit_words(unit: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[A-Za-z]+", unit)}


def _unit_fits(word: str | None, unit: str) -> bool:
    """Whether the word after a bare number can be the unit of a figure in `unit`.
    A time word after the number means the figure must be in that same time unit:
    a figure with no unit or "count", or in another unit, never matches it. A
    figure in time needs its own unit word, and a filler word ("per", "a", "of")
    or none at all is not agreement. A figure with no unit of its own takes any
    other word; any other unit (classes, GB) needs a noun after the number to be
    that unit."""
    figure_time = _TIME_CANON.get(unit.lower())
    word_time = _TIME_CANON.get(word) if word else None
    if word_time:
        return figure_time == word_time
    if figure_time:
        return False
    if word is None or unit in ("", "count") or word in _FUNCTION_WORDS:
        return True
    return _stem(word) in _unit_words(unit)


def _names_unit(word: str | None, unit: str) -> bool:
    """Whether the word after a number names this very unit (not a unitless one)."""
    if word is None or unit in ("", "count") or word in _FUNCTION_WORDS:
        return False
    if word in _TIME_CANON or unit.lower() in _TIME_CANON:
        return _TIME_CANON.get(word) == _TIME_CANON.get(unit.lower())
    return _stem(word) in _unit_words(unit)


def _admissible(f: Figure, shape: _Shape, word: str | None) -> bool:
    if shape.kind == "percent":
        return f.unit == "percent"
    if shape.kind == "money":
        return shape.currency is not None and f.unit == shape.currency
    return f.unit not in _MONEY_UNITS and f.unit != "percent" and _unit_fits(word, f.unit)


_CTX = Context(prec=500)


def _rounds_to(value: Decimal, mention: Decimal) -> bool:
    """Whether `mention` is `value` rounded to the mention's own last significant
    place: 45,000 is 44,928 rounded to thousands, 1,000 is 995 rounded to the one
    digit it shows; 45,010 is not. Only such a rounding may be rewritten."""
    exponent = mention.normalize(_CTX).as_tuple().exponent
    return value.quantize(Decimal(1).scaleb(exponent), rounding=ROUND_HALF_UP, context=_CTX) == mention


_PERIOD_WORDS = {"day": "day", "daily": "day", "week": "week", "weekly": "week", "wk": "week", "month": "month",
                 "monthly": "month", "mo": "month", "year": "year", "yearly": "year", "annual": "year",
                 "annually": "year", "annum": "year", "yr": "year"}


def _figure_period(period: str | None) -> str | None:
    """The period a figure's time basis names ("operating_30_day_month" is a month)."""
    p = (period or "").lower()
    for key, name in (("month", "month"), ("week", "week"), ("year", "year"), ("annual", "year"), ("day", "day")):
        if key in p:
            return name
    return None


def _pick(m: Mention, shape: _Shape, word: str | None, known: FigureSet, exact_only: bool,
          period: str | None = None) -> Figure | None:
    """The one figure `m` names, or None when it names none or cannot choose.

    The tier decides first: a figure equal to the mention, or to what it displays,
    beats any figure that is only near. Within a tier, the figure that names the
    very unit the next word gives beats a unitless one. A near figure is taken only
    if it is derived or ours and the mention is a true rounding of it, and never for
    text that must match exactly (a quotation, "over $45,000"). A period the
    sentence names ("a month") must be the figure's, if the figure has one."""
    cands = [f for f in known.match(m.value) if _admissible(f, shape, word)
             and (period is None or _figure_period(f.period) in (None, period))]
    equal = [f for f in cands if f.value == m.value]
    shown = [f for f in cands if f.value != m.value and displayed_value(f) == m.value]
    near = [f for f in cands if f.value != m.value and displayed_value(f) != m.value]
    pool, is_near = equal or shown, not (equal or shown)
    if is_near:
        pool = near
    if not pool or (is_near and exact_only):
        return None
    named = [f for f in pool if _names_unit(word, f.unit)]
    if named:
        pool = named   # "12 weeks": the figure in weeks is more specific than a unitless 12
    if len({f.value for f in pool}) > 1:
        return None   # figures of different values: a rounding that names none of them
    if len({f.unit for f in pool}) > 1:
        return None   # the same value in two units: 12 weeks or 12 reformers?
    winner = min(pool, key=lambda f: _TRUST[f.kind])   # min keeps the first of equals
    if is_near and (winner.kind in ("theirs", "reference") or not _rounds_to(winner.value, m.value)):
        return None   # the model altered the client's own number, or changed one of ours
    return winner


# -- hedges, comparatives, periods and quotations ------------------------------------------------

# A hedge word right before a number (with an article between: "roughly a 25%"), an
# article alone, or a "~" / approximately-equal sign: the sentence already hedges, so
# the figure's own "~" would say it twice.
_HEDGE = re.compile(
    rf"(?:(?<![A-Za-z])(?:(?:about|around|roughly|approximately|nearly|circa|almost){_SP}+(?:(?:a|an|the){_SP}+)?"
    rf"|(?:a|an|the){_SP}+)|[~\u2248]{_SP}*)\Z", re.I)

# A comparative or a bound introduces the number: it is a claim about a limit, not a
# rounding, so only a figure equal to it (or to what it displays) may bind.
_COMPARATIVE = re.compile(
    rf"(?<![A-Za-z])(?:over|under|above|below|beyond|exceeds?|exceeding|nearly|almost|exactly|at{_SP}+(?:least|most)"
    rf"|up{_SP}+to|(?:no|not){_SP}+(?:more|less|fewer){_SP}+than"
    rf"|(?:more|less|fewer|greater|higher|lower|smaller|larger|bigger){_SP}+than){_SP}+\Z", re.I)

# the period a phrase names: "a month", "per week", "each year", "/day", "weekly"
_PERIOD_AFTER = re.compile(
    rf"(?:{_SP}+(?P<w>[A-Za-z]+))?(?:{_SP}*/{_SP}*|{_SP}+(?:per|a|an|each|every){_SP}+)"
    rf"(?P<u>day|week|month|year|yr|wk|mo|annum)(?![A-Za-z])|{_SP}+(?P<adv>daily|weekly|monthly|yearly|annually|annual)(?![A-Za-z])",
    re.I)
_PERIOD_BEFORE = re.compile(
    r"(?<![A-Za-z])(?P<adv>daily|weekly|monthly|yearly|annual)(?![A-Za-z])(?:[ \t,:]+\w+){0,3}[ \t,:]*\Z", re.I)


def _period_phrase(text: str, start: int, end: int) -> str | None:
    """The period the sentence names around the number at text[start:end]: the
    phrase after it ("a month", "weekly") or, failing that, an adjective just
    before it ("monthly rent of")."""
    m = _PERIOD_AFTER.match(text, end)
    if m and not (m.group("w") and m.group("w").lower() in _FUNCTION_WORDS):
        return _PERIOD_WORDS.get((m.group("u") or m.group("adv")).lower())
    sentence = re.split(r"[.!?;\n]", text[max(0, start - 60):start])[-1]
    b = _PERIOD_BEFORE.search(sentence)
    return _PERIOD_WORDS.get(b.group("adv").lower()) if b else None


def _context(text: str, start: int) -> tuple[bool, bool]:
    """(hedged, comparative) for the number starting at `start`."""
    before = text[max(0, start - 40):start]
    comparative = bool(_COMPARATIVE.search(before))
    return bool(_HEDGE.search(before)) or comparative, comparative


# a client's quotation: text between straight or curly double quotes
_QUOTE = re.compile(r'"[^"]{0,400}"|\u201c[^\u201d]{0,400}\u201d')

_TOKEN = re.compile(r"\{\{\s*F\s*:\s*([^{}]*?)\s*\}\}", re.I)
_OPENER = re.compile(r"\{\{\s*F\s*:", re.I)

# words that follow a figure without naming what it counts, besides the function words
_QUALIFIERS = frozenset(
    "more less extra total monthly weekly daily yearly annually annual overall net gross apiece only".split())


class _Decision(NamedTuple):
    leave: bool                 # supported, and kept exactly as written
    figure: Figure | None       # set with `leave` False: the span is replaced; with `leave` True: named
    text: str                   # what replaces it, when `figure` is set
    start: int | None = None    # where the replaced span starts, when it reaches left of the token
    kind: str = ""              # for a token: how its number must read back, "percent", "money" or "bare"


_LEAVE = _Decision(True, None, "")
_UNRESOLVED = _Decision(False, None, "")


def _contradicts(word: str, unit: str) -> bool:
    """A time word right after a token that is not the figure's own time unit
    ("{{F:PL-01}}-day" for a figure in weeks, "{{F:CLS}} hours" for a count): the
    token's figure is not that."""
    word_time = _TIME_CANON.get(word.lower())
    return bool(word_time) and _TIME_CANON.get(unit.lower()) != word_time


def _same_unit_word(word: str, unit_word: str) -> bool:
    a, b = _TIME_CANON.get(word.lower()), _TIME_CANON.get(unit_word.lower())
    if a or b:
        return a == b
    return _stem(word) in {_stem(w) for w in re.findall(r"[A-Za-z]+", unit_word)}


def _kind_of_unit(unit: str) -> str:
    return "percent" if unit == "percent" else "money" if unit in _MONEY_UNITS else "bare"


def _decide_token(figure_id: str, text: str, start: int, end: int, known: FigureSet, floor: int = 0) -> _Decision:
    """`floor` is where the previous mention ended: a currency code that belongs to
    that mention ("22 USD {{F:A}}") is not the lead of this token."""
    f = known.get(figure_id)
    if f is None:
        return _UNRESOLVED
    before, after_char = text[start - 1:start], text[end:end + 1]
    base = max(0, start - 8, floor)
    lead = _LEAD_BEFORE.search(text[base:start])
    if before.isdigit() or after_char.isalnum() or (before.isalpha() and not lead):
        return _UNRESOLVED   # 12{{F:A}}, {{F:A}}12, {{F:A}}k: stuck to another number or a scale
    if text[start - 2:start] == "}}" or text[end:end + 2] == "{{":
        return _UNRESOLVED   # two tokens side by side would fuse into one number
    after = _NEXT_WORD.match(text, end)
    word = after.group(1).lower() if after else None
    if word and _contradicts(word, f.unit):
        return _UNRESOLVED
    period = _period_phrase(text, start, end)
    if period and _figure_period(f.period) not in (None, period):
        return _UNRESOLVED   # a weekly figure is not "a month"
    hedged, _ = _context(text, start)
    kind = _kind_of_unit(f.unit)
    trail = _TRAIL_HEAD.match(text, end)
    if trail and ("%" in trail.group() or "per" in trail.group().lower()):
        fits = f.unit == "percent"
    elif lead or trail:
        currency = _currency_of(lead.group() if lead else "", trail.group() if trail else "")
        fits = currency is not None and f.unit == currency
        if fits and lead and not trail:
            lead_start = base + lead.start()
            if not _context(text, lead_start)[0] and display_number(f, symbols=False).startswith("~"):
                # "$ {{F:M}}" for a rounded figure: the sign and the "~" read as one, "~$45,000"
                return _Decision(False, f, display_number(f), lead_start, kind)
            hedged = _context(text, lead_start)[0]
    else:
        # nothing beside it names the unit
        number = display_number(f, tilde=not hedged)
        unit_word = display(f)[len(display_number(f)):].strip()
        if word and unit_word and _same_unit_word(word, unit_word):
            return _Decision(False, f, number, None, kind)  # the unit is already said, once
        if word and word not in _FUNCTION_WORDS and word not in _QUALIFIERS:
            # a noun follows and names what is counted: only a figure with no unit of its
            # own can stand before it; a unit or a symbol the noun would contradict cannot
            return _Decision(False, f, number, None, kind) if f.unit in ("", "count", "percent") else _UNRESOLVED
        return _Decision(False, f, number + (" " + unit_word if unit_word else ""), None, kind)
    if not fits:
        return _UNRESOLVED
    return _Decision(False, f, display_number(f, symbols=False, tilde=not hedged), None, kind)


def _decide_mention(m: Mention, shape: _Shape, word: str | None, known: FigureSet, quoted: bool,
                    hedged: bool, comparative: bool, period: str | None, hours: set[int] | None) -> _Decision:
    if m.form in _KEPT_AS_WRITTEN:
        return _LEAVE if supported(m, known, hours) else _UNRESOLVED
    if not shape.plain:
        return _UNRESOLVED
    f = _pick(m, shape, word, known, quoted or comparative, period)
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


def _form_class(form: str) -> str:
    """Digit, word, money, percent and range are the same sort of reading of a number;
    a multiplier, ordinal, fraction, time or date is not, and must stay what it was."""
    return "number" if form in ("digit", "word", "money", "percent", "range") else form


class _Expect(NamedTuple):
    start: int
    end: int
    value: Decimal      # the number the reader must find here
    item: int
    replaced: bool
    kind: str           # how it must read: "percent", "money" or "bare"
    form: str = ""      # for a mention, the reader's form class it must keep


def _assemble(text, items, ms, tokens, decisions, reverted):
    """Build the bound text from the decisions. An item in `reverted` goes back to
    what was written: a number that equals its figure stays (it is still named),
    anything else, and every token, is left unresolved."""
    pieces: list[str] = []
    length = 0                  # length of the bound text so far
    cursor = 0                  # how much of `text` has been copied or replaced
    bound: dict[str, Figure] = {}
    unresolved: list[Unresolved] = []
    spans: list[tuple[int, int, str]] = []
    expect: list[_Expect] = []
    token_spans: list[tuple[int, int]] = []
    for k, (start, end, index, is_token) in enumerate(items):
        d = decisions[k]
        m = None if is_token else ms[index]
        if k in reverted and d.figure is not None and not d.leave:
            same = m is not None and displayed_value(d.figure) == m.value
            d = _Decision(True, d.figure, "") if same else _UNRESOLVED
        if d.start is not None and d.start < cursor:
            d = _UNRESOLVED
        if d.leave:
            if d.figure is not None:
                bound.setdefault(d.figure.id, d.figure)
            if m is not None:
                at = length + (start - cursor)
                expect.append(_Expect(at, at + (end - start), m.value, k, False, _shape(m.text).kind,
                                      _form_class(m.form)))
            continue
        begin = start if d.start is None else d.start
        gap = text[cursor:begin]
        pieces.append(gap)
        at = length + len(gap)
        if d.figure is not None:
            pieces.append(d.text)
            spans.append((at, at + len(d.text), d.figure.id))
            length = at + len(d.text)
            bound.setdefault(d.figure.id, d.figure)
            value = m.value if (m is not None and d.text == m.text) else displayed_value(d.figure)
            expect.append(_Expect(at, at + len(d.text), value, k, True, d.kind if m is None else _shape(m.text).kind,
                                  "" if m is None else _form_class(m.form)))
        else:
            written = text[start:end]
            pieces.append(written)
            if is_token:
                unresolved.append(UnresolvedToken(written, at, at + len(written),
                                                  tokens[index].group(1).strip()))
                token_spans.append((at, at + len(written)))
            else:
                unresolved.append(replace(m, start=at, end=at + len(written)))
                expect.append(_Expect(at, at + len(written), m.value, k, False, _shape(m.text).kind,
                                      _form_class(m.form)))
            length = at + len(written)
        cursor = end
    pieces.append(text[cursor:])
    out = "".join(pieces)

    # a "{{F:" still in the output (nested or unclosed braces) is a token nobody resolved
    starts = [r[0] for r in token_spans]
    extra = []
    for o in _OPENER.finditer(out):
        k = bisect_right(starts, o.start()) - 1
        if k < 0 or o.start() >= token_spans[k][1]:
            extra.append(UnresolvedToken(o.group(), o.start(), o.end(), ""))
    if extra:
        unresolved = sorted(unresolved + extra, key=lambda u: u.start)
    return _Run(out, list(bound.values()), unresolved, spans), expect, token_spans


def _unstable(out: str, expect: list[_Expect], token_spans: list[tuple[int, int]]) -> set[int]:
    """The replacements to take back: those whose number the reader no longer reads as
    the figure's (two tokens fused into "$2212"; "two" made "2" before "200-person" and
    read as 2,200), and those standing next to a number another change has disturbed."""
    t_ends = [t[1] for t in token_spans]
    reread = []
    for r in mentions(out):
        i = bisect_right(t_ends, r.start)
        if i < len(token_spans) and token_spans[i][0] < r.end:
            continue
        reread.append(r)
    r_ends = [r.end for r in reread]
    hits: list[list[int]] = []
    owners: dict[int, list[int]] = {}
    for ei, e in enumerate(expect):
        found = []
        i = bisect_right(r_ends, e.start)
        while i < len(reread) and reread[i].start < e.end:
            found.append(i)
            owners.setdefault(i, []).append(ei)
            i += 1
        hits.append(found)
    def reads_as(e: _Expect, r: Mention) -> bool:
        return (r.value == e.value and (not e.kind or _shape(r.text).kind == e.kind)
                and (not e.form or _form_class(r.form) == e.form))

    failing = {ei for ei, e in enumerate(expect)
               if len(hits[ei]) != 1 or not reads_as(e, reread[hits[ei][0]]) or len(owners[hits[ei][0]]) > 1}
    # a replacement that lands inside braces which now read as a token
    known_tokens = set(token_spans)
    for t in _TOKEN.finditer(out):
        if (t.start(), t.end()) not in known_tokens:
            failing.update(ei for ei, e in enumerate(expect) if e.replaced and e.start < t.end() and e.end > t.start())
    for ri, r in enumerate(reread):     # a number the reader finds that nobody expected
        if ri not in owners:
            failing.update(ei for ei, e in enumerate(expect) if e.start <= r.end + 3 and e.end >= r.start - 3)
    bad: set[int] = set()
    for ei in failing:
        e = expect[ei]
        if e.replaced:
            bad.add(e.item)
            continue
        blamed = {o for ri in hits[ei] for o in owners.get(ri, ()) if expect[o].replaced}
        if not blamed:
            blamed = {o for o, x in enumerate(expect)
                      if x.replaced and x.start <= e.end + 2 and x.end >= e.start - 2}
        bad.update(expect[o].item for o in blamed)
    return bad


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

    # tokens first: they do not depend on ranges, and the number one becomes can be an end of one
    ms_ends = [m.end for m in ms]
    token_decisions: list[_Decision] = []
    numbers: list[Mention] = list(ms)
    for t in tokens:
        k = bisect_right(ms_ends, t.start()) - 1
        d = _decide_token(t.group(1).strip(), text, t.start(), t.end(), known, ms_ends[k] if k >= 0 else 0)
        token_decisions.append(d)
        if d.figure is not None:
            numbers.append(Mention(display_number(d.figure, tilde=False), t.start(), t.end(),
                                   displayed_value(d.figure), "digit"))
    numbers.sort(key=lambda n: (n.start, n.end))
    real = {id(m): i for i, m in enumerate(ms)}

    shapes = [_shape(m.text) for m in ms]
    range_end: dict[int, int] = {}   # for a mention in a range, where the range ends
    shape_of = [_shape(n.text) for n in numbers]
    paired = False
    for i in range(len(numbers) - 1):
        a, b = numbers[i], numbers[i + 1]
        if paired:
            paired = False
            continue
        if a.form in _NOT_A_RANGE_END or b.form in _NOT_A_RANGE_END:
            continue
        joiner = _joiner(text, a, b)
        if joiner is None:
            continue
        paired = True
        nxt = _NEXT_WORD.match(text, b.end)
        word = nxt.group(1).lower() if nxt else None
        before = text[max(0, a.start - 12):a.start]
        shape_of[i], shape_of[i + 1] = _share_range(
            shape_of[i], shape_of[i + 1], joiner=joiner,
            from_between=joiner == "and" or bool(_FROM_BETWEEN.search(before)),
            noun_after=word is not None and (word not in _FUNCTION_WORDS or word in _OWN_NOUN_WORDS),
            partitive_before=bool(_BEFORE_PARTITIVE.search(before)))
        for n in (a, b):
            if id(n) in real:
                range_end[real[id(n)]] = b.end
    for i, n in enumerate(numbers):
        if id(n) in real:
            shapes[real[id(n)]] = shape_of[i]

    quotes = [(q.start(), q.end()) for q in _QUOTE.finditer(text)]
    quote_starts = [q[0] for q in quotes]

    items: list[tuple[int, int, int, bool]] = [(t.start(), t.end(), i, True) for i, t in enumerate(tokens)]
    items += [(m.start, m.end, i, False) for i, m in enumerate(ms)]
    items.sort(key=lambda it: (it[0], it[1]))

    decisions: list[_Decision] = []
    for start, end, index, is_token in items:
        if is_token:
            decisions.append(token_decisions[index])
            continue
        m = ms[index]
        reach = range_end.get(index, m.end)
        word = period = None
        if shapes[index].kind == "bare":
            nxt = _NEXT_WORD.match(text, reach)
            word = nxt.group(1).lower() if nxt else None
        if word not in _TIME_CANON:   # a time word is the number's unit, not a period it is paid in
            period = _period_phrase(text, m.start, reach)
        q = bisect_right(quote_starts, m.start) - 1
        quoted = q >= 0 and m.end <= quotes[q][1]
        hedged, comparative = _context(text, m.start)
        decisions.append(_decide_mention(m, shapes[index], word, known, quoted, hedged, comparative, period, hours))

    reverted: set[int] = set()
    for _ in range(len(items) + 1):
        run, expect, token_spans = _assemble(text, items, ms, tokens, decisions, reverted)
        if not run.spans:
            break
        bad = _unstable(run.text, expect, token_spans) - reverted
        if not bad:
            break
        reverted |= bad
    return run


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

# Lines have a role. An ITEM starts with a bullet or a number; the lines that wrap
# it (indented, or running on without a full stop) are its CONTINUATION and belong
# to it. A SINGLE line is a heading, a quote, a table row, or a bold lead
# ("**Rent:** $999", "**Costs**"). Item, continuation and single lines are never
# split into sentences, so each item and row is one unit; a plain "Label: value" is
# ordinary prose and splits into sentences like any other.
_ITEM = re.compile(r"[ \t]*(?:[-*+\u2022\u2013][ \t]+|\d{1,3}[.)][ \t]+)")
_SINGLE = re.compile(r"[ \t]*(?:#{1,6}[ \t]+|>[ \t]|\|)")
# A bold lead is a unit of its own only when the line holds no sentence end in the
# middle; a bold-led paragraph of several sentences splits like any prose, the bold
# lead staying with the first sentence.
_BOLD = re.compile(r"[ \t]*(?:\*\*|__)[^\n]{1,80}?(?:\*\*|__)")


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


def _closes_line(text: str) -> bool:
    """Whether a line of text ends a sentence or introduces what follows."""
    t = text.rstrip()
    j = len(t)
    while j > 0 and (t[j - 1] in _CLOSERS or t[j - 1] in "*_`~"):
        j -= 1
    return j > 0 and (t[j - 1] in _TERMINATORS or t[j - 1] in ":;")


def _has_sentence_end_inside(text: str, s: int, e: int) -> bool:
    """Whether the line text[s:e] ends a sentence anywhere but at its end."""
    for m in _SPACE.finditer(text, s, e):
        if m.end() < e and _ends_sentence_inline(text, m.start(), m.end()):
            return True
    return False


def _roles(text: str, starts: list[int]) -> list[str]:
    """The role of each line: blank, item, cont, single or prose."""
    roles: list[str] = []
    last = "blank"          # role of the last line that was not blank
    last_text = ""
    gap = 0                 # blank lines since it
    for i, s in enumerate(starts):
        e = starts[i + 1] - 1 if i + 1 < len(starts) else len(text)
        line = text[s:e]
        indented = line[:1] in (" ", "\t")
        if not line.strip():
            roles.append("blank")
            gap += 1
            continue
        if _ITEM.match(line):
            role = "item"
        elif _SINGLE.match(line) or (_BOLD.match(line) and not _has_sentence_end_inside(text, s, e)):
            role = "single"
        elif last in ("item", "cont") and gap == 0 and (indented or not _closes_line(last_text)):
            role = "cont"       # wraps the item above
        elif last in ("item", "cont") and gap > 0 and len(line) - len(line.lstrip(" \t")) >= 2:
            role = "cont"       # a further paragraph of the item above, indented under it
        else:
            role = "prose"
        roles.append(role)
        last, last_text, gap = role, line, 0
    return roles


def _units(text: str) -> list[tuple[int, int, int]]:
    """Split into sentence-like units as (start, body end, end): the body, then the
    white space (line breaks and the next line's indent) that separates it from the
    next unit. Leading white space belongs to the first body. Nothing is lost: the
    units cover the text.

    Prose splits at a sentence end, at a blank line, after a line that ends a
    sentence or a colon, and where an unfinished line is followed by a line that
    starts with a capital (a heading or label, not a wrapped sentence). A line that
    merely wraps does not split, so a sentence broken over two lines stays whole.
    Every list item, with its continuation lines, every table row, heading and bold
    lead is one unit."""
    starts = [0] + [m.end() for m in re.finditer("\n", text)]
    roles = _roles(text, starts)
    cuts: list[tuple[int, int]] = []
    for m in _SPACE.finditer(text):
        a, b = m.span()
        if a == 0 or b == len(text):
            continue
        la, lb = bisect_right(starts, a - 1) - 1, bisect_right(starts, b) - 1
        if "\n" not in m.group():
            ends = roles[la] == "prose" and _ends_sentence_inline(text, a, b)
        elif roles[lb] == "cont":
            ends = False
        elif roles[la] != "prose" or roles[lb] != "prose":
            ends = True
        else:
            ends = (m.group().count("\n") >= 2 or _closes_line(text[starts[la]:a]) or text[b].isupper())
        if ends:
            cuts.append((a, b))
    units: list[tuple[int, int, int]] = []
    start = 0
    for a, b in cuts:
        units.append((start, a, b))
        start = b
    units.append((start, max(start, len(text.rstrip())), len(text)))
    return units


def _rejoin(before: str, after: str) -> str:
    """The separator between two kept units once the unit between them is dropped:
    `before` is what stood in front of the dropped unit, `after` what followed it
    (and holds the indent of the unit that now comes next). The line breaks are the
    longer of the two, so a blank line is never lost and a paragraph never runs into
    a list; the indent is the next unit's own, never the dropped unit's. If that
    would put a blank line and then a line indented four columns or more (a code
    block in markdown) where the text had none, the indent goes."""
    if "\n" not in before or not after:
        return after
    nl_b, nl_a = before.count("\n"), after.count("\n")
    run_b, run_a = before[:before.rfind("\n") + 1], after[:after.rfind("\n") + 1]
    indent = after[after.rfind("\n") + 1:]
    run = run_a if nl_a >= nl_b else run_b
    columns = len(indent.replace("\t", "    "))
    if columns >= 4 and run.count("\n") >= 2 and nl_a < 2:
        indent = ""
    return run + indent


def clean_sentences(text: str, known: FigureSet, *, hours: set[int] | None = None) -> tuple[str, list[str]]:
    """Bind `text`, then remove each sentence that still holds an unresolved
    number or token. Returns the cleaned text and the removed sentences (as
    bound, without their trailing space).

    A sentence ends at ".", "!" or "?" followed by space, except after "e.g.",
    "i.e.", a title such as "Dr.", an initial, or before a lowercase word; a
    decimal point is never followed by space. A blank line, a line that ends a
    sentence, and every list item (with the lines that wrap it), table row, heading
    and bold label line are units of their own, so one bad cell drops only its row,
    one bad child item only itself, and a bad number in a wrapped item takes the
    whole item and never leaves its continuation behind. A plain "Why it matters:
    rent is $22." is prose and splits into sentences. Dropping a unit never removes
    a blank line between paragraphs, nor merges a paragraph into a list; the next
    kept line keeps its own indent, and a drop never leaves a line indented four
    columns after a blank line that was not so before. Nothing is added: the kept
    sentences are the bound text's own characters."""
    r = _run(text, known, hours)
    if not r.unresolved:
        return r.text, []
    t = r.text
    units = _units(t)
    starts = [u[0] for u in units]
    bad = {bisect_right(starts, u.start) - 1 for u in r.unresolved}

    kept: list[list[str]] = []          # [body, separator]
    removed: list[str] = []
    lead = ""                           # the indent of the first kept line, when the text starts with a drop
    first_columns = len(t[:len(t) - len(t.lstrip(" \t"))].replace("\t", "    "))
    for i, (s, body_end, e) in enumerate(units):
        body, sep = t[s:body_end], t[body_end:e]
        if i not in bad:
            kept.append([body, sep])
            continue
        removed.append(body.strip())
        if sep and "\n" not in sep:
            if not kept:
                lead = lead or body[:len(body) - len(body.lstrip())]
            continue                    # more follows on this line: the space goes with it
        if kept:
            kept[-1][1] = _rejoin(kept[-1][1], sep)
        else:
            lead = sep[sep.rfind("\n") + 1:] if "\n" in sep else ""
            if len(lead.replace("\t", "    ")) >= 4 and first_columns < 4:
                lead = ""               # the text did not start with a code block; a drop must not make one
    joined = lead + "".join(body + sep for body, sep in kept)
    if not joined.strip():
        return "", removed
    return joined.rstrip() + t[len(t.rstrip()):], removed
