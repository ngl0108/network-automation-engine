import pytest
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.device import Device, Link
from app.services.diagnosis_service import OneClickDiagnosisOptions, OneClickDiagnosisService


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_one_click_diagnosis_marks_link_down_abnormal(db, monkeypatch):
    d1 = Device(name="sw1", ip_address="10.0.0.1")
    d2 = Device(name="sw2", ip_address="10.0.0.2")
    db.add_all([d1, d2])
    db.commit()
    db.refresh(d1)
    db.refresh(d2)

    db.add(
        Link(
            source_device_id=d1.id,
            target_device_id=d2.id,
            source_interface_name="Gi1/0/1",
            target_interface_name="Gi1/0/1",
            status="down",
            protocol="LLDP",
        )
    )
    db.commit()

    fake_trace = {
        "status": "success",
        "mode": "bfs",
        "path": [
            {"id": d1.id, "ingress_intf": "Client", "egress_intf": "Gi1/0/1"},
            {"id": d2.id, "ingress_intf": "Gi1/0/1", "egress_intf": "Host"},
        ],
        "path_node_ids": [d1.id, d2.id],
        "segments": [
            {
                "hop": 0,
                "from_id": d1.id,
                "to_id": d2.id,
                "from_port": "Gi1/0/1",
                "to_port": "Gi1/0/1",
                "link": {
                    "id": 1,
                    "status": "down",
                    "source_device_id": d1.id,
                    "target_device_id": d2.id,
                    "source_interface_name": "Gi1/0/1",
                    "target_interface_name": "Gi1/0/1",
                },
            }
        ],
    }

    from app.services import path_trace_service as pts

    monkeypatch.setattr(pts.PathTraceService, "trace_path", lambda self, src_ip, dst_ip: fake_trace)
    monkeypatch.setattr("app.services.diagnosis_service._ping_once", lambda ip, timeout_ms=1000: True)

    res = OneClickDiagnosisService(db).run(
        "192.0.2.1",
        "198.51.100.2",
        options=OneClickDiagnosisOptions(include_show_commands=False),
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert res["ok"] is True
    assert res["summary"]["abnormal_count"] >= 1
    assert any(a.get("type") == "link" for a in res.get("abnormal") or [])
