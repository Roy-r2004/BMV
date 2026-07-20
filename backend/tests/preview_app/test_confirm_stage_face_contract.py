"""ConfirmStage utility pages must pass catalogue contract (not be replaced)."""
from __future__ import annotations

from app.application.preview_app.catalogue_contract.validate import (
    validate_catalogue_page_content,
)
from app.application.preview_app.utility_compositor import compose_utility_page_tsx


def test_composed_confirmation_passes_catalogue_contract() -> None:
    route = {
        "path": "/booking/confirmation",
        "title": "Booking Confirmed",
        "skeleton_id": "public-utility",
        "section_slots": ["header", "workspace", "footer"],
        "page_type": "confirmation",
    }
    tsx = compose_utility_page_tsx(
        file_path="src/pages/BookingConfirmationPage.tsx",
        route=route,
        brand_name="Northwheel Pottery",
        workspace_type="confirmation",
        content={
            "header": {
                "title": "You're booked",
                "description": "We saved your seat at the wheel.",
            },
            "footer": {"description": "See you in the studio."},
            "eyebrow": "You're booked",
            "detail": "Northwheel Pottery",
            "primary_cta": {"label": "View classes", "href": "/classes"},
            "workspace": {
                "cards": [
                    {
                        "title": "Class schedule",
                        "description": "Browse other workshops.",
                        "cta_label": "Browse",
                        "cta_href": "/classes",
                    }
                ]
            },
        },
    )
    assert "ConfirmStage" in tsx
    assert validate_catalogue_page_content(tsx, route) == []
