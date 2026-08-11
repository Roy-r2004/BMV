"""Deterministic image-prompt builders — the ONLY place image prompts are
authored. Versioned so prompt/model performance can be compared later via
the metadata saved next to each screenshot.

Why deterministic: letting an LLM freewrite image prompts produced the
dark-glow "AI dashboard" cliché every time — the look that reads as fake.
Real SaaS (Linear, Stripe, HubSpot, Fresha, Square) is light, dense and
restrained; the constraints encoding that live here, in code, where they
can't drift. The LLM's only job upstream is filling the UIDemoSpec with
business-specific DATA (see pipeline/ui_spec.py).

Text-legibility rule (proven repeatedly in real generation tests): short
words, numbers and 2-4 word labels render reliably; sentences and
paragraphs garble. Everything the builders emit as visible UI text comes
from spec fields the ui_spec stage is instructed to keep short.
"""

from app.config import settings
from app.pipeline import art_packs
from app.ui_spec import UIDemoSpec

DASHBOARD_IMAGE_PROMPT_VERSION = "dashboard-image-v1"
SCREEN_CONTINUATION_PROMPT_VERSION = "screen-continuation-v1"


def _art_direction(spec: UIDemoSpec, archetype_id: str | None) -> str:
    """The W2 art-direction pack section, or "" when packs are off or the
    archetype has none — an unpacked archetype must render byte-identically
    to how it renders today, so the A/B measures the pack and nothing else."""
    if not settings.ENABLE_ART_PACKS:
        return ""
    section = art_packs.build_art_direction(spec, archetype_id or spec.style.archetype)
    return f"\n\n{section}" if section else ""


def prompt_version(base: str, spec: UIDemoSpec, archetype_id: str | None = None) -> str:
    """Records in the saved metadata whether a pack was actually applied —
    not whether the flag was on. A screenshot whose provenance says "+pack"
    must have had one."""
    if _art_direction(spec, archetype_id):
        return f"{base}+{art_packs.ART_PACK_VERSION}"
    return base

# Composition-variant experiment (composition-variant-v1): instead of 3
# re-rolls of the identical anchor prompt (sampling noise), each anchor
# candidate gets a distinct art-direction directive layered on top of the
# SAME data/branding/design constraints — so the 3 candidates explore
# genuinely different layouts, not just variance. Exploratory; not wired
# into the default pipeline yet.
COMPOSITION_VARIANTS = [
    {
        "id": "hero-intelligence",
        "label": "Hero Intelligence",
        "directive": (
            "COMPOSITION DIRECTION — Hero Intelligence: one dominant chart or intelligence module, "
            "commanding the most visual weight and space of anything on the screen. Build the layout as "
            "an asymmetric two-column composition — not a uniform grid — with supporting KPIs arranged "
            "around the hero element. The AI Workstream module gets premium, polished treatment. Establish "
            "a strong, unmistakable top-level visual hierarchy: this screen is built around insight, not "
            "raw operations."
        ),
    },
    {
        "id": "command-center",
        "label": "Command Center",
        "directive": (
            "COMPOSITION DIRECTION — Command Center: an operational, action-oriented layout, built for "
            "someone actively running the business right now. Favor richer status, workflow and "
            "people-related components — a stronger sense of live activity in progress — over any single "
            "hero visualization; no one element should dominate the way a hero chart would elsewhere. Use "
            "an asymmetric, modular composition with varied card sizes and shapes arranged with intention, "
            "not a uniform grid, so it reads as a busy, capable operations hub."
        ),
    },
    {
        "id": "executive-overview",
        "label": "Executive Overview",
        "directive": (
            "COMPOSITION DIRECTION — Executive Overview: fewer, larger, higher-value modules rather than "
            "many small cards — restraint and confidence over density. This is the strongest typography "
            "and most executive hierarchy of any variant. Favor premium, synthesized business insights and "
            "AI-generated recommendations over raw operational detail. Deliberately avoid repetitive, "
            "identical KPI-card behavior — if KPIs appear, treat them as part of a larger insight module "
            "rather than a uniform row of small boxes. This should feel like a boardroom summary a business "
            "owner glances at once a day, not a workbench they live in."
        ),
    },
]

_DESIGN_CONSTRAINTS = """DESIGN CONSTRAINTS

The bar is not "looks like functional software" — plenty of generic admin templates clear that bar and still feel cheap. The bar is: this looks like a $50K+ bespoke product a top-tier product-design studio built specifically for this business — real production SaaS, not concept art or a design portfolio shot, but visually striking within the first half-second, not merely tidy.

Use:
- confident, deliberate visual hierarchy: one clear focal point (the single most important number or chart, given real size/weight dominance), everything else visibly secondary — never a flat grid of equally-weighted boxes
- beautiful, considered typography: a real type scale with intentional weight and size contrast, numerals that feel designed rather than default UI-kit text, nothing oversized or gimmicky
- sophisticated spacing used as a design tool: generous room that creates rhythm and focus, never sparse/empty and never cramped
- premium card treatment: refined hairline borders (#E5E7EB), soft layered shadows for real depth, subtle tonal or gradient fills where they add richness — vary card size and visual weight so the layout reads as designed, not a row of identical repetitive white boxes
- clean white / very-light-gray base (#FFFFFF content on #F8F9FB canvas), with the brand color used generously and with intention — chart, focal metric, avatar colors, active states — not just one timid accent dot
- tasteful, consistent iconography and colorful avatar initials that feel art-directed, not stock
- generous internal padding on every card, especially any list or activity feed — the last row or entry always sits with visible breathing room above the card's bottom edge, never clipped
- every status pill, badge or icon clearly communicates its own meaning at a glance — never a bare dash or icon with no label; give any row-level menu/icon button its own comfortable spacing so it never crowds the text next to it
- realistic UI states: one nav item active, one row subtly hovered

Avoid:
- generic admin-dashboard energy, a wireframe feeling, or anything that reads as templated
- futuristic or holographic interfaces, neon glow, dark sci-fi themes, glassmorphism
- excessive empty space, timid/tiny UI elements, weak hierarchy, boring uniform tables
- oversized decorative icons, giant display text for its own sake, random 3D shapes
- marketing landing-page composition or hero-style layouts
- abstract illustrations, stock-photo backgrounds, or fantasy concept-art rendering
- laptop / phone / browser mockup frames around the interface
- invented random UI elements that no real product would have
- lorem ipsum or meaningless placeholder data

The navigation, metrics, chart and data must be internally coherent — they all describe the same business on the same day. A prospect looking at this should think "they already built this for me," not "this is a generic template with my name on it."

Reserve only the immediate bottom-right corner of the canvas (roughly the last 12% of width and 17% of height) clear of text, icon or card content — a real logo is composited into exactly that small corner afterward. No card, list or table may extend into or behind that corner at all, even partially — every element must end with clear margin before that boundary; a card merely hidden behind the logo is still wrong. This is a small protected area, not a design cue: let the surrounding cards and layout fill the rest of the canvas naturally, right up to that boundary, with no large empty gap or dead space beyond what's strictly needed to protect the corner.

OUTPUT

A full-bleed desktop application screenshot filling the entire canvas edge to edge. No device frame, no browser chrome, no drop shadow around the app, no background visible behind it."""


def _kpi_block(spec: UIDemoSpec) -> str:
    lines = ["KPI CARDS", ""]
    for kpi in spec.kpis[:4]:
        entry = f"{kpi.label}\n{kpi.value}"
        if kpi.delta:
            entry += f"\n{kpi.delta}"
        lines.append(entry)
        lines.append("")
    return "\n".join(lines).rstrip()


def _panel_block(title: str, panel) -> str:
    lines = [title, "", panel.title, ""]
    for row in panel.rows[:6]:
        lines.append("   ".join(str(v) for v in row.values() if str(v).strip()))
    return "\n".join(lines)


def _chart_block(spec: UIDemoSpec) -> str:
    """The hero visualization. Trend/peak callouts are computed here from the
    existing values — not new spec fields — so the image model has concrete
    text to render as an annotation instead of inventing one itself."""
    chart = spec.chart
    if chart is None or not chart.labels:
        return ""
    labels, values = chart.labels[:8], chart.values[:8]
    pairs = [f"{label} {value:g}" for label, value in zip(labels, values)]

    annotations = []
    if len(values) >= 2 and values[0]:
        pct = (values[-1] - values[0]) / values[0] * 100
        annotations.append(
            f'Trend annotation to render prominently on the chart: "{pct:+.0f}% {labels[0]} → {labels[-1]}"'
        )
    if values:
        peak_i = max(range(len(values)), key=lambda i: values[i])
        annotations.append(
            f"Emphasize the peak point ({labels[peak_i]}, {values[peak_i]:g}) with a distinct marker or callout."
        )
    annotation_text = ("\n" + "\n".join(annotations)) if annotations else ""

    guidance = (
        "\n\nThis chart is the single most visually crafted element on the screen — not a small "
        "thumbnail squeezed into a side card. Give it real, generous space: at minimum as wide as "
        "two KPI cards combined, with genuine height, positioned so it reads as a centerpiece, not "
        "an afterthought. Polished axis treatment — visible gridlines, axis tick labels, the unit "
        "shown clearly. Render the trend/peak annotations above as actual visual callouts on the "
        "chart itself (a small badge, an emphasized point with a marker and label) — comparison "
        "context, not just raw numbers. Premium data-viz styling: a smooth curve or well-proportioned "
        "bars, a subtle gradient fill under a line, a glowing or emphasized endpoint, color pulled "
        "intentionally from the brand palette. Give the Y-axis unit real typographic presence with a "
        "deliberate, clearly legible caption — render it horizontally (never rotated or sideways), "
        "positioned so it reads immediately without tilting your head."
    )

    return (
        "CHART — this is the screen's HERO element, the single most visually crafted thing on it\n\n"
        f"{chart.title}\n" + "\n".join(pairs) + f"\nY-axis unit: {chart.metric_label}" + annotation_text + guidance
    )


_ACTIVITY_STATUS_CYCLE = ("Done", "In Progress", "Queued")
_AI_PANEL_TITLE_KEYWORDS = ("task", "queue")


def _is_ai_task_panel(title: str) -> bool:
    t = (title or "").lower()
    return any(kw in t for kw in _AI_PANEL_TITLE_KEYWORDS)


def secondary_panel_is_merged_ai_task_list(spec: UIDemoSpec) -> bool:
    """True when spec.secondary_panel is itself an AI-task-style list (e.g.
    ui_spec's LLM stage naming it "AI Task Queue") that _merged_ai_entries
    folds into the single AI Workstream module — used by _content_sections
    to skip emitting it a second time as its own SECONDARY PANEL section."""
    panel = spec.secondary_panel
    return bool(panel and panel.rows and _is_ai_task_panel(panel.title))


def _merged_ai_entries(spec: UIDemoSpec) -> list[tuple[str, str, str | None, str]]:
    """(name, action, time, status) tuples for the single AI Workstream
    module. Folds a secondary_panel that's itself an AI-task list into the
    same module upstream of prompt building — the prompt must only ever
    describe ONE AI-activity module, never two concepts left for the image
    model to merge itself. (Found in testing: ui_spec's LLM stage had put a
    literal secondary_panel titled "AI Task Queue" alongside the activity
    list; sent as two separate sections, the model dutifully rendered both,
    even once explicitly told not to — the fix has to happen before the
    prompt is built, not by asking harder.)"""
    entries = [
        (item.name, item.action, item.time, _ACTIVITY_STATUS_CYCLE[i % len(_ACTIVITY_STATUS_CYCLE)])
        for i, item in enumerate(spec.activity)
    ]
    if secondary_panel_is_merged_ai_task_list(spec):
        for row in spec.secondary_panel.rows:
            status = next((str(v) for k, v in row.items() if k.lower() == "status" and str(v).strip()), "Queued")
            action = next((str(v) for k, v in row.items() if k.lower() != "status" and str(v).strip()), "")
            if action:
                entries.append(("AI", action, None, status))
    return entries[:4]


def _activity_block(spec: UIDemoSpec) -> str:
    """A designed 'AI at work' module, not a plain event log."""
    entries = _merged_ai_entries(spec)
    if not entries:
        return ""
    lines = [
        "AI WORKSTREAM — this is the ONLY AI-activity module on this screen. Its exact title is "
        '"AI Workstream" — render it once, with exactly this title. Do NOT create, in addition to '
        'this, any other card or panel titled "AI Task Queue", "Task Queue", "Queue", or any second '
        "AI-activity panel anywhere on the screen. Even though the items below mix Done, In Progress "
        "and Queued statuses, render ALL of them together inside this one card — never split them by "
        "status into two separate visual groups or panels.\n",
    ]
    for name, action, time, status in entries:
        entry = f"{name} — {action}" if action else name
        if time:
            entry += f" · {time}"
        entry += f" · status: {status}"
        lines.append(entry)
    return "\n".join(lines)


def _content_sections(spec: UIDemoSpec) -> str:
    sections = [
        f"SCREEN\n\n{spec.screen_title}",
    ]
    header_lines = [line for line in (spec.greeting, spec.subheading) if line]
    if header_lines:
        sections.append("HEADER\n\n" + "\n".join(header_lines))
    if spec.navigation:
        sections.append("NAVIGATION (left sidebar, top to bottom; mark the current screen active)\n\n" + "\n".join(spec.navigation[:8]))
    if spec.kpis:
        sections.append(_kpi_block(spec))
    if spec.primary_panel.rows:
        sections.append(_panel_block("PRIMARY PANEL", spec.primary_panel))
    if spec.secondary_panel and spec.secondary_panel.rows and not secondary_panel_is_merged_ai_task_list(spec):
        sections.append(_panel_block("SECONDARY PANEL", spec.secondary_panel))
    chart = _chart_block(spec)
    if chart:
        sections.append(chart)
    activity = _activity_block(spec)
    if activity:
        sections.append(activity)
    return "\n\n".join(sections)


def _branding_block(spec: UIDemoSpec) -> str:
    lines = [
        "BRANDING",
        "",
        f"Business name: {spec.business.name}",
        f"Industry: {spec.business.industry}",
    ]
    if spec.business.location:
        lines.append(f"Location: {spec.business.location}")
    if spec.business.primary_color:
        lines.append(f"Primary brand color: {spec.business.primary_color} (accents only, on a light interface)")
    if spec.business.secondary_color:
        lines.append(f"Secondary color: {spec.business.secondary_color} (sparingly)")
    if spec.style.palette_description:
        lines.append(f"Palette: {spec.style.palette_description}")
    lines.append(
        f'The product wordmark "{spec.product.name}" appears small and plain at the top of the sidebar.'
    )
    return "\n".join(lines)


def build_dashboard_image_prompt(
    spec: UIDemoSpec, composition: dict | None = None, archetype_id: str | None = None,
) -> str:
    """The anchor-screen prompt (version: dashboard-image-v1). `composition`
    (an entry from COMPOSITION_VARIANTS) layers a distinct art-direction
    directive on top of the same data/branding/design constraints — used by
    the composition-variant experiment; normal calls omit it and get the
    prompt exactly as before.

    The W2 art-direction pack (typography, spacing, chart treatment and an
    exact derived palette for this archetype) is appended after the generic
    design constraints, so the specific instruction is the last thing read."""
    density = "compact, information-dense" if spec.style.density == "compact" else "comfortable but realistic"
    composition_directive = f"\n\n{composition['directive']}" if composition else ""
    return f"""TASK

Create a realistic desktop screenshot of a production SaaS application used by {spec.business.industry or "a local business"} — bespoke software built specifically for this business by an elite product-design studio. The quality bar is Linear, Stripe, Arc, Ramp and Vercel at their most polished, with the craft of a top-tier product-design portfolio piece. It must be real, believable production software — not a fantasy concept shot — but visually impressive enough that the business owner's reaction is "you already built this for us?"{composition_directive}

BUSINESS

{spec.business.name}

SOFTWARE

Product name: {spec.product.name}
Purpose: {spec.product.purpose}
Layout density: {density}

{_content_sections(spec)}

Every visible string above is the EXACT text to render — short labels, names and numbers only. Render each string once, spelled exactly as written. Do not add extra text of your own.

{_branding_block(spec)}

{_DESIGN_CONSTRAINTS}{_art_direction(spec, archetype_id)}"""


def build_continuation_prompt(spec: UIDemoSpec, anchor_screen_title: str, archetype_id: str | None = None) -> str:
    """Follow-up screen prompt (version: screen-continuation-v1). Sent WITH the
    selected anchor screenshot attached as a reference image so every screen
    looks like the same product."""
    return f"""TASK

The attached image is the "{anchor_screen_title}" screen of {spec.product.name}, a production SaaS application used by {spec.business.name} ({spec.business.industry}). Create the "{spec.screen_title}" screen of the EXACT SAME application.

Preserve the exact same application design:
- Preserve the sidebar, its wordmark, its items and their order — only the active item changes to {spec.screen_title}.
- Preserve the typography, colors, spacing, card styling, borders and shadows exactly.
- Preserve the overall light, restrained, production-software look.
- Only the main content area changes, to the content below.

{_content_sections(spec)}

Every visible string above is the EXACT text to render — short labels, names and numbers only. Render each string once, spelled exactly as written. Do not add extra text of your own.

{_DESIGN_CONSTRAINTS}{_art_direction(spec, archetype_id)}"""
