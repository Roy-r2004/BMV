"""The range on the headline move.

Only a term we proposed is moved, by the same percent either way. What the
client stated and the calendar constants stay exact. A term that is taken away
is flexed so the low end is still the smaller one. A move that kept no terms
has no range: the caller is told, and nothing is filled in.
"""
from __future__ import annotations

from decimal import Decimal

from app.figures.calc import decimal_of


class NoTerms(Exception):
    """The move kept no terms, so there is no range to show."""


def flexed(terms, pct) -> tuple[Decimal, Decimal, Decimal]:
    """`(low, mid, high)` of the product. `pct` of 20 moves each assumption of
    ours to 80% and to 120%. `None` (a move stored before it kept its terms)
    raises `NoTerms`."""
    if not isinstance(terms, list) or not terms:
        raise NoTerms("the move kept no terms")
    span = Decimal(pct)
    low = mid = high = Decimal(1)
    for term in terms:
        lo, md, hi = _factor(term, span)
        low, high = _product_ends(low, high, lo, hi)
        mid *= md
    return low, mid, high


def note(terms, pct) -> str | None:
    """The footnote that says which assumption moved, or None when none is ours."""
    ours = [leaf for leaf in _leaves(terms) if isinstance(leaf, dict) and leaf.get("kind") == "proposed"]
    if not ours:
        return None
    said = [_assumption(decimal_of(leaf["value"])) for leaf in ours]
    percent = _plain(Decimal(pct))
    if len(said) == 1:
        return f"Flexes our assumption of {said[0]} by {percent}% either way."
    return f"Flexes our assumptions of {_join(said)} by {percent}% either way."


def _factor(term: dict, pct: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    if not isinstance(term, dict):
        raise NoTerms("the move kept no terms")
    parts = term.get("parts")
    if isinstance(parts, list) and parts:
        low = mid = high = Decimal(0)
        for part in parts:
            lo, md, hi = _factor(part, pct)
            low, mid, high = low + lo, mid + md, high + hi
    else:
        low, mid, high = _leaf(term, pct)
    return _apply_sign(low, mid, high, term.get("sign", 1))


def _leaf(term: dict, pct: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    value = decimal_of(term["value"])
    if term.get("kind") != "proposed":
        return value, value, value
    low = value * (Decimal(100) - pct) / Decimal(100)
    high = value * (Decimal(100) + pct) / Decimal(100)
    if low > high:
        low, high = high, low
    return low, value, high


def _apply_sign(low: Decimal, mid: Decimal, high: Decimal, sign) -> tuple[Decimal, Decimal, Decimal]:
    if str(sign) in ("-1", "-"):
        return -high, -mid, -low
    return low, mid, high


def _product_ends(a_low: Decimal, a_high: Decimal, b_low: Decimal, b_high: Decimal) -> tuple[Decimal, Decimal]:
    ends = (a_low * b_low, a_low * b_high, a_high * b_low, a_high * b_high)
    return min(ends), max(ends)


def _leaves(terms):
    if not isinstance(terms, list):
        return
    for term in terms:
        if not isinstance(term, dict):
            continue
        parts = term.get("parts")
        if isinstance(parts, list) and parts:
            yield from _leaves(parts)
        else:
            yield term


def _assumption(value: Decimal) -> str:
    """A share the model wrote as a fraction (0.75) is said as a percent (75%)."""
    if Decimal(0) < abs(value) < 1:
        return f"{_plain(value * Decimal(100))}%"
    return _plain(value)


def _plain(value: Decimal) -> str:
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), "f")


def _join(parts: list[str]) -> str:
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + " and " + parts[-1]
