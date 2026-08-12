"""Pins for the durable result page — the customer's way back to their screens.

A run costs real money and used to be reachable exactly once, in the tab
that started it. The result page fixes that, and it leans on three things
this service has to keep promising:

  - `deck_available` tells the page whether to offer the download at all.
    It must mean the same thing as /export/pptx's own precondition, or the
    page hands a customer a button that 400s.
  - `elapsed_s` is computed on the server. created_at is a naive utcnow(),
    which a browser parses as LOCAL time — subtracting it client-side shows
    a wait clock off by the viewer's UTC offset.
  - Both customer-facing routes must 404 (not 500, not an empty shell) for
    an id that was never issued, because the id now comes from a URL a
    customer can edit, bookmark, or mistype.
"""

import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.models import GeneratedImage, Request


@pytest.fixture
def client(tmp_path, monkeypatch):
    from main import app
    from app.config import settings

    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path))
    return TestClient(app)


def _seed(**kwargs) -> int:
    db = SessionLocal()
    req = Request(
        business_name="Beacon Physiotherapy", business_description="d",
        email="t@example.com", status="done", is_generating=False,
        consulting_recommendations_json=json.dumps(
            {"recommended_ai_employees": [], "recommended_features": []},
        ),
        **kwargs,
    )
    db.add(req)
    db.commit()
    request_id = req.id
    db.close()
    return request_id


def test_deck_is_not_offered_before_the_plan_exists(client):
    """The false case is the one that matters: no roles, no button."""
    request_id = _seed(roles_json=None)

    assert client.get(f"/api/requests/{request_id}/preview").json()["deck_available"] is False
    # ...and the flag agrees with the route it is describing.
    assert client.get(f"/api/requests/{request_id}/export/pptx").status_code == 400


def test_deck_is_offered_once_the_plan_exists(client):
    request_id = _seed(roles_json=json.dumps([{"role_id": "dashboard", "role_label": "Dashboard"}]))

    assert client.get(f"/api/requests/{request_id}/preview").json()["deck_available"] is True


def test_elapsed_is_measured_by_the_server_not_the_browser(client):
    request_id = _seed()
    db = SessionLocal()
    db.get(Request, request_id).created_at = datetime.utcnow() - timedelta(seconds=90)
    db.commit()
    db.close()

    elapsed = client.get(f"/api/requests/{request_id}/progress").json()["elapsed_s"]
    assert 88 <= elapsed <= 95, "a resumed run must show the wait it has really taken"


def test_a_fresh_run_reports_a_sane_clock(client):
    """Never negative, never a surprise — the number goes straight on screen."""
    request_id = _seed()

    assert 0 <= client.get(f"/api/requests/{request_id}/progress").json()["elapsed_s"] <= 5


def _seed_screen(request_id: int, spec_json: str | None) -> None:
    db = SessionLocal()
    db.add(GeneratedImage(
        request_id=request_id, role_id="analytics", role_label="Analytics", variant=0,
        file_path=f"/uploads/images/{request_id}/analytics_0.png", prompt="p",
        screen_type="analytics", archetype="operations-dashboard",
        model="google/gemini-3-pro-image", provider="openrouter",
        prompt_version="v1", spec_json=spec_json,
    ))
    db.commit()
    db.close()


def _story_of(client, request_id: int) -> dict | None:
    body = client.get(f"/api/requests/{request_id}/preview").json()
    return body["generated_pages"]["attraction_images"][0]["story"]


def test_the_story_repeats_only_strings_the_screen_was_asked_to_draw(client):
    """The explanation under a screen has to be checkable against the screen."""
    request_id = _seed()
    _seed_screen(request_id, json.dumps({
        "subheading": "Performance Insights",
        "kpis": [{"label": "Monthly Revenue", "value": "$78,500"}, {"label": "Client Retention", "value": "91%"}],
        "primary_panel": {"title": "Revenue by Service"},
        "chart": {"title": "Monthly Bookings Trend", "labels": ["Jan"], "values": [25]},
        "ai": {
            "title": "Predict Peak Season Demand", "headline": "Pre-book 3 lift slots",
            "rationale": "Historical patterns suggest resource need", "confidence": "96% accuracy",
            "chips": ["Seasonal Planning", "Demand Forecasting"],
        },
    }))

    story = _story_of(client, request_id)
    assert story["subheading"] == "Performance Insights"
    assert story["tracks"] == ["Monthly Revenue", "Client Retention"]
    assert story["sections"] == ["Revenue by Service", "Monthly Bookings Trend"]
    assert story["ai"]["title"] == "Predict Peak Season Demand"
    assert story["ai"]["confidence"] == "96% accuracy"
    assert story["ai"]["chips"] == ["Seasonal Planning", "Demand Forecasting"]


def test_no_ai_module_on_the_screen_means_no_ai_claim_under_it(client):
    """An AI panel with no headline was never drawn. Saying otherwise would
    advertise AI in a demo that does not show any."""
    request_id = _seed()
    _seed_screen(request_id, json.dumps({
        "subheading": "Today's Snapshot",
        "ai": {"title": "AI Insights", "headline": "   ", "chips": ["ignored"]},
    }))

    assert _story_of(client, request_id)["ai"] is None


def test_a_screen_from_before_the_spec_was_kept_has_no_story(client):
    """Null means 'we cannot say' — the page renders nothing, not a blank."""
    request_id = _seed()
    _seed_screen(request_id, None)

    assert _story_of(client, request_id) is None


def test_an_unreadable_spec_never_takes_the_result_page_down(client):
    request_id = _seed()
    _seed_screen(request_id, "{not json at all")

    assert _story_of(client, request_id) is None


def test_progress_names_the_business_so_a_resumed_run_stays_personal(client):
    request_id = _seed()

    assert client.get(f"/api/requests/{request_id}/progress").json()["business_name"] == "Beacon Physiotherapy"


def test_customer_facing_routes_404_for_an_id_that_was_never_issued(client):
    """The id now comes from a URL a customer can edit or mistype."""
    assert client.get("/api/requests/999999/preview").status_code == 404
    assert client.get("/api/requests/999999/progress").status_code == 404
