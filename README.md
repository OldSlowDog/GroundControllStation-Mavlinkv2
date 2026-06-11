# MAVLink 2 地面站（GCS）

## 📌 项目简介

**MAVLink 2 通用飞控上位机调试软件** — 面向所有符合 **MAVLink 2.0 协议** 的飞控系统，提供实时调试、参数调优、传感器校准和数据记录的专业工具。

基于 **Python + PyQt5** 开发，采用现代化的深色主题界面，通过**插件化协议抽象层**实现对多协议、多固件的统一支持，具备良好的可扩展性。

---

## ✨ 功能特性

### 🔌 连接与通信
- 自动检测可用串口设备
- 支持串口 / TCP / MQTT 多路连接
- 波特率可配置（115200 / 57600 / 38400 / 9600，最高 1.5M）
- **MAVLink 2.0 协议**实时数据收发（20 Hz 刷新率）
- 断线自动重连机制

### 📊 实时数据监控
- **姿态显示**: 地平仪仪表盘（Roll/Pitch/Yaw）
- **传感器数据**: 实时曲线图表
  - 陀螺仪三轴数据（°/s）
  - 加速度计三轴数据（g）
  - 磁力计数据
- **电机输出**: 四路 PWM 实时监控
- **遥控器输入**: 8 通道 RC 数据显示

### ⚙️ 参数调优
- PID 参数可视化编辑表格
- 一键从飞控读取 / 写入 PID 参数
- 支持 ROLL/PITCH/YAW 独立调节
- 参数历史对比与一键回滚

### 🎯 校准功能
- IMU 加速度计校准（水平面校准）
- 陀螺仪零偏校准
- 遥控器中点校准
- 电调行程校准（安全提示）
- 磁力计 8 字形校准

### 💾 数据记录与回放
- CSV 格式飞行数据记录
- JSON 数据导出功能
- 飞行统计信息（最大高度、飞行时间、数据率等）
- **黑匣子**日志回放播放器

### 🗺️ GPS 与航点管理
- GPS 实时追踪与轨迹记录
- 航点列表管理与下发
- 电子围栏（地理围栏）配置
- 基于 HTML/JS 的地图展示

### 💬 终端日志
- 实时通信日志显示
- 手动命令发送接口
- 时间戳标记

---

## 🔧 可扩展性设计

### 协议插件化
本项目将协议处理抽象为独立层，使**协议切换仅依赖配置**，无需修改上层业务代码：

```
UI / core (业务层) ──▶ protocol_parser.py (统一抽象) ──▶ 协议插件
                                                    ├─ MAVLink 2.0 (当前)
                                                    ├─ MSP 兼容层 (可选)
                                                    └─ 自定义协议 (可扩展)
```

添加新协议支持，只需：
1. 在 `core/` 下实现新的协议解析模块（参考 `protocol_mavlink.py`）
2. 在 `config/default_config.json` 中注册协议类型
3. 上层 UI/业务逻辑无需改动

### 模块化目录结构

```
GroundControlStation/
├── main.py                      # 主程序入口（跨平台）
├── requirements.txt             # Python 依赖列表
├── start.bat / start.sh         # 一键启动脚本
│
├── core/                        # 核心业务模块（协议无关）
│   ├── communication.py         # 串口/TCP/MQTT 通信抽象
│   ├── protocol_parser.py       # 协议解析统一接口
│   ├── protocol_mavlink.py      # MAVLink 2.0 协议实现（可替换）
│   ├── data_manager.py          # 数据存储、统计、导出
│   ├── gps_tracker.py           # GPS 追踪模块
│   ├── waypoint_manager.py      # 航点管理
│   ├── geofence_manager.py      # 电子围栏
│   ├── param_history.py         # 参数历史记录
│   └── mqtt_manager.py          # MQTT 远程遥测
│
├── ui/                          # 界面层（协议无关）
│   ├── main_window.py           # 主窗口
│   ├── calibration_wizard.py    # 校准向导
│   ├── blackbox_replay_dialog.py# 黑匣子回放
│   ├── complete_param_config.py # 参数面板
│   ├── map_tab.py               # 地图标签页
│   ├── performance_monitor_tab.py# 性能监控
│   ├── rc_monitor_tab.py        # RC 通道监控
│   └── widgets/                 # 自定义控件（地平仪/仪表盘/曲线等）
│
├── utils/                       # 工具函数
│   ├── logger.py                # 日志工具
│   └── helpers.py               # 辅助函数库
│
├── config/                      # 配置
│   └── default_config.json      # 默认配置（波特率/阈值/刷新频率等）
│
├── resources/map/               # 前端资源（HTML/JS/CSS 地图）
│
└── logs/                        # 日志与数据（运行时生成）
```

### 配置驱动的行为
所有可调参数集中于 `config/default_config.json`，支持运行时热切换，**无需重启程序**即可调整：

- 波特率、超时、重连策略
- 刷新频率、历史数据长度
- 告警阈值（电压/电流/高度）
- PID 默认值、校准时长
- 字体、主题、窗口尺寸

---

## 🚀 快速开始

### ✨ 推荐方式：双击启动（全自动安装依赖）

**Windows 用户**：
```bash
双击运行 start.bat
```

脚本自动完成：Python 探测 → 依赖检查 → 在线安装缺失包 → 启动程序

**首次启动预计时间**：2-5 分钟（取决于网络速度）

**Linux/Mac 用户**：
```bash
./start.sh
```

### 🛠️ 手动方式（高级用户）

```bash
# 1. 进入项目目录
cd GroundControlStation

# 2. 创建虚拟环境（可选但推荐）
python -m venv venv
venv\Scripts\activate     # Windows
source venv/bin/activate  # Linux/Mac

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动程序
python main.py
```

### 依赖库说明

| 库名 | 版本要求 | 用途 |
|------|---------|------|
| PyQt5 | >=5.15.0 | GUI 框架 |
| pyserial | >=3.5 | 串口通信 |
| pyqtgraph | >=0.13.0 | 高性能实时绑图 |
| numpy | >=1.24.0 | 数值计算 |
| pyyaml | >=6.0 | 配置文件解析 |

---

## 📖 使用指南

### 1. 连接飞控
1. 使用 USB 数据线连接电脑和飞控开发板
2. 打开软件后，点击"刷新"按钮扫描串口
3. 选择正确的串口号（通常为 COM3-COM10）
4. 保持默认波特率 115200（或根据飞控固件配置调整）
5. 点击"🔌 连接"按钮

**成功标志**：
- 状态栏显示"● 已连接"（绿色）
- 右侧面板开始显示实时数据

### 2. 监控飞行数据
连接成功后，软件会自动以 20 Hz 频率请求并显示：

- **左侧面板**：地平仪、仪表盘（电压/电流/高度/油门）、RC 通道
- **右侧标签页**：实时传感器曲线、电机输出曲线、终端日志

### 3. 调整 PID 参数
1. 切换到"⚙️ PID 调参"标签页
2. 点击"📥 从飞控读取"获取当前参数
3. 在表格中修改 P/I/D 值
4. 点击"📤 发送到飞控"应用更改

### 4. 执行校准
在"🎯 校准向导"中选择校准类型并按提示操作：
- **IMU 加速度计**：将飞控放置在水平面上
- **陀螺仪**：保持飞控完全静止
- **遥控器中点**：所有摇杆置于中间位置
- **电调**：⚠️ 必须拆除螺旋桨
- **磁力计**：手持飞控做 8 字形旋转

### 5. 记录飞行数据
1. 切换到"💾 数据记录"标签页
2. 点击"⏺ 开始记录"
3. 数据自动保存至 `logs/` 目录（CSV / JSON 双格式）

---

## ⌨️ 快捷键与命令

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+R` | 刷新串口列表 |
| `Ctrl+C` | 连接 / 断开 |
| `F5` | 开始 / 停止记录 |
| `Esc` | 关闭对话框 |

---

## 🔧 配置说明

配置文件位于 `config/default_config.json`，可自定义以下参数：

```json
{
  "connection": {
    "default_baudrate": 115200,
    "timeout": 0.1,
    "auto_reconnect": true,
    "reconnect_interval_ms": 5000
  },
  "data_update": {
    "ui_update_rate_hz": 20,
    "request_rate_hz": 20,
    "max_history_points": 1000
  },
  "gauges": {
    "vbat_warning_v": 14.8,
    "vbat_critical_v": 13.0,
    "current_warning_a": 30
  },
  "pid_defaults": {
    "roll": {"p": 45, "i": 40, "d": 0},
    "pitch": {"p": 45, "i": 40, "d": 0},
    "yaw": {"p": 30, "i": 45, "d": 0}
  }
}
```

---

## 🐛 故障排除

**Q: 无法检测到串口？**
- A: 检查 USB 线是否为数据线（非仅充电线）
- A: 安装 CH340 / CP2102 驱动（Windows 需要手动安装）

**Q: 连接后无数据？**
- A: 确认波特率与飞控固件匹配
- A: 检查飞控固件是否启用 MAVLink 2.0 协议输出
- A: 尝试重启飞控后重新连接

**Q: 图表显示异常？**
- A: 更新 pyqtgraph：`pip install --upgrade pyqtgraph`
- A: 减少 `max_history_points` 配置

**Q: 中文显示乱码？**
- A: 确保系统安装了微软雅黑字体
- A: 在 `default_config.json` 中修改 `font_family`

### 日志位置
- 应用日志：`logs/gcs_YYYYMMDD.log`
- 飞行数据：`logs/flight_log_YYYYMMDD_HHMMSS.csv`

---

## 📄 许可证

本项目仅供学习和研究使用。

---

## 📞 技术支持

如遇问题，请检查：
1. 日志文件 `logs/` 目录下的最新日志
2. 确认 Python 版本 >= 3.8
3. 确认所有依赖正确安装
4. 重启应用后再试

**祝飞行愉快！✈️**
