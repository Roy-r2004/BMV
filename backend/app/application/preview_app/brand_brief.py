"""Canonical brand brief — early visual contract every preview page must inherit."""
from __future__ import annotations

import json
import re
from typing import Any

from app.application.preview_app.design_recipes import get_recipe, pick_recipe_id

# AI-default clusters we refuse to ship as "brand".
_BANNED_PRIMARY = {
    "#6366f1",
    "#4f46e5",
    "#7c3aed",
    "#8b5cf6",
    "#9333ea",
    "#a855f7",
    "#2563eb",
    "#3b82f6",
}
_BANNED_BG = {"#f4f1ea", "#faf7f2", "#fffdf8"}

_INDUSTRY_PALETTES: dict[str, dict[str, str]] = {
    "wellness": {
        "primary": "#0f766e",
        "secondary": "#134e4a",
        "background": "#f0fdfa",
        "surface": "#ffffff",
        "text": "#042f2e",
        "muted": "#5f7a78",
    },
    "fitness": {
        "primary": "#c2410c",
        "secondary": "#431407",
        "background": "#fff7ed",
        "surface": "#ffffff",
        "text": "#1c1917",
        "muted": "#78716c",
    },
    "food": {
        "primary": "#b45309",
        "secondary": "#44403c",
        "background": "#fffbeb",
        "surface": "#ffffff",
        "text": "#1c1917",
        "muted": "#78716c",
    },
    "professional": {
        "primary": "#0f172a",
        "secondary": "#334155",
        "background": "#f8fafc",
        "surface": "#ffffff",
        "text": "#0f172a",
        "muted": "#64748b",
    },
    "creative": {
        "primary": "#9f1239",
        "secondary": "#1e1b4b",
        "background": "#fff1f2",
        "surface": "#ffffff",
        "text": "#1c1917",
        "muted": "#78716c",
    },
}


def _norm_hex(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", text):
        return text.lower()
    if re.fullmatch(r"[0-9A-Fa-f]{6}", text):
        return f"#{text.lower()}"
    return fallback.lower()


def _industry_bucket(industry: str | None, description: str | None = None) -> str:
    blob = f"{industry or ''} {description or ''}".lower()
    if re.search(r"yoga|pilates|spa|wellness|salon|beauty|massage|clinic|dental", blob):
        return "wellness"
    if re.search(r"gym|fitness|trainer|crossfit|sport", blob):
        return "fitness"
    if re.search(r"restaurant|cafe|coffee|bakery|food|kitchen|dining", blob):
        return "food"
    if re.search(r"gallery|studio|design|architect|fashion|jewelry", blob):
        return "creative"
    if re.search(r"law|legal|finance|account|consult|saas|software|b2b", blob):
        return "professional"
    return "wellness" if "health" in blob else "professional"


def _signature_for(bucket: str, business_name: str) -> str:
    name = (business_name or "the brand").strip()
    return {
        "wellness": f"A calm full-bleed atmosphere with {name} as the hero signal, not a card grid.",
        "fitness": f"High-energy kinetic type and a bold CTA band that feels like {name}, not a SaaS dashboard.",
        "food": f"Appetite-led photography and a menu-first first viewport for {name}.",
        "creative": f"Editorial asymmetry and display type that could only belong to {name}.",
        "professional": f"Precise typography and restrained color — authority without looking like a template.",
    }.get(bucket, f"One distinctive first viewport that unmistakably belongs to {name}.")


def _voice_for(bucket: str) -> str:
    return {
        "wellness": "Warm, grounded, unhurried. Speak like a trusted studio host.",
        "fitness": "Direct, energetic, coach-like. Short verbs.",
        "food": "Sensory and specific. Name real dishes and moments.",
        "creative": "Confident and sparse. Let materials and type carry the tone.",
        "professional": "Clear and credible. No hype adjectives.",
    }.get(bucket, "Specific to the business. Never generic SaaS marketing.")


def build_brand_brief(
    demo: dict[str, Any] | None,
    *,
    business_name: str | None = None,
    industry: str | None = None,
    business_description: str | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """Build a locked brand brief from visual theme + industry (deterministic)."""

    demo = demo or {}
    theme = dict(demo.get("visual_theme") or {})
    bucket = _industry_bucket(industry, business_description)
    palette_seed = _INDUSTRY_PALETTES[bucket]
    primary = _norm_hex(theme.get("primary_color"), palette_seed["primary"])
    secondary = _norm_hex(theme.get("secondary_color"), palette_seed["secondary"])
    background = _norm_hex(theme.get("background_color"), palette_seed["background"])
    if primary in _BANNED_PRIMARY:
        primary = palette_seed["primary"]
    if secondary in _BANNED_PRIMARY:
        secondary = palette_seed["secondary"]
    if background in _BANNED_BG:
        background = palette_seed["background"]

    recipe_id = pick_recipe_id(
        industry=industry,
        business_description=business_description,
        concept_name=business_name or demo.get("product_name"),
        seed=seed,
    )
    recipe = get_recipe(recipe_id)
    fonts = recipe.get("fonts") or {}
    sans = str(fonts.get("sans") or '"Source Sans 3", sans-serif')
    display = str(fonts.get("display") or sans)
    import_q = str(fonts.get("import") or "Source+Sans+3:wght@400;500;600;700")

    mood = str(theme.get("style") or recipe.get("label") or bucket).strip()
    name = (
        business_name
        or demo.get("product_name")
        or "Brand"
    ).strip()

    brief = {
        "version": "1.0",
        "brand_name": name,
        "locked": True,
        "industry_bucket": bucket,
        "mood": mood,
        "voice": _voice_for(bucket),
        "signature": _signature_for(bucket, name),
        "palette": {
            "primary": primary,
            "secondary": secondary,
            "background": background,
            "surface": palette_seed["surface"],
            "text": palette_seed["text"],
            "muted": palette_seed["muted"],
        },
        "typography": {
            "font_family": sans.split(",")[0].strip().strip('"'),
            "display_font_family": display.split(",")[0].strip().strip('"'),
            "font_sans": sans,
            "font_display": display,
            "font_import": import_q,
            "font_import_url": (
                f"https://fonts.googleapis.com/css2?family={import_q}&display=swap"
            ),
        },
        "recipe_id": recipe["id"],
        "avoid": [
            "purple-on-white or purple-to-indigo default themes",
            "Inter / Roboto / Arial as the display face",
            "card grids in the hero",
            "generic SaaS marketing copy",
            "inventing a second palette per page",
        ],
        "rules": [
            "Every page inherits this palette and type stack via CSS tokens only.",
            "Use bg-brand / text-brand / font-display — never hardcode hex colors.",
            "First viewport must feature the brand name as a hero-level signal.",
        ],
    }
    return brief


def ensure_brand_brief(
    demo: dict[str, Any],
    *,
    business_name: str | None = None,
    industry: str | None = None,
    business_description: str | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """Attach/refresh ``brand_brief`` on the visual demo and sync visual_theme colors."""

    brief = build_brand_brief(
        demo,
        business_name=business_name,
        industry=industry,
        business_description=business_description,
        seed=seed,
    )
    demo = dict(demo or {})
    demo["brand_brief"] = brief
    theme = dict(demo.get("visual_theme") or {})
    theme["primary_color"] = brief["palette"]["primary"]
    theme["secondary_color"] = brief["palette"]["secondary"]
    theme["background_color"] = brief["palette"]["background"]
    theme["font_style"] = brief["typography"]["display_font_family"]
    theme["style"] = brief["mood"]
    demo["visual_theme"] = theme
    return demo


def design_system_from_brief(brief: dict[str, Any]) -> dict[str, Any]:
    """Flatten a brand brief into the design_system object used by codegen."""

    palette = brief.get("palette") or {}
    typography = brief.get("typography") or {}
    return {
        "primary_color": palette.get("primary"),
        "secondary_color": palette.get("secondary"),
        "background_color": palette.get("background"),
        "surface_color": palette.get("surface"),
        "text_color": palette.get("text"),
        "muted_text_color": palette.get("muted"),
        "font_family": typography.get("font_family"),
        "display_font_family": typography.get("display_font_family"),
        "font_import_url": typography.get("font_import_url"),
        "font_sans": typography.get("font_sans"),
        "font_display": typography.get("font_display"),
        "brand_locked": True,
        "brand_brief_version": brief.get("version"),
        "mood": brief.get("mood"),
        "voice": brief.get("voice"),
        "signature": brief.get("signature"),
        "avoid": list(brief.get("avoid") or []),
        "rules": list(brief.get("rules") or []),
        "recipe_id": brief.get("recipe_id"),
    }


def apply_brief_to_plan(plan: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    """Force plan.design_system to inherit the locked brand brief (recipe layout kept)."""

    updated = dict(plan or {})
    design = dict(updated.get("design_system") or {})
    locked = design_system_from_brief(brief)
    # Preserve recipe composition fields stamped earlier.
    for key in (
        "hub_variant",
        "hero_variant",
        "feature_variant",
        "recipe_prompt",
        "style_keywords",
        "border_radius",
        "recipe_id",
    ):
        if design.get(key) is not None:
            locked[key] = design[key]
    if brief.get("recipe_id") and not locked.get("recipe_id"):
        locked["recipe_id"] = brief["recipe_id"]
    updated["design_system"] = locked
    if brief.get("recipe_id"):
        updated.setdefault("recipe_id", brief["recipe_id"])
    direction = str(updated.get("design_direction") or "").strip()
    signature = str(brief.get("signature") or "").strip()
    if signature and signature not in direction:
        updated["design_direction"] = f"{signature} {direction}".strip()
    rules = list(updated.get("consistency_rules") or [])
    for rule in brief.get("rules") or []:
        if rule not in rules:
            rules.append(rule)
    updated["consistency_rules"] = rules
    return updated


def brief_prompt_block(brief: dict[str, Any] | None) -> str:
    if not brief:
        return ""
    return (
        "=== LOCKED BRAND BRIEF (NON-NEGOTIABLE) ===\n"
        f"{json.dumps(brief, ensure_ascii=False, indent=2)}\n"
        "- Do NOT invent a new palette, font stack, or mood.\n"
        "- Do NOT use purple gradients, Inter, or generic SaaS chrome.\n"
        "- Inherit tokens via bg-brand / text-brand / font-display only.\n"
    )


__all__ = [
    "apply_brief_to_plan",
    "brief_prompt_block",
    "build_brand_brief",
    "design_system_from_brief",
    "ensure_brand_brief",
]
