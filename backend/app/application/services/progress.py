"""Real-time progress tracking for generation pipelines.

Every key stage in the pipeline calls `emit()` which persists a JSON snapshot
to `Request.generation_log`. The frontend polls GET /api/requests/{id}/progress
and renders live stage names, real file names, and accurate % values.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.domain.models.request import Request


def emit(
    db: Session,
    req_id: int,
    stage: str,
    label: str,
    pct: int,
    detail: str = "",
    files_done: int = 0,
    files_total: int = 0,
) -> None:
    """Persist a progress snapshot and append a log event. Never raises."""
    try:
        req = db.query(Request).filter(Request.id == req_id).first()
        if not req:
            return

        log: list[dict] = []
        if req.generation_log:
            try:
                existing = json.loads(req.generation_log)
                log = existing.get("log", [])
            except Exception:
                pass

        log.append({
            "t": int(datetime.now(timezone.utc).timestamp()),
            "msg": label,
        })

        snapshot = {
            "stage": stage,
            "label": label,
            "pct": max(0, min(100, pct)),
            "detail": detail,
            "files_done": files_done,
            "files_total": files_total,
            "log": log[-50:],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        req.generation_log = json.dumps(snapshot)
        db.commit()
    except Exception:
        pass  # Progress tracking must never crash the pipeline
