"""Phase 3B candidate provider-call budget and attempt ledger.

Policy revision: see ``CANDIDATE_CALL_BUDGET_POLICY_REVISION`` below.

Caps stay within the existing global ``V2_CANDIDATE_MAX_CALLS`` (default 4).
Per-substage caps match the cold+repair path:
  - business_components: 2
  - pages: 2
Deterministic stages are 0.

A malformed provider response consumes one call. Application-owned recovery
retries must approve another call from this ledger; SDK transport retries
are not separate application charges.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from app.core.config import settings

CANDIDATE_CALL_BUDGET_POLICY_REVISION = "2026-07-28.candidate-provider.3"

CandidateBudgetCode = Literal[
    "candidate_total_call_budget_exhausted",
    "candidate_substage_call_budget_exhausted",
    "candidate_no_budget_for_provider_retry",
]

_SUBSTAGE_CAPS: dict[str, int] = {
    "foundation": 0,
    "data_exports": 0,
    "business_components": 2,
    "pages": 2,
    "routes": 0,
    "validation": 0,
}


def _is_paid_provider_attempt(attempt: CandidateProviderAttempt) -> bool:
    if attempt.response_format == "preflight":
        return False
    if attempt.idempotency_key.endswith(":preflight"):
        return False
    if attempt.terminal_decision == "fail_closed_preflight":
        return False
    return True


@dataclass
class CandidateLedgerEvent:
    kind: str
    stage: str
    wall_elapsed_ms: int
    attempt_type: str = ""
    used_before: int = 0
    failure_code: str = ""
    provider: str = ""
    model: str = ""
    idempotency_key: str = ""


@dataclass
class CandidateProviderAttempt:
    attempt_id: str
    request_id: int
    candidate_revision_uuid: str
    substage: str
    provider: str
    model: str
    http_status: int
    response_top_level_keys: list[str]
    response_format: str
    provider_request_id: str
    raw_payload_sha256: str
    duration_ms: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    typed_result: str
    error_code: str
    retryable: bool
    retry_attempted: bool
    terminal_decision: str
    parent_attempt_id: str = ""
    idempotency_key: str = ""
    error_type: str = ""
    error_message_redacted: str = ""
    error_metadata_keys: list[str] | None = None
    request_shape_hash: str = ""
    capability_profile_revision: str = ""
    retry_decision_reason: str = ""
    fallback_model_decision: str = ""
    calls_remaining: int | None = None
    context_window: int | None = None
    estimated_input_tokens: int | None = None
    requested_output_tokens: int | None = None
    clamped_output_tokens: int | None = None
    minimum_output_allowance: int | None = None
    context_reserve: int | None = None
    approval_decision: str = ""
    attempt_number: int = 0
    started_at: float = 0.0
    finished_at: float = 0.0
    last_checkpoint_status: str = ""

    def to_diagnostics(self) -> dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "request_id": self.request_id,
            "candidate_revision_uuid": self.candidate_revision_uuid,
            "substage": self.substage,
            "provider": self.provider,
            "model": self.model,
            "http_status": self.http_status,
            "response_top_level_keys": list(self.response_top_level_keys),
            "response_format": self.response_format,
            "provider_request_id": self.provider_request_id,
            "raw_payload_sha256": self.raw_payload_sha256,
            "duration_ms": self.duration_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "typed_result": self.typed_result,
            "error_code": self.error_code,
            "retryable": self.retryable,
            "retry_attempted": self.retry_attempted,
            "terminal_decision": self.terminal_decision,
            "parent_attempt_id": self.parent_attempt_id,
            "idempotency_key": self.idempotency_key,
            "error_type": self.error_type,
            "error_message_redacted": self.error_message_redacted,
            "error_metadata_keys": list(self.error_metadata_keys or []),
            "request_shape_hash": self.request_shape_hash,
            "capability_profile_revision": self.capability_profile_revision,
            "retry_decision_reason": self.retry_decision_reason,
            "fallback_model_decision": self.fallback_model_decision,
            "calls_remaining": self.calls_remaining,
            "context_window": self.context_window,
            "estimated_input_tokens": self.estimated_input_tokens,
            "requested_output_tokens": self.requested_output_tokens,
            "clamped_output_tokens": self.clamped_output_tokens,
            "minimum_output_allowance": self.minimum_output_allowance,
            "context_reserve": self.context_reserve,
            "approval_decision": self.approval_decision,
            "attempt_number": self.attempt_number,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "last_checkpoint_status": self.last_checkpoint_status,
        }


@dataclass
class CandidateStageCheckpoint:
    substage: str
    input_hash: str
    output_hash: str
    status: str
    provider_attempt_id: str = ""
    parent_attempt_id: str = ""
    retry_decision: str = ""
    idempotency_key: str = ""
    artifact_manifest: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "substage": self.substage,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "status": self.status,
            "provider_attempt_id": self.provider_attempt_id,
            "parent_attempt_id": self.parent_attempt_id,
            "retry_decision": self.retry_decision,
            "idempotency_key": self.idempotency_key,
        }
        if self.artifact_manifest is not None:
            payload["artifact_manifest"] = self.artifact_manifest
        return payload


class CandidateCallBudget:
    def __init__(self) -> None:
        self.total_max: int = int(settings.V2_CANDIDATE_MAX_CALLS)
        self._substage_caps: dict[str, int] = dict(_SUBSTAGE_CAPS)
        self._used: dict[str, int] = dict.fromkeys(_SUBSTAGE_CAPS, 0)
        self._total_used: int = 0
        self._events: list[CandidateLedgerEvent] = []
        self._attempts: list[CandidateProviderAttempt] = []
        self._checkpoints: dict[str, CandidateStageCheckpoint] = {}
        self._started: float = time.monotonic()
        self._attempt_sequence: int = 0

    @classmethod
    def create(cls) -> "CandidateCallBudget":
        return cls()

    @classmethod
    def restore(
        cls,
        *,
        snapshot: dict[str, Any] | None,
        attempts: list[dict[str, Any]] | None = None,
    ) -> "CandidateCallBudget":
        budget = cls.create()
        if not snapshot:
            return budget
        if snapshot.get("policy_revision") != CANDIDATE_CALL_BUDGET_POLICY_REVISION:
            raise ValueError("candidate call budget restore policy revision mismatch")
        budget._events = [
            CandidateLedgerEvent(
                kind=str(item.get("kind") or ""),
                stage=str(item.get("stage") or ""),
                wall_elapsed_ms=int(item.get("wall_elapsed_ms") or 0),
                attempt_type=str(item.get("attempt_type") or ""),
                used_before=int(item.get("used_before") or 0),
                failure_code=str(item.get("failure_code") or ""),
                provider=str(item.get("provider") or ""),
                model=str(item.get("model") or ""),
                idempotency_key=str(item.get("idempotency_key") or ""),
            )
            for item in (snapshot.get("events") or [])
        ]
        budget._checkpoints = {
            key: CandidateStageCheckpoint(
                substage=str(value.get("substage") or key),
                input_hash=str(value.get("input_hash") or ""),
                output_hash=str(value.get("output_hash") or ""),
                status=str(value.get("status") or ""),
                provider_attempt_id=str(value.get("provider_attempt_id") or ""),
                parent_attempt_id=str(value.get("parent_attempt_id") or ""),
                retry_decision=str(value.get("retry_decision") or ""),
                idempotency_key=str(value.get("idempotency_key") or ""),
                artifact_manifest=(
                    value.get("artifact_manifest")
                    if isinstance(value.get("artifact_manifest"), dict)
                    else None
                ),
            )
            for key, value in (snapshot.get("checkpoints") or {}).items()
            if isinstance(value, dict)
        }
        restored_attempts = [
            CandidateProviderAttempt(
                attempt_id=str(item.get("attempt_id") or ""),
                request_id=int(item.get("request_id") or 0),
                candidate_revision_uuid=str(
                    item.get("candidate_revision_uuid") or ""
                ),
                substage=str(item.get("substage") or ""),
                provider=str(item.get("provider") or ""),
                model=str(item.get("model") or ""),
                http_status=int(item.get("http_status") or 0),
                response_top_level_keys=list(
                    item.get("response_top_level_keys") or []
                ),
                response_format=str(item.get("response_format") or ""),
                provider_request_id=str(item.get("provider_request_id") or ""),
                raw_payload_sha256=str(item.get("raw_payload_sha256") or ""),
                duration_ms=int(item.get("duration_ms") or 0),
                input_tokens=int(item.get("input_tokens") or 0),
                output_tokens=int(item.get("output_tokens") or 0),
                total_tokens=int(item.get("total_tokens") or 0),
                typed_result=str(item.get("typed_result") or ""),
                error_code=str(item.get("error_code") or ""),
                retryable=bool(item.get("retryable") or False),
                retry_attempted=bool(item.get("retry_attempted") or False),
                terminal_decision=str(item.get("terminal_decision") or ""),
                parent_attempt_id=str(item.get("parent_attempt_id") or ""),
                idempotency_key=str(item.get("idempotency_key") or ""),
                error_type=str(item.get("error_type") or ""),
                error_message_redacted=str(
                    item.get("error_message_redacted") or ""
                ),
                error_metadata_keys=list(item.get("error_metadata_keys") or []),
                request_shape_hash=str(item.get("request_shape_hash") or ""),
                capability_profile_revision=str(
                    item.get("capability_profile_revision") or ""
                ),
                retry_decision_reason=str(
                    item.get("retry_decision_reason") or ""
                ),
                fallback_model_decision=str(
                    item.get("fallback_model_decision") or ""
                ),
                calls_remaining=(
                    int(item["calls_remaining"])
                    if item.get("calls_remaining") is not None
                    else None
                ),
                context_window=(
                    int(item["context_window"])
                    if item.get("context_window") is not None
                    else None
                ),
                estimated_input_tokens=(
                    int(item["estimated_input_tokens"])
                    if item.get("estimated_input_tokens") is not None
                    else None
                ),
                requested_output_tokens=(
                    int(item["requested_output_tokens"])
                    if item.get("requested_output_tokens") is not None
                    else None
                ),
                clamped_output_tokens=(
                    int(item["clamped_output_tokens"])
                    if item.get("clamped_output_tokens") is not None
                    else None
                ),
                minimum_output_allowance=(
                    int(item["minimum_output_allowance"])
                    if item.get("minimum_output_allowance") is not None
                    else None
                ),
                context_reserve=(
                    int(item["context_reserve"])
                    if item.get("context_reserve") is not None
                    else None
                ),
                approval_decision=str(item.get("approval_decision") or ""),
                attempt_number=int(item.get("attempt_number") or 0),
                started_at=float(item.get("started_at") or 0.0),
                finished_at=float(item.get("finished_at") or 0.0),
                last_checkpoint_status=str(
                    item.get("last_checkpoint_status") or ""
                ),
            )
            for item in (attempts or [])
        ]
        attempt_ids: set[str] = set()
        idempotency_keys: set[str] = set()
        derived_used = dict.fromkeys(budget._substage_caps, 0)
        derived_total = 0
        for attempt in restored_attempts:
            if not attempt.attempt_id or attempt.attempt_id in attempt_ids:
                raise ValueError("candidate call budget restore duplicate attempt id")
            attempt_ids.add(attempt.attempt_id)
            if not attempt.idempotency_key or attempt.idempotency_key in idempotency_keys:
                raise ValueError(
                    "candidate call budget restore duplicate idempotency"
                )
            idempotency_keys.add(attempt.idempotency_key)
            if attempt.substage not in budget._substage_caps:
                raise ValueError("candidate call budget restore unknown substage")
            numeric_values = (
                attempt.http_status,
                attempt.duration_ms,
                attempt.input_tokens,
                attempt.output_tokens,
                attempt.total_tokens,
            )
            if any(value < 0 for value in numeric_values):
                raise ValueError("candidate call budget restore negative attempt value")
            if _is_paid_provider_attempt(attempt):
                derived_used[attempt.substage] = (
                    derived_used.get(attempt.substage, 0) + 1
                )
                derived_total += 1
        event_derived_used = dict.fromkeys(budget._substage_caps, 0)
        event_derived_total = 0
        for event in budget._events:
            if str(event.kind) != "approved":
                continue
            if event.attempt_type not in {"ai", "ai_repair"}:
                continue
            if event.stage not in budget._substage_caps:
                raise ValueError("candidate call budget restore unknown event stage")
            event_derived_used[event.stage] = (
                event_derived_used.get(event.stage, 0) + 1
            )
            event_derived_total += 1
        # Attempts can under-report when a paid repair was ledgered but the
        # provider-attempt row was not persisted; prefer the higher of the two.
        effective_used = {
            stage: max(derived_used.get(stage, 0), event_derived_used.get(stage, 0))
            for stage in budget._substage_caps
        }
        effective_total = int(sum(effective_used.values()))
        if any(value < 0 for value in effective_used.values()):
            raise ValueError("candidate call budget restore negative usage")
        if any(
            effective_used[stage] > budget._substage_caps[stage]
            for stage in budget._substage_caps
        ):
            raise ValueError("candidate call budget restore exceeds stage cap")
        if effective_total > budget.total_max:
            raise ValueError("candidate call budget restore exceeds total cap")
        snapshot_total_used = int(snapshot.get("total_used") or 0)
        snapshot_substage_used = {
            key: int(value)
            for key, value in (snapshot.get("substage_used") or {}).items()
        }
        if snapshot_total_used < 0 or any(
            value < 0 for value in snapshot_substage_used.values()
        ):
            raise ValueError("candidate call budget restore negative snapshot count")
        if snapshot_total_used not in {0, effective_total}:
            raise ValueError("candidate call budget restore total mismatch")
        for stage, used in snapshot_substage_used.items():
            if stage not in budget._substage_caps:
                raise ValueError("candidate call budget restore unknown snapshot stage")
            if used not in {0, effective_used[stage]}:
                raise ValueError("candidate call budget restore stage mismatch")
        budget._attempts = restored_attempts
        budget._used = {
            **dict.fromkeys(budget._substage_caps, 0),
            **effective_used,
        }
        budget._total_used = effective_total
        budget._attempt_sequence = max(
            (attempt.attempt_number for attempt in restored_attempts),
            default=0,
        )
        return budget

    def _wall_ms(self) -> int:
        return int((time.monotonic() - self._started) * 1000)

    def remaining_total(self) -> int:
        return max(0, self.total_max - self._total_used)

    def remaining_stage(self, stage: str) -> int:
        cap = self._substage_caps.get(stage, 0)
        return max(0, cap - self._used.get(stage, 0))

    def approve(
        self,
        stage: str,
        *,
        attempt_type: str = "ai",
        provider: str = "",
        model: str = "",
        idempotency_key: str = "",
    ) -> tuple[bool, str]:
        used_before = self._total_used
        if self._used.get(stage, 0) >= self._substage_caps.get(stage, 0):
            code = "candidate_substage_call_budget_exhausted"
            self._events.append(
                CandidateLedgerEvent(
                    kind="denied",
                    stage=stage,
                    wall_elapsed_ms=self._wall_ms(),
                    attempt_type=attempt_type,
                    used_before=used_before,
                    failure_code=code,
                    provider=provider,
                    model=model,
                    idempotency_key=idempotency_key,
                )
            )
            return False, code
        if self._total_used >= self.total_max:
            code = "candidate_total_call_budget_exhausted"
            self._events.append(
                CandidateLedgerEvent(
                    kind="denied",
                    stage=stage,
                    wall_elapsed_ms=self._wall_ms(),
                    attempt_type=attempt_type,
                    used_before=used_before,
                    failure_code=code,
                    provider=provider,
                    model=model,
                    idempotency_key=idempotency_key,
                )
            )
            return False, code
        self._used[stage] = self._used.get(stage, 0) + 1
        self._total_used += 1
        self._events.append(
            CandidateLedgerEvent(
                kind="approved",
                stage=stage,
                wall_elapsed_ms=self._wall_ms(),
                attempt_type=attempt_type,
                used_before=used_before,
                provider=provider,
                model=model,
                idempotency_key=idempotency_key,
            )
        )
        return True, ""

    def record_attempt(self, attempt: CandidateProviderAttempt) -> None:
        """Append, or upsert in place when ``attempt_id`` is already ledgered.

        An attempt is opened as an in-flight placeholder before the paid
        provider call starts, then updated to its terminal state in place so
        the row stays a single durable identity from open to close instead of
        leaving orphaned duplicates.
        """
        if attempt.attempt_id:
            for index, existing in enumerate(self._attempts):
                if existing.attempt_id == attempt.attempt_id:
                    self._attempts[index] = attempt
                    return
        self._attempts.append(attempt)

    def record_checkpoint(self, checkpoint: CandidateStageCheckpoint) -> None:
        self._checkpoints[checkpoint.substage] = checkpoint

    def checkpoint_status(self, substage: str) -> str:
        checkpoint = self._checkpoints.get(substage)
        return checkpoint.status if checkpoint is not None else ""

    def new_attempt_id(self) -> str:
        return uuid.uuid4().hex

    def open_attempt_number(self) -> int:
        self._attempt_sequence += 1
        return self._attempt_sequence

    def snapshot(self) -> dict[str, Any]:
        return {
            "policy_revision": CANDIDATE_CALL_BUDGET_POLICY_REVISION,
            "total_max": self.total_max,
            "total_used": self._total_used,
            "remaining": self.remaining_total(),
            "substage_caps": dict(self._substage_caps),
            "substage_used": dict(self._used),
            "events": [
                {
                    "kind": event.kind,
                    "stage": event.stage,
                    "wall_elapsed_ms": event.wall_elapsed_ms,
                    "attempt_type": event.attempt_type,
                    "used_before": event.used_before,
                    "failure_code": event.failure_code,
                    "provider": event.provider,
                    "model": event.model,
                    "idempotency_key": event.idempotency_key,
                }
                for event in self._events
            ],
            "checkpoints": {
                key: value.to_dict() for key, value in self._checkpoints.items()
            },
        }

    def attempts_snapshot(self) -> list[dict[str, Any]]:
        return [item.to_diagnostics() for item in self._attempts]


__all__ = [
    "CANDIDATE_CALL_BUDGET_POLICY_REVISION",
    "CandidateCallBudget",
    "CandidateProviderAttempt",
    "CandidateStageCheckpoint",
]
