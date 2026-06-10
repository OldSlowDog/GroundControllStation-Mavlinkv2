"""
飞行数据管理器
负责数据的存储、历史记录、统计分析
"""

import json
import csv
import os
from datetime import datetime
from typing import List, Dict, Optional
from collections import deque
import threading

from core.protocol_parser import FlightData


class DataManager:
    """数据管理器"""

    MAX_HISTORY_LENGTH = 1000  # 保留最近1000条数据

    def __init__(self):
        self.current_data = FlightData()
        self.history_data = deque(maxlen=self.MAX_HISTORY_LENGTH)
        self.lock = threading.Lock()

        # 数据记录状态
        self.is_recording = False
        self.record_file = None
        self.record_writer = None

        # 统计信息
        self.stats = {
            'max_altitude': 0.0,
            'min_altitude': 0.0,
            'max_speed': 0.0,
            'flight_time': 0.0,
            'packets_received': 0,
            'packets_lost': 0
        }

        self.start_time = None

    def update_data(self, flight_data: FlightData):
        """更新当前数据并添加到历史记录"""
        with self.lock:
            self.current_data = flight_data
            self.history_data.append(flight_data)
            self.stats['packets_received'] += 1

            # 更新统计信息
            if flight_data.altitude > self.stats['max_altitude']:
                self.stats['max_altitude'] = flight_data.altitude
            if flight_data.altitude < self.stats['min_altitude']:
                self.stats['min_altitude'] = flight_data.altitude

            speed = (flight_data.gyro_x**2 + flight_data.gyro_y**2 + flight_data.gyro_z**2)**0.5
            if speed > self.stats['max_speed']:
                self.stats['max_speed'] = speed

            if self.start_time is None:
                self.start_time = flight_data.timestamp
            else:
                self.stats['flight_time'] = flight_data.timestamp - self.start_time

            # 如果正在记录，写入文件
            if self.is_recording and self.record_writer:
                self._write_record(flight_data)

    def get_current(self) -> FlightData:
        """获取当前最新数据"""
        with self.lock:
            return self.current_data

    def get_history(self, count: int = -1) -> List[FlightData]:
        """获取历史数据"""
        with self.lock:
            if count == -1:
                return list(self.history_data)
            elif count <= len(self.history_data):
                return list(self.history_data)[-count:]
            else:
                return list(self.history_data)

    def get_history_field(self, field_name: str, count: int = -1) -> List[float]:
        """获取指定字段的历史值列表"""
        history = self.get_history(count)
        values = []
        for data in history:
            if hasattr(data, field_name):
                values.append(getattr(data, field_name))
        return values

    def start_recording(self, filename: Optional[str] = None) -> bool:
        """开始记录数据到CSV文件"""
        try:
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"logs/flight_log_{timestamp}.csv"

            # 确保目录存在
            os.makedirs(os.path.dirname(filename), exist_ok=True)

            self.record_file = open(filename, 'w', newline='', encoding='utf-8')
            self.record_writer = csv.writer(self.record_file)

            # 写入表头
            headers = [
                'timestamp', 'roll', 'pitch', 'yaw',
                'accel_x', 'accel_y', 'accel_z',
                'gyro_x', 'gyro_y', 'gyro_z',
                'rc_roll', 'rc_pitch', 'rc_yaw', 'rc_throttle',
                'motor_1', 'motor_2', 'motor_3', 'motor_4',
                'armed', 'vbat', 'amperage', 'altitude'
            ]
            self.record_writer.writerow(headers)
            self.record_file.flush()

            self.is_recording = True
            return True

        except Exception as e:
            print(f"开始记录失败: {e}")
            return False

    def stop_recording(self) -> str:
        """停止记录并返回文件路径"""
        filename = ""
        try:
            if self.record_file:
                filename = self.record_file.name
                self.record_file.close()
                self.record_file = None
                self.record_writer = None
        except Exception as e:
            print(f"停止记录失败: {e}")

        self.is_recording = False
        return filename

    def _write_record(self, data: FlightData):
        """写入一条数据记录"""
        row = [
            data.timestamp,
            f"{data.roll:.2f}", f"{data.pitch:.2f}", f"{data.yaw:.2f}",
            f"{data.accel_x:.3f}", f"{data.accel_y:.3f}", f"{data.accel_z:.3f}",
            f"{data.gyro_x:.2f}", f"{data.gyro_y:.2f}", f"{data.gyro_z:.2f}",
            data.rc_roll, data.rc_pitch, data.rc_yaw, data.rc_throttle,
            data.motor_1, data.motor_2, data.motor_3, data.motor_4,
            int(data.armed),
            f"{data.vbat:.2f}", f"{data.amperage:.2f}", f"{data.altitude:.2f}"
        ]
        self.record_writer.writerow(row)
        self.record_file.flush()

    def export_to_json(self, filename: str) -> bool:
        """导出数据为JSON格式"""
        try:
            history = self.get_history()
            export_data = []

            for data in history:
                export_data.append({
                    'timestamp': data.timestamp,
                    'roll': data.roll,
                    'pitch': data.pitch,
                    'yaw': data.yaw,
                    'altitude': data.altitude,
                    'vbat': data.vbat,
                    'armed': data.armed
                })

            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

            return True

        except Exception as e:
            print(f"导出失败: {e}")
            return False

    def clear_history(self):
        """清除所有历史数据"""
        with self.lock:
            self.history_data.clear()
            self.stats['max_altitude'] = 0.0
            self.stats['min_altitude'] = 0.0
            self.stats['max_speed'] = 0.0
            self.stats['flight_time'] = 0.0
            self.stats['packets_received'] = 0
            self.stats['packets_lost'] = 0
            self.start_time = None

    def get_statistics(self) -> Dict:
        """获取统计信息"""
        with self.lock:
            return self.stats.copy()


# 全局单例实例
data_manager = DataManager()