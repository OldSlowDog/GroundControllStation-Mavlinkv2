"""
RC Channel Bar Widget
Horizontal bar visualization for RC channels (ROLL, PITCH, YAW, THROTTLE, AUX1-4)
Displays current values with center point marker and color coding
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PyQt5.QtCore import Qt, QRectF, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont, QLinearGradient
import math


class RCChannelBar(QWidget):
    """Single RC channel horizontal bar indicator"""

    def __init__(self, name: str = "CH", min_val: int = 1000, max_val: int = 2000,
                 center: int = 1500, parent=None):
        super().__init__(parent)

        self.name = name
        self.min_val = min_val
        self.max_val = max_val
        self.center = center
        self.value = center

        self.setMinimumHeight(45)
        self.setMaximumHeight(60)
        self.setMinimumWidth(180)

    def set_value(self, value: int):
        """Set current RC value"""
        self.value = max(self.min_val, min(value, self.max_val))
        self.update()

    def get_color_for_value(self) -> QColor:
        """Return color based on value position"""
        range_size = self.max_val - self.min_val

        if abs(self.value - self.center) < range_size * 0.1:
            return QColor(40, 167, 69)  # Green - near center
        elif abs(self.value - self.center) < range_size * 0.3:
            return QColor(255, 193, 7)  # Yellow - moderate
        else:
            return QColor(220, 53, 69)  # Red - extreme

    def paintEvent(self, event):
        """Custom painting for bar visualization"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()

        # Background
        painter.fillRect(0, 0, width, height, QColor(30, 30, 30))

        # Label area (left side)
        label_width = 70
        painter.fillRect(0, 0, label_width, height, QColor(45, 45, 45))

        # Channel name
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Consolas", 10, QFont.Bold)
        painter.setFont(font)
        painter.drawText(QRectF(5, 0, label_width - 10, height),
                         Qt.AlignCenter, self.name)

        # Bar area
        bar_x = label_width + 10
        bar_width = width - label_width - 20
        bar_height = height - 20
        bar_y = 10

        # Bar background track
        track_rect = QRectF(bar_x, bar_y, bar_width, bar_height)
        painter.fillRect(track_rect, QColor(60, 60, 60))
        painter.setPen(QPen(QColor(100, 100, 100), 1))
        painter.drawRect(track_rect)

        # Center point marker (dashed line)
        center_x = bar_x + (self.center - self.min_val) / (self.max_val - self.min_val) * bar_width
        painter.setPen(QPen(QColor(255, 255, 255, 150), 1, Qt.DashLine))
        painter.drawLine(int(center_x), bar_y, int(center_x), bar_y + bar_height)

        # Value bar with gradient
        value_ratio = (self.value - self.min_val) / (self.max_val - self.min_val)
        value_bar_width = value_ratio * bar_width

        if value_bar_width > 2:
            bar_color = self.get_color_for_value()
            gradient = QLinearGradient(bar_x, 0, bar_x + value_bar_width, 0)
            gradient.setColorAt(0, bar_color.darker(120))
            gradient.setColorAt(1, bar_color.lighter(130))

            value_rect = QRectF(bar_x, bar_y + 2, value_bar_width, bar_height - 4)
            painter.fillRect(value_rect, gradient)

        # Value text
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Consolas", 9)
        painter.setFont(font)
        value_text = f"{self.value:4d}"
        painter.drawText(QRectF(bar_x, bar_y, bar_width, bar_height),
                         Qt.AlignCenter, value_text)


class RCBarWidget(QWidget):
    """Container widget for all 8 RC channels"""

    channels_updated = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.channel_bars = {}
        self.channel_names = {
            'rc_roll': 'ROLL',
            'rc_pitch': 'PITCH',
            'rc_throttle': 'THROTTLE',
            'rc_yaw': 'YAW',
            'rc_aux1': 'AUX1',
            'rc_aux2': 'AUX2',
            'rc_aux3': 'AUX3',
            'rc_aux4': 'AUX4'
        }

        self._setup_ui()

    def _setup_ui(self):
        """Setup UI layout"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)

        title_label = QLabel("RC Channels (1000-2000 us)")
        title_label.setStyleSheet("""
            color: #00bfff;
            font-size: 12px;
            font-weight: bold;
            padding: 3px;
        """)
        layout.addWidget(title_label)

        for key, name in self.channel_names.items():
            channel_bar = RCChannelBar(name=name)
            self.channel_bars[key] = channel_bar
            layout.addWidget(channel_bar)

        layout.addStretch()

    def update_channels(self, rc_data: dict):
        """Update all channel values"""
        for key, bar in self.channel_bars.items():
            if key in rc_data:
                bar.set_value(rc_data[key])

        self.channels_updated.emit(rc_data)
        self.update()
