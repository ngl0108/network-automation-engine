import asyncio
import subprocess
import ipaddress
import logging
import os
try:
    import nmap
except ImportError:  # pragma: no cover
    nmap = None
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from datetime import datetime
from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models.discovery import DiscoveryJob, DiscoveredDevice
from app.models.credentials import SnmpCredentialProfile
from app.models.device import Device
from app.models.device import Site
from app.models.settings import SystemSetting
from app.db.session import SessionLocal
from app.services.snmp_service import SnmpManager
from app.core.device_fingerprints import (
    identify_vendor_by_oid,
    extract_model_from_descr,
    get_driver_for_vendor
)

logger = logging.getLogger(__name__)

class DiscoveryService:
    def __init__(self, db: Session):
        self.db = db

    def _append_job_log(self, job: DiscoveryJob, message: str, max_chars: int = 20000) -> None:
        msg = str(message or "")
        if not msg:
            return
        if job.logs is None:
            job.logs = ""
        if not msg.startswith("\n"):
            msg = "\n" + msg
        job.logs = (job.logs or "") + msg
        if len(job.logs) > max_chars:
            job.logs = job.logs[-max_chars:]

    def _extract_up_hosts(self, nm) -> list:
        hosts = []
        for h in nm.all_hosts() if nm else []:
            try:
                if nm[h].state() == "up":
                    hosts.append(h)
            except Exception:
                continue
        return hosts

    def _tcp_alive_sweep(self, cidr: str, ports=None, max_hosts: int = 1024, timeout: float = 0.25, include_cidrs: list[str] | None = None, exclude_cidrs: list[str] | None = None) -> list:
        network = ipaddress.ip_network(cidr, strict=False)
        total = int(network.num_addresses) - 2 if int(network.num_addresses) >= 2 else 0
        if total > max_hosts:
            return []

        ports = ports or [22, 23, 80, 443, 161, 830]

        import socket

        def check(ip: str) -> bool:
            for p in ports:
                s = None
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(timeout)
                    r = s.connect_ex((ip, int(p)))
                    if r in (0, 111, 10061):
                        return True
                except Exception:
                    continue
                finally:
                    try:
                        if s is not None:
                            s.close()
                    except Exception:
                        pass
            return False

        alive = []
        include_nets = []
        exclude_nets = []
        for c in include_cidrs or []:
            try:
                include_nets.append(ipaddress.ip_network(str(c).strip(), strict=False))
            except Exception:
                continue
        for c in exclude_cidrs or []:
            try:
                exclude_nets.append(ipaddress.ip_network(str(c).strip(), strict=False))
            except Exception:
                continue

        ips = []
        for ip in network.hosts():
            try:
                ip_obj = ipaddress.ip_address(str(ip))
            except Exception:
                continue
            if ip_obj.is_loopback or ip_obj.is_multicast or ip_obj.is_unspecified or ip_obj.is_link_local:
                continue
            if any(ip_obj in n for n in exclude_nets):
                continue
            if include_nets and not any(ip_obj in n for n in include_nets):
                continue
            ips.append(str(ip_obj))

        base_workers = int(os.getenv("DISCOVERY_PING_MAX_WORKERS", "0") or 0)
        if base_workers <= 0:
            cpu = os.cpu_count() or 4
            base_workers = cpu * 10
        max_workers = max(10, min(200, base_workers, len(ips) or 1))

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(check, ip): ip for ip in ips}
            for fut in as_completed(futs):
                ip = futs[fut]
                try:
                    if fut.result():
                        alive.append(ip)
                except Exception:
                    continue
        return alive

    def create_scan_job(
        self,
        cidr: str,
        community: str,
        site_id: int | None = None,
        snmp_profile_id: int | None = None,
        snmp_version: str = "v2c",
        snmp_port: int = 161,
        snmp_v3_username: str | None = None,
        snmp_v3_security_level: str | None = None,
        snmp_v3_auth_proto: str | None = None,
        snmp_v3_auth_key: str | None = None,
        snmp_v3_priv_proto: str | None = None,
        snmp_v3_priv_key: str | None = None,
    ) -> DiscoveryJob:
        """
        Job 생성 및 초기화 (동기 실행)
        """
        profile = None
        if snmp_profile_id is not None:
            profile = self.db.query(SnmpCredentialProfile).filter(SnmpCredentialProfile.id == snmp_profile_id).first()
        if profile is None and site_id is not None:
            site = self.db.query(Site).filter(Site.id == site_id).first()
            if site and getattr(site, "snmp_profile_id", None):
                profile = self.db.query(SnmpCredentialProfile).filter(SnmpCredentialProfile.id == site.snmp_profile_id).first()

        if profile is not None:
            effective_community = profile.snmp_community
            effective_version = profile.snmp_version
            effective_port = profile.snmp_port
            effective_v3_username = profile.snmp_v3_username
            effective_v3_security_level = profile.snmp_v3_security_level
            effective_v3_auth_proto = profile.snmp_v3_auth_proto
            effective_v3_auth_key = profile.snmp_v3_auth_key
            effective_v3_priv_proto = profile.snmp_v3_priv_proto
            effective_v3_priv_key = profile.snmp_v3_priv_key
        else:
            effective_community = community
            effective_version = snmp_version
            effective_port = snmp_port
            effective_v3_username = snmp_v3_username
            effective_v3_security_level = snmp_v3_security_level
            effective_v3_auth_proto = snmp_v3_auth_proto
            effective_v3_auth_key = snmp_v3_auth_key
            effective_v3_priv_proto = snmp_v3_priv_proto
            effective_v3_priv_key = snmp_v3_priv_key

        job = DiscoveryJob(
            cidr=cidr,
            site_id=site_id,
            snmp_profile_id=(profile.id if profile else snmp_profile_id),
            snmp_community=effective_community,
            snmp_version=(effective_version or "v2c"),
            snmp_port=int(effective_port or 161),
            snmp_v3_username=effective_v3_username,
            snmp_v3_security_level=effective_v3_security_level,
            snmp_v3_auth_proto=effective_v3_auth_proto,
            snmp_v3_auth_key=effective_v3_auth_key,
            snmp_v3_priv_proto=effective_v3_priv_proto,
            snmp_v3_priv_key=effective_v3_priv_key,
            status="pending",
            logs="Job Created. Waiting for worker...",
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def run_scan_worker(self, job_id: int):
        """
        Worker Process: 실제 스캔 실행 (Background Task) with Nmap & SNMP
        """
        db = SessionLocal()
        job = db.query(DiscoveryJob).filter(DiscoveryJob.id == job_id).first()
        
        if not job:
            db.close()
            return

        try:
            job.status = "running"
            self._append_job_log(job, "Worker Started. Initializing Scanner...")
            db.commit()

            def _get_setting_value(key: str) -> str:
                setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
                return setting.value if setting and setting.value and setting.value != "********" else ""

            def _parse_cidr_list(raw: str) -> list[str]:
                out = []
                for part in (raw or "").replace("\n", ",").split(","):
                    s = part.strip()
                    if s:
                        out.append(s)
                return out

            cidr = job.cidr
            snmp_profile = {
                "community": (job.snmp_community or "public"),
                "version": (getattr(job, "snmp_version", None) or "v2c"),
                "port": int(getattr(job, "snmp_port", None) or 161),
                "v3_username": getattr(job, "snmp_v3_username", None),
                "v3_security_level": getattr(job, "snmp_v3_security_level", None),
                "v3_auth_proto": getattr(job, "snmp_v3_auth_proto", None),
                "v3_auth_key": getattr(job, "snmp_v3_auth_key", None),
                "v3_priv_proto": getattr(job, "snmp_v3_priv_proto", None),
                "v3_priv_key": getattr(job, "snmp_v3_priv_key", None),
            }
            try:
                raw_lim = (_get_setting_value("auto_credential_max_profiles") or "").strip()
                try:
                    max_profiles = int(raw_lim)
                except Exception:
                    max_profiles = 8
                if max_profiles < 0:
                    max_profiles = 0
                if max_profiles > 50:
                    max_profiles = 50
                if max_profiles and getattr(job, "snmp_profile_id", None) is None:
                    profiles = db.query(SnmpCredentialProfile).order_by(SnmpCredentialProfile.id.asc()).limit(max_profiles).all()
                    pool = []
                    for p in profiles:
                        pool.append(
                            {
                                "profile_id": p.id,
                                "community": getattr(p, "snmp_community", None) or "public",
                                "version": getattr(p, "snmp_version", None) or "v2c",
                                "port": int(getattr(p, "snmp_port", None) or 161),
                                "v3_username": getattr(p, "snmp_v3_username", None),
                                "v3_security_level": getattr(p, "snmp_v3_security_level", None),
                                "v3_auth_proto": getattr(p, "snmp_v3_auth_proto", None),
                                "v3_auth_key": getattr(p, "snmp_v3_auth_key", None),
                                "v3_priv_proto": getattr(p, "snmp_v3_priv_proto", None),
                                "v3_priv_key": getattr(p, "snmp_v3_priv_key", None),
                            }
                        )
                    snmp_profile["credential_pool"] = pool
            except Exception:
                pass

            network = ipaddress.ip_network(cidr, strict=False)
            host_count = int(network.num_addresses) - 2 if int(network.num_addresses) >= 2 else 0
            job.total_ips = max(0, host_count)
            self._append_job_log(job, f"Target Network: {cidr} ({job.total_ips} hosts)")
            
            # Nmap Scanner Init
            nm = None
            if nmap is not None:
                nm = nmap.PortScanner()
            
            # --- Phase 1: Fast Ping Scan (Nmap) ---
            # Nmap is much faster than running ping subprocess for each IP
            active_hosts = []
            include_cidrs = _parse_cidr_list(_get_setting_value("discovery_scope_include_cidrs"))
            exclude_cidrs = _parse_cidr_list(_get_setting_value("discovery_scope_exclude_cidrs"))
            prefer_private = (_get_setting_value("discovery_prefer_private") or "true").strip().lower() in ("true", "1", "yes", "y", "on")
            if nm is not None:
                scan_args = "-sn -PE -PP"
                self._append_job_log(job, f"[Phase 1] Ping Sweeping with Nmap ({scan_args})...")
                db.commit()
                nm.scan(hosts=cidr, arguments=scan_args)
                active_hosts = self._extract_up_hosts(nm)

                if len(active_hosts) == 0:
                    scan_args2 = "-sn -PS22,23,80,443,161,830 -PA80,443"
                    self._append_job_log(job, f"[Phase 1b] TCP Ping Sweeping with Nmap ({scan_args2})...")
                    db.commit()
                    nm.scan(hosts=cidr, arguments=scan_args2)
                    active_hosts = self._extract_up_hosts(nm)
            else:
                self._append_job_log(job, "[Phase 1] python-nmap missing; using TCP connect probe fallback...")
                db.commit()
                active_hosts = self._tcp_alive_sweep(cidr, include_cidrs=include_cidrs, exclude_cidrs=exclude_cidrs)

            try:
                include_nets = []
                exclude_nets = []
                for c in include_cidrs:
                    try:
                        include_nets.append(ipaddress.ip_network(str(c).strip(), strict=False))
                    except Exception:
                        continue
                for c in exclude_cidrs:
                    try:
                        exclude_nets.append(ipaddress.ip_network(str(c).strip(), strict=False))
                    except Exception:
                        continue
                filtered = []
                for ip in active_hosts:
                    try:
                        ip_obj = ipaddress.ip_address(str(ip).strip())
                    except Exception:
                        continue
                    if ip_obj.is_loopback or ip_obj.is_multicast or ip_obj.is_unspecified or ip_obj.is_link_local:
                        continue
                    if any(ip_obj in n for n in exclude_nets):
                        continue
                    if include_nets and not any(ip_obj in n for n in include_nets):
                        continue
                    filtered.append(str(ip_obj))
                if prefer_private:
                    filtered.sort(key=lambda s: (0 if ipaddress.ip_address(s).is_private else 1, s))
                active_hosts = filtered
            except Exception:
                pass

            self._append_job_log(job, f"[Phase 1] Found {len(active_hosts)} active hosts.")
            self._append_job_log(job, "[Phase 2] Deep Inspection (SNMP & Ports)...")
            db.commit()
            
            # --- Phase 2: Deep Inspection (Parallel) ---
            def _get_int_setting(key: str, default: int) -> int:
                raw = (_get_setting_value(key) or "").strip()
                try:
                    return int(raw)
                except Exception:
                    return default

            max_workers = _get_int_setting("discovery_max_workers", 60)
            max_workers = max(10, min(200, max_workers))

            commit_batch = _get_int_setting("discovery_commit_batch_size", 25)
            commit_batch = max(5, min(200, commit_batch))

            inflight_mult = _get_int_setting("discovery_inflight_multiplier", 4)
            inflight_mult = max(2, min(10, inflight_mult))

            existing_devices = {
                ip: did
                for did, ip in db.query(Device.id, Device.ip_address).filter(Device.ip_address.isnot(None)).all()
            }

            completed_count = 0
            job.scanned_ips = 0
            job.total_ips = len(active_hosts)
            db.commit()

            pending_rows = []
            pending_logs = []

            def flush_pending():
                nonlocal pending_rows, pending_logs
                if pending_rows:
                    try:
                        db.add_all(pending_rows)
                        pending_rows = []
                        db.flush()
                    except IntegrityError:
                        db.rollback()
                        for r in pending_rows:
                            self._save_discovered_device(db, job.id, {
                                "ip_address": r.ip_address,
                                "hostname": r.hostname,
                                "vendor": r.vendor,
                                "model": r.model,
                                "os_version": r.os_version,
                                "snmp_status": r.snmp_status,
                                "device_type": r.device_type,
                                "sys_object_id": getattr(r, "sys_object_id", None),
                                "sys_descr": getattr(r, "sys_descr", None),
                                "vendor_confidence": getattr(r, "vendor_confidence", 0.0),
                                "chassis_candidate": getattr(r, "chassis_candidate", False),
                                "issues": getattr(r, "issues", None),
                                "evidence": getattr(r, "evidence", None),
                            })
                        pending_rows = []
                if pending_logs:
                    self._append_job_log(job, "\n".join(pending_logs))
                    pending_logs = []
                db.commit()

            def build_row(result: dict) -> DiscoveredDevice:
                ip = result.get("ip_address")
                matched_id = existing_devices.get(ip)
                status = "existing" if matched_id else "new"
                return DiscoveredDevice(
                    job_id=job.id,
                    ip_address=ip,
                    hostname=result.get("hostname") or ip,
                    vendor=result.get("vendor"),
                    model=result.get("model"),
                    os_version=result.get("os_version"),
                    snmp_status=result.get("snmp_status", "unknown"),
                    status=status,
                    matched_device_id=matched_id,
                    device_type=result.get("device_type") or "unknown",
                    sys_object_id=result.get("sys_object_id"),
                    sys_descr=result.get("sys_descr"),
                    vendor_confidence=float(result.get("vendor_confidence") or 0.0),
                    chassis_candidate=bool(result.get("chassis_candidate") or False),
                    issues=result.get("issues"),
                    evidence=result.get("evidence"),
                )

            inflight = max_workers * inflight_mult
            active_iter = iter([str(ip) for ip in active_hosts])

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {}
                for _ in range(inflight):
                    ip = next(active_iter, None)
                    if not ip:
                        break
                    future_map[executor.submit(self._scan_single_host, ip, snmp_profile)] = ip

                while future_map:
                    done, _ = wait(list(future_map.keys()), return_when=FIRST_COMPLETED)
                    for fut in done:
                        ip = future_map.pop(fut, None)
                        if not ip:
                            continue
                        try:
                            result = fut.result()
                            if result:
                                vendor_str = f"{result.get('vendor','')} {result.get('model','')}".strip()
                                pending_logs.append(f"  [+] {ip}: {vendor_str} ({result.get('snmp_status')})")
                                pending_rows.append(build_row(result))
                            completed_count += 1
                            job.scanned_ips = completed_count
                            if completed_count % commit_batch == 0:
                                flush_pending()
                        except Exception as e:
                            pending_logs.append(f"  [!] {ip}: inspect error {str(e)}")
                        finally:
                            nxt = next(active_iter, None)
                            if nxt:
                                future_map[executor.submit(self._scan_single_host, nxt, snmp_profile)] = nxt

                flush_pending()

            try:
                DiscoveryService(db).auto_approve_job(job.id)
            except Exception:
                pass
            
            job.status = "completed"
            job.completed_at = datetime.now()
            self._append_job_log(job, "Scan Completed Successfully.")
            db.commit()

            try:
                from app.services.topology_snapshot_policy_service import TopologySnapshotPolicyService
                from app.models.settings import SystemSetting

                row = db.query(SystemSetting).filter(SystemSetting.key == "topology_snapshot_auto_on_discovery_job_complete").first()
                enabled = True
                if row and row.value is not None:
                    enabled = str(row.value).strip().lower() in {"1", "true", "yes", "y", "on"}
                if enabled:
                    TopologySnapshotPolicyService.maybe_create_snapshot(
                        db,
                        site_id=getattr(job, "site_id", None),
                        job_id=int(job.id),
                        trigger="discovery_job_completed",
                    )
            except Exception:
                pass

        except Exception as e:
            job.status = "failed"
            self._append_job_log(job, f"[Error] Scan Failed: {str(e)}")
            db.commit()
        finally:
            db.close()

    def _scan_single_host(self, ip: str, snmp_profile: dict):
        """
        개별 호스트 정밀 스캔
        1. SNMP Attempt
        2. If SNMP Fails -> Port Scan (SSH, HTTP) to guess device
        """
        info = {
            "ip_address": ip,
            "snmp_status": "unknown",
            "hostname": ip,
            "vendor": "Unknown",
            "model": "",
            "os_version": "",
            "device_type": "unknown",
            "sys_object_id": None,
            "sys_descr": None,
            "mac_address": None,
            "vendor_confidence": 0.0,
            "chassis_candidate": False,
            "issues": [],
            "evidence": {},
        }

        def add_issue(code: str, severity: str, message: str, hint: str = None):
            issue = {"code": code, "severity": severity, "message": message}
            if hint:
                issue["hint"] = hint
            info["issues"].append(issue)

        def normalize_mac(value):
            if value is None:
                return None
            if isinstance(value, (bytes, bytearray)):
                b = bytes(value)
                if len(b) < 6:
                    return None
                s = b[:6].hex()
                return f"{s[0:4]}.{s[4:8]}.{s[8:12]}".lower()
            s0 = str(value).strip()
            if not s0:
                return None
            s = s0.lower().replace("0x", "")
            s = re.sub(r"[^0-9a-f]", "", s)
            if len(s) < 12:
                return None
            s = s[:12]
            return f"{s[0:4]}.{s[4:8]}.{s[8:12]}".lower()

        profile = snmp_profile or {}
        credential_pool = profile.get("credential_pool")
        if not isinstance(credential_pool, list):
            credential_pool = []

        def _try_snmp(p: dict):
            comm = (p.get("community") or "public").strip() or "public"
            ver = (p.get("version") or "v2c").strip().lower() or "v2c"
            prt = int(p.get("port") or 161)
            snmp = SnmpManager(
                ip,
                community=comm,
                port=prt,
                version=ver,
                v3_username=p.get("v3_username"),
                v3_security_level=p.get("v3_security_level"),
                v3_auth_proto=p.get("v3_auth_proto"),
                v3_auth_key=p.get("v3_auth_key"),
                v3_priv_proto=p.get("v3_priv_proto"),
                v3_priv_key=p.get("v3_priv_key"),
            )
            return snmp, snmp.get_system_info(), comm, ver, prt, p.get("profile_id")

        snmp, sysinfo, community, version, port, matched_profile_id = _try_snmp(profile)
        if not sysinfo:
            for p in credential_pool:
                if not isinstance(p, dict):
                    continue
                snmp, sysinfo, community, version, port, matched_profile_id = _try_snmp(p)
                if sysinfo:
                    break
        if sysinfo:
            info["snmp_status"] = "reachable"
            sys_descr = str(sysinfo.get("sysDescr") or "")
            sys_oid = str(sysinfo.get("sysObjectID") or "")
            sys_name = str(sysinfo.get("sysName") or "")

            info["hostname"] = sys_name if sys_name else ip
            
            # Enhanced Identification
            vendor, confidence = identify_vendor_by_oid(sys_oid, sys_descr)
            info["vendor"] = vendor
            info["model"] = extract_model_from_descr(vendor, sys_descr) or self._identify_model(sys_descr)
            info["os_version"] = self._extract_version(sys_descr)
            info["sys_object_id"] = sys_oid
            info["sys_descr"] = sys_descr

            info["device_type"] = get_driver_for_vendor(vendor)
            info["vendor_confidence"] = confidence
            info["chassis_candidate"] = self._estimate_chassis_candidate(sys_descr, info["model"], info["vendor"])
            info["evidence"]["snmp_version"] = version
            if matched_profile_id is not None:
                try:
                    info["evidence"]["snmp_profile_id"] = int(matched_profile_id)
                except Exception:
                    info["evidence"]["snmp_profile_id"] = str(matched_profile_id)
            info["evidence"]["snmp_sys_oid"] = sys_oid

            lldp_oid = "1.0.8802.1.1.2.1.3.2.0"
            bridge_oid = "1.3.6.1.2.1.17.1.2.0"
            qbridge_oid = "1.3.6.1.2.1.17.7.1.1.1.0"
            probe = snmp.get_oids([lldp_oid, bridge_oid, qbridge_oid]) or {}
            info["evidence"]["snmp_probe"] = {
                "lldp": bool(probe.get(lldp_oid)),
                "bridge": bool(probe.get(bridge_oid)),
                "qbridge": bool(probe.get(qbridge_oid)),
            }
            try:
                bridge_addr_oid = "1.3.6.1.2.1.17.1.1.0"
                lldp_loc_subtype_oid = "1.0.8802.1.1.2.1.3.1.0"
                lldp_loc_id_oid = "1.0.8802.1.1.2.1.3.2.0"
                mac_probe = snmp.get_oids([bridge_addr_oid, lldp_loc_subtype_oid, lldp_loc_id_oid]) or {}
                mac = normalize_mac(mac_probe.get(bridge_addr_oid))
                source = "bridge"
                if not mac:
                    subtype = str(mac_probe.get(lldp_loc_subtype_oid) or "").strip()
                    if subtype == "4":
                        mac = normalize_mac(mac_probe.get(lldp_loc_id_oid))
                        source = "lldp"
                if mac:
                    info["mac_address"] = mac
                    info["evidence"]["mac_source"] = source
            except Exception:
                pass
            if not probe.get(lldp_oid):
                add_issue(
                    "snmp_lldp_missing",
                    "warn",
                    "SNMP는 되지만 LLDP-MIB가 조회되지 않습니다.",
                    "LLDP 활성화 또는 SNMP view/ACL에서 1.0.8802.1.1.2(LLDP-MIB) 허용을 확인하세요.",
                )
            if not probe.get(bridge_oid):
                add_issue(
                    "snmp_bridge_missing",
                    "warn",
                    "SNMP는 되지만 BRIDGE-MIB가 조회되지 않습니다.",
                    "L2 스위치가 아니거나, SNMP view/ACL에서 1.3.6.1.2.1.17(BRIDGE-MIB) 허용을 확인하세요.",
                )

            if info["device_type"] == "unknown":
                add_issue(
                    "device_type_unknown",
                    "info",
                    "장비 타입(device_type) 자동 판별이 확실하지 않습니다.",
                    "등록 후 SSH/SNMP Sync로 보강되며, 필요시 수동으로 device_type을 지정하세요.",
                )

            return info

        # 2. SNMP Failed -> Port Scan (Fallback)
        info["snmp_status"] = "unreachable"
        info["vendor_confidence"] = 0.05
        add_issue("snmp_unreachable", "warn", "SNMP 응답이 없습니다.", "UDP 161 접근(방화벽/ACL), SNMP 버전(v3/v2c/v1), 인증정보(Auth/Priv 또는 community), SNMP view 제한을 확인하세요.")
        try:
            if nmap is None:
                raise RuntimeError("python-nmap is not installed")
            nm = nmap.PortScanner()
            # Scan common headers: 22(SSH), 23(Telnet), 80(HTTP), 443(HTTPS), 161(SNMP), 830(Netconf)
            nm.scan(ip, arguments='-p 22,23,80,443,161,830 -T4 --open')
            
            if ip in nm.all_hosts():
                tcp = nm[ip].get('tcp', {})
                open_ports = [p for p in tcp.keys()]
                
                if 22 in open_ports or 830 in open_ports:
                     info["vendor"] = "Unknown (SSH/Netconf Open)"
                     info["device_type"] = "manageable_device" # Will be mapped to 'generic' later
                     info["vendor_confidence"] = 0.15
                     info["evidence"]["open_ports"] = open_ports
                     add_issue("ssh_open_snmp_blocked", "info", "SSH/NETCONF는 열려 있지만 SNMP는 실패했습니다.", "SNMP(UDP 161) 방화벽/ACL 또는 커뮤니티 설정을 확인하세요.")
                elif 80 in open_ports or 443 in open_ports:
                     info["vendor"] = "Unknown (Web Interface Open)"
                     info["device_type"] = "web_device"
                     info["vendor_confidence"] = 0.10
                     info["evidence"]["open_ports"] = open_ports
                else:
                     info["vendor"] = "Unknown (ICMP Only)"
                     info["vendor_confidence"] = 0.05
                     info["evidence"]["open_ports"] = open_ports
                     
                # OUI (MAC Vendor) Lookup if available (requires root generally)
                if 'mac' in nm[ip].get('addresses', {}):
                     mac_value = nm[ip]['addresses'].get('mac')
                     mac_norm = normalize_mac(mac_value)
                     if mac_norm:
                         info["mac_address"] = mac_norm
                         info["evidence"]["mac_source"] = "nmap"
                     mac_vendor = nm[ip]['vendor'].get(nm[ip]['addresses']['mac'], '')
                     if mac_vendor:
                         info["vendor"] = f"{mac_vendor} (MAC)"
                         info["vendor_confidence"] = 0.40
                         
        except Exception as e:
             info["vendor"] = f"Scan Error: {str(e)}"
             info["vendor_confidence"] = 0.0
             add_issue("scan_error", "error", "포트 스캔 중 오류가 발생했습니다.", str(e))

        return info



    def _estimate_chassis_candidate(self, sys_descr: str, model: str, vendor: str) -> bool:
        text = f"{sys_descr or ''} {model or ''}".lower()
        if "chassis" in text:
            return True
        if any(k in text for k in ("c940", "c960", "c950", "nexus 950", "n9k", "nexus 9k", "mx", "ptx", "qfx10", "dcs-7500", "ce128", "s127", "s97")):
            return True
        v = str(vendor or "").lower()
        if v in ("cisco", "juniper", "arista", "huawei", "aruba") and any(k in text for k in ("sup", "supervisor", "linecard", "fpc", "pic", "mpc", "lpu")):
            return True
        return False

    def _identify_model(self, sys_descr):
        if "C3750" in sys_descr: return "Catalyst 3750"
        if "C2960" in sys_descr: return "Catalyst 2960"
        if "N9K" in sys_descr: return "Nexus 9000"
        if "CSR1000V" in sys_descr: return "CSR1000V"
        return ""

    def _extract_version(self, sys_descr):
        # Simplified version extraction
        parts = sys_descr.split(',')
        if len(parts) > 1:
            return parts[1].strip()
        return ""

    def _save_discovered_device(self, db, job_id, data):
        existing_device = db.query(Device).filter(Device.ip_address == data['ip_address']).first()
        status = "existing" if existing_device else "new"
        matched_id = existing_device.id if existing_device else None

        issues = data.get("issues") or []
        evidence = data.get("evidence") or {}
        try:
            hn = (data.get("hostname") or "").strip()
            if hn:
                host_conflict = db.query(Device).filter(or_(Device.name == hn, Device.hostname == hn)).first()
                if host_conflict and (not matched_id or host_conflict.id != matched_id):
                    issues = list(issues) + [{
                        "code": "hostname_conflict",
                        "severity": "warn",
                        "message": "Hostname이 기존 관리 장비와 중복됩니다.",
                        "hint": f"기존 장비(ID:{host_conflict.id})와 이름 충돌 가능성이 있어 확인이 필요합니다.",
                    }]
        except Exception:
            pass
        
        # Calculate snmp status text from data if needed, or use what's passed
        snmp_status = data.get('snmp_status', 'unknown')
        existing = db.query(DiscoveredDevice).filter(
            DiscoveredDevice.job_id == job_id,
            DiscoveredDevice.ip_address == data['ip_address'],
        ).first()

        if existing:
            existing.hostname = data.get("hostname") or existing.hostname
            existing.vendor = data.get("vendor") or existing.vendor
            existing.model = data.get("model") or existing.model
            existing.os_version = data.get("os_version") or existing.os_version
            existing.mac_address = data.get("mac_address") or existing.mac_address
            existing.snmp_status = snmp_status
            existing.status = existing.status if existing.status in ("approved", "ignored") else status
            existing.matched_device_id = matched_id
            existing.device_type = data.get("device_type") or existing.device_type
            existing.sys_object_id = data.get("sys_object_id") or existing.sys_object_id
            existing.sys_descr = data.get("sys_descr") or existing.sys_descr
            existing.vendor_confidence = data.get("vendor_confidence") if data.get("vendor_confidence") is not None else existing.vendor_confidence
            existing.chassis_candidate = data.get("chassis_candidate") if data.get("chassis_candidate") is not None else existing.chassis_candidate
            existing.issues = issues if issues is not None else existing.issues
            existing.evidence = evidence if evidence is not None else existing.evidence
        else:
            discovered = DiscoveredDevice(
                job_id=job_id,
                ip_address=data['ip_address'],
                hostname=data.get('hostname') or data['ip_address'],
                vendor=data.get('vendor'),
                model=data.get('model'),
                os_version=data.get('os_version'),
                mac_address=data.get("mac_address"),
                snmp_status=snmp_status,
                status=status,
                matched_device_id=matched_id,
                device_type=data.get("device_type") or "unknown",
                sys_object_id=data.get("sys_object_id"),
                sys_descr=data.get("sys_descr"),
                vendor_confidence=data.get("vendor_confidence") or 0.0,
                chassis_candidate=bool(data.get("chassis_candidate") or False),
                issues=issues,
                evidence=evidence,
            )
            db.add(discovered)
            db.flush()

    def approve_device(self, discovered_id: int):
        discovered = self.db.query(DiscoveredDevice).filter(DiscoveredDevice.id == discovered_id).first()
        if not discovered: 
            logger.warning("DiscoveredDevice not found", extra={"job_id": None, "device_id": None})
            return None

        host_name = discovered.hostname if discovered.hostname else None
        if host_name:
            by_name = (
                self.db.query(Device)
                .filter(or_(Device.name == host_name, Device.hostname == host_name))
                .first()
            )
            if by_name:
                discovered.status = "existing"
                discovered.matched_device_id = by_name.id
                self.db.commit()
                return by_name
        
        # Check if IP already exists to prevent duplicate key error
        existing = self.db.query(Device).filter(Device.ip_address == discovered.ip_address).first()
        if existing: 
            logger.info("Device already exists", extra={"device_id": existing.id})
            discovered.status = "existing"
            discovered.matched_device_id = existing.id
            self.db.commit()
            return existing

        # Determine Device Type (Canonical)
        # Default to 'cisco_ios' to ensure successful creation
        device_type = "cisco_ios" 
        
        # 1. Use type discovered by SNMP or Scan Logic
        driver = get_driver_for_vendor(discovered.vendor)
        if driver and driver != "unknown":
            device_type = driver
        else:
            # Fallback based on vendor string (Case-insensitive check)
            v_lower = (discovered.vendor or "").lower()
            if "cisco" in v_lower: device_type = "cisco_ios"
            elif "juniper" in v_lower: device_type = "juniper_junos"
            elif "arista" in v_lower: device_type = "arista_eos"
            elif "huawei" in v_lower: device_type = "huawei"
            elif "hp" in v_lower: device_type = "hp_procurve"
            elif "dell" in v_lower: device_type = "dell_os10"
            elif "extreme" in v_lower: device_type = "extreme_exos"
            elif "fortinet" in v_lower: device_type = "fortinet"
            # Korean Vendors 
            elif "dasan" in v_lower: device_type = "dasan_nos"
            elif "ubiquoss" in v_lower: device_type = "ubiquoss_l2"
            elif "handream" in v_lower: device_type = "handream_sg"
            elif "linux" in v_lower: device_type = "linux"
            elif "windows" in v_lower: device_type = "windows_cmd" 

            # Special case for "Unknown" but reachable (SSH/Netconf)
            # Default is already cisco_ios, so no explicit else needed, 
            # but we ensure it's set if currently unknown
        
        try:
            # Defensive check for required fields even though DB might have defaults
            hostname = discovered.hostname if discovered.hostname else f"Device-{discovered.ip_address}"
            model = discovered.model if discovered.model else "Unknown Model"
            version = discovered.os_version if discovered.os_version else "Unknown Version"

            # Create new Device
            job = self.db.query(DiscoveryJob).filter(DiscoveryJob.id == discovered.job_id).first()
            default_ssh_username = self._get_setting_value("default_ssh_username")
            default_ssh_password = self._get_setting_value("default_ssh_password")
            default_enable_password = self._get_setting_value("default_enable_password")

            new_device = Device(
                name=hostname,
                ip_address=discovered.ip_address,
                device_type=device_type,
                status="reachable", # Assume reachable since we are approving it
                model=model,
                os_version=version,
                mac_address=discovered.mac_address,
                snmp_community=(job.snmp_community if job and job.snmp_community else "public"),
                snmp_version=(getattr(job, "snmp_version", None) or "v2c"),
                snmp_port=int(getattr(job, "snmp_port", None) or 161),
                snmp_v3_username=getattr(job, "snmp_v3_username", None),
                snmp_v3_security_level=getattr(job, "snmp_v3_security_level", None),
                snmp_v3_auth_proto=getattr(job, "snmp_v3_auth_proto", None),
                snmp_v3_auth_key=getattr(job, "snmp_v3_auth_key", None),
                snmp_v3_priv_proto=getattr(job, "snmp_v3_priv_proto", None),
                snmp_v3_priv_key=getattr(job, "snmp_v3_priv_key", None),
                ssh_username=(default_ssh_username or "admin"),
                ssh_password=(default_ssh_password or None),
                enable_password=(default_enable_password or None),
            )
            self.db.add(new_device)
            self.db.flush() # Flush to get ID, but don't commit yet
            
            # Update Discovered Record
            discovered.status = "approved"
            discovered.matched_device_id = new_device.id
            
            self.db.commit()
            logger.info("Device approved successfully", extra={"device_id": new_device.id})
            return new_device

        except Exception as e:
            self.db.rollback()
            logger.exception("Failed to approve device")
            raise e

    def auto_approve_job(self, job_id: int) -> dict:
        job = self.db.query(DiscoveryJob).filter(DiscoveryJob.id == int(job_id)).first()
        if not job:
            return {"approved_count": 0, "skipped_count": 0, "device_ids": []}

        def _get_setting_value(key: str) -> str:
            setting = self.db.query(SystemSetting).filter(SystemSetting.key == key).first()
            return str(setting.value) if setting and setting.value and setting.value != "********" else ""

        enabled = (_get_setting_value("auto_approve_enabled") or "false").strip().lower() in ("true", "1", "yes", "y", "on")
        if not enabled:
            return {"approved_count": 0, "skipped_count": 0, "device_ids": []}

        try:
            min_conf = float(_get_setting_value("auto_approve_min_vendor_confidence") or 0.8)
        except Exception:
            min_conf = 0.8
        if min_conf < 0:
            min_conf = 0.0
        if min_conf > 1:
            min_conf = 1.0

        require_snmp = (_get_setting_value("auto_approve_require_snmp_reachable") or "true").strip().lower() in ("true", "1", "yes", "y", "on")
        block_sev_raw = (_get_setting_value("auto_approve_block_severities") or "error").strip()
        blocked = set([s.strip().lower() for s in block_sev_raw.replace("\n", ",").split(",") if s.strip()])
        if not blocked:
            blocked = {"error"}

        discovered_list = (
            self.db.query(DiscoveredDevice)
            .filter(DiscoveredDevice.job_id == job.id, DiscoveredDevice.status == "new")
            .order_by(DiscoveredDevice.id.asc())
            .all()
        )

        approved_ids: list[int] = []
        skipped = 0
        for d in discovered_list:
            try:
                conf = float(getattr(d, "vendor_confidence", 0.0) or 0.0)
            except Exception:
                conf = 0.0
            if conf < min_conf:
                continue
            if require_snmp and str(getattr(d, "snmp_status", "") or "").strip().lower() != "reachable":
                continue
            issues = getattr(d, "issues", None)
            if isinstance(issues, list) and blocked:
                bad = False
                for it in issues:
                    if not isinstance(it, dict):
                        continue
                    sev = str(it.get("severity") or "").strip().lower()
                    if sev and sev in blocked:
                        bad = True
                        break
                if bad:
                    continue

            device = self.approve_device(d.id)
            if device:
                approved_ids.append(int(device.id))
        skipped = len(discovered_list) - len(approved_ids)

        try:
            self._append_job_log(job, f"Auto Approve: approved={len(approved_ids)} skipped={max(0, skipped)}")
            self.db.commit()
        except Exception:
            pass

        trigger_topology = (_get_setting_value("auto_approve_trigger_topology") or "false").strip().lower() in ("true", "1", "yes", "y", "on")
        trigger_sync = (_get_setting_value("auto_approve_trigger_sync") or "false").strip().lower() in ("true", "1", "yes", "y", "on")
        trigger_monitoring = (_get_setting_value("auto_approve_trigger_monitoring") or "false").strip().lower() in ("true", "1", "yes", "y", "on")
        try:
            topo_depth = int(_get_setting_value("auto_approve_topology_depth") or 2)
        except Exception:
            topo_depth = 2
        topo_depth = max(1, min(6, topo_depth))

        if approved_ids and trigger_topology:
            try:
                from app.tasks.topology_refresh import refresh_device_topology
                for did in approved_ids:
                    try:
                        refresh_device_topology.delay(did, job.id, topo_depth)
                    except Exception:
                        continue
            except Exception:
                pass

        if approved_ids and trigger_monitoring:
            try:
                from app.tasks.monitoring import burst_monitor_devices
                burst_monitor_devices.delay(approved_ids, 3, 5)
            except Exception:
                pass

        if approved_ids and trigger_sync:
            try:
                enabled_sync = (_get_setting_value("auto_sync_enabled") or "true").strip().lower() in ("true", "1", "yes", "y", "on")
                interval = float(_get_setting_value("auto_sync_interval_seconds") or 3)
                jitter = float(_get_setting_value("auto_sync_jitter_seconds") or 0.5)
                if enabled_sync:
                    from app.tasks.device_sync import enqueue_ssh_sync_batch
                    enqueue_ssh_sync_batch.delay(approved_ids, interval, jitter)
            except Exception:
                try:
                    import threading
                    from app.services.device_sync_service import DeviceSyncService

                    def _run():
                        db2 = SessionLocal()
                        try:
                            for did in approved_ids:
                                try:
                                    DeviceSyncService.sync_device_job(did)
                                except Exception:
                                    continue
                        finally:
                            db2.close()

                    threading.Thread(target=_run, name=f"auto_approve_sync_{job.id}", daemon=True).start()
                except Exception:
                    pass

        return {"approved_count": len(approved_ids), "skipped_count": max(0, skipped), "device_ids": approved_ids}

    def _get_setting_value(self, key: str) -> str:
        setting = self.db.query(SystemSetting).filter(SystemSetting.key == key).first()
        return setting.value if setting and setting.value and setting.value != "********" else ""
