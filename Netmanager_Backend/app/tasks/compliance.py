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

        enabled = db.query(SystemSetting).filter(SystemSetting.key == "config_drift_enabled").first()
        if enabled and str(enabled.value or "").strip().lower() in {"0", "false", "no"}:
            return {"status": "skipped", "reason": "disabled"}

        engine = ComplianceEngine(db)
        device_ids = [d_id for (d_id,) in db.query(ConfigBackup.device_id).filter(ConfigBackup.is_golden == True).distinct().all()]
        summary = {"checked": 0, "drift": 0, "compliant": 0, "no_golden": 0, "errors": 0}

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
