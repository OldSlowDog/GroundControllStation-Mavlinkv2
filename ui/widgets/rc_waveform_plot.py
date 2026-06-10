"""
RC Waveform Plot Widget
Real-time waveform display for RC channels using pyqtgraph
Shows historical RC signal data with center line reference
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QGroupBox
from PyQt5.QtCore import Qt
import pyqtgraph as pg
import numpy as np
from collections import deque


class RCWaveformPlot(QWidget):
    """Real-time waveform plot for RC channels"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.max_points = 300  # Display last 300 samples
        self.buffer_size = 500  # Internal buffer size

        # Channel configuration
        self.channels = [
            {'key': 'rc_roll', 'name': 'ROLL', 'color': '#ff4444', 'enabled': True},
            {'key': 'rc_pitch', 'name': 'PITCH', 'color': '#44ff44', 'enabled': True},
            {'key': 'rc_throttle', 'name': 'THROTTLE', 'color': '#ffaa00', 'enabled': True},
            {'key': 'rc_yaw', 'name': 'YAW', 'color': '#4488ff', 'enabled': True},
            {'key': 'rc_aux1', 'name': 'AUX1', 'color': '#aa44ff', 'enabled': False},
            {'key': 'rc_aux2', 'name': 'AUX2', 'color': '#44ffff', 'enabled': False},
            {'key': 'rc_aux3', 'name': 'AUX3', 'color': '#ff88aa', 'enabled': False},
            {'key': 'rc_aux4', 'name': 'AUX4', 'color': '#88ff44', 'enabled': False}
        ]

        # Data buffers for each channel
        self.data_buffers = {ch['key']: deque(maxlen=self.buffer_size)
                            for ch in self.channels}

        # Plot curves
        self.curves = {}
        self.channel_checks = {}

        self._setup_ui()

    def _setup_ui(self):
        """Setup UI with plot and channel toggles"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Title
        title_label = QLabel("RC Waveform (Real-time)")
        title_label.setStyleSheet("""
            color: #00bfff;
            font-size: 12px;
            font-weight: bold;
            padding: 3px;
        """)
        layout.addWidget(title_label)

        # Plot widget
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#1e1e1e')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('left', 'PWM', units='us')
        self.plot_widget.setLabel('bottom', 'Time', units='samples')
        self.plot_widget.setYRange(1000, 2000)
        self.plot_widget.setMinimumHeight(200)

        # Add center line at 1500
        center_line = pg.InfiniteLine(pos=1500, angle=0,
                                       pen=pg.mkPen(color='#ffffff',
                                                   style=Qt.DashLine,
                                                   width=1))
        self.plot_widget.addItem(center_line)

        # Create curves for each enabled channel
        for ch in self.channels:
            if ch['enabled']:
                curve = self.plot_widget.plot(pen=pg.mkPen(color=ch['color'], width=1.5))
                self.curves[ch['key']] = curve

        layout.addWidget(self.plot_widget)

        # Channel toggle checkboxes
        toggle_group = QGroupBox("Visible Channels")
        toggle_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 10px;
                border: 1px solid #555;
                border-radius: 3px;
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
        """)
        toggle_layout = QHBoxLayout(toggle_group)
        toggle_layout.setSpacing(8)

        for ch in self.channels:
            check = QCheckBox(ch['name'])
            check.setChecked(ch['enabled'])
            check.setStyleSheet(f"color: {ch['color']}; font-size: 10px;")
            check.stateChanged.connect(lambda state, key=ch['key']:
                                       self._toggle_channel(key, state))
            self.channel_checks[ch['key']] = check
            toggle_layout.addWidget(check)

        layout.addWidget(toggle_group)

    def _toggle_channel(self, channel_key: str, state: int):
        """Toggle channel visibility"""
        enabled = (state == Qt.Checked)

        if enabled and channel_key not in self.curves:
            # Find channel config
            ch_config = next((ch for ch in self.channels if ch['key'] == channel_key), None)
            if ch_config:
                curve = self.plot_widget.plot(pen=pg.mkPen(color=ch_config['color'], width=1.5))
                self.curves[channel_key] = curve
        elif not enabled and channel_key in self.curves:
            # Remove curve from plot
            curve = self.curves.pop(channel_key)
            self.plot_widget.removeItem(curve)

    def update_data(self, rc_data: dict):
        """Update waveform with new RC data point"""
        # Add new data to buffers
        for key in self.data_buffers:
            if key in rc_data:
                self.data_buffers[key].append(rc_data[key])
            else:
                # Use last value or center if no data
                last_val = self.data_buffers[key][-1] if self.data_buffers[key] else 1500
                self.data_buffers[key].append(last_val)

        # Update curves with latest data
        for key, curve in self.curves.items():
            if key in self.data_buffers and len(self.data_buffers[key]) > 0:
                # Get last max_points samples
                data = list(self.data_buffers[key])[-self.max_points:]
                x_data = np.arange(len(data))
                y_data = np.array(data)
                curve.setData(x_data, y_data)

    def clear_data(self):
        """Clear all waveform data"""
        for key in self.data_buffers:
            self.data_buffers[key].clear()

        for curve in self.curves.values():
            curve.setData([], [])
