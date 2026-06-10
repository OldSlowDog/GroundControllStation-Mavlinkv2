"""
CPU Load Monitor Widget
Real-time CPU load visualization with history graph and statistics
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QGroupBox, QFrame, QGridLayout)
from PyQt5.QtCore import Qt
import pyqtgraph as pg
import numpy as np
from collections import deque


class CPULoadWidget(QWidget):
    """CPU Load Real-time Monitor"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.max_points = 300  # Display last 300 samples (~15 seconds at 20Hz)
        self.buffer_size = 500

        # Data buffer
        self.cpu_buffer = deque(maxlen=self.buffer_size)

        # Statistics
        self.current_load = 0
        self.avg_load = 0
        self.max_load = 0
        self.min_load = 100

        # Plot widget and curve
        self.plot_widget = None
        self.cpu_curve = None

        # Value labels
        self.current_label = None
        self.avg_label = None
        self.max_label = None
        self.status_label = None

        self._setup_ui()

    def _setup_ui(self):
        """Setup UI with plot and statistics"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Title
        title_label = QLabel("CPU System Load (%)")
        title_label.setStyleSheet("""
            color: #00bfff;
            font-size: 12px;
            font-weight: bold;
            padding: 3px;
        """)
        layout.addWidget(title_label)

        # Main plot
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#1e1e1e')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('left', 'Load', units='%')
        self.plot_widget.setLabel('bottom', 'Time', units='samples')
        self.plot_widget.setYRange(0, 100)
        self.plot_widget.setMinimumHeight(180)

        # Warning zones (50% yellow, 80% red)
        warning_pen = pg.mkPen(color='#ffc107', style=Qt.DashLine, width=1)
        critical_pen = pg.mkPen(color='#dc3545', style=Qt.DashLine, width=1)

        line_50 = pg.InfiniteLine(pos=50, angle=0, pen=warning_pen)
        line_80 = pg.InfiniteLine(pos=80, angle=0, pen=critical_pen)

        self.plot_widget.addItem(line_50)
        self.plot_widget.addItem(line_80)

        # CPU load curve with gradient fill
        self.cpu_curve = self.plot_widget.plot(
            pen=pg.mkPen(color='#28a745', width=2),
            fillLevel=0,
            brush=pg.mkBrush(40, 167, 69, 50)  # Semi-transparent green
        )

        layout.addWidget(self.plot_widget)

        # Statistics panel
        stats_frame = QFrame()
        stats_frame.setStyleSheet("""
            QFrame {
                background-color: #252526;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 8px;
            }
        """)
        stats_layout = QGridLayout(stats_frame)
        stats_layout.setSpacing(15)

        # Current value (large display)
        current_group = QGroupBox("Current")
        current_group.setStyleSheet(self._get_groupbox_style())
        current_layout = QVBoxLayout(current_group)

        self.current_label = QLabel("0%")
        self.current_label.setStyleSheet("""
            color: #28a745;
            font-size: 28px;
            font-weight: bold;
            font-family: Consolas, monospace;
            padding: 5px;
        """)
        self.current_label.setAlignment(Qt.AlignCenter)
        current_layout.addWidget(self.current_label)

        stats_layout.addWidget(current_group, 0, 0)

        # Average value
        avg_group = QGroupBox("Average")
        avg_group.setStyleSheet(self._get_groupbox_style())
        avg_layout = QVBoxLayout(avg_group)

        self.avg_label = QLabel("0%")
        self.avg_label.setStyleSheet("""
            color: #17a2b8;
            font-size: 24px;
            font-weight: bold;
            font-family: Consolas, monospace;
            padding: 5px;
        """)
        self.avg_label.setAlignment(Qt.AlignCenter)
        avg_layout.addWidget(self.avg_label)

        stats_layout.addWidget(avg_group, 0, 1)

        # Max/Min values
        maxmin_group = QGroupBox("Peak / Min")
        maxmin_group.setStyleSheet(self._get_groupbox_style())
        maxmin_layout = QHBoxLayout(maxmin_group)

        max_frame = QFrame()
        max_frame.setStyleSheet("background-color: #1e1e1e; border-radius: 2px; padding: 5px;")
        max_layout_v = QVBoxLayout(max_frame)
        self.max_label = QLabel("0%")
        self.max_label.setStyleSheet("color: #dc3545; font-size: 18px; font-weight: bold;")
        self.max_label.setAlignment(Qt.AlignCenter)
        max_label_title = QLabel("MAX")
        max_label_title.setStyleSheet("color: #888; font-size: 10px;")
        max_label_title.setAlignment(Qt.AlignCenter)
        max_layout_v.addWidget(self.max_label)
        max_layout_v.addWidget(max_label_title)

        min_frame = QFrame()
        min_frame.setStyleSheet("background-color: #1e1e1e; border-radius: 2px; padding: 5px;")
        min_layout_v = QVBoxLayout(min_frame)
        self.min_label = QLabel("100%")
        self.min_label.setStyleSheet("color: #28a745; font-size: 18px; font-weight: bold;")
        self.min_label.setAlignment(Qt.AlignCenter)
        min_label_title = QLabel("MIN")
        min_label_title.setStyleSheet("color: #888; font-size: 10px;")
        min_label_title.setAlignment(Qt.AlignCenter)
        min_layout_v.addWidget(self.min_label)
        min_layout_v.addWidget(min_label_title)

        maxmin_layout.addWidget(max_frame)
        maxmin_layout.addWidget(min_frame)
        stats_layout.addWidget(maxmin_group, 0, 2)

        # Status indicator
        status_group = QGroupBox("Status")
        status_group.setStyleSheet(self._get_groupbox_style())
        status_layout = QVBoxLayout(status_group)

        self.status_label = QLabel("IDLE")
        self.status_label.setStyleSheet("""
            color: #28a745;
            font-size: 16px;
            font-weight: bold;
            padding: 10px;
            background-color: #1e1e1e;
            border-radius: 3px;
        """)
        self.status_label.setAlignment(Qt.AlignCenter)
        status_layout.addWidget(self.status_label)

        stats_layout.addWidget(status_group, 0, 3)

        layout.addWidget(stats_frame)

    def update_data(self, cpu_load: int):
        """Update CPU load data"""
        if cpu_load < 0 or cpu_load > 100:
            return

        # Update buffer
        self.cpu_buffer.append(cpu_load)

        # Calculate statistics
        if len(self.cpu_buffer) > 0:
            data_array = np.array(list(self.cpu_buffer))
            self.current_load = cpu_load
            self.avg_load = int(np.mean(data_array[-self.max_points:]) if len(data_array) >= self.max_points else np.mean(data_array))
            self.max_load = int(np.max(data_array[-self.max_points:])) if len(data_array) >= self.max_points else int(np.max(data_array))
            self.min_load = int(np.min(data_array[-self.max_points:])) if len(data_array) >= self.max_points else int(np.min(data_array))

        # Update curve
        if len(self.cpu_buffer) > 0:
            data = list(self.cpu_buffer)[-self.max_points:]
            x_data = np.arange(len(data))
            y_data = np.array(data)
            self.cpu_curve.setData(x_data, y_data)

            # Dynamic color based on load level
            if self.current_load >= 80:
                color = '#dc3545'  # Red - Critical
                status_text = "CRITICAL"
                status_color = '#4d0000'
            elif self.current_load >= 50:
                color = '#ffc107'  # Yellow - Warning
                status_text = "WARNING"
                status_color = '#4d4d00'
            else:
                color = '#28a745'  # Green - Normal
                status_text = "NORMAL"
                status_color = '#001e0d'

            self.cpu_curve.setPen(pg.mkPen(color=color, width=2))

            # Update labels
            self.current_label.setText(f"{self.current_load}%")
            self.current_label.setStyleSheet(f"color: {color}; font-size: 28px; font-weight: bold;")

            self.avg_label.setText(f"{self.avg_load}%")
            self.max_label.setText(f"{self.max_load}%")
            self.min_label.setText(f"{self.min_load}%")

            self.status_label.setText(status_text)
            self.status_label.setStyleSheet(f"""
                color: {color};
                font-size: 16px;
                font-weight: bold;
                padding: 10px;
                background-color: {status_color};
                border-radius: 3px;
            """)

    def clear_data(self):
        """Clear all data"""
        self.cpu_buffer.clear()
        self.current_load = 0
        self.avg_load = 0
        self.max_load = 0
        self.min_load = 100

        self.cpu_curve.setData([], [])
        self.current_label.setText("0%")
        self.avg_label.setText("0%")
        self.max_label.setText("0%")
        self.min_label.setText("100%")
        self.status_label.setText("IDLE")

    @staticmethod
    def _get_groupbox_style() -> str:
        return """
            QGroupBox {
                font-weight: bold;
                font-size: 11px;
                border: 1px solid #555;
                border-radius: 4px;
                margin-top: 6px;
                padding-top: 6px;
                color: #ccc;
                background-color: #2d2d2d;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 6px;
                padding: 0 3px;
                color: #00bfff;
            }
        """
