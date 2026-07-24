"""Read-only serving-pointer resolver for Phase 7A.

Not wired into the production preview-serving path.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.models.rollout import PreviewServingPointerVersionRecord
from app.domain.schemas.rollout import ServingPointerView


def resolve_serving_pointer(db: Session, request_id: int) -> ServingPointerView:
    """Resolve current pointer or repository-default unset behavior."""
    if request_id < 1:
        raise ValueError("request_id must be a positive integer")
    row = (
        db.query(PreviewServingPointerVersionRecord)
        .filter(
            PreviewServingPointerVersionRecord.request_id == request_id,
            PreviewServingPointerVersionRecord.is_current.is_(True),
        )
        .one_or_none()
    )
    if row is None:
        return ServingPointerView(
            request_id=request_id,
            pointer_version=None,
            target_kind="unset",
            is_current=False,
        )
    target_kind = row.target_kind
    # Expose rollback pointer versions distinctly for diagnostics.
    if row.pointer_action == "rollback":
        target_kind = "rollback"
    return ServingPointerView(
        request_id=request_id,
        pointer_version=row.pointer_version,
        target_kind=target_kind,  # type: ignore[arg-type]
        candidate_revision_id=row.candidate_revision_id,
        legacy_preview_relpath=row.legacy_preview_relpath,
        effective_tier=row.effective_tier,
        effective_summary_id=row.effective_summary_id,
        summary_sha256=row.summary_sha256,
        candidate_manifest_sha256=row.candidate_manifest_sha256,
        previous_pointer_version=row.previous_pointer_version,
        created_at=row.created_at.isoformat() if row.created_at else None,
        is_current=bool(row.is_current),
        pointer_action=row.pointer_action,  # type: ignore[arg-type]
    )


__all__ = ["resolve_serving_pointer"]
