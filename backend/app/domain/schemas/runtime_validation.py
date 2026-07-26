"""Strict Phase 4 build and deterministic runtime-validation artifacts."""
from __future__ import annotations

from typing import Literal, Tuple

from pydantic import Field, StrictBool, StrictFloat, StrictInt, model_validator

from app.domain.schemas.composition_contract import Identifier
from app.domain.schemas.design_contract import Sha256, StrictDesignModel


RUNTIME_VALIDATION_SCHEMA_VERSION = "1.0"
RUNTIME_VALIDATION_POLICY_REVISION = "2026-07-24.1"
BASELINE_ACCESSIBILITY_SCANNER = "BaselineAccessibilityScanner"
BASELINE_ACCESSIBILITY_POLICY_REVISION = "2026-07-24.1"

RuntimeTerminalStatus = Literal[
    "candidate_runtime_validated",
    "candidate_build_failed",
    "candidate_runtime_failed",
]
Phase4FailureCode = Literal[
    "package_manifest_invalid",
    "dependency_install_failed",
    "dependency_missing",
    "dependency_version_conflict",
    "typescript_compile_failed",
    "vite_build_failed",
    "import_resolution_failed",
    "export_symbol_missing",
    "route_missing",
    "preview_server_failed",
    "browser_launch_failed",
    "browser_navigation_failed",
    "runtime_console_error",
    "runtime_unhandled_exception",
    "runtime_network_failure",
    "required_element_missing",
    "required_interaction_failed",
    "accessibility_failed",
    "screenshot_failed",
    "runtime_evidence_persistence_failed",
    "runtime_timeout",
]
ViewportName = Literal["mobile", "tablet", "desktop"]
FindingSeverity = Literal["info", "minor", "moderate", "serious", "critical"]


class RuntimeValidationRefs(StrictDesignModel):
    request_id: StrictInt = Field(ge=1)
    candidate_revision_id: StrictInt = Field(ge=1)
    candidate_revision_uuid: str = Field(
        min_length=36,
        max_length=36,
        pattern=(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
            r"[0-9a-f]{4}-[0-9a-f]{12}$"
        ),
    )
    candidate_manifest_sha256: Sha256
    dependency_lock_sha256: Sha256
    candidate_generator_version: str = Field(min_length=1, max_length=48)
    candidate_policy_revision: str = Field(min_length=1, max_length=64)
    runtime_policy_revision: str = Field(
        default=RUNTIME_VALIDATION_POLICY_REVISION,
        pattern=r"^2026-07-24\.1$",
    )


class RuntimeToolVersions(StrictDesignModel):
    node: str = Field(min_length=1, max_length=80)
    npm: str = Field(default="unrecorded", min_length=1, max_length=80)
    platform: str = Field(default="unrecorded", min_length=1, max_length=240)
    python: str = Field(default="unrecorded", min_length=1, max_length=120)
    typescript: str = Field(min_length=1, max_length=80)
    vite: str = Field(min_length=1, max_length=80)
    playwright: str = Field(min_length=1, max_length=80)
    browser_name: str = Field(min_length=1, max_length=80)
    browser_version: str = Field(min_length=1, max_length=120)
    accessibility_scanner: str = Field(
        default=BASELINE_ACCESSIBILITY_SCANNER,
        pattern=r"^BaselineAccessibilityScanner$",
    )
    accessibility_policy_revision: str = Field(
        default=BASELINE_ACCESSIBILITY_POLICY_REVISION,
        pattern=r"^2026-07-24\.1$",
    )
    network_guard_revision: str = Field(
        default="2026-07-24.1",
        pattern=r"^2026-07-24\.1$",
    )


class RuntimeLimits(StrictDesignModel):
    typescript_timeout_seconds: StrictInt = Field(ge=1, le=600)
    vite_build_timeout_seconds: StrictInt = Field(ge=1, le=600)
    build_stage_timeout_seconds: StrictInt = Field(ge=1, le=1200)
    server_startup_timeout_seconds: StrictInt = Field(ge=1, le=120)
    route_timeout_seconds: StrictInt = Field(ge=1, le=120)
    journey_timeout_seconds: StrictInt = Field(ge=1, le=180)
    accessibility_timeout_seconds: StrictInt = Field(ge=1, le=120)
    screenshot_timeout_seconds: StrictInt = Field(ge=1, le=120)
    phase_timeout_seconds: StrictInt = Field(ge=1, le=3600)
    max_browser_contexts: StrictInt = Field(ge=1, le=8)
    max_browser_pages: StrictInt = Field(ge=1, le=8)
    max_console_diagnostics: StrictInt = Field(ge=1, le=1000)
    max_network_diagnostics: StrictInt = Field(ge=1, le=1000)
    max_command_output_bytes: StrictInt = Field(ge=1024, le=1_048_576)
    max_deterministic_repairs: StrictInt = Field(ge=0, le=1)
    max_dist_bytes: StrictInt = Field(ge=1)
    max_javascript_bytes: StrictInt = Field(ge=1)
    max_css_bytes: StrictInt = Field(ge=1)
    max_dist_files: StrictInt = Field(ge=1)
    max_source_maps: StrictInt = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _build_budget_is_consistent(self) -> "RuntimeLimits":
        if self.build_stage_timeout_seconds < max(
            self.typescript_timeout_seconds,
            self.vite_build_timeout_seconds,
        ):
            raise ValueError("Combined build timeout is too small")
        return self


class ViewportContract(StrictDesignModel):
    name: ViewportName
    width: StrictInt = Field(ge=320, le=4096)
    height: StrictInt = Field(ge=480, le=4096)
    touch: StrictBool


class CommandResult(StrictDesignModel):
    command_name: Literal[
        "network_guard_verification",
        "typescript_build",
        "vite_build",
        "vite_preview",
    ]
    argv: Tuple[str, ...] = Field(min_length=1, max_length=32)
    exit_code: StrictInt
    timed_out: StrictBool
    duration_ms: StrictInt = Field(ge=0)
    stdout_summary: str = Field(default="", max_length=70_000)
    stderr_summary: str = Field(default="", max_length=70_000)
    stdout_sha256: Sha256
    stderr_sha256: Sha256


class DistFileRecord(StrictDesignModel):
    path: str = Field(min_length=1, max_length=300)
    sha256: Sha256
    byte_count: StrictInt = Field(ge=0)
    media_kind: Literal[
        "html",
        "javascript",
        "css",
        "image",
        "font",
        "json",
        "other",
    ]


class BuildValidationResult(StrictDesignModel):
    schema_version: str = Field(
        default=RUNTIME_VALIDATION_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    refs: RuntimeValidationRefs
    build_cache_key: Sha256
    dist_cache_key: Sha256
    passed: StrictBool
    dist_validation_passed: StrictBool
    cache_hit: StrictBool
    deterministic_repair_count: StrictInt = Field(ge=0, le=1)
    derived_from_build_attempt_id: StrictInt | None = Field(default=None, ge=1)
    source_candidate_sha256_before: Sha256
    source_candidate_sha256_after: Sha256
    dependency_runtime_sha256_before: Sha256
    dependency_runtime_sha256_after: Sha256
    network_guard_verified: StrictBool
    build_hash: Sha256
    dist_manifest_sha256: Sha256
    dist_files: Tuple[DistFileRecord, ...] = Field(default=(), max_length=200)
    commands: Tuple[CommandResult, ...] = Field(default=(), max_length=4)
    failure_code: Phase4FailureCode | None = None
    first_error_location: str | None = Field(default=None, max_length=500)
    diagnostics: Tuple[str, ...] = Field(default=(), max_length=200)
    duration_ms: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def _passing_build_is_complete(self) -> "BuildValidationResult":
        if self.passed and (
            not self.dist_validation_passed
            or not self.network_guard_verified
            or not self.dist_files
            or self.diagnostics
            or self.source_candidate_sha256_before
            != self.source_candidate_sha256_after
            or self.dependency_runtime_sha256_before
            != self.dependency_runtime_sha256_after
        ):
            raise ValueError("Passing build result is incomplete")
        if not self.passed and not self.diagnostics:
            raise ValueError("Failing build result needs diagnostics")
        return self


class RouteViewportResult(StrictDesignModel):
    schema_version: str = Field(
        default=RUNTIME_VALIDATION_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    refs: RuntimeValidationRefs
    cache_key: Sha256
    build_hash: Sha256
    page_id: Identifier
    route: str = Field(min_length=1, max_length=300)
    viewport: ViewportName
    passed: StrictBool
    page_loaded: StrictBool
    page_marker_verified: StrictBool
    role_marker_verified: StrictBool
    component_markers_verified: StrictBool
    contract_hooks_verified: StrictBool
    reload_verified: StrictBool
    direct_navigation_verified: StrictBool
    history_verified: StrictBool
    overflow_verified: StrictBool
    clipping_verified: StrictBool
    primary_action_reachable: StrictBool
    mobile_bindings_verified: StrictBool
    console_errors: Tuple[str, ...] = Field(default=(), max_length=100)
    page_errors: Tuple[str, ...] = Field(default=(), max_length=100)
    request_failures: Tuple[str, ...] = Field(default=(), max_length=100)
    diagnostics: Tuple[str, ...] = Field(default=(), max_length=200)
    duration_ms: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def _passing_route_is_complete(self) -> "RouteViewportResult":
        checks = (
            self.page_loaded,
            self.page_marker_verified,
            self.role_marker_verified,
            self.component_markers_verified,
            self.contract_hooks_verified,
            self.reload_verified,
            self.direct_navigation_verified,
            self.history_verified,
            self.overflow_verified,
            self.clipping_verified,
            self.primary_action_reachable,
            self.mobile_bindings_verified,
        )
        if self.passed and (
            not all(checks)
            or self.console_errors
            or self.page_errors
            or self.request_failures
            or self.diagnostics
        ):
            raise ValueError("Passing route result is incomplete")
        if not self.passed and not (
            self.diagnostics
            or self.console_errors
            or self.page_errors
            or self.request_failures
        ):
            raise ValueError("Failing route result needs diagnostics")
        return self


class JourneyStepResult(StrictDesignModel):
    step: Literal[
        "navigate",
        "initial_state",
        "input",
        "action",
        "transition",
        "resulting_state",
        "evidence",
        "acceptance_assertion",
        "reduced_motion",
    ]
    canonical_id: Identifier
    passed: StrictBool
    selector: str = Field(default="", max_length=500)
    expected: str = Field(default="", max_length=1000)
    observed: str = Field(default="", max_length=2000)


class JourneyValidationResult(StrictDesignModel):
    schema_version: str = Field(
        default=RUNTIME_VALIDATION_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    refs: RuntimeValidationRefs
    cache_key: Sha256
    build_hash: Sha256
    journey_id: Identifier
    action_id: Identifier
    acceptance_test_ids: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=200,
    )
    route: str = Field(min_length=1, max_length=300)
    passed: StrictBool
    reduced_motion_required: StrictBool
    reduced_motion_passed: StrictBool
    steps: Tuple[JourneyStepResult, ...] = Field(min_length=1, max_length=500)
    diagnostics: Tuple[str, ...] = Field(default=(), max_length=200)
    duration_ms: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def _journey_consistency(self) -> "JourneyValidationResult":
        if self.passed and (
            any(not step.passed for step in self.steps)
            or self.diagnostics
            or (
                self.reduced_motion_required
                and not self.reduced_motion_passed
            )
        ):
            raise ValueError("Passing journey result is incomplete")
        if not self.passed and not self.diagnostics:
            raise ValueError("Failing journey needs diagnostics")
        return self


class AccessibilityFinding(StrictDesignModel):
    rule_id: str = Field(min_length=1, max_length=120)
    severity: FindingSeverity
    selector: str = Field(min_length=1, max_length=1000)
    diagnostic_evidence: str = Field(min_length=1, max_length=4000)


class AccessibilityRouteResult(StrictDesignModel):
    schema_version: str = Field(
        default=RUNTIME_VALIDATION_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    refs: RuntimeValidationRefs
    cache_key: Sha256
    build_hash: Sha256
    scanner_name: str = Field(
        default=BASELINE_ACCESSIBILITY_SCANNER,
        pattern=r"^BaselineAccessibilityScanner$",
    )
    scanner_policy_revision: str = Field(
        default=BASELINE_ACCESSIBILITY_POLICY_REVISION,
        pattern=r"^2026-07-24\.1$",
    )
    page_id: Identifier
    route: str = Field(min_length=1, max_length=300)
    viewport: ViewportName
    passed: StrictBool
    findings: Tuple[AccessibilityFinding, ...] = Field(
        default=(),
        max_length=500,
    )
    duration_ms: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def _severity_policy(self) -> "AccessibilityRouteResult":
        blocking = any(
            item.severity in {"serious", "critical"}
            for item in self.findings
        )
        if self.passed == blocking:
            raise ValueError("Accessibility severity policy is inconsistent")
        return self


class ScreenshotEvidence(StrictDesignModel):
    schema_version: str = Field(
        default=RUNTIME_VALIDATION_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    refs: RuntimeValidationRefs
    cache_key: Sha256
    build_hash: Sha256
    page_id: Identifier
    route: str = Field(min_length=1, max_length=300)
    viewport: ViewportName
    relative_path: str = Field(min_length=1, max_length=500)
    sha256: Sha256
    byte_count: StrictInt = Field(ge=1)
    browser_version: str = Field(min_length=1, max_length=120)
    capture_policy_revision: str = Field(
        default="2026-07-24.1",
        pattern=r"^2026-07-24\.1$",
    )
    captured_at: str = Field(min_length=20, max_length=40)


class RuntimeValidationSummary(StrictDesignModel):
    schema_version: str = Field(
        default=RUNTIME_VALIDATION_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    refs: RuntimeValidationRefs
    attempt_uuid: str = Field(min_length=36, max_length=36)
    status: RuntimeTerminalStatus
    source_candidate_sha256_before: Sha256
    source_candidate_sha256_after: Sha256
    build_result_sha256: Sha256
    route_result_hashes: Tuple[Sha256, ...] = Field(default=(), max_length=300)
    journey_result_hashes: Tuple[Sha256, ...] = Field(
        default=(),
        max_length=500,
    )
    accessibility_result_hashes: Tuple[Sha256, ...] = Field(
        default=(),
        max_length=300,
    )
    screenshot_hashes: Tuple[Sha256, ...] = Field(default=(), max_length=300)
    expected_route_viewport_count: StrictInt = Field(ge=0)
    expected_journey_count: StrictInt = Field(ge=0)
    all_required_gates_passed: StrictBool
    server_identity_verified: StrictBool
    cache_hits: Tuple[str, ...] = Field(default=(), max_length=10)
    server_command: CommandResult | None = None
    network_diagnostics: Tuple[str, ...] = Field(default=(), max_length=100)
    failure_stage: str | None = Field(default=None, max_length=80)
    failure_code: Phase4FailureCode | None = None
    first_error_location: str | None = Field(default=None, max_length=500)
    diagnostics: Tuple[str, ...] = Field(default=(), max_length=300)
    duration_ms: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def _terminal_invariants(self) -> "RuntimeValidationSummary":
        if self.status == "candidate_runtime_validated":
            if (
                not self.all_required_gates_passed
                or not self.server_identity_verified
                or self.source_candidate_sha256_before
                != self.source_candidate_sha256_after
                or self.failure_stage
                or self.diagnostics
                or len(self.route_result_hashes)
                != self.expected_route_viewport_count
                or len(self.accessibility_result_hashes)
                != self.expected_route_viewport_count
                or len(self.screenshot_hashes)
                != self.expected_route_viewport_count
                or len(self.journey_result_hashes)
                != self.expected_journey_count
            ):
                raise ValueError("Runtime-validated summary is incomplete")
        elif self.all_required_gates_passed or not self.failure_stage:
            raise ValueError("Failure summary lacks a failure stage")
        return self


__all__ = [
    "AccessibilityFinding",
    "AccessibilityRouteResult",
    "BASELINE_ACCESSIBILITY_POLICY_REVISION",
    "BASELINE_ACCESSIBILITY_SCANNER",
    "BuildValidationResult",
    "CommandResult",
    "DistFileRecord",
    "FindingSeverity",
    "JourneyStepResult",
    "JourneyValidationResult",
    "Phase4FailureCode",
    "RUNTIME_VALIDATION_POLICY_REVISION",
    "RUNTIME_VALIDATION_SCHEMA_VERSION",
    "RouteViewportResult",
    "RuntimeLimits",
    "RuntimeTerminalStatus",
    "RuntimeToolVersions",
    "RuntimeValidationRefs",
    "RuntimeValidationSummary",
    "ScreenshotEvidence",
    "ViewportContract",
    "ViewportName",
]
