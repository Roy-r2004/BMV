"""The proposal as a PDF: the system, screen by screen, printed by Chromium
from the same HTML the website shows."""

import json
import os

from app.config import settings
from app.models import Request
from app.pipeline import action_plan as plan_stage
from app.pipeline import answer as answer_stage
from app.screens import browser, generate, render


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
    ctx = render.proposal_context(
        system, business_name=req.business_name or "your business", journey_stages=stages,
        answer=answer_stage.load(req), roadmap=roadmap if roadmap.get("status") == plan_stage.READY else None,
    )
    html = render.proposal_html(system, ctx)
    out_dir = os.path.join(settings.UPLOADS_DIR, "exports")
    os.makedirs(out_dir, exist_ok=True)
    return browser.render_pdf(html, os.path.join(out_dir, f"{req.id}-system.pdf"))
