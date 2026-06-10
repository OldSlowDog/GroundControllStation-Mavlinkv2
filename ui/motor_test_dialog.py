"""
电机测试对话框

功能:
- 通过MSP_SET_MOTOR(214)命令控制各电机PWM输出
- 安全确认机制: 必须确认安全警告才能启用电机控制
- 实时滑块调节, 即时发送到飞控
- 一键停止所有电机
- X型飞机示意图, 标注电机位置和机头朝向
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QSlider, QGroupBox, QSpinBox,
    QMessageBox, QWidget, QFrame, QProgressBar
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QRectF, QPointF
from PyQt5.QtGui import (QFont, QColor, QPainter, QPen, QBrush,
                         QPainterPath, QLinearGradient)


class QuadcopterDiagram(QWidget):
    """X型四轴飞行器示意图 - 显示电机位置和机头朝向"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 260)
        self.motor_values = [1000, 1000, 1000, 1000]
        self.motors_enabled = False

    def set_motor_value(self, index, value):
        if 0 <= index < 4:
            self.motor_values[index] = value
            self.update()

    def set_motors_enabled(self, enabled):
        self.motors_enabled = enabled
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        cx, cy = w / 2, h / 2 + 10
        arm_len = min(w, h) * 0.36

        bg_color = QColor(30, 32, 40)
        painter.fillRect(0, 0, w, h, bg_color)

        pen_frame = QPen(QColor(70, 75, 85), 2)
        painter.setPen(pen_frame)
        painter.setBrush(QColor(25, 28, 35))
        painter.drawRoundedRect(2, 2, w - 4, h - 4, 8, 8)

        arrow_y = cy - arm_len - 22
        painter.setPen(QPen(QColor(255, 193, 7), 2))
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.drawText(int(cx) - 20, int(arrow_y) - 12, "▲ FRONT")

        body_pen = QPen(QColor(90, 95, 105), 3)
        body_brush = QBrush(QColor(50, 55, 65))
        painter.setPen(body_pen)
        painter.setBrush(body_brush)
        body = QRectF(cx - 18, cy - 14, 36, 28)
        painter.drawRoundedRect(body, 6, 6)

        arm_pen = QPen(QColor(80, 85, 95), 4, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(arm_pen)

        # ★ 物理标签映射: FR位置实际是M4, RR位置实际是M1
        positions = [
            (cx + arm_len * 0.7, cy - arm_len * 0.7),   # FR → M4
            (cx - arm_len * 0.7, cy + arm_len * 0.7),   # RL → M2
            (cx - arm_len * 0.7, cy - arm_len * 0.7),   # FL → M3
            (cx + arm_len * 0.7, cy + arm_len * 0.7),   # RR → M1
        ]

        for i in range(4):
            px, py = positions[i]
            painter.drawLine(int(cx), int(cy), int(px), int(py))

        colors = [
            QColor(255, 170, 0),    # M4(FR): 橙
            QColor(68, 255, 68),    # M2(RL): 绿
            QColor(68, 136, 255),   # M3(FL): 蓝
            QColor(255, 68, 68),    # M1(RR): 红
        ]
        labels = ['M4', 'M2', 'M3', 'M1']

        for i in range(4):
            px, py = positions[i]
            val = self.motor_values[i]
            intensity = max(0.15, min(1.0, (val - 1000) / 1000.0))

            r = 22
            grad = QLinearGradient(px - r, py - r, px + r, py + r)
            base = colors[i]
            dark = base.darker(250)
            bright = base.lighter(130) if self.motors_enabled else base.darker(180)
            grad.setColorAt(0, bright)
            grad.setColorAt(0.5, QColor(
                int(base.red() * intensity),
                int(base.green() * intensity),
                int(base.blue() * intensity)))
            grad.setColorAt(1, dark)

            painter.setPen(QPen(dark, 2))
            painter.setBrush(QBrush(grad))
            painter.drawEllipse(QPointF(px, py), r, r)

            painter.setPen(Qt.white)
            painter.setFont(QFont("Consolas", 11, QFont.Bold))
            text_rect = QRectF(px - 20, py - 8, 40, 16)
            painter.drawText(text_rect, Qt.AlignCenter, labels[i])

            painter.setFont(QFont("Consolas", 7))
            text_rect2 = QRectF(px - 12, py + 8, 24, 12)
            painter.drawText(text_rect2, Qt.AlignCenter, str(val))


class MotorTestDialog(QDialog):
    """电机测试对话框"""

    send_msp_data = pyqtSignal(bytes)

    PWM_MIN = 1000
    PWM_MAX = 2000
    PWM_CENTER = 1500
    MOTOR_COUNT = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Motor Test - Safety Mode")
        self.setMinimumSize(800, 520)

        self.motors_enabled = False
        self.safety_confirmed = False
        self._update_timer = None

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ===== 安全警告区域 =====
        safety_group = QGroupBox("⚠️ SAFETY WARNING")
        safety_group.setStyleSheet("""
            QGroupBox {
                font-size: 13px; font-weight: bold;
                color: #dc3545; border: 2px solid #dc3545;
                border-radius: 6px; margin-top: 8px; padding-top: 8px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        """)
        safety_layout = QVBoxLayout(safety_group)

        warning_label = QLabel(
            "⚠ DANGER: Motors will spin at full speed!\n"
            "   Remove ALL propellers before proceeding!\n"
            "   Keep hands and loose objects away from motors!"
        )
        warning_label.setStyleSheet("color: #dc3545; font-size: 12px; padding: 5px;")
        warning_label.setAlignment(Qt.AlignCenter)
        safety_layout.addWidget(warning_label)

        btn_layout = QHBoxLayout()
        self.enable_btn = QPushButton("🔓 Enable Motor Control")
        self.enable_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545; color: white; font-weight: bold;
                font-size: 13px; padding: 10px 18px; border-radius: 5px;
            }
            QPushButton:hover { background-color: #c82333; }
            QPushButton:disabled { background-color: #6c757d; color: #aaa; }
        """)
        self.enable_btn.clicked.connect(self._on_enable_clicked)
        btn_layout.addWidget(self.enable_btn)

        self.disable_btn = QPushButton("🔒 Disable All Motors")
        self.disable_btn.setEnabled(False)
        self.disable_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745; color: white; font-weight: bold;
                font-size: 13px; padding: 10px 18px; border-radius: 5px;
            }
            QPushButton:hover { background-color: #218838; }
            QPushButton:disabled { background-color: #6c757d; color: #aaa; }
        """)
        self.disable_btn.clicked.connect(self._on_disable_clicked)
        btn_layout.addWidget(self.disable_btn)
        safety_layout.addLayout(btn_layout)

        layout.addWidget(safety_group)

        # ===== 主内容区: 左侧飞机图 + 右侧控制面板 =====
        content_layout = QHBoxLayout()
        content_layout.setSpacing(12)

        # 左侧: X型飞机示意图
        diagram_group = QGroupBox("Quadcopter Layout (X-Type)")
        diagram_group.setStyleSheet("""
            QGroupBox {
                font-size: 13px; font-weight: bold; color: #17a2b8;
                border: 1px solid #495057; border-radius: 6px;
                margin-top: 8px; padding-top: 8px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        """)
        diagram_layout = QVBoxLayout(diagram_group)
        self.diagram = QuadcopterDiagram()
        diagram_layout.addWidget(self.diagram)
        content_layout.addWidget(diagram_group, stretch=0)

        # 右侧: 电机控制面板
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # 状态栏
        status_frame = QFrame()
        status_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(6, 4, 6, 4)

        self.status_label = QLabel("🔒 Motors DISABLED")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #dc3545;")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        right_layout.addWidget(status_frame)

        # 电机滑块控制
        motor_group = QGroupBox("Motor Output Control")
        motor_group.setStyleSheet("""
            QGroupBox {
                font-size: 13px; font-weight: bold; color: #17a2b8;
                border: 1px solid #495057; border-radius: 6px;
                margin-top: 8px; padding-top: 8px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        """)
        motor_grid = QGridLayout(motor_group)
        motor_grid.setSpacing(6)

        self.sliders = []
        self.value_labels = []
        self.spin_boxes = []
        colors = ['#ffaa00', '#44ff44', '#4488ff', '#ff4444']
        names = ['M4 (Front-Right)', 'M2 (Rear-Left)', 'M3 (Front-Left)', 'M1 (Rear-Right)']

        for i in range(self.MOTOR_COUNT):
            name_label = QLabel(names[i])
            name_label.setStyleSheet(f"font-weight: bold; color: {colors[i]}; min-width: 130px;")
            motor_grid.addWidget(name_label, i, 0)

            slider = QSlider(Qt.Horizontal)
            slider.setMinimum(self.PWM_MIN)
            slider.setMaximum(self.PWM_MAX)
            slider.setValue(self.PWM_MIN)
            slider.setEnabled(False)
            slider.setTickPosition(QSlider.TicksBelow)
            slider.setTickInterval(100)
            slider.setStyleSheet(f"""
                QSlider::groove:horizontal {{
                    border: 1px solid #495057; height: 8px;
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #28a745, stop:0.5 #ffc107, stop:1 #dc3545);
                    border-radius: 4px;
                }}
                QSlider::handle:horizontal {{
                    background: {colors[i]}; border: 2px solid white;
                    width: 18px; margin: -6px 0; border-radius: 9px;
                }}
                QSlider::sub-page:horizontal {{ background: transparent; }}
            """)
            slider.valueChanged.connect(lambda v, idx=i: self._on_slider_changed(idx, v))
            self.sliders.append(slider)
            motor_grid.addWidget(slider, i, 1)

            val_label = QLabel(f"{self.PWM_MIN} μs")
            val_label.setStyleSheet("font-family: Consolas; font-size: 11px; min-width: 55px;")
            val_label.setAlignment(Qt.AlignCenter)
            self.value_labels.append(val_label)
            motor_grid.addWidget(val_label, i, 2)

            spin = QSpinBox()
            spin.setRange(self.PWM_MIN, self.PWM_MAX)
            spin.setValue(self.PWM_MIN)
            spin.setEnabled(False)
            spin.setSuffix(" μs")
            spin.setStyleSheet("min-width: 85px;")
            spin.valueChanged.connect(lambda v, idx=i: self._on_spin_changed(idx, v))
            self.spin_boxes.append(spin)
            motor_grid.addWidget(spin, i, 3)

        right_layout.addWidget(motor_group)

        # 快捷操作按钮
        quick_group = QGroupBox("Quick Actions")
        quick_layout = QHBoxLayout(quick_group)

        quick_buttons = [
            ("All Min", self.PWM_MIN),
            ("All Center", self.PWM_CENTER),
            ("All Max", self.PWM_MAX),
        ]
        for text, value in quick_buttons:
            btn = QPushButton(text)
            btn.setEnabled(False)
            btn.clicked.connect(lambda checked, v=value: self._set_all_motors(v))
            btn.setStyleSheet("padding: 5px 12px; font-size: 11px;")
            quick_layout.addWidget(btn)
            setattr(self, f'_quick_btn_{value}', btn)

        right_layout.addWidget(quick_group)
        content_layout.addWidget(right_panel, stretch=1)

        layout.addLayout(content_layout)

        hint = QLabel(
            "💡 Tip: Use 'All Center' to test if all motors respond equally.\n"
            "     Motors only respond when ENABLED and FC is DISARMED."
        )
        hint.setStyleSheet("color: #888; font-size: 11px; padding: 3px;")
        layout.addWidget(hint)

    def _on_enable_clicked(self):
        reply = QMessageBox.warning(
            self, "⚠️ FINAL SAFETY CHECK",
            "Are you ABSOLUTELY SURE?\n\n"
            "• ALL propellers REMOVED?\n"
            "• No people or objects near motors?\n"
            "• You understand motors will SPIN?\n\n"
            "This action CANNOT be undone!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self.safety_confirmed = True
        self.motors_enabled = True

        for s in self.sliders:
            s.setEnabled(True)
        for sp in self.spin_boxes:
            sp.setEnabled(True)
        for attr in ['_quick_btn_1000', '_quick_btn_1500', '_quick_btn_2000']:
            getattr(self, attr).setEnabled(True)

        self.enable_btn.setEnabled(False)
        self.disable_btn.setEnabled(True)
        self.status_label.setText("🟢 Motors ENABLED - Use sliders to control")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #28a745;")
        self.setWindowTitle("Motor Test - ACTIVE ⚡")
        self.diagram.set_motors_enabled(True)

        self._send_motor_values()

    def _on_disable_clicked(self):
        self.motors_enabled = False

        self._set_all_motors(self.PWM_MIN)
        self._send_motor_values()

        for s in self.sliders:
            s.setEnabled(False)
            s.setValue(self.PWM_MIN)
        for sp in self.spin_boxes:
            sp.setEnabled(False)
            sp.setValue(self.PWM_MIN)
        for attr in ['_quick_btn_1000', '_quick_btn_1500', '_quick_btn_2000']:
            getattr(self, attr).setEnabled(False)

        self.enable_btn.setEnabled(True)
        self.disable_btn.setEnabled(False)
        self.status_label.setText("🔒 Motors DISABLED")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #dc3545;")
        self.setWindowTitle("Motor Test - Safety Mode")
        self.diagram.set_motors_enabled(False)

    def _on_slider_changed(self, index, value):
        self.value_labels[index].setText(f"{value} μs")
        self.spin_boxes[index].blockSignals(True)
        self.spin_boxes[index].setValue(value)
        self.spin_boxes[index].blockSignals(False)
        self.diagram.set_motor_value(index, value)
        if self.motors_enabled:
            self._send_motor_values()

    def _on_spin_changed(self, index, value):
        self.sliders[index].blockSignals(True)
        self.sliders[index].setValue(value)
        self.sliders[index].blockSignals(False)
        self.value_labels[index].setText(f"{value} μs")
        self.diagram.set_motor_value(index, value)
        if self.motors_enabled:
            self._send_motor_values()

    def _set_all_motors(self, value):
        for i, s in enumerate(self.sliders):
            s.setValue(value)

    def _send_motor_values(self):
        values = [s.value() for s in self.sliders]
        cmd = self.parser.set_motor_values(values) if hasattr(self, 'parser') else None
        if cmd:
            self.send_msp_data.emit(cmd)

    def set_parser(self, parser):
        self.parser = parser

    def closeEvent(self, event):
        if self.motors_enabled:
            self._set_all_motors(self.PWM_MIN)
            self._send_motor_values()
        event.accept()


def show_motor_test_dialog(parent=None):
    dialog = MotorTestDialog(parent)
    dialog.show()
    return dialog
