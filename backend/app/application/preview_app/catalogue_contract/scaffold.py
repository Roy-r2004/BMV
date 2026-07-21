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
}

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
    "fintech",
    "oms",
    "execution",
    "broker",
    "pnl",
    "p&l",
    "fund",
    "desk",
)


def _is_trading_domain(*parts: str) -> bool:
    blob = " ".join(str(p or "") for p in parts).lower()
    return any(hint in blob for hint in _TRADING_HINTS)


def _safe_slot_jsx(slot: str, brand: str, title: str) -> str:
    brand_js = json.dumps(brand)
    title_js = json.dumps(title)
    trading = _is_trading_domain(brand, title)
    samples = {
        "hero": (
            f'<MarketingHero brandName={{{brand_js}}} '
            f'headline={{seed.hero?.headline || {title_js}}} '
            'subcopy={seed.hero?.subcopy} '
            'primaryCta={seed.hero?.primaryCta} '
            'secondaryCta={seed.hero?.secondaryCta} '
            'imageSrc={images.hero} imageAlt="" />'
        ),
        "features": (
            '<FeatureBento heading={seed.featuresHeading ?? "Designed to feel alive"} '
            'imagePool={[images.card1, images.card2, images.card3]} '
            'items={seed.features ?? []} />'
        ),
        "products": (
            '<ProductShowcase heading={seed.showcaseHeading ?? "Featured picks"} '
            'items={(seed.items ?? []).map((item, index) => ({ '
            'title: item.title, description: item.description, '
            'imageSrc: [images.card1, images.card2, images.card3][index % 3], imageAlt: item.title '
            '}))} />'
        ),
        "showcase": (
            '<ProductShowcase heading={seed.showcaseHeading ?? "Featured experiences"} '
            'items={(seed.items ?? []).map((item, index) => ({ '
            'title: item.title, description: item.description, '
            'imageSrc: [images.card1, images.card2, images.card3][index % 3], imageAlt: item.title '
            '}))} />'
        ),
        "process": (
            '<ProcessSection heading={seed.processHeading ?? "How it works"} '
            'steps={seed.process ?? []} />'
        ),
        "testimonials": (
            '<TestimonialRail heading={seed.testimonialsHeading ?? "What clients say"} '
            'items={seed.testimonials ?? []} />'
        ),
        "cta": (
            '<CTABand heading={seed.cta?.heading ?? "Make it unforgettable"} '
            'description={seed.cta?.description ?? "Book the next chapter — polished, branded, never bland."} '
            'primaryCta={{ label: seed.cta?.primaryLabel ?? "Get started", href: seed.cta?.primaryHref ?? "#details" }} '
            'secondaryCta={{ label: seed.cta?.secondaryLabel ?? "Talk to us", href: seed.cta?.secondaryHref ?? "#contact" }} />'
        ),
        "footer": (
            f'<BrandFooter brandName={{{brand_js}}} '
            'description={seed.footer?.description ?? "Premium presence from first glance to booked revenue."} />'
        ),
        "trust": (
            '<LogoMarquee size="display" '
            'items={(seed.trustLabels ?? []).map((label) => ({ label }))} />'
        ),
        "credentials": (
            '<CredentialStrip heading={seed.credentialsHeading ?? "Why it stands out"} '
            'items={seed.credentials ?? []} />'
        ),
        "spotlight": '<SpotlightCard title="Atmosphere over filler" description="Layered glow, grain, and brand light so the page never looks pale." />',
        "results": (
            '<ResultRail heading="Representative results" items={['
            '{ label: "Signature result", beforeSrc: images.card2, afterSrc: images.card3 }'
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
        "header": (
            f'<PageHeader title={{seed.hero?.headline || {title_js}}} '
            + (
                'description={seed.hero?.subcopy || "Watchlist, blotter, positions, and P&L for the fund book."} '
                if trading
                else 'description={seed.hero?.subcopy || "A current view of the work that needs your attention."} '
            )
            + 'meta={<span className="text-sm text-muted">Live</span>} />'
        ),
        "kpis": (
            '<div className="grid grid-cols-1 gap-4 sm:grid-cols-3">'
            + (
                (
                    '<StatCard label={seed.kpis?.[0]?.label ?? "Open orders"} value={seed.kpis?.[0]?.value ?? "18"} delta={seed.kpis?.[0]?.delta ?? "+3"} hint={seed.kpis?.[0]?.hint ?? "working on desk"} />'
                    '<StatCard label={seed.kpis?.[1]?.label ?? "Day P&L"} value={seed.kpis?.[1]?.value ?? "+1.24M"} delta={seed.kpis?.[1]?.delta ?? "+0.4%"} hint={seed.kpis?.[1]?.hint ?? "vs NAV"} />'
                    '<StatCard label={seed.kpis?.[2]?.label ?? "Gross exposure"} value={seed.kpis?.[2]?.value ?? "62%"} delta={seed.kpis?.[2]?.delta ?? "-3%"} hint={seed.kpis?.[2]?.hint ?? "limit 75%"} />'
                )
                if trading
                else (
                    '<StatCard label={seed.kpis?.[0]?.label ?? "Active today"} value={seed.kpis?.[0]?.value ?? "24"} delta={seed.kpis?.[0]?.delta ?? "+8%"} hint={seed.kpis?.[0]?.hint ?? "Compared with last week"} />'
                    '<StatCard label={seed.kpis?.[1]?.label ?? "In progress"} value={seed.kpis?.[1]?.value ?? "11"} delta={seed.kpis?.[1]?.delta ?? "+2"} hint={seed.kpis?.[1]?.hint ?? "Open work items"} />'
                    '<StatCard label={seed.kpis?.[2]?.label ?? "Resolved"} value={seed.kpis?.[2]?.value ?? "93%"} delta={seed.kpis?.[2]?.delta ?? "-2%"} hint={seed.kpis?.[2]?.hint ?? "Rolling 7-day rate"} />'
                )
            )
            + '</div>'
        ),
        "chart": (
            '<ChartCard title={seed.showcaseHeading ?? '
            + ('"Intraday P&L"' if trading else '"Weekly performance"')
            + '} type="area" dataKey="value" xKey="day" '
            'data={[{ day: "Mon", value: 12 }, { day: "Tue", value: 18 }, { day: "Wed", value: 15 }, '
            '{ day: "Thu", value: 22 }, { day: "Fri", value: 19 }]} />'
        ),
        "filters": (
            '<FilterBar searchPlaceholder="'
            + ("Search symbols / orders" if trading else "Search records")
            + '" filters={[{ id: "all", label: "All", active: true }, { id: "'
            + ("working" if trading else "open")
            + '", label: "'
            + ("Working" if trading else "Open")
            + '", active: false }]} />'
        ),
        "table": (
            '<DataTable columns={['
            '{ key: "name", header: "'
            + ("Order" if trading else "Name")
            + '" }, '
            '{ key: "status", header: "Status" }, '
            '{ key: "owner", header: "'
            + ("Desk" if trading else "Owner")
            + '" }'
            ']} rows={(seed.tableRows ?? ['
            + (
                (
                    '{ id: "t1", name: "AAPL · BUY 25,000", status: "Working", owner: "Exec trader" }, '
                    '{ id: "t2", name: "MSFT · SELL 12,000", status: "Partial", owner: "Exec trader" }, '
                    '{ id: "t3", name: "NVDA · BUY 8,000", status: "Staged", owner: "PM" }'
                )
                if trading
                else (
                    '{ id: "t1", name: "Primary record", status: "In progress", owner: "Ops" }, '
                    '{ id: "t2", name: "Follow-up item", status: "On hold", owner: "Ops" }, '
                    '{ id: "t3", name: "Completed item", status: "Done", owner: "Ops" }'
                )
            )
            + ']).map((row) => ({ name: row.name, status: row.status, owner: row.owner || row.updated || "—" }))} />'
        ),
        "activity": (
            '<ActivityFeed heading="Activity" items={(seed.activity ?? ['
            + (
                (
                    '{ id: "activity-1", title: "Fill · AAPL 10k", detail: "Avg 198.22 · rest working", time: "Just now" }, '
                    '{ id: "activity-2", title: "Ticket staged · NVDA", detail: "Buy 8k @ 905.00", time: "4m ago" }, '
                    '{ id: "activity-3", title: "Risk check passed", detail: "MSFT sell within net limit", time: "11m ago" }'
                )
                if trading
                else (
                    '{ id: "activity-1", title: "Record updated", detail: "The latest details are ready.", time: "Just now" }, '
                    '{ id: "activity-2", title: "Owner assigned", detail: "Waiting on confirmation.", time: "12m ago" }, '
                    '{ id: "activity-3", title: "Note added", detail: "Internal handoff logged.", time: "1h ago" }'
                )
            )
            + '])} />'
        ),
        "risk": (
            '<RiskQueue heading="'
            + ("Risk limits" if trading else "Needs attention")
            + '" items={(seed.risk ?? ['
            + (
                '{ id: "risk-1", title: "Sector concentration", detail: "Tech sleeve at 28% of NAV", severity: "medium" }'
                if trading
                else
                '{ id: "risk-1", title: "Follow-up due", detail: "An internal item needs confirmation.", severity: "medium" }'
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


def _route_text_blob(file_path: str, route: dict) -> str:
    parts = [
        str(route.get("path") or ""),
        str(route.get("title") or ""),
        str(route.get("page_id") or ""),
        str(route.get("app_spec_page_id") or ""),
        canonical_workspace_path(file_path),
    ]
    return " ".join(parts).lower()


def _is_schedule_listing_route(file_path: str, route: dict) -> bool:
    """Classes/services listings get ScheduleRail — not a home marketing clone."""
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
    if _is_schedule_listing_route(file_path, route):
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
    if skeleton_id == "ops-dashboard":
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
        f"    {slot}: (\n      {_safe_slot_jsx(slot, brand, title)}\n    ),"
        for slot in slots
    )
    path = str(route.get("path") or "")
    is_member = path.startswith("/member") or "/member/" in canonical_workspace_path(file_path)
    uses_seed = any(slot in _SEED_SLOTS for slot in slots)
    needs_images = any("images." in _safe_slot_jsx(slot, brand, title) for slot in slots)
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
        if skeleton_id == "ops-dashboard":
            body = (
                "  const { main, rail } = composeSkeletonLayout(SKELETON_ID, slots);\n\n"
                "  return (\n"
                f'    <{shell} brandName={{{json.dumps(brand)}}} navItems={{adminNavItems}} rail={{rail}}>\n'
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
