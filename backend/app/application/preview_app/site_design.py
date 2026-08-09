"""SiteSpec.design — the single Python resolution of the site's design axes.

Session 25 autopsied three systems fighting over ten variables (recipe kit
tokens, the per-request overlay, the locked brand brief), with the merge
re-implemented inline in ``assemble.write_index_css`` and the losing lanes
still present in code. Stage A collapses that: ``resolve_site_design`` is the
ONE place the fight is settled, ``write_index_css`` renders its result, and
the workspace receives the resolved object verbatim (``src/lib/site-design.ts``)
so the template can consume design values instead of hard-coding them.

The resolution is byte-compatible with the pre-Stage-A merge: overlay
``token_overrides`` win over recipe kit tokens, the brand brief's fonts win
over the recipe's, the locked palette wins over caller-supplied colors, and
the render-time defaults are unchanged. Stage A is plumbing — if this module
changes what any recipe looks like, that is a Stage A defect.

The new axes (type ramp, spacing scale, container width, grid logic, image
treatment) are explicit placeholders: today's template constants stated once,
identical for every recipe until Stage D varies them. Motion identity (3.10)
is live: each recipe authors its temperament in ``design_recipes.RECIPES``
and it ships through this resolution.
"""
from __future__ import annotations

import json
from typing import Any

from app.application.preview_app.theme import sanitize_theme_inputs

SITE_DESIGN_VERSION = "1.1"

#: Today's implicit template constants, stated explicitly. Every recipe shares
#: these values until Stage D introduces per-recipe variation; the numbers are
#: the audited hard-codes (max-w-[92rem]; px-6 py-28 lg:px-12 lg:py-36).
_PLACEHOLDER_AXES: dict[str, Any] = {
    "type_ramp": {
        # The authored six-step ramp lands in 3.0/3.3; today the kit renders
        # Tailwind's default scale plus per-component clamps.
        "source": "tailwind-default",
        "steps": None,
    },
    "spacing": {
        "section_x": "1.5rem",
        "section_x_lg": "3rem",
        "section_y": "7rem",
        "section_y_lg": "9rem",
    },
    "container": {"max": "92rem"},
    "grid": {"catalog_archetype": "uniform"},
    "image_treatment": {"policy": "cover"},
    # Fallback only — every RECIPES entry authors its own motion identity
    # (3.10); this shape covers bare/custom recipe dicts.
    "motion": {
        "identity": "entrance-only",
        "ease": None,
        "stagger_ms": None,
        "travel": None,
        "reveal": None,
    },
}

_TOKEN_DEFAULTS: dict[str, str] = {
    "radius_ui": "0.75rem",
    "bg_mix": "4%",
    "fg_mix": "32%",
    "muted_mix": "30%",
    "border_mix": "16%",
    "shadow": "0 24px 50px -36px",
    "shadow_alpha": "35%",
    "glow": "12%",
    "card": "white",
    "atmosphere": (
        "radial-gradient(120% 80% at 0% 0%, "
        "color-mix(in srgb, var(--color-brand) 10%, transparent), transparent 50%)"
    ),
}


def resolve_site_design(
    *,
    design_system: dict | None,
    recipe: dict | None,
    primary: str | None,
    secondary: str | None,
    font: str | None,
) -> dict[str, Any]:
    """Resolve every design axis once. Returns the complete SiteSpec.design.

    Precedence, stated once: recipe kit tokens are the base; the overlay's
    ``token_overrides`` replace them; the design_system's fonts (the locked
    brand brief's lane) replace the recipe's; the locked palette replaces the
    caller-supplied colors. Missing values fall back to the same defaults the
    renderer always used.
    """
    from app.application.preview_app.design_recipes import get_recipe

    primary, secondary, font_family = sanitize_theme_inputs(primary, secondary, font)
    resolved = dict(recipe or get_recipe(None))
    tokens = dict(resolved.get("tokens") or {})
    fonts = dict(resolved.get("fonts") or {})
    ds = design_system or {}

    overrides = ds.get("token_overrides")
    if isinstance(overrides, dict):
        tokens.update({k: v for k, v in overrides.items() if v is not None})
    if ds.get("font_sans"):
        fonts["sans"] = ds["font_sans"]
    if ds.get("font_display"):
        fonts["display"] = ds["font_display"]
    if ds.get("font_import"):
        fonts["import"] = ds["font_import"]
    if ds.get("font_family"):
        font_family = str(ds["font_family"])
    if ds.get("brand_locked"):
        if ds.get("primary_color"):
            primary = str(ds["primary_color"])
        if ds.get("secondary_color"):
            secondary = str(ds["secondary_color"])

    # Full @import statement (or "") — both pre-Stage-A branches reduced to
    # this: they only ever differed when fonts["import"] was falsy, and then
    # both produced "".
    font_import = (
        "@import url(\"https://fonts.googleapis.com/css2?family="
        f"{fonts.get('import')}&display=swap\");"
        if fonts.get("import")
        else ""
    )

    chrome = dict(resolved.get("chrome") or {})
    design: dict[str, Any] = {
        "version": SITE_DESIGN_VERSION,
        "recipe_id": resolved.get("id") or "warm-service",
        "palette": {"primary": primary, "secondary": secondary},
        "typography": {
            "font_family": font_family,
            "font_sans": fonts.get("sans") or font_family,
            "font_display": fonts.get("display") or fonts.get("sans") or font_family,
            "font_import": font_import,
        },
        "tokens": {
            key: tokens.get(key) or default for key, default in _TOKEN_DEFAULTS.items()
        },
        "variants": {
            "hero": ds.get("hero_variant") or resolved.get("hero_variant") or None,
            "feature": ds.get("feature_variant") or resolved.get("feature_variant") or None,
            "shell": ds.get("shell_chrome") or chrome.get("shell") or None,
            "nav": ds.get("nav_variant") or chrome.get("nav") or None,
            "footer": ds.get("footer_variant") or chrome.get("footer") or None,
            "brand_placement": ds.get("brand_placement") or chrome.get("brand") or None,
        },
        "density": ds.get("density") or None,
    }
    for axis, value in _PLACEHOLDER_AXES.items():
        design[axis] = json.loads(json.dumps(value))
    # Motion identity (3.10) is per-recipe, not a shared placeholder: the
    # recipe's authored temperament ships whenever the recipe declares one.
    recipe_motion = resolved.get("motion")
    if isinstance(recipe_motion, dict):
        design["motion"] = json.loads(json.dumps(recipe_motion))
    return design


def css_render_context(design: dict[str, Any]) -> dict[str, Any]:
    """Map a resolved SiteSpec.design onto index_css.j2's parameters."""
    palette = design["palette"]
    typography = design["typography"]
    tokens = design["tokens"]
    return {
        "primary": palette["primary"],
        "secondary": palette["secondary"],
        "font_family": typography["font_family"],
        "font_sans": typography["font_sans"],
        "font_display": typography["font_display"],
        "font_import": typography["font_import"],
        "radius_ui": tokens["radius_ui"],
        "bg_mix": tokens["bg_mix"],
        "fg_mix": tokens["fg_mix"],
        "muted_mix": tokens["muted_mix"],
        "border_mix": tokens["border_mix"],
        "shadow_ui": tokens["shadow"],
        "shadow_alpha": tokens["shadow_alpha"],
        "glow": tokens["glow"],
        "card_color": tokens["card"],
        "atmosphere": tokens["atmosphere"],
        "recipe_id": design["recipe_id"],
    }


_SITE_DESIGN_TS_INTERFACE = """export interface SiteDesign {
  version: string;
  recipe_id: string;
  palette: { primary: string; secondary: string };
  typography: {
    font_family: string;
    font_sans: string;
    font_display: string;
    font_import: string;
  };
  tokens: {
    radius_ui: string;
    bg_mix: string;
    fg_mix: string;
    muted_mix: string;
    border_mix: string;
    shadow: string;
    shadow_alpha: string;
    glow: string;
    card: string;
    atmosphere: string;
  };
  variants: {
    hero: string | null;
    feature: string | null;
    shell: string | null;
    nav: string | null;
    footer: string | null;
    brand_placement: string | null;
  };
  density: string | null;
  type_ramp: { source: string; steps: null };
  spacing: {
    section_x: string;
    section_x_lg: string;
    section_y: string;
    section_y_lg: string;
  };
  container: { max: string };
  grid: { catalog_archetype: string };
  image_treatment: { policy: string };
  motion: {
    identity: string;
    ease: number[] | null;
    stagger_ms: number | null;
    travel: string | null;
    reveal: string | null;
  };
}"""


def site_design_ts(design: dict[str, Any]) -> str:
    """Self-contained TS module for the workspace (and the template default)."""
    return (
        "/** SiteSpec.design — resolved once in Python (site_design.py)."
        " Overwritten per preview by write_index_css. */\n"
        f"{_SITE_DESIGN_TS_INTERFACE}\n\n"
        "export const SITE_DESIGN: SiteDesign = "
        f"{json.dumps(design, indent=2, ensure_ascii=False)};\n"
    )


__all__ = [
    "SITE_DESIGN_VERSION",
    "css_render_context",
    "resolve_site_design",
    "site_design_ts",
]
