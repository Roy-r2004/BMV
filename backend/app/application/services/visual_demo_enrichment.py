"""Enrich visual demo JSON with business-specific preview_content from blueprint features."""
import re

from app.domain.models.request import Request
from app.application.services.app_config_builder import enrich_app_config
from app.application.services.preview_parser import parse_preview_features

#: There is no palette table here any more, and that is the fix.
#:
#: ``THEME_PALETTES`` had four industry buckets whose ``generic`` and
#: ``wellness`` entries were the *same colour*, and this stage runs before
#: ``brand_brief``, so its ``#0f766e`` was already in ``visual_theme`` by the
#: time the business-aware brief looked — and the brief took the existing value
#: in preference to its own. **58 of the 62 archived workspaces ship
#: ``#0f766e``.** The palette is now derived once, from the business, in
#: ``preview_app.brand_palette``. This stage still infers an *image* theme,
#: which is a photography choice and not a brand colour.

GENERIC_FEATURE_TITLES = frozenset(
    {"Smart Lead Capture", "AI Assistant", "Admin Dashboard", "Automated Follow-up"}
)

GENERIC_HEADLINE = re.compile(r"welcome to your custom|turn inquiries into booked", re.IGNORECASE)


def _infer_image_theme(industry: str | None, features: list[str] | None = None) -> str:
    blob = " ".join([industry or "", " ".join(features or [])]).lower()
    if re.search(r"fitness|nutrition|diet|coach|gym|workout|meal|trainer", blob):
        return "fitness"
    if re.search(r"wellness|clinic|aesthetic|medical|spa|beauty|dental|botox", blob):
        return "wellness"
    if re.search(r"saas|software|tech|marketing|sales|hr|fintech|e-?commerce", blob):
        return "saas"
    return "generic"


def _is_generic_demo(demo: dict) -> bool:
    cards = demo.get("feature_cards") or []
    if not cards:
        return True
    return any(c.get("title") in GENERIC_FEATURE_TITLES for c in cards)


def enrich_visual_demo(demo: dict, req: Request) -> dict:
    """Ensure feature_cards and preview_content match the client's blueprint features."""
    features = parse_preview_features(req.preview_features)
    industry = req.industry or ""
    theme = _infer_image_theme(industry, features)
    product = demo.get("product_name") or req.concept_name or f"{req.business_name} Platform"

    demo.setdefault("visual_theme", {})

    if _is_generic_demo(demo) and features:
        icons = ["users", "sparkles", "chart", "bell", "calendar", "heart"]
        demo["feature_cards"] = [
            {
                "title": title,
                "description": f"{title} — designed for {req.business_name} clients.",
                "icon": icons[i % len(icons)],
            }
            for i, title in enumerate(features[:6])
        ]

    hero = demo.setdefault("hero", {})
    if GENERIC_HEADLINE.search(hero.get("headline", "")):
        if theme == "fitness":
            hero["headline"] = "Your meal plan. Your workouts. One client hub."
        elif theme == "wellness":
            hero["headline"] = "Turn inquiries into booked appointments"
        else:
            hero["headline"] = f"Run {req.business_name} without the busywork"
    if req.preview_summary:
        hero["subheadline"] = req.preview_summary
    hero["primary_cta"] = hero.get("primary_cta") if hero.get("primary_cta") not in (None, "", "Get Started") else "Start your plan"
    hero["secondary_cta"] = hero.get("secondary_cta") if hero.get("secondary_cta") not in (None, "", "Learn More") else "View programs"

    cards = demo.get("feature_cards") or []
    services = [
        {
            "name": c.get("title", "Program"),
            "description": c.get("description", ""),
            "duration": "45 min",
            "cta": "Join program" if theme == "fitness" else "Book now",
        }
        for c in cards[:4]
    ]
    first_service = services[0]["name"] if services else "coaching session"

    pc = demo.get("preview_content") or {}
    if pc.get("image_theme") in (None, "", "wellness") and theme == "fitness":
        pc["image_theme"] = "fitness"
    if not pc.get("website", {}).get("services"):
        eyebrow = (
            "Personalized plans · Weekly check-ins"
            if theme == "fitness"
            else "Premium care · Same-week appointments"
            if theme == "wellness"
            else f"{industry or 'Your business'} · Built for growth"
        )
        demo["preview_content"] = {
            "image_theme": pc.get("image_theme") or theme,
            "website": {
                "eyebrow": pc.get("website", {}).get("eyebrow") or eyebrow,
                "services_label": "Programs & plans" if theme == "fitness" else "Services",
                "services": pc.get("website", {}).get("services") or services,
                "about_paragraphs": pc.get("website", {}).get("about_paragraphs")
                or [
                    f"{req.business_name} uses {product} so every client sees their plan, logs progress, and stays accountable.",
                    req.desired_outcome or req.business_description or "",
                ],
                "contact_intro": pc.get("website", {}).get("contact_intro")
                or f"Ready to start with {req.business_name}? We reply fast on WhatsApp and email.",
                "form_fields": pc.get("website", {}).get("form_fields")
                or ["Full name", "Email", "Phone", "Your goal"],
                "social_proof": pc.get("website", {}).get("social_proof") or "Trusted by coaching clients",
                "hero_highlight": pc.get("website", {}).get("hero_highlight")
                or {
                    "label": "Next check-in",
                    "title": "Thursday · 2:00 PM",
                    "subtitle": f"{first_service} — 1 slot open",
                },
            },
            "inbox": pc.get("inbox")
            or {
                "conversations": [
                    {"name": "Jamie R.", "channel": "WhatsApp", "preview": f"Logged meals for {first_service}?", "time": "2m", "unread": True},
                    {"name": "Taylor S.", "channel": "Instagram", "preview": "Can we adjust my workout for travel?", "time": "18m", "unread": True},
                    {"name": "Jordan P.", "channel": "Email", "preview": "Progress photos uploaded — thanks!", "time": "1h", "unread": False},
                ],
                "messages": [
                    {"role": "user", "text": f"Hi! I want help with {first_service.lower()} — do you have openings this week?"},
                    {"role": "team", "text": f"Absolutely — {req.business_name} has Thursday 2pm or Friday 11am for your kickoff call."},
                    {"role": "user", "text": "Thursday works!"},
                    {"role": "team", "text": "You're booked. Your meal plan and workout are now in your client portal ✓"},
                ],
                "booked_banner": f"Check-in booked · Thu 2:00 PM · {first_service}",
            },
            "schedule": pc.get("schedule")
            or {
                "appointments": [
                    {"time": "10:30", "client": "Taylor S.", "service": services[1]["name"] if len(services) > 1 else "Check-in", "status": "confirmed"},
                    {"time": "2:00", "client": "Jamie R.", "service": first_service, "status": "confirmed"},
                    {"time": "3:30", "client": "Open slot", "service": "—", "status": "available"},
                ],
                "week_stat": "8",
                "week_detail": "check-ins this week",
            },
            "dashboard": pc.get("dashboard")
            or {
                "leads": [
                    {"name": "Jamie R.", "source": "WhatsApp", "service": first_service, "status": "Active"},
                    {"name": "Taylor S.", "source": "Instagram", "service": services[1]["name"] if len(services) > 1 else "Program", "status": "Onboarding"},
                    {"name": "Jordan P.", "source": "Website", "service": first_service, "status": "Completed"},
                ],
            },
        }

    dash = demo.setdefault("admin_dashboard_preview", {"should_show": True, "cards": [], "recent_activity": []})
    if theme == "fitness" and features:
        dash["cards"] = [
            {"title": "Active clients", "value": "24", "description": "On meal & workout plans"},
            {"title": "Check-ins", "value": "8", "description": "This week"},
            {"title": "Adherence", "value": "87%", "description": "Meal logging rate"},
        ]
        dash["recent_activity"] = [
            f"Jamie completed {features[0].lower()} log",
            "Taylor booked weekly check-in via WhatsApp",
            f"Jordan uploaded progress photos for {features[2].lower() if len(features) > 2 else 'program'}",
        ]
    dash["should_show"] = True

    demo["product_name"] = product
    demo = enrich_app_config(demo, req, theme)
    return demo
