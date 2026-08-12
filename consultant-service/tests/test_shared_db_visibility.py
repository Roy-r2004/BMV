"""Pins the cross-container visibility contract for the shared SQLite file.

The consultant DB lives on a bind mount and is opened by at least three
kinds of process at once: the studio service (long-lived), bakeoff cells
(one-shot containers), and the e2e script. Session 36 measured what happens
when a long-lived connection keeps its stale view of the WAL index: the
service answered "Request not found" for /studio/91 and /studio/92 while a
fresh connection — opened inside the SAME container — read both rows fine.
Session 34's ledger bracket reads that "looked like nothing was spent" were
the same failure. The cure is structural, not operational: never hold a
SQLite connection longer than one checkout.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.pool import NullPool

from app.database import engine


def test_sqlite_engine_never_pools_connections():
    """A pooled connection's WAL-index view goes stale across the bind
    mount; a fresh connection per checkout always sees the current file.
    If this pin fails because someone wants pooling back, the /studio 404
    evidence above is what has to be re-litigated."""
    assert engine.url.get_backend_name() == "sqlite", "this pin is about the sqlite deployment"
    assert isinstance(engine.pool, NullPool), (
        "the sqlite engine must use NullPool — a pooled connection served "
        "'Request not found' for rows every fresh connection could read"
    )


def test_fresh_connections_still_get_the_wal_pragmas():
    """NullPool means the connect-event pragmas run on every checkout —
    they must still be applied, or concurrent writers lose their
    busy_timeout and start raising 'database is locked'."""
    with engine.connect() as conn:
        mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
        timeout = conn.exec_driver_sql("PRAGMA busy_timeout").scalar()
    assert str(mode).lower() == "wal"
    assert int(timeout) >= 15000
