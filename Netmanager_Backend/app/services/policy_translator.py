from typing import List
import ipaddress
from app.models.device import Policy, PolicyRule


class PolicyTranslator:
    """
    Multi-vendor policy translator.
    Converts abstract policy rules to vendor-specific CLI commands.
    """
    
    @staticmethod
    def translate(policy: Policy, device_type: str) -> List[str]:
        """
        Main entry point to translate a policy for a specific device type.
        """
        dtype = device_type.lower()
        
        # Cisco
        if "cisco" in dtype or "ios" in dtype or "nxos" in dtype:
            return PolicyTranslator.to_cisco_ios(policy)
        
        # Juniper
        if "juniper" in dtype or "junos" in dtype:
            return PolicyTranslator.to_juniper_junos(policy)
        
        # Arista
        if "arista" in dtype or "eos" in dtype:
            return PolicyTranslator.to_arista_eos(policy)
        
        # Fallback
        return [f"! No translator found for {device_type}"]

    # ================================================================
    # Cisco IOS/IOS-XE/NX-OS
    # ================================================================
    @staticmethod
    def to_cisco_ios(policy: Policy) -> List[str]:
        """
        Generates Cisco IOS 'ip access-list extended' commands.
        """
        commands = []
        acl_name = policy.name.replace(" ", "_").upper()
        
        commands.append(f"ip access-list extended {acl_name}")
        
        sorted_rules = sorted(policy.rules, key=lambda r: r.priority)
        
        for rule in sorted_rules:
            action = rule.action.lower() if rule.action else "permit"
            conditions = rule.match_conditions or {}
            protocol = conditions.get("protocol", "ip")
            src = PolicyTranslator._parse_address_cisco(conditions.get("source", "any"))
            dst = PolicyTranslator._parse_address_cisco(conditions.get("destination", "any"))
            
            port_str = ""
            if protocol in ["tcp", "udp"]:
                port = conditions.get("port")
                if port and str(port).lower() != "any":
                    port_str = f" eq {port}"
            
            cmd = f" {action} {protocol} {src} {dst}{port_str}"
            commands.append(cmd)
            
        return commands

    # ================================================================
    # Juniper JunOS
    # ================================================================
    @staticmethod
    def to_juniper_junos(policy: Policy) -> List[str]:
        """
        Generates Juniper JunOS 'firewall filter' configuration.
        Format: set firewall filter <name> term <term_name> ...
        """
        commands = []
        filter_name = policy.name.replace(" ", "-").upper()
        
        sorted_rules = sorted(policy.rules, key=lambda r: r.priority)
        
        for idx, rule in enumerate(sorted_rules, start=1):
            term_name = f"TERM-{idx}"
            action = "accept" if rule.action.lower() == "permit" else "reject"
            conditions = rule.match_conditions or {}
            protocol = conditions.get("protocol", "ip")
            src = conditions.get("source", "any")
            dst = conditions.get("destination", "any")
            port = conditions.get("port")
            
            # Source address
            if src and src.lower() != "any":
                commands.append(f"set firewall filter {filter_name} term {term_name} from source-address {src}")
            
            # Destination address
            if dst and dst.lower() != "any":
                commands.append(f"set firewall filter {filter_name} term {term_name} from destination-address {dst}")
            
            # Protocol
            if protocol and protocol.lower() != "ip":
                commands.append(f"set firewall filter {filter_name} term {term_name} from protocol {protocol}")
            
            # Port
            if port and protocol in ["tcp", "udp"]:
                commands.append(f"set firewall filter {filter_name} term {term_name} from destination-port {port}")
            
            # Action
            commands.append(f"set firewall filter {filter_name} term {term_name} then {action}")
        
        return commands

    # ================================================================
    # Arista EOS
    # ================================================================
    @staticmethod
    def to_arista_eos(policy: Policy) -> List[str]:
        """
        Generates Arista EOS 'ip access-list' commands.
        Arista EOS syntax is very similar to Cisco IOS.
        """
        commands = []
        acl_name = policy.name.replace(" ", "_").upper()
        
        commands.append(f"ip access-list {acl_name}")
        
        sorted_rules = sorted(policy.rules, key=lambda r: r.priority)
        
        for idx, rule in enumerate(sorted_rules, start=10):  # Arista uses sequence numbers
            action = rule.action.lower() if rule.action else "permit"
            conditions = rule.match_conditions or {}
            protocol = conditions.get("protocol", "ip")
            src = PolicyTranslator._parse_address_arista(conditions.get("source", "any"))
            dst = PolicyTranslator._parse_address_arista(conditions.get("destination", "any"))
            
            port_str = ""
            if protocol in ["tcp", "udp"]:
                port = conditions.get("port")
                if port and str(port).lower() != "any":
                    port_str = f" eq {port}"
            
            # Arista uses sequence numbers (10, 20, 30...)
            cmd = f"   {idx} {action} {protocol} {src} {dst}{port_str}"
            commands.append(cmd)
            
        return commands

    # ================================================================
    # Address Parsing Helpers
    # ================================================================
    @staticmethod
    def _parse_address_cisco(addr: str) -> str:
        """
        Format IP addresses for Cisco IOS.
        - "any" -> "any"
        - "10.1.1.1" -> "host 10.1.1.1"
        - "10.1.1.0/24" -> "10.1.1.0 0.0.0.255"
        """
        if not addr or str(addr).lower() == "any":
            return "any"
        
        if "/" in addr:
            try:
                network = ipaddress.ip_network(addr, strict=False)
                return f"{network.network_address} {network.hostmask}"
            except ValueError:
                return f"! INVALID_IP({addr})"

        if " " not in addr and addr.count(".") == 3:
            return f"host {addr}"
            
        return addr

    @staticmethod
    def _parse_address_arista(addr: str) -> str:
        """
        Format IP addresses for Arista EOS.
        Similar to Cisco but Arista prefers CIDR notation.
        """
        if not addr or str(addr).lower() == "any":
            return "any"
        
        # Arista accepts CIDR directly
        if "/" in addr:
            return addr

        if " " not in addr and addr.count(".") == 3:
            return f"host {addr}"
            
        return addr


