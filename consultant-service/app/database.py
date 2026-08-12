from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")
# timeout: how long a writer waits on a lock instead of raising "database is
# locked" — this service has genuinely concurrent writers (request handlers +
# the pipeline's background thread logging usage per candidate).
connect_args = {"check_same_thread": False, "timeout": 15} if _is_sqlite else {}
# NullPool for SQLite: this database is shared across CONTAINERS over a bind
# mount, where a long-lived connection's view of the WAL index goes stale —
# an hour-old pooled connection in the studio service answered "Request not
# found" for rows that two freshly-opened connections (one in the very same
# container) could both read (session 36: /studio/91 and /92 404'd until the
# service restarted; the session-34 ledger reads that "looked like nothing
# was spent" were the same staleness). A fresh connection per checkout
# re-maps the WAL index and always sees the current database; the ~1ms open
# cost is nothing at this service's traffic.
engine_kwargs: dict = {"connect_args": connect_args}
if _is_sqlite:
    engine_kwargs["poolclass"] = NullPool
engine = create_engine(settings.DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.close()


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401 — register models on Base before create_all

    Base.metadata.create_all(bind=engine)
    _ensure_columns()


def _ensure_columns() -> None:
    """Minimal SQLite forward-migration: create_all() never alters existing
    tables, so columns added to a model after a dev DB was first created
    have to be ADD COLUMNed here. Idempotent and additive-only."""
    from sqlalchemy import inspect, text

    from app import models

    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name not in existing:
                    ddl = f"ALTER TABLE {table.name} ADD COLUMN {column.name} {column.type.compile(engine.dialect)}"
                    conn.execute(text(ddl))
