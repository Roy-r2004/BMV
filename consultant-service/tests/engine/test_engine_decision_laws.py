"""C25 - six laws over the CHOICE the engine makes, and over the work it spends
making it.

C24 (`test_engine_structural_laws.py`) proved that advice has the SHAPE of
advice: one recommendation per decision, naming a live route, citing a
criterion and a comparison, repeating no evidence. Every one of those laws is
green, and every recommendation the suite produces still selects a route whose
`mechanism` is `make`. Never `buy`. Never `partner` - although the routes are
perfectly balanced per capability class, three to each open gap, in every
engagement. The engine does not choose. It takes route one, and the shape laws
cannot see it, because taking route one has exactly the shape of choosing.

These six laws are about the CONTENT of the choice and the COST of making it.

  T1 THE CHOICE FOLLOWS THE EVIDENCE. Two engagements identical but for the
     evidence bearing on their routes - each mirroring the other - cannot
     advise the same route. And over the population: where every engagement
     advises the same mechanism, each of them must instead have declared that
     it could not choose and named what would settle it.
       mutation: select `option_ids[0]`, or any other fixed position in a
       registration order, and call the order a comparison.

  T2 AN UNSEPARATED CHOICE IS DECLARED, NOT TAKEN. For every comparison the
     engagement registered: either something it holds tells the routes apart -
     a COST, a BENEFIT, a RISK, a CONSTRAINT, a CRITERION bearing on one route
     and not another, or scores that differ - and a selection may be made; or
     nothing does, and then the engagement must record that it cannot choose
     and name the evidence that would settle it, and must NOT select.
       mutation: emit the recommendation anyway and let the trade-off's
       `gives_up` ("these routes are alternatives") stand in for a comparison.

  T3 OPTIONS CARRY THIS ENGAGEMENT. A route's text must name the subject it is
     a route to, as THIS engagement recorded it. The frame may be generic - it
     SHOULD be, it comes from a closed catalogue - but the subject may not.
     And across the population, distinct route texts must scale with the
     engagements, not sit at the class x route cross product.
       mutation: name the subject from the capability CLASS instead of from the
       capability, which collapses 318 routes onto 27 sentences and makes every
       engagement's options word-for-word another's; or name it from the
       capability's ID, which is a pointer to the subject and not the subject -
       "Stand up CAP-4 with the organisation's own people and systems" is what
       `named()` writes when a capability has no wording, and it used to pass.

  T4 NO VACUOUS LAW. Both laws below were vacuous, and both have now been
     REPAIRED WHERE THEY LIVE rather than shadowed by a stricter twin here;
     T4 is the proof of the repairs, and every predicate it names is imported
     from the file whose law it is.
     (a) Law E of `test_engine_analysis_quality.py` passed if ANY of OPTION /
         RECOMMENDATION / CAPABILITY was non-empty. Every engagement registers
         fifteen to twenty-seven options, so the disjunction was satisfied by
         the producer that ran first and the law judged nobody. Repaired: a
         core engagement that reached synthesis owes a conclusion ABOUT ITS
         CENTRAL DECISION - advice on it, or a record of what would settle it.
     (b) S2's `typed_blockers()` accepted any OPEN QUESTION that named the
         central decision - and `names_decision` counted a mention in
         `derived_from`, which nearly every row carries. Repaired: a blocker
         names the decision in a TYPED field and names the missing evidence in
         `asks_for`, never the decision in a lineage link.
       mutation: shadow a vacuous law with a strict one and leave the vacuous
       one standing, which is what this file used to do - the suite stays green
       either way, and the law that runs is still the law that measures nothing.

  T5 ADVICE IS REVISABLE. Evidence arriving after the advice, which moves which
     route the evidence favours, must move the advice - by Supersede, with the
     new evidence cited, and never by a second recommendation beside the first.
       mutation: return early when the decision already carries advice, which
       is a correct guard against restating and a wrong one against revising.

  T6 NO GENERATE-AND-DISCARD ANYWHERE, ISSUE INCLUDED. Three clauses: nothing
     offered to the registry may vanish from it (every kind, ISSUE included);
     no run may throw away everything it generated; and no method may be run
     again after a run of it kept nothing.
       mutation: count the waste at the registry door. Refused batches are
       rolled back before they get there and runs discarded inside the method
       never reach it at all, so the door sees a clean sheet while model calls
       are spent every engagement writing nothing.

INDEPENDENCE. The change set these laws are aimed at also moved the instrument:
the per-kind ceiling, the kind list it applies to, the registry's capacity
check and the oracle's shape filter are all additions in the same diff. No law
in this file reads any of them, and `test_no_law_reads_the_moved_instrument`
pins that as source. Every law counts at the METHOD boundary or reads only
typed payload fields.

Written as tests only. No production module is edited by this file; the two
instruments are installed by a fixture and removed in its teardown.
"""
from __future__ import annotations

import collections
import pathlib
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

import pytest

from app.engine.benchmark import cases as C
from app.engine.benchmark import harness as H
from app.engine.benchmark.oracle import structural_oracle
from app.engine.llm import FakeProvider
from app.engine.methods.builtin.recommendation import RecommendationMethod
from app.engine.methods.contract import METHODS, MethodContext
from app.engine.registry import EngagementRegistry
from app.engine.types import (
    Actor,
    Add,
    AsksFor,
    Authority,
    BenefitPayload,
    CapabilityClass,
    CapabilityPayload,
    Confidence,
    CostPayload,
    DecisionPayload,
    DecisionRequiredPayload,
    DecisionRole,
    EffortClass,
    Entity,
    EvaluationCriterionPayload,
    FactBasis,
    FactPayload,
    FillStrategy,
    GapState,
    Kind,
    MeasurePayload,
    OptionPayload,
    Phase,
    Provenance,
    QuestionPayload,
    RecommendationPayload,
    RelationToCentralDecision,
    Relevance,
    Score,
    Status,
    Supersede,
    TERMINAL_STATUSES,
    TradeOffPayload,
    UnitFamily,
    make_entity,
)

import app.engine.methods.builtin  # noqa: F401  - registration by import

from tests.engine.conftest import FIXED_CLOCK

# The two predicates T4 is about, imported from where they live rather than
# copied, so a rewrite of either cannot leave this file measuring a ghost. Both
# have now been repaired where they live - T4 is the proof of those repairs, so
# what these names bind to is the law in the tree and not a restatement of it.
# `lineage_only_blockers` is the clause S2 used to read, kept beside its
# replacement for the same reason.
from tests.engine.test_engine_structural_laws import (
    lineage_only_blockers,
    typed_blockers,
    unconcluded as s2_unconcluded,
)
from tests.engine.test_engine_analysis_quality import (
    a_kind_is_non_empty as law_e_as_it_stood,
    unconcluded_engagement,
)


# ===========================================================================
# 0. The benchmark, run once, instrumented at the METHOD boundary
# ===========================================================================

@dataclass(frozen=True)
class RunRecord:
    """One run of one method, as the method itself finished it - before the
    runner, the admission rules or the registry have had a word.

    `discarded` is the method's own count of outputs it generated and refused:
    the `M.<method>.<reason>` findings are the engine's own record of a
    candidate it would not keep. Counted here because a refusal inside the
    method is invisible everywhere downstream - the delta list is simply
    shorter, and a shorter list looks like a quieter round.
    """
    method_id: str
    added: int
    superseded: int
    questions: int
    discarded: int
    model_calls: int


@dataclass
class Run:
    case_id: str
    registry: Any
    phase: str
    methods: tuple[str, ...]
    records: tuple[RunRecord, ...] = ()
    offered: Mapping[str, int] = field(default_factory=dict)


@pytest.fixture(scope="module")
def runs():
    """Every benchmark case, once, with two instruments installed.

    The first counts rows OFFERED to the registry (`_add`), the second records
    every method run at the moment the method returns. Module-scoped for the
    reason every benchmark suite here is: fifteen engagements are the unit
    under test, and the runs are deterministic.
    """
    current: dict[str, str] = {"case": ""}
    records: dict[str, list[RunRecord]] = collections.defaultdict(list)
    offered: dict[str, dict[str, int]] = collections.defaultdict(dict)

    original_add = EngagementRegistry._add

    def counting_add(self, e):
        seen = offered[current["case"]]
        seen[e.kind.name] = seen.get(e.kind.name, 0) + 1
        return original_add(self, e)

    by_class: dict[type, str] = {}
    for method in METHODS.all():
        by_class.setdefault(type(method), method.spec.id)
    originals = {cls: cls.run for cls in by_class}

    def instrument(original, method_id):
        def run(self, ctx):
            result = original(self, ctx)
            records[current["case"]].append(RunRecord(
                method_id=method_id,
                added=sum(1 for d in result.deltas if isinstance(d, Add)),
                superseded=sum(1 for d in result.deltas if isinstance(d, Supersede)),
                questions=len(result.questions),
                discarded=sum(1 for f in result.findings if str(f.law).startswith("M.")),
                model_calls=len(result.model_call_ids)))
            return result
        return run

    EngagementRegistry._add = counting_add
    for cls, method_id in by_class.items():
        cls.run = instrument(originals[cls], method_id)
    try:
        out: dict[str, Run] = {}
        for case in C.load_all():
            current["case"] = case.id
            bundle = H.run_case(case, FakeProvider(oracle=structural_oracle))
            out[case.id] = Run(case_id=case.id, registry=bundle.registry, phase=bundle.phase,
                               methods=tuple(bundle.methods),
                               records=tuple(records[case.id]), offered=dict(offered[case.id]))
        return out
    finally:
        EngagementRegistry._add = original_add
        for cls, original in originals.items():
            cls.run = original


@pytest.fixture(scope="module")
def core_ids():
    return {case.id for case in C.core_cases(C.load_all())}


# ===========================================================================
# 1. Shared reading. Every law IS one of these functions, and every law's
#    negative control runs the SAME function on a hand-built engagement.
# ===========================================================================

WORD = re.compile(r"[a-z0-9]+")


def live(view, kind: Kind) -> list[Entity]:
    return [e for e in view.query(kind) if e.status not in TERMINAL_STATUSES]


def normalised(text: Any) -> str:
    """Whitespace collapsed, case folded. Exact comparison only - no similarity
    measure is imported by this module and none may be."""
    return " ".join(str(text or "").split()).casefold()


def words(text: Any) -> set[str]:
    return set(WORD.findall(str(text or "").casefold()))


def central(view) -> Entity | None:
    for d in live(view, Kind.DECISION):
        if d.payload.role is DecisionRole.CENTRAL:
            return d
    return None


# -- what separates one route from another ----------------------------------

DISCRIMINATING_KINDS: tuple[Kind, ...] = (
    Kind.COST, Kind.BENEFIT, Kind.RISK, Kind.CONSTRAINT, Kind.EVALUATION_CRITERION)


def bears_on(entity: Entity, option_id: str) -> bool:
    """Whether a registered row is ABOUT this route. Two typed ways a row says
    so: the `for_ids` field the costed kinds carry, and the citation it was
    written under. Nothing here reads wording."""
    if option_id in (getattr(entity.payload, "for_ids", ()) or ()):
        return True
    return option_id in entity.provenance.derived_from


def bearing_evidence(view, option_id: str) -> frozenset[str]:
    """Everything the engagement registered that bears on THIS route and could
    tell it from another.

    A score is included by its VALUE, not by its id: two routes scored 0.5 on
    one criterion carry the same string here and therefore separate nothing,
    which is the truth about them. Two routes scored differently carry
    different strings and do.
    """
    out: set[str] = set()
    for kind in DISCRIMINATING_KINDS:
        for e in live(view, kind):
            if bears_on(e, option_id):
                out.add(e.id)
    for t in live(view, Kind.TRADE_OFF):
        for s in t.payload.scores:
            if s.option_id == option_id:
                out.add(f"{t.id}/{s.criterion_id}={s.score}")
    return frozenset(out)


def separated(view, option_ids: Sequence[str]) -> bool:
    """Whether anything this engagement holds tells these routes apart.

    The test is that the bearing evidence is not the SAME for all of them. A
    cost that names every route separates none of them; a cost that names one
    does. Nothing is weighed and no route is preferred here - a law may not
    decide which way the evidence points, only whether there is any.
    """
    return len({bearing_evidence(view, i) for i in option_ids}) > 1


def compared_with(view, option_id: str, decision_id: str) -> tuple[str, ...]:
    """The live routes a registered TRADE_OFF weighs against this one."""
    out: list[str] = []
    for t in live(view, Kind.TRADE_OFF):
        if t.payload.decision_id != decision_id or option_id not in t.payload.option_ids:
            continue
        out.extend(i for i in t.payload.option_ids
                   if i != option_id and view.get(i) is not None)
    return tuple(dict.fromkeys(out))


# -- what would settle a decision the analysis could not settle -------------

def settling_records(view, decision_id: str) -> list[str]:
    """The rows that say what would SETTLE this decision, read off typed fields
    only.

    Two shapes qualify. An OPEN QUESTION filed against this decision by a typed
    field and carrying a non-empty `asks_for` - the kind of evidence that would
    settle it. And a live DECISION_REQUIRED or CONFLICT typed to this decision
    that cites such a question, so the blocker and the ask are one record
    rather than two rows that happen to coexist.

    What does NOT qualify: a row that names the decision through
    `derived_from`. Lineage says a row was written after the decision, which
    nearly every row was. It does not say the row is why the decision is
    unanswered.

    This IS S2's `typed_blockers`, delegated rather than restated. It was a
    second copy when S2's own clause read lineage; T4(b) repaired that clause
    where it lives, and keeping a copy here would be how the two came to
    disagree in the first place. The name is kept because T1 and T2 ask what
    would SETTLE a choice, which is the same reading under the name that suits
    the question.
    """
    return typed_blockers(view, decision_id)


# -- T1 ---------------------------------------------------------------------

def advised_route(view, decision_id: str) -> tuple[str | None, str | None]:
    """(option id, mechanism) this engagement advises for the decision."""
    for r in sorted(live(view, Kind.RECOMMENDATION), key=lambda e: e.id):
        if r.payload.decision_id != decision_id or not r.payload.option_id:
            continue
        option = view.get(r.payload.option_id)
        return r.payload.option_id, (option.payload.mechanism if option else None)
    return None, None


def mirror_ignored(left, right, decision_id: str) -> list[str]:
    """T1: two engagements alike in every row but the evidence bearing on their
    routes - each favouring the route the other's evidence disfavours - cannot
    advise the same route.

    The mirror is what lets the law be strict without taking a view on which
    way any evidence points. Whichever reading of a COST and a BENEFIT an
    engine holds, applying it to a registry and to that registry's mirror image
    must give the two answers, not one of them twice. An engine that always
    takes route one gives one answer twice, and that is the only thing this
    fails.
    """
    left_id, left_mech = advised_route(left, decision_id)
    right_id, right_mech = advised_route(right, decision_id)
    if left_id is None and right_id is None:
        if settling_records(left, decision_id) and settling_records(right, decision_id):
            return []
        return ["neither mirrored engagement advised a route and neither recorded what would "
                "settle the choice"]
    if left_id is None or right_id is None:
        return [f"one mirrored engagement advised ({left_id}, {right_id}) and the other did not, "
                "without recording why"]
    if left_id == right_id or left_mech == right_mech:
        return [f"both mirrored engagements advise {left_id} ({left_mech}) / {right_id} "
                f"({right_mech}): the choice did not move when the evidence bearing on the "
                "routes was mirrored"]
    return []


def conclusion_is_a_constant(chosen: Mapping[str, str | None],
                             settling: Mapping[str, Sequence[str]]) -> list[str]:
    """T1 over the population: the mechanism the engine advises is not one
    value for every engagement in the world.

    The disjunction is the honest one. An engine MAY advise the same route
    everywhere - if that is what the evidence said everywhere. What it may not
    do is advise it everywhere while recording nothing about why: an engagement
    whose registry separates nothing and which advises anyway has not concluded
    the same thing fifteen times, it has skipped the question fifteen times.
    """
    taken = {case: mech for case, mech in chosen.items() if mech}
    if len(set(taken.values())) > 1:
        return []
    return [f"{case} advises {mech!r} - the only mechanism any engagement advises - and records "
            "nothing naming the evidence that would settle the choice"
            for case, mech in sorted(taken.items()) if not settling.get(case)]


# -- T2 ---------------------------------------------------------------------

def unsettled_choices(view) -> list[str]:
    """T2, both directions in one reading. For every comparison the engagement
    registered:

      separated  -> a selection may be made (this law says nothing more about
                    it; T1 says the selection must follow the evidence);
      not        -> the engagement must NOT select, and must record what would
                    settle it.

    A consultant who cannot choose says so. The failure this refuses is the one
    that reads identically to advice on the page: a route named, a criterion
    cited, a trade-off cited - and a register that holds not one row saying why
    that route rather than the two beside it.
    """
    out: list[str] = []
    for r in sorted(live(view, Kind.RECOMMENDATION), key=lambda e: e.id):
        # The floor of the same law: a route selected out of no comparison at
        # all. S4 asks for a comparison and accepts one that "discriminates" on
        # a `gives_up` string; this clause asks only that one exist, and the
        # clause below asks whether it separates anything.
        option_id = r.payload.option_id
        if option_id and not compared_with(view, option_id, r.payload.decision_id):
            out.append(f"{r.id} selects {option_id} and no registered comparison weighs it "
                       "against anything")
    for t in sorted(live(view, Kind.TRADE_OFF), key=lambda e: e.id):
        decision_id = t.payload.decision_id
        ids = tuple(i for i in t.payload.option_ids if view.get(i) is not None)
        if len(ids) < 2 or separated(view, ids):
            continue
        picked = [r for r in live(view, Kind.RECOMMENDATION)
                  if r.payload.option_id in ids and r.payload.decision_id == decision_id]
        if picked:
            out.append(f"{picked[0].id} selects {picked[0].payload.option_id} out of "
                       f"{t.id} ({', '.join(ids)}) although nothing this engagement registered "
                       "separates those routes")
        elif not settling_records(view, decision_id):
            out.append(f"{t.id} weighs {', '.join(ids)}, nothing separates them, and no record "
                       f"names the evidence that would settle {decision_id}")
    return out


# -- T3 ---------------------------------------------------------------------

SUBJECT_KINDS: tuple[Kind, ...] = (
    Kind.CAPABILITY, Kind.MEASURE, Kind.STAKEHOLDER, Kind.OBJECTIVE, Kind.PROCESS_STEP,
    Kind.WORKSTREAM, Kind.FACT, Kind.BUSINESS_CONTEXT)

SUBJECT_FIELDS: tuple[str, ...] = ("text", "name", "statement", "definition", "purpose", "interest")


def subject_terms(view) -> set[str]:
    """Every word this engagement used to record what it is ABOUT: its
    capabilities, measures, stakeholders, objectives, steps, workstreams,
    facts, context."""
    out: set[str] = set()
    for kind in SUBJECT_KINDS:
        for e in live(view, kind):
            for field_name in SUBJECT_FIELDS:
                out |= words(getattr(e.payload, field_name, None))
    return out


def distinctive_terms(vocabularies: Mapping[str, set[str]]) -> dict[str, set[str]]:
    """Per engagement, the words no OTHER engagement in the population used.

    This is why no stopword list appears anywhere in this file. "The", "of" and
    "capability" are shared by every engagement and so are distinctive to none;
    "sortation" and "Alcantara" are shared by none and so are distinctive. The
    population does the work a hand-written list of function words would do
    badly, and it does it without anybody deciding which words count.
    """
    out: dict[str, set[str]] = {}
    for case_id, mine in vocabularies.items():
        others: set[str] = set()
        for other_id, theirs in vocabularies.items():
            if other_id != case_id:
                others |= theirs
        out[case_id] = mine - others
    return out


def without_ids(ids: Sequence[str], text: Any) -> str:
    """The text with every id this registry holds struck out of it.

    An id is a pointer to a row, not a word about the client. "CAP-4" tells a
    reader where to look and says nothing about what is there, so nothing an id
    contributes may count as naming the subject - not the id itself, and not
    the letters and digits it decomposes into.
    """
    out = str(text or "")
    for entity_id in ids:
        out = out.replace(entity_id, " ")
    return out


def recorded_wording(entity: Entity) -> list[str]:
    """What a row SAYS, normalised: the fields a payload carries human wording
    in. Edge whitespace and full stops are dropped because punctuation at the
    edge of a sentence is not part of the claim."""
    out: list[str] = []
    for field_name in SUBJECT_FIELDS:
        text = normalised(getattr(entity.payload, field_name, None)).strip().strip(".").strip()
        if text:
            out.append(text)
    return out


def quotes_a_row_it_cites(view, ids: Sequence[str], option: Entity) -> str:
    """T3a's second way, repaired: the route QUOTES a row it names.

    It used to be enough to CONTAIN an id, and that is the vacuity. `named()`
    falls back to the bare id when a capability has no wording of its own, so
    "Stand up CAP-4 with the organisation's own people and systems" - the
    catalogue frame with a registry key in the slot - passed a law written to
    require the subject. A pointer is not content.

    The pointer must now be redeemed: strike every id out of the text, and what
    is left must still carry, character for character, what one of the rows the
    route cites recorded about itself. Exact containment after whitespace and
    case are normalised; no similarity measure is imported here and none may
    be. No length rule either - a law that ignored short wording would be a
    similarity measure with extra steps, and what a row says is what it says.
    """
    said = normalised(without_ids(ids, option.payload.text))
    cited = tuple(option.payload.evidence) + tuple(option.provenance.derived_from)
    for entity_id in dict.fromkeys(cited):
        source = view.get(entity_id)
        if source is None:
            continue
        for wording in recorded_wording(source):
            if wording in said:
                return f"{entity_id}: {wording}"
    return ""


def anonymous_options(view, distinctive: set[str]) -> list[str]:
    """T3a: a route that names nothing of the engagement it is a route in.

    The rule asks for the SUBJECT and nothing else. A route's frame is drawn
    from a closed catalogue and SHOULD be the same words everywhere - "stand up
    ... with the organisation's own people and systems" is a fine and reusable
    sentence, and this law never fails one for being generic. What it fails is
    a route whose whole text is that frame with a catalogue value in the slot,
    because such a route is an answer to a question about a class of
    capability, not about anything this client has.

    Two ways a route can name its subject, both structural, and neither of them
    an id: it uses a word its own engagement used and no other engagement in
    the population did, or it quotes what a row it cites recorded. Both are
    read off the text with the ids struck out, so a registry key can be the
    reason a route passes neither.
    """
    ids = sorted({e.id for e in view.query()}, key=len, reverse=True)
    out: list[str] = []
    for o in sorted(live(view, Kind.OPTION), key=lambda e: e.id):
        text = str(o.payload.text or "")
        if words(without_ids(ids, text)) & distinctive:
            continue
        if quotes_a_row_it_cites(view, ids, o):
            continue
        out.append(f"{o.id} {text[:78]!r} names nothing this engagement recorded")
    return out


def scripted_option_texts(texts_by_case: Mapping[str, set[str]]) -> list[str]:
    """T3b: across the population, route texts scale with the engagements.

    Stated per engagement so the failure names who: each engagement that
    registered routes must contribute at least ONE route text no other
    engagement holds. An engagement all of whose routes are word-for-word
    another engagement's routes has recorded nothing about its own decision,
    however many rows it wrote.

    This is the counting half of T3a and it catches what the per-row half
    cannot: a producer that reads the registry but writes from a catalogue
    saturates at the size of the catalogue no matter how many engagements run,
    so distinct texts stop growing while row counts do not.
    """
    shared: collections.Counter = collections.Counter()
    for case_texts in texts_by_case.values():
        shared.update(case_texts)
    return [f"{case_id}: all {len(case_texts)} of its route texts are held by other engagements too"
            for case_id, case_texts in sorted(texts_by_case.items())
            if case_texts and not any(shared[t] == 1 for t in case_texts)]


# -- T4 ---------------------------------------------------------------------
#
# Nothing is restated here any more. `law_e_as_it_stood` is Law E's own ghost
# and `unconcluded_engagement` is Law E, both imported from the file Law E
# lives in; `lineage_only_blockers` and `typed_blockers` are the same pair for
# S2. T4 measures the repaired laws against the clauses they replaced, on
# fixtures those clauses accept.


# -- T5 ---------------------------------------------------------------------

def unrevised(view, standing: Entity, deltas: Sequence[Any],
              new_evidence: Sequence[str]) -> list[str]:
    """T5: the advice that stood is REVISED - superseded in place, selecting the
    route the new evidence favours, citing that evidence - and not duplicated,
    and not left alone.

    Supersession rather than a second row, because both would be live and both
    would be on the same decision: the reader is handed two answers and told
    they are one conclusion. Lineage rather than a rewritten sentence, because
    a revision that does not cite what changed cannot be audited into the round
    it changed on.
    """
    out: list[str] = []
    revisions = [d for d in deltas if isinstance(d, Supersede) and d.old_id == standing.id]
    additions = [d for d in deltas
                 if isinstance(d, Add) and d.entity.kind is Kind.RECOMMENDATION
                 and d.entity.payload.decision_id == standing.payload.decision_id]
    if not revisions:
        out.append(f"{standing.id} still stands: the evidence moved and the advice did not")
    if additions:
        out.append(f"{len(additions)} second recommendation(s) added beside {standing.id} on "
                   f"{standing.payload.decision_id} instead of superseding it")
    for d in revisions:
        new = d.entity
        if new.payload.option_id == standing.payload.option_id:
            out.append(f"{standing.id} was superseded by advice selecting the same route "
                       f"{new.payload.option_id}: nothing was revised")
        missing = [i for i in new_evidence if i not in new.provenance.derived_from]
        if missing:
            out.append(f"the revision of {standing.id} cites none of {missing}: it does not say "
                       "what changed its mind")
    return out


# -- T6 ---------------------------------------------------------------------

def vanished(offered: Mapping[str, int], retained: Mapping[str, int]) -> list[str]:
    """T6a: every row offered to the registry is still findable in it.

    Counted over EVERY kind, ISSUE included, and against no bound: this asks
    whether what was produced survived, not whether there was too much of it. A
    superseded row keeps its id and is still retained; a row whose status went
    terminal keeps its id and is still retained. Only a batch rolled back
    leaves a row that was offered and is nowhere.
    """
    return [f"{offered[name] - retained.get(name, 0)} of {offered[name]} {name} rows were offered "
            "to the registry and are not in it"
            for name in sorted(offered) if offered[name] > retained.get(name, 0)]


def spent_for_nothing(record: RunRecord) -> str:
    """Why a run produced nothing, or "" when it produced something.

    Two shapes. A run that generated candidates and kept none has thrown away
    everything it made - the findings are its own record of that. A run that
    added nothing, superseded nothing and asked nothing has left the registry
    exactly as it found it, having occupied a selection slot to do so.
    """
    if record.added or record.superseded:
        return ""
    if record.discarded:
        return ("generated {} row(s) and kept none".format(record.discarded)
                + (", spending {} model call(s)".format(record.model_calls)
                   if record.model_calls else ""))
    if not record.questions:
        return ("added nothing, superseded nothing and asked nothing"
                + (", spending {} model call(s)".format(record.model_calls)
                   if record.model_calls else ""))
    return ""


def wasted_runs(records: Sequence[RunRecord]) -> tuple[list[str], list[str], list[str]]:
    """T6b and T6c: (runs that threw away everything they generated, runs that
    left the registry untouched, runs of a method that had already kept
    nothing).

    The first two are separated because they are different failures with
    different fixes. A run that generated fifteen nodes and refused all fifteen
    spent a model call to learn something the registry could have told it; a
    run that generated nothing at all spent a selection slot on a node it could
    not advance. Both are work with no output, and only the first is
    generate-and-discard.

    The third is the one the brief names: a method must not be run again once
    its output would be discarded. The first run that keeps nothing is
    information the engine now has; running the same method again spends
    another selection slot, and for a model-assisted method another model call,
    on an outcome already observed.
    """
    discarded: list[str] = []
    inert: list[str] = []
    repeated: list[str] = []
    exhausted: set[str] = set()
    for n, record in enumerate(records, start=1):
        why = spent_for_nothing(record)
        if record.method_id in exhausted:
            repeated.append("run {}: {} ran again after a run of it kept nothing{}".format(
                n, record.method_id, " ({})".format(why) if why else ""))
        if why:
            (discarded if record.discarded else inert).append(
                "run {}: {} {}".format(n, record.method_id, why))
            exhausted.add(record.method_id)
    return discarded, inert, repeated


# ===========================================================================
# 2. Hand-built engagements. Every negative control is one of these, run
#    through the SAME function the law runs over the benchmark.
# ===========================================================================

def row(kind, payload, *, eid, actor=Actor.PARTNER, status=Status.PROPOSED, derived=(),
        decision_id="DEC-1", weight=0.5, relation=RelationToCentralDecision.INFORMS) -> Entity:
    return make_entity(
        kind=kind, engagement_id="E-1", payload=payload,
        provenance=Provenance(actor=actor, actor_ref="{}:1".format(actor.value),
                              derived_from=tuple(derived), source_locator=None,
                              recorded_at=FIXED_CLOCK),
        confidence=Confidence(None), relevance=Relevance(decision_id, weight),
        relation=relation, status=status, entity_id=eid)


def build(rows: Iterable[Entity]) -> EngagementRegistry:
    return EngagementRegistry.from_rows("E-1", list(rows), clock=lambda: FIXED_CLOCK)


DEPOT_SENTENCE = "we move 4200 parcels a week out of the northern depots"


def depot_rows() -> list[Entity]:
    """One decision, one capability gap, two routes to it, a criterion the
    client weighted, and a comparison. Deliberately WITHOUT any evidence that
    bears on one route rather than the other - the mirror fixtures add that,
    one way round each, and nothing else differs between them."""
    return [
        row(Kind.DECISION, DecisionPayload(statement="whether to consolidate the depots",
                                           role=DecisionRole.CENTRAL), eid="DEC-1"),
        row(Kind.MEASURE, MeasurePayload(name="weekly parcel volume", unit_family=UnitFamily.COUNT,
                                         definition="parcels leaving the northern depots in a week"),
            eid="MEA-1", actor=Actor.CLIENT, derived=("DEC-1",)),
        row(Kind.FACT, FactPayload(statement=DEPOT_SENTENCE, basis=FactBasis.CLIENT_STATED,
                                   measure_id="MEA-1"),
            eid="FCT-1", actor=Actor.CLIENT, status=Status.CONFIRMED, derived=("DEC-1", "MEA-1")),
        row(Kind.CAPABILITY, CapabilityPayload(text="a single northern sortation line",
                                               capability_class=CapabilityClass.PROCESS,
                                               gap=GapState.MISSING, evidence=("FCT-1",)),
            eid="CAP-1", derived=("FCT-1",)),
        row(Kind.OPTION, OptionPayload(text="Stand up the northern sortation line with the "
                                            "organisation's own people and systems",
                                       decision_id="DEC-1", mechanism="make", evidence=("CAP-1",)),
            eid="OPT-1", derived=("CAP-1",), relation=RelationToCentralDecision.RESOLVES),
        row(Kind.OPTION, OptionPayload(text="Obtain the northern sortation line as a supplied "
                                            "product or service",
                                       decision_id="DEC-1", mechanism="buy", evidence=("CAP-1",)),
            eid="OPT-2", derived=("CAP-1",), relation=RelationToCentralDecision.RESOLVES),
        row(Kind.EVALUATION_CRITERION, EvaluationCriterionPayload(
            text="peak week throughput", decision_id="DEC-1", weight=0.7,
            weight_set_by=Authority.CLIENT), eid="CRI-1", derived=("DEC-1",)),
        row(Kind.TRADE_OFF, TradeOffPayload(
            decision_id="DEC-1", option_ids=("OPT-1", "OPT-2"),
            gives_up="these routes are alternatives: taking any one of OPT-1, OPT-2 declines the rest",
            gains="", scores=()),
            eid="TRD-1", derived=("CAP-1", "OPT-1", "OPT-2"),
            relation=RelationToCentralDecision.RESOLVES),
    ]


def cost_on(option_id: str, eid: str) -> Entity:
    return row(Kind.COST, CostPayload(text="a second night shift is needed to take {}".format(option_id),
                                      basis="client_fact", for_ids=(option_id,)),
               eid=eid, derived=(option_id, "FCT-1"))


def benefit_on(option_id: str, eid: str) -> Entity:
    return row(Kind.BENEFIT, BenefitPayload(text="peak week capacity rises on {}".format(option_id),
                                            basis="client_fact", for_ids=(option_id,)),
               eid=eid, derived=(option_id, "FCT-1"))


def recommendation_for(option_id: str, eid: str, *, statement: str, cites=()) -> Entity:
    return row(Kind.RECOMMENDATION,
               RecommendationPayload(statement=statement, decision_id="DEC-1",
                                     option_id=option_id, supports=("FCT-1",)),
               eid=eid, derived=(option_id, "DEC-1", "TRD-1", "CRI-1", "FCT-1") + tuple(cites),
               relation=RelationToCentralDecision.RESOLVES)


def mirror_pair() -> tuple[list[Entity], list[Entity]]:
    """Two engagements identical row for row, id for id, word for word - except
    that the BENEFIT names OPT-1 and the COST names OPT-2 in one, and the other
    way round in the other."""
    left = depot_rows() + [benefit_on("OPT-1", "BEN-1"), cost_on("OPT-2", "COS-1")]
    right = depot_rows() + [cost_on("OPT-1", "COS-1"), benefit_on("OPT-2", "BEN-1")]
    return left, right


def settling_question(eid: str = "QST-1") -> Entity:
    """The record a consultant who cannot choose leaves: an open question typed
    to the decision it blocks, naming the KIND of evidence that would settle
    it."""
    return row(Kind.QUESTION, QuestionPayload(
        text="Which of your records gives the cost of running the sortation line in house "
             "against the supplier's quote?",
        asks_for=(AsksFor(Kind.COST),), material=True,
        why="nothing registered separates the two routes, so neither can be advised",
        effort=EffortClass.LOOKUP, strategy=FillStrategy.ASK_CLIENT),
        eid=eid, status=Status.OPEN, derived=("DEC-1", "TRD-1"))


def declared_standoff() -> list[Entity]:
    """The unseparated engagement, done right: no advice, the question that
    would settle it typed to the decision, and the blocker citing that
    question."""
    rows = depot_rows() + [settling_question()]
    rows.append(row(Kind.DECISION_REQUIRED, DecisionRequiredPayload(
        text="DEC-1 is unsettled by this analysis: nothing registered separates the two routes",
        from_authority=Authority.DECISION_OWNER, decision_id="DEC-1",
        options=("OPT-1", "OPT-2")),
        eid="DRQ-1", status=Status.OPEN, derived=("DEC-1", "QST-1", "OPT-1", "OPT-2"),
        relation=RelationToCentralDecision.RESOLVES))
    return rows


BAKERY_SENTENCE = "the proving room holds 18 trolleys and the ovens want 26 an hour"


def bakery_rows() -> list[Entity]:
    """A second engagement, sharing no subject vocabulary with the depots, so
    the population `distinctive_terms` reads is a real population of two."""
    return [
        row(Kind.DECISION, DecisionPayload(statement="whether to add a second proving room",
                                           role=DecisionRole.CENTRAL), eid="DEC-1"),
        row(Kind.FACT, FactPayload(statement=BAKERY_SENTENCE, basis=FactBasis.CLIENT_STATED),
            eid="FCT-1", actor=Actor.CLIENT, status=Status.CONFIRMED, derived=("DEC-1",)),
        row(Kind.CAPABILITY, CapabilityPayload(text="proving capacity matched to oven throughput",
                                               capability_class=CapabilityClass.PROCESS,
                                               gap=GapState.PARTIAL, evidence=("FCT-1",)),
            eid="CAP-1", derived=("FCT-1",)),
        row(Kind.OPTION, OptionPayload(
            text="Stand up proving capacity matched to oven throughput with the organisation's "
                 "own people and systems",
            decision_id="DEC-1", mechanism="make", evidence=("CAP-1",)),
            eid="OPT-1", derived=("CAP-1",), relation=RelationToCentralDecision.RESOLVES),
    ]


def advise(rows: Sequence[Entity]) -> EngagementRegistry:
    """Run the real producer over a registry and keep what it wrote, so the law
    reads a registry and not a delta list. Nothing is monkeypatched: this is
    the method the engine runs, run as the engine runs it."""
    reg = build(rows)
    result = RecommendationMethod().run(MethodContext(
        registry=reg, provider=None, calc=None, actor=Actor.METHOD,
        actor_ref="method:recommendation@1", issue_ids=(), settings={}))
    reg.apply_all(result.deltas)
    return reg


# ===========================================================================
# T1 - the choice follows the evidence
# ===========================================================================

def test_t1_the_choice_moves_when_the_evidence_bearing_on_the_routes_moves(runs):
    """T1. Two halves.

    The differential: two registries alike in every row but the BENEFIT and the
    COST, which name OPT-1 and OPT-2 in one and OPT-2 and OPT-1 in the other,
    must not receive the same advice. The mirror is what lets the law be strict
    without taking a view: no reading of a cost and a benefit gives the same
    answer to a registry and to its mirror image.

    The population: over the fifteen engagements the advised mechanism is not
    one value for all of them - unless every engagement that advises it also
    recorded what would settle the choice, which is the only honest way the
    same route can be right everywhere.

    mutation caught: `selected_route` returns the first entry of `option_ids`
    whose lineage reaches a support, and `option_ids` is registration order.
    Change the tuple order and the answer changes; change the evidence and it
    does not. That is an ordering, presented as a conclusion.
    """
    # NEGATIVE CONTROL: the same function over two engagements whose advice
    # DOES track the mirrored evidence. The law is satisfiable, and satisfiable
    # on registries this engine's own kinds can express.
    left_rows, right_rows = mirror_pair()
    sound_left = build(left_rows + [recommendation_for(
        "OPT-1", "REC-1", statement="Stand up the line in house rather than buying it in: it is "
                                    "the route peak week capacity rises on.", cites=("BEN-1",))])
    sound_right = build(right_rows + [recommendation_for(
        "OPT-2", "REC-1", statement="Buy the line in rather than standing it up: it is the route "
                                    "that does not want a second night shift.", cites=("BEN-1",))])
    assert mirror_ignored(sound_left, sound_right, "DEC-1") == [], \
        "advice that tracks the mirrored evidence passes this law"
    # ... and so does an engine that declined both times and said why both times.
    silent = build(depot_rows() + [settling_question()])
    assert mirror_ignored(silent, silent, "DEC-1") == [], \
        "declining twice, with the ask recorded twice, is a conclusion about the engagement"

    # The engine, on the mirror.
    differential = mirror_ignored(advise(left_rows), advise(right_rows), "DEC-1")

    # The engine, over the population.
    chosen: dict[str, str | None] = {}
    settling: dict[str, list[str]] = {}
    for run in runs.values():
        decision = central(run.registry)
        if decision is None:
            continue
        chosen[run.case_id] = advised_route(run.registry, decision.id)[1]
        settling[run.case_id] = settling_records(run.registry, decision.id)
    population = conclusion_is_a_constant(chosen, settling)

    assert differential == [] and population == [], (
        "the engine does not choose; it takes route one:\n"
        + "\n".join("  mirror: {}".format(why) for why in differential)
        + ("\n" if differential and population else "")
        + "\n".join("  {}".format(why) for why in population)
        + "\n  advised mechanisms over the suite: {}".format(
            collections.Counter(m for m in chosen.values() if m)))


# ===========================================================================
# T2 - an unseparated choice is declared, not taken
# ===========================================================================

def test_t2_a_choice_nothing_separates_is_declared_and_not_taken(runs):
    """T2. For every comparison an engagement registered, either something it
    holds tells the routes apart - a COST, BENEFIT, RISK, CONSTRAINT or
    CRITERION bearing on one and not another, or scores that differ - and a
    route may be selected; or nothing does, and the engagement must record what
    would settle it and select nothing.

    The oracle is case-blind and cannot know which route is better. That is not
    a licence to take the first one. It is the reason the second branch exists:
    an engagement that cannot separate its routes has a true and useful thing to
    say, and saying it is the work.

    mutation caught: read `gives_up` as a comparison. `make_buy_partner` writes
    "these routes are alternatives: taking any one of OPT-1, OPT-2 declines the
    rest" whenever no COST names them, which is true, is not a separation, and
    is enough to satisfy every existing check that a comparison discriminates.
    """
    # NEGATIVE CONTROL 1: a comparison that genuinely separates - a scored
    # trade-off - carries a selection without complaint.
    scored = [r for r in depot_rows() if r.id != "TRD-1"]
    scored.append(row(Kind.TRADE_OFF, TradeOffPayload(
        decision_id="DEC-1", option_ids=("OPT-1", "OPT-2"),
        gives_up="the supplier relationship the client already has",
        gains="control of the peak week roster",
        scores=(Score("OPT-1", "CRI-1", Decimal("0.8"), ("FCT-1",)),
                Score("OPT-2", "CRI-1", Decimal("0.4"), ("FCT-1",)))),
        eid="TRD-1", derived=("CAP-1", "OPT-1", "OPT-2"),
        relation=RelationToCentralDecision.RESOLVES))
    scored.append(recommendation_for("OPT-1", "REC-1",
                                     statement="Stand up the line in house: it leads on peak week "
                                               "throughput and gives up the supplier relationship."))
    assert unsettled_choices(build(scored)) == [], \
        "a selection out of a comparison that separates the routes is a conclusion"
    # NEGATIVE CONTROL 2: the unseparated engagement that declared itself.
    assert unsettled_choices(build(declared_standoff())) == [], \
        "declining to choose, with what would settle it recorded, is the other lawful answer"
    # ... and the same rows WITHOUT the declaration are refused, so control 2 is
    # passing on the declaration and not on the absence of advice.
    assert unsettled_choices(build(depot_rows())), \
        "silence on an unseparated choice is not the same as declaring it"

    offending = {run.case_id: unsettled_choices(run.registry) for run in runs.values()}
    offending = {case: why for case, why in offending.items() if why}
    assert offending == {}, (
        "a route was selected where nothing the engagement registered separates the routes:\n"
        + "\n".join("  {}: {} comparison(s), e.g. {}".format(case, len(why), why[0])
                    for case, why in sorted(offending.items())))


# ===========================================================================
# T3 - options carry this engagement
# ===========================================================================

def test_t3_a_route_names_the_subject_this_engagement_recorded(runs):
    """T3. Two halves, and both are about the SUBJECT, never about the frame.

    Per route: its text, with the registry ids struck out of it, must use a word
    its own engagement used and no other engagement in the population did, or
    quote what a row it cites recorded about itself.

    Per population: every engagement that registered routes must contribute at
    least one route text no other engagement holds.

    A legitimately generic option is not failed by either half, and the
    negative control proves it: a route whose frame is the production
    catalogue's own sentence, word for word, passes as soon as the slot in it
    holds this engagement's capability rather than the name of a class of
    capability.

    AN ID IS NOT CONTENT, and that clause is the repair. This law used to
    accept any route text CONTAINING an id the registry holds - and `named()`
    falls back to the bare id when a capability has no wording, so "Stand up
    CAP-4 with the organisation's own people and systems" was a route that
    named its subject as far as the law could see. The third control below is
    that sentence: the clause as it stood passes it, the clause as repaired
    fails it, and the two other controls show the repair did not simply turn
    the second way off - 20 of the suite's routes still pass on it, by quoting
    the capability they cite.

    mutation caught: name the sourcing subject from `CapabilityClass` instead
    of from the CAPABILITY. Every count in the suite stays healthy - 318 routes
    across fifteen engagements, three to every open gap, none refused - and the
    318 rows carry 27 sentences between them, which is 9 classes x 3 routes and
    is a number about the enum, not about any client. And: fall back to the id
    for the subject, which is the same defect written as a producer instead of
    as a law.
    """
    catalogue_frame = "Stand up {what} with the organisation's own people and systems"

    # NEGATIVE CONTROL: the catalogue frame, filled with the engagement's own
    # capability, in a population of two engagements that share no subject
    # words. The law passes generic wording; it fails a generic subject.
    named = [r for r in depot_rows() if r.id != "OPT-1"]
    named.insert(4, row(Kind.OPTION, OptionPayload(
        text=catalogue_frame.format(what="a single northern sortation line"),
        decision_id="DEC-1", mechanism="make", evidence=("CAP-1",)),
        eid="OPT-1", derived=("CAP-1",), relation=RelationToCentralDecision.RESOLVES))
    depots, bakery = build(named), build(bakery_rows())
    pair = distinctive_terms({"depots": subject_terms(depots), "bakery": subject_terms(bakery)})
    assert anonymous_options(depots, pair["depots"]) == [], \
        "a catalogue frame around this engagement's own capability names its subject"
    assert scripted_option_texts(
        {"depots": {normalised(o.payload.text) for o in live(depots, Kind.OPTION)},
         "bakery": {normalised(o.payload.text) for o in live(bakery, Kind.OPTION)}}) == [], \
        "two engagements whose routes name their own subjects each contribute a text of their own"
    # ... and the same frame filled with the CLASS name is refused, so the
    # control is passing on the subject and not on the frame.
    classed = [r for r in depot_rows() if r.id != "OPT-1"]
    classed.insert(4, row(Kind.OPTION, OptionPayload(
        text=catalogue_frame.format(what="the process capability"),
        decision_id="DEC-1", mechanism="make", evidence=("CAP-1",)),
        eid="OPT-1", derived=("CAP-1",), relation=RelationToCentralDecision.RESOLVES))
    assert anonymous_options(build(classed), pair["depots"]), \
        "the same frame with a class name in the slot names nothing"

    # THE REPAIR, PROVED. The same frame with the bare id of the capability in
    # the slot - what `named()` writes when a capability has no wording of its
    # own. The clause this law used to carry passes it on the id alone; the
    # repaired clause fails it, because striking the id out leaves the frame
    # and nothing the cited row ever said.
    keyed = [r for r in depot_rows() if r.id != "OPT-1"]
    keyed.insert(4, row(Kind.OPTION, OptionPayload(
        text=catalogue_frame.format(what="CAP-1"),
        decision_id="DEC-1", mechanism="make", evidence=("CAP-1",)),
        eid="OPT-1", derived=("CAP-1",), relation=RelationToCentralDecision.RESOLVES))
    keyed_view = build(keyed)
    keyed_text = keyed_view.get("OPT-1").payload.text
    keyed_ids = sorted({e.id for e in keyed_view.query()}, key=len, reverse=True)
    assert normalised(without_ids(keyed_ids, keyed_text)) == \
        "stand up with the organisation's own people and systems", \
        "striking the ids out of that route leaves the catalogue frame and nothing else"
    assert not words(keyed_text) & pair["depots"], (
        "the fixture names no distinctive word, so it is the id clause and only the id clause "
        "that ever passed it")
    assert any(e.id in keyed_text for e in keyed_view.query()), \
        "T3a as it stood: a route names its subject if its text contains ANY id the registry holds"
    assert anonymous_options(keyed_view, pair["depots"]) == [
        "OPT-1 {!r} names nothing this engagement recorded".format(keyed_text[:78])], \
        "the repaired clause refuses it: a pointer to a row is not what the row says"
    # ... and the repair did not simply turn the second way off: the same frame
    # around the same id, with the capability's own wording beside it, quotes
    # the row it cites and passes.
    quoted = [r for r in depot_rows() if r.id != "OPT-1"]
    quoted.insert(4, row(Kind.OPTION, OptionPayload(
        text=catalogue_frame.format(what="a single northern sortation line (CAP-1)"),
        decision_id="DEC-1", mechanism="make", evidence=("CAP-1",)),
        eid="OPT-1", derived=("CAP-1",), relation=RelationToCentralDecision.RESOLVES))
    assert not [why for why in anonymous_options(build(quoted), set()) if why.startswith("OPT-1 ")], \
        "a route that quotes what the row it cites recorded names its subject, id or no id"

    vocabularies = {run.case_id: subject_terms(run.registry) for run in runs.values()}
    distinctive = distinctive_terms(vocabularies)
    assert all(distinctive.values()), \
        "every engagement uses words no other uses, so the law is not asking for the impossible"

    texts = {run.case_id: {normalised(o.payload.text) for o in live(run.registry, Kind.OPTION)}
             for run in runs.values()}
    total = sum(len(live(run.registry, Kind.OPTION)) for run in runs.values())
    anonymous = {run.case_id: anonymous_options(run.registry, distinctive[run.case_id])
                 for run in runs.values()}
    anonymous = {case: why for case, why in anonymous.items() if why}
    scripted = scripted_option_texts(texts)

    assert anonymous == {} and scripted == [], (
        "{} of {} routes across the suite name nothing of the engagement they are a route in, "
        "and the {} rows carry {} distinct sentences between {} engagements:\n".format(
            sum(len(v) for v in anonymous.values()), total, total,
            len({t for case_texts in texts.values() for t in case_texts}),
            len([c for c, v in texts.items() if v]))
        + "\n".join("  {}: {} route(s), e.g. {}".format(case, len(why), why[0])
                    for case, why in sorted(anonymous.items()))
        + ("\n" if anonymous and scripted else "")
        + "\n".join("  {}".format(why) for why in scripted))


# ===========================================================================
# T4 - no vacuous law
# ===========================================================================

def test_t4a_law_e_measures_a_conclusion_and_not_a_non_empty_kind(runs, core_ids):
    """T4(a). Law E used to pass when ANY of OPTION, RECOMMENDATION or
    CAPABILITY was non-empty. Repaired, in the file it lives in: a core
    engagement that reached synthesis holds a live RECOMMENDATION on its
    central decision, or a record naming the evidence that would settle it.

    The proof that the repair has teeth is the fixture below: an engagement
    holding routes and a capability gap and no conclusion at all passes the law
    as it stood and fails the law as it now stands - and BOTH predicates are
    imported from Law E's own file, so this test cannot be green against a
    restatement that has drifted from the tree.

    mutation caught: restore the disjunction, or add back any exemption by run
    count. The disjunction is satisfied by the first producer that runs, and a
    run-count floor reads a number about the ENGINE to excuse a hole in what the
    CLIENT got.
    """
    # The fixture the old law passes and the repaired one fails: routes on the
    # table, a gap found, nothing concluded and nothing asked.
    thin = build(depot_rows())
    assert law_e_as_it_stood(thin), \
        "Law E as it stood passes this engagement: it holds OPTIONs and a CAPABILITY"
    assert unconcluded_engagement(thin), \
        "the repaired law must fail the same engagement, or the repair changed nothing"

    # NEGATIVE CONTROL 1: the engagement that concluded.
    concluded = depot_rows() + [benefit_on("OPT-1", "BEN-1"), cost_on("OPT-2", "COS-1")]
    concluded.append(recommendation_for("OPT-1", "REC-1",
                                        statement="Stand up the line in house rather than buying "
                                                  "it in.", cites=("BEN-1",)))
    assert unconcluded_engagement(build(concluded)) == []
    # NEGATIVE CONTROL 2: the engagement that concluded nothing and said what
    # would settle it. Both are conclusions ABOUT the decision.
    assert unconcluded_engagement(build(declared_standoff())) == []

    judged = 0
    problems: dict[str, list[str]] = {}
    for run in sorted(runs.values(), key=lambda r: r.case_id):
        if run.case_id not in core_ids or run.phase != Phase.SYNTHESIS.value:
            continue
        if not run.registry.live(Kind.CHARTER):
            continue
        judged += 1
        why = unconcluded_engagement(run.registry)
        if why:
            problems[run.case_id] = why
    assert judged >= 2, "only {} core engagements were judged; the law would be vacuous".format(judged)
    assert problems == {}, (
        "a core engagement reached synthesis owing a conclusion about its own decision:\n"
        + "\n".join(
            "  {}: {} (live OPTION {}, CAPABILITY {} - which is why Law E as it stood passed it)"
            .format(case, "; ".join(why), len(runs[case].registry.live(Kind.OPTION)),
                    len(runs[case].registry.live(Kind.CAPABILITY)))
            for case, why in sorted(problems.items())))


def test_t4a_law_e_in_the_tree_is_the_repaired_law_and_not_the_ghost():
    """T4(a), the repair pinned where it was made.

    This test used to pin the RESTATEMENT: it read Law E's source and checked
    that the disjunction quoted here was still the one in the tree. The
    disjunction is gone from the tree - repaired, not shadowed - so the pin
    reverses. What it holds down now is that Law E is not counted back into
    vacuity: the kind-counting predicate must not be what the law reads, and
    the law must be reading a conclusion about the decision.

    Both halves matter. The source half catches a revert by copy-paste; the
    behavioural half catches a revert by rewording, because a Law E that
    accepted an engagement holding routes and no conclusion would fail here
    whatever its source said.
    """
    source = (pathlib.Path(__file__).parent / "test_engine_analysis_quality.py").read_text(
        encoding="utf-8")
    for ghost in ("conclusion_kinds = (Kind.OPTION, Kind.RECOMMENDATION, Kind.CAPABILITY)",
                  "if not any(counts.values()):"):
        offending = [line for line in source.splitlines()
                     if ghost in line and not line.lstrip().startswith(("#", "*", '"', "'"))]
        assert offending == [], (
            "Law E is counting kinds again: {!r} is back in the law's own source".format(ghost))
    assert "unconcluded_engagement(registry)" in source, \
        "Law E no longer reads the predicate that asks what the engagement concluded"

    thin = build(depot_rows())
    assert law_e_as_it_stood(thin) and unconcluded_engagement(thin), \
        "the law in the tree accepts an engagement holding routes and no conclusion at all"


def test_t4b_a_blocker_names_the_missing_evidence_and_not_only_the_decision(runs):
    """T4(b). S2's `typed_blockers` used to accept any OPEN QUESTION that
    `names_decision` - and `names_decision` counted a mention in `derived_from`,
    which nearly every row in an engagement carries. It has been repaired where
    it lives: a blocker must be filed against the decision by a typed field AND
    name, in `asks_for`, the kind of evidence that would settle it.

    The fixture below is the engagement that separates the two: it concluded
    nothing and holds one open question about who signs the leases, which
    happens to cite the decision in its lineage. Both predicates run on the
    SAME registry, and both are imported from S2's own file - the clause as it
    stood and the clause as repaired - so this is a comparison of two laws in
    the tree, not of a law with a restatement of it.

    The LAW is the last block, over the population, and it is two-sided because
    either side alone can be satisfied by a law that says nothing. The repair
    must REFUSE rows the old clause accepted, in real engagements and not only
    in the fixture; and every engagement must still hold a blocker that names
    what it is waiting for, or the repair would be strictness bought by making
    the law unpassable.

    mutation caught: widen the repaired predicate back to `derived_from`, or
    drop the `asks_for` clause. Either restores a blocker that says a decision
    is unanswered without saying what would answer it.
    """
    unrelated = row(Kind.QUESTION, QuestionPayload(
        text="Who signs off the depot lease renewals?",
        asks_for=(AsksFor(Kind.DECISION_OWNER),),
        why="the lease owner is not recorded",
        effort=EffortClass.OFFHAND, strategy=FillStrategy.ASK_CLIENT),
        # `decision_id=None` is not a contrivance: `Relevance.decision_id` is
        # documented as "the DECISION this bears on (None == not yet
        # attached)", and a question the engine has not attached carries
        # nothing else. The lineage link below is the only thing that ties this
        # question to DEC-1, and it is what S2's clause used to read.
        eid="QST-1", status=Status.OPEN, derived=("DEC-1",), decision_id=None, weight=0.0)
    view = build(depot_rows() + [unrelated])

    assert lineage_only_blockers(view, "DEC-1") == ["QST-1"], \
        "the clause S2 used to read accepts a question that names the decision in its lineage"
    assert typed_blockers(view, "DEC-1") == [], \
        "the repaired clause refuses it: nothing on that row says what would settle DEC-1"
    assert s2_unconcluded(view), \
        "so S2 now reports this engagement as having concluded nothing and said nothing"
    assert unconcluded_engagement(view), \
        "and Law E, reading the same predicate, reports it as owing a conclusion"

    # NEGATIVE CONTROL: the same shape of engagement with a question typed to
    # the decision and naming the kind of evidence that would settle it. The
    # repaired predicate accepts it, so the law is strict and not unsatisfiable.
    declared = build(declared_standoff())
    assert typed_blockers(declared, "DEC-1") == ["QST-1", "DRQ-1"]
    assert s2_unconcluded(declared) == []
    assert unconcluded_engagement(declared) == []

    # THE LAW, over the population, in two directions. Wherever the old clause
    # found a blocker the repaired one must find one too - a blocker is judged
    # on what it SAYS, never on how many there are. And somewhere in the
    # population the repair must actually refuse a row, or the two clauses are
    # one law under two names and nothing was repaired.
    thin: dict[str, str] = {}
    refused: dict[str, list[str]] = {}
    for run in runs.values():
        decision = central(run.registry)
        if decision is None:
            continue
        accepted = lineage_only_blockers(run.registry, decision.id)
        kept = typed_blockers(run.registry, decision.id)
        if sorted(set(accepted) - set(kept)):
            refused[run.case_id] = sorted(set(accepted) - set(kept))
        if accepted and not kept:
            opens = list(run.registry.query(Kind.QUESTION, status=Status.OPEN))
            attached = sum(1 for q in opens if q.relevance.decision_id == decision.id)
            thin[run.case_id] = (
                "the old clause accepts {} row(s) as the reason {} is unanswered; none of them "
                "names what would settle it, and {} of the {} open questions is attached to {} "
                "by a typed field"
                .format(len(accepted), decision.id, attached, len(opens), decision.id))
    assert thin == {}, (
        "S2's second branch is satisfied by rows that say a decision is unanswered without saying "
        "what would answer it:\n"
        + "\n".join("  {}: {}".format(case, why) for case, why in sorted(thin.items())))
    assert refused, (
        "the repair refuses nothing anywhere in the benchmark: every row the old clause accepted "
        "the repaired one accepts too, so the repair is a wording change")


# ===========================================================================
# T5 - advice is revisable
# ===========================================================================

def test_t5_evidence_arriving_after_the_advice_revises_it():
    """T5. An engagement advises OPT-1 on the evidence it had. A COST then lands
    on OPT-1 and a BENEFIT on OPT-2 - the mirror of what was there. The live
    advice must move: superseded in place, selecting the other route, citing the
    rows that changed it.

    Supersession and not a second row, because two live recommendations on one
    decision hand the reader the decision back. Citation and not a rewritten
    sentence, because a revision that does not name what changed cannot be
    audited into the round it changed on.

    mutation caught: `if any(r.payload.decision_id == decision.id ...): return
    MethodResult()`. As a guard against restating the same advice twice it is
    right; as the whole treatment of an engagement that already advised, it
    makes the first conclusion the last one, and every fact the client sends
    afterwards unusable.
    """
    rows = depot_rows() + [
        recommendation_for("OPT-1", "REC-1",
                           statement="Stand up the line in house rather than buying it in."),
        cost_on("OPT-1", "COS-1"), benefit_on("OPT-2", "BEN-1"),
    ]
    view = build(rows)
    standing = view.get("REC-1")
    assert separated(view, ("OPT-1", "OPT-2")), \
        "the new rows really do separate the routes, and the other way from the standing advice"

    # NEGATIVE CONTROL 1: the deltas a producer that revises would emit. The
    # same function passes them, so the law is satisfiable in this engine's own
    # delta vocabulary.
    revised = Supersede("REC-1", row(
        Kind.RECOMMENDATION,
        RecommendationPayload(statement="Buy the line in rather than standing it up: the in-house "
                                        "route now wants a second night shift.",
                              decision_id="DEC-1", option_id="OPT-2", supports=("FCT-1",)),
        eid="REC-1", derived=("OPT-2", "DEC-1", "TRD-1", "CRI-1", "FCT-1", "COS-1", "BEN-1"),
        relation=RelationToCentralDecision.RESOLVES))
    assert unrevised(view, standing, (revised,), ("COS-1", "BEN-1")) == []
    # NEGATIVE CONTROL 2: a second recommendation beside the first is NOT a
    # revision, and the same function says so - the control is passing on the
    # supersession, not on any delta at all.
    duplicated = Add(recommendation_for("OPT-2", "REC-2", statement="Buy the line in.",
                                        cites=("COS-1", "BEN-1")))
    assert unrevised(view, standing, (duplicated,), ("COS-1", "BEN-1"))

    result = RecommendationMethod().run(MethodContext(
        registry=view, provider=None, calc=None, actor=Actor.METHOD,
        actor_ref="method:recommendation@1", issue_ids=(), settings={}))
    why = unrevised(view, standing, result.deltas, ("COS-1", "BEN-1"))

    # NEGATIVE CONTROL 3, on the ENGINE and not on the checker: with NOTHING
    # new, the same run must leave the advice alone. This law is not "rewrite
    # every round"; it is "move when the evidence moves".
    quiet = build(depot_rows() + [
        recommendation_for("OPT-1", "REC-1",
                           statement="Stand up the line in house rather than buying it in.")])
    unchanged = RecommendationMethod().run(MethodContext(
        registry=quiet, provider=None, calc=None, actor=Actor.METHOD,
        actor_ref="method:recommendation@1", issue_ids=(), settings={}))
    assert unchanged.deltas == (), \
        "an unchanged registry must draw no revision, or the law would be asking for churn"

    assert why == [], (
        "the advice is frozen: evidence that arrived after it cannot reach it:\n"
        + "\n".join("  {}".format(line) for line in why)
        + "\n  the run returned {} delta(s) and {} question(s)".format(
            len(result.deltas), len(result.questions)))


# ===========================================================================
# T6 - no generate-and-discard anywhere, ISSUE included
# ===========================================================================

def test_t6_nothing_is_generated_and_thrown_away(runs):
    """T6. Four clauses over every kind, ISSUE included, and against no bound.

      (a) every row offered to the registry is still findable in it;
      (b) no run throws away everything it generated;
      (c) no run leaves the registry exactly as it found it;
      (d) no method is run again after a run of it kept nothing.

    Clause (a) is the S1 instrument, widened from one list of kinds to every
    kind and from a ceiling to a conservation law. It is SATISFIED today, and it
    is here because it is what will fail first if the generation defect returns
    at the registry door - and because it is what makes the other three
    necessary rather than redundant. The door sees a clean sheet while the waste
    happens upstream of it: `apply_all` rolls a refused batch back before
    anything is counted, and a run discarded inside the method never reaches the
    door at all. `issue_tree` is the case in point - it is not among the kinds
    S1 rations, and it runs up to five times an engagement, spending a model
    call each time and keeping nothing after the first.

    mutation caught: measure the waste at the registry. Every count goes green
    and the model calls are still spent writing nothing.
    """
    # NEGATIVE CONTROL: a legitimate run sequence. A method that keeps some of
    # what it generates is not failed for refusing the rest; a method that runs
    # twice and keeps rows both times is not failed for running twice; a run
    # that asks instead of writing has done work; and the FIRST run that keeps
    # nothing is not itself a repeat.
    sound = (
        RunRecord("issue_tree", added=7, superseded=0, questions=0, discarded=2, model_calls=1),
        RunRecord("capability_gap", added=4, superseded=0, questions=1, discarded=9, model_calls=1),
        RunRecord("issue_tree", added=3, superseded=1, questions=0, discarded=5, model_calls=1),
        RunRecord("option_evaluation", added=0, superseded=0, questions=6, discarded=0, model_calls=0),
        RunRecord("recommendation", added=1, superseded=0, questions=0, discarded=0, model_calls=0),
    )
    assert wasted_runs(sound) == ([], [], []), \
        "keeping some of what a run generates, and asking instead of writing, are both work"
    assert vanished({"ISSUE": 10, "OPTION": 3}, {"ISSUE": 10, "OPTION": 3}) == []
    assert vanished({"ISSUE": 10}, {"ISSUE": 7}), \
        "and the conservation clause does see a row that was offered and is gone"

    lost: dict[str, list[str]] = {}
    thrown: dict[str, list[str]] = {}
    idle: dict[str, list[str]] = {}
    repeats: dict[str, list[str]] = {}
    for run in runs.values():
        retained: collections.Counter = collections.Counter()
        for e in run.registry.query():
            retained[e.kind.name] += 1
        gone = vanished(run.offered, retained)
        discarded, inert, repeated = wasted_runs(run.records)
        if gone:
            lost[run.case_id] = gone
        if discarded:
            thrown[run.case_id] = discarded
        if inert:
            idle[run.case_id] = inert
        if repeated:
            repeats[run.case_id] = repeated

    rows_thrown = sum(r.discarded for run in runs.values() for r in run.records
                      if r.discarded and not (r.added or r.superseded))
    calls = sum(r.model_calls for run in runs.values() for r in run.records
                if spent_for_nothing(r))
    assert lost == {} and thrown == {} and idle == {} and repeats == {}, (
        "{} run(s) generated {} row(s) between them and kept none; {} more left the registry "
        "exactly as they found it; {} of all of those ran a method that had already kept nothing; "
        "{} model call(s) were spent on rows no engagement holds:\n".format(
            sum(len(v) for v in thrown.values()), rows_thrown, sum(len(v) for v in idle.values()),
            sum(len(v) for v in repeats.values()), calls)
        + "".join("  {}: {}\n".format(case, "; ".join(why)) for case, why in sorted(lost.items()))
        + "".join("  {}: {} discarded run(s), e.g. {}\n".format(case, len(why), why[0])
                  for case, why in sorted(thrown.items()))
        + "".join("  {}: {} inert run(s), e.g. {}\n".format(case, len(why), why[0])
                  for case, why in sorted(idle.items()))
        + "".join("  {}: {} repeat(s), e.g. {}\n".format(case, len(why), why[0])
                  for case, why in sorted(repeats.items())))


# ===========================================================================
# Independence - the instrument may not move with the thing measured
# ===========================================================================

def test_no_law_reads_the_moved_instrument():
    """The change set these laws judge also added the per-kind ceiling, the kind
    list it applies to, the registry's capacity check and the oracle's shape
    filter. A law that read any of them would be measuring the same diff with an
    instrument the diff supplied.

    Pinned as source, because an import added later would pass every other test
    in this file. The oracle is still the provider - a benchmark needs one - but
    no predicate here reads anything of it, and no predicate reads a ceiling.
    """
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    for name in ("MAX_ENTITIES_PER_ANALYSIS" + "_KIND", "ANALYSIS_" + "KINDS",
                 "_check_" + "capacity", "saturated_" + "kinds",
                 "_shapes_by_" + "interrogative", "BOU" + "NDS"):
        offending = [line for line in source.splitlines()
                     if name in line and not line.lstrip().startswith(("#", "*", '"', "'"))]
        assert offending == [], "a law here reads {}: {}".format(name, offending[:1])
    for name in ("dif" "flib", "Sequence" "Matcher", "rapid" "fuzz", "Leven" "shtein"):
        assert name not in source, "{} is a similarity measure; every comparison here is exact".format(name)
