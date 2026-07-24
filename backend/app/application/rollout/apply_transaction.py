"""Atomic pointer-swap transaction for Phase 7C apply (admin-only callers)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.application.rollout.audit import append_audit_event
from app.domain.models.rollout import (
    PreviewPromotionDecisionRecord,
    PreviewPromotionDecisionStatusEventRecord,
    PreviewServingPointerVersionRecord,
)


class PointerApplyError(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _pointer_sha(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _event_sha(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def apply_pointer_swap_transaction(
    db: Session,
    *,
    request_id: int,
    decision: PreviewPromotionDecisionRecord,
    expected_pointer_version: int | None,
    apply_actor_id: str,
    policy_revision: str,
    new_target_kind: str,
    pointer_action: str,
    candidate_revision_id: int | None,
    legacy_preview_relpath: str | None,
    effective_tier: int | None,
    summary_sha256: str | None,
    candidate_manifest_sha256: str | None,
    initialize_legacy_first: bool,
) -> PreviewServingPointerVersionRecord:
    """Execute approved pointer swap. Caller must have validated eligibility."""
    dialect = db.get_bind().dialect.name
    query = db.query(PreviewServingPointerVersionRecord).filter(
        PreviewServingPointerVersionRecord.request_id == request_id,
        PreviewServingPointerVersionRecord.is_current.is_(True),
    )
    if dialect == "postgresql":
        query = query.with_for_update()
    current = query.one_or_none()
    if dialect == "postgresql" and current is None:
        # Serialize first-pointer creation when no current row exists.
        db.execute(
            text("SELECT pg_advisory_xact_lock(:k)"),
            {"k": int(request_id)},
        )
        current = query.one_or_none()
    current_version = None if current is None else current.pointer_version
    if current is None:
        if expected_pointer_version is not None:
            raise PointerApplyError("pointer_version_conflict")
    elif current.pointer_version != expected_pointer_version:
        raise PointerApplyError("pointer_version_conflict")

    previous_for_new = current_version
    if current is None and initialize_legacy_first and legacy_preview_relpath:
        init_payload = {
            "request_id": request_id,
            "pointer_version": 1,
            "target_kind": "legacy_v1",
            "pointer_action": "initialize",
        }
        init = PreviewServingPointerVersionRecord(
            request_id=request_id,
            pointer_version=1,
            target_kind="legacy_v1",
            candidate_revision_id=None,
            legacy_preview_relpath=legacy_preview_relpath,
            effective_tier=None,
            summary_sha256=None,
            candidate_manifest_sha256=None,
            previous_pointer_version=None,
            pointer_action="initialize",
            decision_id=decision.id,
            actor_id=apply_actor_id,
            policy_revision=policy_revision,
            created_at=datetime.utcnow(),
            is_current=True,
            pointer_sha256=_pointer_sha(init_payload),
        )
        db.add(init)
        db.flush()
        current = init
        previous_for_new = 1
        current.is_current = False
        db.flush()

    new_version = 1 if previous_for_new is None else previous_for_new + 1
    if current is not None and current.is_current:
        current.is_current = False
        db.flush()

    pointer_payload = {
        "request_id": request_id,
        "pointer_version": new_version,
        "target_kind": new_target_kind,
        "pointer_action": pointer_action,
        "decision_id": decision.id,
        "candidate_revision_id": candidate_revision_id,
    }
    new_pointer = PreviewServingPointerVersionRecord(
        request_id=request_id,
        pointer_version=new_version,
        target_kind=new_target_kind,
        candidate_revision_id=candidate_revision_id,
        legacy_preview_relpath=legacy_preview_relpath
        if new_target_kind == "legacy_v1"
        else None,
        effective_tier=effective_tier,
        summary_sha256=summary_sha256,
        candidate_manifest_sha256=candidate_manifest_sha256,
        previous_pointer_version=previous_for_new,
        pointer_action=pointer_action,
        decision_id=decision.id,
        actor_id=apply_actor_id,
        policy_revision=policy_revision,
        created_at=datetime.utcnow(),
        is_current=True,
        pointer_sha256=_pointer_sha(pointer_payload),
    )
    db.add(new_pointer)
    db.flush()

    event_payload = {
        "decision_id": decision.id,
        "status": "applied",
        "actor_id": apply_actor_id,
        "pointer_version": new_version,
    }
    db.add(
        PreviewPromotionDecisionStatusEventRecord(
            decision_id=decision.id,
            status="applied",
            actor_id=apply_actor_id,
            reason="phase7c_apply",
            created_at=datetime.utcnow(),
            event_sha256=_event_sha(event_payload),
        )
    )
    # Store resulting version on decision via new decision? Decision is append-only
    # — record resulting version only in pointer + audit metadata.

    audit_type = (
        "rollback_completed" if pointer_action == "rollback" else "pointer_changed"
    )
    append_audit_event(
        db,
        request_id=request_id,
        event_type=audit_type,
        actor_id=apply_actor_id,
        actor_role="rollout_admin",
        policy_revision=policy_revision,
        decision_id=decision.id,
        pointer_version_before=previous_for_new,
        pointer_version_after=new_version,
        lineage_sha256=decision.lineage_sha256,
        reason=decision.reason,
        ticket_ref=decision.ticket_ref,
        metadata={
            "pointer_action": pointer_action,
            "target_kind": new_target_kind,
            "candidate_revision_id": candidate_revision_id,
            "initialize_legacy_predecessor": initialize_legacy_first,
            "no_rollback_predecessor": previous_for_new is None,
            "no_partial": True,
            "no_pointer_mutation_outside_txn": True,
        },
    )
    db.flush()
    return new_pointer


__all__ = ["PointerApplyError", "apply_pointer_swap_transaction"]
