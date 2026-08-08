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


def _renders(src: str, component: str) -> bool:
    """True when the source *mounts* the component, not merely names it.

    Same rule as `_PARAM_READ_RE` below: match the call, not the mention. The
    directory-listing scaffold carries the comment "ProductShowcase used to fill
    this slot and silently showed only three", and a bare substring test read
    that as a listing component — so a browse page with no grid at all reported
    `journey_browse_caps_items` instead of `journey_browse_not_listing`, and a
    page could have satisfied the listing requirement with a comment.
    """
    return f"<{component}" in src

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

#: Owner-surface namespaces. A served path under one of these is not a public
#: detail route, and `App.tsx` carries no `surface` field to ask instead.
_OPS_PATH_PREFIXES = ("/admin", "/owner", "/ops", "/staff", "/member", "/desk")

#: Link-bearing keys. `defaultPath` is a role's landing route — a dead one drops
#: the visitor on the catch-all exactly like a dead nav item does.
_LINK_KEYS = "href|defaultPath"
#: href values in emitted TSX **and** in the JSON-shaped props the writers emit.
#:
#: The key may be quoted. Request 71's `InquiryConfirmationPage.tsx:24` carried
#: `nextSteps={[{"title": …, "href": "/about"}, …]}` and `src/data/mock.ts` holds
#: the whole nav, footer and hero CTA set as `"href": "/gallery"`. The old
#: pattern required `href` to be followed directly by `:` or `=`, so a quoted key
#: never matched and **every link the generator emits as data was invisible to
#: the sweep** — including the primary nav item on all eight public routes.
_HREF_LITERAL_RE = re.compile(
    rf"""(?<![\w-])["']?(?:{_LINK_KEYS})["']?\s*[:=]\s*\{{?\s*["'`](?P<value>[^"'`]+)"""
)
#: Whole template-literal link: `` href={`/gallery/${id}`} ``.
_TEMPLATE_HREF_RE = re.compile(
    rf"""(?<![\w-])["']?(?:{_LINK_KEYS})["']?\s*[:=]\s*\{{?\s*`(?P<value>/[^`]*)`"""
)
#: Template-literal bases: `/gallery/${...}` → "/gallery"
_TEMPLATE_BASE_RE = re.compile(r"[\"'`](?P<base>/[A-Za-z0-9\-_/]*?)/\$\{")
#: `detailBase="/gallery"` — CatalogGrid turns this into one link per card.
_DETAIL_BASE_RE = re.compile(
    r"""detailBase\s*=\s*\{?\s*["'`](?P<base>/[A-Za-z0-9\-_/]*)"""
)
#: Every `<Route path="…">` the shipped router declares.
_ROUTE_PATH_RE = re.compile(r'<Route\s+path="([^"]+)"')
#: Modules every page renders but no route names. `src/data/mock.ts` holds the
#: nav, the footer, the role landing paths and the hero CTAs — read by the whole
#: app, scanned by nothing, and the source of 11 of request 71's 13 dead hrefs.
_SHARED_LINK_SOURCES = ("src/data/mock.ts",)


@dataclass(frozen=True)
class JourneyHop:
    """One edge of the funnel."""

    id: str
    #: "browse" | "detail" | "terminal"
    kind: str
    #: Declared route path pattern this hop lives on, e.g. "/gallery/:id".
    #:
    #: A *hint*, and only that. The architect names routes for the business, so
    #: `/gallery` is `/bikes` on request 148 and `/book` is `/hire/reserve` on 150.
    path_hint: str
    label: str
    #: The skeleton the architect assigns to the page serving this hop. This is
    #: the rename-proof half of the pair: `_find_route` tries the hint first, then
    #: this, and only then falls back to first-segment matching. `/hire/reserve`
    #: shares no stem with `/book`, which is exactly how 150's terminal hop
    #: resolved to nothing and reported `journey_next_hop_missing` against a
    #: booking page the app had.
    skeleton_id: str = ""


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
    #: The dead href this finding is about, when it is a link finding.
    href: str = ""
    #: How many times it appears in this file. A repair that rewrites two of
    #: three occurrences must not be able to present itself as a fix: the
    #: re-walk reports the survivor with a smaller count, never nothing.
    occurrences: int = 1

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
        href: str = "",
        occurrences: int = 1,
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
                href=href,
                occurrences=occurrences,
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
                    **({"href": f.href} if f.href else {}),
                    **({"file": f.component_file} if f.component_file else {}),
                    **({"occurrences": f.occurrences} if f.occurrences != 1 else {}),
                }
                for f in self.findings
            ],
            # Every occurrence, not every finding. Request 71 reported 2 and
            # shipped 13; a count that only ever equals the finding count cannot
            # tell those apart.
            "dead_link_occurrences": sum(
                f.occurrences for f in self.findings if f.href
            ),
        }


JOURNEYS: dict[str, Journey] = {
    "storefront": Journey(
        product_kind="storefront",
        terminal_capability="inquiry",
        hops=(
            JourneyHop("browse", "browse", "/gallery", "Browse the collection",
                       skeleton_id="public-catalog"),
            JourneyHop("detail", "detail", "/gallery/:id", "Open one item",
                       skeleton_id="public-detail"),
            JourneyHop("inquire", "terminal", "/gallery/:id", "Ask about it",
                       skeleton_id="public-detail"),
        ),
    ),
    "booking_service": Journey(
        product_kind="booking_service",
        terminal_capability="booking",
        hops=(
            JourneyHop("browse", "browse", "/services", "Browse services",
                       skeleton_id="public-service"),
            JourneyHop("book", "terminal", "/book", "Book a time",
                       skeleton_id="public-booking"),
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


def rendered_route_paths(workspace: Path) -> set[str]:
    """Paths the shipped router actually serves, read from `src/App.tsx`.

    The catch-all is excluded on purpose: `<Route path="*">` serves every URL by
    redirecting home, which is precisely how a dead link disguises itself.
    """
    source = _read(workspace, "src/App.tsx")
    return {
        _norm(p) for p in _ROUTE_PATH_RE.findall(source) if p and "*" not in p
    }


def served_route_paths(
    workspace: Path, architect: Mapping[str, Any]
) -> set[str]:
    """The route table a *visitor* meets — not the one the planner declared.

    These two diverge silently. Request 71's architect declared `/gallery` onto
    `GalleryHomePage.tsx`, `/` had already claimed that file, and
    `assemble._resolve_page` dropped the route without a word. `App.tsx` shipped
    13 routes; the sweep compared every href against the architect's 14, found
    `/gallery` among them, and passed the primary nav item, the footer link and
    the "View collection" hero CTA on all eight public routes.

    Falls back to the architect when there is no router on disk yet — the same
    fail-open `_route_table_is_stale` takes, because a walk that runs before
    assembly must not invent 13 blockers.
    """
    rendered = rendered_route_paths(workspace)
    return rendered or declared_route_paths(architect)


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

    Exact path match on the hint, then the hop's declared skeleton, then any
    public route whose shape fits (param vs non-param) and whose first segment
    matches. Generated apps rename routes freely — ``/works`` for ``/gallery`` —
    so shape beats literal.

    The skeleton pass sits *before* the stem pass because the stem pass only
    tolerates renames that keep the first segment. ``/hire/reserve`` shares none
    with ``/book``, so request 150's terminal hop resolved to nothing and the walk
    reported the booking page missing on an app that had one. Stem matching stays
    as the fallback: a thin contract with no ``skeleton_id`` on any route still
    resolves exactly as it did.
    """
    routes = [r for r in _routes(architect) if _surface(r) != "ops"]
    hint = _norm(hop.path_hint)
    for route in routes:
        if _norm(str(route.get("path") or "")) == hint:
            return route
    if hop.skeleton_id:
        # Shape still has to agree: a `public-detail` route with no param in it
        # cannot serve the detail hop, and resolving to it would report a page
        # for not reading a route param it has no business reading.
        by_skeleton = [
            r
            for r in routes
            if str(r.get("skeleton_id") or "") == hop.skeleton_id
            and _is_param_path(str(r.get("path") or "")) is want_param
        ]
        if by_skeleton:
            return by_skeleton[0]
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


#: Stands in for one whole `${…}` group while a template link is split into
#: segments. A control character, so it can never collide with source text.
_INTERPOLATION_MARK = "\x00"


def _mask_interpolations(raw: str) -> str:
    """Replace every balanced ``${…}`` group with a single `_INTERPOLATION_MARK`.

    Splitting the raw href on "/" *before* masking is what requests 146 and 148
    died on. An interpolation is arbitrary JavaScript and may contain slashes of
    its own — a regex literal is the common case::

        `/gallery/${item.title.toLowerCase().replace(/\\s+/g, '-')}`

    The old code split first, so the `/` inside `/\\s+/g` opened two extra
    segments and the link resolved to ``/gallery/:_/\\s+/g, '-'))}`` — which
    matches nothing, and both runs were withheld for a dead link that worked.
    The bakery declared `/gallery/:id` and the bike shop `/bikes/:id`; masking
    first, both resolve to `/gallery/:_` and `/bikes/:_` and match.

    Depth-counted rather than regex-matched because interpolations nest:
    ``${items.map(i => ({ id: i.id }))}`` is one group, and `\\$\\{[^}]*\\}`
    stops at the first inner `}`. An unterminated group consumes the rest of the
    string — a truncated template has no further segments worth trusting.

    Braces inside a *string literal* within the interpolation (``${x.replace("}",
    "")}``) would still miscount. Nothing the generator emits does that, and the
    failure mode is the pre-existing one — an over-long shape that fails to
    match — not a link silently declared healthy.
    """
    out: list[str] = []
    i = 0
    end = len(raw)
    while i < end:
        if not raw.startswith("${", i):
            out.append(raw[i])
            i += 1
            continue
        depth = 1
        j = i + 2
        while j < end and depth:
            if raw[j] == "{":
                depth += 1
            elif raw[j] == "}":
                depth -= 1
            j += 1
        out.append(_INTERPOLATION_MARK)
        i = j
    return "".join(out)


def internal_href_templates(source: str) -> list[str]:
    """Template-literal links resolved to the *path shape* they produce.

    `` href={`/gallery/${item.id}`} `` -> `/gallery/:_`, which `_route_matches`
    then answers against the real table.

    This is strictly better than testing the bare base with `_prefix_is_served`.
    `` `/owner/paintings/${painting.id}` `` has a base of `/owner/paintings`, and
    `/owner/paintings/add` hangs under it, so the base test said "served" — while
    the link resolves to `/owner/paintings/painting-1`, which no route matches.
    Request 71 shipped exactly that. The shape test keeps request 44's fix
    intact: `` `/artwork/${id}` `` becomes `/artwork/:_` and a declared
    `/artwork/:id` still serves it.
    """
    out: list[str] = []
    for match in _TEMPLATE_HREF_RE.finditer(source or ""):
        raw = match.group("value")
        if "${" not in raw:
            continue  # a plain literal in backticks — `internal_hrefs` has it
        # Mask before *any* splitting: see `_mask_interpolations` for why the
        # reverse order withheld two working previews. The fragment and query
        # strip is cut the same way — `${…}` is opaque JavaScript that may hold a
        # "#" or a "?" as readily as it holds a "/", and truncating there loses
        # the rest of the path.
        masked = _mask_interpolations(raw).split("#", 1)[0].split("?", 1)[0]
        segments = [
            ":_" if _INTERPOLATION_MARK in seg else seg
            for seg in masked.strip("/").split("/")
        ]
        out.append(_norm("/".join(segments)))
    return out


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
    {
        "privacy",
        "privacy-policy",
        "privacypolicy",
        "terms",
        "terms-of-service",
        "terms-of-use",
        "tos",
        "policy",
        "policies",
        "cookies",
        "cookie-policy",
        "legal",
        "imprint",
        "disclaimer",
        "accessibility",
        "sitemap",
        "logout",
        "signout",
        "sign-out",
    }
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
    # `/about` when the route is `/about-artist`. Request 71's hero CTA "About
    # the Artist" pointed at `/about`; the *model* repaired it to `/about-artist`
    # on one page and the other two occurrences shipped. A rename this obvious
    # should never need a model call, and a blocker the deterministic repair
    # cannot clear is a withheld preview.
    if leaf:
        kin = _first(
            lambda p: p.strip("/").split("/")[-1].lower().startswith(f"{leaf}-")
        )
        if kin:
            return kin
    if leaf in _BROWSE_SYNONYMS:
        browse = _first(lambda p: bool(_LISTING_PATH_RE.match(p + "/")))
        if browse:
            return browse
    # `/paintings/return-to-previous` — a listing namespace with an invented
    # leaf under it. The listing itself is the honest destination.
    if head in _BROWSE_SYNONYMS and len(segments) > 1:
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


#: A confirmation page is where a form *sends* you, never where a link takes you.
_CONFIRMATION_LEAF_RE = re.compile(
    r"^(inquiry|enquiry|order|booking|payment|checkout|contact)?[-_]?"
    r"(confirm|confirmed|confirmation|thank[-_]?you|thanks|success|receipt|complete|completed|sent)$"
)


def _is_confirmation_path(href: str) -> bool:
    leaf = _norm(href).rstrip("/").rsplit("/", 1)[-1].lower()
    return bool(leaf) and bool(_CONFIRMATION_LEAF_RE.match(leaf))


def _contact_target(declared: set[str], src: str) -> str:
    """A route that can actually take an inquiry, or "" when there is none."""
    for path in sorted(declared, key=len):
        leaf = path.rstrip("/").rsplit("/", 1)[-1].lower()
        if _is_confirmation_path(path):
            continue
        if leaf in {"contact", "contact-us", "inquire", "inquiry", "enquire", "enquiry", "get-in-touch"}:
            return path
    # No contact route: the page's own inquiry form is still a real destination.
    if "<InquiryPanel" in src:
        return "#inquire"
    return ""


def repair_dead_internal_links(
    workspace: Path, architect: Mapping[str, Any]
) -> list[str]:
    """Point public dead links at the route they meant. Returns healed files.

    Deterministic counterpart to the sweep's new BLOCK on public surfaces: a dead
    primary CTA is worth failing the gate over only because this can fix it
    without a model call. Links with no plausible target are left for the AI
    repair pass rather than guessed at.

    Reads the same table the sweep blocks on — the routes `App.tsx` actually
    serves. Repairing against a *different* table than the one that blocks is a
    livelock: the gate fails on a link the repair believes is fine.
    """
    declared = served_route_paths(workspace, architect)
    healed: list[str] = []
    for rel in _link_bearing_files(workspace, architect, public_only=True):
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
        for shape in sorted(set(internal_href_templates(src)), key=len, reverse=True):
            if _route_matches(shape, declared):
                continue
            prefix = shape.split("/:_", 1)[0] or "/"
            replacement = _best_declared_target(prefix, declared)
            if not replacement or replacement in ("#", _norm(prefix)):
                continue
            updated = updated.replace(f"{prefix}/${{", f"{replacement}/${{")
        # Links that resolve, to a page that cannot do what the label promises.
        # Request 66 pointed "Contact", "Contact the Gallery", "Arrange a Studio
        # Visit" and "Inquire Now" — home, collection and every footer — at
        # `/inquiry-confirm`: `h1: "Inquiry Sent"`, zero inputs, and body copy
        # thanking the visitor for a message about a painting not in the
        # catalogue. The dead-link sweep above cannot see it because the route is
        # declared and renders fine; it is the wrong destination, not a missing
        # one. Only repointed when there is somewhere real to go — an invented
        # target is the guess this repair exists to avoid.
        #
        # Scoped to page source on purpose. `src/data/mock.ts` carries a nav item
        # whose *label* is "Inquiry Confirm" and whose href correctly points at
        # `/inquiry-confirm`; repointing that at `/contact` mints a duplicate nav
        # entry and loses a declared page. The wrong-destination rule is about a
        # CTA's promise, and only a page makes one.
        confirm_hrefs = (
            [h for h in set(internal_hrefs(updated)) if _is_confirmation_path(h)]
            if rel not in _SHARED_LINK_SOURCES
            else []
        )
        if confirm_hrefs:
            target = _contact_target(declared, updated)
            if target:
                for href in sorted(confirm_hrefs, key=len, reverse=True):
                    if _norm(href) == _norm(target):
                        continue
                    for quote in ('"', "'", "`"):
                        updated = updated.replace(
                            f"{quote}{href}{quote}", f"{quote}{target}{quote}"
                        )
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
    # Every check below answers against the table `App.tsx` serves, not the one
    # the architect declared. See `served_route_paths`.
    declared = served_route_paths(workspace, architect)

    # One dead-link pass over the whole app, keyed on the file. Two hops sharing
    # a component used to run the check twice and report the same href twice:
    # request 71's "2 findings" were **one** dead `/about` in **one** file,
    # counted once for the detail hop and once for the inquire hop, both landing
    # on `ArtworkDetailPage.tsx`.
    dead_by_file = _collect_dead_links(workspace, architect, declared)
    reported_files: set[str] = set()

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

        links = dead_by_file.get(rel, ())
        if rel not in reported_files:
            reported_files.add(rel)
            _emit_dead_links(report, hop, "journey_dead_link", links, path, rel)

        # A second hop on the same page does not re-report the link, but it is
        # not `ok` either — the page it sits on has a blocking dead link.
        if len(report.blocking) == before and not any(
            link.blocking for link in links
        ):
            report.hops_ok.append(hop.id)

    _sweep_non_hop_links(report, dead_by_file, reported_files)
    return report


@dataclass(frozen=True)
class DeadLink:
    """One dead href, in one file, with every occurrence of it in that file."""

    file: str
    href: str
    occurrences: int
    surface: str
    route_path: str
    advisory: bool

    @property
    def blocking(self) -> bool:
        return self.surface != "ops" and not self.advisory


def _link_bearing_files(
    workspace: Path,
    architect: Mapping[str, Any],
    *,
    public_only: bool = False,
) -> list[str]:
    """Every file that can put a link on a page, in a stable order.

    Route components **and** the shared modules every page renders. The nav item,
    the footer and the hero CTA are not written into any page's source — they are
    entries in `src/data/mock.ts`, which no route names and the sweep therefore
    never opened. That is where 11 of request 71's 13 dead hrefs lived.
    """
    files: list[str] = []
    for route in _routes(architect):
        if public_only and _surface(route) != "public":
            continue
        rel = str(route.get("component_file") or "").replace("\\", "/")
        if rel and rel not in files:
            files.append(rel)
    for rel in _SHARED_LINK_SOURCES:
        if rel not in files and _read(workspace, rel):
            files.append(rel)
    return files


def _collect_dead_links(
    workspace: Path,
    architect: Mapping[str, Any],
    declared: set[str],
) -> dict[str, tuple[DeadLink, ...]]:
    """Every dead internal href in the app, grouped by the file that carries it.

    Blocking follows *surface*, not hop membership. Ops pages stay advisory: a
    dead link on an owner-only page is a real defect, but withholding a correct
    public storefront over it is the failure mode logged as P0-4.

    A public page is different. Request 40's home page pointed both of its primary
    CTAs — "View the Collection" and "View Available Paintings" — at `/collection`,
    a path no route serves, so the first thing a visitor clicked bounced them back
    to the page they were on. That was reported as a warning purely because
    HomePage is not the designated browse hop, and the preview shipped `ready`.
    """
    surfaces: dict[str, str] = {}
    route_paths: dict[str, str] = {}
    for route in _routes(architect):
        rel = str(route.get("component_file") or "").replace("\\", "/")
        if not rel:
            continue
        # A file reachable from a public route is public, whichever route the
        # sweep happens to reach it through first.
        if _surface(route) == "public" or rel not in surfaces:
            surfaces.setdefault(rel, _surface(route))
            if _surface(route) == "public":
                surfaces[rel] = "public"
        route_paths.setdefault(rel, _norm(str(route.get("path") or "")))

    out: dict[str, tuple[DeadLink, ...]] = {}
    for rel in _link_bearing_files(workspace, architect):
        src = _read(workspace, rel)
        if not src:
            continue
        counts: dict[str, int] = {}
        for href in internal_hrefs(src):
            if _route_matches(href, declared):
                continue
            counts[_norm(href)] = counts.get(_norm(href), 0) + 1
        for shape in internal_href_templates(src):
            if _route_matches(shape, declared):
                continue
            counts[shape] = counts.get(shape, 0) + 1
        if not counts:
            continue
        # A shared data module has no surface of its own; its nav renders on
        # every public page, so an ops-prefixed entry is advisory and everything
        # else blocks.
        surface = surfaces.get(rel, "public")
        found: list[DeadLink] = []
        for href, count in sorted(counts.items()):
            advisory = _norm(href) in _CONDITIONAL_ROUTES
            link_surface = surface
            if rel in _SHARED_LINK_SOURCES:
                link_surface = (
                    "ops"
                    if href.startswith(tuple(f"{p}/" for p in _OPS_SURFACE_PREFIXES))
                    or href in _OPS_SURFACE_PREFIXES
                    else "public"
                )
            found.append(
                DeadLink(
                    file=rel,
                    href=href,
                    occurrences=count,
                    surface=link_surface,
                    route_path=route_paths.get(rel, ""),
                    advisory=advisory,
                )
            )
        out[rel] = tuple(found)
    return out


def _emit_dead_links(
    report: JourneyReport,
    hop: JourneyHop,
    code: str,
    links: Iterable[DeadLink],
    path: str,
    rel: str,
) -> None:
    for link in links:
        where = f" ({link.occurrences} occurrences)" if link.occurrences > 1 else ""
        report.add(
            code,
            f"{hop.label}: {rel} links to {link.href}{where}, "
            "which no route in App.tsx serves",
            hop,
            surface=link.surface,
            component_file=rel,
            path=path or link.route_path,
            advisory=link.advisory,
            href=link.href,
            occurrences=link.occurrences,
        )


def _sweep_non_hop_links(
    report: JourneyReport,
    dead_by_file: Mapping[str, tuple[DeadLink, ...]],
    reported_files: set[str],
) -> None:
    """Report the dead links on every file the hop walk did not already cover."""
    swept = JourneyHop("other-pages", "sweep", "", "Other pages")
    for rel, links in sorted(dead_by_file.items()):
        if rel in reported_files:
            continue
        reported_files.add(rel)
        _emit_dead_links(
            report,
            swept,
            "journey_dead_link_offpath",
            links,
            links[0].route_path if links else "",
            rel,
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
    if not any(_renders(src, name) for name in LISTING_COMPONENTS):
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
    if (
        not _renders(src, "CatalogGrid")
        and not _renders(src, "ScheduleRail")
        and _renders(src, "ProductShowcase")
    ):
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
        # …plus the ones only the router has. `assemble.py` mints `listing/:id`
        # for a detail page the architect declared at a sibling slug — request
        # 148's `/bikes/v2` becomes `/bikes/:id` in `App.tsx` and nowhere else.
        # Reading the architect alone reports "items cannot be opened" on an app
        # whose router opens them, which is the same architect-versus-served split
        # `served_route_paths` exists to close and which every other check here
        # already answers against. Latent until this pass: the hop it fires on
        # could not resolve before, so nothing reached this line.
        param_routes += [
            p
            for p in sorted(declared)
            if _is_param_path(p)
            and p not in param_routes
            and not p.startswith(_OPS_PATH_PREFIXES)
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
        #
        # Resolved through `_find_route` rather than compared as a literal. This
        # line is the one that produced 150's `journey_next_hop_missing`: it held
        # the hint `/book` against a route table whose booking page is
        # `/hire/reserve`, so the check reported the funnel broken and the rows
        # were then measured against a path nothing on the page could point at.
        # The hint stays as the fallback for contracts that resolve to nothing.
        found = _find_route(
            architect, next_hop, want_param=_is_param_path(next_hop.path_hint)
        )
        target = _norm(str(found.get("path") or "")) if found else _norm(next_hop.path_hint)
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


def journey_gate_issues(report: JourneyReport) -> list[tuple[str, str, str]]:
    """(code, message, path) for public breaks only.

    Ops surfaces warn: mirrors ``asset_integrity.blocking_missing_assets()``,
    where only ``ref.public_surface`` blocks. Blocking on an owner-only page
    would withhold a correct public storefront — the P0-4 failure mode.
    """
    return [
        (f.code, f.message, f.component_file or f.path) for f in report.blocking
    ]
