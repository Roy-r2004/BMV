"""Preview pipeline — AppSpec workspace validation, stub tracking, persisting
generated_pages, emitting ready/failed, and returning the result dict.
"""
from __future__ import annotations

import json
import time
from datetime import datetime

from app.application.appspec.hooks import (
    ensure_workspace_appspec_hooks,
    page_hooks_present,
)
from app.application.appspec.repository import app_spec_provenance
from app.application.appspec.workspace_validation import validate_app_spec_workspace
from app.application.preview_app.fallback import (
    clear_stubbed_path,
    consume_stubbed_paths,
    record_stubbed_path,
)
from app.application.preview_app.pipeline.architect_normalize import _plan_for_persistence
from app.application.preview_app.pipeline.context import PipelineContext
from app.application.preview_app.pipeline.errors import PreviewAppContractError
from app.application.preview_app.workspace import read_file
from app.application.services.progress import emit as _emit
from app.infrastructure.logging import get_logger
from app.infrastructure.logging.diagnostics import dump_pipeline_summary, summarize_workspace_debug

log = get_logger("PreviewPipeline")


def run_finalize(ctx: PipelineContext) -> dict:
    db = ctx.db
    request_id = ctx.request_id
    req = ctx.req
    workspace = ctx.workspace
    architect = ctx.architect
    plan = ctx.plan
    ok = ctx.ok

    app_spec_workspace_issues: list[str] = []
    if ok and ctx.enforce_app_spec and ctx.app_spec_result and ctx.app_spec_scope:
        # Heal missing hooks after visual refine / scaffolds so finalize does
        # not hard-fail on prompt-missed data-appspec-* attributes.
        try:
            healed = ensure_workspace_appspec_hooks(
                workspace,
                ctx.app_spec_result.spec,
                ctx.app_spec_scope,
                architect,
            )
            if healed:
                log.info(
                    "    appspec hooks injected: %s%s",
                    ", ".join(healed[:8]),
                    "..." if len(healed) > 8 else "",
                )
        except Exception as e:
            log.warning("    appspec hook injection skipped: %s", e)
        app_spec_workspace_issues = validate_app_spec_workspace(
            workspace,
            ctx.app_spec_result.spec,
            ctx.app_spec_scope,
            architect,
        )
        # #region agent log
        try:
            from app.application.preview_app.pipeline.debug_ndjson import agent_dbg

            agent_dbg(
                "F",
                "finalize.py:appspec_hooks",
                "post-inject appspec validation",
                {
                    "request_id": request_id,
                    "issue_count": len(app_spec_workspace_issues),
                    "issues_sample": app_spec_workspace_issues[:6],
                },
            )
        except Exception:
            pass
        # #endregion
        if app_spec_workspace_issues:
            ok = False
            _emit(
                db,
                request_id,
                "contract_failed",
                "Preview is missing required AppSpec interaction evidence",
                92,
                detail="; ".join(app_spec_workspace_issues[:6]),
            )

    accent = ctx.design_system.get("primary_color") or ctx.manifest.get("accent") or ctx.primary
    architect_roles = architect.get("roles") or []
    route_list = architect.get("routes") or []
    pages_by_id = (
        {page.id: page for page in ctx.app_spec_result.spec.pages}
        if ctx.app_spec_result
        else {}
    )
    for route in route_list:
        component_file = (route.get("component_file") or "").replace("\\", "/")
        if not component_file or not route.get("skeleton_id"):
            continue
        source = read_file(workspace, component_file)
        if "deterministic catalogue contract scaffold" not in source:
            clear_stubbed_path(workspace, component_file)
            continue
        page_id = str(route.get("app_spec_page_id") or route.get("page_id") or "")
        page = pages_by_id.get(page_id)
        action_ids = list(page.action_ids) if page else list(route.get("action_ids") or [])
        evidence_ids = (
            list(page.evidence_ids) if page else list(route.get("evidence_ids") or [])
        )
        # Catalogue scaffolds with full AppSpec hooks are acceptable fallbacks
        # under enforcement — they still compile and are browser-addressable.
        if (
            ctx.enforce_app_spec
            and page_id
            and page_hooks_present(
                source,
                page_id=page_id,
                action_ids=action_ids,
                evidence_ids=evidence_ids,
            )
        ):
            clear_stubbed_path(workspace, component_file)
        else:
            record_stubbed_path(workspace, component_file)

    fallback_pages = consume_stubbed_paths(workspace)
    if ctx.enforce_app_spec and fallback_pages:
        ok = False
        _emit(
            db,
            request_id,
            "contract_failed",
            "Preview compiled only with fallback pages",
            92,
            detail=", ".join(fallback_pages[:8]),
        )
    preview_url = f"{ctx.base_path}/" if ok else None
    if ok:
        log.info("  OK Preview built: %s", preview_url)
    else:
        log.error("  FAIL build for request %s — see .bmv-debug/", request_id)
        dump_pipeline_summary(
            workspace,
            request_id=request_id,
            ok=False,
            build_log=ctx.build_log,
            notes=[
                f"fix_attempts={ctx.attempt}",
                f"fallback_pages={fallback_pages}",
                f"app_spec_issues={app_spec_workspace_issues}",
            ],
        )
        debug_report = summarize_workspace_debug(workspace)
        for issue in debug_report.get("top_issues", [])[:8]:
            log.error("  debug: %s", issue)
    if ctx.pipeline_watch is not None:
        ctx.pipeline_watch.stop()

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

    persisted_plan = _plan_for_persistence(plan)
    result = {
        "preview_app": {
            "url": preview_url,
            "status": "ready" if ok else "failed",
            "roles": roles_out,
            "routes": route_list,
            "design_direction": architect.get("design_direction", ""),
            "fallback_pages": fallback_pages,
            # Remount host iframe past sticky error boundaries after rebuilds.
            "built_at": int(time.time()),
        },
        "experience_plan": persisted_plan,
    }

    existing: dict = {}
    if req.generated_pages:
        try:
            existing = json.loads(req.generated_pages)
        except Exception:
            pass
    existing["preview_app"] = result["preview_app"]
    existing["experience_plan"] = persisted_plan
    if ctx.app_spec_result:
        existing["app_spec_ref"] = {
            **app_spec_provenance(ctx.app_spec_result.revision_record),
            "enforced": ctx.enforce_app_spec,
        }
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
        if ctx.enforce_app_spec:
            reason = (
                "Required AppSpec preview contains fallback/stub pages: "
                + ", ".join(fallback_pages)
                if fallback_pages
                else (
                    "Required AppSpec preview is missing contract hooks: "
                    + "; ".join(app_spec_workspace_issues)
                    if app_spec_workspace_issues
                    else "Required AppSpec preview did not compile successfully."
                )
            )
            _emit(db, request_id, "failed", reason, 100)
            raise PreviewAppContractError(reason)
        # Do not raise — the UI already has status=failed. Raising caused the
        # background worker to emit a second "Generation failed" and made
        # concurrent runs look like hard crashes even after fallbacks ran.
        log.warning(
            f"  WARN preview {request_id} finished without a successful Vite build "
            f"after {ctx.max_fix_attempts} fix attempts — status marked failed"
        )
        _emit(db, request_id, "failed", "Preview build could not complete — try Generate again", 100)
        return result

    # Stay below tech (90) / proposal (95) / done (100) so the customer bar
    # does not jump backward after the live preview becomes available.
    _emit(db, request_id, "ready", "Live preview ready!", 88,
          detail=preview_url or "")
    return result
