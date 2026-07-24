"""Phase 7B additive migration preserves Phase 7A shadow history."""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect, text

from app.infrastructure.db.phase7a_migrations import migrate_phase7a_rollout
from app.infrastructure.db.phase7b_migrations import (
    PHASE7B_SCHEMA_VERSION,
    migrate_phase7b_shadow,
    phase7b_schema_version,
)
from tests.rollout.helpers import dispose, enable_test_only_mode, make_rollout_engine


def test_upgrade_preserves_phase7a_shadow_rows() -> None:
    enable_test_only_mode()
    # Build 7A-only then insert historical row, then upgrade 7B
    from pathlib import Path
    import uuid
    import shutil

    root = Path(__file__).parent / ".tmp" / uuid.uuid4().hex
    root.mkdir(parents=True)
    engine = create_engine(f"sqlite:///{root / 'p7b.db'}")
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text("CREATE TABLE requests (id INTEGER PRIMARY KEY)"))
        conn.execute(
            text(
                "CREATE TABLE candidate_revisions ("
                "id INTEGER PRIMARY KEY, request_id INTEGER NOT NULL)"
            )
        )
        conn.execute(
            text("CREATE TABLE candidate_effective_tier_summaries (id INTEGER PRIMARY KEY)")
        )
        conn.execute(
            text("CREATE TABLE candidate_validation_summaries (id INTEGER PRIMARY KEY)")
        )
        conn.execute(
            text("CREATE TABLE candidate_visual_summaries (id INTEGER PRIMARY KEY)")
        )
        conn.execute(text("INSERT INTO requests VALUES (1)"))
    migrate_phase7a_rollout(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO preview_shadow_evaluations ("
                "request_id,served_target_kind,comparison_policy_revision,"
                "telemetry_json,telemetry_sha256,result_status,"
                "no_serving_mutation,created_at,evaluation_sha256"
                ") VALUES ("
                "1,'none','2026-07-25.1','{}',:t,'completed',1,:ts,:e)"
            ),
            {"t": "a" * 64, "ts": datetime.utcnow().isoformat(), "e": "b" * 64},
        )
        before = conn.execute(
            text(
                "SELECT id,request_id,evaluation_sha256,created_at "
                "FROM preview_shadow_evaluations"
            )
        ).all()
    migrate_phase7b_shadow(engine)
    assert phase7b_schema_version(engine) == PHASE7B_SCHEMA_VERSION
    with engine.connect() as conn:
        after = conn.execute(
            text(
                "SELECT id,request_id,evaluation_sha256,created_at "
                "FROM preview_shadow_evaluations"
            )
        ).all()
        assert after == before
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(preview_shadow_evaluations)"))}
        assert {
            "shadow_attempt_uuid",
            "terminal_of_evaluation_id",
            "mode",
            "idempotency_key",
            "eligibility_sha256",
        } <= cols
        indexes = inspect(conn).get_indexes("preview_shadow_evaluations")
        names = {i.get("name") for i in indexes}
        assert "uq_shadow_one_pending_per_attempt" in names
        assert "uq_shadow_one_terminal_per_pending" in names
    engine.dispose()
    shutil.rmtree(root, ignore_errors=True)


def test_downgrade_fails_when_lineage_present() -> None:
    enable_test_only_mode()
    engine, root = make_rollout_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO preview_shadow_evaluations ("
                "request_id,served_target_kind,comparison_policy_revision,"
                "telemetry_json,telemetry_sha256,result_status,"
                "no_serving_mutation,created_at,evaluation_sha256,"
                "shadow_attempt_uuid"
                ") VALUES ("
                "1,'none','p','{}',:t,'pending',1,:ts,:e,:u)"
            ),
            {
                "t": "a" * 64,
                "ts": datetime.utcnow().isoformat(),
                "e": "b" * 64,
                "u": "22222222-2222-2222-2222-222222222222",
            },
        )
    with pytest.raises(RuntimeError, match="shadow lineage"):
        migrate_phase7b_shadow(engine, direction="downgrade")
    dispose(engine, root)


def test_postgres_upgrade_sql_explicit(monkeypatch) -> None:
    statements: list[str] = []

    class _Dialect:
        name = "postgresql"

    class _Connection:
        def execute(self, statement, params=None):
            statements.append(str(statement))

            class _R:
                def scalar(self):
                    return 0

                def first(self):
                    return None

            return _R()

    class _Transaction:
        def __enter__(self):
            return _Connection()

        def __exit__(self, *a):
            return False

    class _Bind:
        dialect = _Dialect()

        def begin(self):
            return _Transaction()

    class _Inspector:
        @staticmethod
        def get_table_names():
            return ["preview_shadow_evaluations"]

        @staticmethod
        def get_columns(_table):
            return [{"name": "id"}]

    from app.infrastructure.db import phase7b_migrations as p7b

    monkeypatch.setattr(p7b, "inspect", lambda _b: _Inspector())
    migrate_phase7b_shadow(_Bind())
    joined = "\n".join(statements)
    assert "ADD COLUMN IF NOT EXISTS shadow_attempt_uuid" in joined
    assert "terminal_of_evaluation_id" in joined
    assert "uq_shadow_one_terminal_per_pending" in joined
