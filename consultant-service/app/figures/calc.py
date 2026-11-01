"""Exact arithmetic that returns a Figure with its working kept.

`derive` takes Figures, does one of four operations on them in Decimal, and
returns the result as a Figure whose source is the working: the ids it came
from, the operation, and a line a client can read ("$6 x 144 = $864 a week").
The arithmetic is exact. A float is refused, a result that would need more
digits than the context holds is refused rather than rounded, and the only
rounding anywhere is the cut a ratio needs when its division does not end.

Why a calculator of our own and not the engine's `DecimalCalculator`: the
engine one refuses subtraction, our own proposals, the pipeline's claim ids and
the USD unit, and importing it from the pipeline closes an import cycle (the
engine imports the pipeline at module level). So this module imports the Figure
model and the standard library, and nothing from `app.engine`.
`tests/figures/test_calc.py` runs the engine's calculator beside this one and
requires the same number wherever the engine accepts the operation.

Whose the result is: derived when every input is theirs, derived or a cited
reference; ours when any input is ours, since an estimate resting on our
proposal is our estimate. A Figure of ours carries a Proposal, which has no
inputs field, so for it the working is the note.

How a result prints: with no `precision` it shows the places its value needs
(see `SHOWN_PLACES`), so a chain of steps reads "385.2" and "46.8" and never "~385"
beside a "0". A tie rounds away from zero here and in `model.display` alike.
"""
from __future__ import annotations

from decimal import (
    ROUND_HALF_UP, Context, Decimal, DecimalException, DivisionByZero, Inexact, InvalidOperation, Overflow,
    Subnormal, Underflow,
)
from typing import Literal, Sequence

from app.figures.model import _TIME_UNITS, Figure, Proposal, Working, decimal_from_float, display

Op = Literal["product", "total", "difference", "ratio"]
OPS: tuple[str, ...] = ("product", "total", "difference", "ratio")

_LIMITS = dict(rounding=ROUND_HALF_UP, Emin=-9999, Emax=9999)
# Product, total and difference trap Inexact: wide enough that any figure a client
# or a model could write passes through whole, and a working that is not is refused.
_EXACT = Context(prec=100, traps=[InvalidOperation, DivisionByZero, Overflow, Inexact], **_LIMITS)
# A division that does not end has to be cut somewhere; 50 digits is far past what
# anything shown can use.
_DIVIDE = Context(prec=50, traps=[InvalidOperation, DivisionByZero, Overflow], **_LIMITS)
# Rounding for print (round_half_up): no trap on Inexact, since rounding is the point.
_ROUND = Context(prec=100, traps=[InvalidOperation, DivisionByZero, Overflow], **_LIMITS)

#: The most places a result shows when its precision is left to the working. A value
#: that needs more is shown rounded to this, with "~". The working line writes the
#: result out to the same number of places.
SHOWN_PLACES = 12

_TIMES, _MINUS, _DIVIDED_BY = "×", "−", "÷"
_SIGN = {"product": _TIMES, "total": "+", "difference": _MINUS, "ratio": _DIVIDED_BY}
_ADD_OR_TAKE = {"total": "added to", "difference": "taken from"}
_PER = {"day": "a day", "week": "a week", "fortnight": "a fortnight", "month": "a month", "year": "a year"}
# The closed words a unit may be written two ways: week/weeks, count/counts. Case is
# ignored for every unit (USD/usd).
_UNIT_WORDS = {**{many: one for one, many in _TIME_UNITS}, "counts": "count"}


# -- boundary: a number from JSON becomes digits ------------------------------------

def decimal_of(value: object) -> Decimal:
    """The digits of a number that came from JSON, a model or a stored float.

    A float goes through `model.decimal_from_float` (15 significant digits, then
    its repr, so 0.07 is Decimal('0.07') and a whole float carries no '.0'). An
    int is exact. A string or a Decimal is taken as written. Anything else, a
    bool, a non-finite number or text that is not a number raises ValueError.

    This is the one place a float becomes a Decimal. `derive` itself takes only
    Figures."""
    if isinstance(value, bool):
        raise ValueError("a yes/no value is not a number")
    if isinstance(value, float):
        return decimal_from_float(value)
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, (str, Decimal)):
        try:
            d = value if isinstance(value, Decimal) else Decimal(value.strip())
        except InvalidOperation:
            raise ValueError(f"{value!r} is not a number") from None
        if not d.is_finite():
            raise ValueError("a number must be finite")
        return d
    raise ValueError(f"{type(value).__name__} is not a number")


def _tidy(value: Decimal) -> Decimal:
    """No trailing zeros and no exponent: 7.00 is 7, 4.50 is 4.5, 450 stays 450."""
    return Decimal(int(value)) if value == value.to_integral_value() else value.normalize(_EXACT)


def places_of(value: Decimal) -> int:
    """Digits after the point needed to write `value` exactly: trailing zeros do
    not count, so 22.50 needs 1 and 450 needs 0. The `precision` of a figure that
    is printed exactly."""
    return max(0, -_tidy(value).as_tuple().exponent)


def round_half_up(value: object, places: int = 0) -> Decimal:
    """`value` (any number `decimal_of` reads) to `places` digits after the point,
    a tie going away from zero: 2.5 is 3 and -2.5 is -3, as `model.display` rounds.
    Python's round() and float formatting send a tie to the even digit instead."""
    return decimal_of(value).quantize(Decimal(1).scaleb(-places), context=_ROUND)


def unit_key(unit: str) -> str:
    """A unit with the ways of writing it that mean the same folded together:
    USD and usd, hour and hours, count and counts."""
    word = unit.strip().lower()
    return _UNIT_WORDS.get(word, word)


# -- the working -----------------------------------------------------------------------

def _plain(value: Decimal) -> str:
    return format(_tidy(value), ",f")


def _shown_places(value: Decimal) -> int:
    """The precision of a result left to show what it is: the places it needs, up to
    SHOWN_PLACES. Past that it is rounded there, unless that would print a value that
    is not zero as zero: then it keeps its first three digits instead."""
    needed = places_of(value)
    if needed <= SHOWN_PLACES or abs(value) >= Decimal(5).scaleb(-SHOWN_PLACES - 1):
        return min(needed, SHOWN_PLACES)
    return min(needed, 2 - value.adjusted())


def _after(period: str | None) -> str:
    if not period:
        return ""
    return f" {_PER[period]}" if period in _PER else f" ({period.replace('_', ' ')})"


def _working(op: str, inputs: Sequence[Figure], factors: Sequence[tuple[Decimal, str]], value: Decimal,
             unit: str, period: str | None) -> str:
    """The line a client reads: each input as it prints, the operation, then the
    result written out in full (to SHOWN_PLACES at most, with "~" past that)."""
    sign = f" {_SIGN[op]} "
    left = sign.join(display(f) for f in inputs)
    for number, words in factors:
        left += f" {_TIMES} " + f"{_plain(number)} {words}".strip()
    shown = Figure("working", value, unit, None, "derived", Working((), op, ""), _shown_places(value))
    return f"{left} = {display(shown)}{_after(period)}"


# -- checks ------------------------------------------------------------------------------

def _refuse_non_figures(inputs: Sequence[object]) -> None:
    for item in inputs:
        if isinstance(item, float):
            raise ValueError("a float cannot go into exact arithmetic; give a Figure built from the digits written")
        if not isinstance(item, Figure):
            raise ValueError(f"derive works on Figures, not {type(item).__name__}")


def _factors(factors: Sequence[tuple[object, str]]) -> list[tuple[Decimal, str]]:
    out = []
    for pair in factors:
        try:
            number, words = pair
        except (TypeError, ValueError):
            raise ValueError("a factor is a (number, words) pair, like (Decimal(52), 'weeks a year')") from None
        if isinstance(number, float):
            raise ValueError("a float cannot be a factor; write it as a Decimal, like Decimal('4.33')")
        if isinstance(number, bool) or not isinstance(number, (int, Decimal)):
            raise ValueError("a factor's number must be a Decimal or a whole number")
        if not Decimal(number).is_finite():
            raise ValueError("a factor's number must be finite")
        if not isinstance(words, str):
            raise ValueError("a factor's words must be text")
        out.append((Decimal(number), words))
    return out


def _same_unit_and_period(op: str, inputs: Sequence[Figure]) -> None:
    first = inputs[0]
    for other in inputs[1:]:
        if unit_key(other.unit) != unit_key(first.unit):
            raise ValueError(f"{display(first)} and {display(other)} are not the same kind of number, "
                             f"so one cannot be {_ADD_OR_TAKE[op]} the other")
        if first.period and other.period and first.period != other.period:
            raise ValueError(f"{display(first)} ({first.period}) and {display(other)} ({other.period}) "
                             f"are not for the same period, so one cannot be {_ADD_OR_TAKE[op]} the other")


# -- the operations -------------------------------------------------------------------------

def _compute(op: str, inputs: Sequence[Figure], factors: Sequence[tuple[Decimal, str]]) -> Decimal:
    # Contexts are copied per call so their flags tell what went wrong in this one.
    exact, cut = _EXACT.copy(), _DIVIDE.copy()
    exact.clear_flags()
    cut.clear_flags()
    values = [f.value for f in inputs]
    try:
        if op == "product":
            result = values[0]
            for v in values[1:] + [n for n, _ in factors]:
                result = exact.multiply(result, v)
        elif op == "total":
            result = values[0]
            for v in values[1:]:
                result = exact.add(result, v)
        elif op == "difference":
            result = values[0]
            for v in values[1:]:
                result = exact.subtract(result, v)
        else:
            numerator, denominator = values
            if denominator == 0:
                raise ValueError(f"cannot divide {display(inputs[0])} by {display(inputs[1])}: the second is zero")
            result = cut.divide(numerator, denominator)
            for n, _ in factors:
                result = cut.multiply(result, n)
    except ValueError:
        raise
    except DecimalException:
        if any(c.flags[Underflow] or c.flags[Subnormal] for c in (exact, cut)):
            raise ValueError("this working comes out too small to be a figure") from None
        raise ValueError("this working has too many digits to be worked out exactly") from None
    return _tidy(result)


def derive(op: Op, inputs: Sequence[Figure], *, id: str, unit: str, period: str | None = None,
           precision: int | None = None, factors: Sequence[tuple[Decimal, str]] = ()) -> Figure:
    """The result of `op` over `inputs` as a Figure that carries its working.

    product     every input and every factor multiplied
    total       every input added; the inputs must share a unit (and a period, where both name one)
    difference  the first input less every later one; the same sharing
    ratio       the first input over the second, then times each factor (a percent is a ratio
                with the factor (Decimal(100), "percent"))

    `factors` are calendar constants, like (Decimal(52), "weeks a year"); they
    are numbers, not figures, so they are shown in the working but are not among
    its inputs. They apply to a product or a ratio.

    The result is derived when every input is theirs, derived or reference, and
    ours when any input is ours. `unit` and `period` name the result. Its value
    keeps every digit; `precision` is how it prints: an int rounds to that many
    places (negative to tens, hundreds), and None, the default, shows the places
    the value needs, up to SHOWN_PLACES.

    Raises ValueError, in plain words, for a float or a non-Figure input, a
    ratio by zero, inputs that are not the same kind of number in a total or
    difference, a count of inputs the operation cannot take, or a working too
    wide to be exact or too small to be a figure."""
    if op not in OPS:
        raise ValueError(f"unknown operation {op!r}; one of {', '.join(OPS)}")
    inputs = list(inputs)
    _refuse_non_figures(inputs)
    constants = _factors(factors)
    if constants and op not in ("product", "ratio"):
        raise ValueError(f"a {op} takes no factors; they apply to a product or a ratio")
    if op == "ratio":
        if len(inputs) != 2:
            raise ValueError("a ratio takes exactly two figures, the top and the bottom")
    elif op == "product":
        if len(inputs) + len(constants) < 2:
            raise ValueError("a product needs at least two numbers")
    elif len(inputs) < 2:
        raise ValueError(f"a {op} needs at least two figures")
    if op in _ADD_OR_TAKE:
        _same_unit_and_period(op, inputs)

    value = _compute(op, inputs, constants)
    text = _working(op, inputs, constants, value, unit, period)
    if precision is None:
        precision = _shown_places(value)
    ids = tuple(f.id for f in inputs)
    if any(f.kind == "ours" for f in inputs):
        return Figure(id, value, unit, period, "ours", Proposal(note=text), precision)
    return Figure(id, value, unit, period, "derived", Working(inputs=ids, op=op, text=text), precision)
