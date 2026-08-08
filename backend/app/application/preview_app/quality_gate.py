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
from app.application.preview_app.industry_templates.seed import (
    early_brand_placeholder_item_titles,
    early_brand_placeholder_strings,
)
from app.application.preview_app.workspace import (
    list_source_files,
    read_file,
    restore_source,
    snapshot_source,
    write_file,
)
from app.infrastructure.logging import get_logger

log = get_logger("QualityGate")

_DEAD_AI_STEP = re.compile(
    r"""href=\{\s*["']/(?:[\w-]+/)*(?:ai-advisor|ai-stylist|ai-chat)/[^"']+["']\s*\}"""
    r"""|href=["']/(?:[\w-]+/)*(?:ai-advisor|ai-stylist|ai-chat)/[^"']+["']""",
    re.I,
)
_LISTING_HINTS = ("class", "classes", "service", "services", "schedule", "workshop", "session")
#: `[Artist Name]`, `[Painter's Name]`, `[Owner Name]` — an authoring
#: placeholder nobody filled in, shipped as visible copy.
#:
#: Anchored on a capital and comma-free so JS destructuring is not a hit:
#: `const [name, setName] = useState()` and `[location.pathname]` dependency
#: arrays both survive it. Same pattern the QA harness settled on after
#: measuring four false positives from the naive version.
_BRACKETED_PLACEHOLDER_RE = re.compile(r"\[[A-Z][^,\[\]\n]{2,40}\]")

_EMPTY_IMAGES_EXPORT_RE = re.compile(
    r"export\s+const\s+images\s*=\s*(?:\[\s*\]|\{\s*\})\s*;"
)

#: A quoted string leaf in `mock.ts`. The early-brand sets below hold *exact*
#: leaf values, so they are compared against whole literals and never against a
#: substring of the file: `"Guest favorite"` must not fire on a testimonial
#: reading "our guest favorite for years".
_STRING_LEAF_RE = re.compile(r"""(['"])((?:\\.|(?!\1)[^\\\n])*)\1""")

#: The two Brand-default titles `product_face._entry_is_early_placeholder` treats
#: as early placeholders even though they carry no "Brand" token. Restated here
#: because they are literals there too; `test_the_named_early_titles_track_product_face`
#: fails if the two lists drift apart.
_NAMED_EARLY_TITLES = frozenset({"Everyday essential", "Guest favorite"})


@dataclass
class GateIssue:
    code: str
    message: str
    path: str = ""
    #: The skeleton the failing page resolved to, when the issue names a page.
    #:
    #: Costs one lookup and answers a class of question that was otherwise
    #: unanswerable off the log. `listing_not_schedule_rail` fired 4 times across
    #: trios 2-5, all on `ServicesPage.tsx` and `TreatmentsPage.tsx` — and a page
    #: with that title resolves to `public-catalog` or `public-service` depending
    #: on its *purpose text*, not its name. Only `public-catalog` overflowed the
    #: contract budget that `0082f5f` fixed, so whether that fix could have moved
    #: this code turns entirely on which skeleton each fire was, and the archive
    #: cannot say: `.bmv-debug/catalogue-contract/` only dumps pages that were
    #: rejected, and these compiled fine. Pre-flight question 5.
    skeleton_id: str = ""


@dataclass
class GateReport:
    issues: list[GateIssue] = field(default_factory=list)
    healed: list[str] = field(default_factory=list)
    warnings: list[GateIssue] = field(default_factory=list)
    #: Journey walk summary, carried so "ready" is never read as "the funnel
    #: works" without the evidence. Read by finalize into the API result.
    journey: dict[str, Any] = field(default_factory=dict)
    #: Set by `evaluate_quality_gate` so every issue can name its skeleton without
    #: 40 call sites each having to remember to pass one. A report built without it
    #: still works; its issues just carry an empty `skeleton_id`.
    architect: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return not self.issues

    def _skeleton_for(self, path: str) -> str:
        # No `if not path or self.architect is None` guard in front of this.
        # One was written and the mutation sweep proved both halves dead:
        # `catalogue_route_for_file` already returns `{}` for a `None` architect
        # and can never match an empty path, because it skips routes whose own
        # `component_file` is falsy. Failing open on the skeleton is deliberate —
        # a gate that raised because it could not name a skeleton would trade a
        # reported defect for an unreported crash.
        return str(catalogue_route_for_file(path, self.architect).get("skeleton_id") or "")

    def fail(self, code: str, message: str, path: str = "") -> None:
        self.issues.append(
            GateIssue(
                code=code, message=message, path=path, skeleton_id=self._skeleton_for(path)
            )
        )

    def warn(self, code: str, message: str, path: str = "") -> None:
        """Record a defect that is worse to hide than to ship — never blocks ready."""
        self.warnings.append(
            GateIssue(
                code=code, message=message, path=path, skeleton_id=self._skeleton_for(path)
            )
        )


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
    architect = architect or {}
    report = GateReport(architect=architect)
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

    # An unfilled authoring placeholder shipped as visible copy. Request 71 put
    # `[Artist Name]` in the `<h1>` of `/about-artist`; request 68 shipped
    # `[Painter's Name]` twice and `[Owner Name]` once, in `mock.ts`.
    #
    # This is deterministic on purpose. The visual critic *would* have caught
    # request 71's — it caught the identical defect on 68 — but the 6-page cap
    # skipped `/about-artist`, and which pages the cap skips is effectively
    # arbitrary. A text pattern in seed data needs no vision call at all, so the
    # critic's coverage stops being load-bearing for this class.
    #
    # Deliberately narrow: `[A-Z]` start and no comma, so JS destructuring
    # (`const [name, setName] = useState()`, `[location.pathname]` dep arrays)
    # is not a hit. Measured against five workspaces and the kit: zero false
    # positives, three true positives on request 68.
    for leaked in dict.fromkeys(_BRACKETED_PLACEHOLDER_RE.findall(mock)):
        report.fail(
            "placeholder_content_shipped",
            f"mock.ts ships the unfilled placeholder {leaked} as content",
            "src/data/mock.ts",
        )

    # The second family, and the reason this block exists: item 1.8 specified
    # this gate on `early_brand_placeholder_strings()` /
    # `early_brand_placeholder_item_titles()` and the shipped gate used only the
    # bracket regex above, so for as long as the row has been scored it has
    # measured one of the two families it was meant to catch. Session 26's
    # census found the missing one live on 7 of 87 stored workspaces —
    # `Everyday essential` and `Guest favorite` on requests 19, 34, 37, 39, 43,
    # **135 and 140** — a set that does not overlap the bracket regex's seven at
    # all, and two of whose members sit inside the stretch the row was calling
    # clean.
    #
    # These are not brackets-with-a-capital. They are the seed's own default
    # copy: what the pipeline writes when it has nothing specific to say about
    # the business. They ship looking like content and say nothing, which is the
    # same defect as `[Artist Name]` wearing better clothes.
    #
    # **The `"Brand" in s` guard is load-bearing and is not ours to invent.**
    # `early_brand_placeholder_strings()` is *every* string leaf of the
    # Brand-default seed, and that includes `/gallery`, `60 min`, `Get started`
    # and `On schedule` — routes, durations and CTAs a real business ships too.
    # Matched bare it fires on 87 of 87 workspaces and means nothing.
    # `product_face.py:90` already solved this with a co-occurrence test, and
    # this reproduces that guard rather than inventing a second rule for the
    # same question. Exact-leaf comparison, never substring, for the same
    # reason.
    early_defaults = {
        s for s in early_brand_placeholder_strings() if s and "Brand" in s
    } | {
        t for t in early_brand_placeholder_item_titles()
        if t and ("Brand" in t or t in _NAMED_EARLY_TITLES)
    }
    leaves = {m.group(2).strip() for m in _STRING_LEAF_RE.finditer(mock)}
    for leaked in sorted(leaves & early_defaults):
        report.fail(
            "placeholder_content_shipped",
            f"mock.ts ships the unfilled seed default {leaked!r} as content",
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


def _declared_route_paths_in_app_tsx(workspace: Path) -> list[str]:
    """Every `<Route path="…">` in the generated router, in order, with repeats."""
    source = read_file(workspace, "src/App.tsx") or ""
    return re.findall(r'<Route\s+path="([^"]+)"', source)


def _route_table_is_stale(workspace: Path, architect: dict[str, Any]) -> bool:
    """True when App.tsx no longer serves what the architect declared.

    Two failures, both silent: a route that was deleted (its links fall to the
    catch-all) and a route declared twice (the second element is unreachable —
    React Router takes the first match).
    """
    rendered = _declared_route_paths_in_app_tsx(workspace)
    if not rendered:
        return False  # no router yet, or an unreadable file: not this heal's job
    if len(rendered) != len(set(rendered)):
        return True
    served = set(rendered)
    pages = {p.replace("\\", "/") for p in _pages(workspace)}
    for route in architect.get("routes") or []:
        path = str(route.get("path") or "").strip()
        if not path or path in served:
            continue
        # Only routes whose page actually exists — a route with no component is
        # dropped from the router on purpose, and re-adding it would break the
        # build.
        component = str(route.get("component_file") or "").replace("\\", "/")
        if component and component in pages:
            return True
    return False


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

    # 0a) The route table is generated, so restoring it is free and always
    # correct. Request 67's repair model was handed `src/App.tsx` to clear a
    # dead-link finding and cleared it by deleting the route:
    #
    #   {"op":"replace","path":"src/App.tsx",
    #    "old":"          <Route path=\"/collection\" element={<CollectionPage />} />",
    #    "new":"          "}
    #
    # 14 links on 7 pages then fell through `path="*"` to the home page, and an
    # earlier attempt had minted a duplicate `/gallery` that left `CollectionPage`
    # unreachable behind `GalleryPage`. `_write_if_parseable` waved both through
    # because deleting a `<Route>` parses perfectly.
    #
    # `App.tsx` is now generator-owned so no AI writer can reach it, but a guard
    # that only forbids is half a guard: this repairs the damage if it arrives by
    # some other road, and it is the sibling of "no writer may replace parseable
    # source with unparseable source" — **no writer may make a declared route
    # unreachable**.
    try:
        if _route_table_is_stale(workspace, architect):
            from app.application.preview_app.assemble import write_app_tsx
            from app.infrastructure.templating.renderer import get_template_renderer

            write_app_tsx(workspace, architect, get_template_renderer())
            healed.append("src/App.tsx")
            log.warning("quality gate healed: route table regenerated from architect")
    except Exception as e:  # noqa: BLE001 — a heal must never fail the gate
        log.warning("route table heal failed: %s", e)

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
                    minimal_catalogue_page_scaffold(rel, rt, brand_name=brand_name, architect=architect),
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
                minimal_catalogue_page_scaffold(rel, rt, brand_name=brand_name, architect=architect),
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
                minimal_catalogue_page_scaffold(rel, rt, brand_name=brand_name, architect=architect),
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

    # 10) Contact/auth utility faces — AI repair and mis-labeled skeletons must
    # not leave /contact as a marketing clone or a freeform page with dead legal
    # links (request 62 ContactPage → /privacy-policy, no InquiryPanel).
    try:
        from app.application.preview_app.safety.catalogue_guards import (
            enforce_catalogue_workspace_contracts,
        )

        restored = enforce_catalogue_workspace_contracts(
            workspace, architect, brand_name=brand_name or "Brand"
        )
        if restored:
            log.info("quality heal restored catalogue/utility faces: %s", ", ".join(restored))
            healed.extend(restored)
    except Exception as e:
        log.warning("quality heal catalogue contracts failed: %s", e)

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
    if healed:
        from app.application.preview_app.pipeline.visual_critic import (
            invalidate_visual_verdicts,
        )

        try:
            invalidate_visual_verdicts(workspace, healed)
        except Exception as e:  # noqa: BLE001 — never let bookkeeping fail a gate
            log.warning("could not retire stale visual verdicts: %s", e)

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

    # Same contract, same gap as the visual critic: `quality_repair` is ELECTIVE
    # and was never skipped, because `should_skip_elective` had one caller in the
    # whole tree. Past the deadline this loop snapshots the source, asks for a
    # repair plan that `ask_budget = 0` refuses, and rebuilds — all the disk and
    # vite cost, no repair. Request 76 spent 15 s of its 35 s tail here.
    from app.application.services.request_deadline import should_skip_elective

    if should_skip_elective("quality_repair"):
        log.warning(
            "quality gate AI repair skipped — past the deadline, so the repair ask "
            "would be refused and only the snapshot/rebuild cost would land"
        )
        return final

    from app.application.preview_app.quality_repair import run_ai_quality_repair

    for attempt in range(1, attempts + 1):
        # Taken before the repair so a failed rebuild can be undone rather than
        # left for the gate to judge against a `dist/` it never produced.
        pre_repair = snapshot_source(workspace)
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
                    # Roll back, the way the visual critic's refine pass does. Left
                    # in place, the repair means `evaluate_quality_gate` judges
                    # source that `dist/` was never built from: request 47 reported
                    # PASSED while its last two rebuilds had failed, and the served
                    # bundle was an older one whose `/artwork/:id` fell through to
                    # the home page.
                    log.warning(
                        "quality gate rebuild after AI repair failed — rolling back "
                        "%s file(s) so source and dist agree",
                        len(touched),
                    )
                    restore_source(workspace, pre_repair)
                    try:
                        restored_ok, _ = rebuild()
                        if not restored_ok:
                            log.error(
                                "quality gate rollback rebuild ALSO failed — "
                                "workspace may be inconsistent"
                            )
                    except Exception as e:
                        log.warning("quality gate rollback rebuild error: %s", e)
                    healed = [p for p in healed if p not in set(touched)]
                    touched = []
            except Exception as e:
                log.warning("quality gate rebuild error after AI repair: %s", e)

        if touched:
            # A visual verdict describes source. Once this repair replaced that
            # source, keeping the verdict makes the next `evaluate_quality_gate`
            # read a measurement of a page that no longer exists — and no amount of
            # repair can ever clear it.
            from app.application.preview_app.pipeline.visual_critic import (
                invalidate_visual_verdicts,
            )

            try:
                invalidate_visual_verdicts(workspace, [*touched, *more])
            except Exception as e:  # noqa: BLE001 — never let bookkeeping fail a gate
                log.warning("could not retire stale visual verdicts: %s", e)

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
