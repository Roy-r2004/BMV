"""Visible-copy hygiene: no literal \\uXXXX, no internal template jargon."""
from __future__ import annotations

from pathlib import Path

from app.application.preview_app.catalogue_contract.scaffold import (
    minimal_catalogue_page_scaffold,
)
from app.application.preview_app.safety.copy_hygiene import (
    decode_literal_unicode_escapes,
    strip_template_jargon_copy,
)

_LISTING_ROUTE = {
    "path": "/gallery",
    "title": "Works — The Kassab Collection",
    "page_intent": "listing",
    "skeleton_id": "public-catalog",
    "app_spec_page_id": "works",
    "action_ids": [],
    "evidence_ids": [],
}

_HOME_ROUTE = {
    "path": "/",
    "title": "Jeanne Kassab Art",
    "skeleton_id": "public-home",
    "section_slots": ["hero", "features", "showcase", "cta", "footer"],
    "action_ids": [],
    "evidence_ids": [],
}


def test_listing_scaffold_emits_real_em_dash_not_escape():
    out = minimal_catalogue_page_scaffold(
        "src/pages/WorksPage.tsx", _LISTING_ROUTE, brand_name="Jeanne Kassab Art"
    )
    assert "\\u2014" not in out
    assert "Browse pieces and details — then inquire about availability." in out
    assert 'title={"Works — The Kassab Collection"}' in out


def test_scaffold_never_json_escapes_non_ascii_anywhere():
    for path, route in (
        ("src/pages/WorksPage.tsx", _LISTING_ROUTE),
        ("src/pages/HomePage.tsx", _HOME_ROUTE),
    ):
        out = minimal_catalogue_page_scaffold(path, route, brand_name="Café Über Ärt")
        assert "\\u00" not in out
        assert "Café Über Ärt" in out


def test_listing_scaffold_page_header_has_top_inset():
    out = minimal_catalogue_page_scaffold(
        "src/pages/WorksPage.tsx", _LISTING_ROUTE, brand_name="Jeanne Kassab Art"
    )
    band = out.split("<PageHeader", 1)[0].rsplit("<div className=", 1)[1]
    assert "pt-28" in band and "px-6" in band


def test_showcase_slots_supply_a_badge_so_template_placeholder_never_shows():
    out = minimal_catalogue_page_scaffold(
        "src/pages/HomePage.tsx", _HOME_ROUTE, brand_name="Jeanne Kassab Art"
    )
    assert "badge:" in out
    listing = minimal_catalogue_page_scaffold(
        "src/pages/WorksPage.tsx", _LISTING_ROUTE, brand_name="Jeanne Kassab Art"
    )
    assert "badge:" in listing


def test_feature_slot_never_renders_a_zero_length_carousel():
    out = minimal_catalogue_page_scaffold(
        "src/pages/HomePage.tsx", _HOME_ROUTE, brand_name="Jeanne Kassab Art"
    )
    features = next(line for line in out.splitlines() if "<FeatureBento" in line)
    assert "seed.features ?? []" not in features
    assert "seed.features?.length ? seed.features :" in features
    assert '"title"' in features


def test_decode_literal_unicode_escapes_fixes_jsx_attribute_and_text(tmp_path: Path):
    pages = tmp_path / "src/pages"
    pages.mkdir(parents=True)
    target = pages / "WorksPage.tsx"
    target.write_text(
        'export default function P() {\n'
        '  return (\n'
        '    <div>\n'
        '      <PageHeader description="Browse pieces \\u2014 then inquire." />\n'
        '      <p>Open daily \\u2013 by appointment</p>\n'
        '    </div>\n'
        '  );\n'
        '}\n',
        encoding="utf-8",
    )
    assert decode_literal_unicode_escapes(tmp_path) == ["src/pages/WorksPage.tsx"]
    out = target.read_text(encoding="utf-8")
    assert "\\u2014" not in out and "\\u2013" not in out
    assert 'description="Browse pieces — then inquire."' in out
    assert "<p>Open daily – by appointment</p>" in out


def test_decode_literal_unicode_escapes_leaves_legitimate_content_alone(tmp_path: Path):
    pages = tmp_path / "src/pages"
    pages.mkdir(parents=True)
    target = pages / "SafePage.tsx"
    original = (
        "const DASH = '\\u2014';\n"
        "const CONTROL_RE = /[\\u0000-\\u001f]/g;\n"
        "const label = `total \\u2014 ${count}`;\n"
        'export default function P() { return <p title={DASH}>{label}</p>; }\n'
    )
    target.write_text(original, encoding="utf-8")
    assert decode_literal_unicode_escapes(tmp_path) == []
    assert target.read_text(encoding="utf-8") == original


def test_strip_template_jargon_copy_replaces_internal_eyebrows(tmp_path: Path):
    pages = tmp_path / "src/pages"
    pages.mkdir(parents=True)
    target = pages / "HomePage.tsx"
    target.write_text(
        'export default function P() {\n'
        '  return (\n'
        '    <>\n'
        '      <ProductShowcase heading="Lead drop" />\n'
        '      <p>Guest path</p>\n'
        '      <CTABand heading="Next move" description="Signature craft" />\n'
        '      <FeatureBento heading="Designed to feel alive" />\n'
        '    </>\n'
        '  );\n'
        '}\n',
        encoding="utf-8",
    )
    assert strip_template_jargon_copy(tmp_path) == ["src/pages/HomePage.tsx"]
    out = target.read_text(encoding="utf-8")
    for banned in ("Lead drop", "Guest path", "Next move", "Signature craft",
                   "Designed to feel alive"):
        assert banned not in out
    assert 'heading="Featured"' in out
