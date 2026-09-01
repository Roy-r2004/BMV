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
from typing import Any, Sequence

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


# The closed answer set of the sourcing question, as (key, wording, channel)
# triples the run loops over. The sourcing subject fills {what}: see
# `subject_wording`.
#
# The CHANNEL is the third column and it is the same statement as the wording,
# said in types instead of in words: "the organisation's own people and
# systems" IS CapabilityClass.PEOPLE_AND_ORGANISATION and
# CapabilityClass.SOFTWARE_SYSTEM; "a supplied product or service" IS an
# EXTERNAL_RELATIONSHIP the COMMERCIAL function has to hold up; "jointly with
# an external party" IS an EXTERNAL_RELATIONSHIP under
# GOVERNANCE_AND_CONTROL. It is declared HERE, beside the wording it restates,
# because a second module that decided for itself what "buy" depends on would
# be a second opinion about the catalogue, free to drift from the sentence the
# client actually reads.
#
# This method still reads none of it: the run below loops the catalogue and
# tests no route name, so it remains blind to which route it is writing. The
# column exists for `route_dependency`, which reads what the register says
# about the channel a route runs through and can therefore tell one route from
# another without ever asking which route it is.
_ROUTES: tuple[tuple[str, str, tuple[T.CapabilityClass, ...]], ...] = (
    ("make", "Stand up {what} with the organisation's own people and systems",
     (T.CapabilityClass.PEOPLE_AND_ORGANISATION, T.CapabilityClass.SOFTWARE_SYSTEM)),
    ("buy", "Obtain {what} as a supplied product or service",
     (T.CapabilityClass.EXTERNAL_RELATIONSHIP, T.CapabilityClass.COMMERCIAL)),
    ("partner", "Deliver {what} jointly with an external party",
     (T.CapabilityClass.EXTERNAL_RELATIONSHIP, T.CapabilityClass.GOVERNANCE_AND_CONTROL)),
)

# mechanism key -> the capability classes that route runs through. Read by
# `route_dependency`; a mechanism this catalogue does not name has no declared
# channel and is left alone rather than guessed at.
CHANNELS: dict[str, tuple[T.CapabilityClass, ...]] = {key: classes for key, _w, classes in _ROUTES}


def channel_of(option: T.Entity) -> tuple[T.CapabilityClass, ...]:
    """The capability classes the route an OPTION describes runs through, as
    the sourcing catalogue declares them - or () for a route written by
    something other than this catalogue, which this engine may not second
    guess."""
    return CHANNELS.get(str(getattr(option.payload, "mechanism", "") or ""), ())


def named(cap: T.Entity) -> str:
    """One capability gap as this engagement recorded it: its own words, and
    its id. Both, and for different reasons - the words are what the route is
    ABOUT, the id is what a reader follows to the row the words came from."""
    text = display_text(cap).strip().rstrip(".").strip()
    return f"{text} ({cap.id})" if text else cap.id


def subject_wording(members: Sequence[T.Entity]) -> str:
    """What a route is a route TO: the capability gaps it would close, named
    in the words the engagement recorded them in.

    MB4, restated after the class catalogue was tried and failed. Two things
    have to be true at once and only one of them was.

    The sourcing question is asked ONCE per capability class, because an
    organisation does not decide make-or-buy a hundred and forty times - it
    decides it for the software it runs, for the data it holds, for the people
    it employs. That is what keeps the set of routes a set somebody could
    choose from instead of a catalogue nobody reads, and it stays.

    But the SUBJECT of the question is not the class. Naming it from
    `CapabilityClass.value` made every engagement's routes word-for-word every
    other engagement's: nine class values times three routes is twenty-seven
    sentences, and three hundred and eighteen rows across fifteen engagements
    carried twenty-seven sentences between them. A number about the enum. An
    option that says nothing about THIS engagement is not an option; it is the
    shape of one.

    So the subject is the gaps themselves, in the engagement's own words, each
    with the id of the row those words came from. Two engagements whose
    registers differ therefore hold different routes by construction, and a
    reader can follow any route to the rows it would close. The frame around
    the subject is still the closed catalogue and still the same words
    everywhere, which is what a frame is for.
    """
    if not members:
        return "the capability"
    parts = [named(c) for c in members]
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def sourcing_subjects(capabilities: Sequence[T.Entity]) -> list[tuple[T.CapabilityClass | None, list[T.Entity]]]:
    """The open gaps grouped by the class they belong to, in catalogue order.

    The grouping is the sourcing question's own subject: one class, one set of
    routes. Order comes from the declared catalogue and the row ids, never from
    wording, so scrambling every text field leaves this list unchanged.
    """
    order = {c: i for i, c in enumerate(T.CapabilityClass)}
    grouped: dict[T.CapabilityClass | None, list[T.Entity]] = {}
    for cap in capabilities:
        grouped.setdefault(cap.payload.capability_class, []).append(cap)
    return [(k, sorted(v, key=lambda e: e.id))
            for k, v in sorted(grouped.items(),
                               key=lambda kv: (order.get(kv[0], len(order)),
                                               kv[0].value if kv[0] is not None else ""))]


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


def declined(ids: Sequence[str]) -> str:
    """MB5: what a choice between these routes gives up, where the register
    holds no COST naming any of them.

    The answer set is closed AND exclusive: a capability is stood up by the
    organisation, bought as a supplied product, or delivered jointly - and
    taking one of those is declining the others. So the alternatives ARE what
    is forgone, and that is a fact about the routes, not a preference between
    them: nothing here says which one is better, and this method still scores
    nothing (MB2).

    Recorded because a comparison that records neither what is given up nor
    what is gained is a pairing and not a comparison, and a recommendation
    citing a pairing cannot say what it was weighed against. What it does NOT
    do is separate the routes - see the method's declared limitations.
    """
    if len(ids) < 2:
        return ""
    return "these routes are alternatives: taking any one of " + ", ".join(ids) + " declines the rest"


def pending(view) -> bool:
    """MB6: whether the sourcing question still has anything on it to do.

    Two things this method writes and nothing else: a set of routes for a
    capability class whose gaps no live OPTION already cites, and the
    comparison that weighs a class's routes against one another. Where every
    class with an open gap already has both, the run adds nothing, supersedes
    nothing and asks nothing.

    Read exactly as `run` reads it - the same grouping, the same `uncovered`,
    the same trade-off lookup by option-id set - so this cannot come to a
    different opinion about what a run would do.
    """
    if view.central_decision() is None:
        return True
    caps = [c for c in live(view, T.Kind.CAPABILITY) if c.payload.gap is not T.GapState.PRESENT]
    if not caps:
        # No gap registered yet: the sourcing question has not arrived, it has
        # not been answered. A method excluded here is one `outstanding_inputs`
        # stops listing as waiting, and an engagement that stopped listing the
        # work it is waiting on would reach SYNTHESIS still owing it.
        return True
    options = live(view, T.Kind.OPTION)
    trade_offs = [frozenset(t.payload.option_ids) for t in live(view, T.Kind.TRADE_OFF)]
    for _cap_class, members in sourcing_subjects(caps):
        if len(uncovered(members, options)) == len(members):
            return True                      # a class with no route on the table
        registered: list[str] = []
        for cap in members:
            registered.extend(options_for(cap.id, options))
        ids = frozenset(i for i in dict.fromkeys(registered) if i)
        if len(ids) >= 2 and ids not in trade_offs:
            return True                      # routes on the table, never weighed
    return False


class MakeBuyPartner:
    spec = MethodSpec(
        id="make_buy_partner", version=1,
        applicability=(
            QuestionShape(T.Interrogative.WHICH, T.Kind.CAPABILITY, comparative=True),
            # "Which way do we go?" asked of the decision itself is the same
            # question asked of the capability behind it: the routes are make,
            # buy or partner either way, and the capabilities this enumerates
            # over are read from the registry rather than from the node. Only
            # the capability-shaped node carried it before, and a tree that
            # never proposed one left the engagement with no route on the
            # table at all - and therefore nothing a recommendation could
            # select, which is advice that has chosen nothing.
            QuestionShape(T.Interrogative.WHICH, T.Kind.DECISION, comparative=True),
        ),
        answers=(T.Interrogative.WHICH,),
        required_inputs=(
            InputSpec("capabilities", T.Kind.CAPABILITY,
                      why_needed="the capability whose provider is in question"),
        ),
        optional_inputs=(
            # Routes already on the table are what makes the node comparative
            # and they raise this method's rank on such a node (7.2), but they
            # cannot be REQUIRED: this is the only method in the library that
            # writes an OPTION, so requiring two of them made the sole producer
            # of a kind wait for that kind and no engagement ever held one.
            # The run below already completes a partial set and skips a
            # capability whose routes are registered (`uncovered`).
            InputSpec("options", T.Kind.OPTION, min_count=0,
                      why_needed="the sourcing routes already on the table"),
            InputSpec("costs", T.Kind.COST, min_count=0, why_needed="what a route costs, where registered"),
            InputSpec("benefits", T.Kind.BENEFIT, min_count=0, why_needed="what a route gains, where registered"),
        ),
        execution=T.ExecutionType.DETERMINISTIC,
        output_kinds=(T.Kind.OPTION, T.Kind.TRADE_OFF),
        output_schema=None,
        evidence=EvidenceRequirement(),
        limitations=("enumerates the sourcing routes and restates what is registered about them; "
                     "it scores nothing and recommends nothing",
                     "the trade-off records that the routes are alternatives and what the register "
                     "holds about them; where nothing is registered per route it does not separate "
                     "them, and the choice stays the decision owner's",),
        validators=(),
        cost_class=1, max_model_calls=0, pending=pending)

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

        deltas: list[T.EntityDelta] = []
        findings: list[T.Finding] = []
        weight = T.SENSITIVITY[T.RelationToCentralDecision.RESOLVES]
        # One set of routes per capability CLASS with an open gap (MB4). What
        # this run offers is a function of the closed class catalogue and
        # nothing else: it cannot grow with the size of the register, so the
        # method finishes because the question is answered rather than because
        # a ceiling refused the next row.
        subjects = sourcing_subjects(caps)
        new_ids = iter(fresh_ids(view, T.Kind.OPTION, len(subjects) * len(_ROUTES)))
        per_class: dict[Any, list[str]] = {}

        for cap_class, members in subjects:
            if len(uncovered(members, options)) < len(members):
                # MB1 read at the scope the question is asked at: a class one
                # of whose gaps a live OPTION already cites has its sourcing
                # question on the table. A second set of routes would not
                # complete the set, it would repopulate it.
                continue
            what = subject_wording(members)
            cited = tuple(c.id for c in members)
            for key, wording, _channel in _ROUTES:
                oid = next(new_ids, None)
                payload = T.OptionPayload(text=wording.format(what=what), decision_id=dec.id,
                                          mechanism=key, evidence=cited)
                e = new_entity(ctx, T.Kind.OPTION, payload, derived_from=cited,
                               relation=T.RelationToCentralDecision.RESOLVES,
                               confidence=T.Confidence(None), decision_id=dec.id, weight=weight)
                deltas.append(T.Add(with_id(e, oid) if oid else e))
                per_class.setdefault(cap_class, []).append(oid or "")

        for cap_class, members in subjects:
            registered: list[str] = []
            for cap in members:
                registered.extend(options_for(cap.id, options))
            ids = tuple(i for i in dict.fromkeys(per_class.get(cap_class, []) + registered) if i)
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
                findings.append(refusal(self.spec.id, "uncited_score", members[0].id,
                                        f"{dropped} registered scoring(s) cite no evidence and were not carried forward"))
            payload = T.TradeOffPayload(
                decision_id=dec.id, option_ids=ids,
                gives_up=_rendered_side(costs, option_ids) or declined(ids),
                gains=_rendered_side(benefits, option_ids),
                scores=kept,
                # A rendering snapshot only: the gate recomputes materiality
                # from the live support graph at gate time (MF2.4), so nothing
                # here decides that the decision owner must sign it off.
                material=False)
            deltas.append(T.Add(new_entity(ctx, T.Kind.TRADE_OFF, payload,
                                           derived_from=tuple(c.id for c in members) + ids + sources,
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
