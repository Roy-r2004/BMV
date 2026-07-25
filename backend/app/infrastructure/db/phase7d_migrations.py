"""Additive Phase 7D circuit-breaker / auto-rollback migrations."""
from __future__ import annotations

from typing import Literal

from sqlalchemy import Engine, inspect, text

PHASE7D_SCHEMA_VERSION = "phase7d.1"
_SAMPLES = "preview_breaker_metric_samples"
_CLAIMS = "preview_breaker_auto_rollback_claims"
_META = "preview_phase7d_schema_meta"


def phase7d_schema_version(bind: Engine) -> str | None:
    with bind.connect() as conn:
        if _META not in inspect(conn).get_table_names():
            return None
        row = conn.execute(
            text(
                f"SELECT schema_version FROM {_META} ORDER BY id DESC LIMIT 1"
            )
        ).first()
        return None if row is None else str(row[0])


def _downgrade_guards(conn) -> None:
    tables = set(inspect(conn).get_table_names())
    if "preview_circuit_breaker_states" in tables:
        transitions = conn.execute(
            text(
                "SELECT COUNT(*) FROM preview_circuit_breaker_states "
                "WHERE state IN ('open','half_open','closed')"
            )
        ).scalar()
        if transitions and int(transitions) > 1:
            raise RuntimeError(
                "Phase 7D downgrade rejected: breaker transition history exists"
            )
    if _SAMPLES in tables:
        count = conn.execute(text(f"SELECT COUNT(*) FROM {_SAMPLES}")).scalar()
        if count:
            raise RuntimeError(
                "Phase 7D downgrade rejected: metric samples exist"
            )
    if _CLAIMS in tables:
        count = conn.execute(text(f"SELECT COUNT(*) FROM {_CLAIMS}")).scalar()
        if count:
            raise RuntimeError(
                "Phase 7D downgrade rejected: auto-rollback claims exist"
            )
    if "preview_promotion_decision_status_events" in tables:
        auto = conn.execute(
            text(
                "SELECT COUNT(*) FROM preview_rollout_audit_events "
                "WHERE event_type = 'breaker_auto_rollback_applied'"
            )
        ).scalar()
        if auto:
            raise RuntimeError(
                "Phase 7D downgrade rejected: automatic rollback audits exist"
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
        {"v": PHASE7D_SCHEMA_VERSION},
    ).scalar()
    if not existing:
        conn.execute(
            text(
                f"INSERT INTO {_META} (schema_version, created_at) "
                "VALUES (:v, CURRENT_TIMESTAMP)"
            ),
            {"v": PHASE7D_SCHEMA_VERSION},
        )


def _create_samples_sqlite(conn) -> None:
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_SAMPLES} (
              id INTEGER PRIMARY KEY,
              event_at TEXT NOT NULL,
              metric_class VARCHAR(64) NOT NULL,
              outcome VARCHAR(32) NOT NULL,
              request_id INTEGER REFERENCES requests(id) ON DELETE SET NULL,
              decision_id INTEGER
                REFERENCES preview_promotion_decisions(id) ON DELETE SET NULL,
              pointer_version INTEGER,
              duration_ms FLOAT,
              policy_revision VARCHAR(64) NOT NULL,
              source_event_id VARCHAR(128),
              source_event_hash CHAR(64) NOT NULL,
              metadata_json TEXT NOT NULL,
              metadata_sha256 CHAR(64) NOT NULL,
              created_at TEXT NOT NULL,
              sample_sha256 CHAR(64) NOT NULL UNIQUE
            )
            """
        )
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_breaker_sample_event_at "
            f"ON {_SAMPLES}(event_at)"
        )
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_breaker_sample_class_event "
            f"ON {_SAMPLES}(metric_class, event_at)"
        )
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_breaker_sample_request_event "
            f"ON {_SAMPLES}(request_id, event_at)"
        )
    )
    conn.execute(
        text(
            f"CREATE UNIQUE INDEX IF NOT EXISTS uq_breaker_sample_source "
            f"ON {_SAMPLES}(source_event_hash)"
        )
    )
    for action, op in (("UPDATE", "UPDATE"), ("DELETE", "DELETE")):
        conn.execute(
            text(
                f"""
                CREATE TRIGGER IF NOT EXISTS trg_{_SAMPLES}_no_{action.lower()}
                BEFORE {op} ON {_SAMPLES}
                BEGIN
                  SELECT RAISE(ABORT,
                    'Phase 7D append-only: {op} forbidden on {_SAMPLES}');
                END
                """
            )
        )


def _create_claims_sqlite(conn) -> None:
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_CLAIMS} (
              id INTEGER PRIMARY KEY,
              open_state_id INTEGER NOT NULL
                REFERENCES preview_circuit_breaker_states(id) ON DELETE RESTRICT,
              request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
              decision_id INTEGER
                REFERENCES preview_promotion_decisions(id) ON DELETE SET NULL,
              expected_pointer_version INTEGER NOT NULL,
              target_pointer_version INTEGER NOT NULL,
              idempotency_key VARCHAR(256) NOT NULL UNIQUE,
              claim_sha256 CHAR(64) NOT NULL UNIQUE,
              status VARCHAR(32) NOT NULL,
              created_at TEXT NOT NULL,
              UNIQUE(open_state_id, request_id)
            )
            """
        )
    )
    for action, op in (("UPDATE", "UPDATE"), ("DELETE", "DELETE")):
        conn.execute(
            text(
                f"""
                CREATE TRIGGER IF NOT EXISTS trg_{_CLAIMS}_no_{action.lower()}
                BEFORE {op} ON {_CLAIMS}
                BEGIN
                  SELECT RAISE(ABORT,
                    'Phase 7D append-only: {op} forbidden on {_CLAIMS}');
                END
                """
            )
        )


def _create_samples_postgres(conn) -> None:
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_SAMPLES} (
              id SERIAL PRIMARY KEY,
              event_at TIMESTAMPTZ NOT NULL,
              metric_class VARCHAR(64) NOT NULL,
              outcome VARCHAR(32) NOT NULL,
              request_id INTEGER REFERENCES requests(id) ON DELETE SET NULL,
              decision_id INTEGER
                REFERENCES preview_promotion_decisions(id) ON DELETE SET NULL,
              pointer_version INTEGER,
              duration_ms DOUBLE PRECISION,
              policy_revision VARCHAR(64) NOT NULL,
              source_event_id VARCHAR(128),
              source_event_hash CHAR(64) NOT NULL,
              metadata_json TEXT NOT NULL,
              metadata_sha256 CHAR(64) NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              sample_sha256 CHAR(64) NOT NULL UNIQUE
            )
            """
        )
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_breaker_sample_event_at "
            f"ON {_SAMPLES}(event_at)"
        )
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_breaker_sample_class_event "
            f"ON {_SAMPLES}(metric_class, event_at)"
        )
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_breaker_sample_request_event "
            f"ON {_SAMPLES}(request_id, event_at)"
        )
    )
    conn.execute(
        text(
            f"CREATE UNIQUE INDEX IF NOT EXISTS uq_breaker_sample_source "
            f"ON {_SAMPLES}(source_event_hash)"
        )
    )


def _create_claims_postgres(conn) -> None:
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_CLAIMS} (
              id SERIAL PRIMARY KEY,
              open_state_id INTEGER NOT NULL
                REFERENCES preview_circuit_breaker_states(id) ON DELETE RESTRICT,
              request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
              decision_id INTEGER
                REFERENCES preview_promotion_decisions(id) ON DELETE SET NULL,
              expected_pointer_version INTEGER NOT NULL,
              target_pointer_version INTEGER NOT NULL,
              idempotency_key VARCHAR(256) NOT NULL UNIQUE,
              claim_sha256 CHAR(64) NOT NULL UNIQUE,
              status VARCHAR(32) NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              UNIQUE(open_state_id, request_id)
            )
            """
        )
    )


def migrate_phase7d_breaker(
    bind: Engine,
    *,
    direction: Literal["upgrade", "downgrade"] = "upgrade",
) -> None:
    dialect = bind.dialect.name
    if dialect not in ("sqlite", "postgresql"):
        raise RuntimeError(f"Phase 7D migration unsupported dialect: {dialect}")

    if direction == "downgrade":
        with bind.begin() as conn:
            _downgrade_guards(conn)
            if _META in inspect(conn).get_table_names():
                conn.execute(text(f"DROP TABLE IF EXISTS {_META}"))
        return

    if phase7d_schema_version(bind) == PHASE7D_SCHEMA_VERSION:
        return

    with bind.begin() as conn:
        tables = set(inspect(conn).get_table_names())
        if "preview_circuit_breaker_states" not in tables:
            raise RuntimeError("Phase 7D requires Phase 7A breaker tables")
        if dialect == "sqlite":
            conn.execute(text("PRAGMA foreign_keys=ON"))
            _create_samples_sqlite(conn)
            _create_claims_sqlite(conn)
        else:
            _create_samples_postgres(conn)
            _create_claims_postgres(conn)
        _ensure_meta(conn, dialect)


__all__ = [
    "PHASE7D_SCHEMA_VERSION",
    "migrate_phase7d_breaker",
    "phase7d_schema_version",
]
