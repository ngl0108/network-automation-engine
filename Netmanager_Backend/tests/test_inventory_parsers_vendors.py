import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.device import Device
from app.models.device_inventory import DeviceInventoryItem
from app.services.inventory_ssh_service import InventorySshService


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


class FakeConn:
    def __init__(self, outputs):
        self.outputs = outputs

    def send_command(self, cmd, **kwargs):
        if kwargs.get("use_textfsm"):
            return self.outputs.get(f"{cmd}|textfsm")
        return self.outputs.get(cmd, "")


def test_arista_parser_falls_back_to_show_version(db):
    d = Device(name="A1", ip_address="10.0.0.3", snmp_community="public", device_type="arista_eos", status="online")
    db.add(d)
    db.commit()
    db.refresh(d)

    outputs = {
        "show inventory|textfsm": None,
        "show inventory all|textfsm": None,
        "show version detail": "Model name: DCS-7050SX3-48YC8\nSerial number: JPE12345678\n",
        "show version": "Model name: DCS-7050SX3-48YC8\nSerial number: JPE12345678\n",
    }
    count = InventorySshService.refresh_device_inventory_from_ssh(db, d, FakeConn(outputs))
    db.commit()
    assert count == 1
    items = db.query(DeviceInventoryItem).filter(DeviceInventoryItem.device_id == d.id).all()
    assert items[0].model_name == "DCS-7050SX3-48YC8"
    assert items[0].serial_number == "JPE12345678"


def test_hpe_aruba_parser_parses_show_system_information(db):
    d = Device(name="H1", ip_address="10.0.0.4", snmp_community="public", device_type="aruba_os", status="online")
    db.add(d)
    db.commit()
    db.refresh(d)

    outputs = {
        "show system information": "Product Name : Aruba 8325-48Y8C\nSerial Number : CN12345678\nSystem Description : ArubaOS-CX\n",
    }
    count = InventorySshService.refresh_device_inventory_from_ssh(db, d, FakeConn(outputs))
    db.commit()
    assert count == 1
    items = db.query(DeviceInventoryItem).filter(DeviceInventoryItem.device_id == d.id).all()
    assert items[0].serial_number == "CN12345678"


def test_huawei_parser_parses_display_esn_and_version(db):
    d = Device(name="HW1", ip_address="10.0.0.5", snmp_community="public", device_type="huawei", status="online")
    db.add(d)
    db.commit()
    db.refresh(d)

    outputs = {
        "display esn": "ESN: 210235A1B2C3D4E5\n",
        "display device": "Slot 1:\nBoard Type: LPU\nBarCode: 123456\nDescription: Line Processing Unit\n",
        "display version": "Huawei CE6865-48S8CQ-EI Versatile Routing Platform Software\n",
    }
    count = InventorySshService.refresh_device_inventory_from_ssh(db, d, FakeConn(outputs))
    db.commit()
    assert count >= 1
    items = db.query(DeviceInventoryItem).filter(DeviceInventoryItem.device_id == d.id).all()
    assert any(x.serial_number == "210235A1B2C3D4E5" for x in items)
