"""
GPS追踪器
处理GPS数据、管理飞行轨迹、提供位置过滤和插值算法
"""

import math
import time
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class GPSPoint:
    """单个GPS数据点"""
    timestamp: float
    lat: float
    lon: float
    alt: float = 0.0
    speed: float = 0.0
    heading: float = 0.0
    sats: int = 0
    fix_type: int = 0

    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp,
            'lat': self.lat,
            'lon': self.lon,
            'alt': self.alt,
            'speed': self.speed,
            'heading': self.heading,
            'sats': self.sats,
            'fix_type': self.fix_type
        }


class GPSTracker:
    """
    GPS数据追踪器
    
    功能：
    1. 接收并缓存原始GPS数据
    2. 移动平均滤波（减少抖动）
    3. 轨迹记录（环形缓冲区）
    4. 统计信息计算（距离、速度、最大高度等）
    5. 坐标转换辅助函数
    
    使用示例：
        tracker = GPSTracker(max_track_points=5000)
        tracker.update(lat, lon, alt, speed, sats, fix_type)
        stats = tracker.get_statistics()
    """

    def __init__(self,
                 max_track_points: int = 5000,
                 filter_window: int = 5,
                 min_accuracy: float = 2.0):
        """
        初始化GPS追踪器
        
        Args:
            max_track_points: 最大轨迹点数
            filter_window: 滤波窗口大小（用于移动平均）
            min_accuracy: 最小有效精度阈值（米）
        """
        self.max_track_points = max_track_points
        self.filter_window = filter_window
        self.min_accuracy = min_accuracy

        # 当前状态
        self.current_position: Optional[GPSPoint] = None
        self.last_valid_position: Optional[GPSPoint] = None

        # 轨迹历史
        self.track_history: List[GPSPoint] = []

        # 滤波缓冲区
        self._lat_buffer: List[float] = []
        self._lon_buffer: List[float] = []
        self._alt_buffer: List[float] = []

        # 统计数据
        self.total_distance_m = 0.0
        self.max_altitude_m = 0.0
        self.max_speed_ms = 0.0
        self.flight_time_s = 0.0
        self._start_time: Optional[float] = None

    def update(self,
               lat: float, lon: float,
               alt: float = 0.0,
               speed: float = 0.0,
               heading: float = 0.0,
               sats: int = 0,
               fix_type: int = 0) -> Optional[GPSPoint]:
        """
        更新GPS位置
        
        Args:
            lat: 纬度
            lon: 经度
            alt: 高度（米）
            speed: 地速（m/s）
            heading: 航向角（度）
            sats: 卫星数量
            fix_type: 定位类型 (0=NoFix, 1=2D, 2=3D, 3=DGPS)
        
        Returns:
            过滤后的GPSPoint对象，如果无效则返回None
        """
        if fix_type == 0 or lat == 0 or lon == 0:
            return None

        now = time.time()

        # 应用移动平均滤波
        filtered_lat, filtered_lon, filtered_alt = self._apply_filter(
            lat, lon, alt
        )

        # 创建新的GPS点
        point = GPSPoint(
            timestamp=now,
            lat=filtered_lat,
            lon=filtered_lon,
            alt=filtered_alt,
            speed=speed,
            heading=heading,
            sats=sats,
            fix_type=fix_type
        )

        # 计算统计信息
        if self.last_valid_position is not None:
            distance = self.haversine_distance(
                self.last_valid_position.lat,
                self.last_valid_position.lon,
                point.lat,
                point.lon
            )
            self.total_distance_m += distance

        self.max_altitude_m = max(self.max_altitude_m, alt)
        self.max_speed_ms = max(self.max_speed_ms, speed)

        # 更新状态
        self.last_valid_position = self.current_position
        self.current_position = point

        # 添加到轨迹
        self.track_history.append(point)
        if len(self.track_history) > self.max_track_points:
            self.track_history.pop(0)

        # 记录开始时间
        if self._start_time is None and fix_type >= 2:
            self._start_time = now
        if self._start_time:
            self.flight_time_s = now - self._start_time

        return point

    def _apply_filter(self, lat: float, lon: float, alt: float) -> Tuple[float, float, float]:
        """
        应用移动平均滤波
        
        简单的滑动窗口平均，有效减少GPS抖动
        """
        self._lat_buffer.append(lat)
        self._lon_buffer.append(lon)
        self._alt_buffer.append(alt)

        # 保持缓冲区大小
        if len(self._lat_buffer) > self.filter_window:
            self._lat_buffer.pop(0)
        if len(self._lon_buffer) > self.filter_window:
            self._lon_buffer.pop(0)
        if len(self._alt_buffer) > self.filter_window:
            self._alt_buffer.pop(0)

        # 计算平均值
        avg_lat = sum(self._lat_buffer) / len(self._lat_buffer)
        avg_lon = sum(self._lon_buffer) / len(self._lon_buffer)
        avg_alt = sum(self._alt_buffer) / len(self._alt_buffer)

        return avg_lat, avg_lon, avg_alt

    def get_current_position(self) -> Optional[Dict]:
        """获取当前位置"""
        if self.current_position is None:
            return None
        return self.current_position.to_dict()

    def get_track_history(self) -> List[Dict]:
        """获取完整轨迹历史"""
        return [point.to_dict() for point in self.track_history]

    def get_recent_track(self, last_n: int = 100) -> List[Dict]:
        """获取最近N个轨迹点"""
        recent = self.track_history[-last_n:] if len(self.track_history) > last_n else self.track_history
        return [point.to_dict() for point in recent]

    def get_statistics(self) -> dict:
        """
        获取飞行统计数据
        
        Returns:
            包含以下字段的字典：
            - total_distance_km: 总飞行距离（公里）
            - max_altitude_m: 最大高度（米）
            - max_speed_kmh: 最大速度（km/h）
            - flight_time_s: 飞行时间（秒）
            - track_point_count: 轨迹点数量
            - current_fix: 当前定位类型描述
        """
        fix_types = {
            0: "No Fix",
            1: "2D Fix",
            2: "3D Fix",
            3: "DGPS"
        }

        current_fix = "No Data"
        if self.current_position:
            current_fix = fix_types.get(
                self.current_position.fix_type,
                "Unknown"
            )

        return {
            'total_distance_km': round(self.total_distance_m / 1000, 3),
            'max_altitude_m': round(self.max_altitude_m, 1),
            'max_speed_kmh': round(self.max_speed_ms * 3.6, 1),
            'flight_time_s': round(self.flight_time_s, 1),
            'flight_time_str': self._format_duration(self.flight_time_s),
            'track_point_count': len(self.track_history),
            'current_fix': current_fix,
            'satellites': self.current_position.sats if self.current_position else 0
        }

    def clear_track(self):
        """清除所有轨迹数据"""
        self.track_history.clear()
        self.total_distance_m = 0.0
        self.max_altitude_m = 0.0
        self.max_speed_ms = 0.0
        self.flight_time_s = 0.0
        self._start_time = None
        self.last_valid_position = None

    @staticmethod
    def haversine_distance(lat1: float, lon1: float,
                           lat2: float, lon2: float) -> float:
        """
        使用Haversine公式计算两点间球面距离（米）
        
        Args:
            lat1, lon1: 起点坐标（十进制度）
            lat2, lon2: 终点坐标（十进制度）
        
        Returns:
            两点间的地面距离（米）
        """
        R = 6371000  # 地球半径（米）

        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = (math.sin(delta_phi / 2) ** 2 +
             math.cos(phi1) * math.cos(phi2) *
             math.sin(delta_lambda / 2) ** 2)

        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    @staticmethod
    def calculate_bearing(lat1: float, lon1: float,
                          lat2: float, lon2: float) -> float:
        """
        计算两点间的方位角（度）
        
        Returns:
            从点到点的方位角（0-360°，正北为0°）
        """
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_lambda = math.radians(lon2 - lon1)

        x = math.sin(delta_lambda) * math.cos(phi2)
        y = (math.cos(phi1) * math.sin(phi2) -
             math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda))

        bearing = math.atan2(x, y)
        bearing = math.degrees(bearing)
        bearing = (bearing + 360) % 360

        return bearing

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """格式化持续时间"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"
