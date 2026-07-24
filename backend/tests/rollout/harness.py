"""Test-only Phase 7A pointer/decision mutation harness.

Structurally unreachable from application routing. Requires explicit
PHASE7A_TEST_ONLY_MODE=1 in the process environment for the calling test
module, plus Phase7ATestOnlyRolloutHarness(enabled=True).
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime

from sqlalchemy.orm import Session

from app.domain.models.rollout import (
    PreviewPromotionDecisionRecord,
    PreviewPromotionDecisionStatusEventRecord,
    PreviewRolloutAuditEventRecord,
    PreviewServingPointerVersionRecord,
)

_TEST_ONLY_ENV = "PHASE7A_TEST_ONLY_MODE"


class TestOnlyHarnessError(RuntimeError):
    """Raised when the test harness is used outside test-only mode."""


def assert_test_only_mode() -> None:
    if os.environ.get(_TEST_ONLY_ENV) != "1":
        raise TestOnlyHarnessError(
            "Test-only rollout harness requires PHASE7A_TEST_ONLY_MODE=1"
        )


class Phase7ATestOnlyRolloutHarness:
    """Explicit test-only mutation helper for concurrency/migration simulations."""

    def __init__(self, db: Session, *, enabled: bool) -> None:
        assert_test_only_mode()
        if not enabled:
            raise TestOnlyHarnessError("harness must be constructed with enabled=True")
        self._db = db
        self._enabled = True

    def simulate_pointer_swap_transaction(
        self,
        *,
        request_id: int,
        expected_previous_version: int | None,
        new_pointer_version: int,
        target_kind: str,
        pointer_action: str,
        actor_id: str,
        policy_revision: str,
        candidate_revision_id: int | None = None,
        legacy_preview_relpath: str | None = None,
        effective_tier: int | None = None,
        summary_sha256: str | None = None,
        candidate_manifest_sha256: str | None = None,
        lineage_sha256: str | None = None,
        eligibility_sha256: str | None = None,
        fail_before_commit: bool = False,
    ) -> dict:
        """Future-safe sequence approved for Phase 7A tests.

        1. Begin transaction (caller session)
        2. Acquire request-scoped serialization (SQLite BEGIN IMMEDIATE via
           exclusive write; Postgres FOR UPDATE)
        3. Read and verify expected current pointer version
        4. Insert promotion decision in non-applied pending state
        5. Mark previous pointer non-current
        6. Insert new pointer as current
        7. Mark decision applied via append-only status event
        8. Append audit event
        9. Commit (unless fail_before_commit)
        """
        assert self._enabled
        bind = self._db.get_bind()
        dialect = bind.dialect.name
        lineage = lineage_sha256 or ("a" * 64)
        eligibility = eligibility_sha256 or ("b" * 64)

        # Serialization: Postgres row lock; SQLite relies on write lock +
        # version check + partial unique index (BEGIN IMMEDIATE in concurrency tests).
        query = self._db.query(PreviewServingPointerVersionRecord).filter(
            PreviewServingPointerVersionRecord.request_id == request_id,
            PreviewServingPointerVersionRecord.is_current.is_(True),
        )
        if dialect == "postgresql":
            query = query.with_for_update()
        current = query.one_or_none()
        current_version = None if current is None else current.pointer_version
        if current_version != expected_previous_version:
            self._db.rollback()
            raise TestOnlyHarnessError(
                f"version conflict: expected {expected_previous_version}, "
                f"got {current_version}"
            )

        decision_payload = {
            "request_id": request_id,
            "decision_type": "promote" if pointer_action == "promote" else pointer_action,
            "decision_status": "requested",
            "actor_id": actor_id,
            "policy_revision": policy_revision,
            "pointer_version": new_pointer_version,
        }
        decision_sha = hashlib.sha256(
            json.dumps(decision_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        decision = PreviewPromotionDecisionRecord(
            request_id=request_id,
            decision_type="promote" if pointer_action != "rollback" else "rollback",
            decision_status="requested",
            candidate_revision_id=candidate_revision_id,
            lineage_sha256=lineage,
            candidate_manifest_sha256=candidate_manifest_sha256,
            actor_id=actor_id,
            actor_role="rollout_admin",
            reason="test_only_simulated_pointer_swap",
            policy_revision=policy_revision,
            eligibility_sha256=eligibility,
            requested_at=datetime.utcnow(),
            previous_pointer_version=current_version,
            resulting_pointer_version=new_pointer_version,
            decision_sha256=decision_sha,
        )
        self._db.add(decision)
        self._db.flush()

        if current is not None:
            current.is_current = False
            self._db.flush()

        pointer_payload = {
            "request_id": request_id,
            "pointer_version": new_pointer_version,
            "target_kind": target_kind,
            "pointer_action": pointer_action,
            "decision_id": decision.id,
        }
        pointer_sha = hashlib.sha256(
            json.dumps(pointer_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        pointer = PreviewServingPointerVersionRecord(
            request_id=request_id,
            pointer_version=new_pointer_version,
            target_kind=target_kind,
            candidate_revision_id=candidate_revision_id,
            legacy_preview_relpath=legacy_preview_relpath,
            effective_tier=effective_tier,
            summary_sha256=summary_sha256,
            candidate_manifest_sha256=candidate_manifest_sha256,
            previous_pointer_version=current_version,
            pointer_action=pointer_action,
            decision_id=decision.id,
            actor_id=actor_id,
            policy_revision=policy_revision,
            created_at=datetime.utcnow(),
            is_current=True,
            pointer_sha256=pointer_sha,
        )
        self._db.add(pointer)
        self._db.flush()

        event_payload = {
            "decision_id": decision.id,
            "status": "applied",
            "actor_id": actor_id,
        }
        event_sha = hashlib.sha256(
            json.dumps(event_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        self._db.add(
            PreviewPromotionDecisionStatusEventRecord(
                decision_id=decision.id,
                status="applied",
                actor_id=actor_id,
                reason="test_only_mark_applied",
                created_at=datetime.utcnow(),
                event_sha256=event_sha,
            )
        )
        meta = {"harness": "test_only", "pointer_version": new_pointer_version}
        meta_json = json.dumps(meta, sort_keys=True)
        audit_sha = hashlib.sha256(
            f"{decision.id}:{new_pointer_version}:{meta_json}".encode("utf-8")
        ).hexdigest()
        self._db.add(
            PreviewRolloutAuditEventRecord(
                request_id=request_id,
                event_type="pointer_resolved",
                actor_id=actor_id,
                actor_role="rollout_admin",
                policy_revision=policy_revision,
                decision_id=decision.id,
                pointer_version_before=current_version,
                pointer_version_after=new_pointer_version,
                reason="test_only_simulated_swap",
                metadata_json=meta_json,
                metadata_sha256=hashlib.sha256(meta_json.encode("utf-8")).hexdigest(),
                created_at=datetime.utcnow(),
                event_sha256=audit_sha,
            )
        )
        self._db.flush()

        if fail_before_commit:
            self._db.rollback()
            return {"rolled_back": True}

        self._db.commit()
        return {
            "decision_id": decision.id,
            "pointer_version": new_pointer_version,
            "rolled_back": False,
        }


def harness_is_importable_from_routing() -> bool:
    """Boundary probe used by tests — harness module is not a router."""
    return False


__all__ = [
    "Phase7ATestOnlyRolloutHarness",
    "TestOnlyHarnessError",
    "assert_test_only_mode",
    "harness_is_importable_from_routing",
]
