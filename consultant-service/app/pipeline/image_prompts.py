from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.models import Request
from app.pipeline._shared import employees_with_ids, extract_json_objects, log_usage
from app.templating import render

_FALLBACK_SCREENS = [
    (
        "an overview screen: a top header with a short 2-4 word page title and one short button label, "
        "then exactly 3 large bold KPI tiles in a row (one big bold number/percent/currency each, cleanly "
        "formatted, with a short 2-3 word label underneath), then a clean data table below with 4-5 rows — "
        "every cell only a short name, single word, date, or number, with a small colored status/score "
        "badge (2 digits or one short word) in the last column"
    ),
    (
        "a calendar/schedule grid screen: a top header with a short 2-4 word page title, then a weekly "
        "calendar grid with short appointment/booking blocks (a name and a time only, nothing longer) "
        "placed in a few cells, plus one small KPI tile in the corner with a single big bold number and "
        "a short 2-3 word label"
    ),
]


def _fallback_prompt(req: Request, employee: dict, visual_theme: dict, concept: str, variant_index: int) -> str:
    screen = _FALLBACK_SCREENS[variant_index % len(_FALLBACK_SCREENS)]
    return (
        f'A literal, realistic product UI screenshot — NOT a marketing poster, NOT a chat interface — '
        f'the actual dashboard screen of "{concept}", the AI-powered platform for "{req.business_name}" '
        f'({req.industry or "local"} business), for the AI employee "{employee.get("title")}". '
        f"Premium enterprise SaaS quality (Linear/Stripe/Notion-level polish). Deep near-black background, "
        f"{visual_theme.get('primary_color', '#2563eb')} as the single accent color used sparingly, clean "
        f"modern sans-serif UI font, generous spacing. Left sidebar: the plain-text wordmark \"{concept}\" "
        f"at top, then 4-5 short one-word nav items with small icons, no descriptions. Main content: {screen}. "
        f"Only short words, numbers, and 2-3 word labels anywhere — never a sentence, a chat message, or a "
        f"paragraph. No browser chrome, no tabs, no URL/address bar — the raw application interface, edge "
        f"to edge. Fixed square (1:1) canvas, every element with generous margin, nothing cropped or "
        f"touching any edge. Leave the bottom-right 20%x20% corner completely empty background — no text, "
        f"icon, or element there at all (a real logo is composited into that exact corner afterward). "
        f"Secondary color {visual_theme.get('secondary_color', '#7c3aed')}, "
        f"mood: {visual_theme.get('mood', 'premium, confident')}. "
        "No lorem ipsum, no generic placeholder labels — use real-looking short names/terms specific to this business."
    )


def _fallback_all(req: Request, employees: list[dict], visual_theme: dict, concept: str) -> list[dict]:
    return [
        {"role_id": emp["id"], "variant": variant, "prompt": _fallback_prompt(req, emp, visual_theme, concept, variant)}
        for emp in employees
        for variant in range(settings.VARIANTS_PER_ROLE)
    ]


def craft_image_prompts(db: Session, request_id: int, consult_result: dict, plan_result: dict) -> list[dict]:
    """Stage 4: an LLM writes detailed, image-model-ready prompts for every
    AI-employee/variant in one pass (keeps style direction consistent across
    the set). Images are literal product UI screenshots — one dashboard
    screen per AI employee, not a role/screenshot-of-the-whole-app and not
    a marketing poster. The one rule that survived every round of testing:
    short words/numbers/2-3 word labels render reliably; sentences, chat
    messages, and paragraphs almost always garble. Every rule in
    image_direction.j2 exists to keep visible text inside the first
    category while still showing a real, literal product. `roles` still
    exists and is used for the written blueprint/technical docs, just not
    for images. Falls back to a deterministic prompt per any employee/
    variant the model's response is missing or fails outright.
    """
    req = db.get(Request, request_id)
    if req is None:
        raise ValueError(f"Request {request_id} not found")

    employees = employees_with_ids(consult_result)
    visual_theme = plan_result.get("visual_theme") or {}
    concept = plan_result.get("concept_name") or req.business_name or ""
    fallback = _fallback_all(req, employees, visual_theme, concept)

    try:
        prompt = render(
            "image_direction.j2",
            business_name=req.business_name or "",
            business_description=req.business_description or "",
            industry=req.industry or "unspecified",
            concept_name=concept,
            visual_theme=visual_theme,
            employees=employees,
            variants_per_role=settings.VARIANTS_PER_ROLE,
        )
        # These prompts are long and detailed (up to MAX_ROLES_PER_REQUEST x
        # VARIANTS_PER_ROLE of them) — the default 2000-token cap truncated
        # the JSON mid-response in testing. Budget generously.
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}], max_tokens=8000)
        content = body["choices"][0]["message"]["content"]
        # Salvages every individually well-formed prompt object directly,
        # regardless of whether the outer {"image_prompts": [...]} wrapper
        # is itself valid — a single malformed/truncated entry no longer
        # loses the whole batch (seen in testing: one bad escape or a
        # response cut off mid-array used to fall back to ALL deterministic
        # prompts even when most of the response was fine).
        crafted = extract_json_objects(content, required_keys={"role_id", "variant", "prompt"})
        if not crafted:
            raise ValueError(f"No valid image prompt objects found in model response: {content[:300]}")

        crafted_keys = {(c.get("role_id"), c.get("variant")) for c in crafted}
        for item in fallback:
            if (item["role_id"], item["variant"]) not in crafted_keys:
                crafted.append(item)

        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="image_direction",
            usage=body.get("usage"), success=True,
            error=None if len(crafted) == len(fallback) else f"salvaged {len(crafted_keys)}/{len(fallback)} crafted prompts",
        )
        return crafted
    except Exception as exc:
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="image_direction",
            success=False, error=str(exc)[:500],
        )
        return fallback
