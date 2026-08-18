import json

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.models import Request
from app.pipeline._shared import build_engagement_register, extract_json_from_text, log_usage
from app.templating import render


def _fallback(req: Request) -> dict:
    return {
        "business_model": "Unknown",
        "target_customer_profile": req.target_customers or "General local customers",
        "pain_points": ["Missed inquiries outside business hours", "Manual scheduling / order-taking"],
        "growth_opportunity": "An AI front-desk employee that responds instantly and never misses an inquiry.",
    }


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
            ),
        )
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}])
        content = body["choices"][0]["message"]["content"]
        result = extract_json_from_text(content)
        result.setdefault("business_model", "Unknown")
        result.setdefault("pain_points", [])
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="analyze",
            usage=body.get("usage"), success=True,
        )
    except Exception as exc:
        result = _fallback(req)
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="analyze",
            success=False, error=str(exc)[:500],
        )

    req.business_analysis_json = json.dumps(result)
    db.commit()
    return result
