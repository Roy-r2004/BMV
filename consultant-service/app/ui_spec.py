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

from pydantic import BaseModel, ConfigDict, Field


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


class ScreenConcept(_Tolerant):
    """What KIND of screen this is, beyond a metrics overview.

    Before this field the spec could only describe a dashboard: greeting,
    four KPIs, a chart, two panels, an activity list. Every demo therefore
    came out as the same screen with different words in it. `kind` +
    `steps` let a screen be the thing a prospect actually pictures using —
    picking a unit, configuring an order, exploring a catalogue.
    """

    kind: str = "dashboard"  # see CONCEPT_KINDS
    steps: list[ConceptStep] = Field(default_factory=list)
    detail: Panel | None = None   # the panel the selection resolves to
    primary_action: str = ""      # "View Floor Plan"
    secondary_action: str = ""

    @property
    def is_tool(self) -> bool:
        return self.kind in TOOL_CONCEPT_KINDS and bool(self.steps)


CONCEPT_KINDS = ("dashboard", "selector", "configurator", "explorer", "assistant")
TOOL_CONCEPT_KINDS = ("selector", "configurator", "explorer", "assistant")


class AiLayer(_Tolerant):
    """AI as a first-class module: a recommendation, why it was made, and how
    sure the system is — rather than a log of things AI did.

    Every string here is rendered as visible UI text, so every string here
    is short by construction; `rationale` is the one that wants to be a
    sentence and is the one most likely to garble.
    """

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
