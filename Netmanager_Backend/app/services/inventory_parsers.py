import re
from typing import Any, Dict, List, Optional


class InventoryParser:
    name = "base"
    priority = 100

    def can_handle(self, device_type: str) -> bool:
        return True

    def collect(self, conn: Any) -> List[Dict[str, Any]]:
        raise NotImplementedError()


class CiscoShowInventoryParser(InventoryParser):
    name = "cisco_show_inventory"
    priority = 10

    def can_handle(self, device_type: str) -> bool:
        dt = str(device_type or "").lower()
        return dt in ("cisco_ios", "cisco_ios_xe", "cisco_xe", "cisco_nxos", "cisco_wlc") or dt.startswith("cisco_")

    @staticmethod
    def _normalize_text(s: Any) -> str:
        return str(s or "").strip()

    @staticmethod
    def _parse_textfsm(parsed: Any) -> List[Dict[str, Any]]:
        if not isinstance(parsed, list):
            return []
        rows = []
        for r in parsed:
            if not isinstance(r, dict):
                continue
            name = CiscoShowInventoryParser._normalize_text(r.get("name") or r.get("NAME") or r.get("slot") or r.get("module"))
            descr = CiscoShowInventoryParser._normalize_text(r.get("descr") or r.get("description") or r.get("DESCR"))
            pid = CiscoShowInventoryParser._normalize_text(r.get("pid") or r.get("PID") or r.get("productid"))
            sn = CiscoShowInventoryParser._normalize_text(r.get("sn") or r.get("serial") or r.get("serial_number") or r.get("SN"))
            if not (name or pid or sn or descr):
                continue
            rows.append(
                {
                    "name": name,
                    "description": descr,
                    "model_name": pid,
                    "serial_number": sn,
                }
            )
        return rows

    @staticmethod
    def _parse_raw(output: str) -> List[Dict[str, Any]]:
        text = str(output or "")
        if not text.strip():
            return []
        blocks = re.split(r"\n\s*\n", text)
        rows = []
        for b in blocks:
            name_m = re.search(r'NAME\s*:\s*"([^"]+)"', b, re.IGNORECASE)
            descr_m = re.search(r'DESCR\s*:\s*"([^"]+)"', b, re.IGNORECASE)
            pid_m = re.search(r"\bPID\s*:\s*([^,\n]+)", b, re.IGNORECASE)
            sn_m = re.search(r"\bSN\s*:\s*([^\s,\n]+)", b, re.IGNORECASE)
            if not (name_m or pid_m or sn_m or descr_m):
                continue
            rows.append(
                {
                    "name": CiscoShowInventoryParser._normalize_text(name_m.group(1) if name_m else ""),
                    "description": CiscoShowInventoryParser._normalize_text(descr_m.group(1) if descr_m else ""),
                    "model_name": CiscoShowInventoryParser._normalize_text(pid_m.group(1) if pid_m else ""),
                    "serial_number": CiscoShowInventoryParser._normalize_text(sn_m.group(1) if sn_m else ""),
                }
            )
        return rows

    def collect(self, conn: Any) -> List[Dict[str, Any]]:
        parsed = None
        raw = None
        try:
            parsed = conn.send_command("show inventory", use_textfsm=True)
        except Exception:
            parsed = None
        rows = self._parse_textfsm(parsed)
        if rows:
            return rows
        try:
            raw = conn.send_command("show inventory")
        except Exception:
            raw = None
        return self._parse_raw(raw or "")


class JuniperChassisHardwareParser(InventoryParser):
    name = "juniper_show_chassis_hardware"
    priority = 20

    def can_handle(self, device_type: str) -> bool:
        dt = str(device_type or "").lower()
        return dt in ("juniper_junos", "juniper") or dt.startswith("juniper")

    @staticmethod
    def _normalize_text(s: Any) -> str:
        return str(s or "").strip()

    @staticmethod
    def _parse_textfsm(parsed: Any) -> List[Dict[str, Any]]:
        if not isinstance(parsed, list):
            return []
        rows = []
        for r in parsed:
            if not isinstance(r, dict):
                continue
            item = JuniperChassisHardwareParser._normalize_text(r.get("item") or r.get("name") or r.get("ITEM"))
            descr = JuniperChassisHardwareParser._normalize_text(r.get("description") or r.get("descr") or r.get("DESCR"))
            part = JuniperChassisHardwareParser._normalize_text(r.get("part_number") or r.get("part") or r.get("pid") or r.get("PN"))
            sn = JuniperChassisHardwareParser._normalize_text(r.get("serial_number") or r.get("serial") or r.get("SN"))
            if not (item or part or sn or descr):
                continue
            rows.append({"name": item, "description": descr, "model_name": part, "serial_number": sn})
        return rows

    @staticmethod
    def _parse_raw(output: str) -> List[Dict[str, Any]]:
        text = str(output or "")
        if not text.strip():
            return []
        lines = [ln.rstrip("\n") for ln in text.splitlines() if ln.strip()]
        start = 0
        for i, ln in enumerate(lines):
            if ln.lower().startswith("item") and "serial" in ln.lower():
                start = i + 1
                break
        if start == 0:
            for i, ln in enumerate(lines):
                if "hardware inventory" in ln.lower():
                    start = i + 1
                    break
        rows = []
        for ln in lines[start:]:
            if ln.lower().startswith("item") and "serial" in ln.lower():
                continue
            parts = re.split(r"\s{2,}", ln.strip())
            if len(parts) < 2:
                continue
            item = parts[0].strip()
            descr = parts[-1].strip() if parts else ""
            serial = ""
            model = ""
            for tok in parts[1:-1]:
                if re.fullmatch(r"[A-Za-z0-9]{6,}", tok) and not serial:
                    serial = tok
                elif re.search(r"\d", tok) and not model:
                    model = tok
            rows.append({"name": item, "description": descr, "model_name": model, "serial_number": serial})
        return rows

    def collect(self, conn: Any) -> List[Dict[str, Any]]:
        parsed = None
        raw = None
        try:
            parsed = conn.send_command("show chassis hardware", use_textfsm=True)
        except Exception:
            parsed = None
        rows = self._parse_textfsm(parsed)
        if rows:
            return rows
        try:
            raw = conn.send_command("show chassis hardware")
        except Exception:
            raw = None
        return self._parse_raw(raw or "")


class AristaEosInventoryParser(InventoryParser):
    name = "arista_eos_inventory"
    priority = 15

    def can_handle(self, device_type: str) -> bool:
        dt = str(device_type or "").lower()
        return dt in ("arista_eos", "arista") or dt.startswith("arista")

    @staticmethod
    def _normalize_text(s: Any) -> str:
        return str(s or "").strip()

    @staticmethod
    def _parse_textfsm(parsed: Any) -> List[Dict[str, Any]]:
        if not isinstance(parsed, list):
            return []
        rows = []
        for r in parsed:
            if not isinstance(r, dict):
                continue
            name = AristaEosInventoryParser._normalize_text(r.get("name") or r.get("slot") or r.get("item") or r.get("component"))
            descr = AristaEosInventoryParser._normalize_text(r.get("description") or r.get("descr"))
            pid = AristaEosInventoryParser._normalize_text(r.get("pid") or r.get("part_number") or r.get("model") or r.get("pn"))
            sn = AristaEosInventoryParser._normalize_text(r.get("sn") or r.get("serial") or r.get("serial_number"))
            if not (name or pid or sn or descr):
                continue
            rows.append({"name": name, "description": descr, "model_name": pid, "serial_number": sn})
        return rows

    @staticmethod
    def _parse_show_version(raw: str) -> List[Dict[str, Any]]:
        text = str(raw or "")
        if not text.strip():
            return []
        model = ""
        serial = ""
        m = re.search(r"^\s*Model name\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
        if m:
            model = m.group(1).strip()
        m = re.search(r"^\s*Serial number\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
        if m:
            serial = m.group(1).strip()
        if not model and not serial:
            return []
        return [{"name": "Chassis", "description": "Arista EOS", "model_name": model, "serial_number": serial}]

    def collect(self, conn: Any) -> List[Dict[str, Any]]:
        for cmd in ("show inventory all", "show inventory"):
            try:
                parsed = conn.send_command(cmd, use_textfsm=True)
            except Exception:
                parsed = None
            rows = self._parse_textfsm(parsed)
            if rows:
                return rows

        for cmd in ("show version detail", "show version"):
            try:
                raw = conn.send_command(cmd)
            except Exception:
                raw = None
            rows = self._parse_show_version(raw or "")
            if rows:
                return rows
        return []


class HpeArubaInventoryParser(InventoryParser):
    name = "hpe_aruba_inventory"
    priority = 25

    def can_handle(self, device_type: str) -> bool:
        dt = str(device_type or "").lower()
        return dt in ("aruba_os", "hp_procurve", "hpe_comware", "hp_comware") or "aruba" in dt or dt.startswith("hp_") or dt.startswith("hpe_")

    @staticmethod
    def _parse_system_info(raw: str) -> List[Dict[str, Any]]:
        text = str(raw or "")
        if not text.strip():
            return []
        model = ""
        serial = ""
        descr = ""
        m = re.search(r"^\s*(Product\s+Number|Product\s+Name|Model)\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
        if m:
            model = m.group(2).strip()
        m = re.search(r"^\s*(Serial\s+Number|Chassis\s+Serial)\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
        if m:
            serial = m.group(2).strip()
        m = re.search(r"^\s*(System\s+Description|Description)\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
        if m:
            descr = m.group(2).strip()
        if not model and not serial:
            return []
        return [{"name": "Chassis", "description": descr or "HPE/Aruba", "model_name": model, "serial_number": serial}]

    def collect(self, conn: Any) -> List[Dict[str, Any]]:
        for cmd in ("show inventory", "show chassis", "show system information", "show system"):
            try:
                raw = conn.send_command(cmd)
            except Exception:
                raw = None
            rows = self._parse_system_info(raw or "")
            if rows:
                return rows
        return []


class HuaweiInventoryParser(InventoryParser):
    name = "huawei_inventory"
    priority = 30

    def can_handle(self, device_type: str) -> bool:
        dt = str(device_type or "").lower()
        return dt in ("huawei", "huawei_vrp") or dt.startswith("huawei")

    @staticmethod
    def _parse_display_version(raw: str) -> Dict[str, str]:
        text = str(raw or "")
        model = ""
        m = re.search(r"^\s*Huawei\s+(\S+)\s+.*Version", text, re.IGNORECASE | re.MULTILINE)
        if m:
            model = m.group(1).strip()
        if not model:
            m = re.search(r"^\s*Device\s+Model\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
            if m:
                model = m.group(1).strip()
        return {"model": model}

    @staticmethod
    def _parse_display_esn(raw: str) -> str:
        text = str(raw or "")
        m = re.search(r"\bESN\b\s*:\s*([A-Za-z0-9]+)", text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        m = re.search(r"^\s*([A-Za-z0-9]{8,})\s*$", text, re.MULTILINE)
        if m:
            return m.group(1).strip()
        return ""

    @staticmethod
    def _parse_display_device(raw: str) -> List[Dict[str, Any]]:
        text = str(raw or "")
        if not text.strip():
            return []
        rows: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None
        for ln in text.splitlines():
            line = ln.strip()
            if not line:
                continue
            m = re.match(r"^slot\s+(\d+)\s*[:\-]", line, re.IGNORECASE)
            if m:
                if current:
                    rows.append(current)
                slot = m.group(1)
                current = {"name": f"Slot {slot}", "description": "", "model_name": "", "serial_number": "", "class_name": "module"}
                continue
            if current is None:
                continue
            m = re.match(r"^(board\s*type|type|boardname)\s*:\s*(.+)$", line, re.IGNORECASE)
            if m and not current.get("model_name"):
                current["model_name"] = m.group(2).strip()
                continue
            m = re.match(r"^(barcode|sn|serial\s*number|s/n)\s*:\s*(.+)$", line, re.IGNORECASE)
            if m and not current.get("serial_number"):
                current["serial_number"] = m.group(2).strip()
                continue
            m = re.match(r"^(description)\s*:\s*(.+)$", line, re.IGNORECASE)
            if m and not current.get("description"):
                current["description"] = m.group(2).strip()
                continue
        if current:
            rows.append(current)
        return [r for r in rows if r.get("name") and (r.get("model_name") or r.get("serial_number") or r.get("description"))]

    def collect(self, conn: Any) -> List[Dict[str, Any]]:
        modules: List[Dict[str, Any]] = []
        serial = ""
        model = ""
        try:
            modules = self._parse_display_device(conn.send_command("display device"))
        except Exception:
            modules = []
        try:
            serial = self._parse_display_esn(conn.send_command("display esn"))
        except Exception:
            serial = ""
        try:
            model = self._parse_display_version(conn.send_command("display version")).get("model") or ""
        except Exception:
            model = ""
        if not serial and not model and not modules:
            return []
        rows = [{"name": "Chassis", "description": "Huawei", "model_name": model, "serial_number": serial, "class_name": "chassis"}]
        rows.extend(modules)
        return rows


def get_inventory_parsers() -> List[InventoryParser]:
    parsers: List[InventoryParser] = [
        CiscoShowInventoryParser(),
        AristaEosInventoryParser(),
        JuniperChassisHardwareParser(),
        HpeArubaInventoryParser(),
        HuaweiInventoryParser(),
    ]
    parsers.sort(key=lambda p: int(getattr(p, "priority", 100)))
    return parsers
