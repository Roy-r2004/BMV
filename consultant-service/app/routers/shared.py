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

from app.config import settings
from app.database import get_db
from app.models import Request
from app.pipeline import compositing, screen_story
from app.pipeline import action_plan as plan_stage
from app.pipeline import answer as answer_stage
from app.pipeline import capacity as capacity_stage
from app.routers.requests import PDF_KINDS, build_zip, pdf_file

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
    return {
        "business_name": req.business_name,
        "concept_name": req.concept_name,
        "status": req.status,
        "answer": answer_stage.load(req),
        "capacity": capacity_stage.load(req),
        # the implementation roadmap, and what the owner chose on it — read-only
        "action_plan": plan if (plan or {}).get("status") == plan_stage.READY else None,
        "decisions": plan_stage.load_decisions(req),
        "summary": decision.get("consulting_summary") or req.consulting_analysis,
        "unverified": decision.get("unverified") or [],
        "documents": {
            "blueprint": bool(req.mvp_blueprint),
            "technical": bool(req.technical_plan),
            "operations": bool(req.procedures_json or req.org_json or req.checklists_json),
        },
        "screens": screens,
    }


@router.get("/{token}/export/{kind}")
def shared_export(token: str, kind: str, db: Session = Depends(get_db)):
    req = _load(token, db)
    if kind == "zip":
        out_path, stub = build_zip(req)
        return FileResponse(out_path, media_type="application/zip", filename=f"{stub}-engagement.zip")
    if kind not in PDF_KINDS:
        raise HTTPException(status_code=404, detail="Unknown document")
    out_path, filename = pdf_file(req, kind)
    return FileResponse(out_path, media_type="application/pdf", filename=filename)
