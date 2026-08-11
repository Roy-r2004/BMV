import json
import threading

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Request
from app.pipeline import export_pptx, orchestrator

router = APIRouter(prefix="/api/requests", tags=["requests"])


@router.post("")
def create_request(
    business_name: str = Form(...),
    business_description: str = Form(...),
    email: str = Form(...),
    industry: str | None = Form(None),
    target_customers: str | None = Form(None),
    main_problem: str | None = Form(None),
    reference_url: str | None = Form(None),
    what_you_like: str | None = Form(None),
    desired_outcome: str | None = Form(None),
    needs_ai: str | None = Form(None),
    budget_range: str | None = Form(None),
    timeline: str | None = Form(None),
    whatsapp: str | None = Form(None),
    db: Session = Depends(get_db),
):
    # Every accepted request spends real AI money — cap how many can be
    # generating at once so an unauthenticated burst can't drain the credit
    # balance (found in review).
    in_flight = db.query(Request).filter(Request.is_generating.is_(True)).count()
    if in_flight >= settings.MAX_CONCURRENT_GENERATIONS:
        raise HTTPException(
            status_code=429,
            detail="We're generating a lot of previews right now — please try again in a few minutes.",
        )

    req = Request(
        business_name=business_name,
        business_description=business_description,
        email=email,
        industry=industry,
        target_customers=target_customers,
        main_problem=main_problem,
        reference_url=reference_url,
        what_you_like=what_you_like,
        desired_outcome=desired_outcome,
        needs_ai=needs_ai,
        budget_range=budget_range,
        timeline=timeline,
        whatsapp=whatsapp,
        status="new",
        is_generating=True,
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    threading.Thread(target=orchestrator.run, args=(req.id,), daemon=True).start()

    return {"id": req.id, "status": req.status}


@router.get("/{request_id}/progress")
def get_progress(request_id: int, db: Session = Depends(get_db)):
    req = db.get(Request, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return {
        "stage": req.stage,
        "label": req.stage_label,
        "pct": req.progress_pct,
        "detail": req.progress_detail,
        "is_generating": req.is_generating,
        "is_failed": req.is_failed,
        "updated_at": req.updated_at.isoformat() if req.updated_at else None,
    }


@router.get("/{request_id}/preview")
def get_preview(request_id: int, db: Session = Depends(get_db)):
    req = db.get(Request, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")

    recommendations = json.loads(req.consulting_recommendations_json) if req.consulting_recommendations_json else {}
    ai_features = [
        {
            "id": f"ai-employee-{i}",
            "name": emp.get("title", "AI Employee"),
            "description": emp.get("why", ""),
            "category": "ai_employee",
        }
        for i, emp in enumerate(recommendations.get("recommended_ai_employees", []), start=1)
    ]
    attraction_images = [
        {
            "role_id": img.role_id,
            "role_label": img.role_label,
            "image_url": img.file_path,
            "variant": img.variant,
        }
        for img in sorted(req.images, key=lambda i: (i.role_id, i.variant))
    ]

    return {
        "id": req.id,
        "business_name": req.business_name,
        "business_fit_score": None,
        "concept_name": req.concept_name,
        "preview_summary": req.consulting_analysis,
        "preview_features": recommendations.get("recommended_features", []),
        "ai_features": ai_features,
        "mvp_blueprint": req.mvp_blueprint,
        "technical_plan": req.technical_plan,
        "visual_demo": None,
        "generated_pages": {"attraction_images": attraction_images},
        "status": req.status,
        "is_generating": req.is_generating,
        "industry": req.industry,
        "timeline": req.timeline,
        "budget_range": req.budget_range,
        "desired_outcome": req.desired_outcome,
        "main_problem": req.main_problem,
        "reference_url": req.reference_url,
        "what_you_like": req.what_you_like,
    }


@router.get("/{request_id}/export/pptx")
def export_pptx_route(request_id: int, db: Session = Depends(get_db)):
    req = db.get(Request, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    if not req.roles_json:
        raise HTTPException(status_code=400, detail="Plan not ready yet")

    analysis = json.loads(req.business_analysis_json) if req.business_analysis_json else {}
    consult_result = json.loads(req.consulting_recommendations_json) if req.consulting_recommendations_json else {}
    plan_result = {
        "concept_name": req.concept_name,
        "roles": json.loads(req.roles_json),
        "visual_theme": json.loads(req.visual_theme_json) if req.visual_theme_json else {},
    }

    prs = export_pptx.build_presentation(req, analysis, consult_result, plan_result, list(req.images))
    out_path = export_pptx.export_path_for(request_id)
    prs.save(out_path)

    file_stub = "".join(c if c.isalnum() else "-" for c in (req.concept_name or req.business_name or "deck"))
    return FileResponse(
        out_path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=f"{file_stub}.pptx",
    )
