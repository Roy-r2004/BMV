"""Preview pipeline — Vite build + AI fix loop + regen/stabilize/nuclear +
visual critique.
"""
from __future__ import annotations

import time

from app.application.preview_app.assemble import write_plumbing_mock
from app.application.preview_app.build import extract_build_errors, run_build
from app.application.preview_app.catalogue_contract import catalogue_route_for_file
from app.application.preview_app.codegen.fix_agent import fix_build_errors
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
from app.application.services.progress import emit as _emit
from app.core.config import settings
from app.infrastructure.logging import WatchBmv, get_logger
from app.infrastructure.logging.diagnostics import dump_exception

log = get_logger("PreviewPipeline")


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
