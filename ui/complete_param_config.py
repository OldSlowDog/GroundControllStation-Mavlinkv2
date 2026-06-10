"""
Complete Parameter Configuration Tab
Full PX4-style parameter editor with categorized display for FlightOS_V2.

Categories:
  1. Rate PID   - MC_ROLLRATE/PITCHRATE/YAWRATE P/I/D/FF + limits
  2. Angle PID  - MC_ROLL/PITCH/YAW P/I/D + weights
  3. Position   - MPC position/velocity/throttle control
  4. Battery    - BAT voltage/capacity/critical thresholds
  5. Arming     - COM arming checks, disarm timeouts
  6. RC         - RC channel mapping, rate, expo
  7. Sensors    - Gyro LPF, D-term cutoff, board offsets
  8. System     - MAV_SYS_ID, autostart, arm throttle
  9. Motor      - Motor min/max/idle PWM

MQTT Protocol (set_all_params / get_all_params):
  - PX4-style param names in JSON payload
  - save: FC persists RAM params to Flash
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLabel, QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QTabWidget, QGroupBox, QSpinBox,
                             QDoubleSpinBox, QScrollArea, QFrame,
                             QMessageBox, QSlider)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QColor


# ======================================================================
# Category Definitions: PX4 param key → label / default / range
# ======================================================================

class ParamCategory:
    """PX4 param categories with display metadata"""
    
    RATE_PID = {
        'MC_ROLLRATE_P':    ('Roll Rate P', 4.50, 0.0, 20.0, 'float'),
        'MC_ROLLRATE_I':    ('Roll Rate I', 0.030, 0.0, 1.0, 'float'),
        'MC_ROLLRATE_D':    ('Roll Rate D', 0.003, 0.0, 0.1, 'float'),
        'MC_ROLLRATE_FF':   ('Roll Rate FF', 0.0, 0.0, 1.0, 'float'),
        'MC_PITCHRATE_P':   ('Pitch Rate P', 4.50, 0.0, 20.0, 'float'),
        'MC_PITCHRATE_I':   ('Pitch Rate I', 0.030, 0.0, 1.0, 'float'),
        'MC_PITCHRATE_D':   ('Pitch Rate D', 0.003, 0.0, 0.1, 'float'),
        'MC_PITCHRATE_FF':  ('Pitch Rate FF', 0.0, 0.0, 1.0, 'float'),
        'MC_YAWRATE_P':     ('Yaw Rate P', 3.00, 0.0, 20.0, 'float'),
        'MC_YAWRATE_I':     ('Yaw Rate I', 0.020, 0.0, 1.0, 'float'),
        'MC_YAWRATE_D':     ('Yaw Rate D', 0.000, 0.0, 0.1, 'float'),
        'MC_YAWRATE_FF':    ('Yaw Rate FF', 0.0, 0.0, 1.0, 'float'),
        'MC_RR_INT_LIM':    ('Roll I Limit', 0.25, 0.0, 1.0, 'float'),
        'MC_PR_INT_LIM':    ('Pitch I Limit', 0.25, 0.0, 1.0, 'float'),
        'MC_YR_INT_LIM':    ('Yaw I Limit', 0.25, 0.0, 1.0, 'float'),
        'MC_ROLLRATE_MAX':  ('Max Roll Rate', 720.0, 100.0, 1800.0, 'float'),
        'MC_PITCHRATE_MAX': ('Max Pitch Rate', 720.0, 100.0, 1800.0, 'float'),
        'MC_YAWRATE_MAX':   ('Max Yaw Rate', 360.0, 50.0, 900.0, 'float'),
    }

    ANGLE_PID = {
        'MC_ROLL_P':    ('Roll Angle P', 5.50, 0.0, 20.0, 'float'),
        'MC_ROLL_I':    ('Roll Angle I', 0.010, 0.0, 1.0, 'float'),
        'MC_ROLL_D':    ('Roll Angle D', 0.001, 0.0, 0.1, 'float'),
        'MC_PITCH_P':   ('Pitch Angle P', 5.50, 0.0, 20.0, 'float'),
        'MC_PITCH_I':   ('Pitch Angle I', 0.010, 0.0, 1.0, 'float'),
        'MC_PITCH_D':   ('Pitch Angle D', 0.001, 0.0, 0.1, 'float'),
        'MC_YAW_P':     ('Yaw Angle P', 6.00, 0.0, 20.0, 'float'),
        'MC_YAW_I':     ('Yaw Angle I', 0.020, 0.0, 1.0, 'float'),
        'MC_YAW_D':     ('Yaw Angle D', 0.000, 0.0, 0.1, 'float'),
        'MC_YAW_WEIGHT':('Yaw Weight', 0.20, 0.0, 1.0, 'float'),
        'MC_RATE_WEIGHT':('Rate Weight', 0.50, 0.0, 1.0, 'float'),
    }

    POSITION = {
        'MPC_XY_P':         ('XY Pos P', 1.50, 0.0, 5.0, 'float'),
        'MPC_XY_VEL_P':     ('XY Vel P', 0.09, 0.0, 1.0, 'float'),
        'MPC_XY_VEL_I':     ('XY Vel I', 0.02, 0.0, 1.0, 'float'),
        'MPC_XY_VEL_D':     ('XY Vel D', 0.001, 0.0, 0.1, 'float'),
        'MPC_Z_P':          ('Z Pos P', 1.00, 0.0, 5.0, 'float'),
        'MPC_Z_VEL_P':      ('Z Vel P', 4.00, 0.0, 10.0, 'float'),
        'MPC_Z_VEL_I':      ('Z Vel I', 2.00, 0.0, 10.0, 'float'),
        'MPC_ACC_HOR':      ('Horiz Accel', 5.00, 1.0, 15.0, 'float'),
        'MPC_ACC_HOR_MAX':  ('Max Horiz Accel', 8.00, 1.0, 20.0, 'float'),
        'MPC_ACC_UP_MAX':   ('Max Up Accel', 8.00, 1.0, 20.0, 'float'),
        'MPC_ACC_DOWN_MAX': ('Max Down Accel', 4.00, 1.0, 15.0, 'float'),
        'MPC_JERK_MAX':     ('Max Jerk', 8.00, 1.0, 50.0, 'float'),
        'MPC_THR_HOVER':    ('Hover Throttle', 0.50, 0.1, 1.0, 'float'),
        'MPC_THR_MAX':      ('Max Throttle', 1.00, 0.5, 1.0, 'float'),
        'MPC_THR_MIN':      ('Min Throttle', 0.12, 0.0, 0.5, 'float'),
        'MPC_MAN_TILT_MAX': ('Max Tilt (Manual)', 45.0, 10.0, 90.0, 'float'),
        'MPC_MAN_YAW_MAX':  ('Max Yaw Rate', 150.0, 30.0, 360.0, 'float'),
        'MPC_LAND_SPEED':   ('Land Speed', 0.70, 0.2, 2.0, 'float'),
        'MPC_CRUISE_SPEED': ('Cruise Speed', 5.00, 1.0, 15.0, 'float'),
        'MPC_HOLD_MAX_XY':  ('Hold Max XY', 0.80, 0.2, 5.0, 'float'),
    }

    BATTERY = {
        'BAT_A_VOLTAGE':    ('Full Voltage', 12.6, 8.0, 25.2, 'float'),
        'BAT_A_CAPACITY':   ('Capacity (mAh)', 1500, 500, 10000, 'int'),
        'BAT_CRIT_V':       ('Critical Voltage', 10.5, 6.0, 22.0, 'float'),
        'BAT_EMERGEN_V':    ('Emergency Voltage', 10.0, 6.0, 21.0, 'float'),
        'BAT_N_CELLS':      ('Cell Count', 3, 1, 6, 'int'),
        'BAT_LOW_ACT':      ('Low Battery Action', 0, 0, 2, 'enum'),
    }

    ARMING = {
        'COM_ARM_ARSPD_EN':  ('Airspeed Check', 0, 0, 1, 'int'),
        'COM_ARM_CHK_EN':    ('Enable Arm Checks', 1, 0, 1, 'int'),
        'COM_ARM_GPS_XY_RAD':('GPS Accept Radius', 50.0, 0.0, 200.0, 'float'),
        'COM_ARM_MAG_EN':    ('Mag Check', 1, 0, 1, 'int'),
        'COM_ARM_EKF_CHK':   ('EKF Check', 1, 0, 2, 'int'),
        'COM_ARM_BAT_CAP_EN':('Battery Capacity Check', 0, 0, 1, 'int'),
        'COM_DISARM_TM':     ('Disarm Timeout (s)', 10, 0, 300, 'int'),
        'COM_DISARM_LAND_TM':('Post-Land Disarm', 2, 0, 60, 'int'),
        'IMB_MAN_THR_MAX':   ('Manual Throttle Limit', 0.90, 0.3, 1.0, 'float'),
    }

    RC = {
        'RC_MAP_ROLL':     ('Roll Channel', 1, 0, 18, 'int'),
        'RC_MAP_PITCH':    ('Pitch Channel', 2, 0, 18, 'int'),
        'RC_MAP_YAW':      ('Yaw Channel', 4, 0, 18, 'int'),
        'RC_MAP_THROTTLE': ('Throttle Channel', 3, 0, 18, 'int'),
        'RC_MAP_ARM_SW':   ('Arm Switch Channel', 5, 0, 18, 'int'),
        'RC_MAP_FLTMODE':  ('Flight Mode Chan', 6, 0, 18, 'int'),
        'RC_CHAN_CNT':     ('Channel Count', 8, 4, 18, 'int'),
        'RC_RATE':         ('RC Rate', 1.00, 0.1, 3.0, 'float'),
        'RC_EXPO':         ('RC Expo', 0.00, 0.0, 1.0, 'float'),
    }

    SENSORS = {
        'GYRO_LPF_HZ':       ('Gyro LPF (Hz)', 80, 10, 400, 'int'),
        'MC_DTERM_CUTOFF':   ('D-Term LPF (Hz)', 30, 5, 200, 'int'),
        'SENS_BOARD_X_OFF':  ('Board Rot X (deg)', 0, -180, 180, 'int'),
        'SENS_BOARD_Y_OFF':  ('Board Rot Y (deg)', 0, -180, 180, 'int'),
        'SENS_BOARD_Z_OFF':  ('Board Rot Z (deg)', 0, -180, 180, 'int'),
        'SENS_GPS_EN':       ('Enable GPS', 1, 0, 1, 'int'),
    }

    SYSTEM = {
        'MAV_SYS_ID':        ('System ID', 1, 1, 255, 'int'),
        'SYS_AUTOSTART':     ('Autostart ID', 0, 0, 1000, 'int'),
        'SYS_MC_EST_GROUP':  ('Estimator Group', 0, 0, 10, 'int'),
        'MC_ARM_THR':        ('Arm Throttle', 0.10, 0.0, 0.5, 'float'),
    }

    MOTOR = {
        'MOTOR_MIN':  ('Min PWM (µs)', 1000, 800, 1500, 'int'),
        'MOTOR_MAX':  ('Max PWM (µs)', 2000, 1500, 2200, 'int'),
        'MOTOR_IDLE': ('Idle PWM (µs)', 1000, 800, 1500, 'int'),
    }


# ======================================================================
# Main Tab Widget
# ======================================================================

class CompleteParamConfigTab(QWidget):

    params_sent = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.param_widgets: dict = {}       # px4_key → widget reference
        self.param_defaults: dict = {}      # px4_key → default value
        self._tab_names = []                # list of (tab_key, category_dict)

        self._mqtt = None
        self._fc_client_id = "INAV_FC_STM32_001"

        self._setup_ui()
        self._load_defaults()

    def set_mqtt(self, mqtt_manager, fc_client_id: str = "INAV_FC_STM32_001"):
        self._mqtt = mqtt_manager
        self._fc_client_id = fc_client_id

    # ==================================================================
    # UI Setup
    # ==================================================================

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        info_label = QLabel(
            "PX4 Parameter Configuration | Read → Modify → Send → Save to Flash"
        )
        info_label.setStyleSheet("""
            QLabel {
                color: #ffc107;
                font-size: 11px;
                padding: 6px;
                background-color: #2d2d2d;
                border-radius: 3px;
            }
        """)
        main_layout.addWidget(info_label)

        self.category_tabs = QTabWidget()
        self.category_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #444;
                background-color: #1e1e1e;
                border-radius: 4px;
            }
            QTabBar::tab {
                background-color: #3c3c3c;
                color: #ccc;
                padding: 8px 16px;
                margin-right: 2px;
                font-weight: bold;
                font-size: 11px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #00bfff;
                color: white;
            }
            QTabBar::tab:hover:!selected {
                background-color: #555;
            }
        """)
        main_layout.addWidget(self.category_tabs)

        # Create all tabs
        tab_defs = [
            ('rate_pid',  '🎯 Rate PID',  ParamCategory.RATE_PID),
            ('angle_pid', '📐 Angle PID', ParamCategory.ANGLE_PID),
            ('position',  '📍 Position',   ParamCategory.POSITION),
            ('battery',   '🔋 Battery',    ParamCategory.BATTERY),
            ('arming',    '🔒 Arming',     ParamCategory.ARMING),
            ('rc',        '📡 RC',         ParamCategory.RC),
            ('sensors',   '🔊 Sensors',    ParamCategory.SENSORS),
            ('system',    '⚙️ System',     ParamCategory.SYSTEM),
            ('motor',     '🔄 Motor',      ParamCategory.MOTOR),
        ]

        for key, title, cat_dict in tab_defs:
            self._create_param_tab(key, title, cat_dict)
            self._tab_names.append((key, cat_dict))

        # Action buttons
        action_layout = QHBoxLayout()

        read_btn = QPushButton("📥 Read All from FC")
        read_btn.setStyleSheet(self._btn_style('#28a745'))
        read_btn.clicked.connect(self._read_all_from_fc)
        action_layout.addWidget(read_btn)

        send_btn = QPushButton("📤 Send All to FC")
        send_btn.setStyleSheet(self._btn_style('#17a2b8'))
        send_btn.clicked.connect(self._send_all_to_fc)
        action_layout.addWidget(send_btn)

        save_btn = QPushButton("💾 Save to Flash")
        save_btn.setStyleSheet(self._btn_style('#e67e22'))
        save_btn.clicked.connect(self._save_to_flash)
        action_layout.addWidget(save_btn)

        reset_btn = QPushButton("↩️ Reset Tab")
        reset_btn.setStyleSheet(self._btn_style('#6c757d'))
        reset_btn.clicked.connect(self._reset_current_category)
        action_layout.addWidget(reset_btn)

        action_layout.addStretch()

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #888; font-size: 10px;")
        action_layout.addWidget(self.status_label)

        main_layout.addLayout(action_layout)

    def _create_param_tab(self, tab_key: str, title: str, params: dict):
        """Create a scrollable param editor tab from a param dict"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(10)
        grid.setContentsMargins(4, 4, 4, 4)

        row = 0
        for px4_key, (label, default, vmin, vmax, vtype) in params.items():
            name_label = QLabel(f"{px4_key}")
            name_label.setToolTip(label)
            name_label.setStyleSheet(
                f"color: {'#ff8c00' if 'RATE' in px4_key else '#17a2b8' if 'ROLL' in px4_key or 'PITCH' in px4_key else '#aaa'}; "
                f"font-family: Consolas; font-size: 11px; font-weight: bold;"
            )
            grid.addWidget(name_label, row, 0, Qt.AlignLeft)

            desc_label = QLabel(f"  ({label})")
            desc_label.setStyleSheet("color: #888; font-size: 10px;")
            grid.addWidget(desc_label, row, 1, Qt.AlignLeft)

            val_widget = self._make_widget(px4_key, default, vmin, vmax, vtype)
            grid.addWidget(val_widget, row, 2, Qt.AlignRight)

            self.param_widgets[px4_key] = val_widget
            self.param_defaults[px4_key] = default
            row += 1

        scroll.setWidget(container)
        layout.addWidget(scroll)
        self.category_tabs.addTab(tab, title)

    def _make_widget(self, key: str, default, vmin, vmax, vtype: str) -> QWidget:
        """Create appropriate value editor widget"""
        style = """
            QSpinBox, QDoubleSpinBox {
                background-color: #1e1e1e; border: 1px solid #555;
                padding: 4px 6px; border-radius: 3px; color: white;
                font-family: Consolas; font-size: 12px; min-width: 80px;
            }
            QSpinBox:focus, QDoubleSpinBox:focus { border: 2px solid #00bfff; }
            QSpinBox::up-button, QDoubleSpinBox::up-button { background-color: #3c3c3c; width: 18px; }
            QSpinBox::down-button, QDoubleSpinBox::down-button { background-color: #3c3c3c; width: 18px; }
            QComboBox {
                background-color: #1e1e1e; border: 1px solid #555;
                padding: 4px 6px; border-radius: 3px; color: white;
                font-family: Consolas; font-size: 12px; min-width: 80px;
            }
        """

        if vtype == 'float':
            w = QDoubleSpinBox()
            w.setDecimals(3)
            w.setRange(vmin, vmax)
            w.setSingleStep((vmax - vmin) / 100.0 if vmax > vmin else 0.1)
        elif vtype == 'int':
            w = QSpinBox()
            w.setRange(int(vmin), int(vmax))
        elif vtype == 'enum' and key == 'BAT_LOW_ACT':
            from PyQt5.QtWidgets import QComboBox
            w = QComboBox()
            w.addItems(["0: Warning", "1: Land", "2: RTL"])
            # 设置默认选中项
            idx = w.findText(str(int(default)) + ':')
            if idx >= 0:
                w.setCurrentIndex(idx)
            else:
                w.setCurrentIndex(int(default))
            return w
        else:
            w = QDoubleSpinBox()
            w.setDecimals(3)
            w.setRange(vmin, vmax)

        w.setValue(default)
        w.setStyleSheet(style)
        return w

    def _load_defaults(self):
        pass

    # ==================================================================
    # Data Collection
    # ==================================================================

    def collect_all_params(self) -> dict:
        """Collect all param values from all tabs"""
        params = {}
        for px4_key, widget in self.param_widgets.items():
            try:
                if isinstance(widget, QDoubleSpinBox):
                    params[px4_key] = widget.value()
                elif isinstance(widget, QSpinBox):
                    params[px4_key] = widget.value()
                elif hasattr(widget, 'currentText'):  # QComboBox
                    txt = widget.currentText()
                    val = float(txt.split(':')[0])
                    params[px4_key] = val
            except (ValueError, AttributeError):
                pass
        return params

    def set_all_params(self, params: dict):
        """Apply PX4-style param values to all UI widgets"""
        updated = 0
        for px4_key, widget in self.param_widgets.items():
            val = params.get(px4_key)
            if val is None:
                # Try lowercase variant for legacy compat
                val = params.get(px4_key.lower())
            if val is not None:
                try:
                    widget.blockSignals(True)
                    if isinstance(widget, QDoubleSpinBox):
                        widget.setValue(float(val))
                    elif isinstance(widget, QSpinBox):
                        widget.setValue(int(float(val)))
                    elif hasattr(widget, 'setCurrentText'):
                        widget.setCurrentText(str(val))
                    widget.blockSignals(False)
                    updated += 1
                except Exception:
                    widget.blockSignals(False)

        self.status_label.setText(f"Loaded {updated} parameters (PX4-style)")
        self.status_label.setStyleSheet("color: #28a745; font-size: 10px;")

    # ==================================================================
    # FC Communication
    # ==================================================================

    def _read_all_from_fc(self):
        """Read ALL parameters from FC via MQTT get_all_params"""
        if not self._mqtt or not self._mqtt.is_connected:
            QMessageBox.warning(self, "Error", "MQTT not connected!")
            return

        self.status_label.setText("Requesting all parameters from FC...")

        payload = {"cmd": "get_all_params", "protocol": "px4"}
        ok = self._mqtt.send_command_to_fc(self._fc_client_id, payload)

        if ok:
            response_received = [False]

            def on_response(topic, resp_payload):
                response_received[0] = True
                try:
                    resp_type = resp_payload.get('type', '')
                    if resp_type == 'all_params':
                        params = {k: v for k, v in resp_payload.items()
                                  if k not in ('type', 'cmd', 'protocol')}
                        self.set_all_params(params)
                        self.status_label.setText(f"All {len(params)} params received")
                        self.status_label.setStyleSheet("color: #28a745; font-size: 10px;")
                    elif resp_type == 'ack' and 'params' in resp_payload:
                        self.set_all_params(resp_payload['params'])
                        self.status_label.setText(f"Params received via ack")
                    else:
                        self.status_label.setText(f"Unexpected response: {resp_type}")
                except Exception as e:
                    self.status_label.setText(f"Parse error: {e}")
                finally:
                    self._mqtt.remove_resp_callback(on_response)

            self._mqtt.add_resp_callback(on_response)
            self.status_label.setText("Waiting for FC response (12s)...")

            QTimer.singleShot(12000, lambda: self._timeout_handler(response_received, on_response))
        else:
            self.status_label.setText("Failed to send get_all_params")

    def _send_all_to_fc(self):
        """Send ALL parameters to FC via MQTT"""
        params = self.collect_all_params()

        reply = QMessageBox.question(
            self, "Confirm Send",
            f"Send {len(params)} PX4 params to FC via MQTT?\n\n"
            "Parameters take effect IMMEDIATELY.\nMake sure aircraft is disarmed!",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        if not self._mqtt or not self._mqtt.is_connected:
            QMessageBox.warning(self, "Error", "MQTT not connected!")
            return

        payload = {"cmd": "set_all_params", "protocol": "px4"}
        payload.update(params)
        ok = self._mqtt.send_command_to_fc(self._fc_client_id, payload)

        if ok:
            self.status_label.setText(f"Sent {len(params)} params to FC")
            self.status_label.setStyleSheet("color: #17a2b8; font-size: 10px;")

            response_received = [False]
            def on_ack(topic, resp_payload):
                response_received[0] = True
                try:
                    if resp_payload.get('type') == 'ack' and resp_payload.get('cmd') == 'set_all_params':
                        updated = resp_payload.get('updated', False)
                        self.status_label.setText(
                            "FC confirmed: params applied" if updated else "FC ack (no update)")
                        self.status_label.setStyleSheet(
                            "color: #28a745; font-size: 10px;" if updated else "color: #ffc107; font-size: 10px;")
                except Exception as e:
                    self.status_label.setText(f"Ack error: {e}")
                finally:
                    self._mqtt.remove_resp_callback(on_ack)

            self._mqtt.add_resp_callback(on_ack)
            QTimer.singleShot(5000, lambda: self._timeout_handler(response_received, on_ack))

            QMessageBox.information(self, "Success",
                f"{len(params)} params sent!\n\nClick 'Save to Flash' to persist.")

            try:
                self.params_sent.emit(params)
            except Exception:
                pass
        else:
            self.status_label.setText("Failed to send params!")

    def _save_to_flash(self):
        """Persist params to Flash"""
        if not self._mqtt or not self._mqtt.is_connected:
            QMessageBox.warning(self, "Error", "MQTT not connected!")
            return

        if QMessageBox.question(self, "Confirm", "Save to Flash?") != QMessageBox.Yes:
            return

        self.status_label.setText("Saving to Flash...")
        ok = self._mqtt.send_command_to_fc(self._fc_client_id, {"cmd": "save"})
        if ok:
            response_received = [False]
            def on_save_ack(topic, resp_payload):
                response_received[0] = True
                try:
                    if resp_payload.get('type') == 'ack' and resp_payload.get('cmd') == 'save':
                        ok = resp_payload.get('ok', False)
                        if ok:
                            self.status_label.setText("Saved to Flash!")
                            self.status_label.setStyleSheet("color: #28a745; font-size: 10px;")
                        else:
                            self.status_label.setText("Flash save failed!")
                            self.status_label.setStyleSheet("color: #dc3545; font-size: 10px;")
                except Exception:
                    pass
                finally:
                    self._mqtt.remove_resp_callback(on_save_ack)

            self._mqtt.add_resp_callback(on_save_ack)
            QTimer.singleShot(8000, lambda: self._timeout_handler(response_received, on_save_ack))

    # ==================================================================
    # Reset / Helpers
    # ==================================================================

    def _reset_current_category(self):
        """Reset current tab params to defaults"""
        idx = self.category_tabs.currentIndex()
        if idx < 0 or idx >= len(self._tab_names):
            return
        key, cat_dict = self._tab_names[idx]

        count = 0
        for px4_key, (label, default, *_) in cat_dict.items():
            widget = self.param_widgets.get(px4_key)
            if widget:
                try:
                    widget.blockSignals(True)
                    if isinstance(widget, QDoubleSpinBox):
                        widget.setValue(float(default))
                    elif isinstance(widget, QSpinBox):
                        widget.setValue(int(default))
                    widget.blockSignals(False)
                    count += 1
                except Exception:
                    widget.blockSignals(False)

        self.status_label.setText(f"Reset {key} tab ({count} params) to defaults")

    def _timeout_handler(self, response_received, callback):
        if not response_received[0]:
            try:
                self._mqtt.remove_resp_callback(callback)
            except Exception:
                pass
            self.status_label.setText("Timeout: FC did not respond!")
            self.status_label.setStyleSheet("color: #dc3545; font-size: 10px;")

    # ==================================================================
    # Styles
    # ==================================================================

    @staticmethod
    def _btn_style(color: str) -> str:
        return f"""
            QPushButton {{
                background-color: {color}; color: white; padding: 10px 18px;
                border-radius: 5px; font-weight: bold; font-size: 12px;
            }}
            QPushButton:hover {{ opacity: 0.85; }}
        """