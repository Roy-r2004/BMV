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
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app import mailer
from app.ai.provider import AiProviderError
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import Request
from app.pipeline import failure, orchestrator
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


def test_a_run_restarted_while_the_mail_was_in_flight_is_left_alone(monkeypatch):
    """The mail takes seconds, and a failed run can be pushed back on and
    restarted in that window. The live row then belongs to the new run: the old
    failure must not write its wording over it."""
    request_id = _generating_row()

    def mail_while_the_client_restarts_the_run(to, subject, body):
        db = SessionLocal()
        try:
            row = db.get(Request, request_id)
            row.status, row.is_failed, row.is_generating = "new", False, True
            row.stage, row.stage_label = "researching", "Reading your business..."
            row.progress_detail, row.failure_json = None, None
            db.commit()
        finally:
            db.close()
        return True

    monkeypatch.setattr(mailer, "send_now", mail_while_the_client_restarts_the_run)

    assert _fail(request_id) is True  # the team was told; that stays true

    row = _read(request_id)
    assert row.status == "new" and row.is_generating and not row.is_failed
    assert row.stage == "researching" and row.stage_label == "Reading your business..."
    assert row.progress_detail is None and row.failure_json is None


def test_a_database_error_after_the_mail_cannot_lose_the_answer(monkeypatch, outbox, caplog):
    """Once the team has been told, nothing about upgrading the wording may
    raise out of `fail_run` or change what it reports."""
    real_emit = failure.emit
    calls = []

    def emit_that_fails_the_second_time(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("database is locked")
        return real_emit(*args, **kwargs)

    monkeypatch.setattr(failure, "emit", emit_that_fails_the_second_time)
    request_id = _generating_row()

    with caplog.at_level("ERROR", logger="consultant.failure"):
        assert _fail(request_id) is True

    assert len(outbox) == 1
    row = _read(request_id)
    assert row.status == "failed" and row.is_failed and not row.is_generating
    # the stop from the first phase stands, claiming nobody was told
    assert row.progress_detail == client_reason("blueprint", False)
    assert json.loads(row.failure_json)["team_notified"] is False
    assert any("could not upgrade" in r.getMessage() for r in caplog.records)


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


# -- the orchestrator ------------------------------------------------------


def _stub_blueprint(db, request_id, *args, **kwargs):
    """The one stub with a side effect: a run only ends "done" when a volume
    was written, so the stub writes one."""
    req = db.get(Request, request_id)
    req.mvp_blueprint = "## The decision\nA stub blueprint."
    db.commit()


def _nothing(*args, **kwargs):
    return None


#: Every stage entry point the orchestrator calls, in the order it calls them:
#: stage name -> (what to patch, a stub returning the least the next stage
#: needs). `integrity` has no stage of its own: it runs under the "quality" label.
HEALTHY_STAGES = {
    "researching": ("app.pipeline.research.research_business", _nothing),
    "analyzing": ("app.pipeline.analyze.analyze_business", lambda *a, **k: {"growth_opportunity": "more classes"}),
    "capacity": ("app.pipeline.capacity.read", lambda *a, **k: (None, None, None)),
    "diagnosing": ("app.pipeline.diagnose.diagnose", _nothing),
    "consulting": ("app.pipeline.decide.decide", lambda *a, **k: {"consulting_summary": "Fill the quiet hours."}),
    "answering": ("app.pipeline.answer.write", _nothing),
    "planning": ("app.pipeline.plan.plan_integration", lambda *a, **k: {"concept_name": "Halo"}),
    "decomposing": ("app.pipeline.decompose.decompose_business", lambda *a, **k: {"business_case": {}, "modules": []}),
    "shaping": ("app.pipeline.extras.build_extras", _nothing),
    "blueprint": ("app.pipeline.blueprint.write_blueprint", _stub_blueprint),
    "technical": ("app.pipeline.blueprint.write_technical_plan", _nothing),
    "playbook": ("app.pipeline.playbook.write_playbook", _nothing),
    "roadmap": ("app.pipeline.action_plan.write", _nothing),
    "quality": ("app.pipeline.qa_experts.review_quality", _nothing),
    "integrity": ("app.pipeline.integrity.enforce", _nothing),
    "screens": ("app.screens.generate.build", lambda *a, **k: 0),
}


@pytest.fixture
def pipeline_with_only(monkeypatch, outbox):
    """A factory: `pipeline_with_only("analyzing")` makes a run whose every
    stage is a healthy stub except that one, which is left real, and whose
    provider is down. `None` leaves every stage a stub: a run that works.

    Returns the new row's id and the emails the run tried to send. A test that
    needs a stage to do something particular patches it again on top."""

    def make(real: str | None) -> SimpleNamespace:
        assert real is None or real in HEALTHY_STAGES, f"no stage called {real!r}"
        for stage, (target, stub) in HEALTHY_STAGES.items():
            if stage != real:
                monkeypatch.setattr(target, stub)

        def provider_down(*args, **kwargs):
            raise AiProviderError(SECRET_CAUSE)

        monkeypatch.setattr("app.ai.provider.chat", provider_down)
        # a run that is held for a reviewer sends different mail
        monkeypatch.setattr(settings, "REVIEW_MODE", "off")
        monkeypatch.setattr(settings, "REVIEW_TOKEN", "")
        return SimpleNamespace(request_id=_generating_row(status="new", stage="new"), outbox=outbox)

    return make


def _pushed_back(request_id: int) -> None:
    """What a client pushing back does to the row: a new diagnosis, a new token."""
    db = SessionLocal()
    try:
        row = db.get(Request, request_id)
        row.status, row.phase_started_at = "new", datetime(2026, 9, 26, 10, 5, 0)
        db.commit()
    finally:
        db.close()


def test_a_stage_that_raises_stage_failed_stops_the_run(pipeline_with_only, monkeypatch):
    run = pipeline_with_only("analyzing")

    def analyze(db, request_id):
        raise StageFailed("analyzing", "boom")

    monkeypatch.setattr("app.pipeline.analyze.analyze_business", analyze)

    orchestrator.run(run.request_id)

    row = _read(run.request_id)
    assert row.status == "failed" and row.is_failed and not row.is_generating
    record = json.loads(row.failure_json)
    assert record["stage"] == "analyzing" and record["cause"] == "boom"
    assert row.progress_detail == client_reason("analyzing", True)
    assert [m[1] for m in run.outbox] == ["Run failed: Halo Reformer Studio (analyzing)"]


@pytest.mark.parametrize("entry", ["run", "run_build"])
def test_a_bare_exception_is_attributed_to_the_stage_that_was_running(pipeline_with_only, monkeypatch, entry):
    run = pipeline_with_only("blueprint")

    def write_blueprint(db, request_id, *args, **kwargs):
        raise RuntimeError("db locked")

    monkeypatch.setattr("app.pipeline.blueprint.write_blueprint", write_blueprint)

    getattr(orchestrator, entry)(run.request_id)

    row = _read(run.request_id)
    assert row.status == "failed" and not row.is_generating
    record = json.loads(row.failure_json)
    assert record["stage"] == "blueprint" and record["cause"] == "db locked"
    assert len(run.outbox) == 1


def test_a_bare_exception_from_a_session_the_failure_broke_is_still_attributed(pipeline_with_only, monkeypatch):
    """A failed flush leaves the session unusable until it is rolled back;
    reading the running stage must not trip on that. (Only the diagnosis half
    meets this: the build half rolls back before it re-raises.)"""
    run = pipeline_with_only("analyzing")
    taken = _read(run.request_id).public_id

    def analyze_business(db, request_id):
        db.add(Request(business_name="Twin", business_description="x", email="t@example.com", public_id=taken))
        db.flush()  # public_id is unique

    monkeypatch.setattr("app.pipeline.analyze.analyze_business", analyze_business)

    orchestrator.run(run.request_id)

    row = _read(run.request_id)
    assert row.status == "failed" and not row.is_generating
    assert json.loads(row.failure_json)["stage"] == "analyzing"


def test_a_failure_in_a_superseded_build_is_not_a_failure(pipeline_with_only, monkeypatch):
    """The client pushed back while the plans were being written; the failure
    belongs to a run nobody is waiting on, so nobody is told about it."""
    run = pipeline_with_only("planning")

    def plan_integration(db, request_id, consult_result):
        _pushed_back(request_id)
        raise StageFailed("planning", "boom")

    monkeypatch.setattr("app.pipeline.plan.plan_integration", plan_integration)

    orchestrator.run_build(run.request_id)

    row = _read(run.request_id)
    assert row.status == "new" and not row.is_failed
    assert row.failure_json is None
    assert run.outbox == []


def test_decomposition_that_returns_nothing_stops_the_run(pipeline_with_only, monkeypatch):
    run = pipeline_with_only("decomposing")
    later = []
    monkeypatch.setattr("app.pipeline.decompose.decompose_business", lambda *a, **k: None)
    monkeypatch.setattr("app.pipeline.extras.build_extras", lambda *a, **k: later.append("shaping"))

    orchestrator.run(run.request_id)

    row = _read(run.request_id)
    assert row.status == "failed" and not row.is_generating
    assert json.loads(row.failure_json)["stage"] == "decomposing"
    assert later == []  # nothing was written on top of an empty breakdown
    assert len(run.outbox) == 1


def test_a_capacity_read_that_reports_an_error_stops_the_run(pipeline_with_only, monkeypatch):
    run = pipeline_with_only("capacity")
    monkeypatch.setattr("app.pipeline.capacity.read", lambda *a, **k: (None, None, "boom"))

    orchestrator.run(run.request_id)

    row = _read(run.request_id)
    assert row.status == "failed"
    record = json.loads(row.failure_json)
    assert record["stage"] == "capacity" and record["cause"] == "boom"


#: One row per stage that must stop the run when its provider call fails: the
#: stage left real, and the stage the failure must name. Each later task adds
#: the rows for the stages it converts.
STAGES_THAT_STOP_THE_RUN = [
    pytest.param("capacity", "capacity", id="capacity"),
]


@pytest.mark.parametrize("real, failed_stage", STAGES_THAT_STOP_THE_RUN)
def test_a_stage_whose_provider_call_fails_stops_the_run_and_says_where(pipeline_with_only, real, failed_stage):
    run = pipeline_with_only(real)

    orchestrator.run(run.request_id)

    row = _read(run.request_id)
    assert row.status == "failed" and row.is_failed and not row.is_generating
    assert json.loads(row.failure_json)["stage"] == failed_stage
    assert row.progress_detail == client_reason(failed_stage, True)
    assert len(run.outbox) == 1
    assert run.outbox[0][1] == f"Run failed: Halo Reformer Studio ({failed_stage})"
    # the provider's own words reach the team, never a screen
    assert "SECRET" not in run.outbox[0][1]
    for shown in (row.stage_label, row.progress_detail):
        assert "SECRET" not in shown
        for word in FORBIDDEN:
            assert word not in shown


@pytest.mark.parametrize("entry", ["run", "run_build"])
def test_the_thread_ends_cleanly_when_recording_the_failure_fails_too(pipeline_with_only, monkeypatch, caplog, entry):
    """Both are entry points of a background thread: an error out of them is
    lost with the thread, so it is logged and the thread ends."""
    run = pipeline_with_only("blueprint")

    def write_blueprint(db, request_id, *args, **kwargs):
        raise RuntimeError("db locked")

    def fail_run_that_cannot_commit(*args, **kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr("app.pipeline.blueprint.write_blueprint", write_blueprint)
    monkeypatch.setattr(orchestrator, "fail_run", fail_run_that_cannot_commit)

    with caplog.at_level("ERROR", logger="consultant.orchestrator"):
        getattr(orchestrator, entry)(run.request_id)  # does not raise

    assert any("could not record" in r.getMessage() for r in caplog.records)


# -- the last thing a run does: emailing the client -------------------------


def test_an_undelivered_ready_email_alerts_the_team(pipeline_with_only, monkeypatch):
    run = pipeline_with_only(None)
    monkeypatch.setattr(mailer, "enabled", lambda: True)
    monkeypatch.setattr(mailer, "notify_owner_ready", lambda *args, **kwargs: False)

    orchestrator.run(run.request_id)

    row = _read(run.request_id)
    assert row.status == "done" and not row.is_failed and not row.is_generating  # the package exists
    assert row.stage == "done"
    assert [m[1] for m in run.outbox] == ["Run failed: Halo Reformer Studio (email)"]
    assert "was not delivered" in run.outbox[0][2]


def test_the_run_already_reads_done_while_the_mail_is_in_flight(pipeline_with_only, monkeypatch):
    """Each mail can take a long time. The row must read finished the whole
    while, and nothing may write "Done" over it afterwards: a client who pushes
    back in that window has restarted the row, and it is theirs."""
    run = pipeline_with_only(None)
    monkeypatch.setattr(mailer, "enabled", lambda: True)
    seen = []

    def mail_that_looks_at_the_row(to, subject, body):
        row = _read(run.request_id)  # a fresh session: only what has been committed
        seen.append((subject, row.status, row.stage, row.progress_pct))
        return subject.startswith("Run failed")  # the client's mail fails, the team's goes

    monkeypatch.setattr(mailer, "send_now", mail_that_looks_at_the_row)

    orchestrator.run(run.request_id)

    assert [s[0] for s in seen] == ["Halo Reformer Studio — your answer and plans are ready",
                                    "Run failed: Halo Reformer Studio (email)"]
    assert [s[1:] for s in seen] == [("done", "done", 100)] * 2


@pytest.mark.parametrize("raised_stage", ["screens", "quality"])
def test_a_stage_failed_from_the_screens_stage_keeps_its_own_words(pipeline_with_only, monkeypatch, raised_stage):
    """Wrapping is for bare exceptions; a StageFailed already says what failed."""
    run = pipeline_with_only("screens")

    def build(db, request_id):
        raise StageFailed(raised_stage, "boom")

    monkeypatch.setattr("app.screens.generate.build", build)

    orchestrator.run(run.request_id)

    record = json.loads(_read(run.request_id).failure_json)
    assert record["stage"] == raised_stage and record["cause"] == "boom"


@pytest.mark.parametrize("delivered, configured", [(True, True), (False, False)])
def test_a_ready_email_nobody_expected_alerts_nobody(pipeline_with_only, monkeypatch, delivered, configured):
    """Delivered: nothing to report. Mail not set up: the building screen never
    promised an email, so none is owed."""
    run = pipeline_with_only(None)
    monkeypatch.setattr(mailer, "enabled", lambda: configured)
    monkeypatch.setattr(mailer, "notify_owner_ready", lambda *args, **kwargs: delivered)

    orchestrator.run(run.request_id)

    assert _read(run.request_id).status == "done"
    assert run.outbox == []
