"""In-process Tier 2 generation job for approved Expanded Preview requests."""
from __future__ import annotations

import threading
from datetime import datetime

from app.application.expanded_preview.phase5_loader import load_accepted_tier1_phase5_result
from app.application.expanded_preview.service import generation_lock_for
from app.application.tier_orchestration.service import orchestrate_v2_tier_2
from app.core.config import settings
from app.domain.models import Request
from app.domain.models.expanded_preview import (
    ExpandedPreviewGenerationClaimRecord,
    ExpandedPreviewRequestRecord,
    ExpandedPreviewStatusEventRecord,
)
from app.infrastructure.ai_providers.factory import get_ai_provider
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.logging import get_logger
from app.infrastructure.templating.renderer import get_template_renderer

log = get_logger("ExpandedPreviewJob")


def _append_terminal(
    db,
    *,
    row: ExpandedPreviewRequestRecord,
    to_status: str,
    reason: str | None,
) -> None:
    import hashlib
    import json
    import secrets

    created = datetime.utcnow()
    payload = {
        "expanded_preview_id": row.id,
        "from_status": row.current_status,
        "to_status": to_status,
        "actor_id": "system:tier2_job",
        "actor_role": "system",
        "reason": reason,
        "created_at": created.isoformat(),
        "nonce": secrets.token_hex(8),
    }
    event_sha = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    db.add(
        ExpandedPreviewStatusEventRecord(
            expanded_preview_id=row.id,
            from_status=row.current_status,
            to_status=to_status,
            actor_id="system:tier2_job",
            actor_role="system",
            reason=reason,
            internal_notes=None,
            event_sha256=event_sha,
            created_at=created,
        )
    )
    row.current_status = to_status
    row.updated_at = created
    row.generation_finished_at = created


def _run_job(
    *,
    expanded_preview_id: int,
    request_id: int,
    claim_token: str,
) -> None:
    lock = generation_lock_for(expanded_preview_id)
    if not lock.acquire(blocking=False):
        log.warning(
            "tier2_job_skipped_lock_held expanded_preview_id=%s", expanded_preview_id
        )
        return
    db = SessionLocal()
    try:
        row = db.get(ExpandedPreviewRequestRecord, expanded_preview_id)
        if row is None:
            return
        claim = (
            db.query(ExpandedPreviewGenerationClaimRecord)
            .filter(
                ExpandedPreviewGenerationClaimRecord.expanded_preview_id
                == expanded_preview_id,
                ExpandedPreviewGenerationClaimRecord.claim_token == claim_token,
                ExpandedPreviewGenerationClaimRecord.active.is_(True),
            )
            .first()
        )
        if claim is None:
            log.warning(
                "tier2_job_claim_missing expanded_preview_id=%s", expanded_preview_id
            )
            return
        if row.current_status != "generation_started":
            return
        if not settings.V2_TIER2_GENERATION_ENABLED:
            row.generation_error = "Tier 2 capability disabled"
            _append_terminal(
                db, row=row, to_status="generation_failed", reason="capability_disabled"
            )
            claim.active = False
            claim.released_at = datetime.utcnow()
            db.commit()
            return

        req = db.get(Request, request_id)
        if req is None:
            row.generation_error = "request_missing"
            _append_terminal(
                db, row=row, to_status="generation_failed", reason="request_missing"
            )
            claim.active = False
            claim.released_at = datetime.utcnow()
            db.commit()
            return

        phase5, _rev, _visual = load_accepted_tier1_phase5_result(
            db, request_id=request_id
        )
        # Preserve Tier 1 customer preview payload before orchestration.
        tier1_pages = req.generated_pages
        result = orchestrate_v2_tier_2(
            db,
            request_id,
            get_ai_provider(),
            get_template_renderer(),
            req=req,
            phase5_result=phase5,
        )
        contract = dict(result.get("preview_contract") or {})
        status = contract.get("status")
        summary = dict(contract.get("effective_tier_summary") or {})
        tier2_ref = contract.get("candidate_revision") or {}
        visual_ref = contract.get("visual_evaluation_summary") or {}
        derived_id = (
            summary.get("derived_candidate_revision_id")
            or summary.get("last_accepted_candidate_revision_id")
            or tier2_ref.get("id")
        )
        # Never auto-publish; restore Tier 1 preview surface for the customer.
        req.generated_pages = tier1_pages
        if status == "tier_2_accepted" and derived_id:
            row.tier_2_candidate_revision_id = int(derived_id)
            if visual_ref.get("id"):
                row.tier_2_visual_summary_id = int(visual_ref["id"])
            row.generation_error = None
            _append_terminal(
                db,
                row=row,
                to_status="generation_completed",
                reason="tier2_generation_completed",
            )
        else:
            # Tier 1 remains the customer preview; record failure without publish.
            if derived_id:
                row.tier_2_candidate_revision_id = int(derived_id)
            row.generation_error = f"tier2_failed:{status}"
            _append_terminal(
                db,
                row=row,
                to_status="generation_failed",
                reason=row.generation_error,
            )
        claim.active = False
        claim.released_at = datetime.utcnow()
        db.commit()
    except Exception as exc:  # noqa: BLE001 - persist failure terminal state
        log.exception(
            "tier2_job_failed expanded_preview_id=%s", expanded_preview_id
        )
        try:
            db.rollback()
            row = db.get(ExpandedPreviewRequestRecord, expanded_preview_id)
            claim = (
                db.query(ExpandedPreviewGenerationClaimRecord)
                .filter(
                    ExpandedPreviewGenerationClaimRecord.expanded_preview_id
                    == expanded_preview_id,
                    ExpandedPreviewGenerationClaimRecord.claim_token == claim_token,
                )
                .first()
            )
            if row is not None and row.current_status == "generation_started":
                row.generation_error = str(exc)[:2000]
                _append_terminal(
                    db,
                    row=row,
                    to_status="generation_failed",
                    reason="tier2_exception",
                )
            if claim is not None:
                claim.active = False
                claim.released_at = datetime.utcnow()
            db.commit()
        except Exception:  # noqa: BLE001
            log.exception("tier2_job_failure_persist_failed")
    finally:
        db.close()
        lock.release()


def spawn_tier2_generation_job(
    *,
    expanded_preview_id: int,
    request_id: int,
    claim_token: str,
) -> None:
    thread = threading.Thread(
        target=_run_job,
        kwargs={
            "expanded_preview_id": expanded_preview_id,
            "request_id": request_id,
            "claim_token": claim_token,
        },
        daemon=True,
        name=f"expanded-preview-tier2-{expanded_preview_id}",
    )
    thread.start()


__all__ = ["spawn_tier2_generation_job"]
