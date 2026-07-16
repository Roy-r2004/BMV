"""Design recipes — composition + token leans so businesses don't share one look."""
from __future__ import annotations

import re
from typing import Any


RECIPES: dict[str, dict[str, Any]] = {
    "editorial": {
        "id": "editorial",
        "label": "Editorial",
        "blurb": "Gallery pacing, large display type, airy whitespace, soft surfaces.",
        "hub_variant": "marketing",
        "fonts": {
            "sans": '"Source Sans 3", "Segoe UI", sans-serif',
            "display": '"Fraunces", Georgia, serif',
            "import": "Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,600;1,9..144,500&family=Source+Sans+3:wght@400;500;600;700",
        },
        "tokens": {
            "radius_ui": "0.35rem",
            "bg_mix": "3%",
            "fg_mix": "42%",
            "muted_mix": "28%",
            "border_mix": "12%",
            "shadow": "0 30px 60px -42px",
            "shadow_alpha": "28%",
            "glow": "8%",
            "card": "#fffdf8",
            "atmosphere": "radial-gradient(120% 80% at 10% 0%, color-mix(in srgb, var(--color-brand) 10%, transparent), transparent 55%)",
        },
        "hero_variant": "cinematic",
        "feature_variant": "alternating",
        "section_orders": {
            "public-home": [
                "hero",
                "credentials",
                "showcase",
                "features",
                "process",
                "testimonials",
                "cta",
                "footer",
            ],
            "public-service": ["hero", "process", "features", "testimonials", "cta", "footer"],
            "public-detail": ["hero", "showcase", "process", "testimonials", "cta", "footer"],
        },
        "prompt": (
            "RECIPE editorial: generous whitespace, serif/display headlines via font-display, "
            "fewer cards, longer subcopy, cinematic imagery, avoid dense tables on public pages."
        ),
        "industry_keywords": (
            "spa salon beauty wellness clinic dental law legal architect interior boutique "
            "jewelry gallery hotel hospitality yoga pilates"
        ),
    },
    "dense-ops": {
        "id": "dense-ops",
        "label": "Dense ops",
        "blurb": "Compact, utility-first, data-forward surfaces with tight rhythm.",
        "hub_variant": "app",
        "fonts": {
            "sans": '"IBM Plex Sans", "Segoe UI", sans-serif',
            "display": '"IBM Plex Sans", "Segoe UI", sans-serif',
            "import": "IBM+Plex+Sans:wght@400;500;600;700",
        },
        "tokens": {
            "radius_ui": "0.45rem",
            "bg_mix": "6%",
            "fg_mix": "38%",
            "muted_mix": "32%",
            "border_mix": "22%",
            "shadow": "0 12px 28px -22px",
            "shadow_alpha": "40%",
            "glow": "4%",
            "card": "#ffffff",
            "atmosphere": "linear-gradient(180deg, color-mix(in srgb, var(--color-brand) 6%, #f8fafc), #f1f5f9)",
        },
        "hero_variant": "compact",
        "feature_variant": "grid",
        "section_orders": {
            "public-home": [
                "hero",
                "features",
                "results",
                "process",
                "showcase",
                "cta",
                "footer",
            ],
            "public-service": ["hero", "features", "process", "cta", "footer"],
            "public-detail": ["hero", "features", "showcase", "process", "cta", "footer"],
            "ops-dashboard": ["header", "kpis", "filters", "table", "chart", "activity", "risk"],
        },
        "prompt": (
            "RECIPE dense-ops: compact spacing, short labels, KPI-first, grid features, "
            "compact utility heroes, minimal flourish, prioritize scannable lists and metrics."
        ),
        "industry_keywords": (
            "logistics fleet warehouse saas b2b software accounting payroll hr staffing "
            "agency operations manufacturing industrial"
        ),
    },
    "warm-service": {
        "id": "warm-service",
        "label": "Warm service",
        "blurb": "Approachable service brand — soft panels, process clarity, trust cues.",
        "hub_variant": "marketing",
        "fonts": {
            "sans": '"Nunito Sans", "Segoe UI", sans-serif',
            "display": '"Libre Baskerville", Georgia, serif',
            "import": "Libre+Baskerville:ital,wght@0,400;0,700;1,400&family=Nunito+Sans:wght@400;500;600;700",
        },
        "tokens": {
            "radius_ui": "1rem",
            "bg_mix": "5%",
            "fg_mix": "34%",
            "muted_mix": "30%",
            "border_mix": "14%",
            "shadow": "0 22px 44px -34px",
            "shadow_alpha": "32%",
            "glow": "14%",
            "card": "#fffaf5",
            "atmosphere": "radial-gradient(90% 60% at 90% 10%, color-mix(in srgb, var(--color-brand) 14%, transparent), transparent 50%)",
        },
        "hero_variant": "service",
        "feature_variant": "bento",
        "section_orders": {
            "public-home": [
                "hero",
                "trust",
                "features",
                "process",
                "testimonials",
                "booking",
                "cta",
                "footer",
            ],
            "public-service": ["hero", "features", "process", "testimonials", "cta", "footer"],
            "public-booking": ["hero", "credentials", "process", "booking", "footer"],
            "public-detail": ["hero", "process", "showcase", "testimonials", "cta", "footer"],
        },
        "prompt": (
            "RECIPE warm-service: friendly tone, rounded corners, trust/process before hard sell, "
            "bento features, offer-first service hero (headline bigger than brand), soft card surfaces."
        ),
        "industry_keywords": (
            "fitness gym studio coaching tutoring education childcare pet veterinary "
            "home cleaning repair handyman cafe bakery restaurant food"
        ),
    },
    "bold-retail": {
        "id": "bold-retail",
        "label": "Bold retail",
        "blurb": "High-contrast merchandising — product first, punchy CTAs, tight marketing stack.",
        "hub_variant": "marketing",
        "fonts": {
            "sans": '"Space Grotesk", "Segoe UI", sans-serif',
            "display": '"Syne", "Space Grotesk", sans-serif',
            "import": "Space+Grotesk:wght@400;500;600;700&family=Syne:wght@500;600;700;800",
        },
        "tokens": {
            "radius_ui": "0.15rem",
            "bg_mix": "2%",
            "fg_mix": "52%",
            "muted_mix": "26%",
            "border_mix": "18%",
            "shadow": "0 28px 55px -34px",
            "shadow_alpha": "50%",
            "glow": "18%",
            "card": "#ffffff",
            "atmosphere": "radial-gradient(90% 70% at 80% 0%, color-mix(in srgb, var(--color-brand) 22%, transparent), transparent 55%), linear-gradient(180deg, #0b0d10 0%, transparent 28%)",
        },
        "hero_variant": "product",
        "feature_variant": "bento",
        "section_orders": {
            "public-home": [
                "hero",
                "showcase",
                "features",
                "results",
                "testimonials",
                "cta",
                "footer",
            ],
            "public-service": ["hero", "showcase", "features", "cta", "footer"],
            "public-detail": ["hero", "showcase", "features", "cta", "footer"],
        },
        "prompt": (
            "RECIPE bold-retail: product/showcase first, sharp corners, high-contrast type, "
            "short punchy copy, strong CTAs, avoid long process essays on the home page."
        ),
        "industry_keywords": (
            "retail ecommerce fashion apparel store shop marketplace real estate property "
            "automotive car dealership electronics"
        ),
    },
}


def list_recipes() -> list[dict[str, Any]]:
    return [
        {
            "id": recipe["id"],
            "label": recipe["label"],
            "blurb": recipe["blurb"],
            "hub_variant": recipe["hub_variant"],
        }
        for recipe in RECIPES.values()
    ]


def get_recipe(recipe_id: str | None) -> dict[str, Any]:
    if recipe_id and recipe_id in RECIPES:
        return RECIPES[recipe_id]
    return RECIPES["warm-service"]


def pick_recipe_id(
    industry: str | None = None,
    business_description: str | None = None,
    concept_name: str | None = None,
    seed: int | None = None,
) -> str:
    """Pick a recipe from industry/description keywords; stable tie-break via seed."""
    blob = " ".join(
        part for part in (industry or "", business_description or "", concept_name or "") if part
    ).lower()
    scores: dict[str, int] = {recipe_id: 0 for recipe_id in RECIPES}
    for recipe_id, recipe in RECIPES.items():
        for token in str(recipe.get("industry_keywords") or "").split():
            if token and token in blob:
                scores[recipe_id] += 2
    best = max(scores.values())
    if best <= 0:
        # Deterministic rotation so consecutive businesses don't all look identical.
        order = list(RECIPES.keys())
        return order[(seed or 0) % len(order)]
    winners = [recipe_id for recipe_id, score in scores.items() if score == best]
    if len(winners) == 1:
        return winners[0]
    return winners[(seed or 0) % len(winners)]


def apply_recipe_to_plan(
    plan: dict[str, Any],
    *,
    industry: str | None = None,
    business_description: str | None = None,
    concept_name: str | None = None,
    seed: int | None = None,
    recipe_id: str | None = None,
) -> dict[str, Any]:
    """Stamp recipe_id + token leans onto the experience plan (mutates a shallow copy)."""
    updated = dict(plan or {})
    chosen = recipe_id or pick_recipe_id(
        industry=industry,
        business_description=business_description,
        concept_name=concept_name,
        seed=seed,
    )
    recipe = get_recipe(chosen)
    design = dict(updated.get("design_system") or {})
    fonts = recipe["fonts"]
    tokens = recipe["tokens"]
    brand_locked = bool(design.get("brand_locked"))
    design["recipe_id"] = recipe["id"]
    design["hub_variant"] = recipe["hub_variant"]
    # Recipe owns composition; a locked brand brief owns palette + type.
    if not brand_locked:
        design["font_family"] = fonts["sans"].split(",")[0].strip().strip('"')
        design["display_font_family"] = fonts["display"].split(",")[0].strip().strip('"')
        design["font_import_url"] = (
            "https://fonts.googleapis.com/css2?family="
            + fonts["import"]
            + "&display=swap"
        )
    design["border_radius"] = tokens["radius_ui"]
    design["style_keywords"] = recipe["label"]
    design["hero_variant"] = recipe["hero_variant"]
    design["feature_variant"] = recipe["feature_variant"]
    design["recipe_prompt"] = recipe["prompt"]
    updated["design_system"] = design
    updated["recipe_id"] = recipe["id"]
    updated["hub_variant"] = recipe["hub_variant"]
    updated["design_direction"] = (
        f"{recipe['label']}: {recipe['blurb']} {recipe['prompt']}"
    ).strip()
    return updated


def recipe_section_slots(skeleton_id: str, recipe: dict[str, Any], current: list[str]) -> list[str]:
    """Reorder (and optionally enrich) slots using the recipe's preferred order."""
    preferred = list((recipe.get("section_orders") or {}).get(skeleton_id) or [])
    if not preferred:
        return current
    current_set = set(current)
    ordered = [slot for slot in preferred if slot in current_set]
    # Keep any assigned slots the recipe didn't mention (stable append).
    for slot in current:
        if slot not in ordered:
            ordered.append(slot)
    return ordered


def apply_recipe_to_architect(architect: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """Apply recipe section orders + hub variant hints onto catalogue routes."""
    updated = dict(architect or {})
    recipe = get_recipe(plan.get("recipe_id") or (plan.get("design_system") or {}).get("recipe_id"))
    hub = str(plan.get("hub_variant") or recipe.get("hub_variant") or "marketing")
    routes = []
    for route in updated.get("routes") or []:
        item = dict(route)
        skeleton_id = str(item.get("skeleton_id") or "")
        slots = list(item.get("section_slots") or [])
        if skeleton_id and slots:
            item["section_slots"] = recipe_section_slots(skeleton_id, recipe, slots)
        path = str(item.get("path") or "")
        role = str(item.get("role_id") or "").lower()
        memberish = path.startswith("/member") or (
            role == "member"
            and any(token in path for token in ("dashboard", "history", "profile", "account"))
        )
        if hub == "app" and memberish:
            item["hub_variant"] = "app"
            # Prefer denser detail composition for member hubs.
            if skeleton_id == "public-detail":
                item["section_slots"] = recipe_section_slots(
                    "public-detail",
                    recipe,
                    item.get("section_slots") or ["hero", "showcase", "process", "cta", "footer"],
                )
        elif memberish:
            item["hub_variant"] = hub
        else:
            item["hub_variant"] = item.get("hub_variant") or hub
        routes.append(item)
    updated["routes"] = routes
    updated["recipe_id"] = recipe["id"]
    updated["hub_variant"] = hub
    direction = str(updated.get("design_direction") or "").strip()
    recipe_line = str(recipe.get("prompt") or "")
    if recipe_line and recipe_line not in direction:
        updated["design_direction"] = f"{direction} {recipe_line}".strip()
    return updated


def recipe_font_import_css(recipe: dict[str, Any]) -> str:
    fonts = recipe.get("fonts") or {}
    family = fonts.get("import")
    if not family:
        return ""
    return (
        '@import url("https://fonts.googleapis.com/css2?family='
        + family
        + '&display=swap");\n'
    )


_HEX_RE = re.compile(r"^#?[0-9a-fA-F]{3,8}$")


def sanitize_recipe_id(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = str(value).strip().lower()
    return cleaned if cleaned in RECIPES else None
