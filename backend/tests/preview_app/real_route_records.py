"""Route tables as five real businesses actually got them, verbatim from Postgres.

`requests.generated_pages -> preview_app -> routes` for requests 146–151, trimmed
to the keys the page emitters read. They are here because the defect these
fixtures pin is *naming*: the scaffold wrote the literals `/book` and `/gallery`
into pages whose architect had named those routes something else, and no
hand-written fixture found it for six sessions because hand-written fixtures
keep choosing the obvious names.

    146 Kestrel & Fern Bakehouse  booking `/cakes/order`   browse `/gallery`
    147 Meridian Physiotherapy    booking `/book`          browse — none
    148 Ridgeline Bike Works      booking `/service/book`  browse `/bikes`
    150 Copperline Hardware       booking `/hire/reserve`  browse `/catalogue`
    151 (dispatch console)        booking — none           browse — none

147 is the control: its architect chose `/book`, so a resolver and the literal it
replaced give the same answer, and its emitted pages must not move at all. 151 is
the other end — an ops console with no public face, where inventing `/book`
manufactures the dead link. Only 146's is a *nested* booking route that is also
not the first route in the table, which is what stops a "take the second segment"
shortcut from passing.

Kept out of any `test_*.py` file so `test_every_test_file_is_collected` does not
parametrize a module with no tests in it.
"""
from __future__ import annotations

ROUTES_146 = [
    {
        "path": "/",
        "title": "Home / Live Counter",
        "surface": "public",
        "skeleton_id": "public-home",
        "page_intent": "home",
        "component_file": "src/pages/HomePage.tsx",
        "section_slots": ["hero", "process", "showcase", "credentials", "cta", "footer"],
    },
    {
        "path": "/products",
        "title": "Product Detail View",
        "surface": "public",
        "skeleton_id": "public-detail",
        "page_intent": "home",
        "component_file": "src/pages/ProductDetailPage.tsx",
        "section_slots": ["hero", "credentials", "inquire", "cta", "footer"],
    },
    {
        "path": "/checkout",
        "title": "Checkout/Payment Page",
        "surface": "public",
        "skeleton_id": "public-utility",
        "page_intent": "home",
        "component_file": "src/pages/CheckoutPage.tsx",
        "section_slots": ["header", "workspace", "summary", "footer"],
    },
    {
        "path": "/cakes/order",
        "title": "Celebration Cake Portal",
        "surface": "public",
        "skeleton_id": "public-booking",
        "page_intent": "home",
        "component_file": "src/pages/CelebrationCakeOrderPage.tsx",
        "section_slots": ["hero", "process", "credentials", "booking", "footer"],
    },
    {
        "path": "/admin/dashboard",
        "title": "Admin Dashboard",
        "surface": "ops",
        "skeleton_id": "ops-dashboard",
        "page_intent": "ops",
        "component_file": "src/pages/role-baker/AdminDashboardPage.tsx",
        "section_slots": ["header", "kpis", "chart", "filters", "table", "activity"],
    },
    {
        "path": "/gallery",
        "title": "Gallery",
        "surface": "public",
        "skeleton_id": "public-catalog",
        "page_intent": "home",
        "component_file": "src/pages/GalleryPage.tsx",
        "section_slots": ["hero", "filters", "showcase", "features", "cta", "footer"],
    },
    {
        "path": "/gallery/:id",
        "title": "Artwork",
        "surface": "public",
        "skeleton_id": "public-detail",
        "page_intent": "home",
        "component_file": "src/pages/ArtworkDetailPage.tsx",
        "section_slots": ["hero", "credentials", "inquire", "cta", "footer"],
    },
]

ROUTES_147 = [
    {
        "path": "/",
        "title": "Homepage",
        "surface": "public",
        "skeleton_id": "public-home",
        "page_intent": "home",
        "component_file": "src/pages/HomePage.tsx",
        "section_slots": [
            "hero",
            "credentials",
            "features",
            "showcase",
            "testimonials",
            "cta",
            "footer",
        ],
    },
    {
        "path": "/book",
        "title": "Booking Flow",
        "surface": "public",
        "skeleton_id": "public-booking",
        "page_intent": "booking",
        "component_file": "src/pages/BookingFlowPage.tsx",
        "section_slots": ["hero", "credentials", "booking", "footer"],
    },
    {
        "path": "/services",
        "title": "Services Page",
        "surface": "public",
        "skeleton_id": "public-service",
        "page_intent": "listing",
        "component_file": "src/pages/ServicesPage.tsx",
        "section_slots": ["hero", "features", "testimonials", "cta", "footer"],
    },
    {
        "path": "/admin/dashboard",
        "title": "Admin Dashboard",
        "surface": "ops",
        "skeleton_id": "ops-dashboard",
        "page_intent": "ops",
        "component_file": "src/pages/role-therapist/AdminDashboardPage.tsx",
        "section_slots": ["header", "kpis", "chart", "filters", "table", "activity"],
    },
]

ROUTES_148 = [
    {
        "path": "/",
        "title": "Homepage",
        "surface": "public",
        "skeleton_id": "public-home",
        "page_intent": "home",
        "component_file": "src/pages/HomePage.tsx",
        "section_slots": ["hero", "showcase", "features", "cta", "footer"],
    },
    {
        "path": "/bikes",
        "title": "Bike Range",
        "surface": "public",
        "skeleton_id": "public-catalog",
        "page_intent": "home",
        "component_file": "src/pages/BikeRangePage.tsx",
        "section_slots": [
            "hero",
            "filters",
            "showcase",
            "spotlight",
            "features",
            "cta",
            "footer",
        ],
    },
    {
        "path": "/service/book",
        "title": "Service Booking",
        "surface": "public",
        "skeleton_id": "public-booking",
        "page_intent": "home",
        "component_file": "src/pages/ServiceBookingPage.tsx",
        "section_slots": ["hero", "showcase", "booking", "cta", "footer"],
    },
    {
        "path": "/bikes/v2",
        "title": "Bike Detail",
        "surface": "public",
        "skeleton_id": "public-detail",
        "page_intent": "home",
        "component_file": "src/pages/BikeDetailPage.tsx",
        "section_slots": ["hero", "credentials", "inquire", "cta", "footer"],
    },
]

ROUTES_150 = [
    {
        "path": "/",
        "title": "Homepage",
        "surface": "public",
        "skeleton_id": "public-home",
        "page_intent": "home",
        "component_file": "src/pages/HomePage.tsx",
        "section_slots": ["hero", "showcase", "features", "cta", "footer"],
    },
    {
        "path": "/catalogue",
        "title": "Product Listing Page",
        "surface": "public",
        "skeleton_id": "public-catalog",
        "page_intent": "home",
        "component_file": "src/pages/ProductListingPage.tsx",
        "section_slots": [
            "hero",
            "filters",
            "showcase",
            "spotlight",
            "features",
            "cta",
            "footer",
        ],
    },
    {
        "path": "/product",
        "title": "Product Detail Page",
        "surface": "public",
        "skeleton_id": "public-detail",
        "page_intent": "home",
        "component_file": "src/pages/ProductDetailPage.tsx",
        "section_slots": ["hero", "credentials", "inquire", "cta", "footer"],
    },
    {
        "path": "/hire/reserve",
        "title": "Hire Reservation Page",
        "surface": "public",
        "skeleton_id": "public-booking",
        "page_intent": "home",
        "component_file": "src/pages/HireReservationPage.tsx",
        "section_slots": ["hero", "showcase", "booking", "cta", "footer"],
    },
    {
        "path": "/services",
        "title": "Services",
        "surface": "public",
        "skeleton_id": "public-service",
        "page_intent": "listing",
        "component_file": "src/pages/ServicesPage.tsx",
        "section_slots": ["hero", "showcase", "features", "cta", "footer"],
    },
]

ROUTES_151 = [
    {
        "path": "/login",
        "title": "Login Page",
        "surface": "ops",
        "skeleton_id": "ops-list",
        "page_intent": "ops",
        "component_file": "src/pages/role-dispatcher/LoginPage.tsx",
        "section_slots": ["header", "filters", "table"],
    },
    {
        "path": "/",
        "title": "Command Console Workspace",
        "surface": "ops",
        "skeleton_id": "ops-dashboard",
        "page_intent": "ops",
        "component_file": "src/pages/role-dispatcher/WorkspacePage.tsx",
        "section_slots": ["header", "kpis", "filters", "table", "chart", "activity"],
    },
    {
        "path": "/reconciliation",
        "title": "Back-Office Reconciliation",
        "surface": "ops",
        "skeleton_id": "ops-dashboard",
        "page_intent": "ops",
        "component_file": "src/pages/role-backoffice/ReconciliationPage.tsx",
        "section_slots": ["header", "kpis", "filters", "table", "chart", "activity"],
    },
    {
        "path": "/queue",
        "title": "Work queue",
        "surface": "ops",
        "skeleton_id": "ops-list",
        "page_intent": "ops",
        "component_file": "src/pages/WorkQueuePage.tsx",
        "section_slots": ["header", "filters", "table"],
    },
]

#: Request id -> (brand, routes). The brand matters: several emitters branch on
#: gallery/trading/accounting words in the brand and title.
REAL_APPS = {
    146: ("Kestrel & Fern Bakehouse", ROUTES_146),
    147: ("Meridian Physiotherapy", ROUTES_147),
    148: ("Ridgeline Bike Works", ROUTES_148),
    150: ("Copperline Hardware", ROUTES_150),
    151: ("Halcyon Dispatch", ROUTES_151),
}

#: What each app declared for booking and for browsing, read off the tables above.
DECLARED_BOOKING = {146: "/cakes/order", 147: "/book", 148: "/service/book",
                    150: "/hire/reserve", 151: None}
DECLARED_BROWSE = {146: "/gallery", 147: None, 148: "/bikes",
                   150: "/catalogue", 151: None}


def architect(request_id: int) -> dict:
    """The architect contract as the emitters see it."""
    return {"routes": [dict(r) for r in REAL_APPS[request_id][1]]}


def brand(request_id: int) -> str:
    return REAL_APPS[request_id][0]


def emit_all(request_id: int) -> dict[str, str]:
    """Every page of one app, keyed by workspace-relative file path."""
    from app.application.preview_app.catalogue_contract.scaffold import (
        minimal_catalogue_page_scaffold,
    )

    contract = architect(request_id)
    return {
        str(route["component_file"]): minimal_catalogue_page_scaffold(
            str(route["component_file"]),
            route,
            brand_name=brand(request_id),
            architect=contract,
        )
        for route in contract["routes"]
    }
