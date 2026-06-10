"""
MAVLink 2.0 Protocol Parser
Replaces the original MSP protocol parser with MAVLink v2.
Maintains the same FlightData dataclass and MSPProtocolParser interface
for backward compatibility with UI components.
"""

import struct
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum
import time

# Import MAVLink protocol engine
from .protocol_mavlink import (
    MAVLinkProtocolParser, MAVLinkMessageID, MAVParamType,
    PX4_PARAM_NAMES, PX4_TO_MSP_AXIS,
    MAVHeartbeat, MAVSysStatus, MAVAttitude, MAVGlobalPosition,
    MAVRawIMU, MAVRCChannels, MAVFlightMode, MAVCmd
)


# ======================================================================
# FlightData (unchanged - UI depends on these field names)
# ======================================================================

@dataclass
class FlightData:
    """飞行数据结构体"""
    # 姿态数据
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    heading: float = 0.0       # 罗盘航向 (deg)

    # IMU原始数据
    accel_x: float = 0.0
    accel_y: float = 0.0
    accel_z: float = 0.0
    gyro_x: float = 0.0
    gyro_y: float = 0.0
    gyro_z: float = 0.0
    mag_x: float = 0.0
    mag_y: float = 0.0
    mag_z: float = 0.0

    # 遥控器通道
    rc_roll: int = 1500
    rc_pitch: int = 1500
    rc_yaw: int = 1500
    rc_throttle: int = 1000
    rc_aux1: int = 1500
    rc_aux2: int = 1500
    rc_aux3: int = 1500
    rc_aux4: int = 1500

    # 电机输出
    motor_1: int = 0
    motor_2: int = 0
    motor_3: int = 0
    motor_4: int = 0

    # 系统状态
    armed: bool = False
    flight_mode: str = "MANUAL"
    cycle_time: int = 0
    cpu_load: int = 0
    i2c_errors: int = 0
    vbat: float = 0.0
    amperage: float = 0.0
    altitude: float = 0.0
    variometer: float = 0.0
    battery_remaining: int = -1  # 电池剩余百分比

    # GPS数据
    gps_fix: int = 0
    gps_num_sat: int = 0
    gps_lat: float = 0.0
    gps_lon: float = 0.0
    gps_alt: float = 0.0
    gps_speed: float = 0.0
    gps_heading: float = 0.0
    gps_eph: float = 0.0        # GPS水平精度 (m)
    gps_epv: float = 0.0        # GPS垂直精度 (m)

    # 家/起飞点
    home_lat: float = 0.0
    home_lon: float = 0.0
    home_alt: float = 0.0

    # PID参数
    pid_roll_p: float = 0.0
    pid_roll_i: float = 0.0
    pid_roll_d: float = 0.0
    pid_pitch_p: float = 0.0
    pid_pitch_i: float = 0.0
    pid_pitch_d: float = 0.0
    pid_yaw_p: float = 0.0
    pid_yaw_i: float = 0.0
    pid_yaw_d: float = 0.0

    timestamp: float = 0.0

    # 性能监控数据
    task_max_time: int = 0
    task_avg_time: int = 0
    arming_flags: int = 0
    sensor_status: int = 0


# ======================================================================
# PX4 Parameter Names (for param config UI)
# ======================================================================

class PX4ParamGroup:
    """PX4-style parameter naming constants"""

    # Rate PID (rate controllers)
    MC_ROLLRATE_P = "MC_ROLLRATE_P"
    MC_ROLLRATE_I = "MC_ROLLRATE_I"
    MC_ROLLRATE_D = "MC_ROLLRATE_D"
    MC_PITCHRATE_P = "MC_PITCHRATE_P"
    MC_PITCHRATE_I = "MC_PITCHRATE_I"
    MC_PITCHRATE_D = "MC_PITCHRATE_D"
    MC_YAWRATE_P = "MC_YAWRATE_P"
    MC_YAWRATE_I = "MC_YAWRATE_I"
    MC_YAWRATE_D = "MC_YAWRATE_D"

    # Angle PID (angle controllers)
    MC_ROLL_P = "MC_ROLL_P"
    MC_ROLL_I = "MC_ROLL_I"
    MC_ROLL_D = "MC_ROLL_D"
    MC_PITCH_P = "MC_PITCH_P"
    MC_PITCH_I = "MC_PITCH_I"
    MC_PITCH_D = "MC_PITCH_D"
    MC_YAW_P = "MC_YAW_P"
    MC_YAW_I = "MC_YAW_I"
    MC_YAW_D = "MC_YAW_D"

    # Battery
    BAT_A_VOLTAGE = "BAT_A_VOLTAGE"
    BAT_A_CAPACITY = "BAT_A_CAPACITY"

    # RC
    RC_RATE = "RC_RATE"


# ======================================================================
# MSP Protocol (compatibility constants)
# ======================================================================

class MSPCommand(Enum):
    """MSP命令枚举 (backward compatibility - maps to MAVLink)"""
    MSP_IDENT = 100
    MSP_STATUS = 101
    MSP_STATUS_EX = 102
    MSP_RAW_IMU = 103
    MSP_MOTOR = 104
    MSP_RC = 105
    MSP_RAW_GPS = 106
    MSP_COMP_GPS = 107
    MSP_ATTITUDE = 108
    MSP_ALTITUDE = 109
    MSP_ANALOG = 110
    MSP_RC_TUNING = 111
    MSP_PID = 112
    MSP_BOX = 113
    MSP_MISC = 114
    MSP_MOTOR_PINS = 115
    MSP_BOXNAMES = 116
    MSP_PIDNAMES = 117
    MSP_BOXIDS = 119
    MSP_SERVO_CONFURATIONS = 120
    MSP_DEBUGMSG = 253
    MSP_DEBUG = 254
    MSP_ACC_CALIBRATION = 205
    MSP_MAG_CALIBRATION = 206
    MSP_SET_MOTOR = 214
    INAV_STATUS = 150
    INAV_GPS = 151
    INAV_COMPASS = 152
    INAV_BATTERY = 153
    INAV_NAV_CONFIG = 154
    MSP2_INAV_STATUS = 0x1F00
    MSP2_TASK_INFO = 0x1F01
    MSP_SET_RAW_RC = 200


# ======================================================================
# MAVLink-based Protocol Parser (replaces MSPProtocolParser)
# ======================================================================

class MSPProtocolParser:
    """
    MAVLink 2.0 Protocol Parser
    (Class name kept for backward compatibility with UI code.)
    Internally uses MAVLink v2 protocol instead of MSP.
    """

    # MSP constants kept for API compatibility
    MSP_HEADER = b'\xFD'  # MAVLink v2 start byte (was $M)
    MSP_REQUEST = b'\x00'
    MSP_RESPONSE = b'\x01'

    def __init__(self):
        self.buffer = bytearray()
        self.flight_data = FlightData()

        # Internal MAVLink engine
        self._mavlink = MAVLinkProtocolParser(own_sysid=255, own_compid=240)
        self._mavlink.flight_data = self.flight_data

        # Parameter cache (PX4-style)
        self.params: Dict[str, float] = {}
        self.params.update(PX4_PARAM_NAMES)  # Default values

    def parse_data(self, raw_data: bytes) -> List[Tuple[Any, bytes]]:
        """
        Parse received data using MAVLink v2 protocol.
        Returns list of (message_id, payload) pairs.
        Compatible with original MSP parse_data interface.
        """
        results = []
        self.buffer.extend(raw_data)

        # Delegate to MAVLink parser
        mavlink_results = self._mavlink.parse_data(raw_data)

        for msgid, payload in mavlink_results:
            # Map MAVLink msgid to something compatible
            results.append((msgid, payload))

            # Update our synchronized FlightData
            mav_fd = self._mavlink.flight_data
            self.flight_data = mav_fd

            # Also update GPS and RC from MAVLink state
            mav_att = self._mavlink.attitude
            mav_hb = self._mavlink.heartbeat
            mav_ss = self._mavlink.sys_status

        # Also clear processed bytes from our local buffer
        # (MAVLink parser already handles this internally)
        if self._mavlink.buffer:
            self.buffer = bytearray(self._mavlink.buffer)
        else:
            self.buffer.clear()

        return results

    # ==================================================================
    # MSP-compatible Request Builders → MAVLink
    # ==================================================================

    def build_request(self, command: Any, data: bytes = b'') -> bytes:
        """
        Build a MAVLink request (compatible with old MSP build_request interface)

        For backward compatibility, maps MSP command IDs to MAVLink.
        """
        cmd_map = {
            MSPCommand.MSP_RAW_IMU: (MAVLinkMessageID.RAW_IMU.value, b''),
            MSPCommand.MSP_ATTITUDE: (MAVLinkMessageID.ATTITUDE.value, b''),
            MSPCommand.MSP_RC: (MAVLinkMessageID.RC_CHANNELS.value, b''),
            MSPCommand.MSP_STATUS: (MAVLinkMessageID.HEARTBEAT.value, b''),
            MSPCommand.MSP_STATUS_EX: (MAVLinkMessageID.SYS_STATUS.value, b''),
            MSPCommand.MSP_RAW_GPS: (MAVLinkMessageID.GLOBAL_POSITION_INT.value, b''),
            MSPCommand.MSP_ANALOG: (MAVLinkMessageID.SYS_STATUS.value, b''),
            MSPCommand.MSP_MOTOR: (MAVLinkMessageID.SERVO_OUTPUT_RAW.value, b''),
        }

        if isinstance(command, MSPCommand) and command in cmd_map:
            msgid, payload = cmd_map[command]
            return self._mavlink._build_frame(msgid, payload)
        else:
            # Default: treat as raw MAVLink msgid
            msgid = command.value if isinstance(command, Enum) else int(command)
            return self._mavlink._build_frame(msgid, data or b'')

    def request_ident(self) -> bytes:
        """Request autopilot version info (MAVLink AUTOPILOT_VERSION)"""
        return self._mavlink._build_frame(148, b'')

    def request_status(self) -> bytes:
        """Request system status → MAVLink SYS_STATUS"""
        return self._mavlink._build_frame(1, b'')

    def request_status_ex(self) -> bytes:
        """Request extended status → MAVLink SYS_STATUS"""
        return self._mavlink._build_frame(1, b'')

    def request_inav_status(self) -> bytes:
        """Request system status (previously INAV status)"""
        return self._mavlink._build_frame(1, b'')

    def request_task_info(self) -> bytes:
        """Request task info → not directly available in MAVLink, use SYS_STATUS"""
        return self._mavlink._build_frame(1, b'')

    def request_imu(self) -> bytes:
        """Request IMU data → MAVLink RAW_IMU (#27)"""
        return self._mavlink._build_frame(27, b'')

    def request_attitude(self) -> bytes:
        """Request attitude → MAVLink ATTITUDE (#30)"""
        return self._mavlink._build_frame(30, b'')

    def request_rc(self) -> bytes:
        """Request RC channels → MAVLink RC_CHANNELS (#65)"""
        return self._mavlink._build_frame(65, b'')

    def request_motor(self) -> bytes:
        """Request motor output → MAVLink SERVO_OUTPUT_RAW (#36)"""
        return self._mavlink._build_frame(36, b'')

    def request_raw_gps(self) -> bytes:
        """Request GPS position → MAVLink GLOBAL_POSITION_INT (#33)"""
        return self._mavlink._build_frame(33, b'')

    def request_comp_gps(self) -> bytes:
        """Request GPS → same as raw GPS in MAVLink"""
        return self._mavlink._build_frame(33, b'')

    def request_mag_calibration(self) -> bytes:
        """Send magnetometer calibration command"""
        return self._mavlink.command_calibrate_mag()

    def request_acc_calibration(self) -> bytes:
        """Send accelerometer calibration command"""
        return self._mavlink.command_calibrate_accel()

    def set_motor_values(self, motor_values: List[int]) -> bytes:
        """Set motor values (test mode) → MAVLink COMMAND_LONG motor test"""
        params = [motor_values[i] if i < len(motor_values) else 0 for i in range(7)]
        return self._mavlink.build_command_long(0, params)

    def request_pid(self) -> bytes:
        """Request PID params → MAVLink PARAM_REQUEST_LIST (#21)"""
        return self._mavlink.request_param_list()

    def set_pid(self, pid_values: List[int]) -> bytes:
        """Set PID params (legacy) → not applicable in PX4-style;
           Use set_param() with PX4 param names instead."""
        return b''

    def set_param(self, param_id: str, value: float) -> bytes:
        """Set a single PX4-style parameter via MAVLink PARAM_SET"""
        return self._mavlink.set_param(param_id, value)

    def request_param(self, param_id: str) -> bytes:
        """Request a single parameter via MAVLink PARAM_REQUEST_READ"""
        return self._mavlink.request_param_read(param_id)

    def request_all_params(self) -> bytes:
        """Request all parameters via MAVLink PARAM_REQUEST_LIST"""
        return self._mavlink.request_param_list()

    def command_arm(self) -> bytes:
        """Build MAVLink arm command"""
        return self._mavlink.command_arm()

    def command_disarm(self) -> bytes:
        """Build MAVLink disarm command"""
        return self._mavlink.command_disarm()

    def command_reboot(self) -> bytes:
        """Build MAVLink reboot command"""
        return self._mavlink.command_reboot()

    def get_flight_data(self) -> FlightData:
        """Get latest flight data"""
        return self.flight_data


# ======================================================================
# PX4 ↔ MSP Parameter Name Mapping
# ======================================================================

PX4_TO_MSP_PARAM_MAP = {
    # Rate PID: PX4 → MSP (axis, component)
    'MC_ROLLRATE_P':    ('roll', 'kp', 'rate'),
    'MC_ROLLRATE_I':    ('roll', 'ki', 'rate'),
    'MC_ROLLRATE_D':    ('roll', 'kd', 'rate'),
    'MC_PITCHRATE_P':   ('pitch', 'kp', 'rate'),
    'MC_PITCHRATE_I':   ('pitch', 'ki', 'rate'),
    'MC_PITCHRATE_D':   ('pitch', 'kd', 'rate'),
    'MC_YAWRATE_P':     ('yaw', 'kp', 'rate'),
    'MC_YAWRATE_I':     ('yaw', 'ki', 'rate'),
    'MC_YAWRATE_D':     ('yaw', 'kd', 'rate'),
    
    # Angle PID: PX4 → MSP
    'MC_ROLL_P':        ('roll', 'kp', 'angle'),
    'MC_ROLL_I':        ('roll', 'ki', 'angle'),
    'MC_ROLL_D':        ('roll', 'kd', 'angle'),
    'MC_PITCH_P':       ('pitch', 'kp', 'angle'),
    'MC_PITCH_I':       ('pitch', 'ki', 'angle'),
    'MC_PITCH_D':       ('pitch', 'kd', 'angle'),
    'MC_YAW_P':         ('yaw', 'kp', 'angle'),
    'MC_YAW_I':         ('yaw', 'ki', 'angle'),
    'MC_YAW_D':         ('yaw', 'kd', 'angle'),
}

# Reverse mapping: MSP flat key → PX4 key
MSP_TO_PX4_PARAM_MAP = {}
for px4_key, (axis, comp, ptype) in PX4_TO_MSP_PARAM_MAP.items():
    msp_key = f"pid_{ptype}_{axis}_{comp}"
    MSP_TO_PX4_PARAM_MAP[msp_key] = px4_key
    # Also add legacy format
    legacy_key = f"{ptype}_{axis}_{comp}"
    MSP_TO_PX4_PARAM_MAP[legacy_key] = px4_key


def px4_to_msp(params: dict) -> dict:
    """
    Convert PX4-style parameter dict to MSP-style flat dict.
    
    Example:
        {"MC_ROLLRATE_P": 4.5} → {"rate_roll_kp": 4.5}
    
    Args:
        params: Dict with PX4 parameter names as keys
    
    Returns:
        Dict with MSP-style keys
    """
    msp_params = {}
    
    for px4_key, value in params.items():
        if px4_key in PX4_TO_MSP_PARAM_MAP:
            axis, comp, ptype = PX4_TO_MSP_PARAM_MAP[px4_key]
            msp_key = f"{ptype}_{axis}_{comp}"
            msp_params[msp_key] = value
        else:
            # Pass through unknown keys (e.g., GYRO_LPF_HZ, MOTOR_MIN)
            msp_params[px4_key.lower()] = value
    
    return msp_params


def msp_to_px4(params: dict) -> dict:
    """
    Convert MSP-style flat parameter dict to PX4-style.
    
    Example:
        {"rate_roll_kp": 4.5} → {"MC_ROLLRATE_P": 4.5}
    
    Args:
        params: Dict with MSP-style keys
    
    Returns:
        Dict with PX4 parameter names as keys
    """
    px4_params = {}
    
    for msp_key, value in params.items():
        # Try direct mapping
        if msp_key in MSP_TO_PX4_PARAM_MAP:
            px4_key = MSP_TO_PX4_PARAM_MAP[msp_key]
            px4_params[px4_key] = value
        else:
            # Try upper-case convention (gyro_lpf_hz → GYRO_LPF_HZ)
            upper_key = msp_key.upper()
            if upper_key in PX4_TO_MSP_PARAM_MAP or upper_key in globals().get('PX4_PARAM_NAMES', {}):
                px4_params[upper_key] = value
            else:
                # Keep as-is for unknown keys
                px4_params[msp_key] = value
    
    return px4_params


# ======================================================================
# MAVLink Bridge Layer
# ======================================================================

class MAVLinkBridge:
    """
    Bridge between MAVLink PARAM protocol and MQTT JSON commands.
    
    This allows the CompleteParamConfigTab to use MAVLink-style
    parameter operations while the actual transport (MQTT) uses JSON.
    
    Usage:
        bridge = MAVLinkBridge(mqtt_manager, fc_client_id)
        bridge.request_all_params(callback=on_params_received)
        bridge.send_all_params({"MC_ROLLRATE_P": 4.5, ...})
        bridge.send_single_param("MC_ROLLRATE_P", 4.5)
    """

    def __init__(self, mqtt_manager=None, fc_client_id: str = "INAV_FC_STM32_001"):
        self.mqtt = mqtt_manager
        self.fc_client_id = fc_client_id
        self._param_cache: Dict[str, float] = {}
        self._callbacks: list = []

    def set_mqtt(self, mqtt_manager, fc_client_id: str = "INAV_FC_STM32_001"):
        """Set MQTT manager after initialization"""
        self.mqtt = mqtt_manager
        self.fc_client_id = fc_client_id

    def request_all_params(self, callback=None):
        """
        Request all parameters from FC via MQTT.
        Translates to MQTT get_all_params command.
        Responses are translated from MSP to PX4 naming.
        """
        if not self.mqtt or not self.mqtt.is_connected:
            return False

        payload = {"cmd": "get_all_params", "protocol": "px4"}
        
        if callback:
            self._callbacks.append(callback)
        
        return self.mqtt.send_command_to_fc(self.fc_client_id, payload)

    def send_all_params(self, params: dict) -> bool:
        """
        Send all parameters to FC via MQTT using PX4-style names.
        
        Args:
            params: Dict of {PX4_param_name: value}
        
        Returns:
            True if sent successfully
        """
        if not self.mqtt or not self.mqtt.is_connected:
            return False

        payload = {"cmd": "set_all_params", "protocol": "px4"}
        payload.update(params)
        return self.mqtt.send_command_to_fc(self.fc_client_id, payload)

    def send_single_param(self, param_id: str, value: float) -> bool:
        """
        Send a single PX4 parameter via MAVLink-style PARAM_SET.
        Over MQTT, this translates to a JSON command.
        
        Args:
            param_id: PX4 parameter name (e.g., "MC_ROLLRATE_P")
            value: Parameter value
        
        Returns:
            True if sent successfully
        """
        if not self.mqtt or not self.mqtt.is_connected:
            return False

        payload = {
            "cmd": "set_param",
            "protocol": "px4",
            "param_id": param_id,
            "param_value": value,
            "param_type": 9  # MAV_PARAM_TYPE_REAL32
        }
        return self.mqtt.send_command_to_fc(self.fc_client_id, payload)

    def request_single_param(self, param_id: str) -> bool:
        """
        Request a single PX4 parameter via MAVLink-style PARAM_REQUEST_READ.
        
        Args:
            param_id: PX4 parameter name
        
        Returns:
            True if sent successfully
        """
        if not self.mqtt or not self.mqtt.is_connected:
            return False

        payload = {
            "cmd": "get_param",
            "protocol": "px4",
            "param_id": param_id
        }
        return self.mqtt.send_command_to_fc(self.fc_client_id, payload)

    def save_to_flash(self) -> bool:
        """Persist all parameters to Flash via MQTT save command"""
        if not self.mqtt or not self.mqtt.is_connected:
            return False
        return self.mqtt.send_command_to_fc(self.fc_client_id, {"cmd": "save"})

    def dispatch_response(self, topic: str, payload: dict):
        """
        Dispatch a response from FC to all registered callbacks.
        Translates MSP-style parameter names to PX4 if needed.
        
        Called by the MQTT message handler.
        """
        resp_type = payload.get('type', '')
        
        if resp_type == 'all_params':
            # Extract params (skip metadata keys)
            raw_params = {k: v for k, v in payload.items() 
                         if k not in ('type', 'cmd', 'protocol')}
            # Try to convert to PX4 naming
            px4_params = msp_to_px4(raw_params)
            
            for cb in self._callbacks:
                try:
                    cb('all_params', px4_params)
                except Exception:
                    pass
        
        elif resp_type == 'ack':
            for cb in self._callbacks:
                try:
                    cb('ack', payload)
                except Exception:
                    pass


# ======================================================================
# Legacy Parser (MSP only, for backward compat with MQTT/4G)
# ======================================================================

class LegazyMSPParser:
    """
    Legacy MSP-only parser for MQTT bridge compatibility.
    Only used when FC firmware still sends MSP over MQTT.
    """

    MSP_HEADER = b'$M'
    MSP_REQUEST = '<'
    MSP_RESPONSE = '>'

    def __init__(self):
        self.buffer = bytearray()
        self.flight_data = FlightData()

    def parse_data(self, raw_data: bytes) -> List[Tuple[MSPCommand, bytes]]:
        results = []
        self.buffer.extend(raw_data)

        while len(self.buffer) >= 6:
            header_idx = self.buffer.find(self.MSP_HEADER)
            if header_idx == -1:
                self.buffer.clear()
                break
            if header_idx > 0:
                del self.buffer[:header_idx]
                header_idx = 0
            if header_idx + 5 >= len(self.buffer):
                break

            frame_start = header_idx
            direction = chr(self.buffer[frame_start + 2])
            length = self.buffer[frame_start + 3]
            command = self.buffer[frame_start + 4]
            total_length = 6 + length

            if frame_start + total_length > len(self.buffer):
                break

            data = bytes(self.buffer[frame_start + 5:frame_start + 5 + length])
            checksum = self.buffer[frame_start + 5 + length]

            calc_checksum = length ^ command
            for byte in data:
                calc_checksum ^= byte

            if checksum == calc_checksum and direction == self.MSP_RESPONSE:
                try:
                    cmd_enum = MSPCommand(command)
                    results.append((cmd_enum, data))
                    del self.buffer[:frame_start + total_length]
                except ValueError:
                    del self.buffer[:frame_start + 1]
            else:
                del self.buffer[:frame_start + 1]

        return results

    def get_flight_data(self) -> FlightData:
        return self.flight_data