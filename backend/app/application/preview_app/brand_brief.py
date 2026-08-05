"""Canonical brand brief — early visual contract every preview page must inherit."""
from __future__ import annotations

import json
import re
from typing import Any

from app.application.preview_app.brand_palette import derive_palette
from app.application.preview_app.design_recipes import get_recipe, pick_recipe_id


def _industry_bucket(industry: str | None, description: str | None = None) -> str:
    """Which *voice* a brief is written in. It no longer decides any colour.

    It is still keyword-matched and still wrong in the way keyword tables are:
    the art-gallery briefs say *"not a booking SaaS or clinic front desk"* and
    this table matches ``clinic`` inside that negation, which is how 28 of the
    62 archived workspaces are bucketed ``wellness``.
    ``product_kind.scrub_negated_product_clauses`` does not reach it — its
    pattern lists product nouns and ``clinic`` is not one — and measured over
    all 84 stored requests, applying that scrub here changes **zero** buckets.
    So the scrub is not applied: it would be an inert edit. What removed the
    consequence was taking colour away from this function entirely; what is
    left is voice and signature prose.
    """

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
    """Build a locked brand brief from the business itself (deterministic).

    The palette is **derived, and authoritative**. It used to be
    ``_norm_hex(theme.get("primary_color"), industry_seed)`` — the upstream
    demo's colour first, the industry table only as a fallback — and the demo
    stage stamped one teal over almost every run before this function ever saw
    it. Measured across the corpus, the model supplied a brand colour that
    survived to the shipped site exactly **once in 62 runs**, so what that
    precedence bought was not brand fidelity, it was the monoculture.

    ``brand_locked`` already declares this brief the single source of truth and
    ``ensure_brand_brief`` already writes the brief's palette back over
    ``visual_theme``; making the derivation authoritative is that contract
    stated once instead of half-applied.
    """

    demo = demo or {}
    theme = dict(demo.get("visual_theme") or {})
    bucket = _industry_bucket(industry, business_description)
    palette = derive_palette(
        (business_name or demo.get("product_name") or "").strip(),
        business_description,
    )

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
        "palette": dict(palette),
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


def _preview_brand_candidate(value: Any) -> str:
    """Nonempty real name only — literal ``Brand`` is treated as unknown."""
    text = str(value or "").strip()
    if not text or text == "Brand":
        return ""
    return text


def resolve_preview_brand_name(
    *,
    brand_name: str | None = None,
    brand_brief: dict[str, Any] | None = None,
    business_name: str | None = None,
    concept_name: str | None = None,
    manifest: dict[str, Any] | None = None,
    demo: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
    fallback: bool = True,
) -> str | None:
    """Resolve one preview brand name. First nonempty real candidate wins.

    Priority: explicit brand_name → brand_brief.brand_name → business_name →
    concept_name → manifest brand → demo product_name / plan concept_name.
    Literal ``\"Brand\"`` is never invented mid-chain; returned only when
    ``fallback=True`` and no real name exists (write-site default).
    """
    brief = brand_brief if isinstance(brand_brief, dict) else {}
    manifest = manifest if isinstance(manifest, dict) else {}
    demo = demo if isinstance(demo, dict) else {}
    plan = plan if isinstance(plan, dict) else {}
    manifest_brand = (
        manifest.get("brand") if isinstance(manifest.get("brand"), dict) else {}
    )

    for candidate in (
        brand_name,
        brief.get("brand_name"),
        business_name,
        concept_name,
        manifest_brand.get("name"),
        manifest.get("brand_name"),
        demo.get("product_name"),
        plan.get("concept_name"),
    ):
        picked = _preview_brand_candidate(candidate)
        if picked:
            return picked
    return "Brand" if fallback else None


__all__ = [
    "apply_brief_to_plan",
    "brief_prompt_block",
    "build_brand_brief",
    "design_system_from_brief",
    "ensure_brand_brief",
    "resolve_preview_brand_name",
]
