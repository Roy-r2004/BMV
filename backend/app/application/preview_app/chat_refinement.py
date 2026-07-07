"""Apply chat feedback to an existing preview React workspace and rebuild."""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.application.pipelines._shared import business_info, get_request
from app.application.preview_app.assemble import write_app_tsx, write_index_css
from app.application.preview_app.build import extract_build_errors, run_build
from app.application.preview_app.codegen import _strip_fences, fix_build_errors
from app.application.preview_app.pipeline import MAX_BUILD_FIX_ATTEMPTS
from app.application.preview_app.safety import (
    ensure_mock_exports,
    looks_truncated_source,
    sanitize_workspace_sources,
)
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
from app.application.services.industry_images import get_images_for_industry
from app.application.services.progress import emit as _emit
from app.application.services.visual_demo_enrichment import enrich_visual_demo
from app.application.services.visual_demo_merge import merge_visual_demo
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.shared.json_utils import extract_json_from_text


def _architect_from_generated(generated_pages: dict) -> dict:
    from app.application.preview_app.assemble import architect_from_stored
    return architect_from_stored(generated_pages)


def _rank_refinement_files(path: str) -> tuple:
    low = path.lower().replace("\\", "/")
    if "app.tsx" in low:
        return (0, path)
    if "/pages/" in low:
        return (1, path)
    if "mock.ts" in low:
        return (2, path)
    if "/layouts/" in low or "/components/" in low:
        return (3, path)
    return (4, path)


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

    workspace = get_workspace(request_id)
    if not workspace.is_dir():
        raise ValueError("Preview app workspace not found.")

    # Safety net: snapshot the current working state so a bad AI edit, a
    # failed build, or any unexpected error can never leave the live
    # preview broken — we roll back to exactly what was being served
    # before this chat message.
    source_snapshot = snapshot_source(workspace)
    dist_backup = backup_dist(workspace)
    had_previous_good_build = dist_backup is not None

    plan = generated_pages.get("experience_plan") or {}
    architect = _architect_from_generated(generated_pages)

    ok = False
    data: dict = {}
    changes_made: list[str] = []
    error_message: str | None = None

    try:
        _emit(db, request_id, "refine", "Applying your feedback to the live app...", 5, detail=user_message[:120])

        paths = sorted(list_source_files(workspace), key=_rank_refinement_files)
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
        )

        _emit(db, request_id, "refine", "AI is updating your pages...", 25)
        raw = ai_provider.ask_chat(
            settings.PREVIEW_APP_MODEL,
            [{"role": "user", "content": prompt}],
            max_tokens=16000,
        )
        data = extract_json_from_text(raw)

        changes_made = list(data.get("changes_made") or [])
        for item in data.get("files", []):
            path = item.get("path", "")
            content = item.get("content", "")
            if path and content:
                cleaned = _strip_fences(content)
                if looks_truncated_source(cleaned):
                    changes_made.append(f"Skipped truncated write to {path} (kept existing file)")
                    continue
                write_file(workspace, path, cleaned)
                changes_made.append(f"Updated {path}")

        if data.get("architect"):
            arch = data["architect"]
            pa = generated_pages.setdefault("preview_app", {})
            if arch.get("routes"):
                pa["routes"] = arch["routes"]
                architect["routes"] = arch["routes"]
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

        if data.get("concept_name"):
            req.concept_name = data["concept_name"]
            changes_made.append(f"Renamed concept to {data['concept_name']}")
        if data.get("preview_summary"):
            req.preview_summary = data["preview_summary"]
            changes_made.append("Updated preview summary")
        if data.get("preview_features"):
            req.preview_features = json.dumps(data["preview_features"])
            changes_made.append("Updated feature list")
        if data.get("business_fit_score") is not None:
            req.business_fit_score = int(data["business_fit_score"])

        demo: dict = {}
        if req.visual_demo_json:
            try:
                demo = json.loads(req.visual_demo_json)
            except Exception:
                pass
        if data.get("visual_demo"):
            demo = merge_visual_demo(demo, data["visual_demo"])
            demo = enrich_visual_demo(demo, req)
            req.visual_demo_json = json.dumps(demo)
            req.visual_demo_generated_at = datetime.utcnow()
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
            req.industry or "",
            seed=request_id,
            hero_override=ref_meta.get("og_image") or None,
        )
        brand_name = req.business_name or "Brand"

        sanitize_workspace_sources(workspace)
        ensure_mock_exports(workspace, architect, plan, images, brand_name)
        write_index_css(workspace, primary, secondary, font, template_renderer)
        write_app_tsx(workspace, architect, template_renderer)

        base_path = f"/api/preview-apps/{request_id}"
        _emit(db, request_id, "refine", "Rebuilding live preview...", 60)
        ok, build_log = run_build(workspace, base_path, template_renderer)
        attempt = 0
        while not ok and attempt < MAX_BUILD_FIX_ATTEMPTS:
            attempt += 1
            _emit(
                db, request_id, "refine",
                f"Fixing build errors (attempt {attempt}/{MAX_BUILD_FIX_ATTEMPTS})...",
                65 + attempt,
            )
            errors = extract_build_errors(build_log)
            try:
                fix_build_errors(workspace, errors, architect, ai_provider, template_renderer)
                ensure_mock_exports(workspace, architect, plan, images, brand_name)
                write_index_css(workspace, primary, secondary, font, template_renderer)
                write_app_tsx(workspace, architect, template_renderer)
            except Exception:
                pass
            ok, build_log = run_build(workspace, base_path, template_renderer)
    except Exception as exc:
        ok = False
        error_message = str(exc)

    reverted = False
    if not ok and had_previous_good_build:
        # Never leave the live app broken: roll back to exactly what was
        # being served before this chat message.
        restore_source(workspace, source_snapshot)
        restore_dist(workspace, dist_backup)
        reverted = True
    discard_backup(dist_backup)

    pa = generated_pages.setdefault("preview_app", {})
    if ok:
        base_path = f"/api/preview-apps/{request_id}"
        pa["url"] = f"{base_path}/"
        pa["status"] = "ready"
    elif reverted:
        pa["status"] = "ready"  # previous working build is back and being served
    else:
        pa["status"] = "failed"
    generated_pages["preview_app"] = pa
    req.generated_pages = json.dumps(generated_pages)
    req.updated_at = datetime.utcnow()
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
