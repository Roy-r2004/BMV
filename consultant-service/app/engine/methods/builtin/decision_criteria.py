"""decision_criteria - DETERMINISTIC: name the criteria a comparison is to be
judged against, by restating what the client has already declared.

Nothing here is invented. A criterion is one OBJECTIVE, CONSTRAINT or
SUCCESS_CRITERION the client stated, restated in that row's own words and
citing it; the method coins no dimension of judgement of its own and it sets
no weight. That is the point of it: EVALUATION_CRITERION is the kind
`option_evaluation` and `prioritization` both require and the kind nothing in
the library used to write, so the comparison half of the engine could never
run at all - and the obvious way to fix that, letting a model name the
criteria, would have the consultant decide what the client's decision is
about.

Laws this module enforces, and the failure each prevents:

  DC1 every criterion restates a row the client declared and cites it. A
      criterion that came from nowhere would be the consultant's own priority
      entering the comparison as if it were the client's (spec section 5: the
      client owns objectives, priorities and constraints).
  DC2 no criterion is born with a weight. `weight` and `weight_set_by` stay
      None, so `option_evaluation.client_weighted` stays False until the
      client answers the weighting question, and the options are listed
      rather than ranked. A criteria writer that set its own weights would
      rank the options on the consultant's priorities under the client's
      name - the exact failure O3 exists to prevent.
  DC3 one criterion per declared row, ever. A second run over an unchanged
      registry restates nothing: the same declaration would otherwise become
      two criteria and count twice in any coverage the comparison reads.
"""
from __future__ import annotations

from typing import Any

from app.engine import types as T
from app.engine.methods.builtin.capability_gap import added_of, wording
from app.engine.methods.builtin.cost_benefit import live
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

# The kinds a criterion may restate: the three ways the client declares what a
# good answer looks like. A closed Kind list, never a text filter - and the
# order is the order criteria are written in, so two runs agree.
DECLARED_KINDS: tuple[T.Kind, ...] = (T.Kind.OBJECTIVE, T.Kind.CONSTRAINT, T.Kind.SUCCESS_CRITERION)


def declared_sources(view: Any) -> list[T.Entity]:
    """Every live row the client declared that a criterion may restate, in kind
    order then id order. Read from the registry, so a registry that gathered
    different objectives yields different criteria without anything here
    knowing why."""
    out: list[T.Entity] = []
    for kind in DECLARED_KINDS:
        out.extend(sorted(live(view, kind), key=lambda e: e.id))
    return out


def already_restated(view: Any, decision_id: str, source_id: str) -> bool:
    """DC3: this declaration is already a criterion for this decision. Read by
    citation, not by wording: two rows that happen to read alike are two
    declarations, and one row restated twice is one."""
    for c in live(view, T.Kind.EVALUATION_CRITERION):
        if c.payload.decision_id == decision_id and source_id in c.provenance.derived_from:
            return True
    return False


def _v_criterion_restates_a_declaration(view: Any, result: MethodResult) -> list[T.Finding]:
    """DC1 re-checked on the finished result: every criterion written cites a
    live declared row and carries that row's own wording."""
    out: list[T.Finding] = []
    for e in added_of(result, T.Kind.EVALUATION_CRITERION):
        sources = [s for s in (view.get(i) for i in e.provenance.derived_from)
                   if s is not None and s.kind in DECLARED_KINDS]
        if not sources:
            out.append(T.Finding(
                law="M.decision_criteria.invented_criterion", where=e.id or e.kind.value,
                issue="a criterion cites no objective, constraint or success criterion",
                fix="restate a row the client declared, or write no criterion",
                entity_ids=(e.id,) if e.id else ()))
            continue
        if not any(wording(s) == e.payload.text for s in sources):
            out.append(T.Finding(
                law="M.decision_criteria.reworded_criterion", where=e.id or e.kind.value,
                issue="a criterion does not carry the wording of the declaration it cites",
                fix="restate the declaration in its own words; a reworded criterion is a new one",
                entity_ids=(e.id,) if e.id else ()))
    return out


def _v_criterion_carries_no_weight(view: Any, result: MethodResult) -> list[T.Finding]:
    """DC2 re-checked. Both halves are compared with `is not None` / `is not`:
    a weight of 0.0 is a weight somebody set, and reading it as absence is how
    a consultant weight would slip in as no weight at all."""
    return [T.Finding(
        law="M.decision_criteria.consultant_weight", where=e.id or e.kind.value,
        issue="a criterion is born carrying a weight",
        fix="leave weight and weight_set_by unset; the client sets the weights or nothing ranks",
        entity_ids=(e.id,) if e.id else ())
        for e in added_of(result, T.Kind.EVALUATION_CRITERION)
        if e.payload.weight is not None or e.payload.weight_set_by is not None]


def pending(view: Any) -> bool:
    """DC4: whether this method still has a criterion to write or a hole to
    ask about.

    Three states, all read from the register and none of them a judgement. No
    central decision, or nothing declared: the run asks, and asking is work.
    Every declaration already restated: the run would add nothing, supersede
    nothing and ask nothing - it would occupy a selection slot to leave the
    registry exactly as it found it.

    The method's own `run` reads the same three things in the same order, so
    this cannot drift into a different opinion about what it would do.
    """
    if view.central_decision() is None:
        return True
    sources = declared_sources(view)
    if not sources:
        return True
    decision = view.central_decision()
    return any(wording(s) and not already_restated(view, decision.id, s.id) for s in sources)


SPEC = MethodSpec(
    id="decision_criteria",
    version=1,
    applicability=(
        QuestionShape(T.Interrogative.WHICH, T.Kind.DECISION),
        QuestionShape(T.Interrogative.WHICH, T.Kind.DECISION, comparative=True),
        QuestionShape(T.Interrogative.WHICH, T.Kind.ACTION, comparative=True),
        QuestionShape(T.Interrogative.WHICH, T.Kind.INITIATIVE, comparative=True),
    ),
    answers=(T.Interrogative.WHICH,),
    required_inputs=(
        InputSpec("decision", T.Kind.DECISION, {"role": T.DecisionRole.CENTRAL}, min_count=1,
                  effort=T.EffortClass.OFFHAND,
                  why_needed="a criterion is a criterion FOR a decision; without one it judges nothing"),
        InputSpec("declarations", T.Kind.OBJECTIVE, min_count=1, effort=T.EffortClass.OFFHAND,
                  why_needed="the criteria are the client's declared objectives, not the consultant's"),
    ),
    optional_inputs=(
        InputSpec("constraints", T.Kind.CONSTRAINT, min_count=0,
                  why_needed="a constraint is a criterion an option has to clear"),
        InputSpec("success_criteria", T.Kind.SUCCESS_CRITERION, min_count=0,
                  why_needed="what the client said good would look like"),
        InputSpec("criteria", T.Kind.EVALUATION_CRITERION, min_count=0,
                  why_needed="what is already declared, so nothing is restated twice"),
    ),
    execution=T.ExecutionType.DETERMINISTIC,
    output_kinds=(T.Kind.EVALUATION_CRITERION,),
    output_schema=None,
    evidence=EvidenceRequirement(),
    limitations=(
        "restates the client's declarations as criteria; it does not decide what matters",
        "sets no weight: until the client weights them the criteria list, they do not rank",
    ),
    validators=(_v_criterion_restates_a_declaration, _v_criterion_carries_no_weight),
    cost_class=1,
    max_model_calls=0,
    pending=pending,
)


def _no_decision_question(ctx: MethodContext) -> T.QuestionPayload:
    """The typed hole when nothing central is registered. A criterion for no
    decision would be a preference with nothing to apply it to."""
    return T.QuestionPayload(
        text="Which decision are these criteria for?",
        asks_for=(T.AsksFor(T.Kind.DECISION),), issue_ids=ctx.issue_ids,
        why="a criterion judges options for one decision; without it nothing is being judged",
        effort=T.EffortClass.OFFHAND, strategy=T.FillStrategy.ASK_CLIENT)


def _nothing_declared_question(ctx: MethodContext) -> T.QuestionPayload:
    """The typed hole when the client has declared nothing to judge against.
    The method asks rather than naming criteria of its own (DC1)."""
    return T.QuestionPayload(
        text="What should a good answer to this decision achieve, and what must it not break?",
        asks_for=(T.AsksFor(T.Kind.OBJECTIVE), T.AsksFor(T.Kind.CONSTRAINT)),
        issue_ids=ctx.issue_ids,
        why="the criteria a choice is judged on are the client's to declare, never the consultant's",
        effort=T.EffortClass.OFFHAND, strategy=T.FillStrategy.ASK_CLIENT)


@register
class DecisionCriteriaMethod:
    spec = SPEC

    def run(self, ctx: MethodContext) -> MethodResult:
        view = ctx.registry
        decision = view.central_decision()
        if decision is None:
            return MethodResult(questions=(_no_decision_question(ctx),))
        sources = declared_sources(view)
        if not sources:
            return MethodResult(questions=(_nothing_declared_question(ctx),))
        issue = view.get(ctx.issue_ids[0]) if ctx.issue_ids else None
        fallback = T.SENSITIVITY[T.RelationToCentralDecision.INFORMS]
        deltas: list[T.EntityDelta] = []
        for source in sources:
            if already_restated(view, decision.id, source.id):
                continue
            text = wording(source)
            if not text:
                # A declaration with no wording states no criterion. Absence is
                # left absent rather than filled with the row's kind.
                continue
            payload = T.EvaluationCriterionPayload(
                text=text, decision_id=decision.id, weight=None, weight_set_by=None)
            deltas.append(T.Add(new_entity(
                ctx, T.Kind.EVALUATION_CRITERION, payload, derived_from=(source.id, decision.id),
                relation=T.RelationToCentralDecision.INFORMS, confidence=T.Confidence(None),
                decision_id=decision.id,
                weight=issue.relevance.weight if issue is not None else fallback)))
        return MethodResult(deltas=tuple(deltas))


__all__ = ["DECLARED_KINDS", "SPEC", "DecisionCriteriaMethod", "already_restated", "declared_sources"]
