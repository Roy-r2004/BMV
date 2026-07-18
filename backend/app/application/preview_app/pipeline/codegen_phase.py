"""Preview pipeline — codegen parallel batches, truncated regen, missing routes,
mock synthesize (through codegen_watch.stop()).

`_generate_spec`, `_run_batch`, and `_regenerate_truncated` are exposed as
module-level, ctx-driven functions (rather than nested closures) because
`build_phase` also needs them for its own AI-regen rounds.
"""
from __future__ import annotations

from app.application.preview_app.assemble import find_missing_route_pages, find_unresolved_routes, write_app_tsx
from app.application.preview_app.codegen.generate import generate_file
from app.application.preview_app.codegen.mock import synthesize_mock_data
from app.application.preview_app.fallback import stabilize_all_route_pages, write_safe_stub
from app.application.preview_app.parallel import parallel_map, split_codegen_phases
from app.application.preview_app.pipeline.context import PipelineContext
from app.application.preview_app.safety.source_sanitize import find_truncated_pages, looks_truncated_source
from app.application.preview_app.workspace import read_file
from app.application.services.progress import emit as _emit
from app.core.config import settings
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.logging import WatchBmv, get_logger

log = get_logger("PreviewPipeline")


def _emit_codegen_progress(ctx: PipelineContext, path: str, done: int, *, started: bool = False) -> None:
    short_path = path.replace("src/pages/", "").replace("src/components/", "").replace("src/", "")
    pct = 42 + int((done / max(ctx.total_files, 1)) * 36)
    label = f"{'Starting' if started else 'Generated'}: {short_path}"
    # Never hold progress_lock across SQLite I/O — that deadlocked the pool
    # when the pipeline session also touched the same DB.
    thread_db = SessionLocal()
    try:
        _emit(thread_db, ctx.request_id, "codegen",
              label, pct,
              detail=path,
              files_done=done,
              files_total=ctx.total_files)
    finally:
        thread_db.close()


def _release_pipeline_db(ctx: PipelineContext) -> None:
    """Drop any open SQLite transaction on the request session before workers run."""
    try:
        ctx.db.commit()
    except Exception:
        try:
            ctx.db.rollback()
        except Exception:
            pass
    try:
        ctx.db.expire_all()
    except Exception:
        pass


def _generate_spec(ctx: PipelineContext, spec: dict) -> str:
    path = spec.get("path", "?")
    log.debug(f"    >> begin {path}")
    _emit_codegen_progress(ctx, path, ctx.files_completed, started=True)
    try:
        generate_file(
            ctx.workspace, spec, ctx.full_context, ctx.architect, ctx.plan, ctx.manifest, ctx.images,
            ctx.ai_provider, ctx.template_renderer,
        )
        log.debug(f"    << done {path}")
        return path
    except Exception as exc:
        log.error(f"    << fail {path}: {exc}")
        raise


def _run_batch(ctx: PipelineContext, label: str, batch: list[dict], *, parallel: bool) -> tuple[int, int]:
    if not batch:
        return 0, 0
    ok_count = 0
    page_count = 0
    workers = ctx.workers
    if parallel and workers > 1 and len(batch) > 1:
        log.debug(f"    {label}: {len(batch)} files in parallel (workers={workers})")
        _release_pipeline_db(ctx)
        batch_failed: list[dict] = []

        def _on_file_done(done: int, _total: int, spec: dict, result, exc) -> None:
            nonlocal ok_count, page_count
            path = spec.get("path", "?")
            with ctx.progress_lock:
                ctx.files_completed += 1
                done_now = ctx.files_completed
            _emit_codegen_progress(ctx, path, done_now)
            if exc:
                log.error(f"    FAIL {path}: {exc}")
                batch_failed.append(spec)
            else:
                ctx.generated_ok += 1
                ok_count += 1
                if spec.get("kind") == "page":
                    ctx.page_ok += 1
                    page_count += 1
                # Queue weak outputs for an immediate AI retry.
                body = read_file(ctx.workspace, path) if path and path != "?" else ""
                if looks_truncated_source(body) or (
                    spec.get("kind") == "page" and body and "export default" not in body
                ):
                    log.warning(f"    WEAK {path} — queued for AI retry")
                    batch_failed.append(spec)
                else:
                    log.debug(f"    OK {path}")

        parallel_map(batch, lambda spec: _generate_spec(ctx, spec), max_workers=workers, on_done=_on_file_done)
        if batch_failed:
            # Dedupe by path
            seen: set[str] = set()
            retry_specs: list[dict] = []
            for spec in batch_failed:
                p = spec.get("path", "")
                if p and p not in seen:
                    seen.add(p)
                    retry_specs.append(spec)
            log.error(f"    {label}: AI-retrying {len(retry_specs)} weak/failed file(s)...")
            for spec in retry_specs:
                path = spec.get("path", "?")
                try:
                    generate_file(
                        ctx.workspace, spec, ctx.full_context, ctx.architect, ctx.plan, ctx.manifest, ctx.images,
                        ctx.ai_provider, ctx.template_renderer,
                    )
                    # Count only if this path wasn't already counted as OK.
                    body = read_file(ctx.workspace, path)
                    if body and not looks_truncated_source(body):
                        if spec.get("kind") == "page" and "export default" in body:
                            log.debug(f"    OK retry {path}")
                        elif spec.get("kind") != "page":
                            log.debug(f"    OK retry {path}")
                        else:
                            log.warning(f"    retry still weak {path}")
                    else:
                        log.warning(f"    retry still weak {path}")
                except Exception as e:
                    log.error(f"    FAIL retry {path}: {e}")
    else:
        for spec in batch:
            path = spec.get("path", "?")
            with ctx.progress_lock:
                ctx.files_completed += 1
                done_now = ctx.files_completed
            _emit_codegen_progress(ctx, path, done_now)
            log.debug(f"    -> [{done_now}/{ctx.total_files}] {path}")
            try:
                generate_file(
                    ctx.workspace, spec, ctx.full_context, ctx.architect, ctx.plan, ctx.manifest, ctx.images,
                    ctx.ai_provider, ctx.template_renderer,
                )
                ctx.generated_ok += 1
                ok_count += 1
                if spec.get("kind") == "page":
                    ctx.page_ok += 1
                    page_count += 1
                log.debug(f"    OK {path}")
            except Exception as e:
                log.error(f"    FAIL {path}: {e}")
    return ok_count, page_count


def _regenerate_truncated(ctx: PipelineContext, label: str) -> list[str]:
    truncated = find_truncated_pages(ctx.workspace)
    if not truncated:
        return []
    specs = [
        ctx.specs_by_path.get(rel) or {"path": rel, "kind": "page", "instructions": rel}
        for rel in truncated
    ]
    log.debug(f"    {label}: regenerating {len(specs)} truncated file(s)")

    def _regen_spec(spec: dict) -> str:
        path = spec.get("path", "")
        log.debug(f"    {label} regenerating truncated: {path}")
        _generate_spec(ctx, spec)
        return path

    regen: list[str] = []
    if ctx.workers > 1 and len(specs) > 1:
        for spec, result, exc in parallel_map(specs, _regen_spec, max_workers=ctx.workers):
            path = spec.get("path", "")
            if exc:
                log.error(f"    {label} FAIL {path}: {exc}")
            else:
                regen.append(path)
    else:
        for spec in specs:
            path = spec.get("path", "")
            try:
                _regen_spec(spec)
                regen.append(path)
            except Exception as e:
                log.error(f"    {label} FAIL {path}: {e}")
    return regen


def run_codegen_phase(ctx: PipelineContext) -> None:
    db = ctx.db
    request_id = ctx.request_id
    workspace = ctx.workspace
    architect = ctx.architect
    files_to_gen = ctx.files_to_gen

    ctx.total_files = len(files_to_gen)
    ctx.workers = settings.PREVIEW_PARALLEL_WORKERS
    ctx.max_fix_attempts = settings.PREVIEW_MAX_BUILD_FIX_ATTEMPTS
    ctx.max_fix_seconds = settings.PREVIEW_MAX_FIX_LOOP_SECONDS
    log.info(
        f"  [4/6] Codegen agent — {ctx.total_files} files "
        f"(cap={settings.PREVIEW_MAX_FILES}, workers={ctx.workers})..."
    )
    codegen_watch = WatchBmv("codegen", log).start()
    _emit(
        db,
        request_id,
        "codegen",
        f"Generating {ctx.total_files} files (workers={ctx.workers})...",
        42,
        detail="Starting code generation",
        files_done=0,
        files_total=ctx.total_files,
    )
    ctx.generated_ok = 0
    ctx.page_ok = 0
    ctx.files_completed = 0

    foundation, components, pages = split_codegen_phases(files_to_gen)
    # Parallelize every codegen phase — OpenRouter calls are network-bound.
    _run_batch(ctx, "foundation", foundation, parallel=True)
    _run_batch(ctx, "components", components, parallel=True)
    _run_batch(ctx, "pages", pages, parallel=True)

    regen = _regenerate_truncated(ctx, "post-codegen")
    if regen:
        log.debug(f"    re-generated {len(regen)} truncated file(s)")

    missing_specs = find_missing_route_pages(workspace, architect)
    if missing_specs:
        log.debug(f"    generating {len(missing_specs)} missing route page(s)...")
        _run_batch(ctx, "missing-routes", missing_specs, parallel=True)

    unresolved = find_unresolved_routes(workspace, architect)
    if unresolved:
        log.debug(f"    {len(unresolved)} route(s) still unresolved — AI regen then stub+wire")
        _emit(db, request_id, "codegen", f"Filling {len(unresolved)} missing routes...", 72)
        for rt in unresolved:
            cf = (rt.get("component_file") or "").replace("\\", "/")
            if not cf:
                continue
            spec = ctx.specs_by_path.get(cf) or {
                "path": cf,
                "kind": "page",
                "instructions": (
                    f"{rt.get('title', '')} — {rt.get('purpose', '')}. "
                    f"Role: {rt.get('role_id', '')}."
                ),
            }
            try:
                generate_file(
                    workspace, spec, ctx.full_context, architect, ctx.plan, ctx.manifest, ctx.images,
                    ctx.ai_provider, ctx.template_renderer,
                )
            except Exception as e:
                log.error(f"    unresolved regen FAIL {cf}: {e}")
            if not read_file(workspace, cf).strip():
                write_safe_stub(
                    workspace, cf,
                    brand_name=ctx.brand_name,
                    industry=ctx.industry,
                    page_title=rt.get("title"),
                    route=rt,
                )
                log.debug(f"    stubbed unresolved route page: {cf}")
        still = find_unresolved_routes(workspace, architect)
        if still:
            log.warning(f"    WARN {len(still)} route(s) still unresolved after fill")
        write_app_tsx(workspace, architect, ctx.template_renderer)

    if ctx.generated_ok == 0 or ctx.page_ok == 0:
        # Prefer another full AI pass over stubs — fallbacks are last resort only.
        page_specs = [f for f in files_to_gen if f.get("kind") == "page"]
        log.warning(
            f"    codegen produced few usable files (ok={ctx.generated_ok}, pages={ctx.page_ok}) "
            f"— AI-retrying {len(page_specs)} page(s) before any fallback"
        )
        _emit(db, request_id, "codegen", f"Retrying {len(page_specs)} pages with AI...", 70)
        for spec in page_specs:
            path = spec.get("path", "?")
            try:
                generate_file(
                    workspace, spec, ctx.full_context, architect, ctx.plan, ctx.manifest, ctx.images,
                    ctx.ai_provider, ctx.template_renderer,
                )
                body = read_file(workspace, path)
                if body and not looks_truncated_source(body) and "export default" in body:
                    ctx.generated_ok += 1
                    ctx.page_ok += 1
                    log.debug(f"    OK recovery {path}")
            except Exception as e:
                log.error(f"    FAIL recovery {path}: {e}")
        if ctx.page_ok == 0:
            log.info("    AI recovery still empty — seeding compile-safe pages as last resort")
            seeded = stabilize_all_route_pages(
                workspace, architect, brand_name=ctx.brand_name, industry=ctx.industry,
            )
            log.info(f"    seeded {len(seeded)} fallback page(s)")
            ctx.generated_ok = max(ctx.generated_ok, len(seeded))
            ctx.page_ok = max(ctx.page_ok, len(seeded))

    if synthesize_mock_data(
        workspace, ctx.full_context, ctx.plan, ctx.manifest, ctx.images, architect,
        ctx.ai_provider, ctx.template_renderer,
    ):
        log.info("    mock.ts synthesized from page imports")

    codegen_watch.stop()
