from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.models import Request
from app.pipeline._shared import extract_json_from_text, log_usage
from app.templating import render

_VARIANT_STYLE_HINTS = [
    "clean, minimal composition with generous white space",
    "bold, vibrant composition with confident color blocking",
    "warm, editorial composition with soft, human imagery",
]


def _fallback_prompt(req: Request, role: dict, visual_theme: dict, variant_index: int) -> str:
    style_hint = _VARIANT_STYLE_HINTS[variant_index % len(_VARIANT_STYLE_HINTS)]
    return (
        f'A high-fidelity UI screenshot mockup of a modern web app for "{req.business_name}", '
        f"a {req.industry or 'local'} business. {req.business_description}\n\n"
        f"Screen: {role.get('label')} — {role.get('description')}\n\n"
        f"Visual direction: {visual_theme.get('style', 'modern, professional')}, "
        f"mood: {visual_theme.get('mood', 'trustworthy, warm')}. "
        f"Primary color {visual_theme.get('primary_color', '#2563eb')}, "
        f"secondary color {visual_theme.get('secondary_color', '#7c3aed')}, "
        f"background {visual_theme.get('background_color', '#f8fafc')}.\n\n"
        f"Style for this variant: {style_hint}. "
        "Render as a realistic desktop browser screenshot of a polished, production-quality website/app "
        "interface — real-looking (but fictional) UI text, no watermarks, no placeholder lorem ipsum, "
        "no stock-photo-style close-ups of people."
    )


def _fallback_all(req: Request, roles: list[dict], visual_theme: dict) -> list[dict]:
    return [
        {"role_id": role.get("id", "role"), "variant": variant, "prompt": _fallback_prompt(req, role, visual_theme, variant)}
        for role in roles
        for variant in range(settings.VARIANTS_PER_ROLE)
    ]


def craft_image_prompts(db: Session, request_id: int, plan_result: dict) -> list[dict]:
    """Stage 4: an LLM writes detailed, image-model-ready prompts for every
    role/variant in one pass (keeps style direction consistent across the
    set). Falls back to a deterministic prompt per any role/variant the
    model's response is missing or fails outright.
    """
    req = db.get(Request, request_id)
    if req is None:
        raise ValueError(f"Request {request_id} not found")

    roles = plan_result.get("roles") or []
    visual_theme = plan_result.get("visual_theme") or {}
    fallback = _fallback_all(req, roles, visual_theme)

    try:
        prompt = render(
            "image_direction.j2",
            business_name=req.business_name or "",
            business_description=req.business_description or "",
            industry=req.industry or "unspecified",
            visual_theme=visual_theme,
            roles=roles,
            variants_per_role=settings.VARIANTS_PER_ROLE,
        )
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}])
        content = body["choices"][0]["message"]["content"]
        result = extract_json_from_text(content)
        crafted = result.get("image_prompts") or []

        crafted_keys = {(c.get("role_id"), c.get("variant")) for c in crafted}
        for item in fallback:
            if (item["role_id"], item["variant"]) not in crafted_keys:
                crafted.append(item)

        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="image_direction",
            usage=body.get("usage"), success=True,
        )
        return crafted
    except Exception as exc:
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="image_direction",
            success=False, error=str(exc)[:500],
        )
        return fallback
