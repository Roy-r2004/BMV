"""Orchestrate a fully AI-driven React preview app per business.

Pipeline (no hardcoded UI — the model designs and writes everything):
    plan (planning agent) -> architect (structure agent) -> codegen (writes files)
    -> build -> AI fix loop -> live preview
"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.models.request import Request
from app.application.services.industry_images import get_images_for_industry
from app.application.services.page_experience import (
    build_design_manifest,
    build_experience_plan,
    gather_full_context,
)
from app.application.preview_app.build import extract_build_errors, run_build
from app.application.preview_app.codegen import (
    call_architect,
    critique_and_refine,
    enrich_mock_if_sparse,
    fix_build_errors,
    generate_file,
)
from app.application.preview_app.assemble import write_app_tsx, write_index_css
from app.application.preview_app.safety import cleanup_page_shells, ensure_mock_exports
from app.application.preview_app.workspace import prepare_workspace
from app.application.services.progress import emit as _emit

MAX_BUILD_FIX_ATTEMPTS = 6
MAX_FILES = 40  # No artificial cap — build every page the architect plans


def _sort_gen_order(files: list[dict]) -> list[dict]:
    """Generate foundational files first so later files can import them."""
    kind_order = {"theme": 0, "data": 1, "component": 2, "layout": 3, "page": 4, "router": 5}
    return sorted(files, key=lambda f: (kind_order.get(f.get("kind", ""), 4), f.get("path", "")))


def _attach_plan_sections(files: list[dict], plan: dict) -> list[dict]:
    """Feed each page's plan spec (sections + features) into its codegen instructions."""
    page_specs: dict[str, dict] = {}
    for role in plan.get("roles", []):
        for page in role.get("pages", []):
            pid = page.get("id", "")
            if pid:
                page_specs[pid] = page

    out: list[dict] = []
    for f in files:
        spec = dict(f)
        path = (spec.get("path") or "").lower().replace("-", "").replace("_", "")
        for pid, page in page_specs.items():
            if pid and pid.replace("-", "").replace("_", "") in path:
                sections = page.get("sections") or []
                sec_text = json.dumps(sections[:14], ensure_ascii=False)[:3500]
                spec["instructions"] = (
                    f"{spec.get('instructions', '')}\n\n"
                    f"Page: {page.get('title')} — {page.get('purpose', '')}\n"
                    f"Sections to implement (build EVERY one, richly):\n{sec_text}\n"
                    f"Features to showcase: {', '.join(page.get('features_to_showcase', []))}"
                )
                break
        out.append(spec)
    return out


def _files_from_plan(architect: dict) -> list[dict]:
    """If the architect didn't return a file list, derive it from its routes."""
    files: list[dict] = [
        {"path": "src/index.css", "kind": "theme",
         "instructions": "Tailwind v4 @theme with brand colors + font from the design system"},
        {"path": "src/data/mock.ts", "kind": "data",
         "instructions": "Rich, business-specific sample data for every page"},
    ]
    for route in architect.get("routes", []):
        comp = route.get("component_file")
        if comp:
            files.append({
                "path": comp,
                "kind": "page",
                "instructions": route.get("purpose", route.get("title", "")),
            })
    for comp in architect.get("shared_components") or []:
        if comp.get("path"):
            files.append({
                "path": comp["path"],
                "kind": comp.get("kind", "component"),
                "instructions": comp.get("instructions", ""),
            })
    files.append({
        "path": "src/App.tsx",
        "kind": "router",
        "instructions": "React Router wiring every route from the plan; keep RouteBridge + RoleBridge",
    })
    return files


def _normalize_architect(architect: dict, plan: dict) -> dict:
    files = architect.get("files_to_generate") or []
    if not files:
        files = _files_from_plan(architect)

    # Guarantee every route has a matching file entry — no page ever skipped
    existing_paths = {(f.get("path") or "").lower().replace("\\", "/") for f in files}
    for route in architect.get("routes", []):
        comp = route.get("component_file")
        if not comp:
            continue
        norm = comp.lower().replace("\\", "/")
        if norm not in existing_paths:
            files.append({
                "path": comp,
                "kind": "page",
                "instructions": (
                    f"{route.get('title', '')} — {route.get('purpose', '')}. "
                    f"Features visible: {', '.join(route.get('features', []))}"
                ),
            })
            existing_paths.add(norm)

    architect["files_to_generate"] = _attach_plan_sections(files, plan)

    if not architect.get("roles"):
        architect["roles"] = [
            {
                "id": r.get("id"),
                "label": r.get("label"),
                "defaultPath": r.get("defaultPath", "/"),
                "icon": r.get("icon", "users"),
            }
            for r in plan.get("roles", [])
        ]
    return architect


def generate_preview_app(
    db: Session,
    request_id: int,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> dict:
    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise ValueError(f"Request {request_id} not found")
    if not req.mvp_blueprint:
        raise ValueError("MVP blueprint must be generated first.")

    demo: dict = {}
    if req.visual_demo_json:
        try:
            demo = json.loads(req.visual_demo_json)
        except Exception:
            pass

    theme = demo.get("visual_theme", {})
    primary = theme.get("primary_color", "#6366f1")
    secondary = theme.get("secondary_color", "#0d9488")
    images = get_images_for_industry(req.industry or "")

    print("  [1/5] Planning agent...", flush=True)
    _emit(db, request_id, "codegen", "Planning agent — mapping roles and user journeys...", 30)
    full_context = gather_full_context(req, demo)
    plan = build_experience_plan(req, demo, primary, secondary, ai_provider, template_renderer)
    manifest = build_design_manifest(full_context, plan, ai_provider, template_renderer)
    design_system = plan.get("design_system") or manifest.get("design_system") or {}
    roles_count = len(plan.get("roles", []))
    _emit(db, request_id, "codegen",
          f"Plan ready — {roles_count} role{'s' if roles_count != 1 else ''} defined", 33,
          detail="Architect designing component structure")

    print("  [2/5] Architect agent...", flush=True)
    _emit(db, request_id, "codegen", "Architect agent — designing pages and components...", 35)
    architect = call_architect(full_context, plan, manifest, images, ai_provider, template_renderer)
    architect = _normalize_architect(architect, plan)
    planned_files = len(architect.get("files_to_generate", []))
    _emit(db, request_id, "codegen",
          f"Architecture ready — {planned_files} files planned", 38,
          detail="Starting code generation")

    print("  [3/5] Preparing workspace...", flush=True)
    _emit(db, request_id, "codegen", "Setting up build workspace...", 40)
    workspace = prepare_workspace(request_id)

    # App.tsx, index.css, layouts, Nav — template/assembler owns these (not the LLM).
    _skip = {
        "src/app.tsx", "src/index.css",
        "src/components/nav.tsx", "src/layouts/publiclayout.tsx", "src/layouts/adminlayout.tsx",
    }
    all_files = [
        f for f in architect.get("files_to_generate", [])
        if (f.get("path") or "").lower().replace("\\", "/") not in _skip
    ]
    files_to_gen = _sort_gen_order(all_files[:MAX_FILES])
    total_files = len(files_to_gen)
    print(f"  [4/6] Codegen agent — {total_files} files...", flush=True)
    generated_ok = 0
    page_ok = 0
    # Codegen occupies pct range 42 → 78
    for i, spec in enumerate(files_to_gen, 1):
        path = spec.get("path", "?")
        short_path = path.replace("src/pages/", "").replace("src/components/", "").replace("src/", "")
        pct = 42 + int((i / max(total_files, 1)) * 36)
        _emit(db, request_id, "codegen",
              f"Generating: {short_path}", pct,
              detail=path,
              files_done=i - 1,
              files_total=total_files)
        print(f"    -> [{i}/{total_files}] {path}", flush=True)
        try:
            generate_file(workspace, spec, full_context, architect, plan, manifest, images, ai_provider, template_renderer)
            generated_ok += 1
            if spec.get("kind") == "page":
                page_ok += 1
            print(f"    OK {path}", flush=True)
        except Exception as e:
            print(f"    FAIL {path}: {e}", flush=True)

    if generated_ok == 0 or page_ok == 0:
        raise RuntimeError(
            f"Codegen produced no usable files (ok={generated_ok}, pages={page_ok}). "
            "Refusing to serve the blank template as a finished preview."
        )

    if enrich_mock_if_sparse(workspace, full_context, manifest, images, architect, ai_provider, template_renderer):
        print("    mock.ts enriched (was sparse)", flush=True)

    _emit(db, request_id, "critic",
          f"AI design critic reviewing {page_ok} pages...", 80,
          detail="Checking quality, consistency, and UX")
    print("  [5/6] Design critic — reviewing + refining pages...", flush=True)
    design_direction = architect.get("design_direction", "")
    try:
        refined = critique_and_refine(
            workspace, files_to_gen, full_context, design_direction, manifest, images,
            ai_provider, template_renderer,
        )
        print(f"    refined {len(refined)} page(s)", flush=True)
        _emit(db, request_id, "critic",
              f"Critic refined {len(refined)} page(s)", 84,
              detail="Applying design improvements")
    except Exception as e:
        print(f"    critic pass skipped: {e}", flush=True)

    stripped = cleanup_page_shells(workspace)
    if stripped:
        print(f"    removed duplicate nav from: {', '.join(stripped)}", flush=True)

    brand_name = (
        (manifest.get("brand") or {}).get("name")
        if isinstance(manifest.get("brand"), dict)
        else None
    ) or manifest.get("brand_name") or req.business_name or "Brand"
    font = design_system.get("font_family") or design_system.get("font") or manifest.get("font", "")

    added = ensure_mock_exports(workspace, architect, plan, images, brand_name)
    if added:
        print(f"    mock exports filled: {', '.join(added)}", flush=True)

    write_index_css(workspace, primary, secondary, font, template_renderer)
    routed = write_app_tsx(workspace, architect, template_renderer)
    print(f"    assembled router + theme ({len(routed)} routes)", flush=True)

    base_path = f"/api/preview-apps/{request_id}"
    _emit(db, request_id, "build", "Compiling React app...", 86,
          detail="Running Vite build")
    print("  [6/6] Building + AI fix loop...", flush=True)
    ok, build_log = run_build(workspace, base_path, template_renderer)
    attempt = 0
    while not ok and attempt < MAX_BUILD_FIX_ATTEMPTS:
        attempt += 1
        _emit(db, request_id, "build",
              f"Fixing build errors (attempt {attempt}/{MAX_BUILD_FIX_ATTEMPTS})...", 87,
              detail="AI is patching compilation errors")
        print(f"    fix attempt {attempt}/{MAX_BUILD_FIX_ATTEMPTS}...", flush=True)
        errors = extract_build_errors(build_log)
        try:
            fixed = fix_build_errors(workspace, errors, architect, ai_provider, template_renderer)
            print(f"    patched: {', '.join(fixed) or 'none'}", flush=True)
            ensure_mock_exports(workspace, architect, plan, images, brand_name)
            write_index_css(workspace, primary, secondary, font, template_renderer)
            write_app_tsx(workspace, architect, template_renderer)
        except Exception as e:
            print(f"    fix agent failed: {e} — retrying next attempt", flush=True)
            # Don't break — the next attempt re-extracts errors and tries again
            ok, build_log = run_build(workspace, base_path, template_renderer)
            continue
        ok, build_log = run_build(workspace, base_path, template_renderer)

    preview_url = f"{base_path}/" if ok else None
    if ok:
        _emit(db, request_id, "build_done", "Preview app compiled successfully!", 89,
              detail=f"{total_files} pages built and live")
    else:
        _emit(db, request_id, "build_failed", "Build failed — falling back to role pages", 89)
    print(f"  {'OK Preview built: ' + preview_url if ok else 'FAIL build'}", flush=True)

    accent = design_system.get("primary_color") or manifest.get("accent") or primary
    architect_roles = architect.get("roles") or []
    route_list = architect.get("routes") or []

    def _default_path(role_id: str) -> str:
        for rt in route_list:
            if rt.get("role_id") == role_id and rt.get("path"):
                return rt["path"]
        for ar in architect_roles:
            if ar.get("id") == role_id and ar.get("defaultPath"):
                return ar["defaultPath"]
        return "/"

    roles_out = [
        {
            "id": ar.get("id"),
            "label": ar.get("label"),
            "icon": ar.get("icon", "users"),
            "accent": accent,
            "defaultPath": ar.get("defaultPath") or _default_path(ar.get("id", "")),
        }
        for ar in architect_roles
    ] or [
        {
            "id": r.get("id"),
            "label": r.get("label"),
            "icon": r.get("icon", "users"),
            "accent": accent,
            "defaultPath": _default_path(r.get("id", "")),
        }
        for r in plan.get("roles", [])
    ]

    result = {
        "preview_app": {
            "url": preview_url,
            "status": "ready" if ok else "failed",
            "roles": roles_out,
            "routes": route_list,
            "design_direction": architect.get("design_direction", ""),
        },
        "experience_plan": plan,
    }

    existing: dict = {}
    if req.generated_pages:
        try:
            existing = json.loads(req.generated_pages)
        except Exception:
            pass
    existing["preview_app"] = result["preview_app"]
    existing["experience_plan"] = plan
    if not existing.get("roles"):
        existing["roles"] = [
            {
                "id": r.get("id"),
                "label": r.get("label"),
                "icon": r.get("icon", "users"),
                "accent": accent,
                "tagline": r.get("tagline", ""),
                "pages": [{"id": p.get("id"), "title": p.get("title")} for p in r.get("pages", [])],
            }
            for r in plan.get("roles", [])
        ]

    req.generated_pages = json.dumps(existing)
    req.updated_at = datetime.utcnow()
    db.commit()

    if not ok:
        raise RuntimeError(f"Preview app build failed after {MAX_BUILD_FIX_ATTEMPTS} fix attempts")

    return result
