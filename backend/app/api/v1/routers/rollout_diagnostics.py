"""Phase 7A/7B rollout diagnostics and shadow-only write surface.

GET diagnostics + POST shadow evaluations. No promote/rollback/pointer-swap.
Roles come from trusted admin auth, never from request JSON.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, verify_admin
from app.application.rollout.authorization import (
    RolloutAuthorizationError,
    trusted_actor_from_admin,
)
from app.application.rollout.service import RolloutControlPlaneService
from app.application.rollout.shadow_service import ShadowExecutionError, ShadowService
from app.application.services.user_auth import get_user_by_token
from app.core.config import settings
from app.domain.schemas.rollout import ServingPointerView, TrustedRolloutActor
from app.domain.schemas.shadow_evaluation import (
    ShadowEvaluationView,
    ShadowStartRequest,
)

router = APIRouter(prefix="/api/admin/rollout", tags=["rollout-diagnostics"])


def _trusted_rollout_actor(
    db: Session,
    *,
    x_admin_password: str | None,
    authorization: str | None,
) -> TrustedRolloutActor:
    """Map authenticated admin credentials to trusted rollout roles."""
    if x_admin_password and x_admin_password == settings.ADMIN_PASSWORD:
        return trusted_actor_from_admin(actor_id="admin:shared-password", is_admin=True)
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
    # verify_admin already passed; treat as admin principal.
    return trusted_actor_from_admin(actor_id="admin:session", is_admin=True)


@router.get("/requests/{request_id}/serving-pointer", response_model=ServingPointerView)
def get_serving_pointer_diagnostic(
    request_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> ServingPointerView:
    if request_id < 1:
        raise HTTPException(status_code=400, detail="invalid request_id")
    actor = _trusted_rollout_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    service = RolloutControlPlaneService(db)
    view = service.resolve_pointer(actor=actor, request_id=request_id)
    db.commit()
    return view


@router.get("/policy/current")
def get_current_rollout_policy_diagnostic(
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    actor = _trusted_rollout_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    service = RolloutControlPlaneService(db)
    view = service.current_env_policy_view(actor)
    return view.model_dump(mode="json")


@router.get(
    "/requests/{request_id}/shadow-evaluations",
    response_model=list[ShadowEvaluationView],
)
def list_shadow_evaluations(
    request_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> list[ShadowEvaluationView]:
    if request_id < 1:
        raise HTTPException(status_code=400, detail="invalid request_id")
    actor = _trusted_rollout_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    service = ShadowService(db)
    views = service.list_evaluations(actor=actor, request_id=request_id)
    return views


@router.get(
    "/shadow-evaluations/{evaluation_id}",
    response_model=ShadowEvaluationView,
)
def get_shadow_evaluation(
    evaluation_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> ShadowEvaluationView:
    if evaluation_id < 1:
        raise HTTPException(status_code=400, detail="invalid evaluation_id")
    actor = _trusted_rollout_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    service = ShadowService(db)
    try:
        return service.get_evaluation(actor=actor, evaluation_id=evaluation_id)
    except ShadowExecutionError as exc:
        raise HTTPException(status_code=404, detail=exc.reason) from exc


@router.post(
    "/requests/{request_id}/shadow-evaluations",
    response_model=ShadowEvaluationView,
)
def start_shadow_evaluation(
    request_id: int,
    body: ShadowStartRequest,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> ShadowEvaluationView:
    if request_id < 1:
        raise HTTPException(status_code=400, detail="invalid request_id")
    actor = _trusted_rollout_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    # Capture raw JSON keys for banned-field rejection without trusting body extras
    # (StrictDesignModel already forbids extras; this guards alternate clients).
    client_payload: dict[str, Any] = {}
    try:
        # Body already parsed; reconstruct allowed keys only for reject check.
        client_payload = body.model_dump(mode="json")
    except Exception:
        client_payload = {}
    service = ShadowService(db)
    try:
        view = service.start_shadow(
            actor=actor,
            request_id=request_id,
            body=body,
            client_payload=client_payload,
        )
        db.commit()
        return view
    except RolloutAuthorizationError as exc:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ShadowExecutionError as exc:
        db.rollback()
        status = 409 if exc.stage in {"idempotency", "concurrency"} else 400
        if exc.reason == "flags_off":
            status = 403
        raise HTTPException(status_code=status, detail=exc.reason) from exc


__all__ = ["router"]
