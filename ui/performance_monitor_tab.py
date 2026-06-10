"""
Performance Monitor Tab
Complete flight controller performance monitoring interface
Integrates CPU load, cycle time, and system status visualizations
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
                             QTabWidget, QGroupBox, QLabel)
from PyQt5.QtCore import Qt

from ui.widgets.cpu_load_widget import CPULoadWidget
from ui.widgets.cycle_time_widget import CycleTimeWidget
from ui.widgets.system_status_panel import SystemStatusPanel


class PerformanceMonitorTab(QWidget):
    """Performance Monitoring Tab - Complete Interface"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.cpu_widget = None
        self.cycle_widget = None
        self.status_panel = None

        self._setup_ui()

    def _setup_ui(self):
        """Setup complete performance monitoring UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # Main splitter for left-right layout
        splitter = QSplitter(Qt.Horizontal)

        # ===== Left Panel: Performance Graphs =====
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)
        left_layout.setSpacing(10)

        # CPU Load Monitor (top half)
        self.cpu_widget = CPULoadWidget()
        left_layout.addWidget(self.cpu_widget, stretch=1)

        # Cycle Time Monitor (bottom half)
        self.cycle_widget = CycleTimeWidget()
        left_layout.addWidget(self.cycle_widget, stretch=1)

        splitter.addWidget(left_panel)

        # ===== Right Panel: System Status Dashboard =====
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(5, 5, 5, 5)

        # System Status Panel
        self.status_panel = SystemStatusPanel()
        right_layout.addWidget(self.status_panel)

        splitter.addWidget(right_panel)

        # Set splitter sizes (55% graphs, 45% status)
        splitter.setSizes([550, 450])

        main_layout.addWidget(splitter)

    def update_performance_data(self, cpu_load: int = 0, cycle_time: int = 0,
                                 sensor_status: int = 0, i2c_errors: int = 0,
                                 arming_flags: int = 0):
        """
        Update all performance monitoring displays with new data from FC

        Args:
            cpu_load: CPU system load percentage (0-100)
            cycle_time: Main loop cycle time in microseconds
            sensor_status: Sensor status bitmask (gyro, accel, mag, etc.)
            i2c_errors: I2C communication error counter
            arming_flags: Arming flags bitmask (detailed status bits)
        """
        # Update CPU load widget
        if self.cpu_widget and cpu_load > 0:
            self.cpu_widget.update_data(cpu_load)

        # Update cycle time widget
        if self.cycle_widget and cycle_time > 0:
            self.cycle_widget.update_data(cycle_time)

        # Update system status panel
        if self.status_panel:
            self.status_panel.update_system_status(
                sensor_status=sensor_status,
                i2c_errors=i2c_errors,
                arming_flags=arming_flags,
                cpu_load=cpu_load,
                cycle_time=cycle_time
            )

    def clear_all_data(self):
        """Clear all performance data and reset displays"""
        if self.cpu_widget:
            self.cpu_widget.clear_data()

        if self.cycle_widget:
            self.cycle_widget.clear_data()

        # Reset status panel to defaults
        if self.status_panel:
            self.status_panel.update_system_status(
                sensor_status=0,
                i2c_errors=0,
                arming_flags=0,
                cpu_load=0,
                cycle_time=0
            )
