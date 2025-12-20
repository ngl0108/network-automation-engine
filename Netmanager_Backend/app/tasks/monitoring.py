from celery import shared_task
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.device import Device
from app.services.snmp_service import SnmpManager
import datetime

@shared_task
def monitor_all_devices():
    print(f"[{datetime.datetime.now()}] Celery: Starting monitoring job...")

    db: Session = SessionLocal()
    try:
        devices = db.query(Device).all()

        for device in devices:
            snmp = SnmpManager(target_ip=device.host, community=device.snmp_community)
            status_data = snmp.check_status()
            new_status = status_data['status']

            device.status = new_status
            device.updated_at = datetime.datetime.now()

            print(f"  - {device.name} ({device.host}): {new_status}")

            if new_status == 'online':
                try:
                    resources = snmp.get_resource_usage()
                    if resources:
                        print(f"    CPU: {resources['cpu_usage']}%, Mem: {resources['memory_usage']}%")
                        # TODO: 나중에 metrics_history 테이블에 저장
                except Exception as e:
                    print(f"    Resource check failed: {e}")

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Celery monitoring error: {e}")
    finally:
        db.close()

    print("Celery monitoring job finished.\n")