from sqlalchemy import Column, Integer, String, Text, DateTime
from app.db.base import Base
from datetime import datetime

class ConfigTemplate(Base):
    __tablename__ = "config_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True)
    description = Column(String(255))
    template_text = Column(Text)  # CLI 명령어 템플릿
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)