"""Resume regressions for interrupted Phase 3B candidate generation."""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from app.application.candidate_generation.cache import sha256_text
from app.application.candidate_generation.call_budget import (
    CANDIDATE_CALL_BUDGET_POLICY_REVISION,
    CandidateCallBudget,
)
from app.application.candidate_generation.workspace import (
    candidate_root,
    checkpoint_workspace,
    open_candidate_workspace,
)
from app.application.candidate_generation.service import (
    build_v2_candidate_revision,
)
from app.core.config import settings
from app.domain.models import Request
from app.infrastructure.ai_providers.response_parser import (
    ProviderGenerationError,
    ProviderGenerationResult,
)
from app.infrastructure.templating.renderer import JinjaTemplateRenderer
from tests.candidate_generation.helpers import (
    CandidateFixtureAI,
    prepare_phase3a,
)


class _SyntheticInterruption(BaseException):
    """Simulate a process crash that bypasses normal failure persistence."""


@pytest.fixture
def isolated_candidate_paths(monkeypatch):
    root = Path(__file__).resolve().parent / ".runtime" / uuid.uuid4().hex
    candidates = root / "candidates"
    accepted = root / "accepted"
    monkeypatch.setattr(settings, "PREVIEW_CANDIDATES_DIR", candidates)
    monkeypatch.setattr(settings, "PREVIEW_APPS_DIR", accepted)
    yield root
    if root.exists():
        shutil.rmtree(root)


def _run(db, req, phase3a_result, ai):
    return build_v2_candidate_revision(
        db,
        req.id,
        ai,
        JinjaTemplateRenderer(settings.TEMPLATES_DIR),
        req=req,
        phase3a_result=phase3a_result,
    )


def _reopen_request(bind, request_id: int) -> tuple[object, Request]:
    db = sessionmaker(bind=bind)()
    req = db.get(Request, request_id)
    assert req is not None
    return db, req


def _attempt_metadata_path(request_id: int) -> Path:
    staging_root = candidate_root() / str(request_id) / ".staging"
    entries = [item for item in staging_root.iterdir() if item.is_dir()]
    assert len(entries) == 1
    return entries[0] / ".attempt.json"


def _load_attempt_metadata(request_id: int) -> dict:
    return json.loads(_attempt_metadata_path(request_id).read_text(encoding="utf-8"))


def _save_attempt_metadata(request_id: int, payload: dict) -> None:
    _attempt_metadata_path(request_id).write_text(
        json.dumps(payload, sort_keys=True),
        encoding="utf-8",
    )


def _interrupt_after_stage_write(monkeypatch, *, stage_prefix: str) -> None:
    import app.application.candidate_generation.service as service

    original = service.write_sources
    interrupted = {"done": False}

    def wrapped(workspace, sources):
        original(workspace, sources)
        if interrupted["done"]:
            return
        if any(item.path.startswith(stage_prefix) for item in sources):
            interrupted["done"] = True
            raise _SyntheticInterruption(stage_prefix)

    monkeypatch.setattr(service, "write_sources", wrapped)
    return original


def _interrupt_after_completed_stage_persist(monkeypatch, *, stage_name: str):
    import app.application.candidate_generation.service as service

    original = service._persist_completed_ai_stage
    interrupted = {"done": False}

    def wrapped(*args, **kwargs):
        result = original(*args, **kwargs)
        stage = kwargs.get("stage") if "stage" in kwargs else args[1]
        if not interrupted["done"] and stage.metrics.stage == stage_name:
            interrupted["done"] = True
            raise _SyntheticInterruption(stage_name)
        return result

    monkeypatch.setattr(service, "_persist_completed_ai_stage", wrapped)
    return original


def _interrupt_before_route_generation(monkeypatch):
    import app.application.candidate_generation.service as service

    original = service.build_route_sources
    interrupted = {"done": False}

    def wrapped(*args, **kwargs):
        if not interrupted["done"]:
            interrupted["done"] = True
            raise _SyntheticInterruption("before_routes")
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "build_route_sources", wrapped)
    return original


def test_resume_after_component_write_skips_repeating_component_call(
    isolated_candidate_paths,
    monkeypatch,
) -> None:
    prepared = prepare_phase3a(request_id=1625)
    request_id = prepared.req.id
    phase3a_result = prepared.phase3a_result
    bind = prepared.db.get_bind()
    original_write = _interrupt_after_stage_write(
        monkeypatch, stage_prefix="src/components/business/"
    )
    try:
        with pytest.raises(_SyntheticInterruption, match="src/components/business/"):
            _run(prepared.db, prepared.req, phase3a_result, CandidateFixtureAI())
    finally:
        prepared.db.close()
    import app.application.candidate_generation.service as service

    service.write_sources = original_write

    reopened_db, reopened_req = _reopen_request(bind, request_id)
    try:
        resumed_ai = CandidateFixtureAI()
        result = _run(
            reopened_db,
            reopened_req,
            phase3a_result,
            resumed_ai,
        )
        preview_contract = result["preview_contract"]
        assert preview_contract["status"] == "candidate_build_pending"
        assert preview_contract["candidate_resumed"] is True
        assert resumed_ai.calls == [
            ("pages", settings.V2_CANDIDATE_PAGE_MODEL),
        ]
        assert preview_contract["candidate_totals"]["provider_call_count"] == 2
        assert preview_contract["candidate_stage_metrics"][
            "business_components"
        ]["provider_call_count"] == 1
        assert preview_contract["candidate_stage_metrics"]["pages"][
            "provider_call_count"
        ] == 1
        ledger = preview_contract["candidate_call_ledger"]
        assert ledger["total_used"] == 2
        assert ledger["substage_used"]["business_components"] == 1
        assert ledger["substage_used"]["pages"] == 1
        checkpoints = preview_contract["candidate_stage_checkpoints"]
        assert checkpoints["business_components"]["status"] == "completed"
        assert checkpoints["pages"]["status"] == "completed"
    finally:
        reopened_db.close()


def test_resume_after_parsed_pages_output_skips_repeating_page_call(
    isolated_candidate_paths,
    monkeypatch,
) -> None:
    prepared = prepare_phase3a(request_id=1627)
    request_id = prepared.req.id
    phase3a_result = prepared.phase3a_result
    bind = prepared.db.get_bind()
    original_persist = _interrupt_after_completed_stage_persist(
        monkeypatch, stage_name="pages"
    )
    try:
        with pytest.raises(_SyntheticInterruption, match="pages"):
            _run(prepared.db, prepared.req, phase3a_result, CandidateFixtureAI())
    finally:
        prepared.db.close()
    import app.application.candidate_generation.service as service

    service._persist_completed_ai_stage = original_persist

    reopened_db, reopened_req = _reopen_request(bind, request_id)
    try:
        resumed_ai = CandidateFixtureAI()
        result = _run(
            reopened_db,
            reopened_req,
            phase3a_result,
            resumed_ai,
        )
        preview_contract = result["preview_contract"]
        assert preview_contract["status"] == "candidate_build_pending"
        assert preview_contract["candidate_resumed"] is True
        assert resumed_ai.calls == []
        assert preview_contract["candidate_totals"]["provider_call_count"] == 2
        assert preview_contract["candidate_stage_metrics"]["pages"][
            "provider_call_count"
        ] == 1
    finally:
        reopened_db.close()


def test_resume_after_page_write_skips_repeating_completed_page_call(
    isolated_candidate_paths,
    monkeypatch,
) -> None:
    prepared = prepare_phase3a(request_id=1626)
    request_id = prepared.req.id
    phase3a_result = prepared.phase3a_result
    bind = prepared.db.get_bind()
    original_write = _interrupt_after_stage_write(
        monkeypatch, stage_prefix="src/pages/"
    )
    try:
        with pytest.raises(_SyntheticInterruption, match="src/pages/"):
            _run(prepared.db, prepared.req, phase3a_result, CandidateFixtureAI())
    finally:
        prepared.db.close()
    import app.application.candidate_generation.service as service

    service.write_sources = original_write

    reopened_db, reopened_req = _reopen_request(bind, request_id)
    try:
        resumed_ai = CandidateFixtureAI()
        result = _run(
            reopened_db,
            reopened_req,
            phase3a_result,
            resumed_ai,
        )
        preview_contract = result["preview_contract"]
        assert preview_contract["status"] == "candidate_build_pending"
        assert preview_contract["candidate_resumed"] is True
        assert resumed_ai.calls == []
        assert preview_contract["candidate_totals"]["provider_call_count"] == 2
        assert preview_contract["candidate_stage_metrics"][
            "business_components"
        ]["provider_call_count"] == 1
        assert preview_contract["candidate_stage_metrics"]["pages"][
            "provider_call_count"
        ] == 1
        ledger = preview_contract["candidate_call_ledger"]
        assert ledger["total_used"] == 2
        assert ledger["substage_used"]["business_components"] == 1
        assert ledger["substage_used"]["pages"] == 1
        checkpoints = preview_contract["candidate_stage_checkpoints"]
        assert checkpoints["business_components"]["status"] == "completed"
        assert checkpoints["pages"]["status"] == "completed"
    finally:
        reopened_db.close()


def test_resume_with_inflight_pages_marker_fails_closed_without_retry(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=1628)
    request_id = prepared.req.id
    phase3a_result = prepared.phase3a_result
    bind = prepared.db.get_bind()

    class _InterruptInFlightPagesAI(CandidateFixtureAI):
        def ask_chat(
            self,
            model,
            messages,
            max_tokens=None,
            temperature=None,
            **kwargs,
        ):
            prompt = messages[0]["content"]
            if "page generation stage" in prompt:
                self.calls.append(("pages", model))
                raise _SyntheticInterruption("pages_in_flight")
            return super().ask_chat(
                model,
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )

    try:
        with pytest.raises(_SyntheticInterruption, match="pages_in_flight"):
            _run(
                prepared.db,
                prepared.req,
                phase3a_result,
                _InterruptInFlightPagesAI(),
            )
    finally:
        prepared.db.close()

    reopened_db, reopened_req = _reopen_request(bind, request_id)
    try:
        resumed_ai = CandidateFixtureAI()
        result = _run(
            reopened_db,
            reopened_req,
            phase3a_result,
            resumed_ai,
        )
        preview_contract = result["preview_contract"]
        assert preview_contract["status"] == "candidate_failed"
        assert preview_contract["candidate_resumed"] is True
        assert resumed_ai.calls == []
        assert preview_contract["failure"]["stage"] == "pages"
    finally:
        reopened_db.close()


def test_call_budget_restore_ignores_metadata_caps_and_uses_attempts() -> None:
    budget = CandidateCallBudget.restore(
        snapshot={
            "policy_revision": CANDIDATE_CALL_BUDGET_POLICY_REVISION,
            "total_max": 999,
            "substage_caps": {
                "business_components": 999,
                "pages": 999,
            },
            "total_used": 0,
            "substage_used": {
                "business_components": 0,
                "pages": 0,
            },
            "events": [],
            "checkpoints": {},
        },
        attempts=[
            {
                "attempt_id": "attempt-components",
                "request_id": 1,
                "candidate_revision_uuid": "rev",
                "substage": "business_components",
                "provider": "candidate-fixture",
                "model": settings.V2_CANDIDATE_COMPONENT_MODEL,
                "http_status": 200,
                "response_top_level_keys": ["files"],
                "response_format": "structured_json",
                "provider_request_id": "",
                "raw_payload_sha256": "a" * 64,
                "duration_ms": 1,
                "input_tokens": 10,
                "output_tokens": 10,
                "total_tokens": 20,
                "typed_result": "completed",
                "error_code": "",
                "retryable": False,
                "retry_attempted": False,
                "terminal_decision": "completed",
                "parent_attempt_id": "",
                "idempotency_key": "rev:business_components:completed",
                "error_type": "",
                "error_message_redacted": "",
                "error_metadata_keys": [],
                "request_shape_hash": "",
                "capability_profile_revision": "",
                "retry_decision_reason": "",
                "fallback_model_decision": "",
                "calls_remaining": 3,
                "context_window": None,
                "estimated_input_tokens": None,
                "requested_output_tokens": None,
                "clamped_output_tokens": None,
                "minimum_output_allowance": None,
                "context_reserve": None,
                "approval_decision": "approved",
            }
        ],
    )
    snapshot = budget.snapshot()
    assert snapshot["total_max"] == settings.V2_CANDIDATE_MAX_CALLS
    assert snapshot["substage_caps"]["business_components"] == 2
    assert snapshot["substage_caps"]["pages"] == 2
    assert snapshot["total_used"] == 1
    assert snapshot["substage_used"]["business_components"] == 1


def test_call_budget_restore_rejects_tampered_counts_and_duplicates() -> None:
    with pytest.raises(ValueError, match="candidate call budget restore"):
        CandidateCallBudget.restore(
            snapshot={
                "policy_revision": CANDIDATE_CALL_BUDGET_POLICY_REVISION,
                "total_used": 4,
                "substage_used": {
                    "business_components": 2,
                    "pages": 2,
                },
                "events": [],
                "checkpoints": {},
            },
            attempts=[
                {
                    "attempt_id": "dup",
                    "request_id": 1,
                    "candidate_revision_uuid": "rev",
                    "substage": "business_components",
                    "provider": "candidate-fixture",
                    "model": settings.V2_CANDIDATE_COMPONENT_MODEL,
                    "http_status": 200,
                    "response_top_level_keys": ["files"],
                    "response_format": "structured_json",
                    "provider_request_id": "",
                    "raw_payload_sha256": "a" * 64,
                    "duration_ms": 1,
                    "input_tokens": 10,
                    "output_tokens": 10,
                    "total_tokens": 20,
                    "typed_result": "completed",
                    "error_code": "",
                    "retryable": False,
                    "retry_attempted": False,
                    "terminal_decision": "completed",
                    "parent_attempt_id": "",
                    "idempotency_key": "same",
                    "error_type": "",
                    "error_message_redacted": "",
                    "error_metadata_keys": [],
                    "request_shape_hash": "",
                    "capability_profile_revision": "",
                    "retry_decision_reason": "",
                    "fallback_model_decision": "",
                    "calls_remaining": 3,
                    "context_window": None,
                    "estimated_input_tokens": None,
                    "requested_output_tokens": None,
                    "clamped_output_tokens": None,
                    "minimum_output_allowance": None,
                    "context_reserve": None,
                    "approval_decision": "approved",
                },
                {
                    "attempt_id": "dup",
                    "request_id": 1,
                    "candidate_revision_uuid": "rev",
                    "substage": "business_components",
                    "provider": "candidate-fixture",
                    "model": settings.V2_CANDIDATE_COMPONENT_MODEL,
                    "http_status": 200,
                    "response_top_level_keys": ["files"],
                    "response_format": "structured_json",
                    "provider_request_id": "",
                    "raw_payload_sha256": "b" * 64,
                    "duration_ms": 1,
                    "input_tokens": 10,
                    "output_tokens": 10,
                    "total_tokens": 20,
                    "typed_result": "completed",
                    "error_code": "",
                    "retryable": False,
                    "retry_attempted": False,
                    "terminal_decision": "completed",
                    "parent_attempt_id": "",
                    "idempotency_key": "same",
                    "error_type": "",
                    "error_message_redacted": "",
                    "error_metadata_keys": [],
                    "request_shape_hash": "",
                    "capability_profile_revision": "",
                    "retry_decision_reason": "",
                    "fallback_model_decision": "",
                    "calls_remaining": 3,
                    "context_window": None,
                    "estimated_input_tokens": None,
                    "requested_output_tokens": None,
                    "clamped_output_tokens": None,
                    "minimum_output_allowance": None,
                    "context_reserve": None,
                    "approval_decision": "approved",
                },
            ],
        )


def test_resume_rejects_tampered_checkpoint_output_hash(
    isolated_candidate_paths,
    monkeypatch,
) -> None:
    prepared = prepare_phase3a(request_id=1629)
    request_id = prepared.req.id
    phase3a_result = prepared.phase3a_result
    bind = prepared.db.get_bind()
    original_build_routes = _interrupt_before_route_generation(monkeypatch)
    try:
        with pytest.raises(_SyntheticInterruption, match="before_routes"):
            _run(prepared.db, prepared.req, phase3a_result, CandidateFixtureAI())
    finally:
        prepared.db.close()
    import app.application.candidate_generation.service as service

    service.build_route_sources = original_build_routes

    metadata = _load_attempt_metadata(request_id)
    metadata["candidate_call_ledger"]["checkpoints"]["pages"]["output_hash"] = (
        "0" * 64
    )
    _save_attempt_metadata(request_id, metadata)

    reopened_db, reopened_req = _reopen_request(bind, request_id)
    try:
        resumed_ai = CandidateFixtureAI()
        result = _run(
            reopened_db,
            reopened_req,
            phase3a_result,
            resumed_ai,
        )
        preview_contract = result["preview_contract"]
        assert preview_contract["status"] == "candidate_failed"
        assert resumed_ai.calls == []
        assert preview_contract["failure"]["stage"] == "pages"
    finally:
        reopened_db.close()


def test_resume_rejects_tampered_checkpoint_source_hashes(
    isolated_candidate_paths,
    monkeypatch,
) -> None:
    prepared = prepare_phase3a(request_id=1630)
    request_id = prepared.req.id
    phase3a_result = prepared.phase3a_result
    bind = prepared.db.get_bind()
    original_build_routes = _interrupt_before_route_generation(monkeypatch)
    try:
        with pytest.raises(_SyntheticInterruption, match="before_routes"):
            _run(prepared.db, prepared.req, phase3a_result, CandidateFixtureAI())
    finally:
        prepared.db.close()
    import app.application.candidate_generation.service as service

    service.build_route_sources = original_build_routes

    metadata = _load_attempt_metadata(request_id)
    page_path = next(
        path
        for path in metadata["completed_artifacts"]
        if path.startswith("src/pages/")
    )
    tampered = _attempt_metadata_path(request_id).parent / page_path
    tampered.write_text("tampered", encoding="utf-8")

    reopened_db, reopened_req = _reopen_request(bind, request_id)
    try:
        resumed_ai = CandidateFixtureAI()
        result = _run(
            reopened_db,
            reopened_req,
            phase3a_result,
            resumed_ai,
        )
        preview_contract = result["preview_contract"]
        assert preview_contract["status"] == "candidate_failed"
        assert resumed_ai.calls == []
        assert preview_contract["failure"]["stage"] == "pages"
    finally:
        reopened_db.close()


def test_checkpoint_workspace_replace_failure_cleans_temp_file(
    isolated_candidate_paths,
    monkeypatch,
) -> None:
    workspace = open_candidate_workspace(
        request_id=1991,
        upstream_sha256="a" * 64,
    )
    metadata_path = workspace.staging_path / ".attempt.json"
    original = metadata_path.read_text(encoding="utf-8")

    def fail_replace(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr(
        "app.application.candidate_generation.workspace.os.replace",
        fail_replace,
    )
    with pytest.raises(OSError, match="replace failed"):
        checkpoint_workspace(
            workspace,
            upstream_sha256="a" * 64,
            completed_artifacts={"src/App.tsx": "b" * 64},
            completed_stage_state={},
            candidate_call_ledger={},
            candidate_provider_attempts=[],
        )
    assert metadata_path.read_text(encoding="utf-8") == original
    assert not list(workspace.staging_path.glob(".attempt.json.*"))


def test_torn_attempt_json_restart_fails_closed_without_new_workspace(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=1631)
    request_id = prepared.req.id
    phase3a_result = prepared.phase3a_result
    bind = prepared.db.get_bind()
    try:
        _run(prepared.db, prepared.req, phase3a_result, CandidateFixtureAI())
        staged = open_candidate_workspace(
            request_id=request_id,
            upstream_sha256="force-different",
        )
        metadata_path = staged.staging_path / ".attempt.json"
        metadata_path.write_text("{", encoding="utf-8")
    finally:
        prepared.db.close()

    reopened_db, reopened_req = _reopen_request(bind, request_id)
    try:
        resumed_ai = CandidateFixtureAI()
        result = _run(
            reopened_db,
            reopened_req,
            phase3a_result,
            resumed_ai,
        )
        preview_contract = result["preview_contract"]
        assert preview_contract["status"] == "candidate_failed"
        assert preview_contract["candidate_resumed"] is True
        assert resumed_ai.calls == []
        assert preview_contract["failure"]["stage"] == "candidate_generation"
    finally:
        reopened_db.close()


def test_completed_pages_checkpoint_preserves_attempt_linkage(
    isolated_candidate_paths,
    monkeypatch,
) -> None:
    prepared = prepare_phase3a(request_id=1632)
    request_id = prepared.req.id
    original_build_routes = _interrupt_before_route_generation(monkeypatch)
    try:
        with pytest.raises(_SyntheticInterruption, match="before_routes"):
            _run(prepared.db, prepared.req, prepared.phase3a_result, CandidateFixtureAI())
    finally:
        prepared.db.close()
    import app.application.candidate_generation.service as service

    service.build_route_sources = original_build_routes

    metadata = _load_attempt_metadata(request_id)
    pages_state = metadata["completed_stage_state"]["pages"]
    pages_checkpoint = metadata["candidate_call_ledger"]["checkpoints"]["pages"]
    assert pages_state["provider_attempt_id"]
    assert pages_state["idempotency_key"]
    assert pages_state["provider_attempt_id"] == pages_checkpoint["provider_attempt_id"]
    assert pages_state["idempotency_key"] == pages_checkpoint["idempotency_key"]


def test_successful_retry_attempt_keeps_parent_linkage(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=1633)

    class _RetryOnceAI(CandidateFixtureAI):
        def __init__(self) -> None:
            super().__init__()
            self.failed = False

        def ask_chat(
            self,
            model,
            messages,
            max_tokens=None,
            temperature=None,
            **kwargs,
        ):
            prompt = messages[0]["content"]
            if (
                "business-component generation stage" in prompt
                and not self.failed
            ):
                self.failed = True
                result = ProviderGenerationResult(
                    provider="openrouter",
                    model=model,
                    provider_request_id="",
                    response_format="provider_error",
                    text="",
                    structured_payload=None,
                    finish_reason="",
                    input_tokens=0,
                    output_tokens=0,
                    total_tokens=0,
                    http_status=200,
                    raw_payload_sha256="abc",
                    is_success=False,
                    error_code="provider_server_error",
                    error_message_redacted="upstream error",
                    retryable=True,
                    refusal=False,
                    truncated=False,
                    latency_ms=5,
                    response_top_level_keys=("error",),
                )
                raise ProviderGenerationError("upstream error", result=result)
            return super().ask_chat(
                model,
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )

    try:
        result = _run(prepared.db, prepared.req, prepared.phase3a_result, _RetryOnceAI())
        attempts = result["preview_contract"]["candidate_provider_attempts"]
        business_attempts = [
            item
            for item in attempts
            if item["substage"] == "business_components"
            and item["response_format"] != "preflight"
        ]
        assert len(business_attempts) == 2
        first, second = business_attempts
        assert first["terminal_decision"] == "retry_pending"
        assert first["retry_attempted"] is False
        assert second["terminal_decision"] == "completed"
        assert second["retry_attempted"] is True
        assert second["parent_attempt_id"] == first["attempt_id"]
    finally:
        prepared.db.close()


def test_open_candidate_workspace_selects_latest_verified_checkpoint(
    isolated_candidate_paths,
) -> None:
    request_id = 2440
    upstream_sha256 = "a" * 64
    first = open_candidate_workspace(
        request_id=request_id,
        upstream_sha256=upstream_sha256,
        policy_revision=CANDIDATE_CALL_BUDGET_POLICY_REVISION,
    )
    component_relpath = "src/components/business/CompResume.tsx"
    component_source = "export const CompResume = () => null;\n"
    component_path = first.staging_path / component_relpath
    component_path.parent.mkdir(parents=True, exist_ok=True)
    component_path.write_text(component_source, encoding="utf-8")
    checkpoint_workspace(
        first,
        upstream_sha256=upstream_sha256,
        policy_revision=CANDIDATE_CALL_BUDGET_POLICY_REVISION,
        completed_artifacts={
            component_relpath: sha256_text(component_source),
        },
        completed_stage_state={
            "business_components": {"status": "completed"},
        },
        candidate_call_ledger={"substage_used": {"business_components": 1, "pages": 0}},
        candidate_provider_attempts=[
            {"substage": "business_components", "status": "completed"}
        ],
    )

    staging_root = candidate_root() / str(request_id) / ".staging"
    second_uuid = str(uuid.uuid4())
    second_path = staging_root / second_uuid
    shutil.copytree(first.staging_path, second_path)
    page_relpath = "src/pages/PageResume.tsx"
    page_source = "export const PageResume = () => null;\n"
    page_path = second_path / page_relpath
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(page_source, encoding="utf-8")

    first_metadata_path = first.staging_path / ".attempt.json"
    second_metadata_path = second_path / ".attempt.json"
    first_payload = json.loads(first_metadata_path.read_text(encoding="utf-8"))
    second_payload = json.loads(second_metadata_path.read_text(encoding="utf-8"))
    first_payload["checkpointed_at_utc"] = "2026-07-26T20:00:00+00:00"
    second_payload["revision_uuid"] = second_uuid
    second_payload["checkpointed_at_utc"] = "2026-07-26T20:05:00+00:00"
    second_payload["completed_artifacts"][page_relpath] = sha256_text(page_source)
    second_payload["completed_stage_state"]["pages"] = {"status": "completed"}
    second_payload["candidate_call_ledger"]["substage_used"]["pages"] = 1
    second_payload["candidate_provider_attempts"].append(
        {"substage": "pages", "status": "completed"}
    )
    first_metadata_path.write_text(
        json.dumps(first_payload, sort_keys=True),
        encoding="utf-8",
    )
    second_metadata_path.write_text(
        json.dumps(second_payload, sort_keys=True),
        encoding="utf-8",
    )

    resumed = open_candidate_workspace(
        request_id=request_id,
        upstream_sha256=upstream_sha256,
        policy_revision=CANDIDATE_CALL_BUDGET_POLICY_REVISION,
    )

    assert resumed.resumed is True
    assert resumed.revision_uuid == second_uuid
    assert resumed.resume_state is not None
    assert (
        resumed.resume_state["completed_stage_state"]["pages"]["status"] == "completed"
    )
    assert resumed.resume_state["candidate_call_ledger"]["substage_used"]["pages"] == 1


def test_open_candidate_workspace_fails_closed_on_equal_best_rank_tie(
    isolated_candidate_paths,
) -> None:
    request_id = 2441
    upstream_sha256 = "b" * 64
    first = open_candidate_workspace(
        request_id=request_id,
        upstream_sha256=upstream_sha256,
        policy_revision=CANDIDATE_CALL_BUDGET_POLICY_REVISION,
    )
    source_relpath = "src/components/business/CompTie.tsx"
    source_text = "export const CompTie = () => null;\n"
    source_path = first.staging_path / source_relpath
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(source_text, encoding="utf-8")
    checkpoint_workspace(
        first,
        upstream_sha256=upstream_sha256,
        policy_revision=CANDIDATE_CALL_BUDGET_POLICY_REVISION,
        completed_artifacts={source_relpath: sha256_text(source_text)},
        completed_stage_state={
            "business_components": {"status": "completed"},
        },
        candidate_call_ledger={"substage_used": {"business_components": 1, "pages": 0}},
        candidate_provider_attempts=[
            {"substage": "business_components", "status": "completed"}
        ],
    )
    staging_root = candidate_root() / str(request_id) / ".staging"
    second_uuid = str(uuid.uuid4())
    second_path = staging_root / second_uuid
    shutil.copytree(first.staging_path, second_path)

    first_metadata_path = first.staging_path / ".attempt.json"
    second_metadata_path = second_path / ".attempt.json"
    first_payload = json.loads(first_metadata_path.read_text(encoding="utf-8"))
    second_payload = json.loads(second_metadata_path.read_text(encoding="utf-8"))
    tie_timestamp = "2026-07-26T21:00:00+00:00"
    first_payload["checkpointed_at_utc"] = tie_timestamp
    second_payload["revision_uuid"] = second_uuid
    second_payload["checkpointed_at_utc"] = tie_timestamp
    first_metadata_path.write_text(json.dumps(first_payload, sort_keys=True), encoding="utf-8")
    second_metadata_path.write_text(json.dumps(second_payload, sort_keys=True), encoding="utf-8")

    resumed = open_candidate_workspace(
        request_id=request_id,
        upstream_sha256=upstream_sha256,
        policy_revision=CANDIDATE_CALL_BUDGET_POLICY_REVISION,
    )

    assert resumed.resumed is True
    assert resumed.resume_invalid_reason == "ambiguous_resume_checkpoint"
