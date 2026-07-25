"""Additive Phase 7F percent-serve / live-canary migrations."""
from __future__ import annotations

from typing import Literal

from sqlalchemy import Engine, inspect, text

PHASE7F_SCHEMA_VERSION = "phase7f.2"
_PROVENANCE_COLS = (
    ("execution_mode", "VARCHAR(16)"),
    ("provider_was_live", "INTEGER"),
    ("provider_family", "VARCHAR(64)"),
    ("provider_model", "VARCHAR(128)"),
    ("provider_factory_revision", "VARCHAR(64)"),
    ("network_access_expected", "INTEGER"),
    ("execution_environment", "VARCHAR(64)"),
    ("simulation_only", "INTEGER"),
    ("percent_authorization_eligible", "INTEGER"),
    ("provenance_json", "TEXT"),
)
_EXEC = "preview_live_canary_executions"
_EXEC_STATUS = "preview_live_canary_execution_status_events"
_LIFE = "preview_live_canary_lifecycle_events"
_CLAIM = "preview_live_canary_execution_claims"
_META = "preview_phase7f_schema_meta"
_APPROVALS = "preview_live_canary_approvals"


def phase7f_schema_version(bind: Engine) -> str | None:
    with bind.connect() as conn:
        if _META not in inspect(conn).get_table_names():
            return None
        row = conn.execute(
            text(f"SELECT schema_version FROM {_META} ORDER BY id DESC LIMIT 1")
        ).first()
        return None if row is None else str(row[0])


def _downgrade_guards(conn) -> None:
    tables = set(inspect(conn).get_table_names())
    if _EXEC in tables:
        count = conn.execute(text(f"SELECT COUNT(*) FROM {_EXEC}")).scalar()
        if count:
            raise RuntimeError(
                "Phase 7F downgrade rejected: canary execution history exists"
            )
    if _LIFE in tables:
        reviewed = conn.execute(
            text(
                f"SELECT COUNT(*) FROM {_LIFE} "
                "WHERE status IN ("
                "'reviewed_accepted','reviewed_rejected','reviewed_fixture_only')"
            )
        ).scalar()
        if reviewed:
            raise RuntimeError(
                "Phase 7F downgrade rejected: canary review history exists"
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
        {"v": PHASE7F_SCHEMA_VERSION},
    ).scalar()
    if not existing:
        conn.execute(
            text(
                f"INSERT INTO {_META} (schema_version, created_at) "
                "VALUES (:v, CURRENT_TIMESTAMP)"
            ),
            {"v": PHASE7F_SCHEMA_VERSION},
        )


def _sqlite_triggers(conn, table: str) -> None:
    for action, op in (("UPDATE", "UPDATE"), ("DELETE", "DELETE")):
        conn.execute(
            text(
                f"""
                CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{action.lower()}
                BEFORE {op} ON {table}
                BEGIN
                  SELECT RAISE(ABORT,
                    'Phase 7F append-only: {op} forbidden on {table}');
                END
                """
            )
        )


def _add_approval_columns_sqlite(conn) -> None:
    cols = {c["name"] for c in inspect(conn).get_columns(_APPROVALS)}
    additions = [
        ("requester_id", "VARCHAR(128)"),
        ("reason", "TEXT"),
        ("rollout_salt", "VARCHAR(128)"),
        ("provider_manifest_sha256", "CHAR(64)"),
        ("generation_policy_sha256", "CHAR(64)"),
        ("prompt_policy_sha256", "CHAR(64)"),
        ("runtime_policy_sha256", "CHAR(64)"),
        ("comparison_policy_revision", "VARCHAR(64)"),
        ("budget_policy_sha256", "CHAR(64)"),
        ("max_input_tokens", "INTEGER"),
        ("max_retries", "INTEGER"),
        ("per_call_timeout_seconds", "INTEGER"),
        ("policy_identity_sha256", "CHAR(64)"),
        ("idempotency_key", "VARCHAR(256)"),
    ]
    for name, typ in additions:
        if name not in cols:
            conn.execute(text(f"ALTER TABLE {_APPROVALS} ADD COLUMN {name} {typ}"))


def _add_approval_columns_postgres(conn) -> None:
    additions = [
        ("requester_id", "VARCHAR(128)"),
        ("reason", "TEXT"),
        ("rollout_salt", "VARCHAR(128)"),
        ("provider_manifest_sha256", "CHAR(64)"),
        ("generation_policy_sha256", "CHAR(64)"),
        ("prompt_policy_sha256", "CHAR(64)"),
        ("runtime_policy_sha256", "CHAR(64)"),
        ("comparison_policy_revision", "VARCHAR(64)"),
        ("budget_policy_sha256", "CHAR(64)"),
        ("max_input_tokens", "INTEGER"),
        ("max_retries", "INTEGER"),
        ("per_call_timeout_seconds", "INTEGER"),
        ("policy_identity_sha256", "CHAR(64)"),
        ("idempotency_key", "VARCHAR(256)"),
    ]
    for name, typ in additions:
        conn.execute(
            text(f"ALTER TABLE {_APPROVALS} ADD COLUMN IF NOT EXISTS {name} {typ}")
        )


def _create_lifecycle_sqlite(conn) -> None:
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_LIFE} (
              id INTEGER PRIMARY KEY,
              approval_id INTEGER NOT NULL
                REFERENCES {_APPROVALS}(id) ON DELETE RESTRICT,
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
            f"CREATE INDEX IF NOT EXISTS ix_canary_life_approval "
            f"ON {_LIFE}(approval_id, created_at)"
        )
    )
    _sqlite_triggers(conn, _LIFE)


def _create_exec_sqlite(conn) -> None:
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_EXEC} (
              id INTEGER PRIMARY KEY,
              execution_uuid VARCHAR(36) NOT NULL UNIQUE,
              approval_id INTEGER NOT NULL
                REFERENCES {_APPROVALS}(id) ON DELETE RESTRICT,
              request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
              started_at TEXT NOT NULL,
              completed_at TEXT,
              provider_manifest_sha256 CHAR(64) NOT NULL,
              generation_policy_sha256 CHAR(64) NOT NULL,
              prompt_policy_sha256 CHAR(64) NOT NULL,
              candidate_revision_id INTEGER,
              effective_tier INTEGER,
              phase4_status VARCHAR(64),
              phase5_status VARCHAR(64),
              provider_calls INTEGER NOT NULL DEFAULT 0,
              input_tokens INTEGER NOT NULL DEFAULT 0,
              output_tokens INTEGER NOT NULL DEFAULT 0,
              estimated_cost_usd REAL NOT NULL DEFAULT 0,
              wall_seconds REAL NOT NULL DEFAULT 0,
              retries INTEGER NOT NULL DEFAULT 0,
              budget_json TEXT NOT NULL,
              comparison_artifact_sha256 CHAR(64),
              telemetry_sha256 CHAR(64) NOT NULL,
              result_status VARCHAR(32) NOT NULL,
              failure_reason TEXT,
              no_serving_mutation INTEGER NOT NULL DEFAULT 1,
              pointer_version_before INTEGER,
              pointer_version_after INTEGER,
              policy_identity_sha256 CHAR(64) NOT NULL,
              idempotency_key VARCHAR(256) NOT NULL UNIQUE,
              execution_sha256 CHAR(64) NOT NULL UNIQUE,
              created_at TEXT NOT NULL,
              execution_mode VARCHAR(16) NOT NULL DEFAULT 'fixture',
              provider_was_live INTEGER NOT NULL DEFAULT 0,
              provider_family VARCHAR(64),
              provider_model VARCHAR(128),
              provider_factory_revision VARCHAR(64),
              network_access_expected INTEGER NOT NULL DEFAULT 0,
              execution_environment VARCHAR(64),
              simulation_only INTEGER NOT NULL DEFAULT 1,
              percent_authorization_eligible INTEGER NOT NULL DEFAULT 0,
              provenance_json TEXT
            )
            """
        )
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_canary_exec_request "
            f"ON {_EXEC}(request_id, created_at)"
        )
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_canary_exec_approval "
            f"ON {_EXEC}(approval_id)"
        )
    )
    _sqlite_triggers(conn, _EXEC)

    # Mutable singleton claim (not append-only) — global one-active-execution lock.
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_CLAIM} (
              id INTEGER PRIMARY KEY CHECK (id = 1),
              execution_id INTEGER REFERENCES {_EXEC}(id) ON DELETE RESTRICT,
              claimed_at TEXT NOT NULL,
              released_at TEXT,
              claim_sha256 CHAR(64) NOT NULL UNIQUE
            )
            """
        )
    )

    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_EXEC_STATUS} (
              id INTEGER PRIMARY KEY,
              execution_id INTEGER NOT NULL
                REFERENCES {_EXEC}(id) ON DELETE RESTRICT,
              status VARCHAR(32) NOT NULL,
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
            f"CREATE INDEX IF NOT EXISTS ix_canary_exec_status "
            f"ON {_EXEC_STATUS}(execution_id, created_at)"
        )
    )
    _sqlite_triggers(conn, _EXEC_STATUS)


def _create_lifecycle_postgres(conn) -> None:
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_LIFE} (
              id SERIAL PRIMARY KEY,
              approval_id INTEGER NOT NULL
                REFERENCES {_APPROVALS}(id) ON DELETE RESTRICT,
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
            f"CREATE INDEX IF NOT EXISTS ix_canary_life_approval "
            f"ON {_LIFE}(approval_id, created_at)"
        )
    )


def _create_exec_postgres(conn) -> None:
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_EXEC} (
              id SERIAL PRIMARY KEY,
              execution_uuid VARCHAR(36) NOT NULL UNIQUE,
              approval_id INTEGER NOT NULL
                REFERENCES {_APPROVALS}(id) ON DELETE RESTRICT,
              request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
              started_at TIMESTAMPTZ NOT NULL,
              completed_at TIMESTAMPTZ,
              provider_manifest_sha256 CHAR(64) NOT NULL,
              generation_policy_sha256 CHAR(64) NOT NULL,
              prompt_policy_sha256 CHAR(64) NOT NULL,
              candidate_revision_id INTEGER,
              effective_tier INTEGER,
              phase4_status VARCHAR(64),
              phase5_status VARCHAR(64),
              provider_calls INTEGER NOT NULL DEFAULT 0,
              input_tokens INTEGER NOT NULL DEFAULT 0,
              output_tokens INTEGER NOT NULL DEFAULT 0,
              estimated_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
              wall_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
              retries INTEGER NOT NULL DEFAULT 0,
              budget_json TEXT NOT NULL,
              comparison_artifact_sha256 CHAR(64),
              telemetry_sha256 CHAR(64) NOT NULL,
              result_status VARCHAR(32) NOT NULL,
              failure_reason TEXT,
              no_serving_mutation BOOLEAN NOT NULL DEFAULT TRUE,
              pointer_version_before INTEGER,
              pointer_version_after INTEGER,
              policy_identity_sha256 CHAR(64) NOT NULL,
              idempotency_key VARCHAR(256) NOT NULL UNIQUE,
              execution_sha256 CHAR(64) NOT NULL UNIQUE,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              execution_mode VARCHAR(16) NOT NULL DEFAULT 'fixture',
              provider_was_live BOOLEAN NOT NULL DEFAULT FALSE,
              provider_family VARCHAR(64),
              provider_model VARCHAR(128),
              provider_factory_revision VARCHAR(64),
              network_access_expected BOOLEAN NOT NULL DEFAULT FALSE,
              execution_environment VARCHAR(64),
              simulation_only BOOLEAN NOT NULL DEFAULT TRUE,
              percent_authorization_eligible BOOLEAN NOT NULL DEFAULT FALSE,
              provenance_json TEXT
            )
            """
        )
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_canary_exec_request "
            f"ON {_EXEC}(request_id, created_at)"
        )
    )
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_CLAIM} (
              id INTEGER PRIMARY KEY CHECK (id = 1),
              execution_id INTEGER REFERENCES {_EXEC}(id) ON DELETE RESTRICT,
              claimed_at TIMESTAMPTZ NOT NULL,
              released_at TIMESTAMPTZ,
              claim_sha256 CHAR(64) NOT NULL UNIQUE
            )
            """
        )
    )
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_EXEC_STATUS} (
              id SERIAL PRIMARY KEY,
              execution_id INTEGER NOT NULL
                REFERENCES {_EXEC}(id) ON DELETE RESTRICT,
              status VARCHAR(32) NOT NULL,
              actor_id VARCHAR(128) NOT NULL,
              reason TEXT NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              event_sha256 CHAR(64) NOT NULL UNIQUE
            )
            """
        )
    )


def _ensure_provenance_columns(conn, dialect: str) -> None:
    if _EXEC not in set(inspect(conn).get_table_names()):
        return
    cols = {c["name"] for c in inspect(conn).get_columns(_EXEC)}
    for name, typ in _PROVENANCE_COLS:
        if name in cols:
            continue
        if dialect == "sqlite":
            conn.execute(text(f"ALTER TABLE {_EXEC} ADD COLUMN {name} {typ}"))
        else:
            pg_typ = {
                "INTEGER": "BOOLEAN",
                "VARCHAR(16)": "VARCHAR(16)",
                "VARCHAR(64)": "VARCHAR(64)",
                "VARCHAR(128)": "VARCHAR(128)",
                "TEXT": "TEXT",
            }.get(typ, typ)
            conn.execute(
                text(f"ALTER TABLE {_EXEC} ADD COLUMN IF NOT EXISTS {name} {pg_typ}")
            )


def migrate_phase7f_percent_canary(
    bind: Engine,
    *,
    direction: Literal["upgrade", "downgrade"] = "upgrade",
) -> None:
    dialect = bind.dialect.name
    if dialect not in ("sqlite", "postgresql"):
        raise RuntimeError(f"Phase 7F migration unsupported dialect: {dialect}")

    if direction == "downgrade":
        with bind.begin() as conn:
            _downgrade_guards(conn)
            if _META in inspect(conn).get_table_names():
                conn.execute(text(f"DROP TABLE IF EXISTS {_META}"))
        return

    current = phase7f_schema_version(bind)
    if current == PHASE7F_SCHEMA_VERSION:
        with bind.begin() as conn:
            _ensure_provenance_columns(conn, dialect)
        return

    with bind.begin() as conn:
        tables = set(inspect(conn).get_table_names())
        if _APPROVALS not in tables:
            raise RuntimeError("Phase 7F requires Phase 7A canary approval tables")
        if dialect == "sqlite":
            conn.execute(text("PRAGMA foreign_keys=ON"))
            _add_approval_columns_sqlite(conn)
            _create_lifecycle_sqlite(conn)
            _create_exec_sqlite(conn)
        else:
            _add_approval_columns_postgres(conn)
            _create_lifecycle_postgres(conn)
            _create_exec_postgres(conn)
        _ensure_provenance_columns(conn, dialect)
        _ensure_meta(conn, dialect)


__all__ = [
    "PHASE7F_SCHEMA_VERSION",
    "migrate_phase7f_percent_canary",
    "phase7f_schema_version",
]
