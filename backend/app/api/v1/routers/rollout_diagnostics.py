"""Read-only Phase 7A rollout diagnostics.

No POST promote/rollback endpoints exist. Roles come from trusted admin auth,
never from request JSON.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, verify_admin
from app.application.rollout.authorization import trusted_actor_from_admin
from app.application.rollout.service import RolloutControlPlaneService
from app.domain.schemas.rollout import ServingPointerView

router = APIRouter(prefix="/api/admin/rollout", tags=["rollout-diagnostics"])


@router.get("/requests/{request_id}/serving-pointer", response_model=ServingPointerView)
def get_serving_pointer_diagnostic(
    request_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
) -> ServingPointerView:
    if request_id < 1:
        raise HTTPException(status_code=400, detail="invalid request_id")
    actor = trusted_actor_from_admin(actor_id="admin:session", is_admin=True)
    service = RolloutControlPlaneService(db)
    view = service.resolve_pointer(actor=actor, request_id=request_id)
    db.commit()
    return view


@router.get("/policy/current")
def get_current_rollout_policy_diagnostic(
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    actor = trusted_actor_from_admin(actor_id="admin:session", is_admin=True)
    service = RolloutControlPlaneService(db)
    view = service.current_env_policy_view(actor)
    return view.model_dump(mode="json")


__all__ = ["router"]
