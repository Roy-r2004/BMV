"""The journey contract — the path *between* pages.

Every other check validates a page in isolation, and a storefront passed all of
them while its visitor could not browse a collection, open an item, or ask about
it. These tests pin each hop of the funnel and the severity policy: a broken
public funnel blocks, an owner-only page warns.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.capabilities import (  # noqa: E402
    CAPABILITIES,
    resolve_capabilities,
    terminal_capability_slots,
)
from app.application.preview_app.capabilities.journey import (  # noqa: E402
    JOURNEYS,
    internal_hrefs,
    journey_for,
    journey_gate_issues,
    walk_journey,
)
from app.application.preview_app.catalogue_contract.scaffold import (  # noqa: E402
    catalog_base_from_path,
    minimal_catalogue_page_scaffold,
)
from app.application.preview_app.industry_templates.loader import (  # noqa: E402
    load_templates,
    pick_template_id,
)

BRAND = "Jeanne Kassab Art"


def _storefront_architect() -> dict[str, Any]:
    return {
        "product_kind": "storefront",
        "industry_template_id": "art-gallery-portfolio-home",
        "routes": [
            {
                "path": "/",
                "component_file": "src/pages/HomePage.tsx",
                "surface": "public",
                "skeleton_id": "public-home",
                "title": "Home",
                "section_slots": ["hero", "showcase", "footer"],
            },
            {
                "path": "/gallery",
                "component_file": "src/pages/GalleryPage.tsx",
                "surface": "public",
                "skeleton_id": "public-catalog",
                "title": "Gallery",
                "section_slots": ["hero", "showcase", "footer"],
            },
            {
                "path": "/gallery/:id",
                "component_file": "src/pages/ArtworkDetailPage.tsx",
                "surface": "public",
                "skeleton_id": "public-detail",
                "title": "Artwork",
                "section_slots": ["hero", "showcase", "footer"],
            },
        ],
    }


def _scaffold_workspace(workspace: Path, architect: dict[str, Any]) -> None:
    for route in architect["routes"]:
        rel = route["component_file"]
        target = workspace / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            minimal_catalogue_page_scaffold(rel, route, brand_name=BRAND),
            encoding="utf-8",
        )


def _patch(workspace: Path, rel: str, old: str, new: str) -> None:
    path = workspace / rel
    src = path.read_text(encoding="utf-8")
    assert old in src, f"{rel} does not contain {old!r}"
    path.write_text(src.replace(old, new), encoding="utf-8")


# --------------------------------------------------------------------------- #
# capability registry
# --------------------------------------------------------------------------- #


def test_capabilities_come_from_the_pack_then_the_product_kind() -> None:
    # A pack declaration wins: this is how a barber gets booking and a gallery
    # gets inquiry without either needing a bespoke code path.
    booking = resolve_capabilities("storefront", {"capabilities": ["booking"]})
    assert [c.id for c in booking] == ["booking"]
    # No declaration falls back to the product kind default.
    assert [c.id for c in resolve_capabilities("storefront", {})] == ["inquiry"]
    assert [c.id for c in resolve_capabilities("booking_service", None)] == ["booking"]
    # Internal surfaces are not public funnels.
    assert resolve_capabilities("internal_ops", None) == ()


def test_unimplemented_capabilities_are_not_resolved_by_default() -> None:
    # chatbot is registered so the registry is exercised by a case the pipeline
    # cannot emit; resolving it silently would promise a surface that never ships.
    assert CAPABILITIES["chatbot"].implemented is False
    assert resolve_capabilities("storefront", {"capabilities": ["chatbot"]}) == ()
    declared = resolve_capabilities(
        "storefront", {"capabilities": ["chatbot"]}, include_unimplemented=True
    )
    assert [c.id for c in declared] == ["chatbot"]


def test_terminal_slots_match_the_scaffold_guarantee() -> None:
    # _ensure_terminal_action_slot injects one of these; drifting apart would let
    # a detail page ship with a CTA anchored to nothing.
    assert terminal_capability_slots() == {"inquire", "booking"}


def test_every_capability_names_a_real_anchor_and_component() -> None:
    for cap in CAPABILITIES.values():
        assert cap.anchor and not cap.anchor.startswith("#"), cap.id
        assert cap.component and cap.component[0].isupper(), cap.id
        assert cap.missing_code.startswith("capability_"), cap.id


# --------------------------------------------------------------------------- #
# the walk — healthy journey
# --------------------------------------------------------------------------- #


def test_scaffolded_storefront_journey_is_whole(tmp_path: Path) -> None:
    architect = _storefront_architect()
    _scaffold_workspace(tmp_path, architect)
    report = walk_journey(tmp_path, architect)
    assert report.ok, [(f.code, f.message) for f in report.findings]
    assert report.hops_ok == ["browse", "detail", "inquire"]
    assert report.hops_absent == []


def test_journey_summary_is_carried_not_just_computed(tmp_path: Path) -> None:
    # The report must be reportable: "ready" should never be read as "the funnel
    # works" without this evidence attached.
    architect = _storefront_architect()
    _scaffold_workspace(tmp_path, architect)
    summary = walk_journey(tmp_path, architect).summary()
    assert summary["product_kind"] == "storefront"
    assert summary["hops_ok"] == ["browse", "detail", "inquire"]
    assert summary["broken"] == []
    json.dumps(summary)  # must survive the API boundary


# --------------------------------------------------------------------------- #
# the walk — one test per broken hop
# --------------------------------------------------------------------------- #


def test_browse_page_capped_at_three_items_blocks(tmp_path: Path) -> None:
    """ProductShowcase renders [featured, secondary, tertiary] and nothing else."""
    architect = _storefront_architect()
    _scaffold_workspace(tmp_path, architect)
    _patch(tmp_path, "src/pages/GalleryPage.tsx", "CatalogGrid", "ProductShowcase")
    report = walk_journey(tmp_path, architect)
    assert [f.code for f in report.blocking] == ["journey_browse_caps_items"]


def test_browse_page_with_no_listing_component_blocks(tmp_path: Path) -> None:
    architect = _storefront_architect()
    _scaffold_workspace(tmp_path, architect)
    _patch(tmp_path, "src/pages/GalleryPage.tsx", "CatalogGrid", "SpotlightCard")
    codes = [f.code for f in walk_journey(tmp_path, architect).blocking]
    assert "journey_browse_not_listing" in codes


def test_detail_page_that_ignores_its_param_blocks(tmp_path: Path) -> None:
    """Every id rendering the same page is the defect this hop exists to catch."""
    architect = _storefront_architect()
    _scaffold_workspace(tmp_path, architect)
    _patch(tmp_path, "src/pages/ArtworkDetailPage.tsx", "useParams()", "({} as any)")
    codes = [f.code for f in walk_journey(tmp_path, architect).blocking]
    assert "journey_detail_ignores_param" in codes


def test_importing_useparams_without_calling_it_still_blocks(tmp_path: Path) -> None:
    """The check must match the call, not the import line.

    An earlier pattern accepted the bare word `useParams`, which the import
    statement satisfies — so a page that had stopped resolving its param passed.
    """
    architect = _storefront_architect()
    _scaffold_workspace(tmp_path, architect)
    rel = "src/pages/ArtworkDetailPage.tsx"
    src = (tmp_path / rel).read_text(encoding="utf-8")
    assert "import { useParams } from 'react-router-dom';" in src
    _patch(tmp_path, rel, "useParams()", "({} as any)")
    still_imported = (tmp_path / rel).read_text(encoding="utf-8")
    assert "useParams" in still_imported, "import must remain for this to be a real test"
    codes = [f.code for f in walk_journey(tmp_path, architect).blocking]
    assert "journey_detail_ignores_param" in codes


def test_missing_terminal_capability_surface_blocks(tmp_path: Path) -> None:
    architect = _storefront_architect()
    _scaffold_workspace(tmp_path, architect)
    _patch(tmp_path, "src/pages/ArtworkDetailPage.tsx", "InquiryPanel", "SpotlightCard")
    codes = [f.code for f in walk_journey(tmp_path, architect).blocking]
    assert CAPABILITIES["inquiry"].missing_code in codes


def test_dead_link_on_a_funnel_page_blocks(tmp_path: Path) -> None:
    """The /about regression: a CTA pointing at a route the app does not have."""
    architect = _storefront_architect()
    _scaffold_workspace(tmp_path, architect)
    _patch(tmp_path, "src/pages/ArtworkDetailPage.tsx", 'href: "#inquire"', 'href: "/about"')
    blocking = walk_journey(tmp_path, architect).blocking
    assert [f.code for f in blocking] == ["journey_dead_link"] * len(blocking)
    assert any("/about" in f.message for f in blocking)


def test_no_detail_route_declared_blocks(tmp_path: Path) -> None:
    architect = _storefront_architect()
    architect["routes"] = [r for r in architect["routes"] if ":" not in r["path"]]
    _scaffold_workspace(tmp_path, architect)
    codes = [f.code for f in walk_journey(tmp_path, architect).blocking]
    assert "journey_no_detail_route" in codes


# --------------------------------------------------------------------------- #
# severity policy
# --------------------------------------------------------------------------- #


def test_ops_surface_warns_and_never_withholds(tmp_path: Path) -> None:
    """Mirrors asset_integrity: only public_surface blocks.

    Blocking on an owner-only page withholds a correct public storefront, which
    is the failure already logged as P0-4.
    """
    architect = _storefront_architect()
    architect["routes"].append(
        {
            "path": "/admin/dashboard",
            "component_file": "src/pages/admin/AdminDashboardPage.tsx",
            "surface": "ops",
            "skeleton_id": "ops-dashboard",
            "title": "Dashboard",
            "section_slots": ["header", "kpis", "table"],
        }
    )
    _scaffold_workspace(tmp_path, architect)
    admin = tmp_path / "src/pages/admin/AdminDashboardPage.tsx"
    admin.write_text(
        admin.read_text(encoding="utf-8").replace(
            "export default function", 'const DEAD = "/nope";\nexport default function'
        ).replace('const DEAD = "/nope";', 'const DEAD = <a href="/nope">x</a>;'),
        encoding="utf-8",
    )
    report = walk_journey(tmp_path, architect)
    assert report.blocking == [], [f.code for f in report.blocking]
    assert any(f.code == "journey_dead_link_offpath" for f in report.warnings)
    assert journey_gate_issues(report) == []


def test_conditional_ai_hub_link_is_advisory_not_blocking(tmp_path: Path) -> None:
    """/ai-features is added by a later stage; a false withhold is worse."""
    architect = _storefront_architect()
    _scaffold_workspace(tmp_path, architect)
    _patch(
        tmp_path,
        "src/pages/ArtworkDetailPage.tsx",
        'href: "#inquire"',
        'href: "/ai-features"',
    )
    report = walk_journey(tmp_path, architect)
    assert report.blocking == [], [f.code for f in report.blocking]
    assert any("/ai-features" in f.message for f in report.warnings)


def test_gate_issues_only_carry_public_breaks(tmp_path: Path) -> None:
    architect = _storefront_architect()
    _scaffold_workspace(tmp_path, architect)
    _patch(tmp_path, "src/pages/GalleryPage.tsx", "CatalogGrid", "ProductShowcase")
    report = walk_journey(tmp_path, architect)
    issues = journey_gate_issues(report)
    assert issues and all(len(i) == 3 for i in issues)
    assert {i[0] for i in issues} == {"journey_browse_caps_items"}


# --------------------------------------------------------------------------- #
# gate integration
# --------------------------------------------------------------------------- #


def test_gate_reports_the_journey_and_blocks_on_a_broken_funnel(tmp_path: Path) -> None:
    from app.application.preview_app.quality_gate import evaluate_quality_gate

    architect = _storefront_architect()
    _scaffold_workspace(tmp_path, architect)
    (tmp_path / "dist").mkdir(parents=True, exist_ok=True)
    (tmp_path / "dist/index.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "src/data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src/data/mock.ts").write_text(
        "export const seed = { items: [] };\n", encoding="utf-8"
    )

    healthy = evaluate_quality_gate(tmp_path, architect, require_ai_hub=False)
    assert healthy.journey.get("hops_ok") == ["browse", "detail", "inquire"]
    assert not [i for i in healthy.issues if i.code.startswith("journey_")]

    _patch(tmp_path, "src/pages/ArtworkDetailPage.tsx", "useParams()", "({} as any)")
    broken = evaluate_quality_gate(tmp_path, architect, require_ai_hub=False)
    assert "journey_detail_ignores_param" in {i.code for i in broken.issues}
    assert broken.journey.get("broken"), "summary must carry the break, not only the issue"


def test_gate_reevaluates_the_journey_so_a_repair_can_clear_it(tmp_path: Path) -> None:
    """The P0-3 trap: a BLOCK that can never be cleared withholds a fixed page.

    The journey walk is recomputed on every evaluate call rather than persisted,
    so restoring the page clears the finding.
    """
    from app.application.preview_app.quality_gate import evaluate_quality_gate

    architect = _storefront_architect()
    _scaffold_workspace(tmp_path, architect)
    (tmp_path / "dist").mkdir(parents=True, exist_ok=True)
    (tmp_path / "dist/index.html").write_text("<html></html>", encoding="utf-8")

    rel = "src/pages/ArtworkDetailPage.tsx"
    good = (tmp_path / rel).read_text(encoding="utf-8")
    _patch(tmp_path, rel, "useParams()", "({} as any)")
    assert "journey_detail_ignores_param" in {
        i.code for i in evaluate_quality_gate(tmp_path, architect, require_ai_hub=False).issues
    }
    (tmp_path / rel).write_text(good, encoding="utf-8")
    after = evaluate_quality_gate(tmp_path, architect, require_ai_hub=False)
    assert "journey_detail_ignores_param" not in {i.code for i in after.issues}


# --------------------------------------------------------------------------- #
# booking journey + verticals
# --------------------------------------------------------------------------- #


def test_booking_journey_is_declared_for_service_businesses() -> None:
    journey = journey_for("booking_service")
    assert journey is not None
    assert [h.id for h in journey.hops] == ["browse", "book"]
    assert journey.terminal_capability == "booking"


def test_every_journey_ends_in_a_registered_capability() -> None:
    for kind, journey in JOURNEYS.items():
        assert journey.terminal_capability in CAPABILITIES, kind
        assert CAPABILITIES[journey.terminal_capability].terminal, kind
        assert CAPABILITIES[journey.terminal_capability].implemented, kind


@pytest.mark.parametrize(
    "industry,expected_pack,expected_capability",
    (
        ("Barbershop and men's grooming", "barber-grooming-home", "booking"),
        ("Hair salon and colour studio", "barber-grooming-home", "booking"),
        ("Independent bookshop", "retail-store-home", "inquiry"),
    ),
)
def test_named_verticals_resolve_to_a_pack_with_a_capability(
    industry: str, expected_pack: str, expected_capability: str
) -> None:
    """All three resolved to no pack at all before these packs existed.

    "salon" is in spa-wellness-home's tags but is 5 characters, so a lone hit
    fails the 6-character distinctiveness gate — a hair salon got nothing.
    """
    load_templates.cache_clear()
    picked = pick_template_id(industry=industry, surface="public", seed=3, context=industry)
    assert picked == expected_pack, picked
    pack = load_templates()[picked]
    caps = resolve_capabilities("booking_service", pack) or resolve_capabilities(
        "storefront", pack
    )
    assert [c.id for c in caps] == [expected_capability]


def test_new_packs_do_not_steal_existing_verticals() -> None:
    load_templates.cache_clear()
    for industry, expected in (
        ("Online fashion boutique", "fashion-retail-storefront"),
        ("Yoga and pilates studio", "fitness-studio-home"),
        ("Fine art gallery - original oil paintings", "art-gallery-portfolio-home"),
        ("Dental clinic and orthodontics", "clinic-dental-home"),
        ("Boutique law firm - estate and family law", "law-professional-home"),
    ):
        picked = pick_template_id(
            industry=industry, surface="public", seed=3, context=industry
        )
        assert picked == expected, (industry, picked)


# --------------------------------------------------------------------------- #
# helpers the contract depends on
# --------------------------------------------------------------------------- #


def test_detail_base_is_derived_from_the_route_not_hardcoded() -> None:
    assert catalog_base_from_path("/gallery/:id") == "/gallery"
    assert catalog_base_from_path("/works/:slug") == "/works"
    assert catalog_base_from_path("/shop/{id}") == "/shop"
    assert catalog_base_from_path("") == "/gallery"


def test_internal_hrefs_skips_anchors_and_external_targets() -> None:
    src = """
      <a href="/gallery">in-app</a>
      <a href="#inquire">anchor</a>
      <a href="mailto:hi@example.com">mail</a>
      <a href="https://example.com">external</a>
      <AppLink href={`/gallery/${id}`} />
    """
    found = set(internal_hrefs(src))
    assert "/gallery" in found
    assert not any(h.startswith(("#", "mailto:", "http")) for h in found)


def test_scaffolded_detail_page_resolves_and_describes_one_item() -> None:
    route = {
        "path": "/gallery/:id",
        "component_file": "src/pages/ArtworkDetailPage.tsx",
        "surface": "public",
        "skeleton_id": "public-detail",
        "title": "Artwork",
        "section_slots": ["hero", "showcase", "footer"],
    }
    tsx = minimal_catalogue_page_scaffold(
        "src/pages/ArtworkDetailPage.tsx", route, brand_name=BRAND
    )
    assert "useParams()" in tsx
    assert "itemIndex" in tsx and "notFound" in tsx
    # The specs strip and the inquiry both name the resolved item.
    assert "itemSpecs" in tsx and "CredentialStrip" in tsx
    assert "itemTitle={itemTitle}" in tsx and "itemId={itemKey}" in tsx
    # A bad id gets a real page, not a blank one.
    assert "data-detail-not-found" in tsx
    assert 'href: "#inquire"' in tsx
    assert '"/about"' not in tsx


def test_scaffolded_browse_page_links_every_item() -> None:
    route = {
        "path": "/gallery",
        "component_file": "src/pages/GalleryPage.tsx",
        "surface": "public",
        "skeleton_id": "public-catalog",
        "title": "Gallery",
        "section_slots": ["hero", "showcase", "footer"],
    }
    tsx = minimal_catalogue_page_scaffold(
        "src/pages/GalleryPage.tsx", route, brand_name=BRAND
    )
    assert "CatalogGrid" in tsx
    assert "ProductShowcase" not in tsx, "the 3-item mosaic is not a catalogue"
    # Every card carries an id, which is what the link is derived from.
    assert "id: String((item as any).id" in tsx
    assert 'detailBase="/gallery"' in tsx


# --------------------------------------------------------------------------- #
# booking funnel (barbers, clinics, studios)
# --------------------------------------------------------------------------- #


def _booking_architect() -> dict[str, Any]:
    return {
        "product_kind": "booking_service",
        "industry_template_id": "barber-grooming-home",
        "routes": [
            {
                "path": "/",
                "component_file": "src/pages/HomePage.tsx",
                "surface": "public",
                "skeleton_id": "public-home",
                "title": "Home",
                "section_slots": ["hero", "features", "footer"],
            },
            {
                "path": "/services",
                "component_file": "src/pages/ServicesPage.tsx",
                "surface": "public",
                "skeleton_id": "public-service",
                "title": "Services",
                "page_intent": "listing",
                "section_slots": ["hero", "showcase", "footer"],
            },
            {
                "path": "/book",
                "component_file": "src/pages/BookPage.tsx",
                "surface": "public",
                "skeleton_id": "public-booking",
                "title": "Book",
                "section_slots": ["hero", "booking", "footer"],
            },
        ],
    }


BOOKING_BRAND = "Fade & Blade"


def _scaffold_booking(workspace: Path, architect: dict[str, Any]) -> None:
    for route in architect["routes"]:
        rel = route["component_file"]
        target = workspace / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            minimal_catalogue_page_scaffold(rel, route, brand_name=BOOKING_BRAND),
            encoding="utf-8",
        )


def test_booking_face_never_takes_the_storefront_cta(tmp_path: Path) -> None:
    """The skeleton outranks the brand name.

    A gallery-flavoured brand on a public-booking page used to emit a
    "View collection" CTA to /gallery, which a booking route table
    (/, /services, /book) does not contain — a dead link produced by the brand,
    not by the model.
    """
    route = {
        "path": "/book",
        "component_file": "src/pages/BookPage.tsx",
        "surface": "public",
        "skeleton_id": "public-booking",
        "title": "Book",
        "section_slots": ["hero", "booking", "footer"],
    }
    tsx = minimal_catalogue_page_scaffold(
        "src/pages/BookPage.tsx", route, brand_name="Jeanne Kassab Art Studio"
    )
    assert "/gallery" not in tsx
    assert 'href: "/book"' in tsx


def test_booking_funnel_is_whole_without_a_detail_route(tmp_path: Path) -> None:
    """A service business goes /services → /book with no detail page.

    Requiring a param route here reported a break in a journey that never
    declared one, so the browse check asks for the *next hop*, not always a
    detail page.
    """
    architect = _booking_architect()
    _scaffold_booking(tmp_path, architect)
    report = walk_journey(tmp_path, architect)
    assert report.blocking == [], [(f.code, f.message) for f in report.blocking]
    assert "browse" in report.hops_ok and "book" in report.hops_ok


def test_booking_funnel_blocks_when_the_book_route_is_gone(tmp_path: Path) -> None:
    architect = _booking_architect()
    _scaffold_booking(tmp_path, architect)
    architect["routes"] = [r for r in architect["routes"] if r["path"] != "/book"]
    codes = {f.code for f in walk_journey(tmp_path, architect).blocking}
    assert "journey_next_hop_missing" in codes


def test_booking_page_missing_its_panel_blocks(tmp_path: Path) -> None:
    architect = _booking_architect()
    _scaffold_booking(tmp_path, architect)
    _patch(tmp_path, "src/pages/BookPage.tsx", "BookingPanel", "SpotlightCard")
    codes = {f.code for f in walk_journey(tmp_path, architect).blocking}
    assert CAPABILITIES["booking"].missing_code in codes


def test_schedule_listing_invents_no_routes(tmp_path: Path) -> None:
    """ScheduleRail used to fall back to /classes/:id and /waitlist-confirmation.

    Neither is in the booking route table, so both were dead links on the page
    whose only job is to start a booking.
    """
    architect = _booking_architect()
    _scaffold_booking(tmp_path, architect)
    src = (tmp_path / "src/pages/ServicesPage.tsx").read_text(encoding="utf-8")
    assert "/classes/" not in src
    assert "waitlist-confirmation" not in src
    assert "/contact" not in src


def test_advisory_findings_do_not_strike_a_hop_out_of_hops_ok(tmp_path: Path) -> None:
    architect = _storefront_architect()
    _scaffold_workspace(tmp_path, architect)
    _patch(
        tmp_path,
        "src/pages/ArtworkDetailPage.tsx",
        'href: "#inquire"',
        'href: "/ai-features"',
    )
    report = walk_journey(tmp_path, architect)
    assert report.warnings, "this test needs an advisory finding to be meaningful"
    assert "detail" in report.hops_ok
