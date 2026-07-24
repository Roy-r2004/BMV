"""Deterministically projected Tier 1 interaction contracts."""
from __future__ import annotations

from typing import Literal, Tuple

from pydantic import Field, StrictInt, model_validator

from app.domain.schemas.app_spec import EffectScalar, RoutePath
from app.domain.schemas.composition_contract import (
    CompositionArtifactRef,
    CompositionContractRefs,
    Identifier,
    LongText,
    ShortText,
)
from app.domain.schemas.design_contract import StrictDesignModel


INTERACTION_CONTRACT_SCHEMA_VERSION = "1.0"


class ProjectedStateEffect(StrictDesignModel):
    entity_id: Identifier
    field_id: Identifier
    operation: Literal[
        "set",
        "clear",
        "increment",
        "decrement",
        "append",
        "remove",
    ]
    value: EffectScalar | None = None


class ProjectedTransition(StrictDesignModel):
    transition_id: Identifier
    from_state_id: Identifier
    to_state_id: Identifier
    description: LongText
    preconditions: Tuple[ShortText, ...] = Field(default=(), max_length=20)
    postconditions: Tuple[ShortText, ...] = Field(default=(), max_length=20)
    effects: Tuple[ProjectedStateEffect, ...] = Field(default=(), max_length=30)
    success_evidence_ids: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=100,
    )


class BrowserAssertionProjection(StrictDesignModel):
    acceptance_test_id: Identifier
    assertion_index: StrictInt = Field(ge=0, le=49)
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
    page_id: Identifier | None = None
    route: RoutePath | None = None
    state_id: Identifier | None = None
    evidence_id: Identifier | None = None
    expected: ShortText | None = None


class InteractionProjection(StrictDesignModel):
    action_id: Identifier
    page_id: Identifier
    route: RoutePath
    role_id: Identifier
    action_kind: Literal[
        "navigate",
        "click",
        "fill",
        "select",
        "submit",
        "toggle",
    ]
    entity_id: Identifier | None = None
    trigger_component_id: Identifier
    input_collection_ids: Tuple[Identifier, ...] = Field(
        default=(),
        max_length=100,
    )
    input_field_ids: Tuple[Identifier, ...] = Field(default=(), max_length=100)
    transitions: Tuple[ProjectedTransition, ...] = Field(
        min_length=1,
        max_length=100,
    )
    journey_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=100)
    acceptance_test_ids: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=200,
    )
    browser_assertions: Tuple[BrowserAssertionProjection, ...] = Field(
        min_length=1,
        max_length=500,
    )


class InteractionContract(StrictDesignModel):
    schema_version: str = Field(
        default=INTERACTION_CONTRACT_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    contract_refs: CompositionContractRefs
    page_purpose_ref: CompositionArtifactRef
    business_component_plan_ref: CompositionArtifactRef
    content_data_plan_ref: CompositionArtifactRef
    interactions: Tuple[InteractionProjection, ...] = Field(
        min_length=1,
        max_length=400,
    )

    @model_validator(mode="after")
    def _unique_actions_and_kinds(self) -> "InteractionContract":
        expected = (
            (self.page_purpose_ref, "page_purpose_contract"),
            (
                self.business_component_plan_ref,
                "business_component_plan",
            ),
            (self.content_data_plan_ref, "content_data_plan"),
        )
        if any(ref.artifact_kind != kind for ref, kind in expected):
            raise ValueError("Interaction upstream reference kind is invalid")
        action_ids = tuple(item.action_id for item in self.interactions)
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("interactions cannot repeat action IDs")
        return self


__all__ = [
    "BrowserAssertionProjection",
    "INTERACTION_CONTRACT_SCHEMA_VERSION",
    "InteractionContract",
    "InteractionProjection",
    "ProjectedStateEffect",
    "ProjectedTransition",
]
