from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.models.device import Device, ConfigBackup
from app.models.config_template import ConfigTemplate  # 템플릿 모델 추가
from app.schemas.device import ConfigBackupResponse
from app.services.ssh_service import DeviceConnection, DeviceInfo
from app.services.parser_service import CLIAnalyzer
from app.tasks.config import pull_and_parse_config, deploy_config_task  # 배포 태스크 추가

router = APIRouter()


@router.post("/pull/{device_id}", response_model=ConfigBackupResponse)
def pull_config_from_device(device_id: int, db: Session = Depends(get_db)):
    """
    지정된 장비(ID)에 SSH로 접속하여 설정을 가져오고, 파싱하여 DB에 저장합니다.
    """
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="장비를 찾을 수 없습니다.")

    task = pull_and_parse_config.delay(device_id)

    raise HTTPException(status_code=202, detail={
        "message": "Config pull 요청이 접수되었습니다. 백그라운드에서 처리 중입니다.",
        "task_id": task.id
    })


@router.get("/history/{device_id}", response_model=List[ConfigBackupResponse])
def get_config_history(device_id: int, db: Session = Depends(get_db)):
    """
    특정 장비의 설정 백업 이력을 최신순으로 조회합니다.
    """
    backups = db.query(ConfigBackup) \
        .filter(ConfigBackup.device_id == device_id) \
        .order_by(ConfigBackup.created_at.desc()) \
        .all()
    return backups


@router.post("/deploy/{device_id}/{template_id}")
def deploy_config(device_id: int, template_id: int, db: Session = Depends(get_db)):
    """
    지정된 장비에 템플릿 기반으로 Config 배포 요청
    """
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="장비를 찾을 수 없습니다.")

    template = db.query(ConfigTemplate).filter(ConfigTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다.")

    task = deploy_config_task.delay(device_id, template_id)

    return {"message": "Config 배포 요청이 접수되었습니다. 백그라운드에서 처리 중입니다.", "task_id": task.id}