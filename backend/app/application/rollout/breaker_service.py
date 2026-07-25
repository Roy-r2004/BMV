"""Phase 7D global circuit-breaker evaluation and state transitions."""
from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session, load_only

from app.application.rollout.audit import append_audit_event
from app.application.rollout.authorization import require_permission
from app.application.rollout.breaker_contract import (
    DEFAULT_BREAKER_POLICY,
    breaker_policy_sha256,
)
from app.application.rollout.breaker_metrics import append_metric_sample
from app.core import config as app_config
from app.domain.models.preview_candidate import CandidateRevisionRecord
from app.domain.models.rollout import (
    PreviewBreakerMetricSampleRecord,
    PreviewCircuitBreakerPolicyRecord,
    PreviewCircuitBreakerStateRecord,
    PreviewServingPointerVersionRecord,
)
from app.domain.schemas.breaker import (
    GLOBAL_BREAKER_SCOPE_KEY,
    SYSTEM_BREAKER_ACTOR_ID,
    BreakerEvaluationResult,
    BreakerMetricSampleView,
    BreakerMetricSnapshot,
    BreakerStateView,
)
from app.domain.schemas.rollout import (
    BreakerState,
    CircuitBreakerPolicyContract,
    TrustedRolloutActor,
)


class BreakerServiceError(RuntimeError):
    def __init__(self, reason: str, *, stage: str = "breaker") -> None:
        super().__init__(reason)
        self.reason = reason
        self.stage = stage


def _sha(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    # Nearest-rank deterministic p95
    rank = max(1, math.ceil(0.95 * len(ordered)))
    return float(ordered[rank - 1])


class BreakerService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _flags_ok(self) -> bool:
        s = app_config.settings
        return bool(s.V2_PHASE7_CONFIG_VALID and s.V2_PHASE7_ROLLOUT_ENABLED)

    def _breaker_enabled(self) -> bool:
        return self._flags_ok() and bool(
            app_config.settings.V2_PHASE7_CIRCUIT_BREAKER_ENABLED
        )

    def ensure_default_policy(
        self, *, actor_id: str = SYSTEM_BREAKER_ACTOR_ID
    ) -> PreviewCircuitBreakerPolicyRecord:
        rev = app_config.settings.V2_PHASE7_POLICY_REVISION
        existing = (
            self._db.query(PreviewCircuitBreakerPolicyRecord)
            .filter(PreviewCircuitBreakerPolicyRecord.policy_revision == rev)
            .one_or_none()
        )
        if existing is not None:
            return existing
        policy = DEFAULT_BREAKER_POLICY.model_copy(update={"scope": "global"})
        row = PreviewCircuitBreakerPolicyRecord(
            policy_revision=rev,
            policy_json=policy.model_dump_json(),
            policy_sha256=breaker_policy_sha256(policy),
            created_at=datetime.utcnow(),
            created_actor_id=actor_id,
        )
        self._db.add(row)
        self._db.flush()
        return row

    def get_current_state_row(
        self,
    ) -> PreviewCircuitBreakerStateRecord | None:
        return (
            self._db.query(PreviewCircuitBreakerStateRecord)
            .filter(
                PreviewCircuitBreakerStateRecord.scope_key == GLOBAL_BREAKER_SCOPE_KEY
            )
            .order_by(PreviewCircuitBreakerStateRecord.id.desc())
            .first()
        )

    def current_state(self) -> BreakerState:
        if not self._breaker_enabled():
            return "disabled"
        row = self.get_current_state_row()
        if row is None:
            return "disabled"
        return row.state  # type: ignore[return-value]

    def _policy_from_row(
        self, row: PreviewCircuitBreakerPolicyRecord
    ) -> CircuitBreakerPolicyContract:
        return CircuitBreakerPolicyContract.model_validate_json(row.policy_json)

    def _append_state(
        self,
        *,
        policy: PreviewCircuitBreakerPolicyRecord,
        state: BreakerState,
        metric_class: str,
        reason: str,
    ) -> PreviewCircuitBreakerStateRecord:
        payload = {
            "scope_key": GLOBAL_BREAKER_SCOPE_KEY,
            "state": state,
            "metric_class": metric_class,
            "reason": reason,
            "policy_id": policy.id,
            "created_at": datetime.utcnow().isoformat(),
            "nonce": str(uuid.uuid4()),
        }
        row = PreviewCircuitBreakerStateRecord(
            policy_id=policy.id,
            scope_key=GLOBAL_BREAKER_SCOPE_KEY,
            state=state,
            metric_class=metric_class,
            reason=reason,
            created_at=datetime.utcnow(),
            state_sha256=_sha(payload),
        )
        self._db.add(row)
        self._db.flush()
        return row

    def _state_view(
        self, row: PreviewCircuitBreakerStateRecord, *, is_current: bool
    ) -> BreakerStateView:
        policy = (
            self._db.query(PreviewCircuitBreakerPolicyRecord)
            .filter(PreviewCircuitBreakerPolicyRecord.id == row.policy_id)
            .one()
        )
        return BreakerStateView(
            state_id=row.id,
            scope_key=row.scope_key,
            state=row.state,  # type: ignore[arg-type]
            metric_class=row.metric_class,
            reason=row.reason,
            policy_revision=policy.policy_revision,
            policy_id=policy.id,
            created_at=row.created_at.isoformat() if row.created_at else "",
            state_sha256=row.state_sha256,
            is_current=is_current,
        )

    def get_state_view(self, *, actor: TrustedRolloutActor) -> BreakerStateView:
        require_permission(actor, "read_breaker")
        policy = self.ensure_default_policy(actor_id=actor.actor_id)
        row = self.get_current_state_row()
        if row is None:
            # Logical disabled without snapshot until first evaluate/enable.
            synthetic = self._append_state(
                policy=policy,
                state="disabled",
                metric_class="operator_rejection",
                reason="initial_disabled",
            )
            return self._state_view(synthetic, is_current=True)
        return self._state_view(row, is_current=True)

    def history(self, *, actor: TrustedRolloutActor) -> list[BreakerStateView]:
        require_permission(actor, "read_breaker")
        rows = (
            self._db.query(PreviewCircuitBreakerStateRecord)
            .filter(
                PreviewCircuitBreakerStateRecord.scope_key == GLOBAL_BREAKER_SCOPE_KEY
            )
            .order_by(PreviewCircuitBreakerStateRecord.id.asc())
            .all()
        )
        if not rows:
            return []
        latest_id = rows[-1].id
        return [
            self._state_view(r, is_current=(r.id == latest_id)) for r in rows
        ]

    def list_samples(
        self, *, actor: TrustedRolloutActor, limit: int = 100
    ) -> list[BreakerMetricSampleView]:
        require_permission(actor, "read_breaker")
        rows = (
            self._db.query(PreviewBreakerMetricSampleRecord)
            .order_by(PreviewBreakerMetricSampleRecord.id.desc())
            .limit(max(1, min(limit, 500)))
            .all()
        )
        return [
            BreakerMetricSampleView(
                sample_id=r.id,
                event_at=r.event_at.isoformat() if r.event_at else "",
                metric_class=r.metric_class,  # type: ignore[arg-type]
                outcome=r.outcome,  # type: ignore[arg-type]
                request_id=r.request_id,
                decision_id=r.decision_id,
                pointer_version=r.pointer_version,
                duration_ms=r.duration_ms,
                policy_revision=r.policy_revision,
                source_event_hash=r.source_event_hash,
                sample_sha256=r.sample_sha256,
            )
            for r in rows
        ]

    def _compute_snapshot(
        self, policy: CircuitBreakerPolicyContract
    ) -> BreakerMetricSnapshot:
        window_start = datetime.utcnow() - timedelta(seconds=policy.window_seconds)
        samples = (
            self._db.query(PreviewBreakerMetricSampleRecord)
            .filter(PreviewBreakerMetricSampleRecord.event_at >= window_start)
            .order_by(PreviewBreakerMetricSampleRecord.event_at.asc())
            .all()
        )
        promo = [
            s
            for s in samples
            if s.metric_class
            in ("promotion_write_success", "promotion_write_failure")
        ]
        promo_fail = [s for s in promo if s.metric_class == "promotion_write_failure"]
        health = [
            s
            for s in samples
            if s.metric_class
            in ("serving_health_success", "serving_health_failure")
        ]
        health_fail = [
            s for s in health if s.metric_class == "serving_health_failure"
        ]
        latencies = [
            float(s.duration_ms) / 1000.0
            for s in samples
            if s.metric_class == "serving_latency" and s.duration_ms is not None
        ]
        # Consecutive serving-health failures from newest backward among health samples
        streak = 0
        for s in reversed(health):
            if s.metric_class == "serving_health_failure":
                streak += 1
            else:
                break
        promo_rate = (len(promo_fail) / len(promo)) if promo else 0.0
        health_rate = (len(health_fail) / len(health)) if health else 0.0
        p95 = _p95(latencies) if policy.p95_serving_latency_enabled else None
        trips: list[str] = []
        if (
            len(promo) >= policy.min_samples
            and promo_rate >= policy.promotion_write_failure_threshold
        ):
            trips.append("promotion_write_failure_rate")
        if (
            len(health) >= policy.min_samples
            and health_rate >= policy.serving_health_failure_threshold
        ):
            trips.append("serving_health_failure_rate")
        if streak >= policy.consecutive_serving_health_failures:
            trips.append("consecutive_serving_health_failures")
        if (
            policy.p95_serving_latency_enabled
            and p95 is not None
            and len(latencies) >= policy.min_samples
            and p95 >= policy.p95_serving_latency_seconds
        ):
            trips.append("p95_serving_latency")
        body = {
            "window_seconds": policy.window_seconds,
            "min_samples": policy.min_samples,
            "promotion_write_samples": len(promo),
            "promotion_write_failures": len(promo_fail),
            "promotion_write_failure_rate": promo_rate,
            "serving_health_samples": len(health),
            "serving_health_failures": len(health_fail),
            "serving_health_failure_rate": health_rate,
            "consecutive_serving_health_failures": streak,
            "latency_samples": len(latencies),
            "p95_serving_latency_seconds": p95,
            "p95_enabled": policy.p95_serving_latency_enabled,
            "trip_reasons": trips,
        }
        return BreakerMetricSnapshot(
            **body,
            snapshot_sha256=_sha(body),
        )

    def _synthetic_probe_ok(self) -> bool:
        """Filesystem/lineage probe for half-open recovery (no HTTP/browser)."""
        currents = (
            self._db.query(PreviewServingPointerVersionRecord)
            .filter(PreviewServingPointerVersionRecord.is_current.is_(True))
            .limit(app_config.settings.V2_PHASE7_BREAKER_EVAL_MAX_REQUESTS)
            .all()
        )
        if not currents:
            return True
        root = app_config.settings.PREVIEW_CANDIDATES_DIR.resolve(strict=False)
        passed = 0
        checked = 0
        for ptr in currents:
            if ptr.target_kind not in ("v2_candidate", "rollback"):
                continue
            if not ptr.candidate_revision_id:
                continue
            checked += 1
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
                continue
            workspace = (root / cand.workspace_relpath).resolve(strict=False)
            try:
                workspace.relative_to(root)
            except ValueError:
                continue
            dist = workspace / "dist"
            if dist.is_dir() and (dist / "index.html").is_file():
                manifest = cand.file_manifest_sha256 or cand.upstream_manifest_sha256
                if (
                    ptr.candidate_manifest_sha256 is None
                    or manifest == ptr.candidate_manifest_sha256
                ):
                    passed += 1
        if checked == 0:
            return True
        # All checked v2 currents must pass filesystem/lineage probe.
        return passed == checked

    def evaluate(
        self,
        *,
        actor: TrustedRolloutActor,
        reason: str | None = None,
        run_auto_rollback_if_opened: bool = True,
    ) -> BreakerEvaluationResult:
        require_permission(actor, "evaluate_breaker")
        if not self._breaker_enabled():
            raise BreakerServiceError("breaker_disabled", stage="flags")

        policy_row = self.ensure_default_policy(actor_id=actor.actor_id)
        policy = self._policy_from_row(policy_row)
        current_row = self.get_current_state_row()
        current: BreakerState = (
            "disabled" if current_row is None else current_row.state  # type: ignore[assignment]
        )
        snapshot = self._compute_snapshot(policy)
        next_state: BreakerState = current
        metric_class = "serving_health_failure"
        transition_reason = reason or "evaluate"

        if current == "disabled":
            next_state = "closed"
            metric_class = "operator_rejection"
            transition_reason = "enable_on_evaluate"
        elif current == "closed":
            if snapshot.trip_reasons:
                next_state = "open"
                metric_class = snapshot.trip_reasons[0]
                transition_reason = ",".join(snapshot.trip_reasons)
        elif current == "open":
            assert current_row is not None
            elapsed = (datetime.utcnow() - current_row.created_at).total_seconds()
            if elapsed >= policy.open_duration_seconds:
                next_state = "half_open"
                metric_class = "serving_health_success"
                transition_reason = "open_duration_elapsed"
        elif current == "half_open":
            assert current_row is not None
            if self._synthetic_probe_ok():
                probe_token = str(uuid.uuid4())
                append_metric_sample(
                    self._db,
                    metric_class="serving_health_success",
                    outcome="success",
                    policy_revision=policy_row.policy_revision,
                    source_event_id=f"half_open_probe:{current_row.id}:{probe_token}",
                    source_event_hash=_sha(
                        {
                            "probe": "half_open",
                            "state_id": current_row.id,
                            "token": probe_token,
                            "actor": actor.actor_id,
                        }
                    ),
                    metadata={"half_open_probe": True, "state_id": current_row.id},
                )
                probes = (
                    self._db.query(PreviewBreakerMetricSampleRecord)
                    .filter(
                        PreviewBreakerMetricSampleRecord.metric_class
                        == "serving_health_success",
                        PreviewBreakerMetricSampleRecord.source_event_id.like(
                            f"half_open_probe:{current_row.id}:%"
                        ),
                    )
                    .count()
                )
                if probes >= policy.half_open_probes:
                    next_state = "closed"
                    metric_class = "serving_health_success"
                    transition_reason = "half_open_probes_passed"
            else:
                append_metric_sample(
                    self._db,
                    metric_class="serving_health_failure",
                    outcome="failure",
                    policy_revision=policy_row.policy_revision,
                    source_event_id=(
                        f"half_open_probe_fail:{current_row.id}:{uuid.uuid4()}"
                    ),
                    source_event_hash=_sha(
                        {
                            "probe": "half_open_fail",
                            "state_id": current_row.id,
                            "actor": actor.actor_id,
                            "at": datetime.utcnow().isoformat(),
                        }
                    ),
                    metadata={"half_open_probe": True, "failed": True},
                )
                next_state = "open"
                metric_class = "serving_health_failure"
                transition_reason = "half_open_probe_failed"

        transitioned = next_state != current
        open_state_id = None
        new_row = current_row
        if transitioned:
            new_row = self._append_state(
                policy=policy_row,
                state=next_state,
                metric_class=metric_class,
                reason=transition_reason,
            )
            audit_map = {
                "open": "breaker_opened",
                "half_open": "breaker_half_open",
                "closed": "breaker_closed",
                "disabled": "breaker_disabled",
            }
            append_audit_event(
                self._db,
                request_id=None,
                event_type=audit_map.get(next_state, "breaker_evaluated"),
                actor_id=actor.actor_id,
                actor_role=actor.roles[0],
                policy_revision=policy_row.policy_revision,
                reason=transition_reason,
                metadata={
                    "scope_key": GLOBAL_BREAKER_SCOPE_KEY,
                    "from_state": current,
                    "to_state": next_state,
                    "state_id": new_row.id,
                    "metric_snapshot_sha256": snapshot.snapshot_sha256,
                    "trip_reasons": list(snapshot.trip_reasons),
                },
            )
            if next_state == "open":
                open_state_id = new_row.id

        eval_payload = {
            "current_state": current,
            "next_state": next_state,
            "transitioned": transitioned,
            "snapshot": snapshot.snapshot_sha256,
            "policy_revision": policy_row.policy_revision,
        }
        result = BreakerEvaluationResult(
            current_state=current,
            next_state=next_state,
            transitioned=transitioned,
            policy_revision=policy_row.policy_revision,
            metric_snapshot=snapshot,
            evaluation_sha256=_sha(eval_payload),
            open_state_id=open_state_id,
        )

        if (
            transitioned
            and next_state == "open"
            and run_auto_rollback_if_opened
            and open_state_id is not None
        ):
            from app.application.rollout.auto_rollback import AutoRollbackService

            AutoRollbackService(self._db).run_for_open_event(
                actor=actor,
                open_state_id=open_state_id,
                metric_snapshot_sha256=snapshot.snapshot_sha256,
            )
        return result

    def manual_open(
        self,
        *,
        actor: TrustedRolloutActor,
        reason: str,
        ticket_ref: str,
        run_auto_rollback: bool,
    ) -> BreakerEvaluationResult:
        require_permission(actor, "open_breaker")
        if not self._breaker_enabled():
            raise BreakerServiceError("breaker_disabled", stage="flags")
        policy_row = self.ensure_default_policy(actor_id=actor.actor_id)
        current = self.current_state()
        if current == "open":
            row = self.get_current_state_row()
            snap = self._compute_snapshot(self._policy_from_row(policy_row))
            return BreakerEvaluationResult(
                current_state="open",
                next_state="open",
                transitioned=False,
                policy_revision=policy_row.policy_revision,
                metric_snapshot=snap,
                evaluation_sha256=_sha({"already_open": True, "state_id": row.id if row else 0}),
                open_state_id=row.id if row else None,
            )
        new_row = self._append_state(
            policy=policy_row,
            state="open",
            metric_class="operator_rejection",
            reason=f"manual_open:{reason}",
        )
        snap = self._compute_snapshot(self._policy_from_row(policy_row))
        append_audit_event(
            self._db,
            request_id=None,
            event_type="breaker_opened",
            actor_id=actor.actor_id,
            actor_role=actor.roles[0],
            policy_revision=policy_row.policy_revision,
            reason=reason,
            ticket_ref=ticket_ref,
            metadata={
                "manual": True,
                "state_id": new_row.id,
                "run_auto_rollback": run_auto_rollback,
                "metric_snapshot_sha256": snap.snapshot_sha256,
            },
        )
        if run_auto_rollback:
            from app.application.rollout.auto_rollback import AutoRollbackService

            AutoRollbackService(self._db).run_for_open_event(
                actor=actor,
                open_state_id=new_row.id,
                metric_snapshot_sha256=snap.snapshot_sha256,
            )
        return BreakerEvaluationResult(
            current_state=current,
            next_state="open",
            transitioned=True,
            policy_revision=policy_row.policy_revision,
            metric_snapshot=snap,
            evaluation_sha256=_sha({"manual_open": new_row.id}),
            open_state_id=new_row.id,
        )

    def manual_close(
        self, *, actor: TrustedRolloutActor, reason: str, ticket_ref: str
    ) -> BreakerEvaluationResult:
        """Manual close transitions open → half_open (no force-close)."""
        require_permission(actor, "close_breaker")
        if not self._breaker_enabled():
            raise BreakerServiceError("breaker_disabled", stage="flags")
        policy_row = self.ensure_default_policy(actor_id=actor.actor_id)
        current = self.current_state()
        if current not in ("open", "half_open"):
            raise BreakerServiceError("not_open", stage="validation")
        next_state: BreakerState = "half_open" if current == "open" else current
        transitioned = next_state != current
        new_row = None
        if transitioned:
            new_row = self._append_state(
                policy=policy_row,
                state="half_open",
                metric_class="operator_rejection",
                reason=f"manual_close_to_half_open:{reason}",
            )
            append_audit_event(
                self._db,
                request_id=None,
                event_type="breaker_half_open",
                actor_id=actor.actor_id,
                actor_role=actor.roles[0],
                policy_revision=policy_row.policy_revision,
                reason=reason,
                ticket_ref=ticket_ref,
                metadata={"manual_close": True, "state_id": new_row.id},
            )
        snap = self._compute_snapshot(self._policy_from_row(policy_row))
        return BreakerEvaluationResult(
            current_state=current,
            next_state=next_state,
            transitioned=transitioned,
            policy_revision=policy_row.policy_revision,
            metric_snapshot=snap,
            evaluation_sha256=_sha({"manual_close": True, "to": next_state}),
        )

    def disable(
        self, *, actor: TrustedRolloutActor, reason: str, ticket_ref: str
    ) -> BreakerEvaluationResult:
        require_permission(actor, "disable_breaker")
        policy_row = self.ensure_default_policy(actor_id=actor.actor_id)
        current = self.current_state()
        new_row = self._append_state(
            policy=policy_row,
            state="disabled",
            metric_class="operator_rejection",
            reason=f"manual_disable:{reason}",
        )
        append_audit_event(
            self._db,
            request_id=None,
            event_type="breaker_disabled",
            actor_id=actor.actor_id,
            actor_role=actor.roles[0],
            policy_revision=policy_row.policy_revision,
            reason=reason,
            ticket_ref=ticket_ref,
            metadata={"state_id": new_row.id},
        )
        snap = self._compute_snapshot(self._policy_from_row(policy_row))
        return BreakerEvaluationResult(
            current_state=current,
            next_state="disabled",
            transitioned=True,
            policy_revision=policy_row.policy_revision,
            metric_snapshot=snap,
            evaluation_sha256=_sha({"disable": new_row.id}),
        )


def human_apply_blocked_by_breaker(db: Session) -> bool:
    """True when human promote/rollback apply must fail closed."""
    svc = BreakerService(db)
    if not svc._breaker_enabled():
        return False
    return svc.current_state() in ("open", "half_open")


__all__ = [
    "BreakerService",
    "BreakerServiceError",
    "human_apply_blocked_by_breaker",
]
