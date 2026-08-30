"""scenario - CALCULATION: what the registered figures become under the
assumptions the client has agreed to.

A scenario is a base figure multiplied by a fraction. The whole integrity of
the method is in where that fraction may come from.

Laws this module enforces, and the failure each prevents:

  SC1 a fraction multiplies a client figure only when a registered ASSUMPTION
      carries it. Not a rate FACT the engine inferred, not a literal in this
      module, not a number a model wrote: an ASSUMPTION is the one kind of
      row the client can approve or reject, and an unapproved one is visibly
      labelled everywhere it is used (spec section 7). A coined fraction is
      how a plausible-looking projection gets a number nobody ever agreed to;
      here it cannot be constructed, and the validator refuses it in a result
      even if some future edit tries.
  SC2 the arithmetic is the Calculator's. The product carries its formula
      over entity ids and its input ids, so L7 recomputes it exactly; the
      Calculator's own refusals (an un-given share, an unpinned dimension)
      become findings and questions, never a worked-around estimate. Note
      that arith.share_is_given already refuses an unapproved assumption as a
      multiplier: an unapproved scenario is asked for, not computed.
  SC3 the number of scenarios is bounded by the declared MAX_FANOUT, read
      from settings, never by a fixed count of scenarios per engagement: how
      many bases and how many assumptions exist is a property of the
      engagement, not of the engine.

Each scenario writes two rows: the calculated FACT (the arithmetic, with
lineage) and the EXPECTED_OUTCOME that states it as an outcome. The outcome
copies the calculated quantity; it never carries a number of its own.
"""
from __future__ import annotations

from typing import Any

from app.engine import types as T
from app.engine.calc import IncomparableInputs
from app.engine.calc.arith import quantity_of
from app.engine.calc.units import format_quantity
from app.engine.methods.builtin.cost_benefit import (
    calculated_fact,
    calculated_traceable,
    decision_id,
    known_formulas,
    live,
    pin_question,
)
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

# The bound on how many scenarios one run writes. The name and the default are
# the declared ones (types.BOUNDS / Settings ENGINE_MAX_FANOUT); the value is
# read from the context at run time so a deployment can widen it without an
# edit here (SC3).
FANOUT_BOUND = "MAX_FANOUT"


def fanout(ctx: MethodContext) -> int:
    value = ctx.settings.get(FANOUT_BOUND, T.BOUNDS[FANOUT_BOUND])
    return max(1, int(value))


def fraction_carriers(view: Any) -> list[T.Entity]:
    """SC1: the rows a scenario may take a fraction from - registered
    ASSUMPTIONs carrying a rate quantity, and nothing else. A rate FACT is
    deliberately not here: a fraction the engine inferred or extracted has
    nobody to approve it, and a scenario built on it would look agreed when
    it is not."""
    out = []
    for a in live(view, T.Kind.ASSUMPTION):
        q = quantity_of(a)
        if q is not None and q.unit_family is T.UnitFamily.RATE:
            out.append(a)
    return out


def rests_on_an_assumption(view: Any, fact: T.Entity) -> bool:
    """Whether a calculated fact already has an assumption among its inputs."""
    for input_id in fact.payload.inputs:
        source = view.get(input_id)
        if source is not None and source.kind is T.Kind.ASSUMPTION:
            return True
    return False


def base_carriers(view: Any) -> list[T.Entity]:
    """The figures a fraction may be applied to: registered facts with a
    quantity that is not itself a fraction, and that do not already rest on
    an assumption. A fraction of a fraction is not a scenario, it is a second
    assumption nobody stated; and re-scaling a figure an assumption already
    scaled compounds that assumption invisibly, which is also how a run would
    grow a new scenario on its own output every round."""
    out = []
    for f in live(view, T.Kind.FACT):
        q = quantity_of(f)
        if q is None or q.unit_family is T.UnitFamily.RATE:
            continue
        if f.payload.basis is T.FactBasis.CALCULATED and rests_on_an_assumption(view, f):
            continue
        out.append(f)
    return out


def approval_question(ctx: MethodContext, assumption: T.Entity, why: str) -> T.QuestionPayload:
    """The Calculator refused a share nobody with the authority to state it
    has stated. That is a question for the client, who owns assumptions
    (APPROVAL_OWNER), not a licence for the engine to proceed anyway."""
    return T.QuestionPayload(
        text=f"Do you accept {assumption.id} as an assumption for planning? The scenario is not computed until you do",
        asks_for=(T.AsksFor(T.Kind.ASSUMPTION),),
        issue_ids=ctx.issue_ids, why=why,
        effort=T.EffortClass.OFFHAND, strategy=T.FillStrategy.ASK_CLIENT)


def fraction_from_assumption(view: Any, result: MethodResult) -> list[T.Finding]:
    """SC1 checked on the finished result: every rate-carrying input of a
    calculated fact this method wrote is an ASSUMPTION row. Stated as a
    validator as well as a guard because the guard chooses what to compute
    and the validator refuses what was computed - a later edit to either one
    alone is caught."""
    out: list[T.Finding] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is None or e.kind is not T.Kind.FACT or e.payload.basis is not T.FactBasis.CALCULATED:
            continue
        for input_id in e.payload.inputs:
            source = view.get(input_id)
            if source is None:
                continue
            q = quantity_of(source)
            if q is None or q.unit_family is not T.UnitFamily.RATE:
                continue
            if source.kind is not T.Kind.ASSUMPTION:
                out.append(T.Finding(
                    law="M.scenario.coined_fraction", where=e.id or e.kind.value,
                    issue=f"the fraction in {input_id} is a {source.kind.value}, not an assumption anyone can approve",
                    fix="register the fraction as an ASSUMPTION the client can approve, or do not run the scenario",
                    entity_ids=(input_id,)))
    return out


def outcome_quantity_is_calculated(view: Any, result: MethodResult) -> list[T.Finding]:
    """An EXPECTED_OUTCOME states a scenario result; the figure on it is the
    one the Calculator produced in the same batch, matched by value. An
    outcome carrying a number no calculation in the result produced would be
    a projection with no arithmetic behind it."""
    computed = [getattr(d, "entity", None) for d in result.deltas]
    quantities = [q for e in computed if e is not None and e.kind is T.Kind.FACT
                  and e.payload.basis is T.FactBasis.CALCULATED
                  and (q := quantity_of(e)) is not None]
    out: list[T.Finding] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is None or e.kind is not T.Kind.EXPECTED_OUTCOME:
            continue
        q = quantity_of(e)
        if q is not None and q not in quantities:
            out.append(T.Finding(
                law="M.scenario.uncalculated_outcome", where=e.id or e.kind.value,
                issue="an expected outcome carries a figure no calculation in this result produced",
                fix="state the outcome from the CalcResult, or state it without a figure",
                entity_ids=(e.id,) if e.id else ()))
    return out


SPEC = MethodSpec(
    id="scenario",
    version=1,
    applicability=(
        QuestionShape(T.Interrogative.WHETHER, T.Kind.EXPECTED_OUTCOME, quantified=True),
        QuestionShape(T.Interrogative.HOW_MUCH, T.Kind.EXPECTED_OUTCOME, quantified=True),
    ),
    answers=(T.Interrogative.WHETHER, T.Interrogative.HOW_MUCH),
    required_inputs=(
        InputSpec("base_figures", T.Kind.FACT, filter={"has_quantity": True}, min_count=1,
                  effort=T.EffortClass.LOOKUP,
                  why_needed="a scenario moves a registered figure; without one there is nothing to move"),
        InputSpec("assumptions", T.Kind.ASSUMPTION, min_count=1, effort=T.EffortClass.OFFHAND,
                  why_needed="the fraction a scenario applies must be an assumption the client can approve"),
    ),
    optional_inputs=(InputSpec("measures", T.Kind.MEASURE, min_count=1),),
    execution=T.ExecutionType.CALCULATION,
    output_kinds=(T.Kind.FACT, T.Kind.EXPECTED_OUTCOME, T.Kind.QUESTION),
    output_schema=None,
    evidence=EvidenceRequirement(),
    limitations=(
        "applies fractions the client can approve to registered figures; it does not model interactions between scenarios",
        "a fraction that is not a registered assumption is refused, not estimated",
    ),
    validators=(calculated_traceable, fraction_from_assumption, outcome_quantity_is_calculated),
    cost_class=1,
    max_model_calls=0,
)


@register
class ScenarioMethod:
    spec = SPEC

    def run(self, ctx: MethodContext) -> MethodResult:
        view = ctx.registry
        deltas: list = []
        questions: list[T.QuestionPayload] = []
        findings: list[T.Finding] = []
        seen = known_formulas(view)
        asked: set[str] = set()
        bound = fanout(ctx)
        written = 0
        for base in base_carriers(view):
            for assumption in fraction_carriers(view):
                if written >= bound:
                    # SC3: the bound stops the run, it does not choose a
                    # different answer; what was not computed simply is not
                    # claimed.
                    return self._result(deltas, questions, findings)
                try:
                    quantity = quantity_of(base)
                    cr = ctx.calc.product([base, assumption], unit=quantity.unit, unit_family=quantity.unit_family)
                except IncomparableInputs as exc:
                    questions.append(pin_question(
                        ctx, (base.id, assumption.id), tuple(getattr(exc, "unpinned", ()) or ()),
                        why="a scenario is only lawful over figures whose dimensions join"))
                    continue
                except ValueError as exc:
                    # SC2: the assumption is not one the client has approved,
                    # or a leg carries no quantity. Recorded, then asked.
                    findings.append(T.Finding(
                        law="M.scenario.refused_product", where=f"{base.id}*{assumption.id}",
                        issue=str(exc)[:200],
                        fix="the client approves the assumption, or the scenario is not computed",
                        severity=T.Severity.LOW, blocks_final=False,
                        entity_ids=(base.id, assumption.id)))
                    if assumption.id not in asked:
                        asked.add(assumption.id)
                        questions.append(approval_question(
                            ctx, assumption, why="an unapproved assumption may not multiply a client figure"))
                    continue
                if cr.formula in seen:
                    continue
                seen.add(cr.formula)
                written += 1
                statement = (f"Scenario on {base.id} under {assumption.id}: "
                             f"{cr.formula} = {format_quantity(cr.quantity)}")
                deltas.append(calculated_fact(ctx, self.spec.id, cr,
                                              measure_id=base.payload.measure_id, statement=statement))
                payload = T.ExpectedOutcomePayload(
                    text=statement, measure_id=base.payload.measure_id, quantity=cr.quantity,
                    basis="calculated", supports=cr.inputs)
                deltas.append(T.Add(new_entity(
                    ctx, T.Kind.EXPECTED_OUTCOME, payload, derived_from=cr.inputs,
                    relation=T.RelationToCentralDecision.INFORMS, confidence=T.Confidence(1.0, "computed"),
                    decision_id=decision_id(view), weight=0.4)))
        return self._result(deltas, questions, findings)

    @staticmethod
    def _result(deltas, questions, findings) -> MethodResult:
        return MethodResult(deltas=tuple(deltas), questions=tuple(questions), findings=tuple(findings))
