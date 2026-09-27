"""The system, screen by screen: the block vocabulary is bounded, the render
is faithful, the stage builds from a model that answers in that vocabulary,
and the site can read it back. Nothing here needs a browser: the PNG and PDF
paths are skipped when Chromium is absent, and the live HTML needs neither.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.models import Request
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
    assert [i["screen"] for i in plan["nav"][0]["items"]] == [s["id"] for s in plan["screens"]][:8] or plan["nav"]


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


def test_a_failed_plan_call_saves_nothing_and_does_not_raise(monkeypatch):
    def chat(model, messages, **kwargs):
        raise RuntimeError("402")

    monkeypatch.setattr(generate.provider, "chat", chat)
    db = SessionLocal()
    req = _request(db)
    assert generate.build(db, req.id) == 0
    db.refresh(req)
    assert req.screens_json is None
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
