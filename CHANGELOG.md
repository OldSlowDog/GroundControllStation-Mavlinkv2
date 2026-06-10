# Changelog — INAV Stellar GCS

本文件由定时任务（每日 20:00）自动检测变更并更新。

> 格式标准：[Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)
> 版本规则：语义化版本 `MAJOR.MINOR.PATCH`

---

## [Unreleased]

> 尚未发布的变更将出现在此。

---

## [1.0.0] — 2026-06-10

### feat
- **初始化 INAV Stellar Ground Control Station 项目 v1.0.0**
  `main.py`, `core/`, `ui/`, `utils/` — 基于 PyQt5 + MAVLink 2.0 的飞控调试上位机，含实时姿态监控、PID 调参、传感器校准、数据记录与回放、GPS 追踪、航点管理、电子围栏、MQTT 远程遥测等功能
- **搭建 Git 仓库基础设施**
  `.gitignore`, `README.md`, `CHANGELOG.md` — 版本控制与文档初始化

---

## 变更类型说明

| 类型 | 含义 |
|------|------|
| `feat` | 新增功能、新模块、新接口 |
| `fix` | Bug 修复、逻辑错误、稳定性问题 |
| `refactor` | 代码重构、架构重写、无功能变更 |
| `perf` | 性能 / 稳定性优化（滤波、时延、抗干扰） |
| `config` | 配置 / 参数调整（阈值、优先级、默认值） |
| `docs` | 文档更新（README、注释、图纸） |
| `chore` | 代码清理 / 工程维护（删除冗余、废弃字段、构建清理） |

---

*最后更新时间：2026-06-10*