"""Deterministic fail-closed validation for all Phase 2 artifacts."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from app.domain.schemas.app_spec import AppSpec
from app.domain.schemas.design_contract import (
    DesignArtifactRef,
    DesignContractRefs,
    DesignValidationIssue,
    DesignValidationReport,
)
from app.domain.schemas.design_dna import DesignDNA
from app.domain.schemas.information_architecture import InformationArchitecture
from app.domain.schemas.preview_tier import PreviewTierArtifact
from app.domain.schemas.product_strategy import ProductStrategyV2


@dataclass(frozen=True)
class DesignValidationContext:
    refs: DesignContractRefs
    app_spec: AppSpec
    tiers: tuple[
        PreviewTierArtifact,
        PreviewTierArtifact,
        PreviewTierArtifact,
    ]


def _issue(
    issues: list[DesignValidationIssue],
    code: str,
    *,
    path: str = "",
    related_ids: tuple[str, ...] = (),
    message: str = "",
) -> None:
    issues.append(
        DesignValidationIssue(
            code=code,
            path=path,
            related_ids=related_ids,
            message=message,
        )
    )


def _finish(issues: list[DesignValidationIssue]) -> DesignValidationReport:
    return DesignValidationReport(
        passed=not issues,
        issues=tuple(issues),
    )


def _validate_common_refs(
    actual: DesignContractRefs,
    context: DesignValidationContext,
    issues: list[DesignValidationIssue],
) -> None:
    if actual != context.refs:
        _issue(
            issues,
            "design_contract_reference_mismatch",
            path="contract_refs",
        )


def _deferred_requirement_ids(spec: AppSpec) -> set[str]:
    return {
        requirement_id
        for item in spec.deferred_scope
        for requirement_id in item.requirement_ids
    }


def validate_product_strategy_v2(
    artifact: ProductStrategyV2,
    *,
    context: DesignValidationContext,
) -> DesignValidationReport:
    issues: list[DesignValidationIssue] = []
    _validate_common_refs(artifact.contract_refs, context, issues)
    spec = context.app_spec
    tier1, tier2, tier3 = context.tiers
    active_ids = set(tier3.references.requirement_ids)
    deferred_ids = _deferred_requirement_ids(spec)
    canonical_active_order = tuple(
        requirement.id
        for requirement in spec.requirements
        if requirement.id in active_ids
    )

    if (
        artifact.primary_outcome_requirement_id
        not in tier1.references.requirement_ids
    ):
        _issue(
            issues,
            "strategy_primary_outcome_not_in_tier_1",
            path="primary_outcome_requirement_id",
            related_ids=(artifact.primary_outcome_requirement_id,),
        )

    outcome_ids = tuple(
        item.requirement_id for item in artifact.prioritized_outcomes
    )
    if outcome_ids != canonical_active_order:
        _issue(
            issues,
            "strategy_outcomes_must_match_active_canonical_requirements",
            path="prioritized_outcomes",
        )
    for item in artifact.prioritized_outcomes:
        expected_tier = (
            1
            if item.requirement_id in tier1.references.requirement_ids
            else 2
            if item.requirement_id in tier2.references.requirement_ids
            else 3
        )
        if item.tier != expected_tier:
            _issue(
                issues,
                "strategy_outcome_tier_mismatch",
                path=f"prioritized_outcomes.{item.requirement_id}",
                related_ids=(item.requirement_id,),
            )
        if item.requirement_id in deferred_ids:
            _issue(
                issues,
                "strategy_contains_deferred_requirement",
                related_ids=(item.requirement_id,),
            )

    expected_surfaces = tuple(
        surface
        for surface in ("public", "ops")
        if any(page.surface == surface for page in spec.pages)
    )
    if tuple(item.surface for item in artifact.surfaces) != expected_surfaces:
        _issue(
            issues,
            "strategy_surface_set_mismatch",
            path="surfaces",
        )
    role_ids = {role.id for role in spec.roles}
    for index, surface in enumerate(artifact.surfaces):
        unknown_roles = set(surface.role_ids) - role_ids
        unknown_outcomes = set(surface.outcome_requirement_ids) - active_ids
        if unknown_roles:
            _issue(
                issues,
                "strategy_surface_unknown_role",
                path=f"surfaces.{index}.role_ids",
                related_ids=tuple(sorted(unknown_roles)),
            )
        if unknown_outcomes:
            _issue(
                issues,
                "strategy_surface_unknown_outcome",
                path=f"surfaces.{index}.outcome_requirement_ids",
                related_ids=tuple(sorted(unknown_outcomes)),
            )
    for index, item in enumerate(artifact.differentiators):
        invalid = set(item.proof_requirement_ids) - active_ids
        if invalid:
            _issue(
                issues,
                "strategy_differentiator_invalid_proof",
                path=f"differentiators.{index}.proof_requirement_ids",
                related_ids=tuple(sorted(invalid)),
            )
    for index, item in enumerate(artifact.risks):
        invalid = set(item.related_requirement_ids) - active_ids
        if invalid:
            _issue(
                issues,
                "strategy_risk_invalid_requirement",
                path=f"risks.{index}.related_requirement_ids",
                related_ids=tuple(sorted(invalid)),
            )
    return _finish(issues)


def _page_journey_ids(spec: AppSpec, page_id: str) -> tuple[str, ...]:
    return tuple(
        journey.id
        for journey in spec.journeys
        if journey.start_page_id == page_id
        or any(step.expected_page_id == page_id for step in journey.steps)
    )


def _page_requirement_ids(
    spec: AppSpec,
    page_id: str,
    active_ids: set[str],
) -> tuple[str, ...]:
    return tuple(
        requirement.id
        for requirement in spec.requirements
        if requirement.id in active_ids
        and any(
            link.requirement_id == requirement.id
            and page_id in link.page_ids
            for link in spec.traceability
        )
    )


def validate_information_architecture(
    artifact: InformationArchitecture,
    *,
    context: DesignValidationContext,
    product_strategy_ref: DesignArtifactRef,
) -> DesignValidationReport:
    issues: list[DesignValidationIssue] = []
    _validate_common_refs(artifact.contract_refs, context, issues)
    if artifact.product_strategy_ref != product_strategy_ref:
        _issue(
            issues,
            "ia_product_strategy_reference_mismatch",
            path="product_strategy_ref",
        )
    if not artifact.preserves_canonical_routes:
        _issue(issues, "ia_must_preserve_routes", path="preserves_canonical_routes")
    if not artifact.preserves_all_tier_3_pages:
        _issue(
            issues,
            "ia_must_preserve_tier_3_pages",
            path="preserves_all_tier_3_pages",
        )

    spec = context.app_spec
    active_ids = set(context.tiers[2].references.requirement_ids)
    expected_page_ids = tuple(page.id for page in spec.pages)
    actual_page_ids = tuple(page.page_id for page in artifact.pages)
    if actual_page_ids != expected_page_ids:
        _issue(
            issues,
            "ia_pages_must_match_canonical_order",
            path="pages",
        )

    page_map = {page.id: page for page in spec.pages}
    for index, page_contract in enumerate(artifact.pages):
        page = page_map.get(page_contract.page_id)
        if page is None:
            _issue(
                issues,
                "ia_unknown_page",
                path=f"pages.{index}.page_id",
                related_ids=(page_contract.page_id,),
            )
            continue
        exact_checks = (
            ("route", page_contract.route, page.route),
            ("surface", page_contract.surface, page.surface),
            ("role_ids", page_contract.role_ids, page.role_ids),
            (
                "required_action_ids",
                page_contract.required_action_ids,
                page.action_ids,
            ),
            (
                "required_evidence_ids",
                page_contract.required_evidence_ids,
                page.evidence_ids,
            ),
            (
                "required_outcome_requirement_ids",
                page_contract.required_outcome_requirement_ids,
                _page_requirement_ids(spec, page.id, active_ids),
            ),
            (
                "journey_ids",
                page_contract.journey_ids,
                _page_journey_ids(spec, page.id),
            ),
        )
        for field, actual, expected in exact_checks:
            if actual != expected:
                _issue(
                    issues,
                    "ia_page_contract_mismatch",
                    path=f"pages.{index}.{field}",
                    related_ids=(page.id,),
                )

    expected_role_ids = tuple(role.id for role in spec.roles)
    if tuple(item.role_id for item in artifact.role_access) != expected_role_ids:
        _issue(issues, "ia_roles_must_match_canonical_order", path="role_access")
    for index, access in enumerate(artifact.role_access):
        role = next(
            (item for item in spec.roles if item.id == access.role_id),
            None,
        )
        if role is None:
            continue
        expected_pages = tuple(
            page.id for page in spec.pages if role.id in page.role_ids
        )
        if access.entry_page_id != role.default_page_id:
            _issue(
                issues,
                "ia_role_entry_page_mismatch",
                path=f"role_access.{index}.entry_page_id",
                related_ids=(role.id,),
            )
        if access.accessible_page_ids != expected_pages:
            _issue(
                issues,
                "ia_role_page_access_mismatch",
                path=f"role_access.{index}.accessible_page_ids",
                related_ids=(role.id,),
            )

    visible_page_ids = {
        page.page_id
        for page in artifact.pages
        if page.navigation_visibility != "deep_link"
    }
    grouped_page_ids = {
        page_id
        for group in artifact.navigation_groups
        for page_id in group.page_ids
    }
    if grouped_page_ids != visible_page_ids:
        _issue(
            issues,
            "ia_navigation_groups_must_cover_visible_pages",
            path="navigation_groups",
        )
    known_roles = set(expected_role_ids)
    known_pages = set(expected_page_ids)
    for index, group in enumerate(artifact.navigation_groups):
        if not set(group.role_ids).issubset(known_roles):
            _issue(
                issues,
                "ia_navigation_group_unknown_role",
                path=f"navigation_groups.{index}.role_ids",
            )
        if not set(group.page_ids).issubset(known_pages):
            _issue(
                issues,
                "ia_navigation_group_unknown_page",
                path=f"navigation_groups.{index}.page_ids",
            )
    return _finish(issues)


_FORBIDDEN_DESIGN_DNA_MARKERS = (
    "@/ui",
    ".tsx",
    ".jsx",
    "classname=",
    "<div",
    "<section",
    "shadcn",
    "material ui",
    "chakra ui",
    "bootstrap component",
    "tailwind class",
    "skeleton id",
    "catalogue slot",
)


def validate_design_dna(
    artifact: DesignDNA,
    *,
    context: DesignValidationContext,
    product_strategy_ref: DesignArtifactRef,
    information_architecture_ref: DesignArtifactRef,
    expected_reference_mode: Literal["none", "textual_analysis", "vision"],
) -> DesignValidationReport:
    issues: list[DesignValidationIssue] = []
    _validate_common_refs(artifact.contract_refs, context, issues)
    if artifact.product_strategy_ref != product_strategy_ref:
        _issue(issues, "dna_product_strategy_reference_mismatch")
    if artifact.information_architecture_ref != information_architecture_ref:
        _issue(issues, "dna_information_architecture_reference_mismatch")
    if artifact.reference_mode != expected_reference_mode:
        _issue(
            issues,
            "dna_reference_mode_mismatch",
            path="reference_mode",
        )
    expected_roles = {
        "background",
        "surface",
        "foreground",
        "muted",
        "accent",
        "success",
        "warning",
        "danger",
    }
    if {item.semantic_role for item in artifact.color_tokens} != expected_roles:
        _issue(issues, "dna_color_token_roles_incomplete", path="color_tokens")
    serialized = json.dumps(
        artifact.model_dump(mode="json"),
        ensure_ascii=False,
    ).casefold()
    for marker in _FORBIDDEN_DESIGN_DNA_MARKERS:
        if marker in serialized:
            _issue(
                issues,
                "dna_contains_source_or_component_choice",
                path="artifact",
                message=f"Forbidden marker: {marker}",
            )
    return _finish(issues)


__all__ = [
    "DesignValidationContext",
    "validate_design_dna",
    "validate_information_architecture",
    "validate_product_strategy_v2",
]
