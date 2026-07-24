"""Read-only accepted v2 lineage lookup for shadow reuse_accepted."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.domain.models.preview_candidate import CandidateRevisionRecord
from app.domain.models.runtime_validation import CandidateValidationSummaryRecord
from app.domain.models.tier_orchestration import CandidateEffectiveTierSummaryRecord
from app.domain.models.visual_evaluation import CandidateVisualSummaryRecord


@dataclass(frozen=True)
class AcceptedLineage:
    candidate_revision_id: int
    effective_summary_id: int | None
    effective_summary_sha256: str | None
    candidate_manifest_sha256: str | None
    phase4_status: str
    phase5_status: str
    highest_accepted_tier: int
    lineage_sha256: str
    candidate_routes: tuple[str, ...] | None


def locate_latest_accepted_lineage(
    db: Session, request_id: int
) -> AcceptedLineage | None:
    summary = (
        db.query(CandidateEffectiveTierSummaryRecord)
        .filter(
            CandidateEffectiveTierSummaryRecord.request_id == request_id,
            CandidateEffectiveTierSummaryRecord.status.in_(
                ("tier_2_accepted", "tier_3_accepted")
            ),
        )
        .order_by(CandidateEffectiveTierSummaryRecord.id.desc())
        .first()
    )
    if summary is None:
        return None
    revision_id = (
        summary.last_accepted_candidate_revision_id
        or summary.derived_candidate_revision_id
        or summary.accepted_tier_1_revision_id
    )
    revision = (
        db.query(CandidateRevisionRecord)
        .filter(CandidateRevisionRecord.id == revision_id)
        .one_or_none()
    )
    phase4_status = "unknown"
    if summary.phase4_validation_summary_id:
        p4 = (
            db.query(CandidateValidationSummaryRecord)
            .filter(
                CandidateValidationSummaryRecord.id
                == summary.phase4_validation_summary_id
            )
            .one_or_none()
        )
        if p4 is not None:
            phase4_status = getattr(p4, "status", None) or "candidate_runtime_validated"
    phase5_status = "unknown"
    if summary.phase5_visual_summary_id:
        p5 = (
            db.query(CandidateVisualSummaryRecord)
            .filter(
                CandidateVisualSummaryRecord.id == summary.phase5_visual_summary_id
            )
            .one_or_none()
        )
        if p5 is not None:
            phase5_status = getattr(p5, "status", None) or "candidate_visual_accepted"
    manifest = None
    if revision is not None:
        manifest = revision.file_manifest_sha256 or revision.upstream_manifest_sha256
    return AcceptedLineage(
        candidate_revision_id=int(revision_id),
        effective_summary_id=int(summary.id),
        effective_summary_sha256=summary.summary_sha256,
        candidate_manifest_sha256=manifest,
        phase4_status=phase4_status,
        phase5_status=phase5_status,
        highest_accepted_tier=int(summary.highest_accepted_tier),
        lineage_sha256=summary.summary_sha256,
        candidate_routes=None,
    )


__all__ = ["AcceptedLineage", "locate_latest_accepted_lineage"]
