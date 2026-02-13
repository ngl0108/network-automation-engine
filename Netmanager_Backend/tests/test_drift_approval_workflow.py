from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.device import Device, ConfigBackup
from app.models.settings import SystemSetting
from app.models.approval import ApprovalRequest


@pytest.fixture()
def db_engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return engine


def test_scheduled_drift_creates_approval_request(monkeypatch, db_engine):
    from app.tasks import compliance as tc

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    monkeypatch.setattr(tc, "SessionLocal", SessionLocal)

    def fake_check(self, device_id: int):
        return {"device_id": device_id, "status": "drift", "golden_id": 10, "latest_id": 11}

    monkeypatch.setattr(tc.ComplianceEngine, "check_config_drift", fake_check)

    db = SessionLocal()
    dev = Device(name="sw1", ip_address="10.0.0.1")
    db.add(dev)
    db.commit()
    db.refresh(dev)
    dev_id = int(dev.id)
    db.add(SystemSetting(key="config_drift_approval_enabled", value="true", description="", category="General"))
    db.add(ConfigBackup(device_id=dev.id, raw_config="golden", is_golden=True))
    db.commit()
    db.close()

    tc.run_scheduled_config_drift_checks()
    tc.run_scheduled_config_drift_checks()

    db = SessionLocal()
    reqs = db.query(ApprovalRequest).filter(ApprovalRequest.request_type == "config_drift_remediate").all()
    assert len(reqs) == 1
    assert int((reqs[0].payload or {}).get("device_id")) == int(dev_id)
    db.close()


def test_approve_dispatches_remediation_task(monkeypatch, db_engine):
    from app.api.v1.endpoints import approval as approval_endpoint

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    db = SessionLocal()

    dev = Device(name="sw1", ip_address="10.0.0.1")
    db.add(dev)
    db.commit()
    db.refresh(dev)

    from app.models.user import User

    requester = User(username="req", hashed_password="x", full_name="r", role="operator", is_active=True)
    approver = User(username="admin", hashed_password="y", full_name="a", role="admin", is_active=True)
    db.add(requester)
    db.add(approver)
    db.commit()
    db.refresh(requester)
    db.refresh(approver)

    req = ApprovalRequest(
        requester_id=requester.id,
        title="t",
        request_type="config_drift_remediate",
        payload={"device_id": dev.id},
        status="pending",
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    from app.services import compliance_service as cs

    monkeypatch.setattr(cs.ComplianceEngine, "remediate_config_drift", lambda *a, **k: {"status": "ok"})

    decision = approval_endpoint.ApprovalDecision(approver_comment="ok")
    out = approval_endpoint.approve_request(
        id=req.id,
        decision=decision,
        db=db,
        current_user=SimpleNamespace(id=approver.id, role="admin"),
    )

    assert out.status == "approved"
    assert out.payload.get("execution_status") in {"queued", "executed"}
    db.close()
