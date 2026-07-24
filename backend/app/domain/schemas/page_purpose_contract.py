"""Deterministic Tier 1 page-purpose contracts."""
from __future__ import annotations

from typing import Literal, Tuple

from pydantic import Field, model_validator

from app.domain.schemas.app_spec import RoutePath
from app.domain.schemas.composition_contract import (
    CompositionContractRefs,
    Identifier,
    LongText,
    ShortText,
)
from app.domain.schemas.design_contract import StrictDesignModel
from app.domain.schemas.information_architecture import MobileBehavior


PAGE_PURPOSE_SCHEMA_VERSION = "1.0"


class ImmutablePageConstraints(StrictDesignModel):
    route_locked: Literal[True]
    roles_locked: Literal[True]
    requirements_locked: Literal[True]
    actions_locked: Literal[True]
    transitions_locked: Literal[True]
    evidence_locked: Literal[True]
    journeys_locked: Literal[True]
    acceptance_tests_locked: Literal[True]
    invented_behavior_forbidden: Literal[True]


class ProjectedDesignConstraints(StrictDesignModel):
    composition_hierarchy: LongText
    composition_emphasis: LongText
    public_surface_density: Literal["airy", "balanced", "dense"]
    operations_surface_density: Literal["airy", "balanced", "dense"]
    motion_character: LongText
    reduced_motion: LongText
    avoid_list: Tuple[ShortText, ...] = Field(min_length=3, max_length=30)


class PagePurpose(StrictDesignModel):
    page_id: Identifier
    route: RoutePath
    surface: Literal["public", "ops"]
    goal: LongText
    role_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=20)
    requirement_ids: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=100,
    )
    outcome_requirement_ids: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=100,
    )
    capability_ids: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=100,
    )
    state_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=300)
    action_ids: Tuple[Identifier, ...] = Field(default=(), max_length=400)
    transition_ids: Tuple[Identifier, ...] = Field(default=(), max_length=500)
    evidence_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=400)
    journey_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=100)
    acceptance_test_ids: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=200,
    )
    navigation_visibility: Literal["primary", "secondary", "deep_link"]
    deep_link_reason: LongText | None = None
    mobile: MobileBehavior
    immutable: ImmutablePageConstraints

    @model_validator(mode="after")
    def _unique_references(self) -> "PagePurpose":
        for name in (
            "role_ids",
            "requirement_ids",
            "outcome_requirement_ids",
            "capability_ids",
            "state_ids",
            "action_ids",
            "transition_ids",
            "evidence_ids",
            "journey_ids",
            "acceptance_test_ids",
        ):
            values = getattr(self, name)
            if len(values) != len(set(values)):
                raise ValueError(f"{name} cannot contain duplicate IDs")
        return self


class PagePurposeContract(StrictDesignModel):
    schema_version: str = Field(
        default=PAGE_PURPOSE_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    contract_refs: CompositionContractRefs
    primary_outcome_requirement_id: Identifier
    mobile_global_behavior: LongText
    design_constraints: ProjectedDesignConstraints
    pages: Tuple[PagePurpose, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _unique_pages(self) -> "PagePurposeContract":
        ids = tuple(page.page_id for page in self.pages)
        routes = tuple(page.route for page in self.pages)
        if len(ids) != len(set(ids)):
            raise ValueError("pages cannot repeat a page ID")
        if len(routes) != len(set(routes)):
            raise ValueError("pages cannot repeat a route")
        return self


__all__ = [
    "ImmutablePageConstraints",
    "PAGE_PURPOSE_SCHEMA_VERSION",
    "PagePurpose",
    "PagePurposeContract",
    "ProjectedDesignConstraints",
]
