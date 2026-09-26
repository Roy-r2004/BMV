"""Pins for the consultation flow's parts: the week, the answer, the roadmap,
the owner's decisions, the brief, the case file, the partner link and the
build that supersedes itself when the client pushes back.

The rule under all of them is the product's promise — a figure on screen is
one the owner gave, arithmetic on theirs with the working kept, or a number we
propose and label as ours. Each checker is pure, so each is pinned here with
the honest reading AND the dishonest one it exists to catch.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.models import Request
from app.pipeline import action_plan, answer, capacity, figures
from app.routers import discovery

HALO = [
    "I run a pilates studio and I think I need a proper booking app. The 6pm and 7pm classes have a "
    "waiting list every week, and I spend about 8 hours a week juggling bookings on WhatsApp",
    "How many reformers, and how many classes a week?: 12 reformers. Six 50-minute classes a day, six days a week.",
    "How full is a typical class?: About 10 of 12. The 6pm and 7pm ones have a waiting list most weeks.",
    "What do you charge?: $22 a class, $200 for 10",
    "What do the other studios nearby charge?: Two others nearby, both $32 a class.",
]

GRID = {
    "shape": "weekly_grid", "unit": "reformer spot", "unit_plural": "reformer spots",
    "per_slot": 12, "slots_per_day": 6, "days_per_week": 6,
    "slot_times": [None, None, None, None, "18:00", "19:00"],
    "typical_taken": 10, "full_slots": ["18:00", "19:00"], "waitlist": True,
}


# ── figures ──────────────────────────────────────────────────────────────


def test_given_reads_number_words_and_keeps_clock_times_apart():
    texts = ["Six classes a day, the 7pm one is full", "$22 a class"]
    got = figures.given(texts)
    assert {6.0, 22.0} <= got
    # "the 7pm class" is not the number 7 — it once let "7 days a week" through
    assert 7.0 not in got and 19.0 not in got
    assert figures.given_hours(texts) == {19}


def test_unsupported_catches_invented_money_and_leaves_small_prose_alone():
    allowed = figures.given(HALO)
    assert figures.unsupported("at $22 you are the cheapest", allowed) == []
    assert figures.unsupported("studios nearby charge $35", allowed) == [35.0]
    # "1 in 20" style prose is not policed below 2
    assert figures.unsupported("one of 1 explanations", allowed) == []


# ── capacity ─────────────────────────────────────────────────────────────


def test_week_is_drawn_from_their_words_and_the_arithmetic_is_ours():
    pic = capacity.shape(GRID, HALO)
    assert pic["capacity"] == 432
    # 10 in the four ordinary slots, 12 in the two that sell out, six days
    assert pic["taken"] == 10 * 4 * 6 + 12 * 2 * 6
    assert {d["key"]: d["value"] for d in pic["derived"]}["CAP-05"] == 144
    assert pic["times"] == [None, None, None, None, "18:00", "19:00"]


def test_invented_timetable_and_day_names_are_dropped():
    raw = dict(GRID, slot_times=["7:00", "9:30", None, None, "18:00", "19:00"],
               day_names=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"])
    pic = capacity.shape(raw, HALO)
    # she never named 7am, 9:30 or the days: none of them may appear
    assert pic["times"][:2] == [None, None]
    assert pic["grid"][0]["day"] == "Day 1"


def test_a_capacity_number_she_never_gave_kills_the_picture():
    assert capacity.shape(dict(GRID, per_slot=14), HALO) is None
    assert capacity.shape(dict(GRID, days_per_week=7), HALO) is None


def test_a_waiting_list_without_a_size_is_drawn_as_unknown_not_invented():
    pic = capacity.shape(GRID, HALO)
    evening = pic["grid"][0]["slots"][4]
    assert evening["full"] and evening["waitlist"] == "unknown"


# ── the answer ───────────────────────────────────────────────────────────


CLAIMS = [{"id": "CF-04", "value": 22, "unit": "USD", "text": "$22 a class"},
          {"id": "CF-06", "value": 32, "unit": "USD", "text": "$32"}] + capacity.as_claims(capacity.shape(GRID, HALO))

MOVE = {"label": "moving 6pm and 7pm to $28, if regulars stay", "unit": "USD", "period": "year",
        "terms": [{"label": "evening spots a week", "value": 144, "from": "CAP-05"},
                  {"label": "price rise per spot", "value": 6,
                   "parts": [{"value": 28, "from": "proposed", "label": "proposed evening price"},
                             {"value": 22, "from": "CF-04", "sign": -1}]},
                  {"label": "weeks a year", "value": 52, "from": "constant"}]}


def test_the_move_is_multiplied_here_and_the_proposal_is_labelled():
    move = answer.compute_move(MOVE, CLAIMS)
    assert move["value"] == 144 * 6 * 52
    assert move["rounded"] == 45000
    assert move["display"] == "≈ $45,000 a year"
    assert move["proposed"] == [{"value": 28.0, "label": "proposed evening price"}]
    assert "$28 proposed" in move["working"]


def test_a_term_that_misquotes_its_figure_kills_the_move():
    bad = json.loads(json.dumps(MOVE))
    bad["terms"][0]["value"] = 200
    assert answer.compute_move(bad, CLAIMS) is None


def test_a_move_resting_only_on_proposals_is_refused():
    guess = {"unit": "USD", "terms": [{"label": "new members", "value": 40, "from": "proposed"},
                                      {"label": "months", "value": 12, "from": "constant"}]}
    assert answer.compute_move(guess, CLAIMS) is None


def test_the_answer_drops_a_figure_she_never_gave():
    raw = {"headline": "You're not short of clients.", "turn": "You're full.",
           "sub": "Every evening sells out, and at $22 you're the cheapest nearby.",
           "figures": [{"value": "$22 vs $32", "label": "you and two studios nearby", "cites": ["CF-04", "CF-06"]},
                       {"value": "$25 vs $40", "label": "made up", "cites": ["CF-04"]}],
           "move": MOVE, "action": {"weeks": 6, "name": "six-week pilot"}}
    got, problems = answer.shape(raw, CLAIMS, HALO)
    assert [f["value"] for f in got["figures"]] == ["$22 vs $32"]
    assert problems


def test_a_headline_with_an_invented_number_is_not_shown():
    got, problems = answer.shape({"headline": "You lose $9,000 a month.", "sub": ""}, CLAIMS, HALO)
    assert got is None and problems


# ── the roadmap and the owner's decisions ────────────────────────────────


def _roadmap_raw(**over):
    raw = {
        "summary": "We move the evenings to $28 and watch the waiting list.",
        "phases": [
            {"when": "Weeks 1 to 2", "title": "Set the evening price",
             "do": "We move the 6pm and 7pm classes to $28 and tell your regulars.", "by": "us"},
            {"when": "Weeks 3 to 6", "title": "Watch the evenings",
             "do": "We track evening fill against 10 of 12 each week.", "by": "someone else", "you": ""},
        ],
        "decisions": [
            {"question": "Go ahead with $28 evenings?", "detail": "Daytime stays at $22.",
             "options": ["Yes", "Not yet"]},
        ],
        "assumptions": ["Regulars accept $28"],
    }
    raw.update(over)
    return raw


def _allowed():
    return answer.allowed_numbers(HALO, CLAIMS, answer.compute_move(MOVE, CLAIMS))


def test_the_roadmap_is_phases_we_carry_out_and_decisions_they_make():
    plan, problems = action_plan.shape(_roadmap_raw(), _allowed())
    assert plan["status"] == action_plan.READY and not problems
    # "by" is only ever us or together — never a job handed to the owner
    assert [p["by"] for p in plan["phases"]] == ["us", "us"]
    assert plan["decisions"][0]["id"] == "d1"
    together = _roadmap_raw()
    together["phases"][1]["by"] = "Together"
    assert action_plan.shape(together, _allowed())[0]["phases"][1]["by"] == "together"


def test_a_phase_with_an_invented_price_is_dropped_and_too_few_phases_kill_it():
    raw = _roadmap_raw()
    raw["phases"][1]["do"] = "We match the $35 studio down the road."
    plan, problems = action_plan.shape(raw, _allowed())
    # one usable phase left: not a roadmap
    assert plan is None
    assert any("35" in p for p in problems)


def test_a_roadmap_needs_a_decision_with_real_options():
    assert action_plan.shape(_roadmap_raw(decisions=[]), _allowed())[0] is None
    one_option = [{"question": "Go ahead?", "options": ["Yes"]}]
    assert action_plan.shape(_roadmap_raw(decisions=one_option), _allowed())[0] is None
    invented = [{"question": "Charge $40 at weekends?", "options": ["Yes", "No"]},
                {"question": "Go ahead?", "options": ["Yes", "Not yet"]}]
    plan, problems = action_plan.shape(_roadmap_raw(decisions=invented), _allowed())
    assert [d["question"] for d in plan["decisions"]] == ["Go ahead?"] and problems


def test_choices_only_answer_the_roadmaps_own_decisions_with_its_own_options():
    plan = {"decisions": [{"id": "d1", "options": ["Yes", "Not yet"]},
                          {"id": "d2", "options": ["This month", "Next month"]}]}
    got = action_plan.record_choices(plan, {}, {"d1": "Yes", "d9": "Yes", "d2": "Tomorrow"})
    assert got == {"choices": {"d1": "Yes"}}
    got = action_plan.record_choices(plan, {**got, "go_ahead": True}, {"d2": "Next month", "d1": "Maybe"})
    assert got == {"choices": {"d1": "Yes", "d2": "Next month"}, "go_ahead": True}


# ── the case file ────────────────────────────────────────────────────────


def test_case_file_keeps_only_figures_quoted_from_their_words():
    sources = discovery.casefile_sources(
        HALO[0],
        json.dumps([{"id": "q2", "question": "How full?", "answer": "About 10 of 12. The 6pm and 7pm ones have a waiting list."}]),
        "{}")
    out = discovery.shape_casefile({"figures": [
        {"source": "q2", "token": "About 10 of 12", "value": "10 of 12", "label": "a typical class"},
        {"source": "q2", "token": "About 10 of 12", "value": "11 of 12", "label": "made up"},
        {"source": "q2", "token": "about 11 of 12", "value": "11 of 12", "label": "not in her words"},
        {"source": "main_problem", "token": "about 8 hours a week", "value": "8 hrs", "label": "a week on bookings"},
    ]}, sources, False)
    assert [f["value"] for f in out["figures"]] == ["10 of 12", "8 hrs"]


# ── routes: roadmap, decisions, share, intake, revise ────────────────────


@pytest.fixture
def client(monkeypatch):
    from main import app
    from app.config import settings
    from app.routers import requests as requests_router

    Base.metadata.create_all(bind=engine)
    # the intake and a revise start the real pipeline in a thread — not here
    monkeypatch.setattr(requests_router.orchestrator, "run", lambda request_id: None)
    monkeypatch.setattr(settings, "MAX_CONCURRENT_GENERATIONS", 10_000)
    return TestClient(app)


def _row(**fields) -> Request:
    db = SessionLocal()
    try:
        req = Request(business_name="Halo Reformer Studio", business_description="A pilates studio.",
                      email="test@example.com", owner_email="test@example.com",
                      public_id=f"halo{os.urandom(4).hex()}",
                      **{"status": "done", "is_generating": False, **fields})
        db.add(req)
        db.commit()
        db.refresh(req)
        db.expunge(req)
        return req
    finally:
        db.close()


def _read(req_id: int) -> Request:
    db = SessionLocal()
    try:
        row = db.get(Request, req_id)
        db.expunge(row)
        return row
    finally:
        db.close()


READY = {"status": "ready", "title": "Implementation roadmap", "summary": "",
         "phases": [{"when": "Weeks 1 to 2", "title": "a", "do": "b", "by": "us", "you": ""},
                    {"when": "Weeks 3 to 4", "title": "c", "do": "d", "by": "together", "you": ""}],
         "decisions": [{"id": "d1", "question": "Go ahead?", "detail": "", "options": ["Yes", "Not yet"]},
                       {"id": "d2", "question": "When to go live?", "detail": "",
                        "options": ["This month", "Next month"]}],
         "assumptions": []}


def test_an_older_package_can_ask_for_its_roadmap_once(client, monkeypatch):
    from app.routers import requests as r

    started = []
    monkeypatch.setattr(r.plan_stage, "write_in_background", lambda rid: started.append(rid))
    req = _row(consulting_recommendations_json=json.dumps({"intervention_kind": "software"}))
    assert client.post(f"/api/requests/{req.public_id}/plan/retry").json()["plan_started"] is True
    # it is being written now: a second press is refused, not a second writer
    assert client.post(f"/api/requests/{req.public_id}/plan/retry").status_code == 409
    assert started == [req.id]


def test_the_owner_answers_decisions_and_they_merge(client, monkeypatch):
    from app import mailer

    sent = []
    monkeypatch.setattr(mailer, "notify_team_go_ahead", lambda *a: sent.append(a))
    req = _row(action_plan_json=json.dumps(READY), decisions_json=json.dumps({"choices": {"d1": "Yes"}}))
    r = client.post(f"/api/requests/{req.public_id}/decisions",
                    data={"choices": json.dumps({"d2": "Next month", "d7": "Yes"})})
    assert r.status_code == 200
    assert r.json()["decisions"] == {"choices": {"d1": "Yes", "d2": "Next month"}}
    assert not sent
    got = client.get(f"/api/requests/{req.public_id}/plan").json()
    assert got["decisions"]["choices"] == {"d1": "Yes", "d2": "Next month"}
    assert got["plan"]["title"] == "Implementation roadmap"


def test_go_ahead_is_recorded_and_the_team_is_told(client, monkeypatch):
    from app import mailer

    sent = []
    monkeypatch.setattr(mailer, "notify_team_go_ahead", lambda *a: sent.append(a))
    req = _row(action_plan_json=json.dumps(READY))
    body = client.post(f"/api/requests/{req.public_id}/decisions",
                       data={"choices": json.dumps({"d1": "Yes"}), "go": "true"}).json()
    assert body["decisions"]["go_ahead"] is True and body["decisions"]["go_at"]
    assert json.loads(_read(req.id).decisions_json)["go_ahead"] is True
    assert len(sent) == 1 and sent[0][3] == {"Go ahead?": "Yes"}


def test_only_the_owner_answers_decisions(client, monkeypatch):
    from app import auth_client

    req = _row(action_plan_json=json.dumps(READY))
    monkeypatch.setattr(auth_client, "resolve_user", lambda a: {"email": "someone@else.com", "name": "X"})
    r = client.post(f"/api/requests/{req.public_id}/decisions", data={"choices": json.dumps({"d1": "Yes"})})
    assert r.status_code == 403
    assert _read(req.id).decisions_json is None


def test_the_retired_pilot_routes_are_gone(client):
    req = _row(status="awaiting_approval", action_plan_json=json.dumps(READY))
    assert client.post(f"/api/requests/{req.public_id}/decision/accept").status_code in (404, 405)
    assert client.post(f"/api/requests/{req.public_id}/plan/log", data={"week": 1}).status_code in (404, 405)
    assert client.get(f"/api/requests/{req.public_id}/export/pdf/pilot").status_code == 404


def test_they_can_push_back_while_the_plans_are_being_written(client):
    req = _row(status="building", is_generating=True)
    r = client.post(f"/api/requests/{req.public_id}/decision/revise",
                    data={"note": "You have the evening numbers wrong, it is 11 of 12."})
    assert r.status_code == 200 and r.json()["started"] is True
    row = _read(req.id)
    assert row.status == "new" and "11 of 12" in row.business_description


def test_intake_stores_the_brief_and_names_what_they_did_not_know(client):
    brief = {"question": "Should Halo raise its evening prices?", "lets": {"know": "whether to", "bad": 1},
             "in_scope": ["pricing", 5], "out_scope": "not a list",
             "facts": [{"key": "price", "group": "Money", "label": "What you charge", "status": "got",
                        "value": "$22"},
                       {"key": "costs", "label": "Monthly running costs", "status": "weird"},
                       "junk", {"label": "no key"}]}
    r = client.post("/api/requests", data={
        "business_name": "Halo", "business_description": "A pilates studio.", "email": "o@example.com",
        "brief": json.dumps(brief), "unknowns": json.dumps(["Monthly running costs", 7, "Monthly running costs"]),
    })
    assert r.status_code == 200
    row = _read(r.json()["id"])
    stored = json.loads(row.brief_json)
    assert stored["question"] == brief["question"]
    assert stored["lets"] == {"know": "whether to"}
    assert stored["in_scope"] == ["pricing"] and stored["out_scope"] == []
    assert [f["key"] for f in stored["facts"]] == ["price", "costs"]
    assert stored["facts"][1]["status"] == "need"
    assert "estimate these, and label every estimate as ours" in row.business_description
    assert row.business_description.count("- Monthly running costs") == 1
    assert "The question this engagement answers: Should Halo raise" in row.business_description
    assert row.desired_outcome == brief["question"]
    preview = client.get(f"/api/requests/{row.public_id}/preview").json()
    assert preview["brief"]["question"] == brief["question"] and preview["decisions"] == {}


@pytest.mark.parametrize("bad", ["not json", "[1, 2]", "{}", json.dumps({"facts": "x"})])
def test_a_malformed_brief_is_dropped_not_a_500(client, bad):
    r = client.post("/api/requests", data={
        "business_name": "Halo", "business_description": "A pilates studio.", "email": "o@example.com",
        "brief": bad, "unknowns": "{not json",
    })
    assert r.status_code == 200
    row = _read(r.json()["id"])
    assert row.brief_json is None and row.business_description == "A pilates studio."


def test_a_partner_link_opens_the_package_read_only_and_can_be_turned_off(client):
    req = _row(action_plan_json=json.dumps(READY), decisions_json=json.dumps({"choices": {"d1": "Yes"}}))
    token = client.post(f"/api/requests/{req.public_id}/share").json()["token"]
    # the same link every time until it is revoked
    assert client.post(f"/api/requests/{req.public_id}/share").json()["token"] == token
    shared = client.get(f"/api/shared/{token}").json()
    assert shared["business_name"] == "Halo Reformer Studio"
    assert shared["action_plan"]["title"] == "Implementation roadmap"
    assert shared["decisions"] == {"choices": {"d1": "Yes"}}
    assert "pilot" not in shared["documents"] and "pilot_log" not in shared
    assert "public_id" not in shared and "owner_email" not in shared
    assert client.get(f"/api/shared/{token}/export/pilot").status_code == 404
    client.delete(f"/api/requests/{req.public_id}/share")
    assert client.get(f"/api/shared/{token}").status_code == 404


def test_only_the_owner_can_share(client, monkeypatch):
    from app import auth_client

    req = _row()
    monkeypatch.setattr(auth_client, "resolve_user", lambda a: {"email": "someone@else.com", "name": "X"})
    assert client.post(f"/api/requests/{req.public_id}/share").status_code == 403


# ── the build supersedes itself when they push back ──────────────────────


def _building_row():
    from datetime import datetime

    return _row(status="building", is_generating=True, phase_started_at=datetime(2026, 9, 26, 10, 0, 0, 123456))


def _restart(req_id: int) -> None:
    """What a revise does to the row: a new diagnosis, a new token."""
    from datetime import datetime

    db = SessionLocal()
    try:
        row = db.get(Request, req_id)
        row.status, row.phase_started_at = "new", datetime(2026, 9, 26, 10, 5, 0)
        db.commit()
    finally:
        db.close()


def test_the_supersede_check_passes_only_for_the_current_build():
    from app.pipeline import orchestrator

    Base.metadata.create_all(bind=engine)
    req = _building_row()
    db = SessionLocal()
    try:
        orchestrator._check_current(db, req.id, req.phase_started_at)
        with pytest.raises(orchestrator._Superseded):
            orchestrator._check_current(db, req.id, req.phase_started_at.replace(microsecond=0))
        _restart(req.id)
        with pytest.raises(orchestrator._Superseded):
            orchestrator._check_current(db, req.id, req.phase_started_at)
    finally:
        db.close()


@pytest.mark.parametrize("stage_raises", [False, True])
def test_a_superseded_build_stops_quietly_and_is_not_marked_failed(monkeypatch, stage_raises):
    from app.pipeline import orchestrator

    Base.metadata.create_all(bind=engine)
    req = _building_row()
    later = []

    def planning(db, request_id, consult_result):
        _restart(request_id)  # they pushed back while this stage ran
        if stage_raises:
            raise RuntimeError("the row changed under me")
        return {"concept_name": "x"}

    monkeypatch.setattr(orchestrator.plan, "plan_integration", planning)
    monkeypatch.setattr(orchestrator, "_decompose_with_preflight", lambda *a, **k: later.append("decompose"))
    orchestrator.run_build(req.id)
    row = _read(req.id)
    assert later == []  # nothing after the supersede ran
    assert row.status == "new" and not row.is_failed
