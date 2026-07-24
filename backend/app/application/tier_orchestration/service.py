"""Phase 6A coordinator: extend accepted Tier 1 to cumulative Tier 2."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.application.candidate_generation.cache import canonical_sha256
from app.application.candidate_generation.context import load_candidate_context
from app.application.runtime_validation.policy import tool_versions
from app.application.runtime_validation.service import (
    validate_v2_candidate_runtime,
)
from app.application.tier_orchestration.generation import (
    BuiltTier2Candidate,
    build_tier_2_candidate,
)
from app.application.tier_orchestration.policy import (
    preflight_tier_2_budget,
    tier_2_budget,
)
from app.application.tier_orchestration.preservation import (
    classify_tier_1_files,
    finalize_preservation_audit,
)
from app.application.tier_orchestration.projection import (
    build_tier_2_extension_contracts,
    extension_contract_sha256,
    project_tier_2_delta,
)
from app.application.tier_orchestration.repository import (
    Tier2OrchestrationRepository,
)
from app.application.tier_orchestration.validation import (
    assert_accepted_workspace_unchanged,
)
from app.application.visual_evaluation.context import (
    load_visual_evaluation_context,
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
    CandidateArtifactRecord,
    CandidateBaselineComparisonRecord,
    CandidateRevisionRecord,
    CandidateValidationSummaryRecord,
    CandidateVisualSummaryRecord,
    Request,
)
from app.domain.schemas.tier_orchestration import Tier2Telemetry
from app.infrastructure.db.migrations import (
    assert_candidate_target_tier_constraint,
)


class Tier2OrchestrationError(RuntimeError):
    pass


def _safe_candidate_workspace(candidate: CandidateRevisionRecord) -> Path:
    if not candidate.workspace_relpath:
        raise ValueError("Accepted candidate workspace is missing")
    root = settings.PREVIEW_CANDIDATES_DIR.resolve(strict=False)
    workspace = (root / candidate.workspace_relpath).resolve(strict=False)
    try:
        workspace.relative_to(root)
    except ValueError as exc:
        raise ValueError("Accepted candidate workspace escapes its root") from exc
    if not workspace.is_dir():
        raise ValueError("Accepted candidate workspace does not exist")
    return workspace


def _accepted_rows(
    db: Session,
    candidate: CandidateRevisionRecord,
) -> tuple[CandidateArtifactRecord, ...]:
    ids = (
        candidate.foundation_artifact_id,
        candidate.data_artifact_id,
        candidate.component_artifact_id,
        candidate.page_artifact_id,
        candidate.route_artifact_id,
        candidate.validation_artifact_id,
    )
    rows = tuple(db.get(CandidateArtifactRecord, item) for item in ids)
    if any(row is None for row in rows):
        raise ValueError("Accepted Tier 1 artifact chain is incomplete")
    return tuple(rows)


def _visual_scope(context, projection) -> tuple[str, ...]:
    ordered_pages = tuple(
        page.page_id for page in context.page_purpose.pages
    )
    mandatory: list[str] = []

    def add(values) -> None:
        for value in values:
            if value in ordered_pages and value not in mandatory:
                mandatory.append(value)

    add(projection.delta.page_ids)
    add(projection.lower_tier_integration_page_ids)
    add(context.composition.tier_1.primary_journey_proof.page_ids)
    for role_id in projection.tier_1_references.role_ids:
        for surface in ("public", "ops"):
            page = next(
                (
                    item
                    for item in context.page_purpose.pages
                    if role_id in item.role_ids
                    and item.surface == surface
                    and item.page_id
                    not in set(projection.delta.page_ids)
                    and item.page_id not in mandatory
                ),
                None,
            )
            if page is not None:
                add((page.page_id,))
    routing = resolve_visual_routing()
    image_limit = min(
        routing[0].capability.max_images,
        routing[1].capability.max_images,
    )
    lower_pages = set(projection.tier_1_references.page_ids)
    all_comparison_images = (
        6 * len(lower_pages & set(ordered_pages))
        + 3 * len(set(ordered_pages) - lower_pages)
    )
    if 3 * len(ordered_pages) <= image_limit and (
        all_comparison_images <= routing[1].capability.max_images
    ):
        return ordered_pages
    # Ensure a matched primary Tier 1 route is first so a bounded group always
    # has an explicit same-policy baseline.
    primary = context.composition.tier_1.primary_journey_proof.page_ids[0]
    return tuple(
        item
        for item in ordered_pages
        if item in ({primary} | set(mandatory))
    )


def _baseline_phase4_result(phase5_result: dict[str, Any]) -> dict[str, Any]:
    summary = dict(phase5_result.get("preview_contract") or {})
    summary["status"] = "candidate_runtime_validated"
    return {"preview_contract": summary}


def _telemetry(
    *,
    started: float,
    built: BuiltTier2Candidate | None,
    visual_summary: dict[str, Any] | None,
) -> Tier2Telemetry:
    generation_metrics = built.metrics if built else ()
    visual = dict((visual_summary or {}).get("visual_evaluation") or {})
    generation_calls = sum(
        item.provider_call_count for item in generation_metrics
    )
    visual_calls = int(visual.get("provider_call_count") or 0)
    completion_tokens = sum(
        item.completion_tokens for item in generation_metrics
    ) + int(visual.get("completion_tokens") or 0)
    cost = sum(item.cost_usd for item in generation_metrics) + float(
        visual.get("cost_usd") or 0.0
    )
    telemetry = Tier2Telemetry(
        provider_call_count=generation_calls + visual_calls,
        output_tokens=completion_tokens,
        cost_usd=cost,
        latency_ms=max(0, int((time.monotonic() - started) * 1000)),
        generation_call_count=generation_calls,
        visual_call_count=visual_calls,
        cache_hits=(
            (built.generation_cache_hits if built else 0)
            + len(visual.get("cache_hits") or ())
        ),
    )
    if (
        telemetry.provider_call_count > settings.V2_TIER2_MAX_CALLS
        or telemetry.output_tokens > settings.V2_TIER2_MAX_OUTPUT_TOKENS
        or telemetry.cost_usd > settings.V2_TIER2_MAX_COST_USD
        or telemetry.latency_ms
        > settings.V2_TIER2_MAX_WALL_SECONDS * 1000
    ):
        raise Tier2OrchestrationError(
            "Tier 2 aggregate call/token/cost/time budget exceeded"
        )
    return telemetry


def orchestrate_v2_tier_2(
    db: Session,
    request_id: int,
    ai_provider,
    template_renderer,
    *,
    req: Request,
    phase5_result: dict[str, Any],
) -> dict[str, Any]:
    """Run Tier 2 only; disabled mode returns the exact Phase 5 object."""

    if not settings.V2_TIER2_GENERATION_ENABLED:
        return phase5_result
    assert_candidate_target_tier_constraint(db.get_bind())
    started = time.monotonic()
    phase5_summary = dict(phase5_result.get("preview_contract") or {})
    if phase5_summary.get("status") != "candidate_visual_accepted":
        raise Tier2OrchestrationError(
            "Tier 2 requires accepted Tier 1 visual status"
        )
    candidate_ref = phase5_summary.get("candidate_revision") or {}
    visual_ref = phase5_summary.get("visual_evaluation_summary") or {}
    accepted = db.get(CandidateRevisionRecord, candidate_ref.get("id"))
    accepted_visual = db.get(
        CandidateVisualSummaryRecord,
        visual_ref.get("id"),
    )
    if (
        accepted is None
        or accepted.request_id != request_id
        or accepted.target_tier != 1
        or accepted.status != "candidate_build_pending"
        or accepted.file_manifest_sha256
        != candidate_ref.get("file_manifest_sha256")
        or accepted_visual is None
        or accepted_visual.request_id != request_id
        or accepted_visual.candidate_revision_id != accepted.id
        or accepted_visual.status != "candidate_visual_accepted"
        or accepted_visual.artifact_sha256 != visual_ref.get("sha256")
    ):
        raise Tier2OrchestrationError(
            "Accepted Tier 1 candidate/visual lineage is invalid"
        )
    accepted_workspace = _safe_candidate_workspace(accepted)
    assert_accepted_workspace_unchanged(
        accepted_workspace,
        expected_manifest_sha256=accepted.file_manifest_sha256,
    )
    phase3a_summary = dict(phase5_summary)
    phase3a_summary["status"] = "composition_contract_ready"
    phase3a_summary["target_tier"] = 1
    inherited = load_candidate_context(
        db,
        request_id=request_id,
        phase3a_result={"preview_contract": phase3a_summary},
    )
    projection = project_tier_2_delta(
        inherited.composition,
        accepted_tier_1_revision_id=accepted.id,
        accepted_tier_1_manifest_sha256=accepted.file_manifest_sha256,
        accepted_tier_1_visual_summary_id=accepted_visual.id,
    )
    accepted_artifact_rows = _accepted_rows(db, accepted)
    classification_probe = classify_tier_1_files(
        accepted=accepted,
        accepted_workspace=accepted_workspace,
        artifact_rows=accepted_artifact_rows,
        inherited_context=inherited,
        projection=projection,
        extension_contract_sha256="0" * 64,
    )
    budget = tier_2_budget()
    upstream_refs = {
        "accepted_tier_1_revision_id": accepted.id,
        "accepted_tier_1_manifest_sha256": accepted.file_manifest_sha256,
        "accepted_tier_1_visual_summary_id": accepted_visual.id,
        "tier_1_closure_sha256": projection.tier_1_closure_sha256,
        "tier_2_closure_sha256": projection.tier_2_closure_sha256,
        "delta_sha256": projection.delta_sha256,
        "preservation_classification_sha256": canonical_sha256(
            [
                item.model_dump(mode="json")
                for item in classification_probe.entries
            ]
        ),
        "phase2_hashes": [
            inherited.refs.composition_contract_refs.product_strategy_v2_ref.sha256,
            inherited.refs.composition_contract_refs.information_architecture_ref.sha256,
            inherited.refs.composition_contract_refs.design_dna_ref.sha256,
        ],
        "phase3a_hashes": [
            inherited.refs.page_purpose_ref.sha256,
            inherited.refs.business_component_plan_ref.sha256,
            inherited.refs.content_data_plan_ref.sha256,
            inherited.refs.interaction_contract_ref.sha256,
            inherited.refs.component_dependency_graph_ref.sha256,
        ],
        "dependency_lock_sha256": accepted.dependency_lock_sha256,
        "component_model": settings.V2_TIER2_COMPONENT_MODEL,
        "page_model": settings.V2_TIER2_PAGE_MODEL,
        "repair_model": settings.V2_TIER2_REPAIR_MODEL,
        "repair_prompt_revision": (
            settings.V2_CANDIDATE_REPAIR_PROMPT_REVISION
        ),
        "repair_max_tokens": settings.V2_CANDIDATE_REPAIR_MAX_TOKENS,
        "repair_timeout_seconds": (
            settings.V2_CANDIDATE_REPAIR_TIMEOUT_SECONDS
        ),
        "generation_policy_revision": (
            settings.V2_TIER2_GENERATION_POLICY_REVISION
        ),
        "runtime_policy_revision": settings.V2_RUNTIME_POLICY_REVISION,
        "runtime_tool_versions": tool_versions().model_dump(mode="json"),
        "visual_policy_revision": settings.V2_VISUAL_POLICY_REVISION,
        "visual_routing": [
            item.model_dump(mode="json")
            for item in resolve_visual_routing()
        ],
        "visual_limits": visual_limits().model_dump(mode="json"),
        "budget": budget.model_dump(mode="json"),
    }
    resume_identity = canonical_sha256(upstream_refs)
    repository = Tier2OrchestrationRepository(db)
    terminal = repository.find_terminal(
        request_id=request_id,
        resume_identity_sha256=resume_identity,
    )
    if terminal is not None:
        if terminal.summary.derived_candidate_revision_id is not None:
            derived = db.get(
                CandidateRevisionRecord,
                terminal.summary.derived_candidate_revision_id,
            )
            if derived is None or not derived.file_manifest_sha256:
                raise Tier2OrchestrationError(
                    "Cached Tier 2 candidate manifest is missing"
                )
            assert_accepted_workspace_unchanged(
                _safe_candidate_workspace(derived),
                expected_manifest_sha256=derived.file_manifest_sha256,
            )
        return terminal.result
    attempt = repository.get_or_create_attempt(
        request_id=request_id,
        accepted_tier_1_revision_id=accepted.id,
        accepted_tier_1_visual_summary_id=accepted_visual.id,
        accepted_manifest_sha256=accepted.file_manifest_sha256,
        tier_closure_sha256=projection.tier_2_closure_sha256,
        delta_sha256=projection.delta_sha256,
        generation_policy_revision=(
            settings.V2_TIER2_GENERATION_POLICY_REVISION
        ),
        resume_identity_sha256=resume_identity,
        upstream_refs=upstream_refs,
        budget=budget,
    )
    contracts, refs = build_tier_2_extension_contracts(
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
    db.commit()
    extension_ref = {
        "id": extension.id,
        "sha256": extension.manifest_sha256,
        "orchestration_attempt_id": attempt.id,
    }
    initial_preservation = classify_tier_1_files(
        accepted=accepted,
        accepted_workspace=accepted_workspace,
        artifact_rows=accepted_artifact_rows,
        inherited_context=inherited,
        projection=projection,
        extension_contract_sha256=extension_contract_sha256(contracts),
    )
    built: BuiltTier2Candidate | None = None
    phase4: dict[str, Any] | None = None
    phase5: dict[str, Any] | None = None
    phase4_id = None
    phase5_id = None
    baseline_id = None
    failure_stage = None
    fallback_reason = None
    final_preservation = initial_preservation
    try:
        preflight_tier_2_budget(
            db,
            request_id=request_id,
            ai_provider=ai_provider,
        )
        deadline = started + settings.V2_TIER2_MAX_WALL_SECONDS
        built = build_tier_2_candidate(
            db,
            req=req,
            accepted=accepted,
            accepted_workspace=accepted_workspace,
            inherited_context=inherited,
            contracts=contracts,
            refs=refs,
            preservation=initial_preservation,
            extension_manifest_ref=extension_ref,
            ai_provider=ai_provider,
            template_renderer=template_renderer,
            phase5_summary=phase5_summary,
            phase_deadline=deadline,
        )
        final_preservation = built.preservation
        phase4 = validate_v2_candidate_runtime(
            db,
            request_id,
            req=req,
            phase3b_result={"preview_contract": built.summary},
            update_request_bundle=False,
        )
        phase4_summary = dict(phase4.get("preview_contract") or {})
        phase4_ref = phase4_summary.get("runtime_validation_summary") or {}
        phase4_id = phase4_ref.get("id")
        if phase4_summary.get("status") != "candidate_runtime_validated":
            raise Tier2OrchestrationError(
                "Complete Phase 4 rejected cumulative Tier 2"
            )
        if (phase4_summary.get("candidate_revision") or {}).get("id") != (
            built.candidate.id
        ):
            raise Tier2OrchestrationError(
                "Phase 4 repair changed the Tier 2 candidate revision"
            )
        scope = _visual_scope(built.context, projection)
        phase5 = evaluate_v2_candidate_visuals(
            db,
            request_id,
            ai_provider,
            template_renderer,
            req=req,
            phase4_result=phase4,
            baseline_phase4_result=_baseline_phase4_result(phase5_result),
            baseline_visual_summary_id=accepted_visual.id,
            evidence_page_ids=scope,
            require_no_baseline_regression=True,
            update_request_bundle=False,
        )
        phase5_terminal = dict(phase5.get("preview_contract") or {})
        phase5_ref = phase5_terminal.get("visual_evaluation_summary") or {}
        phase5_id = phase5_ref.get("id")
        if phase5_terminal.get("status") != "candidate_visual_accepted":
            raise Tier2OrchestrationError(
                "Phase 5 rejected cumulative Tier 2"
            )
        visual_row = db.get(CandidateVisualSummaryRecord, phase5_id)
        if (
            visual_row is None
            or visual_row.candidate_revision_id != built.candidate.id
        ):
            raise Tier2OrchestrationError(
                "Tier 2 Phase 5 lineage is invalid"
            )
        baseline_row = (
            db.query(CandidateBaselineComparisonRecord)
            .filter(
                CandidateBaselineComparisonRecord.visual_attempt_id
                == visual_row.visual_attempt_id
            )
            .first()
        )
        if baseline_row is None or baseline_row.mode != "blind_pair":
            raise Tier2OrchestrationError(
                "Tier 2 acceptance lacks Tier 1 regression comparison"
            )
        baseline_id = baseline_row.id
        final_candidate = db.get(
            CandidateRevisionRecord,
            (phase5_terminal.get("candidate_revision") or {}).get("id"),
        )
        if final_candidate is None or final_candidate.target_tier != 2:
            raise Tier2OrchestrationError(
                "Phase 5 accepted a non-Tier-2 revision"
            )
        if final_candidate.id != built.candidate.id:
            final_preservation = finalize_preservation_audit(
                initial_preservation,
                final_workspace=_safe_candidate_workspace(final_candidate),
            )
        telemetry = _telemetry(
            started=started,
            built=built,
            visual_summary=phase5_terminal,
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
            "complete_phase4_reused": True,
            "tier_1_journeys_rerun": True,
        }
        visual_payload = {
            "passed": True,
            "phase5_visual_summary_id": phase5_id,
            "baseline_comparison_id": baseline_id,
            "tier_1_regression_checked": True,
            "scope_page_ids": list(scope),
            "complete_phase5_reused": True,
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
            status="tier_2_accepted",
            failure_stage=None,
            fallback_reason=None,
            telemetry=telemetry,
        )
        db.commit()
        return terminal.result
    except Exception as exc:
        db.rollback()
        if failure_stage is None:
            if built is None:
                failure_stage = "tier_2_generation"
            elif phase4 is None or (
                (phase4.get("preview_contract") or {}).get("status")
                != "candidate_runtime_validated"
            ):
                failure_stage = "phase4_runtime_validation"
            else:
                failure_stage = "phase5_visual_evaluation"
        fallback_reason = f"{type(exc).__name__}: {exc}"[:4000]
        if built is None:
            final_preservation = finalize_preservation_audit(
                initial_preservation,
                final_workspace=accepted_workspace,
            )
        try:
            telemetry = _telemetry(
                started=started,
                built=built,
                visual_summary=(
                    dict((phase5 or {}).get("preview_contract") or {})
                    if phase5
                    else None
                ),
            )
        except Exception:
            generation_calls = sum(
                item.provider_call_count for item in (built.metrics if built else ())
            )
            telemetry = Tier2Telemetry(
                provider_call_count=min(10, generation_calls),
                output_tokens=sum(
                    item.completion_tokens
                    for item in (built.metrics if built else ())
                ),
                cost_usd=sum(
                    item.cost_usd for item in (built.metrics if built else ())
                ),
                latency_ms=max(
                    0,
                    int((time.monotonic() - started) * 1000),
                ),
                generation_call_count=min(4, generation_calls),
                visual_call_count=0,
                cache_hits=(
                    built.generation_cache_hits if built else 0
                ),
            )
        generation_succeeded = built is not None
        phase4_succeeded = bool(
            phase4
            and (phase4.get("preview_contract") or {}).get("status")
            == "candidate_runtime_validated"
        )
        phase5_succeeded = bool(
            phase5
            and (phase5.get("preview_contract") or {}).get("status")
            == "candidate_visual_accepted"
        )
        generation_payload = {
            "passed": generation_succeeded,
            "candidate_revision_id": built.candidate.id if built else None,
            "output_tokens": sum(
                item.completion_tokens
                for item in (built.metrics if built else ())
            ),
            "cost_usd": sum(
                item.cost_usd for item in (built.metrics if built else ())
            ),
            "latency_ms": sum(
                item.latency_ms for item in (built.metrics if built else ())
            ),
            "failure": fallback_reason,
            "full_product_regeneration": False,
        }
        validation_payload = {
            "passed": phase4_succeeded,
            "phase4_validation_summary_id": phase4_id,
            "failure": fallback_reason,
        }
        visual_payload = {
            "passed": phase5_succeeded,
            "phase5_visual_summary_id": phase5_id,
            "baseline_comparison_id": baseline_id,
            "tier_1_regression_checked": baseline_id is not None,
            "phase5_status": (
                (phase5 or {}).get("preview_contract", {}).get("status")
                if phase5
                else None
            ),
            "phase5_evaluation": (
                (phase5 or {}).get("preview_contract", {}).get(
                    "visual_evaluation"
                )
                if phase5
                else None
            ),
            "failure": fallback_reason,
        }
        terminal = Tier2OrchestrationRepository(db).persist_terminal(
            attempt=attempt,
            extension=extension,
            preservation=final_preservation,
            generation_payload=generation_payload,
            generation_passed=generation_succeeded,
            validation_payload=validation_payload,
            validation_passed=phase4_succeeded,
            visual_payload=visual_payload,
            visual_passed=phase5_succeeded,
            derived_candidate_revision_id=(
                built.candidate.id if built else None
            ),
            phase4_validation_summary_id=phase4_id,
            phase5_visual_summary_id=phase5_id,
            baseline_comparison_id=baseline_id,
            status="tier_2_failed_serving_tier_1",
            failure_stage=failure_stage,
            fallback_reason=fallback_reason,
            telemetry=telemetry,
        )
        db.commit()
        assert_accepted_workspace_unchanged(
            accepted_workspace,
            expected_manifest_sha256=accepted.file_manifest_sha256,
        )
        return terminal.result


__all__ = [
    "Tier2OrchestrationError",
    "orchestrate_v2_tier_2",
]
