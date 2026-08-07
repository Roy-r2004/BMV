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

    from app.application.preview_app.brand_brief import (
        apply_brief_to_plan,
        resolve_preview_brand_name,
    )

    log.info("  [1/5] Planning agent...")
    plan_watch = WatchBmv("planning", log).start()
    _emit(db, request_id, "codegen", "Planning agent — mapping roles and user journeys...", 30)
    full_context = gather_full_context(req, demo)
    # One brand clock for packs + plumbing — resolve early; upgrade after manifest only.
    brand_name = resolve_preview_brand_name(
        brand_brief=brand_brief if isinstance(brand_brief, dict) else None,
        business_name=getattr(req, "business_name", None),
        concept_name=getattr(req, "concept_name", None),
        demo=demo if isinstance(demo, dict) else None,
        fallback=False,
    )
    industry_context = " ".join(
        part
        for part in (
            ctx.industry,
            getattr(req, "business_description", None) or "",
            getattr(req, "main_problem", None) or "",
            getattr(req, "desired_outcome", None) or "",
            getattr(req, "target_customers", None) or "",
            getattr(req, "business_name", None) or "",
            full_context[:800],
        )
        if str(part).strip()
    )
    from app.application.preview_app.product_kind import (
        OPS_KINDS,
        PUBLIC_KINDS,
        apply_product_kind_to_architect,
        apply_product_kind_to_plan,
        lock_chrome_on_architecture_seed,
        lock_chrome_on_experience_seed,
        resolve_product_kind_contract,
    )

    kind_contract = resolve_product_kind_contract(industry_context)
    canonical_plan_seed = (
        to_experience_plan_seed(ctx.app_spec_result.spec, ctx.app_spec_scope)
        if ctx.enforce_app_spec and ctx.app_spec_result and ctx.app_spec_scope
        else None
    )
    if canonical_plan_seed is not None:
        canonical_plan_seed = lock_chrome_on_experience_seed(
            canonical_plan_seed, kind_contract
        )
    plan = build_experience_plan(
        req,
        demo,
        primary,
        secondary,
        ai_provider,
        template_renderer,
        canonical_seed=canonical_plan_seed,
        fallback_contract=kind_contract,
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

    # Product kind first — locks chrome before recipes/packs can stamp marketing.
    plan = apply_product_kind_to_plan(plan, kind_contract)
    log.info(
        "    product_kind=%s subtype=%s pages=%s",
        kind_contract.kind,
        kind_contract.subtype,
        len(kind_contract.pages),
    )

    pack_surface = kind_contract.template_surface
    # Brand brief may lock an ops hub recipe (false keyword hits). Public product
    # kinds must keep marketing chrome — never seal dense-ops-ledger onto a gallery.
    brief_recipe = (brand_brief or {}).get("recipe_id")
    if brief_recipe and kind_contract.kind in PUBLIC_KINDS:
        if str(get_recipe(str(brief_recipe)).get("hub_variant") or "") == "app":
            brief_recipe = None
    template_recipe = None
    if not brief_recipe:
        template_recipe = template_recipe_hint(
            industry=ctx.industry,
            seed=request_id,
            surface=pack_surface,
            context=industry_context,
        ) or kind_contract.recipe_id
    plan = apply_recipe_to_plan(
        plan,
        industry=ctx.industry,
        business_description=getattr(req, "description", None)
        or getattr(req, "business_description", None)
        or full_context[:800],
        concept_name=req.business_name,
        seed=request_id,
        recipe_id=brief_recipe or template_recipe or kind_contract.recipe_id,
    )
    # Workspace/desk kinds: ops pack owns voice+seed. Never stamp public-home packs onto /.
    if kind_contract.kind in OPS_KINDS:
        plan = apply_ops_industry_template_to_plan(
            plan,
            industry=ctx.industry,
            seed=request_id,
            context=industry_context,
            brand_name=brand_name,
        )
        # Prefer ops mock_seed as the primary seed (not marketing hero copy).
        if plan.get("ops_template_id"):
            plan["industry_template_id"] = plan.get("ops_template_id")
            plan["industry_template_label"] = plan.get("ops_template_label")
        plan["recipe_id"] = kind_contract.recipe_id
    else:
        plan = apply_industry_template_to_plan(
            plan,
            industry=ctx.industry,
            seed=request_id,
            surface="public",
            context=industry_context,
            brand_name=brand_name,
        )
        plan = apply_ops_industry_template_to_plan(
            plan,
            industry=ctx.industry,
            seed=request_id,
            context=industry_context,
            brand_name=brand_name,
        )
    # Product Face Contract: normalize intents + materialize mock_seed after packs
    # (packs are gap-fill only; contract fields already win inside apply_*).
    from app.application.preview_app.product_face import ensure_product_face_on_plan

    plan = ensure_product_face_on_plan(
        plan, brand_name=brand_name, fill_defaults=True
    )
    # Re-apply kind lock after packs so marketing voice cannot rewrite chrome.
    plan = apply_product_kind_to_plan(plan, kind_contract)
    plan = ensure_product_face_on_plan(
        plan, brand_name=brand_name, fill_defaults=True
    )
    # Legacy forcers kept as validators / last-resort repair for niche keywords.
    from app.application.preview_app.internal_desk import (
        ensure_internal_desk_architect,
        ensure_internal_desk_experience_plan,
    )
    from app.application.preview_app.saas_accounting import (
        ensure_saas_accounting_architect,
        ensure_saas_accounting_experience_plan,
    )

    plan = ensure_internal_desk_experience_plan(
        plan,
        context=industry_context,
    )
    plan = ensure_saas_accounting_experience_plan(
        plan,
        context=industry_context,
    )
    imagery_roles = plan.get("imagery_roles") if isinstance(plan.get("imagery_roles"), dict) else None
    if imagery_roles:
        from app.application.services.industry_images import (
            get_images_for_industry,
            resolve_industry_category,
        )

        # Roles are framing only — subject stays the business industry/brand, so the
        # business-derived set from the appspec gate is refined, never replaced.
        framed = get_images_for_industry(
            ctx.industry,
            seed=request_id,
            business_name=req.business_name,
            imagery_roles=imagery_roles,
        )
        images = {**(images or {}), **framed}
        ctx.images = images
        log.info(
            "    imagery subject=%s roles=%s",
            resolve_industry_category(ctx.industry),
            ",".join(sorted(imagery_roles)),
        )
    recipe = get_recipe(plan.get("recipe_id"))
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
    # Per-request visual face after recipe + brand lock (fonts respect brand_locked).
    from app.application.preview_app.design_overlay import apply_design_overlay_to_plan

    plan = apply_design_overlay_to_plan(
        plan,
        seed=request_id,
        context=industry_context or full_context[:800],
        industry=ctx.industry,
        business_name=req.business_name or "",
    )
    # Collapse recipe/pack/brand/overlay/kind pile-ons into one sealed brief.
    from app.application.preview_app.design_brief import (
        apply_sealed_brief_to_architect,
        apply_sealed_brief_to_plan,
        seal_design_brief,
    )

    design_brief = seal_design_brief(plan, brand_brief=brand_brief)
    plan = apply_sealed_brief_to_plan(plan, design_brief)
    design_system = plan.get("design_system") or design_system
    manifest["design_system"] = design_system
    manifest["design_brief"] = design_brief
    log.info(
        f"    design recipe: {recipe.get('id')} ({recipe.get('label')}) "
        f"overlay={design_system.get('design_overlay_id') or '-'} "
        f"hub={plan.get('hub_variant')} "
        f"template={plan.get('industry_template_id') or '-'} "
        f"ops={plan.get('ops_template_id') or '-'} "
        f"brand_locked={bool(design_system.get('brand_locked'))} "
        f"brief_sealed={bool(design_brief.get('sealed'))}"
    )
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
    except Exception as exc:
        if ctx.enforce_app_spec and ctx.app_spec_result and ctx.app_spec_scope:
            # Enforced mode rescues from the AppSpec projection below. Unchanged.
            architect = {}
        else:
            # 1.12. `architect` is MANDATORY, and a mandatory stage's contract is
            # that it *takes its deterministic path*. Outside the AppSpec branch
            # it had none, so this `raise` was the whole of requests 74, 92 and
            # 94: five runs have shipped NULL rather than a degraded preview,
            # which is the opposite of the designed outcome.
            #
            # The deterministic builder already exists — `{}` is not substantive,
            # so `apply_product_kind_to_architect` eleven lines down injects the
            # kind's whole blueprint (3 routes for a storefront, 6 for accounting)
            # and `_normalize_architect` accepts the result for every kind. Past
            # the deadline codegen is refused too, so what ships is blueprint
            # routes with deterministic scaffolds. That is a degraded preview,
            # and it is worth more than nothing at all.
            from app.application.services.request_deadline import record_degradation

            record_degradation("architect", "call_failed_deterministic_blueprint")
            log.warning(
                "    architect failed (%s: %s) — falling back to the %s blueprint",
                type(exc).__name__,
                exc,
                kind_contract.kind,
            )
            architect = {}
    if ctx.enforce_app_spec and ctx.app_spec_result and ctx.app_spec_scope:
        arch_seed = lock_chrome_on_architecture_seed(
            to_architecture_seed(ctx.app_spec_result.spec, ctx.app_spec_scope),
            kind_contract,
        )
        architect = merge_architecture_enrichment(arch_seed, architect)
    architect = apply_product_kind_to_architect(architect, kind_contract, plan)
    architect = ensure_internal_desk_architect(
        architect,
        context=industry_context,
    )
    architect = ensure_saas_accounting_architect(
        architect,
        context=industry_context,
    )
    # Final kind lock wins over forcer drift on AI hub / extra pages. On the
    # enforced-appspec path this is also R4 rung 4: an ops table the gap-fill
    # could not bring to the gate's floor refuses HERE, in seconds, instead of
    # spending a paid codegen run to be refused by the same rule at the gate.
    architect = apply_product_kind_to_architect(
        architect,
        kind_contract,
        plan,
        refuse_ops_under_floor=bool(
            ctx.enforce_app_spec and ctx.app_spec_result and ctx.app_spec_scope
        ),
    )
    try:
        architect = _normalize_architect(architect, plan)
    except Exception:
        raise
    architect = apply_recipe_to_architect(architect, plan)
    # Sealed brief wins over architect/recipe direction concat pile-ons.
    design_brief = plan.get("design_brief") if isinstance(plan.get("design_brief"), dict) else None
    if design_brief and design_brief.get("sealed"):
        architect = apply_sealed_brief_to_architect(architect, design_brief)
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
    # Final write-site name: keep early real name; only fill if still unknown.
    previous_brand = brand_name
    brand_name = resolve_preview_brand_name(
        brand_name=brand_name,
        brand_brief=brand_brief if isinstance(brand_brief, dict) else None,
        business_name=getattr(req, "business_name", None),
        concept_name=getattr(req, "concept_name", None),
        manifest=manifest if isinstance(manifest, dict) else None,
        demo=demo if isinstance(demo, dict) else None,
        plan=plan if isinstance(plan, dict) else None,
        fallback=True,
    ) or "Brand"
    # Empty-early → Brand-baked sticky seed: rematerialize once Brand→real upgrades.
    if (
        (previous_brand is None or previous_brand == "Brand")
        and brand_name != "Brand"
    ):
        plan = ensure_product_face_on_plan(
            plan, brand_name=brand_name, fill_defaults=True
        )
        log.info("    rematerialized mock_seed after Brand→%s upgrade", brand_name)
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
    ctx.full_context = full_context
    ctx.plan = plan
    ctx.manifest = manifest
    ctx.design_system = design_system
    ctx.design_brief = (
        plan.get("design_brief")
        if isinstance(plan.get("design_brief"), dict)
        else {}
    )
    ctx.architect = architect
    ctx.workspace = workspace
    ctx.brand_name = brand_name
    ctx.files_to_gen = files_to_gen
    ctx.specs_by_path = {f.get("path", ""): f for f in files_to_gen}
