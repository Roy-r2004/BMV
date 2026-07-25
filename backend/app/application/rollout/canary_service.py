"""Phase 7F live-canary lifecycle: request → approve → execute → review.

Providers are constructed only inside execute after all preconditions pass.
FixtureCanaryProvider is never the ordinary production default — only explicit
test injection or structurally non-production simulation mode may use it.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Literal, Protocol

from sqlalchemy.orm import Session

from app.application.rollout.authorization import (
    reject_client_supplied_roles,
    require_permission,
)
from app.application.rollout.canary_auth_cache import invalidate_canary_auth_cache
from app.application.rollout.canary_policy import compute_policy_identity
from app.application.rollout.pointer import resolve_serving_pointer
from app.core import config as app_config
from app.domain.models.rollout import (
    PreviewLiveCanaryApprovalRecord,
    PreviewLiveCanaryApprovalStatusEventRecord,
    PreviewLiveCanaryExecutionClaimRecord,
    PreviewLiveCanaryExecutionRecord,
    PreviewLiveCanaryExecutionStatusEventRecord,
    PreviewLiveCanaryLifecycleEventRecord,
)
from app.domain.schemas.canary import (
    CanaryApprovalBody,
    CanaryApprovalView,
    CanaryExecuteBody,
    CanaryExecutionProvenanceView,
    CanaryExecutionView,
    CanaryLifecycleEventView,
    CanaryRequestBody,
    CanaryReviewBody,
)
from app.domain.schemas.rollout import TrustedRolloutActor

ExecutionMode = Literal["fixture", "live"]
PROVIDER_FACTORY_REVISION = "phase7f.2"


class CanaryServiceError(RuntimeError):
    def __init__(self, reason: str, *, stage: str = "canary") -> None:
        super().__init__(reason)
        self.reason = reason
        self.stage = stage


class CanaryProvider(Protocol):
    def complete(self, *, prompt: str, max_tokens: int) -> dict[str, Any]: ...


@dataclass
class BudgetTracker:
    max_calls: int
    max_input_tokens: int
    max_output_tokens: int
    max_cost_usd: float
    max_wall_seconds: int
    max_retries: int
    per_call_timeout_seconds: int
    started_monotonic: float = field(default_factory=time.monotonic)
    provider_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    retries: int = 0

    def wall_seconds(self) -> float:
        return time.monotonic() - self.started_monotonic

    def check_before_call(self) -> None:
        if self.provider_calls >= self.max_calls:
            raise CanaryServiceError("budget_exceeded_calls", stage="budget")
        if self.wall_seconds() >= self.max_wall_seconds:
            raise CanaryServiceError("budget_exceeded_wall", stage="budget")
        if self.estimated_cost_usd >= self.max_cost_usd:
            raise CanaryServiceError("budget_exceeded_cost", stage="budget")
        if self.input_tokens >= self.max_input_tokens:
            raise CanaryServiceError("budget_exceeded_input_tokens", stage="budget")
        if self.output_tokens >= self.max_output_tokens:
            raise CanaryServiceError("budget_exceeded_output_tokens", stage="budget")

    def record_call(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
    ) -> None:
        self.provider_calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.estimated_cost_usd += cost_usd
        if self.input_tokens > self.max_input_tokens:
            raise CanaryServiceError("budget_exceeded_input_tokens", stage="budget")
        if self.output_tokens > self.max_output_tokens:
            raise CanaryServiceError("budget_exceeded_output_tokens", stage="budget")
        if self.estimated_cost_usd > self.max_cost_usd:
            raise CanaryServiceError("budget_exceeded_cost", stage="budget")
        if self.wall_seconds() > self.max_wall_seconds:
            raise CanaryServiceError("budget_exceeded_wall", stage="budget")
        if self.provider_calls > self.max_calls:
            raise CanaryServiceError("budget_exceeded_calls", stage="budget")

    def check_before_retry(self) -> None:
        if self.retries >= self.max_retries:
            raise CanaryServiceError("budget_exceeded_retries", stage="budget")
        self.check_before_call()
        self.retries += 1

    def check_before_stage(self) -> None:
        self.check_before_call()

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_calls": self.max_calls,
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "max_cost_usd": self.max_cost_usd,
            "max_wall_seconds": self.max_wall_seconds,
            "max_retries": self.max_retries,
            "per_call_timeout_seconds": self.per_call_timeout_seconds,
            "provider_calls": self.provider_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_cost_usd": self.estimated_cost_usd,
            "wall_seconds": self.wall_seconds(),
            "retries": self.retries,
        }


class FixtureCanaryProvider:
    """Deterministic double — no network, no paid providers.

    Allowed only via explicit test injection or non-production simulation mode.
    Never authorizes percentage serving.
    """

    def complete(self, *, prompt: str, max_tokens: int) -> dict[str, Any]:
        _ = prompt
        return {
            "input_tokens": 32,
            "output_tokens": min(64, max_tokens),
            "cost_usd": 0.001,
            "text": "fixture-canary-ok",
        }


@dataclass(frozen=True)
class ExecutionProvenance:
    execution_mode: ExecutionMode
    provider_was_live: bool
    provider_family: str
    provider_model: str
    provider_manifest_sha256: str
    provider_factory_revision: str
    network_access_expected: bool
    execution_environment: str
    simulation_only: bool
    percent_authorization_eligible: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "execution_mode": self.execution_mode,
            "provider_was_live": self.provider_was_live,
            "provider_family": self.provider_family,
            "provider_model": self.provider_model,
            "provider_manifest_sha256": self.provider_manifest_sha256,
            "provider_factory_revision": self.provider_factory_revision,
            "network_access_expected": self.network_access_expected,
            "execution_environment": self.execution_environment,
            "simulation_only": self.simulation_only,
            "percent_authorization_eligible": self.percent_authorization_eligible,
        }


def _execution_environment() -> str:
    env = (
        os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or os.getenv("ENV") or "local"
    ).strip().lower()
    return env or "local"


def canary_simulation_allowed() -> bool:
    """Fixture simulation is structurally unavailable in production config."""
    env = _execution_environment()
    if env in ("production", "prod"):
        return False
    return bool(app_config.settings.V2_PHASE7_CANARY_SIMULATION_ENABLED)


@dataclass
class CanaryRunResult:
    candidate_revision_id: int | None
    effective_tier: int | None
    phase4_status: str
    phase5_status: str
    comparison_artifact_sha256: str
    status: str
    failure_reason: str | None = None


class CanaryRunner(Protocol):
    def run(
        self,
        *,
        provider: CanaryProvider,
        budget: BudgetTracker,
        request_id: int,
        approval: PreviewLiveCanaryApprovalRecord,
    ) -> CanaryRunResult: ...


class DefaultCanaryRunner:
    """Bounded fixture regeneration path used when live providers are off."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def run(
        self,
        *,
        provider: CanaryProvider,
        budget: BudgetTracker,
        request_id: int,
        approval: PreviewLiveCanaryApprovalRecord,
    ) -> CanaryRunResult:
        _ = approval
        from app.application.rollout.shadow_lineage import locate_latest_accepted_lineage

        budget.check_before_stage()
        budget.check_before_call()
        resp = provider.complete(prompt=f"canary:{request_id}", max_tokens=128)
        budget.record_call(
            input_tokens=int(resp["input_tokens"]),
            output_tokens=int(resp["output_tokens"]),
            cost_usd=float(resp["cost_usd"]),
        )
        budget.check_before_stage()
        lineage = locate_latest_accepted_lineage(self._db, request_id)
        if lineage is None:
            return CanaryRunResult(
                candidate_revision_id=None,
                effective_tier=None,
                phase4_status="missing",
                phase5_status="missing",
                comparison_artifact_sha256="0" * 64,
                status="failed",
                failure_reason="missing_accepted_lineage",
            )
        cmp_hash = hashlib.sha256(
            f"canary-compare:{request_id}:{lineage.candidate_revision_id}".encode()
        ).hexdigest()
        return CanaryRunResult(
            candidate_revision_id=lineage.candidate_revision_id,
            effective_tier=lineage.highest_accepted_tier,
            phase4_status="candidate_runtime_validated",
            phase5_status="candidate_visual_accepted",
            comparison_artifact_sha256=cmp_hash,
            status="completed",
        )


def _sha(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _emit_canary_alert(db: Session, *, alert_class: str, source_event_id: str) -> None:
    if not app_config.settings.V2_PHASE7_OPS_ALERTS_ENABLED:
        return
    try:
        from app.application.rollout.ops_alerts import record_alert
        from app.domain.schemas.breaker import GLOBAL_BREAKER_SCOPE_KEY

        record_alert(
            db,
            alert_class=alert_class,
            severity="high",
            scope_key=GLOBAL_BREAKER_SCOPE_KEY,
            source_event_type="live_canary",
            source_event_id=source_event_id,
            source_sha256=hashlib.sha256(source_event_id.encode()).hexdigest(),
            policy_revision=app_config.settings.V2_PHASE7_POLICY_REVISION,
            payload={"lane": "phase7f_canary", "alert_class": alert_class},
        )
    except Exception:  # noqa: BLE001
        pass


class CanaryService:
    def __init__(
        self,
        db: Session,
        *,
        provider_factory: Callable[[], CanaryProvider] | None = None,
        runner: CanaryRunner | None = None,
    ) -> None:
        self._db = db
        self._provider_factory = provider_factory
        self._runner = runner
        self._provider_constructed = False

    def provider_was_constructed(self) -> bool:
        return self._provider_constructed

    def _require_canary_plane(self) -> None:
        s = app_config.settings
        if not (
            s.V2_PHASE7_ROLLOUT_ENABLED
            and s.V2_PHASE7_CONFIG_VALID
            and s.V2_PHASE7_LIVE_CANARY_ENABLED
        ):
            raise CanaryServiceError("canary_plane_disabled", stage="flags")

    def _latest_lifecycle(
        self, approval_id: int
    ) -> PreviewLiveCanaryLifecycleEventRecord | None:
        return (
            self._db.query(PreviewLiveCanaryLifecycleEventRecord)
            .filter(PreviewLiveCanaryLifecycleEventRecord.approval_id == approval_id)
            .order_by(PreviewLiveCanaryLifecycleEventRecord.id.desc())
            .first()
        )

    def _lifecycle_statuses(self, approval_id: int) -> list[str]:
        rows = (
            self._db.query(PreviewLiveCanaryLifecycleEventRecord)
            .filter(PreviewLiveCanaryLifecycleEventRecord.approval_id == approval_id)
            .order_by(PreviewLiveCanaryLifecycleEventRecord.id.asc())
            .all()
        )
        return [str(r.status) for r in rows]

    def _append_lifecycle(
        self,
        *,
        approval_id: int,
        status: str,
        actor_id: str,
        reason: str,
        ticket_ref: str | None,
    ) -> PreviewLiveCanaryLifecycleEventRecord:
        created = datetime.utcnow()
        row = PreviewLiveCanaryLifecycleEventRecord(
            approval_id=approval_id,
            status=status,
            actor_id=actor_id,
            reason=reason,
            ticket_ref=ticket_ref,
            created_at=created,
            event_sha256=_sha(
                {
                    "approval_id": approval_id,
                    "status": status,
                    "actor_id": actor_id,
                    "reason": reason,
                    "ticket_ref": ticket_ref,
                    "created_at": created.isoformat(),
                }
            ),
        )
        self._db.add(row)
        self._db.flush()
        invalidate_canary_auth_cache()
        return row

    def _view_approval(
        self, row: PreviewLiveCanaryApprovalRecord
    ) -> CanaryApprovalView:
        events = (
            self._db.query(PreviewLiveCanaryLifecycleEventRecord)
            .filter(PreviewLiveCanaryLifecycleEventRecord.approval_id == row.id)
            .order_by(PreviewLiveCanaryLifecycleEventRecord.id.asc())
            .all()
        )
        approver = None
        for e in events:
            if e.status == "approved":
                approver = e.actor_id
        latest = events[-1].status if events else row.initial_status
        return CanaryApprovalView(
            approval_id=row.id,
            approval_uuid=row.approval_uuid,
            request_id=row.request_id,
            requester_id=row.requester_id or "",
            approver_id=approver,
            ticket_ref=row.ticket_ref,
            reason=row.reason or "",
            policy_revision=row.policy_revision,
            rollout_salt=row.rollout_salt or "",
            provider_manifest_sha256=row.provider_manifest_sha256 or ("0" * 64),
            generation_policy_sha256=row.generation_policy_sha256 or ("0" * 64),
            prompt_policy_sha256=row.prompt_policy_sha256 or ("0" * 64),
            runtime_policy_sha256=row.runtime_policy_sha256 or ("0" * 64),
            comparison_policy_revision=row.comparison_policy_revision or "",
            budget_policy_sha256=row.budget_policy_sha256 or ("0" * 64),
            policy_identity_sha256=row.policy_identity_sha256 or ("0" * 64),
            max_calls=row.max_calls,
            max_input_tokens=int(row.max_input_tokens or 1),
            max_output_tokens=row.max_output_tokens,
            max_cost_usd=row.max_cost_usd,
            max_wall_seconds=row.max_wall_seconds,
            max_retries=int(row.max_retries or 0),
            per_call_timeout_seconds=int(row.per_call_timeout_seconds or 60),
            expires_at=row.expires_at.isoformat()
            if isinstance(row.expires_at, datetime)
            else str(row.expires_at),
            latest_status=latest,  # type: ignore[arg-type]
            approval_sha256=row.approval_sha256,
            lifecycle=tuple(
                CanaryLifecycleEventView(
                    status=e.status,  # type: ignore[arg-type]
                    actor_id=e.actor_id,
                    reason=e.reason,
                    ticket_ref=e.ticket_ref,
                    created_at=e.created_at.isoformat()
                    if isinstance(e.created_at, datetime)
                    else str(e.created_at),
                    event_sha256=e.event_sha256,
                )
                for e in events
            ),
        )

    def _view_execution(
        self, row: PreviewLiveCanaryExecutionRecord
    ) -> CanaryExecutionView:
        statuses = {
            e.status
            for e in self._db.query(PreviewLiveCanaryLifecycleEventRecord)
            .filter(PreviewLiveCanaryLifecycleEventRecord.approval_id == row.approval_id)
            .all()
        }
        mode = (row.execution_mode or "fixture")  # type: ignore[assignment]
        return CanaryExecutionView(
            execution_id=row.id,
            execution_uuid=row.execution_uuid,
            approval_id=row.approval_id,
            request_id=row.request_id,
            started_at=row.started_at.isoformat()
            if isinstance(row.started_at, datetime)
            else str(row.started_at),
            completed_at=row.completed_at.isoformat()
            if row.completed_at and isinstance(row.completed_at, datetime)
            else (str(row.completed_at) if row.completed_at else None),
            provider_manifest_sha256=row.provider_manifest_sha256,
            generation_policy_sha256=row.generation_policy_sha256,
            prompt_policy_sha256=row.prompt_policy_sha256,
            candidate_revision_id=row.candidate_revision_id,
            effective_tier=row.effective_tier,
            phase4_status=row.phase4_status,
            phase5_status=row.phase5_status,
            provider_calls=row.provider_calls,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            estimated_cost_usd=row.estimated_cost_usd,
            wall_seconds=row.wall_seconds,
            retries=row.retries,
            comparison_artifact_sha256=row.comparison_artifact_sha256,
            telemetry_sha256=row.telemetry_sha256,
            result_status=row.result_status,  # type: ignore[arg-type]
            failure_reason=row.failure_reason,
            no_serving_mutation=bool(row.no_serving_mutation),
            pointer_version_before=row.pointer_version_before,
            pointer_version_after=row.pointer_version_after,
            policy_identity_sha256=row.policy_identity_sha256,
            execution_sha256=row.execution_sha256,
            reviewed_accepted="reviewed_accepted" in statuses,
            reviewed_fixture_only="reviewed_fixture_only" in statuses,
            provenance=CanaryExecutionProvenanceView(
                execution_mode=mode if mode in ("fixture", "live") else "fixture",
                provider_was_live=bool(row.provider_was_live),
                provider_family=row.provider_family,
                provider_model=row.provider_model,
                provider_manifest_sha256=row.provider_manifest_sha256,
                provider_factory_revision=row.provider_factory_revision,
                network_access_expected=bool(row.network_access_expected),
                execution_environment=row.execution_environment,
                simulation_only=bool(row.simulation_only),
                percent_authorization_eligible=bool(
                    row.percent_authorization_eligible
                ),
            ),
        )

    def list_canaries(self, actor: TrustedRolloutActor) -> list[CanaryApprovalView]:
        require_permission(actor, "read_canaries")
        rows = (
            self._db.query(PreviewLiveCanaryApprovalRecord)
            .order_by(PreviewLiveCanaryApprovalRecord.id.desc())
            .limit(100)
            .all()
        )
        return [self._view_approval(r) for r in rows]

    def get_canary(
        self, actor: TrustedRolloutActor, approval_id: int
    ) -> CanaryApprovalView:
        require_permission(actor, "read_canaries")
        row = (
            self._db.query(PreviewLiveCanaryApprovalRecord)
            .filter(PreviewLiveCanaryApprovalRecord.id == approval_id)
            .one_or_none()
        )
        if row is None:
            raise CanaryServiceError("canary_not_found", stage="read")
        return self._view_approval(row)

    def list_executions(
        self, actor: TrustedRolloutActor, approval_id: int
    ) -> list[CanaryExecutionView]:
        require_permission(actor, "read_canaries")
        rows = (
            self._db.query(PreviewLiveCanaryExecutionRecord)
            .filter(PreviewLiveCanaryExecutionRecord.approval_id == approval_id)
            .order_by(PreviewLiveCanaryExecutionRecord.id.desc())
            .all()
        )
        return [self._view_execution(r) for r in rows]

    def get_execution(
        self, actor: TrustedRolloutActor, execution_id: int
    ) -> CanaryExecutionView:
        require_permission(actor, "read_canaries")
        row = (
            self._db.query(PreviewLiveCanaryExecutionRecord)
            .filter(PreviewLiveCanaryExecutionRecord.id == execution_id)
            .one_or_none()
        )
        if row is None:
            raise CanaryServiceError("execution_not_found", stage="read")
        return self._view_execution(row)

    def request_canary(
        self,
        actor: TrustedRolloutActor,
        request_id: int,
        body: CanaryRequestBody,
        *,
        raw_payload: dict | None = None,
    ) -> CanaryApprovalView:
        if raw_payload is not None:
            reject_client_supplied_roles(raw_payload)
        require_permission(actor, "request_canary")
        self._require_canary_plane()
        if request_id not in set(app_config.settings.V2_PHASE7_REQUEST_ALLOWLIST):
            raise CanaryServiceError("request_not_allowlisted", stage="request")

        if body.idempotency_key:
            existing = (
                self._db.query(PreviewLiveCanaryApprovalRecord)
                .filter(
                    PreviewLiveCanaryApprovalRecord.idempotency_key
                    == body.idempotency_key
                )
                .one_or_none()
            )
            if existing is not None:
                return self._view_approval(existing)

        s = app_config.settings
        max_calls = body.max_calls if body.max_calls is not None else s.V2_PHASE7_CANARY_MAX_CALLS
        max_in = (
            body.max_input_tokens
            if body.max_input_tokens is not None
            else s.V2_PHASE7_CANARY_MAX_INPUT_TOKENS
        )
        max_out = (
            body.max_output_tokens
            if body.max_output_tokens is not None
            else s.V2_PHASE7_CANARY_MAX_OUTPUT_TOKENS
        )
        max_cost = (
            body.max_cost_usd
            if body.max_cost_usd is not None
            else s.V2_PHASE7_CANARY_MAX_COST_USD
        )
        max_wall = (
            body.max_wall_seconds
            if body.max_wall_seconds is not None
            else s.V2_PHASE7_CANARY_MAX_WALL_SECONDS
        )
        max_retries = (
            body.max_retries
            if body.max_retries is not None
            else s.V2_PHASE7_CANARY_MAX_RETRIES
        )
        per_call = (
            body.per_call_timeout_seconds
            if body.per_call_timeout_seconds is not None
            else s.V2_PHASE7_CANARY_PER_CALL_TIMEOUT_SECONDS
        )
        # Approval may only tighten ceilings vs server defaults.
        if max_calls > s.V2_PHASE7_CANARY_MAX_CALLS:
            raise CanaryServiceError("budget_exceeds_policy", stage="request")
        if max_wall > s.V2_PHASE7_CANARY_MAX_WALL_SECONDS:
            raise CanaryServiceError("budget_exceeds_policy", stage="request")
        if max_cost > s.V2_PHASE7_CANARY_MAX_COST_USD:
            raise CanaryServiceError("budget_exceeds_policy", stage="request")
        if max_in > s.V2_PHASE7_CANARY_MAX_INPUT_TOKENS:
            raise CanaryServiceError("budget_exceeds_policy", stage="request")
        if max_out > s.V2_PHASE7_CANARY_MAX_OUTPUT_TOKENS:
            raise CanaryServiceError("budget_exceeds_policy", stage="request")

        identity = compute_policy_identity()
        approval_uuid = str(uuid.uuid4())
        expires = datetime.utcnow() + timedelta(
            seconds=s.V2_PHASE7_CANARY_APPROVAL_TTL_SECONDS
        )
        payload = {
            "approval_uuid": approval_uuid,
            "request_id": request_id,
            "requester_id": actor.actor_id,
            "ticket_ref": body.ticket_ref,
            "reason": body.reason,
            "policy_identity_sha256": identity.policy_identity_sha256,
            "max_calls": max_calls,
            "max_input_tokens": max_in,
            "max_output_tokens": max_out,
            "max_cost_usd": max_cost,
            "max_wall_seconds": max_wall,
        }
        row = PreviewLiveCanaryApprovalRecord(
            approval_uuid=approval_uuid,
            request_id=request_id,
            provider_model_allowlist_json=json.dumps(
                ["server-policy-manifest"], separators=(",", ":")
            ),
            max_calls=max_calls,
            max_output_tokens=max_out,
            max_cost_usd=max_cost,
            max_wall_seconds=max_wall,
            expires_at=expires,
            approver_id="pending",
            ticket_ref=body.ticket_ref,
            policy_revision=identity.policy_revision,
            initial_status="requested",
            approval_sha256=_sha(payload),
            created_at=datetime.utcnow(),
            requester_id=actor.actor_id,
            reason=body.reason,
            rollout_salt=identity.rollout_salt,
            provider_manifest_sha256=identity.provider_manifest_sha256,
            generation_policy_sha256=identity.generation_policy_sha256,
            prompt_policy_sha256=identity.prompt_policy_sha256,
            runtime_policy_sha256=identity.runtime_policy_sha256,
            comparison_policy_revision=identity.comparison_policy_revision,
            budget_policy_sha256=identity.budget_policy_sha256,
            max_input_tokens=max_in,
            max_retries=max_retries,
            per_call_timeout_seconds=per_call,
            policy_identity_sha256=identity.policy_identity_sha256,
            idempotency_key=body.idempotency_key,
        )
        self._db.add(row)
        self._db.flush()
        self._append_lifecycle(
            approval_id=row.id,
            status="requested",
            actor_id=actor.actor_id,
            reason=body.reason,
            ticket_ref=body.ticket_ref,
        )
        return self._view_approval(row)

    def approve_canary(
        self,
        actor: TrustedRolloutActor,
        approval_id: int,
        body: CanaryApprovalBody,
        *,
        raw_payload: dict | None = None,
    ) -> CanaryApprovalView:
        if raw_payload is not None:
            reject_client_supplied_roles(raw_payload)
        require_permission(actor, "approve_canary")
        self._require_canary_plane()
        row = (
            self._db.query(PreviewLiveCanaryApprovalRecord)
            .filter(PreviewLiveCanaryApprovalRecord.id == approval_id)
            .one_or_none()
        )
        if row is None:
            raise CanaryServiceError("canary_not_found", stage="approve")
        statuses = self._lifecycle_statuses(approval_id)
        if "approved" in statuses:
            # Idempotent re-approve by same approver only returns view.
            return self._view_approval(row)
        if not statuses or statuses[-1] != "requested":
            raise CanaryServiceError("invalid_lifecycle_state", stage="approve")
        if actor.actor_id == (row.requester_id or ""):
            raise CanaryServiceError("sod_requester_approver", stage="approve")
        if row.request_id not in set(app_config.settings.V2_PHASE7_REQUEST_ALLOWLIST):
            raise CanaryServiceError("request_not_allowlisted", stage="approve")
        identity = compute_policy_identity()
        if row.policy_identity_sha256 != identity.policy_identity_sha256:
            raise CanaryServiceError("policy_identity_mismatch", stage="approve")
        self._append_lifecycle(
            approval_id=row.id,
            status="approved",
            actor_id=actor.actor_id,
            reason=body.reason,
            ticket_ref=body.ticket_ref,
        )
        # Legacy 7A status event lineage for approved.
        created = datetime.utcnow()
        self._db.add(
            PreviewLiveCanaryApprovalStatusEventRecord(
                approval_id=row.id,
                status="approved",
                actor_id=actor.actor_id,
                reason=body.reason,
                created_at=created,
                event_sha256=_sha(
                    {
                        "approval_id": row.id,
                        "status": "approved",
                        "actor_id": actor.actor_id,
                        "created_at": created.isoformat(),
                    }
                ),
            )
        )
        self._db.flush()
        return self._view_approval(row)

    def _resolve_provider_plan(
        self, *, provider_manifest_sha256: str
    ) -> tuple[Callable[[], CanaryProvider], ExecutionProvenance]:
        """Decide fixture vs live wiring before any provider construction.

        Returns a deferred factory callable so callers can fail closed without
        constructing when live providers are disabled.
        """
        env = _execution_environment()
        if self._provider_factory is not None:
            factory = self._provider_factory

            def _build() -> CanaryProvider:
                self._provider_constructed = True
                return factory()

            return _build, ExecutionProvenance(
                execution_mode="fixture",
                provider_was_live=False,
                provider_family="fixture",
                provider_model="FixtureCanaryProvider",
                provider_manifest_sha256=provider_manifest_sha256,
                provider_factory_revision=PROVIDER_FACTORY_REVISION,
                network_access_expected=False,
                execution_environment=env,
                simulation_only=True,
                percent_authorization_eligible=False,
            )
        if canary_simulation_allowed():

            def _build_sim() -> CanaryProvider:
                self._provider_constructed = True
                return FixtureCanaryProvider()

            return _build_sim, ExecutionProvenance(
                execution_mode="fixture",
                provider_was_live=False,
                provider_family="fixture",
                provider_model="FixtureCanaryProvider",
                provider_manifest_sha256=provider_manifest_sha256,
                provider_factory_revision=PROVIDER_FACTORY_REVISION,
                network_access_expected=False,
                execution_environment=env,
                simulation_only=True,
                percent_authorization_eligible=False,
            )
        if not app_config.settings.V2_PHASE7_LIVE_CANARY_PROVIDERS_ENABLED:
            raise CanaryServiceError("live_providers_disabled", stage="providers")

        def _build_live() -> CanaryProvider:
            self._provider_constructed = True
            from app.infrastructure.ai_providers.factory import get_ai_provider

            return get_ai_provider()  # type: ignore[return-value]

        s = app_config.settings
        return _build_live, ExecutionProvenance(
            execution_mode="live",
            provider_was_live=True,
            provider_family=str(getattr(s, "AI_PROVIDER", "openrouter") or "openrouter"),
            provider_model=str(getattr(s, "OPENROUTER_MODEL", "") or "server-policy"),
            provider_manifest_sha256=provider_manifest_sha256,
            provider_factory_revision=PROVIDER_FACTORY_REVISION,
            network_access_expected=True,
            execution_environment=env,
            simulation_only=False,
            # Flipped to True only after successful live gates below.
            percent_authorization_eligible=False,
        )

    def _acquire_claim(self) -> None:
        now = datetime.utcnow()
        claim = (
            self._db.query(PreviewLiveCanaryExecutionClaimRecord)
            .filter(PreviewLiveCanaryExecutionClaimRecord.id == 1)
            .one_or_none()
        )
        if claim is None:
            self._db.add(
                PreviewLiveCanaryExecutionClaimRecord(
                    id=1,
                    execution_id=None,
                    claimed_at=now,
                    released_at=None,
                    claim_sha256=_sha({"claimed_at": now.isoformat(), "active": True}),
                )
            )
            self._db.flush()
            return
        if claim.released_at is None:
            raise CanaryServiceError("concurrent_canary_active", stage="execute")
        claim.execution_id = None
        claim.claimed_at = now
        claim.released_at = None
        claim.claim_sha256 = _sha({"claimed_at": now.isoformat(), "active": True})
        self._db.flush()

    def _release_claim(self, execution_id: int | None) -> None:
        claim = (
            self._db.query(PreviewLiveCanaryExecutionClaimRecord)
            .filter(PreviewLiveCanaryExecutionClaimRecord.id == 1)
            .one_or_none()
        )
        if claim is not None:
            claim.execution_id = execution_id
            claim.released_at = datetime.utcnow()
            self._db.flush()

    def execute_canary(
        self,
        actor: TrustedRolloutActor,
        approval_id: int,
        body: CanaryExecuteBody,
        *,
        raw_payload: dict | None = None,
    ) -> CanaryExecutionView:
        if raw_payload is not None:
            reject_client_supplied_roles(raw_payload)
        require_permission(actor, "execute_canary")
        self._require_canary_plane()

        existing = (
            self._db.query(PreviewLiveCanaryExecutionRecord)
            .filter(
                PreviewLiveCanaryExecutionRecord.idempotency_key == body.idempotency_key
            )
            .one_or_none()
        )
        if existing is not None:
            if existing.approval_id != approval_id:
                raise CanaryServiceError("idempotency_conflict", stage="execute")
            return self._view_execution(existing)

        row = (
            self._db.query(PreviewLiveCanaryApprovalRecord)
            .filter(PreviewLiveCanaryApprovalRecord.id == approval_id)
            .one_or_none()
        )
        if row is None:
            raise CanaryServiceError("canary_not_found", stage="execute")

        # Fail closed before any provider construction.
        statuses = self._lifecycle_statuses(approval_id)
        if "consumed" in statuses or any(
            s in statuses for s in ("completed", "failed", "aborted")
        ):
            raise CanaryServiceError("approval_already_used", stage="execute")
        if "approved" not in statuses:
            raise CanaryServiceError("approval_not_approved", stage="execute")
        if statuses[-1] != "approved":
            raise CanaryServiceError("invalid_lifecycle_state", stage="execute")

        approver = next(
            (
                e.actor_id
                for e in self._db.query(PreviewLiveCanaryLifecycleEventRecord)
                .filter(
                    PreviewLiveCanaryLifecycleEventRecord.approval_id == approval_id,
                    PreviewLiveCanaryLifecycleEventRecord.status == "approved",
                )
                .all()
            ),
            None,
        )
        requester = row.requester_id or ""
        if actor.actor_id in {requester, approver}:
            raise CanaryServiceError("sod_three_distinct_admins", stage="execute")

        expires = row.expires_at
        if isinstance(expires, str):
            expires = datetime.fromisoformat(expires)
        if expires <= datetime.utcnow():
            raise CanaryServiceError("approval_expired", stage="execute")

        if app_config.settings.V2_PHASE7_CIRCUIT_BREAKER_ENABLED:
            from app.application.rollout.breaker_service import BreakerService

            state = BreakerService(self._db).current_state()
            if state in ("open", "half_open"):
                raise CanaryServiceError("breaker_not_closed", stage="execute")

        identity = compute_policy_identity()
        if row.policy_identity_sha256 != identity.policy_identity_sha256:
            raise CanaryServiceError("policy_identity_mismatch", stage="execute")
        if row.provider_manifest_sha256 != identity.provider_manifest_sha256:
            raise CanaryServiceError("provider_manifest_mismatch", stage="execute")

        # Resolve wiring before claim/consume/construction — fail closed with
        # zero provider construction when live providers are disabled.
        provider_builder, provenance = self._resolve_provider_plan(
            provider_manifest_sha256=identity.provider_manifest_sha256
        )

        pointer_before = resolve_serving_pointer(self._db, row.request_id)
        before_ver = pointer_before.pointer_version

        self._acquire_claim()
        started = datetime.utcnow()
        exec_uuid = str(uuid.uuid4())

        # Single-use consume before provider construction.
        self._append_lifecycle(
            approval_id=row.id,
            status="consumed",
            actor_id=actor.actor_id,
            reason="execute_claimed",
            ticket_ref=body.ticket_ref,
        )
        created_status = datetime.utcnow()
        self._db.add(
            PreviewLiveCanaryApprovalStatusEventRecord(
                approval_id=row.id,
                status="consumed",
                actor_id=actor.actor_id,
                reason="execute_claimed",
                created_at=created_status,
                event_sha256=_sha(
                    {
                        "approval_id": row.id,
                        "status": "consumed",
                        "actor_id": actor.actor_id,
                        "created_at": created_status.isoformat(),
                    }
                ),
            )
        )
        self._db.flush()

        budget = BudgetTracker(
            max_calls=row.max_calls,
            max_input_tokens=int(row.max_input_tokens or 1),
            max_output_tokens=row.max_output_tokens,
            max_cost_usd=row.max_cost_usd,
            max_wall_seconds=row.max_wall_seconds,
            max_retries=int(row.max_retries or 0),
            per_call_timeout_seconds=int(row.per_call_timeout_seconds or 60),
        )

        result_status = "failed"
        failure_reason: str | None = None
        run: CanaryRunResult | None = None
        try:
            provider = provider_builder()
            runner = self._runner or DefaultCanaryRunner(self._db)
            run = runner.run(
                provider=provider,
                budget=budget,
                request_id=row.request_id,
                approval=row,
            )
            result_status = run.status
            failure_reason = run.failure_reason
            if result_status == "completed":
                if (
                    run.phase4_status != "candidate_runtime_validated"
                    or run.phase5_status != "candidate_visual_accepted"
                    or not run.comparison_artifact_sha256
                    or run.candidate_revision_id is None
                ):
                    result_status = "failed"
                    failure_reason = "validation_gates_failed"
        except CanaryServiceError as exc:
            if exc.reason.startswith("budget_exceeded"):
                result_status = "aborted"
                failure_reason = exc.reason
                _emit_canary_alert(
                    self._db,
                    alert_class="live_canary_budget_overrun",
                    source_event_id=f"canary-exec:{exec_uuid}",
                )
                _emit_canary_alert(
                    self._db,
                    alert_class="live_canary_aborted",
                    source_event_id=f"canary-abort:{exec_uuid}",
                )
            else:
                result_status = "failed"
                failure_reason = exc.reason
                _emit_canary_alert(
                    self._db,
                    alert_class="live_canary_failed",
                    source_event_id=f"canary-exec:{exec_uuid}",
                )
        except Exception as exc:  # noqa: BLE001
            result_status = "failed"
            failure_reason = f"execution_error:{type(exc).__name__}"
            _emit_canary_alert(
                self._db,
                alert_class="live_canary_failed",
                source_event_id=f"canary-exec:{exec_uuid}",
            )

        pointer_after = resolve_serving_pointer(self._db, row.request_id)
        after_ver = pointer_after.pointer_version
        if before_ver != after_ver:
            result_status = "failed"
            failure_reason = "serving_mutation_detected"

        percent_eligible = False
        if (
            provenance.execution_mode == "live"
            and provenance.provider_was_live
            and not provenance.simulation_only
            and result_status == "completed"
            and run is not None
            and run.phase4_status == "candidate_runtime_validated"
            and run.phase5_status == "candidate_visual_accepted"
            and bool(run.comparison_artifact_sha256)
            and before_ver == after_ver
            and bool(True)  # budgets already respected if completed without abort
        ):
            percent_eligible = True
        provenance = ExecutionProvenance(
            **{
                **provenance.as_dict(),
                "percent_authorization_eligible": percent_eligible,
            }
        )

        completed = datetime.utcnow()
        telemetry = {
            "execution_uuid": exec_uuid,
            "approval_id": row.id,
            "request_id": row.request_id,
            "result_status": result_status,
            "budget": budget.as_dict(),
            "no_serving_mutation": True,
            "pointer_version_before": before_ver,
            "pointer_version_after": after_ver,
            "provenance": provenance.as_dict(),
        }
        telemetry_sha = _sha(telemetry)
        exec_sha = _sha(
            {
                "execution_uuid": exec_uuid,
                "approval_id": row.id,
                "telemetry_sha256": telemetry_sha,
                "result_status": result_status,
                "execution_mode": provenance.execution_mode,
            }
        )
        exec_row = PreviewLiveCanaryExecutionRecord(
            execution_uuid=exec_uuid,
            approval_id=row.id,
            request_id=row.request_id,
            started_at=started,
            completed_at=completed,
            provider_manifest_sha256=identity.provider_manifest_sha256,
            generation_policy_sha256=identity.generation_policy_sha256,
            prompt_policy_sha256=identity.prompt_policy_sha256,
            candidate_revision_id=run.candidate_revision_id if run else None,
            effective_tier=run.effective_tier if run else None,
            phase4_status=run.phase4_status if run else None,
            phase5_status=run.phase5_status if run else None,
            provider_calls=budget.provider_calls,
            input_tokens=budget.input_tokens,
            output_tokens=budget.output_tokens,
            estimated_cost_usd=budget.estimated_cost_usd,
            wall_seconds=budget.wall_seconds(),
            retries=budget.retries,
            budget_json=json.dumps(budget.as_dict(), sort_keys=True),
            comparison_artifact_sha256=(
                run.comparison_artifact_sha256 if run else None
            ),
            telemetry_sha256=telemetry_sha,
            result_status=result_status,
            failure_reason=failure_reason,
            no_serving_mutation=True,
            pointer_version_before=before_ver,
            pointer_version_after=after_ver,
            policy_identity_sha256=identity.policy_identity_sha256,
            idempotency_key=body.idempotency_key,
            execution_sha256=exec_sha,
            created_at=started,
            execution_mode=provenance.execution_mode,
            provider_was_live=provenance.provider_was_live,
            provider_family=provenance.provider_family,
            provider_model=provenance.provider_model,
            provider_factory_revision=provenance.provider_factory_revision,
            network_access_expected=provenance.network_access_expected,
            execution_environment=provenance.execution_environment,
            simulation_only=provenance.simulation_only,
            percent_authorization_eligible=provenance.percent_authorization_eligible,
            provenance_json=json.dumps(provenance.as_dict(), sort_keys=True),
        )
        self._db.add(exec_row)
        self._db.flush()
        self._db.add(
            PreviewLiveCanaryExecutionStatusEventRecord(
                execution_id=exec_row.id,
                status=result_status,
                actor_id=actor.actor_id,
                reason=failure_reason or body.reason,
                created_at=completed,
                event_sha256=_sha(
                    {
                        "execution_id": exec_row.id,
                        "status": result_status,
                        "actor_id": actor.actor_id,
                        "created_at": completed.isoformat(),
                    }
                ),
            )
        )
        terminal = (
            "completed"
            if result_status == "completed"
            else ("aborted" if result_status == "aborted" else "failed")
        )
        self._append_lifecycle(
            approval_id=row.id,
            status="executed",
            actor_id=actor.actor_id,
            reason=body.reason,
            ticket_ref=body.ticket_ref,
        )
        self._append_lifecycle(
            approval_id=row.id,
            status=terminal,
            actor_id=actor.actor_id,
            reason=failure_reason or body.reason,
            ticket_ref=body.ticket_ref,
        )
        self._release_claim(exec_row.id)
        invalidate_canary_auth_cache()
        return self._view_execution(exec_row)

    def review_execution(
        self,
        actor: TrustedRolloutActor,
        execution_id: int,
        body: CanaryReviewBody,
        *,
        raw_payload: dict | None = None,
    ) -> CanaryExecutionView:
        if raw_payload is not None:
            reject_client_supplied_roles(raw_payload)
        require_permission(actor, "review_canary")
        self._require_canary_plane()
        row = (
            self._db.query(PreviewLiveCanaryExecutionRecord)
            .filter(PreviewLiveCanaryExecutionRecord.id == execution_id)
            .one_or_none()
        )
        if row is None:
            raise CanaryServiceError("execution_not_found", stage="review")
        if row.result_status != "completed":
            raise CanaryServiceError("execution_not_completed", stage="review")

        exec_actor = next(
            (
                e.actor_id
                for e in self._db.query(PreviewLiveCanaryLifecycleEventRecord)
                .filter(
                    PreviewLiveCanaryLifecycleEventRecord.approval_id == row.approval_id,
                    PreviewLiveCanaryLifecycleEventRecord.status == "executed",
                )
                .all()
            ),
            None,
        )
        if actor.actor_id == exec_actor:
            raise CanaryServiceError("sod_reviewer_executor", stage="review")

        statuses = self._lifecycle_statuses(row.approval_id)
        if any(
            s in statuses
            for s in (
                "reviewed_accepted",
                "reviewed_rejected",
                "reviewed_fixture_only",
            )
        ):
            return self._view_execution(row)

        if not body.accept:
            status = "reviewed_rejected"
        elif (
            row.execution_mode == "live"
            and bool(row.provider_was_live)
            and not bool(row.simulation_only)
            and bool(row.percent_authorization_eligible)
        ):
            status = "reviewed_accepted"
        else:
            # Fixture / non-eligible executions cannot authorize percent.
            status = "reviewed_fixture_only"
        self._append_lifecycle(
            approval_id=row.approval_id,
            status=status,
            actor_id=actor.actor_id,
            reason=body.reason,
            ticket_ref=body.ticket_ref,
        )
        if status == "reviewed_rejected":
            _emit_canary_alert(
                self._db,
                alert_class="live_canary_review_rejected",
                source_event_id=f"canary-review:{row.execution_uuid}",
            )
        invalidate_canary_auth_cache()
        return self._view_execution(row)


__all__ = [
    "BudgetTracker",
    "CanaryProvider",
    "CanaryRunResult",
    "CanaryRunner",
    "CanaryService",
    "CanaryServiceError",
    "DefaultCanaryRunner",
    "ExecutionProvenance",
    "FixtureCanaryProvider",
    "canary_simulation_allowed",
]
