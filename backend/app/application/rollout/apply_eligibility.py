"""Strict Phase 7C apply eligibility — recomputed per apply, never a write token."""
from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from app.application.rollout.authorization import evaluate_separation_of_duties
from app.application.rollout.breaker_service import (
    BreakerService,
    human_apply_blocked_by_breaker,
)
from app.application.rollout.health_precheck import (
    run_promote_health_precheck,
    verify_rollback_target,
)
from app.application.rollout.repository import RolloutRepository
from app.core import config as app_config
from app.domain.models.rollout import (
    PreviewPromotionDecisionRecord,
    PreviewPromotionDecisionStatusEventRecord,
)
from app.domain.schemas.promotion import (
    HealthPrecheckResult,
    PromotionApplyEligibilityResult,
)
from app.domain.schemas.rollout import BreakerState, TrustedRolloutActor


def latest_decision_status(
    db: Session, decision_id: int
) -> str | None:
    row = (
        db.query(PreviewPromotionDecisionStatusEventRecord)
        .filter(PreviewPromotionDecisionStatusEventRecord.decision_id == decision_id)
        .order_by(
            PreviewPromotionDecisionStatusEventRecord.id.desc(),
        )
        .first()
    )
    return None if row is None else str(row.status)


def latest_status_actor(
    db: Session, decision_id: int, status: str
) -> str | None:
    row = (
        db.query(PreviewPromotionDecisionStatusEventRecord)
        .filter(
            PreviewPromotionDecisionStatusEventRecord.decision_id == decision_id,
            PreviewPromotionDecisionStatusEventRecord.status == status,
        )
        .order_by(PreviewPromotionDecisionStatusEventRecord.id.desc())
        .first()
    )
    return None if row is None else str(row.actor_id)


def _eligibility_sha(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def compute_apply_eligibility(
    db: Session,
    *,
    decision: PreviewPromotionDecisionRecord,
    actor: TrustedRolloutActor,
    expected_pointer_version: int | None,
    ticket_ref: str | None,
    reason: str,
    emergency_dual_role: bool = False,
) -> PromotionApplyEligibilityResult:
    repo = RolloutRepository(db)
    current = repo.get_current_pointer(decision.request_id)
    current_version = None if current is None else int(current.pointer_version)
    status = latest_decision_status(db, decision.id) or decision.decision_status
    requester = decision.actor_id
    approver = latest_status_actor(db, decision.id, "approved")

    dual = bool(
        emergency_dual_role or app_config.settings.V2_PHASE7_ALLOW_ADMIN_DUAL_ROLE
    )
    sod = evaluate_separation_of_duties(
        requester_actor_id=requester,
        approver_actor_id=approver,
        apply_actor_id=actor.actor_id,
        dual_role_allowed=dual,
        ticket_ref=ticket_ref or decision.ticket_ref,
        reason=reason,
        require_approver=True,
    )

    allowlisted = decision.request_id in set(
        app_config.settings.V2_PHASE7_REQUEST_ALLOWLIST
    )
    percent_zero = app_config.settings.V2_PHASE7_ROLLOUT_PERCENT == 0
    master = bool(app_config.settings.V2_PHASE7_ROLLOUT_ENABLED)
    promote = bool(app_config.settings.V2_PHASE7_PROMOTE_ENABLED)
    config_valid = bool(app_config.settings.V2_PHASE7_CONFIG_VALID)
    flags_enabled = master and promote and config_valid
    breaker: BreakerState = BreakerService(db).current_state()
    # Phase 7D first cut: human apply fails closed while open or half_open.
    breaker_not_open = not human_apply_blocked_by_breaker(db)

    pointer_matches = current_version == expected_pointer_version
    approved = status == "approved"

    rejection: list[str] = []
    if not allowlisted:
        rejection.append("not_allowlisted")
    if not percent_zero:
        rejection.append("rollout_percent_nonzero")
    if not flags_enabled:
        rejection.append("flags_disabled")
    if not breaker_not_open:
        rejection.append("breaker_open")
    if not approved:
        rejection.append("not_approved")
    if not pointer_matches:
        rejection.append("pointer_version_mismatch")
    if not sod.satisfied:
        rejection.extend(sod.reasons)

    phase4_ok = False
    phase5_ok = False
    effective_tier_ok = False
    manifest_ok = False
    health: HealthPrecheckResult

    if decision.decision_type == "promote":
        health = run_promote_health_precheck(
            db,
            request_id=decision.request_id,
            candidate_revision_id=int(decision.candidate_revision_id or 0),
            effective_tier_summary_id=int(decision.effective_tier_summary_id or 0),
            expected_manifest_sha256=decision.candidate_manifest_sha256,
            phase4_summary_id=decision.phase4_validation_summary_id,
            phase5_summary_id=decision.phase5_visual_summary_id,
            allowlisted=allowlisted,
            rollout_percent_zero=percent_zero,
            flags_enabled=flags_enabled,
            breaker_not_open=breaker_not_open,
            decision_exists=True,
            latest_status_approved=approved,
            pointer_version_matches=pointer_matches,
        )
        phase4_ok = health.phase4_ok
        phase5_ok = health.phase5_ok
        effective_tier_ok = health.effective_tier_ok
        manifest_ok = health.manifest_matches
        if not health.passed:
            rejection.extend(list(health.reasons))
    else:
        target_ver = decision.target_pointer_version
        ok, reason_code, _row = (
            (False, "rollback_target_missing", None)
            if target_ver is None
            else verify_rollback_target(
                db,
                request_id=decision.request_id,
                target_pointer_version=int(target_ver),
            )
        )
        if not ok and reason_code:
            rejection.append(reason_code)
        health = HealthPrecheckResult(
            passed=ok
            and allowlisted
            and percent_zero
            and flags_enabled
            and breaker_not_open
            and approved
            and pointer_matches
            and sod.satisfied,
            decision_exists=True,
            latest_status_approved=approved,
            pointer_version_matches=pointer_matches,
            allowlisted=allowlisted,
            rollout_percent_zero=percent_zero,
            flags_enabled=flags_enabled,
            breaker_not_open=breaker_not_open,
            candidate_exists=ok,
            manifest_matches=ok,
            dist_exists=ok,
            entry_exists=ok,
            phase4_ok=True,
            phase5_ok=True,
            effective_tier_ok=True,
            reasons=tuple(rejection),
        )
        phase4_ok = True
        phase5_ok = True
        effective_tier_ok = True
        manifest_ok = ok

    # Deduplicate while preserving order
    rejection = list(dict.fromkeys(rejection))
    eligible = not rejection and health.passed and sod.satisfied

    payload = {
        "request_id": decision.request_id,
        "decision_id": decision.id,
        "decision_type": decision.decision_type,
        "candidate_revision_id": decision.candidate_revision_id,
        "target_pointer_version": decision.target_pointer_version,
        "current_pointer_version": current_version,
        "expected_pointer_version": expected_pointer_version,
        "latest_decision_status": status,
        "requester_actor_id": requester,
        "approver_actor_id": approver,
        "apply_actor_id": actor.actor_id,
        "allowlisted": allowlisted,
        "rollout_percent_zero": percent_zero,
        "eligible_to_apply": eligible,
        "rejection_reasons": rejection,
    }
    return PromotionApplyEligibilityResult(
        request_id=decision.request_id,
        decision_id=decision.id,
        decision_type=decision.decision_type,  # type: ignore[arg-type]
        candidate_revision_id=decision.candidate_revision_id,
        target_pointer_version=decision.target_pointer_version,
        current_pointer_version=current_version,
        expected_pointer_version=expected_pointer_version,
        latest_decision_status=status,  # type: ignore[arg-type]
        requester_actor_id=requester,
        approver_actor_id=approver,
        apply_actor_id=actor.actor_id,
        separation_of_duties=sod,
        allowlisted=allowlisted,
        rollout_percent_zero=percent_zero,
        master_enabled=master,
        promote_enabled=promote,
        circuit_breaker_state=breaker,
        phase4_ok=phase4_ok,
        phase5_ok=phase5_ok,
        effective_tier_ok=effective_tier_ok,
        manifest_ok=manifest_ok,
        health=health,
        eligible_to_apply=eligible,
        reusable_write_token=False,
        rejection_reasons=tuple(rejection),
        eligibility_sha256=_eligibility_sha(payload),
    )


__all__ = [
    "compute_apply_eligibility",
    "latest_decision_status",
    "latest_status_actor",
]
