"""What KIND of software surface a screen is — the one key that routes both
how it gets drawn and how it gets judged.

Until session 39 every archetype in this pipeline was a back-office
dashboard, so "how to draw a screen" and "how to score a screen" could both
be single answers and the judge could be archetype-blind. That stopped
being true the moment a customer asked for something a visitor sees.
Request 138's intake was "I wanna showcase my paitings, with a dashboard
that contains home, gallery, about, contact" — home and gallery are public
pages — and the pipeline answered with three admin screens wearing the
customer's words in their header. The navigation was honoured; the product
was not.

A surface carries three decisions that used to be hard-coded:

  - which prompt shape draws it (`prompt_kind`)
  - which rubric scores it (`judge_template`)
  - what is a defect ON it (`allows_marketing_composition`, `expects_chart`)

The third matters as much as the others. `image_quality_judge.j2` lists "a
marketing-page composition" as an automatic rejection and grades "a
thoughtfully crafted hero chart" as a whole criterion. On a landing page
those are not defects, they are the assignment — a rubric written for data
screens would reject a correct public page by construction, and because a
score under QA_REGEN_SCORE_FLOOR buys a regeneration, it would do it while
quietly spending money.

THE ADDITIVE RULE. Every surface that existed before this module routes to
`image_quality_judge.j2`, the same file, unchanged. No historical score
moves, so the judge-held-fixed rule is not broken and no before/after is
owed for the refactor itself. Only genuinely new surfaces get new rubrics.
Moving `conversation` onto a rubric of its own is a live option — session
38 flagged console scores as not comparable to the dashboard corpus for
exactly this reason — but it is a score-moving change and owes its own
measurement, so it is deliberately NOT taken here.

Routing is deterministic, not a second model call. The archetype is already
chosen by the ui_spec stage, and each of its screens declares its surface,
so the screen that gets drawn and the rubric that scores it cannot disagree
about what the screen was meant to be. A separate classifier would be a
model deciding, per image, something the generator already knows.
"""

from __future__ import annotations

BACK_OFFICE = "back_office"
CONVERSATION = "conversation"
MARKETING = "marketing"
CATALOG = "catalog"

DEFAULT_SURFACE = BACK_OFFICE

SURFACES: dict[str, dict] = {
    BACK_OFFICE: {
        "label": "Back-office screen",
        "description": "the software the business operates: dashboards, schedules, pipelines, analytics",
        "prompt_kind": BACK_OFFICE,
        "judge_template": "image_quality_judge.j2",
        "expects_chart": True,
        "allows_marketing_composition": False,
        "audience": "the person who runs the business",
    },
    CONVERSATION: {
        "label": "Assistant console",
        "description": "a thread between a customer and the product's assistant",
        "prompt_kind": CONVERSATION,
        # Deliberately the same rubric as back_office: changing it would move
        # every console score ever published. See the additive rule above.
        "judge_template": "image_quality_judge.j2",
        "expects_chart": False,
        "allows_marketing_composition": False,
        "audience": "the person who runs the business",
    },
    MARKETING: {
        "label": "Public landing page",
        "description": "the page a visitor lands on: hero, what this is, proof, one clear call to action",
        "prompt_kind": MARKETING,
        "judge_template": "image_quality_judge_public.j2",
        "expects_chart": False,
        "allows_marketing_composition": True,
        "audience": "a visitor who has never used the product",
    },
    CATALOG: {
        "label": "Public catalogue page",
        "description": "the page a visitor browses: a grid of the things on offer, with filters",
        "prompt_kind": CATALOG,
        "judge_template": "image_quality_judge_public.j2",
        "expects_chart": False,
        "allows_marketing_composition": True,
        "audience": "a visitor deciding what they want",
    },
}

# Surfaces a visitor sees rather than an operator. Kept as a set rather than
# read off `allows_marketing_composition`, because "is this public" and "may
# this look like a marketing page" are two questions that happen to agree
# today and should be free to stop agreeing.
PUBLIC_SURFACES = frozenset({MARKETING, CATALOG})


def get(surface_id: str | None) -> dict:
    """The surface record, falling back to back-office.

    Unknown ids fall back rather than raise for the same reason
    get_archetype does: this value can arrive from a frozen golden bundle
    written before the field existed, and a demo that renders as a
    dashboard is a far smaller failure than a request that dies."""
    return SURFACES.get(surface_id or "", SURFACES[DEFAULT_SURFACE])


def resolve(surface_id: str | None) -> str:
    """The id itself, normalised to one that exists."""
    return surface_id if surface_id in SURFACES else DEFAULT_SURFACE


def judge_template(surface_id: str | None) -> str:
    return get(surface_id)["judge_template"]


def is_public(surface_id: str | None) -> bool:
    return resolve(surface_id) in PUBLIC_SURFACES
