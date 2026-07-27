from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "cli" / "preview_v2_production_readiness.py"
EXPECTED_TOP_LEVEL_FIELDS = [
    "final_readiness",
    "configuration",
    "docker_environment",
    "deterministic_suites",
    "prompt_variants",
    "model_preflights",
    "provider_calls",
    "phase3a",
    "candidate_generation",
    "call_budgets",
    "checkpoints",
    "generated_code_validation",
    "phase4",
    "phase5",
    "customer_security",
    "expanded_preview",
    "restart_resume",
    "failures",
    "artifacts",
    "required_next_action",
]


def _load_script_module() -> ModuleType:
    if not SCRIPT_PATH.is_file():
        pytest.fail(
            "expected preview readiness driver at "
            f"{SCRIPT_PATH.as_posix()}"
        )
    spec = importlib.util.spec_from_file_location(
        "preview_v2_production_readiness",
        SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:
        pytest.fail("failed to build import spec for preview readiness driver")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_bootstraps_backend_import_path_without_pythonpath() -> None:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        cwd=ROOT.parent,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def _mandatory_pass_checks(module: ModuleType) -> tuple[tuple[str, object], ...]:
    if not hasattr(module, "MANDATORY_CHECK_IDENTITIES"):
        pytest.fail("driver must expose MANDATORY_CHECK_IDENTITIES")
    if not hasattr(module, "CHECK_SECTION_BY_IDENTITY"):
        pytest.fail("driver must expose CHECK_SECTION_BY_IDENTITY")

    def _check_for(section_name: str):
        return lambda _report: {section_name: {"status": "pass"}}

    checks = tuple(
        (
            identity,
            _check_for(module.CHECK_SECTION_BY_IDENTITY[identity]),
        )
        for identity in module.MANDATORY_CHECK_IDENTITIES
    )
    return checks + (
        (
            "final-readiness",
            lambda _report: {
                "final_readiness": {
                    "ready": True,
                    "requirements_satisfied": True,
                    "summary": "all required checks passed",
                },
                "required_next_action": "",
            },
        ),
    )


def test_driver_writes_exact_report_schema_and_fails_closed_for_custom_checks(
    tmp_path,
) -> None:
    module = _load_script_module()
    report_path = tmp_path / "readiness.json"

    exit_code = module.run_preview_v2_production_readiness(
        report_path=report_path,
        checks=(
            (
                "final-readiness",
                lambda _report: {
                    "final_readiness": {
                        "ready": True,
                        "requirements_satisfied": True,
                        "summary": "fabricated custom success must fail closed",
                    },
                    "required_next_action": "",
                },
            ),
        ),
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert list(report) == EXPECTED_TOP_LEVEL_FIELDS
    assert report["artifacts"]["report_path"] == str(report_path)
    assert report["final_readiness"]["ready"] is False
    assert exit_code != 0


def test_driver_does_not_allow_full_dummy_mandatory_set_to_return_zero(
    tmp_path,
) -> None:
    module = _load_script_module()
    report_path = tmp_path / "readiness.json"

    exit_code = module.run_preview_v2_production_readiness(
        report_path=report_path,
        checks=_mandatory_pass_checks(module),
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code != 0
    assert report["final_readiness"]["ready"] is False
    assert report["required_next_action"]


def test_final_readiness_requires_restart_resume_pass_in_real_mode(tmp_path) -> None:
    module = _load_script_module()
    if not hasattr(module, "_build_report") or not hasattr(
        module, "_finalize_internal_readiness"
    ):
        pytest.fail("driver must expose readiness finalization helpers")

    report_path = tmp_path / "readiness.json"
    report = module._build_report(report_path)
    for section in (
        "configuration",
        "docker_environment",
        "deterministic_suites",
        "prompt_variants",
        "model_preflights",
        "candidate_generation",
        "provider_calls",
        "call_budgets",
        "checkpoints",
        "generated_code_validation",
        "customer_security",
        "expanded_preview",
        "phase4",
        "phase5",
    ):
        report[section] = {"status": "pass"}
    report["restart_resume"] = {
        "status": "deferred_external_deterministic_suite",
        "handoff_marker": "gate_supplied_suite_required",
    }

    exit_code = module._finalize_internal_readiness(
        report,
        preflight_only=False,
        run_real_http=True,
    )

    assert exit_code != 0
    assert "restart_resume did not pass" in report["final_readiness"]["blockers"]


def test_driver_persists_incrementally_and_preserves_report_path_on_failure(
    tmp_path,
) -> None:
    module = _load_script_module()
    report_path = tmp_path / "readiness.json"

    def _record_configuration(_report: dict) -> dict:
        return {
            "configuration": {
                "status": "ok",
                "notes": ["config snapshot persisted before later failure"],
            }
        }

    def _raise_failure(_report: dict) -> dict:
        raise RuntimeError("phase4 explosion with sk-secret-123")

    exit_code = module.run_preview_v2_production_readiness(
        report_path=report_path,
        checks=(
            ("configuration", _record_configuration),
            ("phase4", _raise_failure),
        ),
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code != 0
    assert report_path.is_file()
    assert not report_path.with_name(f"{report_path.name}.tmp").exists()
    assert report["artifacts"]["report_path"] == str(report_path)
    assert report["configuration"]["status"] == "ok"
    assert report["failures"][0]["stage"] == "phase4"
    assert "sk-secret-123" not in json.dumps(report)


def test_driver_redacts_prompts_provider_bodies_tokens_and_customer_private_data(
    tmp_path,
) -> None:
    module = _load_script_module()
    report_path = tmp_path / "readiness.json"

    exit_code = module.run_preview_v2_production_readiness(
        report_path=report_path,
        checks=(
            (
                "sensitive-payload",
                lambda report: {
                    "provider_calls": {
                        "prompt_text": "Build this for alice@example.com with token sk-live-123.",
                        "provider_request_body": {
                            "authorization": "Bearer secret-token",
                            "access_token": "customer-access-token",
                            "raw_response": "private provider body",
                        },
                    },
                    "customer_security": {
                        "customer_profile": {
                            "email": "alice@example.com",
                            "phone": "+1 (555) 123-4567",
                            "ssn": "123-45-6789",
                            "address": "123 Main Street",
                            "dob": "1990-01-01",
                            "account_number": "ACCT-99881",
                            "customer_id": 918273645,
                            "notes": "VIP customer private note",
                        }
                    },
                    "final_readiness": {
                        "ready": False,
                        "requirements_satisfied": False,
                    },
                    "required_next_action": "resolve_blockers",
                },
            ),
        ),
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    flattened = json.dumps(report)

    assert exit_code != 0
    assert "alice@example.com" not in flattened
    assert "sk-live-123" not in flattened
    assert "Bearer secret-token" not in flattened
    assert "customer-access-token" not in flattened
    assert "private provider body" not in flattened
    assert "123-45-6789" not in flattened
    assert "123 Main Street" not in flattened
    assert "1990-01-01" not in flattened
    assert "ACCT-99881" not in flattened
    assert "918273645" not in flattened
    assert "VIP customer private note" not in flattened
    assert "<redacted" in flattened


def test_atomic_persistence_cleans_temp_file_when_replace_fails(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_script_module()
    if not hasattr(module, "_build_report"):
        pytest.fail("driver must expose _build_report for atomic persistence coverage")
    if not hasattr(module, "_persist_report"):
        pytest.fail("driver must expose _persist_report for atomic persistence coverage")
    if not hasattr(module, "os"):
        pytest.fail("driver must import os for atomic persistence")
    report_path = tmp_path / "readiness.json"
    report = module._build_report(report_path)
    temp_path = report_path.with_name(f"{report_path.name}.tmp")
    real_replace = os.replace

    def _raising_replace(src: str, dst: str) -> None:
        assert Path(src) == temp_path
        assert Path(dst) == report_path
        raise OSError("replace failed")

    monkeypatch.setattr(module.os, "replace", _raising_replace)

    with pytest.raises(OSError, match="replace failed"):
        module._persist_report(report_path, report)

    assert not temp_path.exists()
    assert not report_path.exists()
    monkeypatch.setattr(module.os, "replace", real_replace)
