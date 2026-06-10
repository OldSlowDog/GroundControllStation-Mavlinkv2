"""
实时图表控件 (Plot Widget) - 优化版
用于显示传感器数据的实时曲线，修复Y轴压缩问题
"""

import numpy as np
import pyqtgraph as pg
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QSizePolicy
from PyQt5.QtCore import Qt
from typing import List


class PlotWidget(QWidget):
    """实时数据图表控件 - 优化版"""

    MAX_POINTS = 500  # 最大显示点数

    def __init__(self, title: str = "", num_lines: int = 1, colors: List[str] = None,
                 names: List[str] = None, parent=None):
        super().__init__(parent)

        self.num_lines = num_lines
        self.colors = colors or ['#00ff00', '#ff0000', '#0088ff', '#ff8800',
                                  '#ff00ff', '#88ff00', '#00ffff', '#888888']
        self.names = names or [f"Line{i+1}" for i in range(num_lines)]

        # 设置布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)

        # 标题
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color: white; font-weight: bold; font-size: 12px;")
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)

        # 图表（关键优化：设置最小高度和大小策略）
        self.plot_widget = pg.PlotWidget(background='#1e1e1e')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.disableAutoRange()
        
        # ★ 关键：设置最小高度防止被压缩
        self.plot_widget.setMinimumHeight(120)  # 从140减到120
        
        # 设置大小策略为可扩展
        self.plot_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # 初始化数据曲线
        self.curves = []
        self.data_buffers = []

        for i in range(num_lines):
            color = self.colors[i % len(self.colors)]
            pen = pg.mkPen(color=color, width=2)
            curve = self.plot_widget.plot(pen=pen, name=self.names[i])
            self.curves.append(curve)
            self.data_buffers.append([])

        layout.addWidget(self.plot_widget)

        # 设置Y轴范围
        self.y_min = -100
        self.y_max = 100
        self.plot_widget.setYRange(self.y_min, self.y_max)

        # X轴范围
        self.x_data = list(range(self.MAX_POINTS))

    def set_y_range(self, min_val: float, max_val: float):
        """设置Y轴范围"""
        self.y_min = min_val
        self.y_max = max_val
        self.plot_widget.setYRange(min_val, max_val)

    def add_data(self, line_index: int, value: float):
        """添加单个数据点到指定曲线"""
        if 0 <= line_index < self.num_lines:
            buffer = self.data_buffers[line_index]
            buffer.append(value)

            # 保持缓冲区大小
            while len(buffer) > self.MAX_POINTS:
                buffer.pop(0)

            # 更新曲线
            x = np.arange(len(buffer))
            y = np.array(buffer)
            self.curves[line_index].setData(x, y)

    def update_all(self, values: List[float]):
        """同时更新所有曲线的数据"""
        for i, value in enumerate(values[:self.num_lines]):
            self.add_data(i, value)

    def clear_data(self):
        """清除所有数据"""
        for buffer in self.data_buffers:
            buffer.clear()
        for curve in self.curves:
            curve.setData([], [])

    def enable_legend(self, enabled: bool = True):
        """启用/禁用图例"""
        if enabled:
            legend = self.plot_widget.addLegend(offset=(10, 10))
            legend.setStyle(LabelTextColor='white')
        else:
            self.plot_widget.plotItem.legend = None

    def set_title(self, title: str):
        """设置图表标题"""
        self.title_label.setText(title)