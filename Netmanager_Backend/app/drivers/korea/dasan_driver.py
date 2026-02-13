from app.drivers.generic_driver import GenericDriver
from typing import List, Dict, Any
import re

class DasanDriver(GenericDriver):
    """
    Driver for Dasan Networks switches (NOS).
    Extends GenericDriver but provides specialized parsing for LLDP and system facts.
    """
    def __init__(self, hostname: str, username: str, password: str, port: int = 22, secret: str = None):
        super().__init__(hostname, username, password, port, secret, device_type="cisco_ios")

    def get_facts(self) -> Dict[str, Any]:
        """
        Dasan specific facts gathering.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
        
        # Dasan often uses 'show system' or 'show version'
        # We try 'show system info' or fall back to 'show version'
        facts = {
            "vendor": "Dasan",
            "os_version": "Unknown",
            "model": "Unknown",
            "serial_number": "Unknown",
            "uptime": "Unknown",
            "hostname": self.hostname,
        }

        try:
            output = self.connection.send_command("show system info")
            if "invalid" in output.lower() or "unknown" in output.lower():
                output = self.connection.send_command("show version")
            
            # Parse logic
            for line in output.splitlines():
                line = line.strip()
                if "System Name" in line or "Host Name" in line:
                    parts = line.split(":", 1)
                    if len(parts) > 1: facts["hostname"] = parts[1].strip()
                elif "System Type" in line or "Model" in line:
                    parts = line.split(":", 1)
                    if len(parts) > 1: facts["model"] = parts[1].strip()
                elif "Serial Number" in line:
                    parts = line.split(":", 1)
                    if len(parts) > 1: facts["serial_number"] = parts[1].strip()
                elif "NOS Version" in line or "Software Version" in line:
                    parts = line.split(":", 1)
                    if len(parts) > 1: facts["os_version"] = parts[1].strip()
                elif "Up Time" in line:
                    parts = line.split(":", 1)
                    if len(parts) > 1: facts["uptime"] = parts[1].strip()
            
            facts["raw_output"] = output
        except Exception as e:
            facts["error"] = str(e)
            
        return facts

    def get_neighbors(self) -> List[Dict[str, Any]]:
        """
        Dasan specific LLDP parsing.
        Use 'show lldp neighbors' but handle potential format differences.
        """
        neighbors = []
        if not self.connection:
            return []

        try:
            generic = super().get_neighbors()
            if generic:
                return generic
        except Exception:
            pass

        # Try textual parsing first as TextFSM might not exist for Dasan
        try:
            raw_lldp = self.connection.send_command("show lldp neighbor")
            neighbors.extend(self._parse_dasan_lldp(raw_lldp))
        except Exception:
            pass
            
        return neighbors

    def apply_config_replace(self, raw_config: str) -> Dict[str, Any]:
        return super().apply_config_replace(raw_config)

    def _parse_dasan_lldp(self, raw: str) -> List[Dict[str, Any]]:
        """
        Parses Dasan 'show lldp neighbor' output.
        Format often looks like:
        
        Local Port   Device ID          Port ID          System Name
        ---------------------------------------------------------------
        1/1          00:11:22:33:44:55  gi0/1            Switch-A
        
        Or varying number of columns. We use regex for robustness.
        """
        neighbors = []
        lines = raw.splitlines()
        
        # Regex to capture: Local Intf, Device ID/Name, Remote Intf
        # This is a heuristic.
        # Pattern: <Local> <Spaces> <DeviceID> <Spaces> <RemotePort> ...
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith("Local") or line.startswith("--"):
                continue
                
            # Naive split by whitespace
            parts = line.split()
            if len(parts) >= 3:
                # Heuristic: 
                # Col 0: Local Port
                # Col 1: Device ID (or Name)
                # Col 2: Port ID (Remote)
                # Col 3+: System Name (Optional)
                
                local_intf = parts[0]
                neighbor_id = parts[1] # MAC or Name
                remote_intf = parts[2]
                neighbor_name = parts[-1] if len(parts) > 3 else neighbor_id
                
                # Filter out suspicious headers/garbage
                if "..." in line or "Total" in line:
                    continue

                neighbors.append({
                    "local_interface": local_intf,
                    "remote_interface": remote_intf,
                    "neighbor_name": neighbor_name,
                    "mgmt_ip": "", # Dasan LLDP summary often doesn't show IP
                    "protocol": "LLDP"
                })
        
        # Enhancements: Try 'show lldp neighbor detail' for IP if needed
        # But this basic summary is enough for topology linking.
        return neighbors
