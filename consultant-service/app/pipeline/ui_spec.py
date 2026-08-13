"""Stage 4: business analysis -> structured UIDemoSpec objects (one per
screen). Prompt version: ui-spec-v1 (prompts/ui_spec.j2).

The LLM here produces DATA only — realistic business-specific labels,
names, KPIs, terminology. It never writes image prompts; those are built
deterministically from the specs by pipeline/prompt_builder.py. Falls back
to deterministic generic specs if the model response is unusable, so the
pipeline always has something to render.
"""

import logging
import re

from sqlalchemy.orm import Session

from app import archetypes
from app.ai import provider
from app.config import settings
from app.models import Request
from app.pipeline._shared import extract_json_from_text, log_usage
from app.templating import render
from app.archetypes import ASSISTANT_ARCHETYPE
from app.ui_spec import TOOL_CONCEPT_KINDS, ChartSpec, Kpi, Panel, ScreenConcept, UIDemoSpec

logger = logging.getLogger("consultant.ui_spec")

UI_SPEC_PROMPT_VERSION = "ui-spec-v5"


# ── the customer's own navigation list ────────────────────────────────────
# Request 107 asked, in as many words, for "a dashboard that contains home,
# gallery, about, contact" and got a five-item header: ui_spec.j2's RULES
# block called for "5-7 short one-word items", so the stage padded the
# customer's four up to the template's floor with "Settings". An explicit
# constraint lost to a default, silently — and silently is the word that
# matters, because the text-truth gate reads spec.navigation as its ground
# truth, so it dutifully checked the invented item and passed 7/7.
#
# The fix is two-layered on purpose. The template (ui_spec.j2) is TOLD the
# list, so the rest of the spec stays coherent with it — screen names, the
# anchor tool, the AI chips. And the list is then applied HERE, in code,
# because a prompt is a request and this is a promise: whatever the model
# returns, the navigation a customer named is the navigation that ships,
# and therefore also the navigation the gate measures.
#
# Deliberately conservative. It fires only on a navigation cue word
# followed by a run of at least three short label-shaped items, so the
# dental brief's "Cleanings, crowns, implants, Invisalign" and the HVAC
# brief's "with 6 technicians" cannot be mistaken for a header. Anything
# phrased more loosely than this regex is left to the template's
# instruction, which reads the same brief in full — a miss here degrades
# to the old behaviour, it never invents a list.

_NAV_CUES = re.compile(
    r"\b(?:nav|navbar|navigation|menu|header|tab|tabs|page|pages|section|sections"
    r"|link|links|contain|contains|containing|include|includes|including)\b",
    re.IGNORECASE,
)

# Words that can sit between the cue and the first item ("contains the
# following pages:", "with"). Every one of them is a word no real
# navigation label would be on its own, which is what makes stripping them
# safe.
_NAV_FILLER = frozenset(
    """a an and are as be been called contains containing exactly following for
    has have having includes including is it items just like link links menu nav
    navbar navigation named of only pages sections shows showing such tabs that
    the these this those with""".split()
)

# 1-3 words, letters first, nothing long enough to be a sentence. The
# leading-letter rule is what rejects "6 technicians" and "3 dentists".
_NAV_ITEM = re.compile(r"^[A-Za-z][A-Za-z0-9&/'’.\-]*(?: [A-Za-z0-9&/'’.\-]+){0,2}$")

_NAV_SPLIT = re.compile(r"\s*(?:,|\||\band\b)\s*", re.IGNORECASE)

# Three, not two: below three items a comma-separated run is far more often
# prose than a header, and early sessions found sparse navigation renders as
# an empty-looking bar. Eight is where prompt_builder and text_truth already
# slice the list, so honouring a ninth item would be a promise neither the
# image prompt nor the gate could keep.
_MIN_EXPLICIT_NAV = 3
_MAX_EXPLICIT_NAV = 8


def _nav_label(raw: str) -> str:
    """Title-cases the words the customer typed in lower case and leaves
    everything else alone — "home" -> "Home", but "FAQ" stays "FAQ"."""
    return " ".join(word.capitalize() if word.islower() else word for word in raw.split())


def _leading_nav_run(text: str) -> list[str]:
    """The run of label-shaped items at the START of `text`, stopping at the
    first thing that is not one. Starting-run rather than best-run: a list
    the customer wrote reads left to right from the cue, and scanning for a
    valid run anywhere in the sentence is how "everything I need, plus a
    calendar" turns into navigation."""
    items: list[str] = []
    for part in _NAV_SPLIT.split(text):
        candidate = part.strip().strip("\"'“”()[]:;.")
        if not candidate or len(candidate) > 24 or not _NAV_ITEM.match(candidate):
            break
        items.append(candidate)
    return items


def extract_explicit_navigation(*texts: str | None) -> list[str] | None:
    """The navigation items the customer named, in their order, or None.

    Reads each intake field in turn and returns the first list it can read
    with confidence. Case is normalised, duplicates dropped; nothing else
    about the customer's wording is changed.
    """
    for text in texts:
        if not text or not str(text).strip():
            continue
        for cue in _NAV_CUES.finditer(str(text)):
            # One sentence only: a list does not survive a full stop.
            tail = re.split(r"[.;\n?!]", str(text)[cue.end():], maxsplit=1)[0]
            tail = tail.lstrip(" \t:=-–—([")
            words = tail.split()
            while words and words[0].strip(",:").lower() in _NAV_FILLER:
                words.pop(0)
            items = _leading_nav_run(" ".join(words))

            seen: set[str] = set()
            labels: list[str] = []
            for item in items:
                label = _nav_label(item)
                if label.lower() in seen:
                    continue
                seen.add(label.lower())
                labels.append(label)

            if len(labels) >= _MIN_EXPLICIT_NAV:
                if len(labels) > _MAX_EXPLICIT_NAV:
                    logger.warning(
                        "explicit navigation had %s items; honouring the first %s",
                        len(labels), _MAX_EXPLICIT_NAV,
                    )
                return labels[:_MAX_EXPLICIT_NAV]
    return None


def _apply_explicit_navigation(specs: list[UIDemoSpec], explicit_nav: list[str] | None) -> None:
    """The customer's list, on every screen, whatever the model returned."""
    if not explicit_nav:
        return
    for spec in specs:
        spec.navigation = list(explicit_nav)


def _apply_active_nav_invariant(specs: list[UIDemoSpec]) -> None:
    """Keep a declared active item only when it is genuinely one of the
    honoured navigation labels, and only one screen may claim each.

    The membership check is the whole safety argument. Request 107's
    six-item header happened because a prompt named an active item that
    did not exist and the model added it; a declared value that is not in
    `navigation` is that same failure arriving by a new road, so it is
    dropped rather than trusted. The de-duplication is the session-39
    defect stated as an invariant: three screens all claiming "Home" is
    exactly the dead navigation this field exists to fix, and a model that
    declares it should not be able to reintroduce it.

    Silence stays legal. A screen that is none of the customer's sections
    declares nothing and gets the pre-existing behaviour, because "no item
    is marked" is honest and banning it would be a new rule with its own
    blast radius.
    """
    claimed: set[str] = set()
    for spec in specs:
        declared = (spec.active_nav or "").strip()
        spec.active_nav = ""
        if not declared:
            continue
        match = next(
            (label for label in spec.navigation if label.strip().lower() == declared.lower()),
            None,
        )
        if match is None or match.strip().lower() in claimed:
            continue
        spec.active_nav = match
        claimed.add(match.strip().lower())


def _apply_hero_subject_invariant(specs: list[UIDemoSpec]) -> None:
    """On a tool screen the hero is a photograph OF the thing the detail
    panel describes, so the caption has to name that thing.

    Session 39, request 130/Analytics: `hero.caption` said "Crimson Tide"
    while `concept.detail.title` and the picker's `selected` both said
    "Azure Embrace". The image model rendered the spec faithfully and drew
    one painting captioned as another, beside a panel quoting a third
    thing's price. No instrument saw it: the defect inspector looks within
    a panel rather than across two, the judge reported only that the image
    was cropped, and text-truth passed correctly because every string on
    the screen was a string the spec had ordered. The spec was internally
    incoherent before a model ever read it, which makes this a code fix and
    not an instrument.

    Runs before the brand invariant so a caption replaced here still gets
    its brand widened.
    """
    for spec in specs:
        if not spec.concept.is_tool or not spec.hero.caption:
            continue
        subject = ((spec.concept.detail.title if spec.concept.detail else "") or "").strip()
        if not subject and spec.concept.steps:
            subject = (spec.concept.steps[-1].selected or "").strip()
        if subject and spec.hero.caption.strip().lower() != subject.lower():
            logger.info(
                "hero caption renamed to the screen's subject: %r -> %r",
                spec.hero.caption, subject,
            )
            spec.hero.caption = subject


def _fallback_specs(
    req: Request, plan_result: dict, screen_count: int, explicit_nav: list[str] | None = None
) -> tuple[str, list[UIDemoSpec]]:
    """Generic-but-coherent specs used when the LLM output is unusable.
    Deliberately neutral wording that can't be wrong for any industry."""
    theme = plan_result.get("visual_theme") or {}
    concept = plan_result.get("concept_name") or f"{req.business_name} OS"
    archetype_id, arch = archetypes.get_archetype(None)

    base = {
        "business": {
            "name": req.business_name or "",
            "industry": req.industry or "",
            "primary_color": theme.get("primary_color"),
            "secondary_color": theme.get("secondary_color"),
        },
        "user": {"name": "Alex", "role": "Owner"},
        # The customer's list survives the fallback too: this path runs when
        # the model failed, which is no reason to stop honouring something
        # read out of the brief in code.
        "navigation": list(explicit_nav) if explicit_nav
        else ["Dashboard", "Schedule", "Customers", "Billing", "Analytics", "Settings"],
        "style": {"archetype": archetype_id, "density": "normal", "palette_description": "light interface, restrained accents"},
    }
    names = ["Sarah Mitchell", "James Lopez", "Emily Chen", "Daniel Wilson", "Maria Thompson"]
    specs: list[UIDemoSpec] = []
    for screen in arch["screens"][:screen_count]:
        spec = UIDemoSpec.model_validate(
            {
                **base,
                "product": {"name": concept, "purpose": "daily operations, customers and analytics", "screen_type": screen["screen_type"]},
                "greeting": "Good morning, Alex",
                "subheading": "Today at a glance",
                "kpis": [
                    Kpi(label="Bookings Today", value="18", delta="+12% vs last week", trend="up"),
                    Kpi(label="New Customers", value="7", delta="+3 this week", trend="up"),
                    Kpi(label="No-show Rate", value="6.2%", delta="-1.1pp", trend="down"),
                    Kpi(label="Revenue Today", value="$1,940", delta="+8%", trend="up"),
                ],
                "primary_panel": Panel(
                    title="Today's Schedule",
                    rows=[
                        {"time": "8:30 AM", "name": names[0], "item": "Consultation", "status": "Confirmed"},
                        {"time": "9:15 AM", "name": names[1], "item": "Follow-up", "status": "Confirmed"},
                        {"time": "10:00 AM", "name": names[2], "item": "New visit", "status": "Pending"},
                        {"time": "11:30 AM", "name": names[3], "item": "Consultation", "status": "Confirmed"},
                    ],
                ),
                "chart": ChartSpec(
                    title="This Week", labels=["Mon", "Tue", "Wed", "Thu", "Fri"],
                    values=[22, 28, 25, 30, 27], metric_label="bookings per day",
                )
                if screen.get("chart")
                else None,
                "activity": [
                    {"name": names[0], "action": "Booking confirmed", "time": "9:02 AM"},
                    {"name": names[1], "action": "Reminder sent", "time": "8:47 AM"},
                    {"name": names[4], "action": "Rescheduled", "time": "8:15 AM"},
                ],
            }
        )
        specs.append(spec)
    return archetype_id, specs


def _apply_anchor_tool(specs: list[UIDemoSpec], anchor_tool: dict | None, archetype_id: str = "") -> None:
    """Map the top-level `anchor_tool` object onto the anchor screen's concept.

    Why it is top-level in the prompt and mapped here, rather than a per-screen
    `concept` field the model fills directly: asked for it per-screen, the model
    returned "dashboard" for 6 of 6 businesses across two prompt revisions. The
    archetype catalogue sits directly above and names a screen sequence of
    dashboards, and a per-screen field inside that sequence reads as "which
    kind of dashboard". Hoisting it to a required top-level key asked before
    the screens array makes it a decision instead of a default.

    Only the ANCHOR gets it — follow-up screens inherit the anchor's look from
    a reference image, and a second selection flow in the same product would
    describe a different screen, not the same one.
    """
    if not isinstance(anchor_tool, dict) or not specs:
        return
    kind = str(anchor_tool.get("kind") or "").strip().lower()

    if kind == "assistant":
        # The conversation shape belongs to ONE archetype, and the rule is
        # enforced here rather than trusted to the prompt. Almost every
        # business this pipeline sees is sold an AI front-desk in its
        # consulting summary, so "assistant" is a kind any brief could
        # reach for — and a salon whose anchor became a chat window instead
        # of its booking flow would be a worse demo, not a more honest one.
        if archetype_id != ASSISTANT_ARCHETYPE:
            logger.info(
                "anchor_tool kind=assistant on archetype=%s — not the console, anchor stays a dashboard",
                archetype_id,
            )
            return
        turns = [
            t for t in (anchor_tool.get("turns") or [])
            if isinstance(t, dict) and str(t.get("text") or "").strip()
        ]
        if len(turns) < 2:
            logger.info("anchor_tool kind=assistant arrived with %s turns — anchor stays a dashboard", len(turns))
            return
        specs[0].concept = ScreenConcept.model_validate(
            {
                "kind": kind,
                "turns": turns,
                "detail": anchor_tool.get("detail"),
                "primary_action": anchor_tool.get("primary_action") or "",
                "secondary_action": anchor_tool.get("secondary_action") or "",
            }
        )
        return

    if kind not in TOOL_CONCEPT_KINDS:
        return
    steps = [s for s in (anchor_tool.get("steps") or []) if isinstance(s, dict) and s.get("label")]
    if not steps:
        # kind without steps is not a tool screen, it is a claim. is_tool
        # requires both, so leaving concept empty degrades to a dashboard.
        logger.info("anchor_tool kind=%s arrived without steps — anchor stays a dashboard", kind)
        return
    specs[0].concept = ScreenConcept.model_validate(
        {
            "kind": kind,
            "steps": steps,
            "detail": anchor_tool.get("detail"),
            "primary_action": anchor_tool.get("primary_action") or "",
            "secondary_action": anchor_tool.get("secondary_action") or "",
        }
    )


_LEGAL_SUFFIXES = ("llp", "llc", "ltd", "inc", "gmbh", "plc", "pllc", "co")


def _widen_truncated_brand(text: str, brand: str) -> str:
    """"LexStream by Hartwell & Grey" + "Hartwell & Grey LLP" ->
    "LexStream by Hartwell & Grey LLP". Fires only when the text embeds the
    brand minus a trailing legal suffix — the one rewrite that cannot hit a
    legitimate coinage. Everything fuzzier (the "Northgate Roastery" and
    "Lumière Studio OS" paraphrase class) is constrained in ui_spec.j2 and
    stays measured by the text-truth gate rather than rewritten here: a
    rule loose enough to catch a paraphrase is loose enough to mangle a
    real product name like "Northgate RoasterFlow AI"."""
    if not text or not brand:
        return text
    tokens = brand.split()
    if len(tokens) < 2 or tokens[-1].strip(".,").lower() not in _LEGAL_SUFFIXES:
        return text
    core = " ".join(tokens[:-1])
    lowered, core_l, brand_l = text.lower(), core.lower(), brand.lower()
    if brand_l in lowered or core_l not in lowered:
        return text
    start = lowered.index(core_l)
    return text[:start] + brand + text[start + len(core):]


def _apply_brand_string_invariant(specs: list[UIDemoSpec]) -> None:
    """The text-truth gate demands the business's exact name; the image
    model renders exactly the strings these specs order. Every recorded
    shipped text-truth failure — "by hartwell & grey" (request 93),
    "northgate roastery" (95, 12), "lumière studio os" (22) — was this
    stage inventing a brand variant, i.e. the pipeline ordering one string
    and judging another. The deterministic half of the fix lives here."""
    for spec in specs:
        spec.product.name = _widen_truncated_brand(spec.product.name, spec.business.name)
        if spec.hero.caption:
            spec.hero.caption = _widen_truncated_brand(spec.hero.caption, spec.business.name)


def build_ui_specs(
    db: Session, request_id: int, consult_result: dict, plan_result: dict
) -> tuple[str, list[UIDemoSpec]]:
    """Returns (archetype_id, specs) — one UIDemoSpec per screen, anchor first."""
    req = db.get(Request, request_id)
    if req is None:
        raise ValueError(f"Request {request_id} not found")

    screen_count = max(2, min(3, settings.DEMO_SCREEN_COUNT))
    theme = plan_result.get("visual_theme") or {}
    explicit_nav = extract_explicit_navigation(
        req.business_description, req.main_problem, req.desired_outcome, req.what_you_like
    )
    if explicit_nav:
        logger.info(
            "explicit navigation read from the intake: request=%s items=%s",
            request_id, explicit_nav,
        )

    try:
        prompt = render(
            "ui_spec.j2",
            explicit_navigation=explicit_nav,
            business_name=req.business_name or "",
            business_description=req.business_description or "",
            industry=req.industry or "unspecified",
            location=None,
            concept_name=plan_result.get("concept_name") or f"{req.business_name} OS",
            consulting_summary=consult_result.get("consulting_summary") or "",
            primary_color=theme.get("primary_color") or "#2563eb",
            secondary_color=theme.get("secondary_color") or "#0f766e",
            archetype_catalog=archetypes.catalog_for_prompt(),
            screen_count=screen_count,
        )
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}], max_tokens=8000)
        content = body["choices"][0]["message"]["content"]
        parsed = extract_json_from_text(content)

        archetype_id, arch = archetypes.get_archetype(parsed.get("archetype"))
        specs = [UIDemoSpec.model_validate(s) for s in (parsed.get("screens") or [])][:screen_count]
        if not specs:
            raise ValueError("Model returned no screens")

        _apply_anchor_tool(specs, parsed.get("anchor_tool"), archetype_id)

        # Coherence guards the image prompt depends on: identical navigation
        # across screens (anchor's wins) and the archetype id recorded on
        # every spec, whatever the model put there.
        for spec in specs:
            spec.style.archetype = archetype_id
            if specs[0].navigation:
                spec.navigation = specs[0].navigation
            if not spec.business.name:
                spec.business.name = req.business_name or ""

        # After the coherence loop, not inside it: the customer's list is the
        # last word on navigation, including over the anchor's.
        _apply_explicit_navigation(specs, explicit_nav)
        _apply_active_nav_invariant(specs)
        _apply_hero_subject_invariant(specs)
        _apply_brand_string_invariant(specs)

        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="ui_spec",
            usage=body.get("usage"), success=True,
        )
        logger.info(
            "ui_spec built: request=%s archetype=%s screens=%s prompt_version=%s",
            request_id, archetype_id, [s.product.screen_type for s in specs], UI_SPEC_PROMPT_VERSION,
        )
        return archetype_id, specs
    except Exception as exc:
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="ui_spec",
            success=False, error=str(exc)[:500],
        )
        logger.warning("ui_spec fell back to deterministic specs: request=%s error=%s", request_id, exc)
        return _fallback_specs(req, plan_result, screen_count, explicit_nav)
