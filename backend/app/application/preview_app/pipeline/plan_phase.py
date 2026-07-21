"""Preview pipeline — planning + architect + workspace prep + file cap ([1/5]-[3/5])."""
from __future__ import annotations

from app.application.appspec.projection import (
    merge_architecture_enrichment,
    to_architecture_seed,
    to_experience_plan_seed,
)
from app.application.preview_app.assemble import write_plumbing_mock
from app.application.preview_app.codegen.architect import call_architect
from app.application.preview_app.fallback import clear_stubbed_paths
from app.application.preview_app.pipeline.architect_normalize import (
    _normalize_architect,
    _prioritize_for_file_cap,
    _sort_gen_order,
)
from app.application.preview_app.pipeline.context import PipelineContext
from app.application.preview_app.protected_paths import is_template_owned_path
from app.application.preview_app.workspace import prepare_workspace
from app.application.services.page_experience import (
    build_design_manifest,
    build_experience_plan,
    gather_full_context,
)
from app.application.services.progress import emit as _emit
from app.core.config import settings
from app.infrastructure.logging import WatchBmv, get_logger

log = get_logger("PreviewPipeline")


def run_plan_phase(ctx: PipelineContext) -> None:
    db = ctx.db
    request_id = ctx.request_id
    req = ctx.req
    ai_provider = ctx.ai_provider
    template_renderer = ctx.template_renderer
    demo = ctx.demo
    brand_brief = ctx.brand_brief
    primary = ctx.primary
    secondary = ctx.secondary
    images = ctx.images

    from app.application.preview_app.brand_brief import apply_brief_to_plan

    log.info("  [1/5] Planning agent...")
    plan_watch = WatchBmv("planning", log).start()
    _emit(db, request_id, "codegen", "Planning agent — mapping roles and user journeys...", 30)
    full_context = gather_full_context(req, demo)
    canonical_plan_seed = (
        to_experience_plan_seed(ctx.app_spec_result.spec, ctx.app_spec_scope)
        if ctx.enforce_app_spec and ctx.app_spec_result and ctx.app_spec_scope
        else None
    )
    plan = build_experience_plan(
        req,
        demo,
        primary,
        secondary,
        ai_provider,
        template_renderer,
        canonical_seed=canonical_plan_seed,
    )
    from app.application.preview_app.design_recipes import (
        apply_recipe_to_architect,
        apply_recipe_to_plan,
        get_recipe,
    )

    if brand_brief:
        plan = apply_brief_to_plan(plan, brand_brief)
    from app.application.preview_app.industry_templates.apply import (
        apply_industry_template_to_plan,
        apply_ops_industry_template_to_plan,
        template_recipe_hint,
    )

    industry_context = " ".join(
        part
        for part in (
            getattr(req, "business_description", None) or "",
            getattr(req, "main_problem", None) or "",
            getattr(req, "desired_outcome", None) or "",
            getattr(req, "target_customers", None) or "",
            getattr(req, "business_name", None) or "",
            full_context[:800],
        )
        if str(part).strip()
    )
    template_recipe = None
    if not (brand_brief or {}).get("recipe_id"):
        template_recipe = template_recipe_hint(
            industry=req.industry,
            seed=request_id,
            surface="public",
            context=industry_context,
        )
    plan = apply_recipe_to_plan(
        plan,
        industry=req.industry,
        business_description=getattr(req, "description", None)
        or getattr(req, "business_description", None)
        or full_context[:800],
        concept_name=req.business_name,
        seed=request_id,
        recipe_id=(brand_brief or {}).get("recipe_id") or template_recipe,
    )
    plan = apply_industry_template_to_plan(
        plan,
        industry=req.industry,
        seed=request_id,
        surface="public",
        context=industry_context,
    )
    # Ops packs were unreachable when surface was hardcoded to public only.
    plan = apply_ops_industry_template_to_plan(
        plan,
        industry=req.industry,
        seed=request_id,
        context=industry_context,
    )
    from app.application.preview_app.internal_desk import (
        ensure_internal_desk_architect,
        ensure_internal_desk_experience_plan,
    )

    plan = ensure_internal_desk_experience_plan(
        plan,
        context=industry_context,
    )
    imagery_roles = plan.get("imagery_roles") if isinstance(plan.get("imagery_roles"), dict) else None
    if imagery_roles:
        from app.application.services.industry_images import get_images_for_industry

        images = get_images_for_industry(
            req.industry or "",
            seed=request_id,
            business_name=req.business_name,
            imagery_roles=imagery_roles,
        )
        ctx.images = images
    recipe = get_recipe(plan.get("recipe_id"))
    log.info(
        f"    design recipe: {recipe.get('id')} ({recipe.get('label')}) "
        f"hub={plan.get('hub_variant')} "
        f"template={plan.get('industry_template_id') or '-'} "
        f"ops={plan.get('ops_template_id') or '-'} "
        f"brand_locked={bool((plan.get('design_system') or {}).get('brand_locked'))}"
    )
    manifest = build_design_manifest(full_context, plan, ai_provider, template_renderer)
    design_system = plan.get("design_system") or manifest.get("design_system") or {}
    if brand_brief:
        design_system = (
            apply_brief_to_plan({"design_system": design_system}, brand_brief).get(
                "design_system"
            )
            or design_system
        )
        plan["design_system"] = design_system
        manifest["design_system"] = design_system
        manifest["accent"] = design_system.get("primary_color") or primary
    roles_count = len(plan.get("roles", []))
    _emit(db, request_id, "codegen",
          f"Plan ready — {roles_count} role{'s' if roles_count != 1 else ''} · recipe {recipe.get('id')}", 33,
          detail="Architect designing component structure")
    plan_watch.stop()

    log.info("  [2/5] Architect agent...")
    architect_watch = WatchBmv("architect", log).start()
    _emit(db, request_id, "codegen", "Architect agent — designing pages and components...", 35)
    try:
        architect = call_architect(
            full_context,
            plan,
            manifest,
            images,
            ai_provider,
            template_renderer,
        )
    except Exception:
        if not (ctx.enforce_app_spec and ctx.app_spec_result and ctx.app_spec_scope):
            raise
        architect = {}
    if ctx.enforce_app_spec and ctx.app_spec_result and ctx.app_spec_scope:
        architect = merge_architecture_enrichment(
            to_architecture_seed(ctx.app_spec_result.spec, ctx.app_spec_scope),
            architect,
        )
    architect = ensure_internal_desk_architect(
        architect,
        context=industry_context,
    )
    try:
        architect = _normalize_architect(architect, plan)
    except Exception:
        raise
    architect = apply_recipe_to_architect(architect, plan)
    planned_files = len(architect.get("files_to_generate", []))
    _emit(db, request_id, "codegen",
          f"Architecture ready — {planned_files} files planned", 38,
          detail="Starting code generation")
    architect_watch.stop()

    log.info("  [3/5] Preparing workspace...")
    workspace_watch = WatchBmv("workspace-prep", log).start()
    _emit(db, request_id, "codegen", "Setting up build workspace...", 40)
    workspace = prepare_workspace(request_id)
    _emit(db, request_id, "codegen", "Build workspace ready", 41,
          detail=str(workspace))
    brand_name = (
        (manifest.get("brand") or {}).get("name")
        if isinstance(manifest.get("brand"), dict)
        else None
    ) or manifest.get("brand_name") or req.business_name or "Brand"
    if isinstance(plan.get("mock_seed"), dict):
        architect["mock_seed"] = plan["mock_seed"]
    from app.application.preview_app.ai_feature_surfaces import (
        ensure_ai_feature_route,
        ensure_ai_feature_surfaces,
    )
    from app.application.services.ai_features import (
        ai_features_from_request,
        business_context_from_request,
    )

    # Route must exist before mock nav is written so the hub is linked.
    ensure_ai_feature_route(
        architect,
        ai_features_from_request(req),
        context=business_context_from_request(req),
    )
    write_plumbing_mock(
        workspace,
        architect,
        images,
        brand_name,
        primary,
        secondary,
        design_system=design_system,
        mock_seed=plan.get("mock_seed") if isinstance(plan.get("mock_seed"), dict) else None,
    )
    ensure_ai_feature_surfaces(
        workspace,
        architect,
        req,
        brand_name=brand_name,
    )
    log.info("    plumbing mock (brand, roles, nav) ready")
    workspace_watch.stop()

    # Router/theme/data and the catalogue kit are template/assembler-owned.
    _skip = {"src/app.tsx", "src/index.css", "src/data/mock.ts"}
    all_files = [
        f for f in architect.get("files_to_generate", [])
        if (f.get("path") or "").lower().replace("\\", "/") not in _skip
        and not is_template_owned_path(f.get("path", ""), architect)
    ]
    prioritized = _prioritize_for_file_cap(all_files)
    capped = prioritized[: settings.PREVIEW_MAX_FILES]
    skipped_files = prioritized[settings.PREVIEW_MAX_FILES :]
    if skipped_files:
        skip_paths = [f.get("path", "?") for f in skipped_files]
        log.warning(
            f"    file cap: skipping {len(skipped_files)} non-priority file(s): "
            f"{', '.join(skip_paths[:8])}{'…' if len(skip_paths) > 8 else ''}"
        )
        _emit(
            db, request_id, "codegen",
            f"Capped to {len(capped)} files — prioritizing pages",
            41,
            detail=f"Skipped {len(skipped_files)}: {', '.join(skip_paths[:5])}",
        )
    files_to_gen = _sort_gen_order(capped)
    clear_stubbed_paths(workspace)
    industry = req.industry or ""

    ctx.full_context = full_context
    ctx.plan = plan
    ctx.manifest = manifest
    ctx.design_system = design_system
    ctx.architect = architect
    ctx.workspace = workspace
    ctx.brand_name = brand_name
    ctx.industry = industry
    ctx.files_to_gen = files_to_gen
    ctx.specs_by_path = {f.get("path", ""): f for f in files_to_gen}
