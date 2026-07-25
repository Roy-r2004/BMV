"""Append-only breaker metric sample helpers for Phase 7D."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.domain.models.rollout import PreviewBreakerMetricSampleRecord
from app.domain.schemas.breaker import BreakerMetricClass, SampleOutcome


def _sha(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def append_metric_sample(
    db: Session,
    *,
    metric_class: BreakerMetricClass,
    outcome: SampleOutcome,
    policy_revision: str,
    source_event_hash: str,
    request_id: int | None = None,
    decision_id: int | None = None,
    pointer_version: int | None = None,
    duration_ms: float | None = None,
    source_event_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    event_at: datetime | None = None,
) -> PreviewBreakerMetricSampleRecord | None:
    """Insert a metric sample; ignore duplicate source_event_hash."""
    existing = (
        db.query(PreviewBreakerMetricSampleRecord)
        .filter(PreviewBreakerMetricSampleRecord.source_event_hash == source_event_hash)
        .one_or_none()
    )
    if existing is not None:
        return existing
    meta = metadata or {}
    meta_json = json.dumps(meta, sort_keys=True, separators=(",", ":"))
    created = event_at or datetime.utcnow()
    payload = {
        "metric_class": metric_class,
        "outcome": outcome,
        "request_id": request_id,
        "decision_id": decision_id,
        "pointer_version": pointer_version,
        "duration_ms": duration_ms,
        "policy_revision": policy_revision,
        "source_event_hash": source_event_hash,
        "metadata_sha256": hashlib.sha256(meta_json.encode()).hexdigest(),
        "event_at": created.isoformat(),
    }
    row = PreviewBreakerMetricSampleRecord(
        event_at=created,
        metric_class=metric_class,
        outcome=outcome,
        request_id=request_id,
        decision_id=decision_id,
        pointer_version=pointer_version,
        duration_ms=duration_ms,
        policy_revision=policy_revision,
        source_event_id=source_event_id,
        source_event_hash=source_event_hash,
        metadata_json=meta_json,
        metadata_sha256=payload["metadata_sha256"],
        created_at=datetime.utcnow(),
        sample_sha256=_sha(payload),
    )
    db.add(row)
    db.flush()
    return row


__all__ = ["append_metric_sample"]
