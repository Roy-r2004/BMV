"""Stamp industry templates onto the experience plan — gap-fill only.

Packs never overwrite Product Face Contract fields. See
`docs/superpowers/specs/2026-07-23-product-face-contract-design.md`.
"""
from __future__ import annotations

import logging
from typing import Any

from app.application.preview_app.brand_brief import resolve_preview_brand_name
from app.application.preview_app.industry_templates.loader import get_template, pick_template_id
from app.application.preview_app.product_face import (
    ensure_product_face_on_plan,
    extract_product_face,
    gap_fill_ops_seed_from_pack,
    gap_fill_public_seed_from_pack,
    materialize_mock_seed,
)
from app.application.services.industry_images import resolve_industry_category

logger = logging.getLogger(__name__)

# Packs own layout, not subject: role values are framing that composes with the
# business-derived search subject in `services.industry_images`.
_ROLE_FRAMINGS: dict[str, str] = {
    "hero": "lifestyle wide atmosphere",
    "hero2": "interior workspace",
    "card1": "product detail close-up",
    "card2": "customer experience",
    "card3": "team service moment",
    "ambient": "ambient background texture",
}


def _resolve_plan_brand_name(
    plan: dict[str, Any] | None,
    brand_name: str | None,
) -> str | None:
    """When callers omit brand_name, pull from plan brief/concept before materialize."""
    plan = plan if isinstance(plan, dict) else {}
    brief = plan.get("brand_brief") if isinstance(plan.get("brand_brief"), dict) else None
    if not brief and isinstance(plan.get("design_brief"), dict):
        brief = plan["design_brief"]
    return resolve_preview_brand_name(
        brand_name=brand_name,
        brand_brief=brief,
        business_name=plan.get("business_name"),
        concept_name=plan.get("concept_name"),
        plan=plan,
        fallback=True,
    )


def _pack_category(pack: dict[str, Any]) -> str:
    tags = " ".join(str(t) for t in (pack.get("industry_tags") or []) if str(t).strip())
    label = str(pack.get("label") or pack.get("id") or "").strip()
    return resolve_industry_category(f"{tags} {label}")


def _pack_imagery_roles(pack: dict[str, Any], *, industry: str | None) -> dict[str, str]:
    """Role framings for a pack — an off-industry pack contributes no subject."""
    pack_category = _pack_category(pack)
    business_category = resolve_industry_category(industry or "")
    off_industry = pack_category != business_category and "generic" not in (
        pack_category,
        business_category,
    )
    if off_industry:
        logger.warning(
            "Industry pack %s reads as %s but business industry resolves to %s — "
            "imagery keeps the business subject, pack contributes framing only",
            pack.get("id"),
            pack_category,
            business_category,
        )
    roles = pack.get("imagery_roles") if isinstance(pack.get("imagery_roles"), dict) else None
    if not roles or off_industry:
        return dict(_ROLE_FRAMINGS)
    return {str(k): str(v).strip() for k, v in roles.items() if str(v).strip()}


def _stamp_pack_voice(updated: dict[str, Any], pack: dict[str, Any], *, key_prefix: str) -> None:
    hints = list(pack.get("prompt_hints") or [])
    moves = list(pack.get("signature_moves") or [])
    design = dict(updated.get("design_system") or {})
    template_prompt = " ".join(hints).strip()
    if moves:
        template_prompt = f"{template_prompt} Signature moves: {', '.join(moves)}.".strip()
    if template_prompt:
        design[f"{key_prefix}_prompt"] = template_prompt
        existing = str(design.get("recipe_prompt") or "").strip()
        design["recipe_prompt"] = (
            f"{existing} TEMPLATE {pack['id']}: {template_prompt}".strip()
        )
        direction = str(updated.get("design_direction") or "").strip()
        updated["design_direction"] = (
            f"{direction} | Template {pack.get('label')}: {template_prompt}".strip(" |")
        )
    if pack.get("section_order"):
        updated[f"{key_prefix}_section_order"] = list(pack["section_order"])
    if pack.get("recipe_hint"):
        design[f"{key_prefix}_recipe_hint"] = pack["recipe_hint"]
    updated["design_system"] = design


def apply_industry_template_to_plan(
    plan: dict[str, Any] | None,
    *,
    industry: str | None = None,
    seed: int | None = 0,
    surface: str = "public",
    context: str | None = None,
    brand_name: str | None = None,
) -> dict[str, Any]:
    """Attach template metadata; pack mock_seed only fills empty product_face slots."""
    brand_name = _resolve_plan_brand_name(plan, brand_name)
    # Extract/stamp without Brand defaults so packs see empty slots.
    updated = ensure_product_face_on_plan(
        plan, brand_name=brand_name, fill_defaults=False
    )
    kind = str(updated.get("product_kind") or "")
    if kind in {"saas_workspace", "internal_ops"}:
        surface = "ops"
    tid = pick_template_id(
        industry=industry or "",
        surface=surface,
        seed=int(seed or 0),
        context=context or "",
    )
    pack = get_template(tid)
    if not pack:
        face = extract_product_face(updated)
        updated["product_face"] = face
        updated["mock_seed"] = materialize_mock_seed(
            face, brand_name=brand_name, fill_defaults=True
        )
        return updated

    updated["industry_template_id"] = pack["id"]
    updated["industry_template_label"] = pack.get("label") or pack["id"]
    _stamp_pack_voice(updated, pack, key_prefix="template")
    if pack.get("section_order"):
        updated["template_section_order"] = list(pack["section_order"])
    if pack.get("recipe_hint"):
        design = dict(updated.get("design_system") or {})
        design["template_recipe_hint"] = pack["recipe_hint"]
        updated["design_system"] = design

    existing_imagery = dict(updated.get("imagery_roles") or {})
    # Imagery: fill missing keys only.
    for k, v in _pack_imagery_roles(pack, industry=industry).items():
        if k not in existing_imagery:
            existing_imagery[k] = v
    updated["imagery_roles"] = existing_imagery

    face = extract_product_face(updated)
    face = gap_fill_public_seed_from_pack(
        face,
        pack.get("mock_seed") if isinstance(pack.get("mock_seed"), dict) else None,
        brand_name=brand_name,
    )
    updated["product_face"] = face
    updated["mock_seed"] = materialize_mock_seed(
        face, brand_name=brand_name, fill_defaults=True
    )
    return updated


def apply_ops_industry_template_to_plan(
    plan: dict[str, Any] | None,
    *,
    industry: str | None = None,
    seed: int | None = 0,
    context: str | None = None,
    brand_name: str | None = None,
) -> dict[str, Any]:
    """Ops pack gap-fills empty ops_seed only — never overwrites contract KPIs/hero."""
    brand_name = _resolve_plan_brand_name(plan, brand_name)
    updated = ensure_product_face_on_plan(
        plan, brand_name=brand_name, fill_defaults=False
    )
    tid = pick_template_id(
        industry=industry or "",
        surface="ops",
        seed=int(seed or 0),
        context=context or "",
    )
    pack = get_template(tid)
    if not pack:
        face = extract_product_face(updated)
        updated["product_face"] = face
        updated["mock_seed"] = materialize_mock_seed(
            face, brand_name=brand_name, fill_defaults=True
        )
        return updated

    updated["ops_template_id"] = pack["id"]
    updated["ops_template_label"] = pack.get("label") or pack["id"]
    _stamp_pack_voice(updated, pack, key_prefix="ops_template")

    face = extract_product_face(updated)
    face = gap_fill_ops_seed_from_pack(
        face,
        pack.get("mock_seed") if isinstance(pack.get("mock_seed"), dict) else None,
        brand_name=brand_name,
    )
    updated["product_face"] = face
    updated["mock_seed"] = materialize_mock_seed(
        face, brand_name=brand_name, fill_defaults=True
    )

    existing = dict(updated.get("imagery_roles") or {})
    for k, v in _pack_imagery_roles(pack, industry=industry).items():
        if k not in existing:
            existing[k] = v
    updated["imagery_roles"] = existing
    return updated


def template_recipe_hint(
    *,
    industry: str | None = None,
    seed: int | None = 0,
    surface: str = "public",
    context: str | None = None,
) -> str | None:
    """Peek recipe hint before recipe apply (when brand has not locked a recipe)."""
    tid = pick_template_id(
        industry=industry or "",
        surface=surface,
        seed=int(seed or 0),
        context=context or "",
    )
    pack = get_template(tid)
    if not pack:
        return None
    hint = pack.get("recipe_hint")
    return str(hint) if hint else None
