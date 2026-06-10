"""
Parameter History Dialog
Visual interface for parameter version history management

Features:
  - Version list with timestamps and descriptions
  - Diff comparison between versions (color-coded changes)
  - Rollback to any previous version
  - Export/Import for backup
  - Version description editing
"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLabel, QPushButton, QListWidget, QListWidgetItem,
                             QTextEdit, QGroupBox, QTableWidget, QTableWidgetItem,
                             QHeaderView, QMessageBox, QLineEdit, QComboBox,
                             QSplitter, QWidget, QFrame, QProgressBar)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QIcon

from core.param_history import get_param_history, ParamVersion


class ParamHistoryDialog(QDialog):
    """Parameter version history dialog"""
    
    # Signal: user wants to rollback to a specific version
    rollback_requested = pyqtSignal(dict)  # Emits {version_id, params}
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.history_mgr = get_param_history()
        self.selected_version_id = None
        
        self.setWindowTitle("Parameter History Manager")
        self.setMinimumSize(1100, 700)
        self.resize(1200, 750)
        
        self._setup_ui()
        self._refresh_version_list()
    
    def _setup_ui(self):
        """Setup dialog UI layout"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)
        
        # ===== Top: Info bar =====
        info_frame = QFrame()
        info_frame.setStyleSheet("""
            QFrame {
                background-color: #2d2d2d;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        info_layout = QHBoxLayout(info_frame)
        
        self.stats_label = QLabel("Loading...")
        self.stats_label.setStyleSheet("color: #00bfff; font-size: 11px;")
        info_layout.addWidget(self.stats_label)
        
        info_layout.addStretch()
        
        export_btn = QPushButton("Export Backup")
        export_btn.setStyleSheet(self._get_button_style('#17a2b8'))
        export_btn.clicked.connect(self._export_history)
        info_layout.addWidget(export_btn)
        
        import_btn = QPushButton("Import")
        import_btn.setStyleSheet(self._get_button_style('#6f42c1'))
        import_btn.clicked.connect(self._import_history)
        info_layout.addWidget(import_btn)
        
        clear_btn = QPushButton("Clear All")
        clear_btn.setStyleSheet(self._get_button_style('#dc3545'))
        clear_btn.clicked.connect(self._clear_all)
        info_layout.addWidget(clear_btn)
        
        main_layout.addWidget(info_frame)
        
        # ===== Main splitter =====
        splitter = QSplitter(Qt.Horizontal)
        
        # ===== Left Panel: Version List =====
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)
        
        list_label = QLabel("Version History")
        list_label.setStyleSheet("color: #00bfff; font-weight: bold; font-size: 12px;")
        left_layout.addWidget(list_label)
        
        self.version_list = QListWidget()
        self.version_list.setStyleSheet("""
            QListWidget {
                background-color: #1e1e1e;
                border: 1px solid #444;
                border-radius: 3px;
                font-family: Consolas, monospace;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #333;
            }
            QListWidget::item:selected {
                background-color: #005a9e;
                color: white;
            }
            QListWidget::item:hover {
                background-color: #2d2d2d;
            }
        """)
        self.version_list.currentRowChanged.connect(self._on_version_selected)
        left_layout.addWidget(self.version_list)
        
        # Description editor
        desc_group = QGroupBox("Edit Description")
        desc_group.setStyleSheet(self._get_groupbox_style())
        desc_layout = QVBoxLayout(desc_group)
        
        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("Enter description for selected version...")
        self.desc_edit.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e1e;
                border: 1px solid #555;
                padding: 6px;
                color: white;
                border-radius: 3px;
            }
        """)
        self.desc_edit.textChanged.connect(self._on_description_changed)
        desc_layout.addWidget(self.desc_edit)
        
        left_layout.addWidget(desc_group)
        splitter.addWidget(left_panel)
        
        # ===== Right Panel: Details + Actions =====
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(5, 5, 5, 5)
        
        # Version details
        detail_group = QGroupBox("Version Details")
        detail_group.setStyleSheet(self._get_groupbox_style())
        detail_layout = QGridLayout(detail_group)
        
        # Version ID
        detail_layout.addWidget(QLabel("Version:"), 0, 0)
        self.detail_version = QLabel("--")
        self.detail_version.setStyleSheet("font-weight: bold; color: #ffc107;")
        detail_layout.addWidget(self.detail_version, 0, 1)
        
        # Timestamp
        detail_layout.addWidget(QLabel("Saved:"), 1, 0)
        self.detail_time = QLabel("--")
        self.detail_time.setStyleSheet("color: #888;")
        detail_layout.addWidget(self.detail_time, 1, 1)
        
        # Param count
        detail_layout.addWidget(QLabel("Parameters:"), 2, 0)
        self.detail_count = QLabel("--")
        self.detail_count.setStyleSheet("color: #888;")
        detail_layout.addWidget(self.detail_count, 2, 1)
        
        # Description
        detail_layout.addWidget(QLabel("Description:"), 3, 0)
        self.detail_desc = QLabel("--")
        self.detail_desc.setWordWrap(True)
        self.detail_desc.setStyleSheet("color: #ccc;")
        detail_layout.addWidget(self.detail_desc, 3, 1)
        
        detail_layout.setColumnStretch(1, 1)
        right_layout.addWidget(detail_group)
        
        # Parameter table
        param_group = QGroupBox("Parameters in this Version")
        param_group.setStyleSheet(self._get_groupbox_style())
        param_layout = QVBoxLayout(param_group)
        
        self.param_table = QTableWidget()
        self.param_table.setColumnCount(4)
        self.param_table.setHorizontalHeaderLabels(["Parameter", "Value", "Type", "Status"])
        self.param_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.param_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.param_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.param_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.param_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.param_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.param_table.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e1e;
                gridline-color: #444;
                color: white;
                font-size: 11px;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QHeaderView::section {
                background-color: #3c3c3c;
                padding: 6px;
                font-weight: bold;
                border: 1px solid #555;
                color: #fff;
            }
        """)
        param_layout.addWidget(self.param_table)
        right_layout.addWidget(param_group)
        
        # Comparison view
        compare_group = QGroupBox("Compare with Previous Version")
        compare_group.setStyleSheet(self._get_groupbox_style())
        compare_layout = QVBoxLayout(compare_group)
        
        self.compare_table = QTableWidget()
        self.compare_table.setColumnCount(4)
        self.compare_table.setHorizontalHeaderLabels(["Parameter", "Current", "Previous", "Change"])
        self.compare_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.compare_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.compare_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.compare_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.compare_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.compare_table.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e1e;
                gridline-color: #444;
                color: white;
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #3c3c3c;
                padding: 6px;
                font-weight: bold;
                border: 1px solid #555;
                color: #fff;
            }
        """)
        compare_layout.addWidget(self.compare_table)
        right_layout.addWidget(compare_group)
        
        # Action buttons
        action_layout = QHBoxLayout()
        
        self.rollback_btn = QPushButton("⬅️ Rollback to This Version")
        self.rollback_btn.setStyleSheet("""
            QPushButton {
                background-color: #fd7e14;
                color: white;
                padding: 12px 20px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #e0690f; }
            QPushButton:disabled { background-color: #666; color: #999; }
        """)
        self.rollback_btn.setEnabled(False)
        self.rollback_btn.clicked.connect(self._rollback_to_selected)
        action_layout.addWidget(self.rollback_btn)
        
        delete_btn = QPushButton("🗑️ Delete Version")
        delete_btn.setStyleSheet(self._get_button_style('#dc3545'))
        delete_btn.clicked.connect(self._delete_selected)
        action_layout.addWidget(delete_btn)
        
        action_layout.addStretch()
        right_layout.addLayout(action_layout)
        
        splitter.addWidget(right_panel)
        
        # Set splitter ratio (40% : 60%)
        splitter.setSizes([400, 700])
        
        main_layout.addWidget(splitter)
        
        # Update stats
        self._update_stats()
    
    def _refresh_version_list(self):
        """Refresh the version list widget"""
        self.version_list.clear()
        
        versions = self.history_mgr.get_all_versions()
        
        for v in versions:
            item_text = f"V{v.version_id:03d} | {v.timestamp[:19]} | {v.description[:35]}"
            
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, v.version_id)
            
            # Highlight latest version
            if v.version_id == self.history_mgr.current_version:
                item.setForeground(QColor('#28a745'))  # Green for current
                item.setText(f"★ {item_text}")
            
            self.version_list.addItem(item)
    
    def _on_version_selected(self, row: int):
        """Handle version selection change"""
        if row < 0:
            return
        
        item = self.version_list.item(row)
        if not item:
            return
        
        version_id = item.data(Qt.UserRole)
        self.selected_version_id = version_id
        
        version = self.history_mgr.get_version(version_id)
        if not version:
            return
        
        # Update details panel
        self.detail_version.setText(f"#{version_id}")
        self.detail_time.setText(version.timestamp.replace('T', ' '))
        self.detail_desc.setText(version.description)
        self.detail_count.setText(f"{len(version.params)} parameters")
        
        # Update description editor
        self.desc_edit.blockSignals(True)
        self.desc_edit.setText(version.description)
        self.desc_edit.blockSignals(False)
        
        # Populate parameter table
        self._populate_param_table(version.params)
        
        # Show comparison with previous version
        prev_version = self.history_mgr.get_previous_version(version_id)
        if prev_version:
            diffs = self.history_mgr.compare_versions(prev_version.version_id, version_id)
            self._populate_compare_table(diffs, prev_version.version_id, version_id)
        else:
            self.compare_table.setRowCount(0)
        
        # Enable rollback button (except for current/latest)
        is_current = (version_id == self.history_mgr.current_version)
        self.rollback_btn.setEnabled(not is_current)
        if is_current:
            self.rollback_btn.setText("⭐ Current Version (No Rollback)")
        else:
            self.rollback_btn.setText(f"⬅️ Rollback to V{version_id}")
    
    def _populate_param_table(self, params: dict):
        """Populate parameter display table"""
        self.param_table.setRowCount(len(params))
        
        for i, (name, value) in enumerate(sorted(params.items())):
            # Parameter name
            name_item = QTableWidgetItem(name)
            name_item.setFont(QFont("Consolas", 10))
            self.param_table.setItem(i, 0, name_item)
            
            # Value
            value_str = str(value) if value is not None else "<null>"
            value_item = QTableWidgetItem(value_str)
            value_item.setFont(QFont("Consolas", 10))
            value_item.setTextAlignment(Qt.AlignCenter)
            self.param_table.setItem(i, 1, value_item)
            
            # Type detection
            type_name = type(value).__name__
            type_item = QTableWidgetItem(type_name)
            type_item.setForeground(QColor('#888'))
            self.param_table.setItem(i, 2, type_item)
            
            # Status (always "saved" for historical view)
            status_item = QTableWidgetItem("✓ Saved")
            status_item.setForeground(QColor('#28a745'))
            status_item.setTextAlignment(Qt.AlignCenter)
            self.param_table.setItem(i, 3, status_item)
    
    def _populate_compare_table(self, diffs: dict, v1_id: int, v2_id: int):
        """Populate comparison table showing differences"""
        changed_params = [(k, v) for k, v in diffs.items() if v['changed']]
        
        self.compare_table.setRowCount(len(changed_params))
        
        for i, (name, diff) in enumerate(changed_params):
            # Name
            name_item = QTableWidgetItem(name)
            name_item.setFont(QFont("Consolas", 10))
            self.compare_table.setItem(i, 0, name_item)
            
            # Current value (v2)
            val2_item = QTableWidgetItem(str(diff[f'v{v2_id}']))
            val2_item.setFont(QFont("Consolas", 10))
            val2_item.setTextAlignment(Qt.AlignCenter)
            self.compare_table.setItem(i, 1, val2_item)
            
            # Previous value (v1)
            val1_item = QTableWidgetItem(str(diff[f'v{v1_id}']))
            val1_item.setFont(QFont("Consolas", 10))
            val1_item.setTextAlignment(Qt.AlignCenter)
            self.compare_table.setItem(i, 2, val1_item)
            
            # Change indicator
            change_item = QTableWidgetItem("Changed")
            change_item.setForeground(QColor('#ffc107'))  # Yellow
            change_item.setTextAlignment(Qt.AlignCenter)
            self.compare_table.setItem(i, 3, change_item)
        
        # Show summary
        total = len(diffs)
        changed = len(changed_params)
        self.compare_group.setTitle(
            f"Compare with Previous Version ({changed} of {total} params changed)"
        )
    
    def _on_description_changed(self, text: str):
        """Handle description edit (update history file)"""
        if not self.selected_version_id:
            return
        
        version = self.history_mgr.get_version(self.selected_version_id)
        if version and version.description != text:
            version.description = text
            self.history_mgr._save_history()
            
            # Refresh list to show updated description
            self._refresh_version_list()
            
            # Re-select current item
            for i in range(self.version_list.count()):
                item = self.version_list.item(i)
                if item and item.data(Qt.UserRole) == self.selected_version_id:
                    self.version_list.setCurrentRow(i)
                    break
    
    def _rollback_to_selected(self):
        """Rollback to selected version"""
        if not self.selected_version_id:
            return
        
        reply = QMessageBox.question(
            self,
            "Confirm Rollback",
            f"Are you sure you want to rollback to Version #{self.selected_version_id}?\n\n"
            "This will load all parameters from that version.\n"
            "You should save them to Flight Controller afterwards.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            params = self.history_mgr.get_rollback_data(self.selected_version_id)
            if params:
                self.rollback_requested.emit({
                    'version_id': self.selected_version_id,
                    'params': params
                })
                
                QMessageBox.information(
                    self,
                    "Rollback Ready",
                    f"Parameters from Version #{self.selected_version_id} loaded!\n"
                    "Please review and click 'Save to FC' to apply."
                )
                self.accept()
    
    def _delete_selected(self):
        """Delete selected version"""
        if not self.selected_version_id:
            return
        
        reply = QMessageBox.warning(
            self,
            "Delete Version",
            f"Permanently delete Version #{self.selected_version_id}?\n"
            "This cannot be undone!",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel
        )
        
        if reply == QMessageBox.Yes:
            if self.history_mgr.delete_version(self.selected_version_id):
                self._refresh_version_list()
                self.selected_version_id = None
    
    def _export_history(self):
        """Export entire history to backup file"""
        from PyQt5.QtWidgets import QFileDialog
        
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Export Parameter History",
            f"params_backup_{self.history_mgr.current_version}.json",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if filepath:
            if self.history_mgr.export_history(filepath):
                QMessageBox.information(self, "Export Success", 
                                        f"History exported to:\n{filepath}")
            else:
                QMessageBox.critical(self, "Export Failed", "Could not export history!")
    
    def _import_history(self):
        """Import history from backup file"""
        from PyQt5.QtWidgets import QFileDialog
        
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Import Parameter History",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if filepath:
            reply = QMessageBox.question(
                self,
                "Import History",
                "Merge with existing history?\n\n"
                "Yes: Add only new versions\n"
                "No: Replace entire history",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Cancel:
                return
            
            merge = (reply == QMessageBox.Yes)
            
            if self.history_mgr.import_history(filepath, merge=merge):
                self._refresh_version_list()
                self._update_stats()
                QMessageBox.information(self, "Import Success",
                                       f"History imported from:\n{filepath}")
            else:
                QMessageBox.critical(self, "Import Failed", "Invalid or corrupted file!")
    
    def _clear_all(self):
        """Clear all history except latest"""
        reply = QMessageBox.warning(
            self,
            "Clear All History",
            "Remove all old versions except the current one?\n"
            "This frees up space but loses rollback ability!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if self.history_mgr.clear_all_history():
                self._refresh_version_list()
                self._update_stats()
    
    def _update_stats(self):
        """Update statistics label"""
        stats = self.history_mgr.get_statistics()
        
        self.stats_label.setText(
            f"Versions: {stats['total_versions']}/{stats['max_versions_limit']} | "
            f"Current: V{stats['current_version']} | "
            f"Storage: {stats['storage_size_kb']:.1f} KB | "
            f"Slots: {stats['remaining_slots']} free"
        )
    
    @staticmethod
    def _get_button_style(color: str) -> str:
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                padding: 6px 15px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 11px;
            }}
            QPushButton:hover {{ background-color: {color}; opacity: 0.8; }}
        """
    
    @staticmethod
    def _get_groupbox_style() -> str:
        return """
            QGroupBox {
                font-weight: bold;
                font-size: 11px;
                border: 1px solid #555;
                border-radius: 4px;
                margin-top: 6px;
                padding-top: 6px;
                color: #ccc;
                background-color: #2d2d2d;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 6px;
                padding: 0 3px;
                color: #00bfff;
            }
        """
