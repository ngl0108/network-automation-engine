import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.device import Device
from app.models.discovery import DiscoveryJob, DiscoveredDevice
from app.services.discovery_service import DiscoveryService


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


def test_approve_device_marks_existing_when_ip_already_registered(db):
    existing = Device(name="sw1", ip_address="10.0.0.10", device_type="cisco_ios", status="online", owner_id=1)
    db.add(existing)
    job = DiscoveryJob(cidr="10.0.0.0/24", snmp_community="public", status="completed", logs="")
    db.add(job)
    db.commit()
    db.refresh(existing)
    db.refresh(job)

    disc = DiscoveredDevice(job_id=job.id, ip_address="10.0.0.10", hostname="sw1", vendor="Cisco", status="new", snmp_status="reachable")
    db.add(disc)
    db.commit()
    db.refresh(disc)

    svc = DiscoveryService(db)
    device = svc.approve_device(disc.id)
    db.refresh(disc)

    assert device.id == existing.id
    assert disc.status == "existing"
    assert disc.matched_device_id == existing.id


def test_approve_device_marks_existing_when_hostname_already_registered(db):
    existing = Device(name="core-sw", ip_address="10.0.0.11", device_type="cisco_ios", status="online", owner_id=1)
    db.add(existing)
    job = DiscoveryJob(cidr="10.0.0.0/24", snmp_community="public", status="completed", logs="")
    db.add(job)
    db.commit()
    db.refresh(existing)
    db.refresh(job)

    disc = DiscoveredDevice(job_id=job.id, ip_address="10.0.0.12", hostname="core-sw", vendor="Cisco", status="new", snmp_status="reachable")
    db.add(disc)
    db.commit()
    db.refresh(disc)

    svc = DiscoveryService(db)
    device = svc.approve_device(disc.id)
    db.refresh(disc)

    assert device.id == existing.id
    assert disc.status == "existing"
    assert disc.matched_device_id == existing.id
