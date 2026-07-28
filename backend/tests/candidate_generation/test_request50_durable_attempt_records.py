"""Request #50: durable candidate attempt records + correct failure labels.

Production #50:
- AppSpec and Phase 3A completed
- business_components made a paid provider call (13.8s, 0 tokens logged)
- only the preflight attempt row was persisted; the paid attempt vanished
- progress stage was candidate_failed but label said "passed static validation"

This suite proves the before/after: every paid attempt is opened before the
provider call and finalized on every failure branch, and failed statuses never
render a success-shaped message.
"""
from __future__ import annotations

import json
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application.appspec.source import canonical_json
from app.application.candidate_generation.builder import (
    CandidateStageError,
    repair_ai_batch,
)
from app.application.candidate_generation.call_budget import (
    CANDIDATE_CALL_BUDGET_POLICY_REVISION,
    CandidateCallBudget,
    CandidateProviderAttempt,
)
from app.application.candidate_generation.policy import repair_policy
from app.application.candidate_generation.service import (
    build_v2_candidate_revision,
)
from app.application.candidate_generation.workspace import candidate_root
from app.application.pipelines import orchestrator as full_orchestrator
from app.core.config import settings
from app.domain.models import Request
from app.domain.schemas.preview_candidate import (
    GeneratedCandidateBatch,
    GeneratedCandidateFile,
)
from app.infrastructure.ai_providers.response_parser import (
    ProviderGenerationError,
    ProviderGenerationResult,
)
from app.infrastructure.db.base import Base
from app.infrastructure.templating.renderer import JinjaTemplateRenderer
from tests.candidate_generation.helpers import (
    CandidateFixtureAI,
    prepare_phase3a,
)

HOME_PATH = "src/components/business/CompHomeComponent.tsx"
BOOK_PATH = "src/components/business/CompBookComponent.tsx"

REQUIRED_ATTEMPT_FIELDS = (
    "substage",
    "provider",
    "model",
    "attempt_number",
    "started_at",
    "finished_at",
    "terminal_decision",
    "error_code",
    "error_message_redacted",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "last_checkpoint_status",
)


class _SyntheticInterruption(BaseException):
    """Simulate a process crash that bypasses normal failure persistence."""


@pytest.fixture
def isolated_candidate_paths(monkeypatch):
    root = Path(__file__).resolve().parent / ".runtime" / uuid.uuid4().hex
    monkeypatch.setattr(settings, "PREVIEW_CANDIDATES_DIR", root / "candidates")
    monkeypatch.setattr(settings, "PREVIEW_APPS_DIR", root / "accepted")
    yield root
    if root.exists():
        shutil.rmtree(root)


def _run(prepared, ai):
    return build_v2_candidate_revision(
        prepared.db,
        prepared.req.id,
        ai,
        JinjaTemplateRenderer(settings.TEMPLATES_DIR),
        req=prepared.req,
        phase3a_result=prepared.phase3a_result,
    )


def _paid_attempts(attempts: list[dict]) -> list[dict]:
    return [
        item
        for item in attempts
        if item.get("response_format") != "preflight"
        and not str(item.get("idempotency_key") or "").endswith(":preflight")
        and item.get("terminal_decision") != "fail_closed_preflight"
    ]


def _assert_required_fields(attempt: dict, *, expect_finished: bool) -> None:
    for field in REQUIRED_ATTEMPT_FIELDS:
        assert field in attempt, f"missing field {field}"
    assert attempt["substage"]
    assert attempt["provider"]
    assert attempt["model"]
    assert int(attempt["attempt_number"]) >= 1
    assert float(attempt["started_at"]) > 0
    if expect_finished:
        assert float(attempt["finished_at"]) > 0
        assert attempt["terminal_decision"] != "in_flight"
    else:
        assert float(attempt["finished_at"]) == 0.0
        assert attempt["terminal_decision"] == "in_flight"


def _assert_unique_identities(attempts: list[dict]) -> None:
    attempt_ids = [item["attempt_id"] for item in attempts]
    idempotency_keys = [item["idempotency_key"] for item in attempts]
    assert len(attempt_ids) == len(set(attempt_ids))
    assert len(idempotency_keys) == len(set(idempotency_keys))


def _restore_round_trip(ledger: dict, attempts: list[dict]) -> CandidateCallBudget:
    return CandidateCallBudget.restore(snapshot=ledger, attempts=attempts)


def _attempt_metadata(request_id: int) -> dict:
    staging_root = candidate_root() / str(request_id) / ".staging"
    entries = [item for item in staging_root.iterdir() if item.is_dir()]
    assert len(entries) == 1
    return json.loads((entries[0] / ".attempt.json").read_text(encoding="utf-8"))


def _provider_error(
    *,
    model: str,
    error_code: str,
    message: str,
    retryable: bool,
) -> ProviderGenerationError:
    return ProviderGenerationError(
        message,
        result=ProviderGenerationResult(
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
            raw_payload_sha256="req50",
            is_success=False,
            error_code=error_code,
            error_message_redacted=message,
            retryable=retryable,
            refusal=False,
            truncated=False,
            latency_ms=5,
            response_top_level_keys=("error",),
        ),
    )


# ---------------------------------------------------------------------------
# call_budget unit behaviour
# ---------------------------------------------------------------------------


def test_record_attempt_upserts_by_attempt_id() -> None:
    budget = CandidateCallBudget.create()
    first = CandidateProviderAttempt(
        attempt_id="same-id",
        request_id=50,
        candidate_revision_uuid="rev",
        substage="business_components",
        provider="openrouter",
        model="google/gemini-2.5-flash",
        http_status=0,
        response_top_level_keys=[],
        response_format="in_flight",
        provider_request_id="",
        raw_payload_sha256="",
        duration_ms=0,
        input_tokens=10,
        output_tokens=0,
        total_tokens=10,
        typed_result="in_flight",
        error_code="",
        retryable=False,
        retry_attempted=False,
        terminal_decision="in_flight",
        idempotency_key="rev:business_components:gen:0",
        attempt_number=1,
        started_at=1.0,
        finished_at=0.0,
    )
    budget.record_attempt(first)
    final = CandidateProviderAttempt(
        attempt_id="same-id",
        request_id=50,
        candidate_revision_uuid="rev",
        substage="business_components",
        provider="openrouter",
        model="google/gemini-2.5-flash",
        http_status=200,
        response_top_level_keys=["error"],
        response_format="provider_error",
        provider_request_id="",
        raw_payload_sha256="abc",
        duration_ms=12,
        input_tokens=10,
        output_tokens=0,
        total_tokens=10,
        typed_result="provider_server_error",
        error_code="provider_server_error",
        retryable=False,
        retry_attempted=False,
        terminal_decision="fail_closed",
        idempotency_key="rev:business_components:gen:0",
        error_message_redacted="upstream error",
        attempt_number=1,
        started_at=1.0,
        finished_at=2.0,
    )
    budget.record_attempt(final)
    snapshot = budget.attempts_snapshot()
    assert len(snapshot) == 1
    assert snapshot[0]["terminal_decision"] == "fail_closed"
    assert snapshot[0]["error_code"] == "provider_server_error"
    assert snapshot[0]["finished_at"] == 2.0


def test_open_attempt_number_is_monotonic_across_restore() -> None:
    budget = CandidateCallBudget.create()
    assert budget.open_attempt_number() == 1
    assert budget.open_attempt_number() == 2
    ok, _ = budget.approve(
        "business_components",
        attempt_type="ai",
        idempotency_key="rev:business_components:gen:0",
    )
    assert ok
    budget.record_attempt(
        CandidateProviderAttempt(
            attempt_id="a1",
            request_id=50,
            candidate_revision_uuid="rev",
            substage="business_components",
            provider="openrouter",
            model="m",
            http_status=200,
            response_top_level_keys=[],
            response_format="structured_json",
            provider_request_id="",
            raw_payload_sha256="x",
            duration_ms=1,
            input_tokens=1,
            output_tokens=1,
            total_tokens=2,
            typed_result="completed",
            error_code="",
            retryable=False,
            retry_attempted=False,
            terminal_decision="completed",
            idempotency_key="rev:business_components:gen:0",
            attempt_number=2,
            started_at=1.0,
            finished_at=2.0,
        )
    )
    restored = CandidateCallBudget.restore(
        snapshot=budget.snapshot(),
        attempts=budget.attempts_snapshot(),
    )
    assert restored.open_attempt_number() == 3


# ---------------------------------------------------------------------------
# build path: provider / parse / batch_kind failures
# ---------------------------------------------------------------------------


def test_build_provider_failure_persists_paid_attempt(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=5001)

    class _FailAI(CandidateFixtureAI):
        def ask_chat(self, model, messages, max_tokens=None, temperature=None, **kwargs):
            prompt = messages[0]["content"]
            if "business-component generation stage" in prompt:
                self.calls.append(("business_components", model))
                raise _provider_error(
                    model=model,
                    error_code="provider_response_shape_invalid",
                    message="unexpected shape",
                    retryable=False,
                )
            return super().ask_chat(
                model, messages, max_tokens=max_tokens, temperature=temperature, **kwargs
            )

    try:
        result = _run(prepared, _FailAI())
        pc = result["preview_contract"]
        assert pc["status"] == "candidate_failed"
        attempts = pc["candidate_provider_attempts"]
        paid = _paid_attempts(attempts)
        assert paid
        failed = [item for item in paid if item.get("error_code")]
        assert failed
        row = failed[0]
        assert row["error_code"] == "provider_response_shape_invalid"
        assert row["terminal_decision"] == "fail_closed"
        assert row["substage"] == "business_components"
        _assert_required_fields(row, expect_finished=True)
        _assert_unique_identities(attempts)
        _restore_round_trip(pc["candidate_call_ledger"], attempts)
    finally:
        prepared.db.close()


def test_build_parse_failure_persists_paid_attempt(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=5002)

    class _BadJsonAI(CandidateFixtureAI):
        def ask_chat(self, model, messages, max_tokens=None, temperature=None, **kwargs):
            prompt = messages[0]["content"]
            if "business-component generation stage" in prompt:
                self.calls.append(("business_components", model))
                return "this is not structured json {"
            return super().ask_chat(
                model, messages, max_tokens=max_tokens, temperature=temperature, **kwargs
            )

    try:
        result = _run(prepared, _BadJsonAI())
        pc = result["preview_contract"]
        assert pc["status"] == "candidate_failed"
        paid = _paid_attempts(pc["candidate_provider_attempts"])
        assert any(
            item.get("error_code") == "provider_structured_output_invalid"
            for item in paid
        )
        row = next(
            item
            for item in paid
            if item.get("error_code") == "provider_structured_output_invalid"
        )
        assert row["terminal_decision"] == "fail_closed"
        assert row["error_type"] == "local_validation"
        assert row["raw_payload_sha256"]
        _assert_required_fields(row, expect_finished=True)
        _assert_unique_identities(pc["candidate_provider_attempts"])
        _restore_round_trip(
            pc["candidate_call_ledger"],
            pc["candidate_provider_attempts"],
        )
    finally:
        prepared.db.close()


def test_build_batch_kind_mismatch_persists_paid_attempt(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=5003)

    class _WrongKindAI(CandidateFixtureAI):
        def ask_chat(self, model, messages, max_tokens=None, temperature=None, **kwargs):
            prompt = messages[0]["content"]
            if "business-component generation stage" in prompt:
                payload = json.loads(super().ask_chat(
                    model, messages, max_tokens=max_tokens, temperature=temperature, **kwargs
                ))
                # undo the call bookkeeping from super for a clean assertion surface
                self.calls.pop()
                self.calls.append(("business_components", model))
                payload["batch_kind"] = "pages"
                return json.dumps(payload)
            return super().ask_chat(
                model, messages, max_tokens=max_tokens, temperature=temperature, **kwargs
            )

    try:
        result = _run(prepared, _WrongKindAI())
        pc = result["preview_contract"]
        assert pc["status"] == "candidate_failed"
        paid = _paid_attempts(pc["candidate_provider_attempts"])
        row = next(
            item
            for item in paid
            if item.get("error_code") == "candidate_batch_kind_mismatch"
        )
        assert row["terminal_decision"] == "fail_closed"
        assert "expected batch_kind" in row["error_message_redacted"]
        _assert_required_fields(row, expect_finished=True)
    finally:
        prepared.db.close()


def test_process_death_mid_call_leaves_durable_in_flight_attempt(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=5004)
    request_id = prepared.req.id

    class _CrashAI(CandidateFixtureAI):
        def ask_chat(self, model, messages, max_tokens=None, temperature=None, **kwargs):
            prompt = messages[0]["content"]
            if "business-component generation stage" in prompt:
                self.calls.append(("business_components", model))
                raise _SyntheticInterruption("components_in_flight")
            return super().ask_chat(
                model, messages, max_tokens=max_tokens, temperature=temperature, **kwargs
            )

    try:
        with pytest.raises(_SyntheticInterruption, match="components_in_flight"):
            _run(prepared, _CrashAI())
    finally:
        prepared.db.close()

    meta = _attempt_metadata(request_id)
    attempts = meta["candidate_provider_attempts"]
    paid = _paid_attempts(attempts)
    assert paid, "paid in-flight row must be durable before the provider returns"
    inflight = [
        item for item in paid if item.get("terminal_decision") == "in_flight"
    ]
    assert inflight
    row = inflight[0]
    assert row["substage"] == "business_components"
    assert row["response_format"] == "in_flight"
    assert row["typed_result"] == "in_flight"
    _assert_required_fields(row, expect_finished=False)
    assert meta["completed_stage_state"]["business_components"]["status"] == "in_flight"
    _assert_unique_identities(attempts)
    _restore_round_trip(meta["candidate_call_ledger"], attempts)


def test_successful_run_has_unique_ids_and_restores(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=5005)
    try:
        result = _run(prepared, CandidateFixtureAI())
        pc = result["preview_contract"]
        assert pc["status"] == "candidate_build_pending"
        attempts = pc["candidate_provider_attempts"]
        assert attempts
        _assert_unique_identities(attempts)
        for row in _paid_attempts(attempts):
            _assert_required_fields(row, expect_finished=True)
            assert row["terminal_decision"] == "completed"
            assert row["error_code"] == ""
        restored = _restore_round_trip(pc["candidate_call_ledger"], attempts)
        assert restored.snapshot()["total_used"] == pc["candidate_call_ledger"]["total_used"]
        assert (
            restored.snapshot()["policy_revision"]
            == CANDIDATE_CALL_BUDGET_POLICY_REVISION
        )
    finally:
        prepared.db.close()


# ---------------------------------------------------------------------------
# repair path: five distinct failure branches
# ---------------------------------------------------------------------------


def _original_batch() -> GeneratedCandidateBatch:
    return GeneratedCandidateBatch(
        schema_version="1.0",
        batch_kind="business_components",
        files=[
            GeneratedCandidateFile(
                path=BOOK_PATH,
                file_kind="business_component",
                owner_contract_ids=["COMP-BOOK"],
                source=(
                    "export function CompBookComponent() {\n"
                    '  return <div data-bmv-component-id="COMP-BOOK">Book</div>;\n'
                    "}"
                ),
            ),
            GeneratedCandidateFile(
                path=HOME_PATH,
                file_kind="business_component",
                owner_contract_ids=["COMP-HOME"],
                source=(
                    "export function CompHomeComponent() {\n"
                    "  return <div>Home without contract hook</div>;\n"
                    "}"
                ),
            ),
        ],
    )


def _canonical_repair_payload(**overrides) -> dict:
    payload = {
        "schema_version": "1.0",
        "batch_kind": "business_components",
        "files": [
            {
                "path": HOME_PATH,
                "file_kind": "business_component",
                "owner_contract_ids": ["COMP-HOME"],
                "source": (
                    "export function CompHomeComponent() {\n"
                    '  return <div data-bmv-component-id="COMP-HOME">Home</div>;\n'
                    "}"
                ),
            }
        ],
    }
    payload.update(overrides)
    return payload


def _run_repair(ai, *, phase_deadline: float | None = None) -> CandidateCallBudget:
    budget = CandidateCallBudget.create()
    assert budget.approve("business_components")[0]
    repair_ai_batch(
        request_id=50,
        batch_stage="business_components",
        policy=repair_policy(),
        batch=_original_batch(),
        diagnostics=(
            canonical_json(
                {
                    "code": "missing_component_hook",
                    "path": HOME_PATH,
                    "related_ids": ["COMP-HOME"],
                }
            ),
        ),
        canonical_bindings={
            "business_component_plan": {
                "components": [
                    {"component_id": "COMP-HOME", "purpose": "home"},
                    {"component_id": "COMP-BOOK", "purpose": "book"},
                ]
            }
        },
        ai_provider=ai,
        template_renderer=JinjaTemplateRenderer(settings.TEMPLATES_DIR),
        prompt_template="prompts/v2_candidate_repair.j2",
        phase_deadline=phase_deadline if phase_deadline is not None else time.monotonic() + 60,
        call_budget=budget,
        candidate_revision_uuid="req50",
    )
    return budget


def _single_paid_repair_row(budget: CandidateCallBudget) -> dict:
    attempts = budget.attempts_snapshot()
    _assert_unique_identities(attempts)
    paid = _paid_attempts(attempts)
    # The open row used response_format=preflight; after finalization there
    # must be exactly one non-preflight row (the upserted terminal state).
    assert len(paid) == 1, paid
    return paid[0]


class _RepairAI:
    name = "openrouter"

    def __init__(self, response: str | Exception) -> None:
        self._response = response
        self.calls: list[dict] = []

    def ask_chat(self, model, messages, max_tokens=None, temperature=None, **kwargs):
        self.calls.append(
            {
                "model": model,
                "prompt": messages[0]["content"],
                "max_tokens": max_tokens,
                **kwargs,
            }
        )
        if isinstance(self._response, Exception):
            raise self._response
        return self._response

    def last_completion_meta(self) -> dict:
        return {"finish_reason": "stop"}

    def last_response_envelope(self):
        return None

    def is_available(self) -> bool:
        return True

    def cancel_inflight(self) -> None:
        return None


def test_repair_timeout_finalizes_same_attempt_id() -> None:
    class _HungAI(_RepairAI):
        def __init__(self) -> None:
            super().__init__("{}")

        def ask_chat(self, *args, **kwargs):
            time.sleep(0.35)
            return "{}"

    with pytest.raises(CandidateStageError) as exc:
        budget = CandidateCallBudget.create()
        assert budget.approve("business_components")[0]
        repair_ai_batch(
            request_id=50,
            batch_stage="business_components",
            policy=repair_policy(),
            batch=_original_batch(),
            diagnostics=(
                canonical_json(
                    {
                        "code": "missing_component_hook",
                        "path": HOME_PATH,
                        "related_ids": ["COMP-HOME"],
                    }
                ),
            ),
            canonical_bindings={
                "business_component_plan": {"components": []}
            },
            ai_provider=_HungAI(),
            template_renderer=JinjaTemplateRenderer(settings.TEMPLATES_DIR),
            prompt_template="prompts/v2_candidate_repair.j2",
            phase_deadline=time.monotonic() + 0.2,
            call_budget=budget,
            candidate_revision_uuid="req50-timeout",
        )
    assert exc.value.provider_error_code == "candidate_stage_wall_timeout"
    row = _single_paid_repair_row(budget)
    assert row["error_code"] == "candidate_stage_wall_timeout"
    assert row["terminal_decision"] == "fail_closed"
    assert row["response_format"] == "repair_timeout"
    _assert_required_fields(row, expect_finished=True)
    _restore_round_trip(budget.snapshot(), budget.attempts_snapshot())


def test_repair_provider_error_finalizes_same_attempt_id() -> None:
    err = _provider_error(
        model=settings.V2_CANDIDATE_REPAIR_MODEL,
        error_code="provider_server_error",
        message="upstream blew up",
        retryable=False,
    )
    budget = CandidateCallBudget.create()
    assert budget.approve("business_components")[0]
    with pytest.raises(CandidateStageError) as exc:
        repair_ai_batch(
            request_id=50,
            batch_stage="business_components",
            policy=repair_policy(),
            batch=_original_batch(),
            diagnostics=(
                canonical_json(
                    {
                        "code": "missing_component_hook",
                        "path": HOME_PATH,
                        "related_ids": ["COMP-HOME"],
                    }
                ),
            ),
            canonical_bindings={
                "business_component_plan": {
                    "components": [
                        {"component_id": "COMP-HOME", "purpose": "home"},
                        {"component_id": "COMP-BOOK", "purpose": "book"},
                    ]
                }
            },
            ai_provider=_RepairAI(err),
            template_renderer=JinjaTemplateRenderer(settings.TEMPLATES_DIR),
            prompt_template="prompts/v2_candidate_repair.j2",
            phase_deadline=time.monotonic() + 60,
            call_budget=budget,
            candidate_revision_uuid="req50-provider",
        )
    assert exc.value.provider_error_code
    row = _single_paid_repair_row(budget)
    assert row["error_code"]
    assert row["terminal_decision"] == "fail_closed"
    assert float(row["finished_at"]) > 0
    assert int(row["attempt_number"]) >= 1
    _restore_round_trip(budget.snapshot(), budget.attempts_snapshot())


def test_repair_extraction_failure_persists_attempt() -> None:
    budget = CandidateCallBudget.create()
    assert budget.approve("business_components")[0]
    with pytest.raises(CandidateStageError) as exc:
        repair_ai_batch(
            request_id=50,
            batch_stage="business_components",
            policy=repair_policy(),
            batch=_original_batch(),
            diagnostics=(
                canonical_json(
                    {
                        "code": "missing_component_hook",
                        "path": HOME_PATH,
                        "related_ids": ["COMP-HOME"],
                    }
                ),
            ),
            canonical_bindings={
                "business_component_plan": {
                    "components": [
                        {"component_id": "COMP-HOME", "purpose": "home"},
                        {"component_id": "COMP-BOOK", "purpose": "book"},
                    ]
                }
            },
            ai_provider=_RepairAI(""),
            template_renderer=JinjaTemplateRenderer(settings.TEMPLATES_DIR),
            prompt_template="prompts/v2_candidate_repair.j2",
            phase_deadline=time.monotonic() + 60,
            call_budget=budget,
            candidate_revision_uuid="req50-extract",
        )
    assert "repair" in str(exc.value.provider_error_code).lower() or (
        exc.value.provider_error_code
    )
    row = _single_paid_repair_row(budget)
    assert row["error_code"]
    assert row["terminal_decision"] == "fail_closed"
    assert row["error_type"] == "local_validation"
    assert row["raw_payload_sha256"]
    _assert_required_fields(row, expect_finished=True)


def test_repair_output_invalid_persists_attempt() -> None:
    # Valid JSON envelope that fails the repair contract (missing source).
    payload = {
        "schema_version": "1.0",
        "batch_kind": "business_components",
        "files": [
            {
                "path": HOME_PATH,
                "file_kind": "business_component",
                "owner_contract_ids": ["COMP-HOME"],
            }
        ],
    }
    budget = CandidateCallBudget.create()
    assert budget.approve("business_components")[0]
    with pytest.raises(CandidateStageError) as exc:
        repair_ai_batch(
            request_id=50,
            batch_stage="business_components",
            policy=repair_policy(),
            batch=_original_batch(),
            diagnostics=(
                canonical_json(
                    {
                        "code": "missing_component_hook",
                        "path": HOME_PATH,
                        "related_ids": ["COMP-HOME"],
                    }
                ),
            ),
            canonical_bindings={
                "business_component_plan": {
                    "components": [
                        {"component_id": "COMP-HOME", "purpose": "home"},
                        {"component_id": "COMP-BOOK", "purpose": "book"},
                    ]
                }
            },
            ai_provider=_RepairAI(json.dumps(payload)),
            template_renderer=JinjaTemplateRenderer(settings.TEMPLATES_DIR),
            prompt_template="prompts/v2_candidate_repair.j2",
            phase_deadline=time.monotonic() + 60,
            call_budget=budget,
            candidate_revision_uuid="req50-invalid",
        )
    assert exc.value.provider_error_code
    row = _single_paid_repair_row(budget)
    assert row["error_code"]
    assert row["terminal_decision"] == "fail_closed"
    assert row["error_type"] == "local_validation"
    _assert_required_fields(row, expect_finished=True)


def test_repair_ownership_violation_persists_attempt() -> None:
    payload = _canonical_repair_payload(
        files=[
            {
                "path": BOOK_PATH,
                "file_kind": "business_component",
                "owner_contract_ids": ["COMP-BOOK"],
                "source": (
                    "export function CompBookComponent() {\n"
                    '  return <div data-bmv-component-id="COMP-BOOK">Book</div>;\n'
                    "}"
                ),
            }
        ]
    )
    budget = CandidateCallBudget.create()
    assert budget.approve("business_components")[0]
    with pytest.raises(CandidateStageError) as exc:
        repair_ai_batch(
            request_id=50,
            batch_stage="business_components",
            policy=repair_policy(),
            batch=_original_batch(),
            diagnostics=(
                canonical_json(
                    {
                        "code": "missing_component_hook",
                        "path": HOME_PATH,
                        "related_ids": ["COMP-HOME"],
                    }
                ),
            ),
            canonical_bindings={
                "business_component_plan": {
                    "components": [
                        {"component_id": "COMP-HOME", "purpose": "home"},
                        {"component_id": "COMP-BOOK", "purpose": "book"},
                    ]
                }
            },
            ai_provider=_RepairAI(json.dumps(payload)),
            template_renderer=JinjaTemplateRenderer(settings.TEMPLATES_DIR),
            prompt_template="prompts/v2_candidate_repair.j2",
            phase_deadline=time.monotonic() + 60,
            call_budget=budget,
            candidate_revision_uuid="req50-ownership",
        )
    assert exc.value.provider_error_code == "candidate_repair_ownership_violation"
    row = _single_paid_repair_row(budget)
    assert row["error_code"] == "candidate_repair_ownership_violation"
    assert row["terminal_decision"] == "fail_closed"
    _assert_required_fields(row, expect_finished=True)


def test_repair_merge_failure_persists_attempt(monkeypatch) -> None:
    import app.application.candidate_generation.repair_scope as repair_scope

    original = repair_scope.merge_repaired_files

    def _boom(*, original, repaired):
        raise ValueError("repair introduced unknown paths: ['ghost.tsx']")

    monkeypatch.setattr(repair_scope, "merge_repaired_files", _boom)
    budget = CandidateCallBudget.create()
    assert budget.approve("business_components")[0]
    with pytest.raises(CandidateStageError) as exc:
        repair_ai_batch(
            request_id=50,
            batch_stage="business_components",
            policy=repair_policy(),
            batch=_original_batch(),
            diagnostics=(
                canonical_json(
                    {
                        "code": "missing_component_hook",
                        "path": HOME_PATH,
                        "related_ids": ["COMP-HOME"],
                    }
                ),
            ),
            canonical_bindings={
                "business_component_plan": {
                    "components": [
                        {"component_id": "COMP-HOME", "purpose": "home"},
                        {"component_id": "COMP-BOOK", "purpose": "book"},
                    ]
                }
            },
            ai_provider=_RepairAI(json.dumps(_canonical_repair_payload())),
            template_renderer=JinjaTemplateRenderer(settings.TEMPLATES_DIR),
            prompt_template="prompts/v2_candidate_repair.j2",
            phase_deadline=time.monotonic() + 60,
            call_budget=budget,
            candidate_revision_uuid="req50-merge",
        )
    monkeypatch.setattr(repair_scope, "merge_repaired_files", original)
    assert exc.value.provider_error_code == "candidate_repair_ownership_violation"
    row = _single_paid_repair_row(budget)
    assert row["error_code"] == "candidate_repair_ownership_violation"
    assert "unknown paths" in row["error_message_redacted"]
    _assert_required_fields(row, expect_finished=True)


# ---------------------------------------------------------------------------
# orchestrator progress labelling
# ---------------------------------------------------------------------------


class _FixtureAI:
    name = "local-fixture"

    def ask_chat(self, *_args, **_kwargs) -> str:
        raise AssertionError("fixture must not call chat")

    def ask_vision(self, *_args, **_kwargs) -> str:
        raise AssertionError("fixture must not call vision")

    def is_available(self) -> bool:
        return True


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _request(request_id: int) -> Request:
    return Request(
        id=request_id,
        business_name="LocalConnect Pro Scheduler",
        industry="Professional Services",
        business_description="Customers book services online.",
        target_customers="Local customers",
        main_problem="Booking is manual.",
        desired_outcome="Customers can book online.",
        project_type="new",
        email="owner@example.com",
        mvp_blueprint="A five-page booking flow.",
        concept_name="LocalConnect Pro Scheduler",
        preview_summary="A booking workflow.",
        preview_features=json.dumps(["Service list"]),
        created_at=datetime(2026, 7, 28, 12, 0, 0),
    )


@pytest.mark.parametrize(
    ("status", "forbidden_snippets"),
    [
        (
            "candidate_failed",
            ("passed static validation", "Phase 4 is disabled"),
        ),
        (
            "candidate_contract_failed",
            ("passed static validation", "Phase 4 is disabled"),
        ),
        (
            "totally_unknown_status",
            ("passed static validation", "Phase 4 is disabled"),
        ),
    ],
)
def test_orchestrator_never_labels_failures_as_static_pass(
    monkeypatch,
    status: str,
    forbidden_snippets: tuple[str, ...],
) -> None:
    db = _db()
    emits: list[dict] = []
    try:
        req = _request(5100 + hash(status) % 1000)
        req.status = "reviewing"
        db.add(req)
        db.commit()
        expected = {
            "preview_contract": {
                "generator_version": "v2",
                "status": status,
            }
        }
        monkeypatch.setattr(settings, "PREVIEW_GENERATOR_V2", True)
        monkeypatch.setattr(
            full_orchestrator.blueprint,
            "generate_mvp_blueprint",
            lambda *_args, **_kwargs: None,
        )
        monkeypatch.setattr(
            full_orchestrator,
            "generate_preview_app",
            lambda *_args, **_kwargs: expected,
        )

        def _capture(_db, request_id, stage, message, pct, detail=None, **_kwargs):
            emits.append(
                {
                    "stage": stage,
                    "message": message,
                    "detail": detail or "",
                    "pct": pct,
                }
            )

        monkeypatch.setattr(full_orchestrator, "_emit", _capture)
        result = full_orchestrator.GenerationPipeline(
            _FixtureAI(),
            object(),
        )._run_inner(db, req.id)
        db.refresh(req)
        assert result is expected
        terminal = [item for item in emits if item["pct"] == 100]
        assert terminal
        label = terminal[-1]["message"]
        detail = terminal[-1]["detail"]
        blob = f"{label}\n{detail}"
        for snippet in forbidden_snippets:
            assert snippet not in blob
        if status in {"candidate_failed", "candidate_contract_failed"}:
            assert req.status == "failed"
            assert "generation failed" in label.lower()
            assert "Phase 4 was not reached" in detail
            assert "passed static validation" not in label
        else:
            assert "unrecognized" in label.lower()
            assert "not a pass" in detail.lower()
            assert req.status != "failed"
    finally:
        db.close()


def test_orchestrator_build_pending_still_reports_static_pass(monkeypatch) -> None:
    db = _db()
    emits: list[dict] = []
    try:
        req = _request(5199)
        req.status = "reviewing"
        db.add(req)
        db.commit()
        expected = {
            "preview_contract": {
                "generator_version": "v2",
                "status": "candidate_build_pending",
            }
        }
        monkeypatch.setattr(settings, "PREVIEW_GENERATOR_V2", True)
        monkeypatch.setattr(
            full_orchestrator.blueprint,
            "generate_mvp_blueprint",
            lambda *_args, **_kwargs: None,
        )
        monkeypatch.setattr(
            full_orchestrator,
            "generate_preview_app",
            lambda *_args, **_kwargs: expected,
        )
        monkeypatch.setattr(
            full_orchestrator,
            "_emit",
            lambda _db, _rid, stage, message, pct, detail=None, **_k: emits.append(
                {"stage": stage, "message": message, "detail": detail or "", "pct": pct}
            ),
        )
        full_orchestrator.GenerationPipeline(_FixtureAI(), object())._run_inner(
            db, req.id
        )
        db.refresh(req)
        terminal = [item for item in emits if item["pct"] == 100][-1]
        assert "passed static validation" in terminal["message"]
        assert req.status != "failed"
    finally:
        db.close()
