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
    from app.application.preview_app.typecheck import (
        refresh_typecheck_record_if_stale,
    )

    try:
        # The gate's heal and AI repair rewrite source *after* the last
        # typecheck. Request 67 measured 3 errors at 12:06:56, the repair
        # rewrote seven files at 12:09, and 9 shipped — six of them created by
        # the repair. A stale count reads exactly like a fresh one.
        record = refresh_typecheck_record_if_stale(workspace)
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


def _visual_review_summary(workspace, not_run_reason: str | None = None) -> dict:
    """Surface *how much was actually looked at*, next to the verdict.

    `gate.ok` and `status: "ready"` were both reportable with zero pages judged:
    a vision outage lands every page in `unmeasured` at WARN, `report.blocking`
    comes back empty, and the gate passes. `measurement_failed` existed to say so
    and had no production reader at all.

    Deliberately does not gate `viewable` — see
    `PREVIEW_VISUAL_CRITIC_BLOCK_ON_UNMEASURED` for the operator who wants that.
    An unreported measurement is indistinguishable from a clean one, which is the
    actual defect being fixed here.
    """
    from app.application.preview_app.pipeline.visual_critic import visual_review_summary

    try:
        return visual_review_summary(workspace, not_run_reason=not_run_reason)
    except (OSError, ValueError) as e:
        log.warning("visual review summary unreadable: %s", e)
        # Still say something. `{}` here is how a run ends up reporting `None`
        # for a measurement it definitely did not take.
        return {
            "visual_review_status": "report_unreadable",
            "visual_pages_reviewed": 0,
            "visual_pages_unmeasured": 0,
            "visual_pages_selected": 0,
        }


#: Routes worth loading for the smoke test. Every declared public route plus the
#: ops surfaces an owner would open in a demo; params resolve to `1`.
_SMOKE_MAX_ROUTES = 12


def _smoke_routes(architect: dict) -> list[tuple[str, str, str]]:
    """(url path, component_file, surface) for each distinct page, public first."""
    seen: set[str] = set()
    public: list[tuple[str, str, str]] = []
    ops: list[tuple[str, str, str]] = []
    for route in architect.get("routes") or []:
        if not isinstance(route, dict):
            continue
        component = str(route.get("component_file") or "").replace("\\", "/")
        raw = str(route.get("path") or "")
        if not component or not raw or "*" in raw or component in seen:
            continue
        seen.add(component)
        import re as _re

        url = _re.sub(r"/:[A-Za-z_][A-Za-z0-9_]*", "/1", raw) or "/"
        surface = str(route.get("surface") or "").strip().lower()
        is_ops = surface == "ops" or url.startswith(
            ("/admin", "/owner", "/ops", "/staff", "/member", "/desk")
        )
        (ops if is_ops else public).append((url, component, "ops" if is_ops else "public"))
    return (public + ops)[:_SMOKE_MAX_ROUTES]


def _remeasure_repaired_pages(ctx: PipelineContext, architect: dict) -> list[str]:
    """Re-judge the pages whose visual verdict the gate retired.

    Retiring a verdict when a repair rewrites the page it describes stops a
    repaired page from failing the gate forever. On its own it also *removes* the
    only reading of pixels we have: request 46 ended with one page reviewed and
    five retired. This is the other half — the pages go back through the same
    screenshot-and-judge path they came from, against the source that will ship.

    Best-effort by construction. A failure here leaves them `unmeasured`, which is
    what the report already said, so nothing gets a pass it did not earn.
    """
    from app.core.config import settings

    if settings.PREVIEW_SKIP_VISUAL_CRITIC:
        return []
    workspace = Path(ctx.workspace)
    try:
        from app.application.preview_app.pipeline.visual_critic import (
            _run_visual_critique,
            load_visual_critique_report,
        )

        pending = [
            p for p in load_visual_critique_report(workspace).unmeasured if str(p).strip()
        ]
        if not pending:
            return []
        log.info("    visual critic: re-measuring %s repaired page(s)", len(pending))
        _run_visual_critique(
            ctx.db,
            ctx.request_id,
            workspace,
            architect,
            ctx.plan,
            ctx.specs_by_path,
            ctx.full_context,
            ctx.manifest,
            ctx.images,
            ctx.brand_name,
            ctx.primary,
            ctx.secondary,
            ctx.font,
            ctx.base_path,
            ctx.ai_provider,
            ctx.template_renderer,
            only_components=set(pending),
        )
        return pending
    except Exception as e:  # noqa: BLE001 — a measurement retry must never fail a run
        log.warning("    visual critic: re-measure pass failed (%s)", e)
        return []


def _regate_after_remeasure(
    ctx: PipelineContext,
    architect: dict,
    gate,
    remeasured: list[str],
    *,
    require_ai_hub: bool,
):
    """Let the verdicts the re-measure produced re-enter the gate.

    A verdict that arrives after the gate ran still has to be read by something.
    On request 66 nothing read it: the AI repair retired the two
    `visual_defect_severe` verdicts that were blocking, the gate re-ran with no
    verdict for those pages and passed on the journey fix alone, and the
    re-measure came back 5/100 and 35/100 for the same two pages three
    milliseconds later. `ready` shipped a page its own critic scored 5.

    This is not requests 43/44/45 inverted. Those were withheld by *stale*
    verdicts describing source a repair had already replaced — the failure mode
    that retiring exists to prevent. A re-measured verdict describes the source
    sitting in the workspace, by construction.

    Scoped hard, and deliberately. The gate is re-evaluated so that the surface
    policy stays in one place (severe blocks on public, warns on ops), but only
    findings **against the pages that were just re-measured** are allowed to
    revoke the pass. Re-running every check at this point would let something
    unrelated withhold a preview with no repair budget left to clear it, which
    is the 43/44/45 failure mode arriving by a different road. Evaluation only:
    no heal, no AI repair — a repair here would retire the verdict it was handed
    and loop.
    """
    from app.application.preview_app.quality_gate import evaluate_quality_gate

    wanted = {str(p).replace("\\", "/") for p in remeasured if str(p).strip()}
    if not wanted:
        return gate
    try:
        rechecked = evaluate_quality_gate(
            Path(ctx.workspace), architect, require_ai_hub=require_ai_hub
        )
    except Exception as e:  # noqa: BLE001 — a re-read must never fail a run
        log.warning("    quality gate: re-check after re-measure failed (%s)", e)
        return gate
    scoped = [
        issue
        for issue in rechecked.issues
        if str(issue.path or "").replace("\\", "/") in wanted
    ]
    if not scoped:
        return gate
    for issue in scoped:
        gate.fail(issue.code, issue.message, issue.path)
    log.error(
        "    quality gate: pass revoked — the re-measure of %s repaired page(s) "
        "returned %s blocking finding(s): %s",
        len(wanted),
        len(scoped),
        "; ".join(f"{i.code}@{i.path or '-'}" for i in scoped[:6]),
    )
    return gate

def _render_smoke_check(ctx: PipelineContext, architect: dict, brand_name: str) -> dict:
    """Load every page once and replace any that crashed with a safe stub.

    Deterministic, no model call, one browser session. This is the only check that
    runs *after* the gate's heal and AI repair have rewritten source, and it exists
    because those rewrites are unrendered: request 41's home page was repaired into
    `aiFeatures is not defined` and shipped an error box under `status=ready`.

    A crashed public page is replaced with the known-good stub the build phase
    already uses for compile failures — a plain, on-brand page beats a stack trace
    in front of an investor — and the workspace is rebuilt. Ops pages are recorded
    but never rebuilt over, matching the surface policy everywhere else.
    """
    from app.application.preview_app.build import run_build
    from app.application.preview_app.fallback import write_safe_stub
    from app.application.preview_app.screenshot import capture_routes_visual
    from app.core.config import settings

    workspace = Path(ctx.workspace)
    summary: dict = {"checked": 0, "crashed": [], "stubbed": [], "unresolved": []}
    if not (workspace / "dist" / "index.html").is_file():
        return summary
    routes = _smoke_routes(architect)
    if not routes:
        return summary

    base_url = f"{settings.INTERNAL_BASE_URL}{ctx.base_path}/"
    shots = workspace / "_render_smoke"

    def _probe(targets: list[tuple[str, str, str]]) -> dict[str, str]:
        captures = capture_routes_visual(
            base_url,
            [(url, shots / f"smoke_{i}.png") for i, (url, _c, _s) in enumerate(targets)],
        )
        errors: dict[str, str] = {}
        for (url, component, _surface), capture in zip(targets, captures):
            message = str(getattr(capture, "render_error", "") or "")
            if message:
                errors[component] = f"{url}: {message}"
        return errors

    try:
        crashed = _probe(routes)
        summary["checked"] = len(routes)
    except Exception as e:  # noqa: BLE001 — a probe failure must not fail the run
        log.warning("    render smoke check skipped: %s", e)
        return summary

    if not crashed:
        log.info("    render smoke: %s page(s) rendered", len(routes))
        _cleanup_dir(shots)
        return summary

    summary["crashed"] = sorted(crashed)
    for component, detail in sorted(crashed.items()):
        log.error("    render smoke FAILED %s — %s", component, detail[:200])

    public_crashed = [
        (url, component, surface)
        for url, component, surface in routes
        if surface == "public" and component in crashed
    ]
    if not public_crashed:
        _cleanup_dir(shots)
        return summary

    _emit(
        ctx.db,
        ctx.request_id,
        "quality_gate",
        f"Repairing {len(public_crashed)} page(s) that failed to render...",
        92,
        detail="; ".join(crashed[c][:80] for _u, c, _s in public_crashed),
    )
    from app.application.preview_app.catalogue_contract.slots import (
        catalogue_route_for_file,
    )

    for _url, component, _surface in public_crashed:
        try:
            route = catalogue_route_for_file(component, architect)
            write_safe_stub(
                workspace,
                component,
                brand_name=brand_name,
                industry=ctx.industry,
                route=route,
            )
            summary["stubbed"].append(component)
            log.warning("    render smoke: replaced %s with a safe stub", component)
        except Exception as e:  # noqa: BLE001
            log.error("    render smoke: could not stub %s: %s", component, e)

    if not summary["stubbed"]:
        _cleanup_dir(shots)
        return summary

    built, _log = run_build(workspace, ctx.base_path, ctx.template_renderer)
    if not built:
        log.error("    render smoke: rebuild after stubbing failed")
        _cleanup_dir(shots)
        summary["unresolved"] = sorted(crashed)
        return summary

    still_broken = _probe(public_crashed)
    summary["unresolved"] = sorted(still_broken)
    if still_broken:
        log.error(
            "    render smoke: %s page(s) still crash after stubbing — %s",
            len(still_broken),
            "; ".join(sorted(still_broken)),
        )
    else:
        log.info("    render smoke: every public page renders after repair")
    _cleanup_dir(shots)
    return summary


def _cleanup_dir(path: Path) -> None:
    try:
        import shutil

        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


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

    # The gate retires the verdict for every page it repairs, so those pages are
    # `unmeasured` now. Judge them again against the source that will actually
    # ship — a retired verdict with no replacement is coverage we quietly lost.
    #
    # This runs *before* the gate outcome is reported, and its result re-enters
    # the gate. Request 66 did it the other way round: the repair retired two
    # `visual_defect_severe` verdicts, the gate re-ran with nothing left to block
    # on and PASSED, and the re-measure returned 5/100 and 35/100 for those same
    # two pages three milliseconds later — the defects confirmed against the
    # source that ships, with nothing left to read them. It shipped `ready`.
    remeasured = _remeasure_repaired_pages(ctx, architect)
    if remeasured and gate.ok:
        gate = _regate_after_remeasure(
            ctx, architect, gate, remeasured, require_ai_hub=bool(planned_ai)
        )

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

    # Last word before "ready": does each page actually render? The gate's heal
    # and AI repair rewrite source *after* the visual critique took its
    # screenshots, so a repair can introduce a crash that nothing re-renders.
    # Request 41 shipped `aiFeatures is not defined` on its home page that way,
    # after a critic had scored the same page 65 for its (nonexistent) hero.
    render_report = _render_smoke_check(ctx, architect, brand_name)

    # Vite may succeed while AppSpec stub/contract checks still fail. Prefer
    # showing the compiled site over leaving Live Product on a blank spinner.
    dist_ok = (Path(workspace) / "dist" / "index.html").is_file()
    # Hard lock: only the automated quality gate blocks Live Product.
    # Soft contract/fallback/AI-surface flags (ok=False) must not hide a built dist
    # behind "Website preview is being generated…".
    #
    # A public page that still renders a stack trace after the stub repair is the
    # one soft flag that must hard-block: there is nothing to show behind it.
    crash_unresolved = [
        c for c in (render_report.get("unresolved") or [])
    ]
    viewable = bool(dist_ok and gate.ok and not crash_unresolved)
    if dist_ok and gate.ok and crash_unresolved:
        log.error(
            "  FAIL preview %s passed the gate but %s public page(s) render an error "
            "boundary — withholding rather than showing a stack trace: %s",
            request_id,
            len(crash_unresolved),
            "; ".join(crash_unresolved[:4]),
        )
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
    preview_app_result.update(
        _visual_review_summary(workspace, getattr(ctx, "visual_not_run_reason", None))
    )
    # Rendering is a measurement like any other, and it gets a reader beside
    # `status` for the same reason the visual counts do.
    preview_app_result["render_pages_checked"] = int(render_report.get("checked") or 0)
    preview_app_result["render_pages_crashed"] = len(render_report.get("crashed") or [])
    preview_app_result["render_pages_stubbed"] = len(render_report.get("stubbed") or [])
    preview_app_result["render_pages_unresolved"] = len(
        render_report.get("unresolved") or []
    )
    # A run that ran out of time and took deterministic paths must not look like
    # one that had time and chose them. Same principle as the visual counts
    # above: the measurement is worthless without a reader beside `status`.
    from app.application.services.request_deadline import (
        current_deadline,
        degradations as _degradations,
    )

    _degraded = _degradations()
    preview_app_result["degraded"] = [entry["stage"] for entry in _degraded]
    preview_app_result["degradations"] = _degraded
    _deadline = current_deadline()
    if _deadline is not None:
        preview_app_result["deadline_seconds"] = int(_deadline.total_seconds)
        preview_app_result["elapsed_seconds"] = int(_deadline.elapsed())
        preview_app_result["deadline_exceeded"] = _deadline.expired()
        # Published beside the degradations, not instead of them: a degradation
        # is only evidence the deadline worked if the run spent its budget on
        # itself. With 200 s of this, the same list is evidence of contention.
        preview_app_result["blocked_seconds"] = round(_deadline.blocked_seconds(), 1)
        preview_app_result["contention"] = _deadline.waits()
    if _degraded:
        log.warning(
            "  preview %s degraded %s stage(s) to meet its deadline: %s",
            ctx.request_id,
            len(preview_app_result["degraded"]),
            ", ".join(preview_app_result["degraded"]),
        )
    if (
        preview_app_result.get("status") == "ready"
        and preview_app_result.get("visual_review_status") == "unmeasured"
    ):
        # Reportable, but never silently. `status` keeps its three-value
        # vocabulary because four production readers and the frontend poller
        # branch on it; the honesty lives in the field beside it.
        log.error(
            "  WARN preview %s is ready but NOT visually reviewed — 0 of %s page(s) "
            "were judged (vision outage). Set "
            "PREVIEW_VISUAL_CRITIC_BLOCK_ON_UNMEASURED=true to withhold instead.",
            request_id,
            preview_app_result.get("visual_pages_selected", 0),
        )
        _emit(
            db,
            request_id,
            "visual_critic",
            "Preview is ready but was not visually reviewed",
            92,
            detail=(
                f"0 of {preview_app_result.get('visual_pages_selected', 0)} page(s) "
                "could be judged — vision measurement failed"
            ),
        )
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
