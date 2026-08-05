"""Product-kind-first preview contract.

Classify the brief into a product kind, lock surface/skeleton/pages, then let
planners fill copy inside that chrome — never invent a marketing landing for
SaaS/ops products.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

ProductKind = Literal[
    "storefront",
    "booking_service",
    "saas_workspace",
    "internal_ops",
]

OPS_KINDS: frozenset[str] = frozenset({"saas_workspace", "internal_ops"})
PUBLIC_KINDS: frozenset[str] = frozenset({"storefront", "booking_service"})

_OPS_DASHBOARD_SLOTS = ["header", "kpis", "filters", "table", "chart", "activity", "risk"]
_OPS_LEDGER_HOME_SLOTS = ["header", "pulse", "kpis", "filters", "table", "chart", "activity"]
_OPS_INVOICE_BOARD_SLOTS = ["header", "filters", "board"]
_OPS_RECON_SPLIT_SLOTS = ["header", "filters", "recon"]
_OPS_BLOTTER_DESK_SLOTS = ["header", "ticker", "kpis", "blotter", "chart", "risk", "activity"]
_OPS_EXPENSE_QUEUE_SLOTS = ["header", "filters", "expenses"]
_OPS_LIST_SLOTS = ["header", "filters", "table"]
_PUBLIC_HOME_SLOTS = ["hero", "features", "cta", "footer"]
_PUBLIC_DETAIL_SLOTS = ["hero", "credentials", "inquire", "cta", "footer"]
_PUBLIC_CATALOG_SLOTS = ["hero", "filters", "showcase", "features", "cta", "footer"]
_PUBLIC_BOOKING_SLOTS = ["hero", "features", "booking", "footer"]
_PUBLIC_SERVICE_SLOTS = ["hero", "features", "process", "cta", "footer"]

_OPS_HOME_SKELETONS = frozenset(
    {"ops-dashboard", "ops-ledger-home", "ops-blotter-desk"}
)


@dataclass(frozen=True)
class PageBlueprint:
    id: str
    title: str
    path: str
    page_type: str
    component_file: str
    purpose: str
    sample_data_notes: str = ""
    skeleton_id: str = "ops-list"
    surface: str = "ops"

    def section_slots(self) -> list[str]:
        if self.skeleton_id == "ops-dashboard":
            return list(_OPS_DASHBOARD_SLOTS)
        if self.skeleton_id == "ops-ledger-home":
            return list(_OPS_LEDGER_HOME_SLOTS)
        if self.skeleton_id == "ops-invoice-board":
            return list(_OPS_INVOICE_BOARD_SLOTS)
        if self.skeleton_id == "ops-recon-split":
            return list(_OPS_RECON_SPLIT_SLOTS)
        if self.skeleton_id == "ops-blotter-desk":
            return list(_OPS_BLOTTER_DESK_SLOTS)
        if self.skeleton_id == "ops-expense-queue":
            return list(_OPS_EXPENSE_QUEUE_SLOTS)
        if self.skeleton_id == "ops-settings":
            return ["header", "filters", "table"]
        if self.skeleton_id == "public-home":
            return list(_PUBLIC_HOME_SLOTS)
        if self.skeleton_id == "public-detail":
            return list(_PUBLIC_DETAIL_SLOTS)
        if self.skeleton_id == "public-catalog":
            return list(_PUBLIC_CATALOG_SLOTS)
        if self.skeleton_id == "public-booking":
            return list(_PUBLIC_BOOKING_SLOTS)
        if self.skeleton_id == "public-service":
            return list(_PUBLIC_SERVICE_SLOTS)
        if self.skeleton_id.startswith("ops"):
            return list(_OPS_LIST_SLOTS)
        if self.skeleton_id.startswith("public"):
            return list(_PUBLIC_HOME_SLOTS)
        return list(_OPS_LIST_SLOTS)


@dataclass(frozen=True)
class ProductKindContract:
    kind: ProductKind
    recipe_id: str
    home_surface: str
    home_skeleton_id: str
    pages: tuple[PageBlueprint, ...]
    template_surface: str  # which industry pack surface to prefer
    design_note: str = ""
    subtype: str = ""  # accounting | trading | generic | ...

    def as_dict(self) -> dict[str, Any]:
        return {
            "product_kind": self.kind,
            "subtype": self.subtype,
            "recipe_id": self.recipe_id,
            "home_surface": self.home_surface,
            "home_skeleton_id": self.home_skeleton_id,
            "template_surface": self.template_surface,
            "design_note": self.design_note,
            "pages": [
                {
                    "id": p.id,
                    "title": p.title,
                    "path": p.path,
                    "page_type": p.page_type,
                    "component_file": p.component_file,
                    "purpose": p.purpose,
                    "sample_data_notes": p.sample_data_notes,
                    "skeleton_id": p.skeleton_id,
                    "surface": p.surface,
                    "section_slots": p.section_slots(),
                }
                for p in self.pages
            ],
        }


_INTERNAL_OPS_HINTS = (
    "hedge",
    "trading",
    "trader",
    "blotter",
    "oms",
    "execution",
    "portfolio manager",
    "risk officer",
    "fund book",
    "institutional",
    "internal desk",
    "internal trading",
    "warehouse floor",
    "floor control",
    "back office",
    "back-office",
    "not a saas",
    "not a retail",
    "not a client",
)

# Plain-English assertions that the tool is internal-facing. On their own they
# name an audience, not a product — they only flip the verdict when the brief
# also carries transactional/ops language (the rule in classify_product_kind).
_INTERNAL_FACING_HINTS = (
    "staff-only",
    "staff only",
    "internal only",
    "internal-only",
    "internal tool",
    "staff tool",
    "nobody outside",
    "no customer ever",
    "not a public",
    "never public",
)

# Transactional words that alone mean "workspace, not marketing landing" —
# and, beside an internal-facing assertion, "internal desk".
_TRANSACTIONAL_WORDS = (
    "dashboard",
    "reconcile",
    "invoice",
    "queue",
    "admin",
    "ops console",
    "workspace",
)

_SAAS_HINTS = (
    "saas",
    "software",
    "accounting",
    "bookkeep",
    "bookkeeper",
    "invoice",
    "invoicing",
    "ledger",
    "expense",
    "reconcil",
    "quickbooks",
    "xero",
    "freshbooks",
    "crm",
    "pipeline",
    "hr ",
    "payroll",
    "workspace",
    "dashboard product",
    "admin panel",
    "b2b",
    "cash flow",
    "cashflow",
    "chart of accounts",
)

_BOOKING_HINTS = (
    "booking",
    "appointment",
    "reservation",
    "reserve a table",
    "reserve a spot",
    "reserve a slot",
    "spa",
    "salon",
    "clinic",
    "dental",
    "yoga",
    "pilates",
    "class schedule",
    "tutoring",
    "therapy",
    "lesson",
    "instructor",
)

_STOREFRONT_HINTS = (
    "restaurant",
    "cafe",
    "café",
    "menu",
    "retail",
    "shop",
    "storefront",
    "e-commerce",
    "ecommerce",
    "boutique",
    "hotel",
    "hospitality",
    "real estate",
    "dealership",
    "pottery",
    "gallery",
    "painting",
    "artwork",
    "artist",
    "atelier",
    "fine art",
    "collector",
    "portfolio",
)

# Briefs often say "not a booking SaaS" — substring classifiers must not treat that as intent.
_NEGATED_PRODUCT_CLAUSE = re.compile(
    r"\b(?:not|never)\s+(?:a\s+|an\s+|the\s+)?"
    r"(?:booking(?:\s+saas)?|saas|ops(?:\s+dashboard)?|marketplace(?:\s+feed)?|"
    r"retail|client(?:\s+facing)?|marketing(?:\s+landing)?|corporate)"
    r"(?:\s+or\s+ops(?:\s+dashboard)?)?",
    re.IGNORECASE,
)


def scrub_negated_product_clauses(text: str) -> str:
    """Drop 'not a booking SaaS / ops dashboard' style clauses before keyword hits."""
    return _NEGATED_PRODUCT_CLAUSE.sub(" ", str(text or ""))


class _HintBlob(str):
    """Classifier text whose `in` only matches a hint starting at a word edge.

    Left-anchored only: the hint tables hold deliberate stems ("reconcil",
    "bookkeep") whose inflections a right-side boundary would kill, and genuine
    suffix hosts (bookshop, physiotherapy) are the accepted cost. This is the
    prefix variant boundary_variant_census.py measured: it removes the bare
    substring class ("oms"@Rooms, "spa"@work**spa**ce) that let spelling
    accidents pick a product kind, and changes 0 of the 47 stored runs.
    """

    __slots__ = ()

    def __contains__(self, hint: object) -> bool:  # type: ignore[override]
        needle = str(hint)
        if not needle:
            return super().__contains__(needle)
        lead = r"(?<!\w)" if needle[0].isalnum() else ""
        return re.search(f"{lead}{re.escape(needle)}", self) is not None


def _blob(*parts: str) -> _HintBlob:
    return _HintBlob(
        scrub_negated_product_clauses(" ".join(str(p or "") for p in parts).lower())
    )


def _hits(blob: str, hints: tuple[str, ...]) -> int:
    return sum(1 for h in hints if h in blob)


def classify_product_kind(*parts: str) -> ProductKind:
    """Deterministic kind classifier. Ops/SaaS wins on transactional ambiguity."""
    text = _blob(*parts)
    internal = _hits(text, _INTERNAL_OPS_HINTS)
    saas = _hits(text, _SAAS_HINTS)
    booking = _hits(text, _BOOKING_HINTS)
    storefront = _hits(text, _STOREFRONT_HINTS)

    if internal >= 2:
        return "internal_ops"
    if saas >= 2:
        return "saas_workspace"
    if booking >= 2 and booking >= storefront:
        return "booking_service"
    if storefront >= 2:
        return "storefront"

    # Single strong signals
    if internal >= 1 and any(h in text for h in ("blotter", "oms", "hedge", "trading desk")):
        return "internal_ops"
    if saas >= 1 and any(
        h in text for h in ("invoice", "accounting", "bookkeep", "ledger", "saas")
    ):
        return "saas_workspace"

    # A brief that ASSERTS it is internal-facing and carries ops/transactional
    # language is an internal desk, not a SaaS product page. The assertion
    # alone names an audience, not a product — it never flips on its own, and
    # a brief that also reads as software stays a workspace (an internal
    # project tool is still a workspace; a staff desk names no software).
    if (
        saas == 0
        and _hits(text, _INTERNAL_FACING_HINTS) >= 1
        and (internal >= 1 or any(w in text for w in _TRANSACTIONAL_WORDS))
    ):
        return "internal_ops"

    # Ambiguous transactional language → workspace, not marketing landing
    if any(w in text for w in _TRANSACTIONAL_WORDS):
        return "saas_workspace"

    if booking >= 1:
        return "booking_service"
    if storefront >= 1:
        return "storefront"
    return "storefront"


def _trading_pages() -> tuple[PageBlueprint, ...]:
    return (
        PageBlueprint(
            "trading-desk",
            "Trading Desk",
            "/",
            "trading-desk",
            "src/pages/TradingDeskPage.tsx",
            "Primary fund desk — ticker, blotter tape, intraday P&L, risk rail.",
            "AAPL BUY 25k Working; Day P&L +1.24M; exposure 62%.",
            "ops-blotter-desk",
            "ops",
        ),
        PageBlueprint(
            "order-ticket",
            "Order Ticket",
            "/ticket",
            "order-ticket",
            "src/pages/OrderTicketPage.tsx",
            "Stage buy/sell tickets with size, limit, TIF, and pre-trade risk checks.",
            "NVDA BUY 8,000 @ 905.00 DAY.",
        ),
        PageBlueprint(
            "order-blotter",
            "Order Blotter",
            "/blotter",
            "order-blotter",
            "src/pages/OrderBlotterPage.tsx",
            "Full working/partial/filled blotter with filters and desk ownership.",
            "AAPL BUY 25k Working; MSFT SELL 12k Partial.",
            "ops-blotter-desk",
            "ops",
        ),
        PageBlueprint(
            "positions",
            "Positions & P&L",
            "/positions",
            "positions",
            "src/pages/PositionsPage.tsx",
            "Book positions, day/MTD P&L, and sleeve attribution.",
            "AAPL +420k day; tech sleeve 28% NAV.",
        ),
        PageBlueprint(
            "risk-limits",
            "Risk Limits",
            "/risk",
            "risk",
            "src/pages/RiskLimitsPage.tsx",
            "Gross/net limits, sector caps, and breach queue for the fund book.",
            "Gross 62/75%; tech 28% soft breach.",
        ),
    )


def _accounting_pages() -> tuple[PageBlueprint, ...]:
    return (
        PageBlueprint(
            "books-dashboard",
            "Books overview",
            "/",
            "accounting-dashboard",
            "src/pages/BooksDashboardPage.tsx",
            "Daily accounting home — cash pulse, AR queue, expenses, unmatched bank.",
            "Cash 48,220; 26 open invoices; 12 unmatched bank.",
            "ops-ledger-home",
            "ops",
        ),
        PageBlueprint(
            "invoices",
            "Invoices",
            "/invoices",
            "invoices",
            "src/pages/InvoicesPage.tsx",
            "AR invoice pipeline — draft/sent/overdue/paid board.",
            "INV-1042 Northwind 2480 Sent; INV-1041 Overdue.",
            "ops-invoice-board",
            "ops",
        ),
        PageBlueprint(
            "expenses",
            "Expenses",
            "/expenses",
            "expenses",
            "src/pages/ExpensesPage.tsx",
            "Expense triage queue — review, categorize, flag missing receipts.",
            "Adobe 54.99; Uber 38.20 Travel.",
            "ops-expense-queue",
            "ops",
        ),
        PageBlueprint(
            "reconciliation",
            "Bank reconciliation",
            "/reconciliation",
            "bank-reconciliation",
            "src/pages/BankReconciliationPage.tsx",
            "Match bank feed lines to invoices and expenses in a split pane.",
            "Chase *4491 — 12 unmatched.",
            "ops-recon-split",
            "ops",
        ),
        PageBlueprint(
            "reports",
            "Reports",
            "/reports",
            "reports",
            "src/pages/ReportsPage.tsx",
            "P&L, balance sheet, and cash flow summary for the period.",
            "MTD revenue 62k; net 18.4k.",
        ),
        PageBlueprint(
            "customers",
            "Customers",
            "/customers",
            "customers",
            "src/pages/CustomersPage.tsx",
            "Customer list with open balance and last invoice.",
            "Northwind open 2480; Bright Labs overdue 890.",
        ),
    )


def _generic_saas_pages() -> tuple[PageBlueprint, ...]:
    return (
        PageBlueprint(
            "workspace-home",
            "Workspace",
            "/",
            "saas-dashboard",
            "src/pages/WorkspaceHomePage.tsx",
            "Primary product workspace — KPIs, work queue, and exceptions.",
            "Open items, throughput, and blockers for today.",
            "ops-dashboard",
            "ops",
        ),
        PageBlueprint(
            "work-queue",
            "Work queue",
            "/queue",
            "work-queue",
            "src/pages/WorkQueuePage.tsx",
            "Operational list of items that need action.",
            "8+ rows with status chips and owners.",
        ),
        PageBlueprint(
            "records",
            "Records",
            "/records",
            "records",
            "src/pages/RecordsPage.tsx",
            "Searchable records table for the core entity.",
            "Dense table with filters and statuses.",
        ),
        PageBlueprint(
            "reports",
            "Reports",
            "/reports",
            "reports",
            "src/pages/ReportsPage.tsx",
            "Period reports and trend charts for the product.",
            "Weekly performance chart and KPI strip.",
        ),
        PageBlueprint(
            "settings",
            "Settings",
            "/settings",
            "settings",
            "src/pages/SettingsPage.tsx",
            "Workspace settings and preferences.",
            "Profile, notifications, integrations stubs.",
            "ops-settings",
            "ops",
        ),
    )


def _storefront_pages() -> tuple[PageBlueprint, ...]:
    return (
        PageBlueprint(
            "home",
            "Home",
            "/",
            "public-home",
            "src/pages/HomePage.tsx",
            "Brand storefront home for browsing and conversion.",
            "Hero, featured items, CTA.",
            "public-home",
            "public",
        ),
        PageBlueprint(
            "gallery",
            "Gallery",
            "/gallery",
            "public-catalog",
            "src/pages/GalleryPage.tsx",
            "Catalogue grid of products or artworks.",
            "Product showcase mosaic linking to detail.",
            "public-catalog",
            "public",
        ),
        PageBlueprint(
            "gallery_detail",
            "Artwork",
            "/gallery/:id",
            "public-detail",
            "src/pages/ArtworkDetailPage.tsx",
            "Single item / artwork detail with inquire CTA.",
            "Hero, credentials, inquire.",
            "public-detail",
            "public",
        ),
    )


def _booking_pages() -> tuple[PageBlueprint, ...]:
    return (
        PageBlueprint(
            "home",
            "Home",
            "/",
            "public-home",
            "src/pages/HomePage.tsx",
            "Service home that leads into booking.",
            "Hero, services, book CTA.",
            "public-home",
            "public",
        ),
        PageBlueprint(
            "services",
            "Services",
            "/services",
            "public-service",
            "src/pages/ServicesPage.tsx",
            "Browsable services / sessions list.",
            "Schedule rail or service cards.",
            "public-service",
            "public",
        ),
        PageBlueprint(
            "book",
            "Book",
            "/book",
            "public-booking",
            "src/pages/BookPage.tsx",
            "Booking flow for appointments or classes.",
            "Slot picker and confirmation path.",
            "public-booking",
            "public",
        ),
    )


def resolve_product_kind_contract(*parts: str) -> ProductKindContract:
    kind = classify_product_kind(*parts)
    text = _blob(*parts)

    if kind == "internal_ops":
        if _hits(text, ("hedge", "trading", "blotter", "oms", "trader", "execution")) >= 1:
            pages = _trading_pages()
            subtype = "trading"
            note = "Internal trading desk — OpsShell blotter/P&L/risk, never marketing SaaS."
        else:
            pages = _generic_saas_pages()
            subtype = "ops"
            note = "Internal ops console — dense OpsShell workspace, never a public landing."
        recipe = "dense-ops-floor" if subtype == "trading" else "dense-ops"
        home_sk = pages[0].skeleton_id if pages else "ops-dashboard"
        return ProductKindContract(
            kind="internal_ops",
            recipe_id=recipe,
            home_surface="ops",
            home_skeleton_id=home_sk,
            pages=pages,
            template_surface="ops",
            design_note=note,
            subtype=subtype,
        )

    if kind == "saas_workspace":
        if _hits(
            text,
            (
                "accounting",
                "bookkeep",
                "invoice",
                "ledger",
                "expense",
                "reconcil",
                "quickbooks",
                "xero",
            ),
        ) >= 1:
            pages = _accounting_pages()
            subtype = "accounting"
            recipe = "dense-ops-ledger"
            note = (
                "SaaS accounting PRODUCT workspace — cash pulse, invoice board, bank recon; "
                "never a foresight marketing landing."
            )
        else:
            pages = _generic_saas_pages()
            subtype = "generic"
            recipe = "dense-ops"
            note = (
                "SaaS product workspace — OpsShell queues and records; "
                "never a Get Started marketing homepage."
            )
        home_sk = pages[0].skeleton_id if pages else "ops-dashboard"
        return ProductKindContract(
            kind="saas_workspace",
            recipe_id=recipe,
            home_surface="ops",
            home_skeleton_id=home_sk,
            pages=pages,
            template_surface="ops",
            design_note=note,
            subtype=subtype,
        )

    if kind == "booking_service":
        return ProductKindContract(
            kind="booking_service",
            recipe_id="warm-service",
            home_surface="public",
            home_skeleton_id="public-home",
            pages=_booking_pages(),
            template_surface="public",
            design_note="Booking service — public home plus bookable services.",
            subtype="booking",
        )

    return ProductKindContract(
        kind="storefront",
        recipe_id="warm-service",
        home_surface="public",
        home_skeleton_id="public-home",
        pages=_storefront_pages(),
        template_surface="public",
        design_note="Storefront — public marketing home is the product surface.",
        subtype="storefront",
    )


def _page_plan_dict(bp: PageBlueprint) -> dict[str, Any]:
    return {
        "id": bp.id,
        "title": bp.title,
        "page_type": bp.page_type,
        "surface": bp.surface,
        "skeleton_id": bp.skeleton_id,
        "section_slots": bp.section_slots(),
        "purpose": bp.purpose,
        "sections": [
            {
                "name": "Workspace",
                "description": bp.purpose,
                "priority": "required",
            }
        ],
        "features_to_showcase": [bp.title],
        "layout_notes": (
            "OpsShell product chrome — never a public marketing hero."
            if bp.surface == "ops"
            else "PublicShell brand storefront."
        ),
        "sample_data_notes": bp.sample_data_notes,
    }


def _is_ai_hub_route(route: dict[str, Any]) -> bool:
    path = str(route.get("path") or "").rstrip("/").lower()
    page_id = str(
        route.get("page_id") or route.get("app_spec_page_id") or route.get("id") or ""
    ).casefold()
    component = str(route.get("component_file") or "").replace("\\", "/").lower()
    page_type = str(route.get("page_type") or "").casefold()
    return (
        path == "/ai-features"
        or page_id == "page-ai-features"
        or component.endswith("aifeaturespage.tsx")
        or page_type == "ai_hub"
    )


def _page_path_hint(page: Mapping[str, Any]) -> str:
    contract_block = page.get("app_spec_contract")
    if isinstance(contract_block, dict):
        route = str(contract_block.get("route") or "").strip()
        if route:
            return route
    for key in ("path", "route", "href"):
        value = str(page.get(key) or "").strip()
        if value.startswith("/"):
            return value
    return ""


def _is_marketing_landing(page: Mapping[str, Any]) -> bool:
    skeleton = str(page.get("skeleton_id") or "")
    surface = str(page.get("surface") or "")
    title = str(page.get("title") or "")
    path = _page_path_hint(page)
    if skeleton in {"public-home", "public-service"} and path in {"", "/", "/home"}:
        return True
    if surface == "public" and path in {"", "/", "/home"}:
        return bool(
            re.search(
                r"home|landing|marketing|foresight|forecast|get started",
                f"{title} {skeleton}",
                re.I,
            )
        )
    return bool(
        re.search(r"foresight|forecast|explore forecasts", title, re.I)
        and (path in {"", "/", "/home"} or not path)
    )


def _inventory_is_substantive(pages: list[Any]) -> bool:
    """True when the LLM already proposed a usable multi-page product face."""
    real = [p for p in pages if isinstance(p, dict) and (p.get("title") or p.get("id"))]
    if len(real) < 2:
        return False
    titles = {
        str(p.get("title") or p.get("id") or "").casefold()
        for p in real
        if str(p.get("title") or p.get("id") or "").strip()
    }
    paths = {_page_path_hint(p) for p in real if _page_path_hint(p)}
    return len(titles) >= 2 or len(paths) >= 2


def _routes_are_substantive(routes: list[Any]) -> bool:
    real = [
        rt
        for rt in routes
        if isinstance(rt, dict)
        and str(rt.get("path") or "").strip()
        and not _is_ai_hub_route(rt)
    ]
    paths = {str(rt.get("path") or "").rstrip("/") for rt in real}
    return len(paths) >= 2


def _repair_ops_home_chrome(page: dict[str, Any], contract: ProductKindContract) -> bool:
    """For ops kinds, rewrite only a marketing `/` landing into product chrome."""
    if contract.kind not in OPS_KINDS or not contract.pages:
        return False
    if not _is_marketing_landing(page):
        return False
    page.update(_page_plan_dict(contract.pages[0]))
    return True


def _sync_role_nav(role: dict[str, Any], pages: list[dict[str, Any]], contract: ProductKindContract) -> bool:
    nav = dict(role.get("navigation") or {})
    bad_labels = (
        "get started",
        "explore forecasts",
        "access dashboard",
        "sign up",
    )
    links = [
        link
        for link in (nav.get("links") or [])
        if isinstance(link, dict)
        and not any(bad in str(link.get("label") or "").lower() for bad in bad_labels)
    ]
    touched = False
    for page in pages:
        pid = page.get("id")
        if not pid or any(link.get("page_id") == pid for link in links):
            continue
        links.append(
            {
                "label": str(page.get("title") or pid),
                "page_id": pid,
                "style": "cta" if page is pages[0] else "link",
            }
        )
        touched = True
    if links:
        nav["links"] = links
        if contract.kind in OPS_KINDS or any(
            str(p.get("surface") or "") == "ops" for p in pages
        ):
            nav.setdefault("type", "sidebar")
        role["navigation"] = nav
    return touched


def _ensure_role_pages(role: dict[str, Any], contract: ProductKindContract) -> bool:
    """Merge kind defaults under LLM inventory — never replace a rich brief-driven plan."""
    pages = [p for p in (role.get("pages") or []) if isinstance(p, dict)]
    touched = False
    substantive = _inventory_is_substantive(pages)

    if not pages:
        role["pages"] = [_page_plan_dict(bp) for bp in contract.pages]
        _sync_role_nav(role, role["pages"], contract)
        return True

    # Chrome repair only: ops kinds cannot keep a foresight marketing home.
    if contract.kind in OPS_KINDS:
        for page in pages:
            if _repair_ops_home_chrome(page, contract):
                touched = True

    if substantive:
        # LLM owns inventory. Fill missing chrome fields only — do not append
        # the full industry blueprint or overwrite skeleton/slots.
        for page in pages:
            if not isinstance(page, dict):
                continue
            if contract.kind in OPS_KINDS and str(page.get("surface") or "") == "ops":
                page.setdefault("skeleton_id", "ops-list")
                page.setdefault("section_slots", list(_OPS_LIST_SLOTS))
            elif contract.kind in PUBLIC_KINDS:
                page.setdefault("surface", "public")
                page.setdefault("skeleton_id", "public-home")
        if _sync_role_nav(role, pages, contract):
            touched = True
        role["pages"] = pages
        return touched

    # Thin / broken plan → seed missing blueprint pages as fallback.
    by_id = {str(p.get("id") or ""): p for p in pages}
    by_title = {str(p.get("title") or "").casefold(): p for p in pages}
    for bp in contract.pages:
        existing = by_id.get(bp.id) or by_title.get(bp.title.casefold())
        if existing is None:
            pages.append(_page_plan_dict(bp))
            touched = True
            continue
        if contract.kind in OPS_KINDS and (
            str(existing.get("surface") or "") == "public"
            or str(existing.get("skeleton_id") or "").startswith("public")
        ):
            existing.update(_page_plan_dict(bp))
            touched = True
        else:
            existing.setdefault("surface", bp.surface)
            existing.setdefault("skeleton_id", bp.skeleton_id)
            existing.setdefault("section_slots", bp.section_slots())

    if contract.kind in OPS_KINDS:
        home = next(
            (
                p
                for p in pages
                if isinstance(p, dict)
                and (
                    str(p.get("skeleton_id") or "") in _OPS_HOME_SKELETONS
                    or p.get("id") == contract.pages[0].id
                )
            ),
            None,
        )
        if home is not None and pages and pages[0] is not home:
            pages = [home] + [p for p in pages if p is not home]
            touched = True

    role["pages"] = pages
    if _sync_role_nav(role, pages, contract):
        touched = True
    return touched


def apply_product_kind_to_plan(
    plan: dict[str, Any] | None,
    contract: ProductKindContract,
) -> dict[str, Any]:
    """Stamp kind chrome/recipe; keep LLM page inventory unless the plan is empty/thin."""
    updated = copy.deepcopy(dict(plan or {}))
    updated["product_kind"] = contract.kind
    updated["product_kind_subtype"] = contract.subtype
    updated["product_kind_contract"] = contract.as_dict()
    # Recipe is a default — do not clobber an explicit plan/recipe choice.
    updated.setdefault("recipe_id", contract.recipe_id)
    if not updated.get("recipe_id"):
        updated["recipe_id"] = contract.recipe_id

    roles = list(updated.get("roles") or [])
    if not roles:
        roles = [{"id": "ROLE-PRIMARY-USER", "label": "Primary user", "pages": []}]

    for role in roles:
        if not isinstance(role, dict):
            continue
        _ensure_role_pages(role, contract)

    direction = str(updated.get("design_direction") or "").strip()
    kind_marker = f"PRODUCT_KIND={contract.kind}/{contract.subtype}"
    if kind_marker in direction:
        # Forcer re-application (plan_phase) lands here 2-3x per run; a kind
        # flip must still append its own note, so key on the full marker.
        updated["design_direction"] = direction
    else:
        updated["design_direction"] = (
            f"{direction} | {kind_marker} (chrome default; "
            f"LLM owns roles/pages from the brief): {contract.design_note}"
        ).strip(" |")
    if contract.kind in OPS_KINDS:
        updated.setdefault("ops_direction", contract.design_note)
        updated.setdefault(
            "public_direction",
            "Prefer the product workspace. Only add public pages if the brief needs them.",
        )
    updated["roles"] = roles
    return updated


def _detail_parent_path(path: str) -> str:
    """`/gallery/:id` -> `/gallery`. Empty when the path is not a detail child."""
    head, sep, tail = str(path or "").rpartition("/")
    if not sep or not tail.startswith(":"):
        return ""
    return head or "/"


def _plan_pages_index(
    plan: Mapping[str, Any] | None,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Plan pages keyed the way `_normalize_architect` keys them.

    A route's page contract is inferred from the plan page merged under the route
    (`architect_normalize.py:519-523`), and the plan page is where the prose that
    decides it lives — request 98's `/rooms` resolves to `public-catalog` with the
    plan merged and to `public-service` without it. The gap-fill asks the same
    question twelve lines earlier, so it has to ask it of the same document.
    """
    by_role_page: dict[tuple[str, str], dict[str, Any]] = {}
    counts: dict[str, int] = {}
    for role in (plan or {}).get("roles") or []:
        if not isinstance(role, dict):
            continue
        role_id = str(role.get("id") or "")
        for page in role.get("pages") or []:
            if not isinstance(page, dict) or not page.get("id"):
                continue
            page_id = str(page["id"])
            by_role_page[(role_id, page_id)] = page
            counts[page_id] = counts.get(page_id, 0) + 1
            by_role_page.setdefault(("", page_id), page)
    # The normalizer only falls back to a page id when it names exactly one page.
    for page_id, count in counts.items():
        if count > 1:
            by_role_page.pop(("", page_id), None)
    return by_role_page


def _route_page_kind(
    route: Mapping[str, Any],
    plan_pages: Mapping[tuple[str, str], dict[str, Any]],
) -> str:
    """The skeleton this route will resolve to, as the normalizer resolves it.

    Skeleton ids are surface-prefixed (`public-catalog`, `ops-list`) and
    `_infer_skeleton_id` only emits a surface's own, so the skeleton alone
    already carries the surface and there is nothing to compare it against.
    """
    from app.application.ui_catalogue import infer_page_contract

    role_id = str(route.get("role_id") or "")
    page_id = str(route.get("page_id") or "")
    page = plan_pages.get((role_id, page_id)) or plan_pages.get(("", page_id))
    source = {**(page or {}), **route}
    try:
        return str(infer_page_contract(source).get("skeleton_id") or "")
    except Exception:
        return ""


def _served_page_kinds(
    routes: list[dict[str, Any]],
    plan_pages: Mapping[tuple[str, str], dict[str, Any]],
) -> set[str]:
    served: set[str] = set()
    for route in routes:
        if not isinstance(route, dict) or _is_ai_hub_route(route):
            continue
        skeleton = _route_page_kind(route, plan_pages)
        if skeleton:
            served.add(skeleton)
    return served


def _inject_blueprint_routes(
    routes: list[dict[str, Any]],
    files: list[dict[str, Any]],
    contract: ProductKindContract,
    role_id: str,
    *,
    only_when_unserved: bool = False,
    plan: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Add missing blueprint routes.

    When the architect inventory is thin the blueprint *is* the app and every page
    is added. When it is already substantive this is a gap-fill, and
    ``only_when_unserved`` holds it to what a gap-fill may honestly do: add a page
    only when nothing in the app already serves it. Two routes serve the same
    purpose when they land on the same path or resolve to the same page contract —
    so a restaurant that declares `/menu` is not missing a catalogue, and the
    `/gallery` + `/gallery/:id -> ArtworkDetailPage.tsx` literals stop reaching it.

    `/` is exempt from the contract test and keyed on its path alone: the router's
    catch-all is `<Route path="*" element={<Navigate to="/" replace />} />`
    (`assemble.py:1123`), so an app with no route at `/` redirects to nothing.
    """
    existing_paths = {str(rt.get("path") or "") for rt in routes}
    existing_files = {str(f.get("path") or "").replace("\\", "/") for f in files}
    plan_pages = _plan_pages_index(plan) if only_when_unserved else {}
    served_kinds: set[str] = (
        _served_page_kinds(routes, plan_pages) if only_when_unserved else set()
    )
    touched = False
    for bp in contract.pages:
        path = bp.path
        component = bp.component_file
        if only_when_unserved and path not in existing_paths:
            parent = _detail_parent_path(path)
            if parent:
                # A detail page is not free-standing: it is reached from one
                # listing, so its equivalent is that listing's own detail child
                # and never an unrelated detail page elsewhere in the app.
                if parent not in existing_paths or any(
                    _detail_parent_path(other) == parent for other in existing_paths
                ):
                    continue
            elif path != "/" and bp.skeleton_id in served_kinds:
                continue
        if path in existing_paths:
            for rt in routes:
                if str(rt.get("path") or "") != path or _is_ai_hub_route(rt):
                    continue
                rt.setdefault("surface", bp.surface)
                rt.setdefault("layout", "admin" if bp.surface == "ops" else "public")
                rt.setdefault("skeleton_id", bp.skeleton_id)
                rt.setdefault("section_slots", bp.section_slots())
                rt.setdefault("title", bp.title)
                rt.setdefault("page_type", bp.page_type)
                rt.setdefault("component_file", component)
                rt.setdefault("role_id", role_id)
            continue
        routes.append(
            {
                "path": path,
                "page_id": bp.id,
                "role_id": role_id,
                "title": bp.title,
                "component_file": component,
                "layout": "admin" if bp.surface == "ops" else "public",
                "surface": bp.surface,
                "skeleton_id": bp.skeleton_id,
                "section_slots": bp.section_slots(),
                "page_type": bp.page_type,
                "purpose": bp.purpose,
            }
        )
        touched = True
        # A page added here is served from here on: `/gallery/:id` is only
        # reachable because `/gallery` was just added one iteration earlier.
        # (There is deliberately no `served_kinds.add` beside this: no contract
        # declares two blueprint pages of the same kind, so it could not change
        # an outcome, and a guard that cannot fail is decoration.)
        existing_paths.add(path)
        if component not in existing_files:
            files.append(
                {
                    "type": "page",
                    "kind": "page",
                    "path": component,
                    "instructions": (
                        f"PRODUCT_KIND={contract.kind} fallback page. "
                        f"{bp.purpose} Real product UI — never a marketing-only hero. "
                        f"Sample: {bp.sample_data_notes}"
                    ),
                }
            )
            existing_files.add(component)
    return routes, files, touched


def apply_product_kind_to_architect(
    architect: dict[str, Any] | None,
    contract: ProductKindContract,
    plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Stamp kind metadata; preserve LLM routes; seed blueprint only when thin.

    `plan` is the page inventory the architect was built from. It is optional and
    only sharpens the gap-fill's "does the app already serve this page" test —
    without it the test reads the route alone, which resolves fewer routes to a
    catalogue than the normalizer will.
    """
    updated = copy.deepcopy(dict(architect or {}))
    updated["product_kind"] = contract.kind
    updated["product_kind_subtype"] = contract.subtype
    updated.setdefault("recipe_id", contract.recipe_id)
    if not updated.get("recipe_id"):
        updated["recipe_id"] = contract.recipe_id

    routes = [rt for rt in (updated.get("routes") or []) if isinstance(rt, dict)]
    files = [f for f in (updated.get("files_to_generate") or []) if isinstance(f, dict)]
    role_id = "ROLE-PRIMARY-USER"
    for role in updated.get("roles") or []:
        if isinstance(role, dict) and role.get("id"):
            role_id = str(role["id"])
            break
    for rt in routes:
        if rt.get("role_id"):
            role_id = str(rt["role_id"])
            break

    substantive = _routes_are_substantive(routes)

    # Chrome repair for ops kinds — do not flatten hybrid public+ops inventories.
    if contract.kind in OPS_KINDS and contract.pages:
        home = contract.pages[0]
        for route in routes:
            if _is_ai_hub_route(route):
                continue
            path = str(route.get("path") or "").rstrip("/") or "/"
            skeleton = str(route.get("skeleton_id") or "")
            surface = str(route.get("surface") or "")
            title = str(route.get("title") or "")
            marketing_home = path in {"/", "/home"} and (
                surface == "public"
                or skeleton.startswith("public")
                or bool(re.search(r"foresight|forecast|landing|marketing|get started", title, re.I))
            )
            if marketing_home:
                route["surface"] = home.surface
                route["layout"] = "admin" if home.surface == "ops" else "public"
                route["skeleton_id"] = home.skeleton_id
                route["section_slots"] = home.section_slots()
                route["title"] = home.title
                continue
            # Fill missing chrome only; keep LLM surface/layout choices.
            if surface == "ops" or route.get("layout") == "admin":
                route.setdefault("surface", "ops")
                route.setdefault("layout", "admin")
                route.setdefault("skeleton_id", "ops-list")
                route.setdefault("section_slots", list(_OPS_LIST_SLOTS))

    if not substantive:
        routes, files, _ = _inject_blueprint_routes(routes, files, contract, role_id)
    elif contract.kind in PUBLIC_KINDS:
        # Public kinds: gap-fill only a blueprint page nothing already serves.
        routes, files, _ = _inject_blueprint_routes(
            routes,
            files,
            contract,
            role_id,
            only_when_unserved=True,
            plan=plan,
        )

    for item in files:
        path = str(item.get("path") or "").replace("\\", "/").lower()
        if "aifeaturespage" in path:
            continue
        kind = str(item.get("kind") or item.get("type") or "").lower()
        if kind not in {"page", ""} and "page" not in path:
            continue
        instructions = str(item.get("instructions") or "")
        prefix = (
            f"PRODUCT_KIND={contract.kind}/{contract.subtype} chrome default. "
            "Follow the brief for roles/screens. Never replace a brief-driven admin or "
            "booking flow with a single marketing hero. "
        )
        if "PRODUCT_KIND=" not in instructions:
            item["instructions"] = (prefix + instructions).strip()

    updated["routes"] = routes
    updated["files_to_generate"] = files
    direction = str(updated.get("design_direction") or "").strip()
    kind_marker = f"PRODUCT_KIND={contract.kind}/{contract.subtype}"
    if kind_marker in direction:
        # Same guard as apply_product_kind_to_plan: dedupe same-kind
        # re-application, never a flipped kind's note.
        updated["design_direction"] = direction
    else:
        updated["design_direction"] = (
            f"{direction} | {kind_marker}: "
            f"LLM-first inventory; {contract.design_note}"
        ).strip(" |")
    return updated


def lock_chrome_on_experience_seed(
    seed: dict[str, Any] | None,
    contract: ProductKindContract,
) -> dict[str, Any]:
    """Stamp locked skeleton/surface onto AppSpec-projected experience seed pages."""
    updated = copy.deepcopy(dict(seed or {}))
    updated["product_kind"] = contract.kind
    updated["product_kind_subtype"] = contract.subtype
    if contract.kind not in OPS_KINDS:
        return updated

    by_path = {bp.path: bp for bp in contract.pages}
    home_bp = contract.pages[0]
    for role in updated.get("roles") or []:
        if not isinstance(role, dict):
            continue
        for page in role.get("pages") or []:
            if not isinstance(page, dict):
                continue
            # Match by path from app_spec_contract if present
            route = ""
            contract_block = page.get("app_spec_contract")
            if isinstance(contract_block, dict):
                route = str(contract_block.get("route") or "")
            surface = str(page.get("surface") or "")
            bp = by_path.get(route)
            if bp is None and (
                page.get("primary")
                or surface == "public"
                or not page.get("skeleton_id")
            ):
                # Primary / unlocked pages get home chrome
                if surface != "ops" or not page.get("skeleton_id"):
                    bp = home_bp
            if bp is None:
                if surface == "ops" or contract.kind in OPS_KINDS:
                    page["surface"] = "ops"
                    page.setdefault("skeleton_id", "ops-list")
                    page.setdefault("section_slots", list(_OPS_LIST_SLOTS))
                continue
            page["surface"] = bp.surface
            page["skeleton_id"] = bp.skeleton_id
            page["section_slots"] = bp.section_slots()
            page["page_type"] = bp.page_type
    return updated


def lock_chrome_on_architecture_seed(
    seed: dict[str, Any] | None,
    contract: ProductKindContract,
) -> dict[str, Any]:
    updated = copy.deepcopy(dict(seed or {}))
    updated["product_kind"] = contract.kind
    if contract.kind not in OPS_KINDS:
        return updated
    for route in updated.get("routes") or []:
        if not isinstance(route, dict) or _is_ai_hub_route(route):
            continue
        path = str(route.get("path") or "")
        bp = next((p for p in contract.pages if p.path == path), None)
        if bp is None and path in {"/", "/home"}:
            bp = contract.pages[0]
        if bp is None:
            route["surface"] = "ops"
            route["layout"] = "admin"
            route.setdefault("skeleton_id", "ops-list")
            route.setdefault("section_slots", list(_OPS_LIST_SLOTS))
            continue
        route["surface"] = bp.surface
        route["layout"] = "admin" if bp.surface == "ops" else "public"
        route["skeleton_id"] = bp.skeleton_id
        route["section_slots"] = bp.section_slots()
        route["title"] = route.get("title") or bp.title
    return updated


def validate_product_kind_chrome(
    architect: Mapping[str, Any] | None,
    *,
    product_kind: str | None = None,
) -> list[str]:
    """Return issue codes when ops/saas kinds still have marketing chrome at `/`."""
    architect = dict(architect or {})
    kind = product_kind or str(architect.get("product_kind") or "")
    if kind not in OPS_KINDS:
        return []
    issues: list[str] = []
    routes = [rt for rt in (architect.get("routes") or []) if isinstance(rt, dict)]
    home = next(
        (rt for rt in routes if str(rt.get("path") or "") in {"/", "/home"}),
        None,
    )
    if home is None:
        issues.append("ops_kind_missing_home")
        return issues
    skeleton = str(home.get("skeleton_id") or "")
    surface = str(home.get("surface") or "")
    if surface == "public" or skeleton.startswith("public"):
        issues.append("ops_kind_public_home")
    if skeleton == "public-home":
        issues.append("ops_kind_marketing_skeleton")
    ops_routes = [
        rt
        for rt in routes
        if str(rt.get("surface") or "") == "ops"
        or str(rt.get("layout") or "") == "admin"
        or str(rt.get("skeleton_id") or "").startswith("ops")
    ]
    # Exclude AI hub from count
    ops_routes = [rt for rt in ops_routes if not _is_ai_hub_route(rt)]
    if len(ops_routes) < 4:
        issues.append("ops_kind_too_few_pages")
    return issues


def context_from_request(req: Any, extra: str = "") -> str:
    parts = [
        getattr(req, "industry", None),
        getattr(req, "business_name", None),
        getattr(req, "business_description", None),
        getattr(req, "description", None),
        getattr(req, "main_problem", None),
        getattr(req, "desired_outcome", None),
        getattr(req, "target_customers", None),
        getattr(req, "what_you_like", None),
        extra,
    ]
    return _blob(*[str(p) for p in parts if p])


__all__ = [
    "OPS_KINDS",
    "PUBLIC_KINDS",
    "ProductKind",
    "ProductKindContract",
    "PageBlueprint",
    "apply_product_kind_to_architect",
    "apply_product_kind_to_plan",
    "classify_product_kind",
    "context_from_request",
    "lock_chrome_on_architecture_seed",
    "lock_chrome_on_experience_seed",
    "resolve_product_kind_contract",
    "scrub_negated_product_clauses",
    "validate_product_kind_chrome",
]
