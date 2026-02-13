import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from app.db.session import get_db
from app.db.session import get_db
from app.services.discovery_service import DiscoveryService
from app.db.session import SessionLocal
from app.models.discovery import DiscoveryJob, DiscoveredDevice
from app.tasks.discovery import run_discovery_job
from app.tasks.topology_refresh import refresh_device_topology
from app.tasks.device_sync import enqueue_ssh_sync_batch
from app.tasks.neighbor_crawl import run_neighbor_crawl_job
from app.models.settings import SystemSetting

router = APIRouter()

# --- Pydantic Schemas ---

class ScanRequest(BaseModel):
    cidr: str
    site_id: Optional[int] = None
    snmp_profile_id: Optional[int] = None
    community: str = "public"
    snmp_version: str = "v2c"
    snmp_port: int = 161
    snmp_v3_username: Optional[str] = None
    snmp_v3_security_level: Optional[str] = None
    snmp_v3_auth_proto: Optional[str] = None
    snmp_v3_auth_key: Optional[str] = None
    snmp_v3_priv_proto: Optional[str] = None
    snmp_v3_priv_key: Optional[str] = None


class CrawlRequest(BaseModel):
    seed_device_id: Optional[int] = None
    seed_ip: Optional[str] = None
    max_depth: int = 2
    site_id: Optional[int] = None
    snmp_profile_id: Optional[int] = None
    community: str = "public"
    snmp_version: str = "v2c"
    snmp_port: int = 161
    snmp_v3_username: Optional[str] = None
    snmp_v3_security_level: Optional[str] = None
    snmp_v3_auth_proto: Optional[str] = None
    snmp_v3_auth_key: Optional[str] = None
    snmp_v3_priv_proto: Optional[str] = None
    snmp_v3_priv_key: Optional[str] = None

class JobResponse(BaseModel):
    id: int
    cidr: str
    status: str
    progress: int = 0 # percent
    logs: str
    created_at: str

class DeviceResponse(BaseModel):
    id: int
    ip_address: str
    hostname: Optional[str]
    vendor: Optional[str]
    model: Optional[str] = None
    os_version: Optional[str] = None
    device_type: Optional[str] = None
    status: str # new, existing, approved
    snmp_status: str
    vendor_confidence: Optional[float] = 0.0
    chassis_candidate: Optional[bool] = False
    matched_device_id: Optional[int] = None
    issues: Optional[List[Dict[str, Any]]] = None
    evidence: Optional[Dict[str, Any]] = None

# --- Endpoints ---

@router.post("/scan", response_model=JobResponse)
def start_scan(
    request: ScanRequest, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    service = DiscoveryService(db)
    
    # 1. Create Job (Sync)
    job = service.create_scan_job(
        request.cidr,
        request.community,
        site_id=request.site_id,
        snmp_profile_id=request.snmp_profile_id,
        snmp_version=request.snmp_version,
        snmp_port=request.snmp_port,
        snmp_v3_username=request.snmp_v3_username,
        snmp_v3_security_level=request.snmp_v3_security_level,
        snmp_v3_auth_proto=request.snmp_v3_auth_proto,
        snmp_v3_auth_key=request.snmp_v3_auth_key,
        snmp_v3_priv_proto=request.snmp_v3_priv_proto,
        snmp_v3_priv_key=request.snmp_v3_priv_key,
    )
    
    # 2. Run scan asynchronously (prefer Celery worker; fallback to FastAPI background task)
    try:
        run_discovery_job.delay(job.id)
    except Exception:
        background_tasks.add_task(service.run_scan_worker, job.id)
    
    return {
        "id": job.id,
        "cidr": job.cidr,
        "status": job.status,
        "logs": job.logs,
        "created_at": str(job.created_at)
    }


@router.post("/crawl", response_model=JobResponse)
def start_neighbor_crawl(
    request: CrawlRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    service = DiscoveryService(db)
    seed_ip = str(request.seed_ip or "").strip()
    seed_device_id = request.seed_device_id
    if not seed_ip and seed_device_id is None:
        raise HTTPException(status_code=400, detail="seed_device_id or seed_ip is required")
    cidr = f"seedip:{seed_ip}" if seed_ip else f"seed:{seed_device_id}"
    job = service.create_scan_job(
        cidr,
        request.community,
        site_id=request.site_id,
        snmp_profile_id=request.snmp_profile_id,
        snmp_version=request.snmp_version,
        snmp_port=request.snmp_port,
        snmp_v3_username=request.snmp_v3_username,
        snmp_v3_security_level=request.snmp_v3_security_level,
        snmp_v3_auth_proto=request.snmp_v3_auth_proto,
        snmp_v3_auth_key=request.snmp_v3_auth_key,
        snmp_v3_priv_proto=request.snmp_v3_priv_proto,
        snmp_v3_priv_key=request.snmp_v3_priv_key,
    )

    try:
        run_neighbor_crawl_job.delay(job.id, seed_device_id, seed_ip, request.max_depth)
    except Exception:
        from app.db.session import SessionLocal
        from app.services.neighbor_crawl_service import NeighborCrawlService

        def _run():
            _db = SessionLocal()
            try:
                NeighborCrawlService(_db).run_neighbor_crawl(job.id, seed_device_id=seed_device_id, seed_ip=seed_ip, max_depth=request.max_depth)
            finally:
                _db.close()

        background_tasks.add_task(_run)

    return {
        "id": job.id,
        "cidr": job.cidr,
        "status": job.status,
        "logs": job.logs,
        "created_at": str(job.created_at),
    }

@router.get("/jobs/{id}")
def get_job_status(id: int, db: Session = Depends(get_db)):
    job = db.query(DiscoveryJob).filter(DiscoveryJob.id == id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Calculate progress
    progress = 0
    if job.total_ips > 0:
        progress = int((job.scanned_ips / job.total_ips) * 100)
    elif job.status == 'completed':
        progress = 100
        
    return {
        "id": job.id,
        "cidr": job.cidr,
        "status": job.status,
        "progress": progress,
        "logs": job.logs,
        "created_at": str(job.created_at)
    }

@router.get("/jobs/{id}/results", response_model=List[DeviceResponse])
def get_job_results(id: int, db: Session = Depends(get_db)):
    results = db.query(DiscoveredDevice).filter(DiscoveredDevice.job_id == id).all()
    return [
        {
            "id": r.id,
            "ip_address": r.ip_address,
            "hostname": r.hostname,
            "vendor": r.vendor,
            "model": r.model,
            "os_version": r.os_version,
            "device_type": r.device_type,
            "status": r.status,
            "snmp_status": r.snmp_status,
            "vendor_confidence": getattr(r, "vendor_confidence", 0.0),
            "chassis_candidate": getattr(r, "chassis_candidate", False),
            "matched_device_id": getattr(r, "matched_device_id", None),
            "issues": getattr(r, "issues", None),
            "evidence": getattr(r, "evidence", None),
        }
        for r in results
    ]


@router.get("/jobs/{id}/stream")
async def stream_job_results(id: int):
    async def event_generator():
        last_id = 0
        while True:
            db = SessionLocal()
            try:
                job = db.query(DiscoveryJob).filter(DiscoveryJob.id == id).first()
                if not job:
                    payload = json.dumps({"error": "Job not found"}, ensure_ascii=False)
                    yield f"event: error\ndata: {payload}\n\n"
                    return

                rows = (
                    db.query(DiscoveredDevice)
                    .filter(DiscoveredDevice.job_id == id, DiscoveredDevice.id > last_id)
                    .order_by(DiscoveredDevice.id.asc())
                    .limit(200)
                    .all()
                )

                for r in rows:
                    data = {
                        "id": r.id,
                        "ip_address": r.ip_address,
                        "hostname": r.hostname,
                        "vendor": r.vendor,
                        "model": r.model,
                        "os_version": r.os_version,
                        "device_type": r.device_type,
                        "status": r.status,
                        "snmp_status": r.snmp_status,
                        "vendor_confidence": getattr(r, "vendor_confidence", 0.0),
                        "chassis_candidate": getattr(r, "chassis_candidate", False),
                        "matched_device_id": getattr(r, "matched_device_id", None),
                        "issues": getattr(r, "issues", None),
                        "evidence": getattr(r, "evidence", None),
                    }
                    last_id = r.id
                    yield f"event: device\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

                total = int(getattr(job, "total_ips", 0) or 0)
                scanned = int(getattr(job, "scanned_ips", 0) or 0)
                pct = int((scanned / total) * 100) if total > 0 else (100 if job.status == "completed" else 0)
                progress_data = {"status": job.status, "scanned_ips": scanned, "total_ips": total, "progress": pct}
                yield f"event: progress\ndata: {json.dumps(progress_data, ensure_ascii=False)}\n\n"

                if job.status in ("completed", "failed") and not rows:
                    yield f"event: done\ndata: {json.dumps({'status': job.status}, ensure_ascii=False)}\n\n"
                    return
            finally:
                db.close()

            await asyncio.sleep(0.8)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@router.post("/approve/{id}")
def approve_device(id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    service = DiscoveryService(db)
    discovered = db.query(DiscoveredDevice).filter(DiscoveredDevice.id == id).first()
    if not discovered:
        raise HTTPException(status_code=404, detail="Discovered device not found")
    device = service.approve_device(id)
    if not device:
        raise HTTPException(status_code=404, detail="Discovered device not found")

    try:
        refresh_device_topology.delay(device.id, discovered.job_id, 2)
    except Exception:
        pass

    try:
        def _get_setting_value(key: str) -> str:
            setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
            return setting.value if setting and setting.value and setting.value != "********" else ""

        enabled = (_get_setting_value("auto_sync_enabled") or "true").strip().lower() in ("true", "1", "yes", "y", "on")
        interval = float(_get_setting_value("auto_sync_interval_seconds") or 3)
        jitter = float(_get_setting_value("auto_sync_jitter_seconds") or 0.5)

        if enabled:
            enqueue_ssh_sync_batch.delay([device.id], interval, jitter)
    except Exception:
        from app.services.device_sync_service import DeviceSyncService
        background_tasks.add_task(DeviceSyncService.sync_device_job, device.id)
    else:
        from app.services.device_sync_service import DeviceSyncService
        background_tasks.add_task(DeviceSyncService.sync_device_job, device.id)

    try:
        from app.tasks.monitoring import burst_monitor_devices
        burst_monitor_devices.delay([device.id], 3, 5)
    except Exception:
        pass

    return {"message": "Device approved", "device_id": device.id}


@router.post("/ignore/{id}")
def ignore_device(id: int, db: Session = Depends(get_db)):
    discovered = db.query(DiscoveredDevice).filter(DiscoveredDevice.id == id).first()
    if not discovered:
        raise HTTPException(status_code=404, detail="Discovered device not found")
    discovered.status = "ignored"
    db.commit()
    return {"message": "Device ignored"}


@router.post("/jobs/{id}/approve-all")
def approve_all_new_devices(id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    service = DiscoveryService(db)
    discovered_list = db.query(DiscoveredDevice).filter(
        DiscoveredDevice.job_id == id,
        DiscoveredDevice.status == "new",
    ).all()

    approved_ids = []
    skipped = 0
    for discovered in discovered_list:
        try:
            device = service.approve_device(discovered.id)
            if device:
                approved_ids.append(device.id)
        except Exception:
            skipped += 1

    for device_id in approved_ids:
        try:
            refresh_device_topology.delay(device_id, id, 2)
        except Exception:
            pass

    try:
        def _get_setting_value(key: str) -> str:
            setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
            return setting.value if setting and setting.value and setting.value != "********" else ""

        enabled = (_get_setting_value("auto_sync_enabled") or "true").strip().lower() in ("true", "1", "yes", "y", "on")
        interval = float(_get_setting_value("auto_sync_interval_seconds") or 3)
        jitter = float(_get_setting_value("auto_sync_jitter_seconds") or 0.5)

        if enabled and approved_ids:
            enqueue_ssh_sync_batch.delay(approved_ids, interval, jitter)
    except Exception:
        from app.services.device_sync_service import DeviceSyncService
        for device_id in approved_ids:
            background_tasks.add_task(DeviceSyncService.sync_device_job, device_id)
    else:
        from app.services.device_sync_service import DeviceSyncService

        def _sync_all():
            for device_id in approved_ids:
                try:
                    DeviceSyncService.sync_device_job(device_id)
                except Exception:
                    continue

        if approved_ids:
            background_tasks.add_task(_sync_all)

    try:
        from app.tasks.monitoring import burst_monitor_devices
        if approved_ids:
            burst_monitor_devices.delay(approved_ids, 3, 5)
    except Exception:
        pass

    return {"approved_count": len(approved_ids), "skipped_count": skipped, "device_ids": approved_ids}
