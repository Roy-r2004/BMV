"""make_buy_partner - who provides a capability (design 7.3 row
make_buy_partner): WHICH on CAPABILITY, comparative.

DETERMINISTIC, so M1 holds and no model is called. What makes the method
deterministic is that the answer set is closed: a capability is stood up by
the organisation itself, bought as a supplied product or service, or
delivered jointly with an external party. The method's whole job is to make
sure every open capability gap has all of those routes on the table before
anyone chooses between them. It never chooses.

Laws this module enforces, each in the docstring of the thing enforcing it:

  MB1 a route is written only for a live CAPABILITY whose gap is open and
      which no live OPTION already cites: the method completes an option set,
      it never repopulates one, so a second run adds nothing (uncovered()).
  MB2 the method coins no score. A sourcing comparison needs evidence per
      option per criterion; where the registry holds a scoring it is copied
      with the evidence it already carried, and a scoring that cites nothing
      is dropped with a visible refusal rather than carried forward
      (scores_cite / _v_scores_cite). Nothing is averaged, blended or
      silently preferred (design 1.2).
  MB3 what an option gives up and gains is rendered from the registered COST
      and BENEFIT rows that name it, never phrased here. An empty string is a
      real answer: nothing is registered about that route yet.

The routes are a loop over declared wordings, not a branch: no comparison in
this module tests a route name, so the method is blind to which route it is
writing and cannot prefer one (the whitelist AST law of design 18).
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
    display_text,
    fresh_ids,
    live,
    refusal,
    require_citations,
    with_id,
)


# The closed answer set of the sourcing question, as (key, wording) pairs the
# run loops over. A capability's own words fill {what}, so the option is named
# after the gap it closes rather than after anything phrased about the client.
_ROUTES: tuple[tuple[str, str], ...] = (
    ("make", "Stand up {what} with the organisation's own people and systems"),
    ("buy", "Obtain {what} as a supplied product or service"),
    ("partner", "Deliver {what} jointly with an external party"),
)


def uncovered(capabilities: Sequence[T.Entity], options: Sequence[T.Entity]) -> list[T.Entity]:
    """MB1: the capability gaps no live OPTION already cites. Coverage is read
    from ids (an option's `evidence` and its provenance), never from wording -
    scrambling every text field must leave this set unchanged, and a second
    run of the method must add nothing to a set it already completed."""
    covered: set[str] = set()
    for o in options:
        covered.update(o.payload.evidence)
        covered.update(o.provenance.derived_from)
    return [c for c in capabilities if c.id not in covered]


def options_for(capability_id: str, options: Sequence[T.Entity]) -> list[str]:
    return [o.id for o in options
            if capability_id in o.payload.evidence or capability_id in o.provenance.derived_from]


def scores_cite(view, option_ids: frozenset[str]) -> tuple[tuple[T.Score, ...], tuple[str, ...]]:
    """MB2: the scorings the registry already holds for these options, kept
    with the evidence they came with, plus the ids of the TRADE_OFFs they were
    copied from. A registered score citing nothing is not copied: a number
    with no evidence behind it is exactly what a comparison must not inherit."""
    kept: list[T.Score] = []
    sources: list[str] = []
    for t in live(view, T.Kind.TRADE_OFF):
        for s in t.payload.scores:
            if s.option_id in option_ids and s.evidence:
                kept.append(s)
                sources.append(t.id)
    return tuple(kept), tuple(dict.fromkeys(sources))


def _rendered_side(rows: Sequence[T.Entity], option_ids: frozenset[str]) -> str:
    """MB3: one side of the trade-off, rendered from the rows that name these
    options. Nothing is phrased here; when no row names them the side is empty,
    which reads as "not registered", never as "nothing to give up"."""
    texts = [display_text(r) for r in rows if set(r.payload.for_ids) & option_ids]
    return "; ".join(t for t in texts if t)


class MakeBuyPartner:
    spec = MethodSpec(
        id="make_buy_partner", version=1,
        applicability=(QuestionShape(T.Interrogative.WHICH, T.Kind.CAPABILITY, comparative=True),),
        answers=(T.Interrogative.WHICH,),
        required_inputs=(
            InputSpec("capabilities", T.Kind.CAPABILITY,
                      why_needed="the capability whose provider is in question"),
            # Two options are what makes the node comparative; the method still
            # runs on fewer and completes the set, but a node with the routes
            # already on the table is the one it is ranked highest for (7.2).
            InputSpec("options", T.Kind.OPTION, min_count=2,
                      why_needed="the sourcing routes already on the table"),
        ),
        optional_inputs=(
            InputSpec("costs", T.Kind.COST, min_count=0, why_needed="what a route costs, where registered"),
            InputSpec("benefits", T.Kind.BENEFIT, min_count=0, why_needed="what a route gains, where registered"),
        ),
        execution=T.ExecutionType.DETERMINISTIC,
        output_kinds=(T.Kind.OPTION, T.Kind.TRADE_OFF),
        output_schema=None,
        evidence=EvidenceRequirement(),
        limitations=("enumerates the sourcing routes and restates what is registered about them; "
                     "it scores nothing and recommends nothing",),
        validators=(),
        cost_class=1, max_model_calls=0)

    def run(self, ctx: MethodContext) -> MethodResult:
        view = ctx.registry
        dec = view.central_decision()
        if dec is None:
            # An option is an option *for* a decision. Without one the routes
            # would belong to nothing, so the hole is asked, never defaulted.
            q = T.QuestionPayload(
                text="Which decision do these sourcing routes serve?",
                asks_for=(T.AsksFor(T.Kind.DECISION),), issue_ids=ctx.issue_ids,
                why="a sourcing option belongs to the decision it is a route for",
                effort=T.EffortClass.OFFHAND, strategy=T.FillStrategy.ASK_CLIENT)
            return MethodResult(questions=(q,))

        caps = [c for c in live(view, T.Kind.CAPABILITY) if c.payload.gap is not T.GapState.PRESENT]
        options = live(view, T.Kind.OPTION)
        costs = live(view, T.Kind.COST)
        benefits = live(view, T.Kind.BENEFIT)
        open_caps = uncovered(caps, options)

        deltas: list[T.EntityDelta] = []
        findings: list[T.Finding] = []
        weight = T.SENSITIVITY[T.RelationToCentralDecision.RESOLVES]
        new_ids = iter(fresh_ids(view, T.Kind.OPTION, len(open_caps) * len(_ROUTES)))
        per_cap: dict[str, list[str]] = {}

        for cap in open_caps:
            what = display_text(cap)
            for key, wording in _ROUTES:
                oid = next(new_ids, None)
                payload = T.OptionPayload(text=wording.format(what=what), decision_id=dec.id,
                                          mechanism=key, evidence=(cap.id,))
                e = new_entity(ctx, T.Kind.OPTION, payload, derived_from=(cap.id,),
                               relation=T.RelationToCentralDecision.RESOLVES,
                               confidence=T.Confidence(None), decision_id=dec.id, weight=weight)
                deltas.append(T.Add(with_id(e, oid) if oid else e))
                per_cap.setdefault(cap.id, []).append(oid or "")

        for cap in caps:
            ids = tuple(dict.fromkeys(per_cap.get(cap.id, []) + options_for(cap.id, options)))
            ids = tuple(i for i in ids if i)
            if len(ids) < 2:
                # One route is not a trade-off. Writing one anyway would put a
                # comparison on the page that the engagement never had.
                continue
            option_ids = frozenset(ids)
            if any(frozenset(t.payload.option_ids) == option_ids for t in live(view, T.Kind.TRADE_OFF)):
                continue
            kept, sources = scores_cite(view, option_ids)
            dropped = sum(1 for t in live(view, T.Kind.TRADE_OFF) for s in t.payload.scores
                          if s.option_id in option_ids and not s.evidence)
            if dropped:
                findings.append(refusal(self.spec.id, "uncited_score", cap.id,
                                        f"{dropped} registered scoring(s) cite no evidence and were not carried forward"))
            payload = T.TradeOffPayload(
                decision_id=dec.id, option_ids=ids,
                gives_up=_rendered_side(costs, option_ids),
                gains=_rendered_side(benefits, option_ids),
                scores=kept,
                # A rendering snapshot only: the gate recomputes materiality
                # from the live support graph at gate time (MF2.4), so nothing
                # here decides that the decision owner must sign it off.
                material=False)
            deltas.append(T.Add(new_entity(ctx, T.Kind.TRADE_OFF, payload,
                                           derived_from=(cap.id,) + ids + sources,
                                           relation=T.RelationToCentralDecision.RESOLVES,
                                           confidence=T.Confidence(None), decision_id=dec.id, weight=weight)))
        return MethodResult(deltas=tuple(deltas), findings=tuple(findings))


def _v_scores_cite(view, result: MethodResult) -> list[T.Finding]:
    """MB2 re-checked on the finished result: a Score in a written TRADE_OFF
    carries the evidence ids it rests on, and a score is a Decimal - a float's
    printed form is not its value, and a comparison that cannot be reproduced
    exactly is a preference, not a finding."""
    out: list[T.Finding] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is None or e.kind is not T.Kind.TRADE_OFF:
            continue
        for s in e.payload.scores:
            if not s.evidence:
                out.append(T.Finding(law="M.make_buy_partner.uncited_score", where=e.id or "trade_off",
                                     issue=f"a score for {s.option_id} cites no evidence",
                                     fix="cite the entities the score rests on, or drop the score"))
            if not isinstance(s.score, Decimal):
                out.append(T.Finding(law="M.make_buy_partner.inexact_score", where=e.id or "trade_off",
                                     issue=f"the score for {s.option_id} is not an exact Decimal",
                                     fix="score with Decimal so the comparison reproduces exactly"))
    return out


def _v_routes_cover_a_capability(view, result: MethodResult) -> list[T.Finding]:
    """MB1 re-checked: every OPTION this method wrote names the capability gap
    it is a route for. A route attached to nothing would be a sourcing answer
    to a question the engagement never asked."""
    out: list[T.Finding] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is None or e.kind is not T.Kind.OPTION:
            continue
        cited = [view.get(i) for i in e.payload.evidence]
        if not any(c is not None and c.kind is T.Kind.CAPABILITY for c in cited):
            out.append(T.Finding(law="M.make_buy_partner.route_without_capability", where=e.id or "option",
                                 issue="a sourcing route names no capability gap",
                                 fix="cite the CAPABILITY the route would close"))
    return out


MakeBuyPartner.spec = replace(MakeBuyPartner.spec,
                              validators=(require_citations("make_buy_partner"),
                                          _v_scores_cite,
                                          _v_routes_cover_a_capability))
register(MakeBuyPartner)
