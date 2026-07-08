from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from app.infrastructure.db.base import Base


class SolutionWorkspace(Base):
    """Per-user customization layer on top of the shared industry template."""

    __tablename__ = "solution_workspaces"
    __table_args__ = (UniqueConstraint("user_id", "solution_id", name="uq_user_solution"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    solution_id = Column(String, nullable=False, index=True)
    overlay_json = Column(Text, default="{}")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class SolutionEditMessage(Base):
    __tablename__ = "solution_edit_messages"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("solution_workspaces.id"), nullable=False, index=True)
    role = Column(String, nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    attachment_name = Column(String, nullable=True)
    attachment_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
