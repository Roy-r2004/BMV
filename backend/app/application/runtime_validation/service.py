"""Phase 4 coordinator: immutable build, fresh-server runtime gates, no AI."""
from __future__ import annotations

import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.application.candidate_generation.cache import canonical_sha256
from app.application.runtime_validation.browser import (
    browser_cache_keys,
    run_browser_validation,
)
from app.application.runtime_validation.build import (
    build_cache_keys,
    restore_cached_build,
    run_build_validation,
)
from app.application.runtime_validation.cache import (
    artifact_sha256,
    runtime_cache_key,
    sha256_file,
)
from app.application.runtime_validation.context import (
    RuntimeValidationContext,
    load_runtime_validation_context,
)
from app.application.runtime_validation.dist import (
    dist_manifest,
    dist_manifest_sha256,
)
from app.application.runtime_validation.policy import (
    VIEWPORTS,
    runtime_limits,
    tool_versions,
)
from app.application.runtime_validation.repository import (
    PersistedBuild,
    RuntimeValidationRepository,
)
from app.application.runtime_validation.server import (
    PreviewServer,
    start_preview_server,
)
from app.application.runtime_validation.workspace import (
    apply_deterministic_repair,
    create_derived_repair_workspace,
    freeze_validation_workspace,
    open_validation_workspace,
    source_manifest_sha256,
    validation_root,
    workspace_relpath,
)
from app.core.config import settings
from app.domain.models import Request
from app.domain.schemas.runtime_validation import (
    BuildValidationResult,
    RuntimeValidationSummary,
    ScreenshotEvidence,
)


class RuntimeValidationError(RuntimeError):
    pass


def _phase_deadline(started: float, seconds: int) -> float:
    return started + seconds


def _ensure_deadline(deadline: float) -> None:
    if time.monotonic() > deadline:
        raise TimeoutError("Phase 4 wall timeout exceeded")


def _attempt_cache_identity(
    context: RuntimeValidationContext,
    *,
    tools,
    limits,
) -> str:
    return runtime_cache_key(
        "runtime_attempt",
        {
            "refs": context.refs.model_dump(mode="json"),
            "tools": tools.model_dump(mode="json"),
            "limits": limits.model_dump(mode="json"),
            "viewport_policy": [
                item.model_dump(mode="json") for item in VIEWPORTS
            ],
            "acceptance_projection_revision": "2026-07-24.1",
        },
    )


def _final_candidate_relpath(workspace, active_candidate_path: Path) -> str:
    relative = active_candidate_path.relative_to(workspace.staging_path)
    return workspace_relpath(workspace.final_path / relative)


def _repair_code(result: BuildValidationResult) -> str | None:
    text = "\n".join(result.diagnostics)
    if "route_fallback_configuration" in text:
        return "route_fallback_configuration"
    if (
        "missing_local_asset:" in text
        or "asset_path_normalization" in text
        or "remote_runtime_asset:" in text
    ):
        return "asset_path_normalization"
    if "manifest_wiring" in text:
        return "manifest_wiring"
    if "recognized_build_configuration" in text:
        return "recognized_build_configuration"
    return None


def _restore_cached_screenshots(
    cached,
    *,
    evidence_root: Path,
    evidence_relbase: str,
) -> tuple[ScreenshotEvidence, ...]:
    restored = []
    root = validation_root().resolve(strict=False)
    for row, evidence in cached:
        source = (root / evidence.relative_path).resolve(strict=False)
        try:
            source.relative_to(root)
        except ValueError as exc:
            raise ValueError("Cached screenshot escapes validation root") from exc
        if (
            not source.is_file()
            or sha256_file(source) != evidence.sha256
            or source.stat().st_size != evidence.byte_count
        ):
            raise ValueError("Cached screenshot evidence is corrupt")
        target = (
            evidence_root
            / "screenshots"
            / evidence.viewport
            / Path(evidence.relative_path).name
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if sha256_file(target) != evidence.sha256:
            raise ValueError("Restored screenshot hash changed")
        restored.append(
            evidence.model_copy(
                update={
                    "relative_path": (
                        f"{evidence_relbase}/screenshots/"
                        f"{evidence.viewport}/{target.name}"
                    )
                }
            )
        )
    return tuple(restored)


def _failure_summary(
    *,
    context: RuntimeValidationContext,
    attempt_uuid: str,
    status: str,
    source_before: str,
    source_after: str,
    build_result: BuildValidationResult,
    failure_stage: str,
    diagnostics: tuple[str, ...],
    duration_ms: int,
    server_command=None,
    network_diagnostics: tuple[str, ...] = (),
) -> RuntimeValidationSummary:
    return RuntimeValidationSummary(
        refs=context.refs,
        attempt_uuid=attempt_uuid,
        status=status,
        source_candidate_sha256_before=source_before,
        source_candidate_sha256_after=source_after,
        build_result_sha256=artifact_sha256(build_result),
        expected_route_viewport_count=(
            len(context.contracts.page_purpose.pages) * len(VIEWPORTS)
        ),
        expected_journey_count=sum(
            len(item.journey_ids)
            for item in context.contracts.interactions.interactions
        ),
        all_required_gates_passed=False,
        server_identity_verified=False,
        server_command=server_command,
        network_diagnostics=network_diagnostics,
        failure_stage=failure_stage,
        diagnostics=diagnostics or ("runtime_validation_failed",),
        duration_ms=duration_ms,
    )


def _result_payload(
    context: RuntimeValidationContext,
    *,
    summary_row,
    summary: RuntimeValidationSummary,
    build: PersistedBuild,
    cache_hits: tuple[str, ...],
    final_path: Path,
) -> dict[str, Any]:
    preview = {
        **context.phase3b_summary,
        "status": summary.status,
        "runtime_validation_summary": {
            "id": summary_row.id,
            "attempt_uuid": summary.attempt_uuid,
            "sha256": summary_row.summary_sha256,
            "source_candidate_sha256_before": (
                summary.source_candidate_sha256_before
            ),
            "source_candidate_sha256_after": (
                summary.source_candidate_sha256_after
            ),
        },
        "runtime_build": {
            "attempt_id": build.row.id,
            "build_hash": build.result.build_hash,
            "dist_manifest_sha256": build.result.dist_manifest_sha256,
            "cache_hit": build.result.cache_hit,
            "diagnostics": list(build.result.diagnostics),
            "commands": [
                {
                    "name": item.command_name,
                    "exit_code": item.exit_code,
                    "timed_out": item.timed_out,
                    "stderr": item.stderr_summary,
                }
                for item in build.result.commands
            ],
        },
        "runtime_cache_hits": list(cache_hits),
        "runtime_validation_workspace": workspace_relpath(final_path),
        "runtime_validation": {
            "diagnostics": list(summary.diagnostics),
            "network_diagnostics": list(summary.network_diagnostics),
            "route_result_count": len(summary.route_result_hashes),
            "journey_result_count": len(summary.journey_result_hashes),
            "accessibility_result_count": len(
                summary.accessibility_result_hashes
            ),
            "screenshot_count": len(summary.screenshot_hashes),
        },
        "provider_call_count": 0,
    }
    return {"preview_contract": preview}


def validate_v2_candidate_runtime(
    db: Session,
    request_id: int,
    *,
    req: Request,
    phase3b_result: dict[str, Any],
) -> dict[str, Any]:
    """Build and validate one Phase 3B candidate without AI or promotion."""

    if not (
        settings.PREVIEW_GENERATOR_V2
        and settings.V2_RUNTIME_VALIDATION_ENABLED
    ):
        raise RuntimeValidationError("Phase 4 runtime validation is disabled")
    started = time.monotonic()
    limits = runtime_limits()
    deadline = _phase_deadline(started, limits.phase_timeout_seconds)
    tools = tool_versions()
    context = load_runtime_validation_context(
        db,
        request_id=request_id,
        phase3b_result=phase3b_result,
    )
    source_before = source_manifest_sha256(
        context.candidate_workspace,
        context.candidate_file_manifest,
    )
    if source_before != context.refs.candidate_manifest_sha256:
        raise RuntimeValidationError("Frozen candidate manifest is corrupt")
    cache_identity = _attempt_cache_identity(
        context,
        tools=tools,
        limits=limits,
    )
    repository = RuntimeValidationRepository(db)
    resumable = repository.find_resumable_attempt(
        candidate_revision_id=context.refs.candidate_revision_id,
        cache_identity=cache_identity,
    )
    workspace = None
    attempt = None
    if resumable is not None:
        try:
            repository.validate_attempt(
                resumable,
                refs=context.refs,
                cache_identity=cache_identity,
                source_candidate_sha256_before=source_before,
                tools=tools,
                limits=limits,
            )
            workspace = open_validation_workspace(
                request_id=request_id,
                candidate_revision_uuid=(
                    context.refs.candidate_revision_uuid
                ),
                attempt_uuid=resumable.attempt_uuid,
                cache_identity=cache_identity,
                source_candidate_sha256=source_before,
                source_path=context.candidate_workspace,
                expected_manifest=context.candidate_file_manifest,
                resume_relpath=resumable.workspace_relpath,
            )
            attempt = resumable
        except Exception:
            db.rollback()
            workspace = None
            attempt = None
    if workspace is None:
        attempt_uuid = str(uuid.uuid4())
        workspace = open_validation_workspace(
            request_id=request_id,
            candidate_revision_uuid=context.refs.candidate_revision_uuid,
            attempt_uuid=attempt_uuid,
            cache_identity=cache_identity,
            source_candidate_sha256=source_before,
            source_path=context.candidate_workspace,
            expected_manifest=context.candidate_file_manifest,
        )
        attempt = repository.create_attempt(
            attempt_uuid=attempt_uuid,
            refs=context.refs,
            cache_identity=cache_identity,
            source_candidate_sha256_before=source_before,
            tools=tools,
            limits=limits,
            workspace_relpath=workspace_relpath(workspace.staging_path),
            resumed_from_attempt_id=(
                resumable.id if resumable is not None else None
            ),
        )
        db.commit()
    active_candidate = workspace.candidate_path
    build_key, dist_key = build_cache_keys(
        refs=context.refs,
        limits=limits,
        tools=tools,
    )
    cache_hits: list[str] = []
    cached_build = repository.find_build_cache(
        candidate_revision_id=context.refs.candidate_revision_id,
        build_cache_key=build_key,
        dist_cache_key=dist_key,
    )
    if cached_build is not None:
        cached_candidate = (
            validation_root()
            / cached_build.row.workspace_relpath
        )
        if (
            cached_build.row.runtime_attempt_id == attempt.id
            and not cached_candidate.is_dir()
        ):
            final_root = workspace.final_path.resolve(strict=False)
            try:
                current_relative = cached_candidate.resolve(
                    strict=False
                ).relative_to(final_root)
            except ValueError as exc:
                raise RuntimeValidationError(
                    "Resumable build cache escapes its workspace"
                ) from exc
            cached_candidate = workspace.staging_path / current_relative
        cached_dist = cached_candidate / "dist"
        build_result = restore_cached_build(
            cached=cached_build.result,
            cached_dist=cached_dist,
            candidate_path=active_candidate,
            frozen_source_path=context.candidate_workspace,
            expected_manifest=context.candidate_file_manifest,
            source_sha_before=source_before,
        )
        cache_hits.extend(("build", "dist"))
    else:
        build_result = run_build_validation(
            refs=context.refs,
            candidate_path=active_candidate,
            frozen_source_path=context.candidate_workspace,
            expected_manifest=context.candidate_file_manifest,
            source_sha_before=source_before,
            limits=limits,
            tools=tools,
        )
    persisted_build = repository.persist_build(
        attempt=attempt,
        result=build_result,
        workspace_relpath=_final_candidate_relpath(
            workspace,
            active_candidate,
        ),
    )
    db.commit()
    _ensure_deadline(deadline)

    if (
        not build_result.passed
        and limits.max_deterministic_repairs
        and _repair_code(build_result)
    ):
        repair_code = _repair_code(build_result)
        derived = create_derived_repair_workspace(
            workspace,
            repair_uuid=str(uuid.uuid4()),
        )
        apply_deterministic_repair(derived, repair_code)
        active_candidate = derived
        repaired_result = run_build_validation(
            refs=context.refs,
            candidate_path=active_candidate,
            frozen_source_path=context.candidate_workspace,
            expected_manifest=context.candidate_file_manifest,
            source_sha_before=source_before,
            limits=limits,
            tools=tools,
            deterministic_repair_count=1,
            derived_from_build_attempt_id=persisted_build.row.id,
        )
        persisted_build = repository.persist_build(
            attempt=attempt,
            result=repaired_result,
            workspace_relpath=_final_candidate_relpath(
                workspace,
                active_candidate,
            ),
            parent_build_attempt_id=persisted_build.row.id,
        )
        build_result = repaired_result
        db.commit()
    if not build_result.passed:
        final_path = freeze_validation_workspace(workspace)
        summary = _failure_summary(
            context=context,
            attempt_uuid=attempt.attempt_uuid,
            status="candidate_build_failed",
            source_before=source_before,
            source_after=build_result.source_candidate_sha256_after,
            build_result=build_result,
            failure_stage="build",
            diagnostics=build_result.diagnostics,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        try:
            summary_row = repository.persist_terminal(
                req=req,
                attempt=attempt,
                build=persisted_build.row,
                routes=(),
                journeys=(),
                accessibility=(),
                screenshots=(),
                summary=summary,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        return _result_payload(
            context,
            summary_row=summary_row,
            summary=summary,
            build=persisted_build,
            cache_hits=tuple(cache_hits),
            final_path=final_path,
        )

    server: PreviewServer | None = None
    server_command = None
    routes = ()
    journeys = ()
    accessibility = ()
    screenshots = ()
    network_diagnostics: tuple[str, ...] = ()
    try:
        server, _identity = start_preview_server(
            active_candidate,
            expected_candidate_manifest_sha256=(
                context.refs.candidate_manifest_sha256
            ),
            expected_build_hash=build_result.build_hash,
            limits=limits,
        )
        _ensure_deadline(deadline)
        keys = browser_cache_keys(
            context,
            build_hash=build_result.build_hash,
            browser_version=tools.browser_version,
        )
        expected_route_count = len(
            context.contracts.page_purpose.pages
        ) * len(VIEWPORTS)
        expected_journey_count = sum(
            len(item.journey_ids)
            for item in context.contracts.interactions.interactions
        )
        cached_routes = repository.route_cache(
            context.refs.candidate_revision_id,
            keys["route"],
        )
        if len(cached_routes) != expected_route_count:
            cached_routes = ()
        else:
            cache_hits.append("route")
        cached_journeys = repository.journey_cache(
            context.refs.candidate_revision_id,
            keys["journey"],
        )
        if len(cached_journeys) != expected_journey_count:
            cached_journeys = ()
        else:
            cache_hits.append("journey")
        cached_accessibility = repository.accessibility_cache(
            context.refs.candidate_revision_id,
            keys["accessibility"],
        )
        if len(cached_accessibility) != expected_route_count:
            cached_accessibility = ()
        else:
            cache_hits.append("accessibility")
        raw_cached_screenshots = repository.screenshot_cache(
            context.refs.candidate_revision_id,
            keys["screenshot"],
        )
        evidence_root = workspace.staging_path / "evidence"
        evidence_relbase = (
            workspace_relpath(workspace.final_path) + "/evidence"
        )
        if len(raw_cached_screenshots) == expected_route_count:
            cached_screenshots = _restore_cached_screenshots(
                raw_cached_screenshots,
                evidence_root=evidence_root,
                evidence_relbase=evidence_relbase,
            )
            cache_hits.append("screenshot")
        else:
            cached_screenshots = ()
        bundle = run_browser_validation(
            context=context,
            base_url=server.base_url,
            build_hash=build_result.build_hash,
            evidence_root=evidence_root,
            evidence_relbase=evidence_relbase,
            limits=limits,
            cache_browser_version=tools.browser_version,
            cached_routes=cached_routes,
            cached_journeys=cached_journeys,
            cached_accessibility=cached_accessibility,
            cached_screenshots=cached_screenshots,
        )
        routes = bundle.routes
        journeys = bundle.journeys
        accessibility = bundle.accessibility
        screenshots = bundle.screenshots
        network_diagnostics = bundle.network_diagnostics
        _ensure_deadline(deadline)
    except Exception as exc:
        failure = f"{type(exc).__name__}: {str(exc)[:4000]}"
        if server is not None:
            server_command = server.stop()
            server = None
        source_after = source_manifest_sha256(
            context.candidate_workspace,
            context.candidate_file_manifest,
        )
        try:
            final_path = freeze_validation_workspace(workspace)
        except Exception:
            final_path = workspace.staging_path
        summary = _failure_summary(
            context=context,
            attempt_uuid=attempt.attempt_uuid,
            status="candidate_runtime_failed",
            source_before=source_before,
            source_after=source_after,
            build_result=build_result,
            failure_stage="runtime",
            diagnostics=(failure,),
            duration_ms=int((time.monotonic() - started) * 1000),
            server_command=server_command,
            network_diagnostics=network_diagnostics,
        )
        summary_row = repository.persist_terminal(
            req=req,
            attempt=attempt,
            build=persisted_build.row,
            routes=routes,
            journeys=journeys,
            accessibility=accessibility,
            screenshots=screenshots,
            summary=summary,
        )
        db.commit()
        return _result_payload(
            context,
            summary_row=summary_row,
            summary=summary,
            build=persisted_build,
            cache_hits=tuple(cache_hits),
            final_path=final_path,
        )
    finally:
        if server is not None:
            server_command = server.stop()

    source_after = source_manifest_sha256(
        context.candidate_workspace,
        context.candidate_file_manifest,
    )
    expected_route_count = len(context.contracts.page_purpose.pages) * len(
        VIEWPORTS
    )
    expected_journey_count = sum(
        len(item.journey_ids)
        for item in context.contracts.interactions.interactions
    )
    gates_passed = (
        source_before == source_after
        and len(routes) == expected_route_count
        and len(accessibility) == expected_route_count
        and len(screenshots) == expected_route_count
        and len(journeys) == expected_journey_count
        and all(item.passed for item in routes)
        and all(item.passed for item in journeys)
        and all(item.passed for item in accessibility)
        and not network_diagnostics
    )
    status = (
        "candidate_runtime_validated"
        if gates_passed
        else "candidate_runtime_failed"
    )
    diagnostics = []
    if source_before != source_after:
        diagnostics.append("frozen_candidate_mutated")
    if len(routes) != expected_route_count:
        diagnostics.append("route_viewport_matrix_incomplete")
    if len(journeys) != expected_journey_count:
        diagnostics.append("journey_matrix_incomplete")
    if any(not item.passed for item in routes):
        diagnostics.append("route_gate_failed")
    if any(not item.passed for item in journeys):
        diagnostics.append("journey_gate_failed")
    if any(not item.passed for item in accessibility):
        diagnostics.append("accessibility_baseline_failed")
    if len(screenshots) != expected_route_count:
        diagnostics.append("screenshot_matrix_incomplete")
    diagnostics.extend(network_diagnostics)
    final_path = freeze_validation_workspace(workspace)
    summary = RuntimeValidationSummary(
        refs=context.refs,
        attempt_uuid=attempt.attempt_uuid,
        status=status,
        source_candidate_sha256_before=source_before,
        source_candidate_sha256_after=source_after,
        build_result_sha256=artifact_sha256(build_result),
        route_result_hashes=tuple(artifact_sha256(item) for item in routes),
        journey_result_hashes=tuple(
            artifact_sha256(item) for item in journeys
        ),
        accessibility_result_hashes=tuple(
            artifact_sha256(item) for item in accessibility
        ),
        screenshot_hashes=tuple(item.sha256 for item in screenshots),
        expected_route_viewport_count=expected_route_count,
        expected_journey_count=expected_journey_count,
        all_required_gates_passed=gates_passed,
        server_identity_verified=True,
        cache_hits=tuple(cache_hits),
        server_command=server_command,
        network_diagnostics=network_diagnostics,
        failure_stage=None if gates_passed else "runtime_gates",
        diagnostics=tuple(diagnostics),
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    try:
        summary_row = repository.persist_terminal(
            req=req,
            attempt=attempt,
            build=persisted_build.row,
            routes=routes,
            journeys=journeys,
            accessibility=accessibility,
            screenshots=screenshots,
            summary=summary,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _result_payload(
        context,
        summary_row=summary_row,
        summary=summary,
        build=persisted_build,
        cache_hits=tuple(cache_hits),
        final_path=final_path,
    )


__all__ = [
    "RuntimeValidationError",
    "validate_v2_candidate_runtime",
]
