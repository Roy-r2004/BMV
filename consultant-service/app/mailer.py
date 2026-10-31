"""Transactional mail from consulting@buildmyversion.com — the two
messages that close the review loop: "your engagement awaits review"
to the consultant, and "your engagement is ready" to the client.

Plain SMTP over SSL (Hostinger mailbox), configured entirely by env.
Fail-open: mail is a courtesy, never a dependency — a down mail server
must not fail an approval or a run, and no send raises.

There are two ways to send. `send_async` is fire-and-forget on a daemon
thread, so no request waits on SMTP; the reviewer, go-ahead and released
notices use it. `send_now` runs on the calling thread and says whether the
mail went, which `notify_owner_ready` and the `notify_team_*` functions
return. Each SMTP step (connect, login, send) can take up to ~20s, so call
those from a background thread, or throttled, never per request.
"""

import logging
import smtplib
import threading
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr

from app.config import settings

logger = logging.getLogger("consultant.mailer")


def _configured() -> bool:
    return bool(settings.SMTP_PASSWORD and settings.SMTP_USER)

def send_now(to: str | None, subject: str, body: str) -> bool:
    """Send on the calling thread and say whether it went. For the one place a
    caller must know the answer — a run that stopped tells the client "we have
    been told" only if this returned True. Never raises: False when there is no
    one to send to, mail is unconfigured, or the server refused."""
    if not to or not _configured():
        return False
    try:
        msg = EmailMessage()
        msg["From"] = formataddr(("Build My Version", settings.SMTP_USER))
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as smtp:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(msg)
        logger.info("mail sent: %s -> %s", subject, to)
        return True
    except Exception as exc:
        logger.warning("mail failed open (%s -> %s): %s", subject, to, str(exc)[:200])
        return False


def _send(to: str, subject: str, body: str) -> None:
    send_now(to, subject, body)


def send_async(to: str | None, subject: str, body: str) -> None:
    if not to or not _configured():
        return
    threading.Thread(target=_send, args=(to, subject, body), daemon=True).start()


def _run_url(ref: str | int) -> str:
    """A run's address. Slug refs land on /engagements/<slug> (the private
    spelling); numeric ids keep the legacy /demo/<id> spelling."""
    path = f"demo/{ref}" if str(ref).isdigit() else f"engagements/{ref}"
    return f"https://buildmyversion.com/{path}"


def notify_reviewer_pending(ref: str | int, business_name: str) -> None:
    link = f"{_run_url(ref)}?review={settings.REVIEW_TOKEN}"
    send_async(
        settings.SMTP_USER,
        f"An engagement awaits your review — {business_name}",
        (
            f"{business_name} finished generating and is waiting for your signature.\n\n"
            f"Review and release:\n{link}\n\n"
            f"The quality bench's report is in the review bar.\n"
        ),
    )


def enabled() -> bool:
    """Whether a promise to email someone can actually be kept. The building
    screen only says "we'll email you" when this is true."""
    return _configured()


def notify_owner_ready(ref: str | int, owner_email: str | None, business_name: str) -> bool:
    return send_now(
        owner_email,
        f"{business_name} — your answer and plans are ready",
        (
            f"The answer for {business_name} is ready, and so is every plan behind it: "
            f"the blueprint, the technical plan, the operations manual, the product screens "
            f"and the implementation roadmap.\n\n"
            f"Open it here (sign in with this address):\n"
            f"{_run_url(ref)}\n\n"
            f"We do the work. The only thing left for you is a few decisions, "
            f"on the page — each one is a tap.\n\n"
            f"Anything we got wrong? Just reply to this email.\n\n"
            f"— Build My Version · buildmyversion.com\n"
        ),
    )


def notify_team_go_ahead(ref: str | int, business_name: str, owner_email: str | None,
                         choices: dict | None) -> None:
    """The owner pressed go ahead on the roadmap: tell us, with their calls."""
    lines = "\n".join(f"- {k}: {v}" for k, v in (choices or {}).items()) or "- (no decisions answered)"
    send_async(
        settings.SMTP_USER,
        f"Go ahead — {business_name}",
        (
            f"{owner_email or 'The owner'} asked us to build {business_name}.\n\n"
            f"The engagement:\n{_run_url(ref)}\n\n"
            f"Their decisions:\n{lines}\n"
        ),
    )


def notify_owner_released(ref: str | int, owner_email: str | None, business_name: str, concept: str | None) -> None:
    title = concept or business_name
    send_async(
        owner_email,
        f"{title} — your engagement is ready",
        (
            f"Good news: your engagement for {business_name} has been personally reviewed "
            f"and released by your consultant.\n\n"
            f"Open it here (sign in with this address):\n"
            f"{_run_url(ref)}\n\n"
            f"Inside you'll find your product screens, the Blueprint, the Technical Plan, "
            f"the Operations Manual, and the downloads — the three-volume PDF set and the deck.\n\n"
            f"Questions, corrections, or ready to talk about building it? Just reply to this email.\n\n"
            f"— Build My Version · buildmyversion.com\n"
        ),
    )


# The cause of a failure can be a provider error, with URLs or key fragments in
# it. It belongs in the team's inbox and the run's record, so it is cut to a
# length a person reads, and it never goes in a subject line.
CAUSE_MAX = 500


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def notify_team_failure(ref: str | int, business_name: str, stage: str, cause: str) -> bool:
    """A run stopped because our side broke. Sent on the calling thread so the
    caller learns whether the team really was told."""
    return send_now(
        settings.SMTP_USER,
        f"Run failed: {business_name} ({stage})",
        (
            f"The run for {business_name} stopped at the {stage} stage.\n\n"
            f"The run:\n{_run_url(ref)}\n\n"
            f"Stage: {stage}\n"
            f"Time: {_now_utc()}\n\n"
            f"Cause:\n{cause[:CAUSE_MAX]}\n"
        ),
    )


def notify_team_restart(runs: list[tuple[str | int, str]]) -> bool:
    """The service restarted with runs in flight, and they were stopped. One
    mail for the whole sweep, however many there were: (ref, business name)
    for each. Never raises."""
    if not runs:
        return False
    lines = "\n".join(f"- {name or '(no name yet)'}: {_run_url(ref)}" for ref, name in runs)
    count = f"{len(runs)} run{'' if len(runs) == 1 else 's'}"
    return send_now(
        settings.SMTP_USER,
        f"Service restarted: {count} stopped",
        (
            f"The service restarted while {count} {'was' if len(runs) == 1 else 'were'} being written. "
            f"Each was stopped and its client told it did not finish.\n\n"
            f"Time: {_now_utc()}\n\n"
            f"The runs:\n{lines}\n"
        ),
    )


def notify_team_stall(kind: str, business_name: str | None, round: int | None, cause: str) -> bool:
    """A step the client is waiting on could not be answered (an interview
    round, say). One mail per kind per window is the caller's business; this
    only writes and sends it."""
    who = f" ({business_name})" if business_name else ""
    at_round = f"Round: {round}\n" if round is not None else ""
    return send_now(
        settings.SMTP_USER,
        f"Stalled: {kind}{who}",
        (
            f"The {kind} step stalled{who}.\n\n"
            f"{at_round}"
            f"Time: {_now_utc()}\n\n"
            f"Cause:\n{cause[:CAUSE_MAX]}\n"
        ),
    )
