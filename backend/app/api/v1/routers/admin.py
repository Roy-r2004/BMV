import json
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_ai_provider_dep, get_db, get_template_renderer_dep, verify_admin
from app.application.pipelines import blueprint, build_plans, orchestrator, proposal, reference_analysis, technical_plan, visual_demo
from app.application.appspec import ensure_approved_app_spec
from app.application.candidate_generation.cache import canonical_sha256
from app.application.runtime_validation.evidence import (
    Phase4EvidenceNotFound,
    build_phase4_evidence,
)
from app.application.appspec.repository import (
    AppSpecRepository,
    load_json_object,
    revision_summary,
)
from app.core.config import (
    appspec_fallback_configuration,
    candidate_model_configuration,
    settings,
)
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.models.request import Request
from app.application.services import admin_ops
from app.application.services.admin_alerts import acknowledge_alert, acknowledge_all, list_alerts
from app.application.services.ai_context import ai_run_scope
from app.application.services.runtime_metadata import production_build_info
from app.application.services.user_auth import authenticate_user, create_session
from app.domain.schemas.admin import (
    AdminLoginRequest,
    AdminLoginResponse,
    AdminSettingsResponse,
    AdminSettingsUpdate,
    RequestDetail,
    RequestListItem,
    RequestUpdate,
)
from app.domain.schemas.request import (
    AdminPreviewDiagnostics,
    AdminProgressDiagnostics,
)
from app.domain.schemas.common import GenerateResponse
from app.domain.models import (
    AppSpecRevision,
    CandidateArtifactRecord,
    CandidateAccessibilityFindingRecord,
    CandidateBuildAttemptRecord,
    CandidateJourneyResultRecord,
    CandidateRouteResultRecord,
    CandidateRevisionRecord,
    CandidateRuntimeValidationAttemptRecord,
    CandidateScreenshotRecord,
    CandidateValidationSummaryRecord,
    CompositionContractArtifactRecord,
    CustomerSourceArtifact,
    DesignContractArtifactRecord,
    PreviewChatMessage,
    PreviewTierArtifactRecord,
    ProductStrategyRevision,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/login", response_model=AdminLoginResponse)
def admin_login(body: AdminLoginRequest, db: Session = Depends(get_db)):
    # Preferred: admin user account (email + password)
    if body.email and body.email.strip():
        try:
            user = authenticate_user(db, email=body.email, password=body.password)
        except HTTPException:
            return AdminLoginResponse(success=False, message="Invalid email or password")
        if not bool(getattr(user, "is_admin", False)):
            return AdminLoginResponse(success=False, message="This account is not an admin")
        token = create_session(db, user)
        return AdminLoginResponse(
            success=True,
            message="Login successful",
            token=token,
            user={
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "is_admin": True,
            },
        )

    # Legacy shared password fallback
    if body.password == settings.ADMIN_PASSWORD:
        return AdminLoginResponse(success=True, message="Login successful")
    return AdminLoginResponse(success=False, message="Invalid password")


@router.get("/overview")
def admin_overview(
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    return admin_ops.build_overview(db)


@router.get("/configuration-safety")
def configuration_safety(
    _: bool = Depends(verify_admin),
):
    """Return redacted trusted runtime-configuration diagnostics."""

    return {
        "appspec_fallback": appspec_fallback_configuration(settings),
        "candidate_models": candidate_model_configuration(settings),
        "related_fallbacks": {
            # No repository settings exist for legacy generator/candidate,
            # provider-error, or validation-error fallback activation.
            "legacy_generator_fallback_enabled": False,
            "legacy_candidate_fallback_enabled": False,
            "fallback_on_provider_error_enabled": False,
            "fallback_on_validation_error_enabled": False,
        },
    }


@router.get("/build-info")
def build_info(
    _: bool = Depends(verify_admin),
):
    """Return authenticated, non-secret release and runtime policy metadata."""

    return production_build_info(settings)


@router.get("/settings", response_model=AdminSettingsResponse)
def get_admin_settings(
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    row = admin_ops.ensure_settings(db)
    return AdminSettingsResponse(
        ai_enabled=bool(row.ai_enabled),
        site_chat_enabled=bool(row.site_chat_enabled),
        daily_budget_usd=row.daily_budget_usd,
        request_budget_usd=getattr(row, "request_budget_usd", None),
        updated_at=row.updated_at,
    )


@router.patch("/settings", response_model=AdminSettingsResponse)
def patch_admin_settings(
    body: AdminSettingsUpdate,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    budget_arg: object = ...
    if body.clear_daily_budget:
        budget_arg = None
    elif "daily_budget_usd" in body.model_fields_set:
        budget_arg = body.daily_budget_usd

    req_budget_arg: object = ...
    if body.clear_request_budget:
        req_budget_arg = None
    elif "request_budget_usd" in body.model_fields_set:
        req_budget_arg = body.request_budget_usd

    row = admin_ops.update_settings(
        db,
        ai_enabled=body.ai_enabled,
        site_chat_enabled=body.site_chat_enabled,
        daily_budget_usd=budget_arg,
        request_budget_usd=req_budget_arg,
    )
    return AdminSettingsResponse(
        ai_enabled=bool(row.ai_enabled),
        site_chat_enabled=bool(row.site_chat_enabled),
        daily_budget_usd=row.daily_budget_usd,
        request_budget_usd=getattr(row, "request_budget_usd", None),
        updated_at=row.updated_at,
    )


@router.get("/usage")
def admin_usage(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(200, ge=1, le=500),
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    return {"days": days, "events": admin_ops.list_usage(db, days=days, limit=limit)}


@router.get("/alerts")
def admin_alerts(
    unread_only: bool = Query(False),
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    return {"alerts": list_alerts(db, unread_only=unread_only, limit=100)}


@router.post("/alerts/{alert_id}/ack")
def admin_ack_alert(
    alert_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    if not acknowledge_alert(db, alert_id):
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"success": True}


@router.post("/alerts/ack-all")
def admin_ack_all_alerts(
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    return {"success": True, "acked": acknowledge_all(db)}


@router.get("/requests")
def list_requests(
    status: str = Query(None),
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    query = db.query(Request).order_by(Request.created_at.desc())
    if status and status != "all":
        query = query.filter(Request.status == status)
    rows = query.all()
    costs = admin_ops.costs_for_request_ids(db, [r.id for r in rows])
    out = []
    for r in rows:
        item = RequestListItem.model_validate(r).model_dump()
        c = costs.get(r.id) or {}
        item["cost_usd"] = c.get("cost_usd", 0.0)
        item["ai_calls"] = c.get("calls", 0)
        item["ai_tokens"] = c.get("tokens", 0)
        out.append(item)
    return out


@router.get("/requests/{request_id}", response_model=RequestDetail)
def get_request(
    request_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    return req


@router.get("/requests/{request_id}/phase3a-call-ledger")
def get_phase3a_call_ledger(
    request_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    """Return the Phase 3A provider-call ledger for a completed request.

    The ledger is persisted as part of the preview_contract summary and
    contains the append-only event log, substage caps, and totals.
    No secrets or prompt content is included.
    """
    req = db.get(Request, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")

    bundle: dict = {}
    if req.generated_pages:
        try:
            raw = json.loads(req.generated_pages)
            if isinstance(raw, dict):
                bundle = raw
        except (TypeError, json.JSONDecodeError):
            pass

    preview = bundle.get("preview_contract")
    ledger = (preview or {}).get("phase3a_call_ledger") if isinstance(preview, dict) else None

    if ledger is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Phase 3A call ledger not found. "
                "The request may not have completed Phase 3A, "
                "or was processed before this feature was deployed."
            ),
        )

    return ledger


@router.get(
    "/requests/{request_id}/candidate-provider-attempts",
    response_model=AdminPreviewDiagnostics,
)
def get_candidate_provider_attempts(
    request_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    """Return redacted Phase 3B provider-attempt diagnostics.

    Includes call-ledger totals and per-attempt HTTP/shape metadata.
    Never returns prompts, secrets, or full provider response bodies.
    """
    req = db.get(Request, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")

    bundle: dict = {}
    if req.generated_pages:
        try:
            raw = json.loads(req.generated_pages)
            if isinstance(raw, dict):
                bundle = raw
        except (TypeError, json.JSONDecodeError):
            pass

    preview = bundle.get("preview_contract")
    if not isinstance(preview, dict):
        raise HTTPException(
            status_code=404,
            detail="Candidate provider attempts not found for this request.",
        )

    attempts = preview.get("candidate_provider_attempts")
    ledger = preview.get("candidate_call_ledger")
    checkpoints = preview.get("candidate_stage_checkpoints")
    failure = preview.get("failure") if isinstance(preview.get("failure"), dict) else {}
    if attempts is None and ledger is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Candidate provider attempts not found. "
                "The request may not have reached Phase 3B, "
                "or was processed before this feature was deployed."
            ),
        )

    return {
        "request_id": request_id,
        "status": preview.get("status"),
        "candidate_call_ledger": ledger,
        "candidate_stage_checkpoints": checkpoints,
        "candidate_provider_attempts": attempts or [],
        "failure": {
            "kind": failure.get("kind"),
            "error_type": failure.get("error_type"),
            "provider_error_code": failure.get("provider_error_code"),
            "root_cause": failure.get("root_cause"),
            "phase4_ran": failure.get("phase4_ran"),
            "stage": failure.get("stage"),
            "message": failure.get("message"),
        },
    }


@router.get(
    "/requests/{request_id}/progress-diagnostics",
    response_model=AdminProgressDiagnostics,
)
def get_progress_diagnostics(
    request_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    """Return raw persisted progress only to authenticated administrators."""

    req = db.get(Request, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    progress: dict = {}
    if req.generation_log:
        try:
            parsed = json.loads(req.generation_log)
            if isinstance(parsed, dict):
                progress = parsed
        except (TypeError, json.JSONDecodeError):
            pass
    preview_contract = None
    if req.generated_pages:
        try:
            bundle = json.loads(req.generated_pages)
            if isinstance(bundle, dict) and isinstance(
                bundle.get("preview_contract"),
                dict,
            ):
                preview_contract = bundle["preview_contract"]
        except (TypeError, json.JSONDecodeError):
            pass
    return AdminProgressDiagnostics(
        request_id=request_id,
        request_status=str(req.status or "new"),
        progress=progress,
        preview_contract=preview_contract,
    )


@router.get("/requests/{request_id}/runtime-validation-attempts")
def get_runtime_validation_attempts(
    request_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    if db.get(Request, request_id) is None:
        raise HTTPException(status_code=404, detail="Request not found")
    attempts = (
        db.query(CandidateRuntimeValidationAttemptRecord)
        .filter(
            CandidateRuntimeValidationAttemptRecord.request_id == request_id
        )
        .order_by(CandidateRuntimeValidationAttemptRecord.id)
        .all()
    )
    payload = []
    for attempt in attempts:
        builds = (
            db.query(CandidateBuildAttemptRecord)
            .filter(
                CandidateBuildAttemptRecord.runtime_attempt_id == attempt.id
            )
            .order_by(CandidateBuildAttemptRecord.attempt_sequence)
            .all()
        )
        summary = (
            db.query(CandidateValidationSummaryRecord)
            .filter(
                CandidateValidationSummaryRecord.runtime_attempt_id
                == attempt.id
            )
            .first()
        )
        tools = load_json_object(attempt.tool_versions_json)
        limits = load_json_object(attempt.limits_json)
        payload.append(
            {
                "id": attempt.id,
                "request_id": attempt.request_id,
                "candidate_revision_id": attempt.candidate_revision_id,
                "attempt_uuid": attempt.attempt_uuid,
                "attempt_sequence": attempt.attempt_sequence,
                "runtime_policy_revision": attempt.runtime_policy_revision,
                "environment_fingerprint": canonical_sha256(
                    {
                        "tools": tools,
                        "limits": limits,
                        "runtime_policy_revision": (
                            attempt.runtime_policy_revision
                        ),
                    }
                ),
                "tools": tools,
                "limits": limits,
                "workspace_relpath": attempt.workspace_relpath,
                "resumed_from_attempt_id": attempt.resumed_from_attempt_id,
                "build_attempts": [
                    {
                        "id": build.id,
                        "attempt_sequence": build.attempt_sequence,
                        "parent_build_attempt_id": (
                            build.parent_build_attempt_id
                        ),
                        "workspace_relpath": build.workspace_relpath,
                        "result_sha256": build.result_sha256,
                        "result": load_json_object(build.result_json),
                    }
                    for build in builds
                ],
                "summary": (
                    load_json_object(summary.summary_json)
                    if summary is not None
                    else None
                ),
                "summary_sha256": (
                    summary.summary_sha256 if summary is not None else None
                ),
            }
        )
    return {"request_id": request_id, "attempts": payload}


@router.get("/requests/{request_id}/phase4-evidence")
def get_phase4_evidence(
    request_id: int,
    attempt: int = Query(None, ge=1),
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    if db.get(Request, request_id) is None:
        raise HTTPException(status_code=404, detail="Request not found")
    try:
        return build_phase4_evidence(
            db,
            request_id=request_id,
            attempt=attempt,
        )
    except Phase4EvidenceNotFound:
        raise HTTPException(
            status_code=404,
            detail="Runtime validation attempt not found",
        )


@router.get("/requests/{request_id}/run-log")
def get_request_run_log(
    request_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    data = admin_ops.build_request_run_log(db, request_id)
    if not data:
        raise HTTPException(status_code=404, detail="Request not found")
    return data


@router.post("/requests/{request_id}/cancel-generation")
def cancel_generation(
    request_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    req.generation_cancel = True
    db.commit()
    return {"success": True, "request_id": request_id, "cancelled": True}


@router.post("/requests/{request_id}/clear-cancel")
def clear_generation_cancel(
    request_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    req.generation_cancel = False
    db.commit()
    return {"success": True, "request_id": request_id}


@router.patch("/requests/{request_id}", response_model=RequestDetail)
def update_request(
    request_id: int,
    body: RequestUpdate,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(req, key, value)
    db.commit()
    db.refresh(req)
    return req


@router.delete("/requests/{request_id}")
def delete_request(
    request_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    """Remove a request (and related preview chat / app-spec rows) from the DB."""
    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    label = (req.concept_name or req.business_name or f"#{request_id}").strip()
    db.query(PreviewChatMessage).filter(PreviewChatMessage.request_id == request_id).delete(
        synchronize_session=False
    )
    for runtime_model in (
        CandidateValidationSummaryRecord,
        CandidateScreenshotRecord,
        CandidateAccessibilityFindingRecord,
        CandidateJourneyResultRecord,
        CandidateRouteResultRecord,
        CandidateBuildAttemptRecord,
        CandidateRuntimeValidationAttemptRecord,
    ):
        db.query(runtime_model).filter(
            runtime_model.request_id == request_id
        ).delete(synchronize_session=False)
    db.query(CandidateRevisionRecord).filter(
        CandidateRevisionRecord.request_id == request_id
    ).delete(synchronize_session=False)
    db.query(CandidateArtifactRecord).filter(
        CandidateArtifactRecord.request_id == request_id
    ).update(
        {CandidateArtifactRecord.parent_artifact_id: None},
        synchronize_session=False,
    )
    db.query(CandidateArtifactRecord).filter(
        CandidateArtifactRecord.request_id == request_id
    ).delete(synchronize_session=False)
    db.query(CompositionContractArtifactRecord).filter(
        CompositionContractArtifactRecord.request_id == request_id
    ).update(
        {CompositionContractArtifactRecord.parent_artifact_id: None},
        synchronize_session=False,
    )
    db.query(CompositionContractArtifactRecord).filter(
        CompositionContractArtifactRecord.request_id == request_id
    ).delete(synchronize_session=False)
    db.query(DesignContractArtifactRecord).filter(
        DesignContractArtifactRecord.request_id == request_id
    ).update(
        {DesignContractArtifactRecord.parent_artifact_id: None},
        synchronize_session=False,
    )
    db.query(DesignContractArtifactRecord).filter(
        DesignContractArtifactRecord.request_id == request_id
    ).delete(synchronize_session=False)
    # Clear the cumulative self-FK chain before deleting v2 tier artifacts.
    db.query(PreviewTierArtifactRecord).filter(
        PreviewTierArtifactRecord.request_id == request_id
    ).update(
        {PreviewTierArtifactRecord.parent_tier_artifact_id: None},
        synchronize_session=False,
    )
    db.query(PreviewTierArtifactRecord).filter(
        PreviewTierArtifactRecord.request_id == request_id
    ).delete(synchronize_session=False)
    # Clear self-FK before bulk-deleting revisions (SQLite)
    db.query(AppSpecRevision).filter(AppSpecRevision.request_id == request_id).update(
        {AppSpecRevision.parent_revision_id: None},
        synchronize_session=False,
    )
    db.query(AppSpecRevision).filter(AppSpecRevision.request_id == request_id).delete(
        synchronize_session=False
    )
    db.query(ProductStrategyRevision).filter(
        ProductStrategyRevision.request_id == request_id
    ).delete(synchronize_session=False)
    db.query(CustomerSourceArtifact).filter(
        CustomerSourceArtifact.request_id == request_id
    ).delete(synchronize_session=False)
    db.delete(req)
    db.commit()

    preview_dir = Path(settings.PREVIEW_APPS_DIR) / str(request_id)
    if preview_dir.is_dir():
        shutil.rmtree(preview_dir, ignore_errors=True)
    candidate_dir = Path(settings.PREVIEW_CANDIDATES_DIR) / str(request_id)
    if candidate_dir.is_dir():
        shutil.rmtree(candidate_dir, ignore_errors=True)
    validation_dir = Path(settings.PREVIEW_VALIDATIONS_DIR) / str(request_id)
    if validation_dir.is_dir():
        shutil.rmtree(validation_dir, ignore_errors=True)

    return {"success": True, "deleted_id": request_id, "label": label}


@router.get("/requests/{request_id}/file")
def get_request_file(
    request_id: int,
    x_admin_password: str = Header(None, alias="X-Admin-Password"),
    authorization: str = Header(None),
    admin_password: str = Query(None),
    db: Session = Depends(get_db),
):
    password = x_admin_password or admin_password
    allowed = bool(password and password == settings.ADMIN_PASSWORD)
    if not allowed and authorization:
        from app.application.services.user_auth import get_user_by_token

        parts = authorization.split(" ", 1)
        token = parts[1].strip() if len(parts) == 2 and parts[0].lower() == "bearer" else None
        user = get_user_by_token(db, token)
        allowed = bool(user and getattr(user, "is_admin", False))
    if not allowed:
        raise HTTPException(status_code=401, detail="Invalid admin credentials")
    req = db.query(Request).filter(Request.id == request_id).first()
    if not req or not req.reference_file_path:
        raise HTTPException(status_code=404, detail="File not found")
    if not os.path.exists(req.reference_file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(req.reference_file_path)


@router.post("/requests/{request_id}/analyze-screenshot", response_model=GenerateResponse)
def analyze_screenshot(
    request_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    ai_provider: AIProvider = Depends(get_ai_provider_dep),
    template_renderer: TemplateRenderer = Depends(get_template_renderer_dep),
):
    try:
        with ai_run_scope(request_id, purpose="analyze"):
            result = reference_analysis.analyze_screenshot(db, request_id, ai_provider, template_renderer)
        return GenerateResponse(success=True, message="Screenshot analyzed", data=result)
    except Exception as e:
        return GenerateResponse(success=False, message=str(e))


@router.post("/requests/{request_id}/generate-blueprint", response_model=GenerateResponse)
def generate_blueprint(
    request_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    ai_provider: AIProvider = Depends(get_ai_provider_dep),
    template_renderer: TemplateRenderer = Depends(get_template_renderer_dep),
):
    try:
        with ai_run_scope(request_id, purpose="blueprint"):
            result = blueprint.generate_mvp_blueprint(db, request_id, ai_provider, template_renderer)
        return GenerateResponse(success=True, message="Blueprint generated", data=result)
    except Exception as e:
        return GenerateResponse(success=False, message=str(e))


@router.post("/requests/{request_id}/generate-app-spec", response_model=GenerateResponse)
def generate_app_spec(
    request_id: int,
    force_new_revision: bool = Query(False),
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    ai_provider: AIProvider = Depends(get_ai_provider_dep),
    template_renderer: TemplateRenderer = Depends(get_template_renderer_dep),
):
    """Author/review an AppSpec independently of rollout mode."""

    try:
        with ai_run_scope(request_id, purpose="appspec"):
            result = ensure_approved_app_spec(
                db,
                request_id,
                ai_provider,
                template_renderer,
                force_new_revision=force_new_revision,
            )
        return GenerateResponse(
            success=True,
            message="AppSpec accepted",
            data={
                **revision_summary(result.revision_record),
                "reused": result.reused,
                "calls_used": result.calls_used,
                "repair_attempts": result.repair_attempts,
            },
        )
    except Exception as e:
        return GenerateResponse(success=False, message=str(e))


@router.get("/requests/{request_id}/app-specs")
def list_app_specs(
    request_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    return [
        revision_summary(row)
        for row in AppSpecRepository(db).list_revisions(request_id)
    ]


@router.get("/requests/{request_id}/appspec-attempts")
def list_appspec_attempts(
    request_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    """Trusted admin diagnostics for AppSpec authoring/repair attempts."""

    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    rows = AppSpecRepository(db).list_revisions(request_id)
    attempts: list[dict] = []
    for row in rows:
        metadata = load_json_object(row.generation_metadata_json)
        validation = load_json_object(row.deterministic_validation_json)
        diagnostics = metadata.get("schema_diagnostics") or {}
        issues = [
            issue
            for issue in (validation.get("issues") or [])
            if isinstance(issue, dict)
        ]
        typed_issues = [
            {
                "code": issue.get("code"),
                "path": issue.get("path"),
                "message": issue.get("message"),
                "error_type": issue.get("error_type"),
                "offending_value_type": issue.get("offending_value_type"),
            }
            for issue in issues
            if issue.get("code")
            and issue.get("code") != "app_spec_schema_parse_failed"
        ]
        # Prefer persisted typed children from diagnostics when present.
        if diagnostics.get("schema_validation_errors"):
            typed_issues = [
                {
                    "code": issue.get("code"),
                    "path": issue.get("path"),
                    "message": issue.get("message"),
                    "error_type": issue.get("error_type"),
                    "offending_value_type": issue.get("offending_value_type"),
                }
                for issue in diagnostics.get("schema_validation_errors") or []
                if isinstance(issue, dict)
            ]
        attempts.append(
            {
                "id": row.id,
                "revision": row.revision,
                "status": row.status,
                "parent_revision_id": row.parent_revision_id,
                "app_spec_sha256": row.app_spec_sha256,
                "validation_passed": row.validation_passed,
                "coverage_passed": row.coverage_passed,
                "provider": diagnostics.get("provider")
                or metadata.get("author_model"),
                "model": diagnostics.get("model")
                or metadata.get("author_model")
                or metadata.get("repair_model"),
                "prompt_revision": diagnostics.get("prompt_revision")
                or metadata.get("prompt_revision"),
                "terminal_result": diagnostics.get("terminal_result")
                or metadata.get("terminal_reason"),
                "typed_issue_codes": [
                    issue.get("code") for issue in typed_issues if issue.get("code")
                ],
                "typed_issues": typed_issues,
                "json_paths": [
                    issue.get("path") for issue in typed_issues if issue.get("path")
                ],
                "repair_attempts": {
                    "graph_repair": metadata.get("graph_repair") or {},
                    "lineage": metadata.get("lineage") or {},
                    "deterministic_heals": metadata.get("deterministic_heals"),
                    "repair_attempts": metadata.get("repair_attempts"),
                },
                "hashes": {
                    "app_spec_sha256": row.app_spec_sha256,
                    "raw_response_sha256": diagnostics.get("raw_response_sha256"),
                    "original_sha256": diagnostics.get("original_sha256"),
                    "result_sha256": diagnostics.get("result_sha256"),
                },
                "redacted_candidate_excerpt": diagnostics.get("redacted_candidate"),
                "created_at": row.created_at,
                "validated_at": row.validated_at,
            }
        )
    return {
        "request_id": request_id,
        "attempt_count": len(attempts),
        "attempts": attempts,
    }


@router.get("/requests/{request_id}/app-specs/{revision}")
def get_app_spec_revision(
    request_id: int,
    revision: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    row = AppSpecRepository(db).get_revision(request_id, revision)
    if not row:
        raise HTTPException(status_code=404, detail="AppSpec revision not found")
    return {
        **revision_summary(row),
        "app_spec": load_json_object(row.app_spec_json),
        "deterministic_validation": load_json_object(
            row.deterministic_validation_json
        ),
        "semantic_coverage": load_json_object(row.semantic_coverage_json),
        "generation_metadata": load_json_object(row.generation_metadata_json),
        "parent_revision_id": row.parent_revision_id,
    }


@router.post("/requests/{request_id}/generate-visual-demo", response_model=GenerateResponse)
def generate_visual_demo(
    request_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    ai_provider: AIProvider = Depends(get_ai_provider_dep),
    template_renderer: TemplateRenderer = Depends(get_template_renderer_dep),
):
    try:
        with ai_run_scope(request_id, purpose="demo"):
            result = visual_demo.generate_visual_demo(db, request_id, ai_provider, template_renderer)
        return GenerateResponse(success=True, message="Visual demo generated", data=result)
    except Exception as e:
        return GenerateResponse(success=False, message=str(e))


@router.post("/requests/{request_id}/generate-technical-plan", response_model=GenerateResponse)
def generate_technical_plan(
    request_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    ai_provider: AIProvider = Depends(get_ai_provider_dep),
    template_renderer: TemplateRenderer = Depends(get_template_renderer_dep),
):
    try:
        with ai_run_scope(request_id, purpose="tech"):
            result = technical_plan.generate_technical_plan(db, request_id, ai_provider, template_renderer)
        return GenerateResponse(success=True, message="Technical plan generated", data=result)
    except Exception as e:
        return GenerateResponse(success=False, message=str(e))


@router.post("/requests/{request_id}/generate-proposal", response_model=GenerateResponse)
def generate_proposal(
    request_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    ai_provider: AIProvider = Depends(get_ai_provider_dep),
    template_renderer: TemplateRenderer = Depends(get_template_renderer_dep),
):
    try:
        with ai_run_scope(request_id, purpose="proposal"):
            result = proposal.generate_proposal(db, request_id, ai_provider, template_renderer)
        return GenerateResponse(success=True, message="Proposal generated", data=result)
    except Exception as e:
        return GenerateResponse(success=False, message=str(e))


@router.post("/requests/{request_id}/generate-build-plans", response_model=GenerateResponse)
def generate_build_plans_admin(
    request_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    ai_provider: AIProvider = Depends(get_ai_provider_dep),
    template_renderer: TemplateRenderer = Depends(get_template_renderer_dep),
):
    try:
        with ai_run_scope(request_id, purpose="build_plans"):
            result = build_plans.generate_build_plans(db, request_id, ai_provider, template_renderer)
        return GenerateResponse(success=True, message="Build plans generated", data=result)
    except Exception as e:
        return GenerateResponse(success=False, message=str(e))


@router.post("/requests/{request_id}/generate-full", response_model=GenerateResponse)
def generate_full(
    request_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
    ai_provider: AIProvider = Depends(get_ai_provider_dep),
    template_renderer: TemplateRenderer = Depends(get_template_renderer_dep),
):
    try:
        result = orchestrator.GenerationPipeline(ai_provider, template_renderer).run(db, request_id)
        return GenerateResponse(success=True, message="Full pipeline completed", data=result)
    except Exception as e:
        return GenerateResponse(success=False, message=str(e))


@router.get("/requests/{request_id}/whatsapp-message")
def get_whatsapp_message(
    request_id: int,
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    features = []
    if req.preview_features:
        try:
            features = json.loads(req.preview_features)
        except Exception:
            features = [f.strip() for f in req.preview_features.split("\n") if f.strip()]

    top_features = ", ".join(features[:3]) if features else "core MVP features"
    name = req.business_name.split()[0] if req.business_name else "there"
    concept = req.concept_name or "your custom MVP"

    message = (
        f"Hi {name}, I reviewed your business and the reference tool you shared.\n\n"
        f"The idea can be adapted into a custom MVP called {concept}.\n\n"
        f"The first version would include {top_features}.\n\n"
        f"I can send you the full proposal with scope and timeline."
    )

    return {"message": message}
