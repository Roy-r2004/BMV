"""Method contract: question shapes, input specs, registration, selection and
gap fill strategies (contracts.py sections 7, 10 and 11).

The laws this module enforces, each in the docstring of the thing that
enforces it:

  M1  a DETERMINISTIC / CALCULATION method declares zero model calls
  M2  an InputSpec filter reads FILTERABLE_FIELDS only (a text filter is
      unconstructible, so a text-reading method is unregisterable)
  M3  `answers` is non-empty and covers every declared shape's interrogative
  M4  applicability is non-empty

Selection reads QuestionShape (enums and booleans) against declared shapes
and InputSpec.matches() against structural fields, and nothing else: that is
why scrambling every TEXT_FIELDS value yields byte-identical selections, and
why no engagement type, benchmark vocabulary or client name can steer which
analysis runs. Registration is by import; adding a method never touches the
Partner loop.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Callable, Iterable, Mapping, Protocol, Sequence, runtime_checkable

from app.engine.types import (
    ASSIGNMENT_EXECUTION,
    BOUNDS,
    EFFORT_WEIGHT,
    FILTERABLE_FIELDS,
    FREE_EXECUTION,
    TERMINAL_STATUSES,
    Actor,
    Add,
    Authority,
    CapabilityClass,
    Confidence,
    Dimensions,
    EffortClass,
    Entity,
    EntityDelta,
    ExecutionType,
    FactBasis,
    FillStrategy,
    Finding,
    Interrogative,
    Kind,
    Provenance,
    QuestionPayload,
    RelationToCentralDecision,
    Relevance,
    Status,
    Supersede,
    _encode,
    _norm,
    make_entity,
)

if TYPE_CHECKING:  # read-side protocols live with their implementations; never imported at runtime here
    from app.engine.llm import ModelProvider
    from app.engine.registry import Calculator, RegistryView


# =============================================================================
# 7. Question shapes, input specs
# =============================================================================

@dataclass(frozen=True)
class QuestionShape:
    """The structural signature of an issue node - the only thing method
    applicability may be declared against."""
    interrogative: Interrogative
    target_kind: Kind
    quantified: bool = False
    comparative: bool = False
    causal: bool = False
    temporal: bool = False
    capability_class: CapabilityClass | None = None

    @classmethod
    def of(cls, issue: Entity) -> "QuestionShape":
        p = issue.payload
        return cls(interrogative=p.interrogative, target_kind=p.target_kind, quantified=p.quantified,
                   comparative=p.comparative, causal=p.causal, temporal=p.temporal,
                   capability_class=p.capability_class)


def shape_matches(decl: QuestionShape, node: QuestionShape) -> bool:
    """A declared shape takes on a node when every constraint it states holds.
    A declaration leaves a dimension open by stating False/None. Both the
    interrogative and the target kind must agree: a WHAT-on-FACT method that
    took on WHAT-on-STAKEHOLDER nodes would run against inputs it never
    declared."""
    if decl.interrogative != node.interrogative or decl.target_kind != node.target_kind:
        return False
    for dim in ("quantified", "comparative", "causal", "temporal"):
        if getattr(decl, dim) and not getattr(node, dim):
            return False
    if decl.capability_class is not None and decl.capability_class != node.capability_class:
        return False
    return True


def _freeze_filter_value(v: Any) -> Any:
    if isinstance(v, (list, tuple, set, frozenset)):
        return tuple(_norm(x) for x in v)
    return _norm(v)


@dataclass(frozen=True)
class InputSpec:
    """What a method needs. M2: filters read FILTERABLE_FIELDS only - a text
    filter raises at construction, so a text-reading method is unregisterable.
    `dimensions_required` makes a quantified input satisfiable only by
    quantities whose named dimensions are pinned (an unpinned dimension is a
    typed hole, never a default); `effort` and `why_needed` are method data
    the question planner and the fake client read."""
    name: str
    kind: Kind
    filter: Mapping[str, Any] = field(default_factory=dict)
    min_count: int = 1
    max_count: int | None = None
    min_status: Status = Status.PROPOSED
    dimensions_required: tuple[str, ...] = ()
    effort: EffortClass = EffortClass.OFFHAND
    why_needed: str = ""

    def __post_init__(self):
        bad = set(self.filter) - FILTERABLE_FIELDS
        if bad:
            raise ValueError(f"M2: InputSpec {self.name!r} filters on non-structural field(s) {sorted(bad)}")
        for d in self.dimensions_required:
            if d not in Dimensions.DIMENSION_NAMES:
                raise ValueError(f"unknown dimension {d!r}")
        object.__setattr__(self, "filter", {k: _freeze_filter_value(v) for k, v in self.filter.items()})

    def matches(self, e: Entity) -> bool:
        if e.kind != self.kind or e.status in TERMINAL_STATUSES:
            return False
        if self.min_status == Status.CONFIRMED and e.status not in (Status.CONFIRMED, Status.APPROVED):
            return False
        for key, want in self.filter.items():
            have = e.kind.value if key == "kind" else e.field(key)
            if isinstance(want, tuple):
                if have not in want:
                    return False
            elif have != want:
                return False
        if self.dimensions_required:
            q = getattr(e.payload, "quantity", None)
            if q is None or not q.dimensions.pinned_for(self.dimensions_required):
                return False
        return True


@dataclass(frozen=True)
class InputState:
    satisfied: tuple[InputSpec, ...]
    missing: tuple[InputSpec, ...]

    @property
    def ratio(self) -> float:
        n = len(self.satisfied) + len(self.missing)
        return 1.0 if n == 0 else len(self.satisfied) / n


def satisfied_by(inp: InputSpec, rows: Iterable[Entity]) -> bool:
    """Whether these rows fill one declared input slot. The one rule, so that
    the two questions asked of it - "does the registry hold this?" and "does
    what this method has not already used hold this?" - cannot answer
    differently over the same rows."""
    return sum(1 for e in rows if inp.matches(e)) >= inp.min_count


def unmet_over(spec: "MethodSpec", rows: Sequence[Entity]) -> tuple[InputSpec, ...]:
    """The required inputs this SET of rows does not fill.

    `input_state` asks it of the whole register; `unconcluded` narrows the set
    first, so the same question can be asked of the rows a method has not
    already drawn its conclusions from. A method whose window still holds every
    kind it declared, but only in rows it has already concluded about, is not
    fed - it is finished, and the two readings have to be the same rule or the
    selector and the method would disagree about what "fed" means.
    """
    return tuple(inp for inp in spec.required_inputs if not satisfied_by(inp, rows))


def input_state(spec: "MethodSpec", registry: "RegistryView") -> InputState:
    sat, miss = [], []
    for inp in spec.required_inputs:
        (sat if satisfied_by(inp, registry.query(inp.kind)) else miss).append(inp)
    return InputState(tuple(sat), tuple(miss))


# =============================================================================
# 10. Method contract, registration and selection
# =============================================================================

@dataclass(frozen=True)
class EvidenceRequirement:
    """What inputs must be for an output to be CONFIRMED rather than PROPOSED."""
    min_authority_for_confirmed: tuple[Authority, ...] = (Authority.VERIFIED_RECORD, Authority.DETERMINISTIC_ENGINE,
                                                          Authority.CLIENT, Authority.CLIENT_STATED)
    every_output_cites_inputs: bool = True
    forbid_new_quantities: bool = True       # every Quantity written is calculated (formula+inputs) or copied by id


@dataclass(frozen=True)
class MethodContext:
    registry: "RegistryView"                 # scoped for specialists
    provider: "ModelProvider"
    calc: "Calculator"
    actor: Actor                             # METHOD or SPECIALIST
    actor_ref: str
    issue_ids: tuple[str, ...]
    assignment_id: str | None = None
    settings: Mapping[str, Any] = field(default_factory=dict)   # bounds only


@dataclass(frozen=True)
class MethodResult:
    deltas: tuple[EntityDelta, ...] = ()
    questions: tuple[QuestionPayload, ...] = ()
    findings: tuple[Finding, ...] = ()
    model_call_ids: tuple[str, ...] = ()


Validator = Callable[["RegistryView", MethodResult], list[Finding]]


@dataclass(frozen=True)
class MethodSpec:
    """M1: a DETERMINISTIC or CALCULATION method declares max_model_calls == 0
    (a method that claims exactness cannot ask a model for its numbers).
    M3: `answers` is non-empty and covers every declared shape's interrogative.
    M4: applicability is non-empty (a method no shape selects is dead code
    that would still count as coverage)."""
    id: str
    version: int
    applicability: tuple[QuestionShape, ...]
    answers: tuple[Interrogative, ...]
    required_inputs: tuple[InputSpec, ...]
    optional_inputs: tuple[InputSpec, ...]
    execution: ExecutionType
    output_kinds: tuple[Kind, ...]
    output_schema: type | None
    evidence: EvidenceRequirement
    limitations: tuple[str, ...]
    validators: tuple[Validator, ...]
    cost_class: int = 1
    max_model_calls: int = 0
    output_schema_version: int = 1
    # Whether this method still has anything to conclude in a given registry,
    # answered from the register alone and before any call is made. Optional:
    # a method that cannot know says nothing and is always offered, which is
    # the safe direction. What it must never be is a judgement about a case -
    # it reads counts, kinds and typed fields, exactly as selection does.
    #
    # It exists because "run it and see" is not free. A method offered a node
    # it can do nothing with spends a selection slot and, if it is model
    # assisted, a call - and then records a refusal for every candidate it
    # generated. The registry could have said so first.
    pending: Callable[["RegistryView"], bool] | None = None

    def __post_init__(self):
        if self.execution in FREE_EXECUTION and self.max_model_calls > 0:
            raise ValueError(f"M1: {self.id} is {self.execution.value} but declares model calls")
        if not self.answers:
            raise ValueError(f"M3: {self.id} answers nothing")
        if not self.applicability:
            raise ValueError(f"M4: {self.id} declares no applicability shape")
        for s in self.applicability:
            if not isinstance(s, QuestionShape):
                raise TypeError("applicability must be QuestionShape instances")
            if s.interrogative not in self.answers:
                raise ValueError(f"M3: {self.id} takes on {s.interrogative.value} nodes it cannot answer")

    def fingerprint(self) -> str:
        body = {"id": self.id, "version": self.version, "applicability": [_encode(a) for a in self.applicability],
                "required": [(i.name, i.kind.value, dict(i.filter), i.min_count, list(i.dimensions_required))
                             for i in self.required_inputs]}
        return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:12]


@runtime_checkable
class Method(Protocol):
    spec: MethodSpec

    def run(self, ctx: MethodContext) -> MethodResult: ...


class MethodRegistry:
    """Registration by import. New methods never touch the orchestrator."""

    def __init__(self) -> None:
        self._methods: dict[str, Method] = {}

    def register(self, method: Method) -> Method:
        if not isinstance(method, Method):
            raise TypeError("a method must expose .spec and .run(ctx)")
        if not isinstance(method.spec, MethodSpec):
            raise TypeError("spec must be a MethodSpec")
        if method.spec.id in self._methods:
            raise ValueError(f"method {method.spec.id!r} already registered")
        self._methods[method.spec.id] = method
        return method

    def get(self, method_id: str) -> Method:
        return self._methods[method_id]

    def all(self) -> list[Method]:
        return list(self._methods.values())

    def producers_of(self, kind: Kind) -> list[Method]:
        return [m for m in self._methods.values() if kind in m.spec.output_kinds]


METHODS = MethodRegistry()


def register(cls: type) -> type:
    """@register on a class with a `spec` attribute; instantiates and registers it."""
    METHODS.register(cls())
    return cls


@dataclass(frozen=True)
class Selection:
    issue_id: str
    method_id: str
    inputs: InputState
    rank_key: tuple
    tied: bool = False                       # another method matched at equal rank: both run as assignments


def select_methods(open_issues: Iterable[Entity], registry: "RegistryView",
                   methods: MethodRegistry = METHODS, *, max_per_issue: int | None = None,
                   exclude: Callable[[str, str], bool] | None = None) -> list[Selection]:
    """For every open issue node, the methods whose declared shapes take the
    node on, ranked by (inputs satisfied, cheaper execution, fewer model calls,
    id). Reads nothing but enums and booleans: scrambling every TEXT_FIELDS
    value yields byte-identical selections. When the top two share
    (ratio, cost, calls) neither is silently preferred: both are marked tied
    and run as assignments so their disagreement surfaces as a CONFLICT.

    `exclude(issue_id, method_id)` drops a pair BEFORE the ceiling is applied.
    The caller passes what it already knows - the loop and the SYNTHESIS guard
    pass `attempted` - because a method that has already run on a node would
    otherwise hold one of the node's slots for the rest of the engagement:
    with `MAX_METHODS_PER_ISSUE` slots and three shape-matching methods, the
    third could never be reached however satisfiable it became, and a method
    whose inputs another method was about to write would be head-of-line
    blocked by the very run that made it selectable. The predicate is passed
    rather than queried here so this function still reads nothing but enums
    and booleans, and the scramble law stays exactly as true as it was.

    `max_per_issue` is the operator's ceiling (MAX_METHODS_PER_ISSUE), never a
    literal: None means the caller stated no value, and the frozen default is
    the last resort.
    """
    ceiling = int(BOUNDS["MAX_METHODS_PER_ISSUE"] if max_per_issue is None else max_per_issue)
    out: list[Selection] = []
    for issue in open_issues:
        node = QuestionShape.of(issue)
        ranked: list[Selection] = []
        for m in methods.all():
            if not any(shape_matches(d, node) for d in m.spec.applicability):
                continue
            if exclude is not None and exclude(issue.id, m.spec.id):
                continue
            st = input_state(m.spec, registry)
            ranked.append(Selection(issue.id, m.spec.id, st,
                                    rank_key=(-st.ratio, m.spec.cost_class, m.spec.max_model_calls, m.spec.id)))
        ranked.sort(key=lambda s: s.rank_key)
        chosen = ranked[:ceiling]
        if len(chosen) >= 2 and chosen[0].rank_key[:3] == chosen[1].rank_key[:3]:
            chosen = [replace(s, tied=True) for s in chosen]
        out.extend(chosen)
    return out


def new_entity(ctx: MethodContext, kind: Kind, payload: Any, *, derived_from: Iterable[str],
               relation: RelationToCentralDecision, confidence: Confidence, decision_id: str | None,
               weight: float, status: Status = Status.PROPOSED, locator: str | None = None,
               model_call_id: str | None = None) -> Entity:
    """The helper every method writes with. A method output cites what it rests on."""
    derived = tuple(derived_from)
    if not derived and kind != Kind.QUESTION:
        raise ValueError("a method output must cite the entities it rests on")
    return make_entity(kind=kind, engagement_id=ctx.registry.engagement_id, payload=payload,
                       provenance=Provenance(actor=ctx.actor, actor_ref=ctx.actor_ref, derived_from=derived,
                                             source_locator=locator, model_call_id=model_call_id),
                       confidence=confidence, relevance=Relevance(decision_id=decision_id, weight=weight),
                       relation=relation, status=status)


def gather_inputs(spec: "MethodSpec", view: "RegistryView") -> list[Entity]:
    """Every live entity a declared InputSpec (required or optional) matches,
    first-seen order, deduplicated by id. InputSpec.matches already excludes
    terminal rows and enforces min_status and dimension pins, so the inputs a
    method sees are exactly what its declaration asked for - no more.

    It lives here rather than beside the first method that needed it because
    the SELECTOR now reads it too: what a method would be shown is what decides
    whether running it again could tell the engagement anything new.
    """
    out: dict[str, Entity] = {}
    for inp in spec.required_inputs + spec.optional_inputs:
        for e in view.query(inp.kind):
            if inp.matches(e):
                out.setdefault(e.id, e)
    return list(out.values())


def input_fingerprint(spec: "MethodSpec", view: "RegistryView") -> str:
    """A digest of exactly what this method would be shown, right now.

    Ids AND content: a row that was superseded in place keeps its id, and a
    method shown the new version is being shown something new. Sorted, so the
    order rows happen to be stored in cannot change the answer, and hashed so
    the ANALYSIS row carries a fixed-width record rather than a growing list.

    This is the honest form of "has this already been done". `attempted` asked
    whether the method had run on this NODE, which is a question about the
    tree; the question that matters is whether it has already seen this
    evidence, which is a question about the register. A method run again on a
    second node with the same inputs writes the same conclusions and has them
    all refused as restatements - a model call spent to learn what the registry
    already knew.
    """
    h = hashlib.sha256()
    h.update(f"{spec.id}@{spec.version}".encode())
    for entity_id, digest in sorted((e.id, e.content_hash()) for e in gather_inputs(spec, view)):
        h.update(entity_id.encode())
        h.update(digest.encode())
    return h.hexdigest()[:16]


def concluded_about(spec: "MethodSpec", view: "RegistryView") -> set[str]:
    """The ids that a live row of one of this method's own output kinds already
    cites - the evidence this analysis has already drawn its kind of conclusion
    from. Read from `derived_from` and from the `evidence` field the concluding
    kinds carry, never from wording."""
    out: set[str] = set()
    for kind in spec.output_kinds:
        if kind is Kind.QUESTION:
            continue
        for row in view.query(kind):
            if row.status in TERMINAL_STATUSES:
                continue
            out.update(row.provenance.derived_from)
            out.update(getattr(row.payload, "evidence", ()) or ())
    return out


def productive(payload: Any) -> bool:
    """Whether a recorded run left the engagement anything.

    Two shapes count. A run that KEPT something - added or superseded a row -
    has moved the engagement's position. A run that asked and refused nothing
    has found a typed hole, which is work: the answer is what makes the next
    round runnable.

    What does NOT count is a run that generated candidates and kept none, and a
    run that did nothing at all. Neither left anything behind, and offering the
    same method again is spending a selection slot - and, for a model-assisted
    method, another model call - on an outcome the engagement has already
    observed.

    A row that was not accounted for carries -1 and is read as productive:
    absence of a record is not a record of failure, and a selector that read it
    the other way would silence a method because some other path wrote its
    ANALYSIS row.
    """
    kept = int(getattr(payload, "kept", -1))
    discarded = int(getattr(payload, "discarded", -1))
    asked = int(getattr(payload, "asked", -1))
    if kept < 0 or discarded < 0 or asked < 0:
        return True
    return bool(kept) or (bool(asked) and not discarded)


def run_record(result: "MethodResult") -> dict[str, int]:
    """What a finished MethodResult cost and left behind, in the terms
    `productive` reads. Counted at the method boundary, because that is where
    the waste is: a batch the registry rolls back never reaches the door, and a
    candidate the method refused inside itself never reaches it either."""
    return {
        "kept": sum(1 for d in result.deltas if isinstance(d, (Add, Supersede))),
        "discarded": sum(1 for f in result.findings if str(f.law).startswith("M.")),
        "asked": len(result.questions),
        "model_calls": len(result.model_call_ids),
    }


def question_lineage(view: "RegistryView", issue_id: str | None,
                     payload: QuestionPayload) -> tuple[str, ...]:
    """The ids a QUESTION is written citing: the node it was asked from, and
    the registered rows the producer said the hole is IN (`about_ids`).

    A question used to be born citing its issue node and nothing else, so a
    producer that knew exactly which rows it could not tell apart had no way to
    say so, and the record of the hole lost its subject on the way from the
    method's result to the registry. An id the registry does not hold is
    dropped rather than written: a citation that resolves to nothing is worse
    than no citation, and a whole batch rolled back over a stale id would lose
    the question too.
    """
    ids = [i for i in (issue_id,) if i]
    for i in payload.about_ids:
        if i and i not in ids and view.get(i) is not None:
            ids.append(i)
    return tuple(ids)


def question_relevance(view: "RegistryView", payload: QuestionPayload,
                       *, weight: float = 0.0) -> Relevance:
    """The decision a QUESTION blocks, as a typed field on the row.

    `Relevance.decision_id` is documented as "the DECISION this bears on (None
    == not yet attached)", and before this every question the engine wrote was
    unattached - which made a blocker unable to say which decision it blocked,
    and made "why this decision is unanswered" indistinguishable from "a row
    written after that decision".

    The WEIGHT stays zero, and that is not an oversight. A question is not
    evidence for a candidate decision; weighting it would let the engine move
    the ranking that chooses the engagement's central decision by asking about
    it (partner/questions.py says the same thing where it writes gap
    questions). Naming the decision and weighting it are two different acts,
    and only the first belongs on a question.
    """
    decision_id = payload.decision_id
    if not decision_id or view.get(decision_id) is None:
        return Relevance(None, weight)
    return Relevance(decision_id, weight)


# =============================================================================
# 11. Gaps and fill strategies (the mechanical specialist trigger, MF1.2)
# =============================================================================

@dataclass(frozen=True)
class Gap:
    """A typed hole between what a selected method needs and what the registry holds."""
    issue_id: str
    method_id: str
    input: InputSpec
    strategy: FillStrategy
    decision_ids: tuple[str, ...] = ()


_DOCUMENT_BASES: frozenset[str] = frozenset({FactBasis.DOCUMENT_VERIFIED.value, FactBasis.DOCUMENT_EXTRACTED.value})


def fill_strategy(inp: InputSpec, methods: MethodRegistry = METHODS, *, client_said_unknown: bool = False) -> FillStrategy:
    """SPAWN_SPECIALIST when the missing input is itself the output of a
    RESEARCH / MODEL_ASSISTED method (the dependency structure of inputs:
    the client is never asked for what analysis produces);
    REQUEST_DOCUMENT when the input demands a document basis or document effort;
    RECORD_UNKNOWN after the client said they do not know (never re-asked);
    otherwise ASK_CLIENT. Mutation partner: removing the SPAWN branch makes
    no assignment appear on any benchmark case."""
    if client_said_unknown:
        return FillStrategy.RECORD_UNKNOWN
    if any(m.spec.execution in ASSIGNMENT_EXECUTION for m in methods.producers_of(inp.kind)):
        return FillStrategy.SPAWN_SPECIALIST
    basis = inp.filter.get("basis")
    wants_document = inp.effort == EffortClass.DOCUMENT or (
        isinstance(basis, tuple) and set(basis) <= _DOCUMENT_BASES)
    if wants_document:
        return FillStrategy.REQUEST_DOCUMENT
    return FillStrategy.ASK_CLIENT


def path_impact(issue: Entity, registry: "RegistryView") -> float:
    """Product of weight_to_parent from the node up to the root."""
    w = 1.0
    node: Entity | None = issue
    seen: set[str] = set()
    while node is not None and node.id not in seen:
        seen.add(node.id)
        w *= float(node.payload.weight_to_parent)
        parent = node.payload.parent_id
        node = registry.get(parent) if parent else None
    return w


def question_value(*, impact: float, uncertainty: float, downstream: float, effort: EffortClass) -> float:
    """decision impact x uncertainty x downstream dependencies / client effort."""
    return impact * uncertainty * downstream / EFFORT_WEIGHT[effort]


__all__ = [n for n in dir() if not n.startswith("_")]
