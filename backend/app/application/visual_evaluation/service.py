"""Phase 5 coordinator: hard gates, independent review, one bounded refinement."""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.application.appspec.source import canonical_json
from app.application.runtime_validation.cache import artifact_sha256
from app.application.runtime_validation.service import (
    validate_v2_candidate_runtime,
)
from app.application.visual_evaluation.baseline import (
    blind_label_order,
    resolve_baseline,
)
from app.application.visual_evaluation.builder import (
    VisualStageError,
    build_critic_group,
    build_refinement,
    build_reviewer_group,
    build_technical_repair,
)
from app.application.visual_evaluation.cache import evaluation_cache_key
from app.application.visual_evaluation.context import (
    VisualEvaluationContext,
    load_visual_evaluation_context,
)
from app.application.visual_evaluation.evidence import (
    build_evidence_bundle,
    evidence_absolute_paths,
)
from app.application.visual_evaluation.hard_gates import run_hard_gates
from app.application.visual_evaluation.policy import (
    acceptance_policy,
    resolve_visual_routing,
    score_band_policy,
    visual_limits,
)
from app.application.visual_evaluation.refinement import (
    StaticValidationFailure,
    classify_and_build_plan,
    derive_candidate,
    refinement_images,
    refinement_prompt_values,
)
from app.application.visual_evaluation.repository import (
    VisualEvaluationRepository,
)
from app.application.visual_evaluation.scoring import (
    aggregate_critic_scorecards,
    aggregate_reviewer_decisions,
    compute_acceptance,
    validate_critic_group,
    validate_reviewer_group,
)
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.models import (
    CandidateRefinementGenerationRecord,
    CandidateRevisionRecord,
    CandidateValidationSummaryRecord,
    CandidateVisualSummaryRecord,
    Request,
)
from app.domain.schemas.visual_evaluation import (
    CandidateBaselineComparison,
    RefinementGeneration,
    RefinementOutput,
    VisualCallMetrics,
    VisualEvaluationSummary,
    VisualFinding,
)


class VisualEvaluationError(RuntimeError):
    pass


def _contracts_payload(context: VisualEvaluationContext) -> str:
    composition = context.contracts.composition
    return canonical_json(
        {
            "source": composition.source.model_dump(mode="json"),
            "app_spec": composition.app_spec.model_dump(mode="json"),
            "tier_1": composition.tier_1.model_dump(mode="json"),
            "target_tier": context.candidate.target_tier,
            "target_tier_contract": composition.tier(
                context.candidate.target_tier
            ).model_dump(mode="json"),
            "product_strategy_v2": (
                composition.product_strategy_v2.model_dump(mode="json")
            ),
            "information_architecture": (
                composition.information_architecture.model_dump(mode="json")
            ),
            "design_dna": composition.design_dna.model_dump(mode="json"),
            "page_purpose": (
                context.contracts.page_purpose.model_dump(mode="json")
            ),
            "business_components": (
                context.contracts.business_components.model_dump(mode="json")
            ),
            "content_data": (
                context.contracts.content_data.model_dump(mode="json")
            ),
            "interactions": (
                context.contracts.interactions.model_dump(mode="json")
            ),
        }
    )


def _budget_guard(
    metrics: tuple[VisualCallMetrics, ...],
    *,
    limits,
    deadline: float,
    required_additional_calls: int = 0,
) -> None:
    if time.monotonic() > deadline:
        raise VisualEvaluationError("Phase 5 wall timeout exceeded")
    calls = sum(item.provider_call_count for item in metrics)
    tokens = sum(item.total_tokens for item in metrics)
    cost = sum(item.cost_usd for item in metrics)
    if calls + required_additional_calls > limits.max_calls:
        raise VisualEvaluationError("Phase 5 call ceiling would be exceeded")
    if tokens > limits.max_output_tokens:
        raise VisualEvaluationError("Phase 5 output-token ceiling exceeded")
    if cost > limits.max_cost_usd:
        raise VisualEvaluationError("Phase 5 cost ceiling exceeded")


def _summary(
    *,
    context: VisualEvaluationContext,
    attempt_uuid: str,
    subject: str,
    status: str,
    repairability: str,
    bundle,
    hard_gate,
    baseline,
    critic,
    reviewer,
    acceptance,
    plan,
    generation,
    metrics: tuple[VisualCallMetrics, ...],
    started: float,
    diagnostics: tuple[str, ...] = (),
    original_summary_sha256: str | None = None,
) -> VisualEvaluationSummary:
    return VisualEvaluationSummary(
        refs=context.refs,
        attempt_uuid=attempt_uuid,
        subject=subject,
        status=status,
        repairability=repairability,
        evidence_bundle_sha256=artifact_sha256(bundle),
        hard_gate_sha256=artifact_sha256(hard_gate),
        critic_scorecard_sha256=(
            artifact_sha256(critic) if critic else None
        ),
        reviewer_decision_sha256=(
            artifact_sha256(reviewer) if reviewer else None
        ),
        baseline_comparison_sha256=artifact_sha256(baseline),
        acceptance_computation=acceptance,
        refinement_plan_sha256=(
            artifact_sha256(plan) if plan else None
        ),
        refinement_generation_sha256=(
            artifact_sha256(generation) if generation else None
        ),
        original_summary_sha256=original_summary_sha256,
        call_metrics=metrics,
        provider_call_count=sum(
            item.provider_call_count for item in metrics
        ),
        prompt_tokens=sum(item.prompt_tokens for item in metrics),
        completion_tokens=sum(item.completion_tokens for item in metrics),
        total_tokens=sum(item.total_tokens for item in metrics),
        cost_usd=sum(item.cost_usd for item in metrics),
        latency_ms=int((time.monotonic() - started) * 1000),
        diagnostics=diagnostics,
    )


def _result(
    context: VisualEvaluationContext,
    *,
    summary,
    summary_row_id: int,
    summary_sha256: str,
    cache_hit: bool,
) -> dict[str, Any]:
    preview = dict(context.phase4_summary)
    preview.update(
        {
            "status": summary.status,
            "visual_evaluation_summary": {
                "id": summary_row_id,
                "attempt_uuid": summary.attempt_uuid,
                "sha256": summary_sha256,
                "repairability": summary.repairability,
            },
            "visual_evaluation": {
                "subject": summary.subject,
                "provider_call_count": 0
                if cache_hit
                else summary.provider_call_count,
                "persisted_provider_call_count": (
                    summary.provider_call_count
                ),
                "prompt_tokens": 0 if cache_hit else summary.prompt_tokens,
                "completion_tokens": (
                    0 if cache_hit else summary.completion_tokens
                ),
                "total_tokens": 0 if cache_hit else summary.total_tokens,
                "cost_usd": 0.0 if cache_hit else summary.cost_usd,
                "latency_ms": summary.latency_ms,
                "cache_hit": cache_hit,
                "cache_hits": (
                    ["full_visual_evaluation"] if cache_hit else []
                ),
                "diagnostics": list(summary.diagnostics),
            },
        }
    )
    return {"preview_contract": preview}


def _evaluate_models(
    context: VisualEvaluationContext,
    *,
    bundle,
    hard_gate,
    routing,
    ai_provider,
    template_renderer,
    deadline,
    metrics_before: tuple[VisualCallMetrics, ...],
    subject: str,
    comparison: dict[str, Any] | None = None,
) -> tuple[tuple, Any, tuple, Any, tuple[VisualCallMetrics, ...]]:
    limits = visual_limits()
    group_count = len(bundle.grouping_manifest)
    _budget_guard(
        metrics_before,
        limits=limits,
        deadline=deadline,
        required_additional_calls=2 * group_count,
    )
    contracts_json = _contracts_payload(context)
    hard_gate_json = canonical_json(hard_gate.model_dump(mode="json"))
    critic_partials = []
    metrics = list(metrics_before)
    for group in bundle.grouping_manifest:
        built = build_critic_group(
            request_id=context.refs.request_id,
            group=group,
            bundle=bundle,
            routing=routing[0],
            contracts_json=contracts_json,
            hard_gate_json=hard_gate_json,
            ai_provider=ai_provider,
            template_renderer=template_renderer,
            phase_deadline=deadline,
            subject=subject,
        )
        validate_critic_group(
            built.artifact,
            subject=subject,
            group=group,
            bundle=bundle,
            hard_gate=hard_gate,
        )
        critic_partials.append(built.artifact)
        metrics.append(built.metrics)
        _budget_guard(tuple(metrics), limits=limits, deadline=deadline)
    critic = aggregate_critic_scorecards(
        bundle.grouping_manifest,
        tuple(critic_partials),
        subject=subject,
    )
    reviewer_partials = []
    for group in bundle.grouping_manifest:
        comparison_paths: tuple[Path, ...] = ()
        blind_json = "{}"
        if comparison is not None:
            comparison_paths = comparison["paths_by_group"][
                group.group_index
            ]
            blind_json = comparison["manifest_by_group"][
                group.group_index
            ]
        built = build_reviewer_group(
            request_id=context.refs.request_id,
            group=group,
            bundle=bundle,
            routing=routing[1],
            contracts_json=contracts_json,
            hard_gate_json=hard_gate_json,
            critic_scorecard_json=canonical_json(
                critic.model_dump(mode="json")
            ),
            ai_provider=ai_provider,
            template_renderer=template_renderer,
            phase_deadline=deadline,
            subject=subject,
            blind_comparison_json=blind_json,
            comparison_image_paths=comparison_paths,
        )
        validate_reviewer_group(
            built.artifact,
            subject=subject,
            group=group,
            bundle=bundle,
            hard_gate=hard_gate,
        )
        reviewer_partials.append(built.artifact)
        metrics.append(built.metrics)
        _budget_guard(tuple(metrics), limits=limits, deadline=deadline)
    reviewer = aggregate_reviewer_decisions(
        bundle.grouping_manifest,
        tuple(reviewer_partials),
        subject=subject,
    )
    return (
        tuple(critic_partials),
        critic,
        tuple(reviewer_partials),
        reviewer,
        tuple(metrics),
    )


def _blind_refinement_comparison(
    original_context,
    original_bundle,
    refined_context,
    refined_bundle,
    *,
    reviewer_capability,
) -> dict[str, Any]:
    if (
        tuple(
            (item.page_id, item.route, item.viewport)
            for item in original_bundle.ordered_screenshots
        )
        != tuple(
            (item.page_id, item.route, item.viewport)
            for item in refined_bundle.ordered_screenshots
        )
    ):
        raise ValueError("Original/refined route matrices do not match")
    original_identity = artifact_sha256(
        {
            "candidate_manifest_sha256": (
                original_context.refs.candidate_manifest_sha256
            ),
            "screenshot_set_sha256": (
                original_context.refs.screenshot_set_sha256
            ),
        }
    )
    refined_identity = artifact_sha256(
        {
            "candidate_manifest_sha256": (
                refined_context.refs.candidate_manifest_sha256
            ),
            "screenshot_set_sha256": (
                refined_context.refs.screenshot_set_sha256
            ),
        }
    )
    attempt_hash = canonical_json(
        {
            "original": original_identity,
            "refined": refined_identity,
        }
    )
    attempt_hash = __import__("hashlib").sha256(
        attempt_hash.encode("utf-8")
    ).hexdigest()
    first, second = blind_label_order(
        original_identity,
        refined_identity,
        attempt_hash=attempt_hash,
    )
    identities = {
        original_identity: (
            original_bundle,
            original_context,
        ),
        refined_identity: (
            refined_bundle,
            refined_context,
        ),
    }
    paths_by_group = {}
    manifests = {}
    refined_label = "a" if first == refined_identity else "b"
    for group in refined_bundle.grouping_manifest:
        page_ids = set(group.page_ids)
        ordered_paths = []
        label_manifest = {}
        for label, identity in (("a", first), ("b", second)):
            label_bundle, _label_context = identities[identity]
            rows = tuple(
                item
                for item in label_bundle.ordered_screenshots
                if item.page_id in page_ids
            )
            label_manifest[label] = [
                {
                    "blind_evidence_id": (
                        f"{label.upper()}-{item.evidence_id}"
                    ),
                    "route": item.route,
                    "viewport": item.viewport,
                    "image_order": len(ordered_paths) + index,
                }
                for index, item in enumerate(rows)
            ]
            ordered_paths.extend(
                evidence_absolute_paths(
                    label_bundle,
                    tuple(item.evidence_id for item in rows),
                )
            )
        if (
            len(ordered_paths) > reviewer_capability.max_images
            or sum(path.stat().st_size for path in ordered_paths)
            > reviewer_capability.max_aggregate_image_bytes
            or any(
                path.stat().st_size > reviewer_capability.max_image_bytes
                for path in ordered_paths
            )
        ):
            raise ValueError(
                "Blind original/refined bundle exceeds reviewer limits"
            )
        paths_by_group[group.group_index] = tuple(ordered_paths)
        manifests[group.group_index] = canonical_json(
            {
                "attempt_hash": attempt_hash,
                "labels": label_manifest,
                "candidate_creation_times_withheld": True,
                "accepted_identity_withheld": True,
            }
        )
    return {
        "attempt_hash": attempt_hash,
        "first": first,
        "second": second,
        "refined_label": refined_label,
        "paths_by_group": paths_by_group,
        "manifest_by_group": manifests,
    }


def _blind_tier_baseline_comparison(
    baseline_context,
    baseline_bundle,
    candidate_context,
    candidate_bundle,
    *,
    reviewer_capability,
) -> dict[str, Any]:
    baseline_identity = artifact_sha256(
        {
            "candidate_revision_id": baseline_context.candidate.id,
            "candidate_manifest_sha256": (
                baseline_context.refs.candidate_manifest_sha256
            ),
            "screenshot_set_sha256": (
                baseline_context.refs.screenshot_set_sha256
            ),
        }
    )
    candidate_identity = artifact_sha256(
        {
            "candidate_revision_id": candidate_context.candidate.id,
            "candidate_manifest_sha256": (
                candidate_context.refs.candidate_manifest_sha256
            ),
            "screenshot_set_sha256": (
                candidate_context.refs.screenshot_set_sha256
            ),
        }
    )
    attempt_hash = artifact_sha256(
        {
            "baseline": baseline_identity,
            "candidate": candidate_identity,
            "policy": settings.V2_VISUAL_POLICY_REVISION,
        }
    )
    first, second = blind_label_order(
        baseline_identity,
        candidate_identity,
        attempt_hash=attempt_hash,
    )
    label_candidate = "a" if first == candidate_identity else "b"
    bundles = {
        baseline_identity: baseline_bundle,
        candidate_identity: candidate_bundle,
    }
    baseline_pages = {
        item.page_id for item in baseline_bundle.ordered_screenshots
    }
    shared_fallback_pages = tuple(
        dict.fromkeys(
            item.page_id
            for item in candidate_bundle.ordered_screenshots
            if item.page_id in baseline_pages
        )
    )
    paths_by_group = {}
    manifests = {}
    for group in candidate_bundle.grouping_manifest:
        matched_pages = tuple(
            page_id for page_id in group.page_ids
            if page_id in baseline_pages
        )
        candidate_only_pages = tuple(
            page_id for page_id in group.page_ids
            if page_id not in baseline_pages
        )
        if not matched_pages:
            if not shared_fallback_pages:
                raise ValueError(
                    "Scoped visual evaluation has no matched baseline route"
                )
            matched_pages = (shared_fallback_pages[0],)
        ordered_paths: list[Path] = []
        label_manifest = {}
        for label, identity in (("a", first), ("b", second)):
            bundle = bundles[identity]
            rows = tuple(
                item for item in bundle.ordered_screenshots
                if item.page_id in matched_pages
            )
            expected = {
                (page_id, viewport)
                for page_id in matched_pages
                for viewport in ("mobile", "tablet", "desktop")
            }
            if {
                (item.page_id, item.viewport) for item in rows
            } != expected:
                raise ValueError(
                    "Tier 1 baseline lacks an exact semantic route/viewport "
                    "match"
                )
            label_manifest[label] = [
                {
                    "blind_evidence_id": (
                        f"{label.upper()}-{item.evidence_id}"
                    ),
                    "route": item.route,
                    "viewport": item.viewport,
                    "image_order": len(ordered_paths) + index,
                }
                for index, item in enumerate(rows)
            ]
            ordered_paths.extend(
                evidence_absolute_paths(
                    bundle,
                    tuple(item.evidence_id for item in rows),
                )
            )
        candidate_only = tuple(
            item for item in candidate_bundle.ordered_screenshots
            if item.page_id in candidate_only_pages
        )
        candidate_only_manifest = [
            {
                "evidence_id": item.evidence_id,
                "route": item.route,
                "viewport": item.viewport,
                "image_order": len(ordered_paths) + index,
                "comparison": "absolute_tier_2_route",
            }
            for index, item in enumerate(candidate_only)
        ]
        ordered_paths.extend(
            evidence_absolute_paths(
                candidate_bundle,
                tuple(item.evidence_id for item in candidate_only),
            )
        )
        if (
            len(ordered_paths) > reviewer_capability.max_images
            or sum(path.stat().st_size for path in ordered_paths)
            > reviewer_capability.max_aggregate_image_bytes
            or any(
                path.stat().st_size > reviewer_capability.max_image_bytes
                for path in ordered_paths
            )
        ):
            raise ValueError("Tier 1 blind comparison exceeds reviewer limits")
        paths_by_group[group.group_index] = tuple(ordered_paths)
        manifests[group.group_index] = canonical_json(
            {
                "attempt_hash": attempt_hash,
                "labels": label_manifest,
                "candidate_only_new_tier_routes": candidate_only_manifest,
                "candidate_creation_times_withheld": True,
                "accepted_identity_withheld": True,
                "same_policy_baseline_required": True,
            }
        )
    return {
        "attempt_hash": attempt_hash,
        "first": first,
        "second": second,
        "candidate_label": label_candidate,
        "baseline_identity": baseline_identity,
        "candidate_identity": candidate_identity,
        "paths_by_group": paths_by_group,
        "manifest_by_group": manifests,
    }


def _not_worse(
    original_acceptance,
    refined_acceptance,
) -> bool:
    original = dict(original_acceptance.dimension_scores)
    refined = dict(refined_acceptance.dimension_scores)
    blocking_dimensions = (
        "business_specificity",
        "design_dna_adherence",
        "conversion_strength",
        "mobile_quality",
        "trust_and_professionalism",
    )
    return (
        refined_acceptance.weighted_overall
        >= original_acceptance.weighted_overall
        and all(refined[item] >= original[item] for item in blocking_dimensions)
        and refined_acceptance.blocking_finding_count == 0
    )


def evaluate_v2_candidate_visuals(
    db: Session,
    request_id: int,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    *,
    req: Request,
    phase4_result: dict[str, Any],
    baseline_phase4_result: dict[str, Any] | None = None,
    baseline_visual_summary_id: int | None = None,
    evidence_page_ids: tuple[str, ...] | None = None,
    require_no_baseline_regression: bool = False,
    update_request_bundle: bool = True,
) -> dict[str, Any]:
    """Evaluate one immutable runtime-validated Tier 1 candidate."""

    if not (
        settings.PREVIEW_GENERATOR_V2
        and settings.V2_RUNTIME_VALIDATION_ENABLED
        and settings.V2_VISUAL_EVALUATION_ENABLED
    ):
        raise VisualEvaluationError("Phase 5 visual evaluation is disabled")
    started = time.monotonic()
    routing = resolve_visual_routing()
    limits = visual_limits()
    deadline = started + limits.phase_timeout_seconds
    bands = score_band_policy()
    acceptance_rules = acceptance_policy()
    context = load_visual_evaluation_context(
        db,
        request_id=request_id,
        phase4_result=phase4_result,
    )
    bundle = build_evidence_bundle(
        context,
        critic_capability=routing[0].capability,
        reviewer_capability=routing[1].capability,
        page_ids=evidence_page_ids,
    )
    hard_gate = run_hard_gates(context, bundle)
    comparison = None
    baseline_identity = None
    if baseline_phase4_result is not None:
        if baseline_visual_summary_id is None:
            raise ValueError("Explicit baseline visual summary is required")
        baseline_context = load_visual_evaluation_context(
            db,
            request_id=request_id,
            phase4_result=baseline_phase4_result,
        )
        baseline_summary_row = db.get(
            CandidateVisualSummaryRecord,
            baseline_visual_summary_id,
        )
        if (
            baseline_summary_row is None
            or baseline_summary_row.request_id != request_id
            or baseline_summary_row.candidate_revision_id
            != baseline_context.candidate.id
            or baseline_summary_row.status != "candidate_visual_accepted"
            or baseline_context.candidate.target_tier != 1
            or context.candidate.target_tier != 2
            or baseline_context.screenshots[0].capture_policy_revision
            != context.screenshots[0].capture_policy_revision
        ):
            raise ValueError("Tier 1 visual baseline is not eligible")
        baseline_page_ids = tuple(
            page_id
            for page_id in (evidence_page_ids or ())
            if page_id
            in {
                item.page_id
                for item in baseline_context.contracts.page_purpose.pages
            }
        )
        if not baseline_page_ids:
            raise ValueError("Visual regression scope lacks a Tier 1 route")
        baseline_bundle = build_evidence_bundle(
            baseline_context,
            critic_capability=routing[0].capability,
            reviewer_capability=routing[1].capability,
            page_ids=baseline_page_ids,
        )
        comparison = _blind_tier_baseline_comparison(
            baseline_context,
            baseline_bundle,
            context,
            bundle,
            reviewer_capability=routing[1].capability,
        )
        baseline_identity = comparison["baseline_identity"]
        baseline = CandidateBaselineComparison(
            mode="absolute_only",
            reason=(
                "A same-policy Tier 1 baseline was validated; blind "
                "comparison is completed only after reviewer scoring."
            ),
            attempt_hash=comparison["attempt_hash"],
        )
    else:
        baseline = resolve_baseline(
            context,
            attempt_hash=artifact_sha256(context.refs),
        )
    eval_key = evaluation_cache_key(
        refs=context.refs,
        bundle=bundle,
        routing=routing,
        limits=limits,
        score_bands=bands,
        acceptance=acceptance_rules,
        baseline_identity=baseline_identity,
    )
    repository = VisualEvaluationRepository(db)
    cached = repository.load_complete_cache(
        request_id=request_id,
        candidate_revision_id=context.candidate.id,
        evaluation_key=eval_key,
        refs=context.refs,
        expected_bundle=bundle,
        expected_hard_gate=hard_gate,
        routing=routing,
        limits=limits,
    )
    if cached is not None:
        if require_no_baseline_regression and (
            cached.baseline.mode != "blind_pair"
            or baseline_identity
            not in {
                cached.baseline.label_a_identity_sha256,
                cached.baseline.label_b_identity_sha256,
            }
        ):
            raise ValueError(
                "Cached scoped result lacks its accepted baseline"
            )
        if cached.summary.repairability == "rejected_repairable":
            generation_row = (
                db.query(CandidateRefinementGenerationRecord)
                .filter(
                    CandidateRefinementGenerationRecord
                    .original_candidate_revision_id
                    == context.candidate.id
                )
                .order_by(CandidateRefinementGenerationRecord.id.desc())
                .first()
            )
            if generation_row is not None:
                derived_candidate = db.get(
                    CandidateRevisionRecord,
                    generation_row.derived_candidate_revision_id,
                )
                derived_runtime = (
                    db.query(CandidateValidationSummaryRecord)
                    .filter(
                        CandidateValidationSummaryRecord
                        .candidate_revision_id
                        == generation_row.derived_candidate_revision_id,
                        CandidateValidationSummaryRecord.status
                        == "candidate_runtime_validated",
                    )
                    .order_by(CandidateValidationSummaryRecord.id.desc())
                    .first()
                )
                if derived_candidate is None or derived_runtime is None:
                    raise ValueError(
                        "Cached refinement runtime lineage is incomplete"
                    )
                refined_preview = dict(context.phase4_summary)
                refined_preview.update(
                    {
                        "status": "candidate_runtime_validated",
                        "candidate_revision": {
                            "id": derived_candidate.id,
                            "revision_uuid": (
                                derived_candidate.revision_uuid
                            ),
                            "revision": derived_candidate.revision,
                            "target_tier": derived_candidate.target_tier,
                            "workspace_relpath": (
                                derived_candidate.workspace_relpath
                            ),
                            "file_manifest_sha256": (
                                derived_candidate.file_manifest_sha256
                            ),
                        },
                        "runtime_validation_summary": {
                            "id": derived_runtime.id,
                            "attempt_uuid": "",
                            "sha256": derived_runtime.summary_sha256,
                        },
                    }
                )
                refined_phase4 = {"preview_contract": refined_preview}
                refined_context = load_visual_evaluation_context(
                    db,
                    request_id=request_id,
                    phase4_result=refined_phase4,
                )
                if (
                    refined_context.candidate.id
                    != generation_row.derived_candidate_revision_id
                ):
                    raise ValueError(
                        "Cached refinement lineage is cross-candidate"
                    )
                refined_bundle = build_evidence_bundle(
                    refined_context,
                    critic_capability=routing[0].capability,
                    reviewer_capability=routing[1].capability,
                )
                refined_gate = run_hard_gates(
                    refined_context,
                    refined_bundle,
                )
                refined_key = evaluation_cache_key(
                    refs=refined_context.refs,
                    bundle=refined_bundle,
                    routing=routing,
                    limits=limits,
                    score_bands=bands,
                    acceptance=acceptance_rules,
                    baseline_identity=context.refs.screenshot_set_sha256,
                )
                refined_cached = repository.load_complete_cache(
                    request_id=request_id,
                    candidate_revision_id=refined_context.candidate.id,
                    evaluation_key=refined_key,
                    refs=refined_context.refs,
                    expected_bundle=refined_bundle,
                    expected_hard_gate=refined_gate,
                    routing=routing,
                    limits=limits,
                )
                if refined_cached is None:
                    raise ValueError(
                        "Partial refined Phase 5 cache fails closed"
                    )
                return _result(
                    refined_context,
                    summary=refined_cached.summary,
                    summary_row_id=refined_cached.summary_row.id,
                    summary_sha256=(
                        refined_cached.summary_row.artifact_sha256
                    ),
                    cache_hit=True,
                )
        return _result(
            context,
            summary=cached.summary,
            summary_row_id=cached.summary_row.id,
            summary_sha256=cached.summary_row.artifact_sha256,
            cache_hit=True,
        )
    attempt_uuid = str(uuid.uuid4())
    if not hard_gate.passed:
        summary = _summary(
            context=context,
            attempt_uuid=attempt_uuid,
            subject="original",
            status="candidate_visual_rejected",
            repairability="rejected_not_repairable",
            bundle=bundle,
            hard_gate=hard_gate,
            baseline=baseline,
            critic=None,
            reviewer=None,
            acceptance=None,
            plan=None,
            generation=None,
            metrics=(),
            started=started,
            diagnostics=tuple(
                item.code
                for item in hard_gate.findings
                if item.severity == "blocking"
            ),
        )
        try:
            row, _ = repository.persist_terminal(
                req=req,
                refs=context.refs,
                subject="original",
                evaluation_key=eval_key,
                routing=routing,
                limits=limits,
                score_bands=bands,
                acceptance=acceptance_rules,
                bundle=bundle,
                hard_gate=hard_gate,
                critic_partials=(),
                critic=None,
                reviewer_partials=(),
                reviewer=None,
                baseline=baseline,
                plan=None,
                generation=None,
                metrics=(),
                summary=summary,
                update_request_bundle=update_request_bundle,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        return _result(
            context,
            summary=summary,
            summary_row_id=row.id,
            summary_sha256=row.artifact_sha256,
            cache_hit=False,
        )

    (
        critic_partials,
        critic,
        reviewer_partials,
        reviewer,
        metrics,
    ) = _evaluate_models(
        context,
        bundle=bundle,
        hard_gate=hard_gate,
        routing=routing,
        ai_provider=ai_provider,
        template_renderer=template_renderer,
        deadline=deadline,
        metrics_before=(),
        subject="original",
        comparison=comparison,
    )
    if comparison is not None:
        baseline = CandidateBaselineComparison(
            mode="blind_pair",
            reason=(
                "Accepted baseline and cumulative candidate were compared "
                "under the same Phase 4 capture and Phase 5 evaluation "
                "policies."
            ),
            attempt_hash=comparison["attempt_hash"],
            label_a_identity_sha256=comparison["first"],
            label_b_identity_sha256=comparison["second"],
            dimensions=reviewer.comparative_dimensions,
        )
    calculation = compute_acceptance(
        critic,
        reviewer,
        hard_gate,
        acceptance_rules,
    )
    if require_no_baseline_regression:
        candidate_label = comparison["candidate_label"] if comparison else ""
        no_regression = (
            len(reviewer.comparative_dimensions) == 6
            and (
                (
                    reviewer.comparative_result
                    == f"{candidate_label}_preferred"
                    and all(
                        item.preferred in {candidate_label, "equal"}
                        for item in reviewer.comparative_dimensions
                    )
                )
                or (
                    reviewer.comparative_result == "inconclusive"
                    and all(
                        item.preferred == "equal"
                        for item in reviewer.comparative_dimensions
                    )
                )
            )
        )
        calculation = calculation.model_copy(
            update={
                "threshold_checks": (
                    *calculation.threshold_checks,
                    ("tier_1_no_material_regression", no_regression),
                ),
                "accepted": calculation.accepted and no_regression,
            }
        )
    findings: tuple[VisualFinding, ...] = (
        *critic.findings,
        *reviewer.blocking_findings,
    )
    if calculation.accepted:
        summary = _summary(
            context=context,
            attempt_uuid=attempt_uuid,
            subject="original",
            status="candidate_visual_accepted",
            repairability="accepted",
            bundle=bundle,
            hard_gate=hard_gate,
            baseline=baseline,
            critic=critic,
            reviewer=reviewer,
            acceptance=calculation,
            plan=None,
            generation=None,
            metrics=metrics,
            started=started,
        )
        try:
            row, _ = repository.persist_terminal(
                req=req,
                refs=context.refs,
                subject="original",
                evaluation_key=eval_key,
                routing=routing,
                limits=limits,
                score_bands=bands,
                acceptance=acceptance_rules,
                bundle=bundle,
                hard_gate=hard_gate,
                critic_partials=critic_partials,
                critic=critic,
                reviewer_partials=reviewer_partials,
                reviewer=reviewer,
                baseline=baseline,
                plan=None,
                generation=None,
                metrics=metrics,
                summary=summary,
                update_request_bundle=update_request_bundle,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        return _result(
            context,
            summary=summary,
            summary_row_id=row.id,
            summary_sha256=row.artifact_sha256,
            cache_hit=False,
        )

    repairability, plan = classify_and_build_plan(
        db,
        context,
        findings=findings,
        bundle=bundle,
        limits=limits,
    )
    # Grouped originals cannot fit the approved 5/6-call refinement path.
    if plan is not None and len(bundle.grouping_manifest) != 1:
        repairability, plan = "rejected_not_repairable", None
    original_summary = _summary(
        context=context,
        attempt_uuid=attempt_uuid,
        subject="original",
        status="candidate_visual_rejected",
        repairability=repairability,
        bundle=bundle,
        hard_gate=hard_gate,
        baseline=baseline,
        critic=critic,
        reviewer=reviewer,
        acceptance=calculation,
        plan=plan,
        generation=None,
        metrics=metrics,
        started=started,
        diagnostics=(
            ()
            if repairability == "rejected_repairable"
            else ("visual_rejection_not_safely_repairable",)
        ),
    )
    try:
        original_row, _ = repository.persist_terminal(
            req=req,
            refs=context.refs,
            subject="original",
            evaluation_key=eval_key,
            routing=routing,
            limits=limits,
            score_bands=bands,
            acceptance=acceptance_rules,
            bundle=bundle,
            hard_gate=hard_gate,
            critic_partials=critic_partials,
            critic=critic,
            reviewer_partials=reviewer_partials,
            reviewer=reviewer,
            baseline=baseline,
            plan=plan,
            generation=None,
            metrics=metrics,
            summary=original_summary,
            update_request_bundle=update_request_bundle,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    if plan is None:
        return _result(
            context,
            summary=original_summary,
            summary_row_id=original_row.id,
            summary_sha256=original_row.artifact_sha256,
            cache_hit=False,
        )

    def refinement_failed(
        diagnostic: str,
        failure_metrics: tuple[VisualCallMetrics, ...],
    ) -> dict[str, Any]:
        failure_key = artifact_sha256(
            {
                "evaluation_key": eval_key,
                "stage": "refinement_failed",
                "metrics": [
                    item.model_dump(mode="json")
                    for item in failure_metrics
                ],
                "diagnostic": diagnostic,
            }
        )
        failure_summary = _summary(
            context=context,
            attempt_uuid=str(uuid.uuid4()),
            subject="original",
            status="candidate_refinement_failed",
            repairability="rejected_repairable",
            bundle=bundle,
            hard_gate=hard_gate,
            baseline=baseline,
            critic=critic,
            reviewer=reviewer,
            acceptance=calculation,
            plan=plan,
            generation=None,
            metrics=failure_metrics,
            started=started,
            diagnostics=(diagnostic[:4000],),
            original_summary_sha256=original_row.artifact_sha256,
        )
        try:
            failure_row, _ = repository.persist_terminal(
                req=req,
                refs=context.refs,
                subject="original",
                evaluation_key=failure_key,
                routing=routing,
                limits=limits,
                score_bands=bands,
                acceptance=acceptance_rules,
                bundle=bundle,
                hard_gate=hard_gate,
                critic_partials=critic_partials,
                critic=critic,
                reviewer_partials=reviewer_partials,
                reviewer=reviewer,
                baseline=baseline,
                plan=plan,
                generation=None,
                metrics=failure_metrics,
                summary=failure_summary,
                update_request_bundle=update_request_bundle,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        return _result(
            context,
            summary=failure_summary,
            summary_row_id=failure_row.id,
            summary_sha256=failure_row.artifact_sha256,
            cache_hit=False,
        )

    def failed_call_metric(stage_index: int, stage: str) -> VisualCallMetrics:
        route = routing[stage_index]
        return VisualCallMetrics(
            stage=stage,
            group_index=None,
            model=route.capability.model,
            provider=str(
                getattr(ai_provider, "name", "unknown") or "unknown"
            ),
            family=route.capability.family,
            capability=route.capability.capability,
            prompt_revision=route.prompt_revision,
            temperature=route.temperature,
            max_tokens=route.max_tokens,
            cache_hit=False,
            provider_call_count=1,
            transport_retry_count=0,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost_usd=0.0,
            latency_ms=0,
        )

    _budget_guard(
        metrics,
        limits=limits,
        deadline=deadline,
        required_additional_calls=3,
    )
    try:
        refinement = build_refinement(
            request_id=request_id,
            routing=routing[2],
            prompt_values=refinement_prompt_values(context, plan, findings),
            image_paths=refinement_images(bundle, plan),
            ai_provider=ai_provider,
            template_renderer=template_renderer,
            phase_deadline=deadline,
        )
    except Exception as exc:
        return refinement_failed(
            f"refinement_generation_failed:{type(exc).__name__}:{exc}",
            (*metrics, failed_call_metric(2, "refinement")),
        )
    metrics = (*metrics, refinement.metrics)
    _budget_guard(metrics, limits=limits, deadline=deadline)
    technical = None
    try:
        derived = derive_candidate(
            db,
            context,
            plan=plan,
            output=refinement.artifact,
        )
    except StaticValidationFailure as initial_error:
        _budget_guard(
            metrics,
            limits=limits,
            deadline=deadline,
            required_additional_calls=3,
        )
        current_sources = [
            {
                "path": item.path,
                "sha256": __import__(
                    "hashlib"
                ).sha256(item.source.encode("utf-8")).hexdigest(),
                "source": item.source,
            }
            for item in refinement.artifact.files
        ]
        try:
            technical = build_technical_repair(
                request_id=request_id,
                routing=routing[3],
                prompt_values={
                    "diagnostics_json": canonical_json(
                        [str(initial_error)[:4000]]
                    ),
                    "allowed_sources_json": canonical_json(current_sources),
                    "contracts_json": _contracts_payload(context),
                },
                ai_provider=ai_provider,
                template_renderer=template_renderer,
                phase_deadline=deadline,
            )
        except Exception as exc:
            return refinement_failed(
                f"technical_repair_failed:{type(exc).__name__}:{exc}",
                (*metrics, failed_call_metric(3, "technical_repair")),
            )
        metrics = (*metrics, technical.metrics)
        _budget_guard(metrics, limits=limits, deadline=deadline)
        try:
            derived = derive_candidate(
                db,
                context,
                plan=plan,
                output=refinement.artifact,
                technical_output=technical.artifact,
            )
        except Exception as exc:
            db.rollback()
            return refinement_failed(
                f"technical_repair_validation_failed:"
                f"{type(exc).__name__}:{exc}",
                metrics,
            )
    except Exception as exc:
        db.rollback()
        return refinement_failed(
            f"refinement_contract_violation:{type(exc).__name__}:{exc}",
            metrics,
        )
    db.commit()
    refined_phase4 = validate_v2_candidate_runtime(
        db,
        request_id,
        req=req,
        phase3b_result=derived.phase3b_result,
    )
    if (
        refined_phase4.get("preview_contract", {}).get("status")
        != "candidate_runtime_validated"
    ):
        return refinement_failed(
            "refined_candidate_failed_full_phase4_validation",
            metrics,
        )
    refined_context = load_visual_evaluation_context(
        db,
        request_id=request_id,
        phase4_result=refined_phase4,
    )
    refined_bundle = build_evidence_bundle(
        refined_context,
        critic_capability=routing[0].capability,
        reviewer_capability=routing[1].capability,
    )
    refined_hard_gate = run_hard_gates(refined_context, refined_bundle)
    comparison = _blind_refinement_comparison(
        context,
        bundle,
        refined_context,
        refined_bundle,
        reviewer_capability=routing[1].capability,
    )
    (
        refined_critic_partials,
        refined_critic,
        refined_reviewer_partials,
        refined_reviewer,
        all_metrics,
    ) = _evaluate_models(
        refined_context,
        bundle=refined_bundle,
        hard_gate=refined_hard_gate,
        routing=routing,
        ai_provider=ai_provider,
        template_renderer=template_renderer,
        deadline=deadline,
        metrics_before=metrics,
        subject="refined",
        comparison=comparison,
    )
    refined_calculation = compute_acceptance(
        refined_critic,
        refined_reviewer,
        refined_hard_gate,
        acceptance_rules,
    )
    preferred = (
        f"{comparison['refined_label']}_preferred"
        == refined_reviewer.comparative_result
    )
    refinement_accepted = (
        refined_calculation.accepted
        and preferred
        and _not_worse(calculation, refined_calculation)
    )
    refined_baseline = CandidateBaselineComparison(
        mode="blind_pair",
        reason=(
            "Original and refined runtime-validated candidates were "
            "blindly labeled from the attempt hash."
        ),
        attempt_hash=comparison["attempt_hash"],
        label_a_identity_sha256=comparison["first"],
        label_b_identity_sha256=comparison["second"],
        dimensions=refined_reviewer.comparative_dimensions,
    )
    generation = RefinementGeneration(
        original_candidate_revision_id=context.candidate.id,
        derived_candidate_revision_id=refined_context.candidate.id,
        refinement_plan_sha256=artifact_sha256(plan),
        output_sha256=artifact_sha256(refinement.artifact),
        allowed_file_hashes_before=derived.allowed_before,
        allowed_file_hashes_after=derived.allowed_after,
        unaffected_manifest_sha256_before=derived.unaffected_before,
        unaffected_manifest_sha256_after=derived.unaffected_after,
        phase3b_static_gate_sha256=artifact_sha256(derived.static_report),
        phase3b_static_gate_passed=derived.static_report.passed,
        phase4_summary_id=refined_context.runtime_summary_row.id,
        phase4_summary_sha256=(
            refined_context.runtime_summary_row.summary_sha256
        ),
        technical_repair_count=derived.technical_repair_count,
    )
    refined_key = evaluation_cache_key(
        refs=refined_context.refs,
        bundle=refined_bundle,
        routing=routing,
        limits=limits,
        score_bands=bands,
        acceptance=acceptance_rules,
        baseline_identity=context.refs.screenshot_set_sha256,
    )
    refined_summary = _summary(
        context=refined_context,
        attempt_uuid=str(uuid.uuid4()),
        subject="refined",
        status=(
            "candidate_visual_accepted"
            if refinement_accepted
            else "candidate_visual_rejected"
        ),
        repairability=(
            "accepted" if refinement_accepted else "rejected_not_repairable"
        ),
        bundle=refined_bundle,
        hard_gate=refined_hard_gate,
        baseline=refined_baseline,
        critic=refined_critic,
        reviewer=refined_reviewer,
        acceptance=(
            refined_calculation
            if refinement_accepted
            else refined_calculation.model_copy(update={"accepted": False})
        ),
        plan=plan,
        generation=generation,
        metrics=all_metrics,
        started=started,
        diagnostics=(
            ()
            if refinement_accepted
            else ("refinement_worse_or_inconclusive",)
        ),
        original_summary_sha256=original_row.artifact_sha256,
    )
    try:
        refined_row, _ = repository.persist_terminal(
            req=req,
            refs=refined_context.refs,
            subject="refined",
            evaluation_key=refined_key,
            routing=routing,
            limits=limits,
            score_bands=bands,
            acceptance=acceptance_rules,
            bundle=refined_bundle,
            hard_gate=refined_hard_gate,
            critic_partials=refined_critic_partials,
            critic=refined_critic,
            reviewer_partials=refined_reviewer_partials,
            reviewer=refined_reviewer,
            baseline=refined_baseline,
            plan=plan,
            generation=generation,
            metrics=all_metrics,
            summary=refined_summary,
            refinement_output=refinement.artifact,
            technical_repair_output=(
                technical.artifact if technical else None
            ),
            update_request_bundle=update_request_bundle,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _result(
        refined_context,
        summary=refined_summary,
        summary_row_id=refined_row.id,
        summary_sha256=refined_row.artifact_sha256,
        cache_hit=False,
    )


__all__ = [
    "VisualEvaluationError",
    "evaluate_v2_candidate_visuals",
]
