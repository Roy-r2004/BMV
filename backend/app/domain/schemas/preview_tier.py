"""Strict reference-only contracts for cumulative preview tiers."""
from __future__ import annotations

from typing import Annotated, Literal, Tuple

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    model_validator,
)


PREVIEW_TIER_SCHEMA_VERSION = "1.0"
TIER_SELECTION_POLICY_REVISION = "2026-07-25.1"

Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*$",
    ),
]
Sha256 = Annotated[
    str,
    StringConstraints(pattern=r"^[a-f0-9]{64}$"),
]


class _ReferenceOnlyModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


class CustomerSourceRef(_ReferenceOnlyModel):
    id: StrictInt = Field(ge=1)
    sha256: Sha256


class ProductStrategyRef(_ReferenceOnlyModel):
    id: StrictInt = Field(ge=1)
    revision: StrictInt = Field(ge=1)
    sha256: Sha256


class CanonicalAppSpecRef(_ReferenceOnlyModel):
    id: StrictInt = Field(ge=1)
    revision: StrictInt = Field(ge=1)
    schema_version: str = Field(min_length=1, max_length=32)
    sha256: Sha256


class TierReferenceSet(_ReferenceOnlyModel):
    requirement_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=100)
    role_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=20)
    entity_ids: Tuple[Identifier, ...] = Field(default=(), max_length=50)
    capability_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=100)
    page_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=100)
    state_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=300)
    action_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=400)
    transition_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=500)
    evidence_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=400)
    journey_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=100)
    acceptance_test_ids: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=200,
    )

    @model_validator(mode="after")
    def _unique_ids(self) -> "TierReferenceSet":
        for field_name in type(self).model_fields:
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} cannot contain duplicate IDs")
        return self


class RequirementCompletionProof(_ReferenceOnlyModel):
    requirement_id: Identifier
    evidence_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=50)
    journey_ids: Tuple[Identifier, ...] = Field(default=(), max_length=20)
    acceptance_test_ids: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=30,
    )


class PrimaryJourneyProof(_ReferenceOnlyModel):
    requirement_id: Identifier
    journey_id: Identifier
    page_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=50)
    action_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=50)
    transition_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=50)
    success_evidence_ids: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=50,
    )
    acceptance_test_id: Identifier


class PreviewTierArtifact(_ReferenceOnlyModel):
    tier_schema_version: str = Field(
        default=PREVIEW_TIER_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    selection_policy_revision: str = Field(min_length=1, max_length=64)
    tier: Literal[1, 2, 3]
    intent: Literal[
        "primary_outcome",
        "all_must_requirements",
        "full_active_contract",
    ]
    request_id: StrictInt = Field(ge=1)
    extends_tier: Literal[1, 2] | None
    customer_source_ref: CustomerSourceRef
    product_strategy_ref: ProductStrategyRef
    app_spec_ref: CanonicalAppSpecRef
    primary_journey_proof: PrimaryJourneyProof
    references: TierReferenceSet
    completion_proofs: Tuple[RequirementCompletionProof, ...] = Field(
        min_length=1,
        max_length=100,
    )

    @model_validator(mode="after")
    def _tier_shape(self) -> "PreviewTierArtifact":
        expected = {
            1: ("primary_outcome", None),
            2: ("all_must_requirements", 1),
            3: ("full_active_contract", 2),
        }[self.tier]
        if (self.intent, self.extends_tier) != expected:
            raise ValueError(
                f"Tier {self.tier} requires intent={expected[0]!r} "
                f"and extends_tier={expected[1]!r}"
            )
        proof_ids = [proof.requirement_id for proof in self.completion_proofs]
        if len(proof_ids) != len(set(proof_ids)):
            raise ValueError("completion_proofs cannot repeat a requirement")
        return self


class TierValidationIssue(_ReferenceOnlyModel):
    code: str = Field(min_length=1, max_length=96)
    path: str = Field(default="", max_length=400)
    related_ids: Tuple[Identifier, ...] = Field(default=(), max_length=30)


class TierValidationReport(_ReferenceOnlyModel):
    passed: StrictBool
    issues: Tuple[TierValidationIssue, ...] = ()

    @model_validator(mode="after")
    def _consistent_outcome(self) -> "TierValidationReport":
        if self.passed and self.issues:
            raise ValueError("A passing tier report cannot contain issues")
        if not self.passed and not self.issues:
            raise ValueError("A failing tier report must contain at least one issue")
        return self


__all__ = [
    "CanonicalAppSpecRef",
    "CustomerSourceRef",
    "PREVIEW_TIER_SCHEMA_VERSION",
    "PreviewTierArtifact",
    "PrimaryJourneyProof",
    "ProductStrategyRef",
    "RequirementCompletionProof",
    "TIER_SELECTION_POLICY_REVISION",
    "TierReferenceSet",
    "TierValidationIssue",
    "TierValidationReport",
]
