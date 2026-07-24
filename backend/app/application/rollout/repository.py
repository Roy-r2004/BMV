"""Phase 7A rollout repository primitives.

Production methods never create applied decisions or promote/rollback pointer
versions. Test-only pointer mutation lives under tests/rollout/harness.py and
requires an explicit test-only mode flag.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.application.rollout.authorization import require_permission
from app.application.rollout.policy import allowlist_canonical_json, build_policy_view
from app.domain.models.rollout import (
    PreviewPromotionDecisionRecord,
    PreviewPromotionDecisionStatusEventRecord,
    PreviewRolloutPolicyRecord,
    PreviewServingPointerVersionRecord,
)
from app.domain.schemas.rollout import (
    DecisionStatus,
    DecisionType,
    RolloutPolicyView,
    TrustedRolloutActor,
)


PRODUCTION_DECISION_STATUSES: frozenset[str] = frozenset(
    {"requested", "rejected", "cancelled"}
)
FORBIDDEN_PRODUCTION_DECISION_STATUSES: frozenset[str] = frozenset(
    {"applied", "test_only_simulated"}
)
FORBIDDEN_PRODUCTION_POINTER_ACTIONS: frozenset[str] = frozenset(
    {"promote", "rollback"}
)


class RolloutRepositoryError(RuntimeError):
    """Repository policy violation."""


def _decision_sha256(payload: dict[str, Any]) -> str:
    material = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


class RolloutRepository:
    """Production-safe repository — inserts only for non-applied decisions/policies."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_latest_policy(self) -> PreviewRolloutPolicyRecord | None:
        return (
            self._db.query(PreviewRolloutPolicyRecord)
            .order_by(PreviewRolloutPolicyRecord.id.desc())
            .first()
        )

    def get_latest_policy_view(self) -> RolloutPolicyView | None:
        row = self.get_latest_policy()
        if row is None:
            return None
        allowlist = tuple(json.loads(row.allowlist_json))
        breaker = json.loads(row.circuit_breaker_policy_json)
        from app.domain.schemas.rollout import CircuitBreakerPolicyContract

        return build_policy_view(
            policy_revision=row.policy_revision,
            master_enabled=bool(row.master_enabled),
            shadow_enabled=bool(row.shadow_enabled),
            promote_enabled=bool(row.promote_enabled),
            rollout_percent=int(row.rollout_percent),
            allowlist=allowlist,
            rollout_salt=row.rollout_salt,
            created_actor_id=row.created_actor_id,
            created_actor_role=row.created_actor_role,  # type: ignore[arg-type]
            breaker=CircuitBreakerPolicyContract.model_validate(breaker),
        )

    def insert_policy_version(
        self,
        *,
        actor: TrustedRolloutActor,
        view: RolloutPolicyView,
    ) -> PreviewRolloutPolicyRecord:
        require_permission(actor, "create_rollout_policy_version")
        row = PreviewRolloutPolicyRecord(
            policy_revision=view.policy_revision,
            master_enabled=view.master_enabled,
            shadow_enabled=view.shadow_enabled,
            promote_enabled=view.promote_enabled,
            rollout_percent=view.rollout_percent,
            allowlist_json=allowlist_canonical_json(view.allowlist),
            allowlist_sha256=view.allowlist_sha256,
            circuit_breaker_policy_json=view.circuit_breaker_policy.model_dump_json(),
            circuit_breaker_policy_sha256=view.circuit_breaker_policy_sha256,
            rollout_salt=view.rollout_salt,
            configuration_sha256=view.configuration_sha256,
            created_at=datetime.utcnow(),
            created_actor_id=actor.actor_id,
            created_actor_role=actor.roles[0],
        )
        self._db.add(row)
        self._db.flush()
        return row

    def insert_decision(
        self,
        *,
        request_id: int,
        decision_type: DecisionType,
        decision_status: DecisionStatus,
        actor_id: str,
        actor_role: str,
        reason: str,
        policy_revision: str,
        eligibility_sha256: str,
        lineage_sha256: str,
        candidate_revision_id: int | None = None,
        effective_tier_summary_id: int | None = None,
        phase4_validation_summary_id: int | None = None,
        phase5_visual_summary_id: int | None = None,
        candidate_manifest_sha256: str | None = None,
        ticket_ref: str | None = None,
        idempotency_key: str | None = None,
        rejection_reason: str | None = None,
        previous_pointer_version: int | None = None,
        resulting_pointer_version: int | None = None,
    ) -> PreviewPromotionDecisionRecord:
        if decision_status in FORBIDDEN_PRODUCTION_DECISION_STATUSES:
            raise RolloutRepositoryError(
                "production repository cannot create applied/simulated decisions"
            )
        if decision_status not in PRODUCTION_DECISION_STATUSES:
            raise RolloutRepositoryError(
                f"unsupported production decision_status={decision_status!r}"
            )
        payload = {
            "request_id": request_id,
            "decision_type": decision_type,
            "decision_status": decision_status,
            "candidate_revision_id": candidate_revision_id,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "reason": reason,
            "policy_revision": policy_revision,
            "eligibility_sha256": eligibility_sha256,
            "lineage_sha256": lineage_sha256,
            "idempotency_key": idempotency_key,
        }
        row = PreviewPromotionDecisionRecord(
            request_id=request_id,
            decision_type=decision_type,
            decision_status=decision_status,
            candidate_revision_id=candidate_revision_id,
            effective_tier_summary_id=effective_tier_summary_id,
            phase4_validation_summary_id=phase4_validation_summary_id,
            phase5_visual_summary_id=phase5_visual_summary_id,
            lineage_sha256=lineage_sha256,
            candidate_manifest_sha256=candidate_manifest_sha256,
            actor_id=actor_id,
            actor_role=actor_role,
            reason=reason,
            ticket_ref=ticket_ref,
            policy_revision=policy_revision,
            eligibility_sha256=eligibility_sha256,
            idempotency_key=idempotency_key,
            requested_at=datetime.utcnow(),
            rejection_reason=rejection_reason,
            previous_pointer_version=previous_pointer_version,
            resulting_pointer_version=resulting_pointer_version,
            decision_sha256=_decision_sha256(payload),
        )
        self._db.add(row)
        self._db.flush()
        return row

    def get_current_pointer(
        self, request_id: int
    ) -> PreviewServingPointerVersionRecord | None:
        return (
            self._db.query(PreviewServingPointerVersionRecord)
            .filter(
                PreviewServingPointerVersionRecord.request_id == request_id,
                PreviewServingPointerVersionRecord.is_current.is_(True),
            )
            .one_or_none()
        )

    def create_promote_or_rollback_pointer(self, **_kwargs: Any) -> None:
        raise RolloutRepositoryError(
            "production repository cannot create promote/rollback pointer versions"
        )

    def apply_pointer_swap(self, **_kwargs: Any) -> None:
        raise RolloutRepositoryError(
            "production repository has no pointer-swap executor in Phase 7A"
        )


def production_services_cannot_create_applied_decisions() -> bool:
    return True


def production_services_cannot_mutate_pointers() -> bool:
    return True


__all__ = [
    "FORBIDDEN_PRODUCTION_DECISION_STATUSES",
    "FORBIDDEN_PRODUCTION_POINTER_ACTIONS",
    "PRODUCTION_DECISION_STATUSES",
    "RolloutRepository",
    "RolloutRepositoryError",
    "production_services_cannot_create_applied_decisions",
    "production_services_cannot_mutate_pointers",
    "PreviewPromotionDecisionStatusEventRecord",
]
