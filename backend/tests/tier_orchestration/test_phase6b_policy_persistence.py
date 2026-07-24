from __future__ import annotations

import pytest

from app.application.appspec.policy import ModelFamilyPolicyError
from app.application.candidate_generation.cache import canonical_sha256
from app.application.candidate_generation.context import load_candidate_context
from app.application.tier_orchestration.policy import (
    Tier3BudgetError,
    build_tier_3_visual_call_plan,
    preflight_tier_3_budget,
    tier_3_budget,
)
from app.application.tier_orchestration.projection import (
    build_tier_2_extension_contracts,
    build_tier_3_extension_contracts,
    project_tier_2_delta,
    project_tier_3_delta,
)
from app.application.tier_orchestration.repository import (
    Tier3OrchestrationRepository,
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
    Tier3PreservationManifest,
    Tier3Telemetry,
)
from tests.candidate_generation.helpers import prepare_phase3a


class _NoCallProvider:
    calls: list = []


def _attempt_and_extension(request_id: int, *, identity: dict | None = None):
    prepared = prepare_phase3a(request_id=request_id)
    context = load_candidate_context(
        prepared.db,
        request_id=prepared.req.id,
        phase3a_result=prepared.phase3a_result,
    )
    projection2 = project_tier_2_delta(
        context.composition,
        accepted_tier_1_revision_id=1,
        accepted_tier_1_manifest_sha256="a" * 64,
        accepted_tier_1_visual_summary_id=1,
    )
    contracts2, _ = build_tier_2_extension_contracts(
        context.composition,
        inherited_page_purpose=context.page_purpose,
        inherited_components=context.business_components,
        inherited_content_data=context.content_data,
        projection=projection2,
        artifact_record_id=1,
    )
    projection3 = project_tier_3_delta(
        context.composition,
        accepted_tier_1_revision_id=1,
        accepted_tier_1_visual_summary_id=1,
        accepted_tier_2_revision_id=2,
        accepted_tier_2_manifest_sha256="b" * 64,
        accepted_tier_2_visual_summary_id=2,
        accepted_tier_2_effective_summary_id=3,
        accepted_tier_2_effective_summary_sha256="c" * 64,
    )
    plan = build_tier_3_visual_call_plan(
        available_pages=(("PAGE-BOOK", "/book"),),
        selected_page_ids=("PAGE-BOOK",),
        matched_tier_2_page_ids=("PAGE-BOOK",),
    )
    provenance = identity or {
        "accepted_tier_2": "b" * 64,
        "component_model": settings.V2_TIER3_COMPONENT_MODEL,
        "page_prompt": settings.V2_TIER3_PAGE_PROMPT_REVISION,
        "policy": settings.V2_TIER3_GENERATION_POLICY_REVISION,
        "toolchain": settings.V2_RUNTIME_POLICY_REVISION,
        "grouping": plan.grouping_sha256,
    }
    repo = Tier3OrchestrationRepository(prepared.db)
    attempt = repo.get_or_create_attempt(
        request_id=prepared.req.id,
        accepted_tier_1_revision_id=1,
        accepted_tier_1_visual_summary_id=1,
        accepted_tier_2_revision_id=2,
        accepted_tier_2_visual_summary_id=2,
        accepted_tier_2_effective_summary_id=3,
        accepted_tier_2_effective_summary_sha256="c" * 64,
        accepted_manifest_sha256="b" * 64,
        tier_closure_sha256=projection3.tier_3_closure_sha256,
        delta_sha256=projection3.delta_sha256,
        generation_policy_revision=provenance["policy"],
        resume_identity_sha256=canonical_sha256(provenance),
        upstream_refs=provenance,
        budget=tier_3_budget(plan),
        visual_call_plan=plan,
    )
    contracts3, _ = build_tier_3_extension_contracts(
        context.composition,
        inherited_page_purpose=contracts2.page_purpose,
        inherited_components=contracts2.business_components,
        inherited_content_data=contracts2.content_data,
        projection=projection3,
        artifact_record_id=attempt.id,
    )
    extension = repo.get_or_create_extension(
        attempt=attempt,
        contracts=contracts3,
    )
    prepared.db.commit()
    return prepared, repo, attempt, extension, plan, projection3


def _preservation(extension, projection) -> Tier3PreservationManifest:
    entry = Tier2FilePreservationEntry(
        path="src/foundation/index.css",
        classification="immutable",
        original_sha256="d" * 64,
        final_sha256="d" * 64,
        owner_ids=("DESIGN-DNA",),
        dependency_path=(),
        justification="Accepted lower-tier foundation remains byte-identical.",
        edit_authority="none",
    )
    payload = {
        "accepted_tier_1_revision_id": 1,
        "accepted_tier_2_revision_id": 2,
        "accepted_manifest_sha256": "b" * 64,
        "accepted_tier_2_effective_summary_sha256": "c" * 64,
        "extension_contract_sha256": extension.manifest_sha256,
        "entries": [entry.model_dump(mode="json")],
    }
    return Tier3PreservationManifest(
        **payload,
        manifest_sha256=canonical_sha256(payload),
    )


def _persist_failed(repo, attempt, extension, plan, projection):
    return repo.persist_terminal(
        attempt=attempt,
        extension=extension,
        preservation=_preservation(extension, projection),
        generation_payload={"passed": False, "failure": "synthetic"},
        generation_passed=False,
        validation_payload={"passed": False, "failure": "synthetic"},
        validation_passed=False,
        visual_payload={"passed": False, "failure": "synthetic"},
        visual_passed=False,
        derived_candidate_revision_id=None,
        phase4_validation_summary_id=None,
        phase5_visual_summary_id=None,
        baseline_comparison_id=None,
        status="tier_3_failed_serving_tier_2",
        failure_stage="tier_3_generation",
        fallback_reason="synthetic",
        telemetry=Tier3Telemetry(
            provider_call_count=0,
            output_tokens=0,
            cost_usd=0.0,
            latency_ms=1,
            generation_call_count=0,
            visual_call_count=0,
            cache_hits=0,
            phase6_provider_call_count=4,
            phase6_output_tokens=100,
            phase6_cost_usd=0.04,
            phase6_latency_ms=2,
        ),
        tier_1_closure_sha256=projection.tier_1_closure_sha256,
        tier_2_closure_sha256=projection.tier_2_closure_sha256,
        tier_2_generation_policy_revision="phase6a-test",
        visual_call_plan=plan,
    )


@pytest.mark.parametrize(
    "flag",
    (
        "PREVIEW_GENERATOR_V2",
        "V2_RUNTIME_VALIDATION_ENABLED",
        "V2_VISUAL_EVALUATION_ENABLED",
        "V2_TIER2_GENERATION_ENABLED",
    ),
)
def test_each_preceding_flag_fails_closed_before_provider(
    monkeypatch,
    flag,
) -> None:
    from app.application.tier_orchestration.tier3_service import (
        Tier3OrchestrationError,
        orchestrate_v2_tier_3,
    )

    monkeypatch.setattr(settings, "V2_TIER3_GENERATION_ENABLED", True)
    monkeypatch.setattr(settings, flag, False)
    provider = _NoCallProvider()
    with pytest.raises(Tier3OrchestrationError, match="preceding"):
        orchestrate_v2_tier_3(
            None,
            1,
            provider,
            object(),
            req=None,
            phase6a_result={},
        )
    assert provider.calls == []


def test_grouping_budget_fails_before_provider_when_mandatory_calls_do_not_fit(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "V2_TIER3_MAX_CALLS", 7)
    provider = _NoCallProvider()
    pages = tuple(
        (f"PAGE-{index:02d}", f"/page-{index}") for index in range(13)
    )
    with pytest.raises(Tier3BudgetError, match="hard call ceiling"):
        build_tier_3_visual_call_plan(
            available_pages=pages,
            selected_page_ids=tuple(item[0] for item in pages),
            matched_tier_2_page_ids=(pages[0][0],),
        )
    assert provider.calls == []


def test_unknown_tier_3_repair_family_fails_before_provider(
    monkeypatch,
) -> None:
    prepared = prepare_phase3a(request_id=23220)
    provider = _NoCallProvider()
    monkeypatch.setattr(
        settings,
        "V2_TIER3_REPAIR_MODEL",
        "unknown-provider/no-family",
    )
    plan = build_tier_3_visual_call_plan(
        available_pages=(("PAGE-BOOK", "/book"),),
        selected_page_ids=("PAGE-BOOK",),
        matched_tier_2_page_ids=("PAGE-BOOK",),
    )
    with pytest.raises(ModelFamilyPolicyError, match="static_repair"):
        preflight_tier_3_budget(
            prepared.db,
            request_id=prepared.req.id,
            ai_provider=provider,
            plan=plan,
            phase6a_calls=4,
            phase6a_output_tokens=100,
            phase6a_cost_usd=0.04,
            phase6a_latency_ms=1,
        )
    assert provider.calls == []


def test_tier_3_terminal_rows_rollback_as_one_transaction() -> None:
    prepared, repo, attempt, extension, plan, projection = (
        _attempt_and_extension(23221)
    )
    try:
        _persist_failed(repo, attempt, extension, plan, projection)
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


def test_tier_3_terminal_is_append_only_and_never_promotes_or_serves() -> None:
    prepared, repo, attempt, extension, plan, projection = (
        _attempt_and_extension(23222)
    )
    terminal = _persist_failed(repo, attempt, extension, plan, projection)
    prepared.db.commit()
    summary = terminal.result["preview_contract"]["effective_tier_summary"]
    assert summary["highest_accepted_tier"] == 2
    assert summary["last_accepted_candidate_revision_id"] == 2
    assert summary["promoted"] is False
    assert summary["serving_pointer_changed"] is False
    assert summary["phase_7_invoked"] is False
    terminal.row.summary_json = "{}"
    with pytest.raises(ValueError, match="append-only"):
        prepared.db.flush()
    prepared.db.rollback()


def test_resume_identity_invalidates_every_tier_3_policy_dimension() -> None:
    prepared, repo, attempt, _extension, plan, projection = (
        _attempt_and_extension(23223)
    )
    base = {
        "accepted_tier_2": "b" * 64,
        "component_model": settings.V2_TIER3_COMPONENT_MODEL,
        "page_prompt": settings.V2_TIER3_PAGE_PROMPT_REVISION,
        "policy": settings.V2_TIER3_GENERATION_POLICY_REVISION,
        "toolchain": settings.V2_RUNTIME_POLICY_REVISION,
        "grouping": plan.grouping_sha256,
    }
    ids = {attempt.id}
    for changed in (
        {**base, "accepted_tier_2": "e" * 64},
        {**base, "component_model": "deepseek/deepseek-v5"},
        {**base, "page_prompt": "tier3-pages-v2"},
        {**base, "policy": "phase6b-policy-v2"},
        {**base, "toolchain": "phase4-toolchain-v2"},
        {**base, "grouping": "f" * 64},
    ):
        row = repo.get_or_create_attempt(
            request_id=prepared.req.id,
            accepted_tier_1_revision_id=1,
            accepted_tier_1_visual_summary_id=1,
            accepted_tier_2_revision_id=2,
            accepted_tier_2_visual_summary_id=2,
            accepted_tier_2_effective_summary_id=3,
            accepted_tier_2_effective_summary_sha256="c" * 64,
            accepted_manifest_sha256=changed["accepted_tier_2"],
            tier_closure_sha256=projection.tier_3_closure_sha256,
            delta_sha256=projection.delta_sha256,
            generation_policy_revision=changed["policy"],
            resume_identity_sha256=canonical_sha256(changed),
            upstream_refs=changed,
            budget=tier_3_budget(plan),
            visual_call_plan=plan,
        )
        prepared.db.commit()
        ids.add(row.id)
    assert len(ids) == 7
