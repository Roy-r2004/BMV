from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
POWERSHELL_SCRIPT = ROOT / "scripts" / "verify-preview-v2-release.ps1"
BASH_SCRIPT = ROOT / "scripts" / "verify-preview-v2-release"
ROOT_ENV_EXAMPLE = ROOT / ".env.example"
ROOT_ENV_PROD_EXAMPLE = ROOT / ".env.prod.example"
BACKEND_ENV_EXAMPLE = ROOT / "backend" / ".env.example"
COOLIFY_COMPOSE = ROOT / "docker-compose.coolify.yml"
PROD_COMPOSE = ROOT / "docker-compose.prod.yml"
README = ROOT / "README.md"
MANDATORY_TEST_TOKENS = (
    "tests/candidate_generation/test_request33_provider_reliability.py",
    "tests/candidate_generation/test_request34_context_overflow.py",
    "tests/candidate_generation/test_request35_pages_model.py",
    "tests/candidate_generation/test_request36_component_model.py",
    "tests/candidate_generation/test_candidate_resume.py",
    "tests/composition_contract/test_phase3a_call_budget.py",
    "tests/infrastructure/ai_providers/test_response_parser.py",
    "tests/infrastructure/ai_providers/test_openrouter_error_matrix.py",
    "tests/preview_contract/test_appspec_v2_policy.py",
    "tests/security/test_customer_preview_responses.py",
    "tests/rollout/test_phase7a_flags.py",
    "tests/commercial/test_staging_flags_and_no_auto_tier2.py",
    "tests/runtime_validation/test_phase4_runtime_validation.py",
    "tests/visual_evaluation/test_phase5_visual_evaluation.py",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_powershell_script_accepts_production_readiness_mode() -> None:
    text = _text(POWERSHELL_SCRIPT)
    assert 'ValidateSet("default", "full", "production-readiness")' in text


def test_powershell_script_avoids_ps7_only_json_and_null_syntax() -> None:
    text = _text(POWERSHELL_SCRIPT)
    assert "-AsHashtable" not in text
    assert "??" not in text


def test_bash_script_accepts_production_readiness_mode() -> None:
    text = _text(BASH_SCRIPT)
    assert '"${MODE}" == "production-readiness"' in text


def test_scripts_define_production_readiness_artifact_root() -> None:
    assert ".runtime/production-readiness" in _text(BASH_SCRIPT)
    assert ".runtime\\production-readiness" in _text(POWERSHELL_SCRIPT)


def test_scripts_include_all_mandatory_production_readiness_suites() -> None:
    for token in MANDATORY_TEST_TOKENS:
        assert token in _text(POWERSHELL_SCRIPT)
        assert token in _text(BASH_SCRIPT)


def test_scripts_run_preflight_driver_before_real_http_with_bound_sha() -> None:
    bash = _text(BASH_SCRIPT)
    ps1 = _text(POWERSHELL_SCRIPT)
    for text in (bash, ps1):
        assert "--preflight-only" in text
        assert "--report-path" in text
        assert "--run-real-http" in text
        assert "--preflight-report" in text
        assert "--preflight-report-sha256" in text
        assert "--resume-access-token-file" in text
        assert "preflight_report_sha256" in text


def test_scripts_accept_host_deferred_docker_environment_for_preflight_handoff() -> None:
    bash = _text(BASH_SCRIPT)
    ps1 = _text(POWERSHELL_SCRIPT)
    for text in (bash, ps1):
        assert "deferred_to_production_image" in text
        assert "host_environment" in text
        assert "production_image_required" in text
        assert "docker_environment" in text


def test_scripts_manage_restart_resume_process_marker() -> None:
    bash = _text(BASH_SCRIPT)
    ps1 = _text(POWERSHELL_SCRIPT)
    for text in (bash, ps1):
        assert "BMV_READINESS_RESTART_RESUME_PASSED" in text
        assert "test_candidate_resume.py" in text


def test_production_defaults_keep_appspec_coverage_on_deepseek_family() -> None:
    for path in (
        ROOT_ENV_EXAMPLE,
        ROOT_ENV_PROD_EXAMPLE,
        BACKEND_ENV_EXAMPLE,
        COOLIFY_COMPOSE,
        PROD_COMPOSE,
        README,
    ):
        text = _text(path)
        assert "APPSPEC_COVERAGE_MODEL" in text
        assert "deepseek/deepseek-chat" in text


def test_scripts_require_admin_and_openrouter_secrets_before_docker() -> None:
    bash = _text(BASH_SCRIPT)
    ps1 = _text(POWERSHELL_SCRIPT)
    assert "ADMIN_PASSWORD" in bash and "OPENROUTER_API_KEY" in bash
    assert "ADMIN_PASSWORD" in ps1 and "OPENROUTER_API_KEY" in ps1


def test_powershell_script_snapshots_and_restores_overridden_env_vars() -> None:
    text = _text(POWERSHELL_SCRIPT)
    assert "Get-EnvSnapshot" in text
    assert "Restore-EnvSnapshot" in text
    assert "$envSnapshot = Get-EnvSnapshot" in text
    assert "finally {" in text
    assert "Restore-EnvSnapshot -Snapshot $envSnapshot" in text
    for token in (
        "APP_ENV",
        "PREVIEW_GENERATOR_V2",
        "V2_CANDIDATE_COMPONENT_MODEL",
        "V2_CANDIDATE_PAGE_MODEL",
        "APPSPEC_FALLBACK_ENABLED",
        "V2_PHASE7_ROLLOUT_ENABLED",
        "V2_PHASE7_PROMOTE_ENABLED",
        "V2_PHASE7_PERCENT_SERVE_ENABLED",
        "V2_PHASE7_ROLLOUT_PERCENT",
        "V2_RUNTIME_VALIDATION_ENABLED",
        "V2_VISUAL_EVALUATION_ENABLED",
    ):
        assert token in text


def test_scripts_use_coolify_compose_and_dockerfile_app_only() -> None:
    bash = _text(BASH_SCRIPT)
    ps1 = _text(POWERSHELL_SCRIPT)
    for text in (bash, ps1):
        assert "docker-compose.coolify.yml" in text
        assert "Dockerfile.app" in text
        assert "--profile" not in text
        assert "docker build" not in text


def test_scripts_override_required_production_env_values() -> None:
    required = (
        "V2_CANDIDATE_COMPONENT_MODEL",
        "V2_CANDIDATE_PAGE_MODEL",
        "APPSPEC_FALLBACK_ENABLED",
        "V2_PHASE7_ROLLOUT_ENABLED",
        "V2_PHASE7_PROMOTE_ENABLED",
        "V2_PHASE7_PERCENT_SERVE_ENABLED",
        "V2_PHASE7_ROLLOUT_PERCENT",
        "V2_RUNTIME_VALIDATION_ENABLED",
        "V2_VISUAL_EVALUATION_ENABLED",
        "APP_ENV",
    )
    for token in required:
        assert token in _text(POWERSHELL_SCRIPT)
        assert token in _text(BASH_SCRIPT)


def test_scripts_preserve_failure_artifacts_and_skip_auto_teardown() -> None:
    bash = _text(BASH_SCRIPT)
    ps1 = _text(POWERSHELL_SCRIPT)
    for text in (bash, ps1):
        assert "docker compose logs" in text
        assert "preserve" in text.lower()
        assert "artifact" in text.lower()
        assert "no automatic teardown" in text.lower() or "automatic teardown" in text.lower()


def test_bash_script_uses_central_compose_failure_handler_for_post_start_steps() -> None:
    text = _text(BASH_SCRIPT)
    assert "handle_compose_failure()" in text
    for fragment in (
        'exec -T app mkdir -p "${container_data_root}"',
        'docker cp "${host_preflight_report}"',
        'exec -T app \\',
        'docker cp "${CONTAINER_ID}:${container_real_flow_report}" "${real_flow_report}"',
        'logs --no-color app > "${COMPOSE_LOGS}"',
    ):
        assert fragment in text
    assert "if ! \"${COMPOSE_CMD[@]}\" exec -T app mkdir -p" in text
    assert "if ! docker cp \"${host_preflight_report}\"" in text
    assert "if ! docker cp \"${CONTAINER_ID}:${container_real_flow_report}\"" in text


def test_bash_script_guards_compose_build_and_up_and_records_diagnostics() -> None:
    text = _text(BASH_SCRIPT)
    assert 'if ! "${COMPOSE_CMD[@]}" build app; then' in text
    assert 'handle_compose_failure 1 "docker compose build failed"' in text
    assert 'if ! "${COMPOSE_CMD[@]}" up -d app; then' in text
    assert 'handle_compose_failure 1 "docker compose up failed"' in text
    assert 'COMPOSE_DIAGNOSTICS=' in text
    assert 'compose-diagnostics.txt' in text
    assert 'record_compose_diagnostics' in text
    assert 'failed_command=' in text


def test_bash_compose_failure_handler_tolerates_missing_container() -> None:
    text = _text(BASH_SCRIPT)
    assert 'if [[ -n "${CONTAINER_ID}" && -n "${REAL_FLOW_REPORT}" ]]; then' in text
    assert 'WARN could not copy container report' in text


def test_powershell_script_uses_property_helpers_instead_of_hashtable_access() -> None:
    text = _text(POWERSHELL_SCRIPT)
    assert "Get-ObjectProperty" in text
    assert "Get-ObjectChild" in text
    assert "Get-ValidatedPreflightSha" in text


def test_powershell_script_does_not_capture_success_stream_in_exit_expression() -> None:
    text = _text(POWERSHELL_SCRIPT)
    assert "exit (Invoke-ProductionReadinessMode)" not in text
    assert "Invoke-ProductionReadinessMode" in text
    assert 'Write-Host "RELEASE GATE FAILED"' in text
    assert 'Write-Host "production-readiness stopped before Docker and real flow."' in text
    assert "exit 1" in text
    assert 'Write-Host "RELEASE GATE PASSED (mode=$Mode)"' in text
    assert "exit 0" in text


def test_powershell_51_can_parse_and_reject_invalid_mode_without_parser_error() -> None:
    powershell = shutil.which("powershell.exe")
    if not powershell:
      return
    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(POWERSHELL_SCRIPT),
            "-Mode",
            "invalid",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    combined = f"{completed.stdout}\n{completed.stderr}"
    assert completed.returncode != 0
    assert "ParserError" not in combined
    assert "production-readiness" in combined or "ValidateSet" in combined
