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
            title = str(entry.get("title") or entry.get("name") or entry.get("label") or "").strip()
            if not title:
                continue
            desc = str(
                entry.get("description")
                or entry.get("detail")
                or entry.get("blurb")
                or entry.get("hint")
                or entry.get("value")
                or ""
            ).strip()
            items.append({"title": title, "description": desc})
    return items


def _ops_tone(tone: str) -> bool:
    t = (tone or "").lower()
    return any(
        key in t
        for key in (
            "ops",
            "operational",
            "floor",
            "dashboard",
            "kpi",
            "inventory",
            "staff",
            "crm",
            "calendar",
        )
    )


def _normalize_kpis(raw: Any, items: list[dict[str, str]]) -> list[dict[str, str]]:
    kpis: list[dict[str, str]] = []
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            label = str(entry.get("label") or entry.get("title") or entry.get("name") or "").strip()
            if not label:
                continue
            kpis.append(
                {
                    "label": label,
                    "value": str(entry.get("value") or entry.get("metric") or "—").strip() or "—",
                    "delta": str(entry.get("delta") or "").strip(),
                    "hint": str(entry.get("hint") or entry.get("description") or "").strip(),
                }
            )
    if kpis:
        return kpis[:6]
    # Derive from marketing-shaped items when pack is ops-toned.
    for item in items[:4]:
        title = item["title"]
        desc = item["description"]
        value = "—"
        hint = desc
        if "·" in desc:
            left, _, right = desc.partition("·")
            value = left.strip() or "—"
            hint = right.strip() or desc
        elif desc and len(desc) <= 24:
            value = desc
            hint = ""
        kpis.append({"label": title, "value": value, "delta": "", "hint": hint})
    return kpis


def _normalize_activity(raw: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if isinstance(raw, list):
        for idx, entry in enumerate(raw):
            if isinstance(entry, dict):
                title = str(entry.get("title") or entry.get("name") or "").strip()
                if not title:
                    continue
                out.append(
                    {
                        "id": str(entry.get("id") or f"activity-{idx + 1}"),
                        "title": title,
                        "detail": str(entry.get("detail") or entry.get("description") or "").strip(),
                        "time": str(entry.get("time") or entry.get("when") or "Just now").strip()
                        or "Just now",
                    }
                )
            elif isinstance(entry, str) and entry.strip():
                out.append(
                    {
                        "id": f"activity-{idx + 1}",
                        "title": entry.strip(),
                        "detail": "",
                        "time": "Just now",
                    }
                )
    return out


def _normalize_risk(raw: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if isinstance(raw, list):
        for idx, entry in enumerate(raw):
            if isinstance(entry, dict):
                title = str(entry.get("title") or entry.get("name") or "").strip()
                if not title:
                    continue
                severity = str(entry.get("severity") or "medium").strip().lower() or "medium"
                if severity not in ("low", "medium", "high"):
                    severity = "medium"
                out.append(
                    {
                        "id": str(entry.get("id") or f"risk-{idx + 1}"),
                        "title": title,
                        "detail": str(entry.get("detail") or entry.get("description") or "").strip(),
                        "severity": severity,
                    }
                )
            elif isinstance(entry, str) and entry.strip():
                out.append(
                    {
                        "id": f"risk-{idx + 1}",
                        "title": entry.strip(),
                        "detail": "",
                        "severity": "medium",
                    }
                )
    return out


def _normalize_table_rows(raw: Any, items: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if isinstance(raw, list):
        for idx, entry in enumerate(raw):
            if isinstance(entry, dict):
                name = str(
                    entry.get("name") or entry.get("title") or entry.get("label") or ""
                ).strip()
                if not name:
                    continue
                rows.append(
                    {
                        "id": str(entry.get("id") or f"row-{idx + 1}"),
                        "name": name,
                        "status": str(entry.get("status") or entry.get("state") or "Open").strip()
                        or "Open",
                        "owner": str(entry.get("owner") or entry.get("assignee") or "Team").strip()
                        or "Team",
                    }
                )
    if rows:
        return rows[:8]
    for idx, item in enumerate(items[:5]):
        rows.append(
            {
                "id": f"row-{idx + 1}",
                "name": item["title"],
                "status": "Open",
                "owner": "Team",
            }
        )
    return rows


def normalize_mock_seed(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Collapse pack-specific keys into one seed used by mock.ts + scaffolds."""
    src = dict(raw or {})
    tone = str(src.get("tone") or "branded").strip() or "branded"

    items = _as_item_dicts(src.get("items"))
    if not items:
        for key in ("products", "dishes", "treatments", "classes", "services", "offerings"):
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

    seed: dict[str, Any] = {
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
            for x in (
                src.get("trustLabels")
                or ["Signature craft", "On-time delivery", "Repeat guests", "Local favorite"]
            )
            if str(x).strip()
        ],
    }

    # Ops dashboards need KPI / table / activity / risk — preserve pack fields or derive.
    want_ops = (
        _ops_tone(tone)
        or src.get("kpis") is not None
        or src.get("activity") is not None
        or src.get("risk") is not None
        or src.get("tableRows") is not None
        or src.get("table") is not None
    )
    if want_ops:
        kpis = _normalize_kpis(src.get("kpis"), items)
        activity = _normalize_activity(src.get("activity"))
        if not activity:
            activity = [
                {
                    "id": "activity-1",
                    "title": "Record updated",
                    "detail": items[0]["title"] if items else "Latest change logged.",
                    "time": "Just now",
                },
                {
                    "id": "activity-2",
                    "title": "Owner assigned",
                    "detail": "Waiting on confirmation.",
                    "time": "12m ago",
                },
                {
                    "id": "activity-3",
                    "title": "Note added",
                    "detail": "Follow-up requested.",
                    "time": "1h ago",
                },
            ]
        risk = _normalize_risk(src.get("risk"))
        if not risk:
            risk = [
                {
                    "id": "risk-1",
                    "title": "Needs attention",
                    "detail": items[0]["description"] if items else "A follow-up is overdue.",
                    "severity": "medium",
                }
            ]
        table_rows = _normalize_table_rows(src.get("tableRows") or src.get("table"), items)
        seed["kpis"] = kpis
        seed["activity"] = activity
        seed["risk"] = risk
        seed["tableRows"] = table_rows

    return seed
