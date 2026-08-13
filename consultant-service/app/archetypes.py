"""The small, reusable set of screenshot archetypes.

Personalization comes from the UIDemoSpec's business-specific data and
terminology — NOT from per-industry templates. The archetype only decides
layout shape: which screens to produce, what panels each screen carries,
and how dense it should feel. Keep this list short and strong; the
ui_spec LLM stage picks the best one per business.

Each screen may declare a `surface` (see app/surfaces.py) — what CLASS of
software surface it is, which routes both the prompt shape that draws it
and the rubric that scores it. Screens that do not declare one are
back-office screens, which is every screen this pipeline had before
session 39.
"""

from app import surfaces

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
    "assistant-console": {
        "label": "AI Assistant Console",
        "when": (
            "businesses whose product IS the assistant: chatbots, AI receptionists, support "
            "copilots — where the conversation is the thing being shown, not a feature inside "
            "something else"
        ),
        "screens": [
            {
                "screen_type": "conversations",
                "surface": surfaces.CONVERSATION,
                "layout": "thread list rail (name + last line + time), one open conversation as the hero, small KPI strip above",
                "chart": None,
            },
            {
                "screen_type": "analytics",
                "layout": "bar chart of conversations handled per day, 3 KPI cards, top-intents breakdown table",
                "chart": "bar",
            },
            {
                "screen_type": "knowledge",
                "layout": "knowledge-source list with short titles and status tags (primary), assistant settings rows (secondary), small KPI strip",
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
    # The first archetype whose screens are not all operator screens.
    #
    # Every archetype above answers "what software does this business RUN".
    # For a business whose product faces the public — an artist, a
    # restaurant, a shop, anyone a visitor browses before they ever make
    # contact — that is the wrong half of the answer. Request 138's intake
    # asked in the owner's own words for "home, gallery, about, contact"
    # and got three admin screens wearing those four words in a header.
    #
    # The split is deliberate: two screens the visitor sees, one the owner
    # works in. A demo of only public pages would be a website mock-up and
    # would not show there is software here at all; a demo of only the back
    # office is what the pipeline already got wrong.
    "public-site": {
        "label": "Public Site + Back Office",
        "when": (
            "businesses whose product faces the public and is browsed before it is bought: "
            "artists, galleries, portfolios, restaurants, shops, venues — where a visitor "
            "looks first and the owner manages what they looked at"
        ),
        "screens": [
            {
                "screen_type": "home",
                "surface": surfaces.MARKETING,
                "layout": "full-bleed hero image with the business name and one short line of positioning, a single primary call to action, three short value points below, and a strip of featured work — no KPI cards, no chart, no data tables",
                "chart": None,
            },
            {
                "screen_type": "gallery",
                "surface": surfaces.CATALOG,
                "layout": "a grid of the things on offer, each with its own image, title and price or short attribute, a row of category filters above the grid, one item visibly hovered or featured — no KPI cards, no chart",
                "chart": None,
            },
            {
                "screen_type": "manage",
                "surface": surfaces.BACK_OFFICE,
                # The owner's own menu. The customer's list is the WEBSITE's
                # navigation and belongs to the visitor-facing screens; this
                # screen is the admin tool behind it and is none of those
                # sections, which is why nothing could ever be marked active
                # on it. Deliberately business-neutral — the archetype serves
                # galleries, restaurants and shops alike — and only used when
                # the model copies the public list across instead of writing
                # its own (measured: it does that every run).
                "admin_navigation": ["Overview", "Catalogue", "Enquiries", "Settings"],
                "layout": "the owner's side: 4 KPI cards, a bar chart of views or enquiries over time, and a management table of the catalogue items with status and price",
                "chart": "bar",
            },
        ],
    },
}

DEFAULT_ARCHETYPE = "operations-dashboard"

# The archetype that answers a public-facing brief. Named for the same
# reason ASSISTANT_ARCHETYPE is: code needs to reason about the pairing
# without string-matching an id in three places.
PUBLIC_SITE_ARCHETYPE = "public-site"

# The one archetype whose anchor is a conversation rather than a selection
# flow. Named here so the ui_spec stage can enforce that pairing in code —
# see _apply_anchor_tool: nearly every brief is sold an AI front-desk in
# its consulting summary, so "assistant" is a kind any business could reach
# for, and a salon whose anchor became a chat window instead of its booking
# flow would be a worse demo rather than a more honest one.
ASSISTANT_ARCHETYPE = "assistant-console"


def get_archetype(archetype_id: str | None) -> tuple[str, dict]:
    """Resolves an archetype id (falling back to the default) — never raises,
    an unknown/missing id from the LLM must not fail the pipeline."""
    if archetype_id and archetype_id in ARCHETYPES:
        return archetype_id, ARCHETYPES[archetype_id]
    return DEFAULT_ARCHETYPE, ARCHETYPES[DEFAULT_ARCHETYPE]


def screen_surfaces(archetype_id: str | None, screen_count: int) -> list[str]:
    """The surface of each screen this archetype will produce, in order.

    This is the routing table the whole surface mechanism rests on, and it
    is deterministic on purpose: the archetype was already chosen by the
    ui_spec stage, so the shape that DRAWS a screen and the rubric that
    SCORES it read the same answer and cannot disagree about what the
    screen was meant to be. A per-image classifier would be a second model
    re-deciding something the generator already knows, and every
    disagreement between the two would be a screen judged by the wrong
    rubric."""
    _, arch = get_archetype(archetype_id)
    return [
        surfaces.resolve(screen.get("surface"))
        for screen in arch["screens"][:screen_count]
    ]


def admin_navigation(archetype_id: str | None) -> list[str] | None:
    """The owner-facing menu an archetype defines for its back-office
    screen, when it has both kinds of screen. None when it does not."""
    _, arch = get_archetype(archetype_id)
    for screen in arch["screens"]:
        if screen.get("admin_navigation"):
            return list(screen["admin_navigation"])
    return None


def has_public_screens(archetype_id: str | None) -> bool:
    _, arch = get_archetype(archetype_id)
    return any(surfaces.is_public(s.get("surface")) for s in arch["screens"])


def catalog_for_prompt() -> str:
    """Short, LLM-readable catalog used by ui_spec.j2 for archetype selection.

    Public screens are marked. The ui_spec stage chooses the archetype, so
    it cannot be told the surfaces up front — but once it has chosen, it has
    to know which screens a VISITOR sees, because the content differs
    completely. Request 141 is why: every screen of the public-site
    archetype came back greeting the owner ("Good morning, Jeanne") and the
    landing page's featured strip was filled from a customer list, so its
    artwork captions read "Sarah Chen · Coastal Serenity". The rendering and
    the rubric knew it was a public page; the stage writing the words did
    not."""
    lines = []
    for aid, arch in ARCHETYPES.items():
        screens = " -> ".join(s["screen_type"] for s in arch["screens"])
        line = f"- {aid}: best for {arch['when']}. Screens: {screens}"
        # The marker sits in its own clause, never fused to a screen_type
        # token. Request 143 rendered it as "home [PUBLIC PAGE]" written
        # straight into product.screen_type, so the studio page labelled the
        # tab "Home [Public Page]" — scaffolding becoming data, the same
        # mechanism as every rendered-prompt-vocabulary leak this pipeline
        # has had.
        public = [s["screen_type"] for s in arch["screens"] if surfaces.is_public(s.get("surface"))]
        if public:
            line += f". Of these, a VISITOR sees: {', '.join(public)}"
        lines.append(line)
    return "\n".join(lines)
