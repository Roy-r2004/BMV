import json
import logging
import threading
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import AiUsageEvent, Request
from app.pipeline import compositing, export_pptx, orchestrator, screen_story, what_this_is

logger = logging.getLogger("consultant.requests")

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
    site_url: str | None = Form(None),
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
        site_url=site_url,
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
        # Carried so a run resumed from its own URL — a refresh, a bookmark,
        # a link opened on a phone — can name the business it is designing
        # for instead of falling back to "your business".
        "business_name": req.business_name,
        "stage": req.stage,
        "label": req.stage_label,
        "pct": req.progress_pct,
        "detail": req.progress_detail,
        "is_generating": req.is_generating,
        "is_failed": req.is_failed,
        "updated_at": req.updated_at.isoformat() if req.updated_at else None,
        # How long this run has been going, computed HERE rather than from a
        # timestamp the browser has to interpret. created_at is a naive
        # utcnow(), which a browser parses as local time — a client-side
        # subtraction would show a clock off by the viewer's UTC offset, and
        # a customer watching a three-minute wait counts every second of it.
        "elapsed_s": max(0, int((datetime.utcnow() - req.created_at).total_seconds())) if req.created_at else 0,
    }


@router.get("/{request_id}/preview")
def get_preview(request_id: int, db: Session = Depends(get_db)):
    req = db.get(Request, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")

    recommendations = json.loads(req.consulting_recommendations_json) if req.consulting_recommendations_json else {}
    # The analyze stage's own diagnosis, already persisted since the first
    # pipeline stage — read back out rather than re-derived, so the reveal
    # never states a finding the consulting/blueprint stages didn't also see.
    analysis = json.loads(req.business_analysis_json) if req.business_analysis_json else {}
    site_research = json.loads(req.site_research_json) if req.site_research_json else None
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
            # W4 composites when they exist. Null rather than absent, and
            # never a guessed URL: a broken <img> in a lead's preview is
            # worse than no hero shot.
            "hero_url": compositing.variant_url(img.file_path, "hero", settings.UPLOADS_DIR),
            "detail_urls": [
                url for url in (
                    compositing.variant_url(img.file_path, "detail_1", settings.UPLOADS_DIR),
                    compositing.variant_url(img.file_path, "detail_2", settings.UPLOADS_DIR),
                ) if url
            ],
            # What this screen is and where the AI sits on it, read from the
            # spec it was drawn from. Null on screens generated before the
            # spec was persisted.
            "story": screen_story.from_spec_json(img.spec_json, img.role_label or ""),
        }
        for img in sorted(req.images, key=lambda i: (i.role_id, i.variant))
    ]

    return {
        "id": req.id,
        "business_name": req.business_name,
        "business_fit_score": None,
        "concept_name": req.concept_name,
        # What class of software this is, in the customer's own nouns. Null
        # when the plan stage has not named a concept yet — the page then
        # says nothing rather than something vague.
        "what_this_is": what_this_is.build(
            req.business_name, req.concept_name, req.business_description,
        ),
        "preview_summary": req.consulting_analysis,
        "preview_features": recommendations.get("recommended_features", []),
        "ai_features": ai_features,
        "mvp_blueprint": req.mvp_blueprint,
        "technical_plan": req.technical_plan,
        "visual_demo": None,
        "generated_pages": {"attraction_images": attraction_images},
        # Whether /export/pptx will actually produce a deck. It is exactly
        # that route's own precondition, read from here so the result page can
        # decide whether to offer the download instead of handing a customer a
        # button that 400s.
        "deck_available": bool(req.roles_json),
        "status": req.status,
        "is_generating": req.is_generating,
        "industry": req.industry,
        "timeline": req.timeline,
        "budget_range": req.budget_range,
        "desired_outcome": req.desired_outcome,
        "main_problem": req.main_problem,
        "reference_url": req.reference_url,
        "what_you_like": req.what_you_like,
        # Null rather than the analyze stage's own fallback sentinel
        # ("Unknown") — a client reading "we classified you as Unknown"
        # is worse than the diagnosis panel not rendering at all.
        "business_model": analysis.get("business_model") if analysis.get("business_model") not in (None, "Unknown") else None,
        "target_customer_profile": analysis.get("target_customer_profile") or None,
        "pain_points": analysis.get("pain_points") or [],
        "growth_opportunity": analysis.get("growth_opportunity") or None,
        # Null when no site_url was given, the fetch failed, or the page had
        # too little content — the frontend renders nothing in that case,
        # same rule as every other optional field on this payload.
        "site_research": site_research,
    }


@router.get("/{request_id}/admin")
def get_admin_detail(request_id: int, db: Session = Depends(get_db)):
    """Operator view of one request: what it cost, on which models, and how
    each screen scored.

    Deliberately its own endpoint rather than a block on /preview — that
    payload is what a lead sees, and the money must never be one careless
    frontend change away from being rendered on it.

    Cost comes from this service's own ai_usage_events rows, never from the
    OpenRouter key balance: the key is shared, so a balance delta is not
    this request's cost.
    """
    req = db.get(Request, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")

    events = db.query(AiUsageEvent).filter(AiUsageEvent.request_id == request_id).all()

    def _bucket(rows: list[AiUsageEvent]) -> dict:
        return {
            "calls": len(rows),
            "failed": sum(1 for e in rows if not e.success),
            "cost_usd": round(sum(e.cost_usd or 0 for e in rows), 5),
        }

    by_purpose = {p: _bucket([e for e in events if e.purpose == p]) for p in sorted({e.purpose for e in events})}
    by_model = {m: _bucket([e for e in events if e.model == m]) for m in sorted({e.model for e in events})}
    image_events = [e for e in events if e.purpose == "image" and e.success]

    def _screen_cost(role_id: str) -> dict:
        """What this one screen cost, from the rows tagged with it. A screen
        that took its allowed regeneration is twice the price of one that
        did not, and that difference is the whole reason an operator opens
        this view. Rows written before the `screen` column existed are
        untagged, so an old request reports zeros here rather than a wrong
        split — absent, not invented."""
        rows = [e for e in events if e.screen == role_id]
        images = [e for e in rows if e.purpose == "image"]
        return {
            "total_usd": round(sum(e.cost_usd or 0 for e in rows), 5),
            "images_usd": round(sum(e.cost_usd or 0 for e in images if e.success), 5),
            "image_calls": sum(1 for e in images if e.success),
            "failed_image_calls": sum(1 for e in images if not e.success),
        }

    return {
        "id": req.id,
        "business_name": req.business_name,
        "status": req.status,
        "is_generating": req.is_generating,
        "cost": {
            # The single number an operator actually wants, plus the
            # breakdown that explains it. Rounded to 5dp because a flash
            # QA call is ~$0.001 and rounding to cents would show $0.00.
            "total_usd": round(sum(e.cost_usd or 0 for e in events), 5),
            "images_usd": round(sum(e.cost_usd or 0 for e in image_events), 5),
            "images_generated": len(image_events),
            "cost_per_image_usd": (
                round(sum(e.cost_usd or 0 for e in image_events) / len(image_events), 5)
                if image_events else None
            ),
            "by_purpose": by_purpose,
            "by_model": by_model,
            # Calls that were made and billed but produced nothing usable —
            # the number that tells an operator a cost rise is waste rather
            # than volume.
            "failed_calls": sum(1 for e in events if not e.success),
        },
        "screens": [
            {
                "role_id": img.role_id,
                "role_label": img.role_label,
                "model": img.model,
                "composition_variant": img.composition_variant,
                "prompt_version": img.prompt_version,
                "qa_score": img.qa_score,
                "qa_issues": json.loads(img.qa_issues) if img.qa_issues else [],
                # The W3 gate's verdict for the shipped screen. `null` means
                # the gate did not run or predates the column — it does NOT
                # mean the screen passed, and an operator reading this must
                # be able to tell those apart.
                "text_truth": json.loads(img.text_truth_json) if img.text_truth_json else None,
                "cost": _screen_cost(img.role_id),
                "image_url": img.file_path,
                "hero_url": compositing.variant_url(img.file_path, "hero", settings.UPLOADS_DIR),
            }
            for img in sorted(req.images, key=lambda i: (i.role_id, i.variant))
        ],
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
