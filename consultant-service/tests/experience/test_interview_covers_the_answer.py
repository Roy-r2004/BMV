"""The interview does not ask twice, and the name is stored as a name."""
import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import Base, engine
from app.routers import discovery


def _facts():
    return [
        {"key": "business_name", "group": "The business", "label": "Business name", "field": "business_name", "status": "need", "value": ""},
        {"key": "price", "group": "Money", "label": "Price per booking", "field": "", "status": "need", "value": ""},
    ]


@pytest.fixture
def client(monkeypatch):
    from main import app
    from app.routers import requests as requests_router

    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(requests_router.orchestrator, "run", lambda request_id: None)
    monkeypatch.setattr(settings, "MAX_CONCURRENT_GENERATIONS", 10_000)
    return TestClient(app)


def _round(client, monkeypatch, reply, known):
    prompts = []

    def fake_chat(model, messages, max_tokens=None):
        prompts.append(messages[0]["content"])
        return {"choices": [{"message": {"content": json.dumps(reply)}}], "usage": {}}

    monkeypatch.setattr(discovery.provider, "chat", fake_chat)
    response = client.post("/api/discovery/interview", data={
        "operating_stage": "opening", "main_problem": "I want to open a home cleaning app in Dubai.", "round": "2",
        "known": json.dumps(known), "facts": json.dumps(_facts()), "ops_numbers": "[]", "asked": "[]",
    }, headers={"Authorization": "Bearer t"})
    assert response.status_code == 200
    return response.json(), prompts[0]


KNOWN = {"business_name": "My new business is called CleanHour.", "business_description": "A cleaning app"}
ASKS_NAME_AGAIN = {"id": "name", "label": "What is the name of the business?", "field": "business_name", "fills": ["business_name"]}
ASKS_PRICE = {"id": "price", "label": "What will one booking cost?", "field": "", "fills": ["price"]}


def test_a_field_already_answered_is_not_asked_again(client, monkeypatch):
    out, _ = _round(client, monkeypatch, {"questions": [ASKS_NAME_AGAIN, ASKS_PRICE], "updates": []}, KNOWN)
    assert [q["id"] for q in out["questions"]] == ["price"]


def test_the_model_is_told_the_field_is_answered(client, monkeypatch):
    _, prompt = _round(client, monkeypatch, {"questions": [ASKS_PRICE], "updates": []}, KNOWN)
    line = next(l for l in prompt.splitlines() if l.startswith("- business_name ["))
    assert "STILL NEEDED" not in line and "My new business is called CleanHour." in line


def test_an_answered_field_settles_its_fact_and_is_never_estimated(client, monkeypatch):
    out, _ = _round(client, monkeypatch, {"questions": [], "updates": []}, KNOWN)
    assert "business_name" in {u["key"] for u in out["updates"]}
    assert "business_name" not in out["estimate_rest"]


def test_the_models_short_value_is_kept_over_the_sentence(client, monkeypatch):
    out, _ = _round(client, monkeypatch, {"questions": [ASKS_PRICE], "updates": [{"key": "business_name", "value": "CleanHour"}]}, KNOWN)
    assert [u["value"] for u in out["updates"] if u["key"] == "business_name"] == ["CleanHour"]


def test_the_engagement_is_named_from_the_brief_not_the_sentence(client):
    from app.database import SessionLocal
    from app.models import Request

    brief = {"question": "Is there a business in it?", "facts": [{**_facts()[0], "status": "got", "value": "CleanHour"}]}
    r = client.post("/api/requests", data={"business_name": "My new business is called CleanHour.", "business_description": "A cleaning app",
                                           "email": "a@example.com", "brief": json.dumps(brief)}, headers={"Authorization": "Bearer t"})
    assert r.status_code == 200
    db = SessionLocal()
    assert db.get(Request, r.json()["id"]).business_name == "CleanHour"
    db.close()
