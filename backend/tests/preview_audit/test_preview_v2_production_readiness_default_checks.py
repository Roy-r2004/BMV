from __future__ import annotations

import importlib.util
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from types import ModuleType

import pytest

from app.core.config import settings
from app.domain.models.expanded_preview import (
    ExpandedPreviewGenerationClaimRecord,
    ExpandedPreviewRequestRecord,
)
from app.domain.models.preview_candidate import CandidateRevisionRecord
from app.domain.models.request import Request
from app.domain.models.runtime_validation import (
    CandidateAccessibilityFindingRecord,
    CandidateBuildAttemptRecord,
    CandidateJourneyResultRecord,
    CandidateRouteResultRecord,
    CandidateRuntimeValidationAttemptRecord,
    CandidateScreenshotRecord,
    CandidateValidationSummaryRecord,
)
from app.domain.models.visual_evaluation import (
    CandidateVisualEvaluationAttemptRecord,
    CandidateVisualSummaryRecord,
)
from app.infrastructure.ai_providers.model_capabilities import (
    APPROVED_CANDIDATE_COMPONENT_MODEL,
    APPROVED_CANDIDATE_PAGE_MODEL,
    CAPABILITY_PROFILE_REVISION,
    CONTEXT_RESERVE_TOKENS,
    MINIMUM_VALID_OUTPUT_TOKENS,
)
from app.application.candidate_generation.cache import canonical_sha256
from app.application.runtime_validation.cache import artifact_sha256, sha256_file
from app.infrastructure.db.session import SessionLocal


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "cli" / "preview_v2_production_readiness.py"
EXPECTED_VARIANT_IDS = [
    "small_three_page",
    "exact_five_page_booking",
    "long_description_booking",
    "larger_service_catalog_booking",
    "maximum_supported_tier1",
]
EXPECTED_SOURCE_IDENTITY_PATHS = {
    "backend/scripts/cli/preview_v2_production_readiness.py",
    "backend/app/infrastructure/ai_providers/model_capabilities.py",
    "backend/app/application/candidate_generation/builder.py",
    "backend/app/application/candidate_generation/service.py",
    "backend/app/application/candidate_generation/call_budget.py",
    "backend/app/application/candidate_generation/policy.py",
    "backend/app/application/candidate_generation/deterministic.py",
    "backend/app/application/candidate_generation/validation.py",
    "backend/app/application/runtime_validation/prebuild.py",
    "backend/app/templates/prompts/v2_candidate_components.j2",
    "backend/app/templates/prompts/v2_candidate_pages.j2",
    "backend/app/templates/prompts/v2_candidate_repair.j2",
    "backend/tests/composition_contract/helpers.py",
    "backend/tests/preview_contract/test_preview_tiers.py",
}
EXPECTED_SAFE_OUTPUT_TOKENS = {
    "business_components": 24_000,
    "pages": 32_000,
}
VISUAL_DIMENSIONS = (
    "business_specificity",
    "product_story_clarity",
    "hierarchy_and_composition",
    "visual_coherence",
    "design_dna_adherence",
    "content_credibility",
    "interaction_clarity",
    "conversion_strength",
    "mobile_quality",
    "responsive_consistency",
    "density_and_readability",
    "evidence_visibility",
    "novelty",
    "trust_and_professionalism",
)


def _load_script_module() -> ModuleType:
    if not SCRIPT_PATH.is_file():
        pytest.fail(
            "expected preview readiness driver at "
            f"{SCRIPT_PATH.as_posix()}"
        )
    spec = importlib.util.spec_from_file_location(
        "preview_v2_production_readiness_default_checks",
        SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:
        pytest.fail("failed to build import spec for preview readiness driver")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _patch_required_settings(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "V2_CANDIDATE_COMPONENT_MODEL", APPROVED_CANDIDATE_COMPONENT_MODEL)
    monkeypatch.setattr(settings, "V2_CANDIDATE_PAGE_MODEL", APPROVED_CANDIDATE_PAGE_MODEL)
    monkeypatch.setattr(settings, "V2_CANDIDATE_MAX_CALLS", 4)
    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_ENABLED", False)
    monkeypatch.setattr(settings, "V2_PHASE7_ROLLOUT_ENABLED", False)
    monkeypatch.setattr(settings, "V2_PHASE7_PROMOTE_ENABLED", False)
    monkeypatch.setattr(settings, "V2_PHASE7_PERCENT_SERVE_ENABLED", False)
    monkeypatch.setattr(settings, "V2_PHASE7_ROLLOUT_PERCENT", 0)
    monkeypatch.setattr(settings, "V2_PHASE7_CONFIG_VALID", True)
    monkeypatch.setattr(settings, "V2_RUNTIME_VALIDATION_ENABLED", True)
    monkeypatch.setattr(settings, "V2_VISUAL_EVALUATION_ENABLED", True)
    monkeypatch.setattr(settings, "APPSPEC_MODEL", "google/gemini-2.5-flash")
    monkeypatch.setattr(settings, "APPSPEC_REPAIR_MODEL", "google/gemini-2.5-flash")
    monkeypatch.setattr(settings, "APPSPEC_COVERAGE_MODEL", "deepseek/deepseek-chat")
    monkeypatch.setattr(settings, "APPSPEC_V2_COVERAGE_MODEL", "deepseek/deepseek-chat")
    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite:///./buildmyversion.db")
    monkeypatch.setattr(settings, "PREVIEW_CANDIDATES_DIR", tmp_path / "candidates")
    monkeypatch.setattr(settings, "PREVIEW_APPS_DIR", tmp_path / "accepted")


def _valid_preflight_report(module, report_path: Path) -> dict:
    report = module._build_report(report_path)
    report["configuration"] = {
        "status": "pass",
        "component_model": APPROVED_CANDIDATE_COMPONENT_MODEL,
        "page_model": APPROVED_CANDIDATE_PAGE_MODEL,
        "capability_profile_revision": CAPABILITY_PROFILE_REVISION,
        "context_window": 1_048_576,
        "supports_json_text_mode": True,
        "minimum_output_allowance": 4_000,
        "context_reserve": 512,
        "candidate_call_cap_total": 4,
        "candidate_call_cap_components": 2,
        "candidate_call_cap_pages": 2,
        "appspec_fallback_enabled": False,
        "appspec_fallback_configuration": {
            "configuration_valid": True,
            "safety_code": "ok",
            "configuration_source": "env",
        },
        "phase7_config_valid": True,
        "phase4_enabled": True,
        "phase5_enabled": True,
        "blockers": [],
    }
    report["docker_environment"] = {
        "status": "deferred_to_production_image",
        "host_environment": True,
        "production_image_required": True,
        "blockers": ["/app-only validation deferred to production image"],
    }
    report["deterministic_suites"] = {
        "status": "pass",
        "variant_ids": EXPECTED_VARIANT_IDS,
        "variant_count": 5,
    }
    report["prompt_variants"] = {
        "status": "pass",
        "variant_count": 5,
        "variants": [
            {
                "variant_id": "small_three_page",
                "prompt_hashes": {
                    "business_components": "a" * 64,
                    "pages": "b" * 64,
                },
                "prompt_char_counts": {"business_components": 3000},
                "prompt_token_estimates": {"business_components": 1000},
                "final_candidate_status": "candidate_build_pending",
                "full_description_omitted": True,
                "seeded_record_count": 3,
                "page_count": 3,
            },
            {
                "variant_id": "exact_five_page_booking",
                "prompt_hashes": {
                    "business_components": "c" * 64,
                    "pages": "d" * 64,
                },
                "prompt_char_counts": {"business_components": 5000},
                "prompt_token_estimates": {"business_components": 1600},
                "final_candidate_status": "candidate_build_pending",
                "full_description_omitted": True,
                "seeded_record_count": 5,
                "page_count": 5,
            },
            {
                "variant_id": "long_description_booking",
                "prompt_hashes": {
                    "business_components": "e" * 64,
                    "pages": "f" * 64,
                },
                "prompt_char_counts": {"business_components": 5005},
                "prompt_token_estimates": {"business_components": 1602},
                "long_description_chars": 12000,
                "final_candidate_status": "candidate_build_pending",
                "full_description_omitted": True,
                "seeded_record_count": 5,
                "page_count": 5,
            },
            {
                "variant_id": "larger_service_catalog_booking",
                "prompt_hashes": {
                    "business_components": "1" * 64,
                    "pages": "2" * 64,
                },
                "prompt_char_counts": {"business_components": 6500},
                "prompt_token_estimates": {"business_components": 2100},
                "final_candidate_status": "candidate_build_pending",
                "full_description_omitted": True,
                "seeded_record_count": 9,
                "page_count": 8,
            },
            {
                "variant_id": "maximum_supported_tier1",
                "prompt_hashes": {
                    "business_components": "3" * 64,
                    "pages": "4" * 64,
                },
                "prompt_char_counts": {"business_components": 9000},
                "prompt_token_estimates": {"business_components": 3000},
                "final_candidate_status": "candidate_build_pending",
                "full_description_omitted": True,
                "seeded_record_count": 13,
                "page_count": 13,
            },
        ],
        "blockers": [],
    }
    report["model_preflights"] = {
        "status": "pass",
        "variants": {
            variant_id: {
                "business_components": {
                    "capability_profile_revision": CAPABILITY_PROFILE_REVISION,
                    "context_window": 1_048_576,
                    "estimated_input_tokens": 12_345,
                    "requested_output_tokens": 24_000,
                    "clamped_output_tokens": 24_000,
                    "minimum_output_allowance": 4_000,
                    "context_reserve": 512,
                    "approval_decision": "approved_preflight",
                    "typed_result": "preflight_passed",
                },
                "pages": {
                    "capability_profile_revision": CAPABILITY_PROFILE_REVISION,
                    "context_window": 1_048_576,
                    "estimated_input_tokens": 22_345,
                    "requested_output_tokens": 32_000,
                    "clamped_output_tokens": 32_000,
                    "minimum_output_allowance": 4_000,
                    "context_reserve": 512,
                    "approval_decision": "approved_preflight",
                    "typed_result": "preflight_passed",
                },
            }
            for variant_id in EXPECTED_VARIANT_IDS
        },
        "blockers": [],
    }
    report["phase3a"] = {
        "status": "pass",
        "variants": {
            variant_id: {
                "artifact_ids": [f"{variant_id}-page-purpose"],
                "provider_call_count": 0,
                "evidence": "fixture-backed phase3a artifacts",
            }
            for variant_id in EXPECTED_VARIANT_IDS
        },
    }
    report["provider_calls"] = {"status": "pass", "total_used": 2, "components_used": 1, "pages_used": 1}
    report["candidate_generation"] = {
        "status": "pass",
        "variants": [
            {"variant_id": item["variant_id"], "status": "candidate_build_pending"}
            for item in report["prompt_variants"]["variants"]
        ],
    }
    report["call_budgets"] = {"status": "pass", "total_cap": 4, "components_cap": 2, "pages_cap": 2}
    report["checkpoints"] = {
        "status": "pass",
        "variants": {
            variant_id: {
                "foundation": "completed",
                "data_exports": "completed",
                "business_components": "completed",
                "pages": "completed",
            }
            for variant_id in EXPECTED_VARIANT_IDS
        },
    }
    report["generated_code_validation"] = {
        "status": "pass",
        "static_gate_pass_count": 5,
    }
    report["restart_resume"] = {
        "status": "pass",
        "source": "release_gate_deterministic_suite",
        "marker": "BMV_READINESS_RESTART_RESUME_PASSED",
    }
    report["required_next_action"] = "run_real_http_flow"
    return report


def _bound_preflight_report(module, report_path: Path) -> tuple[dict, str]:
    binder = getattr(module, "_bind_preflight_report_artifact", None)
    if binder is None:
        pytest.fail("driver must expose _bind_preflight_report_artifact")
    report = _valid_preflight_report(module, report_path)
    bound = binder(report)
    return bound, bound["artifacts"]["preflight_report_sha256"]


def test_configuration_check_requires_exact_candidate_and_phase_settings(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_script_module()
    checker = getattr(module, "_run_configuration_check", None)
    if checker is None:
        pytest.fail("driver must expose _run_configuration_check")

    _patch_required_settings(monkeypatch, tmp_path)
    good = checker()
    assert good["configuration"]["status"] == "pass"
    assert good["configuration"]["component_model"] == APPROVED_CANDIDATE_COMPONENT_MODEL
    assert good["configuration"]["page_model"] == APPROVED_CANDIDATE_PAGE_MODEL
    assert good["configuration"]["capability_profile_revision"] == CAPABILITY_PROFILE_REVISION
    assert good["configuration"]["context_window"] == 1_048_576
    assert good["configuration"]["supports_json_text_mode"] is True
    assert good["configuration"]["minimum_output_allowance"] == MINIMUM_VALID_OUTPUT_TOKENS
    assert good["configuration"]["context_reserve"] == CONTEXT_RESERVE_TOKENS
    assert good["configuration"]["candidate_call_cap_total"] == 4
    assert good["configuration"]["candidate_call_cap_components"] == 2
    assert good["configuration"]["candidate_call_cap_pages"] == 2
    assert good["configuration"]["appspec_fallback_enabled"] is False
    assert good["configuration"]["appspec_fallback_configuration"]["safety_code"] == "ok"
    assert good["configuration"]["appspec_fallback_configuration"]["configuration_valid"] is True
    assert good["configuration"]["phase7_config_valid"] is True
    assert good["configuration"]["phase4_enabled"] is True
    assert good["configuration"]["phase5_enabled"] is True
    assert (
        good["configuration"]["appspec_model_families"]["coverage"]
        == "deepseek"
    )

    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_ENABLED", True)
    bad = checker()
    assert bad["configuration"]["status"] == "fail"
    assert "APPSPEC_FALLBACK_ENABLED" in " ".join(bad["configuration"]["blockers"])

    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_ENABLED", False)
    monkeypatch.setattr(settings, "V2_PHASE7_CONFIG_VALID", False)
    phase7_bad = checker()
    assert phase7_bad["configuration"]["status"] == "fail"
    assert "V2_PHASE7_CONFIG_VALID" in " ".join(
        phase7_bad["configuration"]["blockers"]
    )


def test_configuration_check_rejects_appspec_family_collision(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_script_module()
    checker = getattr(module, "_run_configuration_check", None)
    if checker is None:
        pytest.fail("driver must expose _run_configuration_check")

    _patch_required_settings(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "APPSPEC_COVERAGE_MODEL", "google/gemini-2.5-flash")
    monkeypatch.setattr(settings, "APPSPEC_V2_COVERAGE_MODEL", "google/gemini-2.5-flash")

    report = checker()["configuration"]
    assert report["status"] == "fail"
    assert report["appspec_models"]["author"] == "google/gemini-2.5-flash"
    assert report["appspec_models"]["coverage"] == "google/gemini-2.5-flash"
    assert report["appspec_model_families"]["author"] == "google"
    assert report["appspec_model_families"]["coverage"] == "google"
    assert "different model family" in " ".join(report["blockers"])


def test_prompt_variants_use_real_candidate_flow_and_record_preflights(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_script_module()
    runner = getattr(module, "_run_prompt_variants_check", None)
    if runner is None:
        pytest.fail("driver must expose _run_prompt_variants_check")

    _patch_required_settings(monkeypatch, tmp_path)
    monkeypatch.setenv("BMV_READINESS_RESTART_RESUME_PASSED", "1")
    update = runner()

    variants = update["prompt_variants"]["variants"]
    assert update["prompt_variants"]["status"] == "pass"
    assert [item["variant_id"] for item in variants] == EXPECTED_VARIANT_IDS
    assert "prompt_text" not in json.dumps(update)
    component_chars = {
        item["variant_id"]: item["prompt_char_counts"]["business_components"]
        for item in variants
    }
    component_tokens = {
        item["variant_id"]: item["prompt_token_estimates"]["business_components"]
        for item in variants
    }

    for item in variants:
        assert item["final_candidate_status"] == "candidate_build_pending"
        assert item["static_gate"]["status"] == "pass"
        assert item["prompt_char_counts"]["business_components"] > 0
        assert item["prompt_token_estimates"]["business_components"] > 0
        assert len(item["prompt_hashes"]["business_components"]) == 64
        assert item["call_budget"]["total_max"] == 4
        assert item["call_budget"]["substage_caps"]["business_components"] == 2
        assert item["call_budget"]["substage_caps"]["pages"] == 2
        assert set(item["checkpoints"]) >= {
            "foundation",
            "data_exports",
            "business_components",
            "pages",
        }
        assert item["phase3a_artifact_count"] >= 1

    exact = update["model_preflights"]["variants"]["exact_five_page_booking"]
    assert exact["business_components"]["capability_profile_revision"] == CAPABILITY_PROFILE_REVISION
    assert exact["business_components"]["requested_output_tokens"] == 24_000
    assert exact["business_components"]["clamped_output_tokens"] == 24_000
    assert exact["business_components"]["context_window"] == 1_048_576
    assert exact["business_components"]["minimum_output_allowance"] == 4_000
    assert exact["business_components"]["context_reserve"] == 512
    assert exact["business_components"]["approval_decision"] == "approved_preflight"
    assert exact["business_components"]["typed_result"] == "preflight_passed"
    assert exact["pages"]["context_window"] == 1_048_576
    assert exact["pages"]["requested_output_tokens"] == 32_000
    assert exact["pages"]["clamped_output_tokens"] == 32_000
    assert update["provider_calls"]["status"] == "pass"
    assert update["provider_calls"]["total_used"] <= 4
    assert update["generated_code_validation"]["status"] == "pass"
    assert update["generated_code_validation"]["static_gate_pass_count"] == 5
    assert update["phase3a"]["status"] == "pass"
    assert update["restart_resume"]["status"] == "pass"
    assert update["restart_resume"]["source"] == "release_gate_deterministic_suite"
    assert (
        component_chars["small_three_page"]
        < component_chars["exact_five_page_booking"]
        < component_chars["larger_service_catalog_booking"]
        < component_chars["maximum_supported_tier1"]
    )
    assert (
        component_tokens["small_three_page"]
        < component_tokens["exact_five_page_booking"]
        < component_tokens["larger_service_catalog_booking"]
        < component_tokens["maximum_supported_tier1"]
    )
    assert (
        component_chars["long_description_booking"]
        <= component_chars["exact_five_page_booking"] + 256
    )
    assert (
        component_tokens["long_description_booking"]
        <= component_tokens["exact_five_page_booking"] + 128
    )
    exact_variant = next(
        item for item in variants if item["variant_id"] == "exact_five_page_booking"
    )
    larger_variant = next(
        item for item in variants if item["variant_id"] == "larger_service_catalog_booking"
    )
    maximum_variant = next(
        item for item in variants if item["variant_id"] == "maximum_supported_tier1"
    )
    assert larger_variant["seeded_record_count"] > exact_variant["seeded_record_count"]
    assert (
        larger_variant["prompt_token_estimates"]["business_components"]
        > exact_variant["prompt_token_estimates"]["business_components"]
    )
    assert maximum_variant["page_count"] == max(item["page_count"] for item in variants)
    assert (
        maximum_variant["prompt_token_estimates"]["business_components"]
        == max(item["prompt_token_estimates"]["business_components"] for item in variants)
    )

    for variant_id in EXPECTED_VARIANT_IDS:
        for stage_name, expected_tokens in EXPECTED_SAFE_OUTPUT_TOKENS.items():
            stage = update["model_preflights"]["variants"][variant_id][stage_name]
            assert stage["capability_profile_revision"] == CAPABILITY_PROFILE_REVISION
            assert stage["context_window"] == 1_048_576
            assert stage["requested_output_tokens"] == expected_tokens
            assert stage["clamped_output_tokens"] == expected_tokens
            assert stage["estimated_input_tokens"] >= 1
            assert stage["minimum_output_allowance"] >= 4_000
            assert stage["context_reserve"] == 512
            assert stage["approval_decision"] == "approved_preflight"
            assert stage["typed_result"] == "preflight_passed"


def test_preflight_only_cli_runs_default_checks_and_stays_not_ready(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_script_module()
    _patch_required_settings(monkeypatch, tmp_path)
    if not hasattr(module, "_run_docker_environment_check"):
        pytest.fail("driver must expose _run_docker_environment_check")

    monkeypatch.setattr(
        module,
        "_run_docker_environment_check",
        lambda **_kwargs: {
            "docker_environment": {
                "status": "deferred_to_production_image",
                "python_available": True,
                "node_available": True,
                "npm_available": True,
                "playwright_available": True,
                "chromium_available": True,
                "sqlite_url": "sqlite:///./buildmyversion.db",
                "app_paths_valid": False,
                "host_environment": True,
                "production_image_required": True,
                "tool_versions": {
                    "python": "3.12.10",
                    "node": "v22.0.0",
                    "npm": "10.0.0",
                    "playwright": "1.55.0",
                    "chromium": "138.0.0",
                },
                "timeouts": {
                    "typescript": settings.V2_RUNTIME_TYPESCRIPT_TIMEOUT_SECONDS,
                    "vite_build": settings.V2_RUNTIME_VITE_BUILD_TIMEOUT_SECONDS,
                    "server": settings.V2_RUNTIME_SERVER_TIMEOUT_SECONDS,
                },
                "blockers": ["/app-only validation deferred to production image"],
            }
        },
    )

    report_path = tmp_path / f"preflight-{uuid.uuid4().hex}.json"
    exit_code = module.main(
        ["--preflight-only", "--report-path", str(report_path)]
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code != 0
    assert report["configuration"]["status"] == "pass"
    assert report["docker_environment"]["status"] == "deferred_to_production_image"
    assert report["docker_environment"]["host_environment"] is True
    assert report["docker_environment"]["production_image_required"] is True
    assert report["prompt_variants"]["status"] == "pass"
    assert (
        report["restart_resume"]["status"]
        == "deferred_external_deterministic_suite"
    )
    assert report["phase4"]["status"] == "fail"
    assert report["phase5"]["status"] == "fail"
    assert report["required_next_action"] == "run_real_http_flow"
    assert report["artifacts"]["preflight_report_sha256"]


def test_docker_environment_detects_playwright_managed_chromium(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_script_module()
    _patch_required_settings(monkeypatch, tmp_path)

    class _Chromium:
        def executable_path(self) -> str:
            return str(tmp_path / "ms-playwright" / "chromium" / "chrome")

    class _PlaywrightContext:
        chromium = _Chromium()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    chromium_path = tmp_path / "ms-playwright" / "chromium" / "chrome"
    chromium_path.parent.mkdir(parents=True, exist_ok=True)
    chromium_path.write_text("binary", encoding="utf-8")

    monkeypatch.setattr(module, "_command_version", lambda _cmd: (True, "ok"))
    monkeypatch.setattr(module.shutil, "which", lambda _name: None)
    monkeypatch.setattr(module.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(module, "sync_playwright", lambda: _PlaywrightContext())

    update = module._run_docker_environment_check()

    assert update["docker_environment"]["playwright_available"] is True
    assert update["docker_environment"]["chromium_available"] is True
    assert (
        update["docker_environment"]["tool_versions"]["chromium"]
        == str(chromium_path)
    )


def test_redaction_preserves_safe_preflight_diagnostics_and_redacts_real_tokens(
    tmp_path,
) -> None:
    module = _load_script_module()
    report_path = tmp_path / "readiness.json"

    exit_code = module.run_preview_v2_production_readiness(
        report_path=report_path,
        checks=(
            (
                "safe-diag",
                lambda _report: {
                    "model_preflights": {
                        "variants": {
                            "exact_five_page_booking": {
                                "business_components": {
                                    "capability_profile_revision": "2026-07-26.candidate-provider.3",
                                    "estimated_input_tokens": 12345,
                                    "requested_output_tokens": 24000,
                                    "clamped_output_tokens": 24000,
                                    "minimum_output_allowance": 4000,
                                    "context_reserve": 512,
                                    "access_token": "secret-token",
                                    "request_token": "req-secret",
                                }
                            }
                        }
                    }
                },
            ),
        ),
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    stage = report["model_preflights"]["variants"]["exact_five_page_booking"][
        "business_components"
    ]
    assert exit_code != 0
    assert stage["capability_profile_revision"] == "2026-07-26.candidate-provider.3"
    assert stage["estimated_input_tokens"] == 12345
    assert stage["requested_output_tokens"] == 24000
    assert stage["clamped_output_tokens"] == 24000
    assert stage["minimum_output_allowance"] == 4000
    assert stage["context_reserve"] == 512
    assert stage["access_token"] == "<redacted>"
    assert stage["request_token"] == "<redacted>"


def test_default_checks_real_mode_uses_preflight_report_not_host_variants(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_script_module()
    _patch_required_settings(monkeypatch, tmp_path)
    preflight_path = tmp_path / "host-preflight.json"
    bound_report, expected_sha = _bound_preflight_report(module, preflight_path)
    preflight_path.write_text(
        json.dumps(bound_report),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        module,
        "_run_prompt_variants_check",
        lambda: (_ for _ in ()).throw(
            AssertionError("real mode must not invoke host test helpers")
        ),
    )

    checks = module._default_checks(
        preflight_only=False,
        preflight_report_path=preflight_path,
        preflight_report_sha256=expected_sha,
    )
    identities = [identity for identity, _check in checks]
    assert "prompt_variants" not in identities
    assert "preflight_report" in identities


def test_preflight_report_import_does_not_overwrite_real_sections(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_script_module()
    _patch_required_settings(monkeypatch, tmp_path)
    preflight_path = tmp_path / "host-preflight.json"
    bound_report, expected_sha = _bound_preflight_report(module, preflight_path)
    preflight_path.write_text(json.dumps(bound_report), encoding="utf-8")

    update = module._load_preflight_report_check(
        preflight_path,
        expected_sha256=expected_sha,
    )

    assert "configuration" not in update
    assert "docker_environment" not in update
    assert "final_readiness" not in update
    assert "customer_security" not in update
    assert "phase4" not in update
    assert "phase5" not in update
    assert update["artifacts"]["imported_preflight_report_path"] == str(preflight_path)


def test_preflight_report_validator_requires_five_passing_variants_and_distinct_hashes(
    tmp_path,
) -> None:
    module = _load_script_module()
    validator = getattr(module, "_load_and_validate_preflight_report", None)
    if validator is None:
        pytest.fail("driver must expose _load_and_validate_preflight_report")

    valid_path = tmp_path / "valid-preflight.json"
    bound_report, expected_sha = _bound_preflight_report(module, valid_path)
    valid_path.write_text(
        json.dumps(bound_report),
        encoding="utf-8",
    )
    validated = validator(valid_path, expected_sha256=expected_sha)
    assert validated["prompt_variants"]["status"] == "pass"
    assert validated["restart_resume"]["status"] == "pass"

    invalid, invalid_sha = _bound_preflight_report(
        module,
        tmp_path / "invalid-preflight.json",
    )
    invalid["prompt_variants"]["variants"][2]["prompt_hashes"]["business_components"] = (
        invalid["prompt_variants"]["variants"][1]["prompt_hashes"]["business_components"]
    )
    invalid["prompt_variants"]["variants"][3]["seeded_record_count"] = 4
    invalid_path = tmp_path / "invalid-preflight.json"
    invalid_path.write_text(json.dumps(invalid), encoding="utf-8")

    with pytest.raises(ValueError):
        validator(invalid_path, expected_sha256=invalid_sha)

    invalid_docker, invalid_docker_sha = _bound_preflight_report(
        module,
        tmp_path / "invalid-docker-preflight.json",
    )
    invalid_docker["docker_environment"]["status"] = "fail"
    invalid_docker_path = tmp_path / "invalid-docker-preflight.json"
    invalid_docker_path.write_text(
        json.dumps(invalid_docker),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        validator(invalid_docker_path, expected_sha256=invalid_docker_sha)

    invalid_restart, invalid_restart_sha = _bound_preflight_report(
        module,
        tmp_path / "invalid-restart-preflight.json",
    )
    invalid_restart["restart_resume"]["status"] = "deferred_external_deterministic_suite"
    invalid_restart_path = tmp_path / "invalid-restart-preflight.json"
    invalid_restart_path.write_text(
        json.dumps(invalid_restart),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        validator(invalid_restart_path, expected_sha256=invalid_restart_sha)


def test_upstream_larger_catalog_variant_preserves_valid_chain(tmp_path, monkeypatch) -> None:
    from app.application.candidate_generation.context import load_candidate_context
    from app.application.composition_contract.context import load_composition_context
    from app.application.composition_contract.service import build_v2_composition_contract
    from app.infrastructure.templating.renderer import JinjaTemplateRenderer
    from tests.composition_contract.helpers import (
        CompositionFixtureAI,
        prepare_phase2,
        prompt_variant_prepare_kwargs,
    )

    module = _load_script_module()
    _patch_required_settings(monkeypatch, tmp_path)

    exact_prepared = prepare_phase2(
        request_id=48001,
        page_count=5,
        **prompt_variant_prepare_kwargs("exact_five_page_booking"),
    )
    larger_prepared = prepare_phase2(
        request_id=48002,
        page_count=8,
        **prompt_variant_prepare_kwargs("larger_service_catalog_booking"),
    )
    try:
        exact_phase3a = build_v2_composition_contract(
            exact_prepared.db,
            exact_prepared.req.id,
            CompositionFixtureAI(),
            JinjaTemplateRenderer(settings.TEMPLATES_DIR),
            req=exact_prepared.req,
            phase2_result=exact_prepared.phase2_result,
        )
        larger_phase3a = build_v2_composition_contract(
            larger_prepared.db,
            larger_prepared.req.id,
            CompositionFixtureAI(),
            JinjaTemplateRenderer(settings.TEMPLATES_DIR),
            req=larger_prepared.req,
            phase2_result=larger_prepared.phase2_result,
        )

        load_composition_context(
            exact_prepared.db,
            request_id=exact_prepared.req.id,
            phase2_result=exact_prepared.phase2_result,
        )
        exact_context = load_candidate_context(
            exact_prepared.db,
            request_id=exact_prepared.req.id,
            phase3a_result=exact_phase3a,
        )
        load_composition_context(
            larger_prepared.db,
            request_id=larger_prepared.req.id,
            phase2_result=larger_prepared.phase2_result,
        )
        larger_context = load_candidate_context(
            larger_prepared.db,
            request_id=larger_prepared.req.id,
            phase3a_result=larger_phase3a,
        )

        exact_records = sum(
            len(item.seed_records) for item in exact_context.content_data.data_collections
        )
        larger_records = sum(
            len(item.seed_records)
            for item in larger_context.content_data.data_collections
        )
        assert larger_records > exact_records

        monkeypatch.setenv("BMV_READINESS_RESTART_RESUME_PASSED", "1")
        update = module._run_prompt_variants_check()
        exact_variant = next(
            item
            for item in update["prompt_variants"]["variants"]
            if item["variant_id"] == "exact_five_page_booking"
        )
        larger_variant = next(
            item
            for item in update["prompt_variants"]["variants"]
            if item["variant_id"] == "larger_service_catalog_booking"
        )
        assert larger_variant["seeded_record_count"] > exact_variant["seeded_record_count"]
        assert (
            larger_variant["prompt_token_estimates"]["business_components"]
            > exact_variant["prompt_token_estimates"]["business_components"]
        )
    finally:
        exact_prepared.db.close()
        larger_prepared.db.close()


def test_preflight_report_binding_rejects_tampered_hash_and_source_identity(
    tmp_path,
) -> None:
    module = _load_script_module()
    validator = getattr(module, "_load_and_validate_preflight_report", None)
    if validator is None:
        pytest.fail("driver must expose _load_and_validate_preflight_report")

    bound, expected_sha = _bound_preflight_report(module, tmp_path / "bound.json")
    good_path = tmp_path / "bound.json"
    good_path.write_text(json.dumps(bound), encoding="utf-8")
    validated = validator(good_path, expected_sha256=expected_sha)
    assert validated["artifacts"]["preflight_report_sha256"] == expected_sha

    tampered = json.loads(json.dumps(bound))
    tampered["provider_calls"]["total_used"] = 3
    tampered_path = tmp_path / "tampered.json"
    tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError):
        validator(tampered_path, expected_sha256=expected_sha)

    wrong_sha_path = tmp_path / "wrong-sha.json"
    wrong_sha_path.write_text(json.dumps(bound), encoding="utf-8")
    with pytest.raises(ValueError):
        validator(wrong_sha_path, expected_sha256="0" * 64)

    mismatched_source = json.loads(json.dumps(bound))
    mismatched_source["artifacts"]["preflight_source_identity"]["driver_sha256"] = (
        "f" * 64
    )
    mismatched_source_path = tmp_path / "mismatched-source.json"
    mismatched_source_path.write_text(
        json.dumps(mismatched_source),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        validator(mismatched_source_path, expected_sha256=expected_sha)


def test_preflight_source_identity_tracks_evidence_shaping_files(tmp_path) -> None:
    module = _load_script_module()
    bound, _expected_sha = _bound_preflight_report(module, tmp_path / "bound.json")
    files = {
        item["path"]
        for item in bound["artifacts"]["preflight_source_identity"]["files"]
    }
    assert EXPECTED_SOURCE_IDENTITY_PATHS.issubset(files)


def test_collect_db_evidence_reads_persisted_rows_not_function_return(tmp_path) -> None:
    module = _load_script_module()
    collector = getattr(module, "_collect_db_evidence_for_request", None)
    if collector is None:
        pytest.fail("driver must expose _collect_db_evidence_for_request")

    settings.PREVIEW_VALIDATIONS_DIR = tmp_path / "validations"
    settings.PREVIEW_VALIDATIONS_DIR.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    request = Request(
        business_name=f"Readiness {uuid.uuid4().hex}",
        business_description="Five-page booking service",
        email="review@example.com",
        status="ready",
        generated_pages=json.dumps(
            {
                "preview_app": {"url": "/api/preview-apps/1/index.html"},
                "preview_contract": {
                    "status": "candidate_visual_accepted",
                    "candidate_revision": {"id": 999001, "workspace_relpath": "1/revisions/rev-1"},
                    "candidate_call_ledger": {
                        "total_max": 4,
                        "total_used": 2,
                        "substage_caps": {"business_components": 2, "pages": 2},
                    },
                    "candidate_stage_checkpoints": {
                        "foundation": {"status": "completed"},
                        "data_exports": {"status": "completed"},
                        "business_components": {"status": "completed"},
                        "pages": {"status": "completed"},
                    },
                    "candidate_provider_attempts": [
                        {
                            "substage": "business_components",
                            "response_format": "preflight",
                            "capability_profile_revision": CAPABILITY_PROFILE_REVISION,
                            "context_window": 1_048_576,
                            "minimum_output_allowance": 4_000,
                            "context_reserve": 512,
                            "approval_decision": "approved_preflight",
                        },
                        {
                            "substage": "pages",
                            "response_format": "preflight",
                            "capability_profile_revision": CAPABILITY_PROFILE_REVISION,
                            "context_window": 1_048_576,
                            "minimum_output_allowance": 4_000,
                            "context_reserve": 512,
                            "approval_decision": "approved_preflight",
                        },
                    ],
                },
            }
        ),
    )
    db.add(request)
    db.flush()
    request.generated_pages = request.generated_pages.replace("999001", "1")

    revision = CandidateRevisionRecord(
        revision_uuid=str(uuid.uuid4()),
        request_id=request.id,
        revision=1,
        target_tier=1,
        status="candidate_build_pending",
        generator_version="test",
        policy_revision="2026-07-24.1",
        upstream_manifest_json="{}",
        upstream_manifest_sha256=canonical_sha256({}),
        dependency_lock_sha256="b" * 64,
        model_manifest_json="{}",
        workspace_relpath=f"{request.id}/revisions/rev-1",
        file_manifest_json="[]",
        file_manifest_sha256=canonical_sha256([]),
        failure_json="{}",
        provider_call_count=2,
        repair_call_count=0,
        prompt_tokens=280,
        completion_tokens=220,
        total_tokens=500,
        cost_usd=0.04,
        latency_ms=1234,
    )
    db.add(revision)
    db.flush()
    request.generated_pages = request.generated_pages.replace('"id": 1', f'"id": {revision.id}', 1)

    tool_versions_payload = {
        "node": "v22.0.0",
        "npm": "10.0.0",
        "platform": "linux",
        "python": "3.12.10",
        "typescript": "5.6.0",
        "vite": "5.4.0",
        "playwright": "1.55.0",
        "browser_name": "chromium",
        "browser_version": "138.0.0",
        "accessibility_scanner": "BaselineAccessibilityScanner",
        "accessibility_policy_revision": "2026-07-24.1",
        "network_guard_revision": "2026-07-24.1",
    }
    limits_payload = {
        "typescript_timeout_seconds": 90,
        "vite_build_timeout_seconds": 120,
        "build_stage_timeout_seconds": 180,
        "server_startup_timeout_seconds": 20,
        "route_timeout_seconds": 15,
        "journey_timeout_seconds": 30,
        "accessibility_timeout_seconds": 15,
        "screenshot_timeout_seconds": 10,
        "phase_timeout_seconds": 600,
        "max_browser_contexts": 2,
        "max_browser_pages": 2,
        "max_console_diagnostics": 100,
        "max_network_diagnostics": 100,
        "max_command_output_bytes": 65536,
        "max_deterministic_repairs": 1,
        "max_dist_bytes": 5242880,
        "max_javascript_bytes": 2097152,
        "max_css_bytes": 524288,
        "max_dist_files": 200,
        "max_source_maps": 0,
    }
    runtime_attempt = CandidateRuntimeValidationAttemptRecord(
        attempt_uuid=str(uuid.uuid4()),
        request_id=request.id,
        candidate_revision_id=revision.id,
        attempt_sequence=1,
        cache_identity="d" * 64,
        candidate_manifest_sha256="e" * 64,
        dependency_lock_sha256="f" * 64,
        source_candidate_sha256_before="1" * 64,
        runtime_policy_revision="2026-07-24.1",
        tool_versions_json=json.dumps(tool_versions_payload),
        tool_versions_sha256=artifact_sha256(tool_versions_payload),
        limits_json=json.dumps(limits_payload),
        limits_sha256=artifact_sha256(limits_payload),
        workspace_relpath=revision.workspace_relpath,
    )
    db.add(runtime_attempt)
    db.flush()

    build_result = {
        "commands": [
            {"command_name": "typescript_build", "exit_code": 0, "timed_out": False},
            {"command_name": "vite_build", "exit_code": 0, "timed_out": False},
            {"command_name": "vite_preview", "exit_code": 0, "timed_out": False},
        ],
        "passed": True,
        "network_guard_verified": True,
        "dist_validation_passed": True,
    }
    build_attempt = CandidateBuildAttemptRecord(
        request_id=request.id,
        candidate_revision_id=revision.id,
        runtime_attempt_id=runtime_attempt.id,
        attempt_sequence=1,
        status="build_passed",
        build_cache_key="4" * 64,
        dist_cache_key="5" * 64,
        build_hash="6" * 64,
        dist_manifest_sha256="7" * 64,
        workspace_relpath=revision.workspace_relpath,
        result_json=json.dumps(build_result),
        result_sha256=artifact_sha256(build_result),
        passed=True,
    )
    db.add(build_attempt)
    db.flush()

    runtime_refs = {
        "request_id": request.id,
        "candidate_revision_id": revision.id,
        "candidate_revision_uuid": revision.revision_uuid,
        "candidate_manifest_sha256": "e" * 64,
        "dependency_lock_sha256": "f" * 64,
        "candidate_generator_version": revision.generator_version,
        "candidate_policy_revision": revision.policy_revision,
        "runtime_policy_revision": "2026-07-24.1",
    }
    routes = [
        ("PAGE-HOME", "/"),
        ("PAGE-SERVICE-LIST", "/services"),
        ("PAGE-SERVICE-DETAIL", "/services/detail"),
        ("PAGE-BOOKING", "/book"),
        ("PAGE-CONFIRMATION", "/confirmation"),
    ]
    route_hashes: list[str] = []
    accessibility_hashes: list[str] = []
    screenshot_hashes: list[str] = []
    for viewport in ("desktop", "mobile"):
        for page_id, route in routes:
            screenshot_relpath = (
                Path(str(request.id))
                / str(revision.id)
                / "screenshots"
                / f"{viewport}-{page_id}.png"
            )
            screenshot_path = settings.PREVIEW_VALIDATIONS_DIR / screenshot_relpath
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            screenshot_bytes = f"{viewport}:{page_id}:{route}".encode("utf-8")
            screenshot_path.write_bytes(screenshot_bytes)
            screenshot_sha = sha256_file(screenshot_path)
            route_payload = {
                "schema_version": "1.0",
                "refs": runtime_refs,
                "cache_key": f"{viewport}-{page_id}".ljust(64, "r"),
                "build_hash": "6" * 64,
                "page_id": page_id,
                "route": route,
                "viewport": viewport,
                "passed": True,
                "page_loaded": True,
                "page_marker_verified": True,
                "role_marker_verified": True,
                "component_markers_verified": True,
                "contract_hooks_verified": True,
                "reload_verified": True,
                "direct_navigation_verified": True,
                "history_verified": True,
                "overflow_verified": True,
                "clipping_verified": True,
                "primary_action_reachable": True,
                "mobile_bindings_verified": True,
                "console_errors": [],
                "page_errors": [],
                "request_failures": [],
                "diagnostics": [],
                "duration_ms": 10,
            }
            route_hash = artifact_sha256(route_payload)
            route_hashes.append(route_hash)
            db.add(
                CandidateRouteResultRecord(
                    request_id=request.id,
                    candidate_revision_id=revision.id,
                    runtime_attempt_id=runtime_attempt.id,
                    build_attempt_id=build_attempt.id,
                    page_id=page_id,
                    route=route,
                    viewport=viewport,
                    cache_key=f"{viewport}-{page_id}".ljust(64, "r"),
                    passed=True,
                    result_json=json.dumps(route_payload),
                    result_sha256=route_hash,
                )
            )
            accessibility_payload = {
                "schema_version": "1.0",
                "refs": runtime_refs,
                "cache_key": f"a{viewport}-{page_id}".ljust(64, "a"),
                "build_hash": "6" * 64,
                "scanner_name": "BaselineAccessibilityScanner",
                "scanner_policy_revision": "2026-07-24.1",
                "page_id": page_id,
                "route": route,
                "viewport": viewport,
                "passed": True,
                "findings": [],
                "duration_ms": 7,
            }
            accessibility_hash = artifact_sha256(accessibility_payload)
            accessibility_hashes.append(accessibility_hash)
            db.add(
                CandidateAccessibilityFindingRecord(
                    request_id=request.id,
                    candidate_revision_id=revision.id,
                    runtime_attempt_id=runtime_attempt.id,
                    build_attempt_id=build_attempt.id,
                    page_id=page_id,
                    route=route,
                    viewport=viewport,
                    scanner_name="BaselineAccessibilityScanner",
                    scanner_policy_revision="2026-07-24.1",
                    cache_key=f"a{viewport}-{page_id}".ljust(64, "a"),
                    passed=True,
                    result_json=json.dumps(accessibility_payload),
                    result_sha256=accessibility_hash,
                )
            )
            screenshot_payload = {
                "schema_version": "1.0",
                "refs": runtime_refs,
                "cache_key": f"s{viewport}-{page_id}".ljust(64, "c"),
                "build_hash": "6" * 64,
                "page_id": page_id,
                "route": route,
                "viewport": viewport,
                "relative_path": str(screenshot_relpath).replace("\\", "/"),
                "sha256": screenshot_sha,
                "byte_count": len(screenshot_bytes),
                "browser_version": "138.0.0",
                "capture_policy_revision": "2026-07-24.1",
                "captured_at": "2026-07-26T17:00:00Z",
            }
            screenshot_hash = artifact_sha256(screenshot_payload)
            screenshot_hashes.append(screenshot_hash)
            db.add(
                CandidateScreenshotRecord(
                    request_id=request.id,
                    candidate_revision_id=revision.id,
                    runtime_attempt_id=runtime_attempt.id,
                    build_attempt_id=build_attempt.id,
                    page_id=page_id,
                    route=route,
                    viewport=viewport,
                    cache_key=f"s{viewport}-{page_id}".ljust(64, "c"),
                    relative_path=str(screenshot_relpath).replace("\\", "/"),
                    screenshot_sha256=screenshot_sha,
                    evidence_json=json.dumps(screenshot_payload),
                    evidence_sha256=screenshot_hash,
                )
            )
    journey_payload = {
        "schema_version": "1.0",
        "refs": runtime_refs,
        "cache_key": "j" * 64,
        "build_hash": "6" * 64,
        "journey_id": "JOURNEY-BOOK-SERVICE",
        "action_id": "ACTION-SUBMIT",
        "acceptance_test_ids": ["AT-BOOKING-CONFIRMATION"],
        "route": "/book",
        "passed": True,
        "reduced_motion_required": False,
        "reduced_motion_passed": True,
        "steps": [
            {
                "step": "action",
                "canonical_id": "service_selection",
                "passed": True,
                "selector": "[data-service]",
                "expected": "service selected",
                "observed": "service selected",
            },
                {
                    "step": "evidence",
                    "canonical_id": "EVIDENCE-CALENDAR-VIEW",
                    "passed": True,
                    "selector": "[data-calendar]",
                    "expected": "availability calendar visible",
                    "observed": "availability calendar visible",
                },
            {
                "step": "input",
                "canonical_id": "customer_details",
                "passed": True,
                "selector": "form",
                "expected": "customer details entered",
                "observed": "customer details entered",
            },
            {
                "step": "evidence",
                "canonical_id": "confirmation",
                "passed": True,
                "selector": "[data-confirmation]",
                "expected": "confirmation visible",
                "observed": "confirmation visible",
            },
        ],
        "diagnostics": [],
        "duration_ms": 20,
    }
    journey_hash = artifact_sha256(journey_payload)
    db.add(
        CandidateJourneyResultRecord(
            request_id=request.id,
            candidate_revision_id=revision.id,
            runtime_attempt_id=runtime_attempt.id,
            build_attempt_id=build_attempt.id,
            journey_id="JOURNEY-BOOK-SERVICE",
            action_id="ACTION-SUBMIT",
            cache_key="j" * 64,
            passed=True,
            result_json=json.dumps(journey_payload),
            result_sha256=journey_hash,
        )
    )
    summary_payload = {
        "schema_version": "1.0",
        "refs": runtime_refs,
        "attempt_uuid": runtime_attempt.attempt_uuid,
        "status": "candidate_runtime_validated",
        "source_candidate_sha256_before": "1" * 64,
        "source_candidate_sha256_after": "1" * 64,
        "build_result_sha256": artifact_sha256(build_result),
        "route_result_hashes": route_hashes,
        "journey_result_hashes": [journey_hash],
        "accessibility_result_hashes": accessibility_hashes,
        "screenshot_hashes": screenshot_hashes,
        "all_required_gates_passed": True,
        "server_identity_verified": True,
        "expected_route_viewport_count": 10,
        "expected_journey_count": 1,
        "network_diagnostics": [],
        "diagnostics": [],
        "server_command": {
            "command_name": "vite_preview",
            "argv": ["npm", "run", "preview"],
            "exit_code": 0,
            "timed_out": False,
            "duration_ms": 30,
            "stdout_summary": "preview ready",
            "stderr_summary": "",
            "stdout_sha256": "9" * 64,
            "stderr_sha256": "a" * 64,
        },
        "duration_ms": 120,
    }
    validation_summary = CandidateValidationSummaryRecord(
        request_id=request.id,
        candidate_revision_id=revision.id,
        runtime_attempt_id=runtime_attempt.id,
        build_attempt_id=build_attempt.id,
        status="candidate_runtime_validated",
        candidate_manifest_sha256="e" * 64,
        build_hash="6" * 64,
        source_candidate_sha256_before="1" * 64,
        source_candidate_sha256_after="1" * 64,
        summary_json=json.dumps(summary_payload),
        summary_sha256=artifact_sha256(summary_payload),
    )
    db.add(validation_summary)
    db.flush()

    visual_summary_payload = {
        "schema_version": "1.0",
        "refs": {
            "request_id": request.id,
            "candidate_revision_id": revision.id,
            "candidate_revision_uuid": revision.revision_uuid,
            "candidate_manifest_sha256": "e" * 64,
            "runtime_attempt_id": runtime_attempt.id,
            "runtime_summary_id": validation_summary.id,
            "runtime_summary_sha256": artifact_sha256(summary_payload),
            "build_attempt_id": build_attempt.id,
            "build_hash": "6" * 64,
            "screenshot_set_sha256": canonical_sha256(screenshot_hashes),
            "design_contract_refs": {
                "request_id": request.id,
                "customer_source_ref": {"id": 1, "sha256": "b" * 64},
                "product_strategy_seed_ref": {"id": 1, "revision": 1, "sha256": "c" * 64},
                "app_spec_ref": {
                    "id": 1,
                    "revision": 1,
                    "schema_version": "1.0",
                    "sha256": "d" * 64,
                },
                "tier_refs": [
                    {"id": 1, "tier": 1, "sha256": "e" * 64, "selection_policy_revision": "2026-07-25.1"},
                    {"id": 2, "tier": 2, "sha256": "f" * 64, "selection_policy_revision": "2026-07-25.1"},
                    {"id": 3, "tier": 3, "sha256": "1" * 64, "selection_policy_revision": "2026-07-25.1"},
                ],
            },
            "page_purpose_sha256": "2" * 64,
            "business_component_plan_sha256": "3" * 64,
            "content_data_plan_sha256": "4" * 64,
            "interaction_contract_sha256": "5" * 64,
            "component_dependency_graph_sha256": "6" * 64,
            "visual_policy_revision": "2026-07-24.1",
        },
        "attempt_uuid": str(uuid.uuid4()),
        "subject": "original",
        "status": "candidate_visual_accepted",
        "repairability": "accepted",
        "evidence_bundle_sha256": "7" * 64,
        "hard_gate_sha256": "8" * 64,
        "critic_scorecard_sha256": "9" * 64,
        "reviewer_decision_sha256": "a" * 64,
        "baseline_comparison_sha256": "b" * 64,
        "acceptance_computation": {
            "weighted_overall": 90.0,
            "critic_weighted_overall": 90.0,
            "reviewer_weighted_overall": 90.0,
            "dimension_scores": [(name, 90.0) for name in VISUAL_DIMENSIONS],
            "blocking_finding_count": 0,
            "critic_accepts": True,
            "reviewer_accepts": True,
            "agreement": True,
            "threshold_checks": [
                ("overall", True),
                ("critic", True),
                ("reviewer", True),
                ("business_specificity", True),
                ("mobile_quality", True),
                ("evidence_visibility", True),
                ("trust_and_professionalism", True),
                ("agreement", True),
            ],
            "accepted": True,
        },
        "call_metrics": [],
        "provider_call_count": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
        "latency_ms": 100,
        "cache_hits": [],
        "diagnostics": [],
    }

    visual_attempt = CandidateVisualEvaluationAttemptRecord(
        attempt_uuid=str(uuid.uuid4()),
        request_id=request.id,
        candidate_revision_id=revision.id,
        runtime_summary_id=validation_summary.id,
        subject="tier1",
        evaluation_cache_key="m" * 64,
        refs_json="{}",
        refs_sha256="n" * 64,
        routing_json="{}",
        routing_sha256="o" * 64,
        limits_json="{}",
        limits_sha256="p" * 64,
    )
    db.add(visual_attempt)
    db.flush()
    visual_summary = CandidateVisualSummaryRecord(
        request_id=request.id,
        candidate_revision_id=revision.id,
        visual_attempt_id=visual_attempt.id,
        cache_key="q" * 64,
        artifact_json=json.dumps(visual_summary_payload),
        artifact_sha256=artifact_sha256(visual_summary_payload),
        status="candidate_visual_accepted",
        repairability="accepted",
        acceptance_policy_revision="2026-07-24.1",
        score_band_policy_revision="2026-07-24.1",
        deterministic_acceptance_json="{}",
        provider_call_count=0,
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        cost_usd=0.0,
        latency_ms=100,
    )
    db.add(visual_summary)
    db.add(
        ExpandedPreviewRequestRecord(
            expanded_preview_uuid=str(uuid.uuid4()),
            request_id=request.id,
            current_status="requested",
            idempotency_key=f"ep-{uuid.uuid4().hex}",
            request_sha256="s" * 64,
            actor_id="customer:test",
            accepted_tier_1_revision_id=revision.id,
        )
    )
    db.commit()

    try:
        evidence = collector(request_id=request.id, db_session=db)
        assert evidence["provider_calls"]["status"] == "pass"
        assert evidence["generated_code_validation"]["status"] == "pass"
        assert evidence["phase4"]["status"] == "pass"
        assert evidence["phase4"]["validated_unique_routes"] == 5
        assert evidence["phase4"]["semantic_page_set"]["status"] == "pass"
        assert evidence["phase5"]["status"] == "pass"
        assert evidence["phase5"]["summary_status"] == "candidate_visual_accepted"
        assert evidence["expanded_preview"]["status"] == "pass"
        assert evidence["expanded_preview"]["tier2_artifacts_present"] is False

        invalid_runtime_summary = dict(summary_payload)
        invalid_runtime_summary.pop("refs")
        validation_summary.summary_json = json.dumps(invalid_runtime_summary)
        validation_summary.summary_sha256 = artifact_sha256(invalid_runtime_summary)
        db.commit()
        with pytest.raises(ValueError):
            collector(request_id=request.id, db_session=db)

        validation_summary.summary_json = json.dumps(summary_payload)
        validation_summary.summary_sha256 = artifact_sha256(summary_payload)
        invalid_visual_summary = dict(visual_summary_payload)
        invalid_visual_summary.pop("attempt_uuid")
        visual_summary.artifact_json = json.dumps(invalid_visual_summary)
        visual_summary.artifact_sha256 = artifact_sha256(invalid_visual_summary)
        db.commit()
        with pytest.raises(ValueError):
            collector(request_id=request.id, db_session=db)
    finally:
        db.close()


def test_http_json_supports_json_request_body(monkeypatch) -> None:
    module = _load_script_module()
    captured = {}

    class _Response:
        status = 200

        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request, timeout=30):
        captured["content_type"] = request.headers.get("Content-Type")
        captured["payload"] = request.data
        return _Response()

    monkeypatch.setattr(module.urllib_request, "urlopen", fake_urlopen)

    module._http_json(
        method="POST",
        url="http://localhost/test",
        json_body={},
    )

    assert captured["content_type"] == "application/json"
    assert captured["payload"] == b"{}"


def test_real_http_flow_requires_negative_expanded_preview_auth_before_token(
    monkeypatch,
) -> None:
    module = _load_script_module()
    seen: list[tuple[str, dict[str, str] | None, dict | None]] = []

    def fake_http_json(
        *,
        method,
        url,
        body=None,
        json_body=None,
        headers=None,
        timeout=30,
    ):
        seen.append((url, headers, json_body))
        if url.endswith("/api/requests"):
            return 200, {"id": 321, "customer_access_token": "tok-123"}
        if url.endswith("/api/requests/321/preview"):
            return 200, {"status": "ready", "tier2_request_state": None}
        if url.endswith("/api/requests/321/progress"):
            return 200, {"status": "ready", "tier2_request_state": None}
        if url.endswith("/api/admin/configuration-safety"):
            return 401, {}
        if url.endswith("/api/requests/321/expanded-preview"):
            if headers and headers.get("X-Request-Access-Token") == "tok-123":
                return 200, {"lifecycle_status": "requested"}
            return 401, {}
        raise AssertionError(url)

    monkeypatch.setattr(module, "_http_json", fake_http_json)
    monkeypatch.setattr(
        module,
        "_collect_db_evidence_for_request",
        lambda **_kwargs: {
            "phase4": {"status": "pass"},
            "phase5": {"status": "pass"},
            "expanded_preview": {
                "status": "pass",
                "tier2_artifacts_present": False,
            },
        },
    )

    result = module._run_real_http_flow()
    expanded_calls = [
        (headers, json_body)
        for url, headers, json_body in seen
        if url.endswith("/api/requests/321/expanded-preview")
    ]
    assert expanded_calls[0] == (None, {})
    assert expanded_calls[1] == ({"X-Request-Access-Token": "tok-123"}, {})
    assert result["customer_security"]["admin_config_401_verified"] is True


def test_real_http_flow_reviewing_uses_trusted_candidate_terminal_without_sleep(
    monkeypatch,
) -> None:
    module = _load_script_module()
    polls = {"preview": 0, "progress": 0}

    def fake_http_json(
        *,
        method,
        url,
        body=None,
        json_body=None,
        headers=None,
        timeout=30,
    ):
        if url.endswith("/api/requests"):
            return 200, {"id": 321, "customer_access_token": "tok-123"}
        if url.endswith("/api/requests/321/preview"):
            polls["preview"] += 1
            return 200, {"status": "reviewing", "tier2_request_state": None}
        if url.endswith("/api/requests/321/progress"):
            polls["progress"] += 1
            return 200, {
                "status": "reviewing",
                "is_generating": False,
                "is_failed": False,
                "tier2_request_state": None,
            }
        if url.endswith("/api/admin/configuration-safety"):
            return 401, {}
        if url.endswith("/api/requests/321/expanded-preview"):
            if headers and headers.get("X-Request-Access-Token") == "tok-123":
                return 200, {"lifecycle_status": "requested"}
            return 401, {}
        raise AssertionError(url)

    monkeypatch.setattr(module, "_http_json", fake_http_json)
    monkeypatch.setattr(
        module,
        "_trusted_candidate_terminal_status",
        lambda _request_id: "candidate_contract_failed",
        raising=False,
    )
    monkeypatch.setattr(
        module.time,
        "sleep",
        lambda _seconds: (_ for _ in ()).throw(
            AssertionError("reviewing should not sleep once trusted candidate terminal is known")
        ),
    )
    monkeypatch.setattr(
        module,
        "_collect_db_evidence_for_request",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("db evidence failed")),
    )

    result = module._run_real_http_flow()

    assert polls["preview"] == 1
    assert polls["progress"] == 1
    assert result["artifacts"]["candidate_status"] == "candidate_contract_failed"


def test_trusted_candidate_terminal_ignored_while_request_retrying(
    monkeypatch,
) -> None:
    module = _load_script_module()

    class _Req:
        status = "retrying_preview_app"

    class _DB:
        def get(self, *_args, **_kwargs):
            return _Req()

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        "app.infrastructure.db.session.SessionLocal",
        lambda: _DB(),
    )
    monkeypatch.setattr(
        module,
        "_request_snapshot_evidence",
        lambda _request_id: {
            "artifacts": {
                "candidate_status": "candidate_contract_failed",
            }
        },
    )

    assert module._trusted_candidate_terminal_status(1) == ""


def test_real_http_flow_planning_continues_past_legacy_poll_cap_until_terminal(
    monkeypatch,
) -> None:
    module = _load_script_module()
    polls = {"preview": 0, "progress": 0, "sleep": 0}
    clock = {"now": 0.0}

    def fake_http_json(
        *,
        method,
        url,
        body=None,
        json_body=None,
        headers=None,
        timeout=30,
    ):
        if url.endswith("/api/requests"):
            return 200, {"id": 321, "customer_access_token": "tok-123"}
        if url.endswith("/api/requests/321/preview"):
            polls["preview"] += 1
            return 200, {"status": "planning", "tier2_request_state": None}
        if url.endswith("/api/requests/321/progress"):
            polls["progress"] += 1
            return 200, {
                "status": "planning",
                "stage": "planning",
                "is_generating": False,
                "is_failed": False,
                "tier2_request_state": None,
            }
        if url.endswith("/api/admin/configuration-safety"):
            return 401, {}
        if url.endswith("/api/requests/321/expanded-preview"):
            if headers and headers.get("X-Request-Access-Token") == "tok-123":
                return 200, {"lifecycle_status": "requested"}
            return 401, {}
        raise AssertionError(url)

    def fake_terminal_status(_request_id: int) -> str | None:
        if polls["progress"] > 120:
            return "candidate_visual_accepted"
        return None

    def fake_sleep(seconds: float) -> None:
        polls["sleep"] += 1
        clock["now"] += seconds

    monkeypatch.setattr(module, "_http_json", fake_http_json)
    monkeypatch.setattr(
        module,
        "_trusted_candidate_terminal_status",
        fake_terminal_status,
        raising=False,
    )
    monkeypatch.setattr(
        module,
        "_request_snapshot_evidence",
        lambda _request_id: {
            "provider_calls": {"status": "pass", "blockers": []},
        },
    )
    monkeypatch.setattr(
        module,
        "_collect_db_evidence_for_request",
        lambda **_kwargs: {
            "phase4": {"status": "pass", "blockers": []},
            "phase5": {"status": "pass", "blockers": []},
        },
    )
    monkeypatch.setattr(module.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(module.time, "sleep", fake_sleep)
    monkeypatch.setattr(settings, "V2_RUNTIME_PHASE_TIMEOUT_SECONDS", 600)
    monkeypatch.setattr(settings, "V2_VISUAL_PHASE_TIMEOUT_SECONDS", 600)

    result = module._run_real_http_flow()

    assert polls["preview"] == 121
    assert polls["progress"] == 121
    assert polls["sleep"] == 120
    assert result["artifacts"]["candidate_status"] == "candidate_visual_accepted"
    assert result["artifacts"]["terminal_preview_status"] == "planning"
    assert result["artifacts"]["terminal_progress_status"] == "planning"


def test_real_http_resume_keeps_polling_while_retrying_despite_stale_failed_preview(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_script_module()
    polls = {"preview": 0, "progress": 0, "sleep": 0}
    clock = {"now": 0.0}
    token_file = tmp_path / "resume-token.txt"
    token_file.write_text("tok-resume", encoding="utf-8")

    def fake_http_json(
        *,
        method,
        url,
        body=None,
        json_body=None,
        headers=None,
        timeout=30,
    ):
        if url.endswith("/api/requests/321/retry-generation"):
            if headers and headers.get("X-Request-Access-Token") == "tok-resume":
                return 200, {"ok": True, "id": 321, "status": "restarted"}
            return 401, {}
        if url.endswith("/api/requests/321/preview"):
            polls["preview"] += 1
            # Stale customer surface can remain "failed" while retry is in flight.
            return 200, {"status": "failed", "tier2_request_state": None}
        if url.endswith("/api/requests/321/progress"):
            polls["progress"] += 1
            return 200, {
                "status": "failed",
                "is_generating": False,
                "is_failed": True,
                "tier2_request_state": None,
            }
        if url.endswith("/api/admin/configuration-safety"):
            return 401, {}
        if url.endswith("/api/requests/321/expanded-preview"):
            if headers and headers.get("X-Request-Access-Token") == "tok-resume":
                return 200, {"lifecycle_status": "requested"}
            return 401, {}
        raise AssertionError(url)

    def fake_terminal_status(_request_id: int) -> str:
        if polls["progress"] >= 3:
            return "candidate_visual_accepted"
        return ""

    def fake_request_status(_request_id: int) -> str:
        if polls["progress"] >= 3:
            return "ready"
        return "retrying_preview_app"

    def fake_sleep(seconds: float) -> None:
        polls["sleep"] += 1
        clock["now"] += seconds

    monkeypatch.setattr(module, "_http_json", fake_http_json)
    monkeypatch.setattr(
        module,
        "_trusted_candidate_terminal_status",
        fake_terminal_status,
        raising=False,
    )
    monkeypatch.setattr(
        module,
        "_request_status",
        fake_request_status,
        raising=False,
    )
    monkeypatch.setattr(
        module,
        "_collect_db_evidence_for_request",
        lambda **_kwargs: {
            "phase4": {"status": "pass", "blockers": []},
            "phase5": {"status": "pass", "blockers": []},
        },
    )
    monkeypatch.setattr(module.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(module.time, "sleep", fake_sleep)
    monkeypatch.setattr(settings, "V2_RUNTIME_PHASE_TIMEOUT_SECONDS", 600)
    monkeypatch.setattr(settings, "V2_VISUAL_PHASE_TIMEOUT_SECONDS", 600)

    result = module._run_real_http_flow(
        resume_request_id=321,
        resume_access_token_file=token_file,
    )

    assert polls["preview"] >= 3
    assert polls["sleep"] >= 2
    assert result["artifacts"]["candidate_status"] == "candidate_visual_accepted"


def test_real_http_flow_resume_retries_same_request_without_create(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_script_module()
    seen: list[tuple[str, str, dict[str, str] | None]] = []
    token_file = tmp_path / "resume-token.txt"
    token_file.write_text("tok-resume", encoding="utf-8")
    authenticated_retries = {"count": 0}

    def fake_http_json(
        *,
        method,
        url,
        body=None,
        json_body=None,
        headers=None,
        timeout=30,
    ):
        seen.append((method, url, headers))
        if url.endswith("/api/requests/321/retry-generation"):
            if headers and headers.get("X-Request-Access-Token") == "tok-resume":
                authenticated_retries["count"] += 1
                return 200, {"ok": True, "id": 321, "status": "restarted"}
            return 401, {}
        if url.endswith("/api/requests/321/preview"):
            return 200, {"status": "ready", "tier2_request_state": None}
        if url.endswith("/api/requests/321/progress"):
            return 200, {"status": "ready", "tier2_request_state": None}
        if url.endswith("/api/admin/configuration-safety"):
            return 401, {}
        if url.endswith("/api/requests/321/expanded-preview"):
            if headers and headers.get("X-Request-Access-Token") == "tok-resume":
                return 200, {"lifecycle_status": "requested"}
            return 401, {}
        raise AssertionError(url)

    monkeypatch.setattr(module, "_http_json", fake_http_json)
    monkeypatch.setattr(
        module,
        "_collect_db_evidence_for_request",
        lambda **_kwargs: {
            "phase4": {"status": "pass"},
            "phase5": {"status": "pass"},
            "expanded_preview": {"status": "pass", "tier2_artifacts_present": False},
        },
    )

    result = module._run_real_http_flow(
        resume_request_id=321,
        resume_access_token_file=token_file,
    )

    assert not any(url.endswith("/api/requests") for _method, url, _headers in seen)
    retry_calls = [
        headers
        for method, url, headers in seen
        if method == "POST" and url.endswith("/api/requests/321/retry-generation")
    ]
    assert retry_calls[0] is None
    assert retry_calls[1] == {"X-Request-Access-Token": "tok-resume"}
    assert authenticated_retries["count"] == 1
    assert result["artifacts"]["request_id"] == 321
    assert result["artifacts"]["resume_access_token_file"]["exists"] is False
    assert result["artifacts"]["resume_access_token_file"]["deleted_on_success"] is True


def test_real_http_flow_preserves_request_and_provider_evidence_on_db_failure(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_script_module()
    token_file = tmp_path / "resume-token.txt"
    seen: list[str] = []

    def fake_http_json(
        *,
        method,
        url,
        body=None,
        json_body=None,
        headers=None,
        timeout=30,
    ):
        seen.append(url)
        if url.endswith("/api/requests"):
            return 200, {"id": 321, "customer_access_token": "tok-123"}
        if url.endswith("/api/requests/321/preview"):
            return 200, {
                "status": "failed",
                "tier2_request_state": None,
                "preview_contract": {
                    "status": "candidate_contract_failed",
                    "candidate_provider_attempts": [{"response_format": "preflight"}],
                    "candidate_call_ledger": {
                        "total_used": 3,
                        "substage_used": {"business_components": 2, "pages": 1},
                    },
                },
            }
        if url.endswith("/api/requests/321/progress"):
            return 200, {"status": "failed", "tier2_request_state": None}
        if url.endswith("/api/admin/configuration-safety"):
            return 401, {}
        if url.endswith("/api/requests/321/expanded-preview"):
            if headers and headers.get("X-Request-Access-Token") == "tok-123":
                return 200, {"lifecycle_status": "requested"}
            return 401, {}
        raise AssertionError(url)

    monkeypatch.setattr(module, "_http_json", fake_http_json)
    monkeypatch.setattr(
        module,
        "_collect_db_evidence_for_request",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("db evidence failed")),
    )

    result = module._run_real_http_flow(
        resume_access_token_file=token_file,
    )

    assert result["artifacts"]["request_id"] == 321
    assert result["artifacts"]["terminal_preview_status"] == "failed"
    assert result["artifacts"]["candidate_status"] == "candidate_contract_failed"
    assert result["provider_calls"]["status"] == "fail"
    assert result["provider_calls"]["source"] == "observed_candidate_db"
    assert result["provider_calls"]["caps_respected"] is True
    assert result["provider_calls"]["total_used"] == 3
    assert result["provider_calls"]["components_used"] == 2
    assert result["provider_calls"]["pages_used"] == 1


def test_load_request_access_token_writes_sidecar_before_digest_commit(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_script_module()

    class _Req:
        def __init__(self):
            self.customer_access_token = "legacy-token"

    class _Db:
        def __init__(self):
            self.req = _Req()
            self.commits = 0

        def get(self, entity, key):
            return self.req if key == 1 else None

        def commit(self):
            self.commits += 1

        def close(self):
            return None

    db = _Db()
    token_file = tmp_path / "legacy.token"

    monkeypatch.setattr(
        "app.infrastructure.db.session.SessionLocal",
        lambda: db,
    )

    token = module._load_request_access_token(1, token_file)

    assert token == "legacy-token"
    assert token_file.read_text(encoding="utf-8") == "legacy-token"
    assert db.req.customer_access_token != "legacy-token"
    assert len(db.req.customer_access_token) == 64
    assert db.commits == 1

    second = module._load_request_access_token(1, token_file)
    assert second == "legacy-token"
    assert db.commits == 1


def test_load_request_access_token_does_not_commit_digest_when_sidecar_write_fails(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_script_module()

    class _Req:
        def __init__(self):
            self.customer_access_token = "legacy-token"

    class _Db:
        def __init__(self):
            self.req = _Req()
            self.commits = 0

        def get(self, entity, key):
            return self.req if key == 1 else None

        def commit(self):
            self.commits += 1

        def close(self):
            return None

    db = _Db()
    monkeypatch.setattr(
        "app.infrastructure.db.session.SessionLocal",
        lambda: db,
    )
    monkeypatch.setattr(
        module,
        "_write_private_token_file",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("sink failed")),
    )

    with pytest.raises(OSError, match="sink failed"):
        module._load_request_access_token(1, tmp_path / "legacy.token")

    assert db.req.customer_access_token == "legacy-token"
    assert db.commits == 0
