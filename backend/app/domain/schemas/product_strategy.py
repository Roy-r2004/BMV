"""Strict inferred product-strategy contract for preview generator v2."""
from __future__ import annotations

from typing import Annotated, Literal, Tuple

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    model_validator,
)

from app.domain.schemas.design_contract import DesignContractRefs


PRODUCT_STRATEGY_SCHEMA_VERSION = "1.0"
PRODUCT_STRATEGY_V2_SCHEMA_VERSION = "2.0"

Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*$",
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
SourceEvidenceRef = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=240,
        pattern=r"^(?:customer_input|reference_evidence)(?:\.[A-Za-z0-9_]+)+$",
    ),
]


class _FrozenStrategyModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


class AudienceHypothesis(_FrozenStrategyModel):
    id: Identifier
    description: LongText
    confidence: Literal["low", "medium", "high"]
    evidence_refs: Tuple[SourceEvidenceRef, ...] = Field(min_length=1, max_length=20)


class ProductSurface(_FrozenStrategyModel):
    id: Identifier
    kind: Literal["public", "ops"]
    required: StrictBool
    purpose: LongText
    evidence_refs: Tuple[SourceEvidenceRef, ...] = Field(min_length=1, max_length=20)


class CapabilityHypothesis(_FrozenStrategyModel):
    id: Identifier
    name: ShortText
    outcome: LongText
    surface: Literal["public", "ops"]
    priority: Literal["must", "should", "could"]
    confidence: Literal["low", "medium", "high"]
    evidence_refs: Tuple[SourceEvidenceRef, ...] = Field(min_length=1, max_length=20)


class AiFeatureHypothesis(_FrozenStrategyModel):
    id: Identifier
    name: ShortText
    description: LongText
    surface: Literal["public", "ops"]
    confidence: Literal["low", "medium", "high"]
    evidence_refs: Tuple[SourceEvidenceRef, ...] = Field(min_length=1, max_length=20)


class StrategyAssumption(_FrozenStrategyModel):
    id: Identifier
    statement: LongText
    rationale: LongText
    confidence: Literal["low", "medium", "high"]


class StrategyRisk(_FrozenStrategyModel):
    id: Identifier
    statement: LongText
    mitigation: LongText


class ProductStrategy(_FrozenStrategyModel):
    schema_version: str = Field(
        default=PRODUCT_STRATEGY_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    origin: Literal["legacy_blueprint_projection"]
    product_name: ShortText
    product_kind: Literal[
        "public_website",
        "storefront",
        "booking_service",
        "hybrid",
        "saas_workspace",
        "internal_ops",
    ]
    positioning: LongText
    primary_outcome: LongText
    audience_hypotheses: Tuple[AudienceHypothesis, ...] = Field(
        min_length=1,
        max_length=20,
    )
    surfaces: Tuple[ProductSurface, ...] = Field(min_length=1, max_length=2)
    capability_hypotheses: Tuple[CapabilityHypothesis, ...] = Field(
        min_length=1,
        max_length=100,
    )
    ai_feature_hypotheses: Tuple[AiFeatureHypothesis, ...] = Field(
        default=(),
        max_length=50,
    )
    assumptions: Tuple[StrategyAssumption, ...] = Field(default=(), max_length=50)
    risks: Tuple[StrategyRisk, ...] = Field(default=(), max_length=50)


class PositioningV2(_FrozenStrategyModel):
    category: ShortText
    audience: LongText
    promise: LongText
    problem_frame: LongText


class PrioritizedOutcomeV2(_FrozenStrategyModel):
    requirement_id: Identifier
    tier: Literal[1, 2, 3]
    rationale: LongText


class SurfaceStrategyV2(_FrozenStrategyModel):
    surface: Literal["public", "ops"]
    role_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=20)
    outcome_requirement_ids: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=100,
    )
    purpose: LongText


class DifferentiatorV2(_FrozenStrategyModel):
    id: Identifier
    statement: LongText
    proof_requirement_ids: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=30,
    )
    design_implication: LongText


class StrategyRiskV2(_FrozenStrategyModel):
    id: Identifier
    statement: LongText
    mitigation: LongText
    related_requirement_ids: Tuple[Identifier, ...] = Field(
        default=(),
        max_length=30,
    )


class StrategyAssumptionV2(_FrozenStrategyModel):
    id: Identifier
    statement: LongText
    evidence_refs: Tuple[SourceEvidenceRef, ...] = Field(
        min_length=1,
        max_length=20,
    )
    impact: LongText


class ProductStrategyV2(_FrozenStrategyModel):
    """AI-authored downstream strategy; never replaces the Phase 1A seed."""

    schema_version: str = Field(
        default=PRODUCT_STRATEGY_V2_SCHEMA_VERSION,
        pattern=r"^2\.0$",
    )
    contract_refs: DesignContractRefs
    positioning: PositioningV2
    primary_outcome_requirement_id: Identifier
    prioritized_outcomes: Tuple[PrioritizedOutcomeV2, ...] = Field(
        min_length=1,
        max_length=100,
    )
    surfaces: Tuple[SurfaceStrategyV2, ...] = Field(
        min_length=1,
        max_length=2,
    )
    differentiators: Tuple[DifferentiatorV2, ...] = Field(
        min_length=1,
        max_length=12,
    )
    risks: Tuple[StrategyRiskV2, ...] = Field(default=(), max_length=30)
    assumptions: Tuple[StrategyAssumptionV2, ...] = Field(
        default=(),
        max_length=30,
    )
    exclusions: Tuple[ShortText, ...] = Field(default=(), max_length=30)

    @model_validator(mode="after")
    def _unique_ids(self) -> "ProductStrategyV2":
        for name, values in (
            (
                "prioritized_outcomes",
                tuple(item.requirement_id for item in self.prioritized_outcomes),
            ),
            ("surfaces", tuple(item.surface for item in self.surfaces)),
            ("differentiators", tuple(item.id for item in self.differentiators)),
            ("risks", tuple(item.id for item in self.risks)),
            ("assumptions", tuple(item.id for item in self.assumptions)),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{name} cannot contain duplicate IDs")
        return self


__all__ = [
    "AiFeatureHypothesis",
    "AudienceHypothesis",
    "CapabilityHypothesis",
    "DifferentiatorV2",
    "PRODUCT_STRATEGY_SCHEMA_VERSION",
    "PRODUCT_STRATEGY_V2_SCHEMA_VERSION",
    "PositioningV2",
    "PrioritizedOutcomeV2",
    "ProductStrategy",
    "ProductStrategyV2",
    "ProductSurface",
    "StrategyAssumptionV2",
    "StrategyAssumption",
    "StrategyRiskV2",
    "StrategyRisk",
    "SurfaceStrategyV2",
]
