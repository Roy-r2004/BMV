"""Public-home scaffold floor — brand-bound defaults, no agency mush."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.catalogue_contract.scaffold import (  # noqa: E402
    minimal_catalogue_page_scaffold,
)
from app.application.preview_app.industry_templates.seed import (  # noqa: E402
    normalize_mock_seed,
)
from app.application.preview_app.safety.mock_data import (  # noqa: E402
    ensure_seed_scaffold_fields,
)

_MUSH = (
    "Designed to feel alive",
    "Make it unforgettable",
    "Premium presence from first glance",
    "Cinematic first impression",
    "Book the next chapter",
    "Signature craft",
    "On-time delivery",
    "Handmade · Small batch",
    "Atmosphere over filler",
)


def test_jane_art_public_home_scaffold_floor() -> None:
    route = {
        "path": "/",
        "title": "Home",
        "skeleton_id": "public-home",
        "section_slots": [
            "hero",
            "features",
            "showcase",
            "credentials",
            "testimonials",
            "cta",
            "footer",
        ],
        "app_spec_page_id": "PAGE-HOME",
        "page_id": "PAGE-HOME",
        "action_ids": ["ACTION-BOOK"],
        "evidence_ids": ["EVIDENCE-HERO"],
    }
    tsx = minimal_catalogue_page_scaffold(
        "src/pages/HomePage.tsx",
        route,
        brand_name="Jane Art",
    )
    for phrase in _MUSH:
        assert phrase not in tsx, f"agency mush leaked into scaffold: {phrase!r}"

    assert "SkeletonComposer" in tsx
    assert "RECIPE_ORDER" in tsx
    assert "order={RECIPE_ORDER}" in tsx
    assert 'const SKELETON_ID = "public-home"' in tsx
    assert 'data-appspec-page="PAGE-HOME"' in tsx
    assert 'data-appspec-action="ACTION-BOOK"' in tsx

    assert "eyebrow={seed.hero?.eyebrow ?? \"Jane Art\"}" in tsx
    assert "seed.hero?.headline" in tsx
    assert "imageSrc={images.hero}" in tsx
    assert 'variant="compact"' not in tsx

    assert "FeatureBento" in tsx
    assert "imagePool={[images.card1, images.card2, images.card3]}" in tsx
    assert "items={seed.features ?? []}" in tsx
    assert "What Jane Art offers" in tsx
    assert "Ready for Jane Art?" in tsx
    assert "Jane Art — clear choices and real bookings." in tsx


def test_normalize_mock_seed_brand_bound_not_agency_bank() -> None:
    seed = normalize_mock_seed({}, brand_name="Jane Art")
    blob = str(seed)
    for phrase in _MUSH:
        assert phrase not in blob, f"agency mush in normalize defaults: {phrase!r}"

    assert seed["hero"]["eyebrow"] == "Jane Art"
    assert "Jane Art" in seed["hero"]["subcopy"]
    assert "Jane Art" in seed["featuresHeading"]
    assert "Jane Art" in seed["cta"]["heading"]
    assert "Jane Art" in seed["footer"]["description"]
    assert any("Jane Art" in label for label in seed["trustLabels"])
    assert seed["features"]
    assert seed["credentials"]


def test_normalize_preserves_nonempty_pack_fields() -> None:
    seed = normalize_mock_seed(
        {
            "hero": {
                "eyebrow": "Studio hours · By appointment",
                "headline": "Wheel-thrown for the table",
                "subcopy": "Clay that earns a place at dinner.",
            },
            "featuresHeading": "Studio strengths",
            "cta": {"heading": "Book a throwing session"},
        },
        brand_name="Jane Art",
    )
    assert seed["hero"]["eyebrow"] == "Studio hours · By appointment"
    assert seed["hero"]["headline"] == "Wheel-thrown for the table"
    assert seed["featuresHeading"] == "Studio strengths"
    assert seed["cta"]["heading"] == "Book a throwing session"


def test_ensure_seed_scaffold_fields_brand_bound() -> None:
    mock = """
export const seed = {
  processHeading: 'How it works',
  process: [{ title: 'One', description: 'Step' }],
};
"""
    out = ensure_seed_scaffold_fields(mock, brand_name="Jane Art")
    for phrase in _MUSH:
        assert phrase not in out, f"agency mush in soft-stub restore: {phrase!r}"
    assert "eyebrow: 'Jane Art'" in out
    assert "headline: 'Jane Art'" in out
    assert "features:" in out
    assert "featuresHeading: 'What Jane Art offers'" in out
    assert "trustLabels:" in out
    assert "credentials:" in out
    assert "Ready for Jane Art?" in out
    assert "Jane Art — clear choices and real bookings." in out


def test_slot_fill_template_includes_public_home_floor() -> None:
    path = (
        BACKEND_DIR
        / "app"
        / "templates"
        / "prompts"
        / "preview_app_slot_fill.j2"
    )
    text = path.read_text(encoding="utf-8")
    assert "PUBLIC-HOME FLOOR" in text
    assert "Designed to feel alive" in text
    assert "Handmade · Small batch" in text
    assert 'variant="compact"' in text
    assert "seed.hero" in text
    assert "imagePool" in text
