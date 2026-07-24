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


def enable_test_only_mode() -> None:
    os.environ["PHASE7A_TEST_ONLY_MODE"] = "1"


def make_rollout_engine():
    """Minimal schema for Phase 7A/7B tables + FK parents."""
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
                "request_id INTEGER NOT NULL REFERENCES requests(id))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE candidate_effective_tier_summaries ("
                "id INTEGER PRIMARY KEY)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE candidate_validation_summaries ("
                "id INTEGER PRIMARY KEY)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE candidate_visual_summaries ("
                "id INTEGER PRIMARY KEY)"
            )
        )
        conn.execute(text("INSERT INTO requests VALUES (1)"))
        conn.execute(text("INSERT INTO requests VALUES (42)"))
        conn.execute(
            text("INSERT INTO candidate_revisions VALUES (7, 1)")
        )
        conn.execute(
            text("INSERT INTO candidate_effective_tier_summaries VALUES (1)")
        )
    migrate_phase7a_rollout(engine)
    migrate_phase7b_shadow(engine)
    return engine, root


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
    "make_rollout_engine",
    "make_session",
]
