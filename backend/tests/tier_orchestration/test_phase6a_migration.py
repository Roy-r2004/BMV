from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from app.infrastructure.db import migrations
from app.infrastructure.db.migrations import (
    assert_candidate_target_tier_constraint,
    migrate_candidate_revision_target_tier,
)


def _old_engine():
    root = Path(__file__).parent / ".migration" / uuid.uuid4().hex
    root.mkdir(parents=True)
    engine = create_engine(f"sqlite:///{root / 'phase6a.db'}")
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text("CREATE TABLE requests (id INTEGER PRIMARY KEY)"))
        conn.execute(
            text(
                "CREATE TABLE candidate_revisions ("
                "id INTEGER PRIMARY KEY, "
                "request_id INTEGER NOT NULL REFERENCES requests(id), "
                "revision_uuid TEXT NOT NULL, "
                "target_tier INTEGER NOT NULL, "
                "created_at TEXT NOT NULL, "
                "CONSTRAINT ck_candidate_revision_target_tier "
                "CHECK (target_tier = 1))"
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX uq_phase6_uuid "
                "ON candidate_revisions(revision_uuid)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE candidate_children ("
                "id INTEGER PRIMARY KEY, "
                "candidate_revision_id INTEGER NOT NULL "
                "REFERENCES candidate_revisions(id))"
            )
        )
        conn.execute(text("INSERT INTO requests VALUES (1)"))
        conn.execute(
            text(
                "INSERT INTO candidate_revisions VALUES "
                "(7, 1, 'accepted-tier-one', 1, '2026-07-24T10:00:00')"
            )
        )
        conn.execute(text("INSERT INTO candidate_children VALUES (1, 7)"))
    return engine, root


def test_upgrade_preserves_rows_foreign_keys_and_indexes() -> None:
    engine, root = _old_engine()
    before = {}
    with engine.connect() as conn:
        before["rows"] = conn.execute(
            text("SELECT * FROM candidate_revisions")
        ).all()
        before["indexes"] = inspect(conn).get_indexes(
            "candidate_revisions"
        )
        before["foreign_keys"] = inspect(conn).get_foreign_keys(
            "candidate_revisions"
        )
    migrate_candidate_revision_target_tier(engine)
    assert_candidate_target_tier_constraint(engine)
    with engine.begin() as conn:
        assert conn.execute(
            text("SELECT * FROM candidate_revisions")
        ).all() == before["rows"]
        assert inspect(conn).get_indexes("candidate_revisions") == before[
            "indexes"
        ]
        assert inspect(conn).get_foreign_keys(
            "candidate_revisions"
        ) == before["foreign_keys"]
        assert inspect(conn).get_foreign_keys("candidate_children")[0][
            "referred_table"
        ] == "candidate_revisions"
        assert conn.execute(
            text("PRAGMA foreign_key_check")
        ).all() == []
        conn.execute(
            text(
                "INSERT INTO candidate_revisions VALUES "
                "(8, 1, 'tier-two', 2, '2026-07-24T11:00:00')"
            )
        )
    engine.dispose()
    shutil.rmtree(root)


def test_downgrade_succeeds_when_only_tier_one_exists() -> None:
    engine, root = _old_engine()
    migrate_candidate_revision_target_tier(engine)
    migrate_candidate_revision_target_tier(engine, direction="downgrade")
    with engine.begin() as conn:
        assert conn.execute(
            text("SELECT id, target_tier FROM candidate_revisions")
        ).all() == [(7, 1)]
        try:
            conn.execute(
                text(
                    "INSERT INTO candidate_revisions VALUES "
                    "(8, 1, 'tier-two', 2, '2026-07-24T11:00:00')"
                )
            )
        except Exception:
            pass
        else:
            raise AssertionError("Downgraded constraint accepted Tier 2")
    engine.dispose()
    shutil.rmtree(root)


def test_downgrade_fails_transactionally_with_higher_tiers() -> None:
    engine, root = _old_engine()
    migrate_candidate_revision_target_tier(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO candidate_revisions VALUES "
                "(8, 1, 'tier-two', 2, '2026-07-24T11:00:00')"
            )
        )
    try:
        migrate_candidate_revision_target_tier(
            engine,
            direction="downgrade",
        )
    except RuntimeError as exc:
        assert "rejected existing values" in str(exc)
    else:
        raise AssertionError("Downgrade accepted an existing Tier 2 row")
    assert_candidate_target_tier_constraint(engine)
    with engine.connect() as conn:
        assert conn.execute(
            text(
                "SELECT id, target_tier FROM candidate_revisions ORDER BY id"
            )
        ).all() == [(7, 1), (8, 2)]
    engine.dispose()
    shutil.rmtree(root)


def test_postgres_path_validates_then_replaces_named_constraint(
    monkeypatch,
) -> None:
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
            return ["candidate_revisions"]

    monkeypatch.setattr(
        migrations,
        "_validate_candidate_target_rows",
        lambda _bind, *, direction: validations.append(direction),
    )
    monkeypatch.setattr(migrations, "inspect", lambda _bind: _Inspector())
    migrate_candidate_revision_target_tier(_Bind())
    assert validations == ["upgrade"]
    assert any(
        "DROP CONSTRAINT IF EXISTS ck_candidate_revision_target_tier"
        in item
        for item in statements
    )
    assert any(
        "CHECK (target_tier IN (1, 2, 3))" in item
        for item in statements
    )
