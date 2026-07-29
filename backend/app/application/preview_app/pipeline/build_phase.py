"""Preview pipeline — Vite build + AI fix loop + regen/stabilize/nuclear +
visual critique.
"""
from __future__ import annotations

import re
import shutil
import tempfile
import time
from pathlib import Path

from app.application.preview_app.assemble import write_plumbing_mock
from app.application.preview_app.build import extract_build_errors, run_build
from app.application.preview_app.catalogue_contract import catalogue_route_for_file
from app.application.preview_app.codegen.fix_agent import fix_build_errors, fix_type_errors
from app.application.preview_app.fallback import (
    find_broken_paths,
    is_chrome_path,
    stabilize_all_route_pages,
    write_safe_stub,
    write_template_fallback,
)
from app.application.preview_app.parallel import parallel_map
from app.application.preview_app.pipeline.codegen_phase import _generate_spec
from app.application.preview_app.pipeline.context import PipelineContext
from app.application.preview_app.pipeline.polish_phase import _pre_build_fixups
from app.application.preview_app.pipeline.visual_critic import _run_visual_critique
from app.application.preview_app.safety.source_sanitize import find_truncated_pages
from app.application.preview_app.typecheck import (
    TypecheckReport,
    group_by_file,
    record_typecheck_report,
    typecheck_workspace,
)
from app.application.preview_app.workspace import list_source_files, read_file, write_file
from app.application.services.progress import emit as _emit
from app.core.config import settings
from app.infrastructure.logging import WatchBmv, get_logger
from app.infrastructure.logging.diagnostics import dump_exception

log = get_logger("PreviewPipeline")


def _source_snapshot(workspace: Path) -> dict[str, str]:
    return {rel: read_file(workspace, rel) for rel in list_source_files(workspace)}


def _restore_snapshot(
    workspace: Path,
    snapshot: dict[str, str],
    only: list[str] | None = None,
) -> list[str]:
    """Roll files back to `snapshot`. With `only`, revert just those paths.

    Selective revert is what lets one bad patch out of eight cost only itself.
    """
    targets = snapshot if only is None else {
        rel: snapshot[rel] for rel in only if rel in snapshot
    }
    restored: list[str] = []
    for rel, content in targets.items():
        if read_file(workspace, rel) != content:
            write_file(workspace, rel, content)
            restored.append(rel)
    return restored


def _error_counts(report: TypecheckReport) -> dict[str, int]:
    return {path: len(diags) for path, diags in group_by_file(report.diagnostics).items()}


# A parse failure is the one class of type error that also breaks `vite build`,
# and it hides itself from an error-count comparison: `tsc` abandons a file it
# cannot parse and reports a single "'}' expected." where twelve type errors
# stood, so the file scores as improved while the build is broken.
#
# Matched on the message rather than a TS1xxx code range, because that range
# also holds grammar complaints esbuild accepts — TS1117 (duplicate object key)
# being the one this pipeline hits most.
_PARSE_FAILURE_RE = re.compile(
    r"expected\.|Unexpected token|Unterminated|Invalid character",
    re.IGNORECASE,
)


def _unparseable_files(report: TypecheckReport) -> set[str]:
    """Files whose diagnostics say `tsc` could not parse them."""
    return {
        d.file
        for d in report.diagnostics
        if d.file and _PARSE_FAILURE_RE.search(d.message)
    }


def _regressed_files(
    before: TypecheckReport,
    after: TypecheckReport,
    patched: list[str],
) -> list[str]:
    """Which patched files the model made worse.

    A whole-batch rollback throws away every good patch because one file was
    bad, which is why this loop has never landed a repair. Comparing per-file
    error counts across the two reports isolates the offenders: only files that
    gained errors, or gained a parse failure, are given back.

    Returns [] when either report is unavailable — with no measurement there is
    no evidence any file regressed, and guessing would discard good work.
    """
    if not (before.available and after.available):
        return []
    before_counts = _error_counts(before)
    after_counts = _error_counts(after)
    newly_unparseable = _unparseable_files(after) - _unparseable_files(before)
    return sorted(
        path
        for path in patched
        if after_counts.get(path, 0) > before_counts.get(path, 0)
        or path in newly_unparseable
    )


def _backup_dist(workspace: Path) -> Path | None:
    """Copy the shipping dist outside the workspace before we risk rebuilding it.

    `vite build` empties outDir on start, so a failed rebuild removes a dist the
    customer could already have been served. Kept out of the workspace tree so
    no gate, asset scan, or route walker ever sees it.
    """
    dist = Path(workspace) / "dist"
    if not (dist / "index.html").is_file():
        return None
    try:
        backup = Path(tempfile.mkdtemp(prefix="bmv-dist-")) / "dist"
        shutil.copytree(dist, backup)
    except OSError as exc:
        log.warning("    could not back up dist before typecheck repair: %s", exc)
        return None
    return backup


def _restore_dist(workspace: Path, backup: Path | None) -> bool:
    dist = Path(workspace) / "dist"
    if backup is None or not (backup / "index.html").is_file():
        return False
    if (dist / "index.html").is_file():
        return False
    try:
        shutil.rmtree(dist, ignore_errors=True)
        shutil.copytree(backup, dist)
    except OSError as exc:
        log.error("    could not restore dist backup: %s", exc)
        return False
    log.warning("    restored the pre-typecheck dist — preview still serves")
    return True


def _log_typecheck(report: TypecheckReport, label: str) -> None:
    if not report.available:
        log.warning("    typecheck %s UNAVAILABLE — %s", label, report.reason)
    elif report.clean:
        log.info("    typecheck %s: clean (%sms)", label, report.duration_ms)
    else:
        log.warning(
            "    typecheck %s: %s error(s) in %s file(s) — %s",
            label,
            report.error_count,
            len(report.files),
            ", ".join(f"{code}x{count}" for code, count in report.summary()["codes"].items()),
        )


def _run_typecheck_repair(ctx: PipelineContext) -> TypecheckReport:
    """Typecheck the built app and repair contract violations, bounded.

    Runs only on a workspace whose Vite build already succeeded. Type errors are
    a quality signal, never a reason to ship nothing: leftover errors are
    recorded (``.bmv-debug/typecheck/summary.json``) and the app still serves.

    Each round is screened by `tsc` (~2s) before `vite build` (~20s) is spent on
    it. Files the model made worse are handed back individually and the rest of
    the batch is kept, so one bad patch out of eight costs one patch rather than
    all eight. Only if the build still fails after that screening does the round
    roll back wholesale.
    """
    workspace = ctx.workspace
    timeout = settings.PREVIEW_TYPECHECK_TIMEOUT_SECONDS
    report = typecheck_workspace(workspace, timeout=timeout)
    _log_typecheck(report, "initial")
    rounds_run = 0
    if report.status == "errors":
        started = time.monotonic()
        dist_backup = _backup_dist(workspace)
        rejections: list[str] = []
        for round_number in range(1, settings.PREVIEW_MAX_TYPECHECK_FIX_ROUNDS + 1):
            elapsed = time.monotonic() - started
            if elapsed > ctx.max_fix_seconds:
                log.warning(
                    "    typecheck repair budget exceeded (%.0fs) — keeping remaining errors",
                    elapsed,
                )
                break
            _emit(
                ctx.db, ctx.request_id, "build",
                f"Fixing {report.error_count} type contract error(s) "
                f"(round {round_number}/{settings.PREVIEW_MAX_TYPECHECK_FIX_ROUNDS})...",
                89,
                detail="AI is aligning page data with the component contracts",
            )
            snapshot = _source_snapshot(workspace)
            round_rejections: list[str] = []
            try:
                patched = fix_type_errors(
                    workspace, report, ctx.architect, ctx.ai_provider, ctx.template_renderer,
                    prior_rejections=rejections,
                    rejections_out=round_rejections,
                )
            except Exception as exc:
                dump_exception(
                    workspace, "typecheck-fix", f"round-{round_number}", exc,
                    context={"errors": report.error_count},
                )
                log.error("    typecheck fix agent failed on round %s: %s", round_number, exc)
                break
            rounds_run = round_number
            rejections = round_rejections
            log.info("    typecheck round %s patched: %s", round_number, ", ".join(patched) or "none")

            # Screen with tsc before spending a build on the batch.
            screened = typecheck_workspace(workspace, timeout=timeout)
            regressed = _regressed_files(report, screened, patched)
            if regressed:
                given_back = _restore_snapshot(workspace, snapshot, only=regressed)
                log.warning(
                    "    round %s: reverted %s regressed file(s), kept %s — %s",
                    round_number,
                    len(given_back),
                    len(patched) - len(given_back),
                    ", ".join(given_back),
                )
                rejections = [
                    *rejections,
                    *(f"{path}: your rewrite added type errors to this file" for path in given_back),
                ]
                screened = typecheck_workspace(workspace, timeout=timeout)
            if screened.available and screened.error_count > report.error_count:
                # Strictly worse even after the regressed files went back, so the
                # damage is in files the model was not asked about. Give the round
                # back rather than build a workspace that is worse than the one
                # already shipping.
                restored = _restore_snapshot(workspace, snapshot)
                log.warning(
                    "    round %s left more errors than it found (%s -> %s) "
                    "— rolled back %s file(s)",
                    round_number, report.error_count, screened.error_count, len(restored),
                )
                break

            _pre_build_fixups(ctx)
            ok, build_log = run_build(workspace, ctx.base_path, ctx.template_renderer)
            if not ok:
                restored = _restore_snapshot(workspace, snapshot)
                log.error(
                    "    typecheck repair broke the build despite a clean tsc screen "
                    "— rolled back %s file(s)",
                    len(restored),
                )
                _pre_build_fixups(ctx)
                ok, build_log = run_build(workspace, ctx.base_path, ctx.template_renderer)
                if ok:
                    ctx.build_log = build_log
                else:
                    log.error("    rebuild after rollback failed — restoring previous dist")
                break
            ctx.build_log = build_log
            previous_count = report.error_count
            report = screened
            _log_typecheck(report, f"after round {round_number}")
            if report.status != "errors":
                break
            if report.available and report.error_count >= previous_count:
                # The batch built, so it is kept — but a round that traded errors
                # laterally will keep doing that. Stop spending model calls.
                log.warning(
                    "    round %s made no net progress (%s errors) — stopping repair",
                    round_number, report.error_count,
                )
                break
        _restore_dist(workspace, dist_backup)
        if dist_backup is not None:
            shutil.rmtree(dist_backup.parent, ignore_errors=True)
    record_typecheck_report(workspace, report, rounds=rounds_run)
    return report


def run_build_phase(ctx: PipelineContext) -> None:
    db = ctx.db
    request_id = ctx.request_id
    workspace = ctx.workspace
    architect = ctx.architect
    template_renderer = ctx.template_renderer

    base_path = f"/api/preview-apps/{request_id}"
    ctx.base_path = base_path
    _emit(db, request_id, "build", "Compiling React app...", 86,
          detail="Running Vite build")
    log.info("  [6/6] Building + AI fix loop...")
    build_watch = WatchBmv("build+fix-loop", log).start()
    ok, build_log = run_build(workspace, base_path, template_renderer)
    if not ok:
        log.error(
            "initial vite build failed for request %s — see .bmv-debug/vite-build/",
            request_id,
        )
    attempt = 0
    fix_loop_start = time.monotonic()
    while not ok and attempt < ctx.max_fix_attempts:
        # Native/tooling failures can't be patched by the LLM — skip straight to fallbacks.
        infra_markers = (
            "Cannot find native binding",
            "@rolldown/binding-",
            "Vite requires Node.js version",
            "vite not installed after npm install",
        )
        if any(m in build_log for m in infra_markers):
            log.error("    build tooling/native error — skipping AI fix loop")
            break
        elapsed = time.monotonic() - fix_loop_start
        if elapsed > ctx.max_fix_seconds:
            log.warning(
                f"    fix loop budget exceeded ({elapsed:.0f}s > {ctx.max_fix_seconds}s) — "
                "stopping AI fix attempts, dropping to the guaranteed-safe fallback"
            )
            _emit(db, request_id, "build",
                  "Fix attempts taking too long — applying safe fallback instead...", 87)
            break
        attempt += 1
        _emit(db, request_id, "build",
              f"Fixing build errors (attempt {attempt}/{ctx.max_fix_attempts})...", 87,
              detail="AI is patching compilation errors")
        log.info("    fix attempt %s/%s...", attempt, ctx.max_fix_attempts)
        errors = extract_build_errors(build_log)
        log.debug("fix attempt %s extracted errors:\n%s", attempt, errors[:2000])
        try:
            fixed = fix_build_errors(workspace, errors, architect, ctx.ai_provider, template_renderer)
            log.debug("    patched: %s", ", ".join(fixed) or "none")
        except Exception as e:
            dump_exception(workspace, "fix-agent", f"attempt-{attempt}", e, context={"errors": errors[:1000]})
            log.error("    fix agent failed on attempt %s — retrying next attempt", attempt)
            # Don't break — the next attempt re-extracts errors and tries again
        _pre_build_fixups(ctx)
        ok, build_log = run_build(workspace, base_path, template_renderer)

    if not ok:
        # Prefer AI regeneration (up to 2 rounds) before any stub/template fallback.
        candidate_paths = [
            f.get("path", "") for f in ctx.files_to_gen
            if f.get("kind") == "page" or is_chrome_path(f.get("path", ""))
        ]
        for regen_round in range(1, 3):
            if ok:
                break
            errors = extract_build_errors(build_log)
            broken = find_broken_paths(errors, candidate_paths) or find_broken_paths(build_log, candidate_paths)
            broken = list(dict.fromkeys(broken + find_truncated_pages(workspace)))
            if not broken:
                break
            _emit(db, request_id, "build",
                  f"AI regenerating {len(broken)} broken page(s) (round {regen_round}/2)...", 88,
                  detail="Re-running codegen — prefer AI over stubs")
            log.info(f"    AI regen round {regen_round}/2: {', '.join(broken)}")
            regen_specs = [
                ctx.specs_by_path.get(path) or {"path": path, "kind": "page", "instructions": path}
                for path in broken
            ]

            def _regen_broken(spec: dict) -> str:
                _generate_spec(ctx, spec)
                return spec.get("path", "")

            if ctx.workers > 1 and len(regen_specs) > 1:
                for spec, _, exc in parallel_map(regen_specs, _regen_broken, max_workers=ctx.workers):
                    if exc:
                        log.error(f"    regen FAIL {spec.get('path')}: {exc}")
            else:
                for spec in regen_specs:
                    path = spec.get("path", "")
                    try:
                        _regen_broken(spec)
                    except Exception as e:
                        log.error(f"    regen FAIL {path}: {e}")
            _pre_build_fixups(ctx)
            ok, build_log = run_build(workspace, base_path, template_renderer)
            if ok:
                log.info(f"    AI regen round {regen_round} fixed the build")

    if not ok:
        # Last resort only — after AI fix + 2 AI regen rounds still fail.
        candidate_paths = [
            f.get("path", "") for f in ctx.files_to_gen
            if f.get("kind") == "page" or is_chrome_path(f.get("path", ""))
        ]
        for stub_round in range(1, 3):
            errors = extract_build_errors(build_log)
            broken = find_broken_paths(errors, candidate_paths) or find_broken_paths(build_log, candidate_paths)
            if not broken:
                broken = [p for p in find_truncated_pages(workspace) if p in candidate_paths]
            if not broken:
                break
            _emit(db, request_id, "build",
                  f"Stabilizing {len(broken)} page(s) (round {stub_round}/2)...", 88,
                  detail="Last-resort compile-safe content after AI retries")
            log.info(f"    stabilizing {len(broken)} page(s): {', '.join(broken)}")
            for path in broken:
                route = catalogue_route_for_file(path, architect)
                if is_chrome_path(path):
                    if not write_template_fallback(workspace, path):
                        write_safe_stub(
                            workspace, path, brand_name=ctx.brand_name, industry=ctx.industry,
                            route=route,
                        )
                else:
                    write_safe_stub(
                        workspace, path, brand_name=ctx.brand_name, industry=ctx.industry,
                        route=route,
                    )
            _pre_build_fixups(ctx)
            ok, build_log = run_build(workspace, base_path, template_renderer)
            if ok:
                log.info(f"    stabilized — build now succeeds")
                break

    if not ok:
        # Nuclear safety net: rewrite ALL route pages + chrome to known-good
        # content so the preview always ships something the owner can open.
        log.info("    nuclear stabilize — stubbing all routes + template chrome")
        _emit(db, request_id, "build", "Applying full safe fallback so the preview still opens...", 88)
        stabilize_all_route_pages(
            workspace, architect, brand_name=ctx.brand_name, industry=ctx.industry,
        )
        write_plumbing_mock(
            workspace,
            architect,
            ctx.images,
            ctx.brand_name,
            ctx.primary,
            ctx.secondary,
            design_system=ctx.design_system,
            mock_seed=(ctx.plan or {}).get("mock_seed")
            if isinstance((ctx.plan or {}).get("mock_seed"), dict)
            else None,
        )
        _pre_build_fixups(ctx)
        ok, build_log = run_build(workspace, base_path, template_renderer)
        if ok:
            log.info("    nuclear stabilize succeeded — preview will ship")

    if ok:
        _emit(db, request_id, "build_done", "Preview app compiled successfully!", 89,
              detail=f"{ctx.total_files} pages built and live")
    else:
        _emit(db, request_id, "build_failed", "Build failed — falling back to role pages", 89)

    # `vite build` succeeding proves nothing about prop contracts — it does not
    # typecheck. Do this before the visual critic so it reviews pages whose data
    # shapes are right, and never let it take the request down.
    if ok and settings.PREVIEW_TYPECHECK:
        try:
            _run_typecheck_repair(ctx)
        except Exception as e:
            log.error("    typecheck stage failed entirely, keeping existing build: %s", e)
        ok = (Path(workspace) / "dist" / "index.html").is_file()
    elif ok:
        log.warning("    typecheck skipped (PREVIEW_TYPECHECK=false)")


    # Post-build visual critique: only ever runs against a build that's
    # already succeeded (never a broken one), and is wrapped in its own
    # try/except on top of the guards already inside it — a failure here must
    # degrade to "keep whatever was already built", never take down the
    # whole request.
    if ok and not settings.PREVIEW_SKIP_VISUAL_CRITIC:
        log.info("  [7/7] Visual critique — screenshotting + reviewing rendered pages...")
        _emit(db, request_id, "visual_critic", "AI visually reviewing the built app...", 90,
              detail="Screenshotting pages and checking rendering quality")
        try:
            _run_visual_critique(
                db, request_id, workspace, architect, ctx.plan, ctx.specs_by_path, ctx.full_context,
                ctx.manifest, ctx.images, ctx.brand_name, ctx.primary, ctx.secondary, ctx.font, base_path,
                ctx.ai_provider, template_renderer,
            )
        except Exception as e:
            log.error(f"    visual critique stage failed entirely, keeping existing build: {e}")
    elif ok:
        log.warning("    visual critique skipped (PREVIEW_SKIP_VISUAL_CRITIC=true)")

    build_watch.stop()

    ctx.ok = ok
    ctx.build_log = build_log
    ctx.attempt = attempt
