"""One paragraph naming what the customer is looking at.

Request 107 asked to showcase paintings and received an operations
dashboard. The header failure had a fix (session 38, step 1); this is the
other half, and it is the half no archetype can solve, because the answer
for that customer is genuinely "not the thing you pictured". They read a
result page that opened with a product name and three screenshots and had
no sentence anywhere on it saying what class of software had just been
designed for them. "I didn't get the goal of this" is the reasonable
response to that page, not a misunderstanding of it.

So the page says it. Always, for every request, not only for the ones we
suspect of wanting a public site — a conditional would need a classifier
to decide when honesty applies, and the sentence is true for every
archetype in the catalogue. All six are software the owner runs the
business WITH: an operations board, a calendar, a CRM, an analytics view,
a job pipeline, an assistant console. None of them is the customer's
public website, and a salon that wanted exactly this reads the same
paragraph as reassurance.

COMPOSED, never written — the same rule as screen_story: every noun comes
from a string already stored on the request, so a customer can check the
paragraph against the rest of the page. No model call, no cost, nothing
that can hallucinate.
"""

_PUBLIC_SITE_WORDS = (
    "website", "web site", "landing page", "portfolio site", "showcase",
    "shop online", "online store", "storefront",
)


def _mentions_a_public_site(text: str) -> bool:
    """Whether the brief reads like someone asking for their public face.

    Used ONLY to add a second sentence that names the distinction out loud.
    Getting this wrong in either direction costs a customer nothing: the
    first sentence already tells them what they are looking at, and the
    second is an extra courtesy, never the only honest thing on the page.
    """
    lowered = (text or "").lower()
    return any(word in lowered for word in _PUBLIC_SITE_WORDS)


def build(
    business_name: str | None,
    concept_name: str | None,
    business_description: str | None = None,
) -> str | None:
    """The paragraph, or None when there is not enough on file to say it
    without inventing anything.

    Deliberately does NOT restate what the product does for them. The
    consulting summary is a paragraph of value proposition, the page
    already carries it twice (the AI-employee cards and the feature list),
    and pasting it in a third time turned this into a wall of text on the
    first run it was tried against. This paragraph answers one question —
    what class of thing am I looking at — and stops.
    """
    business = (business_name or "").strip()
    concept = (concept_name or "").strip()
    if not business or not concept:
        return None

    lines = [
        f"{concept} is the software {business} would run day to day — "
        f"the screens below are its interface, drawn with your own services, "
        f"your own customers and plausible numbers for a business your size."
    ]

    if _mentions_a_public_site(business_description or ""):
        lines.append(
            "It is not your public website. It is the back-office tool you would use to run "
            "the enquiries, bookings and sales that come in through one — and it is what we "
            "are proposing to build first."
        )

    return " ".join(lines)
