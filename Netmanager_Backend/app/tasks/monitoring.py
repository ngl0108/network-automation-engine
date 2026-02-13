try:
    from celery import shared_task
except ModuleNotFoundError:
    def shared_task(*args, **kwargs):
        def decorator(fn):
            return fn
        if args and callable(args[0]) and not kwargs:
            return args[0]
        return decorator
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
# [수정] Issue 모델 임포트 추가
from app.models.device import Device, SystemMetric, InterfaceMetric, Issue
from app.models.settings import SystemSetting
from app.models.automation import AutomationRule # [NEW]
from app.services.snmp_service import SnmpManager
import datetime
import subprocess
import platform
from datetime import timedelta
import logging
import os
import redis

logger = logging.getLogger(__name__)


def parse_uptime(uptime_value) -> str:
    """SNMP TimeTicks 변환 함수"""
    try:
        if not uptime_value: return "0d 0h 0m"
        val = float(uptime_value)
        if val > 10000000:
            seconds = val / 100
        else:
            seconds = val
        td = timedelta(seconds=seconds)
        return f"{td.days}d {td.seconds // 3600}h {(td.seconds % 3600) // 60}m"
    except:
        return str(uptime_value)


def ping_device(ip_address):
    """Ping 생존 확인 함수"""
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    timeout_param = '-w' if platform.system().lower() == 'windows' else '-W'
    timeout_val = '1000' if platform.system().lower() == 'windows' else '1'

    command = ['ping', param, '1', timeout_param, timeout_val, ip_address]
    try:
        return subprocess.call(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    except Exception:
        return False


def create_issue_if_not_exists(db: Session, device_id: int, title: str, desc: str, severity: str, device_name: str = None):
    """
    [핵심] 중복되지 않는 경우에만 이슈 생성
    사용자가 이슈를 삭제하기 전까지는 DB에 남아있어야 함.
    [NEW] Critical 이슈 생성 시 이메일 알림 발송
    """
    existing_issue = db.query(Issue).filter(
        Issue.device_id == device_id,
        Issue.title == title
    ).first()

    if not existing_issue:
        new_issue = Issue(
            device_id=device_id,
            title=title,
            description=desc,
            severity=severity,
            status="active"
        )
        db.add(new_issue)
        try:
            from app.services.realtime_event_bus import realtime_event_bus

            realtime_event_bus.publish(
                "issue_update",
                {
                    "device_id": int(device_id),
                    "title": str(title),
                    "severity": str(severity),
                    "status": "active",
                    "description": str(desc),
                    "ts": datetime.datetime.now().isoformat(),
                    "source": "monitoring",
                },
            )
        except Exception:
            pass
        
        # [NEW] Critical 이슈는 이메일 알림 발송
        if severity == "critical":
            try:
                from app.services.email_service import EmailService
                device_label = device_name or f"Device ID {device_id}"
                EmailService.send_email(
                    db,
                    to_email=None,  # None이면 기본 관리자 이메일 사용
                    subject=f"[CRITICAL] {title} - {device_label}",
                    content=f"장비: {device_label}\n이슈: {title}\n상세: {desc}\n\n즉시 확인이 필요합니다."
                )
            except Exception as e:
                logger.exception("Alert email failed", extra={"device_id": device_id, "device_name": device_name})
        
        return True  # 생성됨
    return False  # 이미 있음


def _acquire_monitor_lock():
    db = SessionLocal()
    try:
        now = datetime.datetime.utcnow()
        lock_until = now + datetime.timedelta(seconds=120)
        setting = db.query(SystemSetting).filter(SystemSetting.key == "monitor_all_devices_lock").first()
        if setting and setting.value:
            try:
                current = datetime.datetime.fromisoformat(setting.value)
                if current > now:
                    return False
            except Exception:
                pass
        if not setting:
            setting = SystemSetting(
                key="monitor_all_devices_lock",
                value=lock_until.isoformat(),
                description="monitor_all_devices_lock",
                category="system"
            )
        else:
            setting.value = lock_until.isoformat()
        db.add(setting)
        db.commit()
        return True
    finally:
        db.close()


def _evaluate_automation_rules(db: Session, device: Device, result: dict):
    """
    [Auto-Trigger] Check automation rules against collected metrics.
    If condition met and cooldown passed -> Trigger Action (Log/Issue/Task).
    """
    try:
        # 1. Fetch enabled rules
        rules = db.query(AutomationRule).filter(AutomationRule.enabled == True).all()
        if not rules:
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        
        # Resources
        res_data = result.get('resource_data') or {}
        cpu = res_data.get('cpu_usage', 0)
        mem = res_data.get('memory_usage', 0)
        
        # Interface Counters (Normalized)
        if_counters = result.get('if_counters') or {}
        
        for rule in rules:
            # Scope Check
            if rule.target_device_ids:
                if device.id not in rule.target_device_ids:
                    continue
            
            # Cooldown Check
            if rule.last_triggered_at:
                # Naive check (assuming UTC or compatible timezone)
                elapsed = (now - rule.last_triggered_at).total_seconds()
                if elapsed < rule.cooldown_seconds:
                    continue

            triggered = False
            trigger_val = float(rule.trigger_value) if rule.trigger_value.replace('.','',1).isdigit() else rule.trigger_value
            
            # Condition Logic
            current_val = None
            
            if rule.trigger_type == 'cpu':
                current_val = cpu
            elif rule.trigger_type == 'memory':
                current_val = mem
            elif rule.trigger_type.startswith('interface_'):
                # e.g. interface_traffic_in
                if_name = rule.trigger_target
                if if_name and if_name in if_counters:
                    stats = if_counters[if_name]
                    if rule.trigger_type == 'interface_traffic_in':
                        current_val = stats.get('in_bps', 0)
                    elif rule.trigger_type == 'interface_traffic_out':
                        current_val = stats.get('out_bps', 0)
                    elif rule.trigger_type == 'interface_errors':
                        current_val = stats.get('in_errors_per_sec', 0) + stats.get('out_errors_per_sec', 0)
            
            # Compare
            if current_val is not None:
                op = rule.trigger_condition
                try:
                    val_num = float(current_val)
                    trig_num = float(trigger_val)
                    if op == '>=': triggered = val_num >= trig_num
                    elif op == '>': triggered = val_num > trig_num
                    elif op == '<=': triggered = val_num <= trig_num
                    elif op == '<': triggered = val_num < trig_num
                    elif op == '==': triggered = val_num == trig_num
                except:
                    pass

            if triggered:
                # Action Trigger!
                logger.info(f"[Auto-Trigger] Rule '{rule.name}' triggered on device {device.name} ({device.ip_address})")
                
                # 1. Log to Issue (Visibility)
                create_issue_if_not_exists(
                    db, 
                    device.id, 
                    f"Auto-Trigger: {rule.name}", 
                    f"Condition met: {rule.trigger_type} {rule.trigger_condition} {rule.trigger_value}. Action: {rule.action_type}", 
                    "warning", 
                    device.name
                )
                
                # 2. Update Cooldown
                rule.last_triggered_at = now
                db.add(rule)
                
                # 3. Execute Action (Placeholder for now)
                # In real implementation, this would call a Celery task or Workflow engine
                # e.g. execute_workflow.delay(rule.action_id, device.id)
                
    except Exception as e:
        logger.error(f"Error evaluating automation rules: {e}")


@shared_task
def monitor_all_devices():
    """
    [통합 모니터링] 30초 주기 태스크 (Parallel Optimized)
    1. Ping First: 모든 장비에 대해 병렬로 Ping 수행 (Online 여부 결정)
    2. SNMP Metrics: Online인 장비에 대해서만 SNMP로 CPU, Mem, Traffic 수집
    3. ThreadPoolExecutor: Windows 호환성 및 성능을 위해 멀티스레딩 사용 (Max 30 workers)
    """
    import subprocess
    import platform
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from app.models.device import Device, SystemMetric, Issue, Link
    from app.services.snmp_service import SnmpManager
    
    if not _acquire_monitor_lock():
        return

    db = SessionLocal()
    try:
        # 전체 장비 로드
        devices = db.query(Device).all()
        links = db.query(Link).filter(Link.target_device_id != None).all()
        ports_by_device = {}
        for l in links:
            if l.source_device_id and l.source_interface_name:
                ports_by_device.setdefault(l.source_device_id, set()).add(str(l.source_interface_name))
            if l.target_device_id and l.target_interface_name:
                ports_by_device.setdefault(l.target_device_id, set()).add(str(l.target_interface_name))
        
        gnmi_ts_map = {}
        try:
            r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
            device_ids = [d.id for d in devices]
            if device_ids:
                keys = [f"device:{did}:last_metric_ts" for did in device_ids]
                values = r.mget(keys)
                for did, val in zip(device_ids, values):
                    if val:
                        gnmi_ts_map[did] = float(val)
        except Exception as e:
            logger.warning(f"Redis connection failed for gNMI check: {e}")

        target_list = [
            {
                "id": d.id, 
                "ip": d.ip_address, 
                "comm": d.snmp_community,
                "snmp_version": getattr(d, "snmp_version", None) or "v2c",
                "snmp_port": int(getattr(d, "snmp_port", None) or 161),
                "snmp_v3_username": getattr(d, "snmp_v3_username", None),
                "snmp_v3_security_level": getattr(d, "snmp_v3_security_level", None),
                "snmp_v3_auth_proto": getattr(d, "snmp_v3_auth_proto", None),
                "snmp_v3_auth_key": getattr(d, "snmp_v3_auth_key", None),
                "snmp_v3_priv_proto": getattr(d, "snmp_v3_priv_proto", None),
                "snmp_v3_priv_key": getattr(d, "snmp_v3_priv_key", None),
                "type": d.device_type, 
                "model": d.model,
                # Traffic 계산을 위해 이전 데이터 필요
                "prev_data": d.latest_parsed_data,
                "link_ports": list(ports_by_device.get(d.id, set())),
                # [gNMI] Creds
                "user": d.ssh_username, "pw": d.ssh_password,
                "gnmi_port": d.gnmi_port, "telemetry_mode": d.telemetry_mode,
                "last_gnmi_ts": gnmi_ts_map.get(d.id)
            } 
            for d in devices
        ]
    finally:
        db.close()

    def check_device_full(target):
        """단일 장비 전체 점검 (Worker Thread)"""
        ip = target['ip']
        comm = target['comm'] or 'public'
        snmp_version = str(target.get("snmp_version") or "v2c")
        snmp_port = int(target.get("snmp_port") or 161)
        
        # 1. Ping Check (OS Command)
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        timeout_param = '-w' if platform.system().lower() == 'windows' else '-W'
        timeout_val = '500' if platform.system().lower() == 'windows' else '1' # 500ms
        
        is_alive = False
        try:
            cmd = ['ping', param, '1', timeout_param, timeout_val, ip]
            
            # Windows Console Suppression
            startupinfo = None
            if platform.system().lower() == 'windows':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            ret = subprocess.run(
                cmd, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo,
                timeout=1.5 # 프로세스 타임아웃
            )
            is_alive = (ret.returncode == 0)
        except Exception:
            is_alive = False
        
        result = {
            "id": target['id'],
            "alive": is_alive,
            "snmp_data": {},
            "resource_data": None,
            "snmp_error": None,
            "wlc_clients": None,
            "if_counters": None
        }

        # 2. Hybrid Metrics (SNMP Fallback Decision) (Only if Alive)
        metrics_collected = False
        if is_alive:
            telemetry_mode = target.get('telemetry_mode', 'hybrid')
            
            if telemetry_mode in ['gnmi', 'hybrid']:
                last_ts = target.get('last_gnmi_ts')
                if last_ts and (datetime.datetime.now().timestamp() - last_ts) < 60:
                    metrics_collected = True
                    result['snmp_data'] = {'status': 'online', 'uptime': 'N/A (gNMI Active)'}
                else:
                    if telemetry_mode == 'gnmi':
                        metrics_collected = True 
                        result['gnmi_error'] = "No gNMI data received in last 60s"

            # B. SNMP Fallback (If not collected yet)
            if not metrics_collected:
                try:
                    snmp = SnmpManager(
                        ip,
                        comm,
                        port=snmp_port,
                        version=snmp_version,
                        v3_username=target.get("snmp_v3_username"),
                        v3_security_level=target.get("snmp_v3_security_level"),
                        v3_auth_proto=target.get("snmp_v3_auth_proto"),
                        v3_auth_key=target.get("snmp_v3_auth_key"),
                        v3_priv_proto=target.get("snmp_v3_priv_proto"),
                        v3_priv_key=target.get("snmp_v3_priv_key"),
                    )
                    check = snmp.check_status()
                    if check['status'] == 'online':
                        result['snmp_data'] = check
                        result['resource_data'] = snmp.get_resource_usage()
                        link_ports = target.get('link_ports') or []
                        try:
                            if isinstance(link_ports, list) and len(link_ports) > 0:
                                result['if_counters'] = snmp.get_interface_counters_for_ports(link_ports)
                            else:
                                raw = snmp.get_interface_counters_map()
                                norm = {}
                                if isinstance(raw, dict):
                                    for k, v in raw.items():
                                        pn = snmp.normalize_interface_name(k)
                                        if pn and isinstance(v, dict):
                                            norm[pn] = v
                                result['if_counters'] = norm
                        except Exception:
                            result['if_counters'] = None
                        
                        # WLC Clients
                        dev_type = str(target['type']).lower()
                        model = str(target['model']).lower()
                        if "wlc" in dev_type or "9800" in model or "cisco_wlc" in dev_type:
                            result['wlc_clients'] = snmp.get_wlc_client_count()
                except Exception as e:
                    result['snmp_error'] = str(e)

        return result

    # 병렬 실행
    scan_results = []
    max_workers = 30 # 동시 실행 30개 제한 (윈도우 안정성)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(check_device_full, t): t for t in target_list}
        for future in as_completed(future_map):
            try:
                scan_results.append(future.result())
            except Exception as e:
                logger.exception("Monitor task error")

    # DB Bulk Update Loop
    save_db = SessionLocal()
    try:
        if not scan_results:
            return
        target_ids = [res["id"] for res in scan_results]
        devices_by_id = {
            d.id: d for d in save_db.query(Device).filter(Device.id.in_(target_ids)).all()
        }
        updates_made = False
        metrics_to_add = []
        if_metrics_to_add = []
        for res in scan_results:
            device = devices_by_id.get(res['id'])
            if not device: continue

            # Status Update
            new_status = 'online' if res['alive'] else 'offline'
            if device.status != new_status:
                device.status = new_status
                updates_made = True
            
            device.reachability_status = 'reachable' if res['alive'] else 'unreachable'
            if res['alive']:
                device.last_seen = datetime.datetime.now()
            
            # Issue Generation (Ping Failed)
            if not res['alive']:
                # 기존 로직: Device Unreachable 이슈 생성
                create_issue_if_not_exists(save_db, device.id, "Device Unreachable", "Ping check failed.", "critical", device.name)

            # SNMP Metrics Parsing
            if res['alive'] and res['snmp_data'].get('status') == 'online':
                # Uptime
                if 'uptime' in res['snmp_data']:
                    device.uptime = parse_uptime(res['snmp_data']['uptime'])
                
                # Resources & Traffic
                r_data = res['resource_data']
                if r_data:
                    cpu = r_data.get('cpu_usage', 0)
                    mem = r_data.get('memory_usage', 0)
                    
                    # Traffic Calculation logic (Keep existing logic)
                    traffic_in_bps = 0.0
                    traffic_out_bps = 0.0
                    
                    current_in = r_data.get('raw_octets_in', 0)
                    current_out = r_data.get('raw_octets_out', 0)
                    now_ts = datetime.datetime.now().timestamp()
                    
                    # 이전 데이터 참조
                    prev_meta = device.latest_parsed_data if device.latest_parsed_data else {}
                    t_state = prev_meta.get("traffic_state", {})
                    prev_in = t_state.get("in", 0)
                    prev_out = t_state.get("out", 0)
                    prev_ts = t_state.get("ts", 0)
                    
                    # BPS 계산 (시간차 1초 이상일 때만)
                    if prev_ts > 0 and (now_ts - prev_ts) >= 1:
                        dt = now_ts - prev_ts
                        din = current_in - prev_in
                        dout = current_out - prev_out
                        if din >= 0 and dout >= 0:
                            traffic_in_bps = (din * 8) / dt
                            traffic_out_bps = (dout * 8) / dt
                    
                    # Metadata Update
                    if not device.latest_parsed_data: device.latest_parsed_data = {}
                    new_meta = dict(device.latest_parsed_data)
                    new_meta["traffic_state"] = {"in": current_in, "out": current_out, "ts": now_ts}

                    if_counters = res.get('if_counters') or {}
                    if isinstance(if_counters, dict) and if_counters:
                        prev_if_state = prev_meta.get("if_traffic_state", {}) if isinstance(prev_meta, dict) else {}
                        if not isinstance(prev_if_state, dict):
                            prev_if_state = {}
                        next_if_state = dict(prev_if_state)
                        for port_norm, v in if_counters.items():
                            try:
                                port_in = int(v.get("in_octets", v.get("in", 0)) or 0)
                            except Exception:
                                port_in = 0
                            try:
                                port_out = int(v.get("out_octets", v.get("out", 0)) or 0)
                            except Exception:
                                port_out = 0
                            try:
                                port_in_err = int(v.get("in_errors", 0) or 0)
                            except Exception:
                                port_in_err = 0
                            try:
                                port_out_err = int(v.get("out_errors", 0) or 0)
                            except Exception:
                                port_out_err = 0
                            try:
                                port_in_dis = int(v.get("in_discards", 0) or 0)
                            except Exception:
                                port_in_dis = 0
                            try:
                                port_out_dis = int(v.get("out_discards", 0) or 0)
                            except Exception:
                                port_out_dis = 0

                            prev_entry = next_if_state.get(port_norm, {}) if isinstance(next_if_state.get(port_norm), dict) else {}
                            prev_port_in = prev_entry.get("in_octets", prev_entry.get("in", 0)) or 0
                            prev_port_out = prev_entry.get("out_octets", prev_entry.get("out", 0)) or 0
                            prev_port_in_err = prev_entry.get("in_errors", 0) or 0
                            prev_port_out_err = prev_entry.get("out_errors", 0) or 0
                            prev_port_in_dis = prev_entry.get("in_discards", 0) or 0
                            prev_port_out_dis = prev_entry.get("out_discards", 0) or 0
                            prev_port_ts = prev_entry.get("ts", 0) or 0

                            port_in_bps = 0.0
                            port_out_bps = 0.0
                            in_err_per_sec = 0.0
                            out_err_per_sec = 0.0
                            in_dis_per_sec = 0.0
                            out_dis_per_sec = 0.0
                            if prev_port_ts and (now_ts - float(prev_port_ts)) >= 1:
                                dt = now_ts - float(prev_port_ts)
                                din = port_in - int(prev_port_in)
                                dout = port_out - int(prev_port_out)
                                if din >= 0 and dout >= 0:
                                    port_in_bps = (din * 8) / dt
                                    port_out_bps = (dout * 8) / dt
                                derr_in = port_in_err - int(prev_port_in_err)
                                derr_out = port_out_err - int(prev_port_out_err)
                                ddis_in = port_in_dis - int(prev_port_in_dis)
                                ddis_out = port_out_dis - int(prev_port_out_dis)
                                if derr_in >= 0:
                                    in_err_per_sec = derr_in / dt
                                if derr_out >= 0:
                                    out_err_per_sec = derr_out / dt
                                if ddis_in >= 0:
                                    in_dis_per_sec = ddis_in / dt
                                if ddis_out >= 0:
                                    out_dis_per_sec = ddis_out / dt

                            next_if_state[port_norm] = {
                                "in_octets": port_in,
                                "out_octets": port_out,
                                "in_errors": port_in_err,
                                "out_errors": port_out_err,
                                "in_discards": port_in_dis,
                                "out_discards": port_out_dis,
                                "ts": now_ts,
                                "in_bps": float(port_in_bps),
                                "out_bps": float(port_out_bps),
                                "in_errors_per_sec": float(in_err_per_sec),
                                "out_errors_per_sec": float(out_err_per_sec),
                                "in_discards_per_sec": float(in_dis_per_sec),
                                "out_discards_per_sec": float(out_dis_per_sec),
                            }
                            if_metrics_to_add.append(InterfaceMetric(
                                device_id=device.id,
                                interface_name=str(port_norm),
                                traffic_in_bps=float(port_in_bps),
                                traffic_out_bps=float(port_out_bps),
                                in_errors_per_sec=float(in_err_per_sec),
                                out_errors_per_sec=float(out_err_per_sec),
                                in_discards_per_sec=float(in_dis_per_sec),
                                out_discards_per_sec=float(out_dis_per_sec),
                            ))
                            total_err = float(in_err_per_sec) + float(out_err_per_sec)
                            total_drop = float(in_dis_per_sec) + float(out_dis_per_sec)
                            if total_err >= 5.0:
                                create_issue_if_not_exists(
                                    save_db,
                                    device.id,
                                    f"Interface Errors ({port_norm})",
                                    f"errors/s={total_err:.2f}",
                                    "warning",
                                    device.name,
                                )
                            if total_drop >= 5.0:
                                create_issue_if_not_exists(
                                    save_db,
                                    device.id,
                                    f"Interface Drops ({port_norm})",
                                    f"drops/s={total_drop:.2f}",
                                    "warning",
                                    device.name,
                                )
                        new_meta["if_traffic_state"] = next_if_state
                    
                    # WLC Clients Update
                    if res['wlc_clients'] is not None:
                         if "wireless" in new_meta and isinstance(new_meta["wireless"], dict):
                            w_copy = dict(new_meta["wireless"])
                            w_copy["total_clients"] = res['wlc_clients']
                            new_meta["wireless"] = w_copy
                         else:
                            new_meta["total_clients"] = res['wlc_clients']
                    
                    device.latest_parsed_data = new_meta
                    
                    # Metric History Add
                    metrics_to_add.append(SystemMetric(
                        device_id=device.id,
                        cpu_usage=cpu,
                        memory_usage=mem,
                        traffic_in=traffic_in_bps,
                        traffic_out=traffic_out_bps
                    ))
                    
                    # CPU Issue
                    if cpu >= 80:
                        create_issue_if_not_exists(save_db, device.id, "High CPU", f"CPU: {cpu}%", "warning", device.name)
                    if mem >= 85:
                        create_issue_if_not_exists(save_db, device.id, "High Memory", f"Memory: {mem}%", "warning", device.name)
                        
            updates_made = True

        if metrics_to_add:
            save_db.add_all(metrics_to_add)
            updates_made = True
        if if_metrics_to_add:
            save_db.add_all(if_metrics_to_add)
            updates_made = True
        if updates_made:
            save_db.commit()

    except Exception as e:
        logger.exception("Monitor all devices failed")
        save_db.rollback()
    finally:
        save_db.close()


def _acquire_gnmi_lock():
    db = SessionLocal()
    try:
        now = datetime.datetime.utcnow()
        lock_until = now + datetime.timedelta(seconds=30)
        setting = db.query(SystemSetting).filter(SystemSetting.key == "gnmi_collect_lock").first()
        if setting and setting.value:
            try:
                current = datetime.datetime.fromisoformat(setting.value)
                if current > now:
                    return False
            except Exception:
                pass
        if not setting:
            setting = SystemSetting(
                key="gnmi_collect_lock",
                value=lock_until.isoformat(),
                description="gnmi_collect_lock",
                category="system"
            )
        else:
            setting.value = lock_until.isoformat()
        db.add(setting)
        db.commit()
        return True
    finally:
        db.close()


@shared_task
def collect_gnmi_metrics():
    if not _acquire_gnmi_lock():
        return
    db = SessionLocal()
    try:
        devices = db.query(Device).filter(Device.ip_address != None).all()
        targets = [
            {
                "id": d.id,
                "ip": d.ip_address,
                "type": d.device_type,
                "telemetry_mode": d.telemetry_mode,
                "user": d.ssh_username,
                "pw": d.ssh_password,
                "gnmi_port": d.gnmi_port,
            }
            for d in devices
            if str(d.telemetry_mode or "").lower() in ("gnmi", "hybrid")
        ]
    finally:
        db.close()

    if not targets:
        return

    from concurrent.futures import ThreadPoolExecutor, as_completed
    from app.drivers.manager import DriverManager

    def _poll(t):
        ip = t["ip"]
        if not ip:
            return {"id": t["id"], "ok": False}
        try:
            driver = DriverManager.get_driver(
                str(t.get("type") or "cisco_ios"),
                ip,
                t.get("user"),
                t.get("pw"),
                22,
                t.get("pw"),
            )
            data = driver.get_gnmi_telemetry(port=t.get("gnmi_port", 57400))
            return {"id": t["id"], "ok": True, "data": data}
        except Exception as e:
            return {"id": t["id"], "ok": False, "error": str(e)}

    results = []
    with ThreadPoolExecutor(max_workers=min(30, len(targets) or 1)) as ex:
        futs = [ex.submit(_poll, t) for t in targets]
        for fut in as_completed(futs):
            try:
                results.append(fut.result())
            except Exception:
                continue

    save_db = SessionLocal()
    try:
        if not results:
            return
        metrics_to_add = []
        if_metrics_to_add = []
        metric_events = []
        try:
            from app.services.realtime_event_bus import realtime_event_bus
        except Exception:
            realtime_event_bus = None
        now = datetime.datetime.now()
        now_ts = now.timestamp()
        for res in results:
            if not res.get("ok"):
                continue
            device = save_db.query(Device).filter(Device.id == int(res["id"])).first()
            if not device:
                continue
            device.status = "online"
            device.reachability_status = "reachable"
            device.last_seen = now

            r_data = res.get("data") or {}
            cpu = r_data.get("cpu_usage", 0)
            mem = r_data.get("memory_usage", 0)
            try:
                cpu = float(cpu) if cpu is not None else 0
            except Exception:
                cpu = 0
            try:
                mem = float(mem) if mem is not None else 0
            except Exception:
                mem = 0

            traffic_in_bps = 0.0
            traffic_out_bps = 0.0
            current_in = r_data.get('raw_octets_in', 0)
            current_out = r_data.get('raw_octets_out', 0)
            prev_meta = device.latest_parsed_data if device.latest_parsed_data else {}
            t_state = prev_meta.get("traffic_state", {})
            prev_in = t_state.get("in", 0)
            prev_out = t_state.get("out", 0)
            prev_ts = t_state.get("ts", 0)
            if prev_ts > 0 and (now_ts - prev_ts) >= 1:
                dt = now_ts - prev_ts
                din = current_in - prev_in
                dout = current_out - prev_out
                if din >= 0 and dout >= 0:
                    traffic_in_bps = (din * 8) / dt
                    traffic_out_bps = (dout * 8) / dt

            if not device.latest_parsed_data:
                device.latest_parsed_data = {}
            new_meta = dict(device.latest_parsed_data)
            new_meta["traffic_state"] = {"in": current_in, "out": current_out, "ts": now_ts}

            if_counters = r_data.get("if_counters") or {}
            if isinstance(if_counters, dict) and if_counters:
                prev_if_state = prev_meta.get("if_traffic_state", {}) if isinstance(prev_meta, dict) else {}
                if not isinstance(prev_if_state, dict):
                    prev_if_state = {}
                next_if_state = dict(prev_if_state)
                for port_norm, v in if_counters.items():
                    try:
                        port_in = int(v.get("in_octets", v.get("in", 0)) or 0)
                    except Exception:
                        port_in = 0
                    try:
                        port_out = int(v.get("out_octets", v.get("out", 0)) or 0)
                    except Exception:
                        port_out = 0
                    try:
                        port_in_err = int(v.get("in_errors", 0) or 0)
                    except Exception:
                        port_in_err = 0
                    try:
                        port_out_err = int(v.get("out_errors", 0) or 0)
                    except Exception:
                        port_out_err = 0
                    try:
                        port_in_dis = int(v.get("in_discards", 0) or 0)
                    except Exception:
                        port_in_dis = 0
                    try:
                        port_out_dis = int(v.get("out_discards", 0) or 0)
                    except Exception:
                        port_out_dis = 0

                    prev_entry = next_if_state.get(port_norm, {}) if isinstance(next_if_state.get(port_norm), dict) else {}
                    prev_port_in = prev_entry.get("in_octets", prev_entry.get("in", 0)) or 0
                    prev_port_out = prev_entry.get("out_octets", prev_entry.get("out", 0)) or 0
                    prev_port_in_err = prev_entry.get("in_errors", 0) or 0
                    prev_port_out_err = prev_entry.get("out_errors", 0) or 0
                    prev_port_in_dis = prev_entry.get("in_discards", 0) or 0
                    prev_port_out_dis = prev_entry.get("out_discards", 0) or 0
                    prev_port_ts = prev_entry.get("ts", 0) or 0

                    port_in_bps = 0.0
                    port_out_bps = 0.0
                    in_err_per_sec = 0.0
                    out_err_per_sec = 0.0
                    in_dis_per_sec = 0.0
                    out_dis_per_sec = 0.0
                    if prev_port_ts and (now_ts - float(prev_port_ts)) >= 1:
                        dt = now_ts - float(prev_port_ts)
                        din = port_in - int(prev_port_in)
                        dout = port_out - int(prev_port_out)
                        if din >= 0 and dout >= 0:
                            port_in_bps = (din * 8) / dt
                            port_out_bps = (dout * 8) / dt
                        derr_in = port_in_err - int(prev_port_in_err)
                        derr_out = port_out_err - int(prev_port_out_err)
                        ddis_in = port_in_dis - int(prev_port_in_dis)
                        ddis_out = port_out_dis - int(prev_port_out_dis)
                        if derr_in >= 0:
                            in_err_per_sec = derr_in / dt
                        if derr_out >= 0:
                            out_err_per_sec = derr_out / dt
                        if ddis_in >= 0:
                            in_dis_per_sec = ddis_in / dt
                        if ddis_out >= 0:
                            out_dis_per_sec = ddis_out / dt

                    oper_status = None
                    try:
                        oper_status = v.get("oper_status") or v.get("oper-status")
                    except Exception:
                        oper_status = None
                    is_up = None
                    try:
                        is_up = v.get("is_up")
                    except Exception:
                        is_up = None
                    if is_up is None and oper_status is not None:
                        is_up = str(oper_status).strip().lower() in {"up", "active", "true", "1"}

                    next_if_state[port_norm] = {
                        "in_octets": port_in,
                        "out_octets": port_out,
                        "in_errors": port_in_err,
                        "out_errors": port_out_err,
                        "in_discards": port_in_dis,
                        "out_discards": port_out_dis,
                        "ts": now_ts,
                        "in_bps": float(port_in_bps),
                        "out_bps": float(port_out_bps),
                        "in_errors_per_sec": float(in_err_per_sec),
                        "out_errors_per_sec": float(out_err_per_sec),
                        "in_discards_per_sec": float(in_dis_per_sec),
                        "out_discards_per_sec": float(out_dis_per_sec),
                        "oper_status": oper_status,
                        "is_up": is_up,
                    }
                    if_metrics_to_add.append(InterfaceMetric(
                        device_id=device.id,
                        interface_name=str(port_norm),
                        traffic_in_bps=float(port_in_bps),
                        traffic_out_bps=float(port_out_bps),
                        in_errors_per_sec=float(in_err_per_sec),
                        out_errors_per_sec=float(out_err_per_sec),
                        in_discards_per_sec=float(in_dis_per_sec),
                        out_discards_per_sec=float(out_dis_per_sec),
                    ))
                    total_err = float(in_err_per_sec) + float(out_err_per_sec)
                    total_drop = float(in_dis_per_sec) + float(out_dis_per_sec)
                    health = "degraded" if (total_err >= 5.0 or total_drop >= 5.0) else "ok"
                    prev_health = prev_entry.get("health", "ok")
                    prev_is_up = prev_entry.get("is_up")
                    if prev_is_up is None and prev_entry.get("oper_status") is not None:
                        prev_is_up = str(prev_entry.get("oper_status")).strip().lower() in {"up", "active", "true", "1"}
                    next_if_state[port_norm]["health"] = health

                    if realtime_event_bus is not None:
                        if is_up is not None and prev_is_up is not None and bool(is_up) != bool(prev_is_up):
                            realtime_event_bus.publish(
                                "link_update",
                                {
                                    "device_id": int(device.id),
                                    "device_ip": device.ip_address,
                                    "interface": str(port_norm),
                                    "state": "up" if bool(is_up) else "down",
                                    "protocol": "LLDP",
                                    "ts": now.isoformat(),
                                    "source": "gnmi_oper_status",
                                },
                            )
                        if prev_health != health and (is_up is None or bool(is_up) is True):
                            realtime_event_bus.publish(
                                "link_update",
                                {
                                    "device_id": int(device.id),
                                    "device_ip": device.ip_address,
                                    "interface": str(port_norm),
                                    "state": "degraded" if health == "degraded" else "up",
                                    "protocol": "LLDP",
                                    "reason": "errors" if total_err >= 5.0 else ("drops" if total_drop >= 5.0 else "ok"),
                                    "ts": now.isoformat(),
                                    "source": "gnmi_health",
                                },
                            )
                    if total_err >= 5.0:
                        create_issue_if_not_exists(
                            save_db,
                            device.id,
                            f"Interface Errors ({port_norm})",
                            f"errors/s={total_err:.2f}",
                            "warning",
                            device.name,
                        )
                    if total_drop >= 5.0:
                        create_issue_if_not_exists(
                            save_db,
                            device.id,
                            f"Interface Drops ({port_norm})",
                            f"drops/s={total_drop:.2f}",
                            "warning",
                            device.name,
                        )
                new_meta["if_traffic_state"] = next_if_state

            device.latest_parsed_data = new_meta
            metrics_to_add.append(SystemMetric(
                device_id=device.id,
                cpu_usage=cpu,
                memory_usage=mem,
                traffic_in=traffic_in_bps,
                traffic_out=traffic_out_bps
            ))
            metric_events.append(
                {
                    "device_id": int(device.id),
                    "cpu_usage": float(cpu),
                    "memory_usage": float(mem),
                    "traffic_in_bps": float(traffic_in_bps),
                    "traffic_out_bps": float(traffic_out_bps),
                    "ts": now.isoformat(),
                    "source": "gnmi",
                }
            )
            if cpu >= 80:
                create_issue_if_not_exists(save_db, device.id, "High CPU", f"CPU: {cpu}%", "warning", device.name)
            if mem >= 85:
                create_issue_if_not_exists(save_db, device.id, "High Memory", f"Memory: {mem}%", "warning", device.name)

        if metrics_to_add:
            save_db.add_all(metrics_to_add)
        if if_metrics_to_add:
            save_db.add_all(if_metrics_to_add)
        save_db.commit()

        if metric_events:
            try:
                from app.services.realtime_event_bus import realtime_event_bus

                for ev in metric_events[:2000]:
                    realtime_event_bus.publish("metrics_update", ev)
            except Exception:
                pass

        try:
            r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
            pipe = r.pipeline()
            updated_count = 0
            for res in results:
                if res.get("ok"):
                    pipe.set(f"device:{res['id']}:last_metric_ts", int(now_ts), ex=120)
                    updated_count += 1
            if updated_count > 0:
                pipe.execute()
        except Exception as e:
            logger.warning(f"Redis update failed in collect_gnmi_metrics: {e}")

    except Exception:
        logger.exception("gNMI telemetry collection failed")
        save_db.rollback()
    finally:
        save_db.close()


@shared_task
def monitor_devices(device_ids: list[int]):
    if not device_ids:
        return
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from sqlalchemy import or_
    from app.models.device import Link

    ids = sorted({int(x) for x in device_ids if x is not None})
    db = SessionLocal()
    try:
        devices = db.query(Device).filter(Device.id.in_(ids)).all()
        if not devices:
            return
        links = (
            db.query(Link)
            .filter(
                (Link.target_device_id != None)
                & (
                    or_(
                        Link.source_device_id.in_(ids),
                        Link.target_device_id.in_(ids),
                    )
                )
            )
            .all()
        )
        ports_by_device = {}
        for l in links:
            if l.source_device_id and l.source_interface_name:
                ports_by_device.setdefault(l.source_device_id, set()).add(str(l.source_interface_name))
            if l.target_device_id and l.target_interface_name:
                ports_by_device.setdefault(l.target_device_id, set()).add(str(l.target_interface_name))
        targets = [
            {
                "id": d.id,
                "ip": d.ip_address,
                "comm": d.snmp_community,
                "snmp_version": getattr(d, "snmp_version", None) or "v2c",
                "snmp_port": int(getattr(d, "snmp_port", None) or 161),
                "snmp_v3_username": getattr(d, "snmp_v3_username", None),
                "snmp_v3_security_level": getattr(d, "snmp_v3_security_level", None),
                "snmp_v3_auth_proto": getattr(d, "snmp_v3_auth_proto", None),
                "snmp_v3_auth_key": getattr(d, "snmp_v3_auth_key", None),
                "snmp_v3_priv_proto": getattr(d, "snmp_v3_priv_proto", None),
                "snmp_v3_priv_key": getattr(d, "snmp_v3_priv_key", None),
                "link_ports": list(ports_by_device.get(d.id, set())),
            }
            for d in devices
        ]
    finally:
        db.close()

    def _poll(t):
        ip = t["ip"]
        if not ip:
            return {"id": t["id"], "alive": False}
        alive = ping_device(ip)
        if not alive:
            return {"id": t["id"], "alive": False}
        comm = t["comm"] or "public"
        snmp_version = str(t.get("snmp_version") or "v2c")
        snmp_port = int(t.get("snmp_port") or 161)
        try:
            snmp = SnmpManager(
                ip,
                comm,
                port=snmp_port,
                version=snmp_version,
                v3_username=t.get("snmp_v3_username"),
                v3_security_level=t.get("snmp_v3_security_level"),
                v3_auth_proto=t.get("snmp_v3_auth_proto"),
                v3_auth_key=t.get("snmp_v3_auth_key"),
                v3_priv_proto=t.get("snmp_v3_priv_proto"),
                v3_priv_key=t.get("snmp_v3_priv_key"),
            )
            st = snmp.check_status()
            if st.get("status") != "online":
                return {"id": t["id"], "alive": True, "snmp_online": False}
            res = snmp.get_resource_usage()
            link_ports = t.get("link_ports") or []
            if_counters = None
            try:
                if isinstance(link_ports, list) and len(link_ports) > 0:
                    if_counters = snmp.get_interface_counters_for_ports(link_ports)
                else:
                    raw = snmp.get_interface_counters_map()
                    norm = {}
                    if isinstance(raw, dict):
                        for k, v in raw.items():
                            pn = snmp.normalize_interface_name(k)
                            if pn and isinstance(v, dict):
                                norm[pn] = v
                    if_counters = norm
            except Exception:
                if_counters = None
            return {"id": t["id"], "alive": True, "snmp_online": True, "uptime": st.get("uptime"), "res": res, "if_counters": if_counters}
        except Exception as e:
            return {"id": t["id"], "alive": True, "snmp_online": False, "err": str(e)}

    polled = []
    with ThreadPoolExecutor(max_workers=min(20, len(targets) or 1)) as ex:
        futs = [ex.submit(_poll, t) for t in targets]
        for fut in as_completed(futs):
            try:
                polled.append(fut.result())
            except Exception:
                continue

    db = SessionLocal()
    try:
        now = datetime.datetime.now()
        now_ts = now.timestamp()
        for r in polled:
            d = db.query(Device).filter(Device.id == int(r["id"])).first()
            if not d:
                continue
            if not r.get("alive"):
                d.status = "offline"
                d.reachability_status = "unreachable"
                db.add(d)
                continue
            d.reachability_status = "reachable"
            if r.get("snmp_online"):
                d.status = "online"
                d.last_seen = now
                try:
                    d.uptime = parse_uptime(r.get("uptime"))
                except Exception:
                    pass
                res = r.get("res") or {}
                cpu = res.get("cpu_usage", res.get("cpu", 0))
                mem = res.get("memory_usage", res.get("memory", 0))
                try:
                    cpu = float(cpu) if cpu is not None else 0
                except Exception:
                    cpu = 0
                try:
                    mem = float(mem) if mem is not None else 0
                except Exception:
                    mem = 0
                meta = d.latest_parsed_data if isinstance(d.latest_parsed_data, dict) else {}
                if not isinstance(meta, dict):
                    meta = {}
                prev_if_state = meta.get("if_traffic_state", {}) if isinstance(meta.get("if_traffic_state", {}), dict) else {}
                next_if_state = dict(prev_if_state) if isinstance(prev_if_state, dict) else {}
                total_in_bps = 0.0
                total_out_bps = 0.0
                if_counters = r.get("if_counters") or {}
                if isinstance(if_counters, dict) and if_counters:
                    for port_norm, v in if_counters.items():
                        if not isinstance(v, dict):
                            continue
                        try:
                            port_in = int(v.get("in_octets", v.get("in", 0)) or 0)
                        except Exception:
                            port_in = 0
                        try:
                            port_out = int(v.get("out_octets", v.get("out", 0)) or 0)
                        except Exception:
                            port_out = 0
                        try:
                            port_in_err = int(v.get("in_errors", 0) or 0)
                        except Exception:
                            port_in_err = 0
                        try:
                            port_out_err = int(v.get("out_errors", 0) or 0)
                        except Exception:
                            port_out_err = 0
                        try:
                            port_in_dis = int(v.get("in_discards", 0) or 0)
                        except Exception:
                            port_in_dis = 0
                        try:
                            port_out_dis = int(v.get("out_discards", 0) or 0)
                        except Exception:
                            port_out_dis = 0

                        prev_entry = next_if_state.get(port_norm, {}) if isinstance(next_if_state.get(port_norm), dict) else {}
                        prev_port_in = prev_entry.get("in_octets", prev_entry.get("in", 0)) or 0
                        prev_port_out = prev_entry.get("out_octets", prev_entry.get("out", 0)) or 0
                        prev_port_in_err = prev_entry.get("in_errors", 0) or 0
                        prev_port_out_err = prev_entry.get("out_errors", 0) or 0
                        prev_port_in_dis = prev_entry.get("in_discards", 0) or 0
                        prev_port_out_dis = prev_entry.get("out_discards", 0) or 0
                        prev_port_ts = prev_entry.get("ts", 0) or 0

                        port_in_bps = 0.0
                        port_out_bps = 0.0
                        in_err_per_sec = 0.0
                        out_err_per_sec = 0.0
                        in_dis_per_sec = 0.0
                        out_dis_per_sec = 0.0
                        if prev_port_ts and (now_ts - float(prev_port_ts)) >= 1:
                            dt = now_ts - float(prev_port_ts)
                            din = port_in - int(prev_port_in)
                            dout = port_out - int(prev_port_out)
                            if din >= 0 and dout >= 0:
                                port_in_bps = (din * 8) / dt
                                port_out_bps = (dout * 8) / dt
                            derr_in = port_in_err - int(prev_port_in_err)
                            derr_out = port_out_err - int(prev_port_out_err)
                            ddis_in = port_in_dis - int(prev_port_in_dis)
                            ddis_out = port_out_dis - int(prev_port_out_dis)
                            if derr_in >= 0:
                                in_err_per_sec = derr_in / dt
                            if derr_out >= 0:
                                out_err_per_sec = derr_out / dt
                            if ddis_in >= 0:
                                in_dis_per_sec = ddis_in / dt
                            if ddis_out >= 0:
                                out_dis_per_sec = ddis_out / dt

                        next_if_state[port_norm] = {
                            "in_octets": port_in,
                            "out_octets": port_out,
                            "in_errors": port_in_err,
                            "out_errors": port_out_err,
                            "in_discards": port_in_dis,
                            "out_discards": port_out_dis,
                            "ts": now_ts,
                            "in_bps": float(port_in_bps),
                            "out_bps": float(port_out_bps),
                            "in_errors_per_sec": float(in_err_per_sec),
                            "out_errors_per_sec": float(out_err_per_sec),
                            "in_discards_per_sec": float(in_dis_per_sec),
                            "out_discards_per_sec": float(out_dis_per_sec),
                        }
                        db.add(InterfaceMetric(
                            device_id=d.id,
                            interface_name=str(port_norm),
                            traffic_in_bps=float(port_in_bps),
                            traffic_out_bps=float(port_out_bps),
                            in_errors_per_sec=float(in_err_per_sec),
                            out_errors_per_sec=float(out_err_per_sec),
                            in_discards_per_sec=float(in_dis_per_sec),
                            out_discards_per_sec=float(out_dis_per_sec),
                        ))
                        total_err = float(in_err_per_sec) + float(out_err_per_sec)
                        total_drop = float(in_dis_per_sec) + float(out_dis_per_sec)
                        if total_err >= 5.0:
                            create_issue_if_not_exists(
                                db,
                                d.id,
                                f"Interface Errors ({port_norm})",
                                f"errors/s={total_err:.2f}",
                                "warning",
                                d.name,
                            )
                        if total_drop >= 5.0:
                            create_issue_if_not_exists(
                                db,
                                d.id,
                                f"Interface Drops ({port_norm})",
                                f"drops/s={total_drop:.2f}",
                                "warning",
                                d.name,
                            )
                        total_in_bps += float(port_in_bps)
                        total_out_bps += float(port_out_bps)
                new_meta = dict(meta)
                if next_if_state:
                    new_meta["if_traffic_state"] = next_if_state
                d.latest_parsed_data = new_meta
                db.add(SystemMetric(device_id=d.id, cpu_usage=cpu, memory_usage=mem, traffic_in=total_in_bps, traffic_out=total_out_bps))
                if mem >= 85:
                    create_issue_if_not_exists(db, d.id, "High Memory", f"Memory: {mem}%", "warning", d.name)
                
                # [NEW] Evaluate Automation Rules
                r['resource_data'] = r.get('res')
                _evaluate_automation_rules(db, d, r)
            else:
                d.status = "unknown"
            db.add(d)
        db.commit()
    finally:
        db.close()


@shared_task
def burst_monitor_devices(device_ids: list[int], repeats: int = 3, interval_sec: int = 5):
    try:
        monitor_devices(device_ids)
    except Exception:
        pass
    r = int(repeats or 0)
    if r <= 1:
        return
    i = int(interval_sec or 0)
    if i < 1:
        i = 1
    try:
        burst_monitor_devices.apply_async(args=[device_ids, r - 1, i], countdown=i)
    except Exception:
        import time
        time.sleep(i)
        try:
            burst_monitor_devices(device_ids, r - 1, i)
        except Exception:
            pass

@shared_task
def full_ssh_sync_all():
    """
    [핵심] 1시간 주기 태스크: 전 장비 SSH 기반 풀 동기화 (Config, Neighbors, Inventory).
    순차적으로 진행하여 네트워크 및 서버 부하를 제어합니다.
    """
    from app.services.ssh_service import DeviceConnection, DeviceInfo
    from app.services.topology_link_service import TopologyLinkService
    import re
    
    db = SessionLocal()
    try:
        device_ids = [d.id for d in db.query(Device).all()]
    finally:
        db.close()

    for d_id in device_ids:
        db = SessionLocal()
        try:
            device = db.query(Device).filter(Device.id == d_id).first()
            if not device: continue
            
            inf = DeviceInfo(device.ip_address, device.ssh_username or "admin", device.ssh_password, device.enable_password, device.ssh_port or 22, device.device_type or "cisco_ios")
            conn = DeviceConnection(inf)
            if conn.connect():
                logger.info("SSH sync connected", extra={"device_id": device.id, "device_name": device.name})
                facts = conn.get_facts()
                config = conn.get_running_config()
                # [NEW] Neighbors 탐색
                neighbors = conn.get_neighbors()

                # Facts 업데이트
                if facts:
                    device.model = facts.get("model", device.model)
                    device.os_version = facts.get("os_version", device.os_version)
                    device.serial_number = facts.get("serial_number", device.serial_number)
                
                # 무선 데이터 수집 (WLC)
                if "wlc" in str(device.device_type).lower() or "9800" in str(device.model):
                    try:
                        from app.drivers.cisco.wlc_driver import CiscoWLCDriver
                        # 드라이버가 WLC 드라이버인지 확인 (또는 직접 명령 실행)
                        ap_parsed = conn.driver.connection.send_command("show ap summary", use_textfsm=True)
                        if isinstance(ap_parsed, list):
                            summary = {"ap_list": ap_parsed}
                            # 클라이언트 수 재확인
                            client_out = conn.driver.connection.send_command("show wireless client summary")
                            m = re.search(r"Number of Clients\s*:\s*(\d+)", client_out, re.IGNORECASE)
                            summary["total_clients"] = int(m.group(1)) if m else 0
                            device.latest_parsed_data = summary
                    except: pass
                
                device.last_seen = datetime.datetime.now()
                device.status = "online"

                TopologyLinkService.refresh_links_for_device(db, device, neighbors)

                db.commit()
                conn.disconnect()
        except Exception as e:
            logger.exception("SSH sync failed", extra={"device_id": d_id})
            db.rollback()
        finally:
            db.close()
