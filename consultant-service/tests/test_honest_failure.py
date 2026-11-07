"""Honest failure: one place where a run stops, tells the client in plain words,
emails the team, and records the facts.

The rule under all of it is that nothing the client reads is a guess or a
comfort. We say we have been told only when the email actually went out, and
the cause of a failure (which can carry a provider URL or a key fragment) goes
to the team and to the record, never to the screen.
"""

import json
import os
import re
import sys
import threading
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


def test_report_stall_says_the_team_is_told_while_the_window_holds_a_mail_that_went(monkeypatch, outbox):
    """`stall` says whether THIS call sent a mail. A client's sentence needs the
    other question: does the team know? Inside the window the answer is yes,
    because the mail that opened it went."""
    clock = {"now": 1000.0}
    monkeypatch.setattr(failure.time, "monotonic", lambda: clock["now"])

    assert failure.report_stall("interview", business="Halo", round=3, cause="503") is True
    clock["now"] += settings.STALL_MAIL_WINDOW_SECONDS - 1
    assert failure.report_stall("interview", business="Halo", round=4, cause="503") is True
    assert len(outbox) == 1


def test_report_stall_does_not_say_the_team_is_told_when_the_mail_did_not_go(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(failure.time, "monotonic", lambda: clock["now"])
    attempts = []

    def mail(to, subject, body):
        attempts.append(subject)
        return len(attempts) > 1  # the server is down for the first attempt only

    monkeypatch.setattr(mailer, "send_now", mail)

    assert failure.report_stall("interview", business=None, round=1, cause="503") is False
    # inside the window nobody retries, and nobody is told: the answer stays no
    clock["now"] += settings.STALL_MAIL_WINDOW_SECONDS - 1
    assert failure.report_stall("interview", business=None, round=2, cause="503") is False
    assert len(attempts) == 1
    # the next window tries again, and this time the team is told
    clock["now"] += 2
    assert failure.report_stall("interview", business=None, round=3, cause="503") is True
    assert len(attempts) == 2


def test_report_stall_does_not_claim_a_mail_that_is_still_in_flight(monkeypatch):
    """The window opens when the mail is tried, not when it lands. A request
    that arrives while the first is still on the wire cannot know the outcome."""
    during: list[bool] = []

    def slow_mail(to, subject, body):
        during.append(failure.report_stall("interview", business=None, round=2, cause="503"))
        return True

    monkeypatch.setattr(mailer, "send_now", slow_mail)

    assert failure.report_stall("interview", business=None, round=1, cause="503") is True
    assert during == [False]


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
    # a diagnosis that holds nothing: the stage either returns one or stops the run
    "diagnosing": ("app.pipeline.diagnose.diagnose", lambda *a, **k: {"hypotheses": [], "leading": None}),
    "consulting": ("app.pipeline.decide.decide", lambda *a, **k: {"consulting_summary": "Fill the quiet hours."}),
    "answering": ("app.pipeline.answer.write", _nothing),
    "planning": ("app.pipeline.plan.plan_integration", lambda *a, **k: {"concept_name": "Halo"}),
    # one module, so that the stage after it has something to shape
    "decomposing": ("app.pipeline.decompose.decompose_business",
                    lambda *a, **k: {"business_case": {}, "modules": [{"id": "booking", "name": "Booking", "purpose": "Book classes"}]}),
    "shaping": ("app.pipeline.extras.build_extras", _nothing),
    "blueprint": ("app.pipeline.blueprint.write_blueprint", _stub_blueprint),
    "technical": ("app.pipeline.blueprint.write_technical_plan", _nothing),
    "playbook": ("app.pipeline.playbook.write_playbook", _nothing),
    "roadmap": ("app.pipeline.action_plan.write", _nothing),
    "storyline": ("app.storyline.stage.write", _nothing),
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
    pytest.param("analyzing", "analyzing", id="analyzing"),
    pytest.param("consulting", "consulting", id="consulting"),
    pytest.param("planning", "planning", id="planning"),
    pytest.param("decomposing", "decomposing", id="decomposing"),
    pytest.param("shaping", "shaping", id="shaping"),
    pytest.param("blueprint", "blueprint", id="blueprint"),
    pytest.param("technical", "technical", id="technical"),
    pytest.param("playbook", "playbook", id="playbook"),
    pytest.param("roadmap", "roadmap", id="roadmap"),
    pytest.param("answering", "answering", id="answering"),
    pytest.param("screens", "screens", id="screens"),
    pytest.param("diagnosing", "diagnosing", id="diagnosing"),
]

#: What the old fallbacks wrote for every business on earth. None of it may be
#: on the row of a run whose stage failed: it would read, to the client, as our
#: finding about their business.
CANNED_ANSWERS = ("front-desk", "Front-Desk AI", "AI Analyst", "Missed inquiries")


@pytest.mark.parametrize("real, failed_stage", STAGES_THAT_STOP_THE_RUN)
def test_a_stage_whose_provider_call_fails_stops_the_run_and_says_where(pipeline_with_only, real, failed_stage):
    run = pipeline_with_only(real)

    orchestrator.run(run.request_id)

    row = _read(run.request_id)
    assert row.status == "failed" and row.is_failed and not row.is_generating
    record = json.loads(row.failure_json)
    assert record["stage"] == failed_stage
    # the provider's error is what stopped it: a row cannot pass by crashing on
    # its own inputs, which would name the same stage with a different cause
    assert "SECRET" in record["cause"]
    assert row.progress_detail == client_reason(failed_stage, True)
    assert len(run.outbox) == 1
    assert run.outbox[0][1] == f"Run failed: Halo Reformer Studio ({failed_stage})"
    # the provider's own words reach the team, never a screen
    assert "SECRET" not in run.outbox[0][1]
    for shown in (row.stage_label, row.progress_detail):
        assert "SECRET" not in shown
        for word in FORBIDDEN:
            assert word not in shown
    # and no canned answer stands in for the work that was not done
    for column in (row.business_analysis_json, row.consulting_recommendations_json, row.roles_json):
        for canned in CANNED_ANSWERS:
            assert canned.lower() not in (column or "").lower(), f"{canned!r} was written to the row"


def _provider_is_down(monkeypatch) -> None:
    def provider_down(*args, **kwargs):
        raise AiProviderError(SECRET_CAUSE)

    monkeypatch.setattr("app.ai.provider.chat", provider_down)


def _model_replies(monkeypatch, reply: dict) -> None:
    body = {"choices": [{"message": {"content": json.dumps(reply)}}], "usage": {}}
    monkeypatch.setattr("app.ai.provider.chat", lambda *args, **kwargs: body)


def _plan(request_id: int) -> dict:
    from app.pipeline import plan

    db = SessionLocal()
    try:
        return plan.plan_integration(db, request_id, {"consulting_summary": "Fill the quiet hours."})
    finally:
        db.close()


@pytest.mark.parametrize("roles", [
    pytest.param([], id="an empty list"),
    pytest.param(None, id="null"),
    pytest.param("customer_view", id="a string"),
    pytest.param([None, "owner", {}], id="entries that are not roles"),
])
def test_a_plan_that_answers_with_no_roles_stops_the_run(pipeline_with_only, monkeypatch, roles):
    """The call worked and the reply is valid JSON, but it plans nothing. The
    old code filled in two generic roles (one a "front-desk AI") and a colour
    taken from a hash of the business name, and the client's screens were drawn
    from them. A plan with no roles is no plan."""
    run = pipeline_with_only("planning")
    _model_replies(monkeypatch, {
        "concept_name": "Halo",
        "roles": roles,
        "visual_theme": {"primary_color": "#112233", "secondary_color": "#445566",
                         "background_color": "#ffffff", "style": "calm", "mood": "warm"},
    })

    orchestrator.run(run.request_id)

    row = _read(run.request_id)
    assert row.status == "failed" and row.is_failed and not row.is_generating
    record = json.loads(row.failure_json)
    assert record["stage"] == "planning" and record["cause"] == "the plan returned no roles"
    assert row.progress_detail == client_reason("planning", True)
    assert [m[1] for m in run.outbox] == ["Run failed: Halo Reformer Studio (planning)"]
    # nothing was written for the screens to be drawn from
    assert row.roles_json is None and row.visual_theme_json is None and row.concept_name is None


def test_a_plan_with_more_roles_than_the_cap_is_cut_to_the_cap(monkeypatch):
    cap = settings.MAX_ROLES_PER_REQUEST
    _model_replies(monkeypatch, {
        "concept_name": "Halo",
        "roles": [{"id": f"role_{i}", "label": f"Role {i}"} for i in range(cap + 2)],
        "visual_theme": {"primary_color": "#112233"},
    })
    request_id = _generating_row()

    result = _plan(request_id)

    assert [r["id"] for r in result["roles"]] == [f"role_{i}" for i in range(cap)]
    assert len(json.loads(_read(request_id).roles_json)) == cap


def test_a_plan_without_brand_colours_is_not_given_a_guessed_one(monkeypatch):
    """`phase2_bridge.palette` tells the build "our brand colour is ..." from
    this row, and says it never guesses a hex. A colour made from a hash of the
    business name would be exactly that guess, so a missing colour stays missing."""
    from app.pipeline import phase2_bridge

    _model_replies(monkeypatch, {
        "concept_name": "Halo",
        "roles": [{"id": "customer_view", "label": "Customer View"}],
        "visual_theme": {"style": "calm"},
    })
    request_id = _generating_row()

    _plan(request_id)

    row = _read(request_id)
    assert json.loads(row.visual_theme_json) == {"style": "calm"}
    assert phase2_bridge.palette(row) == {}


def _decide(request_id: int) -> dict:
    from app.pipeline import decide

    db = SessionLocal()
    try:
        return decide.decide(db, request_id, {"business_model": "classes"})
    finally:
        db.close()


@pytest.mark.parametrize("said", [
    pytest.param({}, id="nothing"),
    pytest.param({"confidence": None}, id="null"),
    pytest.param({"confidence": "certain"}, id="a word that is not high, medium or low"),
])
def test_decide_does_not_default_a_confidence(monkeypatch, said):
    """A confidence nobody stated is not "medium": a made-up middle reads as the
    model having weighed it. The key is dropped; whoever shows it shows nothing."""
    _model_replies(monkeypatch, {"intervention_kind": "software", "consulting_summary": "Fill the quiet hours.", **said})
    request_id = _generating_row()

    result = _decide(request_id)

    assert result.get("confidence") is None
    assert "confidence" not in json.loads(_read(request_id).consulting_recommendations_json)


@pytest.mark.parametrize("stated", ["high", "medium", "low"])
def test_decide_keeps_a_confidence_the_model_stated(monkeypatch, stated):
    _model_replies(monkeypatch, {"intervention_kind": "software", "confidence": stated})
    request_id = _generating_row()

    assert _decide(request_id)["confidence"] == stated


# -- the document stages ---------------------------------------------------


def _ledger(request_id: int) -> list[tuple[str, bool]]:
    """What the cost ledger holds for a run: (purpose, success), oldest first."""
    from app.models import AiUsageEvent

    db = SessionLocal()
    try:
        rows = db.query(AiUsageEvent).filter(AiUsageEvent.request_id == request_id).order_by(AiUsageEvent.id)
        return [(e.purpose, e.success) for e in rows]
    finally:
        db.close()


def _provider_by_template(monkeypatch, stage_module, replies: dict) -> None:
    """For a stage that renders several templates: the provider answers each
    prompt from the template it was rendered from. A reply is the dict to
    answer with, an exception to raise, or a function of the prompt that
    returns either; a str reply is sent as it is, not as JSON."""
    rendered: dict[str, str] = {}
    real_render = stage_module.render

    def render_and_remember(name, **context):
        text = real_render(name, **context)
        rendered[text] = name
        return text

    def chat(model, messages, **kwargs):
        prompt = messages[0]["content"]
        reply = replies[rendered[prompt]]
        if callable(reply):
            reply = reply(prompt)
        if isinstance(reply, BaseException):
            raise reply
        content = reply if isinstance(reply, str) else json.dumps(reply)
        return {"choices": [{"message": {"content": content}}], "usage": {}}

    monkeypatch.setattr(stage_module, "render", render_and_remember)
    monkeypatch.setattr("app.ai.provider.chat", chat)


def _decompose(request_id: int) -> dict:
    from app.pipeline import decompose

    db = SessionLocal()
    try:
        return decompose.decompose_business(
            db, request_id, {"business_model": "classes"}, {"consulting_summary": "Fill the quiet hours."},
            {"concept_name": "Halo"})
    finally:
        db.close()


TWO_MODULES = {"modules": [{"id": "m0", "name": "Module 0", "purpose": "Book classes"},
                           {"id": "m1", "name": "Module 1", "purpose": "Take payment"}], "business_case": {}}


def test_one_module_spec_failing_stops_decomposition(monkeypatch):
    from app.pipeline import decompose

    def spec(prompt):
        return AiProviderError(SECRET_CAUSE) if "Name: Module 1\n" in prompt else {"features": []}

    _provider_by_template(monkeypatch, decompose, {
        "decompose.j2": TWO_MODULES, "module_spec.j2": spec, "tech_spec.j2": {"data_model": []}})
    request_id = _generating_row()

    with pytest.raises(StageFailed) as stopped:
        _decompose(request_id)

    assert stopped.value.stage == "decomposing" and SECRET_CAUSE in stopped.value.cause
    assert "Module 1" in stopped.value.cause
    # both calls are on the cost ledger, the failed one as failed; the
    # engineering specs, which are written from these, were never paid for
    assert _ledger(request_id) == [("decompose", True), ("module_spec", True), ("module_spec", False)]


def test_one_module_tech_spec_failing_stops_decomposition(monkeypatch):
    from app.pipeline import decompose

    def tech(prompt):
        return AiProviderError(SECRET_CAUSE) if "Name: Module 0\n" in prompt else {"data_model": []}

    _provider_by_template(monkeypatch, decompose, {
        "decompose.j2": TWO_MODULES, "module_spec.j2": {"features": []}, "tech_spec.j2": tech})
    request_id = _generating_row()

    with pytest.raises(StageFailed) as stopped:
        _decompose(request_id)

    assert stopped.value.stage == "decomposing" and "Module 0" in stopped.value.cause
    assert sorted(_ledger(request_id)) == sorted([
        ("decompose", True), ("module_spec", True), ("module_spec", True), ("tech_spec", True), ("tech_spec", False)])


def test_a_failed_decomposition_call_is_on_the_ledger_and_stops_the_stage(monkeypatch):
    from app.pipeline import decompose

    _provider_by_template(monkeypatch, decompose, {"decompose.j2": AiProviderError(SECRET_CAUSE)})
    request_id = _generating_row()

    with pytest.raises(StageFailed) as stopped:
        _decompose(request_id)

    assert stopped.value.stage == "decomposing" and stopped.value.cause == SECRET_CAUSE
    assert _ledger(request_id) == [("decompose", False)]


def test_a_decomposition_with_no_modules_stops_the_run(pipeline_with_only, monkeypatch):
    """The call worked and the reply is valid, but it breaks the business into
    nothing; every volume after it is written from the breakdown."""
    run = pipeline_with_only("decomposing")
    later = []
    _model_replies(monkeypatch, {"modules": [], "business_case": {}})
    monkeypatch.setattr("app.pipeline.extras.build_extras", lambda *a, **k: later.append("shaping"))

    orchestrator.run(run.request_id)

    row = _read(run.request_id)
    assert row.status == "failed" and not row.is_generating
    assert json.loads(row.failure_json)["stage"] == "decomposing"
    assert later == []  # nothing was written on top of an empty breakdown
    assert len(run.outbox) == 1
    assert row.modules_json is None


SHAPING_LAYERS = {
    "journey.j2": {"stages": [{"stage": "Find a class", "backstage_modules": []}]},
    "governance.j2": {"scoreboard": [{"metric": "Fill rate"}], "risks": [{"risk": "No-shows"}]},
    "organization.j2": {"roles": [{"role": "Owner"}]},
    "checklists.j2": {"checklists": [{"name": "Opening", "items": ["Unlock"]}]},
    "procedures.j2": {"procedures": [{"name": "Booking", "steps": [{"step": "Take the name"}]}]},
}


def _shape(request_id: int, **kwargs) -> None:
    from app.pipeline import extras

    db = SessionLocal()
    try:
        extras.build_extras(db, request_id, {"target_customer_profile": "", "pain_points": []},
                            {"modules": TWO_MODULES["modules"][:1], "business_case": {}}, **kwargs)
    finally:
        db.close()


def test_a_shaping_layer_that_fails_stops_the_run_after_its_usage_is_logged(monkeypatch):
    from app.pipeline import extras

    _provider_by_template(monkeypatch, extras, {
        **SHAPING_LAYERS, "checklists.j2": AiProviderError(SECRET_CAUSE), "journey.j2": AiProviderError("journey boom")})
    request_id = _generating_row()

    with pytest.raises(StageFailed) as stopped:
        _shape(request_id)

    assert stopped.value.stage == "shaping"
    assert "journey boom" in stopped.value.cause  # the first layer to fail, in the order they are asked
    ledger = dict(_ledger(request_id))
    assert ledger["journey"] is False and ledger["checklists"] is False
    assert ledger["governance"] is True and ledger["procedures"] is True
    # a failed run is not left with half its layers
    row = _read(request_id)
    assert row.journey_json is None and row.scoreboard_json is None and row.org_json is None


def test_a_partial_rebuild_of_one_layer_that_fails_stops_the_run_too(monkeypatch):
    from app.pipeline import extras

    _provider_by_template(monkeypatch, extras, {**SHAPING_LAYERS, "journey.j2": AiProviderError(SECRET_CAUSE)})
    request_id = _generating_row()

    with pytest.raises(StageFailed) as stopped:
        _shape(request_id, only={"journey"})

    assert stopped.value.stage == "shaping" and SECRET_CAUSE in stopped.value.cause
    assert _ledger(request_id) == [("journey", False)]


def test_shaping_that_works_still_saves_every_layer(monkeypatch):
    from app.pipeline import extras

    _provider_by_template(monkeypatch, extras, SHAPING_LAYERS)
    request_id = _generating_row()

    _shape(request_id)

    row = _read(request_id)
    assert row.journey_json and row.scoreboard_json and row.org_json and row.checklists_json and row.procedures_json


def _model_replies_text(monkeypatch, text: str) -> None:
    body = {"choices": [{"message": {"content": text}}], "usage": {}}
    monkeypatch.setattr("app.ai.provider.chat", lambda *args, **kwargs: body)


def test_a_document_call_that_fails_is_a_stage_failure_with_its_ledger_row(monkeypatch):
    from app.pipeline import blueprint

    _provider_is_down(monkeypatch)
    request_id = _generating_row()
    db = SessionLocal()
    try:
        with pytest.raises(StageFailed) as stopped:
            blueprint._markdown_call(db, request_id, "technical_plan", "write it", stage="technical")
    finally:
        db.close()

    assert stopped.value.stage == "technical" and stopped.value.cause == SECRET_CAUSE
    assert _ledger(request_id) == [("technical_plan", False)]


def test_a_document_that_comes_back_empty_is_a_stage_failure(monkeypatch):
    from app.pipeline import blueprint

    _model_replies_text(monkeypatch, "   ")
    request_id = _generating_row()
    db = SessionLocal()
    try:
        with pytest.raises(StageFailed) as stopped:
            blueprint._markdown_call(db, request_id, "blueprint", "write it", stage="blueprint")
    finally:
        db.close()

    assert stopped.value.stage == "blueprint" and "empty" in stopped.value.cause


def test_a_volume_already_written_is_kept_when_its_rewrite_comes_back_empty(monkeypatch):
    """The writers save whatever `_markdown_call` returns, with no guard of
    their own: an empty reply must have stopped the run before that line."""
    from app.pipeline import blueprint

    kept = {"mvp_blueprint": "## The decision\nkept\n", "technical_plan": "## How it works\nkept\n"}
    plan = {"concept_name": "C", "roles": []}
    _model_replies_text(monkeypatch, "   ")
    request_id = _generating_row(**kept)
    db = SessionLocal()
    try:
        with pytest.raises(StageFailed) as blueprint_stop:
            blueprint.write_blueprint(db, request_id, {}, {}, plan)
        with pytest.raises(StageFailed) as technical_stop:
            blueprint.write_technical_plan(db, request_id, {}, plan)
    finally:
        db.close()

    assert (blueprint_stop.value.stage, technical_stop.value.stage) == ("blueprint", "technical")
    row = _read(request_id)
    assert (row.mvp_blueprint, row.technical_plan) == (kept["mvp_blueprint"], kept["technical_plan"])


def test_a_volume_that_is_rewritten_replaces_the_one_before_and_is_returned(monkeypatch):
    from app.pipeline import blueprint

    plan = {"concept_name": "C", "roles": []}
    _model_replies_text(monkeypatch, "## The decision\nnew\n")
    request_id = _generating_row(mvp_blueprint="## The decision\nold\n", technical_plan="## How it works\nold\n")
    db = SessionLocal()
    try:
        assert blueprint.write_blueprint(db, request_id, {}, {}, plan) == "## The decision\nnew"
        assert blueprint.write_technical_plan(db, request_id, {}, plan) == "## The decision\nnew"
    finally:
        db.close()

    row = _read(request_id)
    assert row.mvp_blueprint == "## The decision\nnew" and row.technical_plan == "## The decision\nnew"


def test_a_document_that_works_is_returned_with_its_fence_stripped(monkeypatch):
    from app.pipeline import blueprint

    _model_replies_text(monkeypatch, "```markdown\n## The decision\nGo.\n```")
    request_id = _generating_row()
    db = SessionLocal()
    try:
        assert blueprint._markdown_call(db, request_id, "blueprint", "write it", stage="blueprint") == "## The decision\nGo."
    finally:
        db.close()
    assert _ledger(request_id) == [("blueprint", True)]


def test_a_playbook_with_no_valid_steps_stops_the_run(pipeline_with_only, monkeypatch):
    run = pipeline_with_only("playbook")
    _model_replies(monkeypatch, {"steps": [{"title": "Missing its phase and its owner"}]})

    orchestrator.run(run.request_id)

    row = _read(run.request_id)
    assert row.status == "failed" and not row.is_generating
    record = json.loads(row.failure_json)
    assert record["stage"] == "playbook" and "no valid steps" in record["cause"]
    assert row.playbook_json is None
    assert len(run.outbox) == 1


def _write_roadmap(request_id: int):
    from app.pipeline import action_plan

    db = SessionLocal()
    try:
        return action_plan.write(db, request_id)
    finally:
        db.close()


@pytest.mark.parametrize("breakdown", ["the model is down", "the inputs cannot be read", "no roadmap is usable"])
def test_a_roadmap_that_cannot_be_written_saves_its_failed_state_and_raises(monkeypatch, breakdown):
    from app.pipeline import action_plan

    if breakdown == "the model is down":
        _provider_is_down(monkeypatch)
    elif breakdown == "the inputs cannot be read":
        def unreadable(req):
            raise ValueError("modules_json is not json")

        monkeypatch.setattr(action_plan, "_modules", unreadable)
    else:
        _model_replies(monkeypatch, {"summary": "x", "phases": [], "decisions": []})
    request_id = _generating_row(status="done", is_generating=False)

    with pytest.raises(StageFailed) as stopped:
        _write_roadmap(request_id)

    assert stopped.value.stage == "roadmap"
    # what the roadmap page reads: failed, with its retry, not "writing" for good
    assert json.loads(_read(request_id).action_plan_json) == {"status": "failed"}
    ledger = _ledger(request_id)
    if breakdown == "the model is down":
        assert ledger == [("roadmap:1", False)] and SECRET_CAUSE in stopped.value.cause
    elif breakdown == "no roadmap is usable":
        assert ledger == [("roadmap:1", True), ("roadmap:2", True)]
    else:
        assert ledger == [] and "modules_json" in stopped.value.cause


def test_a_roadmap_written_outside_a_run_tells_the_team_and_keeps_the_failed_state(monkeypatch, outbox):
    """The owner can ask for a roadmap again from the page; that thread is not
    the orchestrator, so nothing else would tell the team it failed."""
    from app.pipeline import action_plan

    _provider_is_down(monkeypatch)
    request_id = _generating_row(status="done", is_generating=False)

    action_plan.write_in_background(request_id)  # a thread entry: it does not raise

    row = _read(request_id)
    assert json.loads(row.action_plan_json) == {"status": "failed"}
    assert row.status == "done" and not row.is_failed  # the delivered package is still delivered
    assert [m[1] for m in outbox] == ["Run failed: Halo Reformer Studio (roadmap)"]
    assert SECRET_CAUSE in outbox[0][2] and row.public_id in outbox[0][2]


def test_a_roadmap_thread_ends_cleanly_when_the_team_cannot_be_told(monkeypatch):
    from app.pipeline import action_plan

    def mail_layer_bug(*args, **kwargs):
        raise RuntimeError("mail layer bug")

    _provider_is_down(monkeypatch)
    monkeypatch.setattr(mailer, "notify_team_failure", mail_layer_bug)
    request_id = _generating_row(status="done", is_generating=False)

    action_plan.write_in_background(request_id)

    assert json.loads(_read(request_id).action_plan_json) == {"status": "failed"}


def _write_answer(request_id: int, decision: dict | None = None) -> dict:
    from app.pipeline import answer

    db = SessionLocal()
    try:
        return answer.write(db, request_id, decision if decision is not None else {"consulting_summary": "Fill the quiet hours."})
    finally:
        db.close()


@pytest.mark.parametrize("breakdown", ["the model is down", "the inputs cannot be read", "no answer is usable"])
def test_an_answer_that_cannot_be_written_stops_the_stage(monkeypatch, breakdown):
    from app.pipeline import diagnose

    if breakdown == "the model is down":
        _provider_is_down(monkeypatch)
    elif breakdown == "the inputs cannot be read":
        def unreadable(req):
            raise ValueError("evidence is not json")

        monkeypatch.setattr(diagnose, "_evidence_lines", unreadable)
    else:
        _model_replies(monkeypatch, {"turn": "A reply with no headline"})
    request_id = _generating_row(answer_json=json.dumps({"headline": "From the last diagnosis"}))

    with pytest.raises(StageFailed) as stopped:
        _write_answer(request_id)

    assert stopped.value.stage == "answering"
    # the last diagnosis's answer does not stand in for this one
    assert _read(request_id).answer_json is None
    ledger = _ledger(request_id)
    if breakdown == "the model is down":
        assert ledger == [("answer:1", False)] and SECRET_CAUSE in stopped.value.cause
    elif breakdown == "no answer is usable":
        assert ledger == [("answer:1", True), ("answer:2", True)] and "no headline" in stopped.value.cause
    else:
        assert ledger == [] and "evidence" in stopped.value.cause


def test_an_answer_whose_retry_fails_keeps_the_candidate_it_has(monkeypatch):
    """The answer failed only at the margin: attempt one gave a headline, with a
    complaint about the move; attempt two could not be asked. That is an answer."""
    replies = iter([{"headline": "You're full.", "turn": "Evenings.", "sub": "Six classes.", "move": {"label": "bogus"}},
                    AiProviderError(SECRET_CAUSE)])

    def chat(*args, **kwargs):
        reply = next(replies)
        if isinstance(reply, BaseException):
            raise reply
        return {"choices": [{"message": {"content": json.dumps(reply)}}], "usage": {}}

    monkeypatch.setattr("app.ai.provider.chat", chat)
    request_id = _generating_row()

    result = _write_answer(request_id)

    assert result["headline"] == "You're full."
    assert json.loads(_read(request_id).answer_json)["headline"] == "You're full."


@pytest.mark.parametrize("said", [
    pytest.param({}, id="nothing"),
    pytest.param({"confidence": None}, id="null"),
    pytest.param({"confidence": ""}, id="empty"),
])
def test_the_answer_prompt_states_no_confidence_nobody_stated(monkeypatch, said):
    prompts = []

    def chat(model, messages, **kwargs):
        prompts.append(messages[0]["content"])
        return {"choices": [{"message": {"content": json.dumps({"headline": "You're full."})}}], "usage": {}}

    monkeypatch.setattr("app.ai.provider.chat", chat)
    request_id = _generating_row()

    _write_answer(request_id, {"consulting_summary": "Fill the quiet hours.", **said})

    assert "Confidence" not in prompts[0] and "medium" not in prompts[0].lower()


def test_the_answer_prompt_carries_a_confidence_the_model_stated(monkeypatch):
    prompts = []

    def chat(model, messages, **kwargs):
        prompts.append(messages[0]["content"])
        return {"choices": [{"message": {"content": json.dumps({"headline": "You're full."})}}], "usage": {}}

    monkeypatch.setattr("app.ai.provider.chat", chat)
    request_id = _generating_row()

    _write_answer(request_id, {"consulting_summary": "Fill the quiet hours.", "confidence": "low"})

    assert "Confidence: low" in prompts[0]


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


# -- the diagnosis -----------------------------------------------------------


EXPLANATIONS = ("Evenings are full", "Mornings are empty", "Prices are too low")


def _explanations(*statements: str) -> dict:
    """What the diagnostician answers: one explanation per statement."""
    return {"hypotheses": [
        {"id": f"H{i}", "statement": statement, "area": "capacity", "software_can_fix": True,
         "would_support": "a full week", "would_refute": "an empty week", "cites": [], "from_owner": False}
        for i, statement in enumerate(statements, start=1)]}


def _diagnose(request_id: int) -> dict:
    from app.pipeline import diagnose

    db = SessionLocal()
    try:
        return diagnose.diagnose(db, request_id, {"business_model": "classes"})
    finally:
        db.close()


def _earlier_diagnosis() -> str:
    return json.dumps({"leading": "H1", "hypotheses": [
        {"id": "H1", "statement": "From the last diagnosis", "test": {"verdict": "supported"}}]})


def test_a_diagnosis_call_that_fails_stops_the_stage_with_its_ledger_row(monkeypatch):
    from app.pipeline import diagnose

    _provider_by_template(monkeypatch, diagnose, {"diagnose.j2": AiProviderError(SECRET_CAUSE)})
    request_id = _generating_row(diagnosis_json=_earlier_diagnosis())

    with pytest.raises(StageFailed) as stopped:
        _diagnose(request_id)

    assert stopped.value.stage == "diagnosing" and stopped.value.cause == SECRET_CAUSE
    assert _ledger(request_id) == [("diagnose:1", False)]
    # the last diagnosis does not stand in for this one
    assert _read(request_id).diagnosis_json is None


def test_a_diagnosis_that_is_not_json_is_a_failed_call(monkeypatch):
    _model_replies_text(monkeypatch, "I could not settle on an explanation.")
    request_id = _generating_row(diagnosis_json=_earlier_diagnosis())

    with pytest.raises(StageFailed) as stopped:
        _diagnose(request_id)

    assert stopped.value.stage == "diagnosing" and "No JSON object found" in stopped.value.cause
    # asked once more (STAGE_REPLY_ATTEMPTS), and neither reply could be read
    assert _ledger(request_id) == [("diagnose:1", False)] * settings.STAGE_REPLY_ATTEMPTS
    assert _read(request_id).diagnosis_json is None


@pytest.mark.parametrize("reply", [
    pytest.param({"hypotheses": []}, id="none"),
    pytest.param(_explanations("Only one"), id="one"),
    pytest.param({"hypotheses": ["a string", {"statement": "  "}, {"area": "capacity"}]}, id="entries that are not explanations"),
    pytest.param({"turn": "no hypotheses at all"}, id="no hypotheses key"),
])
def test_a_diagnosis_with_fewer_than_two_usable_explanations_stops_the_stage(monkeypatch, reply):
    """One explanation is an opinion, not a diagnosis, and the analysis it used
    to fall back to is not a replacement for the work that was asked for."""
    from app.pipeline import diagnose

    _provider_by_template(monkeypatch, diagnose, {"diagnose.j2": reply})
    request_id = _generating_row(diagnosis_json=_earlier_diagnosis())

    with pytest.raises(StageFailed) as stopped:
        _diagnose(request_id)

    assert stopped.value.stage == "diagnosing"
    assert "usable explanation" in stopped.value.cause and "needs 2" in stopped.value.cause
    # the calls worked, their answers did not: each is asked again, then the stage stops
    assert _ledger(request_id) == [("diagnose:1", False)] * settings.STAGE_REPLY_ATTEMPTS
    assert _read(request_id).diagnosis_json is None


def test_a_second_look_that_cannot_be_made_stops_the_stage(monkeypatch):
    """Both reviewers killed the first reading, so it is not what the client is
    owed. Thinking again was the way out of that; if it cannot be done, the
    refuted reading does not ship in its place."""
    from app.pipeline import diagnose

    asked = []

    def diagnostician(prompt):
        asked.append(prompt)
        return _explanations(*EXPLANATIONS) if len(asked) == 1 else AiProviderError(SECRET_CAUSE)

    _provider_by_template(monkeypatch, diagnose, {
        "diagnose.j2": diagnostician,
        "test_hypothesis.j2": {"verdict": "supported", "because": "The evenings are full.", "cites": []},
        "challenge.j2": {"kills": True, "because": "The owner said so.", "weakness": "Only the owner's word"}})
    request_id = _generating_row(diagnosis_json=_earlier_diagnosis())

    with pytest.raises(StageFailed) as stopped:
        _diagnose(request_id)

    assert stopped.value.stage == "diagnosing" and stopped.value.cause == SECRET_CAUSE
    assert _ledger(request_id) == [
        ("diagnose:1", True), *[("test_hypothesis", True)] * 3,
        ("challenge:alternative", True), ("challenge:confirmation", True), ("diagnose:2", False)]
    assert _read(request_id).diagnosis_json is None


def test_every_hypothesis_test_crashing_stops_the_run(pipeline_with_only, monkeypatch):
    """Nothing was tested against their figures, so there is nothing to attack
    and nothing to conclude. Passing the explanations on untested would present
    a list of guesses as a diagnosis."""
    from app.pipeline import diagnose

    run = pipeline_with_only("diagnosing")
    later = []
    _provider_by_template(monkeypatch, diagnose, {
        "diagnose.j2": _explanations(*EXPLANATIONS), "test_hypothesis.j2": AiProviderError(SECRET_CAUSE)})
    monkeypatch.setattr("app.pipeline.decide.decide", lambda *a, **k: later.append("consulting"))
    # a pushed-back run: the row still holds the diagnosis of the round before
    db = SessionLocal()
    try:
        db.get(Request, run.request_id).diagnosis_json = _earlier_diagnosis()
        db.commit()
    finally:
        db.close()

    orchestrator.run(run.request_id)

    row = _read(run.request_id)
    assert row.status == "failed" and row.is_failed and not row.is_generating
    record = json.loads(row.failure_json)
    assert record["stage"] == "diagnosing"
    assert "none of the 3 explanations could be tested" in record["cause"] and SECRET_CAUSE in record["cause"]
    assert row.progress_detail == client_reason("diagnosing", True)
    assert later == [] and row.diagnosis_json is None
    # every test is on the ledger as failed, and the reviewers were never paid for
    assert _ledger(run.request_id) == [("diagnose:1", True), *[("test_hypothesis", False)] * 3]
    assert [m[1] for m in run.outbox] == ["Run failed: Halo Reformer Studio (diagnosing)"]


def test_tests_that_all_honestly_come_back_untestable_do_not_stop_the_run(monkeypatch):
    """The opposite of a crash: every test ran, and the figures could not settle
    any explanation. That is a real answer, and a live run once produced exactly
    this. Reading it as a failure would end engagements that did their work."""
    from app.pipeline import diagnose

    _provider_by_template(monkeypatch, diagnose, {
        "diagnose.j2": _explanations(*EXPLANATIONS),
        "test_hypothesis.j2": {"verdict": "untestable", "because": "Nothing they gave bears on it.",
                               "cites": [], "would_need": "Their booking export"},
        "challenge.j2": {"kills": False, "because": "It held.", "weakness": ""}})
    request_id = _generating_row()

    result = _diagnose(request_id)

    assert len(result["hypotheses"]) == 3
    for h in result["hypotheses"]:
        assert h["test"]["verdict"] == "untestable" and not h["test"].get("not_tested")
    assert result["status"] == "survived"
    assert _ledger(request_id) == [
        ("diagnose:1", True), *[("test_hypothesis", True)] * 3,
        ("challenge:alternative", True), ("challenge:confirmation", True)]


def _one_test_crashes(monkeypatch) -> int:
    """A diagnosis in which the test of "Mornings are empty" crashes on our
    side and the rest run. Returns the row it was made for."""
    from app.pipeline import diagnose

    def hypothesis_test(prompt):
        if "Mornings are empty" in prompt:
            return AiProviderError(SECRET_CAUSE)
        return {"verdict": "supported", "because": "The evenings are full.", "cites": []}

    _provider_by_template(monkeypatch, diagnose, {
        "diagnose.j2": _explanations(*EXPLANATIONS), "test_hypothesis.j2": hypothesis_test,
        "challenge.j2": {"kills": False, "because": "It held.", "weakness": ""}})
    return _generating_row()


def test_one_crashed_test_is_marked_not_tested_and_the_diagnosis_continues(monkeypatch):
    request_id = _one_test_crashes(monkeypatch)

    result = _diagnose(request_id)

    tests = {h["statement"]: h["test"] for h in result["hypotheses"]}
    crashed = tests["Mornings are empty"]
    assert crashed["not_tested"] is True
    assert crashed["verdict"] == "untestable" and crashed["because"] == "" and crashed["cites"] == []
    for statement in ("Evenings are full", "Prices are too low"):
        assert not tests[statement].get("not_tested") and tests[statement]["verdict"] == "supported"
    # a test that never ran does not lead over two that did, and the reviewers still ran
    leading = next(h for h in result["hypotheses"] if h["id"] == result["leading"])
    assert leading["statement"] == "Evenings are full"
    assert result["status"] == "survived"
    # the crash is on the ledger as failed, with its cause
    from app.models import AiUsageEvent

    db = SessionLocal()
    try:
        failed = db.query(AiUsageEvent).filter(
            AiUsageEvent.request_id == request_id, AiUsageEvent.success.is_(False)).all()
        assert [(e.purpose, e.error) for e in failed] == [("test_hypothesis", SECRET_CAUSE)]
    finally:
        db.close()


def test_not_tested_reaches_the_narrated_trail(monkeypatch):
    from app.routers import requests as requests_router

    request_id = _one_test_crashes(monkeypatch)

    _diagnose(request_id)

    verdicts = [(t["text"], t["not_tested"]) for t in requests_router._thinking(_read(request_id))
                if t["kind"] == "verdict"]
    assert verdicts == [("Evenings are full", False), ("Mornings are empty", True), ("Prices are too low", False)]
    for line in requests_router._thinking(_read(request_id)):
        assert "SECRET" not in json.dumps(line)  # the provider's words stay off the client's screen


def test_a_hypothesis_that_was_never_tested_ranks_between_refuted_and_inconclusive():
    from app.pipeline.diagnose import _rank

    inconclusive = {"from_owner": False, "test": {"verdict": "untestable"}}
    never_tested = {"from_owner": False, "test": {"verdict": "untestable", "not_tested": True}}
    refuted = {"from_owner": False, "test": {"verdict": "refuted"}}
    assert _rank(refuted) < _rank(never_tested) < _rank(inconclusive)


def test_the_decision_payload_carries_not_tested():
    from app.routers.requests import _diagnosis_payload

    def hypothesis(i, **test):
        return {"id": f"H{i}", "statement": f"Explanation {i}", "area": "capacity", "software_can_fix": True,
                "test": {"verdict": "untestable", "because": "", "cites": [], "would_need": "", **test}}

    diagnosis = {"leading": "H1", "status": "survived", "weaknesses": [], "challenges": [], "evidence": [],
                 "hypotheses": [hypothesis(1, not_tested=True), hypothesis(2),
                                hypothesis(3, not_tested=True)]}

    payload = _diagnosis_payload(SimpleNamespace(diagnosis_json=json.dumps(diagnosis)))

    assert payload["leading"]["not_tested"] is True
    assert [c["not_tested"] for c in payload["considered"]] == [False, True]


def _diagnosis_with_a_test_that_never_ran(**hypothesis) -> str:
    return json.dumps({"leading": "H1", "status": "survived", "hypotheses": [
        {"id": "H1", "statement": "Evenings are full",
         "test": {"verdict": "supported", "because": "Six full evenings a week.", "cites": []}},
        {"id": "H2", "statement": "Prices are too low", **hypothesis,
         "test": {"verdict": "untestable", "because": "", "cites": [], "would_need": "", "not_tested": True}}]})


def test_the_prompt_text_says_not_tested_not_untestable():
    from app.pipeline import consult

    # as a set-aside explanation
    text = consult._format_diagnosis(SimpleNamespace(diagnosis_json=_diagnosis_with_a_test_that_never_ran()))
    assert "Prices are too low (not tested: the test could not be run on our side)" in text
    assert "untestable" not in text

    # as the leading one: said outright, and not passed off as a test that ran
    diagnosis = json.loads(_diagnosis_with_a_test_that_never_ran())
    diagnosis["leading"] = "H2"
    text = consult._format_diagnosis(SimpleNamespace(diagnosis_json=json.dumps(diagnosis)))
    assert "The cause: Prices are too low" in text
    assert "This was not tested: the test could not be run on our side." in text
    assert "untestable" not in text and "Tested against their numbers" not in text and "Still unverified" not in text


def test_a_test_that_ran_and_was_inconclusive_still_reads_untestable():
    from app.pipeline import consult

    diagnosis = json.loads(_diagnosis_with_a_test_that_never_ran())
    diagnosis["hypotheses"][1]["test"] = {"verdict": "untestable", "because": "", "cites": [], "would_need": ""}

    text = consult._format_diagnosis(SimpleNamespace(diagnosis_json=json.dumps(diagnosis)))

    assert "Prices are too low (untestable)" in text and "not tested" not in text


def test_the_build_is_not_told_the_owners_explanation_was_unverifiable_when_it_was_never_tested():
    from app.pipeline import handoff

    text = handoff.for_build(SimpleNamespace(
        diagnosis_json=_diagnosis_with_a_test_that_never_ran(from_owner=True),
        consulting_recommendations_json=None))

    assert "The client's own explanation (Prices are too low) was not tested: the test could not be run on our side." in text
    assert "not verifiable" not in text


def test_the_answer_is_not_told_a_leading_explanation_was_untestable_when_it_was_never_tested():
    from app.pipeline import answer

    diagnosis = json.loads(_diagnosis_with_a_test_that_never_ran())
    diagnosis["leading"] = "H2"

    leading = answer._leading(SimpleNamespace(diagnosis_json=json.dumps(diagnosis)))

    assert leading == "Prices are too low — not tested: the test could not be run on our side"


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


# -- the interview ---------------------------------------------------------
#
# When our model call fails, the client is told so. They are never handed stock
# questions in its place, and never told "that's everything we need" because a
# round failed.

PROBLEM = "My pilates studio is full at 6pm and half empty at noon, and I do not know why."
INTERVIEW_STALLED = ("Our side stalled while we were preparing your next question. "
                     "We have been told. Your answers so far are still on this page.")
INTERVIEW_STALLED_UNTOLD = ("Our side stalled while we were preparing your next question. "
                            "Your answers so far are still on this page.")
SCOPE_STALLED = ("Our side stalled while we were writing the questions we need to ask you. "
                 "We have been told. What you wrote is still on this page.")
SCOPE_STALLED_UNTOLD = ("Our side stalled while we were writing the questions we need to ask you. "
                        "What you wrote is still on this page.")

TWO_QUESTIONS = {
    "questions": [
        {"id": "name", "label": "What is the studio called, and what do you do?",
         "placeholder": "e.g. Halo Reformer Studio", "why": "We cannot size a business we cannot name.",
         "field": "business_name"},
        {"id": "classes", "label": "How many classes do you run in a week?",
         "placeholder": "e.g. 36", "why": "It sets the scale everything else multiplies against."},
    ],
    "enough": False,
}


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from main import app

    Base.metadata.create_all(bind=engine)
    return TestClient(app)


def _scope(client):
    return client.post("/api/discovery/scope", data={"main_problem": PROBLEM})


def _interview(client, **form):
    return client.post("/api/discovery/interview", data={"main_problem": PROBLEM, **form})


def _unattributed_ledger(purpose: str) -> list[bool]:
    """The ledger rows for a call made before any run exists: success, oldest first."""
    from app.models import AiUsageEvent

    db = SessionLocal()
    try:
        rows = (db.query(AiUsageEvent)
                .filter(AiUsageEvent.request_id.is_(None), AiUsageEvent.purpose == purpose)
                .order_by(AiUsageEvent.id))
        return [e.success for e in rows]
    finally:
        db.close()


def test_scope_failure_is_a_503_and_mails_the_team_once(client, monkeypatch, outbox):
    _provider_is_down(monkeypatch)
    before = _unattributed_ledger("scope")

    first = _scope(client)
    second = _scope(client)

    for response in (first, second):
        assert response.status_code == 503
        assert response.json() == {"detail": SCOPE_STALLED}
        assert "sk-or" not in response.text  # the cause is the team's, not the screen's
    assert _unattributed_ledger("scope")[len(before):] == [False, False]
    assert len(outbox) == 1
    to, subject, body = outbox[0]
    assert to == settings.SMTP_USER and subject == "Stalled: scope"
    assert SECRET_CAUSE in body


@pytest.mark.parametrize("text", [
    pytest.param("I am sorry, I cannot do that.", id="no json at all"),
    pytest.param('{"question": "Should we raise', id="cut off mid-object"),
])
def test_a_scope_reply_that_cannot_be_read_is_a_stall(client, monkeypatch, outbox, text):
    _model_replies_text(monkeypatch, text)

    response = _scope(client)

    assert response.status_code == 503 and response.json() == {"detail": SCOPE_STALLED}
    assert [m[1] for m in outbox] == ["Stalled: scope"]


@pytest.mark.parametrize("reply", [
    pytest.param({}, id="an empty object"),
    pytest.param({"question": "", "facts": []}, id="no question and no facts"),
    pytest.param({"question": "too short", "facts": "not a list"}, id="junk"),
])
def test_a_scope_reply_with_nothing_in_it_is_a_stall(client, monkeypatch, outbox, reply):
    _model_replies(monkeypatch, reply)

    response = _scope(client)

    assert response.status_code == 503 and response.json() == {"detail": SCOPE_STALLED}
    assert [m[1] for m in outbox] == ["Stalled: scope"]


def test_a_scope_reply_with_few_facts_simply_has_few_facts(client, monkeypatch, outbox):
    _model_replies(monkeypatch, {
        "question": "Should the studio raise its evening prices?",
        "facts": [{"key": "price", "label": "What you charge", "group": "Money"},
                  {"key": "volume", "label": "Classes a week", "group": "Customers"}],
    })

    response = _scope(client)

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "ai"
    assert body["question"] == "Should the studio raise its evening prices?"
    assert [f["key"] for f in body["facts"]] == ["business_name", "what_you_do", "price", "volume"]
    assert outbox == []


def test_interview_round_failure_is_a_503(client, monkeypatch, outbox):
    _provider_is_down(monkeypatch)
    before = _unattributed_ledger("interview:2")

    response = _interview(client, business_name="Halo Reformer Studio", round="2",
                          ops_numbers=json.dumps([{"id": "name", "question": "What is it called?", "answer": "Halo"}]))

    assert response.status_code == 503
    assert response.json() == {"detail": INTERVIEW_STALLED}  # not done, not "that's everything we need"
    assert "sk-or" not in response.text
    assert _unattributed_ledger("interview:2")[len(before):] == [False]
    assert len(outbox) == 1
    to, subject, body = outbox[0]
    assert to == settings.SMTP_USER and subject == "Stalled: interview (Halo Reformer Studio)"
    assert "Round: 2" in body and SECRET_CAUSE in body


def test_a_failed_first_round_is_not_answered_with_stock_questions(client, monkeypatch, outbox):
    _provider_is_down(monkeypatch)

    response = _interview(client)  # round 1, and the business has no name yet

    assert response.status_code == 503 and response.json() == {"detail": INTERVIEW_STALLED}
    assert [m[1] for m in outbox] == ["Stalled: interview"]  # no business to name
    assert "Round: 1" in outbox[0][2]


def test_an_interview_reply_that_cannot_be_read_is_a_stall(client, monkeypatch, outbox):
    _model_replies_text(monkeypatch, "I would ask about prices, I think.")

    response = _interview(client, round="3")

    assert response.status_code == 503 and response.json() == {"detail": INTERVIEW_STALLED}
    assert "Round: 3" in outbox[0][2]


@pytest.mark.parametrize("reply", [
    pytest.param({"questions": []}, id="no questions"),
    pytest.param({}, id="an empty object"),
    pytest.param({"questions": [{"id": "a", "label": "   "}, "junk"]}, id="nothing usable"),
])
def test_an_empty_first_round_is_a_stall_not_stock_questions(client, monkeypatch, outbox, reply):
    """Nothing to ask before anything has been asked is not a consultant who has
    enough. It is a call that produced nothing."""
    _model_replies(monkeypatch, reply)

    response = _interview(client)

    assert response.status_code == 503
    assert response.json() == {"detail": INTERVIEW_STALLED}
    assert [m[1] for m in outbox] == ["Stalled: interview"]
    assert "Round: 1" in outbox[0][2]


def test_a_later_round_with_nothing_left_to_ask_still_ends_the_interview(client, monkeypatch, outbox):
    """Not a failure: the model read their answers and had nothing more worth
    asking. Only a round that FAILS is a stall."""
    _model_replies(monkeypatch, {"questions": [], "enough": True})

    response = _interview(client, round="4", business_name="Halo", business_description="A pilates studio",
                          known=json.dumps({"business_name": "Halo", "business_description": "A pilates studio"}))

    assert response.status_code == 200
    assert response.json()["done"] is True
    assert outbox == []


def test_a_successful_round_is_unchanged(client, monkeypatch, outbox):
    _model_replies(monkeypatch, TWO_QUESTIONS)

    response = _interview(client)

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "ai" and body["done"] is False
    assert [q["id"] for q in body["questions"]] == ["name", "classes"]
    assert body["questions"][0]["field"] == "business_name" and body["questions"][1]["field"] == ""
    assert body["questions"][0]["why"] == "We cannot size a business we cannot name."
    assert body["still_needed"] == ["business_name", "business_description"]
    assert outbox == []


def test_repeated_interview_stalls_send_one_mail(client, monkeypatch, outbox):
    """A provider outage stalls every round of every client at once. Each of
    them is told so, and the team gets one mail."""
    _provider_is_down(monkeypatch)

    first = _interview(client, business_name="Halo", round="2")
    second = _interview(client, business_name="Another Studio", round="5")

    assert first.status_code == second.status_code == 503
    # the second client's sentence is still true: the team was told of this outage
    assert first.json() == second.json() == {"detail": INTERVIEW_STALLED}
    assert [m[1] for m in outbox] == ["Stalled: interview (Halo)"]


def test_the_scope_and_the_interview_have_a_window_each(client, monkeypatch, outbox):
    _provider_is_down(monkeypatch)

    _scope(client)
    _interview(client)
    _scope(client)
    _interview(client, round="2")

    assert [m[1] for m in outbox] == ["Stalled: scope", "Stalled: interview"]


def test_a_stall_does_not_claim_the_team_was_told_when_mail_is_unconfigured(client, monkeypatch):
    """The real `send_now`, with no mail password: nothing goes out, so nothing
    may say it did. This holds for the follower inside the window too, because
    the mail that opened it never went."""
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "")
    _provider_is_down(monkeypatch)

    scope_first, scope_again = _scope(client), _scope(client)
    interview_first, interview_again = _interview(client, round="2"), _interview(client, round="3")

    for response in (scope_first, scope_again):
        assert response.status_code == 503 and response.json() == {"detail": SCOPE_STALLED_UNTOLD}
    for response in (interview_first, interview_again):
        assert response.status_code == 503 and response.json() == {"detail": INTERVIEW_STALLED_UNTOLD}
        assert "been told" not in response.json()["detail"]


def test_a_stall_whose_mail_blows_up_is_still_a_503(client, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("smtp went away")

    monkeypatch.setattr(mailer, "send_now", broken)
    _provider_is_down(monkeypatch)

    response = _interview(client)

    assert response.status_code == 503 and response.json() == {"detail": INTERVIEW_STALLED_UNTOLD}


def test_questions_endpoint_is_gone(client, monkeypatch):
    """`/questions` served three stock sets whenever its model call failed or
    came back thin. Nothing calls it; it is not there to be called."""
    from app.routers import discovery

    def must_not_be_called(*args, **kwargs):
        raise AssertionError("the model was called")

    monkeypatch.setattr("app.ai.provider.chat", must_not_be_called)

    response = client.post("/api/discovery/questions", data={
        "business_name": "Beacon", "business_description": "a clinic",
    })

    assert response.status_code == 404
    for name in ("_FALLBACK_OPERATING", "_FALLBACK_OPENING", "_FALLBACK_CAPABILITY", "discovery_questions"):
        assert not hasattr(discovery, name), name


def test_shape_scope_pads_only_the_two_required_facts():
    from app.routers import discovery

    required = ["business_name", "business_description"]
    for raw in ({}, "junk", {"facts": "x"}):
        got = discovery.shape_scope(raw, PROBLEM)
        assert [f["field"] for f in got["facts"]] == required
        assert all(f["status"] == "need" and f["value"] == "" for f in got["facts"])

    # what the model wrote stays, behind the two the engagement cannot launch without
    got = discovery.shape_scope({"facts": [{"key": "price", "label": "What you charge"}]}, PROBLEM)
    assert [f["key"] for f in got["facts"]] == ["business_name", "what_you_do", "price"]

    # a model that already asks for both adds nothing and loses nothing
    own = {"facts": [{"key": "called", "label": "Name", "field": "business_name"},
                     {"key": "does", "label": "What you do", "field": "business_description"}]}
    assert [f["key"] for f in discovery.shape_scope(own, PROBLEM)["facts"]] == ["called", "does"]

    # an unlaunched business is asked in the future tense
    opening = discovery.shape_scope({"operating_stage": "opening"}, PROBLEM)["facts"]
    assert [f["label"] for f in opening] == ["Name", "What it will do, and how big"]


def test_shape_scope_never_says_fallback():
    from app.routers import discovery

    for raw in ({}, "junk", {"question": "Should the studio raise its evening prices?", "facts": [{"label": "Price"}]}):
        assert discovery.shape_scope(raw, PROBLEM)["source"] == "ai"


# -- what /progress tells the client ---------------------------------------

RAW_DETAIL = "Generation failed: Traceback (most recent call last): OpenRouter 503 sk-or-v1-SECRET"
DOCUMENT_TITLES = {
    "blueprint": "The blueprint", "technical": "The technical plan", "operations": "The operations manual",
    "roadmap": "The implementation roadmap", "system": "Your system, screen by screen", "ai_team": "Your AI team",
}


ONE_PHASE = {"when": "Weeks 1 to 2", "title": "Set up", "do": "We wire it", "by": "us", "you": ""}


def _roadmap(status: str = "ready", phases=(ONE_PHASE,)) -> str:
    return json.dumps({"status": status, "phases": list(phases), "decisions": []})


def _employees(*titles: str) -> str:
    return json.dumps({"recommended_ai_employees": [{"title": t, "why": "w"} for t in titles]})


def _failed_row(record=None, **fields) -> int:
    """A run `fail_run` stopped: the legacy fields hold raw text, and `record`
    (the contents of `failure_json`, or None for a legacy row) the facts."""
    return _generating_row(
        status="failed", is_generating=False, is_failed=True, stage="failed",
        stage_label=fields.pop("stage_label", RAW_DETAIL), progress_detail=fields.pop("progress_detail", RAW_DETAIL),
        failure_json=None if record is None else (record if isinstance(record, str) else json.dumps(record)),
        **fields,
    )


def _record(**over) -> dict:
    return {"stage": "technical", "at": "2026-10-31T10:00:00+00:00", "cause": SECRET_CAUSE,
            "team_notified": True, "reason": client_reason("technical", True), **over}


def _progress(client, request_id: int) -> dict:
    response = client.get(f"/api/requests/{request_id}/progress")
    assert response.status_code == 200
    return response.json()


def _docs(**fields) -> list[tuple[str, str]]:
    from app import produced

    return [(d["key"], d["state"]) for d in produced.documents_for(Request(**fields))]


def test_documents_follow_what_exists():
    from app import produced

    got = produced.documents_for(Request(mvp_blueprint="# The blueprint", stage="technical"))

    assert got == [
        {"key": "blueprint", "title": "The blueprint", "state": "ready"},
        {"key": "technical", "title": "The technical plan", "state": "writing"},
    ]


def test_documents_come_in_the_order_the_client_reads_them():
    from app import produced

    row = Request(
        mvp_blueprint="b", technical_plan="t", playbook_json='{"quick_wins": []}', action_plan_json=_roadmap(),
        screens_json='{"screens": []}', consulting_recommendations_json=_employees("Front desk"), stage="done",
    )

    got = produced.documents_for(row)

    assert [d["key"] for d in got] == ["blueprint", "technical", "operations", "roadmap", "system", "ai_team"]
    assert {d["key"]: d["title"] for d in got} == DOCUMENT_TITLES
    assert all(d["state"] == "ready" for d in got)


@pytest.mark.parametrize("stage, key", [
    ("blueprint", "blueprint"), ("technical", "technical"), ("playbook", "operations"),
    ("roadmap", "roadmap"), ("screens", "system"),
])
def test_the_document_being_written_is_the_one_the_run_is_on(stage, key):
    assert _docs(stage=stage) == [(key, "writing")]


def test_a_stage_that_writes_no_document_marks_none_as_writing():
    for stage in ("queued", "researching", "diagnosing", "answer_ready", "planning", "quality", "done", "failed"):
        assert _docs(stage=stage) == [], stage


def test_a_document_that_exists_is_ready_even_while_its_stage_is_current():
    assert _docs(stage="blueprint", mvp_blueprint="b") == [("blueprint", "ready")]


@pytest.mark.parametrize("raw", [
    None, "", "not json", "[]", "{}", '{"recommended_ai_employees": []}', '{"recommended_ai_employees": "x"}',
    '{"recommended_ai_employees": null}', '{"recommended_features": ["a"]}', "[1, 2]", "null", "7",
])
def test_no_ai_team_row_when_no_agents(raw):
    assert _docs(consulting_recommendations_json=raw, stage="done") == []


def test_an_ai_team_row_when_there_are_agents():
    assert _docs(consulting_recommendations_json=_employees("Front desk", "Rota planner"), stage="researching") == [
        ("ai_team", "ready"),
    ]


@pytest.mark.parametrize("plan, stage, want", [
    (_roadmap(), "done", [("roadmap", "ready")]),
    (_roadmap("writing"), "done", []),
    (_roadmap("failed"), "done", []),
    (_roadmap(phases=()), "done", []),
    (json.dumps({"status": "ready"}), "done", []),
    (json.dumps({"status": "ready", "phases": "x"}), "done", []),
    ("not json", "done", []),
    ("[]", "done", []),
    ("null", "done", []),
    (None, "done", []),
    (_roadmap("writing"), "roadmap", [("roadmap", "writing")]),
    (None, "roadmap", [("roadmap", "writing")]),
    ("not json", "roadmap", [("roadmap", "writing")]),
])
def test_a_roadmap_is_ready_only_when_it_has_phases_and_is_not_being_written(plan, stage, want):
    assert _docs(action_plan_json=plan, stage=stage) == want


def test_documents_for_reads_the_row_alone():
    """A pure function of the row: it needs nothing else of it, and a missing
    column is an absent document, not an error."""
    from app import produced

    assert produced.documents_for(SimpleNamespace()) == []
    assert produced.documents_for(SimpleNamespace(mvp_blueprint="b", stage="technical")) == [
        {"key": "blueprint", "title": "The blueprint", "state": "ready"},
        {"key": "technical", "title": "The technical plan", "state": "writing"},
    ]


def test_documents_for_survives_the_columns_it_parses_holding_junk():
    assert _docs(action_plan_json="{", consulting_recommendations_json="{", stage="done") == []


def test_progress_tells_the_client_which_documents_exist(client):
    request_id = _generating_row(stage="technical", mvp_blueprint="# Blueprint")

    body = _progress(client, request_id)

    assert body["documents"] == [
        {"key": "blueprint", "title": "The blueprint", "state": "ready"},
        {"key": "technical", "title": "The technical plan", "state": "writing"},
    ]
    assert body["failure"] is None


def test_a_failed_run_still_lists_the_documents_it_wrote(client):
    request_id = _failed_row(_record(), mvp_blueprint="# Blueprint")

    assert _progress(client, request_id)["documents"] == [
        {"key": "blueprint", "title": "The blueprint", "state": "ready"},
    ]


def test_progress_failure_reads_from_the_runs_own_record(client):
    request_id = _failed_row(_record(team_notified=True))

    body = _progress(client, request_id)

    reason = client_reason("technical", True)
    assert body["failure"] == {"reason": reason, "team_notified": True}
    assert body["label"] == reason and body["detail"] == reason
    assert body["is_failed"] is True


def test_progress_failure_says_so_when_the_team_was_not_told(client):
    reason = client_reason("technical", False)
    request_id = _failed_row(_record(team_notified=False, reason=reason))

    body = _progress(client, request_id)

    assert body["failure"] == {"reason": reason, "team_notified": False}
    assert "We have been told" not in json.dumps(body)


def test_progress_failure_carries_only_the_client_reason(client):
    request_id = _failed_row(_record(cause="the key was sk-or-v1-SECRET"))

    body = _progress(client, request_id)

    assert set(body["failure"]) == {"reason", "team_notified"}
    assert "SECRET" not in json.dumps(body)
    assert "sk-or" not in json.dumps(body)


def test_a_legacy_failed_row_does_not_leak_its_raw_detail(client):
    request_id = _failed_row(None, stage_label="Generation failed: Traceback (most recent call last) SECRET")

    body = _progress(client, request_id)

    assert body["label"] == "Our side failed and the run stopped."
    assert body["detail"] is None
    assert body["failure"] is None
    assert body["is_failed"] is True
    assert "SECRET" not in json.dumps(body) and "Traceback" not in json.dumps(body)


@pytest.mark.parametrize("record", [
    "not json", "[]", "null", '"text"', "{}", '{"cause": "SECRET"}', '{"reason": ""}', '{"reason": "   "}',
    '{"reason": 5, "cause": "SECRET"}', '{"reason": null}',
])
def test_a_failed_row_whose_record_cannot_be_used_reads_as_a_legacy_one(client, record):
    request_id = _failed_row(record)

    body = _progress(client, request_id)

    assert body["label"] == "Our side failed and the run stopped." and body["detail"] is None
    assert body["failure"] is None
    assert "SECRET" not in json.dumps(body) and "Traceback" not in json.dumps(body)


def test_team_notified_is_true_only_when_the_record_says_true(client):
    for value in ("yes", 1, None, "true"):
        request_id = _failed_row(_record(team_notified=value))
        assert _progress(client, request_id)["failure"]["team_notified"] is False, value


def test_a_run_that_is_not_failed_reads_as_it_always_did(client):
    request_id = _generating_row(stage="technical", stage_label="Writing your technical plan...",
                                 progress_detail="Concept named: Halo", failure_json=json.dumps(_record()))

    body = _progress(client, request_id)

    # a failure left on the row by an earlier attempt is not this run's
    assert body["label"] == "Writing your technical plan..." and body["detail"] == "Concept named: Halo"
    assert body["failure"] is None and body["is_failed"] is False
    assert "SECRET" not in json.dumps(body)


def test_a_run_the_client_pushes_back_on_sheds_the_record_of_its_last_failure(client, monkeypatch):
    """The record belongs to the failure. A run that has started again is not
    stopped, and if it is stopped later by something that writes no record (a
    restart of the service), the old stage's words must not be read as its own."""
    monkeypatch.setattr(orchestrator, "run", lambda request_id: None)
    request_id = _failed_row(_record())

    response = client.post(f"/api/requests/{request_id}/decision/revise",
                           data={"note": "You misread our evening classes."})

    assert response.status_code == 200 and response.json()["started"] is True
    row = _read(request_id)
    assert row.failure_json is None and not row.is_failed and row.is_generating
    assert _progress(client, request_id)["failure"] is None


@pytest.mark.parametrize("stage, status", [("failed", "new"), ("technical", "failed"), ("failed", "failed")])
def test_a_row_failed_by_its_stage_or_status_alone_does_not_leak_its_raw_detail(client, stage, status):
    """`is_failed` is the flag `fail_run` sets, but a row from before it can say
    it failed in its `stage` or its `status` alone (the column also reads NULL
    on a database that grew it later). Its label and detail are the raw
    exception either way, and the page must not be handed them."""
    request_id = _generating_row(
        status=status, stage=stage, is_generating=False, is_failed=False,
        stage_label="Generation failed: Traceback SECRET", progress_detail="Traceback SECRET",
    )

    body = _progress(client, request_id)

    assert body["label"] == "Our side failed and the run stopped."
    assert body["detail"] is None and body["failure"] is None
    assert "SECRET" not in json.dumps(body) and "Traceback" not in json.dumps(body)


def test_a_run_started_again_does_not_carry_the_raw_words_of_its_last_failure(client, monkeypatch):
    """Between the restart and the new thread's first emit nothing has written a
    label yet. A legacy failed row's own label and detail are the raw exception,
    and its stage reads `failed` to the page, so the restart puts a queued run's
    words in all three."""
    monkeypatch.setattr(orchestrator, "run", lambda request_id: None)
    request_id = _failed_row(None, stage_label="Generation failed: Traceback SECRET",
                             progress_detail="Traceback SECRET")

    response = client.post(f"/api/requests/{request_id}/decision/revise",
                           data={"note": "You misread our evening classes."})

    assert response.status_code == 200 and response.json()["started"] is True
    row = _read(request_id)
    assert (row.stage, row.stage_label, row.progress_detail) == ("queued", "Queued", None)
    body = _progress(client, request_id)
    assert body["stage"] == "queued" and body["label"] == "Queued" and body["detail"] is None
    assert body["is_failed"] is False and body["is_generating"] is True
    assert "SECRET" not in json.dumps(body) and "Traceback" not in json.dumps(body)


def test_reopening_a_run_leaves_it_in_the_state_a_new_one_starts_in():
    from app.routers.requests import _reopen

    request_id = _failed_row(None, stage_label="Generation failed: Traceback SECRET",
                             progress_detail="Traceback SECRET", progress_pct=61)
    db = SessionLocal()
    try:
        assert _reopen(db, db.get(Request, request_id)) == 1
        db.commit()
    finally:
        db.close()

    row = _read(request_id)
    assert (row.status, row.is_generating, row.is_failed, row.failure_json) == ("new", True, False, None)
    assert (row.stage, row.stage_label, row.progress_detail) == ("queued", "Queued", None)


def test_a_run_that_fails_for_real_is_read_back_in_plain_words(client, outbox):
    request_id = _generating_row(stage="technical", mvp_blueprint="# Blueprint")
    assert _fail(request_id, "technical") is True

    body = _progress(client, request_id)

    reason = client_reason("technical", True)
    assert body["failure"] == {"reason": reason, "team_notified": True}
    assert body["label"] == reason and body["detail"] == reason
    assert body["is_generating"] is False and body["is_failed"] is True
    assert body["documents"] == [{"key": "blueprint", "title": "The blueprint", "state": "ready"}]
    assert "SECRET" not in json.dumps(body)


def test_a_run_that_fails_before_any_mail_can_go_is_read_back_without_the_claim(client, monkeypatch):
    monkeypatch.setattr(mailer, "send_now", lambda *args: False)
    request_id = _generating_row(stage="technical")
    assert _fail(request_id, "technical") is False

    body = _progress(client, request_id)

    assert body["failure"] == {"reason": client_reason("technical", False), "team_notified": False}
    assert "SECRET" not in json.dumps(body)


@pytest.mark.parametrize("path", [
    "/api/requests/mine", "/api/requests/{id}/preview", "/api/requests/{id}/decision", "/api/requests/{id}/plan",
    "/api/requests/{id}/admin", "/api/shared/{token}",
])
def test_no_other_route_hands_a_failed_runs_raw_detail_to_a_reader(client, path):
    """`/progress` is the one route that ever carried `stage_label` and
    `progress_detail`. The rest of what a client, a reviewer or a partner can
    open about a run says only its `status`; this pins that it stays so."""
    token = "partnertoken" + os.urandom(4).hex()
    request_id = _failed_row(_record(cause="SECRET"), share_token=token, review_status="approved")

    response = client.get(path.format(id=request_id, token=token))

    assert response.status_code == 200, path
    assert "SECRET" not in response.text and "Traceback" not in response.text, path


# -- the method page: how the work was done, and what was not verified -----

HOW = ("Build My Version's analysis system produced this engagement from the facts you gave us "
       "and the files you sent.")
INTEGRITY_LINE = "A consistency check ran across the whole document."
BENCH_CHECKS = [
    {"label": "Every figure traces to a client input", "passed": True, "note": "n"},
    {"label": "Assumptions explicit and conservative", "passed": False, "note": "n"},
    {"label": "All canonical sections present", "passed": True, "note": "n"},
]
HIGH_FINDING = {"severity": "high", "where": "w", "issue": "an invented figure", "fix": "f"}
FIGURES_CHECKED = "Every figure was compared with the figures you gave us."
SECTIONS_PRESENT = "Every section the documents should contain was present."
# Words that would turn a record of method into a disclaimer or a review claim.
FORBIDDEN_ON_THE_METHOD_PAGE = ("reviewed", "human", "not confident", "ai-generated", "confidence", "unsure")


def _method_row(findings=(), integrity=True, checks=BENCH_CHECKS, blueprint="## The decision\nA fine plan.",
                **fields) -> Request:
    """A finished engagement, held in memory: the facts the client gave, a
    blueprint, the quality bench's report and (unless `integrity` is False) a
    current integrity report. The release gate decides draft or final from
    these alone, as it does for a real row."""
    from tests._integrity_stub import stamp_clean

    row = Request(
        business_name="Halo Reformer Studio", business_description="A pilates studio.",
        email="test@example.com", status="done", is_generating=False, is_failed=False,
        revenue_today="Class passes and a monthly membership", main_problem="Evening classes sit half empty",
        ops_numbers_json=json.dumps([{"question": "Evening class size?", "answer": "5 of 12 places"}]),
        mvp_blueprint=blueprint,
        qa_report_json=json.dumps({"checks": list(checks), "findings": list(findings)}),
        **fields,
    )
    if integrity:
        stamp_clean(row)
    return row


def _method_page(row: Request) -> list[str]:
    """The text of every flowable the Evidence & method page puts on the page."""
    from app.pipeline import export_pdf

    flows = export_pdf._evidence_flowables(row, {}, [])
    return [f.getPlainText() for f in flows if hasattr(f, "getPlainText")]


def test_method_note_for_a_draft_lists_what_was_not_verified():
    from app.pipeline import export_pdf
    from app.pipeline.method_note import method_note

    row = _method_row(findings=[HIGH_FINDING])
    release = export_pdf.release_status(row)
    assert release["status"] == "draft" and release["reasons"]

    note = method_note(row, release)

    assert set(note) == {"how", "checks_ran", "not_verified"}
    assert note["how"] == HOW
    # the gate's reason is for the team; the client reads it restated
    assert release["reasons"] == ["1 open high finding(s) on the quality bench"]
    assert note["not_verified"] == ["The quality review found problems that are still open."]
    # only the checks that passed are claimed, each as our own fixed sentence
    assert note["checks_ran"] == [FIGURES_CHECKED, SECTIONS_PRESENT, INTEGRITY_LINE]
    # the note is a copy: changing it cannot change the release decision
    note["not_verified"].append("x")
    assert "x" not in release["reasons"]


def test_method_note_for_a_final_run_lists_the_checks_and_nothing_outstanding():
    from app.pipeline import export_pdf
    from app.pipeline.method_note import method_note

    row = _method_row(checks=[BENCH_CHECKS[0], BENCH_CHECKS[2]])
    release = export_pdf.release_status(row)
    assert release["status"] == "final"

    note = method_note(row, release)

    assert note["how"] == HOW
    assert note["not_verified"] == []
    assert note["checks_ran"] == [FIGURES_CHECKED, SECTIONS_PRESENT, INTEGRITY_LINE]


def test_the_integrity_layer_is_claimed_only_when_it_ran_on_this_content():
    from app.pipeline import export_pdf
    from app.pipeline.method_note import method_note

    row = _method_row(integrity=False)
    release = export_pdf.release_status(row)

    note = method_note(row, release)

    assert INTEGRITY_LINE not in note["checks_ran"]
    assert note["not_verified"] == ["The consistency check has not run on the current version of this engagement."]


@pytest.mark.parametrize("qa", [
    None, "", "not json", "[]", "null", '"text"', "{}", '{"checks": null}', '{"checks": "x"}',
    '{"checks": [null, 5, "x", {}, {"passed": true}, {"label": "", "passed": true}, {"label": 7, "passed": true}]}',
    '{"checks": [{"label": "No pass flag"}, {"label": "Said no", "passed": "false"}, {"label": "Zero", "passed": 0}]}',
])
def test_a_quality_report_that_cannot_be_read_claims_no_checks(qa):
    from app.pipeline.method_note import method_note

    row = _method_row(integrity=False)
    row.qa_report_json = qa

    note = method_note(row, {"reasons": []})

    assert note["checks_ran"] == []


def test_a_check_is_listed_once_however_often_the_bench_recorded_it():
    from app.pipeline.method_note import method_note

    row = _method_row(integrity=False, checks=[BENCH_CHECKS[0], BENCH_CHECKS[0], BENCH_CHECKS[2]])

    assert method_note(row, {})["checks_ran"] == [FIGURES_CHECKED, SECTIONS_PRESENT]


@pytest.mark.parametrize("release", [
    None, {}, [], "draft", {"reasons": None}, {"reasons": "x"}, {"reasons": []},
    {"status": "final", "reasons": []}, {"status": "client_approved", "reasons": None},
])
def test_a_release_decision_with_no_reasons_that_is_not_a_draft_leaves_nothing_outstanding(release):
    from app.pipeline.method_note import method_note

    assert method_note(_method_row(), release)["not_verified"] == []


@pytest.mark.parametrize("reasons", [[None], [5], [""], ["  "], [None, 5, "", "  "], [["a"], {"b": 1}]])
def test_a_reason_that_is_blank_or_not_text_is_still_a_check_that_did_not_pass(reasons):
    """A reason the gate gave stands for something that did not pass, whatever
    shape it arrived in: dropping it would leave a page that lists nothing under
    a cover that says DRAFT."""
    from app.pipeline.method_note import method_note

    assert method_note(_method_row(), {"status": "draft", "reasons": reasons})["not_verified"] == [
        "One check did not pass."]


@pytest.mark.parametrize("release", [
    {"status": "draft"}, {"status": "draft", "reasons": None}, {"status": "draft", "reasons": []},
    {"status": "draft", "reasons": "unreadable"},
])
def test_a_draft_never_lists_nothing_outstanding(release):
    from app.pipeline.method_note import method_note

    assert method_note(_method_row(), release)["not_verified"] == ["One check did not pass."]


def test_the_method_page_no_longer_says_every_claim_was_checked_before_release():
    row = _method_row(findings=[HIGH_FINDING])

    page = _method_page(row)

    assert page
    for text in page:
        assert "was checked against" not in text and "before release" not in text, text
        assert "structured decomposition" not in text, text
    assert HOW in page
    # the rule about how a figure may appear is still there, less its last claim
    rule = next(t for t in page if t.startswith("Method rule"))
    assert "30-day operating month" in rule and "plain arithmetic" in rule
    # what ran, as our sentences, never the bench's labels; and what did not
    assert "Checks that ran" in page
    assert FIGURES_CHECKED in page and "Every figure traces to a client input" not in page
    assert "Assumptions explicit and conservative" not in page
    assert INTEGRITY_LINE in page
    assert "Not verified" in page
    assert "The quality review found problems that are still open." in page
    assert not any("open high finding" in t or "quality bench" in t for t in page)
    # the rest of the page is as it was
    assert "Facts you supplied" in page and "Sources" in page


def test_the_method_page_names_nothing_outstanding_for_a_final_run():
    page = _method_page(_method_row())

    assert HOW in page and "Checks that ran" in page
    assert "Not verified" not in page


@pytest.mark.parametrize("draft", [True, False])
def test_the_method_page_has_no_review_or_confidence_language(draft):
    row = _method_row(findings=[HIGH_FINDING] if draft else [])

    for text in _method_page(row):
        for word in FORBIDDEN_ON_THE_METHOD_PAGE:
            assert word not in text.lower(), f"{word!r} in {text!r}"


# -- what the client reads of a release reason: the kind, never the string --

# Names of our own machinery, and anything shaped like an id, that no client
# surface may carry.
FORBIDDEN_CLIENT_WORDS = ("bench", "registry", "integrity", "artifact", "identifier", "token", "null")
ID_LIKE = re.compile(r"\b[a-z]+_[a-z0-9_]+\b|\b[a-z]{1,3}\d+\b|\b[A-Z]{2,}-\d+\b", re.IGNORECASE)

#: Every kind of reason the release gate gives (`release_status` and
#: `registry_reasons`), one real-looking example each, and the one sentence the
#: client reads for it.
REASON_KINDS = [
    ("the run did not complete",
     "This engagement had not finished being written."),
    ("no documents were produced",
     "No documents had been written for this engagement."),
    ("the quality bench never audited this run",
     "The quality review did not run on this engagement."),
    ("3 open high finding(s) on the quality bench",
     "The quality review found problems that are still open."),
    ("client-unsafe artifacts: template token, literal Null, unresolved placeholder",
     "Some wording or figures in the documents are unfinished or need correcting."),
    ("2 paraphrased pilot-gate restatement(s)",
     "The pilot's go or no-go rule is worded differently in different places."),
    ("4 KPI/acceptance number(s) map to no registered claim",
     "Some figures in the plans could not be tied back to a figure you gave us."),
    ("internal identifiers in client-facing text: pilot_queue, m3, CAP-01",
     "Some wording still uses working labels instead of the plain names of your system's parts."),
    ("1 pilot-design restatement(s) that are not the canonical randomized design",
     "The pilot is described with a design other than the one it is meant to use."),
    ("2 sentence(s) gate financial detail on a phone-number match alone",
     "Some wording lets a phone number alone unlock financial detail."),
    ("5 API path(s) rendered with spaces",
     "Some technical addresses are written with spaces in them."),
    ("1 pilot specification(s)/procedure(s) depend on AI logic or another module",
     "The pilot is specified to depend on other parts of the system that it should stand apart from."),
    ("3 contradiction(s) inside the pilot specification (procedures and pilot module)",
     "The pilot's procedures and its part of the system do not fully agree."),
    ("2 sentence(s) state a pilot attempt count different from the SOP's",
     "The number of attempts stated for the pilot differs between places."),
    ("6 list ordinal(s) labeled as thresholds",
     "Some numbers that only put a list in order are written as if they were limits."),
    ("2 unlabeled operating time(s)/cadence(s) in the procedures",
     "Some operating times in the procedures are not marked as proposals."),
    ("1 sentence(s) send a customer into the internal pilot queue",
     "Some wording points a customer to a work queue meant for your staff."),
    ("2 sentence(s) narrow the pilot population below the gate's population",
     "Some wording narrows the pilot to fewer customers than the pilot rule covers."),
    ("3 monthly-identity violation(s)",
     "Some monthly figures do not agree with the yearly figures they come from."),
    ("1 invented operational policy statement(s)",
     "Some wording states an operating policy that you did not give us."),
    ("integrity layer has not run on the current content",
     "The consistency check has not run on the current version of this engagement."),
    ("integrity layer: 2 finding(s)",
     "The consistency check found inconsistencies that are still open."),
    ("Volume I, page 7: the number 35 matches none of the client's figures, our workings, our estimates "
     "or a cited reference",
     "Some figures in the documents are not yet tied to your figures, our workings, our estimates or a "
     "cited source."),
    ("2 document(s) not yet checked against the figures since the last data change",
     "Some of the documents have not yet been checked against your figures."),
    ("the stored register no longer checks out against the figures",
     "The register no longer checks out against your figures."),
]


def _client_safe(text: str) -> bool:
    lowered = text.lower()
    return not any(word in lowered for word in FORBIDDEN_CLIENT_WORDS) and not ID_LIKE.search(text)


@pytest.mark.parametrize("reason, sentence", REASON_KINDS)
def test_each_kind_of_release_reason_is_restated_in_one_plain_sentence(reason, sentence):
    from app.pipeline.method_note import plain_reason

    assert plain_reason(reason) == sentence
    assert _client_safe(sentence), sentence
    # whatever the count or the names inside the reason, the sentence is the same
    assert plain_reason(f"  {reason}  ") == sentence


def test_the_kinds_are_told_apart_by_their_wording_not_their_numbers():
    from app.pipeline.method_note import plain_reason

    assert plain_reason("1 open high finding(s) on the quality bench") == plain_reason(
        "12 open high finding(s) on the quality bench")
    assert plain_reason("client-unsafe artifacts: literal Null") == plain_reason(
        "client-unsafe artifacts: template token, unresolved placeholder")
    assert plain_reason("integrity layer: 1 finding(s)") != plain_reason(
        "integrity layer has not run on the current content")


@pytest.mark.parametrize("reason", [
    "", "   ", "something nobody wrote a sentence for", "7 new kind(s) of problem in pilot_queue",
    "the quality bench audited this run twice", "Open high finding(s) on the quality bench",
    "x open high finding(s) on the quality bench", "client-unsafe", "integrity layer", None, 5, ["a"],
])
def test_a_reason_of_no_known_kind_is_the_generic_sentence_never_the_raw_string(reason):
    from app.pipeline.method_note import plain_reason

    assert plain_reason(reason) == "One check did not pass."


_LIST_MARK = "\x00names\x00"


def _reasons_in(source: str) -> tuple[list[str], list[str]]:
    """(the reason strings `source` puts into a list called `reasons`, and every
    place it touches that list in a form this reader does not understand).
    Reads `reasons.append(x)`, `reasons.extend([...])`, `reasons += [...]` and
    `reasons = [...]`, with strings and f-strings rendered (a number for each
    `{...}`, `_LIST_MARK` for a joined list of names); `reasons += registry_reasons(...)`
    is the other function's and is skipped. Anything else is returned as unread,
    so a new way of adding a reason fails the test instead of passing unseen."""
    import ast
    import textwrap

    def text_of(node) -> str:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            return "".join(v.value if isinstance(v, ast.Constant) else "7" for v in node.values)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return text_of(node.left) + text_of(node.right)
        return _LIST_MARK

    def literal_items(node):
        return [text_of(e) for e in node.elts] if isinstance(node, (ast.List, ast.Tuple)) else None

    def is_reasons(node) -> bool:
        return isinstance(node, ast.Name) and node.id == "reasons"

    built, unread = [], []
    for node in ast.walk(ast.parse(textwrap.dedent(source))):
        if isinstance(node, ast.Assign) and any(is_reasons(t) for t in node.targets):
            items = literal_items(node.value)
            if items is None:
                unread.append(ast.unparse(node))
            else:
                built += items
        elif isinstance(node, ast.AugAssign) and is_reasons(node.target):
            items = literal_items(node.value)
            if items is not None:
                built += items
            elif not (isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
                      and node.value.func.id in ("registry_reasons", "_presentation_reasons")):
                unread.append(ast.unparse(node))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and is_reasons(node.func.value):
            items = literal_items(node.args[0]) if node.args else None
            if node.func.attr == "append" and len(node.args) == 1:
                built.append(text_of(node.args[0]))
            elif node.func.attr == "extend" and items is not None:
                built += items
            else:
                unread.append(ast.unparse(node))
        elif isinstance(node, ast.Call) and any(is_reasons(arg) for arg in node.args):
            unread.append(ast.unparse(node))
    return built, unread


def test_the_reader_of_the_gates_reasons_sees_every_way_of_adding_one():
    built, unread = _reasons_in("""
def gate(n, hits):
    reasons = []
    reasons.append("a")
    reasons.append(f"{n} b")
    reasons.append("c: " + ", ".join(hits))
    reasons += ["d", f"{n} e"]
    reasons.extend(["f"])
    reasons += registry_reasons(req)
    return {"reasons": reasons}
""")
    assert sorted(built) == sorted(["a", "7 b", f"c: {_LIST_MARK}", "d", "7 e", "f"]) and unread == []

    built, unread = _reasons_in("""
def gate(more):
    reasons = ["x"]
    reasons += more
    reasons.extend(more)
    reasons.insert(0, "y")
    reasons = more
    helper(reasons)
""")
    assert built == ["x"]
    assert len(unread) == 5, unread


def test_every_reason_the_gate_can_give_has_its_own_sentence():
    """The kinds are told by the wording the gate uses, so a reason it gains or
    rewords would silently fall to the generic sentence. Read the strings the
    gate really builds, from its own source, and hold the table to them in both
    directions: no reason without a sentence, no sentence without a reason."""
    import inspect

    from app.pipeline import export_pdf, method_note

    built, unread = [], []
    for function in (export_pdf.release_status, export_pdf.registry_reasons):
        got, left = _reasons_in(inspect.getsource(function))
        built += got
        unread += left
    assert unread == [], f"a way of adding a reason that this test cannot read: {unread}"

    classes = ", ".join(dict.fromkeys(name for name, _ in export_pdf._GATE_ARTIFACTS))
    built = [reason.replace(_LIST_MARK, classes if reason.startswith("client-unsafe artifacts") else "pilot_queue, m3")
             for reason in built]
    # the release law's reason opens with three open parts (document, page, the
    # numbers), which this reader renders "7, 7: 7": give them real values and
    # keep the tail the gate's own source writes
    built = [reason.replace("7, 7: 7 ", "Volume I, page 7: the number 35 matches ", 1)
             if reason.startswith("7, 7: 7 ") else reason for reason in built]
    assert len(built) == len(method_note._KINDS) == len(REASON_KINDS), built
    sentences = [method_note.plain_reason(reason) for reason in built]
    assert method_note.GENERIC_REASON not in sentences, [
        reason for reason, sentence in zip(built, sentences) if sentence == method_note.GENERIC_REASON]
    assert sorted(sentences) == sorted(sentence for _, sentence in method_note._KINDS)
    assert sorted(sentences) == sorted(sentence for _, sentence in REASON_KINDS)


ARTIFACT_SENTENCE = "Some wording or figures in the documents are unfinished or need correcting."


def test_the_artifact_sentence_is_true_of_every_class_the_gate_names():
    """`client-unsafe artifacts` is nine classes, not one. Four are leftover
    placeholders (a template token, Null, an unresolved placeholder, a gate
    token); the others are an invented ROI figure, a currency sign on a count, a
    month computed two ways, an approval label said twice and a working label in
    the text. One sentence has to be true of all of them, and the class names
    are ours."""
    from app.pipeline import export_pdf, method_note
    from app.pipeline.method_note import plain_reason

    classes = list(dict.fromkeys(name for name, _ in export_pdf._GATE_ARTIFACTS))
    assert sorted(classes) == sorted([
        "template token", "literal Null", "unresolved placeholder", "unsubstituted gate token",
        "invented ROI figure", "currency sign on a count", "mixed monthly identity",
        "duplicate approval label", "internal identifier in client-facing text",
    ])
    # a class the gate adds reads as the generic sentence until it is read here
    assert list(method_note._ARTIFACT_CLASSES) == classes
    for name in classes:
        sentence = plain_reason(f"client-unsafe artifacts: {name}")
        assert sentence == ARTIFACT_SENTENCE, name
        assert _client_safe(sentence) and name.lower() not in sentence.lower(), name
    assert "placeholder" not in ARTIFACT_SENTENCE  # it is not only placeholders
    assert plain_reason("client-unsafe artifacts: " + ", ".join(classes)) == ARTIFACT_SENTENCE
    assert plain_reason("client-unsafe artifacts: invented ROI figure, template token") == ARTIFACT_SENTENCE


@pytest.mark.parametrize("reason", [reason for reason, _ in REASON_KINDS
                                    if not reason.startswith("internal identifiers")])
def test_a_reason_reworded_after_its_matched_wording_is_no_longer_the_kind_it_was(reason):
    from app.pipeline.method_note import plain_reason

    assert plain_reason(reason + " and something added") == "One check did not pass."
    assert plain_reason(reason + ".") == "One check did not pass."
    assert plain_reason("also " + reason) == "One check did not pass."


@pytest.mark.parametrize("reason", [
    "internal identifiers in client-facing text", "internal identifiers in client-facing text:",
    "internal identifiers in client-facing text (3): pilot_queue", "some internal identifiers in client-facing text: m3",
    "client-unsafe artifacts: ", "client-unsafe artifacts: a class nobody listed",
    "client-unsafe artifacts: template token, a class nobody listed", "client-unsafe artifacts: template token and more",
    "client-unsafe artifacts (2): template token",
])
def test_the_kinds_that_end_in_a_list_still_need_the_rest_of_their_wording(reason):
    from app.pipeline.method_note import plain_reason

    assert plain_reason(reason) == "One check did not pass."


def test_the_note_carries_plain_sentences_once_each_in_the_order_given():
    from app.pipeline.method_note import method_note

    release = {"reasons": [
        "something nobody wrote a sentence for",
        "2 KPI/acceptance number(s) map to no registered claim",
        "another thing nobody wrote a sentence for",
        "9 KPI/acceptance number(s) map to no registered claim",
        "the quality bench never audited this run",
    ]}

    assert method_note(_method_row(), release)["not_verified"] == [
        "One check did not pass.",
        "Some figures in the plans could not be tied back to a figure you gave us.",
        "The quality review did not run on this engagement.",
    ]


def test_a_draft_whose_reasons_carry_real_ids_prints_none_of_them(monkeypatch):
    from app.pipeline import export_pdf

    reasons = [
        "internal identifiers in client-facing text: pilot_queue, m3",
        "client-unsafe artifacts: template token, literal Null",
        "2 KPI/acceptance number(s) map to no registered claim (CAP-01, m1)",
        "a reason from a future release: reg_claim_7",
    ]
    # the last two are not the gate's wording as it stands: each reads as the
    # generic sentence, once
    monkeypatch.setattr(export_pdf, "release_status", lambda req: {
        "status": "draft", "status_label": "DRAFT", "reasons": reasons, "client_approval": {}})

    page = _method_page(_method_row())

    start = page.index("Not verified") + 1
    end = next(i for i, text in enumerate(page) if text.startswith("Method rule"))
    assert page[start:end] == [
        "Some wording still uses working labels instead of the plain names of your system's parts.",
        ARTIFACT_SENTENCE,
        "One check did not pass.",
    ]
    everything = " ".join(page)
    for leaked in ("pilot_queue", "m3", "m1", "CAP-01", "reg_claim_7", "template token", "literal Null"):
        assert not re.search(rf"(?<![\w-]){re.escape(leaked)}(?![\w-])", everything), leaked
    for text in page[start:end]:
        assert _client_safe(text), text


@pytest.mark.parametrize("blueprint, hit", [
    ("owner: [TODO fill in]", "unresolved placeholder"),
    ("The build returns 300% ROI in the first year.", "invented ROI figure"),
    ("Expect $4,000 inquiries every month.", "currency sign on a count"),
])
def test_a_blueprint_the_gate_holds_for_unfinished_wording_or_a_figure_says_so_truthfully(blueprint, hit):
    """End to end through the real release gate: the reason it builds is the
    team's wording and names the class; the page carries the client's sentence,
    which is true of a placeholder and of an invented figure alike."""
    from app.pipeline import export_pdf

    row = _method_row(blueprint=blueprint)
    reasons = export_pdf.release_status(row)["reasons"]
    assert reasons == [f"client-unsafe artifacts: {hit}"]

    page = _method_page(row)

    start = page.index("Not verified") + 1
    end = next(i for i, text in enumerate(page) if text.startswith("Method rule"))
    assert page[start:end] == [ARTIFACT_SENTENCE]
    text = " ".join(page)
    assert hit not in text and "artifact" not in text.lower() and "ROI" not in text and "TODO" not in text


# -- a reply that cannot be used is asked for again ------------------------
#
# A model reply that comes back cut off mid-object, or of the wrong shape, is
# an occasional fault of that one reply: the code records it in production
# (runs 47 and 49). With some forty replies in a run, stopping on the first one
# would end a good share of paid runs. So each is asked for again, up to
# STAGE_REPLY_ATTEMPTS in all; the provider's own failures are not, because
# the provider has already retried them.

CUT_OFF = '{"business_model": "Group classes", "pain_points": ["Empty mornin'
UNREADABLE = "the reply stopped here"  # no JSON object anywhere in it


def _replies_in_turn(monkeypatch, *replies) -> list[str]:
    """The provider answers each call with the next reply: a str is sent as it
    is, a dict as JSON, an exception is raised. Returns the prompts asked."""
    queue, asked, lock = list(replies), [], threading.Lock()

    def chat(model, messages, **kwargs):
        with lock:
            asked.append(messages[0]["content"])
            reply = queue.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        content = reply if isinstance(reply, str) else json.dumps(reply)
        return {"choices": [{"message": {"content": content}}], "usage": {}}

    monkeypatch.setattr("app.ai.provider.chat", chat)
    return asked


def _unusable_first(reply, times: int = 1, only: str | None = None):
    """A reply for `_provider_by_template`: unreadable the first `times` times
    each prompt (containing `only`, when given) is asked, then `reply`."""
    seen, lock = {}, threading.Lock()

    def answer(prompt):
        if only is not None and only not in prompt:
            return reply
        with lock:
            seen[prompt] = seen.get(prompt, 0) + 1
            n = seen[prompt]
        return UNREADABLE if n <= times else reply

    return answer


def _in_session(call):
    db = SessionLocal()
    try:
        return call(db)
    finally:
        db.close()


@pytest.mark.parametrize("value, held", [
    ("0", 1), ("1", 1), ("2", 2), ("3", 3), ("9", 3), ("-4", 1), ("", 2), ("two", 2),
])
def test_stage_reply_attempts_is_held_between_one_and_three(monkeypatch, value, held):
    from app import config

    monkeypatch.setenv("STAGE_REPLY_ATTEMPTS", value)
    assert config._env_int_within("STAGE_REPLY_ATTEMPTS", 2, 1, 3) == held
    assert 1 <= settings.STAGE_REPLY_ATTEMPTS <= 3


def test_an_unusable_reply_is_asked_for_up_to_the_setting_and_no_further(monkeypatch):
    from app.pipeline._shared import ask_until_usable, reply_json

    for attempts in (1, 2, 3):
        monkeypatch.setattr(settings, "STAGE_REPLY_ATTEMPTS", attempts)
        calls = []
        asked = _replies_in_turn(monkeypatch, *[UNREADABLE] * 4)
        from app.ai import provider

        with pytest.raises(ValueError):
            ask_until_usable(lambda: provider.chat("m", [{"role": "user", "content": "p"}]), reply_json,
                             lambda usage, error: calls.append(error))
        assert len(asked) == attempts and len(calls) == attempts and all(calls)


def test_a_provider_failure_is_never_asked_again_by_the_stage(monkeypatch):
    """The provider retried its own transient failures already; one that is
    refusing should stop the stage fast, not be asked again."""
    from app.ai import provider
    from app.pipeline._shared import ask_until_usable, reply_json

    monkeypatch.setattr(settings, "STAGE_REPLY_ATTEMPTS", 3)
    calls = []
    asked = _replies_in_turn(monkeypatch, AiProviderError(SECRET_CAUSE), {"ok": True})

    with pytest.raises(AiProviderError):
        ask_until_usable(lambda: provider.chat("m", [{"role": "user", "content": "p"}]), reply_json,
                         lambda usage, error: calls.append(error))
    assert len(asked) == 1 and calls == [SECRET_CAUSE]


def _stage_calls():
    from app.pipeline import analyze, blueprint, decide, plan, playbook

    return {
        "analyze": (lambda db, rid: analyze.analyze_business(db, rid),
                    CUT_OFF, {"business_model": "Group classes"}, "analyzing"),
        "decide": (lambda db, rid: decide.decide(db, rid, {"business_model": "classes"}),
                   CUT_OFF, {"intervention_kind": "software", "consulting_summary": "Fill the quiet hours."},
                   "consulting"),
        "plan": (lambda db, rid: plan.plan_integration(db, rid, {"consulting_summary": "Fill the quiet hours."}),
                 {"concept_name": "Halo", "roles": []},
                 {"concept_name": "Halo", "roles": [{"id": "customer_view", "label": "Customer View"}]},
                 "planning"),
        "playbook": (lambda db, rid: playbook.write_playbook(db, rid, {"concept_name": "Halo"}, None),
                     {"steps": [{"title": "Missing its phase and its owner"}]},
                     {"steps": [{"title": "Export your bookings", "phase": "before", "who": "you"}]},
                     "playbook"),
        "blueprint": (lambda db, rid: blueprint._markdown_call(db, rid, "blueprint", "write it", stage="blueprint"),
                      "   ", "## The decision\nGo.", "blueprint"),
        "technical_plan": (lambda db, rid: blueprint._markdown_call(db, rid, "technical_plan", "write it",
                                                                    stage="technical"),
                           "```markdown\n```", "## How it works\nIt works.", "technical"),
    }


SEQUENTIAL_STAGES = ["analyze", "decide", "plan", "playbook", "blueprint", "technical_plan"]


@pytest.mark.parametrize("purpose", SEQUENTIAL_STAGES)
def test_one_unusable_reply_then_a_usable_one_is_a_stage_that_worked(monkeypatch, purpose):
    call, unusable, usable, _ = _stage_calls()[purpose]
    asked = _replies_in_turn(monkeypatch, unusable, usable)
    request_id = _generating_row()

    assert _in_session(lambda db: call(db, request_id))

    assert len(asked) == 2 and asked[0] == asked[1]  # the same question, asked again
    assert _ledger(request_id) == [(purpose, False), (purpose, True)]


@pytest.mark.parametrize("purpose", SEQUENTIAL_STAGES)
def test_two_unusable_replies_stop_the_stage_and_both_are_on_the_ledger(monkeypatch, purpose):
    call, unusable, usable, stage = _stage_calls()[purpose]
    asked = _replies_in_turn(monkeypatch, unusable, unusable, usable)
    request_id = _generating_row()

    with pytest.raises(StageFailed) as stopped:
        _in_session(lambda db: call(db, request_id))

    assert stopped.value.stage == stage
    assert len(asked) == 2
    assert _ledger(request_id) == [(purpose, False), (purpose, False)]


def test_a_run_whose_analysis_comes_back_cut_off_twice_stops_and_says_where(pipeline_with_only, monkeypatch):
    run = pipeline_with_only("analyzing")
    _replies_in_turn(monkeypatch, CUT_OFF, CUT_OFF)

    orchestrator.run(run.request_id)

    row = _read(run.request_id)
    assert row.status == "failed" and json.loads(row.failure_json)["stage"] == "analyzing"
    assert [m[1] for m in run.outbox] == ["Run failed: Halo Reformer Studio (analyzing)"]


def test_a_run_whose_analysis_comes_back_cut_off_once_carries_on(pipeline_with_only, monkeypatch):
    run = pipeline_with_only("analyzing")
    _replies_in_turn(monkeypatch, CUT_OFF, {"business_model": "Group classes"})

    orchestrator.run(run.request_id)

    row = _read(run.request_id)
    assert row.status == "done" and not row.is_failed
    assert json.loads(row.business_analysis_json)["business_model"] == "Group classes"


def test_a_breakdown_that_comes_back_cut_off_once_is_asked_for_again(monkeypatch):
    from app.pipeline import decompose

    _provider_by_template(monkeypatch, decompose, {
        "decompose.j2": _unusable_first(TWO_MODULES), "module_spec.j2": {"features": []},
        "tech_spec.j2": {"data_model": []}})
    request_id = _generating_row()

    result = _decompose(request_id)

    assert [m["name"] for m in result["modules"]] == ["Module 0", "Module 1"]
    assert sorted(_ledger(request_id)) == sorted([
        ("decompose", False), ("decompose", True), *[("module_spec", True)] * 2, *[("tech_spec", True)] * 2])


@pytest.mark.parametrize("template, purpose", [("module_spec.j2", "module_spec"), ("tech_spec.j2", "tech_spec")])
def test_one_modules_spec_that_comes_back_cut_off_once_is_asked_for_again(monkeypatch, template, purpose):
    from app.pipeline import decompose

    replies = {"decompose.j2": TWO_MODULES, "module_spec.j2": {"features": []}, "tech_spec.j2": {"data_model": []}}
    replies[template] = _unusable_first(replies[template], only="Name: Module 1\n")
    _provider_by_template(monkeypatch, decompose, replies)
    request_id = _generating_row()

    result = _decompose(request_id)

    assert all(m["spec"] is not None and m["tech"] is not None for m in result["modules"])
    rows = [ok for p, ok in _ledger(request_id) if p == purpose]
    assert sorted(rows) == [False, True, True]  # Module 1 twice, Module 0 once


@pytest.mark.parametrize("template", ["module_spec.j2", "tech_spec.j2"])
def test_one_modules_spec_that_comes_back_cut_off_twice_stops_decomposition(monkeypatch, template):
    from app.pipeline import decompose

    replies = {"decompose.j2": TWO_MODULES, "module_spec.j2": {"features": []}, "tech_spec.j2": {"data_model": []}}
    replies[template] = _unusable_first(replies[template], times=2, only="Name: Module 1\n")
    _provider_by_template(monkeypatch, decompose, replies)
    request_id = _generating_row()

    with pytest.raises(StageFailed) as stopped:
        _decompose(request_id)

    assert stopped.value.stage == "decomposing" and "Module 1" in stopped.value.cause
    purpose = template.removesuffix(".j2")
    assert sorted(ok for p, ok in _ledger(request_id) if p == purpose) == [False, False, True]


def test_a_shaping_layer_that_comes_back_cut_off_once_is_asked_for_again(monkeypatch):
    from app.pipeline import extras

    _provider_by_template(monkeypatch, extras, {**SHAPING_LAYERS,
                                                "journey.j2": _unusable_first(SHAPING_LAYERS["journey.j2"])})
    request_id = _generating_row()

    _shape(request_id)

    assert [ok for p, ok in _ledger(request_id) if p == "journey"] == [False, True]
    assert json.loads(_read(request_id).journey_json)["stages"][0]["stage"] == "Find a class"


def test_a_shaping_layer_that_comes_back_wrong_twice_stops_the_run(monkeypatch):
    from app.pipeline import extras

    _provider_by_template(monkeypatch, extras, {**SHAPING_LAYERS, "journey.j2": {"stages": []}})
    request_id = _generating_row()

    with pytest.raises(StageFailed) as stopped:
        _shape(request_id)

    assert stopped.value.stage == "shaping" and "journey had no valid stages" in stopped.value.cause
    assert [ok for p, ok in _ledger(request_id) if p == "journey"] == [False, False]
    assert _read(request_id).journey_json is None


def test_a_diagnosis_that_comes_back_cut_off_once_is_asked_for_again(monkeypatch):
    from app.pipeline import diagnose

    _provider_by_template(monkeypatch, diagnose, {
        "diagnose.j2": _unusable_first(_explanations(*EXPLANATIONS)),
        "test_hypothesis.j2": {"verdict": "supported", "because": "The evenings are full.", "cites": []},
        "challenge.j2": {"kills": False, "because": "It held.", "weakness": ""}})
    request_id = _generating_row()

    result = _diagnose(request_id)

    assert len(result["hypotheses"]) == 3 and result["status"] == "survived"
    assert _ledger(request_id)[:2] == [("diagnose:1", False), ("diagnose:1", True)]


def test_a_hypothesis_test_that_comes_back_cut_off_once_is_still_tested(monkeypatch):
    from app.pipeline import diagnose

    _provider_by_template(monkeypatch, diagnose, {
        "diagnose.j2": _explanations(*EXPLANATIONS),
        "test_hypothesis.j2": _unusable_first({"verdict": "supported", "because": "The evenings are full.",
                                               "cites": []}, only="Mornings are empty"),
        "challenge.j2": {"kills": False, "because": "It held.", "weakness": ""}})
    request_id = _generating_row()

    result = _diagnose(request_id)

    tests = {h["statement"]: h["test"] for h in result["hypotheses"]}
    assert not tests["Mornings are empty"].get("not_tested") and tests["Mornings are empty"]["verdict"] == "supported"
    assert sorted(ok for p, ok in _ledger(request_id) if p == "test_hypothesis") == [False, True, True, True]


def test_a_hypothesis_test_that_comes_back_cut_off_twice_is_not_tested(monkeypatch):
    from app.pipeline import diagnose

    _provider_by_template(monkeypatch, diagnose, {
        "diagnose.j2": _explanations(*EXPLANATIONS),
        "test_hypothesis.j2": _unusable_first({"verdict": "supported", "because": "The evenings are full.",
                                               "cites": []}, times=2, only="Mornings are empty"),
        "challenge.j2": {"kills": False, "because": "It held.", "weakness": ""}})
    request_id = _generating_row()

    result = _diagnose(request_id)

    tests = {h["statement"]: h["test"] for h in result["hypotheses"]}
    assert tests["Mornings are empty"]["not_tested"] is True
    assert sorted(ok for p, ok in _ledger(request_id) if p == "test_hypothesis") == [False, False, True, True]


CAPACITY_TEXTS = ["12 reformers, six classes a day, six days a week."]


def test_a_capacity_read_cut_off_once_is_asked_for_again(monkeypatch):
    from app.pipeline import capacity

    asked = _replies_in_turn(monkeypatch, CUT_OFF, {"week": []})
    earlier = []

    picture, usage, error = capacity.read(CAPACITY_TEXTS, earlier=earlier)

    assert error is None and len(asked) == 2
    assert len(earlier) == 1 and earlier[0][1]  # the unreadable reply, with its error


def test_a_capacity_read_cut_off_twice_reports_its_error(monkeypatch):
    from app.pipeline import capacity

    _replies_in_turn(monkeypatch, CUT_OFF, CUT_OFF)
    earlier = []

    picture, usage, error = capacity.read(CAPACITY_TEXTS, earlier=earlier)

    assert picture is None and error and len(earlier) == 1


def test_the_run_ledgers_every_capacity_call_and_stops_on_two_unreadable_replies(monkeypatch):
    _replies_in_turn(monkeypatch, CUT_OFF, CUT_OFF)
    request_id = _generating_row(main_problem=CAPACITY_TEXTS[0])

    with pytest.raises(StageFailed) as stopped:
        _in_session(lambda db: orchestrator._read_capacity(db, request_id))

    assert stopped.value.stage == "capacity"
    assert _ledger(request_id) == [("capacity", False), ("capacity", False)]


# -- the structural preflight: only the first attempt must produce a skeleton


SKELETON = {"modules": [{"id": "booking", "name": "Booking"}], "business_case": {}, "registry": {}}


def _preflight(monkeypatch, *attempts):
    """Run the preflight over decomposition attempts that each return a
    skeleton (which the preflight always finds a defect in) or raise."""
    queue = list(attempts)

    def decompose_business(db, request_id, *args, **kwargs):
        outcome = queue.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr("app.pipeline.decompose.decompose_business", decompose_business)
    monkeypatch.setattr(orchestrator, "_structural_preflight",
                        lambda *a, **k: [{"where": "scenarios", "issue": "A defect.", "fix": "Fix it."}])
    request_id = _generating_row()
    return _in_session(lambda db: orchestrator._decompose_with_preflight(db, request_id, {}, {}, {})), queue


@pytest.mark.parametrize("failure", [
    pytest.param(StageFailed("decomposing", "the breakdown came back with no usable modules"), id="stage failed"),
    pytest.param(AiProviderError(SECRET_CAUSE), id="provider"),
    pytest.param(ValueError("No JSON object found"), id="anything else"),
])
def test_a_preflight_retry_that_produces_nothing_carries_on_with_the_skeleton_in_hand(monkeypatch, failure):
    decomposition, left = _preflight(monkeypatch, SKELETON, failure, {"modules": "never asked"})

    assert decomposition is SKELETON
    assert left == [{"modules": "never asked"}]  # no attempt after the one that failed


def test_a_preflight_whose_third_attempt_fails_carries_on_with_the_second(monkeypatch):
    second = {**SKELETON, "modules": [{"id": "payments", "name": "Payments"}]}

    decomposition, _ = _preflight(monkeypatch, SKELETON, second, StageFailed("decomposing", "boom"))

    assert decomposition is second


def test_a_preflight_whose_first_attempt_produces_nothing_stops(monkeypatch):
    with pytest.raises(StageFailed) as stopped:
        _preflight(monkeypatch, StageFailed("decomposing", "boom"), SKELETON)

    assert stopped.value.stage == "decomposing"


# -- a provider that is down is asked once per call, never again by a stage --


@pytest.mark.parametrize("real, failed_stage", STAGES_THAT_STOP_THE_RUN)
def test_a_provider_that_is_down_is_asked_once_per_call(pipeline_with_only, monkeypatch, real, failed_stage):
    run = pipeline_with_only(real)
    asked, lock = [], threading.Lock()

    def provider_down(*args, **kwargs):
        with lock:
            asked.append(1)
        raise AiProviderError(SECRET_CAUSE)

    monkeypatch.setattr("app.ai.provider.chat", provider_down)

    orchestrator.run(run.request_id)

    ledger = _ledger(run.request_id)
    assert json.loads(_read(run.request_id).failure_json)["stage"] == failed_stage
    # every call is on the ledger once, as failed, and none was asked twice
    assert len(asked) == len(ledger) and not any(ok for _, ok in ledger)
    assert len({purpose for purpose, _ in ledger}) == len(ledger), ledger


# -- a run with no volume, and the runs a restart stops: the same machinery --


def test_a_run_with_no_volume_fails_through_fail_run_and_tells_the_team_once(pipeline_with_only, monkeypatch):
    run = pipeline_with_only(None)
    monkeypatch.setattr("app.pipeline.blueprint.write_blueprint", _nothing)  # writes no volume

    orchestrator.run(run.request_id)

    row = _read(run.request_id)
    assert row.status == "failed" and row.is_failed and not row.is_generating
    record = json.loads(row.failure_json)
    assert record["stage"] == "blueprint" and record["cause"] == "no blueprint and no technical plan were produced"
    assert row.progress_detail == client_reason("blueprint", True)
    assert [m[1] for m in run.outbox] == ["Run failed: Halo Reformer Studio (blueprint)"]


RESTARTED = "Our service restarted while your engagement was being written."


def _no_run_in_flight() -> None:
    """Rows left generating by earlier tests are not this test's runs."""
    db = SessionLocal()
    try:
        db.query(Request).filter(Request.is_generating.is_(True)).update({"is_generating": False})
        db.commit()
    finally:
        db.close()


def _restart():
    """What startup does with the runs a restart left generating; waits for the
    mail thread so the test can read what it did."""
    import main

    thread = main._fail_stranded_requests()
    if thread is not None:
        thread.join(timeout=10)
        assert not thread.is_alive()
    return thread


@pytest.mark.parametrize("count", [0, 1, 3])
def test_a_restart_stops_every_run_in_flight_and_sends_one_mail_for_all_of_them(client, outbox, count):
    _no_run_in_flight()
    ids = [_generating_row() for _ in range(count)]
    finished = _generating_row(is_generating=False, status="done", stage="done")

    _restart()

    for request_id in ids:
        row = _read(request_id)
        assert row.status == "failed" and row.is_failed and not row.is_generating and row.stage == "failed"
        record = json.loads(row.failure_json)
        assert record["stage"] == "blueprint" and record["team_notified"] is True
        assert record["reason"] == RESTARTED + " We have been told and are looking into it."
        assert row.progress_detail == record["reason"] and row.stage_label == failure._FAILED_LABEL
        assert _progress(client, request_id)["failure"] == {"reason": record["reason"], "team_notified": True}
    assert len(outbox) == (1 if count else 0)
    if count:
        to, subject, body = outbox[0]
        assert to == settings.SMTP_USER
        assert subject == f"Service restarted: {count} run{'' if count == 1 else 's'} stopped"
        for request_id in ids:
            assert mailer._run_url(_read(request_id).public_id) in body
    assert _read(finished).status == "done" and not _read(finished).is_failed


def test_a_restart_whose_mail_cannot_go_does_not_say_the_team_was_told(monkeypatch):
    monkeypatch.setattr(mailer, "send_now", lambda to, subject, body: False)
    _no_run_in_flight()
    request_id = _generating_row()

    _restart()

    row = _read(request_id)
    record = json.loads(row.failure_json)
    assert row.status == "failed" and record["team_notified"] is False
    assert record["reason"] == RESTARTED and row.progress_detail == RESTARTED
    for word in FORBIDDEN:
        assert word not in record["reason"]


def test_a_restart_sweep_that_breaks_never_stops_the_service_starting(monkeypatch):
    import main

    def broken(db):
        raise RuntimeError("database locked")

    monkeypatch.setattr(failure, "fail_interrupted_runs", broken)
    assert main._fail_stranded_requests() is None


def test_a_restart_mail_that_blows_up_leaves_the_runs_stopped(monkeypatch):
    def explode(runs):
        raise RuntimeError("mail layer bug")

    monkeypatch.setattr(mailer, "notify_team_restart", explode)
    _no_run_in_flight()
    request_id = _generating_row()

    _restart()

    row = _read(request_id)
    assert row.status == "failed" and json.loads(row.failure_json)["team_notified"] is False


def test_notify_team_restart_sends_nothing_for_no_runs(outbox):
    assert mailer.notify_team_restart([]) is False
    assert outbox == []


# -- the checks that ran: our sentences, never the label a model wrote ------


def _labels_the_auditors_are_asked_for() -> list[str]:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    labels = []
    for name in ("qa_numbers.j2", "qa_completeness.j2"):
        with open(os.path.join(here, "app", "prompts", name), encoding="utf-8") as fh:
            labels += re.findall(r'"label":\s*"([^"]+)"', fh.read())
    return labels


def test_every_check_the_auditors_are_asked_to_record_has_a_sentence():
    """A label added to an audit prompt, and not here, would silently drop off
    the page: the two lists are held together."""
    from app.pipeline.method_note import _CHECK_SENTENCES, _check_key

    labels = _labels_the_auditors_are_asked_for()
    assert len(labels) == 7
    assert {_check_key(label) for label in labels} == set(_CHECK_SENTENCES)


@pytest.mark.parametrize("label", [
    "Every figure traces to a client input", "Attributions present on computed figures",
    "Assumptions explicit and conservative", "No internal contradictions between figures",
    "All canonical sections present", "Documents consistent with the structured layers",
    "Scope obeys the engagement register",
])
def test_a_known_check_is_told_as_its_sentence_and_its_label_is_never_printed(label):
    from app.pipeline.method_note import _CHECK_SENTENCES, _check_key, method_note

    for written in (label, label.upper(), "  " + label.replace(" ", "\n  ") + " "):
        row = _method_row(integrity=False, checks=[{"label": written, "passed": True, "note": "n"}])
        assert method_note(row, {})["checks_ran"] == [_CHECK_SENTENCES[_check_key(label)]]

    page = _method_page(_method_row(checks=[{"label": label, "passed": True, "note": "n"}]))
    assert _CHECK_SENTENCES[_check_key(label)] in page
    assert not any(label.lower() in text.lower() for text in page), label


@pytest.mark.parametrize("label", [
    "Pricing matches the market", "Every figure traces to a client input, mostly",
    "Scope obeys the engagement register (partly)", "The model is confident in these numbers",
])
def test_a_check_label_the_model_made_up_is_not_printed(label):
    from app.pipeline.method_note import method_note

    checks = [{"label": label, "passed": True, "note": "n"}, BENCH_CHECKS[2]]
    row = _method_row(checks=checks)

    assert method_note(row, {})["checks_ran"] == [SECTIONS_PRESENT, INTEGRITY_LINE]
    page = " ".join(_method_page(row))
    assert label not in page and SECTIONS_PRESENT in page


def test_the_check_sentences_carry_no_review_or_confidence_language():
    from app.pipeline.method_note import _CHECK_SENTENCES

    for sentence in _CHECK_SENTENCES.values():
        assert sentence.endswith(".")
        for word in FORBIDDEN_ON_THE_METHOD_PAGE + ("AI", "model", "pipeline", "try again"):
            assert not re.search(rf"\b{re.escape(word)}\b", sentence, re.IGNORECASE), (word, sentence)


# -- startup says so when mail cannot be sent -------------------------------


def _startup_warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records
            if r.name == "consultant.startup" and r.levelname == "WARNING"]


def test_startup_warns_once_when_mail_is_not_configured(monkeypatch, caplog):
    import main

    monkeypatch.setattr(settings, "SMTP_PASSWORD", "")
    monkeypatch.setattr(main, "_mail_warned", False)
    caplog.set_level("WARNING", logger="consultant.startup")

    main._warn_if_mail_is_not_configured()
    main._warn_if_mail_is_not_configured()

    assert _startup_warnings(caplog) == [
        "Mail is not configured: failures, stalls and ready notices will not be emailed."]


def test_startup_says_nothing_about_mail_that_is_configured(monkeypatch, caplog):
    import main

    monkeypatch.setattr(settings, "SMTP_PASSWORD", "pw")
    monkeypatch.setattr(settings, "SMTP_USER", "consulting@example.com")
    monkeypatch.setattr(main, "_mail_warned", False)
    caplog.set_level("WARNING", logger="consultant.startup")

    main._warn_if_mail_is_not_configured()

    assert _startup_warnings(caplog) == []


def test_the_live_compose_file_passes_the_mail_settings_to_the_service():
    """docker-compose.coolify.yml gives the consultant container no env_file,
    so a setting it does not name never reaches the service."""
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(os.path.join(here, "docker-compose.coolify.yml"), encoding="utf-8") as fh:
        text = fh.read()
    # the consultant service's block: from its key to the next top-level key
    # or service (read as text: the suite does not depend on a YAML parser)
    start = text.index("\n  consultant:\n")
    following = re.search(r"\n(?:  [a-z][\w-]*:|[a-z][\w-]*:)", text[start + 1:])
    block = text[start:start + 1 + following.start()] if following else text[start:]
    for name in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "REVIEW_MODE", "REVIEW_TOKEN",
                 "ENGAGEMENT_LEAD", "STALL_MAIL_WINDOW_SECONDS", "STAGE_REPLY_ATTEMPTS"):
        # passed through, and empty when unset: never a value written here
        assert f"\n      {name}: ${{{name}:-}}\n" in block, name


def test_an_empty_mail_setting_reads_as_unset(monkeypatch):
    """What the compose file passes when Coolify has no value: the setting's
    own default, never a crash on int("")."""
    from app import config

    for name, default in (("SMTP_PORT", "465"), ("STALL_MAIL_WINDOW_SECONDS", "300"), ("SMTP_HOST", "h")):
        monkeypatch.setenv(name, "")
        assert config._env_or(name, default) == default
    monkeypatch.setenv("STAGE_REPLY_ATTEMPTS", "")
    assert config._env_int_within("STAGE_REPLY_ATTEMPTS", 2, 1, 3) == 2


# -- a business name is cleaned before it stands in a subject line ----------


@pytest.fixture
def smtp(monkeypatch):
    """The real `send_now`, against an SMTP server that accepts everything:
    what reaches it is the message EmailMessage built, so a header it refuses
    is a mail that never went."""
    sent: list = []

    class Server:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def login(self, user, password):
            pass

        def send_message(self, msg):
            sent.append(msg)

    monkeypatch.setattr(settings, "SMTP_PASSWORD", "pw")
    monkeypatch.setattr(settings, "SMTP_USER", "consulting@example.com")
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", Server)
    return sent


_REAL_SEND_NOW = mailer.send_now  # before any test stubs it
LONG_NAME = "Halo Reformer Studio and Wellness Collective of the Greater Northern Riverside District Partnership"
NAMES = [
    pytest.param("Halo Reformer\nStudio", "Halo Reformer Studio", id="newline"),
    pytest.param("Halo\r\nReformer\tStudio", "Halo Reformer Studio", id="crlf and tab"),
    pytest.param("  Halo\x00 Reformer Studio  ", "Halo Reformer Studio", id="control characters"),
    pytest.param("", "an engagement", id="empty"),
    pytest.param("\n\t ", "an engagement", id="only whitespace"),
]


def _clean(subject: str) -> bool:
    return subject == subject.strip() and not any(not ch.isprintable() for ch in subject) and "  " not in subject


@pytest.mark.parametrize("name, shown", NAMES)
def test_subject_text_cleans_a_name_for_a_subject_line(name, shown):
    assert mailer._subject_text(name) == shown


def test_subject_text_cuts_a_long_name_at_a_word():
    text = mailer._subject_text(LONG_NAME)
    assert len(text) <= mailer.SUBJECT_TEXT_MAX and text.endswith("…")
    assert LONG_NAME.startswith(text[:-1]) and LONG_NAME[len(text) - 1] == " "  # cut between words
    assert mailer._subject_text("x" * 200).startswith("x" * 70)  # one long word is still cut


@pytest.mark.parametrize("name, shown", NAMES + [pytest.param(LONG_NAME, mailer._subject_text(LONG_NAME), id="long")])
def test_every_mail_with_a_business_name_in_its_subject_still_goes(smtp, monkeypatch, name, shown):
    monkeypatch.setattr(settings, "REVIEW_TOKEN", "t")
    sends = {
        "failure": lambda: mailer.notify_team_failure("abc123", name, "blueprint", "boom"),
        "stall": lambda: mailer.notify_team_stall("interview", name or "x", 2, "boom"),
        "ready": lambda: mailer.notify_owner_ready("abc123", "owner@example.com", name),
        "restart": lambda: mailer.notify_team_restart([("abc123", name)]),
    }
    for what, send in sends.items():
        assert send() is True, what
    # the fire-and-forget ones go on a thread: run them where the test can see
    monkeypatch.setattr(mailer, "send_async", lambda to, subject, body: mailer.send_now(to, subject, body))
    mailer.notify_team_go_ahead("abc123", name, "owner@example.com", {})
    mailer.notify_owner_released("abc123", "owner@example.com", name, None)
    mailer.notify_reviewer_pending("abc123", name)

    subjects = [msg["Subject"] for msg in smtp]
    assert len(subjects) == 7
    for subject in subjects:
        assert _clean(subject), subject
    assert subjects[0] == f"Run failed: {shown} (blueprint)"
    assert subjects[2] == f"{shown} — your answer and plans are ready"
    assert subjects[4] == f"Go ahead — {shown}"
    assert subjects[5] == f"{shown} — your engagement is ready"
    assert subjects[6] == f"An engagement awaits your review — {shown}"


def test_a_stall_with_no_business_name_names_none(outbox):
    for name in (None, "", "\n"):
        mailer.notify_team_stall("interview", name, 1, "boom")
    assert [m[1] for m in outbox] == ["Stalled: interview"] * 3


def test_a_run_whose_business_name_holds_a_newline_still_tells_the_team(pipeline_with_only, smtp, monkeypatch):
    run = pipeline_with_only("analyzing")
    db = SessionLocal()
    try:
        db.get(Request, run.request_id).business_name = "Halo Reformer\nStudio"
        db.commit()
    finally:
        db.close()
    # the real send_now, not the outbox stub the run's fixture installed
    monkeypatch.setattr(mailer, "send_now", _REAL_SEND_NOW)
    orchestrator.run(run.request_id)

    record = json.loads(_read(run.request_id).failure_json)
    assert record["team_notified"] is True
    assert [m["Subject"] for m in smtp] == ["Run failed: Halo Reformer Studio (analyzing)"]


# -- an explanation nobody could test never leads ---------------------------


def _every_tested_explanation_refuted(monkeypatch, crashes: str = "Mornings are empty") -> None:
    """A diagnosis in which the test of `crashes` never runs and every other
    test refutes its explanation."""
    from app.pipeline import diagnose

    def hypothesis_test(prompt):
        if crashes in prompt:
            return AiProviderError(SECRET_CAUSE)
        return {"verdict": "refuted", "because": "Their figures say otherwise.", "cites": []}

    _provider_by_template(monkeypatch, diagnose, {
        "diagnose.j2": _explanations(*EXPLANATIONS), "test_hypothesis.j2": hypothesis_test,
        "challenge.j2": {"kills": False, "because": "It held.", "weakness": ""}})


def test_an_untested_explanation_left_standing_alone_stops_the_diagnosis(monkeypatch):
    _every_tested_explanation_refuted(monkeypatch)
    request_id = _generating_row(diagnosis_json=_earlier_diagnosis())

    with pytest.raises(StageFailed) as stopped:
        _diagnose(request_id)

    assert stopped.value.stage == "diagnosing"
    assert stopped.value.cause == "the leading explanation could not be tested"
    # every test is on the ledger; no reviewer was paid to attack a guess
    assert sorted(_ledger(request_id)) == sorted([
        ("diagnose:1", True), ("test_hypothesis", False), ("test_hypothesis", True), ("test_hypothesis", True)])
    # and the diagnosis of the round before does not stand in for this one
    assert _read(request_id).diagnosis_json is None


def test_a_run_whose_only_standing_explanation_was_never_tested_fails_at_diagnosing(pipeline_with_only, monkeypatch):
    run = pipeline_with_only("diagnosing")
    _every_tested_explanation_refuted(monkeypatch)
    later = []
    monkeypatch.setattr("app.pipeline.decide.decide", lambda *a, **k: later.append("consulting"))

    orchestrator.run(run.request_id)

    row = _read(run.request_id)
    assert row.status == "failed" and json.loads(row.failure_json)["stage"] == "diagnosing"
    assert row.progress_detail == client_reason("diagnosing", True)
    assert later == [] and row.diagnosis_json is None
    assert [m[1] for m in run.outbox] == ["Run failed: Halo Reformer Studio (diagnosing)"]


def test_an_untested_explanation_that_does_not_lead_is_kept_as_it_was(monkeypatch):
    """One supported explanation leads; the untested one stays in the diagnosis,
    marked as never tested, and the diagnosis carries on."""
    request_id = _one_test_crashes(monkeypatch)

    result = _diagnose(request_id)

    leading = next(h for h in result["hypotheses"] if h["id"] == result["leading"])
    assert not leading["test"].get("not_tested")
    untested = [h for h in result["hypotheses"] if h["test"].get("not_tested")]
    assert [h["statement"] for h in untested] == ["Mornings are empty"]
    assert result["status"] == "survived"
