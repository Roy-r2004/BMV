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

    @property
    def screen_slug(self) -> str:
        from app.pipeline._shared import slugify

        return slugify(self.product.screen_type or "dashboard")

    @property
    def screen_title(self) -> str:
        return self.product.screen_type.replace("-", " ").title() if self.product.screen_type else "Dashboard"
