"""Additive commercial Expanded Preview + request access-token migrations."""
from __future__ import annotations

from typing import Literal

from sqlalchemy import Engine, inspect, text

COMMERCIAL_SCHEMA_VERSION = "commercial.1"
_META = "commercial_schema_meta"
_REQ = "expanded_preview_requests"
_EVT = "expanded_preview_status_events"
_CLAIM = "expanded_preview_generation_claims"
_PUB = "expanded_preview_publications"


def commercial_schema_version(bind: Engine) -> str | None:
    with bind.connect() as conn:
        if _META not in inspect(conn).get_table_names():
            return None
        row = conn.execute(
            text(f"SELECT schema_version FROM {_META} ORDER BY id DESC LIMIT 1")
        ).first()
        return None if row is None else str(row[0])


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
        {"v": COMMERCIAL_SCHEMA_VERSION},
    ).scalar()
    if not existing:
        conn.execute(
            text(
                f"INSERT INTO {_META} (schema_version, created_at) "
                "VALUES (:v, CURRENT_TIMESTAMP)"
            ),
            {"v": COMMERCIAL_SCHEMA_VERSION},
        )


def _sqlite_triggers(conn, table: str) -> None:
    conn.execute(
        text(
            f"""
            CREATE TRIGGER IF NOT EXISTS trg_{table}_no_update
            BEFORE UPDATE ON {table}
            BEGIN
              SELECT RAISE(ABORT, '{table} is append-only');
            END;
            """
        )
    )
    conn.execute(
        text(
            f"""
            CREATE TRIGGER IF NOT EXISTS trg_{table}_no_delete
            BEFORE DELETE ON {table}
            BEGIN
              SELECT RAISE(ABORT, '{table} is append-only');
            END;
            """
        )
    )


def _ensure_request_access_token(conn, dialect: str) -> None:
    cols = {c["name"] for c in inspect(conn).get_columns("requests")}
    if "customer_access_token" in cols:
        return
    if dialect == "sqlite":
        conn.execute(
            text("ALTER TABLE requests ADD COLUMN customer_access_token VARCHAR(64)")
        )
    else:
        conn.execute(
            text(
                "ALTER TABLE requests ADD COLUMN IF NOT EXISTS "
                "customer_access_token VARCHAR(64)"
            )
        )


def _create_tables_sqlite(conn) -> None:
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_REQ} (
              id INTEGER PRIMARY KEY,
              expanded_preview_uuid VARCHAR(36) NOT NULL UNIQUE,
              request_id INTEGER NOT NULL REFERENCES requests(id),
              current_status VARCHAR(64) NOT NULL,
              customer_reason TEXT,
              requested_changes TEXT,
              contact_preference VARCHAR(128),
              idempotency_key VARCHAR(128) NOT NULL,
              request_sha256 CHAR(64) NOT NULL,
              actor_id VARCHAR(128) NOT NULL,
              accepted_tier_1_revision_id INTEGER,
              accepted_tier_1_visual_summary_id INTEGER,
              tier_2_candidate_revision_id INTEGER,
              tier_2_visual_summary_id INTEGER,
              published_candidate_revision_id INTEGER,
              generation_claim_token VARCHAR(64),
              generation_started_at TEXT,
              generation_finished_at TEXT,
              generation_error TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE(request_id, idempotency_key)
            )
            """
        )
    )
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_EVT} (
              id INTEGER PRIMARY KEY,
              expanded_preview_id INTEGER NOT NULL REFERENCES {_REQ}(id),
              from_status VARCHAR(64),
              to_status VARCHAR(64) NOT NULL,
              actor_id VARCHAR(128) NOT NULL,
              actor_role VARCHAR(64) NOT NULL,
              reason TEXT,
              internal_notes TEXT,
              event_sha256 CHAR(64) NOT NULL UNIQUE,
              created_at TEXT NOT NULL
            )
            """
        )
    )
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_CLAIM} (
              id INTEGER PRIMARY KEY,
              expanded_preview_id INTEGER NOT NULL UNIQUE REFERENCES {_REQ}(id),
              claim_token VARCHAR(64) NOT NULL UNIQUE,
              claimed_by_actor_id VARCHAR(128) NOT NULL,
              claimed_at TEXT NOT NULL,
              heartbeat_at TEXT NOT NULL,
              released_at TEXT,
              active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
    )
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_PUB} (
              id INTEGER PRIMARY KEY,
              expanded_preview_id INTEGER NOT NULL REFERENCES {_REQ}(id),
              request_id INTEGER NOT NULL REFERENCES requests(id),
              candidate_revision_id INTEGER NOT NULL,
              publisher_actor_id VARCHAR(128) NOT NULL,
              publication_sha256 CHAR(64) NOT NULL UNIQUE,
              customer_preview_path VARCHAR(512) NOT NULL,
              created_at TEXT NOT NULL
            )
            """
        )
    )
    for table in (_EVT, _PUB):
        _sqlite_triggers(conn, table)
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_{_REQ}_request_status "
            f"ON {_REQ}(request_id, current_status)"
        )
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_{_EVT}_expanded "
            f"ON {_EVT}(expanded_preview_id, id)"
        )
    )


def _create_tables_postgres(conn) -> None:
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_REQ} (
              id SERIAL PRIMARY KEY,
              expanded_preview_uuid VARCHAR(36) NOT NULL UNIQUE,
              request_id INTEGER NOT NULL REFERENCES requests(id),
              current_status VARCHAR(64) NOT NULL,
              customer_reason TEXT,
              requested_changes TEXT,
              contact_preference VARCHAR(128),
              idempotency_key VARCHAR(128) NOT NULL,
              request_sha256 CHAR(64) NOT NULL,
              actor_id VARCHAR(128) NOT NULL,
              accepted_tier_1_revision_id INTEGER,
              accepted_tier_1_visual_summary_id INTEGER,
              tier_2_candidate_revision_id INTEGER,
              tier_2_visual_summary_id INTEGER,
              published_candidate_revision_id INTEGER,
              generation_claim_token VARCHAR(64),
              generation_started_at TIMESTAMPTZ,
              generation_finished_at TIMESTAMPTZ,
              generation_error TEXT,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              UNIQUE(request_id, idempotency_key)
            )
            """
        )
    )
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_EVT} (
              id SERIAL PRIMARY KEY,
              expanded_preview_id INTEGER NOT NULL REFERENCES {_REQ}(id),
              from_status VARCHAR(64),
              to_status VARCHAR(64) NOT NULL,
              actor_id VARCHAR(128) NOT NULL,
              actor_role VARCHAR(64) NOT NULL,
              reason TEXT,
              internal_notes TEXT,
              event_sha256 CHAR(64) NOT NULL UNIQUE,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_CLAIM} (
              id SERIAL PRIMARY KEY,
              expanded_preview_id INTEGER NOT NULL UNIQUE REFERENCES {_REQ}(id),
              claim_token VARCHAR(64) NOT NULL UNIQUE,
              claimed_by_actor_id VARCHAR(128) NOT NULL,
              claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              released_at TIMESTAMPTZ,
              active BOOLEAN NOT NULL DEFAULT TRUE
            )
            """
        )
    )
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_PUB} (
              id SERIAL PRIMARY KEY,
              expanded_preview_id INTEGER NOT NULL REFERENCES {_REQ}(id),
              request_id INTEGER NOT NULL REFERENCES requests(id),
              candidate_revision_id INTEGER NOT NULL,
              publisher_actor_id VARCHAR(128) NOT NULL,
              publication_sha256 CHAR(64) NOT NULL UNIQUE,
              customer_preview_path VARCHAR(512) NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_{_REQ}_request_status "
            f"ON {_REQ}(request_id, current_status)"
        )
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_{_EVT}_expanded "
            f"ON {_EVT}(expanded_preview_id, id)"
        )
    )


def migrate_commercial_expanded_preview(
    bind: Engine, *, direction: Literal["upgrade", "downgrade"] = "upgrade"
) -> None:
    if direction == "downgrade":
        with bind.begin() as conn:
            tables = set(inspect(conn).get_table_names())
            if _EVT in tables:
                count = conn.execute(text(f"SELECT COUNT(*) FROM {_EVT}")).scalar()
                if count:
                    raise RuntimeError(
                        "Commercial downgrade rejected: status history exists"
                    )
            if _PUB in tables:
                count = conn.execute(text(f"SELECT COUNT(*) FROM {_PUB}")).scalar()
                if count:
                    raise RuntimeError(
                        "Commercial downgrade rejected: publication history exists"
                    )
            if _META in tables:
                conn.execute(text(f"DROP TABLE IF EXISTS {_META}"))
        return

    dialect = bind.dialect.name
    with bind.begin() as conn:
        _ensure_request_access_token(conn, dialect)
        if dialect == "sqlite":
            _create_tables_sqlite(conn)
        else:
            _create_tables_postgres(conn)
        _ensure_meta(conn, dialect)


__all__ = [
    "COMMERCIAL_SCHEMA_VERSION",
    "commercial_schema_version",
    "migrate_commercial_expanded_preview",
]
