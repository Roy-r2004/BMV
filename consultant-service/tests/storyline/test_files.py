"""One list names the package. The shelf, the zip, the share link and the
progress screen all read it, so a file cannot be offered in one place and
missing in another.
"""
from __future__ import annotations

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.models import Request
from app.storyline.files import files_for

PHASE = {"when": "The first fortnight", "title": "Set the week", "do": "Write the rota", "by": "us", "you": "You approve it"}
PLAN = json.dumps({"status": "ready", "phases": [PHASE], "decisions": []})
ROLES = json.dumps([{"role_id": "desk", "role_label": "Front desk"}])
PROCS = json.dumps({"procedures": [{"name": "Handling an inquiry", "trigger": "a call",
                                    "steps": [{"actor": "ai", "step": "log it"}],
                                    "exceptions": [{"when": "urgent", "then": "call the owner"}]}]})
BLUEPRINT = "## The plan\nA studio keeps its classes full.\n"


@pytest.fixture
def client():
    from main import app

    Base.metadata.create_all(bind=engine)
    return TestClient(app)


def _seed(db, **overrides):
    stamp = overrides.pop("integrity_stamp", True)
    row = Request(
        business_name="Halo Studio", business_description="A studio.",
        email="a@b.c", status="done", is_generating=False, concept_name="Halo",
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    if stamp:
        from tests._integrity_stub import stamp_clean

        stamp_clean(row)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_the_list_names_six_files_and_a_zip_in_order():
    files = files_for(Request(business_name="Halo", business_description="A studio.", email="a@b.c"))
    assert [f.key for f in files] == [
        "blueprint", "technical", "operations", "roadmap", "system", "deck", "zip",
    ]
    assert [f.kind for f in files] == ["pdf", "pdf", "pdf", "pdf", "pdf", "pptx", "zip"]


def test_a_do_not_build_run_marks_the_system_file_absent_with_its_reason_and_zip_still_builds(client, tmp_path, monkeypatch):
    from app.config import settings as cfg

    monkeypatch.setattr(cfg, "UPLOADS_DIR", str(tmp_path))
    db = SessionLocal()
    row = _seed(
        db, mvp_blueprint=BLUEPRINT,
        consulting_recommendations_json=json.dumps({"intervention_kind": "process"}),
        screens_json=json.dumps({"screens": [{"name": "The week"}]}),
    )
    system = next(f for f in files_for(row) if f.key == "system")
    assert system.available is False
    assert system.reason == "Your diagnosis says not to build, so there are no screens."
    response = client.get(f"/api/requests/{row.id}/export/zip")
    assert response.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert names
    assert not any("System" in name or "Volume IV" in name for name in names)
    db.close()


def test_the_zip_contains_every_available_file_including_the_deck_and_the_roadmap(client, tmp_path, monkeypatch):
    from app.config import settings as cfg

    monkeypatch.setattr(cfg, "UPLOADS_DIR", str(tmp_path))
    db = SessionLocal()
    row = _seed(
        db, mvp_blueprint=BLUEPRINT, technical_plan=BLUEPRINT, procedures_json=PROCS,
        action_plan_json=PLAN, roles_json=ROLES,
    )
    offered = {f.key for f in files_for(row) if f.available and f.key != "zip"}
    assert {"blueprint", "technical", "operations", "roadmap", "deck"} <= offered
    response = client.get(f"/api/requests/{row.id}/export/zip")
    assert response.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert any(name.endswith("The implementation roadmap.pdf") for name in names)
    assert any(name.endswith(".pptx") for name in names)
    assert any("Volume I" in name for name in names)
    assert any("Volume III" in name for name in names)
    db.close()


def test_the_share_link_serves_the_deck_and_the_roadmap(client, tmp_path, monkeypatch):
    from app.config import settings as cfg

    monkeypatch.setattr(cfg, "UPLOADS_DIR", str(tmp_path))
    db = SessionLocal()
    row = _seed(db, action_plan_json=PLAN, roles_json=ROLES, share_token="partner-link-1")
    deck = client.get("/api/shared/partner-link-1/export/deck")
    roadmap = client.get("/api/shared/partner-link-1/export/roadmap")
    assert deck.status_code == 200
    assert "presentation" in deck.headers["content-type"]
    assert roadmap.status_code == 200 and roadmap.content.startswith(b"%PDF")
    db.close()


def test_an_unknown_key_is_a_404_with_plain_words(client):
    db = SessionLocal()
    row = _seed(db, share_token="partner-link-2")
    for path in (f"/api/requests/{row.id}/export/pilot", "/api/shared/partner-link-2/export/pilot"):
        response = client.get(path)
        assert response.status_code == 404
        detail = response.json()["detail"]
        assert isinstance(detail, str) and detail
        assert "Traceback" not in detail and "Exception" not in detail
    db.close()


def test_old_export_paths_still_answer(client, tmp_path, monkeypatch):
    from app.config import settings as cfg

    monkeypatch.setattr(cfg, "UPLOADS_DIR", str(tmp_path))
    db = SessionLocal()
    row = _seed(db, mvp_blueprint=BLUEPRINT, roles_json=ROLES)
    pdf = client.get(f"/api/requests/{row.id}/export/pdf/blueprint")
    deck = client.get(f"/api/requests/{row.id}/export/pptx")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert deck.status_code == 200 and "presentation" in deck.headers["content-type"]
    db.close()


def test_progress_files_match_preview_files(client):
    db = SessionLocal()
    row = _seed(db, mvp_blueprint=BLUEPRINT, stage="technical")
    progress = client.get(f"/api/requests/{row.id}/progress").json()["files"]
    preview = client.get(f"/api/requests/{row.id}/preview").json()["files"]
    assert progress == preview
    assert [item["key"] for item in progress] == [
        "blueprint", "technical", "operations", "roadmap", "system", "deck", "zip",
    ]
    assert progress[0]["state"] == "ready"
    db.close()


SECRET = "My partner Dana keeps losing the bookings and I am thinking of firing her."
OWNER_GUESS = "Dana is the reason the evening class empties."


def test_the_share_link_carries_none_of_the_owners_own_words(client, tmp_path, monkeypatch):
    # Review H1: GET /api/shared/<token> served main_problem verbatim as
    # answer_page.believed, and the brief's question and the owner's hypotheses.
    from app.config import settings as cfg

    monkeypatch.setattr(cfg, "UPLOADS_DIR", str(tmp_path))
    db = SessionLocal()
    rows = [{"phase": 1, "recommendation": "Keep the evening class.", "changes": "The evening.",
             "owner": "the owner", "depends_on": [], "share_pct": 100, "cost_figure": None,
             "cost_needs": "a quote from the builder"}]
    row = _seed(
        db, share_token="partner-link-3", action_plan_json=PLAN, main_problem=SECRET,
        brief_json=json.dumps({"question": "Should I fire Dana over the evening class?"}),
        answer_json=json.dumps({"headline": "You are full.", "turn": "Keep the class."}),
        storyline_json=json.dumps({"register": rows, "sections": []}),
        diagnosis_json=json.dumps({"hypotheses": [
            {"statement": OWNER_GUESS, "from_owner": True,
             "test": {"verdict": "refuted", "because": "Dana covers the morning only."}}]}),
        consulting_recommendations_json=json.dumps({"why_not_the_others": "A new hire costs more than it saves."}),
    )
    shared = client.get("/api/shared/partner-link-3")
    assert shared.status_code == 200
    body = shared.text
    for words in (SECRET, "Should I fire Dana", OWNER_GUESS, "Dana covers the morning only."):
        assert words not in body, words
    page = shared.json()["answer_page"]
    assert page["question"] is None and page["believed"] is None and page["tested"] is None
    assert page["would_not"] == ["A new hire costs more than it saves."]
    assert page["answer_lines"] == ["You are full.", "Keep the class."]
    db.close()
