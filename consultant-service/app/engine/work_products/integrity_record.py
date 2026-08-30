"""The Integrity Record: the deliverable that says what the engine knows, how
it knows it, and what it does not know (design 11.5, spec section 7).

It is itself a work product and it is built the same way every other one is -
from registry queries - so it cannot describe a registry other than the one
that was rendered. It is also the `integrity` block of the release record
(design 12.4), which is why its shape is stable and why every list is present
even when empty: a missing section would read as "nothing to report", and
absence of evidence is not evidence of absence.

The laws this module enforces:

  I-R1  every unplanned work product is listed with the verdict that
        excluded it. A client can see what they did not get and why; a
        deliverable set that shrank silently would be the one failure the
        adaptive planner must never have
  I-R2  every correction applied to rendered text is listed, with where it
        was applied and under which of the two permitted laws
  I-R3  what is unknown is listed as unknown - open questions, questions the
        client answered "don't know", unpinned dimensions - never omitted and
        never filled in
  I-R4  the record carries the registry hash it was built from and each
        artifact's own sha256, so "this document describes that registry" is
        checkable rather than asserted (L8)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence, TYPE_CHECKING

from app.engine.types import (
    TERMINAL_STATUSES,
    ApprovalState,
    Entity,
    FactBasis,
    Finding,
    Kind,
    Status,
)
from app.engine.work_products import statements
from app.engine.work_products.decl import PlanVerdict, RenderingRules
from app.engine.work_products.render_md import ArtifactRef

if TYPE_CHECKING:
    from app.engine.registry import RegistryView


STATUS_CURRENT = "current"
STATUS_BLOCKED = "blocked"
STATUS_STALE = "stale"


@dataclass(frozen=True)
class ArtifactReport:
    """One rendered file as the record describes it. `pages` and
    `presentation_findings` come from the presentation gate; None means the
    gate has not run, which is not the same as a clean page."""
    ref: ArtifactRef
    pages: int | None = None
    presentation_findings: tuple[str, ...] = ()


def _rules(view: "RegistryView") -> RenderingRules:
    return statements.DEFAULT_RULES


def _live(view: "RegistryView", kind: Kind) -> list[Entity]:
    return sorted((e for e in view.query(kind) if e.status not in TERMINAL_STATUSES),
                  key=lambda e: e.id)


def _evidence_sources(view: "RegistryView") -> list[dict]:
    out = []
    for e in _live(view, Kind.EVIDENCE_SOURCE):
        p = e.payload
        out.append({"id": e.id, "name": p.name, "source_kind": p.source_kind.value,
                    "record_class": p.record_class.value,
                    "record_class_confirmed_by_client": p.record_class_confirmed_by_client,
                    "sha256": p.sha256})
    return out


def _confirmed_facts(view: "RegistryView") -> list[dict]:
    out = []
    for e in sorted(view.query(Kind.FACT, status=Status.CONFIRMED), key=lambda x: x.id):
        out.append({"id": e.id, "statement": statements.statement_text(e, view, rules=_rules(view)),
                    "basis": e.payload.basis.value, "authority": e.authority.value,
                    "locator": e.provenance.source_locator, "confirmed_by": e.confirmed_by,
                    "derived_from": list(e.provenance.derived_from)})
    return out


def _assumptions(view: "RegistryView") -> dict:
    approved, unapproved = [], []
    for e in _live(view, Kind.ASSUMPTION):
        row = {"id": e.id, "statement": statements.statement_text(e, view, rules=_rules(view)),
               "approval": e.payload.approval.value, "status": e.status.value,
               "used_by": list(e.payload.used_by)}
        # An assumption counts as approved only when it says so; an older row
        # with no approval recorded is unapproved, never assumed approved.
        if e.payload.approval is ApprovalState.APPROVED or e.status is Status.APPROVED:
            approved.append(row)
        else:
            unapproved.append(row)
    return {"approved": approved, "unapproved": unapproved}


def _calculations(view: "RegistryView", calc: Any) -> list[dict]:
    out = []
    for e in _live(view, Kind.FACT):
        if e.payload.basis is not FactBasis.CALCULATED:
            continue
        recomputed = None if calc is None else bool(calc.recompute(e, view))
        out.append({"id": e.id, "formula": e.payload.formula, "inputs": list(e.payload.inputs),
                    "result": statements.statement_text(e, view, rules=_rules(view)),
                    "recomputed": recomputed})
    return out


def _questions(view: "RegistryView") -> tuple[list[dict], list[dict]]:
    """(still open, answered "don't know"). I-R3: both are recorded; a hole
    the client cannot fill is a finding about the evidence, not a defect."""
    unresolved, unknowns = [], []
    for e in _live(view, Kind.QUESTION):
        row = {"id": e.id, "text": e.payload.text, "material": e.payload.material,
               "why": e.payload.why, "strategy": e.payload.strategy.value,
               "status": e.status.value}
        if e.payload.unknown is True:
            unknowns.append(row)
        elif e.status is Status.OPEN:
            unresolved.append(row)
    return unresolved, unknowns


def _unpinned_dimensions(view: "RegistryView") -> list[dict]:
    out = []
    for e in view.query():
        if e.status in TERMINAL_STATUSES:
            continue
        q = getattr(e.payload, "quantity", None)
        if q is None:
            continue
        missing = q.dimensions.unpinned()
        if missing:
            out.append({"id": e.id, "unpinned": list(missing)})
    return sorted(out, key=lambda r: r["id"])


def _conflicts(view: "RegistryView") -> dict:
    open_, resolved = [], []
    for e in _live(view, Kind.CONFLICT):
        p = e.payload
        row = {"id": e.id, "kind": p.kind.value, "subject_id": p.subject_id,
               "material": view.is_material(e) if hasattr(view, "is_material") else p.material,
               "conclusions": [{"entity_id": c.entity_id, "statement": c.statement} for c in p.conclusions]}
        if e.status is Status.RESOLVED or p.resolution_chosen:
            loser = [c.entity_id for c in p.conclusions if c.entity_id != p.resolution_chosen]
            resolved.append({**row, "chosen": p.resolution_chosen, "by": p.resolution_by,
                             "rationale": p.resolution_rationale, "loser": loser,
                             "loser_label": "superseded by the resolution; still recorded"})
        else:
            open_.append(row)
    return {"open": open_, "resolved": resolved}


def _regulated(view: "RegistryView") -> list[dict]:
    return [{"id": e.id, "domain": e.payload.domain.value, "adviser_class": e.payload.adviser_class,
             "withheld_interpretation": e.payload.withheld_interpretation,
             "status": e.status.value, "touches": list(e.payload.touches)}
            for e in _live(view, Kind.REGULATED_MATTER)]


def _recommendations(view: "RegistryView") -> list[dict]:
    out = []
    for e in _live(view, Kind.RECOMMENDATION):
        supports = view.supports_of(e.id)
        out.append({"id": e.id, "statement": statements.statement_text(e, view, rules=_rules(view)),
                    "supports": list(e.payload.supports),
                    "support_status": {s.id: s.status.value for s in supports},
                    "conditional_on": list(e.payload.conditional_on),
                    "licensed_interpretation": e.payload.licensed_interpretation})
    return out


def _work_products(view: "RegistryView", reports: Sequence[ArtifactReport]) -> list[dict]:
    by_product: dict[str, list[ArtifactReport]] = {}
    for r in reports:
        by_product.setdefault(r.ref.product_id, []).append(r)
    out = []
    for e in _live(view, Kind.WORK_PRODUCT):
        p = e.payload
        out.append({"id": e.id, "product_id": p.product_id, "title": p.title,
                    "planned_because": p.planned_because, "section_ids": list(p.section_ids),
                    "consumes": list(p.consumes),
                    "artifacts": [{"fmt": r.ref.fmt, "path": r.ref.path, "sha256": r.ref.sha256,
                                   "registry_hash": r.ref.registry_hash, "pages": r.pages,
                                   "presentation_findings": list(r.presentation_findings)}
                                  for r in by_product.get(p.product_id, [])]})
    return out


def _lineage(view: "RegistryView", mappings: Sequence[Any]) -> dict:
    supersessions = []
    for e in view.rows() if hasattr(view, "rows") else []:
        if e.supersedes is not None:
            supersessions.append({"id": e.id, "version": e.version, "supersedes": e.supersedes,
                                  "by": e.provenance.actor_ref})
    return {"supersessions": supersessions,
            "mappings": [m.as_dict() if hasattr(m, "as_dict") else dict(m) for m in mappings]}


def _model_calls(calls: Sequence[Mapping[str, Any]]) -> dict:
    cost: dict[str, float] = {}
    for c in calls:
        purpose = str(c.get("purpose") or "unknown")
        cost[purpose] = round(cost.get(purpose, 0.0) + float(c.get("cost_usd") or 0.0), 6)
    return {"count": len(calls), "cost_usd": cost}


def build_integrity_record(view: "RegistryView", *,
                           artifacts: Sequence[ArtifactReport] = (),
                           unplanned: Sequence[PlanVerdict] = (),
                           findings: Sequence[Finding] = (),
                           mappings: Sequence[Any] = (),
                           model_calls: Sequence[Mapping[str, Any]] = (),
                           legacy: Mapping[str, Any] | None = None,
                           calc: Any = None) -> dict:
    """The record, from queries. `unplanned`, `findings`, `mappings`,
    `model_calls` and `legacy` are the things the registry alone does not
    hold: the planner's verdicts, the gate's findings, this pass's
    corrections, the model ledger and the r30 package, each passed in by the
    caller that owns them."""
    unresolved, unknowns = _questions(view)
    registry_hash = view.content_hash()
    blocking = [f for f in findings if f.blocks_final]
    stale = [r for r in artifacts if r.ref.registry_hash and r.ref.registry_hash != registry_hash]

    if blocking:
        status = STATUS_BLOCKED
    elif stale:
        # L8's condition, stated positively: an artifact rendered from another
        # registry does not describe this one, whatever it says.
        status = STATUS_STALE
    else:
        status = STATUS_CURRENT

    return {
        "status": status,
        "verification_status": status,
        "registry_hash": registry_hash,
        "content_hash": registry_hash,
        "evidence_sources": _evidence_sources(view),
        "confirmed_facts": _confirmed_facts(view),
        "assumptions": _assumptions(view),
        "calculations": _calculations(view, calc),
        "unresolved_questions": unresolved,
        "unknowns": {"questions_answered_unknown": unknowns,
                     "unpinned_dimensions": _unpinned_dimensions(view)},
        "conflicts": _conflicts(view),
        "qualified_adviser_requirements": _regulated(view),
        "recommendations": _recommendations(view),
        "work_products": _work_products(view, artifacts),
        # I-R1: the verdict that excluded each product, in the planner's own
        # count words, so absence is explained rather than noticed.
        "work_products_unplanned": [{"product_id": v.product_id, "because": v.because}
                                    for v in unplanned],
        "laws": [f.as_dict() for f in findings],
        "findings": [f.as_dict() for f in findings],
        "blocked": [f.as_dict() for f in blocking],
        "lineage": _lineage(view, mappings),
        "mappings_applied": len(mappings),
        "model_calls": _model_calls(model_calls),
        # The r30 package, when one was delivered. `None` is not "no legacy
        # work": it is "this engagement has none", and the key is always here
        # so a reader never has to guess which it was (MF2.8 keeps these
        # references out of corrections_current_pass).
        "legacy": dict(legacy) if legacy is not None else None,
    }
