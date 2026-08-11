"""Pins for W7 — the Phase-1 → Phase-2 bridge.

The bridge's whole value is that a closed client is never asked a question
they have already answered. Every test here is a way that promise breaks:
a field that silently does not cross, a fact invented to fill a gap, an
addendum that buries what the client actually typed, or a payload Phase 2
would reject.

The target shape is not guessed. `PHASE2_INTAKE_FIELDS` is the Form
signature of backend's POST /api/v1/requests, and the reason blueprint
prose does not cross is backend's own `capture_request_source`, which
excludes it from the AppSpec author's snapshot deliberately.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.models import GeneratedImage, Request
from app.pipeline import phase2_bridge


def _finished_request() -> Request:
    """A Phase-1 request as it looks the moment the client says yes."""
    req = Request(
        id=68,
        business_name="Harbourline Marine",
        business_description="A 180-berth marina and full service yard in Falmouth.",
        email="ops@harbourline.example",
        industry="Boatyard and marina services",
        target_customers="Yacht and motorboat owners along the south coast.",
        main_problem="Lift slots go unfilled and nobody can see next week's commitments.",
        what_you_like="Calm, premium, uncluttered.",
        desired_outcome="Owners book their own lift slot.",
        needs_ai="yes",
        budget_range="15k-40k GBP",
        timeline="3 months",
        whatsapp="+44 7700 900000",
        concept_name="Harbourline Navigator",
        visual_theme_json=json.dumps({"primary_color": "#0B3B2E", "secondary_color": "#C9A227"}),
        consulting_recommendations_json=json.dumps({
            "recommended_ai_employees": [
                {"title": "AI Resource Scheduler", "why": "..."},
                {"title": "AI Berth Allocation Agent", "why": "..."},
            ],
        }),
        mvp_blueprint="# Blueprint\n\nA long document.",
    )
    req.images = [
        GeneratedImage(id=1, request_id=68, role_id="dashboard", role_label="Dashboard", variant=0,
                       file_path="/uploads/images/68/dashboard_0.png", prompt="p", screen_type="dashboard"),
        GeneratedImage(id=2, request_id=68, role_id="schedule", role_label="Schedule", variant=0,
                       file_path="/uploads/images/68/schedule_0.png", prompt="p", screen_type="schedule"),
        GeneratedImage(id=3, request_id=68, role_id="analytics", role_label="Analytics", variant=0,
                       file_path="/uploads/images/68/analytics_0.png", prompt="p", screen_type="analytics"),
    ]
    return req


# ── the payload Phase 2 accepts ──────────────────────────────────────────

def test_every_shared_intake_answer_crosses_verbatim():
    """The client typed these once. Any of them missing on the other side is
    a question they get asked twice."""
    brief = phase2_bridge.build_phase2_brief(_finished_request())
    req = _finished_request()

    for name in ("business_name", "business_description", "email", "industry",
                 "target_customers", "main_problem", "needs_ai", "budget_range",
                 "timeline", "whatsapp"):
        assert brief.intake[name] == getattr(req, name), f"{name} did not cross"


def test_the_payload_only_contains_fields_phase_2_declares():
    """Phase 2's endpoint takes declared Form fields. An extra key is not an
    error there — it is silently ignored, which is worse."""
    payload = phase2_bridge.as_form_payload(phase2_bridge.build_phase2_brief(_finished_request()))
    assert set(payload) <= set(phase2_bridge.PHASE2_INTAKE_FIELDS)
    for required in ("business_name", "business_description", "email"):
        assert payload.get(required)


def test_a_phase_1_client_is_commissioning_a_new_build():
    """`enhance` would point Phase 2 at an existing product that, by
    definition, does not exist yet — the demo is a picture of it."""
    assert phase2_bridge.build_phase2_brief(_finished_request()).intake["project_type"] == "new"


# ── what Phase 1 learned, and where it lands ─────────────────────────────

def test_the_agreed_screens_cross_in_the_field_that_means_agreed_outcome():
    brief = phase2_bridge.build_phase2_brief(_finished_request())
    outcome = brief.intake["desired_outcome"]

    assert "Dashboard" in outcome and "Schedule" in outcome and "Analytics" in outcome
    assert "Harbourline Navigator" in outcome
    assert "AI Resource Scheduler" in outcome


def test_the_palette_crosses_in_the_field_that_means_design_preference():
    brief = phase2_bridge.build_phase2_brief(_finished_request(), image_register="cinematic")
    likes = brief.intake["what_you_like"]

    assert "#0B3B2E" in likes and "#C9A227" in likes
    assert "cinematic" in likes


def test_the_clients_own_words_come_first():
    """The addendum is generated; what the client typed is not. If one of
    them is going to be read as the headline, it must be theirs."""
    brief = phase2_bridge.build_phase2_brief(_finished_request())

    assert brief.intake["desired_outcome"].startswith("Owners book their own lift slot.")
    assert brief.intake["what_you_like"].startswith("Calm, premium, uncluttered.")


def test_the_screen_inventory_comes_from_screens_that_really_rendered():
    """A plan can name a screen that never rendered. A GeneratedImage row is
    a screen the client was actually shown and actually signed off."""
    screens = phase2_bridge.screen_inventory(_finished_request())
    assert [s["label"] for s in screens] == ["Dashboard", "Schedule", "Analytics"]
    assert screens[0]["demo_image_url"] == "/uploads/images/68/dashboard_0.png"


# ── what must not cross ──────────────────────────────────────────────────

def test_the_blueprint_prose_never_crosses():
    """backend's capture_request_source excludes blueprint prose from the
    AppSpec author's snapshot on purpose. Routing it through an intake field
    would defeat that decision under a different name."""
    brief = phase2_bridge.build_phase2_brief(_finished_request())

    assert "A long document" not in json.dumps(brief.intake)
    assert "A long document" not in json.dumps(brief.carried)
    assert any("blueprint is deliberately NOT carried" in n for n in brief.notes)


def test_nothing_is_invented_to_fill_a_gap():
    """A fabricated brand colour is indistinguishable downstream from one
    the client chose. An empty answer has to stay empty."""
    req = _finished_request()
    req.visual_theme_json = None
    req.consulting_recommendations_json = None
    req.images = []

    brief = phase2_bridge.build_phase2_brief(req)

    assert brief.carried["palette"] == {}
    assert brief.carried["screens"] == []
    assert brief.carried["ai_capabilities"] == []
    assert "#" not in brief.intake.get("what_you_like", "")
    assert any("No palette" in n for n in brief.notes)
    assert any("No screen inventory" in n for n in brief.notes)


def test_a_malformed_theme_is_treated_as_absent_not_as_a_crash():
    """visual_theme_json is model output that has already been through a
    JSON round trip. A bad one must cost the handoff a palette, not a
    request."""
    req = _finished_request()
    req.visual_theme_json = "{not json"
    assert phase2_bridge.build_phase2_brief(req).carried["palette"] == {}

    req.visual_theme_json = json.dumps({"primary_color": None, "secondary_color": ""})
    assert phase2_bridge.build_phase2_brief(req).carried["palette"] == {}


def test_a_missing_email_is_named_rather_than_discovered_by_phase_2():
    req = _finished_request()
    req.email = None
    brief = phase2_bridge.build_phase2_brief(req)
    assert any("requires one and will reject" in n for n in brief.notes)


# ── the property that makes it safe to call twice ────────────────────────

def test_the_mapper_is_pure_and_idempotent():
    """It is going to be called from a retry, an admin button and a test.
    Two calls must produce the same brief, and neither may mutate the
    request — an addendum appended twice would read as the client saying it
    twice, more emphatically."""
    req = _finished_request()
    before = (req.desired_outcome, req.what_you_like)

    first = phase2_bridge.build_phase2_brief(req, image_register="cinematic")
    second = phase2_bridge.build_phase2_brief(req, image_register="cinematic")

    assert first.intake == second.intake
    assert first.carried == second.carried
    assert (req.desired_outcome, req.what_you_like) == before
    assert first.intake["desired_outcome"].count("Harbourline Navigator") == 1


def test_the_inventory_is_bounded_and_says_when_it_bounded_something():
    """No silent caps."""
    req = _finished_request()
    req.images = [
        GeneratedImage(id=i, request_id=68, role_id=f"s{i}", role_label=f"Screen {i}", variant=0,
                       file_path=f"/uploads/images/68/s{i}_0.png", prompt="p", screen_type="dashboard")
        for i in range(1, 10)
    ]
    brief = phase2_bridge.build_phase2_brief(req)

    assert len(brief.carried["screens"]) == 9, "the structured record keeps everything"
    assert "Screen 9" not in brief.intake["desired_outcome"], "the prose is bounded"
    assert any("9 screens agreed" in n for n in brief.notes)


@pytest.mark.parametrize("field_name", ["desired_outcome", "what_you_like"])
def test_an_empty_client_field_gets_the_addendum_without_leading_space(field_name):
    req = _finished_request()
    setattr(req, field_name, None)
    value = phase2_bridge.build_phase2_brief(req, image_register="cinematic").intake[field_name]
    assert value == value.strip() and value
