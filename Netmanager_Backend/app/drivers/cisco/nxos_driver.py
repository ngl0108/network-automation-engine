"""
Cisco NX-OS (Nexus) Driver with TextFSM-based structured parsing.
"""
from app.drivers.base import NetworkDriver
try:
    from netmiko import ConnectHandler
except Exception:  # pragma: no cover
    ConnectHandler = None
from typing import Dict, List, Any, Optional
import os
import re
import logging

logger = logging.getLogger(__name__)

# Set NTC_TEMPLATES_DIR for netmiko to find templates
try:
    import ntc_templates
    NTC_TEMPLATES_DIR = os.path.dirname(ntc_templates.__file__) + "/templates"
    os.environ.setdefault("NET_TEXTFSM", NTC_TEMPLATES_DIR)
except ImportError:
    NTC_TEMPLATES_DIR = None


class CiscoNXOSDriver(NetworkDriver):
    """
    Cisco NX-OS Driver optimized for Nexus switches.
    Uses 'cisco_nxos' device type in Netmiko.
    """
    
    DEVICE_TYPE = "cisco_nxos"
    
    def connect(self) -> bool:
        try:
            if not ConnectHandler:
                raise ModuleNotFoundError("netmiko is not installed")
            self.connection = ConnectHandler(
                device_type=self.DEVICE_TYPE,
                host=self.hostname,
                username=self.username,
                password=self.password,
                secret=self.secret,
                port=self.port,
                global_delay_factor=2,
                banner_timeout=30,
                auth_timeout=30,
                conn_timeout=60,
                fast_cli=False
            )
            # Nexus rarely needs 'enable' as admin role is usually direct exec, 
            # but we keep it for consistency if a secret is provided.
            if self.secret:
                try:
                    self.connection.enable()
                except Exception:
                    pass 
            return True
        except Exception as e:
            self.last_error = str(e)
            logger.warning("CiscoNXOSDriver connection error error=%s", e)
            return False

    def disconnect(self):
        if self.connection:
            self.connection.disconnect()
            self.connection = None

    def check_connection(self) -> bool:
        if not self.connection:
            return False
        return self.connection.is_alive()

    def get_facts(self) -> Dict[str, Any]:
        """
        Get device facts using TextFSM parsed 'show version'.
        Nexus specific output handling.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
        
        parsed_ver = self.connection.send_command("show version", use_textfsm=True)
        parsed_inv = self.connection.send_command("show inventory", use_textfsm=True)
        
        facts = {
            "vendor": "Cisco",
            "os_version": "Unknown",
            "model": "Nexus",
            "serial_number": "Unknown",
            "uptime": "Unknown",
            "hostname": self.connection.find_prompt().replace("#", "").strip()
        }

        # 1. Process Version
        if isinstance(parsed_ver, list) and parsed_ver:
            data = parsed_ver[0]
            # NX-OS templates use 'os' or 'nxos_ver_str' or 'software'
            facts["os_version"] = data.get("nxos_ver_str") or data.get("software") or data.get("os") or "Unknown"
            facts["uptime"] = data.get("uptime") or "Unknown"
            if data.get("platform"):
                facts["model"] = data.get("platform")

        # 2. Process Inventory for Serial (More reliable for Nexus)
        if isinstance(parsed_inv, list) and parsed_inv:
            for item in parsed_inv:
                # Chassis serial is usually what we want
                name = str(item.get("name", "")).lower()
                if "chassis" in name or item == parsed_inv[0]:
                    facts["serial_number"] = item.get("sn") or item.get("serial_number") or facts["serial_number"]
                    if not facts["model"] or facts["model"] == "Nexus":
                        facts["model"] = item.get("pid") or item.get("product_id") or facts["model"]
                    break

        return facts

    def get_interfaces(self) -> List[Dict[str, Any]]:
        """
        Nexus specific: Combine 'show interface status' and 'show interface'.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
        
        interfaces = []
        
        # 1. 'show interface status' is great for Nexus (shows VLAN, Mode, Speed, Status in one line)
        status_parsed = self.connection.send_command("show interface status", use_textfsm=True)
        status_map = {}
        
        if isinstance(status_parsed, list):
            for entry in status_parsed:
                port = entry.get("port") or entry.get("interface", "")
                status_map[port] = {
                    "vlan": entry.get("vlan", "1"),
                    "mode": entry.get("mode", "access"),
                    "speed": entry.get("speed", ""),
                    "duplex": entry.get("duplex", ""),
                    "status": entry.get("status", "down")
                }

        # 2. 'show interface' for descriptions and MACs
        detail_parsed = self.connection.send_command("show interface", use_textfsm=True, read_timeout=120)
        
        if isinstance(detail_parsed, list):
            for entry in detail_parsed:
                intf_name = entry.get("interface", "")
                st_info = status_map.get(intf_name, {})
                
                # Determine status
                link_status = entry.get("link_status") or st_info.get("status", "down")
                is_up = link_status.lower() in ("up", "connected", "sfp-present")
                is_enabled = "administratively" not in link_status.lower()
                
                interfaces.append({
                    "name": intf_name,
                    "description": entry.get("description", ""),
                    "is_up": is_up,
                    "is_enabled": is_enabled,
                    "link_status": link_status,
                    "protocol_status": entry.get("admin_state", "down"),
                    "ip_address": entry.get("ip_address", ""),
                    "mac_address": entry.get("address", ""),
                    "mtu": entry.get("mtu", ""),
                    "bandwidth": entry.get("bandwidth", ""),
                    "duplex": entry.get("duplex") or st_info.get("duplex", ""),
                    "speed": entry.get("speed") or st_info.get("speed", ""),
                    "input_errors": entry.get("input_errors", 0),
                    "output_errors": entry.get("output_errors", 0),
                    "vlan": st_info.get("vlan", "1")
                })
        
        return interfaces

    def push_config(self, config_commands: List[str]) -> Dict[str, Any]:
        if not self.connection:
            raise ConnectionError("Not connected")
            
        try:
            output = self.connection.send_config_set(config_commands)
            # Nexus save: 'copy running-config startup-config'
            self.connection.send_command("copy running-config startup-config", read_timeout=60)
            return {"success": True, "output": output}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_config(self, source: str = "running") -> str:
        if not self.connection:
            raise ConnectionError("Not connected")
        cmd = "show running-config" if source == "running" else "show startup-config"
        return self.connection.send_command(cmd, read_timeout=180)

    def get_neighbors(self) -> List[Dict[str, Any]]:
        """
        NX-OS CDP/LLDP parsing with interface name normalization.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
        
        neighbors = []
        
        def normalize_intf(name: str) -> str:
            if not name: return ""
            # Eth1/1 -> Ethernet1/1, mgmt0 -> mgmt0
            name = name.strip()
            if name.lower().startswith("eth"):
                # Preserve numeric part
                match = re.search(r"(\d.*)", name)
                if match: return f"Ethernet{match.group(1)}"
            return name

        # Try LLDP
        lldp_parsed = self.connection.send_command("show lldp neighbors detail", use_textfsm=True)
        if isinstance(lldp_parsed, list) and lldp_parsed:
            for entry in lldp_parsed:
                neighbors.append({
                    "neighbor_name": entry.get("chassis_id") or entry.get("system_name", "Unknown"),
                    "mgmt_ip": entry.get("mgmt_address") or entry.get("management_ip", ""),
                    "local_interface": normalize_intf(entry.get("local_interface") or entry.get("local_port", "")),
                    "remote_interface": normalize_intf(entry.get("port_id") or entry.get("remote_port", "")),
                    "platform": entry.get("system_description", ""),
                    "capability": entry.get("capabilities", ""),
                    "protocol": "LLDP"
                })

        # Try CDP
        cdp_parsed = self.connection.send_command("show cdp neighbors detail", use_textfsm=True)
        if isinstance(cdp_parsed, list) and cdp_parsed:
            for entry in cdp_parsed:
                neighbors.append({
                    "neighbor_name": entry.get("dest_host") or entry.get("neighbor_name", "Unknown"),
                    "mgmt_ip": entry.get("mgmt_address") or entry.get("management_ip", ""),
                    "local_interface": normalize_intf(entry.get("local_port") or entry.get("local_interface", "")),
                    "remote_interface": normalize_intf(entry.get("remote_port") or entry.get("neighbor_interface", "")),
                    "platform": entry.get("platform", ""),
                    "capability": entry.get("capabilities", ""),
                    "protocol": "CDP"
                })
        
        return neighbors

    def check_connection(self) -> bool:
        return super().check_connection()
