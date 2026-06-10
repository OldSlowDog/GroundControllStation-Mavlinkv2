@echo off
echo ============================================
echo   Installing Python Dependencies
echo ============================================
echo.

REM Try different Python installations
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found in PATH!
    echo Please install Python from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [INFO] Using Python:
python --version
echo.

echo [1/5] Installing PyQt5...
pip install PyQt5 --quiet
if %errorlevel% neq 0 (
    echo [WARN] PyQt5 installation had issues, continuing...
)

echo [2/5] Installing pyserial...
pip install pyserial --quiet
if %errorlevel% neq 0 (
    echo [WARN] pyserial installation had issues, continuing...
)

echo [3/5] Installing pyqtgraph...
pip install pyqtgraph --quiet
if %errorlevel% neq 0 (
    echo [WARN] pyqtgraph installation had issues, continuing...
)

echo [4/5] Installing numpy...
pip install numpy --quiet
if %errorlevel% neq 0 (
    echo [WARN] numpy installation had issues, continuing...
)

echo [5/5] Installing pyyaml...
pip install pyyaml --quiet
if %errorlevel% neq 0 (
    echo [WARN] pyyaml installation had issues, continuing...
)

echo.
echo ============================================
echo   Installation Complete!
echo ============================================
echo.
echo Now you can run: python main.py
echo.
pause