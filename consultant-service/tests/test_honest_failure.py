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
    # one module, so that the stage after it has something to shape
    "decomposing": ("app.pipeline.decompose.decompose_business",
                    lambda *a, **k: {"business_case": {}, "modules": [{"id": "booking", "name": "Booking", "purpose": "Book classes"}]}),
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
    returns either."""
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
        return {"choices": [{"message": {"content": json.dumps(reply)}}], "usage": {}}

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
