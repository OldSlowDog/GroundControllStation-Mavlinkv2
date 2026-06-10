"""
RC Monitor Tab
Complete RC channel visualization tab with bars, waveforms, and statistics
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QGroupBox, QLabel, QFrame, QSplitter,
                             QTableWidget, QTableWidgetItem, QHeaderView)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from ui.widgets.rc_bar_widget import RCBarWidget
from ui.widgets.rc_waveform_plot import RCWaveformPlot


class RCMonitorTab(QWidget):
    """RC Channel Monitoring Tab - Complete visualization"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.rc_bar_widget = None
        self.waveform_plot = None
        self.stats_table = None
        self.value_labels = {}

        self._setup_ui()

    def _setup_ui(self):
        """Setup complete RC monitoring UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # Main splitter for left-right layout
        splitter = QSplitter(Qt.Horizontal)

        # ===== Left Panel: RC Bar Chart =====
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)

        self.rc_bar_widget = RCBarWidget()
        left_layout.addWidget(self.rc_bar_widget)

        splitter.addWidget(left_panel)

        # ===== Right Panel: Waveform + Statistics =====
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(5, 5, 5, 5)
        right_layout.setSpacing(8)

        # Top: Waveform plot
        self.waveform_plot = RCWaveformPlot()
        right_layout.addWidget(self.waveform_plot, stretch=2)

        # Bottom: Detailed values and statistics
        stats_group = QGroupBox("RC Channel Statistics")
        stats_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 11px;
                border: 2px solid #444;
                border-radius: 5px;
                margin-top: 8px;
                padding-top: 8px;
                color: white;
                background-color: #2d2d2d;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
                color: #00bfff;
            }
        """)
        stats_layout = QVBoxLayout(stats_group)

        # Current values grid
        values_frame = QFrame()
        values_frame.setStyleSheet("""
            QFrame {
                background-color: #252526;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 5px;
            }
        """)
        values_grid = QGridLayout(values_frame)
        values_grid.setSpacing(8)

        channels_info = [
            ('ROLL', 'rc_roll', '#ff4444'),
            ('PITCH', 'rc_pitch', '#44ff44'),
            ('THROTTLE', 'rc_throttle', '#ffaa00'),
            ('YAW', 'rc_yaw', '#4488ff'),
            ('AUX1', 'rc_aux1', '#aa44ff'),
            ('AUX2', 'rc_aux2', '#44ffff'),
            ('AUX3', 'rc_aux3', '#ff88aa'),
            ('AUX4', 'rc_aux4', '#88ff44')
        ]

        for i, (name, key, color) in enumerate(channels_info):
            row = i // 4
            col = i % 4

            # Channel name label
            name_label = QLabel(f"{name}:")
            name_label.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 11px;")
            name_label.setMinimumWidth(55)
            values_grid.addWidget(name_label, row, col * 2)

            # Value label
            value_label = QLabel("----")
            value_label.setStyleSheet("""
                color: #fff;
                font-family: Consolas, monospace;
                font-size: 12px;
                font-weight: bold;
                padding: 2px 5px;
                background-color: #1e1e1e;
                border-radius: 2px;
            """)
            value_label.setMinimumWidth(60)
            value_label.setAlignment(Qt.AlignCenter)
            self.value_labels[key] = value_label
            values_grid.addWidget(value_label, row, col * 2 + 1)

        stats_layout.addWidget(values_frame)

        # Statistics table
        self.stats_table = QTableWidget(8, 4)
        self.stats_table.setHorizontalHeaderLabels(["Channel", "Min", "Max", "Avg"])
        self.stats_table.setVerticalHeaderLabels([ch[0] for ch in channels_info])
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.stats_table.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.stats_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.stats_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.stats_table.setStyleSheet("""
            QTableWidget {
                background-color: #2d2d2d;
                gridline-color: #555;
                color: white;
                font-size: 10px;
            }
            QHeaderView::section {
                background-color: #3c3c3c;
                padding: 4px;
                font-weight: bold;
                border: 1px solid #555;
                font-size: 10px;
            }
        """)

        # Initialize table with default values
        for i, (name, key, color) in enumerate(channels_info):
            item_name = QTableWidgetItem(name)
            item_name.setForeground(Qt.white)
            self.stats_table.setItem(i, 0, item_name)

            for j in range(1, 4):
                item = QTableWidgetItem("---")
                item.setTextAlignment(Qt.AlignCenter)
                self.stats_table.setItem(i, j, item)

        stats_layout.addWidget(self.stats_table)

        right_layout.addWidget(stats_group, stretch=1)

        splitter.addWidget(right_panel)

        # Set splitter sizes (40% left, 60% right)
        splitter.setSizes([300, 500])

        main_layout.addWidget(splitter)

    def update_rc_data(self, rc_data: dict):
        """Update all RC visualizations with new data"""
        if not rc_data:
            return

        # Update bar chart
        if self.rc_bar_widget:
            self.rc_bar_widget.update_channels(rc_data)

        # Update waveform
        if self.waveform_plot:
            self.waveform_plot.update_data(rc_data)

        # Update value labels
        for key, label in self.value_labels.items():
            if key in rc_data:
                value = rc_data[key]
                label.setText(f"{value:4d}")

                # Color coding based on distance from center
                center = 1500
                if abs(value - center) < 100:
                    label.setStyleSheet(label.styleSheet().replace(
                        'background-color: #1e1e1e;',
                        'background-color: #1e1e1e;'
                    ))
                elif abs(value - center) < 300:
                    label.setStyleSheet(label.styleSheet().replace(
                        'background-color: #1e1e1e;',
                        'background-color: #3d3d00;'
                    ))
                else:
                    label.setStyleSheet(label.styleSheet().replace(
                        'background-color: #1e1e1e;',
                        'background-color: #4d0000;'
                    ))

    def clear_all_data(self):
        """Clear all RC data displays"""
        if self.waveform_plot:
            self.waveform_plot.clear_data()

        # Reset value labels
        for label in self.value_labels.values():
            label.setText("----")

        # Reset stats table
        for i in range(8):
            for j in range(1, 4):
                item = self.stats_table.item(i, j)
                if item:
                    item.setText("---")
