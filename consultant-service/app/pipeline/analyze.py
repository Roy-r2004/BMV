import json

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.models import Request
from app.pipeline._shared import extract_json_from_text, log_usage
from app.templating import render


def _fallback(req: Request) -> dict:
    return {
        "business_model": "Unknown",
        "target_customer_profile": req.target_customers or "General local customers",
        "pain_points": ["Missed inquiries outside business hours", "Manual scheduling / order-taking"],
        "growth_opportunity": "An AI front-desk employee that responds instantly and never misses an inquiry.",
    }


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
