"""Synchronous apply health prechecks — no browsers/providers."""
from __future__ import annotations

from sqlalchemy.orm import Session, load_only

from app.core import config as app_config
from app.domain.models.preview_candidate import CandidateRevisionRecord
from app.domain.models.rollout import PreviewServingPointerVersionRecord
from app.domain.models.runtime_validation import CandidateValidationSummaryRecord
from app.domain.models.tier_orchestration import CandidateEffectiveTierSummaryRecord
from app.domain.models.visual_evaluation import CandidateVisualSummaryRecord
from app.domain.schemas.promotion import HealthPrecheckResult


def run_promote_health_precheck(
    db: Session,
    *,
    request_id: int,
    candidate_revision_id: int,
    effective_tier_summary_id: int,
    expected_manifest_sha256: str | None,
    phase4_summary_id: int | None,
    phase5_summary_id: int | None,
    allowlisted: bool,
    rollout_percent_zero: bool,
    flags_enabled: bool,
    breaker_not_open: bool,
    decision_exists: bool,
    latest_status_approved: bool,
    pointer_version_matches: bool,
) -> HealthPrecheckResult:
    reasons: list[str] = []
    candidate = (
        db.query(CandidateRevisionRecord)
        .options(
            load_only(
                CandidateRevisionRecord.id,
                CandidateRevisionRecord.request_id,
                CandidateRevisionRecord.workspace_relpath,
                CandidateRevisionRecord.file_manifest_sha256,
                CandidateRevisionRecord.upstream_manifest_sha256,
            )
        )
        .filter(CandidateRevisionRecord.id == candidate_revision_id)
        .one_or_none()
    )
    candidate_exists = candidate is not None and candidate.request_id == request_id
    if not candidate_exists:
        reasons.append("candidate_missing")

    manifest_matches = False
    dist_exists = False
    entry_exists = False
    if candidate is not None:
        manifest = candidate.file_manifest_sha256 or candidate.upstream_manifest_sha256
        manifest_matches = (
            expected_manifest_sha256 is None or manifest == expected_manifest_sha256
        )
        if not manifest_matches:
            reasons.append("manifest_mismatch")
        if candidate.workspace_relpath:
            root = app_config.settings.PREVIEW_CANDIDATES_DIR.resolve(strict=False)
            workspace = (root / candidate.workspace_relpath).resolve(strict=False)
            try:
                workspace.relative_to(root)
                dist = workspace / "dist"
                dist_exists = dist.is_dir()
                entry_exists = (dist / "index.html").is_file()
            except ValueError:
                reasons.append("workspace_escape")
        if not dist_exists:
            reasons.append("dist_missing")
        if not entry_exists:
            reasons.append("entry_missing")

    phase4_ok = False
    if phase4_summary_id:
        p4 = (
            db.query(CandidateValidationSummaryRecord)
            .options(
                load_only(
                    CandidateValidationSummaryRecord.id,
                    CandidateValidationSummaryRecord.status,
                )
            )
            .filter(CandidateValidationSummaryRecord.id == phase4_summary_id)
            .one_or_none()
        )
        phase4_ok = bool(
            p4 and getattr(p4, "status", "") == "candidate_runtime_validated"
        )
    if not phase4_ok:
        reasons.append("phase4_not_validated")

    phase5_ok = False
    if phase5_summary_id:
        p5 = (
            db.query(CandidateVisualSummaryRecord)
            .options(
                load_only(
                    CandidateVisualSummaryRecord.id,
                    CandidateVisualSummaryRecord.status,
                )
            )
            .filter(CandidateVisualSummaryRecord.id == phase5_summary_id)
            .one_or_none()
        )
        phase5_ok = bool(
            p5 and getattr(p5, "status", "") == "candidate_visual_accepted"
        )
    if not phase5_ok:
        reasons.append("phase5_not_accepted")

    effective_tier_ok = False
    summary = (
        db.query(CandidateEffectiveTierSummaryRecord)
        .options(
            load_only(
                CandidateEffectiveTierSummaryRecord.id,
                CandidateEffectiveTierSummaryRecord.request_id,
                CandidateEffectiveTierSummaryRecord.status,
                CandidateEffectiveTierSummaryRecord.highest_accepted_tier,
            )
        )
        .filter(CandidateEffectiveTierSummaryRecord.id == effective_tier_summary_id)
        .one_or_none()
    )
    if summary is not None and summary.request_id == request_id:
        effective_tier_ok = summary.status in (
            "tier_2_accepted",
            "tier_3_accepted",
        )
    if not effective_tier_ok:
        reasons.append("effective_tier_not_accepted")

    if not allowlisted:
        reasons.append("not_allowlisted")
    if not rollout_percent_zero:
        reasons.append("rollout_percent_nonzero")
    if not flags_enabled:
        reasons.append("flags_disabled")
    if not breaker_not_open:
        reasons.append("breaker_open")
    if not decision_exists:
        reasons.append("decision_missing")
    if not latest_status_approved:
        reasons.append("not_approved")
    if not pointer_version_matches:
        reasons.append("pointer_version_mismatch")

    passed = not reasons
    return HealthPrecheckResult(
        passed=passed,
        decision_exists=decision_exists,
        latest_status_approved=latest_status_approved,
        pointer_version_matches=pointer_version_matches,
        allowlisted=allowlisted,
        rollout_percent_zero=rollout_percent_zero,
        flags_enabled=flags_enabled,
        breaker_not_open=breaker_not_open,
        candidate_exists=candidate_exists,
        manifest_matches=manifest_matches,
        dist_exists=dist_exists,
        entry_exists=entry_exists,
        phase4_ok=phase4_ok,
        phase5_ok=phase5_ok,
        effective_tier_ok=effective_tier_ok,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def verify_rollback_target(
    db: Session,
    *,
    request_id: int,
    target_pointer_version: int,
) -> tuple[bool, str | None, PreviewServingPointerVersionRecord | None]:
    row = (
        db.query(PreviewServingPointerVersionRecord)
        .filter(
            PreviewServingPointerVersionRecord.request_id == request_id,
            PreviewServingPointerVersionRecord.pointer_version
            == target_pointer_version,
        )
        .one_or_none()
    )
    if row is None:
        return False, "rollback_target_missing", None
    if row.target_kind == "v2_candidate" and row.candidate_revision_id:
        dist = None
        candidate = (
            db.query(CandidateRevisionRecord)
            .options(
                load_only(
                    CandidateRevisionRecord.id,
                    CandidateRevisionRecord.workspace_relpath,
                )
            )
            .filter(CandidateRevisionRecord.id == row.candidate_revision_id)
            .one_or_none()
        )
        if candidate and candidate.workspace_relpath:
            root = app_config.settings.PREVIEW_CANDIDATES_DIR.resolve(strict=False)
            workspace = (root / candidate.workspace_relpath).resolve(strict=False)
            try:
                workspace.relative_to(root)
                dist = workspace / "dist"
            except ValueError:
                return False, "rollback_target_workspace_invalid", None
        if dist is None or not dist.is_dir() or not (dist / "index.html").is_file():
            return False, "rollback_target_files_missing", None
    return True, None, row


__all__ = ["run_promote_health_precheck", "verify_rollback_target"]
