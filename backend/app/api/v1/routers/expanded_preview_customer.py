"""Customer Expanded Preview API."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request as FastAPIRequest
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.application.expanded_preview.access import resolve_customer_actor
from app.application.expanded_preview.service import (
    ExpandedPreviewService,
    ExpandedPreviewServiceError,
)
from app.core.config import settings
from app.domain.models import CandidateRevisionRecord, Request
from app.domain.models.expanded_preview import ExpandedPreviewRequestRecord
from app.domain.schemas.expanded_preview import (
    ExpandedPreviewCreateBody,
    ExpandedPreviewCustomerView,
)
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/api/requests", tags=["expanded-preview"])


def _service_error(exc: ExpandedPreviewServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.post(
    "/{request_id}/expanded-preview",
    response_model=ExpandedPreviewCustomerView,
)
def create_expanded_preview(
    request_id: int,
    body: ExpandedPreviewCreateBody,
    http_request: FastAPIRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_request_access_token: str | None = Header(default=None),
) -> ExpandedPreviewCustomerView:
    req = db.get(Request, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    actor_id = resolve_customer_actor(
        db,
        req=req,
        authorization=authorization,
        x_request_access_token=x_request_access_token,
    )
    raw = body.model_dump()
    # Reject smuggled fields that pydantic stripped from alias extras
    for banned in (
        "actor_id",
        "roles",
        "approval_status",
        "target_candidate_revision",
        "publish_authority",
    ):
        if banned in http_request.query_params:
            raise HTTPException(status_code=400, detail=f"forbidden field {banned}")
    try:
        return ExpandedPreviewService(db).customer_create(
            request_id=request_id,
            body=body,
            customer_actor_id=actor_id,
            raw_payload=raw,
        )
    except ExpandedPreviewServiceError as exc:
        raise _service_error(exc) from exc


@router.get(
    "/{request_id}/expanded-preview",
    response_model=ExpandedPreviewCustomerView | None,
)
def get_expanded_preview(
    request_id: int,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_request_access_token: str | None = Header(default=None),
) -> ExpandedPreviewCustomerView | None:
    req = db.get(Request, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    resolve_customer_actor(
        db,
        req=req,
        authorization=authorization,
        x_request_access_token=x_request_access_token,
    )
    return ExpandedPreviewService(db).customer_get(request_id=request_id)


@router.get("/{request_id}/expanded-preview/app/{full_path:path}")
def serve_published_expanded_preview(
    request_id: int,
    full_path: str,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_request_access_token: str | None = Header(default=None),
):
    req = db.get(Request, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    resolve_customer_actor(
        db,
        req=req,
        authorization=authorization,
        x_request_access_token=x_request_access_token,
    )
    row = (
        db.query(ExpandedPreviewRequestRecord)
        .filter(
            ExpandedPreviewRequestRecord.request_id == request_id,
            ExpandedPreviewRequestRecord.current_status == "published",
        )
        .order_by(ExpandedPreviewRequestRecord.id.desc())
        .first()
    )
    if row is None or not row.published_candidate_revision_id:
        raise HTTPException(status_code=404, detail="Published Expanded Preview not found")
    revision = db.get(CandidateRevisionRecord, row.published_candidate_revision_id)
    if revision is None or not revision.workspace_relpath:
        raise HTTPException(status_code=404, detail="Published candidate workspace missing")
    root = Path(settings.PREVIEW_CANDIDATES_DIR)
    workspace = (root / revision.workspace_relpath).resolve()
    try:
        workspace.relative_to(root.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Invalid workspace") from exc
    dist = workspace / "dist"
    target = (dist / (full_path or "index.html")).resolve()
    try:
        target.relative_to(dist.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Invalid path") from exc
    if target.is_dir():
        target = target / "index.html"
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target)

