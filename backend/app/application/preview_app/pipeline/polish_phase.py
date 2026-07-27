"""Preview pipeline — design critic, empty-seed guard, page-shell cleanup,
brand_name/font finalization, and the `_pre_build_fixups` deterministic guard
pass (also re-run by `build_phase` before every build attempt).
"""
from __future__ import annotations

from app.application.preview_app.brand_brief import resolve_preview_brand_name
from app.application.preview_app.codegen.critic import critique_and_refine
from app.application.preview_app.fallback import scan_and_repair_double_brace_literals
from app.application.preview_app.pipeline.codegen_phase import _regenerate_truncated, _run_batch
from app.application.preview_app.pipeline.context import PipelineContext
from app.application.preview_app.safety.orchestrator import apply_workspace_guards
from app.application.preview_app.safety.pages import cleanup_page_shells
from app.application.preview_app.safety.source_sanitize import (
    _empty_seed_state_vars,
    find_empty_seed_pages,
)
from app.application.preview_app.workspace import read_file
from app.application.services.progress import emit as _emit
from app.core.config import settings
from app.infrastructure.logging import get_logger

log = get_logger("PreviewPipeline")


def _pre_build_fixups(ctx: PipelineContext) -> None:
    """Deterministic guards re-applied before every single build attempt."""
    actions = apply_workspace_guards(
        ctx.workspace, ctx.architect, ctx.plan, ctx.images, ctx.brand_name, ctx.primary, ctx.secondary,
        ctx.font, ctx.template_renderer,
    )
    if actions:
        log.info(f"    guards: {', '.join(actions[:8])}{'...' if len(actions) > 8 else ''}")
    try:
        scrubbed = scan_and_repair_double_brace_literals(
            ctx.workspace,
            architect=ctx.architect,
        )
        if scrubbed:
            log.info(
                f"    double-brace scrub: {', '.join(scrubbed[:8])}"
                f"{'...' if len(scrubbed) > 8 else ''}"
            )
    except ValueError as e:
        # Fail early with a clear error instead of opaque Vite transform noise.
        log.error(f"    double-brace scan FAILED: {e}")
        raise


def run_polish_phase(ctx: PipelineContext) -> None:
    db = ctx.db
    request_id = ctx.request_id
    workspace = ctx.workspace

    if settings.PREVIEW_SKIP_CRITIC:
        log.warning("  [5/6] Design critic skipped (PREVIEW_SKIP_CRITIC=true)")
    else:
        _emit(db, request_id, "critic",
              f"AI design critic reviewing {ctx.page_ok} pages...", 80,
              detail="Checking quality, consistency, and UX")
        log.info("  [5/6] Design critic — reviewing + refining pages...")
        design_direction = ctx.architect.get("design_direction", "")

        def _critic_heartbeat(i: int, total: int, path: str) -> None:
            short = path.replace("src/pages/", "").replace("src/", "")
            pct = 80 + int((i / max(total, 1)) * 4)
            _emit(db, request_id, "critic",
                  f"Reviewing page {i}/{total}: {short}", pct,
                  detail="Checking quality, consistency, and UX")

        try:
            refined = critique_and_refine(
                workspace, ctx.files_to_gen, ctx.full_context, design_direction, ctx.manifest, ctx.images,
                ctx.ai_provider, ctx.template_renderer, on_progress=_critic_heartbeat,
                architect=ctx.architect,
            )
            log.info(f"    refined {len(refined)} page(s)")
            _emit(db, request_id, "critic",
                  f"Critic refined {len(refined)} page(s)", 84,
                  detail="Applying design improvements")
            regen_critic = _regenerate_truncated(ctx, "post-critic")
            if regen_critic:
                log.info(f"    critic pass left {len(regen_critic)} truncated — re-generated")
        except Exception as e:
            log.warning(f"    critic pass skipped: {e}")

    # Content-realism guard: a page can compile cleanly with an empty
    # `useState([])` that's never seeded (see find_empty_seed_pages) — not a
    # build error, so the fix-loop never touches it, and the critic can
    # approve/refine a page's copy without ever noticing its list renders
    # empty. Runs regardless of PREVIEW_SKIP_CRITIC since the underlying gap
    # is independent of whether the critic pass ran at all.
    try:
        empty_seed = find_empty_seed_pages(workspace)
    except Exception as e:
        empty_seed = []
        log.warning(f"    empty-seed guard skipped: {e}")
    if empty_seed:
        log.warning(
            f"    empty-seed guard: {len(empty_seed)} page(s) render with no seed data: "
            f"{', '.join(empty_seed)}"
        )
        reinforced_specs = []
        for rel in empty_seed:
            base_spec = ctx.specs_by_path.get(rel) or {"path": rel, "kind": "page", "instructions": rel}
            spec = dict(base_spec)
            state_vars = _empty_seed_state_vars(read_file(workspace, rel))
            var_ref = f"`{state_vars[0]}`" if state_vars else "its list state"
            reinforcement = (
                f"Your previous version initialized {var_ref} as an empty array with no seed "
                "data. This page must render pre-populated with 3-6 realistic example items for "
                "this business — either import them from mock data or define them inline. Do not "
                "ship an empty list."
            )
            spec["instructions"] = f"{spec.get('instructions', '')}\n\n{reinforcement}".strip()
            reinforced_specs.append(spec)
        try:
            _run_batch(ctx, "empty-seed-fix", reinforced_specs, parallel=True)
            still_empty = find_empty_seed_pages(workspace)
            if still_empty:
                log.warning(
                    f"    empty-seed guard: {len(still_empty)} page(s) still empty after regen: "
                    f"{', '.join(still_empty)}"
                )
        except Exception as e:
            log.error(f"    empty-seed regen failed: {e}")

    stripped = cleanup_page_shells(workspace)
    if stripped:
        log.info(f"    removed duplicate nav from: {', '.join(stripped)}")

    brief_for_name = (
        ctx.brand_brief
        if isinstance(ctx.brand_brief, dict) and ctx.brand_brief
        else (ctx.design_brief if isinstance(ctx.design_brief, dict) else None)
    )
    # Brand→real rematerialize runs in plan_phase before plumbing; polish only
    # keeps ctx.brand_name in sync (same upgrade sources already applied).
    ctx.brand_name = resolve_preview_brand_name(
        brand_name=ctx.brand_name,
        brand_brief=brief_for_name,
        business_name=getattr(ctx.req, "business_name", None),
        concept_name=getattr(ctx.req, "concept_name", None),
        manifest=ctx.manifest if isinstance(ctx.manifest, dict) else None,
        demo=ctx.demo if isinstance(ctx.demo, dict) else None,
        plan=ctx.plan if isinstance(ctx.plan, dict) else None,
        fallback=True,
    ) or "Brand"
    ctx.font = ctx.design_system.get("font_family") or ctx.design_system.get("font") or ctx.manifest.get("font", "")

    _pre_build_fixups(ctx)
    log.info("    assembled router + theme")
