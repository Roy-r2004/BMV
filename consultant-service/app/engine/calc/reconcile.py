"""reconcile(a, b) - what two facts on one MEASURE are to each other.

Facts join on `measure_id` only (MF1.6): the caller has already grouped
them, and this function never reads statement text, topic or any other
free field, so no similarity can decide that two numbers are one. Given a
pair it returns exactly one of:

- question   a dimension the comparison needs is None on a side (or pinned
             on one side only): the client is asked to pin it. Absence is
             not a defect and not agreement; the test is `is None`.
- distinct   both pinned, differently (FY24 vs FY25, NL vs group): two facts,
             not one, and no conflict.
- conflict   DEFINITION when the pinned definitions or the units differ
             (heads vs FTE is a question about what is counted, not a value
             to reconcile); CLIENT_VS_RECORD when one side is client-stated
             and the other document-verified; VALUE otherwise.
- same       identical dimensions and identical value.

There is no arithmetic in this module. Two different values on identical
dimensions are a CONFLICT the client or a higher-ranked record resolves;
nothing here computes a midpoint or picks a side.
"""
from __future__ import annotations

from app.engine.calc import Reconciliation
from app.engine.calc.units import canonical_unit, required_dimensions
from app.engine.types import ConflictKind, Dimensions, Entity, FactBasis, Kind


def _unpinned(a: Entity, b: Entity) -> tuple[str, ...]:
    qa, qb = a.payload.quantity, b.payload.quantity
    needed = set(required_dimensions(qa.unit_family))
    out = []
    for name in Dimensions.DIMENSION_NAMES:
        va, vb = getattr(qa.dimensions, name), getattr(qb.dimensions, name)
        # A dimension the family needs must be pinned on BOTH sides; any other
        # dimension pinned on one side only is a question too, because the
        # unpinned side may or may not cover the same population.
        if name in needed and (va is None or vb is None):
            out.append(name)
        elif (va is None) != (vb is None):
            out.append(name)
    return tuple(out)


def reconcile(a: Entity, b: Entity) -> Reconciliation:
    for e in (a, b):
        if e.kind is not Kind.FACT:
            raise ValueError(f"reconcile takes FACT entities, got {e.kind.value}")
    if a.payload.measure_id is None or a.payload.measure_id != b.payload.measure_id:
        raise ValueError("reconcile takes two facts on ONE measure_id; the caller joins on the measure, never on text")
    qa, qb = a.payload.quantity, b.payload.quantity
    if qa is None or qb is None:
        # A fact without a number cannot agree or disagree with one that has
        # one; the missing quantity is the thing to ask for.
        return Reconciliation("question", unpinned=("quantity",))

    unpinned = _unpinned(a, b)
    if unpinned:
        return Reconciliation("question", unpinned=unpinned)

    da, db = qa.dimensions, qb.dimensions
    if da.definition != db.definition or qa.unit_family is not qb.unit_family \
            or canonical_unit(qa.unit) != canonical_unit(qb.unit):
        return Reconciliation("conflict", ConflictKind.DEFINITION)

    for name in Dimensions.DIMENSION_NAMES:
        if name == "definition":
            continue
        if getattr(da, name) != getattr(db, name):
            return Reconciliation("distinct")

    if qa.value == qb.value:
        return Reconciliation("same")

    bases = {a.payload.basis, b.payload.basis}
    if bases == {FactBasis.CLIENT_STATED, FactBasis.DOCUMENT_VERIFIED}:
        return Reconciliation("conflict", ConflictKind.CLIENT_VS_RECORD)
    return Reconciliation("conflict", ConflictKind.VALUE)
