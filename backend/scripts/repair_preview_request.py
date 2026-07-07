"""Regenerate truncated pages, fix imports, assemble routes, and build."""
import json
import sys
from datetime import datetime

sys.path.insert(0, ".")

from app.application.preview_app.assemble import write_app_tsx, write_index_css
from app.application.preview_app.build import extract_build_errors, run_build
from app.application.preview_app.codegen import call_architect, fix_build_errors, generate_file
from app.application.preview_app.pipeline import MAX_BUILD_FIX_ATTEMPTS, _normalize_architect
from app.application.preview_app.safety import cleanup_page_shells, ensure_mock_exports, looks_truncated_source
from app.application.preview_app.workspace import get_workspace, list_source_files, read_file, write_file
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

ROUTES = [
    {"path": "/", "component_file": "src/pages/HomePage.tsx", "layout": "public", "role_id": "public"},
    {"path": "/features", "component_file": "src/pages/FeaturesPage.tsx", "layout": "public", "role_id": "public"},
    {"path": "/request-demo", "component_file": "src/pages/RequestDemoPage.tsx", "layout": "public", "role_id": "public"},
    {"path": "/dashboard", "component_file": "src/pages/owner/DashboardPage.tsx", "layout": "admin", "role_id": "restaurant_owner"},
    {"path": "/inventory", "component_file": "src/pages/owner/InventoryPage.tsx", "layout": "admin", "role_id": "restaurant_owner"},
    {"path": "/procurement", "component_file": "src/pages/owner/ProcurementPage.tsx", "layout": "admin", "role_id": "restaurant_owner"},
    {"path": "/ai-assistant", "component_file": "src/pages/owner/AIAssistantPage.tsx", "layout": "admin", "role_id": "restaurant_owner"},
    {"path": "/admin", "component_file": "src/pages/admin/AdminDashboardPage.tsx", "layout": "admin", "role_id": "plate_sync_admin"},
    {"path": "/integrations", "component_file": "src/pages/admin/IntegrationsPage.tsx", "layout": "admin", "role_id": "plate_sync_admin"},
]


def main(request_id: int) -> None:
    db = SessionLocal()
    ai = get_ai_provider()
    renderer = get_template_renderer()
    try:
        req = db.query(Request).filter(Request.id == request_id).first()
        if not req:
            raise SystemExit(f"Request {request_id} not found")

        workspace = get_workspace(request_id)
        demo = json.loads(req.visual_demo_json or "{}")
        theme = demo.get("visual_theme", {})
        primary = theme.get("primary_color", "#2c7a7b")
        secondary = theme.get("secondary_color", "#f6ad55")
        images = get_images_for_industry(req.industry or "")

        full_context = gather_full_context(req, demo)
        plan = build_experience_plan(req, demo, primary, secondary, ai, renderer)
        manifest = build_design_manifest(full_context, plan, ai, renderer)
        design_system = plan.get("design_system") or manifest.get("design_system") or {}
        architect = _normalize_architect(
            call_architect(full_context, plan, manifest, images, ai, renderer),
            plan,
        )
        architect["routes"] = ROUTES

        for rel in list_source_files(workspace):
            if not rel.endswith(".tsx"):
                continue
            if "/owner/" in rel.replace("\\", "/") and "from '../components/UiIcons'" in read_file(workspace, rel):
                write_file(
                    workspace,
                    rel,
                    read_file(workspace, rel).replace(
                        "from '../components/UiIcons'",
                        "from '../../components/UiIcons'",
                    ),
                )
                print(f"fixed import: {rel}")

        specs = {f.get("path"): f for f in architect.get("files_to_generate", [])}
        for rel in list_source_files(workspace):
            if not rel.endswith(".tsx") or "/pages/" not in rel:
                continue
            raw = read_file(workspace, rel)
            if looks_truncated_source(raw):
                spec = specs.get(rel) or {"path": rel, "kind": "page", "instructions": rel}
                print(f"regenerating truncated: {rel}")
                generate_file(workspace, spec, full_context, architect, plan, manifest, images, ai, renderer)

        cleanup_page_shells(workspace)
        brand_name = req.business_name or "Brand"
        font = design_system.get("font_family") or design_system.get("font") or ""
        ensure_mock_exports(workspace, architect, plan, images, brand_name)
        write_index_css(workspace, primary, secondary, font, renderer)
        routed = write_app_tsx(workspace, architect, renderer)
        print(f"routes wired: {len(routed)}")

        base_path = f"/api/preview-apps/{request_id}"
        ok, build_log = run_build(workspace, base_path, renderer)
        attempt = 0
        while not ok and attempt < MAX_BUILD_FIX_ATTEMPTS:
            attempt += 1
            print(f"fix attempt {attempt}/{MAX_BUILD_FIX_ATTEMPTS}...")
            errors = extract_build_errors(build_log)
            try:
                patched = fix_build_errors(workspace, errors, architect, ai, renderer)
                print(f"  patched: {', '.join(patched) or 'none'}")
                write_index_css(workspace, primary, secondary, font, renderer)
                write_app_tsx(workspace, architect, renderer)
            except Exception as e:
                print(f"  fix failed: {e}")
            ok, build_log = run_build(workspace, base_path, renderer)

        preview_url = f"{base_path}/" if ok else None
        roles_out = [
            {"id": "public", "label": "Prospective Customer", "icon": "users", "accent": primary, "defaultPath": "/"},
            {"id": "restaurant_owner", "label": "Restaurant Owner", "icon": "building", "accent": primary, "defaultPath": "/dashboard"},
            {"id": "plate_sync_admin", "label": "PlateSync Admin", "icon": "chart", "accent": primary, "defaultPath": "/admin"},
        ]

        existing = {}
        if req.generated_pages:
            try:
                existing = json.loads(req.generated_pages)
            except Exception:
                pass
        existing["preview_app"] = {
            "url": preview_url,
            "status": "ready" if ok else "failed",
            "roles": roles_out,
            "routes": ROUTES,
            "design_direction": architect.get("design_direction", ""),
        }
        existing["experience_plan"] = plan
        req.generated_pages = json.dumps(existing)
        req.updated_at = datetime.utcnow()
        db.commit()

        if ok:
            _emit(db, request_id, "done", "Generation complete!", 100)
            print(f"SUCCESS — http://localhost:5173/result/{request_id}")
        else:
            print(build_log[-3500:])
            raise SystemExit(1)
    finally:
        db.close()


if __name__ == "__main__":
    rid = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    main(rid)
