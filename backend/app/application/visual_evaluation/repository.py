"""Append-only Phase 5 persistence and strict full-terminal cache loading."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.application.appspec.repository import load_json_object
from app.application.appspec.source import canonical_json
from app.application.runtime_validation.cache import artifact_sha256
from app.domain.models import (
    CandidateBaselineComparisonRecord,
    CandidateRefinementGenerationRecord,
    CandidateRefinementPlanRecord,
    CandidateVisualEvaluationAttemptRecord,
    CandidateVisualEvidenceBundleRecord,
    CandidateVisualFindingRecord,
    CandidateVisualHardGateResultRecord,
    CandidateVisualReviewerDecisionRecord,
    CandidateVisualScorecardRecord,
    CandidateVisualSummaryRecord,
    Request,
)
from app.domain.schemas.visual_evaluation import (
    CandidateBaselineComparison,
    RefinementGeneration,
    RefinementOutput,
    RefinementPlan,
    ScoreBandPolicy,
    VisualAcceptancePolicy,
    VisualCallMetrics,
    VisualEvaluationLimits,
    VisualEvaluationRefs,
    VisualEvaluationSummary,
    VisualEvidenceBundle,
    VisualHardGateReport,
    VisualReviewerDecision,
    VisualScorecard,
    VisualStageRouting,
)


@dataclass(frozen=True)
class CachedVisualEvaluation:
    attempt: CandidateVisualEvaluationAttemptRecord
    bundle: VisualEvidenceBundle
    hard_gate: VisualHardGateReport
    critic: VisualScorecard | None
    reviewer: VisualReviewerDecision | None
    baseline: CandidateBaselineComparison
    plan: RefinementPlan | None
    generation: RefinementGeneration | None
    refinement_output: RefinementOutput | None
    technical_repair_output: RefinementOutput | None
    summary: VisualEvaluationSummary
    summary_row: CandidateVisualSummaryRecord


def _artifact_payload(row, schema):
    artifact = schema.model_validate(load_json_object(row.artifact_json))
    if artifact_sha256(artifact) != row.artifact_sha256:
        raise ValueError(f"Cached {schema.__name__} hash is corrupt")
    return artifact


class VisualEvaluationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def load_complete_cache(
        self,
        *,
        request_id: int,
        candidate_revision_id: int,
        evaluation_key: str,
        refs: VisualEvaluationRefs,
        expected_bundle: VisualEvidenceBundle,
        expected_hard_gate: VisualHardGateReport,
        routing: tuple[VisualStageRouting, ...],
        limits: VisualEvaluationLimits,
    ) -> CachedVisualEvaluation | None:
        attempt = (
            self.db.query(CandidateVisualEvaluationAttemptRecord)
            .filter(
                CandidateVisualEvaluationAttemptRecord.request_id
                == request_id,
                CandidateVisualEvaluationAttemptRecord.candidate_revision_id
                == candidate_revision_id,
                CandidateVisualEvaluationAttemptRecord.evaluation_cache_key
                == evaluation_key,
            )
            .order_by(CandidateVisualEvaluationAttemptRecord.id.desc())
            .first()
        )
        if attempt is None:
            return None
        if (
            attempt.refs_sha256 != artifact_sha256(refs)
            or attempt.routing_sha256 != artifact_sha256(routing)
            or attempt.limits_sha256 != artifact_sha256(limits)
            or VisualEvaluationRefs.model_validate(
                load_json_object(attempt.refs_json)
            )
            != refs
            or tuple(
                VisualStageRouting.model_validate(item)
                for item in json.loads(attempt.routing_json)
            )
            != routing
            or VisualEvaluationLimits.model_validate(
                load_json_object(attempt.limits_json)
            )
            != limits
        ):
            raise ValueError("Cached Phase 5 attempt provenance changed")
        summary_row = (
            self.db.query(CandidateVisualSummaryRecord)
            .filter(
                CandidateVisualSummaryRecord.visual_attempt_id == attempt.id
            )
            .first()
        )
        bundle_row = (
            self.db.query(CandidateVisualEvidenceBundleRecord)
            .filter(
                CandidateVisualEvidenceBundleRecord.visual_attempt_id
                == attempt.id
            )
            .first()
        )
        gate_row = (
            self.db.query(CandidateVisualHardGateResultRecord)
            .filter(
                CandidateVisualHardGateResultRecord.visual_attempt_id
                == attempt.id
            )
            .first()
        )
        baseline_row = (
            self.db.query(CandidateBaselineComparisonRecord)
            .filter(
                CandidateBaselineComparisonRecord.visual_attempt_id
                == attempt.id
            )
            .first()
        )
        if not all((summary_row, bundle_row, gate_row, baseline_row)):
            raise ValueError("Partial Phase 5 cache fails closed")
        bundle = _artifact_payload(bundle_row, VisualEvidenceBundle)
        hard_gate = _artifact_payload(gate_row, VisualHardGateReport)
        baseline = _artifact_payload(
            baseline_row,
            CandidateBaselineComparison,
        )
        summary = _artifact_payload(summary_row, VisualEvaluationSummary)
        if (
            bundle != expected_bundle
            or hard_gate != expected_hard_gate
            or summary.refs != refs
            or summary.evidence_bundle_sha256 != bundle_row.artifact_sha256
            or summary.hard_gate_sha256 != gate_row.artifact_sha256
            or summary.baseline_comparison_sha256
            != baseline_row.artifact_sha256
        ):
            raise ValueError("Cached Phase 5 artifacts failed revalidation")

        scorecard_rows = (
            self.db.query(CandidateVisualScorecardRecord)
            .filter(
                CandidateVisualScorecardRecord.visual_attempt_id == attempt.id,
                CandidateVisualScorecardRecord.group_index.is_(None),
            )
            .all()
        )
        critic_row = next(
            (row for row in scorecard_rows if row.actor == "critic"),
            None,
        )
        critic = (
            _artifact_payload(critic_row, VisualScorecard)
            if critic_row is not None
            else None
        )
        reviewer_rows = (
            self.db.query(CandidateVisualReviewerDecisionRecord)
            .filter(
                CandidateVisualReviewerDecisionRecord.visual_attempt_id
                == attempt.id,
                CandidateVisualReviewerDecisionRecord.cache_key.like(
                    "%aggregate%"
                ),
            )
            .all()
        )
        # Cache keys are hashes in production; fall back to the final row,
        # because aggregate is always inserted after partial decisions.
        if not reviewer_rows:
            reviewer_rows = (
                self.db.query(CandidateVisualReviewerDecisionRecord)
                .filter(
                    CandidateVisualReviewerDecisionRecord.visual_attempt_id
                    == attempt.id
                )
                .order_by(CandidateVisualReviewerDecisionRecord.id)
                .all()
            )
        reviewer = (
            _artifact_payload(reviewer_rows[-1], VisualReviewerDecision)
            if reviewer_rows
            else None
        )
        if (
            summary.critic_scorecard_sha256
            != (artifact_sha256(critic) if critic else None)
            or summary.reviewer_decision_sha256
            != (artifact_sha256(reviewer) if reviewer else None)
        ):
            raise ValueError("Cached score/review references are inconsistent")
        plan_row = (
            self.db.query(CandidateRefinementPlanRecord)
            .filter(
                CandidateRefinementPlanRecord.visual_attempt_id == attempt.id
            )
            .first()
        )
        generation_row = (
            self.db.query(CandidateRefinementGenerationRecord)
            .filter(
                CandidateRefinementGenerationRecord.visual_attempt_id
                == attempt.id
            )
            .first()
        )
        plan = (
            _artifact_payload(plan_row, RefinementPlan)
            if plan_row is not None
            else None
        )
        generation = (
            _artifact_payload(generation_row, RefinementGeneration)
            if generation_row is not None
            else None
        )
        refinement_output = None
        technical_repair_output = None
        if generation_row is not None:
            refinement_output = RefinementOutput.model_validate(
                load_json_object(generation_row.refinement_output_json)
            )
            if (
                artifact_sha256(refinement_output)
                != generation_row.refinement_output_sha256
                or artifact_sha256(refinement_output)
                != generation.output_sha256
            ):
                raise ValueError("Cached refinement output is corrupt")
            if generation.technical_repair_count:
                if not generation_row.technical_repair_output_json:
                    raise ValueError("Cached technical repair output is missing")
                technical_repair_output = RefinementOutput.model_validate(
                    load_json_object(
                        generation_row.technical_repair_output_json
                    )
                )
                if artifact_sha256(technical_repair_output) != (
                    generation_row.technical_repair_output_sha256
                ):
                    raise ValueError(
                        "Cached technical repair output is corrupt"
                    )
        if (
            summary.refinement_plan_sha256
            != (artifact_sha256(plan) if plan else None)
            or summary.refinement_generation_sha256
            != (artifact_sha256(generation) if generation else None)
        ):
            raise ValueError("Cached refinement references are inconsistent")
        return CachedVisualEvaluation(
            attempt=attempt,
            bundle=bundle,
            hard_gate=hard_gate,
            critic=critic,
            reviewer=reviewer,
            baseline=baseline,
            plan=plan,
            generation=generation,
            refinement_output=refinement_output,
            technical_repair_output=technical_repair_output,
            summary=summary,
            summary_row=summary_row,
        )

    def persist_terminal(
        self,
        *,
        req: Request,
        refs: VisualEvaluationRefs,
        subject: str,
        evaluation_key: str,
        routing: tuple[VisualStageRouting, ...],
        limits: VisualEvaluationLimits,
        score_bands: ScoreBandPolicy,
        acceptance: VisualAcceptancePolicy,
        bundle: VisualEvidenceBundle,
        hard_gate: VisualHardGateReport,
        critic_partials: tuple[VisualScorecard, ...],
        critic: VisualScorecard | None,
        reviewer_partials: tuple[VisualReviewerDecision, ...],
        reviewer: VisualReviewerDecision | None,
        baseline: CandidateBaselineComparison,
        plan: RefinementPlan | None,
        generation: RefinementGeneration | None,
        metrics: tuple[VisualCallMetrics, ...],
        summary: VisualEvaluationSummary,
        refinement_output: RefinementOutput | None = None,
        technical_repair_output: RefinementOutput | None = None,
        parent_attempt_id: int | None = None,
    ) -> tuple[CandidateVisualSummaryRecord, str]:
        if (
            req.id != refs.request_id
            or bundle.refs != refs
            or hard_gate.refs != refs
            or summary.refs != refs
            or summary.subject != subject
        ):
            raise ValueError("Phase 5 terminal references are inconsistent")
        attempt_uuid = summary.attempt_uuid or str(uuid.uuid4())
        attempt = CandidateVisualEvaluationAttemptRecord(
            attempt_uuid=attempt_uuid,
            request_id=req.id,
            candidate_revision_id=refs.candidate_revision_id,
            runtime_summary_id=refs.runtime_summary_id,
            parent_attempt_id=parent_attempt_id,
            subject=subject,
            evaluation_cache_key=evaluation_key,
            refs_json=canonical_json(refs.model_dump(mode="json")),
            refs_sha256=artifact_sha256(refs),
            routing_json=canonical_json(
                [item.model_dump(mode="json") for item in routing]
            ),
            routing_sha256=artifact_sha256(routing),
            limits_json=canonical_json(limits.model_dump(mode="json")),
            limits_sha256=artifact_sha256(limits),
        )
        self.db.add(attempt)
        self.db.flush()

        def add_artifact(model, artifact, cache_key: str, **values):
            row = model(
                request_id=req.id,
                candidate_revision_id=refs.candidate_revision_id,
                visual_attempt_id=attempt.id,
                cache_key=cache_key,
                artifact_json=canonical_json(
                    artifact.model_dump(mode="json")
                ),
                artifact_sha256=artifact_sha256(artifact),
                **values,
            )
            self.db.add(row)
            self.db.flush()
            return row

        bundle_row = add_artifact(
            CandidateVisualEvidenceBundleRecord,
            bundle,
            bundle.cache_key,
            grouping_manifest_sha256=artifact_sha256(
                bundle.grouping_manifest
            ),
            screenshot_set_sha256=bundle.screenshot_set_sha256,
        )
        gate_row = add_artifact(
            CandidateVisualHardGateResultRecord,
            hard_gate,
            hard_gate.cache_key,
            passed=hard_gate.passed,
        )
        critic_rows = []
        critic_metrics = [item for item in metrics if item.stage == "critic"]
        critic_metrics_for_artifacts = critic_metrics[
            -len(critic_partials):
        ] if critic_partials else []
        for index, artifact in enumerate(critic_partials):
            metric = critic_metrics_for_artifacts[index]
            critic_rows.append(
                add_artifact(
                    CandidateVisualScorecardRecord,
                    artifact,
                    f"{evaluation_key}:critic:{index}",
                    actor="critic",
                    subject=subject,
                    group_index=index,
                    effective_model=metric.model,
                    provider=metric.provider,
                    model_family=metric.family,
                    model_capability=metric.capability,
                    prompt_revision=metric.prompt_revision,
                    parameters_json=canonical_json(
                        {
                            "temperature": metric.temperature,
                            "max_tokens": metric.max_tokens,
                        }
                    ),
                    score_band_policy_revision=score_bands.revision,
                    prompt_tokens=metric.prompt_tokens,
                    completion_tokens=metric.completion_tokens,
                    total_tokens=metric.total_tokens,
                    cost_usd=metric.cost_usd,
                    latency_ms=metric.latency_ms,
                )
            )
        critic_row = None
        if critic is not None:
            metric = critic_metrics[0] if critic_metrics else None
            critic_row = add_artifact(
                CandidateVisualScorecardRecord,
                critic,
                f"{evaluation_key}:critic:aggregate",
                actor="critic",
                subject=subject,
                group_index=None,
                effective_model=(
                    metric.model if metric else routing[0].capability.model
                ),
                provider=(
                    metric.provider if metric else routing[0].capability.provider
                ),
                model_family=routing[0].capability.family,
                model_capability=routing[0].capability.capability,
                prompt_revision=routing[0].prompt_revision,
                parameters_json=canonical_json(
                    {
                        "temperature": routing[0].temperature,
                        "max_tokens": routing[0].max_tokens,
                        "aggregation": "deterministic_weighted_by_image_count",
                    }
                ),
                score_band_policy_revision=score_bands.revision,
                prompt_tokens=sum(item.prompt_tokens for item in critic_metrics),
                completion_tokens=sum(
                    item.completion_tokens for item in critic_metrics
                ),
                total_tokens=sum(item.total_tokens for item in critic_metrics),
                cost_usd=sum(item.cost_usd for item in critic_metrics),
                latency_ms=sum(item.latency_ms for item in critic_metrics),
            )
        reviewer_metrics = [
            item for item in metrics if item.stage == "reviewer"
        ]
        reviewer_metrics_for_artifacts = reviewer_metrics[
            -len(reviewer_partials):
        ] if reviewer_partials else []
        for index, artifact in enumerate(reviewer_partials):
            metric = reviewer_metrics_for_artifacts[index]
            add_artifact(
                CandidateVisualReviewerDecisionRecord,
                artifact,
                f"{evaluation_key}:reviewer:{index}",
                recommendation=artifact.recommendation,
                effective_model=metric.model,
                provider=metric.provider,
                model_family=metric.family,
                model_capability=metric.capability,
                prompt_revision=metric.prompt_revision,
                parameters_json=canonical_json(
                    {
                        "temperature": metric.temperature,
                        "max_tokens": metric.max_tokens,
                    }
                ),
                prompt_tokens=metric.prompt_tokens,
                completion_tokens=metric.completion_tokens,
                total_tokens=metric.total_tokens,
                cost_usd=metric.cost_usd,
                latency_ms=metric.latency_ms,
            )
        reviewer_row = None
        if reviewer is not None:
            metric = reviewer_metrics[0] if reviewer_metrics else None
            reviewer_row = add_artifact(
                CandidateVisualReviewerDecisionRecord,
                reviewer,
                f"{evaluation_key}:reviewer:aggregate",
                recommendation=reviewer.recommendation,
                effective_model=(
                    metric.model if metric else routing[1].capability.model
                ),
                provider=(
                    metric.provider if metric else routing[1].capability.provider
                ),
                model_family=routing[1].capability.family,
                model_capability=routing[1].capability.capability,
                prompt_revision=routing[1].prompt_revision,
                parameters_json=canonical_json(
                    {
                        "temperature": routing[1].temperature,
                        "max_tokens": routing[1].max_tokens,
                        "aggregation": "deterministic_weighted_by_image_count",
                    }
                ),
                prompt_tokens=sum(
                    item.prompt_tokens for item in reviewer_metrics
                ),
                completion_tokens=sum(
                    item.completion_tokens for item in reviewer_metrics
                ),
                total_tokens=sum(
                    item.total_tokens for item in reviewer_metrics
                ),
                cost_usd=sum(item.cost_usd for item in reviewer_metrics),
                latency_ms=sum(item.latency_ms for item in reviewer_metrics),
            )
        findings = []
        if critic:
            findings.extend(critic.findings)
        if reviewer:
            findings.extend(reviewer.blocking_findings)
        for finding in findings:
            self.db.add(
                CandidateVisualFindingRecord(
                    request_id=req.id,
                    candidate_revision_id=refs.candidate_revision_id,
                    visual_attempt_id=attempt.id,
                    finding_id=finding.finding_id,
                    source=finding.source,
                    severity=finding.severity,
                    finding_json=canonical_json(
                        finding.model_dump(mode="json")
                    ),
                    finding_sha256=artifact_sha256(finding),
                )
            )
        baseline_row = add_artifact(
            CandidateBaselineComparisonRecord,
            baseline,
            f"{evaluation_key}:baseline",
            mode=baseline.mode,
            baseline_identity_sha256=baseline.label_b_identity_sha256,
        )
        plan_row = (
            add_artifact(
                CandidateRefinementPlanRecord,
                plan,
                plan.cache_key,
                repairability=plan.repairability,
            )
            if plan
            else None
        )
        generation_row = None
        if generation:
            if (
                refinement_output is None
                or artifact_sha256(refinement_output)
                != generation.output_sha256
                or bool(technical_repair_output)
                != bool(generation.technical_repair_count)
            ):
                raise ValueError(
                    "Refinement generation outputs are incomplete"
                )
            refinement_metrics = [
                item for item in metrics if item.stage == "refinement"
            ]
            repair_metrics = [
                item for item in metrics if item.stage == "technical_repair"
            ]
            generation_row = add_artifact(
                CandidateRefinementGenerationRecord,
                generation,
                f"{evaluation_key}:refinement_generation",
                original_candidate_revision_id=(
                    generation.original_candidate_revision_id
                ),
                derived_candidate_revision_id=(
                    generation.derived_candidate_revision_id
                ),
                refinement_model=routing[2].capability.model,
                refinement_output_json=canonical_json(
                    refinement_output.model_dump(mode="json")
                ),
                refinement_output_sha256=artifact_sha256(
                    refinement_output
                ),
                technical_repair_model=(
                    routing[3].capability.model if repair_metrics else None
                ),
                technical_repair_output_json=(
                    canonical_json(
                        technical_repair_output.model_dump(mode="json")
                    )
                    if technical_repair_output
                    else None
                ),
                technical_repair_output_sha256=(
                    artifact_sha256(technical_repair_output)
                    if technical_repair_output
                    else None
                ),
                refinement_call_count=len(refinement_metrics),
                technical_repair_call_count=len(repair_metrics),
                prompt_tokens=sum(item.prompt_tokens for item in metrics),
                completion_tokens=sum(
                    item.completion_tokens for item in metrics
                ),
                total_tokens=sum(item.total_tokens for item in metrics),
                cost_usd=sum(item.cost_usd for item in metrics),
                latency_ms=sum(item.latency_ms for item in metrics),
            )
        if (
            summary.evidence_bundle_sha256 != bundle_row.artifact_sha256
            or summary.hard_gate_sha256 != gate_row.artifact_sha256
            or summary.critic_scorecard_sha256
            != (critic_row.artifact_sha256 if critic_row else None)
            or summary.reviewer_decision_sha256
            != (reviewer_row.artifact_sha256 if reviewer_row else None)
            or summary.baseline_comparison_sha256
            != baseline_row.artifact_sha256
            or summary.refinement_plan_sha256
            != (plan_row.artifact_sha256 if plan_row else None)
            or summary.refinement_generation_sha256
            != (
                generation_row.artifact_sha256 if generation_row else None
            )
        ):
            raise ValueError("Phase 5 terminal summary hashes do not close")
        summary_row = add_artifact(
            CandidateVisualSummaryRecord,
            summary,
            evaluation_key,
            status=summary.status,
            repairability=summary.repairability,
            acceptance_policy_revision=acceptance.revision,
            score_band_policy_revision=score_bands.revision,
            deterministic_acceptance_json=canonical_json(
                (
                    summary.acceptance_computation.model_dump(mode="json")
                    if summary.acceptance_computation
                    else {}
                )
            ),
            provider_call_count=summary.provider_call_count,
            prompt_tokens=summary.prompt_tokens,
            completion_tokens=summary.completion_tokens,
            total_tokens=summary.total_tokens,
            cost_usd=summary.cost_usd,
            latency_ms=summary.latency_ms,
        )
        bundle_json: dict[str, Any] = {}
        if req.generated_pages:
            try:
                loaded = json.loads(req.generated_pages)
                if isinstance(loaded, dict):
                    bundle_json = loaded
            except Exception:
                pass
        preview = dict(bundle_json.get("preview_contract") or {})
        preview.update(
            {
                "status": summary.status,
                "visual_evaluation_summary": {
                    "id": summary_row.id,
                    "attempt_uuid": attempt.attempt_uuid,
                    "sha256": summary_row.artifact_sha256,
                    "repairability": summary.repairability,
                },
            }
        )
        bundle_json["preview_contract"] = preview
        req.generated_pages = json.dumps(bundle_json, ensure_ascii=False)
        self.db.flush()
        return summary_row, attempt.attempt_uuid


__all__ = [
    "CachedVisualEvaluation",
    "VisualEvaluationRepository",
]
