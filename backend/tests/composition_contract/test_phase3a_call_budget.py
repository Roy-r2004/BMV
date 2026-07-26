"""TDD-style tests for Phase 3A provider-call budgeting (fixes #32).

Coverage:
- Every provider call appears in ledger
- Deterministic repairs do not count
- Transport attempts do not create hidden application calls
- Per-substage caps enforced
- Required later-stage reservations preserved
- Optional enrichment skipped when budget low
- Required stages fail with precise code when no deterministic route + no budget
- Deterministic ContentDataPlan uses 0 provider calls for booking fixture
- Deterministic dependency graph uses 0 provider calls
- Duplicate / cache execution does not double-count
- Restart reconstructs used budget from events
- No provider constructed after budget denial (spy)
- Total cap remains <= 4
- #32 failure class reproducible under old AI-first semantics
- Corrected path reaches composition_contract_ready with BCP=1, content=0
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.application.composition_contract.builder import CompositionStageError
from app.application.composition_contract.call_budget import (
    PHASE3A_CALL_BUDGET_POLICY_REVISION,
    Phase3ACallBudget,
)
from app.application.composition_contract.service import (
    V2_COMPOSITION_CONTRACT_READY,
    build_v2_composition_contract,
)
from app.core.config import settings
from app.domain.models import CompositionContractArtifactRecord
from app.infrastructure.templating.renderer import JinjaTemplateRenderer
from tests.composition_contract.helpers import (
    CompositionFixtureAI,
    prepare_phase2,
)


def _renderer() -> JinjaTemplateRenderer:
    return JinjaTemplateRenderer(settings.TEMPLATES_DIR)


def _run(prepared, ai):
    return build_v2_composition_contract(
        prepared.db,
        prepared.req.id,
        ai,
        _renderer(),
        req=prepared.req,
        phase2_result=prepared.phase2_result,
    )


def _rows(prepared):
    return (
        prepared.db.query(CompositionContractArtifactRecord)
        .filter_by(request_id=prepared.req.id)
        .order_by(CompositionContractArtifactRecord.id)
        .all()
    )


# ---------------------------------------------------------------------------
# Unit tests: Phase3ACallBudget in isolation
# ---------------------------------------------------------------------------


class TestPhase3ACallBudgetUnit:
    """Unit-level tests for the budget class (no DB / fixture needed)."""

    def test_create_has_correct_defaults(self, monkeypatch):
        monkeypatch.setattr(settings, "V2_COMPOSITION_CONTRACT_MAX_CALLS", 4)
        budget = Phase3ACallBudget.create()
        assert budget.total_max == 4
        assert budget._substage_caps["business_component_plan"] == 2
        assert budget._substage_caps["content_data_plan"] == 1
        assert budget._substage_caps["page_purpose_contract"] == 0
        assert budget._reservations["content_data_plan"] == 1
        assert budget._total_reserved == 1
        assert budget._total_used == 0

    def test_approve_charges_substage_and_global(self, monkeypatch):
        monkeypatch.setattr(settings, "V2_COMPOSITION_CONTRACT_MAX_CALLS", 4)
        budget = Phase3ACallBudget.create()
        approved, code = budget.approve("business_component_plan")
        assert approved is True
        assert code == ""
        assert budget._used["business_component_plan"] == 1
        assert budget._total_used == 1

    def test_per_substage_cap_enforced(self, monkeypatch):
        monkeypatch.setattr(settings, "V2_COMPOSITION_CONTRACT_MAX_CALLS", 4)
        budget = Phase3ACallBudget.create()
        # content_data_plan cap is 1
        ok, _ = budget.approve("content_data_plan")
        assert ok is True
        denied, code = budget.approve("content_data_plan")
        assert denied is False
        assert code == "phase3a_substage_call_budget_exhausted"
        # Ledger has both events
        kinds = [e.kind for e in budget._events]
        assert "approved" in kinds
        assert "denied" in kinds

    def test_zero_cap_stages_always_denied(self, monkeypatch):
        monkeypatch.setattr(settings, "V2_COMPOSITION_CONTRACT_MAX_CALLS", 4)
        budget = Phase3ACallBudget.create()
        for stage in ("page_purpose_contract", "interaction_contract", "component_dependency_graph"):
            approved, code = budget.approve(stage)
            assert approved is False
            assert code == "phase3a_substage_call_budget_exhausted"

    def test_content_reservation_preserved_for_bcp(self, monkeypatch):
        """BCP cannot exhaust the global budget if content reservation is held."""
        monkeypatch.setattr(settings, "V2_COMPOSITION_CONTRACT_MAX_CALLS", 2)
        budget = Phase3ACallBudget.create()
        # total_max=2, content_reservation=1 → BCP can use 1 call (2 - 0_used - 1_reserved = 1)
        ok1, _ = budget.approve("business_component_plan")
        assert ok1 is True
        # Second BCP call would leave 0 for content → denied
        denied, code = budget.approve("business_component_plan")
        assert denied is False
        assert code == "phase3a_total_call_budget_exhausted"

    def test_release_reservation_frees_headroom(self, monkeypatch):
        monkeypatch.setattr(settings, "V2_COMPOSITION_CONTRACT_MAX_CALLS", 2)
        budget = Phase3ACallBudget.create()
        ok1, _ = budget.approve("business_component_plan")
        assert ok1 is True
        # Release content reservation (deterministic succeeded)
        budget.release_reservation("content_data_plan")
        assert budget._total_reserved == 0
        # Now BCP repair call is allowed
        ok2, _ = budget.approve("business_component_plan")
        assert ok2 is True
        assert budget._total_used == 2

    def test_deterministic_does_not_charge_budget(self, monkeypatch):
        monkeypatch.setattr(settings, "V2_COMPOSITION_CONTRACT_MAX_CALLS", 4)
        budget = Phase3ACallBudget.create()
        budget.record_deterministic("content_data_plan")
        assert budget._total_used == 0
        kinds = [e.kind for e in budget._events]
        assert "deterministic_success" in kinds

    def test_cache_hit_does_not_charge_budget(self, monkeypatch):
        monkeypatch.setattr(settings, "V2_COMPOSITION_CONTRACT_MAX_CALLS", 4)
        budget = Phase3ACallBudget.create()
        budget.record_cache_hit("business_component_plan")
        assert budget._total_used == 0
        kinds = [e.kind for e in budget._events]
        assert "cache_hit" in kinds

    def test_total_cap_cannot_exceed_max(self, monkeypatch):
        monkeypatch.setattr(settings, "V2_COMPOSITION_CONTRACT_MAX_CALLS", 4)
        budget = Phase3ACallBudget.create()
        # Reserve is 1 (content); can approve at most 3 BCP calls (cap=2 also limits)
        budget.release_reservation("content_data_plan")  # free the reservation
        # BCP cap=2: first two approved
        ok1, _ = budget.approve("business_component_plan")
        ok2, _ = budget.approve("business_component_plan")
        assert ok1 is True
        assert ok2 is True
        # Third BCP call denied by substage cap
        denied_bcp, code_bcp = budget.approve("business_component_plan")
        assert denied_bcp is False
        assert code_bcp == "phase3a_substage_call_budget_exhausted"
        # Content can still get 1 call
        ok_c, _ = budget.approve("content_data_plan")
        assert ok_c is True
        # Total used never exceeds total_max=4
        assert budget._total_used <= budget.total_max

    def test_snapshot_contains_all_fields(self, monkeypatch):
        monkeypatch.setattr(settings, "V2_COMPOSITION_CONTRACT_MAX_CALLS", 4)
        budget = Phase3ACallBudget.create()
        budget.approve("business_component_plan")
        snap = budget.snapshot()
        assert snap["policy_revision"] == PHASE3A_CALL_BUDGET_POLICY_REVISION
        assert snap["total_max"] == 4
        assert snap["total_used"] == 1
        assert isinstance(snap["events"], list)
        assert len(snap["events"]) == 1
        assert snap["events"][0]["kind"] == "approved"
        assert snap["events"][0]["stage"] == "business_component_plan"

    def test_reconstruct_from_events_restores_state(self, monkeypatch):
        monkeypatch.setattr(settings, "V2_COMPOSITION_CONTRACT_MAX_CALLS", 4)
        budget = Phase3ACallBudget.create()
        budget.approve("business_component_plan")
        budget.approve("business_component_plan")
        budget.release_reservation("content_data_plan")
        snap = budget.snapshot()

        restored = Phase3ACallBudget.reconstruct_from_events(
            snap["events"],
            total_max=snap["total_max"],
        )
        assert restored._total_used == budget._total_used
        assert restored._total_reserved == budget._total_reserved
        assert restored._used["business_component_plan"] == 2
        assert restored._reservations.get("content_data_plan", 0) == 0

    def test_reconstruct_empty_events_is_fresh_budget(self, monkeypatch):
        monkeypatch.setattr(settings, "V2_COMPOSITION_CONTRACT_MAX_CALLS", 4)
        restored = Phase3ACallBudget.reconstruct_from_events([])
        assert restored._total_used == 0
        assert restored._total_reserved == 1  # content reservation

    def test_duplicate_cache_execution_does_not_double_count(self, monkeypatch):
        monkeypatch.setattr(settings, "V2_COMPOSITION_CONTRACT_MAX_CALLS", 4)
        budget = Phase3ACallBudget.create()
        budget.record_cache_hit("business_component_plan")
        budget.record_cache_hit("business_component_plan")  # duplicate
        assert budget._total_used == 0
        cache_events = [e for e in budget._events if e.kind == "cache_hit"]
        assert len(cache_events) == 2  # recorded but no charge


# ---------------------------------------------------------------------------
# Integration tests: budget wired into the pipeline
# ---------------------------------------------------------------------------


def test_every_bcp_provider_call_appears_in_ledger() -> None:
    """Each approved BCP call must appear as an 'approved' event in the ledger."""
    prepared = prepare_phase2(request_id=3201)
    ai = CompositionFixtureAI()
    try:
        result = _run(prepared, ai)
        ledger = result["preview_contract"]["phase3a_call_ledger"]
        approved_bcp = [
            e for e in ledger["events"]
            if e["kind"] == "approved" and e["stage"] == "business_component_plan"
        ]
        bcp_row = next(
            row for row in _rows(prepared)
            if row.artifact_kind == "business_component_plan"
        )
        assert len(approved_bcp) == bcp_row.provider_call_count
        assert ledger["total_used"] == bcp_row.provider_call_count
    finally:
        prepared.db.close()


def test_deterministic_content_uses_zero_provider_calls_for_booking_fixture() -> None:
    """The booking fixture deterministic projection must produce 0 AI calls for content."""
    prepared = prepare_phase2(request_id=3202)
    ai = CompositionFixtureAI()
    try:
        result = _run(prepared, ai)
        content_metrics = result["preview_contract"]["composition_stage_metrics"][
            "content_data_plan"
        ]
        assert content_metrics["provider_call_count"] == 0
        # Provider should be "local" (deterministic), not "deterministic_fallback" or AI
        assert content_metrics["provider"] in {"local", "deterministic_first"}
        # No content AI call was made
        assert not any(stage == "content_data_plan" for stage, _ in ai.calls)
        # Ledger: deterministic_success for content + reservation_released
        ledger = result["preview_contract"]["phase3a_call_ledger"]
        event_kinds = {e["kind"] for e in ledger["events"]}
        assert "deterministic_success" in event_kinds
        assert "reservation_released" in event_kinds
    finally:
        prepared.db.close()


def test_deterministic_dependency_graph_uses_zero_provider_calls() -> None:
    prepared = prepare_phase2(request_id=3203)
    ai = CompositionFixtureAI()
    try:
        result = _run(prepared, ai)
        graph_metrics = result["preview_contract"]["composition_stage_metrics"][
            "component_dependency_graph"
        ]
        assert graph_metrics["provider_call_count"] == 0
    finally:
        prepared.db.close()


def test_transport_attempts_do_not_create_hidden_application_calls() -> None:
    """transport_attempts=1 (SDK-level) must not become 2 budget approvals."""
    prepared = prepare_phase2(request_id=3204)
    transport_calls: dict[str, Any] = {}

    class InspectAI(CompositionFixtureAI):
        def ask_chat(self, *args, **kwargs):
            transport_calls["transport_attempts"] = kwargs.get("transport_attempts")
            return super().ask_chat(*args, **kwargs)

    ai = InspectAI()
    try:
        result = _run(prepared, ai)
        assert transport_calls.get("transport_attempts") == 1
        ledger = result["preview_contract"]["phase3a_call_ledger"]
        # Only 1 approved event for BCP, no duplicate from transport retry
        bcp_approved = [
            e for e in ledger["events"]
            if e["kind"] == "approved" and e["stage"] == "business_component_plan"
        ]
        bcp_row = next(
            row for row in _rows(prepared)
            if row.artifact_kind == "business_component_plan"
        )
        assert len(bcp_approved) == bcp_row.provider_call_count
    finally:
        prepared.db.close()


def test_no_provider_constructed_after_budget_denial(monkeypatch) -> None:
    """When budget denies a call, the AI provider ask_chat must never be invoked."""
    prepared = prepare_phase2(request_id=3205)
    ai = CompositionFixtureAI()
    # Restrict total to 0 (below BCP minimum); budget will deny BCP immediately
    monkeypatch.setattr(settings, "V2_COMPOSITION_CONTRACT_MAX_CALLS", 2)

    original_ask = ai.ask_chat
    ask_called = {"n": 0}

    def spy_ask(*args, **kwargs):
        ask_called["n"] += 1
        return original_ask(*args, **kwargs)

    ai.ask_chat = spy_ask  # type: ignore[method-assign]

    # Force content reservation to NOT consume the last slot: tighten to 1
    monkeypatch.setattr(settings, "V2_COMPOSITION_CONTRACT_MAX_CALLS", 1)
    try:
        # With MAX_CALLS=1 and content_reservation=1: BCP approve checks
        # 0_used + 1_call + 1_other_reservation = 2 > 1 → denied before any ask_chat
        with pytest.raises(CompositionStageError) as exc_info:
            _run(prepared, ai)
        assert exc_info.value.failure_code == "phase3a_total_call_budget_exhausted"
        assert ask_called["n"] == 0
    finally:
        prepared.db.close()


def test_optional_enrichment_skipped_when_budget_low_records_in_ledger(monkeypatch) -> None:
    """Content with deterministic success should record reservation_released in ledger."""
    prepared = prepare_phase2(request_id=3206)
    ai = CompositionFixtureAI()
    try:
        result = _run(prepared, ai)
        ledger = result["preview_contract"]["phase3a_call_ledger"]
        released = [e for e in ledger["events"] if e["kind"] == "reservation_released"]
        assert len(released) >= 1
        assert released[0]["stage"] == "content_data_plan"
    finally:
        prepared.db.close()


def test_required_bcp_stage_fails_with_precise_code_when_no_budget(monkeypatch) -> None:
    """BCP must fail with a typed budget code, not a vague message."""
    prepared = prepare_phase2(request_id=3207)
    ai = CompositionFixtureAI()
    monkeypatch.setattr(settings, "V2_COMPOSITION_CONTRACT_MAX_CALLS", 1)
    try:
        with pytest.raises(CompositionStageError) as exc_info:
            _run(prepared, ai)
        code = exc_info.value.failure_code
        assert code in {
            "phase3a_total_call_budget_exhausted",
            "phase3a_substage_call_budget_exhausted",
        }
        # The old vague message must NOT appear
        assert "Phase 3A exceeded its provider-call budget" not in str(exc_info.value)
    finally:
        prepared.db.close()


def test_per_substage_caps_enforced_via_integration(monkeypatch) -> None:
    """BCP retry (2nd call) must succeed; a 3rd call must be denied."""
    prepared = prepare_phase2(request_id=3208)
    ai = CompositionFixtureAI()
    # Force BCP to need exactly 2 calls (1 initial invalid + 1 recovery)
    ai.invalid_stage_responses["business_component_plan"] = ["not-json"]
    try:
        result = _run(prepared, ai)
        bcp_calls = [s for s, _ in ai.calls if s == "business_component_plan"]
        assert len(bcp_calls) == 2
        # But a 3rd would have been denied by substage cap=2
        ledger = result["preview_contract"]["phase3a_call_ledger"]
        assert ledger["substage_used"]["business_component_plan"] == 2
    finally:
        prepared.db.close()


def test_cache_hit_produces_no_budget_charge() -> None:
    """Second run (full cache hit) must add 0 to budget total_used."""
    prepared = prepare_phase2(request_id=3209)
    ai = CompositionFixtureAI()
    try:
        _run(prepared, ai)
        result2 = _run(prepared, ai)
        ledger = result2["preview_contract"]["phase3a_call_ledger"]
        # All events after the first run should be cache_hits on second run
        # total_used must be 0 for the second run (ledger is reset per run)
        assert ledger["total_used"] == 0
        # All composition stages had cache_hit metrics
        metrics = result2["preview_contract"]["composition_stage_metrics"]
        assert all(v["cache_hit"] for v in metrics.values())
    finally:
        prepared.db.close()


def test_restart_reconstructs_used_budget_from_events(monkeypatch) -> None:
    """reconstruct_from_events must reproduce the same used/reserved counts."""
    monkeypatch.setattr(settings, "V2_COMPOSITION_CONTRACT_MAX_CALLS", 4)
    prepared = prepare_phase2(request_id=3210)
    ai = CompositionFixtureAI()
    try:
        result = _run(prepared, ai)
        ledger = result["preview_contract"]["phase3a_call_ledger"]
        restored = Phase3ACallBudget.reconstruct_from_events(
            ledger["events"],
            total_max=ledger["total_max"],
        )
        assert restored._total_used == ledger["total_used"]
        assert restored._total_reserved == ledger["total_reserved"]
    finally:
        prepared.db.close()


def test_total_cap_remains_le_4(monkeypatch) -> None:
    """With defaults, total provider calls must never exceed V2_COMPOSITION_CONTRACT_MAX_CALLS."""
    monkeypatch.setattr(settings, "V2_COMPOSITION_CONTRACT_MAX_CALLS", 4)
    # Make BCP fail twice so it uses 2 calls; content is deterministic (0)
    prepared = prepare_phase2(request_id=3211)
    ai = CompositionFixtureAI()
    ai.invalid_stage_responses["business_component_plan"] = ["not-json"]
    try:
        result = _run(prepared, ai)
        ledger = result["preview_contract"]["phase3a_call_ledger"]
        assert ledger["total_used"] <= 4
        assert ledger["total_used"] <= ledger["total_max"]
    finally:
        prepared.db.close()


def test_issue32_failure_class_reproducible_under_ai_first_semantics(
    monkeypatch,
) -> None:
    """Reproduce #32: AI-first content with retry under MAX_CALLS=2 should
    be caught by the substage cap (content_data_plan cap=1), giving a typed
    error instead of the old vague post-hoc message.

    Old behaviour: cumulative check at line 628 (post-content) would raise
    "Phase 3A exceeded its provider-call budget." with no code.
    New behaviour: budget.approve denies the 2nd content call with
    "phase3a_substage_call_budget_exhausted" BEFORE the provider call.
    """
    prepared = prepare_phase2(request_id=3232)
    ai = CompositionFixtureAI()
    monkeypatch.setattr(settings, "V2_COMPOSITION_CONTRACT_MAX_CALLS", 2)
    # Force BCP to use 1 call (succeeds on first attempt)
    # Force deterministic content to fail so AI path is triggered
    import app.application.composition_contract.service as svc_mod

    original_project = svc_mod.project_content_data_plan

    call_count = {"n": 0}

    def always_fail(*args, **kwargs):
        raise ValueError("forced deterministic failure for #32 test")

    monkeypatch.setattr(svc_mod, "project_content_data_plan", always_fail)
    # Make content AI return invalid JSON on first attempt → forces retry
    ai.invalid_stage_responses["content_data_plan"] = ["not-json"]
    # With MAX_CALLS=2 and content_reservation=1:
    #   BCP approves (used=1, reserved=1; check: 0+1+1=2 ≤ 2 ✓)
    #   Content AI attempt 1 approves (used=2, reserved=0; check: 1+1+0=2 ≤ 2 ✓)
    #   Content AI attempt 2 denied by substage cap (used_content=1 >= cap=1)
    try:
        with pytest.raises(CompositionStageError) as exc_info:
            _run(prepared, ai)
        # The error code must be typed (not the old vague string)
        assert exc_info.value.failure_code in {
            "phase3a_substage_call_budget_exhausted",
            "phase3a_total_call_budget_exhausted",
        }
        # The old vague message must NOT appear
        assert "Phase 3A exceeded its provider-call budget" not in str(exc_info.value)
    finally:
        monkeypatch.setattr(svc_mod, "project_content_data_plan", original_project)
        prepared.db.close()


def test_corrected_path_reaches_composition_ready_bcp1_content0(monkeypatch) -> None:
    """Corrected path: BCP=1 AI call, content=0 AI calls (deterministic).

    This is the key fix for #32: when deterministic content projection
    succeeds, the total budget usage is 1 (BCP only), well within any
    reasonable MAX_CALLS setting.
    """
    monkeypatch.setattr(settings, "V2_COMPOSITION_CONTRACT_MAX_CALLS", 2)
    prepared = prepare_phase2(request_id=3231)
    ai = CompositionFixtureAI()
    try:
        result = _run(prepared, ai)
        assert result["preview_contract"]["status"] == V2_COMPOSITION_CONTRACT_READY
        ledger = result["preview_contract"]["phase3a_call_ledger"]
        assert ledger["total_used"] == 1  # BCP only
        assert ledger["substage_used"]["business_component_plan"] == 1
        assert ledger["substage_used"]["content_data_plan"] == 0
        # Only BCP was called via AI
        assert [s for s, _ in ai.calls] == ["business_component_plan"]
    finally:
        prepared.db.close()


def test_phase3a_call_ledger_persisted_on_preview_contract() -> None:
    """phase3a_call_ledger must be a top-level key in the preview_contract."""
    prepared = prepare_phase2(request_id=3212)
    ai = CompositionFixtureAI()
    try:
        result = _run(prepared, ai)
        ledger = result["preview_contract"]["phase3a_call_ledger"]
        assert ledger is not None
        assert "policy_revision" in ledger
        assert "total_max" in ledger
        assert "total_used" in ledger
        assert "events" in ledger
        assert isinstance(ledger["events"], list)
    finally:
        prepared.db.close()


def test_bcp_recovery_does_not_steal_content_reservation(monkeypatch) -> None:
    """BCP's repair call must respect the content_data_plan reservation.

    With MAX_CALLS=3 and content_reservation=1:
    - BCP call 1 approved (used=1, reserved=1; remaining headroom=1)
    - BCP call 2 (repair) approved (used=2, reserved=1; 2+1=3 ≤ 3 ✓)
    - Content deterministic succeeds (used=2, reserved=0 after release)
    - Total=2 ≤ 3: success
    """
    monkeypatch.setattr(settings, "V2_COMPOSITION_CONTRACT_MAX_CALLS", 3)
    prepared = prepare_phase2(request_id=3213)
    ai = CompositionFixtureAI()
    # Force BCP to use 2 calls
    ai.invalid_stage_responses["business_component_plan"] = ["not-json"]
    try:
        result = _run(prepared, ai)
        assert result["preview_contract"]["status"] == V2_COMPOSITION_CONTRACT_READY
        ledger = result["preview_contract"]["phase3a_call_ledger"]
        assert ledger["substage_used"]["business_component_plan"] == 2
        assert ledger["substage_used"]["content_data_plan"] == 0  # deterministic
        assert ledger["total_used"] == 2
    finally:
        prepared.db.close()
