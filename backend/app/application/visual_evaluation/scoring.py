"""Evidence validation, group aggregation, and deterministic acceptance."""
from __future__ import annotations

from app.domain.schemas.visual_evaluation import (
    BaselineDimensionComparison,
    VISUAL_DIMENSIONS,
    ImageBundleGroup,
    VisualAcceptanceComputation,
    VisualAcceptancePolicy,
    VisualDimensionAssessment,
    VisualEvidenceBundle,
    VisualFinding,
    VisualHardGateReport,
    VisualReviewerDecision,
    VisualScorecard,
)


_DIMENSION_WEIGHTS = {
    "business_specificity": 1.20,
    "product_story_clarity": 1.00,
    "hierarchy_and_composition": 1.00,
    "visual_coherence": 0.90,
    "design_dna_adherence": 1.10,
    "content_credibility": 0.90,
    "interaction_clarity": 1.00,
    "conversion_strength": 1.10,
    "mobile_quality": 1.10,
    "responsive_consistency": 0.90,
    "density_and_readability": 0.90,
    "evidence_visibility": 1.00,
    "novelty": 0.80,
    "trust_and_professionalism": 1.10,
}


def _link_citations(rationale: str, citations: tuple[str, ...]) -> str:
    lower = rationale.casefold()
    missing = [
        value
        for value in citations
        if value and value.casefold() not in lower
    ]
    if not missing:
        return rationale
    suffix = " Cited evidence: " + ", ".join(missing)
    return (rationale.rstrip() + suffix)[:4000]


def _anchor_score_band(rationale: str, score: int) -> str:
    lower = rationale.casefold()
    if score >= 90:
        tokens = ("exception", "client-ready", "differentiat")
        inject = "exceptional client-ready differentiation"
    elif score >= 80:
        tokens = ("strong", "professional", "minor")
        inject = "strong professional result with only minor issues"
    elif score >= 70:
        tokens = ("usable", "ordinary", "inconsisten")
        inject = "usable ordinary quality with inconsistencies"
    elif score >= 50:
        tokens = ("weak", "generic", "unclear")
        inject = "weak generic unclear presentation"
    else:
        tokens = ("broken", "unconvincing")
        inject = "broken unconvincing presentation"
    if any(token in lower for token in tokens):
        return rationale
    return (rationale.rstrip() + f" Band: {inject}.")[:4000]


def _heal_assessment(
    item: VisualDimensionAssessment,
) -> VisualDimensionAssessment:
    rationale = _link_citations(
        item.rationale,
        tuple(item.evidence_ids) + tuple(item.affected_routes),
    )
    rationale = _anchor_score_band(rationale, int(item.score))
    if rationale == item.rationale:
        return item
    return item.model_copy(update={"rationale": rationale})


def _heal_finding(item: VisualFinding) -> VisualFinding:
    rationale = _link_citations(
        item.rationale,
        tuple(item.evidence_ids) + tuple(item.routes),
    )
    if rationale == item.rationale:
        return item
    return item.model_copy(update={"rationale": rationale})


def _validate_assessment(
    item: VisualDimensionAssessment,
    *,
    allowed_evidence: set[str],
    bundle: VisualEvidenceBundle,
) -> None:
    evidence_map = {
        row.evidence_id: row for row in bundle.ordered_screenshots
    }
    if not set(item.evidence_ids).issubset(allowed_evidence):
        raise ValueError(
            f"{item.dimension} references evidence outside its image group"
        )
    rows = [evidence_map[evidence_id] for evidence_id in item.evidence_ids]
    if (
        not set(item.affected_routes).issubset(
            {row.route for row in rows}
        )
        or not set(item.affected_viewports).issubset(
            {row.viewport for row in rows}
        )
    ):
        raise ValueError(
            f"{item.dimension} route/viewport claims lack cited evidence"
        )
    rationale = item.rationale.casefold()
    cited = tuple(item.evidence_ids) + tuple(item.affected_routes)
    if not any(value.casefold() in rationale for value in cited):
        raise ValueError(
            f"{item.dimension} rationale is generic and not evidence-linked"
        )
    if item.score >= 90 and not any(
        token in rationale
        for token in ("exception", "client-ready", "differentiat")
    ):
        raise ValueError("Exceptional score lacks anchored band evidence")
    if 80 <= item.score < 90 and not any(
        token in rationale for token in ("strong", "professional", "minor")
    ):
        raise ValueError("Strong score lacks anchored band evidence")
    if 70 <= item.score < 80 and not any(
        token in rationale for token in ("usable", "ordinary", "inconsisten")
    ):
        raise ValueError("Usable score lacks anchored band evidence")
    if 50 <= item.score < 70 and not any(
        token in rationale for token in ("weak", "generic", "unclear")
    ):
        raise ValueError("Weak score lacks anchored band evidence")
    if item.score < 50 and not any(
        token in rationale for token in ("broken", "unconvincing")
    ):
        raise ValueError("Failing score lacks anchored band evidence")


def _validate_finding(
    item: VisualFinding,
    *,
    allowed_evidence: set[str],
    bundle: VisualEvidenceBundle,
    hard_gate: VisualHardGateReport,
) -> None:
    evidence_map = {
        row.evidence_id: row for row in bundle.ordered_screenshots
    }
    if not set(item.evidence_ids).issubset(allowed_evidence):
        raise ValueError("Visual finding cites unavailable evidence")
    rows = [evidence_map[evidence_id] for evidence_id in item.evidence_ids]
    if (
        not set(item.routes).issubset({row.route for row in rows})
        or not set(item.viewports).issubset({row.viewport for row in rows})
        or not set(item.page_ids).issubset({row.page_id for row in rows})
    ):
        raise ValueError("Visual finding route/page claims are unsupported")
    if not any(
        value.casefold() in item.rationale.casefold()
        for value in (*item.evidence_ids, *item.routes)
    ):
        raise ValueError("Visual finding rationale is not evidence-linked")
    if item.deterministic_support and item.issue_type not in {
        finding.code for finding in hard_gate.findings
    }:
        raise ValueError("Finding claims deterministic support without a gate")


def validate_critic_group(
    scorecard: VisualScorecard,
    *,
    subject: str,
    group: ImageBundleGroup,
    bundle: VisualEvidenceBundle,
    hard_gate: VisualHardGateReport,
) -> VisualScorecard:
    if (
        scorecard.actor != "critic"
        or scorecard.subject != subject
        or scorecard.group_index != group.group_index
    ):
        raise ValueError("Critic scorecard identity is invalid")
    allowed = set(group.evidence_ids)
    healed_dimensions = tuple(_heal_assessment(item) for item in scorecard.dimensions)
    healed_findings = tuple(_heal_finding(item) for item in scorecard.findings)
    scorecard = scorecard.model_copy(
        update={
            "dimensions": healed_dimensions,
            "findings": healed_findings,
        }
    )
    for item in scorecard.dimensions:
        _validate_assessment(
            item,
            allowed_evidence=allowed,
            bundle=bundle,
        )
    for finding in scorecard.findings:
        if finding.source != "critic":
            raise ValueError("Critic finding source is invalid")
        _validate_finding(
            finding,
            allowed_evidence=allowed,
            bundle=bundle,
            hard_gate=hard_gate,
        )
    return scorecard


def validate_reviewer_group(
    decision: VisualReviewerDecision,
    *,
    subject: str,
    group: ImageBundleGroup,
    bundle: VisualEvidenceBundle,
    hard_gate: VisualHardGateReport,
) -> VisualReviewerDecision:
    if decision.subject != subject:
        raise ValueError("Reviewer subject is invalid")
    allowed = set(group.evidence_ids)
    healed_dimensions = tuple(
        _heal_assessment(item) for item in decision.dimensions
    )
    healed_blockers = tuple(
        _heal_finding(item) for item in decision.blocking_findings
    )
    healed_disagreements = []
    for disagreement in decision.disagreements:
        rationale = _link_citations(
            disagreement.rationale,
            tuple(disagreement.evidence_ids),
        )
        healed_disagreements.append(
            disagreement
            if rationale == disagreement.rationale
            else disagreement.model_copy(update={"rationale": rationale})
        )
    healed_comparisons = []
    for comparison in decision.comparative_dimensions:
        rationale = _link_citations(
            comparison.rationale,
            tuple(comparison.evidence_ids),
        )
        healed_comparisons.append(
            comparison
            if rationale == comparison.rationale
            else comparison.model_copy(update={"rationale": rationale})
        )
    decision = decision.model_copy(
        update={
            "dimensions": healed_dimensions,
            "blocking_findings": healed_blockers,
            "disagreements": tuple(healed_disagreements),
            "comparative_dimensions": tuple(healed_comparisons),
        }
    )
    for item in decision.dimensions:
        _validate_assessment(
            item,
            allowed_evidence=allowed,
            bundle=bundle,
        )
    for finding in decision.blocking_findings:
        if finding.source != "reviewer" or finding.severity != "blocking":
            raise ValueError("Reviewer blocker provenance is invalid")
        _validate_finding(
            finding,
            allowed_evidence=allowed,
            bundle=bundle,
            hard_gate=hard_gate,
        )
    critic_ids = allowed
    for disagreement in decision.disagreements:
        if not set(disagreement.evidence_ids).issubset(critic_ids):
            raise ValueError("Reviewer disagreement cites unavailable evidence")
        if not any(
            evidence_id.casefold() in disagreement.rationale.casefold()
            for evidence_id in disagreement.evidence_ids
        ):
            raise ValueError("Reviewer disagreement is not evidence-linked")
    for comparison in decision.comparative_dimensions:
        if not any(
            evidence_id.casefold() in comparison.rationale.casefold()
            for evidence_id in comparison.evidence_ids
        ):
            raise ValueError("Blind comparison is not evidence-linked")
    return decision


def _aggregate_dimensions(
    groups: tuple[ImageBundleGroup, ...],
    rows: tuple[tuple[VisualDimensionAssessment, ...], ...],
) -> tuple[VisualDimensionAssessment, ...]:
    result = []
    total_images = sum(group.image_count for group in groups)
    for dimension_index, dimension in enumerate(VISUAL_DIMENSIONS):
        items = tuple(row[dimension_index] for row in rows)
        score = round(
            sum(
                item.score * group.image_count
                for item, group in zip(items, groups)
            )
            / total_images
        )
        confidence = sum(
            item.confidence * group.image_count
            for item, group in zip(items, groups)
        ) / total_images
        severity_order = {"none": 0, "minor": 1, "major": 2, "blocking": 3}
        severity = max(
            (item.failure_severity for item in items),
            key=severity_order.__getitem__,
        )
        result.append(
            VisualDimensionAssessment(
                dimension=dimension,
                score=score,
                confidence=confidence,
                evidence_ids=tuple(
                    dict.fromkeys(
                        evidence_id
                        for item in items
                        for evidence_id in item.evidence_ids
                    )
                ),
                affected_routes=tuple(
                    dict.fromkeys(
                        route
                        for item in items
                        for route in item.affected_routes
                    )
                ),
                affected_viewports=tuple(
                    dict.fromkeys(
                        viewport
                        for item in items
                        for viewport in item.affected_viewports
                    )
                ),
                rationale=" | ".join(item.rationale for item in items)[:4000],
                failure_severity=severity,
                deterministic_support=all(
                    item.deterministic_support for item in items
                ),
            )
        )
    return tuple(result)


def aggregate_critic_scorecards(
    groups: tuple[ImageBundleGroup, ...],
    partials: tuple[VisualScorecard, ...],
    *,
    subject: str,
) -> VisualScorecard:
    findings = []
    for group, partial in zip(groups, partials):
        for finding in partial.findings:
            findings.append(
                finding.model_copy(
                    update={
                        "finding_id": (
                            f"CG{group.group_index + 1}-"
                            f"{finding.finding_id}"
                        )[:64]
                    }
                )
            )
    return VisualScorecard(
        actor="critic",
        subject=subject,
        group_index=None,
        dimensions=_aggregate_dimensions(
            groups,
            tuple(partial.dimensions for partial in partials),
        ),
        findings=tuple(findings),
    )


def aggregate_reviewer_decisions(
    groups: tuple[ImageBundleGroup, ...],
    partials: tuple[VisualReviewerDecision, ...],
    *,
    subject: str,
) -> VisualReviewerDecision:
    disagreements = []
    blockers = []
    for group, partial in zip(groups, partials):
        disagreements.extend(
            item.model_copy(
                update={
                    "disagreement_id": (
                        f"RG{group.group_index + 1}-"
                        f"{item.disagreement_id}"
                    )[:64]
                }
            )
            for item in partial.disagreements
        )
        blockers.extend(
            item.model_copy(
                update={
                    "finding_id": (
                        f"RG{group.group_index + 1}-"
                        f"{item.finding_id}"
                    )[:64]
                }
            )
            for item in partial.blocking_findings
        )
    comparison_results = {
        item.comparative_result for item in partials
    }
    comparative_result = (
        partials[0].comparative_result
        if len(comparison_results) == 1
        else "inconclusive"
    )
    comparative_dimensions = ()
    if (
        comparative_result != "not_applicable"
        and all(len(item.comparative_dimensions) == 6 for item in partials)
    ):
        names = (
            "clarity",
            "business_specificity",
            "visual_quality",
            "trust",
            "conversion_strength",
            "mobile_quality",
        )
        aggregated = []
        total_images = sum(group.image_count for group in groups)
        for index, name in enumerate(names):
            items = tuple(
                item.comparative_dimensions[index] for item in partials
            )
            preferences = {item.preferred for item in items}
            aggregated.append(
                BaselineDimensionComparison(
                    dimension=name,
                    preferred=(
                        next(iter(preferences))
                        if len(preferences) == 1
                        else "inconclusive"
                    ),
                    confidence=sum(
                        item.confidence * group.image_count
                        for item, group in zip(items, groups)
                    )
                    / total_images,
                    evidence_ids=tuple(
                        dict.fromkeys(
                            evidence_id
                            for item in items
                            for evidence_id in item.evidence_ids
                        )
                    ),
                    rationale=" | ".join(
                        item.rationale for item in items
                    )[:4000],
                )
            )
        comparative_dimensions = tuple(aggregated)
    return VisualReviewerDecision(
        subject=subject,
        recommendation=(
            "accept"
            if all(item.recommendation == "accept" for item in partials)
            else "reject"
        ),
        confidence=sum(
            item.confidence * group.image_count
            for item, group in zip(partials, groups)
        )
        / sum(group.image_count for group in groups),
        dimensions=_aggregate_dimensions(
            groups,
            tuple(partial.dimensions for partial in partials),
        ),
        disagreements=tuple(disagreements),
        blocking_findings=tuple(blockers),
        score_band_concerns=tuple(
            dict.fromkeys(
                concern
                for item in partials
                for concern in item.score_band_concerns
            )
        ),
        comparative_result=comparative_result,
        comparative_dimensions=comparative_dimensions,
    )


def _weighted(dimensions: tuple[VisualDimensionAssessment, ...]) -> float:
    total_weight = sum(_DIMENSION_WEIGHTS.values())
    return round(
        sum(
            item.score * _DIMENSION_WEIGHTS[item.dimension]
            for item in dimensions
        )
        / total_weight,
        3,
    )


def compute_acceptance(
    critic: VisualScorecard,
    reviewer: VisualReviewerDecision,
    hard_gate: VisualHardGateReport,
    policy: VisualAcceptancePolicy,
) -> VisualAcceptanceComputation:
    critic_by = {item.dimension: item.score for item in critic.dimensions}
    reviewer_by = {
        item.dimension: item.score for item in reviewer.dimensions
    }
    combined = tuple(
        (
            dimension,
            round((critic_by[dimension] + reviewer_by[dimension]) / 2, 3),
        )
        for dimension in VISUAL_DIMENSIONS
    )
    combined_map = dict(combined)
    critic_weighted = _weighted(critic.dimensions)
    reviewer_weighted = _weighted(reviewer.dimensions)
    weighted = round((critic_weighted + reviewer_weighted) / 2, 3)
    blocking = (
        sum(
            finding.severity == "blocking"
            for finding in critic.findings
        )
        + len(reviewer.blocking_findings)
        + sum(
            finding.severity == "blocking"
            for finding in hard_gate.findings
        )
    )

    def actor_pass(dimensions, weighted_score) -> bool:
        scores = {item.dimension: item.score for item in dimensions}
        return (
            weighted_score >= policy.weighted_overall_min
            and scores["business_specificity"]
            >= policy.business_specificity_min
            and scores["design_dna_adherence"]
            >= policy.design_dna_adherence_min
            and scores["conversion_strength"]
            >= policy.conversion_strength_min
            and scores["mobile_quality"] >= policy.mobile_quality_min
            and scores["trust_and_professionalism"]
            >= policy.trust_and_professionalism_min
        )

    critic_accepts = actor_pass(critic.dimensions, critic_weighted)
    reviewer_accepts = (
        reviewer.recommendation == policy.reviewer_recommendation
        and actor_pass(reviewer.dimensions, reviewer_weighted)
        and not reviewer.blocking_findings
    )
    agreement = critic_accepts == reviewer_accepts
    checks = (
        ("hard_gates", hard_gate.passed),
        ("weighted_overall", weighted >= policy.weighted_overall_min),
        (
            "business_specificity",
            combined_map["business_specificity"]
            >= policy.business_specificity_min,
        ),
        (
            "design_dna_adherence",
            combined_map["design_dna_adherence"]
            >= policy.design_dna_adherence_min,
        ),
        (
            "conversion_strength",
            combined_map["conversion_strength"]
            >= policy.conversion_strength_min,
        ),
        (
            "mobile_quality",
            combined_map["mobile_quality"] >= policy.mobile_quality_min,
        ),
        (
            "trust_and_professionalism",
            combined_map["trust_and_professionalism"]
            >= policy.trust_and_professionalism_min,
        ),
        ("blocking_findings", blocking == 0),
        ("reviewer_recommendation", reviewer_accepts),
        ("critic_reviewer_agreement", agreement),
    )
    return VisualAcceptanceComputation(
        weighted_overall=weighted,
        critic_weighted_overall=critic_weighted,
        reviewer_weighted_overall=reviewer_weighted,
        dimension_scores=combined,
        blocking_finding_count=blocking,
        critic_accepts=critic_accepts,
        reviewer_accepts=reviewer_accepts,
        agreement=agreement,
        threshold_checks=checks,
        accepted=all(value for _name, value in checks),
    )


__all__ = [
    "aggregate_critic_scorecards",
    "aggregate_reviewer_decisions",
    "compute_acceptance",
    "validate_critic_group",
    "validate_reviewer_group",
]
