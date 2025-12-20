from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.schemas.device import DeviceAuthRequest, DeviceAuthResponse, DeviceCreate, DeviceResponse
from app.services.ssh_service import DeviceConnection, DeviceInfo
from app.db.session import get_db
from app.models.device import Device  # DB 모델

router = APIRouter()


# ... (기존 /connect 코드는 그대로 두세요) ...

# [신규] 장비 목록 조회 API
@router.get("/", response_model=List[DeviceResponse])
def read_devices(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    등록된 모든 장비 목록을 반환합니다.
    """
    devices = db.query(Device).offset(skip).limit(limit).all()
    return devices


# [신규] 장비 등록 API
@router.post("/", response_model=DeviceResponse)
def create_device(device_in: DeviceCreate, db: Session = Depends(get_db)):
    """
    새로운 장비를 데이터베이스에 등록합니다.
    """
    # 중복 이름 체크
    existing_device = db.query(Device).filter(Device.name == device_in.name).first()
    if existing_device:
        raise HTTPException(status_code=400, detail="이미 등록된 장비 이름입니다.")

    # DB 모델 생성
    new_device = Device(
        name=device_in.name,
        host=device_in.host,
        username=device_in.username,
        password=device_in.password,
        secret=device_in.secret,
        device_type=device_in.device_type,
        port=device_in.port,
        snmp_community=device_in.snmp_community,
        status="unknown"
    )

    db.add(new_device)
    db.commit()
    db.refresh(new_device)
    return new_device