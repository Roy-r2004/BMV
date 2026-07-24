"""Shared strict contracts for the three Phase 2 design artifacts."""
from __future__ import annotations

from typing import Annotated, Literal, Tuple

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StringConstraints,
    model_validator,
)

from app.domain.schemas.preview_tier import (
    CanonicalAppSpecRef,
    CustomerSourceRef,
    ProductStrategyRef,
)


DESIGN_CONTRACT_SCHEMA_VERSION = "1.0"
DESIGN_CONTRACT_POLICY_REVISION = "2026-07-24.1"

Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*$",
    ),
]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
ShortText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=240),
]
LongText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
]


class StrictDesignModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


class TierArtifactRef(StrictDesignModel):
    id: StrictInt = Field(ge=1)
    tier: Literal[1, 2, 3]
    sha256: Sha256
    selection_policy_revision: str = Field(min_length=1, max_length=64)


class DesignContractRefs(StrictDesignModel):
    request_id: StrictInt = Field(ge=1)
    customer_source_ref: CustomerSourceRef
    product_strategy_seed_ref: ProductStrategyRef
    app_spec_ref: CanonicalAppSpecRef
    tier_refs: Tuple[TierArtifactRef, TierArtifactRef, TierArtifactRef]

    @model_validator(mode="after")
    def _ordered_tiers(self) -> "DesignContractRefs":
        if tuple(ref.tier for ref in self.tier_refs) != (1, 2, 3):
            raise ValueError("tier_refs must contain Tier 1, Tier 2, Tier 3")
        revisions = {
            ref.selection_policy_revision for ref in self.tier_refs
        }
        if len(revisions) != 1:
            raise ValueError("tier_refs must use one selection-policy revision")
        return self


class DesignArtifactRef(StrictDesignModel):
    id: StrictInt = Field(ge=1)
    artifact_kind: Literal[
        "product_strategy_v2",
        "information_architecture",
        "design_dna",
    ]
    schema_version: str = Field(min_length=1, max_length=32)
    sha256: Sha256


class DesignValidationIssue(StrictDesignModel):
    code: str = Field(min_length=1, max_length=96)
    path: str = Field(default="", max_length=400)
    related_ids: Tuple[Identifier, ...] = Field(default=(), max_length=50)
    message: str = Field(default="", max_length=1000)


class DesignValidationReport(StrictDesignModel):
    passed: StrictBool
    issues: Tuple[DesignValidationIssue, ...] = ()

    @model_validator(mode="after")
    def _consistent(self) -> "DesignValidationReport":
        if self.passed and self.issues:
            raise ValueError("A passing report cannot contain issues")
        if not self.passed and not self.issues:
            raise ValueError("A failing report must contain issues")
        return self


class DesignStageMetrics(StrictDesignModel):
    stage: Literal[
        "product_strategy_v2",
        "information_architecture",
        "design_dna",
    ]
    effective_model: str = Field(min_length=1, max_length=240)
    provider: str = Field(min_length=1, max_length=80)
    model_family: str = Field(min_length=1, max_length=80)
    prompt_revision: str = Field(min_length=1, max_length=64)
    cache_hit: StrictBool
    provider_call_count: StrictInt = Field(ge=0, le=2)
    validation_retry_count: StrictInt = Field(ge=0, le=1)
    validation_retry_reasons: Tuple[str, ...] = Field(default=(), max_length=1)
    transport_retry_count: StrictInt = Field(ge=0)
    prompt_tokens: StrictInt = Field(ge=0)
    completion_tokens: StrictInt = Field(ge=0)
    total_tokens: StrictInt = Field(ge=0)
    cost_usd: StrictFloat = Field(ge=0)
    latency_ms: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def _metric_consistency(self) -> "DesignStageMetrics":
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
        return self


__all__ = [
    "DESIGN_CONTRACT_POLICY_REVISION",
    "DESIGN_CONTRACT_SCHEMA_VERSION",
    "DesignArtifactRef",
    "DesignContractRefs",
    "DesignStageMetrics",
    "DesignValidationIssue",
    "DesignValidationReport",
    "Identifier",
    "LongText",
    "Sha256",
    "ShortText",
    "StrictDesignModel",
    "TierArtifactRef",
]
