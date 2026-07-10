"""Orchestrate a fully AI-driven React preview app per business.

Pipeline (no hardcoded UI — the model designs and writes everything):
    plan (planning agent) -> architect (structure agent) -> codegen (writes files)
    -> build -> AI fix loop -> live preview
"""
from __future__ import annotations

import json
import threading
import time
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
from app.application.preview_app.assemble import find_missing_route_pages, write_app_tsx, write_index_css, write_plumbing_mock
from app.application.preview_app.build import extract_build_errors, run_build
from app.application.preview_app.codegen import (
    call_architect,
    critique_and_refine,
    critique_file_visual,
    enrich_mock_if_sparse,
    fix_build_errors,
    generate_file,
    refine_file,
    synthesize_mock_data,
)
from app.application.preview_app.fallback import (
    find_broken_paths,
    is_chrome_path,
    write_safe_stub,
    write_template_fallback,
)
from app.application.preview_app.parallel import parallel_map, split_codegen_phases
from app.application.preview_app.safety import (
    _empty_seed_state_vars,
    apply_workspace_guards,
    cleanup_page_shells,
    find_empty_seed_pages,
    find_truncated_pages,
)
from app.application.preview_app.screenshot import capture_route_screenshot
from app.application.preview_app.workspace import (
    prepare_workspace,
    read_file,
    restore_source,
    snapshot_source,
)
from app.application.services.progress import emit as _emit
from app.core.config import settings
from app.infrastructure.db.session import SessionLocal

MAX_BUILD_FIX_ATTEMPTS = 6
MAX_FILES = 40  # Overridden at runtime by settings.PREVIEW_MAX_FILES
MAX_FIX_LOOP_SECONDS = 900  # Overridden at runtime by settings.PREVIEW_MAX_FIX_LOOP_SECONDS
# beyond this, stop paying for more AI-fix attempts and drop straight to the
# deterministic regen-once-then-stub/revert safety net, which always finishes.
MAX_VISUAL_CRITIQUE_PAGES = 6  # Screenshotting + vision-critiquing every route
# (could be 15-30+ for a bigger business) is expensive — cap to the homepage
# plus each role's primary/landing page.


def _select_visual_critique_routes(architect: dict) -> list[dict]:
    """Homepage + each role's primary/landing page, capped at
    MAX_VISUAL_CRITIQUE_PAGES. Falls back to filling remaining slots from the
    full route list (in plan order) if roles don't cover the cap.
    """
    routes = architect.get("routes") or []
    by_path = {rt.get("path"): rt for rt in routes if rt.get("path")}
    selected: list[dict] = []
    seen_paths: set[str] = set()

    def _add(rt: dict | None) -> None:
        if not rt or len(selected) >= MAX_VISUAL_CRITIQUE_PAGES:
            return
        path = rt.get("path")
        if not path or path in seen_paths:
            return
        seen_paths.add(path)
        selected.append(rt)

    _add(by_path.get("/") or by_path.get("/home"))
    for role in architect.get("roles") or []:
        _add(by_path.get(role.get("defaultPath")))
    for rt in routes:
        _add(rt)

    return selected[:MAX_VISUAL_CRITIQUE_PAGES]


def _run_visual_critique(
    db: Session,
    request_id: int,
    workspace,
    architect: dict,
    plan: dict,
    specs_by_path: dict,
    full_context: str,
    manifest: dict,
    images: dict,
    brand_name: str,
    primary: str,
    secondary: str,
    font: str,
    base_path: str,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> None:
    """Post-build visual critique: screenshot the actually-built app (a real
    rendered page, not raw source) and feed each screenshot to a
    vision-capable critic. Flagged pages get refined and the app rebuilt
    ONCE — a secondary polish pass, not the primary 6-attempt fix-loop. If
    that rebuild fails, the pre-critique snapshot is restored and rebuilt
    again to confirm the previously-working version still serves — visual
    "improvement" must never be able to take a working preview and ship a
    broken one instead. Every failure mode here degrades to "keep whatever
    was already built", never raises.
    """
    routes = _select_visual_critique_routes(architect)
    if not routes:
        return

    design_direction = architect.get("design_direction", "")
    screenshot_dir = workspace / "_visual_critique_shots"
    base_url = f"{settings.INTERNAL_BASE_URL}{base_path}/"
    workers = max(1, settings.PREVIEW_PARALLEL_WORKERS)

    def _review_route(item: tuple[int, dict]) -> tuple[str, str, dict] | None:
        i, rt = item
        route_path = rt.get("path") or "/"
        component_file = (rt.get("component_file") or "").replace("\\", "/")
        if not component_file:
            return None
        shot_path = screenshot_dir / f"shot_{i}.png"
        if not capture_route_screenshot(base_url, route_path, shot_path):
            print(f"    visual critic: skip {component_file} (screenshot failed)", flush=True)
            return None
        spec = specs_by_path.get(component_file) or {}
        try:
            review = critique_file_visual(
                workspace, component_file, str(shot_path),
                spec.get("instructions", ""), full_context, design_direction,
                ai_provider, template_renderer,
            )
        except Exception as e:
            print(f"    visual critic skip {component_file}: {e}", flush=True)
            return None
        score = review.get("score", 100)
        verdict = review.get("verdict", "pass")
        print(f"    visual critic {component_file}: {score} ({verdict})", flush=True)
        if verdict != "revise":
            return None
        notes = review.get("revision_instructions") or "; ".join(review.get("issues", []))
        if not notes:
            return None
        return component_file, notes, spec

    indexed_routes = list(enumerate(routes, 1))
    _emit(db, request_id, "visual_critic",
          f"Visually reviewing {len(indexed_routes)} page(s) in parallel...", 90,
          detail=f"workers={workers}")

    flagged: list[tuple[str, str, dict]] = []
    done = 0
    for _item, result, exc in parallel_map(
        indexed_routes,
        _review_route,
        max_workers=workers,
        on_done=lambda d, tot, item, _res, _exc: None,
    ):
        done += 1
        i, rt = _item
        _emit(db, request_id, "visual_critic",
              f"Visually reviewed {done}/{len(indexed_routes)}: {rt.get('title', rt.get('path', ''))}", 90,
              detail=rt.get("path") or "/")
        if exc:
            print(f"    visual critic route error: {exc}", flush=True)
            continue
        if result:
            flagged.append(result)

    try:
        import shutil
        shutil.rmtree(screenshot_dir, ignore_errors=True)
    except Exception:
        pass

    if not flagged:
        print("    visual critic: no pages flagged", flush=True)
        return

    print(f"    visual critic: refining {len(flagged)} page(s)", flush=True)
    _emit(db, request_id, "visual_critic",
          f"Applying visual fixes to {len(flagged)} page(s)...", 91)
    snapshot = snapshot_source(workspace)

    def _rebuild_and_guard() -> tuple[bool, str]:
        apply_workspace_guards(
            workspace, architect, plan, images, brand_name, primary, secondary, font, template_renderer,
        )
        return run_build(workspace, base_path, template_renderer)

    try:
        def _refine_flagged(item: tuple[str, str, dict]) -> str:
            component_file, notes, spec = item
            refine_file(
                workspace, component_file, spec.get("instructions", ""), notes,
                full_context, manifest, images, ai_provider, template_renderer,
            )
            return component_file

        for _item, _result, exc in parallel_map(flagged, _refine_flagged, max_workers=workers):
            if exc:
                print(f"    visual critic refine failed: {exc}", flush=True)
        ok2, _ = _rebuild_and_guard()
    except Exception as e:
        print(f"    visual critic refine pass raised ({e}) — rolling back", flush=True)
        ok2 = False

    if ok2:
        print("    visual critic: rebuild OK, keeping visually-refined version", flush=True)
        return

    print("    visual critic: rebuild failed after refinement — rolling back to pre-critique version", flush=True)
    restore_source(workspace, snapshot)
    ok3, _ = _rebuild_and_guard()
    if ok3:
        print("    visual critic: rollback confirmed — restored version still builds", flush=True)
    else:
        print("    visual critic: rollback rebuild ALSO failed — unexpected, workspace may be inconsistent", flush=True)


def _sort_gen_order(files: list[dict]) -> list[dict]:
    """Generate foundational files first so later files can import them."""
    kind_order = {"theme": 0, "data": 1, "component": 2, "layout": 3, "page": 4, "router": 5}
    return sorted(files, key=lambda f: (kind_order.get(f.get("kind", ""), 4), f.get("path", "")))


def _attach_plan_sections(files: list[dict], plan: dict, architect: dict | None = None) -> list[dict]:
    """Feed each page's plan spec (sections + features) into its codegen instructions."""
    page_specs: dict[str, dict] = {}
    path_to_page: dict[str, dict] = {}
    for role in plan.get("roles", []):
        for page in role.get("pages", []):
            pid = page.get("id", "")
            if pid:
                enriched = {**page, "role_id": role.get("id"), "role_label": role.get("label")}
                page_specs[pid] = enriched
    if architect:
        for rt in architect.get("routes") or []:
            pid = rt.get("page_id") or ""
            cf = (rt.get("component_file") or "").replace("\\", "/")
            if pid and pid in page_specs and cf:
                path_to_page[cf.lower()] = page_specs[pid]

    out: list[dict] = []
    for f in files:
        spec = dict(f)
        fpath = (spec.get("path") or "").replace("\\", "/").lower()
        page = path_to_page.get(fpath)
        if not page:
            for pid, pg in page_specs.items():
                path = fpath.replace("-", "").replace("_", "")
                if pid and pid.replace("-", "").replace("_", "") in path:
                    page = pg
                    break
        if page:
            sections = page.get("sections") or []
            sec_text = json.dumps(sections[:20], ensure_ascii=False)[:4000]
            spec["instructions"] = (
                f"{spec.get('instructions', '')}\n\n"
                f"Role: {page.get('role_label') or page.get('role_id', '')}\n"
                f"Page: {page.get('title')} — {page.get('purpose', '')}\n"
                f"Sections to implement (build EVERY one — do not add sections not listed here):\n{sec_text}\n"
                f"Features to showcase: {', '.join(page.get('features_to_showcase', []))}\n"
                f"Sample data notes: {page.get('sample_data_notes', '')}"
            )
        out.append(spec)
    return out


def _files_from_plan(architect: dict) -> list[dict]:
    """If the architect didn't return a file list, derive it from its routes."""
    files: list[dict] = [
        {"path": "src/index.css", "kind": "theme",
         "instructions": "Tailwind v4 @theme with brand colors + font from the design system"},
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


# Nav/Layout/icon-set were previously excluded from generation entirely and
# copied verbatim from the static template for every business. They're now
# AI-authored per brand (contracts enforced in codegen.py's _CHROME_CONTRACTS
# and reverted-to-template on repeated build failure — see fallback.py), so
# every architect run must always plan them, even if the model forgets to.
_CHROME_DEFAULTS: dict[str, tuple[str, str]] = {
    "src/components/Nav.tsx": (
        "component",
        "Public top nav bar for this brand — typography, spacing, button shape and "
        "color usage should feel specific to this business, not generic.",
    ),
    "src/layouts/PublicLayout.tsx": (
        "layout",
        "Public site shell (header + main + footer) wrapping every public page. "
        "Footer copy and structure should suit this business.",
    ),
    "src/layouts/AdminLayout.tsx": (
        "layout",
        "Admin dashboard shell (sidebar + header) wrapping every admin page. Never "
        "hardcode a business type in labels (e.g. do not assume 'Studio').",
    ),
    "src/components/UiIcons.tsx": (
        "component",
        "A small bespoke icon set (10-14 icons) matching this brand's visual style "
        "(stroke width, corner rounding), covering the icon keys pages already use.",
    ),
}


def _normalize_architect(architect: dict, plan: dict) -> dict:
    files = architect.get("files_to_generate") or []
    if not files:
        files = _files_from_plan(architect)

    # Merge shared_components (Nav, layouts, icon set) into the same generation
    # list — the architect prompt plans them as a separate field, but everything
    # needs to flow through the one AI-authored files_to_generate pipeline.
    existing_paths = {(f.get("path") or "").lower().replace("\\", "/") for f in files}
    for comp in architect.get("shared_components") or []:
        cp = (comp.get("path") or "").lower().replace("\\", "/")
        if cp and cp not in existing_paths:
            files.append({
                "path": comp["path"],
                "kind": comp.get("kind", "component"),
                "instructions": comp.get("instructions", ""),
            })
            existing_paths.add(cp)

    # Guarantee the shared chrome always gets AI-authored, even if the
    # architect's own plan omitted it.
    for path, (kind, instr) in _CHROME_DEFAULTS.items():
        norm = path.lower()
        if norm not in existing_paths:
            files.append({"path": path, "kind": kind, "instructions": instr})
            existing_paths.add(norm)

    # Guarantee every route has a matching file entry — no page ever skipped
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

    architect["files_to_generate"] = _attach_plan_sections(files, plan, architect)

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
    _emit(db, request_id, "codegen", "Build workspace ready", 41,
          detail=str(workspace))
    brand_name = (
        (manifest.get("brand") or {}).get("name")
        if isinstance(manifest.get("brand"), dict)
        else None
    ) or manifest.get("brand_name") or req.business_name or "Brand"
    write_plumbing_mock(workspace, architect, images, brand_name, primary, secondary)
    print("    plumbing mock (brand, roles, nav) ready", flush=True)

    # App.tsx/index.css/mock.ts stay assembler-owned (routing + theme wiring +
    # data plumbing are deterministic). Nav/Layouts/UiIcons are NOT skipped
    # anymore — they're AI-authored per brand now (see _CHROME_DEFAULTS above
    # and _CHROME_CONTRACTS in codegen.py), with a template-revert safety net
    # in the final build-stabilization step below if they keep breaking.
    _skip = {"src/app.tsx", "src/index.css", "src/data/mock.ts"}
    all_files = [
        f for f in architect.get("files_to_generate", [])
        if (f.get("path") or "").lower().replace("\\", "/") not in _skip
    ]
    files_to_gen = _sort_gen_order(all_files[: settings.PREVIEW_MAX_FILES])
    total_files = len(files_to_gen)
    workers = settings.PREVIEW_PARALLEL_WORKERS
    max_fix_attempts = settings.PREVIEW_MAX_BUILD_FIX_ATTEMPTS
    max_fix_seconds = settings.PREVIEW_MAX_FIX_LOOP_SECONDS
    print(
        f"  [4/6] Codegen agent — {total_files} files "
        f"(cap={settings.PREVIEW_MAX_FILES}, workers={workers})...",
        flush=True,
    )
    _emit(
        db,
        request_id,
        "codegen",
        f"Generating {total_files} files (workers={workers})...",
        42,
        detail="Starting code generation",
        files_done=0,
        files_total=total_files,
    )
    generated_ok = 0
    page_ok = 0
    specs_by_path = {f.get("path", ""): f for f in files_to_gen}
    progress_lock = threading.RLock()
    files_completed = 0

    def _emit_codegen_progress(path: str, done: int, *, started: bool = False) -> None:
        short_path = path.replace("src/pages/", "").replace("src/components/", "").replace("src/", "")
        pct = 42 + int((done / max(total_files, 1)) * 36)
        label = f"{'Starting' if started else 'Generated'}: {short_path}"
        # Never hold progress_lock across SQLite I/O — that deadlocked the pool
        # when the pipeline session also touched the same DB.
        thread_db = SessionLocal()
        try:
            _emit(thread_db, request_id, "codegen",
                  label, pct,
                  detail=path,
                  files_done=done,
                  files_total=total_files)
        finally:
            thread_db.close()

    def _release_pipeline_db() -> None:
        """Drop any open SQLite transaction on the request session before workers run."""
        try:
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
        try:
            db.expire_all()
        except Exception:
            pass

    def _generate_spec(spec: dict) -> str:
        path = spec.get("path", "?")
        print(f"    >> begin {path}", flush=True)
        _emit_codegen_progress(path, files_completed, started=True)
        try:
            generate_file(
                workspace, spec, full_context, architect, plan, manifest, images,
                ai_provider, template_renderer,
            )
            print(f"    << done {path}", flush=True)
            return path
        except Exception as exc:
            print(f"    << fail {path}: {exc}", flush=True)
            raise

    def _run_batch(label: str, batch: list[dict], *, parallel: bool) -> tuple[int, int]:
        nonlocal files_completed, generated_ok, page_ok
        if not batch:
            return 0, 0
        ok_count = 0
        page_count = 0
        if parallel and workers > 1 and len(batch) > 1:
            print(f"    {label}: {len(batch)} files in parallel (workers={workers})", flush=True)
            _release_pipeline_db()

            def _on_file_done(done: int, _total: int, spec: dict, result, exc) -> None:
                nonlocal files_completed, generated_ok, page_ok, ok_count, page_count
                path = spec.get("path", "?")
                with progress_lock:
                    files_completed += 1
                    done_now = files_completed
                _emit_codegen_progress(path, done_now)
                if exc:
                    print(f"    FAIL {path}: {exc}", flush=True)
                else:
                    generated_ok += 1
                    ok_count += 1
                    if spec.get("kind") == "page":
                        page_ok += 1
                        page_count += 1
                    print(f"    OK {path}", flush=True)

            parallel_map(batch, _generate_spec, max_workers=workers, on_done=_on_file_done)
        else:
            for spec in batch:
                path = spec.get("path", "?")
                with progress_lock:
                    files_completed += 1
                    done_now = files_completed
                _emit_codegen_progress(path, done_now)
                print(f"    -> [{done_now}/{total_files}] {path}", flush=True)
                try:
                    generate_file(
                        workspace, spec, full_context, architect, plan, manifest, images,
                        ai_provider, template_renderer,
                    )
                    generated_ok += 1
                    ok_count += 1
                    if spec.get("kind") == "page":
                        page_ok += 1
                        page_count += 1
                    print(f"    OK {path}", flush=True)
                except Exception as e:
                    print(f"    FAIL {path}: {e}", flush=True)
        return ok_count, page_count

    foundation, components, pages = split_codegen_phases(files_to_gen)
    # Parallelize every codegen phase — OpenRouter calls are network-bound.
    _run_batch("foundation", foundation, parallel=True)
    _run_batch("components", components, parallel=True)
    _run_batch("pages", pages, parallel=True)

    def _regenerate_truncated(label: str) -> list[str]:
        truncated = find_truncated_pages(workspace)
        if not truncated:
            return []
        specs = [
            specs_by_path.get(rel) or {"path": rel, "kind": "page", "instructions": rel}
            for rel in truncated
        ]
        print(f"    {label}: regenerating {len(specs)} truncated file(s)", flush=True)

        def _regen_spec(spec: dict) -> str:
            path = spec.get("path", "")
            print(f"    {label} regenerating truncated: {path}", flush=True)
            _generate_spec(spec)
            return path

        regen: list[str] = []
        if workers > 1 and len(specs) > 1:
            for spec, result, exc in parallel_map(specs, _regen_spec, max_workers=workers):
                path = spec.get("path", "")
                if exc:
                    print(f"    {label} FAIL {path}: {exc}", flush=True)
                else:
                    regen.append(path)
        else:
            for spec in specs:
                path = spec.get("path", "")
                try:
                    _regen_spec(spec)
                    regen.append(path)
                except Exception as e:
                    print(f"    {label} FAIL {path}: {e}", flush=True)
        return regen

    regen = _regenerate_truncated("post-codegen")
    if regen:
        print(f"    re-generated {len(regen)} truncated file(s)", flush=True)

    missing_specs = find_missing_route_pages(workspace, architect)
    if missing_specs:
        print(f"    generating {len(missing_specs)} missing route page(s)...", flush=True)
        _run_batch("missing-routes", missing_specs, parallel=True)

    if generated_ok == 0 or page_ok == 0:
        raise RuntimeError(
            f"Codegen produced no usable files (ok={generated_ok}, pages={page_ok}). "
            "Refusing to serve the blank template as a finished preview."
        )

    if synthesize_mock_data(
        workspace, full_context, plan, manifest, images, architect, ai_provider, template_renderer,
    ):
        print("    mock.ts synthesized from page imports", flush=True)

    if settings.PREVIEW_SKIP_CRITIC:
        print("  [5/6] Design critic skipped (PREVIEW_SKIP_CRITIC=true)", flush=True)
    else:
        _emit(db, request_id, "critic",
              f"AI design critic reviewing {page_ok} pages...", 80,
              detail="Checking quality, consistency, and UX")
        print("  [5/6] Design critic — reviewing + refining pages...", flush=True)
        design_direction = architect.get("design_direction", "")

        def _critic_heartbeat(i: int, total: int, path: str) -> None:
            short = path.replace("src/pages/", "").replace("src/", "")
            pct = 80 + int((i / max(total, 1)) * 4)
            _emit(db, request_id, "critic",
                  f"Reviewing page {i}/{total}: {short}", pct,
                  detail="Checking quality, consistency, and UX")

        try:
            refined = critique_and_refine(
                workspace, files_to_gen, full_context, design_direction, manifest, images,
                ai_provider, template_renderer, on_progress=_critic_heartbeat,
            )
            print(f"    refined {len(refined)} page(s)", flush=True)
            _emit(db, request_id, "critic",
                  f"Critic refined {len(refined)} page(s)", 84,
                  detail="Applying design improvements")
            regen_critic = _regenerate_truncated("post-critic")
            if regen_critic:
                print(f"    critic pass left {len(regen_critic)} truncated — re-generated", flush=True)
        except Exception as e:
            print(f"    critic pass skipped: {e}", flush=True)

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
        print(f"    empty-seed guard skipped: {e}", flush=True)
    if empty_seed:
        print(
            f"    empty-seed guard: {len(empty_seed)} page(s) render with no seed data: "
            f"{', '.join(empty_seed)}", flush=True,
        )
        reinforced_specs = []
        for rel in empty_seed:
            base_spec = specs_by_path.get(rel) or {"path": rel, "kind": "page", "instructions": rel}
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
            _run_batch("empty-seed-fix", reinforced_specs, parallel=True)
            still_empty = find_empty_seed_pages(workspace)
            if still_empty:
                print(
                    f"    empty-seed guard: {len(still_empty)} page(s) still empty after regen: "
                    f"{', '.join(still_empty)}", flush=True,
                )
        except Exception as e:
            print(f"    empty-seed regen failed: {e}", flush=True)

    stripped = cleanup_page_shells(workspace)
    if stripped:
        print(f"    removed duplicate nav from: {', '.join(stripped)}", flush=True)

    brand_name = (
        (manifest.get("brand") or {}).get("name")
        if isinstance(manifest.get("brand"), dict)
        else None
    ) or manifest.get("brand_name") or req.business_name or "Brand"
    font = design_system.get("font_family") or design_system.get("font") or manifest.get("font", "")

    def _pre_build_fixups() -> None:
        """Deterministic guards re-applied before every single build attempt."""
        actions = apply_workspace_guards(
            workspace, architect, plan, images, brand_name, primary, secondary, font, template_renderer,
        )
        if actions:
            print(f"    guards: {', '.join(actions[:8])}{'...' if len(actions) > 8 else ''}", flush=True)

    _pre_build_fixups()
    print("    assembled router + theme", flush=True)

    base_path = f"/api/preview-apps/{request_id}"
    _emit(db, request_id, "build", "Compiling React app...", 86,
          detail="Running Vite build")
    print("  [6/6] Building + AI fix loop...", flush=True)
    ok, build_log = run_build(workspace, base_path, template_renderer)
    attempt = 0
    fix_loop_start = time.monotonic()
    while not ok and attempt < max_fix_attempts:
        # Native/tooling failures can't be patched by the LLM — skip straight to fallbacks.
        infra_markers = (
            "Cannot find native binding",
            "@rolldown/binding-",
            "Vite requires Node.js version",
            "vite not installed after npm install",
        )
        if any(m in build_log for m in infra_markers):
            print("    build tooling/native error — skipping AI fix loop", flush=True)
            break
        elapsed = time.monotonic() - fix_loop_start
        if elapsed > max_fix_seconds:
            print(
                f"    fix loop budget exceeded ({elapsed:.0f}s > {max_fix_seconds}s) — "
                "stopping AI fix attempts, dropping to the guaranteed-safe fallback", flush=True,
            )
            _emit(db, request_id, "build",
                  "Fix attempts taking too long — applying safe fallback instead...", 87)
            break
        attempt += 1
        _emit(db, request_id, "build",
              f"Fixing build errors (attempt {attempt}/{max_fix_attempts})...", 87,
              detail="AI is patching compilation errors")
        print(f"    fix attempt {attempt}/{max_fix_attempts}...", flush=True)
        errors = extract_build_errors(build_log)
        try:
            fixed = fix_build_errors(workspace, errors, architect, ai_provider, template_renderer)
            print(f"    patched: {', '.join(fixed) or 'none'}", flush=True)
        except Exception as e:
            print(f"    fix agent failed: {e} — retrying next attempt", flush=True)
            # Don't break — the next attempt re-extracts errors and tries again
        _pre_build_fixups()
        ok, build_log = run_build(workspace, base_path, template_renderer)

    if not ok:
        # Regenerate broken/truncated pages (and any broken chrome file) once
        # before falling back to stubs/template-revert.
        candidate_paths = [
            f.get("path", "") for f in files_to_gen
            if f.get("kind") == "page" or is_chrome_path(f.get("path", ""))
        ]
        errors = extract_build_errors(build_log)
        broken = find_broken_paths(errors, candidate_paths) or find_broken_paths(build_log, candidate_paths)
        broken = list(dict.fromkeys(broken + find_truncated_pages(workspace)))
        if broken:
            _emit(db, request_id, "build",
                  f"Regenerating {len(broken)} broken page(s)...", 88,
                  detail="Re-running codegen on failed pages")
            print(f"    regenerating broken pages: {', '.join(broken)}", flush=True)
            regen_specs = [
                specs_by_path.get(path) or {"path": path, "kind": "page", "instructions": path}
                for path in broken
            ]

            def _regen_broken(spec: dict) -> str:
                _generate_spec(spec)
                return spec.get("path", "")

            if workers > 1 and len(regen_specs) > 1:
                for spec, _, exc in parallel_map(regen_specs, _regen_broken, max_workers=workers):
                    if exc:
                        print(f"    regen FAIL {spec.get('path')}: {exc}", flush=True)
            else:
                for spec in regen_specs:
                    path = spec.get("path", "")
                    try:
                        _regen_broken(spec)
                    except Exception as e:
                        print(f"    regen FAIL {path}: {e}", flush=True)
            _pre_build_fixups()
            ok, build_log = run_build(workspace, base_path, template_renderer)

    if not ok:
        # Final safety net: stabilize only files that still fail — never wipe
        # the whole app. Chrome files (Nav/Layout/UiIcons) revert to the known-
        # good static template instead of a generic page stub, since a stub's
        # shape (a centered placeholder block) would break every page that
        # depends on them rendering a real nav/layout/icon lookup.
        candidate_paths = [
            f.get("path", "") for f in files_to_gen
            if f.get("kind") == "page" or is_chrome_path(f.get("path", ""))
        ]
        for stub_round in range(1, 3):
            errors = extract_build_errors(build_log)
            broken = find_broken_paths(errors, candidate_paths) or find_broken_paths(build_log, candidate_paths)
            if not broken:
                broken = [p for p in find_truncated_pages(workspace) if p in candidate_paths]
            if not broken:
                break
            _emit(db, request_id, "build",
                  f"Stabilizing {len(broken)} page(s) (round {stub_round}/2)...", 88,
                  detail="Applying guaranteed-safe fallback content")
            print(f"    stabilizing {len(broken)} page(s): {', '.join(broken)}", flush=True)
            for path in broken:
                if is_chrome_path(path):
                    if not write_template_fallback(workspace, path):
                        write_safe_stub(workspace, path)
                else:
                    write_safe_stub(workspace, path)
            _pre_build_fixups()
            ok, build_log = run_build(workspace, base_path, template_renderer)
            if ok:
                print(f"    stabilized — build now succeeds", flush=True)
                break

    if ok:
        _emit(db, request_id, "build_done", "Preview app compiled successfully!", 89,
              detail=f"{total_files} pages built and live")
    else:
        _emit(db, request_id, "build_failed", "Build failed — falling back to role pages", 89)

    # Post-build visual critique: only ever runs against a build that's
    # already succeeded (never a broken one), and is wrapped in its own
    # try/except on top of the guards already inside it — a failure here must
    # degrade to "keep whatever was already built", never take down the
    # whole request.
    if ok and not settings.PREVIEW_SKIP_VISUAL_CRITIC:
        print("  [7/7] Visual critique — screenshotting + reviewing rendered pages...", flush=True)
        _emit(db, request_id, "visual_critic", "AI visually reviewing the built app...", 90,
              detail="Screenshotting pages and checking rendering quality")
        try:
            _run_visual_critique(
                db, request_id, workspace, architect, plan, specs_by_path, full_context,
                manifest, images, brand_name, primary, secondary, font, base_path,
                ai_provider, template_renderer,
            )
        except Exception as e:
            print(f"    visual critique stage failed entirely, keeping existing build: {e}", flush=True)
    elif ok:
        print("    visual critique skipped (PREVIEW_SKIP_VISUAL_CRITIC=true)", flush=True)

    preview_url = f"{base_path}/" if ok else None
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
        raise RuntimeError(f"Preview app build failed after {max_fix_attempts} fix attempts")

    return result
