"""Shared fixtures for Phase 7A rollout tests."""
from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.infrastructure.db.base import Base
from app.infrastructure.db.phase7a_migrations import migrate_phase7a_rollout
from app.infrastructure.db.phase7b_migrations import migrate_phase7b_shadow
from app.infrastructure.db.phase7c_migrations import migrate_phase7c_promotion


def enable_test_only_mode() -> None:
    os.environ["PHASE7A_TEST_ONLY_MODE"] = "1"


def make_rollout_engine(*, phase7c: bool = True):
    """Minimal schema for Phase 7A/7B/7C tables + FK parents.

    Phase 7C columns are migrated by default because ORM models include them.
    """
    root = Path(__file__).parent / ".tmp" / uuid.uuid4().hex
    root.mkdir(parents=True)
    engine = create_engine(f"sqlite:///{root / 'phase7a.db'}")
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text("CREATE TABLE requests (id INTEGER PRIMARY KEY)"))
        conn.execute(
            text(
                "CREATE TABLE candidate_revisions ("
                "id INTEGER PRIMARY KEY, "
                "request_id INTEGER NOT NULL REFERENCES requests(id), "
                "workspace_relpath TEXT, "
                "file_manifest_sha256 CHAR(64), "
                "upstream_manifest_sha256 CHAR(64))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE candidate_effective_tier_summaries ("
                "id INTEGER PRIMARY KEY, "
                "request_id INTEGER, "
                "status TEXT, "
                "highest_accepted_tier INTEGER, "
                "summary_sha256 CHAR(64), "
                "phase4_validation_summary_id INTEGER, "
                "phase5_visual_summary_id INTEGER, "
                "last_accepted_candidate_revision_id INTEGER, "
                "derived_candidate_revision_id INTEGER, "
                "accepted_tier_1_revision_id INTEGER)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE candidate_validation_summaries ("
                "id INTEGER PRIMARY KEY, "
                "status TEXT)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE candidate_visual_summaries ("
                "id INTEGER PRIMARY KEY, "
                "status TEXT)"
            )
        )
        conn.execute(text("INSERT INTO requests VALUES (1)"))
        conn.execute(text("INSERT INTO requests VALUES (42)"))
        conn.execute(
            text(
                "INSERT INTO candidate_revisions "
                "(id, request_id, workspace_relpath, file_manifest_sha256, "
                "upstream_manifest_sha256) VALUES "
                "(7, 1, 'req-1/rev-7', :m, :m)"
            ),
            {"m": "b" * 64},
        )
        conn.execute(
            text(
                "INSERT INTO candidate_validation_summaries (id, status) "
                "VALUES (10, 'candidate_runtime_validated')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO candidate_visual_summaries (id, status) "
                "VALUES (11, 'candidate_visual_accepted')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO candidate_effective_tier_summaries "
                "(id, request_id, status, highest_accepted_tier, summary_sha256, "
                "phase4_validation_summary_id, phase5_visual_summary_id, "
                "last_accepted_candidate_revision_id, derived_candidate_revision_id, "
                "accepted_tier_1_revision_id) "
                "VALUES (1, 1, 'tier_2_accepted', 2, :s, 10, 11, 7, 7, 7)"
            ),
            {"s": "a" * 64},
        )
    migrate_phase7a_rollout(engine)
    migrate_phase7b_shadow(engine)
    if phase7c:
        migrate_phase7c_promotion(engine)
    return engine, root


def make_phase7c_engine():
    return make_rollout_engine(phase7c=True)


def make_session(engine):
    Session = sessionmaker(bind=engine)
    return Session()


def dispose(engine, root: Path) -> None:
    engine.dispose()
    shutil.rmtree(root, ignore_errors=True)


def import_rollout_models():
    # Ensure SQLAlchemy mappers are registered.
    import app.domain.models.rollout  # noqa: F401
    return Base


__all__ = [
    "dispose",
    "enable_test_only_mode",
    "import_rollout_models",
    "make_phase7c_engine",
    "make_rollout_engine",
    "make_session",
]
