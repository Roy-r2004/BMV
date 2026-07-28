"""Read-only Phase 4 diagnostic evidence projection for admin operators.

This module never mutates Phase 4 records, never reads candidate source, and
never contacts a provider. Every query is scoped to one request and one
runtime-validation attempt so an operator can diagnose a runtime failure
without shell access to the validation volume.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.domain.models import (
    CandidateAccessibilityFindingRecord,
    CandidateBuildAttemptRecord,
    CandidateJourneyResultRecord,
    CandidateRouteResultRecord,
    CandidateRuntimeValidationAttemptRecord,
    CandidateScreenshotRecord,
    CandidateValidationSummaryRecord,
    CompositionContractArtifactRecord,
)


PHASE4_EVIDENCE_SCHEMA_VERSION = "1.0"

# Ordered Phase 4 substages used to report the last one that fully succeeded.
_SUBSTAGE_ORDER = (
    "build",
    "preview_identity",
    "route_gate",
    "journey_gate",
    "accessibility_baseline",
    "screenshot_persistence",
)


class Phase4EvidenceNotFound(LookupError):
    """Raised when the request or the requested attempt does not exist."""

    def __init__(self, scope: str) -> None:
        super().__init__(scope)
        self.scope = scope


def _loaded(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _sanitized_command(command: Any) -> dict[str, Any] | None:
    """Drop ``argv`` so absolute container paths never leave the API."""

    if not isinstance(command, dict):
        return None
    return {
        "command_name": command.get("command_name"),
        "exit_code": command.get("exit_code"),
        "timed_out": command.get("timed_out"),
        "duration_ms": command.get("duration_ms"),
        "stdout_summary": command.get("stdout_summary", ""),
        "stderr_summary": command.get("stderr_summary", ""),
        "stdout_sha256": command.get("stdout_sha256"),
        "stderr_sha256": command.get("stderr_sha256"),
    }


def _sanitized_summary(summary: dict[str, Any]) -> dict[str, Any]:
    if not summary:
        return {}
    projected = dict(summary)
    projected["server_command"] = _sanitized_command(
        summary.get("server_command")
    )
    return projected


def _sanitized_build(build_row: CandidateBuildAttemptRecord | None) -> dict:
    if build_row is None:
        return {}
    result = _loaded(build_row.result_json)
    return {
        "build_attempt_id": build_row.id,
        "attempt_sequence": build_row.attempt_sequence,
        "parent_build_attempt_id": build_row.parent_build_attempt_id,
        "status": build_row.status,
        "passed": bool(build_row.passed),
        "build_hash": build_row.build_hash,
        "dist_manifest_sha256": build_row.dist_manifest_sha256,
        "cache_hit": result.get("cache_hit"),
        "dist_validation_passed": result.get("dist_validation_passed"),
        "deterministic_repair_count": result.get(
            "deterministic_repair_count"
        ),
        "failure_code": result.get("failure_code"),
        "first_error_location": result.get("first_error_location"),
        "diagnostics": list(result.get("diagnostics") or ()),
        "duration_ms": result.get("duration_ms"),
        "commands": [
            _sanitized_command(item)
            for item in (result.get("commands") or ())
        ],
    }


def _latest_contract(
    db: Session,
    *,
    request_id: int,
    artifact_kind: str,
) -> tuple[str | None, dict[str, Any]]:
    row = (
        db.query(CompositionContractArtifactRecord)
        .filter(
            CompositionContractArtifactRecord.request_id == request_id,
            CompositionContractArtifactRecord.artifact_kind == artifact_kind,
        )
        .order_by(CompositionContractArtifactRecord.id.desc())
        .first()
    )
    if row is None:
        return None, {}
    return row.artifact_sha256, _loaded(row.artifact_json)


def _expected_route_contract(
    db: Session,
    *,
    request_id: int,
) -> dict[str, Any]:
    sha256, contract = _latest_contract(
        db,
        request_id=request_id,
        artifact_kind="page_purpose_contract",
    )
    _, plan = _latest_contract(
        db,
        request_id=request_id,
        artifact_kind="business_component_plan",
    )
    components_by_page = {
        str(item.get("page_id")): list(
            item.get("ordered_component_ids") or ()
        )
        for item in (plan.get("page_compositions") or ())
        if isinstance(item, dict)
    }
    pages = []
    for page in contract.get("pages") or ():
        if not isinstance(page, dict):
            continue
        page_id = str(page.get("page_id"))
        pages.append(
            {
                "page_id": page_id,
                "route": page.get("route"),
                "surface": page.get("surface"),
                "navigation_visibility": page.get("navigation_visibility"),
                "role_ids": list(page.get("role_ids") or ()),
                "state_ids": list(page.get("state_ids") or ()),
                "action_ids": list(page.get("action_ids") or ()),
                "transition_ids": list(page.get("transition_ids") or ()),
                "evidence_ids": list(page.get("evidence_ids") or ()),
                "journey_ids": list(page.get("journey_ids") or ()),
                "acceptance_test_ids": list(
                    page.get("acceptance_test_ids") or ()
                ),
                "mobile": page.get("mobile") or {},
                "expected_component_ids": components_by_page.get(page_id, []),
            }
        )
    return {
        "source": "page_purpose_contract",
        "artifact_sha256": sha256,
        "pages": pages,
    }


def _journey_definitions(
    db: Session,
    *,
    request_id: int,
) -> dict[str, Any]:
    sha256, contract = _latest_contract(
        db,
        request_id=request_id,
        artifact_kind="interaction_contract",
    )
    interactions = []
    for item in contract.get("interactions") or ():
        if not isinstance(item, dict):
            continue
        interactions.append(
            {
                "action_id": item.get("action_id"),
                "page_id": item.get("page_id"),
                "route": item.get("route"),
                "role_id": item.get("role_id"),
                "action_kind": item.get("action_kind"),
                "trigger_component_id": item.get("trigger_component_id"),
                "journey_ids": list(item.get("journey_ids") or ()),
                "input_field_ids": list(item.get("input_field_ids") or ()),
                "input_collection_ids": list(
                    item.get("input_collection_ids") or ()
                ),
                "acceptance_test_ids": list(
                    item.get("acceptance_test_ids") or ()
                ),
                "transitions": [
                    {
                        "transition_id": transition.get("transition_id"),
                        "from_state_id": transition.get("from_state_id"),
                        "to_state_id": transition.get("to_state_id"),
                        "success_evidence_ids": list(
                            transition.get("success_evidence_ids") or ()
                        ),
                    }
                    for transition in (item.get("transitions") or ())
                    if isinstance(transition, dict)
                ],
                "browser_assertions": [
                    {
                        "acceptance_test_id": assertion.get(
                            "acceptance_test_id"
                        ),
                        "assertion_index": assertion.get("assertion_index"),
                        "kind": assertion.get("kind"),
                        "page_id": assertion.get("page_id"),
                        "route": assertion.get("route"),
                        "state_id": assertion.get("state_id"),
                        "evidence_id": assertion.get("evidence_id"),
                        "expected": assertion.get("expected"),
                    }
                    for assertion in (item.get("browser_assertions") or ())
                    if isinstance(assertion, dict)
                ],
            }
        )
    return {
        "source": "interaction_contract",
        "artifact_sha256": sha256,
        "interactions": interactions,
    }


def _resolve_attempt(
    db: Session,
    *,
    request_id: int,
    attempt: int | None,
) -> CandidateRuntimeValidationAttemptRecord:
    query = db.query(CandidateRuntimeValidationAttemptRecord).filter(
        CandidateRuntimeValidationAttemptRecord.request_id == request_id
    )
    if attempt is None:
        row = query.order_by(
            CandidateRuntimeValidationAttemptRecord.id.desc()
        ).first()
        if row is None:
            raise Phase4EvidenceNotFound("attempt")
        return row
    # Operators reference attempts by row id or by per-candidate sequence.
    # Both lookups stay scoped to this request, so neither can leak another.
    row = query.filter(
        CandidateRuntimeValidationAttemptRecord.id == attempt
    ).first()
    if row is not None:
        return row
    row = (
        query.filter(
            CandidateRuntimeValidationAttemptRecord.attempt_sequence == attempt
        )
        .order_by(CandidateRuntimeValidationAttemptRecord.id)
        .first()
    )
    if row is None:
        raise Phase4EvidenceNotFound("attempt")
    return row


def _last_successful_substage(
    *,
    build_passed: bool,
    identity_verified: bool,
    routes: list[dict[str, Any]],
    journeys: list[dict[str, Any]],
    accessibility: list[dict[str, Any]],
    screenshots: list[dict[str, Any]],
    expected_routes: int,
    expected_journeys: int,
) -> str:
    completed = {
        "build": build_passed,
        "preview_identity": identity_verified,
        "route_gate": (
            len(routes) == expected_routes
            and bool(routes)
            and all(item.get("passed") for item in routes)
        ),
        "journey_gate": (
            len(journeys) == expected_journeys
            and bool(journeys)
            and all(item.get("passed") for item in journeys)
        ),
        "accessibility_baseline": (
            len(accessibility) == expected_routes
            and bool(accessibility)
            and all(item.get("passed") for item in accessibility)
        ),
        "screenshot_persistence": (
            len(screenshots) == expected_routes and bool(screenshots)
        ),
    }
    last = "not_started"
    for name in _SUBSTAGE_ORDER:
        if not completed[name]:
            break
        last = name
    return last


def build_phase4_evidence(
    db: Session,
    *,
    request_id: int,
    attempt: int | None = None,
) -> dict[str, Any]:
    """Project persisted Phase 4 evidence for one request and attempt."""

    attempt_row = _resolve_attempt(
        db,
        request_id=request_id,
        attempt=attempt,
    )
    summary_row = (
        db.query(CandidateValidationSummaryRecord)
        .filter(
            CandidateValidationSummaryRecord.runtime_attempt_id
            == attempt_row.id
        )
        .first()
    )
    summary = _sanitized_summary(
        _loaded(summary_row.summary_json) if summary_row else {}
    )
    build_row = (
        db.query(CandidateBuildAttemptRecord)
        .filter(
            CandidateBuildAttemptRecord.runtime_attempt_id == attempt_row.id
        )
        .order_by(CandidateBuildAttemptRecord.attempt_sequence.desc())
        .first()
    )
    build = _sanitized_build(build_row)

    def _results(model: Any, order_columns: tuple[Any, ...]) -> list[dict]:
        rows = (
            db.query(model)
            .filter(model.runtime_attempt_id == attempt_row.id)
            .order_by(*order_columns)
            .all()
        )
        return [_loaded(row.result_json) for row in rows]

    routes = _results(
        CandidateRouteResultRecord,
        (CandidateRouteResultRecord.id,),
    )
    journeys = _results(
        CandidateJourneyResultRecord,
        (CandidateJourneyResultRecord.id,),
    )
    accessibility = _results(
        CandidateAccessibilityFindingRecord,
        (CandidateAccessibilityFindingRecord.id,),
    )
    screenshot_rows = (
        db.query(CandidateScreenshotRecord)
        .filter(
            CandidateScreenshotRecord.runtime_attempt_id == attempt_row.id
        )
        .order_by(CandidateScreenshotRecord.id)
        .all()
    )
    screenshots = [
        {
            "page_id": row.page_id,
            "route": row.route,
            "viewport": row.viewport,
            "relative_path": row.relative_path,
            "sha256": row.screenshot_sha256,
            "byte_count": _loaded(row.evidence_json).get("byte_count"),
            "browser_version": _loaded(row.evidence_json).get(
                "browser_version"
            ),
            "captured_at": _loaded(row.evidence_json).get("captured_at"),
        }
        for row in screenshot_rows
    ]

    console_errors = [
        {
            "page_id": item.get("page_id"),
            "route": item.get("route"),
            "viewport": item.get("viewport"),
            "console_errors": list(item.get("console_errors") or ()),
            "page_errors": list(item.get("page_errors") or ()),
        }
        for item in routes
        if item.get("console_errors") or item.get("page_errors")
    ]
    network_failures = [
        {
            "page_id": item.get("page_id"),
            "route": item.get("route"),
            "viewport": item.get("viewport"),
            "request_failures": list(item.get("request_failures") or ()),
        }
        for item in routes
        if item.get("request_failures")
    ]

    expected_routes = int(summary.get("expected_route_viewport_count") or 0)
    expected_journeys = int(summary.get("expected_journey_count") or 0)
    return {
        "schema_version": PHASE4_EVIDENCE_SCHEMA_VERSION,
        "request_id": request_id,
        "attempt": {
            "id": attempt_row.id,
            "attempt_uuid": attempt_row.attempt_uuid,
            "attempt_sequence": attempt_row.attempt_sequence,
            "candidate_revision_id": attempt_row.candidate_revision_id,
            "candidate_manifest_sha256": (
                attempt_row.candidate_manifest_sha256
            ),
            "dependency_lock_sha256": attempt_row.dependency_lock_sha256,
            "runtime_policy_revision": attempt_row.runtime_policy_revision,
            "workspace_relpath": attempt_row.workspace_relpath,
            "resumed_from_attempt_id": attempt_row.resumed_from_attempt_id,
            "created_at": (
                attempt_row.created_at.isoformat()
                if attempt_row.created_at
                else None
            ),
            "tools": _loaded(attempt_row.tool_versions_json),
            "limits": _loaded(attempt_row.limits_json),
        },
        "summary": summary,
        "build": build,
        "preview_identity": {
            "server_identity_verified": bool(
                summary.get("server_identity_verified")
            ),
            "server_command": summary.get("server_command"),
        },
        "expected_route_contract": _expected_route_contract(
            db,
            request_id=request_id,
        ),
        "journey_definitions": _journey_definitions(
            db,
            request_id=request_id,
        ),
        "route_results": routes,
        "journey_results": journeys,
        "accessibility_results": accessibility,
        "screenshots": screenshots,
        "console_errors": console_errors,
        "network_failures": network_failures,
        "network_diagnostics": list(summary.get("network_diagnostics") or ()),
        "failure_codes": {
            "failure_stage": summary.get("failure_stage"),
            "failure_code": summary.get("failure_code"),
            "first_error_location": summary.get("first_error_location"),
            "diagnostics": list(summary.get("diagnostics") or ()),
            "build_failure_code": build.get("failure_code"),
        },
        "counts": {
            "expected_route_viewport_count": expected_routes,
            "expected_journey_count": expected_journeys,
            "route_results": len(routes),
            "journey_results": len(journeys),
            "accessibility_results": len(accessibility),
            "screenshots": len(screenshots),
            "failed_routes": sum(
                1 for item in routes if not item.get("passed")
            ),
            "failed_journeys": sum(
                1 for item in journeys if not item.get("passed")
            ),
            "failed_accessibility": sum(
                1 for item in accessibility if not item.get("passed")
            ),
        },
        "last_successful_substage": _last_successful_substage(
            build_passed=bool(build.get("passed")),
            identity_verified=bool(summary.get("server_identity_verified")),
            routes=routes,
            journeys=journeys,
            accessibility=accessibility,
            screenshots=screenshots,
            expected_routes=expected_routes,
            expected_journeys=expected_journeys,
        ),
    }


__all__ = [
    "PHASE4_EVIDENCE_SCHEMA_VERSION",
    "Phase4EvidenceNotFound",
    "build_phase4_evidence",
]
