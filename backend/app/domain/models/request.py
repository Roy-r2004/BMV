from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.infrastructure.db.base import Base


class Request(Base):
    __tablename__ = "requests"

    id = Column(Integer, primary_key=True, index=True)

    business_name = Column(String, nullable=False)
    industry = Column(String, nullable=True)
    business_description = Column(Text, nullable=False)
    target_customers = Column(Text, nullable=True)
    main_problem = Column(Text, nullable=True)

    reference_url = Column(String, nullable=True)
    reference_file_path = Column(String, nullable=True)

    what_you_like = Column(Text, nullable=True)
    desired_outcome = Column(Text, nullable=True)
    project_type = Column(String, nullable=True)        # 'new' | 'enhance' | 'automate'
    existing_product_url = Column(String, nullable=True) # URL of existing product (enhance mode)
    needs_ai = Column(String, nullable=True)
    budget_range = Column(String, nullable=True)
    timeline = Column(String, nullable=True)

    email = Column(String, nullable=False)
    whatsapp = Column(String, nullable=True)

    status = Column(String, default="new")
    admin_notes = Column(Text, nullable=True)

    screenshot_analysis = Column(Text, nullable=True)
    mvp_blueprint = Column(Text, nullable=True)
    visual_demo_json = Column(Text, nullable=True)
    technical_plan = Column(Text, nullable=True)
    proposal_draft = Column(Text, nullable=True)

    business_fit_score = Column(Integer, nullable=True)
    concept_name = Column(String, nullable=True)
    preview_summary = Column(Text, nullable=True)
    preview_features = Column(Text, nullable=True)

    reference_metadata = Column(Text, nullable=True)

    generation_log = Column(Text, nullable=True)  # JSON progress snapshot written during generation

    build_requested = Column(Boolean, default=False)
    build_requested_at = Column(DateTime, nullable=True)

    visual_demo_generated_at = Column(DateTime, nullable=True)
    generated_pages = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
