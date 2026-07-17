import json
import os

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_ai_provider_dep, get_db, get_template_renderer_dep, verify_admin
from app.application.pipelines import blueprint, orchestrator, proposal, reference_analysis, technical_plan, visual_demo
from app.application.appspec import ensure_approved_app_spec
from app.application.appspec.repository import (
    AppSpecRepository,
    load_json_object,
    revision_summary,
)
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.models.request import Request
from app.domain.schemas.admin import (
    AdminLoginRequest,
    AdminLoginResponse,
    RequestDetail,
    RequestListItem,
    RequestUpdate,
)
from app.domain.schemas.common import GenerateResponse

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/login", response_model=AdminLoginResponse)
def admin_login(body: AdminLoginRequest):
    if body.password == settings.ADMIN_PASSWORD:
        return AdminLoginResponse(success=True, message="Login successful")
    return AdminLoginResponse(success=False, message="Invalid password")


@router.get("/requests", response_model=list[RequestListItem])
def list_requests(
    status: str = Query(None),
    _: bool = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    query = db.query(Request).order_by(Request.created_at.desc())
    if status and status != "all":
        query = query.filter(Request.status == status)
    return query.all()


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


@router.get("/requests/{request_id}/file")
def get_request_file(
    request_id: int,
    x_admin_password: str = Header(None, alias="X-Admin-Password"),
    admin_password: str = Query(None),
    db: Session = Depends(get_db),
):
    password = x_admin_password or admin_password
    if password != settings.ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin password")
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
        result = proposal.generate_proposal(db, request_id, ai_provider, template_renderer)
        return GenerateResponse(success=True, message="Proposal generated", data=result)
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
