"""cost_benefit - CALCULATION: totals of the registered cost and benefit entities.

Also the home of the calculation helpers every quantified builtin shares
(calculated_fact, pin_question, known_formulas, live, decision_id): they live
with the first method that needs them so the package stays one file per
method with no extra module to own.

Laws this module enforces, and why:

  Q1  every quantity this method writes is a CalcResult from ctx.calc, stored
      as FACT(basis=calculated, formula, inputs) - a total typed by hand would
      be a number with no lineage, exactly what L7's exact recompute exists to
      catch. The aggregate COST/BENEFIT rows copy that same CalcResult, so no
      figure exists that the formula does not reproduce.
  Q2  a refusal is a QUESTION, never a guess: when the calculator raises
      IncomparableInputs (a currency or period basis unpinned, or pinned
      differently with no conversion fact) the method opens a
      pin-the-dimension question and writes no total. Absence of a dimension
      is a typed hole, not a defect and not a default (design 1).
  Q3  calculated facts are written by Actor.CALCULATOR and born CONFIRMED:
      arithmetic is owned by the deterministic engine (AUTHORITY_OF), the
      calculator is its one confirmer (MAY_CONFIRM), and the L7 gate
      re-verifies recompute() exactly, so a drifted number is caught at the
      gate rather than forgiven at the source.

No subtraction is offered by the Calculator protocol, so no net position is
computed here: the two totals stand side by side and the reader subtracts,
rather than the engine growing arithmetic outside the audited boundary.
"""
from __future__ import annotations

from app.engine.calc import IncomparableInputs
from app.engine.calc.arith import quantity_of
from app.engine.calc.units import format_quantity
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
from app.engine.registry import CalcResult, RegistryView
from app.engine.types import (
    TERMINAL_STATUSES,
    Actor,
    Add,
    AsksFor,
    BenefitPayload,
    Confidence,
    CostPayload,
    EffortClass,
    Entity,
    ExecutionType,
    FactBasis,
    FactPayload,
    FillStrategy,
    Finding,
    Interrogative,
    Kind,
    Provenance,
    QuestionPayload,
    RelationToCentralDecision,
    Relevance,
    Status,
    UnitFamily,
    make_entity,
)


# =============================================================================
# shared helpers for the quantified builtins
# =============================================================================

def live(view: RegistryView, kind: Kind | None = None) -> list[Entity]:
    """The registry's current position: latest rows that are not retired.
    RegistryView guarantees only query(), so the terminal filter is applied
    here rather than relying on a live() the protocol does not promise."""
    return [e for e in view.query(kind) if e.status not in TERMINAL_STATUSES]


def decision_id(view: RegistryView) -> str | None:
    d = view.central_decision()
    return d.id if d is not None else None


def known_formulas(view: RegistryView) -> set[str]:
    """Formulas already registered as calculated facts. Re-running a
    CALCULATION method must be idempotent: the same arithmetic over the same
    ids is the same fact, not a growing pile of duplicates."""
    return {f.payload.formula for f in live(view, Kind.FACT)
            if f.payload.basis is FactBasis.CALCULATED and f.payload.formula}


def calculated_fact(ctx: MethodContext, method_id: str, cr: CalcResult, *,
                    measure_id: str | None = None, statement: str | None = None) -> Add:
    """A CalcResult as the registry records arithmetic (Q1/Q3): the formula
    over entity ids, the input ids, the exact quantity, written by the
    CALCULATOR and CONFIRMED because recompute() reproduces it exactly."""
    text = statement or f"{cr.formula} = {format_quantity(cr.quantity)}"
    payload = FactPayload(statement=text, basis=FactBasis.CALCULATED, measure_id=measure_id,
                          quantity=cr.quantity, formula=cr.formula, inputs=cr.inputs)
    entity = make_entity(
        kind=Kind.FACT, engagement_id=ctx.registry.engagement_id, payload=payload,
        provenance=Provenance(actor=Actor.CALCULATOR, actor_ref=f"calc:{method_id}", derived_from=cr.inputs),
        confidence=Confidence(1.0, "computed"),
        relevance=Relevance(decision_id(ctx.registry), 0.4),
        relation=RelationToCentralDecision.INFORMS, status=Status.CONFIRMED)
    return Add(entity)


def pin_question(ctx: MethodContext, entity_ids: tuple[str, ...], unpinned: tuple[str, ...], why: str) -> QuestionPayload:
    """The calculator refused because a dimension is unknown or unjoinable:
    the typed hole becomes a question naming exactly which dimension to pin
    on which entities (Q2), so the client is asked one answerable thing."""
    names = ", ".join(unpinned) if unpinned else "the dimension the comparison needs"
    ids = ", ".join(entity_ids)
    return QuestionPayload(
        text=f"Pin {names} on {ids}: the calculation cannot proceed while a dimension is unknown",
        asks_for=(AsksFor(Kind.FACT, {"has_quantity": True}),),
        issue_ids=ctx.issue_ids, why=why,
        effort=EffortClass.OFFHAND, strategy=FillStrategy.ASK_CLIENT)


def calculated_traceable(view: RegistryView, result: MethodResult) -> list[Finding]:
    """Validator (Q1): a calculated fact in a result without formula and
    inputs is a coined number - nothing could ever recompute it."""
    out: list[Finding] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is None or e.kind is not Kind.FACT or e.payload.basis is not FactBasis.CALCULATED:
            continue
        if not e.payload.formula or not e.payload.inputs:
            out.append(Finding(
                law="M.calc.untraceable_quantity", where=e.id or e.kind.value,
                issue="a calculated fact without formula and inputs is a coined number",
                fix="produce every quantity through ctx.calc and store its CalcResult"))
    return out


# =============================================================================
# the method
# =============================================================================

@register
class CostBenefitMethod:
    spec = MethodSpec(
        id="cost_benefit", version=1,
        applicability=(
            QuestionShape(Interrogative.HOW_MUCH, Kind.COST, quantified=True),
            QuestionShape(Interrogative.HOW_MUCH, Kind.BENEFIT, quantified=True),
        ),
        answers=(Interrogative.HOW_MUCH,),
        required_inputs=(
            # The evidential base: at least one money fact with its currency
            # and period basis pinned, so the selection itself never runs the
            # method on numbers no total could lawfully join (design 7.2).
            InputSpec("money_facts", Kind.FACT,
                      filter={"has_quantity": True, "unit_family": UnitFamily.MONEY},
                      dimensions_required=("currency", "period_basis"),
                      effort=EffortClass.DOCUMENT,
                      why_needed="a cost/benefit total needs money figures whose currency and period basis are pinned"),
        ),
        optional_inputs=(
            InputSpec("costs", Kind.COST), InputSpec("benefits", Kind.BENEFIT),
        ),
        execution=ExecutionType.CALCULATION,
        output_kinds=(Kind.COST, Kind.BENEFIT, Kind.FACT, Kind.QUESTION),
        output_schema=None,
        evidence=EvidenceRequirement(),
        limitations=("no net position: the calculator offers no subtraction, so the totals stand side by side",),
        validators=(calculated_traceable,),
        cost_class=1, max_model_calls=0)

    def run(self, ctx: MethodContext) -> MethodResult:
        view = ctx.registry
        deltas: list = []
        questions: list[QuestionPayload] = []
        seen = known_formulas(view)
        for kind in (Kind.COST, Kind.BENEFIT):
            carriers = [e for e in live(view, kind) if quantity_of(e) is not None]
            if not carriers:
                continue
            try:
                cr = ctx.calc.total(carriers)
            except IncomparableInputs as exc:
                # Q2: no total across incomparable figures; the hole is asked.
                questions.append(pin_question(
                    ctx, tuple(e.id for e in carriers), tuple(getattr(exc, "unpinned", ()) or ()),
                    why="a total is only lawful over figures that share every pinned dimension"))
                continue
            except ValueError:
                # An unregistered or quantity-less carrier slipped in; nothing
                # lawful to total, and inventing a partial total would hide it.
                continue
            if cr.formula in seen:
                continue
            seen.add(cr.formula)
            label = kind.value
            deltas.append(calculated_fact(
                ctx, self.spec.id, cr,
                statement=f"Total of the registered {label} entities: {cr.formula} = {format_quantity(cr.quantity)}"))
            if kind is Kind.COST:
                agg = CostPayload(text=f"Total of the registered {label} entities", basis="calculated",
                                  quantity=cr.quantity, for_ids=cr.inputs)
            else:
                agg = BenefitPayload(text=f"Total of the registered {label} entities", basis="calculated",
                                     quantity=cr.quantity, for_ids=cr.inputs)
            deltas.append(Add(new_entity(
                ctx, kind, agg, derived_from=cr.inputs,
                relation=RelationToCentralDecision.INFORMS, confidence=Confidence(1.0, "computed"),
                decision_id=decision_id(view), weight=0.4)))
        return MethodResult(deltas=tuple(deltas), questions=tuple(questions))
