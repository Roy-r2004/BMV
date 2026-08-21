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
    # The owner's own site/profile — distinct from reference_url, which is a
    # tool they admire, not their own business. Optional; the research stage
    # fetches it before analysis when present.
    site_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # How the business earns today, in the owner's words — the one intake
    # question that grounds the revenue-model half of the decomposition.
    revenue_today: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Which register the discovery numbers are in: "operating" (current
    # reality) or "opening" (a plan, no history yet). Nullable: intakes from
    # before the toggle existed.
    operating_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Which engagement this is: "full" (blueprint the whole business) or
    # "capability" (one solution scoped into an existing operation).
    # Nullable: intakes from before the toggle; treated as "full".
    engagement_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # The discovery Q&A as [{"question","answer"}] — whatever tailored
    # questions were asked, exactly as asked. A flexible list rather than
    # fixed columns: the right questions differ per business, and only
    # answered ones are stored. The decompose stage may compute ONLY with
    # these numbers.
    ops_numbers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The account that created this run. Null on legacy runs (public by
    # grandfathering); every run created after the auth gate carries one,
    # and only that account (or the reviewer) can open it.
    owner_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # The unguessable reference this run is addressed by in client-facing
    # URLs (/engagements/<public_id>). Sequential numeric ids remain valid
    # API references for legacy and showcase runs, but every owned run's
    # links use this. Null on legacy rows.
    public_id: Mapped[str | None] = mapped_column(String(32), unique=True, index=True, nullable=True)

    # Pipeline output.
    status: Mapped[str] = mapped_column(String(50), default="new")
    is_generating: Mapped[bool] = mapped_column(Boolean, default=True)
    is_failed: Mapped[bool] = mapped_column(Boolean, default=False)
    stage: Mapped[str] = mapped_column(String(50), default="queued")
    stage_label: Mapped[str] = mapped_column(String(200), default="Queued")
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    progress_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    business_analysis_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # {"source_url", "services", "hours", "tone", "highlights"} extracted
    # from site_url — null when no URL was given, the fetch failed, or the
    # page had too little real content to extract anything from.
    site_research_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The decomposition stage's output: the product broken into named
    # modules (each later deep-specced one by one) and the business case
    # (revenue streams, pricing levers, costs removed). Structure first,
    # prose second — the blueprint/technical documents are WRITTEN FROM
    # this, so their claims exist as data before they exist as sentences.
    modules_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_case_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The execution playbook: ordered real-world steps for the OWNER — what
    # to prepare, who to hire (or explicitly not hire), which third parties
    # to engage, what to watch after launch. The software build is one actor
    # in this plan, not the whole plan.
    playbook_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The consultancy layers built from the decomposition (extras.py):
    # the service-blueprint journey ({"stages": [...]}: customer action,
    # frontstage, backstage module ids per stage), the KPI scoreboard
    # (baselines only ever the owner's numbers or "measure in week 1"),
    # the risk register, and the franchise-manual core procedures
    # ({"procedures": [...]}: trigger, one-actor-per-step steps,
    # exceptions). All nullable: each layer fails open alone.
    journey_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    scoreboard_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    risks_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    procedures_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The organization layer: human + AI roles with decision rights, and
    # the per-human change impact that seeds the adoption plan.
    org_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The forms & checklists appendix of the operations manual:
    # {"checklists": [...], "forms": [...]} — the artifacts staff hold.
    checklists_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The human review gate: null (legacy runs — treated as released),
    # "pending" (finished, awaiting the reviewer), "approved" (released).
    review_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # The quality bench's verdict: {"checks": [...], "findings": [...],
    # "polish_applied": bool}. Shown in full to the reviewer; the client's
    # pending page sees only the check labels and pass marks.
    qa_report_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The typed claim registry (app/pipeline/registry.py): every release-
    # critical number as a record — client facts, verified derivations,
    # the canonical pilot gate, typed thresholds, module KPI statements,
    # module metadata. Documents are rendered FROM it and validated AGAINST
    # it. Null on runs generated before the registry existed.
    registry_json: Mapped[str | None] = mapped_column(Text, nullable=True)
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
