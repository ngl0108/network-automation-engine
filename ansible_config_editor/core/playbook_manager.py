# ansible_config_editor/core/playbook_manager.py
import yaml

class ConfigManager:
    def __init__(self):
        pass

    def generate_playbook(self, os_type, config_data):
        """
        하드코딩된 UI에서 수집된 데이터를 기반으로 Ansible 플레이북을 동적으로 생성합니다.
        """
        tasks =''

        # 각 모듈별로 task 생성 헬퍼 함수 호출
        tasks.extend(self._generate_global_tasks(os_type, config_data.get('global', {})))
        tasks.extend(self._generate_security_tasks(os_type, config_data.get('security', {})))
        #... 다른 모듈에 대한 헬퍼 함수 호출 추가...

        playbook = [{
            'name': f'Apply Generated Config for {os_type}',
            'hosts': 'all',
            'gather_facts': False,
            'connection': 'network_cli',
            'tasks': tasks
        }]
        return playbook

    def _get_config_module(self, os_type):
        """OS 유형에 맞는 Ansible 설정 모듈 이름을 반환합니다."""
        if "IOS-XE" in os_type:
            return "cisco.ios.ios_config"
        elif "NX-OS" in os_type:
            return "cisco.nxos.nxos_config"
        return "cisco.ios.ios_config" # 기본값

    def _generate_global_tasks(self, os_type, global_data):
        tasks =''
        config_module = self._get_config_module(os_type)

        # Hostname
        if global_data.get('hostname'):
            tasks.append({
                'name': 'Global: Set Hostname',
                config_module: {'lines': [f"hostname {global_data['hostname']}"]}
            })

        # Services
        service_lines =''
        if global_data.get('service_timestamps'):
            service_lines.append("service timestamps debug datetime msec localtime show-timezone")
            service_lines.append("service timestamps log datetime msec localtime show-timezone")
        if global_data.get('service_password_encryption'):
            service_lines.append("service password-encryption")
        
        if service_lines:
            tasks.append({
                'name': 'Global: Configure services',
                config_module: {'lines': service_lines}
            })

        # Logging
        if global_data.get('logging_hosts'):
            log_lines = [f"logging host {h['ip']} vrf {h['vrf']}" for h in global_data['logging_hosts']]
            tasks.append({
                'name': 'Global: Configure Logging Hosts',
                config_module: {'lines': log_lines}
            })
            
        # NTP
        if global_data.get('ntp_servers'):
            ntp_lines =''
            for s in global_data['ntp_servers']:
                cmd = f"ntp server vrf {s['vrf']} {s['ip']}"
                if s.get('prefer'):
                    cmd += " prefer"
                ntp_lines.append(cmd)
            tasks.append({
                'name': 'Global: Configure NTP Servers',
                config_module: {'lines': ntp_lines}
            })

        return tasks

    def _generate_security_tasks(self, os_type, security_data):
        tasks =''
        config_module = self._get_config_module(os_type)

        # AAA
        if security_data.get('aaa_new_model'):
            tasks.append({
                'name': 'Security: Enable AAA New-Model',
                config_module: {'lines': ['aaa new-model']}
            })
        
        #... AAA 서버 그룹, ACL, SNMP 등에 대한 Task 생성 로직 추가...

        return tasks