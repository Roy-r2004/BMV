"""Pins for the defects the first end-to-end run through the PUBLIC path
found — request 68, session 33.

Everything measured in sessions 31 and 32 went through scripts/bakeoff.py,
which calls generate_demo_screens directly on frozen single-screen briefs.
That rig cannot express the two things that broke here: a three-screen set
where follow-ups inherit a TOOL anchor, and an operator opening /admin to
ask what a screen cost and whether it spelled the client's name right.

Each test below names the artifact it came from. None of them would have
failed on a bake-off cell.
"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.database import Base, SessionLocal, engine
from app.models import AiUsageEvent, GeneratedImage, Request
from app.pipeline import prompt_builder
from app.ui_spec import UIDemoSpec


def _tool_spec() -> UIDemoSpec:
    """A tool anchor — the shape that put navigation on the top bar."""
    return UIDemoSpec.model_validate(
        {
            "business": {"name": "Harbourline Marine", "industry": "Boatyard"},
            "product": {"name": "Harbourline Navigator", "screen_type": "dashboard"},
            "navigation": ["Dashboard", "Schedule", "Berths", "Yard"],
            "concept": {
                "kind": "selector",
                "steps": [{"label": "Select Service", "options": ["Haul Out", "Antifoul"], "selected": "Haul Out"}],
                "primary_action": "Confirm Booking",
                "secondary_action": "Suggest Alternatives",
            },
            "ai": {
                "headline": "Optimize Travel Lift 2",
                "rationale": "High demand, low current use",
                "confidence": "92% optimal",
                "chips": ["Resource Allocation", "Capacity Planning"],
            },
        }
    )


# ── the duplicated navigation ────────────────────────────────────────────

def test_a_continuation_never_restates_where_the_navigation_goes(dental_spec):
    """Request 68's schedule screen shipped BOTH a top navigation bar and a
    left sidebar, carrying the same items. Its prompt told the model to
    "preserve the navigation exactly as the attached image places it" — the
    attached anchor was a tool screen with a top bar — and, four lines
    later, to draw a "left sidebar". It did both.

    Placement is a property of the product, decided once by the anchor. A
    continuation prompt may not name a placement at all."""
    prompt = prompt_builder.build_continuation_prompt(dental_spec, "Dashboard")

    assert "left sidebar" not in prompt
    assert "horizontal bar across the very top" not in prompt
    assert "placed exactly where the attached image places them" in prompt
    assert "in one navigation region and no other" in prompt
    # The items themselves still have to be listed — inheriting the PLACEMENT
    # must not become inheriting the labels by guesswork.
    for item in dental_spec.navigation[:4]:
        assert item in prompt


def test_the_anchor_still_chooses_a_placement():
    """The fix is scoped to continuations. An anchor is the screen that
    decides, and a tool anchor still asks for the top bar."""
    anchor = prompt_builder.build_dashboard_image_prompt(_tool_spec())
    assert "horizontal bar across the very top" in anchor
    assert "placed exactly where the attached image places them" not in anchor


def test_a_dashboard_anchor_still_asks_for_the_sidebar(dental_spec):
    assert "left sidebar" in prompt_builder.build_dashboard_image_prompt(dental_spec)


# ── prompt scaffolding rendered as UI ────────────────────────────────────

def test_the_intelligence_module_carries_no_field_labels(dental_spec):
    """Request 68's analytics screen rendered the literal string "Reasoning
    line: Historical patterns suggest resource need" as UI text. "Reasoning
    line:" is the prompt's own field label. 227a6e3 removed this shape from
    the hero, chart, KPI and navigation blocks and missed the AI module.

    Session 32 already established that instructing the model not to render
    a label does not work — the leaks came from the run carrying that
    instruction. So the label has to stop existing."""
    spec = _tool_spec()
    for prompt in (
        prompt_builder.build_dashboard_image_prompt(spec),
        prompt_builder.build_continuation_prompt(spec, "Dashboard"),
    ):
        for label in ("Reasoning line:", "Confidence readout:", "Headline:"):
            assert label not in prompt, f"{label!r} is a field label sitting in front of a string to render"
        # The values themselves must survive the rewrite.
        assert "Optimize Travel Lift 2" in prompt
        assert "High demand, low current use" in prompt
        assert "92% optimal" in prompt
        assert "Resource Allocation" in prompt


def test_action_buttons_are_described_in_prose_not_as_captioned_fields():
    prompt = prompt_builder.build_dashboard_image_prompt(_tool_spec())
    assert "PRIMARY ACTION BUTTON" not in prompt
    assert "SECONDARY ACTION BUTTON" not in prompt
    assert '"Confirm Booking"' in prompt
    assert '"Suggest Alternatives"' in prompt


# ── the window chrome ────────────────────────────────────────────────────

def test_the_top_edge_is_specified_positively_rather_than_forbidden(dental_spec):
    """All three of request 68's screens carried an OS window title bar with
    minimize / maximize / close controls — unlabelled controls, on a screen
    the OUTPUT section already told the model to draw without chrome.

    The fix states what DOES occupy the top row rather than adding another
    ban. This project has twice watched a ban summon the thing it forbade:
    the corner reservation produced a screen with the word "Logo" drawn in
    it, and the anti-scaffolding instruction produced the scaffolding."""
    for prompt in (
        prompt_builder.build_dashboard_image_prompt(dental_spec),
        prompt_builder.build_continuation_prompt(dental_spec, "Dashboard"),
    ):
        assert "topmost row of pixels already belongs to the application itself" in prompt
        assert "with nothing at all above it" in prompt
        # Naming the controls is what the fix deliberately does NOT do.
        assert "minimize" not in prompt.lower()
        assert "traffic light" not in prompt.lower()


# ── the operator view ────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    from main import app
    from app.config import settings

    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path))
    return TestClient(app)


@pytest.fixture
def request_with_two_screens(tmp_path):
    """One screen that took its regeneration, one that did not — the split
    that makes per-screen cost worth reporting at all."""
    db = SessionLocal()
    req = Request(
        business_name="Harbourline Marine", business_description="d", email="t@example.com",
        status="done", is_generating=False,
        consulting_recommendations_json=json.dumps({"recommended_ai_employees": [], "recommended_features": []}),
    )
    db.add(req)
    db.commit()

    images_dir = tmp_path / "images" / str(req.id)
    images_dir.mkdir(parents=True)
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buf, format="PNG")
    for name in ("dashboard_0.png", "analytics_0.png"):
        (images_dir / name).write_bytes(buf.getvalue())

    db.add(GeneratedImage(
        request_id=req.id, role_id="dashboard", role_label="Dashboard", variant=0,
        file_path=f"/uploads/images/{req.id}/dashboard_0.png", prompt="p",
        model="google/gemini-3-pro-image", qa_score=7.3,
        text_truth_json=json.dumps({"passed": True, "checked": 9, "failures": [], "absent": []}),
    ))
    db.add(GeneratedImage(
        request_id=req.id, role_id="analytics", role_label="Analytics", variant=0,
        file_path=f"/uploads/images/{req.id}/analytics_0.png", prompt="p",
        model="google/gemini-3.1-flash-image", qa_score=8.5,
        text_truth_json=json.dumps({
            "passed": False, "checked": 9,
            "failures": [{"field": "business_name", "expected": "Harbourline Marine", "closest": "Harborline Marine"}],
            "absent": [],
        }),
    ))
    rows = [
        ("dashboard", "image", "google/gemini-3-pro-image", 0.14578, True),
        ("dashboard", "image", "google/gemini-3-pro-image", 0.14578, True),
        ("dashboard", "image_qa", "google/gemini-2.5-flash", 0.00112, True),
        # analytics regenerated: three image calls for one shipped screen
        ("analytics", "image", "google/gemini-3.1-flash-image", 0.06959, True),
        ("analytics", "image", "google/gemini-3.1-flash-image", 0.06959, True),
        ("analytics", "image", "google/gemini-3.1-flash-image", 0.0, False),
        (None, "ui_spec", "google/gemini-2.5-flash", 0.00988, True),
    ]
    for screen, purpose, model, cost, ok in rows:
        db.add(AiUsageEvent(
            request_id=req.id, provider="openrouter", model=model, purpose=purpose,
            screen=screen, cost_usd=cost, success=ok,
        ))
    db.commit()
    yield req.id
    db.close()


def test_admin_reports_the_text_truth_verdict_per_screen(client, request_with_two_screens):
    """The gate's verdict lived only in uploads/images/<id>/*.json, which no
    operator reads. "Did this screen spell the client's name right" is the
    single most important thing on this view."""
    screens = {s["role_id"]: s for s in client.get(f"/api/requests/{request_with_two_screens}/admin").json()["screens"]}

    assert screens["dashboard"]["text_truth"]["passed"] is True
    assert screens["analytics"]["text_truth"]["passed"] is False
    assert screens["analytics"]["text_truth"]["failures"][0]["closest"] == "Harborline Marine"


def test_a_screen_with_no_gate_verdict_reports_null_not_passed(client, request_with_two_screens):
    """Rows predating the column, and runs with the gate off, must not read
    as a pass. Absent and passed are different answers."""
    db = SessionLocal()
    req_id = request_with_two_screens
    db.add(GeneratedImage(
        request_id=req_id, role_id="schedule", role_label="Schedule", variant=0,
        file_path=f"/uploads/images/{req_id}/schedule_0.png", prompt="p", text_truth_json=None,
    ))
    db.commit()
    db.close()

    screens = {s["role_id"]: s for s in client.get(f"/api/requests/{req_id}/admin").json()["screens"]}
    assert screens["schedule"]["text_truth"] is None


def test_admin_attributes_cost_to_the_screen_that_spent_it(client, request_with_two_screens):
    """A screen that took its allowed regeneration costs more than one that
    did not, and that is the difference an operator opens this view to see."""
    screens = {s["role_id"]: s for s in client.get(f"/api/requests/{request_with_two_screens}/admin").json()["screens"]}

    assert screens["dashboard"]["cost"]["image_calls"] == 2
    assert screens["dashboard"]["cost"]["images_usd"] == pytest.approx(0.29156, abs=1e-5)
    assert screens["analytics"]["cost"]["image_calls"] == 2
    assert screens["analytics"]["cost"]["failed_image_calls"] == 1
    # The per-request text stages belong to no screen and must not be
    # smeared across them.
    assert sum(s["cost"]["total_usd"] for s in screens.values()) < client.get(
        f"/api/requests/{request_with_two_screens}/admin").json()["cost"]["total_usd"]


def test_untagged_ledger_rows_report_zero_rather_than_a_guessed_split(client, request_with_two_screens):
    """Requests generated before the `screen` column existed have untagged
    rows. Reporting zero is honest; dividing the request total by the screen
    count would be a number that looks right and is not."""
    db = SessionLocal()
    req = Request(business_name="Old Request", business_description="d", email="t@example.com",
                  status="done", is_generating=False,
                  consulting_recommendations_json=json.dumps({}))
    db.add(req)
    db.commit()
    db.add(GeneratedImage(
        request_id=req.id, role_id="dashboard", role_label="Dashboard", variant=0,
        file_path=f"/uploads/images/{req.id}/dashboard_0.png", prompt="p",
    ))
    db.add(AiUsageEvent(request_id=req.id, provider="openrouter", model="m", purpose="image",
                        screen=None, cost_usd=0.14578, success=True))
    db.commit()
    old_id = req.id
    db.close()

    body = client.get(f"/api/requests/{old_id}/admin").json()
    assert body["cost"]["images_usd"] == pytest.approx(0.14578, abs=1e-5)
    assert body["screens"][0]["cost"]["images_usd"] == 0.0
    assert body["screens"][0]["cost"]["image_calls"] == 0


def test_the_money_still_never_reaches_the_lead_facing_preview(client, request_with_two_screens):
    """Two new cost fields landed on /admin this session. The rule they must
    not break is the one W6 was built around."""
    body = client.get(f"/api/requests/{request_with_two_screens}/preview").json()
    assert "cost" not in json.dumps(body).lower().replace("cost_usd", "")


# ── the detail crops ─────────────────────────────────────────────────────

def test_detail_crops_clear_the_navigation_on_whichever_edge_it_is():
    """Request 68's detail_1 shipped reading "morning, Marco" and "SERVICE".
    The crop insets 15% from the left to clear a sidebar; that anchor was a
    tool screen with a TOP nav bar and no sidebar, so the inset sliced
    through the content instead."""
    from app.pipeline import compositing

    size = (1400, 800)
    left = dict(compositing._crop_regions(size, "left"))
    top = dict(compositing._crop_regions(size, "top"))

    # Sidebar screens are unchanged.
    assert left["detail_1"][0] == round(1400 * 0.15)
    # Top-nav screens keep the left edge and clear the bar above instead.
    assert top["detail_1"][0] < round(1400 * 0.05)
    assert top["detail_1"][1] > left["detail_1"][1]


def test_a_tool_anchor_composites_with_top_nav_crops(dental_spec, tmp_path):
    """The decision has to reach the compositor, not just exist in it."""
    from unittest.mock import patch

    from app.pipeline import images as images_mod

    seen = {}

    def fake_compose(_bytes, **kwargs):
        seen.update(kwargs)
        return {}

    class _FakeDb:
        def add(self, *_): ...
        def commit(self): ...

    spec = _tool_spec()
    selected = {"image_bytes": _blank_png(), "prompt": "p", "variant_id": None, "model": "m",
                "attempt": 0, "latency_s": 1.0,
                "verdict": {"score": 9.0, "issues": [], "approved": True}}
    with patch.object(images_mod.compositing, "compose_presentation", side_effect=fake_compose), \
         patch.object(images_mod.settings, "UPLOADS_DIR", str(tmp_path)), \
         patch.object(images_mod, "_apply_bmv_watermark", side_effect=lambda b: b):
        images_mod._save_selected(
            _FakeDb(), 1, spec, "operations-dashboard", selected, [selected], "v", nav_edge="top",
        )

    assert seen["nav_edge"] == "top"


def _blank_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 40), "white").save(buf, format="PNG")
    return buf.getvalue()
