"""objective_stake - CALCULATION: what settling this decision is worth, in the
figures this engagement already registered.

The other half of the hole `route_dependency` opens on. That method says which
route this organisation is equipped for and refuses to price it; this one says
what the decision is worth at all, and it may say it only in numbers the
register already holds.

Where the figure comes from, and where it may not come from:

  OS1 the magnitude is COPIED, never coined. An aim the engagement registered -
      an OBJECTIVE or a SUCCESS_CRITERION - carries the level it is set at as a
      `target` Quantity, on a MEASURE the engagement named. The BENEFIT this
      method writes carries that same Quantity, cited to the row it was copied
      from, so every figure on the page is one somebody in the engagement put
      there (EvidenceRequirement.forbid_new_quantities: calculated, or copied
      by id).
  OS2 the one figure it DERIVES is a ratio through ctx.calc: where a live
      quantified FACT stands on the same MEASURE as the aim, `ratio` gives the
      exact, recomputable distance between what is recorded and what is wanted,
      stored as a CALCULATED fact with its formula and inputs. L7 recomputes
      it; nothing here quantises, rounds or blends anything by hand.
  OS3 an aim with no target, or a target on no measure, is a HOLE and is asked
      about (design 1). It is never filled with a default, an average or a
      figure from another aim: an engagement that does not say what it is
      aiming at has not aimed low, it has not said.
  OS4 nothing here separates the routes. The stake is what ANY route to this
      decision is for, so the row bears on every live route and therefore on
      none of them in particular (`recommendation.points_to` passes over a row
      that names them all). Which route to take is `route_dependency`'s
      evidence and the decision owner's choice; what the choice is worth is
      this method's, and the two are kept apart on purpose.

No net position and no subtraction: the Calculator offers neither, so the
distance is stated as a ratio and the reader does the arithmetic the engine is
not licensed to do outside the audited boundary.
"""
from __future__ import annotations

from typing import Any, Sequence

from app.engine import types as T
from app.engine.calc import IncomparableInputs
from app.engine.calc.arith import quantity_of
from app.engine.calc.units import format_quantity
from app.engine.methods.builtin.cost_benefit import (
    calculated_fact,
    known_formulas,
    pin_question,
)
from app.engine.methods.builtin.org_design import display_text, live, require_citations
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

# The kinds that carry an AIM: a text, the MEASURE it is counted on, and the
# level it is set at. Both are read the same way and neither is preferred -
# `quantity_of` already knows that an objective's magnitude lives in `target`.
AIM_KINDS: tuple[T.Kind, ...] = (T.Kind.OBJECTIVE, T.Kind.SUCCESS_CRITERION)


def aims(view: Any) -> list[T.Entity]:
    """Every live row that states something this engagement is aiming at, in id
    order within kind order. Order is the catalogue's and the register's, never
    a wording's, so two runs over one registry write the same rows."""
    out: list[T.Entity] = []
    for kind in AIM_KINDS:
        out.extend(sorted(live(view, kind), key=lambda e: e.id))
    return out


def measure_of(view: Any, aim: T.Entity) -> T.Entity | None:
    """The MEASURE an aim is counted on, where the register holds it live."""
    measure_id = getattr(aim.payload, "measure_id", None)
    if not measure_id:
        return None
    row = view.get(measure_id)
    if row is None or row.kind is not T.Kind.MEASURE or row.status in T.TERMINAL_STATUSES:
        return None
    return row


def level_on(view: Any, measure_id: str, aim_id: str) -> T.Entity | None:
    """The live quantified FACT recorded on this measure, if the engagement has
    one: where the thing stands, against where the aim puts it.

    The first in id order and never a chosen one: picking among several would
    be this method deciding which of the client's own figures is the real one,
    which is a reconciliation and belongs to the calculator's own machinery.
    Two facts that disagree on one measure are a CONFLICT somebody else raises.
    """
    for fact in sorted(live(view, T.Kind.FACT), key=lambda e: e.id):
        if fact.id == aim_id or fact.payload.measure_id != measure_id:
            continue
        if fact.payload.quantity is not None:
            return fact
    return None


def decision_in(view: Any) -> T.Entity | None:
    """The decision this run is about: the engagement's central one where the
    window carries it, and otherwise the decision the window DOES carry.

    A specialist window is narrower than the engagement and does not hold the
    central decision, so a method that asked only for that produced nothing at
    all whenever the selector tied it with another and it ran as an assignment.
    What the aims are a stake in is still in the window; asking for it that way
    is the difference between a method that works wherever it is run and one
    that works only on the wide view.
    """
    central = view.central_decision()
    if central is not None:
        return central
    held = sorted(live(view, T.Kind.DECISION), key=lambda e: e.id)
    return held[0] if held else None


def routes_for(view: Any, decision_id: str) -> tuple[str, ...]:
    """Every live route registered for this decision, in id order. OS4: the
    stake bears on all of them, which is what keeps it from separating any of
    them."""
    return tuple(sorted(o.id for o in live(view, T.Kind.OPTION)
                        if o.payload.decision_id == decision_id))


def stake_registered(view: Any, aim_id: str) -> bool:
    """Whether the stake in this aim is already on the register. Read by
    citation, so a second run adds nothing and a reworded row is still the
    same row."""
    return any(aim_id in b.provenance.derived_from for b in live(view, T.Kind.BENEFIT))


def asked_about(view: Any, aim_id: str) -> bool:
    """Whether the hole in this aim has already been put to somebody, at any
    status: an answered question is a closed question, and "we have no target
    for that" is an answer."""
    return any(aim_id in (q.payload.about_ids or ()) for q in view.query(T.Kind.QUESTION))


def basis_of(aim: T.Entity) -> str:
    """Where the figure came from, in CostPayload/BenefitPayload's own closed
    vocabulary. The client's own aim is a client fact; anything else is a row
    whose origin this method will not overstate."""
    return "client_fact" if aim.provenance.actor is T.Actor.CLIENT else "unknown"


def _stake_text(view: Any, aim: T.Entity, measure: T.Entity, decision: T.Entity) -> str:
    """What the row SAYS: the aim in the engagement's own words, the measure it
    is counted on, and the decision it is the stake in. Every noun is a
    registered row's wording or an id; the frame is all this method adds."""
    return (f"What settling {decision.id} is worth, as this engagement registered it: "
            f"{display_text(aim).strip().rstrip('.')} ({aim.id}), counted on "
            f"{display_text(measure).strip()} ({measure.id})")


def _no_target_question(ctx: MethodContext, aim: T.Entity, measure: T.Entity,
                        decision_id: str) -> T.QuestionPayload:
    """OS3: the aim is registered and the level it is set at is not. Asked
    against the MEASURE it is already counted on, so the answer is one figure
    and not an opinion."""
    return T.QuestionPayload(
        text=(f"What level is {aim.id} set at on {display_text(measure).strip()} ({measure.id})? "
              f"The aim is registered: {display_text(aim).strip().rstrip('.')}. Without the level "
              "there is no figure to say what settling the decision is worth."),
        asks_for=(T.AsksFor(T.Kind.FACT, {"has_quantity": True}),),
        issue_ids=ctx.issue_ids,
        why="an aim with no level is a direction, not a magnitude, and no figure may be supplied for it",
        effort=T.EffortClass.LOOKUP, strategy=T.FillStrategy.ASK_CLIENT,
        about_ids=(aim.id, measure.id), decision_id=decision_id)


def _no_measure_question(ctx: MethodContext, aim: T.Entity, decision_id: str) -> T.QuestionPayload:
    """OS3, the other hole: a level with nothing to count it on. A figure whose
    measure is unknown cannot be joined to anything the engagement holds, so it
    is asked rather than assumed onto the nearest measure."""
    return T.QuestionPayload(
        text=(f"Which measure is {aim.id} counted on? The aim is registered: "
              f"{display_text(aim).strip().rstrip('.')}. A figure with no measure behind it "
              "cannot be compared with anything else this engagement holds."),
        asks_for=(T.AsksFor(T.Kind.MEASURE),), issue_ids=ctx.issue_ids,
        why="a quantity is only comparable against the measure it is counted on",
        effort=T.EffortClass.OFFHAND, strategy=T.FillStrategy.ASK_CLIENT,
        about_ids=(aim.id,), decision_id=decision_id)


def _v_every_figure_is_registered(view: Any, result: MethodResult) -> list[T.Finding]:
    """OS1 re-checked on the finished result: every BENEFIT that carries a
    Quantity cites a row that carries the SAME quantity, so the figure was
    copied and not typed.

    The mutation this catches is the only interesting one here: read the target
    off the aim, adjust it, and write the adjusted figure. Comparison is on the
    Quantity itself, which carries its unit, its dimensions and its precision,
    so a rescaled or re-based figure is a different object and is caught.
    """
    out: list[T.Finding] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is None or e.kind is not T.Kind.BENEFIT:
            continue
        quantity = getattr(e.payload, "quantity", None)
        if quantity is None:
            continue
        sources = [view.get(i) for i in e.provenance.derived_from]
        if not any(s is not None and quantity_of(s) == quantity for s in sources):
            out.append(T.Finding(
                law="M.objective_stake.uncopied_figure", where=e.id or e.kind.value,
                issue="a benefit carries a figure no row it cites carries",
                fix="copy the registered quantity by id, or write no figure"))
    return out


def pending(view: Any) -> bool:
    """Whether any aim this engagement registered still has a stake to write or
    a hole to ask about. Reads exactly what `run` reads, so the selector and
    the method cannot disagree about whether a run would do anything."""
    if decision_in(view) is None:
        return False
    for aim in aims(view):
        if stake_registered(view, aim.id) or asked_about(view, aim.id):
            continue
        if measure_of(view, aim) is None:
            # A level with no measure is asked about; an aim that states
            # neither is another method's business and this one is silent.
            if quantity_of(aim) is not None:
                return True
            continue
        return True                          # the stake, or the ask for its level
    return False


@register
class ObjectiveStakeMethod:
    spec = MethodSpec(
        id="objective_stake", version=1,
        applicability=(
            # "How much is this decision worth?" - the quantified question
            # asked of the decision itself. It is the one node in the tree that
            # asks for a magnitude about the choice rather than about a cost,
            # a benefit or an outcome already named, which is why no other
            # method in the library declares it.
            QuestionShape(T.Interrogative.HOW_MUCH, T.Kind.DECISION),
        ),
        answers=(T.Interrogative.HOW_MUCH,),
        required_inputs=(
            InputSpec("aims", T.Kind.OBJECTIVE, min_count=1, effort=T.EffortClass.OFFHAND,
                      why_needed="what settling the decision is worth is what the engagement said "
                                 "it was aiming at; with no aim registered there is no stake"),
        ),
        optional_inputs=(
            InputSpec("criteria", T.Kind.SUCCESS_CRITERION, min_count=0,
                      why_needed="a success criterion states an aim and the level it is set at"),
            InputSpec("measures", T.Kind.MEASURE, min_count=0,
                      why_needed="the measure an aim is counted on"),
            InputSpec("levels", T.Kind.FACT, filter={"has_quantity": True}, min_count=0,
                      why_needed="where the thing stands today, against where the aim puts it"),
            InputSpec("options", T.Kind.OPTION, min_count=0,
                      why_needed="the routes the stake is the stake in"),
            InputSpec("benefits", T.Kind.BENEFIT, min_count=0,
                      why_needed="what is already registered, so no stake is written twice"),
        ),
        execution=T.ExecutionType.CALCULATION,
        output_kinds=(T.Kind.BENEFIT, T.Kind.FACT, T.Kind.QUESTION),
        output_schema=None,
        evidence=EvidenceRequirement(),
        limitations=(
            "states what the engagement said it was aiming at; it never estimates a value the "
            "register does not hold, and an aim with no level is asked about rather than filled in",
            "no net position: the calculator offers no subtraction, so the distance between where "
            "a thing stands and where the aim puts it is stated as a ratio",
            "separates no routes: the stake is what any route to this decision is for, so it bears "
            "on all of them and tells none of them apart",
        ),
        validators=(require_citations("objective_stake"), _v_every_figure_is_registered),
        cost_class=1, max_model_calls=0, pending=pending)

    def run(self, ctx: MethodContext) -> MethodResult:
        view = ctx.registry
        decision = decision_in(view)
        if decision is None:
            return MethodResult(questions=(T.QuestionPayload(
                text="Which decision is this worth deciding? An aim is a stake in a choice.",
                asks_for=(T.AsksFor(T.Kind.DECISION),), issue_ids=ctx.issue_ids,
                why="what a decision is worth is only a figure once there is a decision",
                effort=T.EffortClass.OFFHAND, strategy=T.FillStrategy.ASK_CLIENT),))

        weight = T.SENSITIVITY[T.RelationToCentralDecision.EVIDENCES]
        routes = routes_for(view, decision.id)
        seen = known_formulas(view)
        deltas: list[T.EntityDelta] = []
        questions: list[T.QuestionPayload] = []

        for aim in aims(view):
            if stake_registered(view, aim.id) or asked_about(view, aim.id):
                continue
            target = quantity_of(aim)
            measure = measure_of(view, aim)
            if measure is None:
                if target is not None:
                    questions.append(_no_measure_question(ctx, aim, decision.id))
                continue
            if target is None:
                questions.append(_no_target_question(ctx, aim, measure, decision.id))
                continue

            cited = [aim.id, measure.id]
            level = level_on(view, measure.id, aim.id)
            if level is not None:
                try:
                    cr = ctx.calc.ratio(level, aim)
                except IncomparableInputs as exc:
                    # OS3 at the calculator's own boundary: a dimension the two
                    # figures do not share is a hole, and no distance is stated
                    # across it.
                    questions.append(pin_question(
                        ctx, (level.id, aim.id), tuple(getattr(exc, "unpinned", ()) or ()),
                        why="how far a level stands from an aim is only a figure where the two "
                            "share every pinned dimension"))
                    cr = None
                except ValueError:
                    cr = None
                if cr is not None and cr.formula not in seen:
                    seen.add(cr.formula)
                    deltas.append(calculated_fact(
                        ctx, self.spec.id, cr, measure_id=measure.id,
                        statement=(f"Where {measure.id} stands against the level {aim.id} sets: "
                                   f"{cr.formula} = {format_quantity(cr.quantity)}")))
                    cited.append(level.id)

            deltas.append(T.Add(new_entity(
                ctx, T.Kind.BENEFIT,
                T.BenefitPayload(text=_stake_text(view, aim, measure, decision),
                                 basis=basis_of(aim), quantity=target, for_ids=routes),
                derived_from=tuple(cited),
                relation=T.RelationToCentralDecision.EVIDENCES,
                confidence=T.Confidence(None), decision_id=decision.id, weight=weight)))
        return MethodResult(deltas=tuple(deltas), questions=tuple(questions))


__all__ = ["AIM_KINDS", "ObjectiveStakeMethod", "aims", "asked_about", "basis_of", "decision_in",
           "level_on", "measure_of", "pending", "routes_for", "stake_registered"]
