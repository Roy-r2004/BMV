"""Pins for W2 — the per-archetype art-direction packs.

The pack's job is to make one archetype's screens look like their own kind
of product rather than the same card-and-KPI vocabulary with different
words inside. Two things have to hold for that to be measurable at all:
the palette must be derived deterministically (so the same brand color
always produces the same instruction), and turning packs off must restore
the previous prompt EXACTLY — otherwise the A/B is measuring two changes.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch

from app.archetypes import ARCHETYPES
from app.pipeline import art_packs, prompt_builder
from app.ui_spec import UIDemoSpec


# ── palette derivation ───────────────────────────────────────────────────

def test_palette_is_deterministic_and_complete():
    first = art_packs.derive_palette("#0e9594", "#1d4ed8")
    second = art_packs.derive_palette("#0e9594", "#1d4ed8")
    assert first == second
    assert set(first) >= {
        "primary", "primary_dark", "primary_tint", "accent",
        "chart_series_2", "chart_series_3",
        "canvas", "surface", "border", "text_primary", "text_secondary",
        "positive", "negative", "warning",
    }
    assert all(v.startswith("#") and len(v) == 7 for v in first.values())


def test_a_dark_enough_brand_color_is_used_as_is():
    assert art_packs.derive_palette("#0e9594")["primary"] == "#0E9594"


def test_a_too_light_brand_color_is_darkened_for_the_primary_role():
    """A pale yellow used as-is behind white text produces illegible
    buttons; the model then either ignores the brand or ships the mess."""
    palette = art_packs.derive_palette("#F5D142")
    assert palette["primary"] != "#F5D142"
    assert palette["primary"].lower() != "#f5d142"


def test_neutrals_and_semantics_never_follow_the_brand():
    """Overdue must read as red whatever the logo looks like, and tinted
    greys are what make generated UI look themed instead of designed."""
    teal = art_packs.derive_palette("#0e9594")
    crimson = art_packs.derive_palette("#b91c1c")
    for key in ("canvas", "surface", "border", "text_primary", "text_secondary", "positive", "negative"):
        assert teal[key] == crimson[key]


def test_a_garbage_brand_color_falls_back_instead_of_raising():
    palette = art_packs.derive_palette("not a color", "also not a color")
    assert palette["primary"].startswith("#")


def test_a_missing_brand_color_falls_back():
    assert art_packs.derive_palette(None)["primary"].startswith("#")


# ── the prompt section ───────────────────────────────────────────────────

def test_every_archetype_has_a_pack():
    assert set(art_packs.PACKS) == set(ARCHETYPES)


def test_pack_section_describes_the_system(dental_spec):
    section = art_packs.build_art_direction(dental_spec, "operations-dashboard")
    assert art_packs.ART_PACK_VERSION in section
    assert "COLOR" in section
    assert "TYPOGRAPHY" in section and "SPACING AND DENSITY" in section


def test_an_unknown_archetype_gets_no_pack(dental_spec):
    assert art_packs.build_art_direction(dental_spec, "no-such-archetype") == ""


def test_chart_treatment_only_ships_when_the_screen_has_chart_data(dental_spec):
    assert "CHART TREATMENT" in art_packs.build_art_direction(dental_spec, "operations-dashboard")

    chartless = dental_spec.model_copy(deep=True)
    chartless.chart = None
    assert "CHART TREATMENT" not in art_packs.build_art_direction(chartless, "operations-dashboard")


def test_packs_differ_between_archetypes(dental_spec):
    ops = art_packs.build_art_direction(dental_spec, "operations-dashboard")
    crm = art_packs.build_art_direction(dental_spec, "crm-dashboard")
    analytics = art_packs.build_art_direction(dental_spec, "analytics-dashboard")
    assert len({ops, crm, analytics}) == 3


# ── the A/B has to be a clean comparison ─────────────────────────────────

def test_disabling_packs_restores_the_previous_prompt_exactly(dental_spec):
    with patch.object(prompt_builder.settings, "ENABLE_ART_PACKS", False):
        without = prompt_builder.build_dashboard_image_prompt(dental_spec, archetype_id="operations-dashboard")
    with patch.object(prompt_builder.settings, "ENABLE_ART_PACKS", True):
        with_pack = prompt_builder.build_dashboard_image_prompt(dental_spec, archetype_id="operations-dashboard")

    assert with_pack.startswith(without), "the pack is appended; nothing before it may change"
    assert art_packs.ART_PACK_VERSION in with_pack[len(without):]


def test_prompt_version_records_the_pack_only_when_one_applied(dental_spec):
    with patch.object(prompt_builder.settings, "ENABLE_ART_PACKS", True):
        assert prompt_builder.prompt_version("dashboard-image-v1", dental_spec, "operations-dashboard") == (
            f"dashboard-image-v1+{art_packs.ART_PACK_VERSION}"
        )
        # Flag on, but this archetype has no pack — provenance must say so.
        assert prompt_builder.prompt_version("dashboard-image-v1", dental_spec, "nope") == "dashboard-image-v1"
    with patch.object(prompt_builder.settings, "ENABLE_ART_PACKS", False):
        assert prompt_builder.prompt_version("dashboard-image-v1", dental_spec, "operations-dashboard") == (
            "dashboard-image-v1"
        )


def test_continuation_prompt_carries_the_pack_too(dental_spec):
    """Follow-up screens are the ones that most need it: they inherit the
    anchor's look from an image, and the pack keeps the words matching."""
    with patch.object(prompt_builder.settings, "ENABLE_ART_PACKS", True):
        prompt = prompt_builder.build_continuation_prompt(dental_spec, "Dashboard", "operations-dashboard")
    assert art_packs.ART_PACK_VERSION in prompt


def test_pack_falls_back_to_the_specs_own_archetype(dental_spec):
    """generate_demo_screens passes the archetype explicitly; anything else
    calling the builder still gets the right pack from the spec."""
    with patch.object(prompt_builder.settings, "ENABLE_ART_PACKS", True):
        prompt = prompt_builder.build_dashboard_image_prompt(dental_spec)
    assert "Operations pack" in prompt


def test_a_spec_with_no_brand_color_still_gets_a_pack():
    spec = UIDemoSpec.model_validate({
        "business": {"name": "Bare Minimum LLC", "industry": "Retail"},
        "product": {"name": "BM OS", "purpose": "ops", "screen_type": "dashboard"},
    })
    section = art_packs.build_art_direction(spec, "operations-dashboard")
    assert "TYPOGRAPHY" in section


def test_the_pack_puts_no_hex_code_in_the_prompt(dental_spec):
    """Measured twice on 2026-08-11: a hex list leaked into the rendered UI
    as a green pill ("#059669"), and again as a Risk level pill ("#DC2626")
    after being rewritten as roles WITH an explicit prohibition. An image
    model renders strings it is given. The exact values still exist in
    derive_palette for the compositor — they just never reach the prompt."""
    import re

    for archetype in art_packs.PACKS:
        section = art_packs.build_art_direction(dental_spec, archetype)
        assert not re.search(r"#[0-9A-Fa-f]{6}", section), f"{archetype} pack leaks a hex code"


def test_the_derived_palette_is_still_available_to_code(dental_spec):
    """Dropping hex from the PROMPT must not drop it from the system — W4's
    compositor and the deck need the exact values."""
    palette = art_packs.derive_palette(dental_spec.business.primary_color)
    assert palette["primary"] == "#0E9594"
