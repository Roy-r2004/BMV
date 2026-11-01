"""The proposal as a PDF: the system, screen by screen, printed by Chromium
from the same HTML the website shows.

It is Volume IV to the release law: the HTML is drawn inside a law scope (the
templates' `finalize` checks every string they print, sample regions aside),
the findings are placed on the printed pages and kept for the release gate."""

import json
import os
from datetime import datetime

from app.config import settings
from app.figures import law
from app.models import Request
from app.pipeline import action_plan as plan_stage
from app.pipeline import answer as answer_stage
from app.screens import browser, generate, render

#: The release law's name for the proposal (`law.DOCUMENTS`).
WHERE = "Volume IV"


class NotReady(ValueError):
    """No system has been drawn for this engagement yet."""


def build_system_pdf(req: Request) -> str:
    """Returns the path. Raises NotReady without a system, RuntimeError
    without a browser."""
    system = generate.load(req)
    if not system:
        raise NotReady("no system drawn")
    try:
        journey = json.loads(req.journey_json) if req.journey_json else {}
    except (TypeError, ValueError):
        journey = {}
    stages = [str(s.get("stage")) for s in (journey.get("stages") or []) if isinstance(s, dict) and s.get("stage")]
    roadmap = plan_stage.load(req) or {}
    from app.pipeline.export_pdf import document_known

    started = datetime.utcnow()
    known, hours = document_known(req)
    with law.scope(known, where=WHERE, hours=hours, request_id=req.id) as found:
        ctx = render.proposal_context(
            system, business_name=req.business_name or "your business", journey_stages=stages,
            answer=answer_stage.load(req), roadmap=roadmap if roadmap.get("status") == plan_stage.READY else None,
        )
        html = render.proposal_html(system, ctx)
    out_dir = os.path.join(settings.UPLOADS_DIR, "exports")
    os.makedirs(out_dir, exist_ok=True)
    path = browser.render_pdf(html, os.path.join(out_dir, f"{req.id}-system.pdf"))
    law.save(req.id, WHERE, law.locate_pages(path, found.findings), built_at=started)
    return path
