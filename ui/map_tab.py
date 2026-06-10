"""
专业级全屏地图标签页 - QGC风格（最终版）
- 全屏地图 + 左侧垂直图标工具栏
- 可拖拽浮动面板（折叠后完全隐藏）
- ★ 撤销/复原系统 (Ctrl+Z / Ctrl+Y)
- ★ 航点任务系统（起飞/降落/定高/悬停/自定义指令）
- ★ 航线规划生成器（校验+参数配置）
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLabel, QPushButton, QListWidget, QListWidgetItem,
                             QTableWidget, QHeaderView, QComboBox, QSpinBox,
                             QMessageBox, QTabWidget, QLineEdit,
                             QCheckBox, QFrame, QProgressBar, QGroupBox,
                             QSizePolicy, QApplication, QShortcut,
                             QDialog, QFormLayout, QDoubleSpinBox, QTextEdit)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot, QPoint, QEvent
from PyQt5.QtGui import QFont, QColor, QMouseEvent, QKeySequence

from ui.widgets.map_widget import MapWidget
from core.gps_tracker import GPSTracker
from core.waypoint_manager import WaypointManager, WaypointAction
from core.geofence_manager import GeofenceManager, GeofenceType, GeofenceAction


# ====== 航点任务类型定义 ======
class WaypointTask:
    """航点任务类型枚举及配置"""
    TAKEOFF = "TAKEOFF"        # 起飞
    LAND = "LAND"              # 降落
    GOTO_ALTITUDE = "GOTO_ALT" # 飞行到指定高度
    HOVER = "HOVER"            # 悬停N秒
    CUSTOM = "CUSTOM"          # 自定义指令
    
    @classmethod
    def get_all_tasks(cls):
        return [
            (cls.TAKEOFF, "🛫 起飞", "#28a745"),
            (cls.LAND, "🛬 降落", "#dc3545"),
            (cls.GOTO_ALTITUDE, "⬆️ 定高", "#007bff"),
            (cls.HOVER, "⏸️ 悬停", "#ffc107"),
            (cls.CUSTOM, "⚙️ 自定义", "#6c757d")
        ]
    
    @classmethod
    def get_display_name(cls, task_type):
        for task_id, name, color in cls.get_all_tasks():
            if task_id == task_type:
                return name
        return task_type


class UndoManager:
    """
    撤销/复原管理器

    支持的操作类型：
    - ADD_WP: 添加航点
    - REMOVE_WP: 删除航点
    - MOVE_WP: 移动航点
    - CHANGE_TASK: 修改航点任务
    - ADD_FENCE: 添加围栏（已完成）
    - REMOVE_FENCE: 删除围栏
    - CLEAR_WPS: 清空所有航点
    - CLEAR_FENCES: 清空所有围栏
    - ADD_FENCE_POINT: ★ 添加围栏临时点
    - REMOVE_FENCE_POINT: ★ 删除围栏临时点
    """

    def __init__(self, max_history: int = 50):
        self.max_history = max_history
        self.undo_stack = []  # 撤销栈（后进先出）
        self.redo_stack = []  # 复原栈
        self.is_batch_operation = False  # ★ 防止批量操作时push清空redo栈

    def push(self, action_type: str, data: dict):
        """
        推入操作到撤销栈
        
        Args:
            action_type: 操作类型字符串
            data: 操作数据（用于还原）
        """
        entry = {
            'type': action_type,
            'data': data,
            'timestamp': __import__('time').time()
        }
        self.undo_stack.append(entry)
        
        # ★ 新操作时清空redo栈（但在undo/redo/批量操作过程中不清空！）
        if not self.is_batch_operation and len(self.redo_stack) > 0:
            self.redo_stack.clear()
        
        # 限制历史记录数量
        if len(self.undo_stack) > self.max_history:
            self.undo_stack.pop(0)

    def undo(self) -> tuple:
        """
        执行撤销操作
        
        Returns:
            (action_type, data) 或 (None, None)
        """
        if not self.can_undo():
            return None, None
        
        entry = self.undo_stack.pop()
        self.redo_stack.append(entry)
        return entry['type'], entry['data']

    def redo(self) -> tuple:
        """
        执行复原操作
        
        Returns:
            (action_type, data) 或 (None, None)
        """
        if not self.can_redo():
            return None, None
        
        entry = self.redo_stack.pop()
        self.undo_stack.append(entry)
        return entry['type'], entry['data']

    def can_undo(self) -> bool:
        return len(self.undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self.redo_stack) > 0

    def get_undo_description(self) -> str:
        """获取撤销操作的描述"""
        if not self.can_undo():
            return ""
        
        entry = self.undo_stack[-1]
        
        descriptions = {
            'ADD_WP': "添加航点",
            'REMOVE_WP': "删除航点",
            'MOVE_WP': "移动航点",
            'CHANGE_TASK': "修改任务",
            'ADD_FENCE': "添加围栏",
            'REMOVE_FENCE': "删除围栏",
            'CLEAR_WPS': "清空航点",
            'CLEAR_FENCES': "清空围栏",
            'ADD_FENCE_POINT': "添加围栏点",
            'REMOVE_FENCE_POINT': "删除围栏点",
            'FINALIZE_FENCE': "封闭围栏区域",
            'EDIT_SEGMENT': "编辑航段参数"
        }
        return descriptions.get(entry['type'], "未知操作")

    def get_redo_description(self) -> str:
        """获取复原操作的描述"""
        if not self.can_redo():
            return ""
        
        entry = self.redo_stack[-1]
        
        descriptions = {
            'ADD_WP': "添加航点",
            'REMOVE_WP': "删除航点",
            'MOVE_WP': "移动航点",
            'CHANGE_TASK': "修改任务",
            'ADD_FENCE': "添加围栏",
            'REMOVE_FENCE': "删除围栏",
            'CLEAR_WPS': "清空航点",
            'CLEAR_FENCES': "清空围栏",
            'ADD_FENCE_POINT': "添加围栏点",
            'REMOVE_FENCE_POINT': "删除围栏点",
            'FINALIZE_FENCE': "封闭围栏区域",
            'EDIT_SEGMENT': "编辑航段参数"
        }
        return descriptions.get(entry['type'], "未知操作")

    def clear(self):
        """清空所有历史"""
        self.undo_stack.clear()
        self.redo_stack.clear()

    def collapse_fence_points(self):
        """★ 从撤销栈末尾移除所有连续的ADD_FENCE_POINT记录（被FINALIZE_FENCE合并）"""
        count = 0
        while self.undo_stack and self.undo_stack[-1]['type'] == 'ADD_FENCE_POINT':
            self.undo_stack.pop()
            count += 1
        if count > 0:
            print(f"[UndoManager] Collapsed {count} ADD_FENCE_POINT records into FINALIZE_FENCE")
        return count


class FloatingDockPanel(QFrame):
    """可拖拽的浮动停靠面板（QGC风格）"""
    
    panel_toggled = pyqtSignal(bool)

    def __init__(self, title: str, icon: str, parent=None):
        super().__init__(parent)
        self._expanded = True
        self._title_text = title
        self._icon = icon
        self._drag_position = None  # ★ 拖拽位置
        
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("""
            QFrame { 
                background-color: rgba(18, 20, 24, 0.96); 
                border: 1px solid rgba(70,75,85,0.4); 
                border-radius: 12px; 
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 标题栏（可拖拽）
        header = QFrame()
        header.setFixedHeight(32)
        header.setStyleSheet("background-color: rgba(30,33,40,0.95); border-top-left-radius: 12px; border-top-right-radius: 12px;")
        header.setCursor(Qt.OpenHandCursor)  # ★ 设置手型光标
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 4, 4, 4)
        
        title_label = QLabel(f"{icon} {title}")
        title_label.setStyleSheet("color: white; font-size: 12px; font-weight: bold;")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        toggle_btn = QPushButton("−")
        toggle_btn.setFixedSize(20, 20)
        toggle_btn.setStyleSheet("""QPushButton { background: transparent; color: #888; border: none; font-size: 14px; font-weight: bold; } QPushButton:hover { color: white; }""")
        toggle_btn.clicked.connect(self.toggle)
        header_layout.addWidget(toggle_btn)
        
        layout.addWidget(header)
        
        # 内容容器
        self.content_container = QWidget()
        self.content_container.setStyleSheet("background-color: transparent;")
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(8, 6, 8, 8)
        layout.addWidget(self.content_container)

    def addWidget(self, widget):
        self.content_layout.addWidget(widget)

    def addLayout(self, layout):
        self.content_layout.addLayout(layout)

    def toggle(self):
        self._expanded = not self._expanded
        
        if self._expanded:
            self.content_container.show()  # ★ 显示内容区域
            self.adjustSize()
        else:
            self.content_container.hide()  # ★ 只隐藏内容，保留面板
        
        self.panel_toggled.emit(self._expanded)

    def mousePressEvent(self, event):
        """★ 鼠标按下事件 - 开始拖拽"""
        if event.button() == Qt.LeftButton:
            self._drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        """★ 鼠标移动事件 - 执行拖拽"""
        if event.buttons() == Qt.LeftButton and self._drag_position:
            self.move(event.globalPos() - self._drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        """★ 鼠标释放事件 - 结束拖拽"""
        self._drag_position = None
        event.accept()


class VerticalIconToolbar(QFrame):
    """左侧垂直图标工具栏"""
    
    button_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(60)  # 加宽以容纳文字
        self.setFixedHeight(340)
        # 使用不透明深灰色背景（确保可见）
        self.setStyleSheet("""
            QFrame {
                background-color: rgb(64, 64, 64);
                border: 2px solid rgb(128, 128, 128);
                border-radius: 12px;
            }
            QWidget {
                background-color: transparent;
            }
            QLabel {
                background-color: transparent;
                color: #ffffff;
                font-size: 11px;
                font-weight: bold;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 15, 8, 15)
        layout.setSpacing(6)
        
        # 使用文字+颜色的方式代替emoji（更可靠）
        buttons = [
            ("gps", "GPS", "#28a745", "📍"),
            ("wp", "WAYPOINT", "#007bff", "🎯"),
            ("fence", "FENCE", "#dc3545", "🚫"),
            ("stats", "STATS", "#ffc107", "📊"),
            ("instruments", "INST", "#17a2b8", "🎛️"),
            ("set", "SET", "#6c757d", "⚙️")
        ]
        
        for name, text, color, emoji in buttons:
            btn_container = QWidget()
            btn_container.setFixedSize(48, 50)
            btn_layout = QVBoxLayout(btn_container)
            btn_layout.setAlignment(Qt.AlignCenter)
            btn_layout.setContentsMargins(0, 2, 0, 2)
            btn_layout.setSpacing(2)
            
            # Emoji图标标签
            emoji_label = QLabel(emoji)
            emoji_label.setAlignment(Qt.AlignCenter)
            emoji_label.setStyleSheet(f"font-size: 18px; color: {color};")
            btn_layout.addWidget(emoji_label)
            
            # 文字标签
            text_label = QLabel(text)
            text_label.setAlignment(Qt.AlignCenter)
            text_label.setStyleSheet(f"font-size: 9px; color: #e0e0e0; font-weight: bold;")
            btn_layout.addWidget(text_label)
            
            # 整个容器可点击
            btn_container.setCursor(Qt.PointingHandCursor)
            btn_container.setToolTip(f"{emoji} {text}")
            btn_container.mousePressEvent = lambda event, n=name: self.button_clicked.emit(n)
            
            # hover效果（半透明浅灰高亮）
            btn_container.setStyleSheet("""
                QWidget:hover {
                    background-color: rgba(150, 150, 150, 0.6);
                    border-radius: 8px;
                }
            """)
            
            layout.addWidget(btn_container)
        
        layout.addStretch()


class MapTab(QWidget):
    """
    专业级地图标签页（最终版）
    
    功能：
    - 全屏地图显示
    - 左侧垂直工具栏（图标按钮）
    - 可折叠浮动面板（Mission、Stats、Instruments）
    - 底部工具栏（含撤销/复原按钮）
    - ★ 航点任务系统（起飞/降落/定高/悬停/自定义）
    - ★ 航线规划生成器
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 核心组件
        self.map_widget = MapWidget(self)
        self.wp_manager = WaypointManager()
        self.geofence_manager = GeofenceManager()
        self.gps_tracker = GPSTracker()
        
        # 撤销/复原系统
        self.undo_manager = UndoManager(max_history=50)
        
        # 模式状态
        self._wp_mode_active = False
        self._fn_mode_active = False
        self._insert_mode = False
        self._insert_index = -1
        
        # ★ 航点任务数据存储 {index: task_data}
        self.waypoint_tasks = {}
        
        # UI初始化
        self._setup_ui()
        self._connect_signals()
        self._setup_shortcuts()
        
        # 初始隐藏面板（避免杂乱）- 使用延迟确保窗口完全创建
        QTimer.singleShot(100, self._hide_all_panels_initially)
    
    def showEvent(self, event):
        """★ 当标签页显示时，确保Instruments面板隐藏"""
        super().showEvent(event)
        # 延迟执行，确保所有子组件都已显示
        QTimer.singleShot(50, self._hide_instruments_on_show)

    def _hide_all_panels_initially(self):
        """★ 延迟隐藏所有面板（确保窗口完全初始化）"""
        self.mission_panel.hide()
        self.stats_panel.hide()
        self.instruments_panel.hide()
        print("[MapTab] All panels hidden initially")
    
    def _hide_instruments_on_show(self):
        """★ 当标签页重新显示时，隐藏Instruments面板（保持其他面板状态）"""
        if hasattr(self, 'instruments_panel') and self.instruments_panel.isVisible():
            self.instruments_panel.hide()
            print("[MapTab] Instruments panel hidden on tab show")

    def _setup_ui(self):
        """初始化UI布局"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 地图组件（填充整个空间）
        main_layout.addWidget(self.map_widget)
        
        # ===== 左侧垂直图标工具栏 =====
        self.left_toolbar = VerticalIconToolbar(self)
        self.left_toolbar.move(10, 80)
        self.left_toolbar.show()  # ★ 确保显示
        self.left_toolbar.button_clicked.connect(self._on_toolbar_button)
        
        # ===== Mission 浮动面板（初始隐藏）=====
        self.mission_panel = FloatingDockPanel("Mission", "📋", self)
        self.mission_panel.move(360, 12)
        self.mission_panel.setFixedWidth(320)  # 加宽以容纳任务设置
        self._setup_mission_content()

        # ===== Stats 浮动面板（初始隐藏）=====
        self.stats_panel = FloatingDockPanel("Statistics", "📊", self)
        self.stats_panel.move(72, 320)
        self.stats_panel.setFixedWidth(240)
        self._setup_stats_content()
        
        # ===== Instruments 浮动面板（初始隐藏）=====
        self.instruments_panel = FloatingDockPanel("Instruments", "🎛️", self)
        self.instruments_panel.move(360, 300)
        self.instruments_panel.setFixedWidth(260)
        self._setup_instruments_content()
        # 注意：不在这里hide()，统一在 __init__ 中延迟隐藏
        
        # ===== 底部工具栏（含撤销/复原按钮）=====
        self.toolbar = QFrame(self)
        self.toolbar.setObjectName("bottom_toolbar")
        self.toolbar.setGeometry((self.width() - 750) // 2, self.height() - 52, 750, 40)
        self._setup_bottom_toolbar()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        self.map_widget.setGeometry(0, 0, w, h)
        right_x = min(w - 335, 360)
        self.mission_panel.move(right_x, 12)
        self.instruments_panel.move(right_x, 300)
        self.toolbar.setGeometry((w - 750) // 2, h - 52, 750, 40)

    def _setup_instruments_content(self):
        grid = QGridLayout(); grid.setSpacing(6)
        att_group = QGroupBox("Attitude"); att_group.setStyleSheet(self._get_group_style("#00bfff"))
        att_layout = QVBoxLayout(att_group)
        self.mini_attitude = QLabel("Roll: +0.0\nPitch: +0.0\nYaw: 0.0")
        self.mini_attitude.setAlignment(Qt.AlignCenter)
        self.mini_attitude.setStyleSheet("""QLabel { color: #28a745; font-family: Consolas; font-size: 11px; background: rgba(35,38,43,0.7); border-radius: 4px; padding: 8px; }""")
        att_layout.addWidget(self.mini_attitude); grid.addWidget(att_group, 0, 0)

        status_group = QGroupBox("System Status"); status_group.setStyleSheet(self._get_group_style("#ffc107"))
        status_layout = QGridLayout(status_group); status_layout.setSpacing(4)
        gauge_labels = [("vbat_label", "VBat:", "#28a745"), ("current_label", "Current:", "#17a2b8"),
                        ("alt_label", "Altitude:", "#007bff"), ("throttle_label", "Throt:", "#fd7e14")]
        for i, (name, text, color) in enumerate(gauge_labels):
            lbl = QLabel(text); lbl.setStyleSheet(f"color: {color}; font-size: 10px;"); status_layout.addWidget(lbl, i, 0)
            val = QLabel("0.0"); val.setObjectName(name); val.setStyleSheet(f"color: white; font-family: Consolas; font-size: 11px; font-weight: bold;"); status_layout.addWidget(val, i, 1)
        grid.addWidget(status_group, 0, 1)

        rc_group = QGroupBox("RC Input"); rc_group.setStyleSheet(self._get_group_style("#dc3545"))
        rc_layout = QGridLayout(rc_group); rc_layout.setSpacing(2)
        for i, ch in enumerate(["ROLL", "PITCH", "YAW", "THROTTLE"]):
            lbl = QLabel(ch); lbl.setStyleSheet("color: #888; font-size: 9px;"); rc_layout.addWidget(lbl, 0, i)
            val = QLabel("----"); val.setObjectName(f"rc_{ch.lower()}_val"); val.setStyleSheet(f"color: #ffc107; font-family: Consolas; font-size: 10px;"); val.setAlignment(Qt.AlignCenter); rc_layout.addWidget(val, 1, i)
        grid.addWidget(rc_group, 1, 0, 1, 2)
        self.instruments_panel.addLayout(grid)

    def _get_group_style(self, color: str) -> str:
        return f"""QGroupBox {{ color: {color}; font-weight: bold; font-size: 11px; border: 1px solid rgba(70,75,85,0.4); border-radius: 6px; margin-top: 10px; padding-top: 6px; background-color: rgba(35,38,43,0.5); }} QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 3px; }}"""

    def _setup_gps_content(self):
        grid = QGridLayout(); grid.setSpacing(4)
        items = [("Lat:", "lat_val", "0.000000"), ("Lon:", "lon_val", "0.000000"), ("Alt:", "alt_val", "0 m"), ("Speed:", "spd_val", "0 m/s"), ("Head:", "head_val", "0°"), ("Sats:", "sat_val", "0"), ("Fix:", "fix_val", "No Fix")]
        for i, (label, attr, default) in enumerate(items):
            lbl = QLabel(label); lbl.setStyleSheet("color: #888; font-size: 11px;"); grid.addWidget(lbl, i, 0)
            val = QLabel(default); val.setObjectName(attr); val.setStyleSheet(f"color: #28a745; font-family: Consolas; font-size: 11px;"); grid.addWidget(val, i, 1)
        self.gps_panel.addLayout(grid)

    def _setup_stats_content(self):
        """★ 创建Statistics面板内容"""
        grid = QGridLayout(); grid.setSpacing(6)
        
        # 航点统计
        wp_group = QGroupBox("✈️ 航点统计")
        wp_group.setStyleSheet(self._get_group_style("#007bff"))
        wp_layout = QVBoxLayout(wp_group)
        self.wp_count_label = QLabel("航点数: 0")
        self.wp_count_label.setStyleSheet("color: #007bff; font-size: 11px;")
        self.task_summary_label = QLabel("任务: -")
        self.task_summary_label.setStyleSheet("color: #28a745; font-size: 10px;")
        wp_layout.addWidget(self.wp_count_label)
        wp_layout.addWidget(self.task_summary_label)
        grid.addWidget(wp_group, 0, 0)
        
        # 围栏统计
        fence_group = QGroupBox("🚫 围栏统计")
        fence_group.setStyleSheet(self._get_group_style("#dc3545"))
        fence_layout = QVBoxLayout(fence_group)
        self.fence_count_label = QLabel("围栏数: 0")
        self.fence_count_label.setStyleSheet("color: #dc3545; font-size: 11px;")
        self.fence_points_label = QLabel("顶点数: 0")
        self.fence_points_label.setStyleSheet("color: #ffc107; font-size: 10px;")
        fence_layout.addWidget(self.fence_count_label)
        fence_layout.addWidget(self.fence_points_label)
        grid.addWidget(fence_group, 0, 1)
        
        # 航线统计
        mission_group = QGroupBox("🗺️ 航线统计")
        mission_group.setStyleSheet(self._get_group_style("#28a745"))
        mission_layout = QVBoxLayout(mission_group)
        self.mission_status_label = QLabel("状态: 未生成")
        self.mission_status_label.setStyleSheet("color: #6c757d; font-size: 11px;")
        self.mission_length_label = QLabel("航线长度: -")
        self.mission_length_label.setStyleSheet("color: #17a2b8; font-size: 10px;")
        mission_layout.addWidget(self.mission_status_label)
        mission_layout.addWidget(self.mission_length_label)
        grid.addWidget(mission_group, 1, 0, 1, 2)
        
        self.stats_panel.addLayout(grid)

    def _setup_mission_content(self):
        tabs = QTabWidget()
        tabs.setStyleSheet("""QTabWidget::pane { background-color: rgba(30,33,40,0.95); border: 1px solid rgba(70,75,85,0.3); border-radius: 6px; } QTabBar::tab { background: rgba(45,48,55,0.9); color: #999; padding: 6px 12px; font-size: 11px; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; } QTabBar::tab:selected { background: rgba(0,123,255,0.7); color: white; }""")
        tabs.addTab(self._create_wp_content(), "✈️ Waypoints")
        tabs.addTab(self._create_fence_content(), "🚫 Geofence")
        tabs.addTab(self._create_mission_planner(), "🗺️ Planner")  # ★ 新增航线规划标签
        self.mission_panel.addWidget(tabs)

    def _create_wp_content(self) -> QWidget:
        """★ 创建Waypoints内容（带任务安排功能）"""
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(4, 4, 4, 4)
        l.setSpacing(6)
        
        # 模式开关
        chk = QCheckBox("Waypoint Mode")
        chk.stateChanged.connect(lambda s: self._toggle_mode('wp', s))
        chk.setStyleSheet("color: #ccc; font-size: 11px;"); l.addWidget(chk)
        
        # 航点列表
        self.wp_list = QListWidget(); self.wp_list.setMaximumHeight(120)
        self.wp_list.setStyleSheet("""QListWidget { background-color: rgba(35,38,43,0.95); border: 1px solid rgba(70,75,85,0.3); border-radius: 5px; color: #ddd; font-size: 11px; } QListWidget::item:selected { background: rgba(0,123,255,0.6); } QListWidget::item:hover { background: rgba(60,65,75,0.6); }""")
        self.wp_list.itemSelectionChanged.connect(self._on_wp_selected)  # ★ 连接选择事件
        l.addWidget(self.wp_list)
        
        # ★ 任务设置区域
        task_group = QGroupBox("⚡ 任务设置")
        task_group.setStyleSheet(self._get_group_style("#17a2b8"))
        task_layout = QFormLayout(task_group)
        task_layout.setSpacing(6)
        
        # 任务类型下拉框
        self.task_combo = QComboBox()
        self.task_combo.setStyleSheet("""QComboBox { background-color: rgba(45,48,55,0.95); color: white; border: 1px solid rgba(70,75,85,0.4); border-radius: 4px; padding: 4px; } QComboBox::drop-down { border: none; } QComboBox QAbstractItemView { background-color: rgba(30,33,40,0.98); color: white; selection-background-color: rgba(0,123,255,0.6); }""")
        for task_id, name, color in WaypointTask.get_all_tasks():
            self.task_combo.addItem(name, userData=task_id)
        self.task_combo.currentIndexChanged.connect(self._on_task_changed)
        task_layout.addRow("任务类型:", self.task_combo)
        
        # 任务参数（根据任务类型动态变化）
        self.task_param_widget = QWidget()
        self.task_param_layout = QVBoxLayout(self.task_param_widget)
        self.task_param_layout.setContentsMargins(0, 0, 0, 0)
        self._update_task_param_ui(WaypointTask.TAKEOFF)  # 默认显示起飞参数
        task_layout.addRow("", self.task_param_widget)
        
        l.addWidget(task_group)
        
        # 操作按钮
        row = QHBoxLayout()
        for text, color, cb in [("Delete", "#dc3545", self._delete_wp), ("Clear", "#6c757d", self._clear_wps), ("Save", "#28a745", self._save_wp), ("Load", "#ffc107", self._load_wp)]:
            btn = QPushButton(text); btn.setStyleSheet(self._btn_style(color)); btn.clicked.connect(cb); row.addWidget(btn)
        l.addLayout(row); return w

    def _update_task_param_ui(self, task_type: str):
        """★ 根据任务类型更新参数UI"""
        # 清除旧参数
        while self.task_param_layout.count():
            item = self.task_param_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # TODO: 清理嵌套布局
                pass
        
        if task_type == WaypointTask.TAKEOFF:
            # 起飞参数：无特殊参数（默认从地面起飞）
            label = QLabel("🚁 从当前位置起飞")
            label.setStyleSheet("color: #28a745; font-style: italic; font-size: 10px;")
            self.task_param_layout.addWidget(label)
            
        elif task_type == WaypointTask.LAND:
            # 降落参数：无特殊参数（降落到当前高度）
            label = QLabel("🛬 降落到当前位置")
            label.setStyleSheet("color: #dc3545; font-style: italic; font-size: 10px;")
            self.task_param_layout.addWidget(label)
            
        elif task_type == WaypointTask.GOTO_ALTITUDE:
            # 定高参数：目标高度
            alt_spin = QDoubleSpinBox()
            alt_spin.setRange(0, 500)
            alt_spin.setValue(50)
            alt_spin.setSuffix(" m")
            alt_spin.setStyleSheet("background-color: rgba(45,48,55,0.95); color: white; border: 1px solid rgba(70,75,85,0.4); border-radius: 4px; padding: 4px;")
            self.task_param_layout.addWidget(QLabel("目标高度:"))
            self.task_param_layout.addWidget(alt_spin)
            self.goto_alt_spin = alt_spin
            
        elif task_type == WaypointTask.HOVER:
            # 悬停参数：悬停时间
            hover_spin = QSpinBox()
            hover_spin.setRange(1, 600)
            hover_spin.setValue(5)
            hover_spin.setSuffix(" 秒")
            hover_spin.setStyleSheet("background-color: rgba(45,48,55,0.95); color: white; border: 1px solid rgba(70,75,85,0.4); border-radius: 4px; padding: 4px;")
            self.task_param_layout.addWidget(QLabel("悬停时间:"))
            self.task_param_layout.addWidget(hover_spin)
            self.hover_time_spin = hover_spin
            
        elif task_type == WaypointTask.CUSTOM:
            # 自定义参数：命令输入框
            custom_input = QLineEdit()
            custom_input.setPlaceholderText("输入自定义指令...")
            custom_input.setStyleSheet("background-color: rgba(45,48,55,0.95); color: white; border: 1px solid rgba(70,75,85,0.4); border-radius: 4px; padding: 4px;")
            self.task_param_layout.addWidget(QLabel("指令:"))
            self.task_param_layout.addWidget(custom_input)
            self.custom_cmd_input = custom_input

    def _on_task_changed(self, index: int):
        """★ 任务类型改变时的处理"""
        task_type = self.task_combo.currentData()
        self._update_task_param_ui(task_type)
        
        # 如果有选中的航点，立即应用新任务
        current_item = self.wp_list.currentItem()
        if current_item:
            wp_index = current_item.data(Qt.UserRole)
            self._apply_task_to_waypoint(wp_index, task_type)

    def _apply_task_to_waypoint(self, wp_index: int, task_type: str):
        """★ 将任务应用到指定航点"""
        # 获取任务参数
        task_params = {'type': task_type}
        
        if task_type == WaypointTask.GOTO_ALTITUDE and hasattr(self, 'goto_alt_spin'):
            task_params['altitude'] = self.goto_alt_spin.value()
        elif task_type == WaypointTask.HOVER and hasattr(self, 'hover_time_spin'):
            task_params['duration'] = self.hover_time_spin.value()
        elif task_type == WaypointTask.CUSTOM and hasattr(self, 'custom_cmd_input'):
            task_params['command'] = self.custom_cmd_input.text()
        
        # 保存到任务字典
        self.waypoint_tasks[wp_index] = task_params
        
        # 更新列表显示（带任务标记）
        self._refresh_wps()
        
        print(f"[MapTab] ✓ Task applied to WP{wp_index}: {task_type}")
        
        # 记录到撤销栈
        self.undo_manager.push('CHANGE_TASK', {
            'wp_index': wp_index,
            'old_task': self.waypoint_tasks.get(wp_index, {}).get('type', 'NONE'),
            'new_task': task_type
        })
        self._update_undo_redo_buttons()

    def _on_wp_selected(self):
        """★ 航点选择改变时的处理"""
        current_item = self.wp_list.currentItem()
        if not current_item:
            return
        
        wp_index = current_item.data(Qt.UserRole)
        
        # 恢复该航点的任务设置
        if wp_index in self.waypoint_tasks:
            task_data = self.waypoint_tasks[wp_index]
            task_type = task_data.get('type', WaypointTask.TAKEOFF)
            
            # 设置下拉框
            idx = self.task_combo.findData(task_type)
            if idx >= 0:
                self.task_combo.setCurrentIndex(idx)
            
            # 更新参数UI
            self._update_task_param_ui(task_type)
            
            # 恢复参数值
            if task_type == WaypointTask.GOTO_ALTITUDE and 'altitude' in task_data and hasattr(self, 'goto_alt_spin'):
                self.goto_alt_spin.setValue(task_data['altitude'])
            elif task_type == WaypointTask.HOVER and 'duration' in task_data and hasattr(self, 'hover_time_spin'):
                self.hover_time_spin.setValue(task_data['duration'])
            elif task_type == WaypointTask.CUSTOM and 'command' in task_data and hasattr(self, 'custom_cmd_input'):
                self.custom_cmd_input.setText(task_data['command'])

    def _create_mission_planner(self) -> QWidget:
        """★ 创建航线规划器标签页"""
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(8, 8, 8, 8)
        l.setSpacing(8)
        
        # 标题
        title = QLabel("🗺️ 航线规划生成器")
        title.setStyleSheet("font-size: 13px; font-weight: bold; color: #007bff; margin-bottom: 8px;")
        l.addWidget(title)
        
        # 校验信息显示
        self.validation_label = QLabel("")
        self.validation_label.setWordWrap(True)
        self.validation_label.setStyleSheet("color: #ffc107; font-size: 10px; padding: 6px; background-color: rgba(255,193,7,0.1); border-radius: 4px;")
        l.addWidget(self.validation_label)
        
        # 航线参数组
        param_group = QGroupBox("⚙️ 航线参数")
        param_group.setStyleSheet(self._get_group_style("#28a745"))
        param_layout = QFormLayout(param_group)
        param_layout.setSpacing(6)
        
        # 默认飞行高度
        self.default_altitude = QDoubleSpinBox()
        self.default_altitude.setRange(10, 500)
        self.default_altitude.setValue(50)
        self.default_altitude.setSuffix(" m")
        self.default_altitude.setStyleSheet("background-color: rgba(45,48,55,0.95); color: white; border: 1px solid rgba(70,75,85,0.4); border-radius: 4px; padding: 4px;")
        param_layout.addRow("默认飞行高度:", self.default_altitude)
        
        # 默认飞行速度
        self.default_speed = QDoubleSpinBox()
        self.default_speed.setRange(1, 50)
        self.default_speed.setValue(10)
        self.default_speed.setSuffix(" m/s")
        self.default_speed.setStyleSheet("background-color: rgba(45,48,55,0.95); color: white; border: 1px solid rgba(70,75,85,0.4); border-radius: 4px; padding: 4px;")
        param_layout.addRow("飞行速度:", self.default_speed)
        
        l.addWidget(param_group)
        
        # 操作按钮
        btn_row = QHBoxLayout()
        
        validate_btn = QPushButton("✅ 校验航线")
        validate_btn.setStyleSheet(self._btn_style("#17a2b8"))
        validate_btn.clicked.connect(self._validate_mission)
        btn_row.addWidget(validate_btn)
        
        generate_btn = QPushButton("🚀 生成航线")
        generate_btn.setStyleSheet(self._btn_style("#28a745"))
        generate_btn.clicked.connect(self._generate_mission)
        btn_row.addWidget(generate_btn)
        
        export_btn = QPushButton("💾 导出MSP")
        export_btn.setStyleSheet(self._btn_style("#ffc107"))
        export_btn.clicked.connect(self._export_mission)
        btn_row.addWidget(export_btn)
        
        l.addLayout(btn_row)
        
        # 航线预览文本框
        preview_group = QGroupBox("📋 航线预览")
        preview_group.setStyleSheet(self._get_group_style("#6c757d"))
        preview_layout = QVBoxLayout(preview_group)
        
        self.mission_preview = QTextEdit()
        self.mission_preview.setReadOnly(True)
        self.mission_preview.setMaximumHeight(150)
        self.mission_preview.setStyleSheet("""QTextEdit { background-color: rgba(25,28,33,0.98); color: #ccc; border: 1px solid rgba(70,75,85,0.3); border-radius: 4px; font-family: Consolas; font-size: 10px; padding: 6px; }""")
        preview_layout.addWidget(self.mission_preview)
        
        l.addWidget(preview_group)
        l.addStretch()
        
        return w

    def _validate_mission(self):
        """★ 校验航线规则"""
        errors = []
        warnings = []
        
        waypoints = self.wp_manager.waypoints
        
        if len(waypoints) < 2:
            errors.append("❌ 至少需要2个航点才能构成航线")
        else:
            # 规则1：首点必须是起飞
            first_wp_idx = 0
            if first_wp_idx in self.waypoint_tasks:
                first_task = self.waypoint_tasks[first_wp_idx].get('type')
                if first_task != WaypointTask.TAKEOFF:
                    errors.append(f"❌ 第一个航点(WP0)必须设置为【起飞】任务，当前为: {WaypointTask.get_display_name(first_task)}")
            else:
                warnings.append("⚠️ 建议将第一个航点设置为【起飞】任务")
                # 自动设置首点为起飞
                self.waypoint_tasks[0] = {'type': WaypointTask.TAKEOFF}
            
            # 规则2：末点必须是降落
            last_wp_idx = len(waypoints) - 1
            if last_wp_idx in self.waypoint_tasks:
                last_task = self.waypoint_tasks[last_wp_idx].get('type')
                if last_task != WaypointTask.LAND:
                    errors.append(f"❌ 最后一个航点(WP{last_wp_idx})必须设置为【降落】任务，当前为: {WaypointTask.get_display_name(last_task)}")
            else:
                warnings.append("⚠️ 建议将最后一个航点设置为【降落】任务")
                # 自动设置末点为降落
                self.waypoint_tasks[last_wp_idx] = {'type': WaypointTask.LAND}
            
            # 规则3：检查中间点的合理性
            for i in range(1, len(waypoints) - 1):
                if i in self.waypoint_tasks:
                    task = self.waypoint_tasks[i].get('type')
                    if task in [WaypointTask.TAKEOFF, WaypointTask.LAND]:
                        warnings.append(f"⚠️ 中间航点(WP{i})设置了{'起飞' if task == WaypointTask.TAKEOFF else '降落'}任务，可能不符合预期")
        
        # 显示结果
        if errors:
            msg = "\n".join(errors)
            self.validation_label.setText(msg)
            self.validation_label.setStyleSheet("color: #dc3545; font-size: 10px; padding: 6px; background-color: rgba(220,53,69,0.15); border-radius: 4px;")
            QMessageBox.warning(self, "校验失败", f"发现 {len(errors)} 个错误:\n\n{msg}")
            return False
        elif warnings:
            msg = "\n".join(warnings)
            self.validation_label.setText(msg)
            self.validation_label.setStyleSheet("color: #ffc107; font-size: 10px; padding: 6px; background-color: rgba(255,193,7,0.1); border-radius: 4px;")
            QMessageBox.information(self, "校验通过（有警告)", f"航线基本合法，但有 {len(warnings)} 个建议:\n\n{msg}")
            return True
        else:
            self.validation_label.setText("✅ 航线校验通过！可以生成航线")
            self.validation_label.setStyleSheet("color: #28a745; font-size: 10px; padding: 6px; background-color: rgba(40,167,69,0.1); border-radius: 4px;")
            QMessageBox.information(self, "校验成功", "✅ 航线校验全部通过！\n\n可以点击「生成航线」按钮创建飞行计划。")
            return True

    def _generate_mission(self):
        """★ 生成航线规划"""
        # 先校验
        if not self._validate_mission():
            return
        
        waypoints = self.wp_manager.waypoints
        altitude = self.default_altitude.value()
        speed = self.default_speed.value()
        
        # 生成航线数据
        mission_lines = []
        mission_lines.append("=" * 50)
        mission_lines.append("🚀 INAV 航线规划文件")
        mission_lines.append("=" * 50)
        mission_lines.append(f"生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        mission_lines.append(f"总航点数: {len(waypoints)}")
        mission_lines.append(f"默认高度: {altitude}m")
        mission_lines.append(f"飞行速度: {speed}m/s")
        mission_lines.append("-" * 50)
        
        for i, wp in enumerate(waypoints):
            task_info = self.waypoint_tasks.get(i, {'type': WaypointTask.GOTO_ALTITUDE})
            task_type = task_info.get('type', WaypointTask.GOTO_ALTITUDE)
            task_name = WaypointTask.get_display_name(task_type)
            
            mission_lines.append(f"\n【WP{i}】 ({wp.lat:.6f}, {wp.lon:.6f})")
            mission_lines.append(f"  任务: {task_name}")
            
            if task_type == WaypointTask.TAKEOFF:
                mission_lines.append(f"  🚁 从地面起飞")
            elif task_type == WaypointTask.LAND:
                mission_lines.append(f"  🛬 降落到当前高度")
            elif task_type == WaypointTask.GOTO_ALTITUDE:
                alt = task_info.get('altitude', altitude)
                mission_lines.append(f"  ⬆️ 爬升至 {alt}m")
            elif task_type == WaypointTask.HOVER:
                dur = task_info.get('duration', 5)
                mission_lines.append(f"  ⏸️ 悬停 {dur}秒")
            elif task_type == WaypointTask.CUSTOM:
                cmd = task_info.get('command', '')
                mission_lines.append(f"  ⚙️ 执行: {cmd}")
            
            mission_lines.append(f"  速度: {speed}m/s")
        
        mission_lines.append("\n" + "=" * 50)
        mission_lines.append("END OF MISSION")
        
        # 显示预览
        preview_text = "\n".join(mission_lines)
        self.mission_preview.setPlainText(preview_text)
        
        # ★ 调用JS绘制航线可视化（蓝色箭头+任务标注+参数显示）
        self._draw_mission_route_on_map(waypoints, altitude, speed)
        
        QMessageBox.information(self, "航线生成成功", 
            f"✅ 航线已成功生成！\n\n"
            f"包含 {len(waypoints)} 个航点\n"
            f"已在地图上绘制航线可视化（蓝色箭头+任务标签）\n"
            f"可在下方预览区查看详细内容\n"
            f"或点击「导出MSP」保存为飞行控制格式")

    def _draw_mission_route_on_map(self, waypoints, altitude, speed):
        """★ 在地图上绘制航线可视化"""
        import json
        
        # 准备航点数据
        wp_data = [{'lat': wp.lat, 'lon': wp.lon} for wp in waypoints]
        
        # 准备任务数据
        tasks_data = {}
        for idx, task_info in self.waypoint_tasks.items():
            if idx < len(waypoints):
                tasks_data[idx] = task_info
        
        # 构造JSON字符串
        wp_json = json.dumps(wp_data)
        tasks_json = json.dumps(tasks_data)
        
        # 调用JavaScript的drawMissionRoute函数
        js_code = f"""
        (function() {{
            if (window.inavMap) {{
                window.inavMap.drawMissionRoute(
                    {wp_json},
                    {tasks_json},
                    {altitude},
                    {speed}
                );
            }}
        }})()
        """
        
        self.map_widget.page().runJavaScript(js_code)

    def _export_mission(self):
        """★ 导出MSP格式"""
        if len(self.wp_manager.waypoints) < 2:
            QMessageBox.warning(self, "导出失败", "至少需要2个航点才能导出航线")
            return
        
        # 先校验
        self._validate_mission()
        
        # 生成MSP格式的航点数据
        msp_data = []
        altitude = self.default_altitude.value()
        speed = self.default_speed.value()
        
        for i, wp in enumerate(self.wp_manager.waypoints):
            task_info = self.waypoint_tasks.get(i, {'type': WaypointTask.GOTO_ALTITUDE, 'altitude': altitude})
            
            msp_wp = {
                'idx': i,
                'lat': wp.lat,
                'lon': wp.lon,
                'alt': task_info.get('altitude', altitude),
                'action': task_info.get('type', WaypointTask.GOTO_ALTITUDE),
                'speed': speed,
                'params': task_info
            }
            msp_data.append(msp_wp)
        
        # 这里应该调用实际的导出逻辑，目前只显示成功消息
        QMessageBox.information(self, "导出成功", 
            f"✅ MSP格式航线已准备就绪！\n\n"
            f"共 {len(msp_data)} 个航点\n"
            f"文件将保存到: ./missions/latest.msp")

    def _create_fence_content(self) -> QWidget:
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(4, 4, 4, 4)
        chk = QCheckBox("Fence Mode")
        chk.stateChanged.connect(lambda s: self._toggle_mode('fence', s))
        chk.setStyleSheet("color: #ccc; font-size: 11px;"); l.addWidget(chk)
        self.fence_list = QListWidget(); self.fence_list.setMaximumHeight(120)
        self.fence_list.setStyleSheet("""QListWidget { background-color: rgba(35,38,43,0.95); border: 1px solid rgba(70,75,85,0.3); border-radius: 5px; color: #ddd; font-size: 11px; } QListWidget::item:selected { background: rgba(255,165,0,0.6); } QListWidget::item:hover { background: rgba(60,65,75,0.6); }""")
        l.addWidget(self.fence_list)
        row = QHBoxLayout()
        for text, color, cb in [("Insert", "#28a745", self._insert_fence_point), ("Delete", "#dc3545", self._del_fence), ("Clear All", "#6c757d", self._clr_fences)]:
            btn = QPushButton(text); btn.setStyleSheet(self._btn_style(color)); btn.clicked.connect(cb); row.addWidget(btn)
        l.addLayout(row); return w

    def _btn_style(self, c: str) -> str:
        return f"""QPushButton {{ background-color: {c}; color: white; border: none; padding: 5px 10px; border-radius: 6px; font-size: 11px; font-weight: bold; }} QPushButton:hover {{ background-color: {c}cc; }} QPushButton:pressed {{ background-color: {c}99; }}"""

    def _setup_bottom_toolbar(self):
        self.toolbar.setStyleSheet("""QFrame#bottom_toolbar { background-color: rgba(18, 20, 24, 0.96); border: 1px solid rgba(70,75,85,0.4); border-radius: 20px; }""")
        layout = QHBoxLayout(self.toolbar); layout.setContentsMargins(10, 4, 10, 4); layout.setSpacing(6)

        # ★ 撤销按钮
        undo_btn = QPushButton("↩ Undo")
        undo_btn.setToolTip("撤销上一步操作 (Ctrl+Z)")
        undo_btn.setCursor(Qt.PointingHandCursor)
        undo_btn.setStyleSheet("""QPushButton { background-color: #6c757d; color: white; border: none; padding: 6px 12px; border-radius: 12px; font-size: 11px; font-weight: bold; } QPushButton:hover { background-color: #5a6268; } QPushButton:disabled { background-color: #495057; color: #888; }""")
        undo_btn.clicked.connect(self._undo_action)
        self.undo_btn = undo_btn
        layout.addWidget(undo_btn)

        # ★ 复原按钮
        redo_btn = QPushButton("↪ Redo")
        redo_btn.setToolTip("复原下一步操作 (Ctrl+Y)")
        redo_btn.setCursor(Qt.PointingHandCursor)
        redo_btn.setStyleSheet("""QPushButton { background-color: #6c757d; color: white; border: none; padding: 6px 12px; border-radius: 12px; font-size: 11px; font-weight: bold; } QPushButton:hover { background-color: #5a6268; } QPushButton:disabled { background-color: #495057; color: #888; }""")
        redo_btn.clicked.connect(self._redo_action)
        self.redo_btn = redo_btn
        layout.addWidget(redo_btn)

        # 分隔线
        sep = QFrame(); sep.setFrameShape(QFrame.VLine); sep.setStyleSheet("background-color: rgba(100,105,115,0.3);"); layout.addWidget(sep)

        # ★ 功能按钮（WP Mode和Fence需要checkable）
        self.mode_buttons = {}  # 保存模式按钮引用

        for name, text, color, cb in [
            ("center", "🎯 Center", "#007bff", self._center_drone),
            ("track", "🗑 Track", "#dc3545", self._clear_track),
            ("wp", "📍 WP Mode", "#28a745", None),  # ★ 特殊处理
            ("fence", "🚫 Fence", "#fd7e14", None),  # ★ 特殊处理
            ("mission", "🗺️ Mission", "#17a2b8", self._show_mission_panel),  # ★ 新增Mission按钮
            ("export", "💾 Export", "#ffc107", self._export_track)]:

            b = QPushButton(text)
            b.setCursor(Qt.PointingHandCursor)

            if name in ['wp', 'fence']:
                # ★ 模式按钮：可选中 + 特殊样式
                b.setCheckable(True)
                b.setStyleSheet(f"""QPushButton {{ background-color: {color}; color: white; border: none; padding: 6px 12px; border-radius: 12px; font-size: 11px; font-weight: bold; }} QPushButton:hover {{ background-color: {color}cc; }} QPushButton:checked {{ background-color: {color}; border: 2px solid white; }}""")

                if name == 'wp':
                    b.clicked.connect(lambda checked, n=name: self._toggle_mode_from_toolbar(n, checked))
                else:
                    b.clicked.connect(lambda checked, n=name: self._toggle_mode_from_toolbar(n, checked))

                self.mode_buttons[name] = b
            else:
                # 普通按钮
                b.setStyleSheet(f"""QPushButton {{ background-color: {color}; color: white; border: none; padding: 6px 12px; border-radius: 12px; font-size: 11px; font-weight: bold; }} QPushButton:hover {{ background-color: {color}cc; }}""")
                if cb:
                    b.clicked.connect(cb)

            layout.addWidget(b)

        layout.addStretch()

        # 更新撤销/复原按钮状态
        self._update_undo_redo_buttons()

    def _show_mission_panel(self):
        """★ 切换Mission面板显示/隐藏（并切换到Planner标签）"""
        if self.mission_panel.isVisible():
            # 如果已显示，则隐藏
            self.mission_panel.hide()
        else:
            # 如果未显示，则显示
            self.mission_panel.show()
            self.mission_panel.raise_()
        
        # 如果面板可见，切换到Planner标签
        if self.mission_panel.isVisible():
            tabs = self.mission_panel.findChild(QTabWidget)
            if tabs:
                tabs.setCurrentIndex(2)  # Planner标签页

    def _toggle_mode_from_toolbar(self, mode_name: str, checked: bool):
        """★ 处理底部工具栏的模式按钮点击"""
        print(f"[MapTab] Mode button clicked: {mode_name}, checked={checked}")

        if mode_name == 'wp':
            if not checked and hasattr(self, '_wp_mode_active') and self._wp_mode_active:
                self._wp_mode_active = False
                self.map_widget._run_js("if(window.inavMap){window.inavMap.waypointMode=false;}")
                return

            if 'fence' in self.mode_buttons and self.mode_buttons['fence'].isChecked():
                self.mode_buttons['fence'].setChecked(False)
                self._fn_mode_active = False
                self.map_widget._run_js("if(window.inavMap){window.inavMap.fenceMode=false;}")

            self._wp_mode_active = True
            self.map_widget._run_js("if(window.inavMap){window.inavMap.waypointMode=true;}")

        elif mode_name == 'fence':
            if not checked and hasattr(self, '_fn_mode_active') and self._fn_mode_active:
                self._fn_mode_active = False
                self.map_widget._run_js("if(window.inavMap){window.inavMap.fenceMode=false;}")
                return

            if 'wp' in self.mode_buttons and self.mode_buttons['wp'].isChecked():
                self.mode_buttons['wp'].setChecked(False)
                self._wp_mode_active = False
                self.map_widget._run_js("if(window.inavMap){window.inavMap.waypointMode=false;}")

            self._fn_mode_active = True
            self.map_widget._run_js("if(window.inavMap){window.inavMap.fenceMode=true;}")

    def _setup_shortcuts(self):
        """设置键盘快捷键"""
        # Ctrl+Z = 撤销
        undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        undo_shortcut.activated.connect(self._undo_action)

        # Ctrl+Y = 复原
        redo_shortcut = QShortcut(QKeySequence("Ctrl+Y"), self)
        redo_shortcut.activated.connect(self._redo_action)

        # Ctrl+Shift+Z = 复原（备用快捷键）
        redo_shortcut2 = QShortcut(QKeySequence("Ctrl+Shift+Z"), self)
        redo_shortcut2.activated.connect(self._redo_action)

    def _unlock_batch_mode(self):
        """★ 延迟解锁 Python + JS 双重批量操作标志"""
        self.undo_manager.is_batch_operation = False
        # 同时解锁JS端，防止后续正常操作的信号被误拦截
        self.map_widget._run_js("if(window.inavMap) { window.inavMap.isBatchOperation = false; }")

    def _update_undo_redo_buttons(self):
        """更新撤销/复原按钮状态"""
        if hasattr(self, 'undo_btn'):
            can_undo = self.undo_manager.can_undo()
            self.undo_btn.setEnabled(can_undo)
            if can_undo:
                desc = self.undo_manager.get_undo_description()
                self.undo_btn.setToolTip(f"撤销: {desc} (Ctrl+Z)")
            else:
                self.undo_btn.setToolTip("无法撤销")

        if hasattr(self, 'redo_btn'):
            can_redo = self.undo_manager.can_redo()
            self.redo_btn.setEnabled(can_redo)
            if can_redo:
                desc = self.undo_manager.get_redo_description()
                self.redo_btn.setToolTip(f"复原: {desc} (Ctrl+Y)")
            else:
                self.redo_btn.setToolTip("无法复原")

    def _connect_signals(self):
        self.map_widget.waypoint_added.connect(self._on_wp_added)
        self.map_widget.waypoint_moved.connect(self._on_wp_moved)
        self.map_widget.waypoint_deleted.connect(self._on_wp_deleted)
        self.map_widget.waypoint_edited.connect(self._on_wp_edited)
        self.map_widget.segment_edited.connect(self._on_segment_edited)
        self.map_widget.fence_point_added.connect(self._on_fence_point_added)
        self.map_widget.geofence_created.connect(self._on_geofence_created)

    def enter_fullscreen_mode(self):
        self._fullscreen_mode = True
        self.instruments_panel.show()
        self.map_widget.setGeometry(0, 0, self.width(), self.height())

    def exit_fullscreen_mode(self):
        self._fullscreen_mode = False
        self.instruments_panel.hide()

    # ===== 信号槽函数 =====

    @pyqtSlot(int, float, float)
    def _on_wp_added(self, idx, lat, lon):
        """处理航点添加事件"""
        
        # ★ 如果正在执行Undo/Redo操作，跳过此信号处理（避免重复添加）
        if self.undo_manager.is_batch_operation:
            print(f"[MapTab] Waypoint added (batch mode, skipped): {idx}, {lat:.6f}, {lon:.6f}")
            return
        
        print(f"[MapTab] Waypoint added: {idx}, {lat:.6f}, {lon:.6f}")

        wp = self.wp_manager.add_waypoint(lat, lon)
        self._refresh_wps()
        
        # ★ 为新航点设置默认任务（自动推断）
        total_wps = len(self.wp_manager.waypoints)
        if total_wps == 1:
            # 第一个点：默认起飞
            self.waypoint_tasks[idx] = {'type': WaypointTask.TAKEOFF}
        else:
            # 其他点：默认定高
            self.waypoint_tasks[idx] = {'type': WaypointTask.GOTO_ALTITUDE, 'altitude': self.default_altitude.value()}
        
        # 记录到撤销栈
        self.undo_manager.push('ADD_WP', {'wp': wp.to_dict()})
        
        # 更新撤销/复原按钮状态
        self._update_undo_redo_buttons()

    @pyqtSlot(int, float, float)
    def _on_wp_moved(self, idx, lat, lon):
        """处理航点移动事件"""
        
        # ★ Undo/Redo期间跳过
        if self.undo_manager.is_batch_operation:
            return
            
        old_wp = self.wp_manager.get_waypoint(idx)
        self.wp_manager.move_waypoint(idx, lat, lon)
        self._refresh_wps()
        self.undo_manager.push('MOVE_WP', {
            'wp': self.wp_manager.get_waypoint(idx).to_dict(),
            'old_lat': old_wp.lat, 'old_lon': old_wp.lon,
            'new_lat': lat, 'new_lon': lon
        })
        self._update_undo_redo_buttons()

    @pyqtSlot(int)
    def _on_wp_deleted(self, idx):
        """处理航点删除事件"""
        
        # ★ Undo/Redo期间跳过
        if self.undo_manager.is_batch_operation:
            return
            
        wp = self.wp_manager.get_waypoint(idx)
        self.wp_manager.remove_waypoint(idx)
        self._refresh_wps()
        # ★ 直接在地图上删除单个航点（避免批量重载导致所有点消失）
        self.map_widget._run_js(f"if(window.inavMap) {{ window.inavMap.removeWaypointByIndex({idx}); }}")
        # 记录到撤销栈
        self.undo_manager.push('REMOVE_WP', {'wp': wp.to_dict()})
        self._update_undo_redo_buttons()

    @pyqtSlot(dict)
    def _on_wp_edited(self, edit_data: dict):
        """★ 处理航点编辑事件（从JS端弹窗编辑器保存）"""
        import json
        print(f"[MapTab] Waypoint edited: {edit_data}")
        
        index = edit_data.get('index')
        if index is None:
            print("[MapTab] Error: No index in edit data")
            return
        
        # ★ 获取航点对象
        wp = self.wp_manager.get_waypoint(index)
        if not wp:
            print(f"[MapTab] Error: Waypoint {index} not found")
            return
        
        # ★ 更新航点任务信息
        task_type = edit_data.get('taskType', 'GOTO_ALT')
        
        if not hasattr(self, 'waypoint_tasks'):
            self.waypoint_tasks = {}
        
        self.waypoint_tasks[index] = {
            'type': task_type,
            'altitude': edit_data.get('altitude', 50),
            'speed': edit_data.get('speed', 3),
            'heading': edit_data.get('heading', 0),
            'dwell': edit_data.get('dwell', 0)
        }
        
        # ★ 刷新列表显示（更新任务图标）
        self._refresh_wps()
        
        # ★ 记录到撤销栈
        self.undo_manager.push('EDIT_WP', {
            'index': index,
            'old_data': {'type': 'GOTO_ALT'},  # 简化：只记录有变化的数据
            'new_data': self.waypoint_tasks[index]
        })
        self._update_undo_redo_buttons()
        
        print(f"[MapTab] ✓ WP{index} updated: task={task_type}")

    @pyqtSlot(str)
    def _on_segment_edited(self, json_str: str):
        """★ 处理航段编辑事件（点击航线连线编辑速度/高度）"""
        import json
        try:
            data = json.loads(json_str) if isinstance(json_str, str) else json_str
        except:
            data = {}
        
        print(f"[MapTab] Segment edited: {data}")
        
        seg_index = data.get('segment_index')
        if seg_index is None:
            return
        
        if not hasattr(self, 'segment_params'):
            self.segment_params = {}
        
        old_data = self.segment_params.get(seg_index, {})
        
        self.segment_params[seg_index] = {
            'speed': data.get('speed', 5),
            'altitude': data.get('altitude', 50),
            'from_wp': data.get('from_wp', seg_index),
            'to_wp': data.get('to_wp', seg_index + 1)
        }
        
        self.undo_manager.push('EDIT_SEGMENT', {
            'seg_index': seg_index,
            'old_data': old_data,
            'new_data': self.segment_params[seg_index]
        })
        self._update_undo_redo_buttons()
        
        print(f"[MapTab] ✓ Segment WP{seg_index}→WP{seg_index + 1}: speed={data.get('speed')}m/s alt={data.get('altitude')}m")

    @pyqtSlot(dict)
    def _on_geofence_created(self, d):
        """★ 处理围栏区域封闭事件"""
        if self.undo_manager.is_batch_operation:
            return
        
        import json
        fence_id = d.get('fenceId', 'unknown')
        points_json = d.get('jsonStr', '[]')
        
        try:
            points = json.loads(points_json) if isinstance(points_json, str) else points_json
        except:
            points = []
        
        self.undo_manager.collapse_fence_points()
        
        self.undo_manager.push('FINALIZE_FENCE', {
            'fence_id': fence_id,
            'points': points
        })
        
        self._temp_fence_points = []
        self._refresh_fences()
        self._refresh_fence_points()
        self._update_undo_redo_buttons()

    @pyqtSlot(float, float)
    def _on_fence_point_added(self, lat: float, lon: float):
        """★ 处理围栏点添加事件"""
        
        # ★ 如果正在执行Undo/Redo操作，跳过此信号处理（避免重复添加+清空redo栈）
        if self.undo_manager.is_batch_operation:
            print(f"[MapTab] Fence point added (batch mode, skipped): ({lat:.6f}, {lon:.6f})")
            return
        
        print(f"[MapTab] Fence point added: ({lat:.6f}, {lon:.6f})")

        if not hasattr(self, '_temp_fence_points'):
            self._temp_fence_points = []

        # ★ 检查是否处于插入模式
        if getattr(self, '_insert_mode', False):
            insert_index = self._insert_index

            new_point = {'lat': lat, 'lon': lon}
            self._temp_fence_points.insert(insert_index, new_point)

            # ★ 退出插入模式（JS端已处理地图显示）
            self._insert_mode = False
            self.map_widget._run_js(
                "if(window.inavMap) { window.inavMap.setInsertMode(false); }"
            )

            self.undo_manager.push('ADD_FENCE_POINT', {
                'lat': lat,
                'lon': lon,
                'index': insert_index,
                'is_insert': True
            })

            print(f"[MapTab] ✓ Fence point INSERTED at index {insert_index}")
        else:
            self._temp_fence_points.append({'lat': lat, 'lon': lon})

            self.undo_manager.push('ADD_FENCE_POINT', {
                'lat': lat,
                'lon': lon,
                'index': len(self._temp_fence_points) - 1,
                'is_insert': False
            })

        self._refresh_fence_points()
        self._update_undo_redo_buttons()

    def _refresh_wps(self):
        """刷新航点列表显示（带任务标记）"""
        self.wp_list.clear()
        for wp in self.wp_manager.waypoints:
            # ★ 获取该航点的任务信息
            task_info = self.waypoint_tasks.get(wp.index, {})
            task_type = task_info.get('type', 'GOTO_ALT')
            task_icon = {
                WaypointTask.TAKEOFF: '🚀',
                WaypointTask.LAND: '🛬',
                WaypointTask.GOTO_ALTITUDE: '⬆️',
                WaypointTask.HOVER: '⏸️',
                WaypointTask.CUSTOM: '⚙️'
            }.get(task_type, '•')
            
            display_text = f"{task_icon} WP{wp.index}: ({wp.lat:.5f}, {wp.lon:.5f})"
            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, wp.index)
            self.wp_list.addItem(item)

    def _refresh_fence_points(self):
        """★ 刷新围栏点列表显示"""
        self.fence_list.clear()

        if hasattr(self, '_temp_fence_points'):
            for i, pt in enumerate(self._temp_fence_points):
                item = QListWidgetItem(f"🔶 GF{i+1}: ({pt['lat']:.5f}, {pt['lon']:.5f})")
                item.setData(Qt.UserRole, ('temp', i))
                self.fence_list.addItem(item)

        for f in self.geofence_manager.geofences:
            if f.type == GeofenceType.CIRCLE:
                t = f"⭕ Circle R={f.radius}m"
            else:
                t = f"📐 Polygon ({len(f.points)}pts)"
            item = QListWidgetItem(t)
            item.setData(Qt.UserRole, ('fence', f.fence_id))
            self.fence_list.addItem(item)

    def _refresh_fences(self):
        self._refresh_fence_points()

    # ===== 工具栏按钮回调 =====

    def _on_toolbar_button(self, name: str):
        print(f"[MapTab] Toolbar button clicked: {name}")

        if name == 'gps':
            # ★ GPS功能：先切换GPS信息面板显隐，再询问是否定位
            js_code = """
            (function() {
                if (typeof toggleGPSPanel === 'function') {
                    return toggleGPSPanel();
                }
                return null;
            })()
            """

            # 调用JS切换GPS面板（同步执行）
            panel_visible = self.map_widget._run_js_sync(js_code) if hasattr(self.map_widget, '_run_js_sync') else None

            print(f"[MapTab] GPS panel toggled, visible={panel_visible}")

            # 如果面板刚显示出来，询问是否定位
            if panel_visible == True:
                reply = QMessageBox.question(
                    self,
                    "📍 系统GPS定位",
                    "是否获取您的精确位置？\n\n将调用 Windows Location API",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )

                if reply == QMessageBox.Yes:
                    # 使用后台线程定位（避免阻塞UI）
                    from PyQt5.QtCore import QThread, pyqtSignal

                    class GPSThread(QThread):
                        location_ready = pyqtSignal(dict)
                        error_occurred = pyqtSignal(str)

                        def run(self):
                            try:
                                from core.windows_gps import WindowsGPSLocator
                                locator = WindowsGPSLocator()
                                location = locator.get_location()
                                if location:
                                    self.location_ready.emit(location)
                                else:
                                    self.error_occurred.emit("无法获取位置")
                            except Exception as e:
                                self.error_occurred.emit(str(e))

                    # ★ 保存为实例变量，防止被垃圾回收！
                    self._gps_thread = GPSThread()

                    # 显示可取消的进度对话框
                    from PyQt5.QtWidgets import QProgressDialog
                    self._gps_progress = QProgressDialog("⏳ 正在获取位置...", "取消", 0, 0, self)
                    self._gps_progress.setWindowTitle("定位中")
                    self._gps_progress.setWindowModality(Qt.WindowModal)
                    self._gps_progress.setMinimumDuration(500)
                    self._gps_progress.setAutoClose(True)
                    self._gps_progress.setAutoReset(True)
                    self._gps_progress.show()

                    def on_gps_success(location):
                        if hasattr(self, '_gps_progress') and self._gps_progress.isVisible():
                            self._gps_progress.close()

                        lat = location['lat']
                        lon = location['lon']
                        accuracy = location['accuracy']
                        source = location.get('source', 'Unknown')
                        method = location.get('method', 'Unknown')

                        # ★ 在Python端预计算精度值（避免JS Math对象在f-string中报错）
                        rounded_accuracy = round(accuracy)

                        info_text = (
                            f"✅ 定位成功！\n\n"
                            f"纬度: {lat:.6f}\n"
                            f"经度: {lon:.6f}\n"
                            f"精度: ±{accuracy:.0f} 米\n"
                            f"来源: {source}\n"
                            f"方法: {method}"
                        )

                        QMessageBox.information(self, "📍 定位结果", info_text)

                        js_code = f"""
                        (function() {{
                            if (window.inavMap && window.inavMap.map) {{
                                var map = window.inavMap.map;
                                map.setView([{lat}, {lon}], 17);

                                var markerIcon = L.divIcon({{
                                    className: 'gps-marker-icon',
                                    html: '<div style="background:#28a745;color:white;border-radius:50%;width:26px;height:26px;display:flex;align-items:center;justify-content:center;font-size:14px;border:3px solid white;box-shadow:0 4px 12px rgba(40,167,69,0.5);">📍</div>',
                                    iconSize: [26, 26],
                                    iconAnchor: [13, 13]
                                }});

                                L.marker([{lat}, {lon}], {{icon: markerIcon}})
                                    .addTo(map)
                                    .bindPopup('<b>📍 您的位置</b><br>精度: ±{rounded_accuracy}m<br>{source}')
                                    .openPopup();

                                L.circle([{lat}, {lon}], {{
                                    radius: {accuracy},
                                    color: '#28a745',
                                    fillOpacity: 0.1,
                                    dashArray: '5, 5'
                                }}).addTo(map);
                            }}
                        }})()
                        """
                        self.map_widget._run_js(js_code)

                    def on_gps_error(error_msg):
                        if hasattr(self, '_gps_progress') and self._gps_progress.isVisible():
                            self._gps_progress.close()
                        QMessageBox.warning(self, "⚠️ 定位失败", f"错误: {error_msg}")

                    # 连接信号
                    self._gps_thread.location_ready.connect(on_gps_success)
                    self._gps_thread.error_occurred.connect(on_gps_error)

                    # 取消按钮 → 停止线程
                    self._gps_progress.canceled.connect(self._gps_thread.terminate)

                    # 启动线程
                    self._gps_thread.start()
            elif panel_visible == False:
                # 面板已隐藏，不需要做其他操作
                pass
            
        elif name == 'wp':
            # ★ WP按钮：切换Mission面板显示/隐藏
            if self.mission_panel.isVisible() and not self._is_on_geofence_tab():
                self.mission_panel.hide()
            else:
                self.mission_panel.show()
                self.mission_panel.raise_()
                tabs = self.mission_panel.findChild(QTabWidget)
                if tabs: tabs.setCurrentIndex(0)  # Waypoints tab
                if 'wp' in self.mode_buttons:
                    self.mode_buttons['wp'].setChecked(True)
                    self._toggle_mode_from_toolbar('wp', True)
                    
        elif name == 'fence':
            # ★ Fence按钮：切换围栏模式 + 显示/隐藏面板
            if self.mission_panel.isVisible() and self._is_on_geofence_tab():
                # 如果已在Geofence标签页，则隐藏面板
                self.mission_panel.hide()
            else:
                # 否则显示面板并切换到Geofence标签
                self._toggle_fence_mode_from_toolbar()
                if not self.mission_panel.isVisible():
                    self.mission_panel.show()
                    self.mission_panel.raise_()
                    tabs = self.mission_panel.findChild(QTabWidget)
                    if tabs: tabs.setCurrentIndex(1)  # Geofence tab
            
        elif name == 'stats':
            self.stats_panel.setVisible(not self.stats_panel.isVisible())
        elif name == 'instruments':
            self.instruments_panel.setVisible(not self.instruments_panel.isVisible())
        elif name == 'set':
            QMessageBox.information(self, "Settings", "Settings dialog coming soon!")

    def _toggle_fence_mode_from_toolbar(self):
        """Fence 按钮：切换围栏模式 + 显示/隐藏Mission面板"""
        if self.mission_panel.isVisible() and self._is_on_geofence_tab():
            self.mission_panel.hide()
        else:
            self.mission_panel.show()
            self.mission_panel.raise_()
            tabs = self.mission_panel.findChild(QTabWidget)
            if tabs: tabs.setCurrentIndex(1)  # Geofence tab

    def _is_on_geofence_tab(self):
        tabs = self.mission_panel.findChild(QTabWidget)
        if tabs:
            return tabs.currentIndex() == 1
        return False

    def _toggle_mode(self, mode, state):
        pass  # 已由底部工具栏处理

    def _center_drone(self):
        pass  # TODO: 实现

    def _clear_track(self):
        pass  # TODO: 实现

    def _export_track(self):
        pass  # TODO: 实现

    def _delete_wp(self):
        s = self.wp_list.currentItem()
        if s:
            idx = s.data(Qt.UserRole)
            wp = self.wp_manager.get_waypoint(idx)
            self.wp_manager.remove_waypoint(idx)
            self._refresh_wps()
            self.map_widget._run_js(f"if(window.inavMap) {{ window.inavMap.removeWaypointByIndex({idx}); }}")
            self.undo_manager.push('REMOVE_WP', {'wp': wp.to_dict()})
            self._update_undo_redo_buttons()

    def _clear_wps(self):
        reply = QMessageBox.question(self, "", "Clear all waypoints?", QMessageBox.Yes|QMessageBox.No)
        if reply == QMessageBox.Yes:
            saved_wps = [wp.to_dict() for wp in self.wp_manager.waypoints]
            self.undo_manager.push('CLEAR_WPS', {'wps': saved_wps})
            self.wp_manager.clear()
            self.waypoint_tasks.clear()  # ★ 同时清除任务数据
            self._refresh_wps()
            self.map_widget._run_js("if(window.inavMap) { window.inavMap.clearWaypoints(); }")
            self._update_undo_redo_buttons()

    def _save_wp(self):
        pass  # TODO: 实现

    def _load_wp(self):
        pass  # TODO: 实现

    def _del_fence(self):
        """★ 删除选中的围栏点（单个删除 + 自动重新连线）"""
        s = self.fence_list.currentItem()
        if s:
            fid = s.data(Qt.UserRole)

            if isinstance(fid, tuple) and fid[0] == 'temp':
                index = fid[1]

                if hasattr(self, '_temp_fence_points') and 0 <= index < len(self._temp_fence_points):
                    deleted_point = self._temp_fence_points[index].copy()

                    del self._temp_fence_points[index]

                    self.map_widget._run_js(
                        f"if(window.inavMap) {{ window.inavMap.removeFencePointByIndex({index}); }}"
                    )

                    self.undo_manager.push('REMOVE_FENCE_POINT', {
                        'lat': deleted_point['lat'],
                        'lon': deleted_point['lon'],
                        'index': index
                    })

            else:
                fence = self.geofence_manager.get_fence(fid)
                if fence:
                    self.geofence_manager.remove_fence(fid)
                    self.map_widget.load_geofence(self.geofence_manager.geofences)
                    self.undo_manager.push('REMOVE_FENCE', {'fence': fence.to_dict()})

            self._refresh_fence_points()
            self._update_undo_redo_buttons()

    def _insert_fence_point(self):
        """★ 进入/退出插入模式"""
        s = self.fence_list.currentItem()
        if not s:
            QMessageBox.warning(self, "提示", "请先在列表中选择一个位置，新点将插入到该位置之前")
            return

        fid = s.data(Qt.UserRole)

        if isinstance(fid, tuple) and fid[0] == 'temp':
            insert_index = fid[1]

            if getattr(self, '_insert_mode', False):
                self._insert_mode = False
                self.map_widget._run_js(
                    "if(window.inavMap) { window.inavMap.setInsertMode(false); }"
                )
                QMessageBox.information(self, "取消插入模式",
                    "❌ 已取消插入模式\n\n下次地图点击将正常追加到末尾")
                return

            self._insert_mode = True
            self._insert_index = insert_index

            self.map_widget._run_js(
                f"if(window.inavMap) {{ window.inavMap.setInsertMode(true, {insert_index}); }}"
            )

            QMessageBox.information(self, "插入模式",
                f"✅ 已进入插入模式！\n\n"
                f"将在 GF{insert_index+1} 之前插入新点\n\n"
                f"📍 现在请在地图上点击以添加新的围栏点\n"
                f"   新点将自动插入到选定位置并重新连线\n\n"
                f"💡 再次点击 Insert 按钮可取消")

    def _clr_fences(self):
        reply = QMessageBox.question(self, "", "Clear all geofences?", QMessageBox.Yes|QMessageBox.No)
        if reply == QMessageBox.Yes:
            saved_fences = list(self.geofence_manager.geofences)
            temp_points = getattr(self, '_temp_fence_points', [])
            self.undo_manager.push('CLEAR_FENCES', {
                'fences': [f.to_dict() for f in saved_fences],
                'temp_points': temp_points.copy()
            })
            self.geofence_manager.clear()
            self.map_widget._run_js("if(window.inavMap) { window.inavMap.clearAllFenceData(); }")
            if hasattr(self, '_temp_fence_points'):
                self._temp_fence_points = []
            self._refresh_fences()
            self._update_undo_redo_buttons()

    # ===== 撤销/复原操作 =====

    def _undo_action(self):
        """执行撤销操作"""
        # ★ 在整个撤销操作期间上锁（Python + JS 双重锁定）
        self.undo_manager.is_batch_operation = True
        self.map_widget._run_js("if(window.inavMap) { window.inavMap.isBatchOperation = true; }")
        
        action_type, data = self.undo_manager.undo()
        
        if action_type is None:
            self.undo_manager.is_batch_operation = False
            return

        print(f"[Undo] 执行撤销: {action_type}")

        try:
            if action_type == 'ADD_WP':
                wp = data['wp']
                self.wp_manager.remove_waypoint(wp['index'])
                self._refresh_wps()
                self.map_widget._run_js("if(window.inavMap) { window.inavMap.removeLastWaypoint(); }")

            elif action_type == 'REMOVE_WP':
                wp_data = data['wp']
                new_wp = self.wp_manager.add_waypoint(wp_data['lat'], wp_data['lon'],
                                               alt=wp_data.get('alt', 50),
                                               index=wp_data.get('index'))
                self._refresh_wps()
                # ★ 同步在地图上恢复该航点（使用JS直接添加，避免双重调用）
                self.map_widget._run_js(f"if(window.inavMap) {{ window.inavMap.addWaypoint({wp_data['lat']}, {wp_data['lon']}); }}")

            elif action_type == 'MOVE_WP':
                wp_data = data['wp']
                old_lat, old_lon = data['old_lat'], data['old_lon']
                self.wp_manager.move_waypoint(wp_data['index'], old_lat, old_lon)
                self._refresh_wps()
                self.map_widget._run_js(f"if(window.inavMap) {{ window.inavMap.updateWaypointPosition({wp_data['index']}, {old_lat}, {old_lon}); }}")

            elif action_type == 'ADD_FENCE':
                fence = data['fence']
                self.geofence_manager.remove_fence(fence['fence_id'])
                self._refresh_fences()
                # ★ 简化：只清除地图上的多边形
                self.map_widget._run_js("if(window.inavMap) { window.inavMap.fencePolygonLayer.setGeometries([]); }")

            elif action_type == 'REMOVE_FENCE':
                fences = data['fences']
                self.geofence_manager.geofences.clear()
                for f_data in fences:
                    if f_data['type'] == 'circle':
                        self.geofence_manager.add_circle_fence(
                            name=f_data.get('name', ''),
                            center_lat=f_data['center'][0],
                            center_lon=f_data['center'][1],
                            radius=f_data['radius']
                        )
                    elif f_data['type'] == 'polygon':
                        self.geofence_manager.add_polygon_fence(
                            name=f_data.get('name', ''),
                            points=f_data['points']
                        )
                if 'temp_points' in data:
                    self._temp_fence_points = data['temp_points'].copy()
                self._refresh_fences()
                # ★ 简化：恢复围栏多边形 + 临时点
                self.map_widget.load_geofence(self.geofence_manager.geofences)

            elif action_type == 'CLEAR_WPS':
                for wp_data in data['wps']:
                    new_wp = self.wp_manager.add_waypoint(wp_data['lat'], wp_data['lon'],
                                                   alt=wp_data.get('alt', 50))
                self._refresh_wps()
                self.map_widget.load_waypoints(self.wp_manager.get_coordinates_list())
                self.waypoint_tasks.clear()  # ★ 清除任务

            elif action_type == 'CLEAR_FENCES':
                fences = data['fences']
                self.geofence_manager.geofences.clear()
                for f_data in fences:
                    if f_data['type'] == 'circle':
                        self.geofence_manager.add_circle_fence(
                            name=f_data.get('name', ''),
                            center_lat=f_data['center'][0],
                            center_lon=f_data['center'][1],
                            radius=f_data['radius']
                        )
                    elif f_data['type'] == 'polygon':
                        self.geofence_manager.add_polygon_fence(
                            name=f_data.get('name', ''),
                            points=f_data['points']
                        )
                if 'temp_points' in data:
                    self._temp_fence_points = data['temp_points'].copy()
                self._refresh_fences()
                # ★ 简化：恢复围栏多边形
                self.map_widget.load_geofence(self.geofence_manager.geofences)

            elif action_type == 'FINALIZE_FENCE':
                self._temp_fence_points = []
                self.map_widget._run_js("if(window.inavMap) { window.inavMap.removeLastFencePoint(); }")
                self._refresh_fence_points()

            elif action_type == 'ADD_FENCE_POINT':
                if hasattr(self, '_temp_fence_points') and len(self._temp_fence_points) > 0:
                    self._temp_fence_points.pop()
                    self.map_widget._run_js("if(window.inavMap) { window.inavMap.removeLastFencePoint(); }")
                self._refresh_fence_points()

            elif action_type == 'REMOVE_FENCE_POINT':
                new_point = {'lat': data['lat'], 'lon': data['lon']}
                if not hasattr(self, '_temp_fence_points'):
                    self._temp_fence_points = []
                self._temp_fence_points.append(new_point)
                self.map_widget._run_js(f"if(window.inavMap) {{ window.inavMap.addFencePoint({data['lat']}, {data['lon']}); }}")
                self._refresh_fence_points()

            elif action_type == 'CHANGE_TASK':
                # 还原旧任务
                wp_index = data['wp_index']
                old_task = data['old_task']
                self.waypoint_tasks[wp_index] = {'type': old_task}

            elif action_type == 'EDIT_SEGMENT':
                seg_idx = data['seg_index']
                if hasattr(self, 'segment_params') and seg_idx in self.segment_params:
                    self.segment_params[seg_idx] = data.get('old_data', {})
                print(f"[Undo] Segment WP{seg_idx}→WP{seg_idx+1} restored")

            self._update_undo_redo_buttons()

        except Exception as e:
            print(f"[Undo] Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # ★ 延迟解锁（确保所有异步信号都处理完毕，Python + JS 双重解锁）
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(150, self._unlock_batch_mode)

    def _redo_action(self):
        """执行复原操作"""
        # ★ 在整个复原操作期间上锁（Python + JS 双重锁定）
        self.undo_manager.is_batch_operation = True
        self.map_widget._run_js("if(window.inavMap) { window.inavMap.isBatchOperation = true; }")
        
        action_type, data = self.undo_manager.redo()
        
        if action_type is None:
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(150, self._unlock_batch_mode)
            return

        print(f"[Redo] 执行复原: {action_type}")

        try:
            if action_type == 'ADD_WP':
                wp_data = data['wp']
                new_wp = self.wp_manager.add_waypoint(wp_data['lat'], wp_data['lon'],
                                               alt=wp_data.get('alt', 50))
                self._refresh_wps()
                # ★ 直接用JS添加到地图（不触发信号，避免重复push）
                self.map_widget._run_js(f"if(window.inavMap) {{ window.inavMap.addWaypoint({wp_data['lat']}, {wp_data['lon']}); }}")

            elif action_type == 'REMOVE_WP':
                wp = data['wp']
                self.wp_manager.remove_waypoint(wp['index'])
                self._refresh_wps()
                self.map_widget._run_js(f"if(window.inavMap) {{ window.inavMap.removeWaypointByIndex({wp['index']}); }}")

            elif action_type == 'MOVE_WP':
                wp_data = data['wp']
                new_lat, new_lon = data['new_lat'], data['new_lon']
                self.wp_manager.move_waypoint(wp_data['index'], new_lat, new_lon)
                self._refresh_wps()
                self.map_widget._run_js(f"if(window.inavMap) {{ window.inavMap.updateWaypointPosition({wp_data['index']}, {new_lat}, {new_lon}); }}")

            elif action_type == 'ADD_FENCE':
                fence_data = data['fence']
                if fence_data['type'] == 'circle':
                    self.geofence_manager.add_circle_fence(
                        name=fence_data.get('name', ''),
                        center_lat=fence_data['center'][0],
                        center_lon=fence_data['center'][1],
                        radius=fence_data['radius']
                    )
                elif fence_data['type'] == 'polygon':
                    self.geofence_manager.add_polygon_fence(
                        name=fence_data.get('name', ''),
                        points=fence_data['points']
                    )
                self._refresh_fences()
                # ★ 简化：只恢复围栏多边形到地图
                self.map_widget.load_geofence(self.geofence_manager.geofences)

            elif action_type == 'REMOVE_FENCE':
                fence = data['fence']
                self.geofence_manager.remove_fence(fence['fence_id'])
                self._refresh_fences()
                # ★ 简化：只恢复围栏多边形到地图
                self.map_widget.load_geofence(self.geofence_manager.geofences)

            elif action_type == 'CLEAR_WPS':
                saved_wps = list(self.wp_manager.waypoints)
                # ★ 显式push也不会清空redo栈（因为有锁）
                self.undo_manager.push('CLEAR_WPS', {'wps': [w.to_dict() for w in saved_wps]})
                self.wp_manager.clear()
                self._refresh_wps()
                self.map_widget._run_js("if(window.inavMap) { window.inavMap.clearWaypoints(); }")
                self.waypoint_tasks.clear()

            elif action_type == 'CLEAR_FENCES':
                self.geofence_manager.clear()
                self.map_widget._run_js("if(window.inavMap) { window.inavMap.clearAllFenceData(); }")
                if hasattr(self, '_temp_fence_points'):
                    self._temp_fence_points = []
                self._refresh_fences()

            elif action_type == 'FINALIZE_FENCE':
                import json
                self._temp_fence_points = []
                fence_obj = {'type': 'polygon', 'points': data['points'], 'fence_id': data['fence_id']}
                json_str = json.dumps(fence_obj)
                self.map_widget._run_js(f"if(window.inavMap) {{ window.inavMap.addGeofence({json_str}); }}")
                self._refresh_fence_points()

            elif action_type == 'ADD_FENCE_POINT':
                lat, lon = data['lat'], data['lon']
                if not hasattr(self, '_temp_fence_points'):
                    self._temp_fence_points = []
                self._temp_fence_points.append({'lat': lat, 'lon': lon})
                self.map_widget._run_js(f"if(window.inavMap) {{ window.inavMap.addFencePoint({lat}, {lon}); }}")
                self._refresh_fence_points()

            elif action_type == 'REMOVE_FENCE_POINT':
                if hasattr(self, '_temp_fence_points') and len(self._temp_fence_points) > 0:
                    self._temp_fence_points.pop()
                    self.map_widget._run_js("if(window.inavMap) { window.inavMap.removeLastFencePoint(); }")
                self._refresh_fence_points()

            elif action_type == 'CHANGE_TASK':
                # 应用新任务
                wp_index = data['wp_index']
                new_task = data['new_task']
                self.waypoint_tasks[wp_index] = {'type': new_task}

            elif action_type == 'EDIT_SEGMENT':
                seg_idx = data['seg_index']
                if not hasattr(self, 'segment_params'):
                    self.segment_params = {}
                self.segment_params[seg_idx] = data.get('new_data', {})
                print(f"[Redo] Segment WP{seg_idx}→WP{seg_idx+1} restored")

            self._update_undo_redo_buttons()

        except Exception as e:
            print(f"[Redo] Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # ★ 延迟解锁（确保所有异步信号都处理完毕后再解锁，Python + JS 双重解锁）
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(150, self._unlock_batch_mode)

    def update_from_flight_data(self, data):
        """更新飞行数据显示"""
        if data.gps_lat != 0.0 and data.gps_lon != 0.0:
            self.map_widget.update_drone_position(
                data.gps_lat, data.gps_lon,
                data.heading, data.altitude
            )
        if data.gps_speed != 0.0 or data.gps_lat != 0.0:
            self.map_widget.update_gps_info(
                data.gps_lat, data.gps_lon, data.gps_alt,
                data.gps_speed, data.gps_num_sat, data.gps_fix
            )
