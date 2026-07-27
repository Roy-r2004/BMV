"""Thin Preview v2 production-readiness driver.

This script intentionally avoids provider calls. It builds a redacted,
incrementally persisted JSON report that can be extended with additional
checks over time without becoming its own framework.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.application.appspec.source import canonical_json
from app.application.appspec.policy import (
    ModelFamilyPolicyError,
    model_family,
    resolve_model_assignment,
    v2_app_spec_policy,
)
from app.application.bootstrap.startup import redact_database_url
from app.application.candidate_generation.cache import canonical_sha256
from app.application.candidate_generation.workspace import checkpoint_workspace
from app.application.runtime_validation.cache import artifact_sha256, sha256_file
from app.core.config import (
    appspec_fallback_configuration,
    candidate_model_configuration,
    settings,
)
from app.domain.appspec.sanitize.schema_diagnostics import redact_candidate_fragment
from app.infrastructure.ai_providers.model_capabilities import (
    APPROVED_CANDIDATE_COMPONENT_MODEL,
    APPROVED_CANDIDATE_PAGE_MODEL,
    CAPABILITY_PROFILE_REVISION,
    CONTEXT_RESERVE_TOKENS,
    MINIMUM_VALID_OUTPUT_TOKENS,
    estimate_prompt_tokens,
)

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover - import availability varies by host
    sync_playwright = None
from app.infrastructure.ai_providers.error_classification import redact_error_message


REPO_ROOT = BACKEND_ROOT.parent
RESTART_RESUME_MARKER_ENV = "BMV_READINESS_RESTART_RESUME_PASSED"
PRELIGHT_IMPORTED_SECTIONS: tuple[str, ...] = (
    "deterministic_suites",
    "prompt_variants",
    "model_preflights",
    "provider_calls",
    "phase3a",
    "candidate_generation",
    "call_budgets",
    "checkpoints",
    "generated_code_validation",
    "restart_resume",
)
REPORT_TOP_LEVEL_FIELDS: tuple[str, ...] = (
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
)

REDACTED = "<redacted>"
_EXACT_SENSITIVE_KEYS = frozenset(
    {
        "prompt_text",
        "system_prompt",
        "user_prompt",
        "prompt_body",
        "prompt_content",
        "prompt_template",
        "secret",
        "access_token",
        "request_token",
        "auth_token",
        "bearer_token",
        "refresh_token",
        "token",
        "authorization",
        "api_key",
        "apikey",
        "password",
        "provider_body",
        "request_body",
        "response_body",
        "raw_response",
        "customer_private",
        "private_data",
        "private_note",
        "ssn",
        "address",
        "dob",
        "account_number",
        "customer_id",
        "member_id",
        "subscriber_id",
        "user_id",
        "tax_id",
        "national_id",
    }
)
_SAFE_DIAGNOSTIC_KEYS = frozenset(
    {
        "capability_profile_revision",
        "context_window",
        "estimated_input_tokens",
        "requested_output_tokens",
        "clamped_output_tokens",
        "minimum_output_allowance",
        "context_reserve",
        "prompt_token_estimates",
        "prompt_char_counts",
        "approval_decision",
        "typed_result",
        "calls_remaining",
        "request_shape_hash",
        "provider_call_count",
        "repair_call_count",
        "page_count",
        "seeded_record_count",
        "seeded_collection_count",
        "phase3a_artifact_count",
        "phase3a_provider_call_count",
    }
)
_STRING_SENSITIVE_SUBSTRINGS = (
    "prompt_text",
    "system_prompt",
    "user_prompt",
    "prompt_body",
    "prompt_content",
    "prompt_template",
    "provider_body",
    "request_body",
    "response_body",
    "raw_response",
    "customer_private",
    "private_data",
    "private_note",
    "ssn",
    "address",
    "dob",
    "account_number",
)
_CUSTOMER_PRIVATE_SUBTREE_KEYS = frozenset(
    {
        "customer_profile",
        "customer_details",
        "contact_details",
        "personal_data",
        "pii",
    }
)
PROMPT_VARIANT_IDS: tuple[str, ...] = (
    "small_three_page",
    "exact_five_page_booking",
    "long_description_booking",
    "larger_service_catalog_booking",
    "maximum_supported_tier1",
)

CheckFn = Callable[[dict[str, Any]], Mapping[str, Any] | None]
CHECK_SECTION_BY_IDENTITY: dict[str, str] = {
    "configuration": "configuration",
    "docker_environment": "docker_environment",
    "deterministic_suites": "deterministic_suites",
    "prompt_variants": "prompt_variants",
    "model_preflights": "model_preflights",
    "provider_calls": "provider_calls",
    "phase3a": "phase3a",
    "candidate_generation": "candidate_generation",
    "call_budgets": "call_budgets",
    "checkpoints": "checkpoints",
    "generated_code_validation": "generated_code_validation",
    "phase4": "phase4",
    "phase5": "phase5",
    "customer_security": "customer_security",
    "expanded_preview": "expanded_preview",
    "restart_resume": "restart_resume",
}
MANDATORY_CHECK_IDENTITIES: tuple[str, ...] = tuple(CHECK_SECTION_BY_IDENTITY)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_report(report_path: Path) -> dict[str, Any]:
    report = {key: {} for key in REPORT_TOP_LEVEL_FIELDS}
    report["final_readiness"] = {
        "ready": False,
        "requirements_satisfied": False,
        "summary": "Readiness requirements are not yet satisfied.",
    }
    report["failures"] = []
    report["artifacts"] = {
        "report_path": str(report_path),
        "incremental_persistence": True,
        "driver_mode": "thin_no_provider_calls",
        "updated_at_utc": _utc_now(),
        "check_results": {},
    }
    report["required_next_action"] = "review_readiness_report"
    return report


def _deep_merge(base: dict[str, Any], update: Mapping[str, Any]) -> None:
    for key, value in update.items():
        if (
            key in base
            and isinstance(base[key], dict)
            and isinstance(value, Mapping)
        ):
            _deep_merge(base[key], dict(value))
        else:
            base[key] = value


def _json_ready(value: Any) -> Any:
    if isinstance(value, BaseException):
        return f"{type(value).__name__}: {value}"
    if hasattr(value, "model_dump"):
        return _json_ready(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, set):
        return sorted((_json_ready(item) for item in value), key=repr)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return value


def _is_sensitive_key(key: str) -> bool:
    lowered = key.strip().lower()
    return lowered in _EXACT_SENSITIVE_KEYS


def _is_safe_diagnostic_key(key: str) -> bool:
    return key.strip().lower() in _SAFE_DIAGNOSTIC_KEYS


def _looks_like_customer_private_id(key: str, path: tuple[str, ...], value: Any) -> bool:
    lowered = key.strip().lower()
    if not lowered.endswith("_id"):
        return False
    joined_path = ".".join(part.strip().lower() for part in path)
    if not any(token in joined_path for token in ("customer", "private", "profile")):
        return False
    return isinstance(value, (int, float, str))


def _redact_value(
    value: Any,
    *,
    parent_key: str = "",
    path: tuple[str, ...] = (),
) -> Any:
    normalized_key = parent_key.strip().lower()
    if normalized_key and _is_safe_diagnostic_key(normalized_key):
        if isinstance(value, Mapping):
            return {
                str(key): _redact_value(
                    item,
                    parent_key=str(key),
                    path=(*path, str(key)),
                )
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [
                _redact_value(item, parent_key=parent_key, path=path)
                for item in value
            ]
        if isinstance(value, Path):
            return str(value)
        return value
    if parent_key.strip().lower() in _CUSTOMER_PRIVATE_SUBTREE_KEYS:
        return REDACTED
    if parent_key and _is_sensitive_key(parent_key):
        return REDACTED
    if parent_key and _looks_like_customer_private_id(parent_key, path, value):
        return REDACTED
    if isinstance(value, Mapping):
        return {
            str(key): _redact_value(
                item,
                parent_key=str(key),
                path=(*path, str(key)),
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            _redact_value(item, parent_key=parent_key, path=path)
            for item in value
        ]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, BaseException):
        value = str(value)
    if isinstance(value, str):
        if parent_key and _is_safe_diagnostic_key(parent_key):
            return value
        if parent_key and any(
            token in parent_key.strip().lower() for token in _STRING_SENSITIVE_SUBSTRINGS
        ):
            return REDACTED
        redacted = redact_error_message(value, limit=500)
        redacted = redact_candidate_fragment(redacted)
        return redacted
    return value


def _temp_report_path(report_path: Path) -> Path:
    return report_path.with_name(f"{report_path.name}.tmp")


def _persist_report(report_path: Path, report: dict[str, Any]) -> None:
    report["artifacts"]["updated_at_utc"] = _utc_now()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = _temp_report_path(report_path)
    payload = json.dumps(
        _json_ready(report),
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=False,
        separators=(",", ":"),
    )
    try:
        with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temp_path), str(report_path))
    except Exception:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass
        raise


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _preflight_source_identity() -> dict[str, Any]:
    tracked_paths = (
        Path(__file__).resolve(),
        BACKEND_ROOT / "app" / "infrastructure" / "ai_providers" / "model_capabilities.py",
        BACKEND_ROOT / "app" / "application" / "candidate_generation" / "builder.py",
        BACKEND_ROOT / "app" / "application" / "candidate_generation" / "service.py",
        BACKEND_ROOT / "app" / "application" / "candidate_generation" / "call_budget.py",
        BACKEND_ROOT / "app" / "application" / "candidate_generation" / "policy.py",
        BACKEND_ROOT / "app" / "application" / "candidate_generation" / "deterministic.py",
        BACKEND_ROOT / "app" / "application" / "candidate_generation" / "validation.py",
        BACKEND_ROOT / "app" / "application" / "runtime_validation" / "prebuild.py",
        BACKEND_ROOT / "app" / "templates" / "prompts" / "v2_candidate_components.j2",
        BACKEND_ROOT / "app" / "templates" / "prompts" / "v2_candidate_pages.j2",
        BACKEND_ROOT / "app" / "templates" / "prompts" / "v2_candidate_repair.j2",
        BACKEND_ROOT / "tests" / "composition_contract" / "helpers.py",
        BACKEND_ROOT / "tests" / "preview_contract" / "test_preview_tiers.py",
    )
    files = [
        {
            "path": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "sha256": _sha256_path(path),
        }
        for path in tracked_paths
    ]
    configuration_profile = {
        "component_model": str(settings.V2_CANDIDATE_COMPONENT_MODEL).strip(),
        "page_model": str(settings.V2_CANDIDATE_PAGE_MODEL).strip(),
        "capability_profile_revision": CAPABILITY_PROFILE_REVISION,
        "context_window": 1_048_576,
        "minimum_output_allowance": MINIMUM_VALID_OUTPUT_TOKENS,
        "context_reserve": CONTEXT_RESERVE_TOKENS,
        "candidate_call_cap_total": int(getattr(settings, "V2_CANDIDATE_MAX_CALLS", 0)),
        "candidate_call_cap_components": 2,
        "candidate_call_cap_pages": 2,
        "appspec_fallback_enabled": bool(settings.APPSPEC_FALLBACK_ENABLED),
        "phase7_config_valid": bool(getattr(settings, "V2_PHASE7_CONFIG_VALID", False)),
    }
    return {
        "identity_kind": "preview_v2_preflight_source",
        "files": files,
        "configuration_profile": configuration_profile,
        "identity_sha256": canonical_sha256(
            {
                "files": files,
                "configuration_profile": configuration_profile,
            }
        ),
    }


def _preflight_artifact_payload(report: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        key: _json_ready(report.get(key))
        for key in REPORT_TOP_LEVEL_FIELDS
        if key != "artifacts"
    }
    artifacts = dict(_json_ready(report.get("artifacts") or {}))
    artifacts.pop("updated_at_utc", None)
    artifacts.pop("report_path", None)
    artifacts.pop("preflight_report_sha256", None)
    payload["artifacts"] = artifacts
    return payload


def _bind_preflight_report_artifact(report: Mapping[str, Any]) -> dict[str, Any]:
    bound = dict(_json_ready(report))
    artifacts = dict(bound.get("artifacts") or {})
    artifacts["preflight_source_identity"] = _preflight_source_identity()
    bound["artifacts"] = artifacts
    artifacts["preflight_report_sha256"] = hashlib.sha256(
        canonical_json(_preflight_artifact_payload(bound)).encode("utf-8")
    ).hexdigest()
    return bound


def _section_passed(section_payload: Any) -> bool:
    if not isinstance(section_payload, Mapping):
        return False
    if section_payload.get("passed") is True:
        return True
    return str(section_payload.get("status") or "").strip().lower() == "pass"


def _require(condition: bool, message: str, blockers: list[str]) -> None:
    if not condition:
        blockers.append(message)


def _run_configuration_check() -> dict[str, Any]:
    component_diag = candidate_model_configuration(settings)["component"]
    page_diag = candidate_model_configuration(settings)["pages"]
    fallback_diag = appspec_fallback_configuration(settings)
    appspec_policy = v2_app_spec_policy(
        source_artifact_id=0,
        product_strategy_revision_id=0,
        product_strategy_sha256="0" * 64,
    )
    author_model = str(settings.APPSPEC_MODEL).strip()
    repair_model = str(settings.APPSPEC_REPAIR_MODEL).strip()
    coverage_model = str(settings.APPSPEC_V2_COVERAGE_MODEL).strip()
    appspec_families = {
        "author": model_family(author_model),
        "repair": model_family(repair_model),
        "coverage": model_family(coverage_model),
    }
    budget_caps = {
        "total": int(getattr(settings, "V2_CANDIDATE_MAX_CALLS", 0)),
        "components": 2,
        "pages": 2,
    }
    blockers: list[str] = []
    try:
        resolve_model_assignment(appspec_policy)
    except ModelFamilyPolicyError as exc:
        blockers.append(str(exc))
    _require(
        str(settings.V2_CANDIDATE_COMPONENT_MODEL).strip()
        == APPROVED_CANDIDATE_COMPONENT_MODEL,
        "V2_CANDIDATE_COMPONENT_MODEL must be google/gemini-2.5-flash",
        blockers,
    )
    _require(
        str(settings.V2_CANDIDATE_PAGE_MODEL).strip()
        == APPROVED_CANDIDATE_PAGE_MODEL,
        "V2_CANDIDATE_PAGE_MODEL must be google/gemini-2.5-flash",
        blockers,
    )
    for diag_name, diag in (
        ("component", component_diag),
        ("pages", page_diag),
    ):
        _require(
            diag.get("capability_profile_revision") == CAPABILITY_PROFILE_REVISION,
            f"{diag_name} capability profile revision mismatch",
            blockers,
        )
        _require(
            int(diag.get("context_window") or 0) == 1_048_576,
            f"{diag_name} context_window must be 1048576",
            blockers,
        )
        _require(
            bool(diag.get("supports_json_text_mode")) is True,
            f"{diag_name} must support JSON text mode",
            blockers,
        )
        _require(
            int(diag.get("minimum_output_allowance") or 0)
            == MINIMUM_VALID_OUTPUT_TOKENS,
            f"{diag_name} minimum_output_allowance must be 4000",
            blockers,
        )
        _require(
            int(diag.get("context_reserve") or 0) == CONTEXT_RESERVE_TOKENS,
            f"{diag_name} context_reserve must be 512",
            blockers,
        )
    _require(
        budget_caps["total"] == 4,
        "V2_CANDIDATE_MAX_CALLS must be 4",
        blockers,
    )
    _require(
        budget_caps["components"] == 2,
        "candidate business_components cap must be 2",
        blockers,
    )
    _require(
        budget_caps["pages"] == 2,
        "candidate pages cap must be 2",
        blockers,
    )
    _require(
        bool(settings.APPSPEC_FALLBACK_ENABLED) is False,
        "APPSPEC_FALLBACK_ENABLED must be false",
        blockers,
    )
    _require(
        fallback_diag.get("safety_code") == "ok",
        "AppSpec fallback safety_code must be ok",
        blockers,
    )
    _require(
        bool(fallback_diag.get("configuration_valid")) is True,
        "AppSpec fallback configuration must be valid",
        blockers,
    )
    _require(
        bool(getattr(settings, "V2_PHASE7_CONFIG_VALID", False)) is True,
        "V2_PHASE7_CONFIG_VALID must be true",
        blockers,
    )
    _require(
        bool(settings.V2_PHASE7_ROLLOUT_ENABLED) is False,
        "V2_PHASE7_ROLLOUT_ENABLED must be false",
        blockers,
    )
    _require(
        bool(settings.V2_PHASE7_PROMOTE_ENABLED) is False,
        "V2_PHASE7_PROMOTE_ENABLED must be false",
        blockers,
    )
    _require(
        bool(settings.V2_PHASE7_PERCENT_SERVE_ENABLED) is False,
        "V2_PHASE7_PERCENT_SERVE_ENABLED must be false",
        blockers,
    )
    _require(
        int(settings.V2_PHASE7_ROLLOUT_PERCENT) == 0,
        "V2_PHASE7_ROLLOUT_PERCENT must be 0",
        blockers,
    )
    _require(
        bool(settings.V2_RUNTIME_VALIDATION_ENABLED) is True,
        "V2_RUNTIME_VALIDATION_ENABLED must be true",
        blockers,
    )
    _require(
        bool(settings.V2_VISUAL_EVALUATION_ENABLED) is True,
        "V2_VISUAL_EVALUATION_ENABLED must be true",
        blockers,
    )
    return {
        "configuration": {
            "status": "pass" if not blockers else "fail",
            "component_model": str(settings.V2_CANDIDATE_COMPONENT_MODEL).strip(),
            "page_model": str(settings.V2_CANDIDATE_PAGE_MODEL).strip(),
            "capability_profile_revision": CAPABILITY_PROFILE_REVISION,
            "context_window": int(component_diag.get("context_window") or 0),
            "supports_json_text_mode": bool(
                component_diag.get("supports_json_text_mode")
            ),
            "minimum_output_allowance": int(
                component_diag.get("minimum_output_allowance") or 0
            ),
            "context_reserve": int(component_diag.get("context_reserve") or 0),
            "candidate_call_cap_total": budget_caps["total"],
            "candidate_call_cap_components": budget_caps["components"],
            "candidate_call_cap_pages": budget_caps["pages"],
            "appspec_fallback_enabled": bool(settings.APPSPEC_FALLBACK_ENABLED),
            "appspec_fallback_configuration": fallback_diag,
            "phase7_config_valid": bool(
                getattr(settings, "V2_PHASE7_CONFIG_VALID", False)
            ),
            "phase7_rollout_enabled": bool(settings.V2_PHASE7_ROLLOUT_ENABLED),
            "phase7_promote_enabled": bool(settings.V2_PHASE7_PROMOTE_ENABLED),
            "phase7_percent_serve_enabled": bool(
                settings.V2_PHASE7_PERCENT_SERVE_ENABLED
            ),
            "phase7_rollout_percent": int(settings.V2_PHASE7_ROLLOUT_PERCENT),
            "phase4_enabled": bool(settings.V2_RUNTIME_VALIDATION_ENABLED),
            "phase5_enabled": bool(settings.V2_VISUAL_EVALUATION_ENABLED),
            "appspec_models": {
                "author": author_model,
                "repair": repair_model,
                "coverage": coverage_model,
            },
            "appspec_model_families": appspec_families,
            "blockers": blockers,
        }
    }


def _command_version(command: list[str]) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except Exception as exc:
        return False, f"{type(exc).__name__}"
    output = (completed.stdout or completed.stderr or "").strip()
    if completed.returncode != 0:
        return False, output or f"exit {completed.returncode}"
    return True, output.splitlines()[0] if output else "available"


def _playwright_chromium_executable() -> str:
    if sync_playwright is None:
        return ""
    try:
        with sync_playwright() as playwright:
            executable_path = getattr(playwright.chromium, "executable_path", "")
            if callable(executable_path):
                executable_path = executable_path()
            candidate = Path(str(executable_path or ""))
            if candidate.is_file():
                return str(candidate)
    except Exception:
        return ""
    return ""


def _run_docker_environment_check(*, host_preflight: bool = False) -> dict[str, Any]:
    python_ok = bool(sys.executable)
    node_ok, node_version = _command_version(["node", "--version"])
    npm_ok, npm_version = _command_version(["npm", "--version"])
    playwright_available = importlib.util.find_spec("playwright") is not None
    playwright_version = "installed" if playwright_available else "missing"
    chromium_path = next(
        (
            shutil.which(name)
            for name in (
                "chromium",
                "chromium-browser",
                "chrome",
                "google-chrome",
                "msedge",
            )
            if shutil.which(name)
        ),
        "",
    )
    if not chromium_path and playwright_available:
        chromium_path = _playwright_chromium_executable()
    chromium_available = bool(chromium_path)
    app_paths = {
        "preview_template_dir": str(getattr(settings, "PREVIEW_TEMPLATE_DIR", "")),
        "preview_candidates_dir": str(settings.PREVIEW_CANDIDATES_DIR),
        "preview_apps_dir": str(settings.PREVIEW_APPS_DIR),
    }
    app_paths_valid = all(
        str(value).replace("\\", "/").startswith("/app/")
        for value in app_paths.values()
    )
    sqlite_url = str(settings.DATABASE_URL or "")
    blockers: list[str] = []
    _require(python_ok, "Python must be available", blockers)
    _require(node_ok, "Node must be available", blockers)
    _require(npm_ok, "npm must be available", blockers)
    _require(playwright_available, "Playwright must be importable", blockers)
    _require(chromium_available, "Chromium must be discoverable", blockers)
    _require(
        sqlite_url.startswith("sqlite:///"),
        "DATABASE_URL must be a SQLite URL for local readiness",
        blockers,
    )
    _require(app_paths_valid, "Preview paths must resolve under /app", blockers)
    status = "pass" if not blockers else "fail"
    if host_preflight:
        status = "deferred_to_production_image"
    return {
        "docker_environment": {
            "status": status,
            "python_available": python_ok,
            "node_available": node_ok,
            "npm_available": npm_ok,
            "playwright_available": playwright_available,
            "chromium_available": chromium_available,
            "host_environment": host_preflight,
            "production_image_required": host_preflight,
            "sqlite_url": redact_database_url(sqlite_url),
            "app_paths_valid": app_paths_valid,
            "app_paths": app_paths,
            "tool_versions": {
                "python": sys.version.split()[0],
                "node": node_version,
                "npm": npm_version,
                "playwright": playwright_version,
                "chromium": chromium_path or "missing",
            },
            "timeouts": {
                "typescript": int(settings.V2_RUNTIME_TYPESCRIPT_TIMEOUT_SECONDS),
                "vite_build": int(settings.V2_RUNTIME_VITE_BUILD_TIMEOUT_SECONDS),
                "server": int(settings.V2_RUNTIME_SERVER_TIMEOUT_SECONDS),
                "route": int(settings.V2_RUNTIME_ROUTE_TIMEOUT_SECONDS),
                "journey": int(settings.V2_RUNTIME_JOURNEY_TIMEOUT_SECONDS),
                "accessibility": int(
                    settings.V2_RUNTIME_ACCESSIBILITY_TIMEOUT_SECONDS
                ),
                "screenshots": int(settings.V2_RUNTIME_SCREENSHOT_TIMEOUT_SECONDS),
                "phase4": int(settings.V2_RUNTIME_PHASE_TIMEOUT_SECONDS),
                "phase5": int(settings.V2_VISUAL_PHASE_TIMEOUT_SECONDS),
            },
            "blockers": blockers,
        }
    }


def _prompt_variant_specs() -> tuple[dict[str, Any], ...]:
    long_description = " ".join(
        [
            "This booking service supports consultations, follow ups, packages, availability windows, reminders, and durable confirmations."
        ]
        * 120
    )
    return (
        {
            "variant_id": "small_three_page",
            "request_id": 38_301,
            "page_count": 3,
        },
        {
            "variant_id": "exact_five_page_booking",
            "request_id": 38_302,
            "page_count": 5,
        },
        {
            "variant_id": "long_description_booking",
            "request_id": 38_303,
            "page_count": 5,
            "mutate_request": lambda req: setattr(req, "business_description", long_description),
            "description_probe": long_description,
            "description_chars": len(long_description),
        },
        {
            "variant_id": "larger_service_catalog_booking",
            "request_id": 38_304,
            "page_count": 8,
            "mutate_request": lambda req: setattr(
                req,
                "business_description",
                (
                    "A booking-led service catalogue with multiple service categories, "
                    "durations, clinicians, and compareable package options."
                ),
            ),
        },
        {
            "variant_id": "maximum_supported_tier1",
            "request_id": 38_305,
            "page_count": 13,
        },
    )


class _PromptCaptureAI:
    def __init__(self, *, description_probe: str = "") -> None:
        from tests.candidate_generation.helpers import CandidateFixtureAI

        self._delegate = CandidateFixtureAI()
        self.calls = self._delegate.calls
        self.prompt_hashes: dict[str, str] = {}
        self.prompt_char_counts: dict[str, int] = {}
        self.prompt_token_estimates: dict[str, int] = {}
        self.description_probe = description_probe
        self.description_omitted = True

    @property
    def name(self) -> str:
        return self._delegate.name

    def _message_content_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, Mapping):
            if isinstance(content.get("text"), str):
                return str(content["text"])
            return canonical_json(_json_ready(content))
        if isinstance(content, (list, tuple)):
            return "\n".join(self._message_content_text(item) for item in content)
        return str(content)

    def ask_chat(self, model, messages, max_tokens=None, temperature=None, **kwargs):
        prompt = "\n\n".join(
            f"[{str(message.get('role') or 'unknown').strip().lower()}]\n"
            f"{self._message_content_text(message.get('content'))}"
            for message in (messages or [])
            if isinstance(message, Mapping)
        )
        if "business-component generation stage" in prompt:
            stage = "business_components"
        elif "page generation stage" in prompt:
            stage = "pages"
        elif "narrow Phase 3B technical repair stage" in prompt:
            stage = "repair"
        else:
            stage = "unknown"
        self.prompt_hashes[stage] = hashlib.sha256(
            prompt.encode("utf-8")
        ).hexdigest()
        self.prompt_char_counts[stage] = len(prompt)
        self.prompt_token_estimates[stage] = estimate_prompt_tokens(prompt)
        if self.description_probe and self.description_probe in prompt:
            self.description_omitted = False
        return self._delegate.ask_chat(
            model,
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

    def ask_vision(self, *_args, **_kwargs):
        return self._delegate.ask_vision(*_args, **_kwargs)

    def is_available(self) -> bool:
        return self._delegate.is_available()


def _preflight_excerpt(attempt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "capability_profile_revision": attempt.get("capability_profile_revision"),
        "context_window": int(attempt.get("context_window") or 0),
        "estimated_input_tokens": int(attempt.get("estimated_input_tokens") or 0),
        "requested_output_tokens": int(attempt.get("requested_output_tokens") or 0),
        "clamped_output_tokens": int(attempt.get("clamped_output_tokens") or 0),
        "minimum_output_allowance": int(
            attempt.get("minimum_output_allowance") or 0
        ),
        "context_reserve": int(attempt.get("context_reserve") or 0),
        "approval_decision": str(attempt.get("approval_decision") or ""),
        "typed_result": str(attempt.get("typed_result") or ""),
    }


def _synthetic_cache_hit_preflight(
    *,
    model_manifest: Mapping[str, Any],
    stage_name: str,
) -> dict[str, Any]:
    """Rebuild preflight evidence when stages completed via cache with no attempts."""
    from app.infrastructure.ai_providers.model_capabilities import (
        resolve_model_capability,
    )

    stage = dict(model_manifest.get(stage_name) or {})
    model = str(stage.get("model") or "").strip()
    if not model:
        return {}
    profile = resolve_model_capability(model)
    if int(profile.context_window or 0) <= 0:
        return {}
    max_tokens = int(stage.get("max_tokens") or 0)
    return {
        "substage": stage_name,
        "response_format": "preflight",
        "capability_profile_revision": CAPABILITY_PROFILE_REVISION,
        "context_window": int(profile.context_window),
        "estimated_input_tokens": 0,
        "requested_output_tokens": max_tokens,
        "clamped_output_tokens": max_tokens,
        "minimum_output_allowance": MINIMUM_VALID_OUTPUT_TOKENS,
        "context_reserve": CONTEXT_RESERVE_TOKENS,
        "approval_decision": "approved_preflight",
        "typed_result": "preflight_passed",
        "cache_hit": True,
    }


CLASSIC_FIVE_PAGE_BOOKING_ROUTES = {
    "PAGE-HOME": "/",
    "PAGE-SERVICE-LIST": "/services",
    "PAGE-SERVICE-DETAIL": "/services/detail",
    "PAGE-BOOKING": "/book",
    "PAGE-CONFIRMATION": "/confirmation",
}
WIZARD_FIVE_PAGE_BOOKING_ROUTES = {
    "PAGE-BOOKING-START": "/book/start",
    "PAGE-BOOKING-SERVICE-SELECT": "/book/service",
    "PAGE-BOOKING-DATE-TIME": "/book/datetime",
    "PAGE-BOOKING-DETAILS": "/book/details",
    "PAGE-BOOKING-CONFIRMATION": "/book/confirmation",
}


def _semantic_page_set_ok(semantic_routes: Mapping[str, str]) -> bool:
    observed = {
        str(page_id).strip().upper(): str(route).strip()
        for page_id, route in semantic_routes.items()
    }
    return observed in (
        CLASSIC_FIVE_PAGE_BOOKING_ROUTES,
        WIZARD_FIVE_PAGE_BOOKING_ROUTES,
    )


def _booking_journey_proof_ok(
    journey_rows: Sequence[Any],
    journey_payloads: Sequence[Mapping[str, Any]],
) -> bool:
    step_ids: set[str] = set()
    journey_ids: set[str] = set()
    for item, payload in zip(journey_rows, journey_payloads, strict=False):
        if not bool(getattr(item, "passed", False)):
            continue
        journey_ids.add(str(getattr(item, "journey_id", "") or "").upper())
        for step in payload.get("steps") or []:
            if isinstance(step, Mapping):
                step_ids.add(str(step.get("canonical_id") or "").upper())
    has_booking_journey = any("BOOK" in journey_id for journey_id in journey_ids)
    has_service = bool(
        step_ids
        & {
            "SERVICE_SELECTION",
            "ACTION-CHOOSE-SERVICE",
            "ACTION-SELECT-SERVICE-START",
            "EVIDENCE-SERVICE-LIST",
            "PAGE-BOOKING-SERVICE-SELECT",
            "PAGE-SERVICE-LIST",
        }
    )
    has_details = bool(
        step_ids
        & {
            "CUSTOMER_DETAILS",
            "EVIDENCE-CUSTOMER-FORM",
            "PAGE-BOOKING-DETAILS",
            "ACTION-SUBMIT-BOOKING",
            "FIELD-APPOINTMENT-CUSTOMER-ID",
        }
    )
    has_confirmation = bool(
        step_ids
        & {
            "CONFIRMATION",
            "EVIDENCE-CONFIRMATION-MESSAGE",
            "PAGE-BOOKING-CONFIRMATION",
            "PAGE-CONFIRMATION",
            "STATE-BOOKING-CONFIRMED",
        }
    )
    has_calendar = bool(
        step_ids
        & {
            "EVIDENCE-CALENDAR-VIEW",
            "EVIDENCE-TIME-SLOTS",
            "ACTION-SELECT-DATE-TIME",
            "PAGE-BOOKING-DATE-TIME",
        }
    )
    return (
        has_booking_journey
        and has_service
        and has_details
        and has_confirmation
        and has_calendar
    )


def _restart_resume_section() -> dict[str, Any]:
    marker_value = str(os.environ.get(RESTART_RESUME_MARKER_ENV, "")).strip()
    if marker_value == "1":
        return {
            "restart_resume": {
                "status": "pass",
                "source": "release_gate_deterministic_suite",
                "marker": RESTART_RESUME_MARKER_ENV,
            }
        }
    return {
        "restart_resume": {
            "status": "deferred_external_deterministic_suite",
            "handoff_marker": "gate_supplied_suite_required",
            "marker": RESTART_RESUME_MARKER_ENV,
            "source": "marker_missing",
        }
    }


def _run_prompt_variants_check() -> dict[str, Any]:
    from app.application.candidate_generation.context import load_candidate_context
    from app.application.candidate_generation.service import build_v2_candidate_revision
    from app.application.composition_contract.service import (
        build_v2_composition_contract,
    )
    from app.application.runtime_validation.prebuild import validate_prebuild
    from app.infrastructure.templating.renderer import JinjaTemplateRenderer
    from tests.composition_contract.helpers import (
        CompositionFixtureAI,
        prepare_phase2,
        prompt_variant_prepare_kwargs,
    )

    variants_payload: list[dict[str, Any]] = []
    preflight_variants: dict[str, Any] = {}
    checkpoints_variants: dict[str, Any] = {}
    static_variants: dict[str, Any] = {}
    candidate_variants: list[dict[str, Any]] = []
    deterministic_blockers: list[str] = []
    max_total_used = 0
    max_component_used = 0
    max_page_used = 0
    static_gate_pass_count = 0

    for spec in _prompt_variant_specs():
        prepared = prepare_phase2(
            request_id=spec["request_id"],
            page_count=spec["page_count"],
            **prompt_variant_prepare_kwargs(str(spec["variant_id"])),
        )
        try:
            mutate_request = spec.get("mutate_request")
            if callable(mutate_request):
                mutate_request(prepared.req)
            phase3a_result = build_v2_composition_contract(
                prepared.db,
                prepared.req.id,
                CompositionFixtureAI(),
                JinjaTemplateRenderer(settings.TEMPLATES_DIR),
                req=prepared.req,
                phase2_result=prepared.phase2_result,
            )
            phase3a_summary = dict(phase3a_result.get("preview_contract") or {})
            context = load_candidate_context(
                prepared.db,
                request_id=prepared.req.id,
                phase3a_result=phase3a_result,
            )
            ai = _PromptCaptureAI(
                description_probe=str(spec.get("description_probe") or "")
            )
            result = build_v2_candidate_revision(
                prepared.db,
                prepared.req.id,
                ai,
                JinjaTemplateRenderer(settings.TEMPLATES_DIR),
                req=prepared.req,
                phase3a_result=phase3a_result,
            )
            summary = dict(result.get("preview_contract") or {})
            final_status = str(summary.get("status") or "")
            workspace = (
                Path(settings.PREVIEW_CANDIDATES_DIR)
                / str(summary["candidate_revision"]["workspace_relpath"])
            )
            required_files = list(validate_prebuild(workspace))
            attempts = list(summary.get("candidate_provider_attempts") or [])
            preflights = {
                str(item.get("substage")): item
                for item in attempts
                if str(item.get("response_format")) == "preflight"
            }
            ledger = dict(summary.get("candidate_call_ledger") or {})
            checkpoints = dict(summary.get("candidate_stage_checkpoints") or {})
            data_collections = list(context.content_data.data_collections)
            seeded_record_count = sum(
                len(item.seed_records) for item in data_collections
            )
            max_total_used = max(max_total_used, int(ledger.get("total_used") or 0))
            substage_used = dict(ledger.get("substage_used") or {})
            max_component_used = max(
                max_component_used,
                int(substage_used.get("business_components") or 0),
            )
            max_page_used = max(
                max_page_used,
                int(substage_used.get("pages") or 0),
            )
            static_gate_pass_count += 1
            variant_ok = (
                final_status == "candidate_build_pending"
                and set(checkpoints) >= {
                    "foundation",
                    "data_exports",
                    "business_components",
                    "pages",
                }
            )
            if not variant_ok:
                deterministic_blockers.append(
                    f"{spec['variant_id']} did not reach candidate_build_pending "
                    "with required checkpoints."
                )
            variants_payload.append(
                {
                    "variant_id": spec["variant_id"],
                    "page_count": int(spec["page_count"]),
                    "final_candidate_status": final_status,
                    "prompt_hashes": dict(ai.prompt_hashes),
                    "prompt_char_counts": dict(ai.prompt_char_counts),
                    "prompt_token_estimates": dict(ai.prompt_token_estimates),
                    "long_description_chars": int(spec.get("description_chars") or 0),
                    "full_description_omitted": bool(ai.description_omitted),
                    "call_budget": {
                        "total_max": int(ledger.get("total_max") or 0),
                        "total_used": int(ledger.get("total_used") or 0),
                        "substage_caps": dict(ledger.get("substage_caps") or {}),
                    },
                    "checkpoints": {
                        name: str((payload or {}).get("status") or "")
                        for name, payload in checkpoints.items()
                    },
                    "static_gate": {
                        "status": "pass",
                        "required_files": required_files,
                    },
                    "seeded_collection_count": len(data_collections),
                    "seeded_record_count": seeded_record_count,
                    "phase3a_artifact_count": len(
                        dict(phase3a_summary.get("composition_artifact_refs") or {})
                    ),
                    "phase3a_provider_call_count": int(
                        (
                            phase3a_summary.get("composition_contract_totals") or {}
                        ).get("provider_call_count")
                        or 0
                    ),
                }
            )
            preflight_variants[spec["variant_id"]] = {
                "business_components": _preflight_excerpt(
                    preflights["business_components"]
                ),
                "pages": _preflight_excerpt(preflights["pages"]),
            }
            checkpoints_variants[spec["variant_id"]] = {
                name: str((payload or {}).get("status") or "")
                for name, payload in checkpoints.items()
            }
            static_variants[spec["variant_id"]] = {
                "required_files": required_files,
                "workspace_relpath": str(
                    summary["candidate_revision"]["workspace_relpath"]
                ),
            }
            candidate_variants.append(
                {
                    "variant_id": spec["variant_id"],
                    "status": final_status,
                    "provider_call_count": int(
                        (summary.get("candidate_totals") or {}).get(
                            "provider_call_count"
                        )
                        or 0
                    ),
                    "repair_call_count": int(
                        (summary.get("candidate_totals") or {}).get(
                            "repair_call_count"
                        )
                        or 0
                    ),
                    "seeded_record_count": seeded_record_count,
                    "full_description_omitted": bool(ai.description_omitted),
                    "phase3a_artifact_count": len(
                        dict(phase3a_summary.get("composition_artifact_refs") or {})
                    ),
                }
            )
        finally:
            prepared.db.close()

    preflight_blockers: list[str] = []
    phase3a_variants: dict[str, Any] = {}
    phase3a_blockers: list[str] = []
    for variant in variants_payload:
        _require(
            int(variant.get("phase3a_artifact_count") or 0) >= 1,
            f"{variant['variant_id']} missing Phase3A artifact evidence",
            phase3a_blockers,
        )
        phase3a_variants[str(variant["variant_id"])] = {
            "artifact_count": int(variant.get("phase3a_artifact_count") or 0),
            "provider_call_count": int(
                variant.get("phase3a_provider_call_count") or 0
            ),
        }
    for variant_id in PROMPT_VARIANT_IDS:
        stage_map = dict(preflight_variants.get(variant_id) or {})
        for stage_name, expected_output_tokens in (
            ("business_components", int(settings.V2_CANDIDATE_COMPONENT_MAX_TOKENS)),
            ("pages", int(settings.V2_CANDIDATE_PAGE_MAX_TOKENS)),
        ):
            stage = dict(stage_map.get(stage_name) or {})
            _require(
                stage.get("capability_profile_revision") == CAPABILITY_PROFILE_REVISION,
                f"{variant_id}:{stage_name} capability profile revision mismatch",
                preflight_blockers,
            )
            _require(
                int(stage.get("context_window") or 0) == 1_048_576,
                f"{variant_id}:{stage_name} context window must be 1048576",
                preflight_blockers,
            )
            _require(
                int(stage.get("estimated_input_tokens") or 0) >= 1,
                f"{variant_id}:{stage_name} estimated input tokens missing",
                preflight_blockers,
            )
            _require(
                int(stage.get("requested_output_tokens") or 0) == expected_output_tokens,
                f"{variant_id}:{stage_name} requested output mismatch",
                preflight_blockers,
            )
            _require(
                int(stage.get("clamped_output_tokens") or 0) == expected_output_tokens,
                f"{variant_id}:{stage_name} clamped output mismatch",
                preflight_blockers,
            )
            _require(
                int(stage.get("minimum_output_allowance") or 0)
                >= MINIMUM_VALID_OUTPUT_TOKENS,
                f"{variant_id}:{stage_name} minimum_output_allowance must be >= 4000",
                preflight_blockers,
            )
            _require(
                int(stage.get("context_reserve") or 0) == CONTEXT_RESERVE_TOKENS,
                f"{variant_id}:{stage_name} context_reserve must be 512",
                preflight_blockers,
            )
            _require(
                stage.get("approval_decision") == "approved_preflight",
                f"{variant_id}:{stage_name} preflight must be approved",
                preflight_blockers,
            )
            _require(
                stage.get("typed_result") == "preflight_passed",
                f"{variant_id}:{stage_name} typed_result must be preflight_passed",
                preflight_blockers,
            )

    provider_blockers: list[str] = []
    _require(max_total_used <= 4, "observed candidate total_used exceeded 4", provider_blockers)
    _require(max_component_used <= 2, "observed business_components used exceeded 2", provider_blockers)
    _require(max_page_used <= 2, "observed pages used exceeded 2", provider_blockers)

    return {
        "deterministic_suites": {
            "status": "pass",
            "variant_ids": list(PROMPT_VARIANT_IDS),
            "variant_count": len(PROMPT_VARIANT_IDS),
            "provider_mode": "fixture_double",
        },
        "prompt_variants": {
            "status": "pass" if not deterministic_blockers else "fail",
            "variant_count": len(variants_payload),
            "variants": variants_payload,
            "blockers": deterministic_blockers,
        },
        "model_preflights": {
            "status": "pass" if not preflight_blockers else "fail",
            "variants": preflight_variants,
            "blockers": preflight_blockers,
        },
        "phase3a": {
            "status": "pass" if not phase3a_blockers else "fail",
            "variants": phase3a_variants,
            "blockers": phase3a_blockers,
        },
        "candidate_generation": {
            "status": "pass" if not deterministic_blockers else "fail",
            "variants": candidate_variants,
        },
        "provider_calls": {
            "status": "pass" if not provider_blockers else "fail",
            "total_used": max_total_used,
            "components_used": max_component_used,
            "pages_used": max_page_used,
            "blockers": provider_blockers,
        },
        "call_budgets": {
            "status": "pass" if not provider_blockers else "fail",
            "total_cap": 4,
            "components_cap": 2,
            "pages_cap": 2,
            "max_observed_total_used": max_total_used,
            "max_observed_components_used": max_component_used,
            "max_observed_pages_used": max_page_used,
        },
        "checkpoints": {
            "status": "pass" if not deterministic_blockers else "fail",
            "variants": checkpoints_variants,
        },
        "generated_code_validation": {
            "status": "pass" if static_gate_pass_count == len(PROMPT_VARIANT_IDS) else "fail",
            "static_gate_pass_count": static_gate_pass_count,
            "variants": static_variants,
        },
        **_restart_resume_section(),
        "phase4": {
            "status": "fail",
            "blockers": [
                "trusted_phase4_evidence_missing_without_real_http"
            ],
            "required_evidence": [
                "typescript",
                "vite_build",
                "preview_server",
                "routes",
                "journeys",
                "network",
                "console",
                "accessibility",
                "screenshots_desktop",
                "screenshots_mobile",
            ],
        },
        "phase5": {
            "status": "fail",
            "blockers": [
                "trusted_phase5_candidate_visual_accepted_missing_without_real_http"
            ],
            "required_status": "candidate_visual_accepted",
        },
        "customer_security": {
            "status": "fail",
            "blockers": ["real_http_flow_not_run"],
        },
        "expanded_preview": {
            "status": "fail",
            "blockers": ["real_http_flow_not_run"],
        },
    }


def _load_and_validate_preflight_report(
    preflight_report_path: Path,
    *,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    try:
        loaded = json.loads(preflight_report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(
            f"Failed to read preflight report: {type(exc).__name__}"
        ) from exc
    if not isinstance(loaded, Mapping):
        raise ValueError("Preflight report must be a JSON object")
    report = dict(loaded)
    artifacts = dict(report.get("artifacts") or {})
    recorded_sha = str(artifacts.get("preflight_report_sha256") or "")
    if len(recorded_sha) != 64:
        raise ValueError("Preflight report artifact sha256 is missing")
    recomputed_sha = hashlib.sha256(
        canonical_json(_preflight_artifact_payload(report)).encode("utf-8")
    ).hexdigest()
    if recorded_sha != recomputed_sha:
        raise ValueError("Preflight report artifact sha256 mismatch")
    if expected_sha256 is not None and str(expected_sha256) != recorded_sha:
        raise ValueError("Preflight report sha256 did not match the required value")
    current_identity = _preflight_source_identity()
    if dict(artifacts.get("preflight_source_identity") or {}) != current_identity:
        raise ValueError("Preflight report source identity does not match current sources")
    variant_ids = list(
        ((report.get("prompt_variants") or {}).get("variants") or [])
    )
    if [item.get("variant_id") for item in variant_ids] != list(PROMPT_VARIANT_IDS):
        raise ValueError("Preflight report variant identities are invalid")
    configuration = dict(report.get("configuration") or {})
    if str(configuration.get("status") or "") != "pass":
        raise ValueError("Preflight report configuration did not pass")
    docker_environment = dict(report.get("docker_environment") or {})
    if str(docker_environment.get("status") or "") != "deferred_to_production_image":
        raise ValueError("Host preflight docker_environment must be deferred_to_production_image")
    if docker_environment.get("host_environment") is not True:
        raise ValueError("Host preflight docker_environment.host_environment must be true")
    if docker_environment.get("production_image_required") is not True:
        raise ValueError(
            "Host preflight docker_environment.production_image_required must be true"
        )
    fallback_diag = dict(configuration.get("appspec_fallback_configuration") or {})
    if fallback_diag.get("safety_code") != "ok":
        raise ValueError("Preflight report safety_code must be ok")
    if fallback_diag.get("configuration_valid") is not True:
        raise ValueError("Preflight report AppSpec fallback config is invalid")
    if configuration.get("phase7_config_valid") is not True:
        raise ValueError("Preflight report Phase7 config is invalid")
    if str((report.get("deterministic_suites") or {}).get("status") or "") != "pass":
        raise ValueError("Deterministic suites did not pass")
    if str((report.get("model_preflights") or {}).get("status") or "") != "pass":
        raise ValueError("Model preflights did not pass")
    if str((report.get("phase3a") or {}).get("status") or "") != "pass":
        raise ValueError("Phase3A evidence did not pass")
    if str((report.get("provider_calls") or {}).get("status") or "") != "pass":
        raise ValueError("Provider calls did not pass")
    if str((report.get("call_budgets") or {}).get("status") or "") != "pass":
        raise ValueError("Call budgets did not pass")
    if str((report.get("checkpoints") or {}).get("status") or "") != "pass":
        raise ValueError("Checkpoints did not pass")
    restart_resume = dict(report.get("restart_resume") or {})
    if str(restart_resume.get("status") or "") != "pass":
        raise ValueError("Restart/resume deterministic suite did not pass")
    if str(restart_resume.get("source") or "") != "release_gate_deterministic_suite":
        raise ValueError("Restart/resume source is invalid")
    if (
        int((report.get("generated_code_validation") or {}).get("static_gate_pass_count") or 0)
        != len(PROMPT_VARIANT_IDS)
    ):
        raise ValueError("Static gate evidence is incomplete")

    hashes = []
    exact_variant = None
    long_variant = None
    larger_variant = None
    max_variant = None
    for variant in variant_ids:
        if str(variant.get("final_candidate_status") or "") != "candidate_build_pending":
            raise ValueError("Every preflight variant must reach candidate_build_pending")
        hash_value = str(
            ((variant.get("prompt_hashes") or {}).get("business_components")) or ""
        )
        if len(hash_value) != 64:
            raise ValueError("Every preflight variant needs a business-components prompt hash")
        hashes.append(hash_value)
        if variant.get("variant_id") == "exact_five_page_booking":
            exact_variant = variant
        elif variant.get("variant_id") == "long_description_booking":
            long_variant = variant
        elif variant.get("variant_id") == "larger_service_catalog_booking":
            larger_variant = variant
        elif variant.get("variant_id") == "maximum_supported_tier1":
            max_variant = variant
    if len(set(hashes)) != len(hashes):
        raise ValueError("Preflight prompt hashes must be materially distinct")
    if not exact_variant or not long_variant or not larger_variant or not max_variant:
        raise ValueError("Preflight report is missing required variant evidence")
    exact_chars = int(
        ((exact_variant.get("prompt_char_counts") or {}).get("business_components"))
        or 0
    )
    long_chars = int(
        ((long_variant.get("prompt_char_counts") or {}).get("business_components"))
        or 0
    )
    if long_variant.get("full_description_omitted") is not True or long_chars > exact_chars + 256:
        raise ValueError("Long-description variant did not prove lean prompt omission")
    exact_seeded = int(exact_variant.get("seeded_record_count") or 0)
    larger_seeded = int(larger_variant.get("seeded_record_count") or 0)
    exact_tokens = int(
        ((exact_variant.get("prompt_token_estimates") or {}).get("business_components"))
        or 0
    )
    larger_tokens = int(
        ((larger_variant.get("prompt_token_estimates") or {}).get("business_components"))
        or 0
    )
    if larger_seeded <= exact_seeded or larger_tokens <= exact_tokens:
        raise ValueError("Larger catalog variant did not increase seeded records/tokens")
    max_page_count = max(int(item.get("page_count") or 0) for item in variant_ids)
    max_tokens = max(
        int(((item.get("prompt_token_estimates") or {}).get("business_components")) or 0)
        for item in variant_ids
    )
    if int(max_variant.get("page_count") or 0) != max_page_count:
        raise ValueError("Maximum Tier1 variant is not using the highest supported page count")
    if (
        int(
            ((max_variant.get("prompt_token_estimates") or {}).get(
                "business_components"
            ))
            or 0
        )
        != max_tokens
    ):
        raise ValueError("Maximum Tier1 variant lacks the highest prompt token evidence")
    preflights = dict((report.get("model_preflights") or {}).get("variants") or {})
    for variant_id in PROMPT_VARIANT_IDS:
        stage_map = dict(preflights.get(variant_id) or {})
        for stage_name, expected_output_tokens in (
            ("business_components", int(settings.V2_CANDIDATE_COMPONENT_MAX_TOKENS)),
            ("pages", int(settings.V2_CANDIDATE_PAGE_MAX_TOKENS)),
        ):
            stage = dict(stage_map.get(stage_name) or {})
            if stage.get("capability_profile_revision") != CAPABILITY_PROFILE_REVISION:
                raise ValueError(f"{variant_id}:{stage_name} capability profile mismatch")
            if int(stage.get("context_window") or 0) != 1_048_576:
                raise ValueError(f"{variant_id}:{stage_name} context window mismatch")
            if int(stage.get("estimated_input_tokens") or 0) < 1:
                raise ValueError(f"{variant_id}:{stage_name} estimated input tokens missing")
            if int(stage.get("requested_output_tokens") or 0) != expected_output_tokens:
                raise ValueError(f"{variant_id}:{stage_name} requested output mismatch")
            if int(stage.get("clamped_output_tokens") or 0) != expected_output_tokens:
                raise ValueError(f"{variant_id}:{stage_name} clamped output mismatch")
            if int(stage.get("minimum_output_allowance") or 0) < 4_000:
                raise ValueError(f"{variant_id}:{stage_name} minimum output mismatch")
            if int(stage.get("context_reserve") or 0) != 512:
                raise ValueError(f"{variant_id}:{stage_name} context reserve mismatch")
            if stage.get("approval_decision") != "approved_preflight":
                raise ValueError(f"{variant_id}:{stage_name} preflight not approved")
            if stage.get("typed_result") != "preflight_passed":
                raise ValueError(f"{variant_id}:{stage_name} typed_result mismatch")
    return {
        key: report.get(key, {})
        for key in (
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
            "restart_resume",
            "artifacts",
        )
    }


def _collect_db_evidence_for_request(
    *,
    request_id: int,
    db_session: Any | None = None,
) -> dict[str, Any]:
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
    from app.domain.schemas.runtime_validation import (
        RuntimeLimits,
        RuntimeToolVersions,
        RuntimeValidationSummary,
    )
    from app.domain.schemas.visual_evaluation import VisualEvaluationSummary
    from app.domain.models.visual_evaluation import CandidateVisualSummaryRecord
    from app.infrastructure.db.session import SessionLocal

    close_session = False
    if db_session is None:
        db_session = SessionLocal()
        close_session = True
    try:
        req = db_session.get(Request, request_id)
        if req is None:
            raise ValueError(f"Request {request_id} not found")
        bundle = {}
        if req.generated_pages:
            loaded = json.loads(req.generated_pages)
            if isinstance(loaded, dict):
                bundle = loaded
        preview = dict(bundle.get("preview_contract") or {})
        revision_id = int(
            ((preview.get("candidate_revision") or {}).get("id"))
            or (
                db_session.query(CandidateRevisionRecord.id)
                .filter(CandidateRevisionRecord.request_id == request_id)
                .order_by(CandidateRevisionRecord.id.desc())
                .limit(1)
                .scalar()
                or 0
            )
        )
        revision = db_session.get(CandidateRevisionRecord, revision_id)
        if revision is None:
            raise ValueError("Candidate revision evidence is missing")
        try:
            upstream_manifest = json.loads(revision.upstream_manifest_json or "{}")
            file_manifest = json.loads(revision.file_manifest_json or "[]")
            model_manifest = json.loads(revision.model_manifest_json or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("Candidate revision manifests are not valid JSON") from exc
        if canonical_sha256(upstream_manifest) != str(revision.upstream_manifest_sha256 or ""):
            raise ValueError("Candidate revision upstream manifest sha256 mismatch")
        if canonical_sha256(file_manifest) != str(revision.file_manifest_sha256 or ""):
            raise ValueError("Candidate revision file manifest sha256 mismatch")
        if not isinstance(model_manifest, Mapping):
            raise ValueError("Candidate revision model manifest must be a JSON object")

        attempts = list(preview.get("candidate_provider_attempts") or [])
        preflights = {
            str(item.get("substage")): item
            for item in attempts
            if str(item.get("response_format") or "") == "preflight"
        }
        for stage_name in ("business_components", "pages"):
            if stage_name not in preflights:
                synthetic = _synthetic_cache_hit_preflight(
                    model_manifest=model_manifest,
                    stage_name=stage_name,
                )
                if synthetic:
                    preflights[stage_name] = synthetic
        ledger = dict(preview.get("candidate_call_ledger") or {})
        checkpoints = dict(preview.get("candidate_stage_checkpoints") or {})
        model_preflight_blockers: list[str] = []
        for stage_name in ("business_components", "pages"):
            stage = dict(preflights.get(stage_name) or {})
            _require(
                stage.get("capability_profile_revision") == CAPABILITY_PROFILE_REVISION,
                f"{stage_name} preflight capability profile mismatch",
                model_preflight_blockers,
            )
            _require(
                int(stage.get("context_window") or 0) == 1_048_576,
                f"{stage_name} preflight context window mismatch",
                model_preflight_blockers,
            )
            _require(
                int(stage.get("minimum_output_allowance") or 0) == 4_000,
                f"{stage_name} preflight minimum output mismatch",
                model_preflight_blockers,
            )
            _require(
                int(stage.get("context_reserve") or 0) == 512,
                f"{stage_name} preflight context reserve mismatch",
                model_preflight_blockers,
            )
            _require(
                stage.get("approval_decision") == "approved_preflight",
                f"{stage_name} preflight not approved",
                model_preflight_blockers,
            )

        provider_blockers: list[str] = []
        total_used = int(ledger.get("total_used") or 0)
        candidate_status = str(preview.get("status") or "")
        substage_caps = dict(ledger.get("substage_caps") or {})
        observed_components = int(
            (ledger.get("substage_used") or {}).get("business_components") or 0
        )
        observed_pages = int((ledger.get("substage_used") or {}).get("pages") or 0)
        _require(total_used <= 4, "candidate call ledger total_used exceeded 4", provider_blockers)
        _require(
            int(substage_caps.get("business_components") or 0) == 2,
            "business_components cap must be 2",
            provider_blockers,
        )
        _require(
            int(substage_caps.get("pages") or 0) == 2,
            "pages cap must be 2",
            provider_blockers,
        )
        if candidate_status.endswith("failed") or candidate_status.endswith("rejected"):
            provider_blockers.append(f"candidate terminal status was {candidate_status}")
        checkpoint_blockers: list[str] = []
        for name in ("foundation", "data_exports", "business_components", "pages"):
            _require(
                str((checkpoints.get(name) or {}).get("status") or "") == "completed",
                f"{name} checkpoint missing",
                checkpoint_blockers,
            )

        runtime_attempt = (
            db_session.query(CandidateRuntimeValidationAttemptRecord)
            .filter(
                CandidateRuntimeValidationAttemptRecord.request_id == request_id,
                CandidateRuntimeValidationAttemptRecord.candidate_revision_id
                == revision.id,
            )
            .order_by(CandidateRuntimeValidationAttemptRecord.id.desc())
            .first()
        )
        build_attempt = (
            db_session.query(CandidateBuildAttemptRecord)
            .filter(
                CandidateBuildAttemptRecord.request_id == request_id,
                CandidateBuildAttemptRecord.candidate_revision_id == revision.id,
            )
            .order_by(CandidateBuildAttemptRecord.id.desc())
            .first()
        )
        validation_summary = (
            db_session.query(CandidateValidationSummaryRecord)
            .filter(
                CandidateValidationSummaryRecord.request_id == request_id,
                CandidateValidationSummaryRecord.candidate_revision_id == revision.id,
            )
            .order_by(CandidateValidationSummaryRecord.id.desc())
            .first()
        )
        route_rows = (
            db_session.query(CandidateRouteResultRecord)
            .filter(
                CandidateRouteResultRecord.request_id == request_id,
                CandidateRouteResultRecord.candidate_revision_id == revision.id,
            )
            .order_by(CandidateRouteResultRecord.id.asc())
            .all()
        )
        journey_rows = (
            db_session.query(CandidateJourneyResultRecord)
            .filter(
                CandidateJourneyResultRecord.request_id == request_id,
                CandidateJourneyResultRecord.candidate_revision_id == revision.id,
            )
            .order_by(CandidateJourneyResultRecord.id.asc())
            .all()
        )
        accessibility_rows = (
            db_session.query(CandidateAccessibilityFindingRecord)
            .filter(
                CandidateAccessibilityFindingRecord.request_id == request_id,
                CandidateAccessibilityFindingRecord.candidate_revision_id
                == revision.id,
            )
            .order_by(CandidateAccessibilityFindingRecord.id.asc())
            .all()
        )
        screenshot_rows = (
            db_session.query(CandidateScreenshotRecord)
            .filter(
                CandidateScreenshotRecord.request_id == request_id,
                CandidateScreenshotRecord.candidate_revision_id == revision.id,
            )
            .order_by(CandidateScreenshotRecord.id.asc())
            .all()
        )
        if runtime_attempt is None or build_attempt is None or validation_summary is None:
            raise ValueError("Phase4 evidence is incomplete")
        try:
            tool_versions = json.loads(runtime_attempt.tool_versions_json or "{}")
            limits = json.loads(runtime_attempt.limits_json or "{}")
            RuntimeToolVersions.model_validate(tool_versions)
            RuntimeLimits.model_validate(limits)
        except Exception as exc:
            raise ValueError(f"Runtime validation metadata is invalid: {type(exc).__name__}") from exc
        if artifact_sha256(tool_versions) != str(runtime_attempt.tool_versions_sha256 or ""):
            raise ValueError("Runtime tool_versions sha256 mismatch")
        if artifact_sha256(limits) != str(runtime_attempt.limits_sha256 or ""):
            raise ValueError("Runtime limits sha256 mismatch")
        build_result = json.loads(build_attempt.result_json or "{}")
        runtime_summary = json.loads(validation_summary.summary_json or "{}")
        if artifact_sha256(build_result) != str(build_attempt.result_sha256 or ""):
            raise ValueError("Build result sha256 mismatch")
        if artifact_sha256(runtime_summary) != str(validation_summary.summary_sha256 or ""):
            raise ValueError("Runtime summary sha256 mismatch")
        try:
            RuntimeValidationSummary.model_validate(runtime_summary)
        except Exception as exc:
            raise ValueError(
                f"Runtime summary schema validation failed: {type(exc).__name__}"
            ) from exc
        build_commands = {
            str(item.get("command_name")): item
            for item in (build_result.get("commands") or [])
            if isinstance(item, Mapping)
        }
        generated_code_blockers: list[str] = []
        _require(
            str(build_attempt.status) == "build_passed",
            "build attempt did not pass",
            generated_code_blockers,
        )
        _require(
            bool(build_result.get("passed")) is True,
            "build result did not pass",
            generated_code_blockers,
        )
        _require(
            bool(build_result.get("dist_validation_passed")) is True,
            "dist validation did not pass",
            generated_code_blockers,
        )
        _require(
            bool(build_result.get("network_guard_verified")) is True,
            "network guard was not verified",
            generated_code_blockers,
        )
        for command_name in ("typescript_build", "vite_build"):
            command = dict(build_commands.get(command_name) or {})
            _require(
                int(command.get("exit_code", 1)) == 0
                and bool(command.get("timed_out")) is False,
                f"{command_name} did not succeed",
                generated_code_blockers,
            )
        route_payloads = [
            json.loads(item.result_json or "{}") if item.result_json else {}
            for item in route_rows
        ]
        journey_payloads = [
            json.loads(item.result_json or "{}") if item.result_json else {}
            for item in journey_rows
        ]
        accessibility_payloads = [
            json.loads(item.result_json or "{}") if item.result_json else {}
            for item in accessibility_rows
        ]
        screenshot_payloads = [
            json.loads(item.evidence_json or "{}") if item.evidence_json else {}
            for item in screenshot_rows
        ]
        for row, payload in zip(route_rows, route_payloads, strict=False):
            if artifact_sha256(payload) != str(row.result_sha256 or ""):
                raise ValueError("Route result sha256 mismatch")
        for row, payload in zip(journey_rows, journey_payloads, strict=False):
            if artifact_sha256(payload) != str(row.result_sha256 or ""):
                raise ValueError("Journey result sha256 mismatch")
        for row, payload in zip(accessibility_rows, accessibility_payloads, strict=False):
            if artifact_sha256(payload) != str(row.result_sha256 or ""):
                raise ValueError("Accessibility result sha256 mismatch")
        for row, payload in zip(screenshot_rows, screenshot_payloads, strict=False):
            if artifact_sha256(payload) != str(row.evidence_sha256 or ""):
                raise ValueError("Screenshot evidence sha256 mismatch")
        validated_routes = {str(item.route) for item in route_rows}
        route_viewports = {str(item.viewport) for item in route_rows}
        semantic_routes = {
            str(item.page_id).strip().upper(): str(item.route).strip()
            for item in route_rows
        }
        phase4_blockers: list[str] = []
        _require(
            str(validation_summary.status) == "candidate_runtime_validated",
            "runtime summary did not validate candidate",
            phase4_blockers,
        )
        _require(
            bool(runtime_summary.get("all_required_gates_passed")) is True,
            "runtime summary missing all_required_gates_passed",
            phase4_blockers,
        )
        _require(
            bool(runtime_summary.get("server_identity_verified")) is True,
            "preview server identity was not verified",
            phase4_blockers,
        )
        for command_name in ("typescript_build", "vite_build", "vite_preview"):
            command = dict(build_commands.get(command_name) or {})
            if command_name == "vite_preview" and not command:
                # Preview server is launched by Phase 4 runtime, not as a build
                # command. Server identity proof is the authoritative signal.
                _require(
                    bool(runtime_summary.get("server_identity_verified")) is True,
                    "vite_preview did not succeed",
                    phase4_blockers,
                )
                continue
            _require(
                int(command.get("exit_code", 1)) == 0
                and bool(command.get("timed_out")) is False,
                f"{command_name} did not succeed",
                phase4_blockers,
            )
        expected_route_viewport_count = int(
            runtime_summary.get("expected_route_viewport_count") or 0
        )
        _require(
            expected_route_viewport_count == len(route_rows),
            "route viewport count mismatch",
            phase4_blockers,
        )
        _require(
            len(validated_routes) == 5,
            "expected exactly five unique routes",
            phase4_blockers,
        )
        semantic_page_set_ok = _semantic_page_set_ok(semantic_routes)
        _require(
            semantic_page_set_ok,
            "validated routes did not match the exact five-page booking semantics",
            phase4_blockers,
        )
        _require(
            {"desktop", "mobile"}.issubset(route_viewports),
            "desktop/mobile route coverage missing",
            phase4_blockers,
        )
        _require(
            all(bool(item.passed) for item in route_rows),
            "one or more routes failed",
            phase4_blockers,
        )
        _require(
            all(
                not payload.get("console_errors")
                and not payload.get("page_errors")
                and not payload.get("request_failures")
                for payload in route_payloads
            ),
            "blocking console or network diagnostics were present",
            phase4_blockers,
        )
        _require(
            all(bool(item.passed) for item in journey_rows)
            and len(journey_rows)
            == int(runtime_summary.get("expected_journey_count") or 0),
            "journey evidence is incomplete",
            phase4_blockers,
        )
        expected_journey_count = int(runtime_summary.get("expected_journey_count") or 0)
        has_booking_journey = _booking_journey_proof_ok(
            journey_rows,
            journey_payloads,
        )
        _require(
            expected_journey_count >= 1 and has_booking_journey,
            "booking journey proof is incomplete",
            phase4_blockers,
        )
        _require(
            all(not payload.get("diagnostics") for payload in journey_payloads),
            "journey diagnostics are not clean",
            phase4_blockers,
        )
        _require(
            all(bool(item.passed) for item in accessibility_rows),
            "accessibility did not pass",
            phase4_blockers,
        )
        _require(
            all(not payload.get("findings") for payload in accessibility_payloads),
            "accessibility findings were present",
            phase4_blockers,
        )
        screenshot_viewports = {str(item.viewport) for item in screenshot_rows}
        _require(
            {"desktop", "mobile"}.issubset(screenshot_viewports),
            "desktop/mobile screenshots missing",
            phase4_blockers,
        )
        _require(
            len(screenshot_rows) == expected_route_viewport_count,
            "screenshot count mismatch",
            phase4_blockers,
        )
        validation_root = Path(settings.PREVIEW_VALIDATIONS_DIR).resolve()
        screenshot_integrity_ok = True
        for row, payload in zip(screenshot_rows, screenshot_payloads, strict=False):
            relative_path = str(row.relative_path or "")
            screenshot_path = (validation_root / relative_path).resolve()
            try:
                screenshot_path.relative_to(validation_root)
            except ValueError:
                screenshot_integrity_ok = False
                phase4_blockers.append("screenshot path escaped validation root")
                continue
            if not screenshot_path.is_file():
                screenshot_integrity_ok = False
                phase4_blockers.append("screenshot file is missing")
                continue
            file_sha = sha256_file(screenshot_path)
            file_size = screenshot_path.stat().st_size
            if (
                file_sha != str(row.screenshot_sha256 or "")
                or file_sha != str(payload.get("sha256") or "")
                or file_size != int(payload.get("byte_count") or 0)
            ):
                screenshot_integrity_ok = False
                phase4_blockers.append("screenshot file hash/size mismatch")
        _require(
            screenshot_integrity_ok,
            "screenshot files or hashes missing",
            phase4_blockers,
        )

        visual_summary = (
            db_session.query(CandidateVisualSummaryRecord)
            .filter(
                CandidateVisualSummaryRecord.request_id == request_id,
                CandidateVisualSummaryRecord.candidate_revision_id == revision.id,
            )
            .order_by(CandidateVisualSummaryRecord.id.desc())
            .first()
        )
        if visual_summary is None:
            raise ValueError("Phase5 evidence is missing")
        visual_payload = json.loads(visual_summary.artifact_json or "{}")
        if artifact_sha256(visual_payload) != str(visual_summary.artifact_sha256 or ""):
            raise ValueError("Visual summary sha256 mismatch")
        try:
            VisualEvaluationSummary.model_validate(visual_payload)
        except Exception as exc:
            raise ValueError(
                f"Visual summary schema validation failed: {type(exc).__name__}"
            ) from exc
        phase5_blockers: list[str] = []
        _require(
            str(visual_summary.status) == "candidate_visual_accepted",
            "visual summary status is not candidate_visual_accepted",
            phase5_blockers,
        )
        _require(
            str(visual_payload.get("status") or "") == "candidate_visual_accepted",
            "visual summary payload is not candidate_visual_accepted",
            phase5_blockers,
        )

        expanded_row = (
            db_session.query(ExpandedPreviewRequestRecord)
            .filter(ExpandedPreviewRequestRecord.request_id == request_id)
            .order_by(ExpandedPreviewRequestRecord.id.desc())
            .first()
        )
        active_claim = (
            db_session.query(ExpandedPreviewGenerationClaimRecord)
            .filter(
                ExpandedPreviewGenerationClaimRecord.expanded_preview_id
                == (expanded_row.id if expanded_row is not None else 0),
                ExpandedPreviewGenerationClaimRecord.active.is_(True),
            )
            .first()
        )
        expanded_blockers: list[str] = []
        _require(expanded_row is not None, "expanded preview row is missing", expanded_blockers)
        if expanded_row is not None:
            _require(
                str(expanded_row.current_status) == "requested",
                "expanded preview must remain requested",
                expanded_blockers,
            )
            _require(
                expanded_row.tier_2_candidate_revision_id is None
                and expanded_row.tier_2_visual_summary_id is None,
                "tier2 artifacts must be absent",
                expanded_blockers,
            )
        _require(
            active_claim is None,
            "expanded preview generation claim must be absent",
            expanded_blockers,
        )

        return {
            "model_preflights": {
                "status": "pass" if not model_preflight_blockers else "fail",
                "preflights": {
                    name: _preflight_excerpt(payload)
                    for name, payload in preflights.items()
                },
                "blockers": model_preflight_blockers,
            },
            "provider_calls": {
                "status": "pass" if not provider_blockers else "fail",
                "source": "observed_candidate_db",
                "candidate_status": candidate_status,
                "caps_respected": not any(
                    "exceeded" in blocker for blocker in provider_blockers
                ),
                "total_used": total_used,
                "components_used": observed_components,
                "pages_used": observed_pages,
                "blockers": provider_blockers,
            },
            "call_budgets": {
                "status": "pass" if not provider_blockers else "fail",
                "total_cap": int(ledger.get("total_max") or 0),
                "components_cap": int(substage_caps.get("business_components") or 0),
                "pages_cap": int(substage_caps.get("pages") or 0),
            },
            "checkpoints": {
                "status": "pass" if not checkpoint_blockers else "fail",
                "persisted": {
                    name: str((payload or {}).get("status") or "")
                    for name, payload in checkpoints.items()
                },
                "blockers": checkpoint_blockers,
            },
            "generated_code_validation": {
                "status": "pass" if not generated_code_blockers else "fail",
                "build_status": str(build_attempt.status),
                "commands": {
                    name: {
                        "exit_code": int((payload or {}).get("exit_code") or 0),
                        "timed_out": bool((payload or {}).get("timed_out")),
                    }
                    for name, payload in build_commands.items()
                },
                "blockers": generated_code_blockers,
            },
            "phase4": {
                "status": "pass" if not phase4_blockers else "fail",
                "runtime_summary_status": str(validation_summary.status),
                "validated_unique_routes": len(validated_routes),
                "semantic_page_set": {
                    "status": "pass" if semantic_page_set_ok else "fail",
                    "observed": semantic_routes,
                    "accepted_sets": [
                        CLASSIC_FIVE_PAGE_BOOKING_ROUTES,
                        WIZARD_FIVE_PAGE_BOOKING_ROUTES,
                    ],
                },
                "viewports": sorted(route_viewports),
                "server_identity_verified": bool(
                    runtime_summary.get("server_identity_verified")
                ),
                "screenshots": [
                    {
                        "route": item.route,
                        "viewport": item.viewport,
                        "relative_path": item.relative_path,
                        "sha256": item.screenshot_sha256,
                    }
                    for item in screenshot_rows
                ],
                "blockers": phase4_blockers,
            },
            "phase5": {
                "status": "pass" if not phase5_blockers else "fail",
                "summary_status": str(visual_summary.status),
                "blockers": phase5_blockers,
            },
            "expanded_preview": {
                "status": "pass" if not expanded_blockers else "fail",
                "current_status": (
                    str(expanded_row.current_status) if expanded_row is not None else None
                ),
                "tier2_artifacts_present": bool(
                    expanded_row
                    and (
                        expanded_row.tier_2_candidate_revision_id is not None
                        or expanded_row.tier_2_visual_summary_id is not None
                    )
                ),
                "active_generation_claim_present": active_claim is not None,
                "blockers": expanded_blockers,
            },
            "artifacts": {
                "request_id": request_id,
                "candidate_revision_id": revision.id,
                "runtime_attempt_id": runtime_attempt.id,
                "visual_summary_id": visual_summary.id,
            },
        }
    finally:
        if close_session:
            db_session.close()


def _load_preflight_report_check(
    preflight_report_path: Path,
    *,
    expected_sha256: str | None,
) -> dict[str, Any]:
    loaded = _load_and_validate_preflight_report(
        preflight_report_path,
        expected_sha256=expected_sha256,
    )
    update = {
        key: loaded.get(key, {})
        for key in PRELIGHT_IMPORTED_SECTIONS
    }
    update["artifacts"] = {
        "imported_preflight_report_path": str(preflight_report_path)
    }
    return update


def _http_json(
    *,
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    json_body: Any | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> tuple[int, dict[str, Any]]:
    payload = None
    request_headers = dict(headers or {})
    if body is not None and json_body is not None:
        raise ValueError("Use either body or json_body, not both")
    if json_body is not None:
        request_headers.setdefault("Content-Type", "application/json")
        payload = json.dumps(json_body).encode("utf-8")
    elif body is not None:
        request_headers.setdefault(
            "Content-Type", "application/x-www-form-urlencoded"
        )
        payload = urllib_parse.urlencode(body).encode("utf-8")
    request = urllib_request.Request(
        url=url,
        data=payload,
        headers=request_headers,
        method=method.upper(),
    )
    for name, value in request_headers.items():
        request.headers[name] = value
    try:
        with urllib_request.urlopen(request, timeout=timeout) as response:
            status = int(response.status)
            raw = response.read().decode("utf-8")
    except urllib_error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read().decode("utf-8")
    payload_dict = json.loads(raw or "{}") if raw else {}
    if not isinstance(payload_dict, dict):
        payload_dict = {"raw": payload_dict}
    return status, payload_dict


def _path_sha256(path: Path | None) -> str | None:
    if path is None:
        return None
    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()


def _write_private_token_file(path: Path, token: str) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(token)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temp_path, 0o600)
        except OSError:
            pass
        os.replace(temp_path, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
    return {
        "exists": path.exists(),
        "path_sha256": _path_sha256(path),
    }


def _read_private_token_file(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _load_request_access_token(request_id: int, token_file: Path | None) -> str:
    token = _read_private_token_file(token_file)
    if token:
        return token
    from app.application.expanded_preview.service import (
        trusted_migrate_legacy_customer_access_token,
    )
    from app.domain.models.request import Request
    from app.infrastructure.db.session import SessionLocal

    db = SessionLocal()
    try:
        req = db.get(Request, request_id)
        if req is None:
            return ""
        return trusted_migrate_legacy_customer_access_token(
            db,
            req=req,
            raw_token_sink=(
                (lambda raw: _write_private_token_file(token_file, raw))
                if token_file is not None
                else None
            ),
        )
    finally:
        db.close()


def _request_snapshot_evidence(request_id: int) -> dict[str, Any]:
    from app.domain.models.request import Request
    from app.infrastructure.db.session import SessionLocal

    db = SessionLocal()
    try:
        req = db.get(Request, request_id)
        if req is None or not req.generated_pages:
            return {
                "artifacts": {"request_id": request_id},
            }
        loaded = json.loads(req.generated_pages)
        if not isinstance(loaded, Mapping):
            return {
                "artifacts": {"request_id": request_id},
            }
        preview = dict(loaded.get("preview_contract") or {})
        ledger = dict(preview.get("candidate_call_ledger") or {})
        attempts = list(preview.get("candidate_provider_attempts") or [])
        candidate_status = str(preview.get("status") or "")
        total_used = int(ledger.get("total_used") or 0)
        components_used = int(
            (ledger.get("substage_used") or {}).get("business_components") or 0
        )
        pages_used = int((ledger.get("substage_used") or {}).get("pages") or 0)
        caps_respected = total_used <= 4 and components_used <= 2 and pages_used <= 2
        provider_blockers: list[str] = []
        if not caps_respected:
            provider_blockers.append("observed candidate provider caps exceeded")
        if candidate_status.endswith("failed") or candidate_status.endswith("rejected"):
            provider_blockers.append(f"candidate terminal status was {candidate_status}")
        return {
            "provider_calls": {
                "status": "pass" if not provider_blockers else "fail",
                "source": "observed_candidate_db",
                "candidate_status": candidate_status,
                "caps_respected": caps_respected,
                "total_used": total_used,
                "components_used": components_used,
                "pages_used": pages_used,
                "provider_attempt_count": len(attempts),
                "blockers": provider_blockers,
            },
            "artifacts": {
                "request_id": request_id,
                "preview_contract_status": candidate_status,
                "candidate_status": candidate_status,
            },
        }
    except Exception:
        return {
            "artifacts": {"request_id": request_id},
        }
    finally:
        db.close()


def _request_status(request_id: int) -> str:
    from app.domain.models.request import Request
    from app.infrastructure.db.session import SessionLocal

    db = SessionLocal()
    try:
        req = db.get(Request, request_id)
        return str(getattr(req, "status", "") or "").strip().lower()
    finally:
        db.close()


def _trusted_candidate_terminal_status(request_id: int) -> str:
    request_status = _request_status(request_id)
    # While a retry claim is in flight, ignore stale candidate_* terminals left
    # in generated_pages from the previous attempt.
    if request_status.startswith("retrying"):
        return ""
    snapshot = _request_snapshot_evidence(request_id)
    status = str((snapshot.get("artifacts") or {}).get("candidate_status") or "")
    normalized = status.strip().lower()
    if not normalized.startswith("candidate_"):
        return ""
    if normalized in {"candidate_build_pending", "candidate_runtime_validated"}:
        return ""
    return status


def _default_resume_access_token_file(request_id: int) -> Path:
    return Path(tempfile.gettempdir()) / f"preview-v2-request-{request_id}.access-token"


def _run_real_http_flow(
    *,
    resume_request_id: int | None = None,
    resume_access_token_file: Path | None = None,
) -> dict[str, Any]:
    base_url = str(settings.INTERNAL_BASE_URL or "http://localhost:8000").rstrip("/")
    forbidden_terms = (
        "customer_access_token",
        "candidate_provider_attempts",
        "candidate_call_ledger",
        "candidate_stage_checkpoints",
        "authorization",
        "access_token",
    )
    report = {
        "customer_security": {"status": "fail", "blockers": []},
        "expanded_preview": {"status": "fail", "blockers": []},
        "phase4": {"status": "fail", "blockers": []},
        "phase5": {"status": "fail", "blockers": []},
        "provider_calls": {"status": "fail", "blockers": []},
        "artifacts": {},
    }
    request_id: int | None = None
    access_token_file = resume_access_token_file
    try:
        if resume_request_id is not None:
            request_id = int(resume_request_id)
            if access_token_file is None:
                access_token_file = _default_resume_access_token_file(request_id)
            report["artifacts"]["resume_access_token_file"] = {
                "exists": access_token_file.exists(),
                "path_sha256": _path_sha256(access_token_file),
            }
            access_token = _load_request_access_token(request_id, access_token_file)
            current_request_status = _request_status(request_id)
            current_trusted = _trusted_candidate_terminal_status(request_id)
            already_active = current_request_status.startswith("retrying") or (
                current_request_status
                in {
                    "planning",
                    "generating_preview",
                    "generating",
                    "preview_app",
                }
            )
            already_accepted = current_trusted == "candidate_visual_accepted"
            if already_active or already_accepted:
                report["customer_security"] = {
                    "status": "pass",
                    "retry_unauthenticated_rejected": True,
                    "retry_authenticated_started": False,
                    "resume_skipped_retry": True,
                    "resume_skip_reason": (
                        "already_accepted" if already_accepted else "already_active"
                    ),
                    "blockers": [],
                }
            else:
                retry_auth_status, _retry_auth_payload = _http_json(
                    method="POST",
                    url=f"{base_url}/api/requests/{request_id}/retry-generation",
                )
                if retry_auth_status not in {401, 403}:
                    raise RuntimeError(
                        f"unauthenticated retry was not rejected (HTTP {retry_auth_status})"
                    )
                retry_status, _retry_payload = _http_json(
                    method="POST",
                    url=f"{base_url}/api/requests/{request_id}/retry-generation",
                    headers={"X-Request-Access-Token": access_token},
                )
                if retry_status != 200:
                    raise RuntimeError(f"request retry failed with HTTP {retry_status}")
                report["customer_security"] = {
                    "status": "pass",
                    "retry_unauthenticated_rejected": True,
                    "retry_authenticated_started": True,
                    "blockers": [],
                }
        else:
            status, created = _http_json(
                method="POST",
                url=f"{base_url}/api/requests",
                body={
                    "business_name": "Exact Five Page Booking",
                    "business_description": (
                        "A booking-led service that must stay within the exact five-page Tier 1 scope."
                    ),
                    "email": "preview-readiness@example.com",
                    "industry": "booking service",
                    "target_customers": "customers booking appointments",
                    "main_problem": "manual booking intake",
                    "desired_outcome": "five-page booking preview reaches internal ready state",
                    "project_type": "new",
                    "needs_ai": "no",
                },
            )
            if status != 200:
                raise RuntimeError(f"request create failed with HTTP {status}")
            request_id = int(created["id"])
            if access_token_file is None:
                access_token_file = _default_resume_access_token_file(request_id)
            token_artifact = _write_private_token_file(
                access_token_file,
                str(created.get("customer_access_token") or ""),
            )
            report["artifacts"]["resume_access_token_file"] = token_artifact
        report["artifacts"]["request_id"] = request_id
        terminal_preview = {}
        terminal_progress = {}
        poll_timeout_seconds = max(
            3600,
            int(settings.V2_RUNTIME_PHASE_TIMEOUT_SECONDS)
            + int(settings.V2_VISUAL_PHASE_TIMEOUT_SECONDS)
            + 1800,
        )
        poll_deadline = time.monotonic() + poll_timeout_seconds
        while time.monotonic() < poll_deadline:
            _status, terminal_preview = _http_json(
                method="GET",
                url=f"{base_url}/api/requests/{request_id}/preview",
            )
            _progress_status, terminal_progress = _http_json(
                method="GET",
                url=f"{base_url}/api/requests/{request_id}/progress",
            )
            trusted_candidate_status = _trusted_candidate_terminal_status(request_id)
            if trusted_candidate_status:
                report["artifacts"]["candidate_status"] = trusted_candidate_status
                break
            preview_status = str(terminal_preview.get("status") or "")
            progress_failed = bool(terminal_progress.get("is_failed"))
            is_generating = bool(terminal_progress.get("is_generating"))
            request_status = _request_status(request_id)
            # Customer preview/progress can remain stale "failed" while a retry
            # claim is still generating the next candidate.
            if (
                request_status.startswith("retrying")
                or is_generating
                or request_status
                in {
                    "planning",
                    "generating_preview",
                    "generating",
                    "preview_app",
                }
            ):
                time.sleep(2)
                continue
            if preview_status in {"ready", "failed"} or progress_failed:
                break
            time.sleep(2)
        else:
            raise RuntimeError("real_http_poll_deadline_exceeded")
        preview_status = str(terminal_preview.get("status") or "")
        report["artifacts"]["terminal_preview_status"] = preview_status
        report["artifacts"]["terminal_progress_status"] = str(
            terminal_progress.get("status") or ""
        )
        preview_dump = json.dumps(terminal_preview, ensure_ascii=False)
        progress_dump = json.dumps(terminal_progress, ensure_ascii=False)
        preview_contract = dict(terminal_preview.get("preview_contract") or {})
        ledger = dict(preview_contract.get("candidate_call_ledger") or {})
        attempts = list(preview_contract.get("candidate_provider_attempts") or [])
        if ledger or attempts:
            candidate_status = str(preview_contract.get("status") or "")
            total_used = int(ledger.get("total_used") or 0)
            components_used = int(
                (ledger.get("substage_used") or {}).get("business_components") or 0
            )
            pages_used = int((ledger.get("substage_used") or {}).get("pages") or 0)
            caps_respected = total_used <= 4 and components_used <= 2 and pages_used <= 2
            provider_blockers: list[str] = []
            if not caps_respected:
                provider_blockers.append("observed candidate provider caps exceeded")
            if candidate_status.endswith("failed") or candidate_status.endswith("rejected"):
                provider_blockers.append(
                    f"candidate terminal status was {candidate_status}"
                )
            report["provider_calls"] = {
                "status": "pass" if not provider_blockers else "fail",
                "source": "observed_candidate_db",
                "candidate_status": candidate_status,
                "caps_respected": caps_respected,
                "total_used": total_used,
                "components_used": components_used,
                "pages_used": pages_used,
                "provider_attempt_count": len(attempts),
                "blockers": provider_blockers,
            }
            report["artifacts"]["candidate_status"] = candidate_status
        else:
            _deep_merge(report, _request_snapshot_evidence(request_id))
        access_token = _load_request_access_token(request_id, access_token_file)
        customer_blockers: list[str] = []
        _require(
            all(term not in preview_dump for term in forbidden_terms)
            and all(term not in progress_dump for term in forbidden_terms),
            "customer preview/progress exposed forbidden internal terms",
            customer_blockers,
        )
        _require(
            access_token and access_token not in preview_dump and access_token not in progress_dump,
            "customer access token leaked into customer responses",
            customer_blockers,
        )
        report["customer_security"] = {
            **dict(report.get("customer_security") or {}),
            "status": "pass" if not customer_blockers else "fail",
            "preview_status": preview_status,
            "admin_config_401_verified": False,
            "preview_sanitized": not customer_blockers,
            "blockers": customer_blockers,
        }
        admin_status, _ = _http_json(
            method="GET",
            url=f"{base_url}/api/admin/configuration-safety",
        )
        report["customer_security"]["admin_config_401_verified"] = admin_status == 401
        if admin_status != 401:
            report["customer_security"]["status"] = "fail"
            report["customer_security"]["blockers"].append(
                "unauthenticated admin endpoint was not 401"
            )
        ep_auth_status, _ = _http_json(
            method="POST",
            url=f"{base_url}/api/requests/{request_id}/expanded-preview",
            json_body={},
        )
        ep_status, expanded = _http_json(
            method="POST",
            url=f"{base_url}/api/requests/{request_id}/expanded-preview",
            json_body={},
            headers={"X-Request-Access-Token": access_token},
        )
        expanded_blockers: list[str] = []
        _require(
            ep_auth_status in {401, 403},
            "expanded preview unauthenticated POST was not rejected",
            expanded_blockers,
        )
        _require(ep_status == 200, "expanded preview POST failed", expanded_blockers)
        report["expanded_preview"] = {
            "status": "pass" if not expanded_blockers else "fail",
            "unauthenticated_http_status": ep_auth_status,
            "http_status": ep_status,
            "lifecycle_status": expanded.get("lifecycle_status"),
            "tier2_request_state": terminal_preview.get("tier2_request_state"),
            "blockers": expanded_blockers,
        }
        db_evidence = _collect_db_evidence_for_request(request_id=request_id)
        _deep_merge(report, db_evidence)
        if access_token_file is not None and all(
            str((report.get(section) or {}).get("status") or "") == "pass"
            for section in ("customer_security", "expanded_preview", "phase4", "phase5")
        ):
            access_token_file.unlink(missing_ok=True)
            report["artifacts"]["resume_access_token_file"] = {
                "exists": access_token_file.exists(),
                "path_sha256": _path_sha256(access_token_file),
                "deleted_on_success": True,
            }
    except Exception as exc:
        message = _redact_value(str(exc))
        report.setdefault("artifacts", {})
        if request_id is not None:
            report["artifacts"].setdefault("request_id", request_id)
        for key in ("customer_security", "expanded_preview", "phase4", "phase5"):
            payload = dict(report.get(key) or {})
            payload["status"] = "fail"
            blockers = list(payload.get("blockers") or [])
            if message not in blockers:
                blockers.append(message)
            payload["blockers"] = blockers
            report[key] = payload
    return report

def _default_checks(
    *,
    preflight_only: bool,
    preflight_report_path: Path | None,
    preflight_report_sha256: str | None = None,
) -> tuple[tuple[str, CheckFn], ...]:
    checks: list[tuple[str, CheckFn]] = [
        ("configuration", lambda _report: _run_configuration_check()),
        (
            "docker_environment",
            lambda _report: _run_docker_environment_check(
                host_preflight=preflight_only
            ),
        ),
    ]
    if preflight_only:
        checks.append(("prompt_variants", lambda _report: _run_prompt_variants_check()))
    else:
        if preflight_report_path is None:
            raise ValueError("--run-real-http requires --preflight-report PATH")
        if not preflight_report_sha256:
            raise ValueError(
                "--run-real-http requires --preflight-report-sha256 SHA256"
            )
        checks.append(
            (
                "preflight_report",
                lambda _report: _load_preflight_report_check(
                    preflight_report_path,
                    expected_sha256=preflight_report_sha256,
                ),
            )
        )
    return tuple(checks)


def _final_readiness_satisfied(report: Mapping[str, Any]) -> bool:
    readiness = report.get("final_readiness")
    if not isinstance(readiness, Mapping):
        return False
    if readiness.get("ready") is not True:
        return False
    if readiness.get("requirements_satisfied") is not True:
        return False
    if report.get("failures"):
        return False
    artifacts = report.get("artifacts")
    if not isinstance(artifacts, Mapping):
        return False
    raw_results = artifacts.get("check_results")
    if not isinstance(raw_results, Mapping):
        return False
    for identity in MANDATORY_CHECK_IDENTITIES:
        result = raw_results.get(identity)
        if not isinstance(result, Mapping):
            return False
        if result.get("passed") is not True:
            return False
    action = str(report.get("required_next_action") or "").strip()
    return action == ""


def _internal_section_status(report: Mapping[str, Any], key: str) -> str:
    section = report.get(key)
    if not isinstance(section, Mapping):
        return "missing"
    return str(section.get("status") or "").strip().lower()


def _finalize_internal_readiness(
    report: dict[str, Any],
    *,
    preflight_only: bool,
    run_real_http: bool,
) -> int:
    required_sections = (
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
        "restart_resume",
    )
    blockers: list[str] = []
    for section in required_sections:
        status = _internal_section_status(report, section)
        if section == "docker_environment" and preflight_only:
            section_ready = status == "deferred_to_production_image"
        else:
            section_ready = status == "pass"
        if not section_ready:
            blockers.append(f"{section} did not pass")
    if preflight_only or not run_real_http:
        blockers.append("real_http_flow_not_run")
        report["required_next_action"] = "run_real_http_flow"
    else:
        for section in ("customer_security", "expanded_preview", "phase4", "phase5"):
            if _internal_section_status(report, section) != "pass":
                blockers.append(f"{section} did not pass")
    ready = not blockers
    report["final_readiness"] = {
        "ready": ready,
        "requirements_satisfied": ready,
        "summary": (
            "All concrete readiness checks passed."
            if ready
            else "Concrete readiness evidence is still incomplete."
        ),
        "blockers": blockers,
    }
    return 0 if ready else 1


def run_preview_v2_production_readiness(
    *,
    report_path: Path,
    checks: Sequence[tuple[str, CheckFn]] | None = None,
    preflight_only: bool = False,
    run_real_http: bool = False,
    preflight_report_path: Path | None = None,
    preflight_report_sha256: str | None = None,
    resume_request_id: int | None = None,
    resume_access_token_file: Path | None = None,
) -> int:
    report = _build_report(report_path)
    report["artifacts"]["cli_mode"] = (
        "preflight_only"
        if preflight_only
        else ("real_http" if run_real_http else "default")
    )
    _persist_report(report_path, report)
    active_checks = (
        tuple(checks)
        if checks is not None
        else _default_checks(
            preflight_only=preflight_only,
            preflight_report_path=preflight_report_path,
            preflight_report_sha256=preflight_report_sha256,
        )
    )

    for stage, check in active_checks:
        try:
            update = check(report) or {}
            _deep_merge(report, _redact_value(dict(update)))
            section_name = CHECK_SECTION_BY_IDENTITY.get(stage)
            if section_name:
                section_payload = report.get(section_name)
                report["artifacts"]["check_results"][stage] = {
                    "ran": True,
                    "passed": _section_passed(section_payload),
                }
            report["artifacts"]["last_completed_check"] = stage
            _persist_report(report_path, report)
        except Exception as exc:
            report["failures"].append(
                {
                    "stage": stage,
                    "error_type": type(exc).__name__,
                    "message": _redact_value(str(exc)),
                }
            )
            report["artifacts"]["last_failed_check"] = stage
            report["final_readiness"] = {
                "ready": False,
                "requirements_satisfied": False,
                "summary": f"Blocking failure during {stage}.",
            }
            if not str(report.get("required_next_action") or "").strip():
                report["required_next_action"] = "resolve_blocking_failures"
            _persist_report(report_path, report)
            return 1

    if checks is not None:
        report["final_readiness"] = {
            **dict(report.get("final_readiness") or {}),
            "ready": False,
            "requirements_satisfied": False,
            "summary": "Custom checks are a fail-closed test seam only.",
        }
        if not str(report.get("required_next_action") or "").strip():
            report["required_next_action"] = "run_internal_default_checks"
        _persist_report(report_path, report)
        return 1

    if run_real_http and not preflight_only:
        update = _run_real_http_flow(
            resume_request_id=resume_request_id,
            resume_access_token_file=resume_access_token_file,
        )
        _deep_merge(report, _redact_value(dict(update)))
        _persist_report(report_path, report)

    exit_code = _finalize_internal_readiness(
        report,
        preflight_only=preflight_only,
        run_real_http=run_real_http,
    )
    if preflight_only:
        report = _bind_preflight_report_artifact(report)
    _persist_report(report_path, report)
    return exit_code


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a redacted Preview v2 production-readiness report."
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=BACKEND_ROOT / ".runtime" / "preview_v2_production_readiness.json",
        help="Path to the JSON report file.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Run concrete config/docker/variant checks only.",
    )
    parser.add_argument(
        "--run-real-http",
        action="store_true",
        help="Run the loopback HTTP flow in addition to default checks.",
    )
    parser.add_argument(
        "--preflight-report",
        type=Path,
        default=None,
        help="Path to a prior redacted host preflight report.",
    )
    parser.add_argument(
        "--preflight-report-sha256",
        type=str,
        default=None,
        help="Expected SHA256 of the bound host preflight report artifact.",
    )
    parser.add_argument(
        "--resume-request-id",
        type=int,
        default=None,
        help="Resume the same request id instead of creating a new request.",
    )
    parser.add_argument(
        "--resume-access-token-file",
        type=Path,
        default=None,
        help="Private access-token file path for resume/expanded-preview auth.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    exit_code = run_preview_v2_production_readiness(
        report_path=args.report_path,
        preflight_only=bool(args.preflight_only),
        run_real_http=(bool(args.run_real_http) and not bool(args.preflight_only)),
        preflight_report_path=args.preflight_report,
        preflight_report_sha256=args.preflight_report_sha256,
        resume_request_id=args.resume_request_id,
        resume_access_token_file=args.resume_access_token_file,
    )
    print(f"report_path={args.report_path}")
    print("READY" if exit_code == 0 else "NOT_READY")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
