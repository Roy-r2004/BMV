"""Fail-closed validation for an in-memory cumulative tier set."""
from __future__ import annotations

from collections.abc import Sequence

from app.application.preview_contract.tiers import (
    TierBuildError,
    TierContractContext,
    build_preview_tiers,
    expand_tier_graph,
)
from app.domain.schemas.app_spec import AppSpec
from app.domain.schemas.preview_tier import (
    PreviewTierArtifact,
    TIER_SELECTION_POLICY_REVISION,
    TierValidationIssue,
    TierValidationReport,
)
from app.domain.schemas.product_strategy import ProductStrategy


_REFERENCE_FIELDS = (
    "requirement_ids",
    "role_ids",
    "entity_ids",
    "capability_ids",
    "page_ids",
    "state_ids",
    "action_ids",
    "transition_ids",
    "evidence_ids",
    "journey_ids",
    "acceptance_test_ids",
)


def _issue(
    issues: list[TierValidationIssue],
    code: str,
    *,
    path: str = "",
    related_ids: tuple[str, ...] = (),
) -> None:
    issues.append(
        TierValidationIssue(
            code=code,
            path=path,
            related_ids=related_ids,
        )
    )


def _reference_sets(tier: PreviewTierArtifact) -> dict[str, set[str]]:
    return {
        field: set(getattr(tier.references, field))
        for field in _REFERENCE_FIELDS
    }


def validate_preview_tiers(
    tiers: Sequence[PreviewTierArtifact],
    *,
    spec: AppSpec,
    strategy: ProductStrategy,
    context: TierContractContext,
    selection_policy_revision: str = TIER_SELECTION_POLICY_REVISION,
) -> TierValidationReport:
    issues: list[TierValidationIssue] = []
    if len(tiers) != 3 or [tier.tier for tier in tiers] != [1, 2, 3]:
        _issue(issues, "tier_set_requires_exactly_1_2_3", path="tiers")
        return TierValidationReport(passed=False, issues=tuple(issues))

    expected_context = {
        "request_id": context.request_id,
        "customer_source_ref": context.customer_source_ref,
        "product_strategy_ref": context.product_strategy_ref,
        "app_spec_ref": context.app_spec_ref,
    }
    for index, tier in enumerate(tiers):
        if tier.selection_policy_revision != selection_policy_revision:
            _issue(
                issues,
                "selection_policy_revision_mismatch",
                path=f"tiers.{index}.selection_policy_revision",
            )
        for field, expected in expected_context.items():
            if getattr(tier, field) != expected:
                _issue(
                    issues,
                    "cross_contract_reference",
                    path=f"tiers.{index}.{field}",
                )
        try:
            actual_sets = _reference_sets(tier)
            closed_sets = expand_tier_graph(spec, actual_sets)
            for field in _REFERENCE_FIELDS:
                if closed_sets[field] != actual_sets[field]:
                    _issue(
                        issues,
                        "tier_graph_not_closed",
                        path=f"tiers.{index}.references.{field}",
                    )
        except TierBuildError:
            _issue(
                issues,
                "tier_graph_invalid",
                path=f"tiers.{index}.references",
            )

    tier1, tier2, tier3 = tiers
    for field in _REFERENCE_FIELDS:
        one = set(getattr(tier1.references, field))
        two = set(getattr(tier2.references, field))
        three = set(getattr(tier3.references, field))
        if not one.issubset(two):
            _issue(
                issues,
                "tier_2_not_superset",
                path=f"tiers.1.references.{field}",
            )
        if not two.issubset(three):
            _issue(
                issues,
                "tier_3_not_superset",
                path=f"tiers.2.references.{field}",
            )

    must_ids = {
        requirement.id
        for requirement in spec.requirements
        if requirement.priority == "must"
    }
    if not must_ids.issubset(set(tier2.references.requirement_ids)):
        _issue(issues, "tier_2_missing_must_requirements", path="tiers.1")

    deferred_ids = {
        requirement_id
        for item in spec.deferred_scope
        for requirement_id in item.requirement_ids
    }
    active_ids = {
        requirement.id
        for requirement in spec.requirements
        if requirement.id not in deferred_ids
    }
    if not active_ids.issubset(set(tier3.references.requirement_ids)):
        _issue(issues, "tier_3_missing_active_requirements", path="tiers.2")
    if deferred_ids & set(tier3.references.requirement_ids):
        _issue(issues, "tier_3_contains_deferred_requirement", path="tiers.2")
    canonical_page_ids = {page.id for page in spec.pages}
    if not canonical_page_ids.issubset(set(tier3.references.page_ids)):
        _issue(issues, "tier_3_missing_canonical_pages", path="tiers.2")

    primary = tier1.primary_journey_proof
    if primary.requirement_id not in tier1.references.requirement_ids:
        _issue(
            issues,
            "tier_1_primary_requirement_missing",
            related_ids=(primary.requirement_id,),
        )
    for field, values, reference_values in (
        ("page_ids", primary.page_ids, tier1.references.page_ids),
        ("action_ids", primary.action_ids, tier1.references.action_ids),
        (
            "transition_ids",
            primary.transition_ids,
            tier1.references.transition_ids,
        ),
        (
            "success_evidence_ids",
            primary.success_evidence_ids,
            tier1.references.evidence_ids,
        ),
    ):
        if not set(values).issubset(set(reference_values)):
            _issue(
                issues,
                "tier_1_primary_proof_not_contained",
                path=f"tiers.0.primary_journey_proof.{field}",
            )
    if primary.journey_id not in tier1.references.journey_ids:
        _issue(issues, "tier_1_primary_journey_missing")
    if primary.acceptance_test_id not in tier1.references.acceptance_test_ids:
        _issue(issues, "tier_1_primary_acceptance_test_missing")

    try:
        expected = build_preview_tiers(
            spec=spec,
            strategy=strategy,
            context=context,
            selection_policy_revision=selection_policy_revision,
        )
        for index, (actual, deterministic) in enumerate(zip(tiers, expected)):
            if actual.model_dump(mode="json") != deterministic.model_dump(mode="json"):
                _issue(
                    issues,
                    "tier_not_deterministic_projection",
                    path=f"tiers.{index}",
                )
    except TierBuildError:
        _issue(issues, "deterministic_tier_projection_failed", path="tiers")

    return TierValidationReport(
        passed=not issues,
        issues=tuple(issues),
    )


__all__ = ["validate_preview_tiers"]
