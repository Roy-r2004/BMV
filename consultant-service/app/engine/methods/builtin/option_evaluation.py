"""option_evaluation - DETERMINISTIC: score the registered options against
the registered criteria, by a declared rule per criterion, and put the
trade-off to whoever owns the decision.

Nothing here judges. A score is read off the registry by the declared rule
the registered evidence selects, and it carries the ids it was read from.
Where the registry cannot settle a score, the method asks; where the registry
holds two scores for one option on one criterion, the method opens a CONFLICT
and writes neither.

Laws this module enforces, and the failure each prevents:

  O1  two scorings of one (option, criterion) never become one number. There
      is no mean, no blend and no pick in this module: the pair is a CONFLICT
      with both scorings as conclusions, each with its own evidence, and no
      Score is written for that pair. An average is the most plausible-looking
      way to state a figure that no source gives (design 1, consequence 2).
  O2  every score cites the evidence it was read from. A scoring whose
      evidence is empty is not admitted as a scoring at all, so an option
      cannot be scored on the strength of nobody's record.
  O3  only the client's declared weights may order options. A criterion whose
      weight is None, or whose weight was set by the consultant, produces a
      listing in registration order and a question asking the client to set
      the weights - because a consultant who both weights the criteria and
      ranks the options has made the client's decision for them (spec
      section 5: the client owns objectives, priorities and constraints).
  O4  a material trade-off is put to the decision owner as a DECISION_REQUIRED.
      A trade-off on the central decision that the options do not all resolve
      the same way is the client's to make, and the engine's job is to surface
      it, not to pick.

Why the ordering counts criteria rather than adding scores: an
EVALUATION_CRITERION declares no direction, so the engine does not know
whether more of a criterion is better, and scores of different criteria are
not one unit anyway. The order is therefore by the client-weighted set of
criteria on which an option is evidenced at all; the scores themselves stay
visible on the trade-off for the decision owner to read.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any, Sequence

from app.engine import types as T
from app.engine.calc.arith import quantity_of
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

# Rendering labels on the trade-off row. A reader must be able to tell an
# order that means something from a list that does not (O3).
RANKED_LABEL = "ranked_by_client_weights"
LISTED_LABEL = "listed_unranked"


@dataclass(frozen=True)
class Scoring:
    """One reading of one (option, criterion) pair, and where it came from.
    `evidence` is never empty: a scoring with nothing behind it is not built."""
    option_id: str
    criterion_id: str
    value: Decimal
    evidence: tuple[str, ...]
    source_id: str
    source_kind: T.Kind


def linking_facts(view: Any, option: T.Entity, criterion: T.Entity) -> list[T.Entity]:
    """The registered facts that cite BOTH the option and the criterion. That
    citation is the only structural link between an option and a criterion the
    registry holds - neither payload names the other - so it is what a score
    may be read from. A fact that cites only the option says nothing about
    this criterion, and is not evidence for a score on it."""
    return [f for f in live(view, T.Kind.FACT)
            if option.id in f.provenance.derived_from and criterion.id in f.provenance.derived_from]


def rule_scorings(view: Any, option: T.Entity, criterion: T.Entity) -> list[Scoring]:
    """The declared rule the registered evidence selects.

    A linking fact with a quantity is a measured scoring at that quantity's
    value; two such facts are two scorings, which is O1's case, not an
    average. Where no linking fact carries a figure, the fallback is a count
    of the linking facts - direction-free and honest about what it is, a
    count of records rather than a judgement of quality. The count is never a
    second opinion beside a figure: where a figure exists the count is not
    consulted."""
    facts = linking_facts(view, option, criterion)
    measured = [(f, q) for f in facts if (q := quantity_of(f)) is not None]
    if measured:
        return [Scoring(option.id, criterion.id, q.value, (f.id,), f.id, T.Kind.FACT) for f, q in measured]
    if facts:
        return [Scoring(option.id, criterion.id, Decimal(len(facts)),
                        tuple(f.id for f in facts), facts[0].id, T.Kind.FACT)]
    return []


def recorded_scorings(view: Any, option: T.Entity, criterion: T.Entity, own_actor_ref: str) -> list[Scoring]:
    """Scores another producer already registered for this pair on a live
    trade-off. Included so that a disagreement between two analyses surfaces
    as a CONFLICT rather than as a silent overwrite; this method's own earlier
    rows are excluded, because a run disagreeing with itself is not a
    disagreement, it is a re-run."""
    out: list[Scoring] = []
    for t in live(view, T.Kind.TRADE_OFF):
        if t.provenance.actor_ref == own_actor_ref:
            continue
        for s in t.payload.scores:
            if s.option_id != option.id or s.criterion_id != criterion.id or not s.evidence:
                continue
            out.append(Scoring(option.id, criterion.id, s.score, tuple(s.evidence), t.id, T.Kind.TRADE_OFF))
    return out


def scorings_for(view: Any, option: T.Entity, criterion: T.Entity, own_actor_ref: str) -> list[Scoring]:
    """Every scoring the registry holds for one pair: the declared rule over
    the linking evidence, plus whatever another analysis already recorded."""
    return rule_scorings(view, option, criterion) + recorded_scorings(view, option, criterion, own_actor_ref)


def settle(scorings: Sequence[Scoring]) -> tuple[T.Score | None, tuple[Scoring, ...]]:
    """O1. One value -> one Score citing every source that gives it; two
    values -> no Score and the disagreement, for the caller to register as a
    CONFLICT. There is deliberately no third branch: the arithmetic mean of
    two scorings is a number neither source states."""
    if not scorings:
        return None, ()
    values = {s.value for s in scorings}
    if len(values) > 1:
        return None, tuple(scorings)
    evidence = tuple(dict.fromkeys(e for s in scorings for e in s.evidence))
    first = scorings[0]
    return T.Score(first.option_id, first.criterion_id, first.value, evidence), ()


def client_weighted(criteria: Sequence[T.Entity]) -> bool:
    """O3. Options may be ordered only when every criterion carries a weight
    the CLIENT set. `weight_set_by` is read as an identity, not as a
    truthiness: a consultant weight is a real weight and still may not rank."""
    if not criteria:
        return False
    for c in criteria:
        if c.payload.weight is None or c.payload.weight_set_by is not T.Authority.CLIENT:
            return False
    return True


def ranked_order(options: Sequence[T.Entity], criteria: Sequence[T.Entity],
                 scores: Sequence[T.Score]) -> tuple[str, ...]:
    """The client-weighted coverage order: how much of the client's declared
    weight an option is evidenced against. Ties keep registration order, so
    the order is stable and reproducible."""
    weight = {c.id: float(c.payload.weight or 0.0) for c in criteria}
    covered = {o.id: 0.0 for o in options}
    for s in scores:
        if s.option_id in covered:
            covered[s.option_id] += weight.get(s.criterion_id, 0.0)
    position = {o.id: i for i, o in enumerate(options)}
    return tuple(sorted(covered, key=lambda i: (-covered[i], position[i])))


def diverges(scores: Sequence[T.Score]) -> bool:
    """Whether the options actually differ somewhere: two options with
    different values on one criterion. Options that score alike everywhere are
    not a trade-off and nothing is put to the decision owner."""
    by_criterion: dict[str, set[Decimal]] = {}
    for s in scores:
        by_criterion.setdefault(s.criterion_id, set()).add(s.score)
    return any(len(v) > 1 for v in by_criterion.values())


def already_registered(view: Any, payload: T.TradeOffPayload) -> bool:
    """Re-running a deterministic method over unchanged rows is the same
    conclusion, not a second one."""
    for t in live(view, T.Kind.TRADE_OFF):
        p = t.payload
        if p.decision_id == payload.decision_id and p.option_ids == payload.option_ids and p.scores == payload.scores:
            return True
    return False


def _named(entity: T.Entity) -> str:
    """A row as a question may name it: the row's own words, with its id kept
    so the answer is unambiguous.

    A question worded from ids alone says nothing to the person being asked -
    "what evidence scores OPT-98 on CRI-1" is not a question a client can
    answer - and it is the same sentence in every engagement, because ids are
    counters. The words are the engagement's own, so two engagements ask two
    different questions for the same structural reason.
    """
    return f"{wording(entity)} ({entity.id})"


def evidence_question(ctx: MethodContext, option: T.Entity, criterion: T.Entity) -> T.QuestionPayload:
    """O2's typed hole: no evidenced score for this pair. Asked, never filled
    with a placeholder - an unscored option renders as unscored."""
    return T.QuestionPayload(
        text=(f"What evidence scores {_named(option)} on {_named(criterion)}? "
              f"The option is listed unscored on that criterion until there is some"),
        asks_for=(T.AsksFor(T.Kind.FACT, {"has_quantity": True}),),
        issue_ids=ctx.issue_ids,
        why="a score with no evidence behind it is a judgement the engine is not entitled to make",
        effort=T.EffortClass.LOOKUP, strategy=T.FillStrategy.ASK_CLIENT)


def weights_question(ctx: MethodContext, decision_id: str, criteria: Sequence[T.Entity]) -> T.QuestionPayload:
    """O3's typed hole: the options are listed, not ranked, until the client
    weights the criteria. The criteria are named so the answer is one act."""
    names = ", ".join(_named(c) for c in criteria)
    return T.QuestionPayload(
        text=f"How do you weight {names} for {decision_id}? Until you do, the options are listed, not ranked",
        asks_for=(T.AsksFor(T.Kind.EVALUATION_CRITERION),),
        issue_ids=ctx.issue_ids,
        why="priorities are the client's; a ranking on consultant weights would make the choice for them",
        effort=T.EffortClass.OFFHAND, strategy=T.FillStrategy.ASK_CLIENT)


# =============================================================================
# validators - the same four laws, checked on the finished result
# =============================================================================

def score_cites_evidence(view: Any, result: MethodResult) -> list[T.Finding]:
    out: list[T.Finding] = []
    for t in added_of(result, T.Kind.TRADE_OFF):
        for s in t.payload.scores:
            if not s.evidence:
                out.append(T.Finding(
                    law="M.option_evaluation.uncited_score", where=t.id or t.kind.value,
                    issue=f"{s.option_id} is scored on {s.criterion_id} with no evidence cited",
                    fix="read the score off registered rows and cite them, or leave the pair unscored",
                    entity_ids=(t.id,) if t.id else ()))
    return out


def material_trade_off_reaches_the_owner(view: Any, result: MethodResult) -> list[T.Finding]:
    decided = {d.payload.decision_id for d in added_of(result, T.Kind.DECISION_REQUIRED)}
    out: list[T.Finding] = []
    for t in added_of(result, T.Kind.TRADE_OFF):
        if t.payload.material is True and t.payload.decision_id not in decided:
            out.append(T.Finding(
                law="M.option_evaluation.material_trade_off_not_put", where=t.id or t.kind.value,
                issue="a material trade-off was recorded without asking the decision owner to make it",
                fix="emit a DECISION_REQUIRED naming the decision and the options",
                entity_ids=(t.id,) if t.id else ()))
    return out


def ranking_only_on_client_weights(view: Any, result: MethodResult) -> list[T.Finding]:
    """O3 checked against the registry the result was built from, so a ranking
    label cannot outlive the client weights that justify it."""
    out: list[T.Finding] = []
    for t in added_of(result, T.Kind.TRADE_OFF):
        if RANKED_LABEL not in t.labels:
            continue
        criteria = [c for c in live(view, T.Kind.EVALUATION_CRITERION)
                    if c.payload.decision_id == t.payload.decision_id]
        if not client_weighted(criteria):
            out.append(T.Finding(
                law="M.option_evaluation.ranked_without_client_weights", where=t.id or t.kind.value,
                issue="options are ranked although a criterion carries no client-set weight",
                fix="list the options in registration order and ask the client to weight the criteria",
                entity_ids=(t.id,) if t.id else ()))
    return out


SPEC = MethodSpec(
    id="option_evaluation",
    version=1,
    applicability=(QuestionShape(T.Interrogative.WHICH, T.Kind.DECISION, comparative=True),),
    answers=(T.Interrogative.WHICH,),
    required_inputs=(
        InputSpec("options", T.Kind.OPTION, min_count=2, effort=T.EffortClass.OFFHAND,
                  why_needed="an evaluation needs at least two options; one option is not a choice"),
        InputSpec("criteria", T.Kind.EVALUATION_CRITERION, min_count=1, effort=T.EffortClass.OFFHAND,
                  why_needed="options are compared against declared criteria, never against each other in the abstract"),
    ),
    optional_inputs=(
        InputSpec("scoring_evidence", T.Kind.FACT, min_count=1),
        InputSpec("recorded_trade_offs", T.Kind.TRADE_OFF, min_count=1),
    ),
    execution=T.ExecutionType.DETERMINISTIC,
    output_kinds=(T.Kind.TRADE_OFF, T.Kind.CONFLICT, T.Kind.DECISION_REQUIRED, T.Kind.QUESTION),
    output_schema=None,
    evidence=EvidenceRequirement(),
    limitations=(
        "scores by declared rule from registered rows; it does not judge quality a record does not state",
        "orders options by client-weighted evidenced coverage: a criterion declares no direction, so magnitude never ranks",
    ),
    validators=(score_cites_evidence, material_trade_off_reaches_the_owner, ranking_only_on_client_weights),
    cost_class=1,
    max_model_calls=0,
)


@register
class OptionEvaluationMethod:
    spec = SPEC

    def run(self, ctx: MethodContext) -> MethodResult:
        view = ctx.registry
        deltas: list = []
        questions: list[T.QuestionPayload] = []
        central = view.central_decision()
        central_id = central.id if central is not None else None
        criteria_all = live(view, T.Kind.EVALUATION_CRITERION)
        decision_ids = list(dict.fromkeys(c.payload.decision_id for c in criteria_all if c.payload.decision_id))
        for did in decision_ids:
            criteria = [c for c in criteria_all if c.payload.decision_id == did]
            options = [o for o in live(view, T.Kind.OPTION) if o.payload.decision_id == did]
            if len(options) < 2:
                # One option is not a choice; nothing to trade off.
                continue
            scores: list[T.Score] = []
            for criterion in criteria:
                for option in options:
                    score, conflicting = settle(scorings_for(view, option, criterion, ctx.actor_ref))
                    if conflicting:
                        deltas.append(self._conflict(ctx, option, criterion, conflicting, did, central_id))
                        continue
                    if score is None:
                        questions.append(evidence_question(ctx, option, criterion))
                        continue
                    scores.append(score)
            if not scores:
                continue
            ranked = client_weighted(criteria)
            order = ranked_order(options, criteria, scores) if ranked else tuple(o.id for o in options)
            material = did == central_id and diverges(scores)
            payload = T.TradeOffPayload(
                decision_id=did, option_ids=order,
                gives_up=self._divergent_criteria(scores),
                gains="", scores=tuple(scores), material=material)
            if already_registered(view, payload):
                continue
            cited = tuple(dict.fromkeys([o.id for o in options] + [c.id for c in criteria]))
            trade_off = new_entity(
                ctx, T.Kind.TRADE_OFF, payload, derived_from=cited,
                relation=T.RelationToCentralDecision.INFORMS, confidence=T.Confidence(None),
                decision_id=did, weight=0.6)
            deltas.append(T.Add(replace(trade_off, labels=(RANKED_LABEL if ranked else LISTED_LABEL,))))
            if not ranked:
                questions.append(weights_question(ctx, did, criteria))
            if material:
                # O4: the trade-off belongs to whoever owns the decision.
                deltas.append(T.Add(new_entity(
                    ctx, T.Kind.DECISION_REQUIRED,
                    T.DecisionRequiredPayload(
                        text=(f"Choose between {', '.join(order)} for {did}: the options are not equal on every "
                              f"criterion, and the trade-off is the decision owner's to make"),
                        from_authority=T.Authority.DECISION_OWNER, decision_id=did, options=order),
                    derived_from=cited, relation=T.RelationToCentralDecision.RESOLVES,
                    confidence=T.Confidence(None), decision_id=did, weight=0.8,
                    status=T.Status.OPEN)))
        return MethodResult(deltas=tuple(deltas), questions=tuple(questions))

    @staticmethod
    def _divergent_criteria(scores: Sequence[T.Score]) -> str:
        by_criterion: dict[str, set[Decimal]] = {}
        for s in scores:
            by_criterion.setdefault(s.criterion_id, set()).add(s.score)

        names = [c for c, v in by_criterion.items() if len(v) > 1]
        return ("the options differ on " + ", ".join(sorted(names))) if names else ""

    @staticmethod
    def _conflict(ctx: MethodContext, option: T.Entity, criterion: T.Entity,
                  conflicting: Sequence[Scoring], decision_id: str, central_id: str | None) -> T.Add:
        """O1: both scorings stand, side by side, with the evidence each rests
        on. The authority asked to settle it is the decision owner when the
        decision is the central one, and the consultant otherwise (design 9.4)."""
        conclusions = tuple(T.ConflictConclusion(
            entity_id=s.source_id,
            statement=f"{option.id} scores {s.value} on {criterion.id}",
            evidence=s.evidence,
            consequence="an average would state a score neither source gives") for s in conflicting)
        kind = (T.ConflictKind.VALUE if all(s.source_kind is T.Kind.FACT for s in conflicting)
                else T.ConflictKind.SPECIALIST_DISAGREEMENT)
        authority = T.Authority.DECISION_OWNER if decision_id == central_id else T.Authority.CONSULTANT
        payload = T.ConflictPayload(
            kind=kind, subject_id=criterion.id, conclusions=conclusions,
            relation_to_central_decision=T.RelationToCentralDecision.INFORMS,
            authority_required=authority)
        return T.Add(new_entity(
            ctx, T.Kind.CONFLICT, payload,
            derived_from=tuple(dict.fromkeys(s.source_id for s in conflicting)),
            relation=T.RelationToCentralDecision.INFORMS, confidence=T.Confidence(None),
            decision_id=decision_id, weight=0.5, status=T.Status.OPEN))
