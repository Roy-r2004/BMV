"""Phase 7D automatic rollback — reuses Phase 7C pointer transaction."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session, load_only

from app.application.rollout.apply_eligibility import latest_decision_status
from app.application.rollout.apply_transaction import (
    PointerApplyError,
    apply_pointer_swap_transaction,
)
from app.application.rollout.audit import append_audit_event
from app.application.rollout.authorization import require_permission
from app.application.rollout.health_precheck import verify_rollback_target
from app.core import config as app_config
from app.domain.models.preview_candidate import CandidateRevisionRecord
from app.domain.models.rollout import (
    PreviewBreakerAutoRollbackClaimRecord,
    PreviewPromotionDecisionRecord,
    PreviewPromotionDecisionStatusEventRecord,
    PreviewServingPointerVersionRecord,
)
from app.domain.schemas.breaker import (
    SYSTEM_BREAKER_ACTOR_ID,
    AutoRollbackResultView,
)
from app.domain.schemas.rollout import TrustedRolloutActor


def _sha(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _event_sha(payload: dict[str, Any]) -> str:
    return _sha(payload)


def system_breaker_actor() -> TrustedRolloutActor:
    return TrustedRolloutActor(
        actor_id=SYSTEM_BREAKER_ACTOR_ID,
        roles=("rollout_admin",),
        auth_source="service_principal",
    )


class AutoRollbackService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _auto_enabled(self) -> bool:
        s = app_config.settings
        return bool(
            s.V2_PHASE7_CONFIG_VALID
            and s.V2_PHASE7_ROLLOUT_ENABLED
            and s.V2_PHASE7_PROMOTE_ENABLED
            and s.V2_PHASE7_CIRCUIT_BREAKER_ENABLED
            and s.V2_PHASE7_AUTO_ROLLBACK_ENABLED
        )

    def list_results(
        self, *, actor: TrustedRolloutActor
    ) -> list[AutoRollbackResultView]:
        require_permission(actor, "read_breaker")
        claims = (
            self._db.query(PreviewBreakerAutoRollbackClaimRecord)
            .order_by(PreviewBreakerAutoRollbackClaimRecord.id.desc())
            .limit(200)
            .all()
        )
        out: list[AutoRollbackResultView] = []
        for c in claims:
            out.append(
                AutoRollbackResultView(
                    open_state_id=c.open_state_id,
                    request_id=c.request_id,
                    decision_id=c.decision_id,
                    status=c.status,  # type: ignore[arg-type]
                    reason=c.status,
                    resulting_pointer_version=None,
                    target_pointer_version=c.target_pointer_version,
                    idempotency_key=c.idempotency_key,
                )
            )
        return out

    def run_for_open_event(
        self,
        *,
        actor: TrustedRolloutActor,
        open_state_id: int,
        metric_snapshot_sha256: str,
    ) -> list[AutoRollbackResultView]:
        require_permission(actor, "run_auto_rollback")
        if not self._auto_enabled():
            return []

        lookback = app_config.settings.V2_PHASE7_AUTO_ROLLBACK_LOOKBACK_SECONDS
        cutoff = datetime.utcnow() - timedelta(seconds=lookback)
        max_req = app_config.settings.V2_PHASE7_BREAKER_EVAL_MAX_REQUESTS
        currents = (
            self._db.query(PreviewServingPointerVersionRecord)
            .filter(
                PreviewServingPointerVersionRecord.is_current.is_(True),
                PreviewServingPointerVersionRecord.created_at >= cutoff,
            )
            .order_by(PreviewServingPointerVersionRecord.id.asc())
            .limit(max_req)
            .all()
        )
        results: list[AutoRollbackResultView] = []
        for ptr in currents:
            results.append(
                self._process_request(
                    actor=actor,
                    open_state_id=open_state_id,
                    metric_snapshot_sha256=metric_snapshot_sha256,
                    current=ptr,
                    lookback_seconds=lookback,
                )
            )
        return results

    def _human_apply_in_flight(self, request_id: int) -> bool:
        """True when a non-system decision is approved and not yet applied."""
        decisions = (
            self._db.query(PreviewPromotionDecisionRecord)
            .filter(PreviewPromotionDecisionRecord.request_id == request_id)
            .order_by(PreviewPromotionDecisionRecord.id.desc())
            .limit(20)
            .all()
        )
        for decision in decisions:
            if decision.actor_id == SYSTEM_BREAKER_ACTOR_ID:
                continue
            status = latest_decision_status(self._db, decision.id)
            if status == "approved":
                return True
        return False

    def _pointer_unhealthy(self, ptr: PreviewServingPointerVersionRecord) -> bool:
        if ptr.target_kind not in ("v2_candidate", "rollback"):
            return False
        if not ptr.candidate_revision_id:
            return True
        cand = (
            self._db.query(CandidateRevisionRecord)
            .options(
                load_only(
                    CandidateRevisionRecord.id,
                    CandidateRevisionRecord.workspace_relpath,
                    CandidateRevisionRecord.file_manifest_sha256,
                    CandidateRevisionRecord.upstream_manifest_sha256,
                )
            )
            .filter(CandidateRevisionRecord.id == ptr.candidate_revision_id)
            .one_or_none()
        )
        if cand is None or not cand.workspace_relpath:
            return True
        root = app_config.settings.PREVIEW_CANDIDATES_DIR.resolve(strict=False)
        workspace = (root / cand.workspace_relpath).resolve(strict=False)
        try:
            workspace.relative_to(root)
        except ValueError:
            return True
        dist = workspace / "dist"
        if not dist.is_dir() or not (dist / "index.html").is_file():
            return True
        manifest = cand.file_manifest_sha256 or cand.upstream_manifest_sha256
        if (
            ptr.candidate_manifest_sha256
            and manifest
            and ptr.candidate_manifest_sha256 != manifest
        ):
            return True
        return False

    def _select_predecessor(
        self, current: PreviewServingPointerVersionRecord
    ) -> PreviewServingPointerVersionRecord | None:
        if current.previous_pointer_version is not None:
            ok, _reason, row = verify_rollback_target(
                self._db,
                request_id=current.request_id,
                target_pointer_version=int(current.previous_pointer_version),
            )
            if ok and row is not None:
                return row
        legacy = (
            self._db.query(PreviewServingPointerVersionRecord)
            .filter(
                PreviewServingPointerVersionRecord.request_id == current.request_id,
                PreviewServingPointerVersionRecord.target_kind == "legacy_v1",
            )
            .order_by(PreviewServingPointerVersionRecord.pointer_version.desc())
            .first()
        )
        if legacy is None:
            return None
        ok, _reason, row = verify_rollback_target(
            self._db,
            request_id=current.request_id,
            target_pointer_version=int(legacy.pointer_version),
        )
        return row if ok else None

    def _process_request(
        self,
        *,
        actor: TrustedRolloutActor,
        open_state_id: int,
        metric_snapshot_sha256: str,
        current: PreviewServingPointerVersionRecord,
        lookback_seconds: int,
    ) -> AutoRollbackResultView:
        request_id = current.request_id
        existing = (
            self._db.query(PreviewBreakerAutoRollbackClaimRecord)
            .filter(
                PreviewBreakerAutoRollbackClaimRecord.open_state_id == open_state_id,
                PreviewBreakerAutoRollbackClaimRecord.request_id == request_id,
            )
            .one_or_none()
        )
        if existing is not None:
            return AutoRollbackResultView(
                open_state_id=open_state_id,
                request_id=request_id,
                decision_id=existing.decision_id,
                status="already_processed",
                reason="claim_exists",
                target_pointer_version=existing.target_pointer_version,
                idempotency_key=existing.idempotency_key,
            )

        if current.target_kind not in ("v2_candidate", "rollback"):
            return self._claim_skip(
                open_state_id,
                request_id,
                current.pointer_version,
                0,
                "not_v2_current",
            )
        if self._human_apply_in_flight(request_id):
            return self._claim_skip(
                open_state_id,
                request_id,
                current.pointer_version,
                0,
                "human_apply_in_flight",
            )
        if not self._pointer_unhealthy(current):
            return self._claim_skip(
                open_state_id,
                request_id,
                current.pointer_version,
                0,
                "pointer_healthy",
            )
        predecessor = self._select_predecessor(current)
        if predecessor is None:
            return self._claim_skip(
                open_state_id,
                request_id,
                current.pointer_version,
                0,
                "no_verified_predecessor",
            )

        idem_key = (
            f"auto_rb:{open_state_id}:{request_id}:"
            f"{current.pointer_version}:{predecessor.pointer_version}"
        )
        claim_payload = {
            "open_state_id": open_state_id,
            "request_id": request_id,
            "expected": current.pointer_version,
            "target": predecessor.pointer_version,
        }
        try:
            return self._execute_auto_rollback(
                actor=actor,
                open_state_id=open_state_id,
                metric_snapshot_sha256=metric_snapshot_sha256,
                current=current,
                predecessor=predecessor,
                idem_key=idem_key,
                claim_payload=claim_payload,
                lookback_seconds=lookback_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            self._db.rollback()
            # Record failed claim so we do not auto-retry
            self._db.add(
                PreviewBreakerAutoRollbackClaimRecord(
                    open_state_id=open_state_id,
                    request_id=request_id,
                    decision_id=None,
                    expected_pointer_version=current.pointer_version,
                    target_pointer_version=predecessor.pointer_version,
                    idempotency_key=idem_key + ":failed",
                    claim_sha256=_sha({**claim_payload, "failed": str(exc)}),
                    status="failed",
                    created_at=datetime.utcnow(),
                )
            )
            append_audit_event(
                self._db,
                request_id=request_id,
                event_type="breaker_auto_rollback_applied",
                actor_id=SYSTEM_BREAKER_ACTOR_ID,
                actor_role="rollout_admin",
                policy_revision=app_config.settings.V2_PHASE7_POLICY_REVISION,
                reason=f"auto_rollback_failed:{exc}",
                metadata={
                    "auto_rollback": True,
                    "open_state_id": open_state_id,
                    "failed": True,
                },
            )
            self._db.flush()
            return AutoRollbackResultView(
                open_state_id=open_state_id,
                request_id=request_id,
                status="failed",
                reason=str(exc),
                target_pointer_version=predecessor.pointer_version,
                idempotency_key=idem_key,
            )

    def _claim_skip(
        self,
        open_state_id: int,
        request_id: int,
        expected: int,
        target: int,
        reason: str,
    ) -> AutoRollbackResultView:
        idem = f"auto_rb_skip:{open_state_id}:{request_id}:{reason}"
        self._db.add(
            PreviewBreakerAutoRollbackClaimRecord(
                open_state_id=open_state_id,
                request_id=request_id,
                decision_id=None,
                expected_pointer_version=expected,
                target_pointer_version=target or 0,
                idempotency_key=idem,
                claim_sha256=_sha(
                    {
                        "open_state_id": open_state_id,
                        "request_id": request_id,
                        "reason": reason,
                    }
                ),
                status="skipped",
                created_at=datetime.utcnow(),
            )
        )
        self._db.flush()
        return AutoRollbackResultView(
            open_state_id=open_state_id,
            request_id=request_id,
            status="skipped",
            reason=reason,
            target_pointer_version=target or None,
            idempotency_key=idem,
        )

    def _execute_auto_rollback(
        self,
        *,
        actor: TrustedRolloutActor,
        open_state_id: int,
        metric_snapshot_sha256: str,
        current: PreviewServingPointerVersionRecord,
        predecessor: PreviewServingPointerVersionRecord,
        idem_key: str,
        claim_payload: dict[str, Any],
        lookback_seconds: int,
    ) -> AutoRollbackResultView:
        reason = f"auto_rollback:{open_state_id}"
        decision_payload = {
            "request_id": current.request_id,
            "decision_type": "rollback",
            "decision_status": "requested",
            "actor_id": SYSTEM_BREAKER_ACTOR_ID,
            "target_pointer_version": predecessor.pointer_version,
            "expected_pointer_version": current.pointer_version,
            "idempotency_key": idem_key,
            "decision_uuid": str(uuid.uuid4()),
            "auto_rollback": True,
        }
        decision = PreviewPromotionDecisionRecord(
            request_id=current.request_id,
            decision_type="rollback",
            decision_status="requested",
            candidate_revision_id=None,
            lineage_sha256=_sha(
                {
                    "request_id": current.request_id,
                    "target": predecessor.pointer_version,
                    "open": open_state_id,
                }
            ),
            actor_id=SYSTEM_BREAKER_ACTOR_ID,
            actor_role="rollout_admin",
            reason=reason,
            ticket_ref=f"breaker-open:{open_state_id}",
            policy_revision=app_config.settings.V2_PHASE7_POLICY_REVISION,
            eligibility_sha256=metric_snapshot_sha256,
            idempotency_key=idem_key,
            requested_at=datetime.utcnow(),
            previous_pointer_version=current.pointer_version,
            expected_pointer_version=current.pointer_version,
            target_pointer_version=predecessor.pointer_version,
            idempotency_payload_sha256=_sha(claim_payload),
            decision_sha256=_sha(decision_payload),
        )
        self._db.add(decision)
        self._db.flush()

        for status, status_reason in (
            ("requested", reason),
            ("approved", "system_auto_approved"),
        ):
            payload = {
                "decision_id": decision.id,
                "status": status,
                "actor_id": SYSTEM_BREAKER_ACTOR_ID,
                "reason": status_reason,
            }
            self._db.add(
                PreviewPromotionDecisionStatusEventRecord(
                    decision_id=decision.id,
                    status=status,
                    actor_id=SYSTEM_BREAKER_ACTOR_ID,
                    reason=status_reason,
                    created_at=datetime.utcnow(),
                    event_sha256=_event_sha(payload),
                )
            )
        self._db.flush()

        target_kind = (
            predecessor.target_kind
            if predecessor.target_kind != "rollback"
            else (
                "v2_candidate"
                if predecessor.candidate_revision_id
                else "legacy_v1"
            )
        )
        try:
            new_ptr = apply_pointer_swap_transaction(
                self._db,
                request_id=current.request_id,
                decision=decision,
                expected_pointer_version=current.pointer_version,
                apply_actor_id=SYSTEM_BREAKER_ACTOR_ID,
                policy_revision=app_config.settings.V2_PHASE7_POLICY_REVISION,
                new_target_kind=target_kind,
                pointer_action="rollback",
                candidate_revision_id=predecessor.candidate_revision_id,
                legacy_preview_relpath=predecessor.legacy_preview_relpath,
                effective_tier=predecessor.effective_tier,
                summary_sha256=predecessor.summary_sha256,
                candidate_manifest_sha256=predecessor.candidate_manifest_sha256,
                initialize_legacy_first=False,
            )
        except PointerApplyError as exc:
            raise RuntimeError(exc.reason) from exc

        append_audit_event(
            self._db,
            request_id=current.request_id,
            event_type="breaker_auto_rollback_applied",
            actor_id=SYSTEM_BREAKER_ACTOR_ID,
            actor_role="rollout_admin",
            policy_revision=app_config.settings.V2_PHASE7_POLICY_REVISION,
            decision_id=decision.id,
            pointer_version_before=current.pointer_version,
            pointer_version_after=new_ptr.pointer_version,
            reason=reason,
            ticket_ref=f"breaker-open:{open_state_id}",
            metadata={
                "auto_rollback": True,
                "system_auto_approved": True,
                "breaker_state_id": open_state_id,
                "breaker_policy_revision": app_config.settings.V2_PHASE7_POLICY_REVISION,
                "triggering_metric_snapshot_sha256": metric_snapshot_sha256,
                "lookback_seconds": lookback_seconds,
                "trigger_actor": actor.actor_id,
            },
        )
        self._db.add(
            PreviewBreakerAutoRollbackClaimRecord(
                open_state_id=open_state_id,
                request_id=current.request_id,
                decision_id=decision.id,
                expected_pointer_version=current.pointer_version,
                target_pointer_version=predecessor.pointer_version,
                idempotency_key=idem_key,
                claim_sha256=_sha(claim_payload),
                status="applied",
                created_at=datetime.utcnow(),
            )
        )
        self._db.flush()
        return AutoRollbackResultView(
            open_state_id=open_state_id,
            request_id=current.request_id,
            decision_id=decision.id,
            status="applied",
            reason=reason,
            resulting_pointer_version=new_ptr.pointer_version,
            target_pointer_version=predecessor.pointer_version,
            idempotency_key=idem_key,
        )


__all__ = ["AutoRollbackService", "system_breaker_actor"]
