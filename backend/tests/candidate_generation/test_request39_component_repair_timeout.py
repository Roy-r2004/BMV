"""Request 39: business_components_repair wall-timeout class.

Production #39:
- primary Gemini component generation completed
- strict validation required one repair
- repair model z-ai/glm-5.2 approved as component call 2/2
- wall timeout 150s fired with no usage event / no response bytes
- pages never started

This suite proves the before/after policy without live providers.
"""
from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path

import pytest

from app.application.appspec.source import canonical_json
from app.application.candidate_generation.builder import (
    CandidateStageError,
    invoke_with_timeout,
    repair_ai_batch,
)
from app.application.candidate_generation.call_budget import CandidateCallBudget
from app.application.candidate_generation.policy import repair_policy
from app.application.candidate_generation.repair_scope import (
    collect_repair_targets,
    compact_component_contract,
    scoped_failed_batch,
)
from app.application.candidate_generation.service import (
    build_v2_candidate_revision,
)
from app.core.config import settings
from app.domain.schemas.preview_candidate import (
    GeneratedCandidateBatch,
    GeneratedCandidateFile,
)
from app.infrastructure.templating.renderer import JinjaTemplateRenderer
from app.infrastructure.ai_providers.model_capabilities import (
    estimate_prompt_tokens,
)
from tests.candidate_generation.helpers import (
    CandidateFixtureAI,
    prepare_phase3a,
)


@pytest.fixture
def isolated_candidate_paths(monkeypatch):
    root = Path(__file__).resolve().parent / ".runtime" / uuid.uuid4().hex
    monkeypatch.setattr(settings, "PREVIEW_CANDIDATES_DIR", root / "candidates")
    monkeypatch.setattr(settings, "PREVIEW_APPS_DIR", root / "accepted")
    yield root
    if root.exists():
        shutil.rmtree(root)


def _sample_batch(*, bad: bool = True) -> GeneratedCandidateBatch:
    good = GeneratedCandidateFile(
        path="src/components/business/CompBookComponent.tsx",
        file_kind="business_component",
        owner_contract_ids=["COMP-BOOK"],
        source=(
            "export function CompBookComponent() {\n"
            "  return <div data-bmv-component-id=\"COMP-BOOK\">Book</div>;\n"
            "}\n"
        ),
    )
    bad_file = GeneratedCandidateFile(
        path="src/components/business/CompHomeComponent.tsx",
        file_kind="business_component",
        owner_contract_ids=["COMP-HOME"],
        source=(
            "export function CompHomeComponent() {\n"
            "  return <div>Home without contract hook</div>;\n"
            "}\n"
            if bad
            else (
                "export function CompHomeComponent() {\n"
                "  return <div data-bmv-component-id=\"COMP-HOME\">Home</div>;\n"
                "}\n"
            )
        ),
    )
    return GeneratedCandidateBatch(
        schema_version="1.0",
        batch_kind="business_components",
        files=[good, bad_file],
    )


def _legacy_large_prompt(batch: GeneratedCandidateBatch, diagnostics: list[dict]) -> str:
    """Mirror the pre-fix repair prompt shape for request-39 size evidence."""

    bindings = {
        "page_purpose_contract": {"pages": [{"page_id": f"PAGE-{i}"} for i in range(20)]},
        "business_component_plan": {
            "components": [
                {
                    "component_id": "COMP-HOME",
                    "purpose": "home hero " + ("x" * 400),
                },
                {
                    "component_id": "COMP-BOOK",
                    "purpose": "booking form " + ("y" * 400),
                },
            ]
            + [
                {
                    "component_id": f"COMP-EXTRA-{i}",
                    "purpose": "extra " + ("z" * 200),
                }
                for i in range(12)
            ]
        },
        "interaction_contract": {
            "interactions": [{"trigger_component_id": f"COMP-EXTRA-{i}"} for i in range(12)]
        },
    }
    schema = GeneratedCandidateBatch.model_json_schema()
    return (
        "legacy repair\n"
        f"FAILED_BATCH:\n{canonical_json(batch.model_dump(mode='json'))}\n"
        f"DIAGNOSTICS:\n{canonical_json(diagnostics)}\n"
        f"IMMUTABLE_CANONICAL_BINDINGS:\n{canonical_json(bindings)}\n"
        f"OUTPUT_SCHEMA:\n{canonical_json(schema)}\n"
    )


def _scoped_prompt_estimate(batch: GeneratedCandidateBatch, diagnostics: list[dict]) -> int:
    selected, parsed = collect_repair_targets(
        batch=batch,
        diagnostics=[canonical_json(item) for item in diagnostics],
    )
    scoped = scoped_failed_batch(batch=batch, selected_files=selected)
    compact = compact_component_contract(
        batch_stage="business_components",
        selected_files=selected,
        diagnostics=parsed,
        canonical_bindings={
            "business_component_plan": {
                "components": [
                    {"component_id": "COMP-HOME", "purpose": "home"},
                    {"component_id": "COMP-BOOK", "purpose": "book"},
                    {"component_id": "COMP-EXTRA-1", "purpose": "extra"},
                ]
            },
            "page_purpose_contract": {"pages": [{"page_id": "PAGE-1"}]},
            "interaction_contract": {"interactions": []},
        },
    )
    renderer = JinjaTemplateRenderer(settings.TEMPLATES_DIR)
    prompt = renderer.render(
        "prompts/v2_candidate_repair.j2",
        batch_kind="business_components",
        failed_batch_json=canonical_json(scoped.model_dump(mode="json")),
        diagnostics_json=canonical_json(list(parsed)),
        canonical_bindings_json=canonical_json(compact),
        prompt_revision=settings.V2_CANDIDATE_REPAIR_PROMPT_REVISION,
    )
    return estimate_prompt_tokens(prompt)


def test_request39_before_legacy_prompt_includes_unrelated_context() -> None:
    batch = _sample_batch(bad=True)
    diagnostics = [
        {
            "code": "missing_component_hook",
            "path": "src/components/business/CompHomeComponent.tsx",
            "related_ids": ["COMP-HOME"],
            "message": "Component ID is not exposed in its owned source.",
        }
    ]
    legacy = estimate_prompt_tokens(_legacy_large_prompt(batch, diagnostics))
    scoped = _scoped_prompt_estimate(batch, diagnostics)
    assert legacy > scoped
    assert scoped < legacy * 0.6
    selected, _parsed = collect_repair_targets(
        batch=batch,
        diagnostics=[canonical_json(item) for item in diagnostics],
    )
    assert len(selected) == 1
    assert list(selected[0].owner_contract_ids) == ["COMP-HOME"]


def test_request39_before_150s_wall_timeout_class(monkeypatch) -> None:
    """Before: hung repair exceeds 150s wall and fails closed."""

    monkeypatch.setattr(settings, "V2_CANDIDATE_REPAIR_TIMEOUT_SECONDS", 150)
    cancelled = {"count": 0}

    class _HungAI:
        name = "openrouter"

        def ask_chat(self, *args, **kwargs):
            time.sleep(0.35)
            return "{}"

        def cancel_inflight(self) -> None:
            cancelled["count"] += 1

    class _Renderer:
        def render(self, *_args, **_kwargs):
            return "repair prompt"

    batch = _sample_batch(bad=True)
    diagnostics = (
        canonical_json(
            {
                "code": "missing_component_hook",
                "path": "src/components/business/CompHomeComponent.tsx",
                "related_ids": ["COMP-HOME"],
            }
        ),
    )
    budget = CandidateCallBudget.create()
    assert budget.approve("business_components")[0]  # primary already used
    with pytest.raises(CandidateStageError) as exc:
        repair_ai_batch(
            request_id=39,
            batch_stage="business_components",
            policy=repair_policy(),
            batch=batch,
            diagnostics=diagnostics,
            canonical_bindings={"business_component_plan": {"components": []}},
            ai_provider=_HungAI(),
            template_renderer=_Renderer(),
            prompt_template="prompts/v2_candidate_repair.j2",
            phase_deadline=time.monotonic() + 0.2,
            call_budget=budget,
            candidate_revision_uuid="req39-before",
        )
    assert exc.value.stage == "business_components_repair"
    assert exc.value.provider_error_code == "candidate_stage_wall_timeout"
    assert "wall timeout" in str(exc.value)
    assert cancelled["count"] == 1
    assert budget.snapshot()["substage_used"]["business_components"] == 2
    assert budget.snapshot()["total_used"] == 2


def test_request39_after_scoped_repair_completes_within_bounded_policy(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "V2_CANDIDATE_REPAIR_TIMEOUT_SECONDS", 300)

    class _FastRepairAI:
        name = "openrouter"
        cancelled = False

        def ask_chat(self, model, messages, max_tokens=None, **kwargs):
            prompt = messages[0]["content"]
            assert "COMPACT_COMPONENT_CONTRACT" in prompt
            assert "IMMUTABLE_CANONICAL_BINDINGS" not in prompt
            assert "$defs" not in prompt
            # Only the invalid file should be present in FAILED_FILES.
            assert "CompHomeComponent" in prompt
            assert "CompBookComponent" not in prompt
            assert kwargs.get("timeout_seconds") is not None
            assert kwargs["timeout_seconds"] < 300
            return json.dumps(
                {
                    "schema_version": "1.0",
                    "batch_kind": "business_components",
                    "files": [
                        {
                            "path": "src/components/business/CompHomeComponent.tsx",
                            "file_kind": "business_component",
                            "owner_contract_ids": ["COMP-HOME"],
                            "source": (
                                "export function CompHomeComponent() {\n"
                                "  return <div data-bmv-component-id=\"COMP-HOME\">"
                                "Home</div>;\n"
                                "}\n"
                            ),
                        }
                    ],
                }
            )

        def cancel_inflight(self) -> None:
            self.cancelled = True

    batch = _sample_batch(bad=True)
    diagnostics = (
        canonical_json(
            {
                "code": "missing_component_hook",
                "path": "src/components/business/CompHomeComponent.tsx",
                "related_ids": ["COMP-HOME"],
            }
        ),
    )
    budget = CandidateCallBudget.create()
    assert budget.approve("business_components")[0]
    built = repair_ai_batch(
        request_id=39,
        batch_stage="business_components",
        policy=repair_policy(),
        batch=batch,
        diagnostics=diagnostics,
        canonical_bindings={
            "business_component_plan": {
                "components": [
                    {"component_id": "COMP-HOME", "purpose": "home"},
                    {"component_id": "COMP-BOOK", "purpose": "book"},
                ]
            }
        },
        ai_provider=_FastRepairAI(),
        template_renderer=JinjaTemplateRenderer(settings.TEMPLATES_DIR),
        prompt_template="prompts/v2_candidate_repair.j2",
        phase_deadline=time.monotonic() + 60,
        call_budget=budget,
        candidate_revision_uuid="req39-after",
    )
    assert len(built.batch.files) == 2
    home = next(
        item
        for item in built.batch.files
        if "CompHome" in item.path
    )
    assert "data-bmv-component-id=\"COMP-HOME\"" in home.source
    assert budget.snapshot()["substage_used"]["business_components"] == 2
    assert budget.snapshot()["total_used"] == 2
    # No third component call.
    ok, code = budget.approve("business_components")
    assert ok is False
    assert code == "candidate_substage_call_budget_exhausted"


def test_request39_genuine_hung_repair_still_times_out_and_cancels() -> None:
    cancelled = {"count": 0}

    def _hang() -> str:
        time.sleep(1.0)
        return "{}"

    def _on_timeout() -> None:
        cancelled["count"] += 1

    with pytest.raises(CandidateStageError) as exc:
        invoke_with_timeout(
            _hang,
            timeout_seconds=0.2,
            stage="business_components_repair",
            on_timeout=_on_timeout,
        )
    assert exc.value.provider_error_code == "candidate_stage_wall_timeout"
    assert cancelled["count"] == 1


def test_request39_end_to_end_repair_then_pages_eligible(
    isolated_candidate_paths,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "V2_CANDIDATE_REPAIR_TIMEOUT_SECONDS", 300)

    def _remove_action_hook(payload):
        payload["files"][0]["source"] = payload["files"][0]["source"].replace(
            "data-bmv-action-id",
            "data-bmv-action-removed",
        )
        return payload

    prepared = prepare_phase3a(request_id=3901)
    ai = CandidateFixtureAI()
    ai.stage_mutators["business_components"] = [_remove_action_hook]
    try:
        result = build_v2_candidate_revision(
            prepared.db,
            prepared.req.id,
            ai,
            JinjaTemplateRenderer(settings.TEMPLATES_DIR),
            req=prepared.req,
            phase3a_result=prepared.phase3a_result,
        )
        assert result["preview_contract"]["status"] == "candidate_build_pending"
        assert [item[0] for item in ai.calls] == [
            "business_components",
            "business_components_repair",
            "pages",
        ]
        ledger = result["preview_contract"]["candidate_call_ledger"]
        assert ledger["total_used"] <= 4
        assert ledger["substage_used"]["business_components"] == 2
        assert ledger["substage_used"]["pages"] >= 1
    finally:
        prepared.db.close()


def test_repair_timeout_default_is_300() -> None:
    assert settings.V2_CANDIDATE_REPAIR_TIMEOUT_SECONDS == 300
