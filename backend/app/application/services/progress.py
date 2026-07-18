"""Real-time progress tracking for generation pipelines.

Every key stage in the pipeline calls `emit()` which persists a JSON snapshot
to `Request.generation_log`. The frontend polls GET /api/requests/{id}/progress
and renders live stage names, real file names, and accurate % values.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.domain.models.request import Request

# Stages that mean the customer-facing generation UI can stop polling.
TERMINAL_STAGES = frozenset(
    {
        "done",
        "failed",
        "ready",
        "refine_done",
        "refine_failed",
        "refine_reverted",
    }
)

# Terminal customer-facing failure (intermediate build_failed can still recover).
FAILED_STAGES = frozenset(
    {
        "failed",
        "refine_failed",
    }
)

# Relative order for customer-facing progress. Used so retries never rewind the UI.
_STAGE_ORDER: dict[str, int] = {
    "starting": 0,
    "analyze": 1,
    "blueprint": 2,
    "demo": 3,
    "appspec": 4,
    "appspec_failed": 4,
    "codegen": 5,
    "architect": 5,
    "critic": 6,
    "visual_critic": 6,
    "build": 7,
    "build_failed": 7,
    "build_done": 8,
    "tech": 8,
    "proposal": 9,
    "ready": 10,
    "done": 11,
    "failed": 12,
    "refine": 1,
    "refine_done": 11,
    "refine_failed": 12,
    "refine_reverted": 11,
}

# Stages that intentionally reset the progress bar (chat redesign / fresh run).
_RESET_STAGES = frozenset({"refine", "starting", "analyze"})

# Leaving these always starts a new progress run (customer retry or pipeline retry).
_TERMINAL_RESET_STAGES = frozenset(
    {
        "failed",
        "done",
        "ready",
        "refine_done",
        "refine_failed",
        "refine_reverted",
    }
)


def parse_progress_snapshot(raw: str | None) -> dict[str, Any]:
    """Parse generation_log JSON into a dict; empty dict on missing/invalid."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def is_request_generating(req: Request) -> bool:
    """True while the customer should still see the live progress screen.

    Uses progress stage as source of truth (not blueprint presence). Blueprint
    lands early; codegen/build can run for many more minutes afterward.
    """
    if getattr(req, "status", None) == "failed":
        return False

    status = getattr(req, "status", None) or ""
    # Post-generation hand-off states are never "still generating".
    if status in {"reviewing", "approved", "rejected", "delivered"}:
        return False

    snap = parse_progress_snapshot(getattr(req, "generation_log", None))
    stage = str(snap.get("stage") or "").strip()

    if stage in TERMINAL_STAGES:
        return False

    if stage:
        return True

    # No progress log yet (just created) — generating until we have a finished package.
    has_package = bool(getattr(req, "mvp_blueprint", None)) and bool(
        getattr(req, "generated_pages", None) or getattr(req, "visual_demo_json", None)
    )
    if has_package:
        return False

    return status == "new" or status == ""


def progress_payload(req: Request) -> dict[str, Any]:
    """API payload for GET /progress including terminal / generating flags."""
    snap = parse_progress_snapshot(getattr(req, "generation_log", None))
    if not snap:
        snap = {
            "stage": "starting",
            "label": "Starting generation...",
            "pct": 0,
            "detail": "",
            "files_done": 0,
            "files_total": 0,
            "log": [],
        }
    stage = str(snap.get("stage") or "starting")
    generating = is_request_generating(req)
    failed = (
        getattr(req, "status", None) == "failed"
        or stage in FAILED_STAGES
        or stage == "failed"
    )
    return {
        **snap,
        "stage": stage,
        "label": snap.get("label") or "Working...",
        "pct": int(snap.get("pct") or 0),
        "detail": snap.get("detail") or "",
        "files_done": int(snap.get("files_done") or 0),
        "files_total": int(snap.get("files_total") or 0),
        "log": snap.get("log") if isinstance(snap.get("log"), list) else [],
        "updated_at": snap.get("updated_at") or "",
        "is_generating": generating,
        "is_failed": bool(failed and not generating),
        "request_status": getattr(req, "status", None) or "new",
    }


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
    """Persist a progress snapshot and append a log event. Never raises.

    Stage and pct are monotonic within a generation run so a preview retry
    (which re-emits early stages) does not rewind the customer UI.
    """
    try:
        req = db.query(Request).filter(Request.id == req_id).first()
        if not req:
            return

        log: list[dict] = []
        prev_stage = ""
        prev_pct = 0
        prev_files_done = 0
        prev_files_total = 0
        if req.generation_log:
            try:
                existing = json.loads(req.generation_log)
                if isinstance(existing, dict):
                    log = existing.get("log", []) if isinstance(existing.get("log"), list) else []
                    prev_stage = str(existing.get("stage") or "")
                    prev_pct = int(existing.get("pct") or 0)
                    prev_files_done = int(existing.get("files_done") or 0)
                    prev_files_total = int(existing.get("files_total") or 0)
            except Exception:
                pass

        log.append({
            "t": int(datetime.now(timezone.utc).timestamp()),
            "msg": label,
        })

        reset = (
            (stage in _RESET_STAGES and prev_stage not in _RESET_STAGES)
            or prev_stage in _TERMINAL_RESET_STAGES
        )
        if reset:
            clamped_stage = stage
            clamped_pct = max(0, min(100, pct))
            clamped_files_done = files_done
            clamped_files_total = files_total
        else:
            prev_order = _STAGE_ORDER.get(prev_stage, -1)
            new_order = _STAGE_ORDER.get(stage, prev_order)
            # Never move the graph backward on internal retries; keep advancing label/detail.
            if new_order < prev_order and stage not in FAILED_STAGES | {"done", "ready"}:
                clamped_stage = prev_stage or stage
            else:
                clamped_stage = stage
            clamped_pct = max(prev_pct, max(0, min(100, pct)))
            clamped_files_done = max(prev_files_done, files_done)
            clamped_files_total = max(prev_files_total, files_total)


        snapshot = {
            "stage": clamped_stage,
            "label": label,
            "pct": clamped_pct,
            "detail": detail,
            "files_done": clamped_files_done,
            "files_total": clamped_files_total,
            "log": log[-50:],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        req.generation_log = json.dumps(snapshot)
        db.commit()
    except Exception:
        pass  # Progress tracking must never crash the pipeline
