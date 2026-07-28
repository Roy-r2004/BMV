from __future__ import annotations

import json
import inspect
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.deps import verify_admin
from app.api.v1.routers.admin import get_progress_diagnostics
from app.api.v1.routers.requests import get_generation_progress, get_preview
from app.domain.models import AppSpecRevision, Request
from app.domain.models.expanded_preview import ExpandedPreviewRequestRecord
from app.domain.schemas.request import (
    AdminPreviewDiagnostics,
    AdminProgressDiagnostics,
)


FORBIDDEN_PUBLIC_TERMS = (
    "provider",
    "model",
    "choices",
    "response_top_level_keys",
    "payload_sha",
    "call_ledger",
    "provider_attempt",
    "checkpoint",
    "retry",
    "provider_error_code",
    "traceback",
    "workspace",
    "command",
    "environment_fingerprint",
    "candidate_revision",
    "attempt_id",
    "typed_code",
    "stdout",
    "stderr",
    "business_component_usage",
    "dependency_graph",
    "artifact_id",
    "diagnostics_url",
    "rollout",
    "phase7",
    "appspec_fallback",
)


def _request(**overrides):
    defaults = {
        "id": 33,
        "business_name": "Safe Booking",
        "customer_access_token": "must-not-be-returned",
        "business_fit_score": 91,
        "concept_name": "Safe Booking",
        "preview_summary": "A customer-safe summary.",
        "preview_features": '["Booking", "Confirmation"]',
        "ai_features": "[]",
        "visual_demo_json": '{"theme":{"provider":"must-not-leak"}}',
        "generated_pages": None,
        "status": "new",
        "generation_log": None,
        "industry": "Services",
        "timeline": "2 weeks",
        "budget_range": "$1k-$3k",
        "desired_outcome": "Accept bookings",
        "main_problem": "Manual scheduling",
        "screenshot_analysis": "internal screenshot analysis",
        "reference_metadata": None,
        "reference_url": None,
        "what_you_like": None,
        "mvp_blueprint": "internal blueprint",
        "technical_plan": "internal technical plan",
        "build_plans": None,
        "build_requested": False,
        "created_at": datetime(2026, 7, 26, 10, 0, 0),
        "updated_at": datetime(2026, 7, 26, 10, 5, 0),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class _Query:
    def __init__(self, result):
        self.result = result

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.result


class _Db:
    def __init__(self, req, *, expanded=None):
        self.req = req
        self.expanded = expanded
        self.commits = 0

    def query(self, entity):
        if entity is Request:
            return _Query(self.req)
        if entity is AppSpecRevision:
            return _Query(None)
        if entity is ExpandedPreviewRequestRecord:
            return _Query(self.expanded)
        return _Query(None)

    def get(self, entity, key):
        if entity is Request and key == self.req.id:
            return self.req
        return None

    def commit(self):
        self.commits += 1


def _serialized(payload) -> str:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    return json.dumps(payload, default=str).lower()


def _assert_public_payload_is_allowlisted(payload) -> dict:
    data = payload.model_dump(mode="json")
    serialized = json.dumps(data).lower()
    for term in FORBIDDEN_PUBLIC_TERMS:
        assert term not in serialized
    assert "new_future_internal_field" not in serialized
    return data


def _request33_bundle() -> dict:
    return {
        "preview_contract": {
            "status": "candidate_failed",
            "candidate_revision_uuid": "internal-revision-33",
            "candidate_call_ledger": {
                "calls_used": 2,
                "provider": "openrouter",
            },
            "candidate_provider_attempts": [
                {
                    "provider": "openrouter",
                    "model": "private-model",
                    "provider_request_id": "provider-request-33",
                    "attempt_id": "internal-attempt-33",
                    "response_top_level_keys": ["error"],
                    "raw_payload_sha256": "a" * 64,
                    "retry_attempted": True,
                }
            ],
            "candidate_stage_checkpoints": [
                {
                    "checkpoint_id": "internal-attempt",
                    "input_hash": "b" * 64,
                    "output_hash": "c" * 64,
                }
            ],
            "failure": {
                "provider_error_code": "provider_response_shape_invalid",
                "error_type": "KeyError",
                "message": "KeyError: choices at response_parser.py:42",
                "workspace_path": "C:/private/runtime/33",
                "command": "npm run build",
                "stdout": "private stdout",
                "stderr": "private stderr",
            },
            "business_component_usage_evidence": {"artifact_id": 9901},
            "dependency_graph": {"diagnostics_url": "/api/admin/private"},
            "rollout_flags": {"phase7": True},
            "appspec_fallback_enabled": True,
            "new_future_internal_field": {"secret_shape": True},
        }
    }


def test_request33_preview_returns_only_safe_failure() -> None:
    req = _request(
        status="failed",
        generated_pages=json.dumps(_request33_bundle()),
    )

    payload = get_preview(req.id, _Db(req))
    data = _assert_public_payload_is_allowlisted(payload)

    assert data["request_id"] == 33
    assert data["status"] == "failed"
    assert data["error_message"] == (
        "We could not generate the preview. Please try again."
    )
    assert data["generated_pages"] is None
    assert "customer_access_token" not in data


def test_request32_composition_failure_is_customer_safe() -> None:
    bundle = {
        "preview_contract": {
            "status": "composition_failed",
            "failure": {
                "kind": "composition_contract",
                "error_type": "CompositionValidationError",
                "typed_code": "phase3a_business_component_plan_invalid",
                "message": "business component usage internals",
                "dependency_graph": {"internal": True},
            },
        }
    }
    req = _request(id=32, status="failed", generated_pages=json.dumps(bundle))

    payload = get_preview(req.id, _Db(req))
    data = _assert_public_payload_is_allowlisted(payload)

    assert data["request_id"] == 32
    assert data["status"] == "failed"
    assert data["error_message"] == (
        "We could not generate the preview. Please try again."
    )


def test_success_preview_keeps_safe_url_and_expanded_state() -> None:
    bundle = {
        "preview_app": {
            "url": "/api/preview-apps/33/",
            "workspace_path": "C:/private/workspace",
        },
        "preview_contract": {
            "status": "candidate_visual_accepted",
            "new_future_internal_field": {"provider": "hidden"},
        },
    }
    expanded = SimpleNamespace(current_status="requested")
    req = _request(
        status="new",
        generated_pages=json.dumps(bundle),
        visual_demo_json='{"theme":{"name":"safe"}}',
    )

    payload = get_preview(req.id, _Db(req, expanded=expanded))
    data = _assert_public_payload_is_allowlisted(payload)

    assert data["status"] == "expanded_preview_requested"
    assert data["preview_url"] == "/api/preview-apps/33/"
    assert data["visual_demo_status"] == "available"
    assert data["expanded_preview_status"] == "requested"
    assert data["tier2_request_state"] == "requested"


def test_progress_snapshot_is_allowlisted_and_maps_runtime_failure() -> None:
    malicious_snapshot = {
        "stage": "candidate_runtime_validation_failed",
        "label": "C:/private/workspace failed",
        "pct": 87,
        "detail": "Traceback: npm run build failed with provider code",
        "log": [{"command": "npm run build", "stderr": "private"}],
        "workspace_path": "C:/private/workspace",
        "environment_fingerprint": "node-22/npm-10",
        "candidate_revision_id": 310033,
        "new_future_internal_field": {"retry": True},
    }
    req = _request(
        status="failed",
        generation_log=json.dumps(malicious_snapshot),
        generated_pages=json.dumps(
            {
                "preview_contract": {
                    "status": "candidate_failed",
                    "failure": {"stage": "runtime_validation"},
                }
            }
        ),
    )

    payload = get_generation_progress(req.id, _Db(req))
    data = _assert_public_payload_is_allowlisted(payload)

    assert data["request_id"] == 33
    assert data["status"] == "failed"
    assert data["stage_label"] == "Validating your preview"
    assert data["progress_percentage"] == 87
    assert data["error_message"] == (
        "The generated preview did not pass validation."
    )
    assert "detail" not in data
    assert "log" not in data


@pytest.mark.parametrize(
    ("internal_status", "public_status"),
    [
        ("design_contract_ready", "planning"),
        ("composition_contract_ready", "generating"),
        ("candidate_generated", "generating"),
        ("candidate_build_pending", "validating"),
        ("candidate_runtime_validated", "validating"),
        ("candidate_visual_accepted", "ready"),
    ],
)
def test_internal_statuses_map_to_stable_customer_statuses(
    internal_status: str,
    public_status: str,
) -> None:
    req = _request(
        generated_pages=json.dumps(
            {"preview_contract": {"status": internal_status}}
        )
    )

    data = _assert_public_payload_is_allowlisted(
        get_preview(req.id, _Db(req))
    )

    assert data["status"] == public_status
    assert internal_status not in _serialized(data)


def test_visual_review_failure_uses_safe_customer_message() -> None:
    req = _request(
        status="failed",
        generated_pages=json.dumps(
            {
                "preview_contract": {
                    "status": "candidate_failed",
                    "failure": {
                        "stage": "visual_evaluation",
                        "typed_code": "internal_visual_threshold_failed",
                    },
                }
            }
        ),
    )

    data = _assert_public_payload_is_allowlisted(
        get_preview(req.id, _Db(req))
    )

    assert data["error_message"] == (
        "The preview requires another generation attempt."
    )
    assert data["visual_demo_status"] == "failed"


def test_admin_diagnostics_keep_operational_fields() -> None:
    """Admin diagnostics may retain operational detail the customer must not see.

    The candidate-provider-attempts half of this test was removed with preview
    generator v2; progress diagnostics remain the admin-only surface that is
    allowed to carry raw commands and provider detail.
    """

    req = _request(
        generation_log=json.dumps(
            {
                "stage": "build_failed",
                "detail": "provider internal detail",
                "command": "npm run build",
            }
        ),
    )

    db = _Db(req)
    progress = AdminProgressDiagnostics.model_validate(
        get_progress_diagnostics(req.id, True, db)
    )

    assert progress.progress["command"] == "npm run build"
    assert progress.progress["detail"] == "provider internal detail"


def test_admin_diagnostics_reject_missing_credentials() -> None:
    req = _request()
    with pytest.raises(HTTPException) as exc:
        verify_admin(db=_Db(req), x_admin_password=None, authorization=None)
    assert exc.value.status_code == 401


def test_public_routes_have_no_diagnostics_switch() -> None:
    assert set(inspect.signature(get_preview).parameters) == {
        "request_id",
        "db",
    }
    assert set(inspect.signature(get_generation_progress).parameters) == {
        "request_id",
        "db",
    }
