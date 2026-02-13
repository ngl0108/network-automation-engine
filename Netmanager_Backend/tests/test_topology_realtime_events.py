import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.device import Device
from app.services.topology_link_service import TopologyLinkService


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


def test_refresh_links_emits_link_update_events(db, monkeypatch):
    published = []

    def fake_publish(event, data):
        published.append((event, data))

    from app.services import realtime_event_bus as reb

    monkeypatch.setattr(reb.realtime_event_bus, "publish", fake_publish)

    a = Device(name="a", ip_address="10.0.0.1", device_type="cisco_ios", status="online", owner_id=1)
    b = Device(name="b", ip_address="10.0.0.2", device_type="cisco_ios", status="online", owner_id=1)
    db.add_all([a, b])
    db.commit()
    db.refresh(a)
    db.refresh(b)

    neighbors = [
        {
            "local_interface": "Gi0/1",
            "remote_interface": "Gi0/2",
            "neighbor_name": "b",
            "mgmt_ip": "10.0.0.2",
            "protocol": "LLDP",
        }
    ]
    TopologyLinkService.refresh_links_for_device(db, a, neighbors)
    db.commit()

    assert any(evt == "link_update" and d.get("state") == "active" for evt, d in published)
    assert any(d.get("neighbor_device_id") == b.id for _, d in published)

    published.clear()
    TopologyLinkService.refresh_links_for_device(db, a, [])
    db.commit()

    assert any(evt == "link_update" and d.get("state") == "down" for evt, d in published)

