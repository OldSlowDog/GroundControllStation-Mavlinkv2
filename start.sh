#!/bin/bash
echo "============================================"
echo "  INAV Stellar Ground Control Station"
echo "  飞控上位机调试软件 v1.0"
echo "============================================"
echo ""

# 检查Python
if ! command -v python3 &> /dev/null; then
    if ! command -v python &> /dev/null; then
        echo "[错误] 未检测到 Python，请先安装 Python 3.8+"
        exit 1
    fi
fi

# 安装依赖
echo "[1/2] 检查依赖包..."
pip3 install -r requirements.txt 2>/dev/null || pip install -r requirements.txt

# 启动应用
echo "[2/2] 启动应用程序..."
echo ""
python3 main.py || python main.py