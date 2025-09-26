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
            "L2_NX-OS", "L3_NX-OS"
        ]

    def generate_playbook(self, os_type: str, config_data: Dict[str, Any]) -> Dict[str, Any]:
        playbook = {
            'name': f'Standard Configuration for {os_type}',
            'hosts': 'all',
            'gather_facts': 'no',
            'connection': 'network_cli',
            'tasks': []
        }
        if 'IOS-XE' in os_type:
            playbook['vars'] = {'ansible_network_os': 'ios', 'ansible_user': '{{ ansible_user }}',
                                'ansible_password': '{{ ansible_password }}'}
        elif 'NX-OS' in os_type:
            playbook['vars'] = {'ansible_network_os': 'nxos', 'ansible_user': '{{ ansible_user }}',
                                'ansible_password': '{{ ansible_password }}'}

        playbook['tasks'].extend(self._generate_global_tasks(os_type, config_data.get('global', {})))
        playbook['tasks'].extend(self._generate_vlan_tasks(os_type, config_data.get('vlans', {})))
        playbook['tasks'].extend(self._generate_switching_tasks(os_type, config_data.get('switching', {})))
        playbook['tasks'].extend(self._generate_interface_tasks(os_type, config_data.get('interfaces', [])))
        playbook['tasks'].extend(self._generate_routing_tasks(os_type, config_data.get('routing', {})))
        playbook['tasks'].extend(self._generate_ha_tasks(os_type, config_data.get('ha', {})))
        playbook['tasks'].extend(self._generate_security_tasks(os_type, config_data.get('security', {})))

        return playbook

    def _prefix_to_netmask(self, prefix: int) -> str:
        if not 0 <= prefix <= 32: return "255.255.255.0"
        bits = 0xffffffff ^ (1 << (32 - prefix)) - 1
        return f"{(bits >> 24) & 0xff}.{(bits >> 16) & 0xff}.{(bits >> 8) & 0xff}.{bits & 0xff}"

    def _netmask_to_prefix(self, netmask: str) -> str:
        return str(sum(bin(int(x)).count('1') for x in netmask.split('.')))

    def _generate_global_tasks(self, os_type: str, global_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        tasks = []
        commands = []
        if global_config.get('hostname'): commands.append(f"hostname {global_config['hostname']}")
        if global_config.get('service_timestamps'): commands.extend(
            ["service timestamps debug datetime msec localtime show-timezone",
             "service timestamps log datetime msec localtime show-timezone"] if 'IOS-XE' in os_type else [
                "service timestamps debug", "service timestamps log"])
        if global_config.get('service_password_encryption'): commands.append("service password-encryption")
        if global_config.get('service_call_home'): commands.append("no service call-home")
        if global_config.get('domain_name'): commands.append(
            f"ip domain name {global_config['domain_name']}" if 'IOS-XE' in os_type else f"ip domain-name {global_config['domain_name']}")
        for dns in global_config.get('dns_servers', []):
            if dns.get('ip'):
                if dns.get('vrf'):
                    commands.append(
                        f"ip name-server vrf {dns['vrf']} {dns['ip']}" if 'IOS-XE' in os_type else f"ip name-server {dns['ip']} use-vrf {dns['vrf']}")
                else:
                    commands.append(f"ip name-server {dns['ip']}")
        timezone = global_config.get('timezone', '')
        if timezone:
            parts = timezone.split()
            if len(parts) >= 2: tz_name, offset = parts[0], parts[1]; commands.append(
                f"clock timezone {tz_name} {offset}" if 'IOS-XE' in os_type else f"clock timezone {tz_name} {offset} 0")
        summer_time = global_config.get('summer_time', {})
        if summer_time.get('enabled') and summer_time.get('zone'): commands.append(
            f"clock summer-time {summer_time['zone']} recurring")
        if global_config.get('logging_level'):
            level_num = global_config['logging_level'].split('(')[1].split(')')[0] if '(' in global_config[
                'logging_level'] else '6'
            commands.append(f"logging trap {level_num}" if 'IOS-XE' in os_type else f"logging level {level_num}")
        if global_config.get('logging_console'): commands.append("logging console")
        if global_config.get('logging_buffered'): commands.append(
            f"logging buffered {global_config.get('logging_buffer_size', '32000')}")
        for log_host in global_config.get('logging_hosts', []):
            if log_host.get('ip'):
                if log_host.get('vrf'):
                    commands.append(
                        f"logging host {log_host['ip']} vrf {log_host['vrf']}" if 'IOS-XE' in os_type else f"logging server {log_host['ip']} use-vrf {log_host['vrf']}")
                else:
                    commands.append(
                        f"logging host {log_host['ip']}" if 'IOS-XE' in os_type else f"logging server {log_host['ip']}")
        if global_config.get('ntp_authenticate'): commands.append("ntp authenticate")
        if global_config.get('ntp_master_stratum'): commands.append(f"ntp master {global_config['ntp_master_stratum']}")
        for ntp in global_config.get('ntp_servers', []):
            if ntp.get('ip'):
                cmd = f"ntp server {ntp['ip']}"
                if ntp.get('key_id'): cmd += f" key {ntp['key_id']}"
                if ntp.get('prefer'): cmd += " prefer"
                if ntp.get('vrf'): cmd += f" vrf {ntp['vrf']}" if 'IOS-XE' in os_type else f" use-vrf {ntp['vrf']}"
                commands.append(cmd)
        mgmt = global_config.get('management', {})
        if mgmt.get('interface') and mgmt.get('ip'):
            if 'IOS-XE' in os_type:
                commands.extend(
                    [f"interface {mgmt['interface']}", f"ip address {mgmt['ip']} {mgmt.get('subnet', '255.255.255.0')}",
                     "no shutdown"])
                if mgmt.get('vrf'): commands.insert(-2, f"vrf forwarding {mgmt['vrf']}")
            elif 'NX-OS' in os_type:
                commands.extend([f"interface {mgmt['interface']}",
                                 f"ip address {mgmt['ip']}/{self._netmask_to_prefix(mgmt.get('subnet', '255.255.255.0'))}",
                                 "no shutdown"])
                if mgmt.get('vrf'): commands.insert(-2, f"vrf member {mgmt['vrf']}")
            if mgmt.get('gateway'):
                if mgmt.get('vrf'):
                    if 'IOS-XE' in os_type:
                        commands.append(f"ip route vrf {mgmt['vrf']} 0.0.0.0 0.0.0.0 {mgmt['gateway']}")
                    elif 'NX-OS' in os_type:
                        commands.extend([f"vrf context {mgmt['vrf']}", f"ip route 0.0.0.0/0 {mgmt['gateway']}"])
                else:
                    commands.append(f"ip route 0.0.0.0 0.0.0.0 {mgmt['gateway']}")
        banner = global_config.get('banner', {})
        if banner.get('enabled') and banner.get('text'): commands.append(
            f"banner login ^{banner['text'].replace(chr(10), '^C')}^C")
        archive = global_config.get('archive', {})
        if archive.get('enabled'):
            commands.append("archive")
            if archive.get('path'): commands.append(f" path {archive['path']}")
            if archive.get('max_files'): commands.append(f" maximum {archive['max_files']}")
            if archive.get('time_period_enabled') and archive.get('time_period'): commands.append(
                f" time-period {archive['time_period']}")
        if commands:
            module = 'cisco.ios.ios_config' if 'IOS-XE' in os_type else 'cisco.nxos.nxos_config'
            tasks.append({'name': 'Configure Global Settings', module: {'lines': commands}})
        return tasks

    def _generate_vlan_tasks(self, os_type: str, vlan_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        tasks = [];
        commands = [];
        svi_commands = []
        if vlan_config.get('enable_routing'):
            if 'IOS-XE' in os_type:
                commands.append("ip routing")
            elif 'NX-OS' in os_type:
                commands.append("feature interface-vlan")
        for vlan in vlan_config.get('list', []):
            if not vlan.get('id'): continue
            vlan_id = vlan['id'];
            vlan_name = vlan.get('name', f"VLAN{vlan_id}")
            commands.extend([f"vlan {vlan_id}", f" name {vlan_name}"])
            svi_data = vlan.get('svi', {})
            if svi_data.get('enabled'):
                svi_cmds_per_interface = [f"interface Vlan{vlan_id}"]
                if vlan.get('description'): svi_cmds_per_interface.append(f" description {vlan.get('description')}")
                if svi_data.get('ip'):
                    ip, prefix = svi_data['ip'].split('/');
                    netmask = self._prefix_to_netmask(int(prefix))
                    if 'IOS-XE' in os_type:
                        svi_cmds_per_interface.append(f" ip address {ip} {netmask}")
                    elif 'NX-OS' in os_type:
                        svi_cmds_per_interface.append(f" ip address {svi_data['ip']}")
                fhrp_data = svi_data.get('fhrp', {})
                if fhrp_data.get('enabled') and fhrp_data.get('group') and fhrp_data.get('vip'):
                    group = fhrp_data['group'];
                    vip = fhrp_data['vip'];
                    priority = fhrp_data.get('priority')
                    if 'IOS-XE' in os_type:
                        svi_cmds_per_interface.append(f" vrrp {group} ip {vip}")
                        if priority: svi_cmds_per_interface.append(f" vrrp {group} priority {priority}")
                        if fhrp_data.get('preempt'): svi_cmds_per_interface.append(f" vrrp {group} preempt")
                    elif 'NX-OS' in os_type:
                        if 'hsrp' not in ' '.join(commands): commands.append("feature hsrp")
                        svi_cmds_per_interface.extend([f" hsrp version 2", f" hsrp {group}", f"  ip {vip}"])
                        if priority: svi_cmds_per_interface.append(f"  priority {priority}")
                        if fhrp_data.get('preempt'): svi_cmds_per_interface.append("  preempt")
                for helper in svi_data.get('dhcp_helpers', []): svi_cmds_per_interface.append(
                    f" ip helper-address {helper}")
                svi_cmds_per_interface.append(" no shutdown");
                svi_commands.extend(svi_cmds_per_interface)
        if commands or svi_commands:
            final_commands = commands + svi_commands
            module = 'cisco.ios.ios_config' if 'IOS-XE' in os_type else 'cisco.nxos.nxos_config'
            tasks.append({'name': 'Configure VLANs and SVIs', module: {'lines': final_commands}})
        return tasks

    def _generate_switching_tasks(self, os_type: str, switching_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        tasks = [];
        commands = []
        vtp_config = switching_config.get('vtp', {})
        if vtp_config.get('enabled') and vtp_config.get('domain'):
            if 'IOS-XE' in os_type:
                commands.extend(
                    [f"vtp mode {vtp_config.get('mode', 'transparent')}", f"vtp domain {vtp_config['domain']}"])
                if vtp_config.get('password'): commands.append(f"vtp password {vtp_config['password']}")
                if vtp_config.get('version'): commands.append(f"vtp version {vtp_config['version']}")
        stp_mode = switching_config.get('stp_mode')
        if stp_mode: commands.append(f"spanning-tree mode {stp_mode}")
        if switching_config.get('stp_priority'): commands.append(
            f"spanning-tree vlan 1-4094 priority {switching_config['stp_priority']}")
        if switching_config.get('stp_portfast_default'): commands.append("spanning-tree portfast default")
        if switching_config.get('stp_bpduguard_default'): commands.append("spanning-tree portfast bpduguard default")
        if switching_config.get('stp_bpdufilter_default'): commands.append("spanning-tree portfast bpdufilter default")
        if switching_config.get('stp_loopguard_default'): commands.append("spanning-tree loopguard default")
        if stp_mode == 'mst':
            mst_config = switching_config.get('mst', {})
            if mst_config.get('name') and mst_config.get('revision'):
                commands.append("spanning-tree mst configuration")
                commands.append(f" name {mst_config['name']}")
                commands.append(f" revision {mst_config['revision']}")
                for inst in mst_config.get('instances', []):
                    if inst.get('id') and inst.get('vlans'): commands.append(
                        f" instance {inst['id']} vlan {inst['vlans']}")
        l2_sec = switching_config.get('l2_security', {})
        if l2_sec.get('dhcp_snooping_enabled'):
            if 'IOS-XE' in os_type:
                commands.append("ip dhcp snooping")
                if l2_sec.get('dhcp_snooping_vlans'): commands.append(
                    f"ip dhcp snooping vlan {l2_sec['dhcp_snooping_vlans']}")
            elif 'NX-OS' in os_type:
                commands.append("feature dhcp snooping")
        if l2_sec.get('dai_vlans'):
            if 'IOS-XE' in os_type:
                commands.append(f"ip arp inspection vlan {l2_sec['dai_vlans']}")
            elif 'NX-OS' in os_type:
                commands.append("feature arp-inspection")
        if commands:
            module = 'cisco.ios.ios_config' if 'IOS-XE' in os_type else 'cisco.nxos.nxos_config'
            tasks.append({'name': 'Configure Advanced Switching Settings', module: {'lines': commands}})
        return tasks

    def _generate_interface_tasks(self, os_type: str, interface_configs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        tasks = []
        if not interface_configs: return tasks
        parents_list = []
        for config in interface_configs:
            if not config.get('is_port_channel'): continue
            lines = []
            if config.get('description'): lines.append(f"description {config['description']}")
            lines.append("shutdown" if config.get('shutdown') else "no shutdown")
            mode = config.get('mode', '')
            if mode == "L2 Access":
                lines.extend(["switchport", f"switchport mode access"])
                if config['access'].get('vlan'): lines.append(f"switchport access vlan {config['access']['vlan']}")
                if config['access'].get('voice_vlan'): lines.append(
                    f"switchport voice vlan {config['access']['voice_vlan']}")
            elif mode == "L2 Trunk":
                lines.append("switchport")
                if 'IOS-XE' in os_type: lines.append("switchport trunk encapsulation dot1q")
                lines.append("switchport mode trunk")
                if config['trunk'].get('native_vlan'): lines.append(
                    f"switchport trunk native vlan {config['trunk']['native_vlan']}")
                if config['trunk'].get('allowed_vlans'): lines.append(
                    f"switchport trunk allowed vlan {config['trunk']['allowed_vlans']}")
            elif mode == "L3 Routed":
                lines.append("no switchport")
                if config['routed'].get('ip'):
                    ip, prefix = config['routed']['ip'].split('/');
                    netmask = self._prefix_to_netmask(int(prefix))
                    lines.append(f"ip address {ip} {netmask}")
            parents_list.append({'parents': f"interface {config['name']}", 'lines': lines})
        for config in interface_configs:
            if config.get('is_port_channel'): continue
            lines = []
            if config.get('description'): lines.append(f"description {config['description']}")
            lines.append("shutdown" if config.get('shutdown') else "no shutdown")
            mode = config.get('mode', '')
            if "L2" in mode:
                lines.append("switchport")
                if 'IOS-XE' in os_type and mode == "L2 Trunk": lines.append("switchport trunk encapsulation dot1q")
                if mode == "L2 Access":
                    lines.append("switchport mode access")
                    if config['access'].get('vlan'): lines.append(f"switchport access vlan {config['access']['vlan']}")
                    if config['access'].get('voice_vlan'): lines.append(
                        f"switchport voice vlan {config['access']['voice_vlan']}")
                else:  # L2 Trunk
                    lines.append("switchport mode trunk")
                    if config['trunk'].get('native_vlan'): lines.append(
                        f"switchport trunk native vlan {config['trunk']['native_vlan']}")
                    if config['trunk'].get('allowed_vlans'): lines.append(
                        f"switchport trunk allowed vlan {config['trunk']['allowed_vlans']}")
                if config['stp'].get('portfast'): lines.append("spanning-tree portfast")
                if config['stp'].get('bpduguard'): lines.append("spanning-tree bpduguard enable")
                ps = config.get('port_security', {})
                if ps.get('enabled'):
                    lines.extend(
                        [f"switchport port-security", f"switchport port-security maximum {ps.get('max_mac', '1')}",
                         f"switchport port-security violation {ps.get('violation', 'shutdown')}"])
                sc = config.get('storm_control', {})
                if sc.get('broadcast'): lines.append(f"storm-control broadcast level {sc['broadcast']}")
                if sc.get('multicast'): lines.append(f"storm-control multicast level {sc['multicast']}")
                if sc.get('unicast'): lines.append(f"storm-control unicast level {sc['unicast']}")
                if any([sc.get('broadcast'), sc.get('multicast'), sc.get('unicast')]): lines.append(
                    f"storm-control action {sc.get('action', 'shutdown')}")
            elif mode == "L3 Routed":
                lines.append("no switchport")
                if config['routed'].get('ip'): ip, prefix = config['routed']['ip'].split(
                    '/'); netmask = self._prefix_to_netmask(int(prefix)); lines.append(f"ip address {ip} {netmask}")
            elif mode == "Port-Channel Member":
                pc = config.get('pc_member', {})
                if pc.get('group_id'): lines.append(f"channel-group {pc['group_id']} mode {pc.get('mode', 'active')}")
            udld = config.get('udld', {})
            if udld.get('enabled') and config.get('type') == 'Fiber': lines.append(
                f"udld port {udld.get('mode', 'normal')}")
            parents_list.append({'parents': f"interface {config['name']}", 'lines': lines})
        if parents_list:
            module = 'cisco.ios.ios_config' if 'IOS-XE' in os_type else 'cisco.nxos.nxos_config'
            tasks.append(
                {'name': 'Configure Interfaces', module: {'parents': "{{ item.parents }}", 'lines': "{{ item.lines }}"},
                 'loop': parents_list})
        return tasks

    def _generate_routing_tasks(self, os_type: str, routing_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        tasks = [];
        commands = []
        for route in routing_config.get('static_routes', []):
            if route.get('prefix') and route.get('nexthop'):
                parts = route['prefix'].split('/');
                prefix, mask = parts[0], self._prefix_to_netmask(int(parts[1]))
                cmd = "ip route"
                if route.get('vrf'): cmd += f" vrf {route['vrf']}"
                cmd += f" {prefix} {mask} {route['nexthop']}"
                if route.get('metric'): cmd += f" {route['metric']}"
                commands.append(cmd)
        ospf = routing_config.get('ospf', {})
        if ospf.get('enabled') and ospf.get('process_id'):
            if 'NX-OS' in os_type: commands.append("feature ospf")
            commands.append(f"router ospf {ospf['process_id']}")
            if ospf.get('router_id'): commands.append(f" router-id {ospf['router_id']}")
            for net in ospf.get('networks', []):
                if net.get('prefix') and net.get('wildcard') and net.get('area'): commands.append(
                    f" network {net['prefix']} {net['wildcard']} area {net['area']}")
        eigrp = routing_config.get('eigrp', {})
        if eigrp.get('enabled') and eigrp.get('as_number'):
            if 'NX-OS' in os_type: commands.append("feature eigrp")
            commands.append(f"router eigrp {eigrp['as_number']}")
            if eigrp.get('router_id') and 'IOS-XE' in os_type: commands.append(f" eigrp router-id {eigrp['router_id']}")
            for net in eigrp.get('networks', []):
                if net.get('prefix'):
                    cmd = f" network {net['prefix']}"
                    if net.get('wildcard'): cmd += f" {net['wildcard']}"
                    commands.append(cmd)
        bgp = routing_config.get('bgp', {})
        if bgp.get('enabled') and bgp.get('as_number'):
            if 'NX-OS' in os_type: commands.append("feature bgp")
            commands.append(f"router bgp {bgp['as_number']}")
            if bgp.get('router_id'): commands.append(f" bgp router-id {bgp['router_id']}")
            for neighbor in bgp.get('neighbors', []):
                if neighbor.get('ip') and neighbor.get('remote_as'):
                    commands.append(f" neighbor {neighbor['ip']} remote-as {neighbor['remote_as']}")
                    if neighbor.get('description'): commands.append(
                        f" neighbor {neighbor['ip']} description {neighbor['description']}")
                    if neighbor.get('update_source'): commands.append(
                        f" neighbor {neighbor['ip']} update-source {neighbor['update_source']}")
                    if neighbor.get('rmap_in'): commands.append(
                        f" neighbor {neighbor['ip']} route-map {neighbor['rmap_in']} in")
                    if neighbor.get('rmap_out'): commands.append(
                        f" neighbor {neighbor['ip']} route-map {neighbor['rmap_out']} out")
            for net in bgp.get('networks', []): commands.append(f" network {net}")
        if commands:
            module = 'cisco.ios.ios_config' if 'IOS-XE' in os_type else 'cisco.nxos.nxos_config'
            tasks.append({'name': 'Configure Routing Protocols', module: {'lines': commands}})
        return tasks

    def _generate_ha_tasks(self, os_type: str, ha_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        tasks = [];
        commands = []
        if 'IOS-XE' in os_type:
            svl_config = ha_config.get('svl', {})
            if svl_config.get('enabled') and svl_config.get('domain'):
                commands.extend([f"stackwise-virtual", f" domain {svl_config['domain']}"])
                if commands: tasks.append(
                    {'name': 'Configure StackWise Virtual (IOS-XE)', 'cisco.ios.ios_config': {'lines': commands}})
        elif 'NX-OS' in os_type:
            vpc_config = ha_config.get('vpc', {})
            if vpc_config.get('enabled') and vpc_config.get('domain'):
                tasks.append(
                    {'name': 'Enable vPC feature (NX-OS)', 'cisco.nxos.nxos_config': {'lines': ['feature vpc']}})
                commands.append(f"vpc domain {vpc_config['domain']}")
                if vpc_config.get('peer_keepalive'): commands.append(f" peer-keepalive {vpc_config['peer_keepalive']}")
                if commands: tasks.append(
                    {'name': 'Configure vPC (NX-OS)', 'cisco.nxos.nxos_config': {'lines': commands}})
        return tasks

    def _generate_security_tasks(self, os_type: str, security_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        tasks = [];
        commands = []
        module = 'cisco.ios.ios_config' if 'IOS-XE' in os_type else 'cisco.nxos.nxos_config'
        for user in security_config.get('local_users', []):
            if user.get('username') and user.get('password'): commands.append(
                f"username {user['username']} privilege {user.get('privilege', '1')} secret {user['password']}")
        if security_config.get('aaa_new_model'): commands.append("aaa new-model")
        if security_config.get('aaa_auth_login'): commands.append(
            f"aaa authentication login {security_config['aaa_auth_login']}")
        if security_config.get('aaa_auth_exec'): commands.append(
            f"aaa authorization exec {security_config['aaa_auth_exec']}")
        for group in security_config.get('aaa_groups', []):
            if group.get('group_name') and group.get('servers'):
                commands.append(f"aaa group server {group.get('type', 'tacacs+')} {group['group_name']}")
                for server in group['servers']: commands.append(
                    f" server-private {server}" if 'IOS-XE' in os_type and group.get(
                        'type') == 'tacacs+' else f" server {server}")
        line_conf = security_config.get('line_config', {})
        if line_conf:
            commands.append("line con 0")
            if line_conf.get('con_timeout'): commands.append(f" exec-timeout {line_conf['con_timeout']}")
            if line_conf.get('con_logging_sync'): commands.append(" logging synchronous")
            if line_conf.get('con_auth_aaa') and line_conf.get('con_auth_method'): commands.append(
                f" login authentication {line_conf['con_auth_method']}")
            vty_range = line_conf.get('vty_range', '0 4')
            commands.append(f"line vty {vty_range}")
            if line_conf.get('vty_timeout'): commands.append(f" exec-timeout {line_conf['vty_timeout']}")
            if line_conf.get('vty_transport'): commands.append(f" transport input {line_conf['vty_transport']}")
        snmp = security_config.get('snmp', {})
        if snmp:
            if snmp.get('location'): commands.append(f"snmp-server location {snmp['location']}")
            if snmp.get('contact'): commands.append(f"snmp-server contact {snmp['contact']}")
            for comm in snmp.get('communities', []):
                if comm.get('community'):
                    cmd = f"snmp-server community {comm['community']} {comm.get('permission', 'RO')}"
                    if comm.get('acl'): cmd += f" {comm['acl']}"
                    commands.append(cmd)
            for user in snmp.get('v3_users', []):
                if user.get('username') and user.get('group') and user.get('auth_proto') and user.get('auth_pass'):
                    commands.append(f"snmp-server group {user['group']} v3 auth")
                    cmd = f"snmp-server user {user['username']} {user['group']} v3 auth {user['auth_proto']} {user['auth_pass']}"
                    if user.get('priv_proto') and user.get(
                        'priv_pass'): cmd += f" priv {user['priv_proto']} {user['priv_pass']}"
                    commands.append(cmd)
        hardening = security_config.get('hardening', {})
        if hardening:
            if hardening.get('no_ip_http'): commands.extend(["no ip http server", "no ip http secure-server"])
            if hardening.get('no_cdp'): commands.append("no cdp run" if 'IOS-XE' in os_type else "no feature cdp")
            if hardening.get('lldp'): commands.append("lldp run" if 'IOS-XE' in os_type else "feature lldp")
        if commands:
            tasks.append({'name': 'Configure Security Settings', module: {'lines': commands}})
        return tasks

    def export_playbook_to_yaml(self, playbook_data: Dict[str, Any]) -> str:
        return yaml.dump([playbook_data], default_flow_style=False, allow_unicode=True, indent=2)