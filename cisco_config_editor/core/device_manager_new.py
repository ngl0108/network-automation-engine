import os
import json
import re
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

# 로깅 설정 (DEBUG)
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    from netmiko import ConnectHandler

    NETMIKO_AVAILABLE = True
except ImportError as e:
    NETMIKO_AVAILABLE = False
    logger.error(f"Error importing netmiko: {e}")


class ConnectionStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    BUSY = "busy"


class DeviceType(Enum):
    CISCO_IOS = "cisco_ios"
    CISCO_IOSXE = "cisco_iosxe"
    CISCO_NXOS = "cisco_nxos"
    CISCO_ASA = "cisco_asa"
    CISCO_IOS_TELNET = "cisco_ios_telnet"


@dataclass
class DeviceInfo:
    name: str
    host: str
    username: str
    password: str
    device_type: str = "cisco_ios"
    port: int = 22
    enable_password: Optional[str] = None
    timeout: int = 60

    def to_dict(self) -> Dict:
        return {
            'name': self.name, 'host': self.host, 'username': self.username,
            'device_type': self.device_type, 'port': self.port, 'timeout': self.timeout
        }


@dataclass
class BackupInfo:
    device_name: str
    timestamp: str
    config: str
    file_path: str

    def save(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        with open(self.file_path, 'w', encoding='utf-8') as f:
            f.write(self.config)
        logger.info(f"Backup saved: {self.file_path}")


class DeviceConnection:
    def __init__(self, device_info: DeviceInfo):
        self.device_info = device_info
        self.connection = None
        self.status = ConnectionStatus.DISCONNECTED
        self.last_error = None
        self.backup_dir = os.path.expanduser("~/.cisco_config_manager/backups")

    def connect(self) -> bool:
        if not NETMIKO_AVAILABLE:
            self.last_error = "Netmiko library not installed"
            self.status = ConnectionStatus.ERROR
            return False

        self.status = ConnectionStatus.CONNECTING
        try:
            device_dict = {
                'device_type': self.device_info.device_type,
                'host': self.device_info.host,
                'username': self.device_info.username,
                'password': self.device_info.password,
                'port': self.device_info.port,
                'timeout': self.device_info.timeout,
                'global_delay_factor': 2
            }
            if self.device_info.enable_password:
                device_dict['secret'] = self.device_info.enable_password

            self.connection = ConnectHandler(**device_dict)
            if self.device_info.enable_password:
                self.connection.enable()

            self.connection.send_command("terminal length 0")
            self.status = ConnectionStatus.CONNECTED
            return True
        except Exception as e:
            self.last_error = f"Connection error: {str(e)}"
            self.status = ConnectionStatus.ERROR
            logger.error(self.last_error)
            return False

    def disconnect(self):
        if self.connection:
            try:
                self.connection.disconnect()
            except:
                pass
            finally:
                self.connection = None
                self.status = ConnectionStatus.DISCONNECTED

    def is_connected(self) -> bool:
        return self.status == ConnectionStatus.CONNECTED and self.connection is not None

    def send_command(self, command: str) -> str:
        if not self.is_connected(): raise ConnectionError("Not connected")
        try:
            self.status = ConnectionStatus.BUSY
            output = self.connection.send_command(command, use_textfsm=False)
            self.status = ConnectionStatus.CONNECTED
            return output
        except Exception as e:
            self.last_error = str(e)
            raise

    def send_config_commands(self, commands: List[str]) -> str:
        if not self.is_connected(): raise ConnectionError("Not connected")
        try:
            self.status = ConnectionStatus.BUSY
            output = self.connection.send_config_set(commands)
            self.status = ConnectionStatus.CONNECTED
            return output
        except Exception as e:
            self.last_error = str(e)
            raise

    def get_running_config(self) -> str:
        return self.send_command("show running-config")

    def backup_config(self, backup_type: str = "running") -> Optional[BackupInfo]:
        try:
            config = self.get_running_config()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"{self.device_info.name}_{backup_type}_{timestamp}.cfg"
            file_path = os.path.join(self.backup_dir, self.device_info.name, file_name)
            backup = BackupInfo(self.device_info.name, timestamp, config, file_path)
            backup.save()
            return backup
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            return None


class ConnectionManager:
    def __init__(self):
        self.connections: Dict[str, DeviceConnection] = {}
        self.device_list: List[DeviceInfo] = []
        self.config_dir = os.path.expanduser("~/.cisco_config_manager")
        self.devices_file = os.path.join(self.config_dir, "devices.json")
        self._load_devices()

    def _load_devices(self):
        if os.path.exists(self.devices_file):
            try:
                with open(self.devices_file, 'r') as f:
                    data = json.load(f)
                    for d in data: self.device_list.append(DeviceInfo(**d))
            except:
                pass

    def save_devices(self):
        os.makedirs(self.config_dir, exist_ok=True)
        data = [d.to_dict() for d in self.device_list]
        with open(self.devices_file, 'w') as f: json.dump(data, f, indent=2)

    def add_device(self, info: DeviceInfo) -> bool:
        if any(d.name == info.name for d in self.device_list): return False
        self.device_list.append(info)
        self.save_devices()
        return True

    def remove_device(self, name: str) -> bool:
        self.disconnect_device(name)
        self.device_list = [d for d in self.device_list if d.name != name]
        self.save_devices()
        return True

    def connect_device(self, name: str, password: str, enable: str = None) -> bool:
        info = next((d for d in self.device_list if d.name == name), None)
        if not info: return False
        info.password = password
        info.enable_password = enable
        conn = DeviceConnection(info)
        if conn.connect():
            self.connections[name] = conn
            return True
        return False

    def disconnect_device(self, name: str):
        if name in self.connections:
            self.connections[name].disconnect()
            del self.connections[name]

    def get_connection(self, name: str) -> Optional[DeviceConnection]:
        return self.connections.get(name)

    def is_connected(self, name: str) -> bool:
        return name in self.connections and self.connections[name].is_connected()

    def disconnect_all(self):
        for c in self.connections.values(): c.disconnect()
        self.connections.clear()

    def get_device_status(self, name: str) -> Dict:
        conn = self.connections.get(name)
        if not conn: return {'connected': False, 'status': 'disconnected'}
        return {
            'connected': conn.is_connected(),
            'status': conn.status.value,
            'last_error': conn.last_error
        }

    def backup_all_devices(self) -> Dict:
        results = {}
        for name, conn in self.connections.items():
            if conn.is_connected(): results[name] = conn.backup_config()
        return results


# -----------------------------------------------------------------------------
# [통합 파서] CLIAnalyzer
# -----------------------------------------------------------------------------
class CLIAnalyzer:
    @staticmethod
    def analyze_multiple_commands(outputs: Dict[str, str]) -> Dict[str, Any]:
        """show run 결과와 show vlan 등 결과를 통합"""
        print("[DEBUG] Analyze Multiple Commands Started (NEW PARSER)")  # 식별용 로그 변경
        config = CLIAnalyzer.analyze_show_run(outputs.get('show run', ''))

        if 'show vlan' in outputs:
            vlan_list = CLIAnalyzer._parse_show_vlan_brief(outputs['show vlan'])
            existing_ids = {v['id'] for v in config['vlans']['list']}
            for v in vlan_list:
                if v['id'] not in existing_ids:
                    config['vlans']['list'].append(v)

        print(f"[DEBUG] Final Parsed Keys: {list(config.keys())}")
        return config

    @staticmethod
    def analyze_show_run(cli_output: str) -> Dict[str, Any]:
        """show run 전체 파싱"""
        # [초기화] UI가 기대하는 모든 키 구조 생성 (필수!)
        analysis = {
            'global': {
                'hostname': '', 'domain_name': '', 'service_timestamps': False,
                'service_password_encryption': False, 'service_call_home': False,
                'dns_servers': [], 'ntp_servers': [], 'logging': {'hosts': []},
                'management': {}, 'banner': {}, 'archive': {}, 'clock': {'timezone': '', 'summer_time': False}
            },
            'interfaces': [],
            'vlans': {'list': [], 'ip_routing': False},
            'routing': {'static_routes': [], 'ospf': {}, 'bgp': {}, 'eigrp': {}, 'rip': {}},
            'switching': {'stp': {}, 'vtp': {}, 'l2_security': {}, 'mac_table': {}},
            'security': {
                'aaa': {'new_model': False}, 'users': [], 'line_console': {}, 'line_vty': {},
                'snmp': {'communities': []}, 'hardening': {}, 'tcp': {}
            },
            'acls': [],
            'ha': {'fhrp': {}, 'glbp': {}, 'svl': {}, 'vpc': {}, 'tracking': {}}
        }

        lines = cli_output.split('\n')

        # --- 1. Global & Basic ---
        analysis['global']['hostname'] = CLIAnalyzer._extract_regex(lines, r'^hostname\s+(\S+)')
        analysis['global']['domain_name'] = CLIAnalyzer._extract_regex(lines, r'^ip domain name\s+(\S+)')
        analysis['global']['service_timestamps'] = 'service timestamps' in cli_output
        analysis['global']['service_password_encryption'] = 'service password-encryption' in cli_output
        analysis['global']['service_call_home'] = 'service call-home' in cli_output
        analysis['vlans']['ip_routing'] = 'ip routing' in cli_output

        # Clock
        clock_line = CLIAnalyzer._extract_regex(lines, r'^clock timezone\s+(.+)')
        if clock_line:
            analysis['global']['clock']['timezone'] = clock_line

        # DNS / NTP / Logging / Banner / Archive
        for line in lines:
            line = line.strip()
            if line.startswith('ip name-server'):
                parts = line.split()
                for part in parts[2:]:
                    analysis['global']['dns_servers'].append({'ip': part, 'vrf': ''})
            elif line.startswith('ntp server'):
                parts = line.split()
                if len(parts) >= 3:
                    is_prefer = 'prefer' in line
                    analysis['global']['ntp_servers'].append({'server': parts[2], 'prefer': is_prefer, 'vrf': ''})
            elif line.startswith('logging host'):
                parts = line.split()
                if len(parts) >= 3:
                    vrf = ''
                    if 'vrf' in line:
                        try:
                            vrf = parts[parts.index('vrf') + 1]
                        except:
                            pass
                    analysis['global']['logging']['hosts'].append({'ip': parts[2], 'vrf': vrf})
            elif line.startswith('banner motd') or line.startswith('banner login'):
                analysis['global']['banner']['enabled'] = True
                analysis['global']['banner']['text'] = line
            elif line.startswith('archive'):
                analysis['global']['archive']['enabled'] = True

        # --- 2. Interfaces ---
        interface_blocks = CLIAnalyzer._extract_blocks(lines, r'^interface\s+')
        analysis['interfaces'] = CLIAnalyzer._parse_interfaces(interface_blocks)

        # --- 3. Switching ---
        stp_mode = CLIAnalyzer._extract_regex(lines, r'^spanning-tree mode\s+(\S+)')
        analysis['switching']['stp'] = {'mode': stp_mode or 'pvst'}

        vtp_ver = CLIAnalyzer._extract_regex(lines, r'^vtp version\s+(\d+)')
        analysis['switching']['vtp'] = {'version': vtp_ver, 'mode': 'transparent'}

        # --- 4. Security ---
        analysis['security']['aaa']['new_model'] = 'aaa new-model' in cli_output
        analysis['security']['aaa']['authentication_login'] = CLIAnalyzer._extract_regex(lines,
                                                                                         r'^aaa authentication login\s+(.+)')
        analysis['security']['aaa']['authorization_exec'] = CLIAnalyzer._extract_regex(lines,
                                                                                       r'^aaa authorization exec\s+(.+)')
        analysis['security']['aaa']['accounting'] = CLIAnalyzer._extract_regex(lines, r'^aaa accounting exec\s+(.+)')

        # Users & SNMP
        for line in lines:
            if line.startswith('username '):
                m = re.match(r'username\s+(\S+)\s+privilege\s+(\d+)', line)
                if m:
                    analysis['security']['users'].append({'username': m.group(1), 'privilege': m.group(2)})
                else:
                    m2 = re.match(r'username\s+(\S+)', line)
                    if m2:
                        analysis['security']['users'].append({'username': m2.group(1), 'privilege': '1'})

            if line.startswith('snmp-server host'):
                parts = line.split()
                if len(parts) >= 3:
                    analysis['security']['snmp']['communities'].append({
                        'string': parts[2], 'permission': 'Host', 'acl': ''
                    })
            elif line.startswith('snmp-server community'):
                parts = line.split()
                if len(parts) >= 3:
                    comm_str = parts[2]
                    perm = parts[3] if len(parts) > 3 else 'RO'
                    analysis['security']['snmp']['communities'].append({
                        'string': comm_str, 'permission': perm, 'acl': ''
                    })

        # Lines
        con_block = CLIAnalyzer._extract_blocks(lines, r'^line con')
        if con_block:
            analysis['security']['line_console'] = CLIAnalyzer._parse_line_block(con_block[0])

        vty_blocks = CLIAnalyzer._extract_blocks(lines, r'^line vty')
        if vty_blocks:
            analysis['security']['line_vty'] = CLIAnalyzer._parse_line_block(vty_blocks[0])

        # Hardening
        analysis['security']['hardening']['no_ip_http'] = 'no ip http server' in cli_output
        analysis['security']['hardening']['no_cdp'] = 'no cdp run' in cli_output

        # --- 5. ACLs ---
        analysis['acls'] = CLIAnalyzer._parse_acls_full(lines)

        # --- 6. Routing ---
        gw = CLIAnalyzer._extract_regex(lines, r'^ip default-gateway\s+(\S+)')
        if gw:
            analysis['routing']['static_routes'].append({
                'network': '0.0.0.0', 'mask': '0.0.0.0', 'next_hop': gw, 'metric': '1', 'vrf': ''
            })

        for line in lines:
            if line.startswith('ip route '):
                parts = line.split()
                if len(parts) >= 5:
                    analysis['routing']['static_routes'].append({
                        'network': parts[2], 'mask': parts[3], 'next_hop': parts[4], 'metric': '1', 'vrf': ''
                    })

        # --- 7. VLAN Inference (SVI) ---
        for iface in analysis['interfaces']:
            if iface['name'].startswith('Vlan'):
                vid = iface['name'].replace('Vlan', '')
                if vid.isdigit():
                    existing = next((v for v in analysis['vlans']['list'] if v['id'] == vid), None)
                    if existing:
                        existing['svi_enabled'] = True
                        existing['svi_ip'] = iface.get('routed_ip', '')
                    else:
                        analysis['vlans']['list'].append({
                            'id': vid,
                            'name': iface.get('description', f'VLAN{vid}'),
                            'svi_enabled': True,
                            'svi_ip': iface.get('routed_ip', '')
                        })

        return analysis

    @staticmethod
    def _extract_regex(lines: List[str], pattern: str) -> str:
        for line in lines:
            match = re.search(pattern, line)
            if match: return match.group(1)
        return ""

    @staticmethod
    def _extract_blocks(lines: List[str], start_pattern: str) -> List[List[str]]:
        blocks = []
        current_block = []
        in_block = False
        for line in lines:
            stripped = line.strip()
            if re.match(start_pattern, line):
                if current_block: blocks.append(current_block)
                current_block = [stripped]
                in_block = True
            elif in_block:
                if line.startswith(' ') or line.startswith('\t'):
                    current_block.append(stripped)
                elif stripped == '!':
                    in_block = False
                    blocks.append(current_block)
                    current_block = []
                elif not line.startswith(' '):
                    in_block = False
                    blocks.append(current_block)
                    current_block = []
        if current_block: blocks.append(current_block)
        return blocks

    @staticmethod
    def _parse_interfaces(blocks: List[List[str]]) -> List[Dict]:
        interfaces = []
        for block in blocks:
            if not block: continue

            name = block[0].replace('interface ', '').strip()
            iface = {
                'name': name, 'description': '', 'shutdown': False,
                'mode': 'access', 'access_vlan': '', 'trunk_allowed': '',
                'routed_ip': ''
            }

            for line in block[1:]:
                if line.startswith('description '):
                    iface['description'] = line[12:].strip()
                elif line == 'shutdown':
                    iface['shutdown'] = True
                elif line.startswith('switchport access vlan'):
                    iface['access_vlan'] = line.split()[-1]
                    iface['mode'] = 'L2 Access'
                elif line.startswith('switchport mode trunk'):
                    iface['mode'] = 'L2 Trunk'
                elif line.startswith('switchport trunk allowed vlan'):
                    iface['trunk_allowed'] = line.replace('switchport trunk allowed vlan', '').strip()
                elif line.startswith('ip address'):
                    parts = line.split()
                    if len(parts) >= 4:
                        iface['routed_ip'] = f"{parts[2]} {parts[3]}"
                        iface['mode'] = 'L3 Routed'

            interfaces.append(iface)
        return interfaces

    @staticmethod
    def _parse_acls_full(lines: List[str]) -> List[Dict]:
        acls = []
        current_acl = {}
        in_acl = False

        for line in lines:
            line_raw = line
            stripped = line.strip()

            if stripped.startswith('ip access-list'):
                if current_acl: acls.append(current_acl)
                parts = stripped.split()
                if len(parts) >= 4:
                    in_acl = True
                    acl_type = parts[2].capitalize()
                    name = parts[3]
                    current_acl = {'name': name, 'type': acl_type, 'description': '', 'rules': []}
            elif in_acl:
                if line_raw.startswith(' ') or line_raw.startswith('\t'):
                    parts = stripped.split()
                    rule = {'seq': '', 'action': 'permit', 'protocol': 'ip', 'src_ip': 'any', 'dst_ip': 'any',
                            'options': ''}
                    idx = 0
                    if parts[0].isdigit():
                        rule['seq'] = parts[0]
                        idx = 1
                    if idx < len(parts): rule['action'] = parts[idx]
                    if len(parts) > idx + 1: rule['options'] = " ".join(parts[idx + 1:])
                    current_acl['rules'].append(rule)
                else:
                    in_acl = False
                    if current_acl: acls.append(current_acl)
                    current_acl = {}

        if current_acl: acls.append(current_acl)
        return acls

    @staticmethod
    def _parse_line_block(lines: List[str]) -> Dict:
        config = {'range': '', 'exec_timeout': '', 'logging_synchronous': False, 'transport_input': '',
                  'access_class': ''}
        if lines and lines[0].startswith('line'):
            parts = lines[0].split()
            if len(parts) >= 3: config['range'] = " ".join(parts[2:])
        for line in lines[1:]:
            if line.startswith('exec-timeout'):
                config['exec_timeout'] = line.replace('exec-timeout ', '').strip()
            elif line == 'logging synchronous':
                config['logging_synchronous'] = True
            elif line.startswith('transport input'):
                config['transport_input'] = line.split()[-1]
            elif line.startswith('access-class'):
                config['access_class'] = line.split()[1]
        return config

    @staticmethod
    def _parse_show_vlan_brief(output: str) -> List[Dict]:
        vlans = []
        lines = output.split('\n')
        for line in lines:
            parts = line.split()
            if len(parts) >= 2 and parts[0].isdigit():
                vlans.append({
                    'id': parts[0],
                    'name': parts[1],
                    'description': ''
                })
        return vlans


class CiscoCommandGenerator:
    def generate_commands(self, original: Dict, modified: Dict) -> List[str]:
        return ["configure terminal", "! Commands generated", "end"]


class DeploymentManager:
    def __init__(self, connection_manager):
        self.cm = connection_manager

    def validate_commands(self, cmds): return True, []

    def rollback(self, device): return {'success': False}