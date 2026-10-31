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

    # 3. The client reads "we have been told" only if we were.
    if team_notified:
        record["team_notified"] = True
        record["reason"] = client_reason(stage, True)
        req = db.get(Request, request_id)
        if req is not None:
            req.failure_json = json.dumps(record)
            emit(db, request_id, "failed", _FAILED_LABEL, req.progress_pct, detail=record["reason"])
    logger.error("run %s failed at %s (team notified: %s): %s", request_id, stage, team_notified, cause)
    return team_notified


# One mail per kind of stall per window: a provider outage stalls every
# interview round of every client at once. Guarded because the endpoints that
# call `stall` run on a thread pool.
_last_stall_mail: dict[str, float] = {}
_stall_lock = threading.Lock()


def stall(kind: str, *, business: str | None, round: int | None, cause: str) -> bool:
    """Tell the team a step a client is waiting on has stalled, at most once per
    `kind` per `STALL_MAIL_WINDOW_SECONDS`. Returns whether a mail went out."""
    now = time.monotonic()
    with _stall_lock:
        last = _last_stall_mail.get(kind)
        if last is not None and now - last < settings.STALL_MAIL_WINDOW_SECONDS:
            return False
        # The window opens when we try, not when the mail lands: a mail server
        # that is down must not make every round wait on a 20s timeout.
        _last_stall_mail[kind] = now
    return mailer.notify_team_stall(kind, business, round, str(cause))
