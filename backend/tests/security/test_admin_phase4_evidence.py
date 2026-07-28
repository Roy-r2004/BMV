"""Security and scoping tests for the read-only Phase 4 evidence endpoint."""
from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import deps
from app.api.deps import verify_admin
from app.api.v1.routers.admin import get_phase4_evidence
from app.application.runtime_validation.evidence import (
    Phase4EvidenceNotFound,
    build_phase4_evidence,
)
from app.domain.models import (
    CandidateAccessibilityFindingRecord,
    CandidateBuildAttemptRecord,
    CandidateJourneyResultRecord,
    CandidateRevisionRecord,
    CandidateRouteResultRecord,
    CandidateRuntimeValidationAttemptRecord,
    CandidateScreenshotRecord,
    CandidateValidationSummaryRecord,
    CompositionContractArtifactRecord,
    Request,
)
from app.infrastructure.db.base import Base


PRIMARY_REQUEST_ID = 901
OTHER_REQUEST_ID = 902
SECRET_MARKER = "must-not-leak"


class _NoProviderGuard:
    """Any attribute access proves an unexpected provider call."""

    def __getattr__(self, name: str):  # pragma: no cover - defensive
        raise AssertionError(f"Phase 4 evidence must not call a provider: {name}")


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _request(request_id: int) -> Request:
    return Request(
        id=request_id,
        business_name=f"Evidence Fixture {request_id}",
        industry="Wellness",
        business_description="Customers book treatments online.",
        target_customers="Studio customers",
        main_problem="Appointments are coordinated manually.",
        desired_outcome="Customers can book online.",
        project_type="new",
        email="owner@example.com",
        created_at=datetime(2026, 7, 28, 12, 0, 0),
    )


def _refs(request_id: int, revision_id: int) -> dict:
    return {
        "request_id": request_id,
        "candidate_revision_id": revision_id,
        "candidate_revision_uuid": f"00000000-0000-4000-8000-{revision_id:012d}",
        "candidate_manifest_sha256": "a" * 64,
        "dependency_lock_sha256": "b" * 64,
        "candidate_generator_version": "v2-phase3b",
        "candidate_policy_revision": "2026-07-24.1",
        "runtime_policy_revision": "2026-07-24.1",
    }


def _revision(request_id: int, revision_id: int) -> CandidateRevisionRecord:
    return CandidateRevisionRecord(
        id=revision_id,
        revision_uuid=f"00000000-0000-4000-8000-{revision_id:012d}",
        request_id=request_id,
        revision=revision_id,
        target_tier=1,
        status="candidate_build_pending",
        generator_version="v2-phase3b",
        policy_revision="2026-07-24.1",
        upstream_manifest_json="{}",
        upstream_manifest_sha256="c" * 64,
        dependency_lock_sha256="b" * 64,
        model_manifest_json="{}",
        workspace_relpath=f"{request_id}/{revision_id}/candidate",
        file_manifest_json="[]",
        file_manifest_sha256="a" * 64,
    )


def _seed_attempt(
    db,
    *,
    request_id: int,
    revision_id: int,
    attempt_id: int,
    attempt_sequence: int = 1,
    route_passed: bool = False,
) -> None:
    refs = _refs(request_id, revision_id)
    db.add(_revision(request_id, revision_id))
    db.add(
        CandidateRuntimeValidationAttemptRecord(
            id=attempt_id,
            attempt_uuid=f"11111111-0000-4000-8000-{attempt_id:012d}",
            request_id=request_id,
            candidate_revision_id=revision_id,
            attempt_sequence=attempt_sequence,
            cache_identity="d" * 64,
            candidate_manifest_sha256="a" * 64,
            dependency_lock_sha256="b" * 64,
            source_candidate_sha256_before="a" * 64,
            runtime_policy_revision="2026-07-24.1",
            tool_versions_json=json.dumps({"node": "v22.14.0"}),
            tool_versions_sha256="e" * 64,
            limits_json=json.dumps({"route_timeout_seconds": 15}),
            limits_sha256="f" * 64,
            workspace_relpath=f"{request_id}/{revision_id}/.staging/x",
            created_at=datetime(2026, 7, 28, 12, 0, 0),
        )
    )
    build_id = attempt_id * 10
    db.add(
        CandidateBuildAttemptRecord(
            id=build_id,
            request_id=request_id,
            candidate_revision_id=revision_id,
            runtime_attempt_id=attempt_id,
            attempt_sequence=0,
            status="build_passed",
            build_cache_key="1" * 64,
            dist_cache_key="2" * 64,
            build_hash="3" * 64,
            dist_manifest_sha256="4" * 64,
            workspace_relpath=f"{request_id}/{revision_id}/candidate",
            result_json=json.dumps(
                {
                    "passed": True,
                    "cache_hit": False,
                    "dist_validation_passed": True,
                    "deterministic_repair_count": 0,
                    "diagnostics": [],
                    "duration_ms": 10,
                    "commands": [
                        {
                            "command_name": "vite_build",
                            "argv": [
                                "node",
                                f"/app/{SECRET_MARKER}/vite.js",
                            ],
                            "exit_code": 0,
                            "timed_out": False,
                            "duration_ms": 5,
                            "stdout_summary": "built",
                            "stderr_summary": "",
                            "stdout_sha256": "5" * 64,
                            "stderr_sha256": "6" * 64,
                        }
                    ],
                }
            ),
            result_sha256="7" * 64,
            passed=True,
        )
    )
    db.add(
        CandidateRouteResultRecord(
            request_id=request_id,
            candidate_revision_id=revision_id,
            runtime_attempt_id=attempt_id,
            build_attempt_id=build_id,
            page_id=f"PAGE_{request_id}",
            route="/",
            viewport="desktop",
            cache_key="8" * 64,
            passed=route_passed,
            result_json=json.dumps(
                {
                    "refs": refs,
                    "page_id": f"PAGE_{request_id}",
                    "route": "/",
                    "viewport": "desktop",
                    "passed": route_passed,
                    "history_verified": route_passed,
                    "console_errors": [f"boom-{request_id}"],
                    "page_errors": [],
                    "request_failures": [f"http://x/{request_id}:failed"],
                    "diagnostics": ["failed_checks:history_verified"],
                }
            ),
            result_sha256="9" * 64,
        )
    )
    db.add(
        CandidateJourneyResultRecord(
            request_id=request_id,
            candidate_revision_id=revision_id,
            runtime_attempt_id=attempt_id,
            build_attempt_id=build_id,
            journey_id=f"JOURNEY_{request_id}",
            action_id=f"ACTION_{request_id}",
            cache_key="a" * 64,
            passed=False,
            result_json=json.dumps(
                {
                    "refs": refs,
                    "journey_id": f"JOURNEY_{request_id}",
                    "action_id": f"ACTION_{request_id}",
                    "route": "/",
                    "passed": False,
                    "steps": [
                        {
                            "step": "action",
                            "canonical_id": f"ACTION_{request_id}",
                            "passed": False,
                            "selector": "[data-bmv-action-id]",
                            "expected": "one enabled visible trigger",
                            "observed": "0",
                        }
                    ],
                    "diagnostics": ["one_or_more_journey_steps_failed"],
                }
            ),
            result_sha256="b" * 64,
        )
    )
    db.add(
        CandidateAccessibilityFindingRecord(
            request_id=request_id,
            candidate_revision_id=revision_id,
            runtime_attempt_id=attempt_id,
            build_attempt_id=build_id,
            page_id=f"PAGE_{request_id}",
            route="/",
            viewport="desktop",
            scanner_name="BaselineAccessibilityScanner",
            scanner_policy_revision="2026-07-24.1",
            cache_key="c" * 64,
            passed=False,
            result_json=json.dumps(
                {
                    "refs": refs,
                    "page_id": f"PAGE_{request_id}",
                    "route": "/",
                    "viewport": "desktop",
                    "passed": False,
                    "findings": [
                        {
                            "rule_id": "obvious-computed-contrast",
                            "severity": "serious",
                            "selector": "h1",
                            "diagnostic_evidence": (
                                f"Computed contrast for {request_id}"
                            ),
                        }
                    ],
                }
            ),
            result_sha256="d" * 64,
        )
    )
    db.add(
        CandidateScreenshotRecord(
            request_id=request_id,
            candidate_revision_id=revision_id,
            runtime_attempt_id=attempt_id,
            build_attempt_id=build_id,
            page_id=f"PAGE_{request_id}",
            route="/",
            viewport="desktop",
            cache_key="e" * 64,
            relative_path=f"{request_id}/evidence/desktop/root.png",
            screenshot_sha256="f" * 64,
            evidence_json=json.dumps(
                {
                    "byte_count": 1024,
                    "browser_version": "chromium-1228",
                    "captured_at": "2026-07-28T04:49:00+00:00",
                }
            ),
            evidence_sha256="0" * 64,
        )
    )
    db.add(
        CandidateValidationSummaryRecord(
            request_id=request_id,
            candidate_revision_id=revision_id,
            runtime_attempt_id=attempt_id,
            build_attempt_id=build_id,
            status="candidate_runtime_failed",
            candidate_manifest_sha256="a" * 64,
            build_hash="3" * 64,
            source_candidate_sha256_before="a" * 64,
            source_candidate_sha256_after="a" * 64,
            summary_json=json.dumps(
                {
                    "refs": refs,
                    "status": "candidate_runtime_failed",
                    "expected_route_viewport_count": 1,
                    "expected_journey_count": 1,
                    "all_required_gates_passed": False,
                    "server_identity_verified": True,
                    "failure_stage": "runtime_gates",
                    "failure_code": "accessibility_failed",
                    "diagnostics": [
                        "route_gate_failed",
                        "journey_gate_failed",
                        "accessibility_baseline_failed",
                    ],
                    "network_diagnostics": [],
                    "server_command": {
                        "command_name": "vite_preview",
                        "argv": ["node", f"/app/{SECRET_MARKER}/vite.js"],
                        "exit_code": 143,
                        "timed_out": False,
                        "duration_ms": 100,
                        "stdout_summary": "",
                        "stderr_summary": "",
                        "stdout_sha256": "1" * 64,
                        "stderr_sha256": "2" * 64,
                    },
                }
            ),
            summary_sha256="3" * 64,
        )
    )
    db.add(
        CompositionContractArtifactRecord(
            request_id=request_id,
            artifact_kind="page_purpose_contract",
            target_tier=1,
            schema_version="1.0",
            policy_revision="2026-07-24.1",
            prompt_revision="1",
            effective_model="fixture",
            provider="fixture",
            model_family="fixture",
            source_artifact_id=1,
            app_spec_revision_id=1,
            tier_1_artifact_id=1,
            tier_2_artifact_id=2,
            tier_3_artifact_id=3,
            product_strategy_v2_artifact_id=1,
            information_architecture_artifact_id=2,
            design_dna_artifact_id=3,
            cache_key=f"{revision_id:064d}",
            artifact_json=json.dumps(
                {
                    "pages": [
                        {
                            "page_id": f"PAGE_{request_id}",
                            "route": "/",
                            "surface": "public",
                            "navigation_visibility": "primary",
                            "role_ids": ["ROLE_CUSTOMER"],
                            "action_ids": [f"ACTION_{request_id}"],
                            "evidence_ids": ["EVIDENCE_ONE"],
                            "acceptance_test_ids": ["TEST_ONE"],
                            "mobile": {"navigation": "bottom_bar"},
                        }
                    ]
                }
            ),
            artifact_sha256="5" * 64,
            validation_json="{}",
            validation_passed=True,
        )
    )
    db.commit()


def _seeded_db():
    db = _db()
    db.add(_request(PRIMARY_REQUEST_ID))
    db.add(_request(OTHER_REQUEST_ID))
    db.commit()
    _seed_attempt(
        db,
        request_id=PRIMARY_REQUEST_ID,
        revision_id=11,
        attempt_id=5,
        attempt_sequence=1,
    )
    _seed_attempt(
        db,
        request_id=PRIMARY_REQUEST_ID,
        revision_id=12,
        attempt_id=6,
        attempt_sequence=2,
    )
    _seed_attempt(
        db,
        request_id=OTHER_REQUEST_ID,
        revision_id=13,
        attempt_id=7,
        attempt_sequence=1,
    )
    return db


def test_missing_credentials_are_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        verify_admin(db=object(), x_admin_password=None, authorization=None)

    assert exc.value.status_code == 401


def test_non_admin_bearer_user_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        deps,
        "get_user_by_token",
        lambda _db, _token: SimpleNamespace(is_admin=False),
    )

    with pytest.raises(HTTPException) as exc:
        verify_admin(
            db=object(),
            x_admin_password=None,
            authorization="Bearer customer-token",
        )

    assert exc.value.status_code == 401


def test_valid_admin_receives_complete_phase4_evidence() -> None:
    db = _seeded_db()
    try:
        payload = get_phase4_evidence(PRIMARY_REQUEST_ID, 5, True, db)
    finally:
        db.close()

    assert payload["request_id"] == PRIMARY_REQUEST_ID
    assert payload["attempt"]["id"] == 5
    assert payload["route_results"][0]["diagnostics"] == [
        "failed_checks:history_verified"
    ]
    assert payload["journey_results"][0]["steps"][0]["selector"] == (
        "[data-bmv-action-id]"
    )
    assert payload["accessibility_results"][0]["findings"][0]["rule_id"] == (
        "obvious-computed-contrast"
    )
    assert payload["screenshots"][0]["sha256"] == "f" * 64
    assert payload["console_errors"][0]["console_errors"] == [
        f"boom-{PRIMARY_REQUEST_ID}"
    ]
    assert payload["network_failures"][0]["request_failures"] == [
        f"http://x/{PRIMARY_REQUEST_ID}:failed"
    ]
    assert payload["preview_identity"]["server_identity_verified"] is True
    assert payload["failure_codes"]["failure_code"] == "accessibility_failed"
    assert payload["expected_route_contract"]["pages"][0]["route"] == "/"
    assert payload["last_successful_substage"] == "preview_identity"
    assert payload["counts"]["failed_routes"] == 1


def test_evidence_is_scoped_to_the_requested_request() -> None:
    db = _seeded_db()
    try:
        payload = get_phase4_evidence(PRIMARY_REQUEST_ID, 5, True, db)
    finally:
        db.close()

    serialized = json.dumps(payload)
    assert str(OTHER_REQUEST_ID) not in serialized
    assert f"PAGE_{OTHER_REQUEST_ID}" not in serialized
    assert f"boom-{OTHER_REQUEST_ID}" not in serialized


def test_evidence_is_scoped_to_the_requested_attempt() -> None:
    db = _seeded_db()
    try:
        first = get_phase4_evidence(PRIMARY_REQUEST_ID, 5, True, db)
        second = get_phase4_evidence(PRIMARY_REQUEST_ID, 6, True, db)
        latest = get_phase4_evidence(PRIMARY_REQUEST_ID, None, True, db)
    finally:
        db.close()

    assert first["attempt"]["id"] == 5
    assert second["attempt"]["id"] == 6
    assert latest["attempt"]["id"] == 6
    assert len(first["route_results"]) == 1
    assert len(second["route_results"]) == 1
    assert first["attempt"]["candidate_revision_id"] != (
        second["attempt"]["candidate_revision_id"]
    )


def test_unknown_request_and_attempt_return_safe_not_found() -> None:
    db = _seeded_db()
    try:
        with pytest.raises(HTTPException) as unknown_request:
            get_phase4_evidence(4242, None, True, db)
        with pytest.raises(HTTPException) as unknown_attempt:
            get_phase4_evidence(PRIMARY_REQUEST_ID, 999, True, db)
        # An attempt belonging to another request must not resolve here.
        with pytest.raises(HTTPException) as cross_request:
            get_phase4_evidence(PRIMARY_REQUEST_ID, 7, True, db)
    finally:
        db.close()

    assert unknown_request.value.status_code == 404
    assert unknown_request.value.detail == "Request not found"
    assert unknown_attempt.value.status_code == 404
    assert unknown_attempt.value.detail == (
        "Runtime validation attempt not found"
    )
    assert cross_request.value.status_code == 404


def test_response_carries_no_secrets_or_absolute_paths() -> None:
    db = _seeded_db()
    try:
        payload = get_phase4_evidence(PRIMARY_REQUEST_ID, 5, True, db)
    finally:
        db.close()

    serialized = json.dumps(payload)
    assert SECRET_MARKER not in serialized
    assert "argv" not in serialized
    assert "/app/" not in serialized
    for forbidden in (
        "authorization",
        "bearer",
        "password",
        "api_key",
        "cookie",
        "database_url",
        "openrouter",
    ):
        assert forbidden not in serialized.lower()
    assert payload["build"]["commands"][0]["command_name"] == "vite_build"
    assert payload["preview_identity"]["server_command"][
        "command_name"
    ] == "vite_preview"


def test_evidence_makes_no_provider_calls_and_mutates_nothing() -> None:
    db = _seeded_db()
    try:
        before = [
            (row.id, row.passed, row.result_sha256)
            for row in db.query(CandidateRouteResultRecord)
            .order_by(CandidateRouteResultRecord.id)
            .all()
        ]
        summaries_before = db.query(CandidateValidationSummaryRecord).count()

        build_phase4_evidence(
            db,
            request_id=PRIMARY_REQUEST_ID,
            attempt=5,
        )

        assert not db.new and not db.dirty and not db.deleted
        after = [
            (row.id, row.passed, row.result_sha256)
            for row in db.query(CandidateRouteResultRecord)
            .order_by(CandidateRouteResultRecord.id)
            .all()
        ]
        assert before == after
        assert (
            db.query(CandidateValidationSummaryRecord).count()
            == summaries_before
        )
    finally:
        db.close()


def test_builder_raises_typed_not_found_for_unknown_attempt() -> None:
    db = _seeded_db()
    try:
        with pytest.raises(Phase4EvidenceNotFound):
            build_phase4_evidence(
                db,
                request_id=PRIMARY_REQUEST_ID,
                attempt=999,
            )
    finally:
        db.close()


def test_evidence_module_never_imports_a_provider() -> None:
    from app.application.runtime_validation import evidence

    assert not hasattr(evidence, "get_ai_provider")
    assert getattr(evidence, "_provider", _NoProviderGuard()) is not None
