"""Binding: print a figure's own value where the model wrote a number it matches,
and drop the sentences whose numbers nobody owns.

`bind(text, known)` reads every number the text holds (`read.mentions`) and every
`{{F:<id>}}` token, and decides each one:

    one figure, or several of equal value and unit
        the number is replaced by that figure's value. When the equal figures
        differ in kind the most trusted one wins: theirs, derived, reference,
        ours. Among figures of one kind the first added wins.
    figures of different values within tolerance
        the mention is ambiguous. The text is left as written and the mention is
        reported unresolved. A model that wrote "about $4,700" when the case file
        holds 4,720 and 4,680 has not named either of them.
    no figure
        left as written, reported unresolved.

Only the number is replaced, never what the sentence says around it. "twelve
classes" with a theirs count of 12 becomes "12 classes". The currency sign, the
percent sign and the words "percent", "USD" or "dollars" that the model put on its
number are kept; a symbol it did not write is not added. A magnitude it wrote
("10k", "1.5 million") is spelled out as the figure's digits. The figure's "~"
(derived and ours figures that rounding changed) goes in front, and a hedge word
right before the number ("about", "around", "roughly", "approximately",
"nearly", "circa", or a "~" the model wrote) is dropped so the page never says
"about ~$45,000".

What is never rewritten: times, dates (the reader leaves labels out of the
mentions altogether), and the kinds whose words carry the meaning, multipliers
("3x", "twice"), ordinals ("3rd", "third") and fractions ("half", "a third").
These stay exactly as written when a figure supports them
(`read.supported`), and are reported unresolved when none does. A time is
supported when `hours` is None or holds its hour.

A token is replaced by that figure's number with its symbols (`$22`, `25%`,
`~$45,000`) and no unit word. A token whose id is not in `known` is unresolved
and stays in the text.

`BindResult.unresolved` holds `Mention` records for numbers and
`UnresolvedToken` records for tokens. Both have `.text`, `.start` and `.end`, and
the positions are in `BindResult.text` (the bound text), so
`result.text[u.start:u.end] == u.text` always holds. `BindResult.bound` lists
each figure used once, in the order of first use.

`clean_sentences` binds, then removes each sentence that still holds an
unresolved record. `segments` returns the bound text in pieces, each bound
number carrying its figure's id, for the web.

The module imports the reader and the model only. It has no top-level import of
`app.engine` or `app.pipeline`.
"""
from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, replace
from typing import NamedTuple

from app.figures.model import Figure, FigureSet, display_number
from app.figures.read import Mention, mentions, supported


@dataclass(frozen=True)
class UnresolvedToken:
    """A `{{F:<id>}}` token whose id is not a known figure. `start` and `end`
    are positions in the bound text; `text` is the token as written."""
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


# -- the rules ------------------------------------------------------------------------------

# Most trusted first: what the client said, what we worked out from it, what a
# publication says, and last what we only propose.
_TRUST = {"theirs": 0, "derived": 1, "reference": 2, "ours": 3}

# Units a money mention may match; the same three the reader accepts (read._MONEY_UNITS).
_MONEY_UNITS = frozenset({"USD", "EUR", "GBP"})

# Forms whose words carry the meaning. A figure may support them; they are not
# rewritten, because "3" is not "3x", "3rd" or "a third".
_KEPT_AS_WRITTEN = frozenset({"time", "date", "multiplier", "ordinal", "fraction"})

_TOKEN = re.compile(r"\{\{\s*F\s*:\s*([^{}]*?)\s*\}\}")

_SP = r"[ \t\u00a0]"
# a hedge word right before a number, or a "~" / approximately-equal sign
_HEDGE = re.compile(
    rf"(?:(?<![A-Za-z])(?:about|around|roughly|approximately|nearly|circa){_SP}+|[~\u2248]{_SP}*)\Z",
    re.I)

# what a mention carries around its digits, which a replacement keeps:
# "$" / "US$" / the euro and pound signs / "USD " before, and "%", " percent",
# " percentage points", " USD", " dollars" after
_LEAD = re.compile(rf"[-\u2212]?(?P<cur>[A-Z]{{1,3}}\$|\$|\u20ac|\u00a3|(?:USD|EUR|GBP){_SP}?)?")
_TRAIL = re.compile(
    rf"(?:{_SP}*%|{_SP}*per{_SP}?cent|{_SP}*percentage{_SP}+points?"
    rf"|{_SP}?(?:USD|EUR|GBP)|{_SP}+(?:dollars?|euros?))\Z", re.I)


class _Shape(NamedTuple):
    lead: str    # the currency written before the number, "" if none
    trail: str   # the percent or currency words written after it, "" if none
    kind: str    # "percent", "money" or "plain": how the mention presents its number


def _shape(text: str) -> _Shape:
    lead = _LEAD.match(text)
    cur = lead.group("cur") or ""
    t = _TRAIL.search(text, lead.end())
    trail = t.group() if t else ""
    if "%" in trail or "per" in trail.lower():
        kind = "percent"
    elif cur or trail:
        kind = "money"
    else:
        kind = "plain"
    return _Shape(cur, trail, kind)


def _tier(kind: str, unit: str) -> int | None:
    """How well a figure's unit suits a mention: 0 is its own unit, 1 is a figure
    with no say about it, None cannot be this mention (a percent is not money)."""
    if kind == "percent":
        return 0 if unit == "percent" else 1 if unit == "" else None
    if kind == "money":
        return 0 if unit in _MONEY_UNITS else 1 if unit == "" else None
    return 0 if unit not in _MONEY_UNITS and unit != "percent" else 1


def _pick(m: Mention, shape: _Shape, known: FigureSet) -> Figure | None:
    """The one figure `m` names, or None when it names none or cannot choose."""
    cands = [(t, f) for f in known.match(m.value) if (t := _tier(shape.kind, f.unit)) is not None]
    if not cands:
        return None
    if len({f.value for _, f in cands}) > 1:
        return None   # figures of different values: a rounding that names none of them
    best = min(t for t, _ in cands)
    pool = [f for t, f in cands if t == best]
    if len({f.unit for f in pool}) > 1:
        return None   # the same value in two different units: 12 weeks or 12 reformers?
    return min(pool, key=lambda f: _TRUST[f.kind])   # min keeps the first of equals


class _Decision(NamedTuple):
    leave: bool            # supported, and kept exactly as written
    figure: Figure | None  # set: replace the span with `text`
    text: str


_LEAVE = _Decision(True, None, "")
_UNRESOLVED = _Decision(False, None, "")


def _decide_mention(m: Mention, known: FigureSet, hours: set[int] | None) -> _Decision:
    if m.form in _KEPT_AS_WRITTEN:
        return _LEAVE if supported(m, known, hours) else _UNRESOLVED
    shape = _shape(m.text)
    f = _pick(m, shape, known)
    if f is None:
        return _UNRESOLVED
    body = re.fullmatch(r"(~?-?)(.*)", display_number(f, symbols=False), re.S)
    return _Decision(False, f, f"{body.group(1)}{shape.lead}{body.group(2)}{shape.trail}")


def _decide_token(figure_id: str, known: FigureSet) -> _Decision:
    f = known.get(figure_id)
    return _UNRESOLVED if f is None else _Decision(False, f, display_number(f))


# -- one pass over the text ----------------------------------------------------------------------

@dataclass
class _Run:
    text: str
    bound: list[Figure]
    unresolved: list[Unresolved]
    spans: list[tuple[int, int, str]]   # (start, end, figure id) of each replacement, in `text`


def _run(text: str, known: FigureSet, hours: set[int] | None) -> _Run:
    text = text or ""
    tokens = list(_TOKEN.finditer(text))
    items: list[tuple[int, int, Mention | re.Match]] = [(t.start(), t.end(), t) for t in tokens]
    for m in mentions(text):
        # the digits inside a token's id are the id's, not a number the model wrote
        if not any(m.start < t.end() and m.end > t.start() for t in tokens):
            items.append((m.start, m.end, m))
    if not items:
        return _Run(text, [], [], [])
    items.sort(key=lambda it: (it[0], it[1]))

    pieces: list[str] = []
    length = 0                  # length of the bound text so far
    cursor = 0                  # how much of `text` has been copied or replaced
    bound: dict[str, Figure] = {}
    unresolved: list[Unresolved] = []
    spans: list[tuple[int, int, str]] = []
    for start, end, item in items:
        if isinstance(item, Mention):
            d = _decide_mention(item, known, hours)
        else:
            d = _decide_token(item.group(1).strip(), known)
        if d.leave:
            continue
        gap = text[cursor:start]
        if d.figure is not None:
            if d.text.startswith("~"):
                hedge = _HEDGE.search(gap)
                if hedge:
                    gap = gap[:hedge.start()]
            pieces += [gap, d.text]
            spans.append((length + len(gap), length + len(gap) + len(d.text), d.figure.id))
            length += len(gap) + len(d.text)
            bound.setdefault(d.figure.id, d.figure)
        else:
            written = text[start:end]
            at = length + len(gap)
            if isinstance(item, Mention):
                unresolved.append(replace(item, start=at, end=at + len(written)))
            else:
                unresolved.append(UnresolvedToken(written, at, at + len(written), item.group(1).strip()))
            pieces += [gap, written]
            length += len(gap) + len(written)
        cursor = end
    pieces.append(text[cursor:])
    return _Run("".join(pieces), list(bound.values()), unresolved, spans)


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
_LIST_MARK = re.compile(r"[ \t]*(?:[-*+\u2022\u2013>]|#{1,6}|\d{1,3}[.)])[ \t]+")   # a bullet, a heading, "3."
_MARK_ALONE = re.compile(r"[ \t]*(?:[-*+\u2022\u2013>]|#{1,6}|\d{1,3}[.)])")
_SPACE = re.compile(r"\s+")


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
    line_start = text.rfind("\n", 0, k) + 1
    if _MARK_ALONE.fullmatch(text[line_start:j]):
        return False                     # "1." opening a list line
    low = word.lower()
    next_char = text[b] if b < len(text) else ""
    if low in _CLOCK:
        return next_char.isupper()
    if low in _ABBREVIATIONS or _DOTTED.fullmatch(word) or _INITIAL.fullmatch(word):
        return False
    return not next_char.islower()       # "5. and then ..." is not a new sentence


def _line_break_ends(text: str, a: int, b: int) -> bool:
    """Whether the white space text[a:b], which holds a line break, ends a unit:
    a blank line does; so does a line that ends in a full stop, colon or the like,
    a list or heading line, or a line followed by one. A line that merely wraps
    does not, so a sentence broken over two lines stays whole."""
    ws = text[a:b]
    if ws.count("\n") >= 2:
        return True
    j = _stop_before(text, a)
    if j > 0 and (text[j - 1] in _TERMINATORS or text[j - 1] in ":;"):
        return True
    line_start = text.rfind("\n", 0, a) + 1
    return bool(_LIST_MARK.match(text, b) or _LIST_MARK.match(text, line_start))


def _units(text: str) -> list[tuple[int, int, int]]:
    """Split into sentence-like units as (start, body end, end): the body, then the
    white space that separates it from the next unit. Leading white space belongs
    to the first body. Nothing is lost: the units cover the text."""
    cuts: list[int] = []
    for m in _SPACE.finditer(text):
        a, b = m.span()
        if a == 0 or b == len(text):
            continue
        ends = _line_break_ends(text, a, b) if "\n" in m.group() else _ends_sentence_inline(text, a, b)
        if ends:
            cuts.append(m.span())
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
    sentence, and each list or heading line also end a unit, so dropping one
    bullet or paragraph leaves the others whole, with their own spacing. Nothing
    is added: the kept sentences are the bound text's own characters."""
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
        if kept and kept[-1][1] and "\n" not in kept[-1][1]:
            kept[-1][1] = sep           # the line now ends where the dropped sentence's did
    joined = "".join(body + sep for body, sep in kept)
    if not joined.strip():
        return "", removed
    return joined.rstrip() + t[len(t.rstrip()):], removed
