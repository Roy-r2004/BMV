from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.infrastructure.db.base import Base


class PreviewChatMessage(Base):
    __tablename__ = "preview_chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, index=True, nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
