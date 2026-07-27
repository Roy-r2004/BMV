"""Regression: omit transition hooks must be healed without a second AI call."""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest

from app.application.candidate_generation.context import load_candidate_context
from app.application.candidate_generation.deterministic import (
    build_foundation_sources,
    ensure_content_data_compat_aliases,
)
from app.application.candidate_generation.service import build_v2_candidate_revision
from app.application.candidate_generation.validation import (
    heal_missing_transition_hooks,
    validate_generated_batch,
)
from app.application.candidate_generation.workspace import candidate_root
from app.core.config import settings
from app.domain.models.preview_candidate import CandidateRevisionRecord
from app.domain.schemas.preview_candidate import GeneratedCandidateBatch
from app.infrastructure.templating.renderer import JinjaTemplateRenderer
from tests.candidate_generation.helpers import (
    CandidateFixtureAI,
    component_batch_payload,
    prepare_phase3a,
)


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


def _remove_transition_hooks(payload: dict) -> dict:
    for item in payload["files"]:
        item["source"] = item["source"].replace(
            "data-bmv-transition-id",
            "data-bmv-transition-removed",
        )
    return payload


def test_heal_missing_transition_hooks_restores_canonical_markers(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=1701)
    try:
        context = load_candidate_context(
            prepared.db,
            request_id=prepared.req.id,
            phase3a_result=prepared.phase3a_result,
        )
        ai = CandidateFixtureAI()
        raw = component_batch_payload(
            {
                "business_component_plan": context.business_components.model_dump(
                    mode="json"
                ),
                "interaction_contract": context.interactions.model_dump(mode="json"),
                "required_component_exports": {},
                "required_component_modules": {},
            }
        )
        raw = _remove_transition_hooks(raw)
        batch = GeneratedCandidateBatch.model_validate(raw)
        before = validate_generated_batch(batch, context=context)
        assert any(item.code == "missing_transition_hook" for item in before)

        healed, used = heal_missing_transition_hooks(batch, context=context)
        assert used is True
        after = validate_generated_batch(healed, context=context)
        assert not any(item.code == "missing_transition_hook" for item in after)
        combined = "\n".join(item.source for item in healed.files)
        for interaction in context.interactions.interactions:
            for transition in interaction.transitions:
                assert (
                    f'data-bmv-transition-id="{transition.transition_id}"'
                    in combined
                )
    finally:
        prepared.db.close()


def test_omitted_transition_hooks_are_healed_without_ai_repair(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=1702)
    ai = CandidateFixtureAI()
    ai.stage_mutators["business_components"] = [_remove_transition_hooks]
    ai.repair_mutators["business_components"] = [_remove_transition_hooks]
    try:
        result = build_v2_candidate_revision(
            prepared.db,
            prepared.req.id,
            ai,
            JinjaTemplateRenderer(settings.TEMPLATES_DIR),
            req=prepared.req,
            phase3a_result=prepared.phase3a_result,
        )
        assert result["preview_contract"]["status"] == "candidate_build_pending", (
            json.dumps(result["preview_contract"].get("failure"), indent=2)
        )
        assert [item[0] for item in ai.calls] == [
            "business_components",
            "pages",
        ]
        workspace = (
            candidate_root()
            / result["preview_contract"]["candidate_revision"]["workspace_relpath"]
        )
        combined = "\n".join(
            path.read_text(encoding="utf-8") for path in workspace.rglob("*.tsx")
        )
        assert "data-bmv-transition-id=" in combined
    finally:
        prepared.db.close()


def test_foundation_ui_stubs_and_content_aliases_resolve_common_model_imports(
    isolated_candidate_paths,
) -> None:
    foundation = {
        item.path: item.source
        for item in build_foundation_sources(settings.PREVIEW_TEMPLATE_DIR)
    }
    assert "src/components/ui/button.tsx" in foundation
    assert "export function Button" in foundation["src/components/ui/button.tsx"]
    assert "src/components/ui/calendar.tsx" in foundation
    aliased = ensure_content_data_compat_aliases(
        "export const contentDataPlan = { content_items: [], data_collections: [] } as const;\n"
    )
    assert "export const contentData = contentDataPlan.content_items;" in aliased
    assert (
        "export const dataCollections = contentDataPlan.data_collections;"
        in aliased
    )


def test_contract_failure_keeps_staging_checkpoint_for_resume(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=1703)
    ai = CandidateFixtureAI()

    def strip_component_id(payload: dict) -> dict:
        payload["files"][0]["source"] = payload["files"][0]["source"].replace(
            payload["files"][0]["owner_contract_ids"][0],
            "COMP-MISSING",
            1,
        )
        return payload

    ai.stage_mutators["business_components"] = [strip_component_id]
    ai.repair_mutators["business_components"] = [strip_component_id]
    try:
        result = build_v2_candidate_revision(
            prepared.db,
            prepared.req.id,
            ai,
            JinjaTemplateRenderer(settings.TEMPLATES_DIR),
            req=prepared.req,
            phase3a_result=prepared.phase3a_result,
        )
        assert result["preview_contract"]["status"] == "candidate_contract_failed"
        revision = (
            prepared.db.query(CandidateRevisionRecord)
            .filter(CandidateRevisionRecord.request_id == prepared.req.id)
            .one()
        )
        workspace = candidate_root() / revision.workspace_relpath
        assert workspace.is_dir()
        attempt = workspace / ".attempt.json"
        assert attempt.is_file(), "failure must retain resumable attempt metadata"
        payload = json.loads(attempt.read_text(encoding="utf-8"))
        stage = (payload.get("completed_stage_state") or {}).get(
            "business_components"
        ) or {}
        assert stage.get("status") == "parsed_output"
        assert ".staging" in revision.workspace_relpath.replace("\\", "/")
    finally:
        prepared.db.close()
