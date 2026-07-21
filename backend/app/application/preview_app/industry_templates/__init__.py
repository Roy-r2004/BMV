"""Industry starter templates — rich content packs + picker wired into plan/architect."""
from __future__ import annotations

from typing import Any, TypedDict


class IndustryTemplate(TypedDict, total=False):
    id: str
    label: str
    industry_tags: list[str]
    recipe_hint: str
    skeleton_id: str
    section_order: list[str]
    signature_moves: list[str]
    prompt_hints: list[str]
    mock_seed: dict[str, Any]


# Registry ids — packs live in industry_templates/packs/*.json.
TEMPLATE_IDS: tuple[str, ...] = (
    "spa-wellness-home",
    "restaurant-cafe-home",
    "law-professional-home",
    "fitness-studio-home",
    "real-estate-showcase",
    "fashion-retail-storefront",
    "pottery-craft-studio",
    "clinic-dental-home",
    "agency-portfolio-home",
    "home-services-trades",
    "education-tutoring-home",
    "hotel-hospitality-home",
    "auto-dealership-home",
    "member-hub",
    "checkout-cart",
    "account-tracking",
    "hedge-fund-trading-desk",
    "owner-kpi-dashboard",
    "staff-floor-ops",
    "inventory-catalog-ops",
    "leads-crm-list",
    "booking-calendar-ops",
)
