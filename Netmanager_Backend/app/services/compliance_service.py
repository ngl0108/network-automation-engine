import re
import json
from datetime import datetime
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional
from app.models.device import Device, ComplianceReport, ConfigBackup, Issue, EventLog
from app.models.compliance import ComplianceStandard, ComplianceRule
from app.services.template_service import TemplateRenderer
from app.services.ssh_service import DeviceConnection, DeviceInfo
from app.services.post_check_service import resolve_post_check_commands
from app.services.config_replace_profile_service import resolve_config_replace_profile
import uuid

class ComplianceEngine:
    def __init__(self, db: Session):
        self.db = db

    def run_rule_scan(self, device_id: int, standard_id: int = None):
        """
        Rule-based Compliance Scan (New Feature)
        """
        device = self.db.query(Device).filter(Device.id == device_id).first()
        if not device:
            return {"error": "Device not found"}

        # 최신 설정 백업 가져오기
        latest_backup = self.db.query(ConfigBackup)\
            .filter(ConfigBackup.device_id == device_id)\
            .order_by(ConfigBackup.created_at.desc(), ConfigBackup.id.desc())\
            .first()
        
        if not latest_backup or not latest_backup.raw_config:
            return {"error": "No config backup found for this device"}
        
        config_text = latest_backup.raw_config
        
        # 적용할 표준 조회
        query = self.db.query(ComplianceStandard)
        if standard_id:
            query = query.filter(ComplianceStandard.id == standard_id)
        
        standards = query.all()
        if not standards:
            return {"error": "No compliance standards found"}

        violations = []
        total_rules = 0
        passed_rules = 0
        
        report_details = {} # Standard 별 결과

        for standard in standards:
            # 장비 OS Family가 맞는지 확인 (간단한 체크)
            # if standard.device_family and standard.device_family not in device.device_type: continue
            
            std_violations = []
            std_passed = 0
            std_total = 0

            for rule in standard.rules:
                total_rules += 1
                std_total += 1
                
                is_compliant = self._check_rule(config_text, rule)
                
                if is_compliant:
                    passed_rules += 1
                    std_passed += 1
                else:
                    v_data = {
                        "standard": standard.name,
                        "rule": rule.name,
                        "severity": rule.severity,
                        "description": rule.description,
                        "remediation": rule.remediation
                    }
                    violations.append(v_data)
                    std_violations.append(v_data)

            report_details[standard.name] = {
                "total": std_total,
                "passed": std_passed,
                "score": (std_passed / std_total * 100) if std_total > 0 else 100,
                "violations": std_violations
            }

        # 결과 저장
        report = self.db.query(ComplianceReport).filter(ComplianceReport.device_id == device_id).first()
        if not report:
            report = ComplianceReport(device_id=device_id)
            self.db.add(report)
        
        status = "compliant" if not violations else "violation"
        score = (passed_rules / total_rules * 100) if total_rules > 0 else 100.0
        
        report.status = status
        report.match_percentage = score
        report.last_checked = datetime.now()
        
        # 상세 결과 저장 (JSON 직렬화해서 diff_content에 임시 저장하거나 details 컬럼 사용)
        # details 컬럼은 SQL로 추가할 예정이므로, 여기서는 속성이 런타임에 존재한다고 가정하고 에러 처리
        try:
            report.details = report_details
        except Exception:
            # Fallback: Store JSON string in diff_content if details column missing
            report.diff_content = json.dumps(report_details)

        # 이슈 생성 로직
        if status == "violation":
            self._create_compliance_issue(device, violations)
        else:
             # Resolve existing compliance issues
             self._resolve_compliance_issues(device)

        self.db.commit()
        
        return {
            "device": device.name,
            "status": status,
            "score": score,
            "violations": violations
        }

    def _check_rule(self, config: str, rule: ComplianceRule) -> bool:
        """
        규칙 검사 로직
        """
        pattern = rule.pattern
        if not pattern: return True
        
        if rule.check_type == "simple_match":
            return pattern in config
            
        elif rule.check_type == "absent_match":
            return pattern not in config
            
        elif rule.check_type == "regex_match":
            try:
                return re.search(pattern, config, re.MULTILINE) is not None
            except re.error:
                return False 
                
        return True

    def _create_compliance_issue(self, device, violations):
        # Check for existing open issue
        existing_issue = self.db.query(Issue).filter(
            Issue.device_id == device.id,
            Issue.status == 'active',
            Issue.category == 'security',
            Issue.title.like('Security Compliance Violation%')
        ).first()
        
        if not existing_issue:
            cnt = len(violations)
            new_issue = Issue(
                device_id=device.id,
                title=f"Security Compliance Violation ({cnt} items)",
                description=f"Device failed {cnt} security compliance rules. Check audit report for details.",
                severity="warning",
                status="active",
                category="security",
                created_at=datetime.now()
            )
            self.db.add(new_issue)

    def _resolve_compliance_issues(self, device):
        issues = self.db.query(Issue).filter(
            Issue.device_id == device.id,
            Issue.status == 'active',
            Issue.category == 'security',
            Issue.title.like('Security Compliance Violation%')
        ).all()
        for issue in issues:
            issue.status = 'resolved'
            issue.resolved_at = datetime.now()


    # ---------------------------------------------------------
    # Legacy: Golden Config Template Match (Keep for compatibility)
    # ---------------------------------------------------------
    def check_golden_config(self, device_id: int, template_content: str, policy=None):
        # 1. 장비 정보 조회
        device = self.db.query(Device).filter(Device.id == device_id).first()
        if not device:
            return {"status": "error", "message": "Device not found"}

        # 2. Running Config (최근 백업) 확인
        latest_backup = None
        if device.config_backups:
            backups = sorted(device.config_backups, key=lambda x: x.created_at, reverse=True)
            latest_backup = backups[0].raw_config

        if not latest_backup:
            return {"status": "error", "message": "No running config found. Please Sync first."}

        # 3. 변수 병합 및 렌더링
        global_vars = {"company": "NetManager"}
        site_vars = device.site_obj.variables if device.site_obj else {}
        device_vars = device.variables or {}
        device_vars.update({
            "hostname": device.name,
            "management_ip": device.ip_address,
            "model": device.model
        })

        context = TemplateRenderer.merge_variables(global_vars, site_vars, device_vars)
        golden_config = TemplateRenderer.render(template_content, context)

        # 4. Compare
        def is_code(line):
            l = line.strip()
            return l and not l.startswith('!') and not l.startswith('#')

        running_lines = set(line.strip() for line in latest_backup.strip().splitlines() if is_code(line))
        golden_lines = set(line.strip() for line in golden_config.strip().splitlines() if is_code(line))

        missing_lines = golden_lines - running_lines
        
        status = "compliant" if not missing_lines else "violation"
        score = 100.0
        if len(golden_lines) > 0:
            score = ((len(golden_lines) - len(missing_lines)) / len(golden_lines)) * 100

        # ... (Legacy report saving logic simplified) ...
        # This function is kept but we prioritize run_rule_scan for the new page

        return {
            "status": status,
            "match_percentage": round(score, 2),
            "violations": {
                "missing_lines": sorted(list(missing_lines))
            }
        }

    # ---------------------------------------------------------
    # Config Drift Detection (Gluware-like Feature)
    # ---------------------------------------------------------
    def set_golden_config(self, backup_id: int):
        # 1. 대상 백업 조회
        target_backup = self.db.query(ConfigBackup).filter(ConfigBackup.id == backup_id).first()
        if not target_backup:
            return {"error": "Backup not found"}
        
        # 2. 해당 장비의 기존 Golden 해제 (장비당 1개만 Golden 유지)
        self.db.query(ConfigBackup).filter(
            ConfigBackup.device_id == target_backup.device_id,
            ConfigBackup.is_golden == True
        ).update({"is_golden": False})
        
        # 3. 새로운 Golden 지정
        target_backup.is_golden = True
        self.db.commit()
        return {"message": f"Backup #{backup_id} is now the Golden Config"}

    def check_config_drift(self, device_id: int):
        import difflib

        # 1. Golden Config 조회
        golden = self.db.query(ConfigBackup).filter(
            ConfigBackup.device_id == device_id,
            ConfigBackup.is_golden == True
        ).first()

        if not golden:
            return {"status": "no_golden", "message": "No Golden Config defined for this device"}

        # 2. 최신 Running Config (백업) 조회
        latest = self.db.query(ConfigBackup).filter(
            ConfigBackup.device_id == device_id
        ).order_by(ConfigBackup.created_at.desc(), ConfigBackup.id.desc()).first()

        if not latest:
            return {"status": "error", "message": "No config backup available"}

        # 3. 비교 (Diff)
        golden_lines = (golden.raw_config or "").splitlines()
        latest_lines = (latest.raw_config or "").splitlines()
        
        diff = list(difflib.unified_diff(
            golden_lines, latest_lines, 
            fromfile=f'Golden (ID:{golden.id})', 
            tofile=f'Running (ID:{latest.id})',
            lineterm=''
        ))

        # 4. 결과 분석
        drift_detected = len(diff) > 0
        
        return {
            "device_id": device_id,
            "status": "drift" if drift_detected else "compliant",
            "golden_id": golden.id,
            "latest_id": latest.id,
            "diff_lines": diff,
            "message": "Configuration drift detected" if drift_detected else "Configuration matches Golden Config"
        }

    def _looks_like_cli_error(self, output: str) -> bool:
        t = (output or "").lower()
        return any(
            s in t
            for s in (
                "% invalid",
                "invalid input",
                "unknown command",
                "unrecognized command",
                "ambiguous command",
                "incomplete command",
                "error:",
                "syntax error",
            )
        )

    def _default_post_check_commands(self, device_type: str) -> List[str]:
        dt = str(device_type or "").lower()
        if "juniper" in dt or "junos" in dt:
            return ["show system uptime", "show system alarms", "show chassis alarms"]
        if "huawei" in dt:
            return ["display clock", "display version"]
        return ["show clock", "show version"]

    def _run_post_check(self, conn: DeviceConnection, device: Device, commands: List[str]) -> Dict[str, Any]:
        tried = []
        for cmd in commands:
            try:
                out = conn.send_command(cmd, read_timeout=20)
            except Exception as e:
                tried.append({"command": cmd, "ok": False, "error": f"{type(e).__name__}: {e}"})
                continue
            ok = bool(out) and not self._looks_like_cli_error(out)
            if ok:
                return {"ok": True, "command": cmd, "output": out, "tried": tried}
            tried.append({"command": cmd, "ok": False, "output": out})
        return {"ok": False, "command": None, "output": None, "tried": tried}

    def _config_to_commands(self, raw_config: str) -> List[str]:
        lines = []
        for line in (raw_config or "").splitlines():
            s = str(line or "").strip()
            if not s:
                continue
            if s.startswith("!") or s.startswith("#"):
                continue
            if s.lower().startswith("building configuration"):
                continue
            if s.lower().startswith("current configuration"):
                continue
            lines.append(s)
        return lines

    def remediate_config_drift(
        self,
        device_id: int,
        *,
        save_pre_backup: bool = True,
        prepare_device_snapshot: bool = True,
        rollback_on_failure: bool = True,
        post_check_enabled: bool = True,
        post_check_commands: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        device = self.db.query(Device).filter(Device.id == device_id).first()
        if not device:
            return {"status": "error", "message": "Device not found"}

        golden = self.db.query(ConfigBackup).filter(ConfigBackup.device_id == device_id, ConfigBackup.is_golden == True).first()
        if not golden or not golden.raw_config:
            return {"status": "no_golden", "message": "No Golden Config defined for this device"}

        if not device.ssh_password:
            return {"status": "error", "message": "SSH password not set for device"}

        info = DeviceInfo(
            host=device.ip_address,
            username=device.ssh_username or "admin",
            password=device.ssh_password,
            secret=device.enable_password,
            port=int(device.ssh_port or 22),
            device_type=device.device_type or "cisco_ios",
        )

        conn = DeviceConnection(info)
        if not conn.connect():
            return {"status": "failed", "message": f"Connection failed: {conn.last_error}"}

        pre_backup_id = None
        pre_backup_error = None
        rollback_prepared = False
        rollback_ref = None
        post_check = None

        try:
            if save_pre_backup:
                try:
                    running_before = conn.get_running_config()
                    b = ConfigBackup(device_id=device_id, raw_config=running_before, is_golden=False)
                    self.db.add(b)
                    self.db.commit()
                    self.db.refresh(b)
                    pre_backup_id = int(b.id)
                except Exception as e:
                    self.db.rollback()
                    pre_backup_error = f"{type(e).__name__}: {e}"

            if prepare_device_snapshot:
                snap_name = f"rollback_{device_id}_{uuid.uuid4().hex[:10]}"
                try:
                    rollback_prepared = bool(conn.driver.prepare_rollback(snap_name)) if conn.driver else False
                    rollback_ref = getattr(conn.driver, "_rollback_ref", None) or snap_name
                except Exception:
                    rollback_prepared = False
                    rollback_ref = None

            push_output: Any
            replace_result = None
            if getattr(conn, "driver", None) and hasattr(conn.driver, "apply_config_replace"):
                try:
                    profile = resolve_config_replace_profile(self.db, device)
                    if profile and isinstance(profile, dict):
                        try:
                            setattr(conn.driver, "_config_replace_profile", profile)
                        except Exception:
                            pass
                    replace_result = conn.driver.apply_config_replace(golden.raw_config or "")
                except Exception as e:
                    replace_result = {"success": False, "error": f"{type(e).__name__}: {e}"}

            if isinstance(replace_result, dict) and replace_result.get("success") is True:
                push_output = replace_result.get("output")
                if push_output is None or push_output == "":
                    parts: List[str] = []
                    ref = replace_result.get("ref")
                    if ref:
                        parts.append(f"ref: {ref}")
                    replace_command = replace_result.get("replace_command")
                    if replace_command:
                        parts.append(f"replace_command: {replace_command}")
                    copy_output = replace_result.get("copy_output")
                    if copy_output:
                        parts.append("copy_output:\n" + str(copy_output))
                    replace_output = replace_result.get("replace_output")
                    if replace_output:
                        parts.append("replace_output:\n" + str(replace_output))
                    if parts:
                        push_output = "\n\n".join(parts)
                    else:
                        push_output = json.dumps(replace_result, ensure_ascii=False, default=str)
            else:
                cmds = self._config_to_commands(golden.raw_config)
                if not cmds:
                    return {"status": "error", "message": "Golden config is empty after normalization"}
                push_output = conn.send_config_set(cmds)

            if post_check_enabled:
                commands = list(post_check_commands or [])
                if not commands:
                    commands = resolve_post_check_commands(self.db, device) or []
                if not commands:
                    commands = self._default_post_check_commands(info.device_type)
                post_check = self._run_post_check(conn, device, commands)
                if not post_check.get("ok"):
                    raise Exception("Post-check failed")

            try:
                running_after = conn.get_running_config()
                b2 = ConfigBackup(device_id=device_id, raw_config=running_after, is_golden=False)
                self.db.add(b2)
                self.db.commit()
            except Exception:
                self.db.rollback()

            drift = self.check_config_drift(device_id)

            issue_title = "Config Drift Detected"
            existing = self.db.query(Issue).filter(Issue.device_id == device_id, Issue.status == "active", Issue.category == "config", Issue.title == issue_title).first()
            if drift.get("status") == "compliant" and existing:
                existing.status = "resolved"
                existing.resolved_at = datetime.now()
                self.db.commit()

            self.db.add(
                EventLog(
                    device_id=device_id,
                    severity="info",
                    event_id="CONFIG_DRIFT_REMEDIATION",
                    message=f"Remediation executed (golden_id={golden.id})",
                    source="Compliance",
                    timestamp=datetime.now(),
                )
            )
            self.db.commit()

            return {
                "status": "ok",
                "device_id": device_id,
                "golden_id": golden.id,
                "pre_backup_id": pre_backup_id,
                "pre_backup_error": pre_backup_error,
                "rollback_prepared": rollback_prepared,
                "rollback_ref": rollback_ref,
                "push_output": push_output,
                "replace_result": replace_result,
                "post_check": post_check,
                "drift_after": drift,
            }
        except Exception as e:
            rollback_attempted = False
            rollback_success = False
            rollback_error = None
            if rollback_on_failure:
                rollback_attempted = True
                try:
                    rollback_success = bool(conn.driver.rollback()) if conn.driver else False
                except Exception as re:
                    rollback_error = f"{type(re).__name__}: {re}"
                    rollback_success = False

            self.db.add(
                EventLog(
                    device_id=device_id,
                    severity="warning",
                    event_id="CONFIG_DRIFT_REMEDIATION_FAILED",
                    message=str(e),
                    source="Compliance",
                    timestamp=datetime.now(),
                )
            )
            self.db.commit()

            return {
                "status": "failed",
                "device_id": device_id,
                "error": str(e),
                "pre_backup_id": pre_backup_id,
                "pre_backup_error": pre_backup_error,
                "rollback_attempted": rollback_attempted,
                "rollback_success": rollback_success,
                "rollback_error": rollback_error,
                "rollback_prepared": rollback_prepared,
                "rollback_ref": rollback_ref,
                "post_check": post_check,
            }
        finally:
            try:
                conn.disconnect()
            except Exception:
                pass
