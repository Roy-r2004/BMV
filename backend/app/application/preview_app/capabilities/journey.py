"""The journey contract — validates the path *between* pages.

Every other check in this pipeline validates a page in isolation: right skeleton,
right shell, required components present, assets reachable, types clean. All of
them passed on a storefront whose visitor could not browse a collection, open an
item, or ask about it — because nothing checked the edges of the graph.

A journey is a declared sequence of hops per product kind. ``walk_journey``
inspects the generated workspace and reports each broken hop with the surface it
sits on, so the gate can block a public funnel while only warning on ops.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.application.preview_app.capabilities.registry import (
    Capability,
    resolve_capabilities,
)

#: Components that can render a browsable list of linked items.
LISTING_COMPONENTS = ("CatalogGrid", "ProductShowcase", "ScheduleRail")

#: How a page reads its own route parameter.
#
#: Must match the *call*, not the import: `import { useParams } from ...` is
#: present on a page that imports the hook and never calls it, and an earlier
#: version of this pattern accepted the bare word, so a detail page that had
#: stopped resolving its param still passed.
_PARAM_READ_RE = re.compile(r"\buseParams\s*[<(]")

#: Routes other pipeline stages add after the gate first runs. A link to one of
#: these is reported, but never blocking — the route may legitimately appear
#: later, and a false withhold is worse than a late warning.
_CONDITIONAL_ROUTES = frozenset({"/ai-features"})

#: href values in emitted TSX: href="/x", href: "/x", href={`/x/${...}`}
_HREF_LITERAL_RE = re.compile(r"""href\s*[:=]\s*\{?\s*["'`](?P<value>[^"'`]+)""")
#: Template-literal bases: `/gallery/${...}` → "/gallery"
_TEMPLATE_BASE_RE = re.compile(r"[\"'`](?P<base>/[A-Za-z0-9\-_/]*?)/\$\{")


@dataclass(frozen=True)
class JourneyHop:
    """One edge of the funnel."""

    id: str
    #: "browse" | "detail" | "terminal"
    kind: str
    #: Declared route path pattern this hop lives on, e.g. "/gallery/:id".
    path_hint: str
    label: str


@dataclass(frozen=True)
class Journey:
    product_kind: str
    hops: tuple[JourneyHop, ...]
    #: Capability that closes the funnel.
    terminal_capability: str


@dataclass
class HopFinding:
    code: str
    message: str
    hop_id: str
    path: str
    surface: str
    component_file: str = ""
    #: Reported but never blocking, whatever the surface.
    advisory: bool = False

    @property
    def public(self) -> bool:
        """Blocking-eligible: a public-surface break that is not advisory.

        Mirrors ``asset_integrity.blocking_missing_assets()``, which blocks only
        on ``ref.public_surface``. Blocking on an owner-only page would withhold
        a correct public storefront.
        """
        return self.surface != "ops" and not self.advisory


@dataclass
class JourneyReport:
    product_kind: str
    findings: list[HopFinding] = field(default_factory=list)
    #: Hops that were located and passed every check.
    hops_ok: list[str] = field(default_factory=list)
    #: Hops whose route is absent from the architect entirely.
    hops_absent: list[str] = field(default_factory=list)

    def add(
        self,
        code: str,
        message: str,
        hop: JourneyHop,
        *,
        surface: str,
        component_file: str = "",
        path: str = "",
        advisory: bool = False,
    ) -> None:
        self.findings.append(
            HopFinding(
                code=code,
                message=message,
                hop_id=hop.id,
                path=path or hop.path_hint,
                surface=surface,
                component_file=component_file,
                advisory=advisory,
            )
        )

    @property
    def ok(self) -> bool:
        return not self.findings

    @property
    def blocking(self) -> list[HopFinding]:
        """Public-surface breaks. A broken public funnel ships an unusable demo."""
        return [f for f in self.findings if f.public]

    @property
    def warnings(self) -> list[HopFinding]:
        return [f for f in self.findings if not f.public]

    def summary(self) -> dict[str, Any]:
        """Shape carried into the API result so 'ready' is not read blindly."""
        return {
            "product_kind": self.product_kind,
            "hops_ok": list(self.hops_ok),
            "hops_absent": list(self.hops_absent),
            "broken": [
                {
                    "code": f.code,
                    "hop": f.hop_id,
                    "path": f.path,
                    "surface": f.surface,
                    "message": f.message,
                }
                for f in self.findings
            ],
        }


JOURNEYS: dict[str, Journey] = {
    "storefront": Journey(
        product_kind="storefront",
        terminal_capability="inquiry",
        hops=(
            JourneyHop("browse", "browse", "/gallery", "Browse the collection"),
            JourneyHop("detail", "detail", "/gallery/:id", "Open one item"),
            JourneyHop("inquire", "terminal", "/gallery/:id", "Ask about it"),
        ),
    ),
    "booking_service": Journey(
        product_kind="booking_service",
        terminal_capability="booking",
        hops=(
            JourneyHop("browse", "browse", "/services", "Browse services"),
            JourneyHop("book", "terminal", "/book", "Book a time"),
        ),
    ),
}


def journey_for(product_kind: str) -> Journey | None:
    return JOURNEYS.get(str(product_kind or "").strip().lower())


# --------------------------------------------------------------------------- #
# workspace helpers
# --------------------------------------------------------------------------- #


def _read(workspace: Path, rel: str) -> str:
    if not rel:
        return ""
    try:
        return (workspace / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _routes(architect: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [r for r in (architect.get("routes") or []) if isinstance(r, dict)]


def _surface(route: Mapping[str, Any]) -> str:
    return str(route.get("surface") or "public").strip().lower() or "public"


def _is_param_path(path: str) -> bool:
    return bool(re.search(r"/:\w+|/\{[^}]+\}", path or ""))


def _norm(path: str) -> str:
    p = "/" + str(path or "").strip().strip("/")
    return p.rstrip("/") or "/"


def declared_route_paths(architect: Mapping[str, Any]) -> set[str]:
    return {_norm(str(r.get("path") or "")) for r in _routes(architect)}


def _route_matches(path: str, declared: Iterable[str]) -> bool:
    """True when ``path`` is served by a declared route, params included.

    ``/gallery/3`` is served by a declared ``/gallery/:id``.
    """
    target = _norm(path)
    for candidate in declared:
        if candidate == target:
            return True
        c_parts = candidate.strip("/").split("/")
        t_parts = target.strip("/").split("/")
        if len(c_parts) != len(t_parts):
            continue
        if all(
            cp.startswith(":") or cp.startswith("{") or cp == tp
            for cp, tp in zip(c_parts, t_parts)
        ):
            return True
    return False


def _find_route(
    architect: Mapping[str, Any], hop: JourneyHop, *, want_param: bool
) -> dict[str, Any] | None:
    """Locate the route serving a hop.

    Prefers an exact path match on the hint, then any public route whose shape
    fits (param vs non-param) and whose first segment matches. Generated apps
    rename routes freely — ``/works`` for ``/gallery`` — so shape beats literal.
    """
    routes = [r for r in _routes(architect) if _surface(r) != "ops"]
    hint = _norm(hop.path_hint)
    for route in routes:
        if _norm(str(route.get("path") or "")) == hint:
            return route
    stem = hint.strip("/").split("/")[0]
    candidates = [
        r
        for r in routes
        if _is_param_path(str(r.get("path") or "")) is want_param
        and _norm(str(r.get("path") or "")).strip("/").split("/")[0] == stem
    ]
    if candidates:
        return candidates[0]
    # Fall back on shape alone for the detail hop: a single param route is it.
    if want_param:
        param_routes = [r for r in routes if _is_param_path(str(r.get("path") or ""))]
        if len(param_routes) == 1:
            return param_routes[0]
    return None


def internal_hrefs(source: str) -> list[str]:
    """In-app href targets referenced by a page (skips external and anchors)."""
    found: list[str] = []
    for match in _HREF_LITERAL_RE.finditer(source or ""):
        value = match.group("value").strip()
        if not value.startswith("/"):
            continue  # anchor, mailto:, external, or a template expression
        if "${" in value:
            continue
        found.append(value)
    for match in _TEMPLATE_BASE_RE.finditer(source or ""):
        found.append(match.group("base"))
    return found


# --------------------------------------------------------------------------- #
# the walk
# --------------------------------------------------------------------------- #


def walk_journey(
    workspace: Path,
    architect: Mapping[str, Any],
    *,
    pack: Mapping[str, Any] | None = None,
) -> JourneyReport:
    """Check that the declared funnel actually works in the generated workspace."""
    product_kind = str(architect.get("product_kind") or "").strip().lower()
    report = JourneyReport(product_kind=product_kind)
    journey = journey_for(product_kind)
    if journey is None:
        return report

    caps = resolve_capabilities(product_kind, pack)
    terminal = next(
        (c for c in caps if c.id == journey.terminal_capability),
        None,
    )
    declared = declared_route_paths(architect)

    for hop in journey.hops:
        want_param = _is_param_path(hop.path_hint)
        route = _find_route(architect, hop, want_param=want_param)
        if route is None:
            report.hops_absent.append(hop.id)
            continue
        rel = str(route.get("component_file") or "").replace("\\", "/")
        src = _read(workspace, rel)
        path = _norm(str(route.get("path") or ""))
        surface = _surface(route)
        if not src:
            report.add(
                "journey_page_missing",
                f"{hop.label}: {rel or path} has no source",
                hop,
                surface=surface,
                component_file=rel,
                path=path,
            )
            continue

        # Count blocking only: an advisory finding (a conditional route, an ops
        # page) must not strike a hop out of hops_ok, or the summary under-reports
        # a funnel that actually works.
        before = len(report.blocking)

        if hop.kind == "browse":
            _check_browse(
                report, hop, src, path, surface, rel, declared, architect, journey
            )
        elif hop.kind == "detail":
            _check_detail(report, hop, src, path, surface, rel)
        elif hop.kind == "terminal":
            _check_terminal(report, hop, src, path, surface, rel, terminal)

        _check_dead_links(report, hop, src, path, surface, rel, declared)

        if len(report.blocking) == before:
            report.hops_ok.append(hop.id)

    _sweep_non_hop_links(report, workspace, architect, journey, declared)
    return report


def _sweep_non_hop_links(
    report: JourneyReport,
    workspace: Path,
    architect: Mapping[str, Any],
    journey: Journey,
    declared: set[str],
) -> None:
    """Advisory dead-link sweep over every page the journey does not walk.

    Blocking is confined to the funnel on purpose. A dead link on an admin page
    is a real defect worth surfacing, but withholding a correct public storefront
    over an owner-only page is the failure mode already logged as P0-4.
    """
    walked = set()
    for hop in journey.hops:
        route = _find_route(architect, hop, want_param=_is_param_path(hop.path_hint))
        if route is not None:
            walked.add(str(route.get("component_file") or "").replace("\\", "/"))
    swept = JourneyHop("other-pages", "sweep", "", "Other pages")
    for route in _routes(architect):
        rel = str(route.get("component_file") or "").replace("\\", "/")
        if not rel or rel in walked:
            continue
        src = _read(workspace, rel)
        if not src:
            continue
        for href in sorted(set(internal_hrefs(src))):
            if _route_matches(href, declared):
                continue
            report.add(
                "journey_dead_link_offpath",
                f"{rel} links to {href}, which no declared route serves",
                swept,
                surface=_surface(route),
                component_file=rel,
                path=_norm(str(route.get("path") or "")),
                advisory=True,
            )


def _check_browse(
    report: JourneyReport,
    hop: JourneyHop,
    src: str,
    path: str,
    surface: str,
    rel: str,
    declared: set[str],
    architect: Mapping[str, Any],
    journey: Journey,
) -> None:
    if not any(name in src for name in LISTING_COMPONENTS):
        report.add(
            "journey_browse_not_listing",
            f"{hop.label}: page renders no listing component "
            f"({'/'.join(LISTING_COMPONENTS)})",
            hop,
            surface=surface,
            component_file=rel,
            path=path,
        )
        return
    # ProductShowcase renders at most three items — a catalogue needs the grid.
    if "CatalogGrid" not in src and "ScheduleRail" not in src and "ProductShowcase" in src:
        report.add(
            "journey_browse_caps_items",
            f"{hop.label}: ProductShowcase renders at most 3 items; a browse page "
            "needs CatalogGrid so the whole collection is reachable",
            hop,
            surface=surface,
            component_file=rel,
            path=path,
        )
    # Where should a row lead? The hop after this one — a detail page for a
    # storefront, the booking page for a service business.
    hop_ids = [h.id for h in journey.hops]
    next_hop = journey.hops[hop_ids.index(hop.id) + 1] if hop.id in hop_ids[:-1] else None
    if next_hop is None:
        return
    if next_hop.kind == "detail":
        param_routes = [
            _norm(str(r.get("path") or ""))
            for r in _routes(architect)
            if _is_param_path(str(r.get("path") or "")) and _surface(r) != "ops"
        ]
        if not param_routes:
            report.add(
                "journey_no_detail_route",
                f"{hop.label}: no detail route is declared, so items cannot be opened",
                hop,
                surface=surface,
                component_file=rel,
                path=path,
            )
            return
        detail_bases = {p.split("/:")[0].split("/{")[0] or "/" for p in param_routes}
    else:
        # Terminal next hop: rows must reach it, and it must exist.
        target = _norm(next_hop.path_hint)
        if not _route_matches(target, declared):
            report.add(
                "journey_next_hop_missing",
                f"{hop.label}: the next step ({target}) is not a declared route",
                hop,
                surface=surface,
                component_file=rel,
                path=path,
            )
            return
        detail_bases = {target}
    referenced = set(internal_hrefs(src)) | {
        m.group("base") for m in _TEMPLATE_BASE_RE.finditer(src)
    }
    if not any(
        _norm(ref).startswith(_norm(base)) for ref in referenced for base in detail_bases
    ):
        report.add(
            "journey_browse_not_linked",
            f"{hop.label}: no item link points at a detail route "
            f"({', '.join(sorted(detail_bases))})",
            hop,
            surface=surface,
            component_file=rel,
            path=path,
        )


def _check_detail(
    report: JourneyReport,
    hop: JourneyHop,
    src: str,
    path: str,
    surface: str,
    rel: str,
) -> None:
    if not _PARAM_READ_RE.search(src):
        report.add(
            "journey_detail_ignores_param",
            f"{hop.label}: page never reads its route param, so every item shows "
            "the same content",
            hop,
            surface=surface,
            component_file=rel,
            path=path,
        )


def _check_terminal(
    report: JourneyReport,
    hop: JourneyHop,
    src: str,
    path: str,
    surface: str,
    rel: str,
    terminal: Capability | None,
) -> None:
    if terminal is None:
        return
    if terminal.component not in src:
        report.add(
            terminal.missing_code,
            f"{hop.label}: {terminal.component} is absent, so the funnel has no "
            "way to end",
            hop,
            surface=surface,
            component_file=rel,
            path=path,
        )


def _check_dead_links(
    report: JourneyReport,
    hop: JourneyHop,
    src: str,
    path: str,
    surface: str,
    rel: str,
    declared: set[str],
) -> None:
    """Generalises `dead_ai_step_link` to every in-app href on a journey page."""
    for href in sorted(set(internal_hrefs(src))):
        if _route_matches(href, declared):
            continue
        conditional = _norm(href) in _CONDITIONAL_ROUTES
        report.add(
            "journey_dead_link",
            f"{hop.label}: links to {href}, which no declared route serves",
            hop,
            surface=surface,
            component_file=rel,
            path=path,
            advisory=conditional,
        )


def journey_gate_issues(report: JourneyReport) -> list[tuple[str, str, str]]:
    """(code, message, path) for public breaks only.

    Ops surfaces warn: mirrors ``asset_integrity.blocking_missing_assets()``,
    where only ``ref.public_surface`` blocks. Blocking on an owner-only page
    would withhold a correct public storefront — the P0-4 failure mode.
    """
    return [
        (f.code, f.message, f.component_file or f.path) for f in report.blocking
    ]
