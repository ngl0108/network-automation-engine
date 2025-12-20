from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

# --- 장비 관련 스키마 ---
class DeviceCreate(BaseModel):
    name: str
    host: str
    username: str
    password: str
    secret: Optional[str] = None
    device_type: str = "cisco_ios"
    port: int = 22
    snmp_community: str = "public"

class DeviceResponse(DeviceCreate):
    id: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

# --- 연결 테스트용 스키마 ---
class DeviceAuthRequest(BaseModel):
    host: str
    username: str
    password: str
    secret: Optional[str] = None
    device_type: str = "cisco_ios"
    port: int = 22

class DeviceAuthResponse(BaseModel):
    status: str
    message: str
    device_info: dict = {}

# --- [추가] 설정 백업 응답 스키마 ---
class ConfigBackupResponse(BaseModel):
    id: int
    device_id: int
    parsed_config: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True