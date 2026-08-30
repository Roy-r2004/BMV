"""Adaptive work-product planning (design 10.2): which of the 21 declared
products this engagement gets is a function of counts over the registry,
bounded by MIN/MAX_WORK_PRODUCTS, with every non-plan explained.

The laws this module enforces:

  P3       the mandatory products (Always) are always in the plan; if the
           declarations cannot yield MIN_WORK_PRODUCTS the planner refuses
           rather than inventing a product
  bounds   the plan never exceeds MAX_WORK_PRODUCTS; when it would, the
           lowest-count verdicts are dropped first and listed as unplanned,
           so a small registry and a large one differ in what they get, not
           in whether the cap held
  lineage  a planned WORK_PRODUCT row records planned_because (the verdict's
           counts), section_ids (section-level applicability) and consumes
           (the matched entity ids), so the Integrity Record can show why
           each product exists and why each absent one does not

Nothing here reads text, an engagement type or a client name: the verdicts
come from Predicate.evaluate over FILTERABLE_FIELDS, which is why scrambling
every text field yields an identical plan.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, TYPE_CHECKING

from app.engine.types import (
    BOUNDS,
    Actor,
    Add,
    Confidence,
    DecisionRole,
    Kind,
    Provenance,
    RelationToCentralDecision,
    Relevance,
    Status,
    TERMINAL_STATUSES,
    WorkProductPayload,
    make_entity,
)
from app.engine.work_products.decl import (
    AllOf,
    Always,
    AnyOf,
    Count,
    PlanVerdict,
    Predicate,
    WORK_PRODUCTS,
    WorkProductDecl,
    plan_sections,
)

if TYPE_CHECKING:
    from app.engine.registry import RegistryView


@dataclass(frozen=True)
class WorkProductPlan:
    """One planning pass: the deltas to write, and every verdict either way.
    The unplanned verdicts are not discarded - the Integrity Record renders
    them, so absence is explained (absent evidence is a fact, not a defect)."""
    deltas: tuple[Add, ...]
    planned: tuple[PlanVerdict, ...]
    unplanned: tuple[PlanVerdict, ...]


def _plan_bounds(overrides: Mapping[str, int] | None) -> tuple[int, int]:
    """MIN/MAX_WORK_PRODUCTS from the caller's bounds mapping when given
    (MethodContext.settings carries one), else the live settings, else the
    frozen defaults - never a literal in this module."""
    def read(name: str) -> int:
        if overrides is not None and name in overrides:
            return int(overrides[name])
        try:
            from app.config import settings
            v = getattr(settings, f"ENGINE_{name}", None)
            if v is not None:
                return int(v)
        except Exception:
            pass
        return int(BOUNDS[name])
    return read("MIN_WORK_PRODUCTS"), read("MAX_WORK_PRODUCTS")


def _specs_of(pred: Predicate):
    """Every InputSpec a predicate counts, in declaration order. The walk is
    closed over the four predicate types on purpose: a fifth would be a new
    law, not a silent branch."""
    if isinstance(pred, Count):
        yield pred.spec
    elif isinstance(pred, (AllOf, AnyOf)):
        for p in pred.parts:
            yield from _specs_of(p)
    elif isinstance(pred, Always):
        return
    else:
        raise TypeError(f"unknown predicate {type(pred).__name__}")


def _match_count(pred: Predicate, view: "RegistryView") -> int | None:
    """How much evidence stands behind a verdict: the total matched count
    across the predicate's specs. None for Always - a mandatory product has
    no count to be ranked (and is never dropped) (P3)."""
    if isinstance(pred, Always):
        return None
    return sum(sum(1 for e in view.query(s.kind) if s.matches(e)) for s in _specs_of(pred))


def _consumes(decl: WorkProductDecl, view: "RegistryView") -> tuple[str, ...]:
    """The ids the verdict and the sections matched, first-seen order: the
    product's lineage, written into the row so 'why does this exist' is a
    query, not a reconstruction."""
    seen: dict[str, None] = {}
    specs = list(_specs_of(decl.applicability))
    for s in decl.sections:
        specs.extend(s.query)
    for spec in specs:
        for e in view.query(spec.kind):
            if spec.matches(e):
                seen.setdefault(e.id, None)
    return tuple(seen)


def _first_live_field(view: "RegistryView", kind: Kind, flag: str | None, field_name: str) -> str | None:
    for e in view.query(kind):
        if e.status in TERMINAL_STATUSES:
            continue
        if flag is None or e.field(flag) is True:
            v = getattr(e.payload, field_name, None)
            if v:
                return str(v)
    return None


def _render_title(decl: WorkProductDecl, view: "RegistryView") -> str:
    """Titles come from entity fields, never from an engagement label: the
    central decision's own statement, the clock-starting deadline's own text,
    the legacy workstream's own name. A hole renders as the declared unknown
    text - unknown stays unknown, it is not defaulted away."""
    unknown = decl.rules.unknown_text
    central = None
    for e in view.query(Kind.DECISION):
        if e.status not in TERMINAL_STATUSES and e.field("role") == DecisionRole.CENTRAL.value:
            central = e.payload.statement
            break
    ctx = {
        "central_decision": central or unknown,
        "deadline": _first_live_field(view, Kind.DEADLINE, "starts_clock", "text") or unknown,
        "workstream": _first_live_field(view, Kind.WORKSTREAM, "has_legacy_request", "name")
        or _first_live_field(view, Kind.WORKSTREAM, None, "name") or unknown,
    }
    return decl.title_template.format_map(ctx)


def _existing_product_ids(view: "RegistryView") -> frozenset[str]:
    return frozenset(e.payload.product_id for e in view.query(Kind.WORK_PRODUCT)
                     if e.status not in TERMINAL_STATUSES)


def plan_work_products(view: "RegistryView", preliminary: bool = False, *,
                       bounds: Mapping[str, int] | None = None) -> WorkProductPlan:
    """Evaluate every declaration against the registry. Planned products
    become WORK_PRODUCT rows (Add deltas); a preliminary pass (the charter's
    expected-deliverables list) returns the same verdicts and writes nothing,
    so discovery can promise only what the evidence at that moment supports."""
    min_wp, max_wp = _plan_bounds(bounds)

    candidates: list[tuple[WorkProductDecl, str, int | None]] = []
    unplanned: list[PlanVerdict] = []
    for decl in WORK_PRODUCTS.all():
        holds, because = decl.applicability.evaluate(view)
        if holds:
            candidates.append((decl, because, _match_count(decl.applicability, view)))
        else:
            unplanned.append(PlanVerdict(decl.id, planned=False, because=because))

    # The cap: mandatory products are never dropped (P3); among the rest the
    # thinnest evidence goes first, deterministically (count, then id), and
    # every drop is a visible unplanned verdict, not a silent shrink.
    if len(candidates) > max_wp:
        droppable = sorted((c for c in candidates if c[2] is not None), key=lambda c: (c[2], c[0].id))
        to_drop = {c[0].id for c in droppable[:len(candidates) - max_wp]}
        for decl, because, _ in candidates:
            if decl.id in to_drop:
                unplanned.append(PlanVerdict(decl.id, planned=False,
                                             because=f"held ({because}) but over MAX_WORK_PRODUCTS={max_wp}"))
        candidates = [c for c in candidates if c[0].id not in to_drop]

    if len(candidates) < min_wp:
        # The two Always declarations guarantee the floor; being under it
        # means the declarations themselves were mutated, and the planner
        # refuses to hand a client less than the mandatory set.
        raise ValueError(f"P3: {len(candidates)} products planned, below MIN_WORK_PRODUCTS={min_wp}; "
                         "the mandatory declarations are missing")

    central = next((e for e in view.query(Kind.DECISION)
                    if e.status not in TERMINAL_STATUSES and e.field("role") == DecisionRole.CENTRAL.value), None)
    already = _existing_product_ids(view)

    planned: list[PlanVerdict] = []
    deltas: list[Add] = []
    for decl, because, _ in candidates:
        section_ids = plan_sections(decl, view)
        planned.append(PlanVerdict(decl.id, planned=True, because=because, section_ids=section_ids))
        if preliminary or decl.id in already:
            # Preliminary passes promise, they do not record; a re-plan never
            # duplicates a product row the registry already holds live.
            continue
        consumes = _consumes(decl, view)
        payload = WorkProductPayload(product_id=decl.id, title=_render_title(decl, view),
                                     planned_because=because, section_ids=section_ids, consumes=consumes)
        deltas.append(Add(make_entity(
            kind=Kind.WORK_PRODUCT, engagement_id=view.engagement_id, payload=payload,
            provenance=Provenance(actor=Actor.SYSTEM, actor_ref="planner:synthesis", derived_from=consumes),
            confidence=Confidence(None), relevance=Relevance(central.id if central else None, 0.0),
            relation=RelationToCentralDecision.INFORMS, status=Status.PROPOSED)))

    return WorkProductPlan(deltas=tuple(deltas), planned=tuple(planned), unplanned=tuple(unplanned))
