"""Offline loader and validator for frozen preview-generator baselines.

Characterization fixtures are observations, not generation inputs. Loading one
must never construct or call an AI provider, run a build, or mutate a preview
workspace.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


FIXTURE_SCHEMA_VERSION = "1.0"
REPRESENTATIVE_CATEGORIES = frozenset(
    {
        "premium_public_website",
        "hybrid_public_operations",
        "operations_heavy_saas",
        "booking_workflow",
        "data_heavy_trading_workflow",
    }
)
_OBSERVATION_STATUSES = {
    "observed",
    "observed_incomplete",
    "focused_observation",
    "deterministic_only",
    "not_observed",
}


class CharacterizationFixtureError(ValueError):
    """Raised when a frozen baseline is incomplete or internally inconsistent."""


@dataclass(frozen=True)
class FrozenCharacterization:
    path: Path
    payload: dict[str, Any]
    sha256: str

    @property
    def fixture_id(self) -> str:
        return str(self.payload["fixture_id"])

    @property
    def category(self) -> str:
        return str(self.payload["category"])


def _require_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise CharacterizationFixtureError(f"{key} must be an object")
    return value


def _require_list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise CharacterizationFixtureError(f"{key} must be an array")
    return value


def _validate_status(section: dict[str, Any], name: str) -> str:
    status = section.get("status")
    if status not in _OBSERVATION_STATUSES:
        raise CharacterizationFixtureError(f"{name}.status is invalid")
    return str(status)


def _validate_fixture(payload: dict[str, Any]) -> None:
    if payload.get("fixture_schema_version") != FIXTURE_SCHEMA_VERSION:
        raise CharacterizationFixtureError("unsupported fixture_schema_version")
    if payload.get("baseline_generator") != "v1":
        raise CharacterizationFixtureError("baseline_generator must be v1")
    if payload.get("category") not in REPRESENTATIVE_CATEGORIES:
        raise CharacterizationFixtureError("unknown representative category")
    if not str(payload.get("fixture_id") or "").strip():
        raise CharacterizationFixtureError("fixture_id is required")

    source = _require_dict(payload, "source")
    if not str(source.get("captured_at") or "").strip():
        raise CharacterizationFixtureError("source.captured_at is required")
    request_input = _require_dict(payload, "request_input")
    for key in ("business_name", "industry", "business_description", "desired_outcome"):
        if not str(request_input.get(key) or "").strip():
            raise CharacterizationFixtureError(f"request_input.{key} is required")

    app_spec = _require_dict(payload, "app_spec_artifact")
    app_spec_status = _validate_status(app_spec, "app_spec_artifact")
    if app_spec.get("schema_version") != "1.0":
        raise CharacterizationFixtureError("app_spec_artifact.schema_version must be 1.0")
    spec_pages = _require_list(app_spec, "pages")
    if not spec_pages:
        raise CharacterizationFixtureError("app_spec_artifact.pages cannot be empty")
    if app_spec_status != "not_observed":
        digest = str(app_spec.get("sha256") or "")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise CharacterizationFixtureError("app_spec_artifact.sha256 must be lowercase hex")

    output = _require_dict(payload, "generated_output")
    _validate_status(output, "generated_output")
    routes = _require_list(output, "routes")
    generated_files = _require_list(output, "generated_files")
    generated_file_set = {str(path) for path in generated_files}
    route_paths: set[str] = set()
    for route in routes:
        if not isinstance(route, dict):
            raise CharacterizationFixtureError("generated_output.routes entries must be objects")
        path = str(route.get("path") or "")
        component_file = str(route.get("component_file") or "")
        if not path.startswith("/") or not component_file:
            raise CharacterizationFixtureError("each route needs path and component_file")
        if path in route_paths:
            raise CharacterizationFixtureError(f"duplicate generated route: {path}")
        route_paths.add(path)
        if component_file not in generated_file_set:
            raise CharacterizationFixtureError(
                f"route component is absent from generated_files: {component_file}"
            )

    ai_calls = _require_dict(payload, "ai_calls_by_stage")
    ai_status = _validate_status(ai_calls, "ai_calls_by_stage")
    stages = _require_dict(ai_calls, "stages")
    counts = list(stages.values())
    if any(not isinstance(value, int) or value < 0 for value in counts):
        raise CharacterizationFixtureError("AI stage call counts must be non-negative integers")
    if ai_status != "not_observed" and sum(counts) != ai_calls.get("total_calls"):
        raise CharacterizationFixtureError("AI stage call counts do not sum to total_calls")

    build = _require_dict(payload, "build_result")
    _validate_status(build, "build_result")
    if build.get("command") != "npm exec -- vite build":
        raise CharacterizationFixtureError("build_result.command changed from the v1 baseline")

    gate = _require_dict(payload, "quality_gate_result")
    _validate_status(gate, "quality_gate_result")
    _require_list(gate, "issue_codes")
    _require_list(gate, "healed_codes")

    elapsed = _require_dict(payload, "elapsed_time")
    elapsed_status = _validate_status(elapsed, "elapsed_time")
    seconds = elapsed.get("seconds")
    if elapsed_status == "not_observed":
        if seconds is not None:
            raise CharacterizationFixtureError(
                "unobserved elapsed_time.seconds must be null"
            )
    elif not isinstance(seconds, int) or seconds < 0:
        raise CharacterizationFixtureError(
            "observed elapsed_time.seconds must be a non-negative integer"
        )

    catalogue = _require_dict(payload, "scaffold_catalogue_usage")
    _validate_status(catalogue, "scaffold_catalogue_usage")
    for key in (
        "scaffold_first_enabled",
        "slot_fill_enabled",
        "route_count_with_skeleton",
        "workspace_files_importing_ui_catalogue",
        "files_with_scaffold_marker",
    ):
        if not isinstance(catalogue.get(key), (bool, int)):
            raise CharacterizationFixtureError(f"scaffold_catalogue_usage.{key} is required")


def load_frozen_characterization(path: str | Path) -> FrozenCharacterization:
    """Load one fixture using only local file and deterministic validation."""

    fixture_path = Path(path)
    raw = fixture_path.read_bytes()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CharacterizationFixtureError(f"invalid JSON: {fixture_path}") from exc
    if not isinstance(payload, dict):
        raise CharacterizationFixtureError("fixture root must be an object")
    _validate_fixture(payload)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return FrozenCharacterization(
        path=fixture_path,
        payload=payload,
        sha256=hashlib.sha256(canonical).hexdigest(),
    )


__all__ = [
    "CharacterizationFixtureError",
    "FIXTURE_SCHEMA_VERSION",
    "FrozenCharacterization",
    "REPRESENTATIVE_CATEGORIES",
    "load_frozen_characterization",
]
