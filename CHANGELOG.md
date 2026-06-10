# Changelog — INAV Stellar GCS

本文件由 `scripts/auto_sync.py` 自动生成，记录项目的版本历史。

> 💡 格式参考：[Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)
> 📌 版本规则：语义化版本（Semantic Versioning）—— `MAJOR.MINOR.PATCH`

---

## [Unreleased] — 开发中

> 尚未发布的变更将出现在这里。

---

## [1.0.0] — 2026-06-10

### ✨ Added（新增）
- 初始化 INAV Stellar Ground Control Station 项目
- 主程序入口 `main.py`，基于 PyQt5 的现代化深色主题 GUI
- **连接与通信模块**（`core/communication.py`）：串口 / TCP / MQTT 多路连接，自动重连
- **MAVLink 2.0 协议栈**（`core/protocol_parser.py` + `core/protocol_mavlink.py`）：替代 MSP，20 Hz 刷新率
- **数据管理**（`core/data_manager.py`）：CSV / JSON 导出、飞行统计、历史记录
- **UI 主窗口**（`ui/main_window.py`）：集成多标签页（实时监控 / PID / 校准 / 记录 / 终端）
- **自定义控件**（`ui/widgets/`）：地平仪、仪表盘、实时曲线、RC 通道等
- **校准向导**（`ui/calibration_wizard.py`）：IMU / 陀螺 / 遥控 / 电调 / 磁力计
- **GPS 追踪**（`core/gps_tracker.py`）、**航点管理**（`core/waypoint_manager.py`）、**电子围栏**（`core/geofence_manager.py`）
- **黑匣子回放**（`ui/blackbox_replay_dialog.py`）
- **参数历史对比**（`core/param_history.py` + `ui/param_history_dialog.py`）
- 配置文件 `config/default_config.json`
- Windows `start.bat`、Linux/Mac `start.sh` 一键启动脚本（自动安装依赖）
- `requirements.txt` 依赖清单（PyQt5 / pyserial / pyqtgraph / numpy / pyyaml）
- Git 仓库基础文件（`.gitignore`、`README.md`、本 `CHANGELOG.md`）
- 自动同步脚本 `scripts/auto_sync.py`（每日 20:00 自动更新 CHANGELOG 并推送到远程仓库）

### 🔧 Changed（变更）
- 项目初版发布，无历史变更。

### 🐛 Fixed（修复）
- 无。

### 🔒 Security（安全）
- 无。

---

## 版本号含义

| 级别 | 含义 |
|------|------|
| **MAJOR** | 破坏性变更、大功能重构、API 不兼容 |
| **MINOR** | 向后兼容的新功能、新模块 |
| **PATCH** | 向后兼容的 bug 修复、小改动 |

---

## 标签分类（自动生成时使用）

| 标签 | 含义 |
|------|------|
| `Added` / `新增` | 新功能、新文件、新模块 |
| `Changed` / `变更` | 现有功能或行为的变更 |
| `Deprecated` / `弃用` | 标记为将来删除的功能 |
| `Removed` / `移除` | 删除了功能或文件 |
| `Fixed` / `修复` | bug 修复 |
| `Security` / `安全` | 与安全相关的修复 |

---

*最后更新时间：2026-06-10*
