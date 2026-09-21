"""What to do about the diagnosed cause — including "not software".

`consult` could only ever answer one question: which AI employees. Its output
shape said so (`recommended_ai_employees`, set by default on every path) and
its fallback hardcoded a front desk and an analyst for every business on
earth. A pipeline whose only available answer is the thing it sells is not
consulting, and the client can tell.

So this stage names the KIND of intervention first, and only then what to
build. When the kind is not `software` the engagement can end at the brief:
the client gets an answer worth more than a blueprint they did not need, and
it costs one model call instead of thirteen stages of generation.

It keeps `consulting_summary`, `recommended_ai_employees` and
`recommended_features` in its output, unchanged in name and meaning, because
stages 7-19 read them. Nothing downstream knows this stage replaced `consult`.

Fails open to `consult` itself, which is what the pipeline did before.
"""

import json
import logging

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.models import Request
from app.pipeline import consult
from app.pipeline._shared import build_engagement_register, extract_json_from_text, log_usage
from app.templating import render

logger = logging.getLogger("consultant.decide")

#: What actually fixes the diagnosed cause. `SOFTWARE` is the only one that
#: earns a build; the rest end at the brief unless the client overrides.
KINDS = ("software", "process", "pricing", "staffing", "none")
SOFTWARE = "software"

DECIDE_TOKENS = 4000


def builds(result: dict | None) -> bool:
    """Whether this decision justifies running the build half.

    A missing or unreadable `intervention_kind` builds, deliberately: this is
    the behaviour the pipeline had before the field existed, and a parse
    failure must not silently withhold the deliverable the client came for.
    Only an explicit non-software answer stops the build.
    """
    kind = (result or {}).get("intervention_kind")
    return kind not in [k for k in KINDS if k != SOFTWARE]


def decide(db: Session, request_id: int, analysis: dict) -> dict:
    req = db.get(Request, request_id)
    if req is None:
        raise ValueError(f"Request {request_id} not found")

    try:
        prompt = render(
            "decide.j2",
            business_name=req.business_name or "",
            business_description=req.business_description or "",
            desired_outcome=req.desired_outcome or "unspecified",
            business_model=analysis.get("business_model", "Unknown"),
            target_customer_profile=analysis.get("target_customer_profile", ""),
            pain_points=json.dumps(analysis.get("pain_points", [])),
            diagnosis=consult._format_diagnosis(req),
            engagement_register=build_engagement_register(
                req.engagement_type, req.needs_ai, req.main_problem, req.desired_outcome,
                req.business_description,
            ),
        )
        body = provider.chat(settings.REASONING_MODEL, [{"role": "user", "content": prompt}],
                             max_tokens=DECIDE_TOKENS)
        result = extract_json_from_text(body["choices"][0]["message"]["content"])
        log_usage(db, request_id, provider="openrouter", model=settings.REASONING_MODEL,
                  purpose="decide", usage=body.get("usage"), success=True)
    except Exception as exc:
        log_usage(db, request_id, provider="openrouter", model=settings.REASONING_MODEL,
                  purpose="decide", success=False, error=str(exc)[:500])
        logger.warning("decision could not be made, falling back to consult: %s", str(exc)[:200])
        # `consult` writes its own result to the row and returns it. The
        # engagement then behaves exactly as it did before this stage existed.
        return consult.consult(db, request_id, analysis)

    kind = result.get("intervention_kind")
    if kind not in KINDS:
        # An unreadable kind must not be guessed into a refusal to build. It
        # is dropped, `builds()` then answers True, and the client gets their
        # deliverable — the failure mode of this stage has to be the old
        # behaviour, never a withheld engagement.
        logger.warning("unusable intervention_kind %r; treating as unset", kind)
        result.pop("intervention_kind", None)

    result.setdefault("recommended_ai_employees", [])
    result.setdefault("recommended_features", [])
    if result.get("confidence") not in ("high", "medium", "low"):
        result["confidence"] = "medium"
    result["unverified"] = [str(u)[:300] for u in (result.get("unverified") or [])
                            if isinstance(u, str) and u.strip()]

    req.consulting_analysis = result.get("consulting_summary")
    req.consulting_recommendations_json = json.dumps(result)
    db.commit()
    return result
