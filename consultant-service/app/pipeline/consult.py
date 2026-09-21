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


def _format_diagnosis(req: Request) -> str:
    """The diagnosis as the lines the recommendation has to answer.

    Empty string when there is none, which the template reads as "no
    diagnosis" rather than "a diagnosis that found nothing" — the second
    would have the model write around a conclusion that was never reached.
    """
    if not req.diagnosis_json:
        return ""
    try:
        d = json.loads(req.diagnosis_json)
    except (TypeError, ValueError):
        return ""
    leading = next((h for h in d.get("hypotheses") or [] if h.get("id") == d.get("leading")), None)
    if not leading:
        return ""
    test = leading.get("test") or {}
    lines = [f"The cause: {leading['statement']}"]
    if test.get("because"):
        verdict = test.get("verdict", "untestable")
        cites = ", ".join(test.get("cites") or [])
        lines.append(f"Tested against their numbers — {verdict}: {test['because']}"
                     + (f" (their figures: {cites})" if cites else ""))
    if test.get("would_need"):
        lines.append(f"Still unverified. To settle it we would need: {test['would_need']}")
    status = d.get("status")
    if status == "survived":
        lines.append("Two reviewers tried to kill this and could not.")
    elif status == "killed":
        lines.append("A reviewer landed a hit on this — treat it as the best available reading, not a settled fact.")
    else:
        lines.append("This went unchallenged — the review could not be run, so nothing has tested it but the evidence above.")
    for w in d.get("weaknesses") or []:
        lines.append(f"Weakness a reviewer left standing: {w}")
    rejected = [h for h in d.get("hypotheses") or [] if h.get("id") != d.get("leading")]
    if rejected:
        lines.append("Explanations considered and set aside: "
                     + "; ".join(f"{h['statement']} ({(h.get('test') or {}).get('verdict', 'untested')})"
                                 for h in rejected))
    return "\n".join(lines)


def consult(db: Session, request_id: int, analysis: dict) -> dict:
    """Stage 2: given the analysis, recommend what should be included."""
    req = db.get(Request, request_id)
    if req is None:
        raise ValueError(f"Request {request_id} not found")

    try:
        prompt = render(
            "consult.j2",
            diagnosis=_format_diagnosis(req),
            business_name=req.business_name or "",
            business_description=req.business_description or "",
            business_model=analysis.get("business_model", "Unknown"),
            target_customer_profile=analysis.get("target_customer_profile", ""),
            pain_points=json.dumps(analysis.get("pain_points", [])),
            growth_opportunity=analysis.get("growth_opportunity", ""),
            engagement_register=build_engagement_register(
                req.engagement_type, req.needs_ai, req.main_problem, req.desired_outcome,
            req.business_description,
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
