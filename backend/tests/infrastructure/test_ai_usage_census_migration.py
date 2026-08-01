"""The census columns must be addable to a live `ai_usage_events` table.

Additive and nullable with no default, so Postgres takes a catalogue-only lock
and no table rewrite — the migration runs while a generation is in flight. The
column set is also what the report's "measured vs reconstructed" split rests
on: every pre-existing row keeps `usable = NULL`, which the census reads as
"not adjudicated" rather than counting it as a success.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402
from sqlalchemy import create_engine, inspect, text  # noqa: E402

from app.infrastructure.db.migrations import migrate_ai_usage_census  # noqa: E402

#: Spelled out rather than imported from the migration, so the test cannot be
#: satisfied by deleting a column from the list it is checking.
_EXPECTED_COLUMNS = (
    "stage",
    "writer",
    "attempt",
    "finish_reason",
    "output_chars",
    "usable",
    "unusable_reason",
    "ops_applied",
)

_LEGACY_TABLE = """
CREATE TABLE ai_usage_events (
  id INTEGER PRIMARY KEY,
  created_at TEXT,
  provider VARCHAR NOT NULL,
  model VARCHAR NOT NULL,
  purpose VARCHAR NOT NULL,
  request_id INTEGER,
  prompt_tokens INTEGER NOT NULL,
  completion_tokens INTEGER NOT NULL,
  total_tokens INTEGER NOT NULL,
  cost_usd FLOAT,
  success BOOLEAN NOT NULL,
  error TEXT,
  latency_ms INTEGER
)
"""


@pytest.fixture()
def legacy_engine(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.execute(text(_LEGACY_TABLE))
        conn.execute(
            text(
                "INSERT INTO ai_usage_events "
                "(provider, model, purpose, request_id, prompt_tokens, "
                " completion_tokens, total_tokens, success, latency_ms) "
                "VALUES ('openrouter', 'z-ai/glm-5.2', 'build', 67, 0, 0, 0, 1, 90000)"
            )
        )
    yield engine
    engine.dispose()


def test_the_migration_adds_every_census_column(legacy_engine) -> None:
    migrate_ai_usage_census(legacy_engine)

    with legacy_engine.connect() as conn:
        columns = {c["name"] for c in inspect(conn).get_columns("ai_usage_events")}

    for name in _EXPECTED_COLUMNS:
        assert name in columns, f"{name} was not added"


def test_the_migration_is_idempotent(legacy_engine) -> None:
    migrate_ai_usage_census(legacy_engine)
    migrate_ai_usage_census(legacy_engine)

    with legacy_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM ai_usage_events")).scalar() == 1


def test_an_existing_row_keeps_its_columns_and_gains_a_null_verdict(
    legacy_engine,
) -> None:
    """A pre-census row must not be back-filled as usable.

    Reading NULL as success is the same mistake as reading 200 as success, one
    layer down.
    """

    migrate_ai_usage_census(legacy_engine)

    with legacy_engine.connect() as conn:
        row = conn.execute(
            text("SELECT success, usable, stage, ops_applied, latency_ms "
                 "FROM ai_usage_events")
        ).mappings().one()

    assert row["success"] == 1
    assert row["usable"] is None
    assert row["stage"] is None
    assert row["ops_applied"] is None
    assert row["latency_ms"] == 90000


def test_the_migration_is_a_no_op_when_the_table_does_not_exist(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    try:
        migrate_ai_usage_census(engine)
    finally:
        engine.dispose()


def test_an_unsupported_dialect_fails_closed(monkeypatch, legacy_engine) -> None:
    """Silently skipping on an unknown backend would ship a schema that the
    census then reads as "no rows adjudicated, ever"."""

    monkeypatch.setattr(type(legacy_engine.dialect), "name", "mysql", raising=False)

    with pytest.raises(RuntimeError, match="unsupported dialect"):
        migrate_ai_usage_census(legacy_engine)
