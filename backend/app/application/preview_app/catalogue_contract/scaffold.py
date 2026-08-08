"""Minimal catalogue page scaffolds."""
from __future__ import annotations

import json
import re

from app.application.preview_app.catalogue_contract.item_source import (
    catalogue_detail_base,
)
from app.application.preview_app.catalogue_contract.slots import (
    assigned_non_shell_slots,
    expected_shell,
)
from app.application.preview_app.protected_paths import canonical_workspace_path


def _js(value) -> str:
    """JSON literal for emitted TSX — non-ASCII must stay literal.

    Several sites below interpolate this straight into a JSX attribute
    (`description={_js(text)}` renders as `description="…"`). JSX attribute
    string literals do not process JavaScript escape sequences, so an
    ``ensure_ascii=True`` dump would ship `\\u2014` as six visible characters.
    """
    return json.dumps(value, ensure_ascii=False)


# Nav chrome is sticky/fixed at the top of PublicShell — a bare PageHeader band
# collides with it. Public listing scaffolds must supply their own inset.
_PAGE_HEADER_BAND = (
    "mx-auto w-full max-w-[92rem] px-6 pt-28 pb-10 lg:px-12 lg:pt-32 lg:pb-14"
)

# Gallery/shop browse leaves: a route or page whose last path segment (or
# id/title token, at the plan layer) is one of these IS the catalogue face,
# whatever the architect labeled it. Shared with the plan-stage blueprint seed
# (`product_kind._plan_served_kinds`) so "this app already serves a catalogue"
# means the same thing at both layers — the set must stay byte-identical to the
# one `minimal_catalogue_page_scaffold` enforced before the hoist (request 64's
# /gallery shipped ProductShowcase and failed journey_browse_caps).
CATALOG_BROWSE_LEAVES = frozenset(
    {
        "gallery",
        "collection",
        "collections",
        "shop",
        "catalog",
        "catalogue",
        "works",
        "paintings",
        "products",
        "menu",
    }
)

_SLOT_COMPONENT = {
    "hero": "MarketingHero",
    "features": "FeatureBento",
    "showcase": "ProductShowcase",
    "inquire": "InquiryPanel",
    "process": "ProcessSection",
    "testimonials": "TestimonialRail",
    "cta": "CTABand",
    "footer": "BrandFooter",
    "trust": "LogoMarquee",
    "credentials": "CredentialStrip",
    "spotlight": "SpotlightCard",
    "results": "ResultRail",
    "booking": "BookingPanel",
    "workspace": "Card",
    "summary": "Card",
    "header": "PageHeader",
    "kpis": "StatCard",
    "chart": "ChartCard",
    "filters": "FilterBar",
    "table": "DataTable",
    "activity": "ActivityFeed",
    "risk": "RiskQueue",
    "empty": "EmptyState",
    "pulse": "CashPulseBar",
    "board": "InvoiceBoard",
    "recon": "ReconSplit",
    "blotter": "BlotterTape",
    "ticker": "DeskTicker",
    "expenses": "ExpenseQueue",
}

# Per-skeleton slot component overrides. The browse page's showcase slot must be
# a CatalogGrid: ProductShowcase is an editorial mosaic that destructures
# [featured, secondary, tertiary] and therefore renders at most three items, so a
# twelve-piece collection silently showed three and the rest were unreachable.
_SKELETON_SLOT_COMPONENT: dict[str, dict[str, str]] = {
    "public-catalog": {"showcase": "CatalogGrid"},
}


def slot_component_for(slot: str, skeleton_id: str = "") -> str | None:
    """Component that fills ``slot``, honouring per-skeleton overrides."""
    override = _SKELETON_SLOT_COMPONENT.get(skeleton_id or "", {})
    if slot in override:
        return override[slot]
    return _SLOT_COMPONENT.get(slot)


# A listing face may render its items with either component. CatalogGrid is
# correct (renders all items, links each); ProductShowcase is accepted so pages
# generated before the grid existed still validate instead of healing forever.
LISTING_FACE_COMPONENTS = ("CatalogGrid", "ProductShowcase")


def has_listing_face_component(content: str) -> bool:
    """True when a listing page *renders* its items through a catalogue component.

    The tag, not the word. This scaffold's own source carries the comment
    "ProductShowcase used to fill this slot", which a substring test read as a
    listing component — so the check passed on a page that had lost its grid.
    """
    text = content or ""
    return any(f"<{name}" in text for name in LISTING_FACE_COMPONENTS)


_DEFAULT_CATALOG_BASE = "/gallery"
#: The CTA a page emits when the route it would have linked to is not declared.
#: A missing button beats a dead one: `#inquire` is an in-page anchor, so the
#: worst case is a no-op scroll rather than a click that falls through to the
#: catch-all route and lands the visitor back on the home page.
_NO_ROUTE_CTA = '{ label: "Send a message", href: "#inquire" }'


def catalog_base_from_path(route_path: str = "", architect: dict | None = None) -> str:
    """Browse route that a detail route hangs off.

    ``/gallery/:id`` → ``/gallery``, ``/works/:slug`` → ``/works``. Derived rather
    than hardcoded so a renamed catalogue route keeps its cards and its
    back-to-collection link pointing somewhere real.

    "Somewhere real" is the part that needs the route table. A planner that puts
    the detail page at ``/artwork/:id`` while the listing lives at ``/gallery``
    leaves ``/artwork`` undeclared, so request 44's detail page offered "Back to the
    collection" to a path that fell through to the catch-all — three blocking
    findings on an app whose links all otherwise worked. When the derived base is
    not a declared route, the declared listing wins.

    "The declared listing" is resolved by skeleton before it is resolved by name.
    The name list below only knows the words a catalogue usually goes by, and
    request 148's browse face is `/bikes` while 150's is `/catalogue` — neither is
    in it. Both fell through to the `/gallery` default, so every card the home
    page rendered linked into a route those apps do not have.
    """
    raw = str(route_path or "").strip()
    base = raw.split("/:")[0].split("/{")[0].rstrip("/")
    declared = {
        str(r.get("path") or "").rstrip("/")
        for r in ((architect or {}).get("routes") or [])
        if isinstance(r, dict)
    }
    if base and (not declared or base in declared):
        return base
    if browse := catalog_route(architect):
        return browse
    listing = sorted(
        p for p in declared
        if p and ":" not in p and _LISTING_BASE_RE.match(p + "/")
    )
    if listing:
        return listing[0]
    # No path of its own to derive from — a home page's card grid — so fall back
    # to wherever this app's detail routes actually live.
    return base or catalogue_detail_base(architect) or _DEFAULT_CATALOG_BASE


#: Browse-route names a catalogue listing goes by.
_LISTING_BASE_RE = re.compile(
    r"^/(gallery|collection|collections|shop|catalog|catalogue|products|works|menu|"
    r"paintings|pieces|artworks|listings)(/|$)",
    re.I,
)


def _surface_route_path(route: object) -> str:
    """Declared path of a visitor-facing, non-param route — `""` when it is neither.

    Ops routes are excluded because a public CTA must never hand the visitor an
    owner console, and param routes because `/bikes/:id` is a shape, not a place
    a button can point at.
    """
    if not isinstance(route, dict):
        return ""
    path = str(route.get("path") or "").strip()
    if not path.startswith("/"):
        return ""
    if str(route.get("surface") or "").lower() == "ops" or _is_ops_path(path):
        return ""
    if re.search(r"/:\w+", path) or re.search(r"/\{[^}]+\}", path):
        return ""
    return path.rstrip("/") or "/"


def booking_route(architect: dict | None) -> str | None:
    """Where "book a visit" goes — the route the architect declared for it.

    Resolved by **skeleton, never by name**. The scaffold used to write the
    literal `/book` into every booking CTA it emitted, which is right only for
    the apps whose architect happened to choose that word: request 148 named its
    booking page `/service/book` and 150 named it `/hire/reserve`, so every
    "Book a visit" button on those two apps pointed at a path the route table
    does not contain and the catch-all sent the click home.

    The naming freedom is wanted — the architect describes *this* business, and
    a bike workshop's booking page is not a clinic's. What was missing is that
    the emitters never read the table back. Exactly one route per app carries
    `skeleton_id == "public-booking"` (verified across requests 146–151), so the
    table already answers this question; this is the reading of it.

    Returns ``None`` when the app declares no booking page at all — request 151
    is an ops console with no public face, and inventing `/book` for it would
    manufacture the very dead link this function exists to remove.
    """
    for route in (architect or {}).get("routes") or []:
        if not isinstance(route, dict):
            continue
        if str(route.get("skeleton_id") or "") != "public-booking":
            continue
        if path := _surface_route_path(route):
            return path
    return None


def _contact_route(architect: dict | None) -> str | None:
    """The app's contact face, resolved the way the utility compositor names it.

    Imported late: `utility_compositor` imports this module back, and the two
    have to agree on what a contact page is or a CTA points at a route the
    compositor gave a different layout.
    """
    from app.application.preview_app.utility_compositor import utility_route

    return utility_route(architect, "contact")


def declares_path(architect: dict | None, path: str) -> bool:
    """Whether the app declares this exact route.

    The narrowest of the resolvers, and the right one for an ops console's own
    chrome: `/invoices` and `/ticket` are the accounting and trading blueprints'
    own page ids, not a concept another name could stand in for. Either the route
    is there or the button has nowhere to go.
    """
    wanted = str(path or "").rstrip("/") or "/"
    return any(
        isinstance(route, dict)
        and (str(route.get("path") or "").rstrip("/") or "/") == wanted
        for route in (architect or {}).get("routes") or []
    )


def _ops_header_actions(architect: dict | None, label: str, href: str) -> str:
    """The ops PageHeader's action row, minus any button with nowhere to go.

    The AI hub is a pipeline constant and always present. The second action is a
    route the ops blueprint may or may not have seeded — an app whose console
    never got `/invoices` shipped a "New invoice" button that fell through
    `path="*"` to the home page, which on an ops console is not even a page the
    visitor was on. An anchor (`#queue`) is in-page and always fine.
    """
    hub = '{ label: "AI features", href: "/ai-features", variant: "secondary" }'
    if href.startswith("#") or declares_path(architect, href):
        return f' actions={{[{hub}, {{ label: {_js(label)}, href: {_js(href)} }}]}}'
    return f" actions={{[{hub}]}}"


def catalog_route(architect: dict | None) -> str | None:
    """Where "view collection" goes — the declared browse face, by skeleton first.

    Same defect, same shape as `booking_route`: the literal `/gallery` is right
    for a painter and wrong for request 148's `/bikes` and 150's `/catalogue`.
    The declared `public-catalog` route wins; a browse-named route is the
    fallback for thin contracts that never assigned skeletons.
    """
    routes = list((architect or {}).get("routes") or [])
    for route in routes:
        if isinstance(route, dict) and str(route.get("skeleton_id") or "") == "public-catalog":
            if path := _surface_route_path(route):
                return path
    for route in routes:
        path = _surface_route_path(route)
        if path and path != "/" and _LISTING_BASE_RE.match(path + "/"):
            return path
    return None


# Slots that give a page somewhere for its journey to end.
_TERMINAL_ACTION_SLOTS = ("inquire", "booking")


def _ensure_terminal_action_slot(skeleton_id: str, slots: list[str]) -> list[str]:
    """A detail page must end in an inquiry or a booking.

    The detail hero CTA points at ``#inquire`` (the anchor InquiryPanel renders),
    so a detail page whose assigned slots carry neither terminal action would ship
    a CTA anchored to nothing. Guarantee the slot rather than trusting the recipe
    to have supplied it.
    """
    if skeleton_id != "public-detail":
        return slots
    if any(slot in slots for slot in _TERMINAL_ACTION_SLOTS):
        return slots
    ordered = list(slots)
    for anchor in ("cta", "footer"):
        if anchor in ordered:
            ordered.insert(ordered.index(anchor), "inquire")
            return ordered
    ordered.append("inquire")
    return ordered


# Marketing mid-slots that bury the painting specs when they sit before inquire.
_DETAIL_DEMOTE_AFTER_INQUIRE = frozenset(
    {
        "features",
        "showcase",
        "testimonials",
        "process",
        "results",
        "spotlight",
        "trust",
        "products",
        "activity",
        "risk",
        "empty",
        "filters",
        "table",
        "chart",
        "kpis",
        "header",
        "booking",
    }
)


def _paint_first_detail_slots(slots: list[str]) -> list[str]:
    """Painting → specs → inquire first; demote marketing stacks after inquire.

    Request 48 opened a detail page under a brand-billboard hero plus "Why …"
    feature cards before the painting specs the visitor clicked for.
    """
    ordered = list(slots)
    if "credentials" not in ordered:
        anchor = next((s for s in ("inquire", "cta", "footer") if s in ordered), None)
        ordered = (
            ordered[: ordered.index(anchor)] + ["credentials"] + ordered[ordered.index(anchor) :]
            if anchor
            else ordered + ["credentials"]
        )
    front = [s for s in ("hero", "credentials", "inquire") if s in ordered]
    back = [s for s in ("cta", "footer") if s in ordered]
    mid = [
        s
        for s in ordered
        if s not in front and s not in back and s not in _DETAIL_DEMOTE_AFTER_INQUIRE
    ]
    demoted = [s for s in ordered if s in _DETAIL_DEMOTE_AFTER_INQUIRE]
    # Preserve relative order within each band; front/back stay fixed.
    result: list[str] = []
    for band in (front, mid, demoted, back):
        for slot in band:
            if slot not in result:
                result.append(slot)
    return result


_COMPOSE_LAYOUT_SKELETONS = frozenset(
    {"ops-dashboard", "ops-ledger-home", "ops-blotter-desk"}
)
_FLOOR_APPEARANCE_SKELETONS = frozenset({"ops-blotter-desk"})

_SEED_SLOTS = frozenset(
    {
        "hero",
        "features",
        "showcase",
        "products",
        "process",
        "testimonials",
        "cta",
        "footer",
        "trust",
        "credentials",
        "booking",
        "header",
        "kpis",
        "chart",
        "filters",
        "table",
        "activity",
        "risk",
        "pulse",
        "board",
        "recon",
        "blotter",
        "ticker",
        "expenses",
    }
)

_TRADING_HINTS = (
    "trade",
    "trading",
    "trader",
    "hedge",
    "blotter",
    "portfolio",
    "equity",
    "oms",
    "execution",
    "broker",
    "pnl",
    "p&l",
    "fund",
    "desk",
)

_ACCOUNTING_HINTS = (
    "account",
    "ledger",
    "invoice",
    "bookkeep",
    "expense",
    "reconcil",
    "quickbooks",
    "xero",
    "freshbooks",
    "cash flow",
    "cashflow",
)


_GALLERY_HINTS = (
    "gallery",
    "artwork",
    "painting",
    "painter",
    "atelier",
    "artist",
    "sculpture",
    "ceramic",
    "pottery",
    "portfolio",
    " fine art",
    "oil painting",
    # trailing brand words ("… Art") — keep the leading space so "part"/"start"
    # and "chart" do not false-positive.
    " art",
)


def _is_trading_domain(*parts: str) -> bool:
    blob = " ".join(str(p or "") for p in parts).lower()
    if any(hint in blob for hint in _ACCOUNTING_HINTS):
        return False
    return any(hint in blob for hint in _TRADING_HINTS)


def _is_gallery_domain(*parts: str) -> bool:
    """Gallery / portfolio brands must never get booking or scheduling copy."""

    blob = " ".join(str(p or "") for p in parts).lower()
    if any(hint in blob for hint in _ACCOUNTING_HINTS + _TRADING_HINTS):
        return False
    return any(hint in blob for hint in _GALLERY_HINTS)


def _is_accounting_domain(*parts: str) -> bool:
    blob = " ".join(str(p or "") for p in parts).lower()
    return sum(1 for hint in _ACCOUNTING_HINTS if hint in blob) >= 1


def _non_home_hero_ctas(
    skeleton_id: str,
    brand: str,
    title: str,
    architect: dict | None = None,
) -> tuple[str, str]:
    """Return (primaryCta jsx attrs fragment without wrappers, subcopy).

    Storefront catalog/detail must not invent /book-appointment.
    Booking faces link the *declared* booking route — `booking_route` reads it
    out of the route table, because the literal `/book` this used to emit was a
    dead link on every app whose architect named that page something else.
    """
    sk = (skeleton_id or "").lower()
    blob = f"{brand} {title} {sk}".lower()
    book_href = booking_route(architect)
    book_cta = (
        f'{{ label: "Book a visit", href: {_js(book_href)} }}'
        if book_href
        else _NO_ROUTE_CTA
    )
    # The skeleton is stronger evidence than the brand name. A booking or service
    # face must never take the storefront branch: a gallery-flavoured brand on a
    # public-booking page emitted a "View collection" CTA to /gallery, which a
    # booking app's route table (/, /services, /book) does not contain.
    if sk in {"public-booking", "public-service"}:
        # Contact routes must never inherit booking CTAs (request 61).
        if any(
            token in blob
            for token in ("contact", "enquire", "inquire", "get in touch")
        ):
            sub = _js(f"{title} — send a note. We reply directly.")
            return (
                'primaryCta={{ label: "Send a message", href: "#inquire" }} '
                'secondaryCta={{ label: "Back home", href: "/" }}',
                sub,
            )
        sub = _js(
            f"{title} — pick a time that works. This page is not the homepage story."
        )
        return (
            f"primaryCta={{{book_cta}}} "
            'secondaryCta={{ label: "Back home", href: "/" }}',
            sub,
        )
    storefrontish = sk in {"public-catalog", "public-detail"} or any(
        token in blob
        for token in (
            "gallery",
            "artwork",
            "collection",
            "painting",
            "painter",
            "atelier",
            "artist",
            " fine art",
            "oil painting",
            "shop",
            "storefront",
            "menu",
            "catalog",
            # trailing brand words ("… Art") — keep leading space to avoid "part"/"start"
            " art",
        )
    )
    if storefrontish:
        sub = _js(
            f"{title} — browse what’s here. This page is not the homepage story."
        )
        if sk == "public-detail" or "detail" in sk:
            # "/about" is not in the storefront route table, so this was a dead
            # end on the one CTA the whole journey exists to reach. InquiryPanel
            # renders id="inquire" in this page's own inquire slot.
            primary = '{ label: "Inquire about this piece", href: "#inquire" }'
        else:
            # The declared browse face, not the word "gallery". 148's is `/bikes`
            # and 150's is `/catalogue`; both got a dead "View collection".
            browse_href = catalog_route(architect)
            primary = (
                f'{{ label: "View collection", href: {_js(browse_href)} }}'
                if browse_href
                else _NO_ROUTE_CTA
            )
        secondary = '{ label: "Back home", href: "/" }'
        return (
            f"primaryCta={{{primary}}} secondaryCta={{{secondary}}}",
            sub,
        )

    sub = _js(
        f"{title} — browse what’s here, then book. This page is not the homepage story."
    )
    primary = book_cta
    secondary = '{ label: "Back home", href: "/" }'
    return (
        f"primaryCta={{{primary}}} secondaryCta={{{secondary}}}",
        sub,
    )


_FEATURE_ITEMS_ACCOUNTING = (
    ("Invoicing", "Send, track, and chase invoices without a spreadsheet."),
    ("Expenses", "Categorized as they land, so month end is already done."),
    ("Reconciliation", "Bank lines matched against the ledger every morning."),
)

_FEATURE_ITEMS_TRADING = (
    ("Order staging", "Stage, check, and release tickets from one blotter."),
    ("Risk limits", "Gross, sector, and single-name limits checked before release."),
    ("P&L attribution", "Intraday marks and attribution on the same screen."),
)

_FEATURE_ITEMS_GALLERY = (
    ("Original works", "Signed pieces, each one photographed as it hangs."),
    ("Commissions", "A piece scaled to your room, your light, your palette."),
    ("Collector support", "Framing, shipping, and placement handled end to end."),
)


def _feature_items_fallback(
    brand: str,
    *,
    accounting: bool,
    trading: bool,
    gallery: bool,
) -> list[dict[str, str]]:
    """Brand-bound feature cards for when `seed.features` is missing or empty.

    FeatureBento's alternating variant prints a `NN / NN` chapter counter, so an
    empty item list renders the contradiction "01 / 00".
    """
    if accounting:
        pairs = _FEATURE_ITEMS_ACCOUNTING
    elif trading:
        pairs = _FEATURE_ITEMS_TRADING
    elif gallery:
        pairs = _FEATURE_ITEMS_GALLERY
    else:
        pairs = (
            (f"Work with {brand}", "Clear scope, clear pricing, and a real timeline."),
            ("Straight answers", "One point of contact from first call to handover."),
            ("Finished properly", "Work you can check over before you pay for it."),
        )
    return [{"title": title, "description": description} for title, description in pairs]


def _detail_param_block(brand: str, detail_base: str) -> str:
    """Resolve the route param to one seed item, with a real not-found path.

    Without this a detail page renders identical content for every id — the page
    exists, is reachable, and is inquirable, but `/gallery/3` is not artwork 3.
    """
    return (
        "  const params = useParams();\n"
        "  const catalogItems = (seed.items ?? []) as any[];\n"
        # Read whatever param the route declared, rather than the two names the
        # router was made to mint *because* this line named them. An architect
        # that declares `/gallery/:paintingId` — requests 47 and 69 both do —
        # gave this page `params.id === undefined` and `params.slug ===
        # undefined`, so it resolved no item at all and rendered the generic
        # "This piece" against a default image on every id. Reading the first
        # declared param makes `:id`, `:slug`, `:paintingId` and `:artworkId`
        # all work, which is what lets `assemble.py` stop minting a second
        # alias whose only difference is the param's name.
        "  const itemKey = String(Object.values(params)[0] ?? '').trim();\n"
        # A listing that numbered its cards 1..n linked every one of them to a
        # page that resolved nothing, because seed ids are slugs. Match on any of
        # the four things a link in this app can carry — id, slug, slugified
        # title, or 1-based position — so browse -> detail cannot dead-end on a
        # naming disagreement between two files.
        "  const itemToken = (value: any) =>\n"
        "    String(value ?? '')\n"
        "      .trim()\n"
        "      .toLowerCase()\n"
        "      .replace(/[^a-z0-9]+/g, '-')\n"
        "      .replace(/^-+|-+$/g, '');\n"
        "  const wantedToken = itemToken(itemKey);\n"
        "  const itemIndex = catalogItems.findIndex(\n"
        "    (entry: any, index: number) =>\n"
        "      wantedToken !== '' &&\n"
        "      (itemToken(entry?.id) === wantedToken ||\n"
        "        itemToken(entry?.slug) === wantedToken ||\n"
        "        itemToken(entry?.title) === wantedToken ||\n"
        "        String(index + 1) === itemKey),\n"
        "  );\n"
        "  const item: any = itemIndex >= 0 ? catalogItems[itemIndex] : undefined;\n"
        "  const notFound = itemKey !== '' && itemIndex < 0;\n"
        "  const itemTitle = String(item?.title ?? 'This piece');\n"
        "  const itemImage = String(\n"
        "    item?.image ??\n"
        "      [images.item1, images.item2, images.item3, images.item4,\n"
        "       images.item5, images.item6, images.item7, images.item8][\n"
        "        (itemIndex >= 0 ? itemIndex : 0) % 8\n"
        "      ],\n"
        "  );\n"
        "  const itemSpecs = [\n"
        "    { title: 'Reference', detail: itemKey || String(itemIndex + 1) },\n"
        "    item?.medium ? { title: 'Medium', detail: String(item.medium) } : null,\n"
        "    item?.dimensions ? { title: 'Dimensions', detail: String(item.dimensions) } : null,\n"
        "    item?.price ? { title: 'Price', detail: String(item.price) } : null,\n"
        "    item?.status ? { title: 'Availability', detail: String(item.status) } : null,\n"
        "    item?.category ? { title: 'Collection', detail: String(item.category) } : null,\n"
        "  ].filter(Boolean) as { title: string; detail: string }[];\n"
    )


def _detail_not_found_block(
    shell: str, brand_js: str, detail_base: str, appspec_attrs: str
) -> str:
    """Early return for an id that matches nothing — never a blank page."""
    base_js = _js(detail_base)
    return (
        "  if (notFound) {\n"
        "    return (\n"
        f"      <{shell} brandName={{{brand_js}}} "
        "nav={<PublicNav items={navItems} cta={navCta} />}>\n"
        f'        <div data-skeleton={{skeleton.id}} data-detail-not-found=""{appspec_attrs}>\n'
        '          <div className="mx-auto w-full max-w-3xl px-6 pt-32 pb-24 lg:pt-40">\n'
        '            <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-brand">\n'
        "              Not found\n"
        "            </p>\n"
        '            <h1 className="mt-4 font-display text-[clamp(2rem,4vw,3rem)] leading-tight tracking-tight text-foreground">\n'
        "              We could not find that one\n"
        "            </h1>\n"
        '            <p className="mt-4 text-base leading-7 text-muted">\n'
        "              It may have sold or moved. Browse what is available now.\n"
        "            </p>\n"
        f'            <Button href={{{base_js}}} className="mt-8">Back to the collection</Button>\n'
        "          </div>\n"
        "        </div>\n"
        f"      </{shell}>\n"
        "    );\n"
        "  }\n"
    )


def _safe_slot_jsx(
    slot: str,
    brand: str,
    title: str,
    *,
    skeleton_id: str = "",
    item_bound: bool = False,
    detail_base: str = _DEFAULT_CATALOG_BASE,
    architect: dict | None = None,
) -> str:
    brand_js = _js(brand)
    title_js = _js(title)
    accounting = _is_accounting_domain(brand, title)
    trading = _is_trading_domain(brand, title) and not accounting
    gallery = _is_gallery_domain(brand, title)
    # Non-home pages must NOT reuse seed.hero — that makes /doctors look like /.
    home_hero = skeleton_id in {"", "public-home"}
    # Public storefront skeletons. Slots shared with the ops surface (`filters`)
    # need to know which vocabulary they are speaking.
    public_slot_face = (skeleton_id or "").lower().startswith("public-") or not skeleton_id

    def _d(accounting_v: str, trading_v: str, default_v: str) -> str:
        if accounting:
            return accounting_v
        if trading:
            return trading_v
        return default_v

    # Brand-bound fallbacks for public-home (and shared mid-slots) — never agency mush.
    def _fb(text: str) -> str:
        return _js(text)

    features_heading_fb = _fb(f"What {brand} offers")
    showcase_heading_fb = _fb(f"From {brand}")
    products_heading_fb = _fb(f"{brand} picks")
    process_heading_fb = _fb(f"How {brand} works")
    testimonials_heading_fb = _fb(f"Guests of {brand}")
    # `CredentialStrip` is two different things depending on the page. On an item
    # detail page it lists the piece's specs, so "Details" is right. Everywhere
    # else it is the brand's trust block, and "Details" over "Family-owned since
    # 1994 / Free consultation" is worse than the heading it replaced. This is
    # called from `repair.py` too, for every page type.
    detail_face = item_bound or (skeleton_id or "").lower() == "public-detail"
    credentials_heading_fb = _fb("Details" if detail_face else f"Why {brand}")
    cta_heading_fb = _fb(f"Ready for {brand}?")
    cta_desc_fb = _fb(f"Tell {brand} what you need — clear options, real next steps.")
    # Slice 1 (handoff "next slices"): no residual booking copy on gallery brands.
    # Every other fallback here is already brand-bound and domain-neutral; this
    # one asserted "real bookings" on an art brand, which reads as a clinic clone.
    # Stays brand-bound — the point of these fallbacks is never agency mush.
    footer_desc_fb = _fb(
        f"{brand} — original works, shown plainly."
        if _is_gallery_domain(brand, title)
        else f"{brand} — clear choices and real bookings."
    )
    spotlight_title_fb = _fb(f"{brand} in focus")
    spotlight_desc_fb = _fb(f"A closer look at what makes {brand} distinct.")
    results_heading_fb = _fb(f"{brand} results")
    results_label_fb = _fb(f"{brand} highlight")
    features_items_fb = _js(
        _feature_items_fallback(
            brand, accounting=accounting, trading=trading, gallery=gallery
        )
    )
    # ProductShowcase prints this over its lead card; without it the template
    # falls back to its own placeholder eyebrow ("Lead drop").
    showcase_badge_fb = _fb("Featured work" if gallery else "Featured")

    # CatalogGrid derives every card's link from detailBase + item id, so the
    # browse → detail hop cannot be dropped by codegen.
    #
    # The `products` and `showcase` slots read it too. They used to write the
    # literal `/gallery/${…}` while this — already derived, already in scope, and
    # used correctly by the adjacent `catalog` slot six lines down — sat unused,
    # so on request 148 every card on a `/bikes` page linked into a `/gallery`
    # the route table does not contain.
    catalog_detail_base = detail_base or _DEFAULT_CATALOG_BASE
    # Where "Get started" goes when the seed does not say. `/contact#inquire` was
    # the literal, and `/contact` is a route plenty of apps do not declare — the
    # fragment made it look like an anchor and it is a route link with an anchor
    # on the end. Resolve the contact face; with none, fall back to the bare
    # anchor, which at worst scrolls nowhere.
    cta_ask_href = f"{_contact_route(architect)}#inquire" if _contact_route(architect) else "#inquire"
    catalog_item_noun = "pieces" if gallery else "items"
    # "Contact for Purchase" is about *a piece*, so it belongs on the detail
    # page. A gallery's standalone /contact page also fields commissions, studio
    # visits and provenance questions, and narrowing its heading to a purchase
    # turns those visitors away at the door.
    inquire_heading_fb = _fb(
        "Contact for Purchase" if gallery and detail_face else f"Ask {brand} a question"
    )
    inquire_desc_fb = _fb(
        "Ask about availability, dimensions, or a studio visit — we reply directly."
        if gallery
        else f"Tell {brand} what you need and we will come back to you directly."
    )

    if home_hero:
        hero_jsx = (
            f'<MarketingHero brandName={{{brand_js}}} '
            f'eyebrow={{seed.hero?.eyebrow ?? {brand_js}}} '
            f'headline={{seed.hero?.headline || {title_js}}} '
            'subcopy={seed.hero?.subcopy} '
            'primaryCta={seed.hero?.primaryCta} '
            'secondaryCta={seed.hero?.secondaryCta} '
            'imageSrc={images.hero} imageAlt="" />'
        )
    else:
        cta_attrs, sub_js = _non_home_hero_ctas(skeleton_id, brand, title, architect)
        hero_jsx = (
            f'<MarketingHero brandName={{{brand_js}}} '
            f'headline={{{title_js}}} '
            f'subcopy={{{sub_js}}} '
            'variant="compact" '
            f'{cta_attrs} '
            'imageSrc={images.card1} imageAlt="" />'
        )

    samples = {
        "hero": hero_jsx,
        "features": (
            f'<FeatureBento heading={{seed.featuresHeading ?? {features_heading_fb}}} '
            'imagePool={[images.card1, images.card2, images.card3]} '
            f'items={{seed.features?.length ? seed.features : {features_items_fb}}} />'
        ),
        "products": (
            f'<ProductShowcase heading={{seed.showcaseHeading ?? {products_heading_fb}}} '
            'items={(seed.items ?? []).map((item, index) => ({ '
            'title: item.title, description: item.description, '
            # Item pool only — card/hero slots are lifestyle and bury the catalogue.
            'imageSrc: [images.item1, images.item2, images.item3, images.item4, '
            'images.item5, images.item6, images.item7, images.item8][index % 8], imageAlt: item.title, '
            f'badge: String((item as any).badge || (item as any).category || {showcase_badge_fb}), '
            f'href: `{catalog_detail_base}/${{encodeURIComponent(String((item as any).id || (item as any).slug || index + 1))}}` '
            '}))} />'
        ),
        "showcase": (
            f'<ProductShowcase heading={{seed.showcaseHeading ?? {showcase_heading_fb}}} '
            'items={(seed.items ?? []).map((item, index) => ({ '
            'title: item.title, description: item.description, '
            'imageSrc: [images.item1, images.item2, images.item3, images.item4, '
            'images.item5, images.item6, images.item7, images.item8][index % 8], imageAlt: item.title, '
            f'badge: String((item as any).badge || (item as any).category || {showcase_badge_fb}), '
            f'href: `{catalog_detail_base}/${{encodeURIComponent(String((item as any).id || (item as any).slug || index + 1))}}` '
            '}))} />'
        ),
        # Browse face: every item rendered and linked, not a three-card mosaic.
        "catalog": (
            f'<CatalogGrid heading={{seed.showcaseHeading ?? {showcase_heading_fb}}} '
            f'detailBase={_js(catalog_detail_base)} itemNoun={_js(catalog_item_noun)} '
            'items={(seed.items ?? []).map((item, index) => ({ '
            'id: String((item as any).id || (item as any).slug || index + 1), '
            'title: item.title, description: item.description, '
            'meta: String((item as any).price || (item as any).meta || (item as any).medium || \'\'), '
            'category: (item as any).category ? String((item as any).category) : undefined, '
            'status: (item as any).status ? String((item as any).status) : undefined, '
            'imageSrc: [images.item1, images.item2, images.item3, images.item4, '
            'images.item5, images.item6, images.item7, images.item8][index % 8], imageAlt: item.title, '
            'badge: (item as any).badge ? String((item as any).badge) : undefined '
            '}))} />'
        ),
        # No seed.* reference: the seed type is inferred from the generated mock
        # literal, so naming a key it does not define is a type error.
        "inquire": (
            f'<InquiryPanel heading={inquire_heading_fb} '
            f'description={inquire_desc_fb} />'
        ),
        "process": (
            f'<ProcessSection heading={{seed.processHeading ?? {process_heading_fb}}} '
            'steps={seed.process ?? []} />'
        ),
        "testimonials": (
            f'<TestimonialRail heading={{seed.testimonialsHeading ?? {testimonials_heading_fb}}} '
            'items={seed.testimonials ?? []} />'
        ),
        "cta": (
            f'<CTABand heading={{seed.cta?.heading ?? {cta_heading_fb}}} '
            f'description={{seed.cta?.description ?? {cta_desc_fb}}} '
            'primaryCta={{ label: seed.cta?.primaryLabel ?? "Get started", '
            f'href: seed.cta?.primaryHref ?? {_js(cta_ask_href)} }}}} '
            'secondaryCta={{ label: seed.cta?.secondaryLabel ?? "Talk to us", '
            f'href: seed.cta?.secondaryHref ?? {_js(cta_ask_href)} }}}} />'
        ),
        "footer": (
            f'<BrandFooter brandName={{{brand_js}}} '
            f'description={{seed.footer?.description ?? {footer_desc_fb}}} />'
        ),
        "trust": (
            # `trustLabels` is a list of strings in the deterministic seed and a
            # list of `{ label }` objects when the model writes it. Wrapping
            # blindly produced `{ label: { label } }`, which `tsc` reported as
            # TS2322 and the marquee rendered as an empty band.
            '<LogoMarquee size="display" '
            'items={(seed.trustLabels ?? [])'
            '.map((entry: any) => ({ label: String(entry?.label ?? entry ?? \'\') }))'
            '.filter((entry: { label: string }) => entry.label)} />'
        ),
        "credentials": (
            f'<CredentialStrip heading={{seed.credentialsHeading ?? {credentials_heading_fb}}} '
            'items={seed.credentials ?? []} />'
        ),
        "spotlight": (
            f'<SpotlightCard title={{{spotlight_title_fb}}} '
            f'description={{{spotlight_desc_fb}}} />'
        ),
        "results": (
            f'<ResultRail heading={{{results_heading_fb}}} items={{['
            f'{{ label: {results_label_fb}, beforeSrc: images.card2, afterSrc: images.card3 }}'
            ']} />'
        ),
        "booking": (
            '<BookingPanel heading="Choose a time" '
            'treatments={seed.treatments ?? []} '
            'slots={[{ id: "slot-1", startsAt: "2026-07-14T10:00:00" }]} />'
        ),
        "workspace": (
            '<Card title="Your details" description="Everything for this step in one place.">'
            '<div className="space-y-4">'
            '<div className="grid gap-3 sm:grid-cols-2">'
            '<div className="rounded-[calc(var(--radius-ui)+0.15rem)] border border-border-subtle bg-[color-mix(in_srgb,var(--color-brand)_5%,var(--color-background))] p-3">'
            '<p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">Line items</p>'
            '<p className="mt-1 text-sm font-medium text-foreground">Signature package · Qty 1</p>'
            '</div>'
            '<div className="rounded-[calc(var(--radius-ui)+0.15rem)] border border-border-subtle bg-[color-mix(in_srgb,var(--color-brand)_5%,var(--color-background))] p-3">'
            '<p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">Status</p>'
            '<p className="mt-1 text-sm font-medium text-brand">Ready to confirm</p>'
            '</div>'
            '</div>'
            '<p className="text-sm leading-6 text-muted">Totals and confirmation details update as you make changes.</p>'
            '</div>'
            '</Card>'
        ),
        "summary": (
            '<Card title="Summary" description="Review everything before you confirm.">'
            '<div className="space-y-3">'
            '<div className="flex items-center justify-between text-sm"><span className="text-muted">Subtotal</span><span className="font-semibold text-foreground">248</span></div>'
            '<div className="flex items-center justify-between text-sm"><span className="text-muted">Service</span><span className="font-semibold text-foreground">Included</span></div>'
            '<div className="flex items-center justify-between border-t border-border-subtle pt-3 text-base"><span className="font-medium text-foreground">Due today</span><span className="font-display text-xl font-semibold text-brand">248</span></div>'
            '</div>'
            '</Card>'
        ),
        # Ops consoles must not reuse marketing seed.hero (clinic homepage copy on /staff).
        "header": (
            (
                (
                    f'<PageHeader title={{seed.opsHero?.headline || {title_js}}} '
                    "description={seed.opsHero?.subcopy || "
                    + _d(
                        '"Cash, invoices, expenses, and bank matches for today."',
                        '"Watchlist, blotter, positions, and P&L for the fund book."',
                        '"Appointments, check-ins, and the work that needs attention now."',
                    )
                    + "} "
                )
                if (skeleton_id or "").startswith("ops")
                else (
                    f'<PageHeader title={{seed.hero?.headline || {title_js}}} '
                    "description={seed.hero?.subcopy || "
                    + _d(
                        '"Cash, invoices, expenses, and bank matches for today."',
                        '"Watchlist, blotter, positions, and P&L for the fund book."',
                        '"A current view of the work that needs your attention."',
                    )
                    + "} "
                )
            )
            + 'meta={<span className="text-sm text-muted">'
            + _d("Books · live", "Markets open · live marks", "Live")
            + "</span>}"
            + _d(
                _ops_header_actions(architect, "New invoice", "/invoices"),
                _ops_header_actions(architect, "New ticket", "/ticket"),
                _ops_header_actions(architect, "Check in", "#queue"),
            )
            + " />"
        ),
        "pulse": "<CashPulseBar />",
        "board": '<InvoiceBoard heading="Invoice pipeline" />',
        "recon": "<ReconSplit />",
        "blotter": '<BlotterTape heading="Working blotter" />',
        "ticker": "<DeskTicker />",
        "expenses": '<ExpenseQueue heading="Expense queue" />',
        "kpis": (
            '<div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">'
            + _d(
                (
                    '<StatCard label={seed.kpis?.[0]?.label ?? "Cash on hand"} value={seed.kpis?.[0]?.value ?? "48,220"} delta={seed.kpis?.[0]?.delta ?? "+2.1k"} hint={seed.kpis?.[0]?.hint ?? "vs last week"} />'
                    '<StatCard label={seed.kpis?.[1]?.label ?? "Open invoices"} value={seed.kpis?.[1]?.value ?? "26"} delta={seed.kpis?.[1]?.delta ?? "4 overdue"} hint={seed.kpis?.[1]?.hint ?? "AR"} />'
                    '<StatCard label={seed.kpis?.[2]?.label ?? "Expenses MTD"} value={seed.kpis?.[2]?.value ?? "12,840"} delta={seed.kpis?.[2]?.delta ?? "+6%"} hint={seed.kpis?.[2]?.hint ?? "vs last month"} />'
                    '<StatCard label={seed.kpis?.[3]?.label ?? "Unmatched bank"} value={seed.kpis?.[3]?.value ?? "12"} delta={seed.kpis?.[3]?.delta ?? "-3"} hint={seed.kpis?.[3]?.hint ?? "to reconcile"} />'
                ),
                (
                    '<StatCard label={seed.kpis?.[0]?.label ?? "Open orders"} value={seed.kpis?.[0]?.value ?? "18"} delta={seed.kpis?.[0]?.delta ?? "+3"} hint={seed.kpis?.[0]?.hint ?? "working on desk"} />'
                    '<StatCard label={seed.kpis?.[1]?.label ?? "Day P&L"} value={seed.kpis?.[1]?.value ?? "+1.24M"} delta={seed.kpis?.[1]?.delta ?? "+0.4%"} hint={seed.kpis?.[1]?.hint ?? "vs NAV"} />'
                    '<StatCard label={seed.kpis?.[2]?.label ?? "Gross exposure"} value={seed.kpis?.[2]?.value ?? "62%"} delta={seed.kpis?.[2]?.delta ?? "-3%"} hint={seed.kpis?.[2]?.hint ?? "limit 75%"} />'
                    '<StatCard label={seed.kpis?.[3]?.label ?? "Fills today"} value={seed.kpis?.[3]?.value ?? "41"} delta={seed.kpis?.[3]?.delta ?? "+6"} hint={seed.kpis?.[3]?.hint ?? "across 9 names"} />'
                ),
                (
                    '<StatCard label={seed.kpis?.[0]?.label ?? "Active today"} value={seed.kpis?.[0]?.value ?? "24"} delta={seed.kpis?.[0]?.delta ?? "+8%"} hint={seed.kpis?.[0]?.hint ?? "Compared with last week"} />'
                    '<StatCard label={seed.kpis?.[1]?.label ?? "In progress"} value={seed.kpis?.[1]?.value ?? "11"} delta={seed.kpis?.[1]?.delta ?? "+2"} hint={seed.kpis?.[1]?.hint ?? "Open work items"} />'
                    '<StatCard label={seed.kpis?.[2]?.label ?? "Resolved"} value={seed.kpis?.[2]?.value ?? "93%"} delta={seed.kpis?.[2]?.delta ?? "-2%"} hint={seed.kpis?.[2]?.hint ?? "Rolling 7-day rate"} />'
                ),
            )
            + '</div>'
        ),
        "chart": (
            '<ChartCard title={seed.showcaseHeading ?? '
            + _d('"Cash trend"', '"Intraday P&L"', '"Weekly performance"')
            + '} type="area" dataKey="value" xKey="day" '
            + _d(
                'data={[{ day: "Mon", value: 42 }, { day: "Tue", value: 44 }, { day: "Wed", value: 43 }, '
                '{ day: "Thu", value: 46 }, { day: "Fri", value: 48.2 }]} />',
                'data={[{ day: "09:30", value: 0.4 }, { day: "10:30", value: 0.9 }, '
                '{ day: "11:30", value: 0.7 }, { day: "13:00", value: 1.1 }, '
                '{ day: "14:30", value: 1.24 }, { day: "15:45", value: 1.18 }]} />',
                'data={[{ day: "Mon", value: 12 }, { day: "Tue", value: 18 }, { day: "Wed", value: 15 }, '
                '{ day: "Thu", value: 22 }, { day: "Fri", value: 19 }]} />',
            )
        ),
        # A storefront's filter bar is merchandising, not a work queue. `_d` only
        # distinguishes accounting / trading / everything-else, so a public
        # catalogue fell into the default and offered "Search records" filtered
        # by "Open" — the ops vocabulary on a page selling paintings.
        "filters": (
            (
                '<FilterBar searchPlaceholder="'
                + ("Search the collection" if gallery else "Search")
                + '" filters={[{ id: "all", label: "All", active: true }, '
                '{ id: "available", label: "Available", active: false }, '
                '{ id: "recent", label: "Recent", active: false }]} />'
            )
            if not accounting and not trading and public_slot_face
            else '<FilterBar searchPlaceholder="'
            + _d("Search invoices / expenses", "Search symbols / orders", "Search records")
            + '" filters={[{ id: "all", label: "All", active: true }, { id: "'
            + _d("overdue", "working", "open")
            + '", label: "'
            + _d("Overdue", "Working", "Open")
            + '", active: false }'
            + _d(
                ', { id: "sent", label: "Sent", active: false }, '
                '{ id: "draft", label: "Draft", active: false }',
                ', { id: "partial", label: "Partial", active: false }, '
                '{ id: "filled", label: "Filled", active: false }',
                "",
            )
            + "]} />"
        ),
        "table": (
            '<DataTable columns={['
            '{ key: "name", header: "'
            + _d("Record", "Order", "Name")
            + '" }, '
            '{ key: "status", header: "Status" }, '
            '{ key: "owner", header: "'
            + _d("Queue", "Desk", "Owner")
            + '" }'
            ']} rows={(seed.tableRows ?? ['
            + _d(
                (
                    '{ id: "t1", name: "INV-1042 · Northwind Co", status: "Sent", owner: "AR" }, '
                    '{ id: "t2", name: "INV-1041 · Bright Labs", status: "Overdue", owner: "AR" }, '
                    '{ id: "t3", name: "INV-1040 · Harbor Dental", status: "Draft", owner: "Owner" }, '
                    '{ id: "t4", name: "INV-1039 · Peak Studio", status: "Paid", owner: "AR" }, '
                    '{ id: "t5", name: "EXP-332 · Adobe CC", status: "Uncategorized", owner: "Books" }, '
                    '{ id: "t6", name: "EXP-331 · AWS", status: "Categorized", owner: "Books" }, '
                    '{ id: "t7", name: "Bank · Deposit 2,480", status: "Unmatched", owner: "Recon" }, '
                    '{ id: "t8", name: "Bank · Uber 38.20", status: "Matched", owner: "Recon" }'
                ),
                (
                    '{ id: "t1", name: "AAPL · BUY 25,000", status: "Working", owner: "Exec trader" }, '
                    '{ id: "t2", name: "MSFT · SELL 12,000", status: "Partial", owner: "Exec trader" }, '
                    '{ id: "t3", name: "NVDA · BUY 8,000", status: "Staged", owner: "PM" }, '
                    '{ id: "t4", name: "META · BUY 4,500", status: "Filled", owner: "Exec trader" }, '
                    '{ id: "t5", name: "AMZN · SELL 3,200", status: "Working", owner: "PM" }, '
                    '{ id: "t6", name: "JPM · BUY 15,000", status: "Partial", owner: "Exec trader" }, '
                    '{ id: "t7", name: "XOM · SELL 9,000", status: "Working", owner: "Risk" }, '
                    '{ id: "t8", name: "TSLA · BUY 2,100", status: "Rejected", owner: "PM" }'
                ),
                (
                    '{ id: "t1", name: "Primary record", status: "In progress", owner: "Ops" }, '
                    '{ id: "t2", name: "Follow-up item", status: "On hold", owner: "Ops" }, '
                    '{ id: "t3", name: "Completed item", status: "Done", owner: "Ops" }'
                ),
            )
            # `seed.tableRows` is generated, so its rows carry whatever fields the
            # business needed — request 45's were `{ title, artwork, collector, … }`
            # and this projection asserted `name`, `owner`, and an `updated` that
            # exists in no shape at all: nine TS2339s across three ops pages, the
            # same line each time. Read the row loosely and fall back through the
            # names a record actually uses.
            + "]).map((row: any) => ({"
            ' name: String(row?.name ?? row?.title ?? row?.label ?? row?.id ?? ""),'
            ' status: String(row?.status ?? row?.state ?? ""),'
            ' owner: String(row?.owner ?? row?.collector ?? row?.assignee ?? row?.client ?? "—")'
            " }))} />"
        ),
        "activity": (
            '<ActivityFeed heading="Activity" items={(seed.activity ?? ['
            + _d(
                (
                    '{ id: "activity-1", title: "Invoice sent · INV-1042", detail: "Northwind Co · 2,480", time: "Just now" }, '
                    '{ id: "activity-2", title: "Expense categorized", detail: "Uber · Travel · 38.20", time: "12m ago" }, '
                    '{ id: "activity-3", title: "Payment received", detail: "Bright Labs · INV-1038", time: "1h ago" }, '
                    '{ id: "activity-4", title: "Bank feed synced", detail: "Chase *4491 · 18 new lines", time: "2h ago" }'
                ),
                (
                    '{ id: "activity-1", title: "Fill · AAPL 10k", detail: "Avg 198.22 · rest working", time: "Just now" }, '
                    '{ id: "activity-2", title: "Ticket staged · NVDA", detail: "Buy 8k @ 905.00", time: "4m ago" }, '
                    '{ id: "activity-3", title: "Risk check passed", detail: "MSFT sell within net limit", time: "11m ago" }, '
                    '{ id: "activity-4", title: "Replace · AMZN", detail: "Qty 3.2k → 2.8k", time: "18m ago" }, '
                    '{ id: "activity-5", title: "Limit warning", detail: "Tech sleeve 28% soft cap", time: "22m ago" }'
                ),
                (
                    '{ id: "activity-1", title: "Record updated", detail: "The latest details are ready.", time: "Just now" }, '
                    '{ id: "activity-2", title: "Owner assigned", detail: "Waiting on confirmation.", time: "12m ago" }, '
                    '{ id: "activity-3", title: "Note added", detail: "Internal handoff logged.", time: "1h ago" }'
                ),
            )
            + '])} />'
        ),
        "risk": (
            '<RiskQueue heading="'
            + _d("Exceptions", "Risk limits", "Needs attention")
            + '" items={(seed.risk ?? ['
            + _d(
                (
                    '{ id: "risk-1", title: "4 invoices overdue", detail: "3,120 total · oldest 12 days", severity: "high" }, '
                    '{ id: "risk-2", title: "12 unmatched bank lines", detail: "Reconciliation incomplete", severity: "medium" }, '
                    '{ id: "risk-3", title: "3 expenses uncategorized", detail: "Needs bookkeeper review", severity: "low" }'
                ),
                (
                    '{ id: "risk-1", title: "Sector concentration", detail: "Tech sleeve at 28% of NAV", severity: "medium" }, '
                    '{ id: "risk-2", title: "Single-name", detail: "NVDA 9.1% vs 10% hard", severity: "low" }, '
                    '{ id: "risk-3", title: "Gross utilization", detail: "62% of 75% book limit", severity: "low" }'
                ),
                '{ id: "risk-1", title: "Follow-up due", detail: "An internal item needs confirmation.", severity: "medium" }',
            )
            + '])} />'
        ),
        "empty": '<EmptyState title="Nothing here yet" description="New records will appear here." />',
    }
    # A detail page describes the item its route param resolved to. Falling back
    # to the generic slot would render the same page for every id.
    if item_bound:
        # variant="item" overrides recipeHeroVariant — painting-first, no brand billboard.
        purchase_cta = (
            '{ label: "Contact for Purchase", href: "#inquire" }'
            if gallery
            else '{ label: "Inquire about this piece", href: "#inquire" }'
        )
        item_samples = {
            "hero": (
                f'<MarketingHero brandName={{{brand_js}}} '
                f'eyebrow={{{brand_js}}} headline={{itemTitle}} '
                'subcopy={String(item?.description ?? "")} '
                'variant="item" '
                f'primaryCta={{{purchase_cta}}} '
                f'secondaryCta={{{{ label: "Back to the collection", href: {_js(catalog_detail_base)} }}}} '
                'imageSrc={itemImage} imageAlt={itemTitle} />'
            ),
            "credentials": (
                f'<CredentialStrip heading={_js("Details")} items={{itemSpecs}} />'
            ),
            "inquire": (
                f'<InquiryPanel heading={inquire_heading_fb} '
                'itemId={itemKey} itemTitle={itemTitle} />'
            ),
        }
        if slot in item_samples:
            return item_samples[slot]

    # The browse page's showcase slot is a catalogue, not an editorial mosaic.
    if slot == "showcase" and slot_component_for(slot, skeleton_id) == "CatalogGrid":
        slot = "catalog"
    try:
        return samples[slot]
    except KeyError as exc:
        raise ValueError(f"Unsupported catalogue fallback slot: {slot}") from exc


_SCHEDULE_HINTS = (
    "class",
    "classes",
    "workshop",
    "workshops",
    "schedule",
    "session",
    "sessions",
    "service",
    "services",
    "treatment",
    "treatments",
    "booking-list",
)

# People/provider directories — must not render as another cinematic home hero.
_DIRECTORY_PATH_SEGMENTS = frozenset(
    {
        "doctors",
        "doctor",
        "providers",
        "provider",
        "dentists",
        "dentist",
        "physicians",
        "physician",
        "specialists",
        "specialist",
        "practitioners",
        "practitioner",
        "clinicians",
        "clinician",
        "team",
        "our-team",
        "meet-the-team",
        "care-team",
    }
)

_DIRECTORY_TITLE_HINTS = (
    "doctor listing",
    "doctors",
    "providers",
    "meet the team",
    "our team",
    "care team",
    "provider directory",
    "find a doctor",
    "our doctors",
    "our providers",
)


def _route_text_blob(file_path: str, route: dict) -> str:
    parts = [
        str(route.get("path") or ""),
        str(route.get("title") or ""),
        str(route.get("page_id") or ""),
        str(route.get("app_spec_page_id") or ""),
        canonical_workspace_path(file_path),
    ]
    return " ".join(parts).lower()


def _is_ops_path(path: str) -> bool:
    p = (path or "").lower()
    return p.startswith(("/staff", "/admin", "/owner", "/ops", "/member", "/desk"))


def _is_schedule_listing_route(file_path: str, route: dict) -> bool:
    """Classes/services listings get ScheduleRail — not a home marketing clone."""
    if _is_directory_listing_route(file_path, route):
        return False
    skeleton_id = str(route.get("skeleton_id") or "")
    if skeleton_id not in {
        "public-service",
        "public-booking",
        "public-catalog",
        "public-home",
    }:
        return False
    path = str(route.get("path") or "").lower().rstrip("/")
    # Detail routes like /classes/:id are not the listing face.
    if re.search(r"/:\w+", path) or re.search(r"/\{[^}]+\}", path):
        return False
    file_blob = canonical_workspace_path(file_path).lower()
    if "detail" in file_blob:
        return False
    blob = _route_text_blob(file_path, route)
    return any(hint in blob for hint in _SCHEDULE_HINTS)


def _browse_leaf(route_path: str) -> str:
    """Last non-param segment of a route — `/shop/items/:id` -> `items`."""
    stripped = re.sub(r"/:\w+|/\{[^}]+\}", "", str(route_path or ""))
    return stripped.rstrip("/").rsplit("/", 1)[-1].lower()


def _is_public_face(route: dict) -> bool:
    """A visitor-facing route: PublicShell, and not hanging under an ops prefix."""
    return expected_shell(route) != "OpsShell" and not _is_ops_path(
        str(route.get("path") or "")
    )


def schedule_face_required(file_path: str, route: dict) -> bool:
    """Whether this route's page **must** render a `ScheduleRail`.

    The single answer, for the generator, the gate and the repair alike.
    `_is_schedule_listing_route` is only half the rule: it says "this route looks
    like a classes/services listing", and the dispatcher in
    `minimal_catalogue_page_scaffold` then overrides it in two cases. Those
    overrides used to live at the call site, so only the generator applied them.

    Requests 147 (Meridian Physiotherapy), 148 (Ridgeline Bike Works) and 150
    (Copperline Hardware) were all withheld on `listing_not_schedule_rail`
    against pages that had no business carrying a rail. Each architect had set
    `page_intent`, so the generator correctly built a CatalogGrid listing — and
    the gate, calling the bare predicate, failed the page for not being the thing
    the pipeline had just decided it should not be. 147's was the run's only gate
    issue. `repair.py` had drifted a third way, inlining `page_intent != "listing"`
    at one of its two sites, so the repair loop rewrote the page with the same
    dispatcher that would not emit a rail and then failed it again.

    The two overrides, restated here so they cannot drift again:

    - **`page_intent` wins.** An explicit intent is the architect's contract; the
      keyword pickers exist only for legacy/thin contracts that left it blank.
    - **A catalogue browse leaf wins, on a public face.** `/shop`, `/gallery` and
      friends are CatalogGrid browse routes even when the keywords say schedule
      (request 64). Ops routes keep the rail: `_directory_listing_scaffold`
      builds a *public* face and the contract validator rejects it on an
      OpsShell route, so the generator deliberately lets those fall through.
    """
    if not _is_schedule_listing_route(file_path, route):
        return False
    if str(route.get("page_intent") or "").strip().lower():
        return False
    if _browse_leaf(route.get("path") or "") in CATALOG_BROWSE_LEAVES:
        return not _is_public_face(route)
    return True


def _is_directory_listing_route(file_path: str, route: dict) -> bool:
    """Doctor/provider/team directories get a people grid — not the homepage hero."""
    skeleton_id = str(route.get("skeleton_id") or "")
    if skeleton_id and skeleton_id not in {
        "public-service",
        "public-catalog",
        "public-detail",
        "public-home",
        "public-booking",
    }:
        return False
    path = str(route.get("path") or "").lower().rstrip("/") or "/"
    if _is_ops_path(path):
        return False
    if re.search(r"/:\w+", path) or re.search(r"/\{[^}]+\}", path):
        return False
    segments = [s for s in path.strip("/").split("/") if s]
    if any(seg in _DIRECTORY_PATH_SEGMENTS for seg in segments):
        return True
    blob = _route_text_blob(file_path, route)
    return any(hint in blob for hint in _DIRECTORY_TITLE_HINTS)


def _schedule_listing_scaffold(
    *,
    component: str,
    brand: str,
    title: str,
    listing_path: str,
    page_id: str,
    action_ids: list[str],
    evidence_ids: list[str],
    architect: dict | None = None,
) -> str:
    brand_js = _js(brand)
    title_js = _js(title)
    base = (listing_path or "/classes").rstrip("/") or "/classes"
    base_js = _js(base)
    # The declared booking route, not the word "book". An app that declares no
    # booking page keeps its visitor on this page's own rail rather than being
    # handed a path the router will not match.
    book_path = booking_route(architect)
    book_js = _js(book_path or "#classes-list")
    item_href = (
        "`${BOOK_PATH}?service=${encodeURIComponent(String(s.id || i + 1))}`"
        if book_path
        else "BOOK_PATH"
    )
    # "Contact" only when there is a contact page; otherwise the rail itself is
    # the second option, and it is on this page.
    contact_path = _contact_route(architect)
    schedule_contact_label = _js("Contact" if contact_path else "Browse schedule")
    schedule_contact_href = _js(contact_path or "#classes-list")
    appspec_attrs = f" data-appspec-page={_js(page_id)}" if page_id else ""
    span_lines: list[str] = []
    for action_id in action_ids:
        span_lines.append(
            f'        <span className="sr-only" data-appspec-action={_js(action_id)}>'
            f"{action_id}</span>"
        )
    for evidence_id in evidence_ids:
        span_lines.append(
            f'        <span className="sr-only" data-appspec-evidence={_js(evidence_id)}>'
            f"{evidence_id}</span>"
        )
    appspec_hook_spans = ("\n" + "\n".join(span_lines) + "\n") if span_lines else "\n"
    return f"""// schedule listing scaffold — distinct from home marketing clone
import {{ usePublicNavItems, publicCta }} from '@/lib/app-nav';
import {{ BRAND_MANIFEST, images }} from '@/data/mock';
import {{ PublicShell, PublicNav, MarketingHero, ScheduleRail, CTABand, BrandFooter }} from '@/ui';

const services = Array.isArray(BRAND_MANIFEST?.services) ? BRAND_MANIFEST.services : [];
const LISTING_BASE = {base_js};
const BOOK_PATH = {book_js};

export default function {component}() {{
  const navItems = usePublicNavItems();
  const navCta = publicCta();
  const items = services.map((s: any, i: number) => ({{
    id: String(s.id || `session-${{i}}`),
    name: String(s.name || s.title || 'Session'),
    description: String(s.description || ''),
    duration: String(s.duration || ''),
    level: String(s.level || 'All Levels'),
    day: String(s.day || ''),
    status: String(s.status || 'Open'),
    // BOOK_PATH is this app's declared booking route; a query keeps the service
    // without inventing a /services/:id route the app does not have.
    href: {item_href},
  }}));

  return (
    <PublicShell brandName={{{brand_js}}} chrome="immersive" nav={{<PublicNav items={{navItems}} cta={{navCta}} />}}>
      <div data-skeleton="public-service"{appspec_attrs}>{appspec_hook_spans}
      <MarketingHero
        brandName={{{brand_js}}}
        headline={{{title_js}}}
        subcopy="Pick a session from the schedule — levels, times, and open seats in one place."
        primaryCta={{{{ label: "Browse schedule", href: "#classes-list" }}}}
        secondaryCta={{{{ label: "Book a time", href: {book_js} }}}}
        imageSrc={{images.hero}}
        imageAlt=""
      />
      <ScheduleRail
        heading="Upcoming sessions"
        description="Filter by level or day. Full sessions can join the waitlist."
        detailBase={{BOOK_PATH}}
        items={{items}}
      />
      <CTABand
        heading="Not sure which session fits?"
        description="Browse the schedule, or get in touch and we will help you pick a time."
        primaryCta={{{{ label: "Book a time", href: {book_js} }}}}
        secondaryCta={{{{ label: {schedule_contact_label}, href: {schedule_contact_href} }}}}
      />
      <BrandFooter brandName={{{brand_js}}} description="Clear schedules. Real bookings. Brand-first pages." />
      </div>
    </PublicShell>
  );
}}
"""


def _card_detail_base(listing_path: str, architect: dict | None) -> str:
    """Where a listing card's link must point — a route that is declared.

    Request 66 shipped ten dead cards on `/gallery`. The scaffold used the
    listing page's **own** path as the card base, so every card linked
    `/gallery/<slug>`; the route table declared `/collection/:id` and
    `/painting-detail/:id` and no `/gallery/:id`, so `path="*"` sent all ten
    clicks to the home page. The journey gate reported it
    (`journey_dead_link:/gallery/:id`) and the preview shipped anyway.

    The listing's own path wins when the planner actually declared a param route
    under it — `/gallery` + `/gallery/:id` is the natural pairing and keeps the
    card link and the "back to the collection" link agreeing. Otherwise the
    declared detail base is the only honest answer. Falling back to the listing
    path preserves today's behaviour when nothing is declared at all, which is a
    dead link the journey repair still has to catch — but it is no longer the
    *first* choice over a route that exists.
    """
    listing = (listing_path or "").rstrip("/")
    routes = list((architect or {}).get("routes") or [])
    declared = {str(r.get("path") or "").rstrip("/") for r in routes}
    param_bases = set()
    for route in routes:
        path = str(route.get("path") or "")
        if "/:" not in path:
            continue
        surface = str(route.get("surface") or "").lower()
        if surface == "ops" or path.startswith(("/admin", "/owner", "/ops", "/staff")):
            continue
        base = path.split("/:", 1)[0].rstrip("/")
        if base:
            param_bases.add(base)
    if listing and listing in param_bases:
        return listing
    return catalogue_detail_base(architect) or listing


def _directory_listing_scaffold(
    *,
    component: str,
    brand: str,
    title: str,
    listing_path: str,
    page_id: str,
    action_ids: list[str],
    evidence_ids: list[str],
    people_directory: bool = False,
    skeleton_id: str = "",
    architect: dict | None = None,
) -> str:
    brand_js = _js(brand)
    title_js = _js(title)
    listing_base = (listing_path or "/doctors").rstrip("/") or "/doctors"
    base = _card_detail_base(listing_base, architect) or listing_base
    base_js = _js(base)
    appspec_attrs = f" data-appspec-page={_js(page_id)}" if page_id else ""
    span_lines: list[str] = []
    for action_id in action_ids:
        span_lines.append(
            f'        <span className="sr-only" data-appspec-action={_js(action_id)}>'
            f"{action_id}</span>"
        )
    for evidence_id in evidence_ids:
        span_lines.append(
            f'        <span className="sr-only" data-appspec-evidence={_js(evidence_id)}>'
            f"{evidence_id}</span>"
        )
    appspec_hook_spans = ("\n" + "\n".join(span_lines) + "\n") if span_lines else "\n"
    # Three faces, decided by what the page *is* rather than by keyword luck.
    # "Meet the team / Dr. Avery Chen / Book a visit" used to be the default for
    # every listing whose brand, title and path all missed a nine-word keyword
    # list — which is how a fine-art gallery's own listing shipped a clinic.
    #
    # The CTA target is chosen separately from the copy: a service business's
    # listing must hand off to its booking route (that hop is the funnel), while a
    # storefront's cards each carry their own detail link.
    booking_face = (skeleton_id or "").lower() in {"public-service", "public-booking"}
    storefront_listing = not people_directory
    # The booking hop is this page's whole funnel, so it has to land on the route
    # the architect actually declared for it — `/service/book` on request 148,
    # `/hire/reserve` on 150. When no booking page is declared the CTA becomes an
    # in-page ask rather than a click that lands the visitor back home.
    book_path = booking_route(architect)
    book_cta = (
        f'{{ label: "Book a visit", href: {_js(book_path)} }}'
        if book_path
        else _NO_ROUTE_CTA
    )
    contact_href = _contact_route(architect)
    if people_directory:
        cta_primary = book_cta
        cta_secondary = (
            f'{{ label: "Contact", href: {_js(contact_href)} }}'
            if contact_href
            else '{ label: "Back home", href: "/" }'
        )
        footer_desc = "Real providers. Clear booking. Not another homepage clone."
        page_desc = "Browse providers, specialties, and availability — then book the right visit."
        showcase_desc = "Each card opens a provider profile. Book when you are ready."
        cta_heading = "Ready to schedule?"
        cta_desc = "Pick a time online — same team you just reviewed."
    elif booking_face:
        cta_primary = book_cta
        cta_secondary = '{ label: "Back home", href: "/" }'
        footer_desc = f"{brand} — clear options, real availability."
        page_desc = "Browse what is offered, then pick a time that works."
        showcase_desc = "Each card opens the details. Book when you are ready."
        cta_heading = "Ready to book?"
        cta_desc = "Choose a time online and get a confirmation straight away."
    else:
        # "/about" is not in the storefront route table — this CTA was a dead link.
        # The grid anchor CatalogGrid renders (#catalog) is on this page, and the
        # per-item inquiry lives on the detail route each card already links to.
        cta_primary = '{ label: "Browse the collection", href: "#catalog" }'
        cta_secondary = '{ label: "Back home", href: "/" }'
        footer_desc = "Browse the collection. Inquire when a piece speaks to you."
        page_desc = "Browse pieces and details — then inquire about availability."
        showcase_desc = "Each card opens a closer look. Inquire when you are ready."
        cta_heading = "Interested in a piece?"
        cta_desc = "Ask about availability, commissions, or a studio visit."

    # `CatalogGrid heading=""` below: the PageHeader band already states this
    # page's title, and a second display heading 150px under it is a duplicate,
    # not a section. CatalogGrid drops its header block on an empty heading and
    # keeps the item count.
    #
    # This note lives in Python on purpose. It was briefly a JSX comment in the
    # emitted page and broke the build twice over — first inside the opening tag,
    # where `{` begins a spread, then as a child, where the `*/` in its own
    # example closed the comment early. A remark about how the generator works is
    # for whoever reads the generator; the page it writes does not need it, and
    # every character emitted into a page is a character that can fail to parse.
    #
    # A service listing has no per-item detail route — the funnel goes straight to
    # booking — so numbering its cards into `/services/:id` would point every one of
    # them at a path the planner never declared.
    # An app that declares no booking page has nowhere for these cards to go, so
    # they hold the visitor on the grid (`#catalog` is the anchor CatalogGrid
    # renders below) rather than pointing at a `/book` it never declared.
    item_href = (
        _js(book_path or "#catalog")
        if booking_face
        else f"`{base}/${{String(s.slug || s.id || i + 1)}}`"
    )
    return f"""// directory listing scaffold — distinct from home marketing clone
import {{ usePublicNavItems, publicCta }} from '@/lib/app-nav';
import {{ images, seed }} from '@/data/mock';
import {{ PublicShell, PublicNav, PageHeader, CatalogGrid, CTABand, BrandFooter }} from '@/ui';

// One catalogue for the whole app: `seed.items` is what the detail route resolves
// against, so a listing that invents its own array links every card to a page
// that renders "not found". `BRAND_MANIFEST.services` used to be read here and
// does not exist at that level — `tsc` reported it as TS2339 and the array below
// fell through to three hardcoded doctors on every business that took this path.
const catalogue: any[] = Array.isArray((seed as any).items) ? (seed as any).items : [];
const offerings: any[] = Array.isArray((seed as any).services) ? (seed as any).services : [];
const entries: any[] = catalogue.length ? catalogue : offerings;
const IMAGE_POOL = [images.item1, images.item2, images.item3, images.item4, images.item5, images.item6, images.item7, images.item8];
const LISTING_BASE = {base_js};

export default function {component}() {{
  const navItems = usePublicNavItems();
  const navCta = publicCta();
  // CatalogGrid renders every entry and links each into LISTING_BASE/:id.
  // ProductShowcase used to fill this slot and silently showed only three.
  const people = entries.map((s: any, i: number) => ({{
    id: String(s.id || s.slug || i + 1),
    title: String(s.name || s.title || {brand_js} + ' ' + (i + 1)),
    description: String(s.description || s.specialty || s.role || ''),
    imageSrc: String(s.image || s.imageSrc || IMAGE_POOL[i % IMAGE_POOL.length]),
    imageAlt: String(s.name || s.title || 'Item'),
    meta: s.medium ? String(s.medium) : undefined,
    category: s.category ? String(s.category) : undefined,
    badge: s.badge ? String(s.badge) : undefined,
    status: s.status ? String(s.status) : undefined,
    // Written out per item with the target inlined, not left to CatalogGrid's
    // `detailBase` derivation: the journey walk reads links, and a page that only
    // named its base in a const looked like a browse face with no way out of it.
    href: {item_href},
  }}));

  return (
    <PublicShell brandName={{{brand_js}}} chrome="solid" nav={{<PublicNav items={{navItems}} cta={{navCta}} />}}>
      <div data-skeleton="public-catalog"{appspec_attrs}>{appspec_hook_spans}
      <div className={_js(_PAGE_HEADER_BAND)}>
        <PageHeader
          title={{{title_js}}}
          description={_js(page_desc)}
        />
      </div>
      <CatalogGrid
        heading=""
        description={_js(showcase_desc)}
        detailBase={{LISTING_BASE}}
        itemNoun={_js("pieces" if storefront_listing else "providers")}
        items={{people}}
      />
      <CTABand
        heading={_js(cta_heading)}
        description={_js(cta_desc)}
        primaryCta={{{cta_primary}}}
        secondaryCta={{{cta_secondary}}}
      />
      <BrandFooter brandName={{{brand_js}}} description={_js(footer_desc)} />
      </div>
    </PublicShell>
  );
}}
"""


def minimal_catalogue_page_scaffold(
    file_path: str,
    route: dict,
    *,
    brand_name: str | None = None,
    architect: dict | None = None,
) -> str:
    stem = canonical_workspace_path(file_path).split("/")[-1].rsplit(".", 1)[0]
    component = re.sub(r"[^A-Za-z0-9_]", "", stem) or "CataloguePage"
    if component[0].isdigit():
        component = f"Page{component}"
    brand = brand_name or "Brand"
    title = str(route.get("title") or component.replace("Page", "") or "Overview")
    page_id = str(route.get("app_spec_page_id") or route.get("page_id") or "").strip()
    action_ids = [str(a) for a in (route.get("action_ids") or []) if a]
    evidence_ids = [str(e) for e in (route.get("evidence_ids") or []) if e]
    # Contact/auth are form faces — never a public-service marketing clone.
    # Request 61's ContactPage shipped "Book a visit" + FeatureBento and no
    # InquiryPanel because architect assigned public-service and scaffold-first
    # skipped the utility compositor.
    route_path_early = str(route.get("path") or "")
    from app.application.preview_app.utility_compositor import (
        compose_utility_page_tsx,
        infer_utility_workspace_type,
    )

    early_wtype = infer_utility_workspace_type(
        route_path_early,
        title,
        str(route.get("page_type") or ""),
    )
    if early_wtype in {"contact", "auth"}:
        return compose_utility_page_tsx(
            file_path=file_path,
            route={**route, "skeleton_id": "public-utility"},
            content={},
            brand_name=brand,
            workspace_type=early_wtype,
            architect=architect,
        )
    # Product Face Contract: page_intent wins over industry/path keywords — but
    # NOT over surface. `_directory_listing_scaffold` builds a *public* face
    # (PublicShell + PublicNav + CatalogGrid); handing it an ops route produced
    # the owner's "Manage Paintings" page wearing the storefront nav, and the
    # contract validator then rejected it for the OpsShell/header/filters/table
    # it could not contain. An ops listing falls through to the generic scaffold
    # below, which builds the shell and slots its own skeleton declares.
    intent = str(route.get("page_intent") or "").strip().lower()
    public_face = _is_public_face(route)
    route_path = str(route.get("path") or "")
    # Param routes are item detail (or nested record) faces — never a directory
    # listing. Request 50's CollectionDetail at `/gallery/:collectionId` had
    # page_intent=listing and shipped CatalogGrid with literal `:collectionId`
    # in every card href.
    has_route_param = bool(
        re.search(r"/:\w+", route_path) or re.search(r"/\{[^}]+\}", route_path)
    )
    skeleton_hint = str(route.get("skeleton_id") or "")
    browse_leaf = _browse_leaf(route_path)
    # Gallery/shop browse routes must always be CatalogGrid faces — even when the
    # architect left page_intent empty or assigned public-home. Request 64's
    # /gallery shipped ProductShowcase (3-card cap) and failed journey_browse_caps.
    force_catalog_browse = browse_leaf in CATALOG_BROWSE_LEAVES
    # A classes/services listing is a schedule face, not a product grid — it
    # needs times and prices, and its funnel goes to /book, not to a per-item
    # detail route it never declares. The `page_intent` and browse-leaf overrides
    # that used to be spelled out here now live in `schedule_face_required`, so
    # the gate and the repair resolve this the same way the generator does.
    schedule_face = schedule_face_required(file_path, route)
    if (
        public_face
        and not has_route_param
        and skeleton_hint != "public-detail"
        and not schedule_face
        and (intent == "listing" or force_catalog_browse or skeleton_hint == "public-catalog")
    ):
        listing_path = route_path or "/listing"
        # Belt-and-suspenders: never embed `:id` in CatalogGrid detailBase.
        listing_path = re.sub(r"/:\w+|/\{[^}]+\}", "", listing_path).rstrip("/") or "/listing"
        return _directory_listing_scaffold(
            component=component,
            brand=brand,
            title=title,
            listing_path=listing_path,
            page_id=page_id,
            action_ids=action_ids,
            evidence_ids=evidence_ids,
            people_directory=_is_directory_listing_route(file_path, route)
            and not force_catalog_browse,
            skeleton_id=skeleton_hint or "public-catalog",
            architect=architect,
        )
    # Keyword face pickers — only when intent is absent (legacy / thin contracts).
    if not intent and not has_route_param and _is_directory_listing_route(file_path, route):
        return _directory_listing_scaffold(
            component=component,
            brand=brand,
            title=title,
            listing_path=str(route.get("path") or "/doctors"),
            page_id=page_id,
            action_ids=action_ids,
            evidence_ids=evidence_ids,
            people_directory=True,
            skeleton_id=str(route.get("skeleton_id") or ""),
            architect=architect,
        )
    if schedule_face:
        return _schedule_listing_scaffold(
            component=component,
            brand=brand,
            title=title,
            listing_path=str(route.get("path") or "/classes"),
            page_id=page_id,
            action_ids=action_ids,
            evidence_ids=evidence_ids,
            architect=architect,
        )
    skeleton_id = str(route["skeleton_id"])
    shell = expected_shell(route)
    slots = assigned_non_shell_slots(route)
    slots = _ensure_terminal_action_slot(skeleton_id, slots)
    # A detail page resolves its route param and describes that one item.
    detail_bound = skeleton_id == "public-detail" and shell == "PublicShell"
    if detail_bound:
        # Painting → specs → inquire before any "Why brand" marketing stack.
        slots = _paint_first_detail_slots(slots)
    components = [shell, "getSkeleton"]
    if detail_bound:
        components.append("Button")  # not-found path links back to the collection
    if skeleton_id in _COMPOSE_LAYOUT_SKELETONS:
        components.append("composeSkeletonLayout")
    else:
        components.append("SkeletonComposer")
    if shell == "PublicShell" and "PublicNav" not in components:
        components.append("PublicNav")
    for slot in slots:
        slot_component = slot_component_for(slot, skeleton_id)
        if slot_component and slot_component not in components:
            components.append(slot_component)
    path = str(route.get("path") or "")
    # A catalogue face derives its base from its own path — `/gallery/:id` hangs
    # off `/gallery`, and a browse page is its own base. Every other page has no
    # claim on one and must read the table: a booking page carrying a `showcase`
    # slot numbered its cards into `/service/book/:_`, which is a route no app
    # declares, and before that into the `/gallery` default, which is worse.
    own_base = path if skeleton_id in {"public-catalog", "public-detail"} else ""
    detail_base = catalog_base_from_path(own_base, architect)
    slot_lines = "\n".join(
        "    {slot}: (\n      {jsx}\n    ),".format(
            slot=slot,
            jsx=_safe_slot_jsx(
                slot,
                brand,
                title,
                skeleton_id=skeleton_id,
                item_bound=detail_bound,
                detail_base=detail_base,
                architect=architect,
            ),
        )
        for slot in slots
    )
    is_member = path.startswith("/member") or "/member/" in canonical_workspace_path(file_path)
    # The param block reads seed.items and indexes the image pool, so a detail
    # page needs both imports regardless of which slots it ended up with.
    uses_seed = detail_bound or any(slot in _SEED_SLOTS for slot in slots)
    needs_images = detail_bound or any(
        "images."
        in _safe_slot_jsx(
            slot,
            brand,
            title,
            skeleton_id=skeleton_id,
            item_bound=detail_bound,
            detail_base=detail_base,
            architect=architect,
        )
        for slot in slots
    )
    if uses_seed and needs_images:
        images_import = "import { images, seed } from '@/data/mock';\n"
    elif uses_seed:
        images_import = "import { seed } from '@/data/mock';\n"
    elif needs_images:
        images_import = "import { images } from '@/data/mock';\n"
    else:
        images_import = ""
    appspec_attrs = f' data-appspec-page={_js(page_id)}' if page_id else ""
    appspec_hook_spans = ""
    if page_id:
        span_lines = []
        for action_id in action_ids:
            span_lines.append(
                f'        <span className="sr-only" data-appspec-action={_js(action_id)}>'
                f"{action_id}</span>"
            )
        for evidence_id in evidence_ids:
            span_lines.append(
                f'        <span className="sr-only" data-appspec-evidence={_js(evidence_id)}>'
                f"{evidence_id}</span>"
            )
        appspec_hook_spans = ("\n" + "\n".join(span_lines) + "\n") if span_lines else "\n"
    if shell == "OpsShell":
        nav_import = "import { useAdminNavItems } from '@/lib/app-nav';\n"
        nav_hook = "  const adminNavItems = useAdminNavItems();\n"
        if skeleton_id in _COMPOSE_LAYOUT_SKELETONS:
            appearance = (
                ' appearance="floor"'
                if (
                    skeleton_id in _FLOOR_APPEARANCE_SKELETONS
                    or _is_trading_domain(brand, title)
                )
                else ""
            )
            body = (
                "  const { main, rail } = composeSkeletonLayout(SKELETON_ID, slots);\n\n"
                "  return (\n"
                f'    <{shell} brandName={{{_js(brand)}}} navItems={{adminNavItems}} rail={{rail}}{appearance}>\n'
                f"      <div data-skeleton={{skeleton.id}}{appspec_attrs}>"
                f"{appspec_hook_spans}{{main}}</div>\n"
                f"    </{shell}>\n"
                "  );"
            )
        else:
            body = (
                "  return (\n"
                f'    <{shell} brandName={{{_js(brand)}}} navItems={{adminNavItems}}>\n'
                f"      <div data-skeleton={{skeleton.id}}{appspec_attrs}>\n"
                f"{appspec_hook_spans}"
                "        <SkeletonComposer skeletonId={SKELETON_ID} slots={slots} />\n"
                "      </div>\n"
                f"    </{shell}>\n"
                "  );"
            )
    else:
        hook = "useMemberNavItems" if is_member else "usePublicNavItems"
        cta = "memberCta" if is_member else "publicCta"
        nav_import = f"import {{ {hook}, {cta} }} from '@/lib/app-nav';\n"
        nav_hook = f"  const navItems = {hook}();\n  const navCta = {cta}();\n"
        if detail_bound:
            # useParams must be imported and the resolution must run before the
            # slot map, which references item/itemTitle/itemSpecs/notFound.
            nav_import = (
                "import { useParams } from 'react-router-dom';\n" + nav_import
            )
            nav_hook = nav_hook + _detail_param_block(brand, detail_base)
        # Detail pages use solid chrome so the sticky/fixed nav never paints
        # over the artwork image (immersive recipes otherwise overlay the hero).
        chrome_attr = ' chrome="solid"' if detail_bound else ""
        use_recipe_order = skeleton_id in {
            "public-home",
            "public-service",
            "public-detail",
            "public-booking",
            "public-catalog",
        } and bool(slots)
        composer = (
            "        <SkeletonComposer skeletonId={SKELETON_ID} slots={slots} order={RECIPE_ORDER} />\n"
            if use_recipe_order
            else "        <SkeletonComposer skeletonId={SKELETON_ID} slots={slots} />\n"
        )
        body = (
            "  return (\n"
            f'    <{shell} brandName={{{_js(brand)}}}{chrome_attr} '
            f'nav={{<PublicNav items={{navItems}} cta={{navCta}} />}}>\n'
            f"      <div data-skeleton={{skeleton.id}}{appspec_attrs}>\n"
            f"{appspec_hook_spans}"
            f"{composer}"
            "      </div>\n"
            f"    </{shell}>\n"
            "  );"
        )
        if detail_bound:
            body = (
                _detail_not_found_block(shell, _js(brand), detail_base, appspec_attrs)
                + "\n"
                + body
            )
    order_const = (
        f"const RECIPE_ORDER = {_js(slots)} as const;\n\n"
        if skeleton_id
        in {
            "public-home",
            "public-service",
            "public-detail",
            "public-booking",
            "public-catalog",
        }
        and slots
        else ""
    )
    return f"""// deterministic catalogue contract scaffold
{nav_import}{images_import}import {{ {", ".join(components)} }} from '@/ui';

const SKELETON_ID = {_js(skeleton_id)} as const;
{order_const}export default function {component}() {{
{nav_hook}  const skeleton = getSkeleton(SKELETON_ID);
  const slots = {{
{slot_lines}
  }};

{body}
}}
"""
