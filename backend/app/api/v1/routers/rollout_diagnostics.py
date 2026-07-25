"""Phase 7A–7D rollout diagnostics, shadow, promotion, and breaker APIs.

Roles come from trusted admin auth, never from request JSON.
Phase 7C writes are request → approve → apply only (no combined endpoint).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, verify_admin
from app.application.rollout.authorization import (
    RolloutAuthorizationError,
    reject_client_supplied_roles,
    trusted_actor_from_admin,
)
from app.application.rollout.auto_rollback import AutoRollbackService
from app.application.rollout.breaker_service import (
    BreakerService,
    BreakerServiceError,
)
from app.application.rollout.promotion_service import (
    PromotionService,
    PromotionServiceError,
)
from app.application.rollout.service import RolloutControlPlaneService
from app.application.rollout.shadow_service import ShadowExecutionError, ShadowService
from app.application.services.user_auth import get_user_by_token
from app.core.config import settings
from app.domain.schemas.breaker import (
    AutoRollbackResultView,
    BreakerAutoRollbackRunBody,
    BreakerDisableBody,
    BreakerEvaluateBody,
    BreakerEvaluationResult,
    BreakerManualCloseBody,
    BreakerManualOpenBody,
    BreakerMetricSampleView,
    BreakerStateView,
)
from app.domain.schemas.promotion import (
    ApplyResultView,
    DecisionApprovalBody,
    DecisionApplyBody,
    DecisionView,
    PromotionRequestBody,
    RollbackRequestBody,
)
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


def _breaker_http_error(exc: BreakerServiceError) -> HTTPException:
    if exc.stage == "flags":
        return HTTPException(status_code=403, detail=exc.reason)
    if exc.stage == "validation":
        return HTTPException(status_code=400, detail=exc.reason)
    return HTTPException(status_code=400, detail=exc.reason)


def _promotion_http_error(exc: PromotionServiceError) -> HTTPException:
    if exc.stage in {"idempotency", "pointer"}:
        status = 409
    elif exc.stage in {"flags", "allowlist", "sod"} or exc.reason in {
        "flags_off",
        "not_allowlisted",
        "rollout_percent_nonzero",
    }:
        status = 403
    elif exc.stage == "lookup":
        status = 404
    else:
        status = 400
    return HTTPException(status_code=status, detail=exc.reason)


@router.post(
    "/requests/{request_id}/promotions",
    response_model=DecisionView,
)
def request_promotion(
    request_id: int,
    body: PromotionRequestBody,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> DecisionView:
    if request_id < 1:
        raise HTTPException(status_code=400, detail="invalid request_id")
    actor = _trusted_rollout_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    service = PromotionService(db)
    try:
        view = service.request_promotion(
            actor=actor,
            request_id=request_id,
            body=body,
            client_payload=body.model_dump(mode="json"),
        )
        db.commit()
        return view
    except RolloutAuthorizationError as exc:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PromotionServiceError as exc:
        db.rollback()
        raise _promotion_http_error(exc) from exc


@router.post(
    "/promotions/{decision_id}/approvals",
    response_model=DecisionView,
)
def approve_promotion(
    decision_id: int,
    body: DecisionApprovalBody,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> DecisionView:
    if decision_id < 1:
        raise HTTPException(status_code=400, detail="invalid decision_id")
    actor = _trusted_rollout_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    service = PromotionService(db)
    try:
        view = service.approve_promotion(
            actor=actor,
            decision_id=decision_id,
            body=body,
            client_payload=body.model_dump(mode="json"),
        )
        db.commit()
        return view
    except RolloutAuthorizationError as exc:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PromotionServiceError as exc:
        db.rollback()
        raise _promotion_http_error(exc) from exc


@router.post(
    "/promotions/{decision_id}/apply",
    response_model=ApplyResultView,
)
def apply_promotion(
    decision_id: int,
    body: DecisionApplyBody,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> ApplyResultView:
    if decision_id < 1:
        raise HTTPException(status_code=400, detail="invalid decision_id")
    actor = _trusted_rollout_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    service = PromotionService(db)
    try:
        view = service.apply_promotion(
            actor=actor,
            decision_id=decision_id,
            body=body,
            client_payload=body.model_dump(mode="json"),
        )
        db.commit()
        return view
    except RolloutAuthorizationError as exc:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PromotionServiceError as exc:
        db.rollback()
        raise _promotion_http_error(exc) from exc


@router.post(
    "/requests/{request_id}/rollbacks",
    response_model=DecisionView,
)
def request_rollback(
    request_id: int,
    body: RollbackRequestBody,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> DecisionView:
    if request_id < 1:
        raise HTTPException(status_code=400, detail="invalid request_id")
    actor = _trusted_rollout_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    service = PromotionService(db)
    try:
        view = service.request_rollback(
            actor=actor,
            request_id=request_id,
            body=body,
            client_payload=body.model_dump(mode="json"),
        )
        db.commit()
        return view
    except RolloutAuthorizationError as exc:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PromotionServiceError as exc:
        db.rollback()
        raise _promotion_http_error(exc) from exc


@router.post(
    "/rollbacks/{decision_id}/approvals",
    response_model=DecisionView,
)
def approve_rollback(
    decision_id: int,
    body: DecisionApprovalBody,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> DecisionView:
    if decision_id < 1:
        raise HTTPException(status_code=400, detail="invalid decision_id")
    actor = _trusted_rollout_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    service = PromotionService(db)
    try:
        view = service.approve_rollback(
            actor=actor,
            decision_id=decision_id,
            body=body,
            client_payload=body.model_dump(mode="json"),
        )
        db.commit()
        return view
    except RolloutAuthorizationError as exc:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PromotionServiceError as exc:
        db.rollback()
        raise _promotion_http_error(exc) from exc


@router.post(
    "/rollbacks/{decision_id}/apply",
    response_model=ApplyResultView,
)
def apply_rollback(
    decision_id: int,
    body: DecisionApplyBody,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> ApplyResultView:
    if decision_id < 1:
        raise HTTPException(status_code=400, detail="invalid decision_id")
    actor = _trusted_rollout_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    service = PromotionService(db)
    try:
        view = service.apply_rollback(
            actor=actor,
            decision_id=decision_id,
            body=body,
            client_payload=body.model_dump(mode="json"),
        )
        db.commit()
        return view
    except RolloutAuthorizationError as exc:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PromotionServiceError as exc:
        db.rollback()
        raise _promotion_http_error(exc) from exc


@router.get(
    "/requests/{request_id}/promotions",
    response_model=list[DecisionView],
)
def list_promotions(
    request_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> list[DecisionView]:
    if request_id < 1:
        raise HTTPException(status_code=400, detail="invalid request_id")
    actor = _trusted_rollout_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    return PromotionService(db).list_promotions(actor=actor, request_id=request_id)


@router.get(
    "/promotions/{decision_id}",
    response_model=DecisionView,
)
def get_promotion(
    decision_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> DecisionView:
    if decision_id < 1:
        raise HTTPException(status_code=400, detail="invalid decision_id")
    actor = _trusted_rollout_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    try:
        return PromotionService(db).get_decision(
            actor=actor, decision_id=decision_id
        )
    except PromotionServiceError as exc:
        raise _promotion_http_error(exc) from exc


@router.get(
    "/requests/{request_id}/serving-pointer/history",
    response_model=list[ServingPointerView],
)
def get_serving_pointer_history(
    request_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> list[ServingPointerView]:
    if request_id < 1:
        raise HTTPException(status_code=400, detail="invalid request_id")
    actor = _trusted_rollout_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    return PromotionService(db).pointer_history(actor=actor, request_id=request_id)


@router.get("/breaker/state", response_model=BreakerStateView)
def get_breaker_state(
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> BreakerStateView:
    actor = _trusted_rollout_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    view = BreakerService(db).get_state_view(actor=actor)
    db.commit()
    return view


@router.get("/breaker/history", response_model=list[BreakerStateView])
def get_breaker_history(
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> list[BreakerStateView]:
    actor = _trusted_rollout_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    return BreakerService(db).history(actor=actor)


@router.get("/breaker/metric-samples", response_model=list[BreakerMetricSampleView])
def get_breaker_metric_samples(
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> list[BreakerMetricSampleView]:
    actor = _trusted_rollout_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    return BreakerService(db).list_samples(actor=actor)


@router.get("/breaker/auto-rollbacks", response_model=list[AutoRollbackResultView])
def get_breaker_auto_rollbacks(
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> list[AutoRollbackResultView]:
    actor = _trusted_rollout_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    return AutoRollbackService(db).list_results(actor=actor)


@router.post("/breaker/evaluate", response_model=BreakerEvaluationResult)
def post_breaker_evaluate(
    body: BreakerEvaluateBody,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> BreakerEvaluationResult:
    actor = _trusted_rollout_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    try:
        reject_client_supplied_roles(body.model_dump(mode="json"))
        result = BreakerService(db).evaluate(
            actor=actor,
            reason=body.reason,
            run_auto_rollback_if_opened=body.run_auto_rollback_if_opened,
        )
        db.commit()
        return result
    except RolloutAuthorizationError as exc:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except BreakerServiceError as exc:
        db.rollback()
        raise _breaker_http_error(exc) from exc


@router.post("/breaker/open", response_model=BreakerEvaluationResult)
def post_breaker_open(
    body: BreakerManualOpenBody,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> BreakerEvaluationResult:
    actor = _trusted_rollout_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    try:
        reject_client_supplied_roles(body.model_dump(mode="json"))
        result = BreakerService(db).manual_open(
            actor=actor,
            reason=body.reason,
            ticket_ref=body.ticket_ref,
            run_auto_rollback=body.run_auto_rollback,
        )
        db.commit()
        return result
    except RolloutAuthorizationError as exc:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except BreakerServiceError as exc:
        db.rollback()
        raise _breaker_http_error(exc) from exc


@router.post("/breaker/close", response_model=BreakerEvaluationResult)
def post_breaker_close(
    body: BreakerManualCloseBody,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> BreakerEvaluationResult:
    actor = _trusted_rollout_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    try:
        reject_client_supplied_roles(body.model_dump(mode="json"))
        result = BreakerService(db).manual_close(
            actor=actor, reason=body.reason, ticket_ref=body.ticket_ref
        )
        db.commit()
        return result
    except RolloutAuthorizationError as exc:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except BreakerServiceError as exc:
        db.rollback()
        raise _breaker_http_error(exc) from exc


@router.post("/breaker/disable", response_model=BreakerEvaluationResult)
def post_breaker_disable(
    body: BreakerDisableBody,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> BreakerEvaluationResult:
    actor = _trusted_rollout_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    try:
        reject_client_supplied_roles(body.model_dump(mode="json"))
        result = BreakerService(db).disable(
            actor=actor, reason=body.reason, ticket_ref=body.ticket_ref
        )
        db.commit()
        return result
    except RolloutAuthorizationError as exc:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except BreakerServiceError as exc:
        db.rollback()
        raise _breaker_http_error(exc) from exc


@router.post(
    "/breaker/auto-rollbacks/run",
    response_model=list[AutoRollbackResultView],
)
def post_breaker_auto_rollbacks_run(
    body: BreakerAutoRollbackRunBody,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> list[AutoRollbackResultView]:
    actor = _trusted_rollout_actor(
        db, x_admin_password=x_admin_password, authorization=authorization
    )
    try:
        reject_client_supplied_roles(body.model_dump(mode="json"))
        # Snapshot hash is recomputed server-side; body cannot supply authority.
        breaker = BreakerService(db)
        policy_row = breaker.ensure_default_policy(actor_id=actor.actor_id)
        snap = breaker._compute_snapshot(breaker._policy_from_row(policy_row))
        results = AutoRollbackService(db).run_for_open_event(
            actor=actor,
            open_state_id=body.open_state_id,
            metric_snapshot_sha256=snap.snapshot_sha256,
        )
        db.commit()
        return results
    except RolloutAuthorizationError as exc:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc


__all__ = ["router"]
