"""Where a run fails, and what everyone is told.

A stage that cannot do its work raises `StageFailed`. The orchestrator catches
it in one place and calls `fail_run`, which stops the run, tells the client in
plain words, emails the team and records the facts. Nothing canned ever stands
in for work we did not do.

Two rules shape the wording:
  - the client is told "we have been told" only when the email really went out;
  - the raw cause (a provider error can carry a URL or a key fragment) goes to
    the team's email and the run's `failure_json`, never to a screen, a subject
    line or `progress_detail`.
"""

import json
import logging
import threading
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import mailer
from app.config import settings
from app.models import Request
from app.pipeline._shared import emit

logger = logging.getLogger("consultant.failure")

#: Each stage, as the work we were doing; it reads after "we were". Keyed by the
#: stage ids the orchestrator emits, plus `email`, the last thing a run does.
STAGE_WORK: dict[str, str] = {
    "reading": "reading the file you sent",
    "researching": "reading up on your business",
    "analyzing": "analyzing your business",
    "capacity": "working out your capacity",
    "diagnosing": "working out what is actually wrong",
    "challenging": "testing that conclusion against the alternatives",
    "consulting": "working out what would actually help",
    "answering": "writing your answer",
    "planning": "planning your roles and features",
    "decomposing": "breaking your business down into its parts",
    "shaping": "mapping your journey, scoreboard and procedures",
    "blueprint": "writing your blueprint",
    "technical": "writing your technical plan",
    "playbook": "writing your operations manual",
    "roadmap": "writing your implementation roadmap",
    "storyline": "writing the plan summary",
    "quality": "checking the quality of your documents",
    "screens": "drawing your product screens",
    "email": "emailing you your documents",
}

_UNKNOWN_WORK = "working on your engagement"
_FAILED_LABEL = "Our side failed and the run stopped"


class StageFailed(Exception):
    """A stage could not do its work. `stage` is a key of `STAGE_WORK`; `cause`
    is the text of what went wrong, for the team and the record, never the
    client."""

    def __init__(self, stage: str, cause: str | BaseException):
        text = str(cause)
        if not text and isinstance(cause, BaseException):
            text = type(cause).__name__
        self.stage = stage
        self.cause = text[: mailer.CAUSE_MAX]
        super().__init__(f"{stage}: {self.cause}")


def client_reason(stage: str, team_notified: bool) -> str:
    """What the client reads when a run stops. It names the work, not the
    stage, and says the team knows only if the team was in fact told."""
    reason = f"Our side failed while we were {STAGE_WORK.get(stage, _UNKNOWN_WORK)}."
    if team_notified:
        reason += " We have been told and are looking into it."
    return reason


def fail_run(db: Session, request_id: int, stage: str, cause: str) -> bool:
    """Stop the run, record why, and email the team. Returns whether the team
    was told, which is what the client's sentence is written from.

    Three phases, in this order, because the mail is slow (up to ~20s per SMTP
    step) and the run must never read "generating" while we wait on it:
      1. stop the run and commit, with wording that claims nobody was told;
      2. email the team;
      3. only if that mail went, upgrade the wording to say so."""
    # The exception that brought us here may have come from a commit; the
    # session is then unusable until it is rolled back, and the run would
    # stay "generating" for good.
    db.rollback()
    cause = str(cause)[: mailer.CAUSE_MAX]
    req = db.get(Request, request_id)
    if req is None:
        logger.warning("run %s failed at %s but its row is gone: %s", request_id, stage, cause[:200])
        return False
    ref = req.public_id or request_id
    business_name = req.business_name or ""

    # 1. Stopped, and the facts on record, before anything slow. `emit` commits
    # these fields along with the label.
    record = {
        "stage": stage,
        "at": datetime.now(timezone.utc).isoformat(),
        "cause": cause,
        "team_notified": False,
        "reason": client_reason(stage, False),
    }
    req.status = "failed"
    req.is_failed = True
    req.is_generating = False
    req.failure_json = json.dumps(record)
    emit(db, request_id, "failed", _FAILED_LABEL, req.progress_pct, detail=record["reason"])

    # 2. Tell the team. Nothing about telling them may undo the stop above.
    try:
        team_notified = mailer.notify_team_failure(ref, business_name, stage, cause)
    except Exception:
        logger.exception("run %s: could not tell the team it failed", request_id)
        team_notified = False

    # 3. The client reads "we have been told" only if we were. The mail was
    # slow, so the client may have pushed back and restarted the run meanwhile:
    # the row then belongs to the new run, and this failure's wording is not
    # written over it. Whatever goes wrong here, the answer below is still true
    # and still returned.
    if team_notified:
        try:
            req = db.get(Request, request_id, populate_existing=True)
            if req is not None and req.status == "failed":
                record["team_notified"] = True
                record["reason"] = client_reason(stage, True)
                req.failure_json = json.dumps(record)
                emit(db, request_id, "failed", _FAILED_LABEL, req.progress_pct, detail=record["reason"])
        except Exception:
            db.rollback()
            logger.exception("run %s: the team was told, but we could not upgrade the client's notice to say so", request_id)
    logger.error("run %s failed at %s (team notified: %s): %s", request_id, stage, team_notified, cause)
    return team_notified


#: What the client reads of a run a restart stopped. A restart is ours, and the
#: work it stopped is the whole engagement, not one stage.
RESTART_REASON = "Our service restarted while your engagement was being written."
RESTART_CAUSE = "the service restarted while the run was in flight"


def _restart_reason(team_notified: bool) -> str:
    return RESTART_REASON + (" We have been told and are looking into it." if team_notified else "")


def fail_interrupted_runs(db: Session) -> list[int]:
    """Stop every run a restart left generating, and record why. Returns their
    ids, for `tell_team_of_restart`.

    A run lives on a daemon thread, so a restart (a deploy, a crash, a dev
    reload) kills it silently and leaves it "generating" for good. This is the
    first phase of `fail_run` for each of them: stopped, the facts on record,
    and wording that claims nobody was told, all committed before anything
    slow."""
    stranded = db.query(Request).filter(Request.is_generating.is_(True)).all()
    ids = []
    for req in stranded:
        record = {
            "stage": req.stage or "",
            "at": datetime.now(timezone.utc).isoformat(),
            "cause": RESTART_CAUSE,
            "team_notified": False,
            "reason": _restart_reason(False),
        }
        req.status = "failed"
        req.is_failed = True
        req.is_generating = False
        req.failure_json = json.dumps(record)
        req.stage = "failed"
        req.stage_label = _FAILED_LABEL
        req.progress_detail = record["reason"]
        ids.append(req.id)
    if ids:
        db.commit()
        logger.error("a restart stopped %d run(s): %s", len(ids), ids)
    return ids


def tell_team_of_restart(request_ids: list[int]) -> bool:
    """Phases two and three of the restart sweep: ONE mail to the team for the
    whole sweep, then, only if it went, the client's notice upgraded to say so
    on each run still stopped by it. Opens its own session, because it runs on
    a thread of its own so that startup never waits on SMTP. Never raises."""
    if not request_ids:
        return False
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        rows = [db.get(Request, rid) for rid in request_ids]
        rows = [r for r in rows if r is not None]
        records = {r.id: r.failure_json for r in rows}
        runs = [(r.public_id or r.id, r.business_name or "") for r in rows]
        try:
            team_notified = mailer.notify_team_restart(runs)
        except Exception:
            logger.exception("could not tell the team which runs a restart stopped")
            team_notified = False
        if not team_notified:
            return False
        for rid, before in records.items():
            try:
                req = db.get(Request, rid, populate_existing=True)
                # a run the client has started again since belongs to the new run
                if req is None or req.status != "failed" or req.failure_json != before:
                    continue
                record = json.loads(before)
                record["team_notified"] = True
                record["reason"] = _restart_reason(True)
                req.failure_json = json.dumps(record)
                req.progress_detail = record["reason"]
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("run %s: the team was told of the restart, but the notice was not upgraded", rid)
        return True
    except Exception:
        logger.exception("the restart sweep could not finish telling the team")
        return False
    finally:
        db.close()


# One mail per kind of stall per window: a provider outage stalls every
# interview round of every client at once. Each kind maps to (when its window
# opened, whether the mail that opened it went). Guarded because the endpoints
# that call `stall` run on a thread pool.
_last_stall_mail: dict[str, tuple[float, bool]] = {}
_stall_lock = threading.Lock()


def _stall(kind: str, business: str | None, round: int | None, cause: str) -> tuple[bool, bool]:
    """(this call sent a mail, the team has been told of this outage)."""
    now = time.monotonic()
    with _stall_lock:
        window = _last_stall_mail.get(kind)
        if window is not None and now - window[0] < settings.STALL_MAIL_WINDOW_SECONDS:
            return False, window[1]
        # The window opens when we try, not when the mail lands: a mail server
        # that is down must not make every round wait on a 20s timeout. Until
        # the mail lands nobody can say the team was told.
        _last_stall_mail[kind] = (now, False)
    sent = mailer.notify_team_stall(kind, business, round, str(cause))
    with _stall_lock:
        if _last_stall_mail.get(kind) == (now, False):
            _last_stall_mail[kind] = (now, sent)
    return sent, sent


def stall(kind: str, *, business: str | None, round: int | None, cause: str) -> bool:
    """Tell the team a step a client is waiting on has stalled, at most once per
    `kind` per `STALL_MAIL_WINDOW_SECONDS`. Returns whether a mail went out."""
    return _stall(kind, business, round, cause)[0]


def report_stall(kind: str, *, business: str | None, round: int | None, cause: str) -> bool:
    """`stall`, answering the question a client's sentence is written from: has
    the team been told of this outage? True when this call sent the mail, and
    also when it was throttled behind a mail that went. False when the mail
    could not be sent (mail unconfigured, server down), when the mail that
    opened the window is still on the wire, and so for every follower inside a
    window whose mail never went: the next window tries again."""
    return _stall(kind, business, round, cause)[1]
