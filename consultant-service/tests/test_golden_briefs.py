"""Pins for the golden brief set — the fixtures every image evaluation runs on.

These are frozen ui_spec outputs (scripts/build_golden.py). Their whole
purpose is that the model, or the prompt pack, is the ONLY thing that
varies between two runs — so what has to be pinned is that the fixtures
stay loadable, business-specific, internally coherent, and spread across
distinct archetypes.
"""

import json
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


# ── the v4 set (session 38) ──────────────────────────────────────────────
# golden/briefs is frozen at ui-spec-v1 and the live stage is ui-spec-v4.
# The default deliberately does NOT move: every past evidence document
# means v1 by "the golden set", and bakeoff.py --frozen-specs exists to
# reproduce historical cells, which it could not do if the set underneath
# it changed. Session 34 set that precedent when it froze briefs-v3 and
# left the default alone.
#
# So the new set is addressed explicitly (GOLDEN_BRIEFS_DIR=golden/briefs-v4)
# and validated explicitly here — otherwise it would sit on disk untested,
# which is how a control arm rots.

import pathlib

V4_DIR = pathlib.Path(__file__).resolve().parents[1] / "golden" / "briefs-v4"


def _v4(brief_id: str) -> dict:
    from app.ui_spec import UIDemoSpec

    bundle = json.loads((V4_DIR / f"{brief_id}.json").read_text(encoding="utf-8"))
    bundle["screens"] = [UIDemoSpec.model_validate(s) for s in bundle["screens"]]
    return bundle


V4_IDS = sorted(p.stem for p in V4_DIR.glob("*.json")) if V4_DIR.is_dir() else []


def test_the_v4_set_covers_every_intake_fixture():
    assert set(V4_IDS) == set(INTAKE_FIXTURES), (
        "rebuild with GOLDEN_BRIEFS_DIR=golden/briefs-v4 python scripts/build_golden.py"
    )


@pytest.mark.parametrize("brief_id", V4_IDS)
def test_a_v4_brief_is_coherent_and_was_frozen_at_v4(brief_id):
    from app.pipeline.ui_spec import UI_SPEC_PROMPT_VERSION

    bundle = _v4(brief_id)
    assert bundle["frozen_by"]["ui_spec_prompt_version"] == UI_SPEC_PROMPT_VERSION, (
        "one set, one prompt version — that is what makes it a control arm"
    )
    anchor = bundle["screens"][0]
    assert anchor.business.name == INTAKE_FIXTURES[brief_id]["business_name"]
    assert anchor.product.name == INTAKE_FIXTURES[brief_id]["plan_result"]["concept_name"]
    assert not (anchor.user.name == "Alex" and anchor.subheading == "Today at a glance"), (
        "this is the ui_spec fallback, not a real spec"
    )
    for spec in bundle["screens"]:
        assert spec.style.archetype == bundle["archetype"]
        assert spec.navigation == anchor.navigation


def test_the_v4_set_is_the_first_to_carry_a_conversation():
    """The whole reason it was frozen: the assistant console had no golden
    brief, so nothing could measure it."""
    bundle = _v4("assistant")
    assert bundle["archetype"] == "assistant-console"
    anchor = bundle["screens"][0]
    assert anchor.concept.is_conversation
    assert len(anchor.concept.turns) >= 2
    assert anchor.concept.turns[0].speaker == "customer"
    # Real client-facing content, not the prompt's own examples.
    assert all(turn.text.strip() for turn in anchor.concept.turns)


def test_the_v4_set_still_spans_distinct_archetypes_for_the_bakeoff():
    """A model good at one layout shape must not win the matrix on it."""
    archetype_ids = [_v4(bid)["archetype"] for bid in golden.BAKEOFF_BRIEF_IDS]
    assert len(set(archetype_ids)) == len(golden.BAKEOFF_BRIEF_IDS), archetype_ids


def test_the_shipped_default_set_is_untouched_by_any_of_this():
    """The v1 set is what every evidence document before session 38 means
    by "the golden set", and what --frozen-specs replays."""
    assert golden.briefs_dir().endswith("golden/briefs")
    frozen_at = {
        json.loads((pathlib.Path(golden.briefs_dir()) / f"{bid}.json").read_text())["frozen_by"][
            "ui_spec_prompt_version"
        ]
        for bid in golden.brief_ids()
    }
    assert frozen_at == {"ui-spec-v1"}
