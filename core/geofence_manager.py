"""
地理围栏（Geofence）管理器
支持圆形和多边形围栏的创建、验证和导出
"""

import math
import json
from typing import List, Dict, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum


class GeofenceType(Enum):
    """地理围栏类型"""
    CIRCLE = "circle"
    POLYGON = "polygon"


class GeofenceAction(Enum):
    """触发围栏时的动作"""
    WARNING = 0          # 仅警告
    RTH = 1              # 自动返航
    LAND = 2             # 紧急降落
    HOLD = 3             # 悬停等待


@dataclass
class Geofence:
    """
    地理围栏数据结构
    
    Attributes:
        fence_id: 围栏唯一标识符
        name: 围栏名称
        type: 围栏类型（圆形/多边形）
        action: 触发动作
        enabled: 是否启用
        
        圆形围栏特有：
            center: 圆心坐标 [lat, lon]
            radius: 半径（米）
        
        多边形围栏特有：
            points: 顶点坐标列表 [[lat, lon], ...]
        
        公共属性：
            altitude_min: 最小高度限制（米，-1=不限制）
            altitude_max: 最大高度限制（米，-1=不限制）
    """
    fence_id: int = 0
    name: str = ""
    type: GeofenceType = GeofenceType.CIRCLE
    action: GeofenceAction = GeofenceAction.WARNING
    enabled: bool = True

    # 圆形围栏参数
    center: List[float] = field(default_factory=lambda: [0.0, 0.0])
    radius: float = 100.0

    # 多边形围栏参数
    points: List[List[float]] = field(default_factory=list)

    # 高度限制
    altitude_min: float = -1.0   # -1表示不限制
    altitude_max: float = -1.0

    def to_dict(self) -> dict:
        data = {
            'fence_id': self.fence_id,
            'name': self.name,
            'type': self.type.value,
            'action': self.action.value,
            'enabled': self.enabled,
            'altitude_min': self.altitude_min,
            'altitude_max': self.altitude_max
        }

        if self.type == GeofenceType.CIRCLE:
            data['center'] = self.center
            data['radius'] = self.radius
        else:
            data['points'] = self.points

        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'Geofence':
        fence_type = GeofenceType(data.get('type', 'circle'))

        return cls(
            fence_id=data.get('fence_id', 0),
            name=data.get('name', ''),
            type=fence_type,
            action=GeofenceAction(data.get('action', 0)),
            enabled=data.get('enabled', True),
            center=data.get('center', [0.0, 0.0]),
            radius=data.get('radius', 100.0),
            points=data.get('points', []),
            altitude_min=data.get('altitude_min', -1.0),
            altitude_max=data.get('altitude_max', -1.0)
        )


class GeofenceManager:
    """
    地理围栏管理器
    
    功能：
    1. 创建和管理多个围栏（圆形/多边形）
    2. 实时检测位置是否在围栏内/外
    3. 围栏冲突检测（重叠检查）
    4. 导入/导出围栏配置
    
    使用示例：
        gfm = GeofenceManager()
        gfm.add_circle_fence("No-Fly Zone", lat, lon, radius=500)
        is_inside = gfm.check_position(lat, lon)
    """

    def __init__(self):
        self.geofences: List[Geofence] = []
        self._next_id = 0

    def add_circle_fence(self,
                         name: str,
                         center_lat: float,
                         center_lon: float,
                         radius: float,
                         action: GeofenceAction = GeofenceAction.WARNING,
                         **kwargs) -> Geofence:
        """
        添加圆形地理围栏
        
        Args:
            name: 围栏名称
            center_lat: 圆心纬度
            center_lon: 圆心经度
            radius: 半径（米）
            action: 触发动作
            **kwargs: 其他可选参数（altitude_min/max等）
        
        Returns:
            创建的Geofence对象
        """
        fence = Geofence(
            fence_id=self._next_id,
            name=name,
            type=GeofenceType.CIRCLE,
            action=action,
            center=[center_lat, center_lon],
            radius=radius,
            **kwargs
        )

        self.geofences.append(fence)
        self._next_id += 1

        return fence

    def add_polygon_fence(self,
                          name: str,
                          points: List[Tuple[float, float]],
                          action: GeofenceAction = GeofenceAction.WARNING,
                          **kwargs) -> Geofence:
        """
        添加多边形地理围栏
        
        Args:
            name: 围栏名称
            points: 顶点坐标列表 [(lat, lon), ...]，至少3个点
            action: 触发动作
            **kwargs: 其他可选参数
        
        Returns:
            创建的Geofence对象
        """
        if len(points) < 3:
            raise ValueError("Polygon must have at least 3 points")

        fence = Geofence(
            fence_id=self._next_id,
            name=name,
            type=GeofenceType.POLYGON,
            action=action,
            points=[list(pt) for pt in points],
            **kwargs
        )

        self.geofences.append(fence)
        self._next_id += 1

        return fence

    def remove_fence(self, fence_id: int) -> bool:
        """删除指定ID的围栏"""
        for i, fence in enumerate(self.geofences):
            if fence.fence_id == fence_id:
                self.geofences.pop(i)
                return True
        return False

    def clear(self):
        """清除所有围栏"""
        self.geofences.clear()

    def get_fence(self, fence_id: int) -> Optional[Geofence]:
        """获取指定围栏"""
        for fence in self.geofences:
            if fence.fence_id == fence_id:
                return fence
        return None

    def enable_fence(self, fence_id: int, enabled: bool = True) -> bool:
        """启用/禁用围栏"""
        fence = self.get_fence(fence_id)
        if fence:
            fence.enabled = enabled
            return True
        return False

    def check_position(self, lat: float, lon: float,
                       alt: float = 0.0) -> Tuple[bool, Optional[Geofence]]:
        """
        检查坐标是否在任意启用的围栏内
        
        Args:
            lat: 纬度
            lon: 经度
            alt: 高度（用于高度限制检查）
        
        Returns:
            (是否在围栏内, 触发的围栏对象或None)
        """
        for fence in self.geofences:
            if not fence.enabled:
                continue

            # 先检查水平位置
            is_inside = False

            if fence.type == GeofenceType.CIRCLE:
                is_inside = self._point_in_circle(
                    lat, lon,
                    fence.center[0], fence.center[1],
                    fence.radius
                )
            elif fence.type == GeofenceType.POLYGON:
                is_inside = self._point_in_polygon(
                    lat, lon, fence.points
                )

            if is_inside:
                # 再检查高度限制
                if fence.altitude_min >= 0 and alt < fence.altitude_min:
                    continue
                if fence.altitude_max >= 0 and alt > fence.altitude_max:
                    continue

                return (True, fence)

        return (False, None)

    def check_all_positions(self, positions: List[Tuple[float, float]],
                            alt: float = 0.0) -> List[Tuple[int, bool, Optional[Geofence]]]:
        """
        批量检查多个坐标点
        
        Args:
            positions: 坐标列表 [(lat, lon), ...]
            alt: 高度
        
        Returns:
            [(索引, 是否在围栏内, 触发的围栏), ...]
        """
        results = []

        for i, (lat, lon) in enumerate(positions):
            inside, fence = self.check_position(lat, lon, alt)
            results.append((i, inside, fence))

        return results

    def find_conflicts(self) -> List[Tuple[Geofence, Geofence]]:
        """
        检测围栏之间的重叠冲突
        
        Returns:
            冲突的围栏对列表 [(fence1, fence2), ...]
        """
        conflicts = []

        for i in range(len(self.geofences)):
            for j in range(i + 1, len(self.geofences)):
                f1 = self.geofences[i]
                f2 = self.geofences[j]

                if self._fences_overlap(f1, f2):
                    conflicts.append((f1, f2))

        return conflicts

    def export_to_json(self) -> str:
        """导出所有围栏为JSON字符串"""
        data = {
            'version': '1.0',
            'geofences': [f.to_dict() for f in self.geofences]
        }
        return json.dumps(data, indent=2)

    def import_from_json(self, json_str: str) -> bool:
        """从JSON导入围栏配置"""
        try:
            data = json.loads(json_str)
            self.clear()

            for fence_data in data.get('geofences', []):
                fence = Geofence.from_dict(fence_data)
                self.geofences.append(fence)

            return True
        except Exception as e:
            print(f"[GeofenceManager] Import error: {e}")
            return False

    @staticmethod
    def _point_in_circle(lat: float, lon: float,
                         center_lat: float, center_lon: float,
                         radius_m: float) -> bool:
        """
        检查点是否在圆内（使用Haversine近似）
        
        对于小半径（<10km），可以使用简化的平面距离公式提高性能
        """
        distance = GeofenceManager._haversine_distance(
            lat, lon, center_lat, center_lon
        )

        return distance <= radius_m

    @staticmethod
    def _point_in_polygon(lat: float, lon: float,
                          polygon: List[List[float]]) -> bool:
        """
        射线法判断点是否在多边形内
        
        从该点向右发射一条射线，统计与多边形边的交点数量：
        - 奇数个交点：在多边形内
        - 偶数个交点：在多边形外
        """
        n = len(polygon)
        inside = False

        j = n - 1
        for i in range(n):
            xi, yi = polygon[i][0], polygon[i][1]
            xj, yj = polygon[j][0], polygon[j][1]

            if ((yi > lat) != (yj > lat)) and \
               (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
                inside = not inside

            j = i

        return inside

    @staticmethod
    def _haversine_distance(lat1: float, lon1: float,
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

    def _fences_overlap(self, f1: Geofence, f2: Geofence) -> bool:
        """
        检测两个围栏是否重叠（简化版本：仅检查中心距）
        
        完整版本应该使用几何相交算法
        """
        if f1.type == GeofenceType.CIRCLE and f2.type == GeofenceType.CIRCLE:
            dist = self._haversine_distance(
                f1.center[0], f1.center[1],
                f2.center[0], f2.center[1]
            )
            return dist < (f1.radius + f2.radius)

        # 其他组合暂不实现完整检测
        return False
