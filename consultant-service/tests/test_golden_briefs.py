"""Pins for the golden brief set — the fixtures every image evaluation runs on.

These are frozen ui_spec outputs (scripts/build_golden.py). Their whole
purpose is that the model, or the prompt pack, is the ONLY thing that
varies between two runs — so what has to be pinned is that the fixtures
stay loadable, business-specific, internally coherent, and spread across
distinct archetypes.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import golden
from golden.intake import INTAKE_FIXTURES

ALL_IDS = golden.brief_ids()


def test_the_golden_set_is_not_empty():
    assert ALL_IDS, "golden/briefs/*.json is empty — rebuild with scripts/build_golden.py"


@pytest.mark.parametrize("brief_id", ALL_IDS)
def test_brief_loads_and_carries_its_screens(brief_id):
    bundle = golden.load_brief(brief_id)
    assert bundle["archetype"]
    assert len(bundle["screens"]) >= 2, "an anchor plus at least one follow-up"
    for spec in bundle["screens"]:
        assert spec.business.name
        assert spec.product.name
        assert spec.navigation
        assert spec.kpis or spec.primary_panel.rows


@pytest.mark.parametrize("brief_id", ALL_IDS)
def test_brief_matches_its_intake_and_stays_coherent(brief_id):
    bundle = golden.load_brief(brief_id)
    intake = INTAKE_FIXTURES[brief_id]
    anchor = bundle["screens"][0]

    assert anchor.business.name == intake["business_name"]
    assert anchor.product.name == intake["plan_result"]["concept_name"]
    # The coherence guards build_ui_specs applies: one archetype and one
    # navigation across every screen (the image prompts depend on both).
    for spec in bundle["screens"]:
        assert spec.style.archetype == bundle["archetype"]
        assert spec.navigation == anchor.navigation


@pytest.mark.parametrize("brief_id", ALL_IDS)
def test_brief_is_not_a_silent_fallback(brief_id):
    """build_ui_specs returns generic deterministic specs on failure rather
    than raising. A golden brief frozen from THAT would quietly measure every
    future model against a demo specific to nobody (see build_golden.py)."""
    anchor = golden.load_brief(brief_id)["screens"][0]
    fallback_signature = anchor.user.name == "Alex" and anchor.subheading == "Today at a glance"
    assert not fallback_signature, f"{brief_id} looks like the ui_spec fallback, not a real spec"


def test_bakeoff_briefs_exist_and_span_distinct_archetypes():
    """A model good at exactly one layout shape must not be able to win the
    bake-off on that strength alone."""
    archetypes = [golden.load_brief(bid)["archetype"] for bid in golden.BAKEOFF_BRIEF_IDS]
    assert len(set(archetypes)) == len(golden.BAKEOFF_BRIEF_IDS), archetypes


def test_brand_critical_strings_are_the_text_gates_ground_truth():
    truth = golden.brand_critical_strings(golden.load_brief("dental"))
    assert truth["business_name"] == "SmileBright Dental"
    assert truth["product_name"] == "SmileBright Operations"
    assert truth["navigation"]
