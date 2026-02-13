import random
import re
from datetime import datetime, timedelta
from typing import List, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func, and_
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.session import get_db
from app.api import deps
from app.models.device import Device, Link, Site, Policy, FirmwareImage, Interface, ConfigBackup, SystemMetric, \
    EventLog, Issue, ConfigTemplate
from app.models.user import User # [FIX] Dedicated user model
from app.schemas.device import DeviceCreate, DeviceResponse, DeviceDetailResponse, DeviceUpdate
from app.models.device_inventory import DeviceInventoryItem
from app.services.template_service import TemplateRenderer
from app.db.session import SessionLocal
from app.services.audit_service import AuditService
from app.models.settings import SystemSetting

router = APIRouter()


# --------------------------------------------------------------------------
# [Dashboard] 대시보드 통계
# --------------------------------------------------------------------------
@router.get("/stats")
def read_dashboard_stats(
    site_id: int = Query(None),
    db: Session = Depends(get_db), 
    current_user: User = Depends(deps.require_viewer)
):
    """
    모든 장비 데이터를 가져와서 통계를 냅니다. site_id가 있으면 해당 사이트 장비만 보여줍니다.
    """
    # 1. Device Filtering
    device_query = db.query(Device.id, Device.status, Device.latest_parsed_data)
    if site_id:
        device_query = device_query.filter(Device.site_id == site_id)
    
    device_rows = device_query.all()
    total = len(device_rows)

    online_cnt = 0
    alert_cnt = 0
    total_aps = 0
    total_clients = 0

    # 2. Aggregate Stats (Status & Wireless)
    for _dev_id, dev_status, latest_parsed_data in device_rows:
        status_text = str(dev_status or "offline").lower().strip()

        # [Service = Device Reachability]
        if status_text in ['online', 'reachable', 'up']:
            online_cnt += 1
        elif status_text in ['alert', 'warning', 'degraded']:
            alert_cnt += 1

        # [Wireless Aggregate]
        if latest_parsed_data and isinstance(latest_parsed_data, dict):
            w_data = latest_parsed_data
            wireless_nested = w_data.get("wireless", {}) if isinstance(w_data.get("wireless"), dict) else {}
            
            # Clients
            c_count = w_data.get("total_clients") 
            if c_count is None:
                c_count = wireless_nested.get("total_clients", 0)
            total_clients += int(c_count or 0)
            
            # APs
            ap_list = wireless_nested.get("ap_list", [])
            if ap_list and isinstance(ap_list, list):
                total_aps += sum(1 for ap in ap_list if str(ap.get("status", "")).lower() in ('up', 'online', 'registered', 'reg'))
            elif "up_aps" in wireless_nested:
                total_aps += wireless_nested.get("up_aps", 0)
            elif "up_aps" in w_data:
                total_aps += w_data.get("up_aps", 0)

    offline_cnt = total - (online_cnt + alert_cnt)
    if offline_cnt < 0: offline_cnt = 0

    health_score = 0
    if total > 0:
        score = ((online_cnt - (alert_cnt * 0.5)) / total) * 100
        health_score = int(max(0, min(100, score)))

    # 3. Traffic Trend (Real Data)
    # 최근 10분간의 데이터 조회하여 분 단위 합산
    traffic_trend = []
    
    if total > 0:
        ten_mins_ago = datetime.now() - timedelta(minutes=10)
        dialect_name = db.bind.dialect.name if db.bind else ""
        if dialect_name == "sqlite":
            time_bucket = func.strftime("%H:%M", SystemMetric.timestamp)
        else:
            time_bucket = func.to_char(SystemMetric.timestamp, "HH24:MI")

        metric_query = db.query(
            time_bucket.label("t"),
            func.sum(SystemMetric.traffic_in).label("in_sum"),
            func.sum(SystemMetric.traffic_out).label("out_sum")
        ).filter(SystemMetric.timestamp >= ten_mins_ago)

        if site_id:
            metric_query = metric_query.join(Device, Device.id == SystemMetric.device_id).filter(Device.site_id == site_id)

        metrics = metric_query.group_by("t").order_by("t").all()

        trend_map = {}

        for m in metrics:
            t_str = m.t
            trend_map[t_str] = {
                "in": float(m.in_sum or 0),
                "out": float(m.out_sum or 0)
            }
        
        # 맵을 리스트로 변환
        # 데이터가 아예 없으면 빈 그래프가 나오므로, 현재 시간까지 빈 포인트 채워주기 (UX)
        start_dt = datetime.now().replace(second=0, microsecond=0) - timedelta(minutes=9)
        for i in range(10):
            curr = start_dt + timedelta(minutes=i)
            key = curr.strftime("%H:%M")
            val = trend_map.get(key, {"in": 0, "out": 0})
            traffic_trend.append({
                "time": key,
                "in": val["in"], # BPS
                "out": val["out"]
            })
    else:
        # 장비가 하나도 없어도 빈 그래프 표시
        now = datetime.now()
        for i in range(10):
            t = now - timedelta(minutes=(9 - i))
            traffic_trend.append({"time": t.strftime("%H:%M"), "in": 0, "out": 0})

    # Fetch recent issues (Filtered by site device)
    issue_query = db.query(Issue).filter(Issue.status == 'active')
    if site_id:
        issue_query = issue_query.join(Device, Device.id == Issue.device_id).filter(Device.site_id == site_id)
    
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

    # 카운트 쿼리도 필터 적용
    sites_count = db.query(Site).count() # Site 수는 전체 보여주는 게 맞음 (필터링해도)
    policy_query = db.query(Policy)
    if site_id: policy_query = policy_query.filter(Policy.site_id == site_id)
    
    final_data = {
        "counts": {
            "devices": total,
            "online": online_cnt,
            "offline": offline_cnt,
            "alert": alert_cnt,
            "sites": sites_count,
            "policies": policy_query.count(),
            "images": db.query(FirmwareImage).count(),
            "wireless_aps": total_aps,
            "wireless_clients": total_clients,
            "licenses": "Valid",
            "compliant": 0
        },
        "health_score": health_score,
        "trafficTrend": traffic_trend,
        "issues": issues_data
    }

    return JSONResponse(content=final_data)


@router.get("/wireless/overview")
def get_wireless_overview(db: Session = Depends(get_db), current_user: User = Depends(deps.require_viewer)):
    """
    전체 장비 중 무선 데이터를 포함한 장비(WLC)들의 통합 정보를 반환합니다.
    """
    wlc_devices = db.query(Device).filter(Device.latest_parsed_data.isnot(None)).all()
    
    all_aps = []
    all_wlans = []
    total_clients = 0
    
    for dev in wlc_devices:
        parsed = dev.latest_parsed_data
        wireless = parsed.get("wireless")
        if not wireless:
            continue
            
        total_clients += wireless.get("total_clients", 0)
        
        # WLANs 합치기 (중복 제거 필요할 수 있으나 여기서는 단순 나열)
        for wl in wireless.get("wlan_summary", []):
            all_wlans.append({
                **wl,
                "wlc_name": dev.name,
                "wlc_ip": dev.ip_address
            })
            
        # APs 합치기
        for ap in wireless.get("ap_list", []):
            all_aps.append({
                **ap,
                "wlc_name": dev.name,
                "wlc_ip": dev.ip_address
            })
            
    return {
        "summary": {
            "total_wlc": len(wlc_devices),
            "total_aps": len(all_aps),
            "total_wlans": len(all_wlans),
            "total_clients": total_clients
        },
        "wlans": all_wlans,
        "aps": all_aps
    }


# --------------------------------------------------------------------------
# [Helper] 유틸리티
# --------------------------------------------------------------------------
class VlanDeployRequest(BaseModel):
    device_ids: List[int]
    vlan_id: int
    vlan_name: str


def parse_uptime_seconds(uptime_value) -> str:
    """
    Parses uptime which can be numeric seconds or a Cisco-style string.
    Returns standardized format: Xd Xh Xm
    """
    if not uptime_value: 
        return "0d 0h 0m"
    
    # CASE 1: Already a formatted string if parsed by some TextFSM templates
    if isinstance(uptime_value, str) and ('day' in uptime_value or 'hour' in uptime_value):
        return uptime_value

    try:
        # CASE 2: Numeric value (seconds or centiseconds)
        val = float(uptime_value)
        # Handle SNMP-style centiseconds (common in some Cisco outputs)
        if val > 10000000: 
            val = val / 100
        
        td = timedelta(seconds=val)
        return f"{td.days}d {td.seconds // 3600}h {(td.seconds % 3600) // 60}m"
    except (ValueError, TypeError):
        # CASE 3: Unknown string format, return as is
        return str(uptime_value)


# --------------------------------------------------------------------------
# [Analytics] 분석 데이터
# --------------------------------------------------------------------------
@router.get("/analytics")
def get_analytics_data(time_range: str = Query("24h", alias="range"), db: Session = Depends(get_db), current_user: User = Depends(deps.require_viewer)):
    now = datetime.now()
    delta = timedelta(hours=1) if time_range == "1h" else timedelta(days=7) if time_range == "7d" else timedelta(
        hours=24)
    start_time = now - delta
    metrics = db.query(SystemMetric).filter(SystemMetric.timestamp >= start_time).order_by(
        SystemMetric.timestamp.asc()).all()

    resource_data = []
    if metrics:
        step = max(1, len(metrics) // 50)
        for i in range(0, len(metrics), step):
            m = metrics[i]
            fmt = "%H:%M" if time_range in ["1h", "24h"] else "%m/%d"
            resource_data.append({"time": m.timestamp.strftime(fmt), "cpu": m.cpu_usage, "memory": m.memory_usage})

    top_devices_query = db.query(Device).filter(Device.status == 'online').all()

    device_stats = []
    for dev in top_devices_query:
        last_metric = db.query(SystemMetric).filter(SystemMetric.device_id == dev.id).order_by(
            SystemMetric.timestamp.desc()).first()
        if last_metric:
            device_stats.append(
                {"name": dev.name, "usage": last_metric.cpu_usage, "location": dev.location or "Unknown"})

    return {"resourceTrend": resource_data,
            "topDevices": sorted(device_stats, key=lambda x: x['usage'], reverse=True)[:5], "trafficTrend": []}


# --------------------------------------------------------------------------
# [Topology] 토폴로지 데이터 (수정됨: site_id 포함)
# --------------------------------------------------------------------------
@router.get("/topology/links")
def get_topology_links(
    snapshot_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    if snapshot_id is not None:
        import json
        from fastapi import HTTPException
        from app.models.topology import TopologySnapshot

        snap = db.query(TopologySnapshot).filter(TopologySnapshot.id == snapshot_id).first()
        if not snap:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        try:
            nodes = json.loads(snap.nodes_json or "[]")
        except Exception:
            nodes = []
        try:
            links = json.loads(snap.links_json or "[]")
        except Exception:
            links = []
        return {"nodes": nodes, "links": links, "snapshot_id": int(snap.id)}
    from datetime import datetime, timedelta
    from app.models.endpoint import Endpoint, EndpointAttachment
    from app.services.snmp_service import SnmpManager
    from sqlalchemy.orm import load_only
    now = datetime.now()

    devices = (
        db.query(Device)
        .options(
            load_only(
                Device.id,
                Device.name,
                Device.hostname,
                Device.ip_address,
                Device.device_type,
                Device.model,
                Device.os_version,
                Device.status,
                Device.site_id,
                Device.latest_parsed_data,
            )
        )
        .all()
    )
    sites = db.query(Site.id, Site.name).all()
    site_map = {sid: name for sid, name in sites}
    meta_by_id = {d.id: (d.latest_parsed_data or {}) for d in devices}

    metric_by_device_id = {}
    if devices:
        ids = [d.id for d in devices]
        latest_ts = (
            db.query(SystemMetric.device_id.label("device_id"), func.max(SystemMetric.timestamp).label("max_ts"))
            .filter(SystemMetric.device_id.in_(ids))
            .group_by(SystemMetric.device_id)
            .subquery()
        )
        latest_rows = (
            db.query(SystemMetric)
            .join(latest_ts, and_(SystemMetric.device_id == latest_ts.c.device_id, SystemMetric.timestamp == latest_ts.c.max_ts))
            .all()
        )
        metric_by_device_id = {m.device_id: m for m in latest_rows if m and m.device_id is not None}
    
    nodes = []
    for d in devices:
        # [Hierarchy Logic]
        # Tier 0: Core/Router (Nexus, 9500, Router, Backbone)
        # Tier 1: Distribution/L3 Aggregation (9300, 3850, 4500, 6500, 9400, EX4, etc.)
        # Tier 2: Access/L2 (9200, 2960, C1000, etc.)
        # Tier 3: Endpoint (AP)

        dev_type = str(d.device_type or "").lower()
        model = str(d.model or "").lower()
        hostname = str(d.name or "").lower()
        
        tier = 2 # Default to Access
        role = "access"

        # 1. CORE / SPINE (Tier 0)
        # Check for specific high-end models or explicit "core"/"spine" in hostname/type
        if any(k in model for k in ["nexus", "9500", "9600", "n7k", "n9k", "asr", "isr", "mx", "ptx", "ne40", "ce128"]) or \
           any(k in dev_type for k in ["router", "core", "spine", "gateway"]) or \
           "core" in hostname or "spine" in hostname:
            tier = 0
            role = "core"

        # 2. DISTRIBUTION / L3 AGGREGATION (Tier 1)
        # Check for L3 switches or explicit "dist"/"agg" in hostname
        elif any(k in model for k in ["9300", "9400", "9410", "9500", "9600", "3850", "3650", "4500", "6500", "6800", "cat9k", "ex4", "ex3", "qfx", "s67", "7050", "7280", "c3850", "c3650", "c93", "c94", "c95", "c96", "c36", "c38"]) or \
             "dist" in hostname or "agg" in hostname or "l3" in hostname:
            tier = 1
            role = "distribution"

        # 3. SECURITY / FIREWALL (Tier 1)
        elif any(k in dev_type for k in ["firewall", "security", "utm", "fw"]) or \
             any(k in model for k in ["forti", "palo", "asa", "srx", "check", "firepower", "pa-", "fg-"]):
            tier = 1
            role = "security"

        # 4. WIRELESS CONTROLLER (Tier 1)
        elif any(k in dev_type for k in ["wlc", "controller", "wireless"]) or \
             any(k in model for k in ["9800", "5508", "2504", "5520", "8540", "ac6", "vwlc"]):
            tier = 1
            role = "wlc"

        # 5. ACCESS POINTS (Tier 3)
        elif any(k in dev_type for k in ["ap", "access point"]) or \
             any(k in model for k in ["air-", "cap", "iap", "mr", "nap", "wap"]):
            tier = 3
            role = "access_point"

        # 6. DOMESTIC / KOREA VENDORS (Tier 2) - Highlight
        elif any(k in dev_type for k in ["dasan", "ubiquoss", "handream", "piolink"]) or \
             any(k in model for k in ["v2", "v6", "v8", "e5", "h3", "h4"]): # Common domestic model prefixes if needed, but risky. Sticking to vendor check mainly.
            tier = 2
            role = "access_domestic"
            
        # 7. Explicit L2/Access Models (Fail-safe, though they would fall through anyway)
        elif any(k in model for k in ["2960", "9200", "1000", "c2960", "c9200", "c1000", "sf300", "sg300"]):
            tier = 2
            role = "access"

        # [Default] Access Layer (Tier 2)
        else:
            tier = 2
            role = "access"
        
        # [Check Metrics for Healthmap]
        latest_metric = metric_by_device_id.get(d.id)
        cpu = latest_metric.cpu_usage if latest_metric else 0
        mem = latest_metric.memory_usage if latest_metric else 0
        
        # [Unified Health Score Calculation]
        # Base: 100 - max(cpu, memory)
        # WLC Penalty: If AP down ratio > 10%, subtract additional points
        base_health = 100 - max(cpu or 0, mem or 0)
        
        # Wireless specific metrics
        wireless_data = {}
        ap_penalty = 0
        if d.latest_parsed_data and isinstance(d.latest_parsed_data, dict):
            w = d.latest_parsed_data.get("wireless", {})
            if w:
                total_aps = w.get("total_aps", 0) or 0
                down_aps = w.get("down_aps", 0) or 0
                clients = w.get("total_clients", 0) or 0
                wireless_data = {
                    "total_aps": total_aps,
                    "down_aps": down_aps,
                    "up_aps": total_aps - down_aps,
                    "clients": clients
                }
                # AP Down Penalty: If >10% APs are down, reduce health score
                if total_aps > 0:
                    down_ratio = (down_aps / total_aps) * 100
                    if down_ratio > 50:
                        ap_penalty = 30  # Critical
                    elif down_ratio > 20:
                        ap_penalty = 15  # Warning
                    elif down_ratio > 10:
                        ap_penalty = 5   # Minor
        
        health_score = max(0, min(100, base_health - ap_penalty))
        
        nodes.append({
            "id": str(d.id),
            "label": d.name,
            "ip": d.ip_address,
            "type": d.device_type,
            "hostname": d.hostname,
            "model": d.model,
            "os_version": d.os_version,
            "status": str(d.status or "offline").lower(),
            "site_id": d.site_id,
            "site_name": site_map.get(d.site_id, "Default Site"),
            "tier": tier,   # [NEW] For Dagre Ranking
            "role": role,   # [NEW] For Visual Grouping/Coloring
            "metrics": {
                "cpu": cpu,
                "memory": mem,
                "health_score": health_score,
                "traffic_in": latest_metric.traffic_in if latest_metric else 0,
                "traffic_out": latest_metric.traffic_out if latest_metric else 0,
                **wireless_data  # Spread wireless metrics if available
            }
        })

    links = (
        db.query(Link)
        .options(
            load_only(
                Link.source_device_id,
                Link.target_device_id,
                Link.source_interface_name,
                Link.target_interface_name,
                Link.status,
                Link.protocol,
            )
        )
        .filter(Link.target_device_id.isnot(None))
        .all()
    )
    edges = []
    for l in links:
        src_port_raw = str(l.source_interface_name or "")
        dst_port_raw = str(l.target_interface_name or "")
        src_port = SnmpManager.normalize_interface_name(src_port_raw)
        dst_port = SnmpManager.normalize_interface_name(dst_port_raw)

        src_meta = meta_by_id.get(l.source_device_id, {}) if l.source_device_id else {}
        dst_meta = meta_by_id.get(l.target_device_id, {}) if l.target_device_id else {}
        src_if_state = src_meta.get("if_traffic_state", {}) if isinstance(src_meta, dict) else {}
        dst_if_state = dst_meta.get("if_traffic_state", {}) if isinstance(dst_meta, dict) else {}

        src_entry = src_if_state.get(src_port, {}) if isinstance(src_if_state, dict) and src_port else {}
        dst_entry = dst_if_state.get(dst_port, {}) if isinstance(dst_if_state, dict) and dst_port else {}

        src_in_bps = float(src_entry.get("in_bps", 0.0) or 0.0) if isinstance(src_entry, dict) else 0.0
        src_out_bps = float(src_entry.get("out_bps", 0.0) or 0.0) if isinstance(src_entry, dict) else 0.0
        dst_in_bps = float(dst_entry.get("in_bps", 0.0) or 0.0) if isinstance(dst_entry, dict) else 0.0
        dst_out_bps = float(dst_entry.get("out_bps", 0.0) or 0.0) if isinstance(dst_entry, dict) else 0.0

        fwd_bps = max(0.0, min(src_out_bps, dst_in_bps))
        rev_bps = max(0.0, min(dst_out_bps, src_in_bps))

        edges.append({
            "source": str(l.source_device_id),
            "target": str(l.target_device_id),
            "src_port": src_port_raw,
            "dst_port": dst_port_raw,
            "label": f"{src_port_raw}<->{dst_port_raw}",
            "status": "active" if str(l.status) in ["up", "active"] else "down",
            "protocol": l.protocol or "LLDP",
            "traffic": {
                "src_in_bps": src_in_bps,
                "src_out_bps": src_out_bps,
                "dst_in_bps": dst_in_bps,
                "dst_out_bps": dst_out_bps,
                "fwd_bps": fwd_bps,
                "rev_bps": rev_bps,
                "ts": max(float(src_entry.get("ts", 0) or 0), float(dst_entry.get("ts", 0) or 0)) if isinstance(src_entry, dict) or isinstance(dst_entry, dict) else 0
            }
        })

    cutoff = now - timedelta(hours=24)
    endpoint_nodes = {}
    endpoint_edges = []

    def _is_private_mac(mac: str) -> bool:
        s = re.sub(r"[^0-9a-fA-F]", "", str(mac or ""))
        if len(s) < 2:
            return False
        try:
            first = int(s[0:2], 16)
        except Exception:
            return False
        return (first & 0x02) == 0x02
    atts = (
        db.query(
            EndpointAttachment.device_id,
            EndpointAttachment.interface_name,
            EndpointAttachment.last_seen,
            EndpointAttachment.vlan,
            Endpoint.id,
            Endpoint.mac_address,
            Endpoint.ip_address,
            Endpoint.hostname,
            Endpoint.vendor,
            Endpoint.endpoint_type,
            Endpoint.last_seen.label("ep_last_seen"),
        )
        .join(Endpoint, Endpoint.id == EndpointAttachment.endpoint_id)
        .filter(EndpointAttachment.last_seen >= cutoff)
        .all()
    )
    device_map = {d.id: d for d in devices}
    by_port = {}
    for (
        att_device_id,
        att_interface_name,
        att_last_seen,
        att_vlan,
        ep_id,
        ep_mac,
        ep_ip,
        ep_hostname,
        ep_vendor,
        ep_type,
        ep_last_seen,
    ) in atts:
        by_port.setdefault((att_device_id, att_interface_name), []).append(
            (att_device_id, att_interface_name, att_last_seen, att_vlan, ep_id, ep_mac, ep_ip, ep_hostname, ep_vendor, ep_type, ep_last_seen)
        )

    def _safe_port_id(port: str) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", "_", str(port or "")).strip("_")

    for (device_id, interface_name), rows in by_port.items():
        dev = device_map.get(device_id)
        if not dev:
            continue

        if len(rows) > 1:
            group_id = f"epg-{device_id}-{_safe_port_id(interface_name)}"
            private_count = 0
            types = set()
            vendors = set()
            for _row in rows:
                _ep_mac = _row[5]
                _ep_vendor = _row[8]
                _ep_type = _row[9]
                if _is_private_mac(_ep_mac):
                    private_count += 1
                if _ep_type:
                    types.add(_ep_type)
                if _ep_vendor:
                    vendors.add(_ep_vendor)

            label = f"{interface_name} ({len(rows)} endpoints)"
            if private_count:
                label = f"{label} · {private_count} private"

            endpoint_nodes[group_id] = {
                "id": group_id,
                "label": label,
                "ip": interface_name,
                "type": "endpoint_group",
                "status": "online",
                "site_id": dev.site_id,
                "site_name": site_map.get(dev.site_id, "Default Site"),
                "tier": 3,
                "role": "endpoint_group",
                "metrics": {"health_score": 100},
                "device_id": device_id,
                "count": len(rows),
                "private_count": private_count,
                "endpoint_types": sorted(list(types)),
                "vendors": sorted(list(vendors)),
                "port": interface_name,
            }

            endpoint_edges.append(
                {
                    "source": str(device_id),
                    "target": group_id,
                    "src_port": interface_name,
                    "dst_port": "endpoints",
                    "label": f"{interface_name}<->endpoints",
                    "status": "active",
                }
            )
            continue

        (
            att_device_id,
            att_interface_name,
            att_last_seen,
            att_vlan,
            ep_id,
            ep_mac,
            ep_ip,
            ep_hostname,
            ep_vendor,
            ep_type,
            ep_last_seen,
        ) = rows[0]
        dev = device_map.get(att_device_id)
        if not dev:
            continue
        ep_node_id = f"ep-{ep_id}"
        if ep_node_id not in endpoint_nodes:
            private_mac = _is_private_mac(ep_mac)
            label = ep_hostname or ep_ip or ep_mac
            if private_mac:
                label = f"{label} (Private MAC)"
            status = "online" if ep_last_seen and ep_last_seen >= now - timedelta(minutes=30) else "offline"
            endpoint_nodes[ep_node_id] = {
                "id": ep_node_id,
                "label": label,
                "ip": ep_ip or ep_mac,
                "type": "endpoint",
                "status": status,
                "site_id": dev.site_id,
                "site_name": site_map.get(dev.site_id, "Default Site"),
                "tier": 3,
                "role": "endpoint",
                "metrics": {"health_score": 100},
                "private_mac": private_mac,
                "endpoint_type": ep_type,
                "vendor": ep_vendor,
            }

        endpoint_edges.append(
            {
                "source": str(att_device_id),
                "target": ep_node_id,
                "src_port": att_interface_name,
                "dst_port": ep_mac,
                "label": f"{att_interface_name}<->{ep_mac}",
                "status": "active",
            }
        )

    nodes.extend(list(endpoint_nodes.values()))
    edges.extend(endpoint_edges)

    return {"nodes": nodes, "links": edges}


@router.get("/topology/endpoint-group")
def get_endpoint_group_details(
    device_id: int,
    port: str,
    hours: int = 24,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    from datetime import datetime, timedelta
    from app.models.endpoint import Endpoint, EndpointAttachment
    import re

    def _is_private_mac(mac: str) -> bool:
        s = re.sub(r"[^0-9a-fA-F]", "", str(mac or ""))
        if len(s) < 2:
            return False
        try:
            first = int(s[0:2], 16)
        except Exception:
            return False
        return (first & 0x02) == 0x02

    cutoff = datetime.now() - timedelta(hours=max(1, min(int(hours or 24), 168)))
    rows = (
        db.query(EndpointAttachment, Endpoint)
        .join(Endpoint, Endpoint.id == EndpointAttachment.endpoint_id)
        .filter(EndpointAttachment.device_id == device_id)
        .filter(EndpointAttachment.interface_name == port)
        .filter(EndpointAttachment.last_seen >= cutoff)
        .order_by(EndpointAttachment.last_seen.desc())
        .all()
    )

    items = []
    for att, ep in rows:
        items.append(
            {
                "endpoint_id": ep.id,
                "mac_address": ep.mac_address,
                "ip_address": ep.ip_address,
                "hostname": ep.hostname,
                "vendor": ep.vendor,
                "endpoint_type": ep.endpoint_type,
                "private_mac": _is_private_mac(ep.mac_address),
                "vlan": att.vlan,
                "last_seen": att.last_seen.isoformat() if getattr(att, "last_seen", None) else None,
            }
        )

    return {"device_id": device_id, "port": port, "count": len(items), "endpoints": items}


@router.get("/topology/trace")
def trace_path(source_id: int, target_id: int, db: Session = Depends(get_db), current_user: User = Depends(deps.require_viewer)):
    links = db.query(Link).all()
    graph = {}
    for l in links:
        if not l.source_device_id or not l.target_device_id: continue
        graph.setdefault(l.source_device_id, []).append(l.target_device_id)
        graph.setdefault(l.target_device_id, []).append(l.source_device_id)

    queue = [[source_id]];
    visited = {source_id};
    found_path = []
    while queue:
        path = queue.pop(0);
        node = path[-1]
        if node == target_id: found_path = path; break
        if node in graph:
            for neighbor in graph[node]:
                if neighbor not in visited: visited.add(neighbor); new_path = list(path); new_path.append(
                    neighbor); queue.append(new_path)

    if not found_path: return {"status": "failed", "message": "No path found", "path_nodes": [], "path_links": []}

    highlight_links = []
    for i in range(len(found_path) - 1):
        src = found_path[i];
        dst = found_path[i + 1]
        link_obj = db.query(Link).filter(((Link.source_device_id == src) & (Link.target_device_id == dst)) | (
                (Link.source_device_id == dst) & (Link.target_device_id == src))).first()
        if link_obj: highlight_links.append(
            {"source": str(src), "target": str(dst), "status": link_obj.status, "speed": link_obj.link_speed})

    return {"status": "success", "path_nodes": [str(n) for n in found_path], "path_links": highlight_links}


# --------------------------------------------------------------------------
# [Action] 장비 동기화 (Sync)
# --------------------------------------------------------------------------
@router.post("/{device_id}/sync")
def sync_device(
        device_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(deps.require_operator)
):
    from app.services.device_sync_service import DeviceSyncService
    result = DeviceSyncService.sync_device(db, device_id)
    if result.get("status") == "not_found":
        raise HTTPException(404, "Device not found")
    return result


# --------------------------------------------------------------------------
# [Action] VLAN 배포
# --------------------------------------------------------------------------
@router.post("/deploy/vlan")
def deploy_vlan_bulk(req: VlanDeployRequest, db: Session = Depends(get_db),
                     current_user: User = Depends(deps.require_network_admin)):
    from app.tasks.config import deploy_vlan_bulk_task

    try:
        r = deploy_vlan_bulk_task.apply_async(
            args=[req.device_ids, req.vlan_id, req.vlan_name],
            queue="ssh",
        )
        return {"job_id": r.id, "status": "queued"}
    except Exception:
        from app.services.ssh_service import DeviceConnection, DeviceInfo

        vlan_template = "vlan {{ vlan_id }}\n name {{ vlan_name }}\nexit"
        summary = []
        for d_id in req.device_ids:
            dev = db.query(Device).filter(Device.id == d_id).first()
            if not dev:
                summary.append({"id": d_id, "name": None, "status": "not_found"})
                continue
            conn = DeviceConnection(
                DeviceInfo(
                    host=dev.ip_address,
                    username=dev.ssh_username,
                    password=dev.ssh_password,
                    secret=dev.enable_password,
                    port=getattr(dev, "ssh_port", 22) or 22,
                    device_type=dev.device_type or "cisco_ios",
                )
            )
            if conn.connect():
                res = conn.deploy_config_template(vlan_template, req.dict())
                summary.append({"id": d_id, "name": dev.name, "status": "success" if res.get("success") else "failed"})
                conn.disconnect()
            else:
                summary.append({"id": d_id, "name": dev.name, "status": "failed"})
        return {"job_id": None, "status": "executed", "result": {"summary": summary}}


# --------------------------------------------------------------------------
# CRUD 엔드포인트
# --------------------------------------------------------------------------
@router.get("/", response_model=List[DeviceResponse])
def read_devices(skip: int = 0, limit: int = 100, db: Session = Depends(get_db),
                 current_user: User = Depends(deps.require_viewer)):
    devices = db.query(Device).offset(skip).limit(limit).all()
    out = []
    for d in devices:
        d.status = str(d.status or "offline").lower()
        payload = DeviceResponse.model_validate(d).model_dump()
        if payload.get("snmp_community"):
            payload["snmp_community"] = "********"
        out.append(payload)
    return out


@router.get("/{device_id}", response_model=DeviceDetailResponse)
def read_device_detail(device_id: int, db: Session = Depends(get_db),
                       current_user: User = Depends(deps.require_viewer)):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device: raise HTTPException(404, "Device not found")
    device.status = str(device.status or "offline").lower()
    payload = DeviceDetailResponse.model_validate(device).model_dump()
    if payload.get("snmp_community"):
        payload["snmp_community"] = "********"
    return payload


@router.get("/{device_id}/inventory")
def read_device_inventory(device_id: int, db: Session = Depends(get_db), current_user: User = Depends(deps.require_viewer)):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(404, "Device not found")
    items = (
        db.query(DeviceInventoryItem)
        .filter(DeviceInventoryItem.device_id == device_id)
        .order_by(DeviceInventoryItem.class_id.asc().nulls_last(), DeviceInventoryItem.ent_physical_index.asc())
        .all()
    )
    return [
        {
            "ent_physical_index": i.ent_physical_index,
            "parent_index": i.parent_index,
            "class_id": i.class_id,
            "class_name": i.class_name,
            "name": i.name,
            "description": i.description,
            "model_name": i.model_name,
            "serial_number": i.serial_number,
            "mfg_name": i.mfg_name,
            "hardware_rev": i.hardware_rev,
            "firmware_rev": i.firmware_rev,
            "software_rev": i.software_rev,
            "is_fru": i.is_fru,
            "last_seen": i.last_seen.isoformat() if i.last_seen else None,
        }
        for i in items
    ]


@router.get("/{device_id}/inventory/export")
def export_device_inventory(device_id: int, format: str = Query("xlsx"), db: Session = Depends(get_db), current_user: User = Depends(deps.require_viewer)):
    import io

    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(404, "Device not found")
    if format not in {"xlsx", "pdf"}:
        raise HTTPException(400, "Invalid format")

    items = (
        db.query(DeviceInventoryItem)
        .filter(DeviceInventoryItem.device_id == device_id)
        .order_by(DeviceInventoryItem.class_id.asc().nulls_last(), DeviceInventoryItem.ent_physical_index.asc())
        .all()
    )

    from app.services.report_export_service import build_inventory_xlsx, build_inventory_pdf

    if format == "pdf":
        data = build_inventory_pdf(device.name, items)
        media = "application/pdf"
        filename = f"inventory_{device.id}.pdf"
    else:
        data = build_inventory_xlsx(device.name, items)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"inventory_{device.id}.xlsx"

    return StreamingResponse(
        io.BytesIO(data),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/", response_model=DeviceResponse)
def create_device(
    device_in: DeviceCreate, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_network_admin)
):
    # [License Check] Enforce Device Limit
    from app.core.license import license_verifier
    
    # 1. Load active license (from file or DB - currently using file based for V1)
    # In a real app, you might pass the token via header or store it in DB.
    # For this V1 implementation, we check the global token file if exists.
    try:
        with open("license.key", "r") as f:
            token = f.read().strip()
            license_data = license_verifier.verify_license(token)
            
            if not license_data.is_valid:
                raise HTTPException(403, f"License Invalid: {license_data.status}")
                
            current_count = db.query(Device).count()
            if current_count >= license_data.max_devices:
                 raise HTTPException(403, f"License Limit Reached ({license_data.max_devices} devices max). Upgrade your plan.")
    except FileNotFoundError:
        # If no license file, Dev Mode or Restricted
        # For commercial release, you might default to 0 or 5 devices.
        if db.query(Device).count() >= 100:
             raise HTTPException(403, "No License Found. Free tier limit (100 devices) reached.")


    if db.query(Device).filter(Device.name == device_in.name).first(): raise HTTPException(400, "Exists")
    
    # Exclude non-model fields
    data = device_in.dict(exclude={'auto_provision_template_id'})
    def _get_setting_value(key: str) -> str:
        setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        return setting.value if setting and setting.value and setting.value != "********" else ""

    default_ssh_password = _get_setting_value("default_ssh_password")
    default_ssh_username = _get_setting_value("default_ssh_username")
    default_enable_password = _get_setting_value("default_enable_password")
    default_snmp_community = _get_setting_value("default_snmp_community")

    if data.get("ssh_username") in (None, "", "admin") and default_ssh_username:
        data["ssh_username"] = default_ssh_username
    if data.get("ssh_password") in (None, "") and default_ssh_password:
        data["ssh_password"] = default_ssh_password
    if data.get("enable_password") in (None, "") and default_enable_password:
        data["enable_password"] = default_enable_password
    if (not data.get("snmp_community") or data.get("snmp_community") == "public") and default_snmp_community:
        data["snmp_community"] = default_snmp_community

    new_device = Device(**data, status="unknown", owner_id=current_user.id)
    db.add(new_device);
    db.commit();
    db.refresh(new_device)
    
    # Auto Provision
    if device_in.auto_provision_template_id:
        background_tasks.add_task(run_auto_provision, new_device.id, device_in.auto_provision_template_id)

    from app.tasks.device_sync import ssh_sync_device
    try:
        ssh_sync_device.delay(new_device.id)
    except Exception:
        from app.services.device_sync_service import DeviceSyncService
        background_tasks.add_task(DeviceSyncService.sync_device_job, new_device.id)
    else:
        from app.services.device_sync_service import DeviceSyncService
        background_tasks.add_task(DeviceSyncService.sync_device_job, new_device.id)
    try:
        from app.tasks.monitoring import burst_monitor_devices, monitor_all_devices
        burst_monitor_devices.delay([new_device.id], 3, 5)
        monitor_all_devices.delay()
    except Exception:
        pass
    
    # [Audit]
    AuditService.log(db, current_user, "CREATE", "Device", new_device.name, details=f"Created device {new_device.name} ({new_device.ip_address})")
    
    payload = DeviceResponse.model_validate(new_device).model_dump()
    if payload.get("snmp_community"):
        payload["snmp_community"] = "********"
    return payload


@router.put("/{device_id}", response_model=DeviceResponse)
def update_device(device_id: int, device_in: DeviceUpdate, db: Session = Depends(get_db),
                  current_user: User = Depends(deps.require_network_admin)):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device: raise HTTPException(404, "Device not found")
    for k, v in device_in.dict(exclude_unset=True).items():
        if k in {"ssh_password", "enable_password", "snmp_v3_auth_key", "snmp_v3_priv_key"} and v == "********":
            continue
        setattr(device, k, v)
    db.add(device);
    db.commit();
    db.refresh(device)
    
    # [Audit]
    AuditService.log(db, current_user, "UPDATE", "Device", device.name, details=f"Updated properties for device {device.name}")
    
    payload = DeviceResponse.model_validate(device).model_dump()
    if payload.get("snmp_community"):
        payload["snmp_community"] = "********"
    return payload


@router.delete("/{device_id}")
def delete_device(device_id: int, db: Session = Depends(get_db), current_user: User = Depends(deps.require_network_admin)):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device: raise HTTPException(404, "Device not found")
    
    dev_name = device.name
    db.delete(device)
    db.commit()
    
    # [Audit]
    AuditService.log(db, current_user, "DELETE", "Device", dev_name, details=f"Deleted device {dev_name}")
    
    return {"message": "Deleted"}
