"""Stages 4-5 of the consulting workflow: the client-facing MVP Blueprint
and the Technical Implementation Plan — the written half of the paid
deliverable (the images are the visual half).

Both are raw Markdown (no JSON envelope — long documents survive better
without escaping), and both fail OPEN: a missing document degrades the
deliverable, it doesn't kill the request. The frontend only marks the
Blueprint/Technical sections ready when the field is non-null.
"""

import json

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.models import Request
from app.pipeline._shared import log_usage
from app.templating import render


def _markdown_call(db: Session, request_id: int, purpose: str, prompt: str) -> str | None:
    try:
        body = provider.chat(
            settings.ANALYSIS_MODEL,
            [{"role": "user", "content": prompt}],
            max_tokens=4000,
        )
        content = (body["choices"][0]["message"]["content"] or "").strip()
        if content.startswith("```"):
            content = content.strip("`").removeprefix("markdown").strip()
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose=purpose,
            usage=body.get("usage"), success=True,
        )
        return content or None
    except Exception as exc:
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose=purpose,
            success=False, error=str(exc)[:500],
        )
        return None


def write_blueprint(db: Session, request_id: int, analysis: dict, consult_result: dict, plan_result: dict) -> str | None:
    req = db.get(Request, request_id)
    if req is None:
        raise ValueError(f"Request {request_id} not found")

    prompt = render(
        "blueprint.j2",
        business_name=req.business_name or "",
        business_description=req.business_description or "",
        industry=req.industry or "unspecified",
        business_model=analysis.get("business_model", "Unknown"),
        target_customer_profile=analysis.get("target_customer_profile", ""),
        pain_points=json.dumps(analysis.get("pain_points", [])),
        growth_opportunity=analysis.get("growth_opportunity", ""),
        consulting_summary=consult_result.get("consulting_summary", ""),
        recommended_ai_employees=json.dumps(consult_result.get("recommended_ai_employees", [])),
        recommended_features=json.dumps(consult_result.get("recommended_features", [])),
        concept_name=plan_result.get("concept_name", req.business_name or ""),
        roles=json.dumps(plan_result.get("roles", [])),
    )
    content = _markdown_call(db, request_id, "blueprint", prompt)
    req.mvp_blueprint = content
    db.commit()
    return content


def write_technical_plan(db: Session, request_id: int, consult_result: dict, plan_result: dict) -> str | None:
    req = db.get(Request, request_id)
    if req is None:
        raise ValueError(f"Request {request_id} not found")

    prompt = render(
        "technical_plan.j2",
        business_name=req.business_name or "",
        business_description=req.business_description or "",
        concept_name=plan_result.get("concept_name", req.business_name or ""),
        roles=json.dumps(plan_result.get("roles", [])),
        recommended_ai_employees=json.dumps(consult_result.get("recommended_ai_employees", [])),
        recommended_features=json.dumps(consult_result.get("recommended_features", [])),
    )
    content = _markdown_call(db, request_id, "technical_plan", prompt)
    req.technical_plan = content
    db.commit()
    return content
