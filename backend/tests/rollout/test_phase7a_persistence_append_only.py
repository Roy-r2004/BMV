"""Append-only DB protections — repository and direct SQL."""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import text

from app.application.rollout.policy import build_policy_view
from app.application.rollout.repository import (
    RolloutRepository,
    RolloutRepositoryError,
)
from app.domain.models.rollout import PreviewRolloutPolicyRecord
from app.domain.schemas.rollout import TrustedRolloutActor
from tests.rollout.helpers import dispose, enable_test_only_mode, make_rollout_engine, make_session


def test_direct_sql_update_delete_rejected() -> None:
    enable_test_only_mode()
    engine, root = make_rollout_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO preview_rollout_policies ("
                "policy_revision,master_enabled,shadow_enabled,promote_enabled,"
                "rollout_percent,allowlist_json,allowlist_sha256,"
                "circuit_breaker_policy_json,circuit_breaker_policy_sha256,"
                "rollout_salt,configuration_sha256,created_at,"
                "created_actor_id,created_actor_role"
                ") VALUES ("
                "'p1',0,0,0,0,'[]',:a,'{}',:b,'salt',:c,:ts,'x','rollout_admin')"
            ),
            {"a": "a" * 64, "b": "b" * 64, "c": "c" * 64, "ts": datetime.utcnow().isoformat()},
        )
    with engine.connect() as conn:
        with pytest.raises(Exception):
            with conn.begin():
                conn.execute(
                    text(
                        "UPDATE preview_rollout_policies SET rollout_percent = 1"
                    )
                )
        with pytest.raises(Exception):
            with conn.begin():
                conn.execute(text("DELETE FROM preview_rollout_policies"))
    dispose(engine, root)


def test_production_repo_cannot_create_applied_or_pointer_swap() -> None:
    enable_test_only_mode()
    engine, root = make_rollout_engine()
    db = make_session(engine)
    repo = RolloutRepository(db)
    with pytest.raises(RolloutRepositoryError):
        repo.insert_decision(
            request_id=1,
            decision_type="promote",
            decision_status="applied",
            actor_id="x",
            actor_role="rollout_admin",
            reason="nope",
            policy_revision="2026-07-25.1",
            eligibility_sha256="e" * 64,
            lineage_sha256="l" * 64,
        )
    with pytest.raises(RolloutRepositoryError):
        repo.apply_pointer_swap(request_id=1)
    with pytest.raises(RolloutRepositoryError):
        repo.create_promote_or_rollback_pointer(request_id=1)
    # Allowed non-applied decision
    row = repo.insert_decision(
        request_id=1,
        decision_type="reject",
        decision_status="rejected",
        actor_id="x",
        actor_role="rollout_operator",
        reason="not ready",
        policy_revision="2026-07-25.1",
        eligibility_sha256="e" * 64,
        lineage_sha256="l" * 64,
    )
    db.commit()
    assert row.decision_status == "rejected"
    db.close()
    dispose(engine, root)


def test_orm_append_only_blocks_policy_update() -> None:
    enable_test_only_mode()
    engine, root = make_rollout_engine()
    db = make_session(engine)
    actor = TrustedRolloutActor(
        actor_id="admin",
        roles=("rollout_admin",),
        auth_source="test_fixture",
    )
    view = build_policy_view(
        policy_revision="2026-07-25.1",
        master_enabled=False,
        shadow_enabled=False,
        promote_enabled=False,
        rollout_percent=0,
        allowlist=(),
        rollout_salt="2026-07-25.1",
        created_actor_id="admin",
        created_actor_role="rollout_admin",
    )
    repo = RolloutRepository(db)
    row = repo.insert_policy_version(actor=actor, view=view)
    db.commit()
    dirty = db.query(PreviewRolloutPolicyRecord).filter_by(id=row.id).one()
    dirty.rollout_percent = 50
    with pytest.raises(ValueError, match="append-only"):
        db.commit()
    db.close()
    dispose(engine, root)
