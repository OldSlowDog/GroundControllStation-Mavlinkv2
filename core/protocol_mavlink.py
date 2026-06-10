"""
MAVLink v2 Protocol Parser & Builder
Replaces the original MSP protocol with MAVLink 2.0 standard.
Supports PX4-style parameter protocol for remote tuning.
"""

import struct
import time
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from enum import Enum


# ======================================================================
# MAVLink CRC16-CCITT (X.25) Implementation
# ======================================================================

_CRC_EXTRA_TABLE = {}  # msg_id -> crc_extra (populated at bottom of file)

def _crc16_ccitt(crc: int, data: bytes) -> int:
    """CRC16-CCITT (X.25) - the polynomial used by MAVLink"""
    for byte in data:
        crc = (crc >> 8) | (crc << 8)
        crc &= 0xFFFF
        crc ^= byte
        crc ^= (crc & 0xFF) >> 4
        crc ^= (crc << 12) & 0xFFFF
        crc ^= ((crc & 0xFF) << 5) & 0xFFFF
    return crc & 0xFFFF

def _crc16_mavlink(data: bytes, crc_extra: int) -> bytes:
    """Calculate MAVLink v2 16-bit CRC with extra byte"""
    crc = 0xFFFF
    crc = _crc16_ccitt(crc, data)
    crc = _crc16_ccitt(crc, bytes([crc_extra]))
    return struct.pack('<H', crc)


# ======================================================================
# MAVLink v2 Frame
# ======================================================================

MAVLINK_V2_START = 0xFD
MAVLINK_HEADER_LEN = 10  # start(1)+len(1)+incompat(1)+compat(1)+seq(1)+sysid(1)+compid(1)+msgid(3)
MAVLINK_CHECKSUM_LEN = 2
MAVLINK_SIGNATURE_LEN = 13
MAVLINK_IFLAG_SIGNED = 0x01


@dataclass
class MAVLinkFrame:
    """MAVLink v2 frame"""
    len: int                # Payload length
    incompat_flags: int     # Incompatibility flags
    compat_flags: int       # Compatibility flags
    seq: int                # Sequence number
    sysid: int              # System ID
    compid: int             # Component ID
    msgid: int              # Message ID (24-bit)
    payload: bytes          # Raw payload
    crc: bytes              # Checksum (2 bytes)
    signature: bytes = b''  # Optional signature (13 bytes)

    def is_signed(self) -> bool:
        return (self.incompat_flags & MAVLINK_IFLAG_SIGNED) != 0

    def __repr__(self) -> str:
        return f"MAVLink#{self.msgid} sys={self.sysid} comp={self.compid} len={self.len}"


# ======================================================================
# MAVLink Message IDs
# ======================================================================

class MAVLinkMessageID(Enum):
    HEARTBEAT              = 0
    SYS_STATUS             = 1
    SYSTEM_TIME            = 2
    SCALED_PRESSURE        = 29
    PARAM_REQUEST_READ     = 20
    PARAM_REQUEST_LIST     = 21
    PARAM_VALUE            = 22
    PARAM_SET              = 23
    GPS_RAW_INT            = 24
    RAW_IMU                = 27
    ATTITUDE               = 30
    GLOBAL_POSITION_INT    = 33
    SERVO_OUTPUT_RAW       = 36
    RC_CHANNELS            = 65
    VFR_HUD                = 74
    COMMAND_LONG           = 76
    COMMAND_ACK            = 77
    BATTERY_STATUS         = 147
    AUTOPILOT_VERSION      = 148
    HOME_POSITION          = 242
    STATUS_TEXT            = 253


# ======================================================================
# MAVLink Component/Autopilot IDs
# ======================================================================

class MAVType(Enum):
    QUADROTOR = 2
    HEXAROTOR = 3
    OCTOROTOR = 4
    TRICOPTER = 5
    GROUND_CONTROL_STATION = 6
    GENERIC = 0

class MAVModeFlag(Enum):
    SAFETY_ARMED = 0x80     # bit 7: system is armed
    MANUAL_INPUT_ENABLED = 0x40
    HIL_ENABLED = 0x20
    STABILIZE_ENABLED = 0x10
    GUIDED_ENABLED = 0x08
    AUTO_ENABLED = 0x04
    TEST_ENABLED = 0x02
    CUSTOM_MODE_ENABLED = 0x01

class MAVState(Enum):
    UNINIT = 0
    BOOT = 1
    CALIBRATING = 2
    STANDBY = 3
    ACTIVE = 4
    CRITICAL = 5
    EMERGENCY = 6
    POWEROFF = 7
    FLIGHT_TERMINATION = 8

class MAVParamType(Enum):
    UINT8 = 1
    INT8 = 2
    UINT16 = 3
    INT16 = 4
    UINT32 = 5
    INT32 = 6
    UINT64 = 7
    INT64 = 8
    REAL32 = 9
    REAL64 = 10

class MAVCmd(Enum):
    DO_ARM = 400
    DO_DISARM = 21
    DO_REBOOT = 246
    PREFLIGHT_CALIBRATION = 241
    COMPONENT_ARM_DISARM = 400

class MAVFlightMode(Enum):
    MANUAL = 0
    ALT_HOLD = 1
    POS_HOLD = 2
    AUTO = 3
    RTL = 4
    STABILIZE = 5
    ACRO = 6
    SPORT = 7


# ======================================================================
# PX4-style Parameter Naming
# ======================================================================

PX4_PARAM_NAMES = {
    # ===========================
    # Rate controllers (P, I, D, FF)
    # ===========================
    "MC_ROLLRATE_P":      4.50,   # Roll rate P gain
    "MC_ROLLRATE_I":      0.03,   # Roll rate I gain
    "MC_ROLLRATE_D":      0.003,  # Roll rate D gain
    "MC_ROLLRATE_FF":     0.00,   # Roll rate feedforward
    "MC_PITCHRATE_P":     4.50,   # Pitch rate P gain
    "MC_PITCHRATE_I":     0.03,   # Pitch rate I gain
    "MC_PITCHRATE_D":     0.003,  # Pitch rate D gain
    "MC_PITCHRATE_FF":    0.00,   # Pitch rate feedforward
    "MC_YAWRATE_P":       3.00,   # Yaw rate P gain
    "MC_YAWRATE_I":       0.02,   # Yaw rate I gain
    "MC_YAWRATE_D":       0.000,  # Yaw rate D gain
    "MC_YAWRATE_FF":      0.00,   # Yaw rate feedforward
    "MC_RR_INT_LIM":      0.25,   # Roll rate integrator limit
    "MC_PR_INT_LIM":      0.25,   # Pitch rate integrator limit
    "MC_YR_INT_LIM":      0.25,   # Yaw rate integrator limit
    "MC_ROLLRATE_MAX":    720.0,  # Max roll rate (deg/s)
    "MC_PITCHRATE_MAX":   720.0,  # Max pitch rate (deg/s)
    "MC_YAWRATE_MAX":     360.0,  # Max yaw rate (deg/s)
    "MC_DTERM_CUTOFF":    30.0,   # D-term LPF cutoff (Hz)

    # ===========================
    # Angle controllers (P, I, D)
    # ===========================
    "MC_ROLL_P":      5.50,   # Roll angle P gain
    "MC_ROLL_I":      0.01,   # Roll angle I gain
    "MC_ROLL_D":      0.001,  # Roll angle D gain
    "MC_PITCH_P":     5.50,   # Pitch angle P gain
    "MC_PITCH_I":     0.01,   # Pitch angle I gain
    "MC_PITCH_D":     0.001,  # Pitch angle D gain
    "MC_YAW_P":       6.00,   # Yaw angle P gain
    "MC_YAW_I":       0.02,   # Yaw angle I gain
    "MC_YAW_D":       0.000,  # Yaw angle D gain
    "MC_YAW_WEIGHT":  0.20,   # Yaw weight in attitude control
    "MC_RATE_WEIGHT": 0.50,   # Rate weight (1=rate only, 0=angle only)

    # ===========================
    # Position / Velocity Control
    # ===========================
    "MPC_XY_P":          1.50,   # XY position P gain
    "MPC_XY_VEL_P":      0.09,   # XY velocity P gain
    "MPC_XY_VEL_I":      0.02,   # XY velocity I gain
    "MPC_XY_VEL_D":      0.001,  # XY velocity D gain
    "MPC_Z_P":           1.00,   # Z position P gain
    "MPC_Z_VEL_P":       4.00,   # Z velocity P gain
    "MPC_Z_VEL_I":       2.00,   # Z velocity I gain
    "MPC_Z_VEL_D":       0.00,   # Z velocity D gain
    "MPC_ACC_HOR":       5.00,   # Horizontal acceleration limit (m/s/s)
    "MPC_ACC_HOR_MAX":   8.00,   # Max horizontal acceleration
    "MPC_ACC_UP_MAX":    8.00,   # Max vertical up acceleration
    "MPC_ACC_DOWN_MAX":  4.00,   # Max vertical down acceleration
    "MPC_JERK_MAX":      8.00,   # Max jerk (m/s/s/s)
    "MPC_THR_HOVER":     0.50,   # Hover throttle (0~1)
    "MPC_THR_MAX":       1.00,   # Max throttle (0~1)
    "MPC_THR_MIN":       0.12,   # Min throttle (0~1)
    "MPC_MAN_TILT_MAX":  45.00,  # Manual tilt max angle (deg)
    "MPC_MAN_YAW_MAX":   150.0,  # Manual yaw max rate (deg/s)
    "MPC_MANTHR_MIN":    0.08,   # Manual minimum thrust
    "MPC_MANTHR_MAX":    1.00,   # Manual maximum thrust
    "MPC_LAND_SPEED":    0.70,   # Land descend speed (m/s)
    "MPC_CRUISE_SPEED":  5.00,   # Default cruise speed (m/s)
    "MPC_TILTMAX_LND":   12.00,  # Max tilt during landing (deg)
    "MPC_VEL_MANUAL":    8.00,   # Manual position control velocity limit
    "MPC_HOLD_MAX_XY":   0.80,   # Max horizontal position error for hold

    # ===========================
    # Battery
    # ===========================
    "BAT_A_VOLTAGE":     12.6,   # Battery full voltage
    "BAT_A_CAPACITY":    1500,   # Battery capacity (mAh)
    "BAT_CRIT_V":        10.5,   # Critical battery voltage
    "BAT_EMERGEN_V":     10.0,   # Emergency battery voltage
    "BAT_N_CELLS":       3,      # Number of cells
    "BAT_LOW_ACT":       0,      # Low battery action (0=warning, 1=land, 2=RTL)

    # ===========================
    # Arming / Safety
    # ===========================
    "COM_ARM_ARSPD_EN":  0,      # Enable airspeed arming check
    "COM_ARM_CHK_EN":    1,      # Enable arming checks (bitmask)
    "COM_ARM_GPS_XY_RAD":50.0,   # GPS XY acceptance radius (m)
    "COM_ARM_MAG_EN":    1,      # Enable magnetometer arming check
    "COM_ARM_EKF_CHK":   1,      # Enable EKF arming check
    "COM_ARM_BAT_CAP_EN":0,      # Enable battery capacity arming check
    "COM_DISARM_TM":     10,     # Auto disarm timeout (s)
    "COM_DISARM_LAND_TM":2,      # Post-land disarm delay (s)
    "IMB_MAN_THR_MAX":   0.90,   # Manual throttle limit (0~1)

    # ===========================
    # RC / Receiver
    # ===========================
    "RC_MAP_ROLL":       1,      # RC channel mapping for roll
    "RC_MAP_PITCH":      2,      # RC channel mapping for pitch
    "RC_MAP_YAW":        4,      # RC channel mapping for yaw
    "RC_MAP_THROTTLE":   3,      # RC channel mapping for throttle
    "RC_MAP_ARM_SW":     5,      # RC channel mapping for arm switch
    "RC_MAP_FLTMODE":    6,      # RC channel mapping for flight mode
    "RC_CHAN_CNT":       8,      # Number of RC channels
    "RC_RATE":           1.00,   # RC sensitivity/rate
    "RC_EXPO":           0.00,   # RC expo (0~1)

    # ===========================
    # Sensors / Filters
    # ===========================
    "GYRO_LPF_HZ":       80,     # Gyroscope low-pass filter (Hz)
    "SENS_BOARD_X_OFF":  0,      # Board X rotation offset (deg)
    "SENS_BOARD_Y_OFF":  0,      # Board Y rotation offset (deg)
    "SENS_BOARD_Z_OFF":  0,      # Board Z rotation offset (deg)
    "SENS_GPS_EN":       1,      # Enable GPS

    # ===========================
    # System
    # ===========================
    "MC_ARM_THR":        0.10,   # Arming throttle threshold
    "MAV_SYS_ID":        1,      # MAVLink system ID
    "SYS_AUTOSTART":     0,      # Autostart ID (0=manual config)
    "SYS_MC_EST_GROUP":  0,      # Multi-copter estimator group

    # ===========================
    # Misc / Legacy
    # ===========================
    "STICK_DEADZONE":    15,     # Stick deadzone (pwm)
    "AUTO_DISARM_TIMEOUT": 10,   # Auto disarm timeout (s)
    "MOTOR_MIN":         1000,   # Motor minimum PWM
    "MOTOR_MAX":         2000,   # Motor maximum PWM
    "MOTOR_IDLE":        1000,   # Motor idle PWM (armed)
}

# Param -> MSP PID axis mapping (for backward compatibility with FC firmware)
PX4_TO_MSP_AXIS = {
    "MC_ROLLRATE_P":    ("roll", "rate", "kp"),
    "MC_ROLLRATE_I":    ("roll", "rate", "ki"),
    "MC_ROLLRATE_D":    ("roll", "rate", "kd"),
    "MC_PITCHRATE_P":   ("pitch", "rate", "kp"),
    "MC_PITCHRATE_I":   ("pitch", "rate", "ki"),
    "MC_PITCHRATE_D":   ("pitch", "rate", "kd"),
    "MC_YAWRATE_P":     ("yaw", "rate", "kp"),
    "MC_YAWRATE_I":     ("yaw", "rate", "ki"),
    "MC_YAWRATE_D":     ("yaw", "rate", "kd"),
    "MC_ROLL_P":        ("roll", "angle", "kp"),
    "MC_PITCH_P":       ("pitch", "angle", "kp"),
}


# ======================================================================
# MAVLink Message Parse Results
# ======================================================================

@dataclass
class MAVHeartbeat:
    type: int = 2           # MAV_TYPE (2=quadrotor)
    autopilot: int = 8      # MAV_AUTOPILOT_PX4=8 (or GENERIC=0)
    base_mode: int = 0      # MAV_MODE_FLAG
    custom_mode: int = 0    # Custom mode (flight mode)
    system_status: int = 3  # MAV_STATE

@dataclass
class MAVSysStatus:
    onboard_control_sensors_present: int = 0
    onboard_control_sensors_enabled: int = 0
    onboard_control_sensors_health: int = 0
    load: int = 0            # CPU load (d%)
    voltage_battery: int = 0 # mV
    current_battery: int = 0 # cA
    battery_remaining: int = -1

@dataclass
class MAVAttitude:
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    rollspeed: float = 0.0
    pitchspeed: float = 0.0
    yawspeed: float = 0.0

@dataclass
class MAVGlobalPosition:
    lat: int = 0        # degE7
    lon: int = 0        # degE7
    alt: int = 0        # mm (MSL)
    relative_alt: int = 0  # mm
    vx: int = 0         # cm/s
    vy: int = 0         # cm/s
    vz: int = 0         # cm/s
    hdg: int = 0        # cdeg (heading * 100)

@dataclass
class MAVRawIMU:
    xacc: int = 0
    yacc: int = 0
    zacc: int = 0
    xgyro: int = 0
    ygyro: int = 0
    zgyro: int = 0
    xmag: int = 0
    ymag: int = 0
    zmag: int = 0

@dataclass  
class MAVRCChannels:
    chan_count: int = 0
    chan_raw: List[int] = field(default_factory=lambda: [0] * 18)
    rssi: int = 0

@dataclass
class MAVParamInfo:
    param_id: str = ""
    param_value: float = 0.0
    param_type: int = 9     # REAL32 default
    param_count: int = 0
    param_index: int = 0

@dataclass
class MAVBatteryStatus:
    """BATTERY_STATUS (#147)"""
    id: int = 0
    battery_function: int = 0
    type: int = 0
    temperature: int = -1       # cdegC, -1 = unknown
    voltages: List[int] = field(default_factory=lambda: [0]*10)  # mV per cell
    current_battery: int = 0    # cA (=-1 if no current)
    current_consumed: int = 0   # mAh
    energy_consumed: int = 0    # hJ
    battery_remaining: int = -1 # %
    time_remaining: int = 0     # s
    charge_state: int = 0

@dataclass
class MAVScaledPressure:
    """SCALED_PRESSURE (#29)"""
    time_boot_ms: int = 0
    press_abs: float = 0.0     # hPa
    press_diff: float = 0.0    # hPa
    temperature: int = 0       # cdegC

@dataclass
class MAVHomePosition:
    """HOME_POSITION (#242)"""
    lat: int = 0              # degE7
    lon: int = 0              # degE7
    alt: int = 0              # mm
    x: float = 0.0            # local position (m)
    y: float = 0.0
    z: float = 0.0
    approach_x: float = 0.0
    approach_y: float = 0.0
    approach_z: float = 0.0
    valid: bool = False

@dataclass
class MAVAutopilotVersion:
    """AUTOPILOT_VERSION (#148)"""
    capabilities: int = 0
    flight_sw_version: int = 0
    middleware_sw_version: int = 0
    os_sw_version: int = 0
    board_version: int = 0
    flight_custom_version: bytes = b''
    vendor_id: int = 0
    product_id: int = 0
    uid: int = 0


# ======================================================================
# Main MAVLink Protocol Parser
# ======================================================================

class MAVLinkProtocolParser:
    """
    MAVLink v2 protocol parser.
    Parses raw bytes from serial/TCP, extracts MAVLink frames,
    deserializes payloads, and updates FlightData.
    """

    def __init__(self, own_sysid: int = 255, own_compid: int = 240):
        self.buffer = bytearray()
        self.own_sysid = own_sysid       # GCS system ID (255 = ground)
        self.own_compid = own_compid     # GCS component ID (240 = GCS)
        self.target_sysid = 1            # Target FC system ID (default 1)
        self.target_compid = 1           # Target FC component ID (default 1)
        self.seq = 0                     # Outgoing sequence number

        # Parsed messages
        self.heartbeat = MAVHeartbeat()
        self.sys_status = MAVSysStatus()
        self.attitude = MAVAttitude()
        self.global_position = MAVGlobalPosition()
        self.raw_imu = MAVRawIMU()
        self.rc_channels = MAVRCChannels()
        self.battery = MAVBatteryStatus()
        self.scaled_pressure = MAVScaledPressure()
        self.home_position = MAVHomePosition()
        self.autopilot_version = MAVAutopilotVersion()

        # Parameter storage (PX4-style)
        self.params: Dict[str, float] = {}
        self.param_mapping: Dict[str, str] = {}  # param_id -> msp_key

        # Raw frame list (for debugging)
        self.last_frames: List[MAVLinkFrame] = []

        # Initialize flight data structure
        self.flight_data = self._create_flight_data()

    def set_target(self, sysid: int, compid: int):
        """Set FC target system/component IDs"""
        self.target_sysid = sysid
        self.target_compid = compid

    def _create_flight_data(self):
        """Create a FlightData-compatible object (reuse existing definition)"""
        from .protocol_parser import FlightData
        return FlightData()

    def _update_flight_data_from_mavlink(self):
        """Synchronize the FlightData structure from MAVLink state"""
        fd = self.flight_data

        # ATTITUDE → roll/pitch/yaw/heading
        att = self.attitude
        fd.roll = att.roll
        fd.pitch = att.pitch
        fd.yaw = att.yaw
        fd.heading = att.yaw  # heading = yaw (deg)

        # RAW_IMU → accel/gyro/mag
        imu = self.raw_imu
        fd.accel_x = imu.xacc / 1000.0
        fd.accel_y = imu.yacc / 1000.0
        fd.accel_z = imu.zacc / 1000.0
        fd.gyro_x = imu.xgyro / 100.0
        fd.gyro_y = imu.ygyro / 100.0
        fd.gyro_z = imu.zgyro / 100.0
        fd.mag_x = imu.xmag / 1000.0
        fd.mag_y = imu.ymag / 1000.0
        fd.mag_z = imu.zmag / 1000.0

        # GLOBAL_POSITION_INT → GPS
        gpos = self.global_position
        fd.gps_lat = gpos.lat / 10000000.0
        fd.gps_lon = gpos.lon / 10000000.0
        fd.gps_alt = gpos.alt / 1000.0
        fd.gps_heading = gpos.hdg / 100.0

        # SYS_STATUS → vbat, cpu_load, amperage
        ss = self.sys_status
        fd.vbat = ss.voltage_battery / 1000.0
        fd.cpu_load = ss.load  # d% directly
        if ss.current_battery > 0:
            fd.amperage = ss.current_battery / 100.0  # cA → A

        # BATTERY_STATUS → battery_remaining
        bat = self.battery
        if bat.battery_remaining >= 0:
            fd.battery_remaining = bat.battery_remaining
        if bat.current_battery > 0:
            fd.amperage = bat.current_battery / 100.0  # cA → A

        # SCALED_PRESSURE → altitude (barometric)
        sp = self.scaled_pressure
        if sp.press_abs > 0:
            # Convert pressure to altitude (barometric formula)
            fd.altitude = (1 - (sp.press_abs / 1013.25) ** 0.1903) * 44330.0

        # HOME_POSITION → home_lat/lon/alt
        hp = self.home_position
        if hp.valid:
            fd.home_lat = hp.lat / 10000000.0
            fd.home_lon = hp.lon / 10000000.0
            fd.home_alt = hp.alt / 1000.0

        # HEARTBEAT → armed, flight_mode
        hb = self.heartbeat
        fd.armed = bool(hb.base_mode & MAVModeFlag.SAFETY_ARMED.value)
        # Map custom_mode to flight mode string
        mode_map = {
            0: "MANUAL", 1: "ALT_HOLD", 2: "POS_HOLD",
            3: "AUTO", 4: "RTL", 5: "STABILIZE", 6: "ACRO", 7: "SPORT"
        }
        fd.flight_mode = mode_map.get(hb.custom_mode, f"MODE_{hb.custom_mode}")

        fd.timestamp = time.time()

    def parse_data(self, raw_data: bytes) -> List[Tuple[int, bytes]]:
        """
        Parse raw bytes from serial/TCP and extract MAVLink frames.
        
        Returns:
            List of (msgid, payload_bytes) parsed from the buffer
        """
        results = []
        self.buffer.extend(raw_data)

        while len(self.buffer) >= MAVLINK_HEADER_LEN:
            # Find MAVLink v2 start byte 0xFD
            start_idx = -1
            for i, b in enumerate(self.buffer):
                if b == MAVLINK_V2_START:
                    start_idx = i
                    break
                # Skip non-0xFD bytes (junk)
                if i > 100:
                    break

            if start_idx < 0:
                self.buffer.clear()
                break

            if start_idx > 0:
                del self.buffer[:start_idx]
                start_idx = 0

            if len(self.buffer) < MAVLINK_HEADER_LEN:
                break

            # Parse header
            payload_len = self.buffer[1]
            incompat_flags = self.buffer[2]
            compat_flags = self.buffer[3]
            seq = self.buffer[4]
            sysid = self.buffer[5]
            compid = self.buffer[6]
            msgid = self.buffer[7] | (self.buffer[8] << 8) | (self.buffer[9] << 16)

            # Skip signed frames (incompatible with simple implementation)
            if incompat_flags & MAVLINK_IFLAG_SIGNED:
                total_frame_len = MAVLINK_HEADER_LEN + payload_len + \
                                  MAVLINK_CHECKSUM_LEN + MAVLINK_SIGNATURE_LEN
            else:
                total_frame_len = MAVLINK_HEADER_LEN + payload_len + MAVLINK_CHECKSUM_LEN

            if len(self.buffer) < total_frame_len:
                break

            # Extract payload and CRC
            payload_start = MAVLINK_HEADER_LEN
            payload = bytes(self.buffer[payload_start:payload_start + payload_len])
            crc = bytes(self.buffer[payload_start + payload_len:payload_start + payload_len + 2])

            # Get CRC extra byte for this message
            crc_extra = _CRC_EXTRA_TABLE.get(msgid, 0)
            header_bytes = bytes(self.buffer[1:MAVLINK_HEADER_LEN])
            expected_crc = _crc16_mavlink(header_bytes + payload, crc_extra)

            # Verify CRC (ignore if mismatch - continue searching)
            if crc != expected_crc:
                del self.buffer[:1]
                continue

            # Build frame object
            frame = MAVLinkFrame(
                len=payload_len,
                incompat_flags=incompat_flags,
                compat_flags=compat_flags,
                seq=seq,
                sysid=sysid,
                compid=compid,
                msgid=msgid,
                payload=payload,
                crc=crc,
                signature=bytes(self.buffer[payload_start + payload_len + 2:]) if incompat_flags & MAVLINK_IFLAG_SIGNED else b''
            )
            self.last_frames.append(frame)
            if len(self.last_frames) > 100:
                self.last_frames.pop(0)

            # Process the message and store in results
            results.append((msgid, payload))

            try:
                self._process_message(msgid, payload)
            except Exception:
                pass

            # Remove consumed frame from buffer
            del self.buffer[:total_frame_len]

        return results

    def _process_message(self, msgid: int, payload: bytes):
        """Process a MAVLink message and update internal state"""
        plen = len(payload)

        if msgid == 0 and plen >= 7:  # HEARTBEAT
            vals = struct.unpack('<BBBB', payload[:4])
            self.heartbeat.type = vals[0]
            self.heartbeat.autopilot = vals[1]
            self.heartbeat.base_mode = vals[2]
            self.heartbeat.system_status = vals[3]
            if plen >= 8:
                self.heartbeat.custom_mode = struct.unpack('<I', payload[4:8])[0]

        elif msgid == 1 and plen >= 20:  # SYS_STATUS
            vals = struct.unpack('<IIIIHHhHHHH', payload[:31])
            self.sys_status.onboard_control_sensors_present = vals[0]
            self.sys_status.onboard_control_sensors_enabled = vals[1]
            self.sys_status.onboard_control_sensors_health = vals[2]
            self.sys_status.load = vals[3]          # d% (divide by 10)
            self.sys_status.voltage_battery = vals[4]   # mV
            self.sys_status.current_battery = vals[5]   # cA
            self.sys_status.battery_remaining = vals[6] if len(vals) > 6 else -1

        elif msgid == 24 and plen >= 26:  # GPS_RAW_INT (#24)
            vals = struct.unpack('<IihHBBB', payload[:16])
            self.global_position.lat = vals[0]
            self.global_position.lon = vals[1]
            self.global_position.alt = vals[2]
            gps_eph = vals[3]       # cm
            gps_epv = vals[4]       # cm
            gps_vel = vals[5]       # cm/s → m/s
            gps_cog = vals[6]       # cdeg → deg
            self.flight_data.gps_num_sat = payload[15]
            self.flight_data.gps_fix = payload[14]
            self.flight_data.gps_eph = gps_eph / 100.0 if gps_eph < 65535 else 0.0
            self.flight_data.gps_epv = gps_epv / 100.0 if gps_epv < 255 else 0.0

        elif msgid == 27 and plen >= 24:  # RAW_IMU
            vals = struct.unpack('<hhhhhhhhhI', payload[:26])
            self.raw_imu.xacc = vals[0]   # mG
            self.raw_imu.yacc = vals[1]
            self.raw_imu.zacc = vals[2]
            self.raw_imu.xgyro = vals[3]  # mrad/s
            self.raw_imu.ygyro = vals[4]
            self.raw_imu.zgyro = vals[5]
            self.raw_imu.xmag = vals[6]   # mgauss
            self.raw_imu.ymag = vals[7]
            self.raw_imu.zmag = vals[8]

        elif msgid == 30 and plen >= 24:  # ATTITUDE
            vals = struct.unpack('<ffffff', payload[:24])
            self.attitude.roll = vals[0] * 57.29578   # rad → deg
            self.attitude.pitch = vals[1] * 57.29578
            self.attitude.yaw = vals[2] * 57.29578
            self.attitude.rollspeed = vals[3] * 57.29578
            self.attitude.pitchspeed = vals[4] * 57.29578
            self.attitude.yawspeed = vals[5] * 57.29578

        elif msgid == 29 and plen >= 14:  # SCALED_PRESSURE (#29)
            vals = struct.unpack('<Iffh', payload[:14])
            self.scaled_pressure.time_boot_ms = vals[0]
            self.scaled_pressure.press_abs = vals[1]      # hPa
            self.scaled_pressure.press_diff = vals[2]     # hPa
            self.scaled_pressure.temperature = vals[3]    # cdegC

        elif msgid == 33 and plen >= 28:  # GLOBAL_POSITION_INT
            vals = struct.unpack('<IiiihhHh', payload[:28])
            self.global_position.lat = vals[0] - 0x80000000 if vals[0] & 0x80000000 else vals[0]
            self.global_position.lon = vals[1] - 0x80000000 if vals[1] & 0x80000000 else vals[1]
            self.global_position.alt = vals[2]
            self.global_position.relative_alt = vals[3]
            self.global_position.vx = vals[4]
            self.global_position.vy = vals[5]
            self.global_position.vz = vals[6]
            self.global_position.hdg = vals[7]

        elif msgid == 36 and plen >= 2:  # SERVO_OUTPUT_RAW (#36)
            # port(1) + servo_count(1) + servo_raw[]
            if plen >= 6:
                servo_count = payload[1]
                for i in range(min(servo_count, 4)):
                    offset = 2 + i * 2
                    if offset + 1 < plen:
                        servo_val = struct.unpack('<H', payload[offset:offset+2])[0]
                        if i == 0: self.flight_data.motor_1 = servo_val
                        elif i == 1: self.flight_data.motor_2 = servo_val
                        elif i == 2: self.flight_data.motor_3 = servo_val
                        elif i == 3: self.flight_data.motor_4 = servo_val

        elif msgid == 65 and plen >= 3:  # RC_CHANNELS
            chan_count = payload[0]
            rssi = payload[1]
            self.rc_channels.chan_count = chan_count
            self.rc_channels.rssi = rssi
            raw_count = min(chan_count, 18)
            for i in range(raw_count):
                offset = 2 + i * 2
                if offset + 1 < plen:
                    self.rc_channels.chan_raw[i] = struct.unpack('<H', payload[offset:offset+2])[0]

            # Sync RC to FlightData
            rcmap = [('rc_roll', 0), ('rc_pitch', 1), ('rc_throttle', 2), ('rc_yaw', 3),
                     ('rc_aux1', 4), ('rc_aux2', 5), ('rc_aux3', 6), ('rc_aux4', 7)]
            for attr, idx in rcmap:
                if idx < raw_count:
                    setattr(self.flight_data, attr, self.rc_channels.chan_raw[idx])

        elif msgid == 147 and plen >= 36:  # BATTERY_STATUS (#147)
            vals = struct.unpack('<BBh10HhHHIB', payload[:36])
            self.battery.id = vals[0]
            self.battery.battery_function = vals[1]
            self.battery.type = vals[2]
            self.battery.temperature = vals[3]      # cdegC
            # voltages[10] starts at offset 6 (1B*2 + 1B*1 + 2B*1 + 10*2B = 24)
            for j in range(10):
                self.battery.voltages[j] = vals[4 + j]
            self.battery.current_battery = vals[14]    # cA
            self.battery.current_consumed = vals[15]
            self.battery.energy_consumed = vals[16]
            self.battery.battery_remaining = vals[17]
            self.battery.time_remaining = vals[18]

        elif msgid == 148 and plen >= 27:  # AUTOPILOT_VERSION (#148)
            vals = struct.unpack('<Q3I3I3I', payload[:28]) if plen >= 28 else (0, 0, 0, 0, 0, 0, 0)
            self.autopilot_version.capabilities = vals[0]
            self.autopilot_version.flight_sw_version = vals[1]
            self.autopilot_version.middleware_sw_version = vals[2]
            self.autopilot_version.os_sw_version = vals[3]
            self.autopilot_version.board_version = vals[4]
            if plen >= 33:
                self.autopilot_version.vendor_id = struct.unpack('<H', payload[28:30])[0]
                self.autopilot_version.product_id = struct.unpack('<H', payload[30:32])[0]

        elif msgid == 242 and plen >= 40:  # HOME_POSITION (#242)
            vals = struct.unpack('<Iii', payload[:12])
            self.home_position.lat = vals[0]
            self.home_position.lon = vals[1]
            self.home_position.alt = vals[2]
            self.home_position.valid = True

        elif msgid == 22 and plen >= 25:  # PARAM_VALUE
            # param_id(16) + value(4) + type(1) + count(2) + index(2)
            param_id_bytes = payload[:16]
            param_id = param_id_bytes.split(b'\x00')[0].decode('ascii', errors='ignore')
            param_value = struct.unpack('<f', payload[16:20])[0]
            param_type = payload[20]
            param_count = struct.unpack('<H', payload[21:23])[0]
            param_index = struct.unpack('<H', payload[23:25])[0]

            self.params[param_id] = param_value

            # Also map to FlightData PID fields if applicable
            msp_key = PX4_TO_MSP_AXIS.get(param_id)
            if msp_key:
                axis, ptype, component = msp_key
                if axis == "roll" and ptype == "rate":
                    if component == "kp": self.flight_data.pid_roll_p = param_value
                    elif component == "ki": self.flight_data.pid_roll_i = param_value
                    elif component == "kd": self.flight_data.pid_roll_d = param_value
                elif axis == "pitch" and ptype == "rate":
                    if component == "kp": self.flight_data.pid_pitch_p = param_value
                    elif component == "ki": self.flight_data.pid_pitch_i = param_value
                    elif component == "kd": self.flight_data.pid_pitch_d = param_value
                elif axis == "yaw" and ptype == "rate":
                    if component == "kp": self.flight_data.pid_yaw_p = param_value
                    elif component == "ki": self.flight_data.pid_yaw_i = param_value
                    elif component == "kd": self.flight_data.pid_yaw_d = param_value
                elif axis == "roll" and ptype == "angle":
                    self.flight_data.pid_roll_p = param_value
                elif axis == "pitch" and ptype == "angle":
                    self.flight_data.pid_pitch_p = param_value

        elif msgid == 253 and plen >= 3:  # STATUS_TEXT
            severity = payload[0]
            text = payload[1:].split(b'\x00')[0].decode('ascii', errors='ignore')
            level = ["Emergency", "Alert", "Critical", "Error",
                     "Warning", "Notice", "Info", "Debug"]
            level_name = level[severity] if severity < len(level) else f"Severity{severity}"
            if severity <= 3:
                import sys
                print(f"[MAVLink {level_name}] {text}", file=sys.stderr)

        # Update FlightData after each message
        self._update_flight_data_from_mavlink()

    # ==================================================================
    # Frame Building
    # ==================================================================

    def _build_frame(self, msgid: int, payload: bytes) -> bytes:
        """Build a MAVLink v2 frame"""
        plen = len(payload)
        crc_extra = _CRC_EXTRA_TABLE.get(msgid, 0)

        # Header
        header = bytes([
            MAVLINK_V2_START,       # Start
            plen & 0xFF,             # Payload length
            0,                       # Incompat flags
            0,                       # Compat flags
            self.seq & 0xFF,         # Sequence
            self.own_sysid,          # System ID
            self.own_compid,         # Component ID
            msgid & 0xFF,            # Message ID LSB
            (msgid >> 8) & 0xFF,     # Message ID byte 2
            (msgid >> 16) & 0xFF,    # Message ID byte 3
        ])

        # CRC = CRC16(payload_header + payload, crc_extra)
        crc_input = header[1:] + payload  # Skip start byte for CRC
        crc = _crc16_mavlink(crc_input, crc_extra)

        self.seq = (self.seq + 1) & 0xFF

        return header + payload + crc

    # ==================================================================
    # Request Builders
    # ==================================================================

    def request_heartbeat(self) -> bytes:
        """HEARTBEAT is sent automatically by FC; this builds a manual request"""
        return self._build_frame(0, struct.pack('<BBBB', 0, 0, 0, 0))

    def request_sys_status(self) -> bytes:
        """SYS_STATUS request (actually FC sends periodically)"""
        return self._build_frame(1, b'')

    def request_raw_imu(self) -> bytes:
        """Request RAW_IMU"""
        return self._build_frame(27, b'')

    def request_attitude(self) -> bytes:
        """Request ATTITUDE"""
        return self._build_frame(30, b'')

    def request_global_position(self) -> bytes:
        """Request GLOBAL_POSITION_INT"""
        return self._build_frame(33, b'')

    def request_rc_channels(self) -> bytes:
        """Request RC_CHANNELS"""
        return self._build_frame(65, b'')

    def request_param_list(self) -> bytes:
        """
        Request all parameters (PARAM_REQUEST_LIST #21)
        FC will respond with one PARAM_VALUE per parameter.
        """
        payload = struct.pack('<BB', self.target_sysid, self.target_compid)
        return self._build_frame(21, payload)

    def request_param_read(self, param_id: str) -> bytes:
        """
        Request a single parameter by ID (PARAM_REQUEST_READ #20)
        """
        param_bytes = param_id.encode('ascii')[:16].ljust(16, b'\x00')
        payload = struct.pack('<BB', self.target_sysid, self.target_compid)
        payload += param_bytes  # param_id
        return self._build_frame(20, payload)

    def set_param(self, param_id: str, value: float) -> bytes:
        """
        Set a parameter (PARAM_SET #23).
        Uses REAL32 type by default.
        """
        param_bytes = param_id.encode('ascii')[:16].ljust(16, b'\x00')
        payload = struct.pack('<BB', self.target_sysid, self.target_compid)
        payload += param_bytes
        payload += struct.pack('<f', value)
        payload += bytes([9])  # MAV_PARAM_TYPE_REAL32
        return self._build_frame(23, payload)

    def build_command_long(self, command: int, params: List[float] = None) -> bytes:
        """Build COMMAND_LONG (#76) message"""
        if params is None:
            params = [0.0] * 7
        while len(params) < 7:
            params.append(0.0)
        payload = struct.pack('<BB', self.target_sysid, self.target_compid)
        payload += struct.pack('<H', command)
        payload += struct.pack('<B', 1)  # confirmation
        payload += struct.pack('<fffffff', *params[:7])
        return self._build_frame(76, payload)

    def command_arm(self) -> bytes:
        """Build arm command (COMPONENT_ARM_DISARM with param1=1)"""
        return self.build_command_long(400, [1.0, 0, 0, 0, 0, 0, 0])

    def command_disarm(self) -> bytes:
        """Build disarm command (COMPONENT_ARM_DISARM with param1=0)"""
        return self.build_command_long(400, [0.0, 0, 0, 0, 0, 0, 0])

    def command_reboot(self) -> bytes:
        """Build reboot command"""
        return self.build_command_long(246, [1.0, 0, 0, 0, 0, 0, 0])

    def command_calibrate_accel(self) -> bytes:
        """Build accelerometer calibration command"""
        return self.build_command_long(241, [0, 0, 0, 0, 1, 0, 0])

    def command_calibrate_mag(self) -> bytes:
        """Build magnetometer calibration command"""
        return self.build_command_long(241, [1, 0, 0, 0, 0, 0, 0])

    def get_flight_data(self):
        """Get the latest FlightData object (compatible with MSP parser)"""
        return self.flight_data


# ======================================================================
# CRC Extra Table
# ======================================================================
# CRC extra byte for each MAVLink message (X.25 polynomial)
# Only the messages we use are defined here.

_CRC_EXTRA_TABLE = {
    0:   50,    # HEARTBEAT
    1:   50,    # SYS_STATUS
    2:   23,    # SYSTEM_TIME
    20:  142,   # PARAM_REQUEST_READ
    21:  147,   # PARAM_REQUEST_LIST
    22:  220,   # PARAM_VALUE
    23:  95,    # PARAM_SET
    24:  103,   # GPS_RAW_INT
    27:  115,   # RAW_IMU
    29:  143,   # SCALED_PRESSURE
    30:  21,    # ATTITUDE
    33:  168,   # GLOBAL_POSITION_INT
    36:  128,   # SERVO_OUTPUT_RAW
    65:  155,   # RC_CHANNELS
    74:  20,    # VFR_HUD
    76:  212,   # COMMAND_LONG
    77:  98,    # COMMAND_ACK
    147: 119,   # BATTERY_STATUS
    148: 26,    # AUTOPILOT_VERSION
    242: 130,   # HOME_POSITION
    253: 28,    # STATUS_TEXT
}