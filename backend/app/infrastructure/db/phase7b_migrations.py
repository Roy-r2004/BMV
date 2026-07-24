"""Additive Phase 7B shadow lineage migrations (SQLite + Postgres)."""
from __future__ import annotations

from typing import Literal

from sqlalchemy import Engine, inspect, text

PHASE7B_SCHEMA_VERSION = "phase7b.1"

_SHADOW_TABLE = "preview_shadow_evaluations"


def phase7b_schema_version(bind: Engine) -> str | None:
    with bind.connect() as conn:
        tables = set(inspect(conn).get_table_names())
        if "preview_phase7b_schema_meta" not in tables:
            return None
        row = conn.execute(
            text(
                "SELECT schema_version FROM preview_phase7b_schema_meta "
                "ORDER BY id DESC LIMIT 1"
            )
        ).first()
        return None if row is None else str(row[0])


def _sqlite_columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}


def _downgrade_guards(conn, dialect: str) -> None:
    tables = set(inspect(conn).get_table_names())
    if _SHADOW_TABLE not in tables:
        return
    cols = (
        _sqlite_columns(conn, _SHADOW_TABLE)
        if dialect == "sqlite"
        else {c["name"] for c in inspect(conn).get_columns(_SHADOW_TABLE)}
    )
    if "shadow_attempt_uuid" in cols:
        count = conn.execute(
            text(
                f"SELECT COUNT(*) FROM {_SHADOW_TABLE} "
                "WHERE shadow_attempt_uuid IS NOT NULL "
                "OR terminal_of_evaluation_id IS NOT NULL"
            )
        ).scalar()
        if count:
            raise RuntimeError(
                "Phase 7B downgrade rejected: shadow lineage rows depend on "
                "additive columns"
            )


def _ensure_meta(conn, dialect: str) -> None:
    if dialect == "sqlite":
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS preview_phase7b_schema_meta (
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
                CREATE TABLE IF NOT EXISTS preview_phase7b_schema_meta (
                  id SERIAL PRIMARY KEY,
                  schema_version VARCHAR(64) NOT NULL,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
    existing = conn.execute(
        text(
            "SELECT COUNT(*) FROM preview_phase7b_schema_meta "
            "WHERE schema_version = :v"
        ),
        {"v": PHASE7B_SCHEMA_VERSION},
    ).scalar()
    if not existing:
        conn.execute(
            text(
                "INSERT INTO preview_phase7b_schema_meta "
                "(schema_version, created_at) VALUES (:v, CURRENT_TIMESTAMP)"
            ),
            {"v": PHASE7B_SCHEMA_VERSION},
        )


def migrate_phase7b_shadow(
    bind: Engine,
    *,
    direction: Literal["upgrade", "downgrade"] = "upgrade",
) -> None:
    dialect = bind.dialect.name
    if dialect not in ("sqlite", "postgresql"):
        raise RuntimeError(f"Phase 7B migration unsupported dialect: {dialect}")

    if direction == "downgrade":
        with bind.begin() as conn:
            _downgrade_guards(conn, dialect)
            # Safe only when no lineage dependency; drop additive indexes/columns
            # is dialect-specific — refuse column drops when any 7B row exists
            # (guard above). When empty, drop meta + indexes only.
            if "preview_phase7b_schema_meta" in inspect(conn).get_table_names():
                conn.execute(text("DROP TABLE IF EXISTS preview_phase7b_schema_meta"))
            if dialect == "sqlite":
                conn.execute(
                    text("DROP INDEX IF EXISTS uq_shadow_one_terminal_per_pending")
                )
                conn.execute(
                    text("DROP INDEX IF EXISTS uq_shadow_one_pending_per_attempt")
                )
                conn.execute(
                    text("DROP INDEX IF EXISTS uq_shadow_idempotency_key")
                )
            else:
                conn.execute(
                    text(
                        "DROP INDEX IF EXISTS uq_shadow_one_terminal_per_pending"
                    )
                )
                conn.execute(
                    text("DROP INDEX IF EXISTS uq_shadow_one_pending_per_attempt")
                )
                conn.execute(text("DROP INDEX IF EXISTS uq_shadow_idempotency_key"))
            # Columns remain if present but unused — refuse silent history rewrite.
            # Full column drop only when table empty of 7B values (already guarded).
            if _SHADOW_TABLE in inspect(conn).get_table_names():
                if dialect == "postgresql":
                    conn.execute(
                        text(
                            f"ALTER TABLE {_SHADOW_TABLE} "
                            "DROP COLUMN IF EXISTS shadow_attempt_uuid, "
                            "DROP COLUMN IF EXISTS terminal_of_evaluation_id, "
                            "DROP COLUMN IF EXISTS mode, "
                            "DROP COLUMN IF EXISTS idempotency_key, "
                            "DROP COLUMN IF EXISTS eligibility_sha256"
                        )
                    )
                # SQLite cannot DROP COLUMN portably across versions without rewrite;
                # leave columns when empty after guard.
        return

    with bind.begin() as conn:
        tables = set(inspect(conn).get_table_names())
        if _SHADOW_TABLE not in tables:
            raise RuntimeError(
                "Phase 7B migration requires Phase 7A preview_shadow_evaluations"
            )
        if dialect == "sqlite":
            conn.execute(text("PRAGMA foreign_keys=ON"))
            cols = _sqlite_columns(conn, _SHADOW_TABLE)
            additions = [
                ("shadow_attempt_uuid", "VARCHAR(36)"),
                ("terminal_of_evaluation_id", "INTEGER"),
                ("mode", "VARCHAR(32)"),
                ("idempotency_key", "VARCHAR(128)"),
                ("eligibility_sha256", "CHAR(64)"),
            ]
            for name, ddl in additions:
                if name not in cols:
                    conn.execute(
                        text(f"ALTER TABLE {_SHADOW_TABLE} ADD COLUMN {name} {ddl}")
                    )
            conn.execute(
                text(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_shadow_one_pending_per_attempt
                    ON preview_shadow_evaluations(shadow_attempt_uuid)
                    WHERE result_status = 'pending' AND shadow_attempt_uuid IS NOT NULL
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_shadow_one_terminal_per_pending
                    ON preview_shadow_evaluations(terminal_of_evaluation_id)
                    WHERE terminal_of_evaluation_id IS NOT NULL
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_shadow_idempotency_key
                    ON preview_shadow_evaluations(request_id, idempotency_key)
                    WHERE idempotency_key IS NOT NULL AND result_status = 'pending'
                    """
                )
            )
        else:
            conn.execute(
                text(
                    f"ALTER TABLE {_SHADOW_TABLE} "
                    "ADD COLUMN IF NOT EXISTS shadow_attempt_uuid VARCHAR(36)"
                )
            )
            conn.execute(
                text(
                    f"ALTER TABLE {_SHADOW_TABLE} "
                    "ADD COLUMN IF NOT EXISTS terminal_of_evaluation_id INTEGER "
                    "REFERENCES preview_shadow_evaluations(id) ON DELETE RESTRICT"
                )
            )
            conn.execute(
                text(
                    f"ALTER TABLE {_SHADOW_TABLE} "
                    "ADD COLUMN IF NOT EXISTS mode VARCHAR(32)"
                )
            )
            conn.execute(
                text(
                    f"ALTER TABLE {_SHADOW_TABLE} "
                    "ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(128)"
                )
            )
            conn.execute(
                text(
                    f"ALTER TABLE {_SHADOW_TABLE} "
                    "ADD COLUMN IF NOT EXISTS eligibility_sha256 CHAR(64)"
                )
            )
            conn.execute(
                text(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_shadow_one_pending_per_attempt
                    ON preview_shadow_evaluations(shadow_attempt_uuid)
                    WHERE result_status = 'pending' AND shadow_attempt_uuid IS NOT NULL
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_shadow_one_terminal_per_pending
                    ON preview_shadow_evaluations(terminal_of_evaluation_id)
                    WHERE terminal_of_evaluation_id IS NOT NULL
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_shadow_idempotency_key
                    ON preview_shadow_evaluations(request_id, idempotency_key)
                    WHERE idempotency_key IS NOT NULL AND result_status = 'pending'
                    """
                )
            )
        _ensure_meta(conn, dialect)


__all__ = [
    "PHASE7B_SCHEMA_VERSION",
    "migrate_phase7b_shadow",
    "phase7b_schema_version",
]
