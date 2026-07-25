"""Additive Phase 7E ops dashboard / alert migrations."""
from __future__ import annotations

from typing import Literal

from sqlalchemy import Engine, inspect, text

PHASE7E_SCHEMA_VERSION = "phase7e.1"
_ALERTS = "preview_rollout_alert_events"
_STATUS = "preview_rollout_alert_status_events"
_META = "preview_phase7e_schema_meta"


def phase7e_schema_version(bind: Engine) -> str | None:
    with bind.connect() as conn:
        if _META not in inspect(conn).get_table_names():
            return None
        row = conn.execute(
            text(f"SELECT schema_version FROM {_META} ORDER BY id DESC LIMIT 1")
        ).first()
        return None if row is None else str(row[0])


def _downgrade_guards(conn) -> None:
    tables = set(inspect(conn).get_table_names())
    if _ALERTS in tables:
        count = conn.execute(text(f"SELECT COUNT(*) FROM {_ALERTS}")).scalar()
        if count:
            raise RuntimeError(
                "Phase 7E downgrade rejected: alert rows exist"
            )
    if _STATUS in tables:
        count = conn.execute(text(f"SELECT COUNT(*) FROM {_STATUS}")).scalar()
        if count:
            raise RuntimeError(
                "Phase 7E downgrade rejected: alert status history exists"
            )


def _ensure_meta(conn, dialect: str) -> None:
    if dialect == "sqlite":
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {_META} (
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
                f"""
                CREATE TABLE IF NOT EXISTS {_META} (
                  id SERIAL PRIMARY KEY,
                  schema_version VARCHAR(64) NOT NULL,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
    existing = conn.execute(
        text(f"SELECT COUNT(*) FROM {_META} WHERE schema_version = :v"),
        {"v": PHASE7E_SCHEMA_VERSION},
    ).scalar()
    if not existing:
        conn.execute(
            text(
                f"INSERT INTO {_META} (schema_version, created_at) "
                "VALUES (:v, CURRENT_TIMESTAMP)"
            ),
            {"v": PHASE7E_SCHEMA_VERSION},
        )


def _sqlite_append_only_triggers(conn, table: str) -> None:
    for action, op in (("UPDATE", "UPDATE"), ("DELETE", "DELETE")):
        conn.execute(
            text(
                f"""
                CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{action.lower()}
                BEFORE {op} ON {table}
                BEGIN
                  SELECT RAISE(ABORT,
                    'Phase 7E append-only: {op} forbidden on {table}');
                END
                """
            )
        )


def _create_alerts_sqlite(conn) -> None:
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_ALERTS} (
              id INTEGER PRIMARY KEY,
              alert_class VARCHAR(64) NOT NULL,
              severity VARCHAR(16) NOT NULL,
              scope_key VARCHAR(128) NOT NULL,
              source_event_type VARCHAR(64) NOT NULL,
              source_event_id VARCHAR(128) NOT NULL,
              source_sha256 CHAR(64) NOT NULL,
              policy_revision VARCHAR(64) NOT NULL,
              payload_json TEXT NOT NULL,
              payload_sha256 CHAR(64) NOT NULL,
              dedupe_key VARCHAR(256) NOT NULL UNIQUE,
              created_at TEXT NOT NULL,
              alert_sha256 CHAR(64) NOT NULL UNIQUE
            )
            """
        )
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_rollout_alert_class "
            f"ON {_ALERTS}(alert_class)"
        )
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_rollout_alert_severity "
            f"ON {_ALERTS}(severity)"
        )
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_rollout_alert_created "
            f"ON {_ALERTS}(created_at)"
        )
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_rollout_alert_scope "
            f"ON {_ALERTS}(scope_key)"
        )
    )
    _sqlite_append_only_triggers(conn, _ALERTS)


def _create_status_sqlite(conn) -> None:
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_STATUS} (
              id INTEGER PRIMARY KEY,
              alert_id INTEGER NOT NULL
                REFERENCES {_ALERTS}(id) ON DELETE RESTRICT,
              status VARCHAR(32) NOT NULL,
              actor_id VARCHAR(128) NOT NULL,
              reason TEXT NOT NULL,
              ticket_ref VARCHAR(128),
              created_at TEXT NOT NULL,
              event_sha256 CHAR(64) NOT NULL UNIQUE
            )
            """
        )
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_rollout_alert_status_alert "
            f"ON {_STATUS}(alert_id, created_at)"
        )
    )
    _sqlite_append_only_triggers(conn, _STATUS)


def _create_alerts_postgres(conn) -> None:
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_ALERTS} (
              id SERIAL PRIMARY KEY,
              alert_class VARCHAR(64) NOT NULL,
              severity VARCHAR(16) NOT NULL,
              scope_key VARCHAR(128) NOT NULL,
              source_event_type VARCHAR(64) NOT NULL,
              source_event_id VARCHAR(128) NOT NULL,
              source_sha256 CHAR(64) NOT NULL,
              policy_revision VARCHAR(64) NOT NULL,
              payload_json TEXT NOT NULL,
              payload_sha256 CHAR(64) NOT NULL,
              dedupe_key VARCHAR(256) NOT NULL UNIQUE,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              alert_sha256 CHAR(64) NOT NULL UNIQUE
            )
            """
        )
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_rollout_alert_class "
            f"ON {_ALERTS}(alert_class)"
        )
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_rollout_alert_severity "
            f"ON {_ALERTS}(severity)"
        )
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_rollout_alert_created "
            f"ON {_ALERTS}(created_at)"
        )
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_rollout_alert_scope "
            f"ON {_ALERTS}(scope_key)"
        )
    )


def _create_status_postgres(conn) -> None:
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_STATUS} (
              id SERIAL PRIMARY KEY,
              alert_id INTEGER NOT NULL
                REFERENCES {_ALERTS}(id) ON DELETE RESTRICT,
              status VARCHAR(32) NOT NULL,
              actor_id VARCHAR(128) NOT NULL,
              reason TEXT NOT NULL,
              ticket_ref VARCHAR(128),
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              event_sha256 CHAR(64) NOT NULL UNIQUE
            )
            """
        )
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_rollout_alert_status_alert "
            f"ON {_STATUS}(alert_id, created_at)"
        )
    )


def migrate_phase7e_ops(
    bind: Engine,
    *,
    direction: Literal["upgrade", "downgrade"] = "upgrade",
) -> None:
    dialect = bind.dialect.name
    if dialect not in ("sqlite", "postgresql"):
        raise RuntimeError(f"Phase 7E migration unsupported dialect: {dialect}")

    if direction == "downgrade":
        with bind.begin() as conn:
            _downgrade_guards(conn)
            if _META in inspect(conn).get_table_names():
                conn.execute(text(f"DROP TABLE IF EXISTS {_META}"))
        return

    if phase7e_schema_version(bind) == PHASE7E_SCHEMA_VERSION:
        return

    with bind.begin() as conn:
        tables = set(inspect(conn).get_table_names())
        if "preview_breaker_metric_samples" not in tables:
            raise RuntimeError("Phase 7E requires Phase 7D metric sample tables")
        if dialect == "sqlite":
            conn.execute(text("PRAGMA foreign_keys=ON"))
            _create_alerts_sqlite(conn)
            _create_status_sqlite(conn)
        else:
            _create_alerts_postgres(conn)
            _create_status_postgres(conn)
        _ensure_meta(conn, dialect)


__all__ = [
    "PHASE7E_SCHEMA_VERSION",
    "migrate_phase7e_ops",
    "phase7e_schema_version",
]
