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

from app.config import settings
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
    """The intake is bounded — and the bound is whatever the interview can
    actually collect, not a number of its own.

    It was a flat 8, from when one fixed round asked at most 6. The adaptive
    interview runs up to INTERVIEW_MAX_ROUNDS rounds of
    INTERVIEW_MAX_PER_ROUND questions, so a hardcoded 8 would silently throw
    away the last answers a client typed — after asking them for those
    answers. Asserted against the setting so the two cannot drift apart."""
    limit = max(8, settings.INTERVIEW_MAX_ROUNDS * settings.INTERVIEW_MAX_PER_ROUND)
    pairs = [{"question": f"Q{i}" * 200, "answer": "5"} for i in range(limit + 12)]
    r = client.post("/api/requests", data=_intake_form(ops_numbers=json.dumps(pairs)))
    stored = json.loads(SessionLocal().get(Request, r.json()["id"]).ops_numbers_json)
    assert len(stored) == limit, "the intake must bound how many pairs a client can post"
    assert all(len(p["question"]) <= 300 for p in stored)


def test_intake_keeps_every_answer_a_full_interview_can_collect(client):
    """The complementary half: the bound must never cut into real answers.

    A client who sits through every round and answers every question has
    given us the most the product can ask for. Losing any of it is worse
    than never having asked."""
    most = settings.INTERVIEW_MAX_ROUNDS * settings.INTERVIEW_MAX_PER_ROUND
    pairs = [{"question": f"Question {i}?", "answer": str(i)} for i in range(most)]
    r = client.post("/api/requests", data=_intake_form(ops_numbers=json.dumps(pairs)))
    stored = json.loads(SessionLocal().get(Request, r.json()["id"]).ops_numbers_json)
    assert len(stored) == most, f"{most - len(stored)} answers the client typed were dropped"


# ── the prompt contract ──────────────────────────────────────────────────


def _decompose_context(**overrides):
    ctx = dict(
        business_name="Beacon", business_description="clinic", industry="physio",
        revenue_today="per-session fees", main_problem="no-shows", desired_outcome="evenings back",
        site_research="none", business_model="Appointments", target_customer_profile="patients",
        pain_points="[]", growth_opportunity="", consulting_summary="", recommended_ai_employees="[]",
        recommended_features="[]", concept_name="BeaconOS", min_modules=3, max_modules=7,
        operating_stage="operating", owner_numbers="- How many visits a month?: 340",
        engagement_register="reg",
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


# ── the pre-launch briefing chat ─────────────────────────────────────────


def test_brief_opening_turn(client, monkeypatch):
    from app.routers import discovery

    captured = {}

    def chat(model, messages, **kwargs):
        captured["prompt"] = messages[0]["content"]
        return {"choices": [{"message": {"content": json.dumps(
            {"reply": "You run a physio clinic...", "brief_addendum": None}
        )}}], "usage": {}}

    monkeypatch.setattr(discovery.provider, "chat", chat)
    body = client.post("/api/discovery/brief", data={
        "business_name": "Beacon", "business_description": "a clinic with six therapists",
        "operating_stage": "operating", "engagement_type": "capability",
        "main_problem": "missed calls",
        "ops_numbers": json.dumps([{"question": "Missed calls/week?", "answer": "25"}]),
    }).json()
    assert body["ok"] is True
    assert body["reply"].startswith("You run")
    assert body["brief_addendum"] is None
    # the numbers reached the consultant
    assert "Missed calls/week?: 25" in captured["prompt"]
    assert "(empty)" in captured["prompt"]
    # The engagement register's scope claim must NOT. This used to assert
    # "ONE CAPABILITY" was in the prompt, and that is the sentence that made
    # the playback tell a pilates-studio owner "this engagement will blueprint
    # a new booking app capability" — announcing a build one screen before the
    # diagnosis that exists to find out whether one is warranted. The consultant
    # is told instead that nothing has been decided.
    assert "ONE CAPABILITY" not in captured["prompt"]
    assert "NOTHING HAS BEEN DECIDED" in captured["prompt"]


def test_brief_correction_turn_carries_conversation_and_addendum(client, monkeypatch):
    from app.routers import discovery

    captured = {}

    def chat(model, messages, **kwargs):
        captured["prompt"] = messages[0]["content"]
        return {"choices": [{"message": {"content": json.dumps(
            {"reply": "Got it — eight therapists.", "brief_addendum": "- Eight therapists, not six"}
        )}}], "usage": {}}

    monkeypatch.setattr(discovery.provider, "chat", chat)
    body = client.post("/api/discovery/brief", data={
        "business_name": "Beacon", "business_description": "a clinic",
        "messages": json.dumps([
            {"role": "assistant", "content": "You run a clinic with six therapists..."},
            {"role": "user", "content": "We actually have eight therapists"},
        ]),
    }).json()
    assert body["ok"] is True
    assert "eight" in body["reply"]
    assert body["brief_addendum"] == "- Eight therapists, not six"
    assert "CLIENT: We actually have eight therapists" in captured["prompt"]


def test_brief_fails_open(client, monkeypatch):
    from app.routers import discovery

    monkeypatch.setattr(discovery.provider, "chat", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    body = client.post("/api/discovery/brief", data={
        "business_name": "Beacon", "business_description": "a clinic",
    }).json()
    assert body == {"ok": False}


def test_brief_tolerates_malformed_history(client, monkeypatch):
    from app.routers import discovery

    monkeypatch.setattr(discovery.provider, "chat", lambda *a, **k: {
        "choices": [{"message": {"content": json.dumps({"reply": "ok", "brief_addendum": None})}}],
        "usage": {},
    })
    body = client.post("/api/discovery/brief", data={
        "business_name": "Beacon", "business_description": "a clinic",
        "messages": "not json", "ops_numbers": "also not json",
    }).json()
    assert body["ok"] is True


# ── the brief's fact list and what each answer settles ───────────────────


PROBLEM = "I run a pilates studio. We charge $22 a class and the 6pm class is always full."


def test_scope_always_asks_for_the_two_facts_the_engagement_launches_on():
    from app.routers import discovery

    for raw in ({}, {"facts": [{"key": "price", "label": "What you charge"}]}, "junk"):
        got = discovery.shape_scope(raw, PROBLEM)
        fields = {f["field"] for f in got["facts"]}
        assert {"business_name", "business_description"} <= fields
        assert discovery.FACTS_MIN <= len(got["facts"]) <= discovery.FACTS_MAX


def test_scope_bounds_a_runaway_fact_list():
    from app.routers import discovery

    raw = {"question": "Should the studio raise its evening prices?",
           "facts": [{"key": f"f{i}", "label": f"Fact {i}"} for i in range(80)]}
    got = discovery.shape_scope(raw, PROBLEM)
    assert len(got["facts"]) == discovery.FACTS_MAX
    assert got["question"] == raw["question"]


def test_scope_keeps_a_value_only_when_the_quote_is_theirs():
    from app.routers import discovery

    raw = {"facts": [
        {"key": "price", "label": "What you charge", "value": "$22 a class", "quote": "We charge $22 a class"},
        {"key": "costs", "label": "Monthly costs", "value": "$4,000", "quote": "rent is $4,000 a month"},
        {"key": "price2", "label": "Evening price", "value": "$30", "quote": "We charge $22 a class"},
    ]}
    by = {f["key"]: f for f in discovery.shape_scope(raw, PROBLEM)["facts"]}
    assert by["price"]["status"] == "got" and by["price"]["value"] == "$22 a class"
    # a quote she never wrote, and a value whose number is not in the quote
    assert by["costs"]["status"] == "need" and by["costs"]["value"] == ""
    assert by["price2"]["status"] == "need" and by["price2"]["value"] == ""


def _facts():
    return [{"key": "price", "group": "Money", "label": "What you charge", "field": "", "status": "need", "value": ""},
            {"key": "costs", "group": "Money", "label": "Monthly costs", "field": "", "status": "estimate", "value": ""},
            {"key": "volume", "group": "Customers", "label": "Classes a week", "field": "", "status": "need", "value": ""}]


def test_fact_updates_drop_numbers_they_never_gave():
    from app.routers import discovery

    texts = [PROBLEM, "Six classes a day, six days a week"]
    updates, _ = discovery.shape_fact_updates(
        [{"key": "price", "value": "$22 a class"}, {"key": "volume", "value": "40 a week"},
         {"key": "nope", "value": "$22"}, {"key": "price", "value": ""}], [], _facts(), texts)
    assert updates == [{"key": "price", "value": "$22 a class"}]


def test_fact_updates_never_overwrite_what_they_said_they_do_not_know():
    from app.routers import discovery

    updates, _ = discovery.shape_fact_updates(
        [{"key": "costs", "value": "$22"}], [], _facts(), [PROBLEM])
    assert updates == []


def test_new_facts_are_capped_per_round_and_never_duplicate():
    from app.routers import discovery

    new = [{"label": "Price"}] + [{"key": f"extra_{i}", "label": f"Extra {i}"} for i in range(10)]
    new.insert(1, {"key": "price", "label": "What you charge again"})
    _, added = discovery.shape_fact_updates([], new, _facts(), [PROBLEM])
    assert len(added) == discovery.FACTS_ADDED_PER_ROUND
    assert "price" not in [a["key"] for a in added]
    assert all(a["status"] == "need" and a["value"] == "" for a in added)
