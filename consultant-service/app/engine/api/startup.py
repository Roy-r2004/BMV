"""The startup sweep (design 16.3, MF3.2).

`engine_startup()` is called from main.py's `on_startup` AFTER `init_db()`,
and this module deliberately registers no startup handler of its own. The
reason is an ordering the router cannot control: FastAPI runs a router's
startup handlers before the ones the application registers afterwards, so a
sweep hung on the router would query `engagements` on a fresh database
before `create_all` had made the table - the service would crash on its
first boot and only on its first boot. The sweep is therefore a plain
function main.py calls in the order it wants, and that call site is the law
(`tests/engine/test_engine_api.py::test_a_fresh_database_boots_with_every_engine_table`).

The sweep itself mirrors `main._fail_stranded_requests`: analysis runs on a
daemon thread, so a restart - including a uvicorn dev reload - kills it
silently and leaves the engagement at is_working=True forever. A stranded
engagement becomes a clean, retryable failure instead of an eternal spinner.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("consultant.engine.startup")

# What a swept engagement is left saying. The client sees a failure they can
# act on; nothing pretends the interrupted analysis produced anything.
STRANDED_LABEL = "Analysis was interrupted by a service restart"


def engine_startup(session_factory=None) -> int:
    """Sweep engagements stranded at is_working=True into `failed`. Returns
    the number swept.

    Not defensive about a missing table: this runs after init_db() by
    contract, and swallowing an OperationalError here would hide exactly the
    ordering bug MF3.2 names - a fresh database that boots into a crash.
    """
    from app.engine.persistence.models import Engagement

    if session_factory is None:
        from app.database import SessionLocal

        session_factory = SessionLocal

    db = session_factory()
    try:
        stranded = db.query(Engagement).filter(Engagement.is_working.is_(True)).all()
        for row in stranded:
            row.status = "failed"
            row.is_failed = True
            row.is_working = False
            row.stage = "failed"
            row.stage_label = STRANDED_LABEL
        if stranded:
            db.commit()
            logger.info("engine startup swept %d stranded engagement(s)", len(stranded))
        return len(stranded)
    finally:
        db.close()


__all__ = ["STRANDED_LABEL", "engine_startup"]
