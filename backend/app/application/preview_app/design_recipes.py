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
            "bg_mix": "4%",
            "fg_mix": "44%",
            "muted_mix": "30%",
            "border_mix": "14%",
            "shadow": "0 36px 70px -40px",
            "shadow_alpha": "34%",
            "glow": "12%",
            "card": "#fffdf8",
            "atmosphere": (
                "radial-gradient(120% 80% at 8% -10%, color-mix(in srgb, var(--color-brand) 16%, transparent), transparent 58%), "
                "radial-gradient(70% 55% at 92% 8%, color-mix(in srgb, var(--color-accent) 10%, transparent), transparent 52%), "
                "linear-gradient(180deg, color-mix(in srgb, var(--color-brand) 3%, #fffdf8), transparent 42%)"
            ),
        },
        "hero_variant": "editorial",
        "feature_variant": "alternating",
        "chrome": {
            "shell": "immersive",
            "nav": "default",
            "footer": "statement",
            "brand": "center",
        },
        "section_orders": {
            "public-home": [
                "hero",
                "credentials",
                "showcase",
                "testimonials",
                "cta",
                "footer",
            ],
            "public-service": ["hero", "credentials", "features", "testimonials", "cta", "footer"],
            "public-booking": ["hero", "credentials", "booking", "footer"],
            "public-detail": ["hero", "credentials", "showcase", "testimonials", "cta", "footer"],
        },
        "prompt": (
            "RECIPE editorial: generous whitespace, serif/display headlines via font-display, "
            "fewer cards, longer subcopy, cinematic imagery with kenburns/grain, "
            "layered atmosphere, avoid dense tables on public pages, motion on every major section."
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
            "radius_ui": "0.5rem",
            "bg_mix": "7%",
            "fg_mix": "40%",
            "muted_mix": "32%",
            "border_mix": "20%",
            "shadow": "0 18px 36px -24px",
            "shadow_alpha": "42%",
            "glow": "8%",
            "card": "#ffffff",
            "atmosphere": (
                "radial-gradient(90% 60% at 0% 0%, color-mix(in srgb, var(--color-brand) 16%, transparent), transparent 55%), "
                "radial-gradient(55% 45% at 100% 0%, color-mix(in srgb, var(--color-accent) 10%, transparent), transparent 50%), "
                "linear-gradient(165deg, color-mix(in srgb, var(--color-brand) 9%, #f4f6f8), color-mix(in srgb, var(--color-brand) 5%, #eef1f5) 48%, #f7f8fa)"
            ),
        },
        "hero_variant": "compact",
        "feature_variant": "grid",
        "chrome": {
            "shell": "solid",
            "nav": "minimal",
            "footer": "compact",
            "brand": "start",
        },
        "section_orders": {
            "public-home": [
                "hero",
                "features",
                "results",
                "process",
                "cta",
                "footer",
            ],
            "public-service": ["hero", "features", "process", "cta", "footer"],
            "public-booking": ["hero", "features", "booking", "footer"],
            "public-detail": ["hero", "features", "showcase", "cta", "footer"],
            "ops-dashboard": ["header", "kpis", "filters", "table", "chart", "activity", "risk"],
        },
        "prompt": (
            "RECIPE dense-ops: compact spacing, short labels, KPI-first, grid features, "
            "compact utility heroes, brand-tinted workspace chrome (never gray SaaS), "
            "scannable lists and metrics with subtle motion on KPI tiles."
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
            "radius_ui": "1.05rem",
            "bg_mix": "6%",
            "fg_mix": "36%",
            "muted_mix": "30%",
            "border_mix": "15%",
            "shadow": "0 28px 52px -32px",
            "shadow_alpha": "36%",
            "glow": "16%",
            "card": "#fffaf5",
            "atmosphere": (
                "radial-gradient(95% 70% at 95% 0%, color-mix(in srgb, var(--color-brand) 18%, transparent), transparent 55%), "
                "radial-gradient(60% 45% at 5% 30%, color-mix(in srgb, var(--color-accent) 10%, transparent), transparent 50%), "
                "linear-gradient(180deg, #fff7ef, transparent 40%)"
            ),
        },
        "hero_variant": "service",
        "feature_variant": "bento",
        "chrome": {
            "shell": "solid",
            "nav": "default",
            "footer": "compact",
            "brand": "start",
        },
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
            "public-booking": ["hero", "process", "booking", "testimonials", "footer"],
            "public-detail": ["hero", "process", "showcase", "booking", "footer"],
        },
        "prompt": (
            "RECIPE warm-service: friendly tone, rounded corners, trust/process before hard sell, "
            "bento features, offer-first service hero (headline bigger than brand), soft warm card surfaces, "
            "ambient brand glows, never flat white pages."
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
            "radius_ui": "0.2rem",
            "bg_mix": "3%",
            "fg_mix": "54%",
            "muted_mix": "26%",
            "border_mix": "20%",
            "shadow": "0 32px 60px -30px",
            "shadow_alpha": "55%",
            "glow": "22%",
            "card": "#ffffff",
            "atmosphere": (
                "radial-gradient(95% 75% at 85% -5%, color-mix(in srgb, var(--color-brand) 28%, transparent), transparent 58%), "
                "radial-gradient(50% 40% at 10% 20%, color-mix(in srgb, var(--color-accent) 14%, transparent), transparent 48%), "
                "linear-gradient(180deg, color-mix(in srgb, var(--color-brand) 8%, #0b0d10) 0%, transparent 32%)"
            ),
        },
        "hero_variant": "product",
        "feature_variant": "bento",
        "chrome": {
            "shell": "immersive",
            "nav": "minimal",
            "footer": "statement",
            "brand": "start",
        },
        "section_orders": {
            "public-home": [
                "hero",
                "showcase",
                "features",
                "cta",
                "footer",
            ],
            "public-service": ["hero", "showcase", "features", "cta", "footer"],
            "public-booking": ["hero", "showcase", "booking", "cta", "footer"],
            "public-detail": ["hero", "showcase", "features", "cta", "footer"],
        },
        "prompt": (
            "RECIPE bold-retail: product/showcase first, sharp corners, high-contrast type, "
            "short punchy copy, strong CTAs, kinetic marquee after hero, "
            "avoid long process essays on the home page, push visual intensity."
        ),
        "industry_keywords": (
            "retail ecommerce fashion apparel store shop marketplace real estate property "
            "automotive car dealership electronics"
        ),
    },
    "nocturne": {
        "id": "nocturne",
        "label": "Nocturne",
        "blurb": "Dark, luminous nightlife / premium brand — deep surfaces, neon brand accents, high drama.",
        "hub_variant": "marketing",
        "fonts": {
            "sans": '"Manrope", "Segoe UI", sans-serif',
            "display": '"Instrument Serif", Georgia, serif',
            "import": "Instrument+Serif:ital@0;1&family=Manrope:wght@400;500;600;700",
        },
        "tokens": {
            "radius_ui": "0.4rem",
            "bg_mix": "8%",
            "fg_mix": "48%",
            "muted_mix": "28%",
            "border_mix": "22%",
            "shadow": "0 40px 80px -36px",
            "shadow_alpha": "55%",
            "glow": "24%",
            "card": "#121018",
            "atmosphere": (
                "radial-gradient(90% 70% at 80% 0%, color-mix(in srgb, var(--color-brand) 32%, transparent), transparent 55%), "
                "radial-gradient(55% 45% at 10% 80%, color-mix(in srgb, var(--color-accent) 16%, transparent), transparent 50%), "
                "linear-gradient(180deg, #0a090c, #14121a 42%, #0a090c)"
            ),
        },
        "hero_variant": "cinematic",
        "feature_variant": "alternating",
        "chrome": {
            "shell": "immersive",
            "nav": "stacked",
            "footer": "statement",
            "brand": "start",
        },
        "section_orders": {
            "public-home": [
                "hero",
                "showcase",
                "testimonials",
                "cta",
                "footer",
            ],
            "public-service": ["hero", "showcase", "process", "cta", "footer"],
            "public-booking": ["hero", "showcase", "booking", "footer"],
            "public-detail": ["hero", "showcase", "testimonials", "cta", "footer"],
        },
        "prompt": (
            "RECIPE nocturne: dark luminous surfaces, luminous brand accents, cinematic heroes, "
            "high contrast type, fewer pastel cards, nightlife/premium energy, grain + vignette welcome."
        ),
        "industry_keywords": (
            "nightlife bar club lounge music entertainment event concert casino gaming "
            "luxury perfume spirits cocktail"
        ),
    },
    "craft": {
        "id": "craft",
        "label": "Craft",
        "blurb": "Maker / artisan — tactile type, paper tones, process storytelling, handcrafted warmth.",
        "hub_variant": "marketing",
        "fonts": {
            "sans": '"DM Sans", "Segoe UI", sans-serif',
            "display": '"Cormorant Garamond", Georgia, serif',
            "import": "Cormorant+Garamond:ital,wght@0,500;0,600;0,700;1,500&family=DM+Sans:wght@400;500;600;700",
        },
        "tokens": {
            "radius_ui": "0.65rem",
            "bg_mix": "5%",
            "fg_mix": "38%",
            "muted_mix": "28%",
            "border_mix": "16%",
            "shadow": "0 24px 48px -34px",
            "shadow_alpha": "30%",
            "glow": "11%",
            "card": "#fbf7f0",
            "atmosphere": (
                "radial-gradient(80% 60% at 15% 0%, color-mix(in srgb, var(--color-brand) 12%, transparent), transparent 55%), "
                "linear-gradient(180deg, #f7f1e6, transparent 45%)"
            ),
        },
        "hero_variant": "service",
        "feature_variant": "alternating",
        "chrome": {
            "shell": "solid",
            "nav": "stacked",
            "footer": "columns",
            "brand": "center",
        },
        "section_orders": {
            "public-home": [
                "hero",
                "process",
                "showcase",
                "credentials",
                "cta",
                "footer",
            ],
            "public-service": ["hero", "process", "features", "testimonials", "cta", "footer"],
            "public-booking": ["hero", "process", "credentials", "booking", "footer"],
            "public-detail": ["hero", "process", "showcase", "credentials", "footer"],
        },
        "prompt": (
            "RECIPE craft: artisan storytelling, process-first, serif display, paper-warm cards, "
            "tactile imagery, credentials before hard sell, never sterile SaaS chrome."
        ),
        "industry_keywords": (
            "artisan craft bakery pottery woodwork furniture handmade maker studio pottery "
            "floristry florist coffee roaster brewery winery"
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
    chrome = dict(recipe.get("chrome") or {})
    if chrome:
        design["shell_chrome"] = chrome.get("shell") or "solid"
        design["nav_variant"] = chrome.get("nav") or "default"
        design["footer_variant"] = chrome.get("footer") or "statement"
        design["brand_placement"] = chrome.get("brand") or "start"
    design["recipe_prompt"] = recipe["prompt"]
    updated["design_system"] = design
    updated["recipe_id"] = recipe["id"]
    updated["hub_variant"] = recipe["hub_variant"]
    updated["design_direction"] = (
        f"{recipe['label']}: {recipe['blurb']} {recipe['prompt']}"
    ).strip()
    return updated


def recipe_section_slots(skeleton_id: str, recipe: dict[str, Any], current: list[str]) -> list[str]:
    """Apply recipe section order — for public-home, recipe owns the middle stack.

    Other skeletons keep a softer reorder of whatever was already assigned.
    """
    preferred = list((recipe.get("section_orders") or {}).get(skeleton_id) or [])
    if not preferred:
        return current

    from app.application.ui_catalogue import get_skeleton

    skeleton = get_skeleton(skeleton_id)
    allowed = set(skeleton.get("requiredSections") or []) | set(
        skeleton.get("optionalSections") or []
    )
    allowed.discard("shell")
    required = [slot for slot in (skeleton.get("requiredSections") or []) if slot != "shell"]

    # Marketing faces: recipe owns the stack (do not force every optional mid-slot).
    if skeleton_id in {
        "public-home",
        "public-service",
        "public-detail",
        "public-booking",
    }:
        ordered = [slot for slot in preferred if slot in allowed]
        for req in required:
            if req in ordered:
                continue
            if "cta" in ordered:
                ordered.insert(ordered.index("cta"), req)
            elif "booking" in ordered and req != "booking":
                ordered.insert(ordered.index("booking"), req)
            else:
                ordered.append(req)
        return ordered

    current_set = set(current)
    ordered = [slot for slot in preferred if slot in current_set and slot in allowed]
    for slot in current:
        if slot not in ordered and slot in allowed:
            ordered.append(slot)
    for req in required:
        if req not in ordered:
            ordered.append(req)
    return ordered


def apply_recipe_to_architect(architect: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """Apply recipe section orders + hub variant hints onto catalogue routes."""
    updated = dict(architect or {})
    recipe = get_recipe(plan.get("recipe_id") or (plan.get("design_system") or {}).get("recipe_id"))
    hub = str(plan.get("hub_variant") or recipe.get("hub_variant") or "marketing")
    template_order = list(plan.get("template_section_order") or [])
    template_id = plan.get("industry_template_id")
    routes = []
    for route in updated.get("routes") or []:
        item = dict(route)
        skeleton_id = str(item.get("skeleton_id") or "")
        slots = list(item.get("section_slots") or [])
        if skeleton_id and slots:
            item["section_slots"] = recipe_section_slots(skeleton_id, recipe, slots)
            # Template may refine home rhythm only when its recipe_hint matches.
            template_hint = str(
                (plan.get("design_system") or {}).get("template_recipe_hint")
                or plan.get("template_recipe_hint")
                or ""
            ).strip()
            recipe_id = str(recipe.get("id") or "")
            # Fail closed: only override when the pack explicitly targets this recipe.
            # Missing hints used to wipe recipe faces (e.g. pottery → agency stack).
            if (
                template_order
                and skeleton_id == "public-home"
                and str(item.get("path") or "") in {"/", "/home"}
                and template_hint
                and template_hint == recipe_id
            ):
                item["section_slots"] = recipe_section_slots(
                    skeleton_id,
                    {"section_orders": {skeleton_id: template_order}},
                    item["section_slots"],
                )
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
    if template_id:
        updated["industry_template_id"] = template_id
    direction = str(updated.get("design_direction") or "").strip()
    recipe_line = str(recipe.get("prompt") or "")
    template_line = str((plan.get("design_system") or {}).get("template_prompt") or "")
    if recipe_line and recipe_line not in direction:
        direction = f"{direction} {recipe_line}".strip()
    if template_line and template_line not in direction:
        direction = f"{direction} {template_line}".strip()
    updated["design_direction"] = direction
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
