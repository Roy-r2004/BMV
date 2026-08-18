"""Pins for the discovery step — tailored questions in, owner numbers out.

Three rules worth pinning: the questions endpoint NEVER fails closed (a
broken model call serves the stage-appropriate fallback), the intake
stores only well-formed Q&A pairs (client JSON is untrusted), and the
decompose prompt actually carries the numbers with the compute-only-from-
these rules — the whole feature is that contract.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.models import Request
from app.templating import render


@pytest.fixture
def client(monkeypatch):
    from main import app
    from app.config import settings
    from app.routers import requests as requests_router

    Base.metadata.create_all(bind=engine)
    # The intake starts the real pipeline in a thread — not in tests. The
    # no-op leaves every row is_generating=True forever, so the burst cap
    # would 429 later tests: lift it.
    monkeypatch.setattr(requests_router.orchestrator, "run", lambda request_id: None)
    monkeypatch.setattr(settings, "MAX_CONCURRENT_GENERATIONS", 10_000)
    return TestClient(app)


def _intake_form(**overrides):
    form = {
        "business_name": "Beacon Physiotherapy",
        "business_description": "Physio clinic, six therapists, insurance pre-approvals eat our evenings.",
        "email": "owner@example.com",
    }
    form.update(overrides)
    return form


# ── /api/discovery/questions ─────────────────────────────────────────────


def test_model_failure_serves_operating_fallback(client, monkeypatch):
    from app.routers import discovery

    monkeypatch.setattr(discovery.provider, "chat", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    r = client.post("/api/discovery/questions", data={
        "business_name": "Beacon", "business_description": "a clinic", "operating_stage": "operating",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "fallback"
    assert len(body["questions"]) >= 3
    assert all(q["label"] and q["why"] for q in body["questions"])


def test_opening_stage_gets_plan_flavored_fallback(client, monkeypatch):
    from app.routers import discovery

    monkeypatch.setattr(discovery.provider, "chat", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    r = client.post("/api/discovery/questions", data={
        "business_name": "New Bistro", "business_description": "a restaurant we are opening", "operating_stage": "opening",
    })
    ids = {q["id"] for q in r.json()["questions"]}
    # Plan questions, not history questions — an unopened business has no volumes.
    assert "planned-price" in ids
    assert "monthly-volume" not in ids


def test_ai_questions_pass_through_and_clamp(client, monkeypatch):
    from app.config import settings
    from app.routers import discovery

    many = [
        {"id": f"q-{i}", "label": f"Question {i}?", "placeholder": "e.g. 5", "why": "because"}
        for i in range(12)
    ]
    monkeypatch.setattr(
        discovery.provider, "chat",
        lambda *a, **k: {"choices": [{"message": {"content": json.dumps({"questions": many})}}], "usage": {}},
    )
    body = client.post("/api/discovery/questions", data={
        "business_name": "Beacon", "business_description": "a clinic",
    }).json()
    assert body["source"] == "ai"
    assert len(body["questions"]) == settings.MAX_DISCOVERY_QUESTIONS


def test_too_few_ai_questions_fall_back(client, monkeypatch):
    from app.routers import discovery

    monkeypatch.setattr(
        discovery.provider, "chat",
        lambda *a, **k: {"choices": [{"message": {"content": json.dumps({"questions": [{"id": "one", "label": "Only one?"}]})}}], "usage": {}},
    )
    body = client.post("/api/discovery/questions", data={
        "business_name": "Beacon", "business_description": "a clinic",
    }).json()
    assert body["source"] == "fallback"


# ── intake persistence ───────────────────────────────────────────────────


def test_intake_persists_stage_and_numbers_and_preview_echoes(client):
    pairs = [
        {"question": "How many visits a month?", "answer": "340"},
        {"question": "Average visit value?", "answer": "$85"},
    ]
    r = client.post("/api/requests", data=_intake_form(
        operating_stage="operating", ops_numbers=json.dumps(pairs),
    ))
    assert r.status_code == 200
    req_id = r.json()["id"]

    db = SessionLocal()
    try:
        row = db.get(Request, req_id)
        assert row.operating_stage == "operating"
        assert json.loads(row.ops_numbers_json) == pairs
    finally:
        db.close()

    preview = client.get(f"/api/requests/{req_id}/preview").json()
    assert preview["operating_stage"] == "operating"
    assert preview["ops_numbers"] == pairs


@pytest.mark.parametrize("bad", ["not json", "{}", json.dumps([{"question": "", "answer": "5"}]), json.dumps([1, 2])])
def test_intake_ignores_malformed_ops_numbers(client, bad):
    r = client.post("/api/requests", data=_intake_form(ops_numbers=bad, operating_stage="bogus-stage"))
    assert r.status_code == 200
    db = SessionLocal()
    try:
        row = db.get(Request, r.json()["id"])
        assert row.ops_numbers_json is None
        assert row.operating_stage is None
    finally:
        db.close()


def test_intake_bounds_pair_count_and_length(client):
    pairs = [{"question": f"Q{i}" * 200, "answer": "5"} for i in range(20)]
    r = client.post("/api/requests", data=_intake_form(ops_numbers=json.dumps(pairs)))
    stored = json.loads(SessionLocal().get(Request, r.json()["id"]).ops_numbers_json)
    assert len(stored) == 8
    assert all(len(p["question"]) <= 300 for p in stored)


# ── the prompt contract ──────────────────────────────────────────────────


def _decompose_context(**overrides):
    ctx = dict(
        business_name="Beacon", business_description="clinic", industry="physio",
        revenue_today="per-session fees", main_problem="no-shows", desired_outcome="evenings back",
        site_research="none", business_model="Appointments", target_customer_profile="patients",
        pain_points="[]", growth_opportunity="", consulting_summary="", recommended_ai_employees="[]",
        recommended_features="[]", concept_name="BeaconOS", min_modules=3, max_modules=7,
        operating_stage="operating", owner_numbers="- How many visits a month?: 340",
    )
    ctx.update(overrides)
    return ctx


def test_decompose_prompt_carries_numbers_and_rules():
    prompt = render("decompose.j2", **_decompose_context())
    assert "How many visits a month?: 340" in prompt
    assert "ONLY numbers you may compute with" in prompt
    assert "by your own figures" in prompt


def test_decompose_prompt_opening_register():
    prompt = render("decompose.j2", **_decompose_context(operating_stage="opening"))
    assert "NOT launched" in prompt
    assert "avoided hires" in prompt
    # And the operating register never claims the business is unlaunched.
    assert "NOT launched" not in render("decompose.j2", **_decompose_context())
