"""Deterministic heals for Phase 2 AI artifacts before strict validation."""
from __future__ import annotations

from app.application.design_contract.validation import DesignValidationContext
from app.domain.schemas.product_strategy import (
    DifferentiatorV2,
    PrioritizedOutcomeV2,
    ProductStrategyV2,
    StrategyAssumptionV2,
    StrategyRiskV2,
    SurfaceStrategyV2,
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


__all__ = ["normalize_product_strategy_v2"]
