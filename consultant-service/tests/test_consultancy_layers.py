"""Pins for the consultancy layers — journey, governance, procedures,
quick wins, cost of inaction, and the PDF deliverables.

The contracts worth pinning: baselines can only be owner numbers or
"measure in week 1" (the prompt carries the rule), each extras layer
fails open ALONE, journey backstage ids are validated against real
module ids, and the PDF routes return a real PDF for a ready document
and a clean 400 before that.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.models import Request
from app.pipeline import extras
from app.templating import render


@pytest.fixture
def client():
    from main import app

    Base.metadata.create_all(bind=engine)
    return TestClient(app)


def _seed(db, **overrides):
    row = Request(
        business_name="Beacon Physiotherapy", business_description="clinic",
        email="t@example.com", status="done", is_generating=False,
    )
    for k, v in overrides.items():
        setattr(row, k, v)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


MODULES = [
    {"id": "scheduling", "name": "Scheduling", "purpose": "books visits",
     "users": ["owner"], "spec": {"ai": {"role": "books"}, "kpis": ["no-shows"]}},
    {"id": "billing", "name": "Billing", "purpose": "bills visits",
     "users": ["owner"], "spec": None},
]


# ── prompt contracts ─────────────────────────────────────────────────────


def test_governance_prompt_carries_baseline_rule():
    prompt = render(
        "governance.j2", business_name="B", business_description="d",
        operating_stage="operating", owner_numbers="- visits: 340",
        modules="[]", business_case="{}", engagement_register="reg",
    )
    assert "measure in week 1" in prompt
    assert "ONLY permitted baselines" in prompt
    assert "NEVER an invented figure" in prompt


def test_journey_prompt_demands_module_ids_and_their_vocabulary():
    prompt = render(
        "journey.j2", business_name="B", business_description="d",
        target_customer_profile="", pain_points="[]", modules="[]",
        engagement_register="reg",
    )
    assert "exact ids" in prompt
    assert "Never generic" in prompt


def test_procedures_prompt_is_franchise_shaped():
    prompt = render(
        "procedures.j2", business_name="B", business_description="d",
        revenue_today="fees", modules="[]", engagement_register="reg",
    )
    assert "trigger" in prompt
    assert "One actor per step" in prompt


def test_playbook_prompt_demands_quick_wins_and_horizons():
    prompt = render(
        "playbook.j2", business_name="B", business_description="d", industry="i",
        revenue_today="r", main_problem="m", desired_outcome="o", budget_range="b",
        timeline="t", site_research="none", concept_name="C", modules="[]", business_case="{}",
        engagement_register="reg",
    )
    assert "QUICK WINS" in prompt
    assert "no software at all" in prompt
    assert "never a calendar date" in prompt


def test_decompose_prompt_demands_cost_of_inaction():
    ctx = dict(
        business_name="B", business_description="d", industry="i", revenue_today="r",
        main_problem="m", desired_outcome="o", site_research="none", business_model="x",
        target_customer_profile="", pain_points="[]", growth_opportunity="",
        consulting_summary="", recommended_ai_employees="[]", recommended_features="[]",
        concept_name="C", min_modules=3, max_modules=7, operating_stage="operating",
        owner_numbers="none provided", engagement_register="reg",
    )
    assert "cost_of_inaction" in render("decompose.j2", **ctx)


# ── extras stage: fail-open per layer, validation ────────────────────────


def _chat_router(journey=None, governance=None, procedures=None, organization=None):
    """provider.chat replacement routing on prompt content; None → raise."""

    def chat(model, messages, **kwargs):
        prompt = messages[0]["content"]
        if "SERVICE BLUEPRINT" in prompt:
            payload = journey
        elif "GOVERNANCE" in prompt:
            payload = governance
        elif "ORGANIZATION" in prompt:
            payload = organization
        else:
            payload = procedures
        if payload is None:
            raise RuntimeError("boom")
        return {"choices": [{"message": {"content": json.dumps(payload)}}], "usage": {}}

    return chat


GOOD_JOURNEY = {"stages": [
    {"stage": "Booking", "customer_action": "books", "frontstage": "a page",
     "backstage_modules": ["scheduling", "not-a-real-module"]},
]}
GOOD_GOV = {"scoreboard": [{"metric": "no-shows", "baseline": "measure in week 1",
                            "target": "down", "owner": "you", "review": "weekly"}],
            "risks": [{"risk": "staff bypass", "mitigation": "train", "who_feels_it": "front desk"}]}
GOOD_PROCS = {"procedures": [{"name": "Handling an inquiry", "trigger": "a call",
                              "steps": [{"actor": "ai", "step": "log it"}],
                              "exceptions": [{"when": "urgent", "then": "call owner"}]}]}
GOOD_ORG = {"roles": [
    {"role": "Owner", "type": "human", "responsibilities": ["approve"],
     "decides_alone": "pricing", "hands_off": "never"},
    {"role": "Scheduling", "type": "ai", "responsibilities": ["book visits"],
     "decides_alone": "slot picks", "hands_off": "conflicts -> owner"},
], "change_impact": [
    {"role": "Owner", "what_changes": "reviews a dashboard", "must_learn": "the approval queue"},
]}


def test_extras_persist_and_validate(monkeypatch, client):
    db = SessionLocal()
    row = _seed(db)
    monkeypatch.setattr(extras.provider, "chat", _chat_router(GOOD_JOURNEY, GOOD_GOV, GOOD_PROCS, GOOD_ORG))
    extras.build_extras(db, row.id, {"target_customer_profile": "", "pain_points": []},
                        {"modules": MODULES, "business_case": {}})
    db.refresh(row)
    journey = json.loads(row.journey_json)
    # unknown module ids are filtered, real ones survive
    assert journey["stages"][0]["backstage_modules"] == ["scheduling"]
    assert json.loads(row.scoreboard_json)[0]["baseline"] == "measure in week 1"
    assert json.loads(row.risks_json)[0]["risk"] == "staff bypass"
    assert json.loads(row.procedures_json)["procedures"][0]["name"] == "Handling an inquiry"
    org = json.loads(row.org_json)
    assert org["roles"][1]["type"] == "ai"
    assert org["change_impact"][0]["role"] == "Owner"
    db.close()


def test_one_layer_failing_never_sinks_the_others(monkeypatch, client):
    db = SessionLocal()
    row = _seed(db)
    monkeypatch.setattr(extras.provider, "chat", _chat_router(None, GOOD_GOV, None, None))
    extras.build_extras(db, row.id, {}, {"modules": MODULES, "business_case": {}})
    db.refresh(row)
    assert row.journey_json is None
    assert row.procedures_json is None
    assert row.org_json is None
    assert json.loads(row.scoreboard_json)[0]["metric"] == "no-shows"
    db.close()


def test_no_modules_means_no_calls(monkeypatch, client):
    calls = []
    monkeypatch.setattr(extras.provider, "chat", lambda *a, **k: calls.append(1))
    db = SessionLocal()
    row = _seed(db)
    extras.build_extras(db, row.id, {}, {"modules": [], "business_case": {}})
    assert calls == []
    db.close()


# ── preview exposure ─────────────────────────────────────────────────────


def test_preview_exposes_layers(client):
    db = SessionLocal()
    row = _seed(
        db,
        journey_json=json.dumps(GOOD_JOURNEY),
        scoreboard_json=json.dumps(GOOD_GOV["scoreboard"]),
        risks_json=json.dumps(GOOD_GOV["risks"]),
        procedures_json=json.dumps(GOOD_PROCS),
    )
    preview = client.get(f"/api/requests/{row.id}/preview").json()
    assert preview["journey"]["stages"][0]["stage"] == "Booking"
    assert preview["scoreboard"][0]["owner"] == "you"
    assert preview["risks"][0]["who_feels_it"] == "front desk"
    assert preview["procedures"][0]["trigger"] == "a call"
    db.close()


def test_preview_layers_absent_for_old_runs(client):
    db = SessionLocal()
    row = _seed(db)
    preview = client.get(f"/api/requests/{row.id}/preview").json()
    assert preview["journey"] is None
    assert preview["scoreboard"] == [] and preview["risks"] == [] and preview["procedures"] == []
    db.close()


# ── the PDF deliverables ─────────────────────────────────────────────────

MD = "## Executive summary\nA plan.\n\n### Part one\n- **Bold:** detail\n1. do this\n"


def test_blueprint_pdf_roundtrip(client, tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path))
    db = SessionLocal()
    row = _seed(
        db, mvp_blueprint=MD, concept_name="BeaconOS",
        journey_json=json.dumps(GOOD_JOURNEY),
        scoreboard_json=json.dumps(GOOD_GOV["scoreboard"]),
    )
    r = client.get(f"/api/requests/{row.id}/export/pdf/blueprint")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    assert len(r.content) > 1500
    db.close()


def test_technical_pdf_and_not_ready(client, tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path))
    db = SessionLocal()
    ready = _seed(db, technical_plan=MD, procedures_json=json.dumps(GOOD_PROCS))
    empty = _seed(db)
    assert client.get(f"/api/requests/{ready.id}/export/pdf/technical").content.startswith(b"%PDF")
    assert client.get(f"/api/requests/{empty.id}/export/pdf/blueprint").status_code == 400
    assert client.get(f"/api/requests/{ready.id}/export/pdf/nope").status_code == 404
    db.close()


# ── the engagement register ──────────────────────────────────────────────


def test_register_capability_scopes_to_the_one_problem():
    from app.pipeline._shared import build_engagement_register

    reg = build_engagement_register("capability", "yes", "missed calls", None)
    assert "ONE CAPABILITY" in reg
    assert "missed calls" in reg
    assert "Do not propose modules" in reg


def test_register_no_ai_means_no_ai():
    from app.pipeline._shared import build_engagement_register

    reg = build_engagement_register("full", "no", None, None)
    assert "WHOLE BUSINESS" in reg
    assert "NO AI" in reg
    assert "empty AI list is the correct answer" in reg


def test_register_reaches_the_prompts():
    ctx = dict(
        business_name="B", business_description="d", industry="i", revenue_today="r",
        main_problem="m", desired_outcome="o", site_research="none", business_model="x",
        target_customer_profile="", pain_points="[]", growth_opportunity="",
        consulting_summary="", recommended_ai_employees="[]", recommended_features="[]",
        concept_name="C", min_modules=3, max_modules=7, operating_stage="operating",
        owner_numbers="none provided",
        engagement_register="SCOPE-SENTINEL-XYZ",
    )
    assert "SCOPE-SENTINEL-XYZ" in render("decompose.j2", **ctx)
    assert "SCOPE-SENTINEL-XYZ" in render(
        "organization.j2", business_name="B", business_description="d",
        modules="[]", engagement_register="SCOPE-SENTINEL-XYZ",
    )


def test_intake_persists_engagement_type(client, monkeypatch):
    from app.config import settings as cfg
    from app.routers import requests as requests_router

    monkeypatch.setattr(requests_router.orchestrator, "run", lambda request_id: None)
    monkeypatch.setattr(cfg, "MAX_CONCURRENT_GENERATIONS", 10_000)
    r = client.post("/api/requests", data={
        "business_name": "Beacon", "business_description": "clinic desc long enough here",
        "email": "t@example.com", "engagement_type": "capability",
    })
    db = SessionLocal()
    row = db.get(Request, r.json()["id"])
    assert row.engagement_type == "capability"
    preview = client.get(f"/api/requests/{row.id}/preview").json()
    assert preview["engagement_type"] == "capability"
    r2 = client.post("/api/requests", data={
        "business_name": "Beacon", "business_description": "clinic desc long enough here",
        "email": "t@example.com", "engagement_type": "whatever",
    })
    assert db.get(Request, r2.json()["id"]).engagement_type is None
    db.close()


def test_discovery_capability_fallback(client, monkeypatch):
    from app.routers import discovery

    monkeypatch.setattr(discovery.provider, "chat", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    body = client.post("/api/discovery/questions", data={
        "business_name": "Beacon", "business_description": "a clinic",
        "operating_stage": "operating", "engagement_type": "capability",
    }).json()
    ids = {q["id"] for q in body["questions"]}
    assert "problem-frequency" in ids
    assert "monthly-volume" not in ids


def test_blueprint_pdf_carries_all_layers(client, tmp_path, monkeypatch):
    from app.config import settings as cfg

    monkeypatch.setattr(cfg, "UPLOADS_DIR", str(tmp_path))
    db = SessionLocal()
    row = _seed(
        db, mvp_blueprint=MD, concept_name="BeaconOS",
        journey_json=json.dumps(GOOD_JOURNEY),
        scoreboard_json=json.dumps(GOOD_GOV["scoreboard"]),
        risks_json=json.dumps(GOOD_GOV["risks"]),
        org_json=json.dumps(GOOD_ORG),
        playbook_json=json.dumps({"quick_wins": [{"title": "Call your list", "detail": "d", "no_software": True}],
                                  "steps": [{"phase": "before", "who": "you", "title": "Export data",
                                             "detail": "d", "horizon": "week 1"}],
                                  "people_plan": {}}),
        business_case_json=json.dumps({"customers": {"segments": ["patients"], "channels": ["referrals"],
                                                     "how_kept": "reminders"}}),
    )
    r = client.get(f"/api/requests/{row.id}/export/pdf/blueprint")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert len(r.content) > 4000
    db.close()
