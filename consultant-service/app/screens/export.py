"""The proposal as a PDF: the system, screen by screen, printed by Chromium
from the same HTML the website shows.

It is Volume IV to the release law: the HTML is drawn inside a law scope (the
templates' `finalize` checks every string they print, sample regions aside),
the findings are placed on the printed pages and kept for the release gate.
`check_proposal` is the law-only pass: the same HTML, no browser, each finding
placed on the proposal page (one `<section class="page">` is one printed page)
that holds it."""

import html as html_lib
import json
import os
import re
from datetime import datetime

from app.config import settings
from app.figures import law
from app.models import Request
from app.pipeline import action_plan as plan_stage
from app.pipeline import answer as answer_stage
from app.screens import browser, generate, render

#: The release law's name for the proposal (`law.DOCUMENTS`).
WHERE = "Volume IV"

_PAGE = '<section class="page'
_DRAWN_ONLY = re.compile(r"<style.*?</style>|<svg.*?</svg>|<script.*?</script>", re.S)
_TAG = re.compile(r"<[^>]+>")


class NotReady(ValueError):
    """No system has been drawn for this engagement yet."""


def _proposal(req: Request, system: dict) -> tuple[str, list]:
    """The proposal's HTML, drawn inside the law, and what the law found."""
    try:
        journey = json.loads(req.journey_json) if req.journey_json else {}
    except (TypeError, ValueError):
        journey = {}
    stages = [str(s.get("stage")) for s in (journey.get("stages") or []) if isinstance(s, dict) and s.get("stage")]
    roadmap = plan_stage.load(req) or {}
    from app.pipeline.export_pdf import document_known, document_phrases

    known, hours = document_known(req)
    with law.scope(known, where=WHERE, hours=hours, request_id=req.id, phrases=document_phrases(req)) as found:
        ctx = render.proposal_context(
            system, business_name=req.business_name or "your business", journey_stages=stages,
            answer=answer_stage.load(req), roadmap=roadmap if roadmap.get("status") == plan_stage.READY else None,
        )
        html = _answer_first(req) + render.proposal_html(system, ctx)
    return html, found.findings


def _answer_first(req: Request) -> str:
    """The answer, as the first printed page, when the run has one."""
    from app.storyline.build import build as build_story

    story = build_story(req)
    if story is None or not story.answer.question:
        return ""
    rests = story.answer.rests_on
    line = (f"What this rests on: {rests.theirs} figures are yours, {rests.derived} worked out, "
            f"{rests.reference} references with sources, {rests.checks_passed} checks passed.")
    question = html_lib.escape(story.answer.question)
    return f'<section class="page"><h1>{question}</h1><p>{html_lib.escape(line)}</p></section>'


def page_texts(html: str) -> list[str]:
    """The text of each proposal page, in order, as it prints."""
    pages = []
    for section in html.split(_PAGE)[1:]:
        body = section.split(">", 1)[1] if ">" in section else section
        pages.append(html_lib.unescape(_TAG.sub(" ", _DRAWN_ONLY.sub(" ", body))))
    return pages


def build_system_pdf(req: Request) -> str:
    """Returns the path. Raises NotReady without a system, RuntimeError
    without a browser."""
    system = generate.load(req)
    if not system:
        raise NotReady("no system drawn")
    started = datetime.utcnow()
    html, findings = _proposal(req, system)
    out_dir = os.path.join(settings.UPLOADS_DIR, "exports")
    os.makedirs(out_dir, exist_ok=True)
    path = browser.render_pdf(html, os.path.join(out_dir, f"{req.id}-system.pdf"))
    law.save(req.id, WHERE, law.locate_pages(path, findings), built_at=started)
    return path


def proposal_ready(req: Request) -> bool:
    """Whether a system has been drawn for the request (the proposal's source)."""
    return bool(generate.load(req))


def check_proposal(req: Request) -> None:
    """The proposal's law-only pass (`law.ensure_records`). A package with no
    system drawn yet is recorded as having no proposal."""
    started = datetime.utcnow()
    system = generate.load(req)
    if not system:
        law.save(req.id, WHERE, [], built_at=started, absent=True)
        return
    html, findings = _proposal(req, system)
    law.save(req.id, WHERE, law.locate_in_texts(page_texts(html), findings), built_at=started)
