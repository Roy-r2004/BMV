"""Strict inferred product-strategy contract for preview generator v2."""
from __future__ import annotations

from typing import Annotated, Literal, Tuple

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
)


PRODUCT_STRATEGY_SCHEMA_VERSION = "1.0"

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


__all__ = [
    "AiFeatureHypothesis",
    "AudienceHypothesis",
    "CapabilityHypothesis",
    "PRODUCT_STRATEGY_SCHEMA_VERSION",
    "ProductStrategy",
    "ProductSurface",
    "StrategyAssumption",
    "StrategyRisk",
]
