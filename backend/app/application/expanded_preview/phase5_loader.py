"""Rebuild a Phase 5 result envelope from accepted Tier 1 DB lineage."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.models import (
    CandidateRevisionRecord,
    CandidateVisualSummaryRecord,
)


class ExpandedPreviewLineageError(RuntimeError):
    """Accepted Tier 1 lineage is missing or invalid."""


def load_accepted_tier1_phase5_result(
    db: Session, *, request_id: int
) -> tuple[dict, CandidateRevisionRecord, CandidateVisualSummaryRecord]:
    visual = (
        db.query(CandidateVisualSummaryRecord)
        .filter(
            CandidateVisualSummaryRecord.request_id == request_id,
            CandidateVisualSummaryRecord.status == "candidate_visual_accepted",
        )
        .order_by(CandidateVisualSummaryRecord.id.desc())
        .first()
    )
    if visual is None:
        raise ExpandedPreviewLineageError(
            "No accepted Tier 1 visual summary for this request"
        )
    revision = db.get(CandidateRevisionRecord, visual.candidate_revision_id)
    if (
        revision is None
        or revision.request_id != request_id
        or int(getattr(revision, "target_tier", 1) or 1) != 1
    ):
        raise ExpandedPreviewLineageError(
            "Accepted Tier 1 candidate revision lineage is invalid"
        )
    phase5 = {
        "preview_contract": {
            "status": "candidate_visual_accepted",
            "target_tier": 1,
            "candidate_revision": {
                "id": revision.id,
                "file_manifest_sha256": revision.file_manifest_sha256,
            },
            "visual_evaluation_summary": {
                "id": visual.id,
                "sha256": visual.artifact_sha256,
            },
        }
    }
    return phase5, revision, visual


__all__ = [
    "ExpandedPreviewLineageError",
    "load_accepted_tier1_phase5_result",
]
