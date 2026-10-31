import json

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.models import Request
from app.pipeline._shared import build_engagement_register, extract_json_from_text, log_usage
from app.pipeline import handoff
from app.pipeline.failure import StageFailed
from app.templating import render

def _normalize(result: dict, req: Request) -> dict:
    # Trust the model's own judgement on how many roles this business needs —
    # only step in if it blew past the cost/sanity cap. Roles the model did not
    # give are not made up here: `plan_integration` stops the run on none.
    roles = result.get("roles")
    roles = [r for r in roles if isinstance(r, dict) and r] if isinstance(roles, list) else []
    result["roles"] = roles[: settings.MAX_ROLES_PER_REQUEST]

    # A colour the model did not give is left out, not derived from a hash of
    # the business name: `phase2_bridge.palette` tells the build "our brand
    # colour is ..." from this, and is written never to guess a hex.
    theme = result.get("visual_theme")
    result["visual_theme"] = theme if isinstance(theme, dict) else {}

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
            engagement_register=build_engagement_register(
                req.engagement_type, req.needs_ai, req.main_problem, req.desired_outcome,
            req.business_description,
            diagnosis=handoff.for_build(req),
            ),
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
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="plan",
            success=False, error=str(exc)[:500],
        )
        # No plan was made. Generic roles and a colour derived from a hash of
        # the name would be drawn into every screen as this client's own.
        raise StageFailed("planning", exc) from exc

    # The call worked (and is logged as such) but planned nothing: the same
    # canned roles would stand in for it, so it stops the run just the same.
    if not result["roles"]:
        raise StageFailed("planning", "the plan returned no roles")

    req.concept_name = result.get("concept_name")
    req.visual_theme_json = json.dumps(result.get("visual_theme"))
    req.roles_json = json.dumps(result.get("roles"))
    db.commit()
    return result
