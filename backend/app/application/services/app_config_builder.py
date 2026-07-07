"""Build per-business app_config for the interactive preview shell."""
from __future__ import annotations

import copy
import re

from app.domain.models.request import Request
from app.application.services.preview_parser import parse_preview_features

VALID_MODULES = frozenset({"website", "inbox", "schedule", "dashboard"})
VALID_SECTIONS = frozenset({"hero", "features", "programs", "journey", "testimonial", "cta"})

THEME_DEFAULTS: dict[str, dict] = {
    "fitness": {
        "enabled_modules": ["website", "inbox", "schedule", "dashboard"],
        "schedule_variant": "progress",
        "header_variant": "dark",
        "hero_layout": "split",
        "home_sections": ["hero", "features", "programs", "journey"],
        "leads_panel_mode": "adherence",
        "bookings_panel_mode": "programs",
        "tabs": [
            {"id": "website", "label": "Marketing site", "short": "Site", "url_segment": ""},
            {"id": "inbox", "label": "Client chat", "short": "Chat", "url_segment": "messages"},
            {"id": "schedule", "label": "Client progress", "short": "Progress", "url_segment": "progress"},
            {"id": "dashboard", "label": "Coach hub", "short": "Hub", "url_segment": "admin"},
        ],
        "website_nav": [
            {"id": "home", "label": "Home"},
            {"id": "services", "label": "Programs"},
            {"id": "about", "label": "Coach"},
            {"id": "contact", "label": "Join"},
        ],
        "features_section": {
            "title": "Everything your clients need in one hub",
            "subtitle": "Meal plans, workouts, habits, and messaging — built for coaching.",
        },
        "inbox": {
            "title": "Client messages",
            "subtitle": "WhatsApp, Instagram & in-app — one thread per client",
            "footer": "Unified coaching inbox",
            "quick_replies": ["Plan sent ✓", "Great logging!", "Check-in Thu 2pm"],
            "status_label": "Active client",
        },
        "schedule": {
            "title": "Client progress",
            "subtitle": "Habits, meal logs, workouts & progress photos",
            "add_button": "+ Log check-in",
            "today_label": "Today's adherence",
            "slots_label": "Weekly habits",
        },
        "dashboard": {
            "greeting": "Coach dashboard",
            "subtitle": "Client adherence and program delivery at a glance.",
            "nav": [
                {"id": "overview", "label": "Overview"},
                {"id": "clients", "label": "Active clients"},
                {"id": "bookings", "label": "Programs"},
                {"id": "leads", "label": "Adherence"},
                {"id": "settings", "label": "Settings"},
            ],
            "leads_panel": "Adherence leaderboard",
            "bookings_panel": "Active programs",
            "clients_panel": "Client roster",
            "table_headers": {"client": "Client", "source": "Channel", "service": "Program", "status": "Status"},
            "fourth_metric": {"title": "Meal logging", "value": "87%", "sub": "Weekly average"},
            "settings_labels": ["Coach profile", "Meal plan templates", "WhatsApp connected", "Check-in hours"],
        },
    },
    "wellness": {
        "enabled_modules": ["website", "inbox", "schedule", "dashboard"],
        "schedule_variant": "calendar",
        "header_variant": "light",
        "hero_layout": "split",
        "home_sections": ["hero", "programs", "features", "journey"],
        "leads_panel_mode": "table",
        "bookings_panel_mode": "appointments",
        "tabs": [
            {"id": "website", "label": "Clinic website", "short": "Site", "url_segment": ""},
            {"id": "inbox", "label": "Patient inbox", "short": "Inbox", "url_segment": "inbox"},
            {"id": "schedule", "label": "Appointments", "short": "Appts", "url_segment": "calendar"},
            {"id": "dashboard", "label": "Clinic admin", "short": "Admin", "url_segment": "dashboard"},
        ],
        "website_nav": [
            {"id": "home", "label": "Home"},
            {"id": "services", "label": "Treatments"},
            {"id": "about", "label": "About"},
            {"id": "contact", "label": "Book"},
        ],
        "features_section": {
            "title": "Premium patient experience",
            "subtitle": "Booking, reminders, and follow-up built for your clinic.",
        },
        "inbox": {
            "title": "Patient inbox",
            "subtitle": "DMs, WhatsApp & booking inquiries",
            "footer": "Clinic communication hub",
            "quick_replies": ["Slot available Thu", "Send intake form", "Confirm appointment"],
            "status_label": "Active inquiry",
        },
        "schedule": {
            "title": "Appointment calendar",
            "subtitle": "Treatment rooms & practitioner schedule",
            "add_button": "+ Block slot",
            "today_label": "Today's appointments",
            "slots_label": "Available slots",
        },
        "dashboard": {
            "greeting": "Good morning",
            "subtitle": "Today's bookings, inquiries, and follow-ups.",
            "nav": [
                {"id": "overview", "label": "Overview"},
                {"id": "leads", "label": "Inquiries"},
                {"id": "bookings", "label": "Appointments"},
                {"id": "clients", "label": "Patients"},
                {"id": "settings", "label": "Settings"},
            ],
            "leads_panel": "New inquiries",
            "bookings_panel": "Today's appointments",
            "clients_panel": "Recent patients",
            "table_headers": {"client": "Patient", "source": "Source", "service": "Treatment", "status": "Status"},
            "fourth_metric": {"title": "Avg reply", "value": "< 30s", "sub": "Across channels"},
            "settings_labels": ["Clinic profile", "Treatment menu", "WhatsApp connected", "Booking hours"],
        },
    },
    "saas": {
        "enabled_modules": ["website", "inbox", "schedule", "dashboard"],
        "schedule_variant": "calendar",
        "header_variant": "light",
        "hero_layout": "centered",
        "home_sections": ["hero", "features", "journey", "programs"],
        "leads_panel_mode": "table",
        "bookings_panel_mode": "appointments",
        "tabs": [
            {"id": "website", "label": "Product site", "short": "Site", "url_segment": ""},
            {"id": "inbox", "label": "Support inbox", "short": "Support", "url_segment": "support"},
            {"id": "schedule", "label": "Demo calls", "short": "Demos", "url_segment": "meetings"},
            {"id": "dashboard", "label": "Ops dashboard", "short": "Ops", "url_segment": "admin"},
        ],
        "website_nav": [
            {"id": "home", "label": "Home"},
            {"id": "services", "label": "Features"},
            {"id": "about", "label": "About"},
            {"id": "contact", "label": "Demo"},
        ],
        "features_section": {
            "title": "Core platform capabilities",
            "subtitle": "The features that power your product from day one.",
        },
        "inbox": {
            "title": "Support inbox",
            "subtitle": "Live chat, email & onboarding threads",
            "footer": "Customer success hub",
            "quick_replies": ["Onboarding link", "Schedule demo", "Escalate to eng"],
            "status_label": "Active ticket",
        },
        "schedule": {
            "title": "Demo calendar",
            "subtitle": "Sales demos & onboarding calls",
            "add_button": "+ New meeting",
            "today_label": "Today's calls",
            "slots_label": "Open demo slots",
        },
        "dashboard": {
            "greeting": "Product ops",
            "subtitle": "Pipeline, activations, and account health.",
            "nav": [
                {"id": "overview", "label": "Overview"},
                {"id": "leads", "label": "Pipeline"},
                {"id": "bookings", "label": "Meetings"},
                {"id": "clients", "label": "Accounts"},
                {"id": "settings", "label": "Settings"},
            ],
            "leads_panel": "Pipeline",
            "bookings_panel": "Scheduled demos",
            "clients_panel": "Active accounts",
            "table_headers": {"client": "Account", "source": "Channel", "service": "Plan", "status": "Stage"},
            "fourth_metric": {"title": "Activation", "value": "68%", "sub": "Trial → paid"},
            "settings_labels": ["Workspace", "Stripe connected", "Slack alerts", "Demo calendar"],
        },
    },
    "generic": {
        "enabled_modules": ["website", "inbox", "schedule", "dashboard"],
        "schedule_variant": "calendar",
        "header_variant": "light",
        "hero_layout": "split",
        "home_sections": ["hero", "features", "programs"],
        "leads_panel_mode": "table",
        "bookings_panel_mode": "appointments",
        "tabs": [
            {"id": "website", "label": "Your website", "short": "Site", "url_segment": ""},
            {"id": "inbox", "label": "Messages", "short": "Inbox", "url_segment": "inbox"},
            {"id": "schedule", "label": "Bookings", "short": "Book", "url_segment": "calendar"},
            {"id": "dashboard", "label": "Dashboard", "short": "Admin", "url_segment": "dashboard"},
        ],
        "website_nav": [
            {"id": "home", "label": "Home"},
            {"id": "services", "label": "Services"},
            {"id": "about", "label": "About"},
            {"id": "contact", "label": "Contact"},
        ],
        "features_section": {
            "title": "Built for how you work",
            "subtitle": "Key capabilities tailored to your business.",
        },
        "inbox": {
            "title": "Inbox",
            "subtitle": "All channels in one place",
            "footer": "Unified inbox",
            "quick_replies": ["Thanks!", "Booked ✓", "Following up"],
            "status_label": "Active",
        },
        "schedule": {
            "title": "Bookings",
            "subtitle": "Your calendar",
            "add_button": "+ Block time",
            "today_label": "Today's schedule",
            "slots_label": "Available slots",
        },
        "dashboard": {
            "greeting": "Good morning",
            "subtitle": "Here's what's happening today.",
            "nav": [
                {"id": "overview", "label": "Overview"},
                {"id": "leads", "label": "Leads"},
                {"id": "bookings", "label": "Bookings"},
                {"id": "clients", "label": "Clients"},
                {"id": "settings", "label": "Settings"},
            ],
            "leads_panel": "Leads",
            "bookings_panel": "Bookings",
            "clients_panel": "Clients",
            "table_headers": {"client": "Client", "source": "Source", "service": "Service", "status": "Status"},
            "fourth_metric": {"title": "Avg reply", "value": "< 30s", "sub": "Across channels"},
            "settings_labels": ["Business name", "Instagram connected", "WhatsApp connected", "Booking hours"],
        },
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def _infer_modules(req: Request, features: list[str], theme: str) -> list[str]:
    blob = " ".join(
        [
            req.industry or "",
            req.business_description or "",
            req.desired_outcome or "",
            " ".join(features),
        ]
    ).lower()
    modules = ["website"]
    if re.search(r"message|chat|whatsapp|inbox|dm|support|communicat", blob):
        modules.append("inbox")
    elif theme in ("fitness", "wellness", "saas"):
        modules.append("inbox")
    if re.search(r"book|appointment|schedule|calendar|check-?in|reserv", blob):
        modules.append("schedule")
    elif theme == "fitness":
        modules.append("schedule")
    elif theme == "wellness":
        modules.append("schedule")
    if re.search(r"dashboard|admin|analytics|crm|portal|track|manage", blob):
        modules.append("dashboard")
    elif theme != "generic":
        modules.append("dashboard")
    seen: set[str] = set()
    ordered: list[str] = []
    for m in modules:
        if m not in seen and m in VALID_MODULES:
            seen.add(m)
            ordered.append(m)
    return ordered or list(VALID_MODULES)


def _personalize(config: dict, req: Request, product: str) -> dict:
    name = req.business_name or "Your business"
    concept = req.concept_name or product
    tabs = config.get("tabs") or []
    for tab in tabs:
        if tab.get("id") == "website" and tab.get("label") in (
            "Marketing site",
            "Clinic website",
            "Product site",
            "Your website",
        ):
            tab["label"] = f"{name} site"
    fs = config.setdefault("features_section", {})
    if fs.get("title") and name not in fs.get("title", ""):
        fs["title"] = fs["title"].replace("your clients", f"{name} clients").replace("your business", name)
    dash = config.setdefault("dashboard", {})
    dash["greeting"] = dash.get("greeting", "Dashboard")
    if concept and concept not in dash["greeting"]:
        dash["greeting"] = f"{concept}"
    dash["subtitle"] = dash.get("subtitle") or f"Operations hub for {name}."
    return config


def build_app_config(demo: dict, req: Request, theme: str) -> dict:
    features = parse_preview_features(req.preview_features)
    product = demo.get("product_name") or req.concept_name or f"{req.business_name} Platform"
    base = copy.deepcopy(THEME_DEFAULTS.get(theme, THEME_DEFAULTS["generic"]))
    existing = demo.get("app_config") or {}
    merged = _deep_merge(base, existing)

    if not existing.get("enabled_modules"):
        merged["enabled_modules"] = _infer_modules(req, features, theme)

    enabled = [m for m in merged.get("enabled_modules", []) if m in VALID_MODULES]
    merged["enabled_modules"] = enabled
    merged["tabs"] = [t for t in merged.get("tabs", []) if t.get("id") in enabled]

    sections = merged.get("home_sections") or list(base["home_sections"])
    merged["home_sections"] = [s for s in sections if s in VALID_SECTIONS] or list(base["home_sections"])

    merged = _personalize(merged, req, product)
    return merged


def enrich_app_config(demo: dict, req: Request, theme: str) -> dict:
    demo["app_config"] = build_app_config(demo, req, theme)
    return demo
