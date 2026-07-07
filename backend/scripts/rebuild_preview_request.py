"""Sanitize generated source files and re-run build + fix for an existing preview workspace."""
import json
import sys

sys.path.insert(0, ".")

from app.application.preview_app.build import extract_build_errors, run_build
from app.application.preview_app.codegen import _strip_fences, fix_build_errors
from app.application.preview_app.assemble import write_app_tsx, write_index_css
from app.application.preview_app.safety import ensure_mock_exports
from app.application.preview_app.workspace import get_workspace, list_source_files, read_file, write_file
from app.application.preview_app.pipeline import MAX_BUILD_FIX_ATTEMPTS
from app.application.services.industry_images import get_images_for_industry
from app.domain.models.request import Request
from app.infrastructure.ai_providers.factory import get_ai_provider
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.templating.renderer import get_template_renderer


def _sanitize_workspace(workspace) -> list[str]:
    """Strip markdown prose/fences from any generated source file."""
    fixed: list[str] = []
    for path in list_source_files(workspace):
        if not path.endswith((".tsx", ".ts", ".css")):
            continue
        raw = read_file(workspace, path)
        cleaned = _strip_fences(raw)
        if cleaned != raw.strip():
            write_file(workspace, path, cleaned)
            fixed.append(path)
    return fixed


def _architect_from_request(req: Request, gp: dict) -> dict:
    pa = gp.get("preview_app") or {}
    return {
        "routes": pa.get("routes") or [],
        "roles": pa.get("roles") or [],
        "design_direction": pa.get("design_direction") or "",
        "files_to_generate": [],
    }


def main(request_id: int) -> None:
    db = SessionLocal()
    ai = get_ai_provider()
    renderer = get_template_renderer()
    try:
        req = db.query(Request).filter(Request.id == request_id).first()
        if not req:
            raise SystemExit(f"Request {request_id} not found")

        gp = json.loads(req.generated_pages or "{}")
        plan = gp.get("experience_plan") or {}
        architect = _architect_from_request(req, gp)
        workspace = get_workspace(request_id)
        if not workspace.is_dir():
            raise SystemExit(f"Workspace missing: {workspace}")

        sanitized = _sanitize_workspace(workspace)
        print(f"Sanitized {len(sanitized)} file(s):", ", ".join(sanitized) or "none")

        demo: dict = {}
        if req.visual_demo_json:
            try:
                demo = json.loads(req.visual_demo_json)
            except Exception:
                pass
        theme = demo.get("visual_theme", {})
        primary = theme.get("primary_color", "#6366f1")
        secondary = theme.get("secondary_color", "#0d9488")
        design_system = plan.get("design_system") or {}
        font = design_system.get("font_family") or design_system.get("font") or ""
        images = get_images_for_industry(req.industry or "")
        brand_name = req.business_name or "Brand"

        write_index_css(workspace, primary, secondary, font, renderer)
        write_app_tsx(workspace, architect, renderer)

        base_path = f"/api/preview-apps/{request_id}"
        ok, build_log = run_build(workspace, base_path, renderer)
        attempt = 0
        while not ok and attempt < MAX_BUILD_FIX_ATTEMPTS:
            attempt += 1
            print(f"Fix attempt {attempt}/{MAX_BUILD_FIX_ATTEMPTS}...")
            errors = extract_build_errors(build_log)
            try:
                patched = fix_build_errors(workspace, errors, architect, ai, renderer)
                print(f"  patched: {', '.join(patched) or 'none'}")
                ensure_mock_exports(workspace, architect, plan, images, brand_name)
                write_index_css(workspace, primary, secondary, font, renderer)
                write_app_tsx(workspace, architect, renderer)
            except Exception as e:
                print(f"  fix agent failed: {e}")
            ok, build_log = run_build(workspace, base_path, renderer)

        preview_url = f"{base_path}/" if ok else None
        pa = gp.get("preview_app") or {}
        pa["url"] = preview_url
        pa["status"] = "ready" if ok else "failed"
        gp["preview_app"] = pa
        req.generated_pages = json.dumps(gp)
        db.commit()

        if ok:
            print(f"SUCCESS — preview ready at {preview_url}")
        else:
            print("FAIL — build still broken after fix attempts")
            print(build_log[-3000:])
            raise SystemExit(1)
    finally:
        db.close()


if __name__ == "__main__":
    rid = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    main(rid)
