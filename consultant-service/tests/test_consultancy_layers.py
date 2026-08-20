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
        revenue_today="fees", module="{}", other_modules="none",
        engagement_register="reg",
    )
    assert "trigger" in prompt
    assert "One actor per step" in prompt
    assert "THIS module only" in prompt


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


def _chat_router(journey=None, governance=None, procedures=None, organization=None, checklists=None):
    """provider.chat replacement routing on prompt content; None → raise."""

    def chat(model, messages, **kwargs):
        prompt = messages[0]["content"]
        if "SERVICE BLUEPRINT" in prompt:
            payload = journey
        elif "GOVERNANCE" in prompt:
            payload = governance
        elif "ORGANIZATION" in prompt:
            payload = organization
        elif "CHECKLISTS" in prompt:
            payload = checklists
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
GOOD_CHECK = {"checklists": [{"name": "Daily open", "when": "each morning",
                              "items": ["Float counted", "Courts inspected"]}],
              "forms": [{"name": "Intake form", "purpose": "captures new members",
                         "fields": ["Name", "Phone"]}]}
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
    monkeypatch.setattr(extras.provider, "chat", _chat_router(GOOD_JOURNEY, GOOD_GOV, GOOD_PROCS, GOOD_ORG, GOOD_CHECK))
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
    # per-module SOP calls merged into one library, tagged with the module
    procs = json.loads(row.procedures_json)["procedures"]
    assert len(procs) == 2 and {p2["module"] for p2 in procs} == {"Scheduling", "Billing"}
    check = json.loads(row.checklists_json)
    assert check["checklists"][0]["name"] == "Daily open"
    assert check["forms"][0]["fields"] == ["Name", "Phone"]
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


def test_operations_manual_pdf(client, tmp_path, monkeypatch):
    from app.config import settings as cfg

    monkeypatch.setattr(cfg, "UPLOADS_DIR", str(tmp_path))
    db = SessionLocal()
    row = _seed(
        db, concept_name="BeaconOS",
        procedures_json=json.dumps({"procedures": [dict(GOOD_PROCS["procedures"][0], module="Scheduling")]}),
        org_json=json.dumps(GOOD_ORG),
        checklists_json=json.dumps(GOOD_CHECK),
    )
    r = client.get(f"/api/requests/{row.id}/export/pdf/operations")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    # not ready without any layer
    empty = _seed(db)
    assert client.get(f"/api/requests/{empty.id}/export/pdf/operations").status_code == 400
    db.close()


def test_engagement_zip_bundle(client, tmp_path, monkeypatch):
    import io as _io
    import zipfile

    from app.config import settings as cfg

    monkeypatch.setattr(cfg, "UPLOADS_DIR", str(tmp_path))
    db = SessionLocal()
    row = _seed(
        db, concept_name="BeaconOS", mvp_blueprint=MD, technical_plan=MD,
        procedures_json=json.dumps({"procedures": [dict(GOOD_PROCS["procedures"][0], module="Scheduling")]}),
        org_json=json.dumps(GOOD_ORG), checklists_json=json.dumps(GOOD_CHECK),
    )
    r = client.get(f"/api/requests/{row.id}/export/zip")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(_io.BytesIO(r.content)).namelist()
    assert len(names) == 3
    assert any("Volume I" in n for n in names)
    assert any("Volume III" in n for n in names)
    # nothing ready -> 400, never an empty bundle
    empty = _seed(db)
    assert client.get(f"/api/requests/{empty.id}/export/zip").status_code == 400
    db.close()


# ── the human review gate ────────────────────────────────────────────────


@pytest.fixture
def reviewer(monkeypatch):
    from app.config import settings as cfg

    monkeypatch.setattr(cfg, "REVIEW_TOKEN", "secret-token")
    monkeypatch.setattr(cfg, "REVIEW_MODE", "gate")
    return "secret-token"


def _pending_row(db):
    return _seed(
        db, review_status="pending", mvp_blueprint=MD, technical_plan=MD,
        concept_name="BeaconOS",
        modules_json=json.dumps(MODULES),
        journey_json=json.dumps(GOOD_JOURNEY),
        playbook_json=json.dumps({"quick_wins": [{"title": "w"}], "steps": [], "people_plan": {}}),
        ops_numbers_json=json.dumps([{"question": "visits?", "answer": "340 a month"}]),
        qa_report_json=json.dumps({"checks": [{"label": "Numbers trace", "passed": True, "note": ""}],
                                   "findings": [], "polish_applied": False}),
    )


def test_pending_run_shows_teaser_not_content(client, reviewer):
    db = SessionLocal()
    row = _pending_row(db)
    body = client.get(f"/api/requests/{row.id}/preview").json()
    assert body["pending_review"] is True
    assert "mvp_blueprint" not in body
    assert body["stats"]["modules"] == 2
    assert body["module_teasers"][0]["name"] == "Scheduling"
    assert body["numbers_echo"] == ["340 a month"]
    assert body["qa_checks"][0]["passed"] is True
    db.close()


def test_reviewer_token_reveals_everything(client, reviewer):
    db = SessionLocal()
    row = _pending_row(db)
    body = client.get(f"/api/requests/{row.id}/preview?review_token={reviewer}").json()
    assert body.get("pending_review") is None
    assert body["mvp_blueprint"] == MD
    assert body["review_status"] == "pending"
    assert body["qa_report"]["checks"][0]["label"] == "Numbers trace"
    db.close()


def test_pending_blocks_exports_without_token(client, reviewer, tmp_path, monkeypatch):
    from app.config import settings as cfg

    monkeypatch.setattr(cfg, "UPLOADS_DIR", str(tmp_path))
    db = SessionLocal()
    row = _pending_row(db)
    assert client.get(f"/api/requests/{row.id}/export/pdf/blueprint").status_code == 403
    assert client.get(f"/api/requests/{row.id}/export/zip").status_code == 403
    assert client.get(
        f"/api/requests/{row.id}/export/pdf/blueprint?review_token={reviewer}"
    ).content.startswith(b"%PDF")
    db.close()


def test_approve_releases_the_run(client, reviewer):
    db = SessionLocal()
    row = _pending_row(db)
    assert client.post(f"/api/requests/{row.id}/review/approve").status_code == 403
    r = client.post(f"/api/requests/{row.id}/review/approve?review_token={reviewer}")
    assert r.json()["review_status"] == "approved"
    body = client.get(f"/api/requests/{row.id}/preview").json()
    assert body["mvp_blueprint"] == MD
    db.close()


def test_reviewer_edits_flow_into_the_documents(client, reviewer):
    db = SessionLocal()
    row = _pending_row(db)
    new_md = "## Executive summary\nEdited by the partner.\n\n## How this makes money\nStill honest.\n"
    r = client.post(
        f"/api/requests/{row.id}/review/docs?review_token={reviewer}",
        data={"mvp_blueprint": new_md},
    )
    assert r.json()["saved"] is True
    body = client.get(f"/api/requests/{row.id}/preview?review_token={reviewer}").json()
    assert "Edited by the partner" in body["mvp_blueprint"]
    db.close()


def test_review_queue_lists_pending_newest_first(client, reviewer):
    db = SessionLocal()
    a = _pending_row(db)
    b = _pending_row(db)
    assert client.get("/api/requests/review-queue").status_code == 403
    queue = client.get(f"/api/requests/review-queue?review_token={reviewer}").json()["pending"]
    ids = [r["id"] for r in queue]
    assert ids.index(b.id) < ids.index(a.id)
    db.close()


def test_default_mode_serves_content_even_when_pending(client, monkeypatch):
    """Oversight is the default: a pending row serves its full content to
    the caller — review happens after delivery, never in the client's way."""
    from app.config import settings as cfg

    monkeypatch.setattr(cfg, "REVIEW_TOKEN", "")
    monkeypatch.setattr(cfg, "REVIEW_MODE", "on")
    db = SessionLocal()
    row = _pending_row(db)
    body = client.get(f"/api/requests/{row.id}/preview").json()
    assert body.get("pending_review") is None
    assert body["mvp_blueprint"] == MD
    db.close()


# ── the quality bench ────────────────────────────────────────────────────


def test_qa_experts_persist_report_and_polish_guard(client, monkeypatch):
    from app.pipeline import qa_experts

    db = SessionLocal()
    row = _seed(
        db, mvp_blueprint=MD,
        business_case_json=json.dumps({}), modules_json=json.dumps(MODULES),
    )

    def chat(model, messages, **kwargs):
        prompt = messages[0]["content"]
        if "NUMBERS AUDITOR" in prompt:
            payload = {"checks": [{"label": "Every figure traces to a client input", "passed": False,
                                   "note": "one bad figure"}],
                       "findings": [{"severity": "high", "where": "money", "issue": "invented $5",
                                     "fix": "remove"}]}
            return {"choices": [{"message": {"content": json.dumps(payload)}}], "usage": {}}
        if "STRUCTURE AUDITOR" in prompt:
            payload = {"checks": [{"label": "All canonical sections present", "passed": True, "note": "ok"}],
                       "findings": []}
            return {"choices": [{"message": {"content": json.dumps(payload)}}], "usage": {}}
        # polish pass: returns a corrupted doc missing required headings -> must be discarded
        return {"choices": [{"message": {"content": "totally different tiny doc"}}], "usage": {}}

    monkeypatch.setattr(qa_experts.provider, "chat", chat)
    qa_experts.review_quality(db, row.id)
    db.refresh(row)
    report = json.loads(row.qa_report_json)
    assert len(report["checks"]) == 2
    assert report["findings"][0]["issue"] == "invented $5"
    assert report["polish_applied"] is False
    assert row.mvp_blueprint == MD  # guarded: corrupted polish never replaces the doc
    db.close()


# ── accounts and ownership ───────────────────────────────────────────────


def _as_user(monkeypatch, email):
    from app import auth_client
    from app.routers import discovery as discovery_router
    from app.routers import requests as requests_router

    def resolver(authorization):
        return {"email": email, "name": "U"} if email else None

    monkeypatch.setattr(auth_client, "resolve_user", resolver)


def test_anonymous_cannot_start_an_engagement(client, monkeypatch):
    _as_user(monkeypatch, None)
    r = client.post("/api/requests", data={
        "business_name": "B", "business_description": "long enough description here",
        "email": "x@example.com",
    })
    assert r.status_code == 401
    assert client.post("/api/discovery/questions", data={
        "business_name": "B", "business_description": "d",
    }).status_code == 401
    assert client.post("/api/discovery/brief", data={
        "business_name": "B", "business_description": "d",
    }).status_code == 401


def test_owned_runs_are_private_to_their_account(client, monkeypatch):
    db = SessionLocal()
    row = _seed(db, owner_email="owner@example.com", mvp_blueprint=MD)

    _as_user(monkeypatch, "owner@example.com")
    assert client.get(f"/api/requests/{row.id}/preview").status_code == 200
    assert client.get(f"/api/requests/{row.id}/progress").status_code == 200

    _as_user(monkeypatch, "intruder@example.com")
    assert client.get(f"/api/requests/{row.id}/preview").status_code == 403
    assert client.get(f"/api/requests/{row.id}/progress").status_code == 403

    _as_user(monkeypatch, None)
    assert client.get(f"/api/requests/{row.id}/preview").status_code == 401
    db.close()


def test_legacy_and_showcase_runs_stay_public(client, monkeypatch):
    from app.config import settings as cfg

    db = SessionLocal()
    legacy = _seed(db)  # no owner: grandfathered public
    owned = _seed(db, owner_email="owner@example.com", mvp_blueprint=MD)
    monkeypatch.setattr(cfg, "SHOWCASE_IDS", str(owned.id))

    _as_user(monkeypatch, None)
    assert client.get(f"/api/requests/{legacy.id}/preview").status_code == 200
    # showcase listing makes an owned run public by explicit choice
    assert client.get(f"/api/requests/{owned.id}/preview").status_code == 200
    db.close()


def test_mine_lists_only_my_runs(client, monkeypatch):
    db = SessionLocal()
    mine = _seed(db, owner_email="me@example.com")
    _seed(db, owner_email="other@example.com")

    _as_user(monkeypatch, "me@example.com")
    body = client.get("/api/requests/mine").json()
    ids = [e["id"] for e in body["engagements"]]
    assert mine.id in ids
    assert all(
        db.get(Request, i).owner_email == "me@example.com" for i in ids
    )
    db.close()


def test_showcase_gallery_serves_cards(client, monkeypatch):
    from app.config import settings as cfg

    db = SessionLocal()
    row = _seed(
        db, concept_name="BeaconOS", industry="physio",
        modules_json=json.dumps(MODULES),
        journey_json=json.dumps(GOOD_JOURNEY),
        procedures_json=json.dumps({"procedures": GOOD_PROCS["procedures"]}),
    )
    monkeypatch.setattr(cfg, "SHOWCASE_IDS", f"{row.id}, 99999")
    _as_user(monkeypatch, None)
    body = client.get("/api/requests/showcase-gallery").json()
    assert len(body["showcase"]) == 1
    card = body["showcase"][0]
    assert card["concept_name"] == "BeaconOS"
    assert card["stats"]["modules"] == 2
    db.close()


def test_delete_is_reviewer_only_and_total(client, reviewer, tmp_path, monkeypatch):
    from app.config import settings as cfg

    monkeypatch.setattr(cfg, "UPLOADS_DIR", str(tmp_path))
    import os

    db = SessionLocal()
    row = _seed(db, mvp_blueprint=MD)
    rid = row.id
    img_dir = tmp_path / "images" / str(rid)
    img_dir.mkdir(parents=True)
    (img_dir / "a.png").write_bytes(b"x")

    assert client.delete(f"/api/requests/{rid}").status_code == 403
    r = client.delete(f"/api/requests/{rid}?review_token={reviewer}")
    assert r.json() == {"deleted": rid}
    assert client.get(f"/api/requests/{rid}/preview").status_code == 404
    assert not os.path.isdir(img_dir)
    db.close()


def test_oversight_mode_never_holds_the_client(client, reviewer, monkeypatch):
    """The default mode: the run is pending in the reviewer's queue, but
    the client sees everything immediately — review happens after
    delivery, not in the client's way."""
    from app.config import settings as cfg

    monkeypatch.setattr(cfg, "REVIEW_MODE", "on")
    db = SessionLocal()
    row = _pending_row(db)
    body = client.get(f"/api/requests/{row.id}/preview").json()
    assert body.get("pending_review") is None
    assert body["mvp_blueprint"] == MD
    assert body["review_status"] == "pending"  # still in the queue
    queue = client.get(f"/api/requests/review-queue?review_token={reviewer}").json()
    assert any(r["id"] == row.id for r in queue["pending"])
    db.close()


def test_public_id_slug_addresses_a_run(client, monkeypatch):
    from app.config import settings as cfg
    from app.routers import requests as rr

    monkeypatch.setattr(rr.orchestrator, "run", lambda request_id: None)
    monkeypatch.setattr(cfg, "MAX_CONCURRENT_GENERATIONS", 10_000)
    r = client.post("/api/requests", data={
        "business_name": "Slugged", "business_description": "a business with a slug link",
        "email": "t@example.com",
    }).json()
    slug = r["public_id"]
    assert slug and not slug.isdigit() and len(slug) >= 10
    # the slug resolves for its owner (autouse fixture signs us in as them)
    assert client.get(f"/api/requests/{slug}/progress").status_code == 200
    body = client.get(f"/api/requests/{slug}/preview").json()
    assert body["business_name"] == "Slugged"
    # a wrong slug is a clean 404
    assert client.get("/api/requests/not-a-real-slug/preview").status_code == 404


# ── the elite pass: decision memo, quantified case, evidence trail ───────


def test_blueprint_prompt_demands_the_decision_memo():
    prompt = render(
        "blueprint.j2", business_name="B", business_description="d", industry="i",
        revenue_today="r", site_research="none", business_model="x",
        target_customer_profile="", pain_points="[]", growth_opportunity="",
        consulting_summary="", recommended_ai_employees="[]", concept_name="C",
        roles="[]", modules="[]", business_case="{}", engagement_register="reg",
        modules_present=True,
    )
    assert "## The decision" in prompt
    assert "PROVE-THEN-AUTOMATE" in prompt
    assert "SCOPE GUARD" in prompt
    assert "Beyond this engagement" in prompt
    assert "SELECTIVITY" in prompt


def test_decompose_prompt_demands_quantified_financial_model():
    ctx = dict(
        business_name="B", business_description="d", industry="i", revenue_today="r",
        main_problem="m", desired_outcome="o", site_research="none", business_model="x",
        target_customer_profile="", pain_points="[]", growth_opportunity="",
        consulting_summary="", recommended_ai_employees="[]", recommended_features="[]",
        concept_name="C", min_modules=3, max_modules=7, operating_stage="operating",
        owner_numbers="- visits: 340", engagement_register="reg",
    )
    prompt = render("decompose.j2", **ctx)
    assert "financial_model" in prompt
    assert "missing_inputs" in prompt
    assert "Never guess a missing input" in prompt
    assert "Conservative" in prompt and "Upside" in prompt


def test_qa_bench_audits_decision_and_contradictions():
    comp = render(
        "qa_completeness.j2", engagement_register="reg", blueprint="doc",
        module_names="[]", journey_stages="[]", org_count=1, scoreboard_count=1,
        risks_count=1, procedures_count=1, checklists_count=1, quick_wins_count=1,
    )
    assert "The decision;" in comp
    assert "internal contradiction is a high finding" in comp
    nums = render("qa_numbers.j2", owner_numbers="none", business_case="{}", blueprint="doc")
    assert "conflicting values" in nums
    assert "No internal contradictions between figures" in nums


def _flow_text(flows):
    return " ".join(getattr(f, "text", "") or "" for f in flows)


def test_financial_model_renders_lines_scenarios_and_missing_inputs(client):
    from app.pipeline import export_pdf as ep

    bc = {"financial_model": {
        "lines": [{"item": "Failed re-attempts", "arithmetic": "12% of 900/day x $1.80 x 26 days",
                   "annual": "$60,700/year"}],
        "scenarios": [
            {"name": "Conservative", "assumption": "1 in 3 prevented", "impact": "$20,200/year, by your own figures"},
            {"name": "Expected", "assumption": "1 in 2 prevented", "impact": "$30,350/year, by your own figures"},
        ],
        "payback_note": "Divide the build quote by the Expected monthly figure above.",
        "missing_inputs": ["your fully-loaded hourly cost for finance staff"],
    }}
    text = _flow_text(ep._financial_model_flowables(bc))
    assert "Failed re-attempts" in text and "$60,700/year" in text
    assert "Conservative" in text and "1 in 3 prevented" in text
    assert "fully-loaded hourly cost" in text
    # fail-open: nothing produced, nothing rendered
    assert ep._financial_model_flowables({}) == []
    assert ep._financial_model_flowables({"financial_model": {}}) == []


def test_evidence_page_quotes_the_owner_verbatim(client):
    from app.pipeline import export_pdf as ep

    db = SessionLocal()
    row = _seed(
        db,
        ops_numbers_json=json.dumps([{"question": "No-shows per week?", "answer": "3 at $95"}]),
        revenue_today="per-visit fees",
        business_description=(
            "clinic\n\nCorrections and additions from the briefing chat:\n- closed Sundays"
        ),
    )
    flows = ep._evidence_flowables(
        row,
        {"financial_model": {"scenarios": [{"name": "Expected", "assumption": "half recovered"}]}},
        [{"metric": "no-shows", "baseline": "measure in week 1"}],
    )
    text = _flow_text(flows)
    assert "No-shows per week?" in text and "3 at $95" in text
    assert "per-visit fees" in text
    assert "closed Sundays" in text
    assert "half recovered" in text
    assert "no-shows" in text  # the week-1 measurement list
    assert "Method rule" in text
    db.close()


def test_decision_close_is_premium_and_signed(client, monkeypatch):
    from app.config import settings as cfg
    from app.pipeline import export_pdf as ep

    monkeypatch.setattr(cfg, "ENGAGEMENT_LEAD", "Roy Rizkallah - Managing Consultant")
    text = _flow_text(ep._decision_flowables())
    assert "$200" not in text
    assert "executive working session" in text.lower()
    assert "Roy Rizkallah" in text
    # unset lead: the sign-off line simply vanishes
    monkeypatch.setattr(cfg, "ENGAGEMENT_LEAD", "")
    assert "Roy Rizkallah" not in _flow_text(ep._decision_flowables())


# -- the hardening pass: deterministic guards the skeptics demanded --------


def test_arithmetic_sanitizer_drops_wrong_products_keeps_right_ones():
    from app.pipeline.decompose import _sanitize_financial_model

    bc = {"financial_model": {"lines": [
        # correct plain product (hyphenated words must not disqualify it)
        {"item": "no-shows", "arithmetic": "3 no-shows/week x $95 x 52 weeks", "annual": "$14,820/year"},
        # correct with an unstated x12 annualization step
        {"item": "monthly loss", "arithmetic": "45 hours x $10", "annual": "$5,400/year"},
        # WRONG product: the figure goes, the honest arithmetic stays
        {"item": "padded", "arithmetic": "3 x $95 x 52 weeks", "annual": "$19,000/year"},
        # additions are unverifiable here: left for the bench
        {"item": "sum", "arithmetic": "$100 + $200 per month", "annual": "$3,600/year"},
    ]}}
    _sanitize_financial_model(bc)
    lines = bc["financial_model"]["lines"]
    assert lines[0]["annual"] == "$14,820/year"
    assert lines[1]["annual"] == "$5,400/year"
    assert lines[2]["annual"] == ""
    assert lines[3]["annual"] == "$3,600/year"
    _sanitize_financial_model({})  # no model at all: a no-op, never a crash
    _sanitize_financial_model({"financial_model": ["not-a-dict"]})


def test_financial_render_guards_unlabeled_and_priced_content(client):
    from app.pipeline import export_pdf as ep

    fm = {"financial_model": {
        "lines": [{"item": "bare figure", "arithmetic": "", "annual": "$12,000"}],
        "scenarios": [{"name": "Expected", "assumption": "", "impact": "$9,999 appears from nowhere"}],
        "payback_note": "at our usual $6,000 build fee, payback is under 3 months",
        "missing_inputs": [],
    }}
    text = _flow_text(ep._financial_model_flowables(fm))
    assert "$12,000" not in text          # no figure without its computation
    assert "$9,999" not in text           # no scenario without its label
    assert "$6,000" not in text           # no BMV pricing, ever
    # a model carrying ONLY a clean payback note still renders
    only_note = {"financial_model": {"payback_note": "Divide the build quote by the Expected monthly figure."}}
    assert "Divide the build quote" in _flow_text(ep._financial_model_flowables(only_note))
    # malformed shape fails open, never crashes the export
    assert ep._financial_model_flowables({"financial_model": ["wat"]}) == []


def test_evidence_page_is_silent_for_legacy_rows(client):
    from app.pipeline import export_pdf as ep

    db = SessionLocal()
    row = _seed(db, business_name="Legacy", business_description="old run",
                revenue_today=None, main_problem=None)
    assert ep._evidence_flowables(row, {}, []) == []
    db.close()


def test_numbers_findings_route_to_polish_by_source_not_wording(client, monkeypatch):
    """A numbers finding worded without 'figure' or '$' must still reach the
    repair pass — routing is by auditor, not by sniffing prose."""
    from app.pipeline import qa_experts

    db = SessionLocal()
    row = _seed(db, mvp_blueprint=MD, business_case_json=json.dumps({}),
                modules_json=json.dumps(MODULES))
    polish_called = {"v": False}

    def chat(model, messages, **kwargs):
        prompt = messages[0]["content"]
        if "NUMBERS AUDITOR" in prompt:
            payload = {"checks": [], "findings": [{
                "severity": "high", "where": "scoreboard",
                "issue": "35 percent uplift target has no client input",
                "fix": "reword as direction only"}]}
            return {"choices": [{"message": {"content": json.dumps(payload)}}], "usage": {}}
        if "STRUCTURE AUDITOR" in prompt:
            return {"choices": [{"message": {"content": json.dumps({"checks": [], "findings": []})}}], "usage": {}}
        polish_called["v"] = True
        return {"choices": [{"message": {"content": "tiny"}}], "usage": {}}

    monkeypatch.setattr(qa_experts.provider, "chat", chat)
    qa_experts.review_quality(db, row.id)
    assert polish_called["v"] is True
    db.close()


def test_qa_numbers_prompt_demands_recompute_and_fraction_only_assumptions():
    nums = render("qa_numbers.j2", owner_numbers="none", business_case="{}", blueprint="doc")
    assert "RECOMPUTE" in nums
    assert "belongs in missing_inputs" in nums
    assert "BMV's own pricing must never appear" in nums


def test_numeric_annual_prints_as_money(client):
    from app.pipeline import export_pdf as ep

    fm = {"financial_model": {"lines": [
        {"item": "re-attempts", "arithmetic": "900 x 0.12 x $1.80 x 365", "annual": 70956},
    ]}}
    text = _flow_text(ep._financial_model_flowables(fm))
    assert "$70,956" in text
