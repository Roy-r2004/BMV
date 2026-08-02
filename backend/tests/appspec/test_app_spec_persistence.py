"""Focused persistence/source checks for the canonical AppSpec foundation."""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application.appspec.repository import AppSpecRepository, app_spec_provenance
from app.application.appspec.source import capture_derived_context, capture_request_source, source_sha256
from app.domain.models.app_spec import APP_SPEC_STATUS_ACCEPTED, APP_SPEC_STATUS_REJECTED
from app.domain.models.request import Request
from app.infrastructure.db.base import Base


def _request() -> Request:
    return Request(
        id=41,
        business_name="Lumina Studio",
        industry="Wellness",
        business_description="Customers book treatments online.",
        target_customers="Busy professionals",
        main_problem="Bookings arrive through chat.",
        desired_outcome="Self-service bookings and rescheduling.",
        project_type="new",
        email="private@example.com",
        whatsapp="+000000000",
        admin_notes="private operator note",
        mvp_blueprint="Derived blueprint",
        preview_features=json.dumps(["Booking"]),
        created_at=datetime(2026, 7, 15, 9, 0, 0),
    )


def test_appspec_source_snapshot_excludes_secrets_and_tracks_digest() -> None:
    req = _request()
    snapshot = capture_request_source(req)
    snapshot_again = capture_request_source(req)
    assert source_sha256(snapshot) == source_sha256(snapshot_again)
    original_source_digest = source_sha256(snapshot)
    req.mvp_blueprint = "A newly regenerated derived blueprint"
    assert source_sha256(capture_request_source(req)) == original_source_digest
    req.desired_outcome = "Bookings, rescheduling, and automated reminders."
    assert source_sha256(capture_request_source(req)) != original_source_digest
    req.desired_outcome = "Self-service bookings and rescheduling."
    serialized_source = json.dumps(snapshot)
    assert "private@example.com" not in serialized_source
    assert "+000000000" not in serialized_source
    assert "private operator note" not in serialized_source
    assert "Derived blueprint" not in serialized_source
    assert (
        capture_derived_context(req)["derived_context"]["mvp_blueprint"]
        == "A newly regenerated derived blueprint"
    )


def test_appspec_repository_persists_revisions_and_gates_accepted_status() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        req = _request()
        db.add(req)
        db.commit()

        snapshot = capture_request_source(req)
        repo = AppSpecRepository(db)
        rejected = repo.save_attempt(
            request_id=req.id,
            source_snapshot=snapshot,
            app_spec={"schema_version": "1.0", "requirements": []},
            schema_version="1.0",
            deterministic_validation={"passed": False, "errors": ["missing requirement"]},
            semantic_coverage={"passed": False, "score": 20},
        )
        assert rejected.status == APP_SPEC_STATUS_REJECTED
        assert repo.latest_accepted(req.id) is None

        accepted = repo.save_attempt(
            request_id=req.id,
            source_snapshot=snapshot,
            app_spec={"schema_version": "1.0", "requirements": [{"id": "REQ-1"}]},
            schema_version="1.0",
            deterministic_validation={"is_valid": True, "issues": []},
            semantic_coverage={"verdict": "pass", "score": 94},
            parent_revision_id=rejected.id,
        )
        assert accepted.status == APP_SPEC_STATUS_ACCEPTED
        assert accepted.revision == 2
        assert repo.latest_accepted(req.id).id == accepted.id
        assert repo.latest_accepted(
            req.id,
            source_sha256=accepted.source_sha256,
            schema_version="1.0",
        ).id == accepted.id
        assert app_spec_provenance(accepted) == {
            "id": accepted.id,
            "revision": 2,
            "schema_version": "1.0",
            "sha256": accepted.app_spec_sha256,
        }

        later_rejected = repo.save_attempt(
            request_id=req.id,
            source_snapshot=snapshot,
            app_spec={"schema_version": "1.0", "requirements": []},
            schema_version="1.0",
            deterministic_validation={"passed": True},
            semantic_coverage={"passed": False, "score": 50},
        )
        assert later_rejected.revision == 3
        assert repo.latest_attempt(req.id).id == later_rejected.id
        assert repo.latest_accepted(req.id).id == accepted.id

        try:
            repo.save_attempt(
                request_id=req.id,
                source_snapshot=snapshot,
                app_spec={"schema_version": "1.0"},
                schema_version="1.0",
                deterministic_validation={"passed": False},
                semantic_coverage={"passed": True, "score": 100},
                status=APP_SPEC_STATUS_ACCEPTED,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("Accepted status bypassed validation gate")
    finally:
        db.close()
