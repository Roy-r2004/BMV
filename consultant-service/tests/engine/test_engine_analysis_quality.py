"""tests/engine/test_engine_analysis_quality.py - the laws that judge the
analysis, not the ones that count it.

The C23 benchmark already proves that fifteen engagements DIVERGE: different
questions, different deliverable sets, different section signatures. Every one
of those assertions is a count over distinct sets, and a count over distinct
sets is satisfied trivially by an engine that emits six hundred options -
divergence is cheap when production is unbounded. Nothing in the suite asks
whether what was produced is the KIND of thing its label claims.

Three defects live in that gap, all of them green today:

  1. RECOMMENDATION rows whose statement is a FACT statement, verbatim. The
     row cites that same fact as its `supports`, so I3, L2 and
     `unsupported_recommendations()` are all satisfied by the very fact the
     advice is a copy of. Extracted evidence, relabelled as advice.
  2. Runaway production: 603 OPTIONs and 339 CAPABILITYs in one engagement off
     143 method runs. BOUNDS caps rounds and specialists per round; it caps
     nothing about how many rows a round may leave behind.
  3. Uneven coverage: two core engagements reach synthesis having run 80-90
     methods and register zero options, zero recommendations and zero
     capabilities, while others register hundreds.

Every law below is STRUCTURAL. Verbatim equality after whitespace
normalisation is exact comparison, which the engine allows; no similarity
measure is imported here and none may be - `difflib` and its relatives are
what test_engine_universality forbids the engine, and a test that graded the
engine by fuzzy overlap would be grading it on a rule it may not use.

Bounds, never per-case counts: law D reads ONE declared bound name that applies
to every engagement and every analysis kind alike, and states the defensible
default the engine should carry for it. No number in this file is attached to a
case id.
"""
from __future__ import annotations

import pytest

from app.config import settings
from app.engine.benchmark import cases as C
from app.engine.benchmark import harness as H
from app.engine.benchmark.oracle import structural_oracle
from app.engine.llm import FakeProvider
from app.engine.types import (
    ANALYSIS_KINDS as DECLARED_ANALYSIS_KINDS,
    BOUNDS, Authority, FactBasis, Kind, Phase, Status,
)

import app.engine.methods.builtin  # noqa: F401  - method registration is by import

# Law E and S2 (`test_engine_structural_laws.py`) ask one question - did this
# engagement conclude anything about its decision - so they read ONE predicate
# for what a recorded reason is, imported from where that predicate lives
# rather than copied. Two copies of one rule is how Law E came to pass an
# engagement S2 would have refused, and how both came to be repaired in
# different places. The hand-built engagements come from the same file for the
# same reason: a control that drifts proves nothing about the law it controls.
from tests.engine.test_engine_structural_laws import (  # noqa: E402
    build,
    central,
    declared_rows,
    silent_rows,
    sound_rows,
    typed_blockers,
)


# ===========================================================================
# The runs, once
# ===========================================================================

@pytest.fixture(scope="module")
def loaded():
    return C.load_all()


@pytest.fixture(scope="module")
def bundles(loaded):
    """Every case run once against the case-blind structural oracle. The unit
    under test is the population of fifteen engagements, not one of them; and
    the runs are deterministic, so running them again per test would say
    nothing new."""
    return {case.id: H.run_case(case, FakeProvider(oracle=structural_oracle)) for case in loaded}


# ===========================================================================
# Shared structural helpers (exact comparison only)
# ===========================================================================

def norm(text) -> str:
    """Whitespace-normalised text for EXACT comparison. Not a similarity
    measure: two strings are equal here only when they are the same characters
    in the same order once runs of whitespace are collapsed."""
    return " ".join(str(text or "").split())


def quoted_evidence(registry) -> dict:
    """Every normalised string the engagement holds as EVIDENCE: what a FACT
    says, the locator quote a FACT was verified against, and the name a MEASURE
    is registered under. A recommendation equal to one of these is not advice
    about the evidence - it IS the evidence with a different kind on the row."""
    out: dict = {}
    for e in registry.live(Kind.FACT) + registry.live(Kind.MEASURE):
        for text in (getattr(e.payload, "statement", None), getattr(e.payload, "name", None),
                     e.provenance.source_locator):
            key = norm(text)
            if key:
                out.setdefault(key, []).append(e.id)
    return out


def lineage_closure(registry, roots) -> set:
    """Every id the given rows reach through `derived_from` and calculation
    `inputs` - the same walk `EngagementRegistry.support_closure` makes, made
    from one row instead of from all of them."""
    seen: set = set()
    frontier = list(roots)
    while frontier:
        entity_id = frontier.pop()
        if entity_id in seen:
            continue
        seen.add(entity_id)
        row = registry.get(entity_id)
        if row is None:
            continue
        frontier.extend(row.provenance.derived_from)
        frontier.extend(getattr(row.payload, "inputs", ()) or ())
    return seen


def evidential_fact(row) -> bool:
    """A FACT somebody stands behind: CONFIRMED by the authority that owns it,
    or backed by a document the engine read. A PROPOSED inferred fact is a
    claim, not evidence."""
    return row is not None and row.kind is Kind.FACT and (
        row.status is Status.CONFIRMED
        or row.payload.basis in (FactBasis.DOCUMENT_VERIFIED, FactBasis.DOCUMENT_EXTRACTED))


def report(problems, limit: int = 24) -> str:
    head = list(problems[:limit])
    if len(problems) > limit:
        head.append("... and {} more".format(len(problems) - limit))
    return "\n".join(head)


# The kinds an ANALYSIS produces - the engine's own conclusions, as opposed to
# the evidence it was given (FACT, EVIDENCE_SOURCE) and the process records it
# keeps (QUESTION, ANALYSIS, STATEMENT, CHARTER).
ANALYSIS_KINDS = (
    Kind.CAPABILITY, Kind.OPTION, Kind.EVALUATION_CRITERION, Kind.TRADE_OFF, Kind.RECOMMENDATION,
    Kind.PROCESS_STEP, Kind.WORKSTREAM, Kind.INITIATIVE, Kind.ACTION, Kind.HYPOTHESIS,
    Kind.RISK, Kind.CONTROL,
)

# The one bound this file needs and the engine does not yet declare. A NAME,
# applied to every engagement and every analysis kind alike, because a number
# attached to one case would be the fixed count BOUNDS exists to forbid.
ENTITY_BOUND = "MAX_ENTITIES_PER_ANALYSIS_KIND"


def defensible_default(bounds) -> int:
    """The ceiling the engine can defend from the bounds it ALREADY declares:
    an engagement runs at most MAX_ANALYSIS_ROUNDS rounds, each round admits at
    most MAX_SPECIALISTS_PER_ROUND producers, and a producer may open at most
    MAX_FANOUT branches. 6 x 4 x 6 = 144 rows of one kind is already a generous
    reading of "everything ran flat out and nothing was ever reconciled": not a
    target, but the point past which the engagement has stopped analysing and
    started emitting."""
    return (int(bounds["MAX_ANALYSIS_ROUNDS"]) * int(bounds["MAX_SPECIALISTS_PER_ROUND"])
            * int(bounds["MAX_FANOUT"]))


def worked_engagement_floor(bounds) -> int:
    """How many method runs make an engagement one that OWES conclusions. An
    engagement that ran fewer methods than a full analysis budget could admit
    (MAX_ANALYSIS_ROUNDS x MAX_SPECIALISTS_PER_ROUND) is legitimately thin and
    is not judged by law E."""
    return int(bounds["MAX_ANALYSIS_ROUNDS"]) * int(bounds["MAX_SPECIALISTS_PER_ROUND"])


# ===========================================================================
# A. A recommendation is not a fact wearing a different label
# ===========================================================================

def test_a_recommendation_is_not_a_restatement_of_a_fact(bundles):
    """LAW A: a RECOMMENDATION is a proposed course of action, so (a) it names
    the OPTION it selects - a live OPTION registered for the same decision -
    and (b) its statement is not, character for character after whitespace
    normalisation, the statement or locator quote of a FACT or the name of a
    MEASURE the same registry already holds. Advice that repeats the evidence
    has selected nothing.

    MUTATION THIS MUST CATCH: `methods/builtin/recommendation.py` writing
    `statement=action.payload.text` where that action's text was itself copied
    off a FACT, and leaving `option_id=None` because `single_option()` found
    none in the lineage. Both halves are live in the tree today; restoring
    either half alone still fails this test, which is what makes it a law
    rather than a smoke check.

    Not a similarity test: `norm()` collapses whitespace and compares for
    equality. No fuzzy matcher is imported, here or in the engine.
    """
    retired = (Status.SUPERSEDED, Status.REJECTED, Status.WITHDRAWN)
    problems = []
    for case_id, bundle in sorted(bundles.items()):
        registry = bundle.registry
        evidence = quoted_evidence(registry)
        for rec in registry.live(Kind.RECOMMENDATION):
            option_id = rec.payload.option_id
            option = registry.get(option_id) if option_id else None
            if (option is None or option.kind is not Kind.OPTION or option.status in retired
                    or option.payload.decision_id != rec.payload.decision_id):
                problems.append(
                    "{} {}: option_id={!r} is not a live OPTION for {}; the advice selects nothing"
                    .format(case_id, rec.id, option_id, rec.payload.decision_id))
            same = evidence.get(norm(rec.payload.statement))
            if same:
                problems.append(
                    "{} {}: statement is verbatim {} ({!r}) - a fact relabelled as advice"
                    .format(case_id, rec.id, sorted(same), rec.payload.statement[:60]))
    assert not problems, (
        "a recommendation must select a registered option and must say something the evidence "
        "does not already say:\n" + report(problems))


# ===========================================================================
# B. A recommendation traces to evidence - evidence that is not itself
# ===========================================================================

def test_a_recommendation_traces_to_evidence_other_than_itself(bundles):
    """LAW B: `registry.unsupported_recommendations()` is empty, every
    RECOMMENDATION's support closure reaches at least one CONFIRMED or
    document-backed FACT, and at least one such fact is NOT a verbatim copy of
    the recommendation's own statement.

    The third clause is what gives the first two content. A recommendation
    whose statement IS its support's statement satisfies I3, L2 and
    `unsupported_recommendations()` completely - the citation is real, the fact
    is CONFIRMED, the lineage resolves - and has still traced to nothing,
    because the evidence and the claim are one row apart and identical. That is
    the circle the registry exists to make impossible, and it is open.

    MUTATION THIS MUST CATCH: a recommendation producer that satisfies the
    support laws by citing the row it copied. Equivalently: delete the
    requirement that advice rest on something other than its own restatement,
    and this test goes green while every existing law stays green - which is
    exactly the state of the tree today.
    """
    problems = []
    for case_id, bundle in sorted(bundles.items()):
        registry = bundle.registry
        for rec, why in registry.unsupported_recommendations():
            problems.append("{} {}: unsupported ({})".format(case_id, rec.id, why))
        for rec in registry.live(Kind.RECOMMENDATION):
            claim = norm(rec.payload.statement)
            reached = [registry.get(i) for i in lineage_closure(registry, rec.payload.supports)]
            facts = [f for f in reached if evidential_fact(f)]
            if not facts:
                problems.append(
                    "{} {}: support closure reaches no confirmed or document-backed FACT"
                    .format(case_id, rec.id))
                continue
            distinct = [f for f in facts if norm(f.payload.statement) != claim]
            if not distinct:
                problems.append(
                    "{} {}: every fact it rests on is itself, verbatim ({}); the citation is a circle"
                    .format(case_id, rec.id, [f.id for f in facts]))
    assert not problems, (
        "advice traces to evidence FOR the advice, never to a copy of the advice:\n" + report(problems))


# ===========================================================================
# C. A recommendation is a proposal, and it says what chose it
# ===========================================================================

def test_a_recommendation_is_a_proposed_course_of_action(bundles):
    """LAW C: a RECOMMENDATION (a) is never born APPROVED - the consultant
    proposes and only the decision owner or the client approves (I1, R2);
    (b) carries authority CONSULTANT, unless it is a licensed interpretation,
    in which case it belongs to a QUALIFIED_PROFESSIONAL (design 9.6); and
    (c) names the EVALUATION_CRITERIA that chose it - at least one live
    criterion for the same decision reachable through its lineage, required
    whenever the engagement registered any criterion for that decision at all.

    Clause (c) is the one that fails today. Every case registers criteria for
    its central decision, and every recommendation cites only (action,
    decision, supports), so nothing on the row says why this course of action
    beat the others. A recommendation that names no criterion has not chosen;
    it has been emitted.

    MUTATION THIS MUST CATCH: dropping the criteria from a recommendation's
    lineage (clause c), writing advice APPROVED at birth (clause a), or
    deriving its authority from the producer instead of the information type
    (clause b). Clauses (a) and (b) hold on the tree today - I1 and I7 enforce
    them at the registry door - and are asserted here so a fix to (c) cannot be
    bought by loosening them.
    """
    problems = []
    for case_id, bundle in sorted(bundles.items()):
        registry = bundle.registry
        criteria_for: dict = {}
        for crit in registry.live(Kind.EVALUATION_CRITERION):
            criteria_for.setdefault(crit.payload.decision_id, set()).add(crit.id)
        for rec in registry.live(Kind.RECOMMENDATION):
            born = registry.lineage(rec.id)[0]
            if born.status is Status.APPROVED:
                problems.append(
                    "{} {}: born APPROVED; the consultant does not approve its own advice"
                    .format(case_id, rec.id))
            expected = (Authority.QUALIFIED_PROFESSIONAL if rec.payload.licensed_interpretation
                        else Authority.CONSULTANT)
            if rec.authority is not expected:
                problems.append("{} {}: authority {}, expected {}"
                                .format(case_id, rec.id, rec.authority.value, expected.value))
            available = criteria_for.get(rec.payload.decision_id, set())
            if not available:
                continue
            if not (available & lineage_closure(registry, (rec.id,))):
                problems.append(
                    "{} {}: names none of the {} criteria registered for {}; nothing on the row "
                    "says what chose it".format(case_id, rec.id, len(available), rec.payload.decision_id))
    assert not problems, (
        "a recommendation is proposed by the consultant and says what chose it:\n" + report(problems))


# ===========================================================================
# D. Production is bounded per engagement
# ===========================================================================

def test_production_of_each_analysis_kind_is_bounded_per_engagement(bundles):
    """LAW D: for every engagement and every analysis kind, the number of live
    rows stays within ONE declared bound, BOUNDS["MAX_ENTITIES_PER_ANALYSIS_KIND"],
    whose defensible default is MAX_ANALYSIS_ROUNDS x MAX_SPECIALISTS_PER_ROUND
    x MAX_FANOUT (6 x 4 x 6 = 144 on today's values): every round, running flat
    out, opening every branch it is allowed.

    The bound is a name, not a number per case. BOUNDS already caps how many
    ROUNDS may run and how many producers a round may admit; it caps nothing
    about what a round may leave behind, which is why 603 OPTIONs off 143
    method runs is currently legal. An engagement that registers 603 routes has
    not analysed a decision, it has enumerated the registry.

    This fails twice on the tree as it stands: the bound name is not in BOUNDS
    at all (there is no law), and the counts blow the defensible default anyway
    (the runaway). Both are reported together so that declaring the bound is
    not mistaken for fixing the engine.

    MUTATION THIS MUST CATCH: removing the ceiling from a producer's emit loop,
    or declaring the bound at a value large enough to wave the current numbers
    through - the default here is derived from bounds the engine already
    publishes, so a laxer value has to be argued for against them.
    """
    problems = []
    default = defensible_default(BOUNDS)
    if ENTITY_BOUND not in BOUNDS:
        problems.append(
            "BOUNDS declares no {}: nothing in the engine bounds how many rows of one analysis "
            "kind an engagement may produce. Defensible default {} = MAX_ANALYSIS_ROUNDS x "
            "MAX_SPECIALISTS_PER_ROUND x MAX_FANOUT (app/config.py installs ENGINE_{} off the "
            "same table).".format(ENTITY_BOUND, default, ENTITY_BOUND))
    elif not hasattr(settings, "ENGINE_" + ENTITY_BOUND):
        problems.append("BOUNDS declares {} but Settings carries no ENGINE_{}"
                        .format(ENTITY_BOUND, ENTITY_BOUND))

    # The declared bound is LIMITED BY the defensible default, not merely
    # replaced by it when the key is missing. Read as a fallback alone, the
    # default was a courtesy: raising the declared value moved the goalposts
    # and the measuring stick together, every count went legal, and the law
    # reported green on an engagement generating exactly as before. Stated as
    # a limit, the value can be argued DOWN from the bounds the engine already
    # publishes and cannot be argued up without moving those.
    assert int(BOUNDS[ENTITY_BOUND]) <= defensible_default(BOUNDS), (
        "BOUNDS[{!r}] is {}, above the {} that MAX_ANALYSIS_ROUNDS x MAX_SPECIALISTS_PER_ROUND x "
        "MAX_FANOUT can defend: every round running flat out, opening every branch it is allowed. "
        "A larger ceiling is not this bound's to grant - it is an argument against those three."
        .format(ENTITY_BOUND, BOUNDS[ENTITY_BOUND], defensible_default(BOUNDS)))
    # ... and the counts below are judged against the default REGARDLESS, so a
    # bound raised past it cannot buy the engine room even for the one run in
    # which the assert above is the thing being fixed.
    bound = min(int(BOUNDS.get(ENTITY_BOUND, default)), default)

    over = []
    for case_id, bundle in sorted(bundles.items()):
        for kind in ANALYSIS_KINDS:
            count = len(bundle.registry.live(kind))
            if count > bound:
                over.append((count, "{}: {} live {} rows (bound {})"
                             .format(case_id, count, kind.value, bound)))
    problems.extend(line for _count, line in sorted(over, reverse=True))
    assert not problems, (
        "an engagement that emits more rows of one kind than every round running flat out could "
        "justify has stopped analysing:\n" + report(problems))


def test_the_kinds_this_file_bounds_are_the_kinds_the_engine_rations():
    """LAW D's REACH. `ANALYSIS_KINDS` above is the list law D walks; the engine
    rations exactly the kinds `app.engine.types.ANALYSIS_KINDS` names, and I9,
    `saturated_kinds` and S1 all read that one. Two lists, one meaning - so
    either may be narrowed while every law over the other stays green.

    Narrowing the engine's is the mutation that matters: drop OPTION from it
    and I9 stops rationing routes, `saturated_kinds` stops seeing the producer
    fill up, S1's write-path count stops looking at the kind altogether, and
    the only thing left judging the runaway is law D - which would still be
    walking its own unnarrowed copy and would still fail. That is the point of
    keeping the copy. This pin is what stops the copy being "fixed" to match a
    narrowed engine, which is how the narrowing would come to be believed.

    MUTATION THIS MUST CATCH: removing a kind from either list. Membership is
    compared as a set of names, so a reordering is not a defect and a deletion
    cannot be spelled as one.
    """
    mine = {k.name for k in ANALYSIS_KINDS}
    engine = {k.name for k in DECLARED_ANALYSIS_KINDS}
    assert mine == engine, (
        "the kinds law D bounds and the kinds the engine rations have parted; "
        "only here: {}; only in app.engine.types: {}"
        .format(sorted(mine - engine) or "-", sorted(engine - mine) or "-"))
    assert len(ANALYSIS_KINDS) == len(set(ANALYSIS_KINDS)), "a kind is listed twice"
    # And what the list is FOR: the engine's own conclusions, never the
    # evidence it was handed or the records it is audited by. A law that
    # rationed FACT would ration the client.
    for kind in (Kind.FACT, Kind.EVIDENCE_SOURCE, Kind.QUESTION, Kind.ANALYSIS, Kind.DECISION):
        assert kind not in ANALYSIS_KINDS, (
            "{} is evidence or a process record, not a conclusion the engine may be "
            "rationed on".format(kind.name))


# ===========================================================================
# E. Coverage is even
# ===========================================================================

# The kinds Law E used to accept as a conclusion. Kept as the ghost the repair
# is measured against, and read by nothing but the proof inside the law: a
# predicate nothing ever passed would be a rewrite, not a repair.
COUNTED_KINDS = (Kind.OPTION, Kind.RECOMMENDATION, Kind.CAPABILITY)


def a_kind_is_non_empty(registry) -> bool:
    """Law E's predicate AS IT STOOD: any one of OPTION, RECOMMENDATION or
    CAPABILITY non-empty.

    Every engagement registers fifteen to twenty-seven routes, so the
    disjunction was satisfied by the first producer that ran and the law could
    not fail while any producer at all was reachable."""
    return any(len(registry.live(kind)) for kind in COUNTED_KINDS)


def unconcluded_engagement(registry) -> list[str]:
    """LAW E's predicate: what a worked engagement owes about ITS OWN DECISION.

    A live RECOMMENDATION on the central decision, or a record naming the
    evidence that would settle it - `typed_blockers`, the same reading S2 makes
    of the same question, so the two laws cannot come to disagree about what a
    conclusion is.

    Routes are not a conclusion. Three routes to a gap are the question laid
    out; a capability gap is the question found. Counting them as conclusions
    is what made this law vacuous, and it is why the disjunction above is kept
    only as a ghost.
    """
    decision = central(registry)
    if decision is None:
        return ["no live CENTRAL decision: there is nothing this engagement could conclude about"]
    if [r for r in registry.live(Kind.RECOMMENDATION) if r.payload.decision_id == decision.id]:
        return []
    if typed_blockers(registry, decision.id):
        return []
    return ["no live RECOMMENDATION on {}, and no record names the evidence that would settle it"
            .format(decision.id)]


def test_every_worked_core_engagement_reaches_a_conclusion(bundles, loaded):
    """LAW E: a CORE engagement that reached SYNTHESIS and holds a CHARTER owes
    a conclusion ABOUT ITS CENTRAL DECISION - a live RECOMMENDATION on that
    decision, or a record naming the evidence that would settle it. Either is a
    conclusion; a consultant who cannot choose says so and says what would let
    him.

    This law used to read "not zero OPTIONs AND zero RECOMMENDATIONs AND zero
    CAPABILITYs", and that is the defect it now catches in itself. Every
    engagement registers fifteen to twenty-seven routes before anything is
    concluded, so the disjunction was satisfied by the first producer that ran:
    the law was green on every engagement in every state and judged nobody.
    Routes on the table are the question, not an answer to it. The proof is the
    first block below - one hand-built engagement, holding routes and a gap and
    no conclusion, that the old predicate passes and this one fails.

    There is deliberately NO exemption by run count. A floor on method runs
    reads a number about the ENGINE - how much work it did - to excuse a hole
    in what the CLIENT got, and those are not the same question; an engagement
    that ran six methods and concluded nothing has still concluded nothing.
    The floor also made the law disappear the moment the engine stopped
    generating: with a bounded issue tree no engagement runs 24 methods, so
    every one of them was exempt and the law was judging nobody.

    MUTATION THIS MUST CATCH: any change that leaves the recommendation
    producer unreachable for a subset of engagements - a gate whose inputs only
    some issue trees can satisfy - while the aggregate divergence assertions
    stay green because the OTHER engagements still differ from each other. And
    the restoration of the disjunction, which is the same mutation applied to
    the law instead of to the engine.
    """
    # THE REPAIR, PROVED. Two routes on the table, a capability gap found,
    # nothing concluded and nothing asked.
    thin = build(silent_rows())
    assert a_kind_is_non_empty(thin), (
        "Law E as it stood passes this engagement: {} live OPTION(s) and {} live CAPABILITY(s)"
        .format(len(thin.live(Kind.OPTION)), len(thin.live(Kind.CAPABILITY))))
    assert unconcluded_engagement(thin), \
        "the repaired law must fail the same engagement, or the repair changed nothing"

    # NEGATIVE CONTROLS: the engagement that advised, and the engagement that
    # advised nothing and recorded what would settle it. Both concluded.
    assert unconcluded_engagement(build(sound_rows())) == []
    assert unconcluded_engagement(build(declared_rows())) == []

    core = {case.id for case in C.core_cases(loaded)}
    problems = []
    judged = 0
    for case_id, bundle in sorted(bundles.items()):
        if case_id not in core or bundle.phase != Phase.SYNTHESIS.value:
            continue
        registry = bundle.registry
        if not registry.live(Kind.CHARTER):
            continue
        judged += 1
        why = unconcluded_engagement(registry)
        if why:
            problems.append(
                "{}: {} method runs to synthesis and {} (live OPTION {}, CAPABILITY {} - which is "
                "why the law as it stood passed it)"
                .format(case_id, len(bundle.methods), "; ".join(why),
                        len(registry.live(Kind.OPTION)), len(registry.live(Kind.CAPABILITY))))
    assert judged >= 2, (
        "only {} core engagements were judged; the law would be vacuous.".format(judged))
    assert not problems, (
        "every worked core engagement owes a conclusion about its own decision:\n"
        + report(problems))
