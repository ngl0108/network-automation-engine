from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    host = Column(String, nullable=False)
    username = Column(String, nullable=True)
    password = Column(String, nullable=True)  # 실제 배포 시 암호화 필요
    secret = Column(String, nullable=True)
    device_type = Column(String, default="cisco_ios")
    port = Column(Integer, default=22)

    # 모니터링 관련 필드
    snmp_community = Column(String, default="public")
    snmp_version = Column(Integer, default=2)
    status = Column(String, default="unknown")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # [추가] 백업 테이블과의 관계 설정 (1:N)
    backups = relationship("ConfigBackup", back_populates="device", cascade="all, delete-orphan")


class ConfigBackup(Base):
    __tablename__ = "config_backups"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"))

    # 원본 설정 (Raw Text)
    raw_config = Column(Text, nullable=True)

    # 파싱된 설정 (JSON 구조)
    parsed_config = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 관계 설정
    device = relationship("Device", back_populates="backups")