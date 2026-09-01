"""financial_model - CALCULATION: what the registered figures add up to per
measure, and whether the client's quantified objectives survive that
arithmetic.

Two things happen here, in this order, and neither guesses.

1. Per MEASURE, the primary registered figures are totalled by ctx.calc. The
   total is a calculated FACT carrying its formula over entity ids and those
   ids, so L7 recomputes it exactly. Derived figures are excluded from the
   base: totalling a total double-counts, and the second total would be a
   number with a true-looking lineage.
2. Each quantified OBJECTIVE is held against the total on its own measure.
   Comparability is asked of the Calculator, never assumed: an unpinned
   dimension opens a pin-the-dimension QUESTION and no verdict is recorded;
   two figures that are not one kind of thing are recorded as a refusal, also
   with no verdict. Only a COMPARABLE pair produces a feasibility.

Laws this module enforces, and the failure each prevents:

  FM1 no verdict on incomparable inputs. A currency or a period basis that
      nobody pinned is a typed hole (design 1): the objective stays UNTESTED
      and the client is asked to pin exactly the named dimension. An engine
      that defaulted the missing dimension would declare an objective
      infeasible on an arithmetic the client never agreed to.
  FM2 every figure is a CalcResult with formula and inputs. Nothing in this
      module writes a number it did not get from ctx.calc.
  FM3 an objective the facts show infeasible is amended visibly (Supersede,
      so the original stays in lineage), a CONFLICT of kind
      OBJECTIVE_VS_FEASIBILITY is opened with the client as the authority,
      and a DECISION_REQUIRED citing the objective is written - which is what
      makes registry.infeasible_objectives_without_decision() empty (L12).
      An infeasible objective quietly left standing is exactly the failure
      that produces a plan nobody can execute.
  FM4 the engine may state what the arithmetic shows; it may not keep the
      client's confirmation on a statement the client has not seen. So an
      amended objective is written at the status the amending actor is
      entitled to (may_advance): a CONFIRMED objective returns to PROPOSED
      and the DECISION_REQUIRED asks the client.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.engine import types as T
from app.engine.authority import may_advance
from app.engine.calc import IncomparableInputs
from app.engine.calc.arith import quantity_of
from app.engine.calc.units import COMPARABLE, UNKNOWN_DIMENSION, format_quantity, required_dimensions
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

# A total of one figure is that figure again; it is used for the feasibility
# comparison but never registered as its own row.
MIN_TOTAL_LEGS = 2

# The label the amended objective carries, so a reader can see that the
# feasibility on it came from arithmetic and not from the client.
FEASIBILITY_TESTED = "feasibility_tested"


def unpinned_between(a: T.Quantity, b: T.Quantity) -> tuple[str, ...]:
    """Which dimensions a comparison of a and b is missing: one the family
    needs and that is None on either side, or one pinned on one side only.
    Every test is `is None`, so a dimension a newer normaliser pins to an
    empty-but-present value is not condemned as missing."""
    needed = set(required_dimensions(a.unit_family)) | set(required_dimensions(b.unit_family))
    out = []
    for name in T.Dimensions.DIMENSION_NAMES:
        va, vb = getattr(a.dimensions, name), getattr(b.dimensions, name)
        if (name in needed and (va is None or vb is None)) or ((va is None) != (vb is None)):
            out.append(name)
    return tuple(out)


def primary_facts_by_measure(view: Any) -> dict[str, list[T.Entity]]:
    """The registered figures each measure holds, excluding derived ones. A
    calculated fact is a restatement of figures already in the group; adding
    it back in would count them twice and the recompute would still pass."""
    out: dict[str, list[T.Entity]] = {}
    for f in live(view, T.Kind.FACT):
        if f.payload.measure_id is None or f.payload.basis is T.FactBasis.CALCULATED:
            continue
        if quantity_of(f) is None:
            continue
        out.setdefault(f.payload.measure_id, []).append(f)
    return out


def quantified_objectives(view: Any) -> list[T.Entity]:
    """Objectives that state a target on a registered measure - the only ones
    arithmetic can say anything about. An objective with no target is not
    untested, it is unquantified, and nothing here touches it."""
    return [o for o in live(view, T.Kind.OBJECTIVE)
            if quantity_of(o) is not None and o.payload.measure_id is not None]


def amended_status(objective: T.Entity, actor: T.Actor) -> T.Status:
    """FM4. The status an amended objective may be written at by `actor`: its
    own, when that actor is entitled to it, and PROPOSED otherwise. The
    engine never re-asserts the client's confirmation on wording the client
    has not seen."""
    return objective.status if may_advance(objective, objective.status, actor) else T.Status.PROPOSED


def amended_objective(objective: T.Entity, feasibility: T.Feasibility, inputs: tuple[str, ...],
                      method_id: str) -> T.Supersede:
    """The objective again, with the feasibility the arithmetic showed, as a
    new version citing the calculation that changed it. Superseding rather
    than editing keeps the original queryable: lineage is the row history."""
    provenance = replace(
        objective.provenance, actor=T.Actor.CALCULATOR, actor_ref=f"calc:{method_id}",
        derived_from=tuple(dict.fromkeys(objective.provenance.derived_from + inputs)))
    amended = replace(
        objective,
        payload=replace(objective.payload, feasibility=feasibility),
        status=amended_status(objective, T.Actor.CALCULATOR),
        labels=tuple(dict.fromkeys(objective.labels + (FEASIBILITY_TESTED,))),
        provenance=provenance)
    return T.Supersede(objective.id, amended)


def pending(view: Any) -> bool:
    """FM5: whether there is anything here to model.

    Two things this method can do and nothing else: total the registered
    figures on a measure that carries at least MIN_TOTAL_LEGS of them, and test
    a quantified objective against the total on its own measure. Where the
    register holds neither, the run adds nothing, supersedes nothing and asks
    nothing - a selection slot spent to leave the registry as it was.

    Read from counts and typed fields only: which measures carry primary
    figures, how many, and which objectives name one of those measures. It does
    not try to predict what the calculator will say, because a refusal by the
    calculator is a real outcome the run should record.
    """
    groups = primary_facts_by_measure(view)
    if not groups:
        # Nothing measured yet. The method is WAITING, not finished, and the
        # difference matters: a method excluded here is one `outstanding_inputs`
        # stops listing, and an engagement that stopped listing what it is
        # waiting for would reach SYNTHESIS owing the work.
        return True
    if any(len(facts) >= MIN_TOTAL_LEGS for facts in groups.values()):
        return True
    return any(o.payload.measure_id in groups for o in quantified_objectives(view))


SPEC = MethodSpec(
    id="financial_model",
    version=1,
    applicability=(
        QuestionShape(T.Interrogative.HOW_MUCH, T.Kind.COST, quantified=True),
        QuestionShape(T.Interrogative.HOW_MUCH, T.Kind.BENEFIT, quantified=True),
        QuestionShape(T.Interrogative.HOW_MUCH, T.Kind.EXPECTED_OUTCOME, quantified=True),
        QuestionShape(T.Interrogative.WHETHER, T.Kind.OBJECTIVE, quantified=True),
    ),
    answers=(T.Interrogative.HOW_MUCH, T.Interrogative.WHETHER),
    required_inputs=(
        InputSpec("measured_figures", T.Kind.FACT, filter={"has_quantity": True, "has_measure": True},
                  min_count=1, effort=T.EffortClass.DOCUMENT,
                  why_needed="a model runs on registered figures attached to a measure; without one there is nothing to model"),
    ),
    optional_inputs=(
        InputSpec("objectives", T.Kind.OBJECTIVE, min_count=1),
        InputSpec("measures", T.Kind.MEASURE, min_count=1),
    ),
    execution=T.ExecutionType.CALCULATION,
    output_kinds=(T.Kind.FACT, T.Kind.OBJECTIVE, T.Kind.CONFLICT, T.Kind.DECISION_REQUIRED, T.Kind.QUESTION),
    output_schema=None,
    evidence=EvidenceRequirement(),
    limitations=(
        "reads an objective's target as an amount the registered figures must cover; it does not infer a direction the objective does not state",
        "no verdict where the figures are not comparable: the dimension is asked for, never defaulted",
    ),
    validators=(calculated_traceable,),
    # One step above cost_benefit so that a quantified COST node ranks the
    # cheaper total first and the two methods do not tie on every such node
    # (design 7.2: a tie is a real disagreement to surface, not a default).
    cost_class=2,
    max_model_calls=0,
    pending=pending,
)


@register
class FinancialModelMethod:
    spec = SPEC

    def run(self, ctx: MethodContext) -> MethodResult:
        view = ctx.registry
        deltas: list = []
        questions: list[T.QuestionPayload] = []
        findings: list[T.Finding] = []
        seen = known_formulas(view)
        totals: dict[str, Any] = {}
        for measure_id, facts in primary_facts_by_measure(view).items():
            try:
                cr = ctx.calc.total(facts)
            except IncomparableInputs as exc:
                # FM1: the figures on one measure do not join. Asked, not averaged.
                questions.append(pin_question(
                    ctx, tuple(f.id for f in facts), tuple(getattr(exc, "unpinned", ()) or ()),
                    why="figures on one measure are only totalled when every pinned dimension agrees"))
                continue
            except ValueError as exc:
                findings.append(self._refusal(f"total:{measure_id}", str(exc), tuple(f.id for f in facts)))
                continue
            totals[measure_id] = cr
            if len(facts) >= MIN_TOTAL_LEGS and cr.formula not in seen:
                seen.add(cr.formula)
                deltas.append(calculated_fact(
                    ctx, self.spec.id, cr, measure_id=measure_id,
                    statement=f"Registered figures on {measure_id}: {cr.formula} = {format_quantity(cr.quantity)}"))
        for objective in quantified_objectives(view):
            cr = totals.get(objective.payload.measure_id)
            if cr is None:
                # Nothing registered on that measure: absence of evidence is
                # not evidence of infeasibility. The objective stays UNTESTED.
                continue
            target = quantity_of(objective)
            verdict = ctx.calc.comparable(target, cr.quantity)
            if verdict == UNKNOWN_DIMENSION:
                questions.append(pin_question(
                    ctx, (objective.id,) + cr.inputs, unpinned_between(target, cr.quantity),
                    why="an objective is only tested against figures that share every dimension the comparison needs"))
                continue
            if verdict != COMPARABLE:
                findings.append(self._refusal(
                    objective.id, f"{objective.id} and the figures on {objective.payload.measure_id} are not one kind of thing",
                    (objective.id,) + cr.inputs))
                continue
            feasibility = (T.Feasibility.INFEASIBLE_ON_FACTS if target.value > cr.quantity.value
                           else T.Feasibility.FEASIBLE)
            if objective.payload.feasibility is not feasibility:
                deltas.append(amended_objective(objective, feasibility, cr.inputs, self.spec.id))
            if feasibility is not T.Feasibility.INFEASIBLE_ON_FACTS:
                continue
            deltas.append(self._conflict(ctx, objective, target, cr))
            deltas.append(self._decision_required(ctx, objective, target, cr))
        return MethodResult(deltas=tuple(deltas), questions=tuple(questions), findings=tuple(findings))

    @staticmethod
    def _refusal(where: str, why: str, entity_ids: tuple[str, ...]) -> T.Finding:
        """A refusal recorded. LOW and non-blocking: the refusal is the law
        working, and the question beside it is what moves the engagement on."""
        return T.Finding(law="M.financial_model.refused_comparison", where=where, issue=why[:200],
                         fix="pin the dimension or register a conversion fact; the model states no verdict without one",
                         severity=T.Severity.LOW, blocks_final=False, entity_ids=entity_ids)

    @staticmethod
    def _conflict(ctx: MethodContext, objective: T.Entity, target: T.Quantity, cr) -> T.Add:
        """FM3: the target and the arithmetic, side by side, for the client."""
        payload = T.ConflictPayload(
            kind=T.ConflictKind.OBJECTIVE_VS_FEASIBILITY, subject_id=objective.id,
            conclusions=(
                T.ConflictConclusion(entity_id=objective.id,
                                     statement=f"the objective targets {format_quantity(target)}",
                                     evidence=(objective.id,),
                                     consequence="the plan would be built on a target the registered figures do not reach"),
                T.ConflictConclusion(entity_id=cr.inputs[0],
                                     statement=f"the registered figures give {format_quantity(cr.quantity)} ({cr.formula})",
                                     evidence=cr.inputs)),
            relation_to_central_decision=T.RelationToCentralDecision.CONSTRAINS,
            authority_required=T.Authority.CLIENT)
        return T.Add(new_entity(
            ctx, T.Kind.CONFLICT, payload, derived_from=(objective.id,) + cr.inputs,
            relation=T.RelationToCentralDecision.CONSTRAINS, confidence=T.Confidence(1.0, "computed"),
            decision_id=decision_id(ctx.registry), weight=0.9, status=T.Status.OPEN))

    @staticmethod
    def _decision_required(ctx: MethodContext, objective: T.Entity, target: T.Quantity, cr) -> T.Add:
        """FM3: the objective is the client's, so only the client can change
        it or accept the shortfall. Citing the objective is what makes L12's
        query see that it was asked."""
        payload = T.DecisionRequiredPayload(
            text=(f"{objective.id} targets {format_quantity(target)}; the registered figures give "
                  f"{format_quantity(cr.quantity)}. Change the target, change the scope, or accept the shortfall"),
            from_authority=T.Authority.CLIENT, decision_id=decision_id(ctx.registry), options=(objective.id,))
        return T.Add(new_entity(
            ctx, T.Kind.DECISION_REQUIRED, payload, derived_from=(objective.id,) + cr.inputs,
            relation=T.RelationToCentralDecision.CONSTRAINS, confidence=T.Confidence(None),
            decision_id=decision_id(ctx.registry), weight=0.9, status=T.Status.OPEN))
