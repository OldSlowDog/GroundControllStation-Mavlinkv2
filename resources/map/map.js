/* ============================================================
 * GCS Map — Leaflet.js + OpenStreetMap（无需 API Key）
 *
 * Python ↔ JavaScript 通信接口（通过 Qt WebChannel / window.bridge）
 *   Python → JS（信号）:
 *     updateDronePosition(lat, lng, alt, heading)
 *     updateGPSInfo(fix, sats, lat, lng, alt, speed, heading)
 *     clearWaypoints()
 *     loadWaypoints(jsonStr)        [{index,lat,lng,alt,speed,task}, ...]
 *     loadGeofence(jsonStr)          {points:[{lat,lng},...], action, name}
 *     setMapCenter(lat, lng, zoom)
 *     centerOnDrone()
 *     clearTrack()
 *     toggleWaypointMode(enable)
 *     toggleFenceMode(enable)
 *     toggleInsertMode(enable)
 *     exportData()
 *     searchResults(jsonStr)         [{display_name,lat,lon}, ...]
 *
 *   JS → Python（槽函数）:
 *     bridge.addWaypoint(index, lat, lng)
 *     bridge.moveWaypoint(index, lat, lng)
 *     bridge.deleteWaypoint(index)
 *     bridge.addFencePoint(lat, lng)
 *     bridge.createGeofence(jsonStr)
 *     bridge.editWaypoint(jsonStr)
 *     bridge.locationSearched(lat, lng, name)
 *     bridge.segmentEdited(jsonStr)
 *     bridge.searchPlace(keyword)
 * ============================================================ */

/* 全局入口：等页面和 Qt WebChannel 都准备好再初始化 */
window.addEventListener('load', function () {
    // 创建桥对象；Py 端会在 Qt WebChannel 就绪后注入 window.bridge
    new QWebChannel(qt.webChannelTransport, function (channel) {
        window.bridge = channel.objects.bridge;
        window.gcsMap = new INAVMap();
        window.gcsMap.initBridge();
    });
});

/* ============================================================
 * INAVMap — 地图与图层管理
 * ============================================================ */
function INAVMap() {
    this.map = null;
    this.baseLayer = null;

    // 图层容器
    this.waypointLayer = L.layerGroup();     // 航点 marker
    this.waypointLabelLayer = L.layerGroup(); // 航点标签
    this.lineLayer = L.layerGroup();         // 航线 polyline
    this.segmentLabelLayer = L.layerGroup(); // 航段标签
    this.fenceMarkerLayer = L.layerGroup();  // 围栏 marker
    this.fenceLineLayer = L.layerGroup();    // 围栏线
    this.fencePolyLayer = L.layerGroup();    // 围栏面
    this.droneLayer = L.layerGroup();        // 无人机位置
    this.trackLayer = L.layerGroup();        // 飞行轨迹
    this.searchMarkerLayer = L.layerGroup(); // 搜索结果

    // 数据缓存
    this.waypoints = [];       // [{index,lat,lng,alt,speed,task,marker,label}]
    this.lines = [];           // L.polyline 对象数组
    this.fencePoints = [];     // [{lat,lng,marker}]
    this.fenceClosed = false;
    this.dronePos = null;      // {lat,lng}
    this.droneMarker = null;
    this.trackPoints = [];     // 轨迹经纬度数组

    // 模式标志
    this.waypointMode = false;
    this.fenceMode = false;
    this.insertMode = false;

    this.initMap();
    this.initLayers();
    this.initInteraction();
    this.initGPSPanel();
    this.initSearchBox();
}

/* ---------- 初始化 ---------- */
INAVMap.prototype.initMap = function () {
    // 默认中心：北京天安门
    this.map = L.map('map', {
        center: [39.9042, 116.4074],
        zoom: 12,
        zoomControl: true,
        attributionControl: true
    });

    // 底图：OpenStreetMap 标准瓦片（完全免费，无需 Key）
    // 可按需替换为 Esri / 高德栅格 / 天地图等其他免费源
    this.baseLayer = L.tileLayer(
        'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        {
            maxZoom: 19,
            subdomains: 'abc',
            attribution:
                '&copy; <a href="https://www.openstreetmap.org/copyright">' +
                'OpenStreetMap</a> contributors',
            crossOrigin: true
        }
    ).addTo(this.map);
};

INAVMap.prototype.initLayers = function () {
    this.waypointLayer.addTo(this.map);
    this.waypointLabelLayer.addTo(this.map);
    this.lineLayer.addTo(this.map);
    this.segmentLabelLayer.addTo(this.map);
    this.fenceMarkerLayer.addTo(this.map);
    this.fenceLineLayer.addTo(this.map);
    this.fencePolyLayer.addTo(this.map);
    this.droneLayer.addTo(this.map);
    this.trackLayer.addTo(this.map);
    this.searchMarkerLayer.addTo(this.map);
};

/* ---------- 点击交互 ---------- */
INAVMap.prototype.initInteraction = function () {
    var self = this;

    // 普通点击：根据当前模式添加航点或围栏点
    this.map.on('click', function (e) {
        if (self.insertMode && self.waypoints.length >= 2) {
            // 插入模式：在最近的航段中点插入新航点
            self._insertWaypointAt(e.latlng);
            return;
        }
        if (self.waypointMode) {
            self._addWaypoint(e.latlng.lat, e.latlng.lng);
            return;
        }
        if (self.fenceMode) {
            self._addFencePoint(e.latlng.lat, e.latlng.lng);
            return;
        }
    });
};

/* ---------- GPS 面板 ---------- */
INAVMap.prototype.initGPSPanel = function () {
    // 面板 DOM 已在 HTML 中存在，这里只负责显示/隐藏
};

/* ---------- 搜索框 ---------- */
INAVMap.prototype.initSearchBox = function () {
    var self = this;
    var input = document.getElementById('search-input');
    var btn = document.getElementById('search-btn');
    var resultsDiv = document.getElementById('search-results');

    function doSearch() {
        var kw = input.value.trim();
        if (!kw) return;
        resultsDiv.innerHTML = '<div class="search-item">搜索中...</div>';
        resultsDiv.classList.remove('hidden');
        // 调用 Python 端 Nominatim 搜索后端
        if (window.bridge && window.bridge.searchPlace) {
            window.bridge.searchPlace(kw);
        }
    }

    btn.addEventListener('click', doSearch);
    input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') doSearch();
    });
    input.addEventListener('focus', function () {
        resultsDiv.classList.remove('hidden');
    });

    // 点击地图其它位置时收起
    this.map.on('click', function () {
        resultsDiv.classList.add('hidden');
    });
};

/* ============================================================
 * 航点管理
 * ============================================================ */

/* Python 传入：loadWaypoints(jsonStr) */
INAVMap.prototype.loadWaypoints = function (jsonStr) {
    try {
        var data = JSON.parse(jsonStr);
        this.clearWaypoints();
        if (!data || !data.length) return;
        for (var i = 0; i < data.length; i++) {
            var wp = data[i];
            this._createWaypointMarker(wp.index, wp.lat, wp.lng, wp);
        }
        this.redrawLines();
        this._fitToWaypoints();
    } catch (e) {
        console.error('[Map] loadWaypoints parse error:', e);
    }
};

INAVMap.prototype.clearWaypoints = function () {
    this.waypointLayer.clearLayers();
    this.waypointLabelLayer.clearLayers();
    this.lineLayer.clearLayers();
    this.segmentLabelLayer.clearLayers();
    this.waypoints = [];
    this.lines = [];
};

INAVMap.prototype._addWaypoint = function (lat, lng) {
    var index = this.waypoints.length;
    this._createWaypointMarker(index, lat, lng, {
        alt: 100, speed: 10, task: 'GOTO'
    });
    this.redrawLines();
    // 通知 Python
    if (window.bridge) window.bridge.addWaypoint(index, lat, lng);
};

INAVMap.prototype._createWaypointMarker = function (index, lat, lng, data) {
    var self = this;
    var icon = L.divIcon({
        className: 'wp-marker',
        html: '<div class="wp-dot"></div>',
        iconSize: [18, 18],
        iconAnchor: [9, 9]
    });

    var marker = L.marker([lat, lng], {
        icon: icon,
        draggable: true
    }).addTo(this.waypointLayer);

    // 标签（编号）
    var label = L.marker([lat, lng], {
        icon: L.divIcon({
            className: 'wp-label',
            html: '<div class="wp-num">WP' + (index + 1) + '</div>',
            iconSize: [40, 20],
            iconAnchor: [20, 28]
        }),
        interactive: false
    }).addTo(this.waypointLabelLayer);

    var wpObj = {
        index: index,
        lat: lat,
        lng: lng,
        alt: data.alt || 100,
        speed: data.speed || 10,
        task: data.task || 'GOTO',
        marker: marker,
        label: label
    };
    this.waypoints.push(wpObj);

    // 拖拽结束：更新坐标 + 重绘连线
    marker.on('dragend', function () {
        var pos = marker.getLatLng();
        wpObj.lat = pos.lat;
        wpObj.lng = pos.lng;
        label.setLatLng(pos);
        self.redrawLines();
        if (window.bridge) window.bridge.moveWaypoint(index, pos.lat, pos.lng);
    });

    // 点击航点：弹出编辑窗口
    marker.on('click', function (e) {
        L.DomEvent.stopPropagation(e);
        self._showWaypointEditor(wpObj);
    });

    return wpObj;
};

/* 找到距离点击位置最近的航段，在该段中点插入 */
INAVMap.prototype._insertWaypointAt = function (clickLatLng) {
    var self = this;
    var minDist = Infinity;
    var insertAfter = -1;
    var clickPt = this.map.latLngToContainerPoint(clickLatLng);

    for (var i = 0; i < this.waypoints.length - 1; i++) {
        var a = this.map.latLngToContainerPoint(
            L.latLng(this.waypoints[i].lat, this.waypoints[i].lng));
        var b = this.map.latLngToContainerPoint(
            L.latLng(this.waypoints[i + 1].lat, this.waypoints[i + 1].lng));
        var mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
        var d = Math.hypot(mid.x - clickPt.x, mid.y - clickPt.y);
        if (d < minDist) { minDist = d; insertAfter = i; }
    }

    if (insertAfter < 0 || minDist > 35) {  // 25~50 像素吸附半径
        // 没找到近段，退化为普通添加
        this._addWaypoint(clickLatLng.lat, clickLatLng.lng);
        return;
    }

    // 实际插入点：在 (insertAfter, insertAfter+1) 之间的中点
    var midLat = (this.waypoints[insertAfter].lat + this.waypoints[insertAfter + 1].lat) / 2;
    var midLng = (this.waypoints[insertAfter].lng + this.waypoints[insertAfter + 1].lng) / 2;

    // 重建所有航点（因为 index 需要连续）
    var old = this.waypoints.slice();
    this.clearWaypoints();
    for (var j = 0; j < old.length; j++) {
        var w = old[j];
        this._createWaypointMarker(j, w.lat, w.lng, {
            alt: w.alt, speed: w.speed, task: w.task
        });
        if (j === insertAfter) {
            // 新插入点
            this._createWaypointMarker(j + 1, midLat, midLng, {
                alt: (old[j].alt + old[j + 1].alt) / 2,
                speed: (old[j].speed + old[j + 1].speed) / 2,
                task: 'GOTO'
            });
        }
    }
    this.redrawLines();
    if (window.bridge) window.bridge.addWaypoint(insertAfter + 1, midLat, midLng);
};

/* 重绘航线 + 航段标签 */
INAVMap.prototype.redrawLines = function () {
    this.lineLayer.clearLayers();
    this.segmentLabelLayer.clearLayers();

    if (this.waypoints.length < 2) return;

    for (var i = 0; i < this.waypoints.length - 1; i++) {
        var a = this.waypoints[i];
        var b = this.waypoints[i + 1];
        var latlngs = [[a.lat, a.lng], [b.lat, b.lng]];
        var line = L.polyline(latlngs, {
            color: '#00d4ff', weight: 3, opacity: 0.85, dashArray: '6,4'
        }).addTo(this.lineLayer);

        // 航段标签（速度 + 高度）
        var segMid = {
            lat: (a.lat + b.lat) / 2,
            lng: (a.lng + b.lng) / 2
        };
        var dist = this._haversine(a.lat, a.lng, b.lat, b.lng);
        L.marker([segMid.lat, segMid.lng], {
            icon: L.divIcon({
                className: 'seg-label',
                html: '<div class="seg-text">S' + (i + 1) +
                      ' ' + dist.toFixed(1) + 'm<br/>' +
                      b.alt.toFixed(0) + 'm / ' + b.speed.toFixed(0) + 'm/s</div>',
                iconSize: [80, 30],
                iconAnchor: [40, 15]
            }),
            interactive: true
        }).on('click', function (e) {
            L.DomEvent.stopPropagation(e);
        }).addTo(this.segmentLabelLayer);
    }
};

INAVMap.prototype._haversine = function (lat1, lng1, lat2, lng2) {
    var R = 6371000;
    var toRad = Math.PI / 180;
    var dLat = (lat2 - lat1) * toRad;
    var dLng = (lng2 - lng1) * toRad;
    var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(lat1 * toRad) * Math.cos(lat2 * toRad) *
            Math.sin(dLng / 2) * Math.sin(dLng / 2);
    var c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
};

INAVMap.prototype._fitToWaypoints = function () {
    if (this.waypoints.length === 0) return;
    var bounds = L.latLngBounds(this.waypoints.map(function (w) {
        return [w.lat, w.lng];
    }));
    this.map.fitBounds(bounds.pad(0.25));
};

/* 航点编辑器（popup） */
INAVMap.prototype._showWaypointEditor = function (wpObj) {
    var self = this;
    var html =
        '<div class="popup">' +
        '<div class="popup-title">航点 WP' + (wpObj.index + 1) + '</div>' +
        '<div class="popup-row"><label>任务类型</label>' +
          '<select id="pop-task">' +
            '<option value="TAKEOFF"' + (wpObj.task === 'TAKEOFF' ? ' selected' : '') + '>TAKEOFF</option>' +
            '<option value="GOTO"' + ((!wpObj.task || wpObj.task === 'GOTO') ? ' selected' : '') + '>GOTO</option>' +
            '<option value="HOVER"' + (wpObj.task === 'HOVER' ? ' selected' : '') + '>HOVER</option>' +
            '<option value="LAND"' + (wpObj.task === 'LAND' ? ' selected' : '') + '>LAND</option>' +
            '<option value="CUSTOM"' + (wpObj.task === 'CUSTOM' ? ' selected' : '') + '>CUSTOM</option>' +
          '</select></div>' +
        '<div class="popup-row"><label>高度 (m)</label>' +
          '<input type="number" id="pop-alt" step="1" value="' + wpObj.alt.toFixed(0) + '"/></div>' +
        '<div class="popup-row"><label>速度 (m/s)</label>' +
          '<input type="number" id="pop-speed" step="0.5" value="' + wpObj.speed.toFixed(1) + '"/></div>' +
        '<div class="popup-btns">' +
          '<button id="pop-save">保存</button>' +
          '<button id="pop-del" style="background:#c33;">删除</button>' +
        '</div></div>';

    var popup = L.popup({ maxWidth: 260, minWidth: 240 })
        .setLatLng([wpObj.lat, wpObj.lng])
        .setContent(html)
        .openOn(this.map);

    // 等待 DOM 渲染后绑定按钮
    setTimeout(function () {
        var btnSave = document.getElementById('pop-save');
        var btnDel = document.getElementById('pop-del');
        if (btnSave) btnSave.onclick = function () {
            var t = document.getElementById('pop-task').value;
            var a = parseFloat(document.getElementById('pop-alt').value) || wpObj.alt;
            var s = parseFloat(document.getElementById('pop-speed').value) || wpObj.speed;
            wpObj.task = t; wpObj.alt = a; wpObj.speed = s;
            self.redrawLines();
            if (window.bridge) {
                var data = {
                    index: wpObj.index, lat: wpObj.lat, lng: wpObj.lng,
                    alt: wpObj.alt, speed: wpObj.speed, task: wpObj.task
                };
                window.bridge.editWaypoint(JSON.stringify(data));
            }
            self.map.closePopup();
        };
        if (btnDel) btnDel.onclick = function () {
            self._deleteWaypoint(wpObj.index);
            self.map.closePopup();
        };
    }, 50);
};

INAVMap.prototype._deleteWaypoint = function (index) {
    // 重建（简单方式）
    var old = this.waypoints.filter(function (w) { return w.index !== index; });
    this.clearWaypoints();
    for (var i = 0; i < old.length; i++) {
        var w = old[i];
        this._createWaypointMarker(i, w.lat, w.lng, {
            alt: w.alt, speed: w.speed, task: w.task
        });
    }
    this.redrawLines();
    if (window.bridge) window.bridge.deleteWaypoint(index);
};

/* ============================================================
 * 围栏管理
 * ============================================================ */

INAVMap.prototype.loadGeofence = function (jsonStr) {
    try {
        var data = JSON.parse(jsonStr);
        this.clearGeofence();
        if (!data || !data.points || data.points.length < 3) return;
        for (var i = 0; i < data.points.length; i++) {
            var p = data.points[i];
            this._createFenceMarker(p.lat, p.lng);
        }
        this._redrawFence(true);
    } catch (e) {
        console.error('[Map] loadGeofence parse error:', e);
    }
};

INAVMap.prototype.clearGeofence = function () {
    this.fenceMarkerLayer.clearLayers();
    this.fenceLineLayer.clearLayers();
    this.fencePolyLayer.clearLayers();
    this.fencePoints = [];
    this.fenceClosed = false;
};

INAVMap.prototype._addFencePoint = function (lat, lng) {
    // 检查是否点到首个点（封闭围栏）
    if (this.fencePoints.length >= 3) {
        var first = this.fencePoints[0];
        var d = this._haversine(first.lat, first.lng, lat, lng);
        if (d < 50) {
            // 50 米内点击视为封闭
            this._closeFence();
            return;
        }
    }
    this._createFenceMarker(lat, lng);
    this._redrawFence(false);
    if (window.bridge) window.bridge.addFencePoint(lat, lng);
};

INAVMap.prototype._createFenceMarker = function (lat, lng) {
    var self = this;
    var marker = L.circleMarker([lat, lng], {
        radius: 7,
        color: '#ff5555',
        fillColor: '#ff5555',
        fillOpacity: 0.9,
        weight: 2
    }).addTo(this.fenceMarkerLayer);

    this.fencePoints.push({ lat: lat, lng: lng, marker: marker });

    marker.on('click', function (e) {
        L.DomEvent.stopPropagation(e);
        // 点击第一个点 → 封闭
        if (self.fencePoints.length >= 3 &&
            self.fencePoints[0] === self.fencePoints[self.fencePoints.length - 1] ?
            false : self.fencePoints[0].marker === marker) {
            self._closeFence();
        }
    });
};

INAVMap.prototype._redrawFence = function (closed) {
    this.fenceLineLayer.clearLayers();
    this.fencePolyLayer.clearLayers();

    if (this.fencePoints.length === 0) return;

    var latlngs = this.fencePoints.map(function (p) { return [p.lat, p.lng]; });

    if (closed && latlngs.length >= 3) {
        // 封闭围栏：画多边形
        L.polygon(latlngs, {
            color: '#ff5555', fillColor: '#ff8888',
            fillOpacity: 0.25, weight: 2
        }).addTo(this.fencePolyLayer);
        this.fenceClosed = true;
    } else {
        // 未封闭：画折线
        L.polyline(latlngs, {
            color: '#ff5555', weight: 2, opacity: 0.9
        }).addTo(this.fenceLineLayer);
    }
};

INAVMap.prototype._closeFence = function () {
    if (this.fencePoints.length < 3) return;
    this._redrawFence(true);
    if (window.bridge) {
        var data = {
            points: this.fencePoints.map(function (p) { return { lat: p.lat, lng: p.lng }; }),
            action: 'keep_out',
            name: 'Geofence_' + Date.now()
        };
        window.bridge.createGeofence(JSON.stringify(data));
    }
    this._toast('✓ 围栏已创建 (' + this.fencePoints.length + ' 点)');
};

/* ============================================================
 * 无人机位置与轨迹
 * ============================================================ */

INAVMap.prototype.updateDronePosition = function (lat, lng, alt, heading) {
    if (!this.droneMarker) {
        // 三角形箭头（带航向）
        var self = this;
        this.droneMarker = L.marker([lat, lng], {
            icon: L.divIcon({
                className: 'drone-marker',
                html: '<div class="drone-arrow"></div>',
                iconSize: [28, 28],
                iconAnchor: [14, 14]
            }),
            interactive: false,
            zIndexOffset: 1000
        }).addTo(this.droneLayer);
    }
    this.droneMarker.setLatLng([lat, lng]);
    // 旋转箭头
    var el = this.droneMarker.getElement();
    if (el && typeof heading === 'number') {
        var arrow = el.querySelector('.drone-arrow');
        if (arrow) arrow.style.transform = 'rotate(' + heading + 'deg)';
    }
    this.dronePos = { lat: lat, lng: lng };

    // 轨迹点
    this.trackPoints.push([lat, lng]);
    if (this.trackPoints.length > 2000) this.trackPoints.shift();
    this._redrawTrack();
};

INAVMap.prototype._redrawTrack = function () {
    this.trackLayer.clearLayers();
    if (this.trackPoints.length < 2) return;
    L.polyline(this.trackPoints, {
        color: '#ffaa00', weight: 2, opacity: 0.7
    }).addTo(this.trackLayer);
};

INAVMap.prototype.clearTrack = function () {
    this.trackPoints = [];
    this.trackLayer.clearLayers();
};

INAVMap.prototype.centerOnDrone = function () {
    if (this.dronePos) this.map.panTo([this.dronePos.lat, this.dronePos.lng]);
};

/* ============================================================
 * GPS 信息面板（由 Python 端注入）
 * ============================================================ */

INAVMap.prototype.updateGPSInfo = function (fix, sats, lat, lng, alt, speed, heading) {
    var panel = document.getElementById('gps-panel');
    if (!panel) return;
    panel.classList.remove('hidden');

    var setTxt = function (id, val) {
        var el = document.getElementById(id);
        if (el) el.textContent = (val === undefined || val === null || val === '') ? '—' : val;
    };

    var fixText = ['无定位', '仅定位', '2D 定位', '3D 定位', 'DGPS', 'RTK 浮点', 'RTK 固定'][fix] || '—';

    setTxt('gps-fix', fixText);
    setTxt('gps-sats', sats);
    setTxt('gps-lat', (typeof lat === 'number' ? lat.toFixed(6) : lat));
    setTxt('gps-lng', (typeof lng === 'number' ? lng.toFixed(6) : lng));
    setTxt('gps-alt', (typeof alt === 'number' ? alt.toFixed(1) + ' m' : alt));
    setTxt('gps-speed', (typeof speed === 'number' ? speed.toFixed(1) + ' m/s' : speed));
    setTxt('gps-hdg', (typeof heading === 'number' ? heading.toFixed(1) + '°' : heading));
};

/* ============================================================
 * 搜索结果（Python 端通过 searchResults 信号回传）
 * ============================================================ */

INAVMap.prototype.showSearchResults = function (jsonStr) {
    var resultsDiv = document.getElementById('search-results');
    this.searchMarkerLayer.clearLayers();

    try {
        var data = JSON.parse(jsonStr);
        if (!data || data.length === 0) {
            resultsDiv.innerHTML = '<div class="search-item">未找到结果</div>';
            resultsDiv.classList.remove('hidden');
            return;
        }
        var html = '';
        for (var i = 0; i < data.length; i++) {
            var item = data[i];
            var name = item.display_name || item.name || '(未命名)';
            var shortName = name.length > 55 ? name.substring(0, 55) + '...' : name;
            html += '<div class="search-item" data-idx="' + i + '">' + shortName + '</div>';
            // 同步画一个临时 marker
            L.marker([parseFloat(item.lat), parseFloat(item.lon)], {
                opacity: 0.6
            }).addTo(this.searchMarkerLayer);
        }
        resultsDiv.innerHTML = html;
        resultsDiv.classList.remove('hidden');

        // 点击选中
        var self = this;
        var elems = resultsDiv.querySelectorAll('.search-item');
        elems.forEach(function (el) {
            el.addEventListener('click', function () {
                var idx = parseInt(el.getAttribute('data-idx'), 10);
                var sel = data[idx];
                var la = parseFloat(sel.lat);
                var ln = parseFloat(sel.lon);
                var nm = sel.display_name || sel.name || '';
                self.map.setView([la, ln], 15);
                self.searchMarkerLayer.clearLayers();
                L.marker([la, ln]).addTo(self.searchMarkerLayer);
                if (window.bridge) window.bridge.locationSearched(la, ln, nm);
                resultsDiv.classList.add('hidden');
            });
        });
    } catch (e) {
        resultsDiv.innerHTML = '<div class="search-item">搜索出错: ' + e.message + '</div>';
        resultsDiv.classList.remove('hidden');
    }
};

/* ============================================================
 * 模式切换 / 其它命令
 * ============================================================ */

INAVMap.prototype.toggleWaypointMode = function (enable) {
    this.waypointMode = !!enable;
    this.fenceMode = false;
    this.insertMode = false;
    this._toast(this.waypointMode ? '✓ 航点编辑模式（点击添加航点）' : '已退出航点模式');
};

INAVMap.prototype.toggleFenceMode = function (enable) {
    this.fenceMode = !!enable;
    this.waypointMode = false;
    this.insertMode = false;
    this._toast(this.fenceMode ? '✓ 围栏编辑模式（点击添加顶点）' : '已退出围栏模式');
};

INAVMap.prototype.toggleInsertMode = function (enable) {
    this.insertMode = !!enable;
    this._toast(this.insertMode ? '✓ 插入模式（点击航段附近插入航点）' : '已退出插入模式');
};

INAVMap.prototype.setMapCenter = function (lat, lng, zoom) {
    if (typeof zoom === 'number') {
        this.map.setView([lat, lng], zoom);
    } else {
        this.map.panTo([lat, lng]);
    }
};

INAVMap.prototype.exportData = function () {
    // 简化：将当前航点 + 围栏打包成 JSON 后在 toast 中提示
    var wp = this.waypoints.map(function (w) {
        return { index: w.index, lat: w.lat, lng: w.lng, alt: w.alt, speed: w.speed, task: w.task };
    });
    var fp = this.fencePoints.map(function (p) { return { lat: p.lat, lng: p.lng }; });
    var out = JSON.stringify({ waypoints: wp, fence: { points: fp, closed: this.fenceClosed } });
    this._toast('导出数据（见控制台）');
    console.log('[Map] Export data:', out);
    return out;
};

INAVMap.prototype._toast = function (msg) {
    var el = document.getElementById('toast');
    if (!el) return;
    el.textContent = msg;
    el.classList.remove('hidden');
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(function () {
        el.classList.add('hidden');
    }, 2500);
};

/* ============================================================
 * Qt WebChannel 桥接
 * ============================================================ */

INAVMap.prototype.initBridge = function () {
    var self = this;

    // Python → JS：注册所有信号处理函数（信号由 Py 端 emit）
    // 注意：信号名与 Qt 代码中 MapBridge 的信号名必须一致
    if (!window.bridge) {
        console.warn('[Map] bridge not ready, retrying in 500ms');
        setTimeout(function () { self.initBridge(); }, 500);
        return;
    }

    // 绑定信号 → 本地方法
    var bind = function (sigName, fn) {
        if (window.bridge[sigName]) window.bridge[sigName].connect(fn);
    };

    bind('updateDronePosition', function (lat, lng, alt, heading) {
        self.updateDronePosition(lat, lng, alt, heading);
    });
    bind('updateGPSInfo', function (fix, sats, lat, lng, alt, speed, heading) {
        self.updateGPSInfo(fix, sats, lat, lng, alt, speed, heading);
    });
    bind('clearWaypoints', function () { self.clearWaypoints(); });
    bind('loadWaypoints', function (jsonStr) { self.loadWaypoints(jsonStr); });
    bind('loadGeofence', function (jsonStr) { self.loadGeofence(jsonStr); });
    bind('setMapCenter', function (lat, lng, zoom) { self.setMapCenter(lat, lng, zoom); });
    bind('centerOnDrone', function () { self.centerOnDrone(); });
    bind('clearTrack', function () { self.clearTrack(); });
    bind('toggleWaypointMode', function (enable) { self.toggleWaypointMode(enable); });
    bind('toggleFenceMode', function (enable) { self.toggleFenceMode(enable); });
    bind('toggleInsertMode', function (enable) { self.toggleInsertMode(enable); });
    bind('exportData', function () { self.exportData(); });
    bind('searchResults', function (jsonStr) { self.showSearchResults(jsonStr); });

    console.log('[Map] Leaflet + OSM map initialized (no API key required)');
};
