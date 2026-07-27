"""Deterministic replay checks for known production failure classes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.application.candidate_generation.deterministic import (
    component_export_symbol,
    page_export_symbol,
)
from app.application.candidate_generation.usage_validation import (
    validate_binding_against_source,
)
from app.domain.schemas.business_component_usage import (
    RequiredBusinessComponentBinding,
)
from tests.preview_audit.known_failure_catalog import KNOWN_FAILURES


ROOT = Path(__file__).resolve().parents[3]
FAILURE_MAP = ROOT / "docs" / "architecture" / "preview_v2_failure_map.json"
HANDOFF_MATRIX = ROOT / "docs" / "architecture" / "preview_v2_handoff_matrix.json"


def test_failure_map_and_handoff_artifacts_exist_and_parse() -> None:
    failure_map = json.loads(FAILURE_MAP.read_text(encoding="utf-8"))
    handoffs = json.loads(HANDOFF_MATRIX.read_text(encoding="utf-8"))
    assert failure_map["schema_version"] == "1.0"
    assert len(failure_map["stages"]) >= 15
    required_fields = {
        "stage",
        "inputs",
        "outputs",
        "timeout_seconds",
        "retry_count",
        "provider_call_count",
        "deterministic_repair",
        "ai_repair",
        "fallback_behavior",
        "terminal_statuses",
        "known_failure_codes",
        "customer_safe",
        "retryable",
        "idempotent",
        "resume_supported",
        "partial_artifacts_may_leak",
    }
    for stage in failure_map["stages"]:
        missing = required_fields - set(stage)
        assert not missing, f"{stage.get('stage')}: missing {missing}"
    assert len(handoffs["handoffs"]) >= 10
    fragile = [
        item for item in handoffs["handoffs"] if item["compatibility"] in {"fragile", "weak"}
    ]
    assert fragile, "audit expects identified weak/fragile handoffs"


def test_known_failure_catalog_covers_smoke_classes() -> None:
    ids = {item.failure_id for item in KNOWN_FAILURES}
    for required in (
        "page_ai_features_closure",
        "page_membership_mismatch",
        "bcp_wall_timeout",
        "missing_business_component_usage",
        "phase4_pending_mismatch",
        "expanded_preview_409_no_tier1",
        "migration_readiness",
    ):
        assert required in ids


def test_missing_business_component_usage_fixture_fails_at_candidate_pages() -> None:
    binding = RequiredBusinessComponentBinding(
        page_id="PAGE-HOME",
        business_component_id="COMP-HOME",
        component_symbol=component_export_symbol("COMP-HOME"),
        component_module_path=(
            f"src/components/business/{component_export_symbol('COMP-HOME')}.tsx"
        ),
        required_usage_count=1,
        required_props=(),
        action_ids=(),
        state_ids=(),
        evidence_ids=(),
        source_plan_revision="1.0",
        source_plan_hash="b" * 64,
    )
    generic = (
        f"export function {page_export_symbol('PAGE-HOME')}() {{\n"
        "  return (\n"
        '    <main data-bmv-page-id="PAGE-HOME">\n'
        "      <section><h1>Welcome</h1><button>Go</button></section>\n"
        "    </main>\n"
        "  );\n"
        "}\n"
    )
    item = validate_binding_against_source(
        source=generic,
        binding=binding,
        component_file_exists=True,
    )
    assert item.result in {"missing_import", "missing_mount"}
    entry = next(
        row
        for row in KNOWN_FAILURES
        if row.failure_id == "missing_business_component_usage"
    )
    assert entry.stage == "candidate_pages"
    assert entry.typed_error == "missing_business_component_usage"


def test_phase4_pending_mismatch_is_catalogued_as_orchestration_gap() -> None:
    entry = next(
        row for row in KNOWN_FAILURES if row.failure_id == "phase4_pending_mismatch"
    )
    assert entry.stage == "runtime_build"
    assert "candidate_build_pending" in entry.typed_error
    assert entry.existing_test is None
    assert entry.requires_regeneration is True


@pytest.mark.parametrize("failure", KNOWN_FAILURES, ids=lambda item: item.failure_id)
def test_each_known_failure_declares_safe_retry_repair_semantics(failure) -> None:
    assert failure.stage
    assert failure.typed_error
    assert isinstance(failure.customer_safe, bool)
    assert isinstance(failure.retryable, bool)
    # Fail-closed customer safety is required for all catalogued production classes.
    assert failure.customer_safe is True
