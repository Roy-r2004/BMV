"""Read-only serving pointer resolution for Phase 7C Option A.

Hot path may import only this module + models/session — never promotion
writers, apply transactions, or provider factories.
"""
from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session, load_only

from app.core import config as app_config
from app.domain.models.preview_candidate import CandidateRevisionRecord
from app.domain.models.rollout import (
    PreviewRolloutAuditEventRecord,
    PreviewServingPointerVersionRecord,
)
from app.infrastructure.db.session import SessionLocal

_log = logging.getLogger("rollout.serving_resolve")

# Bounded so customer fallback never waits on audit persistence.
SERVING_FALLBACK_AUDIT_TIMEOUT_SECONDS = 0.25


def _candidate_dist(db: Session, candidate_revision_id: int) -> Path | None:
    row = (
        db.query(CandidateRevisionRecord)
        .options(
            load_only(
                CandidateRevisionRecord.id,
                CandidateRevisionRecord.workspace_relpath,
            )
        )
        .filter(CandidateRevisionRecord.id == candidate_revision_id)
        .one_or_none()
    )
    if row is None or not row.workspace_relpath:
        return None
    root = app_config.settings.PREVIEW_CANDIDATES_DIR.resolve(strict=False)
    workspace = (root / row.workspace_relpath).resolve(strict=False)
    try:
        workspace.relative_to(root)
    except ValueError:
        return None
    dist = workspace / "dist"
    if dist.is_dir() and (dist / "index.html").is_file():
        return dist
    return None


def _legacy_pointer_dist(
    db: Session, request_id: int, legacy_get_dist_dir: Callable[[int], Path]
) -> tuple[Path | None, int | None]:
    """Find latest verified legacy_v1 pointer dist for the request."""
    rows = (
        db.query(PreviewServingPointerVersionRecord)
        .filter(
            PreviewServingPointerVersionRecord.request_id == request_id,
            PreviewServingPointerVersionRecord.target_kind == "legacy_v1",
        )
        .order_by(PreviewServingPointerVersionRecord.pointer_version.desc())
        .all()
    )
    for row in rows:
        dist = legacy_get_dist_dir(request_id)
        if dist.is_dir() and (dist / "index.html").is_file():
            if row.legacy_preview_relpath:
                return dist, row.pointer_version
            return dist, row.pointer_version
    return None, None


def _persist_serving_fallback_audit(
    *,
    request_id: int,
    unhealthy_version: int | None,
    fallback_kind: str,
    fallback_pointer_version: int | None,
    reason: str,
    details: dict,
) -> None:
    """Insert audit on a dedicated short-lived session (no pointer mutation)."""
    db = SessionLocal()
    try:
        meta = {
            "unhealthy_pointer_version": unhealthy_version,
            "fallback_target_kind": fallback_kind,
            "fallback_pointer_version": fallback_pointer_version,
            "reason": reason,
            "no_pointer_mutation": True,
            **details,
        }
        meta_json = json.dumps(meta, sort_keys=True, separators=(",", ":"))
        created = datetime.utcnow()
        event_sha = hashlib.sha256(
            f"serving_fallback:{request_id}:{created.isoformat()}:{meta_json}".encode()
        ).hexdigest()
        db.add(
            PreviewRolloutAuditEventRecord(
                request_id=request_id,
                event_type="serving_fallback",
                actor_id="system:serving-resolve",
                actor_role="rollout_viewer",
                policy_revision=app_config.settings.V2_PHASE7_POLICY_REVISION,
                pointer_version_before=unhealthy_version,
                pointer_version_after=unhealthy_version,
                reason=reason,
                metadata_json=meta_json,
                metadata_sha256=hashlib.sha256(meta_json.encode()).hexdigest(),
                created_at=created,
                event_sha256=event_sha,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _append_fallback_audit_best_effort(
    *,
    request_id: int,
    unhealthy_version: int | None,
    fallback_kind: str,
    fallback_pointer_version: int | None,
    reason: str,
    details: dict,
) -> None:
    """Best-effort audit with a hard timeout; never blocks customer fallback."""
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(
            _persist_serving_fallback_audit,
            request_id=request_id,
            unhealthy_version=unhealthy_version,
            fallback_kind=fallback_kind,
            fallback_pointer_version=fallback_pointer_version,
            reason=reason,
            details=details,
        )
        future.result(timeout=SERVING_FALLBACK_AUDIT_TIMEOUT_SECONDS)
    except FuturesTimeoutError:
        _log.error(
            "serving_fallback audit timed out request_id=%s reason=%s "
            "timeout_s=%s",
            request_id,
            reason,
            SERVING_FALLBACK_AUDIT_TIMEOUT_SECONDS,
            extra={
                "event": "serving_fallback_audit_timeout",
                "request_id": request_id,
                "reason": reason,
                "timeout_seconds": SERVING_FALLBACK_AUDIT_TIMEOUT_SECONDS,
                "no_pointer_mutation": True,
            },
        )
    except Exception:  # noqa: BLE001
        _log.exception(
            "serving_fallback audit failed request_id=%s reason=%s",
            request_id,
            reason,
            extra={
                "event": "serving_fallback_audit_failed",
                "request_id": request_id,
                "reason": reason,
                "no_pointer_mutation": True,
            },
        )
    finally:
        # Do not wait for a stuck audit thread — customer response must proceed.
        pool.shutdown(wait=False, cancel_futures=True)


def resolve_dist_for_serving(
    request_id: int,
    *,
    legacy_get_dist_dir: Callable[[int], Path],
) -> Path:
    """Resolve dist with pointer verification and approved fallback order."""
    db = SessionLocal()
    try:
        current = (
            db.query(PreviewServingPointerVersionRecord)
            .filter(
                PreviewServingPointerVersionRecord.request_id == request_id,
                PreviewServingPointerVersionRecord.is_current.is_(True),
            )
            .one_or_none()
        )
        if current is None:
            return legacy_get_dist_dir(request_id)

        if current.target_kind == "v2_candidate" and current.candidate_revision_id:
            dist = _candidate_dist(db, current.candidate_revision_id)
            if dist is not None:
                return dist
            # Capture immutable pointer fields before any audit side-effect.
            unhealthy_version = current.pointer_version
            candidate_revision_id = current.candidate_revision_id
            legacy_dist, legacy_ver = _legacy_pointer_dist(
                db, request_id, legacy_get_dist_dir
            )
            if legacy_dist is not None:
                # Close read session before audit so locks are not held.
                db.close()
                db = None  # type: ignore[assignment]
                _append_fallback_audit_best_effort(
                    request_id=request_id,
                    unhealthy_version=unhealthy_version,
                    fallback_kind="legacy_v1",
                    fallback_pointer_version=legacy_ver,
                    reason="v2_dist_unhealthy",
                    details={"candidate_revision_id": candidate_revision_id},
                )
                return legacy_dist
            workspace = legacy_get_dist_dir(request_id)
            db.close()
            db = None  # type: ignore[assignment]
            _append_fallback_audit_best_effort(
                request_id=request_id,
                unhealthy_version=unhealthy_version,
                fallback_kind="legacy_workspace",
                fallback_pointer_version=None,
                reason="v2_dist_unhealthy_no_legacy_pointer",
                details={"candidate_revision_id": candidate_revision_id},
            )
            return workspace

        if current.target_kind in ("legacy_v1", "rollback"):
            if current.target_kind == "rollback" and current.candidate_revision_id:
                dist = _candidate_dist(db, current.candidate_revision_id)
                if dist is not None:
                    return dist
            return legacy_get_dist_dir(request_id)

        return legacy_get_dist_dir(request_id)
    finally:
        if db is not None:
            db.close()


__all__ = [
    "SERVING_FALLBACK_AUDIT_TIMEOUT_SECONDS",
    "resolve_dist_for_serving",
]
