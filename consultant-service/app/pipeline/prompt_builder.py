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

import re
from collections.abc import Callable

from app import surfaces
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
# The directives are sentence-case prose and carry no "NAME:" header, for
# the same reason every other block in this file stopped carrying one. The
# session-33 golden set shipped two anchors whose intelligence module was
# titled from the variant's own name: law drew "HERO INTELLIGENCE" and
# retail drew "PREMIUM AI INTELLIGENCE", both on the hero-intelligence
# variant, whose directive opened "COMPOSITION DIRECTION — Hero
# Intelligence:" and went on to ask for "premium, polished treatment".
# The variant's `label` is for humans, the log line and the bake-off matrix;
# it is deliberately not in the text the model reads.
COMPOSITION_VARIANTS = [
    {
        "id": "hero-intelligence",
        "label": "Hero Intelligence",
        "directive": (
            "Build this screen around one dominant chart or one dominant insight module, commanding more "
            "visual weight and space than anything else on the screen. Lay it out as an asymmetric "
            "two-column composition rather than a uniform grid, with the supporting metrics arranged "
            "around that dominant element. Establish a strong, unmistakable top-level hierarchy: this "
            "screen is built around a conclusion, not around raw operations."
        ),
    },
    {
        "id": "command-center",
        "label": "Command Center",
        "directive": (
            "Lay this screen out for someone actively running the business right now — operational and "
            "action-oriented. Favour richer status, workflow and people-related components, a stronger "
            "sense of live activity in progress, over any single dominant visualization; no one element "
            "should dominate the way a single large chart would elsewhere. Use an asymmetric, modular "
            "composition with varied card sizes and shapes arranged with intention, not a uniform grid, "
            "so it reads as a busy, capable place of work."
        ),
    },
    {
        "id": "executive-overview",
        "label": "Executive Overview",
        "directive": (
            "Lay this screen out with fewer, larger, higher-value modules rather than many small cards — "
            "restraint and confidence over density, and the strongest typographic hierarchy of any "
            "layout. Favour synthesized conclusions over raw operational detail. Deliberately avoid a "
            "uniform row of identical small metric boxes; if metrics appear, treat them as part of a "
            "larger module. This should read like a summary a business owner glances at once a day, not "
            "a workbench they live in."
        ),
    },
]

_CORNER_RESERVE = """

Reserve only the immediate bottom-right corner of the canvas (roughly the last 12% of width and 17% of height) clear of text, icon or card content — a real logo is composited into exactly that small corner afterward. No card, list or table may extend into or behind that corner at all, even partially — every element must end with clear margin before that boundary; a card merely hidden behind the logo is still wrong. This is a small protected area, not a design cue: let the surrounding cards and layout fill the rest of the canvas naturally, right up to that boundary, with no large empty gap or dead space beyond what's strictly needed to protect the corner."""

_OUTPUT_BLOCK = """

OUTPUT

A full-bleed desktop application screenshot filling the entire canvas edge to edge. The topmost row of pixels already belongs to the application itself — its own header or navigation starts at the very top of the canvas, with nothing at all above it. No device frame, no browser chrome, no drop shadow around the app, no background visible behind it."""


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
    lines = ["Metric cards:", ""]
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
    # Values as well as labels: ChartSpec drops a series it cannot plot
    # (multi-series dicts, non-numbers) rather than failing the whole spec,
    # and a chart section with labels and no numbers is an invitation to
    # invent them — the same reason a chartless screen gets no chart block.
    if chart is None or not chart.labels or not chart.values:
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
        "The chart — this is the screen's hero element, the single most visually crafted thing on it:\n\n"
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


def active_nav_item(spec: UIDemoSpec) -> str | None:
    """The navigation label this screen actually is, or None when the screen
    has no item of its own.

    Both prompts used to ask for "the current screen marked active"
    unconditionally, and the follow-up prompt went further and named it:
    "Only the active item changes, to {screen_title}". On request 107 the
    navigation was the customer's own four items (Home, Gallery, About,
    Contact) and the follow-up's title was "Schedule" — so the model was
    told to activate an item that did not exist, and it did the only thing
    that instruction allows: it added "Schedule" to the header. Six items
    shipped where the customer had asked for four, and the text-truth gate
    passed the screen, because a gate that checks the strings the spec
    ordered cannot see one it never ordered.

    It is not a rare shape. Every one of the six golden briefs has at least
    one screen whose title is absent from its navigation, and 11 of the 21
    screens shipped on requests 100-106 were in that state; sampled, they
    variously invented an item or highlighted an unrelated one (101's
    Analytics screen marks "Pipeline").

    So the instruction is issued only when it is true. The rest of the
    navigation contract — same items, same order — is unchanged and already
    stated; no new ban is added here, because the defect was a
    contradiction rather than a missing rule (the same lesson as the
    duplicated-navigation fix in _nav_block).

    Session 39 added the other half. Matching a title against the labels
    only ever works when the customer's words happen to be the archetype's
    words; on request 130 the header was Home/Gallery/About/Contact and the
    titles were Dashboard/Analytics/Customers, so no screen was ever told
    what it was and every one of them defaulted to the first item. The spec
    now carries `active_nav`, already validated in ui_spec.py against the
    honoured list and de-duplicated across screens, and it is preferred
    here. The title match stays as the fallback for specs that predate the
    field — including every frozen golden bundle.
    """
    declared = (spec.active_nav or "").strip().lower()
    if declared:
        return next(
            (label for label in spec.navigation[:8] if label.strip().lower() == declared), None
        )
    title = (spec.screen_title or "").strip().lower()
    if not title:
        return None
    return next((label for label in spec.navigation[:8] if label.strip().lower() == title), None)


def _nav_block(spec: UIDemoSpec, *, continuation: bool = False) -> str:
    """Sidebar for dashboards, top bar for tools. A selection flow wants its
    full width — the reference screens that do this well (property
    configurators, catalogue explorers) all put navigation across the top and
    spend the reclaimed left edge on the hero.

    On a CONTINUATION screen the placement is not restated, because the
    anchor already decided it and the anchor is attached to the call. Stating
    it again is how request 68 shipped a screen carrying BOTH: its anchor was
    a tool screen (top bar), its follow-up was a dashboard, and the prompt
    told the model in the same breath to "preserve the navigation exactly as
    the attached image places it" and to draw a "left sidebar". It drew both,
    with the same items in each — the duplicated-navigation defect on DoD
    line 2's list. Navigation placement is a property of the PRODUCT, decided
    once by the anchor, not a property of each screen.
    """
    if not spec.navigation:
        return ""
    active = active_nav_item(spec)
    if continuation:
        # "no item is marked" rather than silence. Session 38 measured 11 of
        # 21 screens with no matching nav item and found they "variously
        # invented an item or highlighted an unrelated one"; request 142's
        # Manage screen highlighted Home, a page it is not. Leaving the
        # clause out does not leave the header alone — the bar gets drawn
        # either way, so the omission is a vacancy the model fills. Closing
        # it positively is the pattern that has worked for every other
        # vacancy in this file.
        marked = (
            f", with {active} marked active" if active
            else ", and no navigation item is marked active on this screen"
        )
        placement = (
            "Navigation items — placed exactly where the attached image places them, in one navigation "
            f"region and no other{marked}"
        )
    elif surfaces.is_public(spec.surface):
        # A public page's navigation is a website header, not app chrome.
        # Without this branch the block asked for a "left sidebar" and the
        # surface block two lines later said "no sidebar" — the pipeline
        # contradicting its own instructions in a single prompt, which is
        # the failure mode the duplicated-navigation and double-CTA fixes
        # were both about. The art pack describes the same bar, so the two
        # now agree.
        marked = (
            f"; mark {active} active" if active
            else "; no item is marked active on this screen"
        )
        placement = (
            "Navigation items (a thin horizontal website header across the very top, over the hero: "
            f"the wordmark at the far left, these items spaced to the right{marked})"
        )
    elif is_tool_screen(spec):
        # No button at the right end of the top bar — because _steps_block
        # already asks for concept.primary_action as "the single most
        # prominent accented element on the screen", and this block used to
        # ask for the SAME string as a second button in the same prompt.
        #
        # Measured, session 38: the defect inspector reported it as a
        # duplicated panel on six of six tool screens in the corpus —
        # "Confirm Allocation" (100), "Confirm Booking" (102), "Add to
        # Order" (103), "Schedule Consultation" (105), "Book This Slot"
        # (106), "View Painting" (108) — and it was right every time. The
        # census that found it had first labelled all six clean, so the
        # instrument caught a defect a person reading the same screens
        # missed.
        #
        # The button's original reason was a real one: the session-33
        # golden set shipped a top-bar button labelled literally "Action",
        # because this block asked for a button and supplied no string. But
        # that argues for not asking for an unnamed button, and asking for
        # a named one turned out to order the CTA twice. Asking for no
        # top-bar button at all satisfies both: nothing to leave unlabelled,
        # nothing to duplicate.
        marked = (
            f"; mark {active} active" if active
            else "; no item is marked active on this screen"
        )
        placement = (
            "Navigation items (a horizontal bar across the very top of the screen: the product wordmark at the "
            f"far left, these items spaced across the middle{marked})"
        )
    else:
        marked = (
            f"; mark {active} active" if active
            else "; no item is marked active on this screen"
        )
        placement = f"Navigation items (left sidebar, top to bottom{marked})"
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
        "The visual centerpiece of this screen, rendered INSIDE the application's content area:",
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
        "beyond the caption above, and no cursor, toolbar, slider, crop handle or other image-editing control anywhere "
        "on or near it. It must be the actual thing this business sells or works on — never a "
        "generic stock scene, never an abstract stand-in."
    )
    return "\n".join(lines)


def _steps_block(spec: UIDemoSpec) -> str:
    """The selection flow that makes a screen a tool instead of an overview."""
    concept = spec.concept
    lines = [
        f"The selection flow this screen is built around. It is a {concept.kind}, not a metrics dashboard, and "
        "its structure IS the flow below: numbered stages the user moves through left to right, each with a "
        "small letterspaced uppercase step label. The chosen option in every stage is unmistakably marked "
        "with the accent; the options not chosen stay legible but recede.",
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
    # Prose, not "LABEL: value" — same reason as the intelligence module.
    if concept.primary_action:
        lines.append(
            f'The main button reads "{concept.primary_action}" and is the single most prominent accented '
            "element on the screen."
        )
    if concept.secondary_action:
        lines.append(f'A quieter outlined button beneath it reads "{concept.secondary_action}".')
    return "\n".join(lines).rstrip()


def is_conversation_screen(spec: UIDemoSpec) -> bool:
    """Gated exactly like is_tool_screen, so the whole shape can be switched
    off and every spec renders as it did before it existed."""
    return settings.ENABLE_TOOL_SCREENS and spec.concept.is_conversation


def _conversation_block(spec: UIDemoSpec) -> str:
    """The message thread that IS the product on an assistant console.

    Written the same way as every other block here: each visible string is
    named and quoted, and nothing that describes the layout is ever a
    string. The two failure modes this shape invites are both known
    classes. A bubble whose text the prompt describes rather than supplies
    ("the customer asks about pricing") gets rendered as that description —
    the scaffolding-renders-as-UI lesson. And an unlabelled composer row is
    a blank control, which is on the defect inspector's list, so it either
    carries the spec's own placeholder or is not asked for at all.
    """
    concept = spec.concept
    lines = [
        "The conversation this screen is built around. It is a live message thread, not a metrics "
        "dashboard and not a numbered flow: the messages below run down the centre of the content "
        "area in order, oldest at the top. Messages from the customer sit on the left in a plain "
        "bubble; messages from the assistant sit on the right in a bubble carrying the accent, each "
        "with a small assistant avatar. Every bubble holds ONLY the exact words given for it.",
        "",
    ]
    for turn in concept.turns[:7]:
        speaker = "Assistant" if str(turn.speaker).strip().lower() == "assistant" else "Customer"
        lines.append(f"{speaker}: {turn.text}")
    lines.append("")

    if concept.detail and concept.detail.rows:
        lines.append(_panel_block(
            "A narrow context rail beside the thread; its heading is the title below", concept.detail,
        ))
        lines.append("")
    if concept.primary_action:
        lines.append(
            f'Beneath the thread sits one message composer row: a single input with the placeholder '
            f'"{concept.primary_action}" and a small accented send button at its right end. The '
            "composer carries no other text."
        )
    if concept.secondary_action:
        lines.append(
            f'Above the composer sits one small outlined suggestion chip reading "{concept.secondary_action}".'
        )
    return "\n".join(lines).rstrip()


def _header_stats_block(spec: UIDemoSpec) -> str:
    """KPIs on a tool screen are context, not the subject — a compact strip in
    the page header rather than a row of cards competing with the hero."""
    stats = [f"{k.value} {k.label}".strip() for k in spec.kpis[:3] if k.value or k.label]
    if not stats:
        return ""
    return (
        "Statistics for the page header (a compact row at its top-right — small uppercase labels under "
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
    # Every string here is quoted and introduced by prose rather than by a
    # "Label: value" line. Request 68's analytics screen rendered the literal
    # text "Reasoning line: Historical patterns suggest resource need" — the
    # prompt's own field label drawn as UI, which is the same defect 227a6e3
    # removed from the hero, chart, KPI and navigation blocks and missed
    # here. A colon-prefixed label sitting immediately before the exact
    # string to render is indistinguishable, to the model, from a caption it
    # is being asked to draw. Asking it not to does not work; that was tried
    # in session 32 and the leaks came from the run carrying the instruction.
    # The module has no title field, and an untitled panel sitting under
    # descriptive prose invites the model to title it FROM that prose. The
    # law cell shipped one card headed "SOFTWARE-FORMED OPINION" and another
    # headed "ONLY AI INTELLIGENCE" — both lifted from the sentence that
    # used to open this block ("the ONLY AI element on this screen… it
    # states an opinion the software has formed"). Removing the field labels
    # was not enough; the description itself was being read as a caption.
    #
    # So the vacancy is closed rather than the behaviour forbidden — in two
    # stages. Session 33 declared the headline the topmost line and said
    # "the module has no separate title"; the re-run invented new titles
    # anyway, because a vacancy forbidden is still a vacancy. ui-spec-v3
    # therefore gives the module a REAL title (spec.ai.title), a product
    # label the spec stage writes, rendered as an exact string like every
    # other label — nothing left to be guessed. Briefs frozen before v3
    # have no title, and for them the block below is byte-identical to the
    # session-33 wording, so briefs-v2 remains a valid control arm.
    # Bare strings on their own lines, the same shape the metric-card and
    # panel blocks use — and specifically NOT wrapped in quotation marks. The
    # first attempt at this rewrite quoted each value to delimit it, and the
    # salon anchor drew the delimiters: its headline shipped reading
    # «"Recommend Add-on: Deep Conditioning"», quotation marks included.
    # Anything placed around a string to mark it out is itself a candidate
    # for being drawn. The order is stated once, in prose, above.
    if ai.title:
        intro = [
            "One module on this screen is given real size and premium treatment. Its topmost line is the "
            "small module label below, set as a quiet kicker; the large accent headline sits directly "
            "under it, and nothing whatever is written above the label.",
        ]
        order = ["the module label", "the headline"]
        values = [ai.title, ai.headline]
    else:
        intro = [
            "One module on this screen is given real size and premium treatment. Its topmost line is the "
            "headline below, set large and in the accent; the module has no separate title, and nothing "
            "whatever is written above that headline.",
        ]
        order = ["the headline"]
        values = [ai.headline]
    if ai.rationale:
        order.append("one short, quieter line beneath it")
        values.append(ai.rationale)
    if ai.confidence:
        order.append("a confidence readout")
        values.append(ai.confidence)
    if ai.chips:
        order.append("a row of small outlined pills")
        values.append(" · ".join(ai.chips[:4]))
    intro.append("The lines below are, in order: " + ", then ".join(order) + ".")

    tail = (
        "Render the confidence as a small precise readout — a compact meter, ring or percentage, not a "
        "decorative gauge. This is the one place AI appears on the screen, and it is not a log, a feed, a "
        "task queue or a list of events."
    )
    return "\n".join(intro) + "\n\n" + "\n".join(values) + "\n\n" + tail


_OPERATOR_GREETING = re.compile(
    r"^\s*(good\s+(morning|afternoon|evening)|welcome\s+back|hi|hello|hey)\b",
    re.IGNORECASE,
)


def public_headline(spec: UIDemoSpec) -> str:
    """The hero headline for a public page — never the owner's greeting.

    `greeting` is written for a logged-in dashboard, and on request 141 all
    three public screens rendered "Good morning, Jeanne" as their headline:
    the landing page of an artist's website addressing the artist. The
    ui_spec prompt now asks for a visitor-facing headline on public screens,
    but a prompt is a request and this is the promise — a greeting that
    still arrives addressed to the owner is dropped rather than drawn, and
    the business's own name is a headline that can never be wrong.
    """
    greeting = (spec.greeting or "").strip()
    if greeting and not _OPERATOR_GREETING.match(greeting):
        return greeting
    return spec.business.name or spec.product.name


def _marketing_block(spec: UIDemoSpec) -> str:
    """A public landing page: the screen a visitor lands on.

    Built from the same spec fields as every other screen — no new model
    output was added for this. The hero becomes the full-bleed image
    instead of a panel inside a content area, the KPIs become proof points
    instead of metric cards, and the concept's primary_action becomes the
    one call to action. Reusing the fields is what keeps this a new SHAPE
    rather than a new pipeline.

    Every line names a string the spec supplied. Nothing here describes an
    element without giving its words, because a described-but-unnamed
    element is how "a single accented action button at the right" shipped
    as a button labelled "Action".
    """
    concept = spec.concept
    lines = [
        "This screen is the PUBLIC LANDING PAGE of the website — what a visitor sees "
        "when they arrive, not an admin tool. No KPI cards, no chart, no data table, "
        "no sidebar.",
        "",
    ]
    if spec.hero.present:
        lines.append(f"A full-bleed hero image across the top. Subject: {spec.hero.subject}")
        if spec.hero.treatment:
            lines.append(f"Treatment: {spec.hero.treatment}")
        lines.append("")
    headline = public_headline(spec)
    lines.append(f"Over the hero, the headline reads exactly: {headline}")
    if spec.subheading:
        lines.append(f"Directly beneath it, one supporting line reading exactly: {spec.subheading}")
    if concept.primary_action:
        lines.append(
            f"Below that, one accented button — the single most prominent element on the "
            f"page — reading exactly: {concept.primary_action}"
        )
    if concept.secondary_action:
        lines.append(f"Beside it, one quieter outlined button reading exactly: {concept.secondary_action}")

    points = [kpi for kpi in spec.kpis[:3] if kpi.label]
    if points:
        lines.append("")
        lines.append(
            "Below the hero, a row of three short value points, each one heading and "
            "one figure, reading exactly:"
        )
        for kpi in points:
            lines.append(f"{kpi.label} — {kpi.value}")

    featured = _catalog_items(spec)[:4]
    if featured:
        lines.append("")
        lines.append(
            "Below those, a strip of featured work — one image each, with its title "
            "printed beneath, reading exactly:"
        )
        lines.extend(featured)
    return "\n".join(lines)


def _catalog_items(spec: UIDemoSpec) -> list[str]:
    """Item captions for a public grid, taken from whichever panel the spec
    actually filled. A gallery's items are the same rows a back-office
    screen would have listed in a table; only the way they are drawn
    changes."""
    rows = list(spec.primary_panel.rows or [])
    if not rows and spec.secondary_panel:
        rows = list(spec.secondary_panel.rows or [])
    captions: list[str] = []
    for row in rows:
        values = [str(v).strip() for v in row.values() if str(v).strip()]
        if values:
            captions.append(" · ".join(values[:2]))
    return captions


def _catalog_block(spec: UIDemoSpec) -> str:
    """A public catalogue page: the grid a visitor browses."""
    # Six, not eight, and the count stated. Request 142's gallery was given
    # four captions and drew roughly eight cards, overflowing the canvas so
    # the bottom row was sliced off by the edge — a clipping defect the
    # model produced by padding a list it was not told the length of. A
    # countable instruction is the fix that has worked everywhere else in
    # this file.
    items = _catalog_items(spec)[:6] or [spec.product.name]
    lines = [
        "This screen is a PUBLIC CATALOGUE PAGE of the website — a visitor browsing "
        "what is on offer, not an admin tool. No KPI cards, no chart, no data table.",
        "",
        f"A grid of EXACTLY {len(items)} cards fills the content area — no more and no "
        "fewer, and no card's caption repeated on a second card. Each card is a single "
        "image of that item with its caption printed beneath it, and the first card is "
        "drawn larger than the rest. Every card and every caption is fully visible "
        "inside the canvas; the grid must end well clear of the bottom edge rather than "
        "running past it. The cards read exactly:",
    ]
    lines.extend(items)
    # No separate "featured card" paragraph. Two paragraphs describing a
    # card is two cards, however the second one is worded: request 143
    # repeated "Mountain Retreat · Mixed Media" to fill a fifth slot, and
    # 144 repeated "Golden Sunset · Oil Landscapes" even after the sentence
    # was rewritten to say "not an additional one". The emphasis is folded
    # into the single list instruction above instead, where there is
    # nothing for it to be counted separately from. The hero is dropped
    # entirely on a catalogue page — each card's image IS its item, so a
    # separate hero subject only ever described a seventh thing.

    filters = [step for step in spec.concept.steps if step.options]
    if filters:
        step = filters[0]
        chosen = step.selected or step.options[0]
        lines.append("")
        lines.append(
            "Above the grid, one row of category filter chips reading exactly: "
            + ", ".join(step.options[:5])
        )
        lines.append(f"The chip reading {chosen} is the selected one.")
    return "\n".join(lines)


# Which block draws which surface. Registered here rather than named in
# surfaces.py because a function is not data, and importing prompt_builder
# from the registry would be a cycle.
#
# `None` means "the pre-existing branches below decide" — back_office
# screens still choose between the conversation, tool and dashboard shapes
# on `concept.kind`, which is a distinction WITHIN a surface rather than
# between surfaces. Mapping it to None rather than omitting it is what lets
# a completeness test insist every registered surface has an entry, so a
# new surface cannot be added without someone deciding how it is drawn.
SURFACE_RENDERERS: dict[str, "Callable[[UIDemoSpec], str] | None"] = {
    surfaces.BACK_OFFICE: None,
    surfaces.CONVERSATION: None,
    surfaces.MARKETING: _marketing_block,
    surfaces.CATALOG: _catalog_block,
}


def _content_sections(spec: UIDemoSpec, *, continuation: bool = False) -> str:
    sections = [
        f"The screen to draw:\n\n{spec.screen_title}",
    ]
    header_lines = [line for line in (spec.greeting, spec.subheading) if line]
    if header_lines:
        sections.append("Page header text:\n\n" + "\n".join(header_lines))
    nav = _nav_block(spec, continuation=continuation)
    if nav:
        sections.append(nav)

    tool = is_tool_screen(spec)
    ai_module = _ai_layer_block(spec)

    # Surface dispatch comes first: a public page is a different shape of
    # screen, not a dashboard with different data, so none of the KPI /
    # chart / panel / activity blocks below apply to it. Screens with no
    # surface — every spec frozen before session 39 — resolve to
    # back_office, whose renderer is None, and fall through to exactly the
    # branches that existed before.
    #
    # A registry rather than an if/elif chain, because the chain this
    # replaced read "if public: if MARKETING else CATALOG" — a third public
    # surface would have rendered silently as a catalogue. A missing
    # renderer is now a test failure instead of a wrong screen.
    renderer = SURFACE_RENDERERS.get(surfaces.resolve(spec.surface))
    if renderer is not None:
        # No AI module on a public page. _ai_layer_block describes "AI as a
        # first-class module" — a titled panel with a confidence ring and
        # chips — and on request 141 the image model drew it exactly that
        # way: a detached card floating on the backdrop beside the page,
        # on all three screens. A visitor does not see the business's
        # internal intelligence, and the block has no composition for a
        # page that is not a dashboard.
        sections.append(renderer(spec))
        return "\n\n".join(sections)

    if is_conversation_screen(spec):
        # Same shape as the tool branch and for the same reason: the thread
        # is the subject, so KPIs demote to a header strip and the
        # chart/panel/activity layout does not apply. No hero either — the
        # conversation IS the centrepiece, and a photograph beside it would
        # compete with the one thing this screen exists to show.
        stats = _header_stats_block(spec)
        if stats:
            sections.append(stats)
        sections.append(_conversation_block(spec))
        if ai_module:
            sections.append(ai_module)
        return "\n\n".join(sections)

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
        sections.append(_panel_block("Main list panel:", spec.primary_panel))
    if spec.secondary_panel and spec.secondary_panel.rows and not secondary_panel_is_merged_ai_task_list(spec):
        sections.append(_panel_block("Secondary list panel:", spec.secondary_panel))
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
        "Branding:",
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
    if is_tool_screen(spec) or surfaces.is_public(spec.surface):
        # Public pages and tool screens both carry a top bar. Saying
        # "sidebar" here while the surface block bans one is the same
        # self-contradiction _nav_block used to carry.
        where = "at the far left of the top navigation bar"
    else:
        where = "at the top of the sidebar"
    lines.append(f'The product wordmark "{spec.product.name}" appears small and plain {where}.')
    return "\n".join(lines)


def _task_line(spec: UIDemoSpec) -> str:
    """The opening sentence, and with it the quality reference the model
    reaches for. The reference points are register-specific: naming Linear
    and Stripe while asking for a deep cinematic ground pulls the model back
    toward a light dashboard in the same breath."""
    industry = spec.business.industry or "a local business"
    if surfaces.is_public(spec.surface):
        # A public page is not "a production software application", and
        # opening the prompt by calling it one is the single strongest pull
        # back toward the dashboard the rest of this branch is trying to
        # avoid. The quality references change with it: naming Linear and
        # Ramp asks for app chrome on a page that must not have any.
        # "as a visitor sees it in their browser" is what request 141's
        # anchor obeyed: it drew the page as a chromeless window floating on
        # a backdrop, because a browser was named and the OUTPUT block
        # forbids browser chrome. Both follow-ups then inherited that
        # composition from the anchor, so one word in this sentence cost
        # every screen in the run. Name the page, never the thing it is
        # viewed in.
        return (
            f"Create a realistic screenshot of the PUBLIC WEBSITE of {spec.business.name}, "
            f"a {industry} — the page itself as a visitor reads it, not an admin tool. The page "
            "fills the entire canvas edge to edge: it is not a window, not a card, not a floating "
            "panel, and there is no backdrop, margin or surrounding surface visible anywhere "
            "around it. The quality bar is the site an elite design studio builds for a client who "
            "is not price-sensitive: the editorial restraint of a serious gallery or fashion "
            "house's own site, imagery doing the work and interface staying out of its way. Real, "
            "believable production web design — not a concept shot, and not a template with a name "
            "dropped in."
        )
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

Every visible string above is the EXACT text to render — short labels, names and numbers only. Render each string once, spelled exactly as written. Do not add extra text of your own. The lines above that describe what to draw ("The visual centerpiece...", "Metric cards:", "Navigation items...", and so on) are instructions to you, not labels: never draw them, and never draw a heading above an element unless a heading is given as one of the exact strings.

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
    active = active_nav_item(spec)
    active_clause = f" Only the active item changes, to {active}." if active else ""
    return f"""TASK

The attached image is the "{anchor_screen_title}" screen of {spec.product.name}, a production software application used by {spec.business.name} ({spec.business.industry}). Create the "{spec.screen_title}" screen of the EXACT SAME application.

Preserve the exact same application design:
- Preserve the navigation exactly as the attached image places it — same position, same wordmark, same items in the same order.{active_clause}
- Preserve the typography, colors, spacing, panel styling, borders, elevation and background treatment exactly.
- {_continuation_register_line()}
- Only the main content area changes, to the content below.

{_content_sections(spec, continuation=True)}

Every visible string above is the EXACT text to render — short labels, names and numbers only. Render each string once, spelled exactly as written. Do not add extra text of your own. The lines above that describe what to draw ("The visual centerpiece...", "Metric cards:", "Navigation items...", and so on) are instructions to you, not labels: never draw them, and never draw a heading above an element unless a heading is given as one of the exact strings.

{_design_constraints()}{_art_direction(spec, archetype_id)}"""
