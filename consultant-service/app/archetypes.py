"""The small, reusable set of screenshot archetypes.

Personalization comes from the UIDemoSpec's business-specific data and
terminology — NOT from per-industry templates. The archetype only decides
layout shape: which screens to produce, what panels each screen carries,
and how dense it should feel. Keep this list short and strong; the
ui_spec LLM stage picks the best one per business.
"""

# Each screen entry describes the layout skeleton the ui_spec LLM must fill
# with business-specific data. The first screen is the visual anchor —
# generated first, then used as the style reference for the rest.
ARCHETYPES: dict[str, dict] = {
    "operations-dashboard": {
        "label": "Operations Dashboard",
        "when": (
            "day-to-day service operations: clinics, salons, repair shops, home services — "
            "businesses living in today's schedule and job list"
        ),
        "screens": [
            {
                "screen_type": "dashboard",
                "layout": "greeting header, 4 KPI cards, today's schedule list (primary), pipeline/follow-ups (secondary), recent activity feed",
                "chart": None,
            },
            {
                "screen_type": "schedule",
                "layout": "weekly calendar grid with short appointment blocks (name + service + time), one small KPI strip above",
                "chart": None,
            },
            {
                "screen_type": "analytics",
                "layout": "one clear bar chart of this week's volume, 3 KPI cards, a short breakdown table",
                "chart": "bar",
            },
        ],
    },
    "scheduling-dashboard": {
        "label": "Scheduling Dashboard",
        "when": (
            "appointment-first businesses where the calendar IS the business: "
            "studios, coaches, classes, bookings"
        ),
        "screens": [
            {
                "screen_type": "schedule",
                "layout": "large weekly calendar grid as the hero, short appointment blocks, small KPI strip (bookings today, utilization, no-shows)",
                "chart": None,
            },
            {
                "screen_type": "dashboard",
                "layout": "greeting header, 4 KPI cards, upcoming bookings list (primary), waitlist (secondary), recent activity",
                "chart": None,
            },
            {
                "screen_type": "analytics",
                "layout": "line chart of bookings per day, 3 KPI cards, top-services table",
                "chart": "line",
            },
        ],
    },
    "crm-dashboard": {
        "label": "CRM Dashboard",
        "when": (
            "relationship businesses tracking people over time: agencies, law firms, "
            "consultants, B2B services, memberships"
        ),
        "screens": [
            {
                "screen_type": "dashboard",
                "layout": "greeting header, 4 KPI cards, new leads list (primary), follow-ups due (secondary), recent activity feed",
                "chart": None,
            },
            {
                "screen_type": "pipeline",
                "layout": "kanban board with 3-4 short-named stage columns, 2-3 compact cards each (name + value + tag)",
                "chart": None,
            },
            {
                "screen_type": "analytics",
                "layout": "bar chart of leads per week, 3 KPI cards, source-breakdown table",
                "chart": "bar",
            },
        ],
    },
    "analytics-dashboard": {
        "label": "Analytics Dashboard",
        "when": (
            "numbers-first businesses: retail, e-commerce, restaurants — "
            "where sales/volume trends matter more than a schedule"
        ),
        "screens": [
            {
                "screen_type": "analytics",
                "layout": "hero line chart of revenue/volume, 4 KPI cards, top-items table (primary)",
                "chart": "line",
            },
            {
                "screen_type": "dashboard",
                "layout": "greeting header, 4 KPI cards, today's orders/sales list (primary), low-stock or alerts (secondary), activity feed",
                "chart": None,
            },
            {
                "screen_type": "customers",
                "layout": "customer list with avatar initials, segment tags and short stats, one small KPI strip",
                "chart": None,
            },
        ],
    },
    "pipeline-dashboard": {
        "label": "Pipeline Dashboard",
        "when": (
            "project/job-pipeline businesses: contractors, renovations, custom orders, "
            "long-running engagements moving through stages"
        ),
        "screens": [
            {
                "screen_type": "pipeline",
                "layout": "kanban board hero with 4 short-named stage columns, 2-3 compact cards each (project + value + tag), small KPI strip",
                "chart": None,
            },
            {
                "screen_type": "dashboard",
                "layout": "greeting header, 4 KPI cards, active projects list (primary), pending estimates (secondary), activity feed",
                "chart": None,
            },
            {
                "screen_type": "analytics",
                "layout": "bar chart of jobs completed per month, 3 KPI cards, revenue-by-stage table",
                "chart": "bar",
            },
        ],
    },
}

DEFAULT_ARCHETYPE = "operations-dashboard"


def get_archetype(archetype_id: str | None) -> tuple[str, dict]:
    """Resolves an archetype id (falling back to the default) — never raises,
    an unknown/missing id from the LLM must not fail the pipeline."""
    if archetype_id and archetype_id in ARCHETYPES:
        return archetype_id, ARCHETYPES[archetype_id]
    return DEFAULT_ARCHETYPE, ARCHETYPES[DEFAULT_ARCHETYPE]


def catalog_for_prompt() -> str:
    """Short, LLM-readable catalog used by ui_spec.j2 for archetype selection."""
    lines = []
    for aid, arch in ARCHETYPES.items():
        screens = " -> ".join(s["screen_type"] for s in arch["screens"])
        lines.append(f"- {aid}: best for {arch['when']}. Screens: {screens}")
    return "\n".join(lines)
