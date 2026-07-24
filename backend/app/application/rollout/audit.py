"""Append-only rollout audit helpers for Phase 7A diagnostics."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.domain.models.rollout import PreviewRolloutAuditEventRecord


PHASE7A_EMITTABLE_EVENTS = frozenset(
    {
        "rollout_policy_changed",
        "eligibility_computed",
        "pointer_resolved",
        "history_mutation_attempted",
    }
)


def audit_event_sha256(
    *,
    request_id: int | None,
    event_type: str,
    actor_id: str,
    actor_role: str,
    policy_revision: str | None,
    metadata: dict[str, Any],
    created_at: str,
) -> str:
    payload = {
        "request_id": request_id,
        "event_type": event_type,
        "actor_id": actor_id,
        "actor_role": actor_role,
        "policy_revision": policy_revision,
        "metadata": metadata,
        "created_at": created_at,
    }
    material = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def append_audit_event(
    db: Session,
    *,
    request_id: int | None,
    event_type: str,
    actor_id: str,
    actor_role: str,
    policy_revision: str | None = None,
    decision_id: int | None = None,
    pointer_version_before: int | None = None,
    pointer_version_after: int | None = None,
    lineage_sha256: str | None = None,
    reason: str | None = None,
    ticket_ref: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> PreviewRolloutAuditEventRecord:
    if event_type not in PHASE7A_EMITTABLE_EVENTS:
        raise ValueError(f"Phase 7A cannot emit event_type={event_type!r}")
    meta = metadata or {}
    meta_json = json.dumps(meta, sort_keys=True, separators=(",", ":"))
    meta_sha = hashlib.sha256(meta_json.encode("utf-8")).hexdigest()
    created = datetime.utcnow()
    event_sha = audit_event_sha256(
        request_id=request_id,
        event_type=event_type,
        actor_id=actor_id,
        actor_role=actor_role,
        policy_revision=policy_revision,
        metadata=meta,
        created_at=created.isoformat(),
    )
    row = PreviewRolloutAuditEventRecord(
        request_id=request_id,
        event_type=event_type,
        actor_id=actor_id,
        actor_role=actor_role,
        policy_revision=policy_revision,
        decision_id=decision_id,
        pointer_version_before=pointer_version_before,
        pointer_version_after=pointer_version_after,
        lineage_sha256=lineage_sha256,
        reason=reason,
        ticket_ref=ticket_ref,
        metadata_json=meta_json,
        metadata_sha256=meta_sha,
        created_at=created,
        event_sha256=event_sha,
    )
    db.add(row)
    db.flush()
    return row


__all__ = [
    "PHASE7A_EMITTABLE_EVENTS",
    "append_audit_event",
    "audit_event_sha256",
]
