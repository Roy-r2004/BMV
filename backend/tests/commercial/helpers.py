"""Helpers for commercial Expanded Preview / staging readiness tests."""
from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.domain.models.expanded_preview import (
    ExpandedPreviewGenerationClaimRecord,
    ExpandedPreviewPublicationRecord,
    ExpandedPreviewRequestRecord,
    ExpandedPreviewStatusEventRecord,
)
from app.domain.models.request import Request
from app.domain.models.user import User
from app.infrastructure.db.base import Base
from app.infrastructure.db.commercial_migrations import migrate_commercial_expanded_preview
from app.infrastructure.db.phase7a_migrations import migrate_phase7a_rollout
from app.infrastructure.db.phase7b_migrations import migrate_phase7b_shadow
from app.infrastructure.db.phase7c_migrations import migrate_phase7c_promotion
from app.infrastructure.db.phase7d_migrations import migrate_phase7d_breaker
from app.infrastructure.db.phase7e_migrations import migrate_phase7e_ops
from app.infrastructure.db.phase7f_migrations import migrate_phase7f_percent_canary


def make_commercial_engine():
    root = Path(tempfile.mkdtemp(prefix="commercial-"))
    db = root / "t.db"
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(
        bind=engine,
        tables=[Request.__table__, User.__table__],
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS candidate_revisions ("
                "id INTEGER PRIMARY KEY, request_id INTEGER, workspace_relpath TEXT, "
                "file_manifest_sha256 CHAR(64), upstream_manifest_sha256 CHAR(64), "
                "target_tier INTEGER DEFAULT 1, status TEXT)"
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
                "id INTEGER PRIMARY KEY, status TEXT, candidate_revision_id INTEGER)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS candidate_visual_summaries ("
                "id INTEGER PRIMARY KEY, status TEXT, candidate_revision_id INTEGER, "
                "artifact_sha256 CHAR(64))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS candidate_screenshots ("
                "id INTEGER PRIMARY KEY, candidate_revision_id INTEGER)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS candidate_visual_findings ("
                "id INTEGER PRIMARY KEY, candidate_revision_id INTEGER, severity TEXT)"
            )
        )
    migrate_phase7a_rollout(engine)
    migrate_phase7b_shadow(engine)
    migrate_phase7c_promotion(engine)
    migrate_phase7d_breaker(engine)
    migrate_phase7e_ops(engine)
    migrate_phase7f_percent_canary(engine)
    migrate_commercial_expanded_preview(engine)
    Base.metadata.create_all(
        bind=engine,
        tables=[
            ExpandedPreviewRequestRecord.__table__,
            ExpandedPreviewStatusEventRecord.__table__,
            ExpandedPreviewGenerationClaimRecord.__table__,
            ExpandedPreviewPublicationRecord.__table__,
        ],
    )
    return engine, root


def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def seed_request(db, *, email="customer@example.com") -> Request:
    req = Request(
        business_name="Acme",
        business_description="Widgets",
        email=email,
        status="preview_ready",
        customer_access_token="token-acme-1",
        generated_pages='{"preview_app":{"url":"/api/preview-apps/1/","status":"ready"}}',
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def fake_tier1(request_id: int = 1):
    rev = SimpleNamespace(
        id=101,
        request_id=request_id,
        target_tier=1,
        file_manifest_sha256="a" * 64,
        workspace_relpath="1/rev101",
    )
    visual = SimpleNamespace(
        id=201,
        request_id=request_id,
        candidate_revision_id=101,
        artifact_sha256="b" * 64,
        status="candidate_visual_accepted",
    )
    phase5 = {
        "preview_contract": {
            "status": "candidate_visual_accepted",
            "target_tier": 1,
            "candidate_revision": {
                "id": 101,
                "file_manifest_sha256": "a" * 64,
            },
            "visual_evaluation_summary": {"id": 201, "sha256": "b" * 64},
        }
    }
    return phase5, rev, visual
