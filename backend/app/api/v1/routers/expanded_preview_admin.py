"""Admin Expanded Preview queue and lifecycle APIs."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import verify_admin
from app.application.expanded_preview.authorization import (
    CommercialAuthorizationError,
    trusted_actor_from_admin,
)
from app.application.expanded_preview.service import (
    ExpandedPreviewService,
    ExpandedPreviewServiceError,
)
from app.application.services.user_auth import get_user_by_token
from app.core.config import settings
from app.domain.schemas.expanded_preview import (
    ExpandedPreviewAdminView,
    ExpandedPreviewApproveBody,
    ExpandedPreviewListItem,
    ExpandedPreviewPublishBody,
    ExpandedPreviewRejectBody,
    ExpandedPreviewReviewBody,
    ExpandedPreviewStartBody,
    TrustedCommercialActor,
)
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/api/admin/expanded-previews", tags=["expanded-preview-admin"])


def _trusted_commercial_actor(
    db: Session,
    *,
    x_admin_password: str | None,
    authorization: str | None,
) -> TrustedCommercialActor:
    if x_admin_password and x_admin_password == settings.ADMIN_PASSWORD:
        return trusted_actor_from_admin(
            actor_id="admin:shared-password", is_admin=True
        )
    token = None
    if authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1].strip()
    user = get_user_by_token(db, token) if token else None
    if user and bool(getattr(user, "is_admin", False)):
        return trusted_actor_from_admin(
            actor_id=f"admin:user:{user.id}",
            is_admin=True,
        )
    return trusted_actor_from_admin(actor_id="admin:session", is_admin=True)


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, ExpandedPreviewServiceError):
        return HTTPException(status_code=exc.status_code, detail=str(exc))
    if isinstance(exc, CommercialAuthorizationError):
        return HTTPException(status_code=403, detail=str(exc))
    return HTTPException(status_code=500, detail="expanded preview error")


@router.get("", response_model=list[ExpandedPreviewListItem])
def list_expanded_previews(
    status: str | None = None,
    limit: int = 50,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> list[ExpandedPreviewListItem]:
    actor = _trusted_commercial_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    try:
        return ExpandedPreviewService(db).list_admin(
            actor=actor, status=status, limit=limit
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/{expanded_preview_id}", response_model=ExpandedPreviewAdminView)
def get_expanded_preview(
    expanded_preview_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> ExpandedPreviewAdminView:
    actor = _trusted_commercial_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    try:
        return ExpandedPreviewService(db).admin_detail(
            actor=actor, expanded_preview_id=expanded_preview_id
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/{expanded_preview_id}/approve", response_model=ExpandedPreviewAdminView)
def approve_expanded_preview(
    expanded_preview_id: int,
    body: ExpandedPreviewApproveBody,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> ExpandedPreviewAdminView:
    actor = _trusted_commercial_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    try:
        return ExpandedPreviewService(db).approve(
            actor=actor,
            expanded_preview_id=expanded_preview_id,
            body=body,
            raw_payload=body.model_dump(),
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/{expanded_preview_id}/reject", response_model=ExpandedPreviewAdminView)
def reject_expanded_preview(
    expanded_preview_id: int,
    body: ExpandedPreviewRejectBody,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> ExpandedPreviewAdminView:
    actor = _trusted_commercial_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    try:
        return ExpandedPreviewService(db).reject(
            actor=actor,
            expanded_preview_id=expanded_preview_id,
            body=body,
            raw_payload=body.model_dump(),
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post(
    "/{expanded_preview_id}/start-generation",
    response_model=ExpandedPreviewAdminView,
)
def start_expanded_preview_generation(
    expanded_preview_id: int,
    body: ExpandedPreviewStartBody,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> ExpandedPreviewAdminView:
    actor = _trusted_commercial_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    try:
        return ExpandedPreviewService(db).start_generation(
            actor=actor,
            expanded_preview_id=expanded_preview_id,
            body=body,
            raw_payload=body.model_dump(),
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/{expanded_preview_id}/review", response_model=ExpandedPreviewAdminView)
def review_expanded_preview(
    expanded_preview_id: int,
    body: ExpandedPreviewReviewBody,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> ExpandedPreviewAdminView:
    actor = _trusted_commercial_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    try:
        return ExpandedPreviewService(db).review(
            actor=actor,
            expanded_preview_id=expanded_preview_id,
            body=body,
            raw_payload=body.model_dump(),
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/{expanded_preview_id}/publish", response_model=ExpandedPreviewAdminView)
def publish_expanded_preview(
    expanded_preview_id: int,
    body: ExpandedPreviewPublishBody,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> ExpandedPreviewAdminView:
    actor = _trusted_commercial_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    try:
        return ExpandedPreviewService(db).publish(
            actor=actor,
            expanded_preview_id=expanded_preview_id,
            body=body,
            raw_payload=body.model_dump(),
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc
