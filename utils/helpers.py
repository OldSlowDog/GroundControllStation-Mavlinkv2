"""
辅助工具函数
"""

import math
from typing import Tuple, List


def clamp(value: float, min_val: float, max_val: float) -> float:
    """将值限制在指定范围内"""
    return max(min_val, min(value, max_val))


def map_range(value: float, in_min: float, in_max: float, out_min: float, out_max: float) -> float:
    """线性映射"""
    return (value - in_min) * (out_max - out_min) / (in_max - in_min) + out_min


def deg_to_rad(degrees: float) -> float:
    """角度转弧度"""
    return degrees * math.pi / 180.0


def rad_to_deg(radians: float) -> float:
    """弧度转角度"""
    return radians * 180.0 / math.pi


def normalize_angle(angle: float) -> float:
    """归一化角度到 [-180, 180] 范围"""
    while angle > 180:
        angle -= 360
    while angle < -180:
        angle += 360
    return angle


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    计算两个GPS坐标之间的距离（米）
    使用Haversine公式
    """
    R = 6371000  # 地球半径（米）

    lat1_rad = deg_to_rad(lat1)
    lat2_rad = deg_to_rad(lat2)
    delta_lat = deg_to_rad(lat2 - lat1)
    delta_lon = deg_to_rad(lon2 - lon1)

    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    distance = R * c
    return distance


def smooth_data(data: List[float], window_size: int = 5) -> List[float]:
    """移动平均滤波"""
    if len(data) < window_size:
        return data

    smoothed = []
    half_window = window_size // 2

    for i in range(len(data)):
        start = max(0, i - half_window)
        end = min(len(data), i + half_window + 1)
        window = data[start:end]
        avg = sum(window) / len(window)
        smoothed.append(avg)

    return smoothed


def format_vbat(voltage: float) -> str:
    """格式化电压显示"""
    return f"{voltage:.2f}V"


def format_amperage(current: float) -> str:
    """格式化电流显示"""
    return f"{current:.2f}A"


def format_altitude(altitude: float) -> str:
    """格式化高度显示"""
    return f"{altitude:.1f}m"


def format_angle(angle: float) -> str:
    """格式化角度显示"""
    return f"{angle:.1f}°"