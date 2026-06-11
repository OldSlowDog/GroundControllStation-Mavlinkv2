"""
MSP (MultiWii Serial Protocol) 协议解析与构建模块
独立的 MSP 协议实现，提供与 protocol_mavlink.py 相同的接口风格，
使上层业务代码可以无缝切换协议。

MSP 帧格式:
  $M <方向> <长度> <命令> <数据> <CRC>
  方向: '<' 请求, '>' 响应, '!' 错误
  CRC  = 长度 ^ 命令 ^ (所有数据字节 XOR)
"""

import struct
import time
from typing import Dict, List, Tuple, Optional, Any
from enum import Enum


# ======================================================================
# MSP 命令枚举
# ======================================================================

class MSPCmd(Enum):
    """MSP 命令 ID 枚举"""
    MSP_IDENT = 100
    MSP_STATUS = 101
    MSP_RAW_IMU = 102
    MSP_SERVO = 103
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
    MSP_BOXNAMES = 116
    MSP_PIDNAMES = 117
    MSP_ACC_CALIBRATION = 205
    MSP_MAG_CALIBRATION = 206
    MSP_SET_MOTOR = 214
    MSP_SET_PID = 202
    MSP_SET_RAW_RC = 200
    MSP_SET_RC_TUNING = 204
    MSP_EEPROM_WRITE = 250
    MSP_DEBUG = 254


# ======================================================================
# MSP 协议核心解析器
# ======================================================================

class MSPProtocolParser:
    """
    MSP 协议核心解析器。
    解析来自串口/TCP 的原始字节流，提取 MSP 帧，
    反序列化数据并更新统一的 FlightData 对象。

    接口风格与 MAVLinkProtocolParser 保持一致，便于上层无缝切换。
    """

    # MSP 帧常量
    MSP_HEADER = b'$M'           # 帧头
    MSP_DIR_REQUEST = ord('<')   # 请求方向
    MSP_DIR_RESPONSE = ord('>')  # 响应方向
    MSP_DIR_ERROR = ord('!')     # 错误方向

    def __init__(self):
        # 接收缓冲区（存储未解析完成的字节）
        self.buffer = bytearray()

        # 从 protocol_parser 导入 FlightData，保持字段对齐
        try:
            from .protocol_parser import FlightData
        except Exception:
            # 兜底：直接定义一个最小兼容 FlightData（不会与主项目冲突）
            from dataclasses import dataclass as _dc

            @_dc
            class FlightData:
                roll: float = 0.0
                pitch: float = 0.0
                yaw: float = 0.0
                heading: float = 0.0
                accel_x: float = 0.0
                accel_y: float = 0.0
                accel_z: float = 0.0
                gyro_x: float = 0.0
                gyro_y: float = 0.0
                gyro_z: float = 0.0
                mag_x: float = 0.0
                mag_y: float = 0.0
                mag_z: float = 0.0
                rc_roll: int = 1500
                rc_pitch: int = 1500
                rc_yaw: int = 1500
                rc_throttle: int = 1000
                rc_aux1: int = 1500
                rc_aux2: int = 1500
                rc_aux3: int = 1500
                rc_aux4: int = 1500
                motor_1: int = 0
                motor_2: int = 0
                motor_3: int = 0
                motor_4: int = 0
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
                gps_fix: int = 0
                gps_num_sat: int = 0
                gps_lat: float = 0.0
                gps_lon: float = 0.0
                gps_alt: float = 0.0
                gps_speed: float = 0.0
                gps_heading: float = 0.0
                gps_eph: float = 0.0
                gps_epv: float = 0.0
                home_lat: float = 0.0
                home_lon: float = 0.0
                home_alt: float = 0.0
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
                task_max_time: int = 0
                task_avg_time: int = 0
                arming_flags: int = 0
                sensor_status: int = 0

        # 统一飞行数据对象
        self.flight_data = FlightData()

        # 参数缓存（MSP 使用扁平结构，key -> value）
        self.params: Dict[str, float] = {}

        # 最近设置的电机值（用于 set_motor 回显）
        self._motor_values: List[int] = [0, 0, 0, 0]

        # 最近成功解析的帧列表（用于调试）
        self.last_frames: List[Tuple[MSPCmd, bytes]] = []

    # ==================================================================
    # 帧解析：从字节流中提取 MSP 帧
    # ==================================================================

    def parse_data(self, raw_data: bytes) -> List[Tuple[MSPCmd, bytes]]:
        """
        解析原始字节流，提取完整的 MSP 响应帧。

        Args:
            raw_data: 从串口/TCP 读取的原始字节

        Returns:
            List[(MSPCmd, payload_bytes)] 本次解析出的有效帧
        """
        results: List[Tuple[MSPCmd, bytes]] = []
        if raw_data:
            self.buffer.extend(raw_data)

        # 循环查找帧头 $M，直到缓冲区中没有完整帧
        while len(self.buffer) >= 6:
            # 1. 在缓冲中查找 $M 起始标记
            header_idx = self.buffer.find(self.MSP_HEADER)
            if header_idx == -1:
                # 没有帧头，清空缓冲（避免内存无限增长）
                self.buffer.clear()
                break
            if header_idx > 0:
                # 丢弃帧头前的垃圾字节
                del self.buffer[:header_idx]
                header_idx = 0

            # 2. 确保至少有 $M + 方向 + 长度 + 命令 = 5 字节
            if len(self.buffer) < 5:
                break

            direction = self.buffer[2]
            length = self.buffer[3]
            command = self.buffer[4]
            total_length = 5 + length + 1  # $M(2)+dir(1)+len(1)+cmd(1)+data(length)+crc(1)

            # 3. 检查是否收到完整一帧
            if len(self.buffer) < total_length:
                break

            # 4. 提取数据与 CRC
            data_start = 5
            data_end = data_start + length
            payload = bytes(self.buffer[data_start:data_end])
            crc_byte = self.buffer[data_end]

            # 5. 校验 CRC = 长度 ^ 命令 ^ (data[0] ^ data[1] ^ ...)
            calc_crc = length ^ command
            for b in payload:
                calc_crc ^= b
            calc_crc &= 0xFF

            # 6. CRC 校验失败 → 跳过 1 字节继续搜索，避免死循环
            if calc_crc != crc_byte:
                del self.buffer[:1]
                continue

            # 7. 方向必须为响应（'/'）或错误（'!'），请求帧忽略
            if direction != self.MSP_DIR_RESPONSE and direction != self.MSP_DIR_ERROR:
                # 不是响应帧（可能是我们自己发的请求），直接丢弃
                del self.buffer[:total_length]
                continue

            # 8. 尝试映射到 MSPCmd 枚举
            try:
                cmd_enum = MSPCmd(command)
            except ValueError:
                # 未知命令，丢弃该帧继续
                del self.buffer[:total_length]
                continue

            # 9. 解析 payload 并更新 flight_data
            try:
                self._parse_payload(cmd_enum, payload)
            except Exception:
                # 解析异常不致命，跳过该帧即可
                pass

            # 10. 登记结果并从缓冲移除
            results.append((cmd_enum, payload))
            self.last_frames.append((cmd_enum, payload))
            if len(self.last_frames) > 100:
                self.last_frames.pop(0)

            del self.buffer[:total_length]

        # 更新时间戳
        self.flight_data.timestamp = time.time()
        return results

    # ==================================================================
    # 各种 MSP payload 的反序列化实现
    # ==================================================================

    def _parse_payload(self, cmd: MSPCmd, payload: bytes):
        """
        根据命令类型反序列化 payload 并更新 self.flight_data
        """
        fd = self.flight_data
        plen = len(payload)

        if cmd == MSPCmd.MSP_IDENT and plen >= 7:
            # version(1) + multitype(1) + msp_version(1) + capability(4)
            # 这里只存 capability，不修改飞行数据主要字段
            try:
                vals = struct.unpack('<BBBI', payload[:7])
                fd.sensor_status = vals[3]  # capability 当作传感器状态
            except Exception:
                pass

        elif cmd == MSPCmd.MSP_STATUS and plen >= 11:
            # cycle_time(2) + i2c_errors_count(2) + sensor(2) + flag(4) + global_conf(1)
            try:
                vals = struct.unpack('<HHHIB', payload[:11])
                fd.cycle_time = vals[0]
                fd.i2c_errors = vals[1]
                fd.sensor_status = vals[2]
                fd.arming_flags = vals[3]
                # ARM 状态一般在 flag 的某一位，这里简化处理
                fd.armed = bool(vals[3] & 0x01)
            except Exception:
                pass

        elif cmd == MSPCmd.MSP_RAW_IMU and plen >= 18:
            # 9 个 int16: acx, acy, acz, gyx, gyy, gyz, magx, magy, magz
            try:
                vals = struct.unpack('<9h', payload[:18])
                # 加速度除以 1000 → g（单位：mG → g）
                fd.accel_x = vals[0] / 1000.0
                fd.accel_y = vals[1] / 1000.0
                fd.accel_z = vals[2] / 1000.0
                # 陀螺除以 1000 → deg/s（MSP 约定为 1/1000 deg/s）
                fd.gyro_x = vals[3] / 1000.0
                fd.gyro_y = vals[4] / 1000.0
                fd.gyro_z = vals[5] / 1000.0
                # 磁力计除以 1000 → gauss
                fd.mag_x = vals[6] / 1000.0
                fd.mag_y = vals[7] / 1000.0
                fd.mag_z = vals[8] / 1000.0
            except Exception:
                pass

        elif cmd == MSPCmd.MSP_ATTITUDE and plen >= 6:
            # 3 个 int16: angx, angy, heading → 除以 10 为 deg
            try:
                vals = struct.unpack('<3h', payload[:6])
                fd.roll = vals[0] / 10.0
                fd.pitch = vals[1] / 10.0
                # heading 为 int16，范围 -1800 ~ 1800（度*10），转换到 0~360
                heading_raw = vals[2]
                fd.yaw = heading_raw / 10.0
                fd.heading = (heading_raw / 10.0) % 360.0
            except Exception:
                pass

        elif cmd == MSPCmd.MSP_ALTITUDE and plen >= 6:
            # est_alt(4, cm) + vario(2, cm/s)
            try:
                est_alt, vario = struct.unpack('<ih', payload[:6])
                fd.altitude = est_alt / 100.0   # cm → m
                fd.variometer = vario / 100.0   # cm/s → m/s
            except Exception:
                pass

        elif cmd == MSPCmd.MSP_MOTOR and plen >= 2:
            # N 个 uint16 电机 PWM 值
            try:
                motor_count = plen // 2
                vals = struct.unpack('<' + 'H' * motor_count, payload[:plen - (plen % 2)])
                if motor_count >= 1: fd.motor_1 = vals[0]
                if motor_count >= 2: fd.motor_2 = vals[1]
                if motor_count >= 3: fd.motor_3 = vals[2]
                if motor_count >= 4: fd.motor_4 = vals[3]
            except Exception:
                pass

        elif cmd == MSPCmd.MSP_RC and plen >= 2:
            # N 个 uint16 通道值
            try:
                ch_count = plen // 2
                vals = struct.unpack('<' + 'H' * ch_count, payload[:plen - (plen % 2)])
                if ch_count >= 1: fd.rc_roll = vals[0]
                if ch_count >= 2: fd.rc_pitch = vals[1]
                if ch_count >= 3: fd.rc_throttle = vals[2]
                if ch_count >= 4: fd.rc_yaw = vals[3]
                if ch_count >= 5: fd.rc_aux1 = vals[4]
                if ch_count >= 6: fd.rc_aux2 = vals[5]
                if ch_count >= 7: fd.rc_aux3 = vals[6]
                if ch_count >= 8: fd.rc_aux4 = vals[7]
            except Exception:
                pass

        elif cmd == MSPCmd.MSP_ANALOG and plen >= 7:
            # vbat(1, 单位 0.1V) + power_meter_sum(2) + msp_time(2) + amperage(2)
            try:
                vals = struct.unpack('<BHHh', payload[:7])
                fd.vbat = vals[0] / 10.0
                if vals[3] >= 0:
                    fd.amperage = vals[3] / 100.0  # amperage 为 1/100 A
                fd.cycle_time = vals[2]  # msp_time 作循环时间估计
            except Exception:
                pass

        elif cmd == MSPCmd.MSP_RAW_GPS and plen >= 16:
            # fix(1) + num_sat(1) + lat(4, 1e-7 deg) + lon(4, 1e-7 deg)
            # + alt(2, m) + speed(2, cm/s) + ground_course(2, 0.1 deg)
            try:
                vals = struct.unpack('<BBiihhh', payload[:16])
                fd.gps_fix = vals[0]
                fd.gps_num_sat = vals[1]
                fd.gps_lat = vals[2] / 10000000.0
                fd.gps_lon = vals[3] / 10000000.0
                fd.gps_alt = vals[4] / 1.0      # alt 单位已为 m
                fd.gps_speed = vals[5] / 100.0   # cm/s → m/s
                fd.gps_heading = vals[6] / 10.0  # 0.1 deg → deg
            except Exception:
                pass

        elif cmd == MSPCmd.MSP_COMP_GPS and plen >= 10:
            # distance_to_home(2, m) + direction_to_home(2, deg)
            # + gps_update(1) + ...（不同固件字段略有差异，这里只读取有用的）
            try:
                # 简单使用：若包含速度/高度信息则刷新
                if plen >= 10:
                    vals = struct.unpack('<hhBBii', payload[:10])
                    # vals[0] distance(m), vals[1] direction, vals[2] update, vals[3] flags
                    # 可选更新 home 方向
                    pass
            except Exception:
                pass

        elif cmd == MSPCmd.MSP_PID and plen >= 3:
            # PID 数据：每个轴 3 个 uint8（P, I, D），PITCH/ROLL/YAW 通常在开头
            # MSP 存储为实际值 * 10
            try:
                pid_count = plen // 3
                vals = list(payload[:pid_count * 3])
                # 轴顺序：ROLL, PITCH, YAW（常见 MSP 顺序）
                axes = [
                    ('pid_roll_p', 'pid_roll_i', 'pid_roll_d'),
                    ('pid_pitch_p', 'pid_pitch_i', 'pid_pitch_d'),
                    ('pid_yaw_p', 'pid_yaw_i', 'pid_yaw_d'),
                ]
                for i, (pk, ik, dk) in enumerate(axes):
                    if i * 3 + 2 < len(vals):
                        setattr(fd, pk, vals[i * 3] / 10.0)
                        setattr(fd, ik, vals[i * 3 + 1] / 10.0)
                        setattr(fd, dk, vals[i * 3 + 2] / 10.0)
                        # 同时写入 params 缓存
                        self.params[pk] = vals[i * 3] / 10.0
                        self.params[ik] = vals[i * 3 + 1] / 10.0
                        self.params[dk] = vals[i * 3 + 2] / 10.0
            except Exception:
                pass

        elif cmd == MSPCmd.MSP_MISC and plen >= 20:
            # int16 power_trigger + uint16 conf[7] + uint32 conf[8]
            # 含电池电压校正等信息，这里提取 conf[0]/conf[1] 作为 home 点
            try:
                # 仅简单读取 MISC 的 conf 字段（具体格式随固件差异较大）
                pass
            except Exception:
                pass

        # 其它命令（BOXNAMES/PIDNAMES/DEBUG 等）不需要主动更新 FlightData

    # ==================================================================
    # 获取飞行数据
    # ==================================================================

    def get_flight_data(self):
        """返回解析到的飞行数据对象"""
        return self.flight_data

    # ==================================================================
    # 构建 MSP 请求帧
    # ==================================================================

    def _build_request(self, cmd: MSPCmd, payload: bytes = b'') -> bytes:
        """
        内部方法：构建一个完整的 MSP 请求帧。

        帧格式: $M '<' length cmd <data> crc
        """
        cmd_value = cmd.value if isinstance(cmd, MSPCmd) else int(cmd)
        length = len(payload) & 0xFF
        frame = bytearray()
        frame.extend(self.MSP_HEADER)         # $M
        frame.append(self.MSP_DIR_REQUEST)    # '<'
        frame.append(length)                  # length
        frame.append(cmd_value & 0xFF)        # cmd
        frame.extend(payload)                 # data

        # CRC = length ^ cmd ^ (所有 data 字节 XOR)
        crc = length ^ (cmd_value & 0xFF)
        for b in payload:
            crc ^= b
        frame.append(crc & 0xFF)
        return bytes(frame)

    # ---------- 常规状态请求 ----------

    def request_ident(self) -> bytes:
        """请求飞控身份信息（版本/类型/能力）"""
        return self._build_request(MSPCmd.MSP_IDENT)

    def request_status(self) -> bytes:
        """请求飞控状态（cycle_time、i2c_errors、sensor、flag 等）"""
        return self._build_request(MSPCmd.MSP_STATUS)

    def request_imu(self) -> bytes:
        """请求 IMU 原始数据"""
        return self._build_request(MSPCmd.MSP_RAW_IMU)

    def request_attitude(self) -> bytes:
        """请求姿态（roll/pitch/heading）"""
        return self._build_request(MSPCmd.MSP_ATTITUDE)

    def request_rc(self) -> bytes:
        """请求遥控器通道值"""
        return self._build_request(MSPCmd.MSP_RC)

    def request_motor(self) -> bytes:
        """请求电机输出值"""
        return self._build_request(MSPCmd.MSP_MOTOR)

    def request_raw_gps(self) -> bytes:
        """请求原始 GPS 数据"""
        return self._build_request(MSPCmd.MSP_RAW_GPS)

    def request_comp_gps(self) -> bytes:
        """请求融合后的 GPS 数据（回家距离/方向等）"""
        return self._build_request(MSPCmd.MSP_COMP_GPS)

    def request_analog(self) -> bytes:
        """请求模拟量（电压/电流等）"""
        return self._build_request(MSPCmd.MSP_ANALOG)

    def request_pid(self) -> bytes:
        """请求 PID 参数"""
        return self._build_request(MSPCmd.MSP_PID)

    def request_misc(self) -> bytes:
        """请求 MISC 配置"""
        return self._build_request(MSPCmd.MSP_MISC)

    # ---------- 校准请求 ----------

    def request_acc_calibration(self) -> bytes:
        """触发加速度计校准"""
        return self._build_request(MSPCmd.MSP_ACC_CALIBRATION)

    def request_mag_calibration(self) -> bytes:
        """触发磁力计校准"""
        return self._build_request(MSPCmd.MSP_MAG_CALIBRATION)

    # ---------- 设置请求 ----------

    def set_pid(self, pid_values: List[float]) -> bytes:
        """
        设置 PID 参数。

        Args:
            pid_values: 浮点列表，每个轴的 P/I/D 依次为一组。
                        通常顺序为: [ROLL_P, ROLL_I, ROLL_D,
                                    PITCH_P, PITCH_I, PITCH_D,
                                    YAW_P, YAW_I, YAW_D, ...]
                        值范围: 0.0 ~ 25.5（MSP 存为 value*10 的 uint8）

        Returns:
            MSP 帧字节
        """
        payload = bytearray()
        for v in pid_values:
            scaled = int(round(v * 10.0)) & 0xFF
            payload.append(scaled)
        return self._build_request(MSPCmd.MSP_SET_PID, bytes(payload))

    def set_rc(self, rc_values: List[int]) -> bytes:
        """
        设置遥控通道（MSP_SET_RAW_RC）。

        Args:
            rc_values: 8 个通道的 PWM 值（1000 ~ 2000），顺序为
                       [roll, pitch, throttle, yaw, aux1, aux2, aux3, aux4]

        Returns:
            MSP 帧字节
        """
        # 补齐到至少 8 个通道
        vals = list(rc_values)
        while len(vals) < 8:
            vals.append(1500)
        vals = vals[:8]
        payload = struct.pack('<8H', *[max(0, min(v & 0xFFFF, 0xFFFF)) for v in vals])
        return self._build_request(MSPCmd.MSP_SET_RAW_RC, payload)

    def set_motor(self, motor_values: List[int]) -> bytes:
        """
        设置电机测试值（MSP_SET_MOTOR）。

        Args:
            motor_values: 电机 PWM 值列表，一般 4 个，范围 1000 ~ 2000

        Returns:
            MSP 帧字节
        """
        vals = list(motor_values)
        while len(vals) < 4:
            vals.append(0)
        vals = vals[:8]  # 最多支持 8 个电机
        self._motor_values = vals[:4]
        payload = struct.pack('<' + str(len(vals)) + 'H',
                              *[max(0, min(v & 0xFFFF, 0xFFFF)) for v in vals])
        return self._build_request(MSPCmd.MSP_SET_MOTOR, payload)

    # ---------- 命令型请求 ----------

    def command_arm(self) -> bytes:
        """
        构建解锁命令。
        MSP 协议中通过 RC 通道的 yaw 最大值 + throttle 最小值实现解锁，
        这里提供一个便捷方法：发送一个带有 arm 模式的 RC 帧。
        """
        # 常规 MSP 解锁：yaw 最大(2000)、throttle 最小(1000)、其他居中
        return self.set_rc([1500, 1500, 1000, 2000, 1500, 1500, 1500, 1500])

    def command_disarm(self) -> bytes:
        """
        构建加锁命令。
        MSP 常规方式：yaw 最小(1000)、throttle 最小(1000)
        """
        return self.set_rc([1500, 1500, 1000, 1000, 1500, 1500, 1500, 1500])

    def command_reboot(self) -> bytes:
        """
        重启飞控：通过写 EEPROM（MSP_EEPROM_WRITE）模拟重启。
        注意：MSP 协议本身没有统一 reboot 命令，
        这里通过写 EEPROM 并配合部分固件行为触发重启。
        """
        return self._build_request(MSPCmd.MSP_EEPROM_WRITE)

    # ---------- 与 MAVLink 兼容的接口（MSP 端的映射） ----------

    def request_status_ex(self) -> bytes:
        """扩展状态请求（MSP 中映射到 MSP_STATUS）"""
        return self.request_status()

    def request_inav_status(self) -> bytes:
        """INAV 状态请求（MSP 中映射到 MSP_STATUS）"""
        return self.request_status()

    def request_comp_gps(self) -> bytes:
        """GPS 压缩数据（MSP 中映射到 RAW_GPS）"""
        return self.request_raw_gps()

    def request_task_info(self) -> bytes:
        """任务统计（MSP 无对应命令，返回 STATUS 代替）"""
        return self.request_status()

    def set_param(self, param_id: str, value: float) -> bytes:
        """
        设置参数（PX4 风格 ID → MSP 兼容）。
        对于 ROLL/PITCH/YAW 的 PID 参数，自动识别并写入 set_pid。
        其它参数暂不支持，返回空字节。
        """
        pid_map = {
            "MC_ROLLRATE_P": (0, "kp"),
            "MC_ROLLRATE_I": (0, "ki"),
            "MC_ROLLRATE_D": (0, "kd"),
            "MC_PITCHRATE_P": (1, "kp"),
            "MC_PITCHRATE_I": (1, "ki"),
            "MC_PITCHRATE_D": (1, "kd"),
            "MC_YAWRATE_P": (2, "kp"),
            "MC_YAWRATE_I": (2, "ki"),
            "MC_YAWRATE_D": (2, "kd"),
        }
        if param_id in pid_map:
            axis, comp = pid_map[param_id]
            current = list(getattr(self.flight_data,
                f"pid_{['roll','pitch','yaw'][axis]}_{comp}") for _ in range(1))
            # 简化：直接发送 set_pid，把 value 放到对应位置
            pids = [0.0] * 9  # ROLL P/I/D, PITCH P/I/D, YAW P/I/D
            idx = axis * 3 + {"kp": 0, "ki": 1, "kd": 2}[comp]
            pids[idx] = value
            return self.set_pid(pids)
        return b''

    def request_param(self, param_id: str = "") -> bytes:
        """请求单个参数（MSP 中映射到 request_pid）"""
        return self.request_pid()

    def request_all_params(self) -> bytes:
        """请求全部参数（MSP 中映射到 request_pid）"""
        return self.request_pid()


# ======================================================================
# 便捷函数：快速解析一帧
# ======================================================================

def parse_single_frame(data: bytes) -> Optional[Tuple[MSPCmd, bytes]]:
    """
    便捷函数：从字节中解析单帧 MSP 响应。

    Returns:
        (MSPCmd, payload_bytes) 或 None
    """
    parser = MSPProtocolParser()
    results = parser.parse_data(data)
    return results[0] if results else None


def build_request(cmd: MSPCmd, payload: bytes = b'') -> bytes:
    """
    便捷函数：构建 MSP 请求帧
    """
    return MSPProtocolParser()._build_request(cmd, payload)
