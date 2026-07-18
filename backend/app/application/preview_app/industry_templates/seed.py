"""Normalize industry pack mock_seed into a scaffold-friendly shape."""
from __future__ import annotations

from typing import Any


def _as_item_dicts(raw: Any) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    if not isinstance(raw, list):
        return items
    for entry in raw:
        if isinstance(entry, str) and entry.strip():
            items.append({"title": entry.strip(), "description": ""})
        elif isinstance(entry, dict):
            title = str(entry.get("title") or entry.get("name") or "").strip()
            if not title:
                continue
            desc = str(
                entry.get("description")
                or entry.get("detail")
                or entry.get("blurb")
                or ""
            ).strip()
            items.append({"title": title, "description": desc})
    return items


def normalize_mock_seed(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Collapse pack-specific keys into one seed used by mock.ts + scaffolds."""
    src = dict(raw or {})
    tone = str(src.get("tone") or "branded").strip() or "branded"

    items = _as_item_dicts(src.get("items"))
    if not items:
        for key in ("products", "dishes", "treatments", "classes", "services"):
            items = _as_item_dicts(src.get(key))
            if items:
                break
    if not items:
        items = [
            {"title": "Signature offering", "description": "A dependable starting point."},
            {"title": "Everyday essential", "description": "Built for daily use."},
            {"title": "Member favorite", "description": "The one guests come back for."},
        ]

    process = _as_item_dicts(src.get("process") or src.get("steps"))
    if not process:
        process = [
            {"title": "Choose", "description": "Find the right option."},
            {"title": "Confirm", "description": "Select a convenient time."},
            {"title": "Enjoy", "description": "We take care of the details."},
        ]

    credentials = []
    for entry in src.get("credentials") or []:
        if isinstance(entry, dict):
            title = str(entry.get("title") or "").strip()
            detail = str(entry.get("detail") or entry.get("description") or "").strip()
            if title:
                credentials.append({"title": title, "detail": detail})
    if not credentials:
        credentials = [
            {"title": "Brand-first chrome", "detail": "Every surface carries your color and type."},
            {"title": "Motion with purpose", "detail": "Kenburns, reveals, and lifts — never static."},
        ]

    testimonials = []
    for entry in src.get("testimonials") or []:
        if isinstance(entry, dict) and entry.get("quote"):
            testimonials.append(
                {
                    "quote": str(entry.get("quote")),
                    "author": str(entry.get("author") or "A returning client"),
                    "role": str(entry.get("role") or "Verified guest"),
                }
            )
    if not testimonials:
        testimonials = [
            {
                "quote": "Clear, warm, and easy from start to finish.",
                "author": "A returning client",
                "role": "Verified guest",
            }
        ]

    features = _as_item_dicts(src.get("features"))
    if not features:
        features = [
            {
                "title": "Immersive first view",
                "description": "Atmosphere, motion, and brand color from the first scroll.",
            },
            {
                "title": "Real product moments",
                "description": "Concrete screens — bookings, tickets, KPIs — not placeholder cards.",
            },
            {
                "title": "Guided next step",
                "description": "Every section pushes toward a clear action.",
            },
        ]

    hero_src = src.get("hero") if isinstance(src.get("hero"), dict) else {}
    cta_src = src.get("cta") if isinstance(src.get("cta"), dict) else {}
    footer_src = src.get("footer") if isinstance(src.get("footer"), dict) else {}
    nav_cta = src.get("nav_cta") if isinstance(src.get("nav_cta"), dict) else {}

    primary = hero_src.get("primaryCta") if isinstance(hero_src.get("primaryCta"), dict) else {}
    secondary = (
        hero_src.get("secondaryCta") if isinstance(hero_src.get("secondaryCta"), dict) else {}
    )

    treatments = []
    for idx, item in enumerate(items[:4]):
        treatments.append(
            {
                "id": f"offer-{idx + 1}",
                "name": item["title"],
                "duration": "60 min",
            }
        )

    return {
        "tone": tone,
        "hero": {
            "headline": str(hero_src.get("headline") or "").strip(),
            "subcopy": str(
                hero_src.get("subcopy")
                or src.get("subcopy")
                or "Cinematic first impression — brand-forward, vivid, and ready for the next step."
            ).strip(),
            "primaryCta": {
                "label": str(primary.get("label") or nav_cta.get("label") or "Explore now"),
                "href": str(primary.get("href") or nav_cta.get("href") or "#details"),
            },
            "secondaryCta": {
                "label": str(secondary.get("label") or "See how it works"),
                "href": str(secondary.get("href") or "#process"),
            },
        },
        "items": items,
        "features": features,
        "process": process,
        "credentials": credentials,
        "testimonials": testimonials,
        "treatments": treatments,
        "showcaseHeading": str(src.get("showcaseHeading") or "Featured experiences"),
        "featuresHeading": str(src.get("featuresHeading") or "Designed to feel alive"),
        "processHeading": str(src.get("processHeading") or "How it works"),
        "credentialsHeading": str(src.get("credentialsHeading") or "Why it stands out"),
        "testimonialsHeading": str(src.get("testimonialsHeading") or "What clients say"),
        "cta": {
            "heading": str(cta_src.get("heading") or "Make it unforgettable"),
            "description": str(
                cta_src.get("description")
                or "Book the next chapter — polished, branded, never bland."
            ),
            "primaryLabel": str(cta_src.get("primaryLabel") or "Get started"),
            "primaryHref": str(cta_src.get("primaryHref") or "#details"),
            "secondaryLabel": str(cta_src.get("secondaryLabel") or "Talk to us"),
            "secondaryHref": str(cta_src.get("secondaryHref") or "#contact"),
        },
        "footer": {
            "description": str(
                footer_src.get("description")
                or "Premium presence from first glance to booked revenue."
            ),
        },
        "trustLabels": [
            str(x)
            for x in (src.get("trustLabels") or ["Signature craft", "On-time delivery", "Repeat guests", "Local favorite"])
            if str(x).strip()
        ],
    }
