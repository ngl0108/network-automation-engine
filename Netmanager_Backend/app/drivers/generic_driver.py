from app.drivers.base import NetworkDriver
try:
    from netmiko import ConnectHandler
except Exception:  # pragma: no cover
    ConnectHandler = None
from typing import Dict, List, Any, Optional
import os
import logging
import uuid

logger = logging.getLogger(__name__)

class GenericDriver(NetworkDriver):
    """
    Generic Driver using Netmiko for any supported vendor.
    This driver creates a connection based on the provided device_type via constructor.
    Parsing relies on basic regex or raw output if TextFSM templates are unavailable.
    """
    
    def __init__(self, hostname: str, username: str, password: str, port: int = 22, secret: Optional[str] = None, device_type: str = "cisco_ios"):
        super().__init__(hostname, username, password, port, secret)
        self.device_type = device_type
        
    def connect(self) -> bool:
        try:
            if not ConnectHandler:
                raise ModuleNotFoundError("netmiko is not installed")
            self.connection = ConnectHandler(
                device_type=self.device_type,
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
            if self.secret:
                self.connection.enable()
            return True
        except Exception as e:
            self.last_error = str(e)
            logger.warning("GenericDriver connection error device_type=%s error=%s", self.device_type, e)
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
        Generic get_facts. Tries 'show version' or 'display version' based on simple heuristics
        or returns raw output if parsing impossible.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
        
        # Determine command based on simple heuristics or map
        cmd = "show version"
        if "huawei" in self.device_type: cmd = "display version"
        if "hp" in self.device_type: cmd = "show version"
        if "juniper" in self.device_type: cmd = "show version" # XML is better but CLI is OK
        
        output = self.connection.send_command(cmd)
        
        return {
            "vendor": self.device_type,
            "os_version": "Check raw output",
            "model": "Unknown",
            "serial_number": "Unknown", 
            "uptime": "Unknown",
            "hostname": self.hostname,
            "raw_output": output
        }

    def get_interfaces(self) -> List[Dict[str, Any]]:
        if not self.connection:
            raise ConnectionError("Not connected")
            
        cmd = "show ip interface brief"
        if "huawei" in self.device_type: cmd = "display interface brief"
        if "hp" in self.device_type: cmd = "show ip interface brief"
        if "juniper" in self.device_type: cmd = "show interfaces terse"
        
        output = self.connection.send_command(cmd)
        
        # Return naive list
        return [{
            "name": "See raw output",
            "ip_address": "",
            "is_up": True,
            "is_enabled": True,
            "raw_output": output
        }]

    def push_config(self, config_commands: List[str]) -> Dict[str, Any]:
        if not self.connection:
            raise ConnectionError("Not connected")
            
        try:
            output = self.connection.send_config_set(config_commands)
            # Try to save (might fail on some vendors, ignore)
            try:
                if "cisco" in self.device_type or "ios" in self.device_type:
                    self.connection.send_command("write memory")
                elif "huawei" in self.device_type:
                    self.connection.send_command("save", expect_string=r"[yY]")
                elif "hp" in self.device_type:
                    self.connection.send_command("write memory")
                elif "juniper" in self.device_type:
                    self.connection.commit()
            except:
                pass 
                
            return {"success": True, "output": output}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _looks_like_cli_error(self, output: str) -> bool:
        t = (output or "").lower()
        return any(
            s in t
            for s in (
                "% invalid",
                "invalid input",
                "unknown command",
                "unrecognized command",
                "ambiguous command",
                "incomplete command",
                "error:",
                "syntax error",
                "failed",
            )
        )

    def apply_config_replace(self, raw_config: str) -> Dict[str, Any]:
        if not self.connection:
            raise ConnectionError("Not connected")

        dtype = str(self.device_type or "").lower()
        profile = getattr(self, "_config_replace_profile", None)
        if isinstance(profile, dict):
            dtype = str(profile.get("device_type") or dtype).lower()
        suffix = f"golden_{uuid.uuid4().hex[:10]}.cfg"

        if isinstance(profile, dict) and isinstance(profile.get("file_systems"), list) and profile.get("file_systems"):
            file_systems = [str(x).strip() for x in profile.get("file_systems") if str(x).strip()]
        else:
            if "nxos" in dtype or "cisco_nxos" in dtype:
                file_systems = ["bootflash:"]
            else:
                file_systems = ["flash:", "bootflash:", "disk0:", "primary:", "secondary:"]

        replace_cmds: List[str] = []
        if isinstance(profile, dict) and isinstance(profile.get("replace_commands"), list) and profile.get("replace_commands"):
            replace_cmds = [str(x).strip() for x in profile.get("replace_commands") if str(x).strip()]
        else:
            if "nxos" in dtype or "cisco_nxos" in dtype:
                replace_cmds = [
                    "configure replace {path} force",
                    "rollback running-config file {path}",
                ]
            else:
                replace_cmds = [
                    "configure replace {path} force",
                    "configuration replace {path} force",
                ]

        save_cmds: List[str] = []
        if isinstance(profile, dict) and isinstance(profile.get("save_commands"), list):
            save_cmds = [str(x).strip() for x in profile.get("save_commands") if str(x).strip()]
        else:
            if "huawei" in dtype:
                save_cmds = ["save"]
            elif "juniper" in dtype or "junos" in dtype:
                save_cmds = []
            elif "nxos" in dtype or "cisco_nxos" in dtype:
                save_cmds = ["copy running-config startup-config"]
            else:
                save_cmds = ["write memory", "copy running-config startup-config"]

        copy_template = "copy terminal: {path}"
        if isinstance(profile, dict) and str(profile.get("copy_command_template") or "").strip():
            copy_template = str(profile.get("copy_command_template")).strip()

        text = str(raw_config or "")
        if not text.endswith("\n"):
            text += "\n"

        last_error = None
        last_copy_output = None
        last_replace_output = None

        for fs in file_systems:
            path = f"{fs}{suffix}"
            try:
                copy_cmd = copy_template.format(path=path)
                copy_out = self.connection.send_command_timing(copy_cmd, read_timeout=180)
                for _ in range(12):
                    low = str(copy_out or "").lower()
                    if "destination filename" in low or "destination file name" in low:
                        copy_out = self.connection.send_command_timing("\n", read_timeout=180)
                        continue
                    if "address or name of remote host" in low:
                        copy_out = self.connection.send_command_timing("\n", read_timeout=180)
                        continue
                    if "enter" in low and "configuration" in low:
                        break
                    if "[confirm]" in low:
                        copy_out = self.connection.send_command_timing("\n", read_timeout=180)
                        continue
                    break

                chunk: List[str] = []
                for line in text.splitlines():
                    chunk.append(line)
                    if len(chunk) >= 200:
                        self.connection.send_command_timing("\n".join(chunk) + "\n", read_timeout=180)
                        chunk = []
                if chunk:
                    self.connection.send_command_timing("\n".join(chunk) + "\n", read_timeout=180)
                self.connection.send_command_timing("\x1a", read_timeout=180)

                last_copy_output = str(copy_out or "")

                chosen_replace = None
                rep_out = None
                for tmpl in replace_cmds:
                    cmd = tmpl.format(path=path)
                    tmp = self.connection.send_command_timing(cmd, read_timeout=360)
                    for _ in range(12):
                        low = str(tmp or "").lower()
                        if "(y/n)" in low or "[y/n]" in low:
                            tmp = self.connection.send_command_timing("y\n", read_timeout=360)
                            continue
                        if "[confirm]" in low or "confirm" in low or "proceed" in low:
                            tmp = self.connection.send_command_timing("\n", read_timeout=360)
                            continue
                        break
                    if not self._looks_like_cli_error(str(tmp or "")):
                        chosen_replace = cmd
                        rep_out = tmp
                        break
                    last_replace_output = str(tmp or "")

                if not chosen_replace:
                    last_error = last_replace_output or "replace failed"
                    continue

                for s in save_cmds:
                    try:
                        if s == "save" and "huawei" in dtype:
                            self.connection.send_command(s, expect_string=r"[yY]")
                        else:
                            self.connection.send_command(s, read_timeout=120)
                    except Exception:
                        continue

                return {
                    "success": True,
                    "ref": path,
                    "copy_output": last_copy_output,
                    "replace_command": chosen_replace,
                    "replace_output": str(rep_out or ""),
                }
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                continue

        return {"success": False, "ref": None, "error": last_error, "copy_output": last_copy_output, "replace_output": last_replace_output}

    def prepare_rollback(self, snapshot_name: str) -> bool:
        if not self.connection:
            raise ConnectionError("Not connected")
        dtype = str(self.device_type or "").lower()
        if "juniper" in dtype or "junos" in dtype:
            return False
        snap = f"flash:{snapshot_name}.cfg"
        try:
            out = self.connection.send_command_timing(f"copy running-config {snap}", read_timeout=180)
            for _ in range(6):
                low = str(out or "").lower()
                if "destination filename" in low or "destination file name" in low or "[confirm]" in low:
                    out = self.connection.send_command_timing("\n", read_timeout=180)
                    continue
                if "overwrite" in low and ("confirm" in low or "[y/n]" in low or "(y/n)" in low):
                    out = self.connection.send_command_timing("y\n", read_timeout=180)
                    continue
                break
            self._rollback_ref = snap
            return True
        except Exception as e:
            self.last_error = str(e)
            return False

    def rollback(self) -> bool:
        if not self.connection:
            raise ConnectionError("Not connected")
        ref = getattr(self, "_rollback_ref", None)
        if not ref:
            return False
        dtype = str(self.device_type or "").lower()
        try:
            if "nxos" in dtype or "cisco_nxos" in dtype:
                out = self.connection.send_command_timing(f"rollback running-config file {ref}", read_timeout=240)
                for _ in range(6):
                    low = str(out or "").lower()
                    if "(y/n)" in low or "[y/n]" in low:
                        out = self.connection.send_command_timing("y\n", read_timeout=240)
                        continue
                    if "[confirm]" in low or "confirm" in low:
                        out = self.connection.send_command_timing("\n", read_timeout=240)
                        continue
                    break
                try:
                    self.connection.send_command("copy running-config startup-config", read_timeout=120)
                except Exception:
                    pass
            else:
                out = self.connection.send_command_timing(f"configure replace {ref} force", read_timeout=240)
                for _ in range(6):
                    low = str(out or "").lower()
                    if "[confirm]" in low or "proceed" in low or "confirm" in low:
                        out = self.connection.send_command_timing("\n", read_timeout=240)
                        continue
                    break
                try:
                    if "huawei" in dtype:
                        self.connection.send_command("save", expect_string=r"[yY]")
                    else:
                        self.connection.send_command("write memory", read_timeout=60)
                except Exception:
                    pass
            low = str(out or "").lower()
            if "error" in low or "invalid" in low or "failed" in low:
                return False
            return True
        except Exception as e:
            self.last_error = str(e)
            return False

    def get_config(self, source: str = "running") -> str:
        if not self.connection:
            raise ConnectionError("Not connected")

        dtype = str(self.device_type or "").lower()
        source = str(source or "running").lower().strip()

        candidates: List[str] = []
        if "huawei" in dtype:
            candidates = ["display current-configuration", "display saved-configuration", "display configuration"]
        elif "juniper" in dtype:
            candidates = ["show configuration | display set", "show configuration"]
        else:
            if source == "startup":
                candidates = ["show startup-config", "show configuration"]
            else:
                candidates = [
                    "show running-config",
                    "show running",
                    "show config",
                    "show configuration",
                    "display current-configuration",
                ]

        def looks_like_error(out: str) -> bool:
            t = (out or "").lower()
            return any(
                s in t
                for s in (
                    "% invalid",
                    "invalid input",
                    "unknown command",
                    "unrecognized command",
                    "ambiguous command",
                    "incomplete command",
                    "error:",
                )
            )

        best = ""
        for cmd in candidates:
            try:
                out = self.connection.send_command(cmd)
            except Exception:
                continue
            if not out:
                continue
            if looks_like_error(out):
                continue
            if len(out) > len(best):
                best = out

        if best:
            return best

        return self.connection.send_command(candidates[0] if candidates else "show running-config")

    def get_neighbors(self) -> List[Dict[str, Any]]:
        if not self.connection:
            return []

        def _normalize_intf(s: Any) -> str:
            return str(s or "").strip()

        def _normalize_name(s: Any) -> str:
            return str(s or "").strip()

        def _normalize_ip(s: Any) -> str:
            return str(s or "").strip()

        def _as_list(v: Any) -> List[Dict[str, Any]]:
            return v if isinstance(v, list) else []

        def _map_lldp_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            out = []
            for r in rows:
                local_intf = _normalize_intf(r.get("local_interface") or r.get("local_intf") or r.get("local_port") or r.get("local_port_id"))
                neighbor = _normalize_name(r.get("neighbor") or r.get("neighbor_name") or r.get("system_name") or r.get("remote_system_name") or r.get("chassis_id"))
                mgmt_ip = _normalize_ip(
                    r.get("management_ip")
                    or r.get("management_address")
                    or r.get("mgmt_ip")
                    or r.get("mgmt_address")
                    or r.get("remote_mgmt_ip")
                )
                remote_intf = _normalize_intf(
                    r.get("neighbor_interface")
                    or r.get("remote_port")
                    or r.get("port_id")
                    or r.get("port")
                    or r.get("remote_port_id")
                    or r.get("remote_interface")
                    or r.get("neighbor_port_id")
                )
                if local_intf and remote_intf:
                    out.append(
                        {
                            "local_interface": local_intf,
                            "remote_interface": remote_intf,
                            "neighbor_name": neighbor,
                            "mgmt_ip": mgmt_ip,
                            "protocol": "LLDP",
                        }
                    )
            return out

        def _map_cdp_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            out = []
            for r in rows:
                local_intf = _normalize_intf(r.get("local_interface") or r.get("local_port") or r.get("local_intf"))
                neighbor = _normalize_name(r.get("destination_host") or r.get("neighbor") or r.get("neighbor_name") or r.get("device_id") or r.get("platform"))
                mgmt_ip = _normalize_ip(r.get("management_ip") or r.get("mgmt_ip") or r.get("ip") or r.get("dest_ip") or r.get("management_address"))
                remote_intf = _normalize_intf(r.get("remote_interface") or r.get("remote_port") or r.get("port_id") or r.get("interface") or r.get("dest_port"))
                if local_intf and remote_intf:
                    out.append(
                        {
                            "local_interface": local_intf,
                            "remote_interface": remote_intf,
                            "neighbor_name": neighbor,
                            "mgmt_ip": mgmt_ip,
                            "protocol": "CDP",
                        }
                    )
            return out

        def _parse_lldp_raw(raw: str) -> List[Dict[str, Any]]:
            import re

            text = str(raw or "")
            if not text.strip():
                return []
            results: List[Dict[str, Any]] = []
            current: Dict[str, Any] = {}
            in_sys_descr = False
            for ln in text.splitlines():
                line = ln.rstrip("\n")
                s = line.strip()
                if not s:
                    continue

                m = re.match(r"^(Local\s+(Intf|Interface|Port)\s*):\s*(.+)$", s, re.IGNORECASE)
                if m:
                    if current.get("local_interface") and current.get("remote_interface"):
                        results.append(current)
                    current = {"local_interface": m.group(3).strip(), "protocol": "LLDP"}
                    in_sys_descr = False
                    continue

                if ":" in s:
                    k, v = s.split(":", 1)
                    key = k.strip().lower()
                    val = v.strip()
                    if key in ("port id", "portid", "port-id", "remote port", "remote port id"):
                        current["remote_interface"] = val
                        in_sys_descr = False
                    elif key in ("system name", "system-name", "remote system name"):
                        current["neighbor_name"] = val
                        in_sys_descr = False
                    elif key in ("management address", "management ip", "mgmt address", "mgmt ip", "management-address"):
                        current["mgmt_ip"] = val
                        in_sys_descr = False
                    elif key in ("system description", "system descr", "system-description"):
                        current["system_description"] = val
                        in_sys_descr = True
                    else:
                        in_sys_descr = False
                else:
                    if in_sys_descr and current.get("system_description"):
                        current["system_description"] = (str(current.get("system_description") or "") + " " + s).strip()

            if current.get("local_interface") and current.get("remote_interface"):
                results.append(current)
            return results

        def _parse_cdp_raw(raw: str) -> List[Dict[str, Any]]:
            import re

            text = str(raw or "")
            if not text.strip():
                return []

            results: List[Dict[str, Any]] = []
            current: Dict[str, Any] = {}
            for ln in text.splitlines():
                line = ln.rstrip("\n")
                s = line.strip()
                if not s:
                    continue

                if s.lower().startswith("device id:"):
                    if current.get("local_interface") and current.get("remote_interface"):
                        results.append(current)
                    current = {"neighbor_name": s.split(":", 1)[1].strip(), "protocol": "CDP"}
                    continue

                if ":" in s:
                    k, v = s.split(":", 1)
                    key = k.strip().lower()
                    val = v.strip()
                    if key in ("ip address", "management address"):
                        current["mgmt_ip"] = val
                    elif key in ("interface", "local interface"):
                        m = re.match(r"^([^,]+),\s*Port ID\s*\(outgoing port\)\s*:\s*(.+)$", val, re.IGNORECASE)
                        if m:
                            current["local_interface"] = m.group(1).strip()
                            current["remote_interface"] = m.group(2).strip()
                        else:
                            current["local_interface"] = val
                    elif key in ("port id (outgoing port)", "port id"):
                        current["remote_interface"] = val

            if current.get("local_interface") and current.get("remote_interface"):
                results.append(current)
            return results

        neighbors: List[Dict[str, Any]] = []

        lldp_cmds = ["show lldp neighbors detail", "show lldp neighbors"]
        for cmd in lldp_cmds:
            try:
                parsed = self.connection.send_command(cmd, use_textfsm=True)
            except Exception:
                parsed = None
            mapped = _map_lldp_rows(_as_list(parsed))
            if mapped:
                neighbors.extend(mapped)
                break
            try:
                raw = self.connection.send_command(cmd)
            except Exception:
                raw = ""
            mapped_raw = _parse_lldp_raw(raw)
            mapped2 = [
                {
                    "local_interface": _normalize_intf(r.get("local_interface")),
                    "remote_interface": _normalize_intf(r.get("remote_interface")),
                    "neighbor_name": _normalize_name(r.get("neighbor_name")),
                    "mgmt_ip": _normalize_ip(r.get("mgmt_ip")),
                    "protocol": "LLDP",
                }
                for r in mapped_raw
                if r.get("local_interface") and r.get("remote_interface")
            ]
            if mapped2:
                neighbors.extend(mapped2)
                break

        cdp_cmds = ["show cdp neighbors detail"]
        for cmd in cdp_cmds:
            try:
                parsed = self.connection.send_command(cmd, use_textfsm=True)
            except Exception:
                parsed = None
            mapped = _map_cdp_rows(_as_list(parsed))
            if mapped:
                neighbors.extend(mapped)
                break
            try:
                raw = self.connection.send_command(cmd)
            except Exception:
                raw = ""
            mapped_raw = _parse_cdp_raw(raw)
            if mapped_raw:
                neighbors.extend(
                    [
                        {
                            "local_interface": _normalize_intf(r.get("local_interface")),
                            "remote_interface": _normalize_intf(r.get("remote_interface")),
                            "neighbor_name": _normalize_name(r.get("neighbor_name")),
                            "mgmt_ip": _normalize_ip(r.get("mgmt_ip")),
                            "protocol": "CDP",
                        }
                        for r in mapped_raw
                    ]
                )
                break

        seen = set()
        unique = []
        for n in neighbors:
            key = (
                n.get("protocol"),
                n.get("local_interface"),
                n.get("remote_interface"),
                n.get("neighbor_name"),
                n.get("mgmt_ip"),
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(n)
        return unique

    # ================================================================
    # L3 Topology Discovery (OSPF / BGP)
    # ================================================================

    def get_ospf_neighbors(self) -> List[Dict[str, Any]]:
        """
        Collect OSPF neighbor information.
        Tries TextFSM first, falls back to regex parsing.
        """
        if not self.connection:
            return []

        dtype = str(self.device_type or "").lower()

        # Pick command based on vendor
        if "huawei" in dtype:
            cmds = ["display ospf peer brief", "display ospf peer"]
        elif "juniper" in dtype:
            cmds = ["show ospf neighbor"]
        else:
            # Cisco IOS/IOS-XE/NX-OS and most domestic vendors
            cmds = ["show ip ospf neighbor"]

        for cmd in cmds:
            try:
                parsed = self.connection.send_command(cmd, use_textfsm=True)
                if isinstance(parsed, list) and parsed:
                    return self._map_ospf_textfsm(parsed)
            except Exception:
                pass

            # Fallback: raw regex parsing
            try:
                raw = self.connection.send_command(cmd)
                if raw and "invalid" not in raw.lower() and "unknown" not in raw.lower():
                    result = self._parse_ospf_raw(raw)
                    if result:
                        return result
            except Exception:
                continue

        return []

    def _map_ospf_textfsm(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Map TextFSM parsed OSPF neighbors to standard format."""
        out = []
        for r in rows:
            out.append({
                "neighbor_id": str(r.get("neighbor_id") or r.get("router_id") or r.get("rid") or ""),
                "neighbor_ip": str(r.get("address") or r.get("neighbor_ip") or r.get("peer_address") or ""),
                "state": str(r.get("state") or r.get("status") or ""),
                "interface": str(r.get("interface") or r.get("intf") or ""),
                "area": str(r.get("area") or ""),
                "priority": int(r.get("priority") or r.get("pri") or 0),
            })
        return out

    def _parse_ospf_raw(self, raw: str) -> List[Dict[str, Any]]:
        """
        Parse raw 'show ip ospf neighbor' output.
        Typical Cisco format:
        Neighbor ID     Pri   State          Dead Time   Address         Interface
        10.0.0.1          1   FULL/DR        00:00:33    192.168.1.1     GigabitEthernet0/0
        """
        import re
        results = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            # Skip headers
            if line.lower().startswith("neighbor") or line.startswith("-"):
                continue

            # Regex: Router-ID  Pri  State  DeadTime  Address  Interface
            m = re.match(
                r"^(\d+\.\d+\.\d+\.\d+)\s+"     # Neighbor ID
                r"(\d+)\s+"                       # Priority
                r"(\S+)\s+"                       # State (FULL/DR, 2WAY/DROTHER, etc.)
                r"\S+\s+"                         # Dead Time (skip)
                r"(\d+\.\d+\.\d+\.\d+)\s+"       # Address
                r"(\S+)",                         # Interface
                line
            )
            if m:
                results.append({
                    "neighbor_id": m.group(1),
                    "neighbor_ip": m.group(4),
                    "state": m.group(3),
                    "interface": m.group(5),
                    "area": "",
                    "priority": int(m.group(2)),
                })

        return results

    def get_bgp_neighbors(self) -> List[Dict[str, Any]]:
        """
        Collect BGP neighbor information.
        """
        if not self.connection:
            return []

        dtype = str(self.device_type or "").lower()

        if "huawei" in dtype:
            cmds = ["display bgp peer"]
        elif "juniper" in dtype:
            cmds = ["show bgp summary"]
        else:
            cmds = ["show bgp summary", "show ip bgp summary"]

        for cmd in cmds:
            try:
                parsed = self.connection.send_command(cmd, use_textfsm=True)
                if isinstance(parsed, list) and parsed:
                    return self._map_bgp_textfsm(parsed)
            except Exception:
                pass

            try:
                raw = self.connection.send_command(cmd)
                if raw and "invalid" not in raw.lower() and "unknown" not in raw.lower():
                    result = self._parse_bgp_raw(raw)
                    if result:
                        return result
            except Exception:
                continue

        return []

    def _map_bgp_textfsm(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Map TextFSM parsed BGP summary to standard format."""
        out = []
        for r in rows:
            out.append({
                "neighbor_ip": str(r.get("bgp_neigh") or r.get("neighbor") or r.get("neighbor_ip") or ""),
                "remote_as": int(r.get("neigh_as") or r.get("remote_as") or r.get("as") or 0),
                "state": str(r.get("state_pfxrcd") or r.get("state") or r.get("status") or ""),
                "uptime": str(r.get("up_down") or r.get("uptime") or ""),
                "prefixes_received": self._safe_int(r.get("state_pfxrcd") or r.get("prefixes_received")),
                "local_as": int(r.get("local_as") or 0),
            })
        return out

    def _parse_bgp_raw(self, raw: str) -> List[Dict[str, Any]]:
        """
        Parse raw 'show bgp summary' output.
        Typical Cisco format:
        Neighbor        V           AS MsgRcvd MsgSent   TblVer  InQ OutQ Up/Down  State/PfxRcd
        10.0.0.2        4        65002     123     456        5    0    0 01:23:45        10
        """
        import re
        results = []
        local_as = 0

        # Try to extract local AS from header
        as_match = re.search(r"local AS number (\d+)", raw, re.IGNORECASE)
        if as_match:
            local_as = int(as_match.group(1))

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            # Match a BGP neighbor line (starts with IP address)
            m = re.match(
                r"^(\d+\.\d+\.\d+\.\d+)\s+"    # Neighbor IP
                r"\d+\s+"                        # Version (4)
                r"(\d+)\s+"                      # Remote AS
                r"\d+\s+"                        # MsgRcvd
                r"\d+\s+"                        # MsgSent
                r"\d+\s+"                        # TblVer
                r"\d+\s+"                        # InQ
                r"\d+\s+"                        # OutQ
                r"(\S+)\s+"                      # Up/Down
                r"(\S+)",                        # State/PfxRcd
                line
            )
            if m:
                state_pfx = m.group(4)
                pfx = self._safe_int(state_pfx)
                state = state_pfx if pfx == 0 and not state_pfx.isdigit() else "Established"

                results.append({
                    "neighbor_ip": m.group(1),
                    "remote_as": int(m.group(2)),
                    "state": state,
                    "uptime": m.group(3),
                    "prefixes_received": pfx,
                    "local_as": local_as,
                })

        return results

    def _safe_int(self, val) -> int:
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0

    # SWIM/Telemetry - Not implemented for generic
    def transfer_file(self, local_path: str, remote_path: str = None, file_system: str = None) -> bool:
        return False
    def verify_image(self, file_path: str, expected_checksum: str) -> bool:
        return False
    def set_boot_variable(self, file_path: str) -> bool:
        return False
    def reload(self, save_config: bool = True):
        pass
    def get_gnmi_telemetry(self, port: int = 57400) -> Dict[str, Any]:
        return {}
