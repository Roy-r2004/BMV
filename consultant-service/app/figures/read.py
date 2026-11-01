"""The number reader and checker.

`mentions(text)` reads every number a piece of prose holds; `unsupported(text,
known)` returns the ones no known figure supports. There is no leniency: a
small number is a number, and "1 of 5" holds two of them.

This is its own grammar. It does not use `registry._numbers`, which the engine
and the frozen laws depend on, and it imports nothing from the pipeline or the
engine. It reads with Decimal only; no float is ever made.

What it counts (plan ruling 8), with the form each mention carries:

    digit       12, 1.5, 0.5, .5, 1,000, 45,000, -5; k/M suffixes (10k, 5M) and
                magnitude words (1.5 million, 2 dozen) scale the value
    money       $35, $22.50, US$35, the euro and pound signs, 35 USD, $35k,
                $1.2M, $2bn (m, B and bn scale only after a currency sign)
    percent     50%, 50 %, 25 percent, 25 per cent, fifty percent; the value is
                the percent number (25), never the fraction
    word        two to nineteen, the tens, compounds spaced or hyphenated
                (twenty-two, twenty two), hundred, thousand, million, billion,
                dozen, "a dozen", "half a dozen", "a hundred and twenty",
                "two and a half"
    multiplier  3x, 3 followed by the multiplication sign, 3-fold, threefold,
                tenfold, twice, double, triple, quadruple (and their -d/-s/-ing)
    ordinal     3rd, 1st, 22nd; third and up, twenty-first
    range       2-3, 2 to 3, en or em dash, $20-$30, 10-15%, 10-15k: one
                mention per end, a magnitude on the second end scales the first
    time        6pm, 6 p.m., 6:30 pm, 18:00, 6-7pm, 9am to 5pm; the value is the
                hour on a 24-hour clock
    date        a year 1900-2100 standing alone (2025, the 1990s, 2025-2026), a
                day with a month name (31 Oct, 31st October, the 3rd of March,
                Oct 31), 2025-03-01, 31/10/2025

What it does not count:
  - "one", "a", "an", "first", "second" on their own: articles and a unit of
    time before they are quantities. "one hundred", "twenty-one", "a dozen" and
    "one and a half" are quantities and are counted.
  - a number right after a label word from `labels.LABEL_WORDS`, or its plural
    ("Phase 2", "Exhibit 2.1", "Phases 1-2", "Phase two"): ruling 4.
  - identifiers: letters with digits glued on (Q3, M3-A, B2B, FY2025, v2.1) and capitals,
    a hyphen and digits (CF-04); a dotted chain of three or more parts (3.2.1).
  - "double" or "triple" in a hyphenated compound (double-check).
  - vague plurals (hundreds, dozens).
A month name is a proper noun and is read only capitalised ("May 3", not "may 3").
A unit glued to a number stays out of the mention: "8hrs" is the mention "8".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.figures.labels import LABEL_WORDS
from app.figures.model import FigureSet

Form = Literal["digit", "money", "percent", "word", "multiplier", "ordinal", "range", "time", "date"]


@dataclass(frozen=True)
class Mention:
    """One number as written: the exact text, where it sits, its value, and its form."""
    text: str
    start: int
    end: int
    value: Decimal
    form: Form


# -- the grammar -----------------------------------------------------------------------

_SP = r"[ \t\u00a0]"   # a space inside one phrase; never a line break

# currency before the number: $, US$ / A$ style, the euro sign, the pound sign
_CUR = r"(?:[A-Z]{1,3}\$|\$|\u20ac|\u00a3)"
_CODE = r"(?:USD|EUR|GBP)"
# 1,000 style separators only in groups of three; a point only with a digit after
# it, so the full stop that ends a sentence is never read as a decimal point
_NUM = r"(?:(?:\d{1,3}(?:,\d{3})+(?!\d)|\d+)(?:\.\d+)?|\.\d+)"

_HEAD = re.compile(
    rf"(?P<sign>[-\u2212](?=[\d$\u20ac\u00a3.]))?"
    rf"(?:(?P<cur>{_CUR}){_SP}?|(?P<code>{_CODE}){_SP}?)?"
    rf"(?P<num>{_NUM})")
_MAG_LETTER = re.compile(r"(?P<m>[kK]|M|bn|B|m)(?![A-Za-z0-9])")
_MAG_WORD = re.compile(rf"{_SP}+(?P<w>thousand|million|billion|dozen)(?![A-Za-z])", re.I)
_PCT = re.compile(rf"{_SP}?%|{_SP}*(?:per{_SP}?cent|percentage{_SP}+points?)(?![A-Za-z])", re.I)
_TIMES = re.compile(rf"x(?![A-Za-z0-9])|{_SP}?\u00d7")
_FOLD = re.compile(r"-?fold(?![A-Za-z])", re.I)
_ORD = re.compile(r"(?:st|nd|rd|th)(?![A-Za-z0-9])", re.I)
_MONEY_AFTER = re.compile(rf"{_SP}?{_CODE}(?![A-Za-z])|{_SP}+(?i:dollars?|euros?)(?![A-Za-z])")
_MONEY_WORDS = re.compile(rf"{_SP}+(?:dollars?|euros?)(?![A-Za-z])", re.I)
_TO = re.compile(rf"{_SP}*[-\u2013\u2014]{_SP}*|{_SP}+to{_SP}+")
_CHAIN = re.compile(r"\d+(?:\.\d+){2,}(?!\d)")

_MAGNITUDE = {"k": 1000, "K": 1000, "M": 10**6, "m": 10**6, "B": 10**9, "bn": 10**9,
              "thousand": 1000, "million": 10**6, "billion": 10**9, "dozen": 12}
_NEEDS_CURRENCY = frozenset({"m", "B", "bn"})   # 5m is five metres or minutes, 70B a model size

# clock times: "p.m." keeps its own final point, "6pm." leaves the full stop alone
_MER = r"(?:\.{sp}?m\.|{sp}?m)(?![A-Za-z])".format(sp=_SP)
_TIME_RANGE = re.compile(
    rf"(?P<h1>\d{{1,2}})(?:[:.](?P<m1>[0-5]\d))?(?:{_SP}*[-\u2013]{_SP}*|{_SP}+to{_SP}+)"
    rf"(?P<h2>\d{{1,2}})(?:[:.](?P<m2>[0-5]\d))?{_SP}?(?P<ap>[ap]){_MER}", re.I)
_TIME_12 = re.compile(rf"(?P<h>\d{{1,2}})(?:[:.](?P<mi>[0-5]\d))?{_SP}?(?P<ap>[ap]){_MER}", re.I)
_TIME_24 = re.compile(r"(?P<h>[01]?\d|2[0-3]):(?P<mi>[0-5]\d)(?![\d:])")

# dates: month names are proper nouns, so only capitalised ones are read
_MONTHS = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?"
           r"|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)")
_DAY_MONTH = re.compile(rf"(?P<d>\d{{1,2}})(?:st|nd|rd|th)?(?:{_SP}+of)?{_SP}+{_MONTHS}(?![A-Za-z])")
_MONTH_DAY = re.compile(rf"{_MONTHS}\.?{_SP}+(?P<d>\d{{1,2}})(?:st|nd|rd|th)?(?![A-Za-z0-9%]|[.:]\d)")
_ISO_DATE = re.compile(r"(?P<y>19\d\d|20\d\d|2100)-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])(?!\d)")
_SLASH_DATE = re.compile(r"(?P<d>\d{1,2})/\d{1,2}/(?:\d{4}|\d{2})(?![\d/])")

# identifiers, not quantities: Q3, M3-A, B2B, FY2025, v2.1; CF-04, ISO-9001
_IDENT = re.compile(r"[A-Za-z]+\d[A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)*|[A-Z]{1,6}-\d[A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)*")

_WORD = re.compile(r"[A-Za-z]+")
_JOIN = re.compile(rf"{_SP}+|-(?=[A-Za-z])")

_LABELS = frozenset(w.lower() for w in LABEL_WORDS)

# number words
_UNITS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
_TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
          "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
         "eighty": 80, "ninety": 90}
_SCALES = {"thousand": 10**3, "million": 10**6, "billion": 10**9}
_ORD_UNITS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
              "seventh": 7, "eighth": 8, "ninth": 9}
_ORD_TEENS = {"tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
              "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18, "nineteenth": 19}
_ORD_TENS = {"twentieth": 20, "thirtieth": 30, "fortieth": 40, "fiftieth": 50, "sixtieth": 60,
             "seventieth": 70, "eightieth": 80, "ninetieth": 90}
_ORD_SCALES = {"thousandth": 10**3, "millionth": 10**6}
# counted only as part of a longer phrase: "one" and "a" are articles, "first"
# and "second" an order and a unit of time, before they are quantities
_NOT_ALONE = frozenset({"one", "first", "second"})
_AFTER_A = frozenset({"dozen", "hundred", *_SCALES})
_STARTS = frozenset({*_UNITS, *_TEENS, *_TENS, *_ORD_UNITS, *_ORD_TEENS, *_ORD_TENS})

_MULT_WORDS = {
    "twice": 2,
    **{f"double{s}": 2 for s in ("", "d", "s")}, "doubling": 2,
    **{f"triple{s}": 3 for s in ("", "d", "s")}, "tripling": 3,
    **{f"quadruple{s}": 4 for s in ("", "d", "s")}, "quadrupling": 4,
}
_FOLD_PREFIX = {**_UNITS, **_TEENS, **_TENS, "hundred": 100, "thousand": 1000}


# -- small readers ------------------------------------------------------------------------

@dataclass
class _Qty:
    start: int
    end: int
    value: Decimal
    money: bool = False
    percent: bool = False
    times: bool = False
    ordinal: bool = False
    scale: int = 1
    signed: bool = False
    plain: bool = False   # bare digits: no sign, currency, separator, point or suffix


def _quantity(text: str, pos: int) -> _Qty | None:
    """A number written in digits at `pos`, with its currency, magnitude and
    suffix (percent, multiplier, ordinal, currency after it)."""
    m = _HEAD.match(text, pos)
    if not m:
        return None
    num = m.group("num")
    q = _Qty(start=pos, end=m.end(), value=Decimal(num.replace(",", "")),
             money=bool(m.group("cur") or m.group("code")), signed=bool(m.group("sign")))
    if q.signed:
        q.value = -q.value
    mag = _MAG_LETTER.match(text, q.end)
    if mag and (mag.group("m") not in _NEEDS_CURRENCY or q.money):
        q.scale, q.end = _MAGNITUDE[mag.group("m")], mag.end()
    else:
        word = _MAG_WORD.match(text, q.end)
        if word:
            q.scale, q.end = _MAGNITUDE[word.group("w").lower()], word.end()
    q.value *= q.scale
    pct = _PCT.match(text, q.end)
    times = _TIMES.match(text, q.end) or _FOLD.match(text, q.end)
    ordinal = _ORD.match(text, q.end) if q.scale == 1 and not q.money and num.isdigit() else None
    after = _MONEY_AFTER.match(text, q.end)
    if pct:
        q.percent, q.end = True, pct.end()
    elif times:
        q.times, q.end = True, times.end()
    elif ordinal:
        q.ordinal, q.end = True, ordinal.end()
    elif after:
        q.money, q.end = True, after.end()
    q.plain = (num.isdigit() and q.scale == 1 and not
               (q.signed or q.money or q.percent or q.times or q.ordinal))
    return q


def _form(q: _Qty) -> Form:
    if q.percent:
        return "percent"
    if q.money:
        return "money"
    if q.times:
        return "multiplier"
    if q.ordinal:
        return "ordinal"
    return "digit"


def _mention(text: str, start: int, end: int, value: Decimal | int, form: Form) -> Mention:
    return Mention(text=text[start:end], start=start, end=end, value=Decimal(value), form=form)


def _after_label(text: str, start: int) -> bool:
    """True when the number at `start` follows a label word ("Phase 2", "Phases 1-2")."""
    j = start
    while j > 0 and text[j - 1] in " \t\u00a0":
        j -= 1
    if j == start:
        return False
    k = j
    while k > 0 and text[k - 1].isalpha():
        k -= 1
    word = text[k:j].lower()
    return word in _LABELS or (word.endswith("s") and word[:-1] in _LABELS)


def _is_year(q: _Qty, text: str) -> bool:
    return q.plain and q.end - q.start == 4 and 1900 <= q.value <= 2100 and not text[q.end:q.end + 1].isalpha()


def _hour24(hour: int, ap: str) -> int:
    ap = ap.lower()
    if ap == "p" and hour < 12:
        return hour + 12
    if ap == "a" and hour == 12:
        return 0
    return hour


Read = tuple[int, list[Mention]]   # where reading stopped, and what it found


def _read_time(text: str, pos: int) -> Read | None:
    m = _TIME_RANGE.match(text, pos)
    if m and 1 <= int(m.group("h1")) <= 12 and 1 <= int(m.group("h2")) <= 12:
        ap = m.group("ap")
        second = _hour24(int(m.group("h2")), ap)
        first = _hour24(int(m.group("h1")), ap)
        if first > second:   # 11-1pm is 11am to 1pm
            first = _hour24(int(m.group("h1")), "a" if ap.lower() == "p" else "p")
        end1 = m.end("m1") if m.group("m1") else m.end("h1")
        return m.end(), [_mention(text, pos, end1, first, "time"),
                         _mention(text, m.start("h2"), m.end(), second, "time")]
    m = _TIME_12.match(text, pos)
    if m and 1 <= int(m.group("h")) <= 12:
        return m.end(), [_mention(text, pos, m.end(), _hour24(int(m.group("h")), m.group("ap")), "time")]
    m = _TIME_24.match(text, pos)
    if m:
        return m.end(), [_mention(text, pos, m.end(), int(m.group("h")), "time")]
    return None


def _read_date(text: str, pos: int) -> Read | None:
    m = _ISO_DATE.match(text, pos)
    if m:
        return m.end(), [_mention(text, pos, m.end(), int(m.group("y")), "date")]
    for pattern in (_SLASH_DATE, _DAY_MONTH, _MONTH_DAY):
        m = pattern.match(text, pos)
        if m and 1 <= int(m.group("d")) <= 31:
            return m.end(), [_mention(text, pos, m.end(), int(m.group("d")), "date")]
    return None


def _read_range(text: str, pos: int) -> Read | None:
    a = _quantity(text, pos)
    if a is None or a.times or a.ordinal:
        return None
    to = _TO.match(text, a.end)
    if not to or text[to.end():to.end() + 1] in ("-", "\u2212"):
        return None
    b = _quantity(text, to.end())
    if b is None or b.ordinal or b.signed:
        return None
    if _after_label(text, pos):
        return b.end, []
    if _is_year(a, text) and _is_year(b, text):
        return b.end, [_mention(text, a.start, a.end, a.value, "date"),
                       _mention(text, b.start, b.end, b.value, "date")]
    if b.scale != 1 and a.scale == 1:   # 10-15k is ten to fifteen thousand
        a.value *= b.scale
    return b.end, [_mention(text, a.start, a.end, a.value, "range"),
                   _mention(text, b.start, b.end, b.value, "range")]


def _read_digits(text: str, pos: int) -> Read | None:
    chain = _CHAIN.match(text, pos)
    if chain:   # 3.2.1 is a section or version, not a quantity
        return chain.end(), []
    q = _quantity(text, pos)
    if q is None:
        return None
    form = _form(q)
    if form == "digit" and _after_label(text, pos):
        return q.end, []
    if _is_year(q, text):
        return q.end, [_mention(text, pos, q.end, q.value, "date")]
    if q.plain and q.end - q.start == 4 and 1900 <= q.value <= 2100 and text[q.end:q.end + 1] == "s" \
            and not text[q.end + 1:q.end + 2].isalpha():   # the 1990s
        return q.end + 1, [_mention(text, pos, q.end + 1, q.value, "date")]
    return q.end, [_mention(text, pos, q.end, q.value, form)]


def _words_from(text: str, pos: int, limit: int = 16) -> list[tuple[str, int, int, bool]]:
    """Up to `limit` words from `pos`, each joined to the one before by spaces or
    one hyphen: (word in lower case, start, end, joined by a hyphen)."""
    out: list[tuple[str, int, int, bool]] = []
    p, hyphen = pos, False
    while len(out) < limit:
        m = _WORD.match(text, p)
        if not m:
            break
        out.append((m.group().lower(), m.start(), m.end(), hyphen))
        j = _JOIN.match(text, m.end())
        if not j:
            break
        hyphen, p = j.group() == "-", j.end()
    return out


def _phrase(words: list[str]) -> tuple[Decimal, int, bool] | None:
    """The number a run of number words says: (value, words used, is an ordinal),
    or None when it says none. Words combine as numbers are spoken: a unit only
    after nothing, a tens word, hundred or a scale; hundred after something under
    a hundred; scales falling (thousand after million, never before); "and" only
    after hundred or a scale and before a number word."""
    n = len(words)

    def at(i: int) -> str | None:
        return words[i] if i < n else None

    total, group = Decimal(0), None
    last: str | None = None     # what the word before was
    hundred_here, last_scale, ordinal, k = False, None, False, 0
    if at(0) == "a" and at(1) in _AFTER_A:
        group, last, k = Decimal(1), "a", 1
    elif at(0) == "half":
        j = 2 if at(1) == "a" else 1
        if at(j) not in _AFTER_A:
            return None
        group, last, k = Decimal("0.5"), "a", j
    while k < n and not ordinal:
        w = words[k]
        if w in _UNITS or w in _ORD_UNITS:
            if last not in (None, "tens", "hundred", "scale", "and"):
                break
            group, last = (group or 0) + _UNITS.get(w, _ORD_UNITS.get(w, 0)), "unit"
            ordinal = w in _ORD_UNITS
        elif w in _TEENS or w in _ORD_TEENS:
            if last not in (None, "hundred", "scale", "and"):
                break
            group, last = (group or 0) + _TEENS.get(w, _ORD_TEENS.get(w, 0)), "teen"
            ordinal = w in _ORD_TEENS
        elif w in _TENS or w in _ORD_TENS:
            if last not in (None, "hundred", "scale", "and"):
                break
            group, last = (group or 0) + _TENS.get(w, _ORD_TENS.get(w, 0)), "tens"
            ordinal = w in _ORD_TENS
        elif w in ("hundred", "hundredth"):
            if last not in ("unit", "teen", "tens", "a") or hundred_here:
                break
            group, last, hundred_here = group * 100, "hundred", True
            ordinal = w == "hundredth"
        elif w in _SCALES or w in _ORD_SCALES:
            scale = _SCALES.get(w) or _ORD_SCALES[w]
            if last not in ("unit", "teen", "tens", "hundred", "a") or (last_scale and scale >= last_scale):
                break
            total, group, last, hundred_here, last_scale = total + group * scale, None, "scale", False, scale
            ordinal = w in _ORD_SCALES
        elif w == "dozen":
            if last not in ("unit", "teen", "tens", "a"):
                break
            group, last, k = group * 12, "dozen", k + 1
            break
        elif w == "and":
            if last not in ("hundred", "scale") or at(k + 1) not in _STARTS:
                break
            last = "and"
        else:
            break
        k += 1
    if last in (None, "a", "and"):
        return None
    value = total + (group or 0)
    if not ordinal and words[k:k + 3] == ["and", "a", "half"]:
        value, k = value + Decimal("0.5"), k + 3
    if k == 1 and words[0] in _NOT_ALONE:
        return None
    return value, k, ordinal


def _read_words(text: str, pos: int) -> Read | None:
    ws = _words_from(text, pos)
    if not ws:
        return None
    first, _, first_end, _ = ws[0]
    if first in _MULT_WORDS:
        if len(ws) > 1 and ws[1][3]:   # double-check, triple-booked: a compound, not a factor
            return first_end, []
        return first_end, [_mention(text, pos, first_end, _MULT_WORDS[first], "multiplier")]
    if first.endswith("fold") and first[:-4] in _FOLD_PREFIX:
        return first_end, [_mention(text, pos, first_end, _FOLD_PREFIX[first[:-4]], "multiplier")]
    parsed = _phrase([w[0] for w in ws])
    if parsed is None:
        return None
    value, used, ordinal = parsed
    end = ws[used - 1][2]
    if ordinal:
        return end, [_mention(text, pos, end, value, "ordinal")]
    if used < len(ws) and ws[used][0] == "fold":   # three-fold
        return ws[used][2], [_mention(text, pos, ws[used][2], value, "multiplier")]
    if _after_label(text, pos):   # Phase two
        return end, []
    pct = _PCT.match(text, end)
    if pct:
        return pct.end(), [_mention(text, pos, pct.end(), value, "percent")]
    money = _MONEY_WORDS.match(text, end)
    if money:
        return money.end(), [_mention(text, pos, money.end(), value, "money")]
    return end, [_mention(text, pos, end, value, "word")]


def _read_letters(text: str, pos: int) -> Read | None:
    m = _MONTH_DAY.match(text, pos)
    if m and 1 <= int(m.group("d")) <= 31:
        return m.end(), [_mention(text, pos, m.end(), int(m.group("d")), "date")]
    q = _quantity(text, pos)   # US$35, USD 35
    if q is not None:
        return q.end, [_mention(text, pos, q.end, q.value, _form(q))]
    m = _IDENT.match(text, pos)
    if m:
        return m.end(), []
    return _read_words(text, pos)


def _read_at(text: str, pos: int) -> Read | None:
    if text[pos].isalpha():
        return _read_letters(text, pos)
    return (_read_date(text, pos) or _read_time(text, pos)
            or _read_range(text, pos) or _read_digits(text, pos))


def _can_start(text: str, i: int) -> bool:
    prev = text[i - 1] if i else ""
    if prev.isalnum() or prev == "_":
        return False
    ch, nxt = text[i], text[i + 1:i + 2]
    if ch.isdigit() or ch in "$\u20ac\u00a3":
        return True
    if ch in "-\u2212":
        return bool(nxt) and (nxt.isdigit() or nxt in "$\u20ac\u00a3.")
    if ch == ".":
        return prev != "." and nxt.isdigit()
    return ch.isascii() and ch.isalpha()


# -- the public reader and checker ----------------------------------------------------------

def mentions(text: str) -> list[Mention]:
    """Every number `text` holds, in text order. A range gives one mention per end."""
    out: list[Mention] = []
    text = text or ""
    i, n = 0, len(text)
    while i < n:
        if not _can_start(text, i):
            i += 1
            continue
        read = _read_at(text, i)
        if read is None:
            if text[i].isalpha():   # not a number: step over the whole word
                while i < n and text[i].isalnum():
                    i += 1
            else:
                i += 1
            continue
        end, found = read
        out.extend(found)
        i = max(end, i + 1)
    return out


# Units a money mention may match. "USD" is what the registry gives money
# (registry._infer_unit); the others are the codes the reader knows.
_MONEY_UNITS = frozenset({"USD", "EUR", "GBP"})


def supported(m: Mention, known: FigureSet, hours: set[int] | None = None) -> bool:
    """Whether a known figure supports the mention.

    A time is supported when `hours` is None or holds its hour. A date is
    supported by its form. Every other form needs a figure in `known.match`
    (within half a percent, or equal as the figure displays). Two unit checks
    keep a number from passing as something else: money needs a figure in a
    money unit or with no unit, and a percent (compared as the percent number,
    25 for 25%) needs a figure in "percent" or with no unit.

    A mention near two figures of different values is supported here; refusing
    to pick one of them is the binder's job, not the reader's."""
    if m.form == "time":
        return hours is None or int(m.value) in hours
    if m.form == "date":
        return True
    found = known.match(m.value)
    if m.form == "money":
        return any(f.unit == "" or f.unit in _MONEY_UNITS for f in found)
    if m.form == "percent":
        return any(f.unit in ("", "percent") for f in found)
    return bool(found)


def unsupported(text: str, known: FigureSet, *, hours: set[int] | None = None) -> list[Mention]:
    """Every mention in `text` that no known figure supports, in text order."""
    return [m for m in mentions(text) if not supported(m, known, hours)]
