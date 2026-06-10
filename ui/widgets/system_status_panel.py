"""
System Status Panel Widget
Displays flight controller system status indicators including:
- Sensor status (gyro, accel, mag, baro, GPS, etc.)
- I2C error counter
- Arming flags (detailed)
- System health overview
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QGroupBox, QFrame, QGridLayout, QScrollArea)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class SystemStatusPanel(QWidget):
    """System Status Dashboard"""

    # Sensor status bit definitions (INAV standard)
    SENSOR_GYRO = 1 << 0
    SENSOR_ACCEL = 1 << 1
    SENSOR_MAG = 1 << 2
    SENSOR_BARO = 1 << 3
    SENSOR_GPS = 1 << 4
    SENSOR_SONAR = 1 << 5

    def __init__(self, parent=None):
        super().__init__(parent)

        self.sensor_status = 0
        self.i2c_errors = 0
        self.arming_flags = 0
        self.cpu_load = 0
        self.cycle_time = 0

        # Status labels dictionary
        self.status_labels = {}

        self._setup_ui()

    def _setup_ui(self):
        """Setup UI with status indicators"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)

        # Title
        title_label = QLabel("System Health Monitor")
        title_label.setStyleSheet("""
            color: #00bfff;
            font-size: 12px;
            font-weight: bold;
            padding: 3px;
        """)
        layout.addWidget(title_label)

        # ===== Sensors Status Group =====
        sensor_group = QGroupBox("Sensor Status")
        sensor_group.setStyleSheet(self._get_groupbox_style())
        sensor_layout = QGridLayout(sensor_group)
        sensor_layout.setSpacing(10)

        sensors_config = [
            ("Gyroscope", "sensor_gyro", self.SENSOR_GYRO, "#28a745"),
            ("Accelerometer", "sensor_accel", self.SENSOR_ACCEL, "#17a2b8"),
            ("Magnetometer", "sensor_mag", self.SENSOR_MAG, "#6f42c1"),
            ("Barometer", "sensor_baro", self.SENSOR_BARO, "#fd7e14"),
            ("GPS", "sensor_gps", self.SENSOR_GPS, "#ffc107"),
            ("Sonar", "sensor_sonar", self.SENSOR_SONAR, "#20c997")
        ]

        for i, (name, key, bitmask, color) in enumerate(sensors_config):
            row = i // 3
            col = i % 3 * 2

            # Sensor name label
            name_lbl = QLabel(f"{name}:")
            name_lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold;")
            name_lbl.setMinimumWidth(90)
            sensor_layout.addWidget(name_lbl, row, col)

            # Status indicator
            status_lbl = QLabel("OFFLINE")
            status_lbl.setStyleSheet("""
                color: #dc3545;
                font-size: 10px;
                font-weight: bold;
                padding: 3px 8px;
                background-color: #4d0000;
                border-radius: 3px;
                min-width: 60px;
            """)
            status_lbl.setAlignment(Qt.AlignCenter)
            self.status_labels[key] = status_lbl
            sensor_layout.addWidget(status_lbl, row, col + 1)

        layout.addWidget(sensor_group)

        # ===== Communication & Errors Group =====
        comm_group = QGroupBox("Communication & Errors")
        comm_group.setStyleSheet(self._get_groupbox_style())
        comm_layout = QGridLayout(comm_group)
        comm_layout.setSpacing(12)

        # I2C Error Counter
        i2c_name = QLabel("I2C Errors:")
        i2c_name.setStyleSheet("color: #ffc107; font-size: 11px; font-weight: bold;")
        comm_layout.addWidget(i2c_name, 0, 0)

        self.i2c_error_label = QLabel("0")
        self.i2c_error_label.setStyleSheet("""
            color: #fff;
            font-size: 18px;
            font-weight: bold;
            font-family: Consolas, monospace;
            padding: 5px 15px;
            background-color: #1e1e1e;
            border-radius: 3px;
            min-width: 80px;
        """)
        self.i2c_error_label.setAlignment(Qt.AlignCenter)
        comm_layout.addWidget(self.i2c_error_label, 0, 1)

        # Cycle Time Summary
        cycle_name = QLabel("Loop Time:")
        cycle_name.setStyleSheet("color: #ff8c00; font-size: 11px; font-weight: bold;")
        comm_layout.addWidget(cycle_name, 0, 2)

        self.cycle_summary_label = "--- us"
        self.cycle_summary_label_obj = QLabel(self.cycle_summary_label)
        self.cycle_summary_label_obj.setStyleSheet("""
            color: #ff8c00;
            font-size: 16px;
            font-weight: bold;
            font-family: Consolas, monospace;
            padding: 5px 15px;
            background-color: #1e1e1e;
            border-radius: 3px;
            min-width: 100px;
        """)
        self.cycle_summary_label_obj.setAlignment(Qt.AlignCenter)
        comm_layout.addWidget(self.cycle_summary_label_obj, 0, 3)

        layout.addWidget(comm_group)

        # ===== Arming Flags Group =====
        arming_group = QGroupBox("Arming Flags (Detailed)")
        arming_group.setStyleSheet(self._get_groupbox_style())
        arming_layout = QVBoxLayout(arming_group)

        # Arming status display
        self.arming_status_label = QLabel("DISARMED")
        self.arming_status_label.setStyleSheet("""
            color: #28a745;
            font-size: 18px;
            font-weight: bold;
            padding: 10px;
            background-color: #001e0d;
            border-radius: 4px;
            text-align: center;
        """)
        self.arming_status_label.setAlignment(Qt.AlignCenter)
        arming_layout.addWidget(self.arming_status_label)

        # Arming flags detail grid
        flags_frame = QFrame()
        flags_frame.setStyleSheet("background-color: #1e1e1e; border-radius: 3px; padding: 5px;")
        flags_layout = QGridLayout(flags_frame)
        flags_layout.setSpacing(6)

        # Common arming flag bits (INAV/CF standard)
        arming_flags_config = [
            ("ARMED", 0, "#dc3545"),
            ("WAS_EVER_ARMED", 1, "#ffc107"),
            ("BLOCKED", 2, "#6c757d"),
            ("FAILSAFE", 7, "#17a2b8"),
            ("GPS_FIX", 9, "#20c997"),
            ("ANGLE_MODE", 22, "#28a745"),
            ("HORIZON_MODE", 23, "#6f42c1"),
        ]

        for i, (name, bit, color) in enumerate(arming_flags_config):
            row = i // 4
            col = i % 4

            flag_check = QLabel(f"☐ {name}")
            flag_check.setStyleSheet(f"color: {color}; font-size: 10px; padding: 2px;")
            flag_key = f"flag_{bit}"
            self.status_labels[flag_key] = flag_check
            flags_layout.addWidget(flag_check, row, col)

        arming_layout.addWidget(flags_frame)

        layout.addWidget(arming_group)

        # ===== System Overview =====
        overview_group = QGroupBox("Quick Overview")
        overview_group.setStyleSheet(self._get_groupbox_style())
        overview_layout = QHBoxLayout(overview_group)

        # CPU Load mini gauge
        cpu_frame = QFrame()
        cpu_frame.setStyleSheet("background-color: #1e1e1e; border-radius: 3px; padding: 8px;")
        cpu_vlayout = QVBoxLayout(cpu_frame)

        cpu_title = QLabel("CPU LOAD")
        cpu_title.setStyleSheet("color: #888; font-size: 10px;")
        cpu_title.setAlignment(Qt.AlignCenter)

        self.cpu_mini_label = QLabel("0%")
        self.cpu_mini_label.setStyleSheet("""
            color: #28a745;
            font-size: 24px;
            font-weight: bold;
            font-family: Consolas, monospace;
        """)
        self.cpu_mini_label.setAlignment(Qt.AlignCenter)

        cpu_vlayout.addWidget(cpu_title)
        cpu_vlayout.addWidget(self.cpu_mini_label)
        overview_layout.addWidget(cpu_frame)

        # System health indicator
        health_frame = QFrame()
        health_frame.setStyleSheet("background-color: #1e1e1e; border-radius: 3px; padding: 8px;")
        health_vlayout = QVBoxLayout(health_frame)

        health_title = QLabel("HEALTH")
        health_title.setStyleSheet("color: #888; font-size: 10px;")
        health_title.setAlignment(Qt.AlignCenter)

        self.health_indicator = QLabel("GOOD")
        self.health_indicator.setStyleSheet("""
            color: #28a745;
            font-size: 20px;
            font-weight: bold;
            padding: 5px;
            background-color: #001e0d;
            border-radius: 3px;
        """)
        self.health_indicator.setAlignment(Qt.AlignCenter)

        health_vlayout.addWidget(health_title)
        health_vlayout.addWidget(self.health_indicator)
        overview_layout.addWidget(health_frame)

        layout.addWidget(overview_group)
        layout.addStretch()

    def update_system_status(self, sensor_status: int, i2c_errors: int,
                             arming_flags: int, cpu_load: int, cycle_time: int):
        """Update all system status indicators"""
        self.sensor_status = sensor_status
        self.i2c_errors = i2c_errors
        self.arming_flags = arming_flags
        self.cpu_load = cpu_load
        self.cycle_time = cycle_time

        # Update sensor status
        sensors_map = {
            'sensor_gyro': (self.SENSOR_GYRO, "GYRO"),
            'sensor_accel': (self.SENSOR_ACCEL, "ACCEL"),
            'sensor_mag': (self.SENSOR_MAG, "MAG"),
            'sensor_baro': (self.SENSOR_BARO, "BARO"),
            'sensor_gps': (self.SENSOR_GPS, "GPS"),
            'sensor_sonar': (self.SENSOR_SONAR, "SONAR")
        }

        for key, (bitmask, short_name) in sensors_map.items():
            if key in self.status_labels:
                is_active = (sensor_status & bitmask) != 0
                label = self.status_labels[key]

                if is_active:
                    label.setText("✓ ONLINE")
                    label.setStyleSheet("""
                        color: #28a745;
                        font-size: 10px;
                        font-weight: bold;
                        padding: 3px 8px;
                        background-color: #001e0d;
                        border-radius: 3px;
                    """)
                else:
                    label.setText("✗ OFFLINE")
                    label.setStyleSheet("""
                        color: #dc3545;
                        font-size: 10px;
                        font-weight: bold;
                        padding: 3px 8px;
                        background-color: #4d0000;
                        border-radius: 3px;
                    """)

        # Update I2C errors
        self.i2c_error_label.setText(str(i2c_errors))

        if i2c_errors > 100:
            self.i2c_error_label.setStyleSheet("""
                color: #dc3545;
                font-size: 18px;
                font-weight: bold;
                font-family: Consolas, monospace;
                padding: 5px 15px;
                background-color: #4d0000;
                border-radius: 3px;
            """)
        elif i2c_errors > 10:
            self.i2c_error_label.setStyleSheet("""
                color: #ffc107;
                font-size: 18px;
                font-weight: bold;
                font-family: Consolas, monospace;
                padding: 5px 15px;
                background-color: #4d4d00;
                border-radius: 3px;
            """)
        else:
            self.i2c_error_label.setStyleSheet("""
                color: #28a745;
                font-size: 18px;
                font-weight: bold;
                font-family: Consolas, monospace;
                padding: 5px 15px;
                background-color: #001e0d;
                border-radius: 3px;
            """)

        # Update cycle time summary
        if cycle_time > 0:
            self.cycle_summary_label_obj.setText(f"{cycle_time} us")

        # Update arming flags
        is_armed = (arming_flags & 0x01) != 0

        if is_armed:
            self.arming_status_label.setText("⚡ ARMED")
            self.arming_status_label.setStyleSheet("""
                color: #dc3545;
                font-size: 18px;
                font-weight: bold;
                padding: 10px;
                background-color: #4d0000;
                border-radius: 4px;
            """)
        else:
            self.arming_status_label.setText("🔒 DISARMED")
            self.arming_status_label.setStyleSheet("""
                color: #28a745;
                font-size: 18px;
                font-weight: bold;
                padding: 10px;
                background-color: #001e0d;
                border-radius: 4px;
            """)

        # Update individual flag bits
        for key, label in self.status_labels.items():
            if key.startswith('flag_'):
                try:
                    bit_num = int(key.split('_')[1])
                    is_set = (arming_flags >> bit_num) & 1 == 1

                    if is_set:
                        label.setText(f"☑ {label.text().split(' ', 1)[1] if ' ' in label.text() else ''}")
                    else:
                        current_text = label.text()
                        if current_text.startswith('☑'):
                            pass  # Keep as is
                        elif current_text.startswith('☐'):
                            pass  # Keep as is
                except (ValueError, IndexError):
                    pass

        # Update CPU load mini display
        self.cpu_mini_label.setText(f"{cpu_load}%")

        if cpu_load >= 80:
            self.cpu_mini_label.setStyleSheet("""
                color: #dc3545;
                font-size: 24px;
                font-weight: bold;
                font-family: Consolas, monospace;
            """)
        elif cpu_load >= 50:
            self.cpu_mini_label.setStyleSheet("""
                color: #ffc107;
                font-size: 24px;
                font-weight: bold;
                font-family: Consolas, monospace;
            """)
        else:
            self.cpu_mini_label.setStyleSheet("""
                color: #28a745;
                font-size: 24px;
                font-weight: bold;
                font-family: Consolas, monospace;
            """)

        # Calculate overall system health
        issues = []

        if cpu_load >= 80:
            issues.append("High CPU")
        if i2c_errors > 50:
            issues.append("I2C Errors")
        if sensor_status == 0:
            issues.append("No Sensors")

        if len(issues) == 0:
            self.health_indicator.setText("✓ GOOD")
            self.health_indicator.setStyleSheet("""
                color: #28a745;
                font-size: 20px;
                font-weight: bold;
                padding: 5px;
                background-color: #001e0d;
                border-radius: 3px;
            """)
        elif len(issues) <= 2:
            self.health_indicator.setText(f"⚠ {len(issues)} ISSUE(S)")
            self.health_indicator.setStyleSheet("""
                color: #ffc107;
                font-size: 18px;
                font-weight: bold;
                padding: 5px;
                background-color: #4d4d00;
                border-radius: 3px;
            """)
        else:
            self.health_indicator.setText(f"✗ CRITICAL")
            self.health_indicator.setStyleSheet("""
                color: #dc3545;
                font-size: 20px;
                font-weight: bold;
                padding: 5px;
                background-color: #4d0000;
                border-radius: 3px;
            """)

    @staticmethod
    def _get_groupbox_style() -> str:
        return """
            QGroupBox {
                font-weight: bold;
                font-size: 11px;
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
