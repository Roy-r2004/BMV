from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest

from app.application.appspec.policy import ModelFamilyPolicyError
from app.application.candidate_generation.cache import (
    canonical_sha256,
    sha256_text,
)
from app.application.candidate_generation.context import load_candidate_context
from app.application.candidate_generation.deterministic import (
    CandidateSourceFile,
)
from app.application.candidate_generation.workspace import (
    checkpoint_workspace,
    open_candidate_workspace,
    write_sources,
)
from app.application.tier_orchestration.policy import (
    Tier2BudgetError,
    preflight_tier_2_budget,
    tier_2_budget,
)
from app.application.tier_orchestration.projection import (
    build_tier_2_extension_contracts,
    project_tier_2_delta,
)
from app.application.tier_orchestration.repository import (
    Tier2OrchestrationRepository,
)
from app.core.config import settings
from app.domain.models import (
    CandidateEffectiveTierSummaryRecord,
    CandidateLowerTierPreservationAuditRecord,
    CandidateTierGenerationResultRecord,
    CandidateTierValidationResultRecord,
    CandidateTierVisualOutcomeRecord,
)
from app.domain.schemas.tier_orchestration import (
    Tier2FilePreservationEntry,
    Tier2PreservationManifest,
    Tier2Telemetry,
)
from tests.candidate_generation.helpers import prepare_phase3a


class _NoCallProvider:
    calls: list = []


def _attempt_and_extension(request_id: int, *, resume_suffix: str = ""):
    prepared = prepare_phase3a(request_id=request_id)
    context = load_candidate_context(
        prepared.db,
        request_id=prepared.req.id,
        phase3a_result=prepared.phase3a_result,
    )
    projection = project_tier_2_delta(
        context.composition,
        accepted_tier_1_revision_id=1,
        accepted_tier_1_manifest_sha256="a" * 64,
        accepted_tier_1_visual_summary_id=1,
    )
    repo = Tier2OrchestrationRepository(prepared.db)
    upstream = {
        "accepted": "a" * 64,
        "tier_2": projection.tier_2_closure_sha256,
        "resume_suffix": resume_suffix,
    }
    attempt = repo.get_or_create_attempt(
        request_id=prepared.req.id,
        accepted_tier_1_revision_id=1,
        accepted_tier_1_visual_summary_id=1,
        accepted_manifest_sha256="a" * 64,
        tier_closure_sha256=projection.tier_2_closure_sha256,
        delta_sha256=projection.delta_sha256,
        generation_policy_revision="phase6a-test",
        resume_identity_sha256=canonical_sha256(upstream),
        upstream_refs=upstream,
        budget=tier_2_budget(),
    )
    contracts, _refs = build_tier_2_extension_contracts(
        context.composition,
        inherited_page_purpose=context.page_purpose,
        inherited_components=context.business_components,
        inherited_content_data=context.content_data,
        projection=projection,
        artifact_record_id=attempt.id,
    )
    extension = repo.get_or_create_extension(
        attempt=attempt,
        contracts=contracts,
    )
    prepared.db.commit()
    return prepared, repo, attempt, extension


def _preservation() -> Tier2PreservationManifest:
    entry = Tier2FilePreservationEntry(
        path="src/foundation/index.css",
        classification="immutable",
        original_sha256="b" * 64,
        final_sha256="b" * 64,
        owner_ids=("DESIGN-DNA",),
        dependency_path=(),
        justification="Foundation is inherited and byte-immutable.",
        edit_authority="none",
    )
    payload = {
        "accepted_tier_1_revision_id": 1,
        "accepted_manifest_sha256": "a" * 64,
        "extension_contract_sha256": "c" * 64,
        "entries": [entry.model_dump(mode="json")],
    }
    return Tier2PreservationManifest(
        **payload,
        manifest_sha256=canonical_sha256(payload),
    )


def _persist_failed(repo, attempt, extension):
    return repo.persist_terminal(
        attempt=attempt,
        extension=extension,
        preservation=_preservation(),
        generation_payload={
            "passed": False,
            "failure": "synthetic failure",
        },
        generation_passed=False,
        validation_payload={
            "passed": False,
            "failure": "synthetic failure",
        },
        validation_passed=False,
        visual_payload={
            "passed": False,
            "failure": "synthetic failure",
        },
        visual_passed=False,
        derived_candidate_revision_id=None,
        phase4_validation_summary_id=None,
        phase5_visual_summary_id=None,
        baseline_comparison_id=None,
        status="tier_2_failed_serving_tier_1",
        failure_stage="tier_2_generation",
        fallback_reason="synthetic failure",
        telemetry=Tier2Telemetry(
            provider_call_count=0,
            output_tokens=0,
            cost_usd=0.0,
            latency_ms=1,
            generation_call_count=0,
            visual_call_count=0,
            cache_hits=0,
        ),
    )


@pytest.mark.parametrize(
    ("setting_name", "value"),
    (
        ("V2_TIER2_MAX_OUTPUT_TOKENS", 1),
        ("V2_TIER2_MAX_WALL_SECONDS", 100),
    ),
)
def test_mandatory_budget_fails_before_provider_call(
    monkeypatch,
    setting_name,
    value,
) -> None:
    prepared = prepare_phase3a(request_id=21101)
    provider = _NoCallProvider()
    monkeypatch.setattr(settings, setting_name, value)
    with pytest.raises(Tier2BudgetError, match="mandatory path"):
        preflight_tier_2_budget(
            prepared.db,
            request_id=prepared.req.id,
            ai_provider=provider,
        )
    assert provider.calls == []


def test_unknown_repair_model_fails_closed_before_provider_call(
    monkeypatch,
) -> None:
    prepared = prepare_phase3a(request_id=21102)
    provider = _NoCallProvider()
    monkeypatch.setattr(
        settings,
        "V2_TIER2_REPAIR_MODEL",
        "unknown-provider/no-family",
    )
    with pytest.raises(ModelFamilyPolicyError, match="static_repair"):
        preflight_tier_2_budget(
            prepared.db,
            request_id=prepared.req.id,
            ai_provider=provider,
        )
    assert provider.calls == []


def test_terminal_rows_rollback_as_one_transaction() -> None:
    prepared, repo, attempt, extension = _attempt_and_extension(21103)
    try:
        _persist_failed(repo, attempt, extension)
        raise RuntimeError("synthetic transaction failure")
    except RuntimeError:
        prepared.db.rollback()
    for model in (
        CandidateLowerTierPreservationAuditRecord,
        CandidateTierGenerationResultRecord,
        CandidateTierValidationResultRecord,
        CandidateTierVisualOutcomeRecord,
        CandidateEffectiveTierSummaryRecord,
    ):
        assert prepared.db.query(model).count() == 0


def test_phase6_rows_are_append_only() -> None:
    prepared, repo, attempt, extension = _attempt_and_extension(21104)
    terminal = _persist_failed(repo, attempt, extension)
    prepared.db.commit()
    terminal.row.summary_json = "{}"
    with pytest.raises(ValueError, match="append-only"):
        prepared.db.flush()
    prepared.db.rollback()


def test_resume_identity_invalidates_lower_model_policy_and_tool_changes() -> None:
    prepared, repo, attempt, _extension = _attempt_and_extension(21105)
    base = {
        "accepted_manifest": "a" * 64,
        "model": "deepseek/deepseek-v4-pro",
        "policy": "p1",
        "tool": "typescript-5",
    }
    ids = {attempt.id}
    for changed in (
        {**base, "accepted_manifest": "d" * 64},
        {**base, "model": "deepseek/deepseek-v5"},
        {**base, "policy": "p2"},
        {**base, "tool": "typescript-6"},
    ):
        row = repo.get_or_create_attempt(
            request_id=prepared.req.id,
            accepted_tier_1_revision_id=1,
            accepted_tier_1_visual_summary_id=1,
            accepted_manifest_sha256=changed["accepted_manifest"],
            tier_closure_sha256="e" * 64,
            delta_sha256="f" * 64,
            generation_policy_revision=changed["policy"],
            resume_identity_sha256=canonical_sha256(changed),
            upstream_refs=changed,
            budget=tier_2_budget(),
        )
        prepared.db.commit()
        ids.add(row.id)
    assert len(ids) == 5


def test_interrupted_workspace_resumes_only_with_exact_identity(
    monkeypatch,
) -> None:
    root = (
        Path(__file__).parent
        / ".workspace"
        / uuid.uuid4().hex
    )
    monkeypatch.setattr(settings, "PREVIEW_CANDIDATES_DIR", root)
    try:
        first = open_candidate_workspace(
            request_id=21106,
            upstream_sha256="a" * 64,
            policy_revision="phase6a-p1",
        )
        source = CandidateSourceFile(
            path="src/pages/PAGE-POLICY.tsx",
            file_kind="page",
            owner_contract_ids=("PAGE-POLICY",),
            source="export const PolicyPage = () => null;\n",
        )
        write_sources(first, (source,))
        checkpoint_workspace(
            first,
            upstream_sha256="a" * 64,
            completed_artifacts={
                source.path: sha256_text(source.source),
            },
            policy_revision="phase6a-p1",
        )
        resumed = open_candidate_workspace(
            request_id=21106,
            upstream_sha256="a" * 64,
            policy_revision="phase6a-p1",
        )
        assert resumed.resumed is True
        assert resumed.revision_uuid == first.revision_uuid
        invalidated = open_candidate_workspace(
            request_id=21106,
            upstream_sha256="a" * 64,
            policy_revision="phase6a-p2",
        )
        assert invalidated.resumed is False
        assert invalidated.revision_uuid != first.revision_uuid
    finally:
        if root.exists():
            shutil.rmtree(root)
