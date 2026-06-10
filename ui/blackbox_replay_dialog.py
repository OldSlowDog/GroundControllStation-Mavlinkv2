"""
黑匣子数据回放器UI界面
包含时间轴控制、播放按钮、多通道实时显示
"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLabel, QPushButton, QSlider, QGroupBox, QWidget,
                             QFrame, QSpinBox, QDoubleSpinBox, QCheckBox, QFileDialog,
                             QProgressBar, QSplitter, QTabWidget,
                             QMessageBox, QComboBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QIcon
import pyqtgraph as pg
import numpy as np
import time
import os
from datetime import datetime

from core.blackbox_player import BlackboxPlayer, BlackboxSession, PlaybackState, FlightDataPoint
from core.data_manager import data_manager
from ui.widgets.plot_widget import PlotWidget


class BlackboxReplayDialog(QDialog):
    """
    黑匣子数据回放器对话框
    
    功能：
    - 加载已记录的飞行数据文件
    - 时间轴拖动定位
    - 播放/暂停/停止控制
    - 变速播放 (0.25x - 4x)
    - 循环播放
    - 多通道同步显示（姿态、IMU、电机、RC）
    - 事件标记和跳转
    """
    
    # 信号
    file_loaded = pyqtSignal(object)  # BlackboxSession
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setWindowTitle("Blackbox Data Player")
        self.setMinimumSize(1100, 750)
        
        # 初始化回放器核心
        self.player = BlackboxPlayer()
        
        # 连接回调
        self._connect_signals()
        
        # 构建UI
        self._setup_ui()
    
    def _setup_ui(self):
        """构建用户界面"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)
        
        # ===== 顶部：文件加载和控制栏 =====
        control_bar = self._create_control_bar()
        main_layout.addWidget(control_bar)
        
        # ===== 中间：时间轴 + 数据显示 =====
        splitter = QSplitter(Qt.Vertical)
        
        # 上半部分：时间轴 + 状态信息
        timeline_panel = self._create_timeline_panel()
        splitter.addWidget(timeline_panel)
        
        # 下半部分：多通道数据显示
        display_panel = self._create_display_panel()
        splitter.addWidget(display_panel)
        
        splitter.setSizes([180, 550])
        main_layout.addWidget(splitter)
        
        # ===== 底部：状态栏 =====
        status_bar = self._create_status_bar()
        main_layout.addWidget(status_bar)
    
    def _create_control_bar(self) -> QFrame:
        """创建顶部控制栏"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #2d2d2d;
                border: 1px solid #444;
                border-radius: 5px;
                padding: 6px;
            }
            QLabel { color: white; font-size: 12px; }
            QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                padding: 6px 15px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 70px;
            }
            QPushButton:hover { background-color: #0098ff; }
            QPushButton:disabled { background-color: #555; }
            QPushButton:checked { background-color: #28a745; }
        """)
        
        layout = QHBoxLayout(frame)
        layout.setSpacing(10)
        
        # 文件加载
        load_btn = QPushButton("Load File")
        load_btn.clicked.connect(self._load_file)
        layout.addWidget(load_btn)
        
        self.filename_label = QLabel("No file loaded")
        self.filename_label.setStyleSheet("color: #aaa; min-width: 200px;")
        layout.addWidget(self.filename_label)
        
        layout.addSpacing(20)
        
        # 播放控制按钮
        self.play_btn = QPushButton("▶ Play")
        self.play_btn.clicked.connect(self._toggle_play_pause)
        layout.addWidget(self.play_btn)
        
        self.stop_btn = QPushButton="⏹ Stop"
        self.stop_btn.clicked.connect(self.player.stop)
        layout.addWidget(self.stop_btn)
        
        layout.addSpacing(10)
        
        # 速度控制
        layout.addWidget(QLabel("Speed:"))
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.25x", "0.5x", "1.0x", "2.0x", "4.0x"])
        self.speed_combo.setCurrentText("1.0x")
        self.speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        self.speed_combo.setMinimumWidth(70)
        layout.addWidget(self.speed_combo)
        
        layout.addSpacing(10)
        
        # 循环模式
        self.loop_checkbox = QCheckBox("Loop")
        self.loop_checkbox.toggled.connect(self.player.toggle_loop)
        layout.addWidget(self.loop_checkbox)
        
        layout.addStretch()
        
        return frame
    
    def _create_timeline_panel(self) -> QWidget:
        """创建时间轴面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(6)
        
        # 时间显示组
        time_group = QGroupBox("Timeline Control")
        time_group.setStyleSheet(self._get_group_style())
        time_layout = QGridLayout(time_group)
        
        # 当前时间
        time_layout.addWidget(QLabel("Current:"), 0, 0)
        self.current_time_label = QLabel("00:00.000")
        self.current_time_label.setStyleSheet(
            "color: #00bfff; font-size: 18px; font-weight: bold; font-family: Consolas; padding: 3px;"
        )
        time_layout.addWidget(self.current_time_label, 0, 1)
        
        # 总时长
        time_layout.addWidget(QLabel("Duration:"), 0, 2)
        self.duration_time_label = QLabel("00:00.000")
        self.duration_time_label.setStyleSheet(
            "color: #aaa; font-size: 14px; font-family: Consolas; padding: 3px;"
        )
        time_layout.addWidget(self.duration_time_label, 0, 3)
        
        # 进度百分比
        time_layout.addWidget(QLabel("Progress:"), 1, 0)
        self.progress_label = QLabel("0.0%")
        self.progress_label.setStyleSheet(
            "color: #ffc107; font-size: 14px; font-weight: bold; padding: 3px;"
        )
        time_layout.addWidget(self.progress_label, 1, 1)
        
        # 状态指示
        time_layout.addWidget(QLabel("State:"), 1, 2)
        self.state_label = QLabel("Stopped")
        self.state_label.setStyleSheet(
            "color: #dc3545; font-size: 13px; font-weight: bold; padding: 3px;"
        )
        time_layout.addWidget(self.state_label, 1, 3)
        
        layout.addWidget(time_group)
        
        # 时间轴滑块
        slider_group = QGroupBox("Position Slider")
        slider_group.setStyleSheet(self._get_group_style())
        slider_layout = QVBoxLayout(slider_group)
        
        self.time_slider = QSlider(Qt.Horizontal)
        self.time_slider.setMinimum(0)
        self.time_slider.setMaximum(10000)  # 0-100% * 100
        self.time_slider.setValue(0)
        self.time_slider.setTickPosition(QSlider.TicksBelow)
        self.time_slider.setTickInterval(500)  # 每5%一个刻度
        self.time_slider.sliderMoved.connect(self._on_slider_moved)
        self.time_slider.setMinimumHeight(35)
        slider_layout.addWidget(self.time_slider)
        
        # 时间标记标签（可选：显示关键事件）
        self.event_markers_layout = QHBoxLayout()
        self.event_markers_layout.setSpacing(5)
        slider_layout.addLayout(self.event_markers_layout)
        
        layout.addWidget(slider_group)
        
        return panel
    
    def _create_display_panel(self) -> QWidget:
        """创建数据显示面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(6)
        
        # 使用标签页分组显示不同类型的数据
        tab_widget = QTabWidget()
        tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #444;
                background-color: #252526;
            }
            QTabBar::tab {
                background-color: #3c3c3c;
                color: #ccc;
                padding: 6px 14px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-size: 11px;
            }
            QTabBar::tab:selected {
                background-color: #007acc;
                color: white;
                font-weight: bold;
            }
        """)
        
        # 标签1：姿态+RC
        attitude_tab = self._create_attitude_rc_tab()
        tab_widget.addTab(attitude_tab, "Attitude & RC")
        
        # 标签2：传感器
        sensors_tab = self._create_sensors_tab()
        tab_widget.addTab(sensors_tab, "Sensors (IMU)")
        
        # 标签3：电机输出
        motor_tab = self._create_motor_tab()
        tab_widget.addTab(motor_tab, "Motor Output")
        
        # 标签4：系统状态
        system_tab = self._create_system_tab()
        tab_widget.addTab(system_tab, "System Status")
        
        layout.addWidget(tab_widget)
        
        return panel
    
    def _create_attitude_rc_tab(self) -> QWidget:
        """创建姿态和RC显示标签页"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        
        # 左侧：姿态数值
        attitude_group = QGroupBox("Attitude")
        attitude_group.setStyleSheet(self._get_group_style())
        attitude_layout = QGridLayout(attitude_group)
        
        self.att_labels = {}
        att_items = [
            ("Roll:", "roll", "+0.0°"),
            ("Pitch:", "pitch", "+0.0°"),
            ("Yaw:", "yaw", "0.0°"),
            ("Alt:", "altitude", "0.0m")
        ]
        
        for i, (label_text, key, default_val) in enumerate(att_items):
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color: #ccc;")
            val_lbl = QLabel(default_val)
            val_lbl.setStyleSheet("color: #00bfff; font-family: Consolas; font-size: 13px; font-weight: bold;")
            self.att_labels[key] = val_lbl
            
            row = i // 2
            col = i % 2 * 2
            attitude_layout.addWidget(lbl, row, col)
            attitude_layout.addWidget(val_lbl, row, col+1)
        
        layout.addWidget(attitude_group)
        
        # 右侧：RC通道
        rc_group = QGroupBox("RC Channels")
        rc_group.setStyleSheet(self._get_group_style())
        rc_layout = QGridLayout(rc_group)
        
        self.rc_labels = {}
        channels = [
            ("ROLL", "rc_roll"), ("PITCH", "rc_pitch"),
            ("THROTTLE", "rc_throttle"), ("YAW", "rc_yaw"),
            ("AUX1", "rc_aux1"), ("AUX2", "rc_aux2"),
            ("AUX3", "rc_aux3"), ("AUX4", "rc_aux4")
        ]
        
        for i, (name, key) in enumerate(channels):
            label = QLabel(f"{name}: ----")
            label.setStyleSheet("font-family: Consolas; color: #ddd;")
            self.rc_labels[key] = label
            
            row = i // 4
            col = i % 4
            rc_layout.addWidget(label, row, col)
        
        layout.addWidget(rc_group)
        
        return widget
    
    def _create_sensors_tab(self) -> QWidget:
        """创建传感器(IMU)显示标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 陀螺仪图表
        gyro_group = QGroupBox("Gyroscope (deg/s)")
        gyro_group.setStyleSheet(self._get_group_style())
        gyro_layout = QVBoxLayout(gyro_group)
        
        self.replay_gyro_plot = PlotWidget("Gyroscope", num_lines=3,
                                           colors=['#ff6b6b', '#4ecdc4', '#45b7d1'],
                                           names=["Gyro X", "Gyro Y", "Gyro Z"])
        self.replay_gyro_plot.set_y_range(-1000, 1000)
        self.replay_gyro_plot.setMinimumHeight(120)
        gyro_layout.addWidget(self.replay_gyro_plot)
        
        layout.addWidget(gyro_group)
        
        # 加速度计图表
        accel_group = QGroupBox("Accelerometer (g)")
        accel_group.setStyleSheet(self._get_group_style())
        accel_layout = QVBoxLayout(accel_group)
        
        self.replay_accel_plot = PlotWidget("Accelerometer", num_lines=3,
                                             colors=['#e17055', '#0984e3', '#00b894'],
                                             names=["Accel X", "Accel Y", "Accel Z"])
        self.replay_accel_plot.set_y_range(-2, 2)
        self.replay_accel_plot.setMinimumHeight(120)
        accel_layout.addWidget(self.replay_accel_plot)
        
        layout.addWidget(accel_group)
        
        return widget
    
    def _create_motor_tab(self) -> QWidget:
        """创建电机输出显示标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        motor_group = QGroupBox("Motor PWM Output")
        motor_group.setStyleSheet(self._get_group_style())
        motor_layout = QVBoxLayout(motor_group)
        
        self.replay_motor_plot = PlotWidget("Motor PWM (us)", num_lines=4,
                                              colors=['#ff0000', '#00ff00', '#0088ff', '#ff8800'],
                                              names=["M1", "M2", "M3", "M4"])
        self.replay_motor_plot.set_y_range(1000, 2000)
        self.replay_motor_plot.setMinimumHeight(150)  # 稍大以完整显示范围
        motor_layout.addWidget(self.replay_motor_plot)
        
        layout.addWidget(motor_group)
        
        # 电机数值显示
        values_group = QGroupBox("Current Values")
        values_group.setStyleSheet(self._get_group_style())
        values_layout = QGridLayout(values_group)
        
        self.motor_value_labels = {}
        for i in range(1, 5):
            lbl = QLabel(f"M{i}: ---")
            lbl.setStyleSheet("color: #ffc107; font-family: Consolas; font-size: 14px;")
            self.motor_value_labels[f"motor_{i}"] = lbl
            values_layout.addWidget(lbl, (i-1)//2, (i-1)%2*2)
        
        layout.addWidget(values_group)
        
        return widget
    
    def _create_system_tab(self) -> QWidget:
        """创建系统状态显示标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        sys_group = QGroupBox("System Information")
        sys_group.setStyleSheet(self._get_groupstyle())
        sys_layout = QGridLayout(sys_group)
        
        sys_items = [
            ("Battery Voltage:", "vbat", "12.6 V"),
            ("Current:", "amperage", "0.0 A"),
            ("Altitude:", "altitude", "0.0 m"),
            ("GPS Speed:", "gps_speed", "0.0 m/s"),
            ("GPS Heading:", "gps_heading", "0°"),
            ("Armed:", "armed", "No"),
            ("Event:", "event", "-")
        ]
        
        self.sys_labels = {}
        for i, (label_text, key, default_val) in enumerate(sys_items):
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color: #ccc;")
            val_lbl = QLabel(default_val)
            if key == "armed":
                val_lbl.setStyleSheet("color: #dc3545; font-weight: bold;")
            else:
                val_lbl.setStyleSheet("color: #28a745; font-family: Consolas;")
            self.sys_labels[key] = val_lbl
            
            row = i // 2
            col = i % 2 * 2
            sys_layout.addWidget(lbl, row, col)
            sys_layout.addWidget(val_lbl, row, col+1)
        
        layout.addWidget(sys_group)
        
        # 统计摘要
        stats_group = QGroupBox("Session Statistics")
        stats_group.setStyleSheet(self._get_groupstyle())
        stats_layout = QGridLayout(stats_group)
        
        self.stats_labels = {}
        stat_items = [
            ("Duration:", "duration", "-- s"),
            ("Samples:", "samples", "--"),
            ("Sample Rate:", "rate", "-- Hz"),
            ("File Size:", "size", "-- KB")
        ]
        
        for i, (label_text, key, default_val) in enumerate(stat_items):
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color: #ccc;")
            val_lbl = QLabel(default_val)
            val_lbl.setStyleSheet("color: #aaa; font-family: Consolas;")
            self.stats_labels[key] = val_lbl
            
            row = i // 2
            col = i % 2 * 2
            stats_layout.addWidget(lbl, row, col)
            stats_layout.addWidget(val_lbl, row, col+1)
        
        layout.addWidget(stats_group)
        layout.addStretch()
        
        return widget
    
    def _create_status_bar(self) -> QFrame:
        """创建底部状态栏"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #1e272e;
                border-top: 1px solid #444;
                padding: 5px;
            }
            QLabel { color: #aaa; font-size: 11px; }
        """)
        
        layout = QHBoxLayout(frame)
        
        self.status_label = QLabel("Ready - Load a flight log to start playback")
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
        # 快捷键提示
        shortcut_label = QLabel("Shortcuts: [Space] Play/Pause | [←→] Seek | [+/-] Speed | [L] Loop")
        shortcut_label.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(shortcut_label)
        
        return frame
    
    def _connect_signals(self):
        """连接信号槽"""
        self.player.on_position_changed = self._on_position_update
        self.player.on_state_changed = self._on_state_update
        self.player.on_session_loaded = self._on_session_loaded
        
        # 键盘快捷键
        pass  # 在keyPressEvent中处理
    
    def _load_file(self):
        """加载黑匣子数据文件"""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Open Flight Log",
            "logs/",
            "Flight Log Files (*.json);;All Files (*)"
        )
        
        if not filepath:
            return
        
        # 尝试从DataManager的记录加载，或直接作为BlackboxSession加载
        success = False
        
        # 方法1：直接作为BlackboxSession文件
        session = BlackboxSession.load_from_file(filepath)
        if session and session.data_points:
            success = self.player.load_session(session)
            
        # 方法2：如果上面失败，尝试从CSV转换（简化版）
        if not success and filepath.endswith('.csv'):
            success = self._convert_csv_to_session(filepath)
        
        if success:
            self.filename_label.setText(os.path.basename(filepath))
            self.file_loaded.emit(session)
            self._update_ui_for_session()
            self.status_label.setText(f"Loaded: {len(session.data_points)} samples, {session.total_duration:.1f}s")
        else:
            QMessageBox.warning(self, "Load Failed", f"Could not load:\n{filepath}")
    
    def _convert_csv_to_session(self, csv_path: str) -> bool:
        """将CSV记录文件转换为BlackboxSession（简化版）"""
        try:
            import csv
            
            session = BlackboxSession()
            session.filename = os.path.basename(csv_path)
            session.start_time = datetime.now().isoformat()
            
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for i, row in enumerate(reader):
                    try:
                        dp = FlightDataPoint(
                            timestamp=i / 20.0,  # 假设20Hz采样率
                            
                            roll=float(row.get('roll', 0)),
                            pitch=float(row.get('pitch', 0)),
                            yaw=float(row.get('yaw', 0)) if 'yaw' in row else 0,
                            
                            accel_x=float(row.get('accel_x', 0)),
                            accel_y=float(row.get('accel_y', 0)),
                            accel_z=float(row.get('accel_z', 0)),
                            gyro_x=float(row.get('gyro_x', 0)),
                            gyro_y=float(row.get('gyro_y', 0)),
                            gyro_z=float(row.get('gyro_z', 0)),
                            
                            rc_roll=int(row.get('rc_roll', 1500)),
                            rc_pitch=int(row.get('rc_pitch', 1500)),
                            rc_yaw=int(row.get('rc_yaw', 1500)),
                            rc_throttle=int(row.get('rc_throttle', 1000)),
                            
                            motor_1=int(row.get('motor_1', 0)),
                            motor_2=int(row.get('motor_2', 0)),
                            motor_3=int(row.get('motor_3', 0)),
                            motor_4=int(row.get('motor_4', 0)),
                            
                            vbat=float(row.get('vbat', 12.6)),
                            altitude=float(row.get('altitude', 0)),
                            armed=row.get('armed', 'False').lower() == 'true'
                        )
                        
                        session.data_points.append(dp)
                    except Exception as e:
                        continue
            
            if session.data_points:
                session.total_samples = len(session.data_points)
                session.total_duration = session.total_samples / 20.0
                session.sample_rate_hz = 20
                session.end_time = datetime.now().isoformat()
                
                return self.player.load_session(session)
            
            return False
            
        except Exception as e:
            print(f"CSV转换失败: {e}")
            return False
    
    def _update_ui_for_session(self):
        """根据加载的会话更新UI"""
        if not self.player.session:
            return
        
        session = self.player.session
        
        # 更新时间显示
        self.duration_time_label.setText(self._format_time(session.total_duration))
        
        # 更新统计
        size_kb = os.path.getsize(session.filename) / 1024 if session.filename else 0
        self.stats_labels['duration'].setText(f"{session.total_duration:.1f}")
        self.stats_labels['samples'].setText(str(session.total_samples))
        self.stats_labels['rate'].setText(str(session.sample_rate_hz))
        self.stats_labels['size'].setText(f"{size_kb:.1f}")
        
        # 设置时间轴最大值
        self.time_slider.setMaximum(int(session.total_duration * 100))
        
        # 启用控件
        self.play_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.time_slider.setEnabled(True)
    
    def _toggle_play_pause(self):
        """切换播放/暂停"""
        if self.player.state == PlaybackState.PLAYING:
            self.player.pause()
            self.play_btn.setText("▶ Play")
        else:
            self.player.play()
            self.play_btn.setText("⏸ Pause")
    
    def _on_speed_changed(self, index):
        """速度改变回调"""
        speed_str = self.speed_combo.itemText(index)
        speed = float(speed_str.replace('x', ''))
        self.player.set_speed(speed)
    
    def _on_slider_moved(self, value):
        """时间轴滑块移动回调"""
        if not self.player.session:
            return
        
        target_time = value / 100.0  # 转换为秒
        was_playing = self.player.is_playing
        
        self.player.seek(target_time)
        
        # 如果正在播放，不自动恢复（用户手动调整时暂停）
    
    def _on_position_update(self, current_time: float, data: FlightDataPoint):
        """位置更新回调 - 同步更新所有显示"""
        # 更新时间标签
        self.current_time_label.setText(self._format_time(current_time))
        
        # 更新进度
        progress_pct = self.player.progress * 100
        self.progress_label.setText(f"{progress_pct:.1f}%")
        
        # 更新滑块（避免循环触发valueChanged信号）
        self.time_slider.blockSignals(True)
        self.time_slider.setValue(int(current_time * 100))
        self.time_slider.blockSignals(False)
        
        # 更新姿态显示
        for key in ['roll', 'pitch', 'yaw']:
            if key in self.att_labels:
                val = getattr(data, key, 0)
                unit = '°' if key != 'altitude' else 'm'
                self.att_labels[key].setText(f"{val:+.1f}{unit}")
        
        # 更新RC显示
        for key in self.rc_labels:
            val = getattr(data, f'rc_{key}', 0)
            name = key.upper()
            self.rc_labels[key].setText(f"{name}: {val:5d}")
        
        # 更新系统状态
        for key in ['vbat', 'amperage', 'altitude']:
            if key in self.sys_labels:
                val = getattr(data, key, 0)
                if key == 'vbat':
                    self.sys_labels[key].setText(f"{val:.2f} V")
                elif key == 'amperage':
                    self.sys_labels[key].setText(f"{val:.2f} A")
                elif key == 'altitude':
                    self.sys_labels[key].setText(f"{val:.1f} m")
        
        self.sys_labels['armed'].setText("Yes ✓" if data.armed else "No ✗")
        self.sys_labels['armed'].setStyleSheet(
            "color: #28a745; font-weight: bold;" if data.armed else "color: #dc3545; font-weight: bold;"
        )
        
        event_text = data.event or "-"
        self.sys_labels['event'].setText(event_text)
        
        # 更新图表（添加当前数据点）
        if hasattr(self, 'replay_gyro_plot'):
            self.replay_gyro_plot.update_all([data.gyro_x, data.gyro_y, data.gyro_z])
        
        if hasattr(self, 'replay_accel_plot'):
            self.replay_accel_plot.update_all([data.accel_x, data.accel_y, data.accel_z])
        
        if hasattr(self, 'replay_motor_plot'):
            self.replay_motor_plot.update_all([
                data.motor_1, data.motor_2, data.motor_3, data.motor_4
            ])
            
            # 更新电机数值
            for i in range(1, 5):
                val = getattr(data, f'motor_{i}', 0)
                if f'motor_{i}' in self.motor_value_labels:
                    self.motor_value_labels[f'motor_{i}'].setText(f"M{i}: {val:4d}")
    
    def _on_state_update(self, state: PlaybackState):
        """状态更新回调"""
        state_styles = {
            PlaybackState.STOPPED: ("#dc3545", "⏹ Stopped"),
            PlaybackState.PLAYING: ("#28a745", "▶ Playing"),
            PlaybackState.PAUSED: ("#ffc107", "⏸ Paused"),
            PlaybackState.LOADING: ("#17a2b8", "⏳ Loading...")
        }
        
        color, text = state_styles.get(state, ("#666", state.value))
        self.state_label.setText(text)
        self.state_label.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: bold;")
        
        # 更新按钮状态
        if state == PlaybackState.PLAYING:
            self.play_btn.setText("⏸ Pause")
        else:
            self.play_btn.setText("▶ Play")
        
        self.status_label.setText(f"State: {text}")
    
    def _on_session_loaded(self, session: BlackboxSession):
        """会话加载完成回调"""
        self.status_label.setText(f"Session loaded: {session.filename}")
    
    @staticmethod
    def _format_time(seconds: float) -> str:
        """格式化时间为 MM:ss.mmm"""
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes:02d}:{secs:06.3f}"
    
    def keyPressEvent(self, event):
        """键盘快捷键"""
        key = event.key()
        
        if key == Qt.Key_Space:  # 空格：播放/暂停
            self._toggle_play_pause()
        elif key == Qt.Key_Left:  # 左箭头：后退5秒
            self.player.seek(max(0, self.player.current_time - 5))
        elif key == Qt.Key_Right:  # 右箭头：前进5秒
            self.player.seek(min(self.player.duration, self.player.current_time + 5))
        elif key == Qt.Key_Up:  # 上箭头：加速
            current_speed = self.player.playback_speed
            speeds = [0.25, 0.5, 1.0, 2.0, 4.0]
            idx = speeds.index(current_speed) if current_speed in speeds else 2
            if idx < len(speeds) - 1:
                new_speed = speeds[idx + 1]
                idx = self.speed_combo.findText(f"{new_speed}x")
                self.speed_combo.setCurrentIndex(idx)
        elif key == Qt.Key_Down:  # 下箭头：减速
            current_speed = self.player.playback_speed
            speeds = [0.25, 0.5, 1.0, 2.0, 4.0]
            idx = speeds.index(current_speed) if current_speed in speeds else 2
            if idx > 0:
                new_speed = speeds[idx - 1]
                idx = self.speed_combo.findText(f"{new_speed}x")
                self.speed_combo.setCurrentIndex(idx)
        elif key == Qt.Key_L:  # L键：切换循环
            self.loop_checkbox.setChecked(not self.loop_checkbox.isChecked())
        elif key == Qt.Key_Escape:  # ESC：停止
            self.player.stop()
            self.play_btn.setText("▶ Play")
        
        super().keyPressEvent(event)
    
    @staticmethod
    def _get_group_style() -> str:
        return """
            QGroupBox {
                font-weight: bold;
                font-size: 11px;
                border: 1px solid #444;
                border-radius: 4px;
                margin-top: 6px;
                padding-top: 6px;
                color: white;
                background-color: #2d2d2d;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 6px;
                padding: 0 4px;
                color: #00bfff;
            }
        """