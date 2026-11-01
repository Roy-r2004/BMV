"""Words the package reads the same way everywhere.

`TIME_CANON` maps every time word a number may be followed by, singular, plural
and the abbreviations clients type, to the singular a figure's unit carries
("hrs" is "hour", "mos" is "month"). The case file reads a client's "4 mos" with
it, and the binder is to read the model's prose with the same table (today
`bind._TIME_CANON` is its own copy without "mo" and "mos"), so a number and the
figure it stands for never disagree about what was counted.

It imports only the model's unit table, so every module can import it.
"""
from __future__ import annotations

from app.figures.model import _TIME_UNITS

TIME_CANON: dict[str, str] = {word: one for one, many in _TIME_UNITS for word in (one, many)}
TIME_CANON.update({"sec": "second", "secs": "second", "min": "minute", "mins": "minute", "hr": "hour",
                   "hrs": "hour", "wk": "week", "wks": "week", "mo": "month", "mos": "month",
                   "yr": "year", "yrs": "year"})


# Nouns that say nothing about WHAT a count counts ("2 others nearby", "6 things", "10
# people"). The case file stores such a noun as the count's unit, as typed ("others"), so
# a count with a generic noun is told apart from one with no noun at all (unit ""); the
# binder reads a figure in one of these units as a wildcard noun: it fits a mention with any
# noun after it, and one with none. Singular and plural are both listed, and the pronouns
# and determiners that stand where a noun would ("some", "any", "all"; "those" and "each"
# are function words and end the noun phrase before they are reached).
GENERIC_NOUNS: frozenset[str] = frozenset(
    "other others one ones thing things item items unit units person persons people folk folks place places "
    "them those these some any all both each every more".split())
