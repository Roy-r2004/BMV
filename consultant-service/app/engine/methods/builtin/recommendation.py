"""recommendation - DETERMINISTIC: propose, for the decision on the table, ONE
course of action - the route the analysis evidenced, the routes it was taken
over, the criteria it was judged against, the comparison it was chosen in, and
the confirmed evidence it rests on.

RECOMMENDATION was the one kind the whole build read and nothing wrote. The
registry checks it (I3), the release gate checks it (L2/L4), synthesis
refreshes its conditions and approves it, and the Executive Decision Brief has
a required section for it - all over rows no producer existed to create. This
is that producer.

What it recommends is not invented here. The subject of advice is the ROUTE:
a recommendation selects one of the OPTIONs the engagement registered for the
decision and says to take it, and it is written only when that route's own
lineage reaches evidence a support law admits: a CONFIRMED FACT or an APPROVED
ASSUMPTION (`registry._is_support`). Where the lineage reaches none, no
recommendation is written and the missing evidence is asked for - because a
recommendation nothing supports is what L2 exists to catch, and writing one so
that the gate can catch it would be a defect the engine manufactured for
itself.

Advising per ACTION was the defect this replaced, and it is worth writing down
because every existing law passed while it stood. The statement was the
action's own words; those words had themselves been copied off a FACT; the row
cited that same fact as its support - so I3, L2 and
`unsupported_recommendations()` were all satisfied by the very row the advice
was a copy of, and the citation was a circle one row wide. `single_option`
looked for a route among the action's ANCESTORS, but routes and steps are
siblings under a CAPABILITY, so it found none and every recommendation named
no option at all. Extracted evidence, relabelled as advice, is what a support
law cannot see: only a law relating an output's CONTENT to its inputs' can.

WHAT CHOOSES, AND WHAT MAY NOT. The selection used to be the comparison's own
ORDER: the first route in `option_ids` whose lineage reached a support. That
order is registration order, which `make_buy_partner` fixes as make, buy,
partner - so every engagement in the world advised `make`, and reordering that
one tuple would have flipped every engagement's advice together. An ordering
presented as a conclusion has exactly the shape of a conclusion: it names a
route, cites a criterion, cites a comparison, rests on evidence a support law
admits and repeats none of it. Every structural law stayed green while nothing
was being chosen.

What chooses now is the register (R8). A route is advised only where what this
engagement recorded tells it from its rivals AND everything that tells them
apart points the same way. Where nothing does, or where what does disagrees,
the engagement does not choose: it records that it cannot and asks for the
evidence that would settle it (R7). A consultant who cannot choose says so.

The direction of the evidence is read from the KIND, never from the words. A
BENEFIT registered for a route is a reason FOR it; a COST, a RISK or a
CONSTRAINT registered for a route is a reason AGAINST it. That is what those
kinds ARE, declared once in types.py, and not an opinion about any case. An
EVALUATION_CRITERION and a Score are deliberately NOT read as pointing
anywhere: a criterion declares no direction, so the engine cannot know whether
more of it is better (`option_evaluation` says the same where it refuses to
add scores up), and a scored comparison whose direction the engine cannot read
is one it hands back with the scores visible. Separating the routes and
pointing at one of them are two different acts, and only the second decides.

Laws this module enforces, and the failure each prevents:

  R1  every recommendation carries non-empty `supports`, each of which is a
      support the registry admits, and every support is also cited. A
      recommendation traceable only through prose is the failure the whole
      engine exists to make impossible (spec section 7).
  R2  a recommendation is born PROPOSED. The consultant proposes; only the
      DECISION_OWNER or the CLIENT approves (APPROVAL_OWNER, I1). A producer
      that could write its own advice APPROVED would be approving on the
      client's behalf.
  R3  every recommendation names the OPTION it selects, and that option is a
      live route registered for the same decision. Advice that names no route
      has selected nothing - and because it cites the evidence it was built
      from, every support law is satisfied by a row that settles no choice.
      Where no route can be advised the advice is withheld and the hole is
      asked about; it is never published with the choice left blank.
  R4  ONE recommendation per decision. Three routes to one capability gap set
      beside each other as three recommendations are not advice at all: the
      reader is handed the decision back, dressed as a conclusion, and the two
      halves contradict each other on the same page. A second run over an
      unchanged registry restates nothing either, so a brief cannot list the
      same advice twice because analysis ran twice. `L15` refuses the
      contradictory pair at the release door as well.
  R5  where the engagement registered EVALUATION_CRITERIA for the decision,
      the advice cites them. They are the client's own declarations restated
      by `decision_criteria`, so citing them is not the consultant importing a
      priority - it is the row saying what standard it was held to.
  R6  the advice repeats nothing. Its statement may not contain, nor be
      contained by, the claim of a live FACT or MEASURE or the text of a live
      EVIDENCE_SOURCE, compared exactly after whitespace and case are
      normalised (`repeats_evidence`). The engine has always policed invention
      (`coined_figures` fails text that departs from its source) and never
      policed copying, so the safest possible output - repeating the evidence -
      scored highest under every check that existed. Equality alone is defeated
      by a frame ("Take the route: <the fact>"), which is why the comparison is
      containment; nothing here is a ratio, because how close is too close is
      an opinion and this is a law.
  R7  a decision the analysis cannot settle says so, and says what would
      settle it. Where no route is registered, or none was ever weighed
      against another, or none traces to evidence a support law admits, or
      nothing the engagement recorded separates the routes, the run writes a
      typed DECISION_REQUIRED against the decision - unsettled, and whose it
      is to settle - and an OPEN QUESTION per route carrying, in typed fields,
      the route it is about (`about_ids`), the decision it blocks
      (`decision_id`) and the KINDS of evidence that would separate that route
      from its rivals (`asks_for`). An engagement that concluded nothing and
      recorded nothing has not declined to advise; it has been silent, and
      silence reads as a caution it never exercised. A blocker that names the
      decision and not the missing evidence is that same silence one row on.
  R8  the choice follows the evidence and moves with it. A route is advised
      only where the engagement registered something that tells it from every
      rival in the comparison - a BENEFIT, a COST, a RISK or a CONSTRAINT
      bearing on one route and not on another - and only where every such row
      points the same way. Two registers alike in every row but the evidence
      bearing on their routes, each the mirror of the other, therefore receive
      the two answers and never one of them twice.
  R9  advice is revisable, in place. Evidence that arrives after a
      recommendation and moves which route the register favours SUPERSEDES
      that recommendation - one row, the same id, selecting the route the
      evidence now favours, citing every row that changed it. Never a second
      recommendation beside the first: two live recommendations on one
      decision hand the reader the decision back. With nothing new the run
      writes nothing at all, so this is "move when the evidence moves" and not
      "rewrite every round".

Why DETERMINISTIC rather than model-assisted: a specialist's whole result is
rejected on one S4 violation, and S4 forbids a specialist to write a
RECOMMENDATION against any live decision except a SUBORDINATE one its node was
built to settle (`specialists/runner.py`, `assignment.forbidden_decisions`).
The central decision is forbidden on every assignment, so a model-assisted
recommender would have every delta refused on every engagement. This method
runs directly as `Actor.METHOD`. The only words it adds are the frame that
makes a route a course of action - "rather than", "to settle", "closing" - and
a frame is not a claim: everything inside it is a registered row's own wording
or an id, and R6 keeps even that from being the register's evidence.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Iterable, Mapping, Sequence

from app.engine import types as T
from app.engine.methods.builtin.capability_gap import added_of, wording
from app.engine.methods.builtin.cost_benefit import live, measure_names, measures_behind
from app.engine.methods.builtin.org_design import with_id
from app.engine.methods.contract import (
    METHODS,
    EvidenceRequirement,
    InputSpec,
    MethodContext,
    MethodResult,
    MethodSpec,
    QuestionShape,
    input_state,
    new_entity,
    register,
    shape_matches,
)

# What a recommendation may rest on, as the registry admits it (I3, L2). The
# pair is stated once here and re-read by the validator, so this module and the
# registry cannot drift apart on what counts as evidence.
SUPPORT_STATUS: dict[T.Kind, T.Status] = {
    T.Kind.FACT: T.Status.CONFIRMED,
    T.Kind.ASSUMPTION: T.Status.APPROVED,
}


def is_support(e: T.Entity | None) -> bool:
    """R1: a CONFIRMED FACT or an APPROVED ASSUMPTION, and nothing else. A
    PROPOSED fact is a statement somebody made, not evidence somebody stands
    behind, which is why the registry refuses it under a recommendation."""
    if e is None:
        return False
    return SUPPORT_STATUS.get(e.kind) is e.status


def lineage_closure(view: Any, roots: Iterable[str]) -> list[str]:
    """Every id the given rows reach through `derived_from` and calculation
    `inputs`, in first-seen order.

    The same walk `EngagementRegistry.support_closure` makes downwards from a
    recommendation, made here upwards from the action before one exists. Order
    is the walk's, not a set's, so two runs over one registry agree.
    """
    seen: list[str] = []
    known: set[str] = set()
    frontier = list(roots)
    while frontier:
        entity_id = frontier.pop(0)
        if entity_id in known:
            continue
        known.add(entity_id)
        seen.append(entity_id)
        row = view.get(entity_id)
        if row is None:
            continue
        frontier.extend(row.provenance.derived_from)
        frontier.extend(getattr(row.payload, "inputs", ()) or ())
    return seen


def supports_in(view: Any, closure: Sequence[str]) -> tuple[str, ...]:
    """The ids in a closure that a support law admits, in closure order."""
    return tuple(i for i in closure if is_support(view.get(i)))


def single_option(view: Any, closure: Sequence[str], decision_id: str) -> str | None:
    """R3: the one registered OPTION for this decision that the action's
    lineage reaches, or None.

    None is the answer for zero and for two alike, and deliberately so: with
    no route in the lineage there is nothing to name, and with more than one
    the choice between them is the decision owner's. Nothing here breaks a tie.
    """
    found = [i for i in closure
             if (row := view.get(i)) is not None and row.kind is T.Kind.OPTION
             and row.status not in T.TERMINAL_STATUSES and row.payload.decision_id == decision_id]
    return found[0] if len(found) == 1 else None


def already_recommended(view: Any, subject_id: str) -> bool:
    """R4, read by citation rather than by wording: a live recommendation that
    cites this subject already carries it."""
    return any(subject_id in r.provenance.derived_from for r in live(view, T.Kind.RECOMMENDATION))


def criteria_for(view: Any, decision_id: str) -> tuple[str, ...]:
    """R5: the criteria this decision is judged against, in id order.

    A recommendation that names none of them says nothing about WHY this route
    beat the others - it has been emitted rather than chosen. They are the
    client's own declarations restated by `decision_criteria`, so citing them
    is not the consultant importing a priority; it is the advice pointing at
    the standard it was held to. Where the engagement registered none, there is
    no standard to point at and the lineage says so by their absence.
    """
    return tuple(sorted(c.id for c in live(view, T.Kind.EVALUATION_CRITERION)
                        if c.payload.decision_id == decision_id))


def steps_for(view: Any, option_id: str) -> tuple[str, ...]:
    """The registered ACTIONs whose lineage reaches this route: how the route
    would be taken, where the engagement worked it out. Advice is still advice
    without them, so they are cited when present and never invented."""
    return tuple(a.id for a in sorted(live(view, T.Kind.ACTION), key=lambda e: e.id)
                 if option_id in lineage_closure(view, (a.id,)))


def normalised(text: str) -> str:
    """Whitespace collapsed, case folded. Exact comparison only: a ratio would
    make "how close is too close" an opinion, and R6 is not an opinion."""
    return " ".join(str(text or "").split()).casefold()


def registered_claims(view: Any) -> tuple[str, ...]:
    """Every claim the register already holds, normalised: a live FACT's
    statement, a live MEASURE's definition, and the text of every live
    EVIDENCE_SOURCE.

    A measure's NAME is a column label, not something anybody asserts, and is
    deliberately not here - the distinction is by FIELD and not by length.

    The evidence sources are here because a claim can be registered AFTER the
    advice is written. A sentence the client said is in the turn from the
    moment it is said, and is extracted into a FACT whenever some later method
    gets to it; advice that borrowed that sentence would read as authored on
    the round it was written and as a copy one round later. Refusing to borrow
    anything already inside a source the engagement holds makes the check
    stable over the whole run rather than true only at the instant of writing.
    """
    out: list[str] = []
    for f in live(view, T.Kind.FACT):
        text = normalised(f.payload.statement)
        if text:
            out.append(text)
    for m in live(view, T.Kind.MEASURE):
        text = normalised(getattr(m.payload, "definition", "") or "")
        if text:
            out.append(text)
    for e in live(view, T.Kind.EVIDENCE_SOURCE):
        text = normalised(getattr(e.payload, "text", "") or "")
        if text:
            out.append(text)
    return tuple(out)


def repeats_evidence(text: str, claims: Sequence[str]) -> bool:
    """R6: whether a phrase repeats a claim the register already holds, either
    way round.

    Containment both ways, because a frame defeats equality: "Take the route:
    <the fact>" is not EQUAL to the fact and is not authorship either, and a
    statement so terse a claim swallows it is the same defect mirrored.
    """
    candidate = normalised(text)
    if not candidate:
        return True
    return any(claim in candidate or candidate in claim for claim in claims)


def borrowed(view: Any, texts: Iterable[str]) -> list[str]:
    """The wordings a statement may draw on: the engagement's own, minus any
    that would only be repeating the evidence (R6)."""
    claims = registered_claims(view)
    out: list[str] = []
    for text in texts:
        wordings = str(text or "").strip()
        if wordings and not repeats_evidence(wordings, claims):
            out.append(wordings)
    return out


def widest_comparison(view: Any, decision_id: str, options: Mapping[str, T.Entity]) -> list[T.Entity]:
    """The comparisons this decision registered, widest first.

    A comparison that weighs five routes against each other says more than one
    that weighs two, and the order has to be total or two runs over one
    registry would advise differently: the id breaks the tie.
    """
    def _rivals(t: T.Entity) -> int:
        return len({i for i in t.payload.option_ids if i in options})

    weighed = [t for t in live(view, T.Kind.TRADE_OFF)
               if t.payload.decision_id == decision_id and _rivals(t) >= 2]
    return sorted(weighed, key=lambda t: (-_rivals(t), t.id))


# What the register may hold about a route, and which way each kind points.
# Direction comes from the KIND and is declared once: a BENEFIT is what taking
# a route gains, a COST is what it gives up, a RISK is what may go wrong on it
# and a CONSTRAINT is a limit that binds it (types.py). Reading a direction off
# any of their WORDS would be this module judging prose, which is the one thing
# a universal engine may not do.
FOR_KINDS: tuple[T.Kind, ...] = (T.Kind.BENEFIT,)
AGAINST_KINDS: tuple[T.Kind, ...] = (T.Kind.COST, T.Kind.RISK, T.Kind.CONSTRAINT)

# Kinds that tell two routes apart without saying which is better. They are
# named so that "the engagement registered nothing per route" can be told from
# "the engagement registered something the engine cannot read a direction in" -
# two different states that deserve two different answers. Scores belong here
# too, and are compared by VALUE (see `undirected`).
UNDIRECTED_KINDS: tuple[T.Kind, ...] = (T.Kind.EVALUATION_CRITERION,)

# What the engine asks for when nothing tells the routes apart. Both kinds
# carry a declared direction, which is what makes an answer to them able to
# settle a choice; asking for a criterion would fill the register with rows
# that separate the routes and still point nowhere.
SETTLING_KINDS: tuple[T.Kind, ...] = (T.Kind.COST, T.Kind.BENEFIT)


def bears_on(entity: T.Entity, option_id: str) -> bool:
    """Whether a registered row is ABOUT one route. Two typed ways a row says
    so and neither is prose: the `for_ids` field the costed kinds carry, and
    the citation the row was written under."""
    if option_id in (getattr(entity.payload, "for_ids", ()) or ()):
        return True
    return option_id in entity.provenance.derived_from


def directed(view: Any, option_id: str) -> frozenset[str]:
    """The ids of every row with a declared direction that bears on this
    route."""
    return frozenset(e.id for kind in FOR_KINDS + AGAINST_KINDS
                     for e in live(view, kind) if bears_on(e, option_id))


def undirected(view: Any, option_id: str) -> frozenset[str]:
    """What the register holds about this route that separates it from another
    without saying which way. A Score is included BY VALUE and not by id: two
    routes scored the same on one criterion carry the same token here and so
    separate nothing, which is the truth about them."""
    out: set[str] = set()
    for kind in UNDIRECTED_KINDS:
        for e in live(view, kind):
            if bears_on(e, option_id):
                out.add(e.id)
    for t in live(view, T.Kind.TRADE_OFF):
        for s in t.payload.scores:
            if s.option_id == option_id:
                out.add(f"{t.id}/{s.criterion_id}={s.score}")
    return frozenset(out)


def separates(view: Any, option_ids: Sequence[str]) -> bool:
    """Whether ANYTHING this engagement registered tells these routes apart,
    with a direction or without one.

    A row naming every route in the comparison separates none of them; a row
    naming one separates it from the rest. This asks what the engagement HOLDS;
    `points_to` asks what it has said.
    """
    if len({directed(view, i) for i in option_ids}) > 1:
        return True
    return len({undirected(view, i) for i in option_ids}) > 1


def points_to(view: Any, option_ids: Sequence[str]) -> tuple[str | None, tuple[str, ...]]:
    """R8: the ONE route every reason the register holds points to, and those
    reasons - or (None, ()) where nothing points, or where what points
    disagrees.

    A row naming some of the routes and not others puts the ones it names ahead
    of the ones it does not (a BENEFIT) or behind them (a COST, a RISK, a
    CONSTRAINT). A row naming ALL of them, or none, is passed over: a cost
    every route carries is not a reason to take any of them.

    Unanimity, never a count. "Two benefits beat one" would be this module
    inventing a scale nobody registered, and "the higher score wins" would be
    reading a direction into a criterion that declares none. One row pointing
    the other way is therefore enough to stop the choice - and stopping is not
    a failure, it is the answer the caller records and asks about.
    """
    ahead: dict[str, set[str]] = {}
    behind: set[str] = set()
    everything = set(option_ids)
    for kind in FOR_KINDS + AGAINST_KINDS:
        favours = kind in FOR_KINDS
        for e in live(view, kind):
            named = {i for i in option_ids if bears_on(e, i)}
            if not named or named == everything:
                continue
            better = named if favours else (everything - named)
            for i in better:
                ahead.setdefault(i, set()).add(e.id)
            behind |= (everything - better)
    candidates = sorted(i for i in ahead if i not in behind)
    if len(candidates) != 1:
        return None, ()
    return candidates[0], tuple(sorted(ahead[candidates[0]]))


# The four states an engagement can be in when it cannot advise, read off the
# register and never guessed. They are kept apart because they are four
# different holes with four different fixes, and because collapsing them is how
# a decline came to say "no registered route traces to a confirmed fact" about
# an engagement whose routes were perfectly well evidenced and merely disagreed.
NO_ROUTE = "no_route"
NO_COMPARISON = "no_comparison"
NOTHING_SEPARATES = "nothing_separates"
POINTS_TWO_WAYS = "points_two_ways"
UNEVIDENCED = "unevidenced"


def bearing_rows(view: Any, option_ids: Sequence[str]) -> tuple[str, ...]:
    """Every directed row this engagement holds that bears on some of these
    routes and not on all of them - the rows that are doing the disagreeing,
    in id order, so a reader can go and look at them."""
    everything = set(option_ids)
    out: set[str] = set()
    for kind in FOR_KINDS + AGAINST_KINDS:
        for e in live(view, kind):
            named = {i for i in option_ids if bears_on(e, i)}
            if named and named != everything:
                out.add(e.id)
    return tuple(sorted(out))


def impasse(view: Any, options: Mapping[str, T.Entity],
            comparisons: Sequence[T.Entity]) -> tuple[str, T.Entity | None, tuple[str, ...]]:
    """WHY this engagement could not settle the choice: the state, the
    comparison it is about, and the ids that state rests on.

    Called only where `selected_route` returned nothing, and it reads the same
    two functions in the same order, so the reason recorded is the reason the
    selection actually stopped on. Widest comparison first, id breaking the
    tie, so two runs over one registry give one answer.
    """
    if not options:
        return NO_ROUTE, None, ()
    if not comparisons:
        return NO_COMPARISON, None, ()
    for comparison in comparisons:
        ids = [i for i in comparison.payload.option_ids if i in options]
        if len(ids) < 2 or not separates(view, ids):
            continue
        choice, _reasons = points_to(view, ids)
        if choice is None:
            return POINTS_TWO_WAYS, comparison, bearing_rows(view, ids)
        return UNEVIDENCED, comparison, (choice,)
    return NOTHING_SEPARATES, comparisons[0], ()


def settling_producers(view: Any) -> tuple[str, ...]:
    """R11: the methods this library registers that write a kind able to settle
    a choice, and that this engagement has not run yet, and that it could still
    run - required inputs already satisfied, something still to conclude, and a
    live issue node of a shape they declare.

    Why advice consults the method registry at all. "Nothing this engagement
    registered separates these routes" is a claim about the engagement, and it
    is FALSE while a producer of exactly that evidence is sitting in the round's
    own list waiting for a slot. Recording it anyway is not caution; it is a
    conclusion drawn one turn before the evidence, and because a node is only
    ever offered to a method once, it is also the LAST word the engine gets:
    measured over fifteen engagements, `recommendation` ran immediately before
    `route_dependency` in fourteen of them and declined in every one, while the
    register it declined over went on to point at a route in nine.

    Nothing here is an orchestrator change and nothing schedules anything. It
    is one method asking the register a question about itself, and the three
    clauses are what BOUND the wait: a producer whose inputs are missing is not
    coming, a producer with nothing left to conclude is not coming, and a
    producer with no node to run on is not coming. Where none is coming this
    returns () and the decline is recorded on the spot.
    """
    ran = {a.payload.method_id for a in view.query(T.Kind.ANALYSIS)
           if a.status not in T.TERMINAL_STATUSES}
    nodes = [QuestionShape.of(i) for i in live(view, T.Kind.ISSUE)]
    out: list[str] = []
    for kind in SETTLING_KINDS:
        for method in METHODS.producers_of(kind):
            spec = method.spec
            if spec.id == SPEC.id or spec.id in ran or spec.id in out:
                continue
            if input_state(spec, view).missing:
                continue
            if spec.pending is not None and not spec.pending(view):
                continue
            if not any(shape_matches(d, node) for d in spec.applicability for node in nodes):
                continue
            out.append(spec.id)
    return tuple(sorted(out))


def contesting_rows(view: Any, standing: T.Entity, comparison: T.Entity | None,
                    options: Mapping[str, T.Entity]) -> tuple[str, ...]:
    """R9's other half: the directed rows the register now holds about the
    routes this advice was chosen among, that the advice itself does not cite.

    The silent deadlock this ends. An engagement that had advised once was
    handled by a single early return: same route or nothing pointed, write
    nothing. "Nothing pointed" covers the case where evidence arrived and
    CONTRADICTED the standing advice - the rows now point two ways, `points_to`
    yields no route, and the row that was written before any of them arrived
    goes on standing as though the engagement had never seen them. Nothing in
    the registry says the advice is now contested; the reader sees a
    recommendation and no sign that it is out of date.

    Read by citation, so a row the advice already rested on is not a new
    contest, and an unchanged register yields () - this is "move when the
    evidence moves", never "rewrite every round".
    """
    if comparison is None:
        return ()
    ids = [i for i in comparison.payload.option_ids if i in options]
    cited = set(standing.provenance.derived_from)
    return tuple(i for i in bearing_rows(view, ids) if i not in cited)


def selected_route(view: Any, comparisons: Sequence[T.Entity],
                   options: Mapping[str, T.Entity]
                   ) -> tuple[T.Entity | None, T.Entity | None, tuple[str, ...], tuple[str, ...]]:
    """R3/R8: the ONE route this engagement advises, the comparison it was
    chosen in, the evidence it rests on and the rows that chose it.

    Two conditions, both about the register and neither about an order. The
    routes must be told apart by rows that all point the same way
    (`points_to`), and the route so pointed at must have a lineage that reaches
    evidence a support law admits - advice resting on nothing is what L2 exists
    to refuse, and writing it so the gate can catch it would be a defect the
    engine manufactured for itself.

    Where no comparison yields such a route the answer is (None, None, (), ())
    and the caller records why rather than advising. Comparisons are taken
    widest first with the id breaking the tie, so two runs over one registry
    give one answer.
    """
    for comparison in comparisons:
        ids = [i for i in comparison.payload.option_ids if i in options]
        if len(ids) < 2:
            continue
        choice, reasons = points_to(view, ids)
        if choice is None:
            continue
        supports = supports_in(view, lineage_closure(view, (choice,)))
        if supports:
            return options[choice], comparison, supports, reasons
    return None, None, (), ()


def _uncapitalised(text: str) -> str:
    trimmed = text.rstrip(".").strip()
    return (trimmed[0].lower() + trimmed[1:]) if trimmed else trimmed


def route_phrase(view: Any, option: T.Entity, claims: Sequence[str]) -> str:
    """How the advice NAMES a route: in the route's own words where those words
    are the engagement's, and by reference where they are the register's.

    R6 read at the one place it can be enforced by construction. A route's
    wording now names the capability gaps it would close, in the words the
    engagement recorded them in (`make_buy_partner`), which is what makes a
    route about this engagement rather than about a class of capability. But
    where the producer of a CAPABILITY restated the FACT it cites - the
    structural oracle does, and says so - those words are a claim the register
    already holds, and advice that quoted them would contain its own evidence
    verbatim. So the route is named by its id and by the closed catalogue word
    for its mechanism instead: a pointer and an enum member, neither of which
    asserts anything.

    Quoting where it is safe and citing where it is not is the same rule the
    criteria already live under, applied to the route.
    """
    text = str(wording(option) or "").strip().rstrip(".")
    if text and not repeats_evidence(text, claims):
        return text
    mechanism = str(getattr(option.payload, "mechanism", "") or "").replace("_", " ").strip()
    named = f"the {mechanism} route {option.id}" if mechanism else f"route {option.id}"
    return named + " (its own wording restates evidence the register holds, so it is cited here)"


def advice_statement(view: Any, option: T.Entity, rivals: Sequence[T.Entity], settles: str,
                     closes: Sequence[str], reasons: Sequence[str] = ()) -> str:
    """What the advice SAYS: the route to take, the routes it was taken over,
    the registered rows that chose it, what taking it would settle, and the
    gaps it closes.

    Every word of substance comes from a registered row and none of it repeats
    a claim the register holds: the route is quoted only where its own wording
    is not the register's (`route_phrase`), `settles` has been through
    `borrowed` before it arrives (R6), and the reasons and the gaps are named
    by id, which is a pointer and not an assertion. The frame - "rather than",
    "on the evidence", "to settle", "closing" - is the only thing added, and a
    frame is not a claim.

    The REASONS are new and they are the difference between advice and an
    emission. They are the ids of the rows that put this route ahead of the
    ones beside it (R8), so a reader can ask the row what chose this and get
    an answer that is not "it was listed first".

    The criteria the choice was held to are CITED, not quoted. Quoting them put
    the client's own sentences back into the advice, and those sentences are
    registered as FACTs too, so the advice came out repeating its evidence one
    hop further along than before - which is the same defect, not a fix for it.
    """
    claims = registered_claims(view)
    head = route_phrase(view, option, claims)
    if rivals:
        head += ", rather than " + " or ".join(
            _uncapitalised(route_phrase(view, r, claims)) for r in rivals)
    if reasons:
        head += (", on the evidence this engagement registered against those routes: "
                 + ", ".join(reasons))
    if settles:
        head += ", to settle " + _uncapitalised(settles)
    if closes:
        head += " (the gaps this analysis registered there: " + ", ".join(closes) + ")"
    return head + "."


def gaps_closed(view: Any, option: T.Entity) -> tuple[str, ...]:
    """The capability gaps this route would close, each named by its id and the
    state the register puts it in.

    Ids and enum members only: a pointer and a catalogue value are not
    assertions, so nothing here can repeat a claim, and two engagements whose
    registers differ name different gaps in different states - which is the
    whole of what makes one engagement's advice distinguishable from another's
    when the route wording itself comes from a closed catalogue.
    """
    out: list[str] = []
    for i in option.payload.evidence:
        row = view.get(i)
        if row is not None and row.kind is T.Kind.CAPABILITY:
            out.append(f"{row.id} {row.payload.gap.value}")
    return tuple(out)


def _v_every_recommendation_traces(view: Any, result: MethodResult) -> list[T.Finding]:
    """R1 re-checked on the finished result: non-empty supports, every one of
    them a support the registry admits, and every one of them cited."""
    out: list[T.Finding] = []
    for e in added_of(result, T.Kind.RECOMMENDATION):
        cited = set(e.provenance.derived_from)
        if not e.payload.supports:
            out.append(T.Finding(
                law="M.recommendation.unsupported", where=e.id or e.kind.value,
                issue="a recommendation is written with no supports",
                fix="write the recommendation only where the action's lineage reaches confirmed evidence",
                entity_ids=(e.id,) if e.id else ()))
            continue
        for sid in e.payload.supports:
            if not is_support(view.get(sid)):
                out.append(T.Finding(
                    law="M.recommendation.unsupported", where=e.id or e.kind.value,
                    issue=f"support {sid} is not a confirmed fact or an approved assumption",
                    fix="cite only evidence a support law admits, or write no recommendation",
                    entity_ids=(e.id,) if e.id else ()))
            elif sid not in cited:
                out.append(T.Finding(
                    law="M.recommendation.uncited_support", where=e.id or e.kind.value,
                    issue=f"support {sid} is not among the ids the recommendation cites",
                    fix="cite every support, so lineage and supports say the same thing",
                    entity_ids=(e.id,) if e.id else ()))
    return out


def _v_never_born_approved(view: Any, result: MethodResult) -> list[T.Finding]:
    """R2 re-checked. The registry refuses it too (I1 through APPROVAL_OWNER);
    this says so where the advice is written, so the refusal is not the first
    time anybody learns the producer tried."""
    return [T.Finding(
        law="M.recommendation.self_approved", where=e.id or e.kind.value,
        issue=f"a recommendation is written {e.status.value}, not proposed",
        fix="the consultant proposes; the decision owner or the client approves",
        entity_ids=(e.id,) if e.id else ())
        for e in added_of(result, T.Kind.RECOMMENDATION) if e.status is not T.Status.PROPOSED]


def _v_option_is_registered(view: Any, result: MethodResult) -> list[T.Finding]:
    """R3 re-checked: a named option is a live OPTION for the same decision.
    An option_id naming something else would put a route on the brief that the
    engagement never registered."""
    out: list[T.Finding] = []
    for e in added_of(result, T.Kind.RECOMMENDATION):
        option_id = e.payload.option_id
        if option_id is None:
            continue
        row = view.get(option_id)
        if (row is None or row.kind is not T.Kind.OPTION or row.status in T.TERMINAL_STATUSES
                or row.payload.decision_id != e.payload.decision_id):
            out.append(T.Finding(
                law="M.recommendation.unregistered_option", where=e.id or e.kind.value,
                issue=f"{option_id} is not a live option for {e.payload.decision_id}",
                fix="name an option the registry holds for this decision, or name none",
                entity_ids=(e.id,) if e.id else ()))
    return out


def _v_advice_selects_a_route(view: Any, result: MethodResult) -> list[T.Finding]:
    """R3: every recommendation names the OPTION it selects.

    Advice that names no route has selected nothing - and because it cites the
    evidence it was built from, every support law is satisfied by a row that
    settles no choice. Where the routes are not narrowed to one the honest act
    is to withhold the advice, not to publish it with the choice left blank.
    """
    return [T.Finding(
        law="M.recommendation.selects_nothing", where=e.id or e.kind.value,
        issue="a recommendation names no option, so it selects nothing",
        fix="advise on a registered route, or withhold the advice and ask",
        entity_ids=(e.id,) if e.id else ())
        for e in added_of(result, T.Kind.RECOMMENDATION) if e.payload.option_id is None]


def _v_advice_names_its_criteria(view: Any, result: MethodResult) -> list[T.Finding]:
    """R5: where the engagement registered criteria for the decision, the
    advice cites them. Nothing else on the row says what the route was judged
    against, and advice that names no standard has been emitted rather than
    chosen. Where none are registered there is no standard to name, and their
    absence from the lineage is the truthful record of that."""
    out: list[T.Finding] = []
    for e in added_of(result, T.Kind.RECOMMENDATION):
        registered = set(criteria_for(view, e.payload.decision_id))
        if registered and not (registered & set(e.provenance.derived_from)):
            out.append(T.Finding(
                law="M.recommendation.uncited_criteria", where=e.id or e.kind.value,
                issue=f"advice on {e.payload.decision_id} cites none of its {len(registered)} criteria",
                fix="cite the criteria the decision is judged against, so the row says what chose it",
                entity_ids=(e.id,) if e.id else ()))
    return out


SPEC = MethodSpec(
    id="recommendation",
    version=1,
    applicability=(
        QuestionShape(T.Interrogative.WHICH, T.Kind.DECISION),
        QuestionShape(T.Interrogative.WHICH, T.Kind.DECISION, comparative=True),
        QuestionShape(T.Interrogative.HOW, T.Kind.DECISION),
    ),
    answers=(T.Interrogative.WHICH, T.Interrogative.HOW),
    required_inputs=(
        InputSpec("decision", T.Kind.DECISION, {"role": T.DecisionRole.CENTRAL}, min_count=1,
                  effort=T.EffortClass.OFFHAND,
                  why_needed="advice is advice about a decision; without one there is nothing to advise on"),
        InputSpec("options", T.Kind.OPTION, min_count=1, effort=T.EffortClass.OFFHAND,
                  why_needed="advice selects one of the routes the engagement registered; with no route "
                             "on the table there is nothing to select and nothing to advise"),
        InputSpec("evidence", T.Kind.FACT, min_status=T.Status.CONFIRMED, min_count=1,
                  effort=T.EffortClass.OFFHAND,
                  why_needed="L2 refuses a recommendation that traces to nothing, so evidence is a precondition "
                             "for advising at all, not a check afterwards"),
    ),
    optional_inputs=(
        InputSpec("actions", T.Kind.ACTION, min_count=0,
                  why_needed="how a route would be taken, where the analysis worked it out"),
        InputSpec("assumptions", T.Kind.ASSUMPTION, min_status=T.Status.APPROVED, min_count=0,
                  why_needed="an approved assumption is evidence a recommendation may rest on"),
        InputSpec("trade_offs", T.Kind.TRADE_OFF, min_count=0,
                  why_needed="what the engagement already recorded about the choice"),
        InputSpec("criteria", T.Kind.EVALUATION_CRITERION, min_count=0,
                  why_needed="what the client declared the choice is judged on"),
        InputSpec("recommendations", T.Kind.RECOMMENDATION, min_count=0,
                  why_needed="what is already advised, so nothing is advised twice"),
        # The four directed kinds `points_to` actually reads (FOR_KINDS +
        # AGAINST_KINDS). They are DECLARED here because a method's declared
        # inputs are what the selector fingerprints: a method that reads a kind
        # it never declared is shown a register that changed and is told it has
        # already seen this window (`state.shown_before`), so the very rows that
        # would move the advice are the rows that stop it being asked again.
        # Advice that cannot be revisited is advice that cannot be revised.
        InputSpec("costs", T.Kind.COST, min_count=0,
                  why_needed="what a route gives up, where the engagement registered it against one route"),
        InputSpec("benefits", T.Kind.BENEFIT, min_count=0,
                  why_needed="what a route gains, where the engagement registered it against one route"),
        InputSpec("risks", T.Kind.RISK, min_count=0,
                  why_needed="what may go wrong on one route rather than another"),
        InputSpec("constraints", T.Kind.CONSTRAINT, min_count=0,
                  why_needed="a limit the engagement registered that binds one route rather than another"),
    ),
    execution=T.ExecutionType.DETERMINISTIC,
    output_kinds=(T.Kind.RECOMMENDATION, T.Kind.DECISION_REQUIRED, T.Kind.QUESTION),
    output_schema=None,
    evidence=EvidenceRequirement(),
    limitations=(
        "selects a route the engagement registered and names the confirmed evidence it rests on; "
        "the only words it adds are the frame that makes a route a course of action",
        "advises every route whose own lineage reaches confirmed evidence, including two routes to "
        "the same capability gap: nothing the engagement holds separates one sourcing route from "
        "another, so the choice between them stays the decision owner's and the trade-off is "
        "recorded beside the advice",
    ),
    validators=(_v_every_recommendation_traces, _v_never_born_approved, _v_option_is_registered,
                _v_advice_selects_a_route, _v_advice_names_its_criteria),
    cost_class=1,
    max_model_calls=0,
)


def pending(view: Any) -> bool:
    """R10: whether there is advice to write, to revise, or a reason to record.

    An engagement that has not been advised has something to do here as soon as
    the evidence that would settle the choice has stopped arriving: the route
    the register points to, or the typed record that nothing points (R7). An
    engagement that HAS been advised has something to do where the register now
    points somewhere else (R9), or where it now holds rows about those routes
    that the advice does not cite and that leave it pointing nowhere - which is
    the contest the early return used to swallow.

    R11 is the clause that waits, and it lives HERE and not in the run. A
    decline recorded while a registered producer of COST or BENEFIT still has a
    node to run on is a claim about the engagement that is not yet true, and
    because a method is offered a node only once it is also the last word the
    engine gets on that node: measured over fifteen engagements,
    `recommendation` ran immediately before `route_dependency` in fourteen of
    them and declined in every one, over a register that went on to point at a
    route in nine.

    Waiting is a thing only this function may say, because it is the only
    question the loop asks BEFORE it spends the node: answering "not yet" here
    writes no ANALYSIS row, leaves the node open, and the next round asks again
    with the evidence in hand. The RUN never waits - a method that has been run
    and says nothing has been silent, which is the whole of what R7 refuses -
    so a caller that runs this method directly gets the decline and the asks,
    exactly as it did before. It never waits where a route can already be
    advised either: evidence that would settle a choice already settled does
    not stop the engine settling it.

    Reads the same functions the run reads (`widest_comparison`,
    `selected_route`, `impasse`, `contesting_rows`), so "there is nothing to
    do" here and "nothing was done" there are the same statement.
    """
    decision = view.central_decision()
    if decision is None:
        return True
    options = {o.id: o for o in live(view, T.Kind.OPTION)
               if o.payload.decision_id == decision.id}
    comparisons = widest_comparison(view, decision.id, options)
    option, comparison, _supports, _reasons = selected_route(view, comparisons, options)
    standing = [r for r in sorted(live(view, T.Kind.RECOMMENDATION), key=lambda e: e.id)
                if r.payload.decision_id == decision.id]
    if not standing:
        if option is not None and comparison is not None:
            return True
        return not settling_producers(view)
    held = standing[0]
    if option is not None and comparison is not None:
        return option.id != held.payload.option_id
    widest = comparisons[0] if comparisons else None
    contests = contesting_rows(view, held, widest, options)
    return bool(contests) and not already_contested(view, held, contests)


SPEC = dataclasses.replace(SPEC, pending=pending)


def _no_decision_question(ctx: MethodContext) -> T.QuestionPayload:
    return T.QuestionPayload(
        text="Which decision should this advice be about?",
        asks_for=(T.AsksFor(T.Kind.DECISION),), issue_ids=ctx.issue_ids,
        why="a recommendation is advice on a decision; without one it advises nothing",
        effort=T.EffortClass.OFFHAND, strategy=T.FillStrategy.ASK_CLIENT)


def _unevidenced_question(ctx: MethodContext, decision_id: str,
                          subject_ids: Sequence[str]) -> T.QuestionPayload:
    """The typed hole R1 leaves, as a question the client can answer. The
    routes are named so the ask is answerable: the client is asked to confirm
    the evidence behind particular routes, not for an opinion on whether the
    advice is right.

    It stands beside the DECISION_REQUIRED rather than instead of it. They are
    two different records: the blocker says the decision is unsettled and whose
    it is to settle, and belongs against the decision where a reader looks for
    the advice; the question says what would settle it, and belongs in the next
    turn of the conversation. `about_ids` and `decision_id` are what carry that
    subject onto the registered row - without them the ask would be born citing
    its issue node and attached to no decision, which is a hole that cannot say
    where it is.
    """
    named = ", ".join(subject_ids)
    return T.QuestionPayload(
        text=f"Which of your records confirms what these routes rest on: {named}?",
        asks_for=(T.AsksFor(T.Kind.FACT),), issue_ids=ctx.issue_ids,
        why="a recommendation that traces to no confirmed evidence is not advice the engagement may give",
        effort=T.EffortClass.LOOKUP, strategy=T.FillStrategy.ASK_CLIENT,
        about_ids=tuple(subject_ids), decision_id=decision_id)


def already_asked_about(view: Any, option_id: str, decision_id: str) -> bool:
    """Whether this engagement has already asked what would separate this
    route - at ANY status, answered or not.

    Read from the typed fields the ask carries and never from its wording, so a
    question the model reworded is still the same ask. At any status, because
    the two ways an ask leaves OPEN are both reasons not to repeat it: it is
    still on the table and the client has not answered yet, or the client
    answered it - including with "we have no record of that", which is an
    answer and never re-asked (ingest.RECORD_UNKNOWN).
    """
    for q in view.query(T.Kind.QUESTION):
        payload = q.payload
        if option_id in (payload.about_ids or ()) and q.relevance.decision_id == decision_id:
            return True
    return False


def _standing_hole(ctx: MethodContext, view: Any, decision: T.Entity,
                   comparison: T.Entity, options: Mapping[str, T.Entity],
                   reason: str = NOTHING_SEPARATES, details: Sequence[str] = ()
                   ) -> list[T.QuestionPayload]:
    """R7: the record that OUTLIVES the conversation - what would settle this
    decision, standing until something does.

    The per-route asks above are the client's to answer, and an answered
    question is a closed question: "we have no record of that here" is an
    answer, and a hole recorded only as a client ask therefore disappears the
    moment the client cannot fill it. The decision is no less unsettled for
    that. What has changed is only WHO can settle it - and a hole whose owner
    changed is still a hole, so it is recorded as one.

    `SPAWN_SPECIALIST`, because that is what the strategy means: the client is
    never asked for what analysis produces (design 6.5). A cost or a benefit
    registered against ONE sourcing route and not another is exactly that -
    a costing, a quote, a comparison somebody has to do - and the library has
    no producer for it today, which is why `make_buy_partner` renders an empty
    `gives_up` on every engagement. Writing the hole down is what makes that
    visible instead of silent.

    One per decision, not one per route: this is the standing statement of the
    choice, and it names the routes it is about in `about_ids` so a reader can
    see which comparison it stands over.
    """
    ids = tuple(i for i in comparison.payload.option_ids if i in options)
    if any(q.payload.strategy is T.FillStrategy.SPAWN_SPECIALIST
           and q.relevance.decision_id == decision.id
           and set(q.payload.about_ids or ()) & set(ids)
           for q in view.query(T.Kind.QUESTION, status=T.Status.OPEN)):
        return []
    # The routes are named in their own words, not only by id, and what would
    # settle the choice is named in this engagement's own measures. A hole
    # recorded in ids alone is the same sentence in every engagement in the
    # world, which is the defect this whole change set is about: it would read
    # as a script even though what it stands over is different every time.
    #
    # Both impasses this stands over leave the same hole and are not the same
    # sentence. Nothing separating the routes and the register pointing two
    # ways at once are different states of the engagement - the first holds no
    # evidence per route, the second holds evidence that disagrees - and a hole
    # that described them alike would send the client looking for what they
    # already sent.
    routes = named_routes(view, options, ids)
    if reason == POINTS_TWO_WAYS:
        standing = (f"{decision.id} cannot be settled while what this engagement registered about "
                    f"these routes points more than one way: {', '.join(details)} bear on {routes} "
                    "and do not agree.")
    else:
        standing = (f"{decision.id} cannot be settled while nothing tells these routes apart: "
                    f"{routes}.")
    return [T.QuestionPayload(
        text=f"{standing} What would settle it: {settles_this_choice(view, ids)}.",
        asks_for=tuple(T.AsksFor(kind) for kind in SETTLING_KINDS),
        issue_ids=ctx.issue_ids,
        why=("the routes are weighed against one another and nothing the engagement holds bears "
             "on one of them rather than another"),
        effort=T.EffortClass.THIRD_PARTY, strategy=T.FillStrategy.SPAWN_SPECIALIST,
        about_ids=ids + (comparison.id,), decision_id=decision.id)]


def _separating_questions(ctx: MethodContext, view: Any, decision: T.Entity,
                          comparison: T.Entity, options: Mapping[str, T.Entity]
                          ) -> list[T.QuestionPayload]:
    """R7: one ask per route, for the evidence that would tell that route from
    the others it is weighed against.

    PER ROUTE, and that is the whole point. One question about all three routes
    at once can only be answered about all three at once, and an answer that
    bears on every route separates none of them - the engagement would have
    asked, been answered, and still hold nothing that could choose. The client
    is therefore asked what THIS route costs and what it gains, and the answer
    is recorded against the route it was asked about (`make_buy_partner`).

    The ask names the kinds it wants (`asks_for`), the route it is about
    (`about_ids`) and the decision it blocks (`decision_id`), so the record is
    a hole with a location rather than a sentence about a decision.
    """
    out: list[T.QuestionPayload] = []
    for option_id in comparison.payload.option_ids:
        option = options.get(option_id)
        if option is None or already_asked_about(view, option_id, decision.id):
            continue
        rivals = [i for i in comparison.payload.option_ids if i in options and i != option_id]
        measures = measures_behind(view, (option_id,))
        counted = (" Counted on " + measure_names(view, measures) + "."
                   if measures else " This engagement has registered no measure this route stands "
                                   "on; name one.")
        out.append(T.QuestionPayload(
            text=(f"What does {option_id} cost, and what would it gain, against the routes it is "
                  f"weighed with ({', '.join(rivals)})? The route: {wording(option)}." + counted),
            asks_for=tuple(T.AsksFor(kind) for kind in SETTLING_KINDS),
            issue_ids=ctx.issue_ids,
            why=("nothing this engagement has registered tells these routes apart, so none of them "
                 "can be advised over the others"),
            effort=T.EffortClass.LOOKUP, strategy=T.FillStrategy.ASK_CLIENT,
            about_ids=(option_id, comparison.id), decision_id=decision.id))
    return out


def named_routes(view: Any, options: Mapping[str, T.Entity], ids: Sequence[str]) -> str:
    """The routes, each by its id and by the words this engagement recorded it
    in. Both, and for different reasons: the id is what a reader follows, the
    words are what the route is ABOUT. A record kept in ids alone is the same
    sentence in every engagement in the world."""
    return "; ".join(f"{i} {str(wording(options[i]) or '').strip().rstrip('.')}".strip()
                     for i in ids if i in options)


def settles_this_choice(view: Any, ids: Sequence[str]) -> str:
    """What would settle THIS choice, said in this engagement's own terms: the
    kinds of evidence that carry a direction, the routes one of them would have
    to name, and the measures those routes are already counted on.

    The measures are the half that makes the ask answerable. "Register a cost
    against one of these routes" is a sentence about the engine's type system;
    "register it against MEA-14 loaves per shift, which is what these routes
    already stand on" is a sentence somebody can act on, and it is different in
    every engagement because the measures are.
    """
    kinds = ", ".join(k.value for k in SETTLING_KINDS)
    measures = measures_behind(view, tuple(ids))
    where = (" counted on " + measure_names(view, measures) if measures else
             " - and this engagement has registered no measure these routes stand on, so name one")
    return (f"a {kinds} registered against one of {', '.join(ids)} and not against the others"
            + where)


def unsettled_because(view: Any, decision: T.Entity, options: Mapping[str, T.Entity],
                      comparison: T.Entity | None, reason: str, details: Sequence[str]) -> str:
    """R7: the reason, in this engagement's own routes, rows and measures.

    Every branch names something only this register holds. The count of routes
    is not a reason - "nothing separates the 27 route(s)" was one sentence
    shared by fifteen engagements, differing by an integer, and a reader could
    not tell from it which choice was open or what to send. What replaces it
    names the routes, the rows that disagree, and the measure the answer would
    be counted on.
    """
    ids = ([i for i in comparison.payload.option_ids if i in options]
           if comparison is not None else sorted(options))
    if reason == NO_ROUTE:
        return "no route is registered for it, so there is nothing to select"
    if reason == NO_COMPARISON:
        return (f"the registered routes were never weighed against one another - {named_routes(view, options, sorted(options))} - "
                "so nothing records why one would be taken over another")
    if reason == POINTS_TWO_WAYS:
        return (f"what this engagement registered about these routes points more than one way: "
                f"{', '.join(details)} bear on {comparison.id} ({', '.join(ids)}) and do not agree, "
                "so advising any of them would be preferring one reason over another without "
                "recording why")
    if reason == UNEVIDENCED:
        chosen = details[0] if details else ""
        return (f"the register points at {chosen}, and {chosen}'s own lineage reaches no confirmed "
                "fact and no approved assumption, so advising it would rest on nothing")
    return (f"nothing this engagement has registered tells these routes apart: "
            f"{named_routes(view, options, ids)}. What would settle it: "
            f"{settles_this_choice(view, ids)}")


def _no_conclusion(ctx: MethodContext, decision: T.Entity, options: Mapping[str, T.Entity],
                   comparison: T.Entity | None, reason: str, details: Sequence[str],
                   weight: float) -> T.Add:
    """R7: the typed reason this decision could not be settled, recorded
    AGAINST the decision so a reader looking for the advice finds the reason in
    its place.

    Which reason it is, is read off the register by `impasse` and never
    guessed, and the wording of it names the routes, the rows and the measures
    of THIS engagement (`unsettled_because`). The authority is the decision
    owner's, because a decision the analysis could not settle is still a
    decision somebody has to make.
    """
    return T.Add(new_entity(
        ctx, T.Kind.DECISION_REQUIRED,
        T.DecisionRequiredPayload(
            text=f"{decision.id} is unsettled by this analysis: "
                 f"{unsettled_because(ctx.registry, decision, options, comparison, reason, details)}",
            from_authority=T.Authority.DECISION_OWNER, decision_id=decision.id,
            options=tuple(sorted(options))),
        derived_from=((decision.id,) + tuple(sorted(options)) + tuple(details)
                      + ((comparison.id,) if comparison is not None else ())),
        relation=T.RelationToCentralDecision.RESOLVES, confidence=T.Confidence(None),
        decision_id=decision.id, weight=weight, status=T.Status.OPEN))


def _contested(ctx: MethodContext, decision: T.Entity, standing: T.Entity,
               comparison: T.Entity, options: Mapping[str, T.Entity],
               contests: Sequence[str], weight: float) -> T.Add:
    """R9: the record that the advice that stands is now contested.

    Written where evidence has arrived, bears on the routes the standing advice
    was chosen among, and leaves the register pointing at no route at all. The
    recommendation is NOT rewritten: it still says what it said, on the evidence
    it said it on, and rewriting it into a different route would be advising on
    a register that points nowhere. What is recorded instead is that the choice
    is back with its owner and which rows put it there - so the reader who finds
    the advice also finds, in the same place, the reason it can no longer be
    read as settled.
    """
    ids = [i for i in comparison.payload.option_ids if i in options]
    return T.Add(new_entity(
        ctx, T.Kind.DECISION_REQUIRED,
        T.DecisionRequiredPayload(
            text=(f"{standing.id} advises {standing.payload.option_id} on {decision.id}, and what "
                  f"this engagement has registered since does not bear it out: {', '.join(contests)} "
                  f"bear on {', '.join(ids)} and point more than one way. "
                  f"What would settle it: {settles_this_choice(ctx.registry, ids)}"),
            from_authority=T.Authority.DECISION_OWNER, decision_id=decision.id,
            options=tuple(sorted(options))),
        derived_from=(standing.id, decision.id, comparison.id) + tuple(contests),
        relation=T.RelationToCentralDecision.RESOLVES, confidence=T.Confidence(None),
        decision_id=decision.id, weight=weight, status=T.Status.OPEN))


def already_contested(view: Any, standing: T.Entity, contests: Sequence[str]) -> bool:
    """Whether the contest is already on the register: a live DECISION_REQUIRED
    citing this advice and every row that contests it. Read by citation, so the
    record is written once and a second run over the same register writes
    nothing."""
    wanted = {standing.id} | set(contests)
    return any(wanted <= set(d.provenance.derived_from)
               for d in live(view, T.Kind.DECISION_REQUIRED))


@register
class RecommendationMethod:
    spec = SPEC

    def _advice(self, ctx: MethodContext, decision: T.Entity, option: T.Entity,
                comparison: T.Entity, options: Mapping[str, T.Entity],
                supports: Sequence[str], reasons: Sequence[str],
                criteria: Sequence[str], weight: float) -> T.Entity:
        """The row itself, built the same way whether it is the first advice on
        this decision or the revision of one that stood. Building it once is
        what keeps a revision the same KIND of claim as the advice it replaces:
        same statement rules, same lineage rules, same status."""
        view = ctx.registry
        rivals = [options[i] for i in comparison.payload.option_ids
                  if i in options and i != option.id]
        settles = next(iter(borrowed(view, (getattr(decision.payload, "statement", ""),))), "")
        payload = T.RecommendationPayload(
            statement=advice_statement(view, option, rivals, settles, gaps_closed(view, option),
                                       reasons),
            decision_id=decision.id,
            option_id=option.id,
            supports=tuple(supports),
            conditional_on=(),          # synthesis.refresh_conditional_on owns this
            licensed_interpretation=False)   # synthesis.regulated owns this flag
        return new_entity(
            ctx, T.Kind.RECOMMENDATION, payload,
            derived_from=((option.id, decision.id, comparison.id) + tuple(supports)
                          + tuple(reasons) + steps_for(view, option.id) + tuple(criteria)),
            relation=T.RelationToCentralDecision.RESOLVES, confidence=T.Confidence(None),
            decision_id=decision.id, weight=weight, status=T.Status.PROPOSED)

    def run(self, ctx: MethodContext) -> MethodResult:
        view = ctx.registry
        decision = view.central_decision()
        if decision is None:
            return MethodResult(questions=(_no_decision_question(ctx),))
        issue = view.get(ctx.issue_ids[0]) if ctx.issue_ids else None
        weight = T.SENSITIVITY[T.RelationToCentralDecision.RESOLVES]
        if issue is not None:
            weight = issue.relevance.weight
        criteria = criteria_for(view, decision.id)
        options = {o.id: o for o in live(view, T.Kind.OPTION)
                   if o.payload.decision_id == decision.id}
        standing = [r for r in sorted(live(view, T.Kind.RECOMMENDATION), key=lambda e: e.id)
                    if r.payload.decision_id == decision.id]

        comparisons = widest_comparison(view, decision.id, options)
        option, comparison, supports, reasons = selected_route(view, comparisons, options)

        if standing:
            # R4 and R9 together. The decision is already advised, so nothing
            # is ADDED whatever happens - a second live recommendation on one
            # decision hands the reader the decision back. But an early return
            # here was the whole treatment of an engagement that had advised
            # once, and it made the first conclusion the last one: every fact
            # the client sent afterwards was unusable, because the only code
            # that could have read it had already returned.
            #
            # So the standing advice is compared with what the register now
            # points to. A DIFFERENT route: the standing row is superseded in
            # place, keeping its id, citing the rows that changed its mind. The
            # SAME route: nothing is written. NO route, and rows about these
            # routes that the advice does not cite: the advice is not rewritten
            # - it still says what it said on the evidence it said it on - and
            # the contest is recorded against the decision, where a reader
            # looking for the advice will find it. NO route and nothing new:
            # the run leaves the registry exactly as it found it, because this
            # law is "move when the evidence moves" and not "rewrite every
            # round".
            held = standing[0]
            if option is not None and comparison is not None:
                if option.id == held.payload.option_id:
                    return MethodResult()
                revised = with_id(self._advice(ctx, decision, option, comparison, options,
                                               supports, reasons, criteria, weight), held.id)
                return MethodResult(deltas=(T.Supersede(held.id, revised),))
            widest = comparisons[0] if comparisons else None
            contests = contesting_rows(view, held, widest, options)
            if not contests or already_contested(view, held, contests) or widest is None:
                return MethodResult()
            return MethodResult(deltas=(_contested(ctx, decision, held, widest, options,
                                                   contests, weight),))

        if option is None or comparison is None:
            # R7: no advice, and the reason recorded where a reader looks for
            # the advice. An engagement that concluded nothing and said nothing
            # has not declined to advise; it has been silent, and silence reads
            # as caution it never exercised. The ask that would settle it goes
            # out in the same breath, per route, so that what comes back can
            # bear on one route rather than on all of them at once.
            reason, comparison_at, details = impasse(view, options, comparisons)
            questions: list[T.QuestionPayload] = []
            if reason == NOTHING_SEPARATES and comparison_at is not None:
                # Only where nothing separates them: an engagement that HAS
                # registered something per route and still cannot conclude is
                # missing evidence, not a comparison, and asking it what tells
                # its routes apart would be asking for what it already holds.
                questions.extend(_separating_questions(ctx, view, decision, comparison_at, options))
            if reason in (NOTHING_SEPARATES, POINTS_TWO_WAYS) and comparison_at is not None:
                # The standing record outlives both impasses. A decision the
                # register disagrees about is no more settled than one it says
                # nothing about, and a blocker that names neither the routes nor
                # the measure says a decision is unanswered without saying what
                # would answer it.
                questions.extend(_standing_hole(ctx, view, decision, comparison_at, options,
                                                reason, details))
            unevidenced = [i for i in sorted(options)
                           if not supports_in(view, lineage_closure(view, (i,)))]
            if unevidenced:
                questions.append(_unevidenced_question(ctx, decision.id, unevidenced))
            return MethodResult(
                deltas=(_no_conclusion(ctx, decision, options, comparison_at, reason,
                                       details, weight),),
                questions=tuple(questions))

        return MethodResult(deltas=(T.Add(self._advice(
            ctx, decision, option, comparison, options, supports, reasons, criteria, weight)),))


__all__ = ["AGAINST_KINDS", "FOR_KINDS", "NOTHING_SEPARATES", "NO_COMPARISON", "NO_ROUTE",
           "POINTS_TWO_WAYS", "SETTLING_KINDS", "SPEC", "SUPPORT_STATUS", "UNDIRECTED_KINDS",
           "UNEVIDENCED", "RecommendationMethod", "advice_statement", "already_asked_about",
           "already_contested", "already_recommended", "bearing_rows", "bears_on", "borrowed",
           "contesting_rows", "criteria_for", "directed", "impasse", "is_support", "named_routes",
           "normalised", "points_to", "registered_claims", "route_phrase", "separates",
           "settles_this_choice", "settling_producers", "gaps_closed", "repeats_evidence",
           "selected_route", "steps_for", "undirected", "unsettled_because",
           "widest_comparison", "lineage_closure", "single_option", "supports_in"]
