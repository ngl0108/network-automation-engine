import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.device import Device, Link


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


def test_topology_refresh_infers_link_from_fdb_and_arp(db, monkeypatch):
    a = Device(name="a", ip_address="10.0.0.1", device_type="cisco_ios", status="online", owner_id=1, snmp_community="public")
    b = Device(name="b", ip_address="10.0.0.2", device_type="cisco_ios", status="online", owner_id=1, snmp_community="public")
    db.add_all([a, b])
    db.commit()
    db.refresh(a)
    db.refresh(b)

    import app.tasks.topology_refresh as mod

    class FakeSnmp:
        def __init__(self, *args, **kwargs):
            pass
        def get_interface_name_status_map(self):
            return {}

    monkeypatch.setattr(mod, "SnmpManager", FakeSnmp)
    monkeypatch.setattr(mod.SnmpL2Service, "get_lldp_neighbors", lambda *args, **kwargs: [])
    monkeypatch.setattr(mod.SnmpL2Service, "get_qbridge_mac_table", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        mod.SnmpL2Service,
        "get_arp_table",
        lambda *args, **kwargs: [{"ip": b.ip_address, "mac": "aaaa.bbbb.cccc", "interface": "Vlan1"}],
    )
    monkeypatch.setattr(
        mod.SnmpL2Service,
        "get_bridge_mac_table",
        lambda *args, **kwargs: [{"mac": "aaaa.bbbb.cccc", "port": "Gi0/1", "discovery_source": "snmp_bridge"}],
    )

    monkeypatch.setattr(mod, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    res = mod.refresh_device_topology(a.id, discovery_job_id=None, max_depth=1)
    assert res["status"] == "ok"

    links = db.query(Link).all()
    assert len(links) == 1
    assert links[0].source_device_id in (a.id, b.id)
    assert links[0].target_device_id in (a.id, b.id)


def test_topology_refresh_infers_link_from_fdb_and_mac_match(db, monkeypatch):
    a = Device(name="a", ip_address="10.0.0.1", device_type="cisco_ios", status="online", owner_id=1, snmp_community="public")
    b = Device(
        name="b",
        ip_address="10.0.0.2",
        device_type="cisco_ios",
        status="online",
        owner_id=1,
        snmp_community="public",
        latest_parsed_data={"mac_aliases": ["aaaa.bbbb.cccc"]},
    )
    db.add_all([a, b])
    db.commit()
    db.refresh(a)
    db.refresh(b)

    import app.tasks.topology_refresh as mod

    class FakeSnmp:
        def __init__(self, *args, **kwargs):
            pass
        def get_interface_name_status_map(self):
            return {}

    monkeypatch.setattr(mod, "SnmpManager", FakeSnmp)
    monkeypatch.setattr(mod.SnmpL2Service, "get_lldp_neighbors", lambda *args, **kwargs: [])
    monkeypatch.setattr(mod.SnmpL2Service, "get_qbridge_mac_table", lambda *args, **kwargs: [])
    monkeypatch.setattr(mod.SnmpL2Service, "get_arp_table", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        mod.SnmpL2Service,
        "get_bridge_mac_table",
        lambda *args, **kwargs: [{"mac": "aaaa.bbbb.cccc", "port": "Gi0/1", "discovery_source": "snmp_bridge"}],
    )

    monkeypatch.setattr(mod, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    res = mod.refresh_device_topology(a.id, discovery_job_id=None, max_depth=1)
    assert res["status"] == "ok"
    links = db.query(Link).all()
    assert len(links) == 1
