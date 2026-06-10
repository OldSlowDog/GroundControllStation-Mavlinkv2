"""
姿态显示控件 (Artificial Horizon)
显示飞机的横滚和俯仰角，模拟地平仪
"""

from PyQt5.QtWidgets import QWidget, QFrame, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt, QPoint, QRect, pyqtSignal
from PyQt5.QtGui import (QPainter, QColor, QPen, QBrush, QFont,
                         QPainterPath, QRadialGradient, QLinearGradient)


class AttitudeWidget(QWidget):
    """姿态指示器控件"""

    # 信号：当角度变化时发出
    attitude_changed = pyqtSignal(float, float)  # roll, pitch

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(280, 300)

        self.roll = 0.0      # 横滚角 (度)
        self.pitch = 0.0     # 俯仰角 (度)
        self.heading = 0.0   # 航向角 (度)

        self.setMouseTracking(True)

    def set_attitude(self, roll: float, pitch: float, heading: float = 0.0):
        """设置姿态角度"""
        self.roll = roll
        self.pitch = pitch
        self.heading = heading
        self.update()
        self.attitude_changed.emit(roll, pitch)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2
        radius = min(cx, cy) - 15

        # ---- 外圈边框 ----
        ring_pen = QPen(QColor(70, 70, 70), 3)
        painter.setPen(ring_pen)
        painter.setBrush(QBrush(QColor(20, 20, 22)))
        painter.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)

        # ---- 圆形裁剪区域 ----
        clip = QPainterPath()
        clip.addEllipse(cx - radius + 3, cy - radius + 3,
                        (radius - 3) * 2, (radius - 3) * 2)
        painter.setClipPath(clip)

        # 平移坐标系到圆心 (不旋转! 地面始终保持水平)
        painter.translate(cx, cy)

        # 根据俯仰角偏移地平线位置
        pitch_offset = int(self.pitch * 2)
        horizon_y = -pitch_offset  # 地平线Y坐标 (正offset→下移)

        # 绘制天空（从圆顶到地平线）
        sky_grad = QRadialGradient(0, -radius, radius * 2)
        sky_grad.setColorAt(0, QColor(25, 84, 160))
        sky_grad.setColorAt(0.5, QColor(65, 155, 220))
        sky_grad.setColorAt(1, QColor(135, 206, 235))
        painter.setBrush(QBrush(sky_grad))
        painter.setPen(Qt.NoPen)
        sky_h = radius - pitch_offset
        if sky_h > 0:
            painter.drawRect(-radius, -radius, radius * 2, sky_h)

        # 绘制地面（从地平线到圆底）
        ground_grad = QRadialGradient(0, radius, radius * 2)
        ground_grad.setColorAt(0, QColor(194, 178, 128))
        ground_grad.setColorAt(0.3, QColor(139, 119, 101))
        ground_grad.setColorAt(1, QColor(101, 67, 33))
        painter.setBrush(QBrush(ground_grad))
        ground_h = radius + pitch_offset
        if ground_h > 0:
            painter.drawRect(-radius, horizon_y, radius * 2, ground_h)

        # 绘制地平线
        pen = QPen(QColor(255, 255, 255), 3)
        painter.setPen(pen)
        painter.drawLine(-radius, horizon_y, radius, horizon_y)

        # 绘制俯仰刻度线
        pen = QPen(QColor(255, 255, 255, 200), 2)
        painter.setPen(pen)
        for angle in range(-60, 61, 10):
            if angle == 0:
                continue
            y = int(angle * 3) + horizon_y
            if abs(y) < radius:
                is_major = (angle % 30 == 0)
                length = 18 if is_major else 10
                painter.drawLine(-length, y, length, y)

        # 恢复坐标系
        painter.resetTransform()

        # === 飞机符号 (带滚转, 绕圆心旋转) ===
        painter.translate(cx, cy)
        painter.rotate(self.roll)  # ★ 飞机符号跟随滚转角旋转

        # 机翼横线
        wing_pen = QPen(QColor(255, 200, 0), 4, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(wing_pen)
        painter.drawLine(-45, 0, -12, 0)
        painter.drawLine(12, 0, 45, 0)

        # 机身中线
        painter.drawLine(0, -8, 0, 22)

        # 中心圆点
        painter.setBrush(QBrush(QColor(220, 40, 40)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(-5, -5, 10, 10)

        # === 航向指示条 ===
        painter.resetTransform()
        self._draw_heading_strip(painter, cx, cy, radius)

        # === 角度数字显示 ===
        self._draw_angle_text(painter, cx, cy, radius)

    def _draw_heading_strip(self, painter, cx, cy, radius):
        """底部的航向指示条"""
        strip_w = radius * 2 - 16
        strip_h = 24
        strip_y = cy + radius - 2

        # 背景
        painter.setBrush(QBrush(QColor(30, 30, 32, 230)))
        painter.setPen(QPen(QColor(60, 60, 60), 1))
        painter.drawRoundedRect(cx - strip_w // 2, strip_y, strip_w, strip_h, 4, 4)

        # 刻度和标签
        painter.setPen(QColor(200, 200, 200))
        font = QFont("Arial", 9)
        painter.setFont(font)

        offset = (self.heading % 360) / 360.0 * strip_w
        for deg in range(int(self.heading - 100), int(self.heading + 101), 10):
            ndeg = deg % 360
            x = cx - offset + ((ndeg - self.heading) / 360.0 * strip_w)
            if cx - strip_w // 2 + 5 <= x <= cx + strip_w // 2 - 5:
                is_main = (deg % 30 == 0)
                tick_top = strip_y + (3 if is_main else 7)
                tick_bot = strip_y + (14 if is_main else 11)
                painter.drawLine(int(x), tick_top, int(x), tick_bot)
                if is_main:
                    font2 = QFont("Arial", 9, QFont.Bold)
                    painter.setFont(font2)
                    labels = {0: "N", 90: "E", 180: "S", 270: "W"}
                    text = labels.get(ndeg, str(ndeg))
                    painter.drawText(int(x) - 8, strip_y + 22, text)
                    painter.setFont(font)

        # 当前航向三角指针
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(220, 40, 40)))
        pts = [QPoint(cx, strip_y - 2), QPoint(cx - 6, strip_y + 6), QPoint(cx + 6, strip_y + 6)]
        painter.drawPolygon(pts)

    def _draw_angle_text(self, painter, cx, cy, radius):
        """左上角显示 Roll/Pitch 数值"""
        font = QFont("Consolas", 10, QFont.Bold)
        painter.setFont(font)
        txt_r = f"R {self.roll:+.0f}"
        painter.setPen(QColor(180, 180, 180))
        painter.drawText(cx - radius + 8, cy - radius + 18, txt_r)
        txt_p = f"P {self.pitch:+.0f}"
        painter.drawText(cx - radius + 8, cy - radius + 34, txt_p)

    def get_info_text(self) -> str:
        return f"R:{self.roll:+.1f} P:{self.pitch:+.1f} H:{self.heading:.0f}"
