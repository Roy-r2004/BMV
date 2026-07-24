"""Strict visual-direction artifact without source or component choices."""
from __future__ import annotations

from typing import Literal, Tuple

from pydantic import Field, StrictInt, model_validator

from app.domain.schemas.design_contract import (
    DesignArtifactRef,
    DesignContractRefs,
    LongText,
    ShortText,
    StrictDesignModel,
)


DESIGN_DNA_SCHEMA_VERSION = "1.0"


class CompositionDirection(StrictDesignModel):
    hierarchy: LongText
    rhythm: LongText
    emphasis: LongText
    layering: LongText


class NavigationCharacter(StrictDesignModel):
    character: LongText
    orientation: Literal["horizontal", "vertical", "hybrid", "contextual"]
    wayfinding: LongText
    active_state_direction: LongText


class TypographyDirection(StrictDesignModel):
    voice: LongText
    display_direction: LongText
    body_direction: LongText
    scale_behavior: LongText
    weight_contrast: LongText


class DensityDirection(StrictDesignModel):
    public_surface: Literal["airy", "balanced", "dense"]
    operations_surface: Literal["airy", "balanced", "dense"]
    rationale: LongText


class ImageryDirection(StrictDesignModel):
    subject_direction: LongText
    treatment: LongText
    placement: LongText
    prohibited_treatments: Tuple[ShortText, ...] = Field(
        min_length=1,
        max_length=20,
    )


class GeometryDirection(StrictDesignModel):
    shape_language: LongText
    container_behavior: LongText
    radius_direction: LongText
    border_direction: LongText
    elevation_direction: LongText


class MotionDirection(StrictDesignModel):
    character: LongText
    entrance_behavior: LongText
    interaction_feedback: LongText
    duration_band_ms: Tuple[StrictInt, StrictInt]
    reduced_motion: LongText

    @model_validator(mode="after")
    def _duration_order(self) -> "MotionDirection":
        low, high = self.duration_band_ms
        if low < 0 or high < low or high > 2000:
            raise ValueError("duration_band_ms must be ordered within 0..2000")
        return self


class ColorTokenDirection(StrictDesignModel):
    semantic_role: Literal[
        "background",
        "surface",
        "foreground",
        "muted",
        "accent",
        "success",
        "warning",
        "danger",
    ]
    direction: LongText
    contrast_intent: LongText


class DesignFingerprint(StrictDesignModel):
    name: ShortText
    signature_traits: Tuple[ShortText, ...] = Field(min_length=3, max_length=10)
    recurring_motif: LongText
    differentiation_guard: LongText


class DesignDNA(StrictDesignModel):
    schema_version: str = Field(
        default=DESIGN_DNA_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    contract_refs: DesignContractRefs
    product_strategy_ref: DesignArtifactRef
    information_architecture_ref: DesignArtifactRef
    reference_mode: Literal["none", "textual_analysis", "vision"]
    composition: CompositionDirection
    navigation: NavigationCharacter
    typography: TypographyDirection
    density: DensityDirection
    imagery: ImageryDirection
    geometry: GeometryDirection
    motion: MotionDirection
    color_tokens: Tuple[ColorTokenDirection, ...] = Field(
        min_length=8,
        max_length=8,
    )
    avoid_list: Tuple[ShortText, ...] = Field(min_length=3, max_length=30)
    fingerprint: DesignFingerprint

    @model_validator(mode="after")
    def _upstream_kinds_and_colors(self) -> "DesignDNA":
        if self.product_strategy_ref.artifact_kind != "product_strategy_v2":
            raise ValueError("product_strategy_ref must reference ProductStrategyV2")
        if (
            self.information_architecture_ref.artifact_kind
            != "information_architecture"
        ):
            raise ValueError(
                "information_architecture_ref must reference InformationArchitecture"
            )
        roles = tuple(item.semantic_role for item in self.color_tokens)
        if len(roles) != len(set(roles)):
            raise ValueError("color_tokens cannot repeat semantic roles")
        return self


__all__ = [
    "ColorTokenDirection",
    "CompositionDirection",
    "DESIGN_DNA_SCHEMA_VERSION",
    "DensityDirection",
    "DesignDNA",
    "DesignFingerprint",
    "GeometryDirection",
    "ImageryDirection",
    "MotionDirection",
    "NavigationCharacter",
    "TypographyDirection",
]
