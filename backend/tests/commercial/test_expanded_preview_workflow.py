"""Focused Expanded Preview commercial workflow tests."""
from __future__ import annotations

import shutil

import pytest
from sqlalchemy import text

from app.application.expanded_preview.authorization import trusted_actor_from_admin
from app.application.expanded_preview.service import (
    ExpandedPreviewService,
    ExpandedPreviewServiceError,
)
from app.domain.models.expanded_preview import (
    ExpandedPreviewRequestRecord,
    ExpandedPreviewStatusEventRecord,
)
from app.domain.models.rollout import PreviewServingPointerVersionRecord
from app.domain.schemas.expanded_preview import (
    ExpandedPreviewApproveBody,
    ExpandedPreviewCreateBody,
    ExpandedPreviewPublishBody,
    ExpandedPreviewRejectBody,
    ExpandedPreviewReviewBody,
    ExpandedPreviewStartBody,
)
from tests.commercial.helpers import (
    fake_tier1,
    make_commercial_engine,
    seed_request,
    session_factory,
)


@pytest.fixture()
def db_env(monkeypatch):
    engine, root = make_commercial_engine()
    Session = session_factory(engine)
    db = Session()
    req = seed_request(db)
    phase5, rev, visual = fake_tier1(req.id)

    def _loader(_db, *, request_id: int):
        assert request_id == req.id
        return phase5, rev, visual

    monkeypatch.setattr(
        "app.application.expanded_preview.service.load_accepted_tier1_phase5_result",
        _loader,
    )
    monkeypatch.setattr(
        "app.application.expanded_preview.generation_job.load_accepted_tier1_phase5_result",
        _loader,
    )
    admin = trusted_actor_from_admin(actor_id="admin:user:1", is_admin=True)
    yield db, req, admin, engine
    db.close()
    engine.dispose()
    shutil.rmtree(root, ignore_errors=True)


def test_customer_can_request_expanded_preview(db_env):
    db, req, _admin, _engine = db_env
    view = ExpandedPreviewService(db).customer_create(
        request_id=req.id,
        body=ExpandedPreviewCreateBody(reason="Need more pages"),
        customer_actor_id="customer:access-token:1",
        raw_payload={"reason": "Need more pages"},
    )
    assert view.status == "under_review"
    assert view.lifecycle_status == "requested"
    assert "internal" not in view.model_dump()


def test_duplicate_request_is_idempotent(db_env):
    db, req, _admin, _engine = db_env
    body = ExpandedPreviewCreateBody(
        reason="Need more pages",
        idempotency_key="idem-1",
    )
    first = ExpandedPreviewService(db).customer_create(
        request_id=req.id,
        body=body,
        customer_actor_id="customer:access-token:1",
        raw_payload=body.model_dump(),
    )
    second = ExpandedPreviewService(db).customer_create(
        request_id=req.id,
        body=body,
        customer_actor_id="customer:access-token:1",
        raw_payload=body.model_dump(),
    )
    assert first.expanded_preview_id == second.expanded_preview_id
    count = db.query(ExpandedPreviewRequestRecord).count()
    assert count == 1


def test_request_does_not_start_tier2(db_env, monkeypatch):
    db, req, _admin, _engine = db_env
    called = {"n": 0}

    def _spawn(**_kwargs):
        called["n"] += 1

    monkeypatch.setattr(
        "app.application.expanded_preview.generation_job.spawn_tier2_generation_job",
        _spawn,
    )
    ExpandedPreviewService(db).customer_create(
        request_id=req.id,
        body=ExpandedPreviewCreateBody(reason="x"),
        customer_actor_id="customer:access-token:1",
        raw_payload={"reason": "x"},
    )
    assert called["n"] == 0
    row = db.query(ExpandedPreviewRequestRecord).one()
    assert row.current_status == "requested"


def test_unapproved_cannot_start(db_env, monkeypatch):
    db, req, admin, _engine = db_env
    monkeypatch.setattr(
        "app.core.config.settings.V2_TIER2_GENERATION_ENABLED",
        True,
    )
    view = ExpandedPreviewService(db).customer_create(
        request_id=req.id,
        body=ExpandedPreviewCreateBody(reason="x"),
        customer_actor_id="customer:access-token:1",
        raw_payload={"reason": "x"},
    )
    with pytest.raises(ExpandedPreviewServiceError) as exc:
        ExpandedPreviewService(db).start_generation(
            actor=admin,
            expanded_preview_id=view.expanded_preview_id,
            body=ExpandedPreviewStartBody(confirm=True),
            raw_payload={"confirm": True},
        )
    assert exc.value.status_code == 409


def test_approved_starts_only_via_admin(db_env, monkeypatch):
    db, req, admin, _engine = db_env
    monkeypatch.setattr(
        "app.core.config.settings.V2_TIER2_GENERATION_ENABLED",
        True,
    )
    started = {"n": 0}

    def _spawn(**_kwargs):
        started["n"] += 1

    import app.application.expanded_preview.generation_job as job_mod

    monkeypatch.setattr(job_mod, "spawn_tier2_generation_job", _spawn)
    created = ExpandedPreviewService(db).customer_create(
        request_id=req.id,
        body=ExpandedPreviewCreateBody(reason="x"),
        customer_actor_id="customer:access-token:1",
        raw_payload={"reason": "x"},
    )
    ExpandedPreviewService(db).approve(
        actor=admin,
        expanded_preview_id=created.expanded_preview_id,
        body=ExpandedPreviewApproveBody(reason="ok"),
        raw_payload={"reason": "ok"},
    )
    out = ExpandedPreviewService(db).start_generation(
        actor=admin,
        expanded_preview_id=created.expanded_preview_id,
        body=ExpandedPreviewStartBody(confirm=True),
        raw_payload={"confirm": True},
    )
    assert out.current_status == "generation_started"
    assert started["n"] == 1


def test_duplicate_start_idempotent(db_env, monkeypatch):
    db, req, admin, _engine = db_env
    monkeypatch.setattr(
        "app.core.config.settings.V2_TIER2_GENERATION_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "app.application.expanded_preview.generation_job.spawn_tier2_generation_job",
        lambda **_k: None,
    )
    created = ExpandedPreviewService(db).customer_create(
        request_id=req.id,
        body=ExpandedPreviewCreateBody(reason="x"),
        customer_actor_id="customer:access-token:1",
        raw_payload={"reason": "x"},
    )
    ExpandedPreviewService(db).approve(
        actor=admin,
        expanded_preview_id=created.expanded_preview_id,
        body=ExpandedPreviewApproveBody(),
        raw_payload={},
    )
    first = ExpandedPreviewService(db).start_generation(
        actor=admin,
        expanded_preview_id=created.expanded_preview_id,
        body=ExpandedPreviewStartBody(confirm=True),
        raw_payload={"confirm": True},
    )
    second = ExpandedPreviewService(db).start_generation(
        actor=admin,
        expanded_preview_id=created.expanded_preview_id,
        body=ExpandedPreviewStartBody(confirm=True),
        raw_payload={"confirm": True},
    )
    assert first.current_status == second.current_status == "generation_started"


def test_concurrent_start_prevented(db_env, monkeypatch):
    db, req, admin, _engine = db_env
    monkeypatch.setattr(
        "app.core.config.settings.V2_TIER2_GENERATION_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "app.application.expanded_preview.generation_job.spawn_tier2_generation_job",
        lambda **_k: None,
    )
    created = ExpandedPreviewService(db).customer_create(
        request_id=req.id,
        body=ExpandedPreviewCreateBody(reason="x"),
        customer_actor_id="customer:access-token:1",
        raw_payload={"reason": "x"},
    )
    ExpandedPreviewService(db).approve(
        actor=admin,
        expanded_preview_id=created.expanded_preview_id,
        body=ExpandedPreviewApproveBody(),
        raw_payload={},
    )
    ExpandedPreviewService(db).start_generation(
        actor=admin,
        expanded_preview_id=created.expanded_preview_id,
        body=ExpandedPreviewStartBody(confirm=True),
        raw_payload={"confirm": True},
    )
    # Force status back to approved while claim still active to simulate race
    row = db.get(ExpandedPreviewRequestRecord, created.expanded_preview_id)
    row.current_status = "approved"
    db.commit()
    with pytest.raises(ExpandedPreviewServiceError) as exc:
        ExpandedPreviewService(db).start_generation(
            actor=admin,
            expanded_preview_id=created.expanded_preview_id,
            body=ExpandedPreviewStartBody(confirm=True),
            raw_payload={"confirm": True},
        )
    assert exc.value.status_code == 409


def test_tier1_pages_preserved_and_no_auto_publish(db_env):
    db, req, admin, _engine = db_env
    created = ExpandedPreviewService(db).customer_create(
        request_id=req.id,
        body=ExpandedPreviewCreateBody(reason="x"),
        customer_actor_id="customer:access-token:1",
        raw_payload={"reason": "x"},
    )
    row = db.get(ExpandedPreviewRequestRecord, created.expanded_preview_id)
    row.current_status = "generation_completed"
    row.tier_2_candidate_revision_id = 999
    db.commit()
    db.refresh(req)
    assert "preview_app" in (req.generated_pages or "")
    cust = ExpandedPreviewService(db).customer_get(request_id=req.id)
    assert cust is not None
    assert cust.can_open_published is False


def test_rejected_review_cannot_publish(db_env):
    db, req, admin, _engine = db_env
    created = ExpandedPreviewService(db).customer_create(
        request_id=req.id,
        body=ExpandedPreviewCreateBody(reason="x"),
        customer_actor_id="customer:access-token:1",
        raw_payload={"reason": "x"},
    )
    row = db.get(ExpandedPreviewRequestRecord, created.expanded_preview_id)
    row.current_status = "generation_completed"
    row.tier_2_candidate_revision_id = 999
    db.commit()
    ExpandedPreviewService(db).review(
        actor=admin,
        expanded_preview_id=created.expanded_preview_id,
        body=ExpandedPreviewReviewBody(outcome="review_rejected", confirm=True),
        raw_payload={"outcome": "review_rejected", "confirm": True},
    )
    with pytest.raises(ExpandedPreviewServiceError):
        ExpandedPreviewService(db).publish(
            actor=admin,
            expanded_preview_id=created.expanded_preview_id,
            body=ExpandedPreviewPublishBody(confirm=True),
            raw_payload={"confirm": True},
        )


def test_accepted_review_can_publish(db_env):
    db, req, admin, _engine = db_env
    created = ExpandedPreviewService(db).customer_create(
        request_id=req.id,
        body=ExpandedPreviewCreateBody(reason="x"),
        customer_actor_id="customer:access-token:1",
        raw_payload={"reason": "x"},
    )
    row = db.get(ExpandedPreviewRequestRecord, created.expanded_preview_id)
    row.current_status = "generation_completed"
    row.tier_2_candidate_revision_id = 999
    db.commit()
    ExpandedPreviewService(db).review(
        actor=admin,
        expanded_preview_id=created.expanded_preview_id,
        body=ExpandedPreviewReviewBody(outcome="review_accepted", confirm=True),
        raw_payload={"outcome": "review_accepted", "confirm": True},
    )
    published = ExpandedPreviewService(db).publish(
        actor=admin,
        expanded_preview_id=created.expanded_preview_id,
        body=ExpandedPreviewPublishBody(confirm=True),
        raw_payload={"confirm": True},
    )
    assert published.current_status == "published"
    cust = ExpandedPreviewService(db).customer_get(request_id=req.id)
    assert cust is not None
    assert cust.can_open_published is True
    assert cust.published_preview_url


def test_client_roles_rejected(db_env):
    db, req, _admin, _engine = db_env
    with pytest.raises(Exception):
        ExpandedPreviewService(db).customer_create(
            request_id=req.id,
            body=ExpandedPreviewCreateBody(reason="x"),
            customer_actor_id="customer:access-token:1",
            raw_payload={"reason": "x", "actor_id": "evil", "roles": ["admin"]},
        )


def test_audit_append_only(db_env):
    db, req, admin, _engine = db_env
    created = ExpandedPreviewService(db).customer_create(
        request_id=req.id,
        body=ExpandedPreviewCreateBody(reason="x"),
        customer_actor_id="customer:access-token:1",
        raw_payload={"reason": "x"},
    )
    ExpandedPreviewService(db).approve(
        actor=admin,
        expanded_preview_id=created.expanded_preview_id,
        body=ExpandedPreviewApproveBody(),
        raw_payload={},
    )
    events = (
        db.query(ExpandedPreviewStatusEventRecord)
        .order_by(ExpandedPreviewStatusEventRecord.id.asc())
        .all()
    )
    assert [e.to_status for e in events] == ["requested", "approved"]
    with pytest.raises(Exception):
        events[0].to_status = "tampered"
        db.commit()
    db.rollback()


def test_phase7_pointers_unchanged(db_env):
    db, req, admin, engine = db_env
    before = db.query(PreviewServingPointerVersionRecord).count()
    created = ExpandedPreviewService(db).customer_create(
        request_id=req.id,
        body=ExpandedPreviewCreateBody(reason="x"),
        customer_actor_id="customer:access-token:1",
        raw_payload={"reason": "x"},
    )
    row = db.get(ExpandedPreviewRequestRecord, created.expanded_preview_id)
    row.current_status = "review_accepted"
    row.tier_2_candidate_revision_id = 999
    db.commit()
    ExpandedPreviewService(db).publish(
        actor=admin,
        expanded_preview_id=created.expanded_preview_id,
        body=ExpandedPreviewPublishBody(confirm=True),
        raw_payload={"confirm": True},
    )
    after = db.query(PreviewServingPointerVersionRecord).count()
    assert before == after == 0
    # Serving pointer table exists but was not written
    with engine.connect() as conn:
        assert "preview_serving_pointer_versions" in {
            r[0]
            for r in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }


def test_reject_from_requested(db_env):
    db, req, admin, _engine = db_env
    created = ExpandedPreviewService(db).customer_create(
        request_id=req.id,
        body=ExpandedPreviewCreateBody(reason="x"),
        customer_actor_id="customer:access-token:1",
        raw_payload={"reason": "x"},
    )
    out = ExpandedPreviewService(db).reject(
        actor=admin,
        expanded_preview_id=created.expanded_preview_id,
        body=ExpandedPreviewRejectBody(reason="not a fit"),
        raw_payload={"reason": "not a fit"},
    )
    assert out.current_status == "rejected"
