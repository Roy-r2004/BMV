from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from app.infrastructure.db import migrations
from app.infrastructure.db.migrations import (
    assert_tier_orchestration_target_constraint,
    migrate_tier_orchestration_target_tier,
)


TABLES = (
    "candidate_tier_orchestration_attempts",
    "candidate_tier_extension_manifests",
    "candidate_lower_tier_preservation_audits",
    "candidate_tier_generation_results",
    "candidate_tier_validation_results",
    "candidate_tier_visual_outcomes",
    "candidate_effective_tier_summaries",
)


def _old_engine():
    root = Path(__file__).parent / ".migration" / uuid.uuid4().hex
    root.mkdir(parents=True)
    engine = create_engine(f"sqlite:///{root / 'phase6b.db'}")
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text("CREATE TABLE requests (id INTEGER PRIMARY KEY)"))
        conn.execute(
            text("CREATE TABLE candidate_revisions (id INTEGER PRIMARY KEY)")
        )
        conn.execute(
            text(
                "CREATE TABLE candidate_visual_summaries "
                "(id INTEGER PRIMARY KEY)"
            )
        )
        conn.execute(text("INSERT INTO requests VALUES (17)"))
        conn.execute(
            text(
                "CREATE TABLE candidate_tier_orchestration_attempts ("
                "id INTEGER PRIMARY KEY, "
                "request_id INTEGER NOT NULL REFERENCES requests(id), "
                "target_tier INTEGER NOT NULL, "
                "status TEXT NOT NULL, "
                "payload_json TEXT NOT NULL, "
                "payload_sha256 TEXT NOT NULL, "
                "created_at TEXT NOT NULL, "
                "CONSTRAINT ck_tier_attempt_target CHECK (target_tier = 2))"
            )
        )
        for table in TABLES[1:-1]:
            constraint = {
                "candidate_tier_extension_manifests": "ck_tier_manifest_target",
                "candidate_lower_tier_preservation_audits": "ck_tier_audit_target",
                "candidate_tier_generation_results": "ck_tier_generation_target",
                "candidate_tier_validation_results": "ck_tier_validation_target",
                "candidate_tier_visual_outcomes": "ck_tier_visual_target",
            }[table]
            conn.execute(
                text(
                    f"CREATE TABLE {table} ("
                    "id INTEGER PRIMARY KEY, "
                    "orchestration_attempt_id INTEGER NOT NULL "
                    "REFERENCES candidate_tier_orchestration_attempts(id), "
                    "target_tier INTEGER NOT NULL, "
                    "payload_json TEXT NOT NULL, "
                    "payload_sha256 TEXT NOT NULL, "
                    "created_at TEXT NOT NULL, "
                    f"CONSTRAINT {constraint} CHECK (target_tier = 2))"
                )
            )
        conn.execute(
            text(
                "CREATE TABLE candidate_effective_tier_summaries ("
                "id INTEGER PRIMARY KEY, "
                "orchestration_attempt_id INTEGER NOT NULL "
                "REFERENCES candidate_tier_orchestration_attempts(id), "
                "target_tier INTEGER NOT NULL, "
                "status TEXT NOT NULL, "
                "highest_accepted_tier INTEGER NOT NULL, "
                "payload_json TEXT NOT NULL, "
                "payload_sha256 TEXT NOT NULL, "
                "created_at TEXT NOT NULL, "
                "CONSTRAINT ck_effective_tier_target "
                "CHECK (target_tier = 2), "
                "CONSTRAINT ck_effective_tier_status CHECK (status IN "
                "('tier_2_accepted','tier_2_failed_serving_tier_1')), "
                "CONSTRAINT ck_highest_accepted_tier "
                "CHECK (highest_accepted_tier IN (1, 2)))"
            )
        )
        for table in TABLES:
            conn.execute(
                text(f"CREATE INDEX ix_old_{table}_hash ON {table}(payload_sha256)")
            )
        payload = '{"z":3,"a":{"preserve":"bytes"},"spacing":"x  y"}'
        digest = "f" * 64
        created = "2026-07-24T10:11:12.123456"
        conn.execute(
            text(
                "INSERT INTO candidate_tier_orchestration_attempts "
                "VALUES (31,17,2,'succeeded',:payload,:digest,:created)"
            ),
            {"payload": payload, "digest": digest, "created": created},
        )
        for table in TABLES[1:-1]:
            conn.execute(
                text(
                    f"INSERT INTO {table} VALUES "
                    "(31,31,2,:payload,:digest,:created)"
                ),
                {"payload": payload, "digest": digest, "created": created},
            )
        conn.execute(
            text(
                "INSERT INTO candidate_effective_tier_summaries VALUES "
                "(31,31,2,'tier_2_accepted',2,:payload,:digest,:created)"
            ),
            {"payload": payload, "digest": digest, "created": created},
        )
    return engine, root


def _snapshot(engine) -> dict:
    result = {}
    with engine.connect() as conn:
        for table in TABLES:
            columns = (
                "id,target_tier,status,payload_json,payload_sha256,created_at"
                if table == TABLES[0]
                else (
                    "id,orchestration_attempt_id,target_tier,status,"
                    "highest_accepted_tier,payload_json,payload_sha256,created_at"
                    if table == TABLES[-1]
                    else (
                        "id,orchestration_attempt_id,target_tier,payload_json,"
                        "payload_sha256,created_at"
                    )
                )
            )
            rows = [tuple(row) for row in conn.execute(
                text(f"SELECT {columns} FROM {table} ORDER BY id")
            )]
            result[table] = {
                "rows": rows,
                "bytes": json.dumps(
                    rows,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8"),
                "indexes": inspect(conn).get_indexes(table),
                "foreign_keys": inspect(conn).get_foreign_keys(table),
            }
    return result


def _dispose(engine, root: Path) -> None:
    engine.dispose()
    shutil.rmtree(root)


def test_upgrade_preserves_all_tier_2_rows_byte_exact_and_relationships() -> None:
    engine, root = _old_engine()
    before = _snapshot(engine)
    migrate_tier_orchestration_target_tier(engine)
    assert_tier_orchestration_target_constraint(engine)
    after = _snapshot(engine)
    for table in TABLES:
        assert before[table]["rows"] == after[table]["rows"]
        assert before[table]["bytes"] == after[table]["bytes"]
        assert before[table]["indexes"] == after[table]["indexes"]
        assert all(
            foreign_key in after[table]["foreign_keys"]
            for foreign_key in before[table]["foreign_keys"]
        )
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []
        for table in TABLES:
            columns = {item["name"] for item in inspect(conn).get_columns(table)}
            assert {
                "accepted_tier_2_revision_id",
                "accepted_tier_2_visual_summary_id",
                "accepted_tier_2_effective_summary_id",
                "lower_tier_effective_summary_sha256",
            } <= columns
            row = conn.execute(
                text(
                    f"SELECT accepted_tier_2_revision_id, "
                    f"accepted_tier_2_visual_summary_id, "
                    f"accepted_tier_2_effective_summary_id, "
                    f"lower_tier_effective_summary_sha256 FROM {table}"
                )
            ).one()
            assert tuple(row) == (None, None, None, None)
    _dispose(engine, root)


def test_upgrade_is_idempotent_and_downgrade_keeps_tier_2_bytes() -> None:
    engine, root = _old_engine()
    before = _snapshot(engine)
    migrate_tier_orchestration_target_tier(engine)
    migrate_tier_orchestration_target_tier(engine)
    migrate_tier_orchestration_target_tier(engine, direction="downgrade")
    after = _snapshot(engine)
    for table in TABLES:
        assert before[table]["rows"] == after[table]["rows"]
        assert before[table]["bytes"] == after[table]["bytes"]
        assert before[table]["indexes"] == after[table]["indexes"]
        assert all(
            foreign_key in after[table]["foreign_keys"]
            for foreign_key in before[table]["foreign_keys"]
        )
    with engine.begin() as conn:
        try:
            conn.execute(
                text(
                    "INSERT INTO candidate_tier_generation_results "
                    "(id,orchestration_attempt_id,target_tier,payload_json,"
                    "payload_sha256,created_at) VALUES "
                    "(32,31,3,'{}',:digest,'2026-07-24')"
                ),
                {"digest": "a" * 64},
            )
        except Exception:
            pass
        else:
            raise AssertionError("Downgraded table accepted Tier 3")
    _dispose(engine, root)


def test_downgrade_with_any_tier_3_row_fails_before_schema_change() -> None:
    engine, root = _old_engine()
    migrate_tier_orchestration_target_tier(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO candidate_tier_generation_results "
                "(id,orchestration_attempt_id,target_tier,payload_json,"
                "payload_sha256,created_at) VALUES "
                "(32,31,3,'{}',:digest,'2026-07-24')"
            ),
            {"digest": "a" * 64},
        )
    try:
        migrate_tier_orchestration_target_tier(
            engine,
            direction="downgrade",
        )
    except RuntimeError as exc:
        assert "rejected existing values" in str(exc)
    else:
        raise AssertionError("Downgrade accepted an existing Tier 3 row")
    assert_tier_orchestration_target_constraint(engine)
    with engine.connect() as conn:
        assert conn.execute(
            text(
                "SELECT id,target_tier FROM "
                "candidate_tier_generation_results ORDER BY id"
            )
        ).all() == [(31, 2), (32, 3)]
    _dispose(engine, root)


def test_postgres_upgrade_is_explicit_for_all_seven_tables(monkeypatch) -> None:
    statements: list[str] = []
    validations: list[str] = []

    class _Dialect:
        name = "postgresql"

    class _Connection:
        def execute(self, statement):
            statements.append(str(statement))

    class _Transaction:
        def __enter__(self):
            return _Connection()

        def __exit__(self, exc_type, exc, traceback):
            return False

    class _Bind:
        dialect = _Dialect()

        def begin(self):
            return _Transaction()

    class _Inspector:
        @staticmethod
        def get_table_names():
            return list(TABLES)

    monkeypatch.setattr(
        migrations,
        "_validate_tier_orchestration_rows",
        lambda _bind, *, direction: validations.append(direction),
    )
    monkeypatch.setattr(migrations, "inspect", lambda _bind: _Inspector())
    migrate_tier_orchestration_target_tier(_Bind())
    assert validations == ["upgrade"]
    assert sum("CHECK (target_tier IN (2, 3))" in item for item in statements) == 7
    assert sum(
        "ADD COLUMN IF NOT EXISTS accepted_tier_2_revision_id" in item
        for item in statements
    ) == 7
    assert any("tier_3_failed_serving_tier_2" in item for item in statements)
