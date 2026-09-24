"""Pins for the consultation flow's new parts: the week, the answer, the plan,
the tracker, the case file and the partner link.

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


# ── the plan and the tracker ─────────────────────────────────────────────


def _plan_raw(**over):
    raw = {
        "title": "Pricing pilot plan", "summary": "Move evenings to $28 for six weeks.", "weeks": 6,
        "monday": [{"do": "Tell your 6pm and 7pm regulars the new $28 price.", "why": "Two weeks' notice."},
                   {"do": "Keep daytime classes at $22.", "why": "So the effect reads cleanly."}],
        "schedule": [{"when": "Week 1", "do": "Announce."}],
        "message": {"to": "your evening regulars", "text": "From the 1st, evening classes are $28."},
        "measures": [{"id": "m1", "name": "Evening spots taken", "unit": "spots a week", "watch": "hold",
                      "baseline": 144, "baseline_from": "CAP-05"},
                     {"id": "m2", "name": "Evening waiting list", "unit": "people", "watch": "down",
                      "baseline": 31, "baseline_from": "CF-04"}],
        "decision_rule": "Keep $28 if evening fill stays above 10 of 12.",
        "assumptions": ["How regulars respond to $28"],
    }
    raw.update(over)
    return raw


def test_a_baseline_must_be_her_figure_by_id():
    allowed = answer.allowed_numbers(HALO, CLAIMS, answer.compute_move(MOVE, CLAIMS))
    plan, _ = action_plan.shape(_plan_raw(), CLAIMS, allowed, 6)
    by = {m["name"]: m for m in plan["measures"]}
    assert by["Evening spots taken"]["baseline"] == 144
    # 31 is not what CF-04 holds: measured in week 1, never estimated
    assert by["Evening waiting list"]["baseline"] is None


def test_an_invented_price_in_a_monday_step_drops_the_step():
    allowed = answer.allowed_numbers(HALO, CLAIMS, answer.compute_move(MOVE, CLAIMS))
    raw = _plan_raw(monday=[{"do": "Match the $35 studio down the road.", "why": ""},
                            {"do": "Tell your regulars the new $28 price.", "why": ""},
                            {"do": "Keep daytime at $22.", "why": ""}])
    plan, problems = action_plan.shape(raw, CLAIMS, allowed, 6)
    assert [s["do"] for s in plan["monday"]] == ["Tell your regulars the new $28 price.", "Keep daytime at $22."]
    assert problems


def test_the_tracker_only_keeps_the_plans_own_measures():
    plan = {"measures": [{"id": "m1"}, {"id": "m2"}]}
    log = action_plan.record(plan, [], 1, {"m1": "140", "m9": 5, "m2": "x"}, "first week")
    assert log == [{"week": 1, "values": {"m1": 140.0}, "note": "first week"}]
    log = action_plan.record(plan, log, 1, {"m1": 142}, "")
    assert len(log) == 1 and log[0]["values"] == {"m1": 142.0}


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


# ── routes: plan, tracker, share ─────────────────────────────────────────


@pytest.fixture
def client(monkeypatch):
    from main import app

    Base.metadata.create_all(bind=engine)
    return TestClient(app)


def _row(**fields) -> Request:
    db = SessionLocal()
    try:
        req = Request(business_name="Halo Reformer Studio", business_description="A pilates studio.",
                      email="test@example.com", owner_email="test@example.com",
                      public_id=f"halo{os.urandom(4).hex()}", is_generating=False,
                      **{"status": "advised", **fields})
        db.add(req)
        db.commit()
        db.refresh(req)
        db.expunge(req)
        return req
    finally:
        db.close()


READY = {"status": "ready", "title": "Pricing pilot plan", "weeks": 6,
         "monday": [{"do": "a", "why": ""}, {"do": "b", "why": ""}],
         "measures": [{"id": "m1", "name": "Evening spots", "unit": "", "watch": "hold",
                       "baseline": None, "baseline_from": None}]}


def test_accept_starts_the_plan_once(client, monkeypatch):
    from app.routers import requests as r

    started = []
    monkeypatch.setattr(r.plan_stage, "write_in_background", lambda rid, building=False: started.append(rid))
    req = _row(status="awaiting_approval")
    first = client.post(f"/api/requests/{req.public_id}/decision/accept").json()
    second = client.post(f"/api/requests/{req.public_id}/decision/accept").json()
    assert first["status"] == "advised" and first["plan_started"] is True
    assert second["plan_started"] is False
    assert started == [req.id]


def test_an_older_package_can_ask_for_its_plan_once(client, monkeypatch):
    from app.routers import requests as r

    started = []
    monkeypatch.setattr(r.plan_stage, "write_in_background", lambda rid, building=False: started.append(rid))
    req = _row(status="done", consulting_recommendations_json=json.dumps({"intervention_kind": "software"}))
    assert client.post(f"/api/requests/{req.public_id}/plan/retry").json()["plan_started"] is True
    # it is being written now: a second press is refused, not a second writer
    assert client.post(f"/api/requests/{req.public_id}/plan/retry").status_code == 409
    assert started == [req.id]


def test_the_owner_logs_a_week_and_reads_it_back(client):
    req = _row(action_plan_json=json.dumps(READY))
    r = client.post(f"/api/requests/{req.public_id}/plan/log", data={"week": 2, "values": json.dumps({"m1": 140})})
    assert r.status_code == 200
    got = client.get(f"/api/requests/{req.public_id}/plan").json()
    assert got["log"] == [{"week": 2, "values": {"m1": 140.0}, "note": ""}]


def test_logging_needs_a_ready_plan(client):
    req = _row(action_plan_json=json.dumps({"status": "writing"}))
    r = client.post(f"/api/requests/{req.public_id}/plan/log", data={"week": 1, "values": "{}"})
    assert r.status_code == 409


def test_a_partner_link_opens_the_package_read_only_and_can_be_turned_off(client):
    req = _row(action_plan_json=json.dumps(READY))
    token = client.post(f"/api/requests/{req.public_id}/share").json()["token"]
    # the same link every time until it is revoked
    assert client.post(f"/api/requests/{req.public_id}/share").json()["token"] == token
    shared = client.get(f"/api/shared/{token}").json()
    assert shared["business_name"] == "Halo Reformer Studio"
    assert shared["action_plan"]["title"] == "Pricing pilot plan"
    assert "public_id" not in shared and "owner_email" not in shared
    client.delete(f"/api/requests/{req.public_id}/share")
    assert client.get(f"/api/shared/{token}").status_code == 404


def test_only_the_owner_can_share(client, monkeypatch):
    from app import auth_client

    req = _row()
    monkeypatch.setattr(auth_client, "resolve_user", lambda a: {"email": "someone@else.com", "name": "X"})
    assert client.post(f"/api/requests/{req.public_id}/share").status_code == 403


def test_the_pilot_pdf_renders_from_a_ready_plan(client):
    req = _row(action_plan_json=json.dumps(dict(READY, message={"to": "regulars", "text": "Evenings are $28."},
                                                decision_rule="Keep it if fill holds.")))
    r = client.get(f"/api/requests/{req.public_id}/export/pdf/pilot")
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
