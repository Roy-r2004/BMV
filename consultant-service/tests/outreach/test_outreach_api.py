"""Roy's list and the private report, over the API."""
import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.models import Prospect
from app.outreach import new_token

TOKEN = "reviewer-secret"
REPORT = {"today": "Glow takes bookings by DM.", "changes": [{"change": "a", "ai": "b", "day_to_day": "c", "difference": "d"}] * 2,
          "sources_note": "Read from its website."}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "REVIEW_TOKEN", TOKEN)
    from main import app

    return TestClient(app)


def _queued(db, status="queued", **kw):
    p = Prospect(token=new_token(), name="Glow Salon", city="Dubai", kind="salon", key=f"k-{new_token()}",
                 instagram="glow.dxb", website="https://glowsalon.ae", score=60, status=status,
                 reasons_json=json.dumps(["Bookings are taken by message or phone"]),
                 sources_json=json.dumps([{"url": "https://glowsalon.ae", "what": "its website"}]),
                 report_json=json.dumps(REPORT), dm_text="Hi Glow Salon team, here it is: {link}", **kw)
    db.add(p)
    db.commit()
    return p


ADMIN = {"X-Review-Token": TOKEN}


def test_admin_needs_the_token(client):
    assert client.get("/api/outreach/list").status_code == 403
    assert client.get("/api/outreach/list", headers={"X-Review-Token": "wrong"}).status_code == 403
    assert client.post("/api/outreach/fill").status_code == 403


def test_no_token_configured_means_no_admin(client, monkeypatch):
    monkeypatch.setattr(settings, "REVIEW_TOKEN", "")
    assert client.get("/api/outreach/list", headers={"X-Review-Token": ""}).status_code == 403


def test_the_list_shows_unsent_businesses_with_the_link_in_the_message(client, db):
    p = _queued(db)
    _queued(db, status="sent")
    body = client.get("/api/outreach/list", headers=ADMIN).json()
    [row] = body["rows"]
    url = f"{settings.PUBLIC_SITE_URL}/for/{p.token}"
    assert row["report_url"] == url and row["dm"].endswith(url) and "{link}" not in row["dm"]
    assert row["instagram_url"] == "https://instagram.com/glow.dxb" and row["reasons"]
    assert body["cap"] == settings.OUTREACH_MONTHLY_USD and "spent" in body and "running" in body


def test_the_list_can_show_what_was_sent(client, db):
    _queued(db, status="sent")
    assert len(client.get("/api/outreach/list?status=sent", headers=ADMIN).json()["rows"]) == 1


def test_marking_sent_records_the_time(client, db):
    p = _queued(db)
    assert client.patch(f"/api/outreach/{p.id}", json={"status": "sent"}, headers=ADMIN).status_code == 200
    db.refresh(p)
    assert p.status == "sent" and p.sent_at is not None


def test_an_unknown_status_is_refused(client, db):
    p = _queued(db)
    assert client.patch(f"/api/outreach/{p.id}", json={"status": "queued"}, headers=ADMIN).status_code == 422


def test_the_report_is_not_indexed_and_carries_its_sources(client, db):
    p = _queued(db, status="sent")
    r = client.get(f"/api/outreach/report/{p.token}", headers={"User-Agent": "Mozilla/5.0 Chrome/130"})
    assert r.status_code == 200 and "noindex" in r.headers["X-Robots-Tag"]
    body = r.json()
    assert body["sources"] == ["https://glowsalon.ae"] and body["book_subject"] == "Call about Glow Salon"
    assert body["email"] == "consulting@buildmyversion.com"


def test_a_preview_bot_is_not_an_open(client, db):
    p = _queued(db, status="sent")
    client.get(f"/api/outreach/report/{p.token}", headers={"User-Agent": "facebookexternalhit/1.1"})
    db.refresh(p)
    assert p.opens == 0
    client.get(f"/api/outreach/report/{p.token}", headers={"User-Agent": "Mozilla/5.0 Chrome/130"})
    db.refresh(p)
    assert p.opens == 1 and p.opened_first_at is not None


def test_a_removed_page_is_gone(client, db):
    p = _queued(db, status="removed")
    assert client.get(f"/api/outreach/report/{p.token}").status_code == 404
    assert client.get("/api/outreach/report/not-a-token").status_code == 404


def test_fill_starts_a_run(client, monkeypatch):
    from app.outreach import run

    started = []
    monkeypatch.setattr(run, "fill", lambda db, day, **k: started.append(day))
    assert client.post("/api/outreach/fill", headers=ADMIN).status_code == 202
