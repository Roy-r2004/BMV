"""AI-authored, business-specific visible component contracts."""
from __future__ import annotations

from typing import Literal, Tuple

from pydantic import Field, StrictBool, model_validator

from app.domain.schemas.composition_contract import (
    CompositionArtifactRef,
    CompositionContractRefs,
    Identifier,
    LongText,
    ShortText,
)
from app.domain.schemas.design_contract import StrictDesignModel


BUSINESS_COMPONENT_PLAN_SCHEMA_VERSION = "1.0"


class BusinessComponent(StrictDesignModel):
    component_id: Identifier
    name: ShortText
    purpose: LongText
    component_kind: Literal[
        "business_action",
        "business_evidence",
        "business_data_view",
        "business_content",
        "business_navigation",
    ]
    domain_language: Tuple[ShortText, ...] = Field(min_length=1, max_length=20)
    page_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=100)
    role_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=20)
    requirement_ids: Tuple[Identifier, ...] = Field(
        default=(),
        max_length=100,
    )
    entity_ids: Tuple[Identifier, ...] = Field(default=(), max_length=50)
    capability_ids: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=100,
    )
    state_ids: Tuple[Identifier, ...] = Field(default=(), max_length=300)
    action_ids: Tuple[Identifier, ...] = Field(default=(), max_length=400)
    evidence_ids: Tuple[Identifier, ...] = Field(default=(), max_length=400)
    content_responsibilities: Tuple[ShortText, ...] = Field(
        default=(),
        max_length=30,
    )
    data_responsibilities: Tuple[ShortText, ...] = Field(
        default=(),
        max_length=30,
    )
    interaction_responsibilities: Tuple[ShortText, ...] = Field(
        default=(),
        max_length=30,
    )
    requires_component_ids: Tuple[Identifier, ...] = Field(
        default=(),
        max_length=100,
    )
    shared_across_pages: StrictBool

    @model_validator(mode="after")
    def _unique_and_grounded(self) -> "BusinessComponent":
        for name in (
            "domain_language",
            "page_ids",
            "role_ids",
            "requirement_ids",
            "entity_ids",
            "capability_ids",
            "state_ids",
            "action_ids",
            "evidence_ids",
            "requires_component_ids",
        ):
            values = getattr(self, name)
            if len(values) != len(set(values)):
                raise ValueError(f"{name} cannot contain duplicates")
        if not (
            self.entity_ids
            or self.capability_ids
            or self.state_ids
            or self.action_ids
            or self.evidence_ids
        ):
            raise ValueError("A business component needs canonical grounding")
        if self.component_id in self.requires_component_ids:
            raise ValueError("A component cannot depend on itself")
        return self


class PageComponentComposition(StrictDesignModel):
    page_id: Identifier
    ordered_component_ids: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=100,
    )


class ActionTriggerBinding(StrictDesignModel):
    action_id: Identifier
    component_id: Identifier
    trigger_label: ShortText


class ComponentStateBinding(StrictDesignModel):
    component_id: Identifier
    state_id: Identifier
    visible_evidence_ids: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=100,
    )


class BusinessComponentPlan(StrictDesignModel):
    schema_version: str = Field(
        default=BUSINESS_COMPONENT_PLAN_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    contract_refs: CompositionContractRefs
    page_purpose_ref: CompositionArtifactRef
    components: Tuple[BusinessComponent, ...] = Field(
        min_length=1,
        max_length=300,
    )
    page_compositions: Tuple[PageComponentComposition, ...] = Field(
        min_length=1,
        max_length=100,
    )
    action_trigger_bindings: Tuple[ActionTriggerBinding, ...] = Field(
        default=(),
        max_length=400,
    )
    component_state_bindings: Tuple[ComponentStateBinding, ...] = Field(
        default=(),
        max_length=400,
    )

    @model_validator(mode="after")
    def _unique_local_keys(self) -> "BusinessComponentPlan":
        if self.page_purpose_ref.artifact_kind != "page_purpose_contract":
            raise ValueError("page_purpose_ref has the wrong artifact kind")
        groups = (
            ("components", tuple(item.component_id for item in self.components)),
            (
                "page_compositions",
                tuple(item.page_id for item in self.page_compositions),
            ),
            (
                "action_trigger_bindings",
                tuple(item.action_id for item in self.action_trigger_bindings),
            ),
            (
                "component_state_bindings",
                tuple(
                    (item.component_id, item.state_id)
                    for item in self.component_state_bindings
                ),
            ),
        )
        for name, values in groups:
            if len(values) != len(set(values)):
                raise ValueError(f"{name} cannot contain duplicate keys")
        return self


__all__ = [
    "ActionTriggerBinding",
    "BUSINESS_COMPONENT_PLAN_SCHEMA_VERSION",
    "BusinessComponent",
    "BusinessComponentPlan",
    "ComponentStateBinding",
    "PageComponentComposition",
]
