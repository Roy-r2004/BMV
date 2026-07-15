"""Strict, versioned contract for an AI-produced application specification.

``AppSpec`` is intentionally declarative.  It may describe product semantics,
references, state transitions, and acceptance evidence, but it cannot contain
source paths, selectors, executable expressions, or generated source code.
Those implementation details are derived by later deterministic projections.
"""
from __future__ import annotations

from typing import Annotated, Literal, Optional, Tuple, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    StringConstraints,
    field_validator,
)


APP_SPEC_SCHEMA_VERSION = "1.0"

_ID_PATTERN = r"^[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*$"
_ROUTE_PATTERN = r"^/(?:[a-z0-9][a-z0-9_-]*(?:/[a-z0-9][a-z0-9_-]*)*)?$"
_SOURCE_REF_PATTERN = r"^(?:customer_input|reference_evidence)(?:\.[A-Za-z0-9_]+)+$"

Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=_ID_PATTERN,
    ),
]
ShortText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=240),
]
LongText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
]
RoutePath = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=160,
        pattern=_ROUTE_PATTERN,
    ),
]
SourceRef = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=240,
        pattern=_SOURCE_REF_PATTERN,
    ),
]
EffectScalar = Union[StrictBool, StrictInt, StrictFloat, StrictStr]


class _StrictModel(BaseModel):
    """Shared policy for every nested AppSpec object."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


class ProductIntent(_StrictModel):
    name: ShortText
    summary: LongText
    problem: LongText
    desired_outcome: LongText
    target_users: Tuple[ShortText, ...] = Field(min_length=1, max_length=20)
    success_metrics: Tuple[ShortText, ...] = Field(default=(), max_length=20)


class Requirement(_StrictModel):
    id: Identifier
    title: ShortText
    description: LongText
    priority: Literal["must", "should", "could"] = "must"
    verification_mode: Literal["interaction", "content", "data", "integration"]
    source_refs: Tuple[SourceRef, ...] = Field(min_length=1, max_length=20)


class Assumption(_StrictModel):
    id: Identifier
    statement: LongText
    rationale: Optional[LongText] = None
    confidence: Literal["low", "medium", "high"] = "medium"


class OpenQuestion(_StrictModel):
    id: Identifier
    question: LongText
    rationale: Optional[LongText] = None
    blocking: StrictBool = False


class Role(_StrictModel):
    id: Identifier
    name: ShortText
    description: LongText
    goals: Tuple[ShortText, ...] = Field(default=(), max_length=20)
    default_page_id: Identifier


class EntityField(_StrictModel):
    id: Identifier
    name: ShortText
    description: Optional[LongText] = None
    type: Literal[
        "string",
        "integer",
        "number",
        "boolean",
        "date",
        "datetime",
        "enum",
        "reference",
        "list",
    ]
    required: StrictBool = False
    enum_values: Tuple[ShortText, ...] = Field(default=(), max_length=50)
    reference_entity_id: Optional[Identifier] = None


class Entity(_StrictModel):
    id: Identifier
    name: ShortText
    description: LongText
    fields: Tuple[EntityField, ...] = Field(min_length=1, max_length=80)


class Capability(_StrictModel):
    id: Identifier
    name: ShortText
    description: LongText
    requirement_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=50)
    role_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=20)
    entity_ids: Tuple[Identifier, ...] = Field(default=(), max_length=30)


class Page(_StrictModel):
    id: Identifier
    name: ShortText
    purpose: LongText
    route: RoutePath
    surface: Literal["public", "ops"]
    primary: StrictBool = False
    role_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=20)
    capability_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=50)
    state_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=80)
    action_ids: Tuple[Identifier, ...] = Field(default=(), max_length=100)
    evidence_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=100)


class State(_StrictModel):
    id: Identifier
    page_id: Identifier
    name: ShortText
    description: LongText
    initial: StrictBool = False
    terminal: StrictBool = False
    evidence_ids: Tuple[Identifier, ...] = Field(default=(), max_length=50)


class Action(_StrictModel):
    id: Identifier
    page_id: Identifier
    role_id: Identifier
    name: ShortText
    description: LongText
    kind: Literal["navigate", "click", "fill", "select", "submit", "toggle"]
    capability_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=30)
    entity_id: Optional[Identifier] = None
    input_label: Optional[ShortText] = None


class StateEffect(_StrictModel):
    entity_id: Identifier
    field_id: Identifier
    operation: Literal["set", "clear", "increment", "decrement", "append", "remove"]
    value: Optional[EffectScalar] = None


class Transition(_StrictModel):
    id: Identifier
    action_id: Identifier
    from_state_id: Identifier
    to_state_id: Identifier
    description: LongText
    preconditions: Tuple[ShortText, ...] = Field(default=(), max_length=20)
    postconditions: Tuple[ShortText, ...] = Field(default=(), max_length=20)
    effects: Tuple[StateEffect, ...] = Field(default=(), max_length=30)


class Evidence(_StrictModel):
    id: Identifier
    page_id: Identifier
    name: ShortText
    description: LongText
    kind: Literal[
        "text",
        "metric",
        "list",
        "table",
        "chart",
        "form",
        "status",
        "navigation",
        "media",
    ]
    capability_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=30)


class JourneyStep(_StrictModel):
    id: Identifier
    action_id: Identifier
    transition_id: Identifier
    expected_page_id: Identifier
    expected_state_id: Identifier
    evidence_ids: Tuple[Identifier, ...] = Field(default=(), max_length=30)


class Journey(_StrictModel):
    id: Identifier
    name: ShortText
    description: LongText
    role_id: Identifier
    requirement_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=50)
    start_page_id: Identifier
    start_state_id: Identifier
    steps: Tuple[JourneyStep, ...] = Field(min_length=1, max_length=50)


class AcceptanceAssertion(_StrictModel):
    kind: Literal[
        "route",
        "visible",
        "state",
        "data",
        "count",
        "accessibility",
        "no_runtime_errors",
    ]
    description: LongText
    page_id: Optional[Identifier] = None
    state_id: Optional[Identifier] = None
    evidence_id: Optional[Identifier] = None
    expected: Optional[ShortText] = None


class AcceptanceTest(_StrictModel):
    id: Identifier
    name: ShortText
    description: LongText
    requirement_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=50)
    journey_id: Optional[Identifier] = None
    assertions: Tuple[AcceptanceAssertion, ...] = Field(min_length=1, max_length=50)


class TraceabilityLink(_StrictModel):
    requirement_id: Identifier
    capability_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=30)
    page_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=30)
    evidence_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=50)
    journey_ids: Tuple[Identifier, ...] = Field(default=(), max_length=20)
    acceptance_test_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=30)


class DeferredScopeItem(_StrictModel):
    id: Identifier
    name: ShortText
    description: LongText
    reason: LongText
    requirement_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=50)
    target_release: Optional[ShortText] = None


class AppSpec(_StrictModel):
    """Canonical application specification consumed by deterministic projections."""

    schema_version: Literal["1.0"]
    product_intent: ProductIntent
    requirements: Tuple[Requirement, ...] = Field(min_length=1, max_length=100)
    assumptions: Tuple[Assumption, ...] = Field(default=(), max_length=50)
    open_questions: Tuple[OpenQuestion, ...] = Field(default=(), max_length=50)
    roles: Tuple[Role, ...] = Field(min_length=1, max_length=20)
    entities: Tuple[Entity, ...] = Field(default=(), max_length=50)
    capabilities: Tuple[Capability, ...] = Field(min_length=1, max_length=100)
    pages: Tuple[Page, ...] = Field(min_length=1, max_length=100)
    states: Tuple[State, ...] = Field(min_length=1, max_length=300)
    actions: Tuple[Action, ...] = Field(default=(), max_length=400)
    transitions: Tuple[Transition, ...] = Field(default=(), max_length=500)
    evidence: Tuple[Evidence, ...] = Field(min_length=1, max_length=400)
    journeys: Tuple[Journey, ...] = Field(default=(), max_length=100)
    acceptance_tests: Tuple[AcceptanceTest, ...] = Field(min_length=1, max_length=200)
    traceability: Tuple[TraceabilityLink, ...] = Field(default=(), max_length=100)
    deferred_scope: Tuple[DeferredScopeItem, ...] = Field(default=(), max_length=100)

    @field_validator(
        "requirements",
        "assumptions",
        "open_questions",
        "roles",
        "entities",
        "capabilities",
        "pages",
        "states",
        "actions",
        "transitions",
        "evidence",
        "journeys",
        "acceptance_tests",
        "deferred_scope",
    )
    @classmethod
    def _reject_duplicate_local_ids(cls, values: tuple) -> tuple:
        ids = [item.id for item in values]
        if len(ids) != len(set(ids)):
            raise ValueError("IDs must be unique within each AppSpec collection")
        return values

    @field_validator("traceability")
    @classmethod
    def _reject_duplicate_traceability_requirements(
        cls, values: Tuple[TraceabilityLink, ...]
    ) -> Tuple[TraceabilityLink, ...]:
        requirement_ids = [item.requirement_id for item in values]
        if len(requirement_ids) != len(set(requirement_ids)):
            raise ValueError("traceability may contain at most one link per requirement")
        return values


__all__ = [
    "APP_SPEC_SCHEMA_VERSION",
    "AcceptanceAssertion",
    "AcceptanceTest",
    "Action",
    "AppSpec",
    "Assumption",
    "Capability",
    "DeferredScopeItem",
    "Entity",
    "EntityField",
    "Evidence",
    "Journey",
    "JourneyStep",
    "OpenQuestion",
    "Page",
    "ProductIntent",
    "Requirement",
    "Role",
    "State",
    "StateEffect",
    "TraceabilityLink",
    "Transition",
]
