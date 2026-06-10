"""
Cycle Time Monitor Widget
Real-time flight controller loop time visualization
Shows main loop execution time with statistics and target frequency indicator
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QGroupBox, QFrame, QGridLayout)
from PyQt5.QtCore import Qt
import pyqtgraph as pg
import numpy as np
from collections import deque


class CycleTimeWidget(QWidget):
    """Cycle Time Real-time Monitor"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.max_points = 300  # Display last 300 samples
        self.buffer_size = 500

        # Target loop frequency (typical: 400Hz = 2500us, 1000Hz = 1000us)
        self.target_cycle_time = 2500  # Default 400Hz target

        # Data buffer
        self.cycle_buffer = deque(maxlen=self.buffer_size)

        # Statistics
        self.current_time = 0
        self.avg_time = 0
        self.max_time = 0
        self.min_time = 99999

        # Plot widget and curve
        self.plot_widget = None
        self.cycle_curve = None
        self.target_line = None

        # Value labels
        self.current_label = None
        self.freq_label = None
        self.avg_label = None
        self.max_label = None
        self.jitter_label = None

        self._setup_ui()

    def _setup_ui(self):
        """Setup UI with plot and statistics"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Title
        title_label = QLabel("Main Loop Cycle Time (us)")
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
        self.plot_widget.setLabel('left', 'Time', units='us')
        self.plot_widget.setLabel('bottom', 'Time', units='samples')
        self.plot_widget.setYRange(0, 5000)  # 0-5ms range
        self.plot_widget.setMinimumHeight(180)

        # Target line (400Hz = 2500us)
        self.target_line = pg.InfiniteLine(
            pos=self.target_cycle_time,
            angle=0,
            pen=pg.mkPen(color='#00bfff', style=Qt.DashLine, width=2)
        )
        self.plot_widget.addItem(self.target_line)

        # Cycle time curve
        self.cycle_curve = self.plot_widget.plot(
            pen=pg.mkPen(color='#ff8c00', width=2),
            fillLevel=0,
            brush=pg.mkBrush(255, 140, 0, 40)  # Semi-transparent orange
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
        stats_layout.setSpacing(12)

        # Current cycle time
        current_group = QGroupBox("Current")
        current_group.setStyleSheet(self._get_groupbox_style())
        current_layout = QVBoxLayout(current_group)

        self.current_label = QLabel("0 us")
        self.current_label.setStyleSheet("""
            color: #ff8c00;
            font-size: 24px;
            font-weight: bold;
            font-family: Consolas, monospace;
            padding: 5px;
        """)
        self.current_label.setAlignment(Qt.AlignCenter)
        current_layout.addWidget(self.current_label)

        stats_layout.addWidget(current_group, 0, 0)

        # Frequency display
        freq_group = QGroupBox("Frequency")
        freq_group.setStyleSheet(self._get_groupbox_style())
        freq_layout = QVBoxLayout(freq_group)

        self.freq_label = QLabel("--- Hz")
        self.freq_label.setStyleSheet("""
            color: #17a2b8;
            font-size: 24px;
            font-weight: bold;
            font-family: Consolas, monospace;
            padding: 5px;
        """)
        self.freq_label.setAlignment(Qt.AlignCenter)
        freq_layout.addWidget(self.freq_label)

        stats_layout.addWidget(freq_group, 0, 1)

        # Average time
        avg_group = QGroupBox("Average")
        avg_group.setStyleSheet(self._get_groupbox_style())
        avg_layout = QVBoxLayout(avg_group)

        self.avg_label = QLabel("0 us")
        self.avg_label.setStyleSheet("""
            color: #28a745;
            font-size: 20px;
            font-weight: bold;
            font-family: Consolas, monospace;
            padding: 5px;
        """)
        self.avg_label.setAlignment(Qt.AlignCenter)
        avg_layout.addWidget(self.avg_label)

        stats_layout.addWidget(avg_group, 0, 2)

        # Max/Min/Jitter
        maxmin_group = QGroupBox("Max / Min / Jitter")
        maxmin_group.setStyleSheet(self._get_groupbox_style())
        maxmin_layout = QHBoxLayout(maxmin_group)

        for label_text, attr_name in [("MAX", "max_label"), ("MIN", "min_label"), ("JITTER", "jitter_label")]:
            frame = QFrame()
            frame.setStyleSheet("background-color: #1e1e1e; border-radius: 2px; padding: 4px;")
            vlayout = QVBoxLayout(frame)

            value_label = QLabel("0 us")
            value_label.setStyleSheet(f"color: {'#dc3545' if 'MAX' in label_text else '#28a745' if 'MIN' in label_text else '#ffc107'}; "
                                     f"font-size: 16px; font-weight: bold;")
            value_label.setAlignment(Qt.AlignCenter)
            setattr(self, attr_name, value_label)

            title_lbl = QLabel(label_text)
            title_lbl.setStyleSheet("color: #888; font-size: 9px;")
            title_lbl.setAlignment(Qt.AlignCenter)

            vlayout.addWidget(value_label)
            vlayout.addWidget(title_lbl)
            maxmin_layout.addWidget(frame)

        stats_layout.addWidget(maxmin_group, 0, 3)

        layout.addWidget(stats_frame)

    def update_data(self, cycle_time: int):
        """Update cycle time data"""
        if cycle_time < 0 or cycle_time > 50000:
            return

        # Update buffer
        self.cycle_buffer.append(cycle_time)

        # Calculate statistics
        if len(self.cycle_buffer) > 0:
            data_array = np.array(list(self.cycle_buffer))
            display_data = data_array[-self.max_points:] if len(data_array) >= self.max_points else data_array

            self.current_time = cycle_time
            self.avg_time = int(np.mean(display_data))
            self.max_time = int(np.max(display_data))
            self.min_time = int(np.min(display_data))

            # Calculate jitter (standard deviation of recent samples)
            if len(display_data) > 10:
                jitter = int(np.std(display_data[-50:]) if len(display_data) >= 50 else np.std(display_data))
            else:
                jitter = 0

        # Update curve
        if len(self.cycle_buffer) > 0:
            data = list(self.cycle_buffer)[-self.max_points:]
            x_data = np.arange(len(data))
            y_data = np.array(data)
            self.cycle_curve.setData(x_data, y_data)

            # Dynamic Y-axis scaling based on data
            if self.max_time > 4000:
                self.plot_widget.setYRange(0, int(self.max_time * 1.2))

            # Calculate frequency
            if self.avg_time > 0:
                freq = int(1000000 / self.avg_time)  # Convert to Hz
            else:
                freq = 0

            # Update labels
            self.current_label.setText(f"{self.current_time} us")
            self.freq_label.setText(f"{freq} Hz")
            self.avg_label.setText(f"{self.avg_time} us")
            self.max_label.setText(f"{self.max_time} us")
            self.min_label.setText(f"{self.min_time} us")
            self.jitter_label.setText(f"±{jitter} us")

            # Color coding for current value
            if self.current_time > self.target_cycle_time * 1.5:
                color = '#dc3545'  # Red - Too slow
            elif self.current_time > self.target_cycle_time * 1.2:
                color = '#ffc107'  # Yellow - Slightly slow
            else:
                color = '#28a745'  # Green - Good

            self.current_label.setStyleSheet(f"""
                color: {color};
                font-size: 24px;
                font-weight: bold;
                font-family: Consolas, monospace;
                padding: 5px;
            """)

    def set_target_frequency(self, freq_hz: int):
        """Set target loop frequency (updates target line position)"""
        if freq_hz > 0:
            self.target_cycle_time = int(1000000 / freq_hz)
            self.target_line.setPos(self.target_cycle_time)

    def clear_data(self):
        """Clear all data"""
        self.cycle_buffer.clear()
        self.current_time = 0
        self.avg_time = 0
        self.max_time = 0
        self.min_time = 99999

        self.cycle_curve.setData([], [])
        self.current_label.setText("0 us")
        self.freq_label.setText("--- Hz")
        self.avg_label.setText("0 us")
        self.max_label.setText("0 us")
        self.min_label.setText("0 us")
        self.jitter_label.setText("0 us")

        self.plot_widget.setYRange(0, 5000)

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
