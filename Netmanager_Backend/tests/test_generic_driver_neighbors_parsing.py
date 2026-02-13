from app.drivers.generic_driver import GenericDriver


class FakeConn:
    def __init__(self, mapping):
        self.mapping = mapping

    def send_command(self, cmd, **kwargs):
        key = f"{cmd}|textfsm" if kwargs.get("use_textfsm") else cmd
        v = self.mapping.get(key)
        if isinstance(v, Exception):
            raise v
        return v


def test_generic_driver_parses_lldp_raw_neighbors():
    raw = """
Local Intf: Gi1/0/1
Chassis id: 0011.2233.4455
Port id: Gi0/1
System Name: CORE-SW
Management Address: 10.0.0.1
System Description: DASAN Switch

Local Intf: Gi1/0/2
Port id: Gi0/2
System Name: EDGE-SW
"""
    d = GenericDriver("h", "u", "p", device_type="cisco_ios")
    d.connection = FakeConn({"show lldp neighbors detail|textfsm": None, "show lldp neighbors detail": raw})
    n = d.get_neighbors()
    assert any(x["protocol"] == "LLDP" and x["local_interface"] == "Gi1/0/1" and x["remote_interface"] == "Gi0/1" and x["neighbor_name"] == "CORE-SW" and x["mgmt_ip"] == "10.0.0.1" for x in n)


def test_generic_driver_parses_cdp_raw_neighbors():
    raw = """
Device ID: DIST-SW
Entry address(es):
  IP address: 10.0.0.2
Platform: cisco WS-C3850,  Capabilities: Switch IGMP
Interface: GigabitEthernet1/0/3,  Port ID (outgoing port): GigabitEthernet0/3
"""
    d = GenericDriver("h", "u", "p", device_type="cisco_ios")
    d.connection = FakeConn(
        {
            "show lldp neighbors detail|textfsm": None,
            "show lldp neighbors detail": "",
            "show cdp neighbors detail|textfsm": None,
            "show cdp neighbors detail": raw,
        }
    )
    n = d.get_neighbors()
    assert any(x["protocol"] == "CDP" and x["local_interface"].lower().startswith("gigabit") and x["remote_interface"].lower().startswith("gigabit") and x["neighbor_name"] == "DIST-SW" and x["mgmt_ip"] == "10.0.0.2" for x in n)
