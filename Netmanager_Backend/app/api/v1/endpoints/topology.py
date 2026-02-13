import asyncio
import json
import ipaddress

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.db.session import get_db
from app.api import deps
from app.models.user import User
from app.models.topology import TopologyLayout
from app.schemas.topology import TopologyLayoutCreate, TopologyLayoutResponse
from app.services.path_trace_service import PathTraceService
from app.models.discovery import DiscoveryJob, DiscoveredDevice
from app.models.topology_candidate import TopologyNeighborCandidate
from app.services.candidate_recommendation_service import CandidateRecommendationService
from app.services.realtime_event_bus import realtime_event_bus
from app.services.topology_snapshot_service import TopologySnapshotService

router = APIRouter()


@router.get("/layout", response_model=Optional[TopologyLayoutResponse])
def get_user_layout(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer)
):
    """
    Get current user's saved topology layout.
    """
    layout = db.query(TopologyLayout).filter(
        TopologyLayout.user_id == current_user.id
    ).first()
    
    if not layout:
        # Check for a shared/default layout if user has none? (Optional)
        return None
        
    return layout

@router.post("/layout", response_model=TopologyLayoutResponse)
def save_user_layout(
    layout_in: TopologyLayoutCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator) # Only operators+ can save layouts? Or anyone?
):
    """
    Save or update user's topology layout.
    """
    existing_layout = db.query(TopologyLayout).filter(
        TopologyLayout.user_id == current_user.id
    ).first()

    if existing_layout:
        # Update existing
        existing_layout.data = layout_in.data
        existing_layout.updated_at = db.func.now()
        existing_layout.name = layout_in.name or existing_layout.name
        db.commit()
        db.refresh(existing_layout)
        return existing_layout
    else:
        # Create new
        new_layout = TopologyLayout(
            user_id=current_user.id,
            name=layout_in.name or "My Layout",
            data=layout_in.data,
            is_shared=layout_in.is_shared
        )
        db.add(new_layout)
        db.commit()
        db.refresh(new_layout)
        return new_layout

@router.delete("/layout")
def reset_user_layout(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator)
):
    """
    Delete user's saved layout (Reset).
    """
    db.query(TopologyLayout).filter(
        TopologyLayout.user_id == current_user.id
    ).delete()
    db.commit()
    return {"message": "Layout reset successfully"}


class PathTraceRequest(BaseModel):
    src_ip: str
    dst_ip: str


@router.post("/path-trace")
def path_trace(
    req: PathTraceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer)
):
    try:
        ipaddress.ip_address(req.src_ip)
    except ValueError:
        raise HTTPException(status_code=422, detail={"message": "Invalid src_ip", "field": "src_ip"})
    try:
        ipaddress.ip_address(req.dst_ip)
    except ValueError:
        raise HTTPException(status_code=422, detail={"message": "Invalid dst_ip", "field": "dst_ip"})

    service = PathTraceService(db)
    result = service.trace_path(req.src_ip, req.dst_ip)
    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(status_code=404, detail={"message": str(result.get("error")), "result": result})
    return result


@router.get("/stream")
async def stream_topology_events(
    request: Request,
):
    q = realtime_event_bus.subscribe()

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.to_thread(q.get, True, 15.0)
                    yield f"event: {msg.event}\ndata: {json.dumps(msg.data, ensure_ascii=False)}\n\n"
                except Exception:
                    yield "event: ping\ndata: {}\n\n"
        finally:
            realtime_event_bus.unsubscribe(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


class SnapshotCreateRequest(BaseModel):
    site_id: Optional[int] = None
    job_id: Optional[int] = None
    label: Optional[str] = None
    metadata: Optional[dict] = None


@router.get("/snapshots")
def list_topology_snapshots(
    site_id: Optional[int] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    return TopologySnapshotService.list_snapshots(db, site_id=site_id, limit=limit)


@router.post("/snapshots")
def create_topology_snapshot(
    req: SnapshotCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    snap = TopologySnapshotService.create_snapshot(
        db,
        site_id=req.site_id,
        job_id=req.job_id,
        label=req.label,
        metadata=req.metadata or {},
    )
    return TopologySnapshotService.to_dict(snap)


@router.get("/snapshots/{snapshot_id}")
def get_topology_snapshot(
    snapshot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    try:
        return TopologySnapshotService.get_snapshot_graph(db, snapshot_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/diff")
def diff_topology_snapshots(
    snapshot_a: int,
    snapshot_b: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    try:
        return TopologySnapshotService.diff_snapshots(db, snapshot_a, snapshot_b)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/candidates")
def list_topology_candidates(
    job_id: Optional[int] = None,
    source_device_id: Optional[int] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    order_by: str = "last_seen",
    order_dir: str = "desc",
    limit: int = 500,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer)
):
    query = db.query(TopologyNeighborCandidate)
    if job_id is not None:
        query = query.filter(TopologyNeighborCandidate.discovery_job_id == job_id)
    if source_device_id is not None:
        query = query.filter(TopologyNeighborCandidate.source_device_id == source_device_id)
    if status:
        query = query.filter(TopologyNeighborCandidate.status == status)
    if search:
        like = f"%{search}%"
        query = query.filter(
            (TopologyNeighborCandidate.neighbor_name.ilike(like))
            | (TopologyNeighborCandidate.mgmt_ip.ilike(like))
            | (TopologyNeighborCandidate.reason.ilike(like))
        )

    if limit < 1:
        limit = 1
    if limit > 2000:
        limit = 2000

    order_col = TopologyNeighborCandidate.last_seen
    if order_by == "confidence":
        order_col = TopologyNeighborCandidate.confidence
    elif order_by == "first_seen":
        order_col = TopologyNeighborCandidate.first_seen

    if order_dir.lower() == "asc":
        query = query.order_by(order_col.asc())
    else:
        query = query.order_by(order_col.desc())

    items = query.limit(limit).all()
    return [
        {
            "id": i.id,
            "discovery_job_id": i.discovery_job_id,
            "source_device_id": i.source_device_id,
            "neighbor_name": i.neighbor_name,
            "mgmt_ip": i.mgmt_ip,
            "local_interface": i.local_interface,
            "remote_interface": i.remote_interface,
            "protocol": i.protocol,
            "confidence": i.confidence,
            "reason": i.reason,
            "status": i.status,
            "first_seen": str(i.first_seen) if i.first_seen else None,
            "last_seen": str(i.last_seen) if i.last_seen else None,
        }
        for i in items
    ]


@router.get("/candidates/{candidate_id}/recommendations")
def candidate_recommendations(
    candidate_id: int,
    limit: int = 5,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    cand = db.query(TopologyNeighborCandidate).filter(TopologyNeighborCandidate.id == candidate_id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return CandidateRecommendationService.recommend_for_candidate(db, cand, limit=limit)


class CandidatePromoteRequest(BaseModel):
    job_id: Optional[int] = None
    ip_address: Optional[str] = None
    hostname: Optional[str] = None


@router.post("/candidates/{candidate_id}/promote")
def promote_candidate_to_discovery(
    candidate_id: int,
    req: CandidatePromoteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator)
):
    cand = db.query(TopologyNeighborCandidate).filter(TopologyNeighborCandidate.id == candidate_id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")

    job_id = req.job_id or cand.discovery_job_id
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id is required")

    job = db.query(DiscoveryJob).filter(DiscoveryJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Discovery job not found")

    ip_address = (req.ip_address or cand.mgmt_ip or "").strip()
    if not ip_address:
        raise HTTPException(status_code=400, detail="ip_address is required")

    hostname = (req.hostname or cand.neighbor_name or ip_address).strip()

    existing = db.query(DiscoveredDevice).filter(
        DiscoveredDevice.job_id == job_id,
        DiscoveredDevice.ip_address == ip_address,
    ).first()

    if existing:
        if not existing.hostname and hostname:
            existing.hostname = hostname
        if existing.status in ["ignored"]:
            existing.status = "new"
        discovered_id = existing.id
    else:
        discovered = DiscoveredDevice(
            job_id=job_id,
            ip_address=ip_address,
            hostname=hostname,
            vendor="Unknown",
            model=None,
            os_version=None,
            snmp_status="unknown",
            status="new",
            matched_device_id=None,
        )
        db.add(discovered)
        db.flush()
        discovered_id = discovered.id

    cand.mgmt_ip = ip_address
    cand.status = "promoted"
    db.commit()

    return {"message": "Promoted to discovery", "discovered_id": discovered_id}


@router.post("/candidates/{candidate_id}/ignore")
def ignore_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator)
):
    cand = db.query(TopologyNeighborCandidate).filter(TopologyNeighborCandidate.id == candidate_id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
    cand.status = "ignored"
    db.commit()
    return {"message": "Candidate ignored"}


class BulkIgnoreRequest(BaseModel):
    candidate_ids: List[int]


@router.post("/candidates/bulk-ignore")
def bulk_ignore_candidates(
    req: BulkIgnoreRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator)
):
    if not req.candidate_ids:
        return {"ignored": 0}
    ignored = db.query(TopologyNeighborCandidate).filter(
        TopologyNeighborCandidate.id.in_(req.candidate_ids)
    ).update({"status": "ignored"}, synchronize_session=False)
    db.commit()
    return {"ignored": int(ignored or 0)}


class BulkPromoteItem(BaseModel):
    candidate_id: int
    ip_address: Optional[str] = None
    hostname: Optional[str] = None


class BulkPromoteRequest(BaseModel):
    job_id: int
    items: List[BulkPromoteItem]


@router.post("/candidates/bulk-promote")
def bulk_promote_candidates(
    req: BulkPromoteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator)
):
    job = db.query(DiscoveryJob).filter(DiscoveryJob.id == req.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Discovery job not found")

    promoted = 0
    created = 0
    updated = 0
    skipped = 0

    for item in req.items or []:
        cand = db.query(TopologyNeighborCandidate).filter(TopologyNeighborCandidate.id == item.candidate_id).first()
        if not cand:
            skipped += 1
            continue

        ip_address = (item.ip_address or cand.mgmt_ip or "").strip()
        if not ip_address:
            skipped += 1
            continue

        hostname = (item.hostname or cand.neighbor_name or ip_address).strip()

        existing = db.query(DiscoveredDevice).filter(
            DiscoveredDevice.job_id == req.job_id,
            DiscoveredDevice.ip_address == ip_address,
        ).first()

        if existing:
            if not existing.hostname and hostname:
                existing.hostname = hostname
                updated += 1
        else:
            discovered = DiscoveredDevice(
                job_id=req.job_id,
                ip_address=ip_address,
                hostname=hostname,
                vendor="Unknown",
                model=None,
                os_version=None,
                snmp_status="unknown",
                status="new",
                matched_device_id=None,
            )
            db.add(discovered)
            created += 1

        cand.mgmt_ip = ip_address
        cand.status = "promoted"
        promoted += 1

    db.commit()
    return {"promoted": promoted, "created": created, "updated": updated, "skipped": skipped}
