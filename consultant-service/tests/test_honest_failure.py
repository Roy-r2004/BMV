"""Honest failure: one place where a run stops, tells the client in plain words,
emails the team, and records the facts.

The rule under all of it is that nothing the client reads is a guess or a
comfort. We say we have been told only when the email actually went out, and
the cause of a failure (which can carry a provider URL or a key fragment) goes
to the team and to the record, never to the screen.
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app import mailer
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import Request
from app.pipeline import failure
from app.pipeline.failure import STAGE_WORK, StageFailed, client_reason, fail_run, stall

REQUIRED_STAGES = [
    "reading", "researching", "analyzing", "capacity", "diagnosing", "challenging",
    "consulting", "answering", "planning", "decomposing", "shaping", "blueprint",
    "technical", "playbook", "roadmap", "quality", "screens", "email",
]
FORBIDDEN = ("try again", "Exception", "pipeline")
SECRET_CAUSE = "OpenRouter 503: sk-or-v1-SECRET"


@pytest.fixture(autouse=True)
def _fresh_stall_window():
    failure._last_stall_mail.clear()
    yield
    failure._last_stall_mail.clear()


@pytest.fixture
def outbox(monkeypatch):
    """Every email the code tries to send, as (to, subject, body). The send is
    stubbed to succeed; a test that wants the mail server down overrides it."""
    sent: list[tuple] = []

    def record(to, subject, body):
        sent.append((to, subject, body))
        return True

    monkeypatch.setattr(mailer, "send_now", record)
    return sent


def _generating_row(**fields) -> int:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        req = Request(
            business_name="Halo Reformer Studio", business_description="A pilates studio.",
            email="test@example.com", owner_email="test@example.com",
            public_id=f"halo{os.urandom(4).hex()}",
            **{"status": "new", "is_generating": True, "stage": "blueprint",
               "stage_label": "Writing your blueprint...", "progress_pct": 50, **fields},
        )
        db.add(req)
        db.commit()
        return req.id
    finally:
        db.close()


def _read(request_id: int) -> Request:
    db = SessionLocal()
    try:
        row = db.get(Request, request_id)
        db.expunge(row)
        return row
    finally:
        db.close()


def _fail(request_id: int, stage: str = "blueprint", cause: str = SECRET_CAUSE) -> bool:
    db = SessionLocal()
    try:
        return fail_run(db, request_id, stage, cause)
    finally:
        db.close()


# -- the words the client reads ------------------------------------------


def test_client_reason_claims_notification_only_when_it_happened():
    told = client_reason("blueprint", True)
    untold = client_reason("blueprint", False)
    assert told == "Our side failed while we were writing your blueprint. We have been told and are looking into it."
    assert untold == "Our side failed while we were writing your blueprint."
    assert "We have been told" in told and "We have been told" not in untold
    for text in (told, untold):
        for word in FORBIDDEN:
            assert word not in text


def test_an_unknown_stage_still_reads_plainly():
    assert client_reason("no_such_stage", False) == "Our side failed while we were working on your engagement."


def test_every_stage_the_orchestrator_emits_has_plain_words():
    assert set(REQUIRED_STAGES) <= set(STAGE_WORK)
    for stage, work in STAGE_WORK.items():
        assert work and work == work.strip() and not work.endswith("."), stage
        for notified in (True, False):
            reason = client_reason(stage, notified)
            assert reason.startswith("Our side failed while we were "), stage
            for word in FORBIDDEN:
                assert word not in reason, f"{word!r} in the copy for {stage}"


def test_stage_failed_names_its_stage_and_bounds_its_cause():
    exc = StageFailed("blueprint", "x" * 900)
    assert exc.stage == "blueprint" and len(exc.cause) == 500
    # a caught exception keeps its text; one with no text still says what it was
    assert StageFailed("planning", RuntimeError("db locked")).cause == "db locked"
    assert StageFailed("planning", TimeoutError()).cause == "TimeoutError"
    assert isinstance(exc, Exception)


# -- the mailer ------------------------------------------------------------


def test_send_now_returns_false_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "")
    assert mailer.send_now("a@b.c", "s", "b") is False
    assert mailer.send_now(None, "s", "b") is False


def test_send_now_returns_false_when_the_send_raises(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "pw")

    def refuse(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", refuse)
    assert mailer.send_now("a@b.c", "s", "b") is False


def test_notify_owner_ready_reports_whether_it_sent(monkeypatch, outbox):
    assert mailer.notify_owner_ready("abc123", "owner@example.com", "Halo") is True
    assert outbox[0][0] == "owner@example.com"
    monkeypatch.setattr(mailer, "send_now", lambda to, subject, body: False)
    assert mailer.notify_owner_ready("abc123", "owner@example.com", "Halo") is False


# -- failing a run ---------------------------------------------------------


def test_fail_run_stops_the_run_and_records_the_facts(outbox):
    request_id = _generating_row()
    public_id = _read(request_id).public_id

    assert _fail(request_id) is True

    row = _read(request_id)
    assert row.status == "failed" and row.is_failed and not row.is_generating
    assert row.stage == "failed"
    assert row.progress_pct == 50
    assert row.progress_detail == client_reason("blueprint", True)

    record = json.loads(row.failure_json)
    assert set(record) == {"stage", "at", "cause", "team_notified", "reason"}
    assert record["stage"] == "blueprint"
    assert record["cause"] == SECRET_CAUSE
    assert record["team_notified"] is True
    assert record["reason"] == client_reason("blueprint", True)
    datetime.fromisoformat(record["at"])

    # exactly one email, to the team; the cause is in its body and nowhere else
    assert len(outbox) == 1
    to, subject, body = outbox[0]
    assert to == settings.SMTP_USER
    assert subject == "Run failed: Halo Reformer Studio (blueprint)"
    assert mailer._run_url(public_id) in body and "blueprint" in body and SECRET_CAUSE in body
    assert "SECRET" not in subject
    assert "SECRET" not in row.progress_detail and "SECRET" not in row.stage_label


def test_fail_run_with_mail_down_still_fails_cleanly(monkeypatch):
    monkeypatch.setattr(mailer, "send_now", lambda to, subject, body: False)
    request_id = _generating_row()

    assert _fail(request_id) is False

    row = _read(request_id)
    assert row.status == "failed" and row.is_failed and not row.is_generating
    assert row.stage == "failed"
    assert row.progress_detail == client_reason("blueprint", False)
    assert "We have been told" not in row.progress_detail
    record = json.loads(row.failure_json)
    assert record["team_notified"] is False
    assert "We have been told" not in record["reason"]
    assert record["cause"] == SECRET_CAUSE


def test_the_run_is_already_stopped_while_the_slow_mail_is_in_flight(monkeypatch):
    """Mail can take ~20s a step. A process killed in that window must not
    leave the run "generating" for good (it holds a concurrency slot)."""
    request_id = _generating_row()
    seen = {}

    def mail_that_looks_at_the_row(to, subject, body):
        row = _read(request_id)  # a fresh session: only what has been committed
        seen.update(status=row.status, is_failed=row.is_failed, is_generating=row.is_generating,
                    stage=row.stage, detail=row.progress_detail,
                    failure=json.loads(row.failure_json) if row.failure_json else None)
        return True

    monkeypatch.setattr(mailer, "send_now", mail_that_looks_at_the_row)

    assert _fail(request_id) is True

    # when the mail was attempted: stopped, on record, and claiming nothing yet
    assert seen["status"] == "failed" and seen["is_failed"] and not seen["is_generating"]
    assert seen["stage"] == "failed"
    assert seen["detail"] == client_reason("blueprint", False)
    assert seen["failure"]["team_notified"] is False
    assert seen["failure"]["cause"] == SECRET_CAUSE
    # once it went: the wording is upgraded, in the screen and in the record
    row = _read(request_id)
    assert row.progress_detail == client_reason("blueprint", True)
    record = json.loads(row.failure_json)
    assert record["team_notified"] is True and record["reason"] == client_reason("blueprint", True)
    assert row.status == "failed" and not row.is_generating


def test_fail_run_stops_the_run_even_if_telling_the_team_blows_up(monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("mail layer bug")

    monkeypatch.setattr(mailer, "notify_team_failure", explode)
    request_id = _generating_row()

    assert _fail(request_id) is False

    row = _read(request_id)
    assert row.status == "failed" and row.is_failed and not row.is_generating
    assert row.progress_detail == client_reason("blueprint", False)
    assert json.loads(row.failure_json)["team_notified"] is False


def test_fail_run_survives_a_session_left_broken_by_the_failure(outbox):
    """The exception that stopped the run may have come from a commit; the
    session is then unusable until it is rolled back."""
    request_id = _generating_row()
    db = SessionLocal()
    try:
        db.get(Request, request_id).business_name = "x" * 10  # a pending change the failure must discard
        assert fail_run(db, request_id, "technical", "boom") is True
    finally:
        db.close()
    row = _read(request_id)
    assert row.business_name == "Halo Reformer Studio"
    assert json.loads(row.failure_json)["stage"] == "technical"


def test_fail_run_on_a_missing_row_tells_nobody(outbox):
    db = SessionLocal()
    try:
        assert fail_run(db, 987654321, "blueprint", "boom") is False
    finally:
        db.close()
    assert outbox == []


# -- stalling an endpoint --------------------------------------------------


def test_stall_is_throttled(monkeypatch, outbox):
    clock = {"now": 1000.0}
    monkeypatch.setattr(failure.time, "monotonic", lambda: clock["now"])

    assert stall("interview", business="Halo", round=3, cause="503") is True
    clock["now"] += settings.STALL_MAIL_WINDOW_SECONDS - 1
    assert stall("interview", business="Halo", round=4, cause="503") is False
    assert len(outbox) == 1
    assert outbox[0][0] == settings.SMTP_USER

    # a different kind has its own window
    assert stall("brief", business="Halo", round=None, cause="503") is True
    assert len(outbox) == 2

    clock["now"] += 2
    assert stall("interview", business="Halo", round=5, cause="503") is True
    assert len(outbox) == 3
