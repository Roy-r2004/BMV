"""The execution playbook stage — the answer to "ok, and what do I DO?".

The blueprint says what the product is and why it pays; the technical plan
says how the software gets built. Neither tells the owner the thing a real
consultant gets paid for: the ordered, who-does-what plan for the whole
transformation — the data to export, the accounts to open, the hire to
make (or explicitly skip because an AI employee covers it), the partner to
engage, the numbers to watch weekly once live.

Generated from the same decomposition the documents were written from, as
structured steps the result page renders natively. Fails open like every
text stage: no playbook degrades the deliverable, never kills the request.
"""

import json

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.models import Request
from app.pipeline._shared import extract_json_from_text, log_usage
from app.pipeline.analyze import _format_site_research
from app.templating import render

_VALID_PHASES = {"before", "during", "after"}
_VALID_WHO = {"you", "bmv", "partner"}


def write_playbook(
    db: Session, request_id: int, plan_result: dict, decomposition: dict | None
) -> dict | None:
    req = db.get(Request, request_id)
    if req is None:
        raise ValueError(f"Request {request_id} not found")

    modules = (decomposition or {}).get("modules") or []
    business_case = (decomposition or {}).get("business_case") or {}

    try:
        prompt = render(
            "playbook.j2",
            business_name=req.business_name or "",
            business_description=req.business_description or "",
            industry=req.industry or "unspecified",
            revenue_today=req.revenue_today or "not stated",
            main_problem=req.main_problem or "unspecified",
            desired_outcome=req.desired_outcome or "unspecified",
            budget_range=req.budget_range or "unspecified",
            timeline=req.timeline or "unspecified",
            site_research=_format_site_research(req),
            concept_name=plan_result.get("concept_name", req.business_name or ""),
            modules=json.dumps(modules, indent=1) if modules else "(empty — derive carefully from the business itself)",
            business_case=json.dumps(business_case, indent=1) if business_case else "(empty)",
        )
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}], max_tokens=4000)
        content = body["choices"][0]["message"]["content"]
        result = extract_json_from_text(content)
        steps = [
            s for s in (result.get("steps") or [])
            if isinstance(s, dict) and s.get("title")
            and s.get("phase") in _VALID_PHASES and s.get("who") in _VALID_WHO
        ]
        if not steps:
            raise ValueError("playbook had no valid steps")
        result["steps"] = steps
        result.setdefault("people_plan", {})
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="playbook",
            usage=body.get("usage"), success=True,
        )
    except Exception as exc:
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="playbook",
            success=False, error=str(exc)[:500],
        )
        return None

    req.playbook_json = json.dumps(result)
    db.commit()
    return result
