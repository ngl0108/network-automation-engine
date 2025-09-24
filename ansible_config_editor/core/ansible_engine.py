# ansible_config_editor/core/ansible_engine.py
# import ansible_runner  <- 이 줄을 포함한 모든 import를 제거합니다.
# import tempfile
# import yaml
# import os

class AnsibleEngine:
    def __init__(self, project_dir='../ansible'):
        """
        Windows 환경에서 GUI 테스트를 위해 ansible-runner를 사용하지 않는
        모의(Mock) 엔진 클래스입니다.
        """
        self.project_dir = project_dir # 실제 경로는 사용하지 않습니다.
        self.inventory_path = None # 실제 경로는 사용하지 않습니다.
        print("--- AnsibleEngine is running in MOCK mode for Windows compatibility ---")

    def execute_discovery(self, target_host):
        """
        실제 장비에 접속하는 대신, 성공 메시지와 가짜 장비 정보를 반환합니다.
        """
        print(f"[MOCK] Discovering device: {target_host}")
        
        # 미리 정의된 가짜 장비 정보
        mock_device_info = {
            'model': 'Cisco Mock IOS-XE Router',
            'version': '17.3.1',
            'serial': 'MOCK12345ABC'
        }
        
        # 성공 상태와 가짜 결과를 튜플로 반환
        return 'successful', mock_device_info

    def execute_configuration(self, target_hosts, playbook_data):
        """
        실제 플레이북을 실행하는 대신, 성공 메시지와 가짜 로그를 반환합니다.
        """
        hosts_str = ", ".join(target_hosts)
        print(f"[MOCK] Applying configuration to: {hosts_str}")
        
        # 생성된 플레이북 내용을 터미널에 출력하여 확인 (디버깅용)
        import yaml
        print("--- Generated Playbook (MOCK RUN) ---")
        print(yaml.dump(playbook_data, indent=4, sort_keys=False))
        print("------------------------------------")

        # 미리 정의된 가짜 Ansible 실행 결과
        mock_stdout = (
            f"PLAY [Apply Generated Configuration] *****\n"
            f"TASK [Gathering Facts] *****\n"
            f"ok: [{target_hosts}]\n"
            f"TASK *****\n"
            f"changed: [{target_hosts}]\n"
            f"PLAY RECAP *****\n"
            f"{target_hosts} : ok=2 changed=1 unreachable=0 failed=0"
        )
        
        # 성공 상태와 가짜 결과 로그를 튜플로 반환
        return 'successful', mock_stdout