"""Pins for DoD line 4 — "≤ $0.60 per request" — as arithmetic rather than
as a sentence in a roadmap.

The knobs that decide a request's cost are spread across config.py and each
one looks harmless on its own. Only their product crosses the line, and
before this file nothing could evaluate that without spending money. Two
things are pinned here, and the second is the one that matters:

  1. the projection is inside the DoD line at the shipped defaults;
  2. the projection counts the images the GENERATOR actually makes.

Without (2) this file would be arithmetic agreeing with itself. The count
is therefore taken by running generate_demo_screens against a fake provider
and counting the calls it makes.
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch

import pytest
from PIL import Image

from app import archetypes
from app.config import settings
from app.pipeline import cost_model
from app.pipeline import images as images_mod

_buf = io.BytesIO()
Image.new("RGB", (4, 4), "white").save(_buf, format="PNG")
VALID_PNG = _buf.getvalue()

DOD_COST_CEILING_USD = 0.60


class _FakeDb:
    def add(self, *_): ...
    def commit(self): ...
    def get(self, *_): return object()


def _three_screens(dental_spec):
    """Anchor + two follow-ups, which is what DEMO_SCREEN_COUNT=3 produces."""
    specs = []
    for screen_type in ("dashboard", "patients", "analytics"):
        spec = dental_spec.model_copy(deep=True)
        spec.product.screen_type = screen_type
        specs.append(spec)
    return specs


def _count_generated_images(specs, *, approve: bool) -> int:
    """Runs the real generator against a fake provider and returns how many
    image calls it made. `approve=False` forces the regeneration path."""
    calls = []

    def fake_generate(prompt, *, model=None, reference_images=None, **_):
        calls.append(model)
        return {"image_bytes": VALID_PNG, "usage": None}

    with patch.object(images_mod.provider, "generate_image", side_effect=fake_generate), \
         patch.object(images_mod.qa, "review_image",
                      return_value={"score": 9.0 if approve else 2.0, "issues": [], "approved": approve}), \
         patch.object(images_mod, "log_usage"), \
         patch.object(images_mod, "_save_selected", side_effect=lambda *a, **k: object()):
        images_mod.generate_demo_screens(_FakeDb(), 1, "operations-dashboard", specs)
    return len(calls)


# ── the line itself ──────────────────────────────────────────────────────

def test_a_request_is_projected_inside_the_dod_cost_line():
    projection = cost_model.projected_request_cost("operations-dashboard")
    assert projection["nominal_usd"] <= DOD_COST_CEILING_USD, (
        f"a request projects to ${projection['nominal_usd']}, over the ${DOD_COST_CEILING_USD} DoD line: "
        f"{projection['anchor_candidates']} anchor candidates on {projection['anchor_model']} + "
        f"{projection['followup_candidates']} follow-ups on {projection['followup_model']}"
    )


@pytest.mark.parametrize("archetype_id", [None, *archetypes.ARCHETYPES])
def test_every_archetype_the_intake_can_reach_is_inside_the_line(archetype_id):
    """Not just the three with measured entries. scheduling-dashboard and
    pipeline-dashboard are selectable by the public intake and no golden
    brief lands on either, so nothing had ever costed them: they fell
    through to IMAGE_MODEL for BOTH roles and projected at $0.68."""
    assert cost_model.projected_request_cost(archetype_id)["nominal_usd"] <= DOD_COST_CEILING_USD


def test_an_unmeasured_archetype_still_gets_the_cheaper_follow_up_tier():
    unmeasured = [a for a in archetypes.ARCHETYPES if a not in settings.ARCHETYPE_IMAGE_MODELS]
    assert unmeasured, "this test is about the archetypes with no measured entry"
    for archetype_id in unmeasured:
        assert settings.anchor_model_for(archetype_id) == settings.IMAGE_MODEL
        assert settings.followup_model_for(archetype_id) == settings.FOLLOWUP_MODEL_FALLBACK
        assert settings.followup_model_for(archetype_id) != settings.anchor_model_for(archetype_id)


def test_the_operator_override_still_outranks_the_fallback():
    """The fallback must not make IMAGE_MODEL_FOLLOWUP unreachable — that is
    the escape hatch incident response and the bake-off both use."""
    with patch.object(settings, "IMAGE_MODEL_FOLLOWUP", "forced/model"):
        assert settings.followup_model_for("scheduling-dashboard") == "forced/model"
        assert settings.followup_model_for("operations-dashboard") == "forced/model"


def test_the_shipped_anchor_candidate_count_is_two():
    """Owner's call, 2026-08-11. At 3 the projection is ~$0.60 — exactly ON
    the ceiling, with no headroom for the regeneration the pipeline allows."""
    assert settings.DASHBOARD_CANDIDATES == 2

    with patch.object(settings, "DASHBOARD_CANDIDATES", 3):
        at_three = cost_model.projected_request_cost("operations-dashboard")["nominal_usd"]
    assert at_three > cost_model.projected_request_cost("operations-dashboard")["nominal_usd"]
    assert at_three >= 0.55, "the third candidate was retired for costing ~$0.15; this says it no longer does"


# ── the projection describes the real generator ──────────────────────────

def test_the_projection_counts_the_images_the_generator_actually_makes(dental_spec):
    projected = cost_model.projected_image_count("operations-dashboard")["nominal"]
    assert _count_generated_images(_three_screens(dental_spec), approve=True) == projected


def test_the_worst_case_counts_one_regeneration_per_screen(dental_spec):
    projected = cost_model.projected_image_count("operations-dashboard")["worst_case"]
    assert _count_generated_images(_three_screens(dental_spec), approve=False) == projected


def test_the_regeneration_tail_is_named_rather_than_hidden():
    """The worst case is over the line and that is a known, accepted tail —
    it only fires when NO candidate for a screen was approved. It is pinned
    so nobody discovers it during a funded run."""
    projection = cost_model.projected_request_cost("operations-dashboard")
    assert projection["worst_case_usd"] > projection["nominal_usd"]
    assert projection["worst_case"] == projection["nominal"] + projection["screens"]


# ── the rates ────────────────────────────────────────────────────────────

def test_an_unmeasured_model_is_costed_at_the_most_expensive_measured_rate():
    """A projection that flatters an unknown model is the failure mode that
    would matter — it would clear the DoD line by assuming a bargain."""
    assert cost_model._rate("some/unmeasured-model") == max(cost_model.MEASURED_IMAGE_COST_USD.values())


def test_the_measured_rates_are_the_models_the_pipeline_actually_uses():
    for archetype_id in settings.ARCHETYPE_IMAGE_MODELS:
        for model in (settings.anchor_model_for(archetype_id), settings.followup_model_for(archetype_id)):
            assert model in cost_model.MEASURED_IMAGE_COST_USD, (
                f"{model} is shipped but has never been costed from the ledger"
            )
