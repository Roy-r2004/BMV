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
#: `detailBase="/gallery"` — CatalogGrid turns this into one link per card.
_DETAIL_BASE_RE = re.compile(
    r"""detailBase\s*=\s*\{?\s*["'`](?P<base>/[A-Za-z0-9\-_/]*)"""
)


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


def _write(workspace: Path, rel: str, content: str) -> bool:
    try:
        (workspace / rel).write_text(content, encoding="utf-8")
        return True
    except OSError:
        return False


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
    """Literal in-app href targets (skips external, anchors, and templates).

    Template bases are deliberately *not* here. `` href={`/artwork/${id}`} `` is a
    prefix, not a URL: at runtime it resolves to `/artwork/<something>`, which a
    declared `/artwork/:id` serves — but comparing the bare base against the route
    table says it is dead. Request 44 was withheld on three such findings while
    every one of those links worked. Prefixes are checked by
    `internal_href_prefixes` against the rule that actually applies to them.
    """
    found: list[str] = []
    for match in _HREF_LITERAL_RE.finditer(source or ""):
        value = match.group("value").strip()
        if not value.startswith("/"):
            continue  # anchor, mailto:, external, or a template expression
        if "${" in value:
            continue
        # A fragment or a query is not part of the route. Request 46's contact page
        # linked its own form as `/contact#contact-form` and was blocked for it,
        # against a route table that declares `/contact`.
        target = value.split("#", 1)[0].split("?", 1)[0]
        if not target:
            continue  # a bare `#anchor` on the current page
        found.append(target)
    return found


def internal_href_prefixes(source: str) -> list[str]:
    """Bases of template-literal links: `` `/artwork/${id}` `` -> `/artwork`."""
    return [match.group("base") for match in _TEMPLATE_BASE_RE.finditer(source or "")]


def _prefix_is_served(prefix: str, declared: Iterable[str]) -> bool:
    """True when some declared route hangs under `prefix`.

    The link is `prefix + "/" + <value>`, so what must exist is a child route —
    `/artwork/:id` for `` `/artwork/${id}` `` — not `prefix` itself.
    """
    base = _norm(prefix)
    if base == "/":
        return True
    return any(_norm(candidate).startswith(base + "/") for candidate in declared)


#: Hrefs a storefront invents for its catalogue when the route is named something
#: else. Request 40's hero CTA said "View the Collection" and pointed at
#: `/collection` while the browse route was `/gallery`.
_BROWSE_SYNONYMS = (
    "collection", "collections", "gallery", "galleries", "shop", "store", "catalog",
    "catalogue", "products", "product", "works", "artwork", "artworks", "paintings",
    "pieces", "menu", "listings",
)
_CONTACT_SYNONYMS = ("contact", "inquire", "inquiry", "enquire", "book", "booking", "appointment")
_LISTING_PATH_RE = re.compile(
    r"^/(gallery|collection|collections|shop|catalog|catalogue|products|works|menu|"
    r"paintings|pieces|listings)(/|$)",
    re.I,
)


#: Footer boilerplate. A preview has no legal pages and should not pretend to; an
#: inert anchor is honest and, unlike a dead path, cannot bounce a visitor.
_INERT_LEAVES = frozenset(
    {"privacy", "terms", "policy", "policies", "cookies", "legal", "imprint",
     "disclaimer", "accessibility", "sitemap", "logout", "signout", "sign-out"}
)
#: Surface namespaces a link may address without naming a page inside them.
_SURFACE_LEAVES = frozenset({"admin", "owner", "ops", "staff", "dashboard", "login", "signin"})
_OPS_SURFACE_PREFIXES = ("/admin", "/owner", "/ops", "/staff", "/member", "/desk")


def _best_declared_target(href: str, declared: set[str]) -> str:
    """Nearest declared route for a dead internal link, or "" to leave it alone.

    Returns `"#"` for footer boilerplate: those links must be repairable, because
    the sweep blocks on a dead public link and a "Privacy Policy" in the footer
    would otherwise withhold a working storefront. Request 43 was withheld by
    exactly that — four of them, on an app whose funnel and rendering were clean.
    """
    target = _norm(href)
    segments = [s for s in target.strip("/").split("/") if s]
    leaf = segments[-1].lower() if segments else ""
    head = segments[0].lower() if segments else ""
    statics = sorted(p for p in declared if p and ":" not in p and "{" not in p and p != "/")

    def _first(predicate) -> str:
        return next((p for p in statics if predicate(p)), "")

    # Same leaf under a different parent — `/paintings` when `/owner/paintings` and
    # `/gallery` both exist prefers the public one by sort order.
    same_leaf = _first(lambda p: p.strip("/").split("/")[-1].lower() == leaf)
    if same_leaf:
        return same_leaf
    if leaf in _BROWSE_SYNONYMS:
        browse = _first(lambda p: bool(_LISTING_PATH_RE.match(p + "/")))
        if browse:
            return browse
    if leaf in _CONTACT_SYNONYMS:
        contact = _first(lambda p: any(word in p.lower() for word in _CONTACT_SYNONYMS))
        if contact:
            return contact
    # `/admin` on its own, or `/admin/logout` — send it to an ops entry page. The
    # named surface may not be the one this app declared: a page can link `/admin`
    # while the owner pages live under `/owner`.
    if leaf in _SURFACE_LEAVES or head in _SURFACE_LEAVES:
        entry = _first(lambda p: p.startswith(f"/{head}/")) or _first(
            lambda p: any(p.startswith(f"{root}/") for root in _OPS_SURFACE_PREFIXES)
        )
        if entry:
            return entry
        return "#"
    if leaf in _INERT_LEAVES or head in _INERT_LEAVES:
        return "#"
    return ""


def repair_dead_internal_links(
    workspace: Path, architect: Mapping[str, Any]
) -> list[str]:
    """Point public dead links at the route they meant. Returns healed files.

    Deterministic counterpart to the sweep's new BLOCK on public surfaces: a dead
    primary CTA is worth failing the gate over only because this can fix it
    without a model call. Links with no plausible target are left for the AI
    repair pass rather than guessed at.
    """
    declared = declared_route_paths(architect)
    healed: list[str] = []
    for route in _routes(architect):
        if _surface(route) != "public":
            continue
        rel = str(route.get("component_file") or "").replace("\\", "/")
        if not rel:
            continue
        src = _read(workspace, rel)
        if not src:
            continue
        updated = src
        for href in sorted(set(internal_hrefs(src)), key=len, reverse=True):
            if _route_matches(href, declared):
                continue
            replacement = _best_declared_target(href, declared)
            if not replacement or replacement == _norm(href):
                continue
            for quote in ('"', "'", "`"):
                updated = updated.replace(f"{quote}{href}{quote}", f"{quote}{replacement}{quote}")
        # A template base is repaired in place: `` `/artwork/${id}` `` -> `` `/gallery/${id}` ``.
        for prefix in sorted(set(internal_href_prefixes(src)), key=len, reverse=True):
            if _prefix_is_served(prefix, declared):
                continue
            replacement = _best_declared_target(prefix, declared)
            if not replacement or replacement in ("#", _norm(prefix)):
                continue
            updated = updated.replace(f"{prefix}/${{", f"{replacement}/${{")
        if updated != src:
            _write(workspace, rel, updated)
            healed.append(rel)
    return healed


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
    """Dead-link sweep over every page the journey does not walk.

    Blocking follows *surface*, not hop membership. Ops pages stay advisory: a
    dead link on an owner-only page is a real defect, but withholding a correct
    public storefront over it is the failure mode logged as P0-4.

    A public page is different. Request 40's home page pointed both of its primary
    CTAs — "View the Collection" and "View Available Paintings" — at `/collection`,
    a path no route serves, so the first thing a visitor clicked bounced them back
    to the page they were on. That was reported as a warning purely because
    HomePage is not the designated browse hop, and the preview shipped `ready`.
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
        surface = _surface(route)
        dead = [h for h in sorted(set(internal_hrefs(src))) if not _route_matches(h, declared)]
        dead += [
            p for p in sorted(set(internal_href_prefixes(src)))
            if not _prefix_is_served(p, declared)
        ]
        for href in dead:
            report.add(
                "journey_dead_link_offpath",
                f"{rel} links to {href}, which no declared route serves",
                swept,
                surface=surface,
                component_file=rel,
                path=_norm(str(route.get("path") or "")),
                advisory=surface != "public",
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
    referenced = set(internal_hrefs(src)) | set(internal_href_prefixes(src)) | {
        # `CatalogGrid` derives `${detailBase}/${item.id}` for every card, so a
        # declared detailBase is a real item link even with no `href` in sight.
        m.group("base") for m in _DETAIL_BASE_RE.finditer(src)
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
    dead = [h for h in sorted(set(internal_hrefs(src))) if not _route_matches(h, declared)]
    dead += [
        p for p in sorted(set(internal_href_prefixes(src)))
        if not _prefix_is_served(p, declared)
    ]
    for href in dead:
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
