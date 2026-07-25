from __future__ import annotations

import json
import time

import pytest
from pydantic import ValidationError
from sqlalchemy import event

from app.application.appspec.policy import ModelFamilyPolicyError
from app.application.design_contract.builder import DesignStageError
from app.application.design_contract.policy import resolve_design_stage_policy
from app.application.design_contract.service import (
    V2_DESIGN_CONTRACT_READY,
    build_v2_design_contract,
)
from app.application.preview_app.pipeline import orchestrator as preview_orchestrator
from app.core.config import settings
from app.domain.models.design_contract import DesignContractArtifactRecord
from app.domain.models.request import Request
from app.domain.schemas.design_dna import DesignDNA
from app.domain.schemas.information_architecture import InformationArchitecture
from app.domain.schemas.product_strategy import ProductStrategyV2
from app.infrastructure.templating.renderer import JinjaTemplateRenderer
from tests.design_contract.helpers import (
    DesignFixtureAI,
    prepare_phase1b,
)


def _run(prepared, ai):
    return build_v2_design_contract(
        prepared.db,
        prepared.req.id,
        ai,
        JinjaTemplateRenderer(settings.TEMPLATES_DIR),
        req=prepared.req,
        phase1_result=prepared.phase1_result,
    )


def test_configured_stage_routing_uses_strong_non_haiku_defaults(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "V2_PRODUCT_STRATEGY_MODEL",
        "deepseek/deepseek-v4-pro",
    )
    monkeypatch.setattr(
        settings,
        "V2_INFORMATION_ARCHITECTURE_MODEL",
        "google/gemini-2.5-flash",
    )
    monkeypatch.setattr(settings, "V2_DESIGN_DNA_MODEL", "z-ai/glm-5.2")
    monkeypatch.setattr(
        settings,
        "V2_DESIGN_DNA_VISION_MODEL",
        "meta-llama/llama-3.2-11b-vision-instruct",
    )
    assert resolve_design_stage_policy("product_strategy_v2").model == (
        "deepseek/deepseek-v4-pro"
    )
    assert resolve_design_stage_policy("information_architecture").model == (
        "google/gemini-2.5-flash"
    )
    assert resolve_design_stage_policy("design_dna").model == "z-ai/glm-5.2"
    assert resolve_design_stage_policy(
        "design_dna",
        use_vision=True,
    ).model == "meta-llama/llama-3.2-11b-vision-instruct"


def test_happy_path_uses_exactly_three_routed_calls_and_persists_metrics(
    monkeypatch,
) -> None:
    prepared = prepare_phase1b()
    ai = DesignFixtureAI()
    try:
        monkeypatch.setattr(
            settings,
            "V2_PRODUCT_STRATEGY_MODEL",
            "deepseek/deepseek-v4-pro",
        )
        monkeypatch.setattr(
            settings,
            "V2_INFORMATION_ARCHITECTURE_MODEL",
            "google/gemini-2.5-flash",
        )
        monkeypatch.setattr(settings, "V2_DESIGN_DNA_MODEL", "z-ai/glm-5.2")
        result = _run(prepared, ai)

        assert result["preview_contract"]["status"] == V2_DESIGN_CONTRACT_READY
        assert ai.calls == [
            ("product_strategy_v2", "deepseek/deepseek-v4-pro"),
            ("information_architecture", "google/gemini-2.5-flash"),
            ("design_dna", "z-ai/glm-5.2"),
        ]
        rows = (
            prepared.db.query(DesignContractArtifactRecord)
            .order_by(DesignContractArtifactRecord.id)
            .all()
        )
        assert [row.artifact_kind for row in rows] == [
            "product_strategy_v2",
            "information_architecture",
            "design_dna",
        ]
        assert [row.parent_artifact_id for row in rows] == [
            None,
            rows[0].id,
            rows[1].id,
        ]
        assert [row.provider_call_count for row in rows] == [1, 1, 1]
        assert [row.effective_model for row in rows] == [
            "deepseek/deepseek-v4-pro",
            "google/gemini-2.5-flash",
            "z-ai/glm-5.2",
        ]
        assert [row.model_family for row in rows] == [
            "deepseek",
            "google",
            "z-ai",
        ]
        assert {row.provider for row in rows} == {"fixture-provider"}
        assert {row.prompt_revision for row in rows} == {"2026-07-24.1"}
        assert [row.total_tokens for row in rows] == [150, 150, 150]
        assert [row.cost_usd for row in rows] == pytest.approx(
            [0.01, 0.02, 0.03]
        )
        assert all(row.latency_ms >= 0 for row in rows)
        assert result["preview_contract"]["design_contract_totals"][
            "provider_call_count"
        ] == 3
        assert result["preview_contract"]["design_contract_totals"][
            "cost_usd"
        ] == pytest.approx(0.06)
        strategy = ProductStrategyV2.model_validate_json(rows[0].artifact_json)
        ia = InformationArchitecture.model_validate_json(rows[1].artifact_json)
        dna = DesignDNA.model_validate_json(rows[2].artifact_json)
        assert strategy.primary_outcome_requirement_id == "REQ-BOOK"
        assert len(ia.pages) == 13
        assert tuple(page.page_id for page in ia.pages) == (
            "PAGE-BOOK",
            "PAGE-POLICY",
            "PAGE-GUIDE",
            "PAGE-SUPPORT-04",
            "PAGE-SUPPORT-05",
            "PAGE-SUPPORT-06",
            "PAGE-SUPPORT-07",
            "PAGE-SUPPORT-08",
            "PAGE-SUPPORT-09",
            "PAGE-SUPPORT-10",
            "PAGE-SUPPORT-11",
            "PAGE-SUPPORT-12",
            "PAGE-SUPPORT-13",
        )
        assert dna.fingerprint.name == "Visible Certainty"
    finally:
        prepared.db.close()


def test_artifacts_are_strict_and_reject_skeleton_or_component_fields() -> None:
    prepared = prepare_phase1b(request_id=1102)
    ai = DesignFixtureAI()
    try:
        result = _run(prepared, ai)
        refs = result["preview_contract"]["design_artifact_refs"]
        schema_by_kind = {
            "product_strategy_v2": ProductStrategyV2,
            "information_architecture": InformationArchitecture,
            "design_dna": DesignDNA,
        }
        for kind, schema in schema_by_kind.items():
            row = prepared.db.get(
                DesignContractArtifactRecord,
                refs[kind]["id"],
            )
            payload = json.loads(row.artifact_json)
            schema.model_validate(payload)
            payload["skeleton_id"] = "SKELETON-FORBIDDEN"
            with pytest.raises(ValidationError):
                schema.model_validate(payload)
            payload.pop("skeleton_id")
            payload["component_choice"] = "FixedHero"
            with pytest.raises(ValidationError):
                schema.model_validate(payload)
    finally:
        prepared.db.close()


def test_full_cache_hit_makes_zero_calls_and_revalidates_artifacts() -> None:
    prepared = prepare_phase1b(request_id=1103)
    ai = DesignFixtureAI()
    try:
        _run(prepared, ai)
        assert len(ai.calls) == 3
        result = _run(prepared, ai)
        assert len(ai.calls) == 3
        metrics = result["preview_contract"]["design_stage_metrics"]
        assert all(item["cache_hit"] for item in metrics.values())
        assert all(
            item["provider_call_count"] == 0 for item in metrics.values()
        )
        assert prepared.db.query(DesignContractArtifactRecord).count() == 3
    finally:
        prepared.db.close()


def test_corrupt_matching_cache_fails_closed_without_provider_call() -> None:
    prepared = prepare_phase1b(request_id=1104)
    ai = DesignFixtureAI()
    try:
        _run(prepared, ai)
        strategy = (
            prepared.db.query(DesignContractArtifactRecord)
            .filter(
                DesignContractArtifactRecord.artifact_kind
                == "product_strategy_v2"
            )
            .one()
        )
        strategy.artifact_json = "{}"
        prepared.db.commit()
        calls_before = len(ai.calls)
        with pytest.raises((ValidationError, ValueError)):
            _run(prepared, ai)
        assert len(ai.calls) == calls_before
    finally:
        prepared.db.close()


def test_design_dna_prompt_revision_invalidates_only_design_dna(
    monkeypatch,
) -> None:
    prepared = prepare_phase1b(request_id=1105)
    ai = DesignFixtureAI()
    try:
        _run(prepared, ai)
        monkeypatch.setattr(
            settings,
            "V2_DESIGN_DNA_PROMPT_REVISION",
            "2026-07-24.2",
        )
        result = _run(prepared, ai)
        assert [stage for stage, _model in ai.calls[3:]] == ["design_dna"]
        metrics = result["preview_contract"]["design_stage_metrics"]
        assert metrics["product_strategy_v2"]["cache_hit"] is True
        assert metrics["information_architecture"]["cache_hit"] is True
        assert metrics["design_dna"]["cache_hit"] is False
        assert prepared.db.query(DesignContractArtifactRecord).count() == 4
    finally:
        prepared.db.close()


def test_strategy_model_change_invalidates_all_downstream_artifacts(
    monkeypatch,
) -> None:
    prepared = prepare_phase1b(request_id=1106)
    ai = DesignFixtureAI()
    try:
        _run(prepared, ai)
        monkeypatch.setattr(
            settings,
            "V2_PRODUCT_STRATEGY_MODEL",
            "z-ai/glm-5.2",
        )
        result = _run(prepared, ai)
        assert [stage for stage, _model in ai.calls[3:]] == [
            "product_strategy_v2",
            "information_architecture",
            "design_dna",
        ]
        assert all(
            not item["cache_hit"]
            for item in result["preview_contract"][
                "design_stage_metrics"
            ].values()
        )
        assert prepared.db.query(DesignContractArtifactRecord).count() == 6
    finally:
        prepared.db.close()


def test_schema_failure_gets_one_validation_retry_with_reason() -> None:
    prepared = prepare_phase1b(request_id=1107)
    ai = DesignFixtureAI()
    ai.invalid_stage_responses["product_strategy_v2"] = ["{}"]
    try:
        result = _run(prepared, ai)
        assert len(ai.calls) == 4
        metrics = result["preview_contract"]["design_stage_metrics"][
            "product_strategy_v2"
        ]
        assert metrics["validation_retry_count"] == 1
        assert len(metrics["validation_retry_reasons"]) == 1
        row = (
            prepared.db.query(DesignContractArtifactRecord)
            .filter(
                DesignContractArtifactRecord.artifact_kind
                == "product_strategy_v2"
            )
            .one()
        )
        assert row.validation_retry_count == 1
        assert json.loads(row.validation_retry_reasons_json)
    finally:
        prepared.db.close()


def test_deterministic_route_failure_retries_once_with_reason() -> None:
    prepared = prepare_phase1b(request_id=1112)
    ai = DesignFixtureAI()

    def wrong_route(payload: dict) -> dict:
        payload["pages"][0]["route"] = "/wrong-route"
        return payload

    ai.stage_mutators["information_architecture"] = [wrong_route]
    try:
        result = _run(prepared, ai)
        assert len(ai.calls) == 4
        metrics = result["preview_contract"]["design_stage_metrics"][
            "information_architecture"
        ]
        assert metrics["validation_retry_count"] == 1
        assert "deterministic_validation" in metrics[
            "validation_retry_reasons"
        ][0]
        assert "ia_page_contract_mismatch" in metrics[
            "validation_retry_reasons"
        ][0]
    finally:
        prepared.db.close()


def test_invalid_outputs_fail_closed_without_fallback_or_persistence(
    monkeypatch,
) -> None:
    prepared = prepare_phase1b(request_id=1108)
    ai = DesignFixtureAI()
    monkeypatch.setattr(settings, "V2_DESIGN_STAGE_MAX_ATTEMPTS", 2)
    ai.invalid_stage_responses["product_strategy_v2"] = ["{}", "{}"]
    try:
        with pytest.raises(DesignStageError, match="strict validation"):
            _run(prepared, ai)
        assert len(ai.calls) == 2
        assert prepared.db.query(DesignContractArtifactRecord).count() == 0
        prepared.db.refresh(prepared.req)
        summary = json.loads(prepared.req.generated_pages)["preview_contract"]
        assert summary["status"] == "contract_ready"
    finally:
        prepared.db.close()


def test_unknown_model_fails_before_provider_calls(monkeypatch) -> None:
    prepared = prepare_phase1b(request_id=1109)
    ai = DesignFixtureAI()
    try:
        monkeypatch.setattr(
            settings,
            "V2_PRODUCT_STRATEGY_MODEL",
            "unclassified-model",
        )
        with pytest.raises(ModelFamilyPolicyError, match="before provider"):
            _run(prepared, ai)
        assert ai.calls == []
    finally:
        prepared.db.close()


def test_stage_wall_timeout_fails_closed(monkeypatch) -> None:
    prepared = prepare_phase1b(request_id=1110)

    class SlowAI(DesignFixtureAI):
        def _respond(self, model: str, prompt: str, *, vision: bool) -> str:
            time.sleep(0.05)
            return super()._respond(model, prompt, vision=vision)

    ai = SlowAI()
    try:
        monkeypatch.setattr(
            settings,
            "V2_PRODUCT_STRATEGY_TIMEOUT_SECONDS",
            0.01,
        )
        with pytest.raises(DesignStageError, match="wall timeout"):
            _run(prepared, ai)
        assert prepared.db.query(DesignContractArtifactRecord).count() == 0
    finally:
        prepared.db.close()


def test_phase2_service_stops_at_design_contract_ready(monkeypatch) -> None:
    prepared = prepare_phase1b(request_id=1111)
    ai = DesignFixtureAI()
    try:
        def forbidden(*_args, **_kwargs):
            raise AssertionError("Phase 2 reached a downstream generation path")

        monkeypatch.setattr(preview_orchestrator, "run_plan_phase", forbidden)
        monkeypatch.setattr(preview_orchestrator, "run_codegen_phase", forbidden)
        monkeypatch.setattr(preview_orchestrator, "run_build_phase", forbidden)
        monkeypatch.setattr(preview_orchestrator, "run_polish_phase", forbidden)
        monkeypatch.setattr(preview_orchestrator, "run_finalize", forbidden)
        monkeypatch.setattr(
            "app.application.preview_app.workspace.get_workspace",
            forbidden,
        )
        result = _run(prepared, ai)
        assert result["preview_contract"]["status"] == V2_DESIGN_CONTRACT_READY
        assert len(ai.calls) == 3
    finally:
        prepared.db.close()


def test_final_summary_failure_rolls_back_dna_and_resume_uses_stage_cache() -> None:
    prepared = prepare_phase1b(request_id=1113)
    ai = DesignFixtureAI()

    def fail_design_summary(_mapper, _connection, target) -> None:
        payload = json.loads(target.generated_pages or "{}")
        if (
            payload.get("preview_contract", {}).get("status")
            == V2_DESIGN_CONTRACT_READY
        ):
            raise RuntimeError("forced design summary failure")

    event.listen(Request, "before_update", fail_design_summary)
    try:
        with pytest.raises(RuntimeError, match="design summary"):
            _run(prepared, ai)
    finally:
        event.remove(Request, "before_update", fail_design_summary)
    try:
        assert prepared.db.query(DesignContractArtifactRecord).count() == 2
        prepared.db.refresh(prepared.req)
        assert (
            json.loads(prepared.req.generated_pages)["preview_contract"][
                "status"
            ]
            == "contract_ready"
        )
        resumed = _run(prepared, ai)
        assert [stage for stage, _model in ai.calls[3:]] == ["design_dna"]
        assert resumed["preview_contract"]["design_stage_metrics"][
            "product_strategy_v2"
        ]["cache_hit"] is True
        assert resumed["preview_contract"]["design_stage_metrics"][
            "information_architecture"
        ]["cache_hit"] is True
        assert prepared.db.query(DesignContractArtifactRecord).count() == 3
    finally:
        prepared.db.close()
