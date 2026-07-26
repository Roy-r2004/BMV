from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest

from app.application.candidate_generation.service import (
    build_v2_candidate_revision,
)
from app.application.appspec.repository import load_json_object
from app.application.candidate_generation.deterministic import (
    build_foundation_sources,
)
from app.application.candidate_generation.workspace import (
    candidate_root,
    open_candidate_workspace,
)
from app.application.candidate_generation.context import (
    load_candidate_context,
)
from app.application.candidate_generation.cache import (
    candidate_upstream_sha256,
)
from app.core.config import settings
from app.domain.models import (
    CandidateArtifactRecord,
    CandidateRevisionRecord,
)
from app.infrastructure.templating.renderer import JinjaTemplateRenderer
from app.application.preview_app.pipeline import orchestrator as preview_orchestrator
from tests.candidate_generation.helpers import (
    CandidateFixtureAI,
    prepare_phase3a,
)


@pytest.fixture
def isolated_candidate_paths(monkeypatch):
    root = (
        Path(__file__).resolve().parent
        / ".runtime"
        / uuid.uuid4().hex
    )
    candidates = root / "candidates"
    accepted = root / "accepted"
    monkeypatch.setattr(settings, "PREVIEW_CANDIDATES_DIR", candidates)
    monkeypatch.setattr(settings, "PREVIEW_APPS_DIR", accepted)
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


def _revision(prepared) -> CandidateRevisionRecord:
    return (
        prepared.db.query(CandidateRevisionRecord)
        .filter(CandidateRevisionRecord.request_id == prepared.req.id)
        .order_by(CandidateRevisionRecord.revision.desc())
        .first()
    )


def _workspace(prepared) -> Path:
    row = _revision(prepared)
    assert row.workspace_relpath
    return candidate_root() / row.workspace_relpath


def _remove_action_hook(payload):
    payload["files"][0]["source"] = payload["files"][0]["source"].replace(
        "data-bmv-action-id",
        "data-bmv-action-removed",
    )
    return payload


def _remove_acceptance_hook(payload):
    payload["files"][0]["source"] = payload["files"][0]["source"].replace(
        "data-bmv-acceptance-test-id",
        "data-bmv-acceptance-test-removed",
    )
    return payload


def test_cold_candidate_uses_exactly_two_calls_and_freezes_unserved_revision(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a()
    ai = CandidateFixtureAI()
    try:
        result = _run(prepared, ai)
        assert result["preview_contract"]["status"] == (
            "candidate_build_pending"
        ), json.dumps(result["preview_contract"].get("failure"), indent=2)
        assert ai.calls == [
            ("business_components", settings.V2_CANDIDATE_COMPONENT_MODEL),
            ("pages", settings.V2_CANDIDATE_PAGE_MODEL),
        ]
        assert result["preview_contract"]["candidate_totals"][
            "provider_call_count"
        ] == 2
        revision = _revision(prepared)
        assert revision.status == "candidate_build_pending"
        assert revision.workspace_relpath
        workspace = candidate_root() / revision.workspace_relpath
        assert workspace.is_dir()
        assert not (settings.PREVIEW_APPS_DIR / str(prepared.req.id)).exists()
        rows = (
            prepared.db.query(CandidateArtifactRecord)
            .filter(CandidateArtifactRecord.request_id == prepared.req.id)
            .order_by(CandidateArtifactRecord.id)
            .all()
        )
        assert [row.artifact_kind for row in rows] == [
            "foundation",
            "data_exports",
            "business_components",
            "pages",
            "routes",
            "validation",
        ]
    finally:
        prepared.db.close()


def test_full_cache_hit_uses_zero_calls_and_creates_new_revision(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=1602)
    first_ai = CandidateFixtureAI()
    second_ai = CandidateFixtureAI()
    try:
        first = _run(prepared, first_ai)
        second = _run(prepared, second_ai)
        assert first["preview_contract"]["status"] == "candidate_build_pending"
        assert second["preview_contract"]["status"] == "candidate_build_pending", (
            json.dumps(second["preview_contract"].get("failure"), indent=2)
        )
        assert len(first_ai.calls) == 2
        assert second_ai.calls == []
        assert second["preview_contract"]["candidate_totals"][
            "provider_call_count"
        ] == 0
        revisions = (
            prepared.db.query(CandidateRevisionRecord)
            .filter(CandidateRevisionRecord.request_id == prepared.req.id)
            .order_by(CandidateRevisionRecord.revision)
            .all()
        )
        assert len(revisions) == 2
        assert revisions[0].revision_uuid != revisions[1].revision_uuid
        assert revisions[0].workspace_relpath != revisions[1].workspace_relpath
    finally:
        prepared.db.close()


def test_foundation_and_routes_are_byte_stable(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=1603)
    try:
        _run(prepared, CandidateFixtureAI())
        first = _workspace(prepared)
        first_foundation = {
            item.path: (first / item.path).read_bytes()
            for item in build_foundation_sources(
                settings.PREVIEW_TEMPLATE_DIR
            )
        }
        first_routes = (
            first / "src/generated/route-manifest.ts"
        ).read_bytes()
        _run(prepared, CandidateFixtureAI())
        second = _workspace(prepared)
        assert first_foundation == {
            path: (second / path).read_bytes()
            for path in first_foundation
        }
        assert first_routes == (
            second / "src/generated/route-manifest.ts"
        ).read_bytes()
    finally:
        prepared.db.close()


def test_generated_data_exactly_matches_content_data_plan(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=1604)
    try:
        _run(prepared, CandidateFixtureAI())
        context = load_candidate_context(
            prepared.db,
            request_id=prepared.req.id,
            phase3a_result=prepared.phase3a_result,
        )
        payload = json.loads(
            (_workspace(prepared) / "src/generated/content-data.json")
            .read_text(encoding="utf-8")
        )
        assert payload == context.content_data.model_dump(mode="json")
        assert payload["data_collections"][0]["seed_records"]
        assert payload["evidence_bindings"]
    finally:
        prepared.db.close()


def test_deterministic_routes_preserve_exact_appspec_and_role_access(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=1605)
    try:
        _run(prepared, CandidateFixtureAI())
        context = load_candidate_context(
            prepared.db,
            request_id=prepared.req.id,
            phase3a_result=prepared.phase3a_result,
        )
        app = (_workspace(prepared) / "src/App.tsx").read_text(
            encoding="utf-8"
        )
        manifest = (
            _workspace(prepared) / "src/generated/route-manifest.ts"
        ).read_text(encoding="utf-8")
        for page in context.page_purpose.pages:
            assert f'path="{page.route}"' in app
            assert page.page_id in app
            assert page.route in manifest
            for role_id in page.role_ids:
                assert role_id in manifest
        assert "MarketingHero" not in app
        assert "@/ui" not in app
    finally:
        prepared.db.close()


def test_missing_component_contract_hook_uses_one_scoped_repair(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=1606)
    ai = CandidateFixtureAI()
    ai.stage_mutators["business_components"] = [_remove_action_hook]
    try:
        result = _run(prepared, ai)
        assert result["preview_contract"]["status"] == "candidate_build_pending"
        assert [item[0] for item in ai.calls] == [
            "business_components",
            "business_components_repair",
            "pages",
        ]
        metrics = result["preview_contract"]["candidate_stage_metrics"][
            "business_components"
        ]
        assert metrics["provider_call_count"] == 2
        assert metrics["repair_call_count"] == 1
    finally:
        prepared.db.close()


def test_component_and_page_repairs_are_capped_at_four_calls(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=1607)
    ai = CandidateFixtureAI()
    ai.stage_mutators["business_components"] = [_remove_action_hook]
    ai.stage_mutators["pages"] = [_remove_acceptance_hook]
    try:
        result = _run(prepared, ai)
        assert result["preview_contract"]["status"] == "candidate_build_pending"
        assert [item[0] for item in ai.calls] == [
            "business_components",
            "business_components_repair",
            "pages",
            "pages_repair",
        ]
        assert result["preview_contract"]["candidate_totals"][
            "provider_call_count"
        ] == 4
        assert result["preview_contract"]["candidate_totals"][
            "repair_call_count"
        ] == 2
    finally:
        prepared.db.close()


def test_ai_cannot_claim_route_or_infrastructure_files(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=1608)
    ai = CandidateFixtureAI()

    def claim_app(payload):
        payload["files"][0]["path"] = "src/App.tsx"
        return payload

    ai.stage_mutators["business_components"] = [claim_app]
    try:
        result = _run(prepared, ai)
        assert result["preview_contract"]["status"] == "candidate_failed"
        assert result["preview_contract"]["failure"]["error_type"] == (
            "CandidateStageError"
        )
        assert not (settings.PREVIEW_APPS_DIR / str(prepared.req.id)).exists()
    finally:
        prepared.db.close()


def test_failed_contract_retains_diagnostics_and_is_never_promoted(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=1609)
    ai = CandidateFixtureAI()
    ai.stage_mutators["business_components"] = [_remove_action_hook]
    ai.repair_mutators["business_components"] = [_remove_action_hook]
    try:
        result = _run(prepared, ai)
        assert result["preview_contract"]["status"] == (
            "candidate_contract_failed"
        )
        assert result["preview_contract"]["failure"]["issues"]
        revision = _revision(prepared)
        assert revision.status == "candidate_contract_failed"
        assert json.loads(revision.failure_json)["issues"]
        assert _workspace(prepared).is_dir()
        assert not (settings.PREVIEW_APPS_DIR / str(prepared.req.id)).exists()
    finally:
        prepared.db.close()


def test_scoped_repair_cannot_touch_unrelated_files(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=1610)
    ai = CandidateFixtureAI()
    ai.stage_mutators["business_components"] = [_remove_action_hook]

    def escape_batch(payload):
        payload["files"][0]["path"] = "src/pages/UnrelatedPage.tsx"
        return payload

    ai.repair_mutators["business_components"] = [escape_batch]
    try:
        result = _run(prepared, ai)
        assert result["preview_contract"]["status"] == "candidate_failed"
        assert "batch ownership" in result["preview_contract"]["failure"][
            "message"
        ]
        assert len(ai.calls) == 2
    finally:
        prepared.db.close()


def test_accepted_preview_files_and_serving_state_remain_unchanged(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=1611)
    accepted = settings.PREVIEW_APPS_DIR / str(prepared.req.id)
    accepted.mkdir(parents=True)
    marker = accepted / "accepted.txt"
    marker.write_text("accepted-v1", encoding="utf-8")
    before_generated_pages = prepared.req.generated_pages
    try:
        result = _run(prepared, CandidateFixtureAI())
        assert result["preview_contract"]["status"] == "candidate_build_pending"
        assert marker.read_text(encoding="utf-8") == "accepted-v1"
        assert list(accepted.iterdir()) == [marker]
        assert _revision(prepared).workspace_relpath
        assert prepared.req.status != "ready"
        assert before_generated_pages != prepared.req.generated_pages
    finally:
        prepared.db.close()


def test_generated_batches_follow_candidate_artifact_dag(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=1612)
    try:
        _run(prepared, CandidateFixtureAI())
        rows = (
            prepared.db.query(CandidateArtifactRecord)
            .filter(CandidateArtifactRecord.request_id == prepared.req.id)
            .order_by(CandidateArtifactRecord.id)
            .all()
        )
        assert [item.parent_artifact_id for item in rows] == [
            None,
            rows[0].id,
            rows[1].id,
            rows[2].id,
            rows[3].id,
            rows[4].id,
        ]
        component_batch = load_json_object(rows[2].artifact_json)
        page_batch = load_json_object(rows[3].artifact_json)
        assert component_batch["batch_kind"] == "business_components"
        assert page_batch["batch_kind"] == "pages"
        assert all(
            item["path"].startswith("src/components/business/")
            for item in component_batch["files"]
        )
        assert all(
            item["path"].startswith("src/pages/")
            for item in page_batch["files"]
        )
        context = load_candidate_context(
            prepared.db,
            request_id=prepared.req.id,
            phase3a_result=prepared.phase3a_result,
        )
        kinds = {
            item.node_id: item.kind
            for item in context.dependency_graph.nodes
        }
        expected_components = [
            next(
                node.contract_id
                for node in context.dependency_graph.nodes
                if node.node_id == node_id
            )
            for node_id in context.dependency_graph.topological_order
            if kinds[node_id] == "business_component"
        ]
        expected_pages = [
            next(
                node.contract_id
                for node in context.dependency_graph.nodes
                if node.node_id == node_id
            )
            for node_id in context.dependency_graph.topological_order
            if kinds[node_id] == "page"
        ]
        assert [
            item["owner_contract_ids"][0]
            for item in component_batch["files"]
        ] == expected_components
        assert [
            item["owner_contract_ids"][0] for item in page_batch["files"]
        ] == expected_pages
    finally:
        prepared.db.close()


def test_candidate_contains_no_legacy_scaffold_or_mandatory_ui_import(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=1613)
    try:
        _run(prepared, CandidateFixtureAI())
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in _workspace(prepared).rglob("*")
            if path.suffix in {".ts", ".tsx"}
        )
        for marker in (
            "SkeletonComposer",
            "MarketingHero",
            "ProductShowcase",
            "OpsShell",
            "@/ui",
        ):
            assert marker not in source
    finally:
        prepared.db.close()


def test_component_prompt_change_invalidates_components_and_downstream(
    isolated_candidate_paths,
    monkeypatch,
) -> None:
    prepared = prepare_phase3a(request_id=1614)
    try:
        _run(prepared, CandidateFixtureAI())
        monkeypatch.setattr(
            settings,
            "V2_CANDIDATE_COMPONENT_PROMPT_REVISION",
            "2026-07-24.2",
        )
        ai = CandidateFixtureAI()
        result = _run(prepared, ai)
        assert result["preview_contract"]["status"] == "candidate_build_pending"
        assert [item[0] for item in ai.calls] == [
            "business_components",
            "pages",
        ]
        metrics = result["preview_contract"]["candidate_stage_metrics"]
        assert metrics["foundation"]["cache_hit"] is True
        assert metrics["data_exports"]["cache_hit"] is True
        assert metrics["business_components"]["cache_hit"] is False
        assert metrics["pages"]["cache_hit"] is False
    finally:
        prepared.db.close()


def test_page_prompt_change_invalidates_only_page_and_downstream(
    isolated_candidate_paths,
    monkeypatch,
) -> None:
    prepared = prepare_phase3a(request_id=1615)
    try:
        _run(prepared, CandidateFixtureAI())
        monkeypatch.setattr(
            settings,
            "V2_CANDIDATE_PAGE_PROMPT_REVISION",
            "2026-07-24.2",
        )
        ai = CandidateFixtureAI()
        result = _run(prepared, ai)
        assert [item[0] for item in ai.calls] == ["pages"]
        metrics = result["preview_contract"]["candidate_stage_metrics"]
        assert metrics["business_components"]["cache_hit"] is True
        assert metrics["pages"]["cache_hit"] is False
        assert metrics["routes"]["cache_hit"] is False
        assert metrics["validation"]["cache_hit"] is False
    finally:
        prepared.db.close()


def test_dependency_lock_change_invalidates_foundation_and_downstream(
    isolated_candidate_paths,
    monkeypatch,
) -> None:
    prepared = prepare_phase3a(request_id=1624)
    import app.application.candidate_generation.service as service

    try:
        _run(prepared, CandidateFixtureAI())
        monkeypatch.setattr(
            service,
            "dependency_lock_sha256",
            lambda _path: "f" * 64,
        )
        ai = CandidateFixtureAI()
        result = _run(prepared, ai)
        assert result["preview_contract"]["status"] == "candidate_build_pending"
        assert [item[0] for item in ai.calls] == [
            "business_components",
            "pages",
        ]
        metrics = result["preview_contract"]["candidate_stage_metrics"]
        assert metrics["foundation"]["cache_hit"] is False
        assert metrics["data_exports"]["cache_hit"] is False
        assert metrics["business_components"]["cache_hit"] is False
        assert metrics["pages"]["cache_hit"] is False
    finally:
        prepared.db.close()


def test_cache_hit_still_reruns_full_static_validation(
    isolated_candidate_paths,
    monkeypatch,
) -> None:
    prepared = prepare_phase3a(request_id=1616)
    import app.application.candidate_generation.service as service

    calls = 0
    original = service.validate_candidate_workspace

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "validate_candidate_workspace", counted)
    try:
        _run(prepared, CandidateFixtureAI())
        _run(prepared, CandidateFixtureAI())
        assert calls == 2
    finally:
        prepared.db.close()


def test_verified_nonterminal_staging_attempt_is_resumed(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=1617)
    try:
        context = load_candidate_context(
            prepared.db,
            request_id=prepared.req.id,
            phase3a_result=prepared.phase3a_result,
        )
        staged = open_candidate_workspace(
            request_id=prepared.req.id,
            upstream_sha256=candidate_upstream_sha256(context.refs),
        )
        result = _run(prepared, CandidateFixtureAI())
        assert result["preview_contract"]["candidate_resumed"] is True
        assert result["preview_contract"]["candidate_revision"][
            "revision_uuid"
        ] == staged.revision_uuid
        assert not staged.staging_path.exists()
    finally:
        prepared.db.close()


def test_unknown_model_family_fails_before_provider_call(
    isolated_candidate_paths,
    monkeypatch,
) -> None:
    prepared = prepare_phase3a(request_id=1618)
    ai = CandidateFixtureAI()
    monkeypatch.setattr(
        settings,
        "V2_CANDIDATE_COMPONENT_MODEL",
        "unknown/vendor-model",
    )
    try:
        result = _run(prepared, ai)
        assert result["preview_contract"]["status"] == "candidate_failed"
        assert ai.calls == []
        assert "Unknown model family" in result["preview_contract"]["failure"][
            "message"
        ]
    finally:
        prepared.db.close()


def test_unapproved_dependency_is_repaired_without_whole_regeneration(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=1619)
    ai = CandidateFixtureAI()

    def unknown_import(payload):
        payload["files"][0]["source"] = (
            'import mystery from "not-approved";\n'
            + payload["files"][0]["source"]
        )
        return payload

    ai.stage_mutators["business_components"] = [unknown_import]
    try:
        result = _run(prepared, ai)
        assert result["preview_contract"]["status"] == "candidate_build_pending"
        assert [item[0] for item in ai.calls] == [
            "business_components",
            "pages",
            "business_components_repair",
        ]
        assert "not-approved" not in "\n".join(
            path.read_text(encoding="utf-8")
            for path in _workspace(prepared).rglob("*.tsx")
        )
    finally:
        prepared.db.close()


def test_phase_wall_deadline_fails_without_whole_pipeline_retry(
    isolated_candidate_paths,
    monkeypatch,
) -> None:
    prepared = prepare_phase3a(request_id=1620)
    ai = CandidateFixtureAI()
    monkeypatch.setattr(settings, "V2_CANDIDATE_TIMEOUT_SECONDS", 0)
    try:
        result = _run(prepared, ai)
        assert result["preview_contract"]["status"] == "candidate_failed"
        assert len(ai.calls) <= 1
        assert _revision(prepared).revision == 1
    finally:
        prepared.db.close()


def test_static_gate_invokes_no_vite_playwright_or_axe(
    isolated_candidate_paths,
    monkeypatch,
) -> None:
    prepared = prepare_phase3a(request_id=1621)
    import app.application.candidate_generation.validation as validation

    commands = []
    original = validation.subprocess.run

    def recorded(command, *args, **kwargs):
        commands.append([str(item) for item in command])
        return original(command, *args, **kwargs)

    monkeypatch.setattr(validation.subprocess, "run", recorded)
    try:
        result = _run(prepared, CandidateFixtureAI())
        assert result["preview_contract"]["status"] == "candidate_build_pending"
        flattened = " ".join(item for command in commands for item in command)
        assert "validate_candidate.mjs" in flattened
        for forbidden in ("vite", "playwright", "axe"):
            assert forbidden not in flattened.casefold()
    finally:
        prepared.db.close()


def test_v2_pipeline_stops_before_legacy_codegen_build_and_finalize(
    isolated_candidate_paths,
    monkeypatch,
) -> None:
    prepared = prepare_phase3a(request_id=1622)
    ai = CandidateFixtureAI()
    # This boundary asserts Phase 3B terminal status. Local .env may enable
    # Phase 4/5; pin them off so the test stays environment-independent.
    monkeypatch.setattr(settings, "V2_RUNTIME_VALIDATION_ENABLED", False)
    monkeypatch.setattr(settings, "V2_VISUAL_EVALUATION_ENABLED", False)
    monkeypatch.setattr(
        "app.application.preview_app.pipeline.v2_contract."
        "build_v2_app_spec_contract",
        lambda *_args, **_kwargs: {
            "preview_contract": {"status": "contract_ready"}
        },
    )
    monkeypatch.setattr(
        "app.application.preview_app.pipeline.v2_contract."
        "build_v2_design_contract",
        lambda *_args, **_kwargs: {
            "preview_contract": {"status": "design_contract_ready"}
        },
    )
    monkeypatch.setattr(
        "app.application.preview_app.pipeline.v2_contract."
        "build_v2_composition_contract",
        lambda *_args, **_kwargs: prepared.phase3a_result,
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Phase 3B reached a downstream v1/Phase 4 path")

    monkeypatch.setattr(preview_orchestrator, "run_plan_phase", forbidden)
    monkeypatch.setattr(preview_orchestrator, "run_codegen_phase", forbidden)
    monkeypatch.setattr(preview_orchestrator, "run_build_phase", forbidden)
    monkeypatch.setattr(preview_orchestrator, "run_polish_phase", forbidden)
    monkeypatch.setattr(preview_orchestrator, "run_finalize", forbidden)
    monkeypatch.setattr(
        "app.application.preview_app.workspace.get_workspace",
        forbidden,
    )
    monkeypatch.setattr(
        "app.application.preview_app.codegen.generate.generate_file",
        forbidden,
    )
    try:
        result = preview_orchestrator._run_v2_boundary(
            prepared.db,
            prepared.req.id,
            ai,
            JinjaTemplateRenderer(settings.TEMPLATES_DIR),
            app_spec_revision_id=None,
            req=prepared.req,
        )
        assert result["preview_contract"]["status"] == (
            "candidate_build_pending"
        )
        assert len(ai.calls) == 2
    finally:
        prepared.db.close()


def test_final_transaction_failure_rolls_back_artifacts_and_records_failure(
    isolated_candidate_paths,
    monkeypatch,
) -> None:
    prepared = prepare_phase3a(request_id=1623)
    original_commit = prepared.db.commit
    commit_calls = 0

    def fail_once():
        nonlocal commit_calls
        commit_calls += 1
        if commit_calls == 1:
            raise RuntimeError("synthetic candidate transaction failure")
        return original_commit()

    monkeypatch.setattr(prepared.db, "commit", fail_once)
    try:
        result = _run(prepared, CandidateFixtureAI())
        assert result["preview_contract"]["status"] == "candidate_failed"
        assert "synthetic candidate transaction failure" in (
            result["preview_contract"]["failure"]["message"]
        )
        assert (
            prepared.db.query(CandidateArtifactRecord)
            .filter(CandidateArtifactRecord.request_id == prepared.req.id)
            .count()
            == 0
        )
        revisions = (
            prepared.db.query(CandidateRevisionRecord)
            .filter(CandidateRevisionRecord.request_id == prepared.req.id)
            .all()
        )
        assert len(revisions) == 1
        assert revisions[0].status == "candidate_failed"
        assert not (settings.PREVIEW_APPS_DIR / str(prepared.req.id)).exists()
    finally:
        prepared.db.close()
