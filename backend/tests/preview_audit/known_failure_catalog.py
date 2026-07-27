"""Catalog of known production failure classes for deterministic replay."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KnownFailureClass:
    failure_id: str
    stage: str
    typed_error: str
    customer_safe: bool
    retryable: bool
    deterministic_repair: bool
    requires_regeneration: bool
    existing_test: str | None
    fixture_strategy: str
    notes: str


KNOWN_FAILURES: tuple[KnownFailureClass, ...] = (
    KnownFailureClass(
        failure_id="ia_page_closure",
        stage="information_architecture",
        typed_error="DesignStageError|TierBuildError",
        customer_safe=True,
        retryable=True,
        deterministic_repair=False,
        requires_regeneration=True,
        existing_test="tests/preview_contract/test_tier1_closure_heal.py",
        fixture_strategy="omit journey-required page from IA/tier set",
        notes="Fails before composition when closure heal cannot close refs",
    ),
    KnownFailureClass(
        failure_id="admin_dashboard_optional_closure",
        stage="tier1_closure_heal",
        typed_error="Tier1ClosureHealError",
        customer_safe=True,
        retryable=False,
        deterministic_repair=True,
        requires_regeneration=False,
        existing_test="tests/preview_contract/test_tier1_closure_heal.py",
        fixture_strategy="include optional admin page without closed refs",
        notes="Optional page treated journey-required inconsistently",
    ),
    KnownFailureClass(
        failure_id="page_ai_features_closure",
        stage="tier1_closure_heal",
        typed_error="Tier1ClosureHealError",
        customer_safe=True,
        retryable=False,
        deterministic_repair=True,
        requires_regeneration=False,
        existing_test="tests/preview_contract/test_tier1_closure_heal.py",
        fixture_strategy="PAGE-AI-FEATURES referenced without closed graph",
        notes="Smoke #23 class before closure heal",
    ),
    KnownFailureClass(
        failure_id="page_membership_mismatch",
        stage="appspec",
        typed_error="page_membership_mismatch",
        customer_safe=True,
        retryable=True,
        deterministic_repair=True,
        requires_regeneration=False,
        existing_test="tests/appspec/test_graph_repair.py",
        fixture_strategy="_two_page_mismatch_payload",
        notes="Graph repair path; fallback must stay disabled for v2",
    ),
    KnownFailureClass(
        failure_id="appspec_graph_contradiction",
        stage="appspec",
        typed_error="AppSpecGenerationError|validation",
        customer_safe=True,
        retryable=True,
        deterministic_repair=True,
        requires_regeneration=True,
        existing_test="tests/appspec/test_graph_repair.py",
        fixture_strategy="contradictory action/page ownership",
        notes="Deterministic graph repair or reject",
    ),
    KnownFailureClass(
        failure_id="missing_node_modules_build_env",
        stage="runtime_build",
        typed_error="import_resolution_failed",
        customer_safe=True,
        retryable=True,
        deterministic_repair=False,
        requires_regeneration=False,
        existing_test=(
            "tests/preview_audit/test_request31_phase4_fixture.py"
        ),
        fixture_strategy="redacted production request #31 candidate workspace",
        notes=(
            "Template tsc was invoked from a /app/data candidate without a "
            "candidate-local verified dependency view"
        ),
    ),
    KnownFailureClass(
        failure_id="bcp_wall_timeout",
        stage="business_component_plan",
        typed_error="provider_timeout",
        customer_safe=True,
        retryable=True,
        deterministic_repair=True,
        requires_regeneration=False,
        existing_test="tests/composition_contract/test_business_component_plan_reliability.py",
        fixture_strategy="SlowAI exceeding per-call/wall budgets",
        notes="Smoke #24; bounded recovery now present",
    ),
    KnownFailureClass(
        failure_id="bcp_invalid_output",
        stage="business_component_plan",
        typed_error="invalid_output",
        customer_safe=True,
        retryable=True,
        deterministic_repair=True,
        requires_regeneration=False,
        existing_test="tests/composition_contract/test_business_component_plan_reliability.py",
        fixture_strategy="invalid JSON / schema-invalid BCP",
        notes="AI repair capped",
    ),
    KnownFailureClass(
        failure_id="missing_business_component_usage",
        stage="candidate_pages",
        typed_error="missing_business_component_usage",
        customer_safe=True,
        retryable=True,
        deterministic_repair=True,
        requires_regeneration=False,
        existing_test="tests/candidate_generation/test_business_component_usage.py",
        fixture_strategy="generic pages without BC mounts",
        notes="Smoke #25; heal+bindings uncommitted",
    ),
    KnownFailureClass(
        failure_id="candidate_contract_failure",
        stage="candidate_validation",
        typed_error="candidate_contract_failed",
        customer_safe=True,
        retryable=True,
        deterministic_repair=True,
        requires_regeneration=False,
        existing_test="tests/candidate_generation/test_phase3b_candidate_generation.py",
        fixture_strategy="mutators that strip hooks and refuse repair",
        notes="Must not enter Phase4",
    ),
    KnownFailureClass(
        failure_id="phase4_pending_mismatch",
        stage="runtime_build",
        typed_error="Phase 4 requires candidate_build_pending",
        customer_safe=True,
        retryable=False,
        deterministic_repair=False,
        requires_regeneration=True,
        existing_test=None,
        fixture_strategy="invoke runtime on candidate_contract_failed status",
        notes="Smoke #25 surface message; late orchestration mismatch",
    ),
    KnownFailureClass(
        failure_id="missing_visual_acceptance",
        stage="visual_evaluation",
        typed_error="candidate_visual_rejected|missing acceptance",
        customer_safe=True,
        retryable=True,
        deterministic_repair=False,
        requires_regeneration=True,
        existing_test="tests/visual_evaluation/",
        fixture_strategy="blank/uniform screenshots hard-gate",
        notes="Blocks Expanded Preview",
    ),
    KnownFailureClass(
        failure_id="expanded_preview_409_no_tier1",
        stage="expanded_preview_request",
        typed_error="ExpandedPreviewServiceError/409",
        customer_safe=True,
        retryable=False,
        deterministic_repair=False,
        requires_regeneration=True,
        existing_test="tests/commercial/test_expanded_preview_workflow.py",
        fixture_strategy="request EP without accepted Tier1 visual",
        notes="Eligibility discovered at click time",
    ),
    KnownFailureClass(
        failure_id="interrupted_tier2",
        stage="tier2_generation",
        typed_error="Tier2OrchestrationError|process_restart",
        customer_safe=True,
        retryable=True,
        deterministic_repair=False,
        requires_regeneration=True,
        existing_test=None,
        fixture_strategy="inject process_restart mid tier2",
        notes="No durable resume of in-flight Tier2 AI stages",
    ),
    KnownFailureClass(
        failure_id="migration_readiness",
        stage="migration_startup",
        typed_error="StartupMigrationError|not_ready",
        customer_safe=True,
        retryable=True,
        deterministic_repair=False,
        requires_regeneration=False,
        existing_test="tests/commercial/test_migration_startup_safety.py",
        fixture_strategy="DB missing required versions/tables",
        notes="Health ready gate",
    ),
)


__all__ = ["KNOWN_FAILURES", "KnownFailureClass"]
