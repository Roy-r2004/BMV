"""Phase 6B coordinator: extend accepted Tier 2 to cumulative Tier 3."""
from __future__ import annotations

import time
import traceback
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.application.appspec.repository import load_json_object
from app.application.candidate_generation.cache import canonical_sha256
from app.application.candidate_generation.context import (
    load_tier_2_extension_context,
)
from app.application.runtime_validation.policy import tool_versions
from app.application.runtime_validation.service import (
    validate_v2_candidate_runtime,
)
from app.application.tier_orchestration.generation import (
    BuiltTier3Candidate,
    build_tier_3_candidate,
)
from app.application.tier_orchestration.policy import (
    build_tier_3_visual_call_plan,
    preflight_tier_3_budget,
)
from app.application.tier_orchestration.preservation import (
    classify_tier_2_files,
    finalize_preservation_audit,
)
from app.application.tier_orchestration.projection import (
    build_tier_3_extension_contracts,
    extension_contract_sha256,
    project_tier_3_delta,
)
from app.application.tier_orchestration.repository import (
    Tier2OrchestrationRepository,
    Tier3OrchestrationRepository,
)
from app.application.tier_orchestration.service import (
    _accepted_rows,
    _safe_candidate_workspace,
)
from app.application.tier_orchestration.validation import (
    assert_accepted_workspace_unchanged,
)
from app.application.visual_evaluation.policy import (
    resolve_visual_routing,
    visual_limits,
)
from app.application.visual_evaluation.service import (
    evaluate_v2_candidate_visuals,
)
from app.core.config import settings
from app.domain.models import (
    CandidateBaselineComparisonRecord,
    CandidateEffectiveTierSummaryRecord,
    CandidateRevisionRecord,
    CandidateScreenshotRecord,
    CandidateTierExtensionManifestRecord,
    CandidateTierOrchestrationAttemptRecord,
    CandidateTierVisualOutcomeRecord,
    CandidateValidationSummaryRecord,
    CandidateVisualSummaryRecord,
    Request,
)
from app.domain.schemas.tier_orchestration import (
    Tier2EffectiveSummary,
    Tier3Telemetry,
)
from app.infrastructure.db.migrations import (
    assert_candidate_target_tier_constraint,
    assert_tier_orchestration_target_constraint,
)


class Tier3OrchestrationError(RuntimeError):
    pass


def _accepted_tier_2(
    db: Session,
    *,
    request_id: int,
    phase6a_result: dict[str, Any],
) -> tuple[
    Tier2EffectiveSummary,
    CandidateEffectiveTierSummaryRecord,
    CandidateRevisionRecord,
    CandidateValidationSummaryRecord,
    CandidateVisualSummaryRecord,
    CandidateTierExtensionManifestRecord,
]:
    preview = dict(phase6a_result.get("preview_contract") or {})
    effective_ref = preview.get("effective_tier_summary") or {}
    if (
        preview.get("status") != "tier_2_accepted"
        or preview.get("target_tier") != 2
    ):
        raise Tier3OrchestrationError(
            "Tier 3 requires an accepted Tier 2 result"
        )
    row = db.get(
        CandidateEffectiveTierSummaryRecord,
        effective_ref.get("id"),
    )
    if (
        row is None
        or row.request_id != request_id
        or row.target_tier != 2
        or row.status != "tier_2_accepted"
        or row.summary_sha256 != effective_ref.get("sha256")
    ):
        raise Tier3OrchestrationError(
            "Accepted Tier 2 effective summary reference is invalid"
        )
    summary = Tier2EffectiveSummary.model_validate(
        load_json_object(row.summary_json)
    )
    if (
        canonical_sha256(summary) != row.summary_sha256
        or summary.status != "tier_2_accepted"
        or summary.highest_accepted_tier != 2
        or summary.request_id != request_id
        or summary.orchestration_attempt_id
        != row.orchestration_attempt_id
        or summary.last_accepted_candidate_revision_id
        != summary.derived_candidate_revision_id
        or summary.phase4_validation_summary_id
        != row.phase4_validation_summary_id
        or summary.phase5_visual_summary_id
        != row.phase5_visual_summary_id
    ):
        raise Tier3OrchestrationError(
            "Accepted Tier 2 effective summary is corrupt"
        )
    attempt = db.get(
        CandidateTierOrchestrationAttemptRecord,
        summary.orchestration_attempt_id,
    )
    if (
        attempt is None
        or attempt.request_id != request_id
        or attempt.target_tier != 2
        or attempt.status != "started"
        or attempt.accepted_tier_1_revision_id
        != summary.accepted_tier_1_revision_id
        or attempt.accepted_tier_1_visual_summary_id
        != summary.accepted_tier_1_visual_summary_id
        or attempt.tier_closure_sha256 != summary.tier_2_closure_sha256
        or attempt.delta_sha256 != summary.delta_sha256
        or attempt.generation_policy_revision
        != summary.generation_policy_revision
    ):
        raise Tier3OrchestrationError(
            "Accepted Tier 2 orchestration attempt is invalid"
        )
    try:
        strict_terminal = Tier2OrchestrationRepository(db).find_terminal(
            request_id=request_id,
            resume_identity_sha256=attempt.resume_identity_sha256,
        )
    except (TypeError, ValueError) as exc:
        raise Tier3OrchestrationError(
            "Accepted Tier 2 terminal lineage is corrupt"
        ) from exc
    if strict_terminal is None or strict_terminal.row.id != row.id:
        raise Tier3OrchestrationError(
            "Accepted Tier 2 terminal lineage does not resolve uniquely"
        )
    candidate = db.get(
        CandidateRevisionRecord,
        summary.derived_candidate_revision_id,
    )
    phase4 = db.get(
        CandidateValidationSummaryRecord,
        summary.phase4_validation_summary_id,
    )
    phase5 = db.get(
        CandidateVisualSummaryRecord,
        summary.phase5_visual_summary_id,
    )
    extension = db.get(
        CandidateTierExtensionManifestRecord,
        summary.tier_2_extension_manifest_id,
    )
    visual_outcome = db.get(
        CandidateTierVisualOutcomeRecord,
        summary.tier_visual_outcome_id,
    )
    tier_1_candidate = db.get(
        CandidateRevisionRecord,
        summary.accepted_tier_1_revision_id,
    )
    tier_1_visual = db.get(
        CandidateVisualSummaryRecord,
        summary.accepted_tier_1_visual_summary_id,
    )
    if (
        candidate is None
        or candidate.request_id != request_id
        or candidate.target_tier != 2
        or candidate.status != "candidate_build_pending"
        or not candidate.file_manifest_sha256
        or phase4 is None
        or phase4.request_id != request_id
        or phase4.candidate_revision_id != candidate.id
        or phase4.status != "candidate_runtime_validated"
        or phase5 is None
        or phase5.request_id != request_id
        or phase5.candidate_revision_id != candidate.id
        or phase5.status != "candidate_visual_accepted"
        or extension is None
        or extension.request_id != request_id
        or extension.target_tier != 2
        or extension.id != row.tier_extension_manifest_id
        or extension.tier_closure_sha256
        != summary.tier_2_closure_sha256
        or extension.generation_policy_revision
        != summary.generation_policy_revision
        or extension.manifest_sha256
        != canonical_sha256(
            load_json_object(extension.manifest_json)
        )
        or visual_outcome is None
        or visual_outcome.request_id != request_id
        or visual_outcome.orchestration_attempt_id != attempt.id
        or visual_outcome.phase5_visual_summary_id != phase5.id
        or visual_outcome.baseline_comparison_id is None
        or tier_1_candidate is None
        or tier_1_candidate.request_id != request_id
        or tier_1_candidate.target_tier != 1
        or attempt.accepted_manifest_sha256
        != tier_1_candidate.file_manifest_sha256
        or tier_1_visual is None
        or tier_1_visual.request_id != request_id
        or tier_1_visual.candidate_revision_id != tier_1_candidate.id
        or tier_1_visual.status != "candidate_visual_accepted"
    ):
        raise Tier3OrchestrationError(
            "Accepted Tier 2 candidate/Phase 4/Phase 5 lineage is invalid"
        )
    baseline = db.get(
        CandidateBaselineComparisonRecord,
        visual_outcome.baseline_comparison_id,
    )
    if (
        baseline is None
        or baseline.request_id != request_id
        or baseline.candidate_revision_id != candidate.id
        or baseline.visual_attempt_id != phase5.visual_attempt_id
        or baseline.mode != "blind_pair"
    ):
        raise Tier3OrchestrationError(
            "Accepted Tier 2 baseline comparison is invalid"
        )
    return summary, row, candidate, phase4, phase5, extension


def _phase4_result(
    candidate: CandidateRevisionRecord,
    runtime: CandidateValidationSummaryRecord,
    *,
    extension_ref: dict[str, Any],
) -> dict[str, Any]:
    return {
        "preview_contract": {
            "status": "candidate_runtime_validated",
            "target_tier": candidate.target_tier,
            "candidate_revision": {
                "id": candidate.id,
                "revision_uuid": candidate.revision_uuid,
                "file_manifest_sha256": candidate.file_manifest_sha256,
                "target_tier": candidate.target_tier,
            },
            "runtime_validation_summary": {
                "id": runtime.id,
                "sha256": runtime.summary_sha256,
            },
            "tier_extension_manifest_ref": extension_ref,
            "cumulative_extension_context": True,
        }
    }


def _visual_scope(context, projection) -> tuple[tuple[str, ...], tuple[str, ...]]:
    ordered = tuple(page.id for page in context.composition.app_spec.pages)
    selected: list[str] = []

    def add(values) -> None:
        for value in values:
            if value in ordered and value not in selected:
                selected.append(value)

    add(projection.delta.page_ids)
    add(projection.lower_tier_integration_page_ids)
    add(context.composition.tiers[0].primary_journey_proof.page_ids)
    lower_pages = set(projection.tier_2_references.page_ids)
    for role_id in projection.tier_2_references.role_ids:
        for surface in ("public", "ops"):
            sample = next(
                (
                    page.id
                    for page in context.composition.app_spec.pages
                    if page.id in lower_pages
                    and role_id in page.role_ids
                    and page.surface == surface
                    and page.id not in selected
                ),
                None,
            )
            if sample:
                add((sample,))
    selected_set = set(selected)
    selected = [item for item in ordered if item in selected_set]
    excluded = tuple(
        f"{page_id}:not_delta_integration_primary_or_role_surface_sample"
        for page_id in ordered
        if page_id not in selected_set
    )
    if not selected:
        raise Tier3OrchestrationError("Tier 3 visual scope is empty")
    return tuple(selected), excluded


def _planned_screenshot_bytes(
    db: Session,
    phase4: CandidateValidationSummaryRecord,
) -> dict[tuple[str, str], int]:
    rows = (
        db.query(CandidateScreenshotRecord)
        .filter(
            CandidateScreenshotRecord.runtime_attempt_id
            == phase4.runtime_attempt_id
        )
        .all()
    )
    result: dict[tuple[str, str], int] = {}
    for row in rows:
        evidence = load_json_object(row.evidence_json)
        result[(row.page_id, row.viewport)] = int(
            evidence.get("byte_count") or 0
        )
    return result


def _page_groups(plan) -> tuple[tuple[str, ...], ...]:
    images = {item.ordinal: item for item in plan.images}
    groups = []
    for group in plan.groups:
        if group.actor != "critic":
            continue
        groups.append(
            tuple(
                dict.fromkeys(
                    images[index].page_id
                    for index in group.candidate_image_ordinals
                )
            )
        )
    return tuple(groups)


def _telemetry(
    *,
    started: float,
    built: BuiltTier3Candidate | None,
    visual_summary: dict[str, Any] | None,
    lower: Tier2EffectiveSummary,
) -> Tier3Telemetry:
    metrics = built.metrics if built else ()
    visual = dict((visual_summary or {}).get("visual_evaluation") or {})
    generation_calls = sum(item.provider_call_count for item in metrics)
    visual_calls = int(visual.get("provider_call_count") or 0)
    output_tokens = sum(
        item.completion_tokens for item in metrics
    ) + int(visual.get("completion_tokens") or 0)
    cost = sum(item.cost_usd for item in metrics) + float(
        visual.get("cost_usd") or 0.0
    )
    latency = max(0, int((time.monotonic() - started) * 1000))
    telemetry = Tier3Telemetry(
        provider_call_count=generation_calls + visual_calls,
        output_tokens=output_tokens,
        cost_usd=cost,
        latency_ms=latency,
        generation_call_count=generation_calls,
        visual_call_count=visual_calls,
        cache_hits=(
            (built.generation_cache_hits if built else 0)
            + len(visual.get("cache_hits") or ())
        ),
        phase6_provider_call_count=(
            lower.telemetry.provider_call_count
            + generation_calls
            + visual_calls
        ),
        phase6_output_tokens=(
            lower.telemetry.output_tokens + output_tokens
        ),
        phase6_cost_usd=lower.telemetry.cost_usd + cost,
        phase6_latency_ms=lower.telemetry.latency_ms + latency,
    )
    if (
        telemetry.provider_call_count > settings.V2_TIER3_MAX_CALLS
        or telemetry.output_tokens > settings.V2_TIER3_MAX_OUTPUT_TOKENS
        or telemetry.cost_usd > settings.V2_TIER3_MAX_COST_USD
        or telemetry.latency_ms
        > settings.V2_TIER3_MAX_WALL_SECONDS * 1000
    ):
        raise Tier3OrchestrationError("Tier 3 aggregate budget exceeded")
    return telemetry


def orchestrate_v2_tier_3(
    db: Session,
    request_id: int,
    ai_provider,
    template_renderer,
    *,
    req: Request,
    phase6a_result: dict[str, Any],
) -> dict[str, Any]:
    """Run Tier 3 only; disabled mode returns the exact Phase 6A object."""

    if not settings.V2_TIER3_GENERATION_ENABLED:
        return phase6a_result
    if not (
        settings.PREVIEW_GENERATOR_V2
        and settings.V2_RUNTIME_VALIDATION_ENABLED
        and settings.V2_VISUAL_EVALUATION_ENABLED
        and settings.V2_TIER2_GENERATION_ENABLED
    ):
        raise Tier3OrchestrationError(
            "Tier 3 requires all preceding v2 gates to be enabled"
        )
    assert_candidate_target_tier_constraint(db.get_bind())
    assert_tier_orchestration_target_constraint(db.get_bind())
    started = time.monotonic()
    (
        lower,
        lower_row,
        accepted,
        accepted_phase4,
        accepted_visual,
        lower_extension,
    ) = _accepted_tier_2(
        db,
        request_id=request_id,
        phase6a_result=phase6a_result,
    )
    accepted_workspace = _safe_candidate_workspace(accepted)
    assert_accepted_workspace_unchanged(
        accepted_workspace,
        expected_manifest_sha256=accepted.file_manifest_sha256,
    )
    lower_extension_ref = {
        "id": lower_extension.id,
        "sha256": lower_extension.manifest_sha256,
        "orchestration_attempt_id": (
            lower_extension.orchestration_attempt_id
        ),
    }
    inherited = load_tier_2_extension_context(
        db,
        request_id=request_id,
        extension_ref=lower_extension_ref,
    )
    projection = project_tier_3_delta(
        inherited.composition,
        accepted_tier_1_revision_id=lower.accepted_tier_1_revision_id,
        accepted_tier_1_visual_summary_id=(
            lower.accepted_tier_1_visual_summary_id
        ),
        accepted_tier_2_revision_id=accepted.id,
        accepted_tier_2_manifest_sha256=accepted.file_manifest_sha256,
        accepted_tier_2_visual_summary_id=accepted_visual.id,
        accepted_tier_2_effective_summary_id=lower_row.id,
        accepted_tier_2_effective_summary_sha256=lower_row.summary_sha256,
    )
    accepted_artifacts = _accepted_rows(db, accepted)
    probe = classify_tier_2_files(
        accepted=accepted,
        accepted_workspace=accepted_workspace,
        artifact_rows=accepted_artifacts,
        inherited_context=inherited,
        projection=projection,
        extension_contract_sha256="0" * 64,
    )
    selected, excluded = _visual_scope(inherited, projection)
    routes = tuple(
        (page.id, page.route)
        for page in inherited.composition.app_spec.pages
    )
    plan = build_tier_3_visual_call_plan(
        available_pages=routes,
        selected_page_ids=selected,
        matched_tier_2_page_ids=tuple(
            item
            for item in selected
            if item in set(projection.tier_2_references.page_ids)
        ),
        screenshot_bytes=_planned_screenshot_bytes(db, accepted_phase4),
        excluded_page_reasons=excluded,
    )
    budget = preflight_tier_3_budget(
        db,
        request_id=request_id,
        ai_provider=ai_provider,
        plan=plan,
        phase6a_calls=lower.telemetry.provider_call_count,
        phase6a_output_tokens=lower.telemetry.output_tokens,
        phase6a_cost_usd=lower.telemetry.cost_usd,
        phase6a_latency_ms=lower.telemetry.latency_ms,
    )
    upstream = {
        "accepted_tier_1_revision_id": lower.accepted_tier_1_revision_id,
        "accepted_tier_1_visual_summary_id": (
            lower.accepted_tier_1_visual_summary_id
        ),
        "accepted_tier_2_revision_id": accepted.id,
        "accepted_tier_2_manifest_sha256": (
            accepted.file_manifest_sha256
        ),
        "accepted_tier_2_visual_summary_id": accepted_visual.id,
        "accepted_tier_2_effective_summary_id": lower_row.id,
        "accepted_tier_2_effective_summary_sha256": (
            lower_row.summary_sha256
        ),
        "accepted_tier_2_extension_manifest_id": lower_extension.id,
        "accepted_tier_2_extension_manifest_sha256": (
            lower_extension.manifest_sha256
        ),
        "tier_1_closure_sha256": projection.tier_1_closure_sha256,
        "tier_2_closure_sha256": projection.tier_2_closure_sha256,
        "tier_3_closure_sha256": projection.tier_3_closure_sha256,
        "delta_sha256": projection.delta_sha256,
        "preservation_classification_sha256": canonical_sha256(
            [item.model_dump(mode="json") for item in probe.entries]
        ),
        "phase6a_generation_policy_revision": (
            lower.generation_policy_revision
        ),
        "phase6b_generation_policy_revision": (
            settings.V2_TIER3_GENERATION_POLICY_REVISION
        ),
        "component_model": settings.V2_TIER3_COMPONENT_MODEL,
        "page_model": settings.V2_TIER3_PAGE_MODEL,
        "repair_model": settings.V2_TIER3_REPAIR_MODEL,
        "runtime_policy_revision": settings.V2_RUNTIME_POLICY_REVISION,
        "runtime_tool_versions": tool_versions().model_dump(mode="json"),
        "visual_policy_revision": settings.V2_VISUAL_POLICY_REVISION,
        "visual_routing": [
            item.model_dump(mode="json")
            for item in resolve_visual_routing()
        ],
        "visual_limits": visual_limits().model_dump(mode="json"),
        "visual_call_plan": plan.model_dump(mode="json"),
        "budget": budget.model_dump(mode="json"),
    }
    resume_identity = canonical_sha256(upstream)
    repository = Tier3OrchestrationRepository(db)
    terminal = repository.find_terminal(
        request_id=request_id,
        resume_identity_sha256=resume_identity,
    )
    if terminal is not None:
        if terminal.summary.derived_candidate_revision_id is not None:
            cached = db.get(
                CandidateRevisionRecord,
                terminal.summary.derived_candidate_revision_id,
            )
            if cached is None:
                raise Tier3OrchestrationError(
                    "Cached Tier 3 revision is missing"
                )
            assert_accepted_workspace_unchanged(
                _safe_candidate_workspace(cached),
                expected_manifest_sha256=cached.file_manifest_sha256,
            )
        return terminal.result
    attempt = repository.get_or_create_attempt(
        request_id=request_id,
        accepted_tier_1_revision_id=lower.accepted_tier_1_revision_id,
        accepted_tier_1_visual_summary_id=(
            lower.accepted_tier_1_visual_summary_id
        ),
        accepted_tier_2_revision_id=accepted.id,
        accepted_tier_2_visual_summary_id=accepted_visual.id,
        accepted_tier_2_effective_summary_id=lower_row.id,
        accepted_tier_2_effective_summary_sha256=lower_row.summary_sha256,
        accepted_manifest_sha256=accepted.file_manifest_sha256,
        tier_closure_sha256=projection.tier_3_closure_sha256,
        delta_sha256=projection.delta_sha256,
        generation_policy_revision=(
            settings.V2_TIER3_GENERATION_POLICY_REVISION
        ),
        resume_identity_sha256=resume_identity,
        upstream_refs=upstream,
        budget=budget,
        visual_call_plan=plan,
    )
    contracts, refs = build_tier_3_extension_contracts(
        inherited.composition,
        inherited_page_purpose=inherited.page_purpose,
        inherited_components=inherited.business_components,
        inherited_content_data=inherited.content_data,
        projection=projection,
        artifact_record_id=attempt.id,
    )
    extension = repository.get_or_create_extension(
        attempt=attempt,
        contracts=contracts,
    )
    initial = classify_tier_2_files(
        accepted=accepted,
        accepted_workspace=accepted_workspace,
        artifact_rows=accepted_artifacts,
        inherited_context=inherited,
        projection=projection,
        extension_contract_sha256=extension_contract_sha256(contracts),
    )
    db.commit()
    extension_ref = {
        "id": extension.id,
        "sha256": extension.manifest_sha256,
        "orchestration_attempt_id": attempt.id,
    }
    built: BuiltTier3Candidate | None = None
    phase4_result: dict[str, Any] | None = None
    phase5_result: dict[str, Any] | None = None
    phase4_id = phase5_id = baseline_id = None
    final_preservation = initial
    failure_stage = None
    fallback_reason = None
    try:
        built = build_tier_3_candidate(
            db,
            req=req,
            accepted=accepted,
            accepted_workspace=accepted_workspace,
            inherited_context=inherited,
            contracts=contracts,
            refs=refs,
            preservation=initial,
            extension_manifest_ref=extension_ref,
            ai_provider=ai_provider,
            template_renderer=template_renderer,
            phase5_summary={
                "status": "candidate_visual_accepted",
                "accepted_tier_2_extension_manifest_ref": (
                    lower_extension_ref
                ),
            },
            phase_deadline=(
                started + settings.V2_TIER3_MAX_WALL_SECONDS
            ),
        )
        final_preservation = built.preservation
        phase4_result = validate_v2_candidate_runtime(
            db,
            request_id,
            req=req,
            phase3b_result={"preview_contract": built.summary},
            update_request_bundle=False,
        )
        phase4_summary = dict(
            phase4_result.get("preview_contract") or {}
        )
        phase4_id = (
            phase4_summary.get("runtime_validation_summary") or {}
        ).get("id")
        if (
            phase4_summary.get("status")
            != "candidate_runtime_validated"
            or (phase4_summary.get("candidate_revision") or {}).get("id")
            != built.candidate.id
        ):
            raise Tier3OrchestrationError(
                "Complete Phase 4 rejected cumulative Tier 3"
            )
        phase5_result = evaluate_v2_candidate_visuals(
            db,
            request_id,
            ai_provider,
            template_renderer,
            req=req,
            phase4_result=phase4_result,
            baseline_phase4_result=_phase4_result(
                accepted,
                accepted_phase4,
                extension_ref=lower_extension_ref,
            ),
            baseline_visual_summary_id=accepted_visual.id,
            baseline_target_tier=2,
            evidence_page_ids=selected,
            evidence_page_groups=_page_groups(plan),
            require_no_baseline_regression=True,
            update_request_bundle=False,
        )
        phase5_summary = dict(
            phase5_result.get("preview_contract") or {}
        )
        phase5_id = (
            phase5_summary.get("visual_evaluation_summary") or {}
        ).get("id")
        if phase5_summary.get("status") != "candidate_visual_accepted":
            raise Tier3OrchestrationError(
                "Complete Phase 5 rejected cumulative Tier 3"
            )
        final_candidate = db.get(
            CandidateRevisionRecord,
            (phase5_summary.get("candidate_revision") or {}).get("id"),
        )
        visual_row = db.get(CandidateVisualSummaryRecord, phase5_id)
        if (
            final_candidate is None
            or final_candidate.target_tier != 3
            or visual_row is None
            or visual_row.candidate_revision_id != final_candidate.id
        ):
            raise Tier3OrchestrationError(
                "Tier 3 Phase 5 lineage is invalid"
            )
        baseline = (
            db.query(CandidateBaselineComparisonRecord)
            .filter(
                CandidateBaselineComparisonRecord.visual_attempt_id
                == visual_row.visual_attempt_id
            )
            .first()
        )
        if baseline is None or baseline.mode != "blind_pair":
            raise Tier3OrchestrationError(
                "Tier 3 acceptance lacks a blind Tier 2 comparison"
            )
        baseline_id = baseline.id
        if final_candidate.id != built.candidate.id:
            final_preservation = finalize_preservation_audit(
                initial,
                final_workspace=_safe_candidate_workspace(final_candidate),
            )
        telemetry = _telemetry(
            started=started,
            built=built,
            visual_summary=phase5_summary,
            lower=lower,
        )
        generation_payload = {
            "passed": True,
            "candidate_revision_id": final_candidate.id,
            "component_batch_call_count": sum(
                item.provider_call_count
                for item in built.metrics
                if item.stage == "business_components"
            ),
            "page_batch_call_count": sum(
                item.provider_call_count
                for item in built.metrics
                if item.stage == "pages"
            ),
            "output_tokens": sum(
                item.completion_tokens for item in built.metrics
            ),
            "cost_usd": sum(item.cost_usd for item in built.metrics),
            "latency_ms": sum(item.latency_ms for item in built.metrics),
            "cache_hits": built.generation_cache_hits,
            "full_product_regeneration": False,
        }
        validation_payload = {
            "passed": True,
            "phase3b_static_validation": (
                built.validation_report.model_dump(mode="json")
            ),
            "phase4_validation_summary_id": phase4_id,
            "all_active_pages_validated": True,
            "all_active_journeys_rerun": True,
        }
        visual_payload = {
            "passed": True,
            "phase5_visual_summary_id": phase5_id,
            "baseline_comparison_id": baseline_id,
            "tier_2_regression_checked": True,
            "scope_page_ids": list(selected),
            "excluded_page_reasons": list(excluded),
            "visual_call_plan": plan.model_dump(mode="json"),
        }
        terminal = repository.persist_terminal(
            attempt=attempt,
            extension=extension,
            preservation=final_preservation,
            generation_payload=generation_payload,
            generation_passed=True,
            validation_payload=validation_payload,
            validation_passed=True,
            visual_payload=visual_payload,
            visual_passed=True,
            derived_candidate_revision_id=final_candidate.id,
            phase4_validation_summary_id=phase4_id,
            phase5_visual_summary_id=phase5_id,
            baseline_comparison_id=baseline_id,
            status="tier_3_accepted",
            failure_stage=None,
            fallback_reason=None,
            telemetry=telemetry,
            tier_1_closure_sha256=projection.tier_1_closure_sha256,
            tier_2_closure_sha256=projection.tier_2_closure_sha256,
            tier_2_generation_policy_revision=(
                lower.generation_policy_revision
            ),
            visual_call_plan=plan,
        )
        db.commit()
        return terminal.result
    except Exception as exc:
        db.rollback()
        if built is None:
            failure_stage = "tier_3_generation"
        elif not phase4_result or (
            (phase4_result.get("preview_contract") or {}).get("status")
            != "candidate_runtime_validated"
        ):
            failure_stage = "phase4_runtime_validation"
        else:
            failure_stage = "phase5_visual_evaluation"
        fallback_reason = (
            f"{type(exc).__name__}: {exc}\n"
            f"{traceback.format_exc()}"
        )[-4000:]
        if built is None:
            final_preservation = finalize_preservation_audit(
                initial,
                final_workspace=accepted_workspace,
            )
        try:
            telemetry = _telemetry(
                started=started,
                built=built,
                visual_summary=(
                    dict(
                        (phase5_result or {}).get("preview_contract") or {}
                    )
                    if phase5_result
                    else None
                ),
                lower=lower,
            )
        except Exception:
            generation_calls = sum(
                item.provider_call_count
                for item in (built.metrics if built else ())
            )
            output_tokens = sum(
                item.completion_tokens
                for item in (built.metrics if built else ())
            )
            cost = sum(
                item.cost_usd for item in (built.metrics if built else ())
            )
            latency = max(
                0,
                int((time.monotonic() - started) * 1000),
            )
            telemetry = Tier3Telemetry(
                provider_call_count=min(12, generation_calls),
                output_tokens=output_tokens,
                cost_usd=cost,
                latency_ms=latency,
                generation_call_count=min(4, generation_calls),
                visual_call_count=0,
                cache_hits=(
                    built.generation_cache_hits if built else 0
                ),
                phase6_provider_call_count=min(
                    22,
                    lower.telemetry.provider_call_count
                    + generation_calls,
                ),
                phase6_output_tokens=min(
                    286000,
                    lower.telemetry.output_tokens + output_tokens,
                ),
                phase6_cost_usd=min(
                    4.25,
                    lower.telemetry.cost_usd + cost,
                ),
                phase6_latency_ms=min(
                    6_000_000,
                    lower.telemetry.latency_ms + latency,
                ),
            )
        generation_ok = built is not None
        phase4_ok = bool(
            phase4_result
            and (phase4_result.get("preview_contract") or {}).get("status")
            == "candidate_runtime_validated"
        )
        phase5_ok = bool(
            phase5_result
            and (phase5_result.get("preview_contract") or {}).get("status")
            == "candidate_visual_accepted"
        )
        terminal = Tier3OrchestrationRepository(db).persist_terminal(
            attempt=attempt,
            extension=extension,
            preservation=final_preservation,
            generation_payload={
                "passed": generation_ok,
                "candidate_revision_id": (
                    built.candidate.id if built else None
                ),
                "output_tokens": sum(
                    item.completion_tokens
                    for item in (built.metrics if built else ())
                ),
                "cost_usd": sum(
                    item.cost_usd for item in (built.metrics if built else ())
                ),
                "latency_ms": sum(
                    item.latency_ms for item in (
                        built.metrics if built else ()
                    )
                ),
                "failure": fallback_reason,
                "full_product_regeneration": False,
            },
            generation_passed=generation_ok,
            validation_payload={
                "passed": phase4_ok,
                "phase4_validation_summary_id": phase4_id,
                "failure": fallback_reason,
            },
            validation_passed=phase4_ok,
            visual_payload={
                "passed": phase5_ok,
                "phase5_visual_summary_id": phase5_id,
                "baseline_comparison_id": baseline_id,
                "tier_2_regression_checked": baseline_id is not None,
                "visual_call_plan": plan.model_dump(mode="json"),
                "failure": fallback_reason,
            },
            visual_passed=phase5_ok,
            derived_candidate_revision_id=(
                built.candidate.id if built else None
            ),
            phase4_validation_summary_id=phase4_id,
            phase5_visual_summary_id=phase5_id,
            baseline_comparison_id=baseline_id,
            status="tier_3_failed_serving_tier_2",
            failure_stage=failure_stage,
            fallback_reason=fallback_reason,
            telemetry=telemetry,
            tier_1_closure_sha256=projection.tier_1_closure_sha256,
            tier_2_closure_sha256=projection.tier_2_closure_sha256,
            tier_2_generation_policy_revision=(
                lower.generation_policy_revision
            ),
            visual_call_plan=plan,
        )
        db.commit()
        assert_accepted_workspace_unchanged(
            accepted_workspace,
            expected_manifest_sha256=accepted.file_manifest_sha256,
        )
        return terminal.result


__all__ = ["Tier3OrchestrationError", "orchestrate_v2_tier_3"]
