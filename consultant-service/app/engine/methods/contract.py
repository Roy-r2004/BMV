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
from typing import TYPE_CHECKING, Any, Callable, Iterable, Mapping, Protocol, runtime_checkable

from app.engine.types import (
    ASSIGNMENT_EXECUTION,
    EFFORT_WEIGHT,
    FILTERABLE_FIELDS,
    FREE_EXECUTION,
    TERMINAL_STATUSES,
    Actor,
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


def input_state(spec: "MethodSpec", registry: "RegistryView") -> InputState:
    sat, miss = [], []
    for inp in spec.required_inputs:
        n = sum(1 for e in registry.query(inp.kind) if inp.matches(e))
        (sat if n >= inp.min_count else miss).append(inp)
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
                   methods: MethodRegistry = METHODS, *, max_per_issue: int = 2) -> list[Selection]:
    """For every open issue node, the methods whose declared shapes take the
    node on, ranked by (inputs satisfied, cheaper execution, fewer model calls,
    id). Reads nothing but enums and booleans: scrambling every TEXT_FIELDS
    value yields byte-identical selections. When the top two share
    (ratio, cost, calls) neither is silently preferred: both are marked tied
    and run as assignments so their disagreement surfaces as a CONFLICT."""
    out: list[Selection] = []
    for issue in open_issues:
        node = QuestionShape.of(issue)
        ranked: list[Selection] = []
        for m in methods.all():
            if not any(shape_matches(d, node) for d in m.spec.applicability):
                continue
            st = input_state(m.spec, registry)
            ranked.append(Selection(issue.id, m.spec.id, st,
                                    rank_key=(-st.ratio, m.spec.cost_class, m.spec.max_model_calls, m.spec.id)))
        ranked.sort(key=lambda s: s.rank_key)
        chosen = ranked[:max_per_issue]
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
