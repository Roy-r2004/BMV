import json

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.models import Request
from app.pipeline._shared import ask_until_usable, build_engagement_register, ledger, reply_json
from app.pipeline.failure import StageFailed
from app.templating import render


def _format_site_research(req: Request) -> str:
    """Flattens the research stage's JSON into one line for the prompt —
    same pre-formatted-string pattern plan.py already uses for its JSON
    context fields. "none given" when there is nothing to report, so the
    model reads it the same as any other unanswered intake field."""
    if not req.site_research_json:
        return "none given"
    try:
        data = json.loads(req.site_research_json)
    except (TypeError, ValueError):
        return "none given"
    parts = []
    if data.get("services"):
        parts.append(f"services mentioned: {', '.join(data['services'])}")
    if data.get("hours"):
        parts.append(f"hours: {data['hours']}")
    if data.get("tone"):
        parts.append(f"tone: {data['tone']}")
    if data.get("highlights"):
        parts.append(f"highlights: {', '.join(data['highlights'])}")
    return "; ".join(parts) if parts else "none given"


def _analysis(body: dict) -> dict:
    result = reply_json(body)
    result.setdefault("business_model", "Unknown")
    result.setdefault("pain_points", [])
    return result


def analyze_business(db: Session, request_id: int) -> dict:
    """Stage 1 of the consulting workflow: understand the business."""
    req = db.get(Request, request_id)
    if req is None:
        raise ValueError(f"Request {request_id} not found")

    try:
        prompt = render(
            "analyze.j2",
            business_name=req.business_name or "",
            business_description=req.business_description or "",
            industry=req.industry or "unspecified",
            target_customers=req.target_customers or "unspecified",
            main_problem=req.main_problem or "unspecified",
            desired_outcome=req.desired_outcome or "unspecified",
            what_you_like=req.what_you_like or "none given",
            site_research=_format_site_research(req),
            engagement_register=build_engagement_register(
                req.engagement_type, req.needs_ai, req.main_problem, req.desired_outcome,
            req.business_description,
            ),
        )
        result = ask_until_usable(
            lambda: provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}]),
            _analysis,
            ledger(db, request_id, model=settings.ANALYSIS_MODEL, purpose="analyze"),
        )
    except Exception as exc:
        # No analysis was made, and nothing written in its place: every later
        # stage would build on a finding about a business nobody looked at.
        raise StageFailed("analyzing", exc) from exc

    req.business_analysis_json = json.dumps(result)
    db.commit()
    return result
