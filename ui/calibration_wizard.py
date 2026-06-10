"""
校准向导对话框
提供完整的校准流程UI，包括实时数据可视化、进度显示、结果查看和代码导出
"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLabel, QPushButton, QProgressBar, QTextEdit,
                             QGroupBox, QSplitter, QWidget, QMessageBox,
                             QTabWidget, QTableWidget, QTableWidgetItem,
                             QHeaderView, QCheckBox, QSpinBox, QComboBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QColor

import pyqtgraph as pg
import numpy as np
import time
import json
import os
from typing import Optional

from core.data_collector import (
    DataCollector, CalibrationType, CalibrationStatus, 
    CalibrationResult, CalibrationDataPoint
)
from core.imu_calibrators import IMUAccelCalibrator, IMUGyroCalibrator
from core.other_calibrators import RCMidpointCalibrator, MagnetometerCalibrator


class RealtimePlotWidget(QWidget):
    """实时数据绑图控件"""
    
    def __init__(self, title: str, axes: list, colors: list = None, parent=None):
        super().__init__(parent)
        
        self.axes = axes  # ['x', 'y', 'z'] 等
        self.colors = colors or ['#ff0000', '#00ff00', '#0088ff', '#ff8800']
        self.max_points = 500
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # 标题
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color: white; font-weight: bold; font-size: 12px;")
        layout.addWidget(self.title_label)
        
        # 图表
        self.plot_widget = pg.PlotWidget(background='#1e1e1e')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('left', 'Value')
        self.plot_widget.setLabel('bottom', 'Samples')
        
        # 创建曲线
        self.curves = {}
        self.data_buffers = {axis: [] for axis in axes}
        
        for i, axis in enumerate(axes):
            color = self.colors[i % len(self.colors)]
            pen = pg.mkPen(color=color, width=2)
            curve = self.plot_widget.plot(pen=pen, name=axis)
            self.curves[axis] = curve
        
        layout.addWidget(self.plot_widget)
    
    def add_data_point(self, values_dict: dict):
        """添加一个数据点"""
        for axis in self.axes:
            if axis in values_dict:
                value = values_dict[axis]
                self.data_buffers[axis].append(value)
                
                # 保持缓冲区大小
                while len(self.data_buffers[axis]) > self.max_points:
                    self.data_buffers[axis].pop(0)
                
                # 更新曲线
                x = np.arange(len(self.data_buffers[axis]))
                y = np.array(self.data_buffers[axis])
                self.curves[axis].setData(x, y)
    
    def clear_data(self):
        """清除所有数据"""
        for axis in self.axes:
            self.data_buffers[axis].clear()
            self.curves[axis].setData([], [])


class CalibrationWizardDialog(QDialog):
    """
    校准向导对话框
    
    提供完整的校准流程：
    1. 选择校准类型和参数
    2. 显示操作指引
    3. 实时采集并显示数据
    4. 处理数据并显示结果
    5. 导出校准参数或C代码
    """
    
    # 信号（用于安全地从后台线程更新UI）
    calibration_completed = pyqtSignal(object)  # CalibrationResult
    sig_progress = pyqtSignal(int, int)         # current, total
    sig_status_changed = pyqtSignal(object)     # CalibrationStatus
    sig_data_received = pyqtSignal(object)      # CalibrationDataPoint
    sig_error = pyqtSignal(str)                 # error message
    
    def __init__(self, calibration_type: CalibrationType, parent=None):
        from utils.logger import logger
        logger.info(f"CalibrationWizardDialog.__init__() called for {calibration_type.value}")

        super().__init__(parent)

        self.calibration_type = calibration_type
        self.calibrator: DataCollector = None
        self.result: CalibrationResult = None

        # 定时器用于更新UI
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_display)

        logger.info("Setting up UI...")
        self._setup_ui()
        logger.info("Creating calibrator...")
        self._create_calibrator()
        logger.info("Connecting signals...")
        self._connect_signals()

        self.setWindowTitle(f"Calibration Wizard - {self._get_type_name()}")
        self.setMinimumSize(900, 700)
        logger.info("CalibrationWizardDialog initialization completed")
    
    def _get_type_name(self) -> str:
        """获取校准类型的英文名称"""
        names = {
            CalibrationType.IMU_ACCEL: "Accelerometer",
            CalibrationType.IMU_GYRO: "Gyroscope Bias",
            CalibrationType.RC_MIDPOINT: "RC Midpoint",
            CalibrationType.MAGNETOMETER: "Magnetometer",
            CalibrationType.ESC_CALIBRATION: "ESC Calibration"
        }
        return names.get(self.calibration_type.value, "Unknown")
    
    def _setup_ui(self):
        """设置UI布局"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        
        # ===== 顶部：标题和说明 =====
        header_group = QGroupBox("Instructions")
        header_group.setStyleSheet(self._get_group_style())
        header_layout = QVBoxLayout(header_group)
        
        self.instruction_label = QLabel(self._get_instructions())
        self.instruction_label.setWordWrap(True)
        self.instruction_label.setStyleSheet("font-size: 13px; color: #ccc; padding: 10px;")
        header_layout.addWidget(self.instruction_label)
        
        main_layout.addWidget(header_group)
        
        # ===== 中间主体区域（分割器）=====
        splitter = QSplitter(Qt.Horizontal)
        
        # 左侧：实时数据图表
        left_panel = self._create_plot_panel()
        splitter.addWidget(left_panel)
        
        # 右侧：控制和结果面板
        right_panel = self._create_control_panel()
        splitter.addWidget(right_panel)
        
        splitter.setSizes([550, 350])
        main_layout.addWidget(splitter)
        
        # ===== 底部：按钮栏 =====
        button_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("Start Collection")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 25px;
                border-radius: 5px;
            }
            QPushButton:hover { background-color: #218838; }
            QPushButton:disabled { background-color: #555; }
        """)
        self.start_btn.clicked.connect(self._start_calibration)
        button_layout.addWidget(self.start_btn)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 25px;
                border-radius: 5px;
            }
            QPushButton:hover { background-color: #c82333; }
            QPushButton:disabled { background-color: #555; }
        """)
        self.cancel_btn.clicked.connect(self._cancel_calibration)
        self.cancel_btn.setEnabled(False)
        button_layout.addWidget(self.cancel_btn)
        
        button_layout.addStretch()
        
        self.export_code_btn = QPushButton("Export C Code")
        self.export_code_btn.setStyleSheet("""
            QPushButton {
                background-color: #17a2b8;
                color: white;
                font-size: 12px;
                padding: 8px 15px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #138496; }
        """)
        self.export_code_btn.clicked.connect(self._export_c_code)
        self.export_code_btn.setEnabled(False)
        button_layout.addWidget(self.export_code_btn)
        
        self.save_result_btn = QPushButton("Save Result")
        self.save_result_btn.clicked.connect(self._save_result)
        self.save_result_btn.setEnabled(False)
        button_layout.addWidget(self.save_result_btn)
        
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.close_btn)
        
        main_layout.addLayout(button_layout)
    
    def _create_plot_panel(self) -> QWidget:
        """创建图表面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # 根据校准类型创建不同的图表
        if self.calibration_type == CalibrationType.IMU_ACCEL:
            self.plot_widget = RealtimePlotWidget(
                "Accelerometer Raw Data", 
                ['accel_x', 'accel_y', 'accel_z'],
                ['#ff6b6b', '#4ecdc4', '#45b7d1']
            )
        elif self.calibration_type == CalibrationType.IMU_GYRO:
            self.plot_widget = RealtimePlotWidget(
                "Gyroscope Raw Data (deg/s)",
                ['gyro_x', 'gyro_y', 'gyro_z'],
                ['#ff9f43', '#ee5a52', '#10ac84']
            )
        elif self.calibration_type == CalibrationType.RC_MIDPOINT:
            self.plot_widget = RealtimePlotWidget(
                "RC Channel Values (us)",
                ['rc_roll', 'rc_pitch', 'rc_yaw', 'rc_throttle'],
                ['#e17055', '#0984e3', '#00b894', '#fdcb6e']
            )
        elif self.calibration_type == CalibrationType.MAGNETOMETER:
            self.plot_widget = RealtimePlotWidget(
                "Magnetometer Raw Data",
                ['mag_x', 'mag_y', 'mag_z'],
                ['#6c5ce7', '#fd79a8', '#fdcb6e']
            )
        else:
            self.plot_widget = RealtimePlotWidget("Data Monitor", ['value'], ['#aaa'])
        
        layout.addWidget(self.plot_widget)
        
        return panel
    
    def _create_control_panel(self) -> QWidget:
        """创建控制面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # 参数设置组
        param_group = QGroupBox("Collection Parameters")
        param_group.setStyleSheet(self._get_group_style())
        param_layout = QGridLayout(param_group)
        
        param_layout.addWidget(QLabel("Sample Rate:"), 0, 0)
        self.sample_rate_spin = QSpinBox()
        self.sample_rate_spin.setRange(10, 500)
        self.sample_rate_spin.setValue(100)
        self.sample_rate_spin.setSuffix(" Hz")
        param_layout.addWidget(self.sample_rate_spin, 0, 1)
        
        param_layout.addWidget(QLabel("Samples:"), 1, 0)
        self.samples_spin = QSpinBox()
        self.samples_spin.setRange(100, 10000)
        self.samples_spin.setValue(1000)
        self.samples_spin.setSingleStep(100)
        param_layout.addWidget(self.samples_spin, 1, 1)
        
        layout.addWidget(param_group)
        
        # 状态和进度组
        status_group = QGroupBox("Status")
        status_group.setStyleSheet(self._get_group_style())
        status_layout = QVBoxLayout(status_group)
        
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #00bfff;")
        status_layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v%")
        status_layout.addWidget(self.progress_bar)
        
        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet("color: #aaa; font-size: 11px;")
        status_layout.addWidget(self.detail_label)
        
        layout.addWidget(status_group)
        
        # 结果显示组
        result_group = QGroupBox("Calibration Result")
        result_group.setStyleSheet(self._get_group_style())
        result_layout = QVBoxLayout(result_group)
        
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(3)
        self.result_table.setHorizontalHeaderLabels(["Parameter", "Value", "Unit"])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.result_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.result_table.setStyleSheet("""
            QTableWidget {
                background-color: #2d2d2d;
                gridline-color: #555;
                color: white;
            }
            QHeaderView::section {
                background-color: #3c3c3c;
                padding: 5px;
                font-weight: bold;
            }
        """)
        result_layout.addWidget(self.result_table)
        
        layout.addWidget(result_group)
        
        return panel
    
    def _get_instructions(self) -> str:
        """获取当前校准类型的操作说明 - 使用纯ASCII字符避免编码问题"""
        instructions = {
            CalibrationType.IMU_ACCEL: (
                "<h3>Accelerometer Calibration Steps:</h3>"
                "<ol>"
                "<li>Place FC on a <strong>completely level</strong> surface</li>"
                "<li>Ensure the aircraft is stationary</li>"
                "<li>Click 'Start Collection' button</li>"
                "<li>Wait for auto-completion (~10 seconds)</li>"
                "</ol>"
                "<p style='color: #ffc107;'>Note: Do not move the FC during calibration!</p>"
            ),
            CalibrationType.IMU_GYRO: (
                "<h3>Gyroscope Bias Calibration Steps:</h3>"
                "<ol>"
                "<li>Place FC on a <strong>stable</strong> surface</li>"
                "<li><strong>Absolutely do not move</strong> the FC</li>"
                "<li>Avoid vibration and temperature changes</li>"
                "<li>Click 'Start Collection', wait for completion (10-20s)</li>"
                "</ol>"
                "<p style='color: #ffc107;'>Important: Any tiny movement will affect accuracy!</p>"
            ),
            CalibrationType.RC_MIDPOINT: (
                "<h3>RC Midpoint Calibration Steps:</h3>"
                "<ol>"
                "<li>Turn on the transmitter</li>"
                "<li>Place all sticks at <strong>center position</strong></li>"
                "<li>Throttle usually at lowest position</li>"
                "<li>AUX switches at default position</li>"
                "<li>Click 'Start Collection'</li>"
                "</ol>"
                "<p style='color: #ffc107;'>Tip: Keep sticks stable, no shaking.</p>"
            ),
            CalibrationType.MAGNETOMETER: (
                "<h3>Magnetometer Calibration Steps:</h3>"
                "<ol>"
                "<li>Hold FC (or fix on non-magnetic turntable)</li>"
                "<li>Start doing <strong>continuous figure-8 rotation</strong></li>"
                "<li>Cover all directions as much as possible (360 deg)</li>"
                "<li>Continue rotating for 30-60 seconds until done</li>"
                "</ol>"
                "<p style='color: #ffc107;'>Movement should be slow and smooth, wider coverage is better.</p>"
                "<p style='color: #dc3545;'>Keep away from strong magnetic sources (motors, speakers, phones)!</p>"
            ),
            CalibrationType.ESC_CALIBRATION: (
                "<h3>ESC Calibration Steps (DANGER!):</h3>"
                "<ol>"
                "<li style='color: #dc3545;'><strong>MUST remove all propellers!</strong></li>"
                "<li>Disconnect battery, power via USB only</li>"
                "<li>Follow ESC manual instructions</li>"
                "<li>Usually: max throttle -> hear beep -> min throttle -> confirm</li>"
                "</ol>"
                "<p style='color: #dc3545; font-weight: bold;'>WARNING: Failure to remove props may cause serious injury!</p>"
            )
        }
        return instructions.get(self.calibration_type, "")
    
    def _create_calibrator(self):
        """根据类型创建校准采集器实例"""
        kwargs = {
            'sample_rate_hz': self.sample_rate_spin.value(),
            'required_samples': self.samples_spin.value()
        }
        
        if self.calibration_type == CalibrationType.IMU_ACCEL:
            self.calibrator = IMUAccelCalibrator(**kwargs)
        elif self.calibration_type == CalibrationType.IMU_GYRO:
            self.calibrator = IMUGyroCalibrator(**kwargs)
        elif self.calibration_type == CalibrationType.RC_MIDPOINT:
            self.calibrator = RCMidpointCalibrator(**kwargs)
        elif self.calibration_type == CalibrationType.MAGNETOMETER:
            self.calibrator = MagnetometerCalibrator(**kwargs)
        elif self.calibration_type == CalibrationType.ESC_CALIBRATION:
            from core.other_calibrators import ESCCalibrator
            self.calibrator = ESCCalibrator()
    
    def _connect_signals(self):
        """连接信号槽（通过pyqtSignal实现线程安全的UI更新）"""
        if self.calibrator:
            # 断开旧连接避免重复
            for sig in [self.sig_progress, self.sig_status_changed,
                        self.sig_data_received, self.sig_error]:
                try:
                    sig.disconnect()
                except TypeError:
                    pass

            # 连接pyqtSignal到UI更新方法（信号跨线程安全）
            self.sig_progress.connect(self._on_progress)
            self.sig_status_changed.connect(self._on_status_changed)
            self.sig_data_received.connect(self._on_data_received)
            self.sig_error.connect(self._on_error)
            self.calibration_completed.connect(self._on_completed)

            # 设置采集器回调→发射信号（后台线程安全）
            self.calibrator.on_progress = lambda c, t: self.sig_progress.emit(c, t)
            self.calibrator.on_status_changed = lambda s: self.sig_status_changed.emit(s)
            self.calibrator.on_data_received = lambda d: self.sig_data_received.emit(d)
            self.calibrator.on_completed = lambda r: self.calibration_completed.emit(r)
            self.calibrator.on_error = lambda e: self.sig_error.emit(e)
    
    def _start_calibration(self):
        """开始校准采集（支持重复校准）"""
        # ★ 如果上一次还在运行，先取消
        if self.calibrator and self.calibrator.is_running:
            self.calibrator.cancel_collection()
        
        if self.calibration_type == CalibrationType.ESC_CALIBRATION:
            reply = QMessageBox.warning(
                self, "Safety Warning",
                "Are you sure you have removed ALL propellers?\n\n"
                "ESC calibration will cause motors to run at full speed!\n"
                "Failure to remove props can cause serious injury!",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            
            from core.other_calibrators import ESCCalibrator
            self.calibrator.set_safety_confirmed(True)
        
        # 更新参数（创建全新的校准器实例）
        self._create_calibrator()
        self._connect_signals()
        
        # 清除旧数据
        self.plot_widget.clear_data()
        self.result_table.setRowCount(0)
        self.result = None
        self.detail_label.setText("")
        
        # 重置UI状态
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.export_code_btn.setEnabled(False)
        self.save_result_btn.setEnabled(False)
        self.status_label.setText("Preparing...")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #ffd93d;")
        self.progress_bar.setValue(0)
        
        # 启动定时器更新显示
        self.update_timer.start(50)  # 20Hz
        
        # 开始采集
        self.calibrator.start_collection()
    
    def _cancel_calibration(self):
        """取消校准"""
        if self.calibrator and self.calibrator.is_running:
            reply = QMessageBox.question(
                self, "Confirm Cancel",
                "Are you sure you want to cancel current calibration?",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.calibrator.cancel_collection()
    
    def _on_progress(self, current: int, total: int):
        """进度回调"""
        percentage = int(current / total * 100) if total > 0 else 0
        self.progress_bar.setValue(percentage)
        self.detail_label.setText(f"Collected: {current}/{total} samples")
    
    def _on_status_changed(self, status: CalibrationStatus):
        """状态改变回调"""
        status_text = {
            CalibrationStatus.IDLE: ("Ready", "#00bfff"),
            CalibrationStatus.PREPARING: ("Preparing...", "#ffd93d"),
            CalibrationStatus.COLLECTING: ("Collecting...", "#28a745"),
            CalibrationStatus.PROCESSING: ("Processing...", "#17a2b8"),
            CalibrationStatus.COMPLETED: ("Completed!", "#28a745"),
            CalibrationStatus.FAILED: ("Failed", "#dc3545"),
            CalibrationStatus.CANCELLED: ("Cancelled", "#6c757d")
        }
        
        text, color = status_text.get(status, ("Unknown", "#aaa"))
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {color};")
    
    def _on_data_received(self, data_point: CalibrationDataPoint):
        """收到新数据的回调 - 在主线程中通过定时器更新UI"""
        pass  # 实际更新在 _update_display 中进行
    
    def _on_completed(self, result: CalibrationResult):
        """校准完成的回调"""
        self.result = result
        self.update_timer.stop()
        
        # 恢复UI状态
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.export_code_btn.setEnabled(result.status == CalibrationStatus.COMPLETED)
        self.save_result_btn.setEnabled(True)
        
        # 显示结果
        if result.status == CalibrationStatus.COMPLETED:
            self._display_result(result)
        else:
            self.detail_label.setText(f"Error: {result.error_message}")
            QMessageBox.warning(self, "Calibration Failed", f"Calibration was not successful:\n{result.error_message}")
    
    def _on_error(self, error_msg: str):
        """错误回调"""
        self.detail_label.setText(f"Error: {error_msg}")
    
    def _update_display(self):
        """定时更新显示（由QTimer驱动）"""
        if not self.calibrator or not self.calibrator.is_running:
            return
        
        # 获取最新数据并更新图表
        raw_data = self.calibrator.get_raw_data()
        if raw_data:
            latest = raw_data[-1]
            self.plot_widget.add_data_point(latest.values)
    
    def _display_result(self, result: CalibrationResult):
        """显示校准结果到表格"""
        self.result_table.setRowCount(0)
        
        params = result.parameters
        stats = result.statistics
        
        row = 0
        
        # 显示主要参数
        if 'accel_bias' in params:
            bias = params['accel_bias']
            scale = params.get('accel_scale', {})
            for axis in ['x', 'y', 'z']:
                self._add_row(f"Bias ({axis.upper()})", f"{bias.get(axis, 0):+.4f}", "m/s^2")
                row += 1
            for axis in ['x', 'y', 'z']:
                self._add_row(f"Scale ({axis.upper()})", f"{scale.get(axis, 1.0):.4f}", "")
                row += 1
        
        if 'gyro_bias' in params:
            bias = params['gyro_bias']
            for axis in ['x', 'y', 'z']:
                self._add_row(f"Bias ({axis.upper()})", f"{bias.get(axis, 0):+.4f}", "deg/s")
                row += 1
            
            noise = stats.get('noise_std', {})
            for axis in ['x', 'y', 'z']:
                self._add_row(f"Noise ({axis.upper()})", f"{noise.get(axis, 0):.2f}", "deg/s")
                row += 1
        
        if 'rc_midpoints' in params:
            midpoints = params['rc_midpoints']
            for ch, val in midpoints.items():
                self._add_row(f"Channel {ch.upper()}", str(val), "us")
                row += 1
        
        if 'mag_offset' in params:
            offset = params['mag_offset']
            scale = params.get('mag_scale', {})
            for axis in ['x', 'y', 'z']:
                self._add_row(f"Hard Iron ({axis.upper()})", f"{offset.get(axis, 0):+.1f}", "")
                row += 1
            for axis in ['x', 'y', 'z']:
                self._add_row(f"Soft Iron ({axis.upper()})", f"{scale.get(axis, 1.0):.4f}", "")
                row += 1
            
            field = params.get('field_strength', 0)
            self._add_row("Field Strength", f"{field:.1f}", "uT")
            row += 1
        
        # 统计信息
        self._add_row("---", "---", "---")
        self._add_row("Samples", str(stats.get('sample_count', 0)), "")
        self._add_row("Quality", stats.get('quality', 'N/A'), "")
        
        self.detail_label.setText(f"Success! Collected {stats.get('sample_count', 0)} samples.")
    
    def _add_row(self, name: str, value: str, unit: str):
        """添加一行到结果表格"""
        row = self.result_table.rowCount()
        self.result_table.insertRow(row)
        self.result_table.setItem(row, 0, QTableWidgetItem(name))
        self.result_table.setItem(row, 1, QTableWidgetItem(value))
        self.result_table.setItem(row, 2, QTableWidgetItem(unit))
    
    def _export_c_code(self):
        """导出C语言格式的校准代码"""
        if not self.calibrator or not self.result:
            return
        
        try:
            code = self.calibrator.get_calibration_code()
        except AttributeError:
            QMessageBox.warning(self, "Info", "This calibration type does not support C code export yet")
            return
        
        # 显示对话框让用户复制
        dialog = QDialog(self)
        dialog.setWindowTitle("C Code Export")
        dialog.setMinimumSize(600, 400)
        
        layout = QVBoxLayout(dialog)
        
        text_edit = QTextEdit()
        text_edit.setPlainText(code)
        text_edit.setFont(QFont("Consolas", 11))
        text_edit.setReadOnly(True)
        layout.addWidget(text_edit)
        
        btn_layout = QHBoxLayout()
        
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(lambda: (
            text_edit.selectAll(),
            text_edit.copy(),
            QMessageBox.information(dialog, "Success", "Copied to clipboard!")
        ))
        btn_layout.addWidget(copy_btn)
        
        save_btn = QPushButton("Save to File")
        save_btn.clicked.connect(lambda: self._save_code_to_file(code))
        btn_layout.addWidget(save_btn)
        
        btn_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        dialog.exec_()
    
    def _save_code_to_file(self, code: str):
        """保存代码到文件"""
        from PyQt5.QtWidgets import QFileDialog
        
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Calibration Code",
            f"calibration_{self.calibration_type.value}_{time.strftime('%Y%m%d_%H%M%S')}.h",
            "C Header Files (*.h);;Text Files (*.txt)"
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(code)
                QMessageBox.information(self, "Success", f"File saved:\n{filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Save failed: {str(e)}")
    
    def _save_result(self):
        """保存校准结果为JSON"""
        if not self.result:
            return
        
        from PyQt5.QtWidgets import QFileDialog
        
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Result",
            f"calibration_{self.calibration_type.value}_{time.strftime('%Y%m%d_%H%M%S')}.json",
            "JSON Files (*.json)"
        )
        
        if filename:
            if self.result.save_to_file(filename):
                QMessageBox.information(self, "Success", f"Result saved:\n{filename}")
            else:
                QMessageBox.critical(self, "Error", "Save failed!")
    
    @staticmethod
    def _get_group_style() -> str:
        return """
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 2px solid #444;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
                color: white;
                background-color: #2d2d2d;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #00bfff;
            }
        """
    
    def closeEvent(self, event):
        """关闭事件"""
        if self.calibrator and self.calibrator.is_running:
            reply = QMessageBox.question(
                self, "Confirm Close",
                "Calibration is in progress. Are you sure you want to close?",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.calibrator.cancel_collection()
                self.update_timer.stop()
                event.accept()
            else:
                event.ignore()
        else:
            self.update_timer.stop()
            event.accept()


# Factory function: create wizard dialog
def show_calibration_wizard(calibration_type: CalibrationType, parent=None) -> Optional[CalibrationResult]:
    """
    Show calibration wizard dialog (blocking mode)

    Args:
        calibration_type: Type of calibration
        parent: Parent window

    Returns:
        CalibrationResult or None (if cancelled)
    """
    from utils.logger import logger

    try:
        logger.info(f"Opening calibration wizard for type: {calibration_type.value}")
        dialog = CalibrationWizardDialog(calibration_type, parent)
        logger.info(f"Calibration dialog created successfully, showing...")
        result = dialog.exec_()

        if result == QDialog.Accepted:
            logger.info("Calibration completed with Accepted status")
            return dialog.result
        else:
            logger.info("Calibration dialog cancelled or closed")
            return None

    except Exception as e:
        logger.exception(f"Failed to open calibration wizard: {e}")
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.critical(
            parent,
            "Calibration Error",
            f"Failed to open calibration wizard:\n\n{str(e)}\n\nPlease check logs for details."
        )
        return None