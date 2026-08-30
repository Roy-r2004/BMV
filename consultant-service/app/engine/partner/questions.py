"""app/engine/partner/questions.py - typed gaps, what each is worth, and the
few the client is asked this turn (design 6.5).

A gap is a hole between what the engine needs and what the registry holds, and
every gap in every engagement is one of seven typed kinds (design 6.5 a-g):
an unmet InputSpec of a method a live issue selected, an ISSUE node's own
evidence_needed, an unpinned dimension on a figure, an unconfirmed record class
on a document that owns a contested measure, a CONFLICT only the client may
resolve, an OPEN DECISION_REQUIRED from the client, and the structural holes of
an empty registry. Nothing here reads a text field, an engagement type or a
client name: gaps are found by kind, enum and count, which is why the same
seven queries serve every engagement.

The laws this module lives by:

  * A question with impact == 0 is never asked. Its answer cannot change the
    recommendation, so asking it spends the client's patience on nothing. The
    zero comes from the contract's own SENSITIVITY table (an UNRELATED subject
    scores zero); an entity nobody has RELATED yet is not the same thing, and
    falls back to the caller's default, because absence is not a zero.
  * value = impact x uncertainty x downstream / EFFORT_WEIGHT[effort], through
    the frozen `question_value`. Each factor moves the value on its own: a
    deep leaf under a light branch is worth less than the top-level node
    (path_impact), an answer already in the registry is worth less than a hole
    (uncertainty), an answer many methods are waiting on is worth more
    (downstream), and an answer that costs the client a document is worth less
    per unit of trouble than one they know offhand (effort divides).
  * At most one question per issue leaf per batch (S2), between
    MIN_QUESTIONS_PER_TURN and MAX_QUESTIONS_PER_TURN, stopping once the
    marginal value falls under MIN_QUESTION_VALUE. The bounds are Settings
    values, never counts written here.
  * A SPAWN_SPECIALIST gap is never a client question. The client is not asked
    for what analysis produces; that gap becomes an assignment in the analysis
    loop (design 6.7).
  * The model words questions; it cannot add one. Any reply from
    phrase_questions.j2 whose gap_id is not in the batch is dropped (agenda
    lock), and a gap the model did not word is asked in the engine's own words
    - the InputSpec's `why_needed`, verbatim - so under the FakeProvider the
    wording is deterministic.
  * A question carries its gap id as a label, so the next turn can see that a
    gap is already on the table and never asks it twice; a gap the client
    answered "don't know" becomes RECORD_UNKNOWN and is never re-asked.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from pydantic import BaseModel

from app.engine.calc.units import required_dimensions
from app.engine.llm import ModelCall, ModelProvider, StructuredFailure, structured_call
from app.engine.methods.contract import (
    METHODS, Gap, InputSpec, MethodRegistry, fill_strategy, path_impact, question_value, select_methods,
)
from app.engine.partner.hypothesis import PIN_DIMENSION_LABEL, effective_confidence, hypothesis_weights
from app.engine.templating import render
from app.engine.types import (
    BOUNDS, SENSITIVITY, TERMINAL_STATUSES, Actor, Add, AsksFor, Authority, Confidence, EffortClass,
    Entity, FillStrategy, InfoType, Kind, Provenance, QuestionPayload, RelationToCentralDecision,
    Relevance, SourceKind, Status, info_type_of, make_entity,
)

__all__ = [
    "GAP_LABEL_PREFIX",
    "PHRASE_PURPOSE",
    "QuestionBatch",
    "RECORD_CLASS_LABEL",
    "ScoredGap",
    "SourcedGap",
    "SOURCE_CLIENT_CONFLICT",
    "SOURCE_DECISION_REQUIRED",
    "SOURCE_EVIDENCE_NEEDED",
    "SOURCE_METHOD_INPUT",
    "SOURCE_RECORD_CLASS",
    "SOURCE_STRUCTURAL",
    "SOURCE_UNPINNED_DIMENSION",
    "STRUCTURAL_INPUTS",
    "ask",
    "decision_weights",
    "downstream_factor",
    "fan_out",
    "gap_impact",
    "gap_strategy",
    "gap_uncertainty",
    "gaps",
    "open_issues",
    "phrase_questions",
    "question_text",
    "question_why",
    "score_gap",
    "scored_gaps",
    "select_questions",
    "sourced_gaps",
    "top_gap_value",
]

# The seven typed gap sources of design 6.5 (a)-(g). Named constants, not
# prose: batch selection and the tests match on these, never on wording.
SOURCE_METHOD_INPUT = "method_input"
SOURCE_EVIDENCE_NEEDED = "evidence_needed"
SOURCE_UNPINNED_DIMENSION = "unpinned_dimension"
SOURCE_RECORD_CLASS = "record_class"
SOURCE_CLIENT_CONFLICT = "client_conflict"
SOURCE_DECISION_REQUIRED = "decision_required"
SOURCE_STRUCTURAL = "structural"

# A question carries the id of the gap it closes as a label. That is how the
# next turn knows the gap is already on the table (and how a "don't know"
# answer is tied back to the gap it retired) without matching on wording.
GAP_LABEL_PREFIX = "gap:"
# Provenance questions carry their own label so a renderer can group them;
# PIN_DIMENSION_LABEL is hypothesis.py's - charter_ready reads it structurally.
RECORD_CLASS_LABEL = "record_class"

PHRASE_PURPOSE = "engine:phrase_questions"

# Only these two strategies are ever put to the client. SPAWN_SPECIALIST is an
# assignment (design 6.7) and RECORD_UNKNOWN is an answer already given.
ASKABLE_STRATEGIES: frozenset[FillStrategy] = frozenset(
    {FillStrategy.ASK_CLIENT, FillStrategy.REQUEST_DOCUMENT})

# The decision term of a gap that names no ranked candidate. A gap that has not
# yet been tied to a decision - every gap on turn 1 - bears on whatever decision
# the engagement turns out to be about, so it carries full weight. Scoring it
# zero would silence the engine exactly when it has most to ask.
UNRANKED_DECISION_WEIGHT = 1.0

# The kinds whose information type does not depend on the payload and which the
# CLIENT owns outright. Derived from the contract's own tables, never listed by
# hand, so a kind that changes owner changes with it.
def _info_type_without_payload(kind: Kind) -> InfoType | None:
    try:
        return info_type_of(kind, None)
    except AttributeError:      # the kind's info type reads a payload field
        return None


CLIENT_PREFERENCE_KINDS: frozenset[Kind] = frozenset(
    k for k in Kind if _info_type_without_payload(k) is InfoType.CLIENT_PREFERENCE)

# The structural gaps of an empty registry (design 6.5 g) - turn 1. Evidence
# means a document, a dataset or a link: the conversation turn the client is
# writing right now is an EVIDENCE_SOURCE too, and it would close this gap
# without anybody having produced a record.
STRUCTURAL_INPUTS: tuple[InputSpec, ...] = (
    InputSpec("central_decision", Kind.DECISION, effort=EffortClass.OFFHAND,
              why_needed="until one decision is named, nothing this engagement produces can be aimed at it"),
    InputSpec("objective", Kind.OBJECTIVE, effort=EffortClass.OFFHAND,
              why_needed="an objective is what makes one answer better than another"),
    InputSpec("decision_owner", Kind.DECISION_OWNER, effort=EffortClass.OFFHAND,
              why_needed="a recommendation with nobody empowered to act on it is a document, not a decision"),
    InputSpec("deadline", Kind.DEADLINE, effort=EffortClass.OFFHAND,
              why_needed="what has to be true by when decides how much analysis there is time for"),
    InputSpec("evidence", Kind.EVIDENCE_SOURCE,
              filter={"source_kind": (SourceKind.DOCUMENT, SourceKind.DATASET, SourceKind.LINK)},
              effort=EffortClass.DOCUMENT,
              why_needed="without a record, every current-state figure rests on recollection alone"),
)


# =============================================================================
# 1. The typed gap and its score
# =============================================================================

@dataclass(frozen=True)
class SourcedGap:
    """A `Gap` plus what the registry knows about where it came from: which
    rows it is about (the question cites them), which relation prices it, the
    labels its question carries, and whether it blocks a release."""
    gap: Gap
    source: str
    gap_id: str
    subject_ids: tuple[str, ...] = ()
    relation: RelationToCentralDecision = RelationToCentralDecision.DEFINES
    labels: tuple[str, ...] = ()
    material: bool = False


@dataclass(frozen=True)
class ScoredGap:
    """A gap with every factor of its value kept separately, so a reply, a
    test or an integrity record can show WHY one question was asked and
    another was not - the number alone would be unaccountable."""
    sourced: SourcedGap
    impact: float
    uncertainty: float
    downstream: float
    fan_out: int
    value: float

    @property
    def gap(self) -> Gap:
        return self.sourced.gap

    @property
    def gap_id(self) -> str:
        return self.sourced.gap_id


@dataclass(frozen=True)
class QuestionBatch:
    """What one asking turn did. `scored` is every gap the registry has, not
    only the asked ones: the charter's ASK_FLOOR test and the live summary
    both read the ones that were left."""
    questions: tuple[Entity, ...] = ()
    asked: tuple[ScoredGap, ...] = ()
    scored: tuple[ScoredGap, ...] = ()
    model_call_id: str | None = None


# =============================================================================
# 2. Small registry reads (written against the RegistryView protocol only)
# =============================================================================

def _bound(bounds: Any, name: str):
    """A bound comes from Settings (ENGINE_*) or a mapping of BOUNDS names;
    the frozen default is the last resort so a bound can never be a literal in
    this module (dynamic-not-hardcoded)."""
    if isinstance(bounds, Mapping):
        return bounds.get(name, BOUNDS[name])
    return getattr(bounds, f"ENGINE_{name}")


def _live(view, kind: Kind | None = None) -> list[Entity]:
    return [e for e in view.query(kind) if e.status not in TERMINAL_STATUSES]


def _text_of(e: Entity) -> str:
    for attr in ("text", "statement", "name"):
        value = getattr(e.payload, attr, None)
        if isinstance(value, str) and value:
            return value
    return ""


def _relation_of(e: Entity, default: RelationToCentralDecision = RelationToCentralDecision.DEFINES
                 ) -> RelationToCentralDecision:
    """The relation that prices a gap about `e`. A payload carrying its own
    relation (a CONFLICT does) wins over the envelope's. UNKNOWN falls back to
    the caller's default: an entity nobody has related yet is not an entity
    somebody has declared irrelevant, and absence is not evidence of a defect.
    UNRELATED is honoured as the zero it is - that one somebody chose."""
    rel = getattr(e.payload, "relation_to_central_decision", None) or e.relation
    return default if rel is RelationToCentralDecision.UNKNOWN else rel


def open_issues(view) -> list[Entity]:
    """The issue nodes still worth working: live, not resolved, not already
    answered. Selection and gap-finding both read this one definition."""
    return [i for i in _live(view, Kind.ISSUE)
            if i.status is not Status.RESOLVED and not i.payload.answered_by]


def _count(view, inp: InputSpec) -> int:
    return sum(1 for e in view.query(inp.kind) if inp.matches(e))


def _facts_by_measure(view) -> dict[str, list[Entity]]:
    """Live facts grouped by measure_id. Computed here rather than through
    EngagementRegistry.facts_by_measure so this module stays on the
    RegistryView protocol and a ScopedView serves it equally."""
    out: dict[str, list[Entity]] = {}
    for f in _live(view, Kind.FACT):
        mid = f.payload.measure_id
        if mid:
            out.setdefault(mid, []).append(f)
    return out


def _questions(view) -> list[Entity]:
    return list(view.query(Kind.QUESTION))


def _gap_ids_on(question: Entity) -> tuple[str, ...]:
    return tuple(lbl[len(GAP_LABEL_PREFIX):] for lbl in question.labels
                 if lbl.startswith(GAP_LABEL_PREFIX))


def _unknown_gap_ids(view) -> frozenset[str]:
    """Gaps the client answered "don't know". The flag is checked with
    `is True`, never falsily, so a row an older normaliser left without it is
    not read as an unknown (owner constraint)."""
    out: set[str] = set()
    for q in _questions(view):
        if q.payload.unknown is True:
            out.update(_gap_ids_on(q))
    return frozenset(out)


def _open_gap_ids(view) -> frozenset[str]:
    """Gaps already on the table. A question that is OPEN is not re-asked; one
    that was answered may be asked again only if its gap is still a gap."""
    out: set[str] = set()
    for q in _questions(view):
        if q.status is Status.OPEN:
            out.update(_gap_ids_on(q))
    return frozenset(out)


def _measure_already_questioned(view, measure_id: str) -> bool:
    # Ingestion opens its own provenance question citing the measure when two
    # documents of equal proposed rank carry it (design 6.2). One measure is
    # asked about once, whichever side found it first.
    return any(measure_id in q.provenance.derived_from for q in _questions(view))


# =============================================================================
# 3. gaps(): the seven typed queries
# =============================================================================

def _gap_id(source: str, issue_id: str, method_id: str, inp: InputSpec,
            subject_ids: Iterable[str]) -> str:
    """A stable name for a gap: the same hole on the next turn is the same id,
    so a question already asked is recognised without matching on wording."""
    body = json.dumps({
        "source": source, "issue": issue_id, "method": method_id, "input": inp.name,
        "kind": inp.kind.value,
        "filter": {k: list(v) if isinstance(v, tuple) else v for k, v in sorted(inp.filter.items())},
        "dimensions": list(inp.dimensions_required), "subjects": sorted(subject_ids),
    }, sort_keys=True, default=str)
    return "GAP-" + hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]


def gap_strategy(inp: InputSpec, methods: MethodRegistry = METHODS, *,
                 client_said_unknown: bool = False, client_only: bool = False) -> FillStrategy:
    """`fill_strategy`, plus the one class of gap no analysis can fill.

    `client_only` holds for a CLIENT_PREFERENCE - an objective, a deadline, a
    decision owner is the client's to state, so a registered model-assisted
    method that happens to emit that kind must not turn the question into an
    assignment; the specialist would be inventing the client's preferences -
    and for the structural holes of an empty registry, where a specialist
    spawned before there is a decision, an objective or a document would have
    nothing to work from. Everything else keeps the frozen contract's answer.
    """
    if client_said_unknown:
        return FillStrategy.RECORD_UNKNOWN
    if client_only or inp.kind in CLIENT_PREFERENCE_KINDS:
        return (FillStrategy.REQUEST_DOCUMENT if inp.effort is EffortClass.DOCUMENT
                else FillStrategy.ASK_CLIENT)
    return fill_strategy(inp, methods, client_said_unknown=False)


def _evidence_input(asks: AsksFor) -> InputSpec | None:
    try:
        return InputSpec(name=f"evidence_needed:{asks.kind.value}", kind=asks.kind,
                         filter=dict(asks.filter), effort=EffortClass.OFFHAND,
                         why_needed="the issue node names this as the evidence it needs")
    except ValueError:
        # M2: a filter on a non-structural field cannot be constructed. Dropped
        # rather than widened - asking without the filter would ask for
        # something else and call the answer a match.
        return None


def sourced_gaps(view, *, methods: MethodRegistry = METHODS) -> list[SourcedGap]:
    """Every typed gap the registry holds, in the seven kinds of design 6.5.
    Identical queries for every engagement: no kind of gap exists that one
    industry has and another does not."""
    unknown = _unknown_gap_ids(view)
    out: list[SourcedGap] = []
    seen: set[str] = set()

    def emit(source: str, inp: InputSpec, *, issue_id: str = "", method_id: str = "",
             subjects: Iterable[str] = (), decision_ids: Iterable[str] = (),
             relation: RelationToCentralDecision = RelationToCentralDecision.DEFINES,
             labels: Iterable[str] = (), material: bool = False,
             client_only: bool = False) -> None:
        subject_ids = tuple(s for s in subjects if s)
        gid = _gap_id(source, issue_id, method_id, inp, subject_ids)
        if gid in seen:
            return
        seen.add(gid)
        strategy = gap_strategy(inp, methods, client_said_unknown=gid in unknown,
                                client_only=client_only)
        out.append(SourcedGap(
            gap=Gap(issue_id=issue_id, method_id=method_id, input=inp, strategy=strategy,
                    decision_ids=tuple(d for d in decision_ids if d)),
            source=source, gap_id=gid, subject_ids=subject_ids, relation=relation,
            labels=tuple(labels), material=material))

    issues = open_issues(view)

    # (a) unmet required inputs of the methods the live issues select
    for sel in select_methods(issues, view, methods):
        issue = view.get(sel.issue_id)
        if issue is None:
            continue
        for inp in sel.inputs.missing:
            emit(SOURCE_METHOD_INPUT, inp, issue_id=sel.issue_id, method_id=sel.method_id,
                 subjects=(sel.issue_id,), decision_ids=issue.payload.decisive_for,
                 relation=_relation_of(issue), material=True)

    # (b) evidence an ISSUE node declared it needs, unmet
    for issue in issues:
        for asks in issue.payload.evidence_needed:
            inp = _evidence_input(asks)
            if inp is None or _count(view, inp) >= inp.min_count:
                continue
            emit(SOURCE_EVIDENCE_NEEDED, inp, issue_id=issue.id, subjects=(issue.id,),
                 decision_ids=issue.payload.decisive_for, relation=_relation_of(issue),
                 material=True)

    # (c) a figure whose family needs a dimension the source never stated
    for fact in _live(view, Kind.FACT):
        quantity = fact.payload.quantity
        if quantity is None:
            continue
        for name in required_dimensions(quantity.unit_family):
            if getattr(quantity.dimensions, name) is not None:
                continue
            inp = InputSpec(name=f"pin:{name}", kind=Kind.FACT, filter={"has_quantity": True},
                            dimensions_required=(name,), effort=EffortClass.OFFHAND,
                            why_needed=(f"the figure carries no {name}, so nothing can be compared "
                                        f"with it without inventing one"))
            emit(SOURCE_UNPINNED_DIMENSION, inp, subjects=(fact.id,),
                 decision_ids=(fact.relevance.decision_id,), relation=_relation_of(fact),
                 labels=(PIN_DIMENSION_LABEL,))

    # (d) which document is the record, where two facts contest one measure
    for measure_id, facts in _facts_by_measure(view).items():
        if len(facts) < 2 or _measure_already_questioned(view, measure_id):
            continue
        sources: list[str] = []
        for fact in facts:
            for sid in fact.provenance.derived_from:
                src = view.get(sid)
                if src is None or src.kind is not Kind.EVIDENCE_SOURCE:
                    continue
                if src.payload.source_kind is SourceKind.CONVERSATION_TURN:
                    continue
                # `is True`, never truthiness: a row whose flag a newer
                # normaliser left unset is not read as confirmed OR contested.
                if src.payload.record_class_confirmed_by_client is True:
                    continue
                if sid not in sources:
                    sources.append(sid)
        if not sources:
            continue
        loudest = max(facts, key=lambda f: SENSITIVITY[_relation_of(f)])
        inp = InputSpec(name="record_class", kind=Kind.EVIDENCE_SOURCE,
                        filter={"record_class_confirmed_by_client": True},
                        effort=EffortClass.OFFHAND,
                        why_needed=("which document is the record decides precedence when their "
                                    "figures disagree"))
        emit(SOURCE_RECORD_CLASS, inp, subjects=(measure_id,) + tuple(sorted(sources)),
             decision_ids=tuple(dict.fromkeys(f.relevance.decision_id for f in facts)),
             relation=_relation_of(loudest), labels=(RECORD_CLASS_LABEL,))

    # (e) a conflict only the client's authority can resolve
    for conflict in _live(view, Kind.CONFLICT):
        if conflict.status is not Status.OPEN or conflict.payload.authority_required is not Authority.CLIENT:
            continue
        inp = InputSpec(name="conflict_resolution", kind=Kind.CONFLICT,
                        filter={"authority_required": Authority.CLIENT}, effort=EffortClass.OFFHAND,
                        why_needed=("two records disagree and only you can say which one the "
                                    "engagement should stand on"))
        emit(SOURCE_CLIENT_CONFLICT, inp, subjects=(conflict.id,),
             decision_ids=(conflict.relevance.decision_id,), relation=_relation_of(conflict),
             material=True)

    # (f) a decision required from the client, still open
    for required in _live(view, Kind.DECISION_REQUIRED):
        if required.status is not Status.OPEN or required.payload.from_authority is not Authority.CLIENT:
            continue
        inp = InputSpec(name="client_decision", kind=Kind.DECISION_REQUIRED,
                        filter={"from_authority": Authority.CLIENT}, effort=EffortClass.OFFHAND,
                        why_needed="the engagement cannot go past a decision only you can make")
        emit(SOURCE_DECISION_REQUIRED, inp, subjects=(required.id,),
             decision_ids=(required.payload.decision_id,), relation=_relation_of(required),
             material=True)

    # (g) the structural holes of an empty registry - turn 1
    for inp in STRUCTURAL_INPUTS:
        if _count(view, inp) >= inp.min_count:
            continue
        emit(SOURCE_STRUCTURAL, inp, client_only=True)

    return out


def gaps(view, *, methods: MethodRegistry = METHODS) -> list[Gap]:
    """The typed gaps themselves (contracts section 11)."""
    return [sg.gap for sg in sourced_gaps(view, methods=methods)]


# =============================================================================
# 4. Value: impact x uncertainty x downstream / effort
# =============================================================================

def decision_weights(view) -> dict[str, float]:
    """The hypothesis weights, except that a registry where nothing yet weighs
    on any candidate gives every candidate an equal share. An unranked
    engagement is not a worthless one; a planner that scored every gap zero
    would go silent on exactly the turn it should be asking."""
    weights = hypothesis_weights(view)
    if weights and not any(w > 0.0 for w in weights.values()):
        share = 1.0 / len(weights)
        return {cid: share for cid in weights}
    return weights


def gap_impact(view, sourced: SourcedGap) -> float:
    """impact = (weight of the decisions it serves) x SENSITIVITY[relation] x
    path_impact(issue). The path term is what makes a deep leaf under a light
    branch cheaper to leave open than a top-level node: the answer only
    reaches the decision through every edge above it."""
    weights = decision_weights(view)
    named = [weights[d] for d in sourced.gap.decision_ids if d in weights]
    decision_term = sum(named) if named else UNRANKED_DECISION_WEIGHT
    issue = view.get(sourced.gap.issue_id) if sourced.gap.issue_id else None
    sensitivity = SENSITIVITY[sourced.relation]
    if issue is not None and issue.kind is Kind.ISSUE:
        return decision_term * sensitivity * path_impact(issue, view)
    return decision_term * sensitivity


def gap_uncertainty(view, sourced: SourcedGap) -> float:
    """1 - the best confidence already standing behind an answer to this gap.
    A gap whose kind the registry already holds at high confidence is nearly
    answered; a status nobody has advanced (a conflict, a pin, a record class)
    is not partly advanced, so those stay at 1."""
    if sourced.source not in (SOURCE_METHOD_INPUT, SOURCE_EVIDENCE_NEEDED, SOURCE_STRUCTURAL):
        return 1.0
    inp = sourced.gap.input
    best = 0.0
    for e in view.query(inp.kind):
        if e.id in sourced.subject_ids or not inp.matches(e):
            continue
        best = max(best, effective_confidence(e))
    return max(0.0, min(1.0, 1.0 - best))


def fan_out(view, sourced: SourcedGap, *, methods: MethodRegistry = METHODS) -> int:
    """How many other things are waiting on this kind of answer: registered
    methods with an unsatisfied input of that kind, plus live issue nodes that
    named it as evidence they need. An answer several analyses are blocked on
    is worth more than one that unblocks nothing."""
    kind = sourced.gap.input.kind
    n = 0
    for m in methods.all():
        for inp in m.spec.required_inputs:
            if inp.kind is kind and _count(view, inp) < inp.min_count:
                n += 1
                break
    for issue in open_issues(view):
        if any(asks.kind is kind for asks in issue.payload.evidence_needed):
            n += 1
    return n


def downstream_factor(count: int, bounds: Any = BOUNDS) -> float:
    """1 + min(fan_out, MAX_FANOUT) / MAX_FANOUT: at most a doubling, so a
    widely-blocking answer is favoured without ever outweighing impact."""
    max_fanout = float(_bound(bounds, "MAX_FANOUT"))
    return 1.0 + min(float(count), max_fanout) / max_fanout


def score_gap(view, sourced: SourcedGap, *, bounds: Any = BOUNDS,
              methods: MethodRegistry = METHODS) -> ScoredGap:
    impact = gap_impact(view, sourced)
    uncertainty = gap_uncertainty(view, sourced)
    count = fan_out(view, sourced, methods=methods)
    downstream = downstream_factor(count, bounds)
    # The division by EFFORT_WEIGHT lives in the frozen `question_value`: a
    # question that costs the client a document must earn its place against
    # three they can answer offhand.
    value = question_value(impact=impact, uncertainty=uncertainty, downstream=downstream,
                           effort=sourced.gap.input.effort)
    return ScoredGap(sourced=sourced, impact=impact, uncertainty=uncertainty,
                     downstream=downstream, fan_out=count, value=value)


def scored_gaps(view, *, bounds: Any = BOUNDS, methods: MethodRegistry = METHODS) -> list[ScoredGap]:
    """Every gap, scored, most valuable first. Ties break on the gap id, so the
    order is a fact about the registry and never about dict iteration."""
    scored = [score_gap(view, sg, bounds=bounds, methods=methods)
              for sg in sourced_gaps(view, methods=methods)]
    scored.sort(key=lambda s: (-s.value, s.gap_id))
    return scored


# =============================================================================
# 5. The batch: what is actually asked this turn
# =============================================================================

def select_questions(scored: Iterable[ScoredGap], bounds: Any = BOUNDS,
                     *, exclude_gap_ids: Iterable[str] = ()) -> tuple[ScoredGap, ...]:
    """Top-k by value with k between MIN_ and MAX_QUESTIONS_PER_TURN, stopping
    once the marginal value falls under MIN_QUESTION_VALUE, at most one
    question per issue leaf (S2), and never a gap whose impact is zero or whose
    strategy is not the client's to answer."""
    minimum = int(_bound(bounds, "MIN_QUESTIONS_PER_TURN"))
    maximum = int(_bound(bounds, "MAX_QUESTIONS_PER_TURN"))
    floor = float(_bound(bounds, "MIN_QUESTION_VALUE"))
    skip = set(exclude_gap_ids)
    ranked = sorted((s for s in scored
                     if s.gap.strategy in ASKABLE_STRATEGIES     # a specialist gap is not a question
                     and s.impact > 0.0                          # its answer cannot change anything
                     and s.gap_id not in skip),
                    key=lambda s: (-s.value, s.gap_id))
    chosen: list[ScoredGap] = []
    leaves: set[str] = set()
    for candidate in ranked:
        if len(chosen) >= maximum:
            break
        leaf = candidate.gap.issue_id
        if leaf and leaf in leaves:
            continue                                            # one question per leaf per batch
        if len(chosen) >= minimum and candidate.value < floor:
            break
        chosen.append(candidate)
        if leaf:
            leaves.add(leaf)
    return tuple(chosen)


def top_gap_value(view, *, bounds: Any = BOUNDS, methods: MethodRegistry = METHODS) -> float:
    """The value of the best question left to ask, for the charter's ASK_FLOOR
    test (design 6.6). Nothing left to ask is 0.0, not None: an engagement with
    no askable gap is one whose charter is not waiting on the client."""
    askable = [s.value for s in scored_gaps(view, bounds=bounds, methods=methods)
               if s.gap.strategy in ASKABLE_STRATEGIES and s.impact > 0.0]
    return max(askable) if askable else 0.0


# =============================================================================
# 6. Wording: the model words them, the registry decides them
# =============================================================================

class _PhrasedQuestion(BaseModel):
    gap_id: str = ""
    text: str = ""
    issue_id: str = ""
    decision_id: str = ""


class PhrasedQuestions(BaseModel):
    questions: tuple[_PhrasedQuestion, ...] = ()


# The kinds whose wording is worth showing the model so a question uses the
# client's own terms. Structural kinds only - it is context for phrasing, never
# a filter, and nothing in selection has read it.
_CONTEXT_KINDS: tuple[Kind, ...] = (
    Kind.BUSINESS_CONTEXT, Kind.DECISION, Kind.OBJECTIVE, Kind.CONSTRAINT, Kind.DEADLINE,
    Kind.MEASURE, Kind.FACT, Kind.ISSUE,
)


def _context_entities(view) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for kind in _CONTEXT_KINDS:
        for e in _live(view, kind):
            text = _text_of(e)
            if text:
                out.append({"id": e.id, "kind": e.kind.value, "text": text})
    return out


def _gap_context(view, scored: ScoredGap) -> dict[str, Any]:
    gap = scored.gap
    issue = view.get(gap.issue_id) if gap.issue_id else None
    decision = None
    for did in gap.decision_ids:
        decision = view.get(did)
        if decision is not None:
            break
    if decision is None:
        decision = view.central_decision()
    return {
        "gap_id": scored.gap_id,
        "asks_for_kind": gap.input.kind.value,
        "asks_for_filter": ", ".join(f"{k}={v}" for k, v in sorted(gap.input.filter.items())),
        "effort": gap.input.effort.value,
        "issue_id": issue.id if issue is not None else "",
        "issue_text": _text_of(issue) if issue is not None else "",
        "decision_id": decision.id if decision is not None else "",
        "decision_text": _text_of(decision) if decision is not None else "",
        "why_needed": gap.input.why_needed,
    }


def phrase_questions(view, provider: ModelProvider, selected: Iterable[ScoredGap],
                     *, bounds: Any = BOUNDS,
                     model: str | None = None) -> tuple[dict[str, str], str | None]:
    """Word the selected gaps. Returns {gap_id: text} and the model call id.

    The agenda lock: a returned question whose gap_id is not in the batch is
    dropped, because a question that maps to no typed gap has no answer the
    registry could hold. A gap the model did not word keeps the engine's own
    words, so a provider outage costs wording, never the question.
    """
    batch = list(selected)
    if not batch:
        return {}, None
    prompt = render(
        "phrase_questions.j2",
        entities=_context_entities(view),
        gaps=[_gap_context(view, s) for s in batch],
        min_questions=int(_bound(bounds, "MIN_QUESTIONS_PER_TURN")),
        max_questions=int(_bound(bounds, "MAX_QUESTIONS_PER_TURN")),
    )
    try:
        parsed, response = structured_call(provider, ModelCall(
            purpose=PHRASE_PURPOSE, messages=({"role": "user", "content": prompt},),
            schema=PhrasedQuestions, model=model, engagement_id=getattr(view, "engagement_id", None)))
    except StructuredFailure:
        return {}, None
    allowed = {s.gap_id for s in batch}
    worded: dict[str, str] = {}
    for item in parsed.questions:
        if item.gap_id not in allowed or item.gap_id in worded:
            continue                                    # agenda lock, then first wording wins
        text = (item.text or "").strip()
        if text:
            worded[item.gap_id] = text
    return worded, response.call_id


def question_text(scored: ScoredGap, worded: Mapping[str, str] | None = None) -> str:
    """The question the client sees. The model's wording when the agenda lock
    admitted it, otherwise the InputSpec's `why_needed` verbatim - which is
    what makes the FakeProvider's questions deterministic."""
    text = (worded or {}).get(scored.gap_id, "")
    if text:
        return text
    inp = scored.gap.input
    return inp.why_needed or f"please provide {inp.kind.value.replace('_', ' ')}"


def question_why(view, scored: ScoredGap) -> str:
    """Rendered from the issue node and the decision the gap serves, by id, so
    the client can see what the answer is for (design 6.5)."""
    gap = scored.gap
    issue = view.get(gap.issue_id) if gap.issue_id else None
    decision = None
    for did in gap.decision_ids:
        decision = view.get(did)
        if decision is not None:
            break
    if decision is None:
        decision = view.central_decision()
    parts: list[str] = []
    if issue is not None:
        parts.append(f"needed to settle {issue.id} ({_text_of(issue)})")
    if decision is not None:
        parts.append(f"for {decision.id} ({_text_of(decision)})")
    if not parts:
        return gap.input.why_needed
    return " ".join(parts)


# =============================================================================
# 7. Asking: OPEN QUESTION rows, one per gap
# =============================================================================

def ask(registry, provider: ModelProvider, *, turn_number: int, bounds: Any = BOUNDS,
        methods: MethodRegistry = METHODS, model: str | None = None) -> QuestionBatch:
    """Score every gap, select this turn's batch, word it, and write one OPEN
    QUESTION per gap. A gap whose question is already open is not re-asked."""
    scored = scored_gaps(registry, bounds=bounds, methods=methods)
    selected = select_questions(scored, bounds, exclude_gap_ids=_open_gap_ids(registry))
    worded, call_id = phrase_questions(registry, provider, selected, bounds=bounds, model=model)
    actor_ref = f"partner:turn:{turn_number}"
    written: list[Entity] = []
    for item in selected:
        sourced = item.sourced
        gap = item.gap
        payload = QuestionPayload(
            text=question_text(item, worded),
            asks_for=(AsksFor(gap.input.kind, dict(gap.input.filter)),),
            issue_ids=(gap.issue_id,) if gap.issue_id else (),
            why=question_why(registry, item),
            effort=gap.input.effort,
            strategy=gap.strategy,
            material=sourced.material,
            value=item.value,
        )
        entity = make_entity(
            kind=Kind.QUESTION, engagement_id=registry.engagement_id, payload=payload,
            provenance=Provenance(actor=Actor.PARTNER, actor_ref=actor_ref,
                                  derived_from=sourced.subject_ids,
                                  model_call_id=call_id if item.gap_id in worded else None),
            confidence=Confidence(None),
            # A question is not evidence for a candidate decision: it carries no
            # relevance weight, or asking would move the hypothesis it serves.
            relevance=Relevance(None, 0.0),
            relation=sourced.relation, status=Status.OPEN,
            labels=(GAP_LABEL_PREFIX + item.gap_id,) + sourced.labels)
        written.append(registry.apply(Add(entity)))
    return QuestionBatch(questions=tuple(written), asked=selected, scored=tuple(scored),
                         model_call_id=call_id)
