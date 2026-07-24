"""Append-only persistence and strict terminal cache for Phase 6A."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.application.appspec.repository import load_json_object
from app.application.appspec.source import canonical_json
from app.application.candidate_generation.cache import canonical_sha256
from app.domain.models import (
    CandidateRevisionRecord,
    CandidateValidationSummaryRecord,
    CandidateVisualSummaryRecord,
    CandidateEffectiveTierSummaryRecord,
    CandidateLowerTierPreservationAuditRecord,
    CandidateTierExtensionManifestRecord,
    CandidateTierGenerationResultRecord,
    CandidateTierOrchestrationAttemptRecord,
    CandidateTierValidationResultRecord,
    CandidateTierVisualOutcomeRecord,
)
from app.domain.schemas.tier_orchestration import (
    Tier2Budget,
    Tier2EffectiveSummary,
    Tier2ExtensionContracts,
    Tier2PreservationManifest,
    Tier2Telemetry,
)


@dataclass(frozen=True)
class Tier2Terminal:
    row: CandidateEffectiveTierSummaryRecord
    summary: Tier2EffectiveSummary
    result: dict[str, Any]


class Tier2OrchestrationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def find_terminal(
        self,
        *,
        request_id: int,
        resume_identity_sha256: str,
    ) -> Tier2Terminal | None:
        attempt = (
            self.db.query(CandidateTierOrchestrationAttemptRecord)
            .filter(
                CandidateTierOrchestrationAttemptRecord.request_id
                == request_id,
                CandidateTierOrchestrationAttemptRecord.resume_identity_sha256
                == resume_identity_sha256,
            )
            .first()
        )
        if attempt is None:
            return None
        if (
            canonical_sha256(load_json_object(attempt.upstream_refs_json))
            != attempt.upstream_refs_sha256
            or canonical_sha256(
                Tier2Budget.model_validate(
                    load_json_object(attempt.budget_json)
                )
            )
            != attempt.budget_sha256
        ):
            raise ValueError("Cached Tier 2 attempt provenance is corrupt")
        row = (
            self.db.query(CandidateEffectiveTierSummaryRecord)
            .filter(
                CandidateEffectiveTierSummaryRecord.orchestration_attempt_id
                == attempt.id
            )
            .first()
        )
        if row is None:
            return None
        extension = self.db.get(
            CandidateTierExtensionManifestRecord,
            row.tier_extension_manifest_id,
        )
        audit = self.db.get(
            CandidateLowerTierPreservationAuditRecord,
            row.preservation_audit_id,
        )
        generation = self.db.get(
            CandidateTierGenerationResultRecord,
            row.tier_generation_result_id,
        )
        validation = self.db.get(
            CandidateTierValidationResultRecord,
            row.tier_validation_result_id,
        )
        visual = self.db.get(
            CandidateTierVisualOutcomeRecord,
            row.tier_visual_outcome_id,
        )
        if any(
            item is None
            for item in (
                extension,
                audit,
                generation,
                validation,
                visual,
            )
        ):
            raise ValueError("Cached Tier 2 terminal chain is incomplete")
        chain = (extension, audit, generation, validation, visual, row)
        for item in chain:
            if (
                item.request_id != request_id
                or item.orchestration_attempt_id != attempt.id
                or item.accepted_tier_1_revision_id
                != attempt.accepted_tier_1_revision_id
                or item.accepted_tier_1_visual_summary_id
                != attempt.accepted_tier_1_visual_summary_id
                or item.target_tier != 2
                or item.tier_closure_sha256
                != attempt.tier_closure_sha256
                or item.delta_sha256 != attempt.delta_sha256
                or item.generation_policy_revision
                != attempt.generation_policy_revision
            ):
                raise ValueError("Cached Tier 2 lineage is inconsistent")
        extension_contracts = Tier2ExtensionContracts.model_validate(
            load_json_object(extension.manifest_json)
        )
        preservation = Tier2PreservationManifest.model_validate(
            load_json_object(audit.audit_json)
        )
        generation_payload = load_json_object(generation.result_json)
        validation_payload = load_json_object(validation.result_json)
        visual_payload = load_json_object(visual.outcome_json)
        preservation_payload = preservation.model_dump(
            mode="json",
            exclude={"manifest_sha256"},
        )
        if (
            canonical_sha256(extension_contracts)
            != extension.manifest_sha256
            or canonical_sha256(extension_contracts.page_purpose)
            != extension_contracts.page_purpose_sha256
            or canonical_sha256(extension_contracts.business_components)
            != extension_contracts.business_components_sha256
            or canonical_sha256(extension_contracts.content_data)
            != extension_contracts.content_data_sha256
            or canonical_sha256(extension_contracts.interactions)
            != extension_contracts.interactions_sha256
            or canonical_sha256(extension_contracts.dependency_graph)
            != extension_contracts.dependency_graph_sha256
            or canonical_sha256(preservation) != audit.audit_sha256
            or canonical_sha256(preservation_payload)
            != preservation.manifest_sha256
            or canonical_sha256(generation_payload)
            != generation.result_sha256
            or canonical_sha256(validation_payload)
            != validation.result_sha256
            or canonical_sha256(visual_payload) != visual.outcome_sha256
            or generation.passed
            != bool(generation_payload.get("passed"))
            or validation.passed
            != bool(validation_payload.get("passed"))
            or visual.passed != bool(visual_payload.get("passed"))
        ):
            raise ValueError("Cached Tier 2 artifact hash is corrupt")
        summary = Tier2EffectiveSummary.model_validate(
            load_json_object(row.summary_json)
        )
        if (
            canonical_sha256(summary) != row.summary_sha256
            or summary.orchestration_attempt_id != attempt.id
            or summary.request_id != request_id
            or summary.tier_2_extension_manifest_id != extension.id
            or summary.preservation_audit_id != audit.id
            or summary.tier_generation_result_id != generation.id
            or summary.tier_validation_result_id != validation.id
            or summary.tier_visual_outcome_id != visual.id
            or row.derived_candidate_revision_id
            != summary.derived_candidate_revision_id
            or row.phase4_validation_summary_id
            != summary.phase4_validation_summary_id
            or row.phase5_visual_summary_id
            != summary.phase5_visual_summary_id
        ):
            raise ValueError("Cached Tier 2 effective summary is corrupt")
        if summary.derived_candidate_revision_id is not None:
            candidate = self.db.get(
                CandidateRevisionRecord,
                summary.derived_candidate_revision_id,
            )
            if (
                candidate is None
                or candidate.request_id != request_id
                or candidate.target_tier != 2
                or candidate.status != "candidate_build_pending"
                or generation.derived_candidate_revision_id != candidate.id
            ):
                raise ValueError("Cached Tier 2 candidate reference is invalid")
        if summary.phase4_validation_summary_id is not None:
            phase4 = self.db.get(
                CandidateValidationSummaryRecord,
                summary.phase4_validation_summary_id,
            )
            if (
                phase4 is None
                or phase4.request_id != request_id
                or phase4.candidate_revision_id
                != summary.derived_candidate_revision_id
                or validation.phase4_validation_summary_id != phase4.id
            ):
                raise ValueError("Cached Tier 2 Phase 4 reference is invalid")
        if summary.phase5_visual_summary_id is not None:
            phase5 = self.db.get(
                CandidateVisualSummaryRecord,
                summary.phase5_visual_summary_id,
            )
            if (
                phase5 is None
                or phase5.request_id != request_id
                or phase5.candidate_revision_id
                != summary.derived_candidate_revision_id
                or visual.phase5_visual_summary_id != phase5.id
            ):
                raise ValueError("Cached Tier 2 Phase 5 reference is invalid")
        result = {
            "preview_contract": {
                "status": summary.status,
                "target_tier": 2,
                "effective_tier_summary": {
                    "id": row.id,
                    "sha256": row.summary_sha256,
                    **summary.model_dump(mode="json"),
                },
                "tier_2_cache_hit": True,
            }
        }
        return Tier2Terminal(row=row, summary=summary, result=result)

    def get_or_create_attempt(
        self,
        *,
        request_id: int,
        accepted_tier_1_revision_id: int,
        accepted_tier_1_visual_summary_id: int,
        accepted_manifest_sha256: str,
        tier_closure_sha256: str,
        delta_sha256: str,
        generation_policy_revision: str,
        resume_identity_sha256: str,
        upstream_refs: dict[str, Any],
        budget: Tier2Budget,
    ) -> CandidateTierOrchestrationAttemptRecord:
        existing = (
            self.db.query(CandidateTierOrchestrationAttemptRecord)
            .filter(
                CandidateTierOrchestrationAttemptRecord.request_id
                == request_id,
                CandidateTierOrchestrationAttemptRecord.resume_identity_sha256
                == resume_identity_sha256,
            )
            .first()
        )
        upstream_json = canonical_json(upstream_refs)
        budget_json = canonical_json(budget.model_dump(mode="json"))
        if existing is not None:
            if (
                existing.accepted_tier_1_revision_id
                != accepted_tier_1_revision_id
                or existing.accepted_tier_1_visual_summary_id
                != accepted_tier_1_visual_summary_id
                or existing.accepted_manifest_sha256
                != accepted_manifest_sha256
                or existing.tier_closure_sha256 != tier_closure_sha256
                or existing.delta_sha256 != delta_sha256
                or existing.generation_policy_revision
                != generation_policy_revision
                or existing.upstream_refs_json != upstream_json
                or existing.budget_json != budget_json
            ):
                raise ValueError("Tier 2 resume identity has stale provenance")
            return existing
        row = CandidateTierOrchestrationAttemptRecord(
            attempt_uuid=str(uuid.uuid4()),
            request_id=request_id,
            accepted_tier_1_revision_id=accepted_tier_1_revision_id,
            accepted_tier_1_visual_summary_id=(
                accepted_tier_1_visual_summary_id
            ),
            target_tier=2,
            tier_closure_sha256=tier_closure_sha256,
            delta_sha256=delta_sha256,
            generation_policy_revision=generation_policy_revision,
            resume_identity_sha256=resume_identity_sha256,
            accepted_manifest_sha256=accepted_manifest_sha256,
            upstream_refs_json=upstream_json,
            upstream_refs_sha256=canonical_sha256(upstream_refs),
            budget_json=budget_json,
            budget_sha256=canonical_sha256(budget),
            staging_workspace_relpath=None,
            status="started",
        )
        self.db.add(row)
        self.db.flush()
        return row

    def get_or_create_extension(
        self,
        *,
        attempt: CandidateTierOrchestrationAttemptRecord,
        contracts: Tier2ExtensionContracts,
    ) -> CandidateTierExtensionManifestRecord:
        payload = contracts.model_dump(mode="json")
        payload_json = canonical_json(payload)
        digest = canonical_sha256(payload)
        existing = (
            self.db.query(CandidateTierExtensionManifestRecord)
            .filter(
                CandidateTierExtensionManifestRecord.orchestration_attempt_id
                == attempt.id
            )
            .first()
        )
        if existing is not None:
            if (
                existing.manifest_json != payload_json
                or existing.manifest_sha256 != digest
            ):
                raise ValueError(
                    "Tier 2 extension cache does not exactly match"
                )
            return existing
        row = CandidateTierExtensionManifestRecord(
            request_id=attempt.request_id,
            accepted_tier_1_revision_id=(
                attempt.accepted_tier_1_revision_id
            ),
            accepted_tier_1_visual_summary_id=(
                attempt.accepted_tier_1_visual_summary_id
            ),
            target_tier=2,
            tier_closure_sha256=attempt.tier_closure_sha256,
            delta_sha256=attempt.delta_sha256,
            generation_policy_revision=attempt.generation_policy_revision,
            orchestration_attempt_id=attempt.id,
            manifest_json=payload_json,
            manifest_sha256=digest,
            page_purpose_sha256=contracts.page_purpose_sha256,
            business_component_plan_sha256=(
                contracts.business_components_sha256
            ),
            content_data_plan_sha256=contracts.content_data_sha256,
            interaction_contract_sha256=contracts.interactions_sha256,
            dependency_graph_sha256=contracts.dependency_graph_sha256,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def persist_terminal(
        self,
        *,
        attempt: CandidateTierOrchestrationAttemptRecord,
        extension: CandidateTierExtensionManifestRecord,
        preservation: Tier2PreservationManifest,
        generation_payload: dict[str, Any],
        generation_passed: bool,
        validation_payload: dict[str, Any],
        validation_passed: bool,
        visual_payload: dict[str, Any],
        visual_passed: bool,
        derived_candidate_revision_id: int | None,
        phase4_validation_summary_id: int | None,
        phase5_visual_summary_id: int | None,
        baseline_comparison_id: int | None,
        status: str,
        failure_stage: str | None,
        fallback_reason: str | None,
        telemetry: Tier2Telemetry,
    ) -> Tier2Terminal:
        if (
            self.db.query(CandidateEffectiveTierSummaryRecord)
            .filter(
                CandidateEffectiveTierSummaryRecord.orchestration_attempt_id
                == attempt.id
            )
            .first()
            is not None
        ):
            raise ValueError("Tier 2 attempt is already terminal")
        common = {
            "request_id": attempt.request_id,
            "accepted_tier_1_revision_id": (
                attempt.accepted_tier_1_revision_id
            ),
            "accepted_tier_1_visual_summary_id": (
                attempt.accepted_tier_1_visual_summary_id
            ),
            "target_tier": 2,
            "tier_closure_sha256": attempt.tier_closure_sha256,
            "delta_sha256": attempt.delta_sha256,
            "generation_policy_revision": (
                attempt.generation_policy_revision
            ),
            "orchestration_attempt_id": attempt.id,
        }
        audit_json = canonical_json(preservation.model_dump(mode="json"))
        audit = CandidateLowerTierPreservationAuditRecord(
            **common,
            tier_extension_manifest_id=extension.id,
            audit_json=audit_json,
            audit_sha256=canonical_sha256(preservation),
            passed=True,
        )
        self.db.add(audit)
        self.db.flush()

        generation_json = canonical_json(generation_payload)
        generation = CandidateTierGenerationResultRecord(
            **common,
            preservation_audit_id=audit.id,
            derived_candidate_revision_id=derived_candidate_revision_id,
            result_json=generation_json,
            result_sha256=canonical_sha256(generation_payload),
            passed=generation_passed,
            provider_call_count=telemetry.generation_call_count,
            output_tokens=int(generation_payload.get("output_tokens") or 0),
            cost_usd=float(generation_payload.get("cost_usd") or 0.0),
            latency_ms=int(generation_payload.get("latency_ms") or 0),
        )
        self.db.add(generation)
        self.db.flush()

        validation = CandidateTierValidationResultRecord(
            **common,
            preservation_audit_id=audit.id,
            derived_candidate_revision_id=derived_candidate_revision_id,
            phase4_validation_summary_id=phase4_validation_summary_id,
            result_json=canonical_json(validation_payload),
            result_sha256=canonical_sha256(validation_payload),
            passed=validation_passed,
        )
        self.db.add(validation)
        self.db.flush()

        visual = CandidateTierVisualOutcomeRecord(
            **common,
            preservation_audit_id=audit.id,
            derived_candidate_revision_id=derived_candidate_revision_id,
            phase4_validation_summary_id=phase4_validation_summary_id,
            phase5_visual_summary_id=phase5_visual_summary_id,
            baseline_comparison_id=baseline_comparison_id,
            outcome_json=canonical_json(visual_payload),
            outcome_sha256=canonical_sha256(visual_payload),
            passed=visual_passed,
        )
        self.db.add(visual)
        self.db.flush()

        accepted = status == "tier_2_accepted"
        summary = Tier2EffectiveSummary(
            status=status,
            request_id=attempt.request_id,
            accepted_tier_1_revision_id=(
                attempt.accepted_tier_1_revision_id
            ),
            accepted_tier_1_visual_summary_id=(
                attempt.accepted_tier_1_visual_summary_id
            ),
            orchestration_attempt_id=attempt.id,
            tier_2_extension_manifest_id=extension.id,
            preservation_audit_id=audit.id,
            tier_generation_result_id=generation.id,
            tier_validation_result_id=validation.id,
            tier_visual_outcome_id=visual.id,
            derived_candidate_revision_id=derived_candidate_revision_id,
            phase4_validation_summary_id=phase4_validation_summary_id,
            phase5_visual_summary_id=phase5_visual_summary_id,
            highest_accepted_tier=2 if accepted else 1,
            last_accepted_candidate_revision_id=(
                derived_candidate_revision_id
                if accepted and derived_candidate_revision_id
                else attempt.accepted_tier_1_revision_id
            ),
            failure_stage=failure_stage,
            fallback_reason=fallback_reason,
            tier_2_closure_sha256=attempt.tier_closure_sha256,
            delta_sha256=attempt.delta_sha256,
            preservation_audit_sha256=canonical_sha256(preservation),
            generation_policy_revision=(
                attempt.generation_policy_revision
            ),
            telemetry=telemetry,
            phase4_reused=phase4_validation_summary_id is not None,
            phase5_reused=phase5_visual_summary_id is not None,
        )
        row = CandidateEffectiveTierSummaryRecord(
            **common,
            tier_extension_manifest_id=extension.id,
            preservation_audit_id=audit.id,
            tier_generation_result_id=generation.id,
            tier_validation_result_id=validation.id,
            tier_visual_outcome_id=visual.id,
            derived_candidate_revision_id=derived_candidate_revision_id,
            phase4_validation_summary_id=phase4_validation_summary_id,
            phase5_visual_summary_id=phase5_visual_summary_id,
            status=status,
            highest_accepted_tier=summary.highest_accepted_tier,
            last_accepted_candidate_revision_id=(
                summary.last_accepted_candidate_revision_id
            ),
            summary_json=canonical_json(summary.model_dump(mode="json")),
            summary_sha256=canonical_sha256(summary),
        )
        self.db.add(row)
        self.db.flush()
        result = {
            "preview_contract": {
                "status": summary.status,
                "target_tier": 2,
                "effective_tier_summary": {
                    "id": row.id,
                    "sha256": row.summary_sha256,
                    **summary.model_dump(mode="json"),
                },
                "tier_2_generation_result": generation_payload,
                "tier_2_validation_result": validation_payload,
                "tier_2_visual_outcome": visual_payload,
                "tier_2_cache_hit": False,
            }
        }
        return Tier2Terminal(row=row, summary=summary, result=result)


__all__ = [
    "Tier2OrchestrationRepository",
    "Tier2Terminal",
]
