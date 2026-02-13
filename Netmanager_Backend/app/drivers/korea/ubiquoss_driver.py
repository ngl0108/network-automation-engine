from app.drivers.generic_driver import GenericDriver
from typing import List, Dict, Any
import re

class UbiquossDriver(GenericDriver):
    """
    Driver for Ubiquoss switches (L2/L3).
    """
    def __init__(self, hostname: str, username: str, password: str, port: int = 22, secret: str = None):
        super().__init__(hostname, username, password, port, secret, device_type="cisco_ios")

    def get_facts(self) -> Dict[str, Any]:
        if not self.connection:
            raise ConnectionError("Not connected")
        
        facts = {
            "vendor": "Ubiquoss",
            "os_version": "Unknown",
            "model": "Unknown",
            "serial_number": "Unknown",
            "uptime": "Unknown",
            "hostname": self.hostname,
        }
        
        try:
            # Ubiquoss typically supports standard 'show version' similar to Cisco
            output = self.connection.send_command("show version")
            
            # Simple parsing (Ubiquoss output mimics Cisco IOS often)
            if "Uptime is" in output:
                match = re.search(r"Uptime is (.*)", output)
                if match: facts["uptime"] = match.group(1).strip()
            
            # Match "Software Version : 3.1.2" OR "Version 3.1.2"
            match_ver = re.search(r"(?:Software )?Version\s*[:]?\s*([0-9.]+\S*)", output, re.IGNORECASE)
            if match_ver: facts["os_version"] = match_ver.group(1)
            
            match_model = re.search(r"Model\s*:\s*([^\n\r]+)", output, re.IGNORECASE)
            if match_model: facts["model"] = match_model.group(1).strip()
            
            facts["raw_output"] = output
        except Exception as e:
            facts["error"] = str(e)
            
        return facts

    def get_neighbors(self) -> List[Dict[str, Any]]:
        neighbors = []
        if not self.connection:
            return []

        try:
            generic = super().get_neighbors()
            if generic:
                return generic
        except Exception:
            pass
            
        try:
            # Ubiquoss LLDP
            raw = self.connection.send_command("show lldp neighbors")
            neighbors.extend(self._parse_ubiquoss_lldp(raw))
        except Exception:
            pass
        return neighbors

    def _parse_ubiquoss_lldp(self, raw: str) -> List[Dict[str, Any]]:
        """
        Parse Ubiquoss LLDP output.
        """
        neighbors = []
        # Similar logic to Dasan/Cisco but robust against column variations
        lines = raw.splitlines()
        for line in lines:
            line = line.strip()
            if not line or line.startswith("Device") or line.startswith("--"):
                continue
            
            parts = line.split()
            # Ubiquoss often: Device ID   Local Intf   Hold-time   Capability   Port ID
            if len(parts) >= 4:
                # Heuristic check: is first col a local intf or device id?
                # Usually: Device ID (Name) is first in Cisco-like outputs
                
                # Case 1: Standard Cisco-like
                # Device ID      Local Intf      Holdtme      Capability      Port ID
                # Switch-B       Gi0/2           120          R S             Gi0/1
                
                neighbor_name = parts[0]
                local_intf = parts[1]
                remote_intf = parts[-1] # Port ID is usually last
                
                # Check formatting
                # Sometimes split creates extra columns for capabilities
                
                neighbors.append({
                    "local_interface": local_intf,
                    "remote_interface": remote_intf,
                    "neighbor_name": neighbor_name,
                    "mgmt_ip": "",
                    "protocol": "LLDP"
                })
                
        return neighbors
