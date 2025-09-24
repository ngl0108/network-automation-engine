# ansible_config_editor/core/ansible_engine.py
import yaml
import json
from typing import Dict, List, Any, Tuple
from datetime import datetime


class AnsibleEngine:
    """
    Windows 환경에서의 개발 편의성을 위한 Mock Ansible 실행 엔진

    실제 Ansible을 실행하지 않고, 생성된 플레이북의 내용을
    로그 창에 출력하여 즉각적인 피드백을 제공합니다.

    향후 실제 배포 단계에서는 ansible-runner 라이브러리를
    사용하는 실제 실행 엔진으로 교체할 수 있습니다.
    """

    def __init__(self):
        self.execution_history = []
        self.mock_mode = True  # 실제 실행 모드로 변경 가능

    def execute_configuration(self, target_hosts: List[str], playbook_data: Dict[str, Any]) -> Tuple[str, str]:
        """
        구성을 대상 장비에 적용합니다 (현재는 Mock 실행)

        Args:
            target_hosts: 대상 장비 목록
            playbook_data: 실행할 플레이북 데이터

        Returns:
            Tuple[status, output]: 실행 상태와 출력 결과
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if self.mock_mode:
            return self._execute_mock(target_hosts, playbook_data, timestamp)
        else:
            # 향후 실제 ansible-runner 구현
            return self._execute_real(target_hosts, playbook_data, timestamp)

    def _execute_mock(self, target_hosts: List[str], playbook_data: Dict[str, Any], timestamp: str) -> Tuple[str, str]:
        """Mock 실행 - 플레이북 내용을 분석하여 가상 실행 결과 생성"""

        # 실행 이력에 추가
        execution_record = {
            'timestamp': timestamp,
            'hosts': target_hosts,
            'playbook': playbook_data,
            'status': 'mock_successful'
        }
        self.execution_history.append(execution_record)

        # 플레이북을 YAML로 변환
        playbook_yaml = self._convert_to_yaml(playbook_data)

        # 태스크 분석
        task_count = len(playbook_data.get('tasks', []))
        host_count = len(target_hosts)

        # 가상 실행 결과 생성
        mock_output = self._generate_mock_output(target_hosts, playbook_data, task_count)

        # 최종 출력 조합
        final_output = f"""
=== ANSIBLE MOCK EXECUTION REPORT ===
실행 시간: {timestamp}
대상 장비: {', '.join(target_hosts)} ({host_count}대)
총 태스크 수: {task_count}개

=== GENERATED PLAYBOOK (YAML) ===
{playbook_yaml}

=== MOCK EXECUTION RESULTS ===
{mock_output}

=== EXECUTION SUMMARY ===
✓ 모든 태스크가 성공적으로 실행되었습니다 (모의)
✓ {host_count}대 장비에 {task_count}개 태스크 적용 완료
✓ 구성 변경사항이 적용되었습니다 (모의)

주의: 이것은 Mock 실행 결과입니다. 실제 장비에는 적용되지 않았습니다.
"""

        return 'successful', final_output.strip()

    def _execute_real(self, target_hosts: List[str], playbook_data: Dict[str, Any], timestamp: str) -> Tuple[str, str]:
        """
        실제 ansible-runner를 사용한 실행 (향후 구현)

        향후 이 메서드에서 실제 ansible-runner를 사용하여
        플레이북을 실행하고 결과를 반환할 예정입니다.
        """
        # TODO: ansible-runner 구현
        # import ansible_runner
        #
        # result = ansible_runner.run(
        #     private_data_dir='/tmp/ansible-runner',
        #     inventory=target_hosts,
        #     playbook=playbook_data
        # )
        #
        # return result.status, result.stdout

        return 'not_implemented', 'Real execution not implemented yet. Use mock mode.'

    def _convert_to_yaml(self, playbook_data: Dict[str, Any]) -> str:
        """플레이북 데이터를 YAML 문자열로 변환"""
        try:
            # Ansible 플레이북은 리스트 형태여야 함
            playbook_list = [playbook_data]
            yaml_str = yaml.dump(playbook_list, default_flow_style=False, allow_unicode=True, indent=2)
            return yaml_str
        except Exception as e:
            return f"YAML 변환 오류: {str(e)}"

    def _generate_mock_output(self, target_hosts: List[str], playbook_data: Dict[str, Any], task_count: int) -> str:
        """가상 실행 결과 생성"""
        output_lines = []

        # 플레이북 시작
        playbook_name = playbook_data.get('name', 'Unnamed Playbook')
        output_lines.append(f"PLAY [{playbook_name}] {'*' * 50}")
        output_lines.append("")

        # 각 호스트별로 태스크 실행 결과 시뮬레이션
        for host in target_hosts:
            output_lines.append(f"TASK [Gathering Facts on {host}] {'*' * 30}")
            output_lines.append(f"ok: [{host}]")
            output_lines.append("")

            # 각 태스크별 실행 결과
            for i, task in enumerate(playbook_data.get('tasks', []), 1):
                task_name = task.get('name', f'Task {i}')
                output_lines.append(f"TASK [{task_name}] {'*' * 30}")

                # 태스크 유형에 따른 다른 결과 시뮬레이션
                if 'debug' in task:
                    output_lines.append(f"ok: [{host}] => {{")
                    output_lines.append(f'    "msg": "{task["debug"].get("msg", "Debug message")}"')
                    output_lines.append("}")
                elif any(module in task for module in ['cisco.ios.ios_config', 'cisco.nxos.nxos_config']):
                    # 구성 변경 태스크
                    config_module = 'cisco.ios.ios_config' if 'cisco.ios.ios_config' in task else 'cisco.nxos.nxos_config'
                    lines_count = len(task[config_module].get('lines', []))
                    output_lines.append(f"changed: [{host}] => (item={lines_count} configuration lines)")
                else:
                    output_lines.append(f"ok: [{host}]")

                output_lines.append("")

        # 실행 요약
        output_lines.append("PLAY RECAP " + "*" * 50)
        for host in target_hosts:
            output_lines.append(
                f"{host:<20} : ok={task_count:<3} changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0")

        return "\n".join(output_lines)

    def get_execution_history(self) -> List[Dict[str, Any]]:
        """실행 이력 반환"""
        return self.execution_history

    def clear_execution_history(self):
        """실행 이력 초기화"""
        self.execution_history = []

    def set_mock_mode(self, mock_enabled: bool):
        """Mock 모드 설정"""
        self.mock_mode = mock_enabled

    def validate_connectivity(self, target_hosts: List[str]) -> Dict[str, bool]:
        """
        대상 호스트들의 연결성 검증 (향후 구현)

        현재는 Mock으로 모든 호스트가 연결 가능한 것으로 반환
        """
        if self.mock_mode:
            return {host: True for host in target_hosts}
        else:
            # TODO: 실제 연결성 테스트 구현
            # ping, SSH 연결 테스트 등
            return {host: False for host in target_hosts}

    def dry_run(self, target_hosts: List[str], playbook_data: Dict[str, Any]) -> Tuple[str, str]:
        """
        Dry-run 실행 (--check 모드 시뮬레이션)

        실제 변경 없이 어떤 변경이 발생할지 미리보기
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Dry-run 출력 생성
        playbook_yaml = self._convert_to_yaml(playbook_data)
        task_count = len(playbook_data.get('tasks', []))

        dry_run_output = f"""
=== ANSIBLE DRY-RUN (CHECK MODE) ===
실행 시간: {timestamp}
대상 장비: {', '.join(target_hosts)}
모드: Check Mode (실제 변경 없음)

=== PLAYBOOK TO BE EXECUTED ===
{playbook_yaml}

=== EXPECTED CHANGES (DRY-RUN) ===
다음 변경사항들이 적용될 예정입니다:

"""

        # 각 태스크별 예상 변경사항
        for i, task in enumerate(playbook_data.get('tasks', []), 1):
            task_name = task.get('name', f'Task {i}')
            dry_run_output += f"{i}. {task_name}\n"

            if 'cisco.ios.ios_config' in task or 'cisco.nxos.nxos_config' in task:
                config_key = 'cisco.ios.ios_config' if 'cisco.ios.ios_config' in task else 'cisco.nxos.nxos_config'
                lines = task[config_key].get('lines', [])
                dry_run_output += f"   - {len(lines)}개의 구성 라인이 추가/변경됩니다\n"
                for line in lines[:3]:  # 처음 3개만 미리보기
                    dry_run_output += f"     > {line}\n"
                if len(lines) > 3:
                    dry_run_output += f"     ... 및 {len(lines) - 3}개 추가 라인\n"
            else:
                dry_run_output += "   - 정보 수집 또는 검증 태스크\n"

            dry_run_output += "\n"

        dry_run_output += """
=== DRY-RUN SUMMARY ===
✓ 모든 태스크가 성공적으로 실행될 것으로 예상됩니다
✓ 위 변경사항들이 실제 실행 시 적용됩니다
⚠ 이것은 Dry-run 결과입니다. 실제 장비에는 아직 적용되지 않았습니다.

실제 적용을 원하시면 '구성 적용' 버튼을 클릭하세요.
"""

        return 'dry_run_successful', dry_run_output.strip()