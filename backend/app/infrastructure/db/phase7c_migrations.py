"""Additive Phase 7C promotion/rollback migrations (SQLite + Postgres)."""
from __future__ import annotations

from typing import Literal

from sqlalchemy import Engine, inspect, text

PHASE7C_SCHEMA_VERSION = "phase7c.1"
_DECISIONS = "preview_promotion_decisions"
_EVENTS = "preview_promotion_decision_status_events"


def phase7c_schema_version(bind: Engine) -> str | None:
    with bind.connect() as conn:
        if "preview_phase7c_schema_meta" not in inspect(conn).get_table_names():
            return None
        row = conn.execute(
            text(
                "SELECT schema_version FROM preview_phase7c_schema_meta "
                "ORDER BY id DESC LIMIT 1"
            )
        ).first()
        return None if row is None else str(row[0])


def _downgrade_guards(conn) -> None:
    tables = set(inspect(conn).get_table_names())
    if _EVENTS in tables:
        applied = conn.execute(
            text(
                f"SELECT COUNT(*) FROM {_EVENTS} "
                "WHERE status = 'applied'"
            )
        ).scalar()
        if applied:
            raise RuntimeError(
                "Phase 7C downgrade rejected: applied promotion/rollback events exist"
            )
    if "preview_serving_pointer_versions" in tables:
        current_v2 = conn.execute(
            text(
                "SELECT COUNT(*) FROM preview_serving_pointer_versions "
                "WHERE is_current = 1 AND target_kind = 'v2_candidate'"
            )
        ).scalar()
        if current_v2:
            raise RuntimeError(
                "Phase 7C downgrade rejected: current v2 serving pointer exists"
            )
    if _DECISIONS in tables:
        cols = {c["name"] for c in inspect(conn).get_columns(_DECISIONS)}
        if "expected_pointer_version" in cols:
            count = conn.execute(
                text(
                    f"SELECT COUNT(*) FROM {_DECISIONS} "
                    "WHERE expected_pointer_version IS NOT NULL "
                    "OR target_pointer_version IS NOT NULL"
                )
            ).scalar()
            if count:
                raise RuntimeError(
                    "Phase 7C downgrade rejected: decisions depend on Phase 7C fields"
                )


def _ensure_meta(conn, dialect: str) -> None:
    if dialect == "sqlite":
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS preview_phase7c_schema_meta (
                  id INTEGER PRIMARY KEY,
                  schema_version VARCHAR(64) NOT NULL,
                  created_at TEXT NOT NULL
                )
                """
            )
        )
    else:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS preview_phase7c_schema_meta (
                  id SERIAL PRIMARY KEY,
                  schema_version VARCHAR(64) NOT NULL,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
    existing = conn.execute(
        text(
            "SELECT COUNT(*) FROM preview_phase7c_schema_meta "
            "WHERE schema_version = :v"
        ),
        {"v": PHASE7C_SCHEMA_VERSION},
    ).scalar()
    if not existing:
        conn.execute(
            text(
                "INSERT INTO preview_phase7c_schema_meta "
                "(schema_version, created_at) VALUES (:v, CURRENT_TIMESTAMP)"
            ),
            {"v": PHASE7C_SCHEMA_VERSION},
        )


def _sqlite_add_decision_columns(conn) -> None:
    cols = {row[1] for row in conn.execute(text(f"PRAGMA table_info({_DECISIONS})"))}
    for name, ddl in (
        ("expected_pointer_version", "INTEGER"),
        ("target_pointer_version", "INTEGER"),
        ("idempotency_payload_sha256", "CHAR(64)"),
    ):
        if name not in cols:
            conn.execute(text(f"ALTER TABLE {_DECISIONS} ADD COLUMN {name} {ddl}"))


def _sqlite_relax_event_status_check(conn) -> None:
    """Rebuild status-events table to allow 'approved' (SQLite CHECK is immutable)."""
    # Detect whether approved is already accepted by attempting a no-op path:
    # if table empty of rows needing rebuild and constraint already wide, skip.
    # Always rebuild via rename when meta not yet at phase7c.1.
    conn.execute(text("PRAGMA foreign_keys=OFF"))
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS preview_promotion_decision_status_events_7c (
              id INTEGER PRIMARY KEY,
              decision_id INTEGER NOT NULL
                REFERENCES preview_promotion_decisions(id) ON DELETE RESTRICT,
              status VARCHAR(32) NOT NULL
                CHECK (status IN (
                  'requested','approved','rejected','cancelled',
                  'test_only_simulated','applied'
                )),
              actor_id VARCHAR(128) NOT NULL,
              reason TEXT NOT NULL,
              created_at TEXT NOT NULL,
              event_sha256 CHAR(64) NOT NULL UNIQUE
            )
            """
        )
    )
    conn.execute(
        text(
            """
            INSERT OR IGNORE INTO preview_promotion_decision_status_events_7c
            SELECT id, decision_id, status, actor_id, reason, created_at, event_sha256
            FROM preview_promotion_decision_status_events
            """
        )
    )
    conn.execute(text(f"DROP TABLE IF EXISTS {_EVENTS}"))
    conn.execute(
        text(
            f"ALTER TABLE preview_promotion_decision_status_events_7c "
            f"RENAME TO {_EVENTS}"
        )
    )
    # Restore append-only triggers for the rebuilt table
    conn.execute(
        text(
            f"""
            CREATE TRIGGER IF NOT EXISTS trg_{_EVENTS}_no_update
            BEFORE UPDATE ON {_EVENTS}
            BEGIN
              SELECT RAISE(ABORT, 'Phase 7A append-only: UPDATE forbidden on {_EVENTS}');
            END
            """
        )
    )
    conn.execute(
        text(
            f"""
            CREATE TRIGGER IF NOT EXISTS trg_{_EVENTS}_no_delete
            BEFORE DELETE ON {_EVENTS}
            BEGIN
              SELECT RAISE(ABORT, 'Phase 7A append-only: DELETE forbidden on {_EVENTS}');
            END
            """
        )
    )
    conn.execute(text("PRAGMA foreign_keys=ON"))


def migrate_phase7c_promotion(
    bind: Engine,
    *,
    direction: Literal["upgrade", "downgrade"] = "upgrade",
) -> None:
    dialect = bind.dialect.name
    if dialect not in ("sqlite", "postgresql"):
        raise RuntimeError(f"Phase 7C migration unsupported dialect: {dialect}")

    if direction == "downgrade":
        with bind.begin() as conn:
            _downgrade_guards(conn)
            if "preview_phase7c_schema_meta" in inspect(conn).get_table_names():
                conn.execute(text("DROP TABLE IF EXISTS preview_phase7c_schema_meta"))
        return

    if phase7c_schema_version(bind) == PHASE7C_SCHEMA_VERSION:
        return

    with bind.begin() as conn:
        tables = set(inspect(conn).get_table_names())
        if _DECISIONS not in tables or _EVENTS not in tables:
            raise RuntimeError("Phase 7C requires Phase 7A promotion tables")
        if dialect == "sqlite":
            conn.execute(text("PRAGMA foreign_keys=ON"))
            _sqlite_add_decision_columns(conn)
            _sqlite_relax_event_status_check(conn)
        else:
            conn.execute(
                text(
                    f"ALTER TABLE {_DECISIONS} "
                    "ADD COLUMN IF NOT EXISTS expected_pointer_version INTEGER"
                )
            )
            conn.execute(
                text(
                    f"ALTER TABLE {_DECISIONS} "
                    "ADD COLUMN IF NOT EXISTS target_pointer_version INTEGER"
                )
            )
            conn.execute(
                text(
                    f"ALTER TABLE {_DECISIONS} "
                    "ADD COLUMN IF NOT EXISTS idempotency_payload_sha256 CHAR(64)"
                )
            )
            conn.execute(
                text(
                    f"ALTER TABLE {_EVENTS} "
                    "DROP CONSTRAINT IF EXISTS ck_promotion_decision_event_status"
                )
            )
            conn.execute(
                text(
                    f"ALTER TABLE {_EVENTS} ADD CONSTRAINT "
                    "ck_promotion_decision_event_status CHECK (status IN ("
                    "'requested','approved','rejected','cancelled',"
                    "'test_only_simulated','applied'))"
                )
            )
        _ensure_meta(conn, dialect)


__all__ = [
    "PHASE7C_SCHEMA_VERSION",
    "migrate_phase7c_promotion",
    "phase7c_schema_version",
]
