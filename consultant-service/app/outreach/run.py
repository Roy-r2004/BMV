"""One outreach run: fill the list, best first, under the monthly cap.

A run first queues businesses already written and waiting, best score first,
then searches city by city and kind by kind until the list holds the day's
number, checking the budget before every paid call. A business that was ever
queued, sent, skipped or answered is never queued again, and `find` never finds
it twice. Pressing "Fill" again the same day adds more; the automatic run
happens once a day. `purge` keeps only a name and a status for a business that
said no or was skipped more than 90 days ago.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, timedelta

from app.config import settings
from app.models import OutreachRun, Prospect
from app.outreach import image
from app.outreach.budget import can_spend
from app.outreach.find import SearchFailed, find
from app.outreach.learn import learn, learned
from app.outreach.read import read
from app.outreach.write import write

logger = logging.getLogger("consultant.outreach")

OUT_OF_BUDGET = "The monthly budget is used up"
NONE_LEFT = "No more new businesses were found today"
SEARCH_DOWN = "The web search could not be reached; try again later"
_SEARCH_AT_ONCE = 10
_CLEARED = ("website", "instagram", "phone", "what", "sources_json", "site_text", "signals_json", "reasons_json",
            "report_json", "dm_text", "followup_text", "sent_at", "opened_first_at")
running = threading.Lock()


def _queue(db, rows, day: date, room: int) -> int:
    n = 0
    for p in sorted(rows, key=lambda r: -r.score)[:room]:
        p.status, p.queued_on = "queued", day
        n += 1
    db.commit()
    return n


def fill(db, day: date, want: int | None = None, *, scheduled: bool = False) -> OutreachRun:
    want = want or settings.OUTREACH_DAILY
    r = db.query(OutreachRun).filter_by(day=day).one_or_none()
    if r is not None and scheduled:
        return r
    if r is None:
        r = OutreachRun(day=day, found=0, queued=0)
        db.add(r)
        db.commit()
    r.stopped_because = None
    queued, stopped = 0, None

    def take(p: Prospect) -> str | None:
        """Read, write and queue one business; why the run must stop, if it must."""
        nonlocal queued
        try:
            if p.status == "found" and read(db, p).status != "ready":
                return None
        except Exception:
            logger.exception("outreach: %s could not be read", p.name[:80])
            return None
        if not p.dm_text:
            if not learned(p):
                if not can_spend(db):
                    return OUT_OF_BUDGET
                learn(db, p)
            if not can_spend(db):
                return OUT_OF_BUDGET
            write(db, p)
        if p.status == "ready" and p.dm_text:
            queued += _queue(db, [p], day, want - queued)
        return None

    # what an earlier run left half done goes first: found but not read, read but not written
    leftovers = (db.query(Prospect).filter(Prospect.status.in_(("found", "ready")))
                 .order_by(Prospect.score.desc(), Prospect.id).all())
    for p in leftovers:
        if queued >= want:
            break
        stopped = take(p)
        if stopped:
            break
    searched, failures = 0, 0
    if queued < want and not stopped:
        for city in settings.OUTREACH_CITIES:
            for kind in settings.OUTREACH_KINDS:
                if queued >= want or stopped:
                    break
                if not can_spend(db):
                    stopped = OUT_OF_BUDGET
                    break
                try:
                    new = find(db, city, kind, min(_SEARCH_AT_ONCE, 2 * (want - queued)))
                    searched += 1
                except SearchFailed:
                    failures += 1
                    continue
                r.found += len(new)
                for p in new:
                    if queued >= want:
                        break
                    stopped = take(p)
                    if stopped:
                        break
            if queued >= want or stopped:
                break
        if queued < want and not stopped:
            stopped = SEARCH_DOWN if failures and not searched else NONE_LEFT
    r.queued += queued
    r.stopped_because = stopped
    r.finished_at = datetime.utcnow()
    db.commit()
    logger.info("outreach run %s: %s queued, %s found, %s", day, queued, r.found, stopped or "full")
    return r


def purge(db, now: datetime | None = None) -> int:
    """Forget all but the name and status of businesses that said no or were
    skipped more than 90 days ago, so they are still never offered again."""
    cutoff = (now or datetime.utcnow()) - timedelta(days=90)
    rows = db.query(Prospect).filter(Prospect.status.in_(("not_interested", "skip")),
                                     Prospect.updated_at < cutoff).all()
    n = 0
    for p in rows:
        if all(getattr(p, c) is None for c in _CLEARED):
            continue
        for c in _CLEARED:
            setattr(p, c, None)
        image.forget(p.token)
        n += 1
    db.commit()
    return n


def _seconds_until_six_in_dubai(now: datetime) -> float:
    """Dubai keeps UTC+4 all year, so 06:00 there is 02:00 UTC."""
    target = now.replace(hour=2, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _daily() -> None:
    from app.database import SessionLocal

    while True:
        time.sleep(_seconds_until_six_in_dubai(datetime.utcnow()))
        db = SessionLocal()
        try:
            with running:
                fill(db, (datetime.utcnow() + timedelta(hours=4)).date(), scheduled=True)
                purge(db)
        except Exception:
            logger.exception("the daily outreach run failed")
        finally:
            db.close()


def start_daily() -> threading.Thread | None:
    """The 06:00 run, when OUTREACH_AUTO is on."""
    if settings.OUTREACH_AUTO != "on":
        return None
    thread = threading.Thread(target=_daily, name="outreach-daily", daemon=True)
    thread.start()
    return thread
