"""Which numbers the owner actually gave us, and whether a sentence stays inside them.

Every new client-facing surface — the week drawn from their answers, the
answer screen's headline figures, the value of the move, the action plan —
is written by a model and then checked here. The rule is the product's
promise: a figure on screen is one they said, arithmetic on ones they said
(with the working shown), or a number we PROPOSE and label as ours.

The registry's own extractor (`registry._numbers`) deliberately skips clock
times and number words, because the documents it polices use neither as
figures. Owners do: "six classes a day, six days a week" and "the 6pm and
7pm ones have a waiting list" are the two sentences a capacity picture rests
on. So this reads both.
"""

import re

_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19,
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
         "seventy": 70, "eighty": 80, "ninety": 90}
_OTHER = {"dozen": 12, "hundred": 100, "thousand": 1000}

_TIME = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?\b|\b([01]?\d|2[0-3]):([0-5]\d)\b", re.IGNORECASE)
_NUM = re.compile(r"(?<![\w.])(\$|€|£)?(\d[\d,]*(?:\.\d+)?)\s*(k|K|m|M)?(?![\w])")
_WORD = re.compile(r"\b(" + "|".join(sorted(list(_TENS) + list(_ONES) + list(_OTHER), key=len, reverse=True))
                   + r")(?:[\s-](" + "|".join(sorted(_ONES, key=len, reverse=True)) + r"))?\b", re.IGNORECASE)

#: Constants arithmetic may use without anyone having said them.
CONSTANTS = {52: "weeks a year", 12: "months a year", 7: "days a week", 365: "days a year",
             4: "weeks a month", 4.33: "weeks a month", 30: "days a month", 24: "hours a day",
             60: "minutes an hour"}


def _hour24(hour: int, ampm: str | None) -> int:
    if not ampm:
        return hour
    ampm = ampm.lower()
    if ampm == "p" and hour < 12:
        return hour + 12
    if ampm == "a" and hour == 12:
        return 0
    return hour


def times_in(text: str) -> list[int]:
    """Clock times as 24-hour hours: '6pm' -> 18, '18:00' -> 18."""
    out = []
    for m in _TIME.finditer(text or ""):
        if m.group(1) is not None:
            out.append(_hour24(int(m.group(1)), m.group(3)))
        else:
            out.append(int(m.group(4)))
    return out


def _strip_times(text: str) -> str:
    return _TIME.sub(" ", text or "")


def numbers_in(text: str, words: bool = False) -> list[float]:
    """Every figure in a piece of text. Clock times are left out: they are
    checked on their own (`times_in`), and '18:00' is not the number 18.

    Number words are read only on request — owners write them ("six days a
    week") and a model writing prose does too ("in two weeks"), but only the
    first is evidence.
    """
    src = _strip_times(text)
    out: list[float] = []
    for m in _NUM.finditer(src):
        try:
            v = float(m.group(2).replace(",", ""))
        except ValueError:
            continue
        suffix = (m.group(3) or "").lower()
        if suffix == "k":
            v *= 1000
        elif suffix == "m" and m.group(1):
            v *= 1_000_000
        out.append(v)
    if words:
        for m in _WORD.finditer(src):
            first, second = m.group(1).lower(), (m.group(2) or "").lower()
            if first in _TENS:
                out.append(_TENS[first] + _ONES.get(second, 0))
            elif first in _ONES:
                out.append(_ONES[first])
                if second:
                    out.append(_ONES[second])
            else:
                out.append(_OTHER[first])
    return out


def given(texts) -> set[float]:
    """What the owner said, as a set of values: digits and number words.

    Clock times are NOT in here. "The 7pm class" is not the number 7, and
    counting it as one let "7 days a week" through for a studio that opens
    six. The times they named are given_hours, checked on their own."""
    out: set[float] = set()
    for t in texts or []:
        if t:
            out.update(numbers_in(t, words=True))
    return out


def given_hours(texts) -> set[int]:
    """Every clock time they named, as 24-hour hours."""
    return {h for t in texts or [] if t for h in times_in(t)}


def close(a: float, b: float) -> bool:
    return abs(a - b) <= max(0.005 * abs(b), 1e-6)


def holds(value, allowed) -> bool:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    return any(close(v, a) for a in allowed)


def unsupported(text: str, allowed, lenient_below: float = 2, hours=None) -> list[float]:
    """Numbers in `text` that are neither allowed nor trivially small.

    0 and 1 are never checked: "1 in 20" and "one of the explanations" are
    prose as often as figures. Money and percentages are always checked, at
    any size — the figures a reader acts on. Clock times are checked against
    `hours`, the times they named, when it is given.
    """
    bad = []
    src = _strip_times(text)
    for m in _NUM.finditer(src):
        try:
            v = float(m.group(2).replace(",", ""))
        except ValueError:
            continue
        if (m.group(3) or "").lower() == "k":
            v *= 1000
        money = bool(m.group(1))
        pct = src[m.end():m.end() + 2].lstrip().startswith("%")
        if not (money or pct) and v < lenient_below:
            continue
        if not holds(v, allowed):
            bad.append(v)
    if hours is not None:
        for h in times_in(text):
            if h not in hours:
                bad.append(float(h))
    return bad


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("’", "'").replace("“", '"').replace("”", '"')).strip().casefold()


def quoted(fragment: str, texts) -> bool:
    """Whether `fragment` is really in what they wrote — a quote we put in
    their mouth must be one they said."""
    frag = normalise(fragment).strip(" .\"'")
    if len(frag) < 3:
        return False
    return any(frag in normalise(t) for t in texts or [] if t)


def rounded(v: float) -> float:
    """The figure a person would say out loud: 44,928 -> 45,000."""
    a = abs(v)
    step = 1000 if a >= 10_000 else 100 if a >= 1000 else 10 if a >= 100 else 1
    return round(v / step) * step


def money(v: float) -> str:
    return f"${v:,.0f}"
