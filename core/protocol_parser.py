"""
协议解析器 — 统一接口 + 运行时切换
===========================================

本模块定义了上层 UI / 业务代码使用的统一协议接口，同时
提供两种实现：
  1. MAVLink 2.0（默认） —— PX4 / ArduPilot / INAV 新固件
  2. MSP（MultiWii Serial Protocol） —— 老版 INAV / Betaflight / Cleanflight

上层代码只需要调用 create_protocol_parser("mavlink" | "msp")
即可获得协议实例，实例统一提供下列接口：

    parse_data(raw_bytes)       — 解析收到的字节流
    get_flight_data()           — 返回 FlightData 对象
    flight_data                 — 当前最新的飞行数据（可直接访问）

    # 通用请求（构建发送帧）：
    request_ident()             — 固件识别
    request_status()            — 基础状态
    request_status_ex()         — 扩展状态（MSP兼容）
    request_inav_status()       — INAV状态（MSP兼容）
    request_imu()               — IMU原始数据
    request_attitude()          — 姿态
    request_rc()                — RC通道
    request_motor()             — 电机输出
    request_raw_gps()           — GPS
    request_comp_gps()          — GPS（MSP兼容）
    request_analog()            — 电压/电流
    request_pid()               — PID参数
    request_task_info()         — 任务统计（MSP兼容，MAVLink返回空帧）

    # 校准 / 参数 / 控制：
    request_acc_calibration()   — 加速度计校准
    request_mag_calibration()   — 磁力计校准
    set_pid(pid_values)         — 设置PID
    set_param(param_id, value)  — 设置参数（PX4风格）
    request_param(param_id)     — 读取参数
    request_all_params()        — 读取全部参数
    set_motor(motor_values)     — 电机测试
    command_arm()               — 解锁
    command_disarm()            — 加锁
    command_reboot()            — 重启

两个实现均保持 FlightData 字段完全一致，因此上层业务代码、
data_manager、校准向导、地图等完全不需改动。
"""

import struct
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum


# ======================================================================
# FlightData — 统一飞行数据容器（两个协议共用）
# ======================================================================

@dataclass
class FlightData:
    """飞行数据结构体（协议无关）"""
    # 姿态数据
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    heading: float = 0.0

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
    battery_remaining: int = -1

    # GPS数据
    gps_fix: int = 0
    gps_num_sat: int = 0
    gps_lat: float = 0.0
    gps_lon: float = 0.0
    gps_alt: float = 0.0
    gps_speed: float = 0.0
    gps_heading: float = 0.0
    gps_eph: float = 0.0
    gps_epv: float = 0.0

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

    # 性能监控
    task_max_time: int = 0
    task_avg_time: int = 0
    arming_flags: int = 0
    sensor_status: int = 0


# ======================================================================
# 协议类型枚举
# ======================================================================

class ProtocolType(Enum):
    MAVLINK = "mavlink"
    MSP = "msp"


# ======================================================================
# 工厂函数
# ======================================================================

def create_protocol_parser(kind: str = "mavlink"):
    """
    创建指定类型的协议解析器。

    Args:
        kind: "mavlink" 或 "msp"（大小写不敏感）

    Returns:
        实现了统一接口的协议解析器对象
    """
    k = str(kind).lower().strip()
    if k == "msp":
        from .protocol_msp import MSPProtocolParser as _MSPParser
        return _MSPParser()
    # 默认 MAVLink
    from .protocol_mavlink import MAVLinkProtocolParser as _MAVLinkParser
    return _MAVLinkParser()


def list_protocols() -> List[str]:
    """返回当前支持的所有协议名称"""
    return ["mavlink", "msp"]
