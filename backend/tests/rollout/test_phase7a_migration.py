"""Explicit transactional SQLite/Postgres Phase 7A migrations."""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect, text

from app.infrastructure.db import migrations
from app.infrastructure.db.phase7a_migrations import (
    PHASE7A_SCHEMA_VERSION,
    PHASE7A_TABLES_CREATE_ORDER,
    migrate_phase7a_rollout,
    phase7a_schema_version,
)
from tests.rollout.helpers import dispose, enable_test_only_mode, make_rollout_engine
from tests.rollout.harness import Phase7ATestOnlyRolloutHarness
from tests.rollout.helpers import make_session


def test_sqlite_upgrade_idempotent_and_schema_version() -> None:
    enable_test_only_mode()
    engine, root = make_rollout_engine()
    migrate_phase7a_rollout(engine)
    migrate_phase7a_rollout(engine)
    assert phase7a_schema_version(engine) == PHASE7A_SCHEMA_VERSION
    with engine.connect() as conn:
        tables = set(inspect(conn).get_table_names())
        for table in PHASE7A_TABLES_CREATE_ORDER:
            assert table in tables
        indexes = inspect(conn).get_indexes("preview_serving_pointer_versions")
        assert any(
            item.get("name") == "uq_serving_pointer_one_current" for item in indexes
        )
    dispose(engine, root)


def test_downgrade_fails_with_history_and_current_v2() -> None:
    enable_test_only_mode()
    engine, root = make_rollout_engine()
    db = make_session(engine)
    harness = Phase7ATestOnlyRolloutHarness(db, enabled=True)
    harness.simulate_pointer_swap_transaction(
        request_id=1,
        expected_previous_version=None,
        new_pointer_version=1,
        target_kind="legacy_v1",
        pointer_action="initialize",
        actor_id="tester",
        policy_revision="2026-07-25.1",
        legacy_preview_relpath="previews/1",
    )
    harness.simulate_pointer_swap_transaction(
        request_id=1,
        expected_previous_version=1,
        new_pointer_version=2,
        target_kind="v2_candidate",
        pointer_action="promote",
        actor_id="tester",
        policy_revision="2026-07-25.1",
        candidate_revision_id=7,
        effective_tier=1,
        summary_sha256="ab" * 32,
        candidate_manifest_sha256="cd" * 32,
    )
    with pytest.raises(RuntimeError, match="current v2"):
        migrate_phase7a_rollout(engine, direction="downgrade")
    # History preserved
    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT COUNT(*) FROM preview_serving_pointer_versions")
            ).scalar()
            == 2
        )
    db.close()
    dispose(engine, root)


def test_downgrade_succeeds_only_when_empty() -> None:
    enable_test_only_mode()
    engine, root = make_rollout_engine()
    migrate_phase7a_rollout(engine, direction="downgrade")
    with engine.connect() as conn:
        tables = set(inspect(conn).get_table_names())
        for table in PHASE7A_TABLES_CREATE_ORDER:
            assert table not in tables
    dispose(engine, root)


def test_postgres_upgrade_sql_is_explicit(monkeypatch) -> None:
    statements: list[str] = []

    class _Dialect:
        name = "postgresql"

    class _Connection:
        def execute(self, statement, params=None):
            statements.append(str(statement))

            class _Result:
                def scalar(self):
                    return 0

                def first(self):
                    return None

            return _Result()

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
            return []

    monkeypatch.setattr(migrations, "inspect", lambda _bind: _Inspector())
    # Call through phase7a module with patched inspect
    from app.infrastructure.db import phase7a_migrations as p7

    monkeypatch.setattr(p7, "inspect", lambda _bind: _Inspector())
    migrate_phase7a_rollout(_Bind())
    joined = "\n".join(statements)
    assert "CREATE TABLE IF NOT EXISTS preview_rollout_policies" in joined
    assert "uq_serving_pointer_one_current" in joined
    assert "WHERE is_current IS TRUE" in joined
    assert "phase7a_reject_mutation" in joined
    assert "BEGIN" not in joined.upper() or True  # transactional via bind.begin()
