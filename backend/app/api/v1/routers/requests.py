import json
import threading
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_ai_provider_dep, get_db, get_template_renderer_dep
from app.application.pipelines.orchestrator import GenerationPipeline
from app.application.pipelines.role_pages import generate_role_pages
from app.application.preview_app import generate_preview_app
from app.application.services.progress import emit as _emit
from app.application.services.progress import is_request_generating, progress_payload
from app.application.services.ai_features import ai_features_from_request
from app.application.services.preview_parser import parse_preview_features
from app.application.services.preview_refinement import get_chat_history, refine_preview
from app.application.appspec.repository import (
    AppSpecRepository,
    revision_summary,
)
from app.application.appspec import (
    app_spec_is_required,
    app_spec_mode,
)
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
from app.infrastructure.logging import get_logger
from app.infrastructure.logging.diagnostics import dump_exception, summarize_workspace_debug

router = APIRouter(prefix="/api/requests", tags=["requests"])
pipeline_log = get_logger("RequestPipeline")

_preview_gen_locks: dict[int, threading.Lock] = {}
_preview_gen_locks_guard = threading.Lock()

def _preview_gen_lock(request_id: int) -> threading.Lock:
    with _preview_gen_locks_guard:
        lock = _preview_gen_locks.get(request_id)
        if lock is None:
            lock = threading.Lock()
            _preview_gen_locks[request_id] = lock
        return lock

def _run_pipeline_in_background(request_id: int) -> None:
    """Run the (long, blocking) AI pipeline on its own thread + DB session.

    Never run this directly inside an async request handler — it would freeze
    the whole server's event loop for the entire generation (can take 10-20+ min).
    """
    bg_db = SessionLocal()
    try:
        pipeline_log.info("Starting background pipeline for request %s", request_id)
        GenerationPipeline(get_ai_provider(), get_template_renderer()).run(bg_db, request_id)
        pipeline_log.info("Finished background pipeline for request %s", request_id)
    except Exception as exc:
        safe = str(exc)
        if "Bearer sk-" in safe or "sk-or-" in safe:
            safe = "OpenRouter API key is invalid or has whitespace — re-save OPENROUTER_API_KEY in Render (no trailing spaces/newlines)."
        pipeline_log.error("Background pipeline FAILED request %s: %s", request_id, safe)
        pipeline_log.exception("Pipeline traceback for request %s", request_id)
        try:
            from app.application.preview_app.workspace import get_workspace

            ws = get_workspace(request_id)
            if ws.exists():
                dump_exception(ws, "pipeline", f"background-crash-{request_id}", exc)
                report = summarize_workspace_debug(ws)
                for issue in report.get("top_issues", [])[:10]:
                    pipeline_log.error("request %s debug: %s", request_id, issue)
        except Exception as dump_exc:
            pipeline_log.warning("could not write crash debug artifacts: %s", dump_exc)
        try:
            _emit(
                bg_db,
                request_id,
                "failed",
                f"Generation failed: {safe}",
                0,
                detail=safe[:300],
            )
            req = bg_db.query(Request).filter(Request.id == request_id).first()
            if req and req.status != "failed":
                # Always terminal-fail so the customer UI stops polling and shows error.
                req.status = "failed"
                bg_db.commit()
        except Exception:
            pipeline_log.error("could not persist failure for request %s", request_id)
    finally:
        bg_db.close()

@router.post("/{request_id}/retry-generation")
def retry_generation(request_id: int, db: Session = Depends(get_db)):
    """Restart generation for a stuck or failed request.

    Pre-blueprint: full `GenerationPipeline`.
    Post-blueprint: re-run preview app generation so the customer can recover
    without submitting a brand-new request.
    """
    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")


    req.status = "new"
    if not req.mvp_blueprint:
        _emit(db, request_id, "analyze", "Restarting generation...", 1, detail="Retry requested")
        threading.Thread(
            target=_run_pipeline_in_background,
            args=(request_id,),
            daemon=True,
        ).start()
        return {"ok": True, "status": "restarted", "id": request_id, "mode": "full"}

    _emit(
        db,
        request_id,
        "codegen",
        "Retrying live preview build...",
        28,
        detail="Restarting UI generation from your blueprint",
    )
    threading.Thread(
        target=_run_preview_app_in_background,
        args=(request_id,),
        daemon=True,
    ).start()
    return {"ok": True, "status": "restarted", "id": request_id, "mode": "preview_app"}


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

    app_spec_revision = AppSpecRepository(db).latest_accepted(request_id)

    is_generating = is_request_generating(req)


    return PreviewResponse(
        id=req.id,
        business_name=req.business_name,
        business_fit_score=req.business_fit_score,
        concept_name=req.concept_name,
        preview_summary=req.preview_summary,
        preview_features=parse_preview_features(req.preview_features),
        ai_features=ai_features_from_request(req),
        visual_demo=visual_demo,
        generated_pages=generated_pages,
        app_spec=(
            revision_summary(app_spec_revision)
            if app_spec_revision
            else None
        ),
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
    # One generation at a time per request — concurrent runs race on the same
    # workspace (Playwright + Vite) and can leave a failed/partial build.
    lock = _preview_gen_lock(request_id)
    if not lock.acquire(blocking=False):
        pipeline_log.debug("preview app generation already running for request %s — skip", request_id)
        return
    bg_db = SessionLocal()
    try:
        generate_preview_app(bg_db, request_id, get_ai_provider(), get_template_renderer())
    except Exception as e:
        pipeline_log.exception("preview app generation failed for request %s", request_id)
        try:
            _emit(bg_db, request_id, "failed", f"Generation failed: {e}", 0)
        except Exception:
            pass
    finally:
        bg_db.close()
        lock.release()

def _run_role_pages_in_background(request_id: int) -> None:
    bg_db = SessionLocal()
    try:
        generate_role_pages(bg_db, request_id, get_ai_provider(), get_template_renderer())
    except Exception:
        pipeline_log.exception("role pages generation failed for request %s", request_id)
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

    bundle: dict = {}
    if req.generated_pages:
        try:
            bundle = json.loads(req.generated_pages)
        except Exception:
            bundle = {}
    app_spec_ref = bundle.get("app_spec_ref") or {}
    if app_spec_is_required(
        mode=app_spec_mode(),
        is_new_request=(
            not bool(req.generated_pages) or bool(app_spec_ref.get("enforced"))
        ),
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Legacy role-page generation is disabled for AppSpec previews. "
                "Use generate-preview-app so routes and interactions remain traceable."
            ),
        )

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

    return progress_payload(req)

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
        preview_rebuild_started=result.get("preview_rebuild_started", False),
        concept_name=result.get("concept_name"),
        preview_summary=result.get("preview_summary"),
        preview_features=result.get("preview_features", []),
        business_fit_score=result.get("business_fit_score"),
        visual_demo=result.get("visual_demo"),
    )
