import hmac
import json
import secrets
import logging
import os
import threading
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Header, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import auth_client
from app.config import settings
from app.database import get_db
from app.models import AiUsageEvent, Request
from app.pipeline import compositing, export_pdf, export_pptx, orchestrator, screen_story, what_this_is

logger = logging.getLogger("consultant.requests")

router = APIRouter(prefix="/api/requests", tags=["requests"])


_ALLOWED_STAGES = {"operating", "opening"}
_ALLOWED_ENGAGEMENTS = {"full", "capability"}


def _showcase_ids() -> set[int]:
    out = set()
    for part in (settings.SHOWCASE_IDS or "").split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


def _can_view(req: Request, review_token: str | None, authorization: str | None) -> tuple[bool, int, str]:
    # (allowed, status_code_if_not, message). Order: reviewer, showcase,
    # legacy public (no owner), then owner match.
    if _is_reviewer(review_token):
        return True, 0, ""
    if req.id in _showcase_ids():
        return True, 0, ""
    if not req.owner_email:
        return True, 0, ""
    user = auth_client.resolve_user(authorization)
    if user is None:
        return False, 401, "Sign in to view your engagement"
    if user["email"].lower() != req.owner_email.lower():
        return False, 403, "This engagement belongs to another account"
    return True, 0, ""


def _require_view(req: Request, review_token: str | None, authorization: str | None) -> None:
    allowed, code, message = _can_view(req, review_token, authorization)
    if not allowed:
        raise HTTPException(status_code=code, detail=message)


def _load_request(ref: str, db: Session) -> Request:
    """Resolve a run by numeric id (legacy/showcase) or public_id slug."""
    req = None
    if ref.isdigit():
        req = db.get(Request, int(ref))
    else:
        req = db.query(Request).filter(Request.public_id == ref).first()
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return req


def _is_reviewer(review_token: str | None) -> bool:
    return bool(
        settings.REVIEW_TOKEN
        and review_token
        and hmac.compare_digest(review_token, settings.REVIEW_TOKEN)
    )


def _pending_for(req: Request, review_token: str | None) -> bool:
    # True when this run is held from THIS caller. Only REVIEW_MODE="gate"
    # holds results back; the default "on" is oversight — the client sees
    # their result the moment it finishes, and the consultant reviews,
    # edits and signs after delivery.
    return (
        settings.REVIEW_MODE == "gate"
        and req.review_status == "pending"
        and not _is_reviewer(review_token)
    )


def _teaser_payload(req: Request) -> dict:
    # What the waiting client may see: real facts about their engagement,
    # none of the deliverable content itself. Every value here is either a
    # count, a name, or something the client typed themselves.
    modules = json.loads(req.modules_json) if req.modules_json else []
    journey = (json.loads(req.journey_json) if req.journey_json else {}).get("stages") or []
    org = (json.loads(req.org_json) if req.org_json else {}).get("roles") or []
    procedures = (json.loads(req.procedures_json) if req.procedures_json else {}).get("procedures") or []
    checklists = (json.loads(req.checklists_json) if req.checklists_json else {}).get("checklists") or []
    playbook = json.loads(req.playbook_json) if req.playbook_json else {}
    ops = json.loads(req.ops_numbers_json) if req.ops_numbers_json else []
    qa = json.loads(req.qa_report_json) if req.qa_report_json else {}
    return {
        "id": req.id,
        "pending_review": True,
        "business_name": req.business_name,
        "concept_name": req.concept_name,
        "engagement_type": req.engagement_type,
        "stats": {
            "modules": len(modules),
            "ai_agents": sum(1 for m in modules if (m.get("spec") or {}).get("ai")),
            "journey_stages": len(journey),
            "org_roles": len(org),
            "procedures": len(procedures),
            "checklists": len(checklists),
            "quick_wins": len(playbook.get("quick_wins") or []),
        },
        "module_teasers": [
            {"name": m.get("name"), "purpose": m.get("purpose")} for m in modules
        ],
        "journey_stage_names": [s.get("stage") for s in journey if s.get("stage")],
        # Their own inputs, echoed — proof the engagement was built around
        # their numbers, revealing nothing they didn't type.
        "numbers_echo": [p.get("answer") for p in ops if isinstance(p, dict) and p.get("answer")][:6],
        # The quality bench's checklist — labels and pass marks only.
        "qa_checks": [
            {"label": c.get("label"), "passed": bool(c.get("passed"))}
            for c in qa.get("checks") or []
        ],
    }


def _sanitize_ops_numbers(raw: str | None) -> str | None:
    """The discovery answers arrive as client-built JSON — keep only
    well-formed {question, answer} pairs with real content, bounded in
    count and length. Malformed input stores None, never a 500: the
    numbers are optional garnish on the request, not a precondition."""
    if not raw:
        return None
    try:
        pairs = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(pairs, list):
        return None
    cleaned = []
    for p in pairs[:8]:
        if not isinstance(p, dict):
            continue
        question = str(p.get("question") or "").strip()[:300]
        answer = str(p.get("answer") or "").strip()[:300]
        if question and answer:
            cleaned.append({"question": question, "answer": answer})
    return json.dumps(cleaned) if cleaned else None


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
    revenue_today: str | None = Form(None),
    operating_stage: str | None = Form(None),
    engagement_type: str | None = Form(None),
    ops_numbers: str | None = Form(None),
    document_owner: str | None = Form(None),
    document_approver: str | None = Form(None),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    # Engagements belong to accounts: no sign-in, no run. This is also the
    # spend gate — anonymous traffic can no longer start the pipeline.
    user = auth_client.resolve_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to start your engagement")

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
        revenue_today=revenue_today,
        operating_stage=operating_stage if operating_stage in _ALLOWED_STAGES else None,
        engagement_type=engagement_type if engagement_type in _ALLOWED_ENGAGEMENTS else None,
        ops_numbers_json=_sanitize_ops_numbers(ops_numbers),
        document_owner=(document_owner or "").strip()[:200] or None,
        document_approver=(document_approver or "").strip()[:200] or None,
        owner_email=user["email"],
        public_id=secrets.token_urlsafe(9),
        status="new",
        is_generating=True,
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    threading.Thread(target=orchestrator.run, args=(req.id,), daemon=True).start()

    return {"id": req.id, "public_id": req.public_id, "status": req.status}


@router.get("/mine")
def my_requests(authorization: str | None = Header(None), db: Session = Depends(get_db)):
    """The caller's own engagements, newest first — the only listing a
    client ever sees."""
    user = auth_client.resolve_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to see your engagements")
    rows = (
        db.query(Request)
        .filter(Request.owner_email == user["email"])
        .order_by(Request.id.desc())
        .limit(50)
        .all()
    )
    return {
        "engagements": [
            {
                "id": r.id,
                "public_id": r.public_id,
                "business_name": r.business_name,
                "concept_name": r.concept_name,
                "status": r.status,
                "is_generating": r.is_generating,
                "review_status": r.review_status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }


@router.get("/showcase-gallery")
def showcase_gallery(db: Session = Depends(get_db)):
    """The public example engagements — the marketing gallery. Only runs
    explicitly listed in SHOWCASE_IDS ever appear here."""
    cards = []
    for rid in sorted(_showcase_ids()):
        req = db.get(Request, rid)
        if req is None or req.status != "done":
            continue
        modules = json.loads(req.modules_json) if req.modules_json else []
        journey = (json.loads(req.journey_json) if req.journey_json else {}).get("stages") or []
        procedures = (json.loads(req.procedures_json) if req.procedures_json else {}).get("procedures") or []
        first_image = None
        images = sorted(req.images, key=lambda i: (i.role_id, i.variant)) if req.images else []
        if images:
            cache_v = int(req.created_at.timestamp()) if req.created_at else 0
            hero = compositing.variant_url(images[0].file_path, "hero", settings.UPLOADS_DIR)
            first_image = f"{hero or images[0].file_path}?v={cache_v}"
        cards.append({
            "id": req.id,
            "business_name": req.business_name,
            "concept_name": req.concept_name,
            "industry": req.industry,
            "engagement_type": req.engagement_type,
            "operating_stage": req.operating_stage,
            "stats": {
                "modules": len(modules),
                "ai_agents": sum(1 for m in modules if (m.get("spec") or {}).get("ai")),
                "journey_stages": len(journey),
                "procedures": len(procedures),
            },
            "image_url": first_image,
        })
    return {"showcase": cards}


@router.get("/{request_ref}/progress")
def get_progress(request_ref: str, review_token: str | None = None,
                 authorization: str | None = Header(None), db: Session = Depends(get_db)):
    req = _load_request(request_ref, db)
    _require_view(req, review_token, authorization)
    return {
        "review_status": req.review_status,
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


@router.get("/{request_ref}/preview")
def get_preview(request_ref: str, review_token: str | None = None,
                authorization: str | None = Header(None), db: Session = Depends(get_db)):
    req = _load_request(request_ref, db)
    _require_view(req, review_token, authorization)

    # The review gate: a pending engagement shows the client its teaser —
    # real counts, module names, their own numbers — never the content.
    if _pending_for(req, review_token):
        return _teaser_payload(req)

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
    # Cache-buster on every image URL. The path alone is NOT unique across
    # time: request ids restart when the database does, so /uploads/images/1/
    # can hold a DIFFERENT business's screens than it did last week — and a
    # returning browser will happily show its cached copy of the old ones
    # (seen in production: a fund's result page rendering a gym's cached
    # screens). The request's creation time is distinct per run even across
    # database resets, so it versions the URL.
    cache_v = int(req.created_at.timestamp()) if req.created_at else 0

    def _versioned(path: str | None) -> str | None:
        return f"{path}?v={cache_v}" if path else None

    attraction_images = [
        {
            "role_id": img.role_id,
            "role_label": img.role_label,
            "image_url": _versioned(img.file_path),
            "variant": img.variant,
            # W4 composites when they exist. Null rather than absent, and
            # never a guessed URL: a broken <img> in a lead's preview is
            # worse than no hero shot.
            "hero_url": _versioned(compositing.variant_url(img.file_path, "hero", settings.UPLOADS_DIR)),
            "detail_urls": [
                _versioned(url) for url in (
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
        # The discovery Q&A the business case computed from — echoed back so
        # the result page can show WHICH numbers the figures trace to.
        "operating_stage": req.operating_stage,
        "engagement_type": req.engagement_type,
        "review_status": req.review_status,
        # Full quality-bench report — for the reviewer's eyes; the payload
        # only reaches a pending run's caller with the reviewer token, and
        # released runs carry it harmlessly for the owner's own reading.
        "qa_report": json.loads(req.qa_report_json) if req.qa_report_json else None,
        "ops_numbers": json.loads(req.ops_numbers_json) if req.ops_numbers_json else [],
        # The decomposition the blueprint/technical documents were written
        # FROM — modules (each with its deep spec) and the business case.
        # Exposed structured so the result page can render them natively
        # instead of re-parsing them out of the markdown they produced.
        "modules": json.loads(req.modules_json) if req.modules_json else [],
        "business_case": json.loads(req.business_case_json) if req.business_case_json else None,
        # The execution playbook: ordered real-world steps for the owner,
        # with the AI-covers-it / humans-needed people plan. Null for runs
        # from before the stage existed or when its call failed.
        "playbook": json.loads(req.playbook_json) if req.playbook_json else None,
        # The consultancy layers (extras stage) — each null/empty for older
        # runs or when its one call failed; every layer fails open alone.
        "journey": json.loads(req.journey_json) if req.journey_json else None,
        "organization": json.loads(req.org_json) if req.org_json else None,
        "scoreboard": json.loads(req.scoreboard_json) if req.scoreboard_json else [],
        "risks": json.loads(req.risks_json) if req.risks_json else [],
        "procedures": json.loads(req.procedures_json)["procedures"] if req.procedures_json else [],
        # The operations-manual appendix: {"checklists": [...], "forms": [...]}
        "checklists": json.loads(req.checklists_json) if req.checklists_json else None,
    }


@router.get("/{request_ref}/admin")
def get_admin_detail(request_ref: str, db: Session = Depends(get_db)):
    """Operator view of one request: what it cost, on which models, and how
    each screen scored.

    Deliberately its own endpoint rather than a block on /preview — that
    payload is what a lead sees, and the money must never be one careless
    frontend change away from being rendered on it.

    Cost comes from this service's own ai_usage_events rows, never from the
    OpenRouter key balance: the key is shared, so a balance delta is not
    this request's cost.
    """
    req = _load_request(request_ref, db)
    request_id = req.id

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


@router.post("/{request_ref}/review/approve")
def review_approve(request_ref: str, review_token: str | None = None, db: Session = Depends(get_db)):
    if not _is_reviewer(review_token):
        raise HTTPException(status_code=403, detail="Reviewer token required")
    req = _load_request(request_ref, db)
    request_id = req.id
    req.review_status = "approved"
    req.reviewed_at = datetime.utcnow()
    db.commit()
    from app import mailer

    mailer.notify_owner_released(req.public_id or req.id, req.owner_email, req.business_name or "", req.concept_name)
    return {"id": req.id, "review_status": req.review_status}


@router.post("/{request_ref}/review/docs")
def review_save_docs(
    request_ref: str,
    review_token: str | None = None,
    mvp_blueprint: str | None = Form(None),
    technical_plan: str | None = Form(None),
    db: Session = Depends(get_db),
):
    # The reviewer's red pen: edited documents replace the generated ones,
    # and every export renders from the edited text from then on.
    if not _is_reviewer(review_token):
        raise HTTPException(status_code=403, detail="Reviewer token required")
    req = _load_request(request_ref, db)
    request_id = req.id
    if mvp_blueprint and mvp_blueprint.strip():
        req.mvp_blueprint = mvp_blueprint
    if technical_plan and technical_plan.strip():
        req.technical_plan = technical_plan
    db.commit()
    # an edited document goes back through the integrity layer: its report is
    # bound to the content hash, so the release gate sees the edit either way
    from app.pipeline import integrity

    report = integrity.enforce(db, request_id)
    return {"id": req.id, "saved": True, "integrity_clean": bool(report.get("clean")), "integrity_findings": len(report.get("findings") or [])}


@router.get("/review-queue")
def review_queue(review_token: str | None = None, db: Session = Depends(get_db)):
    """The reviewer's inbox: every finished engagement awaiting approval,
    newest first."""
    if not _is_reviewer(review_token):
        raise HTTPException(status_code=403, detail="Reviewer token required")
    rows = (
        db.query(Request)
        .filter(Request.review_status == "pending")
        .order_by(Request.id.desc())
        .all()
    )
    return {
        "pending": [
            {
                "id": r.id,
                "business_name": r.business_name,
                "concept_name": r.concept_name,
                "engagement_type": r.engagement_type,
                "finished_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]
    }


@router.delete("/{request_ref}")
def delete_request(request_ref: str, review_token: str | None = None, db: Session = Depends(get_db)):
    """Permanent deletion — reviewer only. Removes the row (images cascade),
    the run's uploaded files, and its export artifacts. There is no undo;
    the gate is the REVIEW_TOKEN, never exposed to clients."""
    if not _is_reviewer(review_token):
        raise HTTPException(status_code=403, detail="Reviewer token required")
    req = _load_request(request_ref, db)
    request_id = req.id

    import shutil

    images_dir = os.path.join(settings.UPLOADS_DIR, "images", str(request_id))
    if os.path.isdir(images_dir):
        shutil.rmtree(images_dir, ignore_errors=True)
    exports_dir = os.path.join(settings.UPLOADS_DIR, "exports")
    if os.path.isdir(exports_dir):
        for name in os.listdir(exports_dir):
            if name.startswith(f"{request_id}-") or name == f"{request_id}.pptx":
                try:
                    os.remove(os.path.join(exports_dir, name))
                except OSError:
                    pass

    db.delete(req)
    db.commit()
    return {"deleted": request_id}


@router.get("/{request_ref}/export/zip")
def export_zip_route(request_ref: str, review_token: str | None = None,
                     authorization: str | None = Header(None), db: Session = Depends(get_db)):
    """The whole engagement as one download: all three PDF volumes zipped.
    Volumes that aren't ready are skipped rather than failing the bundle;
    an empty bundle 400s like every other not-ready export."""
    import zipfile

    req = _load_request(request_ref, db)
    request_id = req.id
    _require_view(req, review_token, authorization)
    if _pending_for(req, review_token):
        raise HTTPException(status_code=403, detail="This engagement is with your consultant for review")

    file_stub = "".join(c if c.isalnum() else "-" for c in (req.concept_name or req.business_name or "engagement"))
    built = []
    for kind, name in (
        ("blueprint", "Volume I - The Blueprint.pdf"),
        ("technical", "Volume II - The Technical Plan.pdf"),
        ("operations", "Volume III - The Operations Manual.pdf"),
    ):
        try:
            built.append((export_pdf.build_pdf(req, kind), name))
        except ValueError:
            continue
    if not built:
        raise HTTPException(status_code=400, detail="Documents not ready yet")

    out_dir = os.path.join(settings.UPLOADS_DIR, "exports")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{request_id}-engagement.zip")
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path, name in built:
            bundle.write(path, arcname=f"{file_stub}/{name}")

    return FileResponse(
        out_path,
        media_type="application/zip",
        filename=f"{file_stub}-engagement.zip",
    )


@router.get("/{request_ref}/export/pdf/{kind}")
def export_pdf_route(request_ref: str, kind: str, review_token: str | None = None,
                     authorization: str | None = Header(None), db: Session = Depends(get_db)):
    """The blueprint or technical plan as a branded PDF — the deliverable a
    client prints, forwards, and files. 400 before the document exists,
    same contract as the deck route."""
    if kind not in ("blueprint", "technical", "operations"):
        raise HTTPException(status_code=404, detail="Unknown document")
    req = _load_request(request_ref, db)
    request_id = req.id
    _require_view(req, review_token, authorization)
    if _pending_for(req, review_token):
        raise HTTPException(status_code=403, detail="This engagement is with your consultant for review")
    try:
        out_path = export_pdf.build_pdf(req, kind)
    except ValueError:
        raise HTTPException(status_code=400, detail="Document not ready yet")

    file_stub = "".join(c if c.isalnum() else "-" for c in (req.concept_name or req.business_name or "document"))
    return FileResponse(
        out_path,
        media_type="application/pdf",
        filename=f"{file_stub}-{kind}.pdf",
    )


@router.get("/{request_ref}/export/pptx")
def export_pptx_route(request_ref: str, review_token: str | None = None,
                      authorization: str | None = Header(None), db: Session = Depends(get_db)):
    req = _load_request(request_ref, db)
    request_id = req.id
    _require_view(req, review_token, authorization)
    if _pending_for(req, review_token):
        raise HTTPException(status_code=403, detail="This engagement is with your consultant for review")
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
