import json
import re
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import AiUsageEvent, Request


CORRECTIONS_MARKER = "Corrections and additions from the briefing chat:"


def briefing_corrections(business_description: str | None) -> str:
    """The client's own additions from the pre-launch briefing chat, as one
    line — they extend the capability's scope and every stage must know."""
    text = business_description or ""
    if CORRECTIONS_MARKER not in text:
        return ""
    tail = text.split(CORRECTIONS_MARKER, 1)[1]
    lines = [ln.strip().lstrip("-• ").strip() for ln in tail.splitlines()]
    return " ".join(ln for ln in lines if ln)


def build_engagement_register(
    engagement_type: str | None,
    needs_ai: str | None,
    main_problem: str | None,
    desired_outcome: str | None,
    business_description: str | None = None,
) -> str:
    """The scope-and-AI-appetite paragraph injected into every content
    prompt. Two independent axes: whole-business vs one-capability, and
    how much AI the client actually asked for. One shared builder so the
    register can never drift between stages. The client's briefing-chat
    corrections extend the capability (a past run read a client-added
    workstream as a second capability because the register never said)."""
    corrections = briefing_corrections(business_description)
    if engagement_type == "capability":
        focus = main_problem or desired_outcome or "the one problem stated in their brief"
        base = (
            "This engagement blueprints ONE CAPABILITY for an existing operation, NOT the whole "
            f"business. The capability: {focus}. Scope everything to that capability and how it "
            "integrates into what they already run — their existing tools, staff and routines are "
            "the fixed landscape, not things to redesign. Do not propose modules, screens or steps "
            "outside this capability's slice, and always include how it plugs into their current "
            "operation."
        )
        if corrections:
            base += (
                " The client EXTENDED the capability in the briefing chat — these corrections are part "
                f"of the scope, not scope creep: {corrections}"
            )
    else:
        base = (
            "This engagement blueprints the WHOLE BUSINESS — the complete operating picture: how "
            "it earns, how work flows, who does what, and the systems underneath."
        )
    if needs_ai == "no":
        base += (
            " The client asked for NO AI: recommend none. Human procedures, good process design "
            "and simple off-the-shelf tools are the answer; an empty AI list is the correct answer."
        )
    elif needs_ai == "maybe":
        base += (
            " The client is unsure about AI: recommend it only where it clearly earns its place, "
            "and prefer human procedures or simple tools where they honestly suffice."
        )
    else:
        base += " The client wants AI where it genuinely helps — it still must earn each placement."
    return base


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
