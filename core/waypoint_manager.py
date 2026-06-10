"""
航点（Waypoint）管理器
管理航点数据、序列化、MSP协议转换
"""

import json
import math
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum


class WaypointAction(Enum):
    """航点动作类型"""
    WAYPOINT = 0        # 普通航点（飞过）
    HOLD = 1            # 盘旋等待
    JUMP = 2            # 跳转到指定航点
    SET_HEADING = 3     # 设置航向
    LAND = 4            # 降落
    TAKEOFF = 5         # 起飞
    RTH = 6             # 返航


@dataclass
class Waypoint:
    """
    单个航点数据
    
    Attributes:
        index: 航点序号（从0开始）
        lat: 纬度（十进制度）
        lon: 经度（十进制度）
        alt: 相对高度或绝对高度（米）
        action: 航点动作类型
        param1: 动作参数1（如盘旋半径、跳转目标等）
        param2: 动作参数2
        stay_time: 停留时间（秒，仅HOLD有效）
        speed_limit: 速度限制（m/s，0=不限制）
    """
    index: int = 0
    lat: float = 0.0
    lon: float = 0.0
    alt: float = 50.0
    action: WaypointAction = WaypointAction.WAYPOINT
    param1: float = 0.0
    param2: float = 0.0
    stay_time: float = 0.0
    speed_limit: float = 0.0

    def to_dict(self) -> dict:
        return {
            'index': self.index,
            'lat': self.lat,
            'lon': self.lon,
            'alt': self.alt,
            'action': self.action.value,
            'param1': self.param1,
            'param2': self.param2,
            'stay_time': self.stay_time,
            'speed_limit': self.speed_limit
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Waypoint':
        return cls(
            index=data.get('index', 0),
            lat=data.get('lat', 0.0),
            lon=data.get('lon', 0.0),
            alt=data.get('alt', 50.0),
            action=WaypointAction(data.get('action', 0)),
            param1=data.get('param1', 0.0),
            param2=data.get('param2', 0.0),
            stay_time=data.get('stay_time', 0.0),
            speed_limit=data.get('speed_limit', 0.0)
        )


class WaypointManager:
    """
    航点管理器
    
    功能：
    1. 航点的增删改查
    2. 航点序列导入/导出（JSON/CSV/MSP格式）
    3. 航点间距离和航线总长度计算
    4. 航点验证（有效性检查、安全检查）
    
    使用示例：
        wpm = WaypointManager()
        wpm.add_waypoint(39.9042, 116.4074, alt=100)
        wpm.add_waypoint(39.91, 116.42, alt=120)
        total_dist = wpm.calculate_total_distance()
        mission_data = wpm.export_to_msp()
    """

    def __init__(self):
        self.waypoints: List[Waypoint] = []
        self._next_index = 0

    def add_waypoint(self, lat: float, lon: float,
                     alt: float = 50.0,
                     action: WaypointAction = WaypointAction.WAYPOINT,
                     **kwargs) -> Waypoint:
        """
        添加新航点
        
        Args:
            lat: 纬度
            lon: 经度
            alt: 高度（米）
            action: 动作类型
            **kwargs: 其他可选参数
        
        Returns:
            创建的Waypoint对象
        """
        wp = Waypoint(
            index=self._next_index,
            lat=lat,
            lon=lon,
            alt=alt,
            action=action,
            **kwargs
        )

        self.waypoints.append(wp)
        self._next_index += 1

        return wp

    def remove_waypoint(self, index: int) -> bool:
        """
        删除指定索引的航点
        
        Args:
            index: 航点索引
        
        Returns:
            是否删除成功
        """
        if 0 <= index < len(self.waypoints):
            self.waypoints.pop(index)
            self._renumber()
            return True
        return False

    def update_waypoint(self, index: int, **kwargs) -> bool:
        """
        更新航点属性
        
        Args:
            index: 航点索引
            **kwargs: 要更新的属性
        
        Returns:
            是否更新成功
        """
        if 0 <= index < len(self.waypoints):
            wp = self.waypoints[index]
            for key, value in kwargs.items():
                if hasattr(wp, key):
                    setattr(wp, key, value)
            return True
        return False

    def move_waypoint(self, index: int, new_lat: float, new_lon: float) -> bool:
        """移动航点到新位置"""
        return self.update_waypoint(index, lat=new_lat, lon=new_lon)

    def insert_waypoint(self, index: int, lat: float, lon: float,
                        alt: float = 50.0) -> bool:
        """在指定位置插入航点"""
        if 0 <= index <= len(self.waypoints):
            wp = Waypoint(index=index, lat=lat, lon=lon, alt=alt)
            self.waypoints.insert(index, wp)
            self._renumber()
            return True
        return False

    def clear(self):
        """清除所有航点"""
        self.waypoints.clear()
        self._next_index = 0

    def get_waypoint(self, index: int) -> Optional[Waypoint]:
        """获取指定航点"""
        if 0 <= index < len(self.waypoints):
            return self.waypoints[index]
        return None

    def get_all_waypoints(self) -> List[Dict]:
        """获取所有航点（字典格式）"""
        return [wp.to_dict() for wp in self.waypoints]

    def get_coordinates_list(self) -> List[Tuple[float, float]]:
        """获取所有航点坐标列表 [(lat, lon), ...]"""
        return [(wp.lat, wp.lon) for wp in self.waypoints]

    def _renumber(self):
        """重新编号所有航点"""
        for i, wp in enumerate(self.waypoints):
            wp.index = i
        self._next_index = len(self.waypoints)

    def calculate_total_distance(self) -> float:
        """
        计算航线总距离（米）
        
        使用 Haversine 公式计算相邻航点间的球面距离并累加
        """
        total = 0.0

        for i in range(1, len(self.waypoints)):
            prev_wp = self.waypoints[i - 1]
            curr_wp = self.waypoints[i]

            dist = self._haversine(
                prev_wp.lat, prev_wp.lon,
                curr_wp.lat, curr_wp.lon
            )
            total += dist

        return total

    def calculate_segment_distances(self) -> List[float]:
        """计算每段航线的距离"""
        distances = []

        for i in range(1, len(self.waypoints)):
            prev_wp = self.waypoints[i - 1]
            curr_wp = self.waypoints[i]

            dist = self._haversine(
                prev_wp.lat, prev_wp.lon,
                curr_wp.lat, curr_wp.lon
            )
            distances.append(dist)

        return distances

    def estimate_flight_time(self, avg_speed_ms: float = 15.0) -> float:
        """
        预估飞行时间（秒）
        
        Args:
            avg_speed_ms: 平均飞行速度（m/s），默认15m/s（约54km/h）
        
        Returns:
            预估飞行时间（秒），包含停留时间
        """
        if not self.waypoints:
            return 0.0

        total_dist = self.calculate_total_distance()
        flight_time = total_dist / avg_speed_ms if avg_speed_ms > 0 else 0

        # 加上所有停留时间
        hold_time = sum(wp.stay_time for wp in self.waypoints
                       if wp.action == WaypointAction.HOLD)

        return flight_time + hold_time

    def validate_mission(self) -> Tuple[bool, List[str]]:
        """
        验证任务有效性
        
        Returns:
            (是否有效, 错误/警告信息列表)
        """
        errors = []

        if len(self.waypoints) < 2:
            errors.append("Warning: Mission has fewer than 2 waypoints")

        # 检查坐标有效性
        for i, wp in enumerate(self.waypoints):
            if not (-90 <= wp.lat <= 90):
                errors.append(f"WP {i}: Invalid latitude {wp.lat}")
            if not (-180 <= wp.lon <= 180):
                errors.append(f"WP {i}: Invalid longitude {wp.lon}")
            if wp.alt < 0:
                errors.append(f"WP {i}: Negative altitude {wp.alt}")

        # 检查高度突变
        for i in range(1, len(self.waypoints)):
            prev_alt = self.waypoints[i - 1].alt
            curr_alt = self.waypoints[i].alt
            alt_diff = abs(curr_alt - prev_alt)

            if alt_diff > 200:
                errors.append(
                    f"WP {i}: Large altitude change ({prev_alt}→{curr_alt}m)"
                )

        return (len(errors) == 0, errors)

    def export_to_json(self) -> str:
        """导出为JSON字符串"""
        data = {
            'version': '1.0',
            'waypoints': [wp.to_dict() for wp in self.waypoints],
            'statistics': {
                'total_count': len(self.waypoints),
                'total_distance_m': round(self.calculate_total_distance(), 1),
                'estimated_time_s': round(self.estimate_flight_time(), 1)
            }
        }
        return json.dumps(data, indent=2)

    def import_from_json(self, json_str: str) -> bool:
        """从JSON字符串导入"""
        try:
            data = json.loads(json_str)
            self.clear()

            for wp_data in data.get('waypoints', []):
                wp = Waypoint.from_dict(wp_data)
                self.waypoints.append(wp)

            self._renumber()
            return True
        except Exception as e:
            print(f"[WaypointManager] Import error: {e}")
            return False

    def export_to_msp_format(self) -> List[List[int]]:
        """
        导出为MSP协议格式
        
        MSP_WP格式：[lat(int32), lon(int32), alt(int16), heading(int16), p1(uint16), p2(uint16), p3(uint16), flag(uint8)]
        
        Returns:
            二维列表，每个子列表代表一个航点的MSP数据
        """
        msp_data = []

        for wp in self.waypoints:
            # 坐标转换：度 → ×1e7（MSP标准格式）
            lat_int = int(wp.lat * 1e7)
            lon_int = int(wp.lon * 1e7)
            alt_int = int(wp.alt * 100)  # 厘米
            heading_int = int(0)  # 可选字段

            row = [
                lat_int & 0xFFFFFFFF,
                lon_int & 0xFFFFFFFF,
                alt_int & 0xFFFF,
                heading_int & 0xFFFF,
                int(wp.param1) & 0xFFFF,
                int(wp.param2) & 0xFFFF,
                int(wp.stay_time * 10) & 0xFFFF,  # 0.1秒单位
                wp.action.value & 0xFF
            ]

            msp_data.append(row)

        return msp_data

    @staticmethod
    def _haversine(lat1: float, lon1: float,
                   lat2: float, lon2: float) -> float:
        """计算两点间球面距离（米）"""
        R = 6371000

        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lambda = math.radians(lon2 - lon1)

        a = (math.sin(d_phi / 2) ** 2 +
             math.cos(phi1) * math.cos(phi2) *
             math.sin(d_lambda / 2) ** 2)

        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c
