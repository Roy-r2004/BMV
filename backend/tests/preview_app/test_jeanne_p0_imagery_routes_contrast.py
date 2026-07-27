"""P0 guards: imagery sync, storefront scaffold CTAs, detail route aliases."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.assemble import write_app_tsx  # noqa: E402
from app.application.preview_app.catalogue_contract.scaffold import (  # noqa: E402
    minimal_catalogue_page_scaffold,
)
from app.application.preview_app.safety.mock_data import sync_mock_images  # noqa: E402
from app.application.services.industry_images import (  # noqa: E402
    curated_library_urls,
    get_images_for_industry,
)
from app.infrastructure.templating.renderer import JinjaTemplateRenderer  # noqa: E402


def test_art_industry_uses_art_bucket() -> None:
    from app.application.services.industry_images import _LIBRARY

    images = get_images_for_industry(
        "fine art oil painting gallery",
        seed="jeanne-20",
        business_name="Jeanne Kassab Art",
    )
    assert images["hero"].startswith("https://")
    assert images["card1"].startswith("https://")
    art_urls = set(_LIBRARY["art"].values())
    # Seed rotation permutes slots; every URL should still be from the art bucket
    # (unless Pexels is configured).
    assert all(u in art_urls or "pexels.com" in u for u in images.values())
    library = curated_library_urls()
    assert all(u.startswith("https://") for u in library)


def test_sync_mock_images_rewrites_hallucinated_unsplash(tmp_path: Path) -> None:
    workspace = tmp_path
    (workspace / "src/data").mkdir(parents=True)
    bad = (
        "export const images = {\n"
        "  hero: 'https://images.unsplash.com/photo-1579738541097-f5424756b10d?w=600',\n"
        "  card1: 'https://images.unsplash.com/photo-1628178122394-ae9d53c617dc?w=600',\n"
        "};\n"
        "export const seed = {\n"
        "  items: [{ href: '/book-appointment', "
        "imageSrc: 'https://images.unsplash.com/photo-1579738541171-d4198f192b02?w=400' }],\n"
        "};\n"
    )
    (workspace / "src/data/mock.ts").write_text(bad, encoding="utf-8")
    good = {
        "hero": "https://images.unsplash.com/photo-1541961017774-22349e4a1262?w=1400&q=80&fit=crop&auto=format",
        "hero2": "https://images.unsplash.com/photo-1579783902614-a3fb3927b6a5?w=1400&q=80&fit=crop&auto=format",
        "card1": "https://images.unsplash.com/photo-1513364776144-60967b0f800f?w=700&q=80&fit=crop&auto=format",
        "card2": "https://images.unsplash.com/photo-1460661419201-fd4cecdf8a8b?w=700&q=80&fit=crop&auto=format",
        "card3": "https://images.unsplash.com/photo-1482160549825-59d1b23cb208?w=700&q=80&fit=crop&auto=format",
        "ambient": "https://images.unsplash.com/photo-1549490349-8643362247b5?w=900&q=80&fit=crop&auto=format",
    }
    actions = sync_mock_images(workspace, good)
    assert "images" in actions
    text = (workspace / "src/data/mock.ts").read_text(encoding="utf-8")
    assert "photo-1579738541097" not in text
    assert "photo-1541961017774" in text
    assert "/book-appointment" not in text
    assert "/book" in text


def test_gallery_scaffold_does_not_invent_booking() -> None:
    route = {
        "path": "/gallery",
        "title": "Gallery Page",
        "skeleton_id": "public-catalog",
        "section_slots": ["hero", "showcase", "footer"],
        "page_intent": "listing",
    }
    tsx = minimal_catalogue_page_scaffold(
        "src/pages/GalleryPage.tsx",
        route,
        brand_name="Jeanne Kassab Art",
    )
    assert "/book-appointment" not in tsx
    assert "Book a visit" not in tsx
    assert "View collection" in tsx or "Inquire" in tsx
    assert 'href: "/gallery"' in tsx or 'href: "/about"' in tsx


def test_detail_scaffold_inquire_cta() -> None:
    route = {
        "path": "/gallery/v2",
        "title": "Artwork Detail Page",
        "skeleton_id": "public-detail",
        "section_slots": ["hero", "showcase", "footer"],
        "page_intent": "detail",
    }
    tsx = minimal_catalogue_page_scaffold(
        "src/pages/ArtworkDetailPage.tsx",
        route,
        brand_name="Jeanne Kassab Art",
    )
    assert "/book-appointment" not in tsx
    assert "Book a visit" not in tsx
    assert "Inquire about this piece" in tsx


def test_write_app_adds_gallery_slug_aliases(tmp_path: Path) -> None:
    workspace = tmp_path
    (workspace / "src/pages").mkdir(parents=True)
    (workspace / "src/layouts").mkdir(parents=True)
    (workspace / "src/data").mkdir(parents=True)
    (workspace / "src/pages/HomePage.tsx").write_text(
        "export default function HomePage(){return null}", encoding="utf-8"
    )
    (workspace / "src/pages/GalleryPage.tsx").write_text(
        "export default function GalleryPage(){return null}", encoding="utf-8"
    )
    (workspace / "src/pages/ArtworkDetailPage.tsx").write_text(
        "export default function ArtworkDetailPage(){return null}", encoding="utf-8"
    )
    (workspace / "src/layouts/PublicLayout.tsx").write_text(
        "export default function PublicLayout(){return null}", encoding="utf-8"
    )
    (workspace / "src/data/mock.ts").write_text(
        "export const roles = [];\nexport const navigation = { public: [], admin: [] };\n",
        encoding="utf-8",
    )
    architect = {
        "routes": [
            {
                "path": "/",
                "title": "Home",
                "component_file": "src/pages/HomePage.tsx",
                "layout": "public",
                "skeleton_id": "public-home",
            },
            {
                "path": "/gallery",
                "title": "Gallery",
                "component_file": "src/pages/GalleryPage.tsx",
                "layout": "public",
                "skeleton_id": "public-catalog",
            },
            {
                "path": "/gallery/v2",
                "title": "Artwork Detail",
                "component_file": "src/pages/ArtworkDetailPage.tsx",
                "layout": "public",
                "skeleton_id": "public-detail",
            },
        ],
        "roles": [],
    }
    write_app_tsx(workspace, architect, JinjaTemplateRenderer())
    app = (workspace / "src/App.tsx").read_text(encoding="utf-8")
    assert 'path="/gallery/:id"' in app
    assert "ArtworkDetailPage" in app
