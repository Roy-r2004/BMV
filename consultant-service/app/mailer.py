"""Transactional mail from consulting@buildmyversion.com — the two
messages that close the review loop: "your engagement awaits review"
to the consultant, and "your engagement is ready" to the client.

Plain SMTP over SSL (Hostinger mailbox), configured entirely by env.
Fail-open and fire-and-forget: mail is a courtesy, never a dependency —
a down mail server must not fail an approval or a run. Every send runs
on a daemon thread so no request waits on SMTP.
"""

import logging
import smtplib
import threading
from email.message import EmailMessage
from email.utils import formataddr

from app.config import settings

logger = logging.getLogger("consultant.mailer")


def _configured() -> bool:
    return bool(settings.SMTP_PASSWORD and settings.SMTP_USER)

def _send(to: str, subject: str, body: str) -> None:
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
    except Exception as exc:
        logger.warning("mail failed open (%s -> %s): %s", subject, to, str(exc)[:200])


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
