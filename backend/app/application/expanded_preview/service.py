"""Commercial Expanded Preview lifecycle service."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import uuid
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.application.expanded_preview.authorization import (
    CommercialAuthorizationError,
    reject_client_supplied_roles,
    require_permission,
)
from app.application.expanded_preview.phase5_loader import (
    ExpandedPreviewLineageError,
    load_accepted_tier1_phase5_result,
)
from app.core.config import settings
from app.domain.models import (
    CandidateRevisionRecord,
    CandidateScreenshotRecord,
    CandidateValidationSummaryRecord,
    CandidateVisualFindingRecord,
    CandidateVisualSummaryRecord,
    Request,
)
from app.domain.models.expanded_preview import (
    OPEN_STATUSES,
    ExpandedPreviewGenerationClaimRecord,
    ExpandedPreviewPublicationRecord,
    ExpandedPreviewRequestRecord,
    ExpandedPreviewStatusEventRecord,
)
from app.domain.schemas.expanded_preview import (
    CustomerStatus,
    ExpandedPreviewAdminView,
    ExpandedPreviewApproveBody,
    ExpandedPreviewCreateBody,
    ExpandedPreviewCustomerView,
    ExpandedPreviewListItem,
    ExpandedPreviewPublishBody,
    ExpandedPreviewRejectBody,
    ExpandedPreviewReviewBody,
    ExpandedPreviewStartBody,
    ExpandedPreviewStatusEventView,
    TrustedCommercialActor,
)


class ExpandedPreviewServiceError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _canonical_sha256(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _customer_status(lifecycle: str) -> CustomerStatus:
    mapping: dict[str, CustomerStatus] = {
        "requested": "requested",
        "approved": "approved",
        "rejected": "rejected",
        "generation_started": "generating",
        "generation_completed": "under_review",
        "generation_failed": "failed",
        "review_accepted": "ready",
        "review_rejected": "rejected",
        "published": "ready",
    }
    # "under_review" for requested awaiting admin is clearer for customers
    if lifecycle == "requested":
        return "under_review"
    return mapping.get(lifecycle, "requested")


def _published_url(request_id: int) -> str:
    return f"/api/requests/{request_id}/expanded-preview/app/"


def _tier1_preview_url(request_id: int) -> str:
    return f"/api/preview-apps/{request_id}/"


def customer_access_token_digest(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def _looks_like_customer_access_token_digest(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    return len(normalized) == 64 and all(ch in "0123456789abcdef" for ch in normalized)


def issue_customer_access_token(req: Request) -> str:
    token = secrets.token_urlsafe(32)
    req.customer_access_token = customer_access_token_digest(token)
    return token


def verify_customer_access_token(
    db: Session | None,
    *,
    req: Request,
    token: str | None,
) -> bool:
    candidate = str(token or "").strip()
    stored = str(getattr(req, "customer_access_token", None) or "").strip()
    if not candidate or not stored:
        return False
    candidate_digest = customer_access_token_digest(candidate)
    if _looks_like_customer_access_token_digest(stored):
        return hmac.compare_digest(candidate_digest, stored)
    matched = hmac.compare_digest(candidate, stored)
    if matched and db is not None:
        req.customer_access_token = candidate_digest
        db.commit()
    return matched


def trusted_migrate_legacy_customer_access_token(
    db: Session,
    *,
    req: Request,
    raw_token_sink: Callable[[str], Any] | None = None,
) -> str:
    stored = str(getattr(req, "customer_access_token", None) or "").strip()
    if not stored or _looks_like_customer_access_token_digest(stored):
        return ""
    if callable(raw_token_sink):
        raw_token_sink(stored)
    req.customer_access_token = customer_access_token_digest(stored)
    db.commit()
    return stored


def ensure_customer_access_token(req: Request) -> str:
    token = (getattr(req, "customer_access_token", None) or "").strip()
    if token:
        return token
    return issue_customer_access_token(req)


def _append_event(
    db: Session,
    *,
    row: ExpandedPreviewRequestRecord,
    to_status: str,
    actor_id: str,
    actor_role: str,
    reason: str | None,
    internal_notes: str | None,
) -> ExpandedPreviewStatusEventRecord:
    from_status = row.current_status
    created = datetime.utcnow()
    event_sha = _canonical_sha256(
        {
            "expanded_preview_id": row.id,
            "from_status": from_status,
            "to_status": to_status,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "reason": reason,
            "internal_notes": internal_notes,
            "created_at": created.isoformat(),
            "nonce": secrets.token_hex(8),
        }
    )
    event = ExpandedPreviewStatusEventRecord(
        expanded_preview_id=row.id,
        from_status=from_status,
        to_status=to_status,
        actor_id=actor_id,
        actor_role=actor_role,
        reason=reason,
        internal_notes=internal_notes,
        event_sha256=event_sha,
        created_at=created,
    )
    row.current_status = to_status
    row.updated_at = created
    db.add(event)
    return event


class ExpandedPreviewService:
    def __init__(self, db: Session):
        self.db = db

    def _get_or_404(self, expanded_preview_id: int) -> ExpandedPreviewRequestRecord:
        row = self.db.get(ExpandedPreviewRequestRecord, expanded_preview_id)
        if row is None:
            raise ExpandedPreviewServiceError("Expanded preview not found", status_code=404)
        return row

    def customer_create(
        self,
        *,
        request_id: int,
        body: ExpandedPreviewCreateBody,
        customer_actor_id: str,
        raw_payload: dict,
    ) -> ExpandedPreviewCustomerView:
        reject_client_supplied_roles(raw_payload)
        req = self.db.get(Request, request_id)
        if req is None:
            raise ExpandedPreviewServiceError("Request not found", status_code=404)
        try:
            _, tier1_rev, tier1_visual = load_accepted_tier1_phase5_result(
                self.db, request_id=request_id
            )
        except ExpandedPreviewLineageError as exc:
            raise ExpandedPreviewServiceError(str(exc), status_code=409) from exc

        idem = (body.idempotency_key or "").strip() or _canonical_sha256(
            {
                "request_id": request_id,
                "reason": body.reason,
                "requested_changes": body.requested_changes,
                "contact_preference": body.contact_preference,
            }
        )
        existing_same = (
            self.db.query(ExpandedPreviewRequestRecord)
            .filter(
                ExpandedPreviewRequestRecord.request_id == request_id,
                ExpandedPreviewRequestRecord.idempotency_key == idem,
            )
            .first()
        )
        if existing_same is not None:
            return self._customer_view(existing_same)

        open_row = (
            self.db.query(ExpandedPreviewRequestRecord)
            .filter(
                ExpandedPreviewRequestRecord.request_id == request_id,
                ExpandedPreviewRequestRecord.current_status.in_(tuple(OPEN_STATUSES)),
            )
            .first()
        )
        if open_row is not None:
            raise ExpandedPreviewServiceError(
                "An Expanded Preview request is already open for this business request",
                status_code=409,
            )

        now = datetime.utcnow()
        request_sha = _canonical_sha256(
            {
                "request_id": request_id,
                "reason": body.reason,
                "requested_changes": body.requested_changes,
                "contact_preference": body.contact_preference,
                "idempotency_key": idem,
                "actor_id": customer_actor_id,
            }
        )
        row = ExpandedPreviewRequestRecord(
            expanded_preview_uuid=str(uuid.uuid4()),
            request_id=request_id,
            current_status="requested",
            customer_reason=body.reason,
            requested_changes=body.requested_changes,
            contact_preference=body.contact_preference,
            idempotency_key=idem,
            request_sha256=request_sha,
            actor_id=customer_actor_id,
            accepted_tier_1_revision_id=tier1_rev.id,
            accepted_tier_1_visual_summary_id=tier1_visual.id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.flush()
        event_sha = _canonical_sha256(
            {
                "expanded_preview_id": row.id,
                "from_status": None,
                "to_status": "requested",
                "actor_id": customer_actor_id,
                "actor_role": "customer",
                "reason": body.reason,
                "created_at": now.isoformat(),
                "nonce": secrets.token_hex(8),
            }
        )
        self.db.add(
            ExpandedPreviewStatusEventRecord(
                expanded_preview_id=row.id,
                from_status=None,
                to_status="requested",
                actor_id=customer_actor_id,
                actor_role="customer",
                reason=body.reason,
                internal_notes=None,
                event_sha256=event_sha,
                created_at=now,
            )
        )
        self.db.commit()
        self.db.refresh(row)
        return self._customer_view(row)

    def customer_get(self, *, request_id: int) -> ExpandedPreviewCustomerView | None:
        row = (
            self.db.query(ExpandedPreviewRequestRecord)
            .filter(ExpandedPreviewRequestRecord.request_id == request_id)
            .order_by(ExpandedPreviewRequestRecord.id.desc())
            .first()
        )
        if row is None:
            return None
        return self._customer_view(row)

    def _customer_view(self, row: ExpandedPreviewRequestRecord) -> ExpandedPreviewCustomerView:
        published = row.current_status == "published"
        return ExpandedPreviewCustomerView(
            expanded_preview_id=row.id,
            request_id=row.request_id,
            status=_customer_status(row.current_status),
            lifecycle_status=row.current_status,  # type: ignore[arg-type]
            reason=row.customer_reason,
            requested_changes=row.requested_changes,
            contact_preference=row.contact_preference,
            created_at=row.created_at,
            updated_at=row.updated_at,
            published_preview_url=_published_url(row.request_id) if published else None,
            can_open_published=published,
        )

    def list_admin(
        self,
        *,
        actor: TrustedCommercialActor,
        status: str | None = None,
        limit: int = 50,
    ) -> list[ExpandedPreviewListItem]:
        require_permission(actor, "read_queue")
        q = self.db.query(ExpandedPreviewRequestRecord).order_by(
            ExpandedPreviewRequestRecord.created_at.desc()
        )
        if status:
            q = q.filter(ExpandedPreviewRequestRecord.current_status == status)
        rows = q.limit(max(1, min(limit, 200))).all()
        items: list[ExpandedPreviewListItem] = []
        for row in rows:
            req = self.db.get(Request, row.request_id)
            items.append(
                ExpandedPreviewListItem(
                    id=row.id,
                    request_id=row.request_id,
                    current_status=row.current_status,  # type: ignore[arg-type]
                    business_name=req.business_name if req else None,
                    customer_email=req.email if req else None,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
            )
        return items

    def admin_detail(
        self, *, actor: TrustedCommercialActor, expanded_preview_id: int
    ) -> ExpandedPreviewAdminView:
        require_permission(actor, "read_detail")
        row = self._get_or_404(expanded_preview_id)
        return self._admin_view(row, include_internal=True)

    def approve(
        self,
        *,
        actor: TrustedCommercialActor,
        expanded_preview_id: int,
        body: ExpandedPreviewApproveBody,
        raw_payload: dict,
    ) -> ExpandedPreviewAdminView:
        reject_client_supplied_roles(raw_payload)
        require_permission(actor, "approve")
        row = self._get_or_404(expanded_preview_id)
        if row.current_status != "requested":
            raise ExpandedPreviewServiceError(
                f"Cannot approve from status {row.current_status}", status_code=409
            )
        _append_event(
            self.db,
            row=row,
            to_status="approved",
            actor_id=actor.actor_id,
            actor_role="expanded_preview_operator",
            reason=body.reason,
            internal_notes=body.internal_notes,
        )
        self.db.commit()
        self.db.refresh(row)
        return self._admin_view(row, include_internal=True)

    def reject(
        self,
        *,
        actor: TrustedCommercialActor,
        expanded_preview_id: int,
        body: ExpandedPreviewRejectBody,
        raw_payload: dict,
    ) -> ExpandedPreviewAdminView:
        reject_client_supplied_roles(raw_payload)
        require_permission(actor, "reject")
        row = self._get_or_404(expanded_preview_id)
        if row.current_status not in {"requested", "approved", "generation_completed"}:
            raise ExpandedPreviewServiceError(
                f"Cannot reject from status {row.current_status}", status_code=409
            )
        _append_event(
            self.db,
            row=row,
            to_status="rejected",
            actor_id=actor.actor_id,
            actor_role="expanded_preview_operator",
            reason=body.reason,
            internal_notes=body.internal_notes,
        )
        self.db.commit()
        self.db.refresh(row)
        return self._admin_view(row, include_internal=True)

    def start_generation(
        self,
        *,
        actor: TrustedCommercialActor,
        expanded_preview_id: int,
        body: ExpandedPreviewStartBody,
        raw_payload: dict,
    ) -> ExpandedPreviewAdminView:
        reject_client_supplied_roles(raw_payload)
        require_permission(actor, "start_generation")
        if not body.confirm:
            raise ExpandedPreviewServiceError(
                "confirm=true is required to start Tier 2 generation", status_code=400
            )
        if not settings.V2_TIER2_GENERATION_ENABLED:
            raise ExpandedPreviewServiceError(
                "Tier 2 generation capability is disabled", status_code=403
            )
        row = self._get_or_404(expanded_preview_id)
        if row.current_status == "generation_started":
            # Idempotent if already claimed/running
            return self._admin_view(row, include_internal=True)
        if row.current_status != "approved":
            raise ExpandedPreviewServiceError(
                "Tier 2 generation requires an approved Expanded Preview request",
                status_code=409,
            )
        active_claim = (
            self.db.query(ExpandedPreviewGenerationClaimRecord)
            .filter(
                ExpandedPreviewGenerationClaimRecord.expanded_preview_id == row.id,
                ExpandedPreviewGenerationClaimRecord.active.is_(True),
            )
            .first()
        )
        if active_claim is not None:
            raise ExpandedPreviewServiceError(
                "Tier 2 generation already in progress for this request",
                status_code=409,
            )
        claim_token = secrets.token_hex(16)
        claim = ExpandedPreviewGenerationClaimRecord(
            expanded_preview_id=row.id,
            claim_token=claim_token,
            claimed_by_actor_id=actor.actor_id,
            claimed_at=datetime.utcnow(),
            heartbeat_at=datetime.utcnow(),
            active=True,
        )
        self.db.add(claim)
        row.generation_claim_token = claim_token
        row.generation_started_at = datetime.utcnow()
        row.generation_error = None
        _append_event(
            self.db,
            row=row,
            to_status="generation_started",
            actor_id=actor.actor_id,
            actor_role="expanded_preview_operator",
            reason=body.reason,
            internal_notes=None,
        )
        self.db.commit()
        self.db.refresh(row)
        from app.application.expanded_preview import generation_job

        generation_job.spawn_tier2_generation_job(
            expanded_preview_id=row.id,
            request_id=row.request_id,
            claim_token=claim_token,
        )
        return self._admin_view(row, include_internal=True)

    def review(
        self,
        *,
        actor: TrustedCommercialActor,
        expanded_preview_id: int,
        body: ExpandedPreviewReviewBody,
        raw_payload: dict,
    ) -> ExpandedPreviewAdminView:
        reject_client_supplied_roles(raw_payload)
        require_permission(actor, "review")
        if not body.confirm:
            raise ExpandedPreviewServiceError(
                "confirm=true is required for review", status_code=400
            )
        row = self._get_or_404(expanded_preview_id)
        if row.current_status != "generation_completed":
            raise ExpandedPreviewServiceError(
                "Review requires completed Tier 2 generation", status_code=409
            )
        _append_event(
            self.db,
            row=row,
            to_status=body.outcome,
            actor_id=actor.actor_id,
            actor_role="expanded_preview_operator",
            reason=body.reason,
            internal_notes=body.internal_notes,
        )
        self.db.commit()
        self.db.refresh(row)
        return self._admin_view(row, include_internal=True)

    def publish(
        self,
        *,
        actor: TrustedCommercialActor,
        expanded_preview_id: int,
        body: ExpandedPreviewPublishBody,
        raw_payload: dict,
    ) -> ExpandedPreviewAdminView:
        reject_client_supplied_roles(raw_payload)
        require_permission(actor, "publish")
        if not body.confirm:
            raise ExpandedPreviewServiceError(
                "confirm=true is required to publish", status_code=400
            )
        row = self._get_or_404(expanded_preview_id)
        if row.current_status == "published":
            return self._admin_view(row, include_internal=True)
        if row.current_status != "review_accepted":
            raise ExpandedPreviewServiceError(
                "Only review_accepted Expanded Previews may be published",
                status_code=409,
            )
        if not row.tier_2_candidate_revision_id:
            raise ExpandedPreviewServiceError(
                "Missing Tier 2 candidate for publication", status_code=409
            )
        path = _published_url(row.request_id)
        pub_sha = _canonical_sha256(
            {
                "expanded_preview_id": row.id,
                "request_id": row.request_id,
                "candidate_revision_id": row.tier_2_candidate_revision_id,
                "publisher_actor_id": actor.actor_id,
                "path": path,
                "at": datetime.utcnow().isoformat(),
            }
        )
        self.db.add(
            ExpandedPreviewPublicationRecord(
                expanded_preview_id=row.id,
                request_id=row.request_id,
                candidate_revision_id=row.tier_2_candidate_revision_id,
                publisher_actor_id=actor.actor_id,
                publication_sha256=pub_sha,
                customer_preview_path=path,
                created_at=datetime.utcnow(),
            )
        )
        row.published_candidate_revision_id = row.tier_2_candidate_revision_id
        _append_event(
            self.db,
            row=row,
            to_status="published",
            actor_id=actor.actor_id,
            actor_role="expanded_preview_admin",
            reason=body.reason,
            internal_notes=None,
        )
        # Customer-facing generated_pages hint (does not mutate Phase 7 pointers)
        req = self.db.get(Request, row.request_id)
        if req is not None:
            try:
                pages = json.loads(req.generated_pages or "{}")
            except Exception:
                pages = {}
            if not isinstance(pages, dict):
                pages = {}
            pages["expanded_preview"] = {
                "status": "published",
                "expanded_preview_id": row.id,
                "url": path,
                "candidate_revision_id": row.tier_2_candidate_revision_id,
            }
            req.generated_pages = json.dumps(pages)
        self.db.commit()
        self.db.refresh(row)
        return self._admin_view(row, include_internal=True)

    def _admin_view(
        self, row: ExpandedPreviewRequestRecord, *, include_internal: bool
    ) -> ExpandedPreviewAdminView:
        req = self.db.get(Request, row.request_id)
        events = (
            self.db.query(ExpandedPreviewStatusEventRecord)
            .filter(ExpandedPreviewStatusEventRecord.expanded_preview_id == row.id)
            .order_by(ExpandedPreviewStatusEventRecord.id.asc())
            .all()
        )
        phase4_status = None
        phase5_status = None
        routes: list[str] = []
        screenshot_count = 0
        warning_count = 0
        blocking_finding_count = 0
        tier2_url = None
        subject_revision_id = row.tier_2_candidate_revision_id
        if subject_revision_id:
            try:
                val = (
                    self.db.query(CandidateValidationSummaryRecord)
                    .filter(
                        CandidateValidationSummaryRecord.candidate_revision_id
                        == subject_revision_id
                    )
                    .order_by(CandidateValidationSummaryRecord.id.desc())
                    .first()
                )
                if val is not None:
                    phase4_status = val.status
                vis = (
                    self.db.query(CandidateVisualSummaryRecord)
                    .filter(
                        CandidateVisualSummaryRecord.candidate_revision_id
                        == subject_revision_id
                    )
                    .order_by(CandidateVisualSummaryRecord.id.desc())
                    .first()
                )
                if vis is not None:
                    phase5_status = vis.status
                screenshot_count = (
                    self.db.query(CandidateScreenshotRecord)
                    .filter(
                        CandidateScreenshotRecord.candidate_revision_id
                        == subject_revision_id
                    )
                    .count()
                )
                findings = (
                    self.db.query(CandidateVisualFindingRecord)
                    .filter(
                        CandidateVisualFindingRecord.candidate_revision_id
                        == subject_revision_id
                    )
                    .all()
                )
                for finding in findings:
                    severity = (getattr(finding, "severity", None) or "").lower()
                    if severity in {"blocking", "error", "critical"}:
                        blocking_finding_count += 1
                    elif severity in {"warning", "warn"}:
                        warning_count += 1
                rev = self.db.get(CandidateRevisionRecord, subject_revision_id)
                if rev is not None and getattr(rev, "workspace_relpath", None):
                    tier2_url = (
                        f"/api/admin/expanded-previews/{row.id}/candidate-files/"
                    )
            except Exception:
                # Diagnostic enrichment is best-effort; lifecycle APIs must still work.
                self.db.rollback()
                row = self._get_or_404(row.id)

        timeline = [
            ExpandedPreviewStatusEventView(
                id=e.id,
                from_status=e.from_status,
                to_status=e.to_status,
                actor_id=e.actor_id,
                actor_role=e.actor_role,
                reason=e.reason,
                internal_notes=e.internal_notes if include_internal else None,
                created_at=e.created_at,
                event_sha256=e.event_sha256,
            )
            for e in events
        ]
        return ExpandedPreviewAdminView(
            id=row.id,
            expanded_preview_uuid=row.expanded_preview_uuid,
            request_id=row.request_id,
            current_status=row.current_status,  # type: ignore[arg-type]
            customer_reason=row.customer_reason,
            requested_changes=row.requested_changes,
            contact_preference=row.contact_preference,
            actor_id=row.actor_id,
            accepted_tier_1_revision_id=row.accepted_tier_1_revision_id,
            tier_2_candidate_revision_id=row.tier_2_candidate_revision_id,
            published_candidate_revision_id=row.published_candidate_revision_id,
            generation_error=row.generation_error if include_internal else None,
            generation_started_at=row.generation_started_at,
            generation_finished_at=row.generation_finished_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
            business_name=req.business_name if req else None,
            customer_email=req.email if req else None,
            tier_1_preview_url=_tier1_preview_url(row.request_id),
            tier_2_preview_url=tier2_url,
            published_preview_url=(
                _published_url(row.request_id)
                if row.current_status == "published"
                else None
            ),
            phase4_status=phase4_status,
            phase5_status=phase5_status,
            routes=routes,
            screenshot_count=screenshot_count,
            warning_count=warning_count,
            blocking_finding_count=blocking_finding_count,
            timeline=timeline,
        )


# Module-level lock to reduce same-process double-start races.
_start_locks: dict[int, threading.Lock] = {}
_start_locks_guard = threading.Lock()


def generation_lock_for(expanded_preview_id: int) -> threading.Lock:
    with _start_locks_guard:
        lock = _start_locks.get(expanded_preview_id)
        if lock is None:
            lock = threading.Lock()
            _start_locks[expanded_preview_id] = lock
        return lock


__all__ = [
    "ExpandedPreviewService",
    "ExpandedPreviewServiceError",
    "CommercialAuthorizationError",
    "customer_access_token_digest",
    "ensure_customer_access_token",
    "generation_lock_for",
    "issue_customer_access_token",
    "trusted_migrate_legacy_customer_access_token",
    "verify_customer_access_token",
]
