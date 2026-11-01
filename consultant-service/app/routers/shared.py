"""The package as a partner sees it: read-only, through a link the owner made.

"Share with a partner" is how a consultancy's work actually travels — to the
co-founder, the accountant, the person who signs off the spend. Engagements
are private to one account, so this is a second, narrower door: a token the
owner created and can revoke, opening the finished package and nothing else.
It cannot answer the decision, send it back, answer the roadmap's decisions or
make another link; those stay on the owner's routes, which demand the owner's session.
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import produced
from app.config import settings
from app.database import get_db
from app.figures import payload as figure_payload
from app.models import Request
from app.pipeline import compositing, screen_story
from app.pipeline import action_plan as plan_stage
from app.pipeline import answer as answer_stage
from app.pipeline import capacity as capacity_stage
from app.routers.requests import build_zip

router = APIRouter(prefix="/api/shared", tags=["shared"])


def _load(token: str, db: Session) -> Request:
    # Tokens are 24 url-safe characters; anything else is not one we issued,
    # and is refused before it reaches the database.
    if not token or len(token) > 40 or not all(c.isalnum() or c in "-_" for c in token):
        raise HTTPException(status_code=404, detail="This link doesn't open anything")
    req = db.query(Request).filter(Request.share_token == token).first()
    if req is None:
        raise HTTPException(status_code=404, detail="This link doesn't open anything — it may have been turned off")
    # A package still held for the consultant's signature is not released to
    # its owner either; a partner does not get to see it first.
    if settings.REVIEW_MODE == "gate" and req.review_status == "pending":
        raise HTTPException(status_code=403, detail="This package is still being reviewed")
    return req


@router.get("/{token}")
def shared_package(token: str, db: Session = Depends(get_db)):
    req = _load(token, db)
    decision = json.loads(req.consulting_recommendations_json) if req.consulting_recommendations_json else {}
    cache_v = int(req.created_at.timestamp()) if req.created_at else 0
    screens = [
        {
            "role_label": img.role_label,
            "image_url": f"{img.file_path}?v={cache_v}",
            "hero_url": (lambda u: f"{u}?v={cache_v}" if u else None)(
                compositing.variant_url(img.file_path, "hero", settings.UPLOADS_DIR)),
            "story": screen_story.from_spec_json(img.spec_json, img.role_label or ""),
        }
        for img in sorted(req.images, key=lambda i: (i.role_id, i.variant))
    ]
    plan = plan_stage.load(req)
    ready = plan if isinstance(plan, dict) and plan.get("status") == plan_stage.READY else None
    capacity = capacity_stage.load(req)
    # the answer also in pieces, and the figures its numbers name (whose they are, and where from).
    # Anyone with the link reads this, so none of the owner's own words (questions, quotes, files) is in it.
    answer, figures = figure_payload.for_web(req, answer=answer_stage.load(req), plan=ready, capacity=capacity,
                                             public=True)
    return {
        "business_name": req.business_name,
        "concept_name": req.concept_name,
        "status": req.status,
        "answer": answer,
        "capacity": figure_payload.capacity_for_web(capacity, public=True),
        # the implementation roadmap, and what the owner chose on it — read-only
        "action_plan": ready,
        "figures": figures,
        "decisions": plan_stage.load_decisions(req),
        "summary": decision.get("consulting_summary") or req.consulting_analysis,
        "unverified": decision.get("unverified") or [],
        "documents": _document_flags(req),
        "files": produced.package_files(req),
        "screens": screens,
    }


@router.get("/{token}/system")
def shared_system(token: str, db: Session = Depends(get_db)):
    """The system, live, for a partner with the link."""
    from app.screens import generate as screens_stage

    return screens_stage.payload(_load(token, db))


def _document_flags(req: Request) -> dict:
    """The booleans the share page already reads, taken from the one list."""
    by_key = {item["key"]: item["available"] for item in produced.package_files(req)}
    return {"blueprint": by_key["blueprint"], "technical": by_key["technical"], "operations": by_key["operations"]}


@router.get("/{token}/export/{kind}")
def shared_export(token: str, kind: str, db: Session = Depends(get_db)):
    from app.storyline.files import UnknownFile, files_for, render_file
    from app.storyline.roadmap import NotReady

    req = _load(token, db)
    if kind == "zip":
        out_path, stub = build_zip(req)
        headers = {"X-Skipped": ", ".join(build_zip.skipped)} if build_zip.skipped else {}
        return FileResponse(out_path, media_type="application/zip", filename=f"{stub}-engagement.zip", headers=headers)
    from app.figures.law import UnstampedSample

    try:
        out_path = render_file(req, kind)
    except UnknownFile:
        raise HTTPException(status_code=404, detail="That file is not one of this package.")
    except (NotReady, ValueError):
        raise HTTPException(status_code=400, detail="That file is not ready yet.")
    except (UnstampedSample, RuntimeError):
        raise HTTPException(status_code=503, detail="That file cannot be printed on this server right now.")
    item = next(f for f in files_for(req) if f.key == kind)
    media = {
        "pdf": "application/pdf",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }[item.kind]
    return FileResponse(out_path, media_type=media, filename=item.filename)
