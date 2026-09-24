import hmac
import json
import secrets
import logging
import os
import threading
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import auth_client, mailer
from app.config import settings
from app.database import get_db
from app.models import AiUsageEvent, Request
from app.pipeline import compositing, decide, evidence, export_pdf, export_pilot, export_pptx, orchestrator, screen_story, what_this_is
from app.pipeline import action_plan as plan_stage
from app.pipeline import answer as answer_stage
from app.pipeline import capacity as capacity_stage
from app.pipeline._shared import CORRECTIONS_MARKER, briefing_corrections

logger = logging.getLogger("consultant.requests")

router = APIRouter(prefix="/api/requests", tags=["requests"])


_ALLOWED_STAGES = {"operating", "opening"}
_ALLOWED_ENGAGEMENTS = {"full", "capability"}
MAX_LAUNCH_FILES = 3


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
    numbers are optional garnish on the request, not a precondition.

    The count bound tracks what the interview can actually collect. It was a
    flat 8, from when one fixed round asked at most 6; an adaptive interview
    running its full three rounds gathers twelve, and the old cap would have
    thrown away the last four answers the client typed — silently, and after
    asking for them.
    """
    if not raw:
        return None
    try:
        pairs = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(pairs, list):
        return None
    limit = max(8, settings.INTERVIEW_MAX_ROUNDS * settings.INTERVIEW_MAX_PER_ROUND)
    cleaned = []
    for p in pairs[:limit]:
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
    # Their own files, sent from the conversation ("drop your booking export
    # in"). Read by the diagnosis half before it forms an explanation.
    files: list[UploadFile] | None = File(None),
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
        phase_started_at=datetime.utcnow(),
        status="new",
        is_generating=True,
    )
    # Checked before the row exists, so a file we refuse costs them nothing
    # and leaves no half-made engagement behind.
    uploads = []
    for f in (files or [])[:MAX_LAUNCH_FILES]:
        if not f or not f.filename:
            continue
        name = os.path.basename(f.filename)[:120]
        if not name.lower().endswith(evidence.SUPPORTED):
            raise HTTPException(status_code=422, detail=f"We can't read {name} — send a spreadsheet, CSV or PDF.")
        data = f.file.read(evidence.MAX_FILE_BYTES + 1)
        if len(data) > evidence.MAX_FILE_BYTES:
            raise HTTPException(status_code=422, detail=f"{name} is larger than 8 MB.")
        uploads.append((name, data))

    db.add(req)
    db.commit()
    db.refresh(req)

    for name, data in uploads:
        evidence.stash(req.id, name, data)

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
        # The gate is not visible in `is_generating` alone: an engagement
        # waiting on the client's decision is not generating and not finished,
        # and a poller that reads only the boolean shows them a finished run
        # with no deliverables behind it.
        "status": req.status,
        # The consultant's reasoning as it happens. The wait used to be an
        # animation and a rotating caption; this is the real thing, and it is
        # the most persuasive thing we have — explanations forming, being
        # tested against their own numbers, and being killed.
        "thinking": _thinking(req),
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
        "elapsed_s": max(0, int((datetime.utcnow() - (req.phase_started_at or req.created_at)).total_seconds()))
        if (req.phase_started_at or req.created_at) else 0,
        # The building screen says "you can close this page, we'll email you".
        # It may only say so when a mail can actually be sent.
        "notify": {"email": req.owner_email or req.email, "enabled": mailer.enabled()},
    }


def _require_owner(req: Request, authorization: str | None) -> None:
    """The decision is the client's alone to make.

    Deliberately stricter than `_require_view`: a reviewer token and the
    showcase allowance both open a run for READING, and neither is a mandate
    to spend the owner's remaining pipeline on their behalf.
    """
    user = auth_client.resolve_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to answer your engagement")
    if not req.owner_email or user["email"].lower() != req.owner_email.lower():
        raise HTTPException(status_code=403, detail="This engagement belongs to another account")


def _thinking(req: Request) -> list[dict]:
    """The narrated trail, or nothing. Never raises: a decoration that can
    break the poller would take the progress bar down with it."""
    try:
        trail = json.loads(req.thinking_json) if req.thinking_json else []
        return [t for t in trail if isinstance(t, dict) and t.get("text")][:40]
    except (TypeError, ValueError):
        return []


def _diagnosis_payload(req: Request) -> dict | None:
    """The reasoning, shaped for reading rather than for the next prompt.

    Returns None when no diagnosis was made. The client is then shown the
    decision alone — which is what they used to get — rather than an empty
    reasoning panel implying the thinking happened and found nothing.
    """
    if not req.diagnosis_json:
        return None
    try:
        d = json.loads(req.diagnosis_json)
    except (TypeError, ValueError):
        return None
    hypotheses = d.get("hypotheses") or []
    leading = next((h for h in hypotheses if h.get("id") == d.get("leading")), None)
    if not leading:
        return None
    by_id = {c.get("id"): c for c in d.get("evidence") or []}

    def cited(ids):
        out = []
        for cid in ids or []:
            claim = by_id.get(cid)
            if claim:
                out.append({"id": cid, "text": claim.get("text"), "source": claim.get("source")})
        return out

    return {
        "leading": {
            "statement": leading.get("statement"),
            "area": leading.get("area"),
            "software_can_fix": leading.get("software_can_fix"),
            "verdict": (leading.get("test") or {}).get("verdict"),
            "because": (leading.get("test") or {}).get("because"),
            "cites": cited((leading.get("test") or {}).get("cites")),
            "would_need": (leading.get("test") or {}).get("would_need"),
            # The owner's own stated problem, handed back. Shown so they can
            # see when we agreed with them and when we did not.
            "from_owner": leading.get("from_owner"),
        },
        "considered": [
            {"statement": h.get("statement"), "area": h.get("area"),
             "verdict": (h.get("test") or {}).get("verdict"),
             "because": (h.get("test") or {}).get("because")}
            for h in hypotheses if h.get("id") != d.get("leading")
        ],
        "status": d.get("status"),
        "weaknesses": d.get("weaknesses") or [],
        "challenges": [
            {"angle": c.get("angle"), "kills": c.get("kills"), "because": c.get("because")}
            for c in d.get("challenges") or [] if c.get("ran", True)
        ],
    }


def _decision_payload(req: Request) -> dict:
    analysis = json.loads(req.business_analysis_json) if req.business_analysis_json else {}
    decision = json.loads(req.consulting_recommendations_json) if req.consulting_recommendations_json else {}
    return {
        "diagnosis": _diagnosis_payload(req),
        "id": req.id,
        "public_id": req.public_id,
        "status": req.status,
        "business_name": req.business_name,
        "understanding": {
            "business_model": analysis.get("business_model"),
            "target_customer_profile": analysis.get("target_customer_profile"),
            "pain_points": analysis.get("pain_points") or [],
            "growth_opportunity": analysis.get("growth_opportunity"),
        },
        "decision": {
            "summary": decision.get("consulting_summary") or req.consulting_analysis,
            "recommended_ai_employees": decision.get("recommended_ai_employees") or [],
            "recommended_features": decision.get("recommended_features") or [],
            # What actually fixes the diagnosed cause. Absent on an engagement
            # decided before this field existed, and on a decision the model
            # returned unreadably — `builds` is the one the UI acts on.
            "intervention_kind": decision.get("intervention_kind"),
            "central_problem": decision.get("central_problem"),
            "why_not_the_others": decision.get("why_not_the_others"),
            "confidence": decision.get("confidence"),
            "unverified": decision.get("unverified") or [],
        },
        # Whether a build would move the cause. False means we are telling
        # them not to spend — they can still overrule it.
        "builds": decide.builds(decision),
        # What the client has already sent back, so the gate can show that
        # their last objection was actually read rather than silently dropped.
        "revisions": briefing_corrections(req.business_description),
        # The answer screen: their week drawn from their own answers, the
        # finding in two lines, and the value of the move with its working.
        # Each is null when it could not be made — never a placeholder.
        "capacity": capacity_stage.load(req),
        "answer": answer_stage.load(req),
        "action_plan": plan_stage.load(req),
        "operating_stage": req.operating_stage,
    }


@router.get("/{request_ref}/decision")
def get_decision(request_ref: str, review_token: str | None = None,
                 authorization: str | None = Header(None), db: Session = Depends(get_db)):
    """What we concluded, before anything is built on it."""
    req = _load_request(request_ref, db)
    _require_view(req, review_token, authorization)
    return _decision_payload(req)


@router.post("/{request_ref}/decision/approve")
def approve_decision(request_ref: str,
                     budget_range: str | None = Form(None),
                     timeline: str | None = Form(None),
                     authorization: str | None = Header(None),
                     db: Session = Depends(get_db)):
    """Start the build half.

    Budget and timeline arrive HERE rather than in the intake. They reach
    exactly one prompt — `playbook.j2`, at stage ten — so asking for them on
    the way in bought nothing and cost a screen of commercial questions
    before we had shown the visitor anything. Asked at the moment someone
    wants a build, they are a question worth answering.

    The status flip is a CONDITIONAL update, and only the caller whose update
    matched a row starts a thread. A double-click otherwise races two builds
    over one engagement — the same shape as the charter-confirm bug, where
    checking then writing in two steps let both callers pass the check.
    """
    req = _load_request(request_ref, db)
    _require_owner(req, authorization)

    # ADVISED is a state the client can leave. It records "we told you a build
    # would not fix this and you read it", nothing more — and the page told
    # them to "come back and press Build whenever the picture changes" while
    # this refused every press with a 409 and the page had no button to press.
    # Someone who wants the package must be able to have it, before or after
    # they have read our advice.
    startable = (orchestrator.AWAITING_APPROVAL, orchestrator.ADVISED)
    if req.status not in (*startable, orchestrator.BUILDING):
        raise HTTPException(status_code=409, detail="This engagement has no decision waiting")

    fields = {"status": orchestrator.BUILDING, "is_generating": True, "phase_started_at": datetime.utcnow()}
    if (budget_range or "").strip():
        fields["budget_range"] = budget_range.strip()[:100]
    if (timeline or "").strip():
        fields["timeline"] = timeline.strip()[:100]

    claimed = db.query(Request).filter(
        Request.id == req.id,
        Request.status.in_(startable),
    ).update(fields, synchronize_session=False)
    db.commit()

    if claimed:
        threading.Thread(target=orchestrator.run_build, args=(req.id,), daemon=True).start()

    db.refresh(req)
    return {"id": req.id, "status": req.status, "started": bool(claimed)}


@router.get("/{request_ref}/evidence")
def list_evidence(request_ref: str, review_token: str | None = None,
                  authorization: str | None = Header(None), db: Session = Depends(get_db)):
    req = _load_request(request_ref, db)
    _require_view(req, review_token, authorization)
    return {"figures": evidence.load(req)}


@router.post("/{request_ref}/evidence")
async def add_evidence(request_ref: str, file: UploadFile = File(...),
                       authorization: str | None = Header(None), db: Session = Depends(get_db)):
    """Read figures out of a file they sent, then diagnose again with them.

    The upload is not a passive attachment. The diagnosis it replaces said
    exactly what it could not verify; adding the file that settles it and NOT
    re-running would leave that sentence standing over evidence that answers
    it. So this re-opens the engagement the same way `revise` does.
    """
    req = _load_request(request_ref, db)
    _require_owner(req, authorization)
    if req.is_generating:
        raise HTTPException(status_code=409, detail="This engagement is still running")

    data = await file.read()
    name = os.path.basename(file.filename or "upload")[:120]
    try:
        tables = evidence.read_tables(data, name)
    except evidence.UnreadableFile as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not tables:
        raise HTTPException(status_code=422,
                            detail="We could not find any rows of data in that file.")

    existing = evidence.load(req)
    found, rejected = evidence.extract(db, req.id, tables, name, start_index=len(existing))
    if not found:
        raise HTTPException(
            status_code=422,
            detail=("We read that file but could not find figures worth citing in it."
                    if not rejected else
                    "We could not verify any of the figures we found against their cells."))

    evidence.save(db, req, existing + found)

    # Diagnose again on the wider evidence, through the same door the client's
    # own pushback uses — one path that re-opens an engagement, not two.
    started = False
    if req.status in (orchestrator.AWAITING_APPROVAL, orchestrator.ADVISED, "failed"):
        claimed = db.query(Request).filter(
            Request.id == req.id, Request.status == req.status,
        ).update({"status": "new", "is_generating": True, "is_failed": False,
                  "phase_started_at": datetime.utcnow()},
                 synchronize_session=False)
        db.commit()
        if claimed:
            threading.Thread(target=orchestrator.run, args=(req.id,), daemon=True).start()
            started = True

    return {"added": len(found), "rejected": rejected,
            "figures": found, "rediagnosing": started}


@router.delete("/{request_ref}/evidence/{claim_id}")
def remove_evidence(request_ref: str, claim_id: str,
                    authorization: str | None = Header(None), db: Session = Depends(get_db)):
    """Drop a figure we read wrong.

    Their file, their call. The ids of the remaining figures are NOT
    renumbered: a diagnosis already written cites them, and shifting CE-03 to
    mean something new would silently re-point every citation that survives.
    """
    req = _load_request(request_ref, db)
    _require_owner(req, authorization)
    remaining = [c for c in evidence.load(req) if c.get("id") != claim_id]
    evidence.save(db, req, remaining)
    return {"figures": remaining}


@router.post("/{request_ref}/decision/accept")
def accept_advice(request_ref: str, authorization: str | None = Header(None),
                  db: Session = Depends(get_db)):
    """Take the answer and stop. The brief is the deliverable.

    Reached when we told them a build will not fix the diagnosed cause and
    they agreed. Terminal, and NOT a failure — `is_failed` stays false, so
    nothing in the client's listing reads this as an engagement that broke.
    """
    req = _load_request(request_ref, db)
    _require_owner(req, authorization)

    if req.status not in (orchestrator.AWAITING_APPROVAL, orchestrator.ADVISED):
        raise HTTPException(status_code=409, detail="This engagement has no decision waiting")

    db.query(Request).filter(
        Request.id == req.id,
        Request.status == orchestrator.AWAITING_APPROVAL,
    ).update({"status": orchestrator.ADVISED, "is_generating": False, "is_failed": False},
             synchronize_session=False)
    db.commit()
    db.refresh(req)

    # Taking the answer used to end the engagement with a paragraph. It now
    # starts what they do about it: the plan is written in the background and
    # the page polls for it. Started once — a second press while it is being
    # written, or after it is written, starts nothing.
    started = _start_plan(db, req)
    return {"id": req.id, "status": req.status, "plan_started": started}


def _start_plan(db: Session, req: Request) -> bool:
    current = plan_stage.load(req) or {}
    if current.get("status") in (plan_stage.WRITING, plan_stage.READY):
        return False
    marker = json.dumps({"status": plan_stage.WRITING})
    claimed = db.query(Request).filter(
        Request.id == req.id,
        (Request.action_plan_json.is_(None)) | (Request.action_plan_json == req.action_plan_json),
    ).update({"action_plan_json": marker}, synchronize_session=False)
    db.commit()
    if not claimed:
        return False
    threading.Thread(target=plan_stage.write_in_background, args=(req.id,), daemon=True).start()
    return True


@router.post("/{request_ref}/plan/retry")
def retry_plan(request_ref: str, authorization: str | None = Header(None),
               db: Session = Depends(get_db)):
    """Write the plan after it failed — or for the first time, on a package
    built before plans existed. Not a way to reroll a good one."""
    req = _load_request(request_ref, db)
    _require_owner(req, authorization)
    if (plan_stage.load(req) or {}).get("status") not in (None, plan_stage.FAILED):
        raise HTTPException(status_code=409, detail="This plan is already written or being written")
    if not req.consulting_recommendations_json:
        raise HTTPException(status_code=409, detail="There is no answer to write a plan from yet")
    return {"plan_started": _start_plan(db, req)}


@router.get("/{request_ref}/plan")
def get_plan(request_ref: str, review_token: str | None = None,
             authorization: str | None = Header(None), db: Session = Depends(get_db)):
    req = _load_request(request_ref, db)
    _require_view(req, review_token, authorization)
    return {"plan": plan_stage.load(req), "log": plan_stage.load_log(req),
            "capacity": capacity_stage.load(req)}


@router.post("/{request_ref}/plan/log")
def log_pilot_week(request_ref: str, week: int = Form(...), values: str = Form("{}"),
                   note: str | None = Form(None), authorization: str | None = Header(None),
                   db: Session = Depends(get_db)):
    """One week of the pilot, entered by the owner against the plan's own
    measures. Upserts: correcting last week's number is the same call."""
    req = _load_request(request_ref, db)
    _require_owner(req, authorization)
    plan = plan_stage.load(req) or {}
    if plan.get("status") != plan_stage.READY:
        raise HTTPException(status_code=409, detail="There is no plan to track yet")
    weeks = int(plan.get("weeks") or 6)
    if not 1 <= week <= max(weeks, 12):
        raise HTTPException(status_code=422, detail=f"Week must be between 1 and {max(weeks, 12)}")
    try:
        parsed = json.loads(values or "{}")
    except ValueError:
        raise HTTPException(status_code=422, detail="Values must be a JSON object")
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail="Values must be a JSON object")
    log = plan_stage.record(plan, plan_stage.load_log(req), week, parsed, note or "")
    req.pilot_log_json = json.dumps(log)
    db.commit()
    return {"log": log}


@router.post("/{request_ref}/share")
def share_engagement(request_ref: str, authorization: str | None = Header(None),
                     db: Session = Depends(get_db)):
    """A read-only link for a partner, accountant or co-founder. The same link
    every time until it is revoked, so sending it twice sends one address."""
    req = _load_request(request_ref, db)
    _require_owner(req, authorization)
    if not req.share_token:
        req.share_token = secrets.token_urlsafe(18)
        db.commit()
    return {"token": req.share_token, "path": f"/shared/{req.share_token}"}


@router.delete("/{request_ref}/share")
def unshare_engagement(request_ref: str, authorization: str | None = Header(None),
                       db: Session = Depends(get_db)):
    req = _load_request(request_ref, db)
    _require_owner(req, authorization)
    req.share_token = None
    db.commit()
    return {"token": None}


@router.post("/{request_ref}/decision/revise")
def revise_decision(request_ref: str, note: str = Form(...),
                    authorization: str | None = Header(None), db: Session = Depends(get_db)):
    """The client disagrees. Diagnose again, carrying what they said.

    Their objection is appended under CORRECTIONS_MARKER, which
    `build_engagement_register` already injects into every content prompt —
    so the second diagnosis reads the correction the same way it reads the
    briefing chat's, and no new plumbing carries it.
    """
    req = _load_request(request_ref, db)
    _require_owner(req, authorization)

    text = (note or "").strip()
    if len(text) < 10:
        raise HTTPException(status_code=422, detail="Tell us what we got wrong, in a sentence or two")

    if req.status not in (orchestrator.AWAITING_APPROVAL, orchestrator.ADVISED, "failed"):
        raise HTTPException(status_code=409, detail="This engagement has no decision waiting")

    claimed = db.query(Request).filter(
        Request.id == req.id,
        Request.status == req.status,
    ).update({"status": "new", "is_generating": True, "is_failed": False,
              "phase_started_at": datetime.utcnow()},
             synchronize_session=False)
    if not claimed:
        db.commit()
        db.refresh(req)
        return {"id": req.id, "status": req.status, "started": False}

    existing = req.business_description or ""
    marker = "" if CORRECTIONS_MARKER in existing else f"\n\n{CORRECTIONS_MARKER}"
    req.business_description = f"{existing}{marker}\n- {text[:1000]}"
    db.commit()

    threading.Thread(target=orchestrator.run, args=(req.id,), daemon=True).start()
    return {"id": req.id, "status": "new", "started": True}


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
        # The package page opens with these: the answer it was built around,
        # their week, what to do on Monday, and the tracker's entries so far.
        "answer": answer_stage.load(req),
        "capacity": capacity_stage.load(req),
        "action_plan": plan_stage.load(req),
        "pilot_log": plan_stage.load_log(req),
        "intervention_kind": recommendations.get("intervention_kind"),
        # What the documents still assume. Shown as its own box on the
        # package page, not left for them to find in the fine print.
        "unverified": recommendations.get("unverified") or [],
        "shared": bool(req.share_token),
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
    req = _load_request(request_ref, db)
    _require_view(req, review_token, authorization)
    if _pending_for(req, review_token):
        raise HTTPException(status_code=403, detail="This engagement is with your consultant for review")

    out_path, file_stub = build_zip(req)
    return FileResponse(
        out_path,
        media_type="application/zip",
        filename=f"{file_stub}-engagement.zip",
    )


def build_zip(req: Request) -> tuple[str, str]:
    """Every document this engagement has, zipped. The plan leads, because it
    is the one they use first; volumes that aren't ready are skipped."""
    import zipfile

    file_stub = "".join(c if c.isalnum() else "-" for c in (req.concept_name or req.business_name or "engagement"))
    built = []
    plan = plan_stage.load(req) or {}
    if plan.get("status") == plan_stage.READY:
        try:
            built.append((export_pilot.build_pilot_pdf(req), f"00 - {plan.get('title') or 'Your plan'}.pdf"))
        except ValueError:
            pass
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
    out_path = os.path.join(out_dir, f"{req.id}-engagement.zip")
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path, name in built:
            bundle.write(path, arcname=f"{file_stub}/{name}")
    return out_path, file_stub


@router.get("/{request_ref}/export/pdf/{kind}")
def export_pdf_route(request_ref: str, kind: str, review_token: str | None = None,
                     authorization: str | None = Header(None), db: Session = Depends(get_db)):
    """The blueprint or technical plan as a branded PDF — the deliverable a
    client prints, forwards, and files. 400 before the document exists,
    same contract as the deck route."""
    if kind not in PDF_KINDS:
        raise HTTPException(status_code=404, detail="Unknown document")
    req = _load_request(request_ref, db)
    _require_view(req, review_token, authorization)
    # The plan is theirs the moment it is written — it is not part of the
    # reviewed package, and holding their Monday steps behind a review queue
    # would hold back the one document with nothing to review but their own
    # figures.
    if kind != "pilot" and _pending_for(req, review_token):
        raise HTTPException(status_code=403, detail="This engagement is with your consultant for review")
    out_path, filename = pdf_file(req, kind)
    return FileResponse(out_path, media_type="application/pdf", filename=filename)


PDF_KINDS = ("blueprint", "technical", "operations", "pilot")


def pdf_file(req: Request, kind: str) -> tuple[str, str]:
    try:
        out_path = export_pilot.build_pilot_pdf(req) if kind == "pilot" else export_pdf.build_pdf(req, kind)
    except ValueError:
        raise HTTPException(status_code=400, detail="Document not ready yet")
    file_stub = "".join(c if c.isalnum() else "-" for c in (req.concept_name or req.business_name or "document"))
    return out_path, f"{file_stub}-{kind}.pdf"


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
