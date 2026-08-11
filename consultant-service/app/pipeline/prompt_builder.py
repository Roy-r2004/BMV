"""Deterministic image-prompt builders — the ONLY place image prompts are
authored. Versioned so prompt/model performance can be compared later via
the metadata saved next to each screenshot.

Why deterministic: letting an LLM freewrite image prompts produced the
dark-glow "AI dashboard" cliché every time — the look that reads as fake.
The constraints that rule it out live here, in code, where they can't
drift. The LLM's only job upstream is filling the UIDemoSpec with
business-specific DATA (see pipeline/ui_spec.py).

Two registers (session 32). The original constraints ruled out the cliché
by ruling out the whole dark register — light, dense, restrained, the
Linear/Stripe/Ramp reading of "real software". That threw out the
disciplined version with the fake one: the screens people actually call
astonishing (luxury property configurators, private-bank consoles) are
dark, and they are not the cliché. `_CINEMATIC_REGISTER` keeps every
anti-cliché guard the light register earned — no glow, no HUD, no floating
geometry, no glassmorphism, one accent only — and moves the ground. The
light register is preserved verbatim so the two can be compared rather
than argued about.

Text-legibility rule (proven repeatedly in real generation tests): short
words, numbers and 2-4 word labels render reliably; sentences and
paragraphs garble. Everything the builders emit as visible UI text comes
from spec fields the ui_spec stage is instructed to keep short.
"""

from app.config import settings
from app.pipeline import art_packs
from app.ui_spec import UIDemoSpec

DASHBOARD_IMAGE_PROMPT_VERSION = "dashboard-image-v2"
SCREEN_CONTINUATION_PROMPT_VERSION = "screen-continuation-v2"


def _art_direction(spec: UIDemoSpec, archetype_id: str | None) -> str:
    """The W2 art-direction pack section, or "" when packs are off or the
    archetype has none — an unpacked archetype must render byte-identically
    to how it renders today, so the A/B measures the pack and nothing else."""
    if not settings.ENABLE_ART_PACKS:
        return ""
    section = art_packs.build_art_direction(spec, archetype_id or spec.style.archetype)
    return f"\n\n{section}" if section else ""


def prompt_version(base: str, spec: UIDemoSpec, archetype_id: str | None = None) -> str:
    """Records in the saved metadata what the prompt ACTUALLY contained — not
    which flags were set. A screenshot whose provenance says "+pack" must
    have had one; one that says "cinematic+tool" must have been asked for a
    selection flow in the dark register. This string is how a screenshot on
    disk gets attributed months later, so every axis that changes the prompt
    belongs in it."""
    parts = [f"{base}-{register_id()}"]
    if is_tool_screen(spec):
        parts.append("tool")
    if settings.ENABLE_HERO_ASSET and spec.hero.present:
        parts.append("hero")
    if settings.ENABLE_AI_LAYER and spec.ai.present:
        parts.append("ai")
    if _art_direction(spec, archetype_id):
        parts.append(art_packs.ART_PACK_VERSION)
    return "+".join(parts)

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

_CORNER_RESERVE = """

Reserve only the immediate bottom-right corner of the canvas (roughly the last 12% of width and 17% of height) clear of text, icon or card content — a real logo is composited into exactly that small corner afterward. No card, list or table may extend into or behind that corner at all, even partially — every element must end with clear margin before that boundary; a card merely hidden behind the logo is still wrong. This is a small protected area, not a design cue: let the surrounding cards and layout fill the rest of the canvas naturally, right up to that boundary, with no large empty gap or dead space beyond what's strictly needed to protect the corner."""

_OUTPUT_BLOCK = """

OUTPUT

A full-bleed desktop application screenshot filling the entire canvas edge to edge. No device frame, no browser chrome, no drop shadow around the app, no background visible behind it."""


_CINEMATIC_REGISTER = """DESIGN CONSTRAINTS

The bar is not "looks like functional software" — plenty of dark admin themes clear that bar and still read as a stock template. The bar is: this is the flagship screen of a product someone spent a fortune building, the one a luxury developer, a private bank or a marque automaker puts on stage. Real, believable production software where every element does a job — but the kind that makes a viewer lean toward the screen within the first half-second.

Use:
- a deep, single-hue ground: near-black carrying one dominant colour drawn from the brand — not neutral charcoal, not pure black, and never more than one ground hue on the screen
- exactly ONE luminous accent (a warm metallic, or the brightest tint of the brand hue), spent only on the active state, the primary action and the single most important number — its scarcity is what makes it read as expensive
- real depth and light: a soft directional falloff across the ground, panels lifted by low-opacity elevation rather than hard borders, hairline strokes only where separation is genuinely needed
- two typographic voices in deliberate contrast: a display face with real character for the page title and hero numerals, against a small, letterspaced, uppercase sans for labels, steps and captions — that contrast does most of the work
- generous negative space treated as luxury rather than emptiness: FEWER elements, each given real room. Bare ground between elements is the point — never add a panel to fill a gap, and never repeat a panel you have already drawn. Restraint is the most expensive thing on the screen
- the interface is the canvas: its own background reaches all four edges, with no margin, vignette or backdrop visible around it. That is about where the BACKGROUND ends, not about packing content — a screen with six elements and a lot of quiet ground still reaches the edges
- text that survives being read: on a dark ground, small type loses legibility fast. Every visible label, chip and caption is large enough and high-contrast enough to be crisply legible, correctly spelled and never faint grey-on-grey. Prefer fewer, larger labels over many tiny ones; if a label cannot be rendered sharply at its size, make it bigger rather than dimmer
- a strong asymmetric composition — one commanding focal element with supporting material arranged around it, never a uniform grid of equally-weighted cards
- restrained, precise iconography: thin strokes, consistent weight, small
- realistic UI states: one nav item active, one option visibly selected, one row subtly hovered

Avoid — this is the list that separates expensive dark software from the cliché, and every item is forbidden:
- neon glow, bloom, lens flare, light streaks, or any element emitting light it has no reason to emit
- HUD or sci-fi-movie overlays, wireframe globes, circuit-board patterns, hexagon grids, scan lines, targeting reticles
- floating 3D geometry, abstract blobs, particle fields, purple-to-blue gradient smears
- glassmorphism as decoration, frosted panels stacked over one another, translucency for its own sake
- a second accent colour, rainbow data series, or colour used anywhere hierarchy would do the job
- illustration, concept art, or anything that reads as a design-portfolio mockup rather than shipped software
- laptop, phone or browser mockup frames around the interface
- the application floating as a rounded card, window or panel on a backdrop, with margin or vignette visible around it — there is no backdrop, the interface IS the canvas
- lorem ipsum, placeholder data, or invented UI elements no real product would have
- a blank button, empty swatch or unlabelled control — every element carries its own text
- two panels carrying the same title, or the same information shown twice in different shapes
- a dense grid of small cards; if the content listed above does not fill the screen, give what is there more room rather than inventing more of it
- long sentences anywhere in the interface — every visible string is a label, a name, a number or a short phrase

This screen is dark because software for a decision this considered is dark. It is not dark in order to look futuristic. If the first word a viewer reaches for is "sci-fi", it has failed; the first word should be "expensive".

The navigation, content and data must be internally coherent — they all describe the same business on the same day. A prospect looking at this should think "they already built this for me," not "this is a generic template with my name on it.\""""


_LIGHT_REGISTER = """DESIGN CONSTRAINTS

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

The navigation, metrics, chart and data must be internally coherent — they all describe the same business on the same day. A prospect looking at this should think "they already built this for me," not "this is a generic template with my name on it.\""""


_REGISTERS = {"cinematic": _CINEMATIC_REGISTER, "light": _LIGHT_REGISTER}


def register_id() -> str:
    """Which design register the prompt asks for. Unknown values fall back to
    cinematic rather than raising — a typo in an env var must not take the
    image stage down."""
    return settings.IMAGE_REGISTER if settings.IMAGE_REGISTER in _REGISTERS else "cinematic"


def _design_constraints() -> str:
    """Register + the corner reservation, which is emitted ONLY when the
    watermark is actually going in that corner. The two were independent
    before and drifted: the prompt kept protecting a corner for a mark that
    the compositor had already moved, costing ~12%x17% of every canvas for
    nothing. Pinned in tests/test_registers.py."""
    body = _REGISTERS[register_id()]
    if settings.WATERMARK_STYLE == "corner":
        body += _CORNER_RESERVE
    return body + _OUTPUT_BLOCK


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


def is_tool_screen(spec: UIDemoSpec) -> bool:
    """A screen driven by a selection flow rather than a metrics layout.
    Gated so the concept work can be switched off wholesale and every spec
    renders exactly as it did before."""
    return settings.ENABLE_TOOL_SCREENS and spec.concept.is_tool


def _nav_block(spec: UIDemoSpec) -> str:
    """Sidebar for dashboards, top bar for tools. A selection flow wants its
    full width — the reference screens that do this well (property
    configurators, catalogue explorers) all put navigation across the top and
    spend the reclaimed left edge on the hero."""
    if not spec.navigation:
        return ""
    if is_tool_screen(spec):
        placement = (
            "NAVIGATION (a horizontal bar across the very top of the screen: the product wordmark at the "
            "far left, these items spaced across the middle, a single accented action button at the right; "
            "mark the current screen active)"
        )
    else:
        placement = "NAVIGATION (left sidebar, top to bottom; mark the current screen active)"
    return f"{placement}\n\n" + "\n".join(spec.navigation[:8])


def _hero_block(spec: UIDemoSpec) -> str:
    """The rendered centerpiece. Image models render subjects far better than
    they render dense small text, so a screen built entirely from tables and
    axis labels spends its whole canvas on the model's weakest skill. This
    moves roughly half the canvas onto its strongest — and it is what makes a
    screen look expensive rather than merely tidy."""
    hero = spec.hero
    if not settings.ENABLE_HERO_ASSET or not hero.present:
        return ""

    placement = {
        "left": "filling the left portion of the content area",
        "right": "filling the right portion of the content area",
    }.get(hero.placement, "centred in the content area, with interface on both sides")

    lines = [
        "HERO ASSET — the visual centerpiece, rendered INSIDE the application's content area",
        "",
        f"Subject: {hero.subject}",
    ]
    if hero.treatment:
        lines.append(f"Treatment: {hero.treatment}")
    if hero.caption:
        lines.append(f'Caption to render on it, exactly once: "{hero.caption}"')
    lines.append("")
    lines.append(
        f"Render this as a real, photographic-quality image {placement}, taking roughly half of that area — "
        "the way a property portal shows the building or a configurator shows the car. The product's own "
        "panels and controls sit around it and, where a real product would, slightly over its edges: a small "
        "floating label, a marker, a control resting on top."
    )
    lines.append(
        "It is an IMAGE, not an illustration: correct perspective, real materials, real light. No diagram, no "
        "wireframe, no line drawing, no clip art, no 3D-render-of-a-concept. It carries no text of its own "
        "beyond the caption above. It must be the actual thing this business sells or works on — never a "
        "generic stock scene, never an abstract stand-in."
    )
    return "\n".join(lines)


def _steps_block(spec: UIDemoSpec) -> str:
    """The selection flow that makes a screen a tool instead of an overview."""
    concept = spec.concept
    lines = [
        f"SELECTION FLOW — this screen is a {concept.kind}, not a metrics dashboard. Its structure IS the "
        "flow below: numbered stages the user moves through left to right, each with a small letterspaced "
        "uppercase step label. The chosen option in every stage is unmistakably marked with the accent; the "
        "options not chosen stay legible but recede.",
        "",
    ]
    for i, step in enumerate(concept.steps[:4], start=1):
        lines.append(f"{i}. {step.label}")
        if step.options:
            lines.append("   Options: " + " · ".join(step.options[:8]))
        if step.selected:
            lines.append(f"   Selected: {step.selected}")
        lines.append("")

    if concept.detail and concept.detail.rows:
        lines.append(_panel_block("The panel the selection resolves to; its heading is the title below", concept.detail))
        lines.append("")
    if concept.primary_action:
        lines.append(
            f'PRIMARY ACTION BUTTON: "{concept.primary_action}" — the single most prominent accented '
            "element on the screen."
        )
    if concept.secondary_action:
        lines.append(f'SECONDARY ACTION BUTTON: "{concept.secondary_action}" — quieter, outlined, beneath it.')
    return "\n".join(lines).rstrip()


def _header_stats_block(spec: UIDemoSpec) -> str:
    """KPIs on a tool screen are context, not the subject — a compact strip in
    the page header rather than a row of cards competing with the hero."""
    stats = [f"{k.value} {k.label}".strip() for k in spec.kpis[:3] if k.value or k.label]
    if not stats:
        return ""
    return (
        "HEADER STATS (a compact row at the top-right of the page header — small uppercase labels under "
        "larger numerals, separated by thin vertical rules; NOT cards)\n\n" + "\n".join(stats)
    )


def _ai_layer_block(spec: UIDemoSpec) -> str:
    """AI as an opinion the software formed, not a list of things it did.

    Mutually exclusive with the AI Workstream log by construction — two
    AI-activity modules in one prompt is the exact failure `_merged_ai_entries`
    exists to prevent, and asking the model not to render both does not work.
    """
    ai = spec.ai
    if not settings.ENABLE_AI_LAYER or not ai.present:
        return ""
    lines = [
        "AI MODULE — the ONLY AI element on this screen, given real size and premium treatment. It states "
        "an opinion the software has formed; it is NOT a log, a feed, a task queue or a list of events.",
        "",
        f"Headline: {ai.headline}",
    ]
    if ai.rationale:
        lines.append(f"Reasoning line: {ai.rationale}")
    if ai.confidence:
        lines.append(f"Confidence readout: {ai.confidence}")
    if ai.chips:
        lines.append("Supporting chips: " + " · ".join(ai.chips[:4]))
    lines.append("")
    lines.append(
        "Render the headline large and in the accent, the reasoning as one short quieter line beneath it, and "
        "the confidence as a small precise readout — a compact meter, ring or percentage, not a decorative "
        "gauge. Any chips are small outlined pills. A viewer should see at a glance that the software reached "
        "a conclusion and can say why."
    )
    return "\n".join(lines)


def _content_sections(spec: UIDemoSpec) -> str:
    sections = [
        f"SCREEN\n\n{spec.screen_title}",
    ]
    header_lines = [line for line in (spec.greeting, spec.subheading) if line]
    if header_lines:
        sections.append("HEADER\n\n" + "\n".join(header_lines))
    nav = _nav_block(spec)
    if nav:
        sections.append(nav)

    tool = is_tool_screen(spec)
    ai_module = _ai_layer_block(spec)

    if tool:
        # A tool screen's subject is the flow and the hero; KPIs demote to a
        # header strip and the chart/activity layout does not apply at all.
        stats = _header_stats_block(spec)
        if stats:
            sections.append(stats)
        hero = _hero_block(spec)
        if hero:
            sections.append(hero)
        sections.append(_steps_block(spec))
        if ai_module:
            sections.append(ai_module)
        return "\n\n".join(sections)

    if spec.kpis:
        sections.append(_kpi_block(spec))
    hero = _hero_block(spec)
    if hero:
        sections.append(hero)
    if spec.primary_panel.rows:
        sections.append(_panel_block("PRIMARY PANEL", spec.primary_panel))
    if spec.secondary_panel and spec.secondary_panel.rows and not secondary_panel_is_merged_ai_task_list(spec):
        sections.append(_panel_block("SECONDARY PANEL", spec.secondary_panel))
    chart = _chart_block(spec)
    if chart:
        sections.append(chart)
    if ai_module:
        sections.append(ai_module)
    else:
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
    cinematic = register_id() == "cinematic"
    if spec.business.primary_color:
        stance = (
            "the hue the dark ground is built from, and the source of the single luminous accent"
            if cinematic
            else "accents only, on a light interface"
        )
        lines.append(f"Primary brand color: {spec.business.primary_color} ({stance})")
    if spec.business.secondary_color:
        lines.append(
            f"Secondary color: {spec.business.secondary_color} "
            + ("(structural tints only — never a second accent)" if cinematic else "(sparingly)")
        )
    if spec.style.palette_description and not cinematic:
        # The cinematic register dictates its own palette stance; a stray
        # "light interface, teal accents" from the spec stage would contradict
        # the register in the same prompt.
        lines.append(f"Palette: {spec.style.palette_description}")
    where = (
        "at the far left of the top navigation bar"
        if is_tool_screen(spec)
        else "at the top of the sidebar"
    )
    lines.append(f'The product wordmark "{spec.product.name}" appears small and plain {where}.')
    return "\n".join(lines)


def _task_line(spec: UIDemoSpec) -> str:
    """The opening sentence, and with it the quality reference the model
    reaches for. The reference points are register-specific: naming Linear
    and Stripe while asking for a deep cinematic ground pulls the model back
    toward a light dashboard in the same breath."""
    industry = spec.business.industry or "a local business"
    if register_id() == "light":
        return (
            f"Create a realistic desktop screenshot of a production SaaS application used by {industry} — "
            "bespoke software built specifically for this business by an elite product-design studio. The "
            "quality bar is Linear, Stripe, Arc, Ramp and Vercel at their most polished, with the craft of a "
            "top-tier product-design portfolio piece. It must be real, believable production software — not a "
            "fantasy concept shot — but visually impressive enough that the business owner's reaction is "
            '"you already built this for us?"'
        )
    kind = "software tool" if is_tool_screen(spec) else "software application"
    return (
        f"Create a realistic desktop screenshot of a production {kind} used by {industry} — bespoke software "
        "built specifically for this business. The quality bar is what a top-tier studio delivers to a client "
        "who is not price-sensitive: on the software side Arc, Raycast and Linear's dark surfaces; on the "
        "other side the digital work luxury property developers, private banks and marque automakers "
        "commission. It must be real, believable production software where every element does a job — not a "
        "concept shot — and the business owner's reaction should be "
        '"you already built this for us?"'
    )


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

{_task_line(spec)}{composition_directive}

BUSINESS

{spec.business.name}

SOFTWARE

Product name: {spec.product.name}
Purpose: {spec.product.purpose}
Layout density: {density}

{_content_sections(spec)}

Every visible string above is the EXACT text to render — short labels, names and numbers only. Render each string once, spelled exactly as written. Do not add extra text of your own. The ALL-CAPS section headings above (SCREEN, HEADER, NAVIGATION, HERO ASSET, SELECTION FLOW, HEADER STATS, AI MODULE, KPI CARDS, PRIMARY PANEL, CHART) are instructions to you and must NEVER appear as visible text in the interface.

{_branding_block(spec)}

{_design_constraints()}{_art_direction(spec, archetype_id)}"""


DESIGN_SHEET_PROMPT_VERSION = "design-sheet-v1"


def build_design_sheet_prompt(spec: UIDemoSpec, archetype_id: str | None = None) -> str:
    """W5 experiment: a style board generated BEFORE any screen, then
    attached as the reference for every screen including the anchor.

    The theory being tested: today's consistency comes from the anchor, so
    every follow-up inherits whatever the anchor happened to do — including
    its mistakes — and the anchor itself has no reference at all. A design
    sheet gives all screens one common ancestor that contains no layout to
    copy, only a vocabulary.

    Deliberately NOT a screenshot: it is components on a plain background.
    Handing a model a finished screen as its reference is what makes it
    clone that screen; handing it swatches and a button leaves the layout
    to the screen prompt.
    """
    return f"""TASK

Create a design-system style board for {spec.business.name}, a {spec.business.industry or "local business"} — the one-page reference sheet a product-design studio pins up before building screens. This is NOT an application screen and must contain no dashboard, no sidebar and no page layout.

Lay out, on a plain very-light-grey background, clearly separated and generously spaced:

1. A row of colour swatches as rounded rectangles: the primary brand colour, a darker shade of it, a very pale tint of it, and three small neutral swatches (near-white surface, hairline grey, near-black text).
2. A type scale specimen: one large number in the style KPI values will use ({spec.kpis[0].value if spec.kpis else "1,284"}), one section heading ("{spec.kpis[0].label if spec.kpis else "Revenue"}"), one body line, one small caption line — each rendered once, showing weight and size contrast.
3. Two example cards, empty of data except a short title and one number, showing the exact corner radius, border and shadow every card in this product will use.
4. One small chart fragment — a short line or three bars — showing the data-visualisation styling: stroke weight, gradient fill, gridline colour.
5. Three status pills reading exactly "Done", "In Progress" and "Queued".

BRANDING

Business name: {spec.business.name}
Primary brand colour: {spec.business.primary_color or "#2563EB"}{f" (secondary: {spec.business.secondary_color})" if spec.business.secondary_color else ""}

The mood is light, restrained and premium — the visual language of Linear, Stripe and Ramp. No dark theme, no neon, no glassmorphism, no 3D shapes, no photographs, no mockups of devices.

OUTPUT

A flat, straight-on style board filling the canvas. Label nothing except the strings named above."""


def _continuation_register_line() -> str:
    """The follow-up prompt used to instruct "preserve the overall light,
    restrained look" unconditionally — which fights the cinematic register in
    the same prompt that asks for it, and is the kind of contradiction the
    model resolves by splitting the difference."""
    if register_id() == "light":
        return "Preserve the overall light, restrained, production-software look."
    return (
        "Preserve the deep single-hue ground, the single luminous accent and the same quality of light and "
        "depth — this screen must look photographed in the same room as the attached one."
    )


def build_continuation_prompt(spec: UIDemoSpec, anchor_screen_title: str, archetype_id: str | None = None) -> str:
    """Follow-up screen prompt (version: screen-continuation-v1). Sent WITH the
    selected anchor screenshot attached as a reference image so every screen
    looks like the same product."""
    return f"""TASK

The attached image is the "{anchor_screen_title}" screen of {spec.product.name}, a production software application used by {spec.business.name} ({spec.business.industry}). Create the "{spec.screen_title}" screen of the EXACT SAME application.

Preserve the exact same application design:
- Preserve the navigation exactly as the attached image places it — same position, same wordmark, same items in the same order. Only the active item changes, to {spec.screen_title}.
- Preserve the typography, colors, spacing, panel styling, borders, elevation and background treatment exactly.
- {_continuation_register_line()}
- Only the main content area changes, to the content below.

{_content_sections(spec)}

Every visible string above is the EXACT text to render — short labels, names and numbers only. Render each string once, spelled exactly as written. Do not add extra text of your own. The ALL-CAPS section headings above (SCREEN, HEADER, NAVIGATION, HERO ASSET, SELECTION FLOW, HEADER STATS, AI MODULE, KPI CARDS, PRIMARY PANEL, CHART) are instructions to you and must NEVER appear as visible text in the interface.

{_design_constraints()}{_art_direction(spec, archetype_id)}"""
