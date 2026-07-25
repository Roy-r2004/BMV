from __future__ import annotations

import copy
import json
import time

import pytest
from sqlalchemy import event

from app.application.appspec.policy import ModelFamilyPolicyError
from app.application.composition_contract.builder import (
    CompositionStageError,
)
from app.application.composition_contract.cache import (
    composition_artifact_sha256,
)
from app.application.composition_contract.context import (
    load_composition_context,
)
from app.application.composition_contract.graph import (
    DependencyGraphError,
    build_component_dependency_graph,
)
from app.application.composition_contract.policy import (
    resolve_composition_stage_policy,
)
from app.application.composition_contract.projections import (
    project_interactions,
    project_page_purpose,
)
from app.application.composition_contract.repository import (
    composition_artifact_ref,
)
from app.application.composition_contract.service import (
    V2_COMPOSITION_CONTRACT_READY,
    build_v2_composition_contract,
)
from app.application.composition_contract.validation import (
    validate_business_component_plan,
    validate_content_data_plan,
    validate_interaction_contract,
    validate_page_purpose_contract,
)
from app.application.preview_app.pipeline import orchestrator as preview_orchestrator
from app.core.config import settings
from app.domain.models import CompositionContractArtifactRecord, Request
from app.domain.schemas.business_component_plan import BusinessComponentPlan
from app.domain.schemas.component_dependency_graph import (
    ComponentDependencyGraph,
)
from app.domain.schemas.content_data_plan import ContentDataPlan
from app.domain.schemas.interaction_contract import InteractionContract
from app.domain.schemas.page_purpose_contract import PagePurposeContract
from app.infrastructure.templating.renderer import JinjaTemplateRenderer
from tests.composition_contract.helpers import (
    CompositionFixtureAI,
    prepare_phase2,
)


def _run(prepared, ai):
    return build_v2_composition_contract(
        prepared.db,
        prepared.req.id,
        ai,
        JinjaTemplateRenderer(settings.TEMPLATES_DIR),
        req=prepared.req,
        phase2_result=prepared.phase2_result,
    )


def _rows(prepared):
    return (
        prepared.db.query(CompositionContractArtifactRecord)
        .order_by(CompositionContractArtifactRecord.id)
        .all()
    )


def _artifacts(prepared, result):
    refs = result["preview_contract"]["composition_artifact_refs"]
    schemas = (
        ("page_purpose_contract", PagePurposeContract),
        ("business_component_plan", BusinessComponentPlan),
        ("content_data_plan", ContentDataPlan),
        ("interaction_contract", InteractionContract),
        ("component_dependency_graph", ComponentDependencyGraph),
    )
    return tuple(
        schema.model_validate_json(
            prepared.db.get(
                CompositionContractArtifactRecord,
                refs[kind]["id"],
            ).artifact_json
        )
        for kind, schema in schemas
    )


def _mutate(mutator):
    def apply(payload):
        cloned = copy.deepcopy(payload)
        mutator(cloned)
        return cloned

    return apply


def test_stage_routing_has_two_ai_stages_and_three_deterministic_stages(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "V2_BUSINESS_COMPONENT_MODEL",
        "deepseek/deepseek-v4-pro",
    )
    monkeypatch.setattr(
        settings,
        "V2_CONTENT_DATA_MODEL",
        "qwen/qwen-2.5-coder-32b-instruct",
    )
    expected = {
        "page_purpose_contract": ("deterministic", False),
        "business_component_plan": (
            "deepseek/deepseek-v4-pro",
            True,
        ),
        "content_data_plan": (
            "qwen/qwen-2.5-coder-32b-instruct",
            True,
        ),
        "interaction_contract": ("deterministic", False),
        "component_dependency_graph": ("deterministic", False),
    }
    for stage, (model, ai_authored) in expected.items():
        policy = resolve_composition_stage_policy(stage)
        assert policy.model == model
        assert policy.ai_authored is ai_authored


def test_cold_path_uses_exactly_two_calls_and_persists_five_artifacts() -> None:
    prepared = prepare_phase2()
    ai = CompositionFixtureAI()
    try:
        result = _run(prepared, ai)
        assert result["preview_contract"]["status"] == (
            V2_COMPOSITION_CONTRACT_READY
        )
        assert ai.calls == [
            (
                "business_component_plan",
                "deepseek/deepseek-v4-pro",
            ),
            (
                "content_data_plan",
                "qwen/qwen-2.5-coder-32b-instruct",
            ),
        ]
        assert result["preview_contract"]["composition_contract_totals"][
            "provider_call_count"
        ] == 2
        rows = _rows(prepared)
        assert [row.artifact_kind for row in rows] == [
            "page_purpose_contract",
            "business_component_plan",
            "content_data_plan",
            "interaction_contract",
            "component_dependency_graph",
        ]
        assert [row.parent_artifact_id for row in rows] == [
            None,
            rows[0].id,
            rows[1].id,
            rows[2].id,
            rows[3].id,
        ]
        assert [row.provider_call_count for row in rows] == [0, 1, 1, 0, 0]
        assert [row.total_tokens for row in rows] == [0, 200, 200, 0, 0]
        page, components, content, interactions, graph = _artifacts(
            prepared,
            result,
        )
        assert tuple(item.route for item in page.pages) == ("/book",)
        assert components.components[0].name == "AppointmentDashboard"
        assert content.data_collections[0].entity_id == "ENTITY-BOOKING"
        assert interactions.interactions[0].action_id == "ACTION-SUBMIT"
        assert graph.route_entry_node_ids
    finally:
        prepared.db.close()


def test_full_cache_hit_revalidates_all_artifacts_and_makes_zero_calls() -> None:
    prepared = prepare_phase2(request_id=1302)
    ai = CompositionFixtureAI()
    try:
        first = _run(prepared, ai)
        calls = len(ai.calls)
        second = _run(prepared, ai)
        assert calls == 2
        assert len(ai.calls) == calls
        assert second["preview_contract"]["composition_contract_totals"][
            "provider_call_count"
        ] == 0
        assert all(
            item["cache_hit"]
            for item in second["preview_contract"][
                "composition_stage_metrics"
            ].values()
        )
        assert (
            first["preview_contract"]["composition_artifact_refs"]
            == second["preview_contract"]["composition_artifact_refs"]
        )
    finally:
        prepared.db.close()


def test_page_purpose_is_exact_deterministic_projection() -> None:
    prepared = prepare_phase2(request_id=1303)
    try:
        context = load_composition_context(
            prepared.db,
            request_id=prepared.req.id,
            phase2_result=prepared.phase2_result,
        )
        one = project_page_purpose(context)
        two = project_page_purpose(context)
        assert one == two
        assert composition_artifact_sha256(one) == (
            composition_artifact_sha256(two)
        )
        page = one.pages[0]
        assert page.page_id == "PAGE-BOOK"
        assert page.route == "/book"
        assert page.action_ids == ("ACTION-SUBMIT",)
        assert page.transition_ids == ("TRANSITION-SUBMIT",)
        assert page.evidence_ids == (
            "EVIDENCE-FORM",
            "EVIDENCE-CONFIRMATION",
        )
        assert page.journey_ids == ("JOURNEY-BOOK",)
        assert page.acceptance_test_ids == ("TEST-BOOK",)
        assert page.mobile.navigation == "collapsed_menu"
        assert page.immutable.invented_behavior_forbidden is True
        assert validate_page_purpose_contract(
            one,
            context=context,
        ).passed
    finally:
        prepared.db.close()


def test_interaction_is_exact_deterministic_projection_with_assertions() -> None:
    prepared = prepare_phase2(request_id=1304)
    ai = CompositionFixtureAI()
    try:
        result = _run(prepared, ai)
        page, components, content, interactions, _graph = _artifacts(
            prepared,
            result,
        )
        rows = _rows(prepared)
        context = load_composition_context(
            prepared.db,
            request_id=prepared.req.id,
            phase2_result=prepared.phase2_result,
        )
        expected = project_interactions(
            context,
            page_purpose=page,
            page_purpose_ref=composition_artifact_ref(rows[0]),
            component_plan=components,
            component_plan_ref=composition_artifact_ref(rows[1]),
            content_data_plan=content,
            content_data_plan_ref=composition_artifact_ref(rows[2]),
        )
        assert interactions == expected
        interaction = interactions.interactions[0]
        assert interaction.trigger_component_id == "COMP-BOOK"
        assert interaction.transitions[0].transition_id == (
            "TRANSITION-SUBMIT"
        )
        assert interaction.transitions[0].success_evidence_ids == (
            "EVIDENCE-CONFIRMATION",
        )
        assert interaction.acceptance_test_ids == ("TEST-BOOK",)
        assertion = interaction.browser_assertions[0]
        assert assertion.kind == "visible"
        assert assertion.route == "/book"
        assert assertion.evidence_id == "EVIDENCE-CONFIRMATION"
    finally:
        prepared.db.close()


def test_ai_schemas_cannot_embed_or_change_canonical_behavior() -> None:
    prepared = prepare_phase2(request_id=1305)
    ai = CompositionFixtureAI()
    try:
        result = _run(prepared, ai)
        _page, components, content, _interaction, _graph = _artifacts(
            prepared,
            result,
        )
        component_payload = components.model_dump(mode="json")
        component_payload["components"][0]["route"] = "/changed"
        with pytest.raises(Exception):
            BusinessComponentPlan.model_validate(component_payload)
        content_payload = content.model_dump(mode="json")
        content_payload["transitions"] = [{"id": "INVENTED"}]
        with pytest.raises(Exception):
            ContentDataPlan.model_validate(content_payload)
    finally:
        prepared.db.close()


def test_tampered_canonical_route_transition_evidence_and_test_fail() -> None:
    prepared = prepare_phase2(request_id=1321)
    ai = CompositionFixtureAI()
    try:
        result = _run(prepared, ai)
        page, components, content, interactions, _graph = _artifacts(
            prepared,
            result,
        )
        rows = _rows(prepared)
        context = load_composition_context(
            prepared.db,
            request_id=prepared.req.id,
            phase2_result=prepared.phase2_result,
        )
        page_payload = page.model_dump(mode="json")
        page_payload["pages"][0]["route"] = "/changed"
        tampered_page = PagePurposeContract.model_validate(page_payload)
        page_report = validate_page_purpose_contract(
            tampered_page,
            context=context,
        )
        assert not page_report.passed
        assert page_report.issues[0].code == (
            "page_purpose_not_canonical_projection"
        )

        interaction_payload = interactions.model_dump(mode="json")
        interaction = interaction_payload["interactions"][0]
        interaction["route"] = "/changed"
        interaction["transitions"][0]["transition_id"] = "TRANSITION-OTHER"
        interaction["transitions"][0]["success_evidence_ids"] = [
            "EVIDENCE-FORM"
        ]
        interaction["acceptance_test_ids"] = ["TEST-OTHER"]
        tampered_interactions = InteractionContract.model_validate(
            interaction_payload
        )
        interaction_report = validate_interaction_contract(
            tampered_interactions,
            context=context,
            page_purpose=page,
            page_purpose_ref=composition_artifact_ref(rows[0]),
            component_plan=components,
            component_plan_ref=composition_artifact_ref(rows[1]),
            content_data_plan=content,
            content_data_plan_ref=composition_artifact_ref(rows[2]),
        )
        assert not interaction_report.passed
        assert interaction_report.issues[0].code == (
            "interaction_not_canonical_projection"
        )
    finally:
        prepared.db.close()


def test_common_component_name_is_allowed_when_semantically_grounded() -> None:
    prepared = prepare_phase2(request_id=1306)
    ai = CompositionFixtureAI()
    ai.stage_mutators["business_component_plan"] = [
        _mutate(
            lambda payload: payload["components"][0].update(
                {"name": "Dashboard"}
            )
        )
    ]
    try:
        result = _run(prepared, ai)
        _page, components, *_rest = _artifacts(prepared, result)
        assert components.components[0].name == "Dashboard"
        assert len(ai.calls) == 2
    finally:
        prepared.db.close()


def test_generic_purpose_is_healed_with_canonical_domain_language() -> None:
    prepared = prepare_phase2(request_id=1307)
    ai = CompositionFixtureAI()

    def generic(payload):
        payload["components"][0].update(
            {
                "name": "AppointmentDashboard",
                "purpose": "Display useful information for users.",
                "domain_language": ["information"],
            }
        )

    ai.stage_mutators["business_component_plan"] = [_mutate(generic)]
    try:
        result = _run(prepared, ai)
        _page, components, *_rest = _artifacts(prepared, result)
        first = components.components[0]
        assert first.name == "AppointmentDashboard"
        assert any(
            token in first.purpose.casefold()
            for token in first.domain_language
        )
        assert result["preview_contract"]["status"] == V2_COMPOSITION_CONTRACT_READY
        assert len(ai.calls) == 2
    finally:
        prepared.db.close()


def test_missing_page_outcome_component_coverage_is_healed() -> None:
    prepared = prepare_phase2(request_id=1322)
    ai = CompositionFixtureAI()

    def remove_outcome(payload):
        payload["components"][0]["requirement_ids"] = ["REQ-GUIDE"]

    ai.stage_mutators["business_component_plan"] = [_mutate(remove_outcome)]
    try:
        result = _run(prepared, ai)
        assert result["preview_contract"]["status"] == V2_COMPOSITION_CONTRACT_READY
        assert [stage for stage, _model in ai.calls] == [
            "business_component_plan",
            "content_data_plan",
        ]
    finally:
        prepared.db.close()


def test_missing_action_trigger_binding_is_healed() -> None:
    prepared = prepare_phase2(request_id=1308)
    ai = CompositionFixtureAI()
    remove = _mutate(
        lambda payload: payload.update({"action_trigger_bindings": []})
    )
    ai.stage_mutators["business_component_plan"] = [remove]
    try:
        result = _run(prepared, ai)
        _page, components, *_rest = _artifacts(prepared, result)
        assert components.action_trigger_bindings
        assert result["preview_contract"]["status"] == V2_COMPOSITION_CONTRACT_READY
        assert [stage for stage, _model in ai.calls] == [
            "business_component_plan",
            "content_data_plan",
        ]
    finally:
        prepared.db.close()


def test_missing_success_evidence_binding_is_healed() -> None:
    prepared = prepare_phase2(request_id=1309)
    ai = CompositionFixtureAI()

    def remove_success(payload):
        payload["evidence_bindings"] = [
            item
            for item in payload["evidence_bindings"]
            if item["evidence_id"] != "EVIDENCE-CONFIRMATION"
        ]

    ai.stage_mutators["content_data_plan"] = [_mutate(remove_success)]
    try:
        result = _run(prepared, ai)
        assert result["preview_contract"]["status"] == V2_COMPOSITION_CONTRACT_READY
        assert [stage for stage, _model in ai.calls] == [
            "business_component_plan",
            "content_data_plan",
        ]
    finally:
        prepared.db.close()


def test_missing_action_data_binding_is_healed() -> None:
    prepared = prepare_phase2(request_id=1310)
    ai = CompositionFixtureAI()
    remove = _mutate(
        lambda payload: payload.update({"action_input_bindings": []})
    )
    ai.stage_mutators["content_data_plan"] = [remove]
    try:
        result = _run(prepared, ai)
        _page, _components, content, *_rest = _artifacts(prepared, result)
        assert content.action_input_bindings
        assert result["preview_contract"]["status"] == V2_COMPOSITION_CONTRACT_READY
    finally:
        prepared.db.close()


def test_dependency_graph_is_stable_ordered_and_has_no_template_nodes() -> None:
    prepared = prepare_phase2(request_id=1311)
    ai = CompositionFixtureAI()
    try:
        result = _run(prepared, ai)
        *_artifacts_before, graph = _artifacts(prepared, result)
        node_ids = tuple(node.node_id for node in graph.nodes)
        assert set(graph.topological_order) == set(node_ids)
        position = {
            node_id: index
            for index, node_id in enumerate(graph.topological_order)
        }
        assert all(
            position[edge.prerequisite_node_id]
            < position[edge.dependent_node_id]
            for edge in graph.edges
        )
        assert not {
            "layout",
            "skeleton",
            "catalogue",
            "template",
        } & {node.kind for node in graph.nodes}
        assert graph.generation_batches[-1].node_ids == (
            graph.route_entry_node_ids
        )
    finally:
        prepared.db.close()


def test_dependency_graph_rejects_component_cycle() -> None:
    prepared = prepare_phase2(request_id=1312)
    ai = CompositionFixtureAI()
    try:
        result = _run(prepared, ai)
        page, components, content, interactions, _graph = _artifacts(
            prepared,
            result,
        )
        rows = _rows(prepared)
        payload = components.model_dump(mode="json")
        first = payload["components"][0]
        second = copy.deepcopy(first)
        second["component_id"] = "COMP-BOOK-SUMMARY"
        second["requires_component_ids"] = [first["component_id"]]
        first["requires_component_ids"] = [second["component_id"]]
        payload["components"].append(second)
        payload["page_compositions"][0]["ordered_component_ids"].append(
            second["component_id"]
        )
        cyclic = BusinessComponentPlan.model_validate(payload)
        context = load_composition_context(
            prepared.db,
            request_id=prepared.req.id,
            phase2_result=prepared.phase2_result,
        )
        with pytest.raises(DependencyGraphError, match="cycle"):
            build_component_dependency_graph(
                refs=context.refs,
                page_purpose=page,
                page_purpose_ref=composition_artifact_ref(rows[0]),
                component_plan=cyclic,
                component_plan_ref=composition_artifact_ref(rows[1]),
                content_data_plan=content,
                content_data_plan_ref=composition_artifact_ref(rows[2]),
                interaction_contract=interactions,
                interaction_contract_ref=composition_artifact_ref(rows[3]),
            )
    finally:
        prepared.db.close()


def test_schema_failure_retries_only_failed_ai_stage_with_reason() -> None:
    prepared = prepare_phase2(request_id=1313)
    ai = CompositionFixtureAI()
    ai.invalid_stage_responses["business_component_plan"] = ["not-json"]
    try:
        result = _run(prepared, ai)
        assert [stage for stage, _model in ai.calls] == [
            "business_component_plan",
            "business_component_plan",
            "content_data_plan",
        ]
        metrics = result["preview_contract"]["composition_stage_metrics"][
            "business_component_plan"
        ]
        assert metrics["validation_retry_count"] == 1
        assert "invalid_json_or_schema" in metrics[
            "validation_retry_reasons"
        ][0]
    finally:
        prepared.db.close()


def test_unknown_model_family_fails_before_any_provider_call(
    monkeypatch,
) -> None:
    prepared = prepare_phase2(request_id=1314)
    ai = CompositionFixtureAI()
    try:
        monkeypatch.setattr(
            settings,
            "V2_BUSINESS_COMPONENT_MODEL",
            "unknown-composer",
        )
        with pytest.raises(ModelFamilyPolicyError, match="before provider"):
            _run(prepared, ai)
        assert ai.calls == []
    finally:
        prepared.db.close()


def test_business_plan_change_invalidates_all_downstream_stages(
    monkeypatch,
) -> None:
    prepared = prepare_phase2(request_id=1315)
    ai = CompositionFixtureAI()
    try:
        _run(prepared, ai)
        monkeypatch.setattr(
            settings,
            "V2_BUSINESS_COMPONENT_PROMPT_REVISION",
            "2026-07-24.2",
        )
        result = _run(prepared, ai)
        assert [stage for stage, _model in ai.calls[2:]] == [
            "business_component_plan",
            "content_data_plan",
        ]
        metrics = result["preview_contract"]["composition_stage_metrics"]
        assert metrics["page_purpose_contract"]["cache_hit"] is True
        assert metrics["business_component_plan"]["cache_hit"] is False
        assert metrics["content_data_plan"]["cache_hit"] is False
        assert metrics["interaction_contract"]["cache_hit"] is False
        assert metrics["component_dependency_graph"]["cache_hit"] is False
    finally:
        prepared.db.close()


def test_content_plan_change_invalidates_interactions_and_graph(
    monkeypatch,
) -> None:
    prepared = prepare_phase2(request_id=1316)
    ai = CompositionFixtureAI()
    try:
        _run(prepared, ai)
        monkeypatch.setattr(
            settings,
            "V2_CONTENT_DATA_PROMPT_REVISION",
            "2026-07-24.2",
        )
        result = _run(prepared, ai)
        assert [stage for stage, _model in ai.calls[2:]] == [
            "content_data_plan"
        ]
        metrics = result["preview_contract"]["composition_stage_metrics"]
        assert metrics["business_component_plan"]["cache_hit"] is True
        assert metrics["content_data_plan"]["cache_hit"] is False
        assert metrics["interaction_contract"]["cache_hit"] is False
        assert metrics["component_dependency_graph"]["cache_hit"] is False
    finally:
        prepared.db.close()


def test_corrupt_deterministic_cache_fails_without_provider_call() -> None:
    prepared = prepare_phase2(request_id=1317)
    ai = CompositionFixtureAI()
    try:
        _run(prepared, ai)
        row = _rows(prepared)[0]
        payload = json.loads(row.artifact_json)
        payload["pages"][0]["route"] = "/changed"
        row.artifact_json = json.dumps(payload)
        prepared.db.commit()
        calls = len(ai.calls)
        with pytest.raises(ValueError, match="hash is corrupt"):
            _run(prepared, ai)
        assert len(ai.calls) == calls
    finally:
        prepared.db.close()


def test_content_data_ai_failure_falls_back_to_projection(monkeypatch) -> None:
    prepared = prepare_phase2(request_id=1324)
    ai = CompositionFixtureAI()
    monkeypatch.setattr(settings, "V2_COMPOSITION_AI_STAGE_MAX_ATTEMPTS", 1)
    ai.invalid_stage_responses["content_data_plan"] = ["not-json-{"]
    try:
        result = _run(prepared, ai)
        assert result["preview_contract"]["status"] == (
            V2_COMPOSITION_CONTRACT_READY
        )
        content = next(
            row
            for row in _rows(prepared)
            if row.artifact_kind == "content_data_plan"
        )
        assert content.provider == "deterministic_fallback"
        assert content.validation_passed is True
    finally:
        prepared.db.close()


def test_stage_timeout_fails_closed(monkeypatch) -> None:
    prepared = prepare_phase2(request_id=1318)

    class SlowAI(CompositionFixtureAI):
        def ask_chat(self, *args, **kwargs):
            time.sleep(0.05)
            return super().ask_chat(*args, **kwargs)

    ai = SlowAI()
    try:
        monkeypatch.setattr(
            settings,
            "V2_BUSINESS_COMPONENT_TIMEOUT_SECONDS",
            0.01,
        )
        with pytest.raises(CompositionStageError, match="wall timeout"):
            _run(prepared, ai)
        assert [row.artifact_kind for row in _rows(prepared)] == [
            "page_purpose_contract"
        ]
    finally:
        prepared.db.close()


def test_phase_cost_limit_rolls_back_the_over_budget_ai_stage(
    monkeypatch,
) -> None:
    prepared = prepare_phase2(request_id=1323)
    ai = CompositionFixtureAI()
    try:
        monkeypatch.setattr(
            settings,
            "V2_COMPOSITION_CONTRACT_MAX_COST_USD",
            0.015,
        )
        with pytest.raises(CompositionStageError, match="cost budget"):
            _run(prepared, ai)
        assert [stage for stage, _model in ai.calls] == [
            "business_component_plan"
        ]
        assert [row.artifact_kind for row in _rows(prepared)] == [
            "page_purpose_contract"
        ]
    finally:
        prepared.db.close()


def test_final_summary_failure_rolls_back_graph_and_resume_uses_cache() -> None:
    prepared = prepare_phase2(request_id=1319)
    ai = CompositionFixtureAI()

    def fail_summary(_mapper, _connection, target) -> None:
        payload = json.loads(target.generated_pages or "{}")
        if payload.get("preview_contract", {}).get("status") == (
            V2_COMPOSITION_CONTRACT_READY
        ):
            raise RuntimeError("forced composition summary failure")

    event.listen(Request, "before_update", fail_summary)
    try:
        with pytest.raises(RuntimeError, match="composition summary"):
            _run(prepared, ai)
    finally:
        event.remove(Request, "before_update", fail_summary)
    try:
        assert [row.artifact_kind for row in _rows(prepared)] == [
            "page_purpose_contract",
            "business_component_plan",
            "content_data_plan",
            "interaction_contract",
        ]
        prepared.db.refresh(prepared.req)
        assert json.loads(prepared.req.generated_pages)[
            "preview_contract"
        ]["status"] == "design_contract_ready"
        calls = len(ai.calls)
        resumed = _run(prepared, ai)
        assert len(ai.calls) == calls
        assert resumed["preview_contract"]["composition_contract_totals"][
            "provider_call_count"
        ] == 0
        assert len(_rows(prepared)) == 5
    finally:
        prepared.db.close()


def test_phase3a_service_stops_at_composition_contract_ready(
    monkeypatch,
) -> None:
    prepared = prepare_phase2(request_id=1320)
    ai = CompositionFixtureAI()
    try:
        def forbidden(*_args, **_kwargs):
            raise AssertionError("Phase 3A reached downstream generation")

        monkeypatch.setattr(preview_orchestrator, "run_plan_phase", forbidden)
        monkeypatch.setattr(
            preview_orchestrator,
            "run_codegen_phase",
            forbidden,
        )
        monkeypatch.setattr(
            preview_orchestrator,
            "run_build_phase",
            forbidden,
        )
        monkeypatch.setattr(
            preview_orchestrator,
            "run_polish_phase",
            forbidden,
        )
        monkeypatch.setattr(preview_orchestrator, "run_finalize", forbidden)
        monkeypatch.setattr(
            "app.application.preview_app.workspace.get_workspace",
            forbidden,
        )
        monkeypatch.setattr(
            "app.application.preview_app.codegen.generate.generate_file",
            forbidden,
        )
        result = _run(prepared, ai)
        assert result["preview_contract"]["status"] == (
            V2_COMPOSITION_CONTRACT_READY
        )
        assert len(ai.calls) == 2
    finally:
        prepared.db.close()
