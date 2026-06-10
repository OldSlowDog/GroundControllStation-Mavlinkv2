"""
地图控件组件
封装 QWebEngineView + Leaflet.js，提供 Python-JavaScript 双向通信桥
"""

import os
import json
from PyQt5.QtWidgets import QWidget, QVBoxLayout
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QUrl
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebChannel import QWebChannel


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
    exportData = pyqtSignal(str)

    # ===== 内部信号 (桥接用) =====
    waypoint_added = pyqtSignal(int, float, float)       # index, lat, lon
    waypoint_moved = pyqtSignal(int, float, float)       # index, lat, lon
    waypoint_deleted = pyqtSignal(int)                    # index
    waypoint_edited = pyqtSignal(dict)                   # ★ 编辑数据字典
    fence_point_added = pyqtSignal(float, float)         # lat, lon
    geofence_created = pyqtSignal(dict)                  # geofence data
    map_clicked = pyqtSignal(float, float)               # lat, lon (通用点击)
    data_exported = pyqtSignal(dict)                     # exported data
    location_searched = pyqtSignal(float, float, str)    # lat, lng, name (地点搜索)

    # ===== 槽函数 (JavaScript → Python) ★ 关键修复！=====
    @pyqtSlot(int, float, float)
    def addWaypoint(self, index: int, lat: float, lon: float):
        """JS端调用：添加航点"""
        print(f"[MapBridge] addWaypoint called: {index}, {lat:.6f}, {lon:.6f}")
        self.waypoint_added.emit(index, lat, lon)

    @pyqtSlot(int, float, float)
    def moveWaypoint(self, index: int, lat: float, lon: float):
        """JS端调用：移动航点"""
        print(f"[MapBridge] moveWaypoint called: {index}, {lat:.6f}, {lon:.6f}")
        self.waypoint_moved.emit(index, lat, lon)

    @pyqtSlot(int)
    def deleteWaypoint(self, index: int):
        """JS端调用：删除航点"""
        print(f"[MapBridge] deleteWaypoint called: {index}")
        self.waypoint_deleted.emit(index)

    @pyqtSlot(float, float)
    def addFencePoint(self, lat: float, lon: float):
        """JS端调用：添加围栏点"""
        print(f"[MapBridge] addFencePoint called: {lat:.6f}, {lon:.6f}")
        self.fence_point_added.emit(lat, lon)

    @pyqtSlot('QVariant')
    def createGeofence(self, jsonStr):
        """JS端调用：创建围栏（Qt WebChannel可能自动反序列化JSON）"""
        print(f"[MapBridge] createGeofence called, type={type(jsonStr).__name__}")
        try:
            import json
            # ★ Qt WebChannel 可能自动将JSON字符串反序列化为Python对象
            if isinstance(jsonStr, (list, dict)):
                data = jsonStr  # 已经是对象，直接使用
            elif isinstance(jsonStr, str):
                data = json.loads(jsonStr)  # 字符串需要解析
            else:
                data = []
            self.geofence_created.emit(data)
        except Exception as e:
            print(f"[MapBridge] Error parsing geofence: {e}")

    @pyqtSlot('QVariant')
    def editWaypoint(self, jsonStr):
        """★ JS端调用：编辑航点（任务类型、高度、速度等）"""
        print(f"[MapBridge] editWaypoint called")
        try:
            import json
            if isinstance(jsonStr, (list, dict)):
                data = jsonStr
            elif isinstance(jsonStr, str):
                data = json.loads(jsonStr)
            else:
                data = {}
            print(f"[MapBridge] Edit data: {data}")
            self.waypoint_edited.emit(data)
        except Exception as e:
            print(f"[MapBridge] Error parsing edit data: {e}")

    @pyqtSlot(float, float, str)
    def locationSearched(self, lat: float, lng: float, name: str):
        """JS端调用：地点搜索结果选中"""
        print(f"[MapBridge] Location searched: {name} ({lat:.6f}, {lng:.6f})")
        self.location_searched.emit(lat, lng, name)

    segment_edited = pyqtSignal(str)

    @pyqtSlot('QVariant')
    def segmentEdited(self, jsonStr):
        """JS端调用：航段参数编辑（速度/高度）"""
        print(f"[MapBridge] Segment edited, type={type(jsonStr).__name__}")
        try:
            import json
            if isinstance(jsonStr, (list, dict)):
                data = jsonStr
            elif isinstance(jsonStr, str):
                data = json.loads(jsonStr)
            else:
                data = {}
            self.segment_edited.emit(json.dumps(data) if not isinstance(data, str) else jsonStr)
            print(f"[MapBridge] Segment data: {data}")
        except Exception as e:
            print(f"[MapBridge] Error parsing segment data: {e}")

    searchResults = pyqtSignal(str)  # 搜索结果JSON字符串 → JS

    @pyqtSlot(str)
    def searchPlace(self, keyword: str):
        """JS端调用：地点搜索（Python端签名+请求WebService API）"""
        import hashlib
        import urllib.parse
        try:
            from urllib.request import urlopen
        except ImportError:
            from urllib2 import urlopen

        KEY = 'HXLBZ-OJLWW-B2KR5-335LE-BB6XH-RIFCX'
        SK = '5yX0hX9OXHNekXcbB03e6Fh97swtSUG6'
        
        params = {
            'key': KEY,
            'keyword': keyword,
            'boundary': 'nearby(39.9042,116.4074,50000,1)',
            'page_size': 10,
            'output': 'json'
        }
        
        path = '/ws/place/v1/search'
        param_str = '&'.join(f"{k}={v}" for k, v in sorted(params.items()))
        str_to_sign = f"{path}?{param_str}{SK}"
        sig = hashlib.md5(str_to_sign.encode('utf-8')).hexdigest()
        
        encoded_params = '&'.join(
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
            for k, v in sorted(params.items())
        )
        url = f"https://apis.map.qq.com{path}?{encoded_params}&sig={sig}"
        
        try:
            req = urllib.request.Request(url)
            resp = urlopen(req, timeout=5)
            data = resp.read().decode('utf-8')
            self.searchResults.emit(data)
            print(f"[MapBridge] Search '{keyword}': got results")
        except Exception as e:
            err_msg = str(e).replace('"', '').replace("'", '')
            err_json = '{"status":-1,"message":"' + err_msg + '"}'
            self.searchResults.emit(err_json)
            print(f"[MapBridge] Search error: {e}")


class MapWidget(QWidget):
    """
    地图显示控件
    
    功能特性：
    1. OpenStreetMap 底图（支持在线/离线瓦片）
    2. 实时无人机位置追踪（带航向指示）
    3. 飞行轨迹记录和显示
    4. 航点规划（点击添加、拖拽移动、右键删除）
    5. 地理围栏（圆形/多边形）
    
    使用示例：
        widget = MapWidget()
        widget.update_drone(39.9042, 116.4074, heading=180.0, alt=100.0)
        widget.add_waypoint(39.91, 116.42, alt=50.0)
    """

    waypoint_added = pyqtSignal(int, float, float)  # index, lat, lon
    waypoint_moved = pyqtSignal(int, float, float)  # index, lat, lon
    waypoint_deleted = pyqtSignal(int)               # index
    waypoint_edited = pyqtSignal(dict)              # ★ 编辑数据字典
    fence_point_added = pyqtSignal(float, float)     # ★ 新增：lat, lon (围栏点)
    geofence_created = pyqtSignal(dict)              # geofence data
    map_clicked = pyqtSignal(float, float)           # lat, lon (通用点击)
    data_exported = pyqtSignal(dict)                 # exported data
    location_searched = pyqtSignal(float, float, str)  # lat, lng, name (地点搜索)
    segment_edited = pyqtSignal(str)                   # 航段编辑数据JSON

    def __init__(self, parent=None):
        super().__init__(parent)

        self.bridge = MapBridge()

        self._setup_ui()
        self._setup_channel()
        self._connect_signals()  # ★ 连接内部桥接信号

        self._is_loaded = False

    def _setup_ui(self):
        """初始化UI布局"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.web_view = QWebEngineView()
        layout.addWidget(self.web_view)

        html_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'resources', 'map', 'map.html'
        )
        self.web_view.load(QUrl.fromLocalFile(html_path))

        self.web_view.loadFinished.connect(self._on_page_loaded)

    def _setup_channel(self):
        """设置WebChannel通信通道"""
        self.channel = QWebChannel()
        self.channel.registerObject('bridge', self.bridge)
        
        page = self.web_view.page()
        page.setWebChannel(self.channel)
        
        # ★ 关键：自动批准Geolocation权限请求
        page.featurePermissionRequested.connect(
            self._on_feature_permission_requested
        )

    def _connect_signals(self):
        """★ 连接Bridge内部信号到MapWidget的外部信号"""
        # Bridge的槽函数被JS调用后，会emit这些内部信号
        # 我们将这些内部信号连接到MapWidget的外部信号
        self.bridge.waypoint_added.connect(lambda idx, lat, lon: self.waypoint_added.emit(idx, lat, lon))
        self.bridge.waypoint_moved.connect(lambda idx, lat, lon: self.waypoint_moved.emit(idx, lat, lon))
        self.bridge.waypoint_deleted.connect(lambda idx: self.waypoint_deleted.emit(idx))
        self.bridge.waypoint_edited.connect(lambda data: self.waypoint_edited.emit(data))  # ★ 新增
        self.bridge.fence_point_added.connect(lambda lat, lon: self.fence_point_added.emit(lat, lon))
        self.bridge.geofence_created.connect(lambda data: self.geofence_created.emit(data))
        self.bridge.location_searched.connect(lambda lat, lng, name: self.location_searched.emit(lat, lng, name))
        self.bridge.segment_edited.connect(lambda data: self.segment_edited.emit(data))
        self.bridge.searchResults.connect(self._on_search_results)

    def _on_page_loaded(self, ok):
        """页面加载完成回调"""
        if ok:
            self._is_loaded = True
            print("[Map] Page loaded successfully")
        else:
            print("[Map] ERROR: Failed to load map page")

    def _on_feature_permission_requested(self, security_origin, feature):
        """
        ★ 处理浏览器功能权限请求（Geolocation等）
        
        Args:
            security_origin: 请求来源 (QUrl)
            feature: 请求的功能类型 (QWebEnginePage::Feature)
        """
        from PyQt5.QtWebEngineWidgets import QWebEnginePage
        
        print(f"[Map] Permission requested: {feature} from {security_origin}")
        
        # 自动批准地理位置权限
        if feature == QWebEnginePage.Feature.Geolocation:
            print("[Map] Geolocation permission GRANTED")
            self.web_view.page().setFeaturePermission(
                security_origin,
                feature,
                QWebEnginePage.PermissionGrantedByUser
            )
        # 其他权限也自动批准（通知、媒体设备等）
        elif feature in [QWebEnginePage.Feature.Notifications,
                        QWebEnginePage.Feature.MediaAudioCapture,
                        QWebEnginePage.Feature.MediaVideoCapture]:
            print(f"[Map] Permission granted for: {feature}")
            self.web_view.page().setFeaturePermission(
                security_origin,
                feature,
                QWebEnginePage.PermissionGrantedByUser
            )
        else:
            # 其他未知权限拒绝
            print(f"[Map] Permission denied for: {feature}")
            self.web_view.page().setFeaturePermission(
                security_origin,
                feature,
                QWebEnginePage.PermissionDeniedByUser
            )

    def _run_js(self, script: str):
        """安全执行JavaScript代码（异步）"""
        if self._is_loaded:
            self.web_view.page().runJavaScript(script)

    def _run_js_sync(self, script: str):
        """
        ★ 同步执行JavaScript代码并返回结果

        使用QEventLoop阻塞等待JS执行完成，适用于需要获取返回值的场景
        （如GPS面板切换状态查询）

        Args:
            script: JavaScript代码字符串

        Returns:
            JS执行结果（任意类型），如果出错则返回None
        """
        if not self._is_loaded:
            print("[MapWidget] Warning: Page not loaded yet")
            return None

        from PyQt5.QtCore import QEventLoop

        result = [None]  # 使用列表以便在闭包中修改
        loop = QEventLoop()

        def on_result(r):
            result[0] = r
            loop.quit()

        self.web_view.page().runJavaScript(script, on_result)
        loop.exec_()  # 阻塞等待结果

        return result[0]


    def update_drone_position(self, lat: float, lon: float,
                               heading: float = 0.0, alt: float = 0.0):
        """
        更新无人机位置
        
        Args:
            lat: 纬度
            lon: 经度
            heading: 航向角（度）
            alt: 高度（米）
        """
        script = f"if(window.inavMap) {{ window.inavMap.updateDronePosition({lat}, {lon}, {heading}, {alt}); }}"
        self._run_js(script)

    def update_gps_info(self, lat: float, lon: float, alt: float,
                        speed: float = 0.0, sats: int = 0, fix_type: int = 0):
        """
        更新GPS信息面板
        
        Args:
            lat: 纬度
            lon: 经度
            alt: GPS高度（米）
            speed: 速度（m/s）
            sats: 卫星数量
            fix_type: 定位类型 (0=NoFix, 1=2D, 2=3D, 3=DGPS)
        """
        self.bridge.updateGPSInfo.emit(lat, lon, alt, speed, sats, fix_type)

    def set_center(self, lat: float, lon: float, zoom: int = 15):
        """设置地图中心点"""
        self.bridge.setMapCenter.emit(lat, lon, zoom)

    def clear_track(self):
        """清除飞行轨迹"""
        self._run_js("if(window.inavMap) { window.inavMap.clearTrack(); }")

    def clear_waypoints(self):
        """清除所有航点"""
        self.bridge.clearWaypoints.emit()

    def add_waypoint(self, lat: float, lon: float, index: int = None):
        """
        从Python端添加航点
        
        Args:
            lat: 纬度
            lon: 经度
            index: 可选，指定索引位置
        """
        if index is not None:
            script = f"if(window.inavMap) {{ window.inavMap.addWaypoint({lat}, {lon}, {index}); }}"
        else:
            script = f"if(window.inavMap) {{ window.inavMap.addWaypoint({lat}, {lon}); }}"
        self._run_js(script)

    def load_waypoints(self, waypoints: list):
        """
        批量加载航点
        
        Args:
            waypoints: [{'lat': float, 'lon': float}, ...]
        """
        json_str = json.dumps(waypoints)
        self.bridge.loadWaypoints.emit(json_str)

    def get_waypoints(self) -> list:
        """获取当前所有航点坐标"""
        return []

    def add_geofence_circle(self, lat: float, lon: float, radius: float):
        """添加圆形地理围栏"""
        fence_data = json.dumps([{
            'type': 'circle',
            'center': [lat, lon],
            'radius': radius
        }])
        self.bridge.loadGeofence.emit(fence_data)

    def add_geofence_polygon(self, points: list):
        """
        添加多边形地理围栏
        
        Args:
            points: [[lat, lon], ...] 至少3个点
        """
        fence_data = json.dumps([{
            'type': 'polygon',
            'points': points
        }])
        self.bridge.loadGeofence.emit(fence_data)

    def export_all_data(self) -> dict:
        """导出所有地图数据（轨迹+航点+围栏）"""
        return {}

    def add_waypoint(self, lat: float, lon: float, index: int = None):
        """
        ★ 公开方法：在地图上添加单个航点（用于撤销/复原）
           直接调用JS的addWaypoint方法，不会清除其他航点！

        Args:
            lat: 纬度
            lon: 经度
            index: 航点索引（可选，如果不提供则自动计算）
        """
        if index is None:
            # 如果没有提供索引，获取当前航点数量作为索引
            index = len(self.bridge._parent().waypoint_manager.waypoints) if hasattr(self.bridge, '_parent') else 0

        # ★ 直接调用JS的addWaypoint方法（不经过loadWaypoints，避免清除其他点）
        js_code = f"if(window.inavMap) {{ window.inavMap.addWaypoint({lat}, {lon}, {index}); }}"
        self._run_js(js_code)

    def load_geofence(self, fences):
        """
        ★ 公开方法：加载围栏到地图（用于撤销/复原）
        直接调用JS端的 loadGeofence() 方法绘制多边形
        """
        import json
        fence_data = [f.to_dict() for f in fences]
        json_str = json.dumps(fence_data)
        self._run_js(f"if(window.inavMap) {{ window.inavMap.loadGeofence({json_str}); }}")

    def search_location(self, keyword: str):
        """★ 从Python端触发地点搜索"""
        import json
        escaped = keyword.replace("'", "\\'").replace('"', '\\"')
        self._run_js(f"if(window.inavMap) {{ window.inavMap.searchLocation('{escaped}'); }}")

    def _on_search_results(self, json_str: str):
        """★ 接收Python端搜索结果，转发给JS渲染"""
        import json
        escaped = json_str.replace('\\', '\\\\').replace("'", "\\'")
        self._run_js(f"if(window.inavMap) {{ window.inavMap.renderSearchResults('{escaped}'); }}")

