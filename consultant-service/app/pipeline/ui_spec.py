"""Stage 4: business analysis -> structured UIDemoSpec objects (one per
screen). Prompt version: ui-spec-v1 (prompts/ui_spec.j2).

The LLM here produces DATA only — realistic business-specific labels,
names, KPIs, terminology. It never writes image prompts; those are built
deterministically from the specs by pipeline/prompt_builder.py. Falls back
to deterministic generic specs if the model response is unusable, so the
pipeline always has something to render.
"""

import logging

from sqlalchemy.orm import Session

from app import archetypes
from app.ai import provider
from app.config import settings
from app.models import Request
from app.pipeline._shared import extract_json_from_text, log_usage
from app.templating import render
from app.ui_spec import TOOL_CONCEPT_KINDS, ChartSpec, Kpi, Panel, ScreenConcept, UIDemoSpec

logger = logging.getLogger("consultant.ui_spec")

UI_SPEC_PROMPT_VERSION = "ui-spec-v3"


def _fallback_specs(req: Request, plan_result: dict, screen_count: int) -> tuple[str, list[UIDemoSpec]]:
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
        "navigation": ["Dashboard", "Schedule", "Customers", "Billing", "Analytics", "Settings"],
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


def _apply_anchor_tool(specs: list[UIDemoSpec], anchor_tool: dict | None) -> None:
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

    try:
        prompt = render(
            "ui_spec.j2",
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

        _apply_anchor_tool(specs, parsed.get("anchor_tool"))

        # Coherence guards the image prompt depends on: identical navigation
        # across screens (anchor's wins) and the archetype id recorded on
        # every spec, whatever the model put there.
        for spec in specs:
            spec.style.archetype = archetype_id
            if specs[0].navigation:
                spec.navigation = specs[0].navigation
            if not spec.business.name:
                spec.business.name = req.business_name or ""

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
        return _fallback_specs(req, plan_result, screen_count)
