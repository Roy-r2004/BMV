"""Typed UI spec sitting between business analysis and image generation.

The core philosophy of the demo-screenshot pipeline:

    BUSINESS ANALYSIS -> STRUCTURED UI SPEC -> PROMPT TEMPLATE
    -> IMAGE GENERATION -> QUALITY REVIEW -> FINAL SCREENSHOTS

Image prompts are built deterministically from this spec (see
pipeline/prompt_builder.py) instead of letting an LLM write freeform image
prompts — personalization lives in the DATA (labels, names, KPIs,
terminology), while layout/style stay controlled and consistent.

Validation is deliberately tolerant (defaults everywhere, extra keys
ignored): a partially-filled spec from the LLM should degrade to a thinner
screenshot, never fail the pipeline.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Tolerant(BaseModel):
    model_config = ConfigDict(extra="ignore")


class BusinessInfo(_Tolerant):
    name: str = ""
    industry: str = ""
    location: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None


class ProductInfo(_Tolerant):
    name: str = ""
    purpose: str = ""
    screen_type: str = "dashboard"


class UserInfo(_Tolerant):
    name: str = ""
    role: str = ""


class Kpi(_Tolerant):
    label: str = ""
    value: str = ""
    delta: str | None = None
    trend: str | None = None  # "up" | "down" | "neutral"


class Panel(_Tolerant):
    title: str = ""
    rows: list[dict[str, str]] = Field(default_factory=list)


class ChartSpec(_Tolerant):
    title: str = ""
    labels: list[str] = Field(default_factory=list)
    values: list[float] = Field(default_factory=list)
    metric_label: str = ""

    @field_validator("values", mode="before")
    @classmethod
    def _only_plottable_numbers(cls, value):
        """A chart the model drew wrong costs its own screen a chart. It
        must not cost the request its entire spec.

        Found live, 2026-08-12, on the investment classification probe: the
        stage returned a multi-series chart — values[6] came back as
        {"series1": 1.4, "series2": 6.9} — which failed list[float]
        validation, and because the whole screens array is validated in one
        pass, build_ui_specs caught the error and fell back to the generic
        deterministic specs. A single bad data point turned a personalised
        demo into one specific to nobody, for the whole request. The
        pipeline already renders a chartless screen correctly (_chart_block
        returns "" without labels), so dropping the series is a real
        degradation path and losing the request is not.

        Nothing is repaired or guessed here — a dict is not a number and
        this does not try to pick one out of it. Mixed content drops the
        series entirely rather than plotting the half that parsed, because
        half a series against a full set of labels is a wrong chart rather
        than a smaller one.
        """
        if not isinstance(value, list):
            return []
        cleaned = []
        for entry in value:
            if isinstance(entry, bool) or not isinstance(entry, (int, float, str)):
                return []
            try:
                cleaned.append(float(entry))
            except (TypeError, ValueError):
                return []
        return cleaned


class ActivityItem(_Tolerant):
    name: str = ""
    action: str = ""
    time: str | None = None


class StyleInfo(_Tolerant):
    archetype: str = "operations-dashboard"
    density: str = "normal"  # "compact" | "normal"
    palette_description: str = ""


class HeroAsset(_Tolerant):
    """A rendered centerpiece living INSIDE the app's content area.

    This exists because of what image models are respectively best and worst
    at. They render photoreal subjects beautifully and garble dense small
    text; a screen that is all tables and axis ticks spends the entire
    canvas on the weakness. A hero asset moves roughly half the canvas onto
    the strength — and it is also what makes a screen look expensive rather
    than merely tidy.

    `treatment` is deliberately a closed vocabulary (see HERO_TREATMENTS):
    anything outside it drifts toward illustration and concept art, which
    is the look the pipeline has always refused.
    """

    subject: str = ""      # "a 30-storey residential tower at dusk"
    treatment: str = ""    # one of HERO_TREATMENTS
    caption: str = ""      # short overlay label, <= 4 words
    placement: str = "center"  # "center" | "left" | "right"

    @property
    def present(self) -> bool:
        return bool(self.subject.strip())


HERO_TREATMENTS = (
    "photoreal render",
    "product photograph",
    "aerial view",
    "plan view",
    "cinematic still",
    "material close-up",
)


class ConceptStep(_Tolerant):
    """One stage of a selection flow — "Select Block", options A/B/C, A chosen."""

    label: str = ""
    options: list[str] = Field(default_factory=list)
    selected: str = ""


class ConceptTurn(_Tolerant):
    """One message in a conversation — who spoke, and the words on screen.

    `speaker` is "customer" or "assistant" and decides which side of the
    thread the bubble sits on; anything else is treated as the customer,
    because a bubble on the wrong side is a smaller lie than a dropped
    message.
    """

    speaker: str = "customer"
    text: str = ""


class ScreenConcept(_Tolerant):
    """What KIND of screen this is, beyond a metrics overview.

    Before this field the spec could only describe a dashboard: greeting,
    four KPIs, a chart, two panels, an activity list. Every demo therefore
    came out as the same screen with different words in it. `kind` +
    `steps` let a screen be the thing a prospect actually pictures using —
    picking a unit, configuring an order, exploring a catalogue.

    `turns` is the same idea for the one product whose subject is not a
    choice at all. A business whose demo IS an AI assistant was, until
    session 38, coerced into a dashboard with "Chatbot" as the fourth item
    in its navigation (measured live, request 110) — the product it came to
    see reduced to a menu entry. A conversation is not a selection flow and
    cannot be described with steps and options, so it gets its own field
    and its own prompt block.
    """

    kind: str = "dashboard"  # see CONCEPT_KINDS
    steps: list[ConceptStep] = Field(default_factory=list)
    turns: list[ConceptTurn] = Field(default_factory=list)
    detail: Panel | None = None   # the panel the selection resolves to
    primary_action: str = ""      # "View Floor Plan"
    secondary_action: str = ""

    @property
    def is_tool(self) -> bool:
        return self.kind in TOOL_CONCEPT_KINDS and bool(self.steps)

    @property
    def is_conversation(self) -> bool:
        return self.kind == "assistant" and bool(self.turns)


CONCEPT_KINDS = ("dashboard", "selector", "configurator", "explorer", "assistant")
# "assistant" is deliberately NOT here. A tool screen is a selection flow
# rendered by _steps_block, and an assistant screen is a thread rendered by
# _conversation_block — sharing the flag would send a conversation through
# the steps layout, which is how it would have rendered before it had a
# shape of its own.
TOOL_CONCEPT_KINDS = ("selector", "configurator", "explorer")


class AiLayer(_Tolerant):
    """AI as a first-class module: a recommendation, why it was made, and how
    sure the system is — rather than a log of things AI did.

    Every string here is rendered as visible UI text, so every string here
    is short by construction; `rationale` is the one that wants to be a
    sentence and is the one most likely to garble.

    `title` exists because its absence was a defect factory (JOB 5, session
    34): six screens across the session-33 run drew a heading on this module
    that nobody asked for — "HERO INTELLIGENCE", "ONLY AI INTELLIGENCE",
    "PREMIUM AI INTELLIGENCE", "OPINION" — every one lifted from the prose
    nearest the panel. Session 33 removed the specific phrases it could
    find and the re-run invented new ones, because the panel had a VACANCY
    and the model fills vacancies from context. A field the spec stage
    fills with a real product label ("AI Insights", "Recommended Action")
    leaves nothing to be guessed. Empty = the pre-v3 briefs — rendered
    exactly as before, so briefs-v2 stays a valid control arm.
    """

    title: str = ""        # "AI Insights" — 2-3 words, a label a real product ships
    headline: str = ""     # "Recommended: A-1803"
    rationale: str = ""    # <= 8 words
    confidence: str = ""   # "94% match"
    chips: list[str] = Field(default_factory=list)  # 2-4 words each

    @property
    def present(self) -> bool:
        return bool(self.headline.strip())


class UIDemoSpec(_Tolerant):
    business: BusinessInfo = Field(default_factory=BusinessInfo)
    product: ProductInfo = Field(default_factory=ProductInfo)
    user: UserInfo = Field(default_factory=UserInfo)
    navigation: list[str] = Field(default_factory=list)
    # Which navigation item THIS screen is, when one of them is it.
    #
    # Session 39, request 130: the customer's own four items were honoured
    # exactly (Home, Gallery, About, Contact) and all three screens rendered
    # "Home" active, because active_nav_item can only match a nav label
    # against screen_title — and the titles are archetype roles (Dashboard,
    # Analytics, Customers). Nothing matched, so no screen was told what it
    # was, and the model defaulted every one of them to the first item. The
    # header was the customer's and the navigation state was dead.
    #
    # Matching titles to labels by similarity is the one thing not to do
    # here (see brand-variant specs: fuzzy rewriting is how invented
    # strings get in). The model already sees both the honoured list and
    # the screen's role, so it declares the mapping and code validates it
    # to death — must be a member of `navigation`, one screen per item,
    # empty otherwise.
    active_nav: str = ""
    greeting: str = ""
    subheading: str = ""
    kpis: list[Kpi] = Field(default_factory=list)
    primary_panel: Panel = Field(default_factory=Panel)
    secondary_panel: Panel | None = None
    chart: ChartSpec | None = None
    activity: list[ActivityItem] = Field(default_factory=list)
    style: StyleInfo = Field(default_factory=StyleInfo)
    hero: HeroAsset = Field(default_factory=HeroAsset)
    concept: ScreenConcept = Field(default_factory=ScreenConcept)
    ai: AiLayer = Field(default_factory=AiLayer)

    @property
    def screen_slug(self) -> str:
        from app.pipeline._shared import slugify

        return slugify(self.product.screen_type or "dashboard")

    @property
    def screen_title(self) -> str:
        return self.product.screen_type.replace("-", " ").title() if self.product.screen_type else "Dashboard"
