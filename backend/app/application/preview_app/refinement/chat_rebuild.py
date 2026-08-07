"""Apply chat feedback to an existing preview React workspace and rebuild."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.application.appspec.workspace_validation import validate_app_spec_workspace
from app.application.pipelines._shared import business_info, get_request
from app.application.preview_app.ai_budget import request_mutation_boundary
from app.application.preview_app.assemble import write_app_tsx, write_index_css
from app.application.preview_app.build import extract_build_errors, run_build
from app.application.preview_app.catalogue_contract import enforce_catalogue_page_contract
from app.application.preview_app.codegen.architect import _catalogue_routes_context
from app.application.preview_app.codegen.fix_agent import fix_build_errors
from app.application.preview_app.fallback import (
    clear_stubbed_path,
    clear_stubbed_paths,
    consume_stubbed_paths,
    record_stubbed_path,
)
from app.application.preview_app.pipeline.architect_normalize import _plan_for_persistence
from app.application.preview_app.pipeline.orchestrator import generate_preview_app
from app.application.preview_app.protected_paths import has_catalogue_routes, is_template_owned_path
from app.application.preview_app.refinement.appspec_context import (
    _load_app_spec_refinement_context,
    _merge_app_spec_refinement_enrichment,
)
from app.application.preview_app.refinement.intent import (
    _is_full_redesign_request,
    _rank_refinement_files,
)
from app.application.preview_app.refinement.workspace_patch import (
    _apply_chat_file_updates,
    _architect_from_generated,
    _catalogue_fallback_paths,
    _merge_chat_routes,
    _request_chat_refinement_payload,
)
from app.application.preview_app.safety.mock_data import ensure_mock_exports
from app.application.preview_app.safety.orchestrator import apply_workspace_guards
from app.application.preview_app.text_utils import _bounded_json
from app.application.preview_app.workspace import (
    backup_dist,
    discard_backup,
    get_workspace,
    list_source_files,
    read_file,
    restore_dist,
    restore_source,
    snapshot_source,
    write_file,
)
from app.application.prompts import PromptTemplate
from app.application.services.industry_images import (
    get_images_for_industry,
    industry_or_derived,
)
from app.application.services.progress import emit as _emit
from app.application.services.visual_demo_enrichment import enrich_visual_demo
from app.application.services.visual_demo_merge import merge_visual_demo
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.infrastructure.logging import get_logger

refine_log = get_logger("ChatRefinement")


@request_mutation_boundary
def refine_preview_app_from_chat(
    db: Session,
    request_id: int,
    user_message: str,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> dict:
    """Patch the preview workspace from chat instructions, rebuild, and persist status."""
    req = get_request(db, request_id)
    generated_pages: dict = {}
    if req.generated_pages:
        try:
            generated_pages = json.loads(req.generated_pages)
        except Exception:
            generated_pages = {}
    original_generated_pages = json.loads(json.dumps(generated_pages))
    original_generated_pages_text = req.generated_pages
    metadata_fields = (
        "concept_name",
        "preview_summary",
        "preview_features",
        "business_fit_score",
        "visual_demo_json",
        "visual_demo_generated_at",
        "updated_at",
    )
    original_metadata = {
        field: getattr(req, field, None)
        for field in metadata_fields
    }

    workspace = get_workspace(request_id)
    if not workspace.is_dir():
        raise ValueError("Preview app workspace not found.")

    stored_plan = generated_pages.get("experience_plan") or {}
    stored_architect = _architect_from_generated(generated_pages, stored_plan)
    try:
        app_spec_context = _load_app_spec_refinement_context(
            db,
            request_id,
            generated_pages,
            experience_plan=stored_plan,
            architect=stored_architect,
        )
    except Exception as exc:
        # The public request marked this preview as "rebuilding" before the
        # worker started. Contract resolution happens before any file write, so
        # restore the prior live status immediately and fail closed.
        restored = original_generated_pages
        restored_preview = restored.setdefault("preview_app", {})
        restored_preview["status"] = "ready"
        restored_preview["last_refinement_error"] = str(exc)[:300]
        req.generated_pages = json.dumps(restored)
        db.commit()
        return {
            "reply": (
                "I couldn't safely apply that change because the preview's "
                "product contract could not be verified. The current preview "
                "has been kept unchanged."
            ),
            "changes_made": ["No changes applied — AppSpec verification failed"],
            "preview_rebuild_succeeded": False,
            "reverted": True,
        }

    # Full redesign / "make sure all pages exist" → regenerate the whole app.
    # One-shot chat JSON can't reliably rewrite every file without truncation.
    if _is_full_redesign_request(user_message):
        refine_log.info("full redesign requested for %s — regenerating preview app", request_id)
        message_digest = hashlib.sha256(user_message.encode("utf-8")).hexdigest()[:16]
        _emit(
            db,
            request_id,
            "refine",
            "Full redesign — regenerating the live app...",
            10,
            detail=f"message length={len(user_message)} sha256={message_digest}",
        )
        try:
            result = generate_preview_app(
                db,
                request_id,
                ai_provider,
                template_renderer,
                app_spec_revision_id=(
                    app_spec_context.revision.id if app_spec_context else None
                ),
            )
            pa = (result or {}).get("preview_app") or {}
            ok = pa.get("status") == "ready"
            _emit(
                db, request_id,
                "refine_done" if ok else "refine_failed",
                "Live preview redesigned!" if ok else "Redesign finished with build issues",
                100,
            )
            return {
                "reply": (
                    "I've fully redesigned your live preview and regenerated the pages. "
                    "Refresh the Live Product tab to see the new look."
                    if ok else
                    "I tried a full redesign but the build still had issues. "
                    "Try a smaller change, or ask me to redesign again."
                ),
                "changes_made": ["Full preview app regeneration"],
                "preview_rebuild_succeeded": ok,
                "reverted": False,
            }
        except Exception as exc:
            refine_log.exception("full redesign failed for %s", request_id)
            _emit(db, request_id, "refine_failed", f"Redesign failed: {exc}", 100)
            return {
                "reply": (
                    f"I couldn't complete a full redesign ({exc}). "
                    "Try again, or ask for one specific change at a time."
                ),
                "changes_made": [],
                "preview_rebuild_succeeded": False,
                "reverted": False,
            }

    # Safety net: snapshot the current working state so a bad AI edit, a
    # failed build, or any unexpected error can never leave the live
    # preview broken — we roll back to exactly what was being served
    # before this chat message.
    source_snapshot = snapshot_source(workspace)
    dist_backup = backup_dist(workspace)
    had_previous_good_build = dist_backup is not None

    plan = app_spec_context.plan if app_spec_context else stored_plan
    architect = app_spec_context.architect if app_spec_context else stored_architect
    if has_catalogue_routes(architect):
        architect["_catalogue_workspace"] = True

    ok = False
    data: dict = {}
    changes_made: list[str] = []
    error_message: str | None = None
    pending_metadata: dict[str, object] = {}

    try:
        message_digest = hashlib.sha256(user_message.encode("utf-8")).hexdigest()[:16]
        _emit(
            db,
            request_id,
            "refine",
            "Applying your feedback to the live app...",
            5,
            detail=f"message length={len(user_message)} sha256={message_digest}",
        )

        paths = [
            path
            for path in sorted(list_source_files(workspace), key=_rank_refinement_files)
            if not is_template_owned_path(path, architect)
        ]
        priority = [p for p in paths if p.endswith((".tsx", ".ts", ".css"))][:18]
        files_content = "\n\n".join(
            f"=== {p} ===\n{read_file(workspace, p)[:8000]}" for p in priority
        )
        file_tree = "\n".join(sorted(paths))

        prompt = template_renderer.render(
            PromptTemplate.PREVIEW_APP_CHAT_REFINEMENT,
            business_context=business_info(req)[:6000],
            user_message=user_message,
            experience_plan_json=json.dumps(plan, ensure_ascii=False, indent=2)[:8000],
            architect_json=json.dumps(architect, ensure_ascii=False, indent=2)[:6000],
            file_tree=file_tree[:4000],
            files_content=files_content[:45000],
            catalogue_mode=has_catalogue_routes(architect),
            catalogue_routes_json=_catalogue_routes_context(architect),
            app_spec_enforced=bool(app_spec_context),
            app_spec_ref_json=_bounded_json(
                generated_pages.get("app_spec_ref") or {}, 1200
            ),
            app_spec_contracts_json=_bounded_json(
                app_spec_context.selected_contracts if app_spec_context else {},
                24000,
            ),
        )

        _emit(db, request_id, "refine", "AI is updating your pages...", 25)
        data = _request_chat_refinement_payload(ai_provider, prompt)

        changes_made = list(data.get("changes_made") or [])
        changes_made.extend(
            _apply_chat_file_updates(
                workspace,
                data,
                architect,
                ai_provider=ai_provider,
                chat_prompt=prompt,
            )
        )

        if app_spec_context:
            plan, architect = _merge_app_spec_refinement_enrichment(
                app_spec_context,
                data,
            )
            pa = generated_pages.setdefault("preview_app", {})
            pa["routes"] = architect.get("routes") or []
            pa["roles"] = architect.get("roles") or []
            pa["design_direction"] = architect.get("design_direction", "")
            generated_pages["experience_plan"] = _plan_for_persistence(plan)
            if data.get("architect") or data.get("experience_plan"):
                changes_made.append(
                    "Applied design enrichment while preserving the AppSpec structure"
                )
        else:
            if data.get("architect"):
                arch = data["architect"]
                pa = generated_pages.setdefault("preview_app", {})
                if arch.get("routes"):
                    updated_routes = _merge_chat_routes(
                        architect.get("routes") or [],
                        arch["routes"],
                        data.get("experience_plan") or plan,
                        workspace,
                    )
                    pa["routes"] = updated_routes
                    architect["routes"] = updated_routes
                if arch.get("roles"):
                    pa["roles"] = arch["roles"]
                    architect["roles"] = arch["roles"]
                if arch.get("design_direction"):
                    pa["design_direction"] = arch["design_direction"]
                changes_made.append("Updated navigation structure")

            if data.get("experience_plan"):
                generated_pages["experience_plan"] = data["experience_plan"]
                plan = data["experience_plan"]
                changes_made.append("Updated experience plan")

        for route in architect.get("routes") or []:
            path = route.get("component_file") or ""
            if not path or not route.get("skeleton_id"):
                continue
            current = read_file(workspace, path)
            guarded, replaced = enforce_catalogue_page_contract(
                path,
                current,
                architect,
            )
            # Persist both full scaffold replaces and in-place slot heals.
            if guarded != current:
                write_file(workspace, path, guarded)
                if replaced:
                    changes_made.append(f"Repaired catalogue contract for {path}")
            if replaced or "deterministic catalogue contract scaffold" in guarded:
                record_stubbed_path(workspace, path)
            else:
                clear_stubbed_path(workspace, path)

        # These fields summarize product semantics, not visual treatment. An
        # AppSpec-governed refinement must not create a competing contract.
        if not app_spec_context:
            if data.get("concept_name"):
                pending_metadata["concept_name"] = data["concept_name"]
                changes_made.append(f"Renamed concept to {data['concept_name']}")
            if data.get("preview_summary"):
                pending_metadata["preview_summary"] = data["preview_summary"]
                changes_made.append("Updated preview summary")
            if data.get("preview_features"):
                pending_metadata["preview_features"] = json.dumps(data["preview_features"])
                changes_made.append("Updated feature list")
            if data.get("business_fit_score") is not None:
                pending_metadata["business_fit_score"] = int(data["business_fit_score"])

        demo: dict = {}
        if req.visual_demo_json:
            try:
                demo = json.loads(req.visual_demo_json)
            except Exception:
                pass
        if data.get("visual_demo"):
            demo = merge_visual_demo(demo, data["visual_demo"])
            demo = enrich_visual_demo(demo, req)
            pending_metadata["visual_demo_json"] = json.dumps(demo)
            pending_metadata["visual_demo_generated_at"] = datetime.utcnow()
            changes_made.append("Updated visual theme and copy")

        theme = demo.get("visual_theme", {})
        primary = theme.get("primary_color", "#6366f1")
        secondary = theme.get("secondary_color", "#0d9488")
        design_system = plan.get("design_system") or {}
        font = design_system.get("font_family") or design_system.get("font") or ""
        ref_meta: dict = {}
        if req.reference_metadata:
            try:
                ref_meta = json.loads(req.reference_metadata)
            except Exception:
                ref_meta = {}
        images = get_images_for_industry(
            industry_or_derived(
                req.industry, getattr(req, "business_description", None)
            ),
            seed=request_id,
            hero_override=ref_meta.get("og_image") or None,
            business_name=req.business_name,
        )
        brand_name = req.business_name or "Brand"

        try:
            apply_workspace_guards(
                workspace, architect, plan, images, brand_name, primary, secondary, font,
                template_renderer, (plan or {}).get("design_system"),
            )
        except Exception as guard_exc:
            refine_log.warning("refine guards skipped: %s", guard_exc)
            ensure_mock_exports(workspace, architect, plan, images, brand_name)
            from app.application.preview_app.design_recipes import get_recipe

            recipe = get_recipe(
                plan.get("recipe_id")
                or (plan.get("design_system") or {}).get("recipe_id")
            )
            write_index_css(
                workspace,
                primary,
                secondary,
                font,
                template_renderer,
                recipe=recipe,
                design_system=(plan or {}).get("design_system") or {},
            )
            write_app_tsx(workspace, architect, template_renderer)

        base_path = f"/api/preview-apps/{request_id}"
        _emit(db, request_id, "refine", "Rebuilding live preview...", 60)
        ok, build_log = run_build(workspace, base_path, template_renderer)
        attempt = 0
        while not ok and attempt < settings.PREVIEW_MAX_BUILD_FIX_ATTEMPTS:
            attempt += 1
            _emit(
                db, request_id, "refine",
                f"Fixing build errors (attempt {attempt}/{settings.PREVIEW_MAX_BUILD_FIX_ATTEMPTS})...",
                65 + attempt,
            )
            errors = extract_build_errors(build_log)
            try:
                fix_build_errors(workspace, errors, architect, ai_provider, template_renderer)
                apply_workspace_guards(
                    workspace, architect, plan, images, brand_name, primary, secondary, font,
                    template_renderer, (plan or {}).get("design_system"),
                )
            except Exception:
                pass
            ok, build_log = run_build(workspace, base_path, template_renderer)
        if ok and app_spec_context:
            workspace_issues = validate_app_spec_workspace(
                workspace,
                app_spec_context.spec,
                app_spec_context.scope,
                architect,
            )
            scaffold_pages = _catalogue_fallback_paths(workspace, architect)
            stubbed_pages = consume_stubbed_paths(workspace)
            contract_fallback_pages = list(
                dict.fromkeys([*scaffold_pages, *stubbed_pages])
            )
            if workspace_issues or contract_fallback_pages:
                ok = False
                parts: list[str] = []
                if workspace_issues:
                    parts.append(
                        "missing AppSpec hooks: " + "; ".join(workspace_issues[:6])
                    )
                if contract_fallback_pages:
                    parts.append(
                        "fallback/stub pages: " + ", ".join(contract_fallback_pages[:8])
                    )
                error_message = "AppSpec refinement rejected — " + " | ".join(parts)
        if not ok:
            error_message = (
                error_message
                or extract_build_errors(build_log)[:500]
                or "Build failed"
            )
            error_digest = hashlib.sha256(error_message.encode("utf-8")).hexdigest()[:16]
            refine_log.error(
                "build failed for %s: length=%s sha256=%s — %s",
                request_id,
                len(error_message),
                error_digest,
                error_message[:300],
            )
    except Exception as exc:
        ok = False
        error_message = str(exc)
        refine_log.exception("refine exception for %s", request_id)

    reverted = False
    restored_fallback_pages: list[str] = []
    if not ok:
        restore_source(workspace, source_snapshot)
        restored_fallback_pages = _catalogue_fallback_paths(workspace, architect)
        # Drop any in-memory stub tracking for this workspace after revert.
        clear_stubbed_paths(workspace)
        if had_previous_good_build:
            restore_dist(workspace, dist_backup)
            reverted = True
        generated_pages = original_generated_pages
        if reverted:
            restored_preview = generated_pages.setdefault("preview_app", {})
            restored_preview["status"] = "ready"
            restored_preview["fallback_pages"] = restored_fallback_pages
        for field, value in original_metadata.items():
            setattr(req, field, value)
    discard_backup(dist_backup)

    base_path = f"/api/preview-apps/{request_id}"
    if ok:
        for field, value in pending_metadata.items():
            setattr(req, field, value)
        pa = generated_pages.setdefault("preview_app", {})
        pa["url"] = f"{base_path}/"
        pa["status"] = "ready"
        # Always consume the in-memory stub tracker so request-scoped registries
        # do not leak across refinements (AppSpec path already consumed above).
        stubbed_pages = consume_stubbed_paths(workspace)
        catalogue_pages = _catalogue_fallback_paths(workspace, architect)
        pa["fallback_pages"] = list(dict.fromkeys([*catalogue_pages, *stubbed_pages]))
        pa.pop("last_refinement_error", None)
        generated_pages["preview_app"] = pa
        if app_spec_context:
            generated_pages["experience_plan"] = _plan_for_persistence(plan)
            generated_pages["app_spec_ref"] = original_generated_pages.get(
                "app_spec_ref"
            )
        req.generated_pages = json.dumps(generated_pages)
        req.updated_at = datetime.utcnow()
    else:
        req.generated_pages = (
            json.dumps(generated_pages)
            if reverted
            else original_generated_pages_text
        )
    db.commit()

    if ok:
        _emit(db, request_id, "refine_done", "Live preview updated!", 100, detail="; ".join(changes_made[:4]))
    elif reverted:
        _emit(db, request_id, "refine_reverted", "Change couldn't be applied safely — kept your previous version", 100)
    else:
        _emit(db, request_id, "refine_failed", "Rebuild failed — try rephrasing your request", 100)

    if ok:
        reply = data.get("reply") or "I've updated your live preview based on your feedback."
    elif reverted:
        reply = (
            "I couldn't apply that change without breaking the app, so I've kept your previous "
            "working version live. Try describing one smaller, more specific change at a time."
        )
        if error_message:
            reply += f" (Build issue: {error_message[:180]})"
        changes_made = ["No changes applied — reverted to previous working version"]
    else:
        reply = "I couldn't get the live preview building. Try describing one smaller, more specific change."
        if error_message:
            changes_made = changes_made or []

    return {
        "reply": reply,
        "changes_made": changes_made,
        "preview_rebuild_succeeded": ok,
        "reverted": reverted,
    }
