import json

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.models import Request
from app.pipeline._shared import build_engagement_register, extract_json_from_text, log_usage
from app.templating import render


def _fallback(req: Request) -> dict:
    return {
        "consulting_summary": (
            f"{req.business_name} would benefit from an AI front-desk employee that handles routine "
            "customer interactions, plus an activity dashboard showing what it handled each day."
        ),
        "recommended_ai_employees": [
            {"title": "Front-Desk AI", "why": "Answers and books instantly, day or night."},
            {"title": "AI Analyst", "why": "Shows the owner what happened and what it's worth."},
        ],
        "recommended_features": ["Instant replies", "Online booking", "Activity dashboard"],
    }


def consult(db: Session, request_id: int, analysis: dict) -> dict:
    """Stage 2: given the analysis, recommend what should be included."""
    req = db.get(Request, request_id)
    if req is None:
        raise ValueError(f"Request {request_id} not found")

    try:
        prompt = render(
            "consult.j2",
            business_name=req.business_name or "",
            business_description=req.business_description or "",
            business_model=analysis.get("business_model", "Unknown"),
            target_customer_profile=analysis.get("target_customer_profile", ""),
            pain_points=json.dumps(analysis.get("pain_points", [])),
            growth_opportunity=analysis.get("growth_opportunity", ""),
            engagement_register=build_engagement_register(
                req.engagement_type, req.needs_ai, req.main_problem, req.desired_outcome,
            ),
        )
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}])
        content = body["choices"][0]["message"]["content"]
        result = extract_json_from_text(content)
        result.setdefault("recommended_ai_employees", [])
        result.setdefault("recommended_features", [])
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="consult",
            usage=body.get("usage"), success=True,
        )
    except Exception as exc:
        result = _fallback(req)
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="consult",
            success=False, error=str(exc)[:500],
        )

    req.consulting_analysis = result.get("consulting_summary")
    req.consulting_recommendations_json = json.dumps(result)
    db.commit()
    return result
