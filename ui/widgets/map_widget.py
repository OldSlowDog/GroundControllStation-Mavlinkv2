"""
地图控件组件
封装 QWebEngineView + Leaflet.js + OpenStreetMap（无需 API Key）
提供 Python-JavaScript 双向通信桥
"""

import os
import json
import time
from PyQt5.QtWidgets import QWidget, QVBoxLayout
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QUrl
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebChannel import QWebChannel


# Nominatim 请求节流（官方要求：最多 1 次 / 秒）
_last_nominatim_request = 0.0


class MapBridge(QObject):
    """
    JavaScript-Python 桥接对象

    通过 Qt WebChannel 实现 Python 和 JavaScript 之间的双向通信：
    - Python → JS: 使用 pyqtSignal + emit()
    - JS → Python: 使用 @pyqtSlot 方法
    """

    # ===== 信号 (Python → JavaScript) =====
    updateDronePosition = pyqtSignal(float, float, float, float)
    updateGPSInfo = pyqtSignal(float, float, float, float, int, int)
    clearWaypoints = pyqtSignal()
    loadWaypoints = pyqtSignal(str)
    loadGeofence = pyqtSignal(str)
    setMapCenter = pyqtSignal(float, float, int)
    centerOnDrone = pyqtSignal()
    clearTrack = pyqtSignal()
    toggleWaypointMode = pyqtSignal(bool)
    toggleFenceMode = pyqtSignal(bool)
    toggleInsertMode = pyqtSignal(bool)
    exportData = pyqtSignal(str)
    searchResults = pyqtSignal(str)

    # ===== 内部信号 (桥接用) =====
    waypoint_added = pyqtSignal(int, float, float)
    waypoint_moved = pyqtSignal(int, float, float)
    waypoint_deleted = pyqtSignal(int)
    waypoint_edited = pyqtSignal(dict)
    fence_point_added = pyqtSignal(float, float)
    geofence_created = pyqtSignal(dict)
    map_clicked = pyqtSignal(float, float)
    data_exported = pyqtSignal(dict)
    location_searched = pyqtSignal(float, float, str)

    # ===== 槽函数 (JavaScript → Python) =====
    @pyqtSlot(int, float, float)
    def addWaypoint(self, index: int, lat: float, lon: float):
        self.waypoint_added.emit(index, lat, lon)

    @pyqtSlot(int, float, float)
    def moveWaypoint(self, index: int, lat: float, lon: float):
        self.waypoint_moved.emit(index, lat, lon)

    @pyqtSlot(int)
    def deleteWaypoint(self, index: int):
        self.waypoint_deleted.emit(index)

    @pyqtSlot(float, float)
    def addFencePoint(self, lat: float, lon: float):
        self.fence_point_added.emit(lat, lon)

    @pyqtSlot('QVariant')
    def createGeofence(self, jsonStr):
        """JS端调用：创建围栏（Qt WebChannel 可能自动反序列化）"""
        try:
            if isinstance(jsonStr, (list, dict)):
                data = jsonStr
            elif isinstance(jsonStr, str):
                data = json.loads(jsonStr)
            else:
                data = {}
            self.geofence_created.emit(data)
        except Exception as e:
            print(f"[MapBridge] Error parsing geofence: {e}")

    @pyqtSlot('QVariant')
    def editWaypoint(self, jsonStr):
        """JS端调用：编辑航点（任务类型、高度、速度）"""
        try:
            if isinstance(jsonStr, (list, dict)):
                data = jsonStr
            elif isinstance(jsonStr, str):
                data = json.loads(jsonStr)
            else:
                data = {}
            self.waypoint_edited.emit(data)
        except Exception as e:
            print(f"[MapBridge] Error parsing edit data: {e}")

    @pyqtSlot(float, float, str)
    def locationSearched(self, lat: float, lng: float, name: str):
        """JS端选中搜索结果后回调"""
        self.location_searched.emit(lat, lng, name)

    @pyqtSlot(float, float)
    def mapClicked(self, lat: float, lng: float):
        """地图点击事件（可选）"""
        self.map_clicked.emit(lat, lng)

    @pyqtSlot(str)
    def searchPlace(self, keyword: str):
        """
        地点搜索 — 使用 OpenStreetMap Nominatim 服务
        ★ 完全免费，无需 API Key
        ★ 使用注意：官方要求 ≤ 1 次 / 秒，这里做了节流与 UA 声明
        """
        global _last_nominatim_request
        try:
            from urllib.request import urlopen, Request
            import urllib.parse as uparse
        except ImportError:
            self.searchResults.emit(json.dumps(
                [{"display_name": "系统缺少 urllib，无法搜索", "lat": 0, "lon": 0}]
            ))
            return

        keyword = (keyword or "").strip()
        if not keyword:
            return

        # --- 节流：避免被 Nominatim 封禁 ---
        now = time.time()
        wait = 1.0 - (now - _last_nominatim_request)
        if wait > 0:
            time.sleep(wait)
            now = time.time()
        _last_nominatim_request = now

        # 构造请求（中文结果 + JSON + 限 10 条）
        params = uparse.urlencode({
            "q": keyword,
            "format": "jsonv2",
            "limit": 10,
            "addressdetails": 0,
            "accept-language": "zh-CN"
        })
        url = f"https://nominatim.openstreetmap.org/search?{params}"

        try:
            req = Request(url, headers={
                "User-Agent": "GCS-Desktop-App/1.0 (local-use)",
                "Accept": "application/json"
            })
            resp = urlopen(req, timeout=8)
            raw = resp.read().decode("utf-8")
            self.searchResults.emit(raw)  # 直接把 JSON 数组转发给 JS
        except Exception as e:
            err = f'[{{"display_name":"搜索失败: {e}", "lat":0, "lon":0}}]'
            self.searchResults.emit(err)
            print(f"[MapBridge] Nominatim search error: {e}")


class MapWidget(QWidget):
    """
    地图显示控件（Leaflet.js + OSM，无需 API Key）

    使用示例：
        widget = MapWidget()
        widget.update_drone(39.9042, 116.4074, alt=100.0, heading=180.0)
        widget.load_waypoints([{"index":0, "lat":..., "lng":...}, ...])
    """

    waypoint_added = pyqtSignal(int, float, float)
    waypoint_moved = pyqtSignal(int, float, float)
    waypoint_deleted = pyqtSignal(int)
    waypoint_edited = pyqtSignal(dict)
    fence_point_added = pyqtSignal(float, float)
    geofence_created = pyqtSignal(dict)
    location_searched = pyqtSignal(float, float, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bridge = MapBridge()
        self._setup_ui()
        self._setup_channel()
        self._connect_signals()

    # --------- UI ---------
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.web_view = QWebEngineView()
        layout.addWidget(self.web_view)

        html_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "resources", "map", "map.html"
        )
        self.web_view.load(QUrl.fromLocalFile(html_path))

    # --------- 通信桥 ---------
    def _setup_channel(self):
        self.channel = QWebChannel()
        self.channel.registerObject("bridge", self.bridge)
        page = self.web_view.page()
        page.setWebChannel(self.channel)
        page.featurePermissionRequested.connect(
            self._on_feature_permission_requested
        )

    def _connect_signals(self):
        self.bridge.waypoint_added.connect(
            lambda i, la, ln: self.waypoint_added.emit(i, la, ln)
        )
        self.bridge.waypoint_moved.connect(
            lambda i, la, ln: self.waypoint_moved.emit(i, la, ln)
        )
        self.bridge.waypoint_deleted.connect(
            lambda i: self.waypoint_deleted.emit(i)
        )
        self.bridge.waypoint_edited.connect(
            lambda d: self.waypoint_edited.emit(d)
        )
        self.bridge.fence_point_added.connect(
            lambda la, ln: self.fence_point_added.emit(la, ln)
        )
        self.bridge.geofence_created.connect(
            lambda d: self.geofence_created.emit(d)
        )
        self.bridge.location_searched.connect(
            lambda la, ln, nm: self.location_searched.emit(la, ln, nm)
        )

    # --------- 权限处理 ---------
    def _on_feature_permission_requested(self, securityOrigin, feature):
        page = self.web_view.page()
        page.setFeaturePermission(securityOrigin, feature, 2)  # 2 = granted

    # ===== 对外操作 API =====
    def update_drone(self, lat, lng, alt=0, heading=0):
        self.bridge.updateDronePosition.emit(lat, lng, alt, heading)

    def update_gps(self, fix=3, sats=10, lat=0, lng=0, alt=0, speed=0, heading=0):
        self.bridge.updateGPSInfo.emit(fix, sats, lat, lng, speed, heading)

    def clear_waypoints(self):
        self.bridge.clearWaypoints.emit()

    def load_waypoints(self, wps):
        self.bridge.loadWaypoints.emit(json.dumps(wps))

    def load_geofence(self, data):
        self.bridge.loadGeofence.emit(json.dumps(data))

    def set_center(self, lat, lng, zoom=None):
        self.bridge.setMapCenter.emit(lat, lng, zoom if zoom is not None else -1)

    def center_on_drone(self):
        self.bridge.centerOnDrone.emit()

    def clear_track(self):
        self.bridge.clearTrack.emit()

    def toggle_waypoint_mode(self, enable: bool):
        self.bridge.toggleWaypointMode.emit(enable)

    def toggle_fence_mode(self, enable: bool):
        self.bridge.toggleFenceMode.emit(enable)

    def toggle_insert_mode(self, enable: bool):
        self.bridge.toggleInsertMode.emit(enable)
