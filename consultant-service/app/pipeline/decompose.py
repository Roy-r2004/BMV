"""The decomposition stage — the difference between a brochure and a
deliverable a company would pay for.

The old shape asked one LLM call to write a whole blueprint from
summaries-of-summaries, and it produced exactly what that produces:
confident generic prose. This stage inverts it: FIRST break the proposed
product into named modules and an explicit business case (structured JSON,
each claim traceable to intake facts), THEN deep-spec each module with its
own dedicated call — so the documents downstream are assembled from
specifics that already exist as data, not improvised as sentences.

Fails open like every text stage here: no decomposition means the
blueprint falls back to its pre-decomposition quality, it never kills the
request.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.models import Request
from app.pipeline._shared import extract_json_from_text, log_usage
from app.pipeline.analyze import _format_site_research
from app.templating import render

logger = logging.getLogger("consultant.decompose")


def _clamp_modules(modules: list) -> list:
    """Soft bounds, same pattern as roles: trust the model's count, step in
    only on a degenerate or runaway answer."""
    cleaned = [m for m in modules if isinstance(m, dict) and m.get("name")]
    return cleaned[: settings.MAX_MODULES_PER_REQUEST]


def decompose_business(
    db: Session, request_id: int, analysis: dict, consult_result: dict, plan_result: dict
) -> dict | None:
    """Break the product into modules + business case, then deep-spec each
    module with its own call (in parallel — they are independent).

    Returns {"modules": [...], "business_case": {...}} with each module
    carrying its deep spec under "spec" (None when that one call failed),
    or None when the decomposition call itself failed.
    """
    req = db.get(Request, request_id)
    if req is None:
        raise ValueError(f"Request {request_id} not found")

    try:
        prompt = render(
            "decompose.j2",
            business_name=req.business_name or "",
            business_description=req.business_description or "",
            industry=req.industry or "unspecified",
            revenue_today=req.revenue_today or "not stated — infer carefully from the business type, and say so",
            main_problem=req.main_problem or "unspecified",
            desired_outcome=req.desired_outcome or "unspecified",
            site_research=_format_site_research(req),
            business_model=analysis.get("business_model", "Unknown"),
            target_customer_profile=analysis.get("target_customer_profile", ""),
            pain_points=json.dumps(analysis.get("pain_points", [])),
            growth_opportunity=analysis.get("growth_opportunity", ""),
            consulting_summary=consult_result.get("consulting_summary", ""),
            recommended_ai_employees=json.dumps(consult_result.get("recommended_ai_employees", [])),
            recommended_features=json.dumps(consult_result.get("recommended_features", [])),
            concept_name=plan_result.get("concept_name", req.business_name or ""),
            min_modules=settings.MIN_MODULES_PER_REQUEST,
            max_modules=settings.MAX_MODULES_PER_REQUEST,
        )
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}], max_tokens=3000)
        content = body["choices"][0]["message"]["content"]
        result = extract_json_from_text(content)
        modules = _clamp_modules(result.get("modules") or [])
        business_case = result.get("business_case") or {}
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="decompose",
            usage=body.get("usage"), success=True,
        )
    except Exception as exc:
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="decompose",
            success=False, error=str(exc)[:500],
        )
        return None

    if not modules:
        logger.warning("decomposition returned no usable modules: request=%s", request_id)
        return None

    # Deep-spec each module with its own dedicated call. The calls are pure
    # HTTP and independent, so they run in parallel — but the DB session is
    # not thread-safe, so usage is collected in-thread and ledgered here on
    # the request thread afterwards.
    site_research = _format_site_research(req)

    def _spec_one(module: dict) -> tuple[dict | None, dict | None, str | None]:
        others = "\n".join(
            f"- {m.get('name')}: {m.get('purpose', '')}" for m in modules if m is not module
        ) or "none"
        try:
            spec_prompt = render(
                "module_spec.j2",
                business_name=req.business_name or "",
                business_description=req.business_description or "",
                site_research=site_research,
                target_customer_profile=analysis.get("target_customer_profile", ""),
                module_id=module.get("id") or "module",
                module_name=module.get("name") or "",
                module_purpose=module.get("purpose") or "",
                module_users=json.dumps(module.get("users") or []),
                module_pain_point=module.get("pain_point_addressed") or "",
                other_modules=others,
            )
            body = provider.chat(
                settings.ANALYSIS_MODEL, [{"role": "user", "content": spec_prompt}], max_tokens=2000,
            )
            return extract_json_from_text(body["choices"][0]["message"]["content"]), body.get("usage"), None
        except Exception as exc:  # one module's spec failing must not sink the rest
            return None, None, str(exc)[:500]

    with ThreadPoolExecutor(max_workers=min(4, len(modules))) as pool:
        results = list(pool.map(_spec_one, modules))

    for module, (spec, usage, error) in zip(modules, results):
        module["spec"] = spec
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="module_spec",
            usage=usage, success=error is None, error=error,
        )

    req.modules_json = json.dumps(modules)
    req.business_case_json = json.dumps(business_case)
    db.commit()
    return {"modules": modules, "business_case": business_case}
