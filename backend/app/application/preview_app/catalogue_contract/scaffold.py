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


def _safe_slot_jsx(slot: str, brand: str, title: str) -> str:
    brand_js = json.dumps(brand)
    title_js = json.dumps(title)
    samples = {
        "hero": (
            f'<MarketingHero brandName={{{brand_js}}} headline={{{title_js}}} '
            'subcopy="Cinematic first impression — brand-forward, vivid, and ready for the next step." '
            'primaryCta={{ label: "Explore now", href: "#details" }} '
            'secondaryCta={{ label: "See how it works", href: "#process" }} '
            'imageSrc={images.hero} imageAlt="" />'
        ),
        "features": (
            '<FeatureBento heading="Designed to feel alive" items={['
            '{ title: "Immersive first view", description: "Atmosphere, motion, and brand color from the first scroll." }, '
            '{ title: "Real product moments", description: "Concrete screens — bookings, tickets, KPIs — not placeholder cards." }, '
            '{ title: "Guided next step", description: "Every section pushes toward a clear action." }'
            ']} />'
        ),
        "products": (
            '<ProductShowcase heading="Featured picks" items={['
            '{ title: "Signature item", description: "A dependable starting point.", imageSrc: images.card1, imageAlt: "" }, '
            '{ title: "Everyday essential", description: "Built for daily use.", imageSrc: images.card2, imageAlt: "" }'
            ']} />'
        ),
        "showcase": (
            '<ProductShowcase heading="Featured experiences" items={['
            '{ title: "Signature service", description: "A dependable starting point.", imageSrc: images.card1, imageAlt: "" }, '
            '{ title: "Everyday essential", description: "Built for daily use.", imageSrc: images.card2, imageAlt: "" }'
            ']} />'
        ),
        "process": (
            '<ProcessSection heading="How it works" steps={['
            '{ title: "Choose", description: "Find the right option." }, '
            '{ title: "Confirm", description: "Select a convenient time." }, '
            '{ title: "Enjoy", description: "We take care of the details." }'
            ']} />'
        ),
        "testimonials": (
            '<TestimonialRail heading="What clients say" items={['
            '{ quote: "Clear, warm, and easy from start to finish.", author: "A returning client", role: "Verified guest" }'
            ']} />'
        ),
        "cta": (
            '<CTABand heading="Make it unforgettable" description="Book the next chapter — polished, branded, never bland." '
            'primaryCta={{ label: "Get started", href: "#details" }} '
            'secondaryCta={{ label: "Talk to us", href: "#contact" }} />'
        ),
        "footer": f'<BrandFooter brandName={{{brand_js}}} description="Premium presence from first glance to booked revenue." />',
        "trust": '<LogoMarquee heading="Trusted in the room" items={[{ label: "Signature craft" }, { label: "On-time delivery" }, { label: "Repeat guests" }, { label: "Local favorite" }]} />',
        "credentials": (
            '<CredentialStrip heading="Why it stands out" items={['
            '{ title: "Brand-first chrome", detail: "Every surface carries your color and type." }, '
            '{ title: "Motion with purpose", detail: "Kenburns, reveals, and lifts — never static." }'
            ']} />'
        ),
        "spotlight": '<SpotlightCard title="Atmosphere over filler" description="Layered glow, grain, and brand light so the page never looks pale." />',
        "results": (
            '<ResultRail heading="Representative results" items={['
            '{ label: "Signature result", beforeSrc: images.card2, afterSrc: images.card3 }'
            ']} />'
        ),
        "booking": (
            '<BookingPanel heading="Choose a time" '
            'treatments={[{ id: "signature", name: "Signature service", duration: "60 min" }]} '
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
        "header": f'<PageHeader title={{{title_js}}} description="A current view of the work that needs your attention." meta={{<span className="text-sm text-muted">Today</span>}} />',
        "kpis": (
            '<div className="grid grid-cols-1 gap-4 sm:grid-cols-3">'
            '<StatCard label="Active today" value="24" delta="+8%" hint="Compared with last week" />'
            '<StatCard label="In progress" value="11" delta="+2" hint="Open work items" />'
            '<StatCard label="Resolved" value="93%" delta="-2%" hint="Rolling 7-day rate" />'
            '</div>'
        ),
        "chart": (
            '<ChartCard title="Weekly performance" type="area" dataKey="value" xKey="day" '
            'data={[{ day: "Mon", value: 12 }, { day: "Tue", value: 18 }, { day: "Wed", value: 15 }, '
            '{ day: "Thu", value: 22 }, { day: "Fri", value: 19 }]} />'
        ),
        "filters": '<FilterBar searchPlaceholder="Search records" filters={[{ id: "all", label: "All", active: true }, { id: "open", label: "Open", active: false }]} />',
        "table": (
            '<DataTable columns={['
            '{ key: "name", header: "Name" }, '
            '{ key: "status", header: "Status" }, '
            '{ key: "updated", header: "Updated" }'
            ']} rows={['
            '{ name: "Primary record", status: "In progress", updated: "Today" }, '
            '{ name: "Follow-up item", status: "On hold", updated: "Yesterday" }, '
            '{ name: "Completed item", status: "Done", updated: "2 days ago" }'
            ']} />'
        ),
        "activity": (
            '<ActivityFeed heading="Activity" items={['
            '{ id: "activity-1", title: "Record updated", detail: "The latest details are ready.", time: "Just now" }, '
            '{ id: "activity-2", title: "Owner assigned", detail: "Waiting on confirmation.", time: "12m ago" }, '
            '{ id: "activity-3", title: "Note added", detail: "Customer asked for a callback.", time: "1h ago" }'
            ']} />'
        ),
        "risk": (
            '<RiskQueue heading="Needs attention" items={['
            '{ id: "risk-1", title: "Follow-up due", detail: "A client is waiting for confirmation.", severity: "medium" }'
            ']} />'
        ),
        "empty": '<EmptyState title="Nothing here yet" description="New records will appear here." />',
    }
    try:
        return samples[slot]
    except KeyError as exc:
        raise ValueError(f"Unsupported catalogue fallback slot: {slot}") from exc


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
    skeleton_id = str(route["skeleton_id"])
    shell = expected_shell(route)
    slots = assigned_non_shell_slots(route)
    brand = brand_name or "Brand"
    title = str(route.get("title") or component.replace("Page", "") or "Overview")
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
    needs_images = any("images." in _safe_slot_jsx(slot, brand, title) for slot in slots)
    images_import = "import { images } from '@/data/mock';\n" if needs_images else ""
    page_id = str(route.get("app_spec_page_id") or route.get("page_id") or "").strip()
    action_ids = [str(a) for a in (route.get("action_ids") or []) if a]
    evidence_ids = [str(e) for e in (route.get("evidence_ids") or []) if e]
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
        # Immersive chrome suits full-bleed heroes (retail/nocturne/editorial).
        chrome_attr = ' chrome="immersive"' if skeleton_id == "public-home" else ""
        use_recipe_order = skeleton_id == "public-home" and bool(slots)
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
        if skeleton_id == "public-home" and slots
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

