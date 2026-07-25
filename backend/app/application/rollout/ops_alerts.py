"""Phase 7E alert persistence, dedupe, storm control, and scan generation."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.application.rollout.authorization import require_permission
from app.application.rollout.breaker_service import BreakerService
from app.application.rollout.metric_snapshot import (
    canonical_sha256,
    compute_breaker_metric_snapshot_from_rows,
)
from app.core import config as app_config
from app.domain.models.rollout import (
    PreviewBreakerAutoRollbackClaimRecord,
    PreviewBreakerMetricSampleRecord,
    PreviewCircuitBreakerStateRecord,
    PreviewRolloutAlertEventRecord,
    PreviewRolloutAlertStatusEventRecord,
    PreviewRolloutAuditEventRecord,
)
from app.domain.schemas.breaker import GLOBAL_BREAKER_SCOPE_KEY
from app.domain.schemas.ops import (
    AlertAckBody,
    AlertStatusEventView,
    AlertView,
)
from app.domain.schemas.rollout import TrustedRolloutActor

_log = logging.getLogger("rollout.ops_alerts")

ALERT_SCAN_CAP = 20
BURST_WINDOW_SECONDS = 60
BURST_FAILURE_THRESHOLD = 3
SYSTEM_OPS_ACTOR = "system:phase7-ops"


class OpsAlertError(RuntimeError):
    def __init__(self, reason: str, *, stage: str = "alerts") -> None:
        super().__init__(reason)
        self.reason = reason
        self.stage = stage


def _alerts_enabled() -> bool:
    return bool(app_config.settings.V2_PHASE7_OPS_ALERTS_ENABLED)


def _dedupe_key(
    *,
    alert_class: str,
    scope_key: str,
    source_event_id: str,
    policy_revision: str,
) -> str:
    raw = f"{alert_class}|{scope_key}|{source_event_id}|{policy_revision}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _latest_status(db: Session, alert_id: int) -> str | None:
    row = (
        db.query(PreviewRolloutAlertStatusEventRecord)
        .filter(PreviewRolloutAlertStatusEventRecord.alert_id == alert_id)
        .order_by(PreviewRolloutAlertStatusEventRecord.id.desc())
        .first()
    )
    return None if row is None else str(row.status)


def _append_status(
    db: Session,
    *,
    alert_id: int,
    status: str,
    actor_id: str,
    reason: str,
    ticket_ref: str | None = None,
) -> PreviewRolloutAlertStatusEventRecord:
    payload = {
        "alert_id": alert_id,
        "status": status,
        "actor_id": actor_id,
        "reason": reason,
        "ticket_ref": ticket_ref,
    }
    row = PreviewRolloutAlertStatusEventRecord(
        alert_id=alert_id,
        status=status,
        actor_id=actor_id,
        reason=reason,
        ticket_ref=ticket_ref,
        created_at=datetime.utcnow(),
        event_sha256=canonical_sha256(
            {**payload, "nonce": f"{alert_id}:{status}:{actor_id}:{reason}"}
        ),
    )
    db.add(row)
    db.flush()
    return row


def record_alert(
    db: Session,
    *,
    alert_class: str,
    severity: str,
    scope_key: str,
    source_event_type: str,
    source_event_id: str,
    source_sha256: str,
    policy_revision: str,
    payload: dict[str, Any],
    initial_status: str = "recorded",
) -> PreviewRolloutAlertEventRecord | None:
    """Insert alert + initial status if dedupe allows; else return existing."""
    if not _alerts_enabled():
        return None
    if (
        not app_config.settings.V2_PHASE7_CONFIG_VALID
        and alert_class != "phase7_config_invalid"
    ):
        return None
    dedupe = _dedupe_key(
        alert_class=alert_class,
        scope_key=scope_key,
        source_event_id=source_event_id,
        policy_revision=policy_revision,
    )
    existing = (
        db.query(PreviewRolloutAlertEventRecord)
        .filter(PreviewRolloutAlertEventRecord.dedupe_key == dedupe)
        .one_or_none()
    )
    if existing is not None:
        return existing
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload_sha = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    alert_body = {
        "alert_class": alert_class,
        "severity": severity,
        "scope_key": scope_key,
        "source_event_type": source_event_type,
        "source_event_id": source_event_id,
        "source_sha256": source_sha256,
        "policy_revision": policy_revision,
        "payload_sha256": payload_sha,
        "dedupe_key": dedupe,
    }
    row = PreviewRolloutAlertEventRecord(
        alert_class=alert_class,
        severity=severity,
        scope_key=scope_key,
        source_event_type=source_event_type,
        source_event_id=source_event_id,
        source_sha256=source_sha256,
        policy_revision=policy_revision,
        payload_json=payload_json,
        payload_sha256=payload_sha,
        dedupe_key=dedupe,
        created_at=datetime.utcnow(),
        alert_sha256=canonical_sha256(alert_body),
    )
    db.add(row)
    db.flush()
    _append_status(
        db,
        alert_id=row.id,
        status=initial_status,
        actor_id=SYSTEM_OPS_ACTOR,
        reason=f"alert_{initial_status}",
    )
    _log.info(
        "phase7e alert recorded class=%s scope=%s source=%s",
        alert_class,
        scope_key,
        source_event_id,
        extra={
            "event": "phase7e_alert_recorded",
            "alert_class": alert_class,
            "scope_key": scope_key,
            "source_event_id": source_event_id,
        },
    )
    return row


def scan_and_persist_alerts(db: Session) -> int:
    """Scan authoritative 7A–7D records and persist up to ALERT_SCAN_CAP alerts."""
    if not _alerts_enabled():
        return 0
    created = 0
    candidates: list[dict[str, Any]] = []
    s = app_config.settings
    lookback = s.V2_PHASE7_OPS_ALERT_LOOKBACK_SECONDS
    cutoff = datetime.utcnow() - timedelta(seconds=lookback)
    policy_rev = s.V2_PHASE7_POLICY_REVISION

    if not s.V2_PHASE7_CONFIG_VALID:
        record_alert(
            db,
            alert_class="phase7_config_invalid",
            severity="high",
            scope_key=GLOBAL_BREAKER_SCOPE_KEY,
            source_event_type="config",
            source_event_id=f"config_invalid:{policy_rev}",
            source_sha256=canonical_sha256(
                {"config_valid": False, "policy_revision": policy_rev}
            ),
            policy_revision=policy_rev,
            payload={"config_valid": False},
        )
        return 1

    states = (
        db.query(PreviewCircuitBreakerStateRecord)
        .filter(
            PreviewCircuitBreakerStateRecord.scope_key == GLOBAL_BREAKER_SCOPE_KEY,
            PreviewCircuitBreakerStateRecord.created_at >= cutoff,
        )
        .order_by(PreviewCircuitBreakerStateRecord.id.asc())
        .all()
    )
    for st in states:
        if st.state == "open":
            cls, sev = "breaker_opened", "high"
        elif st.state == "half_open":
            cls, sev = "breaker_half_open", "medium"
        elif st.state == "closed":
            cls, sev = "breaker_closed", "info"
        else:
            continue
        candidates.append(
            {
                "alert_class": cls,
                "severity": sev,
                "scope_key": GLOBAL_BREAKER_SCOPE_KEY,
                "source_event_type": "breaker_state",
                "source_event_id": f"state:{st.id}",
                "source_sha256": st.state_sha256,
                "payload": {
                    "state_id": st.id,
                    "state": st.state,
                    "reason": st.reason,
                },
            }
        )

    breaker = BreakerService(db)
    policy_row = breaker.ensure_default_policy()
    policy = breaker._policy_from_row(policy_row)
    window_start = datetime.utcnow() - timedelta(seconds=policy.window_seconds)
    samples = (
        db.query(PreviewBreakerMetricSampleRecord)
        .filter(PreviewBreakerMetricSampleRecord.event_at >= window_start)
        .order_by(PreviewBreakerMetricSampleRecord.event_at.asc())
        .all()
    )
    snap = compute_breaker_metric_snapshot_from_rows(policy, samples)
    if "promotion_write_failure_rate" in snap.trip_reasons:
        candidates.append(
            {
                "alert_class": "promote_error_budget_burn",
                "severity": "high",
                "scope_key": GLOBAL_BREAKER_SCOPE_KEY,
                "source_event_type": "metric_snapshot",
                "source_event_id": f"promo_burn:{snap.snapshot_sha256[:16]}",
                "source_sha256": snap.snapshot_sha256,
                "payload": {
                    "rate": snap.promotion_write_failure_rate,
                    "threshold": policy.promotion_write_failure_threshold,
                    "samples": snap.promotion_write_samples,
                },
            }
        )
    if (
        "serving_health_failure_rate" in snap.trip_reasons
        or "consecutive_serving_health_failures" in snap.trip_reasons
    ):
        candidates.append(
            {
                "alert_class": "serving_health_budget_burn",
                "severity": "high",
                "scope_key": GLOBAL_BREAKER_SCOPE_KEY,
                "source_event_type": "metric_snapshot",
                "source_event_id": f"health_burn:{snap.snapshot_sha256[:16]}",
                "source_sha256": snap.snapshot_sha256,
                "payload": {
                    "rate": snap.serving_health_failure_rate,
                    "streak": snap.consecutive_serving_health_failures,
                    "threshold": policy.serving_health_failure_threshold,
                },
            }
        )

    burst_cut = datetime.utcnow() - timedelta(seconds=BURST_WINDOW_SECONDS)
    burst_fails = [
        s
        for s in samples
        if s.metric_class == "promotion_write_failure" and s.event_at >= burst_cut
    ]
    if len(burst_fails) >= BURST_FAILURE_THRESHOLD:
        src = f"promo_burst:{len(burst_fails)}:{burst_fails[-1].id}"
        candidates.append(
            {
                "alert_class": "promotion_write_failure_burst",
                "severity": "high",
                "scope_key": GLOBAL_BREAKER_SCOPE_KEY,
                "source_event_type": "metric_burst",
                "source_event_id": src,
                "source_sha256": canonical_sha256(
                    {"count": len(burst_fails), "last": burst_fails[-1].id}
                ),
                "payload": {"failure_count": len(burst_fails), "window_seconds": BURST_WINDOW_SECONDS},
            }
        )

    claims = (
        db.query(PreviewBreakerAutoRollbackClaimRecord)
        .filter(PreviewBreakerAutoRollbackClaimRecord.created_at >= cutoff)
        .order_by(PreviewBreakerAutoRollbackClaimRecord.id.asc())
        .all()
    )
    for claim in claims:
        if claim.status == "failed":
            candidates.append(
                {
                    "alert_class": "auto_rollback_failed",
                    "severity": "high",
                    "scope_key": f"request:{claim.request_id}",
                    "source_event_type": "auto_rollback_claim",
                    "source_event_id": f"claim:{claim.id}",
                    "source_sha256": claim.claim_sha256,
                    "payload": {
                        "request_id": claim.request_id,
                        "open_state_id": claim.open_state_id,
                        "status": claim.status,
                    },
                }
            )
        elif claim.status == "skipped":
            # Inspect claim sha / idempotency for no_verified_predecessor
            if "no_verified_predecessor" in (claim.idempotency_key or ""):
                candidates.append(
                    {
                        "alert_class": "auto_rollback_skipped_unhealthy_no_predecessor",
                        "severity": "medium",
                        "scope_key": f"request:{claim.request_id}",
                        "source_event_type": "auto_rollback_claim",
                        "source_event_id": f"claim:{claim.id}",
                        "source_sha256": claim.claim_sha256,
                        "payload": {
                            "request_id": claim.request_id,
                            "open_state_id": claim.open_state_id,
                        },
                    }
                )

    mut_audits = (
        db.query(PreviewRolloutAuditEventRecord)
        .filter(
            PreviewRolloutAuditEventRecord.created_at >= cutoff,
            PreviewRolloutAuditEventRecord.event_type == "history_mutation_denied",
        )
        .order_by(PreviewRolloutAuditEventRecord.id.asc())
        .all()
    )
    for audit in mut_audits:
        candidates.append(
            {
                "alert_class": "history_mutation_denied",
                "severity": "critical",
                "scope_key": GLOBAL_BREAKER_SCOPE_KEY,
                "source_event_type": "audit",
                "source_event_id": f"audit:{audit.id}",
                "source_sha256": audit.event_sha256,
                "payload": {"audit_id": audit.id, "reason": audit.reason},
            }
        )

    # Deterministic candidate order
    candidates.sort(
        key=lambda c: (
            c["alert_class"],
            c["scope_key"],
            c["source_event_id"],
        )
    )

    suppressed_excess = 0
    for cand in candidates:
        if created >= ALERT_SCAN_CAP:
            suppressed_excess += 1
            continue
        before = (
            db.query(PreviewRolloutAlertEventRecord)
            .filter(
                PreviewRolloutAlertEventRecord.dedupe_key
                == _dedupe_key(
                    alert_class=cand["alert_class"],
                    scope_key=cand["scope_key"],
                    source_event_id=cand["source_event_id"],
                    policy_revision=policy_rev,
                )
            )
            .one_or_none()
        )
        row = record_alert(
            db,
            alert_class=cand["alert_class"],
            severity=cand["severity"],
            scope_key=cand["scope_key"],
            source_event_type=cand["source_event_type"],
            source_event_id=cand["source_event_id"],
            source_sha256=cand["source_sha256"],
            policy_revision=policy_rev,
            payload=cand["payload"],
        )
        if row is not None and before is None:
            created += 1

    if suppressed_excess:
        record_alert(
            db,
            alert_class="alert_storm_suppressed",
            severity="medium",
            scope_key=GLOBAL_BREAKER_SCOPE_KEY,
            source_event_type="storm_control",
            source_event_id=f"storm:{policy_rev}:{snap.snapshot_sha256[:12]}",
            source_sha256=canonical_sha256(
                {"suppressed": suppressed_excess, "cap": ALERT_SCAN_CAP}
            ),
            policy_revision=policy_rev,
            payload={
                "suppressed_count": suppressed_excess,
                "cap": ALERT_SCAN_CAP,
            },
            initial_status="suppressed",
        )
        _log.warning(
            "phase7e alert storm suppressed excess=%s cap=%s",
            suppressed_excess,
            ALERT_SCAN_CAP,
            extra={
                "event": "phase7e_alert_storm_suppressed",
                "suppressed_count": suppressed_excess,
                "cap": ALERT_SCAN_CAP,
            },
        )
    return created


class OpsAlertService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _to_view(self, alert: PreviewRolloutAlertEventRecord) -> AlertView:
        statuses = (
            self._db.query(PreviewRolloutAlertStatusEventRecord)
            .filter(PreviewRolloutAlertStatusEventRecord.alert_id == alert.id)
            .order_by(PreviewRolloutAlertStatusEventRecord.id.asc())
            .all()
        )
        latest = statuses[-1].status if statuses else "recorded"
        return AlertView(
            alert_id=alert.id,
            alert_class=alert.alert_class,  # type: ignore[arg-type]
            severity=alert.severity,  # type: ignore[arg-type]
            scope_key=alert.scope_key,
            source_event_type=alert.source_event_type,
            source_event_id=alert.source_event_id,
            source_sha256=alert.source_sha256,
            policy_revision=alert.policy_revision,
            payload=json.loads(alert.payload_json),
            payload_sha256=alert.payload_sha256,
            dedupe_key=alert.dedupe_key,
            created_at=alert.created_at.isoformat() if alert.created_at else "",
            alert_sha256=alert.alert_sha256,
            latest_status=latest,  # type: ignore[arg-type]
            status_events=tuple(
                AlertStatusEventView(
                    status_event_id=s.id,
                    alert_id=s.alert_id,
                    status=s.status,  # type: ignore[arg-type]
                    actor_id=s.actor_id,
                    reason=s.reason,
                    ticket_ref=s.ticket_ref,
                    created_at=s.created_at.isoformat() if s.created_at else "",
                    event_sha256=s.event_sha256,
                )
                for s in statuses
            ),
        )

    def list_alerts(self, *, actor: TrustedRolloutActor) -> list[AlertView]:
        require_permission(actor, "read_alerts")
        if _alerts_enabled():
            scan_and_persist_alerts(self._db)
        rows = (
            self._db.query(PreviewRolloutAlertEventRecord)
            .order_by(PreviewRolloutAlertEventRecord.id.desc())
            .limit(200)
            .all()
        )
        return [self._to_view(r) for r in rows]

    def get_alert(self, *, actor: TrustedRolloutActor, alert_id: int) -> AlertView:
        require_permission(actor, "read_alerts")
        row = (
            self._db.query(PreviewRolloutAlertEventRecord)
            .filter(PreviewRolloutAlertEventRecord.id == alert_id)
            .one_or_none()
        )
        if row is None:
            raise OpsAlertError("alert_not_found", stage="lookup")
        return self._to_view(row)

    def acknowledge(
        self,
        *,
        actor: TrustedRolloutActor,
        alert_id: int,
        body: AlertAckBody,
        client_payload: dict[str, Any] | None = None,
    ) -> AlertView:
        from app.application.rollout.authorization import reject_client_supplied_roles

        if client_payload is not None:
            reject_client_supplied_roles(client_payload)
        require_permission(actor, "ack_alerts")
        row = (
            self._db.query(PreviewRolloutAlertEventRecord)
            .filter(PreviewRolloutAlertEventRecord.id == alert_id)
            .one_or_none()
        )
        if row is None:
            raise OpsAlertError("alert_not_found", stage="lookup")
        latest = _latest_status(self._db, alert_id)
        # Idempotent ack: same actor+reason+ticket returns existing
        prior_acks = (
            self._db.query(PreviewRolloutAlertStatusEventRecord)
            .filter(
                PreviewRolloutAlertStatusEventRecord.alert_id == alert_id,
                PreviewRolloutAlertStatusEventRecord.status == "acknowledged",
            )
            .order_by(PreviewRolloutAlertStatusEventRecord.id.desc())
            .all()
        )
        for prior in prior_acks:
            if (
                prior.actor_id == actor.actor_id
                and prior.reason == body.reason
                and (prior.ticket_ref or None) == (body.ticket_ref or None)
            ):
                return self._to_view(row)
            # Conflicting ack payload after an ack exists
            if prior.actor_id == actor.actor_id and (
                prior.reason != body.reason
                or (prior.ticket_ref or None) != (body.ticket_ref or None)
            ):
                raise OpsAlertError("ack_payload_conflict", stage="idempotency")
        if latest == "acknowledged" and prior_acks:
            # Different actor attempting ack after already acknowledged
            raise OpsAlertError("ack_payload_conflict", stage="idempotency")
        _append_status(
            self._db,
            alert_id=alert_id,
            status="acknowledged",
            actor_id=actor.actor_id,
            reason=body.reason,
            ticket_ref=body.ticket_ref,
        )
        return self._to_view(row)


__all__ = [
    "ALERT_SCAN_CAP",
    "OpsAlertError",
    "OpsAlertService",
    "record_alert",
    "scan_and_persist_alerts",
]
