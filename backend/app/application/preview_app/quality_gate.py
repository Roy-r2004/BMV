"""Automated preview quality gate — no manual checks, no hand patches.

Runs after generate. Known failures are auto-healed; "ready" must not ship
while hard rules still fail.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.application.preview_app.catalogue_contract.scaffold import (
    _is_schedule_listing_route,
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


@dataclass
class GateIssue:
    code: str
    message: str
    path: str = ""


@dataclass
class GateReport:
    issues: list[GateIssue] = field(default_factory=list)
    healed: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def fail(self, code: str, message: str, path: str = "") -> None:
        self.issues.append(GateIssue(code=code, message=message, path=path))


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

    # Schedule listing faces
    for rt in architect.get("routes") or []:
        if not isinstance(rt, dict):
            continue
        rel = str(rt.get("component_file") or "").replace("\\", "/")
        if not rel or not _is_schedule_listing_route(rel, rt):
            continue
        src = _read(workspace, rel)
        if src and "ScheduleRail" not in src:
            report.fail("listing_not_schedule_rail", "Listing page missing ScheduleRail", rel)

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

    return report


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

    # 3) Schedule listing faces
    for rt in architect.get("routes") or []:
        if not isinstance(rt, dict):
            continue
        rel = str(rt.get("component_file") or "").replace("\\", "/")
        if not rel or not _is_schedule_listing_route(rel, rt):
            continue
        src = _read(workspace, rel)
        if src and "ScheduleRail" not in src:
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

    # De-dupe while preserving order
    return list(dict.fromkeys(healed))


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
