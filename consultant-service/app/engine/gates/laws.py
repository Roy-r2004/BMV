"""L1-L14: the gate, as fourteen registry and artifact queries (design 12.1).

The gate is the law list. `LAWS` holds one `Law` per `LawId`, each a pure
query over the registry and the rendered artifacts; an entry IS the law, so
removing one is exactly the mutation its test catches, and adding a
fifteenth principle means adding a fifteenth entry, not editing a function.

What each law refuses to let out of the door:

  L1  a material conflict still open. Materiality is RECOMPUTED here from the
      live support graph (MF2.4); the stored flag is a rendering snapshot and
      a conflict written before the recommendation that now rests on it would
      carry material=False
  L2  a recommendation that traces to nothing
  L3  an unapproved assumption printed without the approval label
  L4  a regulated matter nobody routed, and licensed interpretation printed
      as advice
  L5  a material question still open
  L6  a claim restated in other words beside its canonical wording
  L7  a stored calculation that does not come back from its own formula,
      EXACTLY (see RECOMPUTE_TOLERANCE)
  L8  an artifact that does not describe the registry it claims to, or a file
      whose bytes no longer match the hash the record carries
  L9  a page a reader cannot read (gates/presentation.py: all three checks)
  L10 two comparable facts on one measure, both printed, neither reconciled
  L11 a figure on the page that matches no registered quantity
  L12 an objective the arithmetic refutes that was never put to the client
  L13 a delivered r30 package that is not itself FINAL
  L14 a client's own quoted words rewritten on the page (MF2.6)

Four of them - L3, L6, L11, L14 - read the EXTRACTED text of the frozen file
rather than the markdown (design 12.3), because the page is what the client
receives and the markdown is not.

The queries live on `EngagementRegistry` (registry.py), never here: a gate
that re-derived materiality or support would be a second definition of them,
and the two would drift. What lives here is the decision each query implies.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Sequence, TYPE_CHECKING

from app.engine.gates import presentation
from app.engine.types import (
    TERMINAL_STATUSES,
    Entity,
    Finding,
    Kind,
    Severity,
    Status,
)

if TYPE_CHECKING:                                         # the read side is a protocol
    from app.engine.registry import RegistryView


# =============================================================================
# The contract (contracts section 14)
# =============================================================================

class LawId(str, Enum):
    L1 = "L1.material_open_conflict"
    L2 = "L2.unsupported_recommendation"
    L3 = "L3.unlabelled_assumption"
    L4 = "L4.unrouted_regulated_matter"
    L5 = "L5.material_open_question"
    L6 = "L6.statement_drift"
    L7 = "L7.calculation_does_not_recompute"
    L8 = "L8.hash_mismatch"
    L9 = "L9.presentation"
    L10 = "L10.unreconciled_facts_rendered"
    L11 = "L11.untraceable_number"
    L12 = "L12.infeasible_objective_without_decision"
    L13 = "L13.legacy_r30_not_final"
    L14 = "L14.client_fact_not_verbatim"


@dataclass(frozen=True)
class ArtifactRef:
    """One rendered file as the gate sees it: where it is, what it hashes to,
    which registry it was rendered FROM (staleness is a comparison, not a
    guess) and the chrome-stripped text the semantic laws read."""
    product_id: str
    fmt: str
    path: str
    sha256: str
    registry_hash: str
    extracted_text: str = ""


@dataclass(frozen=True)
class Law:
    id: LawId
    run: Callable[["RegistryView", Sequence[ArtifactRef]], list[Finding]]
    blocks_final: bool = True


class LawRegistry:
    """LAWS is the gate: an entry IS the law, and removing it is the mutation
    its test catches."""

    def __init__(self) -> None:
        self._laws: dict[LawId, Law] = {}

    def register(self, law: Law) -> Law:
        if law.id in self._laws:
            raise ValueError(f"law {law.id.value} already registered")
        self._laws[law.id] = law
        return law

    def all(self) -> list[Law]:
        return [self._laws[k] for k in LawId if k in self._laws]

    def run_all(self, view: "RegistryView", artifacts: Sequence[ArtifactRef]) -> list[Finding]:
        out: list[Finding] = []
        for law in self.all():
            for f in law.run(view, artifacts):
                out.append(f if f.blocks_final == law.blocks_final else replace(f, blocks_final=law.blocks_final))
        return out


LAWS = LawRegistry()


# =============================================================================
# Constants the laws state rather than assume
# =============================================================================

# L7 is EQUALITY. Not 0.05% (decompose.py:193, r30's print-repair threshold)
# and not 0.5% (timebasis.py:73, which governs a RENDERED restatement under
# L11): a stored number that does not come back from its own formula is
# wrong, and the size of the gap is not the question.
RECOMPUTE_TOLERANCE = Decimal("0")

# The legacy r30 release decision for one delivered package, read with r30's
# own gate (export_pdf.release_status, integrity.current_report). Injectable
# so L13 can be pinned without a database; the default reads the Request row.
LEGACY_STATUS: Callable[[int], Mapping[str, Any]] | None = None

_ENDERS = ".?!"


# =============================================================================
# Shared reading
# =============================================================================

def _live(view: "RegistryView", kind: Kind) -> list[Entity]:
    return [e for e in view.query(kind) if e.status not in TERMINAL_STATUSES]


def _statement_text(e: Entity, view: "RegistryView") -> str:
    """The one canonical wording of one row. Imported from the renderer, never
    re-derived: a law that spelled a claim differently from the page would
    judge a document nobody printed."""
    from app.engine.work_products import statements

    return statements.statement_text(e, view)


def _pages(artifacts: Sequence[ArtifactRef]) -> list[tuple[ArtifactRef, str]]:
    """(artifact, the text a reader reads) for every artifact that carries
    any. An artifact with no extracted text is not skipped silently: the laws
    that need the page simply have nothing to read, and L8 is what notices a
    file that should have text and has none."""
    out = []
    for ref in artifacts:
        text = presentation.readable_text(ref)
        if text:
            out.append((ref, text))
    return out


def _where(ref: ArtifactRef) -> str:
    return f"{ref.product_id}:{ref.fmt}"


def _finding(law: LawId, where: str, issue: str, fix: str, *, ids: Sequence[str] = (),
             severity: Severity = Severity.HIGH) -> Finding:
    return Finding(law=law.value, where=where, issue=issue, fix=fix, severity=severity,
                   entity_ids=tuple(ids), blocks_final=True)


def _sentences(text: str) -> list[str]:
    """Whitespace-collapsed sentences. Hand-split rather than matched: a
    terminator followed by a space ends a sentence, and "4.2" does not,
    because the digit after the stop is not a space. The engine's text tools
    stay literal (design 18)."""
    flat = presentation.normalise(text)
    out: list[str] = []
    buf: list[str] = []
    for i, ch in enumerate(flat):
        buf.append(ch)
        if ch in _ENDERS and (i + 1 >= len(flat) or flat[i + 1] == " "):
            out.append("".join(buf).strip())
            buf = []
    if buf:
        out.append("".join(buf).strip())
    return [s for s in out if s]


def _blank_out(text: str, spans: Iterable[str]) -> str:
    """`text` with every span replaced by spaces of the same length. Longest
    first, so a claim nested inside a longer claim is blanked once as part of
    the longer one; same-length blanking keeps every offset true of the
    original."""
    out = text or ""
    for span in sorted({s for s in spans if s}, key=lambda s: (-len(s), s)):
        out = out.replace(span, " " * len(span))
    return out


def _numbers_in(text: str):
    """r30's number reader (registry._numbers, registry.py:231), imported so a
    figure is read on the page exactly as the r30 gate reads it."""
    from app.pipeline.registry import _numbers

    return _numbers(text or "")


# =============================================================================
# L1 - a material conflict still open
# =============================================================================

def law_material_open_conflict(view: "RegistryView", artifacts: Sequence[ArtifactRef]) -> list[Finding]:
    out = []
    for c in view.query(Kind.CONFLICT, status=Status.OPEN):
        # MF2.4: materiality is RECOMPUTED from the live support graph at the
        # moment of asking. `payload.material` is a rendering snapshot -- a
        # conflict written before the recommendation that now rests on it
        # carries False, and reading it would wave the conflict through.
        if not view.is_material(c):
            continue
        out.append(_finding(
            LawId.L1, c.id,
            f"a material conflict on {c.payload.subject_id} is still open "
            f"({c.payload.kind.value}); the deliverable rests on one of its conclusions",
            "resolve it with the authority the conflict names, or withdraw what rests on it",
            ids=(c.id,) + tuple(x.entity_id for x in c.payload.conclusions)))
    return out


# =============================================================================
# L2 - a recommendation that traces to nothing
# =============================================================================

def law_unsupported_recommendation(view: "RegistryView", artifacts: Sequence[ArtifactRef]) -> list[Finding]:
    """The synthesis check, re-run at the gate. It is the SAME function, so a
    finding raised while analysing and one raised at release carry one
    wording; the gate re-runs it because supports can be superseded after
    synthesis ran."""
    from app.engine.synthesis.recommend import support_findings

    return list(support_findings(view))


# =============================================================================
# L3 - an unapproved assumption printed without its label
# =============================================================================

def _assumption_spans(view: "RegistryView") -> list[tuple[Entity, str, str]]:
    """(assumption, the claim without its label, the claim with it) for every
    live unapproved assumption."""
    from app.pipeline.registry import PROPOSED_LABEL

    out = []
    for a in view.unapproved_assumptions():
        full = presentation.normalise(_statement_text(a, view))
        core = full[:-len(PROPOSED_LABEL)].strip() if full.endswith(PROPOSED_LABEL) else full
        out.append((a, core, full))
    return out


def law_unlabelled_assumption(view: "RegistryView", artifacts: Sequence[ArtifactRef]) -> list[Finding]:
    """On the EXTRACTED page (design 12.3), the way integrity.label_findings
    (integrity.py:680) reads it: a proposal printed without the approval label
    reads as a finding, which is the whole failure this law exists for."""
    from app.pipeline.registry import PROPOSED_LABEL

    out = []
    for ref, text in _pages(artifacts):
        for a, core, full in _assumption_spans(view):
            if not core or core not in text:
                continue                                  # this page does not print it
            if full in text:
                continue
            out.append(_finding(
                LawId.L3, f"{_where(ref)}:{a.id}",
                f"the unapproved assumption {a.id} is printed without {PROPOSED_LABEL}",
                "render assumptions through statement_text, which appends the label",
                ids=(a.id,)))
    return out


# =============================================================================
# L4 - regulated matter unrouted, licensed interpretation printed
# =============================================================================

def law_unrouted_regulated_matter(view: "RegistryView", artifacts: Sequence[ArtifactRef]) -> list[Finding]:
    out = []
    for m in view.unrouted_regulated_matters():
        out.append(_finding(
            LawId.L4, m.id,
            f"a {m.payload.domain.value} matter is {m.status.value}, not routed to a "
            f"{m.payload.adviser_class}",
            "route the matter to a qualified adviser; nothing inside the engine can clear it",
            ids=(m.id,)))
    for r in view.licensed_recommendations():
        out.append(_finding(
            LawId.L4, r.id,
            "a recommendation carrying licensed interpretation is live as advice",
            "render it as a decision required from an adviser, not as a recommendation",
            ids=(r.id,)))
    # And on the page: an unrouted matter's own subject printed as if it were
    # settled. Under-routing is the dangerous direction (design 9.6), so a
    # claim a matter touches is checked where the client will read it.
    for ref, text in _pages(artifacts):
        for m in _live(view, Kind.REGULATED_MATTER):
            if m.status is Status.ROUTED:
                continue
            for touched in m.payload.touches:
                e = view.get(touched)
                if e is None or e.status in TERMINAL_STATUSES:
                    continue
                claim = presentation.normalise(_statement_text(e, view))
                if claim and claim in text:
                    out.append(_finding(
                        LawId.L4, f"{_where(ref)}:{touched}",
                        f"{touched} is printed while the {m.payload.domain.value} matter {m.id} "
                        f"that it raises is {m.status.value}",
                        "route the matter, or remove the claim from the deliverable",
                        ids=(m.id, touched)))
    return out


# =============================================================================
# L5 - a material question still open
# =============================================================================

def law_material_open_question(view: "RegistryView", artifacts: Sequence[ArtifactRef]) -> list[Finding]:
    return [_finding(LawId.L5, q.id,
                     f"a material question is still open: {q.payload.text}",
                     "answer it, record it as unknown, or make what depends on it conditional",
                     ids=(q.id,))
            for q in view.open_material_questions()]


# =============================================================================
# L6 - a claim restated in other words
# =============================================================================

def _canonical_claims(view: "RegistryView") -> list[str]:
    """Every string the registry itself can print: the canonical wording of
    every live row, plus the text every STATEMENT holds. These are the claims
    a page is allowed to carry a figure inside; a figure anywhere else is a
    figure the prose is restating on its own account."""
    claims = {presentation.normalise(s.payload.text) for s in _live(view, Kind.STATEMENT)}
    for e in view.query():
        if e.status in TERMINAL_STATUSES:
            continue
        claims.add(presentation.normalise(_statement_text(e, view)))
    return [c for c in claims if c]


def _traced(value: float, unit: str, known, tolerance: float) -> str | None:
    """The registered quantity a printed figure restates, or None. The match
    is r30's own: unit compatibility (`_unit_compatible`, registry.py:1700)
    and closeness within the declared tolerance (`_close`, :227). L6 and L11
    read a figure with one reader, so every figure on a page is either
    traceable and governed by L6, or untraceable and governed by L11."""
    from app.pipeline.registry import _close, _unit_compatible

    for entity_id, q in known:
        claim = {"unit": q.unit, "time_basis": q.dimensions.period_basis or "n/a"}
        if _unit_compatible(unit, claim) and _close(value, float(q.value), tolerance):
            return entity_id
    return None


def law_statement_drift(view: "RegistryView", artifacts: Sequence[ArtifactRef]) -> list[Finding]:
    """The generalisation of pilot_gate.is_paraphrase (pilot_gate.py:530).

    A claim is written once and printed by token substitution, so on the page
    it appears as its canonical wording and nowhere else. Blank every
    canonical claim out of the extracted text and any figure left standing is
    a claim the prose restated in its own words - and a reader cannot tell
    which of the two wordings governs. The complement (a figure that traces to
    nothing at all) is L11: between them, every figure on the page is judged.
    """
    from app.engine.work_products.render_md import bound, registered_quantities

    known = registered_quantities(view)
    if not known:
        return []
    tolerance = float(bound("RENDERED_RESTATEMENT_TOLERANCE"))
    claims = _canonical_claims(view)
    out = []
    for ref, text in _pages(artifacts):
        # Blanked first: what a token stands for IS the claim, and this law is
        # about what is said beside it. Remove the blanking and every claim
        # reports itself, which is the mutation the passing fixture catches.
        rest = _blank_out(text, claims)
        for sentence in _sentences(rest):
            for tok, value, unit, _start, _end in _numbers_in(sentence):
                entity_id = _traced(value, unit, known, tolerance)
                if entity_id is None:
                    continue                              # L11 owns a figure that traces to nothing
                out.append(_finding(
                    LawId.L6, f"{_where(ref)}:{entity_id}",
                    f"the figure {tok!r} restates {entity_id} outside its claim: \"{sentence[:180]}\"",
                    "reference the claim by its statement token; the engine substitutes the exact wording",
                    ids=(entity_id,)))
                break                                     # one finding per restating sentence
    return out


# =============================================================================
# L7 - a calculation that does not recompute
# =============================================================================

def _recompute_drift(fact: Entity, view: "RegistryView") -> Decimal | None:
    """|stored - recomputed| / |stored| for one calculated FACT, or None when
    the formula cannot be run at all (a missing input, an unreadable formula).
    The arithmetic is the calculator's own (calc/arith.evaluate), so the gate
    and the engine never disagree about what a formula means."""
    # `_quantise` is the calculator's own rounding. Imported rather than
    # restated: two rounding rules would mean a stored value the engine calls
    # exact and the gate calls wrong.
    from app.engine.calc.arith import _quantise, evaluate, quantity_of

    payload = fact.payload
    stored = payload.quantity
    if stored is None or not payload.formula or not payload.inputs:
        return None
    values: dict[str, Decimal] = {}
    for entity_id in payload.inputs:
        e = view.get(entity_id)
        q = quantity_of(e) if e is not None else None
        if q is None:
            return None
        values[entity_id] = q.value
    try:
        got = evaluate(payload.formula, values)
        got = _quantise(got, stored.precision)
    except (ValueError, ZeroDivisionError, ArithmeticError, InvalidOperation):
        return None
    if stored.value == 0:
        return Decimal(0) if got == 0 else Decimal(1)
    return abs(got - stored.value) / abs(stored.value)


def law_calculation_does_not_recompute(view: "RegistryView", artifacts: Sequence[ArtifactRef]) -> list[Finding]:
    out = []
    for f in view.calculated_facts():
        drift = _recompute_drift(f, view)
        if drift is None:
            out.append(_finding(
                LawId.L7, f.id,
                f"the calculation {f.id} cannot be recomputed: its formula or one of its inputs is missing",
                "record the formula and every input, or record the number as a fact with its source",
                ids=(f.id,) + tuple(f.payload.inputs)))
        elif drift > RECOMPUTE_TOLERANCE:
            out.append(_finding(
                LawId.L7, f.id,
                f"the stored value of {f.id} is not what its formula yields "
                f"(off by {drift * 100:.4f}% of the stored value)",
                "store the computed value, or correct the formula and its inputs",
                ids=(f.id,) + tuple(f.payload.inputs)))
    return out


# =============================================================================
# L8 - an artifact that describes another registry, or another file
# =============================================================================

def law_hash_mismatch(view: "RegistryView", artifacts: Sequence[ArtifactRef]) -> list[Finding]:
    """Two comparisons, both recomputed at the gate. An artifact rendered from
    an earlier registry does not describe this one whatever it says, and a
    file whose bytes changed after it was hashed is not the file that was
    checked (export_pdf.py:1756 is the cache rule this states as a law)."""
    now = view.content_hash()
    out = []
    for ref in artifacts:
        if ref.registry_hash and ref.registry_hash != now:
            out.append(_finding(
                LawId.L8, _where(ref),
                f"{ref.fmt} was rendered from registry {ref.registry_hash[:12]} and the registry is now "
                f"{now[:12]}",
                "re-render the artifact from the current registry before releasing it"))
        if not ref.path or not os.path.isfile(ref.path):
            out.append(_finding(
                LawId.L8, _where(ref),
                f"the artifact recorded at {ref.path or '<no path>'} is not on disk to be hashed",
                "render the artifact, or remove it from the release"))
            continue
        actual = presentation.sha256_of_file(ref.path)
        if actual != ref.sha256:
            out.append(_finding(
                LawId.L8, _where(ref),
                f"the file no longer hashes to what the record carries ({actual[:12]} vs {ref.sha256[:12]})",
                "re-hash the artifact; a release is valid only for the exact bytes it names"))
    return out


# =============================================================================
# L9 - the page itself
# =============================================================================

def law_presentation(view: "RegistryView", artifacts: Sequence[ArtifactRef]) -> list[Finding]:
    """All three checks (gates/presentation.py), on every PDF. Dropping any
    one of them leaves a class of broken page that nothing else looks at:
    fonts and glyphs, page completeness and stamping, clipping."""
    out: list[Finding] = []
    for ref in artifacts:
        if ref.fmt != "pdf" or not ref.path or not os.path.isfile(ref.path):
            continue
        out += presentation.presentation_gate(ref.path, where=_where(ref))
    return out


# =============================================================================
# L10 - two comparable facts on one measure, both printed
# =============================================================================

def law_unreconciled_facts_rendered(view: "RegistryView", artifacts: Sequence[ArtifactRef]) -> list[Finding]:
    """Reconciliation joins on measure_id and nothing else (MF1.6). Two live
    facts on one measure whose quantities are comparable and different are a
    conflict that has not been resolved; printing both leaves the reader to
    choose."""
    from app.engine.calc.units import comparable

    pages = _pages(artifacts)
    if not pages:
        return []
    out = []
    for measure_id, facts in sorted(view.facts_by_measure().items()):
        ordered = sorted(facts, key=lambda f: f.id)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1:]:
                qa, qb = a.payload.quantity, b.payload.quantity
                if qa is None or qb is None or comparable(qa, qb) != "comparable":
                    continue
                if qa.value == qb.value:
                    continue
                claim_a = presentation.normalise(_statement_text(a, view))
                claim_b = presentation.normalise(_statement_text(b, view))
                for ref, text in pages:
                    if claim_a in text and claim_b in text:
                        out.append(_finding(
                            LawId.L10, f"{_where(ref)}:{measure_id}",
                            f"{a.id} and {b.id} state different comparable values for one measure "
                            f"({measure_id}) and both are printed",
                            "reconcile them: resolve the conflict, or pin the dimension that makes "
                            "them distinct",
                            ids=(a.id, b.id, measure_id)))
    return out


# =============================================================================
# L11 - a figure that traces to nothing
# =============================================================================

def law_untraceable_number(view: "RegistryView", artifacts: Sequence[ArtifactRef]) -> list[Finding]:
    """The renderer's own check, re-run on the EXTRACTED page. render_md is
    imported here rather than at the top of the module because it declares its
    ArtifactRef from this one: the cycle is real, and the lazy import is what
    keeps a single ArtifactRef class in the process."""
    from app.engine.work_products.render_md import untraceable_number_findings

    out: list[Finding] = []
    for ref, text in _pages(artifacts):
        for f in untraceable_number_findings(text, view, where=_where(ref)):
            out.append(replace(f, law=LawId.L11.value, severity=Severity.HIGH, blocks_final=True))
    return out


# =============================================================================
# L12 - an objective the arithmetic refutes, never put to the client
# =============================================================================

def law_infeasible_objective_without_decision(view: "RegistryView",
                                              artifacts: Sequence[ArtifactRef]) -> list[Finding]:
    return [_finding(LawId.L12, o.id,
                     f"the registered facts show {o.id} infeasible and no decision was put to the client",
                     "raise a DECISION_REQUIRED from the client: the objective is theirs to change",
                     ids=(o.id,))
            for o in view.infeasible_objectives_without_decision()]


# =============================================================================
# L13 - a delivered r30 package that is not itself FINAL
# =============================================================================

def default_legacy_status(request_id: int) -> Mapping[str, Any]:
    """r30's own release decision for one delivered package: its gate reasons
    (export_pdf.release_status) and its integrity report
    (integrity.current_report). Read, never written -- the adapter's Request
    row is frozen after the pipeline returns (design 13.4)."""
    from app.database import SessionLocal
    from app.models import Request
    from app.pipeline import export_pdf, integrity

    db = SessionLocal()
    try:
        row = db.get(Request, int(request_id))
        if row is None:
            return {"found": False, "reasons": [], "integrity_current": False, "integrity_findings": []}
        gate = export_pdf.release_status(row)
        report = integrity.current_report(row)
        return {"found": True, "status": gate["status"], "reasons": list(gate["reasons"]),
                "integrity_current": report is not None,
                "integrity_findings": list((report or {}).get("findings") or [])}
    finally:
        db.close()


def legacy_request_ids(view: "RegistryView") -> list[int]:
    """Every r30 Request the engine commissioned for this engagement, read off
    the rows that carry one (payload_field `has_legacy_request`). There is no
    engagement-type switch here: a registry with no legacy row yields none."""
    ids: set[int] = set()
    for e in view.query():
        if e.status in TERMINAL_STATUSES:
            continue
        raw = getattr(e.payload, "legacy_request_id", None)
        if raw is None:
            continue
        try:
            ids.add(int(raw))
        except (TypeError, ValueError):                   # pragma: no cover - typed field
            continue
    return sorted(ids)


def law_legacy_r30_not_final(view: "RegistryView", artifacts: Sequence[ArtifactRef]) -> list[Finding]:
    """An engine release cannot be FINAL on top of a DRAFT r30 package. The
    reasons are r30's, read with r30's gate and reported unchanged: this law
    adds no opinion of its own, it refuses to ignore theirs."""
    reader = LEGACY_STATUS or default_legacy_status
    out = []
    for request_id in legacy_request_ids(view):
        status = reader(request_id) or {}
        where = f"legacy:{request_id}"
        if not status.get("found"):
            out.append(_finding(
                LawId.L13, where,
                f"the engagement cites r30 request {request_id} and the run cannot be found",
                "restore the run, or remove the legacy work from the engagement"))
            continue
        for reason in status.get("reasons") or []:
            out.append(_finding(
                LawId.L13, where,
                f"r30 request {request_id} is not final: {reason}",
                "clear the r30 finding and re-audit that package before releasing this engagement"))
        # Fail closed, and deliberately so: this flag is computed here and
        # now, not read off an older row, so "we could not confirm a current
        # report" and "there is none" are the same answer for a release.
        if not status.get("integrity_current"):
            out.append(_finding(
                LawId.L13, where,
                f"r30 request {request_id} has no current integrity report",
                "run the r30 integrity layer on the delivered content"))
        for finding in status.get("integrity_findings") or []:
            issue = finding.get("issue") if isinstance(finding, dict) else str(finding)
            out.append(_finding(
                LawId.L13, where,
                f"r30 request {request_id} carries an open integrity finding: {issue}",
                "close the r30 finding at its source and re-audit that package"))
    return out


# =============================================================================
# L14 - the client's own words, rewritten
# =============================================================================

def _client_quotes(view: "RegistryView") -> dict[str, Entity]:
    """The verbatim span of every CONFIRMED client-stated fact, as
    statement_text quotes it. I2 guarantees the span is the client's own
    words; this law guarantees those words reach the page unchanged."""
    return {presentation.normalise('"' + f.payload.statement + '"'): f
            for f in view.client_facts_confirmed() if f.payload.statement}


def _consumed_ids(view: "RegistryView", product_id: str) -> set[str]:
    """What a product printed, from the WORK_PRODUCT row the planner wrote."""
    for e in _live(view, Kind.WORK_PRODUCT):
        if e.payload.product_id == product_id:
            return set(e.payload.consumes)
    return set()


# statement_text renders a client fact as `"<the client's sentence>" <em dash>
# as stated by the client (...)`. Only punctuation may stand between the quote
# and the attribution; a word there means the page is attributing something
# other than the quotation to the client.
_MAX_ATTRIBUTION_GAP = 8


def _quoted_before(text: str, end: int) -> str | None:
    """The quoted span the attribution at `end` belongs to, or None. Scanned
    by hand rather than matched: this law is about exactness, and a pattern
    that had to decide what a quotation mark is would be the wrong tool."""
    close = text.rfind('"', 0, end)
    if close < 0:
        return None
    gap = text[close + 1:end]
    if len(gap) > _MAX_ATTRIBUTION_GAP or any(ch.isalnum() for ch in gap):
        return None                                       # a word stands between quote and attribution
    open_at = text.rfind('"', 0, close)
    if open_at < 0:
        return None
    return text[open_at:close + 1]


def law_client_fact_not_verbatim(view: "RegistryView", artifacts: Sequence[ArtifactRef]) -> list[Finding]:
    """MF2.6, checked where it matters: on the page.

    Two readings, both exact. First the page's own attributions: every
    "as stated by the client" on it must sit behind a quotation that IS some
    confirmed client fact's verbatim span - a canonical mapping that rewrote a
    word inside the quote leaves an attribution behind words the client never
    said. Then the other direction: a client fact the product consumed must be
    findable on the page it was printed on.
    """
    from app.engine.work_products.statements import CLIENT_STATED_SUFFIX

    marker = presentation.normalise(CLIENT_STATED_SUFFIX)
    quotes = _client_quotes(view)
    out = []
    for ref, text in _pages(artifacts):
        start = 0
        while True:
            at = text.find(marker, start)
            if at < 0:
                break
            start = at + len(marker)
            span = _quoted_before(text, at)
            if span is None:
                out.append(_finding(
                    LawId.L14, _where(ref),
                    "the page attributes a statement to the client without quoting them",
                    "render client facts through statement_text, which quotes the client verbatim"))
            elif span not in quotes:
                out.append(_finding(
                    LawId.L14, _where(ref),
                    f"a sentence attributed to the client is not what any confirmed client fact "
                    f"records: {span[:180]}",
                    "mask client-fact spans before applying canonical mappings (corrections.py C3)"))
        consumed = _consumed_ids(view, ref.product_id)
        for span, fact in sorted(quotes.items(), key=lambda kv: kv[1].id):
            if fact.id in consumed and span not in text:
                out.append(_finding(
                    LawId.L14, f"{_where(ref)}:{fact.id}",
                    f"the product consumed the client fact {fact.id} and its words are not on the page",
                    "print the client's sentence verbatim, or stop consuming the fact",
                    ids=(fact.id,)))
    return out


# =============================================================================
# Registration: the list IS the gate
# =============================================================================

LAWS.register(Law(LawId.L1, law_material_open_conflict))
LAWS.register(Law(LawId.L2, law_unsupported_recommendation))
LAWS.register(Law(LawId.L3, law_unlabelled_assumption))
LAWS.register(Law(LawId.L4, law_unrouted_regulated_matter))
LAWS.register(Law(LawId.L5, law_material_open_question))
LAWS.register(Law(LawId.L6, law_statement_drift))
LAWS.register(Law(LawId.L7, law_calculation_does_not_recompute))
LAWS.register(Law(LawId.L8, law_hash_mismatch))
LAWS.register(Law(LawId.L9, law_presentation))
LAWS.register(Law(LawId.L10, law_unreconciled_facts_rendered))
LAWS.register(Law(LawId.L11, law_untraceable_number))
LAWS.register(Law(LawId.L12, law_infeasible_objective_without_decision))
LAWS.register(Law(LawId.L13, law_legacy_r30_not_final))
LAWS.register(Law(LawId.L14, law_client_fact_not_verbatim))


def run_laws(view: "RegistryView", artifacts: Sequence[ArtifactRef] = ()) -> list[Finding]:
    """Every registered law over one registry and its artifacts."""
    return LAWS.run_all(view, tuple(artifacts))


def blocking(findings: Iterable[Finding]) -> list[Finding]:
    """The findings that hold a release. A LOW, non-blocking finding is
    recorded in the Integrity Record and does not stop the door."""
    return [f for f in findings if f.blocks_final]
