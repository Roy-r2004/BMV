"""Preview pipeline — AppSpec workspace validation, stub tracking, persisting
generated_pages, emitting ready/failed, and returning the result dict.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from app.application.appspec.hooks import (
    ensure_workspace_appspec_hooks,
    page_hooks_present,
)
from app.application.appspec.repository import app_spec_provenance
from app.application.appspec.workspace_validation import validate_app_spec_workspace
from app.application.preview_app.ai_feature_surfaces import (
    AI_HUB_COMPONENT,
    assert_ai_features_present,
    ensure_ai_feature_surfaces,
)
from app.application.preview_app.brand_brief import resolve_preview_brand_name
from app.application.preview_app.fallback import (
    clear_stubbed_path,
    consume_stubbed_paths,
    record_stubbed_path,
)
from app.application.preview_app.host_role_ux import role_tagline
from app.application.preview_app.pipeline.architect_normalize import _plan_for_persistence
from app.application.preview_app.pipeline.context import PipelineContext
from app.application.preview_app.pipeline.errors import PreviewAppContractError
from app.application.preview_app.quality_gate import run_quality_gate_with_heal
from app.application.preview_app.source_quality import catalogue_page_is_thin
from app.application.preview_app.workspace import read_file
from app.application.services.ai_features import ai_features_from_request
from app.application.services.progress import emit as _emit
from app.infrastructure.logging import get_logger
from app.infrastructure.logging.diagnostics import dump_pipeline_summary, summarize_workspace_debug

log = get_logger("PreviewPipeline")


def _finalize_brand_name(ctx: PipelineContext) -> str:
    """Write-site brand for AI hub / quality gate — never invent mid-finalize."""
    brief_for_name = (
        ctx.brand_brief
        if isinstance(ctx.brand_brief, dict) and ctx.brand_brief
        else (ctx.design_brief if isinstance(getattr(ctx, "design_brief", None), dict) else None)
    )
    return (
        resolve_preview_brand_name(
            brand_name=ctx.brand_name,
            brand_brief=brief_for_name,
            business_name=getattr(ctx.req, "business_name", None),
            concept_name=getattr(ctx.req, "concept_name", None),
            manifest=ctx.manifest if isinstance(ctx.manifest, dict) else None,
            demo=ctx.demo if isinstance(ctx.demo, dict) else None,
            plan=ctx.plan if isinstance(ctx.plan, dict) else None,
            fallback=True,
        )
        or "Brand"
    )


def _scaffold_page_is_acceptable(
    source: str,
    *,
    page_id: str,
    action_ids: list[str],
    evidence_ids: list[str],
) -> bool:
    """Build-quality verdict for one marker-carrying route source.

    Policy (whether fallbacks may ship) is decided by the caller — this answers
    only whether the page is addressable and carries rendered content, so the
    measurement is identical with AppSpec enforcement on or off.
    """
    if page_id and not page_hooks_present(
        source,
        page_id=page_id,
        action_ids=action_ids,
        evidence_ids=evidence_ids,
    ):
        return False
    return not catalogue_page_is_thin(source)


def _typecheck_summary(workspace) -> dict:
    """Surface the typecheck verdict so it is visible outside `.bmv-debug/`.

    Type errors deliberately do not gate `viewable` — a slightly imperfect served
    preview beats no preview — but an unreported count is indistinguishable from
    a clean run, which is how 59 of them shipped unnoticed.
    """
    from app.application.preview_app.typecheck import read_typecheck_record

    try:
        record = read_typecheck_record(workspace)
    except (OSError, ValueError) as e:
        log.warning("typecheck record unreadable: %s", e)
        return {}
    if not isinstance(record, dict):
        return {}

    status = str(record.get("status") or "")
    if not status:
        return {}
    return {
        "typecheck_status": status,
        "type_errors": int(record.get("error_count") or 0),
    }


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
        source = read_file(workspace, component_file) or ""
        # Deterministic plan→site AI hub is never a catalogue stub.
        if component_file == AI_HUB_COMPONENT or "plan AI feature hub" in source:
            clear_stubbed_path(workspace, component_file)
            continue
        if "deterministic catalogue contract scaffold" not in source:
            clear_stubbed_path(workspace, component_file)
            continue
        page_id = str(route.get("app_spec_page_id") or route.get("page_id") or "")
        page = pages_by_id.get(page_id)
        action_ids = list(page.action_ids) if page else list(route.get("action_ids") or [])
        evidence_ids = (
            list(page.evidence_ids) if page else list(route.get("evidence_ids") or [])
        )
        if _scaffold_page_is_acceptable(
            source,
            page_id=page_id,
            action_ids=action_ids,
            evidence_ids=evidence_ids,
        ):
            clear_stubbed_path(workspace, component_file)
        else:
            record_stubbed_path(workspace, component_file)

    fallback_pages = [
        path
        for path in consume_stubbed_paths(workspace)
        if path.replace("\\", "/") != AI_HUB_COMPONENT
    ]
    if fallback_pages:
        log.warning(
            "    fallback pages (%s): %s",
            len(fallback_pages),
            ", ".join(fallback_pages[:8]),
        )
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

    # Plan → site contract: every structured AI feature must be addressable.
    planned_ai = ai_features_from_request(req) or []
    brand_name = _finalize_brand_name(ctx)
    ctx.brand_name = brand_name
    if planned_ai:
        # Re-apply after codegen so contextual panels land on real pages.
        # Must rebuild after this — earlier Vite dist may still contain a
        # public-utility stub that overwrote the hub before guards were fixed.
        hub_before = read_file(workspace, "src/pages/AiFeaturesPage.tsx") or ""
        written_ai: list[str] = []
        try:
            written_ai = ensure_ai_feature_surfaces(
                workspace,
                architect,
                req,
                brand_name=brand_name,
            )
        except Exception as e:
            log.warning("    AI feature surface inject failed: %s", e)
        hub_after = read_file(workspace, "src/pages/AiFeaturesPage.tsx") or ""
        needs_ai_rebuild = bool(written_ai) and "AiFeatureDeck" in hub_after and (
            hub_before != hub_after or "AiFeatureDeck" not in hub_before
        )
        if needs_ai_rebuild:
            try:
                from app.application.preview_app.build import run_build

                _emit(
                    db,
                    request_id,
                    "build",
                    "Rebuilding preview with AI feature hub...",
                    90,
                    detail="AiFeatureDeck must ship in dist, not only source",
                )
                rebuilt_ok, rebuild_log = run_build(
                    workspace, ctx.base_path, ctx.template_renderer
                )
                if rebuilt_ok:
                    # Fresh dist only — do not clear soft AppSpec/fallback
                    # failures already recorded on `ok`.
                    ctx.build_log = rebuild_log
                    log.info("    AI hub rebuild OK — dist includes AiFeatureDeck")
                else:
                    log.warning(
                        "    AI hub rebuild failed — source has hub but dist may be stale"
                    )
            except Exception as e:
                log.warning("    AI hub rebuild skipped: %s", e)
        missing_ai = assert_ai_features_present(workspace, planned_ai)
        if missing_ai:
            ok = False
            _emit(
                db,
                request_id,
                "contract_failed",
                "Preview is missing AI features from the plan",
                92,
                detail=", ".join(missing_ai[:8]),
            )

    # Automated quality lock — heal known failures; do not claim ready if hard rules fail.
    def _gate_rebuild():
        from app.application.preview_app.build import run_build

        return run_build(workspace, ctx.base_path, ctx.template_renderer)

    _emit(
        db,
        request_id,
        "quality_gate",
        "Running automated quality lock...",
        91,
        detail="AI hub · listings · confirm · nav · dead links",
    )
    gate = run_quality_gate_with_heal(
        Path(workspace),
        architect,
        brand_name=brand_name,
        req=req,
        require_ai_hub=bool(planned_ai),
        rebuild=_gate_rebuild,
        ai_provider=getattr(ctx, "ai_provider", None),
    )
    if gate.healed:
        log.info("    quality gate healed: %s", ", ".join(gate.healed[:10]))
    if not gate.ok:
        ok = False
        detail = "; ".join(
            f"{i.code}@{i.path or '-'}: {i.message}" for i in gate.issues[:8]
        )
        log.error("    quality gate FAILED: %s", detail)
        _emit(
            db,
            request_id,
            "contract_failed",
            "Quality lock failed — preview not ready",
            92,
            detail=detail,
        )
    else:
        log.info("    quality gate PASSED")
        _emit(
            db,
            request_id,
            "quality_gate",
            "Quality lock passed",
            92,
            detail=f"healed={len(gate.healed)}",
        )

    # Vite may succeed while AppSpec stub/contract checks still fail. Prefer
    # showing the compiled site over leaving Live Product on a blank spinner.
    dist_ok = (Path(workspace) / "dist" / "index.html").is_file()
    # Hard lock: only the automated quality gate blocks Live Product.
    # Soft contract/fallback/AI-surface flags (ok=False) must not hide a built dist
    # behind "Website preview is being generated…".
    viewable = bool(dist_ok and gate.ok)
    preview_url = f"{ctx.base_path}/" if viewable else None
    if viewable:
        log.info("  OK Preview built: %s", preview_url)
        if not ok:
            log.warning(
                "  WARN preview %s quality gate passed but soft contract issues remain "
                "(fallback=%s) — serving Live Product anyway",
                request_id,
                len(fallback_pages),
            )
    elif dist_ok and not gate.ok:
        log.error(
            "  FAIL preview %s built but quality lock failed — not marking ready",
            request_id,
        )
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

    plan_roles = plan.get("roles") or []

    roles_out = [
        {
            "id": ar.get("id"),
            "label": ar.get("label"),
            "icon": ar.get("icon", "users"),
            "accent": accent,
            "defaultPath": ar.get("defaultPath") or _default_path(ar.get("id", "")),
            "tagline": role_tagline(ar, plan_roles),
        }
        for ar in architect_roles
    ] or [
        {
            "id": r.get("id"),
            "label": r.get("label"),
            "icon": r.get("icon", "users"),
            "accent": accent,
            "defaultPath": _default_path(r.get("id", "")),
            "tagline": role_tagline(r, plan_roles),
        }
        for r in plan_roles
    ]

    persisted_plan = _plan_for_persistence(plan)
    preview_app_result = {
        "url": preview_url,
        "status": "ready" if viewable else "failed",
        "roles": roles_out,
        "routes": route_list,
        "design_direction": architect.get("design_direction", ""),
        "fallback_pages": fallback_pages,
        # Remount host iframe past sticky error boundaries after rebuilds.
        "built_at": int(time.time()),
    }
    preview_app_result.update(_typecheck_summary(workspace))
    # Carry the journey walk the way _typecheck_summary carries type errors, so
    # "ready" is never read as "the funnel works" without the evidence beside it.
    # Several measurements on this pipeline were accurate and had no reader.
    journey_summary = getattr(gate, "journey", None) or {}
    if journey_summary:
        preview_app_result["journey"] = journey_summary
        preview_app_result["journey_hops_ok"] = len(journey_summary.get("hops_ok") or [])
        preview_app_result["journey_hops_broken"] = len(
            journey_summary.get("broken") or []
        )
    result = {
        "preview_app": preview_app_result,
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

    if not viewable:
        if not gate.ok:
            reason = "Quality lock failed: " + "; ".join(
                f"{i.code}: {i.message}" for i in gate.issues[:6]
            )
            _emit(db, request_id, "failed", reason, 100)
            return result
        if not dist_ok:
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
            log.warning(
                f"  WARN preview {request_id} finished without a successful Vite build "
                f"after {ctx.max_fix_attempts} fix attempts — status marked failed"
            )
            _emit(
                db,
                request_id,
                "failed",
                "Preview build could not complete — try Generate again",
                100,
            )
            return result
        # Should be unreachable: dist_ok + gate.ok ⇒ viewable.
        _emit(
            db,
            request_id,
            "failed",
            "Preview built but could not be published — try Generate again",
            100,
        )
        return result

    # Stay below tech (90) / proposal (95) / done (100) so the customer bar
    # does not jump backward after the live preview becomes available.
    _emit(db, request_id, "ready", "Live preview ready!", 88, detail=preview_url or "")
    return result
