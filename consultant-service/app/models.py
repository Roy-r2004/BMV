from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Request(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Intake fields — same names SubmitWizard.tsx already sends.
    business_name: Mapped[str] = mapped_column(String(200))
    business_description: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(String(200))
    industry: Mapped[str | None] = mapped_column(String(200), nullable=True)
    target_customers: Mapped[str | None] = mapped_column(Text, nullable=True)
    main_problem: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    what_you_like: Mapped[str | None] = mapped_column(Text, nullable=True)
    desired_outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_ai: Mapped[str | None] = mapped_column(String(50), nullable=True)
    budget_range: Mapped[str | None] = mapped_column(String(100), nullable=True)
    timeline: Mapped[str | None] = mapped_column(String(100), nullable=True)
    whatsapp: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Pipeline output.
    status: Mapped[str] = mapped_column(String(50), default="new")
    is_generating: Mapped[bool] = mapped_column(Boolean, default=True)
    is_failed: Mapped[bool] = mapped_column(Boolean, default=False)
    stage: Mapped[str] = mapped_column(String(50), default="queued")
    stage_label: Mapped[str] = mapped_column(String(200), default="Queued")
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    progress_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    business_analysis_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    consulting_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    consulting_recommendations_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    concept_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    mvp_blueprint: Mapped[str | None] = mapped_column(Text, nullable=True)
    technical_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    visual_theme_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    roles_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    images: Mapped[list["GeneratedImage"]] = relationship(back_populates="request", cascade="all, delete-orphan")


class GeneratedImage(Base):
    __tablename__ = "generated_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"))
    role_id: Mapped[str] = mapped_column(String(100))
    role_label: Mapped[str] = mapped_column(String(200))
    variant: Mapped[int] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(String(500))
    prompt: Mapped[str] = mapped_column(Text)

    # Demo-screenshot metadata — lets prompt/model performance be compared
    # across versions later. All nullable: rows from the earlier per-employee
    # image pipeline predate these.
    screen_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    archetype: Mapped[str | None] = mapped_column(String(50), nullable=True)
    composition_variant: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    qa_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    qa_issues: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The W3 gate's verdict for the SHIPPED candidate, as JSON. On disk in the
    # per-screen metadata file since session 31; on the row since session 33,
    # because the operator view is where "did this screen spell the client's
    # name right" has to be answerable, and an operator does not read
    # uploads/images/<id>/*.json. Null for rows written before the column
    # existed, and for runs with the gate off — neither means "passed".
    text_truth_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The UIDemoSpec this screen was drawn FROM, as JSON. Until session 35 the
    # spec was transient — built, rendered into a prompt, discarded — so
    # nothing downstream could say what a finished screen contains. The
    # customer's result page needs exactly that: the screen's own subheading,
    # the metrics it tracks, and the AI module drawn on it. Every string here
    # is one the image was asked to render, which is what makes the
    # explanation under a screen checkable against the screen itself rather
    # than prose invented about it. Null for rows written before the column
    # existed — which means "we cannot say", never "this screen has no AI".
    spec_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    request: Mapped[Request] = relationship(back_populates="images")


class AiUsageEvent(Base):
    __tablename__ = "ai_usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int | None] = mapped_column(ForeignKey("requests.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(200))
    purpose: Mapped[str] = mapped_column(String(100))
    # Which screen this call was spent on (GeneratedImage.role_id), when the
    # call belongs to one. Null for the text stages, which are per-request.
    # Without it a request's cost is one number and "which screen burned it"
    # is unanswerable — and the regeneration tail, the thing that actually
    # moves a request from $0.46 to $0.53, is invisible.
    screen: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
