"""One run fills the list, best first, under the cap, and never offers a business twice."""
import json
from datetime import date, datetime, timedelta

from app.models import OutreachRun, Prospect
from app.outreach import new_token, run

DAY = date(2026, 11, 12)


def _ready(db, n, score, status="ready", dm="Hi {link}"):
    p = Prospect(token=new_token(), name=f"B{n}", city="Dubai", kind="salon", key=f"k{n}-{new_token()}",
                 score=score, status=status, dm_text=dm, report_json="{}", reasons_json="[]")
    db.add(p)
    db.commit()
    return p


def _no_search(monkeypatch):
    monkeypatch.setattr(run, "find", lambda db, city, kind, want: [])


def test_a_run_queues_the_best_first_up_to_the_daily_number(db, monkeypatch):
    _no_search(monkeypatch)
    for n in range(40):
        _ready(db, n, score=n)
    r = run.fill(db, DAY, want=30)
    queued = db.query(Prospect).filter_by(status="queued", queued_on=DAY).all()
    assert r.queued == 30 and len(queued) == 30
    assert min(p.score for p in queued) == 10


def test_found_businesses_are_read_written_and_queued(db, monkeypatch):
    made = []

    def find(db_, city, kind, want):
        p = _ready(db_, len(made), 50, status="found", dm=None)
        made.append(p)
        return [p]

    monkeypatch.setattr(run, "find", find)
    monkeypatch.setattr(run, "read", lambda db_, p: (setattr(p, "status", "ready"), p)[1])
    monkeypatch.setattr(run, "write", lambda db_, p: (setattr(p, "dm_text", "Hi {link}"), p)[1])
    r = run.fill(db, DAY, want=2)
    assert r.queued == 2 and r.found == 2


def test_a_scheduled_run_happens_once_a_day(db, monkeypatch):
    _no_search(monkeypatch)
    _ready(db, 1, 50)
    run.fill(db, DAY, want=5, scheduled=True)
    _ready(db, 2, 50)
    again = run.fill(db, DAY, want=5, scheduled=True)
    assert again.queued == 1 and db.query(Prospect).filter_by(status="ready").count() == 1


def test_pressing_fill_again_the_same_day_adds_more(db, monkeypatch):
    _no_search(monkeypatch)
    _ready(db, 1, 50)
    run.fill(db, DAY, want=5)
    _ready(db, 2, 50)
    r = run.fill(db, DAY, want=5)
    assert r.queued == 2 and db.query(OutreachRun).count() == 1


def test_a_business_already_sent_or_skipped_is_never_queued_again(db, monkeypatch):
    _no_search(monkeypatch)
    for status in ("sent", "skip", "not_interested", "replied", "removed"):
        _ready(db, status, 90, status=status)
    assert run.fill(db, DAY, want=5).queued == 0


def test_the_run_stops_at_the_cap(db, monkeypatch):
    searched = []
    monkeypatch.setattr(run, "find", lambda *a: searched.append(a) or [])
    monkeypatch.setattr(run, "can_spend", lambda db_: len(searched) < 2)
    r = run.fill(db, DAY, want=5)
    assert len(searched) == 2 and r.stopped_because == run.OUT_OF_BUDGET


def test_running_out_of_places_says_so(db, monkeypatch):
    _no_search(monkeypatch)
    assert run.fill(db, DAY, want=5).stopped_because == run.NONE_LEFT


def test_nothing_older_than_90_days_is_kept_about_a_skipped_business(db):
    old = _ready(db, 1, 10, status="not_interested")
    old.site_text, old.website, old.updated_at = "their site", "https://x.ae", datetime(2026, 1, 1)
    fresh = _ready(db, 2, 10, status="skip")
    fresh.site_text = "kept for now"
    db.commit()
    assert run.purge(db, now=datetime(2026, 1, 1) + timedelta(days=91)) == 1
    db.refresh(old)
    db.refresh(fresh)
    assert old.site_text is None and old.website is None and old.name == "B1" and old.status == "not_interested"
    assert fresh.site_text == "kept for now"
    assert json.loads(old.reasons_json or "[]") == []
