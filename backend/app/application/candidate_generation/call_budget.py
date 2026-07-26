"""Phase 3B candidate provider-call budget and attempt ledger.

Policy revision: 2026-07-26.candidate-provider.1

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

CANDIDATE_CALL_BUDGET_POLICY_REVISION = "2026-07-26.candidate-provider.2"

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "substage": self.substage,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "status": self.status,
            "provider_attempt_id": self.provider_attempt_id,
            "parent_attempt_id": self.parent_attempt_id,
            "retry_decision": self.retry_decision,
            "idempotency_key": self.idempotency_key,
        }


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

    @classmethod
    def create(cls) -> "CandidateCallBudget":
        return cls()

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
        self._attempts.append(attempt)

    def record_checkpoint(self, checkpoint: CandidateStageCheckpoint) -> None:
        self._checkpoints[checkpoint.substage] = checkpoint

    def new_attempt_id(self) -> str:
        return uuid.uuid4().hex

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
