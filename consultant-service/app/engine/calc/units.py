"""Quantity parsing, formatting, unit-family inference and comparability.

A number in the engine is a Decimal with a unit, a UnitFamily and six
nullable Dimensions. This module is where prose becomes such a number and
where two such numbers are asked whether they may be compared at all. It
reuses the r30 number grammar rather than growing a second one: a token that
r30 refused to read as a quantity (a year, a model designation, a section
ordinal) is refused here for the same reasons.

The value is built from the TOKEN, never from the float r30 returns, so the
Decimal is the digits the source wrote. This is the only module under
app/engine outside gates/presentation.py and work_products/corrections.py
where re.sub may appear (design section 18.5), and it is used only to
normalise whitespace inside a unit string.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from app.pipeline.registry import _infer_unit, _numbers, canonical_capacity_unit
from app.engine.types import Dimensions, Quantity, UnitFamily

# The three answers comparable() can give. Strings, because the Calculator
# protocol (contracts section 8) freezes the return type as str.
COMPARABLE = "comparable"
INCOMPARABLE = "incomparable"
UNKNOWN_DIMENSION = "unknown_dimension"

# Time units the r30 grammar emits (registry._NUM), in their canonical plural.
_TIME_UNITS = {
    "ms": "ms", "millisecond": "ms", "milliseconds": "ms",
    "second": "seconds", "seconds": "seconds", "minute": "minutes", "minutes": "minutes",
    "hour": "hours", "hours": "hours", "day": "days", "days": "days", "week": "weeks", "weeks": "weeks",
    "month": "months", "months": "months", "year": "years", "years": "years",
}
_DISTANCE_AREA_MASS = {
    "m", "km", "mi", "mile", "miles", "metre", "metres", "meter", "meters", "ft", "feet",
    "m2", "sqm", "sq m", "sqft", "hectare", "hectares", "ha", "acre", "acres",
    "kg", "kilogram", "kilograms", "g", "gram", "grams", "t", "tonne", "tonnes", "ton", "tons", "lb", "lbs",
}
_RATE_UNITS = {"%", "percent", "ratio", "share", "fraction", "pp"}
# A currency is an ISO-4217 style code or the dollar sign; a three-letter
# upper-case code that is not a known non-money unit is read as money so a
# currency the engine has never seen (a client trading in a small market)
# is still money and still needs a conversion fact.
_CURRENCY_SIGNS = {"$": "USD", "usd": "USD", "eur": "EUR", "gbp": "GBP", "chf": "CHF", "jpy": "JPY",
                   "aud": "AUD", "cad": "CAD", "sek": "SEK", "nok": "NOK", "dkk": "DKK", "pln": "PLN",
                   "aed": "AED", "sar": "SAR", "inr": "INR", "cny": "CNY", "lbp": "LBP"}
_ISO_CODE = re.compile(r"^[A-Z]{3}$")
_NON_MONEY_CODES = {"GPU", "FTE", "GBS", "TPS", "RPS", "QPS", "PP"}

# Which dimensions a comparison NEEDS pinned for each family. A money figure
# without a currency or a per-period figure without its period basis cannot
# be compared with anything; an as_of is needed everywhere because a count
# at two unknown dates is two unknown populations, not one.
_REQUIRED: dict[UnitFamily, tuple[str, ...]] = {
    UnitFamily.MONEY: ("currency", "period_basis", "as_of"),
    UnitFamily.CAPACITY: ("period_basis", "as_of"),
    UnitFamily.COUNT: ("as_of",),
    UnitFamily.TIME: ("as_of",),
    UnitFamily.RATE: ("as_of",),
    UnitFamily.DISTANCE_AREA_MASS: ("as_of",),
    UnitFamily.OTHER: ("as_of",),
}


def required_dimensions(family: UnitFamily) -> tuple[str, ...]:
    return _REQUIRED[family]


def canonical_unit(unit: str) -> str:
    """One surface form per unit: '$' and 'usd' are USD, 'GB / s' is 'GB/s',
    'Hours' is 'hours'. Two spellings of one unit must never become two units."""
    raw = re.sub(r"\s+", " ", str(unit or "")).strip()
    if not raw:
        return ""
    low = raw.lower()
    if low in _CURRENCY_SIGNS:
        return _CURRENCY_SIGNS[low]
    if _ISO_CODE.match(raw) and raw not in _NON_MONEY_CODES:
        return raw
    canon = canonical_capacity_unit(raw)
    if canon:
        return canon
    if "/" in raw:
        # A compound unit ('EUR/USD' for a conversion rate, 'hours/week') is
        # canonical when each side is: a rate fact registered as 'eur / usd'
        # must still be found when the calculator looks for 'EUR/USD'.
        left, _, right = raw.partition("/")
        return f"{canonical_unit(left)}/{canonical_unit(right)}"
    if low in _TIME_UNITS:
        return _TIME_UNITS[low]
    if low in _RATE_UNITS:
        return "%" if low in ("%", "percent", "pp") else low
    return low


def family_of(unit: str) -> UnitFamily:
    """The UnitFamily a unit string belongs to. Unknown units are OTHER, which
    is comparable only with the identical unit: the engine never guesses that
    two unfamiliar words measure one thing."""
    u = canonical_unit(unit)
    if not u:
        return UnitFamily.OTHER
    if u in _CURRENCY_SIGNS.values() or (_ISO_CODE.match(u) and u not in _NON_MONEY_CODES):
        return UnitFamily.MONEY
    if u in _RATE_UNITS or u == "%":
        return UnitFamily.RATE
    if u in _TIME_UNITS.values():
        return UnitFamily.TIME
    if canonical_capacity_unit(u) or "/" in u:
        return UnitFamily.CAPACITY
    if u in _DISTANCE_AREA_MASS:
        return UnitFamily.DISTANCE_AREA_MASS
    if u in ("count", "heads", "fte", "staff", "people", "units", "items") or u.endswith("s"):
        return UnitFamily.COUNT
    return UnitFamily.OTHER


def _decimal_of_token(tok: str) -> Decimal | None:
    raw = tok.replace("$", "").replace("~", "").replace(",", "").strip()
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def parse_quantity(text: str, context: str = "", *, dimensions: Dimensions | None = None) -> Quantity | None:
    """The first quantity in `text`, exact, or None when there is none.

    The token is what the source wrote, so "1,250.50" is Decimal("1250.50")
    and not a float that happens to print the same. A percentage is stored as
    the fraction the source meant (12% -> 0.12) with unit '%', as r30 does.
    The currency dimension is pinned from the unit when the unit is money and
    the caller pinned nothing else - the unit IS the currency.
    """
    found = _numbers(text or "")
    if not found:
        return None
    tok, _value, unit, _start, _end = found[0]
    value = _decimal_of_token(tok)
    if value is None:
        return None
    unit, _basis = _infer_unit(tok, unit, context or text or "")
    unit = canonical_unit(unit)
    family = family_of(unit)
    if unit == "%":
        value = value / Decimal(100)
        precision = max(2, -value.as_tuple().exponent if value.as_tuple().exponent < 0 else 0)
    else:
        exp = value.as_tuple().exponent
        precision = max(2, -exp if isinstance(exp, int) and exp < 0 else 0)
    dims = dimensions or Dimensions()
    if family is UnitFamily.MONEY and dims.currency is None:
        dims = Dimensions(currency=unit, period=dims.period, period_basis=dims.period_basis,
                          scope=dims.scope, as_of=dims.as_of, definition=dims.definition)
    return Quantity(value=value, unit=unit, unit_family=family, dimensions=dims, precision=precision)


def format_quantity(q: Quantity) -> str:
    """Deterministic rendering: the exact value at its precision, then the
    unit, then the pinned basis. Never rounds beyond the stored precision."""
    value = q.value.quantize(Decimal(1).scaleb(-q.precision)) if q.precision >= 0 else q.value
    if q.unit == "%":
        shown = (value * 100).normalize()
        text = f"{shown:f}%"
    elif q.unit_family is UnitFamily.MONEY:
        text = f"{q.unit} {value:,.{q.precision}f}"
    else:
        text = f"{value:,.{q.precision}f} {q.unit}"
    basis = q.dimensions.period_basis
    if basis and basis != "point_in_time":
        text += f" per {basis}"
    return text


def comparable(a: Quantity, b: Quantity) -> str:
    """May a and b be added, compared or reconciled directly?

    - different families, or different units within a family (EUR vs USD,
      heads vs FTE), or a dimension pinned differently on the two sides:
      INCOMPARABLE - the caller needs a conversion fact or a question;
    - a dimension the family needs that is None on either side, or pinned on
      one side and None on the other: UNKNOWN_DIMENSION - the caller opens a
      question; absence is never read as agreement;
    - otherwise COMPARABLE.
    The None tests are `is None` so a dimension a newer normaliser pins to an
    empty-but-present value is not condemned as missing.
    """
    if a.unit_family is not b.unit_family:
        return INCOMPARABLE
    if canonical_unit(a.unit) != canonical_unit(b.unit):
        return INCOMPARABLE
    needed = set(required_dimensions(a.unit_family))
    for name in Dimensions.DIMENSION_NAMES:
        va, vb = getattr(a.dimensions, name), getattr(b.dimensions, name)
        if name in needed and (va is None or vb is None):
            return UNKNOWN_DIMENSION
        if (va is None) != (vb is None):
            return UNKNOWN_DIMENSION
        if va is not None and vb is not None and va != vb:
            return INCOMPARABLE
    return COMPARABLE
