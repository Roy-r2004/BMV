import json
import re
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import AiUsageEvent, Request


def emit(db: Session, request_id: int, stage: str, label: str, pct: int, detail: str | None = None) -> None:
    req = db.get(Request, request_id)
    if req is None:
        return
    req.stage = stage
    req.stage_label = label
    req.progress_pct = pct
    req.progress_detail = detail
    req.updated_at = datetime.utcnow()
    db.commit()


def extract_json_from_text(text: str) -> dict:
    """Pulls the first {...} block out of a model response and parses it.

    Models are asked to return raw JSON but sometimes wrap it in prose or
    markdown fences anyway — this tolerates that without pulling in a
    dependency.
    """
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fence_match.group(1) if fence_match else text

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"No JSON object found in model response: {text[:300]}")
    return json.loads(candidate[start : end + 1])


def log_usage(
    db: Session,
    request_id: int | None,
    *,
    provider: str,
    model: str,
    purpose: str,
    usage: dict | None = None,
    image_count: int | None = None,
    success: bool = True,
    error: str | None = None,
) -> None:
    usage = usage or {}
    event = AiUsageEvent(
        request_id=request_id,
        provider=provider,
        model=model,
        purpose=purpose,
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        image_count=image_count,
        cost_usd=usage.get("cost"),
        success=success,
        error=error,
    )
    db.add(event)
    db.commit()
