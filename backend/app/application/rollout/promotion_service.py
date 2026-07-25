"""Phase 7C allowlist promotion and rollback control plane."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, load_only

from app.application.preview_app.workspace import _legacy_get_dist_dir
from app.application.rollout.apply_eligibility import (
    compute_apply_eligibility,
    latest_decision_status,
)
from app.application.rollout.apply_transaction import (
    PointerApplyError,
    apply_pointer_swap_transaction,
)
from app.application.rollout.audit import append_audit_event
from app.application.rollout.authorization import (
    evaluate_separation_of_duties,
    reject_client_supplied_roles,
    require_permission,
)
from app.application.rollout.breaker_metrics import append_metric_sample
from app.application.rollout.health_precheck import verify_rollback_target
from app.application.rollout.pointer import resolve_serving_pointer
from app.application.rollout.repository import RolloutRepository
from app.application.rollout.shadow_lineage import locate_latest_accepted_lineage
from app.core import config as app_config
from app.domain.models.preview_candidate import CandidateRevisionRecord
from app.domain.models.rollout import (
    PreviewLiveCanaryExecutionRecord,
    PreviewLiveCanaryLifecycleEventRecord,
    PreviewPromotionDecisionRecord,
    PreviewPromotionDecisionStatusEventRecord,
    PreviewServingPointerVersionRecord,
)
from app.domain.models.tier_orchestration import CandidateEffectiveTierSummaryRecord
from app.domain.schemas.promotion import (
    ApplyResultView,
    DecisionApprovalBody,
    DecisionApplyBody,
    DecisionView,
    PromotionRequestBody,
    RollbackRequestBody,
)
from app.domain.schemas.rollout import ServingPointerView, TrustedRolloutActor


class PromotionServiceError(RuntimeError):
    def __init__(self, reason: str, *, stage: str = "promotion") -> None:
        super().__init__(reason)
        self.reason = reason
        self.stage = stage


def _payload_sha(payload: dict[str, Any]) -> str:
    material = {k: v for k, v in payload.items() if k not in {"created_at", "timestamp"}}
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _event_sha(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _primary_role(actor: TrustedRolloutActor) -> str:
    return actor.roles[0]


class PromotionService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._repo = RolloutRepository(db)

    def _flags_ok(self) -> bool:
        s = app_config.settings
        return bool(
            s.V2_PHASE7_ROLLOUT_ENABLED
            and s.V2_PHASE7_PROMOTE_ENABLED
            and s.V2_PHASE7_CONFIG_VALID
        )

    def _require_allowlist_zero_percent(self, request_id: int) -> None:
        s = app_config.settings
        if not self._flags_ok():
            raise PromotionServiceError("flags_off", stage="flags")
        if request_id not in set(s.V2_PHASE7_REQUEST_ALLOWLIST):
            raise PromotionServiceError("not_allowlisted", stage="allowlist")
        if s.V2_PHASE7_ROLLOUT_PERCENT != 0:
            raise PromotionServiceError(
                "rollout_percent_nonzero", stage="allowlist"
            )

    def _verify_canary_evidence(
        self,
        *,
        request_id: int,
        canary_execution_id: int,
        candidate_revision_id: int,
        effective_tier_summary_id: int,
    ) -> None:
        """Server-side canary evidence check — never trusts client hashes."""
        from app.application.rollout.canary_policy import compute_policy_identity

        exec_row = (
            self._db.query(PreviewLiveCanaryExecutionRecord)
            .filter(PreviewLiveCanaryExecutionRecord.id == canary_execution_id)
            .one_or_none()
        )
        if exec_row is None:
            raise PromotionServiceError("canary_execution_not_found", stage="canary")
        if exec_row.result_status != "completed":
            raise PromotionServiceError("canary_not_completed", stage="canary")
        if exec_row.request_id != request_id:
            raise PromotionServiceError("canary_request_mismatch", stage="canary")
        if exec_row.candidate_revision_id != candidate_revision_id:
            raise PromotionServiceError("canary_candidate_mismatch", stage="canary")
        if (
            exec_row.execution_mode != "live"
            or not bool(exec_row.provider_was_live)
            or bool(exec_row.simulation_only)
            or not bool(exec_row.percent_authorization_eligible)
        ):
            raise PromotionServiceError("canary_fixture_not_eligible", stage="canary")
        reviewed = (
            self._db.query(PreviewLiveCanaryLifecycleEventRecord)
            .filter(
                PreviewLiveCanaryLifecycleEventRecord.approval_id == exec_row.approval_id,
                PreviewLiveCanaryLifecycleEventRecord.status == "reviewed_accepted",
            )
            .first()
        )
        if reviewed is None:
            raise PromotionServiceError("canary_not_reviewed", stage="canary")
        identity = compute_policy_identity()
        if exec_row.policy_identity_sha256 != identity.policy_identity_sha256:
            raise PromotionServiceError("canary_policy_stale", stage="canary")
        # effective summary match against accepted lineage when present
        lineage = locate_latest_accepted_lineage(self._db, request_id)
        if lineage is not None and lineage.effective_summary_id is not None:
            if lineage.effective_summary_id != effective_tier_summary_id:
                raise PromotionServiceError(
                    "canary_effective_summary_mismatch", stage="canary"
                )

    def _append_status(
        self,
        *,
        decision_id: int,
        status: str,
        actor_id: str,
        reason: str,
        idempotency_key: str | None = None,
    ) -> PreviewPromotionDecisionStatusEventRecord:
        payload = {
            "decision_id": decision_id,
            "status": status,
            "actor_id": actor_id,
            "reason": reason,
            "idempotency_key": idempotency_key,
        }
        row = PreviewPromotionDecisionStatusEventRecord(
            decision_id=decision_id,
            status=status,
            actor_id=actor_id,
            reason=reason
            if not idempotency_key
            else f"{reason}|idempotency:{idempotency_key}",
            created_at=datetime.utcnow(),
            event_sha256=_event_sha(payload),
        )
        self._db.add(row)
        self._db.flush()
        return row

    def _decision_view(self, decision: PreviewPromotionDecisionRecord) -> DecisionView:
        status = latest_decision_status(self._db, decision.id) or decision.decision_status
        resulting = None
        if status == "applied":
            ptr = (
                self._db.query(PreviewServingPointerVersionRecord)
                .filter(
                    PreviewServingPointerVersionRecord.decision_id == decision.id,
                    PreviewServingPointerVersionRecord.pointer_action.in_(
                        ("promote", "rollback")
                    ),
                )
                .order_by(PreviewServingPointerVersionRecord.pointer_version.desc())
                .first()
            )
            if ptr is not None:
                resulting = int(ptr.pointer_version)
        return DecisionView(
            decision_id=decision.id,
            request_id=decision.request_id,
            decision_type=decision.decision_type,  # type: ignore[arg-type]
            latest_status=status,  # type: ignore[arg-type]
            candidate_revision_id=decision.candidate_revision_id,
            effective_tier_summary_id=decision.effective_tier_summary_id,
            expected_pointer_version=decision.expected_pointer_version,
            target_pointer_version=decision.target_pointer_version,
            resulting_pointer_version=resulting,
            requester_actor_id=decision.actor_id,
            reason=decision.reason,
            ticket_ref=decision.ticket_ref,
            idempotency_key=decision.idempotency_key,
            policy_revision=decision.policy_revision,
            decision_sha256=decision.decision_sha256,
            created_at=decision.requested_at.isoformat()
            if decision.requested_at
            else "",
        )

    def get_decision(
        self, *, actor: TrustedRolloutActor, decision_id: int
    ) -> DecisionView:
        require_permission(actor, "read_diagnostics")
        decision = (
            self._db.query(PreviewPromotionDecisionRecord)
            .filter(PreviewPromotionDecisionRecord.id == decision_id)
            .one_or_none()
        )
        if decision is None:
            raise PromotionServiceError("decision_not_found", stage="lookup")
        return self._decision_view(decision)

    def list_promotions(
        self, *, actor: TrustedRolloutActor, request_id: int
    ) -> list[DecisionView]:
        require_permission(actor, "read_diagnostics")
        rows = (
            self._db.query(PreviewPromotionDecisionRecord)
            .filter(
                PreviewPromotionDecisionRecord.request_id == request_id,
                PreviewPromotionDecisionRecord.decision_type.in_(
                    ("promote", "rollback")
                ),
            )
            .order_by(PreviewPromotionDecisionRecord.id.asc())
            .all()
        )
        return [self._decision_view(r) for r in rows]

    def pointer_history(
        self, *, actor: TrustedRolloutActor, request_id: int
    ) -> list[ServingPointerView]:
        require_permission(actor, "read_diagnostics")
        rows = (
            self._db.query(PreviewServingPointerVersionRecord)
            .filter(PreviewServingPointerVersionRecord.request_id == request_id)
            .order_by(PreviewServingPointerVersionRecord.pointer_version.asc())
            .all()
        )
        out: list[ServingPointerView] = []
        for row in rows:
            kind = row.target_kind
            if row.pointer_action == "rollback":
                kind = "rollback"
            out.append(
                ServingPointerView(
                    request_id=request_id,
                    pointer_version=row.pointer_version,
                    target_kind=kind,  # type: ignore[arg-type]
                    candidate_revision_id=row.candidate_revision_id,
                    legacy_preview_relpath=row.legacy_preview_relpath,
                    effective_tier=row.effective_tier,
                    effective_summary_id=row.effective_summary_id,
                    summary_sha256=row.summary_sha256,
                    candidate_manifest_sha256=row.candidate_manifest_sha256,
                    previous_pointer_version=row.previous_pointer_version,
                    created_at=row.created_at.isoformat() if row.created_at else None,
                    is_current=bool(row.is_current),
                    pointer_action=row.pointer_action,  # type: ignore[arg-type]
                )
            )
        return out

    def request_promotion(
        self,
        *,
        actor: TrustedRolloutActor,
        request_id: int,
        body: PromotionRequestBody,
        client_payload: dict[str, Any] | None = None,
    ) -> DecisionView:
        if client_payload is not None:
            reject_client_supplied_roles(client_payload)
        require_permission(actor, "request_promotion")
        self._require_allowlist_zero_percent(request_id)
        if body.canary_execution_id is not None:
            self._verify_canary_evidence(
                request_id=request_id,
                canary_execution_id=body.canary_execution_id,
                candidate_revision_id=body.candidate_revision_id,
                effective_tier_summary_id=body.effective_tier_summary_id,
            )

        payload_hash = _payload_sha(
            {
                "op": "promotion_request",
                "request_id": request_id,
                "candidate_revision_id": body.candidate_revision_id,
                "effective_tier_summary_id": body.effective_tier_summary_id,
                "expected_pointer_version": body.expected_pointer_version,
                "reason": body.reason,
                "ticket_ref": body.ticket_ref,
                "canary_execution_id": body.canary_execution_id,
            }
        )
        if body.idempotency_key:
            existing = (
                self._db.query(PreviewPromotionDecisionRecord)
                .filter(
                    PreviewPromotionDecisionRecord.request_id == request_id,
                    PreviewPromotionDecisionRecord.idempotency_key
                    == body.idempotency_key,
                    PreviewPromotionDecisionRecord.decision_type == "promote",
                )
                .one_or_none()
            )
            if existing is not None:
                if existing.idempotency_payload_sha256 != payload_hash:
                    raise PromotionServiceError(
                        "idempotency_key_conflict", stage="idempotency"
                    )
                return self._decision_view(existing)

        current = self._repo.get_current_pointer(request_id)
        current_version = None if current is None else int(current.pointer_version)
        if body.expected_pointer_version != current_version:
            raise PromotionServiceError(
                "pointer_version_mismatch", stage="validation"
            )

        lineage = locate_latest_accepted_lineage(self._db, request_id)
        if lineage is None:
            raise PromotionServiceError("lineage_missing", stage="validation")
        if lineage.candidate_revision_id != body.candidate_revision_id:
            raise PromotionServiceError(
                "candidate_not_accepted_lineage", stage="validation"
            )
        if (
            lineage.effective_summary_id is not None
            and lineage.effective_summary_id != body.effective_tier_summary_id
        ):
            raise PromotionServiceError(
                "effective_tier_mismatch", stage="validation"
            )
        if lineage.phase4_status != "candidate_runtime_validated":
            raise PromotionServiceError("phase4_not_validated", stage="validation")
        if lineage.phase5_status != "candidate_visual_accepted":
            raise PromotionServiceError("phase5_not_accepted", stage="validation")

        summary = (
            self._db.query(CandidateEffectiveTierSummaryRecord)
            .options(
                load_only(
                    CandidateEffectiveTierSummaryRecord.id,
                    CandidateEffectiveTierSummaryRecord.request_id,
                    CandidateEffectiveTierSummaryRecord.phase4_validation_summary_id,
                    CandidateEffectiveTierSummaryRecord.phase5_visual_summary_id,
                    CandidateEffectiveTierSummaryRecord.highest_accepted_tier,
                    CandidateEffectiveTierSummaryRecord.summary_sha256,
                    CandidateEffectiveTierSummaryRecord.status,
                )
            )
            .filter(
                CandidateEffectiveTierSummaryRecord.id
                == body.effective_tier_summary_id
            )
            .one_or_none()
        )
        if summary is None or int(summary.request_id) != request_id:
            raise PromotionServiceError(
                "effective_tier_summary_missing", stage="validation"
            )

        candidate = (
            self._db.query(CandidateRevisionRecord)
            .options(
                load_only(
                    CandidateRevisionRecord.id,
                    CandidateRevisionRecord.request_id,
                    CandidateRevisionRecord.workspace_relpath,
                    CandidateRevisionRecord.file_manifest_sha256,
                    CandidateRevisionRecord.upstream_manifest_sha256,
                )
            )
            .filter(CandidateRevisionRecord.id == body.candidate_revision_id)
            .one_or_none()
        )
        if candidate is None or int(candidate.request_id) != request_id:
            raise PromotionServiceError("candidate_missing", stage="validation")

        decision_payload = {
            "request_id": request_id,
            "decision_type": "promote",
            "decision_status": "requested",
            "candidate_revision_id": body.candidate_revision_id,
            "actor_id": actor.actor_id,
            "actor_role": _primary_role(actor),
            "reason": body.reason,
            "policy_revision": app_config.settings.V2_PHASE7_POLICY_REVISION,
            "eligibility_sha256": payload_hash,
            "lineage_sha256": lineage.lineage_sha256,
            "idempotency_key": body.idempotency_key,
            "expected_pointer_version": body.expected_pointer_version,
            "decision_uuid": str(uuid.uuid4()),
        }
        decision = PreviewPromotionDecisionRecord(
            request_id=request_id,
            decision_type="promote",
            decision_status="requested",
            candidate_revision_id=body.candidate_revision_id,
            effective_tier_summary_id=body.effective_tier_summary_id,
            phase4_validation_summary_id=summary.phase4_validation_summary_id,
            phase5_visual_summary_id=summary.phase5_visual_summary_id,
            lineage_sha256=lineage.lineage_sha256,
            candidate_manifest_sha256=lineage.candidate_manifest_sha256,
            actor_id=actor.actor_id,
            actor_role=_primary_role(actor),
            reason=body.reason,
            ticket_ref=body.ticket_ref,
            policy_revision=app_config.settings.V2_PHASE7_POLICY_REVISION,
            eligibility_sha256=payload_hash,
            idempotency_key=body.idempotency_key,
            requested_at=datetime.utcnow(),
            previous_pointer_version=current_version,
            expected_pointer_version=body.expected_pointer_version,
            target_pointer_version=None,
            idempotency_payload_sha256=payload_hash,
            decision_sha256=_payload_sha(decision_payload),
        )
        self._db.add(decision)
        self._db.flush()
        self._append_status(
            decision_id=decision.id,
            status="requested",
            actor_id=actor.actor_id,
            reason=body.reason,
            idempotency_key=body.idempotency_key,
        )
        append_audit_event(
            self._db,
            request_id=request_id,
            event_type="promotion_requested",
            actor_id=actor.actor_id,
            actor_role=_primary_role(actor),
            policy_revision=app_config.settings.V2_PHASE7_POLICY_REVISION,
            decision_id=decision.id,
            lineage_sha256=lineage.lineage_sha256,
            reason=body.reason,
            ticket_ref=body.ticket_ref,
            metadata={
                "candidate_revision_id": body.candidate_revision_id,
                "expected_pointer_version": body.expected_pointer_version,
                "no_pointer_mutation": True,
            },
        )
        return self._decision_view(decision)

    def approve_promotion(
        self,
        *,
        actor: TrustedRolloutActor,
        decision_id: int,
        body: DecisionApprovalBody,
        client_payload: dict[str, Any] | None = None,
    ) -> DecisionView:
        if client_payload is not None:
            reject_client_supplied_roles(client_payload)
        require_permission(actor, "approve_promotion")
        decision = (
            self._db.query(PreviewPromotionDecisionRecord)
            .filter(
                PreviewPromotionDecisionRecord.id == decision_id,
                PreviewPromotionDecisionRecord.decision_type == "promote",
            )
            .one_or_none()
        )
        if decision is None:
            raise PromotionServiceError("decision_not_found", stage="lookup")
        self._require_allowlist_zero_percent(decision.request_id)

        payload_hash = _payload_sha(
            {
                "op": "promotion_approve",
                "decision_id": decision_id,
                "reason": body.reason,
                "ticket_ref": body.ticket_ref,
            }
        )
        if body.idempotency_key:
            prior = (
                self._db.query(PreviewPromotionDecisionStatusEventRecord)
                .filter(
                    PreviewPromotionDecisionStatusEventRecord.decision_id
                    == decision_id,
                    PreviewPromotionDecisionStatusEventRecord.status == "approved",
                    PreviewPromotionDecisionStatusEventRecord.reason.contains(
                        f"idempotency:{body.idempotency_key}"
                    ),
                )
                .one_or_none()
            )
            if prior is not None:
                return self._decision_view(decision)

        status = latest_decision_status(self._db, decision.id)
        if status == "approved":
            if body.idempotency_key:
                raise PromotionServiceError(
                    "idempotency_key_conflict", stage="idempotency"
                )
            return self._decision_view(decision)
        if status != "requested":
            raise PromotionServiceError("decision_not_pending", stage="validation")

        dual = bool(app_config.settings.V2_PHASE7_ALLOW_ADMIN_DUAL_ROLE)
        sod = evaluate_separation_of_duties(
            requester_actor_id=decision.actor_id,
            approver_actor_id=actor.actor_id,
            dual_role_allowed=dual,
            ticket_ref=body.ticket_ref or decision.ticket_ref,
            reason=body.reason,
            require_approver=True,
        )
        if not sod.satisfied:
            raise PromotionServiceError(
                sod.reasons[0] if sod.reasons else "sod_failed",
                stage="sod",
            )

        current = self._repo.get_current_pointer(decision.request_id)
        current_version = None if current is None else int(current.pointer_version)
        if decision.expected_pointer_version != current_version:
            raise PromotionServiceError(
                "pointer_version_mismatch", stage="validation"
            )

        self._append_status(
            decision_id=decision.id,
            status="approved",
            actor_id=actor.actor_id,
            reason=body.reason,
            idempotency_key=body.idempotency_key,
        )
        append_audit_event(
            self._db,
            request_id=decision.request_id,
            event_type="promotion_approved",
            actor_id=actor.actor_id,
            actor_role=_primary_role(actor),
            policy_revision=app_config.settings.V2_PHASE7_POLICY_REVISION,
            decision_id=decision.id,
            reason=body.reason,
            ticket_ref=body.ticket_ref or decision.ticket_ref,
            metadata={
                "requester_actor_id": decision.actor_id,
                "payload_sha256": payload_hash,
                "no_pointer_mutation": True,
                "emergency_dual_role": sod.same_actor,
            },
        )
        return self._decision_view(decision)

    def apply_promotion(
        self,
        *,
        actor: TrustedRolloutActor,
        decision_id: int,
        body: DecisionApplyBody,
        client_payload: dict[str, Any] | None = None,
    ) -> ApplyResultView:
        if client_payload is not None:
            reject_client_supplied_roles(client_payload)
        require_permission(actor, "apply_promotion")
        decision = (
            self._db.query(PreviewPromotionDecisionRecord)
            .filter(
                PreviewPromotionDecisionRecord.id == decision_id,
                PreviewPromotionDecisionRecord.decision_type == "promote",
            )
            .one_or_none()
        )
        if decision is None:
            raise PromotionServiceError("decision_not_found", stage="lookup")

        # Idempotent successful apply
        status = latest_decision_status(self._db, decision.id)
        if status == "applied":
            if body.idempotency_key:
                applied_evt = (
                    self._db.query(PreviewPromotionDecisionStatusEventRecord)
                    .filter(
                        PreviewPromotionDecisionStatusEventRecord.decision_id
                        == decision_id,
                        PreviewPromotionDecisionStatusEventRecord.status
                        == "applied",
                    )
                    .order_by(PreviewPromotionDecisionStatusEventRecord.id.desc())
                    .first()
                )
                if applied_evt and body.idempotency_key not in (
                    applied_evt.reason or ""
                ):
                    # Different key after apply — conflict
                    if f"idempotency:{body.idempotency_key}" not in (
                        applied_evt.reason or ""
                    ):
                        # Allow replay only when key matches or key omitted on first
                        if "idempotency:" in (applied_evt.reason or ""):
                            raise PromotionServiceError(
                                "idempotency_key_conflict", stage="idempotency"
                            )
            pointer = resolve_serving_pointer(self._db, decision.request_id)
            elig = compute_apply_eligibility(
                self._db,
                decision=decision,
                actor=actor,
                expected_pointer_version=body.expected_pointer_version,
                ticket_ref=body.ticket_ref or decision.ticket_ref,
                reason=body.reason,
                emergency_dual_role=body.emergency_dual_role,
            )
            # Replayed apply: do not re-check eligibility as gate; return pointer
            return ApplyResultView(
                decision=self._decision_view(decision),
                pointer=pointer,
                eligibility_sha256=elig.eligibility_sha256,
            )

        eligibility = compute_apply_eligibility(
            self._db,
            decision=decision,
            actor=actor,
            expected_pointer_version=body.expected_pointer_version,
            ticket_ref=body.ticket_ref or decision.ticket_ref,
            reason=body.reason,
            emergency_dual_role=body.emergency_dual_role,
        )
        if not eligibility.eligible_to_apply:
            reason = (
                eligibility.rejection_reasons[0]
                if eligibility.rejection_reasons
                else "apply_ineligible"
            )
            raise PromotionServiceError(reason, stage="eligibility")

        legacy_relpath = None
        initialize_legacy = False
        current = self._repo.get_current_pointer(decision.request_id)
        if current is None:
            dist = _legacy_get_dist_dir(decision.request_id)
            if dist.is_dir() and (dist / "index.html").is_file():
                initialize_legacy = True
                legacy_relpath = str(Path(str(decision.request_id)) / "dist")

        summary = (
            self._db.query(CandidateEffectiveTierSummaryRecord)
            .options(
                load_only(
                    CandidateEffectiveTierSummaryRecord.id,
                    CandidateEffectiveTierSummaryRecord.highest_accepted_tier,
                    CandidateEffectiveTierSummaryRecord.summary_sha256,
                )
            )
            .filter(
                CandidateEffectiveTierSummaryRecord.id
                == decision.effective_tier_summary_id
            )
            .one_or_none()
        )
        effective_tier = None
        summary_sha = None
        if summary is not None:
            effective_tier = int(summary.highest_accepted_tier)
            summary_sha = summary.summary_sha256

        try:
            new_ptr = apply_pointer_swap_transaction(
                self._db,
                request_id=decision.request_id,
                decision=decision,
                expected_pointer_version=body.expected_pointer_version,
                apply_actor_id=actor.actor_id,
                policy_revision=app_config.settings.V2_PHASE7_POLICY_REVISION,
                new_target_kind="v2_candidate",
                pointer_action="promote",
                candidate_revision_id=decision.candidate_revision_id,
                legacy_preview_relpath=legacy_relpath,
                effective_tier=effective_tier,
                summary_sha256=summary_sha,
                candidate_manifest_sha256=decision.candidate_manifest_sha256,
                initialize_legacy_first=initialize_legacy,
            )
        except PointerApplyError as exc:
            self._record_promotion_write_metric(
                decision=decision,
                success=False,
                pointer_version=body.expected_pointer_version,
                reason=exc.reason,
            )
            raise PromotionServiceError(exc.reason, stage="pointer") from exc

        self._record_promotion_write_metric(
            decision=decision,
            success=True,
            pointer_version=new_ptr.pointer_version,
            reason="promote_applied",
        )
        return ApplyResultView(
            decision=self._decision_view(decision),
            pointer=resolve_serving_pointer(self._db, decision.request_id),
            eligibility_sha256=eligibility.eligibility_sha256,
        )

    def request_rollback(
        self,
        *,
        actor: TrustedRolloutActor,
        request_id: int,
        body: RollbackRequestBody,
        client_payload: dict[str, Any] | None = None,
    ) -> DecisionView:
        if client_payload is not None:
            reject_client_supplied_roles(client_payload)
        require_permission(actor, "request_rollback")
        self._require_allowlist_zero_percent(request_id)

        current = self._repo.get_current_pointer(request_id)
        if current is None:
            raise PromotionServiceError("no_current_pointer", stage="validation")
        current_version = int(current.pointer_version)
        if body.expected_pointer_version != current_version:
            raise PromotionServiceError(
                "pointer_version_mismatch", stage="validation"
            )

        target_version = body.target_pointer_version
        if target_version is None:
            if current.previous_pointer_version is None:
                raise PromotionServiceError(
                    "no_rollback_predecessor", stage="validation"
                )
            target_version = int(current.previous_pointer_version)

        ok, reason_code, _target = verify_rollback_target(
            self._db, request_id=request_id, target_pointer_version=target_version
        )
        if not ok:
            raise PromotionServiceError(
                reason_code or "rollback_target_invalid", stage="validation"
            )

        payload_hash = _payload_sha(
            {
                "op": "rollback_request",
                "request_id": request_id,
                "expected_pointer_version": body.expected_pointer_version,
                "target_pointer_version": target_version,
                "reason": body.reason,
                "ticket_ref": body.ticket_ref,
            }
        )
        if body.idempotency_key:
            existing = (
                self._db.query(PreviewPromotionDecisionRecord)
                .filter(
                    PreviewPromotionDecisionRecord.request_id == request_id,
                    PreviewPromotionDecisionRecord.idempotency_key
                    == body.idempotency_key,
                    PreviewPromotionDecisionRecord.decision_type == "rollback",
                )
                .one_or_none()
            )
            if existing is not None:
                if existing.idempotency_payload_sha256 != payload_hash:
                    raise PromotionServiceError(
                        "idempotency_key_conflict", stage="idempotency"
                    )
                return self._decision_view(existing)

        decision_payload = {
            "request_id": request_id,
            "decision_type": "rollback",
            "decision_status": "requested",
            "actor_id": actor.actor_id,
            "target_pointer_version": target_version,
            "expected_pointer_version": body.expected_pointer_version,
            "idempotency_key": body.idempotency_key,
            "decision_uuid": str(uuid.uuid4()),
        }
        decision = PreviewPromotionDecisionRecord(
            request_id=request_id,
            decision_type="rollback",
            decision_status="requested",
            candidate_revision_id=None,
            lineage_sha256=_payload_sha(
                {"request_id": request_id, "target": target_version}
            ),
            actor_id=actor.actor_id,
            actor_role=_primary_role(actor),
            reason=body.reason,
            ticket_ref=body.ticket_ref,
            policy_revision=app_config.settings.V2_PHASE7_POLICY_REVISION,
            eligibility_sha256=payload_hash,
            idempotency_key=body.idempotency_key,
            requested_at=datetime.utcnow(),
            previous_pointer_version=current_version,
            expected_pointer_version=body.expected_pointer_version,
            target_pointer_version=target_version,
            idempotency_payload_sha256=payload_hash,
            decision_sha256=_payload_sha(decision_payload),
        )
        self._db.add(decision)
        self._db.flush()
        self._append_status(
            decision_id=decision.id,
            status="requested",
            actor_id=actor.actor_id,
            reason=body.reason,
            idempotency_key=body.idempotency_key,
        )
        append_audit_event(
            self._db,
            request_id=request_id,
            event_type="rollback_requested",
            actor_id=actor.actor_id,
            actor_role=_primary_role(actor),
            policy_revision=app_config.settings.V2_PHASE7_POLICY_REVISION,
            decision_id=decision.id,
            reason=body.reason,
            ticket_ref=body.ticket_ref,
            metadata={
                "target_pointer_version": target_version,
                "expected_pointer_version": body.expected_pointer_version,
                "no_pointer_mutation": True,
            },
        )
        return self._decision_view(decision)

    def approve_rollback(
        self,
        *,
        actor: TrustedRolloutActor,
        decision_id: int,
        body: DecisionApprovalBody,
        client_payload: dict[str, Any] | None = None,
    ) -> DecisionView:
        if client_payload is not None:
            reject_client_supplied_roles(client_payload)
        require_permission(actor, "approve_rollback")
        decision = (
            self._db.query(PreviewPromotionDecisionRecord)
            .filter(
                PreviewPromotionDecisionRecord.id == decision_id,
                PreviewPromotionDecisionRecord.decision_type == "rollback",
            )
            .one_or_none()
        )
        if decision is None:
            raise PromotionServiceError("decision_not_found", stage="lookup")
        self._require_allowlist_zero_percent(decision.request_id)

        if body.idempotency_key:
            prior = (
                self._db.query(PreviewPromotionDecisionStatusEventRecord)
                .filter(
                    PreviewPromotionDecisionStatusEventRecord.decision_id
                    == decision_id,
                    PreviewPromotionDecisionStatusEventRecord.status == "approved",
                    PreviewPromotionDecisionStatusEventRecord.reason.contains(
                        f"idempotency:{body.idempotency_key}"
                    ),
                )
                .one_or_none()
            )
            if prior is not None:
                return self._decision_view(decision)

        status = latest_decision_status(self._db, decision.id)
        if status == "approved":
            return self._decision_view(decision)
        if status != "requested":
            raise PromotionServiceError("decision_not_pending", stage="validation")

        dual = bool(app_config.settings.V2_PHASE7_ALLOW_ADMIN_DUAL_ROLE)
        sod = evaluate_separation_of_duties(
            requester_actor_id=decision.actor_id,
            approver_actor_id=actor.actor_id,
            dual_role_allowed=dual,
            ticket_ref=body.ticket_ref or decision.ticket_ref,
            reason=body.reason,
            require_approver=True,
        )
        if not sod.satisfied:
            raise PromotionServiceError(
                sod.reasons[0] if sod.reasons else "sod_failed",
                stage="sod",
            )

        current = self._repo.get_current_pointer(decision.request_id)
        current_version = None if current is None else int(current.pointer_version)
        if decision.expected_pointer_version != current_version:
            raise PromotionServiceError(
                "pointer_version_mismatch", stage="validation"
            )

        self._append_status(
            decision_id=decision.id,
            status="approved",
            actor_id=actor.actor_id,
            reason=body.reason,
            idempotency_key=body.idempotency_key,
        )
        append_audit_event(
            self._db,
            request_id=decision.request_id,
            event_type="rollback_approved",
            actor_id=actor.actor_id,
            actor_role=_primary_role(actor),
            policy_revision=app_config.settings.V2_PHASE7_POLICY_REVISION,
            decision_id=decision.id,
            reason=body.reason,
            ticket_ref=body.ticket_ref or decision.ticket_ref,
            metadata={
                "requester_actor_id": decision.actor_id,
                "no_pointer_mutation": True,
                "emergency_dual_role": sod.same_actor,
            },
        )
        return self._decision_view(decision)

    def apply_rollback(
        self,
        *,
        actor: TrustedRolloutActor,
        decision_id: int,
        body: DecisionApplyBody,
        client_payload: dict[str, Any] | None = None,
    ) -> ApplyResultView:
        if client_payload is not None:
            reject_client_supplied_roles(client_payload)
        require_permission(actor, "apply_rollback")
        decision = (
            self._db.query(PreviewPromotionDecisionRecord)
            .filter(
                PreviewPromotionDecisionRecord.id == decision_id,
                PreviewPromotionDecisionRecord.decision_type == "rollback",
            )
            .one_or_none()
        )
        if decision is None:
            raise PromotionServiceError("decision_not_found", stage="lookup")

        status = latest_decision_status(self._db, decision.id)
        if status == "applied":
            return ApplyResultView(
                decision=self._decision_view(decision),
                pointer=resolve_serving_pointer(self._db, decision.request_id),
                eligibility_sha256=_payload_sha(
                    {"decision_id": decision_id, "replay": True}
                ),
            )

        eligibility = compute_apply_eligibility(
            self._db,
            decision=decision,
            actor=actor,
            expected_pointer_version=body.expected_pointer_version,
            ticket_ref=body.ticket_ref or decision.ticket_ref,
            reason=body.reason,
            emergency_dual_role=body.emergency_dual_role,
        )
        if not eligibility.eligible_to_apply:
            reason = (
                eligibility.rejection_reasons[0]
                if eligibility.rejection_reasons
                else "apply_ineligible"
            )
            raise PromotionServiceError(reason, stage="eligibility")

        target = (
            self._db.query(PreviewServingPointerVersionRecord)
            .filter(
                PreviewServingPointerVersionRecord.request_id
                == decision.request_id,
                PreviewServingPointerVersionRecord.pointer_version
                == decision.target_pointer_version,
            )
            .one()
        )
        try:
            new_pointer = apply_pointer_swap_transaction(
                self._db,
                request_id=decision.request_id,
                decision=decision,
                expected_pointer_version=body.expected_pointer_version,
                apply_actor_id=actor.actor_id,
                policy_revision=app_config.settings.V2_PHASE7_POLICY_REVISION,
                new_target_kind=target.target_kind
                if target.target_kind != "rollback"
                else (
                    "v2_candidate"
                    if target.candidate_revision_id
                    else "legacy_v1"
                ),
                pointer_action="rollback",
                candidate_revision_id=target.candidate_revision_id,
                legacy_preview_relpath=target.legacy_preview_relpath,
                effective_tier=target.effective_tier,
                summary_sha256=target.summary_sha256,
                candidate_manifest_sha256=target.candidate_manifest_sha256,
                initialize_legacy_first=False,
            )
        except PointerApplyError as exc:
            self._record_promotion_write_metric(
                decision=decision,
                success=False,
                pointer_version=body.expected_pointer_version,
                reason=exc.reason,
            )
            raise PromotionServiceError(exc.reason, stage="pointer") from exc

        self._record_promotion_write_metric(
            decision=decision,
            success=True,
            pointer_version=new_pointer.pointer_version,
            reason="rollback_applied",
        )
        return ApplyResultView(
            decision=self._decision_view(decision),
            pointer=resolve_serving_pointer(self._db, decision.request_id),
            eligibility_sha256=eligibility.eligibility_sha256,
        )

    def _record_promotion_write_metric(
        self,
        *,
        decision: PreviewPromotionDecisionRecord,
        success: bool,
        pointer_version: int | None,
        reason: str,
    ) -> None:
        """Best-effort append for breaker window; never fails the apply path."""
        if not app_config.settings.V2_PHASE7_CIRCUIT_BREAKER_ENABLED:
            return
        try:
            metric = (
                "promotion_write_success" if success else "promotion_write_failure"
            )
            append_metric_sample(
                self._db,
                metric_class=metric,  # type: ignore[arg-type]
                outcome="success" if success else "failure",
                policy_revision=app_config.settings.V2_PHASE7_POLICY_REVISION,
                source_event_hash=_payload_sha(
                    {
                        "metric": metric,
                        "decision_id": decision.id,
                        "request_id": decision.request_id,
                        "pointer_version": pointer_version,
                        "reason": reason,
                    }
                ),
                request_id=decision.request_id,
                decision_id=decision.id,
                pointer_version=pointer_version,
                source_event_id=f"promotion_write:{decision.id}:{reason}",
                metadata={"reason": reason, "decision_type": decision.decision_type},
            )
        except Exception:  # noqa: BLE001
            return


__all__ = ["PromotionService", "PromotionServiceError"]
