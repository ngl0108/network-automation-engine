from __future__ import annotations

import platform
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.device import Device, Issue, Link
from app.services.path_trace_service import PathTraceService


@dataclass(frozen=True)
class OneClickDiagnosisOptions:
    include_show_commands: bool = True
    show_timeout_sec: int = 12
    max_show_devices: int = 2
    recent_issue_minutes: int = 60


def _now_utc(now: Optional[datetime]) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _ping_once(ip_address: str, timeout_ms: int = 1000) -> bool:
    if not ip_address:
        return False
    is_windows = platform.system().lower() == "windows"
    count_flag = "-n" if is_windows else "-c"
    timeout_flag = "-w" if is_windows else "-W"
    timeout_val = str(int(timeout_ms)) if is_windows else str(max(1, int(timeout_ms / 1000)))
    cmd = ["ping", count_flag, "1", timeout_flag, timeout_val, str(ip_address)]
    try:
        return subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    except Exception:
        return False


def _norm_if_name(s: str) -> str:
    return str(s or "").strip().lower().replace(" ", "")


def _select_abnormal_hops(path_trace: Dict[str, Any], device_health: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    segments = path_trace.get("segments") or []
    out: List[Dict[str, Any]] = []

    for seg in segments:
        try:
            from_id = int(seg.get("from_id"))
        except Exception:
            continue
        link = seg.get("link") if isinstance(seg, dict) else None
        link_status = None
        if isinstance(link, dict):
            link_status = str(link.get("status") or "").lower()
        if link_status in {"down", "inactive"}:
            out.append({"type": "link", "device_id": from_id, "segment": seg})
            continue
        h = device_health.get(from_id) or {}
        if h.get("ping_ok") is False:
            out.append({"type": "ping", "device_id": from_id, "segment": seg})
            continue
        if h.get("critical_issues", 0) > 0:
            out.append({"type": "issue", "device_id": from_id, "segment": seg})
            continue

    if not out:
        node_ids = path_trace.get("path_node_ids") or []
        for did in node_ids:
            try:
                did_i = int(did)
            except Exception:
                continue
            h = device_health.get(did_i) or {}
            if h.get("warning_issues", 0) > 0:
                out.append({"type": "issue", "device_id": did_i, "segment": None})
                break

    return out


def _build_show_plan(device: Device, seg: Optional[Dict[str, Any]], dst_ip: str, reasons: List[str]) -> List[str]:
    dev_type = str(getattr(device, "device_type", "") or "").lower()
    is_junos = "junos" in dev_type
    is_arista = "arista" in dev_type or "eos" in dev_type
    port = None
    if isinstance(seg, dict):
        port = seg.get("from_port")
    port = str(port or "").strip()

    cmds: List[str] = []
    if port:
        if is_junos:
            cmds.append(f"show interfaces {port} extensive")
        else:
            cmds.append(f"show interfaces {port}")
            cmds.append(f"show interfaces {port} counters errors")

    if reasons:
        if any(r in {"link", "ping", "issue"} for r in reasons):
            if is_junos:
                cmds.append("show lldp neighbors detail")
            else:
                cmds.append("show lldp neighbors")
                cmds.append("show cdp neighbors detail")

    if is_junos:
        cmds.append(f"show route {dst_ip}")
    else:
        if is_arista:
            cmds.append(f"show ip route {dst_ip}")
        else:
            cmds.append(f"show ip route {dst_ip}")

    if is_junos:
        cmds.append("show bgp summary")
        cmds.append("show ospf neighbor")
    else:
        cmds.append("show ip bgp summary")
        cmds.append("show ip ospf neighbor")

    return cmds[:8]


def _run_show_commands(device: Device, commands: List[str], timeout_sec: int) -> Dict[str, str]:
    if not commands:
        return {}
    if not getattr(device, "ssh_password", None):
        return {"_error": "ssh_password not set"}

    from app.services.ssh_service import DeviceConnection, DeviceInfo

    dev_info = DeviceInfo(
        host=device.ip_address,
        username=device.ssh_username or "admin",
        password=device.ssh_password,
        secret=device.enable_password,
        port=int(device.ssh_port or 22),
        device_type=device.device_type or "cisco_ios",
    )
    conn = DeviceConnection(dev_info)
    if not conn.connect():
        return {"_error": "ssh connect failed"}

    out: Dict[str, str] = {}
    try:
        for cmd in commands:
            t0 = time.monotonic()
            try:
                res = conn.send_command(cmd, read_timeout=int(timeout_sec))
            except Exception as e:
                res = f"ERROR: {type(e).__name__}: {e}"
            dt = time.monotonic() - t0
            out[cmd] = f"{res}\n\n(elapsed={dt:.2f}s)"
    finally:
        try:
            conn.disconnect()
        except Exception:
            pass
    return out


class OneClickDiagnosisService:
    def __init__(self, db: Session):
        self.db = db

    def run(
        self,
        src_ip: str,
        dst_ip: str,
        options: Optional[OneClickDiagnosisOptions] = None,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        options = options or OneClickDiagnosisOptions()
        now_dt = _now_utc(now)

        path_trace = PathTraceService(self.db).trace_path(src_ip, dst_ip)
        if isinstance(path_trace, dict) and path_trace.get("error"):
            return {"ok": False, "error": path_trace.get("error"), "path_trace": path_trace}

        node_ids = [int(x) for x in (path_trace.get("path_node_ids") or []) if str(x).isdigit()]
        devices = self.db.query(Device).filter(Device.id.in_(node_ids)).all() if node_ids else []
        dev_by_id = {int(d.id): d for d in devices}

        issue_since = now_dt - timedelta(minutes=int(options.recent_issue_minutes))
        issues = (
            self.db.query(Issue.device_id, Issue.severity, Issue.status)
            .filter(Issue.status == "active", Issue.created_at >= issue_since)
            .all()
        )
        issue_counts: Dict[int, Dict[str, int]] = {}
        for device_id, sev, _ in issues:
            if device_id is None:
                continue
            did = int(device_id)
            c = issue_counts.setdefault(did, {"critical": 0, "warning": 0, "info": 0})
            s = str(sev or "info").lower()
            if s not in c:
                s = "info"
            c[s] += 1

        device_health: Dict[int, Dict[str, Any]] = {}
        for did in node_ids:
            dev = dev_by_id.get(did)
            ip = dev.ip_address if dev else None
            ping_ok = _ping_once(ip) if ip else False
            ic = issue_counts.get(did) or {"critical": 0, "warning": 0, "info": 0}
            device_health[did] = {
                "device_id": did,
                "name": getattr(dev, "name", None),
                "ip_address": ip,
                "ping_ok": bool(ping_ok),
                "critical_issues": int(ic.get("critical", 0)),
                "warning_issues": int(ic.get("warning", 0)),
                "info_issues": int(ic.get("info", 0)),
            }

        abnormal = _select_abnormal_hops(path_trace, device_health)

        show_results: List[Dict[str, Any]] = []
        if options.include_show_commands and abnormal:
            picked = []
            for a in abnormal:
                did = a.get("device_id")
                if did is None or did in picked:
                    continue
                picked.append(did)
                if len(picked) >= int(options.max_show_devices):
                    break

            for did in picked:
                dev = dev_by_id.get(int(did))
                if not dev:
                    continue
                seg = None
                reasons = []
                for a in abnormal:
                    if int(a.get("device_id") or -1) == int(did):
                        seg = a.get("segment")
                        reasons.append(str(a.get("type")))
                cmds = _build_show_plan(dev, seg, dst_ip, reasons)
                outs = _run_show_commands(dev, cmds, int(options.show_timeout_sec))
                show_results.append(
                    {
                        "device_id": int(did),
                        "device_name": dev.name,
                        "device_ip": dev.ip_address,
                        "reasons": reasons,
                        "commands": cmds,
                        "outputs": outs,
                    }
                )

        summary = {
            "status": str(path_trace.get("status") or "unknown"),
            "mode": str(path_trace.get("mode") or "unknown"),
            "abnormal_count": len(abnormal),
            "show_collected": len(show_results),
        }

        return {
            "ok": True,
            "summary": summary,
            "path_trace": path_trace,
            "device_health": list(device_health.values()),
            "abnormal": abnormal,
            "show": show_results,
            "ts": now_dt.isoformat(),
        }
