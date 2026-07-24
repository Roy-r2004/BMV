"""Frozen, offline characterization coverage for the five Phase 0 profiles."""
from __future__ import annotations

import json
from pathlib import Path

from app.application.preview_app.characterization import (
    REPRESENTATIVE_CATEGORIES,
    load_frozen_characterization,
)
from app.domain.appspec.validation import app_spec_sha256, validate_app_spec
from app.domain.schemas.app_spec import AppSpec


BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
FIXTURE_DIR = BACKEND_DIR / "tests" / "fixtures" / "preview_characterization"

EXPECTED_HASHES = {
    "booking_workflow.json": "ddcd6b4aec181d2097da9308c2ba7d8f9144cb98f99a130d07a7bdfacdd20214",
    "data_heavy_trading_workflow.json": "bacc63d3cb471f4bcf6985f5d27928fe57d670287c457720908b4cbf5918d985",
    "hybrid_public_operations.json": "d2689c5809db00ba0f4d6fee9d1851d5f10d4484b14a0463ad675f48359c7a25",
    "operations_heavy_saas.json": "afebec1e6ea5e5215a74f21eb1601144726444bb00d0d0fe5b38b996195923b1",
    "premium_public_website.json": "fac21968a2d2fb85502bc5dbf35140f1d9454025b340a935e96489ffb10e00c3",
}


def _fixtures():
    return [
        load_frozen_characterization(path)
        for path in sorted(FIXTURE_DIR.glob("*.json"))
    ]


def test_exact_five_representative_fixtures_are_frozen() -> None:
    fixtures = _fixtures()
    assert len(fixtures) == 5
    assert {fixture.category for fixture in fixtures} == REPRESENTATIVE_CATEGORIES
    assert {fixture.path.name: fixture.sha256 for fixture in fixtures} == EXPECTED_HASHES


def test_characterizations_record_every_required_phase0_observation() -> None:
    required = {
        "app_spec_artifact",
        "generated_output",
        "ai_calls_by_stage",
        "build_result",
        "quality_gate_result",
        "elapsed_time",
        "scaffold_catalogue_usage",
    }
    for fixture in _fixtures():
        assert required <= fixture.payload.keys(), fixture.fixture_id
        assert fixture.payload["baseline_generator"] == "v1"


def test_route_alignment_and_generated_file_records_are_exact() -> None:
    for fixture in _fixtures():
        payload = fixture.payload
        spec_routes = {
            page["route"] for page in payload["app_spec_artifact"]["pages"]
        }
        output_routes = {
            route["path"] for route in payload["generated_output"]["routes"]
        }
        alignment = payload["generated_output"]["route_alignment"]
        assert set(alignment["matched"]) == spec_routes & output_routes
        assert set(alignment["missing_from_output"]) == spec_routes - output_routes
        assert set(alignment["extra_in_output"]) == output_routes - spec_routes

        files = set(payload["generated_output"]["generated_files"])
        assert {
            route["component_file"] for route in payload["generated_output"]["routes"]
        } <= files


def test_repository_booking_appspec_artifact_is_valid_and_hashes_match() -> None:
    booking = load_frozen_characterization(FIXTURE_DIR / "booking_workflow.json")
    artifact = booking.payload["app_spec_artifact"]
    artifact_path = REPO_ROOT / artifact["artifact_path"]
    spec = AppSpec.model_validate(json.loads(artifact_path.read_text(encoding="utf-8")))

    report = validate_app_spec(spec)
    assert report.passed is True
    assert app_spec_sha256(spec) == artifact["sha256"]


def test_fixture_loading_cannot_call_a_paid_provider(monkeypatch) -> None:
    import app.infrastructure.ai_providers.factory as provider_factory
    from app.infrastructure.ai_providers.openrouter_provider import OpenRouterAIProvider

    calls: list[str] = []

    def forbidden(*_args, **_kwargs):
        calls.append("paid-provider")
        raise AssertionError("fixture characterization attempted a paid provider call")

    monkeypatch.setattr(provider_factory, "get_ai_provider", forbidden)
    monkeypatch.setattr(OpenRouterAIProvider, "ask_chat", forbidden)
    monkeypatch.setattr(OpenRouterAIProvider, "ask_vision", forbidden)

    fixtures = _fixtures()

    assert len(fixtures) == 5
    assert calls == []
