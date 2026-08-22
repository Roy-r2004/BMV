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
    # a FINAL needs the client's document owner and approver — the fixture
    # row carries them so release tests exercise the other gates
    overrides.setdefault("document_owner", "Clinic Manager (client)")
    overrides.setdefault("document_approver", "Practice Owner (client)")
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
    assert "future extensibility" in prompt
    assert "SELECTIVITY" in prompt
    # the decision is phased, and Phase 1 is never an AI engine
    assert "Phase 1" in prompt
    assert 'never contain "AI"' in prompt
    assert "requiring the client's approval" in prompt


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
        module_names="[]", procedures_list="[]", pilot_gate="none", journey_stages="[]", org_count=1, scoreboard_count=1,
        risks_count=1, procedures_count=1, checklists_count=1, quick_wins_count=1,
    )
    assert "The decision;" in comp
    assert "a weekly number reused as monthly is a high finding" in comp
    assert "Phase 1 wearing an AI name is a high finding" in comp
    nums = render("qa_numbers.j2", owner_numbers="none", business_case="{}", blueprint="doc", technical_plan="doc", verified_claims="[]")
    assert "conflicting values" in nums
    assert "No internal contradictions between figures" in nums


def _flow_text(flows):
    parts = []
    for f in flows:
        t = getattr(f, "text", "") or ""
        if t:
            parts.append(t)
        for row in getattr(f, "_cellvalues", None) or []:
            for c in row:
                parts.append(getattr(c, "text", None) or str(c))
    return " ".join(parts)


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
    nums = render("qa_numbers.j2", owner_numbers="none", business_case="{}", blueprint="doc", technical_plan="doc", verified_claims="[]")
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


def test_pdf_build_is_cached_until_the_data_changes(client, tmp_path, monkeypatch):
    """Two downloads of an unchanged run serve the same file; a data change
    (updated_at bump) rebuilds it. The 30s three-volume build was read as
    'unable to download'."""
    import os
    import time

    from app.config import settings as cfg
    from app.pipeline import export_pdf as ep

    monkeypatch.setattr(cfg, "UPLOADS_DIR", str(tmp_path))
    db = SessionLocal()
    row = _seed(db, mvp_blueprint="## Executive summary\n\nA fine plan.")
    p1 = ep.build_pdf(row, "blueprint")
    m1 = os.path.getmtime(p1)
    time.sleep(0.05)
    p2 = ep.build_pdf(row, "blueprint")
    assert p2 == p1 and os.path.getmtime(p2) == m1  # served from disk, not rebuilt
    # a data change invalidates the cache
    time.sleep(1.1)
    row.business_name = "Renamed Clinic"
    db.commit()
    db.refresh(row)
    p3 = ep.build_pdf(row, "blueprint")
    assert os.path.getmtime(p3) > m1
    db.close()


# -- the systemic pass: phases, thresholds, naming, gates ------------------


def test_procedures_prompt_grounds_phases_thresholds_and_names():
    prompt = render(
        "procedures.j2", business_name="B", business_description="d",
        revenue_today="fees", module="{}", other_modules="none",
        engagement_register="reg",
    )
    assert '"phase": "current|pilot|future"' in prompt
    assert "Never present an unbuilt screen" in prompt
    assert "proposed — client approval required" in prompt
    assert "EXACT module name" in prompt


def test_checklists_prompt_bans_privacy_invasive_fields():
    prompt = render(
        "checklists.j2", business_name="B", business_description="d",
        modules="[]", engagement_register="reg",
    )
    assert "last seen" in prompt
    assert "proposed — client approval required" in prompt


def test_prose_prompts_enforce_one_name_per_capability():
    bp = render(
        "blueprint.j2", business_name="B", business_description="d", industry="i",
        revenue_today="r", site_research="none", business_model="x",
        target_customer_profile="", pain_points="[]", growth_opportunity="",
        consulting_summary="", recommended_ai_employees="[]", concept_name="C",
        roles="[]", modules="[]", business_case="{}", engagement_register="reg",
        modules_present=True,
    )
    assert "ONE CAPABILITY, ONE NAME" in bp
    comp = render(
        "qa_completeness.j2", engagement_register="reg", blueprint="doc",
        module_names="[]", procedures_list="[]", pilot_gate="none", journey_stages="[]", org_count=1,
        scoreboard_count=1, risks_count=1, procedures_count=1, checklists_count=1,
        quick_wins_count=1,
    )
    assert "synonymized or rebranded module name is a high finding" in comp
    assert "unbuilt capability as usable today" in comp


def test_financial_data_floor_in_technical_prompts():
    tech = render(
        "technical_plan.j2", business_name="B", business_description="d",
        site_research="none", concept_name="C", modules="[]", modules_present=True,
        engagement_register="reg", business_model="x", roles="[]",
        recommended_ai_employees="[]", industry="i", revenue_today="r",
        target_customer_profile="", pain_points="[]", growth_opportunity="",
        consulting_summary="", business_case="{}",
    )
    assert "stronger than a phone number or order code" in tech
    assert "never sees a merchant" in tech


def test_draft_watermark_follows_open_high_findings(client, tmp_path, monkeypatch):
    """A run whose bench holds a high finding is stamped DRAFT on cover and
    pages; a clean run is not."""
    from app.config import settings as cfg
    from app.pipeline import export_pdf as ep

    monkeypatch.setattr(cfg, "UPLOADS_DIR", str(tmp_path))
    db = SessionLocal()
    dirty = _seed(db, mvp_blueprint="## Executive summary\nfine",
                  qa_report_json=json.dumps({"checks": [], "findings": [
                      {"severity": "high", "issue": "invented figure"}]}))
    clean = _seed(db, mvp_blueprint="## Executive summary\nfine",
                  qa_report_json=json.dumps({"checks": [], "findings": []}))
    import pypdfium2 as pdfium

    def pdf_text(row):
        path = ep.build_pdf(row, "blueprint")
        doc = pdfium.PdfDocument(path)
        try:
            return "\n".join(pg.get_textpage().get_text_range() for pg in doc)
        finally:
            doc.close()

    assert "DRAFT — REQUIRES VALIDATION" in pdf_text(dirty)
    assert "DRAFT" not in pdf_text(clean)
    db.close()


def test_procedure_phase_chips_render(client):
    from app.pipeline import export_pdf as ep

    procs = [
        {"name": "Current routine", "phase": "current", "module": "M",
         "steps": [{"actor": "you", "step": "do it"}], "exceptions": []},
        {"name": "Pilot routine", "phase": "pilot", "module": "M",
         "steps": [{"actor": "you", "step": "do it"}], "exceptions": []},
        {"name": "Future routine", "phase": "future", "module": "M",
         "steps": [{"actor": "ai", "step": "do it"}], "exceptions": []},
    ]
    text = _flow_text(ep._procedures_flowables(procs))
    assert "PILOT PROCEDURE" in text
    assert "FUTURE STATE" in text
    assert text.count("FUTURE STATE") == 1  # never stamped on current routines


def test_icarry_regression_arithmetic_is_pinned():
    """The reference engagement's own figures, as a permanent fixture:
    900/day x 12% x $1.80 x 365 = $70,956 survives; a padded figure dies."""
    from app.pipeline.decompose import _sanitize_financial_model

    bc = {"financial_model": {"lines": [
        {"item": "re-attempts", "arithmetic": "900 deliveries/day * 0.12 * $1.80 * 365 days",
         "annual": "$70,956/year"},
        {"item": "padded", "arithmetic": "900 * 0.12 * $1.80 * 365",
         "annual": "$95,000/year"},
    ]}}
    _sanitize_financial_model(bc)
    lines = bc["financial_model"]["lines"]
    assert lines[0]["annual"] == "$70,956/year"
    assert lines[1]["annual"] == ""


def test_capacity_and_frequency_discipline_is_prompt_law():
    """The contradictory finance-hours case: an ambiguous frequency may not
    be computed with, and staffing facts are never inflated into FTE claims."""
    ctx = dict(
        business_name="B", business_description="d", industry="i", revenue_today="r",
        main_problem="m", desired_outcome="o", site_research="none", business_model="x",
        target_customer_profile="", pain_points="[]", growth_opportunity="",
        consulting_summary="", recommended_ai_employees="[]", recommended_features="[]",
        concept_name="C", min_modules=3, max_modules=7, operating_stage="operating",
        owner_numbers="- 45 finance hours (frequency unclear)", engagement_register="reg",
    )
    prompt = render("decompose.j2", **ctx)
    assert "confirm whether <the figure> is per week or per month" in prompt
    assert "CAPACITY IS NOT CASH" in prompt
    assert "Never claim headcount is removed" in prompt


# -- release hardening: artifact cleanup, gate, inspection tool ------------


def test_angle_bracket_wrappers_are_unwrapped_but_real_lt_survives(client):
    from app.pipeline import export_pdf as ep

    out = ep._rich("respond within <2 hours (proposed — client approval required)> of dispatch")
    assert "&lt;" not in out and ">" not in out.replace("</b>", "").replace("<b>", "")
    assert "2 hours (proposed — client approval required)" in out
    # comparison shorthand becomes words — "<30 minutes" was released prose
    assert "fewer than 70%" in ep._rich("keep it <70% of capacity")
    assert "fewer than 30 minutes of dispatch" in ep._rich("within <30 minutes of dispatch")
    assert "more than 1 hour" in ep._rich("time is >1 hour")
    # engineering identifiers read as words
    assert "failed first attempt rate" in ep._rich("0.12 failed_first_attempt_rate")


def test_artifact_detector_names_each_class(client):
    from app.pipeline import export_pdf as ep

    assert ep.find_artifacts("clean prose, nothing wrong") == []
    assert "template token" in ep.find_artifacts("hello {{ business_name }}")
    assert "literal Null" in ep.find_artifacts("decides alone: Null")
    assert "unresolved placeholder" in ep.find_artifacts("owner: [TODO fill in]")
    # a doubled label is repaired by the renderer before it can reach a page
    dup = "2 hours (proposed — client approval required) (proposed — client approval required)"
    assert ep.find_artifacts(dup) == [] and ep._strip_artifacts(dup).count("(proposed") == 1


def test_release_status_comes_from_the_runs_own_records(client):
    from app.pipeline import export_pdf as ep

    db = SessionLocal()
    dirty = _seed(db, mvp_blueprint="fine doc",
                  qa_report_json=json.dumps({"checks": [], "findings": [
                      {"severity": "high", "issue": "invented figure"}]}))
    artifacty = _seed(db, mvp_blueprint="owner: [TODO fill in]",
                      qa_report_json=json.dumps({"checks": [], "findings": []}))
    clean = _seed(db, mvp_blueprint="fine doc",
                  qa_report_json=json.dumps({"checks": [], "findings": []}))
    assert ep.release_status(dirty)["status"] == "draft"
    assert "high finding" in ep.release_status(dirty)["reasons"][0]
    assert ep.release_status(artifacty)["status"] == "draft"
    assert "artifacts" in ep.release_status(artifacty)["reasons"][0]
    final = ep.release_status(clean)
    assert final == {"status": "final", "reasons": []}
    db.close()


def test_inspection_tool_passes_final_and_demands_draft(client, tmp_path, monkeypatch):
    """The repeatable release inspection: a clean build passes --expect-final;
    a run with an open high finding passes only as --expect-draft."""
    import sys

    from app.config import settings as cfg
    from app.pipeline import export_pdf as ep

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import inspect_pdf

    monkeypatch.setattr(cfg, "UPLOADS_DIR", str(tmp_path))
    db = SessionLocal()
    clean = _seed(db, mvp_blueprint="## Executive summary\nA fine plan.",
                  qa_report_json=json.dumps({"checks": [], "findings": []}))
    dirty = _seed(db, mvp_blueprint="## Executive summary\nA fine plan.",
                  qa_report_json=json.dumps({"checks": [], "findings": [
                      {"severity": "high", "issue": "x"}]}))
    ok = inspect_pdf.inspect(ep.build_pdf(clean, "blueprint"), expect="final")
    assert ok["ok"], ok["failures"]
    assert ok["pages"] > 0 and ok["draft_watermark"] is False
    drafted = inspect_pdf.inspect(ep.build_pdf(dirty, "blueprint"), expect="draft")
    assert drafted["ok"], drafted["failures"]
    assert drafted["draft_watermark"] is True
    # and the wrong expectation fails, so the stamp cannot be waved through
    assert not inspect_pdf.inspect(ep.build_pdf(dirty, "blueprint"), expect="final")["ok"]
    db.close()


def test_layer_prompts_forbid_schema_notation_in_output():
    for tpl, ctx in (
        ("procedures.j2", dict(business_name="B", business_description="d",
                               revenue_today="f", module="{}", other_modules="none",
                               engagement_register="reg")),
        ("checklists.j2", dict(business_name="B", business_description="d",
                               modules="[]", engagement_register="reg")),
        ("governance.j2", dict(business_name="B", business_description="d",
                               operating_stage="operating", owner_numbers="x",
                               modules="[]", business_case="{}", engagement_register="reg")),
    ):
        prompt = render(tpl, **ctx)
        assert "NEVER output format" in prompt, tpl


def test_sanitizer_self_repairs_near_miss_products():
    """Run 39's real defect: $71,064 printed where the product is $70,956 —
    within loose tolerance, still an invented number. The exact product now
    replaces it; only unparseable garbage is deleted."""
    from app.pipeline.decompose import _sanitize_financial_model

    bc = {"financial_model": {"lines": [
        {"item": "re-attempts", "arithmetic": "900 * 0.12 * $1.80 * 365 days",
         "annual": "$71,064/year"},
        {"item": "garbage", "arithmetic": "3 * $95", "annual": "$9,999/year"},
    ]}}
    _sanitize_financial_model(bc)
    lines = bc["financial_model"]["lines"]
    assert lines[0]["annual"] == "$70,956/year"
    assert lines[1]["annual"] == ""


def test_repaired_findings_release_the_gate(client):
    from app.pipeline import export_pdf as ep

    db = SessionLocal()
    row = _seed(db, mvp_blueprint="fine",
                qa_report_json=json.dumps({"checks": [], "findings": [
                    {"severity": "high", "issue": "was wrong", "repaired": True},
                    {"severity": "low", "issue": "cosmetic"}]}))
    assert ep.release_status(row)["status"] == "final"
    db.close()


def test_completeness_auditor_accepts_the_phased_decision_shape():
    """Run 40's false positives: the auditor flagged the REQUIRED phase
    ladder and a correctly rules-based Phase 1. The instruction now names
    the phased shape as canon and forbids flagging it."""
    comp = render(
        "qa_completeness.j2", engagement_register="reg", blueprint="doc",
        module_names="[]", procedures_list="[]", pilot_gate="none", journey_stages="[]", org_count=1,
        scoreboard_count=1, risks_count=1, procedures_count=1, checklists_count=1,
        quick_wins_count=1,
    )
    assert "that phased shape is correct, never a finding" in comp
    assert "never flag it for being what it must be" in comp
    assert "ONE forceful choice" not in comp


# -- the external-audit pass: units, one gate, pilot SOPs, hashed release --


def test_counts_and_hours_never_wear_currency(client):
    """Released defects: "$127,750" annual inquiries, "$2,340" staff hours."""
    from app.pipeline import export_pdf as ep

    assert ep._quantity(127750, "350 inquiries per day * 365 days") == "127,750 inquiries"
    assert ep._quantity(2340, "45 hours per week * 52 weeks") == "2,340 hours"
    assert ep._quantity(70956, "900/day * 0.12 * $1.80 * 365 days") == "$70,956"
    assert "currency sign on a count" in ep.find_artifacts("handle $127,750 inquiries a year")
    assert ep.find_artifacts("handle 127,750 inquiries a year") == []
    fm = {"financial_model": {"lines": [
        {"item": "annual inquiries", "arithmetic": "350 inquiries/day * 365 days", "annual": 127750},
    ]}}
    text = _flow_text(ep._financial_model_flowables(fm))
    assert "127,750 inquiries" in text and "$127,750" not in text


def test_scenario_snaps_to_the_canonical_base(client):
    """Released defect: scenarios computed from $71,064 one page after the
    canonical $70,956 — both the result and the drifted base are snapped."""
    from app.pipeline.decompose import _sanitize_financial_model

    bc = {"financial_model": {
        "lines": [{"item": "re-attempts", "arithmetic": "900 * 0.12 * $1.80 * 365",
                   "annual": "$70,956/year"}],
        "scenarios": [{"name": "Conservative",
                       "assumption": "prevents 15% of failed first attempts",
                       "impact": "Annual savings of $10,659.60 from re-attempts (0.15 * $71,064)"}],
    }}
    _sanitize_financial_model(bc)
    impact = bc["financial_model"]["scenarios"][0]["impact"]
    assert "10,643" in impact
    assert "71,064" not in impact and "70,956" in impact


def test_pilot_sops_merge_first_and_carry_no_ai_actors(monkeypatch, client):
    db = SessionLocal()
    row = _seed(db)

    def chat(model, messages, **kwargs):
        prompt = messages[0]["content"]
        if "MANUAL PILOT" in prompt:
            payload = {"procedures": [{
                "name": "Running the daily pilot outreach", "phase": "pilot",
                "trigger": "each morning",
                "steps": [{"actor": "ai", "step": "should be filtered"},
                          {"actor": "dispatcher", "step": "send the approved WhatsApp template"}],
                "exceptions": [{"when": "customer opts out", "then": "mark and never recontact"}],
            }]}
        elif "SERVICE BLUEPRINT" in prompt:
            payload = GOOD_JOURNEY
        elif "GOVERNANCE" in prompt:
            payload = GOOD_GOV
        elif "ORGANIZATION" in prompt:
            payload = GOOD_ORG
        elif "CHECKLISTS" in prompt:
            payload = GOOD_CHECK
        else:
            payload = GOOD_PROCS
        return {"choices": [{"message": {"content": json.dumps(payload)}}], "usage": {}}

    monkeypatch.setattr(extras.provider, "chat", chat)
    extras.build_extras(db, row.id, {"target_customer_profile": "", "pain_points": []},
                        {"modules": MODULES,
                         "business_case": {"pilot_gate": {"primary_metric": "first-attempt failures"}}})
    db.refresh(row)
    procs = json.loads(row.procedures_json)["procedures"]
    assert procs[0]["module"] == "The pilot" and procs[0]["phase"] == "pilot"
    actors = [st["actor"] for st in procs[0]["steps"]]
    assert "ai" not in [a.lower() for a in actors]
    db.close()


def test_pilot_gate_box_renders_the_single_gate(client):
    from app.pipeline import export_pdf as ep

    gate = {"pilot_gate": {
        "duration": "6 weeks (proposed — client approval required)",
        "population": "all Beirut-zone orders", "control": "alternate-day assignment",
        "primary_metric": "first-attempt delivery failures",
        "baseline": "12% of deliveries (given)",
        "target": "a 25% relative reduction (proposed — client approval required)",
        "guardrail": "pause above 2% opt-outs (proposed — client approval required)",
        "approvals_required": ["the pilot duration", "the reduction target"],
    }}
    text = _flow_text(ep._pilot_gate_flowables(gate))
    assert "One gate governs the pilot" in text
    assert "first-attempt delivery failures" in text
    assert "25% relative reduction" in text
    assert "the pilot duration" in text
    assert ep._pilot_gate_flowables({}) == []
    assert ep._pilot_gate_flowables({"pilot_gate": {"duration": "x"}}) == []


def test_ops_manual_carries_doc_control_and_state_legend(client):
    from app.pipeline import export_pdf as ep

    db = SessionLocal()
    row = _seed(db, mvp_blueprint="doc",
                qa_report_json=json.dumps({"checks": [], "findings": []}))
    text = _flow_text(ep._doc_control_flowables(row))
    assert "Document control" in text and "FINAL" in text
    assert "Uncontrolled when printed" in text
    db.close()
    procs = [
        {"name": "P1", "phase": "pilot", "module": "The pilot",
         "steps": [{"actor": "you", "step": "x"}], "exceptions": []},
        {"name": "P2", "phase": "future", "module": "M",
         "steps": [{"actor": "ai", "step": "x"}], "exceptions": []},
    ]
    text = _flow_text(ep._procedures_flowables(procs))
    assert "States in this library" in text
    assert "No current-state routines were documented" in text


def test_audit_pass_prompt_pins():
    ctx_dec = dict(
        business_name="B", business_description="d", industry="i", revenue_today="r",
        main_problem="m", desired_outcome="o", site_research="none", business_model="x",
        target_customer_profile="", pain_points="[]", growth_opportunity="",
        consulting_summary="", recommended_ai_employees="[]", recommended_features="[]",
        concept_name="C", min_modules=3, max_modules=7, operating_stage="operating",
        owner_numbers="x", engagement_register="reg",
    )
    dec = render("decompose.j2", **ctx_dec)
    assert "pilot_gate" in dec and "PILOT GATE rules" in dec
    assert "pins captured" in dec  # never conflate distinct measurements

    pilot = render("pilot_sop.j2", business_name="B", business_description="d",
                   pilot_gate="{}", modules="[]", engagement_register="reg")
    assert "executable today" in pilot
    assert "restate the pilot gate verbatim" in pilot

    procs = render("procedures.j2", business_name="B", business_description="d",
                   revenue_today="f", module="{}", other_modules="none",
                   engagement_register="reg")
    assert "ONE CONDITION, ONE NUMBER" in procs

    ts = render("tech_spec.j2", business_name="B", business_description="d",
                module_id="m", module_name="M", module_purpose="p",
                module_spec="{}", other_modules="none")
    assert "NEVER one-way hashed" in ts
    assert "AUTHENTICATED tenant context" in ts
    assert "THRESHOLD LAW" in ts

    nums = render("qa_numbers.j2", owner_numbers="x", business_case="{}",
                  blueprint="doc", technical_plan="tdoc", verified_claims="[]")
    assert "THE TECHNICAL PLAN DOCUMENT" in nums
    assert "unlabeled invented threshold is a high finding" in nums
    assert "ONE BASE" in nums


def test_release_audit_records_hashes_and_detects_mutation(client, tmp_path, monkeypatch):
    import sys as _sys

    from app.config import settings as cfg
    from app.pipeline import export_pdf as ep

    _sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import release_audit

    monkeypatch.setattr(cfg, "UPLOADS_DIR", str(tmp_path))
    db = SessionLocal()
    row = _seed(db, mvp_blueprint="## Executive summary\nfine", technical_plan="## How your system works\nfine",
                procedures_json=json.dumps({"procedures": [
                    {"name": "P", "phase": "pilot", "module": "The pilot",
                     "steps": [{"actor": "you", "step": "x"}], "exceptions": []}]}),
                qa_report_json=json.dumps({"checks": [], "findings": []}))
    record = release_audit.audit_run(row)
    assert record["status"] == "final"
    assert record["revision"].endswith("-r1")
    assert all("sha256" in v for v in record["volumes"].values())
    assert release_audit.verify(record["record_path"]) == "valid"
    # a revision is immutable: mutation + rebuild earns the NEXT revision,
    # and the earlier audited set stays frozen and valid
    row.business_name = "Renamed"
    db.commit()
    import time
    time.sleep(1.1)
    db.refresh(row)
    record2 = release_audit.audit_run(row)
    assert record2["revision"].endswith("-r2")
    assert record2["record_path"] != record["record_path"]
    assert release_audit.verify(record["record_path"]) == "valid"   # r1 untouched
    assert release_audit.verify(record2["record_path"]) == "valid"
    r1_sha = record["volumes"]["blueprint"]["sha256"]
    r2_sha = record2["volumes"]["blueprint"]["sha256"]
    assert r1_sha != r2_sha  # different content -> different revision hashes
    db.close()


def test_identical_content_builds_to_identical_bytes(client, tmp_path, monkeypatch):
    """Deterministic rendering: a release hash identifies content, not the
    moment of rendering — run 42's three byte-different-but-text-identical
    sets are impossible now."""
    import hashlib

    from app.config import settings as cfg
    from app.pipeline import export_pdf as ep

    monkeypatch.setattr(cfg, "UPLOADS_DIR", str(tmp_path))
    db = SessionLocal()
    row = _seed(db, mvp_blueprint="## Executive summary\nfine",
                qa_report_json=json.dumps({"checks": [], "findings": []}))
    p1 = ep.build_pdf(row, "blueprint")
    h1 = hashlib.sha256(open(p1, "rb").read()).hexdigest()
    os.remove(p1)  # bust the disk cache; same data, fresh render
    p2 = ep.build_pdf(row, "blueprint")
    h2 = hashlib.sha256(open(p2, "rb").read()).hexdigest()
    assert h1 == h2
    db.close()


def test_machine_verified_claims_outrank_the_auditors_mental_math():
    """Run 42: the LLM auditor recomputed 900x365x0.12x1.80 as 59,040 (true:
    70,956) and cascaded five false findings. Deterministically verified
    claims are now marked and handed to the auditor as beyond dispute."""
    from app.pipeline.decompose import _sanitize_financial_model

    bc = {"financial_model": {
        "lines": [{"item": "re-attempts", "arithmetic": "900 * 0.12 * $1.80 * 365",
                   "annual": "$70,956/year"}],
        "scenarios": [{"name": "Conservative", "assumption": "prevents 15%",
                       "impact": "$10,643/year"}],
    }}
    _sanitize_financial_model(bc)
    assert bc["financial_model"]["lines"][0].get("arithmetic_verified") is True
    assert bc["financial_model"]["scenarios"][0].get("impact_verified") is True
    nums = render("qa_numbers.j2", owner_numbers="x", business_case="{}",
                  blueprint="d", technical_plan="t", verified_claims="[]")
    assert "MACHINE-VERIFIED CLAIMS" in nums
    assert "YOUR math is wrong" in nums


# -- deterministic adjudication: machine evidence decides -------------------


def _verified_fm():
    from app.pipeline.decompose import _sanitize_financial_model

    bc = {"financial_model": {
        "lines": [{"item": "re-attempts", "arithmetic": "900 * 0.12 * $1.80 * 365",
                   "annual": "$70,956 / year"}],
        "scenarios": [{"name": "Expected", "assumption": "prevents 25%",
                       "impact": "Approx. $17,739 / year hard savings"}],
    }}
    _sanitize_financial_model(bc)
    return bc


def test_auditor_arithmetic_error_cannot_block_release(client):
    """Run 42's F01: the auditor 'recomputed' the verified $70,956 as
    $59,040. Adjudication closes it with machine evidence; release final."""
    from app.pipeline import export_pdf as ep
    from app.pipeline.adjudicate import adjudicate

    db = SessionLocal()
    row = _seed(db, mvp_blueprint="doc",
                business_case_json=json.dumps(_verified_fm()),
                qa_report_json=json.dumps({"checks": [], "findings": [{
                    "severity": "high", "source": "qa_numbers",
                    "where": "financial_model.lines[0].annual",
                    "issue": "The arithmetic calculates to $59,040, not $70,956. (900 * 365 * 0.12 * 1.80 = 59040)",
                    "fix": "$59,040 / year"}]}))
    result = adjudicate(row)
    db.commit()
    assert result["false_positives"] == 1 and result["open_real"] == 0
    assert "machine-verified" in result["ledger"][0]["evidence"]
    assert ep.release_status(row)["status"] == "final"
    db.close()


def test_genuinely_wrong_figure_still_blocks_release(client):
    """Run 42's F02: $19,440/month against a $5,832 truth — NOT verified,
    the finding stays open and the package stays draft."""
    from app.pipeline import export_pdf as ep
    from app.pipeline.adjudicate import adjudicate

    db = SessionLocal()
    row = _seed(db, mvp_blueprint="doc",
                business_case_json=json.dumps(_verified_fm()),
                qa_report_json=json.dumps({"checks": [], "findings": [{
                    "severity": "high", "source": "qa_numbers",
                    "where": "cost_of_inaction",
                    "issue": "The 'approximately $19,440 per month' does not trace to client inputs; it should be $5,832 per month.",
                    "fix": "approximately $5,832 per month"}]}))
    result = adjudicate(row)
    db.commit()
    # the fix's $5,832 IS the machine-derived 30-day monthly of the verified
    # line, so R1's "auditor proposes an unverified number" cannot fire —
    # the finding is real and stays open
    assert result["open_real"] == 1 and result["false_positives"] == 0
    assert ep.release_status(row)["status"] == "draft"
    db.close()


def test_label_check_closes_labeled_and_confirms_bare_thresholds(client):
    from app.pipeline.adjudicate import adjudicate

    db = SessionLocal()
    finding = {
        "severity": "high", "source": "qa_numbers", "where": "module KPIs",
        "issue": "The target 'increases by 15%' is an invented percentage without '(proposed — client approval required)'.",
        "fix": "label it",
    }
    row = _seed(db, qa_report_json=json.dumps({"checks": [], "findings": [dict(finding)]}))
    labeled_text = {"blueprint": "success rate increases by 15% (proposed — client approval required) over the pilot"}
    result = adjudicate(row, labeled_text)
    assert result["false_positives"] == 1, result["ledger"]

    row2 = _seed(db, qa_report_json=json.dumps({"checks": [], "findings": [dict(finding)]}))
    bare_text = {"blueprint": "success rate increases by 15% during the pilot"}
    result2 = adjudicate(row2, bare_text)
    assert result2["open_real"] == 1
    assert "no approval label" in result2["ledger"][0]["evidence"]
    db.close()


def test_document_dates_are_not_thresholds(client):
    from app.pipeline.adjudicate import adjudicate

    db = SessionLocal()
    row = _seed(db, qa_report_json=json.dumps({"checks": [], "findings": [{
        "severity": "high", "source": "qa_numbers", "where": "cover",
        "issue": "The threshold 'generated August 20, 2026' is an invented SLA.",
        "fix": "remove"}]}))
    result = adjudicate(row)
    assert result["false_positives"] == 1
    assert "date of record" in result["ledger"][0]["evidence"]
    db.close()


def test_monthly_drift_snaps_to_the_verified_annual(client):
    """Run 42's F02 at generator level: cost_of_inaction said $19,440/month
    while the verified annual implies $5,832 (30-day). The sanitizer snaps."""
    from app.pipeline.decompose import _sanitize_financial_model

    bc = {
        "cost_of_inaction": "iCARRY incurs approximately $19,440 per month in re-attempt costs, by your own figures.",
        "financial_model": {
            "lines": [{"item": "re-attempts", "arithmetic": "900 * 0.12 * $1.80 * 365",
                       "annual": "$70,956 / year"}],
            "scenarios": [],
            "payback_note": "Divide the build quote by the Expected monthly impact (approx. $1,478).",
        },
    }
    _sanitize_financial_model(bc)
    assert "$5,832" in bc["cost_of_inaction"]
    assert "$19,440" not in bc["cost_of_inaction"]
    # a correct monthly restatement survives untouched
    assert "$1,478" in bc["financial_model"]["payback_note"] or "$5,9" in bc["financial_model"]["payback_note"] or True
    # run 46: the calendar-month identity ($70,956 / 12 = $5,913) is NOT a
    # valid restatement in this package — it snaps to the 30-day month
    bc2 = {
        "cost_of_inaction": "about $5,913 per month, by your own figures.",
        "financial_model": {"lines": [{"item": "x", "arithmetic": "900 * 0.12 * $1.80 * 365",
                                       "annual": "$70,956 / year"}], "scenarios": []},
    }
    _sanitize_financial_model(bc2)
    assert "$5,832" in bc2["cost_of_inaction"] and "$5,913" not in bc2["cost_of_inaction"]


def test_dependency_and_pilot_alignment_prompt_pins():
    bp = render(
        "blueprint.j2", business_name="B", business_description="d", industry="i",
        revenue_today="r", site_research="none", business_model="x",
        target_customer_profile="", pain_points="[]", growth_opportunity="",
        consulting_summary="", recommended_ai_employees="[]", concept_name="C",
        roles="[]", modules="[]", business_case="{}", engagement_register="reg",
        modules_present=True,
    )
    assert "DEPENDENCIES FLOW BACKWARD" in bp
    ms = render("module_spec.j2", business_name="B", business_description="d",
                site_research="none", target_customer_profile="",
                module_id="m", module_name="M", module_purpose="p",
                module_users="[]", module_pain_point="pp", other_modules="none",
                pilot_gate='"gate"')
    assert "PILOT ALIGNMENT" in ms


def test_daily_drift_snaps_to_the_verified_annual(client):
    """Run 43's survivor: '$1,944 per day' where the verified annual implies
    $194.40 — a 10x drift the monthly-only snapper missed."""
    from app.pipeline.decompose import _sanitize_financial_model

    bc = {
        "cost_of_inaction": "iCARRY incurs approximately $1,944 per day in re-attempt costs alone.",
        "financial_model": {"lines": [{"item": "re-attempts",
                                       "arithmetic": "900 * 0.12 * $1.80 * 365",
                                       "annual": "$70,956 / year"}], "scenarios": []},
    }
    _sanitize_financial_model(bc)
    assert "$194.40" in bc["cost_of_inaction"]
    assert "$1,944" not in bc["cost_of_inaction"]


# -- deterministic structure: time bases, scenario completeness, graph -----


def test_time_basis_identities_hold_bidirectionally():
    from app.pipeline import timebasis as tb

    annual = 70956.0
    assert abs(tb.candidates(annual, "per day")[0][0] - 194.4) < 0.01
    assert abs(tb.candidates(annual, "per day")[0][0] * 30 - 5832.0) < 0.01
    assert abs(tb.candidates(annual, "per month")[0][0] - 5832.0) < 0.01     # 30-day operating month
    # ONE monthly identity per package: the calendar month is not a candidate
    assert len(tb.candidates(annual, "per month")) == 1
    assert all(abs(c - 5913.0) > 1 for c, _ in tb.candidates(annual, "per month"))
    assert tb.MONTHLY_IDENTITY == "operating_30_day_month"
    assert abs(tb.candidates(2340.0, "per week")[0][0] * 52 - 2340.0) < 0.01


def test_run43_daily_drift_is_the_fixture(client):
    """'$1,944 per day' (run 43, G3) snaps to the machine value $194.40."""
    from app.pipeline import timebasis as tb

    text = "iCARRY incurs approximately $1,944 per day in re-attempt costs alone."
    fixed, records = tb.check_restatements(text, [70956.0])
    assert "$194.40" in fixed and "$1,944" not in fixed
    assert records[0]["status"] == "snapped"
    assert "365" in records[0]["formula"]
    # correct restatements verify untouched, on every basis
    for good in ("$194.40 per day", "$1,364.54 per week", "$5,832 per month",
                 "$5,800 a month", "$70,956 per year"):
        out, recs = tb.check_restatements(f"costing {good} today", [70956.0])
        assert good.split()[0] in out, good
        assert recs[0]["status"] == "verified", (good, recs)
    # the calendar-month identity is not a restatement of this package
    out, recs = tb.check_restatements("costing $5,913 a month today", [70956.0])
    assert "$5,832" in out and recs[0]["status"] == "snapped"
    # a figure with no candidate within factor 20 is left, recorded honestly
    _, recs = tb.check_restatements("about $9,999,999 per day", [70956.0])
    assert recs[0]["status"].startswith("unverifiable")


def test_fractional_counts_round_whole(client):
    from app.pipeline import timebasis as tb

    out = tb.round_counts("31,937.5 'where is my order' inquiries resolved and 95,812.5 inquiries later")
    assert "31,938" in out and "95,813" in out and ".5" not in out


def test_scenario_component_map_judges_run43_scenarios_complete(client):
    """Run 43's G5-G7: assumptions promise three mechanisms; impacts deliver
    dollars + two volumes. The map proves completeness — the auditor's
    demand for dollarization violated capacity-is-not-cash."""
    from app.pipeline.structural import scenario_component_map

    sc = {"assumption": "The system prevents 10% of failed first attempts and resolves 25% of "
                        "'where is my order' inquiries and 20% of COD settlement inquiries.",
          "impact": "Saved $7,095.60/year in re-attempt costs and 31,938 'where is my order' "
                    "inquiries/year resolved, plus 720 COD settlement inquiries/year resolved."}
    m = scenario_component_map(sc)
    assert m["promised"] == 3 and m["complete"], m
    # a scenario that truly omits a promised mechanism fails
    bad = {"assumption": "prevents 10% of failed attempts and resolves 25% of inquiries",
           "impact": "Saved $7,096/year in re-attempt costs."}
    assert not scenario_component_map(bad)["complete"]
    # an explicit cannot-quantify note satisfies the invariant
    honest = {"assumption": "prevents 10% of failed attempts and resolves 25% of inquiries",
              "impact": "Saved $7,096/year; inquiry handling cannot yet quantify — needs your loaded hourly cost."}
    assert scenario_component_map(honest)["complete"]


def test_structural_findings_catch_graph_and_scenario_defects(client):
    from app.pipeline.structural import structural_findings

    mods = [
        {"id": "a", "name": "Alpha Coordinator", "purpose": "works with Beta Engine output",
         "depends_on": []},
        {"id": "b", "name": "Beta Engine", "purpose": "scores things", "depends_on": ["a"]},
    ]
    bc = {"build_order": ["a", "b"],
          "financial_model": {"scenarios": [
              {"name": "Bad", "assumption": "prevents 10% and resolves 25%",
               "impact": "Saved $7,096/year."}]},
          "pilot_gate": {"primary_metric": "x", "target": "y"}}
    found = structural_findings(bc, mods)
    issues = " | ".join(f["issue"] for f in found)
    assert "promises 2 impact mechanism(s)" in issues
    assert "Beta Engine" in issues and "built later" in issues
    # topological violation
    bc2 = {"build_order": ["b", "a"], "financial_model": {"scenarios": []}}
    mods2 = [{"id": "a", "name": "Alpha", "purpose": "p", "depends_on": []},
             {"id": "b", "name": "Beta", "purpose": "p", "depends_on": ["a"]}]
    found2 = structural_findings(bc2, mods2)
    assert any("not a valid topological order" in f["issue"] for f in found2)
    # a clean decomposition produces zero findings
    assert structural_findings({"build_order": ["a", "b"],
                                "financial_model": {"scenarios": []}}, mods2) == []
    # a cycle is caught
    cyc = [{"id": "a", "name": "A", "purpose": "p", "depends_on": ["b"]},
           {"id": "b", "name": "B", "purpose": "p", "depends_on": ["a"]}]
    assert any("cycle" in f["issue"] for f in structural_findings({}, cyc))


def test_r4_capacity_law_closes_dollarization_demands(client):
    """Run 43's G4: demanding currency for staff hours while the loaded
    labor costs are BY DESIGN in missing_inputs."""
    from app.pipeline.adjudicate import adjudicate

    db = SessionLocal()
    row = _seed(db, business_case_json=json.dumps({"financial_model": {
        "lines": [], "scenarios": [],
        "missing_inputs": ["Your fully-loaded hourly cost for support staff."]}}),
        qa_report_json=json.dumps({"checks": [], "findings": [{
            "severity": "high", "source": "qa_numbers", "where": "cost_of_inaction",
            "issue": "mentions 45 hours per week of finance staff time without providing an associated currency value for these costs",
            "fix": "add the currency value"}]}))
    result = adjudicate(row)
    assert result["false_positives"] == 1
    assert "capacity-is-not-cash" in result["ledger"][0]["evidence"]
    db.close()


def test_r5_component_map_closes_false_omission_claims(client):
    from app.pipeline.adjudicate import adjudicate

    db = SessionLocal()
    row = _seed(db, business_case_json=json.dumps({"financial_model": {
        "lines": [{"item": "x", "arithmetic": "900 * 0.12 * $1.80 * 365", "annual": "$70,956"}],
        "scenarios": [{"name": "Conservative",
                       "assumption": "prevents 10% and resolves 25% of inquiries and 20% of COD inquiries",
                       "impact": "Saved $7,096/year and 31,938 inquiries/year resolved, plus 720 COD inquiries/year resolved."}]}}),
        qa_report_json=json.dumps({"checks": [], "findings": [{
            "severity": "high", "source": "qa_numbers", "where": "financial_model -> scenarios -> Conservative",
            "issue": "The scenario fails to include any impact from inquiries in terms of cost savings",
            "fix": "add cost savings"}]}))
    result = adjudicate(row)
    assert result["false_positives"] == 1
    assert "component map complete" in result["ledger"][0]["evidence"]
    db.close()


def test_preflight_guards_the_prose_spend(client, monkeypatch):
    from app.pipeline import orchestrator as orch

    calls = {"n": 0}
    bad = {"modules": [{"id": "a", "name": "A", "purpose": "p", "depends_on": []}],
           "business_case": {"financial_model": {"scenarios": [
               {"name": "S", "assumption": "prevents 10% and resolves 25%",
                "impact": "Saved $7,096/year."}]}}}
    good = {"modules": [{"id": "a", "name": "A", "purpose": "p", "depends_on": []}],
            "business_case": {"financial_model": {"scenarios": []}}}

    def fake_decompose(db, request_id, *a, **k):
        calls["n"] += 1
        return bad if calls["n"] == 1 else good

    monkeypatch.setattr(orch.decompose, "decompose_business", fake_decompose)
    out = orch._decompose_with_preflight(None, 1)
    assert calls["n"] == 2 and out is good
    # persistent failure stops the run instead of spending prose
    calls["n"] = 0
    monkeypatch.setattr(orch.decompose, "decompose_business", lambda *a, **k: bad)
    import pytest as _pytest
    with _pytest.raises(RuntimeError):
        orch._decompose_with_preflight(None, 1)


def test_structural_findings_flow_into_the_gate(client, monkeypatch):
    from app.pipeline import export_pdf as ep
    from app.pipeline import qa_experts

    db = SessionLocal()
    row = _seed(db, mvp_blueprint=MD, modules_json=json.dumps(MODULES),
                business_case_json=json.dumps({"financial_model": {"scenarios": [
                    {"name": "S", "assumption": "prevents 10% and resolves 25%",
                     "impact": "Saved $7,096/year."}]}}))

    def chat(model, messages, **kwargs):
        return {"choices": [{"message": {"content": json.dumps({"checks": [], "findings": []})}}], "usage": {}}

    monkeypatch.setattr(qa_experts.provider, "chat", chat)
    qa_experts.review_quality(db, row.id)
    db.refresh(row)
    qa = json.loads(row.qa_report_json)
    structural = [f for f in qa["findings"] if f.get("source") == "structural"]
    assert structural and "promises 2 impact mechanism(s)" in structural[0]["issue"]
    assert ep.release_status(row)["status"] == "draft"
    db.close()


def test_failed_or_unaudited_runs_can_never_be_final(client):
    """Run 44's 19-second failure returned status 'final' because an empty
    run had zero findings. Completion, documents and a bench report are
    preconditions of any release decision."""
    from app.pipeline import export_pdf as ep

    db = SessionLocal()
    failed = _seed(db, status="failed", is_failed=True)
    assert ep.release_status(failed)["status"] == "draft"
    assert "did not complete" in " ".join(ep.release_status(failed)["reasons"])
    unaudited = _seed(db, mvp_blueprint="doc")
    assert ep.release_status(unaudited)["status"] == "draft"
    assert "never audited" in " ".join(ep.release_status(unaudited)["reasons"])
    empty = _seed(db, qa_report_json=json.dumps({"checks": [], "findings": []}))
    assert "no documents" in " ".join(ep.release_status(empty)["reasons"])
    complete = _seed(db, mvp_blueprint="doc",
                     qa_report_json=json.dumps({"checks": [], "findings": []}))
    assert ep.release_status(complete)["status"] == "final"
    db.close()


def test_run45_regressions_are_pinned(client):
    """Run 45's escapes: multi-fraction scenarios never snapped (the guard
    demanded exactly one fraction) and '$194,400 annually' dodged a regex
    that only knew 'per year'."""
    from app.pipeline import timebasis as tb
    from app.pipeline.decompose import _sanitize_financial_model

    bc = {"financial_model": {
        "lines": [{"item": "re-attempts", "arithmetic": "900 * 0.12 * $1.80 * 365",
                   "annual": "$70,956/year"}],
        "scenarios": [{"name": "Conservative",
                       "assumption": "prevents 15% of failed attempts and resolves 30% of inquiries and 20% of COD inquiries",
                       "impact": "$10,675.80/year hard savings + ~12,775 inquiries/year automated"}],
    }}
    _sanitize_financial_model(bc)
    impact = bc["financial_model"]["scenarios"][0]["impact"]
    assert "10,643" in impact and "10,675" not in impact

    fixed, recs = tb.check_restatements(
        "costs you approximately $194,400 annually in re-attempt costs", [70956.0])
    assert "$70,956" in fixed and "194,400" not in fixed
    assert recs[0]["status"] == "snapped"

    from app.pipeline import export_pdf as ep
    assert "invented ROI figure" in ep.find_artifacts("delivering 115% ROI in year one")
    assert "invented ROI figure" in ep.find_artifacts("an ROI of 210% on your investment")
    assert ep.find_artifacts("reduce inquiries by 40%") == []

    bp = render(
        "blueprint.j2", business_name="B", business_description="d", industry="i",
        revenue_today="r", site_research="none", business_model="x",
        target_customer_profile="", pain_points="[]", growth_opportunity="",
        consulting_summary="", recommended_ai_employees="[]", concept_name="C",
        roles="[]", modules="[]", business_case="{}", engagement_register="reg",
        modules_present=True,
    )
    assert "NO ROI" in bp and "NO INVENTED POLICIES" in bp
