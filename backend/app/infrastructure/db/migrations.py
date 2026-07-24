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
    except Exception:
        pass


__all__ = [
    "assert_candidate_target_tier_constraint",
    "migrate_candidate_revision_target_tier",
    "run_sqlite_migrations",
]
