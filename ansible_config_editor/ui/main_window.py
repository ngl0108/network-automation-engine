# ansible_config_editor/ui/main_window.py
import os
import json
from copy import deepcopy
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QPushButton, QListWidget, QListWidgetItem, QPlainTextEdit,
                               QFileDialog, QMessageBox, QTabWidget, QFormLayout,
                               QLineEdit, QGroupBox, QTableWidget, QTableWidgetItem,
                               QHeaderView, QAbstractItemView, QApplication, QInputDialog,
                               QScrollArea, QCheckBox, QLabel, QComboBox, QMenuBar,
                               QDialog, QDialogButtonBox, QStackedWidget)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

from ansible_config_editor.core.playbook_manager import ConfigManager
from ansible_config_editor.core.ansible_engine import AnsibleEngine


class CredentialsDialog(QDialog):
    """SSH 인증 정보를 입력받기 위한 다이얼로그"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SSH 인증 정보")
        layout = QFormLayout(self)
        self.username_edit = QLineEdit(self)
        self.password_edit = QLineEdit(self)
        self.password_edit.setEchoMode(QLineEdit.Password)
        layout.addRow("Username:", self.username_edit)
        layout.addRow("Password:", self.password_edit)
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_credentials(self):
        return {'user': self.username_edit.text(), 'pass': self.password_edit.text()}


class AddDevicesDialog(QDialog):
    """여러 장비를 추가하기 위한 커스텀 대화상자"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("여러 장비 추가")
        self.setMinimumSize(400, 300)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("추가할 장비의 IP 또는 호스트명을 한 줄에 하나씩 입력하세요."))
        self.text_edit = QPlainTextEdit(self)
        layout.addWidget(self.text_edit)
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_devices(self):
        content = self.text_edit.toPlainText()
        return [line.strip() for line in content.splitlines() if line.strip()]


class AddInterfacesDialog(QDialog):
    """인터페이스 종류, 슬롯, 포트 범위를 입력받는 다이얼로그"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("인터페이스 범위 추가")
        self.setMinimumWidth(400)
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        self.combo_type = QComboBox()
        self.combo_type.addItems(
            ["GigabitEthernet", "TenGigabitEthernet", "TwentyFiveGigE", "FortyGigabitEthernet", "FastEthernet"])
        self.le_slot = QLineEdit()
        self.le_slot.setPlaceholderText("예: 1/0")
        self.le_start_port = QLineEdit()
        self.le_start_port.setPlaceholderText("예: 1")
        self.le_end_port = QLineEdit()
        self.le_end_port.setPlaceholderText("예: 24 (단일 포트는 비워두세요)")
        form_layout.addRow("인터페이스 종류:", self.combo_type)
        form_layout.addRow("모듈/슬롯 번호:", self.le_slot)
        form_layout.addRow("시작 포트 번호:", self.le_start_port)
        form_layout.addRow("끝 포트 번호 (선택):", self.le_end_port)
        layout.addLayout(form_layout)
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_interfaces(self):
        if_type = self.combo_type.currentText()
        slot = self.le_slot.text()
        start_port_str = self.le_start_port.text()
        end_port_str = self.le_end_port.text()
        if not (if_type and slot and start_port_str):
            QMessageBox.warning(self, "입력 오류", "인터페이스 종류, 슬롯, 시작 포트는 필수입니다.")
            return []
        try:
            start_port = int(start_port_str)
            end_port = int(end_port_str) if end_port_str else start_port
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "포트 번호는 숫자여야 합니다.")
            return []
        if start_port > end_port:
            QMessageBox.warning(self, "입력 오류", "끝 포트 번호는 시작 포트보다 크거나 같아야 합니다.")
            return []
        return [f"{if_type}{slot}/{i}" for i in range(start_port, end_port + 1)]


class MainWindow(QMainWindow):
    # --- 초기화 및 UI 생성 메서드 ---
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Standard Network Config Manager")
        self.setGeometry(100, 100, 1800, 1000)

        self.config_manager = ConfigManager()
        self.ansible_engine = AnsibleEngine()
        self.current_config_path = None

        self._setup_ui()
        self._setup_menu()
        self._connect_signals()
        self._update_ui_for_os()

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # 왼쪽 패널
        device_management_group = QGroupBox("1. 장비 관리")
        device_layout = QVBoxLayout()
        self.combo_os_type = QComboBox()
        self.combo_os_type.addItems(["L2_IOS-XE", "L3_IOS-XE", "L2_NX-OS", "L3_NX-OS"])
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
        self.btn_fetch_info = QPushButton("선택 장비 정보 가져오기")
        self.btn_fetch_info.setEnabled(False)
        self.btn_fetch_info.setToolTip("이 기능은 Linux 환경(예: WSL)에서만 사용 가능합니다.")
        device_layout.addWidget(self.btn_fetch_info)
        device_layout.addWidget(self.device_list)
        device_management_group.setLayout(device_layout)

        # 중앙 패널
        config_group = QGroupBox("2. 구성 편집")
        config_layout = QVBoxLayout()
        self.main_tabs = QTabWidget()
        self.main_tabs.addTab(self._create_global_tab(), "Global")
        self.main_tabs.addTab(self._create_interface_tab(), "Interface")
        self.main_tabs.addTab(self._create_vlan_tab(), "VLAN")
        self.main_tabs.addTab(self._create_switching_tab(), "Switching")
        self.main_tabs.addTab(self._create_routing_tab(), "Routing")
        self.main_tabs.addTab(self._create_ha_tab(), "HA (고가용성)")
        self.main_tabs.addTab(self._create_security_tab(), "Security")
        config_group.setLayout(config_layout)
        config_layout.addWidget(self.main_tabs)

        # 오른쪽 패널
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

    def _setup_menu(self):
        self.menu_bar = QMenuBar(self)
        self.setMenuBar(self.menu_bar)
        file_menu = self.menu_bar.addMenu("파일(&F)")
        new_action = QAction("새 구성(&N)", self)
        new_action.triggered.connect(self._new_config_profile)
        open_action = QAction("구성 열기(&O)...", self)
        open_action.triggered.connect(self._load_config_profile)
        save_as_action = QAction("다른 이름으로 구성 저장(&A)...", self)
        save_as_action.triggered.connect(self._save_config_profile)
        file_menu.addAction(new_action)
        file_menu.addAction(open_action)
        file_menu.addAction(save_as_action)

    def _create_scrollable_tab(self):
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

        group_hostname = QGroupBox("Hostname & General Service")
        form_hostname = QFormLayout()
        self.le_hostname = QLineEdit()
        self.cb_service_timestamps = QCheckBox("service timestamps debug/log")
        self.cb_service_password_encryption = QCheckBox("service password-encryption")
        self.cb_service_call_home = QCheckBox("no service call-home")
        form_hostname.addRow("Hostname:", self.le_hostname)
        form_hostname.addRow(self.cb_service_timestamps)
        form_hostname.addRow(self.cb_service_password_encryption)
        form_hostname.addRow(self.cb_service_call_home)
        group_hostname.setLayout(form_hostname)
        layout.addWidget(group_hostname)

        group_dns = QGroupBox("DNS & Domain")
        form_dns = QFormLayout()
        self.le_domain_name = QLineEdit()
        self.dns_table = QTableWidget(0, 2)
        self.dns_table.setHorizontalHeaderLabels(["DNS 서버 IP", "VRF (선택사항)"])
        self.dns_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.btn_add_dns = QPushButton("DNS 서버 추가")
        self.btn_remove_dns = QPushButton("DNS 서버 삭제")
        form_dns.addRow("Domain Name:", self.le_domain_name)
        form_dns.addRow(self.btn_add_dns, self.btn_remove_dns)
        form_dns.addRow(self.dns_table)
        group_dns.setLayout(form_dns)
        layout.addWidget(group_dns)

        group_clock = QGroupBox("Clock & Timezone")
        form_clock = QFormLayout()
        self.combo_timezone = QComboBox()
        self.combo_timezone.addItems(
            ["UTC 0", "KST 9", "JST 9", "CST 8", "EST -5", "PST -8", "GMT 0", "CET 1", "Custom"])
        self.le_custom_timezone = QLineEdit()
        self.le_custom_timezone.setEnabled(False)
        form_clock.addRow("Timezone:", self.combo_timezone)
        form_clock.addRow("Custom Timezone:", self.le_custom_timezone)
        self.cb_summer_time = QCheckBox("Summer-time (Daylight Saving) 적용")
        self.le_summer_time_zone = QLineEdit()
        self.le_summer_time_zone.setEnabled(False)
        form_clock.addRow(self.cb_summer_time, self.le_summer_time_zone)
        group_clock.setLayout(form_clock)
        layout.addWidget(group_clock)

        group_logging = QGroupBox("Logging")
        form_logging = QFormLayout()
        self.combo_logging_level = QComboBox()
        self.combo_logging_level.addItems(
            ["informational (6)", "warnings (4)", "errors (3)", "critical (2)", "debugging (7)"])
        self.cb_logging_console = QCheckBox("Console Logging")
        self.cb_logging_console.setChecked(True)
        self.cb_logging_buffered = QCheckBox("Buffered Logging")
        self.cb_logging_buffered.setChecked(True)
        self.le_logging_buffer_size = QLineEdit("32000")
        self.logging_table = QTableWidget(0, 2)
        self.logging_table.setHorizontalHeaderLabels(["로깅 서버 IP", "VRF (선택사항)"])
        self.logging_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.btn_add_log_host = QPushButton("로깅 서버 추가")
        self.btn_remove_log_host = QPushButton("로깅 서버 삭제")
        form_logging.addRow("Logging Level:", self.combo_logging_level)
        form_logging.addRow(self.cb_logging_console)
        form_logging.addRow(self.cb_logging_buffered)
        form_logging.addRow("Buffer Size:", self.le_logging_buffer_size)
        form_logging.addRow(self.btn_add_log_host, self.btn_remove_log_host)
        form_logging.addRow(self.logging_table)
        group_logging.setLayout(form_logging)
        layout.addWidget(group_logging)

        group_ntp = QGroupBox("NTP")
        form_ntp = QFormLayout()
        self.cb_ntp_authenticate = QCheckBox("NTP Authentication")
        self.le_ntp_master_stratum = QLineEdit()
        self.ntp_table = QTableWidget(0, 4)
        self.ntp_table.setHorizontalHeaderLabels(["NTP 서버 IP", "Prefer", "Key ID", "VRF"])
        self.ntp_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.btn_add_ntp = QPushButton("NTP 서버 추가")
        self.btn_remove_ntp = QPushButton("NTP 서버 삭제")
        form_ntp.addRow(self.cb_ntp_authenticate)
        form_ntp.addRow("Master Stratum:", self.le_ntp_master_stratum)
        form_ntp.addRow(self.btn_add_ntp, self.btn_remove_ntp)
        form_ntp.addRow(self.ntp_table)
        group_ntp.setLayout(form_ntp)
        layout.addWidget(group_ntp)

        group_mgmt = QGroupBox("Management Interface")
        form_mgmt = QFormLayout()
        self.combo_mgmt_interface = QComboBox()
        self.combo_mgmt_interface.addItems(
            ["None", "GigabitEthernet0/0", "Management1", "Management0", "Vlan1", "FastEthernet0", "Custom"])
        self.le_custom_mgmt_interface = QLineEdit()
        self.le_custom_mgmt_interface.setEnabled(False)
        self.le_mgmt_ip = QLineEdit()
        self.le_mgmt_subnet = QLineEdit()
        self.le_mgmt_gateway = QLineEdit()
        self.le_mgmt_vrf = QLineEdit()
        form_mgmt.addRow("Management Interface:", self.combo_mgmt_interface)
        form_mgmt.addRow("Custom Interface:", self.le_custom_mgmt_interface)
        form_mgmt.addRow("IP Address:", self.le_mgmt_ip)
        form_mgmt.addRow("Subnet Mask:", self.le_mgmt_subnet)
        form_mgmt.addRow("Gateway:", self.le_mgmt_gateway)
        form_mgmt.addRow("VRF:", self.le_mgmt_vrf)
        group_mgmt.setLayout(form_mgmt)
        layout.addWidget(group_mgmt)

        group_banner = QGroupBox("Login Banner")
        form_banner = QFormLayout()
        self.cb_enable_banner = QCheckBox("Enable Login Banner")
        self.te_banner_text = QPlainTextEdit()
        self.te_banner_text.setMaximumHeight(100)
        self.te_banner_text.setEnabled(False)
        form_banner.addRow(self.cb_enable_banner)
        form_banner.addRow("Banner Text:", self.te_banner_text)
        group_banner.setLayout(form_banner)
        layout.addWidget(group_banner)

        self.group_archive = QGroupBox("Configuration Archive")
        form_archive = QFormLayout()
        self.cb_archive_config = QCheckBox("Enable Configuration Archive")
        self.le_archive_path = QLineEdit()
        self.le_archive_path.setEnabled(False)
        self.le_archive_max_files = QLineEdit()
        self.le_archive_max_files.setEnabled(False)
        self.cb_archive_time_period = QCheckBox("Time-based Archive")
        self.le_archive_time_period = QLineEdit()
        self.le_archive_time_period.setEnabled(False)
        form_archive.addRow(self.cb_archive_config)
        form_archive.addRow("Archive Path:", self.le_archive_path)
        form_archive.addRow("Max Files:", self.le_archive_max_files)
        form_archive.addRow(self.cb_archive_time_period, self.le_archive_time_period)
        self.group_archive.setLayout(form_archive)
        layout.addWidget(self.group_archive)

        layout.addStretch()
        return tab

    def _create_interface_tab(self):
        tab = QWidget()
        main_layout = QHBoxLayout(tab)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(QLabel("설정할 인터페이스 목록 (Ctrl, Shift로 다중 선택 가능)"))
        self.interface_list = QListWidget()
        self.interface_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        left_layout.addWidget(self.interface_list)
        warning_label = QLabel("주의: 물리적 구성이 동일한\n장비 그룹별로 작업하십시오.")
        warning_label.setStyleSheet("color: red; font-weight: bold;")
        left_layout.addWidget(warning_label)
        btn_layout = QHBoxLayout()
        self.btn_add_interface = QPushButton("인터페이스 추가")
        self.btn_add_port_channel = QPushButton("Port-Channel 추가")
        self.btn_remove_interface = QPushButton("목록에서 삭제")
        btn_layout.addWidget(self.btn_add_interface)
        btn_layout.addWidget(self.btn_add_port_channel)
        left_layout.addLayout(btn_layout)
        left_layout.addWidget(self.btn_remove_interface)
        main_layout.addWidget(left_widget, 2)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        right_widget = QWidget()
        config_layout = QVBoxLayout(right_widget)
        scroll_area.setWidget(right_widget)
        main_layout.addWidget(scroll_area, 5)

        self.config_area_widget = QWidget()
        config_layout.addWidget(self.config_area_widget)
        form_layout = QVBoxLayout(self.config_area_widget)

        group_basic = QGroupBox("기본 설정")
        form_basic = QFormLayout()
        self.if_label = QLabel("왼쪽 목록에서 인터페이스를 선택하세요.")
        self.cb_if_shutdown = QCheckBox("Shutdown")
        self.le_if_description = QLineEdit()
        self.combo_if_type = QComboBox()
        self.combo_if_type.addItems(["Copper", "Fiber"])
        self.combo_if_mode = QComboBox()
        self.combo_if_mode.addItems(["L2 Access", "L2 Trunk", "L3 Routed", "Port-Channel Member"])
        form_basic.addRow(self.if_label)
        form_basic.addRow("상태:", self.cb_if_shutdown)
        form_basic.addRow("설명:", self.le_if_description)
        form_basic.addRow("포트 유형:", self.combo_if_type)
        form_basic.addRow("인터페이스 모드:", self.combo_if_mode)
        group_basic.setLayout(form_basic)
        form_layout.addWidget(group_basic)

        self.mode_stack = QStackedWidget()
        form_layout.addWidget(self.mode_stack)

        stack_access = QWidget();
        form_access = QFormLayout(stack_access);
        self.le_access_vlan = QLineEdit();
        self.le_voice_vlan = QLineEdit();
        form_access.addRow("Access VLAN:", self.le_access_vlan);
        form_access.addRow("Voice VLAN:", self.le_voice_vlan);
        self.mode_stack.addWidget(stack_access)
        stack_trunk = QWidget();
        form_trunk = QFormLayout(stack_trunk);
        self.le_trunk_native = QLineEdit();
        self.le_trunk_allowed = QLineEdit();
        form_trunk.addRow("Native VLAN:", self.le_trunk_native);
        form_trunk.addRow("Allowed VLANs:", self.le_trunk_allowed);
        self.mode_stack.addWidget(stack_trunk)
        stack_routed = QWidget();
        form_routed = QFormLayout(stack_routed);
        self.le_routed_ip = QLineEdit();
        form_routed.addRow("IP 주소/Prefix:", self.le_routed_ip);
        self.mode_stack.addWidget(stack_routed)
        stack_pc_member = QWidget();
        form_pc_member = QFormLayout(stack_pc_member);
        self.le_channel_group_id = QLineEdit();
        self.combo_channel_group_mode = QComboBox();
        self.combo_channel_group_mode.addItems(["active", "passive", "on"]);
        form_pc_member.addRow("Channel-Group ID:", self.le_channel_group_id);
        form_pc_member.addRow("LACP 모드:", self.combo_channel_group_mode);
        self.mode_stack.addWidget(stack_pc_member)

        self.group_if_stp = QGroupBox("Spanning Tree");
        form_stp = QFormLayout(self.group_if_stp);
        self.cb_stp_portfast = QCheckBox("Portfast 활성화 (Edge port)");
        self.cb_stp_bpduguard = QCheckBox("BPDU Guard 활성화");
        form_stp.addRow(self.cb_stp_portfast);
        form_stp.addRow(self.cb_stp_bpduguard);
        form_layout.addWidget(self.group_if_stp)
        self.group_if_port_security = QGroupBox("Port Security");
        form_ps = QFormLayout(self.group_if_port_security);
        self.cb_ps_enabled = QCheckBox("Port Security 활성화");
        self.le_ps_max_mac = QLineEdit("1");
        self.combo_ps_violation = QComboBox();
        self.combo_ps_violation.addItems(["shutdown", "restrict", "protect"]);
        form_ps.addRow(self.cb_ps_enabled);
        form_ps.addRow("최대 MAC 주소 수:", self.le_ps_max_mac);
        form_ps.addRow("Violation 모드:", self.combo_ps_violation);
        form_layout.addWidget(self.group_if_port_security)
        self.group_if_storm_control = QGroupBox("Storm Control");
        form_sc = QFormLayout(self.group_if_storm_control);
        self.le_sc_broadcast = QLineEdit("10.00");
        self.le_sc_multicast = QLineEdit();
        self.le_sc_unicast = QLineEdit();
        self.combo_sc_action = QComboBox();
        self.combo_sc_action.addItems(["shutdown", "trap"]);
        form_sc.addRow("Broadcast Level (%):", self.le_sc_broadcast);
        form_sc.addRow("Multicast Level (%):", self.le_sc_multicast);
        form_sc.addRow("Unicast Level (%):", self.le_sc_unicast);
        form_sc.addRow("Action:", self.combo_sc_action);
        form_layout.addWidget(self.group_if_storm_control)
        self.group_if_udld = QGroupBox("UDLD");
        form_udld = QFormLayout(self.group_if_udld);
        self.cb_udld_enabled = QCheckBox("UDLD 활성화");
        self.combo_udld_mode = QComboBox();
        self.combo_udld_mode.addItems(["normal", "aggressive"]);
        self.combo_udld_mode.setEnabled(False);
        self.cb_udld_enabled.toggled.connect(self.combo_udld_mode.setEnabled);
        form_udld.addRow(self.cb_udld_enabled);
        form_udld.addRow("모드:", self.combo_udld_mode);
        form_layout.addWidget(self.group_if_udld)

        config_layout.addStretch()
        self.config_area_widget.setVisible(False)
        return tab

    def _create_vlan_tab(self):
        tab, layout = self._create_scrollable_tab()
        self.cb_ip_routing = QCheckBox("Enable Inter-VLAN Routing (ip routing)")
        layout.addWidget(self.cb_ip_routing)
        group_vlan = QGroupBox("1. VLAN 생성 및 관리");
        vlan_layout = QVBoxLayout();
        self.vlan_table = QTableWidget(0, 3);
        self.vlan_table.setHorizontalHeaderLabels(["VLAN ID", "VLAN Name", "Description"]);
        self.vlan_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);
        self.vlan_table.setSelectionBehavior(QAbstractItemView.SelectRows);
        self.vlan_table.setSelectionMode(QAbstractItemView.SingleSelection);
        vlan_button_layout = QHBoxLayout();
        self.btn_add_vlan = QPushButton("VLAN 추가");
        self.btn_remove_vlan = QPushButton("VLAN 삭제");
        vlan_button_layout.addWidget(self.btn_add_vlan);
        vlan_button_layout.addWidget(self.btn_remove_vlan);
        vlan_layout.addLayout(vlan_button_layout);
        vlan_layout.addWidget(self.vlan_table);
        group_vlan.setLayout(vlan_layout);
        layout.addWidget(group_vlan)
        self.group_svi = QGroupBox("2. SVI (Vlan Interface) 설정");
        svi_layout = QVBoxLayout();
        self.svi_label = QLabel("상단 테이블에서 설정을 원하는 VLAN을 선택하세요.");
        svi_layout.addWidget(self.svi_label);
        svi_form_layout = QFormLayout();
        self.cb_svi_enabled = QCheckBox("SVI 인터페이스 생성");
        self.le_svi_ip = QLineEdit();
        svi_form_layout.addRow(self.cb_svi_enabled);
        svi_form_layout.addRow("IP 주소/Prefix:", self.le_svi_ip);
        svi_layout.addLayout(svi_form_layout);
        self.group_fhrp = QGroupBox("VRRP / HSRP 설정");
        fhrp_form = QFormLayout();
        self.cb_fhrp_enabled = QCheckBox("VRRP/HSRP 활성화");
        self.le_fhrp_group = QLineEdit();
        self.le_fhrp_vip = QLineEdit();
        self.le_fhrp_priority = QLineEdit();
        self.cb_fhrp_preempt = QCheckBox("Preempt 활성화");
        fhrp_form.addRow(self.cb_fhrp_enabled);
        fhrp_form.addRow("Group ID:", self.le_fhrp_group);
        fhrp_form.addRow("Virtual IP:", self.le_fhrp_vip);
        fhrp_form.addRow("Priority:", self.le_fhrp_priority);
        fhrp_form.addRow(self.cb_fhrp_preempt);
        self.group_fhrp.setLayout(fhrp_form);
        svi_layout.addWidget(self.group_fhrp);
        self.group_dhcp_helper = QGroupBox("DHCP Helper");
        dhcp_helper_layout = QVBoxLayout();
        self.dhcp_helper_table = QTableWidget(0, 1);
        self.dhcp_helper_table.setHorizontalHeaderLabels(["Helper-Address IP"]);
        self.dhcp_helper_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);
        dhcp_helper_buttons = QHBoxLayout();
        self.btn_add_helper = QPushButton("Helper 추가");
        self.btn_remove_helper = QPushButton("Helper 삭제");
        dhcp_helper_buttons.addWidget(self.btn_add_helper);
        dhcp_helper_buttons.addWidget(self.btn_remove_helper);
        dhcp_helper_layout.addLayout(dhcp_helper_buttons);
        dhcp_helper_layout.addWidget(self.dhcp_helper_table);
        self.group_dhcp_helper.setLayout(dhcp_helper_layout);
        svi_layout.addWidget(self.group_dhcp_helper);
        self.group_svi.setLayout(svi_layout);
        self.group_svi.setEnabled(False);
        layout.addWidget(self.group_svi)
        layout.addStretch()
        return tab

    def _create_switching_tab(self):
        tab, layout = self._create_scrollable_tab()
        group_stp = QGroupBox("Spanning Tree Protocol (STP)");
        form_stp = QFormLayout();
        self.combo_stp_mode = QComboBox();
        self.combo_stp_mode.addItems(["rapid-pvst", "pvst", "mst"]);
        self.le_stp_priority = QLineEdit();
        self.cb_stp_portfast_default = QCheckBox("spanning-tree portfast default");
        self.cb_stp_bpduguard_default = QCheckBox("spanning-tree portfast bpduguard default");
        self.cb_stp_bpdufilter_default = QCheckBox("spanning-tree portfast bpdufilter default");
        self.cb_stp_loopguard_default = QCheckBox("spanning-tree loopguard default");
        form_stp.addRow("STP Mode:", self.combo_stp_mode);
        form_stp.addRow("Root Bridge Priority (VLAN 1-4094):", self.le_stp_priority);
        form_stp.addRow(self.cb_stp_portfast_default);
        form_stp.addRow(self.cb_stp_bpduguard_default);
        form_stp.addRow(self.cb_stp_bpdufilter_default);
        form_stp.addRow(self.cb_stp_loopguard_default);
        group_stp.setLayout(form_stp);
        layout.addWidget(group_stp)
        self.group_mst_config = QGroupBox("MST Configuration");
        mst_layout = QVBoxLayout();
        mst_form = QFormLayout();
        self.le_mst_name = QLineEdit();
        self.le_mst_revision = QLineEdit("0");
        mst_form.addRow("Configuration Name:", self.le_mst_name);
        mst_form.addRow("Revision Number:", self.le_mst_revision);
        mst_layout.addLayout(mst_form);
        self.mst_instance_table = QTableWidget(0, 2);
        self.mst_instance_table.setHorizontalHeaderLabels(["Instance ID", "VLANs (예: 10,20,30-40)"]);
        self.mst_instance_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);
        mst_btn_layout = QHBoxLayout();
        self.btn_add_mst_instance = QPushButton("Instance 추가");
        self.btn_remove_mst_instance = QPushButton("Instance 삭제");
        mst_btn_layout.addWidget(self.btn_add_mst_instance);
        mst_btn_layout.addWidget(self.btn_remove_mst_instance);
        mst_layout.addLayout(mst_btn_layout);
        mst_layout.addWidget(self.mst_instance_table);
        self.group_mst_config.setLayout(mst_layout);
        self.group_mst_config.setVisible(False);
        layout.addWidget(self.group_mst_config)
        group_vtp = QGroupBox("VLAN Trunking Protocol (VTP)");
        form_vtp = QFormLayout();
        self.cb_vtp_enabled = QCheckBox("Enable VTP");
        self.combo_vtp_mode = QComboBox();
        self.combo_vtp_mode.addItems(["transparent", "server", "client", "off"]);
        self.le_vtp_domain = QLineEdit();
        self.le_vtp_password = QLineEdit();
        self.le_vtp_password.setEchoMode(QLineEdit.Password);
        self.combo_vtp_version = QComboBox();
        self.combo_vtp_version.addItems(["2", "1", "3"]);
        form_vtp.addRow(self.cb_vtp_enabled);
        form_vtp.addRow("Mode:", self.combo_vtp_mode);
        form_vtp.addRow("Domain:", self.le_vtp_domain);
        form_vtp.addRow("Password:", self.le_vtp_password);
        form_vtp.addRow("Version:", self.combo_vtp_version);
        group_vtp.setLayout(form_vtp);
        layout.addWidget(group_vtp)
        group_l2_security = QGroupBox("L2 Security");
        form_l2_sec = QFormLayout();
        self.cb_dhcp_snooping_enabled = QCheckBox("Enable DHCP Snooping (Global)");
        self.le_dhcp_snooping_vlans = QLineEdit();
        self.le_dai_vlans = QLineEdit();
        form_l2_sec.addRow(self.cb_dhcp_snooping_enabled);
        form_l2_sec.addRow("DHCP Snooping VLANs:", self.le_dhcp_snooping_vlans);
        form_l2_sec.addRow("Dynamic ARP Inspection (DAI) VLANs:", self.le_dai_vlans);
        group_l2_security.setLayout(form_l2_sec);
        layout.addWidget(group_l2_security)
        layout.addStretch()
        return tab

    def _create_routing_tab(self):
        tab, layout = self._create_scrollable_tab()
        routing_tabs = QTabWidget();
        layout.addWidget(routing_tabs)
        static_tab = QWidget();
        static_layout = QVBoxLayout(static_tab);
        self.static_route_table = QTableWidget(0, 4);
        self.static_route_table.setHorizontalHeaderLabels(
            ["Destination Prefix (예: 1.1.1.0/24)", "Next-Hop IP / Interface", "Metric", "VRF"]);
        self.static_route_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);
        static_btn_layout = QHBoxLayout();
        self.btn_add_static_route = QPushButton("정적 경로 추가");
        self.btn_remove_static_route = QPushButton("정적 경로 삭제");
        static_btn_layout.addWidget(self.btn_add_static_route);
        static_btn_layout.addWidget(self.btn_remove_static_route);
        static_layout.addLayout(static_btn_layout);
        static_layout.addWidget(self.static_route_table);
        routing_tabs.addTab(static_tab, "Static")
        ospf_tab = QWidget();
        ospf_layout = QVBoxLayout(ospf_tab);
        group_ospf_global = QGroupBox("OSPF Global Settings");
        form_ospf_global = QFormLayout();
        self.cb_ospf_enabled = QCheckBox("Enable OSPF");
        self.le_ospf_process_id = QLineEdit("1");
        self.le_ospf_router_id = QLineEdit();
        form_ospf_global.addRow(self.cb_ospf_enabled);
        form_ospf_global.addRow("Process ID:", self.le_ospf_process_id);
        form_ospf_global.addRow("Router ID:", self.le_ospf_router_id);
        group_ospf_global.setLayout(form_ospf_global);
        ospf_layout.addWidget(group_ospf_global);
        group_ospf_networks = QGroupBox("Networks to Advertise");
        layout_ospf_networks = QVBoxLayout(group_ospf_networks);
        self.ospf_network_table = QTableWidget(0, 3);
        self.ospf_network_table.setHorizontalHeaderLabels(["Network Address", "Wildcard Mask", "Area"]);
        self.ospf_network_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);
        ospf_net_btn_layout = QHBoxLayout();
        self.btn_add_ospf_net = QPushButton("네트워크 추가");
        self.btn_remove_ospf_net = QPushButton("네트워크 삭제");
        ospf_net_btn_layout.addWidget(self.btn_add_ospf_net);
        ospf_net_btn_layout.addWidget(self.btn_remove_ospf_net);
        layout_ospf_networks.addLayout(ospf_net_btn_layout);
        layout_ospf_networks.addWidget(self.ospf_network_table);
        ospf_layout.addWidget(group_ospf_networks);
        routing_tabs.addTab(ospf_tab, "OSPF")
        eigrp_tab = QWidget();
        eigrp_layout = QVBoxLayout(eigrp_tab);
        group_eigrp_global = QGroupBox("EIGRP Global Settings");
        form_eigrp_global = QFormLayout();
        self.cb_eigrp_enabled = QCheckBox("Enable EIGRP");
        self.le_eigrp_as_number = QLineEdit("100");
        self.le_eigrp_router_id = QLineEdit();
        form_eigrp_global.addRow(self.cb_eigrp_enabled);
        form_eigrp_global.addRow("AS Number:", self.le_eigrp_as_number);
        form_eigrp_global.addRow("Router ID:", self.le_eigrp_router_id);
        group_eigrp_global.setLayout(form_eigrp_global);
        eigrp_layout.addWidget(group_eigrp_global);
        group_eigrp_networks = QGroupBox("Networks to Advertise");
        layout_eigrp_networks = QVBoxLayout(group_eigrp_networks);
        self.eigrp_network_table = QTableWidget(0, 2);
        self.eigrp_network_table.setHorizontalHeaderLabels(["Network Address", "Wildcard Mask (Optional)"]);
        self.eigrp_network_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);
        eigrp_net_btn_layout = QHBoxLayout();
        self.btn_add_eigrp_net = QPushButton("네트워크 추가");
        self.btn_remove_eigrp_net = QPushButton("네트워크 삭제");
        eigrp_net_btn_layout.addWidget(self.btn_add_eigrp_net);
        eigrp_net_btn_layout.addWidget(self.btn_remove_eigrp_net);
        layout_eigrp_networks.addLayout(eigrp_net_btn_layout);
        layout_eigrp_networks.addWidget(self.eigrp_network_table);
        eigrp_layout.addWidget(group_eigrp_networks);
        routing_tabs.addTab(eigrp_tab, "EIGRP")
        bgp_tab = QWidget();
        bgp_layout = QVBoxLayout(bgp_tab);
        group_bgp_global = QGroupBox("BGP Global Settings");
        form_bgp_global = QFormLayout();
        self.cb_bgp_enabled = QCheckBox("Enable BGP");
        self.le_bgp_as_number = QLineEdit("65001");
        self.le_bgp_router_id = QLineEdit();
        form_bgp_global.addRow(self.cb_bgp_enabled);
        form_bgp_global.addRow("Local AS Number:", self.le_bgp_as_number);
        form_bgp_global.addRow("Router ID:", self.le_bgp_router_id);
        group_bgp_global.setLayout(form_bgp_global);
        bgp_layout.addWidget(group_bgp_global);
        group_bgp_neighbors = QGroupBox("BGP Neighbors");
        layout_bgp_neighbors = QVBoxLayout(group_bgp_neighbors);
        self.bgp_neighbor_table = QTableWidget(0, 6);
        self.bgp_neighbor_table.setHorizontalHeaderLabels(
            ["Neighbor IP", "Remote AS", "Description", "Update Source", "Route-Map IN", "Route-Map OUT"]);
        self.bgp_neighbor_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);
        bgp_neighbor_btn_layout = QHBoxLayout();
        self.btn_add_bgp_neighbor = QPushButton("Neighbor 추가");
        self.btn_remove_bgp_neighbor = QPushButton("Neighbor 삭제");
        bgp_neighbor_btn_layout.addWidget(self.btn_add_bgp_neighbor);
        bgp_neighbor_btn_layout.addWidget(self.btn_remove_bgp_neighbor);
        layout_bgp_neighbors.addLayout(bgp_neighbor_btn_layout);
        layout_bgp_neighbors.addWidget(self.bgp_neighbor_table);
        bgp_layout.addWidget(group_bgp_neighbors);
        group_bgp_networks = QGroupBox("Networks to Advertise");
        layout_bgp_networks = QVBoxLayout(group_bgp_networks);
        layout_bgp_networks.addWidget(QLabel("광고할 네트워크 Prefix 목록 (한 줄에 하나씩)"));
        self.te_bgp_networks = QPlainTextEdit();
        layout_bgp_networks.addWidget(self.te_bgp_networks);
        bgp_layout.addWidget(group_bgp_networks);
        routing_tabs.addTab(bgp_tab, "BGP")
        return tab

    def _create_ha_tab(self):
        tab, layout = self._create_scrollable_tab()
        self.group_svl = QGroupBox("StackWise Virtual (IOS-XE only)");
        form_svl = QFormLayout();
        self.cb_svl_enabled = QCheckBox("Enable StackWise Virtual");
        self.le_svl_domain = QLineEdit();
        form_svl.addRow(self.cb_svl_enabled);
        form_svl.addRow("Domain ID:", self.le_svl_domain);
        self.group_svl.setLayout(form_svl);
        layout.addWidget(self.group_svl)
        self.group_vpc = QGroupBox("vPC - Virtual Port-Channel (NX-OS only)");
        form_vpc = QFormLayout();
        self.cb_vpc_enabled = QCheckBox("Enable vPC");
        self.le_vpc_domain = QLineEdit();
        self.le_vpc_peer_keepalive = QLineEdit();
        form_vpc.addRow(self.cb_vpc_enabled);
        form_vpc.addRow("Domain ID:", self.le_vpc_domain);
        form_vpc.addRow("Peer-Keepalive:", self.le_vpc_peer_keepalive);
        self.group_vpc.setLayout(form_vpc);
        layout.addWidget(self.group_vpc)
        layout.addStretch()
        return tab

    def _create_security_tab(self):
        tab, layout = self._create_scrollable_tab()
        group_aaa = QGroupBox("AAA");
        form_aaa = QFormLayout();
        self.cb_aaa_new_model = QCheckBox("aaa new-model 활성화");
        self.le_aaa_auth_login = QLineEdit("default group tacacs+ local");
        self.le_aaa_auth_exec = QLineEdit("default group tacacs+ local");
        self.aaa_server_table = QTableWidget(0, 3);
        self.aaa_server_table.setHorizontalHeaderLabels(["서버 종류 (tacacs+/radius)", "그룹 이름", "서버 IP 리스트 (쉼표로 구분)"]);
        self.aaa_server_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);
        self.btn_add_aaa_group = QPushButton("AAA 서버 그룹 추가");
        self.btn_remove_aaa_group = QPushButton("AAA 서버 그룹 삭제");
        form_aaa.addRow(self.cb_aaa_new_model);
        form_aaa.addRow("Authentication Login:", self.le_aaa_auth_login);
        form_aaa.addRow("Authorization Exec:", self.le_aaa_auth_exec);
        form_aaa.addRow(self.btn_add_aaa_group, self.btn_remove_aaa_group);
        form_aaa.addRow(self.aaa_server_table);
        group_aaa.setLayout(form_aaa);
        layout.addWidget(group_aaa)
        group_users = QGroupBox("Local User Accounts");
        users_layout = QVBoxLayout();
        self.users_table = QTableWidget(0, 3);
        self.users_table.setHorizontalHeaderLabels(["Username", "Privilege (1-15)", "Password"]);
        self.users_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);
        users_button_layout = QHBoxLayout();
        self.btn_add_user = QPushButton("사용자 추가");
        self.btn_remove_user = QPushButton("사용자 삭제");
        users_button_layout.addWidget(self.btn_add_user);
        users_button_layout.addWidget(self.btn_remove_user);
        users_layout.addLayout(users_button_layout);
        users_layout.addWidget(self.users_table);
        group_users.setLayout(users_layout);
        layout.addWidget(group_users)
        group_line = QGroupBox("Line Configuration (Console/VTY)");
        form_line = QFormLayout();
        self.le_con_exec_timeout = QLineEdit("15 0");
        self.cb_con_logging_sync = QCheckBox();
        self.cb_con_logging_sync.setChecked(True);
        self.cb_con_auth_aaa = QCheckBox("Console Login Authentication (AAA)");
        self.le_con_auth_method = QLineEdit("default");
        self.le_con_auth_method.setEnabled(False);
        self.cb_con_auth_aaa.toggled.connect(self.le_con_auth_method.setEnabled);
        self.le_vty_range = QLineEdit("0 4");
        self.le_vty_exec_timeout = QLineEdit("15 0");
        self.combo_vty_transport = QComboBox();
        self.combo_vty_transport.addItems(["ssh", "telnet", "none", "all"]);
        self.combo_vty_transport.setCurrentText("ssh");
        form_line.addRow("Console Timeout (min sec):", self.le_con_exec_timeout);
        form_line.addRow("Console Logging Synchronous:", self.cb_con_logging_sync);
        form_line.addRow(self.cb_con_auth_aaa, self.le_con_auth_method);
        form_line.addRow("VTY Line Range:", self.le_vty_range);
        form_line.addRow("VTY Timeout (min sec):", self.le_vty_exec_timeout);
        form_line.addRow("VTY Transport Input:", self.combo_vty_transport);
        group_line.setLayout(form_line);
        layout.addWidget(group_line)
        group_snmp = QGroupBox("SNMP");
        snmp_layout = QVBoxLayout();
        snmp_form = QFormLayout();
        self.le_snmp_location = QLineEdit();
        self.le_snmp_contact = QLineEdit();
        snmp_form.addRow("Location:", self.le_snmp_location);
        snmp_form.addRow("Contact:", self.le_snmp_contact);
        snmp_layout.addLayout(snmp_form);
        group_snmp_v2 = QGroupBox("SNMPv2c Communities");
        snmp_v2_layout = QVBoxLayout();
        self.snmp_community_table = QTableWidget(0, 3);
        self.snmp_community_table.setHorizontalHeaderLabels(
            ["Community String", "Permission (RO/RW)", "ACL (Optional)"]);
        self.snmp_community_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);
        snmp_v2_button_layout = QHBoxLayout();
        self.btn_add_snmp = QPushButton("v2c Community 추가");
        self.btn_remove_snmp = QPushButton("v2c Community 삭제");
        snmp_v2_button_layout.addWidget(self.btn_add_snmp);
        snmp_v2_button_layout.addWidget(self.btn_remove_snmp);
        snmp_v2_layout.addLayout(snmp_v2_button_layout);
        snmp_v2_layout.addWidget(self.snmp_community_table);
        group_snmp_v2.setLayout(snmp_v2_layout);
        snmp_layout.addWidget(group_snmp_v2);
        group_snmp_v3 = QGroupBox("SNMPv3 Users");
        snmp_v3_layout = QVBoxLayout();
        self.snmp_v3_user_table = QTableWidget(0, 6);
        self.snmp_v3_user_table.setHorizontalHeaderLabels(
            ["Username", "Group", "Auth (md5/sha)", "Auth Pass", "Priv (des/aes)", "Priv Pass"]);
        self.snmp_v3_user_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);
        snmp_v3_button_layout = QHBoxLayout();
        self.btn_add_snmp_v3 = QPushButton("v3 User 추가");
        self.btn_remove_snmp_v3 = QPushButton("v3 User 삭제");
        snmp_v3_button_layout.addWidget(self.btn_add_snmp_v3);
        snmp_v3_button_layout.addWidget(self.btn_remove_snmp_v3);
        snmp_v3_layout.addLayout(snmp_v3_button_layout);
        snmp_v3_layout.addWidget(self.snmp_v3_user_table);
        group_snmp_v3.setLayout(snmp_v3_layout);
        snmp_layout.addWidget(group_snmp_v3);
        group_snmp.setLayout(snmp_layout);
        layout.addWidget(group_snmp)
        group_hardening = QGroupBox("Security Hardening");
        form_hardening = QFormLayout();
        self.cb_no_ip_http = QCheckBox("no ip http server & secure-server");
        self.cb_no_ip_http.setChecked(True);
        self.cb_no_cdp = QCheckBox("no cdp run / no feature cdp");
        self.cb_lldp = QCheckBox("lldp run / feature lldp");
        self.cb_lldp.setChecked(True);
        form_hardening.addRow(self.cb_no_ip_http);
        form_hardening.addRow(self.cb_no_cdp);
        form_hardening.addRow(self.cb_lldp);
        group_hardening.setLayout(form_hardening);
        layout.addWidget(group_hardening)
        layout.addStretch()
        return tab

    # --- 신호 연결 메서드 ---
    def _connect_signals(self):
        # 장비 관리
        self.btn_add_device.clicked.connect(self.ui_add_device)
        self.btn_remove_device.clicked.connect(self.ui_remove_device)
        self.btn_apply.clicked.connect(self.run_config_task)
        self.btn_fetch_info.clicked.connect(self._fetch_device_info)
        self.combo_os_type.currentTextChanged.connect(self._update_ui_for_os)

        # 인터페이스 탭
        self.btn_add_interface.clicked.connect(self.ui_add_interface)
        self.btn_add_port_channel.clicked.connect(self.ui_add_port_channel)
        self.btn_remove_interface.clicked.connect(
            lambda: self.interface_list.takeItem(self.interface_list.currentRow()))
        self.interface_list.itemSelectionChanged.connect(self._on_interface_selected)

        # 인터페이스 설정값 변경 시 자동 저장
        for widget in [self.cb_if_shutdown, self.cb_stp_portfast, self.cb_stp_bpduguard, self.cb_ps_enabled,
                       self.cb_udld_enabled]: widget.toggled.connect(self._save_interface_data)
        for widget in [self.le_if_description, self.le_access_vlan, self.le_voice_vlan, self.le_trunk_native,
                       self.le_trunk_allowed, self.le_routed_ip, self.le_channel_group_id, self.le_ps_max_mac,
                       self.le_sc_broadcast, self.le_sc_multicast, self.le_sc_unicast]: widget.editingFinished.connect(
            self._save_interface_data)
        for widget in [self.combo_channel_group_mode, self.combo_ps_violation, self.combo_sc_action,
                       self.combo_udld_mode]: widget.currentTextChanged.connect(self._save_interface_data)
        self.combo_if_type.currentTextChanged.connect(self._update_dynamic_interface_ui)
        self.combo_if_mode.currentTextChanged.connect(self._update_dynamic_interface_ui)



        # VLAN 탭
        if hasattr(self, 'btn_add_vlan'):
            self.btn_add_vlan.clicked.connect(lambda: self.ui_add_table_row(self.vlan_table))
            self.btn_remove_vlan.clicked.connect(lambda: self.ui_remove_table_row(self.vlan_table))
            self.vlan_table.itemSelectionChanged.connect(self._on_vlan_selected)
            self.cb_svi_enabled.toggled.connect(self._save_svi_data);
            self.le_svi_ip.editingFinished.connect(self._save_svi_data);
            self.cb_fhrp_enabled.toggled.connect(self._save_svi_data);
            self.le_fhrp_group.editingFinished.connect(self._save_svi_data);
            self.le_fhrp_vip.editingFinished.connect(self._save_svi_data);
            self.le_fhrp_priority.editingFinished.connect(self._save_svi_data);
            self.cb_fhrp_preempt.toggled.connect(self._save_svi_data)
            self.btn_add_helper.clicked.connect(lambda: self.ui_add_table_row(self.dhcp_helper_table));
            self.btn_remove_helper.clicked.connect(lambda: self.ui_remove_table_row(self.dhcp_helper_table));
            self.dhcp_helper_table.itemChanged.connect(self._save_svi_data)

        # Switching 탭
        self.combo_stp_mode.currentTextChanged.connect(self._update_mst_ui_visibility)
        self.btn_add_mst_instance.clicked.connect(lambda: self.ui_add_table_row(self.mst_instance_table))
        self.btn_remove_mst_instance.clicked.connect(lambda: self.ui_remove_table_row(self.mst_instance_table))

        # Routing 탭
        self.btn_add_static_route.clicked.connect(lambda: self.ui_add_table_row(self.static_route_table))
        self.btn_remove_static_route.clicked.connect(lambda: self.ui_remove_table_row(self.static_route_table))
        self.btn_add_ospf_net.clicked.connect(lambda: self.ui_add_table_row(self.ospf_network_table))
        self.btn_remove_ospf_net.clicked.connect(lambda: self.ui_remove_table_row(self.ospf_network_table))
        self.btn_add_eigrp_net.clicked.connect(lambda: self.ui_add_table_row(self.eigrp_network_table))
        self.btn_remove_eigrp_net.clicked.connect(lambda: self.ui_remove_table_row(self.eigrp_network_table))
        self.btn_add_bgp_neighbor.clicked.connect(lambda: self.ui_add_table_row(self.bgp_neighbor_table))
        self.btn_remove_bgp_neighbor.clicked.connect(lambda: self.ui_remove_table_row(self.bgp_neighbor_table))

        # 글로벌 탭
        self.btn_add_dns.clicked.connect(lambda: self.ui_add_table_row(self.dns_table));
        self.btn_remove_dns.clicked.connect(lambda: self.ui_remove_table_row(self.dns_table))
        self.btn_add_log_host.clicked.connect(lambda: self.ui_add_table_row(self.logging_table));
        self.btn_remove_log_host.clicked.connect(lambda: self.ui_remove_table_row(self.logging_table))
        self.btn_add_ntp.clicked.connect(lambda: self.ui_add_table_row(self.ntp_table));
        self.btn_remove_ntp.clicked.connect(lambda: self.ui_remove_table_row(self.ntp_table))
        self.combo_timezone.currentTextChanged.connect(self._on_timezone_changed);
        self.combo_mgmt_interface.currentTextChanged.connect(self._on_mgmt_interface_changed);
        self.cb_enable_banner.toggled.connect(self.te_banner_text.setEnabled);
        self.cb_archive_config.toggled.connect(self._on_archive_config_toggled);
        self.cb_archive_time_period.toggled.connect(self.le_archive_time_period.setEnabled)

        # 보안 탭
        self.btn_add_aaa_group.clicked.connect(lambda: self.ui_add_table_row(self.aaa_server_table));
        self.btn_remove_aaa_group.clicked.connect(lambda: self.ui_remove_table_row(self.aaa_server_table))
        self.btn_add_user.clicked.connect(lambda: self.ui_add_table_row(self.users_table));
        self.btn_remove_user.clicked.connect(lambda: self.ui_remove_table_row(self.users_table))
        self.btn_add_snmp.clicked.connect(lambda: self.ui_add_table_row(self.snmp_community_table));
        self.btn_remove_snmp.clicked.connect(lambda: self.ui_remove_table_row(self.snmp_community_table))
        self.btn_add_snmp_v3.clicked.connect(lambda: self.ui_add_table_row(self.snmp_v3_user_table));
        self.btn_remove_snmp_v3.clicked.connect(lambda: self.ui_remove_table_row(self.snmp_v3_user_table))

    # --- 핵심 로직 및 슬롯 메서드 ---
    def run_config_task(self):
        target_hosts = self._get_selected_devices()
        if not target_hosts: return
        user_input_data = self._gather_data_from_ui()
        os_type = self.combo_os_type.currentText()
        try:
            playbook_data = self.config_manager.generate_playbook(os_type, user_input_data)
            self.log_output.appendPlainText(f"===== {', '.join(target_hosts)}에 구성 적용 시작 ({os_type}) =====")
            status, result_stdout = self.ansible_engine.execute_configuration(target_hosts, playbook_data)
            self.log_output.appendPlainText("구성 적용 성공." if status == 'successful' else "구성 적용 실패.")
            self.log_output.appendPlainText("--- Ansible 실행 결과 (모의) ---");
            self.log_output.appendPlainText(result_stdout);
            self.log_output.appendPlainText("--------------------------\n")
        except Exception as e:
            self.log_output.appendPlainText(f"오류 발생: {str(e)}")

    def _fetch_device_info(self):
        selected_items = self.device_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "오류", "먼저 장비 목록에서 정보를 가져올 장비를 선택하세요.")
            return
        if len(selected_items) > 1:
            QMessageBox.warning(self, "오류", "정보 가져오기는 한 번에 하나의 장비만 선택할 수 있습니다.")
            return
        target_host = selected_items[0].text()
        os_type = self.combo_os_type.currentText()
        cred_dialog = CredentialsDialog(self)
        if cred_dialog.exec():
            credentials = cred_dialog.get_credentials()
            if not credentials['user'] or not credentials['pass']:
                QMessageBox.warning(self, "오류", "Username과 Password를 모두 입력해야 합니다.")
                return
            self.log_output.appendPlainText(f"[{target_host}] 정보 수집을 시작합니다...");
            QApplication.processEvents()
            success, result = self.ansible_engine.discover_facts(target_host, os_type, credentials)
            if success:
                self.log_output.appendPlainText(f"✓ [{target_host}] 정보 수집 성공!")
                self.interface_list.clear()
                if 'ansible_net_interfaces' in result:
                    for if_name in sorted(result['ansible_net_interfaces'].keys()):
                        self._add_interface_item(if_name)
                version = result.get('ansible_net_version', 'N/A');
                model = result.get('ansible_net_model', 'N/A')
                self.log_output.appendPlainText(f"  - 모델: {model}, OS 버전: {version}")
            else:
                self.log_output.appendPlainText(f"✗ [{target_host}] 정보 수집 실패!")
                error_details = result.get('details', str(result.get('error', '')))
                QMessageBox.critical(self, "정보 수집 실패", error_details)

    # --- 동적 UI 업데이트 메서드 ---
    def _update_ui_for_os(self):
        selected_os = self.combo_os_type.currentText();
        is_ios_xe = 'IOS-XE' in selected_os;
        is_nx_os = 'NX-OS' in selected_os
        ios_xe_only_msg = "이 기능은 IOS-XE에서만 사용 가능합니다.";
        nx_os_only_msg = "이 기능은 NX-OS에서만 사용 가능합니다."
        if hasattr(self, 'group_archive'): self.group_archive.setEnabled(is_ios_xe); self.group_archive.setToolTip(
            ios_xe_only_msg if not is_ios_xe else "")
        if hasattr(self, 'cb_summer_time'): self.cb_summer_time.setEnabled(is_ios_xe); self.cb_summer_time.setToolTip(
            ios_xe_only_msg if not is_ios_xe else "")
        if hasattr(self, 'le_ntp_master_stratum'): self.le_ntp_master_stratum.setEnabled(
            is_ios_xe); self.le_ntp_master_stratum.setToolTip(ios_xe_only_msg if not is_ios_xe else "")
        if hasattr(self, 'group_svl'): self.group_svl.setEnabled(is_ios_xe); self.group_svl.setToolTip(
            ios_xe_only_msg if not is_ios_xe else "")
        if hasattr(self, 'group_vpc'): self.group_vpc.setEnabled(is_nx_os); self.group_vpc.setToolTip(
            nx_os_only_msg if not is_nx_os else "")
        if hasattr(self, 'combo_vty_transport'): self.combo_vty_transport.setEnabled(
            is_ios_xe); self.combo_vty_transport.setToolTip(ios_xe_only_msg if not is_ios_xe else "")
        if hasattr(self, 'cb_archive_config'): self._on_archive_config_toggled(self.cb_archive_config.isChecked())

    def _update_dynamic_interface_ui(self, *args):
        selected_items = self.interface_list.selectedItems()
        if not selected_items: return
        current_mode = self.combo_if_mode.currentText()
        if current_mode == "--- Multiple Values ---":
            self.mode_stack.setCurrentIndex(-1)
        else:
            if current_mode == "L2 Access":
                self.mode_stack.setCurrentIndex(0)
            elif current_mode == "L2 Trunk":
                self.mode_stack.setCurrentIndex(1)
            elif current_mode == "L3 Routed":
                self.mode_stack.setCurrentIndex(2)
            elif current_mode == "Port-Channel Member":
                self.mode_stack.setCurrentIndex(3)
        all_l2 = all("L2" in item.data(Qt.UserRole)['mode'] for item in selected_items);
        self.group_if_stp.setEnabled(all_l2);
        self.group_if_port_security.setEnabled(all_l2)
        all_fiber = all(item.data(Qt.UserRole)['type'] == "Fiber" for item in selected_items);
        self.group_if_udld.setEnabled(all_fiber)
        self._save_interface_data()

    # --- 탭별 데이터 관리 메서드 ---
    def _on_vlan_selected(self):
        selected_items = self.vlan_table.selectedItems()
        if not selected_items: self.group_svi.setEnabled(False); self.svi_label.setText(
            "상단 테이블에서 설정을 원하는 VLAN을 선택하세요."); return
        self.current_vlan_item = selected_items[0].row();
        vlan_id_item = self.vlan_table.item(self.current_vlan_item, 0);
        vlan_id = vlan_id_item.text();
        self.svi_label.setText(f"VLAN {vlan_id}의 SVI 설정")
        svi_data = vlan_id_item.data(Qt.UserRole) or {}
        self.cb_svi_enabled.setChecked(svi_data.get('enabled', False));
        self.le_svi_ip.setText(svi_data.get('ip', ''))
        fhrp_data = svi_data.get('fhrp', {});
        self.cb_fhrp_enabled.setChecked(fhrp_data.get('enabled', False));
        self.le_fhrp_group.setText(fhrp_data.get('group', ''));
        self.le_fhrp_vip.setText(fhrp_data.get('vip', ''));
        self.le_fhrp_priority.setText(fhrp_data.get('priority', ''));
        self.cb_fhrp_preempt.setChecked(fhrp_data.get('preempt', False))
        self.dhcp_helper_table.setRowCount(0)
        for helper in svi_data.get('dhcp_helpers',
                                   []): row_pos = self.dhcp_helper_table.rowCount(); self.dhcp_helper_table.insertRow(
            row_pos); self.dhcp_helper_table.setItem(row_pos, 0, QTableWidgetItem(helper))
        self.group_svi.setEnabled(True)

    def _save_svi_data(self):
        if not hasattr(self, 'current_vlan_item') or self.current_vlan_item is None: return
        vlan_id_item = self.vlan_table.item(self.current_vlan_item, 0)
        if not vlan_id_item: return
        helpers = [self.dhcp_helper_table.item(row, 0).text() for row in range(self.dhcp_helper_table.rowCount()) if
                   self.dhcp_helper_table.item(row, 0) and self.dhcp_helper_table.item(row, 0).text()]
        svi_data = {'enabled': self.cb_svi_enabled.isChecked(), 'ip': self.le_svi_ip.text(),
                    'fhrp': {'enabled': self.cb_fhrp_enabled.isChecked(), 'group': self.le_fhrp_group.text(),
                             'vip': self.le_fhrp_vip.text(), 'priority': self.le_fhrp_priority.text(),
                             'preempt': self.cb_fhrp_preempt.isChecked()}, 'dhcp_helpers': helpers}
        vlan_id_item.setData(Qt.UserRole, svi_data)

    def _on_interface_selected(self):
        selected_items = self.interface_list.selectedItems()
        if not selected_items: self.config_area_widget.setVisible(False); return
        self._block_interface_signals(True)
        base_config = selected_items[0].data(Qt.UserRole);
        common_config = deepcopy(base_config)
        if len(selected_items) > 1:
            self.if_label.setText(f"'{len(selected_items)}개 인터페이스 동시 편집'")
            for item in selected_items[1:]:
                current_config = item.data(Qt.UserRole)
                for key, value in base_config.items():
                    if key not in common_config: continue
                    if isinstance(value, dict):
                        for sub_key, sub_value in value.items():
                            if sub_key in common_config[key] and sub_value != current_config[key][sub_key]: del \
                            common_config[key][sub_key]
                    elif value != current_config[key]:
                        del common_config[key]
        else:
            self.if_label.setText(f"'{base_config['name']}' 설정")
        self.cb_if_shutdown.setChecked(common_config.get('shutdown', False));
        self.le_if_description.setText(common_config.get('description', ''));
        self.combo_if_type.setCurrentText(common_config.get('type', '--- Multiple Values ---'));
        self.combo_if_mode.setCurrentText(common_config.get('mode', '--- Multiple Values ---'))
        self.le_access_vlan.setText(common_config.get('access', {}).get('vlan', ''));
        self.le_voice_vlan.setText(common_config.get('access', {}).get('voice_vlan', ''));
        self.le_trunk_native.setText(common_config.get('trunk', {}).get('native_vlan', ''));
        self.le_trunk_allowed.setText(common_config.get('trunk', {}).get('allowed_vlans', ''));
        self.le_routed_ip.setText(common_config.get('routed', {}).get('ip', ''));
        self.le_channel_group_id.setText(common_config.get('pc_member', {}).get('group_id', ''));
        self.combo_channel_group_mode.setCurrentText(common_config.get('pc_member', {}).get('mode', 'active'))
        self.cb_stp_portfast.setChecked(common_config.get('stp', {}).get('portfast', False));
        self.cb_stp_bpduguard.setChecked(common_config.get('stp', {}).get('bpduguard', False))
        ps_common = common_config.get('port_security', {});
        self.cb_ps_enabled.setChecked(ps_common.get('enabled', False));
        self.le_ps_max_mac.setText(ps_common.get('max_mac', ''));
        self.combo_ps_violation.setCurrentText(ps_common.get('violation', '--- Multiple Values ---'))
        for w, v in {self.le_if_description: 'description', self.combo_if_type: 'type',
                     self.combo_if_mode: 'mode'}.items(): w.setProperty("placeholderText",
                                                                        "--- Multiple Values ---" if v not in common_config else "")
        self._update_dynamic_interface_ui();
        self.config_area_widget.setVisible(True);
        self._block_interface_signals(False)

    def _save_interface_data(self):
        selected_items = self.interface_list.selectedItems()
        if not selected_items: return
        for item in selected_items:
            config = item.data(Qt.UserRole)
            if self.le_if_description.placeholderText() != "--- Multiple Values ---": config[
                'description'] = self.le_if_description.text()
            if self.combo_if_type.currentText() != "--- Multiple Values ---": config[
                'type'] = self.combo_if_type.currentText()
            if self.combo_if_mode.currentText() != "--- Multiple Values ---": config[
                'mode'] = self.combo_if_mode.currentText()
            config['shutdown'] = self.cb_if_shutdown.isChecked();
            config['access']['vlan'] = self.le_access_vlan.text();
            config['access']['voice_vlan'] = self.le_voice_vlan.text();
            config['trunk']['native_vlan'] = self.le_trunk_native.text();
            config['trunk']['allowed_vlans'] = self.le_trunk_allowed.text();
            config['routed']['ip'] = self.le_routed_ip.text();
            config['pc_member']['group_id'] = self.le_channel_group_id.text();
            config['pc_member']['mode'] = self.combo_channel_group_mode.currentText();
            config['stp']['portfast'] = self.cb_stp_portfast.isChecked();
            config['stp']['bpduguard'] = self.cb_stp_bpduguard.isChecked();
            config['port_security']['enabled'] = self.cb_ps_enabled.isChecked();
            config['port_security']['max_mac'] = self.le_ps_max_mac.text();
            config['port_security']['violation'] = self.combo_ps_violation.currentText();
            config['udld']['enabled'] = self.cb_udld_enabled.isChecked();
            config['udld']['mode'] = self.combo_udld_mode.currentText()
            sc = config['storm_control'];
            sc['broadcast'] = self.le_sc_broadcast.text();
            sc['multicast'] = self.le_sc_multicast.text();
            sc['unicast'] = self.le_sc_unicast.text();
            sc['action'] = self.combo_sc_action.currentText()
            item.setData(Qt.UserRole, config)

    # --- UI 헬퍼 메서드 ---
    def ui_add_device(self):
        dialog = AddDevicesDialog(self);
        if dialog.exec(): self.device_list.addItems(dialog.get_devices())

    def ui_remove_device(self):
        for item in self.device_list.selectedItems(): self.device_list.takeItem(self.device_list.row(item))

    def ui_add_interface(self):
        dialog = AddInterfacesDialog(self)
        if dialog.exec():
            for if_name in dialog.get_interfaces():
                if not self.interface_list.findItems(if_name, Qt.MatchExactly): self._add_interface_item(if_name)

    def ui_add_port_channel(self):
        num, ok = QInputDialog.getInt(self, "Port-Channel 추가", "Port-Channel 번호 입력:", 1, 1, 4096)
        if ok: self._add_interface_item(f"Port-channel{num}")

    def ui_add_table_row(self, table_widget):
        table_widget.insertRow(table_widget.rowCount())

    def ui_remove_table_row(self, table_widget):
        current_row = table_widget.currentRow()
        if current_row > -1: table_widget.removeRow(current_row)

    # --- 내부 헬퍼 메서드 ---
    def _add_interface_item(self, interface_name):
        item = QListWidgetItem(interface_name)
        default_config = {'name': interface_name, 'is_port_channel': 'port-channel' in interface_name.lower(),
                          'shutdown': False, 'description': '', 'type': 'Copper', 'mode': 'L2 Access',
                          'access': {'vlan': '', 'voice_vlan': ''}, 'trunk': {'native_vlan': '', 'allowed_vlans': ''},
                          'routed': {'ip': ''}, 'pc_member': {'group_id': '', 'mode': 'active'},
                          'stp': {'portfast': False, 'bpduguard': False},
                          'port_security': {'enabled': False, 'max_mac': '1', 'violation': 'shutdown'},
                          'storm_control': {'broadcast': '', 'multicast': '', 'unicast': '', 'action': 'shutdown'},
                          'udld': {'enabled': False, 'mode': 'normal'}}
        if default_config['is_port_channel']: self.combo_if_mode.model().item(3).setEnabled(False)
        item.setData(Qt.UserRole, default_config)
        self.interface_list.addItem(item)

    def _block_interface_signals(self, block):
        widgets = [self.cb_if_shutdown, self.le_if_description, self.combo_if_type, self.combo_if_mode,
                   self.le_access_vlan, self.le_voice_vlan, self.le_trunk_native, self.le_trunk_allowed,
                   self.le_routed_ip, self.le_channel_group_id, self.combo_channel_group_mode, self.cb_stp_portfast,
                   self.cb_stp_bpduguard, self.cb_ps_enabled, self.le_ps_max_mac, self.combo_ps_violation,
                   self.le_sc_broadcast, self.le_sc_multicast, self.le_sc_unicast, self.combo_sc_action,
                   self.cb_udld_enabled, self.combo_udld_mode]
        for widget in widgets: widget.blockSignals(block)

    def _get_selected_devices(self):
        selected_items = self.device_list.selectedItems()
        if not selected_items: QMessageBox.warning(self, "경고", "장비를 먼저 선택해주세요."); return None
        return [item.text() for item in selected_items]

    def _gather_data_from_ui(self):
        """현재 UI의 모든 상태를 하나의 딕셔너리로 수집합니다."""
        # 장비 목록 수집
        devices = [self.device_list.item(i).text() for i in range(self.device_list.count())]

        settings = {'global': {}, 'interfaces': [], 'vlans': {}, 'switching': {}, 'routing': {}, 'ha': {},
                    'security': {}}

        s['mst'] = {
            'name': self.le_mst_name.text(),
            'revision': self.le_mst_revision.text(),
            'instances': [
                {'id': self.mst_instance_table.item(r, 0).text(), 'vlans': self.mst_instance_table.item(r, 1).text()}
                for r in range(self.mst_instance_table.rowCount()) if self.mst_instance_table.item(r, 0)]
        }
        s['vtp'] = {
            'enabled': self.cb_vtp_enabled.isChecked(),
            'mode': self.combo_vtp_mode.currentText(),
            'domain': self.le_vtp_domain.text(),
            'password': self.le_vtp_password.text(),
            'version': self.combo_vtp_version.currentText()
        }
        s['l2_security'] = {
            'dhcp_snooping_enabled': self.cb_dhcp_snooping_enabled.isChecked(),
            'dhcp_snooping_vlans': self.le_dhcp_snooping_vlans.text(),
            'dai_vlans': self.le_dai_vlans.text()
        }

        # 각 탭에서 데이터 수집 (기존 로직과 대부분 동일)
        g = settings['global'];
        g['hostname'] = self.le_hostname.text();
        g['service_timestamps'] = self.cb_service_timestamps.isChecked();
        g['service_password_encryption'] = self.cb_service_password_encryption.isChecked();
        g['service_call_home'] = self.cb_service_call_home.isChecked();
        g['domain_name'] = self.le_domain_name.text();
        g['dns_servers'] = [{'ip': self.dns_table.item(r, 0).text(),
                             'vrf': (self.dns_table.item(r, 1).text() if self.dns_table.item(r, 1) else '')} for r in
                            range(self.dns_table.rowCount()) if
                            self.dns_table.item(r, 0) and self.dns_table.item(r, 0).text()];
        g[
            'timezone'] = self.le_custom_timezone.text() if self.combo_timezone.currentText() == "Custom" else self.combo_timezone.currentText();
        g['summer_time'] = {'enabled': self.cb_summer_time.isChecked(), 'zone': self.le_summer_time_zone.text()};
        g['logging_level'] = self.combo_logging_level.currentText();
        g['logging_console'] = self.cb_logging_console.isChecked();
        g['logging_buffered'] = self.cb_logging_buffered.isChecked();
        g['logging_buffer_size'] = self.le_logging_buffer_size.text();
        g['logging_hosts'] = [{'ip': self.logging_table.item(r, 0).text(),
                               'vrf': (self.logging_table.item(r, 1).text() if self.logging_table.item(r, 1) else '')}
                              for r in range(self.logging_table.rowCount()) if
                              self.logging_table.item(r, 0) and self.logging_table.item(r, 0).text()];
        g['ntp_authenticate'] = self.cb_ntp_authenticate.isChecked();
        g['ntp_master_stratum'] = self.le_ntp_master_stratum.text();
        g['ntp_servers'] = [{'ip': self.ntp_table.item(r, 0).text(), 'prefer': (
            self.ntp_table.item(r, 1).text().lower() == 'true' if self.ntp_table.item(r, 1) else False),
                             'key_id': (self.ntp_table.item(r, 2).text() if self.ntp_table.item(r, 2) else ''),
                             'vrf': (self.ntp_table.item(r, 3).text() if self.ntp_table.item(r, 3) else '')} for r in
                            range(self.ntp_table.rowCount()) if
                            self.ntp_table.item(r, 0) and self.ntp_table.item(r, 0).text()];
        mgmt_interface = self.combo_mgmt_interface.currentText();
        g['management'] = {'interface': self.le_custom_mgmt_interface.text() if mgmt_interface == "Custom" else (
            "" if mgmt_interface == "None" else mgmt_interface), 'ip': self.le_mgmt_ip.text(),
                           'subnet': self.le_mgmt_subnet.text(), 'gateway': self.le_mgmt_gateway.text(),
                           'vrf': self.le_mgmt_vrf.text()};
        g['banner'] = {'enabled': self.cb_enable_banner.isChecked(), 'text': self.te_banner_text.toPlainText()};
        g['archive'] = {'enabled': self.cb_archive_config.isChecked(), 'path': self.le_archive_path.text(),
                        'max_files': self.le_archive_max_files.text(),
                        'time_period_enabled': self.cb_archive_time_period.isChecked(),
                        'time_period': self.le_archive_time_period.text()}
        settings['interfaces'] = [self.interface_list.item(i).data(Qt.UserRole) for i in
                                  range(self.interface_list.count()) if self.interface_list.item(i).data(Qt.UserRole)]
        settings['vlans']['enable_routing'] = self.cb_ip_routing.isChecked();
        settings['vlans']['list'] = [{'id': self.vlan_table.item(r, 0).text(),
                                      'name': (self.vlan_table.item(r, 1).text() if self.vlan_table.item(r, 1) else ''),
                                      'description': (
                                          self.vlan_table.item(r, 2).text() if self.vlan_table.item(r, 2) else ''),
                                      'svi': self.vlan_table.item(r, 0).data(Qt.UserRole) or {}} for r in
                                     range(self.vlan_table.rowCount()) if
                                     self.vlan_table.item(r, 0) and self.vlan_table.item(r, 0).text()]
        s = settings['switching'];
        s['stp_mode'] = self.combo_stp_mode.currentText();
        s['stp_portfast_default'] = self.cb_stp_portfast_default.isChecked();
        s['stp_bpduguard_default'] = self.cb_stp_bpduguard_default.isChecked();
        s['stp_priority'] = self.le_stp_priority.text()
        if hasattr(self, 'cb_svl_enabled'): ha = settings['ha']; ha['svl'] = {
            'enabled': self.cb_svl_enabled.isChecked(), 'domain': self.le_svl_domain.text()}; ha['vpc'] = {
            'enabled': self.cb_vpc_enabled.isChecked(), 'domain': self.le_vpc_domain.text(),
            'peer_keepalive': self.le_vpc_peer_keepalive.text()}
        sec = settings['security'];
        sec['aaa_new_model'] = self.cb_aaa_new_model.isChecked();
        sec['aaa_auth_login'] = self.le_aaa_auth_login.text();
        sec['aaa_auth_exec'] = self.le_aaa_auth_exec.text();
        sec['aaa_groups'] = [
            {'type': self.aaa_server_table.item(r, 0).text(), 'group_name': self.aaa_server_table.item(r, 1).text(),
             'servers': [s.strip() for s in self.aaa_server_table.item(r, 2).text().split(',') if s.strip()]} for r in
            range(self.aaa_server_table.rowCount()) if self.aaa_server_table.item(r, 1)];
        sec['local_users'] = [{'username': self.users_table.item(r, 0).text(), 'privilege': (
            self.users_table.item(r, 1).text() if self.users_table.item(r, 1) else '1'),
                               'password': (self.users_table.item(r, 2).text() if self.users_table.item(r, 2) else '')}
                              for r in range(self.users_table.rowCount()) if
                              self.users_table.item(r, 0) and self.users_table.item(r, 0).text()];
        sec['line_config'] = {'con_timeout': self.le_con_exec_timeout.text(),
                              'con_logging_sync': self.cb_con_logging_sync.isChecked(),
                              'con_auth_aaa': self.cb_con_auth_aaa.isChecked(),
                              'con_auth_method': self.le_con_auth_method.text(), 'vty_range': self.le_vty_range.text(),
                              'vty_timeout': self.le_vty_exec_timeout.text(),
                              'vty_transport': self.combo_vty_transport.currentText()};
        sec['snmp'] = {'location': self.le_snmp_location.text(), 'contact': self.le_snmp_contact.text(),
                       'communities': [{'community': self.snmp_community_table.item(r, 0).text(), 'permission': (
                           self.snmp_community_table.item(r, 1).text() if self.snmp_community_table.item(r,
                                                                                                         1) else 'RO'),
                                        'acl': (self.snmp_community_table.item(r,
                                                                               2).text() if self.snmp_community_table.item(
                                            r, 2) else '')} for r in range(self.snmp_community_table.rowCount()) if
                                       self.snmp_community_table.item(r, 0)], 'v3_users': [
                {'username': self.snmp_v3_user_table.item(r, 0).text(),
                 'group': self.snmp_v3_user_table.item(r, 1).text(),
                 'auth_proto': self.snmp_v3_user_table.item(r, 2).text(),
                 'auth_pass': self.snmp_v3_user_table.item(r, 3).text(),
                 'priv_proto': self.snmp_v3_user_table.item(r, 4).text(),
                 'priv_pass': self.snmp_v3_user_table.item(r, 5).text()} for r in
                range(self.snmp_v3_user_table.rowCount()) if
                self.snmp_v3_user_table.item(r, 0) and self.snmp_v3_user_table.item(r, 0).text()]};
        sec['hardening'] = {'no_ip_http': self.cb_no_ip_http.isChecked(), 'no_cdp': self.cb_no_cdp.isChecked(),
                            'lldp': self.cb_lldp.isChecked()}
        # Switching Tab
        s = data['switching']
        s['stp_mode'] = self.combo_stp_mode.currentText()
        s['stp_priority'] = self.le_stp_priority.text()
        s['stp_portfast_default'] = self.cb_stp_portfast_default.isChecked()
        s['stp_bpduguard_default'] = self.cb_stp_bpduguard_default.isChecked()
        s['stp_bpdufilter_default'] = self.cb_stp_bpdufilter_default.isChecked()
        s['stp_loopguard_default'] = self.cb_stp_loopguard_default.isChecked()

        # Routing Tab
        r = settings['routing']
        r['static_routes'] = [
            {'prefix': self.static_route_table.item(i, 0).text(), 'nexthop': self.static_route_table.item(i, 1).text(),
             'metric': self.static_route_table.item(i, 2).text(), 'vrf': self.static_route_table.item(i, 3).text()} for
            i in range(self.static_route_table.rowCount()) if self.static_route_table.item(i, 0)]
        r['ospf'] = {'enabled': self.cb_ospf_enabled.isChecked(), 'process_id': self.le_ospf_process_id.text(),
                     'router_id': self.le_ospf_router_id.text(), 'networks': [
                {'prefix': self.ospf_network_table.item(i, 0).text(),
                 'wildcard': self.ospf_network_table.item(i, 1).text(),
                 'area': self.ospf_network_table.item(i, 2).text()} for i in range(self.ospf_network_table.rowCount())
                if self.ospf_network_table.item(i, 0)]}
        r['eigrp'] = {'enabled': self.cb_eigrp_enabled.isChecked(), 'as_number': self.le_eigrp_as_number.text(),
                      'router_id': self.le_eigrp_router_id.text(), 'networks': [
                {'prefix': self.eigrp_network_table.item(i, 0).text(),
                 'wildcard': self.eigrp_network_table.item(i, 1).text()} for i in
                range(self.eigrp_network_table.rowCount()) if self.eigrp_network_table.item(i, 0)]}
        r['bgp'] = {'enabled': self.cb_bgp_enabled.isChecked(), 'as_number': self.le_bgp_as_number.text(),
                    'router_id': self.le_bgp_router_id.text(), 'neighbors': [
                {'ip': self.bgp_neighbor_table.item(i, 0).text(),
                 'remote_as': self.bgp_neighbor_table.item(i, 1).text(),
                 'description': self.bgp_neighbor_table.item(i, 2).text(),
                 'update_source': self.bgp_neighbor_table.item(i, 3).text(),
                 'rmap_in': self.bgp_neighbor_table.item(i, 4).text(),
                 'rmap_out': self.bgp_neighbor_table.item(i, 5).text()} for i in
                range(self.bgp_neighbor_table.rowCount()) if self.bgp_neighbor_table.item(i, 0)],
                    'networks': [line.strip() for line in self.te_bgp_networks.toPlainText().splitlines() if
                                 line.strip()]}

        return {
            "devices": devices,
            "settings": settings
        }

    def _on_timezone_changed(self, timezone):
        self.le_custom_timezone.setEnabled(timezone == "Custom")
        if timezone != "Custom": self.le_custom_timezone.clear()

    def _on_mgmt_interface_changed(self, interface):
        self.le_custom_mgmt_interface.setEnabled(interface == "Custom")
        if interface != "Custom": self.le_custom_mgmt_interface.clear()

    def _on_archive_config_toggled(self, checked):
        if hasattr(self, 'le_archive_path'):
            self.le_archive_path.setEnabled(checked);
            self.le_archive_max_files.setEnabled(checked);
            self.cb_archive_time_period.setEnabled(checked);
            self.le_archive_time_period.setEnabled(checked and self.cb_archive_time_period.isChecked())
            if not checked: self.le_archive_path.clear(); self.le_archive_max_files.clear(); self.cb_archive_time_period.setChecked(
                False); self.le_archive_time_period.clear()

    def _new_config_profile(self):
        reply = QMessageBox.question(self, "새 구성", "현재 설정을 지우고 새로 시작하시겠습니까?", QMessageBox.Yes | QMessageBox.No,
                                     QMessageBox.No)
        if reply == QMessageBox.Yes:
            # 주요 위젯 초기화
            self.le_hostname.clear()
            self.interface_list.clear()
            self.vlan_table.setRowCount(0)
            self.device_list.clear()
            # ... 다른 모든 필드 초기화 로직을 여기에 추가 ...
            self.current_config_path = None
            self.log_output.appendPlainText("UI가 초기화되었습니다.")

    def _load_config_profile(self):
        path, _ = QFileDialog.getOpenFileName(self, "구성 열기", "", "JSON Files (*.json)")
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                self._apply_data_to_ui(config_data)
                self.current_config_path = path
                self.log_output.appendPlainText(f"'{os.path.basename(path)}' 구성을 불러왔습니다.")
            except Exception as e:
                QMessageBox.critical(self, "오류", f"구성을 불러오는 중 오류 발생:\n{e}")

    def _save_config_profile(self):
        path, _ = QFileDialog.getSaveFileName(self, "다른 이름으로 구성 저장", "", "JSON Files (*.json)")
        if path:
            try:
                config_data = self._gather_data_from_ui()
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, indent=4)
                self.current_config_path = path
                self.log_output.appendPlainText(f"'{os.path.basename(path)}' 파일으로 구성을 저장했습니다.")
            except Exception as e:
                QMessageBox.critical(self, "오류", f"구성을 저장하는 중 오류 발생:\n{e}")

    def _apply_data_to_ui(self, data):
        """불러온 데이터 사전을 UI의 각 위젯에 적용"""
        self._block_interface_signals(True)
        # Global
        g = data.get('global', {})
        self.le_hostname.setText(g.get('hostname', ''))
        # ... (다른 모든 Global 위젯 값 설정) ...

        # Interface
        self.interface_list.clear()
        for if_config in data.get('interfaces', []):
            item = QListWidgetItem(if_config['name'])
            item.setData(Qt.UserRole, if_config)
            self.interface_list.addItem(item)

        # VLAN
        self.vlan_table.setRowCount(0)
        vlans = data.get('vlans', {}).get('list', [])
        for vlan_data in vlans:
            row = self.vlan_table.rowCount()
            self.vlan_table.insertRow(row)
            self.vlan_table.setItem(row, 0, QTableWidgetItem(vlan_data.get('id')))
            self.vlan_table.setItem(row, 1, QTableWidgetItem(vlan_data.get('name')))
            self.vlan_table.setItem(row, 2, QTableWidgetItem(vlan_data.get('description')))
            self.vlan_table.item(row, 0).setData(Qt.UserRole, vlan_data.get('svi', {}))

        # ... (다른 모든 탭의 데이터 적용 로직 추가) ...


        self.config_area_widget.setVisible(False)
        self._block_interface_signals(False)
        # Routing 탭 복원
        r = settings.get('routing', {})
        self.static_route_table.setRowCount(0)
        for route in r.get('static_routes', []):
            row = self.static_route_table.rowCount();
            self.static_route_table.insertRow(row)
            self.static_route_table.setItem(row, 0, QTableWidgetItem(route.get('prefix')))
            self.static_route_table.setItem(row, 1, QTableWidgetItem(route.get('nexthop')))
            self.static_route_table.setItem(row, 2, QTableWidgetItem(route.get('metric')))
            self.static_route_table.setItem(row, 3, QTableWidgetItem(route.get('vrf')))

        ospf = r.get('ospf', {})
        self.cb_ospf_enabled.setChecked(ospf.get('enabled', False))
        self.le_ospf_process_id.setText(ospf.get('process_id', '1'))
        self.le_ospf_router_id.setText(ospf.get('router_id', ''))
        self.ospf_network_table.setRowCount(0)
        for net in ospf.get('networks', []):
            row = self.ospf_network_table.rowCount();
            self.ospf_network_table.insertRow(row)
            self.ospf_network_table.setItem(row, 0, QTableWidgetItem(net.get('prefix')))
            self.ospf_network_table.setItem(row, 1, QTableWidgetItem(net.get('wildcard')))
            self.ospf_network_table.setItem(row, 2, QTableWidgetItem(net.get('area')))

        # (EIGRP, BGP 복원 로직도 위와 유사한 패턴으로 추가)

        self._update_ui_for_os()

        # Switching 탭 복원
        s = settings.get('switching', {})
        self.combo_stp_mode.setCurrentText(s.get('stp_mode', 'rapid-pvst'))
        self.le_stp_priority.setText(s.get('stp_priority', ''))
        self.cb_stp_portfast_default.setChecked(s.get('stp_portfast_default', False))
        self.cb_stp_bpduguard_default.setChecked(s.get('stp_bpduguard_default', False))
        self.cb_stp_bpdufilter_default.setChecked(s.get('stp_bpdufilter_default', False))
        self.cb_stp_loopguard_default.setChecked(s.get('stp_loopguard_default', False))

        mst = s.get('mst', {})
        self.le_mst_name.setText(mst.get('name', ''))
        self.le_mst_revision.setText(mst.get('revision', '0'))
        self.mst_instance_table.setRowCount(0)
        for inst in mst.get('instances', []):
            row = self.mst_instance_table.rowCount();
            self.mst_instance_table.insertRow(row)
            self.mst_instance_table.setItem(row, 0, QTableWidgetItem(inst.get('id')))
            self.mst_instance_table.setItem(row, 1, QTableWidgetItem(inst.get('vlans')))

        vtp = s.get('vtp', {})
        self.cb_vtp_enabled.setChecked(vtp.get('enabled', False))
        self.combo_vtp_mode.setCurrentText(vtp.get('mode', 'transparent'))
        self.le_vtp_domain.setText(vtp.get('domain', ''))
        self.le_vtp_password.setText(vtp.get('password', ''))
        self.combo_vtp_version.setCurrentText(vtp.get('version', '2'))

        l2_sec = s.get('l2_security', {})
        self.cb_dhcp_snooping_enabled.setChecked(l2_sec.get('dhcp_snooping_enabled', False))
        self.le_dhcp_snooping_vlans.setText(l2_sec.get('dhcp_snooping_vlans', ''))
        self.le_dai_vlans.setText(l2_sec.get('dai_vlans', ''))

    def _setup_menu(self):
        """파일 메뉴 및 액션을 생성합니다."""
        self.menu_bar = QMenuBar(self)
        self.setMenuBar(self.menu_bar)

        file_menu = self.menu_bar.addMenu("파일(&F)")

        new_action = QAction("새 구성(&N)", self)
        new_action.triggered.connect(self._new_config_profile)
        file_menu.addAction(new_action)

        open_action = QAction("구성 열기(&O)...", self)
        open_action.triggered.connect(self._load_config_profile)
        file_menu.addAction(open_action)

        save_as_action = QAction("다른 이름으로 구성 저장(&A)...", self)
        save_as_action.triggered.connect(self._save_config_profile)
        file_menu.addAction(save_as_action)

    def _new_config_profile(self):
        """UI를 기본값으로 초기화합니다."""
        reply = QMessageBox.question(self, "새 구성", "현재 설정을 지우고 새로 시작하시겠습니까?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            # 모든 리스트와 테이블 초기화
            self.device_list.clear()
            self.interface_list.clear()
            self.vlan_table.setRowCount(0)
            # ... 다른 테이블들도 초기화 ...

            # 모든 입력 필드를 지우는 로직 (간단하게는 앱 재시작을 유도할 수도 있음)
            # 여기서는 빈 데이터를 UI에 적용하는 방식으로 초기화
            blank_data = {"devices": [], "settings": {}}
            self._apply_data_to_ui(blank_data)

            self.current_config_path = None
            self.log_output.appendPlainText("UI가 초기화되었습니다.")

    def _load_config_profile(self):
        """파일에서 구성 프로필을 불러와 UI에 적용합니다."""
        path, _ = QFileDialog.getOpenFileName(self, "구성 열기", "", "JSON Files (*.json)")
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                self._apply_data_to_ui(config_data)
                self.current_config_path = path
                self.log_output.appendPlainText(f"'{os.path.basename(path)}' 구성을 불러왔습니다.")
            except Exception as e:
                QMessageBox.critical(self, "오류", f"구성을 불러오는 중 오류 발생:\n{e}")

    def _save_config_profile(self):
        """현재 UI 상태를 구성 프로필 파일로 저장합니다."""
        path, _ = QFileDialog.getSaveFileName(self, "다른 이름으로 구성 저장", "", "JSON Files (*.json)")
        if path:
            try:
                config_data = self._gather_data_from_ui()
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, indent=4, ensure_ascii=False)
                self.current_config_path = path
                self.log_output.appendPlainText(f"'{os.path.basename(path)}' 파일으로 구성을 저장했습니다.")
            except Exception as e:
                QMessageBox.critical(self, "오류", f"구성을 저장하는 중 오류 발생:\n{e}")

    def _apply_data_to_ui(self, data):
        """불러온 데이터 딕셔너리를 UI의 각 위젯에 적용합니다."""
        # UI 업데이트 중 불필요한 신호 발생을 막기 위해 잠시 비활성화
        self._block_interface_signals(True)

        # 1. 장비 목록 복원
        self.device_list.clear()
        self.device_list.addItems(data.get('devices', []))

        settings = data.get('settings', {})

        # 2. Global 탭 복원
        g = settings.get('global', {})
        self.le_hostname.setText(g.get('hostname', ''))
        self.cb_service_timestamps.setChecked(g.get('service_timestamps', False))
        self.cb_service_password_encryption.setChecked(g.get('service_password_encryption', False))
        self.cb_service_call_home.setChecked(g.get('service_call_home', False))
        self.le_domain_name.setText(g.get('domain_name', ''))

        self.dns_table.setRowCount(0)
        for server in g.get('dns_servers', []):
            row = self.dns_table.rowCount();
            self.dns_table.insertRow(row)
            self.dns_table.setItem(row, 0, QTableWidgetItem(server.get('ip')))
            self.dns_table.setItem(row, 1, QTableWidgetItem(server.get('vrf')))

        self.combo_timezone.setCurrentText(g.get('timezone', 'KST 9'))
        self.le_custom_timezone.setText(g.get('timezone', '') if self.combo_timezone.currentText() == "Custom" else "")
        summer_time = g.get('summer_time', {})
        self.cb_summer_time.setChecked(summer_time.get('enabled', False))
        self.le_summer_time_zone.setText(summer_time.get('zone', ''))

        self.combo_logging_level.setCurrentText(g.get('logging_level', 'informational (6)'))
        self.cb_logging_console.setChecked(g.get('logging_console', True))
        self.cb_logging_buffered.setChecked(g.get('logging_buffered', True))
        self.le_logging_buffer_size.setText(g.get('logging_buffer_size', '32000'))

        self.logging_table.setRowCount(0)
        for host in g.get('logging_hosts', []):
            row = self.logging_table.rowCount();
            self.logging_table.insertRow(row)
            self.logging_table.setItem(row, 0, QTableWidgetItem(host.get('ip')))
            self.logging_table.setItem(row, 1, QTableWidgetItem(host.get('vrf')))

        self.cb_ntp_authenticate.setChecked(g.get('ntp_authenticate', False))
        self.le_ntp_master_stratum.setText(g.get('ntp_master_stratum', ''))

        self.ntp_table.setRowCount(0)
        for server in g.get('ntp_servers', []):
            row = self.ntp_table.rowCount();
            self.ntp_table.insertRow(row)
            self.ntp_table.setItem(row, 0, QTableWidgetItem(server.get('ip')))
            self.ntp_table.setItem(row, 1, QTableWidgetItem(str(server.get('prefer', False))))
            self.ntp_table.setItem(row, 2, QTableWidgetItem(server.get('key_id')))
            self.ntp_table.setItem(row, 3, QTableWidgetItem(server.get('vrf')))

        mgmt = g.get('management', {})
        self.combo_mgmt_interface.setCurrentText(mgmt.get('interface', 'None'))
        self.le_mgmt_ip.setText(mgmt.get('ip', ''))
        self.le_mgmt_subnet.setText(mgmt.get('subnet', ''))
        self.le_mgmt_gateway.setText(mgmt.get('gateway', ''))
        self.le_mgmt_vrf.setText(mgmt.get('vrf', ''))

        banner = g.get('banner', {})
        self.cb_enable_banner.setChecked(banner.get('enabled', False))
        self.te_banner_text.setPlainText(banner.get('text', ''))

        archive = g.get('archive', {})
        self.cb_archive_config.setChecked(archive.get('enabled', False))
        self.le_archive_path.setText(archive.get('path', ''))
        self.le_archive_max_files.setText(archive.get('max_files', ''))
        self.cb_archive_time_period.setChecked(archive.get('time_period_enabled', False))
        self.le_archive_time_period.setText(archive.get('time_period', ''))

        # 3. Interface 탭 복원
        self.interface_list.clear()
        for if_config in settings.get('interfaces', []):
            self._add_interface_item(if_config.get('name', 'Unknown Interface'))
            # 저장된 상세 설정 데이터로 덮어쓰기
            last_item_index = self.interface_list.count() - 1
            if last_item_index >= 0:
                self.interface_list.item(last_item_index).setData(Qt.UserRole, if_config)

        # 4. VLAN 탭 복원
        self.vlan_table.setRowCount(0)
        vlans_data = settings.get('vlans', {})
        self.cb_ip_routing.setChecked(vlans_data.get('enable_routing', False))
        for vlan_data in vlans_data.get('list', []):
            row = self.vlan_table.rowCount()
            self.vlan_table.insertRow(row)
            vlan_id_item = QTableWidgetItem(vlan_data.get('id'))
            vlan_id_item.setData(Qt.UserRole, vlan_data.get('svi', {}))  # SVI 데이터 저장
            self.vlan_table.setItem(row, 0, vlan_id_item)
            self.vlan_table.setItem(row, 1, QTableWidgetItem(vlan_data.get('name')))
            self.vlan_table.setItem(row, 2, QTableWidgetItem(vlan_data.get('description')))

        # 5. Switching 탭 복원
        s = settings.get('switching', {})
        self.combo_stp_mode.setCurrentText(s.get('stp_mode', 'rapid-pvst'))
        self.cb_stp_portfast_default.setChecked(s.get('stp_portfast_default', False))
        self.cb_stp_bpduguard_default.setChecked(s.get('stp_bpduguard_default', False))
        self.le_stp_priority.setText(s.get('stp_priority', ''))

        # 6. HA 탭 복원
        ha = settings.get('ha', {})
        svl = ha.get('svl', {})
        self.cb_svl_enabled.setChecked(svl.get('enabled', False))
        self.le_svl_domain.setText(svl.get('domain', ''))
        vpc = ha.get('vpc', {})
        self.cb_vpc_enabled.setChecked(vpc.get('enabled', False))
        self.le_vpc_domain.setText(vpc.get('domain', ''))
        self.le_vpc_peer_keepalive.setText(vpc.get('peer_keepalive', ''))

        # 7. Security 탭 복원
        sec = settings.get('security', {})
        self.cb_aaa_new_model.setChecked(sec.get('aaa_new_model', False))
        self.le_aaa_auth_login.setText(sec.get('aaa_auth_login', ''))
        self.le_aaa_auth_exec.setText(sec.get('aaa_auth_exec', ''))

        self.aaa_server_table.setRowCount(0)
        for group in sec.get('aaa_groups', []):
            row = self.aaa_server_table.rowCount();
            self.aaa_server_table.insertRow(row)
            self.aaa_server_table.setItem(row, 0, QTableWidgetItem(group.get('type')))
            self.aaa_server_table.setItem(row, 1, QTableWidgetItem(group.get('group_name')))
            self.aaa_server_table.setItem(row, 2, QTableWidgetItem(",".join(group.get('servers', []))))

        self.users_table.setRowCount(0)
        for user in sec.get('local_users', []):
            row = self.users_table.rowCount();
            self.users_table.insertRow(row)
            self.users_table.setItem(row, 0, QTableWidgetItem(user.get('username')))
            self.users_table.setItem(row, 1, QTableWidgetItem(user.get('privilege')))
            self.users_table.setItem(row, 2, QTableWidgetItem(user.get('password')))

        line = sec.get('line_config', {})
        self.le_con_exec_timeout.setText(line.get('con_timeout', '15 0'))
        self.cb_con_logging_sync.setChecked(line.get('con_logging_sync', True))
        self.cb_con_auth_aaa.setChecked(line.get('con_auth_aaa', False))
        self.le_con_auth_method.setText(line.get('con_auth_method', 'default'))
        self.le_vty_range.setText(line.get('vty_range', '0 4'))
        self.le_vty_exec_timeout.setText(line.get('vty_timeout', '15 0'))
        self.combo_vty_transport.setCurrentText(line.get('vty_transport', 'ssh'))

        snmp = sec.get('snmp', {})
        self.le_snmp_location.setText(snmp.get('location', ''))
        self.le_snmp_contact.setText(snmp.get('contact', ''))
        self.snmp_community_table.setRowCount(0)
        for comm in snmp.get('communities', []):
            row = self.snmp_community_table.rowCount();
            self.snmp_community_table.insertRow(row)
            self.snmp_community_table.setItem(row, 0, QTableWidgetItem(comm.get('community')))
            self.snmp_community_table.setItem(row, 1, QTableWidgetItem(comm.get('permission')))
            self.snmp_community_table.setItem(row, 2, QTableWidgetItem(comm.get('acl')))

        self.snmp_v3_user_table.setRowCount(0)
        for user in snmp.get('v3_users', []):
            row = self.snmp_v3_user_table.rowCount();
            self.snmp_v3_user_table.insertRow(row)
            self.snmp_v3_user_table.setItem(row, 0, QTableWidgetItem(user.get('username')))
            self.snmp_v3_user_table.setItem(row, 1, QTableWidgetItem(user.get('group')))
            self.snmp_v3_user_table.setItem(row, 2, QTableWidgetItem(user.get('auth_proto')))
            self.snmp_v3_user_table.setItem(row, 3, QTableWidgetItem(user.get('auth_pass')))
            self.snmp_v3_user_table.setItem(row, 4, QTableWidgetItem(user.get('priv_proto')))
            self.snmp_v3_user_table.setItem(row, 5, QTableWidgetItem(user.get('priv_pass')))

        hardening = sec.get('hardening', {})
        self.cb_no_ip_http.setChecked(hardening.get('no_ip_http', True))
        self.cb_no_cdp.setChecked(hardening.get('no_cdp', False))
        self.cb_lldp.setChecked(hardening.get('lldp', True))

        # 8. UI 상태 최종 업데이트
        self.config_area_widget.setVisible(False)
        self._block_interface_signals(False)
        self._update_ui_for_os()

    def _update_mst_ui_visibility(self, mode):
        """STP 모드가 'mst'일 때만 MST 설정 UI를 보여줍니다."""
        if hasattr(self, 'group_mst_config'):
            self.group_mst_config.setVisible(mode == "mst")
