"""Phase 7E read-only ops dashboard aggregations and runbook assist."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.application.rollout.authorization import require_permission
from app.application.rollout.breaker_service import BreakerService
from app.application.rollout.metric_snapshot import (
    canonical_sha256,
    compute_breaker_metric_snapshot_from_rows,
)
from app.application.rollout.ops_alerts import scan_and_persist_alerts
from app.core import config as app_config
from app.domain.models.rollout import (
    PreviewBreakerAutoRollbackClaimRecord,
    PreviewBreakerMetricSampleRecord,
    PreviewPromotionDecisionRecord,
    PreviewPromotionDecisionStatusEventRecord,
    PreviewRolloutAuditEventRecord,
    PreviewServingPointerVersionRecord,
    PreviewShadowEvaluationRecord,
)
from app.domain.schemas.breaker import GLOBAL_BREAKER_SCOPE_KEY
from app.domain.schemas.ops import (
    OpsBreakerBudgetView,
    OpsFlagsView,
    OpsOverviewView,
    OpsRequestDrilldownView,
    OpsRunbookView,
    RunbookActionView,
)
from app.domain.schemas.rollout import CircuitBreakerPolicyContract, TrustedRolloutActor


class OpsServiceError(RuntimeError):
    def __init__(self, reason: str, *, stage: str = "ops") -> None:
        super().__init__(reason)
        self.reason = reason
        self.stage = stage


class OpsService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _dashboard_enabled(self) -> bool:
        s = app_config.settings
        return bool(s.V2_PHASE7_CONFIG_VALID and s.V2_PHASE7_OPS_DASHBOARD_ENABLED)

    def _flags(self) -> OpsFlagsView:
        s = app_config.settings
        return OpsFlagsView(
            rollout_enabled=bool(s.V2_PHASE7_ROLLOUT_ENABLED),
            shadow_enabled=bool(s.V2_PHASE7_SHADOW_ENABLED),
            promote_enabled=bool(s.V2_PHASE7_PROMOTE_ENABLED),
            circuit_breaker_enabled=bool(s.V2_PHASE7_CIRCUIT_BREAKER_ENABLED),
            auto_rollback_enabled=bool(s.V2_PHASE7_AUTO_ROLLBACK_ENABLED),
            ops_dashboard_enabled=bool(s.V2_PHASE7_OPS_DASHBOARD_ENABLED),
            ops_alerts_enabled=bool(s.V2_PHASE7_OPS_ALERTS_ENABLED),
            config_valid=bool(s.V2_PHASE7_CONFIG_VALID),
            rollout_percent=int(s.V2_PHASE7_ROLLOUT_PERCENT),
            allowlist_size=len(s.V2_PHASE7_REQUEST_ALLOWLIST),
        )

    def _policy(self) -> CircuitBreakerPolicyContract:
        breaker = BreakerService(self._db)
        row = breaker.ensure_default_policy()
        return breaker._policy_from_row(row)

    def overview(self, *, actor: TrustedRolloutActor) -> OpsOverviewView:
        require_permission(actor, "read_ops")
        flags = self._flags()
        lookback = app_config.settings.V2_PHASE7_OPS_ALERT_LOOKBACK_SECONDS
        if not self._dashboard_enabled():
            body = {
                "disabled": True,
                "flags": flags.model_dump(mode="json"),
                "lookback_seconds": lookback,
                "counts": {},
            }
            return OpsOverviewView(
                disabled=True,
                flags=flags,
                lookback_seconds=lookback,
                overview_sha256=canonical_sha256(body),
            )

        if app_config.settings.V2_PHASE7_OPS_ALERTS_ENABLED:
            scan_and_persist_alerts(self._db)

        cutoff = datetime.utcnow() - timedelta(seconds=lookback)
        breaker = BreakerService(self._db)
        state_row = breaker.get_current_state_row()
        state = breaker.current_state() if breaker._breaker_enabled() else (
            state_row.state if state_row else None  # type: ignore[arg-type]
        )
        # Age is returned for operators but omitted from hash (volatile).
        age = None
        if state_row is not None:
            age = (datetime.utcnow() - state_row.created_at).total_seconds()

        applied_statuses = (
            self._db.query(PreviewPromotionDecisionStatusEventRecord)
            .filter(
                PreviewPromotionDecisionStatusEventRecord.status == "applied",
                PreviewPromotionDecisionStatusEventRecord.created_at >= cutoff,
            )
            .all()
        )
        decision_ids = {e.decision_id for e in applied_statuses}
        decisions = []
        if decision_ids:
            decisions = (
                self._db.query(PreviewPromotionDecisionRecord)
                .filter(PreviewPromotionDecisionRecord.id.in_(decision_ids))
                .all()
            )
        promo_n = sum(1 for d in decisions if d.decision_type == "promote")
        rb_n = sum(1 for d in decisions if d.decision_type == "rollback")

        claims = (
            self._db.query(PreviewBreakerAutoRollbackClaimRecord)
            .filter(PreviewBreakerAutoRollbackClaimRecord.created_at >= cutoff)
            .all()
        )
        shadow_n = (
            self._db.query(PreviewShadowEvaluationRecord)
            .filter(PreviewShadowEvaluationRecord.created_at >= cutoff)
            .count()
        )
        fallback_n = (
            self._db.query(PreviewRolloutAuditEventRecord)
            .filter(
                PreviewRolloutAuditEventRecord.event_type == "serving_fallback",
                PreviewRolloutAuditEventRecord.created_at >= cutoff,
            )
            .count()
        )
        health_fail_n = (
            self._db.query(PreviewBreakerMetricSampleRecord)
            .filter(
                PreviewBreakerMetricSampleRecord.metric_class
                == "serving_health_failure",
                PreviewBreakerMetricSampleRecord.event_at >= cutoff,
            )
            .count()
        )
        auto_applied = sum(1 for c in claims if c.status == "applied")
        auto_failed = sum(1 for c in claims if c.status == "failed")
        auto_skipped = sum(1 for c in claims if c.status == "skipped")
        canonical = {
            "disabled": False,
            "scope_key": GLOBAL_BREAKER_SCOPE_KEY,
            "breaker_state": state,
            "breaker_state_id": None if state_row is None else state_row.id,
            "policy_revision": app_config.settings.V2_PHASE7_POLICY_REVISION,
            "flags": flags.model_dump(mode="json"),
            "promotion_applied_count": promo_n,
            "rollback_applied_count": rb_n,
            "auto_rollback_applied_count": auto_applied,
            "auto_rollback_failed_count": auto_failed,
            "auto_rollback_skipped_count": auto_skipped,
            "shadow_evaluation_count": shadow_n,
            "serving_fallback_count": fallback_n,
            "serving_health_failure_count": health_fail_n,
            "lookback_seconds": lookback,
        }
        return OpsOverviewView(
            disabled=False,
            breaker_state=state,  # type: ignore[arg-type]
            breaker_state_id=None if state_row is None else state_row.id,
            policy_revision=app_config.settings.V2_PHASE7_POLICY_REVISION,
            breaker_state_age_seconds=age,
            flags=flags,
            promotion_applied_count=promo_n,
            rollback_applied_count=rb_n,
            auto_rollback_applied_count=auto_applied,
            auto_rollback_failed_count=auto_failed,
            auto_rollback_skipped_count=auto_skipped,
            shadow_evaluation_count=shadow_n,
            serving_fallback_count=fallback_n,
            serving_health_failure_count=health_fail_n,
            lookback_seconds=lookback,
            overview_sha256=canonical_sha256(canonical),
        )

    def breaker_budget(self, *, actor: TrustedRolloutActor) -> OpsBreakerBudgetView:
        require_permission(actor, "read_ops")
        if not self._dashboard_enabled():
            body = {"disabled": True, "scope_key": GLOBAL_BREAKER_SCOPE_KEY}
            return OpsBreakerBudgetView(
                disabled=True,
                budget_sha256=canonical_sha256(body),
            )
        policy = self._policy()
        window_start = datetime.utcnow() - timedelta(seconds=policy.window_seconds)
        samples = (
            self._db.query(PreviewBreakerMetricSampleRecord)
            .filter(PreviewBreakerMetricSampleRecord.event_at >= window_start)
            .order_by(PreviewBreakerMetricSampleRecord.event_at.asc())
            .all()
        )
        snap = compute_breaker_metric_snapshot_from_rows(policy, samples)
        breaker = BreakerService(self._db)
        state_row = breaker.get_current_state_row()
        state = breaker.current_state() if breaker._breaker_enabled() else None
        countdown = None
        if state_row is not None and state_row.state == "open":
            elapsed = (datetime.utcnow() - state_row.created_at).total_seconds()
            countdown = max(0.0, float(policy.open_duration_seconds) - elapsed)
        thresholds = {
            "promotion_write_failure_threshold": policy.promotion_write_failure_threshold,
            "serving_health_failure_threshold": policy.serving_health_failure_threshold,
            "consecutive_serving_health_failures": policy.consecutive_serving_health_failures,
            "min_samples": policy.min_samples,
            "window_seconds": policy.window_seconds,
            "p95_serving_latency_seconds": policy.p95_serving_latency_seconds,
            "p95_enabled": policy.p95_serving_latency_enabled,
            "open_duration_seconds": policy.open_duration_seconds,
            "half_open_probes": policy.half_open_probes,
        }
        # Hash omits live countdown (volatile); include open state id + duration.
        canonical = {
            "disabled": False,
            "scope_key": GLOBAL_BREAKER_SCOPE_KEY,
            "breaker_state": state,
            "policy_revision": app_config.settings.V2_PHASE7_POLICY_REVISION,
            "thresholds": thresholds,
            "metric_snapshot_sha256": snap.snapshot_sha256,
            "open_state_id": None if state_row is None else state_row.id,
            "open_duration_seconds": policy.open_duration_seconds,
        }
        return OpsBreakerBudgetView(
            disabled=False,
            breaker_state=state,  # type: ignore[arg-type]
            policy_revision=app_config.settings.V2_PHASE7_POLICY_REVISION,
            thresholds=thresholds,
            metric_snapshot=snap,
            half_open_countdown_seconds=countdown,
            budget_sha256=canonical_sha256(canonical),
        )

    def request_drilldown(
        self, *, actor: TrustedRolloutActor, request_id: int
    ) -> OpsRequestDrilldownView:
        require_permission(actor, "read_ops")
        if not self._dashboard_enabled():
            raise OpsServiceError("ops_dashboard_disabled", stage="flags")
        s = app_config.settings
        allowlisted = request_id in set(s.V2_PHASE7_REQUEST_ALLOWLIST)
        if s.V2_PHASE7_PROMOTE_ENABLED:
            if not allowlisted:
                raise OpsServiceError("not_found", stage="authz")
        else:
            # Promotion plane off: only admin may inspect historical requests.
            if "rollout_admin" not in actor.roles:
                raise OpsServiceError("not_found", stage="authz")

        pointers = (
            self._db.query(PreviewServingPointerVersionRecord)
            .filter(PreviewServingPointerVersionRecord.request_id == request_id)
            .order_by(PreviewServingPointerVersionRecord.pointer_version.asc())
            .all()
        )
        current = next((p for p in pointers if p.is_current), None)

        def ptr_dict(p: PreviewServingPointerVersionRecord) -> dict[str, Any]:
            return {
                "pointer_version": p.pointer_version,
                "target_kind": p.target_kind,
                "is_current": bool(p.is_current),
                "pointer_action": p.pointer_action,
                "candidate_revision_id": p.candidate_revision_id,
                "previous_pointer_version": p.previous_pointer_version,
                "actor_id": p.actor_id,
                "created_at": p.created_at.isoformat() if p.created_at else "",
            }

        decisions = (
            self._db.query(PreviewPromotionDecisionRecord)
            .filter(PreviewPromotionDecisionRecord.request_id == request_id)
            .order_by(PreviewPromotionDecisionRecord.id.asc())
            .all()
        )
        dec_views: list[dict[str, Any]] = []
        for d in decisions:
            statuses = (
                self._db.query(PreviewPromotionDecisionStatusEventRecord)
                .filter(
                    PreviewPromotionDecisionStatusEventRecord.decision_id == d.id
                )
                .order_by(PreviewPromotionDecisionStatusEventRecord.id.asc())
                .all()
            )
            dec_views.append(
                {
                    "decision_id": d.id,
                    "decision_type": d.decision_type,
                    "actor_id": d.actor_id,
                    "statuses": [st.status for st in statuses],
                }
            )
        shadows = (
            self._db.query(PreviewShadowEvaluationRecord)
            .filter(PreviewShadowEvaluationRecord.request_id == request_id)
            .order_by(PreviewShadowEvaluationRecord.id.asc())
            .all()
        )
        claims = (
            self._db.query(PreviewBreakerAutoRollbackClaimRecord)
            .filter(PreviewBreakerAutoRollbackClaimRecord.request_id == request_id)
            .order_by(PreviewBreakerAutoRollbackClaimRecord.id.asc())
            .all()
        )
        fallbacks = (
            self._db.query(PreviewRolloutAuditEventRecord)
            .filter(
                PreviewRolloutAuditEventRecord.request_id == request_id,
                PreviewRolloutAuditEventRecord.event_type == "serving_fallback",
            )
            .order_by(PreviewRolloutAuditEventRecord.id.asc())
            .all()
        )
        hist = tuple(ptr_dict(p) for p in pointers)
        current_d = None if current is None else ptr_dict(current)
        claim_views = tuple(
            {
                "claim_id": c.id,
                "open_state_id": c.open_state_id,
                "status": c.status,
                "expected_pointer_version": c.expected_pointer_version,
                "target_pointer_version": c.target_pointer_version,
            }
            for c in claims
        )
        shadow_views = tuple(
            {
                "evaluation_id": sh.id,
                "status": sh.result_status,
                "created_at": sh.created_at.isoformat() if sh.created_at else "",
            }
            for sh in shadows
        )
        fb_views = tuple(
            {
                "audit_id": a.id,
                "reason": a.reason,
                "created_at": a.created_at.isoformat() if a.created_at else "",
            }
            for a in fallbacks
        )
        canonical = {
            "request_id": request_id,
            "current_pointer": current_d,
            "pointer_history": list(hist),
            "decisions": dec_views,
            "shadow_evaluations": list(shadow_views),
            "auto_rollback_claims": list(claim_views),
            "fallback_audits": list(fb_views),
        }
        return OpsRequestDrilldownView(
            request_id=request_id,
            current_pointer=current_d,
            pointer_history=hist,
            decisions=tuple(dec_views),
            shadow_evaluations=shadow_views,
            auto_rollback_claims=claim_views,
            fallback_audits=fb_views,
            drilldown_sha256=canonical_sha256(canonical),
        )

    def runbook(self, *, actor: TrustedRolloutActor) -> OpsRunbookView:
        require_permission(actor, "read_ops")
        if not self._dashboard_enabled():
            body = {"disabled": True, "actions": []}
            return OpsRunbookView(
                disabled=True,
                runbook_sha256=canonical_sha256(body),
            )
        breaker = BreakerService(self._db)
        state = breaker.current_state() if breaker._breaker_enabled() else "disabled"
        actions: list[RunbookActionView] = []
        notes: list[str] = []
        if state == "open":
            notes.append(
                "Human promote/rollback apply is frozen while breaker is open."
            )
            actions.append(
                RunbookActionView(
                    recommendation="Inspect current breaker state and history",
                    method="GET",
                    path="/api/admin/rollout/breaker/state",
                    required_role="rollout_viewer",
                )
            )
            actions.append(
                RunbookActionView(
                    recommendation=(
                        "After open duration, evaluate to transition toward half_open"
                    ),
                    method="POST",
                    path="/api/admin/rollout/breaker/evaluate",
                    required_role="rollout_admin",
                )
            )
            actions.append(
                RunbookActionView(
                    recommendation="Review auto-rollback claims for the open event",
                    method="GET",
                    path="/api/admin/rollout/breaker/auto-rollbacks",
                    required_role="rollout_viewer",
                )
            )
        elif state == "half_open":
            notes.append(
                "Synthetic filesystem probes are used for half-open recovery; "
                "human apply remains blocked."
            )
            actions.append(
                RunbookActionView(
                    recommendation="Run evaluate to count half-open probes",
                    method="POST",
                    path="/api/admin/rollout/breaker/evaluate",
                    required_role="rollout_admin",
                )
            )
        elif not app_config.settings.V2_PHASE7_CONFIG_VALID:
            notes.append("Phase 7 config is invalid; flags fail closed.")
            actions.append(
                RunbookActionView(
                    recommendation="Review current rollout policy diagnostic",
                    method="GET",
                    path="/api/admin/rollout/policy/current",
                    required_role="rollout_viewer",
                )
            )
        else:
            notes.append("No urgent breaker action; continue normal SoD workflows.")
            actions.append(
                RunbookActionView(
                    recommendation="Optional breaker evaluate tick",
                    method="POST",
                    path="/api/admin/rollout/breaker/evaluate",
                    required_role="rollout_admin",
                )
            )
        canonical = {
            "disabled": False,
            "breaker_state": state,
            "actions": [a.model_dump(mode="json") for a in actions],
            "notes": notes,
        }
        return OpsRunbookView(
            disabled=False,
            breaker_state=state,  # type: ignore[arg-type]
            actions=tuple(actions),
            notes=tuple(notes),
            runbook_sha256=canonical_sha256(canonical),
        )


__all__ = ["OpsService", "OpsServiceError"]
