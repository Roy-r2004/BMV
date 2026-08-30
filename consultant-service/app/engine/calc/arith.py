"""DecimalCalculator - the Calculator protocol (contracts section 8) in exact arithmetic.

Every number a method emits comes from here as a CalcResult: a Quantity, the
formula over entity ids that produced it, and those ids. recompute() runs
the stored formula over the stored inputs again and demands EQUALITY, not
closeness: r30 learned (decompose.py:186-197) that a 0.15% drift is still an
invented number, and L7 generalises that to every calculated fact.

The calculator refuses rather than guesses. Each refusal is one of:

- IncomparableInputs  currencies or period bases differ without a registered
                      conversion fact; a dimension the arithmetic needs is
                      None; capacity would become money without a price fact.
                      `reason` names which, `unpinned` names the dimensions,
                      so the caller can open the right QUESTION.
- ValueError          a share the client never gave (decompose.unit_provenance:
                      applying an inquiry share to an hours pool asserts a
                      fact only the client can state), an unknown period
                      basis, a zero denominator, a malformed formula.

There is no mean, no blend and no pick anywhere in this module.
"""
from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence

from app.engine.calc import CalcResult, IncomparableInputs, RegistryView
from app.engine.calc.units import COMPARABLE, INCOMPARABLE, UNKNOWN_DIMENSION, canonical_unit, comparable
from app.engine.types import (
    ApprovalState, Dimensions, Entity, FactBasis, Kind, Quantity, UnitFamily,
)

# Periods per year for each period basis, exactly the steps r30 recognises
# when it verifies an annualised product (decompose.py:186) and the bases
# timebasis.candidates (timebasis.py:52) can state a figure on.
PERIOD_STEPS: dict[str, int] = {"year": 1, "month": 12, "fortnight": 26, "week": 52, "day": 365}

_ID = re.compile(r"[A-Z]{3}-\d+")
_TOKEN = re.compile(r"\s*(?:([A-Z]{3}-\d+)|(\d+(?:\.\d+)?)|([()+\-*/]))")


def _refusal(reason: str, message: str, unpinned: tuple[str, ...] = ()) -> IncomparableInputs:
    exc = IncomparableInputs(message)
    exc.reason = reason            # "unknown_dimension" | "incomparable" | "capacity_to_money"
    exc.unpinned = unpinned
    return exc


def quantity_of(entity: Entity) -> Quantity | None:
    """The Quantity an entity carries, whatever its kind (FACT, ASSUMPTION,
    COST, BENEFIT, EXPECTED_OUTCOME carry `quantity`; OBJECTIVE carries `target`)."""
    q = getattr(entity.payload, "quantity", None)
    if q is None:
        q = getattr(entity.payload, "target", None)
    return q if isinstance(q, Quantity) else None


def share_is_given(entity: Entity) -> bool:
    """A fraction may enter a product only when someone with the authority to
    state it did: a FACT that is not merely inferred, or an ASSUMPTION the
    client APPROVED. An inferred share or an unapproved assumption is the
    engine's own guess and never multiplies a client figure."""
    if entity.kind is Kind.FACT:
        return entity.payload.basis is not FactBasis.INFERRED
    if entity.kind is Kind.ASSUMPTION:
        return entity.payload.approval is ApprovalState.APPROVED
    return False


def _quantise(value: Decimal, precision: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-precision), rounding=ROUND_HALF_UP)


def _common(values: list[str | None]) -> str | None:
    pinned = {v for v in values if v is not None}
    return pinned.pop() if len(pinned) == 1 else None


def _unpinned_between(a: Quantity, b: Quantity) -> tuple[str, ...]:
    """The dimensions a comparison of a and b is missing: needed by the family
    and None on a side, or pinned on one side only. `is None` throughout."""
    from app.engine.calc.units import required_dimensions
    needed = set(required_dimensions(a.unit_family))
    out = []
    for n in Dimensions.DIMENSION_NAMES:
        va, vb = getattr(a.dimensions, n), getattr(b.dimensions, n)
        if (n in needed and (va is None or vb is None)) or ((va is None) != (vb is None)):
            out.append(n)
    return tuple(out)


class DecimalCalculator:
    """Calculator over a RegistryView (optional: only conversion-fact lookup
    needs one). Pure: no state beyond the view it reads."""

    def __init__(self, view: RegistryView | None = None):
        self.view = view

    # -- inputs ---------------------------------------------------------------

    def _quantities(self, inputs: Sequence[Entity]) -> list[tuple[Entity, Quantity]]:
        out = []
        for e in inputs:
            q = quantity_of(e)
            if q is None:
                raise ValueError(f"{e.id or e.kind.value} carries no quantity")
            if not e.id:
                raise ValueError("calculator inputs must be registered entities (an id is the lineage)")
            out.append((e, q))
        if not out:
            raise ValueError("a calculation needs at least one input")
        return out

    def _conversion_fact(self, from_unit: str, to_unit: str) -> Entity | None:
        """A registered FACT whose unit is '<to>/<from>' and whose basis is
        not inferred: the only thing that may turn one currency into another."""
        if self.view is None:
            return None
        wanted = f"{canonical_unit(to_unit)}/{canonical_unit(from_unit)}"
        for fact in self.view.query(Kind.FACT):
            q = quantity_of(fact)
            if q is not None and canonical_unit(q.unit) == wanted and share_is_given(fact):
                return fact
        return None

    def _same_currency(self, pairs: list[tuple[Entity, Quantity]], target: str
                       ) -> tuple[list[tuple[Entity, Quantity]], list[str], list[str]]:
        """Every money input expressed in `target`, through a registered
        conversion fact or not at all."""
        out, extra_ids, extra_terms = [], [], []
        for e, q in pairs:
            if q.unit_family is not UnitFamily.MONEY or canonical_unit(q.unit) == target:
                out.append((e, q))
                continue
            conv = self._conversion_fact(q.unit, target)
            if conv is None:
                raise _refusal("incomparable",
                               f"{e.id} is in {q.unit}, the calculation is in {target} and no conversion fact is registered",
                               ("currency",))
            rate = quantity_of(conv)
            dims = Dimensions(currency=target, period=q.dimensions.period, period_basis=q.dimensions.period_basis,
                              scope=q.dimensions.scope, as_of=q.dimensions.as_of, definition=q.dimensions.definition)
            out.append((e, Quantity(q.value * rate.value, target, UnitFamily.MONEY, dims, max(q.precision, rate.precision))))
            extra_ids.append(conv.id)
            extra_terms.append(f"{e.id} * {conv.id}")
        return out, extra_ids, extra_terms

    # -- the four operations --------------------------------------------------

    def product(self, inputs: Sequence[Entity], *, unit: str, unit_family: UnitFamily, period_step: int = 1) -> CalcResult:
        pairs = self._quantities(inputs)
        if period_step not in PERIOD_STEPS.values():
            raise ValueError(f"period_step must be one of {sorted(PERIOD_STEPS.values())}, got {period_step!r}")
        for e, q in pairs:
            if q.unit_family is UnitFamily.RATE and not share_is_given(e):
                raise ValueError(f"{e.id} is a share nobody with authority stated; it cannot multiply a client figure")
        families = [q.unit_family for _, q in pairs]
        if unit_family is UnitFamily.MONEY and UnitFamily.MONEY not in families:
            raise _refusal("capacity_to_money",
                           "a volume or capacity becomes money only through a price fact; none is among the inputs")
        money = [(e, q) for e, q in pairs if q.unit_family is UnitFamily.MONEY]
        for e, q in money:
            if q.dimensions.currency is None:
                raise _refusal("unknown_dimension", f"{e.id} is money with no currency pinned", ("currency",))
        currencies = sorted({canonical_unit(q.dimensions.currency) for _, q in money})
        extra_ids: list[str] = []
        formula_terms = [e.id for e, _ in pairs]
        if len(currencies) > 1:
            target = canonical_unit(unit) if unit_family is UnitFamily.MONEY and canonical_unit(unit) in currencies else currencies[0]
            pairs, extra_ids, converted = self._same_currency(pairs, target)
            formula_terms = [t for t in formula_terms if t not in {c.split(" * ")[0] for c in converted}] + converted
            currencies = [target]
        bases = {q.dimensions.period_basis for _, q in pairs if q.dimensions.period_basis is not None}
        if len(bases) > 1:
            raise _refusal("incomparable", f"inputs are on different period bases {sorted(bases)}; convert_period first",
                           ("period_basis",))
        value = Decimal(1)
        for _, q in pairs:
            value *= q.value
        value *= period_step
        precision = max(q.precision for _, q in pairs)
        basis = bases.pop() if bases else None
        if period_step != 1:
            basis = "year"
        dims = Dimensions(
            currency=currencies[0] if money else None,
            period=_common([q.dimensions.period for _, q in pairs]),
            period_basis=basis,
            scope=_common([q.dimensions.scope for _, q in pairs]),
            as_of=_common([q.dimensions.as_of for _, q in pairs]),
            definition=None,
        )
        formula = " * ".join(formula_terms) + (f" * {period_step}" if period_step != 1 else "")
        result = Quantity(_quantise(value, precision), canonical_unit(unit) or unit, unit_family, dims, precision)
        return CalcResult(result, formula, tuple(e.id for e, _ in pairs) + tuple(extra_ids))

    def total(self, inputs: Sequence[Entity]) -> CalcResult:
        pairs = self._quantities(inputs)
        first_e, first_q = pairs[0]
        extra_ids: list[str] = []
        terms = [first_e.id]
        converted = []
        for e, q in pairs[1:]:
            verdict = comparable(first_q, q)
            if verdict == UNKNOWN_DIMENSION:
                raise _refusal("unknown_dimension", f"{first_e.id} and {e.id} cannot be added: a dimension is not pinned",
                               _unpinned_between(first_q, q))
            if verdict == INCOMPARABLE:
                if (first_q.unit_family is UnitFamily.MONEY and q.unit_family is UnitFamily.MONEY
                        and canonical_unit(first_q.unit) != canonical_unit(q.unit)):
                    # Two currencies: only a registered conversion fact joins
                    # them, and the converted figure must then agree on every
                    # other dimension as well.
                    same, ids, cterms = self._same_currency([(e, q)], canonical_unit(first_q.unit))
                    cq = same[0][1]
                    if comparable(first_q, cq) != COMPARABLE:
                        raise _refusal("incomparable", f"{first_e.id} and {e.id} differ beyond currency")
                    converted.append((e, cq))
                    extra_ids.extend(ids)
                    terms.extend(cterms)
                    continue
                raise _refusal("incomparable", f"{first_e.id} ({first_q.unit}) and {e.id} ({q.unit}) cannot be added")
            converted.append((e, q))
            terms.append(e.id)
        value = first_q.value + sum((q.value for _, q in converted), Decimal(0))
        precision = max([first_q.precision] + [q.precision for _, q in converted])
        result = Quantity(_quantise(value, precision), canonical_unit(first_q.unit) or first_q.unit,
                          first_q.unit_family, first_q.dimensions, precision)
        return CalcResult(result, " + ".join(terms), tuple(e.id for e, _ in pairs) + tuple(extra_ids))

    def ratio(self, numerator: Entity, denominator: Entity) -> CalcResult:
        (ne, nq), (de, dq) = self._quantities([numerator, denominator])
        if dq.value == 0:
            raise ValueError(f"{de.id} is zero; the ratio is undefined")
        if nq.unit_family is dq.unit_family:
            verdict = comparable(nq, dq)
            if verdict == UNKNOWN_DIMENSION:
                raise _refusal("unknown_dimension", f"{ne.id} / {de.id}: a dimension is not pinned",
                               _unpinned_between(nq, dq))
            if verdict == INCOMPARABLE:
                raise _refusal("incomparable", f"{ne.id} ({nq.unit}) and {de.id} ({dq.unit}) are not one kind of thing")
            unit, family = "%", UnitFamily.RATE
        else:
            for e, q in ((ne, nq), (de, dq)):
                if q.unit_family is UnitFamily.MONEY and q.dimensions.currency is None:
                    raise _refusal("unknown_dimension", f"{e.id} is money with no currency pinned", ("currency",))
            unit = f"{canonical_unit(nq.unit)}/{canonical_unit(dq.unit)}"
            family = UnitFamily.CAPACITY if dq.unit_family is UnitFamily.TIME else UnitFamily.OTHER
        precision = max(nq.precision, dq.precision)
        dims = Dimensions(currency=nq.dimensions.currency if family is not UnitFamily.RATE else None,
                          period=_common([nq.dimensions.period, dq.dimensions.period]),
                          period_basis=_common([nq.dimensions.period_basis, dq.dimensions.period_basis]),
                          scope=_common([nq.dimensions.scope, dq.dimensions.scope]),
                          as_of=_common([nq.dimensions.as_of, dq.dimensions.as_of]), definition=None)
        value = _quantise(nq.value / dq.value, precision)
        return CalcResult(Quantity(value, unit, family, dims, precision), f"{ne.id} / {de.id}", (ne.id, de.id))

    def convert_period(self, fact: Entity, to_basis: str) -> CalcResult:
        (e, q), = self._quantities([fact])
        if to_basis not in PERIOD_STEPS:
            raise ValueError(f"unknown period basis {to_basis!r}; one of {sorted(PERIOD_STEPS)}")
        frm = q.dimensions.period_basis
        if frm is None:
            raise _refusal("unknown_dimension", f"{e.id} has no period basis pinned; it cannot be restated per {to_basis}",
                           ("period_basis",))
        if frm not in PERIOD_STEPS:
            raise ValueError(f"{e.id} is on period basis {frm!r}, which has no annual step")
        steps_from, steps_to = PERIOD_STEPS[frm], PERIOD_STEPS[to_basis]
        value = _quantise(q.value * steps_from / steps_to, q.precision)
        dims = Dimensions(currency=q.dimensions.currency, period=q.dimensions.period, period_basis=to_basis,
                          scope=q.dimensions.scope, as_of=q.dimensions.as_of, definition=q.dimensions.definition)
        return CalcResult(Quantity(value, q.unit, q.unit_family, dims, q.precision),
                          f"{e.id} * {steps_from} / {steps_to}", (e.id,))

    # -- recompute ------------------------------------------------------------

    def recompute(self, calculated: Entity, registry: RegistryView) -> bool:
        """True only when the stored formula, run over the stored inputs,
        yields the stored value EXACTLY at the stored precision. Any missing
        input, unreadable formula or drift - however small - is False: the
        gate then reports L7 rather than the engine forgiving itself."""
        payload = calculated.payload
        if calculated.kind is not Kind.FACT or payload.basis is not FactBasis.CALCULATED:
            return False
        stored = payload.quantity
        if stored is None or not payload.formula or not payload.inputs:
            return False
        values: dict[str, Decimal] = {}
        for entity_id in payload.inputs:
            e = registry.get(entity_id)
            q = quantity_of(e) if e is not None else None
            if q is None:
                return False
            values[entity_id] = q.value
        try:
            got = evaluate(payload.formula, values)
        except (ValueError, ZeroDivisionError, ArithmeticError):
            return False
        return _quantise(got, stored.precision) == stored.value

    def comparable(self, a: Quantity, b: Quantity) -> str:
        return comparable(a, b)


# -- the formula grammar: ids, integer/decimal literals, + - * / and parentheses --

def evaluate(formula: str, values: dict[str, Decimal]) -> Decimal:
    """Exact evaluation of a stored formula. No eval(): the grammar admits
    entity ids, literals and four operators, nothing that could call code."""
    tokens: list[str] = []
    pos = 0
    text = formula.strip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise ValueError(f"unreadable formula at {text[pos:pos + 12]!r}")
        tokens.append(m.group(1) or m.group(2) or m.group(3))
        pos = m.end()
    if not tokens:
        raise ValueError("empty formula")
    parser = _Parser(tokens, values)
    result = parser.expr()
    if parser.i != len(tokens):
        raise ValueError("trailing tokens in formula")
    return result


class _Parser:
    def __init__(self, tokens: list[str], values: dict[str, Decimal]):
        self.t, self.values, self.i = tokens, values, 0

    def peek(self) -> str | None:
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self) -> str:
        tok = self.t[self.i]
        self.i += 1
        return tok

    def expr(self) -> Decimal:
        v = self.term()
        while self.peek() in ("+", "-"):
            op = self.take()
            r = self.term()
            v = v + r if op == "+" else v - r
        return v

    def term(self) -> Decimal:
        v = self.factor()
        while self.peek() in ("*", "/"):
            op = self.take()
            r = self.factor()
            if op == "/":
                if r == 0:
                    raise ZeroDivisionError("division by zero in formula")
                v = v / r
            else:
                v = v * r
        return v

    def factor(self) -> Decimal:
        tok = self.peek()
        if tok is None:
            raise ValueError("formula ends early")
        if tok == "(":
            self.take()
            v = self.expr()
            if self.take() != ")":
                raise ValueError("unbalanced parentheses")
            return v
        if tok == "-":
            self.take()
            return -self.factor()
        self.take()
        if _ID.fullmatch(tok):
            if tok not in self.values:
                raise ValueError(f"formula names {tok}, which is not among the inputs")
            return self.values[tok]
        return Decimal(tok)
