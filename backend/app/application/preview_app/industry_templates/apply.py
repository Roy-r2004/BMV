"""Stamp a picked industry template onto the experience plan."""
from __future__ import annotations

from typing import Any

from app.application.preview_app.industry_templates.loader import get_template, pick_template_id
from app.application.preview_app.industry_templates.seed import normalize_mock_seed


def apply_industry_template_to_plan(
    plan: dict[str, Any] | None,
    *,
    industry: str | None = None,
    seed: int | None = 0,
    surface: str = "public",
) -> dict[str, Any]:
    """Attach template metadata + prompt hints after recipe selection."""
    updated = dict(plan or {})
    tid = pick_template_id(industry=industry or "", surface=surface, seed=int(seed or 0))
    pack = get_template(tid)
    if not pack:
        # Still emit a default seed so scaffolds can import `@/data/mock` seed.
        if "mock_seed" not in updated:
            updated["mock_seed"] = normalize_mock_seed(None)
        return updated

    updated["industry_template_id"] = pack["id"]
    updated["industry_template_label"] = pack.get("label") or pack["id"]
    hints = list(pack.get("prompt_hints") or [])
    moves = list(pack.get("signature_moves") or [])
    design = dict(updated.get("design_system") or {})
    template_prompt = " ".join(hints).strip()
    if moves:
        template_prompt = f"{template_prompt} Signature moves: {', '.join(moves)}.".strip()
    if template_prompt:
        design["template_prompt"] = template_prompt
        existing = str(design.get("recipe_prompt") or "").strip()
        design["recipe_prompt"] = f"{existing} TEMPLATE {pack['id']}: {template_prompt}".strip()
        direction = str(updated.get("design_direction") or "").strip()
        updated["design_direction"] = (
            f"{direction} | Template {pack.get('label')}: {template_prompt}".strip(" |")
        )
    if pack.get("section_order"):
        updated["template_section_order"] = list(pack["section_order"])
    if pack.get("recipe_hint"):
        design["template_recipe_hint"] = pack["recipe_hint"]
    updated["design_system"] = design
    updated["mock_seed"] = normalize_mock_seed(
        pack.get("mock_seed") if isinstance(pack.get("mock_seed"), dict) else None
    )
    return updated


def template_recipe_hint(
    *,
    industry: str | None = None,
    seed: int | None = 0,
    surface: str = "public",
) -> str | None:
    """Peek recipe hint before recipe apply (when brand has not locked a recipe)."""
    tid = pick_template_id(industry=industry or "", surface=surface, seed=int(seed or 0))
    pack = get_template(tid)
    if not pack:
        return None
    hint = pack.get("recipe_hint")
    return str(hint) if hint else None
