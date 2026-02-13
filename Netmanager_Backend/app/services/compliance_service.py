import re
import json
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.device import Device, ComplianceReport, ConfigBackup, Issue
from app.models.compliance import ComplianceStandard, ComplianceRule
from app.services.template_service import TemplateRenderer

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
