import hashlib
import json

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.models import Request
from app.pipeline._shared import extract_json_from_text, log_usage
from app.templating import render

_DEFAULT_ROLES = [
    {
        "id": "customer_view",
        "label": "Customer View",
        "description": "What a customer sees when they visit — the front-desk AI greeting and helping them.",
        "features_shown": [],
    },
    {
        "id": "owner_dashboard",
        "label": "Owner / AI Employee Dashboard",
        "description": "What the business owner sees — today's activity, what the AI handled, and results.",
        "features_shown": [],
    },
]


def _fallback_palette(seed: str) -> dict:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return {
        "primary_color": "#" + digest[0:6],
        "secondary_color": "#" + digest[6:12],
        "background_color": "#" + digest[12:18],
        "style": "modern, professional",
        "mood": "trustworthy, warm",
    }


def _fallback(req: Request) -> dict:
    return {
        "concept_name": req.business_name or "Your AI-Powered Business",
        "roles": _DEFAULT_ROLES,
        "visual_theme": _fallback_palette(req.business_name or str(req.id)),
    }


def _normalize(result: dict, req: Request) -> dict:
    # Trust the model's own judgement on how many roles this business needs —
    # only step in if it returned nothing, or blew past the cost/sanity cap.
    roles = result.get("roles") or []
    if not roles:
        roles = _DEFAULT_ROLES
    elif len(roles) > settings.MAX_ROLES_PER_REQUEST:
        roles = roles[: settings.MAX_ROLES_PER_REQUEST]
    result["roles"] = roles

    theme = result.get("visual_theme") or {}
    for key, value in _fallback_palette(req.business_name or str(req.id)).items():
        theme.setdefault(key, value)
    result["visual_theme"] = theme

    if not result.get("concept_name"):
        result["concept_name"] = req.business_name or "Your AI-Powered Business"
    return result


def plan_integration(db: Session, request_id: int, consult_result: dict) -> dict:
    """Stage 3: turn the consulting recommendation into concrete roles/screens + brand direction."""
    req = db.get(Request, request_id)
    if req is None:
        raise ValueError(f"Request {request_id} not found")

    try:
        prompt = render(
            "plan.j2",
            business_name=req.business_name or "",
            business_description=req.business_description or "",
            consulting_summary=consult_result.get("consulting_summary", ""),
            recommended_ai_employees=json.dumps(consult_result.get("recommended_ai_employees", [])),
            recommended_features=json.dumps(consult_result.get("recommended_features", [])),
            min_roles=settings.MIN_ROLES_PER_REQUEST,
            max_roles=settings.MAX_ROLES_PER_REQUEST,
        )
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}])
        content = body["choices"][0]["message"]["content"]
        result = _normalize(extract_json_from_text(content), req)
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="plan",
            usage=body.get("usage"), success=True,
        )
    except Exception as exc:
        result = _fallback(req)
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="plan",
            success=False, error=str(exc)[:500],
        )

    req.concept_name = result.get("concept_name")
    req.visual_theme_json = json.dumps(result.get("visual_theme"))
    req.roles_json = json.dumps(result.get("roles"))
    db.commit()
    return result
