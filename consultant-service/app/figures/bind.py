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
                time. The noun after a count must be the figure's own unit
                (plural or singular; "more", "extra", "new" and the like are skipped):
                "Hire 4 more instructors" is not 4 reformers, "Add 3 classes" is not
                3 intro classes. A figure with no noun takes a number only when no
                noun follows it, and a figure that names the unit beats a unitless
                one. Only an unspaced hyphen or en dash, " to ", and "and"
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
    period      a figure that has a period binds only when EVERY rate or period phrase
                in its clause (a sentence, a bullet, a table row, before or after the
                number) names that period: "a week", "per week", "each", "every", "this",
                "last", "the", "in a typical" + a time noun (second to decade, fortnight,
                quarter, term, season), a time adverb ("hourly", "biweekly", "monthly"),
                "per <anything>" (a rate: "per class", "per diem"), "every other week",
                "MTD", "to date", "over 5 years", "over the lease", and a table cell that
                is a time word. Any other phrase blocks, so a weekly figure is never "$9,500
                a month", "$1,950 per session", "this month" or "MTD". No phrase, or a
                figure with no period, does not block.
    value       a mention equal to the figure's value is exact; one equal to the value as
                it displays (44928 shown as ~45,000) or within half a percent of it is a
                rounding. The tier decides first (exact beats a rounding); the figure that
                names the unit the next word gives beats a unitless one only within a
                tier. A rounding binds only a derived or ours figure, only when the number
                stands directly after an approximation cue ("~", the approximately-equal
                sign, about, around, roughly, approximately, approx., circa, c., an
                estimated, some) and nothing else qualifies it (no comparison sign, no
                limit word earlier in the clause, no exactness word), and, when it is not
                the display itself, only if it is a true rounding of the figure to its own
                last significant place (45,000 for 44,928, 1,000 for 995). Without a cue
                "$45,000" for a figure shown as ~$45,000 is unresolved: the model should
                use the token. The exact value of a figure we show rounded, and a true
                rounding of it, stay as the model wrote them (the display could only say
                less); a figure shown exactly is printed as its value. Against a theirs
                or reference figure a rounding is never accepted: we never silently correct
                a client's own number. Figures of different values at the same distance
                make the mention ambiguous, so "about $4,700" between 4,720 and 4,680
                names neither.
    limits      after a comparative, a bound or an exactness word ("over", "under", "at
                least", "up to", "more than", "within", "max", "cap", "ceiling", "tops",
                "passes", "past", "south of", "exactly", "precisely", "an exact", "to the
                dollar" ..., also after the number: "or more", "+", "-plus", "max"), even
                with a hedge word or a "~" between, and after a comparison sign (">",
                "<", the unicode forms), the number binds only when it equals the
                figure's own value, not its rounded display, and is never rewritten:
                "over $45,000" is not certified by 44,928 shown as ~$45,000. A token
                after a limit, or in a clause with a limit word before it, is
                unresolved when its figure is shown rounded.
    unitless    a figure with no unit binds only a mention of exactly its value that has
                no noun after it (also through "of": "3 of 12 reformers" counts reformers
                for both numbers), no rate or period phrase in its clause, and that
                stands where a quantity stands: not a list marker ("**4.** Review"), not
                a table cell ("| 4 |"), not after a verb or a name ("Dial 4", "Room 4"),
                and not a part of a ratio ("1:10", "4/12": no figure names those).
    equal       figures of one value that print the same way are one answer whatever
                their units or kinds: the figure that names the noun, then the most
                trusted kind (theirs, derived, reference, ours), then the lowest id.
                One value printed two ways (12 and 12.0, "~12" and "12") is a choice.

An unresolved mention is left as written and reported.

Only the number is replaced, never what the sentence says around it. "twelve
classes" becomes "12 classes". The currency sign, percent sign, and the words
percent, USD or dollars that the model put on its number are kept; a symbol it did
not write is not added; a magnitude it wrote ("10k", "1.5 million") is spelled out
as the figure's digits. A figure that rounding changed gets a "~" in front, except
after an approximation cue (with or without an article after it), an article, or a
"~" the model wrote, which stay exactly as written: they may be prepositions, and
the sentence already hedges.

Not prose: URLs, markdown link targets and titles, image paths, inline code, fenced
blocks and path-like tokens (".../guides/22") are blanked before the reader sees
them and come back byte for byte; the text of a link is still read.

Never rewritten: times and dates, and the kinds whose words carry the meaning,
multipliers ("3x", "twice"), ordinals ("3rd") and fractions ("half"). They stay as
written when a figure supports them (`read.supported`) and are reported unresolved
when none does. A number inside a client's quotation (between double quotes) is
checked against the figures and bound only on an exact match, never rewritten.

A token `{{F:<id>}}` is replaced by that figure's number. A currency sign before
it, or a percent sign or a unit word after it, is not doubled: the number prints
without its own symbol, and the neighbour must fit the figure (a "%" after a dollar
figure is unresolved). Where nothing next to it names the unit, the figure prints
whole ("$22", "25%", "6 weeks", "24 GB"). A noun after it names what is counted: it
must be the figure's own unit ("12 members" for a figure in members) or the figure a
percent; a figure with no unit, in time, in money or in another unit would be made to
say what the noun does not ("6 members" for weeks). A token with an
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
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Context, Decimal
from functools import lru_cache
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


@lru_cache(maxsize=8192)
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

_FUNCTION_WORDS = _FUNCTION_WORDS | _NUMBER_WORDS | frozenset(
    "against between among across towards toward through throughout during until till since before after behind "
    "beside besides via plus minus versus vs like unlike near".split())

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


# Words that end the noun phrase after a number, besides the function words: adverbs and
# the period adjectives. "more", "extra", "new", "additional", "total" and the like do not
# end it; they are skipped, and the noun is what comes after them.
_ADVERBS = frozenset(
    "here there now today tomorrow yesterday again already too also just still even ever never always often soon "
    "later early late away ahead back together apart instead anyway really very quite rather mostly mainly simply "
    "currently recently actually usually normally typically daily weekly monthly yearly annually annual overall "
    "net gross apiece only".split())
_PHRASE_STOP = _FUNCTION_WORDS | _ADVERBS
_SKIP_WORDS = frozenset("more extra new additional total other further another fewer less".split())
# A "noun" that only stands for one said elsewhere ("two others nearby"): a figure in it takes
# whatever noun the number is given, and gives no evidence of its own.
_PROFORMS = frozenset("others other ones one some many few rest those these them".split())


# "3 of 12 reformers", "4 of your 12 reformers", "2 of your staff": the noun after "of" is the
# one both numbers count
_OF_TAIL = re.compile(
    rf"{_SP}+of(?:{_SP}+(?:the|your|our|their|these|those|my|his|her|its)(?![A-Za-z]))?"
    rf"(?:{_SP}+(?:\d[\d,]*(?:\.\d+)?|{_NUMBER_WORD})(?![A-Za-z\d]))?", re.I)


def _phrase_after(view: str, pos: int) -> tuple[str, ...]:
    """The words that name what the number at `pos` counts: up to four words after it,
    skipping "more", "extra" and the like, stopping at a function word, an adverb,
    punctuation or a number. "180 empty seats a week" gives ("empty", "seats"). After
    "of" the noun is the one the partitive counts: "3 of your 12 reformers" gives
    ("reformers",) for the 3 as for the 12."""
    words: list[str] = []
    tail = _OF_TAIL.match(view, pos)
    m = _NEXT_WORD.match(view, tail.end() if tail else pos)
    while m and len(words) < 4:
        w = m.group(1).lower()
        if w in _PHRASE_STOP:
            break
        if w not in _SKIP_WORDS:
            if words and w in _TIME_CANON:
                break
            words.append(w)
        m = _NEXT_WORD.match(view, m.end())
    return tuple(words)


def _unit_fits(phrase: tuple[str, ...], unit: str) -> bool:
    """Whether the words after a bare number can name what a figure in `unit` counts.
    A time word after the number means the figure must be in that same time unit: a
    figure with no unit or "count", or in another unit, never matches it, and a figure
    in time needs its own time word (a filler like "per" or "a", or nothing, is not
    agreement). A figure with no unit of its own takes the number only when no noun
    follows it. A figure in a noun unit (reformers, classes, intro classes, GB) takes it
    when no noun follows, or when the noun phrase holds all of the unit's words:
    "Hire 4 more instructors" is not 4 reformers, "Add 3 classes" is not 3 intro classes."""
    word = phrase[0] if phrase else None
    figure_time = _TIME_CANON.get(unit.lower())
    word_time = _TIME_CANON.get(word) if word else None
    if word_time:
        return figure_time == word_time
    if figure_time:
        return False
    if unit in ("", "count"):
        return not phrase
    if not phrase or unit in _PROFORMS:
        return True
    return _unit_words(unit) <= {_stem(w) for w in phrase}


def _names_unit(phrase: tuple[str, ...], unit: str) -> bool:
    """Whether the words after a number name this very unit (not a unitless one)."""
    if not phrase or unit in ("", "count") or unit in _PROFORMS:
        return False
    word = phrase[0]
    if _TIME_CANON.get(word) or _TIME_CANON.get(unit.lower()):
        return _TIME_CANON.get(word) == _TIME_CANON.get(unit.lower())
    return _unit_words(unit) <= {_stem(w) for w in phrase}


def _admissible(f: Figure, shape: _Shape, phrase: tuple[str, ...]) -> bool:
    if shape.kind == "percent":
        return f.unit == "percent"
    if shape.kind == "money":
        return shape.currency is not None and f.unit == shape.currency
    return f.unit not in _MONEY_UNITS and f.unit != "percent" and _unit_fits(phrase, f.unit)


_CTX = Context(prec=500)


def _rounds_to(value: Decimal, mention: Decimal) -> bool:
    """Whether `mention` is `value` rounded to the mention's own last significant
    place: 45,000 is 44,928 rounded to thousands, 1,000 is 995 rounded to the one
    digit it shows; 45,010 is not. Only such a rounding may be rewritten."""
    exponent = mention.normalize(_CTX).as_tuple().exponent
    return value.quantize(Decimal(1).scaleb(exponent), rounding=ROUND_HALF_UP, context=_CTX) == mention


def _figure_period(period: str | None) -> str | None:
    """The period a figure's time basis names ("operating_30_day_month" is a month)."""
    p = (period or "").lower()
    for key, name in (("month", "month"), ("week", "week"), ("year", "year"), ("annual", "year"), ("day", "day")):
        if key in p:
            return name
    return None


def _period_ok(period: str | None, keys: frozenset[str] | set[str]) -> bool:
    """Whether a figure's period fits what its clause says. Every rate or period phrase the
    clause holds ("a week", "per class", "last month", "MTD") must name the figure's own
    period; any other blocks ("$1,950 a month" is not a weekly figure, nor is "$1,950 per
    session"). A figure with no period, or a clause with no such phrase, does not block."""
    fp = _figure_period(period)
    return fp is None or all(k == fp for k in keys)


def _pick(m: Mention, shape: _Shape, phrase: tuple[str, ...], found: list[Figure], exact_only: bool,
          strict: bool = False, approximate: bool = False, keys: frozenset[str] | set[str] = frozenset(),
          bare_ok: bool = True) -> Figure | None:
    """The one figure `m` names among `found` (the figures near its value), or None
    when it names none or cannot choose.

    The tier decides first: a figure equal to the mention beats one that only displays as
    it, which beats one that is only near. A figure the mention does not equal exactly (a
    rounded one, or a near one) is taken only if it is derived or ours, the number stands
    after an approximation cue ("about", "~") and nothing else qualifies it (`approximate`),
    and, for a near figure, the mention is a true rounding of it. `exact_only` (a
    quotation) takes no near figure; `strict` (a limit: "over $45,000") takes only a figure
    whose own value equals the mention's. Within a tier, the figure that names the very unit
    the next words give beats a unitless one; figures of one value that print alike are not
    ambiguous, only unequal ones are. A figure with no unit takes only an exact mention that
    stands where a quantity stands (`bare_ok`). Every rate or period phrase in the clause
    must be the figure's own period."""
    cands = [f for f in found if _admissible(f, shape, phrase) and _period_ok(f.period, keys)
             and (f.unit not in ("", "count") or (bare_ok and f.value == m.value))]
    equal = [f for f in cands if f.value == m.value]
    if strict:
        pool, tier = equal, "equal"
    elif equal:
        pool, tier = equal, "equal"
    else:
        shown = [f for f in cands if displayed_value(f) == m.value]
        near = [f for f in cands if displayed_value(f) != m.value]
        pool, tier = (shown, "shown") if shown else (near, "near")
    if not pool or (tier == "near" and exact_only):
        return None
    if tier != "equal" and not (approximate or exact_only):
        return None   # a number that is not the figure's own needs a cue that it is a rounding
    named = [f for f in pool if _names_unit(phrase, f.unit)]
    if named:
        pool = named   # "12 weeks": the figure in weeks is more specific than a unitless 12
    if len({f.value for f in pool}) > 1:
        return None   # figures of different values: a rounding that names none of them
    if len({display_number(f, symbols=False) for f in pool}) > 1:
        return None   # one value printed two ways (12 and 12.00, "~12" and "12"): a choice the page would show
    # Figures of one value that print the same are one answer whatever their units or kinds:
    # the most trusted kind, then the first id. (Unit specificity already narrowed the pool.)
    winner = min(pool, key=lambda f: (_TRUST[f.kind], f.id))
    if tier == "near" and (winner.kind in ("theirs", "reference") or not _rounds_to(winner.value, m.value)):
        return None   # the model altered the client's own number, or changed one of ours
    if tier != "equal" and winner.kind in ("theirs", "reference"):
        return None
    return winner


# -- hedges, limits, periods, non-prose and quotations ----------------------------------------------

# An approximation cue right before the number: "~", the approximately-equal sign, "about",
# "around", "roughly", "approximately", "approx.", "circa", "c.", "an estimated", "some".
# A rounded figure may be written as a rounding only after one. "just under" and "nearly" are
# limits, not cues.
_CUE_WORDS = frozenset("about around roughly approximately approx circa c estimated some".split())
_CUE = (rf"(?:(?<![A-Za-z])(?:about|around|roughly|approximately|approx\.?|circa|c\.|an{_SP}+estimated|estimated|some)"
        rf"{_SP}+(?:(?:a|an|the){_SP}+)?|[~\u2248]{_SP}*)")
_APPROX_CUE = re.compile(_CUE + r"\Z", re.I)
# What stops the figure's own "~" being printed: the sentence already hedges. That is a cue,
# an article alone, or a limit ("over"): a limit is never rewritten, so nothing is printed.
_HEDGE = re.compile(rf"(?:{_CUE}|(?<![A-Za-z])(?:a|an|the){_SP}+)\Z", re.I)

# A comparative, a limit or an exactness word introduces the number ("over $45,000",
# "within $7,500", "a cap of 12", "under about $7,500", "no less than ~$102,000", "precisely
# $19,950") or follows it ("$7,500 max", "12+", "$45,000-plus", "40 or more", "$1,953.60
# exactly"). It is a claim about a bound, not a rounding: it certifies only a figure whose own
# value equals the number, and the number is never rewritten.
_LIMIT_WORDS = (
    rf"over|under|above|below|beyond|past|passes|passing|surpass(?:es|ing)?|tops?|exceeds?|exceeding|nearly|almost"
    rf"|exactly|precisely|precise|exact|within|in{_SP}+excess{_SP}+of"
    rf"|at{_SP}+(?:the{_SP}+)?(?:very{_SP}+)?(?:least|most)|at{_SP}+(?:worst|best)|at{_SP}+a{_SP}+(?:maximum|minimum)"
    rf"|up{_SP}+to|upwards?{_SP}+of|(?:north|south){_SP}+of"
    rf"|(?:no|not){_SP}+(?:more|less|fewer){_SP}+than"
    rf"|(?:more|less|fewer|greater|higher|lower|smaller|larger|bigger){_SP}+than(?:{_SP}+or{_SP}+equal{_SP}+to)?"
    rf"|(?:maximum|minimum|max|min)(?:{_SP}+of)?|cap(?:ped)?(?:{_SP}+(?:at|of))?"
    rf"|(?:limit|ceiling|floor)(?:ed)?(?:{_SP}+(?:to|of|at))?|top(?:{_SP}+of)?")
_COMPARATIVE = re.compile(
    rf"(?<![A-Za-z])(?:{_LIMIT_WORDS})(?![A-Za-z]),?{_SP}+"
    rf"(?:(?:about|around|roughly|approximately|approx\.?|circa|some|nearly|almost){_SP}+)?(?:(?:a|an|the){_SP}+)?"
    rf"(?:[~\u2248]{_SP}*)?\Z", re.I)
# a comparison sign right before the number ("> $45,000", "<=$45,000"; not the arrow in "->")
_SYMBOL_BEFORE = re.compile(
    rf"(?:(?<![-=<>])[<>]=?|[\u2264\u2265]){_SP}*"
    rf"(?:(?:about|around|roughly|approximately|approx\.?|circa|c\.|some|an{_SP}+estimated|estimated){_SP}+)?"
    rf"(?:[~\u2248]{_SP}*)?\Z", re.I)
_COMPARATIVE_AFTER = re.compile(
    rf"{_SP}*(?:\+(?!\d)|-?plus(?![A-Za-z])|(?:or|and){_SP}+(?:more|less|fewer|higher|lower|greater|smaller|up|above"
    rf"|below|over|under)(?![A-Za-z])|(?:max|min|maximum|minimum|tops|exactly|precisely)(?![A-Za-z])"
    rf"|at{_SP}+(?:most|least)(?![A-Za-z])|to{_SP}+the{_SP}+(?:dollar|cent|penny)(?![A-Za-z]))", re.I)
# a limit word anywhere in the text: with a rounded figure, one anywhere earlier in the clause
# takes away the cue ("Cap spend at about $7,500")
_LIMIT_ANYWHERE = re.compile(rf"(?<![A-Za-z])(?:{_LIMIT_WORDS})(?![A-Za-z])", re.I)

# Rate and period phrases. A figure with a period is held to every one in its clause.
_TIME_NOUN = (r"(?:second|minute|hour|day|week|fortnight|month|quarter|term|semester|season|year|decade"
              r"|wk|yr|mo|annum)s?")
_TIME_ADV = (r"(?:hourly|nightly|daily|weekly|fortnightly|biweekly|semiweekly|monthly|bimonthly|semimonthly"
             r"|quarterly|semiannually|annually|yearly|biannually|biennially|annual)")
_COUNT_WORD = r"(?:\d[\d,.]*|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|several|many|few|multiple)"
_PHRASE = re.compile(
    rf"(?<![A-Za-z])(?P<other>(?:every|each){_SP}+other{_SP}+{_TIME_NOUN})(?![A-Za-z])"
    rf"|(?<![A-Za-z])(?:per|a|an|each|every|in{_SP}+a{_SP}+typical|in{_SP}+an{_SP}+average|for{_SP}+the|this|last"
    rf"|next|the|past|previous|current){_SP}+(?P<n1>{_TIME_NOUN})(?![A-Za-z])"
    rf"|(?<=[\d%]){_SP}*/{_SP}*(?P<n2>{_TIME_NOUN})(?![A-Za-z])"
    rf"|(?<![A-Za-z])(?P<adv>{_TIME_ADV})(?![A-Za-z])"
    rf"|(?<![A-Za-z])per{_SP}+(?P<rate>[A-Za-z]+)"
    rf"|(?<=[\d%]){_SP}*/{_SP}*(?P<rate2>[A-Za-z]+)"
    rf"|(?<![A-Za-z])(?P<ytd>[MYQ]TD)(?![A-Za-z])|(?<![A-Za-z])(?P<todate>to{_SP}+date)(?![A-Za-z])"
    rf"|(?<![A-Za-z])(?P<overn>over{_SP}+(?:the{_SP}+)?(?:next{_SP}+|last{_SP}+|past{_SP}+)?{_COUNT_WORD}"
    rf"{_SP}+(?:[A-Za-z-]+{_SP}+)?{_TIME_NOUN})(?![A-Za-z])"
    rf"|(?<![A-Za-z])(?P<overthe>over{_SP}+the{_SP}+(?:lease|term|season|life|course|contract|period))(?![A-Za-z])",
    re.I)
_CELL = re.compile(rf"\s*(?:{_TIME_NOUN}|{_TIME_ADV})\s*", re.I)
_CANON_NOUN = {"wk": "week", "yr": "year", "mo": "month", "annum": "year"}
_CANON_ADV = {"daily": "day", "weekly": "week", "monthly": "month", "yearly": "year", "annually": "year",
              "annual": "year"}
_CLAUSE_BREAK = re.compile(r"[.!?;](?=\s|$)|\n")


_TIME_BASES = frozenset("second minute hour day week fortnight month quarter term semester season year decade wk yr mo".split())


def _noun_key(noun: str) -> str:
    n = noun.lower()
    if n.endswith("s") and n[:-1] in _TIME_BASES:
        n = n[:-1]
    return _CANON_NOUN.get(n, n)


class _Clauses:
    """Where the clauses of a text are (a clause is a sentence, a bullet or a table row), every
    rate and period phrase in it, and the limit words."""

    def __init__(self, text: str) -> None:
        breaks = list(_CLAUSE_BREAK.finditer(text))
        self.text = text
        self._starts = [b.start() for b in breaks]
        self._ends = [b.end() for b in breaks]
        self._limits = [m.start() for m in _LIMIT_ANYWHERE.finditer(text)]
        found: list[tuple[int, int, str]] = []
        for m in _PHRASE.finditer(text):
            if m.group("n1") or m.group("n2"):
                key = _noun_key(m.group("n1") or m.group("n2"))
            elif m.group("adv"):
                adv = m.group("adv").lower()
                key = _CANON_ADV.get(adv, adv)
            else:
                key = "*"        # a rate or a span that names none of day, week, month, year as one period
            found.append((m.start(), m.end(), key))
        if "|" in text:          # a table cell that is a time word names a period too
            pos = 0
            for line in text.split("\n"):
                if "|" in line:
                    at = 0
                    for cell in line.split("|"):
                        c = _CELL.fullmatch(cell)
                        if c:
                            w = c.group().strip().lower()
                            found.append((pos + at + c.start(), pos + at + c.end(),
                                          _CANON_ADV.get(w) or _noun_key(w)))
                        at += len(cell) + 1
                pos += len(line) + 1
        found.sort()
        self._phrases = found
        self._phrase_starts = [f[0] for f in found]

    def bounds(self, start: int, end: int) -> tuple[int, int]:
        i = bisect_right(self._ends, start)
        j = bisect_left(self._starts, end)
        return (self._ends[i - 1] if i else 0), (self._starts[j] if j < len(self._starts) else len(self.text))

    def nearest(self, start: int, end: int, next_number: int) -> frozenset[str]:
        """What the rate or period phrase next to the number at text[start:end] names: the
        nearest one after it, before the next number or the end of the clause; failing that the
        nearest one before it in the clause. Only that phrase can contradict the number; the
        others in the clause belong to other numbers. "*" for a phrase that names none of day,
        week, month or year as one period ("per class", "MTD", "over 5 years")."""
        left, right = self.bounds(start, end)
        i = bisect_left(self._phrase_starts, end)
        if i < len(self._phrases) and self._phrases[i][0] < min(next_number, right):
            return frozenset({self._phrases[i][2]})
        j = bisect_left(self._phrase_starts, start) - 1
        while j >= 0 and self._phrases[j][0] >= left:
            if self._phrases[j][1] <= start:
                return frozenset({self._phrases[j][2]})
            j -= 1
        return frozenset()

    def limit_before(self, start: int) -> bool:
        """Whether a limit word stands earlier in the same clause."""
        left, _ = self.bounds(start, start)
        i = bisect_left(self._limits, start) - 1
        return i >= 0 and self._limits[i] >= left


def _context(text: str, start: int, end: int) -> tuple[bool, bool]:
    """(hedged, limited) for the number at text[start:end]: hedged when a cue, an article or a
    "~" stands right before it or a limit qualifies it; limited when a limit, a comparison sign
    or an exactness word introduces or follows it."""
    before = text[max(0, start - 40):start]
    limited = bool(_COMPARATIVE.search(before) or _SYMBOL_BEFORE.search(before) or _COMPARATIVE_AFTER.match(text, end))
    return bool(_HEDGE.search(before)) or limited, limited


# -- what is not prose: links, code and paths are neither read nor touched ---------------------

_FENCE = re.compile(r"(```|~~~).*?(?:\1|\Z)", re.S)
_INLINE_CODE = re.compile(r"(`{1,2})(?!`)[^`\n]{1,200}?\1(?!`)")
_MD_TARGET = re.compile(r"\]\(([^()\s]{1,300}(?:[ \t]+\"[^\"\n]{0,200}\")?)\)")   # the target and its title
_URL = re.compile(r"(?i)(?<![A-Za-z0-9])(?:https?://|www\.)[^\s<>\"']+")
_PATH_CHARS = re.compile(r"[A-Za-z0-9_.~%@:+\-/]+")
_DOMAIN_PATH = re.compile(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+/\S*")
_DATE_LIKE = re.compile(r"[\d/.\-]+")


def _mask(text: str) -> str:
    """`text` with every link target, URL, code span, fenced block and path-like token
    blanked to spaces (line breaks kept), same length, so the reader never sees a number
    in them and the positions still match the text."""
    spans: list[tuple[int, int]] = []
    for pattern in (_FENCE, _INLINE_CODE):
        spans.extend(m.span() for m in pattern.finditer(text))
    spans.extend(m.span(1) for m in _MD_TARGET.finditer(text))
    for m in _URL.finditer(text):
        url = m.group()
        while url and (url[-1] in ".,;:!?'\"]}" or (url[-1] == ")" and url.count(")") > url.count("("))):
            url = url[:-1]
        spans.append((m.start(), m.start() + len(url)))
    reach = 0                         # the word around each slash, found from the slash so a long run stays linear
    i = text.find("/")
    while i != -1:
        if i >= reach:
            a = i
            while a > 0 and not text[a - 1].isspace():
                a -= 1
            b = i
            while b < len(text) and not text[b].isspace():
                b += 1
            reach = b
            raw = text[a:b]
            lead = len(raw) - len(raw.lstrip("([{<\"'"))
            core = raw[lead:].rstrip(")]}>\"'.,;:!?")
            if core and not _DATE_LIKE.fullmatch(core):     # 5/22, 24/7, 1/2: the reader's business
                if (core.count("/") >= 2 and _PATH_CHARS.fullmatch(core)) or _DOMAIN_PATH.fullmatch(core):
                    spans.append((a + lead, a + lead + len(core)))
        i = text.find("/", max(i + 1, reach))
    if not spans:
        return text
    spans.sort()
    out: list[str] = []
    pos = 0
    for a, b in spans:
        if b <= pos:
            continue
        a = max(a, pos)
        out.append(text[pos:a])
        out.append(re.sub(r"[^\n]", " ", text[a:b]))
        pos = b
    out.append(text[pos:])
    return "".join(out)


# a client's quotation: text between straight or curly double quotes
_QUOTE = re.compile(r'"[^"]{0,400}"|\u201c[^\u201d]{0,400}\u201d')

_TOKEN = re.compile(r"\{\{\s*F\s*:\s*([^{}]*?)\s*\}\}", re.I)
_OPENER = re.compile(r"\{\{\s*F\s*:", re.I)

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


def _kind_of_unit(unit: str) -> str:
    return "percent" if unit == "percent" else "money" if unit in _MONEY_UNITS else "bare"


def _decide_token(figure_id: str, text: str, start: int, end: int, known: FigureSet, floor: int = 0,
                  keys: frozenset[str] | set[str] = frozenset(), quantity: bool = True,
                  limit_before: bool = False) -> _Decision:
    """`floor` is where the previous mention ended: a currency code that belongs to
    that mention ("22 USD {{F:A}}") is not the lead of this token. `keys` holds what
    the rate and period phrases of the clause name."""
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
    if not _period_ok(f.period, keys):
        return _UNRESOLVED   # a weekly figure is not "a month", nor "$1,950 per session"
    if f.unit in ("", "count") and not quantity:
        return _UNRESOLVED   # a figure with no unit is not put where a number is a label, a cell or a name
    hedged, limited = _context(text, start, end)
    if (limited or limit_before) and display_number(f, symbols=False).startswith("~"):
        return _UNRESOLVED   # "over {{F:M}}", "Cap spend at {{F:M}}" for a rounded figure would certify a bound it cannot
    kind = _kind_of_unit(f.unit)
    trail = _TRAIL_HEAD.match(text, end)
    if trail and ("%" in trail.group() or "per" in trail.group().lower()):
        fits = f.unit == "percent"
    elif lead or trail:
        currency = _currency_of(lead.group() if lead else "", trail.group() if trail else "")
        fits = currency is not None and f.unit == currency
        if fits and lead and not trail:
            lead_start = base + lead.start()
            if not _context(text, lead_start, end)[0] and display_number(f, symbols=False).startswith("~"):
                # "$ {{F:M}}" for a rounded figure: the sign and the "~" read as one, "~$45,000"
                return _Decision(False, f, display_number(f), lead_start, kind)
            hedged = _context(text, lead_start, end)[0]
    else:
        # nothing beside it names the unit
        number = display_number(f, tilde=not hedged)
        unit_word = display(f)[len(display_number(f)):].strip()
        phrase = _phrase_after(text, end)
        if phrase:
            # a noun follows and names what is counted: it must be the figure's own unit (then the
            # unit is already said, once), or the figure a percent. A figure with no unit, in money,
            # or in another unit would be made to say what the noun does not
            if f.unit == "percent":
                return _Decision(False, f, number, None, kind)
            if f.unit in ("", "count") or f.unit in _MONEY_UNITS or not _unit_fits(phrase, f.unit):
                return _UNRESOLVED
            return _Decision(False, f, number, None, kind)
        return _Decision(False, f, number + (" " + unit_word if unit_word else ""), None, kind)
    if not fits:
        return _UNRESOLVED
    return _Decision(False, f, display_number(f, symbols=False, tilde=not hedged), None, kind)


def _decide_mention(m: Mention, shape: _Shape, phrase: tuple[str, ...], found: list[Figure], known: FigureSet,
                    quoted: bool, hedged: bool, limited: bool, approximate: bool, bare_ok: bool,
                    keys: frozenset[str] | set[str], hours: set[int] | None) -> _Decision:
    if m.form in _KEPT_AS_WRITTEN:
        return _LEAVE if supported(m, known, hours) else _UNRESOLVED
    if not shape.plain:
        return _UNRESOLVED
    f = _pick(m, shape, phrase, found, quoted or limited, limited, approximate, keys, bare_ok)
    if f is None:
        return _UNRESOLVED
    if quoted or limited:
        return _Decision(False, f, m.text)   # checked, bound, never rewritten
    if displayed_value(f) != f.value:
        # a figure we show rounded: what was said (its exact value, its rounded display, or a true
        # rounding of it) stays as written, since printing the display could only say less
        return _Decision(False, f, m.text)
    body = re.fullmatch(r"(~?-?)(.*)", display_number(f, symbols=False, tilde=not hedged), re.S)
    return _Decision(False, f, f"{body.group(1)}{shape.lead}{body.group(2)}{shape.trail}")


_LIST_MARK_BEFORE = re.compile(r"[ \t]*(?:[-*+>][ \t]+)?(?:\*\*|__)?\Z")
_LIST_MARK_AFTER = re.compile(r"(?:\*\*|__)?[.)]")


def _stands_as_a_quantity(view: str, start: int, end: int, before: str, line_starts: list[int]) -> bool:
    """Whether a bare number stands where a quantity stands, so a figure with no unit may name
    it: not a list marker ("**4.** Review pricing"), not a table cell ("| 4 | Review |"), and
    after a word that can precede a quantity ("is", "of", "about", "against", a comma ...)
    rather than a verb or a name ("Dial 4", "Room 12"). A rate or period phrase beside it does
    not matter: a figure with no period has nothing for the phrase to contradict, and one with
    a period is held to it as any figure is."""
    ls = line_starts[bisect_right(line_starts, start) - 1]
    if ls >= start - 40 and _LIST_MARK_BEFORE.fullmatch(view[ls:start]) and _LIST_MARK_AFTER.match(view, end):
        return False
    if re.search(r"\|[ \t]*\Z", before) and re.match(r"[ \t]*(?:\||$)", view[end:end + 20]):
        return False
    word = re.search(r"([A-Za-z]+)[ \t]*\Z", before)
    return not word or word.group(1).lower() in _PHRASE_STOP or word.group(1).lower() in _CUE_WORDS


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
    for o in _OPENER.finditer(_mask(out)):
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
    view = _mask(out)
    t_ends = [t[1] for t in token_spans]
    reread = []
    for r in mentions(view):
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
    for t in _TOKEN.finditer(view):
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
    view = _mask(text)          # what is read: the text without its links, code and paths
    tokens = list(_TOKEN.finditer(view))
    token_starts = [t.start() for t in tokens]
    token_ends = [t.end() for t in tokens]
    ms: list[Mention] = []
    for m in mentions(view):
        # the digits inside a token's id are the id's, not a number the model wrote
        i = bisect_right(token_ends, m.start)
        if i < len(tokens) and token_starts[i] < m.end:
            continue
        ms.append(m)
    if not ms and not tokens and not _OPENER.search(view):
        return _Run(text, [], [], [])
    clauses = _Clauses(view)
    matched: dict[Decimal, list[Figure]] = {}
    line_starts = [0] + [n.end() for n in re.finditer("\n", view)]

    # tokens first: they do not depend on ranges, and the number one becomes can be an end of one
    ms_ends = [m.end for m in ms]
    number_starts = sorted([m.start for m in ms] + [t.start() for t in tokens])
    token_decisions: list[_Decision] = []
    numbers: list[Mention] = list(ms)
    for t in tokens:
        k = bisect_right(ms_ends, t.start()) - 1
        n = bisect_right(number_starts, t.start())
        keys = clauses.nearest(t.start(), t.end(), number_starts[n] if n < len(number_starts) else len(view))
        d = _decide_token(t.group(1).strip(), view, t.start(), t.end(), known, ms_ends[k] if k >= 0 else 0, keys,
                          _stands_as_a_quantity(view, t.start(), t.end(), view[max(0, t.start() - 40):t.start()],
                                                line_starts),
                          clauses.limit_before(t.start()))
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
        joiner = _joiner(view, a, b)
        if joiner is None:
            continue
        paired = True
        nxt = _NEXT_WORD.match(view, b.end)
        word = nxt.group(1).lower() if nxt else None
        before = view[max(0, a.start - 12):a.start]
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

    quotes = [(q.start(), q.end()) for q in _QUOTE.finditer(view)]
    quote_starts = [q[0] for q in quotes]

    items: list[tuple[int, int, int, bool]] = [(t.start(), t.end(), i, True) for i, t in enumerate(tokens)]
    items += [(m.start, m.end, i, False) for i, m in enumerate(ms)]
    items.sort(key=lambda it: (it[0], it[1]))

    # "4/12" and "1:10" are ratios: their parts are not quantities any figure may name
    ratio: set[int] = set()
    for i in range(len(ms) - 1):
        a, b = ms[i], ms[i + 1]
        if view[a.end:b.start] in (":", "/") and a.form in ("digit", "word") and b.form in ("digit", "word"):
            ratio.update((i, i + 1))
    decisions: list[_Decision] = []
    for start, end, index, is_token in items:
        if is_token:
            decisions.append(token_decisions[index])
            continue
        m = ms[index]
        if index in ratio:
            decisions.append(_UNRESOLVED)
            continue
        reach = range_end.get(index, m.end)
        phrase: tuple[str, ...] = ()
        keys: frozenset[str] = frozenset()
        if shapes[index].kind == "bare":
            phrase = _phrase_after(view, reach)
        if not (phrase and phrase[0] in _TIME_CANON):   # a time word is the number's unit, not a period it is paid in
            n = bisect_left(number_starts, reach)
            keys = clauses.nearest(m.start, reach, number_starts[n] if n < len(number_starts) else len(view))
        q = bisect_right(quote_starts, m.start) - 1
        quoted = q >= 0 and m.end <= quotes[q][1]
        hedged, limited = _context(view, m.start, reach)
        before = view[max(0, m.start - 40):m.start]
        approximate = (not limited and bool(_APPROX_CUE.search(before)) and not clauses.limit_before(m.start))
        bare_ok = shapes[index].kind != "bare" or _stands_as_a_quantity(view, m.start, m.end, before, line_starts)
        if m.value not in matched:
            matched[m.value] = known.match(m.value)
        decisions.append(_decide_mention(m, shapes[index], phrase, matched[m.value], known, quoted, hedged, limited,
                                         approximate, bare_ok, keys, hours))

    reverted: set[int] = set()
    for _ in range(len(items) + 1):
        run, expect, token_spans = _assemble(text, items, ms, tokens, decisions, reverted)
        if run.text == text:
            break           # nothing was written that differs from what was there: nothing to read back
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
