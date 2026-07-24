"""Strict Information Architecture artifact for preview generator v2."""
from __future__ import annotations

from typing import Literal, Tuple

from pydantic import Field, StrictBool, model_validator

from app.domain.schemas.design_contract import (
    DesignArtifactRef,
    DesignContractRefs,
    Identifier,
    LongText,
    ShortText,
    StrictDesignModel,
)
from app.domain.schemas.app_spec import RoutePath


INFORMATION_ARCHITECTURE_SCHEMA_VERSION = "1.0"


class NavigationGroup(StrictDesignModel):
    id: Identifier
    label: ShortText
    surface: Literal["public", "ops"]
    role_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=20)
    page_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=100)


class RoleRouteAccess(StrictDesignModel):
    role_id: Identifier
    entry_page_id: Identifier
    accessible_page_ids: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=100,
    )


class MobileBehavior(StrictDesignModel):
    navigation: Literal[
        "persistent",
        "collapsed_menu",
        "bottom_navigation",
        "contextual",
    ]
    primary_action: Literal[
        "inline",
        "sticky",
        "floating",
        "contextual",
        "none",
    ]
    content_priority: Tuple[ShortText, ...] = Field(min_length=1, max_length=8)
    data_presentation: Literal[
        "not_applicable",
        "stacked_cards",
        "horizontal_scroll",
        "progressive_disclosure",
        "condensed_table",
    ]
    density_adjustment: Literal["preserve", "relax", "compact"]


class PageArchitecture(StrictDesignModel):
    page_id: Identifier
    route: RoutePath
    surface: Literal["public", "ops"]
    purpose: LongText
    role_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=20)
    required_outcome_requirement_ids: Tuple[Identifier, ...] = Field(
        default=(),
        max_length=100,
    )
    required_action_ids: Tuple[Identifier, ...] = Field(
        default=(),
        max_length=100,
    )
    required_evidence_ids: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=100,
    )
    journey_ids: Tuple[Identifier, ...] = Field(default=(), max_length=100)
    navigation_visibility: Literal["primary", "secondary", "deep_link"]
    deep_link_reason: LongText | None = None
    mobile: MobileBehavior

    @model_validator(mode="after")
    def _deep_link_reason(self) -> "PageArchitecture":
        if self.navigation_visibility == "deep_link" and not self.deep_link_reason:
            raise ValueError("Deep-link pages require deep_link_reason")
        if self.navigation_visibility != "deep_link" and self.deep_link_reason:
            raise ValueError("Only deep-link pages may define deep_link_reason")
        return self


class InformationArchitecture(StrictDesignModel):
    schema_version: str = Field(
        default=INFORMATION_ARCHITECTURE_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    contract_refs: DesignContractRefs
    product_strategy_ref: DesignArtifactRef
    navigation_principle: LongText
    navigation_groups: Tuple[NavigationGroup, ...] = Field(
        min_length=1,
        max_length=50,
    )
    role_access: Tuple[RoleRouteAccess, ...] = Field(
        min_length=1,
        max_length=20,
    )
    pages: Tuple[PageArchitecture, ...] = Field(min_length=1, max_length=100)
    mobile_global_behavior: LongText
    preserves_canonical_routes: StrictBool
    preserves_all_tier_3_pages: StrictBool

    @model_validator(mode="after")
    def _unique_local_ids(self) -> "InformationArchitecture":
        for name, values in (
            ("navigation_groups", tuple(item.id for item in self.navigation_groups)),
            ("role_access", tuple(item.role_id for item in self.role_access)),
            ("pages", tuple(item.page_id for item in self.pages)),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{name} cannot contain duplicate IDs")
        if self.product_strategy_ref.artifact_kind != "product_strategy_v2":
            raise ValueError("product_strategy_ref must reference ProductStrategyV2")
        return self


__all__ = [
    "INFORMATION_ARCHITECTURE_SCHEMA_VERSION",
    "InformationArchitecture",
    "MobileBehavior",
    "NavigationGroup",
    "PageArchitecture",
    "RoleRouteAccess",
]
