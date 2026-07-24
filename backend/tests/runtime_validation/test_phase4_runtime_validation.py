from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError
from playwright.sync_api import sync_playwright

from app.application.runtime_validation.accessibility import (
    run_baseline_accessibility_scan,
)
from app.application.runtime_validation.build import (
    build_cache_keys,
    loopback_only_environment,
    run_build_validation,
    verify_dependency_runtime,
    verify_network_guard,
)
from app.application.runtime_validation.browser import browser_cache_keys
from app.application.runtime_validation.cache import (
    artifact_sha256,
    sha256_file,
)
from app.application.runtime_validation.context import (
    load_runtime_validation_context,
)
from app.application.runtime_validation.dist import validate_dist
from app.application.runtime_validation.policy import (
    VIEWPORTS,
    runtime_limits,
    tool_versions,
)
from app.application.runtime_validation.repository import (
    RuntimeValidationRepository,
)
from app.application.runtime_validation.service import (
    RuntimeValidationError,
    _attempt_cache_identity,
    _failure_summary,
)
from app.application.runtime_validation.server import start_preview_server
from app.application.runtime_validation.workspace import (
    apply_deterministic_repair,
    create_derived_repair_workspace,
    open_validation_workspace,
    source_manifest_sha256,
    validation_root,
    workspace_relpath,
)
from app.core.config import settings
from app.domain.models import (
    CandidateAccessibilityFindingRecord,
    CandidateBuildAttemptRecord,
    CandidateJourneyResultRecord,
    CandidateRouteResultRecord,
    CandidateRuntimeValidationAttemptRecord,
    CandidateScreenshotRecord,
    CandidateValidationSummaryRecord,
)
from app.domain.schemas.runtime_validation import (
    AccessibilityFinding,
    AccessibilityRouteResult,
    BuildValidationResult,
    CommandResult,
    DistFileRecord,
    JourneyStepResult,
    JourneyValidationResult,
    RouteViewportResult,
    RuntimeToolVersions,
    RuntimeValidationSummary,
    ScreenshotEvidence,
)
from tests.runtime_validation.helpers import (
    isolated_runtime_paths,
    prepare_runtime_candidate,
    run_phase4,
)


def _close(prepared) -> None:
    prepared.prepared.db.close()


def _command_result(
    name: str,
    *,
    exit_code: int = 0,
    timed_out: bool = False,
) -> CommandResult:
    return CommandResult(
        command_name=name,
        argv=("node", name),
        exit_code=exit_code,
        timed_out=timed_out,
        duration_ms=1,
        stdout_sha256="0" * 64,
        stderr_sha256="0" * 64,
    )


def _tool_fixture() -> RuntimeToolVersions:
    return RuntimeToolVersions(
        node="v24.13.1",
        typescript="5.8.3",
        vite="8.1.3",
        playwright="1.61.0",
        browser_name="chromium",
        browser_version="chromium-1228",
    )


def _route_payload() -> dict:
    return {
        "refs": {
            "request_id": 1,
            "candidate_revision_id": 1,
            "candidate_revision_uuid": (
                "00000000-0000-4000-8000-000000000001"
            ),
            "candidate_manifest_sha256": "1" * 64,
            "dependency_lock_sha256": "2" * 64,
            "candidate_generator_version": "v2-phase3b",
            "candidate_policy_revision": "2026-07-24.1",
        },
        "cache_key": "3" * 64,
        "build_hash": "4" * 64,
        "page_id": "PAGE_ONE",
        "route": "/one",
        "viewport": "desktop",
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
        "duration_ms": 1,
    }


def _failed_build(context, limits) -> BuildValidationResult:
    build_key, dist_key = build_cache_keys(
        refs=context.refs,
        limits=limits,
        tools=_tool_fixture(),
    )
    return BuildValidationResult(
        refs=context.refs,
        build_cache_key=build_key,
        dist_cache_key=dist_key,
        passed=False,
        dist_validation_passed=False,
        cache_hit=False,
        deterministic_repair_count=0,
        source_candidate_sha256_before=(
            context.refs.candidate_manifest_sha256
        ),
        source_candidate_sha256_after=(
            context.refs.candidate_manifest_sha256
        ),
        dependency_runtime_sha256_before="5" * 64,
        dependency_runtime_sha256_after="5" * 64,
        network_guard_verified=False,
        build_hash="0" * 64,
        dist_manifest_sha256="0" * 64,
        diagnostics=("simulated build failure",),
        duration_ms=1,
    )


def _passing_build(context, limits) -> BuildValidationResult:
    build_key, dist_key = build_cache_keys(
        refs=context.refs,
        limits=limits,
        tools=_tool_fixture(),
    )
    return BuildValidationResult(
        refs=context.refs,
        build_cache_key=build_key,
        dist_cache_key=dist_key,
        passed=True,
        dist_validation_passed=True,
        cache_hit=False,
        deterministic_repair_count=0,
        source_candidate_sha256_before=(
            context.refs.candidate_manifest_sha256
        ),
        source_candidate_sha256_after=(
            context.refs.candidate_manifest_sha256
        ),
        dependency_runtime_sha256_before="5" * 64,
        dependency_runtime_sha256_after="5" * 64,
        network_guard_verified=True,
        build_hash="6" * 64,
        dist_manifest_sha256="7" * 64,
        dist_files=(
            DistFileRecord(
                path="index.html",
                sha256="8" * 64,
                byte_count=1,
                media_kind="html",
            ),
        ),
        duration_ms=1,
    )


def test_real_build_runtime_matrix_journey_accessibility_and_screenshots(
    isolated_runtime_paths,
) -> None:
    prepared = prepare_runtime_candidate()
    before = source_manifest_sha256(
        prepared.candidate_path,
        tuple(json.loads(prepared.revision.file_manifest_json)),
    )
    try:
        result = run_phase4(prepared)
        route_diagnostics = [
            json.loads(row.result_json)
            for row in prepared.prepared.db.query(
                CandidateRouteResultRecord
            ).all()
        ]
        accessibility_diagnostics = [
            json.loads(row.result_json)
            for row in prepared.prepared.db.query(
                CandidateAccessibilityFindingRecord
            ).all()
        ]
        assert result["preview_contract"]["status"] == (
            "candidate_runtime_validated"
        ), json.dumps(
            {
                "preview_contract": result["preview_contract"],
                "routes": route_diagnostics,
                "accessibility": accessibility_diagnostics,
            },
            indent=2,
        )
        after = source_manifest_sha256(
            prepared.candidate_path,
            tuple(json.loads(prepared.revision.file_manifest_json)),
        )
        assert before == after == prepared.revision.file_manifest_sha256
        assert prepared.revision.status == "candidate_build_pending"
        db = prepared.prepared.db
        route_rows = db.query(CandidateRouteResultRecord).all()
        assert len(route_rows) == len(VIEWPORTS)
        assert {
            row.viewport for row in route_rows
        } == {"mobile", "tablet", "desktop"}
        assert all(row.passed for row in route_rows)
        journeys = db.query(CandidateJourneyResultRecord).all()
        assert journeys and all(row.passed for row in journeys)
        journey = json.loads(journeys[0].result_json)
        assert {
            step["step"] for step in journey["steps"]
        } >= {
            "navigate",
            "initial_state",
            "input",
            "action",
            "transition",
            "resulting_state",
            "evidence",
            "acceptance_assertion",
            "reduced_motion",
        }
        assert journey["reduced_motion_required"] is True
        assert journey["reduced_motion_passed"] is True
        accessibility = db.query(
            CandidateAccessibilityFindingRecord
        ).all()
        assert len(accessibility) == len(VIEWPORTS)
        assert all(row.scanner_name == "BaselineAccessibilityScanner" for row in accessibility)
        assert all(row.passed for row in accessibility)
        screenshots = db.query(CandidateScreenshotRecord).all()
        assert len(screenshots) == len(VIEWPORTS)
        for row in screenshots:
            target = validation_root() / row.relative_path
            assert target.is_file()
            assert sha256_file(target) == row.screenshot_sha256
        summary = db.query(CandidateValidationSummaryRecord).one()
        assert summary.status == "candidate_runtime_validated"
        build_rows = (
            db.query(CandidateBuildAttemptRecord)
            .order_by(CandidateBuildAttemptRecord.id)
            .all()
        )
        assert len(build_rows) == 2
        passing_build = json.loads(build_rows[-1].result_json)
        assert [
            item["command_name"] for item in passing_build["commands"]
        ] == [
            "network_guard_verification",
            "typescript_build",
            "vite_build",
        ]
        assert passing_build["dist_validation_passed"] is True
        assert passing_build["deterministic_repair_count"] == 1
        assert build_rows[-1].parent_build_attempt_id == build_rows[0].id
        assert not (settings.PREVIEW_APPS_DIR / str(prepared.prepared.req.id)).exists()
        assert result["preview_contract"]["provider_call_count"] == 0
        assert not any(
            value in result["preview_contract"]["status"]
            for value in ("ready", "degraded", "promoted", "served")
        )
        assert prepared.fixture_ai.calls == [
            ("business_components", "deepseek/deepseek-v4-pro"),
            ("pages", "deepseek/deepseek-v4-pro"),
        ]
    finally:
        _close(prepared)


def test_full_runtime_cache_hit_starts_fresh_server_and_revalidates_evidence(
    isolated_runtime_paths,
    monkeypatch,
) -> None:
    prepared = prepare_runtime_candidate(request_id=1802)
    try:
        first = run_phase4(prepared)
        assert first["preview_contract"]["status"] == "candidate_runtime_validated"
        import app.application.runtime_validation.service as service

        original = service.start_preview_server
        starts = 0

        def counted(*args, **kwargs):
            nonlocal starts
            starts += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(service, "start_preview_server", counted)
        context = load_runtime_validation_context(
            prepared.prepared.db,
            request_id=prepared.prepared.req.id,
            phase3b_result=prepared.phase3b_result,
        )
        tools = tool_versions()
        limits = runtime_limits()
        identity = _attempt_cache_identity(
            context,
            tools=tools,
            limits=limits,
        )
        source_sha = source_manifest_sha256(
            context.candidate_workspace,
            context.candidate_file_manifest,
        )
        interrupted_uuid = str(uuid.uuid4())
        interrupted_workspace = open_validation_workspace(
            request_id=context.refs.request_id,
            candidate_revision_uuid=(
                context.refs.candidate_revision_uuid
            ),
            attempt_uuid=interrupted_uuid,
            cache_identity=identity,
            source_candidate_sha256=source_sha,
            source_path=context.candidate_workspace,
            expected_manifest=context.candidate_file_manifest,
        )
        repository = RuntimeValidationRepository(prepared.prepared.db)
        interrupted = repository.create_attempt(
            attempt_uuid=interrupted_uuid,
            refs=context.refs,
            cache_identity=identity,
            source_candidate_sha256_before=source_sha,
            tools=tools,
            limits=limits,
            workspace_relpath=workspace_relpath(
                interrupted_workspace.staging_path
            ),
        )
        prepared.prepared.db.commit()
        passing_build = (
            prepared.prepared.db.query(CandidateBuildAttemptRecord)
            .filter(CandidateBuildAttemptRecord.passed.is_(True))
            .order_by(CandidateBuildAttemptRecord.id.desc())
            .first()
        )
        assert passing_build is not None
        keys = browser_cache_keys(
            context,
            build_hash=passing_build.build_hash,
            browser_version=tools.browser_version,
        )
        assert len(
            repository.route_cache(context.refs.candidate_revision_id, keys["route"])
        ) == len(VIEWPORTS)
        assert repository.route_cache(
            context.refs.candidate_revision_id,
            "0" * 64,
        ) == ()
        assert len(
            repository.journey_cache(
                context.refs.candidate_revision_id,
                keys["journey"],
            )
        ) == 1
        assert len(
            repository.accessibility_cache(
                context.refs.candidate_revision_id,
                keys["accessibility"],
            )
        ) == len(VIEWPORTS)
        assert len(
            repository.screenshot_cache(
                context.refs.candidate_revision_id,
                keys["screenshot"],
            )
        ) == len(VIEWPORTS)
        second = run_phase4(prepared)
        assert second["preview_contract"]["status"] == "candidate_runtime_validated"
        assert starts == 1
        assert set(second["preview_contract"]["runtime_cache_hits"]) == {
            "build",
            "dist",
            "route",
            "journey",
            "accessibility",
            "screenshot",
        }
        assert (
            prepared.prepared.db.query(
                CandidateRuntimeValidationAttemptRecord
            ).count()
            == 2
        )
        latest_summary = (
            prepared.prepared.db.query(CandidateValidationSummaryRecord)
            .order_by(CandidateValidationSummaryRecord.id.desc())
            .first()
        )
        assert latest_summary.runtime_attempt_id == interrupted.id
        assert (
            prepared.prepared.db.query(
                CandidateValidationSummaryRecord
            ).count()
            == 2
        )
    finally:
        _close(prepared)


def test_workspace_is_copy_only_and_deterministic_repair_is_derived(
    isolated_runtime_paths,
) -> None:
    prepared = prepare_runtime_candidate(request_id=1803)
    try:
        context = load_runtime_validation_context(
            prepared.prepared.db,
            request_id=prepared.prepared.req.id,
            phase3b_result=prepared.phase3b_result,
        )
        source_sha = source_manifest_sha256(
            context.candidate_workspace,
            context.candidate_file_manifest,
        )
        workspace = open_validation_workspace(
            request_id=context.refs.request_id,
            candidate_revision_uuid=context.refs.candidate_revision_uuid,
            attempt_uuid=str(uuid.uuid4()),
            cache_identity="a" * 64,
            source_candidate_sha256=source_sha,
            source_path=context.candidate_workspace,
            expected_manifest=context.candidate_file_manifest,
        )
        for item in context.candidate_file_manifest:
            source = context.candidate_workspace / item["path"]
            copied = workspace.candidate_path / item["path"]
            assert not os.path.samefile(source, copied)
        derived = create_derived_repair_workspace(
            workspace,
            repair_uuid=str(uuid.uuid4()),
        )
        config = derived / "vite.config.ts"
        config.write_text(
            config.read_text(encoding="utf-8").replace(
                "base: './'",
                "base: '/'",
            ),
            encoding="utf-8",
        )
        changed = apply_deterministic_repair(
            derived,
            "asset_path_normalization",
        )
        assert set(changed.split(",")) == {
            "index.html",
            "vite.config.ts",
        }
        assert "base: './'" in config.read_text(encoding="utf-8")
        assert 'rel="preconnect"' not in (
            derived / "index.html"
        ).read_text(encoding="utf-8")
        assert source_manifest_sha256(
            context.candidate_workspace,
            context.candidate_file_manifest,
        ) == source_sha
        with pytest.raises(ValueError, match="outside"):
            apply_deterministic_repair(derived, "rewrite_visible_design")
    finally:
        _close(prepared)


def test_network_guard_blocks_external_dns_and_allows_no_package_manager(
    isolated_runtime_paths,
    monkeypatch,
) -> None:
    limits = runtime_limits()
    result = verify_network_guard(
        cwd=settings.PREVIEW_TEMPLATE_DIR,
        limits=limits,
        env=loopback_only_environment(),
    )
    assert result.exit_code == 0
    assert result.stderr_summary.count("external_network_blocked") == 5
    assert '"kind":"dns"' in result.stderr_summary
    assert '"kind":"http"' in result.stderr_summary
    assert '"kind":"https"' in result.stderr_summary
    assert '"kind":"socket"' in result.stderr_summary
    assert '"kind":"tls"' in result.stderr_summary
    import app.application.runtime_validation.build as build

    observed = []
    original = build.subprocess.run

    def guarded(argv, *args, **kwargs):
        observed.append(tuple(argv))
        assert Path(str(argv[0])).name.lower() not in {
            "npm",
            "npm.cmd",
            "yarn",
            "pnpm",
            "bun",
        }
        assert kwargs.get("shell") is False
        return original(argv, *args, **kwargs)

    monkeypatch.setattr(build.subprocess, "run", guarded)
    versions, _digest = verify_dependency_runtime(
        settings.PREVIEW_TEMPLATE_DIR
    )
    assert versions["react"]
    assert observed == []


def test_dependency_lock_and_installed_versions_fail_closed(
    isolated_runtime_paths,
    monkeypatch,
) -> None:
    prepared = prepare_runtime_candidate(request_id=1804)
    try:
        context = load_runtime_validation_context(
            prepared.prepared.db,
            request_id=prepared.prepared.req.id,
            phase3b_result=prepared.phase3b_result,
        )
        root, _validations = isolated_runtime_paths
        validation_copy = root / "tampered-lock"
        shutil.copytree(prepared.candidate_path, validation_copy)
        lock = validation_copy / "package-lock.json"
        payload = json.loads(lock.read_text(encoding="utf-8"))
        payload["name"] = "tampered-runtime-candidate"
        lock.write_text(json.dumps(payload), encoding="utf-8")
        import app.application.runtime_validation.build as build_module

        monkeypatch.setattr(
            build_module,
            "_dependency_tree_sha256",
            lambda _path: "5" * 64,
        )
        result = run_build_validation(
            refs=context.refs,
            candidate_path=validation_copy,
            frozen_source_path=context.candidate_workspace,
            expected_manifest=context.candidate_file_manifest,
            source_sha_before=context.refs.candidate_manifest_sha256,
            limits=runtime_limits(),
            tools=_tool_fixture(),
        )
        assert result.passed is False
        assert any(
            "dependency-lock content changed" in item
            for item in result.diagnostics
        )
        assert prepared.revision.status == "candidate_build_pending"
    finally:
        _close(prepared)


@pytest.mark.parametrize(
    ("failed_command", "expected_commands"),
    [
        ("typescript_build", ("typescript_build",)),
        ("vite_build", ("typescript_build", "vite_build")),
    ],
)
def test_compile_and_vite_failures_become_bounded_build_results(
    isolated_runtime_paths,
    monkeypatch,
    failed_command,
    expected_commands,
) -> None:
    prepared = prepare_runtime_candidate(request_id=1810)
    try:
        context = load_runtime_validation_context(
            prepared.prepared.db,
            request_id=prepared.prepared.req.id,
            phase3b_result=prepared.phase3b_result,
        )
        root, _validations = isolated_runtime_paths
        validation_copy = root / f"build-{failed_command}"
        shutil.copytree(prepared.candidate_path, validation_copy)
        import app.application.runtime_validation.build as build_module

        monkeypatch.setattr(
            build_module,
            "verify_dependency_runtime",
            lambda _path: ({}, "5" * 64),
        )
        monkeypatch.setattr(
            build_module,
            "_dependency_tree_sha256",
            lambda _path: "5" * 64,
        )
        monkeypatch.setattr(
            build_module,
            "verify_network_guard",
            lambda **_kwargs: _command_result(
                "network_guard_verification"
            ),
        )
        observed = []

        def fake_command(name, argv, **kwargs):
            observed.append(name)
            return _command_result(
                name,
                exit_code=1 if name == failed_command else 0,
            )

        monkeypatch.setattr(build_module, "_command", fake_command)
        result = run_build_validation(
            refs=context.refs,
            candidate_path=validation_copy,
            frozen_source_path=context.candidate_workspace,
            expected_manifest=context.candidate_file_manifest,
            source_sha_before=context.refs.candidate_manifest_sha256,
            limits=runtime_limits(),
            tools=_tool_fixture(),
        )
        assert result.passed is False
        assert tuple(observed) == expected_commands
        assert any(
            (
                "TypeScript project build failed"
                if failed_command == "typescript_build"
                else "Vite production build failed"
            )
            in diagnostic
            for diagnostic in result.diagnostics
        )
        assert result.source_candidate_sha256_before == (
            result.source_candidate_sha256_after
        )
    finally:
        _close(prepared)


def test_command_timeout_is_bounded_and_shell_is_disabled(
    monkeypatch,
) -> None:
    import app.application.runtime_validation.build as build_module

    observed = {}

    def timeout(argv, **kwargs):
        observed["argv"] = tuple(argv)
        observed["shell"] = kwargs["shell"]
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(build_module.subprocess, "run", timeout)
    result = build_module._command(
        "typescript_build",
        ["node", "tsc", "-b"],
        cwd=settings.PREVIEW_TEMPLATE_DIR,
        timeout=1,
        output_limit=1024,
        env={},
    )
    assert result.timed_out is True
    assert result.exit_code == 124
    assert observed == {
        "argv": ("node", "tsc", "-b"),
        "shell": False,
    }


def test_server_start_failure_is_bounded(
    isolated_runtime_paths,
    monkeypatch,
) -> None:
    class FailedProcess:
        returncode = 1

        @staticmethod
        def poll():
            return 1

        @staticmethod
        def communicate(timeout):
            return "", "preview failed"

    import app.application.runtime_validation.server as server_module

    monkeypatch.setattr(
        server_module.subprocess,
        "Popen",
        lambda *args, **kwargs: FailedProcess(),
    )
    root, _validations = isolated_runtime_paths
    with pytest.raises(RuntimeError, match="exited before health"):
        start_preview_server(
            root,
            expected_candidate_manifest_sha256="1" * 64,
            expected_build_hash="2" * 64,
            limits=runtime_limits(),
        )


def test_workspace_storage_failure_does_not_touch_source(
    isolated_runtime_paths,
    monkeypatch,
) -> None:
    prepared = prepare_runtime_candidate(request_id=1811)
    before = prepared.revision.file_manifest_sha256
    try:
        context = load_runtime_validation_context(
            prepared.prepared.db,
            request_id=prepared.prepared.req.id,
            phase3b_result=prepared.phase3b_result,
        )
        monkeypatch.setattr(
            shutil,
            "copytree",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                OSError("simulated storage failure")
            ),
        )
        with pytest.raises(OSError, match="storage failure"):
            open_validation_workspace(
                request_id=context.refs.request_id,
                candidate_revision_uuid=(
                    context.refs.candidate_revision_uuid
                ),
                attempt_uuid=str(uuid.uuid4()),
                cache_identity="a" * 64,
                source_candidate_sha256=before,
                source_path=context.candidate_workspace,
                expected_manifest=context.candidate_file_manifest,
            )
        assert source_manifest_sha256(
            context.candidate_workspace,
            context.candidate_file_manifest,
        ) == before
    finally:
        _close(prepared)


def test_dist_validation_rejects_budgets_maps_remote_assets_and_local_paths(
    isolated_runtime_paths,
) -> None:
    root, _validations = isolated_runtime_paths
    dist = root / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text(
        '<script type="module" src="https://example.com/app.js"></script>',
        encoding="utf-8",
    )
    (dist / "app.js.map").write_text("C:\\Users\\secret", encoding="utf-8")
    limits = runtime_limits().model_copy(
        update={"max_dist_files": 1, "max_dist_bytes": 8}
    )
    _manifest, issues = validate_dist(
        dist,
        limits=limits,
        forbidden_absolute_roots=("C:/Users/secret",),
    )
    assert "dist_file_count_budget_exceeded" in issues
    assert "dist_total_bytes_budget_exceeded" in issues
    assert "source_map_file_budget_exceeded" in issues
    assert any(item.startswith("remote_runtime_asset") for item in issues)


def test_phase4_limits_and_viewports_match_the_approved_policy() -> None:
    limits = runtime_limits()
    assert limits.max_dist_bytes == 5 * 1024 * 1024
    assert limits.max_javascript_bytes == 2 * 1024 * 1024
    assert limits.max_css_bytes == 512 * 1024
    assert limits.max_dist_files == 200
    assert limits.max_source_maps == 0
    assert [
        (item.name, item.width, item.height, item.touch)
        for item in VIEWPORTS
    ] == [
        ("mobile", 390, 844, True),
        ("tablet", 768, 1024, True),
        ("desktop", 1440, 900, False),
    ]
    assert limits.max_browser_contexts == 2
    assert limits.max_browser_pages == 2
    assert limits.max_deterministic_repairs == 1


def test_baseline_accessibility_serious_and_critical_findings_fail() -> None:
    refs = {
        "request_id": 1,
        "candidate_revision_id": 1,
        "candidate_revision_uuid": "00000000-0000-4000-8000-000000000001",
        "candidate_manifest_sha256": "1" * 64,
        "dependency_lock_sha256": "2" * 64,
        "candidate_generator_version": "v2-phase3b",
        "candidate_policy_revision": "2026-07-24.1",
    }
    with pytest.raises(ValidationError):
        AccessibilityRouteResult(
            refs=refs,
            cache_key="3" * 64,
            build_hash="4" * 64,
            page_id="PAGE_ONE",
            route="/",
            viewport="desktop",
            passed=True,
            findings=(
                AccessibilityFinding(
                    rule_id="required-control-name",
                    severity="serious",
                    selector="button",
                    diagnostic_evidence="missing name",
                ),
            ),
            duration_ms=1,
        )
    result = AccessibilityRouteResult(
        refs=refs,
        cache_key="3" * 64,
        build_hash="4" * 64,
        page_id="PAGE_ONE",
        route="/",
        viewport="desktop",
        passed=True,
        findings=(
            AccessibilityFinding(
                rule_id="heading-hierarchy",
                severity="moderate",
                selector="h3",
                diagnostic_evidence="skipped h2",
            ),
        ),
        duration_ms=1,
    )
    assert result.scanner_name == "BaselineAccessibilityScanner"


def test_baseline_accessibility_scanner_detects_and_records_a_real_finding() -> None:
    refs = {
        "request_id": 1,
        "candidate_revision_id": 1,
        "candidate_revision_uuid": "00000000-0000-4000-8000-000000000001",
        "candidate_manifest_sha256": "1" * 64,
        "dependency_lock_sha256": "2" * 64,
        "candidate_generator_version": "v2-phase3b",
        "candidate_policy_revision": "2026-07-24.1",
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("<main><button></button></main>")
        result = run_baseline_accessibility_scan(
            page,
            refs=refs,
            cache_key="3" * 64,
            build_hash="4" * 64,
            page_id="PAGE_ONE",
            route="/one",
            viewport="desktop",
        )
        browser.close()
    assert result.scanner_name == "BaselineAccessibilityScanner"
    assert result.passed is False
    assert any(
        item.rule_id == "required-control-name"
        and item.severity == "serious"
        and item.selector == "button"
        and item.diagnostic_evidence
        for item in result.findings
    )


@pytest.mark.parametrize(
    "failed_field",
    [
        "page_loaded",
        "page_marker_verified",
        "role_marker_verified",
        "component_markers_verified",
        "contract_hooks_verified",
        "reload_verified",
        "direct_navigation_verified",
        "history_verified",
        "overflow_verified",
        "clipping_verified",
        "primary_action_reachable",
        "mobile_bindings_verified",
        "console_errors",
        "page_errors",
        "request_failures",
    ],
)
def test_route_result_cannot_pass_with_a_failed_browser_gate(
    failed_field,
) -> None:
    payload = _route_payload()
    payload[failed_field] = (
        ("diagnostic",)
        if failed_field.endswith("errors")
        or failed_field == "request_failures"
        else False
    )
    with pytest.raises(ValidationError, match="incomplete"):
        RouteViewportResult.model_validate(payload)


def test_incomplete_result_set_cannot_be_runtime_validated() -> None:
    with pytest.raises(ValidationError, match="incomplete"):
        RuntimeValidationSummary(
            refs={
                "request_id": 1,
                "candidate_revision_id": 1,
                "candidate_revision_uuid": (
                    "00000000-0000-4000-8000-000000000001"
                ),
                "candidate_manifest_sha256": "1" * 64,
                "dependency_lock_sha256": "2" * 64,
                "candidate_generator_version": "v2-phase3b",
                "candidate_policy_revision": "2026-07-24.1",
            },
            attempt_uuid="00000000-0000-4000-8000-000000000002",
            status="candidate_runtime_validated",
            source_candidate_sha256_before="1" * 64,
            source_candidate_sha256_after="1" * 64,
            build_result_sha256="3" * 64,
            expected_route_viewport_count=3,
            expected_journey_count=1,
            all_required_gates_passed=True,
            server_identity_verified=True,
            duration_ms=1,
        )


def test_runtime_persistence_is_additive_and_registers_exact_phase4_tables() -> None:
    from app.infrastructure.db.base import Base

    expected = {
        "candidate_runtime_validation_attempts",
        "candidate_build_attempts",
        "candidate_route_results",
        "candidate_journey_results",
        "candidate_accessibility_findings",
        "candidate_screenshots",
        "candidate_validation_summaries",
    }
    assert expected <= set(Base.metadata.tables)


def test_terminal_persistence_rolls_back_on_storage_failure(
    isolated_runtime_paths,
    monkeypatch,
) -> None:
    prepared = prepare_runtime_candidate(request_id=1812)
    db = prepared.prepared.db
    try:
        context = load_runtime_validation_context(
            db,
            request_id=prepared.prepared.req.id,
            phase3b_result=prepared.phase3b_result,
        )
        limits = runtime_limits()
        tools = _tool_fixture()
        cache_identity = _attempt_cache_identity(
            context,
            tools=tools,
            limits=limits,
        )
        repository = RuntimeValidationRepository(db)
        attempt = repository.create_attempt(
            attempt_uuid=str(uuid.uuid4()),
            refs=context.refs,
            cache_identity=cache_identity,
            source_candidate_sha256_before=(
                context.refs.candidate_manifest_sha256
            ),
            tools=tools,
            limits=limits,
            workspace_relpath="staging/transaction-test",
        )
        build_result = _failed_build(context, limits)
        build = repository.persist_build(
            attempt=attempt,
            result=build_result,
            workspace_relpath="staging/transaction-test/candidate",
        )
        db.commit()
        summary = _failure_summary(
            context=context,
            attempt_uuid=attempt.attempt_uuid,
            status="candidate_build_failed",
            source_before=context.refs.candidate_manifest_sha256,
            source_after=context.refs.candidate_manifest_sha256,
            build_result=build_result,
            failure_stage="build",
            diagnostics=("simulated build failure",),
            duration_ms=1,
        )
        generated_pages_before = prepared.prepared.req.generated_pages
        original_flush = db.flush

        def fail_flush(*args, **kwargs):
            raise OSError("simulated terminal storage failure")

        monkeypatch.setattr(db, "flush", fail_flush)
        with pytest.raises(OSError, match="terminal storage failure"):
            repository.persist_terminal(
                req=prepared.prepared.req,
                attempt=attempt,
                build=build.row,
                routes=(),
                journeys=(),
                accessibility=(),
                screenshots=(),
                summary=summary,
            )
        db.rollback()
        monkeypatch.setattr(db, "flush", original_flush)
        db.refresh(prepared.prepared.req)
        assert prepared.prepared.req.generated_pages == generated_pages_before
        assert db.query(CandidateValidationSummaryRecord).count() == 0
        assert db.query(CandidateRouteResultRecord).count() == 0
        assert db.query(CandidateJourneyResultRecord).count() == 0
        assert db.query(CandidateAccessibilityFindingRecord).count() == 0
        assert db.query(CandidateScreenshotRecord).count() == 0
    finally:
        _close(prepared)


def test_validated_summary_rejects_missing_screenshot_evidence(
    isolated_runtime_paths,
) -> None:
    prepared = prepare_runtime_candidate(request_id=1813)
    db = prepared.prepared.db
    try:
        context = load_runtime_validation_context(
            db,
            request_id=prepared.prepared.req.id,
            phase3b_result=prepared.phase3b_result,
        )
        limits = runtime_limits()
        tools = _tool_fixture()
        repository = RuntimeValidationRepository(db)
        attempt = repository.create_attempt(
            attempt_uuid=str(uuid.uuid4()),
            refs=context.refs,
            cache_identity=_attempt_cache_identity(
                context,
                tools=tools,
                limits=limits,
            ),
            source_candidate_sha256_before=(
                context.refs.candidate_manifest_sha256
            ),
            tools=tools,
            limits=limits,
            workspace_relpath="staging/evidence-test",
        )
        build = repository.persist_build(
            attempt=attempt,
            result=_passing_build(context, limits),
            workspace_relpath="staging/evidence-test/candidate",
        )
        routes = tuple(
            RouteViewportResult.model_validate(
                {
                    **_route_payload(),
                    "refs": context.refs.model_dump(mode="json"),
                    "build_hash": build.result.build_hash,
                    "page_id": "PAGE-BOOK",
                    "route": "/book",
                    "viewport": viewport.name,
                }
            )
            for viewport in VIEWPORTS
        )
        journey = JourneyValidationResult(
            refs=context.refs,
            cache_key="9" * 64,
            build_hash=build.result.build_hash,
            journey_id="JOURNEY-BOOK",
            action_id="ACTION-BOOK",
            acceptance_test_ids=("TEST-BOOK",),
            route="/book",
            passed=True,
            reduced_motion_required=True,
            reduced_motion_passed=True,
            steps=(
                JourneyStepResult(
                    step="reduced_motion",
                    canonical_id="ACTION-BOOK",
                    passed=True,
                ),
            ),
            duration_ms=1,
        )
        accessibility = tuple(
            AccessibilityRouteResult(
                refs=context.refs,
                cache_key="a" * 64,
                build_hash=build.result.build_hash,
                page_id="PAGE-BOOK",
                route="/book",
                viewport=viewport.name,
                passed=True,
                duration_ms=1,
            )
            for viewport in VIEWPORTS
        )
        screenshots = tuple(
            ScreenshotEvidence(
                refs=context.refs,
                cache_key="b" * 64,
                build_hash=build.result.build_hash,
                page_id="PAGE-BOOK",
                route="/book",
                viewport=viewport.name,
                relative_path=f"missing/{viewport.name}.png",
                sha256="c" * 64,
                byte_count=10,
                browser_version="chromium-test",
                captured_at="2026-07-24T00:00:00+00:00",
            )
            for viewport in VIEWPORTS
        )
        summary = RuntimeValidationSummary(
            refs=context.refs,
            attempt_uuid=attempt.attempt_uuid,
            status="candidate_runtime_validated",
            source_candidate_sha256_before=(
                context.refs.candidate_manifest_sha256
            ),
            source_candidate_sha256_after=(
                context.refs.candidate_manifest_sha256
            ),
            build_result_sha256=artifact_sha256(build.result),
            route_result_hashes=tuple(
                artifact_sha256(item) for item in routes
            ),
            journey_result_hashes=(artifact_sha256(journey),),
            accessibility_result_hashes=tuple(
                artifact_sha256(item) for item in accessibility
            ),
            screenshot_hashes=tuple(item.sha256 for item in screenshots),
            expected_route_viewport_count=3,
            expected_journey_count=1,
            all_required_gates_passed=True,
            server_identity_verified=True,
            duration_ms=1,
        )
        with pytest.raises(
            ValueError,
            match="Screenshot evidence is missing or corrupt",
        ):
            repository.persist_terminal(
                req=prepared.prepared.req,
                attempt=attempt,
                build=build.row,
                routes=routes,
                journeys=(journey,),
                accessibility=accessibility,
                screenshots=screenshots,
                summary=summary,
            )
        db.rollback()
        assert db.query(CandidateValidationSummaryRecord).count() == 0
    finally:
        _close(prepared)


def test_tool_or_limit_change_invalidates_build_and_dist_cache_keys() -> None:
    payload = _route_payload()["refs"]
    from app.domain.schemas.runtime_validation import RuntimeValidationRefs

    refs = RuntimeValidationRefs.model_validate(payload)
    limits = runtime_limits()
    tools = _tool_fixture()
    baseline = build_cache_keys(refs=refs, limits=limits, tools=tools)
    changed_tool = build_cache_keys(
        refs=refs,
        limits=limits,
        tools=tools.model_copy(update={"vite": "8.1.4"}),
    )
    changed_limit = build_cache_keys(
        refs=refs,
        limits=limits.model_copy(
            update={"max_dist_bytes": limits.max_dist_bytes - 1}
        ),
        tools=tools,
    )
    assert baseline[0] != changed_tool[0]
    assert baseline[1] != changed_tool[1]
    assert baseline[0] == changed_limit[0]
    assert baseline[1] != changed_limit[1]


def test_disabled_flag_preserves_phase3b_boundary(
    isolated_runtime_paths,
    monkeypatch,
) -> None:
    prepared = prepare_runtime_candidate(request_id=1805)
    monkeypatch.setattr(
        settings,
        "V2_RUNTIME_VALIDATION_ENABLED",
        False,
    )
    try:
        with pytest.raises(RuntimeValidationError, match="disabled"):
            run_phase4(prepared)
        assert prepared.revision.status == "candidate_build_pending"
        assert (
            prepared.prepared.db.query(
                CandidateRuntimeValidationAttemptRecord
            ).count()
            == 0
        )
    finally:
        _close(prepared)


def test_runtime_flag_cannot_bypass_disabled_v2_boundary(
    isolated_runtime_paths,
    monkeypatch,
) -> None:
    prepared = prepare_runtime_candidate(request_id=1814)
    monkeypatch.setattr(settings, "PREVIEW_GENERATOR_V2", False)
    monkeypatch.setattr(settings, "V2_RUNTIME_VALIDATION_ENABLED", True)
    try:
        with pytest.raises(RuntimeValidationError, match="disabled"):
            run_phase4(prepared)
        assert (
            prepared.prepared.db.query(
                CandidateRuntimeValidationAttemptRecord
            ).count()
            == 0
        )
        assert prepared.revision.status == "candidate_build_pending"
    finally:
        _close(prepared)
