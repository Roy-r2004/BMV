"""Small reviewed migrations used by both SQLite and Postgres.

Lightweight alternative to Alembic for this project's simple schema —
adds columns that may be missing in databases created by older versions of
the app. Safe to call on every startup: it only adds columns that don't
already exist, and never raises.
"""
import re
from typing import Literal

from sqlalchemy import Engine, inspect, text

from app.core.config import settings
from app.infrastructure.db.phase7a_migrations import (
    migrate_phase7a_rollout,
    phase7a_schema_version,
)
from app.infrastructure.db.phase7b_migrations import (
    migrate_phase7b_shadow,
    phase7b_schema_version,
)
from app.infrastructure.db.phase7c_migrations import (
    migrate_phase7c_promotion,
    phase7c_schema_version,
)
from app.infrastructure.db.session import engine

_REQUESTS_TABLE_MIGRATIONS: list[tuple[str, str]] = [
    ("generated_pages", "ALTER TABLE requests ADD COLUMN generated_pages TEXT"),
    ("project_type", "ALTER TABLE requests ADD COLUMN project_type VARCHAR"),
    ("existing_product_url", "ALTER TABLE requests ADD COLUMN existing_product_url VARCHAR"),
    ("generation_log", "ALTER TABLE requests ADD COLUMN generation_log TEXT"),
    ("ai_features", "ALTER TABLE requests ADD COLUMN ai_features TEXT"),
    ("build_plans", "ALTER TABLE requests ADD COLUMN build_plans TEXT"),
]

_CANDIDATE_TARGET_CONSTRAINT = "ck_candidate_revision_target_tier"
_CANDIDATE_TARGET_UP = "target_tier IN (1, 2, 3)"
_CANDIDATE_TARGET_DOWN = "target_tier = 1"
_TIER_ORCHESTRATION_TABLES = (
    "candidate_tier_orchestration_attempts",
    "candidate_tier_extension_manifests",
    "candidate_lower_tier_preservation_audits",
    "candidate_tier_generation_results",
    "candidate_tier_validation_results",
    "candidate_tier_visual_outcomes",
    "candidate_effective_tier_summaries",
)
_TIER3_ADDITIVE_COLUMNS = (
    (
        "accepted_tier_2_revision_id",
        "INTEGER REFERENCES candidate_revisions(id)",
    ),
    (
        "accepted_tier_2_visual_summary_id",
        "INTEGER REFERENCES candidate_visual_summaries(id)",
    ),
    (
        "accepted_tier_2_effective_summary_id",
        "INTEGER REFERENCES candidate_effective_tier_summaries(id)",
    ),
    ("lower_tier_effective_summary_sha256", "VARCHAR(64)"),
)


def _candidate_target_values(bind: Engine) -> tuple[int, ...]:
    with bind.connect() as conn:
        if "candidate_revisions" not in inspect(conn).get_table_names():
            return ()
        return tuple(
            int(row[0])
            for row in conn.execute(
                text(
                    "SELECT DISTINCT target_tier FROM candidate_revisions "
                    "ORDER BY target_tier"
                )
            )
        )


def _validate_candidate_target_rows(
    bind: Engine,
    *,
    direction: Literal["upgrade", "downgrade"],
) -> None:
    values = _candidate_target_values(bind)
    allowed = {1, 2, 3} if direction == "upgrade" else {1}
    unexpected = tuple(value for value in values if value not in allowed)
    if unexpected:
        raise RuntimeError(
            "Candidate target-tier migration rejected existing values: "
            f"{unexpected}"
        )


def _sqlite_candidate_target_migration(
    bind: Engine,
    *,
    direction: Literal["upgrade", "downgrade"],
) -> None:
    desired = (
        _CANDIDATE_TARGET_UP
        if direction == "upgrade"
        else _CANDIDATE_TARGET_DOWN
    )
    raw = bind.raw_connection()
    cursor = raw.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys")
        foreign_keys_enabled = bool(cursor.fetchone()[0])
        cursor.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='table' AND name='candidate_revisions'"
        )
        row = cursor.fetchone()
        if row is None:
            return
        original_ddl = str(row[0])
        compact = re.sub(r"\s+", " ", original_ddl.lower())
        desired_compact = re.sub(r"\s+", " ", desired.lower())
        if desired_compact in compact:
            return
        cursor.execute(
            "SELECT DISTINCT target_tier FROM candidate_revisions "
            "ORDER BY target_tier"
        )
        values = tuple(int(item[0]) for item in cursor.fetchall())
        allowed = {1, 2, 3} if direction == "upgrade" else {1}
        unexpected = tuple(value for value in values if value not in allowed)
        if unexpected:
            raise RuntimeError(
                "Candidate target-tier migration rejected existing values: "
                f"{unexpected}"
            )
        cursor.execute("PRAGMA table_info(candidate_revisions)")
        columns = tuple(str(item[1]) for item in cursor.fetchall())
        if not columns:
            raise RuntimeError("candidate_revisions has no columns")
        quoted_columns = ", ".join(f'"{name}"' for name in columns)
        cursor.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE tbl_name='candidate_revisions' "
            "AND type IN ('index','trigger') AND sql IS NOT NULL "
            "ORDER BY type, name"
        )
        secondary_ddl = tuple(str(item[2]) for item in cursor.fetchall())
        before = tuple(
            cursor.execute(
                f"SELECT {quoted_columns} FROM candidate_revisions ORDER BY id"
            ).fetchall()
        )
        upgraded_ddl, substitutions = re.subn(
            r"target_tier\s*=\s*1",
            desired,
            original_ddl,
            count=1,
            flags=re.IGNORECASE,
        )
        if substitutions != 1:
            upgraded_ddl, substitutions = re.subn(
                r"target_tier\s+IN\s*\(\s*1\s*,\s*2\s*,\s*3\s*\)",
                desired,
                original_ddl,
                count=1,
                flags=re.IGNORECASE,
            )
        if substitutions != 1:
            raise RuntimeError(
                "Candidate target-tier constraint shape is unknown; "
                "migration failed closed."
            )
        cursor.execute("PRAGMA legacy_alter_table")
        legacy_alter_table = bool(cursor.fetchone()[0])
        if foreign_keys_enabled:
            cursor.execute("PRAGMA foreign_keys=OFF")
        if not legacy_alter_table:
            # SQLite 3.26+ otherwise rewrites child-table foreign-key targets
            # to the temporary table name during ALTER TABLE ... RENAME.
            cursor.execute("PRAGMA legacy_alter_table=ON")
        cursor.execute("BEGIN IMMEDIATE")
        try:
            cursor.execute(
                "ALTER TABLE candidate_revisions "
                "RENAME TO candidate_revisions_phase6a_old"
            )
            cursor.execute(upgraded_ddl)
            cursor.execute(
                f"INSERT INTO candidate_revisions ({quoted_columns}) "
                f"SELECT {quoted_columns} "
                "FROM candidate_revisions_phase6a_old"
            )
            after = tuple(
                cursor.execute(
                    f"SELECT {quoted_columns} "
                    "FROM candidate_revisions ORDER BY id"
                ).fetchall()
            )
            if before != after:
                raise RuntimeError(
                    "Candidate target-tier migration changed stored row data"
                )
            cursor.execute("DROP TABLE candidate_revisions_phase6a_old")
            for statement in secondary_ddl:
                cursor.execute(statement)
            cursor.execute("PRAGMA foreign_key_check")
            violations = cursor.fetchall()
            if violations:
                raise RuntimeError(
                    "Candidate target-tier migration broke foreign keys"
                )
            raw.commit()
        except Exception:
            raw.rollback()
            raise
        finally:
            if not legacy_alter_table:
                cursor.execute("PRAGMA legacy_alter_table=OFF")
            if foreign_keys_enabled:
                cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()
        raw.close()


def _postgres_candidate_target_migration(
    bind: Engine,
    *,
    direction: Literal["upgrade", "downgrade"],
) -> None:
    _validate_candidate_target_rows(bind, direction=direction)
    desired = (
        _CANDIDATE_TARGET_UP
        if direction == "upgrade"
        else _CANDIDATE_TARGET_DOWN
    )
    with bind.begin() as conn:
        if "candidate_revisions" not in inspect(conn).get_table_names():
            return
        conn.execute(
            text(
                "ALTER TABLE candidate_revisions "
                f"DROP CONSTRAINT IF EXISTS {_CANDIDATE_TARGET_CONSTRAINT}"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE candidate_revisions ADD CONSTRAINT "
                f"{_CANDIDATE_TARGET_CONSTRAINT} CHECK ({desired})"
            )
        )


def migrate_candidate_revision_target_tier(
    bind: Engine,
    *,
    direction: Literal["upgrade", "downgrade"] = "upgrade",
) -> None:
    """Expand/contract the candidate target-tier constraint transactionally."""

    if bind.dialect.name == "sqlite":
        _sqlite_candidate_target_migration(bind, direction=direction)
        return
    if bind.dialect.name == "postgresql":
        _postgres_candidate_target_migration(bind, direction=direction)
        return
    raise RuntimeError(
        "Candidate target-tier migration supports only SQLite and Postgres"
    )


def assert_candidate_target_tier_constraint(bind: Engine) -> None:
    """Fail closed unless the live table accepts exactly the Phase 6 range."""

    if "candidate_revisions" not in inspect(bind).get_table_names():
        raise RuntimeError("candidate_revisions table is missing")
    if bind.dialect.name == "sqlite":
        with bind.connect() as conn:
            ddl = conn.execute(
                text(
                    "SELECT sql FROM sqlite_master WHERE type='table' "
                    "AND name='candidate_revisions'"
                )
            ).scalar_one()
        compact = re.sub(r"\s+", " ", str(ddl).lower())
        if "target_tier in (1, 2, 3)" not in compact:
            raise RuntimeError(
                "Candidate target-tier constraint has not been migrated"
            )
        return
    checks = inspect(bind).get_check_constraints("candidate_revisions")
    match = next(
        (
            item
            for item in checks
            if item.get("name") == _CANDIDATE_TARGET_CONSTRAINT
        ),
        None,
    )
    sqltext = re.sub(r"\s+", " ", str((match or {}).get("sqltext", "")).lower())
    if not all(str(value) in sqltext for value in (1, 2, 3)):
        raise RuntimeError(
            "Candidate target-tier constraint has not been migrated"
        )


def _tier_orchestration_values(bind: Engine) -> tuple[int, ...]:
    values: set[int] = set()
    with bind.connect() as conn:
        tables = set(inspect(conn).get_table_names())
        for table in _TIER_ORCHESTRATION_TABLES:
            if table not in tables:
                continue
            values.update(
                int(row[0])
                for row in conn.execute(
                    text(f"SELECT DISTINCT target_tier FROM {table}")
                )
            )
    return tuple(sorted(values))


def _validate_tier_orchestration_rows(
    bind: Engine,
    *,
    direction: Literal["upgrade", "downgrade"],
) -> None:
    values = _tier_orchestration_values(bind)
    allowed = {2, 3} if direction == "upgrade" else {2}
    unexpected = tuple(value for value in values if value not in allowed)
    if unexpected:
        raise RuntimeError(
            "Tier orchestration migration rejected existing values: "
            f"{unexpected}"
        )


def _replace_tier_orchestration_constraints(
    ddl: str,
    *,
    direction: Literal["upgrade", "downgrade"],
    effective_summary: bool,
) -> str:
    target = (
        "target_tier IN (2, 3)"
        if direction == "upgrade"
        else "target_tier = 2"
    )
    patterns = (
        r"target_tier\s*=\s*2",
        r"target_tier\s+IN\s*\(\s*2\s*,\s*3\s*\)",
    )
    rewritten = ddl
    count = 0
    for pattern in patterns:
        rewritten, found = re.subn(
            pattern,
            target,
            rewritten,
            count=1,
            flags=re.IGNORECASE,
        )
        if found:
            count = found
            break
    if count != 1:
        raise RuntimeError(
            "Tier orchestration target constraint shape is unknown"
        )
    if effective_summary:
        status = (
            "status IN ('tier_2_accepted','tier_2_failed_serving_tier_1',"
            "'tier_3_accepted','tier_3_failed_serving_tier_2')"
            if direction == "upgrade"
            else
            "status IN ('tier_2_accepted','tier_2_failed_serving_tier_1')"
        )
        rewritten, status_count = re.subn(
            r"status\s+IN\s*\(\s*'tier_2_accepted'\s*,\s*"
            r"'tier_2_failed_serving_tier_1'"
            r"(?:\s*,\s*'tier_3_accepted'\s*,\s*"
            r"'tier_3_failed_serving_tier_2')?\s*\)",
            status,
            rewritten,
            count=1,
            flags=re.IGNORECASE,
        )
        highest = (
            "highest_accepted_tier IN (1, 2, 3)"
            if direction == "upgrade"
            else "highest_accepted_tier IN (1, 2)"
        )
        rewritten, highest_count = re.subn(
            r"highest_accepted_tier\s+IN\s*\(\s*1\s*,\s*2"
            r"(?:\s*,\s*3)?\s*\)",
            highest,
            rewritten,
            count=1,
            flags=re.IGNORECASE,
        )
        if status_count != 1 or highest_count != 1:
            raise RuntimeError(
                "Effective tier summary constraint shape is unknown"
            )
    return rewritten


def _sqlite_tier_orchestration_migration(
    bind: Engine,
    *,
    direction: Literal["upgrade", "downgrade"],
) -> None:
    raw = bind.raw_connection()
    cursor = raw.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys")
        foreign_keys_enabled = bool(cursor.fetchone()[0])
        cursor.execute("PRAGMA legacy_alter_table")
        legacy = bool(cursor.fetchone()[0])
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        live_tables = {str(row[0]) for row in cursor.fetchall()}
        present = tuple(
            item for item in _TIER_ORCHESTRATION_TABLES
            if item in live_tables
        )
        if not present:
            return
        values: set[int] = set()
        for table in present:
            cursor.execute(f"SELECT DISTINCT target_tier FROM {table}")
            values.update(int(row[0]) for row in cursor.fetchall())
        allowed = {2, 3} if direction == "upgrade" else {2}
        unexpected = tuple(sorted(value for value in values if value not in allowed))
        if unexpected:
            raise RuntimeError(
                "Tier orchestration migration rejected existing values: "
                f"{unexpected}"
            )
        if foreign_keys_enabled:
            cursor.execute("PRAGMA foreign_keys=OFF")
        if not legacy:
            cursor.execute("PRAGMA legacy_alter_table=ON")
        cursor.execute("BEGIN IMMEDIATE")
        try:
            if direction == "upgrade":
                for table in present:
                    cursor.execute(f"PRAGMA table_info({table})")
                    columns = {str(row[1]) for row in cursor.fetchall()}
                    for name, sql_type in _TIER3_ADDITIVE_COLUMNS:
                        if name not in columns:
                            cursor.execute(
                                f"ALTER TABLE {table} ADD COLUMN "
                                f"{name} {sql_type}"
                            )
                attempt = "candidate_tier_orchestration_attempts"
                if attempt in present:
                    cursor.execute(f"PRAGMA table_info({attempt})")
                    attempt_columns = {
                        str(row[1]) for row in cursor.fetchall()
                    }
                    for name, sql_type in (
                        ("visual_call_plan_json", "TEXT"),
                        ("visual_call_plan_sha256", "VARCHAR(64)"),
                    ):
                        if name not in attempt_columns:
                            cursor.execute(
                                f"ALTER TABLE {attempt} ADD COLUMN "
                                f"{name} {sql_type}"
                            )
            for table in present:
                cursor.execute(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type='table' AND name=?",
                    (table,),
                )
                original = str(cursor.fetchone()[0])
                desired = (
                    "target_tier in (2, 3)"
                    if direction == "upgrade"
                    else "target_tier = 2"
                )
                compact = re.sub(r"\s+", " ", original.lower())
                effective_ok = True
                if table == "candidate_effective_tier_summaries":
                    effective_ok = (
                        ("tier_3_accepted" in compact)
                        == (direction == "upgrade")
                    )
                if desired in compact and effective_ok:
                    continue
                cursor.execute(f"PRAGMA table_info({table})")
                columns = tuple(str(row[1]) for row in cursor.fetchall())
                quoted = ", ".join(f'"{name}"' for name in columns)
                cursor.execute(
                    "SELECT type, name, sql FROM sqlite_master "
                    "WHERE tbl_name=? AND type IN ('index','trigger') "
                    "AND sql IS NOT NULL ORDER BY type, name",
                    (table,),
                )
                secondary = tuple(str(row[2]) for row in cursor.fetchall())
                before = tuple(
                    cursor.execute(
                        f"SELECT {quoted} FROM {table} ORDER BY id"
                    ).fetchall()
                )
                rewritten = _replace_tier_orchestration_constraints(
                    original,
                    direction=direction,
                    effective_summary=(
                        table == "candidate_effective_tier_summaries"
                    ),
                )
                old = f"{table}_phase6b_old"
                cursor.execute(f"ALTER TABLE {table} RENAME TO {old}")
                cursor.execute(rewritten)
                cursor.execute(
                    f"INSERT INTO {table} ({quoted}) "
                    f"SELECT {quoted} FROM {old}"
                )
                after = tuple(
                    cursor.execute(
                        f"SELECT {quoted} FROM {table} ORDER BY id"
                    ).fetchall()
                )
                if before != after:
                    raise RuntimeError(
                        "Tier orchestration migration changed stored row data"
                    )
                cursor.execute(f"DROP TABLE {old}")
                for statement in secondary:
                    cursor.execute(statement)
            cursor.execute("PRAGMA foreign_key_check")
            if cursor.fetchall():
                raise RuntimeError(
                    "Tier orchestration migration broke foreign keys"
                )
            raw.commit()
        except Exception:
            raw.rollback()
            raise
        finally:
            if not legacy:
                cursor.execute("PRAGMA legacy_alter_table=OFF")
            if foreign_keys_enabled:
                cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()
        raw.close()


def _postgres_tier_orchestration_migration(
    bind: Engine,
    *,
    direction: Literal["upgrade", "downgrade"],
) -> None:
    _validate_tier_orchestration_rows(bind, direction=direction)
    with bind.begin() as conn:
        tables = set(inspect(conn).get_table_names())
        for table in _TIER_ORCHESTRATION_TABLES:
            if table not in tables:
                continue
            if direction == "upgrade":
                for name, sql_type in _TIER3_ADDITIVE_COLUMNS:
                    conn.execute(
                        text(
                            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "
                            f"{name} {sql_type}"
                        )
                    )
                if table == "candidate_tier_orchestration_attempts":
                    conn.execute(
                        text(
                            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "
                            "visual_call_plan_json TEXT"
                        )
                    )
                    conn.execute(
                        text(
                            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "
                            "visual_call_plan_sha256 VARCHAR(64)"
                        )
                    )
            check_names = {
                "candidate_tier_orchestration_attempts": "ck_tier_attempt_target",
                "candidate_tier_extension_manifests": "ck_tier_manifest_target",
                "candidate_lower_tier_preservation_audits": "ck_tier_audit_target",
                "candidate_tier_generation_results": "ck_tier_generation_target",
                "candidate_tier_validation_results": "ck_tier_validation_target",
                "candidate_tier_visual_outcomes": "ck_tier_visual_target",
                "candidate_effective_tier_summaries": "ck_effective_tier_target",
            }
            name = check_names[table]
            conn.execute(
                text(
                    f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}"
                )
            )
            target = (
                "target_tier IN (2, 3)"
                if direction == "upgrade"
                else "target_tier = 2"
            )
            conn.execute(
                text(
                    f"ALTER TABLE {table} ADD CONSTRAINT {name} "
                    f"CHECK ({target})"
                )
            )
        effective = "candidate_effective_tier_summaries"
        if effective in tables:
            conn.execute(
                text(
                    f"ALTER TABLE {effective} DROP CONSTRAINT IF EXISTS "
                    "ck_effective_tier_status"
                )
            )
            conn.execute(
                text(
                    f"ALTER TABLE {effective} DROP CONSTRAINT IF EXISTS "
                    "ck_highest_accepted_tier"
                )
            )
            statuses = (
                "status IN ('tier_2_accepted','tier_2_failed_serving_tier_1',"
                "'tier_3_accepted','tier_3_failed_serving_tier_2')"
                if direction == "upgrade"
                else
                "status IN ('tier_2_accepted','tier_2_failed_serving_tier_1')"
            )
            highest = (
                "highest_accepted_tier IN (1, 2, 3)"
                if direction == "upgrade"
                else "highest_accepted_tier IN (1, 2)"
            )
            conn.execute(
                text(
                    f"ALTER TABLE {effective} ADD CONSTRAINT "
                    f"ck_effective_tier_status CHECK ({statuses})"
                )
            )
            conn.execute(
                text(
                    f"ALTER TABLE {effective} ADD CONSTRAINT "
                    f"ck_highest_accepted_tier CHECK ({highest})"
                )
            )


def migrate_tier_orchestration_target_tier(
    bind: Engine,
    *,
    direction: Literal["upgrade", "downgrade"] = "upgrade",
) -> None:
    """Generalize the seven Phase 6 tables without rewriting row payloads."""

    if bind.dialect.name == "sqlite":
        _sqlite_tier_orchestration_migration(bind, direction=direction)
        return
    if bind.dialect.name == "postgresql":
        _postgres_tier_orchestration_migration(bind, direction=direction)
        return
    raise RuntimeError(
        "Tier orchestration migration supports only SQLite and Postgres"
    )


def assert_tier_orchestration_target_constraint(bind: Engine) -> None:
    tables = set(inspect(bind).get_table_names())
    missing = set(_TIER_ORCHESTRATION_TABLES) - tables
    if missing:
        raise RuntimeError("Tier orchestration tables are missing")
    if bind.dialect.name == "sqlite":
        with bind.connect() as conn:
            for table in _TIER_ORCHESTRATION_TABLES:
                ddl = str(
                    conn.execute(
                        text(
                            "SELECT sql FROM sqlite_master "
                            "WHERE type='table' AND name=:name"
                        ),
                        {"name": table},
                    ).scalar_one()
                )
                compact = re.sub(r"\s+", " ", ddl.lower())
                if "target_tier in (2, 3)" not in compact:
                    raise RuntimeError(
                        f"{table} target-tier constraint is stale"
                    )
        return
    for table in _TIER_ORCHESTRATION_TABLES:
        checks = inspect(bind).get_check_constraints(table)
        if not any(
            "target_tier" in str(item.get("sqltext", "")).lower()
            and "3" in str(item.get("sqltext", ""))
            for item in checks
        ):
            raise RuntimeError(
                f"{table} target-tier constraint is stale"
            )


def run_sqlite_migrations() -> None:
    """Add any missing columns. Never raises."""
    url = settings.DATABASE_URL
    try:
        with engine.connect() as conn:
            if url.startswith("sqlite"):
                existing = {
                    row[1] for row in conn.execute(text("PRAGMA table_info(requests)"))
                }
                for column, ddl in _REQUESTS_TABLE_MIGRATIONS:
                    if column not in existing:
                        conn.execute(text(ddl))
                user_cols = {
                    row[1] for row in conn.execute(text("PRAGMA table_info(users)"))
                }
                if "is_admin" not in user_cols:
                    conn.execute(
                        text(
                            "ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0"
                        )
                    )
                req_cols = {
                    row[1] for row in conn.execute(text("PRAGMA table_info(requests)"))
                }
                if "generation_cancel" not in req_cols:
                    conn.execute(
                        text(
                            "ALTER TABLE requests ADD COLUMN generation_cancel BOOLEAN DEFAULT 0"
                        )
                    )
                settings_cols = {
                    row[1]
                    for row in conn.execute(text("PRAGMA table_info(admin_settings)"))
                }
                if settings_cols and "request_budget_usd" not in settings_cols:
                    conn.execute(
                        text(
                            "ALTER TABLE admin_settings ADD COLUMN request_budget_usd FLOAT"
                        )
                    )
                conn.commit()
                migrate_candidate_revision_target_tier(engine)
                migrate_tier_orchestration_target_tier(engine)
                migrate_phase7a_rollout(engine)
                migrate_phase7b_shadow(engine)
                migrate_phase7c_promotion(engine)
                return

            if url.startswith("postgresql"):
                for column, _ddl in _REQUESTS_TABLE_MIGRATIONS:
                    conn.execute(
                        text(
                            "ALTER TABLE requests ADD COLUMN IF NOT EXISTS "
                            f"{column} TEXT"
                        )
                    )
                conn.execute(
                    text(
                        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                        "is_admin BOOLEAN NOT NULL DEFAULT FALSE"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE requests ADD COLUMN IF NOT EXISTS "
                        "generation_cancel BOOLEAN DEFAULT FALSE"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE admin_settings ADD COLUMN IF NOT EXISTS "
                        "request_budget_usd DOUBLE PRECISION"
                    )
                )
                conn.commit()
                migrate_candidate_revision_target_tier(engine)
                migrate_tier_orchestration_target_tier(engine)
                migrate_phase7a_rollout(engine)
                migrate_phase7b_shadow(engine)
                migrate_phase7c_promotion(engine)
    except Exception:
        pass


__all__ = [
    "assert_candidate_target_tier_constraint",
    "assert_tier_orchestration_target_constraint",
    "migrate_candidate_revision_target_tier",
    "migrate_phase7a_rollout",
    "migrate_phase7b_shadow",
    "migrate_phase7c_promotion",
    "migrate_tier_orchestration_target_tier",
    "phase7a_schema_version",
    "phase7b_schema_version",
    "phase7c_schema_version",
    "run_sqlite_migrations",
]
