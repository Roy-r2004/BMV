"""current_state - WHAT on a FACT or a CAPABILITY: state what the registry
already establishes, and nothing more.

DETERMINISTIC, so M1 gives it zero model calls: there is nothing here for a
model to word. Everything it writes is a rearrangement of rows that already
exist, which is exactly why it is the method a diagnostic report's
current-state section can rest on.

Two outputs, two laws:

  C1  one summary FACT(inferred) per MEASURE that live facts are attached to,
      citing every fact in the group. Its quantity is copied only when every
      figure in the group is the identical Quantity; where they differ the
      summary carries NO quantity. Nothing averages, blends or silently
      selects (design 1, consequence 2) - the divergence stays visible for
      synthesis to raise as a CONFLICT, and a blended figure that matched no
      source would be a number this engagement never recorded.
      Mutation partner: _v_no_blended_summary.
  C2  a CAPABILITY the evidenced process actually runs through is PRESENT.
      The signal is structural - a live PROCESS_STEP naming the capability in
      system_ids - never a word in a payload's prose, so the same rule holds
      whatever the engagement is about. The existing row is SUPERSEDED rather
      than duplicated: the earlier judgement stays in lineage, visibly
      retired, instead of standing beside its own correction.

Re-running the method writes nothing new: a summary whose measure and cited
set already exist is skipped, and a capability already PRESENT is left alone.
An analysis that grew a row on every pass would inflate every count the work
product plan is built from.
"""
from __future__ import annotations

from typing import Any

from app.engine import types as T
from app.engine.authority import owner_of
from app.engine.calc.units import format_quantity
from app.engine.methods.builtin.capability_gap import added_of, evidenced_status, wording
from app.engine.methods.contract import (
    EvidenceRequirement,
    InputSpec,
    MethodContext,
    MethodResult,
    MethodSpec,
    QuestionShape,
    new_entity,
    register,
)
from app.engine.types import make_entity


def _live(view, kind: T.Kind) -> list[T.Entity]:
    """The engagement's current position for one kind. RegistryView promises
    query(), not live(), so the retirement filter is applied here."""
    return [e for e in view.query(kind) if e.status not in T.TERMINAL_STATUSES]


def _one_quantity(facts: list[T.Entity]) -> T.Quantity | None:
    """The group's figure when the group speaks with one voice, else None.

    Equality is the whole test: same value, same unit, same pinned
    dimensions. Two facts that differ in any of those are two claims, and the
    summary declines to choose between them (C1)."""
    quantities = [f.payload.quantity for f in facts if f.payload.quantity is not None]
    if not quantities or len(quantities) != len(facts):
        return None
    first = quantities[0]
    return first if all(q == first for q in quantities) else None


def _summary_text(measure: T.Entity | None, measure_id: str, facts: list[T.Entity]) -> str:
    """The summary sentence, assembled from what the cited rows already say.
    Every figure in it is a registered quantity rendered by the shared
    formatter, so no digit appears here that no cited input carries."""
    name = wording(measure) if measure is not None else measure_id
    parts = [format_quantity(f.payload.quantity) if f.payload.quantity is not None else f.payload.statement
             for f in facts]
    return f"As registered on {name}: " + "; ".join(parts)


def _v_no_blended_summary(view, result: MethodResult) -> list[T.Finding]:
    """C1 on the finished result: a summary fact whose quantity equals no
    cited input's quantity is a blend - the one number in a current-state
    report that no source would confirm. Absence decides nothing: a cited id
    the view cannot resolve is skipped rather than condemned."""
    out: list[T.Finding] = []
    for f in added_of(result, T.Kind.FACT):
        q = f.payload.quantity
        if q is None or f.payload.basis is not T.FactBasis.INFERRED:
            continue
        sources = [view.get(i) for i in f.provenance.derived_from]
        if any(s is not None and getattr(s.payload, "quantity", None) == q for s in sources):
            continue
        if all(s is None for s in sources):
            continue
        out.append(T.Finding(law="M.current_state.blended_summary", where=f.id or f.kind.value,
                             issue="a current-state summary carries a figure no cited fact carries",
                             fix="copy the group's figure only when every fact in it states the same one",
                             entity_ids=(f.id,) if f.id else ()))
    return out


_SUMMARY_ONLY_BASES: frozenset[T.FactBasis] = frozenset({T.FactBasis.INFERRED})


def _v_summary_basis_is_inferred(view, result: MethodResult) -> list[T.Finding]:
    """A summary is an inference, and says so. A method that wrote its own
    conclusion as CLIENT_STATED would put words in the client's mouth and as
    DOCUMENT_VERIFIED would claim a quote no document contains; either one
    outranks the real sources in CURRENT_STATE_PRECEDENCE and would win the
    conflict against them."""
    return [T.Finding(law="M.current_state.manufactured_basis", where=f.id or f.kind.value,
                      issue=f"a summarising method wrote a fact with basis {f.payload.basis.value}",
                      fix="a method's own conclusion about the current state is inferred, never recorded or recalled",
                      entity_ids=(f.id,) if f.id else ())
            for f in added_of(result, T.Kind.FACT) if f.payload.basis not in _SUMMARY_ONLY_BASES]


def pending(view: Any) -> bool:
    """CS4: whether there is a group to summarise or a capability to mark in
    use.

    Two things this method writes and nothing else: one INFERRED summary per
    measure whose group of primary figures it has not already summarised, and a
    supersession marking a CAPABILITY PRESENT where a live PROCESS_STEP uses
    it. Where the register holds neither, the run adds nothing, supersedes
    nothing and asks nothing - a selection slot spent to leave the registry
    exactly as it was.

    The same three reads `run` makes, in the same order: which facts group by
    measure, which groups are already summarised (by measure and by the exact
    set of ids the summary cites), and which capabilities a step names.
    """
    groups: dict[str, frozenset] = {}
    for f in _live(view, T.Kind.FACT):
        if f.payload.measure_id is not None and f.payload.basis is not T.FactBasis.INFERRED:
            groups.setdefault(f.payload.measure_id, set()).add(f.id)
    already = {(f.payload.measure_id, frozenset(f.provenance.derived_from))
               for f in _live(view, T.Kind.FACT) if f.payload.basis is T.FactBasis.INFERRED}
    if any((measure_id, frozenset(ids)) not in already for measure_id, ids in groups.items()):
        return True
    capabilities = {c.id: c for c in _live(view, T.Kind.CAPABILITY)
                    if c.payload.gap is not T.GapState.PRESENT}
    return any(cid in capabilities for s in _live(view, T.Kind.PROCESS_STEP)
               for cid in s.payload.system_ids)


SPEC = MethodSpec(
    id="current_state",
    version=1,
    applicability=(QuestionShape(T.Interrogative.WHAT, T.Kind.FACT),
                   QuestionShape(T.Interrogative.WHAT, T.Kind.CAPABILITY)),
    answers=(T.Interrogative.WHAT,),
    required_inputs=(
        InputSpec("facts", T.Kind.FACT, min_count=1, effort=T.EffortClass.OFFHAND,
                  why_needed="the current state is what the registered facts already say"),
    ),
    optional_inputs=(
        InputSpec("measures", T.Kind.MEASURE, min_count=1),
        InputSpec("steps", T.Kind.PROCESS_STEP, min_count=1),
        InputSpec("capabilities", T.Kind.CAPABILITY, min_count=1),
    ),
    execution=T.ExecutionType.DETERMINISTIC,
    output_kinds=(T.Kind.FACT, T.Kind.CAPABILITY),
    output_schema=None,
    evidence=EvidenceRequirement(),
    limitations=("summarises what is registered; it explains nothing and proposes no change",),
    validators=(_v_no_blended_summary, _v_summary_basis_is_inferred),
    cost_class=1,
    max_model_calls=0,
    pending=pending,
)


@register
class CurrentStateMethod:
    spec = SPEC

    def _summaries(self, ctx: MethodContext) -> list[T.Add]:
        view = ctx.registry
        measures = {m.id: m for m in _live(view, T.Kind.MEASURE)}
        groups: dict[str, list[T.Entity]] = {}
        for f in _live(view, T.Kind.FACT):
            # A fact with no MEASURE is in no group: the measure id is the only
            # join the engine allows between two figures (MF1.6), and joining
            # on a topic string would merge two different things that share a
            # word.
            if f.payload.measure_id is not None and f.payload.basis is not T.FactBasis.INFERRED:
                groups.setdefault(f.payload.measure_id, []).append(f)
        already = {(f.payload.measure_id, frozenset(f.provenance.derived_from))
                   for f in _live(view, T.Kind.FACT) if f.payload.basis is T.FactBasis.INFERRED}
        decision = view.central_decision()
        out: list[T.Add] = []
        for measure_id in sorted(groups):
            facts = sorted(groups[measure_id], key=lambda e: e.id)
            cited = tuple(f.id for f in facts)
            if (measure_id, frozenset(cited)) in already:
                continue
            payload = T.FactPayload(
                statement=_summary_text(measures.get(measure_id), measure_id, facts),
                basis=T.FactBasis.INFERRED, measure_id=measure_id,
                quantity=_one_quantity(facts), topic=measure_id)
            out.append(T.Add(new_entity(
                ctx, T.Kind.FACT, payload, derived_from=cited,
                relation=T.RelationToCentralDecision.INFORMS,
                # An inference over the registry is not a measurement: the
                # confidence of the summary is unknown, never 1.0 because the
                # arithmetic of grouping happened to be exact.
                confidence=T.Confidence(None),
                decision_id=decision.id if decision is not None else None,
                weight=decision.relevance.weight if decision is not None else 0.0,
                status=T.Status.PROPOSED)))
        return out

    def _capabilities_in_use(self, ctx: MethodContext) -> list[T.Supersede]:
        view = ctx.registry
        capabilities = {c.id: c for c in _live(view, T.Kind.CAPABILITY)}
        used: dict[str, list[str]] = {}
        for s in _live(view, T.Kind.PROCESS_STEP):
            for cid in s.payload.system_ids:
                if cid in capabilities:
                    used.setdefault(cid, []).append(s.id)
        out: list[T.Supersede] = []
        for cid in sorted(used):
            old = capabilities[cid]
            if old.payload.gap is T.GapState.PRESENT:
                continue
            steps = tuple(sorted(used[cid]))
            # What the steps rest on is what this claim rests on. A step is a
            # consultant judgement whatever its status, so measuring the
            # evidence against the steps themselves could never confirm
            # anything; the facts underneath them are the record.
            basis = tuple(sorted({fid for sid in steps
                                  for fid in (view.get(sid).provenance.derived_from if view.get(sid) else ())}))
            payload = T.CapabilityPayload(text=old.payload.text,
                                          capability_class=old.payload.capability_class,
                                          gap=T.GapState.PRESENT, evidence=steps)
            info = T.info_type_of(T.Kind.CAPABILITY, payload)
            entity = make_entity(
                kind=T.Kind.CAPABILITY, engagement_id=view.engagement_id, payload=payload,
                provenance=T.Provenance(actor=ctx.actor, actor_ref=ctx.actor_ref,
                                        derived_from=steps + tuple(b for b in basis if b not in steps)),
                confidence=old.confidence, relevance=old.relevance, relation=old.relation,
                # The evidence requirement, not the method, decides how far
                # this row may go: PRESENT is CONFIRMED only when every fact
                # the steps rest on is itself settled by an authority the
                # requirement accepts.
                status=evidenced_status(view, self.spec.evidence, basis, ctx.actor, owner_of(info)),
                entity_id=old.id)
            out.append(T.Supersede(old.id, entity))
        return out

    def run(self, ctx: MethodContext) -> MethodResult:
        deltas: list = list(self._summaries(ctx))
        deltas.extend(self._capabilities_in_use(ctx))
        return MethodResult(deltas=tuple(deltas))


__all__ = ["SPEC", "CurrentStateMethod"]
