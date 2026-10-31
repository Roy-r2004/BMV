"""The system, screen by screen: the block vocabulary is bounded, the render
is faithful, the stage builds from a model that answers in that vocabulary,
and the site can read it back. Nothing here needs a browser: the PNG and PDF
paths are skipped when Chromium is absent, and the live HTML needs neither.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.models import AiUsageEvent, Request
from app.pipeline.failure import StageFailed
from app.screens import browser, generate, render, schema
from main import app


@pytest.fixture(autouse=True)
def _fresh_db():
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client():
    return TestClient(app)


# ── the vocabulary ───────────────────────────────────────────────────────


def test_the_example_shapes_cleanly_and_carries_every_screen():
    system, problems = schema.shape_system(render.load_example())
    assert problems == []
    assert len(system["screens"]) == 12
    kinds = {b["kind"] for s in system["screens"] for row in s["rows"] for b in row}
    assert kinds == set(schema.BLOCK_KINDS)


def test_unknown_kinds_are_dropped_and_lists_are_bounded():
    rows, problems = schema.shape_rows([
        [{"kind": "hologram", "title": "x"}, {"kind": "table", "columns": ["A", "B"], "rows": [["1", "2"]] * 30}],
        [{"kind": "kpis", "items": [{"value": "1", "label": "one"}]}],  # one tile is not a row of tiles
    ])
    assert len(rows) == 1 and len(rows[0]) == 1
    assert len(rows[0][0]["rows"]) == schema.LIMITS["table_rows"]
    assert any("hologram" in p for p in problems) and any("kpis" in p for p in problems)


def test_a_plan_is_bounded_and_always_has_a_navigation():
    raw = {"product": {"name": "X", "accent": "neon"},
           "screens": [{"id": f"s{i}", "title": f"Screen {i}", "caption": "c"} for i in range(30)]}
    plan, problems = schema.shape_plan(raw)
    assert plan and problems == []
    assert len(plan["screens"]) == schema.SCREENS_MAX
    assert plan["product"]["accent"] == schema.DEFAULT_ACCENT
    # no navigation in the reply: one is built that lists every screen
    assert [i["screen"] for g in plan["nav"] for i in g["items"]] == [s["id"] for s in plan["screens"]]


def test_too_few_screens_is_no_plan():
    plan, problems = schema.shape_plan({"screens": [{"id": "a", "title": "A"}]})
    assert plan is None and problems


# ── the render ───────────────────────────────────────────────────────────


def test_the_live_page_draws_every_screen_and_keeps_its_stylesheet_raw():
    system, _ = schema.shape_system(render.load_example())
    html = render.system_html(system, mode="web")
    for s in system["screens"]:
        assert f'id="screen-{s["id"]}"' in html
    style = html.split("<style>")[1].split("</style>")[0]
    assert "&gt;" not in style and "&#34;" not in style
    assert "Sample data" in html and "bmv:shown" in html


def test_the_proposal_prints_only_what_the_run_holds():
    system, _ = schema.shape_system(render.load_example())
    ctx = render.proposal_context(system, business_name="Halo Reformer Studio LLC")
    html = render.proposal_html(system, ctx)
    assert ctx["business_short"] == "Halo Reformer Studio"
    assert "What this is worth" not in html            # no move, no worth page
    assert html.count('class="page') == 1 + 1 + 1 + 12 + 1 + 1 + 1 + 1 + 1 + 1  # cover, ambition, index, screens, changes, platform, principles, fit, comparison, go-live
    ctx = render.proposal_context(system, business_name="Halo", answer={"move": {"display": "≈ $45,000 a year", "label": "l", "working": "w"}})
    assert "What this is worth" in render.proposal_html(system, ctx)
    assert len(ctx["groups"]) <= 4


# ── the stage ────────────────────────────────────────────────────────────


def _plan_reply():
    ex = render.load_example()
    return {"product": ex["product"], "nav": ex["nav"], "cast": ex["cast"],
            "screens": [{"id": s["id"], "title": s["title"], "caption": s["caption"], "module_id": s["module_id"],
                         "brief": "as in the example", "blocks": [b["kind"] for r in s["rows"] for b in r][:4]}
                        for s in ex["screens"][:6]],
            "story": dict(ex["story"], intro="Halo serves 340 clients a week. One record follows each client.",
                          changes=ex["story"]["changes"] + [{"today": "You lose $9,000 a month.", "with": "x", "means": "y"}])}


def _fake_chat(monkeypatch, replies: dict):
    calls = []

    def chat(model, messages, **kwargs):
        prompt = messages[0]["content"]
        calls.append(prompt)
        key = "screen" if "THE SCREEN TO DRAW" in prompt else "plan"
        reply = replies[key](prompt) if callable(replies[key]) else replies[key]
        return {"choices": [{"message": {"content": json.dumps(reply, ensure_ascii=False)}}], "usage": {}}

    monkeypatch.setattr(generate.provider, "chat", chat)
    return calls


def _ledger(db, request_id: int) -> list[tuple[str, bool]]:
    """The cost ledger for a run, oldest first: (purpose, success)."""
    rows = db.query(AiUsageEvent).filter(AiUsageEvent.request_id == request_id).order_by(AiUsageEvent.id)
    return [(e.purpose, e.success) for e in rows]


def _request(db) -> Request:
    req = Request(business_name="Halo Reformer Studio",
                  business_description="12 reformers. Six classes a day, six days a week. $22 a class. The 6pm and 7pm classes have a waiting list.",
                  email="o@example.com", owner_email="test@example.com", status="building", concept_name="Halo",
                  modules_json=json.dumps([{"id": "client-booking-portal", "name": "Client Booking Portal", "purpose": "Book classes",
                                            "spec": {"features": [{"name": "Book a class"}], "data": ["bookings"], "ai": None, "integrations": []}}]),
                  journey_json=json.dumps({"stages": [{"stage": "Find a class"}, {"stage": "Book"}, {"stage": "Attend"}]}))
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def test_the_stage_builds_a_system_from_the_plan_and_screen_calls(monkeypatch):
    ex = {s["id"]: s for s in render.load_example()["screens"]}

    def screen_reply(prompt):
        title = prompt.split("Title: ")[1].split("\n")[0].strip()
        s = next(x for x in ex.values() if x["title"] == title)
        return {"heading": s.get("heading", ""), "subheading": s.get("subheading", ""), "actions": s.get("actions", []), "rows": s["rows"]}

    calls = _fake_chat(monkeypatch, {"plan": _plan_reply(), "screen": screen_reply})
    monkeypatch.setattr(browser, "available", lambda: False)
    db = SessionLocal()
    req = _request(db)
    assert generate.build(db, req.id) == 6
    assert len(calls) == 1 + 6
    db.refresh(req)
    system = generate.load(req)
    assert [s["id"] for s in system["screens"]] == list(ex)[:6]
    assert system["product"]["name"] == "Halo"
    # the sample data on screens stands; statements about the business are checked
    assert "340" not in system["story"]["intro"] and "One record follows" in system["story"]["intro"]
    assert not any("9,000" in c["today"] for c in system["story"]["changes"])
    assert len(system["story"]["changes"]) == 5
    # the site's payload: live html, no thumbnails without a browser
    p = generate.payload(req)
    assert p["available"] and p["pdf_available"] is False
    assert p["screens"][0]["png_url"] is None and 'id="screen-today"' in p["html"]
    db.close()


def test_a_screen_the_renderer_cannot_draw_is_retried_then_dropped(monkeypatch):
    ex = {s["id"]: s for s in render.load_example()["screens"]}
    seen = {}

    def screen_reply(prompt):
        title = prompt.split("Title: ")[1].split("\n")[0].strip()
        seen[title] = seen.get(title, 0) + 1
        if title == "Schedule":
            return {"rows": [[{"kind": "nothing"}]]}
        s = next(x for x in ex.values() if x["title"] == title)
        return {"rows": s["rows"]}

    _fake_chat(monkeypatch, {"plan": _plan_reply(), "screen": screen_reply})
    monkeypatch.setattr(browser, "available", lambda: False)
    db = SessionLocal()
    req = _request(db)
    assert generate.build(db, req.id) == 5
    assert seen["Schedule"] == 2
    db.refresh(req)
    ids = [s["id"] for s in generate.load(req)["screens"]]
    assert "schedule" not in ids and "today" in ids
    # the navigation still lists it, marked absent, so the sidebar stays whole
    nav = {i["screen"]: i["live"] for g in generate.load(req)["nav"] for i in g["items"]}
    assert nav["schedule"] is False and nav["today"] is True
    db.close()


def test_a_screen_that_overflows_the_frame_is_redrawn_once_with_the_reason(monkeypatch):
    ex = {s["id"]: s for s in render.load_example()["screens"]}
    prompts = {}

    def screen_reply(prompt):
        title = prompt.split("Title: ")[1].split("\n")[0].strip()
        prompts.setdefault(title, []).append(prompt)
        s = next(x for x in ex.values() if x["title"] == title)
        return {"rows": s["rows"]}

    _fake_chat(monkeypatch, {"plan": _plan_reply(), "screen": screen_reply})
    # a browser that finds the schedule 120px too tall, then nothing to capture
    monkeypatch.setattr(browser, "available", lambda: True)
    monkeypatch.setattr(browser, "measure_overflow", lambda html, ids: {"schedule": 120})
    monkeypatch.setattr(browser, "render_pngs", lambda html, ids, out_dir, scale=2: {})
    db = SessionLocal()
    req = _request(db)
    assert generate.build(db, req.id) == 6
    assert len(prompts["Schedule"]) == 2 and len(prompts["Today"]) == 1
    assert "120px past the bottom" in prompts["Schedule"][1]
    db.close()


def test_a_failed_plan_call_stops_the_stage_and_saves_nothing(monkeypatch):
    def chat(model, messages, **kwargs):
        raise RuntimeError("402 sk-or-v1-SECRET")

    monkeypatch.setattr(generate.provider, "chat", chat)
    db = SessionLocal()
    req = _request(db)
    with pytest.raises(StageFailed) as stopped:
        generate.build(db, req.id)
    assert stopped.value.stage == "screens" and "402" in stopped.value.cause
    db.refresh(req)
    assert req.screens_json is None
    # the failed call is on the cost ledger
    assert _ledger(db, req.id) == [("screens_plan:1", False)]
    db.close()


def test_a_plan_the_model_cannot_get_right_stops_the_stage(monkeypatch):
    """The calls worked; both replies plan too few screens. No plan, no screens:
    the stage does not carry on to draw nothing and report success."""
    calls = _fake_chat(monkeypatch, {"plan": {"screens": [{"id": "a", "title": "A"}]}, "screen": {}})
    db = SessionLocal()
    req = _request(db)
    with pytest.raises(StageFailed) as stopped:
        generate.build(db, req.id)
    # the cause is what was wrong with the plan, not just the stage's name
    _, problems = schema.shape_plan({"screens": [{"id": "a", "title": "A"}]})
    assert stopped.value.stage == "screens"
    assert stopped.value.cause.startswith("no usable plan for the system:") and problems[0] in stopped.value.cause
    assert len(calls) == 2  # asked again once, with the reasons
    assert _ledger(db, req.id) == [("screens_plan:1", True), ("screens_plan:2", True)]
    db.refresh(req)
    assert req.screens_json is None
    db.close()


def _screen_reply_failing_for(ex: dict, failing_title: str | None, fail_from: int = 1):
    """A screen reply that raises (as a down provider does) for one screen's
    calls from its `fail_from`-th call on, and draws the rest from the example."""
    seen = {}

    def screen_reply(prompt):
        title = prompt.split("Title: ")[1].split("\n")[0].strip()
        seen[title] = seen.get(title, 0) + 1
        if title == failing_title and seen[title] >= fail_from:
            raise RuntimeError("503 sk-or-v1-SECRET")
        s = next(x for x in ex.values() if x["title"] == title)
        return {"rows": s["rows"]}

    return screen_reply


def test_a_screen_whose_call_fails_stops_the_stage_and_saves_nothing(monkeypatch):
    ex = {s["id"]: s for s in render.load_example()["screens"]}
    _fake_chat(monkeypatch, {"plan": _plan_reply(), "screen": _screen_reply_failing_for(ex, "Schedule")})
    monkeypatch.setattr(browser, "available", lambda: False)
    db = SessionLocal()
    req = _request(db)
    with pytest.raises(StageFailed) as stopped:
        generate.build(db, req.id)
    assert stopped.value.stage == "screens" and "503" in stopped.value.cause
    db.refresh(req)
    assert req.screens_json is None
    # every call made is on the ledger, the failed one as failed
    ledger = _ledger(db, req.id)
    assert ("screen:schedule:1", False) in ledger
    assert sum(1 for _, ok in ledger if ok) == 1 + 5 and sum(1 for _, ok in ledger if not ok) == 1
    db.close()


def test_when_the_first_screen_cannot_be_drawn_the_rest_are_not_paid_for(monkeypatch):
    ex = {s["id"]: s for s in render.load_example()["screens"]}
    calls = _fake_chat(monkeypatch, {"plan": _plan_reply(), "screen": _screen_reply_failing_for(ex, "Today")})
    monkeypatch.setattr(browser, "available", lambda: False)
    db = SessionLocal()
    req = _request(db)
    with pytest.raises(StageFailed):
        generate.build(db, req.id)
    assert len(calls) == 2  # the plan and the overview, no more
    assert _ledger(db, req.id) == [("screens_plan:1", True), ("screen:today:1", False)]
    db.close()


def _screen_reply_undrawable_for(ex: dict, undrawable: set):
    """A screen reply that is valid JSON but nothing the renderer can draw, for
    the named screens (no call fails), and a real drawing for the rest."""
    def screen_reply(prompt):
        title = prompt.split("Title: ")[1].split("\n")[0].strip()
        if title in undrawable:
            return {"rows": [[{"kind": "nothing"}]]}
        s = next(x for x in ex.values() if x["title"] == title)
        return {"rows": s["rows"]}

    return screen_reply


@pytest.mark.parametrize("undrawable_count, drawn", [(6, 0), (3, 3)])
def test_too_few_drawable_screens_stop_the_stage_and_save_nothing(monkeypatch, undrawable_count, drawn):
    """No call failed: the model answered every one, and its answers could not
    be drawn. Fewer than the minimum is not a system, and the run does not go on
    to call it finished."""
    ex = {s["id"]: s for s in render.load_example()["screens"]}
    titles = [s["title"] for s in _plan_reply()["screens"]]
    calls = _fake_chat(monkeypatch, {
        "plan": _plan_reply(), "screen": _screen_reply_undrawable_for(ex, set(titles[6 - undrawable_count:]))})
    monkeypatch.setattr(browser, "available", lambda: False)
    db = SessionLocal()
    req = _request(db)
    with pytest.raises(StageFailed) as stopped:
        generate.build(db, req.id)
    assert stopped.value.stage == "screens" and stopped.value.cause == f"only {drawn} screens could be drawn"
    db.refresh(req)
    assert req.screens_json is None
    # every call that was made is on the ledger, none of them failed
    ledger = _ledger(db, req.id)
    assert len(ledger) == len(calls) and all(ok for _, ok in ledger)
    db.close()


def test_exactly_the_minimum_number_of_screens_is_a_system(monkeypatch):
    ex = {s["id"]: s for s in render.load_example()["screens"]}
    titles = [s["title"] for s in _plan_reply()["screens"]]
    _fake_chat(monkeypatch, {
        "plan": _plan_reply(), "screen": _screen_reply_undrawable_for(ex, set(titles[schema.SCREENS_MIN:]))})
    monkeypatch.setattr(browser, "available", lambda: False)
    db = SessionLocal()
    req = _request(db)
    assert generate.build(db, req.id) == schema.SCREENS_MIN
    db.close()


def test_a_failed_redraw_keeps_the_screen_as_it_was_drawn(monkeypatch):
    """Fitting a screen to its frame is polish on a screen that exists: when the
    redraw call fails the screen stays as drawn, and the stage still succeeds."""
    ex = {s["id"]: s for s in render.load_example()["screens"]}
    _fake_chat(monkeypatch, {"plan": _plan_reply(), "screen": _screen_reply_failing_for(ex, "Schedule", fail_from=2)})
    monkeypatch.setattr(browser, "available", lambda: True)
    monkeypatch.setattr(browser, "measure_overflow", lambda html, ids: {"schedule": 120})
    monkeypatch.setattr(browser, "render_pngs", lambda html, ids, out_dir, scale=2: {})
    db = SessionLocal()
    req = _request(db)
    assert generate.build(db, req.id) == 6
    db.refresh(req)
    assert "schedule" in [s["id"] for s in generate.load(req)["screens"]]
    assert ("screen-fit:schedule:1", False) in _ledger(db, req.id)
    db.close()


def test_a_frame_that_cannot_be_measured_leaves_the_screens_as_drawn(monkeypatch):
    ex = {s["id"]: s for s in render.load_example()["screens"]}
    _fake_chat(monkeypatch, {"plan": _plan_reply(), "screen": _screen_reply_failing_for(ex, None)})

    def cannot_measure(html, ids):
        raise RuntimeError("browser crashed")

    monkeypatch.setattr(browser, "available", lambda: True)
    monkeypatch.setattr(browser, "measure_overflow", cannot_measure)
    monkeypatch.setattr(browser, "render_pngs", lambda html, ids, out_dir, scale=2: {})
    db = SessionLocal()
    req = _request(db)
    assert generate.build(db, req.id) == 6
    db.close()


# ── the routes ───────────────────────────────────────────────────────────


def test_the_system_route_serves_the_live_page_or_says_there_is_none(client, monkeypatch):
    monkeypatch.setattr(browser, "available", lambda: False)
    db = SessionLocal()
    req = _request(db)
    ref = req.public_id or str(req.id)
    assert client.get(f"/api/requests/{ref}/system").json()["available"] is False
    system, _ = schema.shape_system(render.load_example())
    req.screens_json = json.dumps(system)
    db.commit()
    body = client.get(f"/api/requests/{ref}/system").json()
    assert body["available"] and body["product"]["name"] == "Halo"
    assert [s["id"] for s in body["screens"]][:2] == ["today", "schedule"]
    assert body["screens"][0]["caption"].startswith("The owner sees")
    assert "bmv:show" in body["html"]
    # the proposal needs a browser; without one the route says so, rather than 500
    assert client.get(f"/api/requests/{ref}/export/pdf/system").status_code == 503
    db.close()


@pytest.mark.skipif(not browser.available(), reason="no browser here")
def test_with_a_browser_the_screens_become_pngs_and_the_proposal_a_pdf(tmp_path, monkeypatch):
    system, _ = schema.shape_system(render.load_example())
    pngs = browser.render_pngs(render.system_html(system, mode="print"), ["today", "reports"], str(tmp_path))
    assert set(pngs) == {"today", "reports"}
    ctx = render.proposal_context(system, business_name="Halo Reformer Studio")
    pdf = browser.render_pdf(render.proposal_html(system, ctx), str(tmp_path / "p.pdf"))
    assert (tmp_path / "p.pdf").stat().st_size > 50_000
