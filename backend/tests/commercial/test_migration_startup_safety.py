"""Migration startup fail-closed and readiness tests."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.application.bootstrap.startup import (
    StartupMigrationError,
    bootstrap_database,
    redact_database_url,
    verify_schema_ready,
)
from app.infrastructure.db.base import Base
from app.infrastructure.db.commercial_migrations import (
    COMMERCIAL_SCHEMA_VERSION,
    migrate_commercial_expanded_preview,
)
from app.infrastructure.db.phase7a_migrations import migrate_phase7a_rollout
from app.infrastructure.db.phase7b_migrations import migrate_phase7b_shadow
from app.infrastructure.db.phase7c_migrations import migrate_phase7c_promotion
from app.infrastructure.db.phase7d_migrations import migrate_phase7d_breaker
from app.infrastructure.db.phase7e_migrations import migrate_phase7e_ops
from app.infrastructure.db.phase7f_migrations import (
    PHASE7F_SCHEMA_VERSION,
    migrate_phase7f_percent_canary,
)
from app.domain.models.request import Request
from app.domain.models.user import User
from tests.commercial.helpers import make_commercial_engine


def _seed_parents(engine):
    Base.metadata.create_all(bind=engine, tables=[Request.__table__, User.__table__])
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS candidate_revisions ("
                "id INTEGER PRIMARY KEY, request_id INTEGER, workspace_relpath TEXT, "
                "file_manifest_sha256 CHAR(64), upstream_manifest_sha256 CHAR(64))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS candidate_effective_tier_summaries ("
                "id INTEGER PRIMARY KEY, request_id INTEGER, status TEXT, "
                "highest_accepted_tier INTEGER, summary_sha256 CHAR(64), "
                "phase4_validation_summary_id INTEGER, phase5_visual_summary_id INTEGER, "
                "last_accepted_candidate_revision_id INTEGER, "
                "derived_candidate_revision_id INTEGER, accepted_tier_1_revision_id INTEGER)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS candidate_validation_summaries ("
                "id INTEGER PRIMARY KEY, status TEXT)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS candidate_visual_summaries ("
                "id INTEGER PRIMARY KEY, status TEXT)"
            )
        )


def test_complete_schema_passes_readiness():
    engine, root = make_commercial_engine()
    try:
        result = verify_schema_ready(engine)
        assert result.ready is True
        assert result.schema_versions_found["phase7f"] == PHASE7F_SCHEMA_VERSION
        assert result.schema_versions_found["commercial"] == COMMERCIAL_SCHEMA_VERSION
        assert not result.missing_versions
    finally:
        engine.dispose()
        shutil.rmtree(root, ignore_errors=True)


def test_missing_phase7f_blocks_readiness():
    root = Path(tempfile.mkdtemp(prefix="ready-miss-"))
    engine = create_engine(f"sqlite:///{root / 't.db'}")
    try:
        _seed_parents(engine)
        migrate_phase7a_rollout(engine)
        migrate_phase7b_shadow(engine)
        migrate_phase7c_promotion(engine)
        migrate_phase7d_breaker(engine)
        migrate_phase7e_ops(engine)
        # intentionally skip 7F + commercial
        result = verify_schema_ready(engine)
        assert result.ready is False
        assert any("phase7f" in item for item in result.missing_versions)
    finally:
        engine.dispose()
        shutil.rmtree(root, ignore_errors=True)


def test_migration_exception_blocks_startup():
    root = Path(tempfile.mkdtemp(prefix="boot-fail-"))
    engine = create_engine(f"sqlite:///{root / 't.db'}")

    def _boom():
        raise RuntimeError("forced migration failure")

    try:
        with pytest.raises(StartupMigrationError) as exc:
            bootstrap_database(
                engine=engine,
                create_all=Base.metadata.create_all,
                run_legacy_column_migrations=_boom,
                database_url="sqlite:///./secret_user:secret_pass@/tmp/x.db",
            )
        assert "forced migration failure" in (exc.value.result.failure_reason or "")
        assert "secret_pass" not in (exc.value.result.failure_reason or "")
    finally:
        engine.dispose()
        shutil.rmtree(root, ignore_errors=True)


def test_credentials_not_exposed_in_redaction():
    redacted = redact_database_url(
        "postgresql://user:supersecret@db.example:5432/buildmyversion"
    )
    assert "supersecret" not in redacted
    assert "user:" not in redacted
    assert "db.example" in redacted


def test_repeat_migration_idempotent():
    engine, root = make_commercial_engine()
    try:
        migrate_phase7f_percent_canary(engine)
        migrate_commercial_expanded_preview(engine)
        migrate_phase7f_percent_canary(engine)
        migrate_commercial_expanded_preview(engine)
        result = verify_schema_ready(engine)
        assert result.ready is True
    finally:
        engine.dispose()
        shutil.rmtree(root, ignore_errors=True)


def test_successful_boot_with_complete_schema(monkeypatch):
    engine, root = make_commercial_engine()

    def _noop_legacy():
        return None

    def _noop_create_all(*, bind):
        return None

    # Schema already complete via make_commercial_engine; bootstrap must remain idempotent.
    from app.application.bootstrap import startup as startup_mod

    monkeypatch.setattr(startup_mod, "run_required_migrations", lambda _engine: None)
    try:
        result = bootstrap_database(
            engine=engine,
            create_all=_noop_create_all,
            run_legacy_column_migrations=_noop_legacy,
            database_url=f"sqlite:///{root / 't.db'}",
        )
        assert result.ready is True
        assert result.migration_completed is True
        assert result.schema_versions_found["phase7f"] == PHASE7F_SCHEMA_VERSION
    finally:
        engine.dispose()
        shutil.rmtree(root, ignore_errors=True)
