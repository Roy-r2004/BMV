"""Sealed design brief — single authoritative design contract for codegen.

Plan phase historically piled product_kind / recipe / industry packs / brand /
overlay / architect notes into ``design_direction`` and ``recipe_prompt`` via
string concat. Downstream codegen (especially scaffold slot-fill) either ignored
that mush or contradicted itself.

``seal_design_brief`` collapses the stamped plan into one structured brief with
explicit precedence, then ``apply_sealed_brief_to_plan`` / ``_to_architect``
write clean fields the rest of the pipeline consumes.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from app.application.preview_app.design_recipes import get_recipe

BRIEF_VERSION = "1.0"


def _str(value: Any) -> str:
    return str(value or "").strip()


def _uniq_parts(*parts: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        text = _str(part)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _compose_direction(brief: Mapping[str, Any]) -> str:
    kind = _str(brief.get("product_kind"))
    subtype = _str(brief.get("product_subtype"))
    kind_label = f"{kind}/{subtype}" if kind and subtype else kind
    kind_note = _str(brief.get("product_kind_note"))
    kind_line = ""
    if kind_label and kind_note:
        kind_line = f"Product kind {kind_label}: {kind_note}"
    elif kind_note:
        kind_line = kind_note
    elif kind_label:
        kind_line = f"Product kind {kind_label}"

    recipe_label = _str(brief.get("recipe_label"))
    recipe_blurb = _str(brief.get("recipe_blurb"))
    recipe_line = ""
    if recipe_label and recipe_blurb:
        recipe_line = f"{recipe_label}: {recipe_blurb}"
    elif recipe_blurb:
        recipe_line = recipe_blurb
    elif recipe_label:
        recipe_line = recipe_label

    overlay_label = _str(brief.get("overlay_label"))
    overlay_blurb = _str(brief.get("overlay_blurb"))
    overlay_line = ""
    if overlay_label and overlay_blurb:
        overlay_line = f"{overlay_label}: {overlay_blurb}"
    elif overlay_blurb:
        overlay_line = overlay_blurb

    template_prompt = _str(brief.get("template_prompt"))
    template_line = f"Public template: {template_prompt}" if template_prompt else ""
    ops_prompt = _str(brief.get("ops_template_prompt"))
    ops_line = f"Ops template: {ops_prompt}" if ops_prompt else ""

    return " · ".join(
        _uniq_parts(
            _str(brief.get("signature")),
            recipe_line,
            overlay_line,
            template_line,
            ops_line,
            kind_line,
        )
    )


def seal_design_brief(
    plan: Mapping[str, Any] | None,
    *,
    brand_brief: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one sealed design brief from the post-stack experience plan.

    Precedence (later wins only within its lane):
    - product_kind → chrome / kind note
    - brand_brief → palette, locked type, voice, signature
    - recipe → composition variants + base recipe_prompt (never pack mush)
    - industry/ops packs → template prompts kept as separate fields
    - overlay → mood / density / atmosphere tokens; fonts only if not brand_locked
    """
    plan = dict(plan or {})
    design = dict(plan.get("design_system") or {})
    brand = dict(brand_brief or {})
    recipe_id = (
        _str(plan.get("recipe_id"))
        or _str(design.get("recipe_id"))
        or _str(brand.get("recipe_id"))
        or "editorial"
    )
    recipe = get_recipe(recipe_id)
    brand_locked = bool(design.get("brand_locked") or brand.get("locked"))

    palette = {
        "primary": design.get("primary_color") or (brand.get("palette") or {}).get("primary"),
        "secondary": design.get("secondary_color")
        or (brand.get("palette") or {}).get("secondary"),
        "background": design.get("background_color")
        or (brand.get("palette") or {}).get("background"),
        "surface": design.get("surface_color")
        or (brand.get("palette") or {}).get("surface"),
        "text": design.get("text_color") or (brand.get("palette") or {}).get("text"),
        "muted": design.get("muted_text_color")
        or (brand.get("palette") or {}).get("muted"),
    }
    typography = {
        "font_family": design.get("font_family")
        or (brand.get("typography") or {}).get("font_family"),
        "display_font_family": design.get("display_font_family")
        or (brand.get("typography") or {}).get("display_font_family"),
        "font_sans": design.get("font_sans")
        or (brand.get("typography") or {}).get("font_sans"),
        "font_display": design.get("font_display")
        or (brand.get("typography") or {}).get("font_display"),
        "font_import": design.get("font_import")
        or (brand.get("typography") or {}).get("font_import"),
        "font_import_url": design.get("font_import_url")
        or (brand.get("typography") or {}).get("font_import_url"),
    }

    kind_contract = plan.get("product_kind_contract")
    kind_contract = kind_contract if isinstance(kind_contract, dict) else {}
    kind = _str(plan.get("product_kind") or kind_contract.get("kind"))
    subtype = _str(
        plan.get("product_kind_subtype") or kind_contract.get("subtype")
    )
    kind_note = _str(kind_contract.get("design_note"))

    section_order = plan.get("template_section_order")
    if not isinstance(section_order, list):
        section_order = design.get("template_section_order")
    if not isinstance(section_order, list):
        section_order = []

    avoid = list(design.get("avoid") or brand.get("avoid") or [])
    rules = list(design.get("rules") or brand.get("rules") or [])
    # Deduplicate while preserving order.
    avoid = list(dict.fromkeys(_str(a) for a in avoid if _str(a)))
    rules = list(dict.fromkeys(_str(r) for r in rules if _str(r)))

    brief: dict[str, Any] = {
        "version": BRIEF_VERSION,
        "sealed": True,
        "brand_name": _str(brand.get("brand_name")) or None,
        "brand_locked": brand_locked,
        "recipe_id": recipe["id"],
        "recipe_label": _str(recipe.get("label")),
        "recipe_blurb": _str(recipe.get("blurb")),
        "recipe_prompt": _str(recipe.get("prompt")),
        "hub_variant": _str(
            plan.get("hub_variant")
            or design.get("hub_variant")
            or recipe.get("hub_variant")
        ),
        "hero_variant": _str(design.get("hero_variant") or recipe.get("hero_variant")),
        "feature_variant": _str(
            design.get("feature_variant") or recipe.get("feature_variant")
        ),
        "product_kind": kind or None,
        "product_subtype": subtype or None,
        "product_kind_note": kind_note or None,
        "industry_template_id": _str(plan.get("industry_template_id")) or None,
        "ops_template_id": _str(plan.get("ops_template_id")) or None,
        "template_prompt": _str(design.get("template_prompt")) or None,
        "ops_template_prompt": _str(design.get("ops_template_prompt")) or None,
        "overlay_id": _str(design.get("design_overlay_id")) or None,
        "overlay_label": _str(design.get("design_overlay_label")) or None,
        "overlay_blurb": _str(design.get("design_overlay_blurb")) or None,
        "density": _str(design.get("density")) or None,
        "mood": _str(design.get("mood") or brand.get("mood")) or None,
        "voice": _str(design.get("voice") or brand.get("voice")) or None,
        "signature": _str(design.get("signature") or brand.get("signature")) or None,
        "palette": palette,
        "typography": typography,
        "token_overrides": dict(design.get("token_overrides") or {}),
        "border_radius": design.get("border_radius"),
        "section_order": list(section_order),
        "avoid": avoid,
        "rules": rules,
        "style_keywords": _str(design.get("style_keywords")) or None,
    }
    brief["direction"] = _compose_direction(brief)
    return brief


def apply_sealed_brief_to_plan(
    plan: Mapping[str, Any] | None,
    brief: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Stamp the sealed brief onto plan as the only design authority."""
    updated = dict(plan or {})
    sealed = dict(brief or {})
    if not sealed.get("sealed"):
        return updated

    design = dict(updated.get("design_system") or {})
    palette = sealed.get("palette") or {}
    typography = sealed.get("typography") or {}

    design["recipe_id"] = sealed.get("recipe_id") or design.get("recipe_id")
    design["recipe_prompt"] = sealed.get("recipe_prompt") or ""
    design["hub_variant"] = sealed.get("hub_variant") or design.get("hub_variant")
    design["hero_variant"] = sealed.get("hero_variant") or design.get("hero_variant")
    design["feature_variant"] = sealed.get("feature_variant") or design.get(
        "feature_variant"
    )
    design["primary_color"] = palette.get("primary") or design.get("primary_color")
    design["secondary_color"] = palette.get("secondary") or design.get("secondary_color")
    design["background_color"] = palette.get("background") or design.get(
        "background_color"
    )
    design["surface_color"] = palette.get("surface") or design.get("surface_color")
    design["text_color"] = palette.get("text") or design.get("text_color")
    design["muted_text_color"] = palette.get("muted") or design.get("muted_text_color")
    design["font_family"] = typography.get("font_family") or design.get("font_family")
    design["display_font_family"] = typography.get("display_font_family") or design.get(
        "display_font_family"
    )
    design["font_sans"] = typography.get("font_sans") or design.get("font_sans")
    design["font_display"] = typography.get("font_display") or design.get("font_display")
    design["font_import"] = typography.get("font_import") or design.get("font_import")
    design["font_import_url"] = typography.get("font_import_url") or design.get(
        "font_import_url"
    )
    design["brand_locked"] = bool(sealed.get("brand_locked"))
    design["mood"] = sealed.get("mood")
    design["voice"] = sealed.get("voice")
    design["signature"] = sealed.get("signature")
    design["avoid"] = list(sealed.get("avoid") or [])
    design["rules"] = list(sealed.get("rules") or [])
    design["density"] = sealed.get("density")
    design["style_keywords"] = sealed.get("style_keywords")
    if sealed.get("border_radius"):
        design["border_radius"] = sealed["border_radius"]
    if sealed.get("token_overrides"):
        design["token_overrides"] = dict(sealed["token_overrides"])
    if sealed.get("overlay_id"):
        design["design_overlay_id"] = sealed["overlay_id"]
        design["design_overlay_label"] = sealed.get("overlay_label")
        design["design_overlay_blurb"] = sealed.get("overlay_blurb")
    # Keep pack prompts as structured fields — never re-mash into recipe_prompt.
    if sealed.get("template_prompt"):
        design["template_prompt"] = sealed["template_prompt"]
    if sealed.get("ops_template_prompt"):
        design["ops_template_prompt"] = sealed["ops_template_prompt"]
    design["design_brief_version"] = sealed.get("version")
    design["design_brief_sealed"] = True

    updated["design_system"] = design
    updated["design_brief"] = sealed
    updated["recipe_id"] = sealed.get("recipe_id") or updated.get("recipe_id")
    updated["hub_variant"] = sealed.get("hub_variant") or updated.get("hub_variant")
    updated["design_direction"] = _str(sealed.get("direction"))
    return updated


def apply_sealed_brief_to_architect(
    architect: Mapping[str, Any] | None,
    brief: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Force architect design_direction / recipe ids from the sealed brief."""
    updated = dict(architect or {})
    sealed = dict(brief or {})
    if not sealed.get("sealed"):
        return updated
    updated["design_direction"] = _str(sealed.get("direction"))
    if sealed.get("recipe_id"):
        updated["recipe_id"] = sealed["recipe_id"]
    if sealed.get("hub_variant"):
        updated["hub_variant"] = sealed["hub_variant"]
    if sealed.get("product_kind"):
        updated.setdefault("product_kind", sealed["product_kind"])
    if sealed.get("product_subtype"):
        updated.setdefault("product_kind_subtype", sealed["product_subtype"])
    updated["design_brief"] = sealed
    return updated


def design_brief_prompt_block(brief: Mapping[str, Any] | None) -> str:
    """Compact prompt block for freeform + slot-fill codegen."""
    if not brief or not brief.get("sealed"):
        return ""
    payload = {
        "version": brief.get("version"),
        "sealed": True,
        "brand_name": brief.get("brand_name"),
        "brand_locked": brief.get("brand_locked"),
        "recipe_id": brief.get("recipe_id"),
        "hub_variant": brief.get("hub_variant"),
        "product_kind": brief.get("product_kind"),
        "product_subtype": brief.get("product_subtype"),
        "overlay_id": brief.get("overlay_id"),
        "industry_template_id": brief.get("industry_template_id"),
        "ops_template_id": brief.get("ops_template_id"),
        "mood": brief.get("mood"),
        "voice": brief.get("voice"),
        "signature": brief.get("signature"),
        "density": brief.get("density"),
        "direction": brief.get("direction"),
        "recipe_prompt": brief.get("recipe_prompt"),
        "template_prompt": brief.get("template_prompt"),
        "ops_template_prompt": brief.get("ops_template_prompt"),
        "palette": brief.get("palette"),
        "typography": {
            "font_family": (brief.get("typography") or {}).get("font_family"),
            "display_font_family": (brief.get("typography") or {}).get(
                "display_font_family"
            ),
        },
        "avoid": brief.get("avoid") or [],
        "rules": brief.get("rules") or [],
    }
    return (
        "=== SEALED DESIGN BRIEF (SINGLE AUTHORITY — NON-NEGOTIABLE) ===\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        "- Do NOT invent a second palette, type stack, mood, or chrome.\n"
        "- Do NOT contradict recipe_prompt / template_prompt / direction.\n"
        "- Inherit tokens via bg-brand / text-brand / font-display only.\n"
    )


def resolve_design_brief(
    plan: Mapping[str, Any] | None = None,
    architect: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Prefer an already-sealed brief on plan or architect."""
    for source in (plan, architect):
        if not isinstance(source, Mapping):
            continue
        brief = source.get("design_brief")
        if isinstance(brief, dict) and brief.get("sealed"):
            return brief
    return None


__all__ = [
    "BRIEF_VERSION",
    "apply_sealed_brief_to_architect",
    "apply_sealed_brief_to_plan",
    "design_brief_prompt_block",
    "resolve_design_brief",
    "seal_design_brief",
]
