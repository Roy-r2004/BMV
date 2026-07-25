"""Deterministic heals for Phase 2 AI artifacts before strict validation."""
from __future__ import annotations

from typing import Any, Literal

from app.application.design_contract.validation import (
    DesignValidationContext,
    _page_journey_ids,
    _page_requirement_ids,
)
from app.domain.schemas.design_contract import DesignArtifactRef
from app.domain.schemas.design_dna import ColorTokenDirection, DesignDNA
from app.domain.schemas.information_architecture import (
    InformationArchitecture,
    MobileBehavior,
    NavigationGroup,
    PageArchitecture,
    RoleRouteAccess,
)
from app.domain.schemas.product_strategy import (
    DifferentiatorV2,
    PrioritizedOutcomeV2,
    ProductStrategyV2,
    StrategyAssumptionV2,
    StrategyRiskV2,
    SurfaceStrategyV2,
)

_FORBIDDEN_DNA_MARKERS = (
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
_COLOR_ROLES = (
    "background",
    "surface",
    "foreground",
    "muted",
    "accent",
    "success",
    "warning",
    "danger",
)

_DEFAULT_MOBILE = MobileBehavior(
    navigation="collapsed_menu",
    primary_action="sticky",
    content_priority=("primary outcome",),
    data_presentation="stacked_cards",
    density_adjustment="preserve",
)


def normalize_product_strategy_v2(
    artifact: ProductStrategyV2,
    *,
    context: DesignValidationContext,
) -> ProductStrategyV2:
    """Repair mechanical ID/order/tier mistakes without inventing new scope.

    LLMs routinely shuffle canonical requirement order or mis-label tiers.
    Those failures are deterministic and should not burn stage retries.
    """

    spec = context.app_spec
    tier1, tier2, tier3 = context.tiers
    tier1_ids = set(tier1.references.requirement_ids)
    tier2_ids = set(tier2.references.requirement_ids)
    active_ids = set(tier3.references.requirement_ids)
    canonical_active_order = tuple(
        requirement.id
        for requirement in spec.requirements
        if requirement.id in active_ids
    )
    if not canonical_active_order:
        return artifact

    rationale_by_id = {
        item.requirement_id: item.rationale
        for item in artifact.prioritized_outcomes
    }
    outcomes = tuple(
        PrioritizedOutcomeV2(
            requirement_id=requirement_id,
            tier=(
                1
                if requirement_id in tier1_ids
                else 2
                if requirement_id in tier2_ids
                else 3
            ),
            rationale=(
                rationale_by_id.get(requirement_id)
                or f"Deliver canonical requirement {requirement_id}."
            ),
        )
        for requirement_id in canonical_active_order
    )

    primary = artifact.primary_outcome_requirement_id
    if primary not in tier1_ids:
        primary = next(
            (
                requirement_id
                for requirement_id in canonical_active_order
                if requirement_id in tier1_ids
            ),
            canonical_active_order[0],
        )

    expected_surfaces = tuple(
        surface
        for surface in ("public", "ops")
        if any(page.surface == surface for page in spec.pages)
    )
    surface_by_kind = {item.surface: item for item in artifact.surfaces}
    role_ids_by_surface: dict[str, tuple[str, ...]] = {}
    for surface in expected_surfaces:
        roles = tuple(
            sorted(
                {
                    role_id
                    for page in spec.pages
                    if page.surface == surface
                    for role_id in page.role_ids
                }
            )
        )
        role_ids_by_surface[surface] = roles or tuple(
            role.id for role in spec.roles[:1]
        )

    surfaces: list[SurfaceStrategyV2] = []
    for surface in expected_surfaces:
        existing = surface_by_kind.get(surface)
        roles = role_ids_by_surface[surface]
        if existing is not None:
            kept_roles = tuple(
                role_id for role_id in existing.role_ids if role_id in set(roles)
            ) or roles
            kept_outcomes = tuple(
                requirement_id
                for requirement_id in existing.outcome_requirement_ids
                if requirement_id in active_ids
            ) or canonical_active_order[:1]
            surfaces.append(
                SurfaceStrategyV2(
                    surface=surface,
                    role_ids=kept_roles,
                    outcome_requirement_ids=kept_outcomes,
                    purpose=existing.purpose,
                )
            )
        else:
            surfaces.append(
                SurfaceStrategyV2(
                    surface=surface,
                    role_ids=roles,
                    outcome_requirement_ids=canonical_active_order[:1],
                    purpose=f"Support the {surface} experience for this preview.",
                )
            )

    differentiators: list[DifferentiatorV2] = []
    for item in artifact.differentiators:
        proofs = tuple(
            requirement_id
            for requirement_id in item.proof_requirement_ids
            if requirement_id in active_ids
        )
        if not proofs:
            proofs = canonical_active_order[:1]
        differentiators.append(
            DifferentiatorV2(
                id=item.id,
                statement=item.statement,
                proof_requirement_ids=proofs,
                design_implication=item.design_implication,
            )
        )
    if not differentiators:
        differentiators.append(
            DifferentiatorV2(
                id="DIFF-PRIMARY",
                statement="Clear preview of the core business outcome.",
                proof_requirement_ids=canonical_active_order[:1],
                design_implication=(
                    "Keep the first viewport focused on the primary outcome."
                ),
            )
        )

    risks = tuple(
        StrategyRiskV2(
            id=item.id,
            statement=item.statement,
            mitigation=item.mitigation,
            related_requirement_ids=tuple(
                requirement_id
                for requirement_id in item.related_requirement_ids
                if requirement_id in active_ids
            ),
        )
        for item in artifact.risks
    )
    assumptions = tuple(
        StrategyAssumptionV2(
            id=item.id,
            statement=item.statement,
            evidence_refs=item.evidence_refs,
            impact=item.impact,
        )
        for item in artifact.assumptions
    )

    return ProductStrategyV2(
        schema_version=artifact.schema_version,
        contract_refs=context.refs,
        positioning=artifact.positioning,
        primary_outcome_requirement_id=primary,
        prioritized_outcomes=outcomes,
        surfaces=tuple(surfaces),
        differentiators=tuple(differentiators),
        risks=risks,
        assumptions=assumptions,
        exclusions=artifact.exclusions,
    )


def normalize_information_architecture(
    artifact: InformationArchitecture,
    *,
    context: DesignValidationContext,
    product_strategy_ref: DesignArtifactRef,
) -> InformationArchitecture:
    """Force page/role contracts to match the canonical AppSpec exactly.

    Authors often drift on role_ids, actions, evidence, or accessible pages.
    Those fields are deterministic from AppSpec and should not fail the stage.
    """

    spec = context.app_spec
    active_ids = set(context.tiers[2].references.requirement_ids)
    by_page_id = {page.page_id: page for page in artifact.pages}
    pages: list[PageArchitecture] = []
    for page in spec.pages:
        prior = by_page_id.get(page.id)
        visibility = (
            prior.navigation_visibility if prior is not None else "primary"
        )
        deep_link_reason = (
            prior.deep_link_reason
            if prior is not None and visibility == "deep_link"
            else (
                "Secondary detail reached from the primary journey."
                if visibility == "deep_link"
                else None
            )
        )
        pages.append(
            PageArchitecture(
                page_id=page.id,
                route=page.route,
                surface=page.surface,
                purpose=(
                    prior.purpose
                    if prior is not None
                    else (page.purpose or f"Support {page.id}.")
                ),
                role_ids=page.role_ids,
                required_outcome_requirement_ids=_page_requirement_ids(
                    spec, page.id, active_ids
                ),
                required_action_ids=page.action_ids,
                required_evidence_ids=page.evidence_ids,
                journey_ids=_page_journey_ids(spec, page.id),
                navigation_visibility=visibility,
                deep_link_reason=deep_link_reason,
                mobile=prior.mobile if prior is not None else _DEFAULT_MOBILE,
            )
        )

    role_access = tuple(
        RoleRouteAccess(
            role_id=role.id,
            entry_page_id=role.default_page_id,
            accessible_page_ids=tuple(
                page.id for page in spec.pages if role.id in page.role_ids
            ),
        )
        for role in spec.roles
    )

    visible_pages = [
        page for page in pages if page.navigation_visibility != "deep_link"
    ]
    groups: list[NavigationGroup] = []
    for surface in ("public", "ops"):
        surface_pages = tuple(
            page.page_id for page in visible_pages if page.surface == surface
        )
        if not surface_pages:
            continue
        roles = tuple(
            sorted(
                {
                    role_id
                    for page in pages
                    if page.surface == surface
                    for role_id in page.role_ids
                }
            )
        )
        if not roles and spec.roles:
            roles = (spec.roles[0].id,)
        prior_group = next(
            (
                group
                for group in artifact.navigation_groups
                if group.surface == surface
            ),
            None,
        )
        groups.append(
            NavigationGroup(
                id=(
                    prior_group.id
                    if prior_group is not None
                    else f"NAV-{surface.upper()}"
                ),
                label=(
                    prior_group.label
                    if prior_group is not None
                    else f"{surface.title()} navigation"
                ),
                surface=surface,
                role_ids=roles or (spec.roles[0].id,),
                page_ids=surface_pages,
            )
        )
    if not groups and visible_pages:
        groups.append(
            NavigationGroup(
                id="NAV-PRIMARY",
                label="Primary navigation",
                surface=visible_pages[0].surface,
                role_ids=visible_pages[0].role_ids[:1] or (spec.roles[0].id,),
                page_ids=tuple(page.page_id for page in visible_pages),
            )
        )

    return InformationArchitecture(
        schema_version=artifact.schema_version,
        contract_refs=context.refs,
        product_strategy_ref=product_strategy_ref,
        navigation_principle=artifact.navigation_principle,
        navigation_groups=tuple(groups),
        role_access=role_access,
        pages=tuple(pages),
        mobile_global_behavior=artifact.mobile_global_behavior,
        preserves_canonical_routes=True,
        preserves_all_tier_3_pages=True,
    )


def _clean_dna_text(value: str) -> str:
    cleaned = value
    for marker in _FORBIDDEN_DNA_MARKERS:
        idx = cleaned.casefold().find(marker)
        while idx >= 0:
            cleaned = cleaned[:idx] + " " + cleaned[idx + len(marker) :]
            idx = cleaned.casefold().find(marker)
    return " ".join(cleaned.split()) or "Business-specific visual direction"


def _clean_dna_tree(value: Any) -> Any:
    if isinstance(value, str):
        return _clean_dna_text(value)
    if isinstance(value, list):
        return [_clean_dna_tree(item) for item in value]
    if isinstance(value, tuple):
        return [_clean_dna_tree(item) for item in value]
    if isinstance(value, dict):
        return {key: _clean_dna_tree(item) for key, item in value.items()}
    return value


def normalize_design_dna(
    artifact: DesignDNA,
    *,
    context: DesignValidationContext,
    product_strategy_ref: DesignArtifactRef,
    information_architecture_ref: DesignArtifactRef,
    expected_reference_mode: Literal["none", "textual_analysis", "vision"],
) -> DesignDNA:
    """Repair mechanical DNA gaps without inventing a new visual system."""

    del context  # reserved for future strategy-aware defaults
    payload = _clean_dna_tree(artifact.model_dump(mode="json"))
    payload["contract_refs"] = artifact.contract_refs.model_dump(mode="json")
    payload["product_strategy_ref"] = product_strategy_ref.model_dump(
        mode="json"
    )
    payload["information_architecture_ref"] = (
        information_architecture_ref.model_dump(mode="json")
    )
    payload["reference_mode"] = expected_reference_mode

    by_role = {
        item.get("semantic_role"): item
        for item in (payload.get("color_tokens") or [])
        if isinstance(item, dict) and item.get("semantic_role")
    }
    payload["color_tokens"] = [
        by_role.get(role)
        or {
            "semantic_role": role,
            "direction": f"Business-specific {role} direction.",
            "contrast_intent": "Maintain readable semantic contrast.",
        }
        for role in _COLOR_ROLES
    ]

    motion = payload.get("motion") or {}
    band = motion.get("duration_band_ms") or [120, 280]
    if (
        not isinstance(band, list)
        or len(band) != 2
        or not all(isinstance(item, int) for item in band)
        or band[0] < 0
        or band[1] < band[0]
        or band[1] > 2000
    ):
        motion["duration_band_ms"] = [120, 280]
        payload["motion"] = motion

    avoid = [
        item
        for item in (payload.get("avoid_list") or [])
        if isinstance(item, str) and item.strip()
    ]
    while len(avoid) < 3:
        avoid.append(f"Generic visual filler {len(avoid) + 1}")
    payload["avoid_list"] = avoid[:30]

    fingerprint = payload.get("fingerprint") or {}
    traits = [
        item
        for item in (fingerprint.get("signature_traits") or [])
        if isinstance(item, str) and item.strip()
    ]
    while len(traits) < 3:
        traits.append(f"Outcome-led trait {len(traits) + 1}")
    fingerprint["signature_traits"] = traits[:10]
    fingerprint.setdefault("name", "Visible Certainty")
    fingerprint.setdefault(
        "recurring_motif",
        "A measured confirmation rhythm.",
    )
    fingerprint.setdefault(
        "differentiation_guard",
        "Every visual decision must reinforce this business outcome.",
    )
    payload["fingerprint"] = fingerprint

    # Re-validate ColorTokenDirection shape after fills.
    payload["color_tokens"] = [
        ColorTokenDirection.model_validate(item).model_dump(mode="json")
        for item in payload["color_tokens"]
    ]
    return DesignDNA.model_validate(payload)


__all__ = [
    "normalize_design_dna",
    "normalize_information_architecture",
    "normalize_product_strategy_v2",
]
