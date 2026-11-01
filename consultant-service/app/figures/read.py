"""The number reader and checker.

`mentions(text)` reads every number a piece of prose holds; `unsupported(text,
known)` returns the ones no known figure supports. There is no leniency: a
small number is a number, and "1 of 5" holds two of them. A hidden number is
the one failure this reader must not have, so wherever the grammar is unsure,
it reads the number: a false flag is preferred to a hidden number.

This is its own grammar. It does not use `registry._numbers`, which the engine
and the frozen laws depend on, and it imports nothing from the pipeline or the
engine. It reads with Decimal only; no float is ever made. Every walk over the
text is linear: runs (digit-led tokens, underscore runs) are measured in one
pass, and no regex can backtrack across a long run more than once.

What it counts (plan ruling 8), with the form each mention carries:

    digit       12, 1.5, 0.5, .5, 1,000, 45 000 (space, thin space or no-break
                space between groups of three), -5; k/K and M scale (10k, 5M),
                as do magnitude words (1.5 million, 2 dozen). The tail of a
                token that starts with a digit is read too: 10x12, 1h30, 24x7.
    money       a currency sign before or after ($35, 40$, the euro, pound, yen
                and rupee signs), US$35, a currency code before or after, glued
                or spaced (AUD50, CAD 5, Rs500, 35 USD), dollars/euros after;
                $35k, $1.2M, $5MM, $5mn, $2bn, $2B (m, MM, mn, B and bn scale
                only with a currency)
    percent     50%, 50 %, 25 percent, 25 per cent, fifty percent; the value is
                the percent number (25), never the fraction
    word        two to nineteen, the tens, compounds spaced or hyphenated
                (twenty-two, twenty two), hundred, thousand, million, billion,
                dozen, "a dozen", "half a dozen", "a hundred and twenty",
                "two and a half"
    multiplier  3x, 3X, 3 followed by the multiplication sign, 3-fold,
                threefold, tenfold, twice, doubled, tripled, quadrupled always;
                double, triple, quadruple (and -s, -ing) only before the, your,
                our, their, its, what, that, as or a number ("double the
                revenue", not "no double booking")
    ordinal     3rd, 1st, 22nd; third and up, twenty-first, the hundredth. A
                word ordinal that opens a sentence before a comma ("Third, we")
                is an enumerator and is not read.
    fraction    half, a half, a third, a quarter, an eighth, thirds, quarters,
                ... and "one third", "two thirds", "three quarters". A fraction
                word is read unless it follows a position or period word (first,
                second, last, final, other, this, next, previous, current,
                every, per, each), is hyphenated into a compound (half-price,
                half-hour), or is "half price". A cardinal one to nine with a
                denominator is always a fraction. The value is the percent
                number (33.3333 for a third).
    range       2-3, 2 to 3, en or em dash, $20-$30, 10-15%, 10-15k: one
                mention per end. A bare end takes the other end's money or
                percent ($30-35 is two money mentions, 30-35% two percents) and
                a magnitude on the second end scales the first; ends with no
                unit have the form "range".
    time        6pm, 6 p.m., 6:30 pm, 18:00, 6-7pm, 9am to 5pm, also after a
                label word ("Step 6pm"); the value is the hour on a 24-hour clock
    date        a year 1900-2100 after in, since, from, until, till, during,
                before, after, year, FY, a month name or Q1-Q4, and followed by
                the end, punctuation, a function word, a month name or "to" a
                second year ("in 2025, ...", "in 2025 the studio"); a month and
                day followed the same way, by an ordinal suffix, a time or a
                dash and another day ("May 12.", "May 12 at 6pm", "May 12-14");
                a year completing a day and month (Oct 31, 2025); a decade (the
                1990s); a day with a month name (31 Oct, the 3rd of March);
                2025-03-01, 31/10/2025. Otherwise the number is a count: "in
                2000 studios", "In May 12 members joined", and also "In 2025
                revenue grew" (the accepted cost).

What it does not count:
  - "one", "a", "an", "first", "second" on their own: articles and a unit of
    time before they are quantities.
  - a label (ruling 4): a bare number (digits, or a dotted exhibit number) right
    after a word from `labels.LABEL_WORDS`, capitalised ("Phase 2") or after a
    reference word ("in phase 2", "on page 7", "open page 7"). Further bare
    numbers join the label only through an unspaced dash ("Steps 1-3"), or,
    after a plural label, through and, to, & or a comma ("Phases 1, 2 and 3");
    each must end the phrase (end of text, punctuation, a closing bracket, or
    another joiner). A number word is a label only when it is one bare word that
    ends the phrase the same way ("Phase two", not "Phase twelve weeks").
    Anything else is read: "Phase 1 - 6 weeks", "Phase 2 and 12 weeks".
  - a numbered list marker at the start of a line ("1. ", "2) "): structure.
  - identifiers that start with letters (Q3, M3-A, B2B, FY2025, v2.1, model_5),
    capitals, a hyphen and digits (CF-04), dotted chains of three or more parts
    (3.2.1).
  - vague plurals (hundreds, dozens).
A month name is a proper noun and is read only capitalised ("May 3", not "may 3").
A unit glued to a number stays out of the mention: "8hrs" is the mention "8".
Markdown emphasis does not hide a number: "**5**", "__5__", "_50%_".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.figures.labels import LABEL_WORDS, TECH_NAMES
from app.figures.model import FigureSet

Form = Literal["digit", "money", "percent", "word", "multiplier", "ordinal", "fraction", "range", "time",
               "date"]
Label = Literal["singular", "plural"]


@dataclass(frozen=True)
class Mention:
    """One number as written: the exact text, where it sits, its value, and its form."""
    text: str
    start: int
    end: int
    value: Decimal
    form: Form


# -- the grammar -----------------------------------------------------------------------

_SPACES = " \t\u00a0"            # a space inside one phrase; never a line break
_SP = f"[{_SPACES}]"

# Currency signs (dollar, euro, pound, yen, rupee), before or after a number, and
# the currency codes the reader knows. The codes are the one list: money mentions
# match figures in these units (see `supported`).
_SIGNS = "$\u20ac\u00a3\u00a5\u20b9"
_SIGN = f"[{_SIGNS}]"
_CURRENCY_CODES: tuple[str, ...] = (
    "USD", "EUR", "GBP", "AUD", "CAD", "CHF", "JPY", "CNY", "INR", "SGD", "AED", "SAR", "ZAR",
    "NZD", "SEK", "NOK", "DKK", "HKD", "MXN", "BRL", "PLN", "TRY", "KRW", "THB", "IDR", "MYR",
    "CZK", "HUF", "ILS", "EGP", "NGN", "KES", "PKR", "VND", "TWD", "RUB", "UAH", "QAR",
    "KWD", "BHD", "OMR",
    "Rs", "R", "RM", "Dh", "kr", "Kr",          # local prefixes: rupee, rand, ringgit, dirham, krona/krone
)
_CODE = "(?:" + "|".join(sorted(_CURRENCY_CODES, key=len, reverse=True)) + ")"   # RM before R
# The short local prefixes also name things ("Risk R1", "Room R2"): before a single
# digit they are an identifier; before two or more digits, money ("R80", "RM45").
# An ISO code before any number is money ("GBP5").
_LOCAL_PREFIXES = frozenset({"Rs", "R", "RM", "Dh", "kr", "Kr"})
_CUR = rf"(?:[A-Z]{{1,3}}\$|{_SIGN})"          # $, US$ / A$ style, the other signs
# Thousands in groups of three, by comma or by one kind of space (a space, a thin
# space, a no-break space, a narrow no-break space); a point only with a digit
# after it, so the full stop that ends a sentence is never read as a decimal point.
_GROUPS = "|".join(rf"\d{{1,3}}(?:{sep}\d{{3}})+(?!\d)" for sep in (",", " ", "\u2009", "\u00a0", "\u202f"))
_NUM = rf"(?:(?:{_GROUPS}|\d+)(?:\.\d+)?|\.\d+)"
_GROUP_SEPARATORS = str.maketrans("", "", ", \u2009\u00a0\u202f")

_HEAD = re.compile(
    rf"(?P<sign>[-\u2212](?=[\d.{_SIGNS}]))?"
    rf"(?:(?P<cur>{_CUR}){_SP}?|(?P<code>{_CODE})\.?{_SP}?)?"
    rf"(?P<num>{_NUM})")
_MAG_LETTER = re.compile(r"(?P<m>MM|mn|bn|[kK]|M|B|m)(?![A-Za-z0-9])")
_MAG_WORD = re.compile(rf"{_SP}+(?P<w>thousand|million|billion|dozen)(?![A-Za-z])", re.I)
_PCT = re.compile(rf"{_SP}?%|{_SP}*(?:per{_SP}?cent|percentage{_SP}+points?)(?![A-Za-z])", re.I)
_TIMES = re.compile(rf"[xX](?![A-Za-z0-9])|{_SP}?\u00d7")
_FOLD = re.compile(r"-?fold(?![A-Za-z])", re.I)
_ORD = re.compile(r"(?:st|nd|rd|th)(?![A-Za-z0-9])", re.I)
# a currency after the number: a code, a sign (40$, 40 euro sign) not opening the next amount, or a word
_MONEY_AFTER = re.compile(
    rf"{_SP}?{_CODE}(?![A-Za-z])|{_SP}?{_SIGN}(?!{_SP}?[\d.])|{_SP}+(?i:dollars?|euros?)(?![A-Za-z])")
_TO = re.compile(rf"{_SP}*[-\u2013\u2014]{_SP}*|{_SP}+to{_SP}+")
_CHAIN = re.compile(r"\d+(?:\.\d+){2,}(?!\d)")

_MAGNITUDE = {"k": 1000, "K": 1000, "M": 10**6, "m": 10**6, "MM": 10**6, "mn": 10**6,
              "B": 10**9, "bn": 10**9, "thousand": 1000, "million": 10**6, "billion": 10**9, "dozen": 12}
# 5m is five metres or minutes, 70B a model size: these scale only with a currency
_NEEDS_CURRENCY = frozenset({"m", "MM", "mn", "B", "bn"})

# clock times: "p.m." keeps its own final point, "6pm." leaves the full stop alone
_MER = rf"(?:\.{_SP}?m\.|{_SP}?m)(?![A-Za-z])"
_TIME_RANGE = re.compile(
    rf"(?P<h1>\d{{1,2}})(?:[:.](?P<m1>[0-5]\d))?(?:{_SP}*[-\u2013]{_SP}*|{_SP}+to{_SP}+)"
    rf"(?P<h2>\d{{1,2}})(?:[:.](?P<m2>[0-5]\d))?{_SP}?(?P<ap>[ap]){_MER}", re.I)
_TIME_12 = re.compile(rf"(?P<h>\d{{1,2}})(?:[:.](?P<mi>[0-5]\d))?{_SP}?(?P<ap>[ap]){_MER}", re.I)
_TIME_24 = re.compile(r"(?P<h>[01]?\d|2[0-3]):(?P<mi>[0-5]\d)(?![\d:])")
# A colon pair without am/pm. A ratio cue (ratio, split, mix, odds, staffing, a
# "staff-to-client" compound) in the four words before it, or right after it,
# makes it a ratio. Otherwise it is a clock time when its minutes are 00, 15, 30 or
# 45, its hour is zero-led (09:10), a time word stands before it, or a time stands
# at the other end of a range ("9:05 to 17:00"); any other pair is a ratio and both
# sides are numbers ("1:12", "after 1:12 became standard").
# A ratio or a duration or score is not a clock time: these words near a colon
# pair, or a "teacher:student" compound, make both sides numbers.
_RATIO_CUES = frozenset({"ratio", "ratios", "split", "splits", "mix", "odds", "staffing", "average", "length",
                         "duration", "wait", "lap", "pace", "score", "call", "calls", "runtime"})
_CUE_WORD = re.compile(r"[A-Za-z]+(?:[-:][A-Za-z]+)*")
_TIME_LEADS = frozenset({"at", "from", "until", "till", "between", "around", "by"})
_QUARTER_MINUTES = frozenset({"00", "15", "30", "45"})
_CLOCK_LINK = rf"(?:{_SP}*[-\u2013]{_SP}*|{_SP}+(?:to|and|until|till){_SP}+)"
_CLOCK_NEXT = re.compile(
    rf"{_CLOCK_LINK}(?:[01]?\d|2[0-3])(?::(?:00|15|30|45)(?!\d)|(?::[0-5]\d)?{_SP}?[ap]\.?{_SP}?m(?![A-Za-z]))",
    re.I)
_CLOCK_PREV = re.compile(rf"(?:[01]?\d|2[0-3]):[0-5]\d{_CLOCK_LINK}$")
_NOON = re.compile(rf"(?:12{_SP}*)?(?P<w>noon|midnight)(?![A-Za-z])", re.I)
# "9-5" and "9 to 5" are working hours, two clock times 9 and 17, only after open,
# opens, hours, shift or daily; otherwise they are numbers ("from 9 to 5 vans")
_NINE_TO_FIVE = re.compile(rf"9(?:{_SP}*[-\u2013]{_SP}*|{_SP}+to{_SP}+)(?P<five>5)(?![\d.,:%A-Za-z])")
_NINE_LEAD = re.compile(rf"(?:^|[^A-Za-z])(?i:open|opens|hours|shift|daily):?{_SP}+$")

# Idioms that hold digits but no quantity: the one closed list.
_IDIOMS: tuple[str, ...] = ("24/7", "24x7", "1-on-1", "one-on-one", "1:1", "one to one", "2FA", "3D", "B2B",
                            "B2C")
_IDIOM = re.compile("(?i:" + "|".join(re.escape(i) for i in _IDIOMS) + ")(?![A-Za-z0-9])")

# "x3": a lone x glued before a number is a multiplier ("grow revenue x3"); a
# longer identifier ("x86-64", "x2b") is not
_X_TIMES = re.compile(r"[xX](?P<n>\d+(?:\.\d+)?)(?![A-Za-z0-9_-]|\.\d)")

# the vulgar fractions, as percent numbers: "1\u00bd hours" is 1 and a half
_VULGAR_PARTS = (("\u00bd", 1, 2), ("\u00bc", 1, 4), ("\u00be", 3, 4), ("\u2150", 1, 7), ("\u2151", 1, 9),
                 ("\u2152", 1, 10), ("\u2153", 1, 3), ("\u2154", 2, 3), ("\u2155", 1, 5), ("\u2156", 2, 5),
                 ("\u2157", 3, 5), ("\u2158", 4, 5), ("\u2159", 1, 6), ("\u215a", 5, 6), ("\u215b", 1, 8),
                 ("\u215c", 3, 8), ("\u215d", 5, 8), ("\u215e", 7, 8))
_VULGAR = {c: (n, d) for c, n, d in _VULGAR_PARTS}

# dates: month names are proper nouns, so only capitalised ones are read
_MONTHS = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?"
           r"|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)")
_YEAR = r"(?:19\d\d|20\d\d|2100)(?!\d)"
# a possessive month owns something, so the number before it is a count: "5 of April's members"
_DAY_MONTH = re.compile(
    rf"(?P<d>\d{{1,2}})(?:st|nd|rd|th)?(?:{_SP}+of)?{_SP}+(?P<mon>{_MONTHS})(?![A-Za-z]|['\u2019]s(?![A-Za-z]))")
_MONTH_DAY = re.compile(
    rf"(?P<mon>{_MONTHS})\.?{_SP}+(?P<d>\d{{1,2}})(?P<suf>st|nd|rd|th)?(?![A-Za-z0-9%]|[.:]\d)")
# the second day of a pair or span: "Dec 24 and 25", "Mar 3-7", "Dec 24 to Jan 2"
_MD_SECOND = re.compile(
    rf"(?:{_SP}*[-\u2013]{_SP}*|{_SP}+(?:and|or|to|until|till|through){_SP}+)(?:(?P<mon>{_MONTHS})\.?{_SP}+)?"
    rf"(?P<d>\d{{1,2}})(?:st|nd|rd|th)?(?![A-Za-z0-9%]|[.:,]\d)")
# the days in each month (February at its longest), so "Feb 31" is not a date
_MONTH_DAYS = {"jan": 31, "feb": 29, "mar": 31, "apr": 30, "may": 31, "jun": 30, "jul": 31, "aug": 31,
               "sep": 30, "oct": 31, "nov": 30, "dec": 31}
# Two or more month-day pairs in a comma or semicolon list are a monthly series of
# counts ("New members: Jan 12, Feb 14, Mar 18."), not dates.
_MD_UNIT = rf"(?:{_MONTHS}\.?{_SP}+\d{{1,2}}|\d{{1,2}}{_SP}+{_MONTHS})(?![A-Za-z0-9])"
# A strong separator (comma, semicolon, bar, slash) makes a series on its own. A
# weak one ("and", a spaced dash) joins a series only when the list has three
# items or a colon or dash introduces it ("New members: Jan 12 and Feb 14"), so
# "Closed Dec 24 - Jan 2." stays a date range.
_SER_STRONG = rf"(?:{_SP}*[,;|/]{_SP}*|{_SP}+)"     # juxtaposed pairs too: "Jan 12 Feb 14 Mar 18"
_SER_WEAK = rf"(?:,?{_SP}+and{_SP}+|{_SP}+[-\u2013]{_SP}+)"
_SER_ANY = rf"(?:{_SER_STRONG}|{_SER_WEAK})"
_SER_INTRO = rf"(?::|{_SP}[-\u2013]){_SP}*$"
_SERIES_NEXT = re.compile(rf"{_SER_STRONG}{_MD_UNIT}")
_SERIES_PREV = re.compile(rf"{_MD_UNIT}{_SER_STRONG}$")
_SERIES_NEXT_WEAK = re.compile(rf"{_SER_WEAK}{_MD_UNIT}")
_SERIES_NEXT_THREE = re.compile(rf"{_SER_WEAK}{_MD_UNIT}{_SER_ANY}{_MD_UNIT}")
_SERIES_PREV_ANY = re.compile(rf"{_MD_UNIT}{_SER_ANY}$")
_SERIES_PREV_INTRO = re.compile(_SER_INTRO)
_SERIES_PREV_WEAK_LIST = re.compile(rf"(?:{_MD_UNIT}{_SER_ANY}|{_SER_INTRO[:-1]}){_MD_UNIT}{_SER_WEAK}$")
_ISO_DATE = re.compile(r"(?P<y>19\d\d|20\d\d|2100)-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])(?!\d)")
# numeric dates need a four-digit year: 31/10/2025, 10/31/2025, 31-10-2025, 2025/10/31.
# "5/10/20 class packs" and "5/10" are numbers.
_SLASH_DATE = re.compile(r"(?P<d>\d{1,2})(?P<s>[/-])(?P<e>\d{1,2})(?P=s)(?:19\d\d|20\d\d|2100)(?![\d/-]?\d)")
_YEAR_FIRST_DATE = re.compile(r"(?P<y>19\d\d|20\d\d|2100)/(?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12]\d|3[01])(?![\d/])")
# the year that completes a date may end a clause ("On 3 March 2026, we start")
_YEAR_AFTER_DATE = re.compile(rf",?{_SP}+(?P<y>19\d\d|20\d\d|2100)(?![\d%A-Za-z]|[.,]\d)")

# What may follow a date so that it reads as one: the end, punctuation, or a
# function word. Any other word after "May 12" or "in 2000" makes it a count.
_FUNCTION_WORDS = (
    "a", "an", "the", "we", "our", "i", "you", "they", "he", "she", "it", "and", "or", "but", "at", "on",
    "in", "to", "from", "until", "till", "through", "by", "for", "with", "as", "is", "was", "were", "are",
    "will", "would", "has", "have", "had", "of", "that", "which", "who",
)
_FUNCTION = "(?i:" + "|".join(sorted(_FUNCTION_WORDS, key=len, reverse=True)) + r")(?![A-Za-z])"
_ENDS = rf"{_SP}*(?:[\r\n]|$)|[.!?;:,)\]]"
# After a date the narrower list: words that also follow counts ("May 12 to 15 new
# members", "12 of our 40", "12 were lost") make the number a count.
_DATE_WORDS = (
    "at", "on", "in", "from", "until", "till", "through", "by", "for", "with", "as", "is", "was", "has",
    "we", "our", "i", "you", "they", "he", "she", "it", "the", "a", "an", "that", "which", "who",
)
_DATE_WORD = "(?i:" + "|".join(sorted(_DATE_WORDS, key=len, reverse=True)) + r")(?![A-Za-z])"
_DATE_END = re.compile(
    rf"{_ENDS}|{_SP}+{_DATE_WORD}|{_SP}+\d{{1,2}}(?:[:.][0-5]\d)?{_SP}?[ap]\.?{_SP}?m(?![A-Za-z])"
    rf"|{_SP}+(?:[01]?\d|2[0-3]):[0-5]\d")
_CLAUSE_END = re.compile(_ENDS)
# nouns a year qualifies ("the 2025 plan", "FY 2025 revenue"); any other noun after a
# year-shaped number makes it a count ("growth of 2000 members")
# A count noun (sales, members) or a generic word (a, the, for) after it makes the
# number a count; so the year continuation drops those from the date words.
_YEAR_NOUNS = ("plan", "plans", "budget", "budgets", "season", "report", "reports", "cohort", "revenue",
               "forecast", "target", "targets", "results", "accounts", "campaign", "intake",
               "goal", "goals", "review", "roadmap", "strategy", "figures")
_YEAR_DATE_WORD = ("(?i:" + "|".join(w for w in _DATE_WORDS if w not in ("a", "an", "the", "for"))
                   + r")(?![A-Za-z])")
_YEAR_FOLLOW = re.compile(
    rf"{_ENDS}|{_SP}+{_YEAR_DATE_WORD}|{_SP}+{_MONTHS}(?![A-Za-z])|(?:{_SP}+to{_SP}+|{_SP}*[-\u2013]{_SP}*){_YEAR}"
    rf"|{_SP}+(?i:{'|'.join(_YEAR_NOUNS)})(?![A-Za-z])")
# after "from" a year needs its other end: "from 2020 to 2024", "from 2020 until May 2024"
_FROM_YEAR = re.compile(rf"{_SP}+(?:to|until|till){_SP}+(?:{_MONTHS}{_SP}+)?{_YEAR}")

# A bare range end takes the other end's money or percent only when no noun of its
# own follows it: the end, punctuation, a function word, or a rate ("$20-30 a class",
# "per class", "each week").
_BARE_END = re.compile(rf"{_ENDS}|{_SP}+{_FUNCTION}|{_SP}+(?i:per|each|every)(?![A-Za-z])")

# the words after which a 1900-2100 number may be a year
# by, of, for, over, the and through lead amounts as often as years ("a budget of
# 2000", "grow by 2000"), so they do not make a year
_YEAR_WORDS = frozenset({"in", "since", "from", "until", "till", "during", "before", "after", "year", "fy",
                         "early", "late", "mid"})
_MONTH_WORD = re.compile(_MONTHS)
_QUARTER = re.compile(r"[Qq][1-4]")
_BEFORE_YEAR = re.compile(rf"(?P<w>[A-Za-z0-9]+)(?:[.,]?{_SP}+|-)$")     # "in 2025", "mid-2025"

# identifiers that start with letters, not quantities: Q3, M3-A, B2B, FY2025, v2.1; CF-04, ISO-9001
_IDENT = re.compile(r"[A-Za-z]+\d[A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)*|[A-Z]{1,6}-\d[A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)*")

_WORD = re.compile(r"[A-Za-z]+")
_JOIN = re.compile(rf"{_SP}+|-(?=[A-Za-z])")

# labels (ruling 4). A lower-case label word is a label only after a word that
# refers to it ("in phase 2", "on page 7"); "book a table 4 times" is a count.
# "go to page 7" and "turn to page 7" are covered by "to".
_LABELS = frozenset(w.lower() for w in LABEL_WORDS)
_LABEL_LEADS = frozenset({"see", "in", "of", "to", "from", "during", "before", "after", "until",
                          "through", "at", "per", "on", "open"})
_LABEL_ITEM = re.compile(r"\d+(?:\.\d+)*")
_DASH_JOIN = r"[-\u2013](?=\d)"          # unspaced: "Steps 1-3"; a spaced dash separates
_LABEL_JOIN = re.compile(_DASH_JOIN)
_LABEL_JOIN_PLURAL = re.compile(
    rf"{_DASH_JOIN}|{_SP}*,{_SP}*(?:(?:and|&){_SP}+)?|{_SP}*&{_SP}*|{_SP}+(?:and|to){_SP}+")
# What may follow a listed label number: the end, punctuation, a bracket, a joiner,
# a spaced dash before a heading word ("### Week 1-2 - Setup"), a function word, or
# a verb that says what the numbered things do ("Weeks 1-4 are setup", "Phases
# 2-3 take 10 weeks"). A unit noun ("Phases 2 and 3 weeks") makes it a quantity.
_LABEL_VERBS = ("is", "are", "was", "were", "will", "run", "runs", "take", "takes", "cost", "costs",
                "start", "starts", "end", "ends", "begin", "begins", "last", "lasts", "cover", "covers",
                "include", "includes", "focus", "focuses", "handle", "handles", "deliver", "delivers",
                "build", "builds", "set", "sets", "need", "needs")
_ITEM_END = re.compile(
    rf"[.!?;:](?!\d)|[)\]}}]|{_SP}*(?:[\r\n]|$)|{_SP}+(?:and|to)(?![A-Za-z])|{_SP}*[,&](?!\d)|{_DASH_JOIN}"
    rf"|{_SP}+[-\u2013\u2014]{_SP}+(?=[A-Za-z])|{_SP}+{_FUNCTION}|{_SP}+(?i:{'|'.join(_LABEL_VERBS)})(?![A-Za-z])")
# a number word after a label is a label when it ends the phrase the same way
_WORD_LABEL_END = _ITEM_END

# a numbered list marker: digits, then "." or ")", then a space, first on its line
_LIST_MARKER = re.compile(rf"\d+[.)]{_SP}")
# a markdown heading's own number ("## 2. Diagnosis", "### 3.1 Plan") is structure too
_HEADING_LEAD = re.compile(rf"(?:^|[\r\n]){_SP}*#{{1,6}}{_SP}+$")
# ... when it is numbered like a section: "2.", "2)", "3:", "3.1". A bare number is
# read ("## 3 Quick Wins", and "# 1 Intro" as a false flag).
_HEADING_NUMBER = re.compile(rf"(?:\d+(?:\.\d+)+\.?|\d+[.):])(?={_SP}|[\r\n]|$)")

# technical names whose number is part of the name ("ISO 27001", "TLS 1.3")
_TECH = frozenset(TECH_NAMES)
_TECH_ITEM = re.compile(r"\d+(?:[.:]\d+)*")
_TOKEN_EDGE = "([{\"'*_"

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

# Multiplier words are read in every use, verbs included ("bookings will double"),
# except in a hyphenated compound ("double-check") or right before a noun they
# only describe ("double booking", "a triple room").
_MULT_WORDS = {
    "twice": 2, "thrice": 3,
    **{f"double{s}": 2 for s in ("", "s", "d")}, "doubling": 2,
    **{f"triple{s}": 3 for s in ("", "s", "d")}, "tripling": 3,
    **{f"quadruple{s}": 4 for s in ("", "s", "d")}, "quadrupling": 4,
    **{w: Decimal("0.5") for w in ("halve", "halved", "halving", "halves")},   # "churn halved"
}
# after "to" or a modal the word is a verb, and the noun after it is its object:
# "aim to triple bookings", "will double bookings"
_MULT_VERB_LEADS = frozenset({"to", "will", "would", "could", "can", "should", "may", "might", "must"})
_MULT_MODIFIES = re.compile(
    rf"{_SP}+(?i:bookings?|checks?|rooms?|shifts?|beds?|clicks?|entry|glazing|major|standard|agents?"
    rf"|take|vision|space)(?![A-Za-z])")

# decades: "in their thirties" reads like "30s"
_DECADES = {"twenties": 20, "thirties": 30, "forties": 40, "fifties": 50, "sixties": 60,
            "seventies": 70, "eighties": 80, "nineties": 90}

# Positions on the plan's own time axis ("Week 6", "Weeks 1-4", "by Day 30") are
# dates: capitalised, or lower case after a reference word.
_POSITIONS = frozenset({"week", "month", "day", "year", "quarter"})
_POSITION_LEADS = frozenset({"see", "in", "by", "from", "until", "of", "to", "during", "before", "after",
                             "at", "on"})
_FOLD_PREFIX = {**_UNITS, **_TEENS, **_TENS, "hundred": 100, "thousand": 1000}

# fractions
_DENOMINATORS = {"half": 2, "third": 3, "quarter": 4, "fourth": 4, "fifth": 5, "sixth": 6,
                 "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10}
_DENOMINATORS_MANY = {"halves": 2, "thirds": 3, "quarters": 4, "fourths": 4, "fifths": 5, "sixths": 6,
                      "sevenths": 7, "eighths": 8, "ninths": 9, "tenths": 10}
# after a position or period word a fraction word names a part of a period, not a share
_FRACTION_NOT_AFTER = frozenset({"first", "second", "last", "final", "other", "this", "next", "previous",
                                 "current", "every", "per", "each"})
# after a rank word a bare fraction word is a share: "the top quarter", "bottom fifth"
_RANK_WORDS = frozenset({"top", "bottom", "upper", "lower", "best", "worst", "weakest", "strongest",
                         "highest", "lowest", "biggest", "smallest"})
# "a third" before a noun is an order ("a third hygienist"); it is a share before
# "of", at the end of a clause, or after one of these ("cut by a third")
_FRACTION_PREPS = frozenset({"by", "in", "into", "than", "over", "under", "about", "around", "nearly",
                             "almost"})
_FRACTION_OF = re.compile(rf"{_SP}+of(?![A-Za-z])", re.I)
_COMPOUND = re.compile(r"-[A-Za-z]")                       # half-price, half-hour
_HALF_PRICE = re.compile(rf"{_SP}+price(?![A-Za-z])", re.I)
_PERCENT_PLACES = Decimal("0.0001")


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
    q = _Qty(start=pos, end=m.end(), value=Decimal(num.translate(_GROUP_SEPARATORS)),
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
    after = _MONEY_AFTER.match(text, q.end) if not q.money else None
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
    code = m.group("code")
    if code:
        one_digit = num.isdigit() and len(num) == 1 and q.scale == 1
        if (text[q.end:q.end + 1].isalpha()                   # "CAD 3D": the number is not an amount
                or (code in _LOCAL_PREFIXES and one_digit)):    # "R1", "Room R2": an identifier
            return None
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


def _word_before(text: str, start: int) -> tuple[str, int]:
    """The word that ends right before `start` (after spaces), and where it starts;
    ("", start) when spaces lead to anything but a word, or to nothing. Callers
    use it once per mention, so its walk over one word is not repeated."""
    j = start
    while j > 0 and text[j - 1] in _SPACES:
        j -= 1
    if j == start:
        return "", start
    k = j
    while k > 0 and text[k - 1].isalpha():
        k -= 1
    return text[k:j], k


def _after_word(text: str, start: int, words: frozenset[str], leads: frozenset[str]) -> Label | None:
    """Whether the number at `start` follows one of `words`, and in which number:
    "Phase 2" is singular, "Phases 1-2" plural, anything else None. A lower-case
    word counts only after one of `leads` ("in phase 2", "by week 6")."""
    word, k = _word_before(text, start)
    lower = word.lower()
    if lower in words:
        label: Label = "singular"
    elif lower.endswith("s") and lower[:-1] in words:
        label = "plural"
    else:
        return None
    if word[0].isupper() or _word_before(text, k)[0].lower() in leads:
        return label
    return None


def _after_label(text: str, start: int) -> Label | None:
    return _after_word(text, start, _LABELS, _LABEL_LEADS)


def _listed(text: str, end: int, label: Label) -> list[tuple[int, int]]:
    """The bare numbers listed after the first one a label started, as spans:
    "Phases 1, 2 and 3" lists 2 and 3."""
    join = _LABEL_JOIN_PLURAL if label == "plural" else _LABEL_JOIN
    items = []
    while (j := join.match(text, end)):
        item = _LABEL_ITEM.match(text, j.end())
        if not item or not _ITEM_END.match(text, item.end()):
            break
        items.append(item.span())
        end = item.end()
    return items


def _bare_first(text: str, pos: int) -> re.Match | None:
    """The first number after a label or a plan position, when it is bare: plain
    digits or a dotted exhibit number, carrying no unit ("Phase 2,000" and "Step
    3 40%" are quantities). A number of two or more digits must also end the
    phrase as a listed item does or meet a function word: "Phase 12 weeks" is a
    quantity, "Phase 12 is next" a label. A single digit or a dotted number is a
    label before any word ("Phase 2 starts", "Exhibit 2.1 shows")."""
    item = _LABEL_ITEM.match(text, pos)
    q = _quantity(text, pos) if item else None
    if (q is None or q.end > item.end() or q.scale != 1
            or q.signed or q.money or q.percent or q.times or q.ordinal):
        return None
    if item.end() - pos > 1 and "." not in item.group() and not _WORD_LABEL_END.match(text, item.end()):
        return None
    return item


def _read_label(text: str, pos: int) -> Read | None:
    """A bare number after a label word, and the bare numbers listed with it."""
    label = _after_label(text, pos)
    item = _bare_first(text, pos) if label else None
    if not item:
        return None
    listed = _listed(text, item.end(), label)
    return (listed[-1][1] if listed else item.end()), []


def _token_before(text: str, start: int) -> str:
    """The token (letters, digits, dots, hyphens) right before `start` after
    spaces, as written, without brackets or emphasis; "" when there is none or
    it is longer than any technical name. The walk is bounded."""
    j = start
    while j > 0 and text[j - 1] in _SPACES:
        j -= 1
    if j == start:
        return ""
    k, limit = j, max(0, j - 24)
    while k > limit and not text[k - 1].isspace():
        k -= 1
    if k == limit and k > 0 and not text[k - 1].isspace():
        return ""
    return text[k:j].strip(_TOKEN_EDGE)


def _read_tech(text: str, pos: int) -> Read | None:
    """The number or version right after a technical name: part of the name."""
    item = _TECH_ITEM.match(text, pos) if _token_before(text, pos) in _TECH else None
    if not item:
        return None
    q = _quantity(text, pos)
    if q is None or q.end > item.end() or q.scale != 1 or q.money or q.percent or q.times or q.ordinal:
        return None   # "ISO 27001 costs ..." is fine; "React 19%" is a quantity
    to = _TO.match(text, item.end())
    if to and text[to.end():to.end() + 1].isdigit():
        return None   # "Office 9 to 5": a range, not a version
    return item.end(), []


def _read_position(text: str, pos: int) -> Read | None:
    """A position on the plan's own time axis ("Week 6", "Weeks 1-4", "by Day
    30"): each bare number is a date. A quantity after it is still read."""
    label = _after_word(text, pos, _POSITIONS, _POSITION_LEADS)
    item = _bare_first(text, pos) if label else None
    if not item:
        return None
    spans = [item.span(), *_listed(text, item.end(), label)]
    # a dotted position ("Week 2.1.3") keeps its first two parts as its value
    return spans[-1][1], [_mention(text, s, e, Decimal(".".join(text[s:e].split(".")[:2])), "date")
                          for s, e in spans]


def _year_number(q: _Qty) -> bool:
    return q.plain and q.end - q.start == 4 and 1900 <= q.value <= 2100


def _year_shaped(q: _Qty, text: str) -> bool:
    return _year_number(q) and not text[q.end:q.end + 1].isalpha()


def _year_context(text: str, start: int) -> str | None:
    """The word before `start` when it may make a 1900-2100 number a year (in
    2025, since 2019, FY 2025, May 2026, Q3 2025, mid-2025), in lower case; None
    otherwise."""
    m = _BEFORE_YEAR.search(text, max(0, start - 40), start)
    if not m or (m.start() > 0 and text[m.start() - 1].isalnum()):
        return None
    word = m.group("w")
    if word.lower() in _YEAR_WORDS or _MONTH_WORD.fullmatch(word) or _QUARTER.fullmatch(word):
        return word.lower()
    return None


def _is_year(q: _Qty, text: str) -> bool:
    """A year: shaped like one, after a word that makes it one, and followed by
    the end, punctuation, a date word, a month, a noun a year qualifies ("the 2025
    plan") or "to" a second year. After "from" it needs its other end ("from 2020
    to 2024"). "in 2000 studios" and "up from 1980 in 2024" hold counts."""
    if not _year_shaped(q, text):
        return False
    lead = _year_context(text, q.start)
    if lead is None or not _YEAR_FOLLOW.match(text, q.end):
        return False
    return lead != "from" or bool(_FROM_YEAR.match(text, q.end))


def _line_start(text: str, pos: int) -> bool:
    """True when only spaces stand between the start of the line and `pos`."""
    i = pos
    while i > 0 and text[i - 1] in _SPACES:
        i -= 1
    return i == 0 or text[i - 1] in "\r\n"


def _sentence_start(text: str, pos: int) -> bool:
    """True when `pos` opens a sentence: the start of the text or a line, or after
    a full stop, question or exclamation mark and a space."""
    i = pos
    while i > 0 and text[i - 1] in _SPACES:
        i -= 1
    return i == 0 or text[i - 1] in "\r\n" or (i < pos and text[i - 1] in ".!?")


def _percent_of(numerator: int, denominator: int) -> Decimal:
    """numerator/denominator as a percent number, exact to four places: 33.3333."""
    value = (Decimal(numerator) * 100 / Decimal(denominator)).quantize(_PERCENT_PLACES)
    return value.quantize(Decimal(1)) if value == value.to_integral_value() else value.normalize()


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
        h1, h2 = int(m.group("h1")), int(m.group("h2"))
        second = _hour24(h2, ap)
        first = _hour24(h1, ap)
        if ap.lower() == "a" and h2 == 12 and h1 < 12:   # 10-12am is ten in the morning to noon
            first, second = h1, 12
        elif first > second:   # 11-1pm is 11am to 1pm
            first = _hour24(h1, "a" if ap.lower() == "p" else "p")
        end1 = m.end("m1") if m.group("m1") else m.end("h1")
        return m.end(), [_mention(text, pos, end1, first, "time"),
                         _mention(text, m.start("h2"), m.end(), second, "time")]
    m = _TIME_12.match(text, pos)
    if m and 1 <= int(m.group("h")) <= 12:
        return m.end(), [_mention(text, pos, m.end(), _hour24(int(m.group("h")), m.group("ap")), "time")]
    m = _TIME_24.match(text, pos)
    if m and _clock(text, pos, m):
        return m.end(), [_mention(text, pos, m.end(), int(m.group("h")), "time")]
    m = _NINE_TO_FIVE.match(text, pos)
    if m and _NINE_LEAD.search(text, max(0, pos - 12), pos):   # "open 9-5": working hours
        return m.end(), [_mention(text, pos, pos + 1, 9, "time"), _mention(text, m.start("five"), m.end(), 17, "time")]
    m = _NOON.match(text, pos)
    if m:
        return m.end(), [_mention(text, pos, m.end(), 12 if m.group("w").lower() == "noon" else 0, "time")]
    return None   # a colon pattern that is not a time is a ratio: both sides are read


def _ratio_cue(text: str, start: int, end: int) -> bool:
    """A ratio word in the four words before a colon pair or the word right after it."""
    before = _CUE_WORD.findall(text, max(0, start - 60), start)[-4:]
    after = _CUE_WORD.match(text, end + 1) if text[end:end + 1] in _SPACES and end < len(text) else None
    words = [w.lower() for w in before] + ([after.group().lower()] if after else [])
    return any(w in _RATIO_CUES or "-to-" in w for w in words)


def _clock(text: str, pos: int, m: re.Match) -> bool:
    """Whether a colon pair without am/pm is a clock time (see `_RATIO_CUES`)."""
    if _ratio_cue(text, pos, m.end()):
        return False
    hour, minutes = m.group("h"), m.group("mi")
    # quarter minutes alone make a time from 6 on: "1:15" and "4:30" with nothing
    # else are ratios or durations ("Mat classes are 1:15", "4:30 average")
    return ((minutes in _QUARTER_MINUTES and 6 <= int(hour) <= 23)
            or (len(hour) == 2 and hour[0] == "0")
            or _word_before(text, pos)[0].lower() in _TIME_LEADS
            or bool(_CLOCK_NEXT.match(text, m.end()))
            or bool(_CLOCK_PREV.search(text, max(0, pos - 20), pos)))


def _valid_day(month: str, day: int) -> bool:
    return 1 <= day <= _MONTH_DAYS[month[:3].lower()]


def _in_series(text: str, start: int, end: int) -> bool:
    """Whether a month-day pair sits in a list of them (a monthly series of counts):
    next to a strong separator; first of three weakly joined; in the middle; or
    last after a list or an introducing colon ("Jan 12, Feb 14 and Mar 18")."""
    if _SERIES_NEXT.match(text, end) or _SERIES_PREV.search(text, max(0, start - 30), start):
        return True
    if _SERIES_NEXT_WEAK.match(text, end):
        if (_SERIES_NEXT_THREE.match(text, end) or _SERIES_PREV_ANY.search(text, max(0, start - 30), start)
                or _SERIES_PREV_INTRO.search(text, max(0, start - 8), start)):
            return True
    return bool(_SERIES_PREV_WEAK_LIST.search(text, max(0, start - 80), start))


def _day_and_year(text: str, pos: int, m: re.Match) -> Read:
    """A day with its month, and the year that completes it ("Oct 31, 2025")."""
    found = [_mention(text, pos, m.end(), int(m.group("d")), "date")]
    year = _YEAR_AFTER_DATE.match(text, m.end())
    if year:
        found.append(_mention(text, year.start("y"), year.end("y"), int(year.group("y")), "date"))
        return year.end(), found
    return m.end(), found


def _read_date(text: str, pos: int) -> Read | None:
    m = _ISO_DATE.match(text, pos)
    if m:
        return m.end(), [_mention(text, pos, m.end(), int(m.group("y")), "date")]
    m = _YEAR_FIRST_DATE.match(text, pos)
    if m:
        return m.end(), [_mention(text, pos, m.end(), int(m.group("y")), "date")]
    m = _SLASH_DATE.match(text, pos)
    if m and 1 <= int(m.group("d")) <= 31 and 1 <= int(m.group("e")) <= 31:
        return m.end(), [_mention(text, pos, m.end(), int(m.group("d")), "date")]
    # "31 Oct", "on 12 December we opened", "12 December 2025" are dates; "4 December
    # parties", "Only 4 of March trials", "30 Feb" and a monthly series are counts
    m = _DAY_MONTH.match(text, pos)
    if (m and _valid_day(m.group("mon"), int(m.group("d"))) and not _in_series(text, pos, m.end())
            and (_DATE_END.match(text, m.end()) or _YEAR_AFTER_DATE.match(text, m.end()))):
        return _day_and_year(text, pos, m)
    return None


def _read_month_day(text: str, pos: int) -> Read | None:
    """"May 12" is a date when the day is real for the month and is followed by
    the end, punctuation, a date word (`_DATE_WORDS`), an ordinal suffix or a time.
    A pair or span ("Dec 24 and 25", "Mar 3-7", "Dec 24 to Jan 2") is two dates
    when its second part ends the same way (or takes a year). Otherwise the numbers
    are counts and are read: "In May 12 members joined", "May 10-15 new members",
    "Feb 30", and a monthly series ("Jan 12, Feb 14, Mar 18")."""
    m = _MONTH_DAY.match(text, pos)
    if not m:
        return None
    if not _valid_day(m.group("mon"), int(m.group("d"))) or _in_series(text, pos, m.end()):
        return m.start("d"), []
    second = _MD_SECOND.match(text, m.end())
    if second:
        month2 = second.group("mon") or m.group("mon")
        year = _YEAR_AFTER_DATE.match(text, second.end())
        if _valid_day(month2, int(second.group("d"))) and (year or _DATE_END.match(text, second.end())):
            start2 = second.start("mon") if second.group("mon") else second.start("d")
            found = [_mention(text, pos, m.end(), int(m.group("d")), "date"),
                     _mention(text, start2, second.end(), int(second.group("d")), "date")]
            if year:
                found.append(_mention(text, year.start("y"), year.end("y"), int(year.group("y")), "date"))
                return year.end(), found
            return second.end(), found
        if not second.group("mon"):
            return m.start("d"), []    # "May 12 to 15 new members": counts
    if not (m.group("suf") or _DATE_END.match(text, m.end())):
        return m.start("d"), []
    return _day_and_year(text, pos, m)


def _unit(q: _Qty) -> Form | None:
    return "money" if q.money else "percent" if q.percent else None


def _read_range(text: str, pos: int) -> Read | None:
    # when this is not a range, the first number is read once, here
    a = _quantity(text, pos)
    if a is None or a.times or a.ordinal:
        return _read_digits(text, pos, a)
    to = _TO.match(text, a.end)
    if not to or text[to.end():to.end() + 1] in ("-", "\u2212"):
        return _read_digits(text, pos, a)
    b = _quantity(text, to.end())
    if b is None or b.ordinal or b.signed:
        return _read_digits(text, pos, a)
    if (_year_shaped(a, text) and _year_context(text, a.start) and _year_shaped(b, text)
            and _YEAR_FOLLOW.match(text, b.end)):   # from 2025 to 2026: the second end follows the first
        return b.end, [_mention(text, a.start, a.end, a.value, "date"),
                       _mention(text, b.start, b.end, b.value, "date")]
    if b.scale != 1 and a.scale == 1:   # 10-15k is ten to fifteen thousand
        a.value *= b.scale
    # a bare end takes the other end's unit: $30-35 is money twice, 30-35% percent twice
    # ... but only when the shapes agree and a bare second end has no noun of its own:
    # "$45 to 12 instructors" and "5% to 40 members" are two numbers, not ranges, and
    # "by 10% to $22" joins a percent and a price. Then each end is read on its own.
    unit_a, unit_b = _unit(a), _unit(b)
    if (unit_a and unit_b and unit_a != unit_b) or (unit_a and not unit_b and not _BARE_END.match(text, b.end)):
        return _read_digits(text, pos)
    unit_a, unit_b = unit_a or unit_b, unit_b or unit_a
    plain_form: Form = "multiplier" if b.times else "range"
    return b.end, [_mention(text, a.start, a.end, a.value, unit_a or plain_form),
                   _mention(text, b.start, b.end, b.value, unit_b or plain_form)]


def _read_digits(text: str, pos: int, q: _Qty | None = None) -> Read | None:
    chain = _CHAIN.match(text, pos)
    if chain:   # 3.2.1 is a section or version, not a quantity
        return chain.end(), []
    q = q or _quantity(text, pos)
    if q is None:
        return None
    if _is_year(q, text):
        return q.end, [_mention(text, pos, q.end, q.value, "date")]
    if _year_number(q) and text[q.end:q.end + 1] == "s" and not text[q.end + 1:q.end + 2].isalpha():
        return q.end + 1, [_mention(text, pos, q.end + 1, q.value, "date")]   # the 1990s
    return q.end, [_mention(text, pos, q.end, q.value, _form(q))]


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
    after hundred or a scale and before a number word. "Hundredth" and
    "thousandth" stand alone too ("the hundredth member")."""
    n = len(words)

    def at(i: int) -> str | None:
        return words[i] if i < n else None

    total, group = Decimal(0), None
    last: str | None = None     # what the word before was
    hundred_here, last_scale, ordinal, k = False, None, False, 0
    if at(0) == "a" and at(1) in _AFTER_A:
        group, last, k = Decimal(1), "a", 1
    elif at(0) == "a" and at(1) == "half" and at(2) in _AFTER_A:   # a half dozen, a half million
        group, last, k = Decimal("0.5"), "a", 2
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
            if last is None and w == "hundredth":
                group, last, ordinal = Decimal(100), "hundred", True
            elif last not in ("unit", "teen", "tens", "a") or hundred_here:
                break
            else:
                group, last, hundred_here = group * 100, "hundred", True
                ordinal = w == "hundredth"
        elif w in _SCALES or w in _ORD_SCALES:
            scale = _SCALES.get(w) or _ORD_SCALES[w]
            if last is None and w in _ORD_SCALES:
                total, last, ordinal = Decimal(scale), "scale", True
            elif last not in ("unit", "teen", "tens", "hundred", "a") or (last_scale and scale >= last_scale):
                break
            else:
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
        # half of the last unit: "two and a half" 2.5, "a dozen and a half" 18,
        # "a million and a half" 1,500,000
        half = Decimal(6) if last == "dozen" else Decimal(last_scale) / 2 if last == "scale" else Decimal("0.5")
        value, k = value + half, k + 3
    if k == 1 and words[0] in _NOT_ALONE:
        return None
    return value, k, ordinal


def _read_fraction(text: str, pos: int, ws: list[tuple[str, int, int, bool]]) -> Read | None:
    """A fraction, read as the percent number. A cardinal one to nine with a
    denominator ("one third", "two thirds", "three quarters") always is one.
    "half", "a half", "a quarter" and a bare plural ("thirds") are one unless they
    follow a position or period word ("the first half", "every quarter"), are
    hyphenated into a compound ("half-price", "half-hour"), or are "half price".
    After a rank word any denominator is a share ("the top quarter", "bottom
    fifth"). "a third", "a fourth", ... before a noun are orders ("a third
    hygienist"): a share only before "of", at the end of a clause, or after a
    word like by, into or than ("cut by a third")."""
    first = ws[0][0]
    second = ws[1][0] if len(ws) > 1 else None
    lead = _word_before(text, pos)[0].lower()
    always = False
    if first in _UNITS and (second in _DENOMINATORS if first == "one" else second in _DENOMINATORS_MANY):
        numerator = _UNITS[first]
        denominator = _DENOMINATORS[second] if first == "one" else _DENOMINATORS_MANY[second]
        used, always = 2, True
    elif first in _DENOMINATORS and lead in _RANK_WORDS:   # the top quarter
        numerator, denominator, used = 1, _DENOMINATORS[first], 1
    elif first in ("a", "an") and second in _DENOMINATORS:
        numerator, denominator, used = 1, _DENOMINATORS[second], 2
        if second not in ("half", "quarter") and not (
                _FRACTION_OF.match(text, ws[1][2]) or _CLAUSE_END.match(text, ws[1][2])
                or lead in _FRACTION_PREPS):
            return None   # "a fourth van": an order, read as the ordinal
    elif first == "half":
        numerator, denominator, used = 1, 2, 1
    elif first in _DENOMINATORS_MANY:
        numerator, denominator, used = 1, _DENOMINATORS_MANY[first], 1
    else:
        return None
    end = ws[used - 1][2]
    if not always and (_COMPOUND.match(text, end)
                       or (first == "half" and _HALF_PRICE.match(text, end))
                       or _word_before(text, pos)[0].lower() in _FRACTION_NOT_AFTER):
        return None
    return end, [_mention(text, pos, end, _percent_of(numerator, denominator), "fraction")]


def _read_words(text: str, pos: int) -> Read | None:
    ws = _words_from(text, pos)
    if not ws:
        return None
    first, _, first_end, _ = ws[0]
    if first in _MULT_WORDS:
        # only double/triple/quadruple compounds are modifiers ("double-check");
        # "twice-weekly" is still a factor
        compound = len(ws) > 1 and ws[1][3] and first not in ("twice", "thrice")
        verb = _word_before(text, pos)[0].lower() in _MULT_VERB_LEADS
        if compound or (not verb and _MULT_MODIFIES.match(text, first_end)):   # double-check, double booking
            return first_end, []
        return first_end, [_mention(text, pos, first_end, _MULT_WORDS[first], "multiplier")]
    if first.endswith("fold") and first[:-4] in _FOLD_PREFIX:
        return first_end, [_mention(text, pos, first_end, _FOLD_PREFIX[first[:-4]], "multiplier")]
    if first in _DECADES:   # "in their thirties" reads like "30s"
        return first_end, [_mention(text, pos, first_end, _DECADES[first], "digit")]
    if first == "zero":
        return first_end, [_mention(text, pos, first_end, 0, "word")]
    if first in ("noon", "midnight"):
        return first_end, [_mention(text, pos, first_end, 12 if first == "noon" else 0, "time")]
    words = [w[0] for w in ws]
    # "half a dozen" and "a half million" are numbers; "a third of members" a fraction
    parsed = _phrase(words) if first == "half" or words[:2] == ["a", "half"] else None
    if parsed is None:
        fraction = _read_fraction(text, pos, ws)
        if fraction is not None:
            return fraction
        parsed = _phrase(words)
    if parsed is None:
        return None
    value, used, ordinal = parsed
    end = ws[used - 1][2]
    if ordinal:
        if _sentence_start(text, pos) and text[end:end + 1] == ",":   # "Third, we ...": an enumerator
            return end, []
        return end, [_mention(text, pos, end, value, "ordinal")]
    if used < len(ws) and ws[used][0] == "fold":   # three-fold
        return ws[used][2], [_mention(text, pos, ws[used][2], value, "multiplier")]
    # "Phase two", "Phase two of the plan" are labels; "Phase twelve weeks", "Phase
    # two thousand" are quantities
    if used == 1 and _WORD_LABEL_END.match(text, end) and _after_label(text, pos):
        return end, []
    pct = _PCT.match(text, end)
    if pct:
        return pct.end(), [_mention(text, pos, pct.end(), value, "percent")]
    money = _MONEY_AFTER.match(text, end)
    if money:
        return money.end(), [_mention(text, pos, money.end(), value, "money")]
    return end, [_mention(text, pos, end, value, "word")]


def _read_letters(text: str, pos: int) -> Read | None:
    month_day = _read_month_day(text, pos)
    if month_day is not None:
        return month_day
    q = _quantity(text, pos)   # US$35, USD 35, AUD50, Rs500
    if q is not None:
        return q.end, [_mention(text, pos, q.end, q.value, _form(q))]
    m = _X_TIMES.match(text, pos)
    if m:   # "x3"
        return m.end(), [_mention(text, pos, m.end(), Decimal(m.group("n")), "multiplier")]
    m = _IDENT.match(text, pos)
    if m:
        return m.end(), []
    return _read_words(text, pos)


def _read_at(text: str, pos: int) -> Read | None:
    idiom = _IDIOM.match(text, pos)
    if idiom:   # 24/7, 1:1, one-on-one: no quantity
        return idiom.end(), []
    if text[pos] in _VULGAR:
        return pos + 1, [_mention(text, pos, pos + 1, _percent_of(*_VULGAR[text[pos]]), "fraction")]
    if text[pos].isalpha():
        return _read_letters(text, pos)
    marker = _LIST_MARKER.match(text, pos)
    if marker and _line_start(text, pos):   # "1. Book the studio": structure, not a number
        return marker.end(), []
    heading = _HEADING_NUMBER.match(text, pos) if _HEADING_LEAD.search(text, max(0, pos - 12), pos) else None
    if heading:   # "## 2. Diagnosis": structure
        return heading.end(), []
    # a clock time is a time even after a label word ("Step 6pm")
    return (_read_time(text, pos) or _read_tech(text, pos) or _read_position(text, pos)
            or _read_label(text, pos) or _read_date(text, pos) or _read_range(text, pos)
            or _read_digits(text, pos))


def _runs(text: str) -> tuple[bytearray, bytearray]:
    """Two facts about every position, measured in one pass so no later check
    walks back over a run:
      led[i]    1 when i sits in a run of letters and digits that starts with a
                digit ("10x12", "1h30"), so a digit inside it may start a number;
      glued[i]  1 when i is an underscore in a run glued to a letter or digit
                before it ("model_5"), so a number after it is an identifier and
                not emphasis ("__5__")."""
    led, glued = bytearray(len(text)), bytearray(len(text))
    run_led = run_glued = 0
    prev = ""
    for i, ch in enumerate(text):
        if ch.isalnum():
            if not prev.isalnum():
                run_led = 1 if ch.isdigit() else 0
            led[i] = run_led
        elif ch == "_":
            if prev != "_":
                run_glued = 1 if prev.isalnum() else 0
            glued[i] = run_glued
        prev = ch
    return led, glued


def _can_start(text: str, i: int, led: bytearray, glued: bytearray) -> bool:
    ch, nxt = text[i], text[i + 1:i + 2]
    if ch in _VULGAR:   # "1\u00bd": the half is read after the 1
        return True
    prev = text[i - 1] if i else ""
    if prev.isalnum():
        # inside a token: only a digit, and only when the token starts with one
        return ch.isdigit() and bool(led[i - 1])
    if prev == "_" and glued[i - 1]:
        return False   # model_5 is an identifier; __5__ is emphasis
    if ch.isdigit() or ch in _SIGNS:
        return True
    if ch in "-\u2212":
        return bool(nxt) and (nxt.isdigit() or nxt in _SIGNS or nxt == ".")
    if ch == ".":
        return prev != "." and nxt.isdigit()
    return ch.isascii() and ch.isalpha()


# -- the public reader and checker ----------------------------------------------------------

def mentions(text: str) -> list[Mention]:
    """Every number `text` holds, in text order. A range gives one mention per end."""
    out: list[Mention] = []
    text = text or ""
    led, glued = _runs(text)
    i, n = 0, len(text)
    while i < n:
        if not _can_start(text, i, led, glued):
            i += 1
            continue
        read = _read_at(text, i)
        if read is None:
            if text[i].isalpha():   # not a number: step over the letters of the word
                while i < n and text[i].isalpha():
                    i += 1
            else:
                i += 1
            continue
        end, found = read
        out.extend(found)
        i = max(end, i + 1)
    return out


# Units a money mention may match: the currency codes the reader knows. "USD" is
# what the registry gives money (registry._infer_unit).
_MONEY_UNITS = frozenset(_CURRENCY_CODES)


def supported(m: Mention, known: FigureSet, hours: set[int] | None = None) -> bool:
    """Whether a known figure supports the mention.

    A time is supported when `hours` is None or holds its hour. A date is
    supported by its form. Every other form needs a figure in `known.match`
    (within half a percent, or equal as the figure displays). Two unit checks
    keep a number from passing as something else: money needs a figure in a
    money unit or with no unit, and a percent or a fraction (both compared as
    the percent number: 25 for 25%, 33.3333 for a third) needs a figure in
    "percent" or with no unit.

    A mention near two figures of different values is supported here; refusing
    to pick one of them is the binder's job, not the reader's."""
    if m.form == "time":
        return hours is None or int(m.value) in hours
    if m.form == "date":
        return True
    found = known.match(m.value)
    if m.form == "money":
        return any(f.unit == "" or f.unit in _MONEY_UNITS for f in found)
    if m.form in ("percent", "fraction"):
        return any(f.unit in ("", "percent") for f in found)
    return bool(found)


def unsupported(text: str, known: FigureSet, *, hours: set[int] | None = None) -> list[Mention]:
    """Every mention in `text` that no known figure supports, in text order."""
    return [m for m in mentions(text) if not supported(m, known, hours)]
