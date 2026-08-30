"""kpi_design - what "better" will be measured as (design 7.3 row kpi_design):
HOW_MUCH or WHAT on SUCCESS_CRITERION.

DETERMINISTIC, so M1 holds and no model is called: a success criterion is the
client's objective joined to a registered measure, and its baseline is a
number the engagement already has or has not.

Laws this module enforces, each in the docstring of the thing enforcing it:

  KP1 a baseline is never invented. It is copied by id from a registered
      FACT on the same measure - a figure the client stated, or one a record
      carries - or it is absent and the criterion says so by reading
      "measure_first": measure it before the work starts. Those three are the
      whole vocabulary (BASELINE_SOURCES, the r30 rule at pilot_gate.py:366
      generalised), and a fourth would be a number nobody can point at
      (baseline_for, _v_baseline_is_registered_or_measure_first).
  KP2 a target is the client's. It is copied from the OBJECTIVE that carries
      it, never derived from the baseline by a rule of thumb: "10% better" is
      an ambition somebody has to own (run()).
  KP3 the measure is the registered MEASURE entity, joined by id. Two
      criteria on one measure reconcile; two criteria on two wordings of one
      measure do not, which is the whole reason MEASURE exists (MF1.6).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from app.engine import types as T
from app.engine.authority import precedence_rank
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
from app.engine.methods.builtin.org_design import (
    display_text,
    live,
    require_citations,
)


# The closed vocabulary of where a baseline may come from. "unknown" is not in
# it: a criterion this method writes always says which of the three it is.
CLIENT_FACT = "client_fact"
RECORD = "record"
MEASURE_FIRST = "measure_first"
BASELINE_SOURCES: frozenset[str] = frozenset({CLIENT_FACT, RECORD, MEASURE_FIRST})

# Which basis makes a fact a client figure rather than a record. Everything
# else that carries a precedence rank is a record.
_CLIENT_BASES: frozenset[T.FactBasis] = frozenset({T.FactBasis.CLIENT_STATED})


def baseline_for(measure_id: str, facts: Sequence[T.Entity], view) -> tuple[T.Entity | None, str]:
    """KP1: the fact that may serve as a baseline for one measure, and which of
    the three sources it is.

    Candidates are live FACTs joined to the measure by `measure_id` (never by
    wording, MF1.6) that carry a quantity and sit somewhere in
    CURRENT_STATE_PRECEDENCE. The strongest rank wins, ties broken by id so
    the choice reproduces. With no candidate the answer is MEASURE_FIRST -
    measure it before the work starts - which is a real answer, not a
    placeholder for a number.
    """
    ranked: list[tuple[int, str, T.Entity]] = []
    for f in facts:
        p = f.payload
        if p.measure_id != measure_id or p.quantity is None:
            continue
        rank = precedence_rank(f, view)
        if rank is None:
            continue
        ranked.append((rank, f.id, f))
    if not ranked:
        return None, MEASURE_FIRST
    ranked.sort(key=lambda t: (t[0], t[1]))
    winner = ranked[0][2]
    return winner, CLIENT_FACT if winner.payload.basis in _CLIENT_BASES else RECORD


class KpiDesign:
    spec = MethodSpec(
        id="kpi_design", version=1,
        applicability=(
            QuestionShape(T.Interrogative.HOW_MUCH, T.Kind.SUCCESS_CRITERION),
            QuestionShape(T.Interrogative.WHAT, T.Kind.SUCCESS_CRITERION),
        ),
        answers=(T.Interrogative.HOW_MUCH, T.Interrogative.WHAT),
        required_inputs=(
            InputSpec("objectives", T.Kind.OBJECTIVE,
                      why_needed="a success criterion measures an objective; without one it measures nothing"),
            InputSpec("measures", T.Kind.MEASURE,
                      why_needed="the registered measure two figures must share to be comparable"),
        ),
        optional_inputs=(
            InputSpec("baseline_facts", T.Kind.FACT, min_count=0, filter={"has_quantity": True, "has_measure": True},
                      why_needed="the figure the measure stands at today"),
            InputSpec("criteria", T.Kind.SUCCESS_CRITERION, min_count=0,
                      why_needed="criteria already registered"),
        ),
        execution=T.ExecutionType.DETERMINISTIC,
        output_kinds=(T.Kind.SUCCESS_CRITERION,),
        output_schema=None,
        evidence=EvidenceRequirement(),
        limitations=("states the measure, the client's target and a registered baseline; where no "
                     "baseline is registered it says so rather than estimating one",),
        validators=(),
        cost_class=1, max_model_calls=0)

    def run(self, ctx: MethodContext) -> MethodResult:
        view = ctx.registry
        dec = view.central_decision()
        decision_id = dec.id if dec is not None else None
        objectives = live(view, T.Kind.OBJECTIVE)
        measures = {m.id: m for m in live(view, T.Kind.MEASURE)}
        facts = live(view, T.Kind.FACT)
        covered = {c.payload.measure_id for c in live(view, T.Kind.SUCCESS_CRITERION)}

        deltas: list[T.EntityDelta] = []
        questions: list[T.QuestionPayload] = []
        weight = T.SENSITIVITY[T.RelationToCentralDecision.DEFINES]

        for obj in sorted(objectives, key=lambda e: e.id):
            measure_id = obj.payload.measure_id
            if measure_id is None or measure_id not in measures:
                # KP3: an objective with no registered measure cannot become a
                # criterion; naming a measure for it here would invent the very
                # key reconciliation depends on.
                questions.append(T.QuestionPayload(
                    text=f"What exactly would be measured to know whether \"{display_text(obj)}\" was met?",
                    asks_for=(T.AsksFor(T.Kind.MEASURE),), issue_ids=ctx.issue_ids,
                    why="a success criterion joins an objective to one registered measure",
                    effort=T.EffortClass.OFFHAND, strategy=T.FillStrategy.ASK_CLIENT))
                continue
            if measure_id in covered:
                continue
            measure = measures[measure_id]
            fact, source = baseline_for(measure_id, facts, view)
            cites = [obj.id, measure_id] + ([fact.id] if fact is not None else [])
            payload = T.SuccessCriterionPayload(
                text=f"{display_text(measure)}, against the objective {display_text(obj)}",
                measure_id=measure_id,
                # KP2: the target is the client's own, copied off the objective
                # by id. Nothing here derives one from the baseline.
                target=obj.payload.target,
                # KP1: copied from the winning fact, or absent and said so.
                baseline=fact.payload.quantity if fact is not None else None,
                baseline_source=source)
            deltas.append(T.Add(new_entity(
                ctx, T.Kind.SUCCESS_CRITERION, payload, derived_from=tuple(cites),
                relation=T.RelationToCentralDecision.DEFINES, confidence=T.Confidence(None),
                decision_id=decision_id, weight=weight)))
            if source == MEASURE_FIRST:
                questions.append(T.QuestionPayload(
                    text=f"Nothing registered says where {display_text(measure)} stands today; "
                         "it is measured before the work starts unless you have the figure.",
                    asks_for=(T.AsksFor(T.Kind.FACT, {"has_quantity": True, "has_measure": True}),),
                    issue_ids=ctx.issue_ids,
                    why="a baseline is a figure the engagement holds, or it is measured; it is never estimated",
                    effort=T.EffortClass.LOOKUP, strategy=T.FillStrategy.ASK_CLIENT))
        return MethodResult(deltas=tuple(deltas), questions=tuple(questions))


def _v_baseline_is_registered_or_measure_first(view, result: MethodResult) -> list[T.Finding]:
    """KP1 re-checked on the finished result: every criterion states one of the
    three sources, and where it states a baseline figure that figure is exactly
    the quantity of a registered FACT the criterion cites, on the same measure.
    Removing this check is the named mutation "allow an invented baseline"."""
    out: list[T.Finding] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is None or e.kind is not T.Kind.SUCCESS_CRITERION:
            continue
        p = e.payload
        where = e.id or "success_criterion"
        if p.baseline_source not in BASELINE_SOURCES:
            out.append(T.Finding(
                law="M.kpi_design.invented_baseline", where=where,
                issue=f"the baseline source {p.baseline_source!r} is outside "
                      "{client_fact, record, measure_first}",
                fix="name where the baseline comes from, or measure it first"))
            continue
        if p.baseline is None:
            if p.baseline_source != MEASURE_FIRST:
                out.append(T.Finding(
                    law="M.kpi_design.invented_baseline", where=where,
                    issue=f"the criterion claims a {p.baseline_source} baseline but carries no figure",
                    fix="cite the fact the figure comes from, or say measure_first"))
            continue
        if p.baseline_source == MEASURE_FIRST:
            out.append(T.Finding(
                law="M.kpi_design.invented_baseline", where=where,
                issue="a criterion to be measured first cannot already carry a baseline figure",
                fix="drop the figure, or cite the registered fact that carries it"))
            continue
        supporting = [view.get(i) for i in e.provenance.derived_from]
        if not any(f is not None and f.kind is T.Kind.FACT
                   and f.payload.measure_id == p.measure_id
                   and f.payload.quantity == p.baseline for f in supporting):
            out.append(T.Finding(
                law="M.kpi_design.invented_baseline", where=where,
                issue="the baseline figure matches no registered fact the criterion cites",
                fix="copy the baseline from a registered fact on this measure, or say measure_first"))
    return out


def _v_measure_is_registered(view, result: MethodResult) -> list[T.Finding]:
    """KP3 re-checked: every criterion names a registered MEASURE. Reconciliation
    joins on measure_id and on nothing else, so a criterion with no measure is a
    figure that can never be compared with another."""
    out: list[T.Finding] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is None or e.kind is not T.Kind.SUCCESS_CRITERION:
            continue
        m = view.get(e.payload.measure_id) if e.payload.measure_id else None
        if m is None or m.kind is not T.Kind.MEASURE:
            out.append(T.Finding(
                law="M.kpi_design.unregistered_measure", where=e.id or "success_criterion",
                issue="the criterion names no registered measure",
                fix="register the MEASURE first; reconciliation joins on its id, never on wording"))
    return out


KpiDesign.spec = replace(KpiDesign.spec,
                         validators=(require_citations("kpi_design"),
                                     _v_baseline_is_registered_or_measure_first,
                                     _v_measure_is_registered))
register(KpiDesign)
