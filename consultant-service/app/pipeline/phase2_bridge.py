"""W7 — the Phase-1 → Phase-2 bridge.

A client who buys the image demo has already answered every question the
React pipeline is going to ask, and has already agreed which screens the
product has. Making them re-enter that is the worst moment in the funnel:
it is the point where a closed lead is asked to prove they meant it.

This module maps a finished Phase-1 request onto the payload Phase 2's
public intake accepts — `POST /api/v1/requests`, form-encoded, in
backend/app/api/v1/routers/requests.py — so the upgrade is a button, not an
interview.

## Why the output is shaped like an intake form and not like a blueprint

Phase 2's AppSpec author does not read arbitrary context. Its authoritative
input is captured by `capture_request_source` (backend/app/application/
appspec/source.py) and is EXACTLY the intake columns, plus reference
evidence. That function's own docstring says the snapshot "deliberately
excludes contact PII, admin notes, generation progress, blueprint prose, and
preview artifacts."

Two consequences, and both are deliberate here:

  - Anything Phase 1 learned reaches the AppSpec author only if it is
    carried IN an intake field. There is no side channel today.
  - The MVP blueprint is not carried at all. Phase 2 excluded blueprint
    prose on purpose; pasting it into `desired_outcome` would smuggle it
    past that decision under a different name. What crosses is facts —
    concept name, the agreed screen inventory, the palette, the AI
    capabilities — not paragraphs.

`carried` holds the same facts as structured data. Nothing consumes it
today. It exists so the handoff is auditable, and so a future Phase-2 seed
endpoint has something to read that is not prose.

## What this module will not do

It never invents. A request with no palette produces a brief with no
palette and a note saying so, because a fabricated brand colour would be
indistinguishable, downstream, from one the client chose.

It is a pure function of the request: no network, no writes, no clock. The
same request maps to the same brief every time, which is what makes it safe
to call from a retry, an admin button, or a test.
"""

import json
from dataclasses import dataclass, field

from app.models import Request

PHASE2_BRIEF_VERSION = "phase2-brief-v1"

# The form fields backend's POST /api/v1/requests accepts. business_name,
# business_description and email are required there; the rest are optional.
PHASE2_INTAKE_FIELDS = (
    "business_name",
    "business_description",
    "email",
    "industry",
    "target_customers",
    "main_problem",
    "reference_url",
    "what_you_like",
    "desired_outcome",
    "project_type",
    "existing_product_url",
    "needs_ai",
    "budget_range",
    "timeline",
    "whatsapp",
)

# Phase 1 and Phase 2 named these identically — the consultant service's
# intake was built from the same wizard — so the shared ones copy across
# verbatim rather than being translated.
_SHARED_INTAKE_FIELDS = (
    "business_name",
    "business_description",
    "email",
    "industry",
    "target_customers",
    "main_problem",
    "reference_url",
    "what_you_like",
    "desired_outcome",
    "needs_ai",
    "budget_range",
    "timeline",
    "whatsapp",
)

# Bounds on what gets appended to a free-text field. The AppSpec author reads
# these as customer intent; a wall of generated text would outweigh what the
# client actually typed, which is the one thing in there that is true by
# definition.
MAX_CARRIED_SCREENS = 6
MAX_CARRIED_AI_CAPABILITIES = 6


@dataclass
class Phase2Brief:
    """`intake` is submittable to Phase 2 as-is. `carried` is the same facts
    structured, for audit. `notes` names everything Phase 1 knew that did not
    survive the crossing, so a gap is visible rather than silent."""

    intake: dict[str, str] = field(default_factory=dict)
    carried: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    version: str = PHASE2_BRIEF_VERSION


def screen_inventory(req: Request) -> list[dict[str, str]]:
    """The screens the client actually saw and agreed to, in the order the
    demo showed them — the anchor first.

    Read from the generated images rather than from `roles_json`, because
    those rows are the screens that were really produced and shown. A plan
    can name a screen that never rendered; a GeneratedImage row cannot.
    """
    return [
        {
            "label": img.role_label or img.role_id,
            "screen_type": img.screen_type or img.role_id,
            "demo_image_url": img.file_path,
        }
        for img in sorted(req.images, key=lambda i: (i.id,))
    ]


def palette(req: Request) -> dict[str, str]:
    """The brand colours Phase 1 settled on. Empty when it never had any —
    never a guessed hex."""
    if not req.visual_theme_json:
        return {}
    try:
        theme = json.loads(req.visual_theme_json) or {}
    except (ValueError, TypeError):
        return {}
    return {
        key: str(theme[key])
        for key in ("primary_color", "secondary_color")
        if isinstance(theme.get(key), str) and theme[key].strip()
    }


def ai_capabilities(req: Request) -> list[str]:
    """The AI employees the consulting stage recommended, by title. Phase 2
    has a first-class `ai_features` channel for these, but it fills it from
    its OWN blueprint stage and there is no way to write it through the
    intake form — so they cross as named capabilities in the text."""
    if not req.consulting_recommendations_json:
        return []
    try:
        recommendations = json.loads(req.consulting_recommendations_json) or {}
    except (ValueError, TypeError):
        return []
    titles = [
        str(emp.get("title", "")).strip()
        for emp in (recommendations.get("recommended_ai_employees") or [])
        if isinstance(emp, dict) and str(emp.get("title", "")).strip()
    ]
    return titles[:MAX_CARRIED_AI_CAPABILITIES]


def _outcome_addendum(concept_name: str | None, screens: list[dict], capabilities: list[str]) -> str:
    """What Phase 1 agreed, in the register of a client describing what they
    want — because that is what the field it lands in means."""
    parts = []
    if concept_name:
        parts.append(f'We have already agreed the product and named it "{concept_name}".')
    if screens:
        listed = ", ".join(s["label"] for s in screens[:MAX_CARRIED_SCREENS])
        parts.append(
            f"We have also agreed its screens and signed them off from a visual demo: {listed}. "
            "The build should have these screens."
        )
    if capabilities:
        parts.append("The AI capabilities we agreed on are: " + ", ".join(capabilities) + ".")
    return " ".join(parts)


def _style_addendum(colors: dict[str, str], register: str | None) -> str:
    parts = []
    if colors.get("primary_color"):
        secondary = colors.get("secondary_color")
        parts.append(
            f"Our brand colour is {colors['primary_color']}"
            + (f", with {secondary} as a secondary." if secondary else ".")
        )
    if register:
        parts.append(f"We approved a {register} visual direction for the screens and want the build to match it.")
    return " ".join(parts)


def _joined(existing: str | None, addendum: str) -> str:
    """The client's own words first, always. Theirs are the true ones."""
    existing = (existing or "").strip()
    if not addendum:
        return existing
    return f"{existing} {addendum}".strip() if existing else addendum


def build_phase2_brief(req: Request, *, image_register: str | None = None) -> Phase2Brief:
    """A finished Phase-1 request -> the Phase-2 intake payload.

    `image_register` is the register the demo actually shipped in (the
    caller's `settings.IMAGE_REGISTER`); passed in rather than read here so
    this stays a pure function of its arguments.
    """
    brief = Phase2Brief()

    for name in _SHARED_INTAKE_FIELDS:
        value = getattr(req, name, None)
        if value:
            brief.intake[name] = str(value)

    # Phase-2-only fields. A Phase-1 client is commissioning a build of the
    # product they were just shown, which is `new` — `enhance` would point
    # the pipeline at an existing product that, by definition, does not
    # exist yet.
    brief.intake["project_type"] = "new"

    screens = screen_inventory(req)
    colors = palette(req)
    capabilities = ai_capabilities(req)

    brief.carried = {
        "phase1_request_id": req.id,
        "concept_name": req.concept_name,
        "screens": screens,
        "palette": colors,
        "ai_capabilities": capabilities,
        "image_register": image_register,
    }

    outcome = _outcome_addendum(req.concept_name, screens, capabilities)
    style = _style_addendum(colors, image_register)
    if outcome:
        brief.intake["desired_outcome"] = _joined(brief.intake.get("desired_outcome"), outcome)
    if style:
        brief.intake["what_you_like"] = _joined(brief.intake.get("what_you_like"), style)

    if not screens:
        brief.notes.append(
            "No screen inventory: this request has no generated images, so there is nothing the "
            "client has actually agreed to. Phase 2 will plan its own screens."
        )
    elif len(screens) > MAX_CARRIED_SCREENS:
        brief.notes.append(
            f"{len(screens)} screens agreed, {MAX_CARRIED_SCREENS} carried — the rest are in `carried`."
        )
    if not colors:
        brief.notes.append("No palette: Phase 1 never settled one, and a guessed brand colour is worse than none.")
    if not capabilities:
        brief.notes.append("No AI capabilities carried: the consulting stage recommended none.")
    if req.mvp_blueprint:
        brief.notes.append(
            "The MVP blueprint is deliberately NOT carried. Phase 2's source capture excludes blueprint "
            "prose by design; routing it through an intake field would defeat that decision."
        )
    if not req.email:
        brief.notes.append("No email: Phase 2's intake requires one and will reject this payload.")

    return brief


def as_form_payload(brief: Phase2Brief) -> dict[str, str]:
    """Exactly what to POST to Phase 2, with unknown keys dropped rather than
    sent — its endpoint takes declared Form fields and would silently ignore
    anything else, which is a worse failure than not sending it."""
    return {k: v for k, v in brief.intake.items() if k in PHASE2_INTAKE_FIELDS and v}
