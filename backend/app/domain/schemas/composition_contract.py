"""Shared strict contracts for Phase 3A composition artifacts."""
from __future__ import annotations

from typing import Literal, Tuple

from pydantic import Field, StrictBool, StrictFloat, StrictInt, model_validator

from app.domain.schemas.design_contract import (
    DesignArtifactRef,
    DesignContractRefs,
    Identifier,
    LongText,
    Sha256,
    ShortText,
    StrictDesignModel,
)


COMPOSITION_CONTRACT_POLICY_REVISION = "2026-07-24.1"
COMPOSITION_CONTRACT_SCHEMA_VERSION = "1.0"

CompositionArtifactKind = Literal[
    "page_purpose_contract",
    "business_component_plan",
    "content_data_plan",
    "interaction_contract",
    "component_dependency_graph",
]


class CompositionContractRefs(StrictDesignModel):
    request_id: StrictInt = Field(ge=1)
    target_tier: Literal[1, 2, 3] = 1
    design_contract_refs: DesignContractRefs
    product_strategy_v2_ref: DesignArtifactRef
    information_architecture_ref: DesignArtifactRef
    design_dna_ref: DesignArtifactRef

    @model_validator(mode="after")
    def _reference_kinds_and_request(self) -> "CompositionContractRefs":
        if self.request_id != self.design_contract_refs.request_id:
            raise ValueError("Composition and design request IDs must match")
        expected = (
            (self.product_strategy_v2_ref, "product_strategy_v2"),
            (
                self.information_architecture_ref,
                "information_architecture",
            ),
            (self.design_dna_ref, "design_dna"),
        )
        if any(ref.artifact_kind != kind for ref, kind in expected):
            raise ValueError("Phase 2 artifact reference kinds are invalid")
        return self


class CompositionArtifactRef(StrictDesignModel):
    id: StrictInt = Field(ge=1)
    artifact_kind: CompositionArtifactKind
    schema_version: str = Field(min_length=1, max_length=32)
    sha256: Sha256


class CompositionValidationIssue(StrictDesignModel):
    code: str = Field(min_length=1, max_length=96)
    path: str = Field(default="", max_length=400)
    related_ids: Tuple[Identifier, ...] = Field(default=(), max_length=60)
    message: str = Field(default="", max_length=1000)


class CompositionValidationReport(StrictDesignModel):
    passed: StrictBool
    issues: Tuple[CompositionValidationIssue, ...] = ()

    @model_validator(mode="after")
    def _consistent(self) -> "CompositionValidationReport":
        if self.passed and self.issues:
            raise ValueError("A passing report cannot contain issues")
        if not self.passed and not self.issues:
            raise ValueError("A failing report must contain issues")
        return self


class CompositionStageMetrics(StrictDesignModel):
    stage: CompositionArtifactKind
    effective_model: str = Field(min_length=1, max_length=240)
    provider: str = Field(min_length=1, max_length=80)
    model_family: str = Field(min_length=1, max_length=80)
    prompt_revision: str = Field(min_length=1, max_length=64)
    cache_hit: StrictBool
    provider_call_count: StrictInt = Field(ge=0, le=5)
    validation_retry_count: StrictInt = Field(ge=0, le=4)
    validation_retry_reasons: Tuple[str, ...] = Field(default=(), max_length=4)
    transport_retry_count: StrictInt = Field(ge=0)
    prompt_tokens: StrictInt = Field(ge=0)
    completion_tokens: StrictInt = Field(ge=0)
    total_tokens: StrictInt = Field(ge=0)
    cost_usd: StrictFloat = Field(ge=0)
    latency_ms: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def _metric_consistency(self) -> "CompositionStageMetrics":
        if self.total_tokens < self.prompt_tokens + self.completion_tokens:
            raise ValueError(
                "total_tokens cannot be less than prompt plus completion"
            )
        if self.cache_hit and (
            self.provider_call_count
            or self.validation_retry_count
            or self.transport_retry_count
            or self.total_tokens
            or self.cost_usd
        ):
            raise ValueError("A cache hit cannot record provider usage")
        if self.validation_retry_count != len(self.validation_retry_reasons):
            raise ValueError("Every validation retry requires one reason")
        deterministic = {
            "page_purpose_contract",
            "interaction_contract",
            "component_dependency_graph",
        }
        if self.stage in deterministic and (
            self.provider_call_count
            or self.validation_retry_count
            or self.transport_retry_count
            or self.total_tokens
            or self.cost_usd
        ):
            raise ValueError("Deterministic stages cannot record AI usage")
        return self


__all__ = [
    "COMPOSITION_CONTRACT_POLICY_REVISION",
    "COMPOSITION_CONTRACT_SCHEMA_VERSION",
    "CompositionArtifactKind",
    "CompositionArtifactRef",
    "CompositionContractRefs",
    "CompositionStageMetrics",
    "CompositionValidationIssue",
    "CompositionValidationReport",
    "Identifier",
    "LongText",
    "ShortText",
]
