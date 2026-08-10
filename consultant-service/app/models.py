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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    request: Mapped[Request] = relationship(back_populates="images")


class AiUsageEvent(Base):
    __tablename__ = "ai_usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int | None] = mapped_column(ForeignKey("requests.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(200))
    purpose: Mapped[str] = mapped_column(String(100))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
