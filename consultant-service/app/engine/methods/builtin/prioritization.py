"""prioritization - the order the work is worth doing in (design 7.3 row
prioritization): WHICH on INITIATIVE or ACTION, comparative.

DETERMINISTIC, so M1 holds and no model is called: a ranking is arithmetic
over registered scores and registered weights, and asking a model to rank is
asking it to prefer.

Laws this module enforces, each in the docstring of the thing enforcing it:

  PR1 only the client's criterion weights rank. A criterion whose weight was
      set by anyone else lists the criterion - it says the dimension matters
      - but it does not decide the order, because the relative importance of
      two objectives is a client preference and nothing else in the authority
      table owns it (client_weights, run()).
  PR2 nothing is ranked on a score the registry does not hold. A subject with
      no registered scoring is left unsequenced and asked about, never given
      a middling default: an invented rank is a recommendation dressed as
      arithmetic (weighted_totals, run()).
  PR3 every score written cites the evidence it was computed from, and the
      arithmetic is exact Decimal - two runs over one registry produce one
      order, ties broken by id (_v_scores_cite).
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Sequence

from app.engine import types as T
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
    live,
    require_citations,
    with_id,
)


def client_weights(criteria: Sequence[T.Entity]) -> dict[str, Decimal]:
    """PR1: the criteria that rank, and by how much.

    `weight_set_by` is the authority that set the number. Only CLIENT weights
    are read here: the authority table gives the client every objective,
    success criterion and constraint, so how much one matters against another
    is the client's to say. A consultant-set weight still lists its criterion
    in the trade-off; it just does not move anything.
    """
    out: dict[str, Decimal] = {}
    for c in criteria:
        p = c.payload
        if p.weight is not None and p.weight_set_by is T.Authority.CLIENT:
            out[c.id] = Decimal(str(p.weight))
    return out


def registered_scores(trade_offs: Sequence[T.Entity]) -> dict[tuple[str, str], tuple[T.Score, str]]:
    """Every (subject, criterion) scoring the registry holds, with the
    TRADE_OFF it came from. A scoring that cites no evidence is not read: a
    ranking may not inherit a number nothing stands behind."""
    out: dict[tuple[str, str], tuple[T.Score, str]] = {}
    for t in trade_offs:
        for s in t.payload.scores:
            if s.evidence:
                out[(s.option_id, s.criterion_id)] = (s, t.id)
    return out


def weighted_totals(subject_ids: Sequence[str], weights: dict[str, Decimal],
                    scores: dict[tuple[str, str], tuple[T.Score, str]]) -> dict[str, Decimal]:
    """PR2: the weighted total per subject, over the criteria the client
    weighted and the scores the registry holds. A subject with no such score
    is absent from the result, not zero: zero is a position, absence is a
    hole. Exact Decimal, so the order reproduces byte for byte."""
    out: dict[str, Decimal] = {}
    for sid in subject_ids:
        total = Decimal("0")
        seen = False
        for cid, w in weights.items():
            hit = scores.get((sid, cid))
            if hit is None:
                continue
            total += w * hit[0].score
            seen = True
        if seen:
            out[sid] = total
    return out


class Prioritization:
    spec = MethodSpec(
        id="prioritization", version=1,
        applicability=(
            QuestionShape(T.Interrogative.WHICH, T.Kind.ACTION, comparative=True),
            QuestionShape(T.Interrogative.WHICH, T.Kind.INITIATIVE, comparative=True),
        ),
        answers=(T.Interrogative.WHICH,),
        required_inputs=(
            InputSpec("actions", T.Kind.ACTION, min_count=2,
                      why_needed="a priority order needs more than one thing to order"),
            InputSpec("criteria", T.Kind.EVALUATION_CRITERION,
                      why_needed="an order is an order against something; the criteria are that something"),
        ),
        optional_inputs=(
            InputSpec("initiatives", T.Kind.INITIATIVE, min_count=0, why_needed="the groupings actions sit in"),
            InputSpec("trade_offs", T.Kind.TRADE_OFF, min_count=0, why_needed="the scorings already registered"),
        ),
        execution=T.ExecutionType.DETERMINISTIC,
        output_kinds=(T.Kind.ACTION, T.Kind.TRADE_OFF),
        output_schema=None,
        evidence=EvidenceRequirement(),
        limitations=("ranks only on client-set weights over registered scores; with neither it lists "
                     "the criteria and asks for the weights",),
        validators=(),
        cost_class=1, max_model_calls=0)

    def run(self, ctx: MethodContext) -> MethodResult:
        view = ctx.registry
        dec = view.central_decision()
        decision_id = dec.id if dec is not None else None
        subjects = sorted(live(view, T.Kind.ACTION), key=lambda a: a.id)
        criteria = live(view, T.Kind.EVALUATION_CRITERION)
        trade_offs = live(view, T.Kind.TRADE_OFF)
        if len(subjects) < 2 or not criteria or decision_id is None:
            return MethodResult()

        weights = client_weights(criteria)
        scores = registered_scores(trade_offs)
        deltas: list[T.EntityDelta] = []
        questions: list[T.QuestionPayload] = []

        if not weights:
            # PR1: the criteria are on the table and nothing ranks. The gap is
            # a question to the one authority that can close it, and the order
            # stays as it was rather than being invented from the list.
            questions.append(T.QuestionPayload(
                text="How would you weigh these criteria against each other? "
                     "Nothing is ranked until the weights are yours.",
                asks_for=(T.AsksFor(T.Kind.EVALUATION_CRITERION, {"weight_set_by": T.Authority.CLIENT}),),
                issue_ids=ctx.issue_ids,
                why="only the client's weights rank; a consultant's weight lists a criterion",
                effort=T.EffortClass.OFFHAND, strategy=T.FillStrategy.ASK_CLIENT, material=True))

        totals = weighted_totals([s.id for s in subjects], weights, scores)
        ranked = sorted(totals, key=lambda sid: (-totals[sid], sid))
        by_id = {s.id: s for s in subjects}
        for position, sid in enumerate(ranked, start=1):
            old = by_id[sid]
            if old.payload.sequence == position:
                continue                        # already where the arithmetic puts it
            new_payload = replace(old.payload, sequence=position)
            e = new_entity(ctx, T.Kind.ACTION, new_payload,
                           derived_from=tuple(dict.fromkeys(old.provenance.derived_from + tuple(sorted(weights)))),
                           relation=old.relation, confidence=old.confidence,
                           decision_id=old.relevance.decision_id or decision_id,
                           weight=old.relevance.weight, status=old.status)
            deltas.append(T.Supersede(sid, with_id(e, sid)))

        unranked = [s.id for s in subjects if s.id not in totals]
        if unranked and weights:
            # PR2: no default rank for what nothing scored.
            questions.append(T.QuestionPayload(
                text=f"Nothing is registered that scores {', '.join(unranked)} against the criteria; "
                     "they stay unsequenced until something does.",
                asks_for=(T.AsksFor(T.Kind.TRADE_OFF),), issue_ids=ctx.issue_ids,
                why="a rank with no scoring behind it would be a preference presented as arithmetic",
                effort=T.EffortClass.LOOKUP, strategy=T.FillStrategy.ASK_CLIENT))

        if ranked:
            kept = tuple(scores[(sid, cid)][0] for sid in ranked for cid in sorted(weights)
                         if (sid, cid) in scores)
            sources = tuple(dict.fromkeys(scores[(sid, cid)][1] for sid in ranked for cid in sorted(weights)
                                          if (sid, cid) in scores))
            payload = T.TradeOffPayload(
                decision_id=decision_id, option_ids=tuple(ranked),
                gives_up="", gains="", scores=kept,
                # A snapshot only; the gate recomputes materiality from the
                # live support graph (MF2.4).
                material=False)
            deltas.append(T.Add(new_entity(
                ctx, T.Kind.TRADE_OFF, payload,
                derived_from=tuple(ranked) + tuple(sorted(weights)) + sources,
                relation=T.RelationToCentralDecision.RESOLVES, confidence=T.Confidence(None),
                decision_id=decision_id, weight=T.SENSITIVITY[T.RelationToCentralDecision.RESOLVES])))

        return MethodResult(deltas=tuple(deltas), questions=tuple(questions))


def _v_scores_cite(view, result: MethodResult) -> list[T.Finding]:
    """PR3 re-checked on the finished result: every score written cites its
    evidence and is an exact Decimal. A ranking nobody can reproduce is a
    preference."""
    out: list[T.Finding] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is None or e.kind is not T.Kind.TRADE_OFF:
            continue
        for s in e.payload.scores:
            if not s.evidence:
                out.append(T.Finding(law="M.prioritization.uncited_score", where=e.id or "trade_off",
                                     issue=f"the score for {s.option_id} cites no evidence",
                                     fix="rank only on scores the registry holds with their evidence"))
            if not isinstance(s.score, Decimal):
                out.append(T.Finding(law="M.prioritization.inexact_score", where=e.id or "trade_off",
                                     issue=f"the score for {s.option_id} is not an exact Decimal",
                                     fix="score with Decimal so the order reproduces exactly"))
    return out


def _v_sequence_rests_on_client_weights(view, result: MethodResult) -> list[T.Finding]:
    """PR1 re-checked: a sequence this result writes cites at least one
    criterion the CLIENT weighted. Removing this check lets a consultant's own
    weighting decide the client's order, which is the authority table read
    backwards."""
    out: list[T.Finding] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is None or e.kind is not T.Kind.ACTION or e.payload.sequence is None:
            continue
        cited = [view.get(i) for i in e.provenance.derived_from]
        if not any(c is not None and c.kind is T.Kind.EVALUATION_CRITERION
                   and c.payload.weight_set_by is T.Authority.CLIENT for c in cited):
            out.append(T.Finding(
                law="M.prioritization.sequence_without_client_weight", where=e.id or "action",
                issue="a priority order was written without citing a criterion the client weighted",
                fix="ask the client for the weights, or leave the steps unsequenced"))
    return out


Prioritization.spec = replace(Prioritization.spec, validators=(require_citations("prioritization"),
                                                               _v_scores_cite,
                                                               _v_sequence_rests_on_client_weights))
register(Prioritization)
