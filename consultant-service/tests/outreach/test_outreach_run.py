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
    monkeypatch.setattr(run, "learn", lambda db_, p: p)
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


def test_nothing_older_than_90_days_is_kept_about_a_skipped_business(db, monkeypatch):
    old = _ready(db, 1, 10, status="not_interested")
    old.site_text, old.website, old.updated_at = "their site", "https://x.ae", datetime(2026, 1, 1)
    fresh = _ready(db, 2, 10, status="skip")
    fresh.site_text = "kept for now"
    db.commit()
    forgotten = []
    monkeypatch.setattr(run.image, "forget", forgotten.append)
    assert run.purge(db, now=datetime(2026, 1, 1) + timedelta(days=91)) == 1
    assert forgotten == [old.token]
    db.refresh(old)
    db.refresh(fresh)
    assert old.site_text is None and old.website is None and old.name == "B1" and old.status == "not_interested"
    assert fresh.site_text == "kept for now"
    assert json.loads(old.reasons_json or "[]") == []


def test_leftovers_from_a_stopped_run_are_finished_first(db, monkeypatch):
    _no_search(monkeypatch)
    found = _ready(db, "f", 0, status="found", dm=None)
    unwritten = _ready(db, "u", 60, status="ready", dm=None)
    monkeypatch.setattr(run, "read", lambda db_, p: (setattr(p, "status", "ready"), p)[1])
    monkeypatch.setattr(run, "write", lambda db_, p: (setattr(p, "dm_text", "Hi {link}"), p)[1])
    monkeypatch.setattr(run, "learn", lambda db_, p: p)
    r = run.fill(db, DAY, want=5)
    db.refresh(found)
    db.refresh(unwritten)
    assert found.status == "queued" and unwritten.status == "queued" and r.queued == 2


def test_a_page_that_breaks_the_reader_does_not_stop_the_run(db, monkeypatch):
    calls = []

    def find(db_, city, kind, want):
        calls.append(kind)
        return [_ready(db_, f"x{len(calls)}", 50, status="found", dm=None)] if len(calls) == 1 else []

    def broken(db_, p):
        raise ValueError("bad page")

    monkeypatch.setattr(run, "find", find)
    monkeypatch.setattr(run, "read", broken)
    run.fill(db, DAY, want=2)
    assert len(calls) > 1


def test_a_search_outage_is_not_reported_as_nothing_found(db, monkeypatch):
    from app.outreach.find import SearchFailed

    def down(*a):
        raise SearchFailed("down")

    monkeypatch.setattr(run, "find", down)
    assert run.fill(db, DAY, want=5).stopped_because == run.SEARCH_DOWN


def test_each_business_is_learned_about_once_before_it_is_written(db, monkeypatch):
    order = []

    def learn(db_, p):
        order.append(("learn", p.name))
        p.sources_json = json.dumps([{"url": "", "what": run_learn.LEARNED}])
        return p

    from app.outreach import learn as run_learn

    p = _ready(db, 1, 50, dm=None)
    monkeypatch.setattr(run, "find", lambda *a: [])
    monkeypatch.setattr(run, "learn", learn)
    monkeypatch.setattr(run, "write", lambda db_, p: order.append(("write", p.name)) or p)
    run.fill(db, DAY, want=1)
    run.fill(db, DAY, want=1)
    assert order[:2] == [("learn", p.name), ("write", p.name)]
    assert order.count(("learn", p.name)) == 1

