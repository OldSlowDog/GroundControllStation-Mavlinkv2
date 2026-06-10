"""
仪表盘控件 (Gauge Widget) - 优化版
用于显示电压、电流、高度等数值
修复文字重叠问题，优化布局
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt, QRectF, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont
import math


class GaugeWidget(QWidget):
    """圆形仪表盘控件 - 优化版"""

    value_changed = pyqtSignal(float)

    def __init__(self, title: str = "", min_val: float = 0, max_val: float = 100,
                 unit: str = "", parent=None):
        super().__init__(parent)
        self.title = title
        self.min_val = min_val
        self.max_val = max_val
        self.unit = unit
        self.value = min_val
        self.warning_threshold = None
        self.critical_threshold = None

        # 增大最小尺寸以避免重叠
        self.setMinimumSize(160, 180)
        self.setMaximumSize(200, 220)

    def set_value(self, value: float):
        """设置当前值"""
        self.value = max(self.min_val, min(value, self.max_val))
        self.update()
        self.value_changed.emit(self.value)

    def set_warning_threshold(self, threshold: float):
        """设置警告阈值"""
        self.warning_threshold = threshold

    def set_critical_threshold(self, critical: float):
        """设置危险阈值"""
        self.critical_threshold = critical

    def get_color_for_value(self) -> QColor:
        """根据值返回对应颜色"""
        if self.critical_threshold and self.value >= self.critical_threshold:
            return QColor(220, 53, 69)  # 红色
        elif self.warning_threshold and self.value >= self.warning_threshold:
            return QColor(255, 193, 7)  # 黄色
        else:
            return QColor(40, 167, 69)   # 绿色

    def paintEvent(self, event):
        """绘制仪表盘 - 优化布局避免重叠"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()

        # 布局参数（重新分配空间）
        title_height = 22          # 标题区高度
        gauge_area_height = height - title_height - 35  # 圆弧+数值区
        
        margin = 8
        center_x = width // 2
        center_y = title_height + gauge_area_height // 2 - 5
        
        # 动态计算半径，确保不超出边界
        available_radius = min(
            (width - 2 * margin) // 2 - 10,
            (gauge_area_height) // 2 - 10
        )
        
        outer_radius = available_radius
        inner_radius = outer_radius - 14  # 圆弧线宽

        # ========== 1. 绘制标题 ==========
        font = QFont("Microsoft YaHei", 9, QFont.Bold)
        painter.setFont(font)
        painter.setPen(QColor(0, 191, 255))  # 蓝色标题更醒目
        title_rect = QRectF(margin, 2, width - 2*margin, title_height)
        painter.drawText(title_rect, Qt.AlignCenter, self.title)

        # ========== 2. 绘制背景圆弧（灰色底色）==========
        pen = QPen(QColor(60, 60, 60), 12)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        rect = QRectF(center_x - inner_radius, center_y - inner_radius,
                     inner_radius * 2, inner_radius * 2)
        painter.drawArc(rect, 225 * 16, 270 * 16)

        # ========== 3. 绘制前景圆弧（彩色进度）==========
        color = self.get_color_for_value()
        value_range = self.max_val - self.min_val
        if value_range > 0:
            angle_span = ((self.value - self.min_val) / value_range) * 270
        else:
            angle_span = 0

        pen = QPen(color, 12)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        if angle_span > 0:
            painter.drawArc(rect, 225 * 16, int(angle_span) * 16)

        # ========== 4. 绘制刻度（简化版，减少拥挤）==========
        painter.setPen(QColor(120, 120, 120))
        font = QFont("Arial", 7)
        painter.setFont(font)

        # 只绘制主要刻度（0%, 50%, 100%）
        major_ticks = [0, 5, 10]  # 对应 0%, 50%, 100%
        for i in major_ticks:
            angle = 225 + i * 27  # 每27度一个主刻度
            rad = math.radians(angle)

            # 刻度线
            x1 = center_x + (inner_radius - 18) * math.cos(rad)
            y1 = center_y + (inner_radius - 18) * math.sin(rad)
            x2 = center_x + (inner_radius - 24) * math.cos(rad)
            y2 = center_y + (inner_radius - 24) * math.sin(rad)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

            # 刻度值（只在两端显示）
            if i in [0, 10]:
                val = self.min_val + i * (value_range / 10)
                tx = center_x + (inner_radius - 32) * math.cos(rad) - 8
                ty = center_y + (inner_radius - 32) * math.sin(rad) + 4
                painter.drawText(int(tx), int(ty), f"{val:.0f}")

        # ========== 5. 绘制中心数值（加大间距）==========
        font = QFont("Arial", 16, QFont.Bold)
        painter.setFont(font)
        painter.setPen(color)
        value_text = f"{self.value:.1f}"
        value_rect = QRectF(center_x - 30, center_y - 12, 60, 28)
        painter.drawText(value_rect, Qt.AlignCenter, value_text)

        # ========== 6. 绘制单位（在数值下方，确保不重叠）==========
        font = QFont("Arial", 8)
        painter.setFont(font)
        painter.setPen(QColor(140, 140, 140))
        unit_rect = QRectF(center_x - 25, center_y + 15, 50, 18)
        painter.drawText(unit_rect, Qt.AlignCenter, self.unit)