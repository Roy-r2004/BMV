"""Focused reliability tests for business_component_plan budgets."""
from __future__ import annotations

import json
import time
from typing import Any

import pytest

from app.application.composition_contract.builder import CompositionStageError
from app.application.composition_contract.component_plan_budgets import (
    resolve_business_component_plan_budgets,
)
from app.application.composition_contract.component_plan_prompt import (
    project_business_component_plan_prompt,
)
from app.application.composition_contract.deadline import StageDeadline
from app.application.composition_contract.normalize import (
    normalize_business_component_plan,
)
from app.application.composition_contract.service import (
    build_v2_composition_contract,
)
from app.application.composition_contract.context import load_composition_context
from app.application.composition_contract.projections import project_page_purpose
from app.core.config import settings
from app.infrastructure.templating.renderer import JinjaTemplateRenderer
from tests.composition_contract.helpers import (
    CompositionFixtureAI,
    prepare_phase2,
)


def _renderer() -> JinjaTemplateRenderer:
    return JinjaTemplateRenderer(settings.TEMPLATES_DIR)


def test_stage_deadline_created_once_and_per_call_below_wall() -> None:
    budgets = resolve_business_component_plan_budgets()
    deadline = StageDeadline.start(
        "business_component_plan",
        budgets.stage_wall_seconds,
    )
    assert deadline.wall_seconds == budgets.stage_wall_seconds
    call_timeout = deadline.call_timeout(
        per_call_timeout=budgets.per_call_timeout_seconds,
        min_call_budget=budgets.min_call_budget_seconds,
    )
    assert call_timeout is not None
    assert call_timeout <= budgets.per_call_timeout_seconds
    assert call_timeout <= budgets.stage_wall_seconds
    assert budgets.per_call_timeout_seconds <= budgets.stage_wall_seconds


def test_nested_retries_cannot_exceed_deadline() -> None:
    deadline = StageDeadline.start("business_component_plan", 0.05)
    time.sleep(0.06)
    assert deadline.exhausted()
    assert (
        deadline.call_timeout(per_call_timeout=180, min_call_budget=0.01)
        is None
    )


def test_prompt_projection_excludes_tier_2_3_and_full_appspec() -> None:
    prepared = prepare_phase2(request_id=2401)
    try:
        context = load_composition_context(
            prepared.db,
            request_id=prepared.req.id,
            phase2_result=prepared.phase2_result,
        )
        page_purpose = project_page_purpose(context)
        from app.domain.schemas.composition_contract import (
            CompositionArtifactRef,
        )

        ref = CompositionArtifactRef(
            id=1,
            artifact_kind="page_purpose_contract",
            schema_version="1.0",
            sha256="a" * 64,
        )
        projection = project_business_component_plan_prompt(
            context,
            page_purpose=page_purpose,
            page_purpose_ref=ref,
        )
        assert projection.stage_input["prompt_projection_meta"][
            "includes_tier_2_3_pages"
        ] is False
        assert "full_raw_app_spec" in projection.omitted_sections
        tier1_pages = set(context.tier_1.references.page_ids)
        projected_pages = {
            page["id"]
            for page in projection.stage_input["canonical_app_spec"]["pages"]
        }
        assert projected_pages == tier1_pages
        assert set(projection.skeleton["required_page_ids"]) == tier1_pages
        full = context.app_spec.model_dump(mode="json")
        assert len(projection.stage_input_json) < len(json.dumps(full))
    finally:
        prepared.db.close()


def test_deterministic_skeleton_contains_every_tier1_page() -> None:
    prepared = prepare_phase2(request_id=2402)
    try:
        context = load_composition_context(
            prepared.db,
            request_id=prepared.req.id,
            phase2_result=prepared.phase2_result,
        )
        page_purpose = project_page_purpose(context)
        from app.domain.schemas.composition_contract import (
            CompositionArtifactRef,
        )

        ref = CompositionArtifactRef(
            id=1,
            artifact_kind="page_purpose_contract",
            schema_version="1.0",
            sha256="b" * 64,
        )
        projection = project_business_component_plan_prompt(
            context,
            page_purpose=page_purpose,
            page_purpose_ref=ref,
        )
        expected = [page.page_id for page in page_purpose.pages]
        assert projection.skeleton["required_page_ids"] == expected
        assert [
            page["page_id"] for page in projection.skeleton["pages"]
        ] == expected
    finally:
        prepared.db.close()


def test_normalize_prevents_removing_mandatory_actions() -> None:
    prepared = prepare_phase2(request_id=2403)
    try:
        context = load_composition_context(
            prepared.db,
            request_id=prepared.req.id,
            phase2_result=prepared.phase2_result,
        )
        page_purpose = project_page_purpose(context)
        from app.domain.schemas.composition_contract import (
            CompositionArtifactRef,
        )

        ref = CompositionArtifactRef(
            id=1,
            artifact_kind="page_purpose_contract",
            schema_version="1.0",
            sha256="c" * 64,
        )
        projection = project_business_component_plan_prompt(
            context,
            page_purpose=page_purpose,
            page_purpose_ref=ref,
        )
        plan = projection.skeleton_plan
        stripped = plan.model_copy(
            update={
                "components": tuple(
                    component.model_copy(update={"action_ids": ()})
                    for component in plan.components
                ),
                "action_trigger_bindings": (),
            }
        )
        healed = normalize_business_component_plan(
            stripped,
            context=context,
            page_purpose=page_purpose,
            page_purpose_ref=ref,
        )
        required = {
            action_id
            for page in page_purpose.pages
            for action_id in page.action_ids
        }
        healed_actions = {
            action_id
            for component in healed.components
            for action_id in component.action_ids
        }
        assert required <= healed_actions
    finally:
        prepared.db.close()


def test_valid_first_attempt_completes() -> None:
    prepared = prepare_phase2(request_id=2404)
    ai = CompositionFixtureAI()
    try:
        result = build_v2_composition_contract(
            prepared.db,
            prepared.req.id,
            ai,
            _renderer(),
            req=prepared.req,
            phase2_result=prepared.phase2_result,
        )
        reliability = result["preview_contract"][
            "business_component_plan_reliability"
        ]
        assert reliability["terminal_result"] == "completed"
        assert len(reliability["attempts"]) == 1
        assert [stage for stage, _ in ai.calls][0] == "business_component_plan"
    finally:
        prepared.db.close()


def test_invalid_first_attempt_gets_at_most_one_recovery() -> None:
    prepared = prepare_phase2(request_id=2405)
    ai = CompositionFixtureAI()
    ai.invalid_stage_responses["business_component_plan"] = ["not-json"]
    try:
        result = build_v2_composition_contract(
            prepared.db,
            prepared.req.id,
            ai,
            _renderer(),
            req=prepared.req,
            phase2_result=prepared.phase2_result,
        )
        bcp_calls = [
            stage for stage, _ in ai.calls if stage == "business_component_plan"
        ]
        assert len(bcp_calls) == 2
        reliability = result["preview_contract"][
            "business_component_plan_reliability"
        ]
        assert len(reliability["attempts"]) == 2
        assert reliability["terminal_result"] == "completed"
    finally:
        prepared.db.close()


def test_partial_invalid_json_rejected_and_no_generic_plan() -> None:
    prepared = prepare_phase2(request_id=2406)
    ai = CompositionFixtureAI()
    ai.invalid_stage_responses["business_component_plan"] = [
        '{"components":[',
        '{"components":[',
    ]
    try:
        with pytest.raises(CompositionStageError) as exc_info:
            build_v2_composition_contract(
                prepared.db,
                prepared.req.id,
                ai,
                _renderer(),
                req=prepared.req,
                phase2_result=prepared.phase2_result,
            )
        assert exc_info.value.result_class in {
            "invalid_output",
            "validation_failed",
        }
        prepared.db.refresh(prepared.req)
        bundle = json.loads(prepared.req.generated_pages or "{}")
        reliability = bundle["preview_contract"][
            "business_component_plan_reliability"
        ]
        assert reliability["terminal_result"] in {
            "invalid_output",
            "validation_failed",
        }
        assert "generic" not in json.dumps(reliability).casefold()
        from app.domain.models import CompositionContractArtifactRecord

        rows = (
            prepared.db.query(CompositionContractArtifactRecord)
            .filter_by(request_id=prepared.req.id)
            .all()
        )
        assert [row.artifact_kind for row in rows] == [
            "page_purpose_contract"
        ]
    finally:
        prepared.db.close()


def test_timeout_reproduces_request_24_failure_class(monkeypatch) -> None:
    prepared = prepare_phase2(request_id=2424)
    cancelled = {"count": 0}

    class TimedOutAI(CompositionFixtureAI):
        def ask_chat(self, *args, **kwargs):
            time.sleep(0.12)
            return super().ask_chat(*args, **kwargs)

        def cancel_inflight(self) -> None:
            cancelled["count"] += 1

    ai = TimedOutAI()
    try:
        # Stage wall is large enough for prompt construction; per-call is not.
        monkeypatch.setattr(
            settings,
            "V2_BUSINESS_COMPONENT_TIMEOUT_SECONDS",
            1.0,
        )
        monkeypatch.setattr(
            settings,
            "V2_BUSINESS_COMPONENT_PER_CALL_TIMEOUT_SECONDS",
            0.05,
        )
        monkeypatch.setattr(
            settings,
            "V2_BUSINESS_COMPONENT_MIN_CALL_BUDGET_SECONDS",
            0.02,
        )
        monkeypatch.setattr(
            settings,
            "V2_BUSINESS_COMPONENT_MAX_AI_REPAIR",
            0,
        )
        with pytest.raises(
            CompositionStageError,
            match="wall timeout",
        ) as exc:
            build_v2_composition_contract(
                prepared.db,
                prepared.req.id,
                ai,
                _renderer(),
                req=prepared.req,
                phase2_result=prepared.phase2_result,
            )
        assert exc.value.result_class == "provider_timeout"
        assert cancelled["count"] >= 1
        prepared.db.refresh(prepared.req)
        reliability = json.loads(prepared.req.generated_pages)[
            "preview_contract"
        ]["business_component_plan_reliability"]
        assert reliability["terminal_result"] == "provider_timeout"
        assert reliability["attempts"][0]["cancelled"] is True
        assert len(ai.calls) <= 1
    finally:
        prepared.db.close()


def test_timeout_gets_at_most_one_bounded_recovery(monkeypatch) -> None:
    prepared = prepare_phase2(request_id=2407)
    bcp_calls = {"n": 0}

    class FlakyTimeoutAI(CompositionFixtureAI):
        def ask_chat(self, *args, **kwargs):
            messages = args[1] if len(args) > 1 else kwargs.get("messages")
            prompt = messages[0]["content"]
            if "BusinessComponentPlan stage" in prompt:
                bcp_calls["n"] += 1
                if bcp_calls["n"] == 1:
                    time.sleep(0.08)
                    return "{}"
            return super().ask_chat(*args, **kwargs)

        def cancel_inflight(self) -> None:
            return None

    ai = FlakyTimeoutAI()
    try:
        monkeypatch.setattr(
            settings,
            "V2_BUSINESS_COMPONENT_TIMEOUT_SECONDS",
            0.2,
        )
        monkeypatch.setattr(
            settings,
            "V2_BUSINESS_COMPONENT_PER_CALL_TIMEOUT_SECONDS",
            0.05,
        )
        monkeypatch.setattr(
            settings,
            "V2_BUSINESS_COMPONENT_MIN_CALL_BUDGET_SECONDS",
            0.01,
        )
        monkeypatch.setattr(
            settings,
            "V2_BUSINESS_COMPONENT_MAX_AI_REPAIR",
            1,
        )
        monkeypatch.setattr(
            settings,
            "V2_BUSINESS_COMPONENT_MAX_PROVIDER_CALLS",
            2,
        )
        result = build_v2_composition_contract(
            prepared.db,
            prepared.req.id,
            ai,
            _renderer(),
            req=prepared.req,
            phase2_result=prepared.phase2_result,
        )
        reliability = result["preview_contract"][
            "business_component_plan_reliability"
        ]
        assert bcp_calls["n"] == 2
        assert len(reliability["attempts"]) == 2
        assert reliability["attempts"][0]["result"] == "provider_timeout"
        assert reliability["terminal_result"] == "completed"
    finally:
        prepared.db.close()


def test_no_second_call_without_remaining_time(monkeypatch) -> None:
    prepared = prepare_phase2(request_id=2408)
    calls = {"n": 0}

    class AlwaysTimeoutAI(CompositionFixtureAI):
        def ask_chat(self, *args, **kwargs):
            calls["n"] += 1
            time.sleep(0.05)
            return "{}"

        def cancel_inflight(self) -> None:
            return None

    ai = AlwaysTimeoutAI()
    try:
        monkeypatch.setattr(
            settings,
            "V2_BUSINESS_COMPONENT_TIMEOUT_SECONDS",
            0.04,
        )
        monkeypatch.setattr(
            settings,
            "V2_BUSINESS_COMPONENT_PER_CALL_TIMEOUT_SECONDS",
            0.03,
        )
        monkeypatch.setattr(
            settings,
            "V2_BUSINESS_COMPONENT_MIN_CALL_BUDGET_SECONDS",
            0.02,
        )
        monkeypatch.setattr(
            settings,
            "V2_BUSINESS_COMPONENT_MAX_AI_REPAIR",
            1,
        )
        with pytest.raises(CompositionStageError):
            build_v2_composition_contract(
                prepared.db,
                prepared.req.id,
                ai,
                _renderer(),
                req=prepared.req,
                phase2_result=prepared.phase2_result,
            )
        assert calls["n"] == 1
    finally:
        prepared.db.close()


def test_provider_ask_chat_disables_sdk_retries_on_bounded_path() -> None:
    prepared = prepare_phase2(request_id=2409)
    seen: dict[str, Any] = {}

    class InspectAI(CompositionFixtureAI):
        def ask_chat(self, *args, **kwargs):
            seen.update(kwargs)
            return super().ask_chat(*args, **kwargs)

    ai = InspectAI()
    try:
        build_v2_composition_contract(
            prepared.db,
            prepared.req.id,
            ai,
            _renderer(),
            req=prepared.req,
            phase2_result=prepared.phase2_result,
        )
        assert seen.get("transport_attempts") == 1
        assert "timeout_seconds" in seen
    finally:
        prepared.db.close()
