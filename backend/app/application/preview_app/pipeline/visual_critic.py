"""Post-build visual critique via screenshots."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.application.preview_app.build import run_build
from app.application.preview_app.codegen.critic import critique_file_visual, refine_file
from app.application.preview_app.parallel import parallel_map
from app.application.preview_app.safety.orchestrator import apply_workspace_guards
from app.application.preview_app.screenshot import capture_route_screenshot
from app.application.preview_app.workspace import restore_source, snapshot_source
from app.application.services.progress import emit as _emit
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.infrastructure.logging import get_logger

log = get_logger("PreviewPipeline")

MAX_VISUAL_CRITIQUE_PAGES = 6  # Screenshotting + vision-critiquing every route

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
            log.error(f"    visual critic: skip {component_file} (screenshot failed)")
            return None
        spec = specs_by_path.get(component_file) or {}
        try:
            review = critique_file_visual(
                workspace, component_file, str(shot_path),
                spec.get("instructions", ""), full_context, design_direction,
                ai_provider, template_renderer, architect,
            )
        except Exception as e:
            log.warning(f"    visual critic skip {component_file}: {e}")
            return None
        score = review.get("score", 100)
        verdict = review.get("verdict", "pass")
        log.debug(f"    visual critic {component_file}: {score} ({verdict})")
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
            log.error(f"    visual critic route error: {exc}")
            continue
        if result:
            flagged.append(result)

    try:
        import shutil
        shutil.rmtree(screenshot_dir, ignore_errors=True)
    except Exception:
        pass

    if not flagged:
        log.info("    visual critic: no pages flagged")
        return

    log.debug(f"    visual critic: refining {len(flagged)} page(s)")
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
                architect,
            )
            return component_file

        for _item, _result, exc in parallel_map(flagged, _refine_flagged, max_workers=workers):
            if exc:
                log.error(f"    visual critic refine failed: {exc}")
        ok2, _ = _rebuild_and_guard()
    except Exception as e:
        log.info(f"    visual critic refine pass raised ({e}) — rolling back")
        ok2 = False

    if ok2:
        log.info("    visual critic: rebuild OK, keeping visually-refined version")
        return

    log.error("    visual critic: rebuild failed after refinement — rolling back to pre-critique version")
    restore_source(workspace, snapshot)
    ok3, _ = _rebuild_and_guard()
    if ok3:
        log.info("    visual critic: rollback confirmed — restored version still builds")
    else:
        log.error("    visual critic: rollback rebuild ALSO failed — unexpected, workspace may be inconsistent")
