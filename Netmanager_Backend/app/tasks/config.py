from celery import shared_task
from app.services.ssh_service import DeviceConnection, DeviceInfo
from app.services.parser_service import CLIAnalyzer
from app.models.device import ConfigBackup, Device
from app.models.config_template import ConfigTemplate
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
import datetime

@shared_task
def pull_and_parse_config(device_id: int):
    db: Session = SessionLocal()
    try:
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device:
            return {"status": "error", "message": "Device not found"}

        target_device = DeviceInfo(
            name=device.name, host=device.host, username=device.username,
            password=device.password, enable_password=device.secret,
            device_type=device.device_type, port=device.port
        )

        connection = DeviceConnection(target_device)
        if not connection.connect():
            return {"status": "error", "message": connection.last_error}

        raw_run = connection.get_running_config()
        raw_vlan = connection.send_command("show vlan brief")
        connection.disconnect()

        parsed = CLIAnalyzer.analyze_multiple_commands({
            'show run': raw_run,
            'show vlan': raw_vlan
        })

        new_backup = ConfigBackup(
            device_id=device.id,
            raw_config=raw_run,
            parsed_config=parsed
        )
        db.add(new_backup)
        db.commit()
        db.refresh(new_backup)
        return {"status": "success", "backup_id": new_backup.id}
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        db.close()

@shared_task
def deploy_config_task(device_id: int, template_id: int):
    db: Session = SessionLocal()
    try:
        device = db.query(Device).filter(Device.id == device_id).first()
        template = db.query(ConfigTemplate).filter(ConfigTemplate.id == template_id).first()
        if not device:
            return {"status": "error", "message": "Device not found"}
        if not template:
            return {"status": "error", "message": "Template not found"}

        target_device = DeviceInfo(
            name=device.name,
            host=device.host,
            username=device.username,
            password=device.password,
            enable_password=device.secret,
            device_type=device.device_type,
            port=device.port
        )

        connection = DeviceConnection(target_device)
        if not connection.connect():
            return {"status": "error", "message": f"Connection failed: {connection.last_error}"}

        # 템플릿 명령어 줄 단위로 분리
        commands = [cmd.strip() for cmd in template.template_text.splitlines() if cmd.strip()]

        output = connection.send_commands(commands)
        connection.disconnect()

        # 배포 성공 로그 (옵션: ConfigBackup에 저장하거나 별도 로그 테이블)
        return {"status": "success", "output": output}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        db.close()