class INAVMap {
    constructor() {
        this.map = null;
        this.viewMode = '2D';
        
        this.waypoints = [];
        this.wpLayer = null;
        this.wpLabelLayer = null;
        
        this.fencePoints = [];
        this.fenceLayer = null;
        this.fenceLabelLayer = null;
        this.fenceLineLayer = null;
        this.fencePolygonLayer = null;
        
        this.waypointMode = false;
        this.fenceMode = false;
        this.insertMode = false;
        this.insertIndex = -1;
        
        // ★ 吸附相关
        this.snapRadius = 25;  // 吸附半径（像素）
        
        this.bridgeReady = false;
        this.bridge = null;
        this.pendingActions = [];
        
        // ★ 当前选中的航点（用于编辑）
        this.selectedWaypointIndex = -1;
        
        // ★ 航段参数（每段的速度/高度）
        this.segments = {};
        
        // ★ 围栏封闭锁定标志（防止事件冲突）
        this._isFinalizingFence = false;
        
        this.initMap();
        this.initLayers();
        this._initInteraction();
        this._initGPSPanel();
        this._initSearchBox();
        this.initBridge();
    }
    
    initMap() {
        console.log('[Map] Initializing Tencent GL map...');
        
        try {
            this.map = new TMap.Map('map', {
                center: new TMap.LatLng(39.9042, 116.4074),
                zoom: 17,
                viewMode: '2D',
                baseMap: {
                    type: 'vector',
                    features: ['base', 'building3d', 'label', 'point']
                }
            });
            
            console.log('[Map] ✓ Map initialized');
            
            this.map.on('click', (evt) => {
                const latLng = evt.latLng;
                if (!latLng) return;
                
                const lat = latLng.getLat();
                const lng = latLng.getLng();
                
                // ★ 检查是否正在封闭围栏（防止事件冲突）
                if (this._isFinalizingFence) {
                    console.log('[Map] Fence finalizing in progress - skipping map click');
                    return;
                }
                
                // ★ 检查是否点击在已有标记上（避免双重操作）
                if (this._isClickOnMarker(evt)) {
                    console.log('[Map] Click on existing marker - skipping add operation');
                    return;  // 让标记层的click事件处理（显示详情/封闭等）
                }
                
                if (this.waypointMode) {
                    if (this.insertMode) {
                        this.insertWaypoint(lat, lng, this.insertIndex);
                    } else {
                        this.addWaypoint(lat, lng);
                    }
                } else if (this.fenceMode) {
                    if (this.insertMode) {
                        this.insertFencePoint(lat, lng, this.insertIndex);
                    } else {
                        this.addFencePoint(lat, lng);
                    }
                }
            });
            
            this._addMapControls();
            
        } catch (e) {
            console.error('[Map] Failed to initialize map:', e);
        }
    }
    
    _addMapControls() {
        const controlDiv = document.createElement('div');
        controlDiv.style.cssText = `
            position: absolute; top: 10px; right: 10px; z-index: 1000;
            background: rgba(30,33,40,0.95); padding: 8px; border-radius: 6px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.4); display: flex; flex-direction: column; gap: 5px;
        `;
        
        const btn2D = document.createElement('button');
        btn2D.innerHTML = '🗺️ 2D'; btn2D.className = 'map-mode-btn active';
        btn2D.onclick = () => this.switchTo2D();
        
        const btn3D = document.createElement('button');
        btn3D.innerHTML = '🏙️ 3D'; btn3D.className = 'map-mode-btn';
        btn3D.onclick = () => this.switchTo3D();
        
        controlDiv.appendChild(btn2D);
        controlDiv.appendChild(btn3D);
        document.getElementById('map').appendChild(controlDiv);
    }
    
    switchTo2D() {
        if (!this.map) return;
        this.viewMode = '2D';
        this.map.setViewMode('2D');
        this._updateModeButtons('2D');
    }
    
    switchTo3D() {
        if (!this.map) return;
        this.viewMode = '3D';
        this.map.setViewMode('3D');
        this.map.setPitch(50);
        this._updateModeButtons('3D');
    }
    
    _updateModeButtons(mode) {
        document.querySelectorAll('.map-mode-btn').forEach((btn, i) => {
            const active = (mode === '2D' && i === 0) || (mode === '3D' && i === 1);
            btn.style.background = active ? '#007bff' : 'rgba(60,65,75,0.8)';
            btn.style.color = active ? 'white' : '#e0e0e0';
        });
    }
    
    initLayers() {
        // ★ 航点图层（蓝色圆形图标 + 纯蓝字标签）
        this.wpLayer = new TMap.MultiMarker({
            map: this.map,
            styles: {
                'wp-marker': new TMap.MarkerStyle({
                    width: 24, height: 24, anchor: { x: 12, y: 12 },
                    src: 'data:image/svg+xml;base64,' + btoa('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"><circle cx="12" cy="12" r="10" fill="#007bff" stroke="#ffffff" stroke-width="2"/></svg>')
                }),
                'wp-insert': new TMap.MarkerStyle({
                    width: 28, height: 28, anchor: { x: 14, y: 14 },
                    src: 'data:image/svg+xml;base64,' + btoa('<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28"><circle cx="14" cy="14" r="12" fill="#28a745" stroke="#ffffff" stroke-width="2"/></svg>')
                }),
                'wp-selected': new TMap.MarkerStyle({
                    width: 28, height: 28, anchor: { x: 14, y: 14 },
                    src: 'data:image/svg+xml;base64,' + btoa('<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28"><circle cx="14" cy="14" r="12" fill="#ffc107" stroke="#ffffff" stroke-width="3"/></svg>')
                })
            },
            geometries: []
        });
        
        // ★ 航点标签（纯蓝字，无背景！）
        this.wpLabelLayer = new TMap.MultiLabel({
            map: this.map,
            styles: {
                'label': new TMap.LabelStyle({
                    color: '#007bff',
                    size: 13,
                    fontWeight: 'bold',
                    offset: { x: 18, y: -5 },
                    background: { padding: '0px' }
                })
            },
            geometries: []
        });
        
        // ★ 航线连线图层（腾讯原生箭头：粗蓝线+白边+自动方向箭头）
        this.wpLineLayer = new TMap.MultiPolyline({
            map: this.map,
            styles: {
                'wp-line': new TMap.PolylineStyle({
                    color: '#3777FF',      // 腾讯标准蓝
                    width: 6,              // 粗线（>6才能显示箭头）
                    borderWidth: 3,        // 白色边框宽度
                    borderColor: '#FFFFFF', // 白色边框
                    lineCap: 'round',      // 圆角端点
                    lineJoin: 'round',     // 圆角连接
                    showArrow: true,       // ★ 显示方向箭头！
                    arrowOptions: {        // ★ 箭头配置
                        color: '#FFFFFF',   // 箭头颜色：白色
                        size: 8,           // 箭头大小
                        width: 4           // 箭头宽度
                    }
                }),
                'wp-line-active': new TMap.PolylineStyle({
                    color: '#0052D9',
                    width: 8,
                    borderWidth: 4,
                    borderColor: '#FFE066',
                    lineCap: 'round',
                    lineJoin: 'round',
                    showArrow: true,
                    arrowOptions: {
                        color: '#FFD700',
                        size: 10,
                        width: 5
                    }
                })
            },
            geometries: []
        });
        
        // ★ 航段参数标签层（显示在航线中点上方：速度/高度）
        this.segLabelLayer = new TMap.MultiLabel({
            map: this.map,
            styles: {
                'seg-label': new TMap.LabelStyle({
                    color: '#fff',
                    size: 11,
                    fontWeight: 'bold',
                    offset: { x: 0, y: -12 },
                    background: {
                        color: 'rgba(255, 152, 0, 0.92)',
                        padding: '2px 8px',
                        radius: 10,
                        borderColor: '#e65100',
                        borderWidth: 1
                    }
                }),
                'seg-label-empty': new TMap.LabelStyle({
                    color: '#bbb',
                    size: 10,
                    offset: { x: 0, y: -10 },
                    background: {
                        color: 'rgba(60, 65, 75, 0.85)',
                        padding: '2px 6px',
                        radius: 8
                    }
                })
            },
            geometries: []
        });
        
        // ★ 围栏点图层（红色菱形图标 + 纯红字标签）
        this.fenceLayer = new TMap.MultiMarker({
            map: this.map,
            styles: {
                'fence-marker': new TMap.MarkerStyle({
                    width: 22, height: 22, anchor: { x: 11, y: 11 },
                    src: 'data:image/svg+xml;base64,' + btoa('<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22"><rect x="4" y="4" width="14" height="14" fill="#dc3545" stroke="#ffffff" stroke-width="2" transform="rotate(45 11 11)"/></svg>')
                }),
                'fence-insert': new TMap.MarkerStyle({
                    width: 26, height: 26, anchor: { x: 13, y: 13 },
                    src: 'data:image/svg+xml;base64,' + btoa('<svg xmlns="http://www.w3.org/2000/svg" width="26" height="26"><rect x="5" y="5" width="16" height="16" fill="#fd7e14" stroke="#ffffff" stroke-width="2" transform="rotate(45 13 13)"/></svg>')
                })
            },
            geometries: []
        });
        
        // ★ 围栏标签（纯红字，无背景！）
        this.fenceLabelLayer = new TMap.MultiLabel({
            map: this.map,
            styles: {
                'label': new TMap.LabelStyle({
                    color: '#dc3545',
                    size: 12,
                    fontWeight: 'bold',
                    offset: { x: 15, y: -3 },
                    background: { padding: '0px' }
                })
            },
            geometries: []
        });
        
        // 围栏连线图层
        this.fenceLineLayer = new TMap.MultiPolyline({
            map: this.map,
            styles: {
                'fence-line': new TMap.PolylineStyle({
                    color: '#dc3545', width: 2, dashArray: [5, 5], lineCap: 'round'
                })
            },
            geometries: []
        });
        
        // ★ 围栏多边形填充图层（支持多个独立区域）
        this.fencePolygonLayer = new TMap.MultiPolygon({
            map: this.map,
            styles: {
                'fence-polygon': new TMap.PolygonStyle({
                    color: 'rgba(220,53,69,0.15)',
                    showBorder: true,
                    borderColor: '#dc3545',
                    borderWidth: 2
                })
            },
            geometries: []
        });
        
        // ★ 已完成的围栏区域列表（支持多个独立区域）
        this.completedFences = [];  
        this.fenceCounter = 0;  // 围栏计数器
        
        // ★ 批量操作标志（与Python端同步，防止Undo/Redo时发送信号）
        this.isBatchOperation = false;
        
        console.log('[Map] ✓ All layers initialized');
    }
    
    /**
     * ★ 检测点击位置是否在已有标记上（防止事件冲突）
     * 使用经纬度距离计算（兼容性更好）
     */
    _isClickOnMarker(evt) {
        if (!evt.latLng) return false;
        
        const clickLat = evt.latLng.getLat();
        const clickLon = evt.latLng.getLng();
        
        // ★ 使用地理距离检测（约5米范围内视为"点在标记上"）
        // 1度纬度 ≈ 111km × cos(纬度)
        // 1度经度 ≈ 111km × cos(纬度)
        const clickRadius = 0.0003;  // 约30-35米（足够覆盖点击区域）
        
        // 检测是否点击在航点上
        for (const wp of this.waypoints) {
            const latDiff = Math.abs(wp.lat - clickLat);
            const lonDiff = Math.abs(wp.lon - clickLon);
            
            if (latDiff < clickRadius && lonDiff < clickRadius) {
                console.log(`[Map] Click on WP${wp.index} marker`);
                return true;
            }
        }
        
        // 检测是否点击在围栏点上
        for (const gf of this.fencePoints) {
            const latDiff = Math.abs(gf.lat - clickLat);
            const lonDiff = Math.abs(gf.lon - clickLon);
            
            if (latDiff < clickRadius && lonDiff < clickRadius) {
                console.log(`[Map] Click on GF${gf.index} marker`);
                return true;
            }
        }
        
        return false;
    }
    
    /**
     * ★ 初始化交互功能（吸附、鼠标样式、点击事件）
     */
    _initInteraction() {
        const mapContainer = document.getElementById('map');
        
        // ★ 鼠标移动事件 - 检测是否靠近航点/围栏点
        this.map.on('mousemove', (evt) => {
            if (!evt.latLng) return;
            
            let nearMarker = false;
            const evtLat = evt.latLng.getLat();
            const evtLon = evt.latLng.getLng();
            const snapRadius = 0.0005;  // 吸附半径约50米
            
            // 检测是否靠近航点
            for (const wp of this.waypoints) {
                const latDiff = Math.abs(wp.lat - evtLat);
                const lonDiff = Math.abs(wp.lon - evtLon);
                if (latDiff < snapRadius && lonDiff < snapRadius) {
                    nearMarker = true;
                    break;
                }
            }
            
            // 检测是否靠近围栏点
            if (!nearMarker) {
                for (const gf of this.fencePoints) {
                    const latDiff = Math.abs(gf.lat - evtLat);
                    const lonDiff = Math.abs(gf.lon - evtLon);
                    if (latDiff < snapRadius && lonDiff < snapRadius) {
                        nearMarker = true;
                        break;
                    }
                }
            }
            
            // ★ 直接操作DOM元素的cursor样式（兼容性更好）
            if (nearMarker) {
                mapContainer.style.cursor = 'pointer';
            } else {
                mapContainer.style.cursor = 'crosshair';
            }
        });
        
        // ★ 航点点击事件 - 显示详细信息+可编辑表单
        this.wpLayer.on('click', (evt) => {
            const id = evt.geometry.id;
            const index = parseInt(id.replace('wp-', ''));
            const wp = this.waypoints[index];
            
            if (wp) {
                this.selectedWaypointIndex = index;
                this._showWaypointEditor(evt.geometry.position, index, wp);
            }
        });
        
        // ★ 航线连线点击事件 - 编辑航段参数（速度/高度）
        if (this.wpLineLayer) {
            this.wpLineLayer.on('click', (evt) => {
                if (this.waypoints.length < 2) return;
                
                const clickLat = evt.latLng.getLat();
                const clickLon = evt.latLng.getLng();
                
                let nearestSeg = -1;
                let minDist = Infinity;
                
                for (let i = 0; i < this.waypoints.length - 1; i++) {
                    const p1 = this.waypoints[i];
                    const p2 = this.waypoints[i + 1];
                    const dist = this._pointToSegmentDistance(clickLat, clickLon, p1.lat, p1.lon, p2.lat, p2.lon);
                    if (dist < minDist) {
                        minDist = dist;
                        nearestSeg = i;
                    }
                }
                
                if (nearestSeg >= 0 && minDist < 0.002) {
                    const midLat = (this.waypoints[nearestSeg].lat + this.waypoints[nearestSeg + 1].lat) / 2;
                    const midLon = (this.waypoints[nearestSeg].lon + this.waypoints[nearestSeg + 1].lon) / 2;
                    this._showSegmentEditor(new TMap.LatLng(midLat, midLon), nearestSeg);
                }
            });
        }
        
        // ★ 围栏点点击事件 - 封闭图形（用该点作为最后一点）
        this.fenceLayer.on('click', (evt) => {
            const id = evt.geometry.id;
            const clickedIndex = parseInt(id.replace('gf-', ''));
            
            console.log(`[Map] Fence point GF${clickedIndex} clicked - will finalize fence to this point`);
            
            // ★ 设置锁定标志，阻止后续map.click添加新点
            this._isFinalizingFence = true;
            
            // ★ 延迟执行封闭（确保map.click事件已经处理完毕）
            setTimeout(() => {
                this.finalizeFenceAt(clickedIndex);
                this._isFinalizingFence = false;  // 解除锁定
            }, 50);
        });
    }
    
    /**
     * ★ 显示航点详细编辑器（包含任务类型、坐标等）
     */
    _showWaypointEditor(position, index, wp) {
        if (!this.infoWindow) {
            this.infoWindow = new TMap.InfoWindow({
                map: this.map,
                position: position,
                content: '',
                offset: { x: 0, y: -40 }
            });
        }
        
        // ★ 获取当前航点的任务信息（默认值）
        const taskType = wp.taskType || 'GOTO_ALT';
        const altitude = wp.altitude || 50;
        const speed = wp.speed || 3;
        const heading = wp.heading || 0;
        
        const content = `
            <div id="wp-editor-${index}" style="
                min-width: 280px;
                padding: 15px;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #ffffff;
                border-radius: 8px;
                box-shadow: 0 4px 16px rgba(0,0,0,0.15);
            ">
                <!-- 标题栏 -->
                <div style="
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 12px;
                    padding-bottom: 8px;
                    border-bottom: 2px solid #007bff;
                ">
                    <span style="font-size: 16px; font-weight: bold; color: #007bff;">
                        📍 WP${index} 编辑器
                    </span>
                    <span style="
                        font-size: 11px;
                        padding: 2px 8px;
                        border-radius: 10px;
                        background: #e3f2fd;
                        color: #1976d2;
                    ">可编辑</span>
                </div>
                
                <!-- 任务类型 -->
                <div style="margin-bottom: 10px;">
                    <label style="
                        display: block;
                        font-size: 12px;
                        font-weight: 600;
                        color: #333;
                        margin-bottom: 4px;
                    ">
                        🎯 任务类型:
                    </label>
                    <select id="wp-task-type" style="
                        width: 100%;
                        padding: 6px 8px;
                        border: 1px solid #ddd;
                        border-radius: 4px;
                        font-size: 13px;
                        cursor: pointer;
                    " onchange="window.inavMap._onTaskTypeChanged(${index}, this.value)">
                        <option value="TAKEOFF" ${taskType === 'TAKEOFF' ? 'selected' : ''}>🚀 起飞 (TAKEOFF)</option>
                        <option value="GOTO_ALT" ${taskType === 'GOTO_ALT' ? 'selected' : ''}>⬆️ 飞向目标高度 (GOTO_ALT)</option>
                        <option value="GOTO_HEADING" ${taskType === 'GOTO_HEADING' ? 'selected' : ''}>➡️ 飞向目标航向 (GOTO_HEADING)</option>
                        <option value="HOVER" ${taskType === 'HOVER' ? 'selected' : ''}>⏸️ 悬停 (HOVER)</option>
                        <option value="LAND" ${taskType === 'LAND' ? 'selected' : ''}>🛬 降落 (LAND)</option>
                        <option value="JUMP" ${taskType === 'JUMP' ? 'selected' : ''}>🔀 跳转 (JUMP)</option>
                        <option value="SET_HEAD" ${taskType === 'SET_HEAD' ? 'selected' : ''}>🧭 设定航向 (SET_HEAD)</option>
                        <option value="CUSTOM" ${taskType === 'CUSTOM' ? 'selected' : ''}>⚙️ 自定义 (CUSTOM)</option>
                    </select>
                </div>
                
                <!-- 坐标信息 -->
                <div style="
                    background: #f8f9fa;
                    padding: 8px;
                    border-radius: 4px;
                    margin-bottom: 10px;
                    font-size: 12px;
                ">
                    <table style="width: 100%;">
                        <tr>
                            <td style="color: #666;"><b>纬度:</b></td>
                            <td style="color: #333; text-align: right;">${wp.lat.toFixed(6)}°</td>
                        </tr>
                        <tr>
                            <td style="color: #666;"><b>经度:</b></td>
                            <td style="color: #333; text-align: right;">${wp.lon.toFixed(6)}°</td>
                        </tr>
                    </table>
                </div>
                
                <!-- 参数编辑区 -->
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px;">
                    <div>
                        <label style="font-size: 11px; font-weight: 600; color: #555;">
                            📏 高度(m):
                        </label>
                        <input type="number" id="wp-altitude" value="${altitude}"
                            style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 3px; font-size: 12px;"
                            onchange="window.inavMap._onParamChanged(${index}, 'altitude', this.value)">
                    </div>
                    <div>
                        <label style="font-size: 11px; font-weight: 600; color: #555;">
                            ⚡ 速度(m/s):
                        </label>
                        <input type="number" id="wp-speed" value="${speed}" step="0.5" min="0"
                            style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 3px; font-size: 12px;"
                            onchange="window.inavMap._onParamChanged(${index}, 'speed', this.value)">
                    </div>
                    <div>
                        <label style="font-size: 11px; font-weight: 600; color: #555;">
                            🧭 航向(°):
                        </label>
                        <input type="number" id="wp-heading" value="${heading}" min="0" max="360"
                            style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 3px; font-size: 12px;"
                            onchange="window.inavMap._onParamChanged(${index}, 'heading', this.value)">
                    </div>
                    <div>
                        <label style="font-size: 11px; font-weight: 600; color: #555;">
                            ⏱️ 停留(s):
                        </label>
                        <input type="number" id="wp-dwell" value="${wp.dwell || 0}" min="0"
                            style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 3px; font-size: 12px;"
                            onchange="window.inavMap._onParamChanged(${index}, 'dwell', this.value)">
                    </div>
                </div>
                
                <!-- 操作按钮 -->
                <div style="
                    display: flex;
                    gap: 8px;
                    margin-top: 12px;
                    padding-top: 10px;
                    border-top: 1px solid #eee;
                ">
                    <button onclick="window.inavMap._saveWaypointEdits(${index})"
                        style="
                            flex: 1;
                            padding: 8px;
                            background: #007bff;
                            color: white;
                            border: none;
                            border-radius: 4px;
                            font-size: 13px;
                            font-weight: 600;
                            cursor: pointer;
                        ">
                        💾 保存修改
                    </button>
                    <button onclick="if(window.inavMap.infoWindow) window.inavMap.infoWindow.close();"
                        style="
                            flex: 1;
                            padding: 8px;
                            background: #6c757d;
                            color: white;
                            border: none;
                            border-radius: 4px;
                            font-size: 13px;
                            cursor: pointer;
                        ">
                        ✖ 关闭
                    </button>
                </div>
                
                <!-- 提示信息 -->
                <div style="
                    margin-top: 10px;
                    padding: 6px;
                    background: #fff3cd;
                    border-radius: 4px;
                    font-size: 11px;
                    color: #856404;
                    text-align: center;
                ">
                    💡 点击地图其他位置关闭此窗口
                </div>
            </div>
        `;
        
        this.infoWindow.setPosition(position);
        this.infoWindow.setContent(content);
        this.infoWindow.open();
        
        // 点击地图其他位置时关闭
        setTimeout(() => {
            this.map.once('click', () => {
                if (this.infoWindow) this.infoWindow.close();
            });
        }, 100);
    }
    
    /**
     * ★ 处理任务类型变更
     */
    _onTaskTypeChanged(index, newType) {
        console.log(`[Map] WP${index} task type changed to: ${newType}`);
        
        if (this.waypoints[index]) {
            this.waypoints[index].taskType = newType;
        }
    }
    
    /**
     * ★ 处理参数变更
     */
    _onParamChanged(index, param, value) {
        console.log(`[Map] WP${index} ${param} changed to: ${value}`);
        
        if (this.waypoints[index]) {
            this.waypoints[index][param] = parseFloat(value);
        }
    }
    
    /**
     * ★ 保存航点编辑到Python端
     */
    _saveWaypointEdits(index) {
        const wp = this.waypoints[index];
        if (!wp) {
            alert('错误：无法获取航点数据！');
            return;
        }
        
        // ★ 收集所有编辑的数据
        const editData = {
            index: index,
            taskType: document.getElementById('wp-task-type')?.value || wp.taskType || 'GOTO_ALT',
            altitude: parseFloat(document.getElementById('wp-altitude')?.value || wp.altitude || 50),
            speed: parseFloat(document.getElementById('wp-speed')?.value || wp.speed || 3),
            heading: parseFloat(document.getElementById('wp-heading')?.value || wp.heading || 0),
            dwell: parseFloat(document.getElementById('wp-dwell')?.value || wp.dwell || 0),
            lat: wp.lat,
            lon: wp.lon
        };
        
        console.log('[Map] Saving waypoint edits:', editData);
        
        // ★ 发送到Python端保存
        this.sendAction({
            type: 'waypoint_edited',
            data: editData
        });
        
        // ★ 更新本地数据
        Object.assign(this.waypoints[index], editData);
        
        this.refreshWaypoints();
        
        alert(`✅ WP${index} 已保存！\n\n任务类型: ${editData.taskType}\n高度: ${editData.altitude}m\n速度: ${editData.speed}m/s`);
        
        // 关闭弹窗
        if (this.infoWindow) this.infoWindow.close();
    }

    _pointToSegmentDistance(lat, lon, x1, y1, x2, y2) {
        const dx = x2 - x1;
        const dy = y2 - y1;
        if (dx === 0 && dy === 0) return Math.sqrt((lat - x1) ** 2 + (lon - y1) ** 2);
        const t = Math.max(0, Math.min(1, ((lat - x1) * dx + (lon - y1) * dy) / (dx * dx + dy * dy)));
        const projX = x1 + t * dx;
        const projY = y1 + t * dy;
        return Math.sqrt((lat - projX) ** 2 + (lon - projY) ** 2);
    }

    _showSegmentEditor(position, segIndex) {
        const wp1 = this.waypoints[segIndex];
        const wp2 = this.waypoints[segIndex + 1];
        
        if (!this.segmentInfoWindow) {
            this.segmentInfoWindow = new TMap.InfoWindow({
                map: this.map,
                position: position,
                content: '',
                offset: { x: 0, y: -30 }
            });
        }
        
        const seg = this.segments ? this.segments[segIndex] : null;
        const speed = seg ? (seg.speed || 5) : 5;
        const alt = seg ? (seg.altitude || 50) : 50;
        
        const content = `
            <div id="seg-editor-${segIndex}" style="
                min-width: 260px;
                padding: 15px;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #ffffff;
                border-radius: 8px;
                box-shadow: 0 4px 16px rgba(0,0,0,0.18);
                border-left: 4px solid #ff9800;
            ">
                <div style="
                    display: flex; justify-content: space-between; align-items: center;
                    margin-bottom: 10px; padding-bottom: 6px; border-bottom: 2px solid #ff9800;
                ">
                    <span style="font-size: 15px; font-weight: bold; color: #e65100;">
                        ✈️ 航段 WP${segIndex} → WP${segIndex + 1}
                    </span>
                    <span style="font-size: 11px; padding: 2px 8px; border-radius: 10px; background: #fff3e0; color: #e65100;">航段参数</span>
                </div>
                
                <div style="background: #f5f5f5; padding: 6px 10px; border-radius: 4px; margin-bottom: 12px; font-size: 11px; color: #666;">
                    📍 ${wp1.lat.toFixed(5)}, ${wp1.lon.toFixed(5)} → ${wp2.lat.toFixed(5)}, ${wp2.lon.toFixed(5)}
                </div>
                
                <div style="margin-bottom: 10px;">
                    <label style="display: block; font-size: 12px; font-weight: 600; color: #333; margin-bottom: 4px;">
                        🚀 飞行速度 (m/s):
                    </label>
                    <input id="seg-speed" type="number" min="0.5" max="50" step="0.5" value="${speed}" style="
                        width: 100%; padding: 7px 10px; border: 1px solid #ddd; border-radius: 4px;
                        font-size: 13px; box-sizing: border-box;
                    ">
                </div>
                
                <div style="margin-bottom: 10px;">
                    <label style="display: block; font-size: 12px; font-weight: 600; color: #333; margin-bottom: 4px;">
                        📏 目标高度 (m):
                    </label>
                    <input id="seg-altitude" type="number" min="5" max="500" step="5" value="${alt}" style="
                        width: 100%; padding: 7px 10px; border: 1px solid #ddd; border-radius: 4px;
                        font-size: 13px; box-sizing: border-box;
                    ">
                </div>
                
                <div style="display: flex; gap: 8px; margin-top: 14px;">
                    <button onclick="window.inavMap._saveSegmentEdits(${segIndex})" style="
                        flex: 1; padding: 8px; background: linear-gradient(135deg, #ff9800, #f57c00);
                        color: white; border: none; border-radius: 6px; font-size: 13px; font-weight: bold;
                        cursor: pointer; transition: transform 0.15s;
                    " onmouseover="this.style.transform='scale(1.02)'" onmouseout="this.style.transform='scale(1)'">
                        💾 保存
                    </button>
                    <button onclick="if(window.inavMap.segmentInfoWindow) window.inavMap.segmentInfoWindow.close()" style="
                        padding: 8px 16px; background: #eee; color: #666; border: none; border-radius: 6px;
                        font-size: 13px; cursor: pointer;
                    ">取消</button>
                </div>
            </div>`;
        
        this.segmentInfoWindow.setPosition(position);
        this.segmentInfoWindow.setContent(content);
        this.segmentInfoWindow.open();
    }

    _saveSegmentEdits(segIndex) {
        if (!this.segments) this.segments = {};
        
        const editData = {
            segment_index: segIndex,
            from_wp: segIndex,
            to_wp: segIndex + 1,
            speed: parseFloat(document.getElementById('seg-speed')?.value || 5),
            altitude: parseFloat(document.getElementById('seg-altitude')?.value || 50),
            from_lat: this.waypoints[segIndex].lat,
            from_lon: this.waypoints[segIndex].lon,
            to_lat: this.waypoints[segIndex + 1].lat,
            to_lon: this.waypoints[segIndex + 1].lon
        };
        
        this.segments[segIndex] = editData;
        
        this.sendAction({
            type: 'segment_edited',
            data: editData
        });
        
        this.updateWpLines();
        
        alert(`✅ 航段 WP${segIndex}→WP${segIndex + 1} 已保存！\n\n速度: ${editData.speed} m/s\n高度: ${editData.altitude} m`);
        
        if (this.segmentInfoWindow) this.segmentInfoWindow.close();
    }
    
    /**
     * ★ 在指定围栏点处封闭图形（支持多个独立区域）
     * 
     * 核心逻辑：
     * 1. 从被点击的点到最后一个点 → 形成封闭多边形
     * 2. 删除该点之前的所有散点
     * 3. 保存为独立的围栏区域
     * 4. 清空当前点列表（准备开始新的区域）
     * 
     * 示例：fencePoints = [GF0, GF1, GF2, GF3, GF4], 点击GF2
     * → 封闭区域 = [GF2, GF3, GF4] (3个顶点的三角形)
     * → 删除 GF0, GF1
     * → fencePoints 清空
     * → 下次添加的点是新区域的起点
     */
    finalizeFenceAt(clickedIndex) {
        console.log(`[Map] === Starting multi-fence finalization at GF${clickedIndex} ===`);
        console.log(`[Map] Total fence points: ${this.fencePoints.length}`);
        
        if (this.fencePoints.length < 3) {
            alert('⚠️ 至少需要3个围栏点才能封闭图形！');
            return;
        }
        
        if (clickedIndex < 0 || clickedIndex >= this.fencePoints.length) {
            alert(`⚠️ 无效的索引: ${clickedIndex}`);
            return;
        }
        
        // ★ 截取从被点击点到最后的所有点（这才是要封闭的区域！）
        const closedPoints = this.fencePoints.slice(clickedIndex);
        
        console.log(`[Map] Fence region #${this.fenceCounter + 1} will have ${closedPoints.length} vertices:`);
        closedPoints.forEach((p, i) => {
            const originalIndex = clickedIndex + i;
            console.log(`[Map]   Vertex ${i}: original GF${originalIndex} (${p.lat.toFixed(6)}, ${p.lon.toFixed(6)})`);
        });
        
        if (closedPoints.length < 3) {
            alert(`⚠️ 从GF${clickedIndex}到末尾只有${closedPoints.length}个点，不足3个无法封闭！`);
            return;
        }
        
        // ★ 保存到已完成围栏列表
        const fenceRegion = {
            id: `fence-region-${this.fenceCounter}`,
            points: closedPoints,
            createdAt: new Date().toLocaleString()
        };
        this.completedFences.push(fenceRegion);
        
        // ★ 绘制/更新所有已完成的围栏多边形（保留之前的）
        this._refreshAllFencePolygons();
        
        // 发送数据到Python
        this.sendAction({
            type: 'geofence_created',
            data: { 
                jsonStr: JSON.stringify(closedPoints),
                fenceId: fenceRegion.id,
                regionNumber: this.completedFences.length
            }
        });
        
        // ★ 关键：清除该点之前的所有散点和当前所有显示的点
        // 这样下一个添加的点就是新独立区域的起点
        this.fencePoints = [];
        this.refreshFencePoints();
        
        console.log(`[Map] ✓ Fence region #${this.fenceCounter + 1} finalized!`);
        console.log(`[Map]   Vertices: ${closedPoints.length}`);
        console.log(`[Map]   Cleared all temporary points (ready for next region)`);
        console.log(`[Map]   Total completed fences: ${this.completedFences.length}`);
        
        this.fenceCounter++;
        
        alert(`✅ 围栏区域 #${this.completedFences.length} 已封闭！\n\n` +
              `📐 多边形顶点数: ${closedPoints.length}\n` +
              `📍 起始点: 原GF${clickedIndex}\n` +
              `🎯 已清除前面的散点\n` +
              `🆕 可继续添加下一个独立围栏区域`);
    }
    
    /**
     * ★ 刷新所有已完成的围栏多边形显示
     */
    _refreshAllFencePolygons() {
        const polygonGeometries = [];
        
        this.completedFences.forEach((fence, idx) => {
            const paths = [fence.points.map(p => new TMap.LatLng(p.lat, p.lon))];
            polygonGeometries.push({
                id: fence.id,
                styleId: 'fence-polygon',
                paths: paths
            });
        });
        
        this.fencePolygonLayer.setGeometries(polygonGeometries);
        console.log(`[Map] Refreshed ${polygonGeometries.length} fence polygon(s) on map`);
    }
    
    // ====== 航点操作 ======
    
    addWaypoint(lat, lon) {
        const index = this.waypoints.length;
        this.waypoints.push({ 
            index, lat, lon,
            taskType: 'GOTO_ALT',
            altitude: 50,
            speed: 3,
            heading: 0,
            dwell: 0
        });
        
        this.wpLayer.add([{
            id: `wp-${index}`,
            styleId: 'wp-marker',
            position: new TMap.LatLng(lat, lon)
        }]);
        
        this.wpLabelLayer.add([{
            id: `wp-label-${index}`,
            styleId: 'label',
            position: new TMap.LatLng(lat, lon),
            content: `${this._getTaskIcon('GOTO_ALT')} WP${index}`
        }]);
        
        // ★ 立即更新航线连线（每添加一个点就显示路径）
        this.updateWpLines();
        
        this.sendAction({ type: 'waypoint_added', data: { index, lat, lon } });
    }
    
    insertWaypoint(lat, lon, index) {
        this.waypoints.splice(index, 0, { 
            index, lat, lon,
            taskType: 'GOTO_ALT',
            altitude: 50,
            speed: 3,
            heading: 0,
            dwell: 0
        });
        this.refreshWaypoints();
        
        this.insertMode = false;
        this.insertIndex = -1;
    }
    
    removeWaypointByIndex(index) {
        if (index >= 0 && index < this.waypoints.length) {
            this.waypoints.splice(index, 1);
            this.refreshWaypoints();

            // ★ 重要：不再发送waypoint_removed信号到Python！
            // 因为Python端已经知道要删除这个点了，避免双重删除！
            console.log(`[Map] ✓ Waypoint ${index} removed locally (no signal to Python)`);
        }
    }

    /**
     * ★ 删除最后一个航点（用于撤销操作）
     */
    removeLastWaypoint() {
        if (this.waypoints.length > 0) {
            const lastIndex = this.waypoints.length - 1;
            this.waypoints.pop();
            this.refreshWaypoints();
            console.log(`[Map] ✓ Last waypoint (WP${lastIndex}) removed for undo`);
        }
    }

    /**
     * ★ 智能删除围栏点（用于撤销操作）
     * 
     * 逻辑：
     * 1. 如果有散点(fencePoints) → 删除最后一个散点
     * 2. 如果没有散点但有已完成的围栏(completedFences) → 直接删除最后一个围栏区域
     */
    removeLastFencePoint() {
        if (this.fencePoints.length > 0) {
            const lastIndex = this.fencePoints.length - 1;
            this.fencePoints.pop();
            this.refreshFencePoints();
            console.log(`[Map] ✓ Last fence point (GF${lastIndex}) removed`);
        } else if (this.completedFences.length > 0) {
            const removed = this.completedFences.pop();
            this._refreshAllFencePolygons();
            console.log(`[Map] ✓ Fence region ${removed.id} removed (${removed.points.length} vertices)`);
        } else {
            console.log('[Map] Nothing to undo');
        }
    }
    
    refreshWaypoints() {
        const wpGeometries = [];
        const labelGeometries = [];
        
        this.waypoints.forEach((wp, i) => {
            wp.index = i;
            wpGeometries.push({
                id: `wp-${i}`,
                styleId: (i === this.selectedWaypointIndex) ? 'wp-selected' : 'wp-marker',
                position: new TMap.LatLng(wp.lat, wp.lon)
            });
            const taskIcon = this._getTaskIcon(wp.taskType);
            labelGeometries.push({
                id: `wp-label-${i}`,
                styleId: 'label',
                position: new TMap.LatLng(wp.lat, wp.lon),
                content: `${taskIcon} WP${i}`
            });
        });
        
        this.wpLayer.setGeometries(wpGeometries);
        this.wpLabelLayer.setGeometries(labelGeometries);
        
        // ★ 更新航线连线（蓝色虚线）
        this.updateWpLines();
    }
    
    /**
     * ★ 更新航线连线（粗蓝线+白边+自动方向箭头）+ 航段参数标签
     */
    updateWpLines() {
        if (this.waypoints.length < 2) {
            this.wpLineLayer.setGeometries([]);
            this.segLabelLayer.setGeometries([]);
            return;
        }
        
        const paths = [this.waypoints.map(wp => new TMap.LatLng(wp.lat, wp.lon))];
        
        this.wpLineLayer.setGeometries([{
            id: 'wp-polyline-0',
            styleId: 'wp-line',
            paths: paths
        }]);
        
        // ★ 更新航段参数标签（显示在每段中点上方）
        const segLabels = [];
        for (let i = 0; i < this.waypoints.length - 1; i++) {
            const p1 = this.waypoints[i];
            const p2 = this.waypoints[i + 1];
            const midLat = (p1.lat + p2.lat) / 2;
            const midLon = (p1.lon + p2.lon) / 2;
            
            const segData = this.segments ? this.segments[i] : null;
            let content, styleId;
            
            if (segData && (segData.speed || segData.altitude)) {
                const sp = segData.speed || '-';
                const alt = segData.altitude || '-';
                content = `🚀${sp}m/s 📏${alt}m`;
                styleId = 'seg-label';
            } else {
                content = `─── WP${i}→WP${i + 1} ───`;
                styleId = 'seg-label-empty';
            }
            
            segLabels.push({
                id: `seg-label-${i}`,
                styleId: styleId,
                position: new TMap.LatLng(midLat, midLon),
                content: content
            });
        }
        
        this.segLabelLayer.setGeometries(segLabels);
        
        console.log(`[Map] ✓ Flight path updated: ${this.waypoints.length} waypoints, ${segLabels.length} segment labels`);
    }
    

    
    // ====== 围栏操作 ======
    
    addFencePoint(lat, lon) {
        const index = this.fencePoints.length;
        this.fencePoints.push({ index, lat, lon });
        
        this.fenceLayer.add([{
            id: `gf-${index}`,
            styleId: 'fence-marker',
            position: new TMap.LatLng(lat, lon)
        }]);
        
        this.fenceLabelLayer.add([{
            id: `gf-label-${index}`,
            styleId: 'label',
            position: new TMap.LatLng(lat, lon),
            content: `GF${index}`
        }]);
        
        this.updateFenceLines();
        this.sendAction({ type: 'fence_point_added', data: { index, lat, lon } });
    }
    
    insertFencePoint(lat, lon, index) {
        this.fencePoints.splice(index, 0, { index, lat, lon });
        this.refreshFencePoints();
        
        this.insertMode = false;
        this.insertIndex = -1;
    }
    
    removeFencePointByIndex(index) {
        if (index >= 0 && index < this.fencePoints.length) {
            this.fencePoints.splice(index, 1);
            this.refreshFencePoints();
            // ★ 同样不发送信号避免双重删除
        }
    }
    
    refreshFencePoints() {
        const markerGeometries = [];
        const labelGeometries = [];
        
        this.fencePoints.forEach((p, i) => {
            p.index = i;
            markerGeometries.push({
                id: `gf-${i}`,
                styleId: 'fence-marker',
                position: new TMap.LatLng(p.lat, p.lon)
            });
            labelGeometries.push({
                id: `gf-label-${i}`,
                styleId: 'label',
                position: new TMap.LatLng(p.lat, p.lon),
                content: `GF${i}`
            });
        });
        
        this.fenceLayer.setGeometries(markerGeometries);
        this.fenceLabelLayer.setGeometries(labelGeometries);
        this.updateFenceLines();
    }
    
    updateFenceLines() {
        if (this.fencePoints.length < 2) {
            this.fenceLineLayer.setGeometries([]);
            return;
        }
        
        const paths = [this.fencePoints.map(p => new TMap.LatLng(p.lat, p.lon))];
        this.fenceLineLayer.setGeometries([{
            id: 'fence-polyline-0',
            styleId: 'fence-line',
            paths: paths
        }]);
    }
    
    clearAllFenceData() {
        this.fencePoints = [];
        this.fenceLayer.setGeometries([]);
        this.fenceLabelLayer.setGeometries([]);
        this.fenceLineLayer.setGeometries([]);
        this.fencePolygonLayer.setGeometries([]);
        // ★ 清除所有已完成的围栏区域
        this.completedFences = [];
        this.fenceCounter = 0;
    }
    
    finalizeGeofence() {
        if (this.fencePoints.length >= 3) {
            this.sendAction({
                type: 'geofence_created',
                data: { jsonStr: JSON.stringify(this.fencePoints) }
            });
        }
        this.clearAllFenceData();
    }
    
    setInsertMode(enabled, index) {
        this.insertMode = enabled;
        this.insertIndex = index;
    }
    
    clearWaypoints() {
        this.waypoints = [];
        this.wpLayer.setGeometries([]);
        this.wpLabelLayer.setGeometries([]);
        // ★ 清除航线连线（箭头自动随连线消失）
        this.wpLineLayer.setGeometries([]);
    }
    
    clearAll() {
        this.clearWaypoints();
        this.clearAllFenceData();
    }
    
    loadWaypoints(waypoints) {
        this.clearAll();
        waypoints.forEach((wp, i) => {
            this.addWaypoint(wp.lat, wp.lon);
        });
    }
    
    /**
     * ★ 批量加载围栏点（用于Undo/Redo恢复）
     */
    loadFencePoints(pointsJson) {
        try {
            let points;
            if (typeof pointsJson === 'string') {
                points = JSON.parse(pointsJson);
            } else if (Array.isArray(pointsJson)) {
                points = pointsJson;
            } else {
                console.error('[Map] loadFencePoints: invalid input type', typeof pointsJson);
                return;
            }
            this.clearAllFenceData();
            points.forEach((pt) => {
                this.fencePoints.push({ index: this.fencePoints.length, lat: pt.lat, lon: pt.lon });
            });
            this.refreshFencePoints();
            console.log(`[Map] ✓ Loaded ${points.length} fence points with lines`);
        } catch (e) {
            console.error('[Map] Error loading fence points:', e);
        }
    }
    
    /**
     * ★ 加载已完成的围栏多边形到地图（用于Undo/Redo恢复）
     */
    loadGeofence(fencesJson) {
        try {
            // ★ Qt WebChannel 可能自动反序列化
            let fences;
            if (typeof fencesJson === 'string') {
                fences = JSON.parse(fencesJson);
            } else if (Array.isArray(fencesJson)) {
                fences = fencesJson;
            } else {
                console.error('[Map] Invalid geofence data type:', typeof fencesJson);
                return;
            }
            
            console.log(`[Map] Loading ${fences.length} geofence(s) to map`);
            
            // 清除现有围栏多边形
            this.fencePolygonLayer.setGeometries([]);
            this.completedFences = [];
            
            // 绘制每个围栏
            fences.forEach((fence, idx) => {
                if (!fence.points || fence.points.length < 3) return;
                
                const paths = [fence.points.map(p => new TMap.LatLng(p.lat, p.lon))];
                
                this.fencePolygonLayer.add([{
                    id: `fence-restore-${idx}`,
                    styleId: 'fence-polygon',
                    paths: paths
                }]);
                
                this.completedFences.push({
                    id: `fence-restore-${idx}`,
                    points: fence.points
                });
            });
            
            console.log(`[Map] ✓ Loaded ${this.completedFences.length} fence polygon(s) on map`);
        } catch (e) {
            console.error('[Map] Error loading geofence:', e);
        }
    }

    addGeofence(fenceJson) {
        try {
            let fence;
            if (typeof fenceJson === 'string') {
                fence = JSON.parse(fenceJson);
            } else if (typeof fenceJson === 'object' && fenceJson !== null) {
                fence = fenceJson;
            } else {
                return;
            }
            
            if (!fence.points || fence.points.length < 3) return;
            
            const fid = fence.fence_id || `fence-redo-${this.completedFences.length}`;
            const paths = [fence.points.map(p => new TMap.LatLng(p.lat, p.lon))];
            
            this.fencePolygonLayer.add([{
                id: fid,
                styleId: 'fence-polygon',
                paths: paths
            }]);
            
            this.completedFences.push({ id: fid, points: fence.points });
            console.log(`[Map] ✓ Added fence region ${fid} (${fence.points.length} vertices), total: ${this.completedFences.length}`);
        } catch (e) {
            console.error('[Map] Error adding geofence:', e);
        }
    }
    
    setCenter(lat, lon, zoom = 17) {
        if (this.map) {
            this.map.setCenter(new TMap.LatLng(lat, lon));
            if (zoom) this.map.setZoom(zoom);
        }
    }

    // ====== 地点搜索 ======

    _initSearchBox() {
        const container = document.createElement('div');
        container.id = 'search-container';
        container.innerHTML = `
            <div id="search-box">
                <svg class="search-icon" viewBox="0 0 24 24" width="16" height="16"><path fill="#888" d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0016 9.5 6.5 6.5 0 109.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
                <input id="search-input" type="text" placeholder="搜索地点..." autocomplete="off" />
                <button id="search-clear" title="清除">×</button>
            </div>
            <div id="search-results"></div>
        `;
        document.body.appendChild(container);

        const input = document.getElementById('search-input');
        const clearBtn = document.getElementById('search-clear');
        const resultsDiv = document.getElementById('search-results');

        let debounceTimer = null;

        input.addEventListener('input', (e) => {
            clearBtn.style.display = e.target.value ? 'block' : 'none';
            clearTimeout(debounceTimer);
            const keyword = e.target.value.trim();
            if (keyword.length < 2) {
                resultsDiv.style.display = 'none';
                return;
            }
            debounceTimer = setTimeout(() => this._doSearch(keyword), 300);
        });

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                clearTimeout(debounceTimer);
                this._doSearch(input.value.trim());
            } else if (e.key === 'Escape') {
                resultsDiv.style.display = 'none';
                input.blur();
            }
        });

        clearBtn.addEventListener('click', () => {
            input.value = '';
            clearBtn.style.display = 'none';
            resultsDiv.style.display = 'none';
            input.focus();
        });

        document.addEventListener('click', (e) => {
            if (!container.contains(e.target)) {
                resultsDiv.style.display = 'none';
            }
        });
    }

    _doSearch(keyword) {
        this._lastSearchKeyword = keyword;
        const resultsDiv = document.getElementById('search-results');
        resultsDiv.innerHTML = '<div class="search-loading">🔍 搜索中...</div>';
        resultsDiv.style.display = 'block';

        if (this.bridgeReady && this.bridge && typeof this.bridge.searchPlace === 'function') {
            this.bridge.searchPlace(keyword);
        } else {
            resultsDiv.innerHTML = '<div class="search-error">搜索服务未就绪</div>';
        }
    }

    renderSearchResults(jsonStr) {
        const resultsDiv = document.getElementById('search-results');
        if (!resultsDiv) return;

        let json;
        try {
            if (typeof jsonStr === 'string') {
                json = JSON.parse(jsonStr);
            } else {
                json = jsonStr;
            }
        } catch (e) {
            console.error('[Map] Parse search results error:', e);
            resultsDiv.innerHTML = '<div class="search-error">结果解析失败</div>';
            return;
        }

        resultsDiv.innerHTML = '';
        const keyword = this._lastSearchKeyword || '';

        if (json.status !== 0) {
            resultsDiv.innerHTML = '<div class="search-error">搜索失败: ' + (json.message || '未知错误') + '</div>';
            return;
        }

        const pois = json.data || [];

        if (pois.length === 0) {
            resultsDiv.innerHTML = '<div class="search-empty">未找到相关地点</div>';
            return;
        }

        pois.forEach((poi) => {
            const item = document.createElement('div');
            item.className = 'search-result-item';

            const title = poi.title || '';
            const addr = poi.address || '';
            const cat = poi.category || '';
            const lat = poi.location.lat;
            const lng = poi.location.lng;
            const dist = poi._distance;
            const catIcon = this._getCategoryIcon(cat);

            item.innerHTML = `
                <span class="result-cat-icon">${catIcon}</span>
                <div class="result-body">
                    <div class="result-title">${this._highlight(title, keyword)}</div>
                    <div class="result-meta">
                        ${cat ? `<span class="result-category">${cat}</span>` : ''}
                        ${dist !== undefined ? `<span class="result-distance">${dist > 1000 ? (dist/1000).toFixed(1) + 'km' : dist + 'm'}</span>` : ''}
                    </div>
                    ${addr ? `<div class="result-addr">${this._highlight(addr, keyword)}</div>` : ''}
                    <div class="result-coords">${lat.toFixed(6)}, ${lng.toFixed(6)}</div>
                </div>
            `;

            item.addEventListener('click', () => {
                this.setCenter(lat, lng, 17);
                resultsDiv.style.display = 'none';
                document.getElementById('search-input').value = title;

                this.sendAction({
                    type: 'location_searched',
                    data: { lat, lng, name: title, address: addr, category: cat }
                });
            });

            resultsDiv.appendChild(item);
        });

        if (json.count > 10) {
            const more = document.createElement('div');
            more.className = 'search-more';
            more.textContent = `共 ${json.count} 个结果，显示前 10 条`;
            resultsDiv.appendChild(more);
        }
    }

    _getTaskIcon(taskType) {
        const map = {
            'GOTO_ALT': '🎯', 'GOTO': '🎯', 'WAYPOINT': '🎯',
            'TAKEOFF': '🛫', 'LAND': '🛬', 'RTL': '🏠',
            'LOITER_TIME': '⏱️', 'LOITER_UNLIM': '♾️', 'HOLD': '⏸️',
            'JUMP': '⤴️', 'SET_HEAD': '🧭', 'CONDITIONAL': '❓',
            'DO_JUMP': '⤴️', 'DO_SET_SERVO': '⚙️', 'DO_REPEAT': '🔁',
            'DO_CHANGE_SPEED': '⚡', 'DO_LAND': '🛬',
            'DO_FIGURE8': '∞', 'DO_SURFACE_TRACKING': '📡'
        };
        return map[taskType] || '📍';
    }

    _getCategoryIcon(category) {
        const map = {
            '餐饮': '🍜', '美食': '🍜', '餐厅': '🍜', '酒店': '🏨', '宾馆': '🏨',
            '购物': '🛒', '超市': '🛒', '商场': '🛒',
            '交通': '🚇', '地铁': '🚇', '公交': '🚌', '机场': '✈️', '火车站': '🚄',
            '景点': '🏞️', '公园': '🌳', '景区': '🏞️', '旅游': '🏞️',
            '医院': '🏥', '银行': '🏦', '学校': '🎓', '大学': '🎓',
            '公司': '🏢', '写字楼': '🏢', '住宅': '🏠', '小区': '🏠'
        };
        for (const [key, icon] of Object.entries(map)) {
            if (category.includes(key)) return icon;
        }
        return '📍';
    }

    _highlight(text, keyword) {
        if (!keyword) return text;
        const escaped = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const regex = new RegExp(`(${escaped})`, 'gi');
        return text.replace(regex, '<mark>$1</mark>');
    }

    searchLocation(keyword) {
        const input = document.getElementById('search-input');
        if (input) {
            input.value = keyword;
            this._doSearch(keyword.trim());
        }
    }
    
    // ====== GPS面板 ======
    
    _initGPSPanel() {
        const panel = document.getElementById('info-panel');
        const closeBtn = document.getElementById('close-gps-btn');
        if (!panel || !closeBtn) return;
        
        closeBtn.addEventListener('click', () => {
            panel.style.display = 'none';
            localStorage.setItem('gps_panel_visible', 'false');
        });
        
        if (localStorage.getItem('gps_panel_visible') === 'false') {
            panel.style.display = 'none';
        }
        
        let isDragging = false, startX, startY, initialLeft, initialTop;
        const header = panel.querySelector('.panel-header');
        
        if (header) {
            header.addEventListener('mousedown', (e) => {
                if (e.target === closeBtn || closeBtn.contains(e.target)) return;
                isDragging = true;
                startX = e.clientX; startY = e.clientY;
                const rect = panel.getBoundingClientRect();
                initialLeft = rect.left; initialTop = rect.top;
                panel.style.opacity = '0.9';
                e.preventDefault();
            });
        }
        
        document.addEventListener('mousemove', (e) => {
            if (!isDragging) return;
            panel.style.left = Math.max(10, Math.min(initialLeft + e.clientX - startX, window.innerWidth - panel.offsetWidth - 10)) + 'px';
            panel.style.top = Math.max(10, Math.min(initialTop + e.clientY - startY, window.innerHeight - panel.offsetHeight - 10)) + 'px';
            panel.style.right = 'auto';
        });
        
        document.addEventListener('mouseup', () => {
            if (isDragging) { isDragging = false; panel.style.opacity = '1'; }
        });
    }
    
    // ====== Bridge通信 ======
    
    initBridge() {
        new QWebChannel(qt.webChannelTransport, (channel) => {
            this.bridge = channel.objects.bridge;
            this.bridgeReady = true;
            console.log('[Map] ✓ Bridge connected');
            
            if (typeof this.bridge.searchResults !== 'undefined') {
                this.bridge.searchResults.connect((data) => {
                    this.renderSearchResults(data);
                });
                console.log('[Map] ✓ Search results signal connected');
            }
            
            while (this.pendingActions.length > 0) {
                this.sendAction(this.pendingActions.shift());
            }
        });
    }
    
    sendAction(action) {
        if (!this.bridgeReady || !this.bridge) {
            this.pendingActions.push(action);
            return;
        }
        
        // ★ 如果在批量操作（Undo/Redo）期间，不发送任何信号到Python
        if (this.isBatchOperation) {
            return;  // 静默跳过所有bridge调用
        }
        
        try {
            switch (action.type) {
                case 'waypoint_added':
                case 'waypoint_inserted':
                    if (typeof this.bridge.addWaypoint === 'function') {
                        this.bridge.addWaypoint(action.data.index, action.data.lat, action.data.lon);
                    }
                    break;
                    
                case 'waypoint_removed':
                    // ★ 不再发送删除信号！避免双重删除
                    console.log('[Map] Blocked: waypoint_removed signal (prevents double delete)');
                    break;
                    
                case 'waypoint_edited':
                    if (typeof this.bridge.editWaypoint === 'function') {
                        this.bridge.editWaypoint(JSON.stringify(action.data));
                    } else {
                        console.warn('[Map] editWaypoint bridge method not found');
                    }
                    break;
                    
                case 'segment_edited':
                    if (typeof this.bridge.segmentEdited === 'function') {
                        this.bridge.segmentEdited(JSON.stringify(action.data));
                    } else {
                        console.warn('[Map] segmentEdited bridge method not found');
                    }
                    break;
                    
                case 'fence_point_added':
                case 'fence_point_insert':
                    if (typeof this.bridge.addFencePoint === 'function') {
                        this.bridge.addFencePoint(action.data.lat, action.data.lon);
                    }
                    break;
                    
                case 'geofence_created':
                    if (typeof this.bridge.createGeofence === 'function') {
                        this.bridge.createGeofence(action.data);
                    }
                    break;
                    
                case 'location_searched':
                    if (typeof this.bridge.locationSearched === 'function') {
                        this.bridge.locationSearched(action.data.lat, action.data.lng, action.data.name);
                    }
                    break;
                    
                default:
                    console.warn(`[Map] Unknown action: ${action.type}`);
            }
        } catch (e) {
            console.error(`[Map] Error sending ${action.type}:`, e.message);
        }
    }
}

// ====== 全局函数 ======

function toggleGPSPanel() {
    const panel = document.getElementById('info-panel');
    if (!panel) return false;
    const isVisible = panel.style.display !== 'none';
    panel.style.display = isVisible ? 'none' : 'block';
    localStorage.setItem('gps_panel_visible', isVisible ? 'false' : 'true');
    return !isVisible;
}

window.onload = () => {
    console.log('[Map] Window loaded');
    window.inavMap = new INAVMap();
    
    setTimeout(() => {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) {
            overlay.style.opacity = '0';
            setTimeout(() => overlay.style.display = 'none', 300);
        }
    }, 1000);
};
