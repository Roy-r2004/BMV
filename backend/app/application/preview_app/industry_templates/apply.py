"""Stamp a picked industry template onto the experience plan."""
from __future__ import annotations

from typing import Any

from app.application.preview_app.industry_templates.loader import get_template, pick_template_id
from app.application.preview_app.industry_templates.seed import normalize_mock_seed


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
    """Attach template metadata + prompt hints after recipe selection."""
    updated = dict(plan or {})
    tid = pick_template_id(
        industry=industry or "",
        surface=surface,
        seed=int(seed or 0),
        context=context or "",
    )
    pack = get_template(tid)
    if not pack:
        # Still emit a default seed so scaffolds can import `@/data/mock` seed.
        if "mock_seed" not in updated:
            updated["mock_seed"] = normalize_mock_seed(None)
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
    updated["imagery_roles"] = {
        str(k): str(v).strip()
        for k, v in (roles or _default_imagery_roles(pack)).items()
        if str(v).strip()
    }

    updated["mock_seed"] = normalize_mock_seed(
        pack.get("mock_seed") if isinstance(pack.get("mock_seed"), dict) else None
    )
    return updated


def apply_ops_industry_template_to_plan(
    plan: dict[str, Any] | None,
    *,
    industry: str | None = None,
    seed: int | None = 0,
    context: str | None = None,
) -> dict[str, Any]:
    """Stamp an ops pack alongside the public pack so owner/staff faces get voice + seed."""
    updated = dict(plan or {})
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

    ops_seed = normalize_mock_seed(
        pack.get("mock_seed") if isinstance(pack.get("mock_seed"), dict) else None
    )
    public_seed = dict(updated.get("mock_seed") or {})
    # Keep public marketing copy; merge ops-facing structures for dashboards.
    for key in ("kpis", "activity", "risk", "tableRows"):
        if ops_seed.get(key):
            public_seed[key] = ops_seed[key]
    if not public_seed.get("tone") or public_seed.get("tone") == "branded":
        # Prefer ops tone when public seed had no ops identity.
        if ops_seed.get("tone"):
            public_seed["opsTone"] = ops_seed["tone"]
    updated["mock_seed"] = public_seed

    # Ops packs rarely own hero photography; only fill missing imagery slots.
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
