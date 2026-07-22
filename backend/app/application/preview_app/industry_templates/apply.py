"""Stamp industry templates onto the experience plan — gap-fill only.

Packs never overwrite Product Face Contract fields. See
`docs/superpowers/specs/2026-07-23-product-face-contract-design.md`.
"""
from __future__ import annotations

from typing import Any

from app.application.preview_app.industry_templates.loader import get_template, pick_template_id
from app.application.preview_app.industry_templates.seed import normalize_mock_seed
from app.application.preview_app.product_face import (
    ensure_product_face_on_plan,
    extract_product_face,
    gap_fill_ops_seed_from_pack,
    gap_fill_public_seed_from_pack,
    materialize_mock_seed,
)


def _default_imagery_roles(pack: dict[str, Any]) -> dict[str, str]:
    tags = " ".join(str(t) for t in (pack.get("industry_tags") or []) if str(t).strip())
    label = str(pack.get("label") or pack.get("id") or "business").strip()
    base = (tags or label).strip() or "professional small business"
    return {
        "hero": f"{base} lifestyle wide atmosphere",
        "hero2": f"{base} interior workspace",
        "card1": f"{base} product detail close-up",
        "card2": f"{base} customer experience",
        "card3": f"{base} team service moment",
        "ambient": f"{base} ambient background texture",
    }


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
) -> dict[str, Any]:
    """Attach template metadata; pack mock_seed only fills empty product_face slots."""
    updated = ensure_product_face_on_plan(plan)
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
        if "mock_seed" not in updated:
            updated["mock_seed"] = materialize_mock_seed(extract_product_face(updated))
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

    roles = pack.get("imagery_roles") if isinstance(pack.get("imagery_roles"), dict) else None
    existing_imagery = dict(updated.get("imagery_roles") or {})
    defaults = {
        str(k): str(v).strip()
        for k, v in (roles or _default_imagery_roles(pack)).items()
        if str(v).strip()
    }
    # Imagery: fill missing keys only.
    for k, v in defaults.items():
        if k not in existing_imagery:
            existing_imagery[k] = v
    updated["imagery_roles"] = existing_imagery

    face = extract_product_face(updated)
    face = gap_fill_public_seed_from_pack(
        face,
        pack.get("mock_seed") if isinstance(pack.get("mock_seed"), dict) else None,
    )
    updated["product_face"] = face
    updated["mock_seed"] = materialize_mock_seed(face)
    return updated


def apply_ops_industry_template_to_plan(
    plan: dict[str, Any] | None,
    *,
    industry: str | None = None,
    seed: int | None = 0,
    context: str | None = None,
) -> dict[str, Any]:
    """Ops pack gap-fills empty ops_seed only — never overwrites contract KPIs/hero."""
    updated = ensure_product_face_on_plan(plan)
    tid = pick_template_id(
        industry=industry or "",
        surface="ops",
        seed=int(seed or 0),
        context=context or "",
    )
    pack = get_template(tid)
    if not pack:
        return updated

    updated["ops_template_id"] = pack["id"]
    updated["ops_template_label"] = pack.get("label") or pack["id"]
    _stamp_pack_voice(updated, pack, key_prefix="ops_template")

    face = extract_product_face(updated)
    face = gap_fill_ops_seed_from_pack(
        face,
        pack.get("mock_seed") if isinstance(pack.get("mock_seed"), dict) else None,
    )
    updated["product_face"] = face
    updated["mock_seed"] = materialize_mock_seed(face)

    roles = pack.get("imagery_roles") if isinstance(pack.get("imagery_roles"), dict) else None
    if roles:
        existing = dict(updated.get("imagery_roles") or {})
        for k, v in roles.items():
            if str(v).strip() and k not in existing:
                existing[str(k)] = str(v).strip()
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
