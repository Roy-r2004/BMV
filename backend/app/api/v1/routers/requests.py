import json
import threading
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_ai_provider_dep, get_db, get_template_renderer_dep
from app.application.pipelines.orchestrator import GenerationPipeline
from app.application.pipelines.role_pages import generate_role_pages
from app.application.preview_app import generate_preview_app
from app.application.services.preview_parser import parse_preview_features
from app.application.services.preview_refinement import get_chat_history, refine_preview
from app.application.services.reference_formatter import format_reference_analysis
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.models.request import Request
from app.domain.schemas.chat import ChatHistoryResponse, ChatMessage, ChatSendRequest, ChatSendResponse
from app.domain.schemas.request import (
    BuildRequestBody,
    BuildRequestResponse,
    PreviewResponse,
    RequestCreateResponse,
)
from app.infrastructure.ai_providers.factory import get_ai_provider
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.storage.file_service import save_upload
from app.infrastructure.templating.renderer import get_template_renderer
from app.infrastructure.web.reference_scraper import fetch_reference_metadata

router = APIRouter(prefix="/api/requests", tags=["requests"])


def _run_pipeline_in_background(request_id: int) -> None:
    """Run the (long, blocking) AI pipeline on its own thread + DB session.

    Never run this directly inside an async request handler — it would freeze
    the whole server's event loop for the entire generation (can take 10-20+ min).
    """
    bg_db = SessionLocal()
    try:
        GenerationPipeline(get_ai_provider(), get_template_renderer()).run(bg_db, request_id)
    except Exception:
        pass
    finally:
        bg_db.close()


@router.post("", response_model=RequestCreateResponse)
async def create_request(
    business_name: str = Form(...),
    business_description: str = Form(...),
    email: str = Form(...),
    industry: str = Form(None),
    target_customers: str = Form(None),
    main_problem: str = Form(None),
    reference_url: str = Form(None),
    what_you_like: str = Form(None),
    desired_outcome: str = Form(None),
    project_type: str = Form(None),
    existing_product_url: str = Form(None),
    needs_ai: str = Form(None),
    budget_range: str = Form(None),
    timeline: str = Form(None),
    whatsapp: str = Form(None),
    reference_file: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    file_path = None
    if reference_file and reference_file.filename:
        file_path = save_upload(reference_file)

    req = Request(
        business_name=business_name,
        industry=industry,
        business_description=business_description,
        target_customers=target_customers,
        main_problem=main_problem,
        reference_url=reference_url,
        reference_file_path=file_path,
        what_you_like=what_you_like,
        desired_outcome=desired_outcome,
        project_type=project_type or 'new',
        existing_product_url=existing_product_url,
        needs_ai=needs_ai,
        budget_range=budget_range,
        timeline=timeline,
        email=email,
        whatsapp=whatsapp,
        status="new",
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    if reference_url:
        metadata = fetch_reference_metadata(reference_url)
        req.reference_metadata = json.dumps(metadata)
        db.commit()

    # Run the (long) AI pipeline on a background thread so this request
    # returns immediately and the frontend can poll live progress.
    threading.Thread(
        target=_run_pipeline_in_background,
        args=(req.id,),
        daemon=True,
    ).start()

    return RequestCreateResponse(id=req.id, status="created")


@router.get("/{request_id}/preview", response_model=PreviewResponse)
def get_preview(request_id: int, db: Session = Depends(get_db)):
    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    visual_demo = None
    if req.visual_demo_json:
        try:
            visual_demo = json.loads(req.visual_demo_json)
        except Exception:
            pass

    generated_pages = None
    if req.generated_pages:
        try:
            generated_pages = json.loads(req.generated_pages)
        except Exception:
            pass

    is_generating = not req.mvp_blueprint and req.status == "new"

    return PreviewResponse(
        id=req.id,
        business_name=req.business_name,
        business_fit_score=req.business_fit_score,
        concept_name=req.concept_name,
        preview_summary=req.preview_summary,
        preview_features=parse_preview_features(req.preview_features),
        visual_demo=visual_demo,
        generated_pages=generated_pages,
        status=req.status,
        is_generating=is_generating,
        industry=req.industry,
        timeline=req.timeline,
        budget_range=req.budget_range,
        desired_outcome=req.desired_outcome,
        main_problem=req.main_problem,
        screenshot_analysis=req.screenshot_analysis,
        reference_analysis=format_reference_analysis(req),
        reference_url=req.reference_url,
        what_you_like=req.what_you_like,
        mvp_blueprint=req.mvp_blueprint,
        technical_plan=req.technical_plan,
        proposal_draft=req.proposal_draft,
        build_requested=req.build_requested or False,
    )


def _run_preview_app_in_background(request_id: int) -> None:
    bg_db = SessionLocal()
    try:
        generate_preview_app(bg_db, request_id, get_ai_provider(), get_template_renderer())
    except Exception:
        pass
    finally:
        bg_db.close()


def _run_role_pages_in_background(request_id: int) -> None:
    bg_db = SessionLocal()
    try:
        generate_role_pages(bg_db, request_id, get_ai_provider(), get_template_renderer())
    except Exception:
        pass
    finally:
        bg_db.close()


@router.post("/{request_id}/generate-preview-app")
def trigger_generate_preview_app(request_id: int, db: Session = Depends(get_db)):
    """Generate a unique React + Tailwind mini-app for this request (runs in background)."""
    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if not req.mvp_blueprint:
        raise HTTPException(status_code=400, detail="Blueprint not generated yet")

    threading.Thread(
        target=_run_preview_app_in_background, args=(request_id,), daemon=True,
    ).start()
    return {"ok": True, "status": "started"}


@router.post("/{request_id}/generate-pages")
def trigger_generate_pages(request_id: int, db: Session = Depends(get_db)):
    """Re-run the role pages generation for an existing request (runs in background)."""
    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if not req.mvp_blueprint:
        raise HTTPException(status_code=400, detail="Blueprint not generated yet")

    threading.Thread(
        target=_run_role_pages_in_background, args=(request_id,), daemon=True,
    ).start()
    return {"ok": True, "status": "started"}


@router.post("/{request_id}/request-build", response_model=BuildRequestResponse)
def request_build(request_id: int, body: BuildRequestBody, db: Session = Depends(get_db)):
    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    req.email = body.email.strip()
    if body.whatsapp:
        req.whatsapp = body.whatsapp.strip()
    note_line = f"Build request from {body.contact_name.strip()} ({body.email.strip()})"
    if body.whatsapp:
        note_line += f" · WhatsApp: {body.whatsapp.strip()}"
    if body.notes:
        note_line += f"\nNotes: {body.notes.strip()}"
    if req.admin_notes:
        req.admin_notes = f"{req.admin_notes}\n\n{note_line}"
    else:
        req.admin_notes = note_line

    req.build_requested = True
    req.build_requested_at = datetime.utcnow()
    req.status = "reviewing"
    req.updated_at = datetime.utcnow()
    db.commit()

    return BuildRequestResponse(
        id=req.id,
        build_requested=True,
        status=req.status,
    )


@router.get("/{request_id}/progress")
def get_generation_progress(request_id: int, db: Session = Depends(get_db)):
    """Return the live generation progress snapshot for the loading screen."""
    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    if not req.generation_log:
        # Nothing emitted yet — just started
        return {
            "stage": "starting",
            "label": "Starting generation...",
            "pct": 0,
            "detail": "",
            "files_done": 0,
            "files_total": 0,
            "log": [],
        }

    try:
        return json.loads(req.generation_log)
    except Exception:
        return {"stage": "unknown", "label": "Working...", "pct": 0, "log": []}


@router.get("/{request_id}/chat", response_model=ChatHistoryResponse)
def get_request_chat(request_id: int, db: Session = Depends(get_db)):
    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    messages = get_chat_history(db, request_id)
    return ChatHistoryResponse(messages=[ChatMessage(**m) for m in messages])


@router.post("/{request_id}/chat", response_model=ChatSendResponse)
def send_request_chat(
    request_id: int,
    body: ChatSendRequest,
    db: Session = Depends(get_db),
    ai_provider: AIProvider = Depends(get_ai_provider_dep),
    template_renderer: TemplateRenderer = Depends(get_template_renderer_dep),
):
    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    try:
        result = refine_preview(db, request_id, body.message, ai_provider, template_renderer)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to process your message. Please try again.") from exc

    return ChatSendResponse(
        reply=result["reply"],
        changes_made=result.get("changes_made", []),
        preview_updated=result.get("preview_updated", False),
        concept_name=result.get("concept_name"),
        preview_summary=result.get("preview_summary"),
        preview_features=result.get("preview_features", []),
        business_fit_score=result.get("business_fit_score"),
        visual_demo=result.get("visual_demo"),
    )
