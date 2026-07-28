"""Request #45 Phase 4 regression: empty contract subtree + contrast measurement.

The committed fixture captures only the sanitized route, journey, and
accessibility rows from production request #45 attempt 5. It proves:

- /services/v2 and /booking rendered empty contract subtrees
- journeys cascaded from those empty pages
- transparent-gradient contrast was measured as 1.00 against white

The production fix is the deterministic contract-render floor plus corrected
effective-background contrast resolution. This suite asserts both.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.application.candidate_generation.contract_floor import (
    build_contract_floor_hooks,
    humanize_contract_id,
    render_contract_floor_module,
)
from app.application.candidate_generation.validation import (
    validate_contract_render_quality,
)
from app.application.runtime_validation.accessibility import (
    _BASELINE_SCRIPT,
    run_baseline_accessibility_scan,
)
from app.domain.schemas.runtime_validation import RuntimeValidationRefs
from tests.candidate_generation.helpers import prepare_phase3a
from tests.runtime_validation.helpers import (
    prepare_runtime_candidate,
    run_phase4,
)


FIXTURE = Path(__file__).with_name("request45_phase4_failure.json")
EMPTY_ROUTES = {"/services/v2", "/booking"}
CONTRAST_ROUTES = {"/", "/services"}
FAIL_CHECKS = {
    "component_markers_verified",
    "contract_hooks_verified",
    "clipping_verified",
    "primary_action_reachable",
}


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_request45_fixture_reproduces_empty_contract_subtree() -> None:
    fixture = _fixture()
    assert fixture["request_id"] == 45
    assert fixture["counts"]["failed_routes"] == 6
    assert fixture["counts"]["failed_journeys"] == 5
    assert fixture["counts"]["failed_accessibility"] == 6
    assert fixture["typescript_diagnostic_count"] == 0
    assert fixture["vite_build_passed"] is True
    assert fixture["preview_identity_verified"] is True
    assert fixture["screenshot_count"] == 15
    assert fixture["console_errors"] == []
    assert fixture["network_failures"] == []
    assert fixture["network_diagnostics"] == []

    failed_routes = [
        row for row in fixture["route_results"] if not row["passed"]
    ]
    assert {row["route"] for row in failed_routes} == EMPTY_ROUTES
    for row in failed_routes:
        assert set(row["failed_checks"]) == FAIL_CHECKS
        assert row["console_errors"] == []
        assert row["page_errors"] == []
        assert row["request_failures"] == []

    passed_routes = [
        row for row in fixture["route_results"] if row["passed"]
    ]
    assert len(passed_routes) == 9
    assert all(row["route"] not in EMPTY_ROUTES for row in passed_routes)


def test_request45_fixture_journeys_cascade_from_empty_pages() -> None:
    fixture = _fixture()
    passed = [row for row in fixture["journey_results"] if row["passed"]]
    failed = [row for row in fixture["journey_results"] if not row["passed"]]
    assert len(passed) == 1
    assert passed[0]["action_id"] == "ACTION-NAVIGATE-TO-SERVICES"
    assert len(failed) == 5
    for row in failed:
        assert row["failed_steps"]
        first = row["failed_steps"][0]
        assert first["observed"] == "0"
        assert first["selector"].startswith("[data-bmv-")
        # Downstream of the empty detail/booking pages: locator counts are 0.
        assert any(
            marker in first["selector"]
            for marker in (
                "data-bmv-state-id",
                "data-bmv-action-id",
                "data-bmv-evidence-id",
                "data-bmv-transition-id",
            )
        )


def test_request45_fixture_contrast_was_white_on_transparent_gradient() -> None:
    fixture = _fixture()
    contrast_findings = []
    for row in fixture["accessibility_results"]:
        for finding in row["findings"]:
            if finding["rule_id"] == "obvious-computed-contrast":
                contrast_findings.append((row["route"], finding))
    assert contrast_findings
    assert {route for route, _ in contrast_findings} == CONTRAST_ROUTES
    for _route, finding in contrast_findings:
        assert finding["severity"] == "serious"
        assert "1.00" in finding["diagnostic_evidence"]
        assert finding["selector"].startswith("[data-bmv-action-id=")


def test_contract_floor_projection_covers_accepted_pages() -> None:
    prepared = prepare_phase3a(request_id=4501, page_count=5)
    from app.application.candidate_generation.context import (
        load_candidate_context,
    )

    context = load_candidate_context(
        prepared.db,
        request_id=prepared.req.id,
        phase3a_result=prepared.phase3a_result,
    )
    projection = build_contract_floor_hooks(context)
    assert set(projection) == {
        page.page_id for page in context.page_purpose.pages
    }
    for page in context.page_purpose.pages:
        groups = projection[page.page_id]
        assert groups
        component_ids = {group["componentId"] for group in groups}
        expected = next(
            item.ordered_component_ids
            for item in context.business_components.page_compositions
            if item.page_id == page.page_id
        )
        assert component_ids == set(expected)
        for group in groups:
            kinds = {hook["kind"] for hook in group["hooks"]}
            assert kinds <= {"state", "evidence", "action"}
    module = render_contract_floor_module(context)
    assert "export const contractFloorHooks" in module
    assert "ContractFloorComponent" in module


def test_source_quality_rejects_unconditional_null_and_hidden_hooks() -> None:
    null_issues = validate_contract_render_quality(
        path="src/components/business/Empty.tsx",
        source=(
            'export function Empty() {\n'
            '  return null;\n'
            '}\n'
        ),
        component_id="COMP-EMPTY",
        action_ids=("ACTION-X",),
    )
    assert any(
        issue.code == "component_renders_no_contract_content"
        for issue in null_issues
    )

    empty_fragment = validate_contract_render_quality(
        path="src/components/business/Empty.tsx",
        source=(
            'export function Empty() {\n'
            '  return <></>;\n'
            '}\n'
        ),
        component_id="COMP-EMPTY",
    )
    assert any(
        issue.code == "component_renders_no_contract_content"
        for issue in empty_fragment
    )

    hidden = validate_contract_render_quality(
        path="src/components/business/Hidden.tsx",
        source=(
            'export function Hidden() {\n'
            '  return (\n'
            '    <section data-bmv-component-id="COMP-HIDDEN">\n'
            '      <button hidden data-bmv-action-id="ACTION-X">Go</button>\n'
            '    </section>\n'
            '  );\n'
            '}\n'
        ),
        component_id="COMP-HIDDEN",
        action_ids=("ACTION-X",),
    )
    assert any(
        issue.code == "contract_hook_permanently_hidden" for issue in hidden
    )

    valid = validate_contract_render_quality(
        path="src/components/business/Valid.tsx",
        source=(
            'export function Valid() {\n'
            '  return (\n'
            '    <section data-bmv-component-id="COMP-VALID">\n'
            '      <button data-bmv-action-id="ACTION-X">Go</button>\n'
            '      <p data-bmv-state-id="STATE-X">Ready</p>\n'
            '      <p data-bmv-evidence-id="EVIDENCE-X">Done</p>\n'
            '    </section>\n'
            '  );\n'
            '}\n'
        ),
        component_id="COMP-VALID",
        action_ids=("ACTION-X",),
        state_ids=("STATE-X",),
        evidence_ids=("EVIDENCE-X",),
    )
    assert valid == ()


def test_humanize_contract_id_is_deterministic() -> None:
    assert humanize_contract_id("ACTION-INITIATE-BOOKING") == (
        "Initiate booking"
    )
    assert humanize_contract_id("STATE-SERVICE-DETAIL-VIEWED") == (
        "Service detail viewed"
    )


def _refs() -> RuntimeValidationRefs:
    digest = "a" * 64
    return RuntimeValidationRefs.model_validate(
        {
            "request_id": 45,
            "candidate_revision_id": 1,
            "candidate_revision_uuid": "00000000-0000-4000-8000-000000000045",
            "candidate_manifest_sha256": digest,
            "dependency_lock_sha256": digest,
            "candidate_generator_version": "v2",
            "candidate_policy_revision": "2026-07-24.1",
            "runtime_policy_revision": "2026-07-24.1",
        }
    )


def test_contrast_transparent_child_resolves_ancestor_background(page) -> None:
    page.set_content(
        """
        <main>
          <div style="background-color: rgb(29, 78, 216); padding: 24px;">
            <button data-bmv-action-id="ACTION-X"
              style="color: rgb(255,255,255); background-color: rgba(0,0,0,0);">
              Book now
            </button>
          </div>
        </main>
        """
    )
    result = run_baseline_accessibility_scan(
        page,
        refs=_refs(),
        cache_key="b" * 64,
        build_hash="c" * 64,
        page_id="PAGE-X",
        route="/",
        viewport="desktop",
    )
    contrast = [
        item
        for item in result.findings
        if item.rule_id
        in {"obvious-computed-contrast", "contrast-background-unresolved"}
    ]
    assert contrast == []


def test_contrast_hero_over_image_with_overlay_passes(page) -> None:
    page.set_content(
        """
        <main>
          <section style="background-image: url('data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==');
                          background-color: #0f172a; color: #ffffff; padding: 48px;">
            <h1 style="color: #ffffff; background-color: transparent;">Evening service</h1>
          </section>
        </main>
        """
    )
    result = run_baseline_accessibility_scan(
        page,
        refs=_refs(),
        cache_key="b" * 64,
        build_hash="c" * 64,
        page_id="PAGE-X",
        route="/",
        viewport="desktop",
    )
    assert not any(
        item.rule_id
        in {"obvious-computed-contrast", "contrast-background-unresolved"}
        for item in result.findings
    )


def test_contrast_hero_over_image_without_overlay_blocks(page) -> None:
    page.set_content(
        """
        <main>
          <section style="background-image: url('data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==');
                          background-color: transparent; padding: 48px;">
            <h1 style="color: #ffffff; background-color: transparent;">Evening service</h1>
          </section>
        </main>
        """
    )
    result = run_baseline_accessibility_scan(
        page,
        refs=_refs(),
        cache_key="b" * 64,
        build_hash="c" * 64,
        page_id="PAGE-X",
        route="/",
        viewport="desktop",
    )
    unresolved = [
        item
        for item in result.findings
        if item.rule_id == "contrast-background-unresolved"
    ]
    assert unresolved
    assert unresolved[0].severity == "serious"
    assert result.passed is False


def test_contrast_gradient_with_solid_fallback_is_measured(page) -> None:
    page.set_content(
        """
        <main>
          <button data-bmv-action-id="ACTION-Y"
            style="color: #ffffff; background-color: #1d4ed8;
                   background-image: linear-gradient(#1d4ed8, #1e40af);">
            Continue
          </button>
        </main>
        """
    )
    result = run_baseline_accessibility_scan(
        page,
        refs=_refs(),
        cache_key="b" * 64,
        build_hash="c" * 64,
        page_id="PAGE-X",
        route="/",
        viewport="desktop",
    )
    assert not any(
        item.rule_id
        in {"obvious-computed-contrast", "contrast-background-unresolved"}
        for item in result.findings
    )


def test_contrast_gradient_opaque_stops_are_measured(page) -> None:
    page.set_content(
        """
        <main>
          <button data-bmv-action-id="ACTION-Y2"
            style="color: #ffffff; background-color: transparent;
                   background-image: linear-gradient(#1d4ed8, #1e40af);">
            Continue
          </button>
        </main>
        """
    )
    result = run_baseline_accessibility_scan(
        page,
        refs=_refs(),
        cache_key="b" * 64,
        build_hash="c" * 64,
        page_id="PAGE-X",
        route="/",
        viewport="desktop",
    )
    assert not any(
        item.rule_id
        in {"obvious-computed-contrast", "contrast-background-unresolved"}
        for item in result.findings
    )


def test_contrast_gradient_without_fallback_blocks(page) -> None:
    page.set_content(
        """
        <main>
          <button data-bmv-action-id="ACTION-Z"
            style="color: #ffffff; background-color: transparent;
                   background-image: linear-gradient(transparent, transparent);">
            Ghost
          </button>
        </main>
        """
    )
    result = run_baseline_accessibility_scan(
        page,
        refs=_refs(),
        cache_key="b" * 64,
        build_hash="c" * 64,
        page_id="PAGE-X",
        route="/",
        viewport="desktop",
    )
    unresolved = [
        item
        for item in result.findings
        if item.rule_id == "contrast-background-unresolved"
    ]
    assert unresolved
    assert unresolved[0].severity == "serious"
    assert result.passed is False


def test_contrast_token_metadata_fallback_is_measured(page) -> None:
    page.set_content(
        """
        <main>
          <button data-bmv-action-id="ACTION-TOKEN"
            data-bmv-contrast-background="#1d4ed8"
            style="color: #ffffff; background-color: transparent;
                   background-image: url('data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==');">
            Book
          </button>
        </main>
        """
    )
    result = run_baseline_accessibility_scan(
        page,
        refs=_refs(),
        cache_key="b" * 64,
        build_hash="c" * 64,
        page_id="PAGE-X",
        route="/",
        viewport="desktop",
    )
    assert not any(
        item.rule_id
        in {"obvious-computed-contrast", "contrast-background-unresolved"}
        for item in result.findings
    )


def test_contrast_white_on_white_still_fails(page) -> None:
    page.set_content(
        """
        <main>
          <button data-bmv-action-id="ACTION-W"
            style="color: #ffffff; background-color: #ffffff;">
            Invisible
          </button>
        </main>
        """
    )
    result = run_baseline_accessibility_scan(
        page,
        refs=_refs(),
        cache_key="b" * 64,
        build_hash="c" * 64,
        page_id="PAGE-X",
        route="/",
        viewport="desktop",
    )
    contrast = [
        item
        for item in result.findings
        if item.rule_id == "obvious-computed-contrast"
    ]
    assert contrast
    assert "below 3:1" in contrast[0].diagnostic_evidence
    assert result.passed is False


def test_contrast_compliant_cta_passes(page) -> None:
    page.set_content(
        """
        <main>
          <button data-bmv-action-id="ACTION-OK"
            style="color: #ffffff; background-color: #1d4ed8;">
            Book
          </button>
        </main>
        """
    )
    result = run_baseline_accessibility_scan(
        page,
        refs=_refs(),
        cache_key="b" * 64,
        build_hash="c" * 64,
        page_id="PAGE-X",
        route="/",
        viewport="desktop",
    )
    assert not any(
        item.rule_id
        in {"obvious-computed-contrast", "contrast-background-unresolved"}
        for item in result.findings
    )


def test_contrast_threshold_and_parse_policy() -> None:
    assert "if (worst < 3)" in _BASELINE_SCRIPT
    assert "|| [255, 255, 255]" not in _BASELINE_SCRIPT
    assert "contrast-background-unresolved" in _BASELINE_SCRIPT
    assert 'raw === "transparent"' in _BASELINE_SCRIPT
    assert "startsWith(\"#\")" in _BASELINE_SCRIPT
    assert "rgba?" in _BASELINE_SCRIPT


def test_generated_app_wraps_pages_in_contract_floor(
    isolated_runtime_paths,
) -> None:
    prepared = prepare_runtime_candidate(request_id=4502)
    try:
        app = (prepared.candidate_path / "src" / "App.tsx").read_text(
            encoding="utf-8"
        )
        floor = (
            prepared.candidate_path / "src" / "runtime" / "ContractFloor.tsx"
        ).read_text(encoding="utf-8")
        hooks = (
            prepared.candidate_path / "src" / "generated" / "contract-floor.ts"
        ).read_text(encoding="utf-8")
        css = (
            prepared.candidate_path / "src" / "index.css"
        ).read_text(encoding="utf-8")
        assert 'import { ContractFloor } from "./runtime/ContractFloor";' in app
        assert "contractFloorHooks" in app
        assert "<ContractFloor" in app
        assert "data-bmv-contract-floor" in floor
        assert "data-bmv-component-id={group.componentId}" in floor
        assert "export const contractFloorHooks" in hooks
        assert "emptyComponents" in floor
        assert (
            'present(`[data-bmv-component-id="${group.componentId}"]`)'
            in floor
        )
        # Brand-safe visual: no bordered diagnostic card, no debug wording.
        assert "border: \"1px" not in floor
        assert "Required contract content" not in floor
        assert "diagnostic" not in floor.lower()
        assert "--bmv-accent" in floor
        assert "--bmv-surface" in css
        assert "--bmv-contrast-background" in css
    finally:
        prepared.prepared.db.close()


def test_phase4_passes_with_contract_floor_and_contrast_fix(
    isolated_runtime_paths,
) -> None:
    prepared = prepare_runtime_candidate(request_id=4503)
    try:
        result = run_phase4(prepared)
        assert result["preview_contract"]["status"] == (
            "candidate_runtime_validated"
        )
    finally:
        prepared.prepared.db.close()


@pytest.fixture
def page():
    from app.application.preview_app.screenshot import launch_chromium
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = launch_chromium(playwright)
        context = browser.new_context()
        current = context.new_page()
        try:
            yield current
        finally:
            context.close()
            browser.close()
