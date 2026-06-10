"""
主窗口界面 - 稳定版
确保所有信息完整显示，布局舒适不拥挤，绝不重叠
"""

import sys
import time  # ★ 新增: 时间相关功能
import json  # ★ 新增: JSON处理 (MQTT用)
from typing import Optional  # ★ 新增: 类型提示 (MQTT用)
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QTabWidget, QGroupBox, QLabel, QPushButton,
                             QComboBox, QSpinBox, QDoubleSpinBox, QSlider,
                             QTextEdit, QSplitter, QFrame, QGridLayout,
                             QStatusBar, QMenuBar, QAction, QMessageBox,
                             QProgressBar, QTableWidget, QTableWidgetItem,
                             QHeaderView, QCheckBox, QListWidget, QLineEdit)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QFont, QIcon, QColor

from core.communication import comm_serial, comm_tcp
from core.protocol_parser import MSPProtocolParser, FlightData
from core.data_manager import data_manager
from core.mqtt_manager import MQTTManager, MQTTPreset, MQTTConfig  # ★ 新增: MQTT支持
from ui.widgets.attitude_widget import AttitudeWidget
from ui.widgets.gauge_widget import GaugeWidget
from ui.widgets.plot_widget import PlotWidget
from ui.calibration_wizard import CalibrationWizardDialog, show_calibration_wizard, CalibrationType
from ui.blackbox_replay_dialog import BlackboxReplayDialog
from ui.rc_monitor_tab import RCMonitorTab
from ui.performance_monitor_tab import PerformanceMonitorTab
from ui.param_history_dialog import ParamHistoryDialog
from ui.complete_param_config import CompleteParamConfigTab
from ui.map_tab import MapTab
from core.param_history import get_param_history
from utils.logger import logger


class MainWindow(QMainWindow):
    # ★ 线程安全的Terminal日志信号
    _terminal_log = pyqtSignal(str)
    _connection_signal = pyqtSignal(bool)

    """主窗口类 - 稳定版"""

    def __init__(self):
        super().__init__()
        
        # ★ 稳定的窗口尺寸设置
        self.setWindowTitle("INAV Stellar GCS v1.0")
        self.setMinimumSize(1200, 750)
        self.resize(1400, 900)  # 适中的默认尺寸

        # 初始化核心组件
        self.parser = MSPProtocolParser()
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_data_cycle)

        # 数据请求定时器（50ms = 20Hz）
        self.request_timer = QTimer()
        self.request_timer.timeout.connect(self._request_flight_data)

        # ★ 自动重连定时器（2秒间隔）
        self._reconnect_timer = QTimer()
        self._reconnect_timer.timeout.connect(self._on_reconnect_tick)
        self._reconnect_attempts = 0
        self._reconnect_max_attempts = 10

        # ★ 诊断计数器
        self._rx_bytes_total = 0
        self._rx_packets_total = 0
        self._last_rx_time = 0
        self._terminal_max_lines = 500    # ★ Terminal最大行数
        self._last_rx_preview = ""       # ★ 上次RX预览（用于去重节流）

        # ★ MQTT客户端管理器 (新增!)
        self.mqtt_manager: Optional[MQTTManager] = None
        self.mqtt_enabled = False        # MQTT功能开关
        self.mqtt_publish_timer = QTimer()  # MQTT发布定时器
        self.mqtt_publish_timer.timeout.connect(self._mqtt_publish_cycle)
        self._mqtt_client_id = f"INAV_GCS_{int(time.time()) % 10000}"  # 随机ClientID

        # 构建UI
        self._setup_ui()
        self._setup_menu_bar()
        self._setup_status_bar()

        # ★ 初始化标签页状态（Map标签页默认全屏）
        if hasattr(self, 'tab_widget') and self.tab_widget:
            initial_index = self.tab_widget.currentIndex()
            self._on_tab_changed(initial_index)

        # 连接信号
        self._connect_signals()
        
        # ★ 连接线程安全的Terminal日志信号（确保UI操作在主线程）
        self._terminal_log.connect(self._do_log_terminal)

        logger.info("GCS initialized (Stable Layout)")

    def _setup_ui(self):
        """构建用户界面 - 舒适版"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        # ★ 舒适的边距：8px（不太紧也不太松）
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # 顶部：连接控制栏
        connection_bar = self._create_connection_bar()
        main_layout.addWidget(connection_bar)

        # 中间主体区域（使用分割器）
        self.splitter = QSplitter(Qt.Horizontal)

        # 左侧面板
        self.left_panel = self._create_left_panel()
        self.splitter.addWidget(self.left_panel)

        # 右侧面板
        right_panel = self._create_right_panel()
        self.splitter.addWidget(right_panel)

        # ★ 固定比例：左侧40%，右侧60%
        self.splitter.setSizes([520, 780])

        main_layout.addWidget(self.splitter)

    def _create_connection_bar(self) -> QFrame:
        """创建连接控制栏（支持串口/WiFi双模式）"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #2d2d2d;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 6px;
            }
            QLabel { color: white; font-size: 12px; }
            QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                padding: 6px 15px;
                border-radius: 3px;
                min-width: 80px;
            }
            QPushButton:hover { background-color: #0098ff; }
            QPushButton:disabled { background-color: #555; }
            QComboBox {
                background-color: #3c3c3c;
                color: white;
                border: 1px solid #555;
                padding: 5px;
                min-width: 150px;
            }
            QLineEdit {
                background-color: #3c3c3c;
                color: white;
                border: 1px solid #555;
                padding: 5px;
                min-width: 120px;
            }
        """)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        # ===== 连接模式选择 =====
        self.conn_mode_combo = QComboBox()
        self.conn_mode_combo.addItems(["📡 Serial (USB)", "📶 WiFi (TCP)", "📡 4G/MQTT (远程)"])  # ★ 新增: 4G选项
        self.conn_mode_combo.currentIndexChanged.connect(self._on_conn_mode_changed)
        layout.addWidget(self.conn_mode_combo)

        # ===== Serial 模式控件 =====
        self.serial_widget = QWidget()
        serial_layout = QHBoxLayout(self.serial_widget)
        serial_layout.setContentsMargins(0, 0, 0, 0)
        serial_layout.setSpacing(8)

        serial_layout.addWidget(QLabel("Port:"))
        self.port_combo = QComboBox()
        serial_layout.addWidget(self.port_combo)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_ports)
        serial_layout.addWidget(refresh_btn)

        serial_layout.addSpacing(10)
        serial_layout.addWidget(QLabel("Baud:"))
        self.baudrate_combo = QComboBox()
        self.baudrate_combo.addItems([
            "1500000", "1000000", "921600", "460800",
            "230400", "115200", "57600", "38400", "9600"
        ])
        self.baudrate_combo.setCurrentText("1500000")
        serial_layout.addWidget(self.baudrate_combo)
        layout.addWidget(self.serial_widget)

        # ===== WiFi 模式控件 =====
        self.wifi_widget = QWidget()
        wifi_layout = QHBoxLayout(self.wifi_widget)
        wifi_layout.setContentsMargins(0, 0, 0, 0)
        wifi_layout.setSpacing(8)

        wifi_layout.addWidget(QLabel("IP:"))
        self.ip_input = QLineEdit("192.168.4.1")
        wifi_layout.addWidget(self.ip_input)

        wifi_layout.addWidget(QLabel("Port:"))
        self.port_input = QLineEdit("8888")
        self.port_input.setMaximumWidth(80)
        wifi_layout.addWidget(self.port_input)

        scan_btn = QPushButton("Scan")
        scan_btn.clicked.connect(self._scan_wifi_networks)
        wifi_layout.addWidget(scan_btn)
        layout.addWidget(self.wifi_widget)

        # ===== 4G/MQTT 模式控件 (新增!) =====
        self.mqtt_widget = QWidget()
        mqtt_layout = QHBoxLayout(self.mqtt_widget)
        mqtt_layout.setContentsMargins(0, 0, 0, 0)
        mqtt_layout.setSpacing(8)

        # Broker选择
        mqtt_layout.addWidget(QLabel("Broker:"))
        self.mqtt_broker_combo = QComboBox()
        self.mqtt_broker_combo.addItems([
            "⭐ EMQX国内 (推荐)",
            "EMQX国际",
            "阿里云IoT",
            "华为云IoT",
            "自定义服务器"
        ])
        self.mqtt_broker_combo.setCurrentIndex(0)  # 默认EMQX国内节点
        self.mqtt_broker_combo.setToolTip(
            "推荐使用EMQX国内节点 (broker-cn.emqx.io)\n"
            "延迟<50ms，免费无需注册"
        )
        mqtt_layout.addWidget(self.mqtt_broker_combo)

        # ClientID输入
        mqtt_layout.addWidget(QLabel("ID:"))
        self.mqtt_clientid_input = QLineEdit("INAV_GCS_001")
        self.mqtt_clientid_input.setMaximumWidth(140)
        self.mqtt_clientid_input.setToolTip(
            "MQTT Client ID (must be unique!)\n"
            "Format: INAV_GCS_XXX or Drone_XXX"
        )
        mqtt_layout.addWidget(self.mqtt_clientid_input)

        # TLS加密开关
        self.mqtt_tls_check = QCheckBox("TLS")
        self.mqtt_tls_check.setToolTip(
            "Enable SSL/TLS encryption\n"
            "Port will auto-switch to 8883\n"
            "Required by some brokers (e.g. EMQX public)"
        )
        self.mqtt_tls_check.setStyleSheet("color: #ffc107; font-size: 11px;")
        mqtt_layout.addWidget(self.mqtt_tls_check)

        # MQTT状态标签
        self.mqtt_conn_status = QLabel("☁ Disconnected")
        self.mqtt_conn_status.setStyleSheet("color: #6c757d; font-size: 11px; padding: 2px 8px; border-radius: 3px;")
        mqtt_layout.addWidget(self.mqtt_conn_status)

        layout.addWidget(self.mqtt_widget)
        self.mqtt_widget.setVisible(False)  # 初始隐藏

        # 初始状态：显示Serial，隐藏WiFi和4G
        self.wifi_widget.setVisible(False)

        # ===== 公共按钮 =====
        layout.addSpacing(15)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._toggle_connection)
        layout.addWidget(self.connect_btn)

        layout.addSpacing(15)
        self.connection_status_label = QLabel("Not Connected")
        self.connection_status_label.setStyleSheet("color: #dc3545; font-size: 13px; font-weight: bold;")
        layout.addWidget(self.connection_status_label)

        # ===== 远程控制按钮 (MQTT模式下可用) =====
        self.remote_btn_frame = QFrame()
        remote_layout = QHBoxLayout(self.remote_btn_frame)
        remote_layout.setContentsMargins(0, 0, 0, 0)
        remote_layout.setSpacing(4)

        self.arm_btn = QPushButton("🔒 Arm")
        self.arm_btn.setStyleSheet("QPushButton{background:#28a745;color:white;padding:4px 12px;border-radius:3px;font-size:11px}"
                                   "QPushButton:hover{background:#34ce57}")
        self.arm_btn.clicked.connect(lambda: self._send_mqtt_command({"cmd": "arm"}))
        remote_layout.addWidget(self.arm_btn)

        self.disarm_btn = QPushButton("🔓 Disarm")
        self.disarm_btn.setStyleSheet("QPushButton{background:#dc3545;color:white;padding:4px 12px;border-radius:3px;font-size:11px}"
                                      "QPushButton:hover{background:#e35d6a}")
        self.disarm_btn.clicked.connect(lambda: self._send_mqtt_command({"cmd": "disarm"}))
        remote_layout.addWidget(self.disarm_btn)

        self.save_btn = QPushButton("💾 Save")
        self.save_btn.setStyleSheet("QPushButton{background:#ffc107;color:#333;padding:4px 12px;border-radius:3px;font-size:11px}"
                                    "QPushButton:hover{background:#ffd43b}")
        self.save_btn.clicked.connect(lambda: self._send_mqtt_command({"cmd": "save"}))
        remote_layout.addWidget(self.save_btn)

        self.reboot_btn = QPushButton("🔄 Reboot")
        self.reboot_btn.setStyleSheet("QPushButton{background:#17a2b8;color:white;padding:4px 12px;border-radius:3px;font-size:11px}"
                                      "QPushButton:hover{background:#20c997}")
        self.reboot_btn.clicked.connect(lambda: self._send_mqtt_command({"cmd": "reboot"}))
        remote_layout.addWidget(self.reboot_btn)

        self.remote_btn_frame.setVisible(False)  # 初始隐藏
        layout.addWidget(self.remote_btn_frame)

        layout.addStretch()

        self.data_rate_label = QLabel("-- Hz")
        self.data_rate_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(self.data_rate_label)

        return frame

    def _on_conn_mode_changed(self, index: int):
        """连接模式切换 (支持3种模式: Serial/WiFi/4G-MQTT)"""
        if index == 0:
            # Serial模式
            self.serial_widget.setVisible(True)
            self.wifi_widget.setVisible(False)
            self.mqtt_widget.setVisible(False)
            self.remote_btn_frame.setVisible(False)
        elif index == 1:
            # WiFi模式
            self.serial_widget.setVisible(False)
            self.wifi_widget.setVisible(True)
            self.mqtt_widget.setVisible(False)
            self.remote_btn_frame.setVisible(False)
        else:
            # 4G/MQTT模式 (新增!)
            self.serial_widget.setVisible(False)
            self.wifi_widget.setVisible(False)
            self.mqtt_widget.setVisible(True)

    def _scan_wifi_networks(self):
        """扫描WiFi网络（提示用户）"""
        QMessageBox.information(
            self,
            "WiFi 连接说明",
            "<b>请先手动连接 ESP32 热点：</b><br><br>"
            "• 热点名称：<b>ESP32-Car</b><br>"
            "• 密码：<b>12345678</b><br><br>"
            "连接后，IP 默认为 <b>192.168.4.1</b>，端口 <b>8888</b><br><br>"
            "<i>然后点击 Connect 按钮即可建立TCP连接</i>"
        )

    def _create_left_panel(self) -> QWidget:
        """创建左侧面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        # ===== 1. 姿态显示 =====
        attitude_group = QGroupBox("Attitude")
        attitude_group.setStyleSheet(self._get_groupbox_style())
        attitude_layout = QVBoxLayout(attitude_group)
        attitude_layout.setSpacing(5)

        self.attitude_widget = AttitudeWidget()
        self.attitude_widget.setMinimumSize(220, 200)
        attitude_layout.addWidget(self.attitude_widget)

        info_layout = QHBoxLayout()
        self.roll_label = QLabel("Roll: +0.0")
        self.pitch_label = QLabel("Pitch: +0.0")
        self.yaw_label = QLabel("Yaw: 0.0")
        for label in [self.roll_label, self.pitch_label, self.yaw_label]:
            label.setStyleSheet("color: #00bfff; font-size: 12px; font-weight: bold;")
            label.setMinimumWidth(75)
            info_layout.addWidget(label)
        attitude_layout.addLayout(info_layout)

        layout.addWidget(attitude_group)

        # ===== 2. 仪表盘 (2x2) =====
        gauge_group = QGroupBox("System Status")
        gauge_group.setStyleSheet(self._get_groupbox_style())
        gauge_layout = QGridLayout(gauge_group)
        gauge_layout.setSpacing(12)

        self.vbat_gauge = GaugeWidget("Voltage", 0, 25, "V")
        self.vbat_gauge.set_warning_threshold(14.8)
        self.vbat_gauge.set_critical_threshold(13.0)
        gauge_layout.addWidget(self.vbat_gauge, 0, 0)

        self.current_gauge = GaugeWidget("Current", 0, 50, "A")
        self.current_gauge.set_warning_threshold(30)
        gauge_layout.addWidget(self.current_gauge, 0, 1)

        self.battery_pct_label = QLabel("Battery: --%")
        self.battery_pct_label.setStyleSheet("color: #28a745; font-size: 10px; font-weight: bold;")
        gauge_layout.addWidget(self.battery_pct_label, 0, 2, Qt.AlignTop | Qt.AlignLeft)

        self.altitude_gauge = GaugeWidget("Altitude", -10, 100, "m")
        gauge_layout.addWidget(self.altitude_gauge, 1, 0)

        self.throttle_gauge = GaugeWidget("Throttle", 1000, 2000, "us")
        gauge_layout.addWidget(self.throttle_gauge, 1, 1)

        layout.addWidget(gauge_group)

        # ===== 3. RC通道 =====
        rc_group = QGroupBox("RC Input")
        rc_group.setStyleSheet(self._get_groupbox_style())
        rc_layout = QGridLayout(rc_group)
        rc_layout.setSpacing(8)

        self.rc_labels = {}
        channels = [
            ("ROLL", "rc_roll"), ("PITCH", "rc_pitch"),
            ("THROTTLE", "rc_throttle"), ("YAW", "rc_yaw"),
            ("AUX1", "rc_aux1"), ("AUX2", "rc_aux2"),
            ("AUX3", "rc_aux3"), ("AUX4", "rc_aux4")
        ]

        for i, (name, key) in enumerate(channels):
            label = QLabel(f"{name:8s}: ----")
            label.setStyleSheet("""
                color: #ddd;
                font-family: Consolas, monospace;
                font-size: 11px;
                padding: 2px;
            """)
            label.setMinimumWidth(90)
            self.rc_labels[key] = label
            
            row = i // 4
            col = i % 4
            rc_layout.addWidget(label, row, col)

        layout.addWidget(rc_group)

        return panel

    def _create_right_panel(self) -> QWidget:
        """创建右侧面板"""
        tab_widget = QTabWidget()
        tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #444;
                background-color: #252526;
            }
            QTabBar::tab {
                background-color: #3c3c3c;
                color: #ccc;
                padding: 8px 18px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background-color: #007acc;
                color: white;
                font-weight: bold;
            }
            QTabBar::tab:hover:!selected {
                background-color: #4a4a4a;
            }
        """)

        tab_widget.setMinimumSize(650, 550)

        # Map tab - First (full-screen map experience)
        map_tab = self._create_map_tab()
        tab_widget.addTab(map_tab, "🗺 Map")

        monitor_tab = self._create_monitor_tab()
        tab_widget.addTab(monitor_tab, "Monitor")

        rc_tab = self._create_rc_tab()
        tab_widget.addTab(rc_tab, "RC Channels")

        perf_tab = self._create_performance_tab()
        tab_widget.addTab(perf_tab, "Perf Monitor")

        pid_tab = self._create_pid_tab()
        tab_widget.addTab(pid_tab, "参数")

        calibration_tab = self._create_calibration_tab()
        tab_widget.addTab(calibration_tab, "Calibration")

        blackbox_tab = self._create_blackbox_tab()
        tab_widget.addTab(blackbox_tab, "Logger")

        terminal_tab = self._create_terminal_tab()
        tab_widget.addTab(terminal_tab, "Terminal")

        # ★ 监听标签页切换：Map标签页时隐藏左侧面板，实现全屏地图
        self.tab_widget = tab_widget
        tab_widget.currentChanged.connect(self._on_tab_changed)

        return tab_widget

    def _on_tab_changed(self, index: int):
        """
        标签页切换事件处理
        
        当切换到 Map 标签页（index=0）时：
        - 隐藏左侧面板，让地图全屏显示
        - 通知 MapTab 显示仪表盘浮动面板
        
        切换到其他标签页时：
        - 恢复左侧面板显示
        """
        if hasattr(self, 'tab_widget') and self.tab_widget:
            tab_text = self.tab_widget.tabText(index)

            # Map 标签页 → 全屏模式
            if "Map" in tab_text:
                self.left_panel.setVisible(False)
                # 通知 MapTab 进入全屏模式
                if hasattr(self, 'map_tab') and self.map_tab:
                    self.map_tab.enter_fullscreen_mode()
            else:
                # 其他标签页 → 正常模式
                self.left_panel.setVisible(True)
                if hasattr(self, 'map_tab') and self.map_tab:
                    self.map_tab.exit_fullscreen_mode()

    def _create_monitor_tab(self) -> QWidget:
        """创建实时监控标签页 - 紧凑版"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # IMU数据图表
        imu_group = QGroupBox("IMU Sensors")
        imu_group.setStyleSheet(self._get_groupbox_style())
        imu_layout = QVBoxLayout(imu_group)

        self.gyro_plot = PlotWidget("Gyroscope (deg/s)", num_lines=3,
                                     names=["Gyro X", "Gyro Y", "Gyro Z"])
        self.gyro_plot.set_y_range(-1000, 1000)
        self.gyro_plot.setMinimumHeight(110)  # ★ 适度缩小
        imu_layout.addWidget(self.gyro_plot)

        self.accel_plot = PlotWidget("Accelerometer (g)", num_lines=3,
                                     names=["Accel X", "Accel Y", "Accel Z"])
        self.accel_plot.set_y_range(-2, 2)
        self.accel_plot.setMinimumHeight(110)  # ★ 适度缩小
        imu_layout.addWidget(self.accel_plot)

        layout.addWidget(imu_group)

        # 电机输出图表
        motor_group = QGroupBox("Motor Output")
        motor_group.setStyleSheet(self._get_groupbox_style())
        motor_layout = QVBoxLayout(motor_group)

        self.motor_plot = PlotWidget("Motor PWM (us)", num_lines=4,
                                      colors=['#ff0000', '#00ff00', '#0088ff', '#ff8800'],
                                      names=["M1", "M2", "M3", "M4"])
        self.motor_plot.set_y_range(1000, 2000)
        self.motor_plot.setMinimumHeight(140)  # ★ 适度缩小但仍足够显示1000-2000
        motor_layout.addWidget(self.motor_plot)

        layout.addWidget(motor_group)

        return widget

    def _create_rc_tab(self) -> QWidget:
        """Create RC channel monitoring tab"""
        self.rc_monitor_tab = RCMonitorTab()
        return self.rc_monitor_tab

    def _create_performance_tab(self) -> QWidget:
        """Create performance monitoring tab"""
        self.performance_tab = PerformanceMonitorTab()
        return self.performance_tab

    def _create_pid_tab(self) -> QWidget:
        """创建完整参数配置标签页（包含所有35个参数）"""
        self.complete_param_config = CompleteParamConfigTab(self)
        
        # Connect signals
        try:
            self.complete_param_config.params_sent.connect(self._on_all_params_sent)
        except Exception:
            pass  # Signal may not be defined yet
        
        return self.complete_param_config

    def _create_calibration_tab(self) -> QWidget:
        """创建校准标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        calibrations = [
            ("Accelerometer Cal", "Place FC on a level surface, then click Start.",
             lambda: show_calibration_wizard(CalibrationType.IMU_ACCEL, self)),
            ("Gyroscope Bias Cal", "Keep FC completely still, then click Start.",
             lambda: show_calibration_wizard(CalibrationType.IMU_GYRO, self)),
            ("RC Midpoint Cal", "Place all sticks at center position.",
             lambda: show_calibration_wizard(CalibrationType.RC_MIDPOINT, self)),
            ("Magnetometer Cal", "Rotate in figure-8 pattern for 30-60s.",
             lambda: show_calibration_wizard(CalibrationType.MAGNETOMETER, self)),
            ("ESC Calibration", "Remove props first! Follow ESC manual.",
             lambda: show_calibration_wizard(CalibrationType.ESC_CALIBRATION, self)),
            ("⚡ Motor Test", "Remove ALL propellers! Direct motor PWM control.",
             self._open_motor_test),
        ]

        for title, description, callback in calibrations:
            group = QGroupBox(title)
            group.setStyleSheet(self._get_groupbox_style())
            group_layout = QVBoxLayout(group)

            desc_label = QLabel(description)
            desc_label.setStyleSheet("color: #aaa; font-size: 11px; padding: 5px;")
            desc_label.setWordWrap(True)
            group_layout.addWidget(desc_label)

            start_btn = QPushButton(f"Start {title}")
            start_btn.setStyleSheet("""
                QPushButton {
                    background-color: #fd7e14;
                    color: white;
                    padding: 8px;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #e8690f; }
            """)
            start_btn.clicked.connect(callback)
            group_layout.addWidget(start_btn)

            layout.addWidget(group)

        layout.addStretch()
        return widget

    def _create_map_tab(self) -> QWidget:
        """创建地图标签页"""
        self.map_tab = MapTab(self)
        return self.map_tab

    def _create_blackbox_tab(self) -> QWidget:
        """创建数据记录标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)

        control_group = QGroupBox("Recording Control")
        control_group.setStyleSheet(self._get_groupbox_style())
        control_layout = QHBoxLayout(control_group)

        self.record_btn = QPushButton("Start Recording")
        self.record_btn.setStyleSheet("background-color: #dc3545; padding: 8px;")
        self.record_btn.clicked.connect(self._toggle_recording)
        control_layout.addWidget(self.record_btn)

        self.record_status_label = "Status: Idle"
        self.record_status_label_obj = QLabel(self.record_status_label)
        self.record_status_label_obj.setStyleSheet("color: #aaa; font-size: 11px;")
        control_layout.addWidget(self.record_status_label_obj)

        control_layout.addStretch()

        export_btn = QPushButton("Export JSON")
        export_btn.clicked.connect(self._export_data)
        control_layout.addWidget(export_btn)

        clear_btn = QPushButton("Clear History")
        clear_btn.clicked.connect(data_manager.clear_history)
        control_layout.addWidget(clear_btn)

        control_layout.addSpacing(15)

        replay_btn = QPushButton("Blackbox Replay")
        replay_btn.setStyleSheet("""
            QPushButton {
                background-color: #6f42c1;
                color: white;
                padding: 8px 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #5a32a3; }
        """)
        replay_btn.clicked.connect(self._open_blackbox_replay)
        control_layout.addWidget(replay_btn)

        layout.addWidget(control_group)

        stats_group = QGroupBox("Flight Statistics")
        stats_group.setStyleSheet(self._get_groupbox_style())
        stats_layout = QGridLayout(stats_group)

        self.stats_display = {}
        stats_labels = [("Max Alt:", "max_alt"), ("Flight Time:", "flight_time"),
                       ("Packets:", "packets"), ("Rate:", "data_rate")]

        for i, (label_text, key) in enumerate(stats_labels):
            label = QLabel(label_text)
            label.setStyleSheet("color: #ccc;")
            value_label = QLabel("---")
            value_label.setStyleSheet("color: #fff; font-weight: bold;")
            self.stats_display[key] = value_label
            row = i // 2
            col = i % 2 * 2
            stats_layout.addWidget(label, row, col)
            stats_layout.addWidget(value_label, row, col+1)

        layout.addWidget(stats_group)

        log_group = QGroupBox("Recent Logs")
        log_group.setStyleSheet(self._get_groupbox_style())
        log_layout = QVBoxLayout(log_group)

        self.log_list = QTextEdit()
        self.log_list.setReadOnly(True)
        self.log_list.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #ccc;
                border: 1px solid #444;
                font-family: Consolas, monospace;
                font-size: 11px;
            }
        """)
        log_layout.addWidget(self.log_list)

        layout.addWidget(log_group)
        return widget

    def _create_terminal_tab(self) -> QWidget:
        """创建终端日志标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)

        self.terminal_output = QTextEdit()
        self.terminal_output.setReadOnly(True)
        self.terminal_output.setStyleSheet("""
            QTextEdit {
                background-color: #0c0c0c;
                color: #cccccc;
                font-family: Consolas, monospace;
                font-size: 12px;
                border: 1px solid #444;
                padding: 10px;
            }
        """)
        layout.addWidget(self.terminal_output)

        input_layout = QHBoxLayout()

        cmd_label = QLabel("Cmd:")
        cmd_label.setStyleSheet("color: #aaa;")
        input_layout.addWidget(cmd_label)

        self.command_input = QLineEdit()
        self.command_input.setStyleSheet("""
            QLineEdit {
                background-color: #2d2d2d;
                color: white;
                border: 1px solid #555;
                padding: 5px;
                font-family: Consolas, monospace;
            }
        """)
        self.command_input.returnPressed.connect(self._send_command)
        input_layout.addWidget(self.command_input)

        send_btn = QPushButton("Send")
        send_btn.clicked.connect(self._send_command)
        input_layout.addWidget(send_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.terminal_output.clear)
        input_layout.addWidget(clear_btn)

        layout.addLayout(input_layout)
        return widget

    def _setup_menu_bar(self):
        """设置菜单栏"""
        menubar = self.menuBar()
        menubar.setStyleSheet("""
            QMenuBar {
                background-color: #2d2d2d;
                color: white;
                padding: 2px;
            }
            QMenuBar::item:selected {
                background-color: #007acc;
            }
            QMenu {
                background-color: #2d2d2d;
                color: white;
                border: 1px solid #555;
            }
            QMenu::item:selected {
                background-color: #007acc;
            }
        """)

        file_menu = menubar.addMenu("&File")
        exit_action = QAction("E&xit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        view_menu = menubar.addMenu("&View")
        tools_menu = menubar.addMenu("&Tools")
        motor_test_action = QAction("⚡ Motor Test...", self)
        motor_test_action.triggered.connect(self._open_motor_test)
        tools_menu.addAction(motor_test_action)
        
        mag_cal_action = QAction("🧭 Trigger FC Mag Calibration", self)
        mag_cal_action.triggered.connect(self._trigger_fc_mag_calibration)
        tools_menu.addAction(mag_cal_action)
        help_menu = menubar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_status_bar(self):
        """设置状态栏"""
        statusbar = QStatusBar()
        statusbar.setStyleSheet("""
            QStatusBar {
                background-color: #007acc;
                color: white;
                font-size: 11px;
                padding: 3px 5px;
            }
        """)
        self.setStatusBar(statusbar)

        self.status_label = QLabel("Ready")
        statusbar.addWidget(self.status_label, 1)

        armed_indicator = QLabel("Locked")
        armed_indicator.setStyleSheet("padding: 2px 8px; background-color: #28a745; color: white; border-radius: 3px;")
        self.armed_indicator = armed_indicator
        statusbar.addPermanentWidget(armed_indicator)

        # ★ GPS定位状态标签 (新增!)
        gps_status = QLabel("🛰 GPS: No Fix")
        gps_status.setStyleSheet("color: #6c757d; font-size: 11px;")
        self.gps_status_label = gps_status
        statusbar.addPermanentWidget(gps_status)

        # ★ GPS坐标详情标签 (新增!)
        gps_coord = QLabel("📍 --")
        gps_coord.setStyleSheet("color: #adb5bd; font-size: 10px; margin-left: 10px;")
        self.gps_coord_label = gps_coord
        statusbar.addPermanentWidget(gps_coord)

        # ★ MQTT连接状态标签 (新增!)
        mqtt_status = QLabel("☁ MQTT: Disconnected")
        mqtt_status.setStyleSheet("color: #6c757d; font-size: 11px;")
        self.mqtt_status_label = mqtt_status
        statusbar.addPermanentWidget(mqtt_status)

    def _connect_signals(self):
        """连接信号槽"""
        comm_serial.on_data_received = self._on_data_received
        comm_serial.on_connection_changed = self._on_connection_changed
        comm_serial.on_error = self._on_error
        comm_tcp.on_data_received = self._on_data_received
        comm_tcp.on_connection_changed = self._on_connection_changed
        comm_tcp.on_error = self._on_error

        self._connection_signal.connect(self._handle_connection_changed)

        self.attitude_widget.attitude_changed.connect(
            lambda r, p: (
                self.roll_label.setText(f"Roll: {r:+.1f}"),
                self.pitch_label.setText(f"Pitch: {p:+.1f}")
            )
        )

    def _refresh_ports(self):
        """刷新可用串口列表"""
        ports = comm_serial.get_available_ports()
        self.port_combo.clear()

        if not ports:
            self.port_combo.addItem("No serial port found")
        else:
            for port in ports:
                display_name = f"{port['device']} - {port['description']}"
                self.port_combo.addItem(display_name, port['device'])

    def _get_active_comm(self):
        """获取当前激活的通信实例"""
        if self.conn_mode_combo.currentIndex() == 1:
            return comm_tcp
        return comm_serial

    def _toggle_connection(self):
        """切换连接状态（支持Serial/WiFi/4G-MQTT三种模式）"""
        mode_index = self.conn_mode_combo.currentIndex()

        # ★ 4G/MQTT模式的特殊处理 (新增!)
        if mode_index == 2:
            # 如果已连接MQTT，则断开
            if self.mqtt_enabled and self.mqtt_manager and self.mqtt_manager.is_connected:
                # ★ 异步断开连接 (避免UI卡死!)
                self.connect_btn.setText("Disconnecting...")
                self.connect_btn.setEnabled(False)
                self._log_terminal("[System] 正在断开MQTT...")

                # 使用QTimer延迟执行disconnect (让UI先刷新!)
                QTimer.singleShot(100, self._async_mqtt_disconnect)

            else:
                # 连接MQTT
                self._connect_mqtt_from_ui()

            return

        # Serial/WiFi 模式（原有逻辑）
        active = self._get_active_comm()

        if active.is_connected:
            self._reconnect_timer.stop()
            active.disconnect()
            self.connect_btn.setText("Connect")
            self.update_timer.stop()
            self.request_timer.stop()
        else:
            is_wifi = (self.conn_mode_combo.currentIndex() == 1)

            if is_wifi:
                host = self.ip_input.text().strip()
                port_str = self.port_input.text().strip()

                if not host:
                    QMessageBox.warning(self, "Error", "请输入飞控IP地址！")
                    return
                try:
                    port = int(port_str) if port_str else 8888
                except ValueError:
                    QMessageBox.warning(self, "Error", "端口号必须是数字！")
                    return

                self.connect_btn.setText("Connecting...")
                self.connect_btn.setEnabled(False)

                if comm_tcp.connect(host, port):
                    self.connect_btn.setText("Disconnect")
                    self.update_timer.start(50)
                    self.request_timer.start(50)
                    self._log_terminal(f"[System] WiFi connected to {host}:{port}")
                else:
                    self.connect_btn.setText("Connect")
                    QMessageBox.critical(self, "Error", f"TCP连接失败！\n\n请确认：\n1. 已连接 ESP32-Car 热点\n2. IP: {host}\n3. 端口: {port}")

                self.connect_btn.setEnabled(True)
            else:
                port_data = self.port_combo.currentData()
                if not port_data or str(port_data).startswith("No"):
                    QMessageBox.warning(self, "Error", "Please select a valid serial port!")
                    return

                baudrate = int(self.baudrate_combo.currentText())

                self.connect_btn.setText("Connecting...")
                self.connect_btn.setEnabled(False)

                if comm_serial.connect(port_data, baudrate):
                    self.connect_btn.setText("Disconnect")
                    self.update_timer.start(50)
                    self.request_timer.start(50)
                    self._log_terminal("[System] Connected to FC via Serial")
                else:
                    self.connect_btn.setText("Connect")
                    QMessageBox.critical(self, "Error", "Connection failed!")

                self.connect_btn.setEnabled(True)

    def _on_data_received(self, data: bytes):
        """处理接收到的原始数据（重复内容自动节流）"""
        self._rx_bytes_total += len(data)
        
        # ★ 构建预览文本
        ascii_preview = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[:40])
        rx_line = f"[RX] {len(data):4d}B | {ascii_preview}"
        
        # ★ 去重节流：只有和上次不同时才显示（飞控每2秒重复的调试日志会被合并）
        if rx_line != self._last_rx_preview:
            self._last_rx_preview = rx_line
            self._log_terminal(rx_line)
        
        # ★ 检查是否包含MSP响应头 ($M>) — 始终实时显示
        msp_idx = data.find(b'$M')
        if msp_idx >= 0:
            align = "对齐" if msp_idx == 0 else f"偏移{msp_idx}B"
            self._log_terminal(f"[MSP] 帧头{align}: {data[msp_idx:msp_idx+16].hex(' ')}")
        
        results = self.parser.parse_data(data)
        self._rx_packets_total += len(results)
        
        if results:
            cmd_names = [str(r[0].name) for r in results]
            self._log_terminal(f"[MSP] ✓ {', '.join(cmd_names)}")
        
        flight_data = self.parser.get_flight_data()

        if flight_data.timestamp > 0:
            data_manager.update_data(flight_data)

    def _on_connection_changed(self, connected: bool):
        """连接状态改变回调（可在任何线程调用，通过信号投递到主线程）"""
        self._connection_signal.emit(connected)

    def _handle_connection_changed(self, connected: bool):
        """实际处理连接状态变化（只在主线程执行）"""
        if connected:
            self._reconnect_timer.stop()
            self._reconnect_attempts = 0
            self.connection_status_label.setText("Connected")
            self.connection_status_label.setStyleSheet("color: #28a745; font-size: 13px; font-weight: bold;")
            active = self._get_active_comm()
            self.status_label.setText(f"Connected: {active.connection_info}")
            
            # ★ 重置诊断计数器
            self._rx_bytes_total = 0
            self._rx_packets_total = 0
            self._last_rx_time = 0
            
            # ★ 连接后立即发送 MSP_IDENT 请求，测试飞控是否响应
            ident_cmd = self.parser.request_ident()
            self._log_terminal(f"[TX] 发送 MSP_IDENT ({len(ident_cmd)}B): {ident_cmd.hex(' ')}")
            
            if active.send_data(ident_cmd):
                self._log_terminal("[TX] ✓ MSP_IDENT 发送成功")
            else:
                self._log_terminal("[TX] ✗ MSP_IDENT 发送失败! 检查串口权限/波特率")
        else:
            active = self._get_active_comm()
            unexpected = not active._user_disconnect
            
            self.connection_status_label.setText("Not Connected")
            self.connection_status_label.setStyleSheet("color: #dc3545; font-size: 13px; font-weight: bold;")
            self.status_label.setText("Disconnected")
            self.connect_btn.setText("Connect")
            self.connect_btn.setEnabled(True)
            self.update_timer.stop()
            self.request_timer.stop()
            self._log_terminal(f"[System] Session stats: {self._rx_bytes_total} bytes, {self._rx_packets_total} MSP packets")
            
            # ★ 非用户主动断开 → 自动重连
            if unexpected:
                self._start_reconnect()

    def _on_error(self, error_msg: str):
        """错误处理回调"""
        logger.error(error_msg)
        self._log_terminal(f"[Error] {error_msg}")

    def _update_data_cycle(self):
        """更新数据显示（定时调用）"""
        data = data_manager.get_current()

        if data.timestamp == 0:
            return

        # 更新姿态指示器
        self.attitude_widget.set_attitude(data.roll, data.pitch, data.heading)
        self.yaw_label.setText(f"Yaw: {data.heading:.0f}°")

        # 更新仪表盘
        self.vbat_gauge.set_value(data.vbat)
        self.current_gauge.set_value(data.amperage)
        self.altitude_gauge.set_value(data.altitude)
        self.throttle_gauge.set_value(data.rc_throttle)

        # 电池剩余百分比
        if data.battery_remaining >= 0:
            pct_color = "#28a745" if data.battery_remaining > 50 else "#ffc107" if data.battery_remaining > 20 else "#dc3545"
            self.battery_pct_label.setText(f"Battery: {data.battery_remaining:.0f}%")
            self.battery_pct_label.setStyleSheet(f"color: {pct_color}; font-size: 10px; font-weight: bold;")

        # 更新遥控器通道
        for key, label in self.rc_labels.items():
            value = getattr(data, key, 0)
            name = key.replace('rc_', '').upper()
            label.setText(f"{name:8s}: {value:5d}")

        # Update RC monitoring tab (if exists)
        if hasattr(self, 'rc_monitor_tab') and self.rc_monitor_tab:
            rc_data = {
                'rc_roll': getattr(data, 'rc_roll', 1500),
                'rc_pitch': getattr(data, 'rc_pitch', 1500),
                'rc_yaw': getattr(data, 'rc_yaw', 1500),
                'rc_throttle': getattr(data, 'rc_throttle', 1000),
                'rc_aux1': getattr(data, 'rc_aux1', 1500),
                'rc_aux2': getattr(data, 'rc_aux2', 1500),
                'rc_aux3': getattr(data, 'rc_aux3', 1500),
                'rc_aux4': getattr(data, 'rc_aux4', 1500)
            }
            self.rc_monitor_tab.update_rc_data(rc_data)

        # Update Performance Monitor tab (if exists)
        if hasattr(self, 'performance_tab') and self.performance_tab:
            self.performance_tab.update_performance_data(
                cpu_load=getattr(data, 'cpu_load', 0),
                cycle_time=getattr(data, 'cycle_time', 0),
                sensor_status=getattr(data, 'sensor_status', 0),
                i2c_errors=getattr(data, 'i2c_errors', 0),
                arming_flags=getattr(data, 'arming_flags', 0)
            )

        # 更新实时图表
        self.gyro_plot.update_all([data.gyro_x, data.gyro_y, data.gyro_z])
        self.accel_plot.update_all([data.accel_x, data.accel_y, data.accel_z])
        self.motor_plot.update_all([data.motor_1, data.motor_2, data.motor_3, data.motor_4])

        # 更新解锁状态
        if data.armed:
            self.armed_indicator.setText("Armed")
            self.armed_indicator.setStyleSheet("padding: 2px 8px; background-color: #dc3545; color: white; border-radius: 3px;")
        else:
            self.armed_indicator.setText("Locked")
            self.armed_indicator.setStyleSheet("padding: 2px 8px; background-color: #28a745; color: white; border-radius: 3px;")

        # ★ 更新GPS定位状态 (新增!)
        gps_fix = getattr(data, 'gps_fix', 0)
        gps_sats = getattr(data, 'gps_num_sat', 0)
        gps_lat = getattr(data, 'gps_lat', 0.0)
        gps_lon = getattr(data, 'gps_lon', 0.0)
        gps_alt = getattr(data, 'gps_alt', 0.0)
        gps_speed = getattr(data, 'gps_speed', 0.0)
        gps_heading = getattr(data, 'gps_heading', 0.0)
        gps_eph = getattr(data, 'gps_eph', 0.0)
        gps_epv = getattr(data, 'gps_epv', 0.0)

        if gps_fix > 0 and gps_sats >= 3:
            fix_text = {1: "2D Fix", 2: "3D Fix", 3: "DGPS"}.get(gps_fix, f"Fix{gps_fix}")
            acc_text = ""
            if gps_eph > 0:
                acc_text = f" | Eph:{gps_eph:.1f}m"
            if gps_epv > 0:
                acc_text += f"/{gps_epv:.1f}m"
            self.gps_status_label.setText(f"🛰 GPS: {fix_text} ({gps_sats} Sats){acc_text}")
            gps_color = "#28a745" if gps_eph < 5.0 else "#ffc107"
            self.gps_status_label.setStyleSheet(f"color: {gps_color}; font-size: 12px; font-weight: bold;")
        else:
            self.gps_status_label.setText("🛰 GPS: No Fix (0 Sats)")
            self.gps_status_label.setStyleSheet("color: #6c757d; font-size: 12px;")

        # GPS坐标显示（在状态栏或单独区域）
        if hasattr(self, 'gps_coord_label'):
            if gps_fix > 0:
                self.gps_coord_label.setText(
                    f"📍 {gps_lat:.6f}, {gps_lon:.6f} | "
                    f"Alt:{gps_alt:.1f}m | Spd:{gps_speed:.1f}m/s | Hdg:{gps_heading:.0f}°"
                )
            else:
                self.gps_coord_label.setText("📍 Waiting for GPS...")

        # 更新地图（GPS位置追踪）
        if hasattr(self, 'map_tab') and self.map_tab:
            self.map_tab.update_from_flight_data(data)

        # 更新统计信息
        stats = data_manager.get_statistics()
        self.stats_display["max_alt"].setText(f"{stats['max_altitude']:.2f} m")
        self.stats_display["flight_time"].setText(f"{stats['flight_time']:.1f} s")
        self.stats_display["packets"].setText(str(stats['packets_received']))

        rate = int(stats['packets_received'] / max(stats['flight_time'], 0.001))
        self.stats_display["data_rate"].setText(f"{rate} Hz")
        
        # ★ 显示接收诊断统计
        self.data_rate_label.setText(
            f"RX: {self._rx_bytes_total}B | {self._rx_packets_total} pkts"
        )

        # ★ MQTT数据发布 (如果已连接且启用) (新增!)
        if self.mqtt_enabled and self.mqtt_manager and self.mqtt_manager.is_connected:
            self._mqtt_publish_data(data)

    def _mqtt_publish_data(self, data):
        """
        将飞行数据通过MQTT发布到云端

        发布的主题:
          - inav/{client_id}/gps     GPS定位数据
          - inav/{client_id}/status  飞行状态
          - inav/{client_id}/imu     IMU传感器数据
          - inav/{client_id}/rc      遥控器通道

        Args:
            data: FlightData对象
        """
        try:
            # 发布GPS数据 (如果有有效定位)
            if getattr(data, 'gps_fix', 0) > 0:
                self.mqtt_manager.publish_gps(
                    latitude=getattr(data, 'gps_lat', 0.0),
                    longitude=getattr(data, 'gps_lon', 0.0),
                    altitude=getattr(data, 'gps_alt', 0.0),
                    num_satellites=getattr(data, 'gps_num_sat', 0),
                    fix_type=getattr(data, 'gps_fix', 0),
                    ground_speed=getattr(data, 'gps_speed', 0.0),
                    ground_course=getattr(data, 'gps_heading', 0.0)
                )

            # 发布状态数据 (至少vbat>0或armed才发)
            if data.vbat > 0.1 or data.armed:
                self.mqtt_manager.publish_status(
                    armed=data.armed,
                    vbat=data.vbat,
                    cpu_load=getattr(data, 'cpu_load', 0)
                )

            # 发布IMU数据 (accel非零才发)
            if abs(data.accel_x) > 0.001 or abs(data.accel_y) > 0.001 or abs(data.accel_z) > 0.001:
                if not hasattr(self, '_imu_counter'):
                    self._imu_counter = 0
                self._imu_counter += 1
                if self._imu_counter >= 5:
                    self._imu_counter = 0
                    self.mqtt_manager.publish_imu(
                        accel_x=data.accel_x, accel_y=data.accel_y, accel_z=data.accel_z,
                        gyro_x=data.gyro_x, gyro_y=data.gyro_y, gyro_z=data.gyro_z
                    )

            # 发布RC通道 (有实际遥控值才发, 默认值全是1500/1000时不发)
            rc_channels = [
                getattr(data, 'rc_roll', 1500),
                getattr(data, 'rc_pitch', 1500),
                getattr(data, 'rc_throttle', 1000),
                getattr(data, 'rc_yaw', 1500),
                getattr(data, 'rc_aux1', 1500),
                getattr(data, 'rc_aux2', 1500),
                getattr(data, 'rc_aux3', 1500),
                getattr(data, 'rc_aux4', 1500)
            ]
            defaults = [1500, 1500, 1000, 1500, 1500, 1500, 1500, 1500]
            if any(abs(rc_channels[i] - defaults[i]) > 10 for i in range(8)):
                self.mqtt_manager.publish_rc(rc_channels)

        except Exception as e:
            logger.error(f"[MQTT] 数据发布异常: {e}")

    def _request_flight_data(self):
        """请求飞行数据（轮询模式：按顺序循环发送所有MSP命令）"""
        active = self._get_active_comm()
        if not active.is_connected:
            return

        requests = [
            self.parser.request_attitude(),
            self.parser.request_imu(),
            self.parser.request_rc(),
            self.parser.request_motor(),
            self.parser.request_status_ex(),
            self.parser.request_inav_status(),
            self.parser.request_raw_gps()       # ★ GPS原始数据 (新增!)
        ]

        if not hasattr(self, '_msp_request_index'):
            self._msp_request_index = 0
        self._msp_request_index = (self._msp_request_index + 1) % len(requests)

        active.send_data(requests[self._msp_request_index])

    def _log_terminal(self, message: str):
        """线程安全的日志入口（可在任何线程调用，自动投递到主线程）"""
        self._terminal_log.emit(message)

    @pyqtSlot(str)
    def _do_log_terminal(self, message: str):
        """实际执行Terminal UI更新（只在主线程运行）"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        self.terminal_output.append(f"[{timestamp}] {message}")
        
        # ★ 自动清理：超过最大行数时从头部删除
        doc = self.terminal_output.document()
        if doc.blockCount() > self._terminal_max_lines:
            cursor = self.terminal_output.textCursor()
            cursor.movePosition(cursor.Start)
            cursor.movePosition(cursor.Down, cursor.KeepAnchor,
                                 doc.blockCount() - self._terminal_max_lines)
            cursor.removeSelectedText()

    def _send_mqtt_command(self, payload: dict):
        """通过MQTT发送命令到飞控 (arm/disarm/save/reboot/get_pid等)"""
        if not self.mqtt_manager or not self.mqtt_manager.is_connected:
            self._log_terminal("[MQTT] Not connected!")
            QMessageBox.warning(self, "MQTT未连接", "请先连接MQTT")
            return
        fc_id = "INAV_FC_STM32_001"
        ok = self.mqtt_manager.send_command_to_fc(fc_id, payload)
        cmd_name = payload.get("cmd", "unknown")
        if ok:
            self._log_terminal(f"[MQTT] → Sent cmd='{cmd_name}' to {fc_id}")
        else:
            self._log_terminal(f"[MQTT] ✗ Failed to send cmd='{cmd_name}'")

    def _send_command(self):
        """发送命令到飞控 (同时支持串口/4G-MQTT模式)"""
        command = self.command_input.text().strip()
        if not command:
            return

        # MQTT模式: 通过MQTT发送JSON命令
        if self.conn_mode_combo.currentIndex() == 2:
            # 如果输入是完整JSON, 直接原样发送
            if command.startswith('{') and command.endswith('}'):
                try:
                    payload = json.loads(command)
                    self._send_mqtt_command(payload)
                except json.JSONDecodeError:
                    self._log_terminal(f"[MQTT] Invalid JSON: {command}")
            else:
                # 简单命令名 → 包装为 {"cmd":"xxx"}
                self._send_mqtt_command({"cmd": command})
            self.command_input.clear()
            return

        # 串口/TCP模式: 通过串口发送原始数据
        active = self._get_active_comm()
        if active and active.is_connected:
            active.send_data(command.encode('utf-8'))
            self._log_terminal(f"[Send] {command}")
        else:
            self._log_terminal("[Warning] Not connected!")
        self.command_input.clear()

    def _open_param_history(self):
        """Open parameter history dialog"""
        dialog = ParamHistoryDialog(self)
        
        # Connect rollback signal
        dialog.rollback_requested.connect(self._on_rollback_from_history)
        
        result = dialog.exec_()
        
        if result == QDialog.Accepted:
            self._log_terminal("[History] Rollback applied - review and send to FC")

    def _on_rollback_from_history(self, rollback_data: dict):
        """Handle rollback request from history dialog"""
        params = rollback_data.get('params', {})
        version_id = rollback_data.get('version_id', 0)
        
        # Use new complete param config to set all parameters
        if hasattr(self, 'complete_param_config'):
            self.complete_param_config.set_all_params(params)
        
        self._log_terminal(f"[History] Rolled back to Version #{version_id}")

    def _on_all_params_sent(self, params: dict):
        """
        Handle signal when all parameters are sent to FC
        Auto-save to parameter history
        Now uses PX4-style parameter naming.
        """
        try:
            history_mgr = get_param_history()
            
            desc_parts = []
            
            # PX4-style key detection
            if 'MC_ROLLRATE_P' in params:
                desc_parts.append(
                    f"Rate: P{params['MC_ROLLRATE_P']} "
                    f"I{params.get('MC_ROLLRATE_I','?')} "
                    f"D{params.get('MC_ROLLRATE_D','?')}"
                )
            elif 'MC_ROLL_P' in params:
                desc_parts.append(
                    f"Angle: P{params['MC_ROLL_P']} "
                    f"I{params.get('MC_ROLL_I','?')} "
                    f"D{params.get('MC_ROLL_D','?')}"
                )
            if 'GYRO_LPF_HZ' in params:
                desc_parts.append(f"GyroLPF={params['GYRO_LPF_HZ']}Hz")
            
            # Also check legacy MSP keys for backward compatibility
            if 'rate_roll_kp' in params and not desc_parts:
                desc_parts.append(
                    f"Rate: R{params['rate_roll_kp']} "
                    f"P{params.get('rate_pitch_kp','?')} "
                    f"Y{params.get('rate_yaw_kp','?')}"
                )
            if 'gyro_lpf_hz' in params and not any('GyroLPF' in p for p in desc_parts):
                desc_parts.append(f"GyroLPF={params['gyro_lpf_hz']}Hz")
            
            description = " | ".join(desc_parts) if desc_parts else f"All {len(params)} params"
            
            version_id = history_mgr.save_version(
                params=params,
                description=description,
                metadata={
                    'total_params': len(params),
                    'source': 'CompleteParamConfig'
                }
            )
            
            self._log_terminal(f"[History] Saved as Version #{version_id} ({len(params)} params)")
            
        except Exception as hist_err:
            self._log_terminal(f"[History] Save failed: {hist_err}")

    def _toggle_recording(self):
        """切换数据记录状态"""
        if data_manager.is_recording:
            filename = data_manager.stop_recording()
            self.record_btn.setText("Start Recording")
            self.record_btn.setStyleSheet("background-color: #dc3545; padding: 8px;")
            self.record_status_label_obj.setText(f"Stopped (saved)")
            self._log_terminal(f"[Logger] Stopped: {filename}")
        else:
            if data_manager.start_recording():
                self.record_btn.setText("Stop Recording")
                self.record_btn.setStyleSheet("background-color: #28a745; padding: 8px;")
                self.record_status_label_obj.setText("Recording...")
                self._log_terminal("[Logger] Started recording...")

    def _export_data(self):
        """导出数据"""
        from datetime import datetime
        filename = f"logs/export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        if data_manager.export_to_json(filename):
            self._log_terminal(f"[Export] Saved: {filename}")
            QMessageBox.information(self, "Success", f"Exported:\n{filename}")
        else:
            QMessageBox.critical(self, "Error", "Export failed!")

    def _open_blackbox_replay(self):
        """打开黑匣子数据回放器"""
        dialog = BlackboxReplayDialog(self)
        dialog.exec_()

    def _open_motor_test(self):
        """打开电机测试对话框"""
        from ui.motor_test_dialog import MotorTestDialog
        dialog = MotorTestDialog(self)
        dialog.set_parser(self.parser)
        dialog.send_msp_data.connect(self._send_motor_command)
        dialog.show()
    
    def _send_motor_command(self, data: bytes):
        """发送电机控制命令到飞控"""
        active = self._get_active_comm()
        if active and active.is_connected:
            active.send_data(data)
            self._log_terminal(f"[MotorTest] Sent motor command: {len(data)}B")
        else:
            self._log_terminal("[MotorTest] Error: Not connected")

    # ========== 自动重连逻辑 ==========

    def _start_reconnect(self):
        """开始自动重连"""
        is_wifi = (self.conn_mode_combo.currentIndex() == 1)
        mode_name = "WiFi" if is_wifi else "Serial"
        
        self._reconnect_attempts = 0
        self.connection_status_label.setText(f"⚡ Reconnecting ({mode_name})...")
        self.connection_status_label.setStyleSheet("color: #ffc107; font-size: 13px; font-weight: bold;")
        self.status_label.setText("Reconnecting...")
        self._log_terminal(f"[System] Connection lost, starting auto-reconnect ({mode_name})")
        
        self._reconnect_timer.start(2000)  # 2秒间隔

    def _on_reconnect_tick(self):
        """重连定时器触发"""
        self._reconnect_attempts += 1
        
        if self._reconnect_attempts > self._reconnect_max_attempts:
            self._reconnect_timer.stop()
            self.connection_status_label.setText("Reconnect Failed")
            self.connection_status_label.setStyleSheet("color: #dc3545; font-size: 13px; font-weight: bold;")
            self.status_label.setText(f"Reconnect failed after {self._reconnect_max_attempts} attempts")
            self._log_terminal(f"[System] Auto-reconnect failed after {self._reconnect_max_attempts} attempts, giving up")
            return
        
        is_wifi = (self.conn_mode_combo.currentIndex() == 1)
        
        self.connection_status_label.setText(f"⚡ Reconnecting ({self._reconnect_attempts}/{self._reconnect_max_attempts})...")
        
        if is_wifi:
            host = self.ip_input.text().strip()
            port_str = self.port_input.text().strip()
            if not host:
                self._reconnect_timer.stop()
                return
            try:
                port = int(port_str) if port_str else 8888
            except ValueError:
                self._reconnect_timer.stop()
                return
            
            if comm_tcp.connect(host, port):
                self._reconnect_timer.stop()
                self._log_terminal(f"[System] WiFi reconnected ({host}:{port})")
        else:
            port = self.port_combo.currentData()
            if not port or str(port).startswith("No"):
                self._reconnect_timer.stop()
                return
            baudrate = int(self.baudrate_combo.currentText())
            
            if comm_serial.connect(port, baudrate):
                self._reconnect_timer.stop()
                self._log_terminal(f"[System] Serial reconnected ({port}@{baudrate})")
    
    def _trigger_fc_mag_calibration(self):
        """触发飞控端磁力计校准"""
        active = self._get_active_comm()
        if not active or not active.is_connected:
            QMessageBox.warning(self, "Not Connected", "Please connect to FC first.")
            return
        if self.parser.flight_data.armed:
            QMessageBox.warning(self, "Armed", "Disarm FC before calibration!")
            return
        
        reply = QMessageBox.question(
            self, "Magnetometer Calibration",
            "Trigger FC-side magnetometer calibration?\n\n"
            "The FC will enter calibration mode for ~30 seconds.\n"
            "Rotate the FC in all orientations during this time.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return
        
        cmd = self.parser.request_mag_calibration()
        if active.send_data(cmd):
            self._log_terminal("[MagCal] Triggered FC magnetometer calibration (MSP 206)")
            QMessageBox.information(
                self, "Calibration Started",
                "FC magnetometer calibration started!\n\n"
                "Rotate the FC in a figure-8 pattern for ~30 seconds.\n"
                "The FC will beep when complete."
            )
        else:
            QMessageBox.warning(self, "Error", "Failed to send calibration command")

    def _show_about(self):
        """显示关于对话框"""
        QMessageBox.about(
            self,
            "About INAV Stellar GCS",
            "<h2>INAV Stellar GCS</h2>"
            "<p>Version: 1.0.0</p>"
            "<p>Ground Control Station for INAV Stellar</p>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li>Real-time attitude display</li>"
            "<li>Sensor data visualization</li>"
            "<li>PID parameter tuning</li>"
            "<li>Calibration tools</li>"
            "<li>Data logging</li>"
            "</ul>"
            "<p>(c) 2026 INAV Team</p>"
        )

    # ========== MQTT功能 (新增!) ==========

    def _async_mqtt_disconnect(self):
        """
        异步执行MQTT断开连接 (避免UI卡死!)

        由QTimer.singleShot(100, self._async_mqtt_disconnect)调用
        在后台线程中安全断开MQTT连接
        """
        try:
            # 停止定时器
            self.update_timer.stop()
            self.request_timer.stop()

            # 执行断开
            self.mqtt_disconnect()

            # 恢复UI状态
            self.connect_btn.setText("Connect")
            self.connect_btn.setEnabled(True)
            self.remote_btn_frame.setVisible(False)  # 隐藏远程控制按钮

            self._log_terminal("[System] ✓ MQTT已断开连接")

        except Exception as e:
            logger.error(f"[MQTT] 异步断开异常: {e}")
            self.connect_btn.setText("Connect")
            self.connect_btn.setEnabled(True)
            QMessageBox.warning(self, "Warning", f"MQTT断开时出现异常:\n{str(e)}")

    def _connect_mqtt_from_ui(self):
        """
        从UI控件读取配置并连接MQTT (新增!)

        从以下UI控件获取参数:
          - mqtt_broker_combo: Broker选择下拉框
          - mqtt_clientid_input: ClientID输入框

        连接成功后:
          - 更新按钮文字为"Disconnect"
          - 启动数据更新定时器
          - 更新状态标签显示
        """
        # Read UI values
        broker_index = self.mqtt_broker_combo.currentIndex()
        client_id = self.mqtt_clientid_input.text().strip()
        use_tls = self.mqtt_tls_check.isChecked()

        if not client_id:
            QMessageBox.warning(self, "Error", "Please enter MQTT ClientID!")
            return

        # Map Broker selection to preset name
        broker_map = {
            0: "emqx_cn",
            1: "emqx_global",
            2: "aliyun_iot",
            3: "huawei_iot",
            4: "custom"
        }
        preset = broker_map.get(broker_index, "emqx_cn")

        broker_names = {
            "emqx_cn": "EMQX CN",
            "emqx_global": "EMQX Global",
            "aliyun_iot": "Aliyun IoT",
            "huawei_iot": "Huawei IoT",
            "custom": "Custom"
        }

        tls_str = "TLS" if use_tls else "plain"
        self.connect_btn.setText("Connecting...")
        self.connect_btn.setEnabled(False)
        self._log_terminal(f"[System] Connecting {broker_names.get(preset, preset)} ({tls_str}) ...")

        # Execute connection
        success = self.mqtt_connect(
            preset=preset,
            client_id=client_id,
            use_tls=use_tls
        )

        if success:
            self.connect_btn.setText("Disconnect")
            self.update_timer.start(50)
            self.request_timer.start(50)

            # 更新MQTT状态标签
            self.mqtt_conn_status.setText("☁ 已连接")
            self.mqtt_conn_status.setStyleSheet(
                "color: #28a745; font-size: 11px; padding: 2px 8px; "
                "border-radius: 3px; background-color: #d4edda;"
            )

            self._log_terminal(f"[System] ✓ MQTT连接成功! ClientID={client_id}")

            # 连接PID调参面板到MQTT (支持远程读写PID)
            if hasattr(self, 'complete_param_config'):
                self.complete_param_config.set_mqtt(self.mqtt_manager, "INAV_FC_STM32_001")

            # 启用远程控制按钮
            self.remote_btn_frame.setVisible(True)
        else:
            self.connect_btn.setText("Connect")
            self.mqtt_conn_status.setText("✗ 连接失败")
            self.mqtt_conn_status.setStyleSheet(
                "color: #dc3545; font-size: 11px; padding: 2px 8px; "
                "border-radius: 3px; background-color: #f8d7da;"
            )
            QMessageBox.critical(
                self,
                "MQTT连接失败",
                f"无法连接到 {broker_names.get(preset, preset)}!\n\n"
                "请检查：\n"
                "1. 网络是否正常（能否上网）\n"
                "2. Broker地址是否正确\n"
                "3. 是否被防火墙拦截\n\n"
                "提示：可以使用EMQX公共Broker进行测试（免费无需注册）"
            )

        self.connect_btn.setEnabled(True)

    def mqtt_connect(self, preset: str = "emqx_cn",
                     client_id: Optional[str] = None,
                     username: str = "", password: str = "",
                     use_tls: bool = False) -> bool:
        """
        Connect to MQTT Broker (convenience method)

        Args:
            preset: Preset broker ("emqx_cn" / "emqx_global" / "custom")
            client_id: Client ID (auto-generated if None)
            username: Username (optional)
            password: Password (optional)
            use_tls: Enable SSL/TLS encryption (default=False)

        Returns:
            True=connected/connecting, False=failed
        """
        if self.mqtt_manager is None:
            # 创建MQTT管理器实例
            config = MQTTConfig()
            if username:
                config.username = username
            if password:
                config.password = password
            self.mqtt_manager = MQTTManager(config)

        # 映射预设名称
        preset_map = {
            'emqx_cn': MQTTPreset.EMQX_CN,
            'emqx_global': MQTTPreset.EMQX_GLOBAL,
            'aliyun_iot': MQTTPreset.ALIYUN_IOT,
            'huawei_iot': MQTTPreset.HUAWEI_IOT,
            'custom': MQTTPreset.CUSTOM
        }
        mqtt_preset = preset_map.get(preset.lower(), MQTTPreset.EMQX_CN)

        # 设置ClientID
        cid = client_id or self._mqtt_client_id

        # 添加消息接收回调
        def on_mqtt_message(topic, payload):
            """收到MQTT消息时解析并更新显示到面板"""
            self._log_terminal(f"[MQTT] ← [{topic}] {json.dumps(payload, ensure_ascii=False)[:120]}")

            msg_type = payload.get('type', '')
            fd = self.parser.flight_data

            if msg_type == 'gps':
                fd.gps_lat = payload.get('latitude', 0.0)
                fd.gps_lon = payload.get('longitude', 0.0)
                fd.gps_alt = payload.get('altitude', 0.0)
                fd.gps_num_sat = payload.get('num_satellites', 0)
                fd.gps_fix = payload.get('fix_type', 0)
                fd.gps_speed = payload.get('ground_speed', 0.0)
                fd.gps_heading = payload.get('ground_course', 0.0)

            elif msg_type == 'status':
                fd.armed = payload.get('armed', False)
                vbat = payload.get('vbat', 0.0)
                fd.vbat = vbat
                fd.cpu_load = payload.get('cpu_load', 0)

            elif msg_type == 'attitude':
                fd.roll = payload.get('roll', 0.0)
                fd.pitch = -payload.get('pitch', 0.0)  # 俯仰取反: 飞控抬头(+), 地平仪天空上移
                heading = payload.get('heading', 0.0)
                fd.heading = heading + 360.0 if heading < 0 else heading

            elif msg_type == 'rc':
                channels = payload.get('channels', [])
                channel_map = ['rc_roll', 'rc_pitch', 'rc_throttle', 'rc_yaw',
                               'rc_aux1', 'rc_aux2', 'rc_aux3', 'rc_aux4']
                for i, ch in enumerate(channels[:8]):
                    if ch is not None:
                        setattr(fd, channel_map[i], ch)

            elif msg_type == 'imu':
                accel = payload.get('accel', {})
                gyro = payload.get('gyro', {})
                fd.accel_x = accel.get('x', 0.0)
                fd.accel_y = accel.get('y', 0.0)
                fd.accel_z = accel.get('z', 0.0)
                fd.gyro_x = gyro.get('x', 0.0)
                fd.gyro_y = gyro.get('y', 0.0)
                fd.gyro_z = gyro.get('z', 0.0)

            # 解析到数据后, 更新时间戳并推送到DataManager, 触发UI更新
            if msg_type in ('gps', 'status', 'rc', 'attitude'):
                fd.timestamp = time.time()
                try:
                    data_manager.update_data(self.parser.get_flight_data())
                except Exception as e:
                    logger.error(f"[MQTT] update_data error: {e}")

        # Execute connection
        success = self.mqtt_manager.connect(
            client_id=cid,
            preset=mqtt_preset,
            on_message=on_mqtt_message,
            use_tls=use_tls
        )

        if success:
            self.mqtt_enabled = True
            self._update_mqtt_status_ui()
            
            # Wire MQTT to param config for remote tuning
            if hasattr(self, 'complete_param_config'):
                self.complete_param_config.set_mqtt(
                    self.mqtt_manager,
                    fc_client_id="INAV_FC_STM32_001"
                )
            
            self._log_terminal(f"[MQTT] ✓ Connected to {self.mqtt_manager.config.broker_host} (ClientID={cid})")
            return True
        else:
            self._log_terminal("[MQTT] ✗ 连接失败!")
            return False

    def mqtt_disconnect(self):
        """断开MQTT连接"""
        if self.mqtt_manager:
            self.mqtt_manager.disconnect()
            self.mqtt_enabled = False
            self._update_mqtt_status_ui()

            # ★ 更新4G/MQTT模式下的UI状态 (新增!)
            if hasattr(self, 'mqtt_conn_status'):
                self.mqtt_conn_status.setText("☁ 未连接")
                self.mqtt_conn_status.setStyleSheet(
                    "color: #6c757d; font-size: 11px; padding: 2px 8px; border-radius: 3px;"
                )

            self._log_terminal("[MQTT] 已断开连接")

    def _update_mqtt_status_ui(self):
        """更新MQTT状态标签显示 (包括状态栏和4G模式面板)"""
        # 更新状态栏标签
        if hasattr(self, 'mqtt_status_label'):
            if self.mqtt_manager and self.mqtt_manager.is_connected:
                stats = self.mqtt_manager.get_stats()
                self.mqtt_status_label.setText(
                    f"☁ MQTT: Connected ({stats['messages_sent']}↑/{stats['messages_received']}↓)"
                )
                self.mqtt_status_label.setStyleSheet("color: #28a745; font-size: 11px; font-weight: bold;")
            else:
                self.mqtt_status_label.setText("☁ MQTT: Disconnected")
                self.mqtt_status_label.setStyleSheet("color: #6c757d; font-size: 11px;")

        # ★ 更新4G/MQTT模式面板的状态标签 (新增!)
        if hasattr(self, 'mqtt_conn_status'):
            if self.mqtt_manager and self.mqtt_manager.is_connected:
                stats = self.mqtt_manager.get_stats()
                self.mqtt_conn_status.setText(
                    f"☁ 已连接 ({stats['messages_sent']}↑/{stats['messages_received']}↓)"
                )
                self.mqtt_conn_status.setStyleSheet(
                    "color: #28a745; font-size: 11px; padding: 2px 8px; "
                    "border-radius: 3px; background-color: #d4edda;"
                )
            else:
                self.mqtt_conn_status.setText("☁ 未连接")
                self.mqtt_conn_status.setStyleSheet(
                    "color: #6c757d; font-size: 11px; padding: 2px 8px; border-radius: 3px;"
                )

    def _mqtt_publish_cycle(self):
        """MQTT发布定时器回调 (备用方法，通常在_update_data_cycle中直接发布)"""
        pass  # 当前实现已在_update_data_cycle中集成

    def get_mqtt_stats(self) -> Optional[dict]:
        """获取MQTT统计信息"""
        if self.mqtt_manager:
            return self.mqtt_manager.get_stats()
        return None

    def closeEvent(self, event):
        """关闭事件处理"""
        self._reconnect_timer.stop()

        # ★ 断开MQTT连接 (新增!)
        if self.mqtt_manager:
            self.mqtt_disconnect()

        if comm_serial.is_connected or comm_tcp.is_connected:
            reply = QMessageBox.question(
                self, 'Exit',
                'Still connected. Exit anyway?',
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                event.ignore()
                return
            comm_serial.disconnect()
            comm_tcp.disconnect()

        if data_manager.is_recording:
            data_manager.stop_recording()

        logger.info("Application closed")
        event.accept()

    @staticmethod
    def _get_groupbox_style() -> str:
        return """
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 2px solid #444;
                border-radius: 5px;
                margin-top: 8px;
                padding-top: 8px;
                color: white;
                background-color: #2d2d2d;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
                color: #00bfff;
            }
        """