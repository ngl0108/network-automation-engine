# ansible_config_editor/ui/main_window.py
import os
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QPushButton, QListWidget, QPlainTextEdit,
                               QFileDialog, QMessageBox, QTabWidget, QFormLayout,
                               QLineEdit, QGroupBox, QTableWidget, QTableWidgetItem,
                               QHeaderView, QAbstractItemView, QApplication, QInputDialog,
                               QScrollArea, QCheckBox, QLabel, QComboBox, QMenuBar)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

from core.playbook_manager import ConfigManager
from core.ansible_engine import AnsibleEngine


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Standard Network Config Manager")
        self.setGeometry(100, 100, 1800, 1000)

        self.config_manager = ConfigManager()
        self.ansible_engine = AnsibleEngine()

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # --- 왼쪽 패널: 장비 관리 및 OS 선택 ---
        device_management_group = QGroupBox("1. 장비 관리")
        device_layout = QVBoxLayout()

        self.combo_os_type = QComboBox()
        # [수정된 부분] OS 유형 리스트 추가
        os_types = [
            "L2_IOS-XE",
            "L3_IOS-XE",
            "L2_NX-OS",
            "L3_NX-OS",
            "WLC_AireOS"
        ]
        self.combo_os_type.addItems(os_types)
        device_layout.addWidget(QLabel("대상 장비 OS 유형:"))
        device_layout.addWidget(self.combo_os_type)

        self.device_list = QListWidget()
        self.device_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        device_button_layout = QHBoxLayout()
        self.btn_add_device = QPushButton("장비 추가")
        self.btn_remove_device = QPushButton("장비 삭제")
        device_button_layout.addWidget(self.btn_add_device)
        device_button_layout.addWidget(self.btn_remove_device)
        device_layout.addLayout(device_button_layout)
        device_layout.addWidget(self.device_list)
        device_management_group.setLayout(device_layout)

        # --- 중앙 패널: 계층적 구성 탭 ---
        config_group = QGroupBox("2. 구성 편집")
        config_layout = QVBoxLayout()
        self.main_tabs = QTabWidget()

        # 각 모듈에 대한 탭 생성
        self.main_tabs.addTab(self._create_global_tab(), "Global")
        self.main_tabs.addTab(self._create_interface_tab(), "Interface")
        self.main_tabs.addTab(self._create_vlan_tab(), "VLAN")
        self.main_tabs.addTab(self._create_routing_tab(), "Routing")
        self.main_tabs.addTab(self._create_ha_tab(), "HA (고가용성)")
        self.main_tabs.addTab(self._create_security_tab(), "Security (ACL, SNMP 등)")

        config_layout.addWidget(self.main_tabs)
        config_group.setLayout(config_layout)

        # --- 오른쪽 패널: 실행 및 로그 ---
        execution_group = QGroupBox("3. 실행 및 로그")
        execution_layout = QVBoxLayout()
        self.btn_apply = QPushButton("구성 적용")
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        execution_layout.addWidget(self.btn_apply)
        execution_layout.addWidget(self.log_output)
        execution_group.setLayout(execution_layout)

        main_layout.addWidget(device_management_group, 1)
        main_layout.addWidget(config_group, 3)
        main_layout.addWidget(execution_group, 2)

    def _create_scrollable_tab(self):
        """탭 내부에 스크롤을 추가하기 위한 헬퍼 함수"""
        tab_widget = QWidget()
        tab_layout = QVBoxLayout(tab_widget)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_area.setWidget(scroll_content)
        tab_layout.addWidget(scroll_area)
        return tab_widget, scroll_layout

    def _create_global_tab(self):
        tab, layout = self._create_scrollable_tab()

        # Hostname & General Service
        group_hostname = QGroupBox("Hostname & General Service")
        form_hostname = QFormLayout()
        self.le_hostname = QLineEdit()
        self.le_hostname.setPlaceholderText("예: SW-CORE-01")
        self.cb_service_timestamps = QCheckBox()
        self.cb_service_password_encryption = QCheckBox()
        form_hostname.addRow("Hostname:", self.le_hostname)
        form_hostname.addRow("service timestamps debug/log...", self.cb_service_timestamps)
        form_hostname.addRow("service password-encryption", self.cb_service_password_encryption)
        group_hostname.setLayout(form_hostname)
        layout.addWidget(group_hostname)

        # Logging
        group_logging = QGroupBox("Logging")
        form_logging = QFormLayout()
        self.logging_table = QTableWidget(0, 2)
        # [수정된 부분] 헤더 라벨 추가
        self.logging_table.setHorizontalHeaderLabels(["로깅 서버 IP", "VRF (선택사항)"])
        self.logging_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.btn_add_log_host = QPushButton("로깅 서버 추가")
        self.btn_remove_log_host = QPushButton("로깅 서버 삭제")
        form_logging.addRow(self.btn_add_log_host, self.btn_remove_log_host)
        form_logging.addRow(self.logging_table)
        group_logging.setLayout(form_logging)
        layout.addWidget(group_logging)

        # NTP
        group_ntp = QGroupBox("NTP")
        form_ntp = QFormLayout()
        self.ntp_table = QTableWidget(0, 3)
        # [수정된 부분] 헤더 라벨 추가
        self.ntp_table.setHorizontalHeaderLabels(["NTP 서버 IP", "Prefer (선택)", "VRF (선택사항)"])
        self.ntp_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.btn_add_ntp = QPushButton("NTP 서버 추가")
        self.btn_remove_ntp = QPushButton("NTP 서버 삭제")
        form_ntp.addRow(self.btn_add_ntp, self.btn_remove_ntp)
        form_ntp.addRow(self.ntp_table)
        group_ntp.setLayout(form_ntp)
        layout.addWidget(group_ntp)

        layout.addStretch()
        return tab

    def _create_interface_tab(self):
        tab, layout = self._create_scrollable_tab()

        # 기본적인 인터페이스 설정 UI 추가
        group_interface = QGroupBox("Physical Interface Configuration")
        form_interface = QFormLayout()

        # 인터페이스 타입 선택
        self.combo_interface_type = QComboBox()
        self.combo_interface_type.addItems(["Access", "Trunk", "Routed"])
        form_interface.addRow("Interface Mode:", self.combo_interface_type)

        # 기본 설정
        self.le_interface_description = QLineEdit()
        self.le_interface_description.setPlaceholderText("예: To Server Farm")
        form_interface.addRow("Description:", self.le_interface_description)

        group_interface.setLayout(form_interface)
        layout.addWidget(group_interface)

        # 추후 상세 구현 예정 메시지
        layout.addWidget(QLabel("인터페이스 설정 (Trunk, Access, Port-Channel) 기능이 여기에 구현됩니다."))
        layout.addStretch()
        return tab

    def _create_vlan_tab(self):
        tab, layout = self._create_scrollable_tab()

        # VLAN 관리 테이블
        group_vlan = QGroupBox("VLAN Management")
        vlan_layout = QVBoxLayout()

        self.vlan_table = QTableWidget(0, 3)
        self.vlan_table.setHorizontalHeaderLabels(["VLAN ID", "VLAN Name", "Description"])
        self.vlan_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        vlan_button_layout = QHBoxLayout()
        self.btn_add_vlan = QPushButton("VLAN 추가")
        self.btn_remove_vlan = QPushButton("VLAN 삭제")
        vlan_button_layout.addWidget(self.btn_add_vlan)
        vlan_button_layout.addWidget(self.btn_remove_vlan)

        vlan_layout.addLayout(vlan_button_layout)
        vlan_layout.addWidget(self.vlan_table)
        group_vlan.setLayout(vlan_layout)
        layout.addWidget(group_vlan)

        layout.addWidget(QLabel("VLAN 정의 및 SVI 설정 기능이 여기에 구현됩니다."))
        layout.addStretch()
        return tab

    def _create_routing_tab(self):
        tab, layout = self._create_scrollable_tab()
        layout.addWidget(QLabel("Static, OSPF, BGP, VRRP 등 라우팅 설정 기능이 여기에 구현됩니다."))
        layout.addStretch()
        return tab

    def _create_ha_tab(self):
        tab, layout = self._create_scrollable_tab()
        layout.addWidget(QLabel("StackWise Virtual (IOS-XE), vPC (NX-OS) 등 고가용성 설정 기능이 여기에 구현됩니다."))
        layout.addStretch()
        return tab

    def _create_security_tab(self):
        tab, layout = self._create_scrollable_tab()

        # AAA
        group_aaa = QGroupBox("AAA")
        form_aaa = QFormLayout()
        self.cb_aaa_new_model = QCheckBox("aaa new-model 활성화")
        self.aaa_server_table = QTableWidget(0, 3)
        self.aaa_server_table.setHorizontalHeaderLabels(["서버 종류 (tacacs+/radius)", "그룹 이름", "서버 IP 리스트 (쉼표로 구분)"])
        self.aaa_server_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.btn_add_aaa_group = QPushButton("AAA 서버 그룹 추가")
        self.btn_remove_aaa_group = QPushButton("AAA 서버 그룹 삭제")
        form_aaa.addRow(self.cb_aaa_new_model)
        form_aaa.addRow(self.btn_add_aaa_group, self.btn_remove_aaa_group)
        form_aaa.addRow(self.aaa_server_table)
        group_aaa.setLayout(form_aaa)
        layout.addWidget(group_aaa)

        # ACL
        group_acl = QGroupBox("Access Control Lists (ACL)")
        layout.addWidget(group_acl)  # 추후 상세 구현

        # SNMP
        group_snmp = QGroupBox("SNMP")
        layout.addWidget(group_snmp)  # 추후 상세 구현

        layout.addStretch()
        return tab

    def _connect_signals(self):
        self.btn_add_device.clicked.connect(self.ui_add_device)
        self.btn_remove_device.clicked.connect(self.ui_remove_device)
        self.btn_apply.clicked.connect(self.run_config_task)

        # 동적으로 생성된 버튼에 대한 연결
        self.btn_add_log_host.clicked.connect(lambda: self.ui_add_table_row(self.logging_table))
        self.btn_remove_log_host.clicked.connect(lambda: self.ui_remove_table_row(self.logging_table))
        self.btn_add_ntp.clicked.connect(lambda: self.ui_add_table_row(self.ntp_table))
        self.btn_remove_ntp.clicked.connect(lambda: self.ui_remove_table_row(self.ntp_table))
        self.btn_add_aaa_group.clicked.connect(lambda: self.ui_add_table_row(self.aaa_server_table))
        self.btn_remove_aaa_group.clicked.connect(lambda: self.ui_remove_table_row(self.aaa_server_table))

        # VLAN 관리 버튼 연결
        if hasattr(self, 'btn_add_vlan'):
            self.btn_add_vlan.clicked.connect(lambda: self.ui_add_table_row(self.vlan_table))
            self.btn_remove_vlan.clicked.connect(lambda: self.ui_remove_table_row(self.vlan_table))

    def _gather_data_from_ui(self):
        """하드코딩된 UI에서 모든 사용자 입력값을 수집합니다."""
        data = {'global': {}, 'interfaces': {}, 'vlans': {}, 'routing': {}, 'ha': {}, 'security': {}}

        # Global Tab
        data['global']['hostname'] = self.le_hostname.text()
        data['global']['service_timestamps'] = self.cb_service_timestamps.isChecked()
        data['global']['service_password_encryption'] = self.cb_service_password_encryption.isChecked()

        # [수정된 부분] 빈 리스트로 초기화
        log_hosts = []
        for row in range(self.logging_table.rowCount()):
            ip_item = self.logging_table.item(row, 0)
            vrf_item = self.logging_table.item(row, 1)
            if ip_item and ip_item.text():
                log_hosts.append({'ip': ip_item.text(), 'vrf': vrf_item.text() if vrf_item else ''})
        data['global']['logging_hosts'] = log_hosts

        # [수정된 부분] 빈 리스트로 초기화
        ntp_servers = []
        for row in range(self.ntp_table.rowCount()):
            ip_item = self.ntp_table.item(row, 0)
            prefer_item = self.ntp_table.item(row, 1)  # QCheckBox를 테이블 셀에 넣어야 함
            vrf_item = self.ntp_table.item(row, 2)
            if ip_item and ip_item.text():
                ntp_servers.append({'ip': ip_item.text(), 'prefer': False, 'vrf': vrf_item.text() if vrf_item else ''})
        data['global']['ntp_servers'] = ntp_servers

        # Interface Tab (기본 정보만)
        data['interfaces']['type'] = self.combo_interface_type.currentText() if hasattr(self,
                                                                                        'combo_interface_type') else 'Access'
        data['interfaces']['description'] = self.le_interface_description.text() if hasattr(self,
                                                                                            'le_interface_description') else ''

        # VLAN Tab
        vlans = []
        if hasattr(self, 'vlan_table'):
            for row in range(self.vlan_table.rowCount()):
                vlan_id_item = self.vlan_table.item(row, 0)
                vlan_name_item = self.vlan_table.item(row, 1)
                vlan_desc_item = self.vlan_table.item(row, 2)
                if vlan_id_item and vlan_id_item.text():
                    vlans.append({
                        'id': vlan_id_item.text(),
                        'name': vlan_name_item.text() if vlan_name_item else '',
                        'description': vlan_desc_item.text() if vlan_desc_item else ''
                    })
        data['vlans']['list'] = vlans

        # Security Tab
        data['security']['aaa_new_model'] = self.cb_aaa_new_model.isChecked()

        # AAA 서버 그룹
        aaa_groups = []
        for row in range(self.aaa_server_table.rowCount()):
            type_item = self.aaa_server_table.item(row, 0)
            group_item = self.aaa_server_table.item(row, 1)
            servers_item = self.aaa_server_table.item(row, 2)
            if type_item and group_item and servers_item:
                aaa_groups.append({
                    'type': type_item.text(),
                    'group_name': group_item.text(),
                    'servers': [s.strip() for s in servers_item.text().split(',') if s.strip()]
                })
        data['security']['aaa_groups'] = aaa_groups

        return data

    def run_config_task(self):
        target_hosts = self._get_selected_devices()
        if not target_hosts: return

        user_input_data = self._gather_data_from_ui()
        os_type = self.combo_os_type.currentText()

        try:
            playbook_data = self.config_manager.generate_playbook(os_type, user_input_data)

            self.log_output.appendPlainText(f"===== {', '.join(target_hosts)}에 구성 적용 시작 ({os_type}) =====")
            status, result_stdout = self.ansible_engine.execute_configuration(target_hosts, playbook_data)

            if status == 'successful':
                self.log_output.appendPlainText("구성 적용 성공.")
            else:
                self.log_output.appendPlainText("구성 적용 실패.")

            self.log_output.appendPlainText("--- Ansible 실행 결과 (모의) ---")
            self.log_output.appendPlainText(result_stdout)
            self.log_output.appendPlainText("--------------------------\n")
        except Exception as e:
            self.log_output.appendPlainText(f"오류 발생: {str(e)}")

    # --- UI 헬퍼 함수들 ---
    def ui_add_device(self):
        text, ok = QInputDialog.getText(self, '장비 추가', '장비 IP 또는 호스트명 입력:')
        if ok and text:
            self.device_list.addItem(text)

    def ui_remove_device(self):
        for item in self.device_list.selectedItems():
            self.device_list.takeItem(self.device_list.row(item))

    def ui_add_table_row(self, table_widget):
        table_widget.insertRow(table_widget.rowCount())

    def ui_remove_table_row(self, table_widget):
        current_row = table_widget.currentRow()
        if current_row > -1:
            table_widget.removeRow(current_row)

    def _get_selected_devices(self):
        selected_items = self.device_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "경고", "장비를 먼저 선택해주세요.")
            return None
        return [item.text() for item in selected_items]