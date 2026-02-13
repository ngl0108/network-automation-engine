from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload
from typing import List
import random
from datetime import datetime, timedelta

from app.db.session import get_db
# [수정] Issue, ComplianceReport, SystemMetric 모델 추가 임포트
from app.models.device import Site, FirmwareImage, Policy, Device, ConfigTemplate, Issue, ComplianceReport, SystemMetric
from app.models.user import User
from app.schemas.device import (
    SiteResponse, FirmwareImageResponse, PolicyResponse, UserResponse,
    Token, UserLogin, DashboardStats
)

router = APIRouter()


@router.get("/dashboard/stats")
def get_dashboard_stats(
    site_id: int = Query(None),
    db: Session = Depends(get_db)
):
    # 1. Device Filtering
    device_query = db.query(Device)
    if site_id:
        device_query = device_query.filter(Device.site_id == site_id)
    
    all_devices = device_query.all()
    target_ids = [d.id for d in all_devices]
    total_devices = len(all_devices)
    
    # Counts
    total_sites = db.query(Site).count()
    total_policies = db.query(Policy).count()
    if site_id:
        total_policies = db.query(Policy).filter(Policy.site_id == site_id).count()

    total_images = db.query(FirmwareImage).count() # Global Image
    
    # [FIX] Filter compliance count by target devices (respecting site_id)
    compliant_cnt = 0
    if target_ids:
        compliant_cnt = db.query(ComplianceReport).filter(
            ComplianceReport.status == 'compliant',
            ComplianceReport.device_id.in_(target_ids)
        ).count()

    online_cnt = 0
    alert_cnt = 0
    total_aps = 0
    total_clients = 0

    for dev in all_devices:
        status_text = str(dev.status or "offline").lower().strip()
        if status_text in ['online', 'reachable', 'up']:
            online_cnt += 1
        elif status_text in ['alert', 'warning', 'degraded']:
            alert_cnt += 1

        # [Wireless Aggregate]
        if dev.latest_parsed_data and isinstance(dev.latest_parsed_data, dict):
            w_data = dev.latest_parsed_data
            wireless_nested = w_data.get("wireless", {}) if isinstance(w_data.get("wireless"), dict) else {}
            
            c_count = w_data.get("total_clients")
            if c_count is None:
                c_count = wireless_nested.get("total_clients", 0)
            total_clients += int(c_count or 0)
            
            ap_list = wireless_nested.get("ap_list", [])
            if ap_list and isinstance(ap_list, list):
                total_aps += sum(1 for ap in ap_list if str(ap.get("status", "")).lower() in ('up', 'online', 'registered', 'reg'))
            elif "up_aps" in wireless_nested:
                total_aps += wireless_nested.get("up_aps", 0)
            elif "up_aps" in w_data:
                total_aps += w_data.get("up_aps", 0)

    offline_cnt = total_devices - (online_cnt + alert_cnt)
    if offline_cnt < 0: offline_cnt = 0

    # Health Score
    current_health_score = 0
    if total_devices > 0:
        score = ((online_cnt - (alert_cnt * 0.5)) / total_devices) * 100
        current_health_score = int(max(0, min(100, score)))

    # Traffic Trend (Real Data)
    traffic_trend = []
    if target_ids:
        ten_mins_ago = datetime.now() - timedelta(minutes=10)
        metrics = db.query(SystemMetric)\
            .filter(SystemMetric.device_id.in_(target_ids))\
            .filter(SystemMetric.timestamp >= ten_mins_ago)\
            .order_by(SystemMetric.timestamp.asc())\
            .all()
        
        trend_map = {} 
        for m in metrics:
            t_str = m.timestamp.strftime("%H:%M")
            if t_str not in trend_map: trend_map[t_str] = {"in": 0, "out": 0}
            trend_map[t_str]["in"] += (m.traffic_in or 0)
            trend_map[t_str]["out"] += (m.traffic_out or 0)
        
        start_dt = datetime.now().replace(second=0, microsecond=0) - timedelta(minutes=9)
        for i in range(10):
            curr = start_dt + timedelta(minutes=i)
            key = curr.strftime("%H:%M")
            val = trend_map.get(key, {"in": 0, "out": 0})
            traffic_trend.append({"time": key, "in": val["in"], "out": val["out"]})
    else:
        now = datetime.now()
        for i in range(10):
            t = now - timedelta(minutes=(9 - i))
            traffic_trend.append({"time": t.strftime("%H:%M"), "in": 0, "out": 0})

    # Issues
    issue_query = db.query(Issue).filter(Issue.status == 'active')
    if target_ids:
        issue_query = issue_query.filter(Issue.device_id.in_(target_ids))
    recent_issues = issue_query.order_by(Issue.created_at.desc()).limit(10).all()
    
    issues_data = []
    for issue in recent_issues:
        issues_data.append({
            "id": issue.id,
            "title": issue.title,
            "device": issue.device.name if issue.device else "System",
            "severity": issue.severity,
            "time": issue.created_at.isoformat()
        })

    final_data = {
        "counts": {
            "sites": total_sites,
            "devices": total_devices,
            "online": online_cnt,
            "offline": offline_cnt,
            "alert": alert_cnt,
            "policies": total_policies,
            "images": total_images,
            "wireless_aps": total_aps,
            "wireless_clients": total_clients,
            "compliant": compliant_cnt
        },
        "health_score": current_health_score,
        "issues": issues_data,
        "trafficTrend": traffic_trend
    }

    return JSONResponse(content=final_data)


# ----------------------------------------------------------------
# [NEW] 3. 알람(Issue) 센터 API (새로 추가된 부분)
# ----------------------------------------------------------------
@router.get("/issues/active")
def get_active_issues(
    category: str = Query(None, description="Filter by category: device, security, system, config, performance"),
    severity: str = Query(None, description="Filter by severity: critical, warning, info"),
    is_read: bool = Query(None, description="Filter by read status"),
    db: Session = Depends(get_db)
):
    """
    해결되지 않은(active) 이슈 목록을 반환합니다.
    Device 정보를 조인해서 장비 이름도 같이 보냅니다.
    """
    query = db.query(Issue).options(joinedload(Issue.device)) \
        .filter(Issue.status == 'active')
    
    # Apply filters
    if category:
        query = query.filter(Issue.category == category)
    if severity:
        query = query.filter(Issue.severity == severity)
    if is_read is not None:
        query = query.filter(Issue.is_read == is_read)
    
    issues = query.order_by(Issue.created_at.desc()).all()

    result = []
    for issue in issues:
        result.append({
            "id": issue.id,
            "title": issue.title,
            "device": issue.device.name if issue.device else "System",
            "device_id": issue.device_id,
            "message": issue.description,
            "severity": issue.severity,
            "category": issue.category or "system",
            "is_read": issue.is_read,
            "created_at": issue.created_at.isoformat(),
            "status": issue.status
        })

    return result


@router.get("/issues/unread-count")
def get_unread_count(db: Session = Depends(get_db)):
    """
    읽지 않은 active 이슈 개수를 반환합니다.
    """
    count = db.query(Issue).filter(
        Issue.status == 'active',
        Issue.is_read == False
    ).count()
    return {"unread_count": count}


@router.put("/issues/{issue_id}/read")
def mark_issue_as_read(issue_id: int, db: Session = Depends(get_db)):
    """
    특정 이슈를 읽음 처리합니다.
    """
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    
    issue.is_read = True
    db.commit()
    return {"message": "Issue marked as read"}


@router.put("/issues/read-all")
def mark_all_as_read(db: Session = Depends(get_db)):
    """
    모든 Active 이슈를 읽음 처리합니다.
    """
    db.query(Issue).filter(Issue.status == 'active', Issue.is_read == False).update(
        {"is_read": True},
        synchronize_session=False
    )
    db.commit()
    return {"message": "All issues marked as read"}


@router.put("/issues/{issue_id}/resolve")
def resolve_issue(issue_id: int, db: Session = Depends(get_db)):
    """
    특정 이슈를 'resolved' 상태로 변경하여 목록에서 제거합니다.
    """
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    issue.status = "resolved"
    issue.resolved_at = datetime.now()
    issue.is_read = True
    db.commit()

    return {"message": "Issue resolved successfully"}


@router.post("/issues/resolve-all")
def resolve_all_issues(db: Session = Depends(get_db)):
    """
    모든 Active 이슈를 한 번에 해결 처리합니다.
    """
    db.query(Issue).filter(Issue.status == 'active').update(
        {"status": "resolved", "resolved_at": datetime.now(), "is_read": True},
        synchronize_session=False
    )
    db.commit()
    return {"message": "All issues resolved"}
