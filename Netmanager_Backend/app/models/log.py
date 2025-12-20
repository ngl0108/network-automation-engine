from sqlalchemy import Column, Integer, String, DateTime, Text
from app.db.base import Base
from datetime import datetime

class EventLog(Base):
    __tablename__ = "event_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    severity = Column(String(20))  # CRITICAL, WARNING, INFO
    source = Column(String(50))    # 장비 이름 or IP
    event_id = Column(String(50))  # LINK_DOWN, HIGH_CPU 등
    message = Column(Text)

    device_id = Column(Integer)    # devices 테이블 FK (옵션)