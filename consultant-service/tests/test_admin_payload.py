"""Pins for W6 — the operator's cost view, and composites in the preview.

Two rules worth a test each: the money never appears on the lead-facing
payload, and a composite URL is only ever emitted when the file is really
on disk (a broken <img> in a prospect's preview is worse than no hero).
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
from app.pipeline import compositing


@pytest.fixture
def client(tmp_path, monkeypatch):
    from main import app
    from app.config import settings

    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path))
    return TestClient(app)


@pytest.fixture
def seeded_request(tmp_path):
    db = SessionLocal()
    req = Request(
        business_name="SmileBright Dental", business_description="d", industry="Dental Clinic",
        email="t@example.com", status="done", is_generating=False,
        consulting_recommendations_json=json.dumps({"recommended_ai_employees": [], "recommended_features": []}),
    )
    db.add(req)
    db.commit()

    images_dir = tmp_path / "images" / str(req.id)
    images_dir.mkdir(parents=True)
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buf, format="PNG")
    (images_dir / "dashboard_0.png").write_bytes(buf.getvalue())
    (images_dir / "dashboard_hero.png").write_bytes(buf.getvalue())
    (images_dir / "dashboard_detail_1.png").write_bytes(buf.getvalue())
    # detail_2 deliberately absent — a partial composite set is normal.

    db.add(GeneratedImage(
        request_id=req.id, role_id="dashboard", role_label="Dashboard", variant=0,
        file_path=f"/uploads/images/{req.id}/dashboard_0.png", prompt="p", screen_type="dashboard",
        archetype="operations-dashboard", model="google/gemini-3-pro-image",
        composition_variant="hero-intelligence", provider="openrouter",
        prompt_version="dashboard-image-v1+composition", qa_score=8.7, qa_issues=json.dumps(["minor blur"]),
    ))
    for purpose, model, cost, ok in [
        ("image", "google/gemini-3-pro-image", 0.1447, True),
        ("image", "google/gemini-3.1-flash-image", 0.0695, True),
        ("image", "google/gemini-3.1-flash-image", 0.0, False),
        ("image_qa", "google/gemini-2.5-flash", 0.0011, True),
        ("ui_spec", "google/gemini-2.5-flash", 0.0043, True),
    ]:
        db.add(AiUsageEvent(
            request_id=req.id, provider="openrouter", model=model, purpose=purpose,
            cost_usd=cost, success=ok,
        ))
    db.commit()
    yield req.id
    db.close()


def test_admin_payload_reports_cost_from_the_ledger(client, seeded_request):
    body = client.get(f"/api/requests/{seeded_request}/admin").json()
    cost = body["cost"]

    assert cost["total_usd"] == pytest.approx(0.2196, abs=1e-4)
    assert cost["images_usd"] == pytest.approx(0.2142, abs=1e-4)
    assert cost["images_generated"] == 2, "a failed image call is not a generated image"
    assert cost["cost_per_image_usd"] == pytest.approx(0.1071, abs=1e-4)
    assert cost["failed_calls"] == 1
    assert cost["by_purpose"]["image"]["calls"] == 3
    assert set(cost["by_model"]) == {
        "google/gemini-3-pro-image", "google/gemini-3.1-flash-image", "google/gemini-2.5-flash",
    }


def test_admin_payload_reports_what_produced_each_screen(client, seeded_request):
    screen = client.get(f"/api/requests/{seeded_request}/admin").json()["screens"][0]
    assert screen["model"] == "google/gemini-3-pro-image"
    assert screen["composition_variant"] == "hero-intelligence"
    assert screen["qa_score"] == 8.7
    assert screen["qa_issues"] == ["minor blur"]
    assert screen["hero_url"].endswith("dashboard_hero.png")


def test_cost_never_appears_on_the_lead_facing_preview(client, seeded_request):
    body = client.get(f"/api/requests/{seeded_request}/preview").json()
    assert "cost" not in body
    assert "cost" not in json.dumps(body).lower().replace("cost_usd", "")


def test_preview_exposes_composites_only_when_they_exist(client, seeded_request):
    image = client.get(f"/api/requests/{seeded_request}/preview").json()["generated_pages"]["attraction_images"][0]
    assert image["hero_url"].endswith("dashboard_hero.png")
    assert [u.rsplit("_", 1)[1] for u in image["detail_urls"]] == ["1.png"], "detail_2 is absent on disk"


def test_a_missing_composite_yields_null_not_a_guessed_url(tmp_path):
    assert compositing.variant_url("/uploads/images/9/dashboard_0.png", "hero", str(tmp_path)) is None


def test_admin_detail_404s_for_an_unknown_request(client):
    assert client.get("/api/requests/999999/admin").status_code == 404
