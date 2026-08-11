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


def extract_json_objects(text: str, required_keys: set[str] | None = None) -> list[dict]:
    """Salvages every individually-well-formed `{...}` object found in text,
    regardless of whether the surrounding array/wrapper is itself valid
    JSON. Used where a model's response is a list of independent objects
    (e.g. one per image prompt) — if the response gets cut off or one
    object's escaping is malformed, every object before/around the bad one
    is still recoverable instead of losing the whole batch.
    """
    # A stack of open-brace positions, one per nesting depth — every time a
    # `}` matches a `{`, that span is tried as a candidate, at ANY depth.
    # The per-prompt objects live nested inside {"image_prompts": [...]},
    # so a scanner that only captured depth-0 spans would find nothing at
    # all once the truncated/malformed outer wrapper stops the top-level
    # object from ever closing.
    objects = []
    stack: list[int] = []
    in_string = False
    escape = False
    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            stack.append(i)
        elif ch == "}" and stack:
            start = stack.pop()
            candidate = text[start : i + 1]
            try:
                obj = json.loads(candidate)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(obj, dict) and (not required_keys or required_keys.issubset(obj)):
                objects.append(obj)
    return objects


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug or "item"


def employees_with_ids(consult_result: dict) -> list[dict]:
    """`recommended_ai_employees` items only have title/why — derive a
    stable slug id from the title so image generation, storage, and
    frontend/pptx grouping all key off the same identifier without
    threading extra state through the pipeline.
    """
    employees = consult_result.get("recommended_ai_employees") or []
    seen: dict[str, int] = {}
    out = []
    for emp in employees:
        base = slugify(emp.get("title", "ai_employee"))
        seen[base] = seen.get(base, 0) + 1
        eid = base if seen[base] == 1 else f"{base}_{seen[base]}"
        out.append({"id": eid, "title": emp.get("title", "AI Employee"), "why": emp.get("why", "")})
    return out


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
    screen: str | None = None,
) -> None:
    usage = usage or {}
    event = AiUsageEvent(
        request_id=request_id,
        provider=provider,
        model=model,
        purpose=purpose,
        screen=screen,
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        image_count=image_count,
        cost_usd=usage.get("cost"),
        success=success,
        error=error,
    )
    db.add(event)
    db.commit()
