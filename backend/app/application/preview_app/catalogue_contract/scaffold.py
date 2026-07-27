"""Minimal catalogue page scaffolds."""
from __future__ import annotations

import json
import re

from app.application.preview_app.catalogue_contract.slots import (
    assigned_non_shell_slots,
    expected_shell,
)
from app.application.preview_app.protected_paths import canonical_workspace_path

_SLOT_COMPONENT = {
    "hero": "MarketingHero",
    "features": "FeatureBento",
    "showcase": "ProductShowcase",
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


def _is_trading_domain(*parts: str) -> bool:
    blob = " ".join(str(p or "") for p in parts).lower()
    if any(hint in blob for hint in _ACCOUNTING_HINTS):
        return False
    return any(hint in blob for hint in _TRADING_HINTS)


def _is_accounting_domain(*parts: str) -> bool:
    blob = " ".join(str(p or "") for p in parts).lower()
    return sum(1 for hint in _ACCOUNTING_HINTS if hint in blob) >= 1


def _non_home_hero_ctas(skeleton_id: str, brand: str, title: str) -> tuple[str, str]:
    """Return (primaryCta jsx attrs fragment without wrappers, subcopy).

    Storefront catalog/detail must not invent /book-appointment.
    Booking faces keep a real /book target that matches product_kind routes.
    """
    sk = (skeleton_id or "").lower()
    blob = f"{brand} {title} {sk}".lower()
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
        sub = json.dumps(
            f"{title} — browse what’s here. This page is not the homepage story.",
            ensure_ascii=False,
        )
        if sk == "public-detail" or "detail" in sk:
            primary = '{ label: "Inquire about this piece", href: "/about" }'
        else:
            primary = '{ label: "View collection", href: "/gallery" }'
        secondary = '{ label: "Back home", href: "/" }'
        return (
            f"primaryCta={{{primary}}} secondaryCta={{{secondary}}}",
            sub,
        )

    sub = json.dumps(
        f"{title} — browse what’s here, then book. This page is not the homepage story.",
        ensure_ascii=False,
    )
    primary = '{ label: "Book a visit", href: "/book" }'
    secondary = '{ label: "Back home", href: "/" }'
    return (
        f"primaryCta={{{primary}}} secondaryCta={{{secondary}}}",
        sub,
    )


def _safe_slot_jsx(
    slot: str,
    brand: str,
    title: str,
    *,
    skeleton_id: str = "",
) -> str:
    brand_js = json.dumps(brand)
    title_js = json.dumps(title)
    accounting = _is_accounting_domain(brand, title)
    trading = _is_trading_domain(brand, title) and not accounting
    # Non-home pages must NOT reuse seed.hero — that makes /doctors look like /.
    home_hero = skeleton_id in {"", "public-home"}

    def _d(accounting_v: str, trading_v: str, default_v: str) -> str:
        if accounting:
            return accounting_v
        if trading:
            return trading_v
        return default_v

    # Brand-bound fallbacks for public-home (and shared mid-slots) — never agency mush.
    def _fb(text: str) -> str:
        return json.dumps(text, ensure_ascii=False)

    features_heading_fb = _fb(f"What {brand} offers")
    showcase_heading_fb = _fb(f"From {brand}")
    products_heading_fb = _fb(f"{brand} picks")
    process_heading_fb = _fb(f"How {brand} works")
    testimonials_heading_fb = _fb(f"Guests of {brand}")
    credentials_heading_fb = _fb(f"Why {brand}")
    cta_heading_fb = _fb(f"Ready for {brand}?")
    cta_desc_fb = _fb(f"Tell {brand} what you need — clear options, real next steps.")
    footer_desc_fb = _fb(f"{brand} — clear choices and real bookings.")
    spotlight_title_fb = _fb(f"{brand} in focus")
    spotlight_desc_fb = _fb(f"A closer look at what makes {brand} distinct.")
    results_heading_fb = _fb(f"{brand} results")
    results_label_fb = _fb(f"{brand} highlight")

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
        cta_attrs, sub_js = _non_home_hero_ctas(skeleton_id, brand, title)
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
            'items={seed.features ?? []} />'
        ),
        "products": (
            f'<ProductShowcase heading={{seed.showcaseHeading ?? {products_heading_fb}}} '
            'items={(seed.items ?? []).map((item, index) => ({ '
            'title: item.title, description: item.description, '
            'imageSrc: [images.card1, images.card2, images.card3][index % 3], imageAlt: item.title, '
            'href: `/gallery/${encodeURIComponent(String((item as any).id || (item as any).slug || index + 1))}` '
            '}))} />'
        ),
        "showcase": (
            f'<ProductShowcase heading={{seed.showcaseHeading ?? {showcase_heading_fb}}} '
            'items={(seed.items ?? []).map((item, index) => ({ '
            'title: item.title, description: item.description, '
            'imageSrc: [images.card1, images.card2, images.card3][index % 3], imageAlt: item.title, '
            'href: `/gallery/${encodeURIComponent(String((item as any).id || (item as any).slug || index + 1))}` '
            '}))} />'
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
            'primaryCta={{ label: seed.cta?.primaryLabel ?? "Get started", href: seed.cta?.primaryHref ?? "#details" }} '
            'secondaryCta={{ label: seed.cta?.secondaryLabel ?? "Talk to us", href: seed.cta?.secondaryHref ?? "#contact" }} />'
        ),
        "footer": (
            f'<BrandFooter brandName={{{brand_js}}} '
            f'description={{seed.footer?.description ?? {footer_desc_fb}}} />'
        ),
        "trust": (
            '<LogoMarquee size="display" '
            'items={(seed.trustLabels ?? []).map((label) => ({ label }))} />'
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
                ' actions={[{ label: "AI features", href: "/ai-features", variant: "secondary" }, '
                '{ label: "New invoice", href: "/invoices" }]}',
                ' actions={[{ label: "AI features", href: "/ai-features", variant: "secondary" }, '
                '{ label: "New ticket", href: "/ticket" }]}',
                ' actions={[{ label: "AI features", href: "/ai-features", variant: "secondary" }, '
                '{ label: "Check in", href: "#queue" }]}',
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
        "filters": (
            '<FilterBar searchPlaceholder="'
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
            + ']).map((row) => ({ name: row.name, status: row.status, owner: row.owner || row.updated || "—" }))} />'
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
) -> str:
    brand_js = json.dumps(brand)
    title_js = json.dumps(title)
    base = (listing_path or "/classes").rstrip("/") or "/classes"
    base_js = json.dumps(base)
    appspec_attrs = f" data-appspec-page={json.dumps(page_id)}" if page_id else ""
    span_lines: list[str] = []
    for action_id in action_ids:
        span_lines.append(
            f'        <span className="sr-only" data-appspec-action={json.dumps(action_id)}>'
            f"{action_id}</span>"
        )
    for evidence_id in evidence_ids:
        span_lines.append(
            f'        <span className="sr-only" data-appspec-evidence={json.dumps(evidence_id)}>'
            f"{evidence_id}</span>"
        )
    appspec_hook_spans = ("\n" + "\n".join(span_lines) + "\n") if span_lines else "\n"
    return f"""// schedule listing scaffold — distinct from home marketing clone
import {{ usePublicNavItems, publicCta }} from '@/lib/app-nav';
import {{ BRAND_MANIFEST, images }} from '@/data/mock';
import {{ PublicShell, PublicNav, MarketingHero, ScheduleRail, CTABand, BrandFooter }} from '@/ui';

const services = Array.isArray(BRAND_MANIFEST?.services) ? BRAND_MANIFEST.services : [];
const LISTING_BASE = {base_js};

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
    href: `${{LISTING_BASE}}/${{s.id || i + 1}}`,
  }}));

  return (
    <PublicShell brandName={{{brand_js}}} chrome="immersive" nav={{<PublicNav items={{navItems}} cta={{navCta}} />}}>
      <div data-skeleton="public-service"{appspec_attrs}>{appspec_hook_spans}
      <MarketingHero
        brandName={{{brand_js}}}
        headline={{{title_js}}}
        subcopy="Pick a session from the schedule — levels, times, and open seats in one place."
        primaryCta={{{{ label: "Browse schedule", href: "#schedule-list" }}}}
        secondaryCta={{{{ label: "Ask AI advisor", href: "/ai-features" }}}}
        imageSrc={{images.hero}}
        imageAlt=""
      />
      <ScheduleRail
        heading="Upcoming sessions"
        description="Filter by level or day. Full sessions can join the waitlist."
        items={{items}}
      />
      <CTABand
        heading="Not sure which session fits?"
        description="Open the AI features hub for advisors, FAQs, and waitlist help."
        primaryCta={{{{ label: "Open AI features", href: "/ai-features" }}}}
        secondaryCta={{{{ label: "Contact us", href: "/contact" }}}}
      />
      <BrandFooter brandName={{{brand_js}}} description="Clear schedules. Real bookings. Brand-first pages." />
      </div>
    </PublicShell>
  );
}}
"""


def _directory_listing_scaffold(
    *,
    component: str,
    brand: str,
    title: str,
    listing_path: str,
    page_id: str,
    action_ids: list[str],
    evidence_ids: list[str],
) -> str:
    brand_js = json.dumps(brand)
    title_js = json.dumps(title)
    base = (listing_path or "/doctors").rstrip("/") or "/doctors"
    base_js = json.dumps(base)
    appspec_attrs = f" data-appspec-page={json.dumps(page_id)}" if page_id else ""
    span_lines: list[str] = []
    for action_id in action_ids:
        span_lines.append(
            f'        <span className="sr-only" data-appspec-action={json.dumps(action_id)}>'
            f"{action_id}</span>"
        )
    for evidence_id in evidence_ids:
        span_lines.append(
            f'        <span className="sr-only" data-appspec-evidence={json.dumps(evidence_id)}>'
            f"{evidence_id}</span>"
        )
    appspec_hook_spans = ("\n" + "\n".join(span_lines) + "\n") if span_lines else "\n"
    storefront_listing = bool(
        re.search(
            r"gallery|artwork|collection|shop|store|menu|catalog|boutique",
            f"{brand} {title} {base}",
            re.I,
        )
    )
    if storefront_listing:
        cta_primary = '{ label: "Inquire", href: "/about" }'
        cta_secondary = '{ label: "Back home", href: "/" }'
        footer_desc = "Browse the collection. Inquire when a piece speaks to you."
        page_desc = "Browse pieces and details — then inquire about availability."
        showcase_heading = "From the collection"
        showcase_desc = "Each card opens a closer look. Inquire when you are ready."
        cta_heading = "Interested in a piece?"
        cta_desc = "Ask about availability, commissions, or a studio visit."
    else:
        cta_primary = '{ label: "Book a visit", href: "/book" }'
        cta_secondary = '{ label: "Ask AI assistant", href: "/ai-features" }'
        footer_desc = "Real providers. Clear booking. Not another homepage clone."
        page_desc = "Browse providers, specialties, and availability — then book the right visit."
        showcase_heading = "Meet the team"
        showcase_desc = "Each card opens a provider profile. Book when you are ready."
        cta_heading = "Ready to schedule?"
        cta_desc = "Pick a time online — same team you just reviewed."
    return f"""// directory listing scaffold — distinct from home marketing clone
import {{ usePublicNavItems, publicCta }} from '@/lib/app-nav';
import {{ BRAND_MANIFEST, images }} from '@/data/mock';
import {{ PublicShell, PublicNav, PageHeader, ProductShowcase, CTABand, BrandFooter }} from '@/ui';

const services = Array.isArray(BRAND_MANIFEST?.services) ? BRAND_MANIFEST.services : [];
const LISTING_BASE = {base_js};

export default function {component}() {{
  const navItems = usePublicNavItems();
  const navCta = publicCta();
  const people = (services.length ? services : [
    {{ id: 'dr-1', name: 'Dr. Avery Chen', description: 'Family medicine · accepting new patients' }},
    {{ id: 'dr-2', name: 'Dr. Jordan Miles', description: 'Pediatrics · same-week visits' }},
    {{ id: 'dr-3', name: 'Dr. Sam Rivera', description: 'Internal medicine · telehealth available' }},
  ]).map((s: any, i: number) => ({{
    title: String(s.name || s.title || `Provider ${{i + 1}}`),
    description: String(s.description || s.specialty || s.role || 'Available for appointments'),
    imageSrc: [images.card1, images.card2, images.card3][i % 3],
    imageAlt: String(s.name || s.title || 'Provider'),
    href: `${{LISTING_BASE}}/${{s.id || i + 1}}`,
  }}));

  return (
    <PublicShell brandName={{{brand_js}}} chrome="solid" nav={{<PublicNav items={{navItems}} cta={{navCta}} />}}>
      <div data-skeleton="public-catalog"{appspec_attrs}>{appspec_hook_spans}
      <PageHeader
        title={{{title_js}}}
        description={json.dumps(page_desc)}
      />
      <ProductShowcase
        heading={json.dumps(showcase_heading)}
        description={json.dumps(showcase_desc)}
        items={{people}}
      />
      <CTABand
        heading={json.dumps(cta_heading)}
        description={json.dumps(cta_desc)}
        primaryCta={{{cta_primary}}}
        secondaryCta={{{cta_secondary}}}
      />
      <BrandFooter brandName={{{brand_js}}} description={json.dumps(footer_desc)} />
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
    # Product Face Contract: page_intent wins over industry/path keywords.
    intent = str(route.get("page_intent") or "").strip().lower()
    if intent == "listing":
        return _directory_listing_scaffold(
            component=component,
            brand=brand,
            title=title,
            listing_path=str(route.get("path") or "/listing"),
            page_id=page_id,
            action_ids=action_ids,
            evidence_ids=evidence_ids,
        )
    # Keyword face pickers — only when intent is absent (legacy / thin contracts).
    if not intent and _is_directory_listing_route(file_path, route):
        return _directory_listing_scaffold(
            component=component,
            brand=brand,
            title=title,
            listing_path=str(route.get("path") or "/doctors"),
            page_id=page_id,
            action_ids=action_ids,
            evidence_ids=evidence_ids,
        )
    if not intent and _is_schedule_listing_route(file_path, route):
        return _schedule_listing_scaffold(
            component=component,
            brand=brand,
            title=title,
            listing_path=str(route.get("path") or "/classes"),
            page_id=page_id,
            action_ids=action_ids,
            evidence_ids=evidence_ids,
        )
    skeleton_id = str(route["skeleton_id"])
    shell = expected_shell(route)
    slots = assigned_non_shell_slots(route)
    components = [shell, "getSkeleton"]
    if skeleton_id in _COMPOSE_LAYOUT_SKELETONS:
        components.append("composeSkeletonLayout")
    else:
        components.append("SkeletonComposer")
    if shell == "PublicShell" and "PublicNav" not in components:
        components.append("PublicNav")
    for slot in slots:
        slot_component = _SLOT_COMPONENT.get(slot)
        if slot_component and slot_component not in components:
            components.append(slot_component)
    slot_lines = "\n".join(
        f"    {slot}: (\n      {_safe_slot_jsx(slot, brand, title, skeleton_id=skeleton_id)}\n    ),"
        for slot in slots
    )
    path = str(route.get("path") or "")
    is_member = path.startswith("/member") or "/member/" in canonical_workspace_path(file_path)
    uses_seed = any(slot in _SEED_SLOTS for slot in slots)
    needs_images = any(
        "images." in _safe_slot_jsx(slot, brand, title, skeleton_id=skeleton_id)
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
    appspec_attrs = f' data-appspec-page={json.dumps(page_id)}' if page_id else ""
    appspec_hook_spans = ""
    if page_id:
        span_lines = []
        for action_id in action_ids:
            span_lines.append(
                f'        <span className="sr-only" data-appspec-action={json.dumps(action_id)}>'
                f"{action_id}</span>"
            )
        for evidence_id in evidence_ids:
            span_lines.append(
                f'        <span className="sr-only" data-appspec-evidence={json.dumps(evidence_id)}>'
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
                f'    <{shell} brandName={{{json.dumps(brand)}}} navItems={{adminNavItems}} rail={{rail}}{appearance}>\n'
                f"      <div data-skeleton={{skeleton.id}}{appspec_attrs}>"
                f"{appspec_hook_spans}{{main}}</div>\n"
                f"    </{shell}>\n"
                "  );"
            )
        else:
            body = (
                "  return (\n"
                f'    <{shell} brandName={{{json.dumps(brand)}}} navItems={{adminNavItems}}>\n'
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
        # Shell/nav/footer chrome comes from the active recipe at runtime.
        chrome_attr = ""
        use_recipe_order = skeleton_id in {
            "public-home",
            "public-service",
            "public-detail",
            "public-booking",
        } and bool(slots)
        composer = (
            "        <SkeletonComposer skeletonId={SKELETON_ID} slots={slots} order={RECIPE_ORDER} />\n"
            if use_recipe_order
            else "        <SkeletonComposer skeletonId={SKELETON_ID} slots={slots} />\n"
        )
        body = (
            "  return (\n"
            f'    <{shell} brandName={{{json.dumps(brand)}}}{chrome_attr} '
            f'nav={{<PublicNav items={{navItems}} cta={{navCta}} />}}>\n'
            f"      <div data-skeleton={{skeleton.id}}{appspec_attrs}>\n"
            f"{appspec_hook_spans}"
            f"{composer}"
            "      </div>\n"
            f"    </{shell}>\n"
            "  );"
        )
    order_const = (
        f"const RECIPE_ORDER = {json.dumps(slots)} as const;\n\n"
        if skeleton_id
        in {
            "public-home",
            "public-service",
            "public-detail",
            "public-booking",
        }
        and slots
        else ""
    )
    return f"""// deterministic catalogue contract scaffold
{nav_import}{images_import}import {{ {", ".join(components)} }} from '@/ui';

const SKELETON_ID = {json.dumps(skeleton_id)} as const;
{order_const}export default function {component}() {{
{nav_hook}  const skeleton = getSkeleton(SKELETON_ID);
  const slots = {{
{slot_lines}
  }};

{body}
}}
"""
