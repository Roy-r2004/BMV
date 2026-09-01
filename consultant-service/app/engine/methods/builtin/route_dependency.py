"""route_dependency - DETERMINISTIC: what each route on the table asks of THIS
organisation, and what it already holds, read off the capability register.

The hole this fills. `recommendation.SETTLING_KINDS` is (COST, BENEFIT) and
until now nothing in the library wrote a COST or a BENEFIT row: measured over
fifteen benchmark engagements, zero of each. So the register held three
sourcing routes per capability class and not one row that bore on one of them
rather than on another, `points_to` had nothing to read, and the engine could
only ever produce a constant - route one when it selected by position, and a
decline in every engagement in the world once the position was taken away.
Neither is a judgement.

What it may read, and why that is not a preference. A route is a route through
a CHANNEL: the organisation's own people and systems, a supplier, or a joint
arrangement. Which channel a route runs through is not this module's opinion -
it is the third column of the sourcing catalogue, declared beside the wording
it restates (`make_buy_partner._ROUTES`), and read here through `channel_of`.
Nothing in this file tests a route name; the catalogue is data, and a route
whose mechanism the catalogue does not name has no declared channel and is
left alone.

What the register then says about a channel is a fact about this engagement
and about no other:

  RD1 a channel is SHORT when every live CAPABILITY of its class that this
      engagement registered is missing or partial - the organisation would
      have to build the channel before it could use it. That is a COST of the
      route that runs through it, and of no other route in the comparison.
  RD2 a channel is HELD when every one of them is present or present-unused -
      the way through is already there, and something in it is standing idle.
      That is a BENEFIT of that route, and of no other.
  RD3 a channel the register holds BOTH ways, or holds nothing of at all, says
      nothing one-sided, and no row is written for it. Two engagements whose
      capability registers differ therefore receive different rows by
      construction, which is the whole of what makes the advice move.
  RD4 no magnitude is coined. A cost this method writes carries no Quantity:
      the register holds the state of a capability, not the price of closing
      it. The gap is RECORDED instead - one ask per route, naming the route,
      the channels the register cannot settle, and the MEASURES the route's own
      lineage reaches, so what comes back can be attached to the row that is
      waiting for it (design 1: absence is a typed hole, never a default).
  RD5 the gap a route exists to CLOSE is not also a cost of taking it. The
      capabilities an OPTION cites are excluded from its own channel reading,
      or a route to a people-and-organisation gap would be costed by the very
      gap it was written to close.

Idempotence: a second run writes nothing. `pending` and `run` read the same
`readings()`, so "there is nothing to do" here and "nothing was done" there are
the same statement, and a reading whose row the register already holds is
skipped by citation and never by wording.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from app.engine import types as T
from app.engine.methods.builtin.cost_benefit import measure_names, measures_behind
from app.engine.methods.builtin.make_buy_partner import channel_of
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

# The two one-sided readings of a gap state, as a partition of the enum. Stated
# as sets over GapState and never as a comparison on a string: a new gap state
# would land in neither and be read as "says nothing", which is the safe
# direction.
SHORT: frozenset[T.GapState] = frozenset((T.GapState.MISSING, T.GapState.PARTIAL))
HELD: frozenset[T.GapState] = frozenset((T.GapState.PRESENT, T.GapState.PRESENT_UNUSED))

# What one channel reading concluded. Four values, and the two that write
# nothing are kept apart from each other because they are different holes: a
# register that says both things about a channel has evidence the engine cannot
# read one way, and a register that holds nothing of that class has no evidence
# at all. They deserve different asks.
SHORT_OF = "short"
ALREADY_HELD = "held"
BOTH_WAYS = "mixed"
UNREGISTERED = "unregistered"


@dataclass(frozen=True)
class Reading:
    """One route, one channel, and what this engagement's register says about
    it. Ids only, so two runs over one registry produce the same list and no
    wording can change it."""
    option_id: str
    channel: T.CapabilityClass
    verdict: str
    capability_ids: tuple[str, ...]

    @property
    def label(self) -> str:
        return self.channel.value.replace("_", " ")


def weighed_options(view: Any) -> list[T.Entity]:
    """The live routes a registered TRADE_OFF actually weighs against another,
    in id order.

    Read from the COMPARISONS and not from the central decision, so the method
    works on whatever window it is shown. A method that asked the view for its
    central decision produced nothing at all when the selector tied it with
    another and it ran as an assignment: a specialist window does not carry the
    central decision, so `central_decision()` was None, the run returned one
    question and every route in the engagement went uncosted. What a route
    belongs to is written on the route (`OptionPayload.decision_id`), and that
    is in every window that holds the route.

    A route nobody is comparing is not a choice, and costing it would fill the
    register with rows no comparison will ever read.
    """
    weighed: set[str] = set()
    for t in live(view, T.Kind.TRADE_OFF):
        ids = [i for i in t.payload.option_ids if view.get(i) is not None]
        if len(ids) >= 2:
            weighed.update(ids)
    return [o for o in sorted(live(view, T.Kind.OPTION), key=lambda e: e.id) if o.id in weighed]


def readings(view: Any) -> list[Reading]:
    """RD1-RD3 and RD5: what the register says about every channel every
    weighed route runs through.

    Deterministic in the register alone - option id order, then the catalogue's
    own class order - so two runs agree and no wording is read anywhere.
    """
    capabilities = live(view, T.Kind.CAPABILITY)
    out: list[Reading] = []
    for option in weighed_options(view):
        own = set(option.payload.evidence) | set(option.provenance.derived_from)
        for channel in channel_of(option):
            rows = [c for c in capabilities
                    if c.payload.capability_class is channel and c.id not in own]
            ids = tuple(sorted(c.id for c in rows))
            if not rows:
                verdict = UNREGISTERED
            elif all(c.payload.gap in SHORT for c in rows):
                verdict = SHORT_OF
            elif all(c.payload.gap in HELD for c in rows):
                verdict = ALREADY_HELD
            else:
                verdict = BOTH_WAYS
            out.append(Reading(option.id, channel, verdict, ids))
    return out


def already_registered(view: Any, kind: T.Kind, reading: Reading) -> bool:
    """Whether this engagement already holds the row this reading would write.

    Read by CITATION - the route it names and the capability rows it rests on -
    never by wording, so a row somebody reworded is still the same row and a
    second run adds nothing to a set it already completed.
    """
    wanted = set(reading.capability_ids)
    for row in live(view, kind):
        if reading.option_id not in (getattr(row.payload, "for_ids", ()) or ()):
            continue
        if wanted <= set(row.provenance.derived_from):
            return True
    return False


def already_asked(view: Any, option_id: str) -> bool:
    """Whether this engagement has already asked what this route costs and
    gains - at ANY status. The two ways an ask leaves OPEN are both reasons not
    to repeat it: it is still on the table, or the client answered it, and "we
    have no record of that" is an answer.

    Read from the typed fields the ask carries - the route it is about and the
    kinds it wants - and never from its wording, so a question the client's
    turn reworded is still the same ask.
    """
    for q in view.query(T.Kind.QUESTION):
        if (option_id in (q.payload.about_ids or ())
                and T.Kind.COST in tuple(a.kind for a in q.payload.asks_for)):
            return True
    return False


def unsettled(readings_for_option: Sequence[Reading]) -> tuple[Reading, ...]:
    """The channel readings that wrote nothing: the ones the register answers
    both ways, and the ones it holds nothing of."""
    return tuple(r for r in readings_for_option if r.verdict in (BOTH_WAYS, UNREGISTERED))


def _cost_text(view: Any, reading: Reading) -> str:
    """What the route asks of the organisation, in the register's own words and
    ids. The words are the engagement's; the frame around them is the only
    thing this method adds."""
    named = "; ".join(f"{i} {display_text(view.get(i)).strip()}".strip()
                      for i in reading.capability_ids)
    return (f"Taking {reading.option_id} runs through {reading.label}, and every capability of "
            f"that kind this engagement registered is still to be closed: {named}. "
            "The route therefore carries closing them; what that costs is not registered.")


def _benefit_text(view: Any, reading: Reading) -> str:
    named = "; ".join(f"{i} {display_text(view.get(i)).strip()}".strip()
                      for i in reading.capability_ids)
    return (f"Taking {reading.option_id} runs through {reading.label}, and every capability of "
            f"that kind this engagement registered is already in place: {named}. "
            "The route uses what the organisation holds; what that is worth is not registered.")


def _ask(ctx: MethodContext, view: Any, option: T.Entity,
         written: Sequence[Reading], holes: Sequence[Reading]) -> T.QuestionPayload:
    """RD4: the gap, recorded as one answerable ask per route.

    One question and not one per channel, because a client asked four times
    about one route answers about the route. It carries, in typed fields, the
    route it is about (`about_ids`), the decision it blocks (`decision_id`) and
    the kinds that would settle it (`asks_for`); and in its wording, the
    channels the register could not settle and the measures this route's own
    lineage reaches, so the answer has somewhere to land.
    """
    measures = measures_behind(view, (option.id,))
    parts: list[str] = []
    if written:
        parts.append("this engagement's register says the "
                     + ", ".join(r.label for r in written)
                     + " way through is one-sided for this route, and says nothing about what "
                       "going down it would cost or save")
    for hole in holes:
        if hole.verdict == UNREGISTERED:
            parts.append(f"this engagement has registered no {hole.label} capability at all, so "
                         "nothing says whether that way through is open")
        else:
            parts.append(f"the {hole.label} capabilities this engagement registered are recorded "
                         "both ways, so they do not say whether that way through is open")
    on_measure = (" Recorded against " + measure_names(view, measures) + "."
                  if measures else
                  " This engagement has registered no measure this route is counted on; name one.")
    return T.QuestionPayload(
        text=(f"What does {option.id} cost, and what does it gain? " + "; ".join(parts) + "."
              + on_measure),
        asks_for=(T.AsksFor(T.Kind.COST), T.AsksFor(T.Kind.BENEFIT)),
        issue_ids=ctx.issue_ids,
        why=("a route whose cost and gain are not registered cannot be weighed against the routes "
             "it is on the table with"),
        effort=T.EffortClass.LOOKUP, strategy=T.FillStrategy.ASK_CLIENT,
        about_ids=(option.id,) + tuple(measures), decision_id=option.payload.decision_id)


def _v_every_row_names_one_route(view: Any, result: MethodResult) -> list[T.Finding]:
    """RD1/RD2 re-checked on the finished result: a COST or BENEFIT this method
    writes names exactly ONE route in `for_ids`.

    A row naming every route separates none of them, and a row naming none
    bears on nothing. Either would be a row that looks like evidence in the
    register and cannot tell one route from another - which is the defect this
    whole method exists to end, reintroduced one layer down.
    """
    out: list[T.Finding] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is None or e.kind not in (T.Kind.COST, T.Kind.BENEFIT):
            continue
        for_ids = tuple(e.payload.for_ids or ())
        if len(for_ids) != 1:
            out.append(T.Finding(
                law="M.route_dependency.bears_on_no_single_route", where=e.id or e.kind.value,
                issue=f"a {e.kind.value} names {len(for_ids)} route(s) in for_ids",
                fix="write one row per route, or write none"))
    return out


def _v_no_coined_magnitude(view: Any, result: MethodResult) -> list[T.Finding]:
    """RD4 re-checked: nothing this method writes carries a Quantity. The
    register holds the STATE of a capability, never the price of closing it, so
    a figure here could only have been invented."""
    return [T.Finding(
        law="M.route_dependency.coined_magnitude", where=e.id or e.kind.value,
        issue=f"a {e.kind.value} carries a quantity this engagement never registered",
        fix="record the gap as an ask; a magnitude the register does not hold is not the engine's to state")
        for e in (getattr(d, "entity", None) for d in result.deltas)
        if e is not None and e.kind in (T.Kind.COST, T.Kind.BENEFIT)
        and getattr(e.payload, "quantity", None) is not None]


def pending(view: Any) -> bool:
    """Whether this method still has anything to write or ask.

    Reads exactly what `run` reads - the same `readings`, the same
    `already_registered`, the same `already_asked` - so the selector and the
    method cannot come to different opinions about whether a run would leave
    the registry as it found it.
    """
    by_option: dict[str, list[Reading]] = {}
    for reading in readings(view):
        by_option.setdefault(reading.option_id, []).append(reading)
    for option_id, group in by_option.items():
        for reading in group:
            if reading.verdict == SHORT_OF and not already_registered(view, T.Kind.COST, reading):
                return True
            if reading.verdict == ALREADY_HELD and not already_registered(view, T.Kind.BENEFIT, reading):
                return True
        if (any(r.verdict in (SHORT_OF, ALREADY_HELD, BOTH_WAYS, UNREGISTERED) for r in group)
                and not already_asked(view, option_id)):
            return True
    return False


@register
class RouteDependencyMethod:
    spec = MethodSpec(
        id="route_dependency", version=1,
        applicability=(
            # The same node the routes were written on: the sourcing question,
            # asked of the decision or of the capability behind it. This method
            # answers the half of it the catalogue cannot - not what the routes
            # ARE, but what this organisation would be taking on down each one.
            QuestionShape(T.Interrogative.WHICH, T.Kind.DECISION, comparative=True),
            QuestionShape(T.Interrogative.WHICH, T.Kind.CAPABILITY, comparative=True),
        ),
        answers=(T.Interrogative.WHICH,),
        required_inputs=(
            InputSpec("options", T.Kind.OPTION, min_count=2, effort=T.EffortClass.OFFHAND,
                      why_needed="a cost or a gain that bears on one route rather than another "
                                 "needs at least two routes to bear between"),
            InputSpec("capabilities", T.Kind.CAPABILITY, min_count=1, effort=T.EffortClass.OFFHAND,
                      why_needed="the capability register is what says whether a way through is "
                                 "open to this organisation"),
        ),
        optional_inputs=(
            InputSpec("trade_offs", T.Kind.TRADE_OFF, min_count=0,
                      why_needed="which routes are actually weighed against one another"),
            InputSpec("measures", T.Kind.MEASURE, min_count=0,
                      why_needed="what this engagement counts, so an ask has somewhere to land"),
            InputSpec("costs", T.Kind.COST, min_count=0,
                      why_needed="what is already registered against a route, so nothing is written twice"),
            InputSpec("benefits", T.Kind.BENEFIT, min_count=0,
                      why_needed="what is already registered for a route, so nothing is written twice"),
        ),
        execution=T.ExecutionType.DETERMINISTIC,
        output_kinds=(T.Kind.COST, T.Kind.BENEFIT, T.Kind.QUESTION),
        output_schema=None,
        evidence=EvidenceRequirement(),
        limitations=(
            "reads whether a way through is open to this organisation, never what going down it "
            "would cost: no row it writes carries a figure, and the magnitude is recorded as an ask",
            "says nothing about a channel its register answers both ways, or holds nothing of; "
            "two routes the register is silent about stay unseparated and the choice stays the "
            "decision owner's",
            "a route whose mechanism the sourcing catalogue does not name has no declared channel "
            "and is left alone",
        ),
        validators=(require_citations("route_dependency"), _v_every_row_names_one_route,
                    _v_no_coined_magnitude),
        cost_class=1, max_model_calls=0, pending=pending)

    def run(self, ctx: MethodContext) -> MethodResult:
        view = ctx.registry
        weight = T.SENSITIVITY[T.RelationToCentralDecision.EVIDENCES]
        options = {o.id: o for o in weighed_options(view)}
        by_option: dict[str, list[Reading]] = {}
        for reading in readings(view):
            by_option.setdefault(reading.option_id, []).append(reading)

        deltas: list[T.EntityDelta] = []
        questions: list[T.QuestionPayload] = []
        for option_id, group in by_option.items():
            option = options[option_id]
            decision_id = option.payload.decision_id
            written: list[Reading] = []
            for reading in group:
                if reading.verdict == SHORT_OF:
                    kind, payload = T.Kind.COST, T.CostPayload(
                        text=_cost_text(view, reading), basis="unknown",
                        for_ids=(reading.option_id,))
                elif reading.verdict == ALREADY_HELD:
                    kind, payload = T.Kind.BENEFIT, T.BenefitPayload(
                        text=_benefit_text(view, reading), basis="unknown",
                        for_ids=(reading.option_id,))
                else:
                    continue
                written.append(reading)
                if already_registered(view, kind, reading):
                    continue
                deltas.append(T.Add(new_entity(
                    ctx, kind, payload,
                    derived_from=(reading.option_id,) + reading.capability_ids,
                    relation=T.RelationToCentralDecision.EVIDENCES,
                    confidence=T.Confidence(None), decision_id=decision_id, weight=weight)))
            holes = unsettled(group)
            if (written or holes) and not already_asked(view, option_id):
                questions.append(_ask(ctx, view, option, written, holes))
        return MethodResult(deltas=tuple(deltas), questions=tuple(questions))


__all__ = ["ALREADY_HELD", "BOTH_WAYS", "HELD", "Reading", "RouteDependencyMethod", "SHORT",
           "SHORT_OF", "UNREGISTERED", "already_asked", "already_registered",            "pending", "readings", "unsettled",
           "weighed_options"]
