import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.device import Device, Link, Site
from app.api.v1.endpoints.devices import get_topology_links


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


def test_topology_links_endpoint_includes_link_rows(db):
    site = Site(name="s1", type="area")
    db.add(site)
    db.commit()
    db.refresh(site)

    a = Device(name="a", ip_address="10.0.0.1", device_type="cisco_ios", status="online", owner_id=1, site_id=site.id, model="C2960")
    b = Device(name="b", ip_address="10.0.0.2", device_type="cisco_ios", status="online", owner_id=1, site_id=site.id)
    db.add_all([a, b])
    db.commit()
    db.refresh(a)
    db.refresh(b)

    l = Link(
        source_device_id=a.id,
        source_interface_name="Gi0/1",
        target_device_id=b.id,
        target_interface_name="Gi0/2",
        status="active",
        protocol="LLDP",
        link_speed="1G",
        discovery_source="test",
    )
    db.add(l)
    db.commit()

    payload = get_topology_links(db=db, current_user=object())
    assert isinstance(payload, dict)
    nodes = payload.get("nodes") or []
    node_a = next((n for n in nodes if n.get("id") == str(a.id)), None)
    assert node_a
    assert node_a.get("model") == "C2960"
    links = payload.get("links") or []
    assert any(x.get("source") == str(a.id) and x.get("target") == str(b.id) for x in links)
