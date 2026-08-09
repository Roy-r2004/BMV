"""Per-request design token overlays — unique visual face without industry hardcoding.

Moods are aesthetic directions (density, atmosphere, surface tokens), not
vertical packs. Picked from the brief + a stable seed so the same request stays
consistent and different businesses don't share one kit look. Fonts are the
brand brief's lane, not the overlay's (Stage A deleted the dead mood pairs).
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

# Visual moods — brief keywords nudge; seed breaks ties for uniqueness.
_MOODS: dict[str, dict[str, Any]] = {
    "calm_air": {
        "label": "Calm air",
        "blurb": "Airy clinical calm — soft surfaces, quiet type, low density.",
        "keywords": (
            "clinic",
            "dental",
            "health",
            "wellness",
            "therapy",
            "medical",
            "hospital",
            "care",
            "patient",
        ),
        "tokens": {
            "radius_ui": "0.85rem",
            "bg_mix": "3%",
            "fg_mix": "38%",
            "muted_mix": "28%",
            "border_mix": "12%",
            "shadow": "0 28px 56px -40px",
            "shadow_alpha": "22%",
            "glow": "5%",
            "card": "#ffffff",
            "atmosphere": (
                "radial-gradient(90% 55% at 8% -5%, color-mix(in srgb, var(--color-brand) 9%, transparent), transparent 58%), "
                "linear-gradient(180deg, #fbfcfd 0%, color-mix(in srgb, var(--color-brand) 3%, #f5f7f9) 55%, #f8fafb 100%)"
            ),
        },
        "density": "airy",
    },
    "warm_paper": {
        "label": "Warm paper",
        "blurb": "Service warmth — paper surfaces, friendly radius, soft glow.",
        "keywords": (
            "salon",
            "spa",
            "studio",
            "booking",
            "appointment",
            "hospitality",
            "cafe",
            "restaurant",
            "boutique",
        ),
        "tokens": {
            "radius_ui": "0.95rem",
            "bg_mix": "5%",
            "fg_mix": "40%",
            "muted_mix": "30%",
            "border_mix": "14%",
            "shadow": "0 26px 52px -38px",
            "shadow_alpha": "30%",
            "glow": "8%",
            "card": "#fffdf9",
            "atmosphere": (
                "radial-gradient(85% 50% at 100% 0%, color-mix(in srgb, var(--color-accent) 12%, transparent), transparent 55%), "
                "linear-gradient(165deg, #fffaf4 0%, color-mix(in srgb, var(--color-brand) 5%, #f7f1ea) 50%, #faf7f2 100%)"
            ),
        },
        "density": "comfortable",
    },
    "bold_ink": {
        "label": "Bold ink",
        "blurb": "High-contrast retail energy — sharp type, punchy surfaces.",
        "keywords": (
            "retail",
            "shop",
            "store",
            "fashion",
            "commerce",
            "brand",
            "marketplace",
            "menu",
        ),
        "tokens": {
            "radius_ui": "0.35rem",
            "bg_mix": "6%",
            "fg_mix": "48%",
            "muted_mix": "34%",
            "border_mix": "18%",
            "shadow": "0 20px 40px -28px",
            "shadow_alpha": "40%",
            "glow": "10%",
            "card": "#ffffff",
            "atmosphere": (
                "linear-gradient(135deg, color-mix(in srgb, var(--color-brand) 14%, #0f172a) 0%, transparent 42%), "
                "radial-gradient(70% 50% at 100% 0%, color-mix(in srgb, var(--color-accent) 18%, transparent), transparent 55%), "
                "linear-gradient(180deg, #f8fafc 0%, #eef2f7 100%)"
            ),
        },
        "density": "punchy",
    },
    "ledger_light": {
        "label": "Ledger light",
        "blurb": "Books clarity — crisp numbers, paper workspace, calm density.",
        "keywords": (
            "account",
            "invoice",
            "ledger",
            "bookkeep",
            "finance",
            "payroll",
            "expense",
            "reconcil",
            "saas",
        ),
        "tokens": {
            "radius_ui": "0.55rem",
            "bg_mix": "4%",
            "fg_mix": "42%",
            "muted_mix": "30%",
            "border_mix": "15%",
            "shadow": "0 18px 36px -28px",
            "shadow_alpha": "26%",
            "glow": "6%",
            "card": "#ffffff",
            "atmosphere": (
                "radial-gradient(80% 50% at 0% 0%, color-mix(in srgb, var(--color-brand) 11%, transparent), transparent 55%), "
                "linear-gradient(180deg, #fbfaf7 0%, color-mix(in srgb, var(--color-brand) 4%, #f4f7f5) 55%, #f7f8fa 100%)"
            ),
        },
        "density": "compact",
    },
    "night_floor": {
        "label": "Night floor",
        "blurb": "Ops floor density — dark chrome, mono numbers, tight rhythm.",
        "keywords": (
            "trading",
            "blotter",
            "hedge",
            "desk",
            "oms",
            "portfolio",
            "risk",
            "ops",
            "warehouse",
            "logistics",
        ),
        "tokens": {
            "radius_ui": "0.3rem",
            "bg_mix": "10%",
            "fg_mix": "55%",
            "muted_mix": "38%",
            "border_mix": "24%",
            "shadow": "0 20px 40px -28px",
            "shadow_alpha": "55%",
            "glow": "10%",
            "card": "#0b1624",
            "atmosphere": (
                "radial-gradient(70% 45% at 10% 0%, color-mix(in srgb, var(--color-brand) 22%, transparent), transparent 55%), "
                "radial-gradient(50% 40% at 100% 0%, rgba(34,211,238,0.12), transparent 50%), "
                "linear-gradient(165deg, #050b14 0%, #0a1524 48%, #07101c 100%)"
            ),
        },
        "density": "dense",
    },
    "soft_glass": {
        "label": "Soft glass",
        "blurb": "Modern product glass — translucent cards, medium radius, brand wash.",
        "keywords": (
            "software",
            "platform",
            "workspace",
            "dashboard",
            "crm",
            "startup",
            "app",
            "product",
        ),
        "tokens": {
            "radius_ui": "0.75rem",
            "bg_mix": "7%",
            "fg_mix": "40%",
            "muted_mix": "32%",
            "border_mix": "16%",
            "shadow": "0 22px 48px -32px",
            "shadow_alpha": "34%",
            "glow": "12%",
            "card": "#ffffff",
            "atmosphere": (
                "radial-gradient(90% 60% at 0% 0%, color-mix(in srgb, var(--color-brand) 16%, transparent), transparent 55%), "
                "radial-gradient(55% 45% at 100% 0%, color-mix(in srgb, var(--color-accent) 12%, transparent), transparent 50%), "
                "linear-gradient(165deg, color-mix(in srgb, var(--color-brand) 8%, #f4f6f8), #f7f8fa 55%, #eef1f5)"
            ),
        },
        "density": "comfortable",
    },
}


def _blob(*parts: str) -> str:
    return " ".join(str(p or "") for p in parts).lower()


def _stable_pick(candidates: list[str], seed: int | str | None) -> str:
    if not candidates:
        return "soft_glass"
    if len(candidates) == 1:
        return candidates[0]
    raw = f"{seed or 0}|{','.join(sorted(candidates))}".encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    idx = int(digest[:8], 16) % len(candidates)
    return candidates[idx]


def pick_design_mood(*parts: str, seed: int | str | None = None) -> str:
    """Pick a mood from brief text; seed breaks ties so businesses diverge."""
    text = _blob(*parts)
    scores: dict[str, int] = {mid: 0 for mid in _MOODS}
    for mid, mood in _MOODS.items():
        for kw in mood["keywords"]:
            if kw in text:
                scores[mid] += 2 if len(kw) > 4 else 1
    best = max(scores.values())
    if best <= 0:
        # No keyword hit — rotate across all moods by seed for uniqueness.
        return _stable_pick(list(_MOODS.keys()), seed)
    winners = [mid for mid, score in scores.items() if score == best]
    return _stable_pick(winners, seed)


def build_design_overlay(
    *parts: str,
    seed: int | str | None = None,
    mood_id: str | None = None,
) -> dict[str, Any]:
    mid = mood_id if mood_id in _MOODS else pick_design_mood(*parts, seed=seed)
    mood = _MOODS[mid]
    tokens = dict(mood["tokens"])
    # Micro-variation from seed so two “calm_air” businesses still differ slightly.
    tweak = int(hashlib.sha256(f"{seed}:{mid}".encode()).hexdigest()[:2], 16)
    radius = float(str(tokens["radius_ui"]).replace("rem", "") or "0.75")
    radius = max(0.25, min(1.15, radius + ((tweak % 7) - 3) * 0.04))
    tokens["radius_ui"] = f"{radius:.2f}rem"
    glow_n = int(re.sub(r"[^\d]", "", str(tokens.get("glow") or "8")) or "8")
    tokens["glow"] = f"{max(4, min(16, glow_n + (tweak % 5) - 2))}%"
    return {
        "id": mid,
        "label": mood["label"],
        "blurb": mood["blurb"],
        "density": mood["density"],
        "tokens": tokens,
    }


def apply_design_overlay_to_plan(
    plan: dict[str, Any] | None,
    *,
    seed: int | str | None = None,
    context: str = "",
    industry: str = "",
    business_name: str = "",
) -> dict[str, Any]:
    """Stamp a per-request design overlay onto plan.design_system (tokens only).

    Type never ships from here: the brand brief owns fonts on every production
    run (brand_locked is always True — session-25 inventory §4), so the six
    mood font pairs were dead weight and Stage A deleted the lane. The overlay
    owns atmosphere / radius / density.
    """
    updated = dict(plan or {})
    design = dict(updated.get("design_system") or {})
    overlay = build_design_overlay(
        context,
        industry,
        business_name,
        str(updated.get("design_direction") or ""),
        str(updated.get("public_direction") or ""),
        str(updated.get("ops_direction") or ""),
        seed=seed,
    )
    tokens = overlay["tokens"]
    design["design_overlay_id"] = overlay["id"]
    design["design_overlay_label"] = overlay["label"]
    design["design_overlay_blurb"] = overlay["blurb"]
    design["density"] = overlay["density"]
    design["token_overrides"] = tokens
    design["border_radius"] = tokens["radius_ui"]
    design["style_keywords"] = f"{design.get('style_keywords') or ''} · {overlay['label']}".strip(" ·")
    updated["design_system"] = design
    updated["design_overlay"] = {
        "id": overlay["id"],
        "label": overlay["label"],
        "density": overlay["density"],
    }
    return updated
