"""Automated preview quality gate — no manual checks, no hand patches.

Runs after generate. Known failures are auto-healed; "ready" must not ship
while hard rules still fail.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.application.preview_app.catalogue_contract.scaffold import (
    _is_directory_listing_route,
    _is_schedule_listing_route,
    has_listing_face_component,
    minimal_catalogue_page_scaffold,
)
from app.application.preview_app.catalogue_contract.slots import catalogue_route_for_file
from app.application.preview_app.workspace import list_source_files, read_file, write_file
from app.infrastructure.logging import get_logger

log = get_logger("QualityGate")

_DEAD_AI_STEP = re.compile(
    r"""href=\{\s*["']/(?:[\w-]+/)*(?:ai-advisor|ai-stylist|ai-chat)/[^"']+["']\s*\}"""
    r"""|href=["']/(?:[\w-]+/)*(?:ai-advisor|ai-stylist|ai-chat)/[^"']+["']""",
    re.I,
)
_LISTING_HINTS = ("class", "classes", "service", "services", "schedule", "workshop", "session")
_EMPTY_IMAGES_EXPORT_RE = re.compile(
    r"export\s+const\s+images\s*=\s*(?:\[\s*\]|\{\s*\})\s*;"
)


@dataclass
class GateIssue:
    code: str
    message: str
    path: str = ""


@dataclass
class GateReport:
    issues: list[GateIssue] = field(default_factory=list)
    healed: list[str] = field(default_factory=list)
    warnings: list[GateIssue] = field(default_factory=list)
    #: Journey walk summary, carried so "ready" is never read as "the funnel
    #: works" without the evidence. Read by finalize into the API result.
    journey: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.issues

    def fail(self, code: str, message: str, path: str = "") -> None:
        self.issues.append(GateIssue(code=code, message=message, path=path))

    def warn(self, code: str, message: str, path: str = "") -> None:
        """Record a defect that is worse to hide than to ship — never blocks ready."""
        self.warnings.append(GateIssue(code=code, message=message, path=path))


def _pages(workspace: Path) -> list[str]:
    return [
        rel
        for rel in list_source_files(workspace)
        if rel.replace("\\", "/").startswith("src/pages/") and rel.endswith(".tsx")
    ]


def _read(workspace: Path, rel: str) -> str:
    return read_file(workspace, rel) or ""


def evaluate_quality_gate(
    workspace: Path,
    architect: dict[str, Any] | None = None,
    *,
    require_ai_hub: bool = True,
) -> GateReport:
    """Pure evaluation — does not mutate the workspace."""
    report = GateReport()
    architect = architect or {}
    dist = Path(workspace) / "dist" / "index.html"
    if not dist.is_file():
        report.fail("no_dist", "Preview dist/index.html missing — site cannot load")

    pages = _pages(workspace)
    if not pages:
        report.fail("no_pages", "No pages generated under src/pages/")
        return report

    hub = "src/pages/AiFeaturesPage.tsx"
    hub_src = _read(workspace, hub)
    if require_ai_hub:
        if not hub_src:
            report.fail("ai_hub_missing", "AiFeaturesPage.tsx missing", hub)
        else:
            if "AiFeatureDeck" not in hub_src:
                report.fail("ai_hub_not_deck", "AI hub is not AiFeatureDeck", hub)
            if "Signature package" in hub_src or (
                "Your details" in hub_src and "Ready to confirm" in hub_src
            ):
                report.fail("ai_hub_utility_stub", "AI hub still looks like checkout stub", hub)

    for rel in pages:
        src = _read(workspace, rel)
        if _DEAD_AI_STEP.search(src):
            report.fail(
                "dead_ai_step_link",
                "Page links to invented AI advisor sub-route",
                rel,
            )

    # Schedule / directory listing faces
    for rt in architect.get("routes") or []:
        if not isinstance(rt, dict):
            continue
        rel = str(rt.get("component_file") or "").replace("\\", "/")
        if not rel:
            continue
        src = _read(workspace, rel)
        if _is_schedule_listing_route(rel, rt):
            if src and "ScheduleRail" not in src:
                report.fail(
                    "listing_not_schedule_rail",
                    "Listing page missing ScheduleRail",
                    rel,
                )
        if _is_directory_listing_route(rel, rt):
            if src and (
                not has_listing_face_component(src)
                or "seed.hero" in src
                or "// directory listing scaffold" not in src
            ):
                report.fail(
                    "listing_not_directory_face",
                    "Doctor/team page looks like homepage — missing directory face",
                    rel,
                )

    # Confirmation faces
    for rel in pages:
        low = rel.lower()
        blob = _read(workspace, rel)
        title_hit = bool(
            re.search(r"confirm|success|booked|thank", low)
            or re.search(r"confirm|success|booked|thank", blob[:400], re.I)
        )
        if not title_hit:
            continue
        route = catalogue_route_for_file(rel, architect)
        path = str(route.get("path") or "").lower()
        if "confirm" in path or "success" in path or "confirm" in low or "success" in low:
            if "ConfirmStage" not in blob and "composed confirmation page" not in blob:
                # Utility confirmation stub is a hard fail for the demo journey.
                if "public-utility" in blob or "Signature package" in blob or "PageHeader" in blob:
                    report.fail(
                        "confirm_not_stage",
                        "Confirmation page missing ConfirmStage",
                        rel,
                    )

    app = _read(workspace, "src/App.tsx")
    if 'path="/ai-advisor"' in app and 'path="/ai-advisor/*"' not in app:
        report.fail("ai_advisor_no_wildcard", "App.tsx missing /ai-advisor/* catch-all", "src/App.tsx")

    # Product-kind chrome: saas/ops must not ship a marketing home.
    try:
        from app.application.preview_app.product_kind import validate_product_kind_chrome

        for code in validate_product_kind_chrome(architect):
            report.fail(
                code,
                f"Product kind chrome mismatch: {code}",
                "architect.routes",
            )
    except Exception as e:
        log.warning("product_kind chrome check skipped: %s", e)

    # Workspace density: ops home page should look like a product, not MarketingHero.
    for rt in architect.get("routes") or []:
        if not isinstance(rt, dict):
            continue
        if str(rt.get("path") or "") not in {"/", "/home"}:
            continue
        if str(rt.get("surface") or "") != "ops" and not str(
            rt.get("skeleton_id") or ""
        ).startswith("ops"):
            continue
        rel = str(rt.get("component_file") or "").replace("\\", "/")
        src = _read(workspace, rel) if rel else ""
        if src and "MarketingHero" in src:
            report.fail(
                "ops_home_marketing_hero",
                "Ops/SaaS home still uses MarketingHero",
                rel,
            )
        if src and "OpsShell" not in src and "composeSkeletonLayout" not in src:
            report.fail(
                "ops_home_missing_shell",
                "Ops/SaaS home missing OpsShell",
                rel,
            )
        if src and "StatCard" not in src and "DataTable" not in src:
            report.fail(
                "ops_home_thin",
                "Ops/SaaS home missing KPI/table density",
                rel,
            )

    mock = _read(workspace, "src/data/mock.ts")
    # Nav clutter: too many public detail links in navigation JSON.
    public_nav_match = re.search(
        r'"public"\s*:\s*\[(.*?)\]', mock, re.S
    )
    if public_nav_match:
        chunk = public_nav_match.group(1)
        paths = re.findall(r'"path"\s*:\s*"([^"]+)"', chunk)
        deep = [p for p in paths if p.count("/") >= 2]
        if len(paths) > 8 or len(deep) > 2:
            report.fail(
                "nav_clutter",
                f"Public nav too cluttered ({len(paths)} items, {len(deep)} deep)",
                "src/data/mock.ts",
            )

    # `images` is a slot map consumed as images.hero/.card1 — an empty literal of
    # either shape yields undefined src attributes, so it needs its own code and
    # heal rather than the list-row seeding the generic check triggers.
    if _EMPTY_IMAGES_EXPORT_RE.search(mock):
        report.fail(
            "empty_mock_images",
            "mock.ts exports an empty `images` slot map — hero and card photography cannot render",
            "src/data/mock.ts",
        )

    # Empty mock array exports → blank list UIs even when pages import them.
    from app.application.preview_app.patterns import _EMPTY_ARRAY_EXPORT_RE

    skip_empty = {"roles", "navigation", "images", "brand", "aiFeatures"}
    for match in _EMPTY_ARRAY_EXPORT_RE.finditer(mock):
        name = match.group(1)
        if name.lower() in {s.lower() for s in skip_empty}:
            continue
        report.fail(
            "empty_mock_export",
            f"mock.ts exports empty array `{name}`",
            "src/data/mock.ts",
        )

    # Pages that map over useState([]) with no mock import → empty demo lists.
    try:
        from app.application.preview_app.safety.source_sanitize import find_empty_seed_pages

        for rel in find_empty_seed_pages(workspace):
            report.fail(
                "empty_seed_page",
                "Page maps over useState([]) with no mock seed import",
                rel,
            )
    except Exception as e:
        log.warning("empty_seed_page check skipped: %s", e)

    # Locally-referenced images that resolve nowhere → broken-image icons.
    from app.application.preview_app.asset_integrity import (
        blocking_missing_assets,
        scan_asset_integrity,
    )

    try:
        assets = scan_asset_integrity(workspace)
    except (OSError, ValueError) as e:
        log.warning("asset integrity check skipped: %s", e)
    else:
        blocking = {ref.path for ref in blocking_missing_assets(assets)}
        for ref in assets.missing:
            message = (
                f"Referenced asset `{ref.path}` exists in neither public/ nor dist/"
            )
            if ref.path in blocking:
                report.fail("missing_public_asset", message, ref.referenced_by[0])
            else:
                report.warn("missing_internal_asset", message, ref.referenced_by[0])
        if assets.missing:
            log.warning(
                "asset integrity: %s missing reference(s), %s on public surfaces: %s",
                len(assets.missing),
                len(blocking),
                ", ".join(ref.path for ref in assets.missing[:8]),
            )

    # The visual loop renders real pixels and is the only check that can see a
    # photograph depicting the wrong industry. It persists a report rather than
    # failing inline, because it runs before this gate.
    from app.application.preview_app.pipeline.visual_critic import (
        visual_critique_gate_issues,
    )

    try:
        visual_issues = [
            issue
            for issue in visual_critique_gate_issues(workspace)
            # `missing_image_asset` restates what asset_integrity already found,
            # but blocks on every surface. Defer to the surface-aware check above
            # so a broken owner-page thumbnail cannot withhold the whole preview.
            if issue[0] != "missing_image_asset"
        ]
    except (OSError, ValueError) as e:
        log.warning("visual critique issues unreadable: %s", e)
    else:
        for code, message, path in visual_issues:
            report.fail(code, message, path)
        if visual_issues:
            log.warning(
                "visual critique blocking (%s): %s",
                len(visual_issues),
                "; ".join(f"{c}:{p}" for c, _m, p in visual_issues[:8]),
            )

    # Journey contract — the path *between* pages. Every check above validates a
    # page in isolation, and a storefront passed all of them while its visitor
    # could not browse a collection, open an item, or ask about it.
    #
    # Deliberately computed here rather than persisted: this function is called
    # again after heal, so a repaired page clears its own finding. The visual
    # critique report is written once pre-refine and cannot (P0-3).
    try:
        from app.application.preview_app.capabilities.journey import (
            journey_gate_issues,
            walk_journey,
        )

        journey_report = walk_journey(
            Path(workspace), architect, pack=_journey_pack(architect)
        )
    except Exception as e:  # noqa: BLE001 - recorded, never silently swallowed
        # A crash in the walker must not fail every generation, but it must also
        # not vanish the way build_phase's bare except vanished the visual report.
        log.error("journey walk failed: %s", e, exc_info=True)
        report.warn("journey_walk_failed", f"Journey contract not evaluated: {e}")
    else:
        report.journey = journey_report.summary()
        for code, message, path in journey_gate_issues(journey_report):
            report.fail(code, message, path)
        for finding in journey_report.warnings:
            report.warn(
                finding.code, finding.message, finding.component_file or finding.path
            )
        if journey_report.findings:
            log.warning(
                "journey broken (%s blocking, %s warn): %s",
                len(journey_report.blocking),
                len(journey_report.warnings),
                "; ".join(
                    f"{f.code}:{f.path}" for f in journey_report.findings[:8]
                ),
            )

    return report


def _journey_pack(architect: dict[str, Any]) -> dict[str, Any] | None:
    """The industry pack, for its declared capabilities. None is a safe default."""
    template_id = str(architect.get("industry_template_id") or "").strip()
    if not template_id:
        return None
    try:
        from app.application.preview_app.industry_templates.loader import load_templates

        return load_templates().get(template_id)
    except Exception as e:  # noqa: BLE001 - capability defaults still apply
        log.warning("industry pack unreadable for journey walk: %s", e)
        return None


def heal_quality_gate(
    workspace: Path,
    architect: dict[str, Any],
    *,
    brand_name: str,
    req: Any = None,
) -> list[str]:
    """Auto-repair known gate failures. Returns list of healed relative paths."""
    from app.application.preview_app.ai_feature_surfaces import (
        ensure_ai_feature_surfaces,
        rewrite_invented_ai_step_links,
    )
    from app.application.preview_app.assemble import sync_mock_roles_navigation
    from app.application.services.ai_features import ai_feature_hub_page_source

    healed: list[str] = []

    # 0) Product-kind chrome repair — rewrite marketing ops homes to catalogue ops scaffold
    try:
        from app.application.preview_app.product_kind import (
            OPS_KINDS,
            apply_product_kind_to_architect,
            resolve_product_kind_contract,
            validate_product_kind_chrome,
        )

        kind = str(architect.get("product_kind") or "")
        if kind in OPS_KINDS or validate_product_kind_chrome(architect):
            context = ""
            if req is not None:
                from app.application.preview_app.product_kind import context_from_request

                context = context_from_request(req)
            contract = resolve_product_kind_contract(
                context or kind or "saas workspace dashboard"
            )
            repaired = apply_product_kind_to_architect(architect, contract)
            architect.clear()
            architect.update(repaired)
            for rt in architect.get("routes") or []:
                if not isinstance(rt, dict):
                    continue
                if str(rt.get("path") or "") not in {"/", "/home"}:
                    continue
                if str(rt.get("surface") or "") != "ops" and not str(
                    rt.get("skeleton_id") or ""
                ).startswith("ops"):
                    continue
                rel = str(rt.get("component_file") or "").replace("\\", "/")
                if not rel:
                    continue
                src = _read(workspace, rel)
                if src and "MarketingHero" not in src and "OpsShell" in src:
                    continue
                rt = dict(rt)
                rt["surface"] = "ops"
                # Keep subtype signature skeletons (ledger/blotter); only fill if missing.
                if not str(rt.get("skeleton_id") or "").startswith("ops"):
                    rt["skeleton_id"] = contract.home_skeleton_id or "ops-dashboard"
                if not rt.get("section_slots"):
                    home_bp = next(
                        (p for p in contract.pages if p.path in {"/", "/home"}),
                        contract.pages[0] if contract.pages else None,
                    )
                    rt["section_slots"] = (
                        home_bp.section_slots()
                        if home_bp is not None
                        else [
                            "header",
                            "kpis",
                            "filters",
                            "table",
                            "chart",
                            "activity",
                            "risk",
                        ]
                    )
                write_file(
                    workspace,
                    rel,
                    minimal_catalogue_page_scaffold(rel, rt, brand_name=brand_name),
                )
                healed.append(rel)
    except Exception as e:
        log.warning("quality heal product_kind chrome failed: %s", e)

    # 1) AI hub + panels + dead step links
    if req is not None:
        try:
            written = ensure_ai_feature_surfaces(
                workspace, architect, req, brand_name=brand_name
            )
            healed.extend(written)
        except Exception as e:
            log.warning("quality heal AI surfaces failed: %s", e)
    else:
        hub = "src/pages/AiFeaturesPage.tsx"
        if "AiFeatureDeck" not in _read(workspace, hub):
            write_file(
                workspace,
                hub,
                ai_feature_hub_page_source(brand_name=brand_name, features=[]),
            )
            healed.append(hub)
        for rel in _pages(workspace):
            src = _read(workspace, rel)
            fixed = rewrite_invented_ai_step_links(src)
            if fixed != src:
                write_file(workspace, rel, fixed)
                healed.append(rel)

    # 2) App.tsx wildcard for advisor
    app = _read(workspace, "src/App.tsx")
    if 'path="/ai-advisor"' in app and 'path="/ai-advisor/*"' not in app:
        app2 = app.replace(
            '<Route path="/ai-advisor" element={<AiAdvisorChatPage />} />',
            '<Route path="/ai-advisor" element={<AiAdvisorChatPage />} />\n'
            '          <Route path="/ai-advisor/*" element={<AiAdvisorChatPage />} />',
            1,
        )
        # Generic: any *Advisor*Page component
        if app2 == app:
            app2 = re.sub(
                r'(<Route path="(/ai-advisor)" element=\{<(\w+) />\} />)',
                r'\1\n          <Route path="\2/*" element={<\3 />}} />',
                app,
                count=1,
            )
        if app2 != app:
            write_file(workspace, "src/App.tsx", app2)
            healed.append("src/App.tsx")

    # 3) Schedule / directory listing faces
    for rt in architect.get("routes") or []:
        if not isinstance(rt, dict):
            continue
        rel = str(rt.get("component_file") or "").replace("\\", "/")
        if not rel:
            continue
        src = _read(workspace, rel)
        if _is_schedule_listing_route(rel, rt) and src and "ScheduleRail" not in src:
            write_file(
                workspace,
                rel,
                minimal_catalogue_page_scaffold(rel, rt, brand_name=brand_name),
            )
            healed.append(rel)
        if _is_directory_listing_route(rel, rt) and src and (
            not has_listing_face_component(src)
            or "seed.hero" in src
            or "// directory listing scaffold" not in src
        ):
            write_file(
                workspace,
                rel,
                minimal_catalogue_page_scaffold(rel, rt, brand_name=brand_name),
            )
            healed.append(rel)

    # 4) Confirmation → ConfirmStage via utility compose
    from app.application.preview_app.utility_compositor import (
        compose_utility_page_tsx,
        default_utility_content,
        infer_utility_workspace_type,
    )

    for rel in _pages(workspace):
        low = rel.lower()
        if not re.search(r"confirm|success|booked", low):
            continue
        src = _read(workspace, rel)
        if "ConfirmStage" in src:
            continue
        route = catalogue_route_for_file(rel, architect)
        path = str(route.get("path") or f"/{Path(rel).stem}")
        title = str(route.get("title") or "Confirmed")
        wtype = infer_utility_workspace_type(path, title, "confirmation")
        if wtype != "confirmation":
            wtype = "confirmation"
        composed = compose_utility_page_tsx(
            file_path=rel,
            route={**route, "path": path, "title": title, "skeleton_id": "public-utility"},
            content=default_utility_content(
                wtype, brand_name=brand_name, title=title, path=path
            ),
            brand_name=brand_name,
            workspace_type="confirmation",
        )
        write_file(workspace, rel, composed)
        healed.append(rel)

    # 5) Nav clutter — regenerate from architect with tightened rules
    try:
        if sync_mock_roles_navigation(workspace, architect):
            healed.append("src/data/mock.ts")
    except Exception as e:
        log.warning("quality heal nav failed: %s", e)

    # 6) Empty mock array exports → seed realistic rows
    try:
        from app.application.preview_app.safety.mock_data import enrich_empty_mock_exports

        filled = enrich_empty_mock_exports(workspace, brand_name)
        if filled:
            healed.append("src/data/mock.ts")
    except Exception as e:
        log.warning("quality heal empty mock exports failed: %s", e)

    # 7) Empty `images` slot map → curated slot URLs that always load
    try:
        from app.application.services.industry_images import normalize_image_slot_map

        mock_src = _read(workspace, "src/data/mock.ts")
        empty_images = _EMPTY_IMAGES_EXPORT_RE.search(mock_src)
        if empty_images:
            slot_map = json.dumps(
                normalize_image_slot_map(None), indent=2, ensure_ascii=False
            )
            write_file(
                workspace,
                "src/data/mock.ts",
                mock_src[: empty_images.start()]
                + f"export const images = {slot_map};"
                + mock_src[empty_images.end() :],
            )
            healed.append("src/data/mock.ts")
    except Exception as e:
        log.warning("quality heal empty images slot map failed: %s", e)

    # 8) Broken local asset references → imagery the browser can actually fetch
    try:
        from app.application.preview_app.asset_integrity import (
            repair_missing_asset_references,
        )

        healed.extend(repair_missing_asset_references(workspace))
    except Exception as e:
        log.warning("quality heal asset references failed: %s", e)

    # 9) Public dead links → the declared route they meant
    try:
        from app.application.preview_app.capabilities.journey import (
            repair_dead_internal_links,
        )

        relinked = repair_dead_internal_links(workspace, architect)
        if relinked:
            log.info("quality heal repointed dead links in %s", ", ".join(relinked))
        healed.extend(relinked)
    except Exception as e:
        log.warning("quality heal dead links failed: %s", e)

    # De-dupe while preserving order
    return list(dict.fromkeys(healed))


def _settle_warnings(
    workspace: Path,
    architect: dict[str, Any],
    report: GateReport,
    *,
    require_ai_hub: bool,
) -> None:
    """Repair and report warning-only defects, which never reach the heal path.

    `ok` ignores warnings, so a run whose only defect is owner-surface breakage
    returns before `heal_quality_gate`. Without this the deterministic asset
    repair never fires and the warning is recorded into a field nobody reads.
    """
    if not report.warnings:
        return

    from app.application.preview_app.asset_integrity import (
        repair_missing_asset_references,
    )

    try:
        touched = repair_missing_asset_references(workspace)
    except (OSError, ValueError) as e:
        log.warning("warning-only asset repair skipped: %s", e)
        touched = []

    if touched:
        report.healed = list(dict.fromkeys([*report.healed, *touched]))
        rescan = evaluate_quality_gate(
            workspace, architect, require_ai_hub=require_ai_hub
        )
        # Only warnings are adopted: this path is reached because the preview
        # already passed, and a repair must never withhold a shippable app.
        report.warnings = rescan.warnings

    if report.warnings:
        log.warning(
            "quality gate warnings (%s, not blocking ready): %s",
            len(report.warnings),
            "; ".join(f"{w.code}:{w.path}" for w in report.warnings[:8]),
        )


def run_quality_gate_with_heal(
    workspace: Path,
    architect: dict[str, Any],
    *,
    brand_name: str,
    req: Any = None,
    require_ai_hub: bool = True,
    rebuild=None,
    ai_provider: Any = None,
    allow_ai_repair: bool | None = None,
    max_ai_attempts: int | None = None,
) -> GateReport:
    """Evaluate → deterministic heal → AI repair (sandboxed) → rebuild → re-gate.

    Ready only when the fixed checks pass. AI may invent fixes; it cannot skip checks.
    """
    from app.core.config import settings

    report = evaluate_quality_gate(
        workspace, architect, require_ai_hub=require_ai_hub
    )
    if report.ok:
        _settle_warnings(workspace, architect, report, require_ai_hub=require_ai_hub)
        return report

    log.warning(
        "quality gate failed (%s): %s",
        len(report.issues),
        "; ".join(f"{i.code}:{i.path}" for i in report.issues[:8]),
    )
    healed = heal_quality_gate(
        workspace, architect, brand_name=brand_name, req=req
    )
    report.healed = healed
    if healed and callable(rebuild):
        try:
            ok, _log = rebuild()
            if not ok:
                log.warning("quality gate rebuild after heal failed")
        except Exception as e:
            log.warning("quality gate rebuild error: %s", e)

    final = evaluate_quality_gate(
        workspace, architect, require_ai_hub=require_ai_hub
    )
    final.healed = list(healed)

    use_ai = (
        settings.PREVIEW_QUALITY_AI_REPAIR
        if allow_ai_repair is None
        else bool(allow_ai_repair)
    )
    attempts = (
        settings.PREVIEW_MAX_QUALITY_FIX_ATTEMPTS
        if max_ai_attempts is None
        else max(0, int(max_ai_attempts))
    )
    if final.ok or not use_ai or attempts <= 0:
        return final

    from app.application.preview_app.quality_repair import run_ai_quality_repair

    for attempt in range(1, attempts + 1):
        log.warning(
            "quality gate AI repair attempt %s/%s (%s issues)",
            attempt,
            attempts,
            len(final.issues),
        )
        try:
            touched = run_ai_quality_repair(
                workspace,
                architect,
                final.issues,
                ai_provider=ai_provider,
            )
        except Exception as e:
            log.warning("quality gate AI repair crashed: %s", e)
            touched = []

        more: list[str] = []
        if touched:
            more = heal_quality_gate(
                workspace, architect, brand_name=brand_name, req=req
            )
            healed = list(dict.fromkeys([*healed, *touched, *more]))
        if touched and callable(rebuild):
            try:
                ok, _log = rebuild()
                if not ok:
                    log.warning("quality gate rebuild after AI repair failed")
            except Exception as e:
                log.warning("quality gate rebuild error after AI repair: %s", e)

        final = evaluate_quality_gate(
            workspace, architect, require_ai_hub=require_ai_hub
        )
        final.healed = healed
        if final.ok:
            log.info("quality gate PASSED after AI repair attempt %s", attempt)
            return final
        if not touched:
            log.warning("quality gate AI repair produced no file changes — stopping")
            break

    return final
