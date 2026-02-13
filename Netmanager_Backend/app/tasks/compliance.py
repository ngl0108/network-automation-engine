try:
    from celery import shared_task
except ModuleNotFoundError:
    def shared_task(*args, **kwargs):
        def decorator(fn):
            return fn
        if args and callable(args[0]) and not kwargs:
            return args[0]
        return decorator

from app.db.session import SessionLocal
from app.services.compliance_service import ComplianceEngine


@shared_task(bind=True, name="app.tasks.compliance.run_compliance_scan_task")
def run_compliance_scan_task(self, device_ids: list[int], standard_id: int | None = None):
    db = SessionLocal()
    try:
        engine = ComplianceEngine(db)
        results = []
        total = len(device_ids or [])
        for idx, dev_id in enumerate(device_ids or []):
            try:
                res = engine.run_rule_scan(dev_id, standard_id)
                results.append(res)
            except Exception as e:
                results.append({"device_id": dev_id, "error": str(e)})
            try:
                if hasattr(self, "update_state"):
                    self.update_state(state="PROGRESS", meta={"done": idx + 1, "total": total})
            except Exception:
                pass
        return {"results": results}
    finally:
        db.close()


@shared_task(name="app.tasks.compliance.run_scheduled_compliance_scan")
def run_scheduled_compliance_scan():
    db = SessionLocal()
    try:
        from app.models.device import Device
        from app.models.settings import SystemSetting

        enabled = db.query(SystemSetting).filter(SystemSetting.key == "compliance_scan_enabled").first()
        if enabled and str(enabled.value or "").strip().lower() in {"0", "false", "no"}:
            return {"status": "skipped", "reason": "disabled"}

        std_setting = db.query(SystemSetting).filter(SystemSetting.key == "compliance_scan_standard_id").first()
        standard_id = None
        if std_setting and str(std_setting.value or "").strip():
            try:
                standard_id = int(str(std_setting.value).strip())
            except Exception:
                standard_id = None

        device_ids = [d_id for (d_id,) in db.query(Device.id).all()]
        engine = ComplianceEngine(db)
        results = []
        for dev_id in device_ids:
            try:
                results.append(engine.run_rule_scan(dev_id, standard_id))
            except Exception as e:
                results.append({"device_id": dev_id, "error": str(e)})
        return {"status": "ok", "standard_id": standard_id, "count": len(results), "results": results}
    finally:
        db.close()


@shared_task(name="app.tasks.compliance.run_scheduled_config_drift_checks")
def run_scheduled_config_drift_checks():
    db = SessionLocal()
    try:
        from datetime import datetime

        from app.models.device import Device, Issue, EventLog, ConfigBackup
        from app.models.settings import SystemSetting
        from app.models.approval import ApprovalRequest
        from app.models.user import User
        from app.core import security
        import secrets

        enabled = db.query(SystemSetting).filter(SystemSetting.key == "config_drift_enabled").first()
        if enabled and str(enabled.value or "").strip().lower() in {"0", "false", "no"}:
            return {"status": "skipped", "reason": "disabled"}

        engine = ComplianceEngine(db)
        device_ids = [d_id for (d_id,) in db.query(ConfigBackup.device_id).filter(ConfigBackup.is_golden == True).distinct().all()]
        summary = {"checked": 0, "drift": 0, "compliant": 0, "no_golden": 0, "errors": 0}

        approval_enabled = db.query(SystemSetting).filter(SystemSetting.key == "config_drift_approval_enabled").first()
        approval_is_on = bool(approval_enabled) and str(approval_enabled.value or "").strip().lower() in {"1", "true", "yes", "on"}
        system_user = None
        if approval_is_on:
            system_user = db.query(User).filter(User.username == "system").first()
            if not system_user:
                hashed_pw = security.get_password_hash(secrets.token_urlsafe(32))
                system_user = User(username="system", hashed_password=hashed_pw, full_name="System Automation", role="admin", is_active=True)
                db.add(system_user)
                db.commit()
                db.refresh(system_user)

        for dev_id in device_ids:
            summary["checked"] += 1
            device = db.query(Device).filter(Device.id == dev_id).first()
            if not device:
                continue

            try:
                res = engine.check_config_drift(dev_id)
            except Exception as e:
                summary["errors"] += 1
                db.add(
                    EventLog(
                        device_id=dev_id,
                        severity="warning",
                        event_id="CONFIG_DRIFT_CHECK_ERROR",
                        message=str(e),
                        source="Automation",
                        timestamp=datetime.now(),
                    )
                )
                db.commit()
                continue

            status = str(res.get("status") or "")
            if status == "no_golden":
                summary["no_golden"] += 1
                continue

            issue_title = "Config Drift Detected"
            existing = (
                db.query(Issue)
                .filter(Issue.device_id == dev_id, Issue.status == "active", Issue.category == "config", Issue.title == issue_title)
                .first()
            )

            if status == "drift":
                summary["drift"] += 1
                msg = f"Golden#{res.get('golden_id')} vs Running#{res.get('latest_id')} drift detected"
                db.add(
                    EventLog(
                        device_id=dev_id,
                        severity="warning",
                        event_id="CONFIG_DRIFT",
                        message=msg,
                        source="Automation",
                        timestamp=datetime.now(),
                    )
                )
                if not existing:
                    db.add(
                        Issue(
                            device_id=dev_id,
                            title=issue_title,
                            description=msg,
                            severity="warning",
                            status="active",
                            category="config",
                            created_at=datetime.now(),
                        )
                    )
                else:
                    existing.description = msg

                if approval_is_on and system_user:
                    already = False
                    existing_pending = (
                        db.query(ApprovalRequest)
                        .filter(ApprovalRequest.request_type == "config_drift_remediate", ApprovalRequest.status == "pending")
                        .order_by(ApprovalRequest.created_at.desc())
                        .limit(200)
                        .all()
                    )
                    for r in existing_pending:
                        try:
                            if int((r.payload or {}).get("device_id") or 0) == int(dev_id):
                                already = True
                                break
                        except Exception:
                            continue
                    if not already:
                        db.add(
                            ApprovalRequest(
                                requester_id=system_user.id,
                                title=f"[Drift] Force Sync Proposal - {device.name}",
                                description=msg,
                                request_type="config_drift_remediate",
                                payload={
                                    "device_id": dev_id,
                                    "golden_id": res.get("golden_id"),
                                    "latest_id": res.get("latest_id"),
                                    "save_pre_backup": True,
                                    "prepare_device_snapshot": True,
                                    "rollback_on_failure": True,
                                    "post_check_enabled": True,
                                    "post_check_commands": [],
                                    "execution_status": "proposed",
                                },
                                status="pending",
                            )
                        )
                db.commit()
            else:
                summary["compliant"] += 1
                if existing:
                    existing.status = "resolved"
                    existing.resolved_at = datetime.now()
                    db.commit()

        return {"status": "ok", **summary}
    finally:
        db.close()


@shared_task(name="app.tasks.compliance.run_config_drift_remediation_for_approval")
def run_config_drift_remediation_for_approval(approval_request_id: int):
    db = SessionLocal()
    try:
        from datetime import datetime
        from app.models.approval import ApprovalRequest
        from app.models.device import EventLog

        req = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_request_id).first()
        if not req:
            return {"status": "error", "message": "Approval request not found"}

        if req.request_type != "config_drift_remediate":
            return {"status": "skipped", "message": "Unsupported request_type"}

        if req.status != "approved":
            return {"status": "skipped", "message": f"Request status is {req.status}"}

        payload = req.payload or {}
        device_id = payload.get("device_id")
        if not device_id:
            return {"status": "error", "message": "device_id missing in payload"}

        engine = ComplianceEngine(db)
        result = engine.remediate_config_drift(
            int(device_id),
            save_pre_backup=bool(payload.get("save_pre_backup", True)),
            prepare_device_snapshot=bool(payload.get("prepare_device_snapshot", True)),
            rollback_on_failure=bool(payload.get("rollback_on_failure", True)),
            post_check_enabled=bool(payload.get("post_check_enabled", True)),
            post_check_commands=list(payload.get("post_check_commands") or []),
        )

        payload["execution_status"] = "success" if result.get("status") == "ok" else "failed"
        payload["execution_result"] = result
        payload["executed_at"] = datetime.now().isoformat()
        req.payload = payload

        db.add(
            EventLog(
                device_id=int(device_id),
                severity="info" if result.get("status") == "ok" else "warning",
                event_id="CONFIG_DRIFT_REMEDIATION_APPROVAL_EXECUTED",
                message=f"Approval#{approval_request_id} executed remediation status={result.get('status')}",
                source="Approval",
                timestamp=datetime.now(),
            )
        )
        db.commit()
        return {"status": "ok", "approval_request_id": approval_request_id, "result": result}
    finally:
        db.close()
