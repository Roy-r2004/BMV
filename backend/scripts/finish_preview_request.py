"""Finish preview app build from an existing workspace (skip codegen + critic)."""
import json
import sys
from datetime import datetime

sys.path.insert(0, ".")

from app.application.preview_app.assemble import (
    architect_from_stored,
    find_missing_route_pages,
    write_app_tsx,
    write_index_css,
)
from app.application.preview_app.build import extract_build_errors, run_build
from app.application.preview_app.codegen import call_architect, fix_build_errors, generate_file
from app.application.preview_app.pipeline import MAX_BUILD_FIX_ATTEMPTS, _normalize_architect
from app.application.preview_app.safety import apply_workspace_guards, cleanup_page_shells
from app.application.preview_app.workspace import get_workspace
from app.application.services.industry_images import get_images_for_industry
from app.application.services.page_experience import (
    build_design_manifest,
    build_experience_plan,
    gather_full_context,
)
from app.application.services.progress import emit as _emit
from app.domain.models.request import Request
from app.infrastructure.ai_providers.factory import get_ai_provider
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.templating.renderer import get_template_renderer


def main(request_id: int) -> None:
    db = SessionLocal()
    ai = get_ai_provider()
    renderer = get_template_renderer()
    try:
        req = db.query(Request).filter(Request.id == request_id).first()
        if not req:
            raise SystemExit(f"Request {request_id} not found")

        workspace = get_workspace(request_id)
        if not workspace.is_dir():
            raise SystemExit(f"Workspace missing: {workspace}")

        demo: dict = {}
        if req.visual_demo_json:
            try:
                demo = json.loads(req.visual_demo_json)
            except Exception:
                pass

        theme = demo.get("visual_theme", {})
        primary = theme.get("primary_color", "#6366f1")
        secondary = theme.get("secondary_color", "#0d9488")
        images = get_images_for_industry(
            req.industry or "",
            seed=req.id,
            business_name=req.business_name,
        )

        print("Loading stored architect + plan...", flush=True)
        full_context = gather_full_context(req, demo)
        plan = build_experience_plan(req, demo, primary, secondary, ai, renderer)
        manifest = build_design_manifest(full_context, plan, ai, renderer)
        design_system = plan.get("design_system") or manifest.get("design_system") or {}

        existing_gp: dict = {}
        if req.generated_pages:
            try:
                existing_gp = json.loads(req.generated_pages)
            except Exception:
                pass
        architect = architect_from_stored(existing_gp, plan)
        if not architect.get("routes"):
            architect = _normalize_architect(
                call_architect(full_context, plan, manifest, images, ai, renderer),
                plan,
            )

        missing = find_missing_route_pages(workspace, architect)
        if missing:
            print(f"  generating {len(missing)} missing page(s)...", flush=True)
            images_data = images
            for spec in missing:
                try:
                    generate_file(
                        workspace, spec, full_context, architect, plan, manifest, images_data, ai, renderer,
                    )
                    print(f"    OK {spec.get('path')}", flush=True)
                except Exception as e:
                    print(f"    FAIL {spec.get('path')}: {e}", flush=True)

        _emit(db, request_id, "build", "Assembling routes and compiling...", 86)
        stripped = cleanup_page_shells(workspace)
        if stripped:
            print(f"  cleaned shells: {', '.join(stripped)}", flush=True)

        brand_name = req.business_name or "Brand"
        font = design_system.get("font_family") or design_system.get("font") or manifest.get("font", "")
        apply_workspace_guards(workspace, architect, plan, images, brand_name, primary, secondary, font, renderer)
        routed = write_app_tsx(workspace, architect, renderer)
        print(f"  routes wired: {len(routed)}", flush=True)

        base_path = f"/api/preview-apps/{request_id}"
        ok, build_log = run_build(workspace, base_path, renderer)
        attempt = 0
        while not ok and attempt < MAX_BUILD_FIX_ATTEMPTS:
            attempt += 1
            print(f"  fix attempt {attempt}/{MAX_BUILD_FIX_ATTEMPTS}...", flush=True)
            errors = extract_build_errors(build_log)
            try:
                patched = fix_build_errors(workspace, errors, architect, ai, renderer)
                print(f"  patched: {', '.join(patched) or 'none'}", flush=True)
                apply_workspace_guards(workspace, architect, plan, images, brand_name, primary, secondary, font, renderer)
            except Exception as e:
                print(f"  fix failed: {e}", flush=True)
            ok, build_log = run_build(workspace, base_path, renderer)

        preview_url = f"{base_path}/" if ok else None
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

        existing: dict = {}
        if req.generated_pages:
            try:
                existing = json.loads(req.generated_pages)
            except Exception:
                pass

        existing["preview_app"] = {
            "url": preview_url,
            "status": "ready" if ok else "failed",
            "roles": roles_out,
            "routes": route_list,
            "design_direction": architect.get("design_direction", ""),
        }
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

        if ok:
            _emit(db, request_id, "done", "Generation complete!", 100)
            print(f"SUCCESS — http://localhost:5173/result/{request_id}")
            print(f"Preview app: {preview_url}")
        else:
            print("BUILD FAILED")
            print(build_log[-4000:])
            raise SystemExit(1)
    finally:
        db.close()


if __name__ == "__main__":
    rid = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    main(rid)
