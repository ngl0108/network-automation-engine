# ansible_config_editor/core/playbook_manager.py
import yaml
from typing import Dict, List, Any


class ConfigManager:
    """
    GUI에서 수집된 구조화된 데이터로부터 OS 유형에 맞는
    Ansible 플레이북을 동적으로 생성하는 핵심 클래스
    """

    def __init__(self):
        self.supported_os_types = [
            "L2_IOS-XE", "L3_IOS-XE",
            "L2_NX-OS", "L3_NX-OS",
            "WLC_AireOS"
        ]

    def generate_playbook(self, os_type: str, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        주어진 OS 유형과 구성 데이터로부터 완전한 Ansible 플레이북을 생성합니다.

        Args:
            os_type: 대상 장비 OS 유형 (예: "L3_IOS-XE")
            config_data: UI에서 수집된 구조화된 구성 데이터

        Returns:
            Ansible이 실행할 수 있는 완전한 플레이북 구조 (딕셔너리)
        """
        if os_type not in self.supported_os_types:
            raise ValueError(f"지원하지 않는 OS 유형입니다: {os_type}")

        # 기본 플레이북 구조 생성
        playbook = {
            'name': f'Standard Configuration for {os_type}',
            'hosts': 'all',
            'gather_facts': 'no',
            'connection': 'network_cli',
            'tasks': []
        }

        # OS별 기본 설정
        if 'IOS-XE' in os_type:
            playbook['vars'] = {
                'ansible_network_os': 'ios',
                'ansible_user': '{{ ansible_user }}',
                'ansible_password': '{{ ansible_password }}'
            }
        elif 'NX-OS' in os_type:
            playbook['vars'] = {
                'ansible_network_os': 'nxos',
                'ansible_user': '{{ ansible_user }}',
                'ansible_password': '{{ ansible_password }}'
            }

        # 모듈별 태스크 생성
        global_tasks = self._generate_global_tasks(os_type, config_data.get('global', {}))
        interface_tasks = self._generate_interface_tasks(os_type, config_data.get('interfaces', {}))
        vlan_tasks = self._generate_vlan_tasks(os_type, config_data.get('vlans', {}))
        routing_tasks = self._generate_routing_tasks(os_type, config_data.get('routing', {}))
        ha_tasks = self._generate_ha_tasks(os_type, config_data.get('ha', {}))
        security_tasks = self._generate_security_tasks(os_type, config_data.get('security', {}))

        # 모든 태스크를 플레이북에 추가
        playbook['tasks'].extend(global_tasks)
        playbook['tasks'].extend(interface_tasks)
        playbook['tasks'].extend(vlan_tasks)
        playbook['tasks'].extend(routing_tasks)
        playbook['tasks'].extend(ha_tasks)
        playbook['tasks'].extend(security_tasks)

        return playbook

    def _generate_global_tasks(self, os_type: str, global_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """글로벌 설정 태스크 생성"""
        tasks = []
        commands = []

        # Hostname 설정
        hostname = global_config.get('hostname', '')
        if hostname:
            commands.append(f"hostname {hostname}")

        # Service 설정
        if global_config.get('service_timestamps', False):
            if 'IOS-XE' in os_type:
                commands.extend([
                    "service timestamps debug datetime msec localtime show-timezone",
                    "service timestamps log datetime msec localtime show-timezone"
                ])
            elif 'NX-OS' in os_type:
                commands.extend([
                    "service timestamps debug",
                    "service timestamps log"
                ])

        if global_config.get('service_password_encryption', False):
            commands.append("service password-encryption")

        # Logging 설정
        for log_host in global_config.get('logging_hosts', []):
            if log_host.get('ip'):
                if log_host.get('vrf'):
                    if 'IOS-XE' in os_type:
                        commands.append(f"logging host {log_host['ip']} vrf {log_host['vrf']}")
                    elif 'NX-OS' in os_type:
                        commands.append(f"logging server {log_host['ip']} use-vrf {log_host['vrf']}")
                else:
                    if 'IOS-XE' in os_type:
                        commands.append(f"logging host {log_host['ip']}")
                    elif 'NX-OS' in os_type:
                        commands.append(f"logging server {log_host['ip']}")

        # NTP 설정
        for ntp_server in global_config.get('ntp_servers', []):
            if ntp_server.get('ip'):
                ntp_cmd = f"ntp server {ntp_server['ip']}"
                if ntp_server.get('prefer'):
                    ntp_cmd += " prefer"
                if ntp_server.get('vrf'):
                    if 'IOS-XE' in os_type:
                        ntp_cmd += f" vrf {ntp_server['vrf']}"
                    elif 'NX-OS' in os_type:
                        ntp_cmd += f" use-vrf {ntp_server['vrf']}"
                commands.append(ntp_cmd)

        # 명령어가 있으면 태스크 생성
        if commands:
            if 'IOS-XE' in os_type:
                tasks.append({
                    'name': 'Configure Global Settings (IOS-XE)',
                    'cisco.ios.ios_config': {
                        'lines': commands
                    }
                })
            elif 'NX-OS' in os_type:
                # NX-OS는 일부 기능을 활성화해야 함
                feature_commands = ["feature ntp"]  # NTP 기능 활성화
                tasks.append({
                    'name': 'Enable required features (NX-OS)',
                    'cisco.nxos.nxos_config': {
                        'lines': feature_commands
                    }
                })
                tasks.append({
                    'name': 'Configure Global Settings (NX-OS)',
                    'cisco.nxos.nxos_config': {
                        'lines': commands
                    }
                })

        return tasks

    def _generate_interface_tasks(self, os_type: str, interface_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """인터페이스 설정 태스크 생성 (기본 구현)"""
        tasks = []

        # 현재는 기본 구조만 제공
        if interface_config.get('description'):
            tasks.append({
                'name': 'Configure Interface Description (Placeholder)',
                'debug': {
                    'msg': f"Interface type: {interface_config.get('type', 'Access')}, "
                           f"Description: {interface_config.get('description')}"
                }
            })

        return tasks

    def _generate_vlan_tasks(self, os_type: str, vlan_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """VLAN 설정 태스크 생성"""
        tasks = []
        commands = []

        # VLAN 생성
        for vlan in vlan_config.get('list', []):
            if vlan.get('id'):
                vlan_id = vlan['id']
                vlan_name = vlan.get('name', f"VLAN{vlan_id}")

                if 'IOS-XE' in os_type:
                    commands.extend([
                        f"vlan {vlan_id}",
                        f" name {vlan_name}"
                    ])
                elif 'NX-OS' in os_type:
                    commands.extend([
                        f"vlan {vlan_id}",
                        f"  name {vlan_name}"
                    ])

        if commands:
            if 'IOS-XE' in os_type:
                tasks.append({
                    'name': 'Configure VLANs (IOS-XE)',
                    'cisco.ios.ios_config': {
                        'lines': commands
                    }
                })
            elif 'NX-OS' in os_type:
                tasks.append({
                    'name': 'Configure VLANs (NX-OS)',
                    'cisco.nxos.nxos_config': {
                        'lines': commands
                    }
                })

        return tasks

    def _generate_routing_tasks(self, os_type: str, routing_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """라우팅 설정 태스크 생성 (향후 구현)"""
        tasks = []

        # 현재는 플레이스홀더만 제공
        tasks.append({
            'name': 'Configure Routing (Placeholder)',
            'debug': {
                'msg': 'Routing configuration will be implemented here'
            }
        })

        return tasks

    def _generate_ha_tasks(self, os_type: str, ha_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """고가용성 설정 태스크 생성 (향후 구현)"""
        tasks = []

        if 'IOS-XE' in os_type:
            tasks.append({
                'name': 'Configure StackWise Virtual (Placeholder)',
                'debug': {
                    'msg': 'StackWise Virtual configuration for IOS-XE'
                }
            })
        elif 'NX-OS' in os_type:
            tasks.append({
                'name': 'Configure vPC (Placeholder)',
                'debug': {
                    'msg': 'vPC configuration for NX-OS'
                }
            })

        return tasks

    def _generate_security_tasks(self, os_type: str, security_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """보안 설정 태스크 생성"""
        tasks = []
        commands = []

        # AAA 설정
        if security_config.get('aaa_new_model', False):
            commands.append("aaa new-model")

        # AAA 서버 그룹
        for aaa_group in security_config.get('aaa_groups', []):
            group_type = aaa_group.get('type', '').lower()
            group_name = aaa_group.get('group_name', '')
            servers = aaa_group.get('servers', [])

            if group_type and group_name and servers:
                if 'IOS-XE' in os_type:
                    if group_type == 'tacacs+':
                        commands.append(f"aaa group server tacacs+ {group_name}")
                        for server in servers:
                            commands.append(f" server {server}")
                    elif group_type == 'radius':
                        commands.append(f"aaa group server radius {group_name}")
                        for server in servers:
                            commands.append(f" server {server}")
                elif 'NX-OS' in os_type:
                    # NX-OS에서는 약간 다른 구문 사용
                    if group_type == 'tacacs+':
                        commands.append(f"aaa group server tacacs+ {group_name}")
                        for server in servers:
                            commands.append(f"  server {server}")

        if commands:
            if 'IOS-XE' in os_type:
                tasks.append({
                    'name': 'Configure Security Settings (IOS-XE)',
                    'cisco.ios.ios_config': {
                        'lines': commands
                    }
                })
            elif 'NX-OS' in os_type:
                # NX-OS는 AAA 기능을 활성화해야 할 수 있음
                if security_config.get('aaa_new_model', False):
                    tasks.append({
                        'name': 'Enable AAA feature (NX-OS)',
                        'cisco.nxos.nxos_config': {
                            'lines': ['feature tacacs+']  # 필요에 따라 radius도 추가
                        }
                    })
                tasks.append({
                    'name': 'Configure Security Settings (NX-OS)',
                    'cisco.nxos.nxos_config': {
                        'lines': commands
                    }
                })

        return tasks

    def export_playbook_to_yaml(self, playbook_data: Dict[str, Any]) -> str:
        """
        생성된 플레이북을 YAML 문자열로 변환합니다.
        파일로 저장하거나 미리보기에 사용할 수 있습니다.
        """
        # 플레이북을 리스트로 감싸야 함 (Ansible 플레이북 형식)
        playbook_list = [playbook_data]
        return yaml.dump(playbook_list, default_flow_style=False, allow_unicode=True, indent=2)