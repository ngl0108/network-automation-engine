
import re
from typing import Optional, Tuple, Dict

# ============================================================================
# 1. SNMP Enterprise OID Database (PEN: Private Enterprise Number)
# ============================================================================
VENDOR_OIDS = {
    # Global Vendors
    "1.3.6.1.4.1.9": "Cisco",
    "1.3.6.1.4.1.29671": "Cisco Meraki",
    "1.3.6.1.4.1.2636": "Juniper",
    "1.3.6.1.4.1.30065": "Arista",
    "1.3.6.1.4.1.2011": "Huawei",
    "1.3.6.1.4.1.11": "HP",
    "1.3.6.1.4.1.25506": "H3C",
    "1.3.6.1.4.1.14823": "Aruba",
    "1.3.6.1.4.1.1916": "Extreme",
    "1.3.6.1.4.1.45": "Nortel", # Avaya/Extreme
    "1.3.6.1.4.1.2272": "Passport", # Nortel/Extreme
    "1.3.6.1.4.1.1872": "Alteon", # Radware
    "1.3.6.1.4.1.89": "Allied Telesis",
    "1.3.6.1.4.1.171": "D-Link",
    "1.3.6.1.4.1.6486": "Alcatel-Lucent",
    "1.3.6.1.4.1.12356": "Fortinet",
    "1.3.6.1.4.1.25461": "PaloAlto",
    "1.3.6.1.4.1.3375": "F5",
    "1.3.6.1.4.1.2620": "CheckPoint",
    "1.3.6.1.4.1.5951": "NetScaler", # Citrix
    "1.3.6.1.4.1.3076": "Ruckus",
    "1.3.6.1.4.1.119": "NEC",
    "1.3.6.1.4.1.2": "IBM",
    "1.3.6.1.4.1.674": "Dell",

    # Korean Vendors
    "1.3.6.1.4.1.6296": "Dasan",         # Dasan Zhone
    "1.3.6.1.4.1.6728": "Dasan",         # Dasan/DZS (PEN)
    "1.3.6.1.4.1.7800": "Ubiquoss",      # Ubiquoss
    "1.3.6.1.4.1.7803": "Ubiquoss",      # Ubiquoss (Legacy)
    "1.3.6.1.4.1.7784": "Ubiquoss",      # Ubiquoss (PEN)
    "1.3.6.1.4.1.10226": "Ubiquoss",     # Ubiquoss (Alt PEN)
    "1.3.6.1.4.1.20935": "Handream",     # HanDreamnet
    "1.3.6.1.4.1.23237": "HanDreamnet",  # HanDreamnet (Alt)
    "1.3.6.1.4.1.14781": "HanDreamnet",  # Handreamnet (PEN)
    "1.3.6.1.4.1.17804": "Piolink",      # Piolink
    "1.3.6.1.4.1.13530": "Piolink",      # Piolink (PAS)
    "1.3.6.1.4.1.11798": "Piolink",      # Piolink (PEN)
    "1.3.6.1.4.1.29336": "NST IC",       # NST
    "1.3.6.1.4.1.13626": "HFR",          # HFR
    "1.3.6.1.4.1.10166": "Coweaver",     # Coweaver
    "1.3.6.1.4.1.10931": "WooriNet",     # WooriNet
    "1.3.6.1.4.1.14838": "Telefield",    # Telefield
    "1.3.6.1.4.1.19865": "EFMNetworks",  # ipTIME
    "1.3.6.1.4.1.17792": "EFMNetworks",  # ipTIME (PEN)
    "1.3.6.1.4.1.16668": "Mercury",      # Mercury
    "1.3.6.1.4.1.13974": "Davolink",     # Davolink

    # Security / NAC (Korea)
    "1.3.6.1.4.1.35020": "Genians",
    "1.3.6.1.4.1.5491": "NetMan",
    "1.3.6.1.4.1.26163": "AirCuve",
    "1.3.6.1.4.1.19746": "MLSoft",
    "1.3.6.1.4.1.26154": "SGA",
    "1.3.6.1.4.1.20038": "Nixtech",
    "1.3.6.1.4.1.26464": "AhnLab",
    "1.3.6.1.4.1.2608": "AhnLab",        # AhnLab (PEN)
    "1.3.6.1.4.1.2603": "SECUI",
    "1.3.6.1.4.1.4867": "SECUI",         # SECUI (PEN)
    "1.3.6.1.4.1.2439": "WINS",
    "1.3.6.1.4.1.3996": "WINS",          # WINS (PEN)
    "1.3.6.1.4.1.26472": "MonitorApp",
    "1.3.6.1.4.1.20237": "MonitorApp",   # MonitorApp (PEN)
    "1.3.6.1.4.1.37259": "AXGATE",
    "1.3.6.1.4.1.10641": "NexG",
    "1.3.6.1.4.1.30058": "TrinitySoft",

    # OS / Servers
    "1.3.6.1.4.1.8072": "Linux",
    "1.3.6.1.4.1.311": "Windows",
    "1.3.6.1.4.1.6876": "VMware",
    "1.3.6.1.4.1.231": "Compaq", # HP/Compaq
    "1.3.6.1.4.1.343": "Intel",
    "1.3.6.1.4.1.236": "Samsung", # Samsung Electronics (PEN)
}

# ============================================================================
# 2. Netmiko Driver Mapping
# ============================================================================
VENDOR_TO_DRIVER = {
    "Cisco": "cisco_ios",
    "Cisco Meraki": "cisco_meraki",
    "Juniper": "juniper_junos",
    "Arista": "arista_eos",
    "Huawei": "huawei",
    "HP": "hp_procurve",
    "Aruba": "aruba_os",
    "H3C": "hp_comware",
    "Extreme": "extreme_exos",
    "Dell": "dell_os10",
    "Alcatel-Lucent": "alcatel_aos",
    "Fortinet": "fortinet",
    "PaloAlto": "paloalto_panos",
    "F5": "f5_ltm",
    "CheckPoint": "checkpoint_gaia",
    "Linux": "linux",
    "Windows": "windows_cmd",
    "Dasan": "dasan_nos",
    "Ubiquoss": "ubiquoss_l2",
    "Handream": "handream_sg",
    "HanDreamnet": "handream_sg",
    "Piolink": "piolink_pas",
    "NST IC": "cisco_ios",
    "HFR": "cisco_ios",
    "Coweaver": "cisco_ios",
    "WooriNet": "cisco_ios",
    "Telefield": "cisco_ios",
    # Default fallback
    "Genians": "linux",
    "NetMan": "linux",
    "AirCuve": "linux",
    "MLSoft": "linux",
    "SGA": "linux",
    "Nixtech": "linux",
    "AhnLab": "linux",
    "SECUI": "linux",
    "WINS": "linux",
    "MonitorApp": "linux",
    "AXGATE": "linux",
    "NexG": "linux",
    "TrinitySoft": "linux",
    "EFMNetworks": "linux",
    "Mercury": "linux",
    "Davolink": "linux",
    "Samsung": "linux",
}

# ============================================================================
# 3. Model Extraction Regex Patterns
# ============================================================================
MODEL_PATTERNS = {
    "Cisco": [
        r"\b(C\d{4}[A-Z]?)\b",
        r"Cisco\s+Nexus\s+([0-9]+[A-Z0-9]*)", # Nexus
        r"Cisco\s+IOS\s+Software.*?\(([^)]+)\)", # IOS Image
        r"Cisco\s+Adaptive\s+Security\s+Appliance\s+Version\s+([0-9\.]+)", # ASA
    ],
    "Juniper": [
        r"Juniper\s+Networks,\s+Inc\.\s+([a-zA-Z0-9-]+)\s+Edge", # MX/SRX
        r"Junos:\s+([0-9\.]+)", # Version
        r"Model:\s+([a-zA-Z0-9-]+)", # Explicit Model
    ],
    "Arista": [
        r"Arista\s+([a-zA-Z0-9-]+)", # Arista 7050
    ],
    "Huawei": [
        r"Huawei\s+Versatile\s+Routing\s+Platform\s+Software",
        r"HUAWEI\s+([A-Z0-9-]+)\s+Switch",
    ],
    "Dasan": [
        r"Dasan\s+Networks\s+([A-Z0-9-]+)",
        r"\b(V\d{4}[A-Z0-9-]*)\b",
    ],
    "Ubiquoss": [
        r"\b([A-Z]{1,5}-?\d{3,5}[A-Z0-9-]*)\b",
        r"Ubiquoss\s+(?:L[23]\s+)?(?:Switch\s+)?([A-Z0-9-\/]+)",
        r"uNOS\s+System\s+([A-Z0-9-]+)",
    ],
    "Handream": [
        r"\b(SG\d{3,5}[A-Z0-9-]*)\b",
        r"\b(Subgate|SubGate)\b",
    ],
    "HanDreamnet": [
        r"\b(SG\d{3,5}[A-Z0-9-]*)\b",
        r"\b(Subgate|SubGate)\b",
    ],
    "Piolink": [
        r"\b(PAS-[A-Z0-9-]+)\b",
        r"\b(TiFRONT)\b",
    ],
    "AhnLab": [
        r"\b(TrusGuard\s*[A-Z0-9-]+)\b",
        r"\b(TrusGuard)\b",
    ],
    "SECUI": [
        r"\b(MF\d+[A-Z0-9-]*)\b",
        r"\b(BLUEMAX)\b",
    ],
    "WINS": [
        r"\b(DDX-[A-Z0-9-]+)\b",
        r"\b(Sniper\s+[A-Z0-9-]+)\b",
    ],
    "MonitorApp": [
        r"\b(AIWAF[A-Z0-9-]*)\b",
    ],
    "EFMNetworks": [
        r"\b(A\d{3,4}[A-Z0-9-]*)\b",
        r"\biptime\s+([a-z0-9-]+)\b",
    ],
    "Samsung": [
        r"\b([A-Z]{2,6}-\d{3,6}[A-Z0-9-]*)\b",
        r"Samsung\s+([A-Z0-9-]+)",
    ],
}

def identify_vendor_by_oid(sys_oid: str, sys_descr: str = "") -> Tuple[str, float]:
    """
    Identifies vendor from sys_oid (primary) or sys_descr (fallback).
    Returns (VendorName, ConfidenceScore).
    """
    sys_oid = (sys_oid or "").strip()
    sys_descr = (sys_descr or "").lower()
    
    # 1. Precise OID Match
    # Sort by key length desc to match longer (more specific) OIDs first
    sorted_oids = sorted(VENDOR_OIDS.items(), key=lambda x: len(x[0]), reverse=True)
    
    for oid, vendor in sorted_oids:
        if sys_oid.startswith(oid):
            # Special Handling for generic OIDs that share prefixes
            if oid == "1.3.6.1.4.1.23237": # HanDreamnet
                if "somansa" in sys_descr:
                    return "Somansa", 0.9
                if "handream" in sys_descr or "subgate" in sys_descr:
                    return "HanDreamnet", 0.9
            return vendor, 0.95

    # 2. SysDescr Text Match (Fallback)
    if "cisco" in sys_descr: return "Cisco", 0.8
    if "juniper" in sys_descr or "junos" in sys_descr: return "Juniper", 0.8
    if "arista" in sys_descr or "eos" in sys_descr: return "Arista", 0.8
    if "huawei" in sys_descr or "vrp" in sys_descr: return "Huawei", 0.8
    if "hp" in sys_descr or "procurve" in sys_descr or "provision" in sys_descr: return "HP", 0.7
    if "aruba" in sys_descr: return "Aruba", 0.8
    if "extreme" in sys_descr or "xos" in sys_descr or "exos" in sys_descr: return "Extreme", 0.8
    if "dell" in sys_descr or "powerconnect" in sys_descr or "force10" in sys_descr: return "Dell", 0.8
    if "fortinet" in sys_descr or "fortigate" in sys_descr: return "Fortinet", 0.8
    if "paloalto" in sys_descr or "panos" in sys_descr: return "PaloAlto", 0.8
    if "f5" in sys_descr or "big-ip" in sys_descr: return "F5", 0.8
    if "iptime" in sys_descr: return "EFMNetworks", 0.8
    if "samsung" in sys_descr: return "Samsung", 0.8
    if "linux" in sys_descr: return "Linux", 0.6
    if "windows" in sys_descr: return "Windows", 0.6
    
    # Korean Vendors Text Match
    if "dasan" in sys_descr: return "Dasan", 0.8
    if "ubiquoss" in sys_descr: return "Ubiquoss", 0.8
    if "handream" in sys_descr: return "HanDreamnet", 0.8
    if "piolink" in sys_descr: return "Piolink", 0.8
    if "wins" in sys_descr or "sniper" in sys_descr: return "WINS", 0.8
    if "secui" in sys_descr or "bluemax" in sys_descr: return "SECUI", 0.8
    if "ahnlab" in sys_descr or "trusguard" in sys_descr: return "AhnLab", 0.8
    if "genians" in sys_descr: return "Genians", 0.8
    
    return "Unknown", 0.0

def extract_model_from_descr(vendor: str, sys_descr: str) -> Optional[str]:
    """
    Attempts to extract the model number from sys_descr using regex patterns.
    """
    if not sys_descr or not vendor or vendor == "Unknown":
        return None
        
    patterns = MODEL_PATTERNS.get(vendor, [])
    for pattern in patterns:
        match = re.search(pattern, sys_descr, re.IGNORECASE)
        if match:
            if match.lastindex:
                return match.group(1).strip()
            return match.group(0).strip()
            
    return None

def get_driver_for_vendor(vendor: str) -> str:
    """
    Returns the Netmiko/Napalm driver name for a given vendor.
    Defaults to 'generic' (which usually maps to linux or similar).
    """
    return VENDOR_TO_DRIVER.get(vendor, "unknown")
