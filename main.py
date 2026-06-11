"""
INAV Stellar Ground Control Station - 主程序入口
飞控上位机调试软件
"""

import sys
import os

# 添加项目根目录到系统路径
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _PROJECT_ROOT)

# ── 加载 .env 文件（地图 API Key 等敏感信息保存在此处） ──
# 不依赖 python-dotenv，自实现极简解析，避免额外依赖
def _load_env():
    env_path = os.path.join(_PROJECT_ROOT, ".env")
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for lineno, raw in enumerate(f, 1):
                line = raw.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' not in line:
                    continue
                key, _, value = line.partition('=')
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                # 不覆盖已有的环境变量（允许用户在 shell 中预先设定）
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception as e:
        print(f"[Warning] 无法加载 .env: {e}")

_load_env()

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from ui.main_window import MainWindow
from utils.logger import logger


def main():
    """应用程序主函数"""
    # 注册跨线程信号元类型 (修复 QWebChannel QVector<int> 警告)
    try:
        from PyQt5.QtCore import QMetaType
        QMetaType.registerType("QVector<int>")
    except Exception:
        pass

    # 启用高DPI支持
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    # 创建应用实例
    app = QApplication(sys.argv)
    app.setApplicationName("INAV Stellar GCS")
    app.setOrganizationName("INAV Stellar Team")

    # 设置全局字体
    font = QFont("Microsoft YaHei", 9)
    app.setFont(font)

    # 设置应用样式（深色主题）
    app.setStyleSheet("""
        QMainWindow {
            background-color: #1e1e1e;
        }
        QWidget {
            background-color: #252526;
            color: #cccccc;
        }
        QPushButton {
            background-color: #0e639c;
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 3px;
            min-width: 80px;
        }
        QPushButton:hover {
            background-color: #1177bb;
        }
        QPushButton:pressed {
            background-color: #094771;
        }
        QPushButton:disabled {
            background-color: #555555;
            color: #888888;
        }
        QLabel {
            color: #cccccc;
        }
        QLineEdit {
            background-color: #3c3c3c;
            color: white;
            border: 1px solid #555;
            padding: 4px;
            border-radius: 3px;
        }
        QComboBox {
            background-color: #3c3c3c;
            color: white;
            border: 1px solid #555;
            padding: 4px;
            border-radius: 3px;
        }
        QSpinBox, QDoubleSpinBox {
            background-color: #3c3c3c;
            color: white;
            border: 1px solid #555;
            padding: 4px;
        }
        QTextEdit {
            background-color: #1e1e1e;
            color: #cccccc;
            border: 1px solid #444;
            font-family: Consolas, monospace;
        }
        QSplitter::handle {
            background-color: #444444;
            width: 2px;
            height: 2px;
        }
    """)

    logger.info("=" * 60)
    logger.info("启动 INAV Stellar Ground Control Station")
    logger.info("=" * 60)

    # 创建并显示主窗口
    window = MainWindow()
    window.show()

    # 运行事件循环
    exit_code = app.exec_()

    logger.info("应用程序正常退出")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()