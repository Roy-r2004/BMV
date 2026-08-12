"""W2 — per-archetype art-direction packs.

Today's prompt carries the DATA plus one brand color and a generic set of
design constraints. That is enough to get "looks like real software" and
not enough to get "looks like it was designed for us": every archetype
comes back with the same card-and-KPI vocabulary because nothing in the
prompt distinguishes a clinic's operations board from a roastery's
analytics screen beyond the words inside the cards.

A pack is a small design system per archetype — a named type pairing, a
density/spacing stance, chart styling, and an EXACT hex palette derived
here in code from the client's brand color. Versioned, because the whole
point is being able to say which pack produced which screenshot.

Why the palette is computed rather than described: "use the brand color
generously" is a suggestion an image model interprets differently every
call. Nine concrete hex values are an instruction. The derivation is plain
HSL arithmetic (colorsys, stdlib) — deterministic, testable, and free.

The neutrals and the semantic colors are deliberately NOT derived from the
brand: a red that means "overdue" must read as red whatever the client's
logo looks like, and tinting the greys makes screenshots look themed
rather than designed.
"""

import colorsys

from app.ui_spec import UIDemoSpec

ART_PACK_VERSION = "art-pack-v1"

# Fixed across every pack. Real production SaaS is built on near-neutral
# surfaces with one strong accent; deriving these from the brand is what
# makes generated UI look like a colored template.
_NEUTRALS = {
    "canvas": "#F8F9FB",
    "surface": "#FFFFFF",
    "border": "#E5E7EB",
    "text_primary": "#111827",
    "text_secondary": "#6B7280",
}
_SEMANTIC = {
    "positive": "#059669",
    "negative": "#DC2626",
    "warning": "#D97706",
}

_FALLBACK_BRAND = "#2563EB"

# The palette reaches the PROMPT as prose, and the exact hex values reach
# the compositor and the tests instead. Measured twice on 2026-08-11:
#
#   attempt 1, a plain "positive: #059669" list -> the screenshot rendered
#   "#059669" as a green pill beside a KPI and again as a status chip.
#   attempt 2, the same list rewritten as roles ("Negative delta text and
#   alert pills - #DC2626") plus an explicit "no hex code may appear as
#   visible text" prohibition, twice -> the screenshot rendered "#DC2626"
#   as the Risk level pill. Naming the UI element a color belongs to told
#   the model exactly where to WRITE it.
#
# An image model renders strings it is given; a 14-line block of them is an
# invitation whatever the surrounding instruction says. The one hex the
# prompt has always carried (the brand color, in the BRANDING block) has
# never leaked, so the rule is: at most that one, and the rest described.
_ROLE_PROSE = (
    "Build the whole screen from one brand color and a near-neutral base. The brand color owns the "
    "active nav item, the focal metric, the primary button and the main chart line; a much darker "
    "shade of the SAME hue carries hover and pressed states and the emphasized bar or data point; a "
    "very pale tint of it fills the active nav item, the selected row and the area under the chart. "
    "A second categorical series may use one analogous hue shifted around the wheel from the brand "
    "color — never a new unrelated color. Everything else is neutral: a very light grey page canvas "
    "behind white cards, hairline grey borders and gridlines, near-black primary text, mid-grey "
    "secondary text and axis ticks. Deltas and status pills are the only other colors on the screen "
    "— a restrained green for positive and done, a restrained red for negative and overdue, a "
    "restrained amber for pending — and they keep those meanings regardless of the brand color, "
    "which is never used to tint the neutrals."
)


def _hex_to_rgb(value: str) -> tuple[float, float, float]:
    value = (value or "").strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        raise ValueError(f"not a hex color: {value!r}")
    return tuple(int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))


def _rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02X}" for c in rgb)


def _shift(hex_color: str, *, lightness: float | None = None, saturation_scale: float = 1.0,
           hue_turn: float = 0.0) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    h = (h + hue_turn) % 1.0
    s = max(0.0, min(1.0, s * saturation_scale))
    if lightness is not None:
        l = max(0.0, min(1.0, lightness))
    return _rgb_to_hex(colorsys.hls_to_rgb(h, l, s))


def _relative_luminance(hex_color: str) -> float:
    """WCAG relative luminance. HLS lightness is the wrong measure here: a
    pale yellow (#F5D142) sits at lightness 0.61 — apparently mid-range —
    while being far too bright to put white text on."""
    channels = []
    for channel in _hex_to_rgb(hex_color):
        channels.append(channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_with_white(hex_color: str) -> float:
    return 1.05 / (_relative_luminance(hex_color) + 0.05)


def derive_palette(primary: str | None, secondary: str | None = None) -> dict[str, str]:
    """Fourteen exact hex values from the client's brand color.

    A brand color too bright to sit behind white text is darkened for the
    `primary` role rather than used as-is: a #F5D142 "primary" produces
    illegible buttons, and the model then either ignores the instruction
    (losing the brand) or obeys it (shipping the mess). Darkened just
    enough to clear 3:1 against white — the brand stays recognisable.
    """
    try:
        base = _rgb_to_hex(_hex_to_rgb(primary or _FALLBACK_BRAND))
    except ValueError:
        base = _FALLBACK_BRAND

    usable = base
    r, g, b = _hex_to_rgb(base)
    _, lightness, _ = colorsys.rgb_to_hls(r, g, b)
    while _contrast_with_white(usable) < 3.0 and lightness > 0.08:
        lightness -= 0.04
        usable = _shift(base, lightness=lightness)

    try:
        accent = _shift(secondary, lightness=0.42) if secondary else _shift(usable, hue_turn=0.083)
    except ValueError:
        accent = _shift(usable, hue_turn=0.083)

    return {
        "primary": usable,
        "primary_dark": _shift(usable, lightness=0.30),
        "primary_tint": _shift(usable, lightness=0.93, saturation_scale=0.85),
        "accent": accent,
        "chart_series_2": _shift(usable, hue_turn=0.055, lightness=0.55),
        "chart_series_3": _shift(usable, hue_turn=-0.055, lightness=0.62, saturation_scale=0.8),
        **_NEUTRALS,
        **_SEMANTIC,
    }


# Per-archetype design systems. Each names a type pairing, a density stance
# and the chart treatment that archetype's hero visualization should get.
# Kept short on purpose: a prompt section that runs longer than the data it
# describes starts competing with it for the model's attention.
PACKS: dict[str, dict[str, str]] = {
    "operations-dashboard": {
        "label": "Operations",
        "typography": (
            "Inter (or a near-identical grotesque) throughout. Section titles 18-20px semibold, "
            "KPI values 30-34px bold with TABULAR figures so digits align in a column, labels "
            "12-13px medium in the secondary text color, all-caps only for small table headers."
        ),
        "density": (
            "Comfortable-dense: 24px card padding, 16px gutters, 8px vertical rhythm inside lists. "
            "Rows in the schedule/job list are 44-48px tall so the list reads as scannable work, "
            "not a spreadsheet."
        ),
        "chart": (
            "One area chart with a soft vertical gradient fading to transparent, 2px line, "
            "emphasized end point, horizontal gridlines only in the border color, no vertical "
            "gridlines, no chart border."
        ),
        "signature": (
            "The operational signature: a today-first hierarchy. The schedule or job list is the "
            "widest single module, status is carried by small filled pills rather than icons alone, "
            "and each person in a list has a colored initial avatar."
        ),
    },
    "crm-dashboard": {
        "label": "CRM",
        "typography": (
            "Inter for the interface with a slightly tighter tracking on headings; names rendered "
            "15px semibold — people are the primary object on this screen and should read as such. "
            "KPI values 30-34px bold, tabular figures. Deal/matter values in tabular figures too."
        ),
        "density": (
            "Roomier than an operations board: 28px card padding, 20px gutters, list rows 52-56px "
            "so an avatar, a name, a tag and a value sit comfortably on one line."
        ),
        "chart": (
            "One bar chart with rounded 4px bar caps in the primary color, the current period bar "
            "in the darker primary, value labels above the bars, horizontal gridlines only."
        ),
        "signature": (
            "The relationship signature: every person has a colored initial avatar; lead source and "
            "stage are outlined tags, not filled pills; one row shows a subtle hover state with a "
            "quick-action affordance revealed."
        ),
    },
    "analytics-dashboard": {
        "label": "Analytics",
        "typography": (
            "A number-forward pairing: Inter for labels and interface, and genuinely large tabular "
            "figures for metrics — hero metric 40-46px bold, supporting KPIs 28-32px. Units and "
            "deltas 12px, set beside the number rather than under it."
        ),
        "density": (
            "Chart-led and calm: 28px card padding, generous 24px gutters, fewer modules than an "
            "operations board. The hero chart occupies at least the width of two KPI cards and a "
            "third of the canvas height."
        ),
        "chart": (
            "The hero is a line/area chart with a smooth 2.5px curve, gradient fill, a dashed "
            "vertical marker on the peak with a floating value badge, axis ticks in the secondary "
            "text color, and the y-axis unit set horizontally above the axis, never rotated. "
            "Secondary series use the two chart-series colors, never new hues."
        ),
        "signature": (
            "The analytics signature: a comparison is always visible — a delta chip beside every "
            "metric and a period label on the chart, so no number appears without context."
        ),
    },
    "scheduling-dashboard": {
        "label": "Scheduling",
        "typography": (
            "Inter throughout; time labels 12px tabular in the secondary text color, appointment "
            "titles 13-14px medium, day headers 13px semibold with the date in the secondary color."
        ),
        "density": (
            "Grid-first: an even 7-column week with 1px border-color separators, appointment blocks "
            "with 8px padding and 6px radius, 12-16px between stacked blocks."
        ),
        "chart": (
            "If a chart appears at all it is a compact utilization bar strip, not a hero — the "
            "calendar grid is the hero on this archetype."
        ),
        "signature": (
            "The scheduling signature: appointment blocks tinted by type using the primary tint and "
            "accent at low opacity with a 3px left border in the full color; the current time drawn "
            "as a thin accent-colored line across today's column."
        ),
    },
    "assistant-console": {
        "label": "Assistant",
        "typography": (
            "Inter throughout; message text 14-15px regular with generous 1.5 line height — this is "
            "the only screen in the set whose subject is sentences, and it has to read like a real "
            "conversation. Thread names 14px medium, timestamps 12px in the secondary text color, "
            "KPI values 26-30px bold tabular in the strip above."
        ),
        "density": (
            "Thread-first: the conversation column is the widest module and holds the centre, with "
            "20px between bubbles, 14-16px bubble padding and a 16px radius rounded on three corners. "
            "Everything else on the screen is quieter and narrower than it is."
        ),
        "chart": (
            "No hero chart on the conversation screen; the volume story lives on the analytics screen "
            "as a bar chart with rounded caps and horizontal gridlines only."
        ),
        "signature": (
            "The assistant signature: the assistant's bubbles carry the accent and a small circular "
            "avatar, the customer's stay in the surface color with no avatar, and one quiet 'read' or "
            "delivered timestamp sits under the most recent bubble. The composer is a single rounded "
            "input with an accented send button — never a multi-line form."
        ),
    },
    "pipeline-dashboard": {
        "label": "Pipeline",
        "typography": (
            "Inter throughout; column headers 13px semibold uppercase with a count chip beside them, "
            "card titles 14px medium, values 14px tabular semibold."
        ),
        "density": (
            "Board-first: 4 equal columns with 16px gutters on the canvas color, cards with 16px "
            "padding, 12px between cards, each card 3-4 lines tall at most."
        ),
        "chart": (
            "No hero chart on the board screen; value is carried by per-column totals in the column "
            "headers."
        ),
        "signature": (
            "The pipeline signature: each column header carries a small colored dot and a count; "
            "cards carry one tag and one value; one card is lifted with a slightly stronger shadow "
            "as though just dropped."
        ),
    },
}


def pack_for(archetype_id: str | None) -> dict[str, str] | None:
    return PACKS.get(archetype_id or "")


def build_art_direction(spec: UIDemoSpec, archetype_id: str | None) -> str:
    """The ART DIRECTION prompt section, or "" when the archetype has no pack
    (so an unpacked archetype renders exactly as it does today)."""
    pack = pack_for(archetype_id)
    if pack is None:
        return ""

    # derive_palette() is still the source of truth for these colors — the
    # W4 compositor and the deck use its exact values. It is only the
    # PROMPT that gets prose instead of hex.
    palette = derive_palette(spec.business.primary_color, spec.business.secondary_color)

    # The chart treatment only ships when this screen actually has chart
    # data. A schedule or kanban screen handed "one area chart with a soft
    # gradient" is being invited to invent a module the spec never asked
    # for — the exact failure the prompt spends a paragraph forbidding.
    chart_section = ""
    if spec.chart is not None and spec.chart.labels:
        chart_section = f"\n\nCHART TREATMENT\n{pack['chart']}"

    return f"""ART DIRECTION — {pack['label']} pack ({ART_PACK_VERSION})

COLOR
{_ROLE_PROSE}

TYPOGRAPHY
{pack['typography']}

SPACING AND DENSITY
{pack['density']}{chart_section}

WHAT MAKES THIS SCREEN ITS OWN KIND
{pack['signature']}

The interface is light. Not a dark theme, not a "dark mode toggle" — one light interface, rendered with the confidence of a product team that chose it.

Nothing in this ART DIRECTION section is text to render. It describes how the screen looks; none of its words appear anywhere in the image."""
