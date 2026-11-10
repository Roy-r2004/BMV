"""GCC outreach over the API: Roy's list (admin sign-in only) and the private
report a business opens (anyone with its unguessable link)."""
from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request as HttpRequest, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import auth_client
from app.config import settings
from app.database import SessionLocal, get_db
from app.models import OutreachRun, Prospect
from app.outreach import budget, run

router = APIRouter(prefix="/api/outreach", tags=["outreach"])
logger = logging.getLogger("consultant.outreach")

EMAIL = "consulting@buildmyversion.com"
# Link previews (Instagram's and WhatsApp's) load the page without running it, so
# they never reach this API; what does arrive from Instagram's in-app browser is
# the business itself and counts.
_BOT = re.compile(r"facebookexternalhit|facebot|bot\b|crawler|spider|headless", re.I)
_LISTS = {"queued", "sent", "replied", "call_booked", "not_interested", "skip", "removed"}


def _admin(x_admin_password: str | None = Header(default=None),
           authorization: str | None = Header(default=None)) -> None:
    """The main site's admin sign-in, the same one the rest of the admin area uses."""
    if not auth_client.is_admin(x_admin_password, authorization):
        raise HTTPException(status_code=403, detail="Admin sign-in required")


def _report_url(p: Prospect) -> str:
    return f"{settings.PUBLIC_SITE_URL}/for/{p.token}"


def _row(p: Prospect) -> dict:
    url = _report_url(p)
    sources = json.loads(p.sources_json or "[]")
    return {
        "id": p.id, "name": p.name, "city": p.city, "kind": p.kind, "score": p.score,
        "instagram": p.instagram, "instagram_url": f"https://instagram.com/{p.instagram}" if p.instagram else None,
        "website": p.website, "phone": p.phone, "what": p.what,
        "reasons": json.loads(p.reasons_json or "[]"), "sources": [s.get("url") for s in sources if s.get("url")],
        "dm": (p.dm_text or "").replace("{link}", url), "report_url": url, "status": p.status,
        "queued_on": p.queued_on.isoformat() if p.queued_on else None,
        "sent_at": p.sent_at.isoformat() if p.sent_at else None,
        "opens": p.opens or 0, "opened_first_at": p.opened_first_at.isoformat() if p.opened_first_at else None,
    }


@router.get("/list", dependencies=[Depends(_admin)])
def outreach_list(status: str = "queued", db: Session = Depends(get_db)) -> dict:
    """The businesses in one state, newest list first, best first within a day."""
    if status not in _LISTS:
        raise HTTPException(status_code=422, detail="Unknown list")
    rows = (db.query(Prospect).filter(Prospect.status == status)
            .order_by(Prospect.queued_on.desc(), Prospect.score.desc(), Prospect.id).limit(500).all())
    last = db.query(OutreachRun).order_by(OutreachRun.day.desc()).first()
    counts = {s: db.query(Prospect).filter(Prospect.status == s).count() for s in _LISTS}
    return {
        "rows": [_row(p) for p in rows], "counts": counts,
        "spent": round(budget.spent_this_month(db), 2), "cap": settings.OUTREACH_MONTHLY_USD,
        "running": run.running.locked(), "daily": settings.OUTREACH_DAILY,
        "last_run": None if last is None else {
            "day": last.day.isoformat(), "found": last.found, "queued": last.queued,
            "finished_at": last.finished_at.isoformat() if last.finished_at else None,
            "stopped_because": last.stopped_because},
    }


def _fill_in_background() -> None:
    if not run.running.acquire(blocking=False):
        return
    db = SessionLocal()
    day = (datetime.utcnow() + timedelta(hours=4)).date()
    try:
        run.fill(db, day)
        run.purge(db)
    except Exception:
        logger.exception("the outreach run failed")
        db.rollback()
        r = db.query(OutreachRun).filter_by(day=day).one_or_none()
        if r is not None:
            r.stopped_because, r.finished_at = "The run stopped on an error; see the service log", datetime.utcnow()
            db.commit()
    finally:
        db.close()
        run.running.release()


@router.post("/fill", status_code=202, dependencies=[Depends(_admin)])
def outreach_fill() -> dict:
    """Find more businesses for today's list, in the background."""
    if run.running.locked():
        raise HTTPException(status_code=409, detail="A run is already going")
    threading.Thread(target=_fill_in_background, name="outreach-fill", daemon=True).start()
    return {"started": True}


class StatusChange(BaseModel):
    status: Literal["sent", "replied", "call_booked", "not_interested", "skip", "removed", "queued"]


@router.patch("/{prospect_id}", dependencies=[Depends(_admin)])
def outreach_status(prospect_id: int, change: StatusChange, db: Session = Depends(get_db)) -> dict:
    p = db.get(Prospect, prospect_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Not found")
    if change.status == "queued" and p.status not in ("sent", "skip", "not_interested", "replied", "call_booked"):
        raise HTTPException(status_code=422, detail="Only a business already marked can be put back")
    if change.status == "queued" and not p.dm_text:
        raise HTTPException(status_code=422, detail="This business has no message to send")
    p.status = change.status
    if change.status == "sent" and p.sent_at is None:
        p.sent_at = datetime.utcnow()
    db.commit()
    return _row(p)


@router.get("/report/{token}")
def outreach_report(token: str, request: HttpRequest, response: Response, preview: bool = False,
                    db: Session = Depends(get_db)) -> dict:
    """One business's report. Never indexed; a preview bot's visit is not an open."""
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    p = db.query(Prospect).filter(Prospect.token == token).one_or_none()
    if p is None or p.status == "removed" or not p.report_json:
        raise HTTPException(status_code=404, detail="This page is not available")
    if not preview and not _BOT.search(request.headers.get("user-agent") or ""):
        p.opens = (p.opens or 0) + 1
        p.opened_first_at = p.opened_first_at or datetime.utcnow()
        db.commit()
    report = json.loads(p.report_json)
    return {
        "name": p.name, "city": p.city, "today": report.get("today"), "changes": report.get("changes") or [],
        "sources_note": report.get("sources_note"),
        "sources": [s.get("url") for s in json.loads(p.sources_json or "[]") if s.get("url")],
        "email": EMAIL, "book_subject": f"Call about {p.name}", "remove_subject": f"Remove the page for {p.name}",
    }
