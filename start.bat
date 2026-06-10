@echo off
chcp 65001 >nul 2>&1
set PYTHON=C:\Users\Q\AppData\Local\Programs\Python\Python312\python.exe
cd /d "%~dp0"
"%PYTHON%" main.py
pause
