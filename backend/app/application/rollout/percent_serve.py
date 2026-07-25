"""Phase 7F sticky-percentage serving eligibility (read-only, no providers)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.application.rollout.canary_auth_cache import (
    CanaryAuthSnapshot,
    invalidate_canary_auth_cache,
    resolve_canary_auth,
)
from app.application.rollout.canary_policy import compute_policy_identity
from app.application.rollout.targeting import compute_sticky_bucket
from app.core import config as app_config
from app.domain.models.rollout import (
    PreviewLiveCanaryExecutionRecord,
    PreviewLiveCanaryLifecycleEventRecord,
    PreviewServingPointerVersionRecord,
)
from app.domain.schemas.canary import ServePathReason, TargetingDiagnosticView
from app.domain.schemas.rollout import BreakerState

ServeMode = Literal["pointer", "legacy"]


@dataclass(frozen=True)
class ServeEligibility:
    mode: ServeMode
    reason: ServePathReason
    allowlisted: bool
    percent_eligible: bool
    canary_gate_valid: bool
    canary_gate_reason: str | None
    sticky_bucket: int
    configured_percent: int
    current_pointer_available: bool
    breaker_state: BreakerState


def _breaker_state(db: Session) -> BreakerState:
    if not app_config.settings.V2_PHASE7_CIRCUIT_BREAKER_ENABLED:
        return "disabled"
    from app.application.rollout.breaker_service import BreakerService

    try:
        return BreakerService(db).current_state()  # type: ignore[return-value]
    except Exception:  # noqa: BLE001
        return "disabled"


def _auth_cache_key(
    *,
    identity,
    execution_id: int | None,
    execution_sha256: str | None,
    execution_mode: str,
    percent_authorization_eligible: bool,
) -> str:
    material = {
        "policy_identity_sha256": identity.policy_identity_sha256,
        "rollout_salt": identity.rollout_salt,
        "policy_revision": identity.policy_revision,
        "provider_manifest_sha256": identity.provider_manifest_sha256,
        "generation_policy_sha256": identity.generation_policy_sha256,
        "prompt_policy_sha256": identity.prompt_policy_sha256,
        "runtime_policy_sha256": identity.runtime_policy_sha256,
        "comparison_policy_revision": identity.comparison_policy_revision,
        "execution_id": execution_id,
        "execution_sha256": execution_sha256,
        "execution_mode": execution_mode,
        "percent_authorization_eligible": percent_authorization_eligible,
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _execution_authorizes_percent(
    exec_row: PreviewLiveCanaryExecutionRecord, identity
) -> bool:
    if exec_row.result_status != "completed":
        return False
    if exec_row.execution_mode != "live":
        return False
    if not bool(exec_row.provider_was_live):
        return False
    if bool(exec_row.simulation_only):
        return False
    if not bool(exec_row.percent_authorization_eligible):
        return False
    if exec_row.policy_identity_sha256 != identity.policy_identity_sha256:
        return False
    if exec_row.provider_manifest_sha256 != identity.provider_manifest_sha256:
        return False
    if exec_row.generation_policy_sha256 != identity.generation_policy_sha256:
        return False
    if exec_row.prompt_policy_sha256 != identity.prompt_policy_sha256:
        return False
    if not exec_row.no_serving_mutation:
        return False
    if exec_row.pointer_version_before != exec_row.pointer_version_after:
        return False
    if exec_row.phase4_status != "candidate_runtime_validated":
        return False
    if exec_row.phase5_status != "candidate_visual_accepted":
        return False
    if not exec_row.comparison_artifact_sha256:
        return False
    return True


def _load_canary_auth(db: Session) -> CanaryAuthSnapshot:
    identity = compute_policy_identity()
    base_key = _auth_cache_key(
        identity=identity,
        execution_id=None,
        execution_sha256=None,
        execution_mode="none",
        percent_authorization_eligible=False,
    )
    if not app_config.settings.V2_PHASE7_PERCENT_REQUIRES_CANARY:
        return CanaryAuthSnapshot(
            valid=True,
            reason="canary_not_required",
            execution_id=None,
            execution_sha256=None,
            policy_identity_sha256=identity.policy_identity_sha256,
            cache_key=base_key,
            execution_mode=None,
            percent_authorization_eligible=False,
        )

    accepted = (
        db.query(PreviewLiveCanaryLifecycleEventRecord)
        .filter(PreviewLiveCanaryLifecycleEventRecord.status == "reviewed_accepted")
        .order_by(PreviewLiveCanaryLifecycleEventRecord.id.desc())
        .limit(8)
        .all()
    )
    fixture_only = (
        db.query(PreviewLiveCanaryLifecycleEventRecord)
        .filter(
            PreviewLiveCanaryLifecycleEventRecord.status == "reviewed_fixture_only"
        )
        .order_by(PreviewLiveCanaryLifecycleEventRecord.id.desc())
        .limit(1)
        .first()
    )

    if not accepted:
        reason = (
            "fixture_canary_not_eligible" if fixture_only is not None else "missing_canary"
        )
        return CanaryAuthSnapshot(
            valid=False,
            reason=reason,
            execution_id=None,
            execution_sha256=None,
            policy_identity_sha256=identity.policy_identity_sha256,
            cache_key=base_key,
            execution_mode="fixture" if fixture_only is not None else None,
            percent_authorization_eligible=False,
        )

    for life in accepted:
        exec_row = (
            db.query(PreviewLiveCanaryExecutionRecord)
            .filter(
                PreviewLiveCanaryExecutionRecord.approval_id == life.approval_id,
                PreviewLiveCanaryExecutionRecord.result_status == "completed",
            )
            .order_by(PreviewLiveCanaryExecutionRecord.id.desc())
            .first()
        )
        if exec_row is None:
            continue
        if not _execution_authorizes_percent(exec_row, identity):
            if exec_row.execution_mode == "fixture" or bool(exec_row.simulation_only):
                continue
            continue
        cache_key = _auth_cache_key(
            identity=identity,
            execution_id=exec_row.id,
            execution_sha256=exec_row.execution_sha256,
            execution_mode="live",
            percent_authorization_eligible=True,
        )
        return CanaryAuthSnapshot(
            valid=True,
            reason="reviewed_accepted",
            execution_id=exec_row.id,
            execution_sha256=exec_row.execution_sha256,
            policy_identity_sha256=identity.policy_identity_sha256,
            cache_key=cache_key,
            execution_mode="live",
            percent_authorization_eligible=True,
        )

    # Reviewed_accepted rows existed but none were live-eligible (e.g. spoofed).
    reason = (
        "fixture_canary_not_eligible" if fixture_only is not None else "stale_canary"
    )
    return CanaryAuthSnapshot(
        valid=False,
        reason=reason,
        execution_id=None,
        execution_sha256=None,
        policy_identity_sha256=identity.policy_identity_sha256,
        cache_key=base_key,
        execution_mode="fixture" if fixture_only is not None else None,
        percent_authorization_eligible=False,
    )


def canary_authorization(db: Session) -> CanaryAuthSnapshot:
    identity = compute_policy_identity()
    lookup_key = _auth_cache_key(
        identity=identity,
        execution_id=None,
        execution_sha256=None,
        execution_mode="lookup",
        percent_authorization_eligible=False,
    )
    return resolve_canary_auth(
        db,
        cache_key=lookup_key,
        loader=_load_canary_auth,
    )


def evaluate_serve_eligibility(
    db: Session,
    request_id: int,
) -> ServeEligibility:
    s = app_config.settings
    breaker = _breaker_state(db)
    sticky = compute_sticky_bucket(
        salt=s.V2_PHASE7_ROLLOUT_SALT,
        request_id=request_id,
        rollout_percent=s.V2_PHASE7_ROLLOUT_PERCENT,
    )
    allowlisted = request_id in set(s.V2_PHASE7_REQUEST_ALLOWLIST)
    pointer = (
        db.query(PreviewServingPointerVersionRecord)
        .filter(
            PreviewServingPointerVersionRecord.request_id == request_id,
            PreviewServingPointerVersionRecord.is_current.is_(True),
        )
        .one_or_none()
    )
    pointer_available = pointer is not None

    if not (
        s.V2_PHASE7_ROLLOUT_ENABLED
        and s.V2_PHASE7_PROMOTE_ENABLED
        and s.V2_PHASE7_CONFIG_VALID
    ):
        return ServeEligibility(
            mode="legacy",
            reason="gates_invalid",
            allowlisted=allowlisted,
            percent_eligible=sticky.percent_eligible,
            canary_gate_valid=False,
            canary_gate_reason="gates_invalid",
            sticky_bucket=sticky.bucket,
            configured_percent=s.V2_PHASE7_ROLLOUT_PERCENT,
            current_pointer_available=pointer_available,
            breaker_state=breaker,
        )

    if allowlisted:
        return ServeEligibility(
            mode="pointer",
            reason="allowlisted",
            allowlisted=True,
            percent_eligible=sticky.percent_eligible,
            canary_gate_valid=True,
            canary_gate_reason=None,
            sticky_bucket=sticky.bucket,
            configured_percent=s.V2_PHASE7_ROLLOUT_PERCENT,
            current_pointer_available=pointer_available,
            breaker_state=breaker,
        )

    if not s.V2_PHASE7_PERCENT_SERVE_ENABLED or s.V2_PHASE7_ROLLOUT_PERCENT <= 0:
        return ServeEligibility(
            mode="legacy",
            reason="percent_serve_disabled",
            allowlisted=False,
            percent_eligible=False,
            canary_gate_valid=False,
            canary_gate_reason="percent_serve_disabled",
            sticky_bucket=sticky.bucket,
            configured_percent=s.V2_PHASE7_ROLLOUT_PERCENT,
            current_pointer_available=pointer_available,
            breaker_state=breaker,
        )

    auth = canary_authorization(db)
    if not auth.valid:
        if auth.reason == "fixture_canary_not_eligible":
            reason: ServePathReason = "fixture_canary_not_eligible"
        elif auth.reason == "missing_canary":
            reason = "percent_blocked_missing_canary"
        else:
            reason = "percent_blocked_stale_canary"
        return ServeEligibility(
            mode="legacy",
            reason=reason,
            allowlisted=False,
            percent_eligible=sticky.percent_eligible,
            canary_gate_valid=False,
            canary_gate_reason=auth.reason,
            sticky_bucket=sticky.bucket,
            configured_percent=s.V2_PHASE7_ROLLOUT_PERCENT,
            current_pointer_available=pointer_available,
            breaker_state=breaker,
        )

    if sticky.percent_eligible:
        return ServeEligibility(
            mode="pointer",
            reason="percent_eligible",
            allowlisted=False,
            percent_eligible=True,
            canary_gate_valid=True,
            canary_gate_reason=auth.reason,
            sticky_bucket=sticky.bucket,
            configured_percent=s.V2_PHASE7_ROLLOUT_PERCENT,
            current_pointer_available=pointer_available,
            breaker_state=breaker,
        )

    return ServeEligibility(
        mode="legacy",
        reason="percent_miss",
        allowlisted=False,
        percent_eligible=False,
        canary_gate_valid=True,
        canary_gate_reason=auth.reason,
        sticky_bucket=sticky.bucket,
        configured_percent=s.V2_PHASE7_ROLLOUT_PERCENT,
        current_pointer_available=pointer_available,
        breaker_state=breaker,
    )


def build_targeting_diagnostic(
    db: Session,
    request_id: int,
) -> TargetingDiagnosticView:
    elig = evaluate_serve_eligibility(db, request_id)
    payload = {
        "request_id": request_id,
        "sticky_bucket": elig.sticky_bucket,
        "configured_percent": elig.configured_percent,
        "allowlisted": elig.allowlisted,
        "percent_eligible": elig.percent_eligible,
        "canary_gate_valid": elig.canary_gate_valid,
        "serve_reason": elig.reason,
        "breaker_state": elig.breaker_state,
    }
    return TargetingDiagnosticView(
        request_id=request_id,
        normalized_request_id=str(request_id),
        sticky_bucket=elig.sticky_bucket,
        configured_percent=elig.configured_percent,
        allowlisted=elig.allowlisted,
        percent_serve_enabled=bool(
            app_config.settings.V2_PHASE7_PERCENT_SERVE_ENABLED
        ),
        percent_eligible=elig.percent_eligible,
        canary_gate_valid=elig.canary_gate_valid,
        canary_gate_reason=elig.canary_gate_reason,
        current_pointer_available=elig.current_pointer_available,
        breaker_state=elig.breaker_state,
        serve_pointer=elig.mode == "pointer",
        serve_legacy=elig.mode == "legacy",
        serve_reason=elig.reason,
        diagnostic_sha256=hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    )


__all__ = [
    "ServeEligibility",
    "build_targeting_diagnostic",
    "canary_authorization",
    "evaluate_serve_eligibility",
    "invalidate_canary_auth_cache",
]
